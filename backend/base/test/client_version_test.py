# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Test versioning.
"""

import unittest

from viewfinder.backend.base.client_version import ClientVersion


__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

class ClientVersionTestCase(unittest.TestCase):
  def testParsing(self):
    version = ClientVersion(None)
    self.assertFalse(version.IsValid())
    version = ClientVersion('')
    self.assertFalse(version.IsValid())
    version = ClientVersion('1')
    self.assertFalse(version.IsValid())

    version = ClientVersion('1.3.0')
    self.assertTrue(version.IsValid())
    self.assertFalse(version.IsDev())
    self.assertFalse(version.IsTestFlight())
    self.assertTrue(version.IsAppStore())

    version = ClientVersion('1.3.0.dev')
    self.assertTrue(version.IsValid())
    self.assertTrue(version.IsDev())
    self.assertFalse(version.IsTestFlight())
    self.assertFalse(version.IsAppStore())

    version = ClientVersion('1.3.0.adhoc')
    self.assertTrue(version.IsValid())
    self.assertFalse(version.IsDev())
    self.assertTrue(version.IsTestFlight())
    self.assertFalse(version.IsAppStore())

  def testCompare(self):
    version = ClientVersion('1.6.0.40')

    self.assertTrue(version.LT('1.7'))
    self.assertTrue(version.LT('1.6.1'))
    self.assertTrue(version.LT('1.6.0.41'))
    self.assertFalse(version.LT('1.6.0.40'))
    self.assertFalse(version.LT('1.6'))

    self.assertTrue(version.LE('1.7'))
    self.assertTrue(version.LE('1.6.1'))
    self.assertTrue(version.LE('1.6.0.41'))
    self.assertTrue(version.LE('1.6.0.40'))
    self.assertFalse(version.LE('1.6'))

    self.assertFalse(version.EQ('1.6.0'))
    self.assertTrue(version.EQ('1.6.0.40'))

    self.assertTrue(version.GT('1.5'))
    self.assertTrue(version.GT('1.6.0'))
    self.assertTrue(version.GT('1.6.0.39'))
    self.assertFalse(version.GT('1.6.0.40'))
    self.assertFalse(version.GT('1.6.0.41'))

    self.assertTrue(version.GE('1.5'))
    self.assertTrue(version.GE('1.6.0'))
    self.assertTrue(version.GE('1.6.0.39'))
    self.assertTrue(version.GE('1.6.0.40'))
    self.assertFalse(version.GE('1.6.0.41'))
