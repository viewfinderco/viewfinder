# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for ContextLocal object."""

from __future__ import with_statement

__author__ = 'Matt Tracy (matt@emailscrubbed.com)'

import unittest
from functools import partial
from tornado.stack_context import StackContext
from viewfinder.backend.base import context_local, util, testing

class ExampleContext(context_local.ContextLocal):
  def __init__(self, val):
    super(ExampleContext, self).__init__()
    self.val = val

class ExampleContextTwoParams(context_local.ContextLocal):
  def __init__(self, val1, val2):
    super(ExampleContextTwoParams, self).__init__()
    self.val1 = val1
    self.val2 = val2

class ContextLocalTestCase(testing.BaseTestCase):
  """Tests using a few basic ContextLocal subclasses."""

  def testNestedContexts(self):
    """Test the nesting of a single ContextLocal subclass."""
    with util.Barrier(self._OnSuccess, on_exception=self._OnException) as b:
      with StackContext(ExampleContext(1)):
        self.io_loop.add_callback(partial(self._VerifyExampleContext, 1, b.Callback()))
        with StackContext(ExampleContext(2)):
          self._VerifyExampleContext(2, util.NoCallback)
          self.io_loop.add_callback(partial(self._VerifyExampleContext, 2, b.Callback()))
        self._VerifyExampleContext(1, util.NoCallback)

    self.wait()

  def testMultipleContextTypes(self):
    """Test the usage of multiple ContextLocal subclasses in tandem."""
    with util.Barrier(self._OnSuccess, on_exception=self._OnException) as b:
      with StackContext(ExampleContext(1)):
        with StackContext(ExampleContextTwoParams(2, 3)):
          self._VerifyExampleContext(1, util.NoCallback)
          self._VerifyExampleContextTwoParams(2, 3, util.NoCallback)
          self.io_loop.add_callback(partial(self._VerifyExampleContext, 1, b.Callback()))
          self.io_loop.add_callback(partial(self._VerifyExampleContextTwoParams, 2, 3, b.Callback()))

    self.wait()


  def _OnSuccess(self):
    self.assertTrue(ExampleContext.current() is None, "Unexpected example context: context")
    self.assertTrue(ExampleContextTwoParams.current() is None)
    self.stop()

  def _OnException(self, type, value, traceback):
    try:
      raise
    finally:
      self.stop()

  def _VerifyExampleContext(self, expected, callback):
    self.assertEqual(ExampleContext.current().val, expected)
    callback()

  def _VerifyExampleContextTwoParams(self, expected1, expected2, callback):
    self.assertEqual(ExampleContextTwoParams.current().val1, expected1)
    self.assertEqual(ExampleContextTwoParams.current().val2, expected2)
    callback()





