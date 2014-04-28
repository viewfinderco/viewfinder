# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Tests for Job class.
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import time

from viewfinder.backend.base import constants
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db.job import Job
from viewfinder.backend.db.lock import Lock
from viewfinder.backend.db.lock_resource_type import LockResourceType

from base_test import DBBaseTestCase

class JobTestCase(DBBaseTestCase):
  def testLocking(self):
    """Test basic locking mechanism."""
    job1 = Job(self._client, 'test_job')
    self.assertTrue(self._RunAsync(job1.AcquireLock))

    job2 = Job(self._client, 'test_job')
    self.assertFalse(self._RunAsync(job2.AcquireLock))

    # Abandon job1 lock. We never do this on real jobs, so manually clear the lock.
    self._RunAsync(job1._lock.Abandon, self._client)
    job1._lock = None

    # Set detect_abandonment=False: failure.
    self.assertFalse(self._RunAsync(job2.AcquireLock, detect_abandonment=False))
    self.assertFalse(self._RunAsync(job2.AcquireLock, detect_abandonment=False))

    # Now allow abandoned lock acquisition.
    self.assertTrue(self._RunAsync(job2.AcquireLock))
    self.assertFalse(self._RunAsync(job1.AcquireLock))
    self._RunAsync(job2.ReleaseLock)

    # Job1 grabs the lock again.
    self.assertTrue(self._RunAsync(job1.AcquireLock))
    self._RunAsync(job1.ReleaseLock)

  def testMetrics(self):
    """Test fetching/writing metrics."""
    # Job being tested.
    job = Job(self._client, 'test_job')
    prev_runs = self._RunAsync(job.FindPreviousRuns)
    self.assertEqual(len(prev_runs), 0)

    # Unrelated job with a different name. Run entries should not show up under 'test_job'.
    other_job = Job(self._client, 'other_test_job')
    other_job.Start()
    self._RunAsync(other_job.RegisterRun, Job.STATUS_SUCCESS)
    other_job.Start()
    self._RunAsync(other_job.RegisterRun, Job.STATUS_FAILURE)

    # Calling RegisterRun without first calling Start fails because the start_time is not set.
    self.assertIsNone(job._start_time)
    self.assertRaises(AssertionError, self._RunAsync, job.RegisterRun, Job.STATUS_SUCCESS)

    job.Start()
    self.assertIsNotNone(job._start_time)
    # Overwrite it for easier testing.
    start_time = job._start_time = int(time.time() - (constants.SECONDS_PER_WEEK + constants.SECONDS_PER_HOUR))

    # Write run summary with extra stats.
    stats = DotDict()
    stats['foo.bar'] = 5
    stats['baz'] = 'test'
    self._RunAsync(job.RegisterRun, Job.STATUS_SUCCESS, stats=stats, failure_msg='foo')
    # start_time is reset to prevent multiple calls to RegisterRun.
    self.assertIsNone(job._start_time)
    self.assertRaises(AssertionError, self._RunAsync, job.RegisterRun, Job.STATUS_SUCCESS)

    end_time = int(time.time())
    # Default search is "runs started in the past week".
    prev_runs = self._RunAsync(job.FindPreviousRuns)
    self.assertEqual(len(prev_runs), 0)
    # Default search is for successful runs.
    prev_runs = self._RunAsync(job.FindPreviousRuns, start_timestamp=(start_time - 10))
    self.assertEqual(len(prev_runs), 1)
    self.assertEqual(prev_runs[0]['start_time'], start_time)
    self.assertAlmostEqual(prev_runs[0]['end_time'], end_time, delta=10)
    self.assertEqual(prev_runs[0]['status'], Job.STATUS_SUCCESS)
    self.assertEqual(prev_runs[0]['stats.foo.bar'], 5)
    self.assertEqual(prev_runs[0]['stats.baz'], 'test')
    # failure_msg does nothing when status is SUCCESS.
    self.assertTrue('failure_msg' not in prev_runs[0])

    # Search for failed runs.
    prev_runs = self._RunAsync(job.FindPreviousRuns, start_timestamp=(start_time - 10), status=Job.STATUS_FAILURE)
    self.assertEqual(len(prev_runs), 0)

    # Create a failed job summary.
    job.Start()
    start_time2 = job._start_time = int(time.time() - constants.SECONDS_PER_HOUR)
    self._RunAsync(job.RegisterRun, Job.STATUS_FAILURE, failure_msg='stack trace')

    # Find previous runs using a variety of filters.
    prev_runs = self._RunAsync(job.FindPreviousRuns, start_timestamp=(start_time - 10), status=Job.STATUS_SUCCESS)
    self.assertEqual(len(prev_runs), 1)
    self.assertEqual(prev_runs[0]['start_time'], start_time)
    prev_runs = self._RunAsync(job.FindPreviousRuns, start_timestamp=(start_time - 10), status=Job.STATUS_FAILURE)
    self.assertEqual(len(prev_runs), 1)
    self.assertEqual(prev_runs[0]['status'], Job.STATUS_FAILURE)
    self.assertEqual(prev_runs[0]['failure_msg'], 'stack trace')
    self.assertEqual(prev_runs[0]['start_time'], start_time2)
    prev_runs = self._RunAsync(job.FindPreviousRuns, start_timestamp=(start_time - 10))
    self.assertEqual(len(prev_runs), 2)
    self.assertEqual(prev_runs[0]['start_time'], start_time)
    self.assertEqual(prev_runs[1]['start_time'], start_time2)
    prev_runs = self._RunAsync(job.FindPreviousRuns, start_timestamp=(start_time2 - 10))
    self.assertEqual(len(prev_runs), 1)
    self.assertEqual(prev_runs[0]['start_time'], start_time2)
    prev_runs = self._RunAsync(job.FindPreviousRuns, start_timestamp=(start_time - 10), limit=1)
    self.assertEqual(len(prev_runs), 1)
    self.assertEqual(prev_runs[0]['start_time'], start_time2)

    # Find last successful run with optional payload key/value.
    prev_success = self._RunAsync(job.FindLastSuccess, start_timestamp=(start_time - 10))
    self.assertIsNotNone(prev_success)
    self.assertEqual(prev_success['stats.foo.bar'], 5)
    prev_success = self._RunAsync(job.FindLastSuccess, start_timestamp=(start_time - 10), with_payload_key='stats.baz')
    self.assertIsNotNone(prev_success)
    self.assertEqual(prev_success['stats.foo.bar'], 5)
    prev_success = self._RunAsync(job.FindLastSuccess, start_timestamp=(start_time - 10), with_payload_key='stats.bar')
    self.assertIsNone(prev_success)
    prev_success = self._RunAsync(job.FindLastSuccess, start_timestamp=(start_time - 10),
                                  with_payload_key='stats.baz', with_payload_value='test')
    self.assertIsNotNone(prev_success)
    self.assertEqual(prev_success['stats.foo.bar'], 5)
    prev_success = self._RunAsync(job.FindLastSuccess, start_timestamp=(start_time - 10),
                                  with_payload_key='stats.baz', with_payload_value='test2')
    self.assertIsNone(prev_success)
