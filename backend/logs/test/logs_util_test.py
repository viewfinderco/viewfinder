# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""logs_util.py tests.
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import logging
import unittest
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.storage.file_object_store import FileObjectStore
from viewfinder.backend.base.testing import BaseTestCase
from viewfinder.backend.logs import logs_util


class LogsUtilTestCase(BaseTestCase):
  def setUp(self):
    super(LogsUtilTestCase, self).setUp()
    self.object_store = FileObjectStore(ObjectStore.SERVER_LOG, temporary=True)
    # Put a key to initialize the file object store.
    self.key = 'hello'
    self._RunAsync(self.object_store.Put, self.key, 'world')

  def tearDown(self):
    self.object_store.Delete(self.key, None)
    super(LogsUtilTestCase, self).tearDown()

  def testServerLogsPaths(self):
    """Test path utility class for server logs."""
    # Instance names.
    self.assertTrue(logs_util.IsEC2Instance('i-a92c0'))
    self.assertFalse(logs_util.IsEC2Instance('vintner.local'))

    slogs = logs_util.ServerLogsPaths('viewfinder', 'full')
    self.assertEquals(slogs.RawDirectory(), 'viewfinder/full')
    self.assertEquals(slogs.MergedDirectory(), 'merged_server_logs/viewfinder/full')
    self.assertEquals(slogs.ProcessedRegistryPath(), 'merged_server_logs/viewfinder/full/PROCESSED')

    # Raw logs path parsing.
    raw_path = 'viewfinder/full/2013-01-04T17:20:38.422833/i-e7f7e69b/26186'
    self.assertEquals(slogs.RawLogPathToInstance(raw_path), 'i-e7f7e69b')
    self.assertEquals(slogs.RawLogPathToInstance('foo/bar'), None)

    # Merged logs path parsing.
    processed_path = 'merged_server_logs/viewfinder/full/2013-01-04/i-e7f7e69b'
    self.assertEquals(slogs.MergedLogPathToInstance(processed_path), 'i-e7f7e69b')
    self.assertEquals(slogs.MergedLogPathToDate(processed_path), '2013-01-04')
    self.assertEquals(slogs.MergedLogPathToInstance('merged_server_logs/viewfinder/full/date'), None)
    self.assertEquals(slogs.MergedLogPathToDate('merged_server_logs/viewfinder/full/date'), None)


  def testUserAnalyticsLogsPaths(self):
    """Test path utility class for user analytics logs."""
    clogs = logs_util.UserAnalyticsLogsPaths('112')
    self.assertEquals(clogs.RawDirectory(), '112/')
    self.assertEquals(clogs.MergedDirectory(), 'merged_user_analytics/')
    self.assertEquals(clogs.ProcessedRegistryPath(), 'merged_user_analytics/PROCESSED/112')

    # logs path parsing.
    res = clogs.ParseRawLogPath('112/2013-01-31/dev-3342-16-40-39.348-1.2.1.13.analytics.gz')
    self.assertEquals(res, ('analytics', '112', '3342', '1.2.1.13'))
    res = clogs.ParseRawLogPath('112/2013-02-10/dev-3562-22-06-11.050-1.3.0.14.log.gz')
    self.assertEquals(res, ('log', '112', '3562', '1.3.0.14'))
    res = clogs.ParseRawLogPath('112/2013-02-10/dev-3562-22-06-11-0.1.3.14.log.gz')
    self.assertEquals(res, ('log', '112', '3562', '0.1.3.14'))
    res = clogs.ParseRawLogPath('112/2013-02-10/dev-3562-22-06-11.050.analytics.gz')
    self.assertEquals(res, ('analytics', '112', '3562', None))
    res = clogs.ParseRawLogPath('112/2013-02-10/dev-3562-22-06-11.analytics.gz')
    self.assertEquals(res, ('analytics', '112', '3562', None))


  def testLogParse(self):
    """Test log line parsing functions."""
    success_log_line = '2013-01-04 00:04:20:624 [pid:3883] user_op_manager:247: SUCCESS: user: 271, ' \
                       'device: 1774, op: ovVqW7V, method: Device.UpdateOperation in 0.104s'
    execute_log_line = "2013-02-25 00:02:05:691 [pid:3714] user_op_manager:356: EXECUTE: user: 1190, device: 4021, " \
                       "op: ohGz88k, method: Device.UpdateOperation: {u'device_dict': {u'device_id': 4021, " \
                       "u'device_uuid': u'FDAB1FA3-C43C-4195-9856-2ECCADBF6B3F', u'name': '...scrubbed 16 bytes...', " \
                       "u'os': u'iPhone OS 6.1.2', u'platform': u'iPhone 5', u'push_token': " \
                       "u'apns-prod:...scrubbed...', u'version': u'1.3.1.16'}, " \
                       "u'device_id': 4021, u'user_id': 1190}"
    ping_log_line = '2013-02-25 00:11:08:750 [pid:3714] base:575: /ping OK: request: {"device": {"name": ' \
                    '"Gabrielle", "device_uuid": "4BA7D53D-2B33-41F1-A574-A6ACE052521D", "platform": "iPhone 5", ' \
                    '"version": "1.3.1.16", "push_token": "...scrubbed...", ' \
                    '"os": "iPhone OS 6.1", "device_id": 1458}, "headers": {"version": 13}}'
    new_ping_log_line = '2013-05-20 00:43:24:029 [pid:25000] ping:92: ping OK: request: {"device": {"name": ' \
                        '"iPhone Simulator", "device_uuid": "97415FE5-2D89-4C30-9064-5E138DAC2FBF", "platform": ' \
                        '"iPhone Simulator", "version": "1.6.0.41.dev", "os": "iPhone OS 6.1", "device_id": 3647}, ' \
                        '"headers": {"version": 17}} response: {"message": {"body": "you have the latest ' \
                        'development version", "identifier": "latest-dev-1.6.0.41.dev", "link": ' \
                        '"http://appstore.com/minetta/viewfinder", "severity": "INFO", ' \
                        '"title": "congrats on running 1.6.0.41.dev"}}'
    other_log_line = '2013-01-04 00:04:21:942 [pid:3883] service:263: GET NEW CLIENT LOG URL: user: 271, ' \
                     'device: 1774, client log id: 17-14-22.013-1.1.2.analytics.gz'

    # Parse entire log lines.
    self.assertEquals(logs_util.ParseLogLine(success_log_line),
                      ('2013-01-04', '00:04:20:624', 'user_op_manager:247',
                       'SUCCESS: user: 271, device: 1774, op: ovVqW7V, method: Device.UpdateOperation in 0.104s'))
    self.assertEquals(logs_util.ParseLogLine(other_log_line),
                      ('2013-01-04', '00:04:21:942', 'service:263',
                       'GET NEW CLIENT LOG URL: user: 271, device: 1774, client log ' \
                       'id: 17-14-22.013-1.1.2.analytics.gz'))

    self.assertEquals(logs_util.ParseLogLine(''), None)
    self.assertEquals(logs_util.ParseLogLine('2013/01/04 00:04:20:624 [pid:3883] user_op_manager:247: SUCCESS'), None)
    self.assertEquals(logs_util.ParseLogLine('2013-01-04 00:04:20:624 pid:3883 user_op_manager:247: SUCCESS'), None)
    self.assertEquals(logs_util.ParseLogLine('2013-01-04 00:04:20:624 [pid:3883] user_op_manager: SUCCESS'), None)

    # Parse message part of a user_op_manager::SUCCESS log line.
    (date, time, module, msg) = logs_util.ParseLogLine(success_log_line)
    self.assertEquals(msg, 'SUCCESS: user: 271, device: 1774, op: ovVqW7V, method: Device.UpdateOperation in 0.104s')
    self.assertEquals(logs_util.ParseSuccessMsg(msg), ('271', '1774', 'ovVqW7V', 'Device', 'UpdateOperation'))

    self.assertEquals(logs_util.ParseSuccessMsg('FAILURE: user: 271, device: 1774, op: ovVqW7V, ' \
                                           'method: Device.UpdateOperation in 0.104s'), None)
    self.assertEquals(logs_util.ParseSuccessMsg('SUCCESS: user:271, device: 1774, op: ovVqW7V, ' \
                                           'method: Device.UpdateOperation in 0.104s'), None)
    self.assertEquals(logs_util.ParseSuccessMsg('SUCCESS: user: 271, device: 1774, op:ovVqW7V, ' \
                                           'method: Device.UpdateOperation in 0.104s'), None)
    self.assertEquals(logs_util.ParseSuccessMsg('SUCCESS: user: 271, device: 1774, op: ovVqW7V, ' \
                                           'method: DeviceUpdateOperation in 0.104s'), None)

    # Parse message part of a user_op_manager::EXECUTE log line.
    (date, time, module, msg) = logs_util.ParseLogLine(execute_log_line)
    self.assertEquals(msg,
                      "EXECUTE: user: 1190, device: 4021, " \
                      "op: ohGz88k, method: Device.UpdateOperation: {u'device_dict': {u'device_id': 4021, " \
                      "u'device_uuid': u'FDAB1FA3-C43C-4195-9856-2ECCADBF6B3F', u'name': '...scrubbed 16 bytes...', " \
                      "u'os': u'iPhone OS 6.1.2', u'platform': u'iPhone 5', u'push_token': " \
                      "u'apns-prod:...scrubbed...', u'version': u'1.3.1.16'}, " \
                      "u'device_id': 4021, u'user_id': 1190}")

    self.assertEquals(logs_util.ParseExecuteMsg(msg), ('1190', '4021', 'ohGz88k', 'Device', 'UpdateOperation',
                      "{u'device_dict': {u'device_id': 4021, " \
                      "u'device_uuid': u'FDAB1FA3-C43C-4195-9856-2ECCADBF6B3F', u'name': '...scrubbed 16 bytes...', " \
                      "u'os': u'iPhone OS 6.1.2', u'platform': u'iPhone 5', u'push_token': " \
                      "u'apns-prod:...scrubbed...', u'version': u'1.3.1.16'}, " \
                      "u'device_id': 4021, u'user_id': 1190}"))


    # Parse message part of a ping log line.
    (date, time, module, msg) = logs_util.ParseLogLine(ping_log_line)
    self.assertTrue(module.startswith('base:'))
    self.assertEquals(msg,
                      '/ping OK: request: {"device": {"name": ' \
                      '"Gabrielle", "device_uuid": "4BA7D53D-2B33-41F1-A574-A6ACE052521D", "platform": "iPhone 5", ' \
                      '"version": "1.3.1.16", "push_token": "...scrubbed...", ' \
                      '"os": "iPhone OS 6.1", "device_id": 1458}, "headers": {"version": 13}}')

    self.assertEquals(logs_util.ParsePingMsg(msg),
                      '{"device": {"name": ' \
                      '"Gabrielle", "device_uuid": "4BA7D53D-2B33-41F1-A574-A6ACE052521D", "platform": "iPhone 5", ' \
                      '"version": "1.3.1.16", "push_token": "...scrubbed...", ' \
                      '"os": "iPhone OS 6.1", "device_id": 1458}, "headers": {"version": 13}}')


    # Parse the new ping log line.
    (date, time, module, msg) = logs_util.ParseLogLine(new_ping_log_line)
    self.assertTrue(module.startswith('ping:'))
    self.assertEquals(msg,
                      'ping OK: request: {"device": {"name": ' \
                      '"iPhone Simulator", "device_uuid": "97415FE5-2D89-4C30-9064-5E138DAC2FBF", "platform": ' \
                      '"iPhone Simulator", "version": "1.6.0.41.dev", "os": "iPhone OS 6.1", "device_id": 3647}, ' \
                      '"headers": {"version": 17}} response: {"message": {"body": "you have the latest development ' \
                      'version", "identifier": "latest-dev-1.6.0.41.dev", "link": ' \
                      '"http://appstore.com/minetta/viewfinder", "severity": "INFO", ' \
                      '"title": "congrats on running 1.6.0.41.dev"}}')

    (request, response) = logs_util.ParseNewPingMsg(msg)
    self.assertEquals(request,
                      '{"device": {"name": ' \
                      '"iPhone Simulator", "device_uuid": "97415FE5-2D89-4C30-9064-5E138DAC2FBF", "platform": ' \
                      '"iPhone Simulator", "version": "1.6.0.41.dev", "os": "iPhone OS 6.1", "device_id": 3647}, ' \
                      '"headers": {"version": 17}}')
    self.assertEquals(response,
                      '{"message": {"body": "you have the latest development ' \
                      'version", "identifier": "latest-dev-1.6.0.41.dev", "link": ' \
                      '"http://appstore.com/minetta/viewfinder", "severity": "INFO", ' \
                      '"title": "congrats on running 1.6.0.41.dev"}}')


  def testRegistry(self):
    """Test registry-related functions: read/write."""
    # Registry file does not exist: error is caught and returned contents is None.
    contents = self._RunAsync(logs_util.GetRegistry, self.object_store, 'viewfinder/full/PROCESSED')
    self.assertEquals(contents, None)

    # Write registry file with empty contents.
    self._RunAsync(logs_util.WriteRegistry, self.object_store, 'viewfinder/full/PROCESSED', [])
    contents = self._RunAsync(logs_util.GetRegistry, self.object_store, 'viewfinder/full/PROCESSED')
    self.assertEquals(contents, [])
    # Check for a different logs category.
    contents = self._RunAsync(logs_util.GetRegistry, self.object_store, 'viewfinder/info/PROCESSED')
    self.assertEquals(contents, None)

    # Write with non-empty contents. Each line is stripped of leading and trailing whitespace.
    contents = [ '  foo/bar  ', '  foo/bar/baz', 'foo/baz/bar  ' ]
    self._RunAsync(logs_util.WriteRegistry, self.object_store, 'viewfinder/full/PROCESSED', contents)
    fetched = self._RunAsync(logs_util.GetRegistry, self.object_store, 'viewfinder/full/PROCESSED')
    self.assertEquals(fetched, ['foo/bar', 'foo/bar/baz', 'foo/baz/bar'])


  def testListUserLogs(self):
    """Test functions that list user logs."""
    # Create and test raw logs.
    self.assertEquals(self._RunAsync(logs_util.ListClientLogUsers, self.object_store), [])

    raw_files = [
      'bogusdir/2013-01-31/dev-2900-22-43-02.757-1.1.11.log.gz',
      '112/2013-01-31/dev-2900-22-43-02.757-1.1.11.log.gz',
      '112/2013-01-31/dev-3293-00-39-29.430-1.2.1.13.log.gz',
      '112/2013-02-02/dev-3562-12-07-53.984-1.2.12.log.gz',
      '1/2013-02-01/dev-1446-08-28-25.147-1.3.0.14.dev.log.gz',
      '1/2013-02-03/op/Comment.PostOperation/odVi0gFJ/0'
      ]

    for f in raw_files:
      self._RunAsync(self.object_store.Put, f, 'test')

    self.assertEquals(self._RunAsync(logs_util.ListClientLogUsers, self.object_store), ['1', '112'])


