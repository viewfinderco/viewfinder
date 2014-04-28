# Copyright 2012 Viewfinder Inc. All Rights Reserved.
# -*- coding: utf-8 -*-

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import datetime
import logging
import mock
import time

from functools import partial
from tornado import options
from viewfinder.backend.base import otp, util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db import client_log
from viewfinder.backend.www import json_schema
from viewfinder.backend.www.test import service_base_test
from viewfinder.backend.www.test.service_base_test import ClientLogRecord

class NewClientLogUrlTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(NewClientLogUrlTestCase, self).setUp()

    # Write sample client logs.
    self._cur_t = time.time()
    self._t_minus_1d = self._cur_t - 24 * 60 * 60
    self._t_minus_2d = self._cur_t - 2 * 24 * 60 * 60

    self._logs = [(self._cookie, ClientLogRecord(self._t_minus_2d, 'cl1.t-2', 'log 1, t-2')),
                  (self._cookie, ClientLogRecord(self._t_minus_1d, 'cl1.t-1', 'log 1, t-1')),
                  (self._cookie, ClientLogRecord(self._cur_t, 'cl1.t.1', 'log 1, t')),
                  (self._cookie, ClientLogRecord(self._cur_t, 'cl1.t.2', 'log 2, t')),
                  (self._cookie2, ClientLogRecord(self._cur_t, 'cl2', 'user 2, log 1, t'))]
    for user_cookie, log in self._logs:
      self._WriteClientLog(user_cookie, log)

  def testListClientLogs(self):
    """Verify listing of client logs."""
    start_timestamp = self._cur_t
    end_timestamp = start_timestamp

    response_dict = self._tester.SendAdminRequest('list_client_logs',
                                                  {'user_id': self._users[0].user_id,
                                                   'start_timestamp': start_timestamp,
                                                   'end_timestamp': end_timestamp})

    urls = self._FilterList(response_dict['log_urls'])
    self.assertEqual(2, len(urls))

    content = self._FetchClientLog(urls[0]['url'])
    self.assertEqual('log 1, t', content)

    content = self._FetchClientLog(urls[1]['url'])
    self.assertEqual('log 2, t', content)

  def testMultipleDates(self):
    """Verify logs can be listed for multiple dates."""
    start_timestamp = self._t_minus_2d
    end_timestamp = self._cur_t

    response_dict = self._tester.SendAdminRequest('list_client_logs',
                                                  {'user_id': self._users[0].user_id,
                                                   'start_timestamp': start_timestamp,
                                                   'end_timestamp': end_timestamp})

    urls = self._FilterList(response_dict['log_urls'])
    self.assertEqual(4, len(urls))

  def testListFilter(self):
    """Verify logs can be filtered via regexp."""
    start_timestamp = self._cur_t
    end_timestamp = self._cur_t

    response_dict = self._tester.SendAdminRequest('list_client_logs',
                                                  {'user_id': self._users[0].user_id,
                                                   'start_timestamp': start_timestamp,
                                                   'end_timestamp': end_timestamp,
                                                   'filter': 'cl1.t.2'})

    urls = self._FilterList(response_dict['log_urls'])
    self.assertEqual(1, len(urls))
    self.assertTrue(urls[0]['filename'].endswith('dev-2-cl1.t.2'))

  @mock.patch.object(client_log, 'MAX_CLIENT_LOGS', 1)
  def testLimit(self):
    """Verify limit is respected."""
    response_dict = self._tester.SendAdminRequest('list_client_logs',
                                                  {'user_id': self._users[0].user_id,
                                                   'start_timestamp': self._cur_t,
                                                   'end_timestamp': self._cur_t,
                                                   'filter': 'dev-2'})
    urls = response_dict['log_urls']
    self.assertEqual(2, len(urls))
    self.assertTrue(urls[0]['filename'].endswith('dev-2-cl1.t.1'))
    self.assertTrue(urls[1]['filename'].endswith('dev-2-cl1.t.2'))

  def _FetchClientLog(self, url):
    """Fetches the client log specified by "url" and returns the
    contents to "callback".
    """
    response = self._RunAsync(self._tester.http_client.fetch, url, method='GET')
    self.assertEqual(200, response.code)
    return response.body

  def _FilterList(self, log_urls):
    """Remove op logs from response that were created by base class user
    registration.
    """
    return [log_url for log_url in log_urls if 'Operation' not in log_url['url']]
