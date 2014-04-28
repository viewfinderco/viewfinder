# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""tools/store_utils.py tests.
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import logging
import os
import unittest

from tornado import options
from viewfinder.backend.storage.object_store import ObjectStore, InitObjectStore
from viewfinder.backend.storage.file_object_store import FileObjectStore
from viewfinder.backend.base.testing import BaseTestCase
from viewfinder.backend.storage import store_utils


class StoreUtilsTestCase(BaseTestCase):
  def setUp(self):
    super(StoreUtilsTestCase, self).setUp()
    # Tests don't normally initialize the object store itself. We need to in order to test bucket names.
    options.options.fileobjstore = True
    InitObjectStore(temporary=True)
    self.object_store = FileObjectStore(ObjectStore.SERVER_LOG, temporary=True)
    # Put a key to initialize the file object store.
    self.key = 'hello'
    self._RunAsync(self.object_store.Put, self.key, 'world')

  def tearDown(self):
    self.object_store.Delete(self.key, None)
    super(StoreUtilsTestCase, self).tearDown()

  def testBuckets(self):
    self.assertTrue(store_utils.IsBucket(ObjectStore.SERVER_LOG))
    self.assertFalse(store_utils.IsBucket('foo'))

    self.assertIsNone(store_utils.ParseFullPath('foo/bar'))
    bucket, path = store_utils.ParseFullPath('serverlog/foo/bar')
    self.assertEqual(bucket, 'serverlog')
    self.assertEqual(path, 'foo/bar')

  def testPattern(self):
    self.assertEqual(store_utils.PrefixFromPattern(''), '')
    self.assertEqual(store_utils.PrefixFromPattern('/'), '')
    self.assertEqual(store_utils.PrefixFromPattern('foo'), 'foo/')
    self.assertEqual(store_utils.PrefixFromPattern('foo*'), 'foo')
    self.assertEqual(store_utils.PrefixFromPattern('foo/*'), 'foo/')

  def testFileExists(self):
    files = [ os.path.join('dir', '%0.2d' % x) for x in xrange(0, 100)]
    for f in files:
      self._RunAsync(self.object_store.Put, f, 'test')

    self.assertTrue(self._RunAsync(store_utils.FileExists, self.object_store, 'dir/09'))
    self.assertFalse(self._RunAsync(store_utils.FileExists, self.object_store, 'dir/091'))
    self.assertFalse(self._RunAsync(store_utils.FileExists, self.object_store, 'dir/'))
    self.assertFalse(self._RunAsync(store_utils.FileExists, self.object_store, 'dir'))

    for f in files:
      self._RunAsync(self.object_store.Delete, f)

  def testListAllKeys(self):
    files = [ os.path.join('dir', '%0.2d' % x) for x in xrange(0, 100)]
    for f in files:
      self._RunAsync(self.object_store.Put, f, 'test')

    found_files = self._RunAsync(store_utils.ListAllKeys, self.object_store)
    # Don't forget to add the key 'hello' from Setup.
    self.assertEqual(len(found_files), len(files) + 1)

    # With a smaller batch size, we end up calling ListKeys multiple times.
    found_files = self._RunAsync(store_utils.ListAllKeys, self.object_store, batch_size=10)
    self.assertEqual(len(found_files), len(files) + 1)

    found_files = self._RunAsync(store_utils.ListAllKeys, self.object_store, prefix='dir', batch_size=5)
    self.assertEqual(len(found_files), len(files))

    found_files = self._RunAsync(store_utils.ListAllKeys, self.object_store, prefix='dir/9', batch_size=5)
    self.assertEqual(len(found_files), 10)

    found_files = self._RunAsync(store_utils.ListAllKeys, self.object_store, prefix='dir/9',
                                 marker='dir/95', batch_size=5)
    self.assertEqual(len(found_files), 4)

    # Test the shortcut. This takes a pattern.
    found_files = self._RunAsync(store_utils.ListRecursively, self.object_store, '')
    self.assertEqual(len(found_files), len(files) + 1)

    found_files = self._RunAsync(store_utils.ListRecursively, self.object_store, 'dir*')
    self.assertEqual(len(found_files), len(files))

    found_files = self._RunAsync(store_utils.ListRecursively, self.object_store, 'dir/')
    self.assertEqual(len(found_files), len(files))

    found_files = self._RunAsync(store_utils.ListRecursively, self.object_store, 'dir/9*')
    self.assertEqual(len(found_files), 10)

    found_files = self._RunAsync(store_utils.ListRecursively, self.object_store, 'dir/9')
    self.assertEqual(len(found_files), 0)

    for f in files:
      self._RunAsync(self.object_store.Delete, f)

  def testListAllCommonPrefixes(self):
    files = [ 'onefile', 'onedir/foo', 'twodir/foo', 'twodir/bar', 'twodir/bardir/baz', 'twodir2/foo' ]
    for f in files:
      self._RunAsync(self.object_store.Put, f, 'test')

    dirs, files = self._RunAsync(store_utils.ListAllCommonPrefixes, self.object_store, delimiter='/')
    self.assertEqual(dirs, ['onedir/', 'twodir/', 'twodir2/'])
    self.assertEqual(files, ['hello', 'onefile'])

    dirs, files = self._RunAsync(store_utils.ListAllCommonPrefixes, self.object_store, delimiter='/', prefix='twodir/')
    self.assertEqual(dirs, ['twodir/bardir/'])
    self.assertEqual(files, ['twodir/bar', 'twodir/foo'])

    # Test shortcut.
    dirs, files = self._RunAsync(store_utils.ListFilesAndDirs, self.object_store, '')
    self.assertEqual(dirs, ['onedir/', 'twodir/', 'twodir2/'])
    self.assertEqual(files, ['hello', 'onefile'])

    dirs, files = self._RunAsync(store_utils.ListFilesAndDirs, self.object_store, '*')
    self.assertEqual(dirs, ['onedir/', 'twodir/', 'twodir2/'])
    self.assertEqual(files, ['hello', 'onefile'])

    dirs, files = self._RunAsync(store_utils.ListFilesAndDirs, self.object_store, 'two*')
    self.assertEqual(dirs, ['twodir/', 'twodir2/'])
    self.assertEqual(files, [])

    dirs, files = self._RunAsync(store_utils.ListFilesAndDirs, self.object_store, 'twodir/')
    self.assertEqual(dirs, ['twodir/bardir/'])
    self.assertEqual(files, ['twodir/bar', 'twodir/foo'])


if __name__ == '__main__':
  suite = unittest.TestLoader().loadTestsFromTestCase(StoreUtilsTestCase)
  unittest.TextTestRunner(verbosity=2).run(suite)
