# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder performance metrics.  Metrics are captured from a machine
using the counters module, serialized, and stored using this table.
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import json
import logging
import time
import platform
from collections import namedtuple
from functools import partial

from tornado.ioloop import IOLoop
from viewfinder.backend.base import util, counters, retry
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import db_client, vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.range_base import DBRangeObject


# Default clustering key for metrics.  The cluster name is used in combination with
# additional information to create a group key for metrics.  Use of this variable
# should be considered temporary until a more comprehensive deployment model is
# developed.
DEFAULT_CLUSTER_NAME = 'us-east-1'

# Group name for daily logs analysis output.
LOGS_STATS_NAME = 'logs'

# Group name for metrics written by periodic jobs (dbchk, logs merge, logs analysis).
JOBS_STATS_NAME = 'jobs'

# A metric interval is a combination of a name and a length of time in seconds.
# The name is intended for use as part of the group_key when creating metric
# object.
MetricInterval = namedtuple('MetricInterval', ['name', 'length'])


# Configured metric collection intervals.  Each interval is a tuple (name, frequency) where frequency is
# specified in seconds.  If additional intervals are added, this list should be maintained in ascending
# order by interval length.
METRIC_INTERVALS = [MetricInterval('detail', 30), MetricInterval('hourly', 3600)]
LOGS_INTERVALS = [MetricInterval('daily', 86400)]
JOBS_INTERVALS = [MetricInterval('daily', 86400)]

def GetMachineKey():
  """Gets the machine key to be used for Metrics uploaded from this process."""
  return platform.node()


class MetricUploadRetryPolicy(retry.RetryPolicy):
  """Retry policy for uploading Metrics to the server."""
  def __init__(self, max_tries=3, timeout=30, min_delay=.5, max_delay=5):
    retry.RetryPolicy.__init__(self, max_tries=max_tries, timeout=timeout,
                               min_delay=min_delay, max_delay=max_delay,
                               check_result=None, check_exception=self._ShouldRetry)

  def _ShouldRetry(self, type_, value_, traceback):
    """Stub retry method, indicating that all exceptions should result in a retry."""
    return True


