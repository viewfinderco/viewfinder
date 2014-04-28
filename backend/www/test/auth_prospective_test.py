# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Authentication tests for prospective users.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import base64
import json
import time
import urllib

from copy import deepcopy
from tornado import options
from viewfinder.backend.base import constants, message, secrets, util
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.user import User
from viewfinder.backend.services.sms_mgr import TestSMSManager
from viewfinder.backend.www.auth_prospective import AuthProspectiveHandler
from viewfinder.backend.www.test import service_base_test


class AuthProspectiveTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(AuthProspectiveTestCase, self).setUp()
    self._CreateSimpleTestAssets()

    # Create prospective user and default invitation.
    self._new_user, self._new_vp_id, self._new_ep_id = self._CreateProspectiveUser()
    self._invitation_url = self._CreateInvitationURL(self._new_vp_id, '/view')

    # Create another viewpoint for the prospective user.
    self._another_vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                                        [(self._episode_id, self._photo_ids)],
                                                        [self._new_user.user_id])

  def testWithCookies(self):
    """Verifies that the invitation grants access to user photos with and without various
    existing cookies.
    """
    # ------------------------------
    # Log in once, with no existing cookie.
    # ------------------------------
    response = self._SendRequest(self._invitation_url)
    user_cookie = self._VerifyInvitationResponse(response, self._new_vp_id)

    # ------------------------------
    # Log in again with same viewpoint_id that's in the existing cookie.
    # ------------------------------
    response = self._SendRequest(self._invitation_url, user_cookie)
    user_cookie = self._VerifyInvitationResponse(response, self._new_vp_id)

    # ------------------------------
    # Now log in with different viewpoint than's in the cookie.
    # ------------------------------
    invitation_url = self._CreateInvitationURL(self._another_vp_id, '/view')
    response = self._SendRequest(invitation_url, user_cookie)
    self._VerifyInvitationResponse(response, self._another_vp_id)

  def testServiceInvitation(self):
    """Tests that prospective user can make a service API call."""
    response = self._SendRequest(self._invitation_url)
    user_cookie = self._VerifyInvitationResponse(response, self._new_vp_id)

    ep_select = self._tester.CreateEpisodeSelection(self._new_ep_id)
    self._tester.QueryEpisodes(user_cookie, [ep_select])

  def testRegisteredUser(self):
    """Verify that an already registered user is redirected to /auth."""
    def _VerifyAuthRedirectResponse(response):
      """Verifies the HTTPResponse has a status code of 302, a location
      header that starts with /auth, and no cookie.
      """
      self.assertEqual(response.code, 302)
      self.assertTrue(response.headers['location'].startswith('/auth'))
      self.assertEqual(self._tester.GetCookieFromResponse(response), '')

    # First login with invitation in order to set prospective cookie.
    response = self._SendRequest(self._invitation_url)
    user_cookie = self._VerifyInvitationResponse(response, self._new_vp_id)

    # Now register the user.
    self._UpdateOrAllocateDBObject(User,
                                   user_id=self._new_user.user_id,
                                   labels=[User.REGISTERED])

    # ------------------------------
    # Log in using invitation URL, with no current cookie.
    # ------------------------------
    response = self._SendRequest(self._invitation_url)
    _VerifyAuthRedirectResponse(response)

    # ------------------------------
    # Log in using invitation URL, with invitation cookie as current cookie.
    # ------------------------------
    response = self._SendRequest(self._invitation_url, user_cookie)
    _VerifyAuthRedirectResponse(response)

    # ------------------------------
    # Log in using invitation URL, with a cookie from a different user as current cookie.
    # ------------------------------
    response = self._SendRequest(self._invitation_url, self._cookie)
    _VerifyAuthRedirectResponse(response)

    # ------------------------------
    # Log in using invitation URL, with a registered user cookie (should not require re-auth).
    # ------------------------------
    registered_cookie = self._tester.GetSecureUserCookie(self._new_user.user_id,
                                                         self._new_user.webapp_dev_id,
                                                         self._new_user.name)
    response = self._SendRequest(self._invitation_url, registered_cookie)
    self.assertEqual(response.code, 302)
    self.assertTrue(response.headers['location'].startswith('/view'))
    self.assertNotEqual(self._tester.GetCookieFromResponse(response), '')

  def testRedirectNext(self):
    """Test that prospective user auth handler will redirect to "next" query parameter."""
    response = self._SendRequest(self._invitation_url + "?next=/foobar", self._cookie)
    self.assertEqual(response.code, 302)
    self.assertEqual(response.headers['location'], '/foobar')

    response = self._SendRequest(self._invitation_url + "?next=//foobar", self._cookie)
    self.assertEqual(response.code, 400)

    response = self._SendRequest(self._invitation_url + "?next=http://google.com", self._cookie)
    self.assertEqual(response.code, 400)

  def testRedirectPhoto(self):
    """Test that a photo redirection returns the signed S3 URL and does *not* set the cookie."""
    next_url = "?next=/episodes/%s/photos/%s.f" % (self._new_ep_id, self._photo_ids[0])
    response = self._SendRequest(self._invitation_url + next_url)
    self.assertEqual(response.code, 302)
    self.assertIn('/fileobjstore/photo/%s.f' % self._photo_ids[0], response.headers['location'])
    self.assertIsNone(self._tester.GetCookieFromResponse(response))

    self._tester.PutPhotoImage(self._cookie, self._new_ep_id, self._photo_ids[0], '.f', 'full image data',
                               content_md5=util.ComputeMD5Base64('full image data'))

    response = self._SendRequest(response.headers['location'], self._cookie)
    self.assertEqual(response.code, 200)
    self.assertEqual(response.body, 'full image data')

    # Ensure that any cookie passed is not disturbed.
    response = self._SendRequest(self._invitation_url + next_url, self._cookie3)
    response_cookie = self._tester.GetCookieFromResponse(response)

    # Get only first value part of each cookie, which excludes the timestamp & sig parts, which may change.
    self.assertEqual(response_cookie.split('|')[0], self._cookie3.split('|')[0])

  def testFirstClick(self):
    """Test that first click of an invitation is a confirmed cookie, second is not."""
    # ------------------------------
    # Validate that first use of the invitation results in a confirmed cookie.
    # ------------------------------
    response = self._SendRequest(self._invitation_url)
    prospective_user_cookie = self._VerifyInvitationResponse(response, self._new_vp_id)
    cookie_dict = self._tester.DecodeUserCookie(prospective_user_cookie)
    self.assertEqual(cookie_dict['confirm_time'], util._TEST_TIME)

    # ------------------------------
    # Validate that second use of the invitation results in unconfirmed cookie.
    # ------------------------------
    response = self._SendRequest(self._invitation_url)
    prospective_user_cookie = self._VerifyInvitationResponse(response, self._new_vp_id)
    cookie_dict = self._tester.DecodeUserCookie(prospective_user_cookie)
    self.assertNotIn('confirm_time', cookie_dict)

  def testShortDomain(self):
    """Test invitation that uses the short domain."""
    # Share with user that has a mobile phone.
    phone_key = 'Phone:+14251234567'
    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._episode_id, self._photo_ids)],
                                          [phone_key])

    prospective_identity = self._RunAsync(Identity.Query, self._client, phone_key, None)
    prospective_user = self._RunAsync(User.Query, self._client, prospective_identity.user_id, None)

    sms_args = TestSMSManager.Instance().phone_numbers[prospective_user.phone]
    url = sms_args[0]['Body'].split(' ')[-1]

    # Add the testing port.
    url = url.replace('.com/', '.com:%s/' % self.get_http_port())
    url = url.replace('https', 'http')

    # Follow the invitation URL.
    response = self._SendRequest(url)
    self.assertEqual(response.code, 302)
    self.assertTrue(response.headers['location'].startswith('https://%s/pr/' % options.options.domain))

    # Add the testing port.
    url = response.headers['location'].replace('.com/', '.com:%s/' % self.get_http_port())
    url = url.replace('https', 'http')

    # Now follow the redirect (add the testing port first).
    response = self._SendRequest(url)
    self.assertEqual(response.code, 302)
    self.assertEqual(response.headers['location'], '/view#conv/v-Vw')

  def testSMSLimit(self):
    """Test that server stops sending SMS messages if the user is not clicking links."""
    # Turn off alert validation at end of test.
    self._skip_validation_for = ['Alerts']

    phone = '+14257349284'

    # Send 5 texts.
    for i in xrange(5):
      self._tester.ShareNew(self._cookie,
                            [(self._episode_id, self._photo_ids)],
                            ['Phone:' + phone])

    sms_list = TestSMSManager.Instance().phone_numbers[phone]

    # First 3 messages should be "normal", 4th should be warning, 5th should not exist. 
    self.assertEqual(len(sms_list), 4)
    self.assertTrue(sms_list[0]['Body'].startswith('Viewfinder User #1 shared photos on Viewfinder'))
    self.assertTrue(sms_list[1]['Body'].startswith('Viewfinder User #1 shared photos on Viewfinder'))
    self.assertTrue(sms_list[2]['Body'].startswith('Viewfinder User #1 shared photos on Viewfinder'))
    self.assertTrue(sms_list[3]['Body'].startswith('You haven\'t viewed photos shared to you on Viewfinder. ' \
                                                   'Do you want to continue receiving these links? If yes, ' \
                                                   'click: https://short.goviewfinder.com/p'))

    # Now follow the link in the last message in order to reset the count.
    url = sms_list[3]['Body'].split(' ')[-1]
    url = url.replace('.com/', '.com:%s/' % self.get_http_port())
    url = url.replace('https', 'http')

    response = self._SendRequest(url)
    self.assertEqual(response.code, 302)
    self.assertTrue(response.headers['location'].startswith('https://%s/pr/' % options.options.domain))

    # Now send more texts and verify that 4 more are sent.
    for i in xrange(5):
      self._tester.ShareNew(self._cookie,
                            [(self._episode_id, self._photo_ids)],
                            ['Phone:' + phone])

    self.assertEqual(len(sms_list), 4)

  def testUnlinkedIdentity(self):
    """ERROR: Identity has been unlinked since invitation was issued."""
    user_dict = {'user_id': self._new_user.user_id,
                 'email': 'prospective@emailscrubbed.com',
                 'name': 'Matt Tracy',
                 'given_name': 'Matt'}
    user, device_id = self._tester.RegisterFakeViewfinderUser(user_dict, None)
    user_cookie = self._GetSecureUserCookie(user, device_id)

    user_dict = {'id': 100}
    self._tester.LinkFacebookUser(user_dict, None, user_cookie)

    self._tester.UnlinkIdentity(user_cookie, 'Email:prospective@emailscrubbed.com')

    response = self._SendRequest(self._invitation_url, self._cookie)
    self.assertEqual(response.code, 403)
    self.assertIn('>The requested link has expired and can no longer be used.<', response.body)

  def testExpiredInvitation(self):
    """ERROR: Try to use expired invitation."""
    util._TEST_TIME += constants.SECONDS_PER_DAY * 30
    response = self._SendRequest(self._invitation_url)
    self.assertEqual(response.code, 403)
    self.assertIn('>The requested link has expired and can no longer be used.<', response.body)

  def testGetPrimaryIdentity(self):
    """Test getting the primary identity from a prospective user."""
    identity = self._RunAsync(self._new_user.QueryPrimaryIdentity, self._client)
    self.assertEqual(identity.key, 'Email:prospective@emailscrubbed.com')

  def _CreateInvitationURL(self, viewpoint_id, default_url):
    """Create an invitation URL for the prospective user created in setUp, giving him access
    to the given viewpoint, and redirecting to "default_url" after authentication.
    """
    short_url = self._RunAsync(Identity.CreateInvitationURL,
                               self._client,
                               self._new_user.user_id,
                               'Email:prospective@emailscrubbed.com',
                               viewpoint_id,
                               default_url)
    return self._tester.GetUrl('/%s%s' % (short_url.group_id, short_url.random_key))

  def _SendRequest(self, url, user_cookie=None):
    """Sends HTTP request to the service URL and returns the response."""
    return self._RunAsync(self.http_client.fetch,
                          url,
                          method='GET',
                          headers={'Cookie': 'user=%s' % user_cookie} if user_cookie is not None else None,
                          follow_redirects=False)

  def _VerifyInvitationResponse(self, response, viewpoint_id):
    """Verifies the HTTPResponse returned from an invitation request. The response should have
    a status code of 200 and contain a cookie that grants access to the specified viewpoint,
    but not to any other viewpoint. Returns the cookie.
    """
    self.assertEqual(response.code, 302)
    self.assertEqual(response.headers['Location'], '/view')

    # Verify that viewpoint_id is contained in cookie.
    cookie = self._tester.GetCookieFromResponse(response)
    cookie_dict = self._tester.DecodeUserCookie(cookie)
    self.assertEqual(cookie_dict['viewpoint_id'], viewpoint_id)

    # Verify that prospective user cookie is a session cookie.
    self.assertNotIn('expires', response.headers['Set-Cookie'])
    self.assertTrue(cookie_dict.get('is_session_cookie', False))

    # Verify that cookie has access to given viewpoint.
    response_dict = self._tester.QueryViewpoints(cookie, [self._tester.CreateViewpointSelection(viewpoint_id)])
    self.assertEqual(len(response_dict['viewpoints']), 1)

    # Verify that cookie only has shallow access to default viewpoint.
    user = self._RunAsync(User.Query, self._client, cookie_dict['user_id'], None)
    vp_select = self._tester.CreateViewpointSelection(user.private_vp_id)
    response_dict = self._tester.QueryViewpoints(cookie, [vp_select])
    self.assertEqual(len(response_dict['viewpoints']), 1)
    self.assertNotIn('activities', response_dict['viewpoints'][0])

    return cookie
