# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Async version of Amazon S3 access library.

The "boto" open source library supports synchronous operations against
S3, but does not have asynchronous support. In a high-scale server
environment, this is a real problem, because it is not permissible to
block threads waiting on network I/O. This module layers support for non-
blocking async operations over the boto library. It re-uses boto
functionality whenever possible.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import logging
import socket
import urllib
from tornado.httpclient import AsyncHTTPClient, HTTPRequest, HTTPError
from boto.connection import AWSAuthConnection
from boto.s3.connection import SubdomainCallingFormat
from viewfinder.backend.base.retry import RetryPolicy, CallWithRetryAsync

class S3RetryPolicy(RetryPolicy):
  """Define a retry policy that is adapted to the Amazon S3 service.
  Retries will only be attempted for HTTP 500-level errors, or if there
  was a basic network failure of some kind. By default, a request
  against S3 will be retried three times, with retries starting after
  at least 1/2 second, and exponentially backing off from there to a
  maximum of 10 seconds.
  """
  def __init__(self, max_tries=3, timeout=30, min_delay=.5, max_delay=10):
    RetryPolicy.__init__(self, max_tries=max_tries, timeout=timeout, min_delay=min_delay, max_delay=max_delay,
                         check_result=self._ShouldRetry)

  def _ShouldRetry(self, response):
    """Retry on:
      1. HTTP error codes 500 (Internal Server Error) and 503 (Service
         Unavailable).
      2. Tornado HTTP error code 599, which typically indicates some kind
         of general network failure of some kind.
      3. Socket-related errors.
    """
    if response.error:
      # Check for socket errors.
      if type(response.error) == socket.error or type(response.error) == socket.gaierror:
        return True

      # Check for HTTP errors.
      if isinstance(response.error, HTTPError):
        code = response.error.code
        if code in (500, 503, 599):
          return True

    return False

class AsyncS3Connection(AWSAuthConnection):
  """Sub-class that adds support for asynchronous S3 access. Callers provide
  their Amazon AWS access key and secret key when an instance of the class
  is created. Then, callers can repeatedly call 'make_request' in order to
  make asynchronous HTTP calls against the S3 service. Using this API
  rather than the standard boto API avoids blocking the calling thread
  until the operation is complete.
  """

  DefaultHost = 's3.amazonaws.com'
  """By default, connect to this S3 endpoint."""

  DefaultCallingFormat = SubdomainCallingFormat()
  """By default, use the S3 sub-domain format for providing bucket name."""

  def __init__(self, host=DefaultHost, aws_access_key_id=None, aws_secret_access_key=None,
               retry_policy=S3RetryPolicy()):
    AWSAuthConnection.__init__(self, host, aws_access_key_id, aws_secret_access_key)
    self.retry_policy = retry_policy

  def make_request(self, method, bucket='', key='', headers=None, params=None,
                   body=None, request_timeout=20.0, callback=None):
    """Start an asynchronous HTTP operation against the S3 service. When
    the operation is complete, the 'callback' function will be invoked,
    with the HTTP response object as its only parameter. If a failure
    occurs during execution of the operation, it may be retried, according
    to the retry policy with which this instance was initialized.
    """
    CallWithRetryAsync(self.retry_policy, self._make_request, method, bucket, key,
                       headers, params, body, request_timeout,
                       callback=callback)

  def _make_request(self, method, bucket, key, headers, params, body, request_timeout, callback):
    """Wrapped by CallWithRetryAsync in order to support retry."""
    # Build the boto HTTP request in order to create the authorization header.
    path = AsyncS3Connection.DefaultCallingFormat.build_path_base(bucket, key)
    auth_path = AsyncS3Connection.DefaultCallingFormat.build_auth_path(bucket, key)
    host = AsyncS3Connection.DefaultCallingFormat.build_host(self.server_name(), bucket)

    # Only support byte strings for now.
    assert not body or type(body) is str, "Only support byte strings (type=%s)." % type(body)

    boto_request = self.build_base_http_request(method, path, auth_path,
                                                {}, headers, body or '', host)
    boto_request.authorize(connection=self)

    # Log request for debugging.
    debug_body = boto_request.body[:256].decode(errors='ignore') if boto_request.body else None
    logging.debug('%s "%s://%s%s" headers: %s body: %s', boto_request.method, self.protocol,
                  boto_request.host, boto_request.path, boto_request.headers, debug_body)

    request_url = '%s://%s%s' % (self.protocol, host, path)
    if params:
      request_url += '?' + urllib.urlencode(params)

    # Build the tornado http client request (different version of HTTPRequest class).
    tornado_request = HTTPRequest(request_url, method=method,
                                  headers=boto_request.headers, body=body,
                                  request_timeout=request_timeout)

    # Start the asynchronous request. When it's complete, invoke 'callback', passing the HTTP response object.
    http_client = AsyncHTTPClient()
    http_client.fetch(tornado_request, callback=callback)

  def _required_auth_capability(self):
    """Called by AWSAuthConnection.__init__ in order to determine which
    auth handler to construct. In this case, S3 HMAC signing should be used.
    """
    return ['s3']
