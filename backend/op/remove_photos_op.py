# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder RemovePhotosOperation.

This operation removes photos from the personal library or inbox view of the user. The posts
are no longer accessible to the user.
"""

__authors__ = ['mike@emailscrubbed.com (Mike Purtell)',
               'andy@emailscrubbed.com (Andy Kimball)']

import json

from tornado import gen
from viewfinder.backend.base.exceptions import PermissionError
from viewfinder.backend.db.accounting import AccountingAccumulator
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation
from viewfinder.backend.resources.message.error_messages import INVALID_REMOVE_PHOTOS_VIEWPOINT


class RemovePhotosOperation(ViewfinderOperation):
  """The RemovePhotos operation follows the four phase pattern described in the header of
  operation_map.py.
  """
  def __init__(self, client, user, ep_dicts):
    super(RemovePhotosOperation, self).__init__(client)
    self._op = Operation.GetCurrent()
    self._client = client
    self._user = user
    self._ep_dicts = ep_dicts

  @classmethod
  @gen.coroutine
  def Execute(cls, client, user_id, episodes):
    """Entry point called by the operation framework."""
    user = yield gen.Task(User.Query, client, user_id, None)
    yield RemovePhotosOperation(client, user, episodes)._RemovePhotos()

  @gen.coroutine
  def _RemovePhotos(self):
    """Orchestrates the remove_photos operation by executing each of the phases in turn."""
    lock = yield gen.Task(Viewpoint.AcquireLock, self._client, self._user.private_vp_id)
    try:
      yield self._Check()
      self._client.CheckDBNotModified()
      yield self._Update()
      yield self._Account()
      yield Operation.TriggerFailpoint(self._client)
      yield self._Notify()
    finally:
      yield gen.Task(Viewpoint.ReleaseLock, self._client, self._user.private_vp_id, lock)

  @gen.coroutine
  def _Check(self):
    """Gathers pre-mutation information:
       1. Queries for episodes.
       2. Queries for user posts.
       3. Checkpoints list of post ids that need to be removed.

       Validates the following:
       1. Permission to remove photos from episodes.
       2. Photos cannot be removed from shared viewpoints.
    """
    ep_ph_ids_list = [(ep_dict['episode_id'], ep_dict['photo_ids']) for ep_dict in self._ep_dicts]
    self._ep_posts_list = yield self._CheckEpisodePostAccess('remove',
                                                             self._client,
                                                             self._user.user_id,
                                                             ep_ph_ids_list)

    for episode, post in self._ep_posts_list:
      if episode.viewpoint_id != self._user.private_vp_id:
        raise PermissionError(INVALID_REMOVE_PHOTOS_VIEWPOINT, viewpoint_id=episode.viewpoint_id)

    if self._op.checkpoint is None:
      # Get subset of photos that need to be removed.
      self._remove_ids = set(Post.ConstructPostId(episode.episode_id, post.photo_id)
                             for episode, posts in self._ep_posts_list
                             for post in posts
                             if not post.IsRemoved())

      # Set checkpoint.
      # List of post ids to remove need to be check-pointed because they will change in the
      # UPDATE phase. If we fail after UPDATE, but before NOTIFY, we would not send correct
      # notifications on retry.
      yield self._op.SetCheckpoint(self._client, {'remove': list(self._remove_ids)})
    else:
      self._remove_ids = set(self._op.checkpoint['remove'])

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Add the REMOVED label to the post.
    """
    for episode, posts in self._ep_posts_list:
      for post in posts:
        post.labels.add(Post.REMOVED)
        yield gen.Task(post.Update, self._client)

  @gen.coroutine
  def _Account(self):
    """Makes accounting changes:
       1. Decrease user accounting by size of removed photos.
    """
    # Get list of the ids of all photos that were removed.
    photo_ids = [Post.DeconstructPostId(post_id)[1] for post_id in self._remove_ids]

    acc_accum = AccountingAccumulator()
    yield acc_accum.RemovePhotos(self._client, self._user.user_id, self._user.private_vp_id, photo_ids)
    yield acc_accum.Apply(self._client)

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
       1. Notify all of the user's devices that photos have been removed from the viewpoint.
    """
    yield NotificationManager.NotifyRemovePhotos(self._client, self._user.user_id, self._ep_dicts)
