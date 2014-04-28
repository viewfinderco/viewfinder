# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for Accounting data object.
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import logging
import time
import unittest

from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.accounting import Accounting
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.op.op_context import EnterOpContext

from base_test import DBBaseTestCase


class AccountingTestCase(DBBaseTestCase):
  def testOperationReplay(self):
    """Verify that multiple applies for the same operation ID only increment the stats once."""
    act = Accounting.CreateViewpointOwnedBy('vp1', 1)
    act.num_photos = 1

    # Manually set the current operation.
    op = Operation(1, 'o1')
    with EnterOpContext(op):
      # First write for this entry.
      self._RunAsync(Accounting.ApplyAccounting, self._client, act)
      accounting = self._RunAsync(Accounting.Query, self._client, act.hash_key, act.sort_key, None)
      assert accounting.StatsEqual(act)
      ids = accounting.op_ids.split(',')
      assert len(ids) == 1, 'len(op_ids) == %d' % len(ids)
      assert op.operation_id in ids
      assert accounting.num_photos == 1, 'num_photos: %d' % accounting.num_photos

      # Apply the same operation.
      self._RunAsync(Accounting.ApplyAccounting, self._client, act)
      accounting = self._RunAsync(Accounting.Query, self._client, act.hash_key, act.sort_key, None)
      assert accounting.StatsEqual(act)
      ids = accounting.op_ids.split(',')
      assert len(ids) == 1, 'len(op_ids) == %d' % len(ids)
      assert op.operation_id in ids
      assert accounting.num_photos == 1, 'num_photos: %d' % accounting.num_photos

    # New operation.
    op = Operation(1, 'o2')
    with EnterOpContext(op):
      self._RunAsync(Accounting.ApplyAccounting, self._client, act)
      accounting = self._RunAsync(Accounting.Query, self._client, act.hash_key, act.sort_key, None)
      ids = accounting.op_ids.split(',')
      assert len(ids) == 2, 'len(op_ids) == %d' % len(ids)
      assert op.operation_id in ids
      assert accounting.num_photos == 2, 'num_photos: %d' % accounting.num_photos

      # Simulate a "repair missing accounting entry" by dbchk. This means that the stats will be there,
      # but the op_ids field will be None.
      accounting.op_ids = None
      self._RunAsync(accounting.Update, self._client)

    # New operation.
    op = Operation(1, 'o3')
    with EnterOpContext(op):
      self._RunAsync(Accounting.ApplyAccounting, self._client, act)
      accounting = self._RunAsync(Accounting.Query, self._client, act.hash_key, act.sort_key, None)
      ids = accounting.op_ids.split(',')
      # op_ids is back to a size of 1.
      assert len(ids) == 1, 'len(op_ids) == %d' % len(ids)
      assert op.operation_id in ids
      assert accounting.num_photos == 3, 'num_photos: %d' % accounting.num_photos

    self.stop()
