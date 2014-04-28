# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""User operation manager.

For each active user, the OpManager creates an instance of the UserOpManager. The UserOpManager
is responsible for acquiring an operation lock, and then for executing all pending operations
which have been submitted by that user's devices. This may include operations which were
submitted to other servers, as the operations are pulled from the shared Operation table.

It is important that operations do not "fall through the cracks". If operations are concurrently
submitted to multiple servers, all operations should be executed in a timely way, even though
just one of the servers is executing the operations in serial.

Consider the case where a lock is held by server A, which is iterating in order over the
operations for user #1 and executing them. While this is happening, user #1 submits a new
operation to server B. Server B attempts to acquire the operation lock, but that fails, since
server A currently owns it. So server B simply writes the operation to the Operation table. If
this was all that happened, then the new operation might be stranded, as server A would not know
that a new operation had been inserted into the table. The operation would not be run until the
next operation is run for the user, or the table was scanned for failed operations.

The solution to this problem is for server A to inspect the "acquire_failures" attribute on the
operation lock when it's released. Server B would have incremented this value when it tried and
failed to acquire the lock. This tells server A it needs to re-query the Operations table for
any additional operations that have been added for user #1. This process may repeat many times
for a busy user.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import json
import logging
import pprint
import sys
import time
import traceback

from collections import defaultdict
from copy import deepcopy
from functools import partial
from tornado import gen, stack_context
from tornado.ioloop import IOLoop
from viewfinder.backend.base import counters, message, util
from viewfinder.backend.base.exceptions import FailpointError, InvalidRequestError, LimitExceededError, PermissionError
from viewfinder.backend.base.exceptions import CannotWaitError, NotFoundError, LockFailedError, StopOperationError
from viewfinder.backend.db.lock import Lock
from viewfinder.backend.db.lock_resource_type import LockResourceType
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.op.op_mgr_db_client import OpMgrDBClient
from viewfinder.backend.op.op_context import OpContext

# Performance counters for operation module.
# Average operation time is tracked for all operations - its historical value can be used to measure overall resource usage.
# A rate count of operations attempted and retries attempted - these numbers will indicate if a large number of operations are
# resulting in retry attempts.
_avg_op_time = counters.define_average('viewfinder.operation.avg_op_time', 'Average time in seconds per completed operation.')
_ops_per_min = counters.define_rate('viewfinder.operation.ops_per_min', 'Operations attempted per minute.', 60)
_retries_per_min = counters.define_rate('viewfinder.operation.retries_per_min', 'Operation retries attempted per minute.', 60)
_aborts_per_min = counters.define_rate('viewfinder.operation.aborts_per_min', 'Operations aborted per minute.', 60)

# Tuple of exceptions for which we will abort an operation (not retry).
# Any exception base class included here qualifies all of its subclasses.
_ABORTABLE_EXCEPTIONS = (
  PermissionError,
  InvalidRequestError,
  LimitExceededError,
  NotFoundError,
  )

# Tuple of exceptions which trigger a retry with a smaller initial backoff.
_SMALLER_RETRY_EXCEPTIONS = (
  LockFailedError,
  )

