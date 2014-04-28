# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Validates db objects during testing.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import json

from collections import defaultdict, namedtuple
from copy import deepcopy
from viewfinder.backend.base import message, util
from viewfinder.backend.db.accounting import Accounting
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.analytics import Analytics
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.followed import Followed
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.friend import Friend
from viewfinder.backend.db.id_allocator import IdAllocator
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.notification import Notification
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint


DBObjectKey = namedtuple('DBObjectKey', ['db_class', 'db_key'])
"""DB objects are indexed in the model using this key."""


class DBValidator(object):
  """Contains a set of methods which validate the correctness of
  objects in the database.

  In order to validate the correctness of the present state of an
  object, it is useful to know the previous state of that object
  before it was operated on. The validator achieves this by
  keeping a replica of the database, called the "model". As objects
  are validated, the model is kept up-to-date. Validation methods
  can use the model objects in order to determine what the present
  state of the database should be.
  """
  def __init__(self, client, stop, wait):
    self.client = client
    self._stop = stop
    self._wait = wait
    self._model = dict()

  def Cleanup(self, validate=False):
    """Deletes all objects that were created in the context of the model.
    If validate=True, then validates all objects before the cleanup by
    comparing them against the database.
    """
    if validate:
      for dbo_key, dbo in self._model.items():
        self._ValidateDBObject(dbo_key.db_class, dbo_key.db_key)

    for dbo_key, dbo in self._model.items():
      if dbo is not None:
        self._RunAsync(dbo.Delete, self.client)


  # =================================================================
  #
  # Model management methods.
  #
  # =================================================================

  def GetModelObject(self, cls, key, must_exist=True):
    """Gets a DBObject from the model that has the specified class and key.
    If "must_exist" is true, raises an exception if the object is not
    present in the model. Otherwise, returns the object, or None if it is
    not present in the model.
    """
    if not isinstance(key, DBKey):
      assert cls._table.range_key_col is None, 'key must be of type DBKey for range tables'
      key = DBKey(hash_key=key, range_key=None)

    dbo_key = DBObjectKey(cls, key)
    dbo = self._model.get(dbo_key, None)
    assert not must_exist or dbo is not None, '%s "%s" does not exist' % (cls.__name__, key)

    return dbo

  def QueryModelObjects(self, cls, hash_key=None, predicate=None, limit=None, start_key=None,
                        query_forward=True):
    """Returns all DBObjects from the model that:

       1. Are of the specified class.
       2. Have the specified hash key.
       3. Match the predicate (predicate takes DBObject as argument).
       4. Have a key greater than start_key, if not None.

    Returns only up to "limit" DBObjects, and return in sorted order if
    query_forward is True, or reverse sorted order otherwise.
    """
    matches = [dbo
               for key, dbo in self._model.items()
               if dbo and key.db_class == cls
               if hash_key is None or key.db_key.hash_key == hash_key
               if start_key is None or (key.db_key.range_key > start_key
                                        if query_forward else
                                        start_key > key.db_key.range_key)
               if predicate is None or predicate(dbo)]

    matches.sort(key=lambda x: x.GetKey(), reverse=not query_forward)
    return matches[:limit]

  def AddModelObject(self, dbo):
    """Add the specified DBObject to the list of objects tracked by the model."""
    dbo_key = DBObjectKey(dbo.__class__, dbo.GetKey())
    self._model[dbo_key] = dbo


  # =================================================================
  #
  # Simple single object validation methods.
  #
  # =================================================================

  def ValidateCreateDBObject(self, cls, **db_dict):
    """Validates that an object of type "cls" was created in the database,
    assuming it did not already exist. If it was created, validates that
    its attributes match those in "db_dict", else validates that its
    attributes match those of the existing object in the model. All
    attributes in "db_dict" are explicitly checked, even if they'd
    normally be ignored by ValidateDBObject. Returns the object.
    """
    dbo = cls.CreateFromKeywords(**db_dict)
    existing_dbo = self.GetModelObject(dbo.__class__, dbo.GetKey(), must_exist=False)
    if not existing_dbo:
      self.AddModelObject(dbo)
      existing_dbo = dbo
    self._ValidateDBObject(dbo.__class__, dbo.GetKey(), must_check_dict=db_dict)
    return existing_dbo

  def ValidateUpdateDBObject(self, cls, **db_dict):
    """Validates that an object of type "cls" was created in the database
    if it did not already exist. Validates that the attributes of the new
    or existing object were updated to match those in "db_dict". All
    attributes in "db_dict" are explicitly checked, even if they'd normally
    be ignored by ValidateDBObject. Invokes the callback with the object.
    """
    dbo = cls.CreateFromKeywords(**db_dict)
    existing_dbo = self.GetModelObject(dbo.__class__, dbo.GetKey(), must_exist=False)
    if not existing_dbo:
      # Add the new object to the model.
      self.AddModelObject(dbo)
      existing_dbo = dbo
    else:
      # Update the existing object in the model.
      existing_dbo.UpdateFromKeywords(**db_dict)

    # Now validate against the object in the database. Never ignore any updated attributes during comparison.
    self._ValidateDBObject(dbo.__class__, dbo.GetKey(), must_check_dict=db_dict)
    return existing_dbo

  def ValidateDeleteDBObject(self, cls, key):
    """Validates that the object with the specified key was deleted from
    the database.
    """
    if not isinstance(key, DBKey):
      assert cls._table.range_key_col is None, 'key must be of type DBKey for range tables'
      key = DBKey(hash_key=key, range_key=None)

    dbo_key = DBObjectKey(cls, key)
    self._model[dbo_key] = None

    self._ValidateDBObject(cls, key)


  # =================================================================
  #
  # Multiple object validation methods.
  #  - Shared by multiple operations
  #
  # =================================================================

  def ValidateCreateContact(self, user_id, identities_properties, timestamp, contact_source, **op_dict):
    """Validates creation of contact along with derived attributes.
    Returns created contact.
    """
    contact_dict = op_dict
    contact_dict['user_id'] = user_id
    contact_dict['timestamp'] = timestamp
    if identities_properties is not None:
      contact_dict['identities_properties'] = identities_properties
      contact_dict['identities'] = set([Identity.Canonicalize(identity_properties[0])
                                        for identity_properties in identities_properties])
    else:
      contact_dict['identities_properties'] = None
    contact_dict['contact_source'] = contact_source
    if 'contact_id' not in contact_dict:
      contact_dict['contact_id'] = Contact.CalculateContactId(contact_dict)
    if 'sort_key' not in contact_dict:
      contact_dict['sort_key'] = Contact.CreateSortKey(contact_dict['contact_id'], timestamp)

    return self.ValidateCreateDBObject(Contact, **contact_dict)

  def ValidateCreateProspectiveUsers(self, op_dict, contacts):
    """Validates that a prospective user has been created for any contact which is not yet
    associated with Viewfinder user. Returns all resolved users.
    """
    users = []
    for contact_dict in contacts:
      # Look up user in the model.
      if 'user_id' in contact_dict:
        users.append(self.GetModelObject(User, contact_dict['user_id']))
      else:
        # Look up identity and user in db in order to get various server-generated ids.
        identity_key = contact_dict['identity']
        actual_ident = self._RunAsync(Identity.Query, self.client, identity_key, None)
        actual_user = self._RunAsync(User.Query, self.client, actual_ident.user_id, None)

        # Determine whether the op is causing a new prospective user to be created.
        expected_user = self.GetModelObject(User, actual_user.user_id, must_exist=False)

        if expected_user is None:
          user_dict = {'user_id': actual_user.user_id,
                       'webapp_dev_id': actual_user.webapp_dev_id}
          identity_type, value = identity_key.split(':', 1)
          if identity_type == 'Email':
            user_dict['email'] = value
          elif identity_type == 'Phone':
            user_dict['phone'] = value
          ident_dict = {'key': identity_key, 'authority': 'Viewfinder'}
          self.ValidateUpdateUser('create prospective user',
                                  op_dict,
                                  user_dict,
                                  ident_dict,
                                  device_dict=None,
                                  is_prospective=True)

          analytics = Analytics.Create(entity='us:%d' % actual_user.user_id,
                                       type=Analytics.USER_CREATE_PROSPECTIVE)
          self.ValidateCreateDBObject(Analytics, **analytics._asdict())

        users.append(actual_user)

    return users

  def ValidateFollower(self, user_id, viewpoint_id, labels, last_updated,
                       timestamp=None, adding_user_id=None, viewed_seq=None):
    """Validates that Follower and Followed records have been created or updated in the database
    for user "user_id" and viewpoint "viewpoint_id".

    Returns the follower.
    """
    follower_dict = {'user_id': user_id,
                     'viewpoint_id': viewpoint_id,
                     'labels': labels}
    util.SetIfNotNone(follower_dict, 'timestamp', timestamp)
    util.SetIfNotNone(follower_dict, 'adding_user_id', adding_user_id)
    util.SetIfNotNone(follower_dict, 'viewed_seq', viewed_seq)
    follower = self.ValidateUpdateDBObject(Follower, **follower_dict)

    self._ValidateUpdateFollowed(user_id, viewpoint_id, None, last_updated)

    return follower

  def ValidateUpdateUser(self, name, op_dict, user_dict, ident_dict,
                         device_dict=None, is_prospective=False):
    """Validates that a user and identity have been created in the database
    if they did not already exist, or were updated if they did. If
    "device_dict" is defined, validates that a device was created or updated
    as well.
    """
    user_id = user_dict['user_id']

    # Validate creation of the default viewpoint, follower, and followed record.
    viewpoint_id = Viewpoint.ConstructViewpointId(user_dict['webapp_dev_id'], 0)
    viewpoint = self.GetModelObject(User, user_id, must_exist=False)
    if viewpoint is None:
      expected_viewpoint = self.ValidateCreateDBObject(Viewpoint,
                                                       viewpoint_id=viewpoint_id,
                                                       user_id=user_id,
                                                       timestamp=op_dict['op_timestamp'],
                                                       last_updated=op_dict['op_timestamp'],
                                                       type=Viewpoint.DEFAULT,
                                                       update_seq=0)

      labels = Follower.PERMISSION_LABELS + [Follower.PERSONAL]
      expected_follower = self.ValidateFollower(user_id=user_id,
                                                viewpoint_id=viewpoint_id,
                                                timestamp=op_dict['op_timestamp'],
                                                labels=labels,
                                                last_updated=op_dict['op_timestamp'],
                                                viewed_seq=0)

    # Validate User object.
    scratch_user_dict = deepcopy(user_dict)
    if ident_dict.get('authority', None) == 'Facebook' and user_dict.get('email', None):
      scratch_user_dict['facebook_email'] = user_dict['email']

    union_label = [] if is_prospective else [User.REGISTERED]
    existing_user = self.GetModelObject(User, user_id, must_exist=False)
    if existing_user is None:
      is_registering = False
      before_user_dict = None
      scratch_user_dict['private_vp_id'] = viewpoint_id
      scratch_user_dict['labels'] = union_label
    else:
      is_registering = not existing_user.IsRegistered()
      before_user_dict = existing_user._asdict()
      scratch_user_dict.update(before_user_dict)
      scratch_user_dict['labels'] = list(set(scratch_user_dict['labels']).union(union_label))

    expected_user = self.ValidateUpdateDBObject(User, **scratch_user_dict)

    # Validate AccountSettings object.
    settings = AccountSettings.CreateForUser(user_id)

    if device_dict is None:
      if self.GetModelObject(AccountSettings, settings.GetKey(), must_exist=False) is None:
        # First web device was registered, so validate that emails or sms messages are turned on.
        settings.push_alerts = AccountSettings.PUSH_NONE
        settings.email_alerts = AccountSettings.EMAIL_NONE
        settings.sms_alerts = AccountSettings.SMS_NONE

        identity_type, identity_value = Identity.SplitKey(ident_dict['key'])
        if identity_type == 'Email':
          settings.email_alerts = AccountSettings.EMAIL_ON_SHARE_NEW
        elif identity_type == 'Phone':
          settings.sms_alerts = AccountSettings.SMS_ON_SHARE_NEW
    else:
      if len(self.QueryModelObjects(Device, user_id)) == 0:
        # First mobile device was registered, so validate that emails and sms messages are
        # turned off and push alerts turned on.
        settings.push_alerts = AccountSettings.PUSH_ALL
        settings.email_alerts = AccountSettings.EMAIL_NONE
        settings.sms_alerts = AccountSettings.SMS_NONE

    self.ValidateUpdateDBObject(AccountSettings, **settings._asdict())

    # Validate Friend object.
    self.ValidateUpdateDBObject(Friend, user_id=user_id, friend_id=user_id)

    # Validate Identity object.
    existing_identity = self.GetModelObject(Identity, ident_dict['key'], must_exist=False)
    expected_ident = self.ValidateUpdateDBObject(Identity,
                                                 user_id=user_id,
                                                 **ident_dict)

    # Validate Device object.
    if device_dict is not None:
      update_dict = {'user_id': user_id,
                     'timestamp': util._TEST_TIME,
                     'last_access': util._TEST_TIME}
      if 'push_token' in device_dict:
        update_dict['alert_user_id'] = user_id
      update_dict.update(device_dict)
      expected_device = self.ValidateUpdateDBObject(Device, **update_dict)

      # Validate that any other devices with same push token have had their tokens revoked.
      if 'push_token' in device_dict:
        predicate = lambda d: d.device_id != expected_device.device_id and d.push_token == expected_device.push_token
        other_devices = self.QueryModelObjects(Device, predicate=predicate)
        for device in other_devices:
          self.ValidateUpdateDBObject(Device,
                                      user_id=device.user_id,
                                      device_id=device.device_id,
                                      push_token=None,
                                      alert_user_id=None)

    # Validate Contact objects.
    if existing_identity is None or is_registering:
      self.ValidateRewriteContacts(expected_ident.key, op_dict)

    # Validate contact notifications.
    self.ValidateContactNotifications(name, expected_ident.key, op_dict)

    # Validate Friend notifications.
    after_user_dict = self.GetModelObject(User, user_id)._asdict()
    if before_user_dict != after_user_dict and not is_prospective:
      invalidate = {'users': [user_id]}
      self.ValidateFriendNotifications('register friend', user_id, op_dict, invalidate)

    # Validate analytics entry for Register.
    if existing_user is None:
      # User is being created for the first time, it must have a CREATE_PROSPECTIVE analytics entry.
      analytics = Analytics.Create(entity='us:%d' % user_id,
                                   type=Analytics.USER_CREATE_PROSPECTIVE)
      self.ValidateCreateDBObject(Analytics, **analytics._asdict())

    if (not existing_user or is_registering) and not is_prospective:
      # User is being registered.
      analytics = Analytics.Create(entity='us:%d' % user_id,
                                   type=Analytics.USER_REGISTER)
      self.ValidateCreateDBObject(Analytics, **analytics._asdict())

  def ValidateRewriteContacts(self, identity_key, op_dict):
    """Validates that all contacts that reference "identity_key" have been updated with the
    new timestamp.
    """
    # Iterate over all contacts that reference the identity.
    for co in self.QueryModelObjects(Contact, predicate=lambda co: identity_key in co.identities):
      # Validate that contact has been updated.
      contact_dict = co._asdict()
      contact_dict['timestamp'] = op_dict['op_timestamp']
      sort_key = Contact.CreateSortKey(Contact.CalculateContactId(contact_dict), contact_dict['timestamp'])
      contact_dict['sort_key'] = sort_key
      self.ValidateUpdateDBObject(Contact, **contact_dict)

      # Validate that any old contacts have been deleted.
      if sort_key != co.sort_key:
        self.ValidateDeleteDBObject(Contact, co.GetKey())

  def ValidateFriendsInGroup(self, user_ids):
    """Validates that all specified users are friends with each other."""
    for index, user_id in enumerate(user_ids):
      for friend_id in user_ids[index + 1:]:
        if user_id != friend_id:
          user1 = self.GetModelObject(User, user_id)
          user2 = self.GetModelObject(User, friend_id)

          self.ValidateUpdateDBObject(Friend, user_id=user_id, friend_id=friend_id)
          self.ValidateUpdateDBObject(Friend, user_id=friend_id, friend_id=user_id)

  def ValidateCopyEpisodes(self, op_dict, viewpoint_id, ep_dicts):
    """Validates that a set of episodes and posts have been created within the specified
    viewpoint via a sharing or save operation.
    """
    ph_act_dict = {}
    for ep_dict in ep_dicts:
      existing_episode = self.GetModelObject(Episode, ep_dict['existing_episode_id'])

      new_ep_dict = {'episode_id': ep_dict['new_episode_id'],
                     'parent_ep_id': ep_dict['existing_episode_id'],
                     'user_id': op_dict['user_id'],
                     'viewpoint_id': viewpoint_id,
                     'timestamp': existing_episode.timestamp,
                     'publish_timestamp': op_dict['op_timestamp'],
                     'location': existing_episode.location,
                     'placemark': existing_episode.placemark}
      self.ValidateCreateDBObject(Episode, **new_ep_dict)

      for photo_id in ep_dict['photo_ids']:
        post = self.GetModelObject(Post, DBKey(ep_dict['new_episode_id'], photo_id), must_exist=False)
        if post is None or post.IsRemoved():
          if post is None:
            self.ValidateCreateDBObject(Post, episode_id=ep_dict['new_episode_id'], photo_id=photo_id)
          else:
            self.ValidateUpdateDBObject(Post, episode_id=ep_dict['new_episode_id'], photo_id=photo_id, labels=[])
          ph_act_dict.setdefault(viewpoint_id, {}).setdefault(ep_dict['new_episode_id'], []).append(photo_id)

  def ValidateCoverPhoto(self, viewpoint_id, unshare_ep_dicts=None):
    """Validate that a cover_photo is set on a viewpoint.  Selects a new cover_photo if
    there currently isn't one or the current one is no longer shared in the viewpoint.
    Returns: True if viewpoint's cover_photo value changed, otherwise False.
    """
    current_model_cover_photo = self.GetModelObject(Viewpoint, viewpoint_id).cover_photo

    exclude_posts_set = set()
    if unshare_ep_dicts is not None:
      exclude_posts_set = set([(episode_id, photo_id)
                               for (episode_id, photo_ids) in unshare_ep_dicts.items()
                               for photo_id in photo_ids])
    elif current_model_cover_photo is not None:
      # No unshares and a cover photo is already set, so we don't do anything.
      return False

    # Take a shortcut here and call the implementation to select the photo.  If we start
    #   seeing bugs in this area, we may want to do a test model implementation.
    # We use the actual db because that already has all the activities written to it that
    #   SelectCoverPhoto() depends on.
    viewpoint = self._RunAsync(Viewpoint.Query, self.client, viewpoint_id, col_names=None)
    selected_cover_photo = self._RunAsync(viewpoint.SelectCoverPhoto, self.client, exclude_posts_set)

    if current_model_cover_photo != selected_cover_photo:
      # Update cover_photo with whatever we've got at this point.
      self.ValidateUpdateDBObject(Viewpoint,
        viewpoint_id=viewpoint_id,
        cover_photo=selected_cover_photo)
    return current_model_cover_photo != selected_cover_photo

  def ValidateUnlinkIdentity(self, op_dict, identity_key):
    """Validates that the specified identity was properly unlinked from the attached user."""
    identity = self.GetModelObject(Identity, identity_key, must_exist=False)

    # Validate that the identity has been removed.
    self.ValidateDeleteDBObject(Identity, identity_key)

    # Validate that all contacts have been unlinked from the user.
    self.ValidateRewriteContacts(identity_key, op_dict)

    # Validate contact notifications.
    self.ValidateContactNotifications('unlink_identity', identity_key, op_dict)

    # Validate user notification for the owner of the identity (if it existed).
    if identity:
      self.ValidateUserNotification('unlink_self', op_dict['user_id'], op_dict)

  def ValidateReviveRemovedFollowers(self, viewpoint_id, op_dict):
    """Validates that the REMOVED followers label has been removed from viewpoint followers.
    Removed followers should be revived by any structural changes to their viewpoints.
    """
    follower_matches = lambda f: f.viewpoint_id == viewpoint_id
    for follower in self.QueryModelObjects(Follower, predicate=follower_matches):
      if follower.IsRemoved() and not follower.IsUnrevivable():
        follower.labels.remove(Follower.REMOVED)
        follower.labels = follower.labels.combine()
        self.ValidateUpdateDBObject(Follower,
                                    user_id=follower.user_id,
                                    viewpoint_id=follower.viewpoint_id,
                                    labels=follower.labels)

        self.ValidateNotification('revive followers',
                                  follower.user_id,
                                  op_dict,
                                  DBValidator.CreateViewpointInvalidation(viewpoint_id),
                                  viewpoint_id=viewpoint_id)

  def ValidateTerminateAccount(self, user_id, op_dict, merged_with=None):
    """Validates that the given user's account has been terminated."""
    # Validate that all alerts have been stopped to user devices.
    devices = self.QueryModelObjects(Device, predicate=lambda d: d.user_id == user_id)
    for device in devices:
      self.ValidateUpdateDBObject(Device,
                                  user_id=user_id,
                                  device_id=device.device_id,
                                  alert_user_id=None)

    # Validate that all identities attached to the user have been unlinked.
    identities = self.QueryModelObjects(Identity, predicate=lambda i: i.user_id == user_id)
    for identity in identities:
      self.ValidateUnlinkIdentity(op_dict, identity.key)

    # Validate that "terminated" label is added to User object.
    user = self.GetModelObject(User, user_id)
    labels = user.labels.union([User.TERMINATED])
    self.ValidateUpdateDBObject(User, user_id=user_id, labels=labels, merged_with=merged_with)

    # Validate notifications to friends of the user account.
    invalidate = {'users': [user_id]}
    self.ValidateFriendNotifications('terminate_account', user_id, op_dict, invalidate)

    # Validate analytics entry.
    analytics = Analytics.Create(entity='us:%d' % user_id,
                                 type=Analytics.USER_TERMINATE)
    self.ValidateCreateDBObject(Analytics, **analytics._asdict())

  def ValidateAccounting(self):
    """Validates accounting stats for all viewpoints and users."""
    desired_act = {}

    def _SetOrIncrement(act):
      key = (act.hash_key, act.sort_key)
      if key not in desired_act:
        desired_act[key] = act
      else:
        desired_act[key].IncrementStatsFrom(act)

    followers = defaultdict(list)
    all_followers, _ = self._RunAsync(Follower.Scan, self.client, None)
    for follower in all_followers:
      followers[follower.viewpoint_id].append(follower)

    all_viewpoints, _ = self._RunAsync(Viewpoint.Scan, self.client, None)
    for viewpoint in all_viewpoints:
      # Validate the viewpoint accounting stats.
      self.ValidateViewpointAccounting(viewpoint.viewpoint_id)

      # Get accounting for the viewpoint.
      vp_vt_act = Accounting.CreateViewpointVisibleTo(viewpoint.viewpoint_id)
      vp_vt_act = self.GetModelObject(Accounting, vp_vt_act.GetKey(), must_exist=False) or vp_vt_act

      # Increment user-level accounting stats.
      for follower in followers[viewpoint.viewpoint_id]:
        if not follower.IsRemoved():
          # Add to follower's accounting.
          us_vt_act = Accounting.CreateUserVisibleTo(follower.user_id)
          us_vt_act.CopyStatsFrom(vp_vt_act)
          _SetOrIncrement(us_vt_act)

          vp_sb_act = Accounting.CreateViewpointSharedBy(viewpoint.viewpoint_id, follower.user_id)
          vp_sb_act = self.GetModelObject(Accounting, vp_sb_act.GetKey(), must_exist=False) or vp_sb_act

          us_sb_act = Accounting.CreateUserSharedBy(follower.user_id)
          us_sb_act.CopyStatsFrom(vp_sb_act)
          _SetOrIncrement(us_sb_act)

    for key, value in desired_act.iteritems():
      # Absence of accounting record is equivalent to zero-value accounting record.
      if value.IsZero():
        act = self._RunAsync(Accounting.KeyQuery, self.client, value.GetKey(), None, must_exist=False)
        if act is None:
          continue

      self.ValidateUpdateDBObject(Accounting, **value._asdict())

  def ValidateViewpointAccounting(self, viewpoint_id):
    """Validates the given viewpoint's accounting stats by iterating over all viewable photos
    and adding up the expected stats for each.
    """
    desired_act = {}

    def _SetOrIncrement(act):
      key = (act.hash_key, act.sort_key)
      if key not in desired_act:
        desired_act[key] = act
      else:
        desired_act[key].IncrementStatsFrom(act)

    viewpoint = self._RunAsync(Viewpoint.Query, self.client, viewpoint_id, None)
    episodes, _ = self._RunAsync(Viewpoint.QueryEpisodes, self.client, viewpoint_id)
    for episode in episodes:
      act = Accounting()
      posts = self._RunAsync(Post.RangeQuery, self.client, episode.episode_id, None, None, None)
      for post in posts:
        if post.IsRemoved():
          continue

        photo = self._RunAsync(Photo.Query, self.client, post.photo_id, None)
        act.IncrementFromPhotos([photo])

      # Get follower record of owner of the episode.
      follower = self._RunAsync(Follower.Query, self.client, episode.user_id, viewpoint_id, None)

      if viewpoint.IsDefault():
        # Default viewpoint. only "owned by" types are filled in.
        if not follower.IsRemoved():
          vp_ob_act = Accounting.CreateViewpointOwnedBy(viewpoint_id, episode.user_id)
          vp_ob_act.CopyStatsFrom(act)
          _SetOrIncrement(vp_ob_act)

        us_ob_act = Accounting.CreateUserOwnedBy(episode.user_id)
        us_ob_act.CopyStatsFrom(act)
        _SetOrIncrement(us_ob_act)
      else:
        # Shared viewpoint - fill in "shared by" and "visible to".
        vp_sb_act = Accounting.CreateViewpointSharedBy(viewpoint_id, episode.user_id)
        vp_sb_act.CopyStatsFrom(act)
        _SetOrIncrement(vp_sb_act)

        vp_vt_act = Accounting.CreateViewpointVisibleTo(viewpoint_id)
        vp_vt_act.CopyStatsFrom(act)
        _SetOrIncrement(vp_vt_act)

    for key, value in desired_act.iteritems():
      # Absence of accounting record is equivalent to zero-value accounting record.
      if value.IsZero() and self.GetModelObject(Accounting, value.GetKey(), must_exist=False) == None:
          continue
      self.ValidateUpdateDBObject(Accounting, **value._asdict())

  def ValidateFollowerNotifications(self, viewpoint_id, activity_dict, op_dict, invalidate, sends_alert=False):
    """Validates that a notification has been created for each follower of the specified
    viewpoint. If "invalidate" is a dict, then each follower uses that as its invalidation.
    Otherwise, it is assumed to be a func that returns the invalidation, given the id of the
    follower. Validates that an activity was created in the viewpoint.

    The "activity_dict" must contain expected "activity_id", "timestamp", and "name" fields.
    The "op_dict" must contain expected "user_id", "device_id", "op_id", and "op_timestamp"
    fields.
    """
    # Validate that last_updated and update_seq have been properly updated.
    viewpoint = self.GetModelObject(Viewpoint, viewpoint_id)
    old_timestamp = viewpoint.last_updated
    new_timestamp = max(old_timestamp, op_dict['op_timestamp'])
    update_seq = 1 if viewpoint.update_seq is None else viewpoint.update_seq + 1
    self.ValidateUpdateDBObject(Viewpoint,
                                viewpoint_id=viewpoint_id,
                                last_updated=new_timestamp,
                                update_seq=update_seq)

    # Validate new Activity object.
    activity_dict = deepcopy(activity_dict)
    activity = self.ValidateCreateDBObject(Activity,
                                           viewpoint_id=viewpoint_id,
                                           activity_id=activity_dict.pop('activity_id'),
                                           timestamp=activity_dict.pop('timestamp'),
                                           name=activity_dict.pop('name'),
                                           user_id=op_dict['user_id'],
                                           update_seq=update_seq,
                                           json=util.ToCanonicalJSON(activity_dict))

    # Validate revival of removed followers in most cases.
    if activity.name not in ['unshare', 'remove_followers']:
      self.ValidateReviveRemovedFollowers(viewpoint_id, op_dict)

    # Validate that a notification was created for each follower.
    follower_matches = lambda f: f.viewpoint_id == viewpoint_id
    for follower in self.QueryModelObjects(Follower, predicate=follower_matches):
      if not follower.IsRemoved() or activity.name in ['remove_followers']:
        # Validate that sending follower had its viewed_seq field incremented.
        if follower.user_id == op_dict['user_id']:
          viewed_seq = 1 if follower.viewed_seq is None else follower.viewed_seq + 1
          self.ValidateUpdateDBObject(Follower,
                                      user_id=follower.user_id,
                                      viewpoint_id=viewpoint_id,
                                      viewed_seq=viewed_seq)
        else:
          viewed_seq = None

        # Validate that the Followed row for this follower had its timestamp updated.
        self._ValidateUpdateFollowed(follower.user_id, viewpoint_id, old_timestamp, new_timestamp)

        if invalidate is None or isinstance(invalidate, dict):
          foll_invalidate = invalidate
        else:
          foll_invalidate = invalidate(follower.user_id)

        # Validate that a new notification was created for this follower.
        self.ValidateNotification(activity.name,
                                  follower.user_id,
                                  op_dict,
                                  foll_invalidate,
                                  activity_id=activity.activity_id,
                                  viewpoint_id=viewpoint_id,
                                  sends_alert=sends_alert,
                                  seq_num_pair=(update_seq, viewed_seq))

  def ValidateFriendNotifications(self, name, user_id, op_dict, invalidate):
    """Validates that a notification was created for each friend of the given user, as well as
    the user himself.
    """
    for friend in self.QueryModelObjects(Friend, predicate=lambda fr: fr.user_id == user_id):
      self.ValidateNotification(name, friend.friend_id, op_dict, invalidate)

  def ValidateContactNotifications(self, name, identity_key, op_dict):
    """Validates that a notification was created for each user who
    references a contact of the specified identity.
    """
    invalidate = {'contacts': {'start_key': Contact.CreateSortKey(None, op_dict['op_timestamp'])}}
    for co in self.QueryModelObjects(Contact, predicate=lambda co: identity_key in co.identities):
      self.ValidateNotification(name, co.user_id, op_dict, invalidate)

  def ValidateUserNotification(self, name, user_id, op_dict):
    """Validates that a notification was created for the specified user."""
    self.ValidateNotification(name, user_id, op_dict, {'users': [user_id]})

  def ValidateNotification(self, name, target_user_id, op_dict, invalidate,
                           activity_id=None, viewpoint_id=None, seq_num_pair=None, sends_alert=False):
    """Validates that a notification with the specified name and invalidation
    has been created for "target_user_id".

    The "op_dict" must contain expected "user_id", "device_id", and
    "op_timestamp" fields. It may contain "op_id", if its expected value
    is known to the caller.
    """
    # Validate that new notification is based on previous notification.
    notifications = self.QueryModelObjects(Notification, target_user_id)
    last_notification = notifications[-1] if notifications else None

    notification_id = last_notification.notification_id + 1 if last_notification is not None else 1
    if invalidate is not None:
      invalidate = deepcopy(invalidate)
      invalidate['headers'] = dict(version=message.MAX_MESSAGE_VERSION)
      invalidate = json.dumps(invalidate)

    badge = last_notification.badge if last_notification is not None else 0
    if sends_alert and target_user_id != op_dict['user_id']:
      badge += 1

    self.ValidateCreateDBObject(Notification,
                                notification_id=notification_id,
                                user_id=target_user_id,
                                name=name,
                                timestamp=op_dict['op_timestamp'],
                                sender_id=op_dict['user_id'],
                                sender_device_id=op_dict['device_id'],
                                invalidate=invalidate,
                                badge=badge,
                                activity_id=activity_id,
                                viewpoint_id=viewpoint_id,
                                update_seq=None if seq_num_pair is None else seq_num_pair[0],
                                viewed_seq=None if seq_num_pair is None else seq_num_pair[1])

    # Optionally validate the op_id field, if it was passed in op_dict.
    if 'op_id' in op_dict:
      self.ValidateUpdateDBObject(Notification,
                                  notification_id=notification_id,
                                  user_id=target_user_id,
                                  op_id=op_dict['op_id'])

  @classmethod
  def CreateViewpointInvalidation(cls, viewpoint_id):
    """Create invalidation for entire viewpoint, including all metadata and all collections.

    NOTE: Make sure to update this when new viewpoint collections are added.
    """
    return {'viewpoints': [{'viewpoint_id': viewpoint_id,
                            'get_attributes': True,
                            'get_followers': True,
                            'get_activities': True,
                            'get_episodes': True,
                            'get_comments': True}]}


  # =================================================================
  #
  # Helper methods.
  #
  # =================================================================

  def _ValidateUpdateFollowed(self, user_id, viewpoint_id, old_timestamp, new_timestamp):
    """Validate that an older Followed record was deleted and a newer created."""
    if old_timestamp is not None and \
       Followed._TruncateToDay(new_timestamp) > Followed._TruncateToDay(old_timestamp):
      db_key = DBKey(user_id, Followed.CreateSortKey(viewpoint_id, old_timestamp))
      self.ValidateDeleteDBObject(Followed, db_key)

    self.ValidateCreateDBObject(Followed,
                                user_id=user_id,
                                viewpoint_id=viewpoint_id,
                                sort_key=Followed.CreateSortKey(viewpoint_id, new_timestamp),
                                date_updated=Followed._TruncateToDay(new_timestamp))

  def _RunAsync(self, func, *args, **kwargs):
    """Runs an async function which takes a callback argument. Waits for
    the function to complete and returns any result.
    """
    func(callback=self._stop, *args, **kwargs)
    return self._wait()

  def _ValidateDBObject(self, cls, key, must_check_dict=None):
    """Validates that a model object of type "cls", and with the specified
    key is equivalent to the actual DBObject that exists (or not) in the
    database. Always checks attributes in "must_check_dict", even if
    normally the attribute would be ignored.
    """
    # Get the expected object from the model.
    expected_dbo = self.GetModelObject(cls, key, must_exist=False)
    if expected_dbo is not None:
      expected_dict = self._SanitizeDBObject(expected_dbo, must_check_dict)
      expected_json = util.ToCanonicalJSON(expected_dict, indent=True)
    else:
      expected_json = None

    # Get the actual object to validate from the database.
    actual_dbo = self._RunAsync(cls.KeyQuery, self.client, key, None, must_exist=False)
    if actual_dbo is not None:
      actual_dict = self._SanitizeDBObject(actual_dbo, must_check_dict)
      actual_json = util.ToCanonicalJSON(actual_dict, indent=True)
    else:
      actual_json = None

    if expected_json != actual_json:
      # Special-case notifications in order to show all notifications for the user to aid in debugging.
      if cls == Notification and expected_dbo is not None:
        expected_seq = self.QueryModelObjects(Notification, expected_dbo.user_id)
        actual_seq = self._RunAsync(Notification.RangeQuery, self.client, expected_dbo.user_id, None, None, None)

        raise AssertionError("DBObject difference detected.\n\nEXPECTED (%s): %s\n%s\n\nACTUAL (%s): %s\n%s\n" % \
                             (type(expected_dbo).__name__, expected_json, [n.name for n in expected_seq],
                              type(actual_dbo).__name__, actual_json, [n.name for n in actual_seq]))
      else:
        raise AssertionError("DBObject difference detected.\n\nEXPECTED (%s): %s\n\nACTUAL (%s): %s\n" % \
                             (type(expected_dbo).__name__, expected_json, type(actual_dbo).__name__, actual_json))

  def _SanitizeDBObject(self, dbo, must_check_dict):
    """Converts dbo to a dict, and then removes attributes from it that
    should be ignored when comparing DBObjects with each other.
    """
    dbo_dict = dbo._asdict()

    remove_dict = {Accounting: set(['op_ids']),
                   AccountSettings: set(['sms_count']),
                   Analytics: set(['payload']),
                   Follower: set(['viewed_seq']),
                   IdAllocator: set(['next_id']),
                   Identity: set(['last_fetch', 'token_guesses', 'token_guesses_time', 'json_attrs', 'auth_throttle']),
                   Notification: set(['op_id']),
                   User: set(['asset_id_seq', 'signing_key', 'pwd_hash', 'salt']),
                   Viewpoint: set(['last_updated', 'update_seq'])}

    for key, value in dbo_dict.items():
      # Always remove _version attribute.
      dbo_dict.pop('_version', None)

      # Normalize any lists.
      if isinstance(value, list):
        dbo_dict[key] = sorted(value)

      # Normalize the order of attributes embedded in json_attr.
      if key == 'json' or key == 'invalidate':
        json_dict = json.loads(value)
        json_dict.pop('headers', None)
        dbo_dict[key] = util.ToCanonicalJSON(json_dict)

      # Remove certain attributes from certain types.
      remove_set = remove_dict.get(type(dbo), [])
      if key in remove_set and (must_check_dict is None or key not in must_check_dict):
        del dbo_dict[key]

    return dbo_dict
