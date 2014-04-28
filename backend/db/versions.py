# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Feature versions and data migration.

Versions describe how new features or functionality should change the
data in a row (aka an item) of the table. For example, new columns
might be added, old columns deprecated, values transformed, the
indexing algorithm changed, etc. Each version 'tag' refers to a
function which makes the relevant changes to the an item. The item can
then be updated in the table with its version # updated to the number
of the tag. This mechanism allows a sequential scan (as implemented in
backend/db/tools/upgrade.py) to migrate all rows in a table. It also
allows changes to be made lazily, where items are upgraded in
arbitrary batches. Any new features not reflected in the item's
version # are applied in order, automatically. If the item is then
updated, the new version # and the transformations are preserved, but
this isn't necessary.

Some features, such as a change in indexing, should be migrated in toto
via db/tools/upgrade. Other features, such as deprecating a column,
can be done piecemeal, with items which are never accessed being updated
only on the next full table migration.

The ordinality of features is important as any set of transformations
which must take place on a row may have ordered dependencies.
"""

import json
import logging
import time

from functools import partial
from tornado import gen, httpclient
from viewfinder.backend.base import message, util, retry, secrets
from viewfinder.backend.base.context_local import ContextLocal

class Version(object):
  """The version base class. Provides a guarantee that rank order is
  correct (that careless code updating doesn't confuse the ordering of
  versions).

  When authoring a version migrator, do not assume that the version
  is correct. There are cases where it can "get behind". So, for
  example, while the version on the row = 5, the actual row data
  corresponds to version 8. However, the reverse *cannot* happen;
  if the version = 8, then the actual row data cannot correspond
  to version 5. So if a row version shows the row is at the latest
  version, then there is no need to migrate.
  """
  _DELETED_MIGRATOR_COUNT = 16
  """If older migrators are deleted, update this."""

  _version_classes = set()
  _rank_ordering = []
  _mutate_items = True
  _allow_s3_queries = True

  _migrate_retry_policy = retry.RetryPolicy(max_tries=5, min_delay=1,
                                            check_exception=lambda type, value, tb: True)
  """Retry migration of an item up to 5 times before giving up."""

  def __init__(self):
    self.rank = len(Version._rank_ordering) + 1 + Version._DELETED_MIGRATOR_COUNT
    if Version._rank_ordering:
      assert self.rank > Version._rank_ordering[-1], \
          'rank is out of order (! %d > %d)' % (self.rank, Version._rank_ordering[-1])
    assert self.__class__ not in Version._version_classes, \
        'class %s has already been added to version set' % self.__class__.__name__
    Version._rank_ordering.append(self.rank)
    Version._version_classes.add(self.__class__)

  @classmethod
  def SetMutateItems(cls, mutate):
    """Set to affect mutations on the database. If False, the planned
    modifications to each item are verbosely logged but not persisted.
    """
    Version._mutate_items = mutate

  @classmethod
  def SetAllowS3Queries(cls, allow):
    """Allow S3 queries. If False, upgrades that involve querying S3 will
    skip it, but may perform other work.
    eg: CreateMD5Hashes and FillFileSizes both use S3 queries as a fallback
    when the desired fields are not found the Photo.client_data.
    """
    Version._allow_s3_queries = allow

  @classmethod
  def GetCurrentVersion(cls):
    """Returns the maximum version. New objects have item._version set
    to this value.
    """
    if Version._rank_ordering:
      return Version._rank_ordering[-1]
    else:
      return 0

  @classmethod
  def MaybeMigrate(cls, client, original_item, versions, callback):
    """Migrates the data in one table row ('item') by advancing
    'item's version via successive data migrations. If 'item' does not
    have a version yet, all data migrations are applied. If item's
    version is current, does nothing. Return the migrated object if
    mutations are enabled, or the original object if not. Take care
    if the migration changes the primary key; the caller might fetch
    an object using one primary key, but get back an object with a
    different migrated primary key!
    """
    def _Migrate(start_rank, mutate_item):
      last_rank = 0
      for version in versions:
        if version.rank < start_rank:
          last_rank = version.rank
          continue
        assert version.rank > last_rank, \
            'tags listed out of order (! %d > %d)' % (version.rank, last_rank)
        last_rank = version.rank
        item_version = mutate_item._version or 0
        if item_version < version.rank:
          logging.debug('upgrading item from %s to version %s' %
                        (type(mutate_item)._table.name, version.__class__.__name__))
          mutate_item._version = version.rank

          # If Transform fails, retry several times before giving up.
          transform_callback = partial(_Migrate, last_rank + 1)
          retry.CallWithRetryAsync(Version._migrate_retry_policy,
                                   version.Transform,
                                   client,
                                   mutate_item,
                                   callback=transform_callback)
          return

      callback(mutate_item if Version._mutate_items else original_item)

    _Migrate(0, original_item if Version._mutate_items else original_item._Clone())

  def _LogUpdate(self, item):
    """Log the changes to the object."""
    mods = ['%s => %r' % (n, getattr(item, n)) for n in item.GetColNames() if item._IsModified(n)]
    if mods:
      logging.info('%s (%r): %s' % (type(item)._table.name, item.GetKey(), ', '.join(mods)))

  def Transform(self, client, item, callback):
    """Implement in each subclass to effect the required data migration.
    'callback' should be invoked on completion with the update object.
    If no async processing is required, it should be invoked directly.
    """
    raise NotImplementedError()


class TestVersion(Version):
  """Upgrade rows in the Test table."""
  def Transform(self, client, item, callback):
    """If an attribute does not exist, create it with default value."""
    # Test creating brand new object.
    item = item._Clone()
    if item.attr0 is None:
      item.attr0 = 100
    self._LogUpdate(item)
    if Version._mutate_items:
      item.Update(client, partial(callback, item))
    else:
      callback(item)


class TestVersion2(Version):
  """Upgrade rows in the Test table."""
  def Transform(self, client, item, callback):
    """If an attribute does exist, delete it."""
    if item.attr1 is not None:
      item.attr1 = None
    self._LogUpdate(item)
    if Version._mutate_items:
      item.Update(client, partial(callback, item))
    else:
      callback(item)


class AddViewpointSeq(Version):
  """Add update_seq attribute to Viewpoint and viewed_seq attribute to
  Follower, each with starting value of 0.
  """
  def Transform(self, client, follower, callback):
    from viewpoint import Viewpoint

    def _OnQuery(viewpoint):
      with util.Barrier(partial(callback, follower)) as b:
        follower.viewed_seq = 0
        self._LogUpdate(follower)

        if Version._mutate_items:
          follower.Update(client, b.Callback())

        if viewpoint.update_seq is None:
          viewpoint._version = self.rank
          viewpoint.update_seq = 0
          self._LogUpdate(viewpoint)

          if Version._mutate_items:
            viewpoint.Update(client, b.Callback())

    Viewpoint.Query(client, follower.viewpoint_id, None, _OnQuery)


class AddActivitySeq(Version):
  """Add update_seq attribute to existing activities, with starting
  value of 0.
  """
  def Transform(self, client, activity, callback):
    activity.update_seq = 0
    self._LogUpdate(activity)

    if Version._mutate_items:
      activity.Update(client, partial(callback, activity))
    else:
      callback(activity)


class UpdateActivityShare(Version):
  """Add follower_ids to share activities and rename to either share_new
  or share_existing, depending on whether the activity's timestamp is
  before all other activities in the viewpoint.
  """
  def Transform(self, client, viewpoint, callback):
    from activity import Activity
    from viewpoint import Viewpoint

    def _OnQuery(followers_activities):
      (follower_ids, last_key), activities = followers_activities

      activities = [activity for activity in activities if activity.name == 'share']

      if len(activities) > 0:
        # Find the share activity with the lowest timestamp.
        oldest_activity = None
        for activity in activities:
          if oldest_activity is None or activity.timestamp < oldest_activity.timestamp:
            oldest_activity = activity
          activity.name = 'share_existing'

        # Override oldest activity as share_new and add followers.
        oldest_activity.name = 'share_new'
        act_dict = json.loads(activities[-1].json)
        act_dict['follower_ids'] = [f_id for f_id in follower_ids if f_id != viewpoint.user_id]
        oldest_activity.json = json.dumps(act_dict)

        # Update all activities.
        with util.Barrier(partial(callback, viewpoint)) as b:
          for activity in activities:
            self._LogUpdate(activity)

            if Version._mutate_items:
              activity.Update(client, b.Callback())
            else:
              b.Callback()()
      else:
        callback(viewpoint)

    with util.ArrayBarrier(_OnQuery) as b:
      Viewpoint.QueryFollowerIds(client, viewpoint.viewpoint_id, b.Callback())
      Activity.RangeQuery(client, viewpoint.viewpoint_id, None, None, None, b.Callback())


class CreateMD5Hashes(Version):
  """Create tn_md5 and med_md5 attributes on all photos by extracting
  the hashes from the client_data attribute, if possible. If they don't
  exist there, then get them by issuing HEAD requests against S3. As a
  side effect, this upgrade will also fix the placemark base64hex padding
  issue.
  """
  def Transform(self, client, photo, callback):
    from viewfinder.backend.storage.s3_object_store import S3ObjectStore

    def _SetPhotoMD5Values(md5_values):
      tn_md5, med_md5, full_md5, orig_md5 = md5_values

      assert photo.tn_md5 == tn_md5 or photo.tn_md5 is None, photo
      photo.tn_md5 = tn_md5

      assert photo.med_md5 == med_md5 or photo.med_md5 is None, photo
      photo.med_md5 = med_md5

      assert photo.full_md5 == full_md5 or photo.full_md5 is None, photo
      photo.full_md5 = full_md5

      assert photo.orig_md5 == orig_md5 or photo.orig_md5 is None, photo
      photo.orig_md5 = orig_md5

      photo.placemark = photo.placemark

      self._LogUpdate(photo)

      if Version._mutate_items:
        photo.Update(client, partial(callback, photo))
      else:
        callback(photo)

    def _OnFetchHead(head_callback, response):
      # Etag is the hex string encoded MD5 hash of the photo.
      if response.code != 404:
        etag = response.headers['Etag'][1:-1]
      else:
        etag = None
      head_callback(etag)

    def _SendHeadRequest(photo_id, suffix, head_callback):
      object_store = S3ObjectStore('photos-viewfinder-co')
      url = object_store.GenerateUrl(photo_id + suffix, method='HEAD')
      http_client = httpclient.AsyncHTTPClient()
      http_client.fetch(url, method='HEAD', callback=partial(_OnFetchHead, head_callback))

    client_data = photo.client_data
    if client_data is None or 'tn_md5' not in client_data:
      if not Version._allow_s3_queries:
        callback(photo)
        return
      # Get MD5 values by issuing HEAD against S3.
      with util.ArrayBarrier(_SetPhotoMD5Values) as b:
        _SendHeadRequest(photo.photo_id, '.t', b.Callback())
        _SendHeadRequest(photo.photo_id, '.m', b.Callback())
        _SendHeadRequest(photo.photo_id, '.f', b.Callback())
        _SendHeadRequest(photo.photo_id, '.o', b.Callback())
    else:
      # Get MD5 values by extracting from client_data.
      _SetPhotoMD5Values((client_data['tn_md5'], client_data['med_md5'],
                          photo.full_md5, photo.orig_md5))


class DisambiguateActivityIds(Version):
  """Search for activities which were migrated from old data model to
  new data model. In some cases, the assigned activity ids are duplicated
  across viewpoints. This happened when an episode "sharing tree" involved
  multiple users. For each unique pair of users who had access to the
  episode, an activity with the same activity id was created. This upgrade
  appends the viewpoint id to the activity id to make it globally unique
  (rather than just unique within a particular viewpoint).
  """
  pass


class MigrateMoreShares(Version):
  """Migrate shares which were missed during the last migration because
  the member sharing_user_id attribute was not specified. Infer the
  attribute by assuming that the photo owner was the sharer.
  """
  def Transform(self, client, member, callback):
    from episode import Episode
    from member import Member

    def _OnQueryMember(root_episode, sharer_member):
      assert Member.OWNED in sharer_member.labels, sharer_member

      logging.info('migrating share from user "%s" to user "%s" in episode "%s" in viewpoint "%s"' % \
                   (sharer_member.user_id, member.user_id, root_episode.episode_id,
                    root_episode.viewpoint_id))

      if Version._mutate_items:
        Episode._MigrateShare(client, root_episode, sharer_member=sharer_member,
                              recipient_member=member, add_photo_ids=None,
                              callback=partial(callback, member))
      else:
        callback(member)

    def _OnQueryEpisode(root_episode):
      Member.Query(client, root_episode.user_id, root_episode.episode_id, None,
                   partial(_OnQueryMember, root_episode))

    if member.sharing_user_id is None and Member.OWNED not in member.labels:
      assert list(member.labels) == [Member.SHARED], member
      Episode.Query(client, member.episode_id, None, _OnQueryEpisode)
    else:
      callback(member)


class AddUserType(Version):
  """Set user "type" attribute to "activated", and also get rid of the
  "op_id_seq" attribute, which is no longer used.
  """
  def Transform(self, client, user, callback):
    from user import User

    user.labels = [User.ACTIVATED]
    user.op_id_seq = None

    self._LogUpdate(user)

    if Version._mutate_items:
      user.Update(client, partial(callback, user))
    else:
      callback(user)


class DisambiguateActivityIds2(Version):
  """Search for activities which were migrated from old data model to
  new data model. In some cases, the assigned activity ids are duplicated
  across viewpoints. This happened when an episode "sharing tree" involved
  multiple users. For each unique pair of users who had access to the
  episode, an activity with the same activity id was created. This upgrade
  appends the viewpoint id to the activity id to make it globally unique
  (rather than just unique within a particular viewpoint).

  NOTE: This is being done a second time, as we've discovered a new case
        in which activity-id dups have been created.
  """
  _unique_activity_ids = set()

  def Transform(self, client, activity, callback):
    from activity import Activity
    from asset_id import AssetIdUniquifier
    from device import Device

    def _OnUpdate(new_activity):
      """Delete the old activity."""
      if Version._mutate_items:
        activity.Delete(client, partial(callback, new_activity))
      else:
        callback(new_activity)

    timestamp, device_id, uniquifier = Activity.DeconstructActivityId(activity.activity_id)

    if device_id == Device.SYSTEM:
      if activity.activity_id in DisambiguateActivityIds2._unique_activity_ids:
        # Already saw this activity id, so append viewpoint id to it.
        assert uniquifier.server_id is None, (activity, uniquifier)
        new_uniquifier = AssetIdUniquifier(uniquifier.client_id, activity.viewpoint_id)
        new_activity_id = Activity.ConstructActivityId(timestamp, device_id, new_uniquifier)

        new_activity_dict = activity._asdict()
        new_activity_dict['activity_id'] = new_activity_id

        new_activity = Activity.CreateFromKeywords(**new_activity_dict)

        logging.info('%s\n%s (%s/%s/%s) => %s (%s/%s/%s/%s)' %
                     (activity, activity.activity_id, timestamp, device_id, uniquifier.client_id,
                      new_activity_id, timestamp, device_id, new_uniquifier.client_id, new_uniquifier.server_id))

        if Version._mutate_items:
          new_activity.Update(client, partial(_OnUpdate, new_activity))
        else:
          _OnUpdate(new_activity)
      else:
        DisambiguateActivityIds2._unique_activity_ids.add(activity.activity_id)
        callback(activity)
    else:
      assert activity.activity_id not in DisambiguateActivityIds2._unique_activity_ids, activity
      callback(activity)


class CopyUpdateSeq(Version):
  """Copy the update_seq column from the activity table to the notification
  table.
  """
  def Transform(self, client, notification, callback):
    from activity import Activity
    from asset_id import AssetIdUniquifier

    def _DoUpdate():
      self._LogUpdate(notification)

      if Version._mutate_items:
        notification.Update(client, partial(callback, notification))
      else:
        callback(notification)

    def _OnQueryNewActivity(activity):
      if activity is None:
        logging.warning('notification does not have a valid activity_id: %s', notification)
        notification.update_seq = 0
        self._LogUpdate(notification)
        _DoUpdate()
      else:
        _OnQueryActivity(activity)

    def _OnQueryActivity(activity):
      if activity is None:
        # Also migrate any notifications which are using the older activity id.
        timestamp, device_id, uniquifier = Activity.DeconstructActivityId(notification.activity_id)
        new_uniquifier = AssetIdUniquifier(uniquifier.client_id, notification.viewpoint_id)
        new_activity_id = Activity.ConstructActivityId(timestamp, device_id, new_uniquifier)
        Activity.Query(client, notification.viewpoint_id, new_activity_id, None,
                       _OnQueryNewActivity, must_exist=False)
        return

      notification.activity_id = activity.activity_id
      notification.update_seq = activity.update_seq
      _DoUpdate()

    if notification.activity_id is None:
      callback(notification)
    else:
      Activity.Query(client, notification.viewpoint_id, notification.activity_id, None,
                     _OnQueryActivity, must_exist=False)


class AddUserSigningKey(Version):
  """Add a Keyczar signing keyset to each User db object."""
  def Transform(self, client, user, callback):
    user.signing_key = secrets.CreateSigningKeyset('signing_key')
    self._LogUpdate(user)

    if Version._mutate_items:
      user.Update(client, partial(callback, user))
    else:
      callback(user)


class UpdateUserType(Version):
  """Update user "type" attribute from "activated" to "registered".
  """
  def Transform(self, client, user, callback):
    from user import User

    if 'activated' in user.labels:
      labels = user.labels.combine()
      labels.remove('activated')
      labels.add(User.REGISTERED)
      user.labels = labels

    self._LogUpdate(user)

    if Version._mutate_items:
      user.Update(client, partial(callback, user))
    else:
      callback(user)


class AddFollowed(Version):
  """Add one record to "Followed" table for each viewpoint. The records
  are sorted by the timestamp of the latest activity in each viewpoint.
  """
  def Transform(self, client, viewpoint, callback):
    from activity import Activity
    from followed import Followed
    from viewpoint import Viewpoint

    def _OnQuery(activities_followers):
      activities, (follower_ids, last_key) = activities_followers

      with util.Barrier(partial(callback, viewpoint)) as b:
        old_timestamp = viewpoint.last_updated

        if len(activities) > 0:
          new_timestamp = max(a.timestamp for a in activities)
        else:
          # Viewpoint has no activities.
          new_timestamp = 0

        viewpoint.last_updated = new_timestamp
        self._LogUpdate(viewpoint)

        for follower_id in follower_ids:
          logging.info('Followed (user_id=%s, viewpoint_id=%s): %s => %s' %
                       (follower_id, viewpoint.viewpoint_id, Followed._TruncateToDay(old_timestamp),
                        Followed._TruncateToDay(new_timestamp)))

          if Version._mutate_items:
            Followed.UpdateDateUpdated(client, follower_id, viewpoint.viewpoint_id,
                                       old_timestamp, new_timestamp, b.Callback())

    with util.ArrayBarrier(_OnQuery) as b:
      Activity.RangeQuery(client, viewpoint.viewpoint_id, None, None, None, b.Callback())
      Viewpoint.QueryFollowerIds(client, viewpoint.viewpoint_id, b.Callback())


class InTransformContext(ContextLocal):
  """ContextLocal used to prevent transform re-entrancy."""
  pass


class UpdateDevices(Version):
  """Add columns and indexes to devices and remove duplicate and
  expired push tokens.
  """
  def Transform(self, client, device, callback):
    from tornado.web import stack_context
    from viewfinder.backend.db.device import Device

    def _DoUpdate():
      self._LogUpdate(device)

      if Version._mutate_items:
        device.Update(client, partial(callback, device))
      else:
        callback(device)

    def _OnQueryByPushToken(other_devices):
      # If another device with the same push token and with a greater id exists, then erase this
      # device's push token.
      for other in other_devices:
        if other.push_token == device.push_token and other.device_id > device.device_id:
          device.alert_user_id = None
          device.push_token = None
          break

      _DoUpdate()

    # Do not allow re-entrancy, which is caused by the Device.IndexQuery below. Put a
    # ContextLocal into scope so that re-entrancy can be detected.
    if InTransformContext.current() is None:
      with stack_context.StackContext(InTransformContext()):
        # Set the new device timestamp field.
        device.timestamp = device.last_access or time.time()

        if device.push_token is not None:
          # Enable alerts if the device is still active.
          if time.time() < device.last_access + Device._PUSH_EXPIRATION:
            device.alert_user_id = device.user_id

          # Find all devices with the same push token.
          query_expr = ('device.push_token={t}', {'t': device.push_token})
          Device.IndexQuery(client, query_expr, None, _OnQueryByPushToken)
        else:
          _DoUpdate()
    else:
      callback(device)

class FillFileSizes(Version):
  """Fill in the file size columns (tn/med/full/orig) from the client_data."""
  def Transform(self, client, photo, callback):
    from viewfinder.backend.storage.s3_object_store import S3ObjectStore

    def _SetPhotoSizeValues(size_values):
      tn_size, med_size, full_size, orig_size = size_values

      assert photo.tn_size == tn_size or photo.tn_size is None, photo
      photo.tn_size = tn_size

      assert photo.med_size == med_size or photo.med_size is None, photo
      photo.med_size = med_size

      assert photo.full_size == full_size or photo.full_size is None, photo
      photo.full_size = full_size

      assert photo.orig_size == orig_size or photo.orig_size is None, photo
      photo.orig_size = orig_size

      self._LogUpdate(photo)

      if Version._mutate_items:
        photo.Update(client, partial(callback, photo))
      else:
        callback(photo)

    def _OnListKeys(result):
      def _GetSizeOrNone(files, suffix):
        fname = photo.photo_id + '.' + suffix
        if fname in files:
          return int(files[fname]['Size'])
        else:
          return None

      if len(result) > 0:
        _SetPhotoSizeValues((_GetSizeOrNone(result, 't'), _GetSizeOrNone(result, 'm'),
                            _GetSizeOrNone(result, 'f'), _GetSizeOrNone(result, 'o')))
      else:
        logging.info('No files found in S3 for photo %s' % photo.photo_id)
        callback(photo)

    def _ListPhotoMetadata():
      object_store = S3ObjectStore('photos-viewfinder-co')
      object_store.ListKeyMetadata(_OnListKeys, prefix=photo.photo_id + '.',
                                   fields=['Size', 'Key'])

    client_data = photo.client_data
    # the assumption is that is we have the tn_size field set, all other
    # sizes will be as well. db analysis shows this to be currently true.
    if client_data is None or 'tn_size' not in client_data:
      if not Version._allow_s3_queries:
        callback(photo)
        return
      # Extract sizes from S3.
      _ListPhotoMetadata()
    else:
      # Extract sizes from client_data.
      _SetPhotoSizeValues((int(client_data['tn_size']), int(client_data['med_size']),
                          int(client_data['full_size']), int(client_data['orig_size'])))

class RepairFacebookContacts(Version):
  @gen.engine
  def Transform(self, client, identity, callback):
    from tornado.web import stack_context
    from operation import Operation
    from user import User

    # Do not allow re-entrancy, which is caused by the Device.IndexQuery below. Put a
    # ContextLocal into scope so that re-entrancy can be detected.
    if InTransformContext.current() is None:
      with stack_context.StackContext(InTransformContext()):
        if identity.authority == 'Facebook' and identity.user_id is not None:
          user = yield gen.Task(User.Query, client, identity.user_id, None)
          yield gen.Task(Operation.CreateAndExecute, client, identity.user_id, user.webapp_dev_id,
                         'FetchContactsOperation.Execute',
                         {'headers': {'synchronous': True}, 'key': identity.key, 'user_id': identity.user_id})

    callback(identity)

class AddAccountSettings(Version):
  """Add account settings to every existing user, defaulting to full push notifications."""
  @gen.engine
  def Transform(self, client, user, callback):
    from settings import AccountSettings

    settings = yield gen.Task(AccountSettings.QueryByUser, client, user.user_id, None, must_exist=False)
    if settings is None:
      logging.info('Creating account settings for user %d', user.user_id)
      settings = AccountSettings.CreateForUser(user.user_id,
                                               email_alerts=AccountSettings.EMAIL_NONE,
                                               push_alerts=AccountSettings.PUSH_ALL)
      if Version._mutate_items:
        yield gen.Task(settings.Update, client)

    callback(user)

class SplitUserNames(Version):
  """Split full names of all users that don't have given/family names specified."""
  @gen.engine
  def Transform(self, client, user, callback):
    if user.name and '@' not in user.name and not user.given_name and not user.family_name:
      match = message.FULL_NAME_RE.match(user.name)
      if match is not None:
        user.given_name = match.group(1)
        if match.group(2):
          user.family_name = match.group(2)

      self._LogUpdate(user)

      if Version._mutate_items:
        yield gen.Task(user.Update, client)

    callback(user)

