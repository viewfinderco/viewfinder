# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Go over multi-day processed server log data and compute metrics to store in dynamodb.

Computes:
- count of 1/7/30 day active users per type of request.
- count of (not) registered installs per day as well as the "time to register". Since the window to look for
  registration is two weeks, the stats can vary every day for up to that long.

Usage:
# Compute metrics for needed days (based on date of last successful run)
python -m viewfinder.backend.logs.server_log_metrics --smart_scan=True

# Compute metrics from a specific date.
python -m viewfinder.backend.logs.server_log_metrics --start_date=2012-12-15

Other options:
-ec2_only: default=True: only analyze logs from AWS instances.
-require_lock: default=True: hold the job:server_log_metrics lock during processing.
-smart_scan: default=False: determine the start date from previous run summaries.
-hours_between_runs: default=0: don't run if last successful run started less than this many hours ago.

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import cStringIO
import json
import logging
import numpy
import os
import re
import sys
import time
import traceback

from collections import Counter, defaultdict
from itertools import islice
from tornado import gen, options
from viewfinder.backend.base import constants, main, util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import db_client
from viewfinder.backend.db.job import Job
from viewfinder.backend.logs import logs_util
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.storage import store_utils
from viewfinder.backend.services.email_mgr import EmailManager, LoggingEmailManager, SendGridEmailManager

options.define('start_date', default=None, help='Start date (filename start key). May be overridden by smart_scan.')
options.define('ec2_only', default=True, help='AWS instances only')
options.define('dry_run', default=True, help='Do not update dynamodb metrics table')
options.define('require_lock', type=bool, default=True,
               help='attempt to grab the job:server_log_metrics lock before running. Exit if acquire fails.')
options.define('smart_scan', type=bool, default=False,
               help='determine start_date from previous successful runs.')
options.define('hours_between_runs', type=int, default=0,
               help='minimum time since start of last successful run (with dry_run=False)')
options.define('max_days_to_process', default=None, type=int,
               help='Process at most this many days (in chronological order)')
options.define('compute_user_requests', default=True, help='Compute user requests stats')
options.define('compute_registration_delay', default=True, help='Compute user registration delay stats')
options.define('compute_app_versions', default=True, help='Compute app version stats')
options.define('compute_traces', default=True, help='Summarize stack traces')
options.define('compute_aborts', default=True, help='Summarize abort messages')
options.define('send_email', default=True, help='Email summary of traces')
options.define('extra_trace_days', default=7, help='Analyze this many extra days to filter out known trace failures')

options.define('email', default='crash-reports+backend@emailscrubbed.com', help='Email address to notify')
options.define('s3_url_expiration_days', default=14, help='Time to live in days for S3 URLs')

# Window to look for device_uuid registration. If it takes longer than this for a user to register, we consider them
# unregistered.
kDeviceRegistrationWindowDays = 14

@gen.engine
def ComputeUserRequests(merged_store, filenames, callback):
  """Fetch and process each file contained in 'filenames'."""

  # Compute per-day totals. Toss them into a list, we'll want it sorted.
  stats_by_day = list()
  for f in filenames:
    # We don't really need to process days in-order, but it's nicer.
    day = f.split('/')[-1]
    day_stats = logs_util.DayUserRequestStats(day)

    # Let exceptions surface.
    contents = yield gen.Task(merged_store.Get, f)
    dotdict = json.loads(contents)
    day_stats.FromDotDict(dotdict)
    stats_by_day.append(day_stats)

  stats_by_day.sort(key=lambda stat: stat.day)

  def _Window(seq, n=2):
    """ From itertools examples: http://docs.python.org/release/2.3.5/lib/itertools-example.html
    Returns a sliding window (of width n) over data from the iterable
    s -> (s0,s1,...s[n-1]), (s1,s2,...,sn), ...
    """
    it = iter(seq)
    result = tuple(islice(it, n))
    if len(result) == n:
      yield result
    for elem in it:
      result = result[1:] + (elem,)
      yield result

  def _StatsByRange(seq, days):
    """Returns a list of day stats with each entry being the sum of #days consecutive days. The day field
    corresponds to the last day of each interval.
    """
    windows = _Window(seq, n=days)
    day_stats = list()
    for day_list in windows:
      total = logs_util.DayUserRequestStats(day_list[-1].day)
      for day in day_list:
        total.MergeFrom(day)
      day_stats.append(total)
    return day_stats

  def _AddToDayDict(dd, day_stat, suffix):
    """Add the various request categories to the day dict."""
    dd[day_stat.day]['active_users.requests_all.%s' % suffix] = len(day_stat._active_all)
    dd[day_stat.day]['active_users.requests_post.%s' % suffix] = len(day_stat._active_post)
    dd[day_stat.day]['active_users.requests_share.%s' % suffix] = len(day_stat._active_share)
    dd[day_stat.day]['active_users.requests_view.%s' % suffix] = len(day_stat._active_view)

  # TODO(marc): we should handle days without stats at all (bad logs or logs merge).
  day_dict = defaultdict(DotDict)
  for stats in stats_by_day:
    _AddToDayDict(day_dict, stats, '1d')

  for stats in _StatsByRange(stats_by_day, 7):
    _AddToDayDict(day_dict, stats, '7d')

  for stats in _StatsByRange(stats_by_day, 30):
    _AddToDayDict(day_dict, stats, '30d')

  callback(day_dict)


