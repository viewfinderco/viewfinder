# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Utility to directly invoke JSON service RPCs.

Usage:

% python backend/www/tools/run_service.py --method=<method> \
      --user_id=<user_id> [--device_id=<device_id>]

The body of the request should be specified via STDIN.

This script imports the service code and runs it directly, so it takes
all the same command-line flags that a server would.  See also
call_http_service.py, which can make a call to a running server over HTTP.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import json
import logging
import pprint
import sys

from functools import partial
from tornado import options
from tornado.web import stack_context
from viewfinder.backend.base import util
from viewfinder.backend.base.message import MAX_SUPPORTED_MESSAGE_VERSION
from viewfinder.backend.db.db_client import DBClient
from viewfinder.backend.db.user import User
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.www import base, www_main
from viewfinder.backend.www.service import ServiceHandler

options.define('method', default=None, help='service method to run')
options.define('user_id', default=None, type=int, help='user id of the account running service method')
options.define('device_id', default=None, type=int, help='device id of the account running service method')


def _RunService(callback):
  """Invokes user account merge utility."""
  assert options.options.method, 'must specify a service method (--method)'
  assert options.options.user_id, 'must specify a user id (--user_id)'

  # Read request body from standard in.
  if sys.stdin.isatty():
    print 'Enter JSON-encoded service request:'
  request_body = sys.stdin.read()

  # If version was not specified, add it now (use max supported version).
  request_dict = json.loads(request_body)
  if not request_dict.has_key('headers'):
    request_dict['headers'] = dict()

  if not request_dict['headers'].has_key('version'):
    request_dict['headers']['version'] = MAX_SUPPORTED_MESSAGE_VERSION

  client = DBClient.Instance()
  obj_store = ObjectStore.GetInstance(ObjectStore.PHOTO)

  def _OnService(response_dict):
    logging.info('result: %s' % util.ToCanonicalJSON(response_dict, indent=2))
    callback()

  def _OnQueryUser(user):
    context = base.ViewfinderContext(None)
    context.user = user
    context.device_id = user.webapp_dev_id if options.options.device_id is None else options.options.device_id

    with stack_context.StackContext(context):
      ServiceHandler.InvokeService(client, obj_store, options.options.method,
                                   context.user.user_id, context.device_id,
                                   request_dict, callback=_OnService)

  User.Query(client, options.options.user_id, None, _OnQueryUser)


if __name__ == '__main__':
  www_main.InitAndRun(_RunService)
