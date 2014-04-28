#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Verifies properties of the device/operation queuing, restart,
and priority model.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import mock

from viewfinder.backend.base import util
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.lock import Lock
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.www.test import service_base_test

class OperationQueuingTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(OperationQueuingTestCase, self).setUp()
    self._validate = False

  @mock.patch.object(Lock, 'ABANDONMENT_SECS', 0.150)
  @mock.patch.object(Lock, 'LOCK_RENEWAL_SECS', 0.050)
  def testConcurrentOperations(self):
    """Verify N concurrent synchronous uploads with an additional operation
    manager also trying to scan and assume device operation queues.
    """
    N = 50
    with util.Barrier(self.stop) as b:
      for i in xrange(N):
        request_dict = {'activity': self._tester.CreateActivityDict(self._cookie),
                        'episode': self._CreateEpisodeDict(self._cookie),
                        'photos': [self._CreatePhotoDict(self._cookie)]}
        self._tester.SendRequestAsync('upload_episode', self._cookie, request_dict, b.Callback())
    self.wait()

    self.assertEqual(len(self._RunAsync(Episode.Scan, self._client, None)[0]), N)
    self.assertEqual(len(self._RunAsync(Photo.Scan, self._client, None)[0]), N)
