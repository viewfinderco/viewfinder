# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder ShareNewOperation.

This operation creates a new viewpoint and adds a set of contacts to it as followers. If a
contact is not yet a Viewfinder user, we create a prospective user and link the contact to
that. We then share episodes and photos into the new viewpoint.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import json
import logging

from copy import deepcopy
from tornado import gen
from viewfinder.backend.base.exceptions import InvalidRequestError, LimitExceededError, PermissionError
from viewfinder.backend.db.accounting import AccountingAccumulator
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation


class ShareNewOperation(ViewfinderOperation):
  """The ShareNew operation follows the four phase pattern described in the header of
  operation_map.py.
  """
  def __init__(self, client, act_dict, user_id, vp_dict, ep_dicts, contact_dicts):
    super(ShareNewOperation, self).__init__(client)
    self._act_dict = act_dict
    self._user_id = user_id
    self._viewpoint_id = vp_dict['viewpoint_id']
    self._vp_dict = vp_dict
    self._vp_dict['user_id'] = user_id
    self._vp_dict['timestamp'] = self._op.timestamp
    self._ep_dicts = ep_dicts
    self._contact_dicts = contact_dicts

  @classmethod
  @gen.coroutine
  def Execute(cls, client, activity, user_id, viewpoint, episodes, contacts):
    """Entry point called by the operation framework."""
    yield ShareNewOperation(client, activity, user_id, viewpoint, episodes, contacts)._ShareNew()

  @gen.coroutine
  def _ShareNew(self):
    """Orchestrates the share new operation by executing each of the phases in turn."""
    # Lock the viewpoint while sharing into it.
    lock = yield gen.Task(Viewpoint.AcquireLock, self._client, self._viewpoint_id)
    try:
      if not (yield self._Check()):
        return
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
       1. Checkpoints list of contacts that need to be made prospective users.
       2. Cover photo, if not specified.

       Validates the following:
       1. Max follower limit.
       2. Permissions to share from source episodes.
       3. Permission to create new viewpoint.
       4. Cover photo is contained in the request.

    Returns True if all checks succeeded and operation execution should continue, or False
    if the operation should end immediately.
    """
    if len(self._contact_dicts) + 1 > Viewpoint.MAX_FOLLOWERS:   # +1 to account for user creating viewpoint.
      raise LimitExceededError(
          'User %d attempted to exceed follower limit on viewpoint "%s" by creating a viewpoint with %d followers.' %
          (self._user_id, self._viewpoint_id, len(self._contact_dicts) + 1))

    # Validate source episodes and posts.
    source_ep_posts_list = yield ViewfinderOperation._CheckCopySources('share',
                                                                       self._client,
                                                                       self._user_id,
                                                                       self._ep_dicts)

    # Get dicts describing the target episodes and posts.
    target_ep_ids = [ep_dict['new_episode_id'] for ep_dict in self._ep_dicts]
    self._new_ep_dicts = ViewfinderOperation._CreateCopyTargetDicts(self._op.timestamp,
                                                                    self._user_id,
                                                                    self._viewpoint_id,
                                                                    source_ep_posts_list,
                                                                    target_ep_ids)

    # Does request explicitly set a cover photo?
    if self._vp_dict.has_key('cover_photo'):
      if self._vp_dict['type'] == Viewpoint.DEFAULT:
        # cover_photo isn't supported creating default viewpoint.
        raise InvalidRequestError('cover_photo is invalid in share_new request for default viewpoint.')
      # Make sure the designated cover photo is contained in the request.
      elif not Viewpoint.IsCoverPhotoContainedInEpDicts(self._vp_dict['cover_photo']['episode_id'],
                                                        self._vp_dict['cover_photo']['photo_id'],
                                                        self._new_ep_dicts):
        logging.warning('cover_photo is specified but not contained in request: vp_dict: %s, ep_dicts: %s',
                        self._vp_dict,
                        self._ep_dicts)
        raise InvalidRequestError('cover_photo is specified but not contained in request.')
    else:
      # Select cover photo from the set being shared.
      self._vp_dict['cover_photo'] = Viewpoint.SelectCoverPhotoFromEpDicts(self._new_ep_dicts)

    # Start populating the checkpoint if this the first time the operation has been run.
    if self._op.checkpoint is None:
      # If viewpoint already exists, then just warn and do nothing. We do not raise an error
      # because sometimes the client resubmits the same operation with different ids.
      viewpoint = yield gen.Task(Viewpoint.Query, self._client, self._viewpoint_id, None, must_exist=False)
      if viewpoint is not None:
        logging.warning('target viewpoint "%s" already exists', self._viewpoint_id)
        raise gen.Return(False)

      # Get a tuple for each contact: (user_exists?, user_id, webapp_dev_id). 
      self._contact_ids = yield self._ResolveContactIds(self._contact_dicts)

      # Set checkpoint.
      # List of contacts need to be check-pointed because it may change in the UPDATE phase (when contacts
      # can be bound to prospective users). If we fail after UPDATE, but before NOTIFY, we would not send
      # correct notifications on retry.
      checkpoint = {'contacts': self._contact_ids}
      yield self._op.SetCheckpoint(self._client, checkpoint)
    else:
      # Restore state from checkpoint.
      self._contact_ids = self._op.checkpoint['contacts']

    self._contact_user_ids = [user_id for user_exists, user_id, webapp_dev_id in self._contact_ids]

    raise gen.Return(True)

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Creates prospective users.
       2. Creates new viewpoint, episodes, and posts.
    """
    # Create any prospective users (may create nested CreateProspective operations).
    yield self._ResolveContacts(self._contact_dicts, self._contact_ids, reason='share_new=%d' % self._user_id)

    # Filter out sharer id, if it exists in the set.
    follower_ids = list(set(user_id for user_id in self._contact_user_ids if user_id != self._user_id))

    # Create the viewpoint.
    self._viewpoint, self._followers = yield gen.Task(Viewpoint.CreateNewWithFollowers,
                                                      self._client,
                                                      follower_ids=follower_ids,
                                                      **self._vp_dict)

    # Create episode and posts.
    tasks = []
    for new_ep_dict in deepcopy(self._new_ep_dicts):
      episode_id = new_ep_dict['episode_id']
      photo_ids = new_ep_dict.pop('photo_ids')
      tasks.append(gen.Task(Episode.CreateNew, self._client, **new_ep_dict))
      for photo_id in photo_ids:
        tasks.append(gen.Task(Post.CreateNew, self._client, episode_id=episode_id, photo_id=photo_id))
    yield tasks

  @gen.coroutine
  def _Account(self):
    """Makes accounting changes:
       1. For revived followers.
       2. For new followers.
    """
    # Get list of the ids of all photos that were added.
    photo_ids = [photo_id for new_ep_dict in self._new_ep_dicts for photo_id in new_ep_dict['photo_ids']]

    # Make accounting changes for the new viewpoint.
    acc_accum = AccountingAccumulator()
    yield acc_accum.SharePhotos(self._client,
                                self._user_id,
                                self._viewpoint_id,
                                photo_ids,
                                [follower.user_id for follower in self._followers])
    yield acc_accum.Apply(self._client)

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
       1. Notifies removed followers that conversation has new activity.
       2. Notifies users with contacts that have become prospective users.
       3. Notifies existing followers of the viewpoint that new followers have been added.
       4. Notifies new followers that they have been added to a viewpoint.
    """
    # Creates notifications for any new prospective users.
    identity_keys = [contact_dict['identity']
                     for contact_dict, (user_exists, user_id, webapp_dev_id) in zip(self._contact_dicts,
                                                                                    self._contact_ids)
                     if not user_exists]
    yield NotificationManager.NotifyCreateProspective(self._client,
                                                      identity_keys,
                                                      self._op.timestamp)

    # Notify followers of the changes made by the share operation.
    yield NotificationManager.NotifyShareNew(self._client,
                                             self._vp_dict,
                                             self._followers,
                                             self._contact_user_ids,
                                             self._act_dict,
                                             self._ep_dicts,
                                             self._op.timestamp)
