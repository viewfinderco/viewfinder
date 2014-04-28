# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""S3ObjectStore tests.
"""
from __future__ import with_statement

__author__ = 'peter@emailscrubbed.com (Peter Mattis)'

import base64
import hashlib
import logging
import os
import random
import time
import unittest
import urllib

from tornado import httpclient, options
from viewfinder.backend.base.testing import async_test, async_test_timeout, BaseTestCase
from viewfinder.backend.base import base64hex, base_options, counters, secrets
from viewfinder.backend.storage.s3_object_store import S3ObjectStore
from viewfinder.backend.base import util

@unittest.skip("needs aws credentials")
@unittest.skipIf('NO_NETWORK' in os.environ, 'no network')
class S3ObjectStoreTestCase(BaseTestCase):
  def setUp(self):
    super(S3ObjectStoreTestCase, self).setUp()

    # Init secrets with the unencrypted 'goviewfinder.com' domain.
    options.options.domain = 'goviewfinder.com'
    secrets.InitSecretsForTest()
    self.object_store = S3ObjectStore('test-goviewfinder-com')
    self.key = 'test/hello%d' % random.randint(1, 1000000)
    self.listkey = 'test/list%d' % random.randint(1, 1000000)
    self.listkeyA = '/'.join((self.listkey, 'a'))
    self.listkeyB = '/'.join((self.listkey, 'b'))
    self.listitems = ['item%d' % i for i in range(0, 5)]

    self.meter = counters.Meter(counters.counters.viewfinder.s3)
    self.meter_start = time.time()

  def tearDown(self):
    self._RunAsync(self.object_store.Delete, self.key)
    for item in self.listitems:
      self._RunAsync(self.object_store.Delete, '/'.join((self.listkeyA, item)))
      self._RunAsync(self.object_store.Delete, '/'.join((self.listkeyB, item)))

    super(S3ObjectStoreTestCase, self).tearDown()

  def _GetCounters(self):
    return (counters.counters.viewfinder.s3.gets_per_min.get_total(),
            counters.counters.viewfinder.s3.puts_per_min.get_total())

  def _CheckCounters(self, baseline, expected_gets, expected_puts):
    # Method used in a few tests to help verify performance counters.
    baseline_gets, baseline_puts = baseline
    new_gets, new_puts = self._GetCounters()
    self.assertEqual(new_gets - baseline_gets, expected_gets)
    self.assertEqual(new_puts - baseline_puts, expected_puts)
    sample = self.meter.sample()
    elapsed = time.time() - self.meter_start
    self.assertGreater(sample.viewfinder.s3.secs_per_put, 0)
    self.meter_start += elapsed


  def testPutGet(self):
    """Test asynchronous S3 object store Put and Get methods."""
    baseline = self._GetCounters()
    self._RunAsync(self.object_store.Put, self.key, 'world')
    s = self._RunAsync(self.object_store.Get, self.key)

    self.assertEquals(s, 'world')
    self._CheckCounters(baseline, 1, 1)


  def testGetMustExist(self):
    """Test Get must_exist parameter."""
    unknown_key = 'some/unknown/key'
    self.assertRaises(httpclient.HTTPError, self._RunAsync, self.object_store.Get, unknown_key)
    self.assertRaises(httpclient.HTTPError, self._RunAsync, self.object_store.Get, unknown_key, must_exist=True)
    self.assertIsNone(self._RunAsync(self.object_store.Get, unknown_key, must_exist=False))

    self._RunAsync(self.object_store.Put, self.key, 'world')
    self.assertEquals(self._RunAsync(self.object_store.Get, self.key, must_exist=True), 'world')
    self.assertEquals(self._RunAsync(self.object_store.Get, self.key, must_exist=False), 'world')


  def testGenerateUrl(self):
    """Test GenerateUrl method on S3 object store."""
    self._RunAsync(self.object_store.Put, self.key, 'foo')

    url = self.object_store.GenerateUrl(self.key,
                                        cache_control='private,max-age=31536000',
                                        expires_in=100)
    response = httpclient.HTTPClient().fetch(url, method='GET')
    self.assertEqual(response.body, 'foo')
    self.assertEqual(response.headers['Cache-Control'], 'private,max-age=31536000')


  def testGenerateHeadUrl(self):
    """Test GenerateUrl method with 'HEAD' method on S3 object store."""
    self._RunAsync(self.object_store.Put, self.key, 'foo')

    url = self.object_store.GenerateUrl(self.key, method='HEAD', expires_in=100)
    response = httpclient.HTTPClient().fetch(url, method='HEAD', request_timeout=3.0)
    self.assertEqual(response.code, 200)
    self.assertEqual(response.headers['Content-Length'], '3')


  def testGenerateUploadUrl(self):
    """Test GenerateUploadUrl method on S3 object store."""
    content = 'hello world'
    # Generate hash of content.
    hasher = hashlib.md5()
    hasher.update(content)
    md5 = base64.b64encode(hasher.digest())

    upload_url = self.object_store.GenerateUploadUrl(self.key,
                                                     content_type='text/plain',
                                                     content_md5=md5,
                                                     expires_in=100, max_bytes=1024)
    headers = {'Content-Type': 'text/plain',
               'Content-MD5': md5}

    # Change uploaded content slightly to violate MD5 hash.
    self.assertRaises(httpclient.HTTPError, httpclient.HTTPClient().fetch,
      upload_url, method='PUT', headers=headers, body=content + '-')

    # Now upload correct content.
    response = httpclient.HTTPClient().fetch(upload_url, method='PUT', headers=headers, body=content)
    self.assertEqual(response.code, 200)

    value = self._RunAsync(self.object_store.Get, self.key)
    self.assertEqual(value, content)


  def testListItems(self):
    baseline = self._GetCounters()
    lastmarker = None

    for item in self.listitems:
      self._RunAsync(self.object_store.Put, '/'.join((self.listkeyA, item)), 'test')
      self._RunAsync(self.object_store.Put, '/'.join((self.listkeyB, item)), 'test')

    self._CheckCounters(baseline, 0, len(self.listitems) * 2)

    resultlist = self._RunAsync(self.object_store.ListKeys, prefix=self.listkeyB)
    self.assertEquals(len(resultlist), len(self.listitems))
    for i in resultlist:
      self.assertTrue(i.startswith(self.listkeyB))

    resultlist = self._RunAsync(self.object_store.ListKeys, prefix=self.listkey, maxkeys=3)
    self.assertEquals(len(resultlist), 3)
    for i in resultlist:
      self.assertTrue(i.startswith(self.listkeyA))

    lastmarker = resultlist[-1]
    resultlist = self._RunAsync(self.object_store.ListKeys, prefix=self.listkey, marker=lastmarker)
    self.assertEquals(len(resultlist), (len(self.listitems) * 2) - 3)
    for i in resultlist:
      self.assertTrue(i > lastmarker)


  def testEtag(self):
    """Test S3 ETAG mechanism."""
    hasher = hashlib.md5()
    content = 'hello world'
    hasher.update(content)
    digest = '"%s"' % hasher.hexdigest()
    # Verify Etag.
    upload_url = self.object_store.GenerateUploadUrl(self.key, expires_in=100, max_bytes=1024)
    response = httpclient.HTTPClient().fetch(upload_url, method='PUT', body=content)
    self.assertEqual(response.code, 200)
    self.assertTrue('Etag' in response.headers)
    self.assertEqual(response.headers['Etag'], digest)


  def testListCommonPrefixes(self):
    # Test setup created 'test/hello..', 'test/list...'
    files = [ 'onefile', 'onedir/foo', 'twodir/foo', 'twodir/bar', 'twodir/bardir/baz', 'twodir2/foo' ]
    for f in files:
      self._RunAsync(self.object_store.Put, f, 'test')
    (prefixes, keys) = self._RunAsync(self.object_store.ListCommonPrefixes, '/')
    self.assertEqual(prefixes, ['onedir/', 'test/', 'twodir/', 'twodir2/'])
    self.assertEqual(keys, ['onefile'])

    (prefixes, keys) = self._RunAsync(self.object_store.ListCommonPrefixes, '/', prefix='two')
    self.assertEqual(prefixes, ['twodir/', 'twodir2/'])
    self.assertEqual(keys, [])

    (prefixes, keys) = self._RunAsync(self.object_store.ListCommonPrefixes, '/', prefix='two', maxkeys=1)
    self.assertEqual(prefixes, ['twodir/'])
    self.assertEqual(keys, [])

    (prefixes, keys) = self._RunAsync(self.object_store.ListCommonPrefixes, '/', prefix='twodir/')
    self.assertEqual(prefixes, ['twodir/bardir/'])
    self.assertEqual(keys, ['twodir/bar', 'twodir/foo'])

    (prefixes, keys) = self._RunAsync(self.object_store.ListCommonPrefixes, '/', prefix='twodir/', maxkeys=1)
    # each prefix and key counts towards maxkeys. The lexicographically smallest key/prefix wins.
    self.assertEqual(prefixes, [])
    self.assertEqual(keys, ['twodir/bar'])

    # Cleanup.
    for f in files:
      self._RunAsync(self.object_store.Delete, f)


@unittest.skip("needs aws credentials")
@unittest.skipIf('NO_NETWORK' in os.environ, 'no network')
class ReadOnlyS3ObjectStoreTestCase(BaseTestCase):
  def setUp(self):
    super(ReadOnlyS3ObjectStoreTestCase, self).setUp()
    options.options.domain = 'goviewfinder.com'
    secrets.InitSecretsForTest()
    self.object_store = S3ObjectStore('test-goviewfinder-com', read_only=True)

    # Manually flip read-only so we can write a key.
    self.key = 'test'
    self.object_store._read_only = False
    self._RunAsync(self.object_store.Put, self.key, 'test')
    self.object_store._read_only = True


  def tearDown(self):
    self.object_store._read_only = False
    self._RunAsync(self.object_store.Delete, self.key)
    self.object_store._read_only = True
    super(ReadOnlyS3ObjectStoreTestCase, self).tearDown()


  def testMethods(self):
    # Read-only methods:
    self._RunAsync(self.object_store.Get, self.key)
    self._RunAsync(self.object_store.ListKeys)
    self._RunAsync(self.object_store.ListCommonPrefixes, delimiter='/')

    # Mutating methods:
    self.assertRaisesRegexp(AssertionError, 'request on read-only object store.', self._RunAsync,
                            self.object_store.Put, self.key, 'foo')
    self.assertRaisesRegexp(AssertionError, 'request on read-only object store.', self._RunAsync,
                            self.object_store.Delete, self.key)