class ExtractAssetKeys(Version):
  @gen.engine
  def Transform(self, client, photo, callback):
    from device_photo import DevicePhoto
    from photo import Photo

    if photo.client_data is None:
      callback(photo)
      return

    if photo.client_data.get('asset_key'):
      # Asset keys were only stored in client_data for the device that originally uploaded the photo.
      _, device_id, _ = Photo.DeconstructPhotoId(photo.photo_id)
      existing = yield gen.Task(DevicePhoto.Query, client, device_id, photo.photo_id, None, must_exist=False)
      if existing is None:
        logging.info('Creating device photo for photo %s, device %s', photo.photo_id, device_id)
        device_photo = DevicePhoto.CreateFromKeywords(photo_id=photo.photo_id,
                                                      device_id=device_id,
                                                      asset_keys=[photo.client_data['asset_key']])
      else:
        logging.info('Photo %s, device %s already has device photo', photo.photo_id, device_id)
        device_photo = None

      if device_photo is not None:
        self._LogUpdate(device_photo)
      photo.client_data = None
      self._LogUpdate(photo)

      if Version._mutate_items:
        # Do this serially with device_photo first so we can retry on partial failure.
        if device_photo is not None:
          yield gen.Task(device_photo.Update, client)
        yield gen.Task(photo.Update, client)

    callback(photo)

