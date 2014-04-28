#!/usr/bin/env python
#
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Creates and verifies one time passwords (OTPs).

OTPs are implemented as an SHA1 digest of:
  - user secret
  - GMT (UTC) time rounded to nearest 30s increment

This module tracks the number of OTP attempts and the specific codes
encountered so it can warn of brute-force or MITM attacks.

The OTP tokens generated are compatible with Google Authenticator,
and the mobile devices it supports.

Example Usage:

For a new administrator, run the following to create a secret for the
admin and get a verification code and QRcode URL for initializing
Google Authenticator:

% python -m viewfinder.backend.base.otp --otp_mode=new_secret --domain=viewfinder.co --user=<user>

To set a password for the admin:

% python -m viewfinder.backend.base.otp --otp_mode=set_pwd --user=<user>

To display an existing secret, as well as the verification code and
QRcode URL:

% python -m viewfinder.backend.base.otp --otp_mode=display_secret --user=<user>


To get an OTP value for a user:

% python -m viewfinder.backend.base.otp --otp_mode=get --user=<user>

To verify an OTP:

% python -m viewfinder.backend.base.otp --otp_mode=verify --user=<user> --otp=<otp>

To generate random bytes:

% python -m viewfinder.backend.base.otp --otp_mode=(random,randomb64) --bytes=<bytes>


  OTPException: exception for otp verification errors.

  GetOTP(): returns the otp for the requesting user at current time.
  VerifyOTP(): verifies an OTP for requesting user.
  CreateUserSecret(): creates and persists a user's secret.
  CreateRandomBytes(): creates random bytes.
  GetPassword(): returns the encrypted user password.
  SetPassword(): sets a user password from stdin.
  VerifyPassword(): verifies a user password.

  GetAdminOpener(): returns an OpenerDirector for retrieving administrative URLs.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'


import base64
import bisect
import cookielib
import getpass
import hashlib
import hmac
import json
import logging
import os
import re
import struct
import sys
import time
import urllib2

from Crypto.Protocol.KDF import PBKDF2
from os.path import expanduser
from tornado import ioloop, options
from viewfinder.backend.base import base_options

import secrets, util


options.define("otp_mode", "get",
               help="one of { get, verify, new_secret, set_pwd }")
options.define("otp", None, help="the otp if otp_mode=verify was set")
options.define("user", "", help="username")
options.define("bytes", 128, help="number of bytes to generate")

_SECRET_BYTES = 10
_GRANULARITY = 30
_TIMEOUT = 180
_VERIFY_MODULUS = 1000 * 1000
_ATTEMPTS_PER_MIN = 3

_PASSWORD_VERSION_MD5 = 0  # md5 with a global "salt"
_PASSWORD_VERSION_PBKDF2 = 1  # pbkdf2 with 10k iterations of sha1

_CURRENT_PASSWORD_VERSION = _PASSWORD_VERSION_PBKDF2


# History keeps track of the timestamps of recent login attempts,
# as well as all provided OTP codes.
_history = {}


class OTPException(Exception):
  """Subclass of exception to communicate error conditions upon
  attempted verification of OTP. In particular, too many unsuccesful
  OTP entry attempts or repeated tokens.
  """
  pass


def _ComputeOTP(secret, t):
  """Computes the HMAC hash of the user secret, and time (in 30s of
  seconds from the epoch). SHA1 is used as the internal digest and
  time is packed in big-endian order into an 8 byte string. Four
  bytes are extracted from the resulting digest (20 bytes in length
  for SHA1) based on an offset computed from the last byte of the
  digest % 0xF (e.g. from 0 to 14). The result is adjusted for
  negative values and taken modulo _VERIFY_MODULUS to yield a
  positive, N-digit OTP, where N = log10(_VERIFY_MODULUS).
  """
  h = hmac.new(base64.b32decode(secret), struct.pack('>Q', t), hashlib.sha1)
  hash = h.digest()
  offset = struct.unpack('B', hash[-1])[0] & 0xF
  truncated_hash = struct.unpack('>I', hash[offset:offset + 4])[0]
  truncated_hash &= 0x7FFFFFFF
  truncated_hash %= _VERIFY_MODULUS
  return truncated_hash


def _SecretName(user):
  """Returns the name of the secret file for the specified user.
  """
  return "{0}_otp".format(user)


def _PasswordName(user):
  """Returns the name of the password file for the specified user.
  """
  return "{0}_pwd".format(user)


def _GenerateSalt(version):
  if version == _PASSWORD_VERSION_MD5:
    return ""
  elif version == _PASSWORD_VERSION_PBKDF2:
    return base64.b64encode(os.urandom(8))
  raise ValueError("unsupported password version")


def _HashPassword(password, version, salt):
  """Hashes the provided password according to the specified version's policy.

  The result is base32 encoded.
  """
  if version == _PASSWORD_VERSION_MD5:
    m = hashlib.md5()
    m.update(password)
    m.update(secrets.GetSecret("cookie_secret"))
    hashed = m.digest()
  elif version == _PASSWORD_VERSION_PBKDF2:
    hashed = PBKDF2(password, base64.b64decode(salt), count=10000)
  return base64.b32encode(hashed)


