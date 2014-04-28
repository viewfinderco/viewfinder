#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Account authorization tests for Viewfinder accounts.
"""

__authors__ = ['andy@emailscrubbed.com (Andrew Kimball)']

import base64
import json
import mock
import os
import unittest
import urllib

from copy import deepcopy
from Crypto.Hash import HMAC, SHA512
from Crypto.Protocol.KDF import PBKDF2
from tornado.escape import url_escape
from viewfinder.backend.base import constants, message, util
from viewfinder.backend.base.environ import ServerEnvironment
from viewfinder.backend.base.testing import MockAsyncHTTPClient
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.guess import Guess
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.user import User
from viewfinder.backend.services.email_mgr import TestEmailManager
from viewfinder.backend.services.sms_mgr import TestSMSManager
from viewfinder.backend.www import password_util
from viewfinder.backend.www.auth_viewfinder import LoginViewfinderHandler, VerifyIdBaseHandler, VerifyIdMobileHandler
from viewfinder.backend.www.test import auth_test, service_base_test


@unittest.skipIf('NO_NETWORK' in os.environ, 'no network')
class AuthViewfinderTestCase(service_base_test.ServiceBaseTestCase):
  """Tests authentication via the Google OAuth service."""
  def setUp(self):
    super(AuthViewfinderTestCase, self).setUp()

    self._viewfinder_user_dict = {'name': 'Andy Kimball',
                                  'given_name': 'Andy',
                                  'family_name': 'Kimball',
                                  'email': 'andy@emailscrubbed.com'}

    self._viewfinder_user2_dict = {'name': 'Spencer Kimball',
                                   'given_name': 'Spencer',
                                   'phone': '+19091234567'}

    self._viewfinder_user3_dict = {'name': 'Pete Mattis',
                                   'given_name': 'Pete',
                                   'email': 'pete@emailscrubbed.com',
                                   'password': u'supersecure\u2019s'}

    self._mobile_device_dict = {'name': 'Andy\'s IPhone', 'version': '1.0', 'platform': 'IPhone 4S',
                                'os': 'iOS 5.0.1', 'push_token': 'push_token'}

  def testRegisterWebUser(self):
    """Test successful register of web user."""
    self._tester.RegisterViewfinderUser(self._viewfinder_user_dict)
    self.assertRaisesHttpError(403,
                               self._tester.RegisterViewfinderUser,
                               self._viewfinder_user_dict,
                               self._mobile_device_dict)

  def testRegisterMobileUser(self):
    """Test successful register of mobile user."""
    self._tester.RegisterViewfinderUser(self._viewfinder_user_dict, self._mobile_device_dict)
    self.assertRaisesHttpError(403,
                               self._tester.RegisterViewfinderUser,
                               self._viewfinder_user_dict)

  def testLoginWebUser(self):
    """Test successful login of web user."""
    # Register as web user, login as web user.
    user, device_id = self._tester.RegisterViewfinderUser(self._viewfinder_user2_dict)
    user2, device_id2 = self._tester.LoginViewfinderUser(self._viewfinder_user2_dict)
    self.assertEqual(user.user_id, user2.user_id)
    self.assertEqual(device_id, device_id2)

    # And login again as mobile user.
    self._tester.LoginViewfinderUser(self._viewfinder_user2_dict, self._mobile_device_dict)

  def testLoginMobileUser(self):
    """Test successful login of mobile user."""
    # Login as mobile user, and then again.
    user, device_id = self._tester.RegisterViewfinderUser(self._viewfinder_user2_dict, self._mobile_device_dict)
    user2, device_id2 = self._tester.LoginViewfinderUser(self._viewfinder_user2_dict, self._mobile_device_dict)
    self.assertEqual(user.user_id, user2.user_id)
    self.assertNotEqual(device_id, device_id2)

    # And login again as web user.
    self._tester.LoginViewfinderUser(self._viewfinder_user2_dict)

  def testLoginResetWebUser(self):
    """Test /login_reset/viewfinder with web user."""
    emails = TestEmailManager.Instance().emails
    self._tester.RegisterViewfinderUser(self._viewfinder_user_dict)

    # ------------------------------
    # Login for reset.
    # ------------------------------
    emails.clear()
    self._tester.LoginResetViewfinderUser(self._viewfinder_user_dict)
    self.assertIn('did not submit a password reset', emails[self._viewfinder_user_dict['email']][0]['html'])

    # ------------------------------
    # ERROR: Don't accept password login.
    # ------------------------------
    self.assertRaisesHttpError(400, self._tester.LoginResetViewfinderUser, self._viewfinder_user3_dict)

  def testLoginResetMobileUser(self):
    """Test /login_reset/viewfinder with mobile user."""
    emails = TestEmailManager.Instance().emails
    self._tester.RegisterViewfinderUser(self._viewfinder_user_dict, self._mobile_device_dict)

    emails.clear()
    self._tester.LoginResetViewfinderUser(self._viewfinder_user_dict, self._mobile_device_dict)
    self.assertIn('did not submit a password reset', emails[self._viewfinder_user_dict['email']][0]['html'])

  def testLinkMobileUser(self):
    """Test successful link of mobile user."""
    # Register as web user, link as mobile user.
    user, device_id = self._tester.RegisterViewfinderUser(self._viewfinder_user_dict)
    cookie = self._GetSecureUserCookie(user, device_id)
    self._tester.LinkViewfinderUser(self._viewfinder_user2_dict, self._mobile_device_dict, user_cookie=cookie)

    # And link again as web user.
    self._tester.LinkViewfinderUser(self._viewfinder_user2_dict, user_cookie=cookie)
    self.assertEqual(len(self._tester.ListIdentities(cookie)), 2)

  def testLinkWebUser(self):
    """Test successful link of web user."""
    # Register as mobile user, link as web user.
    user, device_id = self._tester.RegisterViewfinderUser(self._viewfinder_user_dict, self._mobile_device_dict)
    cookie = self._GetSecureUserCookie(user, device_id)
    self._tester.LinkViewfinderUser(self._viewfinder_user2_dict, user_cookie=cookie)

    # And link again as mobile user.
    self._tester.LinkViewfinderUser(self._viewfinder_user2_dict, self._mobile_device_dict, user_cookie=cookie)
    self.assertEqual(len(self._tester.ListIdentities(cookie)), 2)

  def testAuthPassword(self):
    """Register a user with a password, then login with the password."""
    # ------------------------------
    # Register a user with a password (email should be sent).
    # ------------------------------
    TestEmailManager.Instance().emails.clear()
    user, _ = self._tester.RegisterViewfinderUser(self._viewfinder_user3_dict, self._mobile_device_dict)
    self.assertEqual(len(TestEmailManager.Instance().emails), 1)

    # Verify correct password hash was created.
    expected_pwd_hash = base64.b64encode(PBKDF2(self._viewfinder_user3_dict['password'].encode('utf8'),
                                                base64.b64decode(user.salt.Decrypt()),
                                                count=1000,
                                                prf=lambda p, s: HMAC.new(p, s, SHA512).digest()))
    self.assertEqual(user.pwd_hash.Decrypt(), expected_pwd_hash)

    # ------------------------------
    # Use the password to login (no email should be sent).
    # ------------------------------
    TestEmailManager.Instance().emails.clear()
    user, device_id = self._tester.LoginViewfinderUser({'email': self._viewfinder_user3_dict['email'],
                                                        'password': self._viewfinder_user3_dict['password']},
                                                       self._mobile_device_dict)
    self.assertEqual(len(TestEmailManager.Instance().emails), 0)

  def testConfirmedRegister(self):
    """Test shortcut registration with a confirmed prospective user cookie."""
    # Create a prospective user.
    self._validate = False
    self._CreateSimpleTestAssets()
    prospective_user, _, _ = self._CreateProspectiveUser()

    # Create registration request for the prospective user.
    auth_info_dict = {'identity': 'Email:%s' % prospective_user.email,
                      'name': 'Jimmy John',
                      'given_name': 'Jimmy',
                      'family_name': 'John'}

    url = self._tester.GetUrl('/register/viewfinder')
    request_dict = auth_test._CreateRegisterRequest(self._mobile_device_dict, auth_info_dict)

    # Try to register without a confirmed cookie.
    cookie = self._tester.GetSecureUserCookie(user_id=prospective_user.user_id,
                                              device_id=prospective_user.webapp_dev_id,
                                              user_name=None)
    response = auth_test._SendAuthRequest(self._tester,
                                          url,
                                          'POST',
                                          user_cookie=cookie,
                                          request_dict=request_dict)
    # Identity confirmation should have been required.
    self.assertNotIn('user_id', response.body)

    # Now register with a confirmed cookie.
    confirmed_cookie = self._tester.GetSecureUserCookie(user_id=prospective_user.user_id,
                                                        device_id=prospective_user.webapp_dev_id,
                                                        user_name=None,
                                                        confirm_time=util._TEST_TIME)
    response = auth_test._SendAuthRequest(self._tester,
                                          url,
                                          'POST',
                                          user_cookie=confirmed_cookie,
                                          request_dict=request_dict)
    # Immediate registration should have occurred.
    self.assertIn('user_id', response.body)

  def testRegisterProspectiveContact(self):
    """Register a prospective user, which is the target of a contact."""
    # Create a contact.
    user_dict = {'email': 'prospective@emailscrubbed.com', 'name': 'Andy Kimball', 'given_name': 'Andy'}
    identity_key = 'Email:prospective@emailscrubbed.com'
    contact_dict = Contact.CreateContactDict(self._user2.user_id,
                                             [(identity_key, None)],
                                             util._TEST_TIME,
                                             Contact.GMAIL)
    self._UpdateOrAllocateDBObject(Contact, **contact_dict)

    # Now create the prospective user (which should notify contact user).
    self._CreateSimpleTestAssets()
    self._CreateProspectiveUser()

    # Increment time so that the contact will be rewritten during registration.
    util._TEST_TIME += 1

    # Now register the user (which should notify contact user).
    self._tester.RegisterViewfinderUser(user_dict, None)
    response_dict = self._tester.QueryNotifications(self._cookie2, 3, scan_forward=False)
    self.assertEqual([notify_dict['name'] for notify_dict in response_dict['notifications']],
                     [u'first register contact', u'create prospective user', u'register friend'])

  def testInvalidPassword(self):
    """ERROR: Try to register a password that does not meet min requirements."""
    self.assertRaisesHttpError(400,
                               self._tester.RegisterViewfinderUser,
                               {'name': 'Pete Mattis',
                                'given_name': 'Pete',
                                'email': 'pete@emailscrubbed.com',
                                'password': 'tiny'},
                               self._mobile_device_dict)

  def testMissingPassword(self):
    """ERROR: Try to use password to log into account with no password."""
    self._tester.RegisterViewfinderUser(self._viewfinder_user_dict, self._mobile_device_dict)
    self.assertRaisesHttpError(403,
                               self._tester.LoginViewfinderUser,
                               {'email': self._viewfinder_user_dict['email'],
                                'password': 'missing password'},
                               self._mobile_device_dict)

  def testIncorrectPassword(self):
    """ERROR: Test auth with incorrect password."""
    self._tester.RegisterViewfinderUser(self._viewfinder_user3_dict, self._mobile_device_dict)
    self.assertRaisesHttpError(403,
                               self._tester.LoginViewfinderUser,
                               {'email': self._viewfinder_user3_dict['email'],
                                'password': 'wrong password'},
                               self._mobile_device_dict)

  @mock.patch.object(password_util, '_MAX_PASSWORD_GUESSES', 1)
  def testTooManyPasswordGuesses(self):
    """ERROR: Try to guess password too many times."""
    self._tester.RegisterViewfinderUser(self._viewfinder_user3_dict, self._mobile_device_dict)

    self.assertRaisesHttpError(403,
                               self._tester.LoginViewfinderUser,
                               {'email': self._viewfinder_user3_dict['email'],
                                'password': 'wrong password'},
                               self._mobile_device_dict)

    self.assertRaisesHttpError(403,
                               self._tester.LoginViewfinderUser,
                               self._viewfinder_user3_dict,
                               self._mobile_device_dict)

  def testMissingNameParts(self):
    """ERROR: Try to create users with missing name parts."""
    user_dict = {'email': 'no-one@island-of-cyclopes.com'}
    self.assertRaisesHttpError(400, self._tester.RegisterViewfinderUser, user_dict, self._mobile_device_dict)

    user_dict = {'name': 'Andy Kimball', 'phone': '13844759384'}
    self.assertRaisesHttpError(400, self._tester.RegisterViewfinderUser, user_dict, self._mobile_device_dict)

    user_dict = {'given_name': 'Andy', 'email': 'just-name@foo.com'}
    self.assertRaisesHttpError(400, self._tester.RegisterViewfinderUser, user_dict, self._mobile_device_dict)

    user_dict = {'family_name': 'Kimball', 'email': 'just-name@foo.com'}
    self.assertRaisesHttpError(400, self._tester.RegisterViewfinderUser, user_dict, self._mobile_device_dict)

  def testNonCanonicalId(self):
    """ERROR: Test that non canonical identity keys are rejected."""
    self._viewfinder_user_dict['email'] = self._viewfinder_user_dict['email'].upper()
    self.assertRaisesHttpError(400,
                               self._tester.RegisterViewfinderUser,
                               self._viewfinder_user_dict,
                               self._mobile_device_dict)

    self._viewfinder_user2_dict['phone'] = '3854759'
    self.assertRaisesHttpError(400,
                               self._tester.RegisterViewfinderUser,
                               self._viewfinder_user2_dict,
                               self._mobile_device_dict)

  def testLoginNoExist(self):
    """ERROR: Try to login with identity that is not linked to a Viewfinder account."""
    self.assertRaisesHttpError(403,
                               self._tester.LoginViewfinderUser,
                               self._viewfinder_user_dict,
                               self._mobile_device_dict)

    self.assertRaisesHttpError(403,
                               self._tester.LoginViewfinderUser,
                               self._viewfinder_user2_dict,
                               None)

  @mock.patch.object(VerifyIdMobileHandler, '_ACCESS_TOKEN_WAIT', .01)
  def testVerifyIdMobileFail(self):
    """Test identity verification in the mobile case where we can't switch to the app."""
    def _Test(action, identity):
      self.assertEqual(len(identity.access_token), 9)
      url = self._tester.GetUrl('/%s%s' % (identity.json_attrs['group_id'], identity.json_attrs['random_key']))

      # Start with non-mobile user-agent string.
      response = self._RunAsync(self.http_client.fetch, url, method='GET')
      self.assertEqual(response.code, 200)

      self.assertIn('No app on this device', response.body)
      self.assertIn('<div class="code-partial">%s</div>' % identity.access_token[0:3], response.body)
      self.assertIn('<div class="code-partial">%s</div>' % identity.access_token[3:6], response.body)
      self.assertIn('<div class="code-partial">%s</div>' % identity.access_token[6:9], response.body)

      if action == 'register':
        email_type = 'activation'
      elif action == 'login_reset':
        email_type = 'reset password'
      else:
        email_type = 'confirmation'
      self.assertIn('Looks like you opened the %s email outside your iPhone.' % email_type, response.body)

      # Try IOS user-agent string.
      response = self._RunAsync(self.http_client.fetch, url, method='GET', headers={'User-Agent': 'IPhone'})
      self.assertEqual(response.code, 200)

      self.assertIn('This device *may* contain the app', response.body)
      self.assertIn('app_url = "viewfinder://verify_id?"', response.body)
      self.assertIn('app_url += "identity=%s&"' % url_escape(identity.key), response.body)
      self.assertIn('app_url += "access_token=%s"' % url_escape(identity.access_token), response.body)

      self.assertIn('window.location = "?redirected=True";', response.body)

      # Now pass redirected=True to simulate case where we fail to switch to app on IOS device.
      response = self._RunAsync(self.http_client.fetch, url + '?redirected=True', method='GET',
                                headers={'User-Agent': 'IPhone'})
      self.assertEqual(response.code, 200)

      self.assertIn('No app on this device', response.body)
      self.assertIn('We\'re having trouble loading the Viewfinder app.', response.body)

    # ------------------------------
    # Test register case.
    # ------------------------------
    auth_info_dict = {'identity': 'Email:mike@emailscrubbed.com',
                      'name': 'Mike Purtell',
                      'given_name': 'Mike',
                      'family_name': 'Purtell'}
    identity = _TestGenerateAccessToken('register',
                                        self._tester,
                                        self._mobile_device_dict,
                                        auth_info_dict,
                                        use_short_token=False)
    _Test('register', identity)

    # ------------------------------
    # Test login case (need to register first).
    # ------------------------------
    self._tester.RegisterViewfinderUser({'name': 'Mike Purtell',
                                         'given_name': 'Mike',
                                         'email': 'mike@emailscrubbed.com'})

    auth_info_dict = {'identity': 'Email:mike@emailscrubbed.com'}
    identity = _TestGenerateAccessToken('login',
                                        self._tester,
                                        self._mobile_device_dict,
                                        auth_info_dict,
                                        use_short_token=False)
    _Test('login', identity)

    # ------------------------------
    # Test login_reset case.
    # ------------------------------
    identity = _TestGenerateAccessToken('login_reset',
                                        self._tester,
                                        self._mobile_device_dict,
                                        auth_info_dict,
                                        use_short_token=False)
    _Test('login_reset', identity)

    # ------------------------------
    # Test link case.
    # ------------------------------
    user, device_id = self._tester.RegisterViewfinderUser(self._viewfinder_user_dict)
    user_cookie = self._GetSecureUserCookie(user, device_id)
    auth_info_dict = {'identity': 'Email:alt-email@emailscrubbed.com'}
    identity = _TestGenerateAccessToken('link',
                                        self._tester,
                                        self._mobile_device_dict,
                                        auth_info_dict,
                                        user_cookie=user_cookie,
                                        use_short_token=False)
    _Test('link', identity)

  @mock.patch.object(VerifyIdMobileHandler, '_ACCESS_TOKEN_WAIT', .01)
  def testVerifyIdMobileSuccess(self):
    """Test identity verification in the mobile case where switching to app works."""
    # First generate an access token without redeeming it in order to grab the verify_id URL.
    auth_info_dict = {'identity': 'Email:%s' % self._viewfinder_user_dict['email'],
                      'name': self._viewfinder_user_dict['name'],
                      'given_name': self._viewfinder_user_dict['given_name']}
    identity = _TestGenerateAccessToken('register',
                                        self._tester,
                                        self._mobile_device_dict,
                                        auth_info_dict,
                                        use_short_token=False)

    url = self._tester.GetUrl('/%s%s?redirected=True' % (identity.json_attrs['group_id'],
                                                         identity.json_attrs['random_key']))

    # Now register the user; the access token will be re-used since the previous one was not redeemed.
    self._tester.RegisterViewfinderUser(self._viewfinder_user_dict, self._mobile_device_dict)

    # Now ensure that the call to the verify_id handler succeeds.
    response = self._RunAsync(self.http_client.fetch, url, method='GET', headers={'User-Agent': 'IPhone'})
    self.assertEqual(response.code, 200)

    self.assertIn('Your Viewfinder Account is all set', response.body)

  def testVerifyIdWeb(self):
    """Test identity verification in the web site case."""
    # ------------------------------
    # Generate the confirmation email for web scenario.
    # ------------------------------
    auth_info_dict = {'identity': 'Email:%s' % self._viewfinder_user_dict['email'],
                      'name': self._viewfinder_user_dict['name'],
                      'given_name': self._viewfinder_user_dict['given_name'],
                      'family_name': self._viewfinder_user_dict['family_name'],
                      'password': 'foobarbaz'}
    identity = _TestGenerateAccessToken('register', self._tester, None, auth_info_dict, use_short_token=False)

    # ------------------------------
    # Follow the email link and expect the auth.html page.
    # ------------------------------
    url = self._tester.GetUrl('/%s%s' % (identity.json_attrs['group_id'], identity.json_attrs['random_key']))
    response = self._RunAsync(self.http_client.fetch, url, method='GET')
    self.assertEqual(response.code, 200)
    self.assertIn('identity', response.body)
    self.assertIn('access_token', response.body)

    # ------------------------------
    # Try to confirm an incorrect password.
    # ------------------------------
    request_dict = {'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION}, 'password': 'incorrect'}
    response = self._RunAsync(self.http_client.fetch,
                              url,
                              method='POST',
                              headers={'Cookie': '_xsrf=fake_xsrf', 'X-Xsrftoken': 'fake_xsrf',
                                       'Content-Type': 'application/json'},
                              body=json.dumps(request_dict))
    self.assertEqual(response.code, 403)
    #TODO(matt): Detect the error message, whatever it is.
    #self.assertIn('"message": "The password you provided is incorrect."', response.body)

    # ------------------------------
    # Confirm the correct password.
    # ------------------------------
    request_dict = {'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION}, 'password': 'foobarbaz'}
    response = self._RunAsync(self.http_client.fetch,
                              url,
                              method='POST',
                              headers={'Cookie': '_xsrf=fake_xsrf', 'X-Xsrftoken': 'fake_xsrf',
                                       'Content-Type': 'application/json'},
                              body=json.dumps(request_dict))
    self.assertEqual(response.code, 200)

    # ------------------------------
    # Verify the access token.
    # ------------------------------
    verify_url = self._tester.GetUrl('/verify/viewfinder')
    request_dict = {'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION,
                                'synchronous': True},
                    'identity': identity.key,
                    'access_token': identity.access_token}
    response = auth_test._SendAuthRequest(self._tester, verify_url, 'POST', request_dict=request_dict)
    self.assertEqual(response.code, 200)

    # Validate the registration updated the expected DB objects.
    auth_test._ValidateAuthUser(self._tester,
                                'register',
                                self._viewfinder_user_dict,
                                {'key': auth_info_dict['identity'], 'authority': 'Viewfinder'},
                                None,
                                self._cookie,
                                response)

    # ------------------------------
    # Follow the email link again and expect expiration failure.
    # ------------------------------
    response = self._RunAsync(self.http_client.fetch,
                              url,
                              method='GET',
                              headers={'Cookie': '_xsrf=fake_xsrf;skip-pwd=true;', 'X-Xsrftoken': 'fake_xsrf'},
                              follow_redirects=False)
    self.assertEqual(response.code, 403)
    self.assertIn('The link in your email has expired or already been used', response.body)

  def testAccessToken(self):
    """Use valid and invalid access tokens with Viewfinder auth."""
    auth_info_dict = {'identity': 'Email:new.user@emailscrubbed.com', 'name': 'New User', 'given_name': 'New User'}
    identity = _TestGenerateAccessToken('register', self._tester, self._mobile_device_dict, auth_info_dict)

    url = self._tester.GetUrl('/verify/viewfinder')
    request_dict = {'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION,
                                'synchronous': True},
                    'identity': auth_info_dict['identity'],
                    'access_token': 'mismatch'}

    # ------------------------------
    # Try to use invalid token, which should fail.
    # ------------------------------
    self.assertRaisesHttpError(403, auth_test._SendAuthRequest, self._tester, url, 'POST',
                               request_dict=request_dict)

    # ------------------------------
    # Now use valid token, which should succeed, since several failed tries are allowed.
    # ------------------------------
    request_dict['access_token'] = identity.access_token
    auth_test._SendAuthRequest(self._tester, url, 'POST', request_dict=request_dict)

    identity = self._RunAsync(Identity.Query, self._client, auth_info_dict['identity'], None)
    self._tester.validator.ValidateUpdateDBObject(Identity,
                                                  key=auth_info_dict['identity'],
                                                  user_id=identity.user_id,
                                                  json_attrs=identity.json_attrs,
                                                  expires=0,
                                                  auth_throttle=None)

    guess_id = Guess.ConstructGuessId('em', identity.user_id)
    self._tester.validator.ValidateUpdateDBObject(Guess,
                                                  guess_id=guess_id,
                                                  expires=util._TEST_TIME + constants.SECONDS_PER_DAY,
                                                  guesses=1)

    # ------------------------------
    # Now try to use valid token again, which should fail, since a token can be used just once.
    # ------------------------------
    self.assertRaisesHttpError(403, auth_test._SendAuthRequest, self._tester, url, 'POST',
                               request_dict=request_dict)

  def testTokenReuse(self):
    """Test that access token will be reused if it is not redeemed or expired."""
    # ------------------------------
    # Token should be reused if it's a VF token.
    # ------------------------------
    auth_info_dict = {'identity': 'Email:kat@emailscrubbed.com', 'name': 'Kat Mattis', 'given_name': 'Kat'}
    identity = _TestGenerateAccessToken('register', self._tester, self._mobile_device_dict, auth_info_dict)
    identity2 = _TestGenerateAccessToken('register', self._tester, self._mobile_device_dict, auth_info_dict)
    self.assertEqual(identity.access_token, identity2.access_token)

    # ------------------------------
    # Token should be reused if it's a different auth action.
    # ------------------------------
    identity3 = _TestGenerateAccessToken('register', self._tester, self._mobile_device_dict, auth_info_dict)
    self.assertEqual(identity2.access_token, identity3.access_token)

    # ------------------------------
    # Token should be reused if password has changed.
    # ------------------------------
    auth_info_dict2 = deepcopy(auth_info_dict)
    auth_info_dict2['password'] = 'foobarbaz'
    identity4 = _TestGenerateAccessToken('register', self._tester, self._mobile_device_dict, auth_info_dict2)
    self.assertEqual(identity3.access_token, identity4.access_token)

    # ------------------------------
    # Token should be reused if password has not changed.
    # ------------------------------
    auth_info_dict2 = deepcopy(auth_info_dict)
    auth_info_dict2['password'] = 'foobarbaz'
    identity5 = _TestGenerateAccessToken('register', self._tester, self._mobile_device_dict, auth_info_dict2)
    self.assertEqual(identity4.access_token, identity5.access_token)

    # ------------------------------
    # Token should not be reused if it's a different length.
    # ------------------------------
    identity6 = _TestGenerateAccessToken('register',
                                         self._tester,
                                         self._mobile_device_dict,
                                         auth_info_dict,
                                         use_short_token=False)
    self.assertNotEqual(identity5.access_token, identity6.access_token)
    identity7 = _TestGenerateAccessToken('register', self._tester, self._mobile_device_dict, auth_info_dict)
    self.assertNotEqual(identity6.access_token, identity7.access_token)

    # ------------------------------
    # Token should not be reused if it's been redeemed (i.e. is expired).
    # ------------------------------
    user_dict = {'name': 'Kat Mattis', 'given_name': 'Kat', 'email': 'kat@emailscrubbed.com'}
    user, device_id = self._tester.RegisterViewfinderUser(user_dict, self._mobile_device_dict)

    auth_info_dict2 = {'identity': auth_info_dict['identity']}
    identity8 = _TestGenerateAccessToken('login', self._tester, self._mobile_device_dict, auth_info_dict2)
    self.assertNotEqual(identity7.access_token, identity8.access_token)

    # ------------------------------
    # Token should not be reused if it's not a VF token.
    # ------------------------------
    user_dict = {'name': 'Andy Kimball', 'email': 'andy@emailscrubbed.com', 'verified_email': True}
    user, device_id = self._tester.RegisterGoogleUser(user_dict)
    identity = self._RunAsync(Identity.Query, self._client, 'Email:' + user_dict['email'], None)

    auth_info_dict = {'identity': 'Email:' + user_dict['email']}
    identity2 = _TestGenerateAccessToken('login', self._tester, self._mobile_device_dict, auth_info_dict)
    self.assertNotEqual(identity.access_token, identity2.access_token)

    # ------------------------------
    # Make sure that reusing token does not reset guesses.
    # ------------------------------
    url = self._tester.GetUrl('/verify/viewfinder')
    request_dict = {'identity': auth_info_dict['identity'], 'access_token': 'mismatch'}
    self.assertRaisesHttpError(403,
                               auth_test._SendAuthRequest,
                               self._tester,
                               url,
                               'POST',
                               request_dict=request_dict)
    identity3 = _TestGenerateAccessToken('login', self._tester, self._mobile_device_dict, auth_info_dict)
    self.assertEqual(identity2.access_token, identity3.access_token)

    guess_id = Guess.ConstructGuessId('em', identity3.user_id)
    guess = self._RunAsync(Guess.Query, self._client, guess_id, None)
    self.assertEqual(guess.guesses, 1)

  def testMaxGuesses(self):
    """ERROR: Test that maximum access token guesses are respected."""
    auth_info_dict = {'identity': 'Email:new.user@emailscrubbed.com', 'name': 'New User', 'given_name': 'New User'}
    identity = _TestGenerateAccessToken('register', self._tester, self._mobile_device_dict, auth_info_dict)

    url = self._tester.GetUrl('/verify/viewfinder')
    request_dict = {'identity': auth_info_dict['identity'],
                    'access_token': 'mismatch'}

    # ------------------------------
    # Exceed max guesses.
    # ------------------------------
    # Set number of guesses near limit.
    guess_id = Identity._ConstructAccessTokenGuessId('Email', identity.user_id)
    guess = Guess.CreateFromKeywords(guess_id=guess_id,
                                     expires=util._TEST_TIME + constants.SECONDS_PER_DAY,
                                     guesses=9)
    guess.Update(self._client)

    self.assertRaisesHttpError(403,
                               auth_test._SendAuthRequest,
                               self._tester,
                               url,
                               'POST',
                               request_dict=request_dict)

    # At this point we should be at the limit of guesses.
    self._tester.validator.ValidateUpdateDBObject(Guess,
                                                  guess_id=guess.guess_id,
                                                  expires=util._TEST_TIME + constants.SECONDS_PER_DAY,
                                                  guesses=10)

    # Now make sure that trying to auth with a valid token fails due to max guesses.
    request_dict['access_token'] = identity.access_token
    self.assertRaisesHttpError(403,
                               auth_test._SendAuthRequest,
                               self._tester,
                               url,
                               'POST',
                               request_dict=request_dict)

    # ------------------------------
    # Try to reset max guesses by generating new token.
    # ------------------------------
    util._TEST_TIME += 1
    auth_info_dict = {'identity': 'Email:new.user@emailscrubbed.com', 'name': 'New User 2', 'given_name': 'New User 2'}
    self.assertRaisesHttpError(403,
                               _TestGenerateAccessToken,
                               'register',
                               self._tester,
                               self._mobile_device_dict,
                               auth_info_dict)

    # ------------------------------
    # Move ahead 24 hours and verify that token guesses are reset.
    # ------------------------------
    util._TEST_TIME += constants.SECONDS_PER_DAY
    identity = _TestGenerateAccessToken('register', self._tester, self._mobile_device_dict, auth_info_dict)

    self.assertRaisesHttpError(403,
                               auth_test._SendAuthRequest,
                               self._tester,
                               url,
                               'POST',
                               request_dict=request_dict)

    self._tester.validator.ValidateUpdateDBObject(Guess,
                                                  guess_id=guess.guess_id,
                                                  expires=util._TEST_TIME + constants.SECONDS_PER_DAY,
                                                  guesses=1)

  def testRegisterOverGoogle(self):
    """ERROR: Try to use invalid Viewfinder access token with existing Google identity."""
    url = self._tester.GetUrl('/verify/viewfinder')
    request_dict = {'identity': 'Email:user3@emailscrubbed.com',
                    'access_token': 'mismatch'}
    self.assertRaisesHttpError(403, auth_test._SendAuthRequest, self._tester, url, 'POST',
                               request_dict=request_dict)
    user = self._RunAsync(User.Query, self._client, self._user3.user_id, None)
    self.assertEqual(user.name, self._user3.name)

  @mock.patch.object(VerifyIdBaseHandler, '_MAX_MESSAGES_PER_MIN', 2)
  @mock.patch.object(VerifyIdBaseHandler, '_MAX_MESSAGES_PER_DAY', 3)
  def testTooManyMessages(self):
    """ERROR: Try to send too many auth messages to a particular identity."""
    emails = TestEmailManager.Instance().emails
    phone_numbers = TestSMSManager.Instance().phone_numbers

    # ------------------------------
    # Max emails per minute.
    # ------------------------------
    emails.clear()
    auth_info_dict = {'identity': 'Email:mike@emailscrubbed.com', 'name': 'Mike', 'given_name': 'Mike'}
    _GenerateAccessToken('register', self._tester, {}, auth_info_dict)
    _GenerateAccessToken('register', self._tester, {}, auth_info_dict)
    _GenerateAccessToken('register', self._tester, {}, auth_info_dict)
    self.assertEqual(len(emails['mike@emailscrubbed.com']), 2)

    # ------------------------------
    # Max emails per day.
    # ------------------------------
    util._TEST_TIME += constants.SECONDS_PER_MINUTE
    emails.clear()
    _GenerateAccessToken('register', self._tester, {}, auth_info_dict)
    self.assertRaisesHttpError(400, _GenerateAccessToken, 'register', self._tester, {}, auth_info_dict)
    self.assertEqual(len(emails['mike@emailscrubbed.com']), 1)

    # ------------------------------
    # Max emails per minute (different identity).
    # ------------------------------
    emails.clear()
    auth_info_dict = {'identity': 'Email:andy@emailscrubbed.com', 'name': 'Andy', 'given_name': 'Andy'}
    _GenerateAccessToken('register', self._tester, {}, auth_info_dict)
    _GenerateAccessToken('register', self._tester, {}, auth_info_dict)
    _GenerateAccessToken('register', self._tester, {}, auth_info_dict)
    self.assertEqual(len(emails['andy@emailscrubbed.com']), 2)

    # ------------------------------
    # Max SMS messages per minute.
    # ------------------------------
    phone_numbers.clear()
    auth_info_dict = {'identity': 'Phone:+14255555555', 'name': 'Andy', 'given_name': 'Andy'}
    _GenerateAccessToken('register', self._tester, {}, auth_info_dict)
    _GenerateAccessToken('register', self._tester, {}, auth_info_dict)
    _GenerateAccessToken('register', self._tester, {}, auth_info_dict)
    self.assertEqual(len(phone_numbers['+14255555555']), 2)

  def testEmailAccessToken(self):
    """Test the VerifyIdBaseHandler.SendVerifyIdMessage method with an email identity."""
    def _TestEmail(action, identity_key, name, token_len):
      identity_type, value = Identity.SplitKey(identity_key)
      email_args = TestEmailManager.Instance().emails[value][0]

      identity = self._RunAsync(Identity.Query, self._client, identity_key, None)
      url = 'https://%s/%s%s' % (ServerEnvironment.GetHost(),
                                 identity.json_attrs['group_id'],
                                 identity.json_attrs['random_key'])

      self.assertEqual(email_args['from'], 'info@mailer.viewfinder.co')
      self.assertEqual(email_args['fromname'], 'Viewfinder')
      self.assertEqual(email_args['to'], value)
      self.assertEqual(email_args.get('toname', None), name)

      name = name or value
      self.assertIn(name, email_args['html'])
      self.assertIn('Hello %s' % name, email_args['html'])
      self.assertNotIn('\n', email_args['html'], 'HTML should have been squeezed')
      self.assertIn('you are at least 13 years old', email_args['html'])

      self.assertIn(name, email_args['text'])
      self.assertIn('Hello %s,' % name, email_args['text'])
      self.assertIn('\n', email_args['text'], 'text should not have been squeezed')
      self.assertIn('you are at least 13 years old', email_args['text'])

      # A short access token (i.e. 4 digits) is in-lined in email rather than a link.
      self.assertEqual(len(identity.access_token), token_len)
      if token_len == 4:
        self.assertNotIn(url, email_args['html'])
        self.assertNotIn(url, email_args['text'])
        self.assertIn(identity.access_token, email_args['html'])
        self.assertIn(identity.access_token, email_args['text'])
      else:
        self.assertIn(url, email_args['html'])
        self.assertIn(url, email_args['text'])
        self.assertNotIn(identity.access_token, email_args['html'])
        self.assertNotIn(identity.access_token, email_args['text'])

    # Turn off end-step validation, as we're only interested in content of emails.
    self._validate = False

    # Test register.
    TestEmailManager.Instance().emails.clear()
    new_identity_key = 'Email:new.user@emailscrubbed.com'
    new_user_name = 'New User'
    user_id, webapp_dev_id = self._RunAsync(User.AllocateUserAndWebDeviceIds, self._client)
    user, identity = self._RunAsync(User.CreateProspective,
                                    self._client,
                                    user_id,
                                    webapp_dev_id,
                                    new_identity_key,
                                    util._TEST_TIME)
    self._RunAsync(VerifyIdBaseHandler.SendVerifyIdMessage,
                   self._client,
                   'register',
                   use_short_token=True,
                   is_mobile_app=False,
                   identity_key=new_identity_key,
                   user_id=user.user_id,
                   user_name=new_user_name,
                   user_dict={},
                   ident_dict={'key': new_identity_key},
                   device_dict=None)
    _TestEmail('register', new_identity_key, new_user_name, 4)

    # Test login, with no user name.
    TestEmailManager.Instance().emails.clear()
    existing_identity_key = 'Email:%s' % self._user.email
    self._RunAsync(VerifyIdBaseHandler.SendVerifyIdMessage,
                   self._client,
                   'login',
                   use_short_token=False,
                   is_mobile_app=True,
                   identity_key=existing_identity_key,
                   user_id=user.user_id,
                   user_name=None,
                   user_dict={},
                   ident_dict={'key': existing_identity_key},
                   device_dict={})
    _TestEmail('login', existing_identity_key, None, 9)

    # Test link.
    TestEmailManager.Instance().emails.clear()
    new_identity_key = 'Email:alt-email@emailscrubbed.com'
    identity = Identity.CreateFromKeywords(key=new_identity_key)
    self._RunAsync(identity.Update, self._client)
    self._RunAsync(VerifyIdBaseHandler.SendVerifyIdMessage,
                   self._client,
                   'link',
                   use_short_token=False,
                   is_mobile_app=True,
                   identity_key=new_identity_key,
                   user_id=user.user_id,
                   user_name=user.name,
                   user_dict={},
                   ident_dict={'key': new_identity_key},
                   device_dict={})
    _TestEmail('link', new_identity_key, None, 9)

    # Test reset.
    TestEmailManager.Instance().emails.clear()
    new_identity_key = 'Email:alt-email@emailscrubbed.com'
    self._RunAsync(VerifyIdBaseHandler.SendVerifyIdMessage,
                   self._client,
                   'login_reset',
                   use_short_token=True,
                   is_mobile_app=True,
                   identity_key=new_identity_key,
                   user_id=user.user_id,
                   user_name=user.name,
                   user_dict={},
                   ident_dict={'key': new_identity_key},
                   device_dict={})
    _TestEmail('login_reset', new_identity_key, None, 4)

    # Test merge.
    TestEmailManager.Instance().emails.clear()
    new_identity_key = 'Email:alt-email@emailscrubbed.com'
    self._RunAsync(VerifyIdBaseHandler.SendVerifyIdMessage,
                   self._client,
                   'merge_token',
                   use_short_token=True,
                   is_mobile_app=True,
                   identity_key=new_identity_key,
                   user_id=user.user_id,
                   user_name=user.name,
                   user_dict={},
                   ident_dict={'key': new_identity_key},
                   device_dict={})
    _TestEmail('merge_token', new_identity_key, None, 4)

  def testSmsAccessToken(self):
    """Test the VerifyIdBaseHandler.SendVerifyIdMessage method with an SMS identity."""
    def _TestSms(identity_key, name):
      identity = self._RunAsync(Identity.Query, self._client, identity_key, None)
      identity_type, value = Identity.SplitKey(identity_key)
      sms_args = TestSMSManager.Instance().phone_numbers[value][0]

      self.assertEqual(sms_args['To'], value)
      self.assertEqual(len(identity.access_token), 4)
      self.assertEqual(sms_args['Body'], 'Viewfinder code: %s' % identity.access_token)

    # Test register.
    TestSMSManager.Instance().phone_numbers.clear()
    new_identity_key = 'Phone:+11234567890'
    new_user_name = 'New User'
    user_id, webapp_dev_id = self._RunAsync(User.AllocateUserAndWebDeviceIds, self._client)
    user, identity = self._RunAsync(User.CreateProspective,
                                    self._client,
                                    user_id,
                                    webapp_dev_id,
                                    new_identity_key,
                                    util._TEST_TIME)
    self._RunAsync(VerifyIdBaseHandler.SendVerifyIdMessage,
                   self._client,
                   'register',
                   use_short_token=False,
                   is_mobile_app=False,
                   identity_key=new_identity_key,
                   user_id=user.user_id,
                   user_name=new_user_name,
                   user_dict={},
                   ident_dict={'key': new_identity_key},
                   device_dict=None)
    _TestSms(new_identity_key, new_user_name)

    # Test login, with no user name.
    TestSMSManager.Instance().phone_numbers.clear()
    existing_identity_key = 'Phone:+11234567890'
    self._RunAsync(VerifyIdBaseHandler.SendVerifyIdMessage,
                   self._client,
                   'login',
                   use_short_token=True,
                   is_mobile_app=True,
                   identity_key=existing_identity_key,
                   user_id=user.user_id,
                   user_name=None,
                   user_dict={},
                   ident_dict={'key': existing_identity_key},
                   device_dict={})
    _TestSms(existing_identity_key, None)

    # Test link.
    TestSMSManager.Instance().phone_numbers.clear()
    new_identity_key = 'Phone:+14251234567'
    identity = Identity.CreateFromKeywords(key=new_identity_key)
    self._RunAsync(identity.Update, self._client)
    self._RunAsync(VerifyIdBaseHandler.SendVerifyIdMessage,
                   self._client,
                   'link',
                   use_short_token=False,
                   is_mobile_app=True,
                   identity_key=new_identity_key,
                   user_id=user.user_id,
                   user_name=user.name,
                   user_dict={},
                   ident_dict={'key': new_identity_key},
                   device_dict={})
    _TestSms(new_identity_key, None)

  def testConfirmedCookie(self):
    """Test generation and use of a confirmed cookie."""
    user_dict = self._viewfinder_user_dict

    # Register the user.
    self._tester.RegisterViewfinderUser(user_dict, None)

    # Login in and capture the user cookie, which should be confirmed.
    ident_dict = {'key': 'Email:%s' % user_dict['email'], 'authority': 'Viewfinder'}
    response = _AuthViewfinderUser(self._tester, 'login', user_dict, ident_dict, None)
    auth_test._ValidateAuthUser(self._tester, 'login', user_dict, ident_dict, None, None, response)
    confirmed_cookie = self._tester.GetCookieFromResponse(response)

    # ------------------------------
    # Use the cookie for a lower privilege operation.
    # ------------------------------
    self._tester.QueryUsers(confirmed_cookie, [self._user2.user_id])

    # ------------------------------
    # Use the cookie to perform a highly-privileged operation.
    # ------------------------------
    self._tester.UpdateUser(confirmed_cookie, password='supersecure')

    # ------------------------------
    # Ensure that the cookie's extra powers expire after an hour.
    # ------------------------------
    util._TEST_TIME += constants.SECONDS_PER_HOUR
    self.assertRaisesHttpError(403, self._tester.UpdateUser, confirmed_cookie, password='supersecure')

  def testFakeViewfinderLogin(self):
    """Test successful login of the fake viewfinder authority."""
    # Register as mobile user, and then attempt to log in.
    user, device_id = _TestFakeAuthViewfinderUser('register',
                                                  self._tester,
                                                  self._viewfinder_user3_dict,
                                                  self._mobile_device_dict)
    self.assertIsNotNone(user.pwd_hash)

    user2, device_id2 = _TestFakeAuthViewfinderUser('login',
                                                    self._tester,
                                                    self._viewfinder_user3_dict,
                                                    self._mobile_device_dict)
    self.assertEqual(user.user_id, user2.user_id)
    self.assertNotEqual(device_id, device_id2)

    # Login as web user (no device Id)
    user3_no_pwd_dict = deepcopy(self._viewfinder_user3_dict)
    del user3_no_pwd_dict['password']
    user, device_id = _TestFakeAuthViewfinderUser('login', self._tester, user3_no_pwd_dict)
    self.assertEqual(user.user_id, user2.user_id)
    self.assertIsNone(device_id)

    # Login with user which has not registered yet.
    url = self._tester.GetUrl('/login/fakeviewfinder')
    request_dict = {'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION},
                    'auth_info' : {'identity': 'Email:matt@emailscrubbed.com'}}
    self.assertRaisesHttpError(403, auth_test._SendAuthRequest, self._tester, url, 'POST',
                               request_dict=request_dict)

  def testPartialUser(self):
    """Test register and login with an identity/user that is not fully created yet."""
    ident_dict = {'key': 'Email:%s' % self._viewfinder_user_dict['email'], 'authority': 'Viewfinder'}
    response = _AuthViewfinderUser(self._tester, 'register', self._viewfinder_user_dict, ident_dict, None)
    response_dict = json.loads(response.body)

    # Delete the user object.
    user = self._RunAsync(User.Query, self._client, response_dict['user_id'], None)
    self._RunAsync(user.Delete, self._client)

    # Try to log in.
    self.assertRaisesHttpError(403,
                               _AuthViewfinderUser,
                               self._tester,
                               'login',
                               self._viewfinder_user_dict,
                               ident_dict,
                               None)

    # Try to re-register.
    self.assertRaisesHttpError(403,
                               _AuthViewfinderUser,
                               self._tester,
                               'register',
                               self._viewfinder_user_dict,
                               ident_dict,
                               None)

    # Skip validation, since partial user will cause problems.
    self._validate = False


