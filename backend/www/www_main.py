#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Main utility to setup everything necessary to run a viewfinder server
or a tool which acts as if it were a full-fledged server.

Set up:
  - Email manager
  - SMS manager
  - Op manager
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

from functools import partial
from tornado.httpclient import AsyncHTTPClient
from tornado import gen, options
from viewfinder.backend.base import main
from viewfinder.backend.base.environ import ServerEnvironment
from viewfinder.backend.db import db_client
from viewfinder.backend.db.device import Device
from viewfinder.backend.op.op_manager import OpManager
from viewfinder.backend.op.operation_map import DB_OPERATION_MAP
from viewfinder.backend.services.apns import APNS
from viewfinder.backend.services.email_mgr import EmailManager, SendGridEmailManager, LoggingEmailManager
from viewfinder.backend.services.itunes_store import ITunesStoreClient
from viewfinder.backend.services.sms_mgr import LoggingSMSManager, SMSManager, TwilioSMSManager
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.www.system_users import LoadSystemUsers


options.define('local_services', default=False, type=bool,
               help='If true, then do not use external services for email and texting. ' +
                    'Instead, log emails and texts to the console.')


@gen.coroutine
def _StartWWW(run_callback, scan_ops):
  """Starts services necessary for operating in the Viewfinder WWW server environment. Invokes
  'run_callback' asynchronously.
  """
  client = db_client.DBClient.Instance()

  # Log emails and texts to the console in local mode.
  if options.options.local_services:
    EmailManager.SetInstance(LoggingEmailManager())
    SMSManager.SetInstance(LoggingSMSManager())
  else:
    EmailManager.SetInstance(SendGridEmailManager())
    SMSManager.SetInstance(TwilioSMSManager())

  # Set URL for local fileobjstores.
  if options.options.fileobjstore:
    # Import server for ssl and port options.
    from viewfinder.backend.www import server
    url_fmt_string = '%s://%s:%d/fileobjstore/' % ('https' if options.options.ssl else 'http',
                                                   ServerEnvironment.GetHost(), options.options.port)
    url_fmt_string += '%s/%%s'
    for store_name in (ObjectStore.PHOTO, ObjectStore.USER_LOG, ObjectStore.USER_ZIPS):
      ObjectStore.GetInstance(store_name).SetUrlFmtString(url_fmt_string % store_name)

  OpManager.SetInstance(OpManager(op_map=DB_OPERATION_MAP, client=client, scan_ops=scan_ops))

  apns_feedback_handler = Device.FeedbackHandler(client)
  APNS.SetInstance('dev', APNS(environment='dev', feedback_handler=apns_feedback_handler))
  APNS.SetInstance('ent', APNS(environment='ent', feedback_handler=apns_feedback_handler))
  APNS.SetInstance('prod', APNS(environment='prod', feedback_handler=apns_feedback_handler))
  http_client = AsyncHTTPClient()
  ITunesStoreClient.SetInstance('dev', ITunesStoreClient(environment='dev', http_client=http_client))
  ITunesStoreClient.SetInstance('prod', ITunesStoreClient(environment='prod', http_client=http_client))

  # Ensure that system users are loaded.
  yield LoadSystemUsers(client)

  yield gen.Task(run_callback)


def InitAndRun(run_callback, shutdown_callback=None, scan_ops=False, server_logging=True):
  """Runs the main initialization routine, with the provided run and shutdown callbacks wrapped
  by the WWW-specific functionality provided by '_StartWWW' and '_ShutdownWWW'.
  """
  main.InitAndRun(run_callback=partial(_StartWWW, run_callback, scan_ops),
                  shutdown_callback=shutdown_callback,
                  server_logging=server_logging)
