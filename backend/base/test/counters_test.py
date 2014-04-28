# Copyright 2012 Viewfinder Inc. All Rights Reserved.

""" Tests for the viewfinder counters module.
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import time
from viewfinder.backend.base import counters
import unittest


class CountersTest(unittest.TestCase):
  """Test for the various counter types, the CounterManager and Meter."""
  def testTotal(self):
    """Test for the Total counter type."""
    total = counters._TotalCounter('mytotal', 'Description')
    sampler = total.get_sampler()
    sampler2 = total.get_sampler()

    self.assertEqual(0, sampler())

    total.increment()
    self.assertEqual(1, sampler())

    total.increment(4)
    self.assertEqual(5, sampler())

    total.decrement()
    self.assertEqual(4, sampler())

    total.decrement(5)
    self.assertEqual(-1, sampler())
    self.assertEqual(-1, sampler2())

  def testDelta(self):
    """Test for the delta counter type."""
    delta = counters._DeltaCounter('mydelta', 'Description')
    sampler = delta.get_sampler()
    sampler2 = delta.get_sampler()

    self.assertEqual(0, sampler())

    delta.increment()
    self.assertEqual(1, sampler())

    delta.increment(4)
    self.assertEqual(4, sampler())

    delta.decrement()
    self.assertEqual(-1, sampler())

    delta.decrement(5)
    self.assertEqual(-5, sampler())
    self.assertEqual(-1, sampler2())

  def testAverage(self):
    avg = counters._AverageCounter('myaverage', 'Description')
    sampler = avg.get_sampler()
    sampler2 = avg.get_sampler()

    self.assertEqual(0, sampler())

    avg.add(5)
    avg.add(10)
    avg.add(15)
    self.assertEqual(10, sampler())

    avg.add(6)
    avg.add(12)
    avg.add(18)
    self.assertEqual(12, sampler())

    self.assertEqual(0, sampler())

    self.assertEqual(11, sampler2())

  def testRate(self):
    time_val = [0]
    def test_time():
      time_val[0] += 1
      return time_val[0]

    rate = counters._RateCounter('myrate', 'description', time_func=test_time)
    sampler = rate.get_sampler()
    sampler2 = rate.get_sampler()

    self.assertEqual(0, sampler())

    rate.increment(5)
    rate.increment(10)
    rate.increment(15)
    self.assertEqual(30, sampler())

    rate.increment(5)
    rate.increment(10)
    rate.increment(15)
    test_time()
    self.assertEqual(15, sampler())
    self.assertEqual(12, sampler2())

    rate = counters._RateCounter('myrate', 'description', 60, time_func=test_time)
    sampler = rate.get_sampler()
    self.assertEqual(0, sampler())

    rate.increment(5)
    rate.increment(10)
    rate.increment(15)
    self.assertEqual(1800, sampler())

    rate.increment(5)
    rate.increment(10)
    rate.increment(15)
    test_time()
    self.assertEqual(900, sampler())

  def testManagerAndMeter(self):
    manager = counters._CounterManager()
    total = counters._TotalCounter('test.mytotal', 'Example total counter')
    delta = counters._DeltaCounter('test.mydelta', 'Example delta counter')
    manager.register(total)
    manager.register(delta)

    # Test that counters are accessible from manager object via dot notation.
    self.assertIs(manager.test.mytotal, total)
    self.assertIs(manager.test.mydelta, delta)

    # Test for namespace errors when registering a counter with the manager.
    badcounter = counters._RateCounter('test', 'Bad namespace')
    with self.assertRaises(KeyError):
      manager.register(badcounter)

    badcounter = counters._RateCounter('test.mydelta.rate', 'Existing counter')
    with self.assertRaises(KeyError):
      manager.register(badcounter)

    # Test basic functionality of meter class in conjunction with a meter.
    meter = counters.Meter(manager.test)

    total.increment()
    total.increment(5)
    delta.increment(6)

    x = meter.sample()
    self.assertEqual(6, x.test.mytotal)
    self.assertEqual(6, x.test.mydelta)

    total.increment(5)
    delta.increment(6)
    x = meter.sample()
    self.assertEqual(11, x.test.mytotal)
    self.assertEqual(6, x.test.mydelta)

    # Test that namespace selection using a meter has the appropriate behavior.

    d = meter.describe()
    self.assertEqual(d.test.mytotal, 'Example total counter')