def _GenerateAccessToken(action, tester, device_dict, auth_info_dict, user_cookie=None, use_short_token=True):
  """Sends a request to the Viewfinder auth service, requesting an access token to be emailed
  or messaged to the user. Returns the identity that was created or updated.
  """
  # If use_short_token is true, then a 4-digit code will be in-lined into the email.
  version = message.MAX_SUPPORTED_MESSAGE_VERSION if use_short_token else message.Message.SUPPRESS_AUTH_NAME
  url = tester.GetUrl('/%s/viewfinder' % action)
  request_dict = auth_test._CreateRegisterRequest(device_dict, auth_info_dict, version=version)
  response = auth_test._SendAuthRequest(tester, url, 'POST', user_cookie=user_cookie, request_dict=request_dict)
  return json.loads(response.body)


def _TestGenerateAccessToken(action, tester, device_dict, auth_info_dict, user_cookie=None, use_short_token=True):
  """Invokes the auth API that triggers the email of a Viewfinder access token. Validates that
  an identity was created. Returns the identity that was created or updated.
  """
  response_dict = _GenerateAccessToken(action,
                                       tester,
                                       device_dict,
                                       auth_info_dict,
                                       user_cookie,
                                       use_short_token=use_short_token)

  # Validate the response.
  identity_type, value = Identity.SplitKey(auth_info_dict['identity'])
  expected_digits = 4 if use_short_token or identity_type == 'Phone' else 9
  assert response_dict['token_digits'] == expected_digits, response_dict

  identity = tester._RunAsync(Identity.Query, tester.validator.client, auth_info_dict['identity'], None)

  # Validate the identity.
  tester.validator.ValidateUpdateDBObject(Identity,
                                          key=auth_info_dict['identity'],
                                          authority='Viewfinder',
                                          user_id=identity.user_id,
                                          access_token=identity.access_token,
                                          expires=identity.expires)
  return identity