class MyOnlyFriend(Version):
  """Make each user a friend with himself/herself."""
  @gen.engine
  def Transform(self, client, user, callback):
    from friend import Friend
    friend = Friend.CreateFromKeywords(user_id=user.user_id, friend_id=user.user_id)

    logging.info('Creating friend for user %d', user.user_id)
    if Version._mutate_items:
      yield gen.Task(friend.Update, client)

    callback(user)

class EraseFriendNames(Version):
  """Remove the name attributes from all friends."""
  @gen.engine
  def Transform(self, client, friend, callback):

    friend.name = None
    self._LogUpdate(friend)
    if Version._mutate_items:
      yield gen.Task(friend.Update, client)

    callback(friend)


class MoveDevicePhoto(Version):
  _device_to_user_cache = {}

  @gen.engine
  def Transform(self, client, device_photo, callback):
    from device import Device
    from user_photo import UserPhoto
    device_id = device_photo.device_id

    if device_id not in MoveDevicePhoto._device_to_user_cache:
      query_expr = ('device.device_id={t}', {'t': device_id})
      devices = yield gen.Task(Device.IndexQuery, client, query_expr, None)
      assert len(devices) == 1
      MoveDevicePhoto._device_to_user_cache[device_id] = devices[0].user_id
    user_id = MoveDevicePhoto._device_to_user_cache[device_id]

    existing = yield gen.Task(UserPhoto.Query, client, user_id, device_photo.photo_id, None, must_exist=False)
    if existing is None:
      logging.info('Creating user photo for photo %s, device %s, user %s', device_photo.photo_id, device_id, user_id)
      user_photo = UserPhoto.CreateFromKeywords(photo_id=device_photo.photo_id,
                                                user_id=user_id,
                                                asset_keys=device_photo.asset_keys)
    else:
      logging.info('Photo %s, device %s, user %s already has user photo', device_photo.photo_id, device_id, user_id)
      user_photo = None

    if user_photo is not None:
      self._LogUpdate(user_photo)

    if Version._mutate_items and user_photo is not None:
      yield gen.Task(user_photo.Update, client)

    callback(device_photo)

