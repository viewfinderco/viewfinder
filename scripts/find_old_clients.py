# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Look for clients running old versions and potentially notify using APNS.

Scan the Device table for devices running old versions.
Devices must have a push_token. If the user has another device with a version > version_le, don't notify.

Filtering:
- version_le: find devices running a version less than, or equal to this. (eg: --version_le=1.5.0)

Notification:
- notification_message: send this message to matching devices. Prompts before sending.
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import logging
import sys
import time

from collections import defaultdict, Counter
from functools import partial
from tornado import gen, ioloop, options
from viewfinder.backend.base import client_version, constants, main, util
from viewfinder.backend.db import db_client
from viewfinder.backend.db.device import Device

options.options.define('version_le', default=None, help='Look for devices running a client version <= this')
options.options.define('notification_message', default=None, help='Message to send to devices (no push if None)')

def IsValidDevice(device):
  if not device.version:
    # No version information: skip. This is fairly rare.
    logging.error('no client version for device: %r' % device)
    return False

  if not device.push_token or not device.alert_user_id:
    return False

  if device.alert_user_id != device.user_id:
    logging.error('mismatched alert_user_id and user_id for device: %r' % device)
    return False

  return True

@gen.engine
def Start(callback):
  client = db_client.DBClient.Instance()

  version_limit = client_version.ClientVersion(options.options.version_le) if options.options.version_le else None

  time_filter = time.time() - constants.SECONDS_PER_DAY * 30
  total_devices = []
  last_key = None
  while True:
    devices, last_key = yield gen.Task(Device.Scan, client, None, excl_start_key=last_key)
    total_devices.extend(devices)
    if last_key is None:
      break
  logging.info('Total devices: %d' % len(total_devices))
  matching_devices = defaultdict(list)
  other_devices = defaultdict(list)
  num_matching_devices = 0
  for d in total_devices:
    if not IsValidDevice(d):
      continue
    if version_limit and version_limit.LT(d.version):
      other_devices[d.user_id].append(d)
      continue
    matching_devices[d.user_id].append(d)
    num_matching_devices += 1

  logging.info('Matching devices: %d (%d users)' % (num_matching_devices, len(matching_devices)))

  notify_devices = []
  for user_id in matching_devices.keys():
    if user_id not in other_devices:
      notify_devices.extend(matching_devices[user_id])

  logging.info('Devices to be notified: %d' % len(notify_devices))
  version_counter = Counter([d.version for d in notify_devices])
  logging.info('Devices per version: %r' % version_counter)

  def _APNSCallback(push_token, timestamp=None, callback=None):
    logging.info('Got callback for token: %s, timestamp %d' % (push_token, timestamp))
    callback()

  if options.options.notification_message and len(notify_devices) > 0:
    feedback = raw_input('You are about to notify %d devices, continue [yes NO]: ' % len(notify_devices))
    if feedback.lower() != 'yes':
      logging.info('Skipping notification')
      callback()
      return

    from viewfinder.backend.services.apns import APNS
    from viewfinder.backend.services.push_notification import PushNotification
    APNS.SetInstance('dev', APNS(environment='dev', feedback_handler=_APNSCallback))
    APNS.SetInstance('ent', APNS(environment='ent', feedback_handler=_APNSCallback))
    APNS.SetInstance('prod', APNS(environment='prod', feedback_handler=_APNSCallback))
    for d in notify_devices:
      PushNotification.Push(d.push_token, alert=options.options.notification_message)

    logging.info('Sending notifications')
    while not APNS.Instance('prod').IsIdle() or not APNS.Instance('dev').IsIdle() or not APNS.Instance('ent').IsIdle():
      yield gen.Task(ioloop.IOLoop.current().add_timeout, time.time() + 1)

    # Wait an extra second to ensure everything has been dispatched.
    yield gen.Task(ioloop.IOLoop.current().add_timeout, time.time() + 1)
    logging.info('Notifications sent')

  callback()

if __name__ == '__main__':
  sys.exit(main.InitAndRun(Start))
