# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Manual push notification facility.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

from tornado import options
from viewfinder.backend.services.apns import APNS
from viewfinder.backend.services.push_notification import PushNotification
from viewfinder.backend.www import www_main

options.define('token', default=None, help='push notification token (e.g. "apns-prod:(.*)")')
options.define('badge', default=1, help='badge value (integer)')


def _Start(callback):
  """Allows manual push notifications."""
  assert options.options.token, 'must specify a push notification token'
  assert options.options.badge is not None, 'must specify a badge value'
  PushNotification.Push(options.options.token, badge=int(options.options.badge))

if __name__ == '__main__':
  www_main.InitAndRun(_Start)
