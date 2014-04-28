# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder HidePhotosOperation.

This operation hides photos from appearing in the user's library or inbox.
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
from viewfinder.backend.db.user_post import UserPost
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation


class HidePhotosOperation(ViewfinderOperation):
  """The HidePhotos operation follows the four phase pattern described in the header of
  operation_map.py.
  """
  def __init__(self, client, user, ep_dicts):
    super(HidePhotosOperation, self).__init__(client)
    self._op = Operation.GetCurrent()
    self._client = client
    self._user = user
    self._ep_dicts = ep_dicts

  @classmethod
  @gen.coroutine
  def Execute(cls, client, user_id, episodes):
    """Entry point called by the operation framework."""
    user = yield gen.Task(User.Query, client, user_id, None)
    yield HidePhotosOperation(client, user, episodes)._HidePhotos()

  @gen.coroutine
  def _HidePhotos(self):
    """Orchestrates the hide photos operation by executing each of the phases in turn."""
    lock = yield gen.Task(Viewpoint.AcquireLock, self._client, self._user.private_vp_id)
    try:
      yield self._Check()
      self._client.CheckDBNotModified()
      yield self._Update()
      # No accounting changes for hide_photos.
      yield Operation.TriggerFailpoint(self._client)
      yield self._Notify()
    finally:
      yield gen.Task(Viewpoint.ReleaseLock, self._client, self._user.private_vp_id, lock)

  @gen.coroutine
  def _Check(self):
    """Gathers pre-mutation information:
       1. Queries for user posts.

       Validates the following:
       1. Permission to remove photos from episodes.
    """
    ep_ph_ids_list = [(ep_dict['episode_id'], ep_dict['photo_ids']) for ep_dict in self._ep_dicts]
    yield self._CheckEpisodePostAccess('hide', self._client, self._user.user_id, ep_ph_ids_list)

    self._user_post_keys = [DBKey(self._user.user_id, Post.ConstructPostId(ep_dict['episode_id'], photo_id))
                            for ep_dict in self._ep_dicts for photo_id in ep_dict['photo_ids']]
    self._user_posts = yield gen.Task(UserPost.BatchQuery,
                                      self._client,
                                      self._user_post_keys,
                                      None,
                                      must_exist=False)

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Add the HIDDEN label to the UserPost, creating it in the process if necessary.
    """
    for user_post, (user_id, post_id) in zip(self._user_posts, self._user_post_keys):
      if user_post is None:
        user_post = UserPost.CreateFromKeywords(user_id=user_id, post_id=post_id, timestamp=self._op.timestamp)

      if not user_post.IsHidden():
        user_post.labels.add(UserPost.HIDDEN)

      yield gen.Task(user_post.Update, self._client)

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
       1. Notify all of the user's devices that photos have been hidden.
    """
    yield NotificationManager.NotifyHidePhotos(self._client, self._user.user_id, self._ep_dicts)
