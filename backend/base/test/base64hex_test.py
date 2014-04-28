# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test encode/decode & maintenance of sort ordering for
base64hex encoding.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import random
import unittest

from viewfinder.backend.base import base64hex

class Base64HexTestCase(unittest.TestCase):
  def _RandomString(self):
    """Use a multiple of 6 for the length of the random string to ensure
    no padding is used in the encoded result.
    """
    length = random.randint(1, 10) * 6
    return ''.join([chr(random.randint(0,255)) for i in xrange(length)])

  def testEncodeDecode(self):
    num_trials = 1000
    for i in xrange(num_trials):
      s = self._RandomString()
      enc = base64hex.B64HexEncode(s)
      dec = base64hex.B64HexDecode(enc)
      self.assertEqual(s, dec)

  def testSortOrder(self):
    num_trials = 1000
    for i in xrange(num_trials):
      s1 = self._RandomString()
      s2 = self._RandomString()
      enc1 = base64hex.B64HexEncode(s1)
      enc2 = base64hex.B64HexEncode(s2)
      assert (s1 < s2) == (enc1 < enc2), 's1: %s, s2: %s, enc1: %s, enc2: %s' % (s1, s2, enc1, enc2)

  def testInvalidDecode(self):
    # Bad character
    self.assertRaises(TypeError, base64hex.B64HexDecode, '@')
    # Padding unnecessary.
    self.assertRaises(TypeError, base64hex.B64HexDecode, 'RV_3SDFO=')
    # Wrong amount of padding.
    self.assertRaises(TypeError, base64hex.B64HexDecode, 'RV_3SDFO==')

  def testKnownValues(self):
    # random strings of lengths 0-19
    data = [
      ('', ''),
      ('\xf9', 'yF=='),
      ('*\xc9', '9gZ='),
      ('T\xe7`', 'KDSV'),
      ('\xd2\xe9H\x0c', 'oi_72-=='),
      ('K\x84\x03\xeb\xe8', 'HsF2uyV='),
      ('\xebl\xe5\xa3\xa3\xf8', 'uqn_cuEs'),
      ('\x04\x88yR\xef\xa1M', '07WtJiyWIF=='),
      ('h\x8c\xa2\xb8h\x8c\x19v', 'P7mXi5XB5MN='),
      ('\x06\xc7_M\x19$\x88v\xb4', '0gSUIGZZX6Po'),
      ('\x1d\xab\xefI\xf7\x7fY\xa4\r\xe8', '6PjjHUSzLPFCu-=='),
      ('\xa4=\xe6\x1b\x00\xb1\r\xba\xcc\xca\xf4', 'd2ra5k1l2QfBmjF='),
      ('\xd7\xac\xa8\x97\xc2\x14\x16)\xf5"\xc8d', 'pumc_w7J4Xbp7gWZ'),
      ('\xab\xb3%\xd3&I\xfd\x9cc\x91\x17\xd7\xdf', 'evB_omO8zOlYZGUMrk=='),
      ('O\x8dO\xf4\nd\xc4\xf5W]\xdf\xd3\xa9\xfe', 'IspEx-dZlEKMMSzIeUs='),
      ("\xca\xdc\x8d'\xf0\xc5a\x93b\x1c@4\xdaC\x9a", 'mhmC8z24NOCX63-oqZDP'),
      ('\xe1\x00\xf7\xd8p\xef\x08v\xca\x9b\x81INPvu', 'sF2rq62j16Q9as48I_0qSF=='),
      ('8_\xaeS\xb9\xa9\xb7\x1e\x99\x8c\x06\xc7\xa9\xa2F\xb5\x0f', 'D4yiJvadhluOY-Q6eP85hFw='),
      ('"\xc3)!J H\x98\ro\xe1\\\xc2a\xc9\xe2v\xe8', '7gBd7JcVH8VCQy4Rka68sbQc'),
      ('\xe3\xb1?_\x97a<\xc5\xf5Cj\x86\xbeB\xc3F\xcc\x1ai', 'sv3zMtSWEBMpFqe5jZA2GgkPPF=='),
      ]
    for s, expected in data:
      try:
        self.assertEqual(base64hex.B64HexEncode(s), expected)
        self.assertEqual(base64hex.B64HexDecode(expected), s)
        self.assertEqual(base64hex.B64HexEncode(s, padding=False), expected.rstrip('='))
        self.assertEqual(base64hex.B64HexDecode(expected.rstrip('='), padding=False), s)
      except:
        logging.info("failed on %r", (s, expected))
        raise
