# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Merge user analytics logs into per-day/per-user files.

For each user, we look at files not yet processed (there is a per-user registry in serverdata/).
For each individual analytic entry, we determine which day to write it to based on the entry timestamp and wrap
it inside a small dict containing device_id and version (from the raw filename).

Usage:
# Process analytics logs for all users
python -m viewfinder.backend.logs.get_client_logs

# Search for new logs starting on December 1st 2012 (S3 ListKeys prefix).
python -m viewfinder.backend.logs.get_client_logs --start_date=2012-12-01

Other flags:
-dry_run: default=True: do everything, but do not write processed logs files to S3 or update registry.
-require_lock: default=True: hold the job:client_logs lock during processing.
-user: default=None: process a single user. If None, process all users.
-start_user: default=None: start scanning from this user id (lexicographically, not numerically)

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import json
import logging
import os
import sys

from tornado import gen, options
from viewfinder.backend.base import main, retry, util
from viewfinder.backend.db import db_client
from viewfinder.backend.db.job import Job
from viewfinder.backend.logs import log_merger, logs_util
from viewfinder.backend.storage import store_utils
from viewfinder.backend.storage.object_store import ObjectStore

options.define('start_date', default=None, help='Start date (filename start key)')
options.define('dry_run', default=True, help='Do not write processed logs to S3 or update registry')
options.define('require_lock', type=bool, default=True,
               help='attempt to grab the job:client_logs lock before running. Exit if acquire fails.')
options.define('user', default=None, help='Process a single user')
options.define('start_user', default=None,
               help='start scanning from this user id (lexicographically, not numerically)')
options.define('max_users', default=None, type=int,
               help='maximum number of users to examine')
options.define('process_analytics', default=True, type=bool,
               help='process user analytics files')
options.define('process_crashes', default=True, type=bool,
               help='process user crash files')

# Retry policy for uploading files to S3 (merge logs and registry).
kS3UploadRetryPolicy = retry.RetryPolicy(max_tries=5, timeout=300,
                                         min_delay=1, max_delay=30,
                                         check_exception=retry.RetryPolicy.AlwaysRetryOnException)

@gen.engine
def HandleOneUser(client_store, user_id, callback):
  """Process client logs for a single user."""
  logs_paths = logs_util.UserAnalyticsLogsPaths(user_id)

  # List all files for this user.
  base_path = logs_paths.RawDirectory()
  marker = os.path.join(base_path, options.options.start_date) if options.options.start_date is not None else None
  files = yield gen.Task(store_utils.ListAllKeys, client_store, prefix=base_path, marker=marker)
  analytics_files = []
  crash_files = []
  for f in sorted(files):
    if f.endswith('.analytics.gz'):
      analytics_files.append(f)
    elif f.endswith('.crash') or f.endswith('.crash.gz'):
      crash_files.append(f)

  if analytics_files and options.options.process_analytics:
    yield gen.Task(HandleAnalytics, client_store, user_id, logs_paths, analytics_files)
  if crash_files and options.options.process_crashes:
    yield gen.Task(HandleCrashes, client_store, user_id, crash_files)

  callback()

@gen.engine
def HandleCrashes(client_store, user_id, raw_files, callback):
  logs_paths = logs_util.UserCrashLogsPaths(user_id)
  raw_store = ObjectStore.GetInstance(logs_paths.SOURCE_LOGS_BUCKET)
  merged_store = ObjectStore.GetInstance(logs_paths.MERGED_LOGS_BUCKET)

  # List all processed
  base_path = logs_paths.MergedDirectory()
  existing_files = yield gen.Task(store_utils.ListAllKeys, merged_store, prefix=base_path, marker=None)
  done_files = set()
  for e in existing_files:
    parsed = logs_paths.ParseMergedLogPath(e)
    if parsed:
      done_files.add(parsed)

  to_copy = []
  for f in raw_files:
    parsed = logs_paths.ParseRawLogPath(f)
    if not parsed or parsed in done_files:
      continue
    to_copy.append(parsed)

  if to_copy:
    logging.info('User %s: %d crash files' % (user_id, len(to_copy)))

  if options.options.dry_run:
    callback()
    return

  @gen.engine
  def _CopyFile(source_parsed, callback):
    user, date, fname = source_parsed
    src_file = os.path.join(logs_paths.RawDirectory(), date, fname)
    dst_file = os.path.join(logs_paths.MergedDirectory(), date, fname)
    contents = yield gen.Task(raw_store.Get, src_file)
    yield gen.Task(merged_store.Put, dst_file, contents)
    callback()

  yield [gen.Task(_CopyFile, st) for st in to_copy]
  callback()

