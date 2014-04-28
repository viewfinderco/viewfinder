# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Run analysis over all merged user analytics logs.

Computes speed percentiles for full asset scans (only those lasting more than 1s for more accurate numbers).

Automatically finds the list of merged logs in S3. If --start_date=YYYY-MM-DD is specified, only analyze logs
starting from a week before that date (we give user logs that much time to get uploaded).


Usage:
# Analyze all logs.
python -m viewfinder.backend.logs.analyze_analytics_logs

# Analyze logs from a specific start date.
python -m viewfinder.backend.logs.analyze_analytics_logs --start_date=2012-12-15

Other options:
-require_lock: default=True: hold the job:analyze_analytics lock during processing.
-smart_scan: default=False: determine the start date from previous run summaries.
-hours_between_runs: default=0: don't run if last successful run started less than this many hours ago.

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import cStringIO
import json
import logging
import numpy
import os
import sys
import time
import traceback

from collections import defaultdict, Counter
from tornado import gen, options
from viewfinder.backend.base import constants, main, statistics, util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import db_client
from viewfinder.backend.db.job import Job
from viewfinder.backend.logs import logs_util
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.storage import store_utils

# TODO(marc): automatic date detection (eg: find latest metric entry and process from 30 days before).
options.define('start_date', default=None, help='Start date (filename start key). May be overridden by smart_scan.')
options.define('dry_run', default=True, help='Do not update dynamodb metrics table')
options.define('compute_today', default=False, help='Do not compute statistics for today, logs will be partial')
options.define('require_lock', type=bool, default=True,
               help='attempt to grab the job:analyze_analytics lock before running. Exit if acquire fails.')
options.define('smart_scan', type=bool, default=False,
               help='determine start_date from previous successful runs.')
options.define('hours_between_runs', type=int, default=0,
               help='minimum time since start of last successful run (with dry_run=False)')

class DayStats(object):
  def __init__(self, day):
    self.day = day
    self._scan_durations = []
    self._long_scan_speeds = []
    self._photos_scanned = []
    # Number of unique users recording an event on this day.
    self.event_users = Counter()
    # Number of occurrences of an event aggregated across all users.
    self.total_events = Counter()

  def AddScan(self, version, photos, duration):
    self._scan_durations.append(duration)
    self._photos_scanned.append(photos)
    if duration > 1.0:
      self._long_scan_speeds.append(photos / duration)

  def AddEvents(self, counters):
    for name, count in counters.iteritems():
      self.total_events[name] += count
      self.event_users[name] += 1

  def PrintSummary(self):
    logging.info('Day: %s\n %s' % (self.day, statistics.FormatStats(self._long_scan_speeds, percentiles=[90,95,99])))

  def ScanDurationPercentile(self, percentile):
    return numpy.percentile(self._scan_durations, percentile)

  def LongScanSpeedPercentile(self, percentile):
    return numpy.percentile(self._long_scan_speeds, percentile)

  def PhotosScannedPercentile(self, percentile):
    return numpy.percentile(self._photos_scanned, percentile)


@gen.engine
def ProcessFiles(merged_store, filenames, callback):
  """Fetch and process each file contained in 'filenames'."""

  @gen.engine
  def _ProcessOneFile(contents, day_stats):
    """Iterate over the contents of a processed file: one entry per line. Increment stats for specific entries."""
    buf = cStringIO.StringIO(contents)
    buf.seek(0)
    ui_events = Counter()
    while True:
      line = buf.readline()
      if not line:
        break
      parsed = json.loads(line)
      if not parsed:
        continue
      if 'version' not in parsed:
        continue
      # TODO(marc): lookup the user's device ID in dynamodb and get device model.
      payload = parsed['payload']
      if 'name' in payload:
        if payload['name'] == '/assets/scan' and payload['type'] == 'full':
          day_stats.AddScan(parsed['version'], payload['num_scanned'], payload['elapsed'])
        elif payload['name'].startswith('/ui/'):
          ui_events[payload['name']] += 1
    if ui_events:
      ui_events['/ui/anything'] += 1
    day_stats.AddEvents(ui_events)
    buf.close()

  today = util.NowUTCToISO8601()
  # Group filenames by day.
  files_by_day = defaultdict(list)
  for filename in filenames:
    _, day, user = filename.split('/')
    if options.options.compute_today or today != day:
      files_by_day[day].append(filename)

  # Compute per-day totals. Toss them into a list, we'll want it sorted.
  stats_by_day = {}
  for day in sorted(files_by_day.keys()):
    # We don't really need to process days in-order, but it's nicer.
    files = files_by_day[day]
    day_stats = DayStats(day)
    for f in files:
      contents = ''
      try:
        contents = yield gen.Task(merged_store.Get, f)
      except Exception as e:
        logging.error('Error fetching file %s: %r' % (f, e))
        continue
      _ProcessOneFile(contents, day_stats)
    if len(day_stats._long_scan_speeds) == 0:
      continue
    dd = DotDict()
    for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]:
      dd['user_analytics.scans_gt1s_speed_percentile.%.2d' % p] = day_stats.LongScanSpeedPercentile(p)
      dd['user_analytics.scans_duration_percentile.%.2d' % p] = day_stats.ScanDurationPercentile(p)
      dd['user_analytics.scans_num_photos_percentile.%.2d' % p] = day_stats.PhotosScannedPercentile(p)
    dd['user_analytics.ui.event_users'] = day_stats.event_users
    dd['user_analytics.ui.total_events'] = day_stats.total_events
    stats_by_day[day] = dd

  callback(stats_by_day)

