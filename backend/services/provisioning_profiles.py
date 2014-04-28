# Copyright 2013 Viewfinder Inc. All Rights Reserved
"""Testflight and Apple provisioning profile handling.
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import logging
import plistlib

class AppleProvisioningProfile(object):
  """Parser for apple provisioning profile plist file.
  Let all exceptions surface.
  """
  _FILE_START_TOKEN = '<?xml version="1.0" encoding="UTF-8"?>'
  _FILE_END_TOKEN = '</plist>'

  def __init__(self, filename):
    data = open(filename, 'r').read()

    # Extract the plist data from the file. It starts and ends with a bunch of garbage.
    start_index = data.index(self._FILE_START_TOKEN)
    stop_index = data.index(self._FILE_END_TOKEN, start_index + len(self._FILE_START_TOKEN))
    stop_index += len(self._FILE_END_TOKEN)

    plist_data = data[start_index:stop_index]
    self._provision_dict = plistlib.readPlistFromString(plist_data)

  def Name(self):
    return self._provision_dict['Name']

  def Devices(self):
    return self._provision_dict['ProvisionedDevices']


class TestFlightDevices(object):
  """Parser for testflight device list files.
  """
  _FIRST_LINE = 'deviceIdentifier\tdeviceName'

  def __init__(self, filename):
    data_list = open(filename, 'r').readlines()
    assert data_list[0].startswith(self._FIRST_LINE)

    self._device_list = [line.rstrip('\r\n').split('\t') for line in data_list[1:]]

  def Devices(self):
    return [d for (d,_) in self._device_list]
