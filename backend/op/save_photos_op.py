# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder SavePhotosOperation.

This operation saves photos from existing episodes to new episodes in the current user's
default viewpoint.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import json
import logging

from copy import copy, deepcopy
from functools import partial
from operator import itemgetter
from tornado import gen
from viewfinder.backend.base.exceptions import InvalidRequestError
from viewfinder.backend.db.accounting import AccountingAccumulator
from viewfinder.backend.db.asset_id import IdPrefix
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation
from viewfinder.backend.op.viewpoint_lock_tracker import ViewpointLockTracker


class SavePhotosOperation(ViewfinderOperation):
  """The SavePhotos operation follows the four phase pattern described in the header of
  operation_map.py.
  """
  def __init__(self, client, act_dict, user, viewpoint_ids, ep_dicts):
    super(SavePhotosOperation, self).__init__(client)
    self._act_dict = act_dict
    self._user = user
    self._viewpoint_ids = viewpoint_ids
    self._ep_dicts = ep_dicts
    self._lock_tracker = ViewpointLockTracker(client)

  @classmethod
  @gen.coroutine
  def Execute(cls, client, activity, user_id, viewpoint_ids=[], episodes=[]):
    """Entry point called by the operation framework."""
    user = yield gen.Task(User.Query, client, user_id, None)
    yield SavePhotosOperation(client, activity, user, viewpoint_ids, episodes)._SavePhotos()

  @gen.coroutine
  def _SavePhotos(self):
    """Orchestrates the save_photos operation by executing each of the phases in turn."""
    # Lock the viewpoint while sharing into it.
    try:
      yield self._lock_tracker.AcquireViewpointLock(self._user.private_vp_id)

      yield self._Check()
      self._client.CheckDBNotModified()
      yield self._Update()
      yield self._Account()
      yield Operation.TriggerFailpoint(self._client)
      yield self._Notify()
    finally:
      # Release all locks acquired while processing this operation.
      yield self._lock_tracker.ReleaseAllViewpointLocks()

  @gen.coroutine
  def _Check(self):
    """Gathers pre-mutation information:
       1. List of requested episodes and photos to save.
       2. Checkpoints list of episode and post ids that need to be (re)created.
       3. Acquires locks for all source viewpoints.

       Validates the following:
       1. Permissions to share from source episodes.
    """
    # Create save episode dicts from episodes and viewpoints in the request.
    self._save_ep_dicts = yield self._CreateSaveEpisodeDicts()

    # Validate episodes and posts to save.
    source_ep_posts_list = yield ViewfinderOperation._CheckCopySources('save',
                                                                       self._client,
                                                                       self._user.user_id,
                                                                       self._save_ep_dicts)

    # Get dicts describing the target episodes and posts.
    target_ep_ids = [ep_dict['new_episode_id'] for ep_dict in self._save_ep_dicts]
    self._target_ep_dicts = ViewfinderOperation._CreateCopyTargetDicts(self._op.timestamp,
                                                                       self._user.user_id,
                                                                       self._user.private_vp_id,
                                                                       source_ep_posts_list,
                                                                       target_ep_ids)

    # Lock all source viewpoints.
    for source_vp_id in set(episode.viewpoint_id for episode, posts in source_ep_posts_list):
      yield self._lock_tracker.AcquireViewpointLock(source_vp_id)

    # Start populating the checkpoint if this the first time the operation has been run.
    if self._op.checkpoint is None:
      # Get subset of target episodes and posts that need to be saved.
      self._new_ids = yield ViewfinderOperation._CheckCopyTargets('save',
                                                                  self._client,
                                                                  self._user.user_id,
                                                                  self._user.private_vp_id,
                                                                  self._target_ep_dicts)

      # Set checkpoint.
      # List of new episode/post ids need to be check-pointed because they may change in the
      # UPDATE phase. If we fail after UPDATE, but before NOTIFY, we would not send correct
      # notifications on retry.
      checkpoint = {'new': list(self._new_ids)}
      yield self._op.SetCheckpoint(self._client, checkpoint)
    else:
      # Restore state from checkpoint.
      self._new_ids = set(self._op.checkpoint['new'])

    raise gen.Return(True)

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Creates new episodes and posts.
    """
    # Create episode and posts that did not already exist at the beginning of the operation.
    yield self._CreateNewEpisodesAndPosts(self._target_ep_dicts, self._new_ids)

  @gen.coroutine
  def _Account(self):
    """Makes accounting changes:
       1. For new photos that were saved.
    """
    # Get list of the ids of all photos that were added.
    photo_ids = [Post.DeconstructPostId(id)[1] for id in self._new_ids if id.startswith(IdPrefix.Post)]

    acc_accum = AccountingAccumulator()

    # Make accounting changes for the new photos that were added.
    yield acc_accum.SavePhotos(self._client,
                               self._user.user_id,
                               self._user.private_vp_id,
                               photo_ids)

    yield acc_accum.Apply(self._client)

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
       1. Notifies all devices of the default viewpoint owner that new photos have been saved.
    """
    follower = yield gen.Task(Follower.Query, self._client, self._user.user_id, self._user.private_vp_id, None)
    yield NotificationManager.NotifySavePhotos(self._client,
                                               self._user.private_vp_id,
                                               follower,
                                               self._act_dict,
                                               self._save_ep_dicts)

  @gen.coroutine
  def _CreateSaveEpisodeDicts(self):
    """Creates a list of dicts describing the source and target episodes of the save. The
    episode dicts passed in the save_photos request are combined with episodes in any of the
    viewpoints passed in the save_photos request. Returns the list.
    """
    # Query episode ids from viewpoints given in the request, but skip those that are already in the request.
    vp_ep_ids = []
    skip_vp_ep_ids = set(ep_dict['existing_episode_id'] for ep_dict in self._ep_dicts)

    # Query photo_ids from viewpoint episodes.
    ep_ph_ids = {}

    @gen.coroutine
    def _VisitPosts(photo_ids, post):
      photo_ids.append(post.photo_id)

    @gen.coroutine
    def _VisitEpisodeKeys(episode_key):
      episode_id = episode_key.hash_key

      # Get list of episodes in the viewpoint that need a target episode id discovered/generated.
      if episode_id not in skip_vp_ep_ids:
        vp_ep_ids.append(episode_id)

      # For each episode in the viewpoint, get the complete list of photo ids in that episode.
      photo_ids = []
      yield gen.Task(Post.VisitRange, self._client, episode_id, None, None, partial(_VisitPosts, photo_ids))
      ep_ph_ids[episode_id] = photo_ids

    tasks = []
    for viewpoint_id in set(self._viewpoint_ids):
      query_expr = ('episode.viewpoint_id={id}', {'id': viewpoint_id})
      tasks.append(gen.Task(Episode.VisitIndexKeys, self._client, query_expr, _VisitEpisodeKeys))
    yield tasks

    # Allocate target ids for all episodes not given by the client.
    target_ep_ids = yield ViewfinderOperation._AllocateTargetEpisodeIds(self._client,
                                                                        self._user.user_id,
                                                                        self._user.webapp_dev_id,
                                                                        self._user.private_vp_id,
                                                                        vp_ep_ids)

    # Create save dicts for each of the viewpoint episodes to save.
    save_ep_dicts = {}
    for source_ep_id, target_ep_id in zip(vp_ep_ids, target_ep_ids):
      save_ep_dicts[target_ep_id] = {'existing_episode_id': source_ep_id,
                                     'new_episode_id': target_ep_id,
                                     'photo_ids': ep_ph_ids[source_ep_id]}

    # Now add the save dicts from the request, validating rules as we go.
    for ep_dict in self._ep_dicts:
      existing_ep_dict = save_ep_dicts.get(ep_dict['new_episode_id'], None)
      if existing_ep_dict is not None:
        if ep_dict['existing_episode_id'] != existing_ep_dict['existing_episode_id']:
          raise InvalidRequestError('Cannot save episodes "%s" and "%s" to same target episode "%s".' %
                                    (existing_ep_dict['existing_episode_id'],
                                     ep_dict['existing_episode_id'],
                                     ep_dict['new_episode_id']))

        existing_ep_dict['photo_ids'].extend(ep_dict['photo_ids'])
        existing_ep_dict['photo_ids'] = sorted(set(existing_ep_dict['photo_ids']))
      else:
        photo_ids = ep_dict['photo_ids']
        if ep_dict['existing_episode_id'] in ep_ph_ids:
          photo_ids.extend(ep_ph_ids[ep_dict['existing_episode_id']])

        save_ep_dicts[ep_dict['new_episode_id']] = {'existing_episode_id': ep_dict['existing_episode_id'],
                                                    'new_episode_id': ep_dict['new_episode_id'],
                                                    'photo_ids': sorted(set(photo_ids))}

    save_ep_dicts = [ep_dict for ep_dict in save_ep_dicts.itervalues()]
    save_ep_dicts.sort(key=itemgetter('new_episode_id'))
    raise gen.Return(save_ep_dicts)
