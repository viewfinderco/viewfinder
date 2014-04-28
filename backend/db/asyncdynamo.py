# Copyright 2012 bit.ly
# Copyright 2012 Viewfinder Inc. All Rights Reserved.
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
Created by Dan Frank on 2012-01-23.
Copyright (c) 2012 bit.ly. All rights reserved.
"""

import sys
assert sys.version_info >= (2, 7), "run this with python2.7"

import functools
import json
import logging
import time

from async_aws_sts import AsyncAwsSts, InvalidClientTokenIdError
from boto.auth import HmacAuthV3HTTPHandler
from boto.connection import AWSAuthConnection
from boto.exception import DynamoDBResponseError
from boto.provider import Provider
from collections import deque
from tornado import httpclient, ioloop
from tornado.httpclient import HTTPRequest
from viewfinder.backend.base.exceptions import DBProvisioningExceededError, DBLimitExceededError, DBConditionalCheckFailedError

PENDING_SESSION_TOKEN_UPDATE = "this is not your session token"


class AsyncDynamoDB(AWSAuthConnection):
  """The main class for asynchronous connections to DynamoDB.

  The user should maintain one instance of this class (though more
  than one is ok), parametrized with the user's access key and secret
  key. Make calls with make_request or the helper methods, and
  AsyncDynamoDB will maintain session tokens in the background.
  """

  DefaultHost = 'dynamodb.us-east-1.amazonaws.com'
  """The default DynamoDB API endpoint to connect to."""

  ServiceName = 'DynamoDB'
  """The name of the Service"""

  Version = '20111205'
  """DynamoDB API version."""

  ExpiredSessionError = 'ExpiredTokenException'
  """The error response returned when session token has expired"""

  UnrecognizedClientException = 'UnrecognizedClientException'
  """Another error response that is possible with a bad session token"""

  ProvisionedThroughputExceededException = 'ProvisionedThroughputExceededException'
  """Provisioned throughput for requests to table exceeded."""

  LimitExceededException = 'LimitExceededException'
  """Limit for subscriber requests exceeded."""

  ConditionalCheckFailedException = 'ConditionalCheckFailedException'

  def __init__(self, aws_access_key_id=None, aws_secret_access_key=None,
               is_secure=True, port=None, proxy=None, proxy_port=None,
               host=None, debug=0, session_token=None,
               authenticate_requests=True, validate_cert=True, max_sts_attempts=3):
    if not host:
      host = self.DefaultHost
    self.validate_cert = validate_cert
    self.authenticate_requests = authenticate_requests
    AWSAuthConnection.__init__(self, host,
                               aws_access_key_id,
                               aws_secret_access_key,
                               is_secure, port, proxy, proxy_port,
                               debug=debug, security_token=session_token)
    self.pending_requests = deque()
    self.sts = AsyncAwsSts(aws_access_key_id, aws_secret_access_key)
    assert (isinstance(max_sts_attempts, int) and max_sts_attempts >= 0)
    self.max_sts_attempts = max_sts_attempts

  def _init_session_token_cb(self, error=None):
    if error:
      logging.warn("Unable to get session token: %s" % error)

  def _required_auth_capability(self):
    return ['hmac-v3-http']

  def _update_session_token(self, callback, attempts=0, bypass_lock=False):
    """Begins the logic to get a new session token. Performs checks to
    ensure that only one request goes out at a time and that backoff
    is respected, so it can be called repeatedly with no ill
    effects. Set bypass_lock to True to override this behavior.
    """
    if self.provider.security_token == PENDING_SESSION_TOKEN_UPDATE and not bypass_lock:
      return
    self.provider.security_token = PENDING_SESSION_TOKEN_UPDATE # invalidate the current security token
    return self.sts.get_session_token(
      functools.partial(self._update_session_token_cb, callback=callback, attempts=attempts))

  def _update_session_token_cb(self, creds, provider='aws', callback=None, error=None, attempts=0):
    """Callback to use with `async_aws_sts`. The 'provider' arg is a
    bit misleading, it is a relic from boto and should probably be
    left to its default. This will take the new Credentials obj from
    `async_aws_sts.get_session_token()` and use it to update
    self.provider, and then will clear the deque of pending requests.

    A callback is optional. If provided, it must be callable without
    any arguments.
    """
    def raise_error():
      # get out of locked state
      self.provider.security_token = None
      if callable(callback):
        return callback(error=error)
      else:
        logging.error(error)
        raise error
    if error:
      if isinstance(error, InvalidClientTokenIdError):
        # no need to retry if error is due to bad tokens
        raise_error()
      else:
        if attempts > self.max_sts_attempts:
          raise_error()
        else:
          seconds_to_wait = (0.1 * (2 ** attempts))
          logging.warning("Got error[ %s ] getting session token, retrying in %.02f seconds" % (error, seconds_to_wait))
          ioloop.IOLoop.current().add_timeout(time.time() + seconds_to_wait,
            functools.partial(self._update_session_token, attempts=attempts + 1, callback=callback, bypass_lock=True))
          return
    else:
      self.provider = Provider(provider,
                               creds.access_key,
                               creds.secret_key,
                               creds.session_token)
      # force the correct auth, with the new provider
      self._auth_handler = HmacAuthV3HTTPHandler(self.host, None, self.provider)
      while self.pending_requests:
        request = self.pending_requests.pop()
        request()
      if callable(callback):
        return callback()

  def make_request(self, action, body='', callback=None, object_hook=None):
    """Make an asynchronous HTTP request to DynamoDB. Callback should
    operate on the decoded json response (with object hook applied, of
    course). It should also accept an error argument, which will be a
    boto.exception.DynamoDBResponseError.

    If there is not a valid session token, this method will ensure
    that a new one is fetched and cache the request when it is
    retrieved.
    """
    this_request = functools.partial(self.make_request, action=action,
                                     body=body, callback=callback, object_hook=object_hook)
    if self.authenticate_requests and self.provider.security_token in [None, PENDING_SESSION_TOKEN_UPDATE]:
      # we will not be able to complete this request because we do not have a valid session token.
      # queue it and try to get a new one. _update_session_token will ensure that only one request
      # for a session token goes out at a time
      self.pending_requests.appendleft(this_request)
      def cb_for_update(error=None):
        # create a callback to handle errors getting session token
        # callback here is assumed to take a json response, and an instance of DynamoDBResponseError
        if error:
          raise DynamoDBResponseError(error.status, error.reason, body={'message': error.body})
        else:
          return
      self._update_session_token(cb_for_update)
      return
    headers = {'X-Amz-Target' : '%s_%s.%s' % (self.ServiceName, self.Version, action),
               'Content-Type' : 'application/x-amz-json-1.0',
               'Content-Length' : str(len(body))}
    request = HTTPRequest('https://%s' % self.host,
                          method='POST',
                          headers=headers,
                          body=body,
                          validate_cert=self.validate_cert)
    request.path = '/' # Important! set the path variable for signing by boto. '/' is the path for all dynamodb requests
    if self.authenticate_requests:
      self._auth_handler.add_auth(request) # add signature to headers of the request

    http_client = httpclient.AsyncHTTPClient()
    http_client.fetch(request, functools.partial(
      self._finish_make_request, callback=callback, orig_request=this_request,
      token_used=self.provider.security_token, object_hook=object_hook))

  def _finish_make_request(self, response, callback, orig_request, token_used, object_hook=None):
    """Check for errors and decode the json response (in the tornado
    response body), then pass on to orig callback.  This method also
    contains some of the logic to handle reacquiring session tokens.
    """
    if not response.body:
      assert response.error, 'How can there be no response body and no error? Response: %s' % response
      raise DynamoDBResponseError(response.error.code, response.error.message, None)

    json_response = json.loads(response.body, object_hook=object_hook)
    if response.error:
      aws_error_type = None
      try:
        # The error code should be in the __type field of the json response, and should be a string
        # in the form 'namespace.version#errorcode'.  If the field doesn't exist or is in some other form,
        # just treat this as an unknown error type.
        aws_error_type = json_response.get('__type').split('#')[1]
      except:
        aws_error_type = None

      if aws_error_type == self.ExpiredSessionError or aws_error_type == self.UnrecognizedClientException:
        if self.provider.security_token == token_used:
          # The token that we used has expired, wipe it out.
          self.provider.security_token = None

        # make_request will handle logic to get a new token if needed, and queue until it is fetched
        return orig_request()

      if aws_error_type == AsyncDynamoDB.ProvisionedThroughputExceededException:
        raise DBProvisioningExceededError(json_response['message'])

      if aws_error_type == AsyncDynamoDB.LimitExceededException:
        raise DBLimitExceededError(json_response['message'])

      if aws_error_type == AsyncDynamoDB.ConditionalCheckFailedException:
        raise DBConditionalCheckFailedError(json_response['message'])

      raise DynamoDBResponseError(response.error.code, response.error.message, json_response)

    return callback(json_response)
