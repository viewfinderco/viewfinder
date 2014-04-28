# Copyright 2012 Viewfinder Inc. All Rights Reserved.
# -*- coding: utf-8 -*-

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import iso8601
import logging
import math
import shutil
import sys
import tempfile
import time

from datetime import datetime
from tornado import options
from StringIO import StringIO
from viewfinder.backend.base import otp, util
from viewfinder.backend.base.constants import SECONDS_PER_DAY
from viewfinder.backend.base.testing import async_test, thread_test
from viewfinder.backend.db.client_log import ClientLog
from viewfinder.backend.www import json_schema
from viewfinder.backend.www.test import service_base_test
from viewfinder.backend.www.test.service_base_test import ClientLogRecord
from viewfinder.scripts import fetch_logs

class FetchLogsTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(FetchLogsTestCase, self).setUp()
    self._validate = False

    self._temp_dir = tempfile.mkdtemp()
    options.options.fetch_dir = self._temp_dir
    options.options.cache_logs = False

    # Clients logs for user 0 to verify querying with time range and filter.
    self._cur_t = math.floor(time.time())
    self._t_minus_1d = self._cur_t - 24 * 60 * 60
    self._t_minus_2d = self._cur_t - 2 * 24 * 60 * 60
    self._user0_logs = [ClientLogRecord(self._t_minus_2d, 'cl1.t-2.log', 'log 1, t-2'),
                        ClientLogRecord(self._t_minus_1d, 'cl1.t-1.log', 'log 1, t-1'),
                        ClientLogRecord(self._cur_t, 'cl1.t.1.log', 'log 1, t'),
                        ClientLogRecord(self._cur_t, 'cl1.t.2.log', 'log 2, t')]

    user_cookie = self._GetSecureUserCookie(user=self._users[0], device_id=self._device_ids[0])
    for log in self._user0_logs:
      self._WriteClientLog(user_cookie, log)

    # Client logs for user 1 to verify merging.
    self._t = fetch_logs.UTCDatetimeToTimestamp(
      fetch_logs.ParseIso8601DatetimeToUTCDatetime('2012-11-03'))

    log1a = """2012-11-03 13:29:31:000 <client log line 1>
<client log line 1b>
2012-11-03 13:29:33:000 <client log line 2>
<client log line 2b>"""
    log1b = """2012-11-03 14:14:28:000 <client log line 3>
2012-11-03 14:14:29:000 <client log line 4>"""
    op1a = """2012-11-03 13:29:32:000 <client op line 2>
2012-11-03 13:29:34:000 <client op line 3>"""
    op1b = """2012-11-03 13:29:30:000 <client op line 1>
2012-11-03 14:14:30:000 <client op line 4>"""

    self._merged = """2012-11-03 13:29:30:000 <client op line 1>
2012-11-03 13:29:31:000 <client log line 1>
<client log line 1b>
2012-11-03 13:29:32:000 <client op line 2>
2012-11-03 13:29:33:000 <client log line 2>
<client log line 2b>
2012-11-03 13:29:34:000 <client op line 3>
2012-11-03 14:14:28:000 <client log line 3>
2012-11-03 14:14:29:000 <client log line 4>
2012-11-03 14:14:30:000 <client op line 4>
"""

    self._user1_logs = [ClientLogRecord(self._t, '1a.log', log1a),
                        ClientLogRecord(self._t, '1b.log', log1b),
                        ClientLogRecord(self._t, 'op-1a.log', op1a),
                        ClientLogRecord(self._t, 'op-1b.log', op1b)]
    user_cookie = self._GetSecureUserCookie(user=self._users[1], device_id=self._device_ids[1])
    for log in self._user1_logs:
      self._WriteClientLog(user_cookie, log)

  def tearDown(self):
    """Cleans up the temporary directory."""
    shutil.rmtree(self._temp_dir)

  @thread_test
  def testFetchLogsScript(self):
    """Test scripts/fetch_logs.py."""
    self._FetchLogs(self._users[0].user_id, start_timestamp=self._cur_t,
                    end_timestamp=self._cur_t, exp_logs=self._user0_logs[2:])

  @thread_test
  def testFetchLogsScriptTimeRange(self):
    """Verify time ranges with fetch_logs."""
    self._FetchLogs(self._users[0].user_id, start_timestamp=self._t_minus_2d,
                    end_timestamp=self._cur_t, exp_logs=self._user0_logs)

  @thread_test
  def testFetchLogsScriptDateRange(self):
    """Verify date ranges with fetch_logs."""
    options.options.use_utc = True
    self._FetchLogs(self._users[0].user_id,
                    start_date=FetchLogsTestCase._IsoDateTime(self._t_minus_1d, utc_time=True),
                    end_date=FetchLogsTestCase._IsoDateTime(self._cur_t, utc_time=True),
                    exp_logs=self._user0_logs[1:])

    options.options.use_utc = False
    self._FetchLogs(self._users[0].user_id,
                    start_date=FetchLogsTestCase._IsoDateTime(self._t_minus_1d),
                    end_date=FetchLogsTestCase._IsoDateTime(self._cur_t),
                    exp_logs=self._user0_logs[1:])

  @thread_test
  def testFetchLogsScriptFilter(self):
    """Verify date ranges with fetch_logs."""
    self._FetchLogs(self._users[0].user_id, start_timestamp=self._cur_t,
                    end_timestamp=self._cur_t + SECONDS_PER_DAY, filter='t.2', exp_logs=self._user0_logs[3:])

  @thread_test
  def testFetchLogsScriptMerge(self):
    """Verify merged output from fetch of all logs for user 1."""
    log_urls = self._FetchLogs(self._users[1].user_id, start_timestamp=self._t,
                               end_timestamp=self._t + SECONDS_PER_DAY, exp_logs=self._user1_logs)
    # Redirect stdout to a file for testing.
    output = StringIO()
    options.options.merge_logs = True
    fetch_logs.MergeLogs(log_urls, output)
    self.assertEqual(self._merged, output.getvalue())
    output.close()

  def _GetAdminOpener(self):
    """Gets the admin opener. Returns the opener and api_host."""
    otp._ClearUserHistory()
    api_host = 'www.goviewfinder.com:%d' % self.get_http_port()
    tmp_file = tempfile.NamedTemporaryFile(delete=False)
    opener = otp.GetAdminOpener(api_host, 'test-user', 'test-password',
                                otp.GetOTP('test-user'), tmp_file.name)
    return api_host, opener

  def _FetchLogs(self, user_id, start_date=None, start_timestamp=None,
                 end_date=None, end_timestamp=None, filter=None, exp_logs=[]):
    """Calls the fetch_logs.FetchLogs method by setting command-line
    options according to this method's parameters. Verifies the resulting
    list of fetched urls and the contents of the locally saved log files.

    Returns the resulting array of log urls from fetch_logs.FetchLogs().
    """
    api_host, opener = self._GetAdminOpener()

    options.options.user_id = user_id
    # Clear all existing fetch_logs options.
    options.options.start_date = None
    options.options.start_timestamp = None
    options.options.end_date = None
    options.options.end_timestamp = None
    options.options.filter = None

    if start_date is not None:
      options.options.start_date = start_date
    if start_timestamp is not None:
      options.options.start_timestamp = start_timestamp
    if end_date is not None:
      options.options.end_date = end_date
    if end_timestamp is not None:
      options.options.end_timestamp = end_timestamp
    if filter is not None:
      options.options.filter = filter
    log_urls = fetch_logs.FetchLogs(opener, api_host)

    # Filter out logs created by ops run in base class.
    log_urls = [log_url for log_url in log_urls if 'Operation' not in log_url['url']]

    self.assertEqual(len(exp_logs), len(log_urls))
    for exp_log, log_url in zip(exp_logs, log_urls):
      self.assertTrue(log_url['filename'].endswith(exp_log.client_id))
      self.assertTrue(log_url['url'].endswith(exp_log.client_id))
      # Read locally-saved file and verify contents.
      with open(log_url['local_filename'], 'r') as f:
        contents = f.read()
      self.assertEqual(exp_log.contents, contents)
    return log_urls

  @staticmethod
  def _IsoDateTime(timestamp, utc_time=False):
    """Converts timestamp to ISO 8601 date/time value. If "utc_time" is true, return the UTC
    date/time. Otherwise, return the local date/time.
    """
    dt = datetime.utcfromtimestamp(timestamp) if utc_time else datetime.fromtimestamp(timestamp)
    return dt.strftime('%Y-%m-%d %H:%M:%S')
