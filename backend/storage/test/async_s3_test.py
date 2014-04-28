# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""AsyncS3Connection module tests."""

__author__ = "andy@emailscrubbed.com (Andy Kimball)"

import os
import random
import unittest
from tornado import options, httpclient, simple_httpclient
from viewfinder.backend.storage.async_s3 import AsyncS3Connection, S3RetryPolicy
from viewfinder.backend.base import base_options, secrets
from viewfinder.backend.base.testing import BaseTestCase, LogMatchTestCase

try:
  import pycurl
except ImportError:
  pycurl = None

@unittest.skip("needs aws credentials")
@unittest.skipIf('NO_NETWORK' in os.environ, 'no network')
class AsyncS3TestCase(BaseTestCase, LogMatchTestCase):
  def setUp(self):
    super(AsyncS3TestCase, self).setUp()

    # Init secrets with the unencrypted 'goviewfinder.com' domain.
    options.options.domain = 'goviewfinder.com'
    secrets.InitSecretsForTest()
    self.bucket = 'test-goviewfinder-com'
    self.key = 'test/hello%d' % random.randint(1, 1000000)

  def tearDown(self):
    def _OnCompletedDelete(response):
      self.stop()

    asyncS3 = AsyncS3Connection(aws_access_key_id=secrets.GetSecret('aws_access_key_id'),
                      aws_secret_access_key=secrets.GetSecret('aws_secret_access_key'))
    asyncS3.make_request('DELETE', self.bucket, self.key, callback=_OnCompletedDelete)
    self.wait()
    super(AsyncS3TestCase, self).tearDown()

  def testMakeByteRequest(self):
    """Try several successful AsyncS3Connection.make_request operations using a byte string value."""
    self._TestMakeRequest('abc 123\n\0\xc3\xb1')

  def testMakeUnicodeRequest(self):
    """Try calling AsyncS3Connection.make_request with a Unicode string (not supported)."""
    self.assertRaises(AssertionError, self._TestMakeRequest, u'abc 123\n\0\u1000')

  # Tornado 2.3 introduces _save_configuration and _restore_configuration.
  # When running on 2.2, implement them locally (in 3.0 the _impl variables
  # are being renamed, so we can't use our local versions all the time).
  def _SaveHTTPClientConfig(self):
    cls = httpclient.AsyncHTTPClient
    if hasattr(cls, '_save_configuration'):
      return cls._save_configuration()
    return cls._impl_class, cls._impl_kwargs

  def _RestoreHTTPClientConfig(self, saved):
    cls = httpclient.AsyncHTTPClient
    if hasattr(cls, '_restore_configuration'):
      cls._restore_configuration(saved)
    cls._impl_class, cls._impl_kwargs = saved

  def testMakeRequestError(self):
    """Trigger errors in AsyncS3Connection.make_request using the Simple HTTP async client."""
    saved = self._SaveHTTPClientConfig()
    try:
      httpclient.AsyncHTTPClient.configure(None)
      self.assertIsInstance(httpclient.AsyncHTTPClient(io_loop=self.io_loop), simple_httpclient.SimpleAsyncHTTPClient)
      self._TestMakeRequestError()
    finally:
      self._RestoreHTTPClientConfig(saved)

  @unittest.skipIf(pycurl is None, 'pycurl not available')
  def testMakeRequestCurlError(self):
    """Trigger errors in AsyncS3Connection.make_request using the Curl HTTP async client."""
    from tornado import curl_httpclient
    saved = self._SaveHTTPClientConfig()
    try:
      httpclient.AsyncHTTPClient.configure('tornado.curl_httpclient.CurlAsyncHTTPClient')
      self.assertIsInstance(httpclient.AsyncHTTPClient(io_loop=self.io_loop), curl_httpclient.CurlAsyncHTTPClient)
      self._TestMakeRequestError()
    finally:
      self._RestoreHTTPClientConfig(saved)

  def _TestMakeRequest(self, value):
    asyncS3 = AsyncS3Connection(host='s3.amazonaws.com', aws_access_key_id=secrets.GetSecret('aws_access_key_id'),
                      aws_secret_access_key=secrets.GetSecret('aws_secret_access_key'))

    def _OnCompletedGet(response):
      self.assertEqual(response.body, value if type(value) is str else value.encode('utf-8'))
      self.assertTrue(1)
      self.assertEqual(response.headers['Content-Type'], 'text/plain; charset=utf-8')
      self.stop()

    def _OnCompletedPut(response):
      self.assertFalse(response.error)
      asyncS3.make_request('GET', self.bucket, self.key, callback=_OnCompletedGet)

    asyncS3.make_request('PUT', self.bucket, self.key, headers={'Content-Type' : 'text/plain; charset=utf-8'},
                         body=value, callback=_OnCompletedPut)
    self.wait(timeout=30)

  def _TestMakeRequestError(self):
    def _OnErrorRetry(response):
      self.assertTrue(response.error)
      self.assertLogMatches('(Retrying function after){1}', 'Retry should have occurred once')
      self.stop()

    def _OnErrorNoRetry(response):
      self.assertTrue(response.error)
      self.assertNotLogMatches('Retrying function after', 'Retry should not happen on HTTP 403 error')
      asyncS3 = AsyncS3Connection(host='unknown', aws_access_key_id=secrets.GetSecret('aws_access_key_id'),
                                  aws_secret_access_key=secrets.GetSecret('aws_secret_access_key'),
                                  retry_policy=S3RetryPolicy(max_tries=2, min_delay=0))
      asyncS3.make_request('GET', self.bucket, self.key, callback=_OnErrorRetry)

    asyncS3 = AsyncS3Connection(aws_access_key_id='unknown',
                                aws_secret_access_key=secrets.GetSecret('aws_secret_access_key'))
    asyncS3.make_request('GET', self.bucket, self.key, callback=_OnErrorNoRetry)
    self.wait(timeout=30)
