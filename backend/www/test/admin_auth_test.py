# Copyright 2012 Viewfinder Inc. All Rights Reserved.
# -*- coding: utf-8 -*-

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import json
import re

from functools import partial
from tornado import web
from viewfinder.backend.base import otp
from viewfinder.backend.www import basic_auth
from viewfinder.backend.www.test import service_base_test

class AdminAuthTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(AdminAuthTestCase, self).setUp()
    self._validate = False

  def testJSONAdminAuthenticate(self):
    """Authenticate test-user admin via JSON."""
    otp._ClearUserHistory()
    self._SendJSONRequest('test-user', 'test-password', otp.GetOTP('test-user'), 200, True)
    self.wait()

  def testOTPReuse(self):
    """Verify that reusing an OTP yields no cookie."""
    otp._ClearUserHistory()
    self._SendJSONRequest('test-user', 'test-password', otp.GetOTP('test-user'), 200, True)
    self.wait()
    self._SendJSONRequest('test-user', 'test-password', otp.GetOTP('test-user'), 200, False)
    self.wait()

  def testBadOTP(self):
    """Verify that incorrect OTP value yields no cookie."""
    otp._ClearUserHistory()
    self._SendJSONRequest('test-user', 'test-password', 0, 200, False)
    self.wait()

  def testBadPassword(self):
    """Verify bad password yields no cookie."""
    otp._ClearUserHistory()
    self._SendJSONRequest('test-user', 'wrong-password', otp.GetOTP('test-user'), 200, False)
    self.wait()

  def testBadUser(self):
    """Verify bad user yields no cookie."""
    otp._ClearUserHistory()
    self._SendJSONRequest('wrong-user', 'test-password', otp.GetOTP('test-user'), 200, False)
    self.wait()

  def testHTTPAdminAuthenticate(self):
    """Authenticate test-user admin via HTTP with a form post."""
    otp._ClearUserHistory()
    self._SendHTTPRequest('test-user', 'test-password', otp.GetOTP('test-user'), 302, True)
    self.wait()
    otp._ClearUserHistory()
    self._SendHTTPRequest('test-user', 'wrong-password', otp.GetOTP('test-user'), 200, False)
    self.wait()

  def _SendJSONRequest(self, user, pwd, otp_entry, exp_code, exp_has_cookie):
    """Sends a request using JSON protocol."""
    request_dict = {'username': user, 'password': pwd, 'otp': otp_entry}
    headers={'Content-Type': 'application/json',
             'X-Xsrftoken': 'fake_xsrf',
             'Cookie': '_xsrf=fake_xsrf'}
    url = self._tester.GetUrl('/admin/otp')
    self._tester.http_client.fetch(
      url, callback=partial(self._VerifyAdminAuthResponse, exp_code, exp_has_cookie),
      method='POST', body=json.dumps(request_dict), follow_redirects=False, headers=headers)

  def _SendHTTPRequest(self, user, pwd, otp_entry, exp_code, exp_has_cookie):
    """Sends a request using HTTP protocol."""
    post_body = 'username=%s&password=%s&otp=%s' % (user, pwd, otp_entry)
    headers = {'Content-Type': 'application/x-www-form-urlencoded',
               'X-Xsrftoken': 'fake_xsrf',
               'Cookie': '_xsrf=fake_xsrf'}
    url = self._tester.GetUrl('/admin/otp')
    self._tester.http_client.fetch(
      url, callback=partial(self._VerifyAdminAuthResponse, exp_code, exp_has_cookie),
      method='POST', body=post_body, follow_redirects=False, headers=headers)

  def _VerifyAdminAuthResponse(self, exp_code, exp_has_admin_otp_cookie, response):
    """Deconstructs the admin otp cookie and verifies that test-user
    and timestamp are correct (timestamp within an epsilon of current
    time). Calls self.stop() on completion.
    """
    try:
      self.assertEqual(response.code, exp_code)
      set_cookie = response.headers.get('Set-Cookie', '')
      match = re.compile('admin_otp="(.*)"').match(set_cookie)
      if exp_has_admin_otp_cookie:
        self.assertTrue(match, 'Expecting admin_otp cookie, but none found.')
        cookie = match.group(1)
        decoded_cookie = web.decode_signed_value(self._tester._secret, basic_auth.COOKIE_NAME, cookie)
        admin, expires = json.loads(decoded_cookie)
        self.assertEqual(admin, 'test-user')
      else:
        self.assertFalse(match, 'Expecting no admin_otp cookie, but found one.')
    finally:
      self.stop()

