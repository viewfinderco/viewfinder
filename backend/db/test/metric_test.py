# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for Metric upload process.
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import json
import time

from base_test import DBBaseTestCase
from functools import partial
from tornado.ioloop import IOLoop
from viewfinder.backend.base import counters, util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.metric import Metric, AggregatedMetric, MetricInterval

class MetricsTestCase(DBBaseTestCase):
  @async_test
  def testMetricsUploadTimer(self):
    """Test the periodic metric upload system."""
    def _OnQueryMetric(min_metrics, max_metrics, metrics):
      self.assertTrue(len(metrics) >= min_metrics and len(metrics) <= max_metrics,
                      '%d not in [%d-%d]' % (len(metrics), min_metrics, max_metrics))
      for m in metrics:
        self.assertTrue(m.timestamp % 3 == 0)
      payload = DotDict(json.loads(metrics[0].payload))
      keys = counters.counters.flatten().keys()
      for k in keys:
        self.assertTrue(k in payload, 'Payload did not contain record for counter %s' % k)
      self.stop()

    start_time = time.time()
    cluster_name = 'test_group_key'
    interval = MetricInterval('test_interval', 3)
    group_key = Metric.EncodeGroupKey(cluster_name, interval)
    rate = counters.define_rate('metricstest.rate', 'Test rate')

    Metric.StartMetricUpload(self._client, cluster_name, interval)
    IOLoop.current().add_timeout(start_time + 7, self.stop)
    rate.increment()
    self.wait(timeout=10)
    end_time = time.time()

    Metric.StopMetricUpload(group_key)
    Metric.QueryTimespan(self._client, group_key, start_time, end_time, partial(_OnQueryMetric, 2, 3))
    Metric.QueryTimespan(self._client, group_key, start_time + 4, end_time, partial(_OnQueryMetric, 1, 2))
    Metric.QueryTimespan(self._client, group_key, start_time, end_time - 4, partial(_OnQueryMetric, 1, 2))
    Metric.QueryTimespan(self._client, group_key, None, end_time, partial(_OnQueryMetric, 2, 3))
    Metric.QueryTimespan(self._client, group_key, start_time, None, partial(_OnQueryMetric, 2, 3))

    # Setting both start_time and end_time to None fails.
    self.assertRaises(AssertionError,
                      Metric.QueryTimespan, self._client, group_key, None, None, partial(_OnQueryMetric, 2, 3))

  @async_test
  def testMetricsAggregator(self):
    """Test metrics aggregation with data from multiple machines"""
    num_machines = 5
    num_samples = 15
    sample_duration = 60.0
    group_key = 'agg_test_group_key'
    fake_time = 0
    managers = []

    def fake_time_func():
      return fake_time

    def _OnAggregation(aggregator):
      base_sum = sum(range(1, num_machines + 1))
      base_avg = base_sum / num_machines

      agg_total = aggregator.counter_data['aggtest.total']
      agg_delta = aggregator.counter_data['aggtest.delta']
      agg_rate = aggregator.counter_data['aggtest.rate']
      agg_avg = aggregator.counter_data['aggtest.avg']
      for s in range(num_samples):
        # Check timestamp values
        for cd in aggregator.counter_data.itervalues():
          self.assertEqual(cd.cluster_total[s][0], sample_duration * (s + 1))
          self.assertEqual(cd.cluster_avg[s][0], sample_duration * (s + 1))

        # Check aggregate total
        self.assertEqual(agg_total.cluster_total[s][1], base_sum * (s + 1))
        self.assertEqual(agg_total.cluster_avg[s][1], base_avg * (s + 1))

        # Check aggregate delta
        self.assertEqual(agg_delta.cluster_total[s][1], base_sum)
        self.assertEqual(agg_delta.cluster_avg[s][1], base_avg)

        # Check aggregate rate
        self.assertEqual(agg_rate.cluster_total[s][1], base_sum / sample_duration)
        self.assertEqual(agg_rate.cluster_avg[s][1], base_avg / sample_duration)

        # Check aggregate avg
        self.assertEqual(agg_avg.cluster_total[s][1], base_sum)
        self.assertEqual(agg_avg.cluster_avg[s][1], base_avg)

        for m in range(1, num_machines + 1):
          machine_name = 'machine%d' % m

          # Check per-machine total
          mtotal = agg_total.machine_data[machine_name]
          self.assertEqual(mtotal[s][1], m * (s + 1))

          # Check per-machine delta
          mdelta = agg_delta.machine_data[machine_name]
          self.assertEqual(mdelta[s][1], m)

          # Check per-machine rate
          mrate = agg_rate.machine_data[machine_name]
          self.assertEqual(mrate[s][1], m / sample_duration)

          # Check per-machine avg
          mavg = agg_avg.machine_data[machine_name]
          self.assertEqual(mavg[s][1], m)

      self.stop()


    def _OnMetricsUploaded():
      AggregatedMetric.CreateAggregateForTimespan(self._client, group_key, 0, sample_duration * num_samples,
                                                  managers[0], _OnAggregation)

    with util.Barrier(_OnMetricsUploaded) as b:
      for m in range(1, num_machines + 1):
        cm = counters._CounterManager()
        cm.register(counters._TotalCounter('aggtest.total', 'Test Total'))
        cm.register(counters._DeltaCounter('aggtest.delta', 'Test Delta'))
        cm.register(counters._RateCounter('aggtest.rate', 'Test Rate', time_func=fake_time_func))
        cm.register(counters._AverageCounter('aggtest.avg', 'Test Average'))

        fake_time = 0
        meter = counters.Meter(cm)
        managers.append(cm)
        for s in range(num_samples):
          cm.aggtest.total.increment(m)
          cm.aggtest.delta.increment(m)
          cm.aggtest.rate.increment(m)
          cm.aggtest.avg.add(m)
          cm.aggtest.avg.add(m)
          fake_time += sample_duration
          sample = json.dumps(meter.sample())
          metric = Metric.Create(group_key, 'machine%d' % m, fake_time, sample)
          metric.Update(self._client, b.Callback())
