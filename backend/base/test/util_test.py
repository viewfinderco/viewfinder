# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Utility tests.

  ParseHostPort(): parses host:port string and returns tuple
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)'
               'andy@emailscrubbed.com (Andy Kimball)']

import logging
import time
import unittest
from datetime import date, timedelta
from functools import partial

from viewfinder.backend.base import util, testing

class BarrierTestCase(testing.BaseTestCase):
  """Tests for basic barrier type."""
  def testBarrier(self):
    val = [False]
    def _Callback():
      val[0] = True
      self.stop()

    with util.Barrier(_Callback) as b:
      cb1 = b.Callback()
      cb2 = b.Callback()
    cb1()
    self.io_loop.add_callback(self.stop)
    self.wait()
    self.assertFalse(val[0])
    cb2()
    self.wait()
    self.assertTrue(val[0])

  def testEmptyBarrier(self):
    val = [False]
    def _Callback():
      val[0] = True
      self.stop()

    with util.Barrier(_Callback):
      pass

    self.wait()
    self.assertTrue(val[0])

  def testEmptyBarrierException(self):
    val = [False]
    def _Exception(type_, value_, traceback):
      print "Exception"
      self.io_loop.add_callback(self.stop)

    def _Completed():
      print "Completed"
      val[0] = True

    with util.Barrier(_Completed, _Exception):
      raise KeyError('Key')

    self.wait()
    self.assertFalse(val[0], 'Barrier complete method was called unexpectedly.')

  def testCompletedBeforeException(self):
    """Make the barrier callback and then raise exception."""
    val = [0]
    def _Exception(type_, value_, traceback):
      logging.info("Exception")
      val[0] += 1

    def _Completed():
      logging.info("Completed")
      val[0] += 1

    def _RaiseException():
      raise KeyError('key')

    def _PropException(type_, value_, traceback):
      self.io_loop.add_callback(self.stop)

    with util.ExceptionBarrier(_PropException):
      with util.Barrier(_Completed, _Exception):
        self.io_loop.add_callback(_RaiseException)

    self.wait()
    self.assertEqual(val[0], 1, 'Both _Completed and _Exception were called.')

  def testCompletedAfterException(self):
    """Raise exception and then make the barrier callback."""
    val = [0]
    def _Exception(type_, value_, traceback):
      logging.info("Exception")
      val[0] += 1
      self.io_loop.add_callback(self.stop)

    def _Completed():
      logging.info("Completed")
      val[0] += 1
      self.io_loop.add_callback(self.stop)

    def _RaiseException(completed_cb):
      self.io_loop.add_callback(partial(completed_cb, 1))
      raise KeyError('key')

    with util.ArrayBarrier(_Completed, on_exception=_Exception) as b:
      self.io_loop.add_callback(partial(_RaiseException, b.Callback()))
      self.io_loop.add_callback(partial(_RaiseException, b.Callback()))

    self.wait()
    self.assertEqual(val[0], 1, 'Both _Completed and _Exception were called.')


class MonoBarrierTestCase(testing.BaseTestCase):
  """Tests for MonoBarrier barrier type."""
  def testBarrier(self):
    val = []
    def _Callback(result):
      val.append(result)
      self.stop()

    with util.MonoBarrier(_Callback) as b:
      cb = b.Callback()
      self.assertRaises(Exception, b.Callback)
    cb(1)
    self.wait()
    self.assertEqual(1, val[0])

  def testEmptyBarrier(self):
    val = [False]
    def _Callback(result):
      self.assertEqual(result, None)
      val[0] = True
      self.stop()

    with util.MonoBarrier(_Callback):
      pass
    self.wait()
    self.assertTrue(val[0])

  def testCallbackPositionalArguments(self):
    val = [0]
    def _Callback(arg1, arg2):
      self.stop()
      self.assertEqual(arg1, 'arg1')
      self.assertEqual(arg2, 'arg2')
      val[0] = 1

    def _Exception(type_, instance_, traceback):
      self.stop()
      self.assertTrue(type_ is TypeError)
      val[0] = 2

    with util.MonoBarrier(_Callback) as b:
      b.Callback()('arg1', 'arg2')
    self.wait()
    self.assertEqual(1, val[0])

    with util.Barrier(_Callback, on_exception=_Exception) as b1:
      with util.MonoBarrier(_Callback) as b2:
        b2.Callback()(b1.Callback())
    self.wait()
    self.assertEqual(2, val[0])