@gen.engine
def ComputeRegistrationDelay(merged_store, filenames, stats_start_date, callback):
  """Fetch and process device details for each file contained in 'filenames'."""

  # Dict of 'device_uuid' -> (first_seen_timestamp, first_registered_timestamp)
  # 'first_seen' is the time at which we first saw a ping request for this uuid, where device_id was not set.
  # 'first_registered' is the time at which we saw the first request for this uuid, where a device_id was set.
  uuid_dict = {}

  def _AddUnknown(device_uuid, timestamp):
    """Set a device_uuid as 'seen without a device_id'."""
    seen_ts, registered_ts = uuid_dict.get(device_uuid, (None, None))
    if seen_ts is None or seen_ts > timestamp:
      uuid_dict[device_uuid] = (timestamp, registered_ts)

  def _AddRegistered(device_uuid, timestamp):
    """Register a device_uuid as 'seen with a device_id'."""
    seen_ts, registered_ts = uuid_dict.get(device_uuid, (None, None))
    if registered_ts is None or registered_ts > timestamp:
      uuid_dict[device_uuid] = (seen_ts, timestamp)

  def _ProcessDeviceDict(device_dict, timestamp):
    """Process a device dict. It may come from either ping or Device/User requests."""
    if not device_dict:
      # Empty device entry in the request; skip.
      return
    dev_uuid = device_dict.get('device_uuid', None)
    if not dev_uuid:
      # No device_uuid field in the device dict; skip.
      return

    # Skip dev versions.
    version = device_dict.get('version', None)
    if version and version.endswith('.dev'):
      return
    # Skip iphone simulator. warning: nothing would prevent someone from naming their phone like this.
    # The name is only in plain text in the ping request, which is exactly the one we want to filter out.
    name = device_dict.get('name', None)
    if name and name == 'iPhone Simulator':
      return

    dev_id = device_dict.get('device_id', None)
    if dev_id is not None:
      _AddRegistered(dev_uuid, timestamp)
    else:
      _AddUnknown(dev_uuid, timestamp)


  # Make sure we process files in chronological order.
  for f in sorted(filenames):
    day = f.split('/')[-1]

    # Let exceptions surface.
    contents = yield gen.Task(merged_store.Get, f)
    dev_list = json.loads(contents)
    for entry in dev_list:
      timestamp = entry['timestamp']
      method = entry['method']
      req = entry['request']
      if not req:
        continue
      if method == 'ping':
        _ProcessDeviceDict(req.get('device', None), timestamp)
        # TODO(marc): compute stats on response sent back in ping.
      else:
        assert method in ('Device.UpdateOperation', 'User.RegisterOperation', 'RegisterUserOperation.Execute'), \
          'Unexpected entry: %r' % entry
        _ProcessDeviceDict(req.get('device_dict', None), timestamp)

  # Go through the uuid_dict and build up per-day counts and list of deltas.
  day_delta = defaultdict(list)
  day_registered = Counter()
  day_non_registered = Counter()
  day_total = Counter()
  registration_window_secs = kDeviceRegistrationWindowDays * constants.SECONDS_PER_DAY
  for k, (s, e) in uuid_dict.iteritems():
    if s is None:
      # No start time for this uuid. Either it was before our two-week window, or before an app version with ping.
      continue

    start_day = util.TimestampUTCToISO8601(s)
    if e is None or (e - s) > registration_window_secs:
      # Not registered: either we did not see a registration, or it was beyond the window.
      # We use a window because the number of days processed may vary (eg: pipeline was broken for a week).
      # Increment the "non registered" count for the start day.
      day_non_registered[start_day] += 1
      day_total[start_day] += 1
      continue

    # Registered.
    # Increment the "registered" count and the "registration delay (in hours)" for the start day.
    day_registered[start_day] += 1
    day_total[start_day] += 1
    day_delta[start_day].append((e - s) / 3600.0)

  # The 'stats_start_date' is different from the date of the earliest log we examine. This is because we do not
  # want an unregistered device that has been pinging every day for ages to count as being new on our first stat day.
  # We'll usually examine an extra 5 days of data even though we don't care about those days' numbers.
  day_stats = defaultdict(DotDict)
  for k, v in day_total.iteritems():
    if k >= stats_start_date:
      day_stats[k]['device_installs.registration.all'] = v
  for k, v in day_registered.iteritems():
    if k >= stats_start_date:
      day_stats[k]['device_installs.registration.yes'] = v
  for k, v in day_non_registered.iteritems():
    if k >= stats_start_date:
      day_stats[k]['device_installs.registration.no'] = v
  for k, v in day_delta.iteritems():
    if k >= stats_start_date:
      percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
      res = numpy.percentile(v, percentiles)
      for per, val in zip(percentiles, res):
        day_stats[k]['device_installs.registration.delay_hours_percentile.%.2d' % per] = val

  callback(day_stats)


