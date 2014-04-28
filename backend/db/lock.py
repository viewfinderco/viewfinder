# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Lock description.

A lock is "acquired" on a "resource" in order to control concurrent
access to that resource. Resources are grouped by "resource type", and
within each type, resources are distinguished by a unique identifier.
In addition, resource-specific data can be stored in the lock. Each
lock has a single owner, who is the only one that is allowed to modify
the resource during the lock's lifetime.

At this time, locks are assumed to govern write access to resources.
They do not restrict read access. Therefore, a resource may be read
even while a lock has been acquired on it by another agent.

Locks are stored in the database so that they can survive process failure.
If a lock is acquired by an owner, and the owner fails in such a way
that the lock is never released, then the lock has been "abandoned".
Each lock owner must guarantee that every lock acquired is also released.
In order to assist owners in meeting this guarantee, owners can request
"abandonment detection" when acquiring a lock. Locks with abandonment
detection will be tagged with an expiration attribute. As long as the
acquiring process has not failed, the expiration will be updated on
a periodic basis in order to "renew" the lock. If the lock is not
renewed for a time, the lock is considered to be abandoned, and will
be cleaned up by a periodic sweep of the lock table.

Note that even though the Lock class can *detect* that a lock has been
abandoned, it cannot actually *release* those locks, as only code with
specific knowledge of a particular resource type can do that safely.

TODO(Andy): Add a LockManager class which offers callers a way to
            register for notifications when locks of a particular
            resource type have been abandoned. The LockManager would
            periodically scan the Lock table to find abandoned locks.

  Lock: control concurrent access to resources
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import logging
import random
import sys
import time

from datetime import timedelta
from functools import partial
from tornado import gen
from tornado.ioloop import IOLoop
from viewfinder.backend.base import util
from viewfinder.backend.base.exceptions import LockFailedError
from viewfinder.backend.db import vf_schema, db_client
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.hash_base import DBHashObject