@gen.engine
def GetMergedLogsFileList(merged_store, marker, callback):
  """Fetch the list of file names from S3."""
  registry_dir = os.path.join(logs_util.UserAnalyticsLogsPaths.kMergedLogsPrefix,
                              logs_util.UserAnalyticsLogsPaths.kRegistryDir)
  def _WantFile(filename):
    return not filename.startswith(registry_dir)

  base_path = logs_util.UserAnalyticsLogsPaths.kMergedLogsPrefix + '/'
  marker = os.path.join(base_path, marker) if marker is not None else None
  file_list = yield gen.Task(store_utils.ListAllKeys, merged_store, prefix=base_path, marker=marker)
  files = [f for f in file_list if _WantFile(f)]
  files.sort()

  logging.info('found %d merged log files, analyzing %d' % (len(file_list), len(files)))
  callback(files)


@gen.engine
def RunOnce(client, job, callback):
  """Get list of files and call processing function."""
  merged_store = ObjectStore.GetInstance(logs_util.UserAnalyticsLogsPaths.MERGED_LOGS_BUCKET)

  start_date = options.options.start_date
  if options.options.smart_scan:
    # Search for successful full-scan run in the last week.
    last_run = yield gen.Task(job.FindLastSuccess, with_payload_key='stats.last_day')
    if last_run is None:
      logging.info('No previous successful scan found, rerun with --start_date')
      callback(None)
      return

    last_run_start = last_run['start_time']
    if util.HoursSince(last_run_start) < options.options.hours_between_runs:
      logging.info('Last successful run started at %s, less than %d hours ago; skipping.' %
                   (time.asctime(time.localtime(last_run_start)), options.options.hours_between_runs))
      callback(None)
      return

    last_day = last_run['stats.last_day']
    # Set scan_start to start of previous run - 30d (we need 30 days' worth of data to properly compute
    # 30-day active users. Add an extra 3 days just in case we had some missing logs during the last run.
    start_time = util.ISO8601ToUTCTimestamp(last_day, hour=12) - constants.SECONDS_PER_WEEK
    start_date = util.TimestampUTCToISO8601(start_time)
    logging.info('Last successful analyze_analytics run (%s) scanned up to %s, setting analysis start date to %s' %
                 (time.asctime(time.localtime(last_run_start)), last_day, start_date))

  # Fetch list of merged logs.
  files = yield gen.Task(GetMergedLogsFileList, merged_store, start_date)
  day_stats = yield gen.Task(ProcessFiles, merged_store, files)

  # Write per-day stats to dynamodb.
  if len(day_stats) > 0:
    hms = logs_util.kDailyMetricsTimeByLogType['analytics_logs']
    yield gen.Task(logs_util.UpdateMetrics, client, day_stats, dry_run=options.options.dry_run, hms_tuple=hms)
    last_day = sorted(day_stats.keys())[-1]
    callback(last_day)
  else:
    callback(None)

@gen.engine
def _Start(callback):
  """Grab a lock on job:analyze_analytics and call RunOnce. If we get a return value, write it to the job summary."""
  client = db_client.DBClient.Instance()
  job = Job(client, 'analyze_analytics')

  if options.options.require_lock:
    got_lock = yield gen.Task(job.AcquireLock)
    if got_lock == False:
      logging.warning('Failed to acquire job lock: exiting.')
      callback()
      return

  result = None
  job.Start()
  try:
    result = yield gen.Task(RunOnce, client, job)
  except:
    # Failure: log run summary with trace.
    typ, val, tb = sys.exc_info()
    msg = ''.join(traceback.format_exception(typ, val, tb))
    logging.info('Registering failed run with message: %s' % msg)
    yield gen.Task(job.RegisterRun, Job.STATUS_FAILURE, failure_msg=msg)
  else:
    if result is not None and not options.options.dry_run:
      # Successful run with data processed and not in dry-run mode: write run summary.
      stats = DotDict()
      stats['last_day'] = result
      logging.info('Registering successful run with stats: %r' % stats)
      yield gen.Task(job.RegisterRun, Job.STATUS_SUCCESS, stats=stats)
  finally:
    yield gen.Task(job.ReleaseLock)

  callback()


if __name__ == '__main__':
  sys.exit(main.InitAndRun(_Start))
