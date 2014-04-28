# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder health report.  A report represents a guess at the overall health
of the server at a given time.
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import logging
import math
import time
from collections import namedtuple
from functools import partial

from viewfinder.backend.base import util
from viewfinder.backend.base.exceptions import DBConditionalCheckFailedError
from viewfinder.backend.base.counters import counters
from viewfinder.backend.db import db_client, vf_schema, metric
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.range_base import DBRangeObject
from viewfinder.backend.op import user_op_manager


# Because alerts and warnings are a flat list, this token is used to indicate that an alert
# or warning applies to the entire cluster rather than a single machine.
CLUSTER_TOKEN = 'CLUSTER'


# Number of previous reports to consider when looking for trends in performance counters.
# Certain warnings may be escalated to alerts if they occur too often.
TREND_SAMPLE_SIZE = 9


def ErrorCriteria(errors):
  """Monitor the number of unexpected errors logged in the cluster.  If more than five
  errors have occurred on the cluster during this time period, post an alert. Posts a
  warning if between one and four errors have occurred.
  """
  ERROR_ALERT_THRESHOLD = 5
  alerts = []
  warnings = []

  if errors['cluster_total'] > ERROR_ALERT_THRESHOLD:
    alerts.append(CLUSTER_TOKEN)
  elif errors['cluster_total'] > 0:
    warnings.append(CLUSTER_TOKEN)

  return alerts, warnings


def RequestsFailedCriteria(request_rate, failed_rate):
  """Monitor the rate of failed service requests on the server.  The number of failed
  requests will be compared to the total number of requests to determine if a warning
  is warranted, either for the cluster or for any individual machine.
  """
  alerts = []
  warnings = []

  def _ComputeThreshold(x):
    # Failure threshold is defined as the square root of the total request rate.  This gives
    # an appropriate threshold for both very low and very high numbers.  For example, the
    # threshold is approximately 30% of requests for 10 total requests, 10% for 100 and 
    # 3% for 1000.
    return math.ceil(math.sqrt(x))

  if failed_rate['cluster_total'] > _ComputeThreshold(request_rate['cluster_total']):
    warnings.append(CLUSTER_TOKEN)

  for m, v in request_rate['machine_data'].iteritems():
    if failed_rate['machine_data'][m] > _ComputeThreshold(v):
      warnings.append(m)

  return alerts, warnings


def OperationRetriesCriteria(operation_rate, retry_rate):
  """Monitor the rate of operation retries on the server.  The number of operation retries
  will be compared to the total number of operations run.
  """
  alerts = []
  warnings = []

  def _ComputeThreshold(x):
    # Failure threshold is defined as one-third of the square root of the total request rate.  
    # This gives an appropriate threshold for both very low and very high numbers.  For example, 
    # the threshold is approximately 10% of requests for 10 total requests, 3% for 100 and 
    # 1% for 1000.
    return math.ceil(math.sqrt(x)) / 3

  if retry_rate['cluster_total'] > _ComputeThreshold(operation_rate['cluster_total']):
    warnings.append(CLUSTER_TOKEN)

  for m, v in operation_rate['machine_data'].iteritems():
    if retry_rate['machine_data'][m] > _ComputeThreshold(v):
      warnings.append(m)

  return alerts, warnings


def MissingMetricsCriteria():
  """This criteria is alerted if metrics data is completely missing at a timestamp.
  This is a special criteria in that warnings are generated directly in the GetHealthReport
  method, rather than in this criteria.
  """
  return [], []


class HealthCriteria(object):
  """Class which encapsulates a single health criteria for a report.  Each criteria
  checks a set of counters at the report timestamp, returning a list of alerts and
  warnings based on the timestamp.  A criteria can also evaluate trends over the last
  several health reports, which may result in a warning escalating to an alert.

  'alert_description' is a description of the condition which would result in this criteria
  raising an alert.

  'counter_list' is a list of counters which the criteria needs to operate on.  The values
  for each counter at the report timestamp will be passed to the handler as parameters
  in the order requested.

  'handler' is a method which accepts the requested counter data and returns a list of
  machines for which the criteria should alert, and a second list of machines for which
  the criteria should warn.

  Finally, 'escalation_threshold' is an optional value which is used to escalate warnings
  to alerts based on the value of previous reports.  If the threshold is non-zero and
  a warning has been present in a number of previous reports exceeding the threshold,
  then the warning is escalated to an alert.
  """
  def __init__(self, criteria_name, alert_description, handler, counter_list, escalation_threshold=0):
    self.name = criteria_name
    self.description = alert_description
    self.counter_list = counter_list
    self.handler = handler
    self.escalation_threshold = escalation_threshold

  def InspectMetrics(self, metric_data, report):
    """Passes the requested counter data for this criteria to the handler, and adds
    the returned set of warnings and alerts to the report.
    """
    alerts, warnings = self.handler(*[metric_data[c.name] for c in self.counter_list])
    for w in warnings:
      report.warnings.add(self.name + ':' + w)
    for a in alerts:
      report.alerts.add(self.name + ':' + a)

  def InspectTrends(self, old_reports, new_report):
    """If an escalation threshold is set for this criteria, inspects previous reports
    and escalates warnings to alerts if they are present in a number of previous reports
    exceeding the threshold.
    """
    if self.escalation_threshold == 0:
      return

    current_warnings = [w for w in new_report.warnings.combine() if w.startswith(self.name + ':')]
    for w in current_warnings:
      if len([r for r in old_reports if w in r.warnings]) > self.escalation_threshold:
        new_report.alerts.add(w)

  @classmethod
  def GetCriteriaList(cls):
    """Gets the list of criteria for server health checks.  This is implemented as a class
    method to ensure that the static counters variable is completely loaded before accessing
    it, rather than depending on python module loading order.
    """

    if hasattr(cls, '_criteria_list'):
      return cls._criteria_list

    cls._criteria_list = [
      HealthCriteria('Errors',
                     'Error threshold exceeded.',
                     ErrorCriteria,
                     [counters.viewfinder.errors.error],
                     5),
      HealthCriteria('ReqFail',
                     'Failed Request threshold exceeded.',
                     RequestsFailedCriteria,
                     [counters.viewfinder.service.req_per_min, counters.viewfinder.service.fail_per_min],
                     5),
      HealthCriteria('OpRetries',
                     'Operation retry threshold exceeded.',
                     OperationRetriesCriteria,
                     [counters.viewfinder.operation.ops_per_min, counters.viewfinder.operation.retries_per_min],
                     5),
      HealthCriteria('MissingMetrics',
                     'Metrics collection failed.',
                     MissingMetricsCriteria,
                     [],
                     3),
      ]
    return cls._criteria_list


