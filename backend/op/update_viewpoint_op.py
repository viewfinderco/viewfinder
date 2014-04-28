# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder UpdateViewpointOperation.

This operation updates viewpoint metadata.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import json

from tornado import gen
from viewfinder.backend.base import util
from viewfinder.backend.base.exceptions import InvalidRequestError, PermissionError
from viewfinder.backend.db.accounting import AccountingAccumulator
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation


class UpdateViewpointOperation(ViewfinderOperation):
  """The UpdateViewpoint operation follows the four phase pattern described in the header of
  operation_map.py.
  """
  def __init__(self, client, act_dict, user_id, vp_dict):
    super(UpdateViewpointOperation, self).__init__(client)
    self._act_dict = act_dict
    self._user_id = user_id
    self._vp_dict = vp_dict
    self._viewpoint_id = vp_dict['viewpoint_id']

  @classmethod
  @gen.coroutine
  def Execute(cls, client, activity, user_id, viewpoint):
    """Entry point called by the operation framework."""
    yield UpdateViewpointOperation(client, activity, user_id, viewpoint)._UpdateViewpoint()

  @gen.coroutine
  def _UpdateViewpoint(self):
    """Orchestrates the update viewpoint operation by executing each of the phases in turn."""
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
       2. Checkpoints list of followers that need to be revived.

       Validates the following:
       1. Permission to update viewpoint metadata.
    """
    # Get the viewpoint to be modified, along with the follower that is adding the additional users.
    # This state will not be changed by add followers, and so doesn't need to be part of the checkpoint.
    self._viewpoint, self._follower = yield gen.Task(Viewpoint.QueryWithFollower,
                                                     self._client,
                                                     self._user_id,
                                                     self._viewpoint_id)

    if self._viewpoint is None:
      raise InvalidRequestError('Viewpoint "%s" does not exist and so cannot be updated.' %
                                (self._viewpoint_id))

    if self._follower is None or not self._follower.CanContribute():
      raise PermissionError('User %d does not have permission to update viewpoint "%s".' %
                            (self._user_id, self._viewpoint_id))

    # Get all existing followers.
    self._followers, _ = yield gen.Task(Viewpoint.QueryFollowers,
                                        self._client,
                                        self._viewpoint_id,
                                        limit=Viewpoint.MAX_FOLLOWERS)

    # Check that cover photo exists in this viewpoint.
    cover_photo = self._vp_dict.get('cover_photo', None)
    if cover_photo is not None:
      if self._viewpoint.IsDefault():
        # cover_photo isn't supported creating default viewpoint.
        raise InvalidRequestError('A cover photo cannot be set on your library.')

      cover_photo_episode, cover_photo_post = yield [gen.Task(Episode.Query,
                                                              self._client,
                                                              cover_photo['episode_id'],
                                                              None,
                                                              must_exist=False),
                                                     gen.Task(Post.Query,
                                                              self._client,
                                                              cover_photo['episode_id'],
                                                              cover_photo['photo_id'],
                                                              None,
                                                              must_exist=False)]

      if cover_photo_post is None:
        raise InvalidRequestError('The requested cover photo does not exist.')

      if cover_photo_post.IsUnshared():
        raise PermissionError('The requested cover photo has been unshared.')

      if cover_photo_episode.viewpoint_id != self._viewpoint_id:
        raise InvalidRequestError('The requested cover photo is not in viewpoint "%s".' % self._viewpoint_id)

    # Start populating the checkpoint if this the first time the operation has been run.
    if self._op.checkpoint is None:
      # Get list of followers which have removed themselves from the viewpoint and will need to be revived.
      self._revive_follower_ids = self._GetRevivableFollowers(self._followers)

      # Get previous values of title and cover_photo, if they are being updated.
      self._prev_values = {}
      if 'title' in self._vp_dict:
        util.SetIfNotNone(self._prev_values, 'prev_title', self._viewpoint.title)
      if 'cover_photo' in self._vp_dict:
        util.SetIfNotNone(self._prev_values, 'prev_cover_photo', self._viewpoint.cover_photo)

      # Set checkpoint.
      # Followers to revive need to be check-pointed because they are changed in the UPDATE phase.
      # If we fail after UPDATE, but before NOTIFY, we would not send correct notifications on retry.
      checkpoint = {'revive': self._revive_follower_ids}
      util.SetIfNotEmpty(checkpoint, 'prev', self._prev_values)
      yield self._op.SetCheckpoint(self._client, checkpoint)
    else:
      # Restore state from checkpoint.
      self._revive_follower_ids = self._op.checkpoint['revive']
      self._prev_values = self._op.checkpoint.get('prev', {})

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Revives any followers that have removed the viewpoint.
       2. Updates the viewpoint metadata.
    """
    # Revive any REMOVED followers.
    yield gen.Task(Follower.ReviveRemovedFollowers, self._client, self._followers)

    # Update the viewpoint metadata.
    assert 'update_seq' not in self._vp_dict, self._vp_dict
    self._viewpoint.UpdateFromKeywords(**self._vp_dict)
    yield gen.Task(self._viewpoint.Update, self._client)

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
       2. Notifies existing followers of the viewpoint that metadata has changed.
    """
    # Creates notifications for any revived followers.
    yield NotificationManager.NotifyReviveFollowers(self._client,
                                                    self._viewpoint_id,
                                                    self._revive_follower_ids,
                                                    self._op.timestamp)

    # Notifies followers that viewpoint metadata has changed.
    yield NotificationManager.NotifyUpdateViewpoint(self._client,
                                                    self._vp_dict,
                                                    self._followers,
                                                    self._prev_values,
                                                    self._act_dict)
