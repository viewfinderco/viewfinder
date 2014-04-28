# -*- coding: utf-8 -*-
# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder CreateProspectiveOperation.

This operation creates a prospective (un-registered) user, along with the new user's identity,
default viewpoint, initial account settings, etc.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import json

from tornado import gen, options
from viewfinder.backend.base import util
from viewfinder.backend.db.accounting import AccountingAccumulator
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.analytics import Analytics
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.lock import Lock
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation
from viewfinder.backend.www import system_users


class CreateProspectiveOperation(ViewfinderOperation):
  """The CreateProspective operation expects the caller to allocate the new user's id and
  web device id. The caller is also responsible for ensuring that the user does not yet
  exist.
  """
  _ASSET_ID_COUNT = 24
  """Number of asset ids that will be allocated for the welcome conversation."""

  _UPDATE_SEQ_COUNT = 13
  """Number of viewpoint updates that will be made for the welcome conversation."""

  def __init__(self, client, new_user_id, webapp_dev_id, identity_key, reason=None):
    super(CreateProspectiveOperation, self).__init__(client)
    self._new_user_id = new_user_id
    self._webapp_dev_id = webapp_dev_id
    self._identity_key = identity_key
    self._reason = reason

  @classmethod
  @gen.coroutine
  def Execute(cls, client, user_id, webapp_dev_id, identity_key, reason=None):
    """Entry point called by the operation framework."""
    yield CreateProspectiveOperation(client, user_id, webapp_dev_id, identity_key, reason=reason)._CreateProspective()

  @gen.coroutine
  def _CreateProspective(self):
    """Create the prospective user and identity."""
    self._new_user, _ = yield User.CreateProspective(self._client,
                                                     self._new_user_id,
                                                     self._webapp_dev_id,
                                                     self._identity_key,
                                                     self._op.timestamp)

    # If system user is defined, then create the welcome conversation.
    # For now, add a check to ensure the welcome conversation is not created in production.
    if system_users.NARRATOR_USER is not None:
      # Checkpoint the allocated asset id range used to create the welcome conversation.
      if self._op.checkpoint is None:
        # NOTE: Asset ids are allocated from the new user's ids. This is different than the
        #       usual practice of allocating from the sharer's ids. 
        self._unique_id_start = yield gen.Task(User.AllocateAssetIds,
                                               self._client,
                                               self._new_user_id,
                                               CreateProspectiveOperation._ASSET_ID_COUNT)

        checkpoint = {'id': self._unique_id_start}
        yield self._op.SetCheckpoint(self._client, checkpoint)
      else:
        self._unique_id_start = self._op.checkpoint['id']

      yield self._CreateWelcomeConversation()

    # Add an analytics entry for this user.
    analytics = Analytics.Create(entity='us:%d' % self._new_user_id,
                                 type=Analytics.USER_CREATE_PROSPECTIVE,
                                 timestamp=self._op.timestamp,
                                 payload=self._reason)
    yield gen.Task(analytics.Update, self._client)

    yield Operation.TriggerFailpoint(self._client)

  @gen.coroutine
  def _CreateWelcomeConversation(self):
    """Creates the welcome conversation at the db level. Operations are not used in order
    to avoid creating notifications, sending alerts, taking locks, running nested operations,
    etc.
    """
    from viewfinder.backend.www.system_users import NARRATOR_USER
    from viewfinder.backend.www.system_users import NARRATOR_UPLOAD_PHOTOS, NARRATOR_UPLOAD_PHOTOS_2, NARRATOR_UPLOAD_PHOTOS_3

    # Accumulate accounting changes.
    self._acc_accum = AccountingAccumulator()

    self._unique_id = self._unique_id_start
    self._update_seq = 1

    # Create the viewpoint.
    self._viewpoint_id = Viewpoint.ConstructViewpointId(self._new_user.webapp_dev_id, self._unique_id)
    self._unique_id += 1
    initial_follower_ids = [self._new_user.user_id]
    viewpoint, followers = yield Viewpoint.CreateNewWithFollowers(self._client,
                                                                  follower_ids=initial_follower_ids,
                                                                  user_id=NARRATOR_USER.user_id,
                                                                  viewpoint_id=self._viewpoint_id,
                                                                  type=Viewpoint.SYSTEM,
                                                                  title='Welcome...',
                                                                  timestamp=self._op.timestamp)

    # Narrator creates and introduces the conversation.
    yield self._CreateActivity(NARRATOR_USER,
                               self._op.timestamp - 60,
                               Activity.CreateShareNew,
                               ep_dicts=[],
                               follower_ids=initial_follower_ids)

    yield self._PostComment(NARRATOR_USER,
                            self._op.timestamp - 60,
                            'Welcome to Viewfinder, a new way to privately share photos with your friends.')

    # Narrator shares photos.
    yield self._PostComment(NARRATOR_USER,
                            self._op.timestamp - 59,
                            'Select as many photos as you want to share with exactly who you want.')

    photo_ids = [ph_dict['photo_id'] for ph_dict in NARRATOR_UPLOAD_PHOTOS['photos']]
    episode = yield self._CreateEpisodeWithPosts(NARRATOR_USER,
                                                 NARRATOR_UPLOAD_PHOTOS['episode']['episode_id'],
                                                 NARRATOR_UPLOAD_PHOTOS['photos'])
    yield self._CreateActivity(NARRATOR_USER,
                               self._op.timestamp - 58,
                               Activity.CreateShareExisting,
                               ep_dicts=[{'new_episode_id': episode.episode_id, 'photo_ids': photo_ids}])

    # Set cover photo on viewpoint now that episode id is known.
    viewpoint.cover_photo = {'episode_id': episode.episode_id,
                             'photo_id': NARRATOR_UPLOAD_PHOTOS['photos'][0]['photo_id']}
    yield gen.Task(viewpoint.Update, self._client)

    yield self._PostComment(NARRATOR_USER,
                            self._op.timestamp - 56,
                            'Your friends can also add photos to the conversation, '
                            'creating unique collaborative albums.')

    yield self._PostComment(NARRATOR_USER,
                            self._op.timestamp - 55,
                            'You can add as many photos, messages and friends as you want to the conversation, '
                            'leading to a memorable shared experience.')

    # Narrator shares more photos.
    photo_ids = [ph_dict['photo_id'] for ph_dict in NARRATOR_UPLOAD_PHOTOS_2['photos']]
    episode = yield self._CreateEpisodeWithPosts(NARRATOR_USER,
                                                 NARRATOR_UPLOAD_PHOTOS_2['episode']['episode_id'],
                                                 NARRATOR_UPLOAD_PHOTOS_2['photos'])
    yield self._CreateActivity(NARRATOR_USER,
                               self._op.timestamp - 54,
                               Activity.CreateShareExisting,
                               ep_dicts=[{'new_episode_id': episode.episode_id, 'photo_ids': photo_ids}])

    # Single-photo comment.
    yield self._PostComment(NARRATOR_USER,
                            self._op.timestamp - 53,
                            'Hold and press on photos to comment on specific pics.',
                            asset_id=NARRATOR_UPLOAD_PHOTOS_2['photos'][1]['photo_id'])

    # Narrator rambles on for a while.
    yield self._PostComment(NARRATOR_USER,
                            self._op.timestamp - 52,
                            'Use mobile #\'s or email addresses to add new people if they\'re not yet on Viewfinder.');

    # Narrator shares more photos.
    photo_ids = [ph_dict['photo_id'] for ph_dict in NARRATOR_UPLOAD_PHOTOS_3['photos']]
    episode = yield self._CreateEpisodeWithPosts(NARRATOR_USER,
                                                 NARRATOR_UPLOAD_PHOTOS_3['episode']['episode_id'],
                                                 NARRATOR_UPLOAD_PHOTOS_3['photos'])
    yield self._CreateActivity(NARRATOR_USER,
                               self._op.timestamp - 51,
                               Activity.CreateShareExisting,
                               ep_dicts=[{'new_episode_id': episode.episode_id, 'photo_ids': photo_ids}])


    # Conclusion.
    yield self._PostComment(NARRATOR_USER,
                            self._op.timestamp - 50,
                            'Viewfinder is perfect for vacations, weddings, or any shared experience where you want '
                            'to share photos without posting them for everyone to see.')

    yield self._PostComment(NARRATOR_USER,
                            self._op.timestamp - 49,
                            'Start sharing now.')

    # Validate that we allocated enough ids and counted update_seq properly.
    assert self._unique_id == self._unique_id_start + CreateProspectiveOperation._ASSET_ID_COUNT, self._unique_id
    assert self._update_seq == CreateProspectiveOperation._UPDATE_SEQ_COUNT, self._update_seq

    # Set update_seq on the new viewpoint.
    viewpoint.update_seq = self._update_seq
    yield gen.Task(viewpoint.Update, self._client)

    # Remove this viewpoint for all sample users so that accounting will be correct (also in case
    # we want to sync a device to Nick's account and see if new users are trying to chat). Also
    # update viewed_seq so that entire conversation is "read" for each sample user.
    for follower in followers:
      if follower.user_id != self._new_user.user_id:
        follower.viewed_seq = viewpoint.update_seq
        yield follower.RemoveViewpoint(self._client)

    # Commit accounting changes.
    yield self._acc_accum.Apply(self._client)

  @gen.coroutine
  def _CreateActivity(self, sharer_user, timestamp, activity_func, **kwargs):
    """Creates an activity by invoking "activity_func" with the given args."""
    activity_id = Activity.ConstructActivityId(timestamp, self._new_user.webapp_dev_id, self._unique_id)
    self._unique_id += 1
    activity = yield activity_func(self._client,
                                   sharer_user.user_id,
                                   self._viewpoint_id,
                                   activity_id,
                                   timestamp,
                                   update_seq=self._update_seq,
                                   **kwargs)
    self._update_seq += 1
    raise gen.Return(activity)

  @gen.coroutine
  def _CreateEpisodeWithPosts(self, sharer_user, parent_ep_id, ph_dicts):
    """Creates a new episode containing the given photos."""
    # Create the episode.
    episode_id = Episode.ConstructEpisodeId(self._op.timestamp, self._new_user.webapp_dev_id, self._unique_id)
    self._unique_id += 1
    episode = yield gen.Task(Episode.CreateNew,
                             self._client,
                             episode_id=episode_id,
                             parent_ep_id=parent_ep_id,
                             user_id=sharer_user.user_id,
                             viewpoint_id=self._viewpoint_id,
                             publish_timestamp=util.GetCurrentTimestamp(),
                             timestamp=self._op.timestamp,
                             location=ph_dicts[0].get('location', None),
                             placemark=ph_dicts[0].get('placemark', None))

    # Create the photos from photo dicts.
    photo_ids = [ph_dict['photo_id'] for ph_dict in ph_dicts]
    for photo_id in photo_ids:
      yield gen.Task(Post.CreateNew, self._client, episode_id=episode_id, photo_id=photo_id)

    # Update accounting, but only apply to the new user, since system users will remove
    # themselves from the viewpoint.
    yield self._acc_accum.SharePhotos(self._client,
                                      sharer_user.user_id,
                                      self._viewpoint_id,
                                      photo_ids,
                                      [self._new_user.user_id])

    # Update viewpoint shared by total for the sharing user.
    self._acc_accum.GetViewpointSharedBy(self._viewpoint_id, sharer_user.user_id).IncrementFromPhotoDicts(ph_dicts)

    raise gen.Return(episode)

  @gen.coroutine
  def _PostComment(self, sharer_user, timestamp, message, asset_id=None):
    """Creates a new comment and a corresponding activity."""
    comment_id = Comment.ConstructCommentId(timestamp, self._new_user.webapp_dev_id, self._unique_id)
    self._unique_id += 1
    comment = yield Comment.CreateNew(self._client,
                                      viewpoint_id=self._viewpoint_id,
                                      comment_id=comment_id,
                                      user_id=sharer_user.user_id,
                                      asset_id=asset_id,
                                      timestamp=timestamp,
                                      message=message)

    # Create post_comment activity.
    yield self._CreateActivity(sharer_user, timestamp, Activity.CreatePostComment, cm_dict={'comment_id': comment_id})

    raise gen.Return(comment)