def _GetUserSecret(user):
  """Returns the user secret by consulting the secrets database."""
  secret = secrets.GetSecret(_SecretName(user))
  if not secret:
    raise LookupError("no secret has been created for {0}".
              format(user))
  return secret


def _UpdateUserHistory(user, t, auth):
  """Updates the user history with the specified timestamp and auth
  code. Truncates arrays to maximum 30 entries each. Returns a list
  of (timestamp, otp) tuples for this user's past accesses.
  """
  ts = _history.get(user, [])[-30:]
  ts.append((t, auth))
  _history[user] = ts
  return ts


def _ClearUserHistory():
  """Clears the user history (for testing)."""
  _history.clear()


def _GetActivationURL(user, secret):
  """Generates a URL that displays a QR code on the browser for activating
  mobile devices with user secret.
  """
  return "https://www.google.com/chart?chs=200x200&chld=M|0&cht=qr&chl=" \
    "otpauth://totp/{0}@www.{1}%3Fsecret%3D{2}".format(user, options.options.domain, secret)


def GetOTP(user):
  """Gets a new OTP for the specified user by looking up the
  user's secret in the secrets database and using it to salt an
  MD5 hash of time and username.
  """
  return _ComputeOTP(_GetUserSecret(user),
                     long(time.time() / _GRANULARITY))


def VerifyOTP(user, otp):
  """Verifies the provided OTP for the user by comparing it to one
  generated right now, with successive checks both going forward and
  backwards in time to cover timeout range. This accounts for clock
  skew or delay in entering the OTP after fetching it.
  """
  timestamp = long(time.time())
  challenge = timestamp / _GRANULARITY
  units = _TIMEOUT / _GRANULARITY

  secret = _GetUserSecret(user)
  ts = _UpdateUserHistory(user, timestamp, otp)
  if len(ts) - bisect.bisect_left(ts, (timestamp - 60,)) > _ATTEMPTS_PER_MIN:
    raise OTPException("Too many OTP login attempts for {0} "
                       "in past minute".format(user))
  if  [True for x in ts[:-1] if x[1] == otp]:
    raise OTPException("Have already seen OTP {0} for "
                       "{1}".format(otp, user))

  for offset in range(-(units - 1) / 2, units / 2 + 1):
    if int(otp) == _ComputeOTP(secret, challenge + offset):
      return
  raise OTPException("Entered OTP invalid")


def CreateUserSecret(user):
  """Generates a random user secret and stores it to the secrets
  database.
  """
  secret = base64.b32encode(os.urandom(_SECRET_BYTES))
  secrets.PutSecret(_SecretName(user), secret)
  DisplayUserSecret(user)


def DisplayUserSecret(user):
  """Gets the user secret from the secrets database and displays
  it, along with the activation URL and verification code.
  """
  secret = _GetUserSecret(user)
  print "user secret={0}".format(secret)
  print "verification code={0}".format(_ComputeOTP(secret, 0))
  print "activation URL:", _GetActivationURL(user, secret)


def CreateRandomBytes(bytes, b64encode=False):
  """Generates a string of random bytes."""
  if b64encode:
    sys.stdout.write(base64.b64encode(os.urandom(bytes)))
  else:
    sys.stdout.write(os.urandom(bytes))


def GetPassword(user):
  """Returns the encrypted user password from the secrets database."""
  s = secrets.GetSecret(_PasswordName(user))
  try:
    return json.loads(s)
  except ValueError:
    # Pre-json format.
    return dict(version=_PASSWORD_VERSION_MD5, hashed=s)


def SetPassword(user):
  """Accepts a user password as input from stdin and stores it to
  the secrets database. The user password is stored as <user>_pwd
  and is encrypted using the cookie_secret, defined for the
  application to secure cookies.
  """
  print "Please enter your password twice to reset:"
  pwd = getpass.getpass()
  pwd2 = getpass.getpass()
  assert pwd == pwd2, 'passwords don\'t match'
  version = _CURRENT_PASSWORD_VERSION
  salt = _GenerateSalt(version)
  hashed = _HashPassword(pwd, version, salt)
  data = dict(salt=salt, hashed=hashed, version=version)
  secrets.PutSecret(_PasswordName(user), json.dumps(data))


def VerifyPassword(user, cleartext_pwd):
  """Encrypts the provided `cleartext_pwd` and compares it to the
  encrypted password stored for the user in the secrets DB.
  """
  expected = GetPassword(user)
  hashed = _HashPassword(cleartext_pwd, expected['version'],
                         expected.get('salt'))
  if hashed != expected['hashed']:
    raise OTPException("Entered username/password invalid")


def VerifyPasswordCLI(user):
  """Command-line interface to VerifyPassword, for testing purposes."""
  print "Please enter your password:"
  pwd = getpass.getpass()
  result = VerifyPassword(user, pwd)
  print "Passwords match" if result else "No match"