class SetCoverPhoto(Version):
  """Set a cover photo on each viewpoint.
  This will use the original mobile client algorithm to select the cover photo.
  """
  @gen.engine
  def Transform(self, client, viewpoint, callback):
    # We don't set a cover_photo on DEFAULT viewpoints.
    if not viewpoint.IsDefault() and viewpoint.cover_photo == None:
      viewpoint.cover_photo = yield gen.Task(viewpoint.SelectCoverPhotoUsingOriginalAlgorithm, client)
    if Version._mutate_items:
      yield gen.Task(viewpoint.Update, client)

    callback(viewpoint)

class RemoveAssetUrls(Version):
  """Remove the asset urls from client-supplied asset keys, leaving only
  the fingerprints.
  """
  @gen.engine
  def Transform(self, client, user_photo, callback):
    from user_photo import UserPhoto
    asset_keys = user_photo.asset_keys.combine()
    changed = False
    # Copy the set because we'll modify it as we go.
    for asset_key in list(asset_keys):
      fingerprint = UserPhoto.AssetKeyToFingerprint(asset_key)
      if fingerprint is None:
        # Old asset key with no fingerprint; throw it away.
        asset_keys.remove(asset_key)
        changed = True
      elif asset_key != fingerprint:
        # A url was present, remove it and just leave the fingerprint.
        asset_keys.remove(asset_key)
        asset_keys.add(fingerprint)
        changed = True
    if changed:
      # Set columns don't support adding and deleting values in the same
      # operation unless you delete and rewrite the whole thing.
      # That's not entirely atomic, but the risk here is low so it's
      # not worth the trouble of splitting the adds and deletes into separate
      # phases.
      user_photo.asset_keys = asset_keys

    self._LogUpdate(user_photo)
    if Version._mutate_items:
      yield gen.Task(user_photo.Update, client)

    callback(user_photo)

