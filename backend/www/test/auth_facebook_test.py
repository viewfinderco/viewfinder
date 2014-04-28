#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Account authorization tests for Facebook and Facebook accounts.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andrew Kimball)']

import json
import mock
import os
import time
import unittest
import urllib

from functools import partial
from tornado import httpclient, ioloop
from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test_timeout, MockAsyncHTTPClient
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.user import User
from viewfinder.backend.www.test import auth_test, facebook_utils, service_base_test


@unittest.skip("needs facebook credentials")
@unittest.skipIf('NO_NETWORK' in os.environ, 'no network')
class AuthFacebookTestCase(service_base_test.ServiceBaseTestCase):
  """Tests authentication via the Facebook OAuth service."""
  def setUp(self):
    super(AuthFacebookTestCase, self).setUp()

    self._facebook_user_dict = {'first_name': 'Andrew', 'last_name': 'Kimball', 'name': 'Andrew Kimball',
                                'id': 'id', 'link': 'http://www.facebook.com/andrew.kimball.50',
                                'timezone':-7, 'locale': 'en_US', 'email': 'andy@facebook.com',
                                'picture': {'data': {'url': 'http://foo.com/pic.jpg',
                                                     'is_silhouette': False}},
                                'verified': True}

    self._facebook_user2_dict = {'name': 'Spencer Kimball', 'id': 'id2'}

    self._mobile_device_dict = {'name': 'Andy\'s IPhone', 'version': '1.0', 'platform': 'IPhone 4S',
                                'os': 'iOS 5.0.1', 'push_token': 'push_token'}

  def testRegisterWebUser(self):
    """Test successful register of web user."""
    # Register as web user, register as mobile user (2nd attempt is error).
    self._tester.RegisterFacebookUser(self._facebook_user_dict)
    self.assertRaisesHttpError(403,
                               self._tester.RegisterFacebookUser,
                               self._facebook_user_dict,
                               self._mobile_device_dict)

  def testRegisterMobileUser(self):
    """Test successful register of mobile user."""
    # Register as mobile user, register as web user (2nd attempt is error).
    self._tester.RegisterFacebookUser(self._facebook_user_dict, self._mobile_device_dict)
    self.assertRaisesHttpError(403,
                               self._tester.RegisterFacebookUser,
                               self._facebook_user_dict)

  def testLoginWebUser(self):
    """Test successful login of web user."""
    # Register as web user, login as web user.
    user, device_id = self._tester.RegisterFacebookUser(self._facebook_user_dict)
    user2, device_id2 = self._tester.LoginFacebookUser(self._facebook_user_dict)
    self.assertEqual(user.user_id, user2.user_id)
    self.assertEqual(device_id, device_id2)

    # And login again as mobile user.
    self._tester.LoginFacebookUser(self._facebook_user_dict, self._mobile_device_dict)

  def testLoginMobileUser(self):
    """Test successful login of mobile user."""
    # Register as web user, login as mobile user.
    user, device_id = self._tester.RegisterFacebookUser(self._facebook_user_dict)
    user2, device_id2 = self._tester.LoginFacebookUser(self._facebook_user_dict, self._mobile_device_dict)
    self.assertEqual(user.user_id, user2.user_id)
    self.assertNotEqual(device_id, device_id2)

    # And login again as web user.
    self._tester.LoginFacebookUser(self._facebook_user_dict)

  def testLinkWebUser(self):
    """Test successful link of web user."""
    # Register as mobile user, link as web user
    user, device_id = self._tester.RegisterFacebookUser(self._facebook_user_dict, self._mobile_device_dict)
    cookie = self._GetSecureUserCookie(user, device_id)
    user2, device_id2 = self._tester.LinkFacebookUser(self._facebook_user2_dict, user_cookie=cookie)
    self.assertEqual(user.user_id, user2.user_id)
    self.assertNotEqual(device_id, device_id2)

    # And link again as mobile user.
    self._tester.LinkFacebookUser(self._facebook_user2_dict, self._mobile_device_dict, user_cookie=cookie)
    self.assertEqual(len(self._tester.ListIdentities(cookie)), 2)

  def testLinkMobileUser(self):
    """Test successful link of mobile user."""
    # Register as web user, link as mobile user.
    user, device_id = self._tester.RegisterFacebookUser(self._facebook_user_dict)
    cookie = self._GetSecureUserCookie(user, device_id)
    self._tester.LinkFacebookUser(self._facebook_user2_dict, self._mobile_device_dict, user_cookie=cookie)

    # And link again as web user.
    self._tester.LinkFacebookUser(self._facebook_user2_dict, user_cookie=cookie)
    self.assertEqual(len(self._tester.ListIdentities(cookie)), 2)

  def testLoginNoExist(self):
    """ERROR: Try to login with Facebook identity that is not linked to a Viewfinder account."""
    self.assertRaisesHttpError(403, self._tester.LoginFacebookUser, self._facebook_user_dict)
    self.assertRaisesHttpError(403, self._tester.LoginFacebookUser, self._facebook_user_dict,
                               self._mobile_device_dict)

  def testAuthenticationFailed(self):
    """ERROR: Fail Facebook authentication (which returns None user_dict)."""
    with mock.patch('tornado.httpclient.AsyncHTTPClient', MockAsyncHTTPClient()) as mock_client:
      mock_client.map(r'https://graph.facebook.com/me\?',
                      lambda request: httpclient.HTTPResponse(request, 400))

      url = self.get_url('/register/facebook?access_token=access_token')
      self.assertRaisesHttpError(401,
                                 auth_test._SendAuthRequest,
                                 self._tester,
                                 url,
                                 'POST',
                                 user_cookie=self._cookie,
                                 request_dict=auth_test._CreateRegisterRequest(self._mobile_device_dict))

  def testMissingAccessToken(self):
    """ERROR: Test error on missing facebook access token."""
    self.assertRaisesHttpError(400,
                               auth_test._SendAuthRequest,
                               self._tester,
                               self.get_url('/register/facebook'),
                               'POST',
                               request_dict=auth_test._CreateRegisterRequest(self._mobile_device_dict))

  @async_test_timeout(timeout=30)
  def testFacebookRegistration(self):
    """Test end-end Facebook registration scenario using a test Facebook
    account.
    """
    self._validate = False

    # Get one facebook test user by querying facebook.
    fu = facebook_utils.FacebookUtils()
    users = fu.QueryFacebookTestUsers(limit=1)
    assert len(users) == 1, users

    def _VerifyAccountStatus(cookie, results):
      u = results['user']
      dev = results['device']
      ident = results['identity']
      self.assertEqual(ident.user_id, u.user_id)
      self.assertTrue(u.name)
      self.assertTrue(u.given_name)
      self.assertTrue(u.family_name)
      self.assertIsNotNone(u.webapp_dev_id)
      [self.assertEqual(getattr(dev, k), v) for k, v in self._mobile_device_dict.items()]

      # Keep querying until notifications are found.
      while True:
        response_dict = self._SendRequest('query_notifications', cookie, {})
        if len(response_dict['notifications']) > 2:
          break
        time.sleep(0.100)

      self.assertEqual(response_dict['notifications'][1]['name'], 'register friend')
      notification = response_dict['notifications'][2]
      self.assertEqual(notification['name'], 'fetch_contacts')
      sort_key = Contact.CreateSortKey(None, notification['timestamp'])
      self.assertEqual(notification['invalidate']['contacts']['start_key'], sort_key)
      self.stop()

    def _VerifyResponse(response):
      """Verify successful registration. Query the identity and
      contacts and verify against the actual test data in facebook.
      """
      self.assertEqual(response.code, 200)
      cookie = self._tester.GetCookieFromResponse(response)
      user_dict = self._tester.DecodeUserCookie(cookie)
      response_dict = json.loads(response.body)

      self.assertTrue('user_id' in user_dict)
      self.assertTrue('device_id' in user_dict)
      self.assertEqual(user_dict['device_id'], response_dict['device_id'])

      with util.DictBarrier(partial(_VerifyAccountStatus, cookie)) as b:
        identity_key = 'FacebookGraph:%s' % users[0]['id']
        Identity.Query(self._client, hash_key=identity_key, col_names=None,
                       callback=b.Callback('identity'))
        User.Query(self._client, hash_key=user_dict['user_id'], col_names=None,
                   callback=b.Callback('user'))
        Device.Query(self._client, hash_key=user_dict['user_id'], range_key=user_dict['device_id'],
                     col_names=None, callback=b.Callback('device'))

    url = self.get_url('/link/facebook') + '?' + \
          urllib.urlencode({'access_token': users[0]['access_token']})
    self.http_client.fetch(url, method='POST',
                           headers={'Content-Type': 'application/json',
                                    'X-Xsrftoken': 'fake_xsrf',
                                    'Cookie': 'user=%s;_xsrf=fake_xsrf' % self._cookie},
                           body=json.dumps(auth_test._CreateRegisterRequest(self._mobile_device_dict)),
                           callback=_VerifyResponse)

  def get_new_ioloop(self):
    """Override get_io_loop() to return IOLoop.instance(). The global IOLoop instance is used
    by self.http_client.fetch in the testFacebookRegistration test.
    """
    return ioloop.IOLoop.instance()


