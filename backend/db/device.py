# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Device description.

Describes a mobile device. Each device is tightly coupled to the user
id that first registers it. On registration, a device is assigned a
unique id from the id allocation table, which when combined with ids
assigned either locally by the device, or through each user's id_seq
column (in the case of access via the web application), provides a
stream of unique photo and episode ids.

A device is created and associated with a user on registration. If
registration is done on the web application, no device is stored with
the user cookie. In this case, photo ids are allocated through the
user's 'id_seq' sequence. With a mobile device, platform, os &
Viewfinder app version are all stored with the device. The device
itself manages the photo id sequence.

On a new registration, no device id is provided by the mobile app. It
is generated from the id allocation table and returned with a
successful authentication / authorization. However, the device does
provide information on app version, os & platform. On subsequent
registrations, the device id is provided along with any updates to
device information. The device id is stored in the secure user cookie
and is supplied on every subsequent request.

Each device may have an associated 'push_token' (ex. APNs token for
iOS devices). Every time the device is used and a registration request
is sent to viewfinder, the push_token--if applicable--is supplied and
the 'last_access' timestamp is updated. 'alert' and 'badge' are set
when notifications are generated in response to activity on a user
account. 'alert' is a message to display with a push notification;
'badge' is a number indicating the number of pending updates to the
user's account.

  Device: device information; mobile (iOS, Android, etc.) or web-app
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import time

from copy import deepcopy
from functools import partial
from tornado import gen
from viewfinder.backend.base import constants, util
from viewfinder.backend.db import db_client, vf_schema
from viewfinder.backend.db.id_allocator import IdAllocator
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.range_base import DBRangeObject
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.services.push_notification import PushNotification


