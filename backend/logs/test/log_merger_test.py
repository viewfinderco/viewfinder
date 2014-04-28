# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Test log_merger.
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import logging
import os
import unittest

from tornado import options
from viewfinder.backend.storage.object_store import ObjectStore, InitObjectStore
from viewfinder.backend.storage.file_object_store import FileObjectStore
from viewfinder.backend.base.testing import BaseTestCase
from viewfinder.backend.logs.log_merger import LocalLogMerge


class LogMergerTestCase(BaseTestCase):
  def setUp(self):
    super(LogMergerTestCase, self).setUp()
    options.options.fileobjstore = True
    InitObjectStore(temporary=True)
    self.object_store = FileObjectStore(ObjectStore.SERVER_DATA, temporary=True)
    # Put a key to initialize the file object store.
    self.key = 'hello'
    self._RunAsync(self.object_store.Put, self.key, 'world')

  def tearDown(self):
    self.object_store.Delete(self.key, None)
    super(LogMergerTestCase, self).tearDown()

  def testLogMerger(self):
    def _ContentsToLines(contents):
      lines = contents.split('\n')
      return [l for l in lines if l != '']

    def _GetLocalFile(filename):
      return _ContentsToLines(open(filename, 'r').read())

    """Test the log merging function. initial put, fetch-existing, and S3 upload."""
    first_data = ['one', 'two', 'three']
    second_data = ['four', 'five', 'six']

    ignored_data = ['ignored_one', 'ignored_two', 'ignored_three']

    merge = LocalLogMerge(self.object_store, ['test', 'instance'], 'test/path')
    # Fetch previous data, although there shouldn't be any.
    self._RunAsync(merge.FetchExistingFromS3)

    # Write the first batch of data.
    for i in first_data:
      merge.Append(i)
    merge.FlushBuffer()

    # Write some more data, but discard the buffer.
    for i in ignored_data:
      merge.Append(i)
    merge.DiscardBuffer()

    # Close and upload to S3.
    merge.Close()
    self.assertEqual(_GetLocalFile(merge._working_filename), first_data)
    self._RunAsync(merge.Upload)

    # Get file from S3.
    contents = self._RunAsync(self.object_store.Get, 'test/path/test/instance')
    self.assertEqual(_ContentsToLines(contents), first_data)

    # Create a new merge object for the same target.
    new_merge = LocalLogMerge(self.object_store, ['test', 'instance'], 'test/path')
    # Fetch previous data, although there shouldn't be any.
    self._RunAsync(new_merge.FetchExistingFromS3)

    # Append and discard first.
    for i in ignored_data:
      new_merge.Append(i)
    new_merge.DiscardBuffer()

    # Write the second batch of data.
    for i in second_data:
      new_merge.Append(i)

    # Don't flush, let Close do it for us.
    new_merge.Close()
    # Show that the two instances share the S3 filename, but not the local filename.
    self.assertEqual(merge._s3_filename, new_merge._s3_filename)
    self.assertNotEqual(merge._working_filename, new_merge._working_filename)

    self.assertEqual(_GetLocalFile(new_merge._working_filename), first_data + second_data)
    self._RunAsync(new_merge.Upload)

    # Get file from S3.
    contents = self._RunAsync(self.object_store.Get, 'test/path/test/instance')
    self.assertEqual(_ContentsToLines(contents), first_data + second_data)

    # Test Cleanup
    self.assertTrue(os.access(merge._working_filename, os.F_OK))
    merge.Cleanup()
    self.assertFalse(os.access(merge._working_filename, os.F_OK))

    self.assertTrue(os.access(new_merge._working_filename, os.F_OK))
    new_merge.Cleanup()
    self.assertFalse(os.access(new_merge._working_filename, os.F_OK))
