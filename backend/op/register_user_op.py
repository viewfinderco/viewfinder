# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder RegisterUserOperation.

This operation registers an existing user by adding the REGISTERED label to it. It also can
register a new mobile device.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import json

from tornado import gen
from viewfinder.backend.db.analytics import Analytics
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.lock import Lock
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation


class RegisterUserOperation(ViewfinderOperation):
  """The RegisterUser operation follows the four phase pattern described in the header of
  operation_map.py.

    "user_dict" contains oauth-supplied user information which is either used to initially
    populate the fields for a new user account, or is used to update missing fields. The
    "REGISTERED" label is always added to the user object if is not yet present.

    "ident_dict" contains the identity key, authority, and various auth-specific access and
    refresh tokens that will be stored with the identity.

    "device_dict" contains information about the device being used for this registration. If
    access is via the web application, "device_dict" will be None. Otherwise, it will contain
    either: a device-id for an already-registered device, or device information in order to
    create a new device.
  """
  def __init__(self, client, user_dict, ident_dict, device_dict):
    super(RegisterUserOperation, self).__init__(client)
    self._user_dict = user_dict
    self._ident_dict = ident_dict
    self._device_dict = device_dict

  @classmethod
  @gen.coroutine
  def Execute(cls, client, user_dict, ident_dict, device_dict):
    """Entry point called by the operation framework."""
    yield RegisterUserOperation(client, user_dict, ident_dict, device_dict)._RegisterUser()

  @gen.coroutine
  def _RegisterUser(self):
    """Orchestrates the register operation by executing each of the phases in turn."""
    yield self._Check()
    self._client.CheckDBNotModified()
    yield self._Update()
    yield Operation.TriggerFailpoint(self._client)
    yield self._Notify()

  @gen.coroutine
  def _Check(self):
    """Gathers pre-mutation information:
       1. Queries for the existing user and identity.
       2. Checkpoints whether the user is prospective.
       3. Checkpoints whether the identity is linked to the user.
       4. Checkpoints whether the device is the first mobile device to be registered.
    """
    # Start populating the checkpoint if this the first time the operation has been run.
    if self._op.checkpoint is None:
      # Remember whether the user was a prospective user at the start of the operation. 
      user = yield gen.Task(User.Query, self._client, self._user_dict['user_id'], None)
      self._is_first_register = not user.IsRegistered()

      # Remember whether the identity was bound to the user at the start of the operation.
      identity = yield gen.Task(Identity.Query, self._client, self._ident_dict['key'], None)
      self._is_linking = identity.user_id is None

      # Remember if this is the first mobile device to be registered for this user.
      existing_devices = yield gen.Task(Device.RangeQuery,
                                        self._client,
                                        user.user_id,
                                        None,
                                        limit=1,
                                        col_names=None)
      self._is_first_device = len(existing_devices) == 0

      checkpoint = {'is_first_reg': self._is_first_register,
                    'linked': self._is_linking,
                    'is_first_dev': self._is_first_device}
      yield self._op.SetCheckpoint(self._client, checkpoint)
    else:
      # Restore state from checkpoint.
      self._is_first_register = self._op.checkpoint['is_first_reg']
      self._is_first_device = self._op.checkpoint['is_first_dev']
      self._is_linking = self._op.checkpoint['linked']

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Registers the user and identity.
       2. Registers the device.
    """
    yield User.Register(self._client,
                        self._user_dict,
                        self._ident_dict,
                        self._op.timestamp,
                        rewrite_contacts=self._is_first_register or self._is_linking)

    if self._device_dict is not None:
      yield Device.Register(self._client,
                            self._user_dict['user_id'],
                            self._device_dict,
                            is_first=self._is_first_device)

    # Update analytics if prospective user was registered.
    if self._is_first_register:
      analytics = Analytics.Create(entity='us:%d' % self._user_dict['user_id'],
                                   type=Analytics.USER_REGISTER,
                                   timestamp=self._op.timestamp)
      yield gen.Task(analytics.Update, self._client)

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
       1. Notifies the user and his friends and contacts of any changes to the user or its
          identities.
    """
    yield NotificationManager.NotifyRegisterUser(self._client,
                                                 self._user_dict,
                                                 self._ident_dict,
                                                 self._op.timestamp,
                                                 self._is_first_register,
                                                 self._is_linking)
