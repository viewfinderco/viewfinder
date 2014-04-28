# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests update_user method.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import time

from copy import deepcopy
from functools import partial
from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.user import User
from viewfinder.backend.services.email_mgr import EmailManager, TestEmailManager
from viewfinder.backend.services.sms_mgr import SMSManager, TestSMSManager
from viewfinder.backend.www.test import service_base_test


class UpdateUserTestCase(service_base_test.ServiceBaseTestCase):
  def testUpdateUser(self):
    """Update a user profile attribute and an account setting."""
    self._tester.UpdateUser(self._cookie, name='fake.name', given_name='fake.name',
                            settings_dict={'email_alerts': 'on_share_new'})

    response_dict = self._tester.QueryUsers(self._cookie, [self._user.user_id])
    self.assertEqual(response_dict['users'][0]['name'], 'fake.name')
    self.assertEqual(response_dict['users'][0]['private']['account_settings']['email_alerts'], 'on_share_new')

  def testSerialUpdateUser(self):
    """Call update_user, then call again with different values."""
    self._tester.UpdateUser(self._cookie, name='fake.name', given_name='fake.name',
                            settings_dict={'sms_alerts': 'on_share_new'})

    self._tester.UpdateUser(self._cookie, name='Andrew Kimball', given_name='Andrew', family_name='Kimball',
                            settings_dict={'sms_alerts': 'none'})

    response_dict = self._tester.QueryUsers(self._cookie, [self._user.user_id])
    self.assertEqual(response_dict['users'][0]['name'], 'Andrew Kimball')
    self.assertEqual(response_dict['users'][0]['private']['account_settings']['sms_alerts'], 'none')

  def testUpdateProfile(self):
    """Update only user profile attributes."""
    self._tester.UpdateUser(self._cookie,
                            name='Andy Kimball',
                            given_name='Andy',
                            family_name='Kimball',
                            picture='http://about.me/andrewkimball')

    response_dict = self._tester.QueryUsers(self._cookie, [self._user.user_id])
    self.assertEqual(response_dict['users'][0]['name'], 'Andy Kimball')

  def testUpdateSettings(self):
    """Update only account settings."""
    settings_dict = {'email_alerts': 'on_share_new',
                     'sms_alerts': 'on_share_new',
                     'push_alerts': 'all',
                     'storage_options': ['use_cloud', 'store_originals']}
    self._tester.UpdateUser(self._cookie, settings_dict=settings_dict)

    response_dict = self._tester.QueryUsers(self._cookie, [self._user.user_id])
    self.assertEqual(response_dict['users'][0]['private']['account_settings']['email_alerts'], 'on_share_new')

  def testUpdateWithFriends(self):
    """Update a user with friends."""
    # Turn off alert validation, since name of user changes during test, and this causes failure.
    self._skip_validation_for = ['Alerts']

    # Sharing creates friend relationships.
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 2)
    vp_id, ep_ids = self._tester.ShareNew(self._cookie, [(ep_id, ph_ids)], [])
    self._tester.AddFollowers(self._cookie, vp_id, [self._user2.user_id, self._user3.user_id, 'Local:identity1'])

    # Update only a profile attribute.
    self._tester.UpdateUser(self._cookie, picture='http://about.me/andrewkimball')

    # Update both a profile attribute and a setting.
    self._tester.UpdateUser(self._cookie, name='Andy', given_name='Andy',
                            settings_dict={'storage_options': []})

    # Update just a setting.
    self._tester.UpdateUser(self._cookie, settings_dict={'storage_options': ['use_cloud']})

    # Query friend's notifications.
    response_dict = self._tester.QueryNotifications(self._cookie2, 3, scan_forward=False)
    self.assertEqual(response_dict['notifications'][0]['name'], 'update_user')
    self.assertEqual(response_dict['notifications'][1]['name'], 'update_user')
    self.assertEqual(response_dict['notifications'][2]['name'], 'add_followers')

  def testUpdateNothing(self):
    """Update no profile attributes or settings."""
    self._tester.UpdateUser(self._cookie)

  def testUpdateAllSettings(self):
    """Update all settings."""
    self._tester.UpdateUser(self._cookie, settings_dict={'email_alerts': 'on_share_new'})
    self._tester.UpdateUser(self._cookie, settings_dict={'email_alerts': 'none'})
    self._tester.UpdateUser(self._cookie, settings_dict={'sms_alerts': 'on_share_new'})
    self._tester.UpdateUser(self._cookie, settings_dict={'sms_alerts': 'none'})
    self._tester.UpdateUser(self._cookie, settings_dict={'push_alerts': 'none'})
    self._tester.UpdateUser(self._cookie, settings_dict={'push_alerts': 'all'})
    self._tester.UpdateUser(self._cookie, settings_dict={'storage_options': ['use_cloud', 'store_originals']})

  def testUpdateEmptySettings(self):
    """Send empty settings dict."""
    self._tester.UpdateUser(self._cookie, settings_dict={})

  def testUpdateNames(self):
    """Update various combinations of names and make sure names are updated in concert."""
    self._tester.UpdateUser(self._cookie, name='Andy Kimball', given_name='Andy', family_name='Kimball')
    response_dict = self._tester.QueryUsers(self._cookie, [self._user.user_id])
    self.assertEqual(response_dict['users'][0]['name'], 'Andy Kimball')

    self._tester.UpdateUser(self._cookie, name='Andy', given_name='Andy')
    response_dict = self._tester.QueryUsers(self._cookie, [self._user.user_id])
    self.assertNotIn('family_name', response_dict['users'][0])

    self._tester.UpdateUser(self._cookie, picture='http://about.me/andrewkimball')
    response_dict = self._tester.QueryUsers(self._cookie, [self._user.user_id])
    self.assertEqual(response_dict['users'][0]['name'], 'Andy')

  def testOneSidedFriendship(self):
    """Test notifications sent to other users in one-sided "friendship"."""
    self._tester.UpdateFriend(self._cookie, user_id=self._user2.user_id, nickname='The Dude')
    self._tester.UpdateUser(self._cookie, name='Andy Kimball', given_name='Andy')
    response = self._tester.QueryNotifications(self._cookie2, limit=1, scan_forward=False)
    self.assertEqual(response['notifications'][0]['name'], 'update_user')

  def testAlerts(self):
    """Turn on/off alerts for a user and trigger operations which send alerts."""
    self._skip_validation_for = ['Alerts']
    emails = TestEmailManager.Instance().emails
    phone_numbers = TestSMSManager.Instance().phone_numbers
    self._CreateSimpleTestAssets()

    # Turn on email alerts and share with the user.
    self._tester.UpdateUser(self._cookie2, settings_dict={'email_alerts': 'on_share_new',
                                                          'sms_alerts': 'on_share_new'})
    vp_id, ep_ids = self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)], [self._user2.user_id])
    self._tester.PostComment(self._cookie, vp_id, 'a comment')
    assert len(emails[self._user2.email]) == 1, len(emails[self._user2.email])
    assert len(phone_numbers[self._user2.phone]) == 1, len(phone_numbers[self._user2.phone])

    # Turn email, SMS, and APNS alerts off and share with the user.
    self._tester.UpdateUser(self._cookie2, settings_dict={'email_alerts': 'none',
                                                          'sms_alerts': 'none',
                                                          'push_alerts': 'none'})
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)], [self._user2.user_id])
    assert len(emails[self._user2.email]) == 1, len(emails[self._user2.email])
    assert len(phone_numbers[self._user2.phone]) == 1, len(phone_numbers[self._user2.phone])

  def testMissingNameParts(self):
    """ERROR: Try to update invalid subset of user names."""
    self.assertRaisesHttpError(400, self._tester.UpdateUser, self._cookie, given_name='Andy')
    self.assertRaisesHttpError(400, self._tester.UpdateUser, self._cookie, family_name='Kimball')
    self.assertRaisesHttpError(400, self._tester.UpdateUser, self._cookie, name='Andy Kimball')

  def testInvalidSettings(self):
    """ERROR: Test invalid account settings."""
    settings_dict = {'unknown': 'unknown'}
    self.assertRaisesHttpError(400, self._tester.UpdateUser, self._cookie, settings_dict=settings_dict)

    settings_dict = {'email_alerts': 'unknown'}
    self.assertRaisesHttpError(400, self._tester.UpdateUser, self._cookie, settings_dict=settings_dict)

    settings_dict = {'storage_options': ['unknown']}
    self.assertRaisesHttpError(400, self._tester.UpdateUser, self._cookie, settings_dict=settings_dict)

    settings_dict = {'storage_options': 'use_cloud'}
    self.assertRaisesHttpError(400, self._tester.UpdateUser, self._cookie, settings_dict=settings_dict)

  def testInvalidRequests(self):
    """ERROR: Test invalid requests."""
    request_dict = {'account_settings': 'unknown'}
    self.assertRaisesHttpError(400, self._tester.SendRequest, 'update_user', self._cookie, request_dict)

    request_dict = {'unknown': 'unknown'}
    self.assertRaisesHttpError(400, self._tester.SendRequest, 'update_user', self._cookie, request_dict)

    # Try to set empty name.
    request_dict = {'name': ''}
    self.assertRaisesHttpError(400, self._tester.SendRequest, 'update_user', self._cookie, request_dict)

    # Try to update non-updatable user attribute.
    request_dict = {'email': 'kimball.andy@emailscrubbed.com'}
    self.assertRaisesHttpError(400, self._tester.SendRequest, 'update_user', self._cookie, request_dict)

  def testUpdatePassword(self):
    """Test update of user password."""
    # Need to create confirmed cookie.
    confirmed_cookie = self._GetSecureUserCookie(self._user, self._device_ids[0], confirm_time=util._TEST_TIME)

    # ------------------------------
    # Update password with other fields as well.
    # ------------------------------
    self.assertIsNone(self._RunAsync(User.Query, self._client, self._user.user_id, None).pwd_hash)
    self._tester.UpdateUser(confirmed_cookie, password='supersecure', name='Jimmy John', given_name='user1')
    self.assertIsNotNone(self._RunAsync(User.Query, self._client, self._user.user_id, None).pwd_hash)
    self._tester.LoginViewfinderUser({'email': self._user.email, 'password': 'supersecure'}, None)

    # ------------------------------
    # Update only password (a notification should be created for the user himself, but not for friend).
    # ------------------------------
    # Share with another user to create friend.
    self._CreateSimpleTestAssets()
    self._ShareSimpleTestAssets([self._user2.user_id])
    self._tester.UpdateUser(confirmed_cookie, password='foobarbaz')

    response_dict = self._tester.QueryNotifications(confirmed_cookie, limit=1, scan_forward=False)
    self.assertEqual(response_dict['notifications'][0]['name'], 'update_user')
    response_dict = self._tester.QueryNotifications(self._cookie2, limit=1, scan_forward=False)
    self.assertNotEqual(response_dict['notifications'][0]['name'], 'update_user')

    self._tester.LoginViewfinderUser({'email': self._user.email, 'password': 'foobarbaz'}, None)

    # ------------------------------
    # Update password using matching old_password.
    # ------------------------------
    self._tester.UpdateUser(self._cookie, password='password', old_password='foobarbaz')
    self._tester.LoginViewfinderUser({'email': self._user.email, 'password': 'password'}, None)

    # ------------------------------
    # Set new password where password didn't previously exist.
    # ------------------------------
    self._tester.UpdateUser(self._cookie3, password='new password')
    self._tester.LoginViewfinderUser({'email': self._user3.email, 'password': 'new password'}, None)

    # ------------------------------
    # ERROR: Try to set a password that is too short.
    # ------------------------------
    self.assertRaisesHttpError(400, self._tester.UpdateUser, confirmed_cookie, password='1234567')
    self._tester.LoginViewfinderUser({'email': self._user.email, 'password': 'password'}, None)

    # ------------------------------
    # ERROR: Try to update password without a recently confirmed cookie.
    # ------------------------------
    self.assertRaisesHttpError(403, self._tester.UpdateUser, self._cookie, password='foobarbaz')
    self._tester.LoginViewfinderUser({'email': self._user.email, 'password': 'password'}, None)

    # ------------------------------
    # ERROR: Try to update password with old_password that doesn't match.
    # ------------------------------
    self.assertRaisesHttpError(403,
                               self._tester.UpdateUser,
                               self._cookie,
                               password='a very long password this is for sure',
                               old_password='unknownpwd')
    self._tester.LoginViewfinderUser({'email': self._user.email, 'password': 'password'}, None)


