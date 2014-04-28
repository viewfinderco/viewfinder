# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder UpdateFollowerOperation.

This operation update's follower metadata for a user.
"""

__authors__ = ['mike@emailscrubbed.com (Mike Purtell)',
               'andy@emailscrubbed.com (Andy Kimball)']

import json
import logging

from tornado import gen
from viewfinder.backend.base.exceptions import PermissionError
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation


class UpdateFollowerOperation(ViewfinderOperation):
  """The UpdateFollower operation follows the four phase pattern described in the header of
  operation_map.py, except that there is no ACCOUNT phase, since this operation does not affect
  accounting.
  """
  def __init__(self, client, user_id, foll_dict):
    super(UpdateFollowerOperation, self).__init__(client)
    self._foll_dict = foll_dict
    self._user_id = user_id
    self._viewpoint_id = foll_dict['viewpoint_id']

  @classmethod
  @gen.coroutine
  def Execute(cls, client, user_id, follower):
    """Entry point called by the operation framework."""
    yield UpdateFollowerOperation(client, user_id, follower)._UpdateFollower()

  @gen.coroutine
  def _UpdateFollower(self):
    """Orchestrates the update follower operation by executing each of the phases in turn."""
    lock = yield gen.Task(Viewpoint.AcquireLock, self._client, self._viewpoint_id)
    try:
      yield self._Check()
      self._client.CheckDBNotModified()
      yield self._Update()
      yield Operation.TriggerFailpoint(self._client)
      yield self._Notify()
    finally:
      yield gen.Task(Viewpoint.ReleaseLock, self._client, self._viewpoint_id, lock)

  @gen.coroutine
  def _Check(self):
    """Gathers pre-mutation information:
       1. Queries for follower.
       2. Queries for viewpoint.

       Validates the following:
       1. Permission to update follower metadata.
       2. Certain labels cannot be set.
    """
    self._follower = yield gen.Task(Follower.Query,
                                    self._client,
                                    self._user_id,
                                    self._viewpoint_id,
                                    None,
                                    must_exist=False)
    if self._follower is None:
      raise PermissionError('User %d does not have permission to update follower "%s", or it does not exist.' %
                            (self._user_id, self._viewpoint_id))

    self._viewpoint = yield gen.Task(Viewpoint.Query, self._client, self._viewpoint_id, None)

    if 'labels' in self._foll_dict:
      self._follower.SetLabels(self._foll_dict['labels'])

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Updates the follower metadata.
    """
    # Labels should have been set in the _Check step.
    assert 'labels' not in self._foll_dict or set(self._follower.labels) == set(self._foll_dict['labels']), \
           (self._foll_dict, self._follower.labels)

    if 'viewed_seq' in self._foll_dict:
      # Don't allow viewed_seq to exceed update_seq.
      if self._foll_dict['viewed_seq'] > self._viewpoint.update_seq:
        self._foll_dict['viewed_seq'] = self._viewpoint.update_seq

      # Ratchet up viewed_seq so that it's guaranteed to monotonically increase.
      if self._foll_dict['viewed_seq'] > self._follower.viewed_seq:
        self._follower.viewed_seq = self._foll_dict['viewed_seq']
      else:
        # Map to final value which will be used in the notification.
        self._foll_dict['viewed_seq'] = self._follower.viewed_seq

    yield gen.Task(self._follower.Update, self._client)

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
       1. Notify all of the user's devices that the follower has been updated.
    """
    yield NotificationManager.NotifyUpdateFollower(self._client, self._foll_dict)
