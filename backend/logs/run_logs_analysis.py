# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Run logs analysis jobs that depend on each other while holding the job:logs_analysis lock.

We can't import those modules as too many global variables would conflict (flags, process name etc...).

Sequentially run jobs that depend on each other. Sets of jobs are:
Server logs pipeline:
 - viewfinder.backend.logs.get_server_logs
 - viewfinder.backend.logs.analyze_merged_logs
 - viewfinder.backend.logs.server_log_metrics
Client analytics logs pipeline:
 - viewfinder.backend.logs.get_client_logs
 - viewfinder.backend.logs.analyze_analytics_logs

Each job set grabs its own lock to prevent the same job set from being run on another instance.

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import logging
import sys
import time
import traceback

from tornado import gen, ioloop, options, process
from viewfinder.backend.base import main
from viewfinder.backend.db import db_client
from viewfinder.backend.db.job import Job

# The jobs are run serially and in the order listed for each key.
# Dictionary of 'job set name' to list of jobs. Each job consists of a tuple ('job name', list of args).
kJobSets = {
  'server_logs_analysis': [
    ('get_server_logs', ['python', '-m', 'viewfinder.backend.logs.get_server_logs',
                         '--dry_run=False', '--require_lock=True' ]),
    ('analyze_merged_logs', ['python', '-m', 'viewfinder.backend.logs.analyze_merged_logs',
                             '--dry_run=False', '--require_lock=True',
                             '--smart_scan=True', '--hours_between_runs=6']),
    ('server_log_metrics', ['python', '-m', 'viewfinder.backend.logs.server_log_metrics',
                            '--dry_run=False', '--require_lock=True',
                            '--smart_scan=True', '--hours_between_runs=6']),
                          ],
  'client_logs_analysis': [
    ('get_client_logs', ['python', '-m', 'viewfinder.backend.logs.get_client_logs',
                         '--dry_run=False', '--require_lock=True' ]),
    ('analyze_analytics_logs', ['python', '-m', 'viewfinder.backend.logs.analyze_analytics_logs',
                                '--dry_run=False', '--require_lock=True',
                                '--smart_scan=True', '--hours_between_runs=6']),
                          ]
}

options.define('job_set', default='server_logs_analysis', help='Job set to run. One of %r.' % kJobSets.keys())

@gen.engine
def _Run(callback):
  """Grab the lock and run all commands an subprocesess."""
  job_set = options.options.job_set
  assert job_set in kJobSets.keys(), '--job_set must be one of %r' % kJobSets.keys()
  jobs = kJobSets[job_set]

  client = db_client.DBClient.Instance()
  job = Job(client, job_set)
  got_lock = yield gen.Task(job.AcquireLock)
  if not got_lock:
    logging.warning('Failed to acquire job lock: exiting.')
    callback()
    return

  # Wrap entire call inside a try to make sure we always release the lock.
  try:
    for title, args in jobs:
      logging.info('[%s] running %s' % (title, ' '.join(args)))

      # Run the task and wait for the termination callback.
      proc = process.Subprocess(args, io_loop=ioloop.IOLoop.instance())
      code = yield gen.Task(proc.set_exit_callback)

      logging.info('[%s] finished with code: %r' % (title, code))

  except:
    logging.error(traceback.format_exc())
  finally:
    yield gen.Task(job.ReleaseLock)

  callback()

if __name__ == '__main__':
  sys.exit(main.InitAndRun(_Run))
