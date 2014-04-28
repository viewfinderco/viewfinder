# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Viewfinder user.

  User: viewfinder user account information
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import json

from copy import deepcopy
from tornado import gen, web
from viewfinder.backend.base import secrets, util
from viewfinder.backend.base.exceptions import InvalidRequestError
from viewfinder.backend.db import db_client, vf_schema
from viewfinder.backend.db.analytics import Analytics
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.hash_base import DBHashObject
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.friend import Friend
from viewfinder.backend.db.id_allocator import IdAllocator
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.subscription import Subscription
from viewfinder.backend.op.notification_manager import NotificationManager


@DBObject.map_table_attributes
class User(DBHashObject):
  """Viewfinder user account."""
  __slots__ = []

  # Label flags.
  REGISTERED = 'registered'
  """Full user that is authenticated by trusted authority and has
  explicitly accepted the TOS. If this flag is not present, then the
  user is a "prospective" user, which is a read-only user that has
  not yet been fully registered.
  """

  STAGING = 'staging'
  """Beta user that is redirected to the staging cluster. If this flag
  is not present, then the user will be redirected to the main production
  cluster.
  """

  TERMINATED = 'terminated'
  """The account has been terminated by the user. This user can no longer
  sign in, and other users can no longer share with him/her.
  """

  SYSTEM = 'system'
  """System user that should not be shown in contacts even if a friend."""

  _REGISTER_USER_ATTRIBUTES = set(['user_id', 'name', 'given_name', 'family_name', 'email', 'picture', 'gender',
                                   'link', 'locale', 'timezone', 'facebook_email', 'phone', 'pwd_hash', 'salt'])
  """Subset of user attributes that can be set as part of user registration."""

  _UPDATE_USER_ATTRIBUTES = set(['name', 'given_name', 'family_name', 'picture', 'pwd_hash', 'salt'])
  """Subset of user attributes that can be updated by the user."""

  _USER_FRIEND_ATTRIBUTES = set(['user_id', 'name', 'given_name', 'family_name', 'email', 'picture', 'merged_with'])
  """Subset of user attributes that are visible to friends."""

  _USER_NON_FRIEND_LABELS = set([REGISTERED, TERMINATED, SYSTEM])
  """Subset of user labels that are visible to non-friends."""

  _USER_FRIEND_LABELS = _USER_NON_FRIEND_LABELS
  """Subset of user labels that are visible to friends."""

  _table = DBObject._schema.GetTable(vf_schema.USER)

  _ALLOCATION = 1
  _allocator = IdAllocator(id_type=_table.hash_key_col.name, allocation=_ALLOCATION)

  _RESERVED_ASSET_ID_COUNT = 1
  """Number of asset ids which are reserved for system use (default vp for now)."""

  DEFAULT_VP_ASSET_ID = 0
  """Asset id used in the default viewpoint id."""

  def __init__(self, user_id=None):
    """Creates a new user."""
    super(User, self).__init__()
    self.user_id = user_id

  def IsRegistered(self):
    """Returns true if this is a fully registered user that has been
    authenticated by a trusted authority.
    """
    return User.REGISTERED in self.labels

  def IsStaging(self):
    """Returns true if this user should always be redirected to the
    staging cluster.
    """
    return User.STAGING in self.labels

  def IsTerminated(self):
    """Returns true if this user's account has been terminated."""
    return User.TERMINATED in self.labels

  def IsSystem(self):
    """Returns true if this user is a system user."""
    return User.SYSTEM in self.labels

  @gen.coroutine
  def MakeSystemUser(self, client):
    """Adds the SYSTEM label to this user."""
    self.labels.add(User.SYSTEM)
    yield gen.Task(self.Update, client)

  def QueryIdentities(self, client, callback):
    """Queries the identities (if any) attached to this user and
    returns the list to the provided callback.
    """
    query_str = 'identity.user_id=%d' % self.user_id
    Identity.IndexQuery(client, query_str, col_names=None, callback=callback)

  @gen.coroutine
  def QueryPrimaryIdentity(self, client):
    """Method to return the primary identity associated with an account.

    This currently only works for prospective users, which are guaranteed to have a single
    identity.  The method is being created with a more general signature so that it will
    be useful once the anticipated concept of a primary identity is introduced.
    """
    assert not self.IsRegistered(), 'QueryPrimaryIdentity is currently only permitted for Prospective users.'
    identities = yield gen.Task(self.QueryIdentities, client)

    assert len(identities) == 1, 'Encountered prospective user %d with multiple identities.' % self.user_id
    raise gen.Return(identities[0])

  @classmethod
  def ShouldScrubColumn(cls, name):
    """Returns list of column names that should not be printed in logs."""
    return name in ['signing_key', 'pwd_hash', 'salt']

  def MakeLabelList(self, is_friend):
    """Returns a list suitable for the 'labels' field of USER_PROFILE_METADATA.

    If 'is_friend' is True, returns labels accessible to friends; if it is false, returns
    only labels accessible to strangers.
    """
    if is_friend:
      labels = [label for label in self.labels if label in User._USER_FRIEND_LABELS]
      labels.append('friend')
      return labels
    else:
      return [label for label in self.labels if label in User._USER_NON_FRIEND_LABELS]

  @gen.engine
  def MakeUserMetadataDict(self, client, viewer_user_id, forward_friend, reverse_friend, callback):
    """Projects a subset of the user attributes that can be provided to the viewing user (using
    the same schema as the query_users service method). The 'forward_friend' is viewer_user_id =>
    friend_user_id, and the 'reverse_friend' is the reverse. This user's profile information
    will only be provided to the viewer if the viewer is a reverse friend (i.e. user considers
    the viewer a friend).

    The 'private' block will be returned only if viewer_user_id == self.user_id.
    """
    user_dict = {'user_id': self.user_id}

    # First, populate basic user data, but only if the user considers the viewer a friend.
    if reverse_friend is not None:
      for attr_name in User._USER_FRIEND_ATTRIBUTES:
        util.SetIfNotNone(user_dict, attr_name, getattr(self, attr_name, None))
      user_dict['labels'] = self.MakeLabelList(True)
    else:
      # Set labels which are visible to non-friends.
      user_dict['labels'] = self.MakeLabelList(False)

    # Now project friend attributes.
    for attr_name in Friend.FRIEND_ATTRIBUTES:
      util.SetIfNotNone(user_dict, attr_name, getattr(forward_friend, attr_name, None))

    # Now fill out private attributes if this user is also the viewing user.
    if viewer_user_id == self.user_id:
      user_dict['private'] = {}
      if self.pwd_hash is None:
        user_dict['private']['no_password'] = True

      subs, settings = yield [gen.Task(Subscription.QueryByUser, client, user_id=self.user_id),
                              gen.Task(AccountSettings.QueryByUser, client, self.user_id, None, must_exist=False)]

      sub_dicts = [sub.MakeMetadataDict() for sub in subs]
      user_dict['private']['subscriptions'] = sub_dicts

      if settings is not None:
        user_dict['private']['account_settings'] = settings.MakeMetadataDict()

      def _MakeIdentityDict(ident):
        i_dict = {'identity': ident.key}
        if ident.authority is not None:
          i_dict['authority'] = ident.authority
        return i_dict

      query_expr = 'identity.user_id=%d' % self.user_id
      identities = yield gen.Task(Identity.IndexQuery, client, query_expr, ['key', 'authority'])
      user_dict['private']['user_identities'] = [_MakeIdentityDict(ident) for ident in identities]

    callback(user_dict)

  @classmethod
  def AllocateAssetIds(cls, client, user_id, num_ids, callback):
    """Allocates 'num_ids' new ids from the 'asset_id_seq' column in a
    block for the specified user id and returns the first id in the
    sequence (first_id, ..., first_id + num_ids] with the callback
    """
    id_seq_key = cls._table.GetColumn('asset_id_seq').key

    def _OnUpdateIdSeq(result):
      last_id = result.return_values[id_seq_key]
      first_id = last_id - num_ids
      callback(first_id)

    client.UpdateItem(table=cls._table.name,
                      key=db_client.DBKey(hash_key=user_id, range_key=None),
                      attributes={id_seq_key: db_client.UpdateAttr(value=num_ids, action='ADD')},
                      return_values='UPDATED_NEW', callback=_OnUpdateIdSeq)

  @classmethod
  @gen.coroutine
  def AllocateUserAndWebDeviceIds(cls, client):
    """Allocates a new user id and a new web device id and returns them in a tuple."""
    user_id = yield gen.Task(User._allocator.NextId, client)
    webapp_dev_id = yield gen.Task(Device._allocator.NextId, client)
    raise gen.Return((user_id, webapp_dev_id))

  @classmethod
  @gen.engine
  def QueryUsers(cls, client, viewer_user_id, user_ids, callback):
    """Queries User objects for each id in the 'user_ids' list. Invokes 'callback' with a list
    of (user, forward_friend, reverse_friend) tuples. Non-existent users are omitted.
    """
    user_keys = [db_client.DBKey(user_id, None) for user_id in user_ids]
    forward_friend_keys = [db_client.DBKey(viewer_user_id, user_id) for user_id in user_ids]
    reverse_friend_keys = [db_client.DBKey(user_id, viewer_user_id) for user_id in user_ids]
    users, forward_friends, reverse_friends = \
    yield [gen.Task(User.BatchQuery, client, user_keys, None, must_exist=False),
           gen.Task(Friend.BatchQuery, client, forward_friend_keys, None, must_exist=False),
           gen.Task(Friend.BatchQuery, client, reverse_friend_keys, None, must_exist=False)]

    user_friend_list = []
    for user, forward_friend, reverse_friend in zip(users, forward_friends, reverse_friends):
      if user is not None:
        user_friend_list.append((user, forward_friend, reverse_friend))

    callback(user_friend_list)

  @classmethod
  @gen.coroutine
  def CreateProspective(cls, client, user_id, webapp_dev_id, identity_key, timestamp):
    """Creates a prospective user with the specified user id. web device id, and identity key.

    A prospective user is typically created when photos are shared with a contact that is not
    yet a Viewfinder user.

    Returns a tuple containing the user and identity.
    """
    from viewfinder.backend.db.viewpoint import Viewpoint

    identity_type, identity_value = Identity.SplitKey(identity_key)

    # Ensure that identity is created.
    identity = yield gen.Task(Identity.CreateProspective,
                              client,
                              identity_key,
                              user_id,
                              timestamp)

    # Create the default viewpoint.
    viewpoint = yield Viewpoint.CreateDefault(client, user_id, webapp_dev_id, timestamp)

    # By default, send alerts when a new conversation is started. Send email alerts if the
    # identity is email, or sms alerts if the identity is phone.
    email_alerts = AccountSettings.EMAIL_ON_SHARE_NEW if identity_type == 'Email' else AccountSettings.EMAIL_NONE
    sms_alerts = AccountSettings.SMS_ON_SHARE_NEW if identity_type == 'Phone' else AccountSettings.SMS_NONE
    settings = AccountSettings.CreateForUser(user_id,
                                             email_alerts=email_alerts,
                                             sms_alerts=sms_alerts,
                                             push_alerts=AccountSettings.PUSH_NONE)
    yield gen.Task(settings.Update, client)

    # Create a Friend relation (every user is friends with himself).
    friend = Friend.CreateFromKeywords(user_id=user_id, friend_id=user_id)
    yield gen.Task(friend.Update, client)

    # Create the prospective user.
    email = identity_value if identity_type == 'Email' else None
    phone = identity_value if identity_type == 'Phone' else None
    user = User.CreateFromKeywords(user_id=user_id,
                                   private_vp_id=viewpoint.viewpoint_id,
                                   webapp_dev_id=webapp_dev_id,
                                   email=email,
                                   phone=phone,
                                   asset_id_seq=User._RESERVED_ASSET_ID_COUNT,
                                   signing_key=secrets.CreateSigningKeyset('signing_key'))
    yield gen.Task(user.Update, client)

    raise gen.Return((user, identity))

  @classmethod
  @gen.coroutine
  def Register(cls, client, user_dict, ident_dict, timestamp, rewrite_contacts):
    """Registers a user or updates its attributes using the contents of "user_dict". Updates
    an identity using the contents of "ident_dict" and ensures its linked to the user.

    "user_dict" contains oauth-supplied user information which is either used to initially
    populate the fields for a new user account, or is used to update missing fields. The
    "REGISTERED" label is always added to the user object if is not yet present.

    "ident_dict" contains the identity key, authority, and various auth-specific access and
    refresh tokens that will be stored with the identity.

    Returns the user object.
    """
    # Create prospective user if it doesn't already exist, or else return existing user.
    assert 'user_id' in user_dict, user_dict
    assert 'authority' in ident_dict, ident_dict

    user = yield gen.Task(User.Query, client, user_dict['user_id'], None)
    identity = yield gen.Task(Identity.Query, client, ident_dict['key'], None)

    # Update user attributes (only if they have not yet been set).
    for k, v in user_dict.items():
      assert k in User._REGISTER_USER_ATTRIBUTES, user_dict
      if getattr(user, k) is None:
        setattr(user, k, v)

    # Ensure that prospective user is registered.
    user.labels.add(User.REGISTERED)

    if rewrite_contacts:
      yield identity._RewriteContacts(client, timestamp)

    yield gen.Task(user.Update, client)

    # Update identity attributes.
    assert identity.user_id is None or identity.user_id == user.user_id, (identity, user)
    identity.user_id = user.user_id
    identity.UpdateFromKeywords(**ident_dict)
    yield gen.Task(identity.Update, client)

    raise gen.Return(user)

  @classmethod
  @gen.engine
  def UpdateWithSettings(cls, client, user_dict, settings_dict, callback):
    """Update the user's public profile, as well as any account settings specified in
    "settings_dict".
    """
    # Update user profile attributes.
    assert all(attr_name == 'user_id' or attr_name in User._UPDATE_USER_ATTRIBUTES
               for attr_name in user_dict), user_dict

    # If any name attribute is updated, update them all, if only to None. This helps prevent
    # accidental divergence of name from given_name/family_name.
    for attr_name in ['name', 'given_name', 'family_name']:
      if attr_name in user_dict:
        user_dict.setdefault('name', None)
        user_dict.setdefault('given_name', None)
        user_dict.setdefault('family_name', None)
        break

    user = yield gen.Task(User.Query, client, user_dict['user_id'], None)
    user.UpdateFromKeywords(**user_dict)
    yield gen.Task(user.Update, client)

    if settings_dict:
      # Add keys to dict.
      scratch_settings_dict = deepcopy(settings_dict)
      scratch_settings_dict['settings_id'] = AccountSettings.ConstructSettingsId(user_dict['user_id'])
      scratch_settings_dict['group_name'] = AccountSettings.GROUP_NAME
      scratch_settings_dict['user_id'] = user_dict['user_id']

      # Update any user account settings.
      settings = yield gen.Task(AccountSettings.QueryByUser, client, user_dict['user_id'], None, must_exist=False)
      if settings is None:
        settings = AccountSettings.CreateFromKeywords(**scratch_settings_dict)
      else:
        settings.UpdateFromKeywords(**scratch_settings_dict)
      yield gen.Task(settings.Update, client)

    callback()

  @classmethod
  @gen.coroutine
  def TerminateAccount(cls, client, user_id, merged_with):
    """Terminate the user's account by adding the "TERMINATED" flag to the labels set. If
    "merged_with" is not None, then the terminate is due to a merge, so set the "merged_with"
    field on the terminated user.
    """
    user = yield gen.Task(User.Query, client, user_id, None)
    user.merged_with = merged_with
    user.labels.add(User.TERMINATED)
    yield gen.Task(user.Update, client)

  @classmethod
  def CreateUnsubscribeCookie(cls, user_id, email_type):
    """Create a user unsubscribe cookie that is passed as an argument to the unsubscribe handler,
    and which proves control of the given user id.
    """
    unsubscribe_dict = {'user_id': user_id, 'email_type': email_type}
    return web.create_signed_value(secrets.GetSecret('invite_signing'), 'unsubscribe', json.dumps(unsubscribe_dict))

  @classmethod
  def DecodeUnsubscribeCookie(cls, unsubscribe_cookie):
    """Decode a user unsubscribe cookie that is passed as an argument to the unsubscribe handler.
    Returns the unsubscribe dict containing the user_id and email_type originally passed to
    CreateUnsubscribeCookie.
    """
    value = web.decode_signed_value(secrets.GetSecret('invite_signing'),
                                    'unsubscribe',
                                    unsubscribe_cookie)
    return None if value is None else json.loads(value)

  @classmethod
  @gen.coroutine
  def TerminateAccountOperation(cls, client, user_id, merged_with=None):
    """Invokes User.TerminateAccount via operation execution."""
    @gen.coroutine
    def _VisitIdentity(identity_key):
      """Unlink this identity from the user."""
      yield Identity.UnlinkIdentityOperation(client, user_id, identity_key.hash_key)

    # Turn off alerts to all devices owned by the user.
    yield gen.Task(Device.MuteAlerts, client, user_id)

    # Unlink every identity attached to the user.
    query_expr = ('identity.user_id={id}', {'id': user_id})
    yield gen.Task(Identity.VisitIndexKeys, client, query_expr, _VisitIdentity)

    # Add an analytics entry for this user.
    timestamp = Operation.GetCurrent().timestamp
    payload = 'terminate' if merged_with is None else 'merge=%s' % merged_with
    analytics = Analytics.Create(entity='us:%d' % user_id,
                                 type=Analytics.USER_TERMINATE,
                                 timestamp=timestamp,
                                 payload=payload)
    yield gen.Task(analytics.Update, client)

    # Terminate the user account.
    yield gen.Task(User.TerminateAccount, client, user_id, merged_with=merged_with)

    # Notify all friends that this user account has been terminated.
    yield NotificationManager.NotifyTerminateAccount(client, user_id)

  @classmethod
  @gen.engine
  def UpdateOperation(cls, client, callback, user_dict, settings_dict):
    """Invokes User.Update via operation execution."""
    yield gen.Task(User.UpdateWithSettings, client, user_dict, settings_dict)

    timestamp = Operation.GetCurrent().timestamp
    yield NotificationManager.NotifyUpdateUser(client, user_dict, settings_dict, timestamp)

    callback()
