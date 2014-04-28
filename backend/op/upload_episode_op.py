# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder UploadEpisodeOperation.

This operation creates metadata for a new episode and photos in the current user's default
viewpoint. The user's device will then upload the photos to S3.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import json
import logging

from tornado import gen
from viewfinder.backend.base import util
from viewfinder.backend.base.exceptions import InvalidRequestError, PermissionError
from viewfinder.backend.db.accounting import AccountingAccumulator
from viewfinder.backend.db.asset_id import IdPrefix
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user import User
from viewfinder.backend.db.user_photo import UserPhoto
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation


class UploadEpisodeOperation(ViewfinderOperation):
  """The UploadEpisode operation follows the four phase pattern described in the header of
  operation_map.py.
  """
  def __init__(self, client, act_dict, user, ep_dict, ph_dicts):
    super(UploadEpisodeOperation, self).__init__(client)
    self._act_dict = act_dict
    self._user = user
    self._ep_dict = ep_dict
    self._ep_dict['user_id'] = user.user_id
    self._ep_dict['viewpoint_id'] = user.private_vp_id
    self._ep_dict['publish_timestamp'] = self._op.timestamp
    self._ph_dicts = ph_dicts
    self._episode_id = ep_dict['episode_id']

    # Fixup photo metadata.
    for ph_dict in self._ph_dicts:
      ph_dict['user_id'] = self._user.user_id
      ph_dict['episode_id'] = self._episode_id

  @classmethod
  @gen.coroutine
  def Execute(cls, client, activity, user_id, episode, photos):
    """Entry point called by the operation framework."""
    user = yield gen.Task(User.Query, client, user_id, None)
    yield UploadEpisodeOperation(client, activity, user, episode, photos)._UploadEpisode()

  @gen.coroutine
  def _UploadEpisode(self):
    """Orchestrates the upload_episode operation by executing each of the phases in turn."""
    # Lock the viewpoint while sharing into it.
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
       1. Episode and photos to upload.
       2. Checkpoints list of episode and photo ids that need to be (re)created.
       3. Checkpoints whether to attempt to set episode location and placemark from photos.

       Validates the following:
       1. Permissions to upload to the given episode.
       2. Each photo can be uploaded into at most one episode.
    """
    # Get existing episode, if it exists.
    self._episode = yield gen.Task(Episode.Query,
                                   self._client,
                                   self._episode_id,
                                   None,
                                   must_exist=False)

    if self._episode is not None and self._episode.parent_ep_id != None:
      raise InvalidRequestError('Cannot upload photos into an episode that was saved.')

    # Query for all photos in a batch.
    photo_keys = [DBKey(ph_dict['photo_id'], None) for ph_dict in self._ph_dicts]
    photos = yield gen.Task(Photo.BatchQuery,
                            self._client,
                            photo_keys,
                            None,
                            must_exist=False)

    # Start populating the checkpoint if this the first time the operation has been run.
    if self._op.checkpoint is None:
      # Gather list of ids of new episode and photos that need to be created.
      self._new_ids = set()
      if self._episode is None:
        self._new_ids.add(self._episode_id)

      for photo, ph_dict in zip(photos, self._ph_dicts):
        if photo is None:
          self._new_ids.add(ph_dict['photo_id'])
        elif photo.episode_id != self._episode_id:
          raise InvalidRequestError('Cannot upload photo "%s" into multiple episodes.' % ph_dict['photo_id'])

      # Determine whether episode location/placemark needs to be set.
      self._set_location = self._episode is None or self._episode.location is None
      self._set_placemark = self._episode is None or self._episode.placemark is None

      # Set checkpoint.
      # List of new episode/photo ids, and whether to set location/placemark need to be check-
      # pointed because they may change in the UPDATE phase. If we fail after UPDATE, but
      # before NOTIFY, we would not send correct notifications on retry.
      checkpoint = {'new': list(self._new_ids),
                    'location': self._set_location,
                    'placemark': self._set_placemark}
      yield self._op.SetCheckpoint(self._client, checkpoint)
    else:
      # Restore state from checkpoint.
      self._new_ids = set(self._op.checkpoint['new'])
      self._set_location = self._op.checkpoint['location']
      self._set_placemark = self._op.checkpoint['placemark']

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Creates episode if it did not exist, or sets episode's location/placemark.
       2. Creates posts that did not previously exist.
       3. Creates photos that did not previously exist.
       4. Updates photo MD5 values if they were given in a re-upload.
    """
    # Set episode location/placemark.
    if self._set_location or self._set_placemark:
      for ph_dict in self._ph_dicts:
        if 'location' not in self._ep_dict and 'location' in ph_dict:
          self._ep_dict['location'] = ph_dict['location']
        if 'placemark' not in self._ep_dict and 'placemark' in ph_dict:
          self._ep_dict['placemark'] = ph_dict['placemark']

    # Create new episode if it did not exist at the beginning of the operation.
    if self._episode_id in self._new_ids:
      yield gen.Task(Episode.CreateNew, self._client, **self._ep_dict)
    # Update existing episode's location/placemark.
    elif self._set_location or self._set_placemark:
      yield gen.Task(self._episode.UpdateExisting,
                     self._client,
                     location=self._ep_dict.get('location', None),
                     placemark=self._ep_dict.get('placemark', None))

    # Create posts and photos that did not exist at the beginning of the operation.
    tasks = []
    for ph_dict in self._ph_dicts:
      # Only create post, user_photo and photo if photo did not exist at the beginning of the operation.
      if ph_dict['photo_id'] in self._new_ids:
        # Create user photo record if asset keys were specified.
        asset_keys = ph_dict.pop('asset_keys', None)
        if asset_keys is not None:
          tasks.append(UserPhoto.CreateNew(self._client,
                                           user_id=self._user.user_id,
                                           photo_id=ph_dict['photo_id'],
                                           asset_keys=asset_keys))

        tasks.append(Photo.CreateNew(self._client, **ph_dict))
        tasks.append(Post.CreateNew(self._client, episode_id=self._episode_id, photo_id=ph_dict['photo_id']))
      else:
        # Update the photo if any MD5 attributes need to be overwritten. This is allowed if the photo image
        # has not yet been uploaded. This can happen if the MD5 value has changed on the client due to an IOS
        # upgrade.
        md5_dict = {'photo_id': ph_dict['photo_id']}
        util.SetIfNotNone(md5_dict, 'tn_md5', ph_dict['tn_md5'])
        util.SetIfNotNone(md5_dict, 'med_md5', ph_dict['med_md5'])
        util.SetIfNotNone(md5_dict, 'full_md5', ph_dict['full_md5'])
        util.SetIfNotNone(md5_dict, 'orig_md5', ph_dict['orig_md5'])
        if md5_dict:
          yield Photo.UpdateExisting(self._client, **md5_dict)

    yield tasks

  @gen.coroutine
  def _Account(self):
    """Makes accounting changes:
       1. For new photos that were uploaded.
    """
    # Get list of photos that were added by this operation.
    new_ph_dicts = [ph_dict for ph_dict in self._ph_dicts if ph_dict['photo_id'] in self._new_ids]

    acc_accum = AccountingAccumulator()

    # Make accounting changes for the new photos that were added.
    yield acc_accum.UploadEpisode(self._client, self._user.user_id, self._user.private_vp_id, new_ph_dicts)

    yield acc_accum.Apply(self._client)

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
       1. Notifies all devices of the default viewpoint owner that new photos have been uploaded.
    """
    follower = yield gen.Task(Follower.Query, self._client, self._user.user_id, self._user.private_vp_id, None)
    yield NotificationManager.NotifyUploadEpisode(self._client,
                                                  self._user.private_vp_id,
                                                  follower,
                                                  self._act_dict,
                                                  self._ep_dict,
                                                  self._ph_dicts)