class RemoveContactUserId(Version):
  """Remove the contact_user_id field from contact records."""
  @gen.engine
  def Transform(self, client, contact, callback):
    from contact import Contact
    contact.contact_user_id = None
    self._LogUpdate(contact)
    if Version._mutate_items:
      yield gen.Task(contact.Update, client)

    callback(contact)

class UploadContactsSupport(Version):
  """Convert contact records to support upload_contacts schema change.
  - Populate new fields:
    * timestamp: Generate new timestamp for each record.
    * contact_source: 'gm' from 'Email:' identity or 'fb' from 'FacebookGraph:' identity.
    * identities: Create with one value from existing identity column.
    * contact_id: Derived from base64/hash of other columns plus contact_source.
    * identities_properties: Create with one value from existing identity column and None for description.
  - Update existing field:
    * sort_key: Now, derived from timestamp and contact_id columns.
  """
  @gen.engine
  def Transform(self, client, contact, callback):
    from viewfinder.backend.db.contact import Contact
    from viewfinder.backend.db.identity import Identity
    contact_dict = contact._asdict()
    # During this upgrade assume that any email identities came from GMail and any facebook identities came from
    #   Facebook.  At this time, there shouldn't be any identities that start with anything else.
    assert contact.identity.startswith('Email:') or contact.identity.startswith('FacebookGraph:'), contact
    contact_dict['contact_source'] = Contact.GMAIL if contact.identity.startswith('Email:') else Contact.FACEBOOK
    contact_dict['identities_properties'] = [(Identity.Canonicalize(contact.identity), None)]
    contact_dict['timestamp'] = util.GetCurrentTimestamp()
    # Let Contact.CreateFromKeywords calculate a new sort_key.
    contact_dict.pop('sort_key')
    # Let Contact.CreateFromKeywords determine value for identities column.
    contact_dict.pop('identities')
    # Contact.CreateFromKeywords() will calculate sort_key, contact_id, and identities columns.
    new_contact = Contact.CreateFromKeywords(**contact_dict)

    self._LogUpdate(new_contact)

    if Version._mutate_items:
      yield gen.Task(new_contact.Update, client)
      yield gen.Task(contact.Delete, client)

    callback(new_contact)

