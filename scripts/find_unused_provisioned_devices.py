# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Look for old and unused provisioned devices.

The input is one of:
--apple: Apple provisioning profile (plist file downloaded from developer.apple.com)
--testflight: TestFlight list of devices (select all users on testflightapp.com/dashboard/team/all/, then
              click Action and "Export iOS Devices"

Searches back through the processed "device details" logs (dump of all device_dict seen on the backends) and searches
for the latest timestamp at which each UDID was seen.

Each device UDID falls into one of three categories:
- missing: not found in the backend logs going back --search_days days (default 120)
- inactive: found, but not in the last --inactive_days days (default 60)
- active: found and seen in the last --inactive_days days (default 60)

The first two categories should probably be removed from the provisioning profile.
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import json
import logging
import os
import sys
import time

from tornado import gen, options
from viewfinder.backend.base import constants, main, util
from viewfinder.backend.logs import logs_util
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.storage import store_utils
from viewfinder.backend.services.provisioning_profiles import AppleProvisioningProfile, TestFlightDevices

options.define('apple', default=None, help='File path to the Apple Provisioning Profile')
options.define('testflight', default=None, help='File path to the TestFlight list of devices')
options.define('search_days', default=120, help='Search back this many days')
options.define('inactive_days', default=60, help='Devices not seen in this many days are considered inactive')

@gen.coroutine
def GetFileList(merged_store, marker):
  """Fetch the list of file names from S3."""
  base_path = 'processed_data/device_details/'
  marker = os.path.join(base_path, marker)
  file_list = yield gen.Task(store_utils.ListAllKeys, merged_store, prefix=base_path, marker=marker)
  file_list.sort()

  raise gen.Return(file_list)

@gen.coroutine
def GetUDIDTimestamps(merged_store, files):
  """Iterate over all files and build a dict of UDID -> last-seen-timestamp."""
  last_seen = {}
  for f in files:
    # Let exceptions surface.
    contents = yield gen.Task(merged_store.Get, f)
    dev_list = json.loads(contents)
    for entry in dev_list:
      timestamp = entry['timestamp']
      # The device dict is found under different keys based on the operation (ping vs update user/device)
      device_dict = entry['request'].get('device', entry['request'].get('device_dict', None))
      if not device_dict:
        # Some User.RegisterOperation entries do not have a device_dict.
        continue

      udid = device_dict.get('test_udid', None)
      if not udid:
        continue
      prev_seen = last_seen.get(udid, 0)
      if timestamp > prev_seen:
        last_seen[udid] = timestamp

  raise gen.Return(last_seen)

@gen.engine
def Start(callback):
  assert options.options.apple or options.options.testflight, \
         'You must specify exactly one of --apple or --testflight'
  assert options.options.search_days > 0

  # Exceptions are surfaced from both file parsers.
  if options.options.apple:
    assert not options.options.testflight, 'You must specify exactly one of --apple or --testflight'
    devices = AppleProvisioningProfile(options.options.apple).Devices()
  else:
    devices = TestFlightDevices(options.options.testflight).Devices()

  logs_paths = logs_util.ServerLogsPaths('viewfinder', 'full')
  merged_store = ObjectStore.GetInstance(logs_paths.MERGED_LOGS_BUCKET)
  # +1 because the start_date is exclusive.
  start_time = time.time() - (options.options.search_days + 1) * constants.SECONDS_PER_DAY
  start_date = util.TimestampUTCToISO8601(start_time)

  files = yield GetFileList(merged_store, start_date)

  logging.info('Looking for %d devices UDIDs in %d files' % (len(devices), len(files)))
  last_seen = yield GetUDIDTimestamps(merged_store, files)

  missing = []
  by_age = []
  valid = []
  now = time.time()
  for d in devices:
    if d not in last_seen:
      missing.append(d)
    else:
      age = (now - last_seen[d]) / constants.SECONDS_PER_DAY
      if age > options.options.inactive_days:
        by_age.append((age, d))
      else:
        valid.append(d)
  by_age.sort()

  print 'Devices still active: %d' % len(valid)

  print 'Devices not seen in %d days: %d' % (options.options.search_days, len(missing))
  if missing:
    print '  ' + '\n  '.join(missing)

  print 'Inactive devices (and days since last seen): %d' % len(by_age)
  for (age, device) in by_age:
    print '  %3d %s' % (age, device)

  callback()

if __name__ == '__main__':
  sys.exit(main.InitAndRun(Start))