@gen.engine
def ComputeAppVersions(merged_store, filenames, callback):
  """Compute count of devices per version for each day. If a device is seen with different versions, count newest."""

  def _ProcessOneEntry(entry, uuid_dict):
    timestamp = entry['timestamp']
    method = entry['method']
    req = entry['request']
    if not req:
      return
    ddict = None
    if method == 'ping':
      ddict = req.get('device', None)
    else:
      assert method in ('Device.UpdateOperation', 'User.RegisterOperation', 'RegisterUserOperation.Execute'), \
        'Unexpected entry: %r' % entry
      ddict =  req.get('device_dict', None)
    if not ddict:
      return
    dev_uuid = ddict.get('device_uuid', None)
    if not dev_uuid:
      return
    version = ddict.get('version', None)
    if not version or version.endswith('.dev'):
      # Skip missing version or dev versions.
      return

    name = ddict.get('name', None)
    if name and name == 'iPhone Simulator':
      return

    # We register these fields straight out if they are present in the device dict, overwriting previous entries.
    for k in ['platform', 'os', 'language', 'country']:
      val = ddict.get(k, None)
      if val:
        uuid_dict[dev_uuid][k] = val

    prev_version = uuid_dict[dev_uuid].get('version', None)
    # Only register the latest version seen.
    if not prev_version or cmp(version.split('.'), prev_version.split('.')) > 0:
      uuid_dict[dev_uuid]['version'] = version


  day_dict = defaultdict(list)
  # Build dict of day -> list of files
  for f in filenames:
    day_dict[f.split('/')[-1]].append(f)

  # Go over each day's files.
  day_stats = defaultdict(DotDict)
  for day in sorted(day_dict.keys()):
    file_list = day_dict[day]

    # latest version per UUID.
    uuid_dict = defaultdict(dict)
    for f in file_list:
      # Let exceptions surface.
      contents = yield gen.Task(merged_store.Get, f)
      dev_list = json.loads(contents)
      for entry in dev_list:
        _ProcessOneEntry(entry, uuid_dict)

    # Count number of entries for each version. Counters are great.
    def _CounterFromField(field):
      return Counter(x[field] for x in uuid_dict.values() if field in x)

    count_by_platform = _CounterFromField('platform')
    for platform, count in count_by_platform.iteritems():
      day_stats[day]['device_count.platform.%s' % platform.replace('.', '_')] = count
    count_by_os = _CounterFromField('os')
    for os, count in count_by_os.iteritems():
      day_stats[day]['device_count.os.%s' % os.replace('.', '_').replace('iPhone OS', 'iOS')] = count
    count_by_version = _CounterFromField('version')
    for version, count in count_by_version.iteritems():
      day_stats[day]['device_count.version.%s' % version.replace('.', '_')] = count
    # These fields can be copied without modification.
    for k in ['language', 'country']:
      counter = _CounterFromField(k)
      for value, count in counter.iteritems():
        day_stats[day]['device_count.%s.%s' % (k, value)] = count

  callback(day_stats)

