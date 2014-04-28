# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder RemoveViewpointOperation.

This operation removes a viewpoint from a user's inbox without removing the user (as follower)
from the viewpoint.
"""

__authors__ = ['mike@emailscrubbed.com (Mike Purtell)',
               'andy@emailscrubbed.com (Andy Kimball)']

import json

from tornado import gen
from viewfinder.backend.base.exceptions import PermissionError
from viewfinder.backend.db.accounting import AccountingAccumulator
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation


class RemoveViewpointOperation(ViewfinderOperation):
  """The RemoveViewpoint operation follows the four phase pattern described in the header of
  operation_map.py.
  """
  def __init__(self, client, user_id, viewpoint_id):
    super(RemoveViewpointOperation, self).__init__(client)
    self._op = Operation.GetCurrent()
    self._client = client
    self._user_id = user_id
    self._viewpoint_id = viewpoint_id

  @classmethod
  @gen.coroutine
  def Execute(cls, client, user_id, viewpoint_id):
    """Entry point called by the operation framework."""
    yield RemoveViewpointOperation(client, user_id, viewpoint_id)._RemoveViewpoint()

  @gen.coroutine
  def _RemoveViewpoint(self):
    """Orchestrates the update follower operation by executing each of the phases in turn."""
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
       1. Queries for follower.

       Validates the following:
       1. Permission to remove viewpoint.

    Returns True if all checks succeeded and operation execution should continue, or False
    if the operation should end immediately.
    """
    # Get the follower object, check permissions, and determine if it's already been removed.
    self._follower = yield gen.Task(Follower.Query,
                                    self._client,
                                    self._user_id,
                                    self._viewpoint_id,
                                    None,
                                    must_exist=False)

    if self._follower is None:
      raise PermissionError('User %d does not have permission to remove viewpoint "%s", or it does not exist.' %
                            (self._user_id, self._viewpoint_id))

    if self._op.checkpoint is None:
      # The operation should not proceed if the viewpoint is already removed.
      if self._follower.IsRemoved():
        raise gen.Return(False)

      # Set checkpoint so that IsRemoved will not be checked on restart (since it will be updated
      # to True as part of this operation).
      yield self._op.SetCheckpoint(self._client, {'state': 'remove'})

    raise gen.Return(True)

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Add the REMOVED label to the follower.
    """
    yield self._follower.RemoveViewpoint(self._client)

  @gen.coroutine
  def _Account(self):
    """Makes accounting changes:
       1. Decrease user accounting by size of viewpoint.
    """
    acc_accum = AccountingAccumulator()
    yield acc_accum.RemoveViewpoint(self._client, self._user_id, self._viewpoint_id)
    yield acc_accum.Apply(self._client)

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
       1. Notify all of the user's devices that the viewpoint has been removed for them.
    """
    yield NotificationManager.NotifyRemoveViewpoint(self._client, self._user_id, self._viewpoint_id)
