# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Retry module tests."""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import functools
import logging
import contextlib
from datetime import timedelta
from tornado import stack_context, testing
from viewfinder.backend.base import retry, util
from viewfinder.backend.base.testing import BaseTestCase, LogMatchTestCase

class CallWithRetryTestCase(BaseTestCase, LogMatchTestCase):

  def testWithStackContext1(self):
    """Ensure Retry preserves StackContext."""
    self.__in_context = False

    @contextlib.contextmanager
    def _MyContext():
      try:
        self.__in_context = True
        yield
      finally:
        self.__in_context = False

    def _OnCompletedCheckContext(result, error):
      self.assertTrue(self.__in_context)
      self.stop()

    with stack_context.StackContext(_MyContext):
      retry_policy = retry.RetryPolicy(max_tries=2, check_result=lambda res, err: err)
      retry.CallWithRetryAsync(retry_policy, self._AsyncFuncFailOnce, callback=_OnCompletedCheckContext)
    self.wait()

  def testWithStackContext2(self):
    """Ensure Retry doesn't interfere with asynchronous function that throws immediately."""
    try:
      with stack_context.ExceptionStackContext(self._OnError):
        retry.CallWithRetryAsync(retry.RetryPolicy(), self._AsyncFuncRaisesError,
                                 callback=self._OnCompleted)
      self.assert_(False, 'Expected exception to be raised')
    except:
      self.wait()

  def testWithStackContext3(self):
    """Ensure Retry doesn't interfere with asynchronous callback that throws."""
    try:
      with stack_context.ExceptionStackContext(self._OnError):
        retry.CallWithRetryAsync(retry.RetryPolicy(check_exception=lambda typ, val, tb: True), self._AsyncFunc,
                                 callback=self._OnCompletedRaisesError)
      self.wait()
      self.assert_(False, 'Expected exception to be raised')
    except Exception as e:
      self.assert_('_OnCompletedRaisesError' in e.message, e)

  def testWithBarrier(self):
    """Ensure Retry doesn't interfere with barriers."""
    retry_policy = retry.RetryPolicy(max_tries=2, check_result=lambda res, err: err)
    with util.MonoBarrier(self._OnCompleted) as b:
      retry.CallWithRetryAsync(retry_policy, self._AsyncFuncFailOnce, callback=b.Callback())
    self.wait()

  def testRetryPolicyApi(self):
    """Test RetryPolicy __init__ API."""
    self.assertRaises(OverflowError, functools.partial(retry.RetryPolicy, timeout=1234123412341234))

    retry.RetryPolicy(timeout=timedelta(milliseconds=500))
    self.assertEqual(retry.RetryPolicy(timeout=10).timeout.total_seconds(), 10)
    self.assertEqual(retry.RetryPolicy(timeout= -1.5).timeout.total_seconds(), -1.5)

    retry.RetryPolicy(min_delay=timedelta(days=500))
    self.assertEqual(retry.RetryPolicy(min_delay=10).min_delay.total_seconds(), 10)
    self.assertEqual(retry.RetryPolicy(min_delay= -1.5).min_delay.total_seconds(), -1.5)

    retry.RetryPolicy(max_delay=timedelta(hours=500))
    self.assertEqual(retry.RetryPolicy(max_delay=10).max_delay.total_seconds(), 10)
    self.assertEqual(retry.RetryPolicy(max_delay= -1.5).max_delay.total_seconds(), -1.5)

  def testMaxTries(self):
    """Test retry scenario in which the RetryPolicy max_tries is exceeded."""
    retry_policy = retry.RetryPolicy(max_tries=10, check_result=lambda res, err: True)
    retry.CallWithRetryAsync(retry_policy, self._AsyncFunc, callback=self._OnCompleted)
    self.wait()
    self.assertLogMatches('Retrying.*Retrying.*Retrying.*Retrying.*Retrying.*Retrying.*Retrying.*Retrying.*Retrying',
                          'Expected 9 retries in the log')

  def testTimeoutAndDelays(self):
    """Test retry scenario in which the RetryPolicy timeout is exceeded."""
    retry_policy = retry.RetryPolicy(timeout=.6, min_delay=.05, max_delay=.2, check_result=lambda res, err: True)
    retry.CallWithRetryAsync(retry_policy, self._AsyncFunc, callback=self._OnCompleted)
    self.wait()
    self.assertLogMatches('Retrying.*Retrying.*Retrying',
                          'Expected at least 3 retries in the log')

  def testCallWithRetryApi(self):
    """Test CallWithRetry API."""
    self.assertRaises(AssertionError, retry.CallWithRetryAsync, None, None)

  def testRetryWithException(self):
    """Retry on exceptions raised immediately by async function."""
    def CallWithRetry():
      retry_policy = retry.RetryPolicy(max_tries=3, check_exception=lambda typ, val, tb: True)
      retry.CallWithRetryAsync(retry_policy, self._AsyncFuncRaisesErrorOnce, dict(), callback=self.stop)

    self.io_loop.add_callback(CallWithRetry)
    self.wait()

  def testRetryWithException2(self):
    """Retry on exceptions raised by async function after stack transfer."""
    def CallAfterStackTransfer(dict, callback):
      func = functools.partial(self._AsyncFuncRaisesErrorOnce, dict, callback)
      self.io_loop.add_callback(func)

    retry_policy = retry.RetryPolicy(max_tries=3, check_exception=lambda typ, val, tb: True)
    retry.CallWithRetryAsync(retry_policy, CallAfterStackTransfer, dict(), callback=self.stop)
    self.wait()

  def _AsyncFuncRaisesErrorOnce(self, dict, callback):
    if not 'raised_error' in dict:
      dict['raised_error'] = True
      raise Exception('Error in AsyncFuncRaisesErrorOnce')
    callback()

  def _AsyncFunc(self, callback=None):
    func = functools.partial(callback, 'hello world', None)
    self.io_loop.add_callback(func)

  def _AsyncFuncRaisesError(self, callback=None):
    raise Exception('Error in _AsyncFuncRaisesError')

  def _AsyncFuncFailOnce(self, callback=None):
    if self.__dict__.has_key('_succeed_async_func_fail_once'):
      func = functools.partial(callback, 'hello world', None)
      del self._succeed_async_func_fail_once
    else:
      func = functools.partial(callback, None, Exception('Failed'))
      self._succeed_async_func_fail_once = True

    self.io_loop.add_callback(func)

  def _OnCompleted(self, result, error):
    self.stop()

  def _OnCompletedRaisesError(self, result, error):
    raise Exception('Error in _OnCompletedRaisesError')

  def _OnError(self, exc_type, value, traceback):
    self.stop()
