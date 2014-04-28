#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test xsrf protection.
"""

__author__ = 'mike@emailscrubbed.com (Mike Purtell)'

import json
import re

from viewfinder.backend.base import message
from viewfinder.backend.www.test import service_base_test

class XsrfTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(XsrfTestCase, self).setUp()

  def testXsrfFailureNoXsrfHeader(self):
    """Send a POST request without a header containing the xsrf token and expect failure.
    """
    self._tester.http_client.fetch(self._tester.GetUrl('/service/get_calendar'),
                                   callback=lambda r: self.stop(r), method='POST',
                                   body=json.dumps({'calendars':
                                                    [{'calendar_id': 'EnglishHolidays.ics', 'year': 2012}]}),
                                   headers={'Content-Type': 'application/json',
                                            'Cookie': 'user=%s' % self._cookie})
    response = self.wait()
    self.assertEqual(response.code, 403)

  def testXsrfFailureBadXsrfHeader(self):
    """Send a POST request with an xsrf token that doesn't match the token in the xsrf cookie and expect failure.
    """
    xsrf_cookie = '_xsrf=a3675174a8f64c72a4a626aae658dbcd'

    self._tester.http_client.fetch(self._tester.GetUrl('/service/get_calendar'),
                                   callback=lambda r: self.stop(r), method='POST',
                                   body=json.dumps({'calendars':
                                                    [{'calendar_id': 'EnglishHolidays.ics', 'year': 2012}]}),
                                   headers={'Content-Type': 'application/json',
                                            'Cookie': 'user=%s' % self._cookie + ';' + xsrf_cookie,
                                            # token which ends with '00' (cookie ends with 'cd') should fail.
                                            'X-Xsrftoken': 'a3675174a8f64c72a4a626aae658db00'})
    response = self.wait()
    self.assertEqual(response.code, 403)

  def testXsrfSuccess(self):
    """Send a POST request with an xsrf token that matches the on in the xsrf cookie and expect success.
    """
    xsrf_cookie = '_xsrf=a3675174a8f64c72a4a626aae658dbcd'

    self._tester.http_client.fetch(self._tester.GetUrl('/service/get_calendar'),
                                   callback=lambda r: self.stop(r), method='POST',
                                   body=json.dumps({'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION},
                                                    'calendars': [{'calendar_id': 'EnglishHolidays.ics',
                                                                   'year': 2012}]}),
                                   headers={'Content-Type': 'application/json',
                                            'Cookie': 'user=%s' % self._cookie + ';' + xsrf_cookie,
                                            'X-Xsrftoken': 'a3675174a8f64c72a4a626aae658dbcd'})
    response = self.wait()
    self.assertEqual(response.code, 200)

  def testXsrfAuthFailure(self):
    """Send a POST request to our auth handler without an xsrf token and expect a 403 failure.
    """
    self._tester.http_client.fetch(self._tester.GetUrl('/register/google'),
                                   callback=lambda r: self.stop(r), method='POST',
                                   body=json.dumps({'something': [{'invalid': 'stuff'}, {'other':'stuff'}]}),
                                   headers={'Content-Type': 'application/json',
                                            'Cookie': 'user=%s' % self._cookie})
    response = self.wait()
    # Some other error indicates that the request got past the xsrf protection.
    self.assertEqual(response.code, 403)

class ForceXsrfSendTestCase(service_base_test.ServiceBaseTestCase):
  """"Variation on above without _xsrf cookie checking/generation enabled.
  """
  def setUp(self):
    self._enable_xsrf = False
    super(ForceXsrfSendTestCase, self).setUp()

  def tearDown(self):
    self._enable_xsrf = True

  def testXsrfSendAlways(self):
    """Send a POST request without an xsrf token and with xsrf disabled and expect no XSRF cookie in a successful
    response.
    """
    self._tester.http_client.fetch(self._tester.GetUrl('/service/get_calendar'),
                                   callback=lambda r: self.stop(r), method='POST',
                                   body=json.dumps({'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION},
                                                    'calendars':
                                                    [{'calendar_id': 'EnglishHolidays.ics', 'year': 2012}]}),
                                   headers={'Content-Type': 'application/json',
                                            'Cookie': 'user=%s' % self._cookie})
    response = self.wait()
    self.assertEqual(response.code, 200)
    set_cookie = response.headers.get('Set-Cookie', '')
    match = re.compile('_xsrf=(.*);').match(set_cookie)
    self.assertTrue(match is None, 'Expecting no _xsrf cookie.')
