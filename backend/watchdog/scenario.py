# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder watchdog scenario.
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import logging
import json
import os
import re
import time
import urllib

from viewfinder.backend.base import util, secrets
from viewfinder.backend.base.environ import ServerEnvironment
from viewfinder.backend.www import www_util
from tornado.ioloop import IOLoop
from tornado import httpclient, options, web

_GOOGLE_OAUTH2_DEVICECODE_URL = 'https://accounts.google.com/o/oauth2/device/code'
_GOOGLE_OAUTH2_TOKEN_URL = 'https://accounts.google.com/o/oauth2/token'
_GOOGLE_OAUTH2_SCOPES = 'https://www.googleapis.com/auth/userinfo.profile ' \
      'https://www.googleapis.com/auth/userinfo.email ' \
      'https://accounts.google.com/o/oauth2/auth'

options.define('watchdog_auth_dir', './local/watchdog', help='Storage location for watchdog authorization credentials.')
options.define('watchdog_auth_reset', False, help='If true, resets credentials for watchdog logins.')


class ScenarioLoginError(Exception):
  """Error occurred during the login process for a scenario client."""
  pass


class Scenario(object):
  """Class describes a scenario objects.  Scenarios are initialized with a handler function, a name and a description.
  The frequency parameter is the frequency in seconds to repeat this scenario.

  The handler method is invoked with a ScenarioDevice client, a logger and a barrier callback each time it is run.

  The handler can indicate its status by using the logger provided to it - a log message of level 'error' will result
  in an immediate alert being sent.  A series of too many errors will also result in an alert.  The handler is completed
  by calling the provided barrier callback.
  """
  _http_error_dict = {404: '404 File not found received the viewfinder service.',
                      500: '500 Internal server error from viewfinder service.',
                      599: '599 Timeout when attempting to reach the viewfinder service.'}

  def __init__(self, name, handler, frequency, description=None):
    self.name = name
    self.handler = handler
    self.description = description
    self.frequency = frequency
    self._timeout = None

  def StartLoop(self, device):
    """Start this scenario.  It will run at the configured frequency until StopLoop() is called."""
    logger = logging.LoggerAdapter(logging.getLogger(), {'scenario': self.name})

    def _OnComplete():
      self._timeout = IOLoop.current().add_timeout(time.time() + self.frequency, _RunIteration)

    def _OnException(typ, val, tb):
      if (typ, val, tb) != (None, None, None):
        if typ is web.HTTPError:
          message = self._http_error_dict.get(val.status_code,
                                              'HTTP status %d received from viewfinder: %s' %
                                              (val.status_code, val.log_message))
          logger.error(message)
        else:
          logger.error('Unknown exception in scenario %s', self.name, exc_info=(typ, val, tb))
      _OnComplete()

    def _RunIteration():
      with util.Barrier(_OnComplete, _OnException) as b:
        self.handler(device, logger, b.Callback())

    _RunIteration()

  def StopLoop(self):
    """Stop the loop if it is already running."""
    if self._timeout is not None:
      IOLoop.current().remove_timeout(self._timeout)


