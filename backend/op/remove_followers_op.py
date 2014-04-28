# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder RemoveFollowersOperation.

This operation removes followers from an existing viewpoint by adding the REMOVED + UNREVIVABLE
labels to the corresponding Follower records. A user may only remove himself, or other users
which he himself added within the last 7 days. The UNREVIVABLE label prevents the activity of
other followers from restoring access to the removed follower.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import json

from tornado import gen
from viewfinder.backend.base import constants, util
from viewfinder.backend.base.exceptions import LimitExceededError, NotFoundError, PermissionError
from viewfinder.backend.db.accounting import AccountingAccumulator
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.followed import Followed
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.lock import Lock
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation
from viewfinder.backend.resources.message.error_messages import CANNOT_REMOVE_FOLLOWERS, CANNOT_REMOVE_DEFAULT_FOLLOWER
from viewfinder.backend.resources.message.error_messages import CANNOT_REMOVE_OLD_FOLLOWER, CANNOT_REMOVE_THIS_FOLLOWER
from viewfinder.backend.resources.message.error_messages import VIEWPOINT_NOT_FOUND


class RemoveFollowersOperation(ViewfinderOperation):
  """The RemoveFollowers operation follows the four phase pattern described in the header of
  operation_map.py.
  """
  MAX_REMOVE_PERIOD = constants.SECONDS_PER_WEEK
  """A follower (besides yourself) can be removed only if added within last 7 days."""

  def __init__(self, client, act_dict, user_id, viewpoint_id, remove_ids):
    super(RemoveFollowersOperation, self).__init__(client)
    self._act_dict = act_dict
    self._user_id = user_id
    self._viewpoint_id = viewpoint_id
    self._remove_ids = remove_ids
    self._remove_id_set = set(remove_ids)

  @classmethod
  @gen.coroutine
  def Execute(cls, client, activity, user_id, viewpoint_id, remove_ids):
    """Entry point called by the operation framework."""
    yield RemoveFollowersOperation(client, activity, user_id, viewpoint_id, remove_ids)._RemoveFollowers()

  @gen.coroutine
  def _RemoveFollowers(self):
    """Orchestrates the remove followers operation by executing each of the phases in turn."""
    # Lock the viewpoint while removing followers.
    lock = yield gen.Task(Viewpoint.AcquireLock, self._client, self._viewpoint_id)
    try:
      yield self._Check()
      self._client.CheckDBNotModified()
      yield self._Update()
      yield self._Account()
      yield Operation.TriggerFailpoint(self._client)
      yield self._Notify()
    finally:
      yield gen.Task(Viewpoint.ReleaseLock, self._client, self._viewpoint_id, lock)

  @gen.coroutine
  def _Check(self):
    """Gathers pre-mutation information:
       1. Queries for existing followers and viewpoint.
       2. Checkpoints list of followers that need to have REMOVED label added.

       Validates the following:
       1. Viewpoint exists and is not a default viewpoint.
       2. Permission to modify viewpoint.
       3. Permission to remove the requested followers.
    """
    # Get all existing followers.
    self._followers, _ = yield gen.Task(Viewpoint.QueryFollowers,
                                        self._client,
                                        self._viewpoint_id,
                                        limit=Viewpoint.MAX_FOLLOWERS)

    # Get the viewpoint to be modified, along with the follower that is removing the users.
    # This state will not be changed by remove followers, and so doesn't need to be part of
    # the checkpoint.
    self._viewpoint, self._removing_follower = yield gen.Task(Viewpoint.QueryWithFollower,
                                                              self._client,
                                                              self._user_id,
                                                              self._viewpoint_id)

    # Raise error if viewpoint is not found.
    if self._viewpoint is None:
      raise NotFoundError(VIEWPOINT_NOT_FOUND, viewpoint_id=self._viewpoint_id)

    # Don't allow removal of followers from a default viewpoint.
    if self._viewpoint.IsDefault():
      raise PermissionError(CANNOT_REMOVE_DEFAULT_FOLLOWER)

    # Check permission to remove followers from the viewpoint.
    if self._removing_follower is None or not self._removing_follower.CanContribute():
      raise PermissionError(CANNOT_REMOVE_FOLLOWERS, user_id=self._user_id, viewpoint_id=self._viewpoint.viewpoint_id)

    # Check permission to remove each of the followers.
    for follower in self._followers:
      # Only consider followers to be removed.
      if follower.user_id not in self._remove_id_set:
        continue;

      # User can always remove himself from the viewpoint.
      if follower.user_id == self._user_id:
        continue

      # User can only remove other user if he originally added that user.
      if follower.adding_user_id != self._user_id:
        raise PermissionError(CANNOT_REMOVE_THIS_FOLLOWER,
                              remove_id=follower.user_id,
                              viewpoint_id=self._viewpoint.viewpoint_id)

      # Follower can only be removed if he was added less than 7 days ago.
      if util.GetCurrentTimestamp() - follower.timestamp > RemoveFollowersOperation.MAX_REMOVE_PERIOD:
        raise PermissionError(CANNOT_REMOVE_OLD_FOLLOWER,
                              remove_id=follower.user_id,
                              viewpoint_id=self._viewpoint.viewpoint_id)

    # Get followers to make un-revivable.
    self._unrevivable_followers = [follower for follower in self._followers
                                   if follower.user_id in self._remove_id_set and not follower.IsUnrevivable()]

    # Start populating the checkpoint if this the first time the operation has been run.
    if self._op.checkpoint is None:
      # Trim down remove set to include only those which are not already removed. Note that
      # some of the discarded followers still need to be made un-revivable.
      for follower in self._followers:
        if follower.IsRemoved():
          self._remove_id_set.discard(follower.user_id)

      # Set checkpoint.
      # The list of followers that need to be removed from the viewpoint need to be check-pointed  
      # because it is changed in the UPDATE phase. If we fail after UPDATE, but before NOTIFY,
      # we would not send correct notifications on retry.
      checkpoint = {'remove': list(self._remove_id_set)}
      yield self._op.SetCheckpoint(self._client, checkpoint)
    else:
      # Restore state from checkpoint.
      self._remove_id_set = set(self._op.checkpoint['remove'])

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Removes (and/or makes unrevivable) specified followers to the viewpoint.
    """
    for follower in self._unrevivable_followers:
      yield follower.RemoveViewpoint(self._client, allow_revive=False)

  @gen.coroutine
  def _Account(self):
    """Makes accounting changes:
       1. For removed followers.
    """
    acc_accum = AccountingAccumulator()

    # Make accounting changes for the removed followers.
    for follower_id in self._remove_id_set:
      yield acc_accum.RemoveViewpoint(self._client, follower_id, self._viewpoint_id)

    yield acc_accum.Apply(self._client)

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
       1. Notifies existing followers of the viewpoint that followers have been removed.
       2. Notifies removed followers that they have been removed from the viewpoint.
    """
    # Creates notifications for removal of followers of the viewpoint.
    yield NotificationManager.NotifyRemoveFollowers(self._client,
                                                    self._viewpoint_id,
                                                    self._followers,
                                                    self._remove_ids,
                                                    self._act_dict)
