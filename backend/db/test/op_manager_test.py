# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for OpManager and UserOpManager.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import json
import time

from base_test import DBBaseTestCase
from datetime import timedelta
from tornado import gen
from viewfinder.backend.base.exceptions import CannotWaitError, PermissionError
from viewfinder.backend.db.base import util
from viewfinder.backend.db.lock import Lock
from viewfinder.backend.db.lock_resource_type import LockResourceType
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.op.op_manager import OpManager, OpMapEntry
from viewfinder.backend.op.user_op_manager import UserOpManager


class OpManagerTestCase(DBBaseTestCase):
  def setUp(self):
    super(OpManagerTestCase, self).setUp()
    self._id = 1
    self._method_count = 0
    self._wait_count = 0

    # Speed up retries and decrease limits for testing.
    UserOpManager._INITIAL_BACKOFF_SECS = 0.05
    OpManager._MAX_SCAN_ABANDONED_LOCKS_INTERVAL = timedelta(seconds=0.5)
    OpManager._MAX_SCAN_FAILED_OPS_INTERVAL = timedelta(seconds=0.5)
    OpManager._SCAN_LIMIT = 1

    # Remember the current OpManager instance in order to restore it after.
    self.prev_op_mgr = OpManager.Instance()

  def tearDown(self):
    # Restore original values.
    OpManager.SetInstance(self.prev_op_mgr)
    UserOpManager._INITIAL_BACKOFF_SECS = 8.0
    OpManager._MAX_SCAN_ABANDONED_LOCKS_INTERVAL = timedelta(seconds=60)
    OpManager._MAX_SCAN_FAILED_OPS_INTERVAL = timedelta(hours=6)
    OpManager._SCAN_LIMIT = 10
    super(OpManagerTestCase, self).tearDown()

  def testMultipleOps(self):
    """Test multiple operations executed by OpManager."""
    def _OpMethod(client, callback):
      self._method_count += 1
      callback()
      if self._method_count == 3:
        self.io_loop.add_callback(self.stop)

    def _OnWait():
      self._wait_count += 1

    op_mgr = self._CreateOpManager(handlers=[_OpMethod])

    op = self._CreateTestOp(user_id=1, handler=_OpMethod)
    op_mgr.MaybeExecuteOp(self._client, op.user_id, op.operation_id, wait_callback=_OnWait)

    op = self._CreateTestOp(user_id=2, handler=_OpMethod)
    op_mgr.MaybeExecuteOp(self._client, op.user_id, op.operation_id)

    op = self._CreateTestOp(user_id=1, handler=_OpMethod)
    op_mgr.MaybeExecuteOp(self._client, op.user_id, op.operation_id)

    self.wait()
    self.assertEqual(self._wait_count, 1)

    self._RunAsync(op_mgr.Drain)

  def testScanAbandonedLocks(self):
    """Test scanning for locks which were abandoned due to server failure."""
    def _OpMethod(client, callback):
      self._method_count += 1
      callback()
      if self._method_count == 10:
        self.io_loop.add_callback(self.stop)

    for i in xrange(10):
      lock = self._AcquireOpLock(user_id=i / 2)
      lock.Abandon(self._client, self.stop)
      self.wait()
      self._CreateTestOp(user_id=i / 2, handler=_OpMethod)

    # Add an expired non-op lock to ensure that it's skipped over during scan.
    Lock.TryAcquire(self._client, LockResourceType.Job, 'v0', lambda lock, status: self.stop(lock),
                    detect_abandonment=True)
    lock = self.wait()
    lock.Abandon(self._client, self.stop)
    self.wait()

    # Now scan for abandoned locks.
    op_mgr = self._CreateOpManager(handlers=[_OpMethod])
    op_mgr._ScanAbandonedLocks()
    self.wait()

    self._RunAsync(op_mgr.Drain)

  def testResourceData(self):
    """Abandon an op lock with resource data set, and make sure that the op is run first."""
    def _OpMethod1(client, callback):
      self._method_count += 1
      callback()

    def _OpMethod2(client, callback):
      # Make sure that _OpMethod1 was already called.
      self.assertEqual(self._method_count, 1)
      callback()
      self.io_loop.add_callback(self.stop)

    op = self._CreateTestOp(user_id=100, handler=_OpMethod2)
    op = self._CreateTestOp(user_id=100, handler=_OpMethod1)
    lock = self._AcquireOpLock(user_id=100, operation_id=op.operation_id)
    self._RunAsync(lock.Abandon, self._client)

    op_mgr = self._CreateOpManager(handlers=[_OpMethod1, _OpMethod2])
    op_mgr._ScanAbandonedLocks()
    self.wait()

    self._RunAsync(op_mgr.Drain)

  def testScanFailedOps(self):
    """Test scanning for ops which have failed."""
    def _FlakyOpMethod(client, callback):
      """Fails 8 times and then succeeds."""
      self._method_count += 1
      if self._method_count <= 8:
        raise Exception('some transient failure')
      callback()
      self.io_loop.add_callback(self.stop)

    self._ExecuteOp(user_id=1, handler=_FlakyOpMethod, wait_for_op=False)
    self._ExecuteOp(user_id=2, handler=_FlakyOpMethod, wait_for_op=False)
    self.assertEqual(self._method_count, 6)

    op_mgr = self._CreateOpManager(handlers=[_FlakyOpMethod])
    op_mgr._ScanFailedOps()
    self.wait()

    self._RunAsync(op_mgr.Drain)

  def testSimpleUserOp(self):
    """Test simple operation that completes successfully."""
    self._ExecuteOp(user_id=1, handler=self._OpMethod)
    self.assertEqual(self._method_count, 1)

  def testUserOpWithArgs(self):
    """Test simple operation that completes successfully."""
    def _OpMethodWithArgs(client, callback, arg1, arg2):
      assert arg1 == 'foo' and arg2 == 10
      self._method_count += 1
      callback()

    self._ExecuteOp(user_id=1, handler=_OpMethodWithArgs, arg1='foo', arg2=10)
    self.assertEqual(self._method_count, 1)

  def testMultipleUserOps(self):
    """Test multiple operations executed by UserOpManager."""
    self._CreateTestOp(user_id=1, handler=self._OpMethod)
    self._CreateTestOp(user_id=1, handler=self._OpMethod)
    self._CreateTestOp(user_id=2, handler=self._OpMethod)
    self._ExecuteOp(user_id=1, handler=self._OpMethod)
    self.assertEqual(self._method_count, 3)

  def testAddUserOpsDuring(self):
    """Test new ops added during UserOpManager execution."""
    def _AddOpMethod3(client, callback):
      """Create operation with lower op id."""
      with util.Barrier(callback) as b:
        op_dict = self._CreateTestOpDict(user_id=1, handler=self._OpMethod)
        op_dict['operation_id'] = Operation.ConstructOperationId(1, 1)
        Operation.CreateFromKeywords(**op_dict).Update(client, b.Callback())

      # Try to acquire lock, which has side effect of incrementing "acquire_failures" and triggering requery.
      Lock.TryAcquire(self._client, LockResourceType.Operation, '1', b.Callback())

    def _AddOpMethod2(client, callback):
      """Create operation with lower op id."""
      op_dict = self._CreateTestOpDict(user_id=1, handler=_AddOpMethod3)
      op_dict['operation_id'] = Operation.ConstructOperationId(1, 5)
      Operation.CreateFromKeywords(**op_dict).Update(client, callback)

      # Explicitly call Execute for this op, since otherwise the UserOpManager won't "see" it, because
      # it has an op-id that is lower than the currently executing op-id.
      user_op_mgr.Execute(op_dict['operation_id'])

    def _AddOpMethod1(client, callback):
      """Create operation with higher op id."""
      op_dict = self._CreateTestOpDict(user_id=1, handler=_AddOpMethod2)
      Operation.CreateFromKeywords(**op_dict).Update(client, callback)

    self._id += 10
    op = self._CreateTestOp(user_id=1, handler=_AddOpMethod1)
    user_op_mgr = self._CreateUserOpManager(user_id=1, handlers=[_AddOpMethod1, _AddOpMethod2,
                                                                 _AddOpMethod3, self._OpMethod],
                                            callback=self.stop)
    user_op_mgr.Execute(op.operation_id)
    self.wait()
    self.assertEqual(self._method_count, 1)

  def testLockFailure(self):
    """Test case when UserOpManager cannot acquire lock."""
    # Acquire op lock for user #1.
    self._AcquireOpLock(user_id=1)

    # Now try to execute op that also requires same lock.
    self.assertRaises(CannotWaitError, self._ExecuteOp, user_id=1, handler=self._OpMethod)

  def testAbandonedLock(self):
    """Test acquiring an abandoned lock."""
    lock = self._AcquireOpLock(user_id=1)
    lock.Abandon(self._client, self.stop)
    self.wait()

    self._ExecuteOp(user_id=1, handler=self._OpMethod)
    self.assertEqual(self._method_count, 1)

  def testNoneOpId(self):
    """Test operation_id=None given to UserOpManager.Execute."""
    self._CreateTestOp(user_id=1, handler=self._OpMethod)
    user_op_mgr = self._CreateUserOpManager(user_id=1, handlers=[self._OpMethod], callback=self.stop)
    user_op_mgr.Execute()
    self.wait()
    self.assertEqual(self._method_count, 1)

  def testUnknownOpId(self):
    """Test unknown operation id given to UserOpManager.Execute."""
    user_op_mgr = self._CreateUserOpManager(user_id=1, handlers=[self._OpMethod], callback=self.stop)
    user_op_mgr.Execute(operation_id='unk1')
    self.wait()

  def testMultipleExecuteCalls(self):
    """Test multiple calls to UserOpManager.Execute."""
    user_op_mgr = self._CreateUserOpManager(user_id=1, handlers=[self._OpMethod], callback=self.stop)

    self._CreateTestOp(user_id=1, handler=self._OpMethod)
    user_op_mgr.Execute(operation_id='unk1')
    user_op_mgr.Execute()
    self.wait()
    self.assertEqual(self._method_count, 1)

    self._CreateTestOp(user_id=1, handler=self._OpMethod)
    user_op_mgr.Execute()
    user_op_mgr.Execute()
    self.wait()
    self.assertEqual(self._method_count, 2)

  def testMultipleWaits(self):
    """Test multiple UserOpManager.Execute, each with a wait callback for a different op."""
    with util.Barrier(self.stop) as b:
      user_op_mgr = self._CreateUserOpManager(user_id=1, handlers=[self._OpMethod], callback=b.Callback())

      op1 = self._CreateTestOp(user_id=1, handler=self._OpMethod)
      op2 = self._CreateTestOp(user_id=1, handler=self._OpMethod)
      user_op_mgr.Execute(operation_id=op1.operation_id, wait_callback=b.Callback())
      user_op_mgr.Execute(operation_id=op1.operation_id, wait_callback=b.Callback())
      user_op_mgr.Execute(operation_id=op2.operation_id, wait_callback=b.Callback())

    self.wait()
    self.assertEqual(self._method_count, 2)

  def testWaitFailure(self):
    """Test wait for operation that results in failure."""
    def _BuggyOpMethod(client, callback):
      self._method_count += 1
      if self._method_count == 1:
        raise Exception('some permanent failure')
      callback()

    self.assertRaises(Exception, self._ExecuteOp, 1, _BuggyOpMethod)
    self.assertEqual(self._method_count, 1)

    self._RunAsync(self.user_op_mgr.Drain)

  def testTransientFailure(self):
    """Test op that fails once and then succeeds."""
    def _FlakyOpMethod(client, callback):
      self._method_count += 1
      if self._method_count == 1:
        raise Exception('some transient failure')
      callback()

    self._ExecuteOp(user_id=1, handler=_FlakyOpMethod, wait_for_op=False)
    self.assertEqual(self._method_count, 2)

  def testPermanentFailure(self):
    """Test op that continually fails."""
    def _BuggyOpMethod(client, callback):
      self._method_count += 1
      raise Exception('some permanent failure')

    op = self._CreateTestOp(user_id=1, handler=_BuggyOpMethod)
    user_op_mgr = self._CreateUserOpManager(user_id=1, handlers=[_BuggyOpMethod], callback=self.stop)
    user_op_mgr.Execute()
    self.wait()
    self.assertEqual(self._method_count, 3)

    # Ensure that operation still exists in db with right values.
    Operation.Query(self._client, 1, op.operation_id, None, lambda op: self.stop(op))
    op = self.wait()
    self.assertIsNotNone(op.first_failure)
    self.assertIsNotNone(op.last_failure)
    self.assertEqual(op.attempts, 3)
    self.assertEqual(op.quarantine, 1)
    self.assertGreater(op.backoff, 0)

  def testRerunBeforeContinue(self):
    """Test that a previous operation is retried 3 times before the next operation is attempted."""
    @gen.coroutine
    def _NextOpMethod(client):
      # Multiply the method count, which tells us if this was called before or after the 2nd call
      # to _FlakyOpMethod.
      self._method_count *= 4

    @gen.coroutine
    def _FlakyOpMethod(client):
      # Fail 1st to attempts, and succeed on the 3rd.
      self._method_count += 1
      if self._method_count <= 2:
        raise Exception('some transient failure')

    # Create two operations and ensure that first is re-run before second is completed.
    op = self._CreateTestOp(user_id=1, handler=_FlakyOpMethod)
    op2 = self._CreateTestOp(user_id=1, handler=_NextOpMethod)
    user_op_mgr = self._CreateUserOpManager(user_id=1, handlers=[_FlakyOpMethod, _NextOpMethod], callback=self.stop)
    user_op_mgr.Execute()
    self.wait()
    self.assertEqual(self._method_count, 12)

    # Ensure that all operations completed and were deleted.
    self.assertEqual(self._RunAsync(Operation.RangeQuery, self._client, 1, None, None, None), [])

  def testLargePermanentFailure(self):
    """Test when DynamoDB limits the size of the traceback of a failing op."""
    def _BuggyOpMethod(client, callback, blob):
      raise Exception('some permanent failure')

    op = self._CreateTestOp(user_id=1, handler=_BuggyOpMethod, blob='A' * (UserOpManager._MAX_OPERATION_SIZE - 200))
    user_op_mgr = self._CreateUserOpManager(user_id=1, handlers=[_BuggyOpMethod], callback=self.stop)
    user_op_mgr.Execute()
    self.wait()

    Operation.Query(self._client, 1, op.operation_id, None, lambda op: self.stop(op))
    op = self.wait()
    self.assertIsNotNone(op.first_failure)
    self.assertIsNotNone(op.last_failure)
    self.assertLessEqual(len(op.first_failure), 100)
    self.assertLessEqual(len(op.last_failure), 100)

  def testAbortOfPermissionError(self):
    """Test op that hits an abortable error."""
    def _BuggyOpMethod(client, callback):
      self._method_count += 1
      # PermissionError is one of the exceptions which qualifies as abortable.
      raise PermissionError('Not Authorized')

    op = self._CreateTestOp(user_id=1, handler=_BuggyOpMethod)
    user_op_mgr = self._CreateUserOpManager(user_id=1, handlers=[_BuggyOpMethod], callback=self.stop)
    user_op_mgr.Execute()
    self.wait()
    self.assertEqual(self._method_count, 1)

    # Ensure that operation does not exist in the db.
    Operation.Query(self._client, 1, op.operation_id, None, lambda op: self.stop(op), must_exist=False)
    op = self.wait()
    self.assertTrue(op is None)

  def testMissingOpId(self):
    """Provide non-existent op-id to UserOpManager.Execute."""
    self._CreateTestOp(user_id=1, handler=self._OpMethod)
    user_op_mgr = self._CreateUserOpManager(user_id=1, handlers=[self._OpMethod], callback=self.stop)
    user_op_mgr.Execute(operation_id='unknown')
    self.wait()
    self.assertEqual(self._method_count, 1)

  def testNestedOp(self):
    """Test creation and invocation of nested operation."""
    @gen.coroutine
    def _InnerMethod(client, arg1, arg2):
      self._method_count += 1
      self.assertEqual(arg1, 1)
      self.assertEqual(arg2, 'hello')
      self.assertEqual(self._method_count, 2)

      # Assert that nested operation is derived from parent op.
      inner_op = Operation.GetCurrent()
      self.assertEqual(inner_op.user_id, outer_op.user_id)
      self.assertEqual(inner_op.timestamp, outer_op.timestamp)
      self.assertEqual(inner_op.operation_id, '+%s' % outer_op.operation_id)

    @gen.coroutine
    def _OuterMethod(client):
      self._method_count += 1
      if self._method_count == 1:
        yield Operation.CreateNested(client, '_InnerMethod', {'arg1': 1, 'arg2': 'hello'})

    # Create custom OpManager and make it the current instance for duration of test.
    op_mgr = self._CreateOpManager(handlers=[_OuterMethod, _InnerMethod])
    OpManager.SetInstance(op_mgr)

    outer_op = self._CreateTestOp(user_id=1, handler=_OuterMethod)
    self._RunAsync(op_mgr.WaitForUserOps, self._client, 1)
    self.assertEqual(self._method_count, 3)

  def testMultiNestedOp(self):
    """Test nested op within nested op."""
    @gen.coroutine
    def _InnererMethod(client, arg3):
      self.assertTrue(Operation.GetCurrent().operation_id.startswith('++'))
      self.assertEqual(arg3, 3)
      self._method_count += 1

    @gen.coroutine
    def _InnerMethod(client, arg2):
      self.assertEqual(arg2, 2)
      self._method_count += 1
      if self._method_count == 2:
        yield Operation.CreateNested(client, '_InnererMethod', {'arg3': 3})

    @gen.coroutine
    def _OuterMethod(client, arg1):
      self.assertEqual(arg1, 1)
      self._method_count += 1
      if self._method_count == 1:
        yield Operation.CreateNested(client, '_InnerMethod', {'arg2': 2})

    # Create custom OpManager and make it the current instance for duration of test.
    op_mgr = self._CreateOpManager(handlers=[_OuterMethod, _InnerMethod, _InnererMethod])
    OpManager.SetInstance(op_mgr)

    outer_op = self._CreateTestOp(user_id=1, handler=_OuterMethod, arg1=1)
    self._RunAsync(op_mgr.WaitForUserOps, self._client, 1)
    self.assertEqual(self._method_count, 5)

  def testNestedOpError(self):
    """Test nested op that fails with errors."""
    @gen.coroutine
    def _InnerMethod(client):
      self._method_count += 1
      if self._method_count < 8:
        raise Exception('permanent error')

    @gen.coroutine
    def _OuterMethod(client):
      self._method_count += 1
      if self._method_count < 8:
        yield Operation.CreateNested(client, '_InnerMethod', {})
        self.assertEqual(Operation.GetCurrent().quarantine, 1)

    # Create custom OpManager and make it the current instance for duration of test.
    op_mgr = self._CreateOpManager(handlers=[_OuterMethod, _InnerMethod])
    OpManager.SetInstance(op_mgr)

    outer_op = self._CreateTestOp(user_id=1, handler=_OuterMethod)
    op_mgr.MaybeExecuteOp(self._client, 1, None)

    # Now run failed ops (they should eventually succeed due to method_count < 8 checks) and ensure
    # that ops complete.
    while len(self._RunAsync(Operation.RangeQuery, self._client, 1, None, None, None)) != 0:
      pass

    self.assertEqual(self._method_count, 9)

  def _OpMethod(self, client, callback):
    self._method_count += 1
    callback()

  def _AcquireOpLock(self, user_id, operation_id=None):
    Lock.TryAcquire(self._client, LockResourceType.Operation, str(user_id), lambda lock, status: self.stop(lock),
                    resource_data=operation_id)
    return self.wait()

  def _ExecuteOp(self, user_id, handler, wait_for_op=True, **kwargs):
    op = self._CreateTestOp(user_id=user_id, handler=handler, **kwargs)

    # Don't call self.stop() until we've gotten both the "completed all" and the "op wait" callbacks.
    with util.Barrier(self.stop) as b:
      self.user_op_mgr = self._CreateUserOpManager(user_id=user_id, handlers=[handler], callback=b.Callback())
      self.user_op_mgr.Execute(op.operation_id, b.Callback() if wait_for_op else None)
    self.wait()

    # Ensure that lock is released.
    lock_id = Lock.ConstructLockId(LockResourceType.Operation, str(user_id))
    Lock.Query(self._client, lock_id, None, lambda lock: self.stop(lock), must_exist=False)
    lock = self.wait()
    self.assertIsNone(lock, 'operation lock should have been released')

    return op

  def _CreateOpManager(self, handlers):
    op_map = {handler.__name__: OpMapEntry(handler, []) for handler in handlers}
    return OpManager(op_map, client=self._client, scan_ops=True)

  def _CreateUserOpManager(self, user_id, handlers, callback):
    op_map = {handler.__name__: OpMapEntry(handler, []) for handler in handlers}
    return UserOpManager(self._client, op_map, user_id, callback)

  def _CreateTestOp(self, user_id, handler, **kwargs):
    Operation.ConstructOperationId(1, self._id)
    self._id += 1

    op_dict = self._CreateTestOpDict(user_id, handler, **kwargs)
    op = Operation.CreateFromKeywords(**op_dict)

    op.Update(self._client, self.stop)
    self.wait()

    return op

  def _CreateTestOpDict(self, user_id, handler, **kwargs):
    op_id = Operation.ConstructOperationId(1, self._id)
    self._id += 1

    op_dict = {'user_id': user_id,
               'operation_id': op_id,
               'device_id': 1,
               'method': handler.__name__,
               'json': json.dumps(kwargs, indent=True),
               'timestamp': time.time(),
               'attempts': 0}

    return op_dict
