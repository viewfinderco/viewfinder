#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Account authorization tests for Facebook and Google accounts.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andrew Kimball)']

import json
import mock
import os
import time
import unittest
import urllib

from copy import deepcopy
from cStringIO import StringIO
from tornado import httpclient, options
from tornado.ioloop import IOLoop
from urlparse import urlparse
from viewfinder.backend.base import message, util
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.notification import Notification
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.user import User
from viewfinder.backend.op.fetch_contacts_op import FetchContactsOperation
from viewfinder.backend.www import auth
from viewfinder.backend.www.test import service_base_test
from viewfinder.backend.www.www_util import GzipEncode


@unittest.skipIf('NO_NETWORK' in os.environ, 'no network')
class AuthTestCase(service_base_test.ServiceBaseTestCase):
  """Initializes the test datastore and the viewfinder schema.
  """
  def setUp(self):
    super(AuthTestCase, self).setUp()
    self._CreateSimpleTestAssets()

    self._google_user_dict = {'family_name': 'Kimball', 'name': 'Andrew Kimball', 'locale': 'en',
                              'gender': 'male', 'email': 'kimball.andy@emailscrubbed.com',
                              'link': 'https://plus.google.com/id',
                              'given_name': 'Andrew', 'id': 'id', 'verified_email': True}

    self._facebook_user_dict = {'first_name': 'Andrew', 'last_name': 'Kimball', 'name': 'Andrew Kimball',
                                'id': 'id', 'link': 'http://www.facebook.com/andrew.kimball.50',
                                'timezone':-7, 'locale': 'en_US', 'email': 'andy@facebook.com',
                                'picture': {'data': {'url': 'http://foo.com/pic.jpg',
                                                     'is_silhouette': False}},
                                'verified': True}

    self._viewfinder_user_dict = {'name': 'Andy Kimball', 'given_name': 'Andrew', 'email': 'andy@emailscrubbed.com'}

    self._mobile_device_dict = {'name': 'Andy\'s IPhone', 'version': '1.0', 'platform': 'IPhone 4S',
                                'os': 'iOS 5.0.1', 'push_token': 'push_token',
                                'device_uuid': '926744AC-8540-4103-9F3F-C84AA2F6D648',
                                'test_udid': '7d527095d4e0539aba40c852547db5da00000000',
                                'country': 'US', 'language': 'en'}

    self._prospective_user, _, _ = self._CreateProspectiveUser()
    self._register_user_dict = {'email': self._prospective_user.email,
                                'name': 'Jimmy John',
                                'given_name': 'Jimmy',
                                'family_name': 'John'}

  def tearDown(self):
    super(AuthTestCase, self).tearDown()
    options.options.freeze_new_accounts = False

  def testRegisterWithCookie(self):
    """Register user, overriding current logged-in user."""
    # Override registered user.
    user, device_id = self._tester.RegisterGoogleUser(self._google_user_dict)
    google_cookie = self._GetSecureUserCookie(user, device_id)
    user2, _ = self._tester.RegisterFacebookUser(self._facebook_user_dict,
                                                 self._mobile_device_dict,
                                                 user_cookie=google_cookie)
    self.assertNotEqual(user.user_id, user2.user_id)

    # Override prospective user.
    cookie = self._GetSecureUserCookie(self._prospective_user, self._prospective_user.webapp_dev_id)
    user, _ = self._tester.RegisterViewfinderUser(self._viewfinder_user_dict, user_cookie=cookie)
    self.assertNotEqual(self._prospective_user.user_id, user.user_id)

    # Override with registration of prospective user.
    user, _ = self._tester.RegisterViewfinderUser(self._register_user_dict, user_cookie=self._cookie)
    self.assertNotEqual(user.user_id, self._user.user_id)

  def testEmailAlertSettings(self):
    """Test that email/push alert settings are updated properly during registration."""
    def _ValidateAlerts(email_alerts, push_alerts):
      settings = self._RunAsync(AccountSettings.QueryByUser, self._client, self._prospective_user.user_id, None)
      self.assertEqual(settings.email_alerts, email_alerts)
      self.assertEqual(settings.sms_alerts, AccountSettings.SMS_NONE)
      self.assertEqual(settings.push_alerts, push_alerts)

    # Skip cleanup validation of alerts because a new device is created in this test that did not receive
    # notifications sent as part of setUp() call.
    self._skip_validation_for = ['Alerts']

    # Register a prospective user using the web device.
    cookie = self._GetSecureUserCookie(self._prospective_user, self._prospective_user.webapp_dev_id)
    _ValidateAlerts(AccountSettings.EMAIL_ON_SHARE_NEW, AccountSettings.PUSH_NONE)
    user, device_id = self._tester.RegisterViewfinderUser(self._register_user_dict)
    _ValidateAlerts(AccountSettings.EMAIL_ON_SHARE_NEW, AccountSettings.PUSH_NONE)

    # Update the user's email alert setting and validate the changed setting.
    self._tester.UpdateUser(cookie, settings_dict={'email_alerts': 'none'})
    _ValidateAlerts(AccountSettings.EMAIL_NONE, AccountSettings.PUSH_NONE)

    # Login and register a new mobile device and validate that email alerts were turned off
    # and push alerts turned on.
    self._tester.UpdateUser(cookie, settings_dict={'email_alerts': 'on_share_new'})
    self._tester.LoginViewfinderUser(self._register_user_dict, self._mobile_device_dict)
    _ValidateAlerts(AccountSettings.EMAIL_NONE, AccountSettings.PUSH_ALL)

    # Turn off push alerts, and then re-login, and validate that they were not turned back on.
    self._tester.UpdateUser(cookie, settings_dict={'push_alerts': 'none'})
    self._tester.LoginViewfinderUser(self._register_user_dict)
    self._tester.LoginViewfinderUser(self._register_user_dict, self._mobile_device_dict)
    _ValidateAlerts(AccountSettings.EMAIL_NONE, AccountSettings.PUSH_NONE)

  def testSmsAlertSettings(self):
    """Test that SMS/push alert settings are updated properly during registration."""
    def _ValidateAlerts(sms_alerts, push_alerts):
      settings = self._RunAsync(AccountSettings.QueryByUser, self._client, prospective_user.user_id, None)
      self.assertEqual(settings.email_alerts, AccountSettings.EMAIL_NONE)
      self.assertEqual(settings.sms_alerts, sms_alerts)
      self.assertEqual(settings.push_alerts, push_alerts)

    # Skip cleanup validation of alerts because a new device is created in this test that did not receive
    # notifications sent as part of setUp() call.
    self._skip_validation_for = ['Alerts']

    # Create prospective user with mobile phone.
    ident_key = 'Phone:+14251234567'
    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._episode_id, self._photo_ids)],
                                          [ident_key])

    prospective_ident = self._RunAsync(Identity.Query, self._client, ident_key, None)
    prospective_user = self._RunAsync(User.Query, self._client, prospective_ident.user_id, None)

    register_user_dict = {'phone': prospective_user.phone,
                          'name': 'Jimmy John',
                          'given_name': 'Jimmy',
                          'family_name': 'John'}

    # Register a prospective user using the web device.
    cookie = self._GetSecureUserCookie(prospective_user, prospective_user.webapp_dev_id)
    _ValidateAlerts(AccountSettings.SMS_ON_SHARE_NEW, AccountSettings.PUSH_NONE)
    user, device_id = self._tester.RegisterViewfinderUser(register_user_dict)
    _ValidateAlerts(AccountSettings.SMS_ON_SHARE_NEW, AccountSettings.PUSH_NONE)

    # Login and register a new mobile device and validate that SMS alerts were turned off
    # and push alerts turned on.
    self._tester.LoginViewfinderUser(register_user_dict, self._mobile_device_dict)
    _ValidateAlerts(AccountSettings.SMS_NONE, AccountSettings.PUSH_ALL)

    # Turn off push alerts, and then re-login, and validate that they were not turned back on.
    self._tester.UpdateUser(cookie, settings_dict={'push_alerts': 'none'})
    self._tester.LoginViewfinderUser(register_user_dict)
    self._tester.LoginViewfinderUser(register_user_dict, self._mobile_device_dict)
    _ValidateAlerts(AccountSettings.SMS_NONE, AccountSettings.PUSH_NONE)

  def testMultipleAuthorities(self):
    """Test multiple authorities that authenticate same identity."""
    # Login as Google user, then as Viewfinder user with same email, then again as same Google user.
    self._tester.RegisterGoogleUser({'name': 'Mike Purtell', 'email': 'mike@emailscrubbed.com', 'verified_email': True})
    self._tester.LoginViewfinderUser({'email': 'mike@emailscrubbed.com'},
                                     self._mobile_device_dict)

    identity = self._RunAsync(Identity.Query, self._client, 'Email:mike@emailscrubbed.com', None)
    self.assertEqual(identity.authority, 'Viewfinder')
    self.assertEqual(identity.expires, 0)

    self._tester.LoginGoogleUser({'email': 'mike@emailscrubbed.com', 'verified_email': True})

    identity = self._RunAsync(Identity.Query, self._client, 'Email:mike@emailscrubbed.com', None)
    self.assertEqual(identity.authority, 'Google')

  def testLoginWithCookie(self):
    """Test successful login override of current logged-in user."""
    # Login with cookie from same user.
    user, device_id = self._tester.RegisterFacebookUser(self._facebook_user_dict, self._mobile_device_dict)
    facebook_cookie = self._GetSecureUserCookie(user, device_id)
    self._tester.LoginFacebookUser(self._facebook_user_dict, self._mobile_device_dict, user_cookie=facebook_cookie)

    # Login with cookie from different user.
    user, device_id = self._tester.RegisterGoogleUser(self._google_user_dict)
    google_cookie = self._GetSecureUserCookie(user, device_id)
    self._tester.LoginFacebookUser(self._facebook_user_dict, self._mobile_device_dict, user_cookie=google_cookie)

    # Login with cookie from prospective user.
    cookie = self._GetSecureUserCookie(self._prospective_user, self._prospective_user.webapp_dev_id)
    self._tester.LoginFacebookUser(self._facebook_user_dict, user_cookie=cookie)

  def testErrorFormat(self):
    """Test that error returned by the service handler is properly formed."""
    ident_dict = {'key': 'Email:andy@emailscrubbed.com', 'authority': 'FakeViewfinder'}
    auth_info_dict = {'identity': ident_dict['key']}
    url = self._tester.GetUrl('/login/viewfinder')
    request_dict = _CreateRegisterRequest(self._mobile_device_dict, auth_info_dict, synchronous=False)
    response = _SendAuthRequest(self._tester, url, 'POST', request_dict=request_dict, allow_errors=[403])

    self.assertEqual(json.loads(response.body),
                     {'error': {'id': 'NO_USER_ACCOUNT',
                                'method': 'login',
                                'message': 'We can\'t find your Viewfinder account. Are you sure you used ' +
                                           'andy@emailscrubbed.com to sign up?'}})

  def testLoginWithProspective(self):
    """ERROR: Try to log into a prospective user account."""
    self.assertRaisesHttpError(403, self._tester.LoginViewfinderUser, self._register_user_dict)

  def testLinkWithProspective(self):
    """ERROR: Try to link another identity to a prospective user."""
    # Link with cookie from prospective user, using Facebook account that is not yet linked.
    cookie = self._GetSecureUserCookie(self._prospective_user, self._prospective_user.webapp_dev_id)
    self.assertRaisesHttpError(403, self._tester.LinkFacebookUser, self._facebook_user_dict, user_cookie=cookie)

  def testLinkAlreadyLinked(self):
    """ERROR: Try to link a Google account that is already linked to a different Viewfinder account."""
    user, device_id = self._tester.RegisterFacebookUser(self._facebook_user_dict)
    facebook_cookie = self._GetSecureUserCookie(user, device_id)
    self._tester.RegisterGoogleUser(self._google_user_dict)
    self.assertRaisesHttpError(403, self._tester.LinkGoogleUser, self._google_user_dict,
                               self._mobile_device_dict, user_cookie=facebook_cookie)

  def testUpdateFriendAttribute(self):
    """Update name of a user and ensure that each friend is notified."""
    # Create a prospective user by sharing with an email.
    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._episode_id, self._photo_ids)],
                                          ['Email:kimball.andy@emailscrubbed.com', self._user2.user_id])

    # Register the user and verify friends are notified.
    self._tester.RegisterGoogleUser(self._google_user_dict)
    response_dict = self._tester.QueryNotifications(self._cookie2, 1, scan_forward=False)
    self.assertEqual(response_dict['notifications'][0]['invalidate'], {u'users': [5]})

  def testRegisterContact(self):
    """Register an identity that is the target of a contact, which will
    be bound to a user_id as a result.
    """
    # Create a contact.
    user_dict = {'name': 'Andrew Kimball', 'email': 'kimball.andy@emailscrubbed.com', 'verified_email': True}
    identity_key = 'Email:%s' % user_dict['email']
    contact_dict = Contact.CreateContactDict(self._user.user_id,
                                             [(identity_key, None)],
                                             util._TEST_TIME,
                                             Contact.GMAIL,
                                             name=user_dict['name'])
    self._UpdateOrAllocateDBObject(Contact, **contact_dict)

    # Register the new user.
    user, device_id = self._tester.RegisterGoogleUser(user_dict)
    response_dict = self._tester.QueryNotifications(self._cookie, 1, scan_forward=False)
    self.assertEqual([notify_dict['name'] for notify_dict in response_dict['notifications']],
                     ['first register contact'])

  def testRegisterProspectiveContact(self):
    """Register an identity that is the target of a contact (that is still a prospective user)."""
    for user_id in [self._user.user_id, self._user2.user_id]:
      # Create several contacts.
      identity_key = 'Email:%s' % self._prospective_user.email
      contact_dict = Contact.CreateContactDict(user_id,
                                               [(identity_key, None)],
                                               util._TEST_TIME,
                                               Contact.GMAIL,
                                               name='Mr. John')
      self._UpdateOrAllocateDBObject(Contact, **contact_dict)

    # Register the prospective user.
    user, device_id = self._tester.RegisterViewfinderUser(self._register_user_dict)

    # Expect friend & contact notifications.
    response_dict = self._tester.QueryNotifications(self._cookie, 2, scan_forward=False)
    self.assertEqual([notify_dict['name'] for notify_dict in response_dict['notifications']],
                     ['register friend', 'first register contact'])

    # Expect only contact notification.
    response_dict = self._tester.QueryNotifications(self._cookie2, 1, scan_forward=False)
    self.assertEqual([notify_dict['name'] for notify_dict in response_dict['notifications']],
                     ['first register contact'])

    # Expect only friend notification.
    cookie = self._GetSecureUserCookie(self._prospective_user, self._prospective_user.webapp_dev_id)
    response_dict = self._tester.QueryNotifications(cookie, 2, scan_forward=False)
    self.assertEqual([notify_dict['name'] for notify_dict in response_dict['notifications']],
                     ['register friend', 'share_new'])

  def testNewIdentityOnly(self):
    """Register existing user and device, but create new identity via link."""
    user, device_id = self._tester.RegisterGoogleUser(self._google_user_dict, self._mobile_device_dict)
    cookie = self._GetSecureUserCookie(user, device_id)
    self._mobile_device_dict['device_id'] = device_id
    self._tester.LinkFacebookUser(self._facebook_user_dict, self._mobile_device_dict, cookie)

  def testNewDeviceOnly(self):
    """Register existing user and identity, but create new device as part of login."""
    self._tester.RegisterGoogleUser(self._google_user_dict)
    self._tester.LoginGoogleUser(self._google_user_dict, self._mobile_device_dict)

  def testDuplicateToken(self):
    """Register device with push token that is already in use by another device."""
    self._tester.RegisterGoogleUser(self._google_user_dict, self._mobile_device_dict)
    self._tester.RegisterFacebookUser(self._facebook_user_dict, self._mobile_device_dict)

  def testAsyncRequest(self):
    """Send async register request."""
    ident_dict = {'key': 'Email:andy@emailscrubbed.com', 'authority': 'FakeViewfinder'}
    auth_info_dict = {'identity': ident_dict['key']}
    url = self._tester.GetUrl('/link/fakeviewfinder')
    request_dict = _CreateRegisterRequest(self._mobile_device_dict, auth_info_dict, synchronous=False)
    response = _SendAuthRequest(self._tester, url, 'POST', request_dict=request_dict, user_cookie=self._cookie)
    response_dict = json.loads(response.body)

    self._validate = False

    # Wait until notification is written by the background fetch_contacts op.
    while True:
      notification = self._RunAsync(Notification.QueryLast, self._client, response_dict['user_id'])
      if notification.name == 'fetch_contacts':
        self.assertEqual(notification.op_id, response_dict['headers']['op_id'])
        break
      self._RunAsync(IOLoop.current().add_timeout, time.time() + .1)

  def testDeviceNoUser(self):
    """ERROR: Try to register existing device without existing user."""
    user, device_id = self._tester.RegisterGoogleUser(self._google_user_dict, self._mobile_device_dict)
    self._mobile_device_dict['device_id'] = device_id
    self.assertRaisesHttpError(403, self._tester.RegisterFacebookUser, self._facebook_user_dict,
                               self._mobile_device_dict)

  def testDeviceNotOwned(self):
    """ERROR: Try to register existing device that is not owned by the
    existing user.
    """
    self._tester.RegisterGoogleUser(self._google_user_dict, self._mobile_device_dict)
    self._mobile_device_dict['device_id'] = 1000
    self.assertRaisesHttpError(403, self._tester.RegisterGoogleUser, self._google_user_dict,
                               self._mobile_device_dict)

  def testRegisterFreezeNewAccounts(self):
    """ERROR: Verify that attempt to register fails if --freeze_new_accounts
    is true. This is the kill switch the server can throw to stop the tide
    of incoming account registrations.
    """
    options.options.freeze_new_accounts = True
    exc = self.assertRaisesHttpError(403, self._tester.RegisterGoogleUser, self._google_user_dict,
                                     self._mobile_device_dict)
    error_dict = json.loads(exc.response.body)
    self.assertEqual(error_dict['error']['message'], auth._FREEZE_NEW_ACCOUNTS_MESSAGE)
    self.assertRaisesHttpError(403, self._tester.RegisterFacebookUser, self._facebook_user_dict)

  def testLoginWithUnboundIdentity(self):
    """ERROR: Try to login with an identity that exists, but is not bound to a user."""
    self._UpdateOrAllocateDBObject(Identity, key='Email:andy@emailscrubbed.com')
    self.assertRaisesHttpError(403,
                               self._tester.LoginViewfinderUser,
                               self._viewfinder_user_dict,
                               self._mobile_device_dict)

  def testBadRequest(self):
    """ERROR: Verify that various malformed and missing register fields result
    in a bad request (400) error.
    """
    # Missing request dict.
    url = self.get_url('/register/facebook') + '?' + urllib.urlencode({'access_token': 'dummy'})
    self.assertRaisesHttpError(400, _SendAuthRequest, self._tester, url, 'POST', request_dict='')

    # Malformed request dict.
    self.assertRaisesHttpError(400, _SendAuthRequest, self._tester, url, 'POST', request_dict={'device': 'foo'})

  def testRegisterExisting(self):
    """ERROR: Try to register a user that already exists."""
    self._tester.RegisterViewfinderUser(self._viewfinder_user_dict)
    self.assertRaisesHttpError(403,
                               self._tester.RegisterViewfinderUser,
                               self._viewfinder_user_dict,
                               self._mobile_device_dict)

  def testLogout(self):
    """Ensure that logout sends back a cookie with an expiration time."""
    url = self._tester.GetUrl('/logout')
    response = _SendAuthRequest(self._tester, url, 'GET', user_cookie=self._cookie)
    self.assertEqual(response.code, 302)
    self.assertEqual(response.headers['location'], '/')
    self.assertIn('user', response.headers['Set-Cookie'])
    self.assertIn('expires', response.headers['Set-Cookie'])
    self.assertIn('Domain', response.headers['Set-Cookie'])

  def testSessionCookie(self):
    """Test "use_session_cookie" option in auth request."""
    # First register a user, requesting a session cookie.
    auth_info_dict = {'identity': 'Email:andy@emailscrubbed.com',
                      'name': 'Andy Kimball',
                      'given_name': 'Andy',
                      'password': 'supersecure'}
    url = self._tester.GetUrl('/register/viewfinder')
    request_dict = _CreateRegisterRequest(None, auth_info_dict)
    response = _SendAuthRequest(self._tester, url, 'POST', request_dict=request_dict)
    self.assertNotIn('Set-Cookie', response.headers)

    identity = self._tester._RunAsync(Identity.Query, self._client, auth_info_dict['identity'], None)
    url = self._tester.GetUrl('/verify/viewfinder')
    request_dict = {'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION,
                                'synchronous': True},
                    'identity': identity.key,
                    'access_token': identity.access_token,
                    'use_session_cookie': True}
    response = _SendAuthRequest(self._tester, url, 'POST', request_dict=request_dict)
    self.assertNotIn('expires', response.headers['Set-Cookie'])
    cookie_user_dict = self._tester.DecodeUserCookie(self._tester.GetCookieFromResponse(response))
    self.assertTrue(cookie_user_dict.get('is_session_cookie', False))

    # Now log in and request a session cookie.
    del auth_info_dict['name']
    del auth_info_dict['given_name']
    url = self._tester.GetUrl('/login/viewfinder')
    request_dict = _CreateRegisterRequest(None, auth_info_dict, synchronous=False)
    response = _SendAuthRequest(self._tester, url, 'POST', request_dict=request_dict)
    self.assertIn('expires', response.headers['Set-Cookie'])

    request_dict['use_session_cookie'] = True
    response = _SendAuthRequest(self._tester, url, 'POST', request_dict=request_dict)
    self.assertNotIn('expires', response.headers['Set-Cookie'])
    cookie = self._tester.GetCookieFromResponse(response)
    cookie_user_dict = self._tester.DecodeUserCookie(cookie)
    self.assertTrue(cookie_user_dict.get('is_session_cookie', False))

    # Now use the session cookie to make a service request and verify it's preserved.
    request_dict = {'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION, 'synchronous': True}}

    headers = {'Content-Type': 'application/json',
               'X-Xsrftoken': 'fake_xsrf',
               'Cookie': '_xsrf=fake_xsrf;user=%s' % cookie}

    response = self._RunAsync(self.http_client.fetch,
                              self._tester.GetUrl('/service/query_followed'),
                              method='POST',
                              body=json.dumps(request_dict),
                              headers=headers)

    cookie_user_dict = self._tester.DecodeUserCookie(self._tester.GetCookieFromResponse(response))
    self.assertTrue(cookie_user_dict.get('is_session_cookie', False))


def _CreateRegisterRequest(device_dict=None, auth_info_dict=None, synchronous=True,
                           version=message.MAX_SUPPORTED_MESSAGE_VERSION):
  """Returns a new AUTH_REQUEST dict that has been populated with information from the
  specified dicts.
  """
  request_dict = {'headers': {'version': version}}
  util.SetIfNotNone(request_dict, 'device', device_dict)
  util.SetIfNotNone(request_dict, 'auth_info', auth_info_dict)
  if synchronous:
    request_dict['headers']['synchronous'] = True
  return request_dict


def _AddMockJSONResponse(mock_client, url, response_dict):
  """Add a mapping entry to the mock client such that requests to
  "url" will return an HTTP response containing the JSON-formatted
  "response_dict".
  """
  def _CreateResponse(request):
    return httpclient.HTTPResponse(request, 200,
                                   headers={'Content-Type': 'application/json'},
                                   buffer=StringIO(json.dumps(response_dict)))

  mock_client.map(url, _CreateResponse)


def _SendAuthRequest(tester, url, http_method, user_cookie=None, request_dict=None, allow_errors=None):
  """Sends request to auth service. If "request_dict" is defined, dumps it as a JSON body.
  If "user_cookie" is defined, automatically adds a "Cookie" header. Raises an HTTPError if
  an HTTP error is returned, unless the error code is part of the "allow_errors" set. Returns
  the HTTP response object on success.
  """
  headers = {'Content-Type': 'application/json',
             'Content-Encoding': 'gzip'}
  if user_cookie is not None:
    headers['Cookie'] = 'user=%s' % user_cookie
  # All requests are expected to have xsrf cookie/header.
  headers['X-Xsrftoken'] = 'fake_xsrf'
  headers['Cookie'] = headers['Cookie'] + ';_xsrf=fake_xsrf' if headers.has_key('Cookie') else '_xsrf=fake_xsrf'

  with mock.patch.object(FetchContactsOperation, '_SKIP_UPDATE_FOR_TEST', True):
    response = tester._RunAsync(tester.http_client.fetch, url, method=http_method,
                                body=None if request_dict is None else GzipEncode(json.dumps(request_dict)),
                                headers=headers, follow_redirects=False)
  if response.code >= 400:
    if allow_errors is None or response.code not in allow_errors:
      response.rethrow()
  return response


def _AuthFacebookOrGoogleUser(tester, action, user_dict, ident_dict, device_dict, user_cookie):
  """Registers a user, identity, and device using the auth web service. The interface to Facebook
  or Google is mocked, with the contents of "user_dict" returned in lieu of what the real service
  would return. If "device_dict" is None, then simulates the web experience; else simulates the
  mobile device experience. If "user_cookie" is not None, then simulates case where calling user
  is already logged in when registering the new user. Returns the HTTP response that was returned
  by the auth service.
  """
  if device_dict is None:
    # Web client.
    url = tester.GetUrl('/%s/%s' % (action, ident_dict['authority'].lower()))
    response = _SendAuthRequest(tester, url, 'GET', user_cookie=user_cookie)
    assert response.code == 302, response.code

    # Invoke authentication again, this time sending code."""
    url = tester.GetUrl('/%s/%s?code=code' % (action, ident_dict['authority'].lower()))
    response = _SendAuthRequest(tester, url, 'GET', user_cookie=user_cookie)
    assert response.code == 302, response.code
    assert response.headers['location'].startswith('/view')
  else:
    if ident_dict['authority'] == 'Facebook':
      url = tester.GetUrl('/%s/facebook?access_token=access_token' % action)
    else:
      url = tester.GetUrl('/%s/google?refresh_token=refresh_token' % action)

    request_dict = _CreateRegisterRequest(device_dict)
    response = _SendAuthRequest(tester, url, 'POST', user_cookie=user_cookie, request_dict=request_dict)

  return response


def _ValidateAuthUser(tester, action, user_dict, ident_dict, device_dict, user_cookie, auth_response):
  """Validates an auth action that has taken place and resulted in the HTTP response given
  by "auth_response".
  """
  validator = tester.validator

  # Validate the response from a GET (device_dict is None) or POST to auth service.
  if device_dict is None:
    # Get the id of the user that should have been created by the registration.
    actual_identity = tester._RunAsync(Identity.Query, validator.client, ident_dict['key'], None)
    actual_user_id = actual_identity.user_id
  else:
    # Extract the user_id and device_id from the JSON response.
    response_dict = json.loads(auth_response.body)
    actual_op_id = response_dict['headers']['op_id']
    actual_user_id = response_dict['user_id']
    actual_device_id = response_dict.get('device_id', None)

  # Verify that the cookie in the response contains the correct information.
  cookie_user_dict = tester.DecodeUserCookie(tester.GetCookieFromResponse(auth_response))
  assert cookie_user_dict['user_id'] == actual_user_id, (cookie_user_dict, actual_user_id)
  assert device_dict is None or 'device_id' not in device_dict or \
         cookie_user_dict['device_id'] == device_dict['device_id'], \
         (cookie_user_dict, device_dict)

  actual_user = tester._RunAsync(User.Query, validator.client, actual_user_id, None)
  if device_dict is None:
    # If no mobile device was used, then web device id is expected.
    actual_device_id = actual_user.webapp_dev_id

  # Get notifications that were created. There could be up to 2: a register_user notification and
  # a fetch_contacts notification (in link case).
  notification_list = tester._RunAsync(Notification.RangeQuery,
                                       tester.validator.client,
                                       actual_user_id,
                                       range_desc=None,
                                       limit=3,
                                       col_names=None,
                                       scan_forward=False)
  if device_dict is None:
    actual_op_id = notification_list[1 if action == 'link' else 0].op_id

  # Determine what the registered user's id should have been.
  if user_cookie is None or action != 'link':
    expected_user_id = None
  else:
    expected_user_id, device_id = tester.GetIdsFromCookie(user_cookie)

  expected_identity = validator.GetModelObject(Identity, ident_dict['key'], must_exist=False)
  if expected_identity is not None:
    # Identity already existed, so expect registered user's id to equal the user id of that identity.
    expected_user_id = expected_identity.user_id

  # Verify that identity is linked to expected user.
  assert expected_user_id is None or expected_user_id == actual_user_id, \
         (expected_user_id, actual_user_id)

  # Validate the device if it should have been created.
  if device_dict is None:
    expected_device_dict = None
  else:
    expected_device_dict = deepcopy(device_dict)
    if 'device_id' not in device_dict:
      expected_device_dict['device_id'] = actual_device_id

  # Re-map picture element for Facebook authority (Facebook changed format in Oct 2012).
  scratch_user_dict = deepcopy(user_dict)
  if ident_dict['authority'] == 'Facebook':
    if device_dict is None:
      scratch_user_dict['session_expires'] = ['3600']
    if 'picture' in scratch_user_dict:
      scratch_user_dict['picture'] = scratch_user_dict['picture']['data']['url']
  elif ident_dict['authority'] == 'Viewfinder' and action != 'register':
    # Only use name in registration case.
    scratch_user_dict.pop('name', None)

  # Validate the Identity object.
  expected_ident_dict = deepcopy(ident_dict)
  expected_ident_dict.pop('json_attrs', None)
  if ident_dict['authority'] == 'Viewfinder':
    identity = tester._RunAsync(Identity.Query, tester.validator.client, ident_dict['key'], None)
    expected_ident_dict['access_token'] = identity.access_token
    expected_ident_dict['expires'] = identity.expires

  # Validate the User object.
  expected_user_dict = {}
  before_user = validator.GetModelObject(User, actual_user_id, must_exist=False)
  before_user_dict = {} if before_user is None else before_user._asdict()
  for k, v in scratch_user_dict.items():
    user_key = auth.AuthHandler._AUTH_ATTRIBUTE_MAP.get(k, None)
    if user_key is not None:
      if before_user is None or getattr(before_user, user_key) is None:
        expected_user_dict[auth.AuthHandler._AUTH_ATTRIBUTE_MAP[k]] = v

      # Set facebook email if it has not yet been set.
      if user_key == 'email' and ident_dict['authority'] == 'Facebook':
        if before_user is None or getattr(before_user, 'facebook_email') is None:
          expected_user_dict['facebook_email'] = v


  expected_user_dict['user_id'] = actual_user_id
  expected_user_dict['webapp_dev_id'] = actual_user.webapp_dev_id

  op_dict = {'op_timestamp': util._TEST_TIME,
             'op_id': notification_list[1 if action == 'link' else 0].op_id,
             'user_id': actual_user_id,
             'device_id': actual_device_id}

  if expected_device_dict:
    expected_device_dict.pop('device_uuid', None)
    expected_device_dict.pop('test_udid', None)

  is_prospective = before_user is None or not before_user.IsRegistered()
  validator.ValidateUpdateUser('first register contact' if is_prospective else 'link contact',
                               op_dict,
                               expected_user_dict,
                               expected_ident_dict,
                               device_dict=expected_device_dict)
  after_user_dict = validator.GetModelObject(User, actual_user_id)._asdict()

  if expected_identity is not None:
    expected_ident_dict['user_id'] = expected_identity.user_id
  if action == 'link':
    ignored_keys = ['user_id', 'webapp_dev_id']
    if 'user_id' not in expected_ident_dict and all(k in ignored_keys for k in expected_user_dict.keys()):
      # Only notify self if it hasn't been done through Friends.
      validator.ValidateUserNotification('register friend self', actual_user_id, op_dict)

    # Validate fetch_contacts notification. 
    op_dict['op_id'] = notification_list[0].op_id
    invalidate = {'contacts': {'start_key': Contact.CreateSortKey(None, util._TEST_TIME)}}
    validator.ValidateNotification('fetch_contacts', actual_user_id, op_dict, invalidate)

  return actual_user, actual_device_id if device_dict is not None else None
