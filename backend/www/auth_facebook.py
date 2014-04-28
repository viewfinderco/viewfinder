# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Authentication and authorization for Facebook.

The flow via the web application is:
  - /register/facebook: redirects to facebook server, which in turn redirect to:
  - /register/facebook?code=<code>: sends facebook a request for an access token.
  - send a request to facebook for /me?access_token=<>.

The flow via the mobile app is:
  - /register/facebook?access_token=<access_token>: send request to facebook for
  /me?access_token=<>.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import httplib

from tornado import auth, gen, httpclient, web
from viewfinder.backend.base import handler
from viewfinder.backend.www import json_schema
from viewfinder.backend.www.auth import AuthHandler


class AuthFacebookHandler(AuthHandler, auth.FacebookGraphMixin):
  """Authenticates the caller as a Facebook user using Facebook's OAuth system."""
  @handler.asynchronous(datastore=True)
  @gen.engine
  def get(self, action):
    """GET is used when authenticating via the web application."""
    self._StartInteractiveRequest(action)
    if self.get_argument('code', False):
      user_dict = yield gen.Task(self.get_authenticated_user,
                                 redirect_uri='https://%s/%s/facebook' % (self.request.host, action),
                                 client_id=self.settings['facebook_api_key'],
                                 client_secret=self.settings['facebook_secret'],
                                 extra_fields=['email', 'timezone', 'verified'],
                                 code=self.get_argument('code'))
      self._PrepareUserInfo(None, user_dict)
    else:
      self.authorize_redirect(
        redirect_uri='https://%s/%s/facebook' % (self.request.host, action),
        extra_params={'scope': 'offline_access,user_photos,friends_photos'},
        client_id=self.settings['facebook_api_key'])

  @handler.asynchronous(datastore=True)
  @gen.engine
  def post(self, action):
    """POST is used when authenticating via the mobile application. The device info is in the
    JSON-encoded request body. A device id will be allocated and returned with the response.
    """
    yield gen.Task(self._StartJSONRequest, action, self.request, json_schema.AUTH_FB_GOOGLE_REQUEST)

    device_dict = self._request_message.dict.get('device', None)
    access_token = self.get_argument('access_token')

    user_dict = yield gen.Task(self.facebook_request,
                               path='/me',
                               access_token=access_token,
                               fields='id,name,first_name,last_name,locale,picture,link,email,timezone,verified')

    # Combines the access token with the user dictionary and invokes _OnAuthenticate to
    # register the user as a viewfinder account. If user_dict is None, then facebook
    # authentication failed, so return 401. 
    if user_dict is None:
      raise web.HTTPError(httplib.UNAUTHORIZED, 'Facebook authentication failed')

    user_dict['access_token'] = access_token

    self._PrepareUserInfo(device_dict, user_dict)

  def _PrepareUserInfo(self, device_dict, user_dict):
    """Converts user_dict returned by Facebook to Viewfinder format and forwards to base class
    _OnAuthenticate.
    """
    # Remove fields with null values.
    for key, value in user_dict.items():
      if value is None:
        del user_dict[key]

    # 10/3/2012: Facebook now returns picture as a dictionary, so drill down to get picture URL.
    if 'picture' in user_dict:
      user_dict['picture'] = user_dict['picture']['data']['url']

    # Create identity dict from Facebook's id field.
    ident_dict = {'key': 'FacebookGraph:%s' % user_dict['id'],
                  'authority': 'Facebook',
                  'access_token': user_dict.pop('access_token')}
    if 'expires' in user_dict:
      ident_dict['expires'] = user_dict.pop('expires')

    self._AuthUser(user_dict, ident_dict, device_dict)

  def get_http_client(self):
    """Overrides the get_http_client() method use in the facebook Auth mixin."""
    return httpclient.AsyncHTTPClient()
