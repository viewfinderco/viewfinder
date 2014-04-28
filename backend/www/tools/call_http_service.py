#!/usr/bin/env python
"""Call a service method through the HTTP RPC interface.

Unlike run_service.py, which imports the service code and runs it directly, this
script goes through the HTTP interface.  Among other things, this allows it to be run
against a local server (the local db is not safe for access from multiple processes),
and doesn't require all the same command-line flags that a server would.

It relies on access to the cookie-signing secret to create cookies for any user.
Currently only read-only methods (i.e. those that use HEADERS instead of OP_HEADERS in
json_schema) are supported.

Sample usage against a local server:
  python -m viewfinder.backend.www.tools.call_http_service \
    --devbox --domain=goviewfinder.com --validate_cert=false \
    --base_url=https://www.goviewfinder.com:8443 \
    --user_id=1 --device_id=12 --body='{"user_ids": [1]}'
"""

import json
from tornado.ioloop import IOLoop
from tornado.httpclient import HTTPClient
from tornado.options import define, options, parse_command_line
from tornado.web import create_signed_value
from viewfinder.backend.base.message import MAX_SUPPORTED_MESSAGE_VERSION
from viewfinder.backend.base.secrets import InitSecrets, GetSecret

define('user_id', type=int, help='user id to authenticate as')
define('device_id', type=int)
define('base_url', default='https://www.viewfinder.co')
define('method', type=str)
define('body', default='{}')
define('validate_cert', default=True)


def main():
  parse_command_line()
  io_loop = IOLoop.instance()

  assert options.user_id, '--user_id must be set'
  assert options.device_id, '--device_id must be set'
  assert options.method, '--method must be set'
  assert not options.base_url.endswith('/'), 'base_url should be scheme://host:port only, no path'

  InitSecrets(callback=io_loop.stop)
  io_loop.start()

  cookie_secret = GetSecret('cookie_secret')
  # TODO(ben): move this (and the server_version constant) somewhere sharable that doesn't need
  # to pull in the entire server-side codebase.  Or add an auth flow like fetch_logs so we don't
  # need production secrets at all.
  cookie = create_signed_value(cookie_secret, 'user', json.dumps(dict(user_id=options.user_id,
                                                                      device_id=options.device_id,
                                                                      server_version='1.1')))

  url = '%s/service/%s' % (options.base_url, options.method)

  http_headers = {
    'Cookie': '_xsrf=fake_xsrf; user=%s' % cookie,
    'X-XSRFToken': 'fake_xsrf',
    'Content-Type': 'application/json',
    }
  body = json.loads(options.body)
  body.setdefault('headers', {}).setdefault('version', MAX_SUPPORTED_MESSAGE_VERSION)
  # TODO: support op headers too
  response = HTTPClient().fetch(url, method='POST', body=json.dumps(body), headers=http_headers,
                                validate_cert=options.validate_cert)
  print json.dumps(json.loads(response.body), indent=2)


if __name__ == '__main__':
  main()