import json
from viewfinder.backend.base import util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import metric
from viewfinder.backend.db.test.base_test import DBBaseTestCase

class LogsUtilMetricsTestCase(DBBaseTestCase):
  def setUp(self):
    super(LogsUtilMetricsTestCase, self).setUp()
    cluster = metric.LOGS_STATS_NAME
    self._group_key = metric.Metric.EncodeGroupKey(cluster, metric.Metric.FindIntervalForCluster(cluster, 'daily'))

  def _WriteMetric(self, day, dotdict):
    new_metric = metric.Metric.Create(self._group_key, 'logs_daily',
                                      util.ISO8601ToUTCTimestamp(day, hour=12),
                                      json.dumps(dotdict))
    self._RunAsync(new_metric.Update, self._client)

  def _GetMetric(self, day, h=12, m=0, s=0):
    timestamp = util.ISO8601ToUTCTimestamp(day, hour=h, minute=m, second=s)
    existing_metrics = self._RunAsync(metric.Metric.QueryTimespan, self._client, self._group_key,
                                      timestamp, timestamp)
    if len(existing_metrics) == 0:
      return None
    return DotDict(json.loads(existing_metrics[0].payload))

  def testUpdateMetrics(self):
    def _DotDictsEqual(dict1, dict2): return dict1.flatten() == dict2.flatten()

    # Write some basic metrics.
    stats_1 = DotDict({'itunes': {'downloads': {'US': 1, 'UK': 2, 'FR': 3}}})
    stats_2 = DotDict({'itunes': {'downloads': {'US': 5, 'DE': 6}}})
    stats_3 = DotDict({'itunes': {'updates': {'US': 4, 'UK': 5, 'FR': 6}}})
    self._WriteMetric('2013-01-01', stats_1)
    self._WriteMetric('2013-01-02', stats_2)
    self._WriteMetric('2013-01-03', stats_3)

    # Dict of new stats.
    new_stats = {'2013-01-01': stats_1,    # No changes.
                 '2013-01-02': stats_1,    # Changed.
                 '2013-01-03': stats_2,    # Changed, but in a different prefix
                 '2013-01-04': stats_2,    # New metric.
                }

    # Dry-run only.
    self._RunAsync(logs_util.UpdateMetrics, self._client, new_stats, dry_run=True)
    self.assertTrue(_DotDictsEqual(stats_1, self._GetMetric('2013-01-01')))
    self.assertTrue(_DotDictsEqual(stats_2, self._GetMetric('2013-01-02')))
    self.assertTrue(_DotDictsEqual(stats_3, self._GetMetric('2013-01-03')))
    self.assertIsNone(self._GetMetric('2013-01-04'))

    self._RunAsync(logs_util.UpdateMetrics, self._client, new_stats, dry_run=True, prefix_to_erase='itunes')
    self.assertTrue(_DotDictsEqual(stats_1, self._GetMetric('2013-01-01')))
    self.assertTrue(_DotDictsEqual(stats_2, self._GetMetric('2013-01-02')))
    self.assertTrue(_DotDictsEqual(stats_3, self._GetMetric('2013-01-03')))
    self.assertIsNone(self._GetMetric('2013-01-04'))

    # Update only, don't erase previous metrics.
    self._RunAsync(logs_util.UpdateMetrics, self._client, new_stats, dry_run=False)
    # stats1 doesn't change.
    self.assertTrue(_DotDictsEqual(stats_1, self._GetMetric('2013-01-01')))
    # stats2 gains UK and FR from stats1, keeps its own DE, and changes US.
    self.assertTrue(_DotDictsEqual(self._GetMetric('2013-01-02'),
                                   DotDict({'itunes': {'downloads': {'US': 1, 'UK': 2, 'FR': 3, 'DE': 6}}})))
    # stats3 keeps its own data (different prefix) and gains stats2 under 'downloads'.
    self.assertTrue(_DotDictsEqual(self._GetMetric('2013-01-03'),
                                   DotDict({'itunes': {'downloads': {'US': 5, 'DE': 6},
                                                       'updates': {'US': 4, 'UK': 5, 'FR': 6}}})))
    # stats4 is brand new.
    self.assertTrue(_DotDictsEqual(stats_2, self._GetMetric('2013-01-04')))


    # Rewrite metrics. 2013-01-04 will still be filled.
    self._WriteMetric('2013-01-01', stats_1)
    self._WriteMetric('2013-01-02', stats_2)
    self._WriteMetric('2013-01-03', stats_3)

    # Update and erase a given prefix on previous metrics.
    self._RunAsync(logs_util.UpdateMetrics, self._client, new_stats,
                   dry_run=False, prefix_to_erase='itunes.downloads')
    # stats1 doesn't change.
    self.assertTrue(_DotDictsEqual(stats_1, self._GetMetric('2013-01-01')))
    # stats2 gains UK and FR from stats1, a new value for US, and drop DE.
    self.assertTrue(_DotDictsEqual(self._GetMetric('2013-01-02'),
                                   DotDict({'itunes': {'downloads': {'US': 1, 'UK': 2, 'FR': 3}}})))
    # stats3 keeps its own data (different prefix) and gains stats2 under 'downloads'.
    self.assertTrue(_DotDictsEqual(self._GetMetric('2013-01-03'),
                                   DotDict({'itunes': {'downloads': {'US': 5, 'DE': 6},
                                                       'updates': {'US': 4, 'UK': 5, 'FR': 6}}})))
    # stats4 is brand new.
    self.assertTrue(_DotDictsEqual(stats_2, self._GetMetric('2013-01-04')))

    # Now write metrics at a custom timestamp. By default, they are written at noon.
    self.assertIsNone(self._GetMetric('2013-01-01', h=12, m=1))

    new_stats2 = {'2013-01-01': stats_3,
                  '2013-01-02': stats_2,
                  '2013-01-03': stats_1,
                  '2013-01-04': stats_1,
                 }
    hms = logs_util.kDailyMetricsTimeByLogType['active_users']
    self._RunAsync(logs_util.UpdateMetrics, self._client, new_stats2, dry_run=False, hms_tuple=hms)
    self.assertTrue(_DotDictsEqual(self._GetMetric('2013-01-01', h=12, m=1), stats_3))
    self.assertTrue(_DotDictsEqual(self._GetMetric('2013-01-02', h=12, m=1), stats_2))
    self.assertTrue(_DotDictsEqual(self._GetMetric('2013-01-03', h=12, m=1), stats_1))
    self.assertTrue(_DotDictsEqual(self._GetMetric('2013-01-04', h=12, m=1), stats_1))

    # Make sure the stats previously written at noon haven't changed.
    self.assertTrue(_DotDictsEqual(stats_1, self._GetMetric('2013-01-01')))
    self.assertTrue(_DotDictsEqual(self._GetMetric('2013-01-02'),
                                   DotDict({'itunes': {'downloads': {'US': 1, 'UK': 2, 'FR': 3}}})))
    self.assertTrue(_DotDictsEqual(self._GetMetric('2013-01-03'),
                                   DotDict({'itunes': {'downloads': {'US': 5, 'DE': 6},
                                                       'updates': {'US': 4, 'UK': 5, 'FR': 6}}})))
    self.assertTrue(_DotDictsEqual(stats_2, self._GetMetric('2013-01-04')))
