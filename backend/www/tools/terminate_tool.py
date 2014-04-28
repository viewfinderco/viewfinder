#!/usr/bin/env python
"""Terminates a user account.

Invokes the terminate_account service API in order to terminate a target user account.

It relies on access to the cookie-signing secret to create cookies for any user.

Sample usage:
  python -m viewfinder.backend.www.tools.terminate_account \
    --devbox --target_user_id=1
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
from viewfinder.backend.db.db_client import DBClient, InitDB
from viewfinder.backend.db.dynamodb_client import DynamoDBClient
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.user import User
from viewfinder.backend.www.server import SERVER_VERSION

# Do not define options for tests.
if __name__ == '__main__':
  define('user_id', type=int, help='id of user account to terminate')


@gen.coroutine
def Terminate(client, user_id, base_url, no_prompt=False):
  # Get target user objects.
  user = yield gen.Task(User.Query, client, user_id, None)

  print '--------- TERMINATE ACCOUNT ----------'
  print '  User account to terminate: %s (user %d)' % (user.email, user_id)
  print ''

  if not no_prompt:
    answer = raw_input('Are you SURE you want to do this? Type \'yes\' to confirm: ')
    print ''
    if answer.lower() != 'yes':
      print 'ABORTED account termination.'
      return

  # Construct cookies for the user.
  cookie_secret = GetSecret('cookie_secret')
  user_cookie = create_signed_value(cookie_secret, 'user', json.dumps(dict(user_id=user_id,
                                                                           device_id=user.webapp_dev_id,
                                                                           server_version=SERVER_VERSION)))

  timestamp = time.time()
  http_headers = {
    'Cookie': '_xsrf=fake_xsrf; user=%s' % user_cookie,
    'X-XSRFToken': 'fake_xsrf',
    'Content-Type': 'application/json',
    }

  # Allocate unique asset ids for the operation.
  http_client = AsyncHTTPClient()
  body = {'headers': {'version': MAX_SUPPORTED_MESSAGE_VERSION},
          'asset_types': ['o']}
  response = yield gen.Task(http_client.fetch,
                            '%s/service/allocate_ids' % base_url,
                            method='POST',
                            body=json.dumps(body),
                            headers=http_headers,
                            validate_cert=options.validate_cert)
  operation_id, = json.loads(response.body)['asset_ids']

  body = {'headers': {'version': MAX_SUPPORTED_MESSAGE_VERSION,
                      'op_id': operation_id,
                      'op_timestamp': timestamp,
                      'synchronous': True}}
  yield gen.Task(http_client.fetch,
                 '%s/service/terminate_account' % base_url,
                 method='POST',
                 body=json.dumps(body),
                 headers=http_headers,
                 validate_cert=options.validate_cert)

  print 'Account termination succeeded.'


if __name__ == '__main__':
  @gen.coroutine
  def main():
    parse_command_line()
    assert options.user_id, '--user_id must be set'

    ServerEnvironment.InitServerEnvironment()
    yield gen.Task(InitSecrets)
    yield gen.Task(InitDB, vf_schema.SCHEMA, verify_or_create=False)
    yield Terminate(DBClient.Instance(),
                    user_id=options.user_id,
                    base_url='https://%s' % ServerEnvironment.GetHost())


  IOLoop.instance().run_sync(main)
