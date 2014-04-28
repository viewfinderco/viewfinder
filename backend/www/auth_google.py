# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Authentication and authorization for Google.

The flow via the web application is:
    - /register/google: redirects to _OAUTH2_AUTH_URL, asking permission for contacts list,
      which in turn redirects to:
    - /register/google?code=<auth_code>: sends a request to _OAUTH2_ACCESS_TOKEN_URL for
      access token.

  The flow via the mobile app is:
    - /register/google?refresh_token=<>: sends a request to _OAUTH2_ACCESS_TOKEN_URL for
      access token.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import urllib

from tornado import auth, gen, httpclient, web
from viewfinder.backend.base import handler, util
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.www.auth import AuthHandler
from viewfinder.backend.www import json_schema, www_util


_CANNOT_USE_UNVERIFIED_EMAIL = 'Viewfinder cannot use your "%s" email. It has not been verified by Google.'


class AuthGoogleHandler(AuthHandler, auth.OAuth2Mixin):
  """Authenticates the caller as a Google user using Google's OAuth system."""
  _OAUTH2_AUTH_URL = 'https://accounts.google.com/o/oauth2/auth'
  _OAUTH2_ACCESS_TOKEN_URL = 'https://accounts.google.com/o/oauth2/token'
  _OAUTH2_USERINFO_URL = 'https://www.googleapis.com/oauth2/v1/userinfo'
  _OAUTH2_SCOPE = 'https://www.googleapis.com/auth/userinfo.profile ' \
      'https://www.googleapis.com/auth/userinfo.email ' \
      'https://www.google.com/m8/feeds/contacts'

  @handler.asynchronous(datastore=True)
  @gen.engine
  def get(self, action):
    """GET is used when authenticating via the web application. If code isn't supplied in URL
    params, redirects to Google with a request for authentication. Google redirects to this
    URL again on successful authentication with a code which is then used to authorize user
    information and contacts.
    """
    self._StartInteractiveRequest(action)
    if not self.get_argument('code', False):
      url = AuthGoogleHandler._OAUTH2_AUTH_URL
      args = {'client_id': self.settings['google_client_id'],
              'redirect_uri': 'https://%s/%s/google' % (self.request.host, action),
              'response_type': 'code',
              'access_type': 'offline',
              'approval_prompt': 'force',
              'scope': AuthGoogleHandler._OAUTH2_SCOPE}
      self.redirect(url + '?' + urllib.urlencode(args))
    else:
      url = AuthGoogleHandler._OAUTH2_ACCESS_TOKEN_URL
      args = {'client_id': self.settings['google_client_id'],
              'client_secret': self.settings['google_client_secret'],
              'redirect_uri': 'https://%s/%s/google' % (self.request.host, action),
              'code': self.get_argument('code'),
              'grant_type': 'authorization_code'}
      http_client = httpclient.AsyncHTTPClient()
      response = yield gen.Task(http_client.fetch, url, method='POST', body=urllib.urlencode(args))
      self._GetUserInfo(None, None, response)

  @handler.asynchronous(datastore=True)
  @gen.engine
  def post(self, action):
    """POST is used when authenticating via the mobile application. The device info is in the
    JSON-encoded request body. A device id will be allocated and returned with the response.
    """
    yield gen.Task(self._StartJSONRequest, action, self.request, json_schema.AUTH_FB_GOOGLE_REQUEST)

    device_dict = self._request_message.dict.get('device', None)

    if self.get_argument('refresh_token', False):
      refresh_token = self.get_argument('refresh_token')
      url = AuthGoogleHandler._OAUTH2_ACCESS_TOKEN_URL
      args = {'client_id': self.settings['google_client_mobile_id'],
              'client_secret': self.settings['google_client_mobile_secret'],
              'refresh_token': refresh_token,
              'grant_type': 'refresh_token'}
      http_client = httpclient.AsyncHTTPClient()
      response = yield gen.Task(http_client.fetch, url, method='POST', body=urllib.urlencode(args))
      self._GetUserInfo(device_dict, refresh_token, response)
    else:
      raise web.HTTPError(400, 'refresh_token was not provided')

  @gen.engine
  def _GetUserInfo(self, device_dict, refresh_token, response):
    """Parses the google access token from the JSON response body. Gets user data via OAUTH2
    with access token.
    """
    tokens = www_util.ParseJSONResponse(response)
    assert tokens, 'unable to fetch access token'
    access_token = tokens['access_token']
    expires = tokens['expires_in']
    if tokens.has_key('refresh_token') and not refresh_token:
      refresh_token = tokens['refresh_token']

    # Using the access token that was previously retrieved, request information about the
    # user that is logging in.
    assert access_token, 'no access token was provided'
    url = AuthGoogleHandler._OAUTH2_USERINFO_URL + '?' + urllib.urlencode({'access_token': access_token})
    http_client = httpclient.AsyncHTTPClient()
    response = yield gen.Task(http_client.fetch, url)

    # Parse the user information from the JSON response body and invoke _OnAuthenticate to
    # register the user as a viewfinder account. Create user dict from Google's JSON response.
    user_dict = www_util.ParseJSONResponse(response)
    assert user_dict, 'unable to fetch user data'
    assert 'phone' not in user_dict, user_dict
    assert 'email' in user_dict, user_dict
    user_dict['email'] = Identity.CanonicalizeEmail(user_dict['email'])

    # Ensure that user email is verified, else we can't trust that the user really owns it.
    if not user_dict.get('verified_email', False):
      raise web.HTTPError(403, _CANNOT_USE_UNVERIFIED_EMAIL % user_dict['email'])

    # Create identity dict from Google's email field.
    ident_dict = {'key': 'Email:%s' % user_dict['email'],
                  'authority': 'Google',
                  'refresh_token': refresh_token,
                  'access_token': access_token,
                  'expires': util.GetCurrentTimestamp() + expires}

    self._AuthUser(user_dict, ident_dict, device_dict)
