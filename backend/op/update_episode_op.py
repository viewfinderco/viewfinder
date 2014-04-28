# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder UpdateEpisodeOperation.

This operation updates episode metadata.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import json

from tornado import gen
from viewfinder.backend.base.exceptions import InvalidRequestError, PermissionError
from viewfinder.backend.db.accounting import AccountingAccumulator
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation


class UpdateEpisodeOperation(ViewfinderOperation):
  """The UpdateEpisode operation follows the four phase pattern described in the header of
  operation_map.py.
  """
  def __init__(self, client, act_dict, user_id, ep_dict):
    super(UpdateEpisodeOperation, self).__init__(client)
    self._act_dict = act_dict
    self._user_id = user_id
    self._ep_dict = ep_dict
    self._episode_id = ep_dict['episode_id']

  @classmethod
  @gen.coroutine
  def Execute(cls, client, activity, user_id, episode):
    """Entry point called by the operation framework."""
    yield UpdateEpisodeOperation(client, activity, user_id, episode)._UpdateEpisode()

  @gen.coroutine
  def _UpdateEpisode(self):
    """Orchestrates the update_episode operation by executing each of the phases in turn."""
    # Get the viewpoint_id from the episode (which must exist).
    self._episode = yield gen.Task(Episode.Query, self._client, self._episode_id, None, must_exist=False)
    if not self._episode:
      raise InvalidRequestError('Episode "%s" does not exist and so cannot be updated.' % self._episode_id)
    self._viewpoint_id = self._episode.viewpoint_id

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
       1. Queries for existing followers.
       2. Checkpoints list of followers that need to be revived.

       Validates the following:
       1. Permission to update episode metadata.
    """
    if self._episode.user_id != self._user_id:
      raise PermissionError('User id of episode "%s" does not match requesting user.' % self._episode_id)

    # Get all existing followers.
    self._followers, _ = yield gen.Task(Viewpoint.QueryFollowers,
                                        self._client,
                                        self._viewpoint_id,
                                        limit=Viewpoint.MAX_FOLLOWERS)

    # Check for permission to modify the viewpoint.
    owner_follower = [follower for follower in self._followers if follower.user_id == self._user_id]
    if not owner_follower or not owner_follower[0].CanContribute():
      raise PermissionError('User %d does not have permission to contribute to viewpoint "%s".' %
                            (self._user_id, self._viewpoint_id))

    # Start populating the checkpoint if this the first time the operation has been run.
    if self._op.checkpoint is None:
      # Get list of followers which have removed themselves from the viewpoint and will need to be revived.
      self._revive_follower_ids = self._GetRevivableFollowers(self._followers)

      # Set checkpoint.
      # Followers to revive need to be check-pointed because they are changed in the UPDATE phase.
      # If we fail after UPDATE, but before NOTIFY, we would not send correct notifications on retry.
      checkpoint = {'revive': self._revive_follower_ids}
      yield self._op.SetCheckpoint(self._client, checkpoint)
    else:
      # Restore state from checkpoint.
      self._revive_follower_ids = self._op.checkpoint['revive']

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Revives any followers that have removed the viewpoint.
       2. Updates the episode metadata.
    """
    # Revive any REMOVED followers.
    yield gen.Task(Follower.ReviveRemovedFollowers, self._client, self._followers)

    # Update the episode metadata.
    yield self._episode.UpdateExisting(self._client, **self._ep_dict)

  @gen.coroutine
  def _Account(self):
    """Makes accounting changes:
       1. For revived followers.
    """
    acc_accum = AccountingAccumulator()
    yield acc_accum.ReviveFollowers(self._client, self._viewpoint_id, self._revive_follower_ids)
    yield acc_accum.Apply(self._client)

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
       1. Notifies removed followers that conversation has new activity.
       2. Notifies existing followers of the viewpoint that episode metadata has changed.
    """
    # Creates notifications for any revived followers.
    yield NotificationManager.NotifyReviveFollowers(self._client,
                                                    self._viewpoint_id,
                                                    self._revive_follower_ids,
                                                    self._op.timestamp)

    # Notify followers that episode metadata has been updated.
    yield NotificationManager.NotifyUpdateEpisode(self._client,
                                                  self._viewpoint_id,
                                                  self._followers,
                                                  self._act_dict,
                                                  self._ep_dict)
