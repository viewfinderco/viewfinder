# Copyright 2013 Viewfinder Inc. All Rights Reserved
"""Crawl dynamodb tables and compute various metrics.

Run with:
$ python -m viewfinder.backend.logs.analyze_dynamodb --dry_run=False

Options:
- dry_run: default=True: run in dry-run mode (don't write to dynamodb)
- require_lock: default=True: grab the job:analyze_dynamodb lock for the duration of the job.
- throttling_factor: default=4: set allowed dynamodb capacity to "total / factor"
- force_recompute: default=False: recompute today's stats even if we already have
"""

import json
import logging
import sys
import time
import traceback

from collections import Counter
from tornado import gen, options
from viewfinder.backend.base import main, util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import db_client, metric, vf_schema
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.job import Job
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.user import User
from viewfinder.backend.logs import logs_util

options.define('dry_run', default=True, help='Print output only, do not write to metrics table.')
options.define('require_lock', type=bool, default=True,
               help='attempt to grab the job:analyze_dynamodb lock before running. Exit if acquire fails.')
options.define('throttling_factor', default=4, help='Dynamodb throttling factor')
options.define('force_recompute', default=False, help='Recompute even if we have already run today')
options.define('limit_users', default=-1, help='Limit number of users to scan. --dry_run only')


@gen.engine
def CountByIdentity(client, user_id, callback):
  query_str = 'identity.user_id=%d' % user_id
  # We only care about the identity type (the key).
  result = yield gen.Task(Identity.IndexQuery, client, query_str, col_names=['key'])
  if len(result) == 0:
    callback(('NONE', 'NONE'))
    return

  type_count = Counter()
  for r in result:
    identity_type, value = Identity.SplitKey(r.key)
    type_count[identity_type[0]] += 1
  count_by_type = ''
  types = ''
  for k in sorted(type_count.keys()):
    count_by_type += '%s%d' % (k, type_count[k])
    types += k
  callback((count_by_type, types))

@gen.engine
def ProcessUserDevices(client, user_id, callback):
  devices = []
  start_key = None
  while True:
    dev_list = yield gen.Task(Device.RangeQuery, client, user_id, None, None, None, excl_start_key=start_key)
    if len(dev_list) == 0:
      break
    devices.extend(dev_list)
    start_key = dev_list[-1].GetKey()

  # The highest app version across all devices for this user. This may not be a device with a push token.
  highest_version = None
  has_notification = 0

  for d in devices:
    if d.push_token is not None and d.alert_user_id == user_id:
      has_notification += 1
    if d.version is not None and (highest_version is None or d.version.split('.') > highest_version.split('.')):
      highest_version = d.version

  callback((highest_version, has_notification))

@gen.engine
def ProcessTables(client, callback):
  user_count = Counter()
  locale_count = Counter()

  identity_count = Counter()
  identity_types = Counter()

  device_highest_version = Counter()
  device_has_notification = Counter()
  device_notification_count = Counter()

  settings_email_alerts = Counter()
  settings_sms_alerts = Counter()
  settings_push_alerts = Counter()
  settings_storage = Counter()
  settings_marketing = Counter()

  start_key = None
  limit = options.options.limit_users if options.options.limit_users > 0 else None
  while True:
    users, start_key = yield gen.Task(User.Scan, client, None, limit=limit, excl_start_key=start_key)

    for user in users:
      if user.IsTerminated():
        # This includes terminated prospective users (pretty rare).
        user_count['terminated'] += 1
        continue
      elif not user.IsRegistered():
        user_count['prospective'] += 1
        continue

      # From here on out, only registered users are part of the stats.
      user_count['registered'] += 1

      # User locale.
      locale_count[user.locale or 'NONE'] += 1

      # Count of identities by type.
      counts, types = yield gen.Task(CountByIdentity, client, user.user_id)
      identity_count[counts] += 1
      identity_types[types] += 1

      # Versions and notification status for user's devices.
      highest_version, notification_count = yield gen.Task(ProcessUserDevices, client, user.user_id)
      device_highest_version[highest_version.replace('.', '_') if highest_version else 'None'] += 1
      device_notification_count[str(notification_count)] += 1
      if notification_count > 0:
        device_has_notification['true'] += 1
      else:
        device_has_notification['false'] += 1

      # Account settings.
      settings = yield gen.Task(AccountSettings.QueryByUser, client, user.user_id, None)
      settings_email_alerts[settings.email_alerts or 'NA'] += 1
      settings_sms_alerts[settings.sms_alerts or 'NA'] += 1
      settings_push_alerts[settings.push_alerts or 'NA'] += 1
      settings_storage[','.join(settings.storage_options) if settings.storage_options else 'NA'] += 1
      settings_marketing[settings.marketing or 'NA'] += 1

    if limit is not None:
      limit -= len(users)
      if limit <= 0:
        break


    if start_key is None:
      break

  day_stats = DotDict()
  day_stats['dynamodb.user.state'] = user_count
  day_stats['dynamodb.user.locale'] = locale_count
  day_stats['dynamodb.user.identities'] = identity_count
  day_stats['dynamodb.user.identity_types'] = identity_types
  day_stats['dynamodb.user.device_highest_version'] = device_highest_version
  day_stats['dynamodb.user.device_has_notification'] = device_has_notification
  day_stats['dynamodb.user.devices_with_notification'] = device_notification_count
  day_stats['dynamodb.user.settings_email_alerts'] = settings_email_alerts
  day_stats['dynamodb.user.settings_sms_alerts'] = settings_sms_alerts
  day_stats['dynamodb.user.settings_push_alerts'] = settings_push_alerts
  day_stats['dynamodb.user.settings_storage'] = settings_storage
  day_stats['dynamodb.user.settings_marketing'] = settings_marketing

  callback(day_stats)


@gen.engine
def RunOnce(client, job, callback):
  """Find last successful run. If there is one from today, abort. Otherwise, run everything."""
  today = util.NowUTCToISO8601()

  last_run = yield gen.Task(job.FindLastSuccess, with_payload_key='stats.last_day')
  if last_run is not None and last_run['stats.last_day'] == today and not options.options.force_recompute:
    logging.info('Already ran successfully today: skipping. Specify --force_recompute to recompute.')
    callback(None)
    return

  # Analyze.
  day_stats = yield gen.Task(ProcessTables, client)
  assert day_stats is not None

  # Write per-day stats to dynamodb.
  hms = logs_util.kDailyMetricsTimeByLogType['dynamodb_user']
  yield gen.Task(logs_util.UpdateMetrics, client, {today: day_stats}, dry_run=options.options.dry_run, hms_tuple=hms,
                 prefix_to_erase='dynamodb.user')
  callback(today)


@gen.engine
def _Start(callback):
  """Grab a lock on job:analyze_dynamodb and call RunOnce. If we get a return value, write it to the job summary."""
  # Setup throttling.
  for table in vf_schema.SCHEMA.GetTables():
    table.read_units = max(1, table.read_units // options.options.throttling_factor)
    table.write_units = max(1, table.write_units // options.options.throttling_factor)

  client = db_client.DBClient.Instance()
  job = Job(client, 'analyze_dynamodb')

  if not options.options.dry_run and options.options.limit_users > 0:
    logging.error('--limit_users specified, but not running in dry-run mode. Aborting')
    callback()
    return

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
