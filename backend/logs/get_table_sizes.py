# Copyright 2013 Viewfinder Inc. All Rights Reserved
"""Fetch dynamodb table sizes and counts and store in logs.daily metric.

Run with:
$ python -m viewfinder.backend.logs.get_table_sizes --dry_run=False

Options:
- dry_run: default=True: run in dry-run mode (don't write to dynamodb)
- require_lock: default=True: grab the job:itunes_trends lock for the duration of the job.
"""

import json
import logging
import sys
import time

from tornado import gen, options
from viewfinder.backend.base import main, util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import db_client, metric, vf_schema
from viewfinder.backend.db.job import Job
from viewfinder.backend.logs import logs_util

options.define('dry_run', default=True, help='Print output only, do not write to metrics table.')
options.define('require_lock', type=bool, default=True,
               help='attempt to grab the job:itunes_trends lock before running. Exit if acquire fails.')


@gen.engine
def RunOnce(client, callback):
  today = util.NowUTCToISO8601()
  logging.info('getting table sizes for %s' % today)

  results = yield gen.Task(vf_schema.SCHEMA.VerifyOrCreate, client, verify_only=True)
  stats = DotDict()
  for r in sorted(results):
    name = r[0]
    props = r[1]
    stats['db.table.count.%s' % name] = props.count
    stats['db.table.size.%s' % name] = props.size_bytes

  # Replace the entire 'db.table' prefix in previous metrics.
  hms = logs_util.kDailyMetricsTimeByLogType['dynamodb_stats']
  yield gen.Task(logs_util.UpdateMetrics, client, {today: stats}, prefix_to_erase='db.table',
                 dry_run=options.options.dry_run, hms_tuple=hms)
  callback()


@gen.engine
def _Start(callback):
  """Grab a lock on job:table_sizes and call RunOnce. We never write a job summary."""
  client = db_client.DBClient.Instance()
  job = Job(client, 'table_sizes')

  if options.options.require_lock:
    got_lock = yield gen.Task(job.AcquireLock)
    if got_lock == False:
      logging.warning('Failed to acquire job lock: exiting.')
      callback()
      return

  try:
    yield gen.Task(RunOnce, client)
  finally:
    yield gen.Task(job.ReleaseLock)

  callback()


if __name__ == '__main__':
  sys.exit(main.InitAndRun(_Start))
