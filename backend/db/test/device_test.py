# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for device object.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import time
import unittest

from functools import partial

from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.device import Device

from base_test import DBBaseTestCase

class DeviceTestCase(DBBaseTestCase):
  @async_test
  def testInvalidToken(self):
    """Create a device with an invalid token and verify it is cleared
    on a push notification.
    """
    self._mobile_dev.push_token = 'invalid-scheme:push-token'
    self._mobile_dev.Update(self._client, self._OnDeviceUpdate)

  def _OnDeviceUpdate(self):
    """Try pushing a notification to the device."""
    Device.PushNotification(self._client, self._user.user_id, 'test alert', 1,
                            partial(self._QueryUntilPushTokenNone, 0, self._mobile_dev))

  def _QueryUntilPushTokenNone(self, count, device):
    """Query the device until the push token has been cleared."""
    MAX_RETRIES = 5
    assert count < MAX_RETRIES
    if device.push_token is None:
      self.assertIsNone(device.alert_user_id)
      self.stop()
    else:
      query_cb = partial(Device.Query, self._client, self._user.user_id,
                         self._mobile_dev.device_id, None,
                         partial(self._QueryUntilPushTokenNone, count + 1))
      self.io_loop.add_timeout(time.time() + 0.100, query_cb)

  def testRepr(self):
    device = Device.CreateFromKeywords(user_id=1, device_id=1, os='iOS 6.0', name='My iPhone')
    self.assertIn('iOS 6.0', repr(device))
    self.assertNotIn('My iPhone', repr(device))

  def testCreate(self):
    self.assertRaises(KeyError, Device.CreateFromKeywords, user_id=1, device_id=2, device_uuid='foo')
    self.assertRaises(KeyError, Device.CreateFromKeywords, user_id=1, device_id=2, test_udid='bar')

    device = Device.Create(user_id=1, device_id=1, os='iOS 6.0', name='My iPhone', device_uuid='foo', test_udid='bar')
    self.assertIn('iOS 6.0', repr(device))
    self.assertNotIn('My iPhone', repr(device))
    self.assertNotIn('device_uuid', repr(device))
    self.assertNotIn('test_udid', repr(device))

    self.assertRaises(KeyError, device.UpdateFromKeywords, user_id=1, device_id=1,
                      os='iOS 6.1', device_uuid='foo', test_udid='bar')
    device.UpdateFields(user_id=1, device_id=1, os='iOS 6.1', device_uuid='foo')
    self.assertIn('iOS 6.1', repr(device))
    self.assertNotIn('My iPhone', repr(device))
    self.assertNotIn('device_uuid', repr(device))
    self.assertNotIn('test_udid', repr(device))