@DBObject.map_table_attributes
class HealthReport(DBRangeObject):
  """Class which describes the overall health of a metrics group at a given timestamp.  Health
  is determined based on the aggregated performance counters of the metrics group over a
  period of time.

  A health report record is designed to be sparse if the group is healthy - only a list
  of warnings and alerts is stored.  If the cluster is completely healthy according to
  the configured criteria, then the record will essentially be empty.
  """
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.HEALTH_REPORT)

  def __init__(self, group_key=None, timestamp=None):
    super(HealthReport, self).__init__()
    self.group_key = group_key
    self.timestamp = timestamp

  @classmethod
  def QueryTimespan(cls, client, group_key, start_time, end_time, callback, excl_start_key=None):
    """ Performs a range query on the HealthReport table for the given group_key between
    the given start and end time.  An optional start key can be specified to resume
    an earlier query which did not retrieve the full result set.
    """
    HealthReport.RangeQuery(client, group_key, db_client.RangeOperator([start_time, end_time], 'BETWEEN'),
                            None, None, callback=callback, excl_start_key=excl_start_key)

  @classmethod
  def GetHealthReport(cls, client, cluster_name, interval, timestamp, callback, counter_set=None, criteria=None):
    """ Get a cluster health report for the given cluster and collection interval at the
    given timestamp. The report will be generated if it is not already available in the database.
    The given callback will be invoked with the report once it is retrieved or generated.

    A specific counter set can be provided if desired; by default, all counters registered globally
    with the counters module will be used.

    The optional criteria parameter is intended for testing, but can be used to provide an optional
    list of HealthCriteria objects used to generate the report.  By default, the list provided by
    HealthCriteria.GetCriteriaList() will be used.
    """
    criteria = criteria or HealthCriteria.GetCriteriaList()
    counter_set = counter_set or counters
    group_key = metric.Metric.EncodeGroupKey(cluster_name, interval)

    # Calculate points in time relevant to this report.
    newest_report_timestamp = timestamp - (timestamp % interval.length)
    oldest_report_timestamp = newest_report_timestamp - (interval.length * TREND_SAMPLE_SIZE)

    def _OnCreateReport(old_reports, new_report):
      _OnQueryPreviousReports(old_reports + [new_report])

    def _OnFailCreateReport(type_, value_, traceback_):
      if type_ is DBConditionalCheckFailedError:
        # Another machine has already generated the new report, restart at _OnQueryReport.
        _OnQueryReport(None)
      else:
        raise type_, value_, traceback_

    def _OnAggregate(timestamp, reports, metrics):
      new_report = HealthReport.CreateFromKeywords(group_key=group_key, timestamp=timestamp)

      if len(metrics.timestamps) == 0:
        # No metrics collected for this period.  Only the missing metrics criteria
        # can be evaluated in this case.
        new_report.warnings.add('MissingMetrics:' + CLUSTER_TOKEN)
        for c in criteria:
          c.InspectTrends(reports, new_report)
      else:
        # Pivot metrics data to time.
        time_pivot = {counter: {'cluster_total': data.cluster_total[0][1],
                                'cluster_avg': data.cluster_avg[0][1],
                                'machine_data': {k : v[0][1] for k, v in data.machine_data.iteritems()},
                                } for counter, data in metrics.counter_data.iteritems()
                      }

        for c in criteria:
          c.InspectMetrics(time_pivot, new_report)
          c.InspectTrends(reports, new_report)

      success_cb = partial(_OnCreateReport, reports, new_report)
      with util.Barrier(success_cb, _OnFailCreateReport) as b:
        new_report.Update(client, b.Callback(), replace=False)

    def _OnQueryPreviousReports(reports):
      if (len(reports) == TREND_SAMPLE_SIZE + 1):
        # The report for the requested timestamp is now available.
        callback(reports[-1])
        return

      # Generate the first missing report chronologically.
      next_timestamp = (reports[-1].timestamp + interval.length) if len(reports) > 0 else oldest_report_timestamp
      metric.AggregatedMetric.CreateAggregateForTimespan(client, group_key, next_timestamp, next_timestamp,
                                                         counter_set, partial(_OnAggregate, next_timestamp, reports))

    def _OnQueryReport(report):
      if report is not None:
        callback(report)
        return

      # If the requested report doesn't already exist, it should be generated from metrics and previous reports.
      HealthReport.QueryTimespan(client, group_key, oldest_report_timestamp, newest_report_timestamp,
                                 _OnQueryPreviousReports)

    # Retrieve the report for the most recent time if it is not cached.
    HealthReport.Query(client, group_key, newest_report_timestamp, None, _OnQueryReport, must_exist=False)