class ScenarioDevice(object):
  """Represents a single client."""
  def __init__(self, name):
    self.name = name
    self._svc_url = 'https://%s:%d/' % (ServerEnvironment.GetHost(), options.options.port)
    self._user_cookie = None
    if options.options.watchdog_auth_reset:
      self._ClearAuthentication()
    else:
      self._LoadAuthentication()

  def SendRequest(self, service_path, callback, method='POST', **kwargs):
    """Send an arbitrary service request to the viewfinder service from this client.
    The request is a json request consisting of any additional keyword arguments to
    SendRequest.
    """
    if self._user_cookie is None:
      raise ScenarioLoginError('Client %s can not be used until it is has a valid authorization cookie.'
                              % self.name)

    http_client = httpclient.AsyncHTTPClient()
    url = self._GetUrl(service_path)
    headers = {'Cookie': 'user=%s;_xsrf=watchdog' % (self._user_cookie),
               'X-Xsrftoken': 'watchdog'}
    if method == 'GET':
      if len(kwargs) > 0:
        url += '?' + urllib.urlencode(kwargs)
      http_client.fetch(url, method=method, callback=callback, validate_cert=False, headers=headers)
    elif method == 'POST':
      headers['Content-Type'] = 'application/json'
      request_body = json.dumps(kwargs)
      http_client.fetch(url, method=method, body=request_body, callback=callback, validate_cert=False,
                        headers=headers)
    else:
      raise ValueError('Invalid method %s: must be one of "GET" or "POST"' % method)

  def IsAuthenticated(self):
    """Return true if this device has a valid authentication cookie from the server."""
    return self._user_cookie is not None

  def GetUserCode(self, callback):
    """Retrieve a user code from google's device login API.  The given callback will
    be invoked with the user code and a URL where the user code can be used to
    authenticate a google account.
    """
    def _OnGetDeviceCode(response):
      response_dict = www_util.ParseJSONResponse(response)
      self._device_code = response_dict.get('device_code')
      callback(response_dict.get('user_code'), response_dict.get('verification_url'))

    # Get a device code from google's API
    request_args = {'client_id': secrets.GetSecret('google_client_mobile_id'),
                    'scope': _GOOGLE_OAUTH2_SCOPES}
    url = _GOOGLE_OAUTH2_DEVICECODE_URL
    http_client = httpclient.AsyncHTTPClient()
    http_client.fetch(url, method='POST',
                      body=urllib.urlencode(request_args), callback=_OnGetDeviceCode)

  def PollForAuthentication(self, callback):
    """Poll the google authorization service to find if the user code generated
    in a previous call to GetUserCode() has been used to authorize a google user account.
    If an account has been authorized, this method will use that authorization to log
    into the viewfinder service, thus retrieving the needed authentication cookie.

    The given callback will be invoked with a boolean parameter to indicate whether
    or not the authentication was successful.  If authentication was not successful, then
    this method can be polled again until it is successful.
    """
    if not hasattr(self, '_device_code'):
      raise ScenarioLoginError('Must call GetUserCode() on a device before using the '
                               'PollForAuthentication() method.')

    http_client = httpclient.AsyncHTTPClient()

    def _OnLogin(response):
      if not response.code in (200, 302):
        raise ScenarioLoginError('Error during login process:%s' % response.error)
      self._user_cookie = self._GetUserCookieFromResponse(response)
      self._SaveAuthentication()
      callback(True)

    def _OnPollTokenEndpoint(response):
      json_response = www_util.ParseJSONResponse(response)
      if 'error' in json_response:
        callback(False)
      else:
        refresh_token = json_response.get('refresh_token')
        url = 'https://%s:%d/auth/google?refresh_token=%s' % \
              (ServerEnvironment.GetHost(), options.options.port, refresh_token)
        http_client.fetch(url, method='POST',
                          callback=_OnLogin,
                          body=json.dumps({}),
                          validate_cert=False, follow_redirects=False,
                          headers={'Content-Type': 'application/json'})

    url = _GOOGLE_OAUTH2_TOKEN_URL
    request_args = {'client_id': secrets.GetSecret('google_client_mobile_id'),
                    'client_secret': secrets.GetSecret('google_client_mobile_secret'),
                    'code': self._device_code,
                    'grant_type': 'http://oauth.net/grant_type/device/1.0'}

    http_client.fetch(url, method='POST',
                      body=urllib.urlencode(request_args),
                      callback=_OnPollTokenEndpoint)

  def _GetUserCookieFromResponse(self, response):
    """Extracts the user cookie from an HTTP response and returns it if
    it exists, or returns None if not."""
    user_cookie_header = [h for h in response.headers.get_list('Set-Cookie') if h.startswith('user=')][-1]
    return re.match(r'user="?([^";]*)', user_cookie_header).group(1)

  def _LoadAuthentication(self):
    """Loads a previous authorization cookie for this client from file."""
    auth_file = self._AuthFilePath()
    if os.path.exists(auth_file):
      try:
        fh = open(auth_file, 'r')
        self._user_cookie = fh.read()
      except:
        logging.fatal('Exception loading authorization file %s', auth_file, exc_info=True)
        raise ScenarioLoginError('Error loading auth file for client %s.' % self.name)

  def _SaveAuthentication(self):
    """Save the authorization cookie to a local file."""
    auth_file = self._AuthFilePath()
    try:
      dir = os.path.dirname(auth_file)
      if not os.path.exists(dir):
        os.makedirs(dir)
      fh = open(auth_file, 'w')
      fh.write(self._user_cookie)
      fh.close()
    except:
      logging.fatal('Failed to save authorization file %s', auth_file, exc_info=True)
      raise ScenarioLoginError('Error saving auth file for client %s.' % self.name)

  def _ClearAuthentication(self):
    """Clears any existing authorization for this client."""
    auth_file = self._AuthFilePath()
    if os.path.exists(auth_file):
      try:
        os.remove(auth_file)
      except:
        logging.fatal('Could not clear authorization file %s', auth_file, exc_info=True)
        raise ScenarioLoginError('Error clearing auth file for client %s.' % self.name)

  def _AuthFilePath(self):
    return os.path.join(options.options.watchdog_auth_dir, self.name)

  def _GetUrl(self, path):
    return self._svc_url + path