class RenameUserPostRemoved(Version):
  """Rename the USER_POST "REMOVED" label to be "HIDDEN"."""
  @gen.engine
  def Transform(self, client, user_post, callback):
    from user_post import UserPost
    if UserPost.REMOVED in user_post.labels:
      labels = user_post.labels.combine()
      labels.remove(UserPost.REMOVED)
      labels.add(UserPost.HIDDEN)
      user_post.labels = labels
      self._LogUpdate(user_post)
      if Version._mutate_items:
        yield gen.Task(user_post.Update, client)

    callback(user_post)

class AddRemovedToPost(Version):
  """Add REMOVED to every UNSHARED post."""
  @gen.engine
  def Transform(self, client, post, callback):
    from post import Post
    labels = post.labels.combine()
    if Post.UNSHARED in labels:
      labels.add(Post.REMOVED)
      post.labels = labels
      self._LogUpdate(post)
      if Version._mutate_items:
        yield gen.Task(post.Update, client)

    callback(post)

class RemoveHiddenPosts(Version):
  """Add REMOVED label to posts that are hidden in default viewpoints, and then delete the
  user post.
  """
  @gen.engine
  def Transform(self, client, user_post, callback):
    from episode import Episode
    from post import Post
    from user_post import UserPost
    from viewpoint import Viewpoint

    if UserPost.REMOVED in user_post.labels:
      episode_id, photo_id = Post.DeconstructPostId(user_post.post_id)
      episode = yield gen.Task(Episode.Query, client, episode_id, None)
      viewpoint = yield gen.Task(Viewpoint.Query, client, episode.viewpoint_id, None)
      if viewpoint.IsDefault():
        post = yield gen.Task(Post.Query, client, episode_id, photo_id, None)
        post.labels.add(Post.REMOVED)

        logging.info('Adding REMOVED label to POST: %s (%s, %s)', user_post.post_id, episode_id, photo_id)
        if Version._mutate_items:
          yield gen.Task(post.Update, client)
          yield gen.Task(user_post.Delete, client)

    callback(user_post)

