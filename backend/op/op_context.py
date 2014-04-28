# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Operation context support.

When an operation is executed, the Operation object is made available to all code executing
within the scope of that operation via a ContextLocal object. Furthermore, all logging within
this same scope is redirected to an op-specific location.
"""

import logging

from contextlib import contextmanager
from functools import partial
from tornado import stack_context
from viewfinder.backend.base.context_local import ContextLocal
from viewfinder.backend.storage.server_log import UserOperationLogHandler


class OpContext(ContextLocal):
  """Provides a context local object that is established on the outer "edges" of operation
  execution -- i.e. always available at any point during operation discovery or execution.

  If OpContext.current() is defined, then we're currently involved in operation discovery
  or execution. To establish an OpContext that is valid in a particular scope of async
  execution:

    with stack_context.StackContext(OpContext()):
      # Now OpContext.current() is defined in this async scope.
      ...

  If an op is currently executing, then OpContext.current().executing_op is set to that op.
  To enter an execution scope for a particular operation:

    with OpContext.current().Enter(op):
      # Anything done in this scope has access to OpContext.current().executing_op.
      ...

  Note that this usage of Enter establishes a static scope (i.e. a stack context is not used).
  It is intended to be used in concert with Tornado gen.
  """
  def __init__(self):
    super(OpContext, self).__init__()
    self.executing_op = None

  @contextmanager
  def Enter(self, op):
    """Saves the given operation as the currently executing operation. Once the caller exits
    the contextmanager, the currently executing operation is cleared.

    Redefines the current thread's logger to include a handler which keeps all log messages
    in a buffer to include with the JSON operation args and be written to the current user's
    log stream.
    """
    log_handler = None
    log_context = None
    try:
      assert op is not None, 'operation must not be None'
      assert self.executing_op is None, 'execution of nested ops is not supported'
      self.executing_op = op
      if op.method is not None:
        log_handler = UserOperationLogHandler(op)
        log_handler.setLevel(logging.INFO)
        log_context = log_handler.LoggingContext()
        log_context.__enter__()
      yield
    finally:
      if log_context is not None:
        log_context.__exit__(None, None, None)
      if log_handler is not None:
        log_handler.close()
      self.executing_op = None


def EnterOpContext(op):
  """Returns a StackContext that when entered, puts the given operation into scope in a new
  OpContext.
  """
  @contextmanager
  def _ContextManager(op):
    with OpContext():
      with OpContext.current().Enter(op):
        yield

  return stack_context.StackContext(partial(_ContextManager, op))
