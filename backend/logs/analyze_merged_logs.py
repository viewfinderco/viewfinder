# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Run analysis over all merged log files stored in S3.

This processes wanted data and writes output files to S3.

Data processed:
- per day/per user count of requests by type. stored in S3://serverdata/processed_data/user_requests/YYYY-MM-DD


Usage:
# Analyze logs written since the last run (plus an extra two days to catch any stragglers).
python -m viewfinder.backend.logs.analyze_merged_logs --smart_scan=True

# Analyze logs from a specific start date.
python -m viewfinder.backend.logs.analyze_merged_logs --start_date=2012-12-15

Other options:
-ec2_only: default=True: only analyze logs from AWS instances.
-require_lock: default=True: hold the job:analyze_logs lock during processing.
-smart_scan: default=False: determine the start date from previous run summaries.
-hours_between_runs: default=0: don't run if last successful run started less than this many hours ago.

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import cStringIO
import json
import logging
import os
import re
import sys
import time
import traceback

from collections import Counter, defaultdict, deque
from itertools import islice
from tornado import gen, options
from viewfinder.backend.base import constants, main, util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import db_client
from viewfinder.backend.db.job import Job
from viewfinder.backend.logs import logs_util
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.storage import store_utils

options.define('start_date', default=None, help='Start date (filename start key). May be overridden by smart_scan.')
options.define('ec2_only', default=True, help='AWS instances only')
options.define('dry_run', default=True, help='Do not update dynamodb metrics table')
options.define('compute_today', default=False, help='Do not compute statistics for today, logs will be partial')
options.define('require_lock', type=bool, default=True,
               help='attempt to grab the job:analyze_logs lock before running. Exit if acquire fails.')
options.define('smart_scan', type=bool, default=False,
               help='determine start_date from previous successful runs.')
options.define('hours_between_runs', type=int, default=0,
               help='minimum time since start of last successful run (with dry_run=False)')
options.define('max_days_to_process', default=None, type=int,
               help='Process at most this many days (in chronological order)')
options.define('trace_context_num_lines', default=2, type=int,
               help='Number of lines of context to save before and after a Trace (eg: 2 before and 2 after)')
options.define('process_op_abort', default=True, type=bool,
               help='Process and store traces for OP ABORT lines')
options.define('process_traceback', default=True, type=bool,
               help='Process and store Traceback lines')

kTracebackRE = re.compile(r'Traceback \(most recent call last\)')

