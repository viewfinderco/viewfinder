# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for Operation and OpManager.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import time

from functools import partial

from viewfinder.backend.base import message, util, counters
from viewfinder.backend.base.exceptions import PermissionError
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.lock import Lock
from viewfinder.backend.db.lock_resource_type import LockResourceType
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.op_manager import OpManager
from viewfinder.backend.op.user_op_manager import UserOpManager

from base_test import DBBaseTestCase

class OperationTestCase(DBBaseTestCase):
  def setUp(self):
    super(OperationTestCase, self).setUp()
    # Speed up retries for testing.
    UserOpManager._INITIAL_BACKOFF_SECS = 0.10
    UserOpManager._SMALL_INITIAL_BACKOFF_SECS = 0.10

    self.meter = counters.Meter(counters.counters.viewfinder.operation)
    self.meter_start = time.time()

  def tearDown(self):
    super(OperationTestCase, self).tearDown()
    UserOpManager._INITIAL_BACKOFF_SECS = 8.0

  @async_test
  def testDuplicateOperations(self):
    """Verify that inserting duplicate operations is a no-op."""
    op_id = Operation.ConstructOperationId(self._mobile_dev.device_id, 100)

    with util.Barrier(self.stop) as b:
      for i in xrange(10):
        Operation.CreateAndExecute(self._client, self._user.user_id, self._mobile_dev.device_id,
                                   'HidePhotosOperation.Execute',
                                   {'headers': {'op_id': op_id, 'op_timestamp': time.time(),
                                                'synchronous': True},
                                    'user_id': self._user.user_id,
                                    'episodes': []}, b.Callback())

  def testOperationRetries(self):
    """Verify an operation is retried on failure."""
    # Acquire lock ahead of creation and execution of the operation.
    # This will cause the operation to fail, but not be aborted, so it can be retried.
    self._RunAsync(Lock.Acquire, self._client, LockResourceType.Viewpoint, self._user.private_vp_id,
                   Operation.ConstructOperationId(self._mobile_dev.device_id, 123))

    # Make request to upload an episode
    op = self._RunAsync(self._UploadPhotoOperation, self._user.user_id, self._mobile_dev.device_id, 1)

    start = time.time()
    while True:
      # Wait for op to execute.
      self._RunAsync(self.io_loop.add_timeout, time.time() + UserOpManager._INITIAL_BACKOFF_SECS)

      op = self._RunAsync(Operation.Query,
                          self._client,
                          op.user_id,
                          op.operation_id,
                          None,
                          must_exist=False)
      if op.attempts < 3:
        self.assertTrue(not op.quarantine)
      elif op.attempts == 3:
        # After 3 attempts, op should go into quarantine.
        self.assertTrue(op.first_failure is not None)
        self.assertTrue(op.last_failure is not None)
        self.assertEqual(op.quarantine, 1)

        # Manually goose the op manager to retry abandoned locks.
        OpManager.Instance()._ScanFailedOps()
      elif op.attempts == 4:
        # No operations completed successfully.
        self._CheckCounters(op.attempts, op.attempts - 1)
        break

  @async_test
  def testFailedRetriableOp(self):
    """Verify that a failing retriable operation doesn't stop other ops from
    continuing.
    """
    def _OnQueryOrigOp(orig_op):
      retry_count = orig_op.attempts - 1
      # 3 base operations expected plus 1 photo upload operation as part of _CreateBlockedOperation().
      self._CheckCounters(3 + 1 + retry_count, retry_count)
      self.stop()

    def _OnSecondUploadOp(orig_op, op):
      """Wait for the second operation and on completion, query the
      original operation which is still failing. It should have a retry.
      """
      Operation.WaitForOp(self._client, op.user_id, op.operation_id,
                          partial(Operation.Query, self._client, orig_op.user_id,
                                  orig_op.operation_id, None, _OnQueryOrigOp))

    def _OnFirstUpload(orig_op):
      self._UploadPhotoOperation(orig_op.user_id, orig_op.device_id, 2,
                                 partial(_OnSecondUploadOp, orig_op))

    def _OnFirstUploadOp(orig_op, op):
      Operation.WaitForOp(self._client, op.user_id, op.operation_id,
                          partial(_OnFirstUpload, orig_op))

    def _OnCreateOp(orig_op):
      """Set the operation's quarantine boolean to true and update."""
      orig_op.quarantine = 1
      orig_op.Update(self._client, partial(self._UploadPhotoOperation,
                                           orig_op.user_id, orig_op.device_id, 1,
                                           partial(_OnFirstUploadOp, orig_op)))

    self._CreateBlockedOperation(self._user.user_id, self._mobile_dev.device_id, _OnCreateOp)

  @async_test
  def testFailedAbortableOp(self):
    """Verify that a failing aborted operation doesn't stop other ops from
    continuing.
    """
    def _OnQueryOrigOp(orig_op):
      # 3 base operations expected and no retries because the failed operation aborted.
      self._CheckCounters(3, 0)
      self.stop()

    def _OnSecondUploadOp(orig_op, op):
      """Wait for the second operation and on completion, query the
      original operation which is still failing. It should have a retry.
      """
      Operation.WaitForOp(self._client, op.user_id, op.operation_id,
                          partial(_OnQueryOrigOp, orig_op))

    def _OnFirstUpload(orig_op):
      self._UploadPhotoOperation(orig_op.user_id, orig_op.device_id, 2,
                                 partial(_OnSecondUploadOp, orig_op))

    def _OnFirstUploadOp(orig_op, op):
      Operation.WaitForOp(self._client, op.user_id, op.operation_id,
                          partial(_OnFirstUpload, orig_op))

    def _OnCreateOp(orig_op):
      self._UploadPhotoOperation(orig_op.user_id, orig_op.device_id, 1,
                                 partial(_OnFirstUploadOp, orig_op))

    self._CreateBadOperation(self._user.user_id, self._mobile_dev.device_id, _OnCreateOp)

  def testMismatchedDeviceId(self):
    """ERROR: Try to create an op_id that does not match the client's
    device.
    """
    op_id = Operation.ConstructOperationId(100, 100)

    self.assertRaises(PermissionError,
                      self._RunAsync,
                      Operation.CreateAndExecute,
                      self._client,
                      self._user.user_id,
                      self._mobile_dev.device_id,
                      'ShareNewOperation.Execute',
                      {'headers': {'op_id': op_id, 'op_timestamp': time.time(),
                                   'original_version': message.Message.ADD_OP_HEADER_VERSION}})

  def _UploadPhotoOperation(self, user_id, device_id, seed, callback, photo_id=None):
    """Creates an upload photos operation using seed to create unique ids."""
    request = {'user_id': user_id,
               'activity': {'activity_id': Activity.ConstructActivityId(time.time(), device_id, seed),
                            'timestamp': time.time()},
               'episode': {'user_id': user_id,
                           'episode_id': Episode.ConstructEpisodeId(time.time(), device_id, seed),
                           'timestamp': time.time()},
               'photos': [{'photo_id': Photo.ConstructPhotoId(time.time(), device_id, seed) if photo_id is None else photo_id,
                           'aspect_ratio': 1.3333,
                           'timestamp': time.time(),
                           'tn_size': 5 * 1024,
                           'med_size': 50 * 1024,
                           'full_size': 150 * 1024,
                           'orig_size': 1200 * 1024}]}
    Operation.CreateAndExecute(self._client, user_id, device_id,
                               'UploadEpisodeOperation.Execute', request, callback)

  def _CreateBadOperation(self, user_id, device_id, callback):
    """Creates a photo share for a photo which doesn't exist."""
    request = {'user_id': user_id,
               'activity': {'activity_id': 'a123',
                            'timestamp': time.time()},
               'viewpoint': {'viewpoint_id': Viewpoint.ConstructViewpointId(100, 100),
                             'type': Viewpoint.EVENT},
               'episodes': [{'existing_episode_id': 'eg8QVrk3S',
                             'new_episode_id': 'eg8QVrk3T',
                             'timestamp': time.time(),
                             'photo_ids': ['pg8QVrk3S']}],
               'contacts': [{'identity': 'Local:testing1',
                             'name': 'Peter Mattis'}]}
    Operation.CreateAndExecute(self._client, user_id, device_id,
                               'ShareNewOperation.Execute', request, callback)

  def _CreateBlockedOperation(self, user_id, device_id, callback):
    """Creates a photo share after locking the viewpoint so that the operation will fail and get retried."""
    photo_id = Photo.ConstructPhotoId(time.time(), device_id, 123)
    self._RunAsync(self._UploadPhotoOperation, user_id, device_id, 1, photo_id=photo_id)

    self._RunAsync(Lock.Acquire, self._client, LockResourceType.Viewpoint, 'vp123',
                   Operation.ConstructOperationId(device_id, 123))

    request = {'user_id': user_id,
               'activity': {'activity_id': 'a123',
                            'timestamp': time.time()},
               'viewpoint': {'viewpoint_id': 'vp123',
                             'type': Viewpoint.EVENT},
               'episodes': [{'existing_episode_id': 'eg8QVrk3S',
                             'new_episode_id': 'eg8QVrk3T',
                             'timestamp': time.time(),
                             'photo_ids': [photo_id]}],
               'contacts': [{'identity': 'Local:testing1',
                             'name': 'Peter Mattis'}]}

    Operation.CreateAndExecute(self._client, user_id, device_id,
                               'ShareNewOperation.Execute', request, callback)

  def _CheckCounters(self, expected_ops, expected_retries):
    """Method used in a few tests to help verify performance counters."""
    sample = self.meter.sample()
    elapsed = time.time() - self.meter_start
    ops_per_min = (expected_ops / elapsed) * 60
    self.assertAlmostEqual(sample.viewfinder.operation.ops_per_min, ops_per_min, delta=ops_per_min * .1)
    retries_per_min = (expected_retries / elapsed) * 60
    self.assertAlmostEqual(sample.viewfinder.operation.retries_per_min, retries_per_min, delta=retries_per_min * .1)

    # Assuming at least one op succeeded, avg_op_time should be > 0.
    if expected_ops > expected_retries + 1:
      self.assertGreater(sample.viewfinder.operation.avg_op_time, 0)

    self.meter_start += elapsed