def _AuthViewfinderUser(tester, action, user_dict, ident_dict, device_dict, user_cookie=None):
  """Registers a user, identity, and device using the Viewfinder auth web service. Returns the
  HTTP response that was returned by the auth service.
  """
  auth_info_dict = {'identity': ident_dict['key']}
  util.SetIfNotNone(auth_info_dict, 'password', user_dict.get('password', None))
  if action == 'register':
    util.SetIfNotNone(auth_info_dict, 'name', user_dict.get('name', None))
    util.SetIfNotNone(auth_info_dict, 'given_name', user_dict.get('given_name', None))
    util.SetIfNotNone(auth_info_dict, 'family_name', user_dict.get('family_name', None))

  if ident_dict['authority'] == 'Viewfinder':
    if 'password' in auth_info_dict and action != 'register':
      # If logging in with a password, no need for 2-step process involving access token.
      url = tester.GetUrl('/%s/viewfinder' % action)
      request_dict = auth_test._CreateRegisterRequest(device_dict,
                                                      auth_info_dict)
    else:
      # First generate the access token.
      _GenerateAccessToken(action, tester, device_dict, auth_info_dict, user_cookie)
      identity = tester._RunAsync(Identity.Query, tester.validator.client, auth_info_dict['identity'], None)
      url = tester.GetUrl('/verify/viewfinder')

      request_dict = {'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION,
                                  'synchronous': True},
                      'identity': identity.key,
                      'access_token': identity.access_token}
  else:
    # 'FakeViewfinder' actually reports as the 'Viewfinder' authority internally.
    assert ident_dict['authority'] == 'FakeViewfinder', ident_dict
    ident_dict['authority'] = 'Viewfinder'
    url = tester.GetUrl('/%s/fakeviewfinder' % action)
    request_dict = auth_test._CreateRegisterRequest(device_dict, auth_info_dict)

  return auth_test._SendAuthRequest(tester, url, 'POST', user_cookie=user_cookie, request_dict=request_dict)


