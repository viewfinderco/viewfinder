# Copyright 2012 Viewfinder Inc. All Rights Reserved.
# -*- coding: utf-8 -*-

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import datetime
import json
import time

from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.client_log import ClientLog, CLIENT_LOG_CONTENT_TYPE
from viewfinder.backend.www import json_schema
from viewfinder.backend.www.test import service_base_test

class NewClientLogUrlTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(NewClientLogUrlTestCase, self).setUp()
    self._validate = False

  def testNewClientLogUrl(self):
    """Verify the put url can be fetched via /service/get_client_log."""
    timestamp = time.time()
    log_timestamp = timestamp - 24 * 60 * 60

    response_dict = self._SendRequest('new_client_log_url', self._cookie,
                                      {'headers': {'op_id': 'o1', 'op_timestamp': timestamp},
                                       'timestamp': log_timestamp,
                                       'client_log_id': 'log1'})
    exp_put_url = ClientLog.GetPutUrl(
      self._user.user_id, self._device_ids[0], log_timestamp, 'log1')
    self.assertEqual(exp_put_url, response_dict['client_log_put_url'])

  def testContentType(self):
    """Verify that content type can be set explicitly and used."""
    request_dict = {'headers': {'op_id': 'o1', 'op_timestamp': time.time()},
                    'timestamp': time.time(),
                    'client_log_id': 'log_content_type',
                    'content_type': 'text/plain'}
    self._GetNewLogUrlAndVerify(request_dict, 'test log file',
                                content_type='test/plain',
                                content_md5=None)

  def testDefaultContentType(self):
    """Verify default content type."""
    request_dict = {'headers': {'op_id': 'o1', 'op_timestamp': time.time()},
                    'timestamp': time.time(),
                    'client_log_id': 'default_content_type'}
    self._GetNewLogUrlAndVerify(request_dict, 'test log file',
                                content_type=CLIENT_LOG_CONTENT_TYPE,
                                content_md5=None)

  def testMD5ClientLog(self):
    """Verify MD5 validation for client logs."""
    log_body = 'test log file'
    content_md5 = util.ComputeMD5Hex(log_body)

    request_dict = {'headers': {'op_id': 'o1', 'op_timestamp': time.time()},
                    'timestamp': time.time(),
                    'client_log_id': 'log1',
                    'content_md5': content_md5}
    self._GetNewLogUrlAndVerify(request_dict, log_body,
                                content_type=CLIENT_LOG_CONTENT_TYPE,
                                content_md5=content_md5)

  def _GetNewLogUrlAndVerify(self, request_dict, log_body, content_type, content_md5):
    """Get a new client log url based on "request_dict" and verify
    the URL can be PUT using the specified content-type and md5.
    """
    response_dict = self._SendRequest('new_client_log_url', self._cookie, request_dict)
    url = response_dict['client_log_put_url']

    headers = {'Content-Type': content_type}
    if content_md5 is not None:
      headers['Content-MD5'] = content_md5
    response = self._RunAsync(self._tester.http_client.fetch, url, method='PUT',
                              body=log_body, follow_redirects=False, headers=headers)
    self.assertEqual(200, response.code)