@gen.engine
def _SendEmail(from_name, title, text, callback):
  args = {
    'from': 'crash-reports+backend@emailscrubbed.com',
    'fromname': from_name,
    'to': options.options.email,
    'subject': title,
    'text': text
    }
  yield gen.Task(EmailManager.Instance().SendEmail, description=title, **args)
  callback()


@gen.engine
def ComputeTraces(merged_store, filenames, start_date, callback):
  """Summarize the list of failure traces."""

  seen_traces = Counter()
  text = ''
  days = []
  unique_traces = 0
  for f in sorted(filenames):
    day = f.split('/')[-1]
    # Let exceptions surface.
    contents = yield gen.Task(merged_store.Get, f)
    trace_list = json.loads(contents)

    failure_count = Counter()
    sample_trace = {}

    for entry in trace_list:
      if entry.get('type', None) != 'traceback':
        continue
      trace = entry.get('trace', None)
      if not trace:
        continue
      lines = logs_util.ParseTraceDump(trace)
      if len(lines) < 2:
        continue
      parsed = logs_util.ParseTraceLocationLine(lines[-2])
      if not parsed:
        continue
      # 'parsed' is made up of: (filename, line, method)
      # We may not want to include line numbers, but for now, we only aggregate per day, so it's safe enough.
      failure_count[parsed] += 1
      sample_trace[parsed] = lines

    if day <= start_date:
      # Extra analysis days: record all traces seen but don't generate text.
      seen_traces.update(failure_count)
      continue

    days.append(day)
    text += '\n-------- Traces for %s --------\n' % day
    unique_traces += len(failure_count)
    for key in failure_count.keys():
      trace = sample_trace[key]
      text += '\n--- %d in %s, L%s (%s):\n' % (failure_count[key], key[0], key[1], key[2])
      if key in seen_traces:
        # This trace was seen in prior non-displayed days: only show the summary line.
        text += '(seen %d times in the previous %d days)\n' % (seen_traces[key], options.options.extra_trace_days)
        continue
      text += '%s\n' % trace[0]
      for line in trace[1:]:
        if logs_util.ParseTraceLocationLine(line) is not None:
          text += '%s\n' % line
        else:
          text += '    %s\n' % line

  if unique_traces > 0:
    title = 'Backend Traces for %s' % ', '.join(days)
    yield gen.Task(_SendEmail, 'Traceback', title, text)

  callback()


