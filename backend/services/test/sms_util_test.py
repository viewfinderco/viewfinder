# -*- coding: utf-8 -*-
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""SMS utility testing.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

from tornado import escape
from viewfinder.backend.base.testing import BaseTestCase
from viewfinder.backend.services.sms_util import ForceUnicode, IsOneSMSMessage, MAX_GSM_CHARS, MAX_UTF16_CHARS


class SMSUtilTestCase(BaseTestCase):
  _gsm_chars = '@£$¥èéùìòÇ\nØø\rÅå_ÆæßÉ !"#%&\'()*+,-./0123456789:;<=>?¡' + \
               'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà'

  def testForceUnicode(self):
    """Unit test the sms_util.ForceUnicode function."""
    self.assertFalse(ForceUnicode(''))
    self.assertFalse(ForceUnicode('abcXYZ123'))
    self.assertFalse(ForceUnicode('朋朋朋'))
    self.assertFalse(ForceUnicode('1朋è朋A朋-'))
    self.assertFalse(ForceUnicode('朋Σ'))
    self.assertFalse(ForceUnicode('[Π]'))

    for ch in u'¤ΔΦΓΛΩΠΨΣΘΞ':
      self.assertTrue(ForceUnicode(ch))
      self.assertTrue(ForceUnicode(escape.utf8(ch)))

    self.assertTrue(ForceUnicode('123¤abcèéùìòäöñüà'))
    self.assertTrue(ForceUnicode('¤ΔΦΓΛΩΠΨΣΘΞ'))
    self.assertFalse(ForceUnicode(SMSUtilTestCase._gsm_chars))

  def testIsOneSMSMessage(self):
    """Unit test the sms_util.IsOneSMSMessage function."""
    self.assertTrue(IsOneSMSMessage(''))
    self.assertTrue(IsOneSMSMessage('a' * MAX_GSM_CHARS))
    self.assertFalse(IsOneSMSMessage('a' * MAX_GSM_CHARS + 'a'))
    self.assertTrue(IsOneSMSMessage('Ñ' * MAX_GSM_CHARS))
    self.assertFalse(IsOneSMSMessage('Ñ' * MAX_GSM_CHARS + 'Ñ'))
    self.assertTrue(IsOneSMSMessage('\n' * MAX_GSM_CHARS))
    self.assertFalse(IsOneSMSMessage('\n' * MAX_GSM_CHARS + '\r'))
    self.assertTrue(IsOneSMSMessage('Ω' * MAX_UTF16_CHARS))
    self.assertFalse(IsOneSMSMessage('Ω' * MAX_UTF16_CHARS + '-'))
    self.assertTrue(IsOneSMSMessage('[' * MAX_UTF16_CHARS))
    self.assertFalse(IsOneSMSMessage('[' * MAX_UTF16_CHARS + '1'))
    self.assertTrue(IsOneSMSMessage('朋' * MAX_UTF16_CHARS))
    self.assertFalse(IsOneSMSMessage('朋' * MAX_UTF16_CHARS + '_'))
    self.assertTrue(IsOneSMSMessage('👍' * (MAX_UTF16_CHARS / 2)))
    self.assertFalse(IsOneSMSMessage('👍' * (MAX_UTF16_CHARS / 2) + '\n'))

    self.assertTrue(IsOneSMSMessage(SMSUtilTestCase._gsm_chars + '01234567890123456789012345678901234567890123'))
    self.assertFalse(IsOneSMSMessage(SMSUtilTestCase._gsm_chars + '012345678901234567890123456789012345678901234'))
