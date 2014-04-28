# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Reusable functional retry patterns.

Certain kinds of operations are not always reliable, such as accessing
a network (the network may be down), or communicating with a remote
service (the service may be busy). These operations can fail with
"transient" errors. Given enough time, transient errors may be resolved.
Therefore, the caller may wish to retry the operation several times in
the hope that it will eventually succeed. Callers often want to control
the number of retries, the total amount of time spent retrying, and other
properties of the retry operation. Taken together, these properties
are called a "retry policy". The functions exported by this module
enable a retry policy to be defined and then used to govern the retry
of any arbitrary asynchronous operation. Furthermore, the retry policy
and manager can be sub-classed if custom retry policies are desired.

Example Usage:

  # Create retry policy that retries 3 times, with no delay between attempts,
  # as long as the HTTP response has an error. Typically this policy would
  # be created once and reused throughout the application.
  http_retry_policy = RetryPolicy(max_tries=3,
                                  check_result=lambda resp: resp.Error)

  # Retry an asynchronous HTTP fetch operation using this policy.
  CallWithRetryAsync(http_retry_policy, client.fetch,
                     'http://www.google.com',
                     callback=handle_response)

  # Create retry policy that retries for up to 30 seconds, starting with
  # a retry interval of at least 1 second, and exponentially backing off
  # to at most 10 seconds between retries. Retry if the operation fails
  # with an exception.
  retry_policy = RetryPolicy(timeout=timedelta(seconds=30),
                             min_delay=timedelta(seconds=1),
                             max_delay=timedelta(seconds=10),
                             check_exception=lambda typ, val, tb: True)
  # or use check_exception=RetryPolicy.AlwaysRetryOnException
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import sys
import random
import functools
import time
import logging
import traceback
import util

from datetime import timedelta
from tornado.ioloop import IOLoop
from tornado.stack_context import ExceptionStackContext

class RetryPolicy(object):
  """Defines a group of properties that together govern whether and how
  an operation will be retried. The base class defines a number of common
  retry properties. It can handle two common asynchronous patterns:

    - Errors are never raised as exceptions, but instead passed to the
      callback function. Define the "check_result" argument in this case.
    - Errors are raised as exceptions, which are expected to be handled
      by a stack_context. Define the "check_exception" argument in this
      case.

  However, if additional customization is needed, then a custom retry
  policy can be created to work with CallWithRetryAsync. To do this,
  create a subclass of RetryPolicy as well as RetryManager, and
  re-implement the constructor(s), CreateManager, and/or DoRetry.
  """
  def __init__(self, max_tries=sys.maxint, timeout=timedelta.max, min_delay=timedelta(seconds=0),
               max_delay=timedelta.max, check_result=None, check_exception=None):
    """Initialize a default instance of the RetryPolicy, choosing among
    the following properties:

    max_tries (int)
      Maximum number of tries that will be attempted.

    timeout (timedelta or int or float)
      If this amount of time is exceeded, then the operation will not be
      retried. This is only checked between attempts. If a number is
      provided, then it is interpreted as a number of seconds.

    min_delay (timedelta or int or float)
      Minimum delay between attempts. After the first attempt, at least
      this amount of time must pass before the second attempt will be
      made. For subsequent tries, the delay will exponentially increase,
      up to the limit specified in max_delay. If a number is provided,
      then it is interpreted as a number of seconds.

    max_delay (timedelta or int or float)
      Maximum delay between attempts. It is useful to cap this in order
      to guarantee that an attempt will be tried at a minimum frequency,
      even after exponential back-off. If a number is provided, then it
      is interpreted as a number of seconds.

    check_result (func(*callback_args, **callback_kwargs))
      When an asynchronous operation completes, this function is passed
      the arguments to the callback function. Therefore, its signature
      should match that of the callback passed to the retry-able function.
      The check_result function should return true if the operation has
      failed with a retry-able error, or false otherwise.

    check_exception (func(type, value, traceback))
      If the asynchronous function throws an exception, this function is
      passed the parts of the exception. The check_exception should return
      true if the operation has failed with a retry-able error, or false
      otherwise.

    The exponential backoff algorithm helps to prevent "retry storms", in
    which many callers are repeatedly and insistently retrying the same
    operation. This behavior can compound any existing problem. In addition,
    a random factor is added to the backoff time in order to desynchronize
    attempts that may have been aligned.
    """
    self.max_tries = max_tries
    self.timeout = timeout if type(timeout) is timedelta else timedelta(seconds=timeout)
    self.min_delay = min_delay if type(min_delay) is timedelta else timedelta(seconds=min_delay)
    self.max_delay = max_delay if type(max_delay) is timedelta else timedelta(seconds=max_delay)
    self.check_result = check_result
    self.check_exception = check_exception

  def CreateManager(self):
    """Called by CallWithRetry in order to create a RetryManager which can
    track the progress of a particular operation. This method can be overridden
    if a custom retry policy is created.
    """
    return RetryManager(self)

  @staticmethod
  def AlwaysRetryOnException(type, value, traceback):
    """Static method to always retry on exceptions."""
    return True