@gen.engine
def ComputeAborts(merged_store, filenames, start_date, callback):
  """Summarize the list of ABORT messages."""

  # The store object for client logs (only used to generate S3 URLs).
  client_log_store = ObjectStore.GetInstance(ObjectStore.USER_LOG)

  total_failures = 0
  text = ''
  days = []
  for f in sorted(filenames):
    day = f.split('/')[-1]
    if day <= start_date:
      # For now, we don't do duplicate analysis, so ignore the extra week of files.
      # TODO(marc): do duplicate analysis :)
      continue

    # Let exceptions surface.
    contents = yield gen.Task(merged_store.Get, f)
    trace_list = json.loads(contents)

    failures = 0
    day_text = ''

    def _S3URL(filename):
      return client_log_store.GenerateUrl(filename,
                                          expires_in=constants.SECONDS_PER_DAY * options.options.s3_url_expiration_days,
                                          content_type='text/plain')

    def _UserDeviceURL(user_id, device_id):
      return 'https://staging.viewfinder.co/admin/db?table=Device&type=view&hash_key=%s&sort_key=%s&sort_desc=EQ' % \
             (user_id, device_id)

    for entry in trace_list:
      if entry.get('type', None) != 'abort':
        continue

      trace = entry.get('trace', None)
      if not trace:
        continue

      parsed = logs_util.ParseAbortMsg(trace)
      if not parsed:
        continue

      # 'parsed' is made up of: (user, device, op, class_name, method_name, message)
      user, device, op, classname, methodname, _ = parsed

      # We always assume this is attempt 0 for the op.
      s3path = os.path.join(user, day, 'op', '%s.%s' % (classname, methodname), op, '0')
      context_before = entry.get('context_before')
      context = '\n' + '    \n'.join(context_before) if context_before else 'None'
      day_text += '\nMessage: %s\nPrevious lines: %s\nDevice: %s\nOp log: %s\n' % \
                  (trace, context, _UserDeviceURL(user, device), _S3URL(s3path))
      failures += 1

    days.append(day)
    if failures:
      text += '\n-------- %d ABORT messages for %s --------\n' % (failures, day) + day_text
      total_failures += failures

  if total_failures > 0:
    title = 'Abort messages for %s' % ', '.join(days)
    yield gen.Task(_SendEmail, 'Aborts', title, text)

  callback()


@gen.engine
def GetFileList(merged_store, subdir, marker, callback):
  """Fetch the list of file names from S3."""
  base_path = 'processed_data/%s/' % subdir
  marker = os.path.join(base_path, marker) if marker is not None else None
  file_list = yield gen.Task(store_utils.ListAllKeys, merged_store, prefix=base_path, marker=marker)
  file_list.sort()

  logging.info('found %d %s files' % (len(file_list), subdir))
  callback(file_list)


