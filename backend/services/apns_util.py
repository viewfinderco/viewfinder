# -*- coding: utf-8 -*-
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Apple Push Notification service utilities.

Original copyright for this code: https://github.com/jayridge/apnstornado

  TokenToBinary(): converts a hex-encoded token into a binary value
  CreateMessage(): formats a binary APNs message from parameters
  ParseResponse(): parses APNs binary response for status & identifier
  ErrorStatusToString(): converts error status to error message
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import base64
import json
import struct
import time

from tornado import escape


_MAX_PAYLOAD_BYTES = 256
"""Maximum number of bytes in the APNS payload."""

_ELLIPSIS_BYTES = escape.utf8(u'…')
"""UTF-8 encoding of the Unicode ellipsis character."""


def TokenToBinary(token):
  return base64.b64decode(token)


def TokenFromBinary(bin_token):
  return base64.b64encode(bin_token)

def CreateMessage(token, alert=None, badge=None, sound=None,
                  identifier=0, expiry=None, extra=None, allow_truncate=True):
  token = TokenToBinary(token)
  if len(token) != 32:
    raise ValueError, u'Token must be a 32-byte binary string.'
  if (alert is not None) and (not isinstance(alert, (basestring, dict))):
    raise ValueError, u'Alert message must be a string or a dictionary.'
  if expiry is None:
    expiry = long(time.time() + 365 * 86400)

  # Start by determining the length of the UTF-8 encoded JSON with no alert text. This allows us to
  # determine how much space is left for the message.
  # 'content-available': 1 is necessary to trigger iOS 7's background download processing.
  aps = { 'alert' : '', 'content-available': 1 }
  if badge is not None:
    aps['badge'] = badge
  if sound is not None:
    aps['sound'] = sound

  data = { 'aps' : aps }
  if extra is not None:
    data.update(extra)

  # Create compact JSON representation with no extra space and no escaping of non-ascii chars (i.e. use
  # direct UTF-8 representation rather than "\u1234" escaping). This maximizes the amount of space that's
  # left for the alert text.
  encoded = escape.utf8(json.dumps(escape.recursive_unicode(data), separators=(',', ':'), ensure_ascii=False))
  bytes_left = _MAX_PAYLOAD_BYTES - len(encoded)
  if allow_truncate and isinstance(alert, basestring):
    alert = _TruncateAlert(alert, bytes_left)
  elif alert and len(escape.utf8(alert)) > bytes_left:
    raise ValueError, u'max payload(%d) exceeded: %d' % (_MAX_PAYLOAD_BYTES, len(escape.utf8(alert)))

  # Now re-encode including the alert text.
  aps['alert'] = alert
  encoded = escape.utf8(json.dumps(escape.recursive_unicode(data), separators=(',', ':'), ensure_ascii=False))
  length = len(encoded)
  assert length <= _MAX_PAYLOAD_BYTES, (encoded, length)

  return struct.pack('!bIIH32sH%(length)ds' % { 'length' : length },
                     1, identifier, expiry,
                     32, token, length, encoded)


def ParseResponse(bytes):
  if len(bytes) != 6:
    raise ValueError, u'response must be a 6-byte binary string.'

  command, status, identifier = struct.unpack_from('!bbI', bytes, 0)
  if command != 8:
    raise ValueError, u'response command must equal 8.'

  return status, identifier, ErrorStatusToString(status)


def ErrorStatusToString(status):
  if status is 0:
    return 'No errors encountered'
  elif status is 1:
    return 'Processing error'
  elif status is 2:
    return 'Missing device token'
  elif status is 3:
    return 'Missing topic'
  elif status is 4:
    return 'Missing payload'
  elif status is 5:
    return 'Invalid token size'
  elif status is 6:
    return 'Invalid topic size'
  elif status is 7:
    return 'Invalid payload size'
  elif status is 8:
    return 'Invalid token'
  elif status is 255:
    return 'None (unknown)'
  else:
    return ''


def _TruncateAlert(alert, max_bytes):
  """Converts the alert text to UTF-8 encoded JSON format, which is how
  the alert will be stored in the APNS payload. If the number of
  resulting bytes exceeds "max_bytes", then truncates the alert text
  at a Unicode character boundary, taking care not to split JSON
  escape sequences. Returns the truncated UTF-8 encoded alert text,
  including a trailing ellipsis character.
  """
  alert_json = escape.utf8(json.dumps(escape.recursive_unicode(alert), ensure_ascii=False))

  # Strip quotes added by JSON.
  alert_json = alert_json[1:-1]

  # Check if alert fits with no truncation.
  if len(alert_json) <= max_bytes:
    return escape.utf8(alert)

  # Make room for an appended ellipsis.
  assert max_bytes >= len(_ELLIPSIS_BYTES), 'max_bytes must be at least %d' % len(_ELLIPSIS_BYTES)
  max_bytes -= len(_ELLIPSIS_BYTES)

  # Truncate the JSON UTF8 string at a Unicode character boundary.
  truncated = alert_json[:max_bytes].decode('utf-8', errors='ignore')

  # If JSON escape sequences were split, then the truncated string may not be valid JSON. Keep
  # chopping trailing characters until the truncated string is valid JSON. It may take several
  # tries, such as in the case where a "\u1234" sequence has been split.
  while True:
    try:
      alert = json.loads(u'"%s"' % truncated)
      break
    except Exception:
      truncated = truncated[:-1]

  # Return the UTF-8 encoding of the alert with the ellipsis appended to it.
  return escape.utf8(alert) + _ELLIPSIS_BYTES