def _TestUpdateUser(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test update_user
  service API call.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  # Send update_user request.
  actual_dict = tester.SendRequest('update_user', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # Validate updates to the User object.
  user_dict = deepcopy(request_dict)
  user_dict['user_id'] = user_id
  user_dict.pop('headers', None)
  user_dict.pop('account_settings', None)
  user_dict.pop('old_password', None)

  # Get pwd_hash and salt from actual user.
  actual_user = tester._RunAsync(User.Query, validator.client, user_id, None)
  if user_dict.pop('password', None):
    user_dict['pwd_hash'] = actual_user.pwd_hash
    user_dict['salt'] = actual_user.salt

  # If any name was set, all names should have been set.
  for name_attr in ['name', 'given_name', 'family_name']:
    if name_attr in user_dict:
      user_dict.setdefault('name', None)
      user_dict.setdefault('given_name', None)
      user_dict.setdefault('family_name', None)

  validator.ValidateUpdateDBObject(User, **user_dict)

  # Validate updates to the AccountSettings object.
  if request_dict.get('account_settings', None):
    settings = request_dict['account_settings']
    settings['settings_id'] = 'us:%d' % user_id
    settings['group_name'] = AccountSettings.GROUP_NAME
    settings['user_id'] = user_id
    validator.ValidateUpdateDBObject(AccountSettings, **settings)

  # Validate notifications.
  if any(key not in ['headers', 'account_settings', 'user_id', 'password', 'old_password']
         for key in request_dict.iterkeys()):
    # User profile attribute was updated, so validate that friend notifications were sent.
    invalidate = {'users': [user_id]}
    validator.ValidateFriendNotifications('update_user', user_id, op_dict, invalidate)
  else:
    # Validate that device notifications were sent.
    invalidate = {'users': [user_id]}
    validator.ValidateNotification('update_user', user_id, op_dict, invalidate)

  tester._CompareResponseDicts('update_user', user_id, request_dict, {}, actual_dict)
  return actual_dict
