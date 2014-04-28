#!/usr/bin/env python
"""Uploads issues to bitbucket.
"""

import urllib

from tornado.escape import utf8
from tornado import gen
from tornado.httpclient import AsyncHTTPClient
from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line

import parse_cases

define('filename', default='cases.xml')
define('repo', default='viewfinder/viewfinder')
define('username', default='viewfinder')
define('password', default='')

@gen.coroutine
def main():
  parse_command_line()
  assert options.password
  client = AsyncHTTPClient()

  cases = parse_cases.parse_cases(options.filename)

  url = 'https://api.bitbucket.org/1.0/repositories/%s/issues' % options.repo
  for subject, assigned_to, body in cases:
    args = {'title': utf8(subject), 'content': utf8(body)}
    if assigned_to:
      args['responsible'] = assigned_to
    response = yield client.fetch(url, method='POST', body=urllib.urlencode(args),
                                  auth_username=options.username, auth_password=options.password)
    print response, response.body

if __name__ == '__main__':
  IOLoop.instance().run_sync(main)
