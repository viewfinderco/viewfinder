# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Statistics tests.
"""

__authors__ = ['marc@emailscrubbed.com (Marc Berhault)']

import logging
try:
  import numpy
except ImportError:
  numpy = None
import random
import unittest

from viewfinder.backend.base import statistics, testing

@unittest.skipIf(numpy is None, 'numpy not present')
class FormatStatsTestCase(testing.BaseTestCase):
  def _RandomList(self):
    """ List of random integers (0-20) and of random size (10-20). """
    l = []
    for i in range(random.randint(10, 20)):
      l.append(random.randint(0, 20))
    print 'list: %r' % l
    return l

  def testEmpty(self):
    self.assertEqual(statistics.FormatStats([]), '')

  def testSimple(self):
    """ No indentation, no percentiles. """
    a = self._RandomList()
    out_str = 'mean=%.2f\nmedian=%.2f\nstddev=%.2f' % \
              (numpy.mean(a), numpy.median(a), numpy.std(a))
    self.assertEqual(statistics.FormatStats(a), out_str)

  def testIndent(self):
    """ With indentation, no percentiles. """
    a = self._RandomList()
    out_str = '   mean=%.2f\n   median=%.2f\n   stddev=%.2f' % \
              (numpy.mean(a), numpy.median(a), numpy.std(a))
    self.assertEqual(statistics.FormatStats(a, indent=3), out_str)

  def testPercentile(self):
    """ With indentation and percentiles. """
    a = self._RandomList()
    p = [80, 90, 95, 99]
    out_str = '   mean=%.2f\n   median=%.2f\n   stddev=%.2f\n' % \
              (numpy.mean(a), numpy.median(a), numpy.std(a))
    out_str += '   80/90/95/99 percentiles=%s' % numpy.percentile(a, p)
    self.assertEqual(statistics.FormatStats(a, percentiles=p, indent=3), out_str)

@unittest.skipIf(numpy is None, 'numpy not present')
class HistogramTestCase(testing.BaseTestCase):
  def testEmpty(self):
    self.assertEqual(statistics.HistogramToASCII([]), '')

  def testSimple(self):
    a = [1, 1, 2, 4, 4]
    out_str = '  [1-2) 2 40.00% ########\n'
    out_str += '  [2-3) 1 20.00% ####\n'
    out_str += '  [3-4] 2 40.00% ########'
    self.assertEqual(statistics.HistogramToASCII(a, bins=3, indent=2, line_width=26), out_str)

  def testRounding(self):
    """ Bucket limits can be floats, but we round everything for display. """
    a = [1, 1, 2, 4, 4]
    out_str = '  [1-1) 2 40.00% ########\n'
    out_str += '  [1-2) 1 20.00% ####\n'
    out_str += '  [2-2) 0  0.00% \n'
    out_str += '  [2-3) 0  0.00% \n'
    out_str += '  [3-4] 2 40.00% ########'
    self.assertEqual(statistics.HistogramToASCII(a, bins=5, indent=2, line_width=26), out_str)
