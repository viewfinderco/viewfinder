#!/usr/bin/env python
"""Merges two user accounts.

Invokes the merge_accounts service API in order to merge the assets from a source user account
into a target user account.

It relies on access to the cookie-signing secret to create cookies for any user.

Sample usage:
  python -m viewfinder.backend.www.tools.merge_tool \
    --devbox --target_user_id=1 --source_user_id=2
"""

import json
import time

from tornado import gen, options
from tornado.ioloop import IOLoop
from tornado.httpclient import AsyncHTTPClient
from tornado.options import define, options, parse_command_line
from tornado.web import create_signed_value
from viewfinder.backend.base.environ import ServerEnvironment
from viewfinder.backend.base.message import MAX_SUPPORTED_MESSAGE_VERSION
from viewfinder.backend.base.secrets import InitSecrets, GetSecret
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.db_client import DBClient, InitDB
from viewfinder.backend.db.dynamodb_client import DynamoDBClient
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.user import User
from viewfinder.backend.www.server import SERVER_VERSION

# Do not define options for tests.
if __name__ == '__main__':
  define('target_user_id', type=int, help='id of user receiving merge assets')
  define('source_user_id', type=int, help='id of user giving merge assets')


@gen.coroutine
def Merge(client, target_user_id, source_user_id, base_url, no_prompt=False):
  # Get source and target user objects.
  source_user = yield gen.Task(User.Query, client, source_user_id, None)
  target_user = yield gen.Task(User.Query, client, target_user_id, None)

  print '--------- MERGE ACCOUNTS ----------'
  print '  Source User (will be terminated): %s (user %d)' % (source_user.email, source_user_id)
  print '  Target User (gets the assets)   : %s (user %d)' % (target_user.email, target_user_id)
  print ''

  if not no_prompt:
    answer = raw_input('Are you SURE you want to do this? Type \'yes\' to confirm: ')
    if answer.lower() != 'yes':
      return

  # Construct cookies for source and target users.
  cookie_secret = GetSecret('cookie_secret')
  source_cookie = create_signed_value(cookie_secret, 'user', json.dumps(dict(user_id=source_user_id,
                                                                             device_id=source_user.webapp_dev_id,
                                                                             server_version=SERVER_VERSION,
                                                                             confirm_time=time.time())))
  target_cookie = create_signed_value(cookie_secret, 'user', json.dumps(dict(user_id=target_user_id,
                                                                             device_id=target_user.webapp_dev_id,
                                                                             server_version=SERVER_VERSION)))

  timestamp = time.time()
  http_headers = {
    'Cookie': '_xsrf=fake_xsrf; user=%s' % target_cookie,
    'X-XSRFToken': 'fake_xsrf',
    'Content-Type': 'application/json',
    }

  # Allocate unique asset ids for the operation.
  http_client = AsyncHTTPClient()
  body = {'headers': {'version': MAX_SUPPORTED_MESSAGE_VERSION},
          'asset_types': ['o', 'a']}
  response = yield gen.Task(http_client.fetch,
                            '%s/service/allocate_ids' % base_url,
                            method='POST',
                            body=json.dumps(body),
                            headers=http_headers,
                            validate_cert=options.validate_cert)
  operation_id, activity_id = json.loads(response.body)['asset_ids']

  body = {'headers': {'version': MAX_SUPPORTED_MESSAGE_VERSION,
                      'op_id': operation_id,
                      'op_timestamp': timestamp,
                      'synchronous': True},
          'activity': {'activity_id': activity_id,
                       'timestamp': timestamp},
          'source_user_cookie': source_cookie}
  yield gen.Task(http_client.fetch,
                 '%s/service/merge_accounts' % base_url,
                 method='POST',
                 body=json.dumps(body),
                 headers=http_headers,
                 validate_cert=options.validate_cert)


if __name__ == '__main__':
  @gen.coroutine
  def main():
    parse_command_line()
    assert options.target_user_id, '--target_user_id must be set'
    assert options.source_user_id, '--source_user_id must be set'

    ServerEnvironment.InitServerEnvironment()
    yield gen.Task(InitSecrets)
    yield gen.Task(InitDB, vf_schema.SCHEMA, verify_or_create=False)
    yield Merge(DBClient.Instance(),
                target_user_id=options.target_user_id,
                source_user_id=options.source_user_id,
                base_url='https://%s' % ServerEnvironment.GetHost())


  IOLoop.instance().run_sync(main)
