#!/usr/bin/env python
#
# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Test miscellaneous server.py functionality.
"""

__author__ = 'ben@emailscrubbed.com (Ben Darnell)'

import mock
from cStringIO import StringIO
from tornado.httpclient import HTTPResponse
from viewfinder.backend.base.testing import MockAsyncHTTPClient
from viewfinder.backend.www.test import service_base_test

class ServerTestCase(service_base_test.ServiceBaseTestCase):
  def test_app_redirect(self):
    """Follow the redirect from /app to app store and verify google analytics logging."""
    requests = []
    def _LogRequest(request):
      requests.append(request)
      return HTTPResponse(request, 200, buffer=StringIO(''))
    with mock.patch('tornado.httpclient.AsyncHTTPClient', MockAsyncHTTPClient()) as mock_client:
      mock_client.map('.*', _LogRequest)
      response = self.fetch('/app', follow_redirects=False)
    self.assertEqual(response.code, 302)
    self.assertIn('https://itunes.apple.com', response.headers['Location'])
    self.assertEqual(len(requests), 1)
    self.assertEqual('http://www.google-analytics.com/collect', requests[0].url)