class ResultsBarrierTestCase(testing.BaseTestCase):
  """Tests for Results barrier."""
  def testResultsBarrier(self):
    val = [False]
    def _Callback(exp_results, results):
      self.stop()
      self.assertEqual(results, exp_results)
      val[0] = True

    with util.ArrayBarrier(partial(_Callback, [1, 2, 3])) as b:
      b.Callback()(1)
      b.Callback()(2)
      b.Callback()(3)
    self.wait()
    self.assertTrue(val[0])

  def testEmptyBarrier(self):
    val = [False]
    def _Callback(exp_results, results):
      self.stop()
      self.assertEqual(results, exp_results)
      val[0] = True

    with util.ArrayBarrier(partial(_Callback, [])):
      pass
    self.wait()
    self.assertTrue(val[0])

  def testCompact(self):
    val = [False]
    def _Callback(exp_results, results):
      self.stop()
      self.assertEqual(exp_results, results)
      val[0] = True

    with util.ArrayBarrier(partial(_Callback, [2]), compact=True) as b:
      b.Callback()(None)
      b.Callback()(2)
      b.Callback()(None)
    self.wait()
    self.assertTrue(val[0])


class ArrayBarrierTestCase(testing.BaseTestCase):
  """Tests for ArrayBarrier barrier type."""
  def testArrayBarrier(self):
    val = [False]
    def _Callback(exp_results, results):
      self.stop()
      self.assertEqual(exp_results, results)
      val[0] = True

    with util.ArrayBarrier(partial(_Callback, ['cb1', 'cb2', 'cb3', 'cb4'])) as b:
      b.Callback()('cb1')
      b.Callback()('cb2')
      b.Callback()('cb3')
      b.Callback()('cb4')
    self.wait()
    self.assertTrue(val[0])


class DictBarrierTestCase(testing.BaseTestCase):
  """Tests for DictBarrier type."""
  def testDictBarrier(self):
    val = [False]
    def _Callback(exp_results, results):
      self.stop()
      self.assertEqual(exp_results, results)
      val[0] = True

    with util.DictBarrier(partial(_Callback, {'key1': 1, 'key2': 2, 'key3': 3})) as b:
      b.Callback('key1')(1)
      b.Callback('key2')(2)
      b.Callback('key3')(3)
    self.wait()
    self.assertTrue(val[0])


class ExceptionBarrierTestCase(testing.BaseTestCase):
  """Tests for ExceptionBarrier type."""
  def testImmediateException(self):
    """Test exception raised before barrier context is exited."""
    def _OnException(type, value, tb):
      self.stop()

    with util.ExceptionBarrier(_OnException):
      raise Exception('an error')
    self.wait()

  def testDelayedException(self):
    """Test exception raised after initial barrier context has exited."""
    def _OnException(type, value, tb):
      self.stop()

    def _RaiseException():
      raise Exception('an error')

    with util.ExceptionBarrier(_OnException):
      self.io_loop.add_callback(_RaiseException)
    self.wait()

  def testCallback(self):
    """ERROR: Try to use Callback() method on barrier."""
    def _OnException(type, value, tb):
      self.assertEqual(type, AssertionError)
      self.stop()

    with util.ExceptionBarrier(_OnException) as b:
      b.Callback()
    self.wait()

  def testMultipleExceptions(self):
    """ERROR: Raise multiple exceptions within scope of exception barrier."""
    def _OnException(type, value, tb):
      self.stop()

    def _RaiseException():
      raise Exception('an error')

    with util.ExceptionBarrier(_OnException) as b:
      self.io_loop.add_callback(_RaiseException)
      self.io_loop.add_callback(_RaiseException)
    self.wait()


