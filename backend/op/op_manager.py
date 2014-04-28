# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder operation manager.

The operation manager tracks and executes operations submitted by user devices. The key goals
of the operation manager are:
  - Provide restart functionality for incomplete operations
  - Serialize operations coming from a single device
  - Mutual exclusion between multiple processing servers (only one server may operate on a
    user's operations at a time).

Restart functionality is achieved by writing each operation as JSON-encoded data to the
Operation table. Operations are given a unique id that is allocated by client devices, which
should be the order that the client would like them run by the server. Mutual exclusion is
assured by acquiring a per-user lock for operations submitted by a particular user. The
operation lock provides a server with exclusive access to operations for a user. With the lock,
the server processes each pending operation in order for a device (operations from multiple
devices may be interleaved). Another server receiving an operation for a locked user will
simply write the op to the database and continue. If a server with a lock crashes, then
operations for that user will stall for a maximum of the lock expiration time. Each server
periodically scans the lock table to pick up and resuscitate idle user operation queues which
were dropped or ignored (e.g. due to excessive load).

In cases where an operation hits transient problems (such as database unavailability) or bugs,
the operation will be retried by the manager. After a number of such retries, the operation
manager will eventually give up and put that operation into "quarantine", which means it will
be saved in the database for later developer inspection and repair. The quarantine state is
useful because without it, a failed operation would retain the operation lock and prevent all
future operations for that user from executing. This would result in total user lockout.

  OpManager: one instance per server; processes user ops which have fallen through the cracks
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import logging
import random
import time

from datetime import timedelta
from functools import partial
from tornado import gen, stack_context
from tornado.ioloop import IOLoop
from viewfinder.backend.base import message, util
from viewfinder.backend.db import db_client
from viewfinder.backend.db.lock import Lock
from viewfinder.backend.db.lock_resource_type import LockResourceType


class OpManager(object):
  """Submit new operations to the op manager via the "MaybeExecuteOp" method. The OpManager
  class manages the set of all users that have submitted operations to this server. However,
  the queue of operations is actually managed and executed by an instance of the UserOpManager
  class.

  Periodically scans the database for abandoned locks and failed operations. Each abandoned
  lock is associated with user operations that have stalled and need to be restarted. Each
  failed operation needs to be periodically retried in order to see if the underlying issue
  has been fixed.

  On startup, a random time offset is chosen before initiating the first scan. This is meant
  to avoid multiple servers scanning the same data.

  This class is meant to be a singleton for each instance of the server. Access the instance
  via OpManager.Instance().
  """
  _MAX_USERS_OUTSTANDING = 1000
  """Maximum number of users that can be under management for scans to take place."""

  _SCAN_LIMIT = 10
  """Maximum number of abandoned locks and failed operations that will be returned from scans
  (i.e. after filtering).
  """

  _MAX_SCAN_ABANDONED_LOCKS_INTERVAL = timedelta(seconds=60)
  """Time between scans for abandoned locks."""

  _MAX_SCAN_FAILED_OPS_INTERVAL = timedelta(hours=6)
  """Time between scans for failed operations to retry."""

  def __init__(self, op_map, client=None, scan_ops=False):
    """Initializes the operation map, which is a dictionary mapping from operation method str
    to an instance of OpMapEntry. Also initializes maps for active users (map from user id to
    an instance of UserOpManager).
    """
    self.op_map = op_map
    self._client = client or db_client.Instance()
    self._active_users = dict()
    self._drain_callback = None
    if scan_ops:
      self._ScanAbandonedLocks()
      self._ScanFailedOps()

  def WaitForUserOps(self, client, user_id, callback):
    """Wait for all ops running on behalf of user_id to complete. WaitForOp behaves exactly
    like using the "synchronous" option when submitting an operation. The callback will be
    invoked once all operations are completed or they're backed off due to repeated failure.
    """
    self.MaybeExecuteOp(client, user_id, None, callback)

  def Drain(self, callback):
    """Invokes "callback" when there is no current work to be done.

    To be used for cleanup in tests.
    """
    if not self._active_users:
      IOLoop.current().add_callback(callback)
    else:
      self._drain_callback = stack_context.wrap(callback)


  def MaybeExecuteOp(self, client, user_id, operation_id, wait_callback=None):
    """Adds the op's user to the queue and attempts to begin processing the operation. If the
    user is already locked by another server, or if this server is already executing operations
    for this user, then the operation is merely queued for later execution.

    If the "wait_callback" function is specified, then it is called once the operation has
    completed execution (or an error has occurred). This is useful for testing. The callback
    should have the form:
      OnExecution(value=None, type=None, tb=None)
    """
    from viewfinder.backend.op.user_op_manager import UserOpManager

    user_op_mgr = self._active_users.get(user_id, None)
    if user_op_mgr is None:
      user_op_mgr = UserOpManager(client, self.op_map, user_id,
                                  partial(self._OnCompletedOp, user_id))
      self._active_users[user_id] = user_op_mgr

    user_op_mgr.Execute(operation_id, wait_callback)

  def _OnCompletedOp(self, user_id):
    """Removes the user from the list of active users, since all of that user's operations have
    been executed.
    """
    del self._active_users[user_id]
    if not self._active_users and self._drain_callback:
      IOLoop.current().add_callback(self._drain_callback)
      self._drain_callback = None

  @gen.engine
  def _ScanFailedOps(self):
    """Periodically scans the Operation table for operations which have failed and are ready
    to retry. If any are found, they are retried to see if the error that originally caused
    them to fail has been fixed.
    """
    from viewfinder.backend.db.operation import Operation

    max_timeout_secs = OpManager._MAX_SCAN_FAILED_OPS_INTERVAL.total_seconds()
    while True:
      # If there are too many active users, do not scan.
      if len(self._active_users) < self._MAX_USERS_OUTSTANDING:
        try:
          last_key = None
          while True:
            limit = min(self._MAX_USERS_OUTSTANDING - len(self._active_users), OpManager._SCAN_LIMIT)
            ops, last_key = yield gen.Task(Operation.ScanFailed,
                                           self._client,
                                           limit=limit,
                                           excl_start_key=last_key)

            # Add each operation to the queue for the owning user.
            for op in ops:
              logging.info('scanned failed operation "%s" for user %d' % (op.operation_id, op.user_id))
              if op.user_id not in self._active_users:
                # Create a clean context for this operation since we're not blocking the current
                # coroutine on it.
                with stack_context.NullContext():
                  with util.ExceptionBarrier(util.LogExceptionCallback):
                    self.MaybeExecuteOp(self._client, op.user_id, op.operation_id)

            # Keep iterating until all failed operations have been found, otherwise wait until the next scan time.
            if last_key is None:
              break
        except Exception:
          logging.exception('failed op scan failed')

      # Wait until next scan time.
      timeout_secs = random.random() * max_timeout_secs
      timeout_time = time.time() + timeout_secs
      logging.debug('next scan in %.2fs' % timeout_secs)
      yield gen.Task(IOLoop.current().add_timeout, timeout_time)

  @gen.engine
  def _ScanAbandonedLocks(self):
    """Periodically scans the Locks table looking for abandoned operation
    locks. If any are found, the associated operations are executed.

    TODO(Andy): Scanning for abandoned locks really should go into a
                LockManager class. See header for lock.py.
    """
    max_timeout_secs = OpManager._MAX_SCAN_ABANDONED_LOCKS_INTERVAL.total_seconds()
    while True:
      # If there are too many active users, do not scan.
      if len(self._active_users) < self._MAX_USERS_OUTSTANDING:
        try:
          last_key = None
          while True:
            limit = min(self._MAX_USERS_OUTSTANDING - len(self._active_users), OpManager._SCAN_LIMIT)
            locks, last_key = yield gen.Task(Lock.ScanAbandoned,
                                             self._client,
                                             limit=limit,
                                             excl_start_key=last_key)

            for lock in locks:
              resource_type, resource_id = Lock.DeconstructLockId(lock.lock_id)
              if resource_type == LockResourceType.Operation:
                user_id = int(resource_id)
                logging.info('scanned operation lock for user %d' % user_id)
                # Create a clean context for this operation since we're not blocking the current
                # coroutine on it.
                with stack_context.NullContext():
                  with util.ExceptionBarrier(util.LogExceptionCallback):
                    self.MaybeExecuteOp(self._client, user_id, lock.resource_data)

            # Keep iterating until all abandoned locks have been found, otherwise wait until the next scan time.
            if last_key is None:
              break
        except Exception:
          logging.exception('abandoned lock scan failed')

      # Wait until next scan time.
      timeout_secs = random.random() * max_timeout_secs
      timeout_time = time.time() + timeout_secs
      logging.debug('next scan in %.2fs' % timeout_secs)
      yield gen.Task(IOLoop.current().add_timeout, timeout_time)

  @staticmethod
  def SetInstance(op_manager):
    """Sets the per-process instance of the OpManager class."""
    OpManager._instance = op_manager

  @staticmethod
  def Instance():
    """Gets the per-process instance of the OpManager class."""
    assert hasattr(OpManager, '_instance'), 'instance not initialized'
    return OpManager._instance


class OpMapEntry(object):
  """The OpManager constructor is supplied with the "operation map",
  which is a dictionary mapping from operation method str to an
  instance of this class. Each operation method is associated with
  the following information:

    handler: Method to invoke in order to execute the operation.
    migrators: Message version migrators for the method args.
    scrubber: Scrubs personal info from operation args before logging.
  """
  def __init__(self, handler, migrators=[], scrubber=None):
    self.handler = handler
    self.migrators = sorted(message.REQUIRED_MIGRATORS + migrators)
    self.scrubber = scrubber