def _TestAuthFacebookUser(action, tester, user_dict, device_dict=None, user_cookie=None):
  """Called by the ServiceTester in order to test login/facebook, link/facebook, and
  register/facebook calls.
  """
  ident_dict = {'key': 'FacebookGraph:%s' % user_dict['id'], 'authority': 'Facebook',
                'access_token': 'access_token'}
  if device_dict:
    device_dict.pop('device_uuid', None)
    device_dict.pop('test_udid', None)

  # Mock responses from Facebook.
  with mock.patch('tornado.httpclient.AsyncHTTPClient', MockAsyncHTTPClient()) as mock_client:
    # Add response to request for an access token.
    mock_client.map(r'https://graph.facebook.com/oauth/access_token',
                    'access_token=%s&expires=3600' % ident_dict['access_token'])

    # Response to request for user info.
    auth_test._AddMockJSONResponse(mock_client, r'https://graph.facebook.com/me\?', user_dict)

    # Add empty response to request for photos and friends.
    auth_test._AddMockJSONResponse(mock_client, r'https://graph.facebook.com/me/photos\?', {'data': []})
    auth_test._AddMockJSONResponse(mock_client, r'https://graph.facebook.com/me/friends\?', {'data': []})

    response = auth_test._AuthFacebookOrGoogleUser(tester, action, user_dict, ident_dict, device_dict, user_cookie)
    return auth_test._ValidateAuthUser(tester, action, user_dict, ident_dict, device_dict, user_cookie, response)