@gen.engine
def RunOnce(client, job, callback):
  """Get list of files and call processing function."""
  logs_paths = logs_util.ServerLogsPaths('viewfinder', 'full')
  merged_store = ObjectStore.GetInstance(logs_paths.MERGED_LOGS_BUCKET)

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

    # Compute stats for all days since the last run (inclusive).
    start_date = last_run['stats.last_day']
    logging.info('Last successful server_log_metrics run (%s) scanned up to %s' %
                 (time.asctime(time.localtime(last_run_start)), start_date))

  assert start_date is not None, 'No start date provided. Use --start_date=YYYY-MM-DD or --smart_scan=True'

  last_day = None
  if options.options.compute_user_requests:
    # We look for files going back 32 days (30 because we need 30-day active users, and +2 for extra safety).
    user_start_time = util.ISO8601ToUTCTimestamp(start_date, hour=12) - 32 * constants.SECONDS_PER_DAY
    user_start_date = util.TimestampUTCToISO8601(user_start_time)
    # Fetch list of per-day user request stats.
    files = yield gen.Task(GetFileList, merged_store, 'user_requests', user_start_date)
    user_request_stats = yield gen.Task(ComputeUserRequests, merged_store, files)

    # Write per-day stats to dynamodb.
    if len(user_request_stats) > 0:
      # We do not replace the 'active_users' category in previous metrics as we may not be recomputing all data
      # eg: we need to analyze 30 days of logs to get the full metric info.
      hms = logs_util.kDailyMetricsTimeByLogType['active_users']
      yield gen.Task(logs_util.UpdateMetrics, client, user_request_stats,
                     dry_run=options.options.dry_run, hms_tuple=hms)
      last_day = sorted(user_request_stats.keys())[-1]


  if options.options.compute_registration_delay:
    # We compute stats for days within the registration window (plus an extra two for safety).
    device_start_time = util.ISO8601ToUTCTimestamp(start_date, hour=12) - \
                        (kDeviceRegistrationWindowDays + 2) * constants.SECONDS_PER_DAY
    device_start_date = util.TimestampUTCToISO8601(device_start_time)
    # However, we search for files for an extra 15 days. This is so that unregistered devices that ping every day
    # are not counted as starting on the first day of stats.
    device_search_time = device_start_time - 15 * constants.SECONDS_PER_DAY
    device_search_date = util.TimestampUTCToISO8601(device_search_time)
    # Fetch list of merged logs.
    files = yield gen.Task(GetFileList, merged_store, 'device_details', device_search_date)
    device_stats = yield gen.Task(ComputeRegistrationDelay, merged_store, files, device_start_date)

    # Write per-day stats to dynamodb.
    if len(device_stats) > 0:
      # Replace the entire 'device_installs.registration' category
      hms = logs_util.kDailyMetricsTimeByLogType['device_installs']
      yield gen.Task(logs_util.UpdateMetrics, client, device_stats, dry_run=options.options.dry_run, hms_tuple=hms,
                     prefix_to_erase='device_installs.registration')

      last_day_device = sorted(device_stats.keys())[-1]
      if last_day is None or last_day > last_day_device:
        # We consider the last successful processing day to be the earlier of the two.
        last_day = last_day_device

  if options.options.compute_app_versions:
    # Look at an extra two days for safety.
    version_start_time = util.ISO8601ToUTCTimestamp(start_date, hour=12) - 2 * constants.SECONDS_PER_DAY
    version_start_date = util.TimestampUTCToISO8601(version_start_time)
    # Fetch list of merged logs.
    files = yield gen.Task(GetFileList, merged_store, 'device_details', version_start_date)
    version_stats = yield gen.Task(ComputeAppVersions, merged_store, files)

    # Write per-day stats to dynamodb.
    if len(version_stats) > 0:
      # Replace the entire 'device_installs.registration' category
      hms = logs_util.kDailyMetricsTimeByLogType['device_count']
      yield gen.Task(logs_util.UpdateMetrics, client, version_stats, dry_run=options.options.dry_run, hms_tuple=hms,
                     prefix_to_erase='device_count')

      last_day_device = sorted(version_stats.keys())[-1]
      if last_day is None or last_day > last_day_device:
        # We consider the last successful processing day to be the earlier of the two.
        last_day = last_day_device

  if options.options.compute_traces or options.options.compute_aborts:
    # Fetch an extra 7 days to filter out previously-seen traces.
    trace_start_time = (util.ISO8601ToUTCTimestamp(start_date, hour=12) -
                        options.options.extra_trace_days * constants.SECONDS_PER_DAY)
    trace_start_date = util.TimestampUTCToISO8601(trace_start_time)
    # Fetch list of merged logs.
    files = yield gen.Task(GetFileList, merged_store, 'traces', trace_start_date)
    # Run them separately, we'll be sending separate email reports.
    if options.options.compute_traces:
      yield gen.Task(ComputeTraces, merged_store, files, start_date)
    if options.options.compute_aborts:
      yield gen.Task(ComputeAborts, merged_store, files, start_date)

  callback(last_day)


@gen.engine
def _Start(callback):
  """Grab a lock on job:server_log_metrics and call RunOnce. If we get a return value, write it to the job summary."""
  if options.options.send_email:
    # When running on devbox, this prompts for the passphrase. Skip if not sending email.
    EmailManager.SetInstance(SendGridEmailManager())
  else:
    EmailManager.SetInstance(LoggingEmailManager())

  client = db_client.DBClient.Instance()
  job = Job(client, 'server_log_metrics')

  if options.options.require_lock:
    got_lock = yield gen.Task(job.AcquireLock)
    if got_lock == False:
      logging.warning('Failed to acquire job lock: exiting.')
      callback()
      return

  is_full_run = all([options.options.compute_user_requests,
                     options.options.compute_registration_delay,
                     options.options.compute_app_versions])

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
    if result is not None and not options.options.dry_run and is_full_run:
      # Successful full run with data processed and not in dry-run mode: write run summary.
      stats = DotDict()
      stats['last_day'] = result
      logging.info('Registering successful run with stats: %r' % stats)
      yield gen.Task(job.RegisterRun, Job.STATUS_SUCCESS, stats=stats)
  finally:
    yield gen.Task(job.ReleaseLock)

  callback()


if __name__ == '__main__':
  sys.exit(main.InitAndRun(_Start))