@DBObject.map_table_attributes
class Lock(DBHashObject):
  """Lock object. The "Lock.TryAcquire" method acquires a lock on an
  instance of some resource type. If the acquire succeeds, then the
  lock owner has sole write access to the resource for the lifetime
  of the lock. The Release method *must* eventually be called by the
  owner, even in cases of process failure. The TryAcquire method has
  a "detect_abandonment" option that uses the lock "expiration"
  attribute and a periodic renewal to detect cases where the owner
  has failed and will not be able to call Release.
  """
  __slots__ = ['_unique_id', '_is_released', '_timeout', '_renewing']

  _table = DBObject._schema.GetTable(vf_schema.LOCK)

  FAILED_TO_ACQUIRE_LOCK = 0
  ACQUIRED_LOCK = 1
  ACQUIRED_ABANDONED_LOCK = 2

  MAX_UPDATE_ATTEMPTS = 10
  """Limit of attempts to acquire the lock in case where race conditions
  or bugs force repeated attempts.
  """

  ABANDONMENT_SECS = 60.0
  """Locks with abandonment detection are assumed to be abandoned after 60
  seconds.
  """

  LOCK_RENEWAL_SECS = 30.0
  """Locks with abandonment detection are renewed every 30 seconds, giving
  a 30 second window for slow renewals.
  """

  def __init__(self, lock_id=None, owner_id=None):
    super(Lock, self).__init__()
    self.lock_id = lock_id
    self._GenerateOwnerId() if owner_id is None else self._SetOwnerId(owner_id)
    self._is_released = False
    self._timeout = None
    self._renewing = False

  @classmethod
  def ConstructLockId(cls, resource_type, resource_id):
    """A lock id is the concatenation of the resource type and resource
    id, separated by a colon. For example:
      op:123
      vp:v--F
    """
    assert resource_type and ":" not in resource_type, resource_type
    assert resource_id and ":" not in resource_id, resource_id
    return resource_type + ':' + resource_id

  @classmethod
  def DeconstructLockId(cls, lock_id):
    """Returns the components of a lock identifier:
        (resource_type, resource_id)
    """
    index = lock_id.find(':')
    assert index != -1
    return lock_id[:index], lock_id[index + 1:]

  @classmethod
  def TryAcquire(cls, client, resource_type, resource_id, callback,
                 resource_data=None, detect_abandonment=False, owner_id=None):
    """Tries to acquire a lock on the specific resources instance,
    associating an optional "resource_data" string with the lock.
    Returns a tuple containing the lock object and a status value:
      (lock, status)

    The status value is one of:
      FAILED_TO_ACQUIRE_LOCK
        TryAcquire was unable to acquire the lock because another
        agent has already acquired it. In this case, the lock's
        "acquire_failures" attribute is incremented.

      ACQUIRED_LOCK
        TryAcquire successfully acquired the lock.

      ACQUIRED_ABANDONED_LOCK
        TryAcquire successfully acquired the lock, but the lock had
        been abandoned by the previous owner. In this case, the lock's
        resource_data is set to the previous owner's value rather than
        the new value. The new owner should ensure that the resource
        is in a complete and consistent state before proceeding.

    If the "detect_abandonment" option is set, then uses the lock's
    "expiration" attribute as a "heartbeat" to detect failure of this
    process. If the expiration is not continually renewed, then the
    lock will expire and be considered abandoned.
    """
    Lock._TryAcquire(client, resource_type, resource_id, callback,
                     resource_data=resource_data, detect_abandonment=detect_abandonment,
                     owner_id=owner_id)

  @classmethod
  @gen.engine
  def Acquire(cls, client, resource_type, resource_id, owner_id, callback):
    """Acquires lock or fails with LockFailedError.
    Returns lock as only parameter to callback.
    """
    results = yield gen.Task(Lock.TryAcquire, client, resource_type, resource_id, owner_id=owner_id)
    lock, status = results.args
    if status == Lock.FAILED_TO_ACQUIRE_LOCK:
      raise LockFailedError('Cannot acquire lock "%s:%s", owner_id "%s" because another agent has acquired it' %
                            (resource_type, resource_id, owner_id))
    callback(lock)

  @classmethod
  def ScanAbandoned(cls, client, callback, limit=None, excl_start_key=None):
    """Scans the Lock table for locks that have expired, and therefore
    are assumed to have been abandoned by their owners. Returns a tuple
    containing a list of abandoned locks and the key of the last lock
    that was scanned (or None if all locks have been scanned).
    """
    assert limit > 0, limit
    now = int(time.time())
    Lock.Scan(client, None, callback, limit=limit,
              excl_start_key=excl_start_key,
              scan_filter={'expiration': db_client.ScanFilter([now], 'LE')})

  def IsAbandoned(self):
    """Returns true if this lock has been abandoned, which means that the
    process which acquired it failed and will never release it. Abandonment
    is assumed to have occurred if enough time has passed since the last
    renewal.
    """
    return self.expiration is not None and self.expiration <= time.time()

  def AmOwner(self):
    """Returns true if the lock is owned by the current instance."""
    return self._unique_id == self.owner_id

  def IsReleased(self):
    """Returns true if the lock has been released via a call to "Release"."""
    return self._is_released

  @gen.coroutine
  def Release(self, client):
    """Releases the lock so that it may be acquired by other agents. Deletes
    the lock from the Lock table. In addition, updates the "acquire_failures"
    attribute on the lock to the value in the database. This attribute allows
    the releasing owner to see whether any other agents tried to acquire the
    lock during the period in which it was held.
    """
    assert not self.IsAbandoned(), self
    assert self.AmOwner(), self
    assert not self.IsReleased(), self

    self._StopRenewal()

    do_raise = False

    try:
      expected_acquire_failures = False if self.acquire_failures is None else self.acquire_failures
      yield gen.Task(self.Delete, client, expected={'acquire_failures': expected_acquire_failures,
                                                    'owner_id': self.owner_id})
    except Exception:
      type, value, tb = sys.exc_info()
      logging.warning('release of "%s" lock failed (will retry): %s' % (self, value))
      lock = yield gen.Task(Lock.Query, client, self.lock_id, None)
      # As long as we still have ownership of lock, update acquire_failures and retry.
      if lock.owner_id == self.owner_id:
        self.acquire_failures = lock.acquire_failures
        yield self.Release(client)
        raise gen.Return()
      else:
        # Shouldn't happen, but we definitely want to know if it is happening.
        resource_type, resource_id = Lock.DeconstructLockId(self.lock_id)
        raise LockFailedError('Cannot release lock "%s:%s", owner_id "%s" because another agent, owner_id "%s", '
                              'owns it' %
                              (resource_type, resource_id, self.owner_id, lock.owner_id))

    self._is_released = True

  def Abandon(self, client, callback):
    """Marks the lock as abandoned by disabling renewal and expiring the
    lock. Other agents may acquire or release the lock, but must first
    be certain that the protected resource is in a consistent state.
    """
    assert self.AmOwner(), self
    self._StopRenewal()
    self.expiration = 0
    self.Update(client, expected={'owner_id': self.owner_id}, callback=callback)

  @classmethod
  def _TryAcquire(cls, client, resource_type, resource_id, callback,
                  resource_data=None, detect_abandonment=False, owner_id=None,
                  attempts=0, test_hook=None):
    """Helper method that makes "MAX_UPDATE_ATTEMPTS" to acquire the
    lock. If multiple agents are trying to acquire the lock, then one
    might be updating the lock in order to acquire it while another
    is querying the lock in order to see if it can be acquired. These
    race conditions are resolved by detecting changes and retrying.

    The "test_hook" function is called just before an attempt is made
    to update the Lock row in the database. This makes testing various
    race conditions much easier.
    """
    def _OnUpdate(lock, status):
      """If lock was acquired and abandonment needs to be detected,
      then starts renewal timer.
      """
      if status != Lock.FAILED_TO_ACQUIRE_LOCK and detect_abandonment:
        lock._Renew(client)

      callback(lock, status)

    def _OnException(type, value, tb):
      """Starts over unless too many acquire attempts have been made."""
      logging.warning('race condition caused update of "%s:%s" lock to fail (will retry): %s' %
                      (resource_type, resource_id, value))

      # Retry the acquire unless too many attempts have already been made.
      if attempts >= Lock.MAX_UPDATE_ATTEMPTS:
        logging.error('too many failures attempting to update lock; aborting', exc_info=(type, value, tb))
        callback(None, Lock.FAILED_TO_ACQUIRE_LOCK)
      else:
        # TODO(Andy): We really should consider adding in a randomly-perturbed, exponential backoff
        # here to avoid senseless fights between concurrent servers.
        Lock._TryAcquire(client, resource_type, resource_id, callback,
                         resource_data=resource_data, detect_abandonment=detect_abandonment,
                         attempts=attempts + 1, test_hook=test_hook)

    def _DoUpdate(update_func):
      """Calls the test hook just before a row is updated in the database.
      Tests can simulate updates made by another agent at this critical
      juncture.
      """
      if test_hook is not None:
        test_hook(update_func)
      else:
        update_func()

    def _OnQuery(lock):
      """Creates a new lock, takes control of an abandoned lock, or reports
      failure to acquire the lock. The choice depends upon the current
      state of the lock in the database. Other agents may be trying to
      acquire the lock at the same time, so takes care to handle those race
      conditions.
      """
      if lock is None:
        # Create new lock.
        lock = Lock(lock_id, owner_id)
        if resource_data is not None:
          lock.resource_data = resource_data
        if detect_abandonment:
          lock.expiration = time.time() + Lock.ABANDONMENT_SECS

        with util.Barrier(partial(_OnUpdate, lock, Lock.ACQUIRED_LOCK), on_exception=_OnException) as b:
          _DoUpdate(partial(lock.Update, client, expected={'lock_id': False}, callback=b.Callback()))
      elif lock._IsOwnedBy(owner_id):
        assert not detect_abandonment, (resource_type, resource_data)
        # Acquirer knew owner id, so sync _unique_id up with it.
        lock._SyncUniqueIdToOwnerId()
        _OnUpdate(lock, Lock.ACQUIRED_LOCK)
      elif lock.IsAbandoned():
        logging.warning('lock was abandoned; trying to take control of it: %s' % lock)

        # Try to take control of lock.
        with util.Barrier(partial(_OnUpdate, lock, Lock.ACQUIRED_ABANDONED_LOCK), on_exception=_OnException) as b:
          _DoUpdate(partial(lock._TryTakeControl, client, detect_abandonment, b.Callback()))
      else:
        logging.warning('acquire of lock failed; already held by another agent: %s' % lock)

        # Report the failure to acquire in order to track contention on the lock and to notify the current
        # lock owner that another agent tried to acquire the lock.
        with util.Barrier(partial(_OnUpdate, None, Lock.FAILED_TO_ACQUIRE_LOCK), on_exception=_OnException) as b:
          _DoUpdate(partial(lock._TryReportAcquireFailure, client, b.Callback()))

    # Get current state of the lock from the database.
    lock_id = Lock.ConstructLockId(resource_type, resource_id)
    Lock.Query(client, lock_id, None, _OnQuery, must_exist=False)

  def _StopRenewal(self):
    """Stops renewing this lock's expiration on a periodic basis."""
    if self._timeout is not None:
      IOLoop.current().remove_timeout(self._timeout)
      self._timeout = None
    self._renewing = False

  def _IsOwnedBy(self, owner_id):
    """Compares against Lock.owner_id."""
    assert self.owner_id is not None  # None should never match self.owner_id
    return owner_id == self.owner_id

  def _SetOwnerId(self, owner_id):
    """Set owner_id and asserts that owner_id argument is not None."""
    assert owner_id is not None
    self._unique_id = owner_id
    self.owner_id = owner_id

  def _SyncUniqueIdToOwnerId(self):
    """We matched expected owner_id to actual owner_id.  Now, get _unique_id into sync with owner_id."""
    self._unique_id = self.owner_id

  def _GenerateOwnerId(self):
    """Generates a random 48 bit number (converted to string) which is used as the owner id.
    This string is a decimal representation of a 48 bit random number and not 6 random bytes.
    """
    self._SetOwnerId(str(random.getrandbits(48)))

  def _TryTakeControl(self, client, detect_abandonment, callback):
    """Sets new owner on this lock and update expiration."""
    former_owner_id = self.owner_id
    self._GenerateOwnerId()
    self.expiration = time.time() + Lock.ABANDONMENT_SECS if detect_abandonment else None
    self.Update(client, expected={'owner_id': former_owner_id}, callback=callback)

  def _TryReportAcquireFailure(self, client, callback):
    """Increments the "acquire_failures" attribute on the lock. Multiple
    agents may concurrently try to acquire the lock, so this operation
    must handle race conditions.  Expecting the owner_id is a way to ensure
    that the lock hasn't been released by the owner before we update it here.
    Otherwise, our attempt to update a released lock will result in a lock row without
    expiration or resource_data fields which means a stuck lock.
    """
    expected = {'owner_id': self.owner_id}

    if self.acquire_failures is None:
      self.acquire_failures = 1
      expected['acquire_failures'] = False
    else:
      self.acquire_failures += 1
      expected['acquire_failures'] = self.acquire_failures - 1

    self.Update(client, expected=expected, callback=callback)

  def _Renew(self, client):
    """Continually renews the lock by updating its expiration on a regular
    interval. As long as the expiration is in the future, the lock is not
    considered to be abandoned.
    """
    def _OnException(type, value, tb):
      """If failure occurs during renewal, just abandon the lock."""
      logging.error('failure trying to renew lock "%s"', exc_info=(type, value, tb))

    def _OnRenewalTimeout():
      self._timeout = None
      if not self._renewing:
        return
      logging.info('renewing lock: %s' % self)

      with util.Barrier(_ScheduleNextRenew, on_exception=_OnException) as b:
        self.expiration = time.time() + Lock.ABANDONMENT_SECS
        self.Update(client, b.Callback())

    def _ScheduleNextRenew():
      if not self._renewing:
        return
      self._timeout = IOLoop.current().add_timeout(timedelta(seconds=Lock.LOCK_RENEWAL_SECS), _OnRenewalTimeout)

    self._renewing = True
    _ScheduleNextRenew()
