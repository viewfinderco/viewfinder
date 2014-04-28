#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Account authorization tests for Google accounts.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andrew Kimball)']

import mock
import os
import unittest

from viewfinder.backend.base import util
from viewfinder.backend.base.testing import MockAsyncHTTPClient
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.www.test import auth_test, service_base_test


@unittest.skip("needs google credentials")
@unittest.skipIf('NO_NETWORK' in os.environ, 'no network')
class AuthGoogleTestCase(service_base_test.ServiceBaseTestCase):
  """Tests authentication via the Google OAuth service."""
  def setUp(self):
    super(AuthGoogleTestCase, self).setUp()

    self._google_user_dict = {'family_name': 'Kimball', 'name': 'Andrew Kimball', 'locale': 'en',
                              'gender': 'male', 'email': 'kimball.andy@emailscrubbed.com',
                              'link': 'https://plus.google.com/id',
                              'given_name': 'Andrew', 'id': 'id', 'verified_email': True}

    self._google_user2_dict = {'name': 'Spencer Kimball', 'email': 'spencer@emailscrubbed.com',
                               'verified_email': True}

    self._mobile_device_dict = {'name': 'Andy\'s IPhone', 'version': '1.0', 'platform': 'IPhone 4S',
                                'os': 'iOS 5.0.1', 'push_token': 'push_token'}

  def testRegisterWebUser(self):
    """Test successful register of web user."""
    # Register as web user, register as mobile user
    self._tester.RegisterGoogleUser(self._google_user_dict)
    self.assertRaisesHttpError(403,
                               self._tester.RegisterGoogleUser,
                               self._google_user_dict,
                               self._mobile_device_dict)

  def testRegisterMobileUser(self):
    """Test successful register of mobile user."""
    # Register as mobile user, register as web user.
    self._tester.RegisterGoogleUser(self._google_user_dict, self._mobile_device_dict)
    self.assertRaisesHttpError(403,
                               self._tester.RegisterGoogleUser,
                               self._google_user_dict)

  def testLoginWebUser(self):
    """Test successful login of web user."""
    # Register as web user, login as web user.
    user, device_id = self._tester.RegisterGoogleUser(self._google_user_dict)
    user2, device_id2 = self._tester.LoginGoogleUser(self._google_user_dict)
    self.assertEqual(user.user_id, user2.user_id)
    self.assertEqual(device_id, device_id2)

    # And login again as mobile user.
    self._tester.LoginGoogleUser(self._google_user_dict, self._mobile_device_dict)

  def testLoginMobileUser(self):
    """Test successful login of mobile user."""
    # Register as web user, login as mobile user.
    user, device_id = self._tester.RegisterGoogleUser(self._google_user_dict)
    user2, device_id2 = self._tester.LoginGoogleUser(self._google_user_dict, self._mobile_device_dict)
    self.assertEqual(user.user_id, user2.user_id)
    self.assertNotEqual(device_id, device_id2)

    # And login again as web user.
    self._tester.LoginGoogleUser(self._google_user_dict)

  def testLinkWebUser(self):
    """Test successful link of web user."""
    # Register as mobile user, link as web user
    user, device_id = self._tester.RegisterGoogleUser(self._google_user_dict, self._mobile_device_dict)
    cookie = self._GetSecureUserCookie(user, device_id)
    user2, device_id2 = self._tester.LinkGoogleUser(self._google_user2_dict, user_cookie=cookie)
    self.assertEqual(user.user_id, user2.user_id)
    self.assertNotEqual(device_id, device_id2)

    # And link again as mobile user.
    self._tester.LinkGoogleUser(self._google_user2_dict, self._mobile_device_dict, user_cookie=cookie)
    self.assertEqual(len(self._tester.ListIdentities(cookie)), 2)

  def testLinkMobileUser(self):
    """Test successful link of mobile user."""
    # Register as web user, link as mobile user.
    user, device_id = self._tester.RegisterGoogleUser(self._google_user_dict)
    cookie = self._GetSecureUserCookie(user, device_id)
    self._tester.LinkGoogleUser(self._google_user2_dict, self._mobile_device_dict, user_cookie=cookie)

    # And link again as web user.
    self._tester.LinkGoogleUser(self._google_user2_dict, user_cookie=cookie)
    self.assertEqual(len(self._tester.ListIdentities(cookie)), 2)

  def testNonCanonicalId(self):
    """Test that identity key is canonicalized during import from Google."""
    user, device_id = self._tester.RegisterGoogleUser(self._google_user_dict, self._mobile_device_dict)
    self._google_user_dict['email'] = self._google_user_dict['email'].upper()
    user2, device_id2 = self._tester.LoginGoogleUser(self._google_user_dict, self._mobile_device_dict)
    self.assertEqual(user.user_id, user2.user_id)

  def testLoginNoExist(self):
    """ERROR: Try to login with Google identity that is not linked to a Viewfinder account."""
    self.assertRaisesHttpError(403, self._tester.LoginGoogleUser, self._google_user_dict)
    self.assertRaisesHttpError(403, self._tester.LoginGoogleUser, self._google_user_dict,
                               self._mobile_device_dict)

  def testUnverifiedEmail(self):
    """ERROR: Try to register an unverified email address."""
    self._google_user_dict['verified_email'] = False
    self.assertRaisesHttpError(403, self._tester.RegisterGoogleUser, self._google_user_dict, self._mobile_device_dict)

  def testMissingRefreshToken(self):
    """ERROR: Test error on missing Google refresh token."""
    self.assertRaisesHttpError(400,
                               auth_test._SendAuthRequest,
                               self._tester,
                               self.get_url('/register/google'),
                               'POST',
                               request_dict=auth_test._CreateRegisterRequest(self._mobile_device_dict))

  def testGoogleRegistration(self):
    # TODO(spencer): implement something here; a cursory look around
    # the internets didn't turn up anything provided by Google analogous
    # to Facebook's test accounts.
    pass


