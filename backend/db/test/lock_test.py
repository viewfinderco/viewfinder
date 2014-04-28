# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for Lock class.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import time

from datetime import timedelta
from functools import partial
from base_test import DBBaseTestCase
from viewfinder.backend.base.exceptions import LockFailedError
from viewfinder.backend.db.lock import Lock


class LockTestCase(DBBaseTestCase):
  def testSimpleAcquire(self):
    """Test acquiring a lock."""
    self._TryAcquire('my', '1234')
    self._TryAcquire('my', '!@#%!@#$', resource_data='some data')
    self._TryAcquire('my', '12-34', resource_data='the quick brown fox jumped over the lazy dog',
                     detect_abandonment=True)

  def testLockAlreadyAcquired(self):
    """Test attempt to acquire a lock that is already owned."""
    lock = self._TryAcquire('op', 'andy', release_lock=False)
    self._TryAcquire('op', 'andy', expected_status=Lock.FAILED_TO_ACQUIRE_LOCK)
    self._TryAcquire('op', 'andy', expected_status=Lock.FAILED_TO_ACQUIRE_LOCK)
    self._Release(lock)
    self.assertEqual(lock.acquire_failures, 2)

  def testAbandonedLock(self):
    """Test acquiring an abandoned lock."""
    lock = self._TryAcquire('op', 'id', detect_abandonment=True, release_lock=False)
    lock.Abandon(self._client, self.stop)
    self.wait()
    self._TryAcquire('op', 'id', expected_status=Lock.ACQUIRED_ABANDONED_LOCK)

  def testRenewLock(self):
    """Test that renewal mechanism is preventing lock abandonment."""
    Lock.ABANDONMENT_SECS = .3
    Lock.LOCK_RENEWAL_SECS = .1
    lock = self._TryAcquire('op', 'id', detect_abandonment=True, release_lock=False)
    self.io_loop.add_timeout(timedelta(seconds=.6), self.stop)
    self.wait()
    self._TryAcquire('op', 'id', expected_status=Lock.FAILED_TO_ACQUIRE_LOCK)
    self._Release(lock)
    Lock.ABANDONMENT_SECS = 60
    Lock.LOCK_RENEWAL_SECS = 30

  def testRaceToAcquire(self):
    """Test cases where multiple agents are racing to acquire locks."""
    lock_to_release = []

    def _OnAcquire(update_func, lock, status):
      lock_to_release.append(lock)
      update_func()

    def _Race(update_func):
      if len(lock_to_release) == 0:
        # Win race to acquire lock.
        Lock.TryAcquire(self._client, 'op', 'id', partial(_OnAcquire, update_func))
      elif len(lock_to_release) == 1:
        # Win race to update acquire_failures.
        Lock.TryAcquire(self._client, 'op', 'id', partial(_OnAcquire, update_func))
      else:
        update_func()

    self._TryAcquire('op', 'id', expected_status=Lock.FAILED_TO_ACQUIRE_LOCK,
                     test_hook=_Race)

    self._Release(lock_to_release[0])

  def testRaceToUpdateReleasedLock(self):
    """Test case where failed lock acquirer tries to update lock after it's been released."""

    def _Race(lock_to_release, update_func):
      # Release the acquired lock after the current attempt has queried the row for the lock
      # and has its own instance of the lock.
      lock_to_release.Release(self._client, callback=update_func)

    # First, acquire the lock.
    lock_to_release = self._TryAcquire('op', 'id', release_lock=False)

    # Now, try to acquire, expecting failure because we'll release it in the test hook.
    self._TryAcquire('op', 'id', expected_status=Lock.FAILED_TO_ACQUIRE_LOCK,
                     test_hook=partial(_Race, lock_to_release), release_lock=False)

    # Now, check for lock row.  There shouldn't be one.
    lock_id = Lock.ConstructLockId('op', 'id')
    lock = self._RunAsync(Lock.Query, self._client, lock_id, None, must_exist=False)
    self.assertIsNone(lock, 'Lock row should not exist')

  def testRaceToTakeOver(self):
    """Test cases where multiple agents are racing to take over an
    abandoned lock.
    """
    lock_to_release = []

    def _OnAcquire(update_func, lock, status):
      lock_to_release.append(lock)
      update_func()

    def _Race(update_func):
      if len(lock_to_release) == 0:
        # Win race to acquire the abandoned lock.
        Lock.TryAcquire(self._client, 'op', 'id', partial(_OnAcquire, update_func))
      else:
        update_func()

    lock = self._TryAcquire('op', 'id', detect_abandonment=True, release_lock=False)
    lock.expiration = time.time() - 1
    lock.Update(self._client, self.stop)
    self.wait()
    self._TryAcquire('op', 'id', expected_status=Lock.FAILED_TO_ACQUIRE_LOCK,
                     test_hook=_Race)

    self._Release(lock_to_release[0])

  def testAcquireLock(self):
    """Test Lock.Acquire function."""
    hit_exception = False

    # This should succeed.
    lock = self._RunAsync(Lock.Acquire, self._client, 'tst', 'id0', None)
    try:
      # This should fail and raise an error because the lock is already taken.
      self._RunAsync(Lock.Acquire, self._client, 'tst', 'id0', None)
      try:
        self.fail("Shouldn't reach this point in try.")
      finally:
        self.fail("Shouldn't reach this point in finally.")
    except Exception as e:
      hit_exception = True
      self.assertEqual(type(e), LockFailedError)
    finally:
      self._RunAsync(lock.Release, self._client)

    self.assertTrue(lock.IsReleased())
    self.assertTrue(hit_exception)

  def testAcquireLockWithError(self):
    """Test Lock.Acquire failure in try/except that encounters an error."""
    error_was_raised = False

    lock = self._RunAsync(Lock.Acquire, self._client, 'tst', 'id0', None)
    try:
      raise Exception('raise an error')
    except Exception as e:
      self.assertEqual(e.message, 'raise an error')
      error_was_raised = True
    finally:
      self._RunAsync(lock.Release, self._client)

    self.assertTrue(error_was_raised)
    self.assertTrue(lock.IsReleased())
    self.assertTrue(lock.AmOwner())

    # Now, ensure that the lock can be aquired.
    lock = self._RunAsync(Lock.Acquire, self._client, 'tst', 'id0', None)
    self.assertTrue(lock.AmOwner())
    self.assertTrue(not lock.IsReleased())
    self._RunAsync(lock.Release, self._client)

  def testReaquireLock(self):
    """Test that Lock.Acquire will succeed with orphaned lock when owner_id matches that of lock."""

    # Create lock, but don't release so that it's 'orphaned'.
    lock = self._RunAsync(Lock.Acquire, self._client, 'tst', 'id0', 'owner89')
    self.assertTrue(lock.AmOwner())

    # Now, try to acquire the same lock using the same owner_id and observe that it succeeds.
    lock = self._RunAsync(Lock.Acquire, self._client, 'tst', 'id0', 'owner89')
    self.assertTrue(lock.AmOwner())
    self._RunAsync(lock.Release, self._client)

  def testReleaseOtherOwnedLock(self):
    """Test releasing a lock that's owned by a different agent."""
    lock = self._RunAsync(Lock.Acquire, self._client, 'tst', 'id0', 'owner89')

    # Read same lock into a new object.
    lock2 = self._RunAsync(Lock.Query, self._client, lock.lock_id, None)
    # Set a different owner_id on it:
    lock2.owner_id = 'new_owner_id'
    self._RunAsync(lock2.Update, self._client)

    # Now try to release (should fail).
    self.assertRaises(LockFailedError, self._RunAsync, lock.Release, self._client)

    # Now, read it to demonstrate that it hasn't been released.
    lock3 = self._RunAsync(Lock.Query, self._client, lock.lock_id, None)

  def _TryAcquire(self, resource_type, resource_id, expected_status=Lock.ACQUIRED_LOCK,
                  resource_data=None, detect_abandonment=False, release_lock=True, test_hook=None):
    Lock._TryAcquire(self._client, resource_type, resource_id,
                     lambda lock, status: self.stop((lock, status)),
                     resource_data=resource_data, detect_abandonment=detect_abandonment, test_hook=test_hook)
    lock, status = self.wait()

    if release_lock and status != Lock.FAILED_TO_ACQUIRE_LOCK:
      self._Release(lock)

    self.assertEqual(status, expected_status)

    if status != Lock.FAILED_TO_ACQUIRE_LOCK:
      self.assertEqual(Lock.DeconstructLockId(lock.lock_id), (resource_type, resource_id))
      self.assertIsNotNone(lock.owner_id)
      if detect_abandonment:
        self.assertAlmostEqual(lock.expiration, time.time() + Lock.ABANDONMENT_SECS,
                               delta=Lock.ABANDONMENT_SECS / 4)
      self.assertEqual(lock.resource_data, resource_data)

    return lock

  def _Release(self, lock):
    lock.Release(self._client, callback=self.stop)
    self.assertTrue(lock.IsReleased)
    self.wait()
