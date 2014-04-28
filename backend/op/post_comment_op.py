# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder PostCommentOperation.

This operation adds a new comment to a viewpoint, optionally attached to another asset in the
same viewpoint (such as a photo or another comment).
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import json
import logging

from tornado import escape, gen
from viewfinder.backend.base.exceptions import LimitExceededError, PermissionError
from viewfinder.backend.db.accounting import AccountingAccumulator
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation


class PostCommentOperation(ViewfinderOperation):
  """The PostComment operation follows the four phase pattern described in the header of
  operation_map.py.
  """
  def __init__(self, client, act_dict, user_id, cm_dict):
    super(PostCommentOperation, self).__init__(client)
    self._act_dict = act_dict
    self._user_id = user_id
    self._cm_dict = cm_dict
    self._cm_dict['user_id'] = user_id
    self._viewpoint_id = cm_dict['viewpoint_id']
    self._comment_id = cm_dict['comment_id']

  @classmethod
  @gen.coroutine
  def Execute(cls, client, activity, user_id, comment):
    """Entry point called by the operation framework."""
    yield PostCommentOperation(client, activity, user_id, comment)._PostComment()

  @gen.coroutine
  def _PostComment(self):
    """Orchestrates the post_comment operation by executing each of the phases in turn."""
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
       1. Queries for existing followers and comment.
       2. Checkpoints list of followers that need to be revived.

       Validates the following:
       1. Checks for maximum comment size.
       2. Permission to add a comment to the viewpoint.
    """
    # Check that the size of the comment message isn't too large.
    message_byte_size = len(escape.utf8(self._cm_dict['message']))
    if message_byte_size > Comment.COMMENT_SIZE_LIMIT_BYTES:
      logging.warning('User %d attempted to exceed message size limit ( %d / %d ) on comment "%s", viewpoint "%s"' %
                      (self._user_id, message_byte_size, Comment.COMMENT_SIZE_LIMIT_BYTES,
                       self._comment_id, self._viewpoint_id))
      raise LimitExceededError('Comment "%s" is too long.' % self._comment_id)

    # Get all existing followers.
    self._followers, _ = yield gen.Task(Viewpoint.QueryFollowers,
                                        self._client,
                                        self._viewpoint_id,
                                        limit=Viewpoint.MAX_FOLLOWERS)

    # Check for permission to add a comment to the viewpoint.
    owner_follower = [follower for follower in self._followers if follower.user_id == self._user_id]
    if not owner_follower or not owner_follower[0].CanContribute():
      raise PermissionError('User %d does not have permission to add comments to viewpoint "%s".' %
                            (self._user_id, self._viewpoint_id))

    # Start populating the checkpoint if this the first time the operation has been run.
    if self._op.checkpoint is None:
      # If comment already exists, then just warn and do nothing. We do not raise an error
      # because sometimes the client resubmits the same operation with different ids.
      comment = yield gen.Task(Comment.Query,
                               self._client,
                               self._viewpoint_id,
                               self._comment_id,
                               None,
                               must_exist=False)
      if comment is not None:
        logging.warning('comment "%s" already exists', self._comment_id)
        raise gen.Return(False)

      # Get list of followers which have removed themselves from the viewpoint and will need to be revived.
      self._revive_follower_ids = self._GetRevivableFollowers(self._followers)

      # Set checkpoint.
      # Followers to revive need to be check-pointed because they are changed in the UPDATE phase.
      # If we fail after UPDATE, but before NOTIFY, we would not send correct notifications on retry.
      checkpoint = {'revive': self._revive_follower_ids}
      yield self._op.SetCheckpoint(self._client, checkpoint)
    else:
      # Restore state from checkpoint.
      self._revive_follower_ids = self._op.checkpoint['revive']

    raise gen.Return(True)

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Revives any followers that have removed the viewpoint.
       2. Creates the new comment.
    """
    # Revive any REMOVED followers.
    yield gen.Task(Follower.ReviveRemovedFollowers, self._client, self._followers)

    # Create the comment.
    yield Comment.CreateNew(self._client, **self._cm_dict)

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
       2. Notifies existing followers of the viewpoint that a new comment has been added.
    """
    # Creates notifications for any revived followers.
    yield NotificationManager.NotifyReviveFollowers(self._client,
                                                    self._viewpoint_id,
                                                    self._revive_follower_ids,
                                                    self._op.timestamp)

    # Notifies followers that a comment has been added.
    yield NotificationManager.NotifyPostComment(self._client,
                                                self._followers,
                                                self._act_dict,
                                                self._cm_dict)
