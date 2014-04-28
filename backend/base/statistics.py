# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""
Functions to pretty print basic statistics and histograms.

Print basic statistics about a list of numbers:
>>> a = [1, 1, 2, 3, 4, 4]
>>> print statistics.FormatStats(a, percentiles=[90, 95, 99], indent=2)
  mean=2.50
  median=2.50
  stddev=1.26
  50/90/95/99 percentiles=[2.5, 4.0, 4.0, 4.0]

Pretty print a histogram
>>> a = [ 1, 1, 2, 3, 4, 4]
>>> print statistics.HistogramToASCII(a, bins=5, indent=2)
  [1-1) 2 33.33% ##############################################################
  [1-2) 1 16.67% ###############################
  [2-3) 1 16.67% ###############################
  [3-4] 2 33.33% ##############################################################
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

try:
  import numpy
except ImportError:
  numpy = None
import pprint
import string

def FormatStats(data, percentiles=None, indent=0):
  """ Compute basic stats for an array and return a string
  containing average, median, standard deviation and
  percentiles (if not None). indent specifies the number
  of leading spaces on each line.
  """
  if len(data) == 0: return ''
  leader = ' ' * indent
  out_str = leader + 'mean=%.2f' % numpy.mean(data)
  out_str += '\n' + leader + 'median=%.2f' % numpy.median(data)
  out_str += '\n' + leader + 'stddev=%.2f' % numpy.std(data)
  if percentiles:
    out_str += '\n' + leader + '/'.join(map(str, percentiles))
    out_str += ' percentiles=%s' % numpy.percentile(data, percentiles)
  return out_str

def HistogramToASCII(data, bins=10, line_width=80, indent=0):
  """ Compute the histogram for 'data' and generate its string
  representation. line_width is used to compute the maximum bar
  length. indent specifies the number of leading spaces on each line.
  """
  if len(data) == 0: return ''
  hist, buckets = numpy.histogram(data, bins=bins)
  percent_multiplier = float(100) / hist.sum()

  # buckets contains the bucket limits. it therefore has one more element
  # than hist. the last bin is closed. all others half-open.
  bin_edge_length = len(str(int(buckets[-1])))
  num_length = len(str(hist.max()))

  bar_max = line_width - indent - bin_edge_length * 2 - num_length
  # spaces, brackets, percentage, percent and dash. and one at the end.
  bar_max -= 13
  bar_divider = float(hist.max()) / bar_max

  # closing character for ranges. most are half-open: ')'
  closing_char = ')'
  out_str = ''
  for i in range(len(hist)):
    last = (i == len(hist) - 1)
    if last:
      # last bucket is closed.
      closing_char = ']'
    line_str = ' ' * indent
    # add bucket description with zfilled range limits to have equal string length.
    line_str += '[' + string.zfill(int(buckets[i]), bin_edge_length)
    line_str += '-' + string.zfill(int(buckets[i+1]), bin_edge_length) + closing_char
    # count of items in this bucket and percentage of total.
    line_str += ' ' + string.zfill(hist[i], num_length)
    line_str += ' ' + '%5.2f%%' % (hist[i] * percent_multiplier)
    # histogram bar, but only if we have room to display it.
    if bar_max > 0:
      line_str += ' ' + '#' * (hist[i] / bar_divider)

    out_str += line_str
    if not last:
      out_str += '\n'
  return out_str