@DBObject.map_table_attributes
class Metric(DBRangeObject):
  """Viewfinder metric data object.  A Metric object represents the collected performance
  counters from one Viewfinder server instance at a specific point in time.  The metric
  is additionally associated with a group key, which helps to organize metrics collected
  from several different machines into a more natural group for querying.
  """
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.METRIC)
  _timeouts = dict()

  def __init__(self, group_key=None, sort_key=None):
    """Initialize a new Metric object."""
    super(Metric, self).__init__()
    self.group_key = group_key
    self.sort_key = sort_key

  @classmethod
  def QueryTimespan(cls, client, group_key, start_time, end_time, callback, excl_start_key=None):
    """Performs a range query on the metrics table for the given group_key the given start and
    end time.  An optional start key can be specified to resume an earlier query which did not
    retrieve the full result set.
    Either start_time or end_time may be None, but not both.
    """
    # Query from start_time to end_time + 1 - because they contain a machine id, actual
    # sort keys will always follow a key comprised only of a timestamp.
    assert start_time is not None or end_time is not None, 'must specify at least one of start_time and end_time'
    operator = None
    start_rk = util.CreateSortKeyPrefix(start_time, randomness=False) if start_time is not None else None
    end_rk = util.CreateSortKeyPrefix(end_time + 1, randomness=False) if end_time is not None else None
    if start_time is None:
      operator = db_client.RangeOperator([end_rk], 'LE')
    elif end_time is None:
      operator = db_client.RangeOperator([start_rk], 'GE')
    else:
      operator = db_client.RangeOperator([start_rk, end_rk], 'BETWEEN')
    Metric.RangeQuery(client, group_key, operator, None, None,
                      callback=callback, excl_start_key=excl_start_key)

  @classmethod
  def Create(cls, group_key, machine_id, timestamp, payload):
    """Create a new metric object with the given attributes.  The sort key is
    computed automatically from the timestamp and machine id.
    """
    sort_key = util.CreateSortKeyPrefix(timestamp, randomness=False) + machine_id
    metric = Metric(group_key, sort_key)
    metric.machine_id = machine_id
    metric.timestamp = timestamp
    metric.payload = payload
    return metric

  @classmethod
  def StartMetricUpload(cls, client, cluster_name, interval):
    """Starts an asynchronous loop which periodically samples performance counters and saves
    their values to the database.  The interval parameter is a MetricInterval object which
    specifies the frequency of upload in seconds.
    """
    retry_policy = MetricUploadRetryPolicy()
    machine_id = GetMachineKey()
    meter = counters.Meter(counters.counters)
    group_key = cls.EncodeGroupKey(cluster_name, interval)
    frequency_seconds = interval.length

    def _UploadError(type_, value_, traceback):
      logging.getLogger().error('Unable to upload metrics payload for group: %s' % group_key)

    def _UploadSuccess():
      logging.getLogger().debug('Uploaded metrics payload for group: %s' % group_key)

    def _SnapMetrics(deadline):
      """ Method which takes a single sample of performance counters and attempts
      to upload the data to the database.  This method automatically schedules itself
      again on the current IOLoop.
      """
      next_deadline = deadline + frequency_seconds
      callback = partial(_SnapMetrics, next_deadline)
      cls._timeouts[group_key] = IOLoop.current().add_timeout(next_deadline, callback)

      sample = meter.sample()
      sample_json = json.dumps(sample)
      new_metric = Metric.Create(group_key, machine_id, deadline, sample_json)
      with util.Barrier(_UploadSuccess, _UploadError) as b:
        retry.CallWithRetryAsync(retry_policy, new_metric.Update, client=client, callback=b.Callback())

    # Initial deadline should fall exactly on an even multiple of frequency_seconds.
    initial_deadline = time.time() + frequency_seconds
    initial_deadline -= initial_deadline % frequency_seconds
    callback = partial(_SnapMetrics, initial_deadline)

    cls.StopMetricUpload(group_key)
    cls._timeouts[group_key] = IOLoop.current().add_timeout(initial_deadline, callback)

  @classmethod
  def StopMetricUpload(cls, group_key):
    """Stops the metrics upload process if it has already been started.  This method is idempotent."""
    if cls._timeouts.get(group_key, None) is not None:
      IOLoop.current().remove_timeout(cls._timeouts[group_key])
      cls._timeouts[group_key] = None

  @classmethod
  def EncodeGroupKey(cls, cluster_name, interval):
    """Encodes a group key for the Metric table.  A group key is a combination of a machine cluster
    name and a collection interval name.
    """
    return cluster_name + '.' + interval.name

  @classmethod
  def DecodeGroupKey(cls, group_key):
    """Attempts to decode a metrics group key.  Returns the machine cluster name and metric
    interval used to encode the group.
    """
    index = group_key.find('.')
    assert index != -1
    cluster = group_key[:index]
    interval = group_key[index + 1:]
    return cluster, cls.FindIntervalForCluster(cluster, interval)

  @classmethod
  def FindIntervalForCluster(cls, cluster, interval):
    """Look for and return 'interval' for 'cluster'. Returns None if not found."""
    intervals = []

    if cluster == DEFAULT_CLUSTER_NAME:
      intervals = METRIC_INTERVALS
    elif cluster == LOGS_STATS_NAME:
      intervals = LOGS_INTERVALS
    elif cluster == JOBS_STATS_NAME:
      intervals = JOBS_INTERVALS
    for i in intervals:
      if i.name == interval:
        return i
    return None


