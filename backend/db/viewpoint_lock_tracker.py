# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Tracks set of viewpoints locked by an operation.

Certain actions require viewpoint lock(s) to be acquired before it's safe to perform them.
For example, if a user adds a follower to a viewpoint, that viewpoint should be locked in
order to avoid conflicts with other users. The ViewpointLockTracker keeps a list of
viewpoints that have been locked by the current Operation. This allows us to ensure that
viewpoints are not locked multiple times, and also to assert that certain viewpoint(s)
have been locked before running code that requires those locks.
"""

from viewfinder.backend.db.operation import Operation


class ViewpointLockTracker(object):
  """Container to help track which viewpoints have locks acquired for them. This will help
  assert that we have the proper viewpoint locks before modifying them.
  """
  def __init__(self):
    self.viewpoint_lock_ids = set()

  @classmethod
  def AddViewpointId(cls, viewpoint_lock_id):
    """Adds a viewpoint id to the set on the current operation."""
    lock_tracker = ViewpointLockTracker._GetInstance()
    assert viewpoint_lock_id not in lock_tracker.viewpoint_lock_ids
    lock_tracker.viewpoint_lock_ids.add(viewpoint_lock_id)

  @classmethod
  def RemoveViewpointId(cls, viewpoint_lock_id):
    """Removes a viewpoint id from the set on the current operation."""
    lock_tracker = ViewpointLockTracker._GetInstance()
    assert viewpoint_lock_id in lock_tracker.viewpoint_lock_ids
    lock_tracker.viewpoint_lock_ids.remove(viewpoint_lock_id)

  @classmethod
  def HasViewpointId(cls, viewpoint_lock_id):
    """Returns true if the the viewpoint id is in the set on the current operation."""
    lock_tracker = ViewpointLockTracker._GetInstance()
    return viewpoint_lock_id in lock_tracker.viewpoint_lock_ids

  @classmethod
  def _GetInstance(cls):
    """Ensures that a viewpoint lock tracker has been created and attached to the current
    operation.
    """
    op = Operation.GetCurrent()
    lock_tracker = op.context.get('viewpoint_lock_tracker')
    if lock_tracker is None:
      lock_tracker = ViewpointLockTracker()
      op.context['viewpoint_lock_tracker'] = lock_tracker

    return lock_tracker