class ReactivateAlertUser(Version):
  """Set Device.alert_user_id for devices that have a push token and belong to a non-terminated user."""
  @gen.engine
  def Transform(self, client, device, callback):
    from device import Device
    from user import User

    if device.push_token is not None and device.alert_user_id is None:
      user = yield gen.Task(User.Query, client, device.user_id, None)
      if not user.IsTerminated():
        device.alert_user_id = device.user_id
        if Version._mutate_items:
          yield gen.Task(device.Update, client)

    callback(device)

class RemoveContactIdentity(Version):
  """Remove the identity field from contact records."""
  @gen.engine
  def Transform(self, client, contact, callback):
    contact.identity = None
    self._LogUpdate(contact)
    if Version._mutate_items:
      yield gen.Task(contact.Update, client)

    callback(contact)

class RepairWelcomeConvos(Version):
  """Repair the welcome conversations by updating the cover_photo episode id to be an episode
  in the viewpoint.
  """
  @gen.engine
  def Transform(self, client, viewpoint, callback):
    from viewpoint import Viewpoint
    from viewfinder.backend.www import system_users

    if viewpoint.type == Viewpoint.SYSTEM:
      episodes, _ = yield gen.Task(Viewpoint.QueryEpisodes, client, viewpoint.viewpoint_id)
      for episode in episodes:
        if episode.parent_ep_id == 'egAZn7AjQ-F7':
          assert viewpoint.cover_photo['episode_id'] == episode.parent_ep_id or episode.episode_id, episode
          assert viewpoint.cover_photo['photo_id'] == 'pgAZn7AjQ-FB', viewpoint.cover_photo

          viewpoint.cover_photo = {'episode_id': episode.episode_id,
                                   'photo_id': 'pgAZn7AjQ-FB'}

          self._LogUpdate(viewpoint)
          if Version._mutate_items:
            yield gen.Task(viewpoint.Update, client)

    callback(viewpoint)

