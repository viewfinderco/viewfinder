# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder MergeAccountsOperation.

This operation merges one source user account into another target user account. The target user
is added to all the source user's viewpoints, all source identities are re-bound to the target
user, and the source is terminated.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import logging

from tornado import gen
from viewfinder.backend.db.accounting import Accounting, AccountingAccumulator
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.lock import Lock
from viewfinder.backend.db.lock_resource_type import LockResourceType
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation


class MergeAccountsOperation(ViewfinderOperation):
  """The MergeAccounts operation consists of the following steps:

     STEP 1: MERGE VIEWPOINTS
       Add target user as a follower of all non-removed viewpoints followed by the source user.

     STEP 2: MERGE IDENTITIES
       Re-bind all source user identities to the target user.

     STEP 3: TERMINATE USER
       Terminates the source user.
  """
  _MAX_IDENTITIES = 25
  """Maximum number of identities that can be merged."""

  _FOLLOWER_LIMIT = 50
  """Number of followers that will be queried at a time."""

  def __init__(self, client, act_dict, target_user_id, source_user_id):
    super(MergeAccountsOperation, self).__init__(client)
    self._act_dict = act_dict
    self._target_user_id = target_user_id
    self._source_user_id = source_user_id
    self._acc_accum = AccountingAccumulator()

  @classmethod
  @gen.coroutine
  def Execute(cls, client, activity, target_user_id, source_user_id):
    """Entry point called by the operation framework."""
    yield MergeAccountsOperation(client, activity, target_user_id, source_user_id)._Merge()

  @gen.coroutine
  def _Merge(self):
    """Orchestrates the merge operation."""
    # Acquire op-lock for source user (should already have op-lock for target user).
    op_lock = yield gen.Task(Lock.Acquire,
                             self._client,
                             LockResourceType.Operation,
                             str(self._source_user_id),
                             owner_id=self._op.operation_id)
    try:
      # If checkpoint exists, may skip past viewpoint merge phase.
      state = self._op.checkpoint['state'] if self._op.checkpoint else 'vp'
      if state == 'vp':
        # Make target user a follower of all source user's viewpoints.
        yield self._MergeViewpoints()
        yield Operation.TriggerFailpoint(self._client)
        self._op.checkpoint = None
      else:
        assert state == 'id', state

      # Re-bind identities of the source user to the target user.
      yield self._MergeIdentities()
      yield Operation.TriggerFailpoint(self._client)

      # Terminate the source user.
      yield gen.Task(User.TerminateAccountOperation,
                     self._client,
                     user_id=self._source_user_id,
                     merged_with=self._target_user_id)
      yield Operation.TriggerFailpoint(self._client)
    finally:
      yield gen.Task(op_lock.Release, self._client)

  @gen.coroutine
  def _MergeViewpoints(self):
    """Loops over all viewpoints followed by the source user and merges any that have not been
    removed. Applies user accounting information accumulated in _MergeOneViewpoint.
    """
    # If checkpoint exists, then operation has been restarted, so re-merge the checkpointed viewpoint.
    if self._op.checkpoint is not None:
      start_key = self._op.checkpoint['id']
      yield self._MergeOneViewpoint(start_key)
    else:
      start_key = None

    # Scan remainder of viewpoints.
    while True:
      follower_list = yield gen.Task(Follower.RangeQuery,
                                     self._client,
                                     self._source_user_id,
                                     range_desc=None,
                                     limit=MergeAccountsOperation._FOLLOWER_LIMIT,
                                     col_names=None,
                                     excl_start_key=start_key)

      start_key = follower_list[-1].viewpoint_id if follower_list else None
      logging.info('scanned %d follower records for merging, last key=%s', len(follower_list), start_key)

      for follower in follower_list:
        # Skip removed viewpoints.
        if follower.IsRemoved():
          continue

        self._op.checkpoint = None
        yield self._MergeOneViewpoint(follower.viewpoint_id)

      if len(follower_list) < MergeAccountsOperation._FOLLOWER_LIMIT:
        break

    # Apply the accounting information that was accumulated from the viewpoints. 
    yield self._acc_accum.Apply(self._client)

  @gen.coroutine
  def _MergeOneViewpoint(self, viewpoint_id):
    """Adds the target user as a follower of the given viewpoint owned by the source user.
    Accumulates the size of all viewpoints that are merged. Creates notifications for the
    merged viewpoint. Sets a checkpoint containing follower and accounting information to
    be used if a restart occurs.
    """
    # Skip default and system viewpoints.
    viewpoint = yield gen.Task(Viewpoint.Query, self._client, viewpoint_id, None)
    if viewpoint.IsDefault() or viewpoint.IsSystem():
      return

    # Lock the viewpoint while querying and modifying to the viewpoint.
    vp_lock = yield gen.Task(Viewpoint.AcquireLock, self._client, viewpoint_id)
    try:
      if self._op.checkpoint is None:
        # Get list of existing followers.
        existing_follower_ids, _ = yield gen.Task(Viewpoint.QueryFollowerIds,
                                                  self._client,
                                                  viewpoint_id,
                                                  limit=Viewpoint.MAX_FOLLOWERS)

        # Skip viewpoint if target user is already a follower.
        if self._target_user_id in existing_follower_ids:
          return

        # Skip viewpoint if there are too many followers (this should virtually never happen, since client
        # enforces an even smaller limit).
        if len(existing_follower_ids) >= Viewpoint.MAX_FOLLOWERS:
          logging.warning('merge of user %d into user %d would exceed follower limit on viewpoint "%s"',
                          (self._source_user_id, self._target_user_id, viewpoint_id))
          return

        # Add size of this viewpoint to the accounting accumulator and checkpoint in case operation restarts.
        yield self._acc_accum.MergeAccounts(self._client, viewpoint_id, self._target_user_id)

        checkpoint = {'state': 'vp',
                      'id': viewpoint_id,
                      'existing': existing_follower_ids,
                      'account': self._acc_accum.GetUserVisibleTo(self._target_user_id)._asdict()}
        yield self._op.SetCheckpoint(self._client, checkpoint)
      else:
        # Re-constitute state from checkpoint.
        existing_follower_ids = self._op.checkpoint['existing']
        accounting = Accounting.CreateFromKeywords(**self._op.checkpoint['account'])
        self._acc_accum.GetUserVisibleTo(self._target_user_id).IncrementStatsFrom(accounting)

      # Get the source follower.
      source_follower = yield gen.Task(Follower.Query, self._client, self._source_user_id, viewpoint_id, None)

      # Now actually add the target user as a follower.
      target_follower = (yield viewpoint.AddFollowers(self._client,
                                                      source_follower.adding_user_id,
                                                      existing_follower_ids,
                                                      [self._target_user_id],
                                                      self._op.timestamp))[0]

      # Get list of existing follower db objects.
      follower_keys = [DBKey(follower_id, viewpoint_id) for follower_id in existing_follower_ids]
      existing_followers = yield gen.Task(Follower.BatchQuery, self._client, follower_keys, None)

      # Synthesize a unique activity id by adding viewpoint id to the activity id.
      truncated_ts, device_id, (client_id, server_id) = Activity.DeconstructActivityId(self._act_dict['activity_id'])
      activity_id = Activity.ConstructActivityId(truncated_ts, device_id, (client_id, viewpoint_id))
      activity_dict = {'activity_id': activity_id,
                       'timestamp': self._act_dict['timestamp']}

      # Create merge-related notifications.
      yield NotificationManager.NotifyMergeViewpoint(self._client,
                                                     viewpoint_id,
                                                     existing_followers,
                                                     target_follower,
                                                     self._source_user_id,
                                                     activity_dict,
                                                     self._op.timestamp)
    finally:
      yield gen.Task(Viewpoint.ReleaseLock, self._client, viewpoint_id, vp_lock)

  @gen.coroutine
  def _MergeIdentities(self):
    """Re-binds all identities attached to the source user to the target user. Sends corresponding
    notifications for any merged identities. Sets a checkpoint so that the exact same set of
    identities will be merged if a restart occurs.
    """
    if self._op.checkpoint is None:
      # Get set of identities that need to re-bound to the target user.
      query_expr = ('identity.user_id={id}', {'id': self._source_user_id})
      identity_keys = yield gen.Task(Identity.IndexQueryKeys,
                                     self._client,
                                     query_expr,
                                     limit=MergeAccountsOperation._MAX_IDENTITIES)

      checkpoint = {'state': 'id',
                    'ids': [key.hash_key for key in identity_keys]}
      yield self._op.SetCheckpoint(self._client, checkpoint)
    else:
      identity_keys = [DBKey(id, None) for id in self._op.checkpoint['ids']]

    # Get all the identity objects and re-bind them to the target user.
    identities = yield gen.Task(Identity.BatchQuery, self._client, identity_keys, None)
    for identity in identities:
      identity.expires = 0
      identity.user_id = self._target_user_id
      yield gen.Task(identity.Update, self._client)

    # Send notifications for all identities that were re-bound.
    yield NotificationManager.NotifyMergeIdentities(self._client,
                                                    self._target_user_id,
                                                    [identity.key for identity in identities],
                                                    self._op.timestamp)
