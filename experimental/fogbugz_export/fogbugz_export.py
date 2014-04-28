#!/usr/bin/env python
"""Exports fogbugz cases to a file.

Create a text file ~/.fogbugz containing your credentials in json:
  {"email": "ben@emailscrubbed.com", "password": "asdf"}

The fogbugz API is insane: the API doesnt let you specify queries directly; it uses
a single persistent per-user query (same as the website).  Before running this script
go to the fogbugz website and set your current view to the query you want to run
(e.g. "all open cases").
"""

import json
import os
import urllib
from xml.etree import ElementTree

from tornado import gen
from tornado.httpclient import AsyncHTTPClient
from tornado.ioloop import IOLoop
from tornado.options import define, options, parse_command_line

define('base_url', default='https://viewfinder.fogbugz.com/api.asp')
define('credential_file', default=os.path.expanduser('~/.fogbugz'))
define('output_file', default='cases.xml')

def make_url(**kwargs):
  return options.base_url + '?' + urllib.urlencode(kwargs)

@gen.coroutine
def fetch(**kwargs):
  http = AsyncHTTPClient()
  response = yield http.fetch(make_url(**kwargs))
  raise gen.Return(ElementTree.fromstring(response.body))

@gen.coroutine
def main():
  parse_command_line()

  with open(options.credential_file) as f:
    credentials = json.load(f)

  response = yield fetch(cmd='logon', email=credentials['email'], password=credentials['password'])

  token = response.find('token').text

  cases = yield fetch(cmd='search', token=token,
                      cols='sTitle,sPersonAssignedTo,sProject,sArea,sCategory,ixPriority,sPriority,events')

  with open(options.output_file, 'w') as f:
    f.write(ElementTree.tostring(cases))

if __name__ == '__main__':
  IOLoop.instance().run_sync(main)
