# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Test allocating asset ids from the server.
"""

__author__ = ['matt@emailscrubbed.com (Matt Tracy)']

from viewfinder.backend.base import util
from viewfinder.backend.db.user import User
from viewfinder.backend.www.test import service_base_test

class AllocateIdsTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(AllocateIdsTestCase, self).setUp()

    # October 21, 2015 4:29 PM
    util._TEST_TIME = 1445473740.0

  def tearDown(self):
    super(AllocateIdsTestCase, self).tearDown()
    util._TEST_TIME = None

  def testAllocateIds(self):
    asset_count = [0]

    def _GetAndVerifyIds(asset_types, expected):
      ids, timestamp = self._sendAllocateIdsRequest(asset_types)
      self.assertEqual(timestamp, util._TEST_TIME)
      self.assertEqual(len(ids), len(expected))
      for actual, expected in zip(ids, expected):
        self.assertEqual(actual, expected)

      user_obj = self._RunAsync(User.Query,
                                self._client,
                                self._user.user_id,
                                None)
      self.assertEqual(user_obj.asset_id_seq, 1 + len(asset_types) + asset_count[0])
      asset_count[0] += len(asset_types)

    _GetAndVerifyIds('a', [u'aeSUHBk70'])
    _GetAndVerifyIds('ao', [u'aeSUHBk71', u'o-VB'])
    _GetAndVerifyIds('cocop', [u'cKXVhn-73', u'o-VJ', u'cKXVhn-75', u'o-VR', u'peSUHBk77'])

  def testAllocateInvalidIds(self):
    self.assertRaisesHttpError(400, self._sendAllocateIdsRequest, 'aaf')

  def testAllocateUnsupportedIds(self):
    self.assertRaisesHttpError(400, self._sendAllocateIdsRequest, 'v')

  def testAllocateNoIds(self):
    result, timestamp = self._sendAllocateIdsRequest([]);
    self.assertEqual(len(result), 0)

  def _sendAllocateIdsRequest(self, asset_types):
    request_dict = { 'asset_types' : list(asset_types) }
    result = self._tester.SendRequest('allocate_ids', self._cookie, request_dict)
    return result['asset_ids'], result['timestamp']
