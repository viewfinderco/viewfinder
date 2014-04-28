# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder LinkIdentityOperation.

This operation links a previously unlinked identity to a target user account.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import logging

from tornado import gen
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.resources.message.error_messages import ALREADY_LINKED
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation


class LinkIdentityOperation(ViewfinderOperation):
  """The LinkIdentity operation follows the four phase pattern described in the header of
  operation_map.py.
  """
  def __init__(self, client, target_user_id, source_identity_key):
    super(LinkIdentityOperation, self).__init__(client)
    self._target_user_id = target_user_id
    self._source_identity_key = source_identity_key

  @classmethod
  @gen.coroutine
  def Execute(cls, client, target_user_id, source_identity_key):
    """Entry point called by the operation framework."""
    yield LinkIdentityOperation(client, target_user_id, source_identity_key)._Link()

  @gen.coroutine
  def _Link(self):
    """Orchestrates the link identity operation by executing each of the phases in turn."""
    yield self._Check()
    self._client.CheckDBNotModified()
    yield self._Update()
    # No accounting for this operation.
    yield Operation.TriggerFailpoint(self._client)
    yield self._Notify()

  @gen.coroutine
  def _Check(self):
    """Gathers pre-mutation information:
       1. Queries for the identity.

       Validates the following:
       1. Identity cannot be already linked to a different user.
    """
    self._identity = yield gen.Task(Identity.Query, self._client, self._source_identity_key, None, must_exist=False)
    if self._identity is None:
      self._identity = Identity.CreateFromKeywords(key=self._source_identity_key, authority='Viewfinder')

    if self._identity.user_id is not None and self._identity.user_id != self._target_user_id:
      raise PermissionError(ALREADY_LINKED, account=Identity.GetDescription(self._source_identity_key))

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Binds the identity to the target user.
    """
    self._identity.expires = 0
    self._identity.user_id = self._target_user_id
    yield gen.Task(self._identity.Update, self._client)

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
       1. Notifies other users with contacts that are bound to the identity.
       2. Notifies target user that identities have changed.
    """
    # Send notifications for all identities that were re-bound.
    yield NotificationManager.NotifyLinkIdentity(self._client,
                                                 self._target_user_id,
                                                 self._source_identity_key,
                                                 self._op.timestamp)