class NestedBarrierTestCase(testing.BaseTestCase):
  def testUnhandledExeption(self):
    """Verify that without an exception handler, a thrown exception
    in a barrier propagates.
    """
    success = [False]

    def _Op(cb):
      raise ZeroDivisionError('exception')

    def _OnSuccess():
      success[0] = True

    def _RunBarrier():
      with util.Barrier(_OnSuccess) as b:
        _Op(b.Callback())

    self.assertRaises(ZeroDivisionError, _RunBarrier)
    self.assertTrue(not success[0])

  def testHandledException(self):
    """Verify that if an exception handler is specified, a thrown
    exception doesn't propagate.
    """
    exception = [False]
    success = [False]

    def _OnException(type, value, traceback):
      exception[0] = True
      self.io_loop.add_callback(self.stop)

    def _OnSuccess():
      success[0] = True

    def _Op(cb):
      raise Exception('exception')

    with util.Barrier(_OnSuccess, on_exception=_OnException) as b:
      _Op(b.Callback())

    self.wait()
    self.assertTrue(exception[0])
    self.assertTrue(not success[0])

  def testNestedBarriers(self):
    """Verify that a handled exception in a nested barrier doesn't prevent
    outer barrier from completing.
    """
    exceptions = [False, False]
    level1_reached = [False]

    def _Level2Exception(type, value, traceback):
      exceptions[1] = True

    def _Level2(cb):
      raise Exception('exception in level 2')

    def _Level1Exception(type, value, traceback):
      exceptions[0] = True

    def _OnLevel1():
      self.io_loop.add_callback(self.stop)
      level1_reached[0] = True

    def _Level1(cb):
      with util.Barrier(None, on_exception=_Level2Exception) as b:
        _Level2(b.Callback())
      _OnLevel1()

    with util.Barrier(_OnLevel1, on_exception=_Level1Exception) as b:
      _Level1(b.Callback())
    self.wait()
    self.assertTrue(not exceptions[0])
    self.assertTrue(exceptions[1])
    self.assertTrue(level1_reached[0])


class ParseHostPortTestCase(unittest.TestCase):
  def setUp(self):
    pass
  def tearDown(self):
    pass
  def testSimple(self):
    self.assertEquals(util.ParseHostPort("host:80"), ("host", 80))
  def testSimple2(self):
    self.assertEquals(util.ParseHostPort("host.example.com:80"), ("host.example.com", 80))
  def testIP(self):
    self.assertEquals(util.ParseHostPort("127.0.0.1:80"), ("127.0.0.1", 80))
  def testEmpty(self):
    self.assertRaises(TypeError, util.ParseHostPort, "")
  def testHostOnly(self):
    self.assertRaises(TypeError, util.ParseHostPort, "host")
  def testPortOnly(self):
    self.assertRaises(TypeError, util.ParseHostPort, ":1")
  def testThreeValues(self):
    self.assertRaises(TypeError, util.ParseHostPort, "host:1:2")
  def testNoColon(self):
    self.assertRaises(TypeError, util.ParseHostPort, "host;1")
  def testNonIntegerPort(self):
    self.assertRaises(TypeError, util.ParseHostPort, "host:port")
  def testOutOfRangePort(self):
    self.assertRaises(TypeError, util.ParseHostPort, "host:65536")
  def testLongPort(self):
    self.assertRaises(TypeError, util.ParseHostPort, "host:1000000000000")


