# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test case for performance counters related to the service frontend.
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import time

from viewfinder.backend.base import util, counters
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.www.test import service_base_test


class ServiceCountersTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(ServiceCountersTestCase, self).setUp()
    self.meter = counters.Meter(counters.counters.viewfinder.service)
    self.meter_start = time.time()

  def _CheckCounters(self, expected_requests, expected_failures):
    sample = self.meter.sample()
    elapsed = time.time() - self.meter_start

    # High deltas because of very small denominators.
    self.assertAlmostEqual(sample.viewfinder.service.req_per_min, (expected_requests / elapsed) * 60, delta=100.0)
    self.assertAlmostEqual(sample.viewfinder.service.fail_per_min, (expected_failures / elapsed) * 60, delta=100.0)
    self.meter_start += elapsed

  def testServiceCounters(self):
    """Verify the requests per second and failures per second performance counters."""
    self._CheckCounters(0, 0)
    for i in range(5):
      self._SendRequest('query_notifications', self._cookie, {})
      self.assertRaisesHttpError(400, self._SendRequest, 'query_notifications', self._cookie, {'start_key': 2})

    self._CheckCounters(10, 5)
    self._CheckCounters(0, 0)