class RetryManager(object):
  """For each kind of RetryPolicy, there should be a corresponding
  RetryManager which tracks the retry progress of a particular operation.
  The CallWithRetryAsync function will call CreateManager on the
  RetryPolicy instance in order to get a manager that it can use to
  track the progress of retries by calling the DoRetry method. The
  manager may track how many tries have been attempted, how much time
  has elapsed, etc.

  When the asynchronous operation has completed, CallWithRetryAsync
  will invoke the MaybeRetryOnResult function. If the asynchronous
  operation fails with an exception, then CallWithRetryAsync will
  invoke the MaybeRetryOnException function. If the invoked function
  returns false, then no retry will be attempted. Instead, the original
  callback will be invoked (in case of MaybeRetryOnResult), or the
  exception will be re-raised (in case of MaybeRetryOnException).
  However, if the function returns true, then CallWithRetryAsync
  expects it to invoke "retry_func" once the retry should be attempted.
  The function should never block the calling thread, but it may
  perform a non-blocking wait before invoking "retry_func".
  """
  def __init__(self, retry_policy):
    """Create a RetryManager that is capable of tracking properties
    defined in the RetryPolicy base class. This involves tracking the
    number of tries attempted so far, along with whether the timeout
    deadline has been exceeded.
    """
    self.retry_policy = retry_policy
    self._num_tries = 0
    self._deadline = time.time() + retry_policy.timeout.total_seconds()
    self._delay = None

  def MaybeRetryOnResult(self, retry_func, *result_args, **result_kwargs):
    """This function is called by CallWithRetryAsync once the asynchronous
    operation has completed and has invoked its callback function. It
    returns true if a retry should be attempted.
    """
    def CheckRetry():
      """Retry should be attempted if the result inspector function exists and returns true."""
      return self.retry_policy.check_result and self.retry_policy.check_result(*result_args, **result_kwargs)

    def GetLoggingText():
      """Return text that will be logged if retry is necessary."""
      return '%s returned %s' % (util.FormatFunctionCall(retry_func),
                                 util.FormatArguments(*result_args, **result_kwargs))

    return self._MaybeRetry(retry_func, CheckRetry, GetLoggingText)

  def MaybeRetryOnException(self, retry_func, type, value, tb):
    """This function is called by CallWithRetryAsync if the asynchronous
    operation raises an exception. It returns true if a retry should be
    attempted.
    """
    def CheckRetry():
      """Retry should be attempted if the exception inspector function exists and returns true."""
      return self.retry_policy.check_exception and self.retry_policy.check_exception(type, value, tb)

    def GetLoggingText():
      """Return text that will be logged if retry is necessary."""
      return '%s raised exception %s' % (util.FormatFunctionCall(retry_func),
                                         traceback.format_exception(type, value, tb))

    return self._MaybeRetry(retry_func, CheckRetry, GetLoggingText)

  def _MaybeRetry(self, retry_func, check_retry_func, log_func):
    """Helper function that determines whether a retry should be attempted.
    A retry is only attempted if "check_func" returns true. The "log_func"
    is invoked if a retry is attempted in order to get text that shows
    the context of the retry, and which will be logged.
    """
    # Check whether max tries have been exceeded.
    self._num_tries += 1
    if self._num_tries >= self.retry_policy.max_tries:
      return False

    # Check whether timeout has been exceeded.
    if time.time() >= self._deadline:
      return False

    # Invoke caller-defined function that determines whether a retry-able error has occurred.
    if not check_retry_func():
      return False

    # Retry after delay.
    if not self._delay:
      self._delay = self.retry_policy.min_delay
    else:
      self._delay *= 2

    # Cap delay.
    if self._delay > self.retry_policy.max_delay:
      self._delay = self.retry_policy.max_delay

    # Add random factor to desynchronize retries, still capped by max delay.
    sleep_time = timedelta(seconds=(random.random() + 1) * self._delay.total_seconds())
    if sleep_time > self.retry_policy.max_delay:
      sleep_time = self.retry_policy.max_delay

    # Start asynchronous sleep and instruct caller to retry.
    logging.getLogger().warning('Retrying function after %.2f seconds: %s' %
                                (sleep_time.total_seconds(), log_func()))

    if sleep_time.total_seconds() == 0:
      IOLoop.current().add_callback(retry_func)
    else:
      IOLoop.current().add_timeout(sleep_time, retry_func)

    return True

def CallWithRetryAsync(retry_policy, func, *args, **kwargs):
  """This is a higher-order function that wraps an arbitrary asynchronous
  function (plus its arguments) in order to add retry functionality. If the
  wrapped function completes with an error, then CallWithRetryAsync may call
  it again. Pass a "retry_policy" argument that derives from RetryPolicy in
  order to control the retry behavior. The retry policy determines whether
  the function completed with a retry-able error, and then decides how many
  times to retry, and how frequently to retry.
  """
  # Validate presence of named "callback" argument.
  inner_callback = kwargs.get('callback', None)
  assert 'callback' in kwargs, 'CallWithRetryAsync requires a named "callback" argument that is not None.'

  retry_manager = retry_policy.CreateManager()

  # Called when "func" is complete; checks whether to retry the call.
  def _OnCompletedCall(*callback_args, **callback_kwargs):
    """Called when the operation has completed. Determine whether to retry,
    based on the arguments to the callback.
    """
    retry_func = functools.partial(func, *args, **kwargs)
    if not retry_manager.MaybeRetryOnResult(retry_func, *callback_args, **callback_kwargs):
      # If the async operation completes successfully, don't want to retry if continuation code raises an exception.
      exception_context.check_retry = False
      inner_callback(*callback_args, **callback_kwargs)

  def _OnException(type, value, tb):
    """Called if the operation raises an exception. Determine whether to retry
    or re-raise the exception, based on the exception details.
    """
    if exception_context.check_retry:
      retry_func = functools.partial(func, *args, **kwargs)
      return retry_manager.MaybeRetryOnException(retry_func, type, value, tb)

  # Replace the callback argument with a callback to _OnCompletedCall which will check for retry.
  kwargs['callback'] = _OnCompletedCall

  # Catch any exceptions in order to possibly retry in that case.
  exception_context = ExceptionStackContext(_OnException)
  exception_context.check_retry = True
  with exception_context:
    func(*args, **kwargs)
