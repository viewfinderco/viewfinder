# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for Health Report system.
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import json
import time
from functools import partial

from base_test import DBBaseTestCase
from viewfinder.backend.base import counters, util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.metric import Metric, MetricInterval
from viewfinder.backend.db.health_report import HealthReport, HealthCriteria, TREND_SAMPLE_SIZE

class HealthReportTestClass(DBBaseTestCase):

  @async_test
  def testHealthReport(self):
    """Verify the health report generation and retrieval."""

    # Test constants
    cluster_name = 'test'
    interval = MetricInterval('testint', 60)
    group_key = Metric.EncodeGroupKey(cluster_name, interval)
    num_machines = 5
    num_samples = TREND_SAMPLE_SIZE + 1

    # Outer variables
    fake_time = 0
    def fake_time_func():
      return fake_time
    managers = []
    criteria_list = []
    criteria_called = [0, 0]

    # Test criteria #1
    def _deltaCriteria(totals, deltas):
      criteria_called[0] += 1
      alerts = []
      warnings = []
      if len(totals['machine_data'].keys()) != len(deltas['machine_data'].keys()):
        alerts.append('CLUSTER')

      warnings = [m for m, v in deltas['machine_data'].iteritems() if v > 3]
      return alerts, warnings

    # Test criteria #2
    def _rateCriteria(rates):
      criteria_called[1] += 1

      warnings = []
      for m, v in rates['machine_data'].iteritems():
        m_int = int(m[len('machine'):])
        if v == m_int / interval.length:
          warnings.append(m)

      return [], warnings

    def _OnGetReport(repeat, report):
      # Verify that the criteria were actually executed.
      for i in criteria_called:
        self.assertEqual(num_samples, i)

      # Verify that the criteria generated the expected warnings.
      self.assertEqual(len(report.alerts), num_machines)
      self.assertFalse('deltaCrit:CLUSTER' in report.alerts)

      for i in range(1, num_machines + 1):
        m_name = 'machine%d' % i
        self.assertTrue(('rateCrit:' + m_name) in report.warnings)
        self.assertTrue(('rateCrit:' + m_name) in report.alerts)

        if i > 3:
          self.assertTrue(('deltaCrit:' + m_name) in report.warnings)
        else:
          self.assertFalse(('deltaCrit:' + m_name) in report.warnings)

      if repeat:
        # Repeat the call to GetHealthReport to verify that criteria are only
        # run when the report is generated.
        HealthReport.GetHealthReport(self._client, cluster_name, interval, num_samples * interval.length,
                                     partial(_OnGetReport, False), managers[0], criteria_list)
      else:
        self.stop()


    def _OnMetricsUploaded():
      # Create a criteria list and request a health report based on those criteria.
      criteria_list.append(HealthCriteria('deltaCrit',
                                          'Description',
                                          _deltaCriteria,
                                          [managers[0].aggtest.total, managers[0].aggtest.delta],
                                          0))
      criteria_list.append(HealthCriteria('rateCrit',
                                          'Description',
                                          _rateCriteria,
                                          [managers[0].aggtest.rate],
                                          5))

      HealthReport.GetHealthReport(self._client, cluster_name, interval, num_samples * interval.length,
                                   partial(_OnGetReport, True), managers[0], criteria_list)



    with util.Barrier(_OnMetricsUploaded) as b:
      # Generate metrics.
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
          fake_time += interval.length
          sample = json.dumps(meter.sample())
          metric = Metric.Create(group_key, 'machine%d' % m, fake_time, sample)
          metric.Update(self._client, b.Callback())

  @async_test
  def testEmptyHealthReport(self):
    """Verify the health reports with no data are properly saved to the db.
    """

    # Test constants
    cluster_name = 'test'
    interval = MetricInterval('testint', 60)
    group_key = Metric.EncodeGroupKey(cluster_name, interval)
    num_machines = 5
    num_samples = TREND_SAMPLE_SIZE + 1

    # Outer variables
    managers = []
    criteria_list = []
    criteria_called = [0]

    # Test criteria #1
    def _blankCriteria():
      criteria_called[0] += 1
      return [], []

    def _OnDirectQuery(reports):
      self.assertEqual(len(reports), num_samples)
      self.stop()

    def _OnGetReport(report):
      # Verify that the criteria were actually executed.
      for i in criteria_called:
        self.assertEqual(num_samples, i)

      # Verify that the criteria generated the expected warnings.
      self.assertEqual(len(report.alerts), 0)
      self.assertEqual(len(report.warnings), 0)
      HealthReport.QueryTimespan(self._client, group_key, interval.length, interval.length * num_samples,
                                 _OnDirectQuery)


    def _OnMetricsUploaded():
      # Create a criteria list and request a health report based on those criteria.
      criteria_list.append(HealthCriteria('blankCrit',
                                          'Description',
                                          _blankCriteria,
                                          [],
                                          0))

      HealthReport.GetHealthReport(self._client, cluster_name, interval, num_samples * interval.length,
                                   _OnGetReport, managers[0], criteria_list)


    with util.Barrier(_OnMetricsUploaded) as b:
      # Generate metrics.
      for m in range(1, num_machines + 1):
        cm = counters._CounterManager()
        cm.register(counters._TotalCounter('aggtest.total', 'Test Total'))

        fake_time = 0
        meter = counters.Meter(cm)
        managers.append(cm)
        for s in range(num_samples):
          fake_time += interval.length
          sample = json.dumps(meter.sample())
          metric = Metric.Create(group_key, 'machine%d' % m, fake_time, sample)
          metric.Update(self._client, b.Callback())