class VarLengthEncodeDecodeTestCase(unittest.TestCase):
  def testEncode(self):
    self._VerifyEncodeDecode(1, '\x01')
    self._VerifyEncodeDecode(2, '\x02')
    self._VerifyEncodeDecode(127, '\x7f')
    self._VerifyEncodeDecode(128, '\x80\x01')
    self._VerifyEncodeDecode(255, '\xff\x01')
    self._VerifyEncodeDecode(0xffff, '\xff\xff\x03')
    self._VerifyEncodeDecode(0xffffffff, '\xff\xff\xff\xff\x0f')
    self._VerifyEncodeDecode(0xffffffffffffffff, '\xff\xff\xff\xff\xff\xff\xff\xff\xff\x01')

  def testConcatEncodeDecode(self):
    numbers = [0xfff112, 0x12, 0x0, 0xffffffffff]
    raw_bytes = ''
    for n in numbers:
      raw_bytes += util.EncodeVarLengthNumber(n)
    for n in numbers:
      val, length = util.DecodeVarLengthNumber(raw_bytes)
      self.assertEqual(val, n)
      raw_bytes = raw_bytes[length:]

  def testInvalidDecode(self):
    self.assertRaises(TypeError, util.DecodeVarLengthNumber, '\xff\xff\xff\xff\xff\xff\xff\xff\xff\xff')

  def _VerifyEncodeDecode(self, number, string):
    self.assertEqual(util.EncodeVarLengthNumber(number), string)
    self.assertEqual(util.DecodeVarLengthNumber(string), (number, len(string)))


class DecayingStatTestCase(unittest.TestCase):
  def testDecay(self):
    now = 0.0
    stat = util.DecayingStat(half_life=1.0, now=now)
    stat.Add(1.0, now)
    self.assertAlmostEquals(stat.Get(now), 1.0)
    stat.Add(1.0, now)
    self.assertAlmostEquals(stat.Get(now), 2.0)
    now = 1.0
    self.assertAlmostEquals(stat.Get(now), 1.0)


class LRUCacheTestCase(unittest.TestCase):
  def testExpiration(self):
    cache = util.LRUCache(4)

    # Populate the cache
    self.assertEqual(cache.Get(1, lambda: 1), 1)
    self.assertEqual(cache.Get(2, lambda: 2), 2)
    self.assertEqual(cache.Get(3, lambda: 3), 3)
    self.assertEqual(cache.Get(4, lambda: 4), 4)

    # Access 2 and 1 to move them to the top (and see that they are not yet evicted, so the
    # factory function is ignored)
    self.assertEqual(cache.Get(2, lambda: None), 2)
    self.assertEqual(cache.Get(1, lambda: None), 1)

    # Add a fifth object and see #3 get evicted:
    self.assertEqual(cache.Get(5, lambda: 5), 5)
    self.assertEqual(cache.Get(3, lambda: None), None)


class ThrottleRateTestCase(unittest.TestCase):
  def testThrottle(self):
    util._TEST_TIME = time.time()

    # Null and empty cases.
    self.assertEqual(util.ThrottleRate(None, 1, 1), ({'count': 1, 'start_time': util._TEST_TIME}, False))
    self.assertEqual(util.ThrottleRate({}, 1, 1), ({'count': 1, 'start_time': util._TEST_TIME}, False))

    # Increment existing.
    self.assertEqual(util.ThrottleRate({'count': 1, 'start_time': util._TEST_TIME}, 2, 1),
                     ({'count': 2, 'start_time': util._TEST_TIME}, False))

    # Reset existing.
    self.assertEqual(util.ThrottleRate({'count': 10, 'start_time': util._TEST_TIME - 1}, 1, 1),
                     ({'count': 1, 'start_time': util._TEST_TIME}, False))

    # Exceed.
    self.assertEqual(util.ThrottleRate({}, 0, 1), ({'count': 0, 'start_time': util._TEST_TIME}, True))
    self.assertEqual(util.ThrottleRate({'count': 1, 'start_time': util._TEST_TIME}, 1, 1),
                     ({'count': 1, 'start_time': util._TEST_TIME}, True))
