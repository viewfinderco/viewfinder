# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Utilities for base class of servers and command-line tools.

 - InitAndRun() - initializes secrets, invokes a run callback.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import os
import signal
import sys

from functools import partial
from tornado import gen, httpclient, options, stack_context, ioloop
from viewfinder.backend.base import ami_metadata, process_util, secrets
from viewfinder.backend.base.environ import ServerEnvironment
from viewfinder.backend.db import db_client, vf_schema
from viewfinder.backend.storage import object_store, server_log

options.define('blocking_log_threshold', default=None, type=float,
               help='Log a warning (with stack trace) if the IOLoop is blocked for this many seconds')


@gen.coroutine
def _Init(init_db=True, server_logging=True):
  """Completes Viewfinder initialization, such as secrets, DB client, AMI metadata, and the
  object store.
  """
  # Configure the default http client to use pycurl.
  httpclient.AsyncHTTPClient.configure('tornado.curl_httpclient.CurlAsyncHTTPClient', max_clients=100)

  # Retrieve AMI metadata before initializing secrets. Don't try to get metadata on devbox.
  if options.options.devbox:
    metadata = ami_metadata.Metadata()
  else:
    metadata = yield gen.Task(ami_metadata.Metadata)

  if metadata is None:
    raise Exception('failed to fetch AWS instance metadata; if running on dev box, '
                    'use the --devbox option')

  ami_metadata.SetAMIMetadata(metadata)
  logging.info('AMI metadata initialized')

  # Initialize server environment.
  ServerEnvironment.InitServerEnvironment()
  logging.info('server environment initialized')

  # Initialize secrets.
  yield gen.Task(secrets.InitSecrets, can_prompt=sys.stderr.isatty())
  logging.info('secrets initialized')

  # Initialize database.
  if init_db:
    yield gen.Task(db_client.InitDB, vf_schema.SCHEMA)
    logging.info('DB client initialized')

  # Initialize object store.
  object_store.InitObjectStore(temporary=False)
  logging.info('object store initialized')

  # Initialize the server log now that the object store is initialized.
  if server_logging:
    server_log.InitServerLog()

  logging.info('main.py initialization complete')


def InitAndRun(run_callback, shutdown_callback=None, init_db=True, server_logging=True):
  """Initializes and configures the process and then the Viewfinder server.

  If 'init_db' is False, skip initializing the database client. If 'server_logging' is False,
  do not write logs to S3 and do not override the logging level to INFO.

  Creates an instance of IOLoop, and adds it to the stack context and starts it. When
  initialization is complete, invokes 'run_callback'. When that has completed, invokes
  "shutdown_callback".

  Note that this function runs *synchronously*, and will not return until both "run_callback"
  and "shutdown_callback" have been executed.
  """
  options.parse_command_line()

  # Set the global process name from command line. Do not override if already set.
  proc_name = os.path.basename(sys.argv[0])
  if proc_name and process_util.GetProcessName() is None:
    process_util.SetProcessName(proc_name)

  # Create IOLoop and add it to the context.
  # Use IOLoop.Instance() to avoid problems with certain third-party libraries.
  io_loop = ioloop.IOLoop.instance()
  if options.options.blocking_log_threshold is not None:
    io_loop.set_blocking_log_threshold(options.options.blocking_log_threshold)

  # Setup signal handlers to initiate shutdown and stop the IOLoop. 
  def _OnSignal(signum, frame):
    logging.info('process stopped with signal %d' % signum)
    io_loop.stop()

  signal.signal(signal.SIGHUP, _OnSignal)
  signal.signal(signal.SIGINT, _OnSignal)
  signal.signal(signal.SIGQUIT, _OnSignal)
  signal.signal(signal.SIGTERM, _OnSignal)

  @gen.coroutine
  def _InvokeCallback(wrapped_callback):
    """Wraps "run_callback" in function that returns the Future that IOLoop.run_sync requires."""
    yield gen.Task(wrapped_callback)

  # If this is true at shutdown time, exit with error code.
  shutdown_by_exception = False

  try:
    # Initialize.
    if server_logging:
      logging.getLogger().setLevel(logging.INFO)
      logging.getLogger().handlers[0].setLevel(logging.INFO)

    io_loop.run_sync(partial(_Init, init_db=init_db, server_logging=server_logging))

    # Run.
    io_loop.run_sync(partial(_InvokeCallback, run_callback))

    # Shutdown.
    if shutdown_callback is not None:
      io_loop.run_sync(partial(_InvokeCallback, shutdown_callback))
  except Exception as ex:
    # TimeoutError is raised by run_sync if signal handler stopped the ioloop.
    if not isinstance(ex, ioloop.TimeoutError):
      logging.exception('unhandled exception in %s' % sys.argv[0])
      shutdown_by_exception = True

  db_client.ShutdownDB()
  io_loop.run_sync(server_log.FinishServerLog)

  # Exit with error code if exception caused shutdown.
  if shutdown_by_exception:
    sys.exit(1)
