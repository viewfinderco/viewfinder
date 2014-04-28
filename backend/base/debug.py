# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Debug utilities.

http://www.smira.ru/wp-content/uploads/2011/08/heapy.html

 - HeapDebugger: class that runs periodic guppy heap analysis
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
from functools import partial
from tornado import ioloop, options

options.define('profile_interval', default=None, help='seconds between heap profiles')

_can_use_guppy = False
try:
  from guppy import hpy
  _can_use_guppy = True
except:
  logging.warning('unable to import guppy module for heap analysis')


class HeapDebugger(object):
  """If guppy can be imported, creates a periodic
  """
  def __init__(self):
    if options.options.profile_interval:
      hp = self.StartProfiling()
      interval_ms = int(options.options.profile_interval) * 1000
      self._periodic_cb = ioloop.PeriodicCallback(
        partial(self._PeriodicDump, hp), interval_ms, ioloop.IOLoop.current())
      self._periodic_cb.start()

  def StartProfiling(self):
    """Creates a new heapy object, sets it to begin profiling, and returns to caller.
    """
    hp = hpy()
    hp.setrelheap()
    return hp

  def StopProfiling(self, hp):
    """Returns the heap object for further examination."""
    try:
      return hp.heap()
    finally:
      del hp

  def _PeriodicDump(self, hp):
    """Called from a periodic timer to dump (hopefully) useful information
    about the heap to the logs.
    """
    logging.info('in periodic dump')
    heap = self.StopProfiling(hp)
    logging.info('By class or dict owner:\n%s' % heap.byclodo)
    logging.info('By referrers:\n%s' % heap.byrcs)
    logging.info('By type:\n%s' % heap.bytype)
    logging.info('By via:\n%s' % heap.byvia)
    del heap
