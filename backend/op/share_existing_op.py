# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder ShareExistingOperation.

This operation shares existing episodes and photos into an existing viewpoint.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import json
import logging

from copy import deepcopy
from tornado import gen
from viewfinder.backend.base.exceptions import InvalidRequestError, LimitExceededError, PermissionError
from viewfinder.backend.db.accounting import AccountingAccumulator
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.asset_id import IdPrefix
from viewfinder.backend.db.db_client import DBClient, DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation


class ShareExistingOperation(ViewfinderOperation):
  """The ShareExisting operation follows the four phase pattern described in the header of
  operation_map.py.
  """
  def __init__(self, client, act_dict, user_id, viewpoint_id, ep_dicts):
    super(ShareExistingOperation, self).__init__(client)
    self._act_dict = act_dict
    self._user_id = user_id
    self._viewpoint_id = viewpoint_id
    self._ep_dicts = ep_dicts

  @classmethod
  @gen.coroutine
  def Execute(cls, client, activity, user_id, viewpoint_id, episodes):
    """Entry point called by the operation framework."""
    yield ShareExistingOperation(client, activity, user_id, viewpoint_id, episodes)._ShareExisting()

  @gen.coroutine
  def _ShareExisting(self):
    """Orchestrates the share_existing operation by executing each of the phases in turn."""
    # Lock the viewpoint while sharing into it.
    lock = yield gen.Task(Viewpoint.AcquireLock, self._client, self._viewpoint_id)
    try:
      yield self._Check()
      self._client.CheckDBNotModified()
      yield self._Update()
      yield self._Account()
      yield Operation.TriggerFailpoint(self._client)
      yield self._Notify()

      # Trigger any save_photos operations for followers that have marked the viewpoint to be auto-saved.
      yield self._AutoSave()

    finally:
      yield gen.Task(Viewpoint.ReleaseLock, self._client, self._viewpoint_id, lock)

  @gen.coroutine
  def _Check(self):
    """Gathers pre-mutation information:
       1. Existing viewpoint and owner follower.
       2. Followers of the existing viewpoint.
       3. List of requested episodes and photos to share.
       4. Checkpoints list of episode and post ids that need to be (re)created.
       5. Checkpoints list of followers that need to be revived.
       6. Checkpoints boolean indicating whether cover photo needs to be set.

       Validates the following:
       1. Permissions to share from source episodes.
       2. Permission to share into existing viewpoint.
    """
    self._viewpoint, self._follower = yield gen.Task(Viewpoint.QueryWithFollower,
                                                     self._client,
                                                     self._user_id,
                                                     self._viewpoint_id)

    # Checks permission to share into viewpoint.
    if self._follower is None or not self._follower.CanContribute():
      raise PermissionError('User %d does not have permission to contribute to viewpoint "%s".' %
                            (self._user_id, self._viewpoint_id))
    assert self._viewpoint is not None, self._viewpoint_id

    # Get all existing followers.
    self._followers, _ = yield gen.Task(Viewpoint.QueryFollowers,
                                        self._client,
                                        self._viewpoint_id,
                                        limit=Viewpoint.MAX_FOLLOWERS)

    # Validate source episodes and posts and save the list for possible later use.
    self._source_ep_posts_list = yield ViewfinderOperation._CheckCopySources('share',
                                                                             self._client,
                                                                             self._user_id,
                                                                             self._ep_dicts)

    # Get dicts describing the target episodes and posts.
    target_ep_ids = [ep_dict['new_episode_id'] for ep_dict in self._ep_dicts]
    self._new_ep_dicts = ViewfinderOperation._CreateCopyTargetDicts(self._op.timestamp,
                                                                    self._user_id,
                                                                    self._viewpoint_id,
                                                                    self._source_ep_posts_list,
                                                                    target_ep_ids)

    # Start populating the checkpoint if this the first time the operation has been run.
    if self._op.checkpoint is None:
      # Get subset of target episodes and posts that need to be shared.
      self._new_ids = yield self._CheckCopyTargets('share',
                                                   self._client,
                                                   self._user_id,
                                                   self._viewpoint_id,
                                                   self._new_ep_dicts)

      # Get list of followers which have removed themselves from the viewpoint and will need to be revived.
      self._revive_follower_ids = self._GetRevivableFollowers(self._followers)

      # Check whether a cover photo needs to be set on the viewpoint.
      self._need_cover_photo = not self._viewpoint.IsDefault() and not self._viewpoint.IsCoverPhotoSet()

      # Set checkpoint.
      # List of new episode/post ids and followers to revive need to be check-pointed because they may change
      # in the UPDATE phase. If we fail after UPDATE, but before NOTIFY, we would not send correct notifications
      # on retry.
      checkpoint = {'new': list(self._new_ids),
                    'revive': self._revive_follower_ids,
                    'cover': self._need_cover_photo}
      yield self._op.SetCheckpoint(self._client, checkpoint)
    else:
      # Restore state from checkpoint.
      self._new_ids = set(self._op.checkpoint['new'])
      self._revive_follower_ids = self._op.checkpoint['revive']
      self._need_cover_photo = self._op.checkpoint['cover']

    raise gen.Return(True)

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Revives any followers that have removed the viewpoint.
       2. Creates new episodes and posts.
       3. Creates cover photo, if needed.
    """
    # Revive any REMOVED followers.
    yield gen.Task(Follower.ReviveRemovedFollowers, self._client, self._followers)

    # Create episode and posts that did not exist at the beginning of the operation.
    yield self._CreateNewEpisodesAndPosts(self._new_ep_dicts, self._new_ids)

    # Create cover photo if one is needed.
    if self._need_cover_photo:
      self._viewpoint.cover_photo = Viewpoint.SelectCoverPhotoFromEpDicts(self._new_ep_dicts)
      yield gen.Task(self._viewpoint.Update, self._client)

  @gen.coroutine
  def _Account(self):
    """Makes accounting changes:
       1. For revived followers.
       2. For new photos that were shared.
    """
    # Get list of the ids of all photos that were added.
    photo_ids = [Post.DeconstructPostId(id)[1] for id in self._new_ids if id.startswith(IdPrefix.Post)]

    acc_accum = AccountingAccumulator()

    # Make accounting changes for any revived followers.
    yield acc_accum.ReviveFollowers(self._client, self._viewpoint_id, self._revive_follower_ids)

    # Make accounting changes for the new photos that were added.
    yield acc_accum.SharePhotos(self._client,
                                self._user_id,
                                self._viewpoint_id,
                                photo_ids,
                                [follower.user_id for follower in self._followers
                                 if not follower.IsRemoved()])

    yield acc_accum.Apply(self._client)

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
       1. Notifies removed followers that conversation has new activity.
       2. Notifies existing followers of the viewpoint that photos have been added.
    """
    # Creates notifications for any revived followers.
    yield NotificationManager.NotifyReviveFollowers(self._client,
                                                    self._viewpoint_id,
                                                    self._revive_follower_ids,
                                                    self._op.timestamp)

    # Notify followers of the changes made by the share operation.
    yield NotificationManager.NotifyShareExisting(self._client,
                                                  self._viewpoint_id,
                                                  self._followers,
                                                  self._act_dict,
                                                  self._ep_dicts,
                                                  self._need_cover_photo)

  @gen.coroutine
  def _AutoSave(self):
    """For each follower that has enabled auto-save for this viewpoint, trigger save_photos
    operation that will save the shared photos to their default viewpoint.
    """
    # Get ids of all the source episodes that will be provided to save_photos.
    source_ep_ids = [ep_dict['new_episode_id'] for ep_dict in self._ep_dicts]

    for follower in self._followers:
      # Skip follower if he did not mark this viewpoint for auto-saving.
      if not follower.ShouldAutoSave():
        continue

      # Skip follower if he is removed from the conversation.
      if follower.IsRemoved():
        continue

      follower_user = yield gen.Task(User.Query, self._client, follower.user_id, None)

      # Skip follower if he is the sharer, and is sharing only episodes from his default viewpoint.
      if follower_user.user_id == self._user_id:
        if all(source_episode.viewpoint_id == follower_user.private_vp_id
          for source_episode, posts in self._source_ep_posts_list):
            continue

      # Allocate ids for save_photos operation and activity.
      first_id = yield gen.Task(User.AllocateAssetIds, self._client, follower.user_id, 2)
      op_id = Operation.ConstructOperationId(follower_user.webapp_dev_id, first_id)
      activity_id = Activity.ConstructActivityId(self._act_dict['timestamp'],
                                                 follower_user.webapp_dev_id,
                                                 first_id + 1)

      # Generate ids for any target episodes that don't already exist.
      target_ep_ids = yield ViewfinderOperation._AllocateTargetEpisodeIds(self._client,
                                                                          follower.user_id,
                                                                          follower_user.webapp_dev_id,
                                                                          follower_user.private_vp_id,
                                                                          source_ep_ids)

      # Create target episode dicts expected by the SavePhotos op.
      target_eps_list = []
      for ep_dict, target_ep_id in zip(self._ep_dicts, target_ep_ids):
        target_eps_list.append({'existing_episode_id': ep_dict['new_episode_id'],
                                'new_episode_id': target_ep_id,
                                'photo_ids': ep_dict['photo_ids']})

      save_photos_dict = {'headers': {'op_id': op_id, 'op_timestamp': self._op.timestamp},
                          'user_id': follower.user_id,
                          'activity': {'activity_id': activity_id, 'timestamp': self._act_dict['timestamp']},
                          'episodes': target_eps_list}

      # Create the save_photos op for this user. Use the raw DBClient instance since self._client
      # is wrapped with OpMgrDBClient. 
      yield gen.Task(Operation.CreateAndExecute,
                     DBClient.Instance(),
                     follower.user_id,
                     follower_user.webapp_dev_id,
                     'SavePhotosOperation.Execute',
                     save_photos_dict)
