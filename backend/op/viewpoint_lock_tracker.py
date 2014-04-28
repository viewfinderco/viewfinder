# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewpoint lock tracker.

Some operations need to lock multiple viewpoints during the course of execution. This class
provides help for acquiring, tracking, and releasing those locks.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

from tornado import gen
from viewfinder.backend.db.viewpoint import Viewpoint


class ViewpointLockTracker(object):
  """Locks should be acquired via "AcquireViewpointLock". Once the locks are no longer needed,
  they should be released via "ReleaseAllViewpointLocks".
  """

  def __init__(self, client):
    self._client = client
    self._acquired_viewpoint_locks = {}

  @gen.coroutine
  def AcquireViewpointLock(self, viewpoint_id):
    """Ensure that a lock is acquired for the given viewpoint.

    The lock may have already been acquired in which case this is a no-op.
    Locks should be acquired one at a time, never concurrently.
    """
    if not self._acquired_viewpoint_locks.has_key(viewpoint_id):
      lock = yield gen.Task(Viewpoint.AcquireLock, self._client, viewpoint_id)

      # Locks should not be acquired concurrently, but assert just to be safe.
      assert not self._acquired_viewpoint_locks.has_key(viewpoint_id), self
      self._acquired_viewpoint_locks[viewpoint_id] = lock

  @gen.coroutine
  def ReleaseAllViewpointLocks(self):
    """Release all viewpoint locks that have been acquired up to this point."""
    yield [gen.Task(Viewpoint.ReleaseLock, self._client, viewpoint_id, lock)
           for viewpoint_id, lock in self._acquired_viewpoint_locks.items()]
    self._acquired_viewpoint_locks = {}

  def IsViewpointLocked(self, viewpoint_id):
    """Returns true if a lock is already held for the given viewpoint."""
    return viewpoint_id in self._acquired_viewpoint_locks
