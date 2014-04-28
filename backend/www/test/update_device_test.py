# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Update device metadata.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import time

from copy import deepcopy
from functools import partial
from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.device import Device
from viewfinder.backend.www import json_schema
from viewfinder.backend.www.test import service_base_test


_DEVICE_DICT = {'version': 'alpha-1.0',
                'name': 'My Phone',
                'platform': 'Samsung Galaxy S',
                'os': 'Android 4.0',
                'push_token': 'gcm-prod:qQ+6V6u4SLHs133vMor7ck=',
                'country': 'US',
                'language': 'en'}


class UpdateDeviceTestCase(service_base_test.ServiceBaseTestCase):
  def testSimpleUpdate(self):
    """Update device properties of default mobile_dev."""
    self._tester.UpdateDevice(self._cookie, self._mobile_device.device_id, **_DEVICE_DICT)

  def testMinimumUpdate(self):
    """Test update with only device id."""
    self._tester.UpdateDevice(self._cookie, self._mobile_device.device_id)

  def testAddPushToken(self):
    """Test adding a push token after initial registration."""
    user, device_id = self._tester.RegisterGoogleUser({'name': 'Andy', 'email': 'kimball.andy@emailscrubbed.com',
                                                       'verified_email': True}, {})
    cookie = self._GetSecureUserCookie(user, device_id)
    self._tester.UpdateDevice(cookie, device_id, push_token=_DEVICE_DICT['push_token'])

  def testLastAccess(self):
    """Test update, then update again with increased access time."""
    self._tester.UpdateDevice(self._cookie, self._mobile_device.device_id)
    util._TEST_TIME += 1
    self._tester.UpdateDevice(self._cookie, self._mobile_device.device_id, **_DEVICE_DICT)

  def testDuplicateToken(self):
    """Update push token that is already in use by another device."""
    self._tester.UpdateDevice(self._cookie, self._mobile_device.device_id, **_DEVICE_DICT)

    user, device_id = self._tester.RegisterGoogleUser({'name': 'Andy', 'email': 'kimball.andy@emailscrubbed.com',
                                                       'verified_email': True}, {})
    cookie = self._GetSecureUserCookie(user, device_id)
    self._tester.UpdateDevice(cookie, device_id, push_token=_DEVICE_DICT['push_token'])

  def testDeviceIdMismatch(self):
    """Verify 400 bad auth cookie error on device id mismatch."""
    self.assertRaisesHttpError(400, self._tester.UpdateDevice, self._cookie, self._mobile_device.device_id + 1)


def _TestUpdateDevice(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test update_device
  service API call.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)
  device_dict = request_dict['device_dict']

  # Send update_device request.
  actual_dict = tester.SendRequest('update_device', user_cookie, request_dict)

  # Validate Device object.
  device_dict['user_id'] = user_id
  if 'push_token' in device_dict:
    device_dict['alert_user_id'] = user_id
  device_dict.pop('device_uuid', None)
  device_dict.pop('test_udid', None)
  device = validator.ValidateUpdateDBObject(Device, last_access=util._TEST_TIME, **device_dict)

  # Validate that only this device can use its push token.
  if 'push_token' in device_dict:
    predicate = lambda d: d.push_token == device_dict['push_token'] and d.device_id != device_dict['device_id']
    for other_device in validator.QueryModelObjects(Device, predicate=predicate):
      validator.ValidateUpdateDBObject(Device, user_id=other_device.user_id,
                                       device_id=other_device.device_id,
                                       push_token=None, alert_user_id=None)

  tester._CompareResponseDicts('update_device', user_id, request_dict, {}, actual_dict)
  return actual_dict
