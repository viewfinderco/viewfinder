# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Job utility functions.

A Job is a process independent of the backend but using dynamodb to coordinate runs.
The class provides two independent (and both optional) features:
- locking: grab a job-specific lock for the duration of the work. prevents other instances of the same job from running.
  methods: AcquireLock(), ReleaseLock()
- run status: fetch previous run statuses and write run status at the end (with optional additional stats).
  method: Start(), FindPreviousRuns(), RegisterRun()

Jobs should be used as follows:

job = Job(db_client, 'dbchk')
if yield gen.Task(job.AcquireLock):
  # Acquired lock, we must release it eventually.
  # Record start time:
  job.Start()

  # Find last successful run within the last 7 days.
  runs = yield gen.Task(job.FindPreviousRuns, start_timestamp=time.time() - 7*24*3600,
                        status=Job.STATUS_SUCCESS, limit=1)
  if len(runs) > 0:
    yield gen.Task(job.ReleaseLock)
    return
  status = Job.STATUS_SUCCESS
  try:
    # do work
  except:
    status = Job.STATUS_FAILURE

  # Write summary with extra stats.
  stats = DotDict()
  stats['analyzed_bytes': 1024]
  yield gen.Task(job.RegisterRun(status, stats=stats):

  # Release lock.
  yield gen.Task(job.ReleaseLock)

By default, abandoned locks can be acquired. Only jobs that cannot recover from a failed run and require manual
intervention should set detect_abandonment=False.

TODO(marc): add helpers to read/write job status entries in the Metric table. This is how we're going
to figure out what the last successful run was and determine whether to run again.

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import json
import logging
import os
import time

from tornado import gen
from viewfinder.backend.base import constants, util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import db_client, metric
from viewfinder.backend.db.lock import Lock
from viewfinder.backend.db.lock_resource_type import LockResourceType

class Job(object):

  # Status codes stored in the metric payload.status
  STATUS_SUCCESS = 'success'
  STATUS_FAILURE = 'failure'

  def __init__(self, client, name):
    """Initialize a new Job object."""
    self._client = client
    self._name = name
    self._lock = None
    self._start_time = None


  def __del__(self):
    """There's no point in attempting to release the lock in the destructor, it's much too unreliable."""
    if self._lock is not None:
      logging.error('Job:%s is being cleaned, but lock was not released: %r' % (self._name, self._lock))


  def Start(self):
    """Start the start time to now."""
    self._start_time = int(time.time())


  def HasLock(self):
    """Return true if a lock is held."""
    return self._lock is not None

  @gen.engine
  def AcquireLock(self, callback, resource_data=None, detect_abandonment=True):
    """Attempt to acquire the lock "job:name". Returns True if acquired.
    If resource_data is None, a string is built consisting of the local user name,
    machine hostname and timestamp.
    If detect_abandonment is True, we allow acquisition of expired locks and specify
    an expiration on our lock. If False, acquiring an abandoned lock is considered an acquire failure.
    If lock acquisition succeeds, the client must call Release() when finished to release the lock.
    """
    assert self._lock is None, 'Job.AcquireLock called with existing lock held %r' % self._lock

    data = '%s@%s:%d' % (util.GetLocalUser(), os.uname()[1], time.time()) if resource_data is None else resource_data

    result = yield gen.Task(Lock.TryAcquire, self._client, LockResourceType.Job, self._name,
                            resource_data=data, detect_abandonment=detect_abandonment)
    lock, status = result.args

    if status == Lock.FAILED_TO_ACQUIRE_LOCK:
      callback(False)
    elif status == Lock.ACQUIRED_ABANDONED_LOCK and not detect_abandonment:
      logging.warning('Acquired abandoned lock, but specified locking without expiration; abandoning %r' % lock)
      yield gen.Task(lock.Abandon, self._client)
      callback(False)
    else:
      # ACQUIRED_LOCK or ACQUIRED_ABANDONED with abandonment detection enabled.
      self._lock = lock
      callback(True)


  @gen.engine
  def ReleaseLock(self, callback):
    """Release _lock if not None."""
    if self._lock is not None:
      yield gen.Task(self._lock.Release, self._client)
      self._lock = None
    callback()


  @gen.engine
  def FindPreviousRuns(self, callback, start_timestamp=None, status=None, limit=None):
    """Look for previous runs of this job in the metrics table. Return all found runs regardless of status.
    If start_timestamp is None, search for jobs started in the last week.
    If status is specified, only return runs that finished with this status, otherwise return all runs.
    If limit is not None, return only the latest 'limit' runs, otherwise return all runs.
    Runs are sorted by timestamp.
    """
    assert status in [None, Job.STATUS_SUCCESS, Job.STATUS_FAILURE], 'Unknown status: %s' % status
    runs = []
    cluster = metric.JOBS_STATS_NAME
    # TODO(marc): there is no guarantee that jobs will run daily (could be more or less). It shouldn't matter except
    # when accessing the data using counters.
    group_key = metric.Metric.EncodeGroupKey(cluster, metric.Metric.FindIntervalForCluster(cluster, 'daily'))
    start_time = start_timestamp if start_timestamp is not None else time.time() - constants.SECONDS_PER_WEEK

    # Search for metrics from start_time to now.
    existing_metrics = yield gen.Task(metric.Metric.QueryTimespan, self._client, group_key, start_time, None)
    for m in existing_metrics:
      if m.machine_id != self._name:
        # Not for this job.
        continue

      # Parse and validate payload.
      payload = DotDict(json.loads(m.payload))
      assert 'start_time' in payload and 'status' in payload, 'Malformed payload: %r' % payload
      assert payload['start_time'] == m.timestamp, 'Payload start_time does not match metric timestamp'

      if status is not None and payload['status'] != status:
        continue

      runs.append(payload)

    # Sort by timestamp, although it should already should be.
    runs.sort(key=lambda payload: payload['start_time'])
    if limit is None:
      callback(runs)
    else:
      callback(runs[-limit:])


  @gen.engine
  def FindLastSuccess(self, callback, start_timestamp=None, with_payload_key=None, with_payload_value=None):
    """Find and return the latest successful run. Search back to start_timestamp (a week ago if None).
    If with_payload_key is not None, the key must be found in the payload (DotDict format).
    If with_payload_value is not None, the value at that key must match.
    Callback is run with the matching metric payload if found, else with None.
    """
    payloads = yield gen.Task(self.FindPreviousRuns, start_timestamp=start_timestamp, status=Job.STATUS_SUCCESS)
    for p in reversed(payloads):
      assert p['status'] == Job.STATUS_SUCCESS
      if with_payload_key is not None and with_payload_key not in p:
        continue
      if with_payload_value is not None:
        assert with_payload_key is not None, 'with_payload_value specified, but with_payload_key is None'
        if p[with_payload_key] != with_payload_value:
          continue
      callback(p)
      return

    callback(None)


  @gen.engine
  def RegisterRun(self, status, callback, stats=None, failure_msg=None):
    """Write the metric entry for this run. The start_time is set in Start(). end_time is now.
    If stats is not none, the DotDict is added to the metrics payload with the prefix 'stats'.
    If failure_msg is not None and status==STATUS_FAILURE, write the message in payload.failure_msg.
    """
    assert status in [None, Job.STATUS_SUCCESS, Job.STATUS_FAILURE], 'Unknown status: %s' % status
    assert self._start_time is not None, 'Writing job summary, but Start never called.'
    end_time = int(time.time())
    payload = DotDict()
    payload['start_time'] = self._start_time
    payload['end_time'] = end_time
    payload['status'] = status
    if stats is not None:
      assert isinstance(stats, DotDict), 'Stats is not a DotDict: %r' % stats
      payload['stats'] = stats
    if failure_msg is not None and status == Job.STATUS_FAILURE:
      payload['failure_msg'] = failure_msg


    cluster = metric.JOBS_STATS_NAME
    group_key = metric.Metric.EncodeGroupKey(cluster, metric.Metric.FindIntervalForCluster(cluster, 'daily'))
    new_metric = metric.Metric.Create(group_key, self._name, self._start_time, json.dumps(payload))
    yield gen.Task(new_metric.Update, self._client)

    # Clear start time, we should not be able to run RegisterRun multiple times for a single run.
    self._start_time = None

    callback()
