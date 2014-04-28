#!/usr/bin/env python
#
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Provides OTP entry handler.

  OTPEntryHandler: handler for OTP entry; login_url for AdminServer.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'


import json
import logging
import sys
import time
import validictory

from tornado import httputil, template, web
from viewfinder.backend.base import otp, secrets
from viewfinder.backend.www import basic_auth, json_schema
from viewfinder.backend.www.admin import admin, admin_schema


class OTPEntryHandler(admin.AdminHandler):
  """Request handler for OTP entry. Displays an OTP entry form on
  GET, and accepts the OTP for verification on a call to POST. If
  verified, a secure 'admin_otp' cookie containing the expiration
  for the OTP validation is returned to the user and the request is
  redirected.
  """
  @classmethod
  def _CreateCookie(cls, user, timestamp):
    """Returns a json-encoded list of auth user and
    expiration time.
    """
    return json.dumps((user, long(timestamp) + basic_auth.COOKIE_EXPIRATION))

  @classmethod
  def _ValidateCredentials(cls, user, pwd, otp_entry):
    """Validates username / password in conjunction with
    OTP entry. Returns otp_admin cookie value on success.
    """
    otp.VerifyPassword(user, pwd)
    otp.VerifyOTP(user, otp_entry)
    return OTPEntryHandler._CreateCookie(user, time.time())

  # Do not require permissions on OTP.
  def get(self):
    """Writes the template for OTP entry form with this URI as
    the action.
    """
    self.render('otp.html',
        uri=self.request.uri, msg=self.get_argument('msg', ''),
        auth_credentials=self._auth_credentials)

  # Do not require permissions on OTP.
  def post(self):
    """Verifies the OTP parameter of the POST. On success, sends
    the user a secure expiration cookie and redirects to the
    original page. On failure, shows login again with error msg.
    """
    FORM_TYPE = 'application/x-www-form-urlencoded'
    JSON_TYPE = 'application/json'

    if self.request.headers['Content-Type'].startswith(FORM_TYPE):
      try:
        user = self.get_argument('username', '')
        pwd = self.get_argument('password', '')
        otp_entry = self.get_argument('otp', '')
        self.set_secure_cookie(basic_auth.COOKIE_NAME,
                               self._ValidateCredentials(user, pwd, otp_entry),
                               path='/admin', expires_days=1)
        logging.info('admin web authentication: %s' % user)
        self.redirect(self.get_argument('next', '/admin'))
      except Exception as ex_msg:
        logging.exception(ex_msg)
        self.render('otp.html',
                    uri=self.request.uri, msg=ex_msg, auth_credentials=self._auth_credentials)
    else:
      assert self.request.headers['Content-Type'].startswith(JSON_TYPE)
      try:
        # TODO(ben): refactor BaseHandler so we can use _LoadJSONRequest here.
        request_dict = json.loads(self.request.body)
        validictory.validate(request_dict, admin_schema.AUTHENTICATE_REQUEST)
        self.set_secure_cookie(basic_auth.COOKIE_NAME,
                               self._ValidateCredentials(request_dict['username'],
                                                         request_dict['password'],
                                                         str(request_dict['otp'])),
                               path='/admin', expires_days=1)
        response_dict = {}
        validictory.validate(response_dict, admin_schema.AUTHENTICATE_RESPONSE)
        self.set_status(200)
        self.write(response_dict)  # tornado automatically serializes json
        logging.info('admin RPC authentication: %s' % request_dict['username'])
        self.finish()
      except Exception as ex_msg:
        logging.exception(ex_msg)
        type, value, tb = sys.exc_info()
        error_dict = {'error': {'method': 'authenticate',
                                'message': '%s %s' % (type, value)}}
        validictory.validate(error_dict, json_schema.ERROR_RESPONSE)
        self.set_header('Content-Type', 'application/json; charset=UTF-8')
        self.write(error_dict)
        self.finish()
