# -*- coding: utf-8 -*-
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""APNs testing.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import base64
import json
import os
import unittest

from collections import deque
from tornado import escape, options
from viewfinder.backend.services.apns import APNS
from viewfinder.backend.base import base_options  # imported for option defs
from viewfinder.backend.base import secrets
from viewfinder.backend.base.testing import async_test_timeout, BaseTestCase
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.services.apns_util import CreateMessage


@unittest.skip("needs apns credentials")
@unittest.skipIf('NO_NETWORK' in os.environ, 'no network')
class _FeedbackHandler(object):
  """Invokes waiting callbacks with feedback."""
  def __init__(self):
    self._feedback = deque()
    self._waiters = deque()

  def HandleBadToken(self, push_token, timestamp=None, callback=None):
    if callback:
      callback()
    if self._waiters:
      self._waiters.popleft()(push_token)
    else:
      self._feedback.append(push_token)

  def WaitForFeedback(self, callback):
    if self._feedback:
      callback(self._feedback.popleft())
    else:
      self._waiters.append(callback)


class APNSTestCase(BaseTestCase):
  def setUp(self):
    super(APNSTestCase, self).setUp()
    options.options.domain = 'goviewfinder.com'
    secrets.InitSecretsForTest()
    self._feedback = _FeedbackHandler()
    self._apns = APNS(environment='dev', feedback_handler=self._feedback.HandleBadToken)

  def tearDown(self):
    super(APNSTestCase, self).tearDown()

  @async_test
  def testInput(self):
    """Verify obviously bad inputs fail."""
    self.assertRaises(TypeError, self._apns.Push, '0', None, 1, None, None, None, None)
    self.stop()

  @async_test_timeout(timeout=30)
  def testBadToken(self):
    """Sends a bad token to apns and verifies feedback handler."""
    BAD_TOKEN = base64.b64encode('0' * 32)  # a 32 byte string, encoded as b64
    self.assertEqual(len(BAD_TOKEN), 44)

    def _OnFeedback(push_token):
      self.assertEqual('apns-dev:%s' % BAD_TOKEN, push_token)
      self.stop()

    self._feedback.WaitForFeedback(_OnFeedback)
    self._apns.Push(BAD_TOKEN, None, 1, None, None, None, None)

  def testUnicodeMessage(self):
    """Verify that passing Unicode fields to CreateMessage works."""
    CreateMessage(u'u1fGNVUPy9ZWquLzCmgBj+11SWbqHqGrICwr7rk+qWE="', alert=u'foo bar朋友你好ààà',
                  badge=0, sound=u'default', extra={u'foo': u'bar'})

  def testAlertTruncation(self):
    """Verify that long messages are truncated properly."""
    alert = '朋友你好朋友你好朋友你好朋友你好朋友你好朋友你好朋友你好朋友你好朋友你好朋友你好朋友你好朋友你好朋友你好朋友' \
            '你好朋友你好朋友你好朋友你好朋友你好朋友你好朋友你好朋友你好朋友你好'
    msg = CreateMessage('u1fGNVUPy9ZWquLzCmgBj+11SWbqHqGrICwr7rk+qWE="', alert=alert, badge=0,
                        sound='default', extra={'foo': 'bar'})

    truncated = alert[:171] + '…'
    self.assertTrue(truncated in msg)

    self.assertRaises(ValueError, CreateMessage, 'u1fGNVUPy9ZWquLzCmgBj+11SWbqHqGrICwr7rk+qWE=',
                      alert=alert, badge=0, sound='default', allow_truncate=False)

  def testTruncateAlert(self):
    """Unit test alert truncation."""
    from viewfinder.backend.services.apns_util import _TruncateAlert

    def _TestTruncate(alert, max_bytes, expected):
      truncated = _TruncateAlert(alert, max_bytes)
      truncated_json = escape.utf8(json.dumps(escape.recursive_unicode(truncated), ensure_ascii=False)[1:-1])
      self.assertEqual(truncated_json, expected)
      self.assertTrue(len(truncated_json) <= max_bytes)

    # Test ASCII characters (1 byte in UTF-8).
    _TestTruncate('the quick brown fox', 12, 'the quick…')
    _TestTruncate('abcd', 4, 'abcd')
    _TestTruncate('abcd', 3, '…')
    _TestTruncate('abc', 3, 'abc')
    _TestTruncate('ab', 3, 'ab')
    _TestTruncate('a', 3, 'a')
    _TestTruncate('', 3, '')

    # Test accented characters (2 bytes in UTF-8).
    _TestTruncate('ààà', 6, 'ààà')
    _TestTruncate('ààà', 5, 'à…')
    _TestTruncate('ààà', 4, '…')
    _TestTruncate('ààà', 3, '…')

    # Test Chinese characters (3 bytes in UTF-8).
    _TestTruncate('朋友你好', 12, '朋友你好')
    _TestTruncate('朋友你好', 11, '朋友…')
    _TestTruncate('朋友你好', 10, '朋友…')
    _TestTruncate('朋友你好', 9, '朋友…')

    # Test surrogate characters (4 bytes in UTF-8).
    _TestTruncate(u'\U00010000\U00010000', 8, escape.utf8(u'\U00010000\U00010000'))
    _TestTruncate(u'\U00010000\U00010000', 7, escape.utf8(u'\U00010000…'))
    _TestTruncate(u'\U00010000\U00010000', 6, '…')
    _TestTruncate(u'\U00010000\U00010000', 5, '…')
    _TestTruncate(u'\U00010000\U00010000', 4, '…')
    _TestTruncate(u'\U00010000\U00010000', 3, '…')

    # Test chars that JSON escapes.
    _TestTruncate('\b\f\n\\\r\t\"', 14, '\\b\\f\\n\\\\\\r\\t\\"')
    _TestTruncate('\b\f\n\\\r\t\"', 13, '\\b\\f\\n\\\\\\r…')
    _TestTruncate('\b\f\n\\\r\t\"', 12, '\\b\\f\\n\\\\…')
    _TestTruncate('\b\f\n\\\r\t\"', 11, '\\b\\f\\n\\\\…')
    _TestTruncate('\\\\', 4, '\\\\\\\\')
    _TestTruncate('\\\\', 3, '…')
    _TestTruncate('\x00\x01', 12, '\\u0000\\u0001')
    _TestTruncate('\x00\x01', 11, '\\u0000…')
    _TestTruncate('\x00\x01', 10, '\\u0000…')

    # Test errors.
    self.assertRaises(AssertionError, _TruncateAlert, 'a', 0)