class AggregatedMetric(object):
  """This is a utility class intended to average multiple samples from a set of several counters
  taken over multiple machines.  The class is initialized with a start and end time, along with
  a set of counters (specified as a subset of counters.counters or another counter collection.)
  AggregatedMetric will maintain an internal AggregatedCounter object for each counter specified
  in its target counter set.

  Metric objects loaded from the database are added to the metric sequentially - metrics MUST be
  added in chronological order by timestamp.  The component counter values within each metric sample
  will be added to the AggregatedCounter objects.  After aggregation, the AggregatedCounter objects
  are available from the counter_data member, which is a dictionary keyed by counter name.

  This class is not intended to be instantiated directly - rather, it should be created using
  the CreateAggregateForTimespan class method, which automatically handles the details
  of querying the backend and aggregating metrics in an efficient way.
  """
  class AggregatedCounter(object):
    """A utility class used to aggregate data from multiple samples of a single counter, which
    may be taken over multiple machines.  An AggregatedCounter is initialized by passing it
    a counter object - individual samples of the counter should then be added using the AddSample
    methods.  Samples MUST be added in chronological order by timestamp.

    After samples are added, the following data points are available from this object:

    .machine_data: A dictionary containing the samples collected from each individual machine.
                   Each member of the dictionary is a list of [timestamp, value] data points.
    .cluster_total: A list of [timestamp, value] data points.  Each value is the sum of all sample
                    values for all machines with the same timestamp.
    .cluster_avg:   An aggregated list like cluster_total, but provides the average value across
                    all machines rather than a sum.

    The 'is_average' property indicates if this counter's units are an average with a non-time base,
    and thus implies that the units of cluster_total will not be analogous to the units of cluster_total.
    An example of this would be a counter for the average time per request - this should be averaged
    across machines, rather than totaled, because the base of the average is specific to each machine.
    """
    def __init__(self, counter):
      self.name = counter.name
      self.description = counter.description
      self.is_average = isinstance(counter, counters._AverageCounter)
      self.machine_data = dict()
      self.cluster_total = list()
      self.cluster_avg = list()

    def AddSample(self, machine, timestamp, value):
      """Adds a single sample to the aggregation."""
      self.machine_data.setdefault(machine, list()).append([timestamp, value])
      if len(self.cluster_total) == 0 or timestamp > self.cluster_total[-1][0]:
        self.cluster_total.append([timestamp, 0])
        self.cluster_avg.append([timestamp, 0])
      self.cluster_total[-1][1] += value
      self.cluster_avg[-1][1] = self.cluster_total[-1][1] / float(len(self.machine_data))


  def __init__(self, group_key, start_time, end_time, counter_set):
    self.start_time = start_time
    self.end_time = end_time
    self.group_key = group_key
    self.machines = set()
    self.timestamps = set()
    self.counter_data = dict()
    for c in counter_set.flatten().itervalues():
      self.counter_data[c.name] = self.AggregatedCounter(c)

  def _AddMetric(self, metric):
    """Adds a single metric sample to the aggregation.  Metric samples must be added in
    chronological order.
    """
    machine = metric.machine_id
    time = metric.timestamp
    payload = DotDict(json.loads(metric.payload)).flatten()

    self.machines.add(machine)
    self.timestamps.add(time)
    for k in payload:
      if k not in self.counter_data:
        continue
      val = payload.get(k, None)
      if val is not None:
        self.counter_data[k].AddSample(machine, time, val)

  @classmethod
  def CreateAggregateForTimespan(cls, client, group_key, start_time, end_time, counter_set, callback):
    """Creates an Aggregated Metric and for a set of counters and queries the database,
    aggregating all metrics for the given cluster and interval across the given time span.
    Invokes the given callback with the resulting AggregatedMetric object after the query is
    completed.
    """
    aggregator = AggregatedMetric(group_key, start_time, end_time, counter_set)

    def _OnQueryPartial(metrics):
      if len(metrics) > 0:
        Metric.QueryTimespan(client, group_key, start_time, end_time, _OnQueryPartial,
                             excl_start_key=metrics[-1].GetKey())
        for m in metrics:
          aggregator._AddMetric(m)
      else:
        callback(aggregator)

    Metric.QueryTimespan(client, group_key, start_time, end_time, _OnQueryPartial)