class UserOpManager(object):
  """Create an instance of the UserOpManager to execute operations for a particular user.
  Operations can be scheduled for execution using the "Execute" method, which will try to
  execute all operations in the Operation table, regardless of whether they were added by
  this server or by another server. Other servers will increment the "acquire_failures"
  attribute on the operation in order to notify the UserOpManager that it needs to requery
  the Operation table in order to get the new operations. When no more operations can be
  executed for the user, the callback passed to __init__ is invoked.
  """
  _INITIAL_BACKOFF_SECS = 8.0  # this value is increased exponentially
  _SMALL_INITIAL_BACKOFF_SECS = 2.0  # this value is increased exponentially
  _MAX_BACKOFF_STEPS = 10  # this implies a maximum backoff of ~34 minutes and 2.3 hr for small and normal backoffs.

  # Stack traces will be truncated if the operation exceeds this limit.  DynamoDB has a limit of 64KB per
  # record; we use 64 * 1000 instead of 64 * 1024 to allow for overhead and fields not explicitly measured.
  _MAX_OPERATION_SIZE = 64000

  def __init__(self, client, op_map, user_id, callback):
    """Construct a new UserOpManager in order to execute operations for the specified user.
    Each time that no more operations can be executed for the user, "callback" is invoked.
    This can happen when the operation lock cannot be acquired or when all operations have
    been executed, blocked, or quarantined.
    """
    # Wrap the DBClient so that we can detect db modifications during the
    #   operation and validate that aborts are happening without db modification.
    self._client = OpMgrDBClient(client)
    self._op_map = op_map
    self._user_id = user_id
    self._sync_cb_map = defaultdict(list)
    self._callback = stack_context.wrap(callback)
    self._is_executing = False

  def Drain(self, callback):
    """Invokes "callback" when there is no current work do be done.

    To be used for cleanup in tests.  Only needed after a previous run has failed.
    """
    self._callback = stack_context.wrap(callback)
    self.Execute()

  @gen.engine
  def Execute(self, operation_id=None, wait_callback=None):
    """Starts execution of all operations for the managed user. Once all operations have been
    completed, or if another server is already executing the operations, then the callback
    passed to __init__ is invoked. If the "operation_id" argument is provided, it is used as a
    hint as to where to start execution. However, if an operation with a lower id is found in
    the database, that is executed first, in order to ensure that the server executes operations
    in the same order that a device submitted them. If "wait_callback" is specified, then it is
    invoked when the "operation_id" operation is complete (but other operations for the user may
    still be running). If "operation_id" is None in this case, then "wait_callback" will only be
    invoked once all operations for this user are complete.
    """
    def _OnCompletedOp(type=None, value=None, tb=None):
      """Wraps the caller's callback so that it is called in the original context, and any
      exception is raised in the original context.
      """
      if (type, value, tb) != (None, None, None):
        raise type, value, tb

      wait_callback()

    @gen.engine
    def _ExecuteAll():
      """Executes all ops within the scope of an OpContext. "yield" is not supported in the
      static scope of OpContext, which is why this is a separate function.
      """
      try:
        self._is_executing = True
        self._requery = True
        while self._requery:
          yield self._ExecuteAll(operation_id=operation_id)
      finally:
        # Notify any remaining listeners that their operations are complete (since all operations are now complete).
        for cb_op_id in self._sync_cb_map.keys():
          self._InvokeSyncCallbacks(cb_op_id)

        # Complete execution.
        self._is_executing = False
        self._callback()

    # Add callbacks for synchronous case.
    if wait_callback is not None:
      self._sync_cb_map[operation_id].append(stack_context.wrap(_OnCompletedOp))

    if not self._is_executing:
      # Establish op context, and then call another func, since it is not safe to use a yield in the static scope
      # of the "with stack_context" statement. 
      with stack_context.StackContext(OpContext()):
        _ExecuteAll()
    else:
      # Sets flag so that once all operations are executed, the list of operations is re-queried
      # in order to find any newly added operations.
      self._requery = True

  @gen.coroutine
  def _ExecuteAll(self, operation_id=None):
    """Tries to acquire the operation lock. If it is acquired, queries for each operation owned
    by the user and executes each in turn.
    """
    self._requery = False

    results = yield gen.Task(Lock.TryAcquire,
                             self._client,
                             LockResourceType.Operation,
                             str(self._user_id),
                             resource_data=operation_id,
                             detect_abandonment=True)
    self._lock, status = results.args

    if status == Lock.FAILED_TO_ACQUIRE_LOCK:
      # Another server has the lock, so can't wait synchronously for the operations to complete.
      # TODO(Andy): We could poll the operations table if we want to support this.
      for operation_id in self._sync_cb_map.keys():
        self._InvokeSyncCallbacks(operation_id, CannotWaitError,
                                  'Cannot wait for the operation to complete, because another server '
                                  'owns the operation lock.')
      return

    try:
      next_ops = None
      if status == Lock.ACQUIRED_ABANDONED_LOCK and self._lock.resource_data is not None:
        # Execute the operation stored in lock.resource_data if it still exists. It is important
        # to continue with whatever operation was currently running when the abandon occurred.
        # This is because that operation may have only been partly complete.
        op = yield gen.Task(Operation.Query,
                            self._client,
                            self._user_id,
                            self._lock.resource_data,
                            col_names=None,
                            must_exist=False,
                            consistent_read=True)
        next_ops = [op]

      last_op_id = None
      while True:
        if next_ops is None:
          # Get 10 ops at a time, looking for one that is not in quarantine.
          # Use consistent reads, in order to avoid reading already deleted operations. We've
          # seen cases where an op runs, then deletes itself, but then an inconsistent read
          # gets an old version that hasn't yet been deleted and re-runs it.
          next_ops = yield gen.Task(Operation.RangeQuery,
                                    self._client,
                                    self._user_id,
                                    range_desc=None,
                                    limit=10,
                                    col_names=None,
                                    excl_start_key=last_op_id,
                                    consistent_read=True)
          if len(next_ops) == 0:
            # No more operations to process.
            break

        for op in next_ops:
          # Run the op if it is not in quarantine or if it's no longer in backoff.
          if not op.quarantine or not op.IsBackedOff():
            yield self._ExecuteOp(op)

            # Look for next op to run; always run earliest op possible.
            last_op_id = None
            break
          else:
            # Skip quarantined operation.
            logging.info('queried quarantined operation "%s", user %d backed off for %.2fs; skipping...' %
                         (op.operation_id, op.user_id, op.backoff - time.time()))
            last_op_id = op.operation_id

        next_ops = None
    finally:
      # Release the operation lock.
      yield gen.Task(self._lock.Release, self._client)

      if self._lock.acquire_failures is not None:
        # Another caller tried to acquire the lock, so there may be more operations available.
        logging.info('other servers tried to acquire lock "%s"; there may be more operations pending' % self._lock)
        self._requery = True

  @gen.coroutine
  def _ExecuteOp(self, op):
    """Executes the operation by marshalling the JSON-encoded op data as arguments to the
    operation method. The execution of the operation is wrapped in an execution scope, which
    will capture all logging during the execution of this operation.
    """
    # If necessary, wait until back-off has expired before execution begins.
    if op.backoff is not None:
      yield gen.Task(IOLoop.current().add_timeout, op.backoff)

    # Enter execution scope for this operation, so that it can be accessed in OpContext, and so that op-specific
    # logging will be started.
    with OpContext.current().Enter(op):
      op_entry = self._op_map[op.method]
      op_args = json.loads(op.json)

      # If not already done, update the lock to remember the id of the op that is being run. In
      # case of server failure, the server that takes over this lock will know where to start.
      if self._lock.resource_data != op.operation_id:
        self._lock.resource_data = op.operation_id
        yield gen.Task(self._lock.Update, self._client)

      # Migrate the arguments to the current server message version, as the format in the operations
      # table may be out-dated. Remove the headers object from the message, since it's not an
      # expected argument to the method.
      op_message = message.Message(op_args)
      yield gen.Task(op_message.Migrate,
                     self._client,
                     migrate_version=message.MAX_MESSAGE_VERSION,
                     migrators=op_entry.migrators)

      try:
        del op_args['headers']

        # Scrub the op args for logging in order to minimize personal information in the logs.
        scrubbed_op_args = op_args
        if op_entry.scrubber is not None:
          scrubbed_op_args = deepcopy(op_args)
          op_entry.scrubber(scrubbed_op_args)
        args_str = pprint.pformat(scrubbed_op_args)

        logging.info('EXECUTE: user: %d, device: %d, op: %s, method: %s:%s%s' %
                     (op.user_id, op.device_id, op.operation_id, op.method,
                      ('\n' if args_str.find('\n') != -1 else ' '), args_str))

        _ops_per_min.increment()
        if op.attempts > 0:
          _retries_per_min.increment()

        # Starting operation from beginning, so reset modified db state in the
        # OpMgrDBClient wrapper so we'll know if any modifications happened before an abort.
        self._client.ResetDBModified()

        # Actually execute the operation by invoking its handler method.
        results = yield gen.Task(op_entry.handler, self._client, **op_args)

        # Invokes synchronous callback if applicable.
        elapsed_secs = time.time() - op.timestamp
        logging.info('SUCCESS: user: %d, device: %d, op: %s, method: %s in %.3fs%s' %
                     (op.user_id, op.device_id, op.operation_id, op.method, elapsed_secs,
                      (': %s' % pprint.pformat(results) if results else '')))
        _avg_op_time.add(elapsed_secs)

        # Notify any waiting for op to finish that it's now complete.
        self._InvokeSyncCallbacks(op.operation_id)

        # Delete the op, now that it's been successfully executed.
        yield self._DeleteOp(op)
      except StopOperationError:
        # Stop the current operation in order to run a nested operation.
        pass
      except FailpointError:
        # Retry immediately if the operation is retried due to a failpoint.
        type, value, tb = sys.exc_info()
        logging.warning('restarting op due to failpoint: %s (%d)', value.filename, value.lineno)
      except Exception:
        type, value, tb = sys.exc_info()

        # Notify any waiting for op to finish that it failed (don't even wait for retries).
        self._InvokeSyncCallbacks(op.operation_id, type, value, tb)

        # Check for abortable exceptions, but only on 1st attempt.
        if op.attempts == 0 and issubclass(type, _ABORTABLE_EXCEPTIONS):
          yield self._AbortOp(op, type, value, tb)
        else:
          initial_backoff = UserOpManager._INITIAL_BACKOFF_SECS
          if issubclass(type, _SMALLER_RETRY_EXCEPTIONS):
            initial_backoff = UserOpManager._SMALL_INITIAL_BACKOFF_SECS
          yield self._FailOp(op, type, value, tb, initial_backoff_secs=initial_backoff)

  @gen.coroutine
  def _AbortOp(self, op, type, value, tb):
    """The given operation has failed in such a way that we know it will never succeed so we
    will abort it.  If it modified the DB before the failure, we log an error with callstack
    of db modification and call retry logic so that it sticks around in operation table for
    analysis.
    """
    # Did we make any modifications to the db before hitting an abortable error?
    if self._client.HasDBBeenModified():
      # If so, let's dump some information into the log about where this happened.
      stackDumpLines = ''.join(traceback.format_list(self._client.GetModifiedDBStack()))
      logging.error('Database modified before abortable exception was raised: %s' % stackDumpLines)

      # Now, go to the failure logic.
      yield self._FailOp(op, type, value, tb)
    else:
      elapsed_secs = time.time() - op.timestamp
      logging.warning('ABORT: user: %d, device: %d, op: %s, method: %s in %.3fs, %s' %
                      (op.user_id, op.device_id, op.operation_id, op.method, elapsed_secs, value))
      _avg_op_time.add(elapsed_secs)
      _aborts_per_min.increment()

      # Fully abort the op, with no possibility of retry.
      yield self._DeleteOp(op)

  @gen.coroutine
  def _FailOp(self, op, type, value, tb, initial_backoff_secs=_INITIAL_BACKOFF_SECS):
    """Writes the failure to the log and puts the operation to sleep in the database with
    a backoff. The operation will get re-run once the backoff expires. If the operation has
    failed less than 3 times, then the next operation will *not* be run until this operation
    has been retried at least 3 times. That many retries indicate there's probably a real
    issue, so the operation is considered to be in "quarantine", and execution will proceed
    to the next operation.

    TODO(Andy): Recognize certain exceptions as disallowing quarantine. In that case, we will
                not proceed to the next operation. Instead, we will abandon the lock, which
                will block further user actions until the operation is fixed.
    """
    elapsed_secs = time.time() - op.timestamp
    logging.error('FAILURE: user: %d, device: %d, op: %s, method: %s in %.3fs, %s' %
                  (op.user_id, op.device_id, op.operation_id, op.method, elapsed_secs, value),
                  exc_info=(type, value, tb))
    exc = ''.join(traceback.format_exception(type, value, tb))
    if op.first_failure:
      op.last_failure = exc
    else:
      op.first_failure = exc

    # Truncate stack traces if they make the operation too large.
    max_traceback_size = UserOpManager._MAX_OPERATION_SIZE - len(op.json)
    if (len(op.first_failure or '') + len(op.last_failure or '')) > max_traceback_size:
      if op.first_failure and op.last_failure:
        max_traceback_size = int(max_traceback_size / 2)
      if op.first_failure:
        op.first_failure = op.first_failure[-max_traceback_size:]
      if op.last_failure:
        op.last_failure = op.last_failure[-max_traceback_size:]

    # Compute an exponential backoff based on number of attempts.
    op.backoff = time.time() + (1 << min(op.attempts, UserOpManager._MAX_BACKOFF_STEPS)) * initial_backoff_secs
    retry_after_secs = op.backoff - time.time()

    op.attempts = op.attempts + 1
    if op.attempts < 3:
      # Less than 3 attempts of this operation, so hold lock and try again after a delay.
      logging.warning('%d failed attempt%s of operation %s for user %d; hold lock and retry in %.2fs' %
                      (op.attempts, util.Pluralize(op.attempts), op.operation_id, op.user_id, retry_after_secs))
    else:
      # The operation failed at least 3 times, so just write it back to database in quarantine
      # and move to next operation.
      logging.warning('%d failed attempt%s of operation %s for user %d; put operation into quarantine and '
                      'move to next operation; retry operation no sooner than %.2fs from now' %
                      (op.attempts, util.Pluralize(op.attempts), op.operation_id, op.user_id, retry_after_secs))
      self._last_op_id = op.operation_id
      op.quarantine = 1

    yield gen.Task(op.Update, self._client)

  @gen.coroutine
  def _DeleteOp(self, op):
    """Deletes the given operation and invokes the callback when that is complete."""
    self._last_op_id = op.operation_id
    try:
      yield gen.Task(op.Delete, self._client)
    except Exception:
      logging.warning('op %s (%s) was not deleted; assuming already deleted.' %
                      (op.method, op.operation_id), exc_info=True)

  def _InvokeSyncCallbacks(self, operation_id, type=None, value=None, tb=None):
    """Invoke all synchronous callbacks which are waiting for the specified
    operation to complete. If the operation completed with an error, then
    "type", "value", and/or "tb" will be defined.
    """
    sync_cb_list = self._sync_cb_map.pop(operation_id, None)
    if sync_cb_list is not None:
      for sync_cb in sync_cb_list:
        IOLoop.current().add_callback(partial(sync_cb, type, value, tb))
