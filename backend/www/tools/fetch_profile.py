#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Fetch server profiles."""

__author__ = 'ben@emailscrubbed.com (Ben Darnell)'

import datetime
import logging
import os
from tornado import options
from viewfinder.backend.base import otp

options.define('api_host', 'www.viewfinder.co', help='hostname for admin service API')

def GetDataDir():
  return os.path.expanduser('~/.viewfinder.plop')

def FetchProfile(opener, api_host):
  url = 'https://%s/admin/profile' % api_host
  logging.info('fetching profile from %s; will take 60 seconds' % url)
  response = opener.open('https://%s/admin/profile' % api_host)
  if response.code != 200:
    raise Exception('request failed: %d' % response.code)
  data = response.read()
  logging.info('got profile')
  return data

def SaveProfile(data, api_host):
  datadir = GetDataDir()
  if not os.path.exists(datadir):
    os.makedirs(datadir)
  with open(os.path.join(datadir, api_host + '-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.plop'), 'w') as f:
    f.write(data)

def main():
  options.parse_command_line()

  opener = otp.GetAdminOpener(options.options.api_host)
  profile = FetchProfile(opener, options.options.api_host)
  SaveProfile(profile, options.options.api_host)

if __name__ == '__main__':
  main()
