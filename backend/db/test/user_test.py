# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Tests for User data object.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import sys
import time
import unittest

from functools import partial
from tornado import stack_context
from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.schema import Location
from viewfinder.backend.db import device, viewpoint
from viewfinder.backend.db.user import User

from base_test import DBBaseTestCase

class UserTestCase(DBBaseTestCase):
  def _CreateDefaultUser(self):
    return self._CreateUserAndDevice(user_dict={'user_id': 4,
                                                'given_name': 'Spencer',
                                                'family_name': 'Kimball',
                                                'email': 'spencer@emailscrubbed.com'},
                                     ident_dict={'key': 'Email:spencer@emailscrubbed.com',
                                                 'authority': 'Test'},
                                     device_dict=None)

  def testPartialCreate(self):
    """Creates a user with just a given name."""
    user_dict = {'user_id': 5, 'given_name': 'Spencer'}
    user, device = self._CreateUserAndDevice(user_dict=user_dict,
                                             ident_dict={'key': 'Email:spencer.kimball@foo.com',
                                                         'authority': 'Test'},
                                             device_dict=None)
    user._version = None
    user.signing_key = None
    user_dict['labels'] = [User.REGISTERED]
    user_dict['email'] = 'spencer.kimball@foo.com'
    user_dict['private_vp_id'] = 'v-k-'
    user_dict['webapp_dev_id'] = 3
    user_dict['asset_id_seq'] = 1
    self.assertEqual(user._asdict(), user_dict)

  def testRegister(self):
    """Creates a user via an OAUTH user dictionary."""
    u, dev = self._CreateUserAndDevice(user_dict={'user_id': 4,
                                                  'given_name': 'Spencer',
                                                  'family_name': 'Kimball',
                                                  'locale': 'en:US'},
                                       ident_dict={'key': 'Local:0_0.1',
                                                   'authority': 'Test'},
                                       device_dict={'device_id': 20,
                                                    'version': 'alpha-1.0',
                                                    'os': 'iOS 5.0.1',
                                                    'platform': 'iPhone 4S',
                                                    'country': 'US',
                                                    'language': 'en'})

    self.assertEqual(u.given_name, 'Spencer')
    self.assertEqual(u.family_name, 'Kimball')
    self.assertEqual(u.locale, 'en:US')

    self.assertTrue(dev.device_id > 0)
    self.assertTrue(dev.version, 'alpha-1.0')
    self.assertTrue(dev.os, 'iOS 5.0.1')
    self.assertTrue(dev.platform, 'iPhone 4S')
    self.assertTrue(dev.country, 'US')
    self.assertTrue(dev.language, 'en')

    # Try another registration with the same identity, but some different data and a different device.
    u2, dev2 = self._CreateUserAndDevice(user_dict={'user_id': 4,
                                                    'given_name': 'Brian',
                                                    'email': 'spencer@emailscrubbed.com'},
                                         ident_dict={'key': 'Local:0_0.1',
                                                     'authority': 'Test'},
                                         device_dict={'device_id': 21,
                                                      'version': 'alpha-1.0',
                                                      'os': 'Android 4.0.3',
                                                      'platform': 'Samsung Galaxy S'})

    # On a second registration, the user id shouldn't change, new information should be added, but
    # changed information should be ignored.
    self.assertEqual(u.user_id, u2.user_id)
    self.assertEqual(u2.given_name, 'Spencer')
    self.assertEqual(u2.email, 'spencer@emailscrubbed.com')

    self.assertTrue(dev.device_id != dev2.device_id)
    self.assertEqual(dev2.version, 'alpha-1.0')
    self.assertEqual(dev2.os, 'Android 4.0.3')
    self.assertEqual(dev2.platform, 'Samsung Galaxy S')

    # Try a registration with a different identity, same user. Use the original device, but change
    # the app version number.
    u3, dev3 = self._CreateUserAndDevice(user_dict={'user_id': u2.user_id,
                                                    'link': 'http://www.goviewfinder.com'},
                                         ident_dict={'key': 'Local:0_0.2',
                                                     'authority': 'Test'},
                                         device_dict={'device_id': dev.device_id,
                                                      'version': 'alpha-1.2'})

    self.assertEqual(u.user_id, u3.user_id)
    self.assertEqual(u3.link, 'http://www.goviewfinder.com')
    self.assertEqual(dev3.device_id, dev.device_id)
    self.assertEqual(dev3.os, dev.os)
    self.assertEqual(dev3.version, 'alpha-1.2')

    # Try a registration with an already-used identity.
    try:
      self._CreateUserAndDevice(user_dict={'user_id': 1000},
                                ident_dict={'key': 'Local:0_0.1',
                                            'authority': 'Test'},
                                device_dict={'device_id': dev3.device_id})
      assert False, 'third identity should have failed with already-in-use'
    except Exception as e:
      assert e.message.startswith('the identity is already in use'), e
      identities = self._RunAsync(u3.QueryIdentities, self._client)
      keys = [i.key for i in identities]
      self.assertTrue('Local:0_0.1' in keys)
      self.assertTrue('Local:0_0.2' in keys)

  def testRegisterViaWebApp(self):
    """Register from web application."""
    u, dev = self._CreateUserAndDevice(user_dict={'user_id': 4,
                                                  'name': 'Spencer Kimball'},
                                       ident_dict={'key': 'Test:1',
                                                   'authority': 'Test'},
                                       device_dict=None)
    self.assertEqual(u.name, 'Spencer Kimball')
    self.assertTrue(u.webapp_dev_id > 0)
    self.assertIsNone(dev)

  def testAddDevice(self):
    """Register with no mobile device, then add one."""
    u, dev = self._CreateUserAndDevice(user_dict={'user_id': 4,
                                                  'name': 'Spencer Kimball'},
                                       ident_dict={'key': 'Local:1',
                                                   'authority': 'Test'},
                                       device_dict=None)

    u2, dev2 = self._CreateUserAndDevice(user_dict={'user_id': 4},
                                         ident_dict={'key': 'Local:1',
                                                     'authority': 'Test'},
                                         device_dict={'device_id': 30})

    self.assertEqual(u2.user_id, u.user_id)
    self.assertIsNone(dev)
    self.assertIsNotNone(dev2)

  def testQueryUpdate(self):
    """Update a user."""
    u, d = self._CreateDefaultUser()

    # Now update the user.
    u2, d2 = self._CreateUserAndDevice(user_dict={'user_id': u.user_id,
                                                  'email': 'spencer.kimball@emailscrubbed.com'},
                                       ident_dict={'key': 'Email:spencer@emailscrubbed.com',
                                                   'authority': 'Facebook'},
                                       device_dict=None)
    self.assertEqual(u.email, u2.email)

  def testAllocateAssetIds(self):
    """Verify the per-device allocation of user ids."""
    self._RunAsync(User.AllocateAssetIds, self._client, self._user.user_id, 5)
    user = self._RunAsync(User.Query, self._client, self._user.user_id, None)
    self.assertEqual(user.asset_id_seq, 6)

    self._RunAsync(User.AllocateAssetIds, self._client, self._user.user_id, 100)
    user = self._RunAsync(User.Query, self._client, self._user.user_id, None)
    self.assertEqual(user.asset_id_seq, 106)

  def testPartialQuery(self):
    """Test query of partial row data."""
    u, dev = self._CreateDefaultUser()
    u2 = self._RunAsync(User.Query, self._client, u.user_id, ['given_name', 'family_name'])
    self.assertEqual(u2.email, None)
    self.assertEqual(u2.given_name, u.given_name)
    self.assertEqual(u2.family_name, u.family_name)

  def testMissing(self):
    """Test query of a non-existent user."""
    try:
      self._RunAsync(User.Query, self._client, 1L << 63, None)
      assert False, 'user query should fail with missing key'
    except Exception as e:
      pass