def _TestAuthViewfinderUser(action, tester, user_dict, device_dict=None, user_cookie=None):
  """Called by the ServiceTester in order to test login/viewfinder, link/viewfinder, and
  register/viewfinder calls.
  """
  if 'email' in user_dict:
    ident_dict = {'key': 'Email:%s' % user_dict['email'], 'authority': 'Viewfinder'}
  else:
    ident_dict = {'key': 'Phone:%s' % user_dict['phone'], 'authority': 'Viewfinder'}

  response = _AuthViewfinderUser(tester, action, user_dict, ident_dict, device_dict, user_cookie)

  # Validate confirm_time field. It should be defined for register & login cases, but only if the
  # password is not specified in the login case.
  cookie_user_dict = tester.DecodeUserCookie(tester.GetCookieFromResponse(response))
  if action != 'link' and not (action == 'login' and 'password' in user_dict):
    assert 'confirm_time' in cookie_user_dict, cookie_user_dict
  else:
    assert 'confirm_time' not in cookie_user_dict, cookie_user_dict

  return auth_test._ValidateAuthUser(tester, action, user_dict, ident_dict, device_dict, user_cookie, response)


def _TestFakeAuthViewfinderUser(action, tester, user_dict, device_dict=None, user_cookie=None):
  """Called by the ServiceTester in order to test login/fakeviewfinder and register/fakeviewfinder
  service endpoints.
  """
  if 'email' in user_dict:
    ident_dict = {'key': 'Email:%s' % user_dict['email'], 'authority': 'FakeViewfinder'}
  else:
    ident_dict = {'key': 'Phone:%s' % user_dict['phone'], 'authority': 'FakeViewfinder'}
  response = _AuthViewfinderUser(tester, action, user_dict, ident_dict, device_dict, user_cookie)
  return auth_test._ValidateAuthUser(tester, action, user_dict, ident_dict, device_dict, user_cookie, response)
