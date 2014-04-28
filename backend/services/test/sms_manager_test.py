#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Account authorization tests for Viewfinder accounts.
"""

__authors__ = ['greg@emailscrubbed.com (Greg Vandenberg)']

import mock
import os
import unittest
import urllib
import json

from cStringIO import StringIO
from tornado import httpclient
from viewfinder.backend.base.testing import MockAsyncHTTPClient
from viewfinder.backend.services.sms_mgr import TwilioSMSManager, ClickatellSMSManager
from viewfinder.backend.www.test import auth_test, service_base_test
from viewfinder.backend.base.exceptions import SMSError


@unittest.skipIf('NO_NETWORK' in os.environ, 'no network')
class SMSManagerTestCase(service_base_test.ServiceBaseTestCase):
  """Tests SMS Manager sendSMS via the Twilio or Clickatell service."""

  def testTwilioSMSManagerSend(self):
    """Test the Twilio API."""
    info_dict = {'Body': u'this is a test text \xc9', 'To': '+14251234567', 'From': '+12061234567'}
    expected_response_dict = {'account_sid': 'ACa437bddda03231c80f4c463dc51513bb',
                              'api_version': '2010-04-01',
                              'body': 'Jenny please?! I love you <3',
                              'date_created': 'Wed, 18 Aug 2010 20:01:40 +0000',
                              'date_sent': 'null',
                              'date_updated': 'Wed, 18 Aug 2010 20:01:40 +0000',
                              'direction': 'outbound-api',
                              'from': '+12061234567',
                              'price': 'null',
                              'sid': 'SM90c6fc909d8504d45ecdb3a3d5b3556e',
                              'status': 'queued',
                              'to': '+14151234567',
                              'uri': '/2010-04-01/Accounts/ACa437bddda03231c80f4c463dc51513bb/SMS/Messages/SM90c6fc909d8504d45ecdb3a3d5b3556e.json'
                              }
    sms = TwilioSMSManager()
    # Mock responses from Twilio.
    with mock.patch('tornado.httpclient.AsyncHTTPClient', MockAsyncHTTPClient()) as mock_client:
      # Response to sms.
      _AddMockJSONResponse(mock_client,
                           r'https://api.twilio.com/2010-04-01/Accounts/dummy_twilio_account_sid/SMS/Messages.json',
                           expected_response_dict
                          )
      response_dict = self._RunAsync(sms.SendSMS, number=info_dict['To'], text=info_dict['Body'])
      self.assertEqual(expected_response_dict, response_dict);

  def testTwilioSMSManagerSendError(self):
    """Test the Twilio SMS Manager http error handling."""
    info_dict = {'Body': 'this is a test text', 'To': '+14251234567', 'From': '+12061234567'}

    sms = TwilioSMSManager()
    # Mock responses from Twilio.
    with mock.patch('tornado.httpclient.AsyncHTTPClient', MockAsyncHTTPClient()) as mock_client:
      # Response to sms.
      _AddMockJSONResponseError(mock_client,
                           r'https://api.twilio.com/2010-04-01/Accounts/dummy_twilio_account_sid/SMS/Messages.json')
      self.assertRaises(SMSError, self._RunAsync, sms.SendSMS, number=info_dict['To'], text=info_dict['Body'])

  def testClickatellSMSManagerSendError(self):
    """Test the Clickatell SMS Manager http error handling."""
    info_dict = {
      'user': 'viewfinder-dev',
      'password': 'SPAMM_5!',
      'api_id': '3391545',
      'to': '14257502513',
      'MO': '1',
      'from': '16467361610',
      'text': 'this is a test text',
    }
    sms = ClickatellSMSManager()
    # Mock responses from Twilio.
    with mock.patch('tornado.httpclient.AsyncHTTPClient', MockAsyncHTTPClient()) as mock_client:
      # Response to sms.
      _AddMockJSONResponseError(mock_client,
                           r'https://api.clickatell.com/http/sendmsg')
      self.assertRaisesHttpError(401, self._RunAsync, sms.SendSMS, number=info_dict['to'], text=info_dict['text'])

  def testClickatellSMSManagerSend(self):
    """Test the Clickatell API."""
    info_dict = {
      'user': 'viewfinder-dev',
      'password': 'SPAMM_5!',
      'api_id': '3391545',
      'to': '14257502513',
      'MO': '1',
      'from': '16467361610',
      'text': 'this is a test text',
      }

    expected_response_dict = {'ID': '18af4edb086a15f7904a1584c7960c2a'}

    sms = ClickatellSMSManager()
    # Mock responses from Clickatell.
    with mock.patch('tornado.httpclient.AsyncHTTPClient', MockAsyncHTTPClient()) as mock_client:
      # Response to sms.
      _AddMockJSONResponse(mock_client, r'https://api.clickatell.com/http/sendmsg', expected_response_dict)

      response_dict = self._RunAsync(sms.SendSMS, number=info_dict['to'], text=info_dict['text'])

      self.assertEqual(expected_response_dict, response_dict);

def _AddMockJSONResponse(mock_client, url, response_dict):
  """Add a mapping entry to the mock client such that requests to
  "url" will return an HTTP response containing the JSON-formatted
  "response_dict".
  """
  def _CreateResponse(request):
    return httpclient.HTTPResponse(request, 201,
                                   headers={'Content-Type': 'application/json'},
                                   buffer=StringIO(json.dumps(response_dict)))

  mock_client.map(url, _CreateResponse)

def _AddMockJSONResponseError(mock_client, url):
  """Add a mapping entry to the mock client such that requests to
  "url" will return an HTTP response containing the JSON-formatted
  "response_dict".
  """
  def _CreateResponse(request):
    print request
    return httpclient.HTTPResponse(request, 401,
                                   headers={'Content-Type': 'application/json'},
                                   buffer=None)

  mock_client.map(url, _CreateResponse)
