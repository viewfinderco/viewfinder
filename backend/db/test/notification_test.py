# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for Notification & push notifications.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import time

from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.notification import Notification
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.op.op_context import EnterOpContext

from base_test import DBBaseTestCase


class NotificationTestCase(DBBaseTestCase):
  def testSimulateNotificationRaces(self):
    """Try to create notification with same id twice to simulate race condition."""
    notification = Notification(self._user.user_id, 100)
    notification.name = 'test'
    notification.timestamp = time.time()
    notification.sender_id = self._user.user_id
    notification.sender_device_id = 1
    notification.badge = 0
    notification.activity_id = 'a123'
    notification.viewpoint_id = 'v123'

    success = self._RunAsync(notification._TryUpdate, self._client)
    self.assertTrue(success)

    notification.badge = 1
    success = self._RunAsync(notification._TryUpdate, self._client)
    self.assertFalse(success)

  def testNotificationRaces(self):
    """Concurrently create many notifications to force races."""
    op = Operation(1, 'o123')
    with util.ArrayBarrier(self.stop) as b:
      for i in xrange(10):
        Notification.CreateForUser(self._client,
                                   op,
                                   1,
                                   'test',
                                   callback=b.Callback(),
                                   invalidate={'invalid': True},
                                   activity_id='a123',
                                   viewpoint_id='v%d' % i,
                                   inc_badge=True)
    notifications = self.wait()

    for i, notification in enumerate(notifications):
      self.assertEqual(notification.user_id, 1)
      self.assertEqual(notification.name, 'test')
      self.assertEqual(notification.activity_id, 'a123')
      self.assertEqual(notification.viewpoint_id, 'v%d' % i)
      self.assertEqual(notification.badge, i + 1)