@DBObject.map_table_attributes
class Device(DBRangeObject):
  """Viewfinder device data object."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.DEVICE)

  _ALLOCATION = 1
  _allocator = IdAllocator(id_type=_table.range_key_col.name, allocation=_ALLOCATION)

  _sys_obj_allocator = IdAllocator(id_type='system-object-id', allocation=_ALLOCATION)
  """Used to allocate ids for objects created by the system (e.g.
  viewpoint created during migration of user episodes).
  """

  _MAX_ALERT_DEVICES = 25
  """Maximum number of devices to which Viewfinder will push alerts."""

  SYSTEM = 0
  """Id of reserved system device, used when allocating system objects."""

  def __init__(self, user_id=None, device_id=None):
    super(Device, self).__init__()
    self.user_id = user_id
    self.device_id = device_id

  @classmethod
  def Create(cls, **device_dict):
    """Create a new Device object from 'device_dict'. Clears out 'device_uuid' and 'test_udid' if present."""
    create_dict = device_dict
    if 'device_uuid' in device_dict or 'test_udid' in device_dict:
      create_dict = deepcopy(device_dict)
      create_dict.pop('device_uuid', None)
      create_dict.pop('test_udid', None)
    return cls.CreateFromKeywords(**create_dict)

  def UpdateFields(self, **device_dict):
    """Update a Device object from 'device_dict'. Clears out 'device_uuid' and 'test_udid' if present."""
    create_dict = device_dict
    if 'device_uuid' in device_dict or 'test_udid' in device_dict:
      create_dict = deepcopy(device_dict)
      create_dict.pop('device_uuid', None)
      create_dict.pop('test_udid', None)
    self.UpdateFromKeywords(**create_dict)

  @classmethod
  def ShouldScrubColumn(cls, name):
    return name == 'name'

  @classmethod
  @gen.coroutine
  def Register(cls, client, user_id, device_dict, is_first=True):
    """Registers a new device or update an existing device, using the fields in "device_dict".
    If "is_first" is true, then this is the first mobile device to be registered for this
    user.
    """
    assert 'device_id' in device_dict, device_dict

    device = yield gen.Task(Device.Query,
                            client,
                            user_id,
                            device_dict['device_id'],
                            None,
                            must_exist=False)
    if device is None:
      device = Device.Create(user_id=user_id, timestamp=util.GetCurrentTimestamp(), **device_dict)
    else:
      device.UpdateFields(**device_dict)

    yield gen.Task(device.Update, client)

    # If this is the first mobile device to be registered, then turn turn off email alerting
    # and turn on full push alerting to mobile devices.
    if is_first:
      settings = AccountSettings.CreateForUser(user_id,
                                               email_alerts=AccountSettings.EMAIL_NONE,
                                               sms_alerts=AccountSettings.SMS_NONE,
                                               push_alerts=AccountSettings.PUSH_ALL)
      yield gen.Task(settings.Update, client)

    raise gen.Return(device)

  def Update(self, client, callback):
    """Call the base class "Update" method in order to persist modified
    columns to the db. But also ensure that this device has a unique
    push token; two Viewfinder devices might share the same push token
    if a phone has been given or sold to another person without
    re-installing the OS. Also, ensure that the device is added to the
    secondary index used for alerting (alert_user_id), for fast
    enumeration of all devices that need to be alerted for a particular
    user.
    """
    def _DoUpdate():
      super(Device, self).Update(client, callback)

    def _OnQueryByPushToken(devices):
      """Disable alerts for all other devices."""
      with util.Barrier(_DoUpdate) as b:
        for device in devices:
          if device.device_id != self.device_id:
            device.push_token = None
            device.alert_user_id = None
            super(Device, device).Update(client, b.Callback())

    # Each time the device is updated, update the last_access field.
    self.last_access = util.GetCurrentTimestamp()

    if self._IsModified('push_token'):
      if self.push_token is None:
        self.alert_user_id = None
        _DoUpdate()
      else:
        # Ensure that the device will be alerted.
        self.alert_user_id = self.user_id

        query_expr = ('device.push_token={t}', {'t': self.push_token})
        Device.IndexQuery(client, query_expr, None, _OnQueryByPushToken)
    else:
      _DoUpdate()

  @classmethod
  def PushNotification(cls, client, user_id, alert, badge, callback,
                       exclude_device_id=None, extra=None, sound=None):
    """Queries all devices for 'user'. Devices with 'push_token'
    set are pushed notifications via the push_notification API.
    NOTE: currently, code path is synchronous, but the callback
      is provided in case that changes.

    If specified, 'exclude_device_id' will exclude a particular device
    from the set to which notifications are pushed. For example, the
    device which is querying notifications when the badge is set to 0.
    """
    def _OnQuery(devices):
      with util.Barrier(callback) as b:
        now = util.GetCurrentTimestamp()
        for device in devices:
          if device.device_id != exclude_device_id:
            token = device.push_token
            assert token, device
            try:
              PushNotification.Push(token, alert=alert, badge=badge, sound=sound, extra=extra)
            except TypeError as e:
              logging.error('bad push token %s', token)
              Device._HandleBadPushToken(client, token, time.time(), b.Callback())
            except Exception as e:
              logging.warning('failed to push notification to user %d: %s', user_id, e)
              raise

    # Find all devices owned by the user that need to be alerted.
    Device.QueryAlertable(client, user_id, _OnQuery)

  @classmethod
  def QueryAlertable(cls, client, user_id, callback, limit=_MAX_ALERT_DEVICES):
    """Returns all devices owned by the given user that can be alerted."""
    query_expr = ('device.alert_user_id={u}', {'u': user_id})
    Device.IndexQuery(client, query_expr, None, callback, limit=limit)

  @classmethod
  @gen.coroutine
  def MuteAlerts(cls, client, user_id):
    """Turn off alerts to all devices owned by "user_id"."""
    @gen.coroutine
    def _VisitDevice(device):
      device.alert_user_id = None
      yield gen.Task(device.Update, client)

    yield gen.Task(Device.VisitRange, client, user_id, None, None, _VisitDevice)

  @classmethod
  def FeedbackHandler(cls, client):
    """Returns a callback which deals appropriately with device push
    tokens which have failed delivery.
    """
    return partial(Device._HandleBadPushToken, client)

  @classmethod
  def AllocateSystemObjectId(cls, client, callback):
    """Generate a unique id to be used for identifying system-generated
    objects. Return the new id.
    """
    Device._sys_obj_allocator.NextId(client, callback)

  @classmethod
  def _HandleBadPushToken(cls, client, push_token, timestamp=None, callback=None):
    """Callback in the event of failed delivery of push notification.
    'push_token' is queried via the secondary index on Device. Timestamp
    is the time at which the delivery failed. If the device attached to
    the failed push_token has 'last_access' > timestamp, ignore failure;
    otherwise, clear the push token and update.
    """
    def _OnQueryByPushToken(devices):
      if not devices:
        logging.warning('unable to locate device for push token: %s' % push_token)
        return
      for device in devices:
        if device.last_access is None or device.last_access < timestamp:
          logging.info('unsetting push_token for device %s' % device)
          device.push_token = None
          device.Update(client, callback if callback else util.NoCallback)

    query_expr = ('device.push_token={t}', {'t': push_token})
    Device.IndexQuery(client, query_expr, None, _OnQueryByPushToken)

  @classmethod
  def UpdateOperation(cls, client, callback, user_id, device_id, device_dict):
    """Updates device metadata."""
    def _OnQuery(device):
      device.UpdateFields(**device_dict)
      device.Update(client, callback)

    Device.Query(client, user_id, device_id, None, _OnQuery)
