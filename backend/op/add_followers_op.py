# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder AddFollowersOperation.

This operation adds a set of contacts to an existing viewpoint as followers of that viewpoint.
If a contact is not yet a Viewfinder user, we create a prospective user and link the contact
to that.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import json

from tornado import gen
from viewfinder.backend.base.exceptions import LimitExceededError, PermissionError
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


class AddFollowersOperation(ViewfinderOperation):
  """The AddFollowers operation follows the four phase pattern described in the header of
  operation_map.py.
  """
  def __init__(self, client, act_dict, user_id, viewpoint_id, contact_dicts):
    super(AddFollowersOperation, self).__init__(client)
    self._act_dict = act_dict
    self._user_id = user_id
    self._viewpoint_id = viewpoint_id
    self._contact_dicts = contact_dicts

  @classmethod
  @gen.coroutine
  def Execute(cls, client, activity, user_id, viewpoint_id, contacts):
    """Entry point called by the operation framework."""
    yield AddFollowersOperation(client, activity, user_id, viewpoint_id, contacts)._AddFollowers()

  @gen.coroutine
  def _AddFollowers(self):
    """Orchestrates the add followers operation by executing each of the phases in turn."""
    # Lock the viewpoint while adding followers.
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
       3. Checkpoints list of contacts that need to be made prospective users.
       4. Checkpoints list of contacts that are already following the viewpoint.

       Validates the following:
       1. Max follower limit.
       2. Permission to add followers.
    """
    # Get the viewpoint to be modified, along with the follower that is adding the additional users.
    # This state will not be changed by add followers, and so doesn't need to be part of the checkpoint.
    self._viewpoint, self._follower = yield gen.Task(Viewpoint.QueryWithFollower,
                                                     self._client,
                                                     self._user_id,
                                                     self._viewpoint_id)

    # Checks permission to add followers.
    if self._follower is None or not self._follower.CanContribute():
      raise PermissionError('User %d does not have permission to add followers to viewpoint "%s".' %
                            (self._user_id, self._viewpoint_id))

    # Start populating the checkpoint if this the first time the operation has been run.
    if self._op.checkpoint is None:
      # Get all existing followers.
      self._existing_followers, _ = yield gen.Task(Viewpoint.QueryFollowers,
                                                   self._client,
                                                   self._viewpoint_id,
                                                   limit=Viewpoint.MAX_FOLLOWERS)

      # Get list of followers which have removed themselves from the viewpoint and will need to be revived.
      self._revive_follower_ids = self._GetRevivableFollowers(self._existing_followers)

      # Get a tuple for each contact: (user_exists?, user_id, webapp_dev_id). 
      self._contact_ids = yield self._ResolveContactIds(self._contact_dicts)

      # Set checkpoint.
      # Existing followers, followers to revive, and list of contacts need to be check-pointed
      # because these sets are changed in the UPDATE phase. If we fail after UPDATE, but before
      # NOTIFY, we would not send correct notifications on retry.
      checkpoint = {'existing': [follower.user_id for follower in self._existing_followers],
                    'revive': self._revive_follower_ids,
                    'contacts': self._contact_ids}
      yield self._op.SetCheckpoint(self._client, checkpoint)
    else:
      # Restore state from checkpoint.
      follower_keys = [DBKey(follower_id, self._viewpoint_id) for follower_id in self._op.checkpoint['existing']]
      self._existing_followers = yield gen.Task(Follower.BatchQuery, self._client, follower_keys, None)
      self._revive_follower_ids = self._op.checkpoint['revive']
      self._contact_ids = self._op.checkpoint['contacts']

    self._contact_user_ids = [user_id for user_exists, user_id, webapp_dev_id in self._contact_ids]

    # Check if we're about to exceed follower limit on this viewpoint.
    if len(self._existing_followers) + len(self._contact_dicts) > Viewpoint.MAX_FOLLOWERS:
      raise LimitExceededError(
        'User %d attempted to exceed follower limit on viewpoint "%s" by adding %d followers.' %
        (self._user_id, self._viewpoint_id, len(self._contact_dicts)))

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Revives any followers that have removed the viewpoint.
       2. Creates prospective users.
       3. Adds the followers to the viewpoint.
    """
    # Create any prospective users (may create nested CreateProspective operations).
    yield self._ResolveContacts(self._contact_dicts, self._contact_ids, reason='add_follower=%d' % self._user_id)

    # Revive any REMOVED followers.
    yield gen.Task(Follower.ReviveRemovedFollowers, self._client, self._existing_followers)

    # Figure out which users need to be added as followers. Note that new followers exclude followers
    # from the request that are already following the viewpoint (assuming they're not removed).
    existing_follower_ids = set(follower.user_id for follower in self._existing_followers
                                if not follower.IsRemoved())
    self._new_follower_ids = [user_id for user_id in set(self._contact_user_ids)
                              if user_id not in existing_follower_ids]

    # Now actually add the followers.
    self._new_followers = yield self._viewpoint.AddFollowers(self._client,
                                                             self._user_id,
                                                             list(existing_follower_ids),
                                                             self._new_follower_ids,
                                                             self._op.timestamp)

  @gen.coroutine
  def _Account(self):
    """Makes accounting changes:
       1. For revived followers.
       2. For new followers.
    """
    acc_accum = AccountingAccumulator()

    # Make accounting changes for any revived followers.
    yield acc_accum.ReviveFollowers(self._client, self._viewpoint_id, self._revive_follower_ids)

    # Make accounting changes for the new followers.
    yield acc_accum.AddFollowers(self._client, self._viewpoint_id, self._new_follower_ids)

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

    # Creates notifications for any revived followers.
    yield NotificationManager.NotifyReviveFollowers(self._client,
                                                    self._viewpoint_id,
                                                    self._revive_follower_ids,
                                                    self._op.timestamp)

    # Creates notification of new viewpoint for each new follower.
    yield NotificationManager.NotifyAddFollowers(self._client,
                                                 self._viewpoint_id,
                                                 self._existing_followers,
                                                 self._new_followers,
                                                 self._contact_user_ids,
                                                 self._act_dict,
                                                 self._op.timestamp)
