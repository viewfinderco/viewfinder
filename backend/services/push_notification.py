# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""PushNotification MUX class. Services Android and Apple Push
Notifications.

  PushNotification
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import re

from viewfinder.backend.services.apns import APNS

class PushNotification(object):
  """Multiplexes to supported push notification services.
  """
  DEFAULT_SOUND = 'default'

  @staticmethod
  def Push(token, alert=None, badge=None, sound=None, expiry=None, extra=None, timestamp=None):
    """Parses push notification scheme from the token prefix and muxes
    the notification to the appropriate service. The token is in base64
    encoding ([a-zA-Z0-9+/=]).

    To get the default system sound, specify sound=PushNotification.DEFAULT_SOUND.
    """
    token_re = re.match(r'(apns|gcm)-(test|dev|ent|prod):([a-zA-Z0-9+/=]+)$', token)
    if not token_re:
      raise TypeError('invalid token: %s' % token)
    scheme = token_re.group(1)
    environment = token_re.group(2)
    push_token = token_re.group(3)

    if scheme == 'apns':
      APNS.Instance(environment).Push(push_token, alert, badge, sound, expiry, extra, timestamp)
    elif scheme == 'gcm':
      logging.info('Ignoring message meant for Android device: %s' % token)
