#!/bin/env python
#
# Copyright 2012 bit.ly
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
"""
Created by Dan Frank on 2012-01-25.
Copyright (c) 2012 bit.ly. All rights reserved.
"""

import functools
from tornado.httpclient import HTTPRequest
from tornado.httpclient import AsyncHTTPClient
import xml.sax

import boto
from boto.sts.connection import STSConnection
from boto.sts.credentials import Credentials
from boto.exception import BotoServerError

class InvalidClientTokenIdError(BotoServerError):
  """Error subclass to indicate that the client's token(s) is/are invalid.
  """
  pass

class AsyncAwsSts(STSConnection):
  """Class that manages session tokens. Users of AsyncDynamoDB should not
  need to worry about what goes on here.

  Usage: Keep an instance of this class (though it should be cheap to
  re instantiate) and periodically call get_session_token to get a new
  Credentials object when, say, your session token expires.
  """
  def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
               is_secure=True, port=None, proxy=None, proxy_port=None,
               proxy_user=None, proxy_pass=None, debug=0,
               https_connection_factory=None, region=None, path='/',
               converter=None):
    STSConnection.__init__(self, aws_access_key_id,
                           aws_secret_access_key,
                           is_secure, port, proxy, proxy_port,
                           proxy_user, proxy_pass, debug,
                           https_connection_factory, region, path, converter)

  def get_session_token(self, callback):
    """Gets a new Credentials object with a session token, using this
    instance's aws keys. Callback should operate on the new Credentials obj,
    or else a boto.exception.BotoServerError.
    """
    return self.get_object('GetSessionToken', {}, Credentials, verb='POST', callback=callback)

  def get_object(self, action, params, cls, path="/", parent=None, verb="GET", callback=None):
    """Get an instance of `cls` using `action`."""
    if not parent:
      parent = self
    self.make_request(action, params, path, verb,
                      functools.partial(self._finish_get_object, callback=callback, parent=parent, cls=cls))

  def _finish_get_object(self, response_body, callback, cls=None, parent=None, error=None):
    """Process the body returned by STS. If an error is present,
    convert from a tornado error to a boto error.
    """
    if error:
      if error.code == 403:
        error_class = InvalidClientTokenIdError
      else:
        error_class = BotoServerError
      return callback(None, error=error_class(error.code, error.message, response_body))
    obj = cls(parent)
    h = boto.handler.XmlHandler(obj, parent)
    xml.sax.parseString(response_body, h)
    return callback(obj)

  def make_request(self, action, params={}, path='/', verb='GET', callback=None):
    """Make an async request. This handles the logic of translating
    from boto params to a tornado request obj, issuing the request,
    and passing back the body.

    The callback should operate on the body of the response, and take
    an optional error argument that will be a tornado error.
    """
    request = HTTPRequest('https://%s' % self.host, method=verb)
    request.params = params
    request.auth_path = '/' # need this for auth
    request.host = self.host # need this for auth
    if action:
      request.params['Action'] = action
    if self.APIVersion:
      request.params['Version'] = self.APIVersion
    self._auth_handler.add_auth(request) # add signature
    http_client = AsyncHTTPClient()
    http_client.fetch(request, functools.partial(self._finish_make_request, callback=callback))

  def _finish_make_request(self, response, callback):
    if response.error:
      return callback(response.body, error=response.error)
    return callback(response.body)