def _TestAuthGoogleUser(action, tester, user_dict, device_dict=None, user_cookie=None):
  """Called by the ServiceTester in order to test login/google, link/google, and
  register/google calls.
  """
  ident_dict = {'key': 'Email:%s' % Identity.CanonicalizeEmail(user_dict['email']),
                'authority': 'Google',
                'refresh_token': 'refresh_token',
                'access_token': 'access_token',
                'expires': util._TEST_TIME + 3600}
  if device_dict:
    device_dict.pop('device_uuid', None)
    device_dict.pop('test_udid', None)

  # Mock responses from Google.
  with mock.patch('tornado.httpclient.AsyncHTTPClient', MockAsyncHTTPClient()) as mock_client:
    # Response to request for access token.
    auth_test._AddMockJSONResponse(mock_client,
                                   r'https://accounts.google.com/o/oauth2/token',
                                   {'access_token': ident_dict['access_token'],
                                    'token_type': 'Bearer',
                                    'expires_in': ident_dict['expires'] - util._TEST_TIME,
                                    'id_token': 'id_token',
                                    'refresh_token': ident_dict['refresh_token']})

    # Response to request for user info.
    auth_test._AddMockJSONResponse(mock_client,
                                   r'https://www.googleapis.com/oauth2/v1/userinfo\?',
                                   user_dict)

    # Response to request for people (i.e. contacts).
    auth_test._AddMockJSONResponse(mock_client,
                                   r'https://www.google.com/m8/feeds/contacts/default/full',
                                   {'feed': {'entry': [],
                                             'openSearch$startIndex': {'$t': '1'},
                                             'openSearch$totalResults': {'$t': '0'}}})

    response = auth_test._AuthFacebookOrGoogleUser(tester, action, user_dict, ident_dict, device_dict, user_cookie)
    return auth_test._ValidateAuthUser(tester, action, user_dict, ident_dict, device_dict, user_cookie, response)