@gen.engine
def HandleAnalytics(client_store, user_id, logs_paths, raw_files, callback):
  s3_base = logs_paths.MergedDirectory()
  raw_store = ObjectStore.GetInstance(logs_paths.SOURCE_LOGS_BUCKET)
  merged_store = ObjectStore.GetInstance(logs_paths.MERGED_LOGS_BUCKET)

  # Fetch user's repository of processed files.
  processed_files = yield gen.Task(logs_util.GetRegistry, merged_store, logs_paths.ProcessedRegistryPath())
  if processed_files is None:
    # None means: registry does not exist. All other errors throw exceptions.
    processed_files = []

  # Compute list of raw files to process (and sort by filename -> sort by date).
  files_set = set(raw_files)
  processed_set = set(processed_files)
  missing_files = list(files_set.difference(processed_set))
  missing_files.sort()

  if len(missing_files) == 0:
    callback()
    return

  # Dict of 'day' to LocalLogMerge for that day and user.
  day_mergers = {}

  finished_files = []

  for i in missing_files:
    res = logs_paths.ParseRawLogPath(i)
    assert res is not None, 'Problem parsing file %s' % i
    assert res[0] == 'analytics', 'Problem parsing file %s' % i
    assert res[1] == user_id, 'Problem parsing file %s' % i
    device_id = res[2]
    version = res[3]

    # We wrap the entire file processing into a single try statement. Any problems with is and we discard all
    # entries in the log mergers and don't add it to the list of processed files.
    try:
      # GetFileContents automatically gunzips files based on extension.
      contents = yield gen.Task(store_utils.GetFileContents, client_store, i)
      # Clients don't know when the file is closed so will not write a terminating bracket. Make it conditional just
      # in case they do one day.
      if contents.startswith('[') and not contents.endswith(']'):
        contents += ']'
      parsed = json.loads(contents)
      for p in parsed:
        if not 'timestamp':
          logging.warning('Analytics entry without timestamp: %r' % p)
          continue
        day = util.TimestampUTCToISO8601(p['timestamp'])
        container = {'device_id': device_id, 'payload': p}
        # Some (old?) user logs don't have a version embedded in the filename.
        if version is not None:
          container['version'] = version

        merger = day_mergers.get(day, None)
        if merger is None:
          merger = log_merger.LocalLogMerge(merged_store, [day, user_id], s3_base)
          yield gen.Task(merger.FetchExistingFromS3)
          day_mergers[day] = merger

        # Each line is individually json encoded, but we do not terminate the file as we don't know when we'll
        # be adding more data to it.
        merger.Append(json.dumps(container))
    except Exception as e:
      # We don't currently surface the error and interrupt the entire job as we want to find any badly-formatter files.
      # TODO(marc): this won't be very visible, we should create a list of bad files we can examine later.
      logging.warning('Problem processing %s: %r' % (i, e))
      for merger in day_mergers.values():
        merger.DiscardBuffer()
      continue

    # We put log flushing after the try statement. We do want to catch this.
    for merger in day_mergers.values():
      merger.FlushBuffer()
    finished_files.append(i)


  # Close all mergers for this user
  tasks = []
  for day, merger in day_mergers.iteritems():
    merger.Close()
    tasks.append(gen.Task(merger.Upload))

  if not options.options.dry_run:
    try:
      yield tasks
    except Exception as e:
      # Errors in the Put are unrecoverable. We can't upload the registry after a failed merged log upload.
      # TODO(marc): provide a way to mark a given day's merged logs as bad and force recompute.
      logging.error('Error uploading file(s) to S3 for user %s: %r' % (user_id, e))

  # Commit the registry file.
  processed_files.extend(finished_files)
  processed_files.sort()
  if not options.options.dry_run:
    yield gen.Task(retry.CallWithRetryAsync, kS3UploadRetryPolicy,
                   logs_util.WriteRegistry, merged_store, logs_paths.ProcessedRegistryPath(), processed_files)

  # Now cleanup the merger objects.
  for merger in day_mergers.values():
    merger.Cleanup()

  callback()

@gen.engine
def RunOnce(callback):
  """Get list of files and call processing function."""
  dry_run = options.options.dry_run
  client_store = ObjectStore.GetInstance(logs_util.UserAnalyticsLogsPaths.SOURCE_LOGS_BUCKET)

  if options.options.user:
    users = [options.options.user]
  else:
    users = yield gen.Task(logs_util.ListClientLogUsers, client_store)

  examined = 0
  for u in users:
    # Running all users in parallel can get us to exceed the open FD limit.
    if options.options.start_user is not None and u < options.options.start_user:
      continue
    if options.options.max_users is not None and examined > options.options.max_users:
      break
    examined += 1
    yield gen.Task(HandleOneUser, client_store, u)

  if dry_run:
    logging.warning('dry_run=True: will not upload processed logs files or update registry')

  callback()

@gen.engine
def _Start(callback):
  """Grab the job lock and call RunOnce if acquired. We do not write a job summary as we currently do not use it."""
  client = db_client.DBClient.Instance()
  job = Job(client, 'client_logs')

  if options.options.require_lock:
    got_lock = yield gen.Task(job.AcquireLock)
    if got_lock == False:
      logging.warning('Failed to acquire job lock: exiting.')
      callback()
      return

  try:
    yield gen.Task(RunOnce)
  finally:
    yield gen.Task(job.ReleaseLock)

  callback()


if __name__ == '__main__':
  sys.exit(main.InitAndRun(_Start))