def _PromptForAdminCookie(user, pwd, otp_entry):
  """Prompts the user to enter admin username / password and OTP code.
  Synchronously authenticates the user/pwd/otp combination with the
  server at www.domain and stores resulting auth cookie(s).

  Returns the new admin cookiejar.
  """
  if user is None:
    user = raw_input('Please enter admin username: ')
  else:
    print 'Username: %s' % user
  if pwd is None:
    pwd = getpass.getpass('Please enter admin password: ')
  if otp_entry is None:
    otp_entry = int(getpass.getpass('Please enter OTP code: '))
  return user, pwd, otp_entry


def GetAdminOpener(host, user=None, pwd=None, otp_entry=None,
                   cookiejar_path=None):
  """Returns an OpenerDirector for retrieving administrative URLs.
  Uses stored admin cookies if available, or prompts for authentication
  credentials and authenticates with server otherwise.

  Based on reitveld codereview script.
  """
  opener = urllib2.OpenerDirector()
  opener.add_handler(urllib2.HTTPDefaultErrorHandler())
  opener.add_handler(urllib2.HTTPSHandler())
  opener.add_handler(urllib2.HTTPErrorProcessor())
  # TODO(spencer): remove the HTTP handler when we move to AsyncHTTPSTestCase.
  # This is only for testing currently.
  opener.add_handler(urllib2.HTTPHandler())

  if cookiejar_path is None:
    cookiejar_path = expanduser('~/.viewfinder_admin_cookie')
  cookie_jar = cookielib.MozillaCookieJar(cookiejar_path)
  if os.path.exists(cookiejar_path):
    try:
      cookie_jar.load()
      logging.info('loaded admin authentication cookies from %s' %
                   cookiejar_path)
    except:
      # Otherwise, bad cookies; clear them.
      os.unlink(cookiejar_path)
  if not os.path.exists(cookiejar_path):
    # Create empty file with correct permissions.
    fd = os.open(cookiejar_path, os.O_CREAT, 0600)
    os.close(fd)
  # Always chmod to be sure.
  os.chmod(cookiejar_path, 0600)
  opener.add_handler(urllib2.HTTPCookieProcessor(cookie_jar))

  class TornadoXSRFProcessor(urllib2.BaseHandler):
    """Add tornado's xsrf headers to outgoing requests."""
    handler_order = urllib2.HTTPCookieProcessor.handler_order + 1
    def http_request(self, request):
      cookie_header = request.get_header('Cookie')
      if cookie_header is not None and '_xsrf=' in cookie_header:
        # We have an xsrf cookie in the cookie jar.  Copy it into the X-Xsrftoken header.
        request.add_unredirected_header('X-Xsrftoken', re.match('_xsrf=([^;]+)', cookie_header).group(1))
      else:
        # No xsrf cookie, so just make one up.  (this is currently the expected case because cookielib
        # considers our xsrf cookie to be a "session" cookie and doesn't save it)
        request.add_unredirected_header('X-Xsrftoken', 'fake_xsrf')
        if cookie_header:
          request.add_unredirected_header('Cookie', '_xsrf="fake_xsrf"; ' + cookie_header)
        else:
          request.add_unredirected_header('Cookie', '_xsrf="fake_xsrf"')
      return request
    https_request = http_request
  opener.add_handler(TornadoXSRFProcessor())

  # Look for admin cookie. If it doesn't exist (or is expired), prompt
  # and reauthenticate.
  if len(cookie_jar) == 0 or \
        any([c.is_expired() for c in cookie_jar if c.domain == host]):
    if user is None or pwd is None or otp_entry is None:
      user, pwd, otp_entry = _PromptForAdminCookie(user, pwd, otp_entry)

    from viewfinder.backend.www.admin import admin_api
    admin_api.Authenticate(opener, host, user, pwd, otp_entry)
    cookie_jar.save()
    logging.info('saved admin authentication cookies to %s' % cookiejar_path)

  return opener


def main():
  io_loop = ioloop.IOLoop.current()
  options.parse_command_line()

  def _OnException(type, value, traceback):
    logging.error('failed %s' % options.options.otp_mode, exc_info=(type, value, traceback))
    io_loop.stop()
    sys.exit(1)

  def _RunOTPCommand():
    with util.ExceptionBarrier(_OnException):
      if options.options.otp_mode == "get":
        print GetOTP(options.options.user)
      elif options.options.otp_mode == "verify":
        print VerifyOTP(options.options.user, options.options.otp)
      elif options.options.otp_mode == "new_secret":
        CreateUserSecret(options.options.user)
      elif options.options.otp_mode == "display_secret":
        DisplayUserSecret(options.options.user)
      elif options.options.otp_mode == "set_pwd":
        SetPassword(options.options.user)
      elif options.options.otp_mode == "verify_pwd":
        VerifyPasswordCLI(options.options.user)
      elif options.options.otp_mode == "random":
        CreateRandomBytes(options.options.bytes)
      elif options.options.otp_mode == "randomb64":
        CreateRandomBytes(options.options.bytes, True)
      else:
        logging.error("unrecognized mode {0}", options.options.otp_mode)
        options.print_help()
      io_loop.stop()

  print options.options.domain

  secrets.InitSecrets(shared_only=True, callback=_RunOTPCommand)
  io_loop.start()

if __name__ == "__main__":
  main()