@gen.engine
def ProcessFiles(merged_store, logs_paths, filenames, callback):
  """Fetch and process each file contained in 'filenames'."""

  def _ProcessOneFile(contents, day_stats, device_entries, trace_entries):
    """Iterate over the contents of a processed file: one entry per line. Increment stats for specific entries."""
    buf = cStringIO.StringIO(contents)
    buf.seek(0)
    # Max len is +1 since we include the current line. It allows us to call 'continue' in the middle of the loop.
    context_before = deque(maxlen=options.options.trace_context_num_lines + 1)
    # Traces that still need "after" context.
    pending_traces = []
    def _AddTrace(trace_type, timestamp, module, message):
      # context_before also has the current line, so grab only :-1.
      trace = {'type': trace_type,
               'timestamp': timestamp,
               'module': module,
               'trace': msg,
               'context_before': list(context_before)[:-1],
               'context_after': []}
      if options.options.trace_context_num_lines == 0:
        trace_entries.append(trace)
      else:
        pending_traces.append(trace)

    def _CheckPendingTraces(line):
      for t in pending_traces:
        t['context_after'].append(line)
      while pending_traces and len(pending_traces[0]['context_after']) >= options.options.trace_context_num_lines:
        trace_entries.append(pending_traces.pop(0))

    while True:
      line = buf.readline()
      if not line:
        break
      line = line.rstrip('\n')
      # The deque automatically pops elements from the front when maxlen is reached.
      context_before.append(line)
      _CheckPendingTraces(line)

      parsed = logs_util.ParseLogLine(line)
      if not parsed:
        continue
      day, time, module, msg = parsed
      timestamp = logs_util.DayTimeStringsToUTCTimestamp(day, time)

      if options.options.process_traceback and re.search(kTracebackRE, line):
        _AddTrace('traceback', timestamp, module, msg)

      if module.startswith('user_op_manager:') or module.startswith('operation:'):
        # Found op status line.
        if msg.startswith('SUCCESS'):
          # Success message. eg: SUCCESS: user: xx, device: xx, op: xx, method: xx.yy in xxs
          parsed = logs_util.ParseSuccessMsg(msg)
          if not parsed:
            continue
          user, device, op, class_name, method_name = parsed
          method = '%s.%s' % (class_name, method_name)
          day_stats.ActiveAll(user)
          if method in ('Follower.UpdateOperation', 'UpdateFollowerOperation.Execute'):
            day_stats.ActiveView(user)
          elif method in ('Comment.PostOperation', 'PostCommentOperation.Execute'):
            day_stats.ActivePost(user)
          elif method in ('Episode.ShareExistingOperation', 'Episode.ShareNewOperation',
                          'ShareExistingOperation.Execute', 'ShareNewOperation.Execute'):
            day_stats.ActiveShare(user)
        elif msg.startswith('EXECUTE'):
          # Exec message. eg: EXECUTE: user: xx, device: xx, op: xx, method: xx.yy: <req>
          parsed = logs_util.ParseExecuteMsg(msg)
          if not parsed:
            continue
          user, device, op, class_name, method_name, request = parsed
          method = '%s.%s' % (class_name, method_name)
          if method in ('Device.UpdateOperation', 'User.RegisterOperation', 'RegisterUserOperation.Execute'):
            try:
              req_dict = eval(request)
              device_entries.append({'method': method, 'timestamp': timestamp, 'request': req_dict})
            except Exception as e:
              continue
        elif msg.startswith('ABORT'):
          if options.options.process_op_abort:
            # Abort message, save the entire line as well as context.
            _AddTrace('abort', timestamp, module, msg)
        # FAILURE status is already handled by Traceback processing.
      elif module.startswith('base:') and msg.startswith('/ping OK:'):
        # Ping message. Extract full request dict.
        req_str = logs_util.ParsePingMsg(msg)
        if not req_str:
          continue
        try:
          req_dict = json.loads(req_str)
          device_entries.append({'method': 'ping', 'timestamp': timestamp, 'request': req_dict})
        except Exception as e:
          continue
      elif module.startswith('ping:') and msg.startswith('ping OK:'):
        # Ping message in new format. Extract full request and response dicts.
        (req_str, resp_str) = logs_util.ParseNewPingMsg(msg)
        if not req_str or not resp_str:
          continue
        try:
          req_dict = json.loads(req_str)
          resp_dict = json.loads(resp_str)
          device_entries.append({'method': 'ping', 'timestamp': timestamp, 'request': req_dict, 'response': resp_dict})
        except Exception as e:
          continue


    # No more context. Flush the pending traces into the list.
    trace_entries.extend(pending_traces)
    buf.close()

  today = util.NowUTCToISO8601()
  # Group filenames by day.
  files_by_day = defaultdict(list)
  for filename in filenames:
    day = logs_paths.MergedLogPathToDate(filename)
    if not day:
      logging.error('filename cannot be parsed as processed log: %s' % filename)
      continue
    if options.options.compute_today or today != day:
      files_by_day[day].append(filename)

  # Sort the list of days. This is important both for --max_days_to_process, and to know the last
  # day for which we wrote the file.
  day_list = sorted(files_by_day.keys())
  if options.options.max_days_to_process is not None:
    day_list = day_list[:options.options.max_days_to_process]

  last_day_written = None
  for day in day_list:
    files = files_by_day[day]
    day_stats = logs_util.DayUserRequestStats(day)
    device_entries = []
    trace_entries = []
    for f in files:
      # Let exceptions surface.
      contents = yield gen.Task(merged_store.Get, f)
      logging.info('Processing %d bytes from %s' % (len(contents), f))
      _ProcessOneFile(contents, day_stats, device_entries, trace_entries)

    if not options.options.dry_run:
      # Write the json-ified stats.
      req_contents = json.dumps(day_stats.ToDotDict())
      req_file_path = 'processed_data/user_requests/%s' % day
      dev_contents = json.dumps(device_entries)
      dev_file_path = 'processed_data/device_details/%s' % day
      try:
        trace_contents = json.dumps(trace_entries)
      except Exception as e:
        trace_contents = None
      trace_file_path = 'processed_data/traces/%s' % day


      @gen.engine
      def _MaybePut(path, contents, callback):
        if contents:
          yield gen.Task(merged_store.Put, path, contents)
          logging.info('Wrote %d bytes to %s' % (len(contents), path))
        callback()


      yield [gen.Task(_MaybePut, req_file_path, req_contents),
             gen.Task(_MaybePut, dev_file_path, dev_contents),
             gen.Task(_MaybePut, trace_file_path, trace_contents)]

      last_day_written = day_stats.day

  callback(last_day_written)
  return


@gen.engine
def GetMergedLogsFileList(merged_store, logs_paths, marker, callback):
  """Fetch the list of file names from S3."""
  registry_file = logs_paths.ProcessedRegistryPath()
  def _WantFile(filename):
    if filename == registry_file:
      return False
    instance = logs_paths.MergedLogPathToInstance(filename)
    if instance is None:
      logging.error('Could not extract instance from file name %s' % filename)
      return False
    return not options.options.ec2_only or logs_util.IsEC2Instance(instance)

  base_path = logs_paths.MergedDirectory()
  marker = os.path.join(base_path, marker) if marker is not None else None
  file_list = yield gen.Task(store_utils.ListAllKeys, merged_store, prefix=base_path, marker=marker)
  files = [f for f in file_list if _WantFile(f)]
  files.sort()

  logging.info('found %d merged log files, analyzing %d' % (len(file_list), len(files)))
  callback(files)


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

    last_day = last_run['stats.last_day']
    # Set scan_start to start of previous run - 1d. The extra 1d is in case some logs were pushed to S3 late.
    # This really recomputes two days (the last day that was successfully processed and the one prior).
    start_time = util.ISO8601ToUTCTimestamp(last_day, hour=12) - constants.SECONDS_PER_DAY
    start_date = util.TimestampUTCToISO8601(start_time)
    logging.info('Last successful analyze_logs run (%s) scanned up to %s, setting analysis start date to %s' %
                 (time.asctime(time.localtime(last_run_start)), last_day, start_date))

  # Fetch list of merged logs.
  files = yield gen.Task(GetMergedLogsFileList, merged_store, logs_paths, start_date)
  last_day = yield gen.Task(ProcessFiles, merged_store, logs_paths, files)
  callback(last_day)
  return


@gen.engine
def _Start(callback):
  """Grab a lock on job:analyze_logs and call RunOnce. If we get a return value, write it to the job summary."""
  client = db_client.DBClient.Instance()
  job = Job(client, 'analyze_logs')

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
