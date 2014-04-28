# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Ping handler.

Logs ping request and response to INFO.

May send back a message to the client based on the value of the fields in the ping request (eg: notice of
newer version).

The message is composed of:
- title: required string: displayed on the app dashboard
- body: optional string: displayed if the title box is expanded
- link: optional string: link is opened if the title box is clicked
- identifier: required string: if the identifier matches the last one received by the client, the message
  is not displayed
- severity: required string: one of:
  - SILENT: the message is not displayed, but still saved by the client (useful to override any previous message)
  - INFO: the message is displayed on the dashboard (orange? green?)
  - ATTENTION: the message is displayed on the dashboard (red? orange?)
  - DISABLE_NETWORK: the message is displayed on the dashboard (red) and requests to the backend are disallowed
    (except for periodic pings).

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import json
import logging

from viewfinder.backend.base import util
from viewfinder.backend.base.client_version import ClientVersion
from viewfinder.backend.www import base, json_schema, www_util

class PingHandler(base.BaseHandler):
  """Handles ping requests:
  - logs json request
  - optionally sends back (and logs) an informational message based on the request parameters
  """
  def check_xsrf_cookie(self):
    pass

  def post(self):
    def _BuildMessage(msg):
      device = msg.get('device', None)
      if not device:
        return None

      app_version = ClientVersion(device.get('version', None))
      if not app_version.IsValid():
        return None

      if app_version.LT('1.6.0'):
        # Client versions before 1.6.0 don't know about a ping response.
        return None

      if app_version.IsAppStore():
        # For now, never return a message for app store versions. We need more real-world testing first.
        return None

      # Disable "latest dev" message, we accidentally pushed a dev build to the app store.
      return None

      # This particular logic is used in ping_test.py
      if app_version.GE('1.6.0.41') and app_version.IsDev():
        return {'title': 'congrats on running %s' % app_version.version,
                'body': 'you have the latest development version',
                'link': 'http://appstore.com/minetta/viewfinder',
                'identifier': 'latest-dev-%s' % app_version.version,
                'severity': 'INFO'
                }

      return None

    # Verify application/json; (415: Unsupported Media Type).
    content_type = self.request.headers['Content-Type']
    if not content_type.startswith('application/json'):
      self.send_error(status_code=415)
      return

    try:
      msg = self._LoadJSONRequest()
    except Exception:
      # We specifically do not want to log warning or error as spam could pollute our logs.
      # Log the repr to escape newlines.
      logging.info('ping FAIL: body: %r' % self.request.body[:256])
      self.send_error(status_code=400)
      return

    response_msg = _BuildMessage(msg)

    if response_msg:
      ping_response = {'message': response_msg}
      logging.info('ping OK: request: %s response: %s' % (json.dumps(msg), json.dumps(ping_response)))
      self.write(ping_response)
    else:
      logging.info('ping OK: request: %s response: {}' % json.dumps(msg))
      self.write('{}')

    # Access this property for the side effect of setting the _xsrf cookie.
    self.xsrf_token

    self.set_status(200)
    self.finish()