class RepairWelcomeConvos2(Version):
  """Repair corrupt welcome conversations by removing all photos."""
  @gen.engine
  def Transform(self, client, viewpoint, callback):
    from viewpoint import Viewpoint
    from viewfinder.backend.www import system_users

    if viewpoint.type == Viewpoint.SYSTEM:
      episodes, _ = yield gen.Task(Viewpoint.QueryEpisodes, client, viewpoint.viewpoint_id)
      if len(episodes) == 0:
        # Remove reference to cover photo.
        viewpoint.cover_photo = None
        self._LogUpdate(viewpoint)
        if Version._mutate_items:
          yield gen.Task(viewpoint.Update, client)

        # Delete share_existing activities.
        activities, _ = yield gen.Task(Viewpoint.QueryActivities, client, viewpoint.viewpoint_id)
        for activity in activities:
          if activity.name == 'share_existing':
            logging.info('removing activity %s' % activity.activity_id)
            if Version._mutate_items:
              yield gen.Task(activity.Delete, client)

        # Remove comment reference to photo asset.
        comments, _ = yield gen.Task(Viewpoint.QueryComments, client, viewpoint.viewpoint_id)
        for comment in comments:
          if comment.asset_id is not None:
            comment.asset_id = None
            self._LogUpdate(comment)
            if Version._mutate_items:
              yield gen.Task(comment.Update, client)

    callback(viewpoint)


# Append new version migrations here.
# MAINTAIN THE ORDERING!
# ONLY DELETE OLDEST CLASSES IN ORDER!
# IF YOU DELETE, MAKE SURE TO UPDATE Version._DELETED_MIGRATOR_COUNT.
TEST_VERSION = TestVersion()
TEST_VERSION2 = TestVersion2()
ADD_VIEWPOINT_SEQ = AddViewpointSeq()
ADD_ACTIVITY_SEQ = AddActivitySeq()
UPDATE_ACTIVITY_SHARE = UpdateActivityShare()
CREATE_MD5_HASHES = CreateMD5Hashes()
DISAMBIGUATE_ACTIVITY_IDS = DisambiguateActivityIds()
MIGRATE_MORE_SHARES = MigrateMoreShares()
ADD_USER_TYPE = AddUserType()
DISAMBIGUATE_ACTIVITY_IDS_2 = DisambiguateActivityIds2()
COPY_UPDATE_SEQ = CopyUpdateSeq()
ADD_USER_SIGNING_KEY = AddUserSigningKey()
UPDATE_USER_TYPE = UpdateUserType()
ADD_FOLLOWED = AddFollowed()
UPDATE_DEVICES = UpdateDevices()
FILL_FILE_SIZES = FillFileSizes()
REPAIR_FACEBOOK_CONTACTS = RepairFacebookContacts()
ADD_ACCOUNT_SETTINGS = AddAccountSettings()
SPLIT_USER_NAMES = SplitUserNames()
EXTRACT_ASSET_KEYS = ExtractAssetKeys()
MY_ONLY_FRIEND = MyOnlyFriend()
ERASE_FRIEND_NAMES = EraseFriendNames()
MOVE_DEVICE_PHOTO = MoveDevicePhoto()
SET_COVER_PHOTO = SetCoverPhoto()
REMOVE_ASSET_URLS = RemoveAssetUrls()
REMOVE_CONTACT_USER_ID = RemoveContactUserId()
UPLOAD_CONTACTS_SUPPORT = UploadContactsSupport()
RENAME_USER_POST_REMOVED = RenameUserPostRemoved()
ADD_REMOVED_TO_POST = AddRemovedToPost()
REMOVE_HIDDEN_POSTS = RemoveHiddenPosts()
REACTIVATE_ALERT_USER = ReactivateAlertUser()
REMOVE_CONTACT_IDENTITY = RemoveContactIdentity()
REPAIR_WELCOME_CONVOS = RepairWelcomeConvos()
REPAIR_WELCOME_CONVOS_2 = RepairWelcomeConvos2()

# TODO(spencer): should transform all photo placemarks by simply
# loading them and then saving them. That will remove all of the
# incorrectly-padded base64-encoded values.
#
# Also, should consider re-indexing all full-text-search indexed
# columns for the same reason.
