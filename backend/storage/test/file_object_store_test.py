#!/usr/bin/env python
#
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""FileObjectStore tests.
"""
from __future__ import with_statement

__author__ = 'peter@emailscrubbed.com (Peter Mattis)'

import random
import unittest
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.storage.file_object_store import FileObjectStore
from viewfinder.backend.base import util
from viewfinder.backend.base.testing import BaseTestCase


class FileObjectStoreTestCase(BaseTestCase):
  def setUp(self):
    super(FileObjectStoreTestCase, self).setUp()
    self.object_store = FileObjectStore(ObjectStore.PHOTO, temporary=True)
    self.key = 'hello%d' % random.randint(1, 1000000)
    self.listkey = 'list%d' % random.randint(1, 1000000)
    self.listkeyA = '/'.join((self.listkey, 'a'))
    self.listkeyB = '/'.join((self.listkey, 'b'))
    self.listitems = ['item%d' % i for i in range(0, 10)]

  def tearDown(self):
    self.object_store.Delete(self.key, None)
    super(FileObjectStoreTestCase, self).tearDown()

  def testPutGet(self):
    self._RunAsync(self.object_store.Put, self.key, 'world')
    value = self._RunAsync(self.object_store.Get, self.key)
    self.assertEquals(value, 'world')

  def testGetMustExist(self):
    """Test Get must_exist parameter."""
    unknown_key = 'some/unknown/key'
    self.assertRaises(IOError, self._RunAsync, self.object_store.Get, unknown_key)
    self.assertRaises(IOError, self._RunAsync, self.object_store.Get, unknown_key, must_exist=True)
    self.assertIsNone(self._RunAsync(self.object_store.Get, unknown_key, must_exist=False))

    self._RunAsync(self.object_store.Put, self.key, 'world')
    self.assertEquals(self._RunAsync(self.object_store.Get, self.key, must_exist=True), 'world')
    self.assertEquals(self._RunAsync(self.object_store.Get, self.key, must_exist=False), 'world')


  def testListKeys(self):
    for item in self.listitems:
      self._RunAsync(self.object_store.Put, '/'.join((self.listkeyA, item)), 'test')
      self._RunAsync(self.object_store.Put, '/'.join((self.listkeyB, item)), 'test')

    # Test with prefix.
    resultlist = self._RunAsync(self.object_store.ListKeys, prefix=self.listkeyB)
    self.assertEquals(len(resultlist), len(self.listitems))
    for i in resultlist:
      self.assertTrue(i.startswith(self.listkeyB))

    # Test with prefix and maxkeys.
    resultlist = self._RunAsync(self.object_store.ListKeys, prefix=self.listkey, maxkeys=3)
    self.assertEquals(len(resultlist), 3)
    for i in resultlist:
      self.assertTrue(i.startswith(self.listkeyA))

    # Test with prefix and marker.
    lastmarker = resultlist[-1]
    resultlist = self._RunAsync(self.object_store.ListKeys, prefix=self.listkeyA, marker=lastmarker)
    self.assertEquals(len(resultlist), len(self.listitems) - 3)
    for i in resultlist:
      self.assertTrue(i > lastmarker)

    # Test with marker set to a non-existing key.
    lastmarker = self.listkeyB
    resultlist = self._RunAsync(self.object_store.ListKeys, marker=lastmarker)
    self.assertEquals(len(resultlist), len(self.listitems))
    for i in resultlist:
      self.assertTrue(i > lastmarker)

  def testListCommonPrefixes(self):
    files = [ 'onefile', 'onedir/foo', 'twodir/foo', 'twodir/bar', 'twodir/bardir/baz', 'twodir2/foo' ]
    for f in files:
      self._RunAsync(self.object_store.Put, f, 'test')
    (prefixes, keys) = self._RunAsync(self.object_store.ListCommonPrefixes, '/')
    self.assertEqual(prefixes, ['onedir/', 'twodir/', 'twodir2/'])
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


class ReadOnlyFileObjectStoreTestCase(BaseTestCase):
  def setUp(self):
    super(ReadOnlyFileObjectStoreTestCase, self).setUp()
    self.object_store = FileObjectStore(ObjectStore.PHOTO, temporary=True, read_only=True)

    # Manually flip read-only so we can write a key.
    self.key = 'test'
    self.object_store._read_only = False
    self._RunAsync(self.object_store.Put, self.key, 'test')
    self.object_store._read_only = True


  def tearDown(self):
    self.object_store._read_only = False
    self.object_store.Delete(self.key, None)
    self.object_store._read_only = True
    super(ReadOnlyFileObjectStoreTestCase, self).tearDown()


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


if __name__ == '__main__':
  suite = unittest.TestLoader().loadTestsFromTestCase(FileObjectStoreTestCase)
  unittest.TextTestRunner(verbosity=2).run(suite)
