# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Tests for IdAllocator data object.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import unittest

from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.id_allocator import IdAllocator

from base_test import DBBaseTestCase

class IdAllocatorTestCase(DBBaseTestCase):
  @async_test
  def testCreate(self):
    alloc = IdAllocator('type', 13)
    num_ids = 3000
    def _OnAllocated(ids):
      id_set = set(ids)
      assert len(id_set) == num_ids
      self.stop()

    with util.ArrayBarrier(_OnAllocated) as b:
      [alloc.NextId(self._client, callback=b.Callback()) for i in xrange(num_ids)]

  @async_test
  def testMultiple(self):
    """Tests that multiple allocations from the same sequence do
    not overlap.
    """
    allocs = [IdAllocator('type'), IdAllocator('type')]
    num_ids = 3000
    def _OnAllocated(id_lists):
      assert len(id_lists) == 2
      id_set1 = set(id_lists[0])
      id_set2 = set(id_lists[1])
      assert len(id_set1) == 3000
      assert len(id_set2) == 3000
      assert id_set1.isdisjoint(id_set2)
      self.stop()

    with util.ArrayBarrier(_OnAllocated) as b:
      with util.ArrayBarrier(b.Callback()) as b1:
        [allocs[0].NextId(self._client, b1.Callback()) for i in xrange(num_ids)]
      with util.ArrayBarrier(b.Callback()) as b2:
        [allocs[1].NextId(self._client, b2.Callback()) for i in xrange(num_ids)]
