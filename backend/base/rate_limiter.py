# Copyright 2013 Viewfinder Inc. All Rights Reserved.

""" Strict rate-limiter.
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import logging
import math
import time

from functools import partial
from tornado.ioloop import IOLoop
from viewfinder.backend.base import counters

class RateLimiter(object):
  """Rate limiter allowing no more than the specified qps.
  The rate limiter keeps a count of "available requests" that can be issued right away.
  Any time ComputeBackoffSecs is called, 'available' is incremented by the qps * time_spent_since_last_call.

  This method strictly enforces rate limiting using a sliding window.
  """

  def __init__(self, qps, unavailable_qps=0.0, qps_counter=None, backoff_counter=None):
    """QPS is the number of desired queries per second. 'unavailable_qps' will be subtracted from 'qps'.
    If 'qps_counter' is not None, it is incremented when Add() is called.
    If 'backoff_counter' is not None, it is incremented by the backoff time in seconds when ComputeBackoffSecs is called
    """
    self._qps = qps
    self._unavailable_qps = unavailable_qps
    self._qps_counter = qps_counter
    self._backoff_counter = backoff_counter

    self.available = self._qps - self._unavailable_qps
    self.last_time = time.time()

  def _GetQPS(self):
    """Return the actual rate-limit we want to use."""
    return self._qps - self._unavailable_qps

  def _Recompute(self):
    """Add qps * time_spent to available."""
    now = time.time()
    delta = now - self.last_time
    # Add the qps freed up since the last call.
    limit = self._GetQPS()
    self.available += limit * delta
    # Make sure the available ops left is in [-qps, +qps].
    # The upper end is throttling (don't exceed the max speed even if we haven't sent anything in > 1s).
    # The lower end is to ensure that unexpected "big ops" don't cause us to pause for too long (eg: we may allow
    # a Scan with 1 op left, but it may finish with > 1 consumed capacity units).
    self.available = max(-limit, min(limit, self.available))
    self.last_time = now

  def Add(self, requests):
    """Specify the number of requests issued. Can be negative if correcting for a previous Add()."""
    self.available -= requests
    if self._qps_counter is not None:
      self._qps_counter.increment(requests)

  def SetQPS(self, new_qps):
    """Specify a new value for QPS. No need to verify ceilings on 'available', ComputeBackoffSecs will do that."""
    self.available += (new_qps - self._qps)
    self._qps = new_qps

  def SetUnavailableQPS(self, new_unavailable_qps):
    """Specify a new value for unavailable QPS. No need to verify ceilings on 'available',
    ComputeBackoffSecs will do that.
    """
    self.available -= (new_unavailable_qps - self._unavailable_qps)
    self._unavailable_qps = new_unavailable_qps

  def ComputeBackoffSecs(self):
    """Return the number of backoff seconds needed to remain within the desired qps. This should be called only if
    the backoff will be done. To check whether backoff is needed without performing it, call NeedsBackoff.
    """
    self._Recompute()
    if self.available >= 0.0:
      # We should technically be checking against 1.0 (since this would mean one request available), but this would
      # cause us to send nothing at all when dealing with very small numbers.
      return 0.0
    else:
      # Time to sleep until we reach positive. |available| / (qps - unavailable)
      # The -1 is to reach "available=1.0". The only exception is when we're between 0-1. Otherwise, we need the
      # offset to reach the desired rate.
      backoff = min(1.0, math.fabs((self.available - 1.0) / self._GetQPS()))
      if self._backoff_counter is not None:
        self._backoff_counter.increment(backoff)
      return backoff

  def NeedsBackoff(self):
    """Returns whether or not we will need to backoff. This does not increment the backoff counter."""
    self._Recompute()
    return self.available < 0.0
