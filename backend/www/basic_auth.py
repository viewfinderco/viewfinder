#!/usr/bin/env python
#
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Provides HTTP basic authentication for RequestHandlers.

Any handler which provides access to site administration or monitoring
functionality must subclass BasicAuthHandler. This in turn requires that
HTTP requests use scheme 'https', or response is HTTP/403 -
Forbidden. If a verified username/password for SRE access is not
included with the result, then returns HTTP/401 - Unauthorized.

All administration handlers should be decorated with
@handler.authenticated. After HTTP basic authentication has been
established, this decorator invokes get_current_user(), which verifies
the state of the secure "admin_otp" cookie. This cookie is a
single-day token, established via one time password (OTP). It combines
the basic auth user, password and an expiration time. If the cookie is
missing, expired, or doesn't match basic auth username/password
combination, then the user is redirected to the login_url page, which
prompts for an OTP token. Once provided, the "admin_otp" cookie is
established and the user is redirected to the original page.

  BasicAuthHandler: handler with HTTP basic authentication.
  OTPEntryHandler: handler for OTP entry; login_url for AdminServer.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'


import base64
import json
import logging
import re
import time

from tornado import httputil, template, web
from viewfinder.backend.base import otp


# Cookie name.
COOKIE_NAME = 'admin_otp'
# Cookie expiration on otp authorization (in seconds).
COOKIE_EXPIRATION = 23 * 60 * 60


class BasicAuthHandler(web.RequestHandler):
  """All handlers supplied to AdminServer must subclass
  this object before web.RequestHandler.
  """
  # TODO(spencer): remove this once we're using tornado 3.0 and
  #   the AsyncHTTPSTestCase.
  _HTTP_TEST_CASE = False

  def get_login_url(self):
    """For admin pages, we require a a login url which prompts for
    username, password and OTP entry. Specify this in application
    setting 'admin_login_url' to point at OTPEntryHandler instance.
    """
    self.require_setting('admin_login_url', '@handler.authenticated')
    return self.application.settings['admin_login_url']

  def get_current_user(self):
    """Looks for and parses the admin_otp cookie. If present, it
    should contain a json list of auth user and expiration time. The
    expiration time is verified; if not expired, the user is
    returned. Otherwise, returns None.
    """
    admin_cookie = self.get_secure_cookie(COOKIE_NAME)
    try:
      if admin_cookie:
        try:
          (user, expires) = json.loads(admin_cookie)
        except ValueError:
          # Old cookie format; delete it.
          self.clear_cookie(COOKIE_NAME)
          return None
        if expires > time.time():
          self._auth_user = user
          return self._auth_user
    except Exception:
      logging.exception('cannot authenticate admin access')
    return None

  def prepare(self):
    """Enforces 'https' and handles logout argument.

    Also sets self._loader to the template loader initialized in
    application setup.
    """
    web.RequestHandler.prepare(self)
    if not self.request.protocol == 'https' and \
          BasicAuthHandler._HTTP_TEST_CASE == False:
      logging.error('access to basic auth only available via https; '
                    'specify --xheaders=False if this server is not in production')
      self.send_error(403)
      return
    if self.get_argument('logout', False):
      self.clear_cookie(COOKIE_NAME, path='/admin')
      self.redirect('/admin/otp')
      return

  def set_secure_cookie(self, *args, **kwargs):
    """Override base set_secure_cookie to default secure and httponly to true.

    "secure" means HTTPS-only; "httponly" means the cookie is not accessible
    to javascript.
    """
    # TODO(spencer): remove this once we're using tornado 3.0 and
    #   the AsyncHTTPSTestCase.
    if not BasicAuthHandler._HTTP_TEST_CASE:
      kwargs.setdefault("secure", True)
    kwargs.setdefault("httponly", True)
    super(BasicAuthHandler, self).set_secure_cookie(*args, **kwargs)
