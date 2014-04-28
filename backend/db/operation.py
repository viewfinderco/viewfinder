# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder operation.

Operations are write-ahead logs for functions which comprise multiple steps. If server failure
or transient exceptions would otherwise leave the database in a partial state, creating an
operation to encapsulate the execution will guarantee that it is retried until successful.
Operations must be written to be idempotent, so that executing them once or many times results
in the same ending state.

Operations are submitted to the "OpManager", which contains the functionality necessary to
execute the operations and handle any failures. See the header to op_manager.py for more details.

  Operation: write-ahead log record for mutating request
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)',
               'spencer@emailscrubbed.com (Spencer Kimball)']

import json
import logging
import sys
import time

from functools import partial
from tornado import gen, stack_context
from tornado.concurrent import return_future
from viewfinder.backend.base import message, util
from viewfinder.backend.base.exceptions import StopOperationError, FailpointError, TooManyRetriesError
from viewfinder.backend.db import db_client, vf_schema
from viewfinder.backend.db.asset_id import IdPrefix, ConstructAssetId, DeconstructAssetId, VerifyAssetId
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.range_base import DBRangeObject
from viewfinder.backend.op.op_context import OpContext
from viewfinder.backend.op.op_manager import OpManager


@DBObject.map_table_attributes
class Operation(DBRangeObject):
  """Viewfinder operation data object."""
  __slots__ = ['log_handler', 'context', '_triggered_failpoints']

  _table = DBObject._schema.GetTable(vf_schema.OPERATION)
  _user_table = DBObject._schema.GetTable(vf_schema.USER)

  ANONYMOUS_DEVICE_ID = 0
  ANONYMOUS_USER_ID = 0

  FAILPOINTS_ENABLED = False
  """If false, then calls to TriggerFailpoint are no-ops."""

  def __init__(self, user_id=None, operation_id=None):
    super(Operation, self).__init__()
    self.user_id = user_id
    self.operation_id = operation_id
    self.context = {} # general purpose context dictionary that any consumers or Operation may use.
    self._triggered_failpoints = None

  def IsBackedOff(self):
    """Returns true if this operation is in exponential backoff awaiting a retry."""
    return self.backoff > time.time()

  @gen.coroutine
  def SetCheckpoint(self, client, checkpoint):
    """Stores progress information with the operation. If the operation is restarted, it can
    use this information to skip over steps it's already completed. The progress information
    is operation-specific and is not used in any way by the operation framework itself. The
    checkpoint is expected to be a JSON-serializable dict.
    """
    assert Operation.GetCurrent() == self, 'checkpoint should only be set during op execution'
    assert isinstance(checkpoint, dict), checkpoint
    self.checkpoint = checkpoint
    yield self.Update(client)

  @classmethod
  def ConstructOperationId(cls, device_id, uniquifier):
    """Returns an operation id constructed from component parts. See "ConstructAssetId" for
    details of the encoding.
    """
    return ConstructAssetId(IdPrefix.Operation, device_id, uniquifier)

  @classmethod
  def DeconstructOperationId(cls, operation_id):
    """Returns the components of an operation id: device_id, and uniquifier."""
    return DeconstructAssetId(IdPrefix.Operation, operation_id)

  @classmethod
  @gen.coroutine
  def VerifyOperationId(cls, client, user_id, device_id, operation_id):
    """Ensures that a client-provided operation id is valid according to the rules specified
    in VerifyAssetId.
    """
    yield VerifyAssetId(client, user_id, device_id, IdPrefix.Operation, operation_id, has_timestamp=False)

  @classmethod
  def GetCurrent(cls):
    """Returns the operation currently being executed. If no operation is being executed,
    returns a default operation with user_id and device_id set to None.
    """
    current = OpContext.current()
    if current is not None and current.executing_op is not None:
      return current.executing_op
    return Operation()

  @classmethod
  @gen.coroutine
  def CreateNested(cls, client, method, args):
    """Creates a new nested operation, which is based on the current operation. The current
    operation is stopped so that the nested operation can be run. The nested operation must
    complete successfully before the parent operation will be continued.

    The new operation's id parenthesizes the current operation id. For example:
      current op_id: o12345
      nested op_id: (o12345)

    This ensures that at most one nested operation runs at a time (and that it sorts and
    therefore runs before the current op), and makes it easy to identify nested operations
    when debugging.
    """
    current = OpContext.current()
    assert current is not None and current.executing_op is not None, \
           'outer operation must be running in order to execute a nested operation'
    current_op = current.executing_op

    assert 'headers' not in args, 'headers are derived from the current operation'
    args['headers'] = {'op_id': '+%s' % current_op.operation_id,
                       'op_timestamp': current_op.timestamp}

    nested_op = yield gen.Task(Operation.CreateAndExecute,
                               client,
                               current_op.user_id,
                               current_op.device_id,
                               method,
                               args)

    # If nested op is in quarantine, then fail this operation, since it cannot start until the
    # nested op has successfully completed.
    if nested_op.quarantine:
      raise TooManyRetriesError('Nested operation "%s" already exists and is in quarantine.' % nested_op.operation_id)

    raise StopOperationError()

  @classmethod
  @gen.engine
  def CreateAndExecute(cls, client, user_id, device_id, method, args, callback,
                       message_version=message.MAX_SUPPORTED_MESSAGE_VERSION):
    """Creates a new operation with 'method' and 'args' describing the operation. After
    successfully creating the operation, the operation is asynchronously executed. Returns
    the op that was executed.
    """
    # Get useful headers and strip all else.
    headers = args.pop('headers', {})
    synchronous = headers.pop('synchronous', False)

    # Validate the op_id and op_timestamp fields.
    op_id = headers.pop('op_id', None)
    op_timestamp = headers.pop('op_timestamp', None)
    assert (op_id is not None) == (op_timestamp is not None), (op_id, op_timestamp)

    # Validate that op_id is correctly formed and is allowed to be generated by the current device.
    # No need to do this if the op_id was generated by the system as part of message upgrade.
    if op_id is not None and headers.get('original_version', 0) >= message.Message.ADD_OP_HEADER_VERSION:
      yield Operation.VerifyOperationId(client, user_id, device_id, op_id)

    # Use the op_id provided by the user, or generate a system op-id.
    if op_id is None:
      op_id = yield gen.Task(Operation.AllocateSystemOperationId, client)

    # Possibly migrate backwards to a message version that is compatible with older versions of the
    # server that may still be running.
    op_message = message.Message(args, default_version=message.MAX_MESSAGE_VERSION)
    yield gen.Task(op_message.Migrate,
                   client,
                   migrate_version=message_version,
                   migrators=OpManager.Instance().op_map[method].migrators)

    op = Operation(user_id, op_id)
    op.device_id = device_id
    op.method = method
    op.json = json.dumps(args)
    op.attempts = 0

    # Set timestamp to header value if it was specified, or current timestamp if not.
    if op_timestamp is not None:
      op.timestamp = op_timestamp
    else:
      op.timestamp = util.GetCurrentTimestamp()

    # Set expired backoff so that if this process fails before the op can be executed, in the worst
    # case it will eventually get picked up by the OpManager's scan for failed ops. Note that in
    # rare cases, this may mean that the op gets picked up immediately by another server (i.e. even
    # though the current server has *not* failed), but that is fine -- it doesn't really matter what
    # server executes the op, it just matters that the op gets executed in a timely manner.
    op.backoff = 0

    # Try to create the operation if it does not yet exist.
    try:
      yield gen.Task(op.Update, client, expected={'operation_id': False})

      # Execute the op according to the 'synchronous' parameter. If 'synchronous' is True, the
      # callback is invoked only after the operation has completed. Useful during unittests to
      # ensure the mutations wrought by the operation are queryable.
      logging.info('PERSIST: user: %d, device: %d, op: %s, method: %s' % (user_id, device_id, op_id, method))
    except Exception:
      # Return existing op. 
      logging.warning('operation "%s" already exists', op_id)
      existing_op = yield gen.Task(Operation.Query, client, user_id, op_id, None, must_exist=False)
      if existing_op is not None:
         op = existing_op

    # If not synchronous, we fire the callback, but continue to execute.
    if not synchronous:
      callback(op)

      # Establish new "clean" context in which to execute the operation. The operation should not rely
      # on any context, since it may end up run on a completely different machine. In addition, establish
      # an exception barrier in order to handle any bugs or asserts, rather than letting the context
      # established for the request handle it, since it will have already completed).
      with stack_context.NullContext():
        with util.ExceptionBarrier(util.LogExceptionCallback):
          OpManager.Instance().MaybeExecuteOp(client, user_id, op.operation_id)
    else:
      # Let exceptions flow up to request context so they'll be put into an error response.
      OpManager.Instance().MaybeExecuteOp(client, user_id, op.operation_id, partial(callback, op))

  @classmethod
  def CreateAnonymous(cls, client, method, args, callback):
    """Similar to CreateAndExecute(), but uses the anonymous user and device and allocates the
    operation id from the id-allocator table.
    """
    Operation.CreateAndExecute(client, Operation.ANONYMOUS_USER_ID,
                               Operation.ANONYMOUS_DEVICE_ID, method, args, callback)

  @classmethod
  def WaitForOp(cls, client, user_id, operation_id, callback):
    """Waits for the specified operation to complete. WaitForOp behaves exactly like using the
    "synchronous" option when submitting an operation. The callback will be invoked once the
    operation has completed or if it's backed off due to repeated failure.
    """
    OpManager.Instance().MaybeExecuteOp(client, user_id, operation_id, callback)

  @classmethod
  def ScanFailed(cls, client, callback, limit=None, excl_start_key=None):
    """Scans the Operation table for operations which have failed and for which the backoff
    time has expired. These operations can be retried. Returns a tuple containing the failed
    operations and the key of the last scanned operation.
    """
    now = time.time()
    Operation.Scan(client, None, callback, limit=limit, excl_start_key=excl_start_key,
                   scan_filter={'backoff': db_client.ScanFilter([now], 'LE')})

  @classmethod
  @gen.engine
  def AllocateSystemOperationId(cls, client, callback):
    """Create a unique operation id that is generated using the system device allocator."""
    device_op_id = yield gen.Task(Device.AllocateSystemObjectId, client)
    op_id = Operation.ConstructOperationId(Device.SYSTEM, device_op_id)
    callback(op_id)

  @classmethod
  @gen.coroutine
  def TriggerFailpoint(cls, client):
    """Raises a non-abortable exception in order to cause the operation to restart. Only raises
    the exception if this failpoint has not yet been triggered for this operation.

    This facility is useful for testing operation idempotency in failure situations.
    """
    # Check whether failpoint support is enabled.
    if not Operation.FAILPOINTS_ENABLED:
      return

    op = Operation.GetCurrent()
    assert op.operation_id is not None, \
           'TriggerFailpoint can only be called in scope of executing operation'

    # Get list of previously triggered failpoints for this operation. 
    triggered_failpoints = op.triggered_failpoints or []

    # Check whether this failpoint has already been triggered for this operation.
    frame = sys._getframe().f_back
    trigger_point = [frame.f_code.co_filename, frame.f_lineno]
    if trigger_point in triggered_failpoints:
      return

    # This is first time the failpoint has been triggered, so trigger it now and save it to the op.
    triggered_failpoints.append(trigger_point)
    op = Operation.CreateFromKeywords(user_id=op.user_id,
                                      operation_id=op.operation_id,
                                      triggered_failpoints=list(triggered_failpoints))
    yield gen.Task(op.Update, client)

    raise FailpointError(*trigger_point)
