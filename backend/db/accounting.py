# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Accounting table. Stores aggregated usage metrics. The keys are prefixed
with the type of aggregation and metric stored:
- Per viewpoint: hash_key='vs:<vp_id>'
  Aggregate sizes/counts per viewpoint, keyed by the viewpoint
  id. Sort keys fall into three categories:
  - owned by: 'ow:<user_id>' only found in default viewpoint.
  - shared by: 'sb:<user_id>' in shared viewpoint, sum of all photos
    in episodes owned by 'user_id'
  - visible to: 'vt' in shared viewpoint, sum of all photos. not keyed
    by user. a given user's "shared with" stats will be 'vt - sb:<user_id>',
    but we do not want to keep per-user shared-by stats.
- Per user: hash_key='us:<user_id>'
  Aggregate sizes/counts per user, keyed by user id. Sort keys are:
  - owned by: 'ow' sum of all photos in default viewpoint
  - shared by: 'sb' sum of all photos in shared viewpoints and episodes owned by this user
  - visible to: 'vt' sum of all photos in shared viewpoint (includes 'sb'). to get the
    real count of photos shared with this user but not shared by him, compute 'vt - sb:'
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

from functools import partial
from tornado import gen
from viewfinder.backend.base import util
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.user import User
from viewfinder.backend.db.range_base import DBRangeObject


@DBObject.map_table_attributes
class Accounting(DBRangeObject):
  """Accounting object. Stores aggregated information. Currently stores
  photo count and sizes per (viewpoint, episode) pair.
  """

  # Maximum op ids to keep.
  _MAX_APPLIED_OP_IDS = 10

  # Types of accounting: each type has its own prefix used to build hash keys.
  VIEWPOINT_SIZE = 'vs'
  USER_SIZE = 'us'

  # Categories for each type of accounting. Prefix is used to build sort keys.
  OWNED_BY = 'ow'
  SHARED_BY = 'sb'
  VISIBLE_TO = 'vt'

  _table = DBObject._schema.GetTable(vf_schema.ACCOUNTING)

  def __init__(self, hash_key=None, sort_key=None):
    """Initialize a new Accounting object."""
    super(Accounting, self).__init__()
    self.hash_key = hash_key
    self.sort_key = sort_key
    self.op_ids = None
    self._Reset()

  def _Reset(self):
    """Reset counters to 0."""
    self.num_photos = 0
    self.tn_size = 0
    self.med_size = 0
    self.full_size = 0
    self.orig_size = 0

  def IncrementFromPhotoDict(self, photo_dict):
    """Increment counters with the photo stats."""
    self.num_photos += 1
    self.tn_size += photo_dict.get('tn_size', 0)
    self.med_size += photo_dict.get('med_size', 0)
    self.full_size += photo_dict.get('full_size', 0)
    self.orig_size += photo_dict.get('orig_size', 0)

  def IncrementFromPhotoDicts(self, photo_dicts):
    """Increment counters with the photo stats."""
    for p in photo_dicts:
      self.IncrementFromPhotoDict(p)

  def IncrementFromPhoto(self, photo):
    """Increment counters with the photo stats."""
    def _GetOrZero(val):
      if val is not None:
        return val
      else:
        return 0

    self.num_photos += 1
    self.tn_size += _GetOrZero(photo.tn_size)
    self.med_size += _GetOrZero(photo.med_size)
    self.full_size += _GetOrZero(photo.full_size)
    self.orig_size += _GetOrZero(photo.orig_size)

  def IncrementFromPhotos(self, photos):
    """Increment counters with the photo stats."""
    for photo in photos:
      self.IncrementFromPhoto(photo)

  def DecrementFromPhotoDicts(self, photo_dicts):
    """Decrement counters with the photo stats."""
    for p in photo_dicts:
      self.num_photos -= 1
      self.tn_size -= p.get('tn_size', 0)
      self.med_size -= p.get('med_size', 0)
      self.full_size -= p.get('full_size', 0)
      self.orig_size -= p.get('orig_size', 0)

  def DecrementFromPhotos(self, photos):
    """Decrement counters with the photo stats."""
    def _GetOrZero(val):
      if val is not None:
        return val
      else:
        return 0
    for p in photos:
      self.num_photos -= 1
      self.tn_size -= _GetOrZero(p.tn_size)
      self.med_size -= _GetOrZero(p.med_size)
      self.full_size -= _GetOrZero(p.full_size)
      self.orig_size -= _GetOrZero(p.orig_size)

  def CopyStatsFrom(self, accounting):
    """Copy the usage stats from another accounting object."""
    self.num_photos = accounting.num_photos
    self.tn_size = accounting.tn_size
    self.med_size = accounting.med_size
    self.full_size = accounting.full_size
    self.orig_size = accounting.orig_size

  def IncrementStatsFrom(self, accounting):
    """Increment stats by another accounting object."""
    self.num_photos += accounting.num_photos
    self.tn_size += accounting.tn_size
    self.med_size += accounting.med_size
    self.full_size += accounting.full_size
    self.orig_size += accounting.orig_size

  def DecrementStatsFrom(self, accounting):
    """Decrement stats by another accounting object."""
    self.num_photos -= accounting.num_photos
    self.tn_size -= accounting.tn_size
    self.med_size -= accounting.med_size
    self.full_size -= accounting.full_size
    self.orig_size -= accounting.orig_size

  def StatsEqual(self, accounting):
    """Return true if all stats match those in 'accounting'."""
    return (self.num_photos == accounting.num_photos and
            self.tn_size == accounting.tn_size and
            self.med_size == accounting.med_size and
            self.full_size == accounting.full_size and
            self.orig_size == accounting.orig_size)

  def IsZero(self):
    return self.StatsEqual(Accounting())

  def IsOpDuplicate(self, op_id):
    """Check whether the 'op_id' is in 'op_id_list_string'.
    If it is, return true and leave the original list of op ids untouched. Otherwise,
    add the op_id to the list, trim it to a max length of _MAX_APPLIED_OP_IDS = 10
    and return false."""
    ids = self.op_ids.split(',') if self.op_ids is not None else []
    if op_id in ids:
      return True
    ids.append(op_id)
    # Generate a comma-separated string of at most _MAX_APPLIED_OP_IDS elements.
    self.op_ids = ','.join(ids[-self._MAX_APPLIED_OP_IDS:])
    return False

  @classmethod
  def CreateUserOwnedBy(cls, user_id):
    """Create an accounting object (USER_SIZE:<user_id>, OWNED_BY)."""
    return Accounting('%s:%d' % (Accounting.USER_SIZE, user_id), Accounting.OWNED_BY)

  @classmethod
  def CreateUserSharedBy(cls, user_id):
    """Create an accounting object (USER_SIZE:<user_id>, SHARED_BY)."""
    return Accounting('%s:%d' % (Accounting.USER_SIZE, user_id), Accounting.SHARED_BY)

  @classmethod
  def CreateUserVisibleTo(cls, user_id):
    """Create an accounting object (USER_SIZE:<user_id>, VISIBLE_TO)."""
    return Accounting('%s:%d' % (Accounting.USER_SIZE, user_id), Accounting.VISIBLE_TO)

  @classmethod
  def CreateViewpointOwnedBy(cls, viewpoint_id, user_id):
    """Create an accounting object (VIEWPOINT_SIZE:<vp_id>, OWNED_BY:<user_id>)."""
    return Accounting('%s:%s' % (Accounting.VIEWPOINT_SIZE, viewpoint_id),
                      '%s:%d' % (Accounting.OWNED_BY, user_id))

  @classmethod
  def CreateViewpointSharedBy(cls, viewpoint_id, user_id):
    """Create an accounting object (VIEWPOINT_SIZE:<vp_id>, SHARED_BY:<user_id>)."""
    return Accounting('%s:%s' % (Accounting.VIEWPOINT_SIZE, viewpoint_id),
                      '%s:%d' % (Accounting.SHARED_BY, user_id))

  @classmethod
  def CreateViewpointVisibleTo(cls, viewpoint_id):
    """Create an accounting object (VIEWPOINT_SIZE:<vp_id>, VISIBLE_TO)."""
    return Accounting('%s:%s' % (Accounting.VIEWPOINT_SIZE, viewpoint_id),
                      Accounting.VISIBLE_TO)

  @classmethod
  def QueryViewpointSharedBy(cls, client, viewpoint_id, user_id, callback, must_exist=True):
    """Query for an accounting object (VIEWPOINT_SIZE:<vp_id>, SHARED_BY:<user_id>)."""
    Accounting.Query(client,
                     Accounting.VIEWPOINT_SIZE + ':' + viewpoint_id,
                     Accounting.SHARED_BY + ':%d' % user_id,
                     None,
                     callback,
                     must_exist=must_exist)

  @classmethod
  def QueryViewpointVisibleTo(cls, client, viewpoint_id, callback, must_exist=True):
    """Query for an accounting object (VIEWPOINT_SIZE:<vp_id>, VISIBLE_TO)."""
    Accounting.Query(client,
                     Accounting.VIEWPOINT_SIZE + ':' + viewpoint_id,
                     Accounting.VISIBLE_TO,
                     None,
                     callback,
                     must_exist=must_exist)

  @classmethod
  @gen.coroutine
  def QueryUserAccounting(cls, client, user_id):
    """Query a single user's accounting entries. Returns an array of [owned_by, shared_by, visible_to] accounting
    entries, any of which may be None (eg: if data was not properly populated).
    """
    user_hash = '%s:%d' % (Accounting.USER_SIZE, user_id)
    result = yield [gen.Task(Accounting.Query, client, user_hash, Accounting.OWNED_BY, None, must_exist=False),
                    gen.Task(Accounting.Query, client, user_hash, Accounting.SHARED_BY, None, must_exist=False),
                    gen.Task(Accounting.Query, client, user_hash, Accounting.VISIBLE_TO, None, must_exist=False)]
    raise gen.Return(result)

  @classmethod
  def ApplyAccounting(cls, client, accounting, callback):
    """Apply an accounting object. This involves a query to fetch stats and applied op ids,
    check that this operation has not been applied, increment of values and Update.
    """
    op_id = Operation.GetCurrent().operation_id
    assert op_id is not None, 'accounting update outside an operation'

    def _OnException(accounting, type, value, traceback):
      # Entry was modified between Query and Update. Rerun the entire method.
      Accounting.ApplyAccounting(client, accounting, callback)

    def _OnQueryAccounting(entry):
      if entry is None:
        # No previous entry. Set op_id and set replace to false.
        # We can submit the accounting object directly since it has not been mutated.
        accounting.op_ids = op_id
        with util.Barrier(callback, on_exception=partial(_OnException, accounting)) as b:
          accounting.Update(client, b.Callback(), replace=False)
      else:
        prev_op_ids = entry.op_ids

        # Checks whether the op id has been applied and modifies op_ids accordingly.
        found = entry.IsOpDuplicate(op_id)
        if found:
          # This operation has been applied: skip.
          callback()
          return

        entry.IncrementStatsFrom(accounting)

        # Entry exists: modify the object returned by Query and require that the op_ids
        # field has not changed since. If the existing entry was created by dbchk, it will
        # not have a op_ids field. Setting expected={'op_ids': None} is not equivalent to
        # expected={'op_ids': False}.
        with util.Barrier(callback, on_exception=partial(_OnException, accounting)) as b:
          entry.Update(client, b.Callback(), expected={'op_ids': prev_op_ids or False})

    Accounting.Query(client, accounting.hash_key, accounting.sort_key, None, _OnQueryAccounting, must_exist=False)


class AccountingAccumulator(object):
  """Facilitates collection and application of accounting deltas.

  Typical usage involves calling into an Accounting method one or more times with one of these
  accumulators and finally calling the Apply method to apply all of the accounting deltas.
  """
  def __init__(self):
    """Initializes new AccountingAccumulator object."""
    self.vp_ow_acc_dict = {}
    self.vp_vt_acc_dict = {}
    self.vp_sb_acc_dict = {}
    self.us_ow_acc_dict = {}
    self.us_vt_acc_dict = {}
    self.us_sb_acc_dict = {}

  def GetViewpointOwnedBy(self, viewpoint_id, user_id):
    """Returns the viewpoint owned_by accounting object for the given viewpoint and user."""
    key = (viewpoint_id, user_id)
    if key not in self.vp_ow_acc_dict:
      self.vp_ow_acc_dict[key] = Accounting.CreateViewpointOwnedBy(viewpoint_id, user_id)
    return self.vp_ow_acc_dict[key]

  def GetViewpointVisibleTo(self, viewpoint_id):
    """Returns the viewpoint visible_to accounting for the given viewpoint."""
    key = viewpoint_id
    if key not in self.vp_vt_acc_dict:
      self.vp_vt_acc_dict[key] = Accounting.CreateViewpointVisibleTo(viewpoint_id)
    return self.vp_vt_acc_dict[key]

  def GetViewpointSharedBy(self, viewpoint_id, user_id):
    """Returns the viewpoint shared_by accounting object for the given viewpoint and user."""
    key = (viewpoint_id, user_id)
    if key not in self.vp_sb_acc_dict:
      self.vp_sb_acc_dict[key] = Accounting.CreateViewpointSharedBy(viewpoint_id, user_id)
    return self.vp_sb_acc_dict[key]

  def GetUserOwnedBy(self, user_id):
    """Returns the user owned_by accounting for the given user."""
    key = user_id
    if key not in self.us_ow_acc_dict:
      self.us_ow_acc_dict[key] = Accounting.CreateUserOwnedBy(user_id)
    return self.us_ow_acc_dict[key]

  def GetUserVisibleTo(self, user_id):
    """Returns the user visible_to accounting for the given user."""
    key = user_id
    if key not in self.us_vt_acc_dict:
      self.us_vt_acc_dict[key] = Accounting.CreateUserVisibleTo(user_id)
    return self.us_vt_acc_dict[key]

  def GetUserSharedBy(self, user_id):
    """Returns the user shared_by accounting for the given user."""
    key = user_id
    if key not in self.us_sb_acc_dict:
      self.us_sb_acc_dict[key] = Accounting.CreateUserSharedBy(user_id)
    return self.us_sb_acc_dict[key]

  @gen.coroutine
  def AddFollowers(self, client, viewpoint_id, new_follower_ids):
    """Add accounting changes caused by adding followers to a viewpoint. Each follower
    user has VISIBLE_TO incremented by the size of the viewpoint VISIBLE_TO.
    """
    if len(new_follower_ids) > 0:
      # Query the viewpoint visible_to accounting.  New followers' visible_to will be adjusted by this much.
      vp_vt_acc = yield gen.Task(Accounting.QueryViewpointVisibleTo, client, viewpoint_id, must_exist=False)

      if vp_vt_acc is not None:
        # If the viewpoint has data, apply it to the new followers.
        for follower_id in new_follower_ids:
          self.GetUserVisibleTo(follower_id).CopyStatsFrom(vp_vt_acc)

  @gen.coroutine
  def MergeAccounts(self, client, viewpoint_id, target_user_id):
    """Add accounting changes caused by adding the given user as a follower of the viewpoint as
    part of a merge accounts operation. Increments the target user's VISIBLE_TO by the size of the
    viewpoint VISIBLE_TO.
    """
    # Query the viewpoint visible_to accounting.  The target user's visible_to will be adjusted by this much.
    vp_vt_acc = yield gen.Task(Accounting.QueryViewpointVisibleTo, client, viewpoint_id, must_exist=False)
    if vp_vt_acc is not None:
      self.GetUserVisibleTo(target_user_id).IncrementStatsFrom(vp_vt_acc)

  @gen.coroutine
  def RemovePhotos(self, client, user_id, viewpoint_id, photo_ids):
    """Add accounting changes caused by removing photos from a user's default viewpoint.
      - photo_ids: list of photos that were removed (caller should exclude the ids of any
                   photos that were already removed).

    We need to query all photos for size information. Creates the following entries:
      - (vs:<viewpoint>, ow:<user>): stats for user in default viewpoint.
      - (us:<user>, ow): overall stats for user.
    """
    photo_keys = [DBKey(photo_id, None) for photo_id in photo_ids]
    photos = yield gen.Task(Photo.BatchQuery, client, photo_keys, None)

    # Decrement owned by stats on both the viewpoint and the user.
    self.GetViewpointOwnedBy(viewpoint_id, user_id).DecrementFromPhotos(photos)
    # Don't recompute owned-by stats, just copy them from the viewpoint accounting object.
    self.GetUserOwnedBy(user_id).CopyStatsFrom(self.GetViewpointOwnedBy(viewpoint_id, user_id))

  @gen.coroutine
  def RemoveViewpoint(self, client, user_id, viewpoint_id):
    """Generate and update accounting entries for a RemoveViewpoint event.
    The user will never be removed from their default viewpoint.

    This won't modify the viewpoint stats, but we will query them to determine how much to modify the user stats.
    Query:
    - (vs:<viewpoint_id>, vt)
    - (vs:<viewpoint_id>, sb:<user_id>)
    Creates the following entries:
    - (us:<user_id>, vt): decrement by (vs:<viewpoint_id>, vt).
    - (us:<user_id>, sb): decrement by (vs:<viewpoint_id>, sb:<user_id>).
    """
    # Query the current visible_to and shared_by for the given user and viewpoint.
    vp_vt, vp_sb = yield [gen.Task(Accounting.QueryViewpointVisibleTo, client, viewpoint_id, must_exist=False),
                          gen.Task(Accounting.QueryViewpointSharedBy, client, viewpoint_id, user_id, must_exist=False)]

    # Decrease the associated user consumption by amounts that the user has associated with the viewpoint.
    if vp_vt is not None:
      self.GetUserVisibleTo(user_id).DecrementStatsFrom(vp_vt)
    if vp_sb is not None:
      self.GetUserSharedBy(user_id).DecrementStatsFrom(vp_sb)

  @gen.coroutine
  def ReviveFollowers(self, client, viewpoint_id, revive_follower_ids):
    """Add accounting changes caused by the revival of the given followers. These followers
    had removed the viewpoint (which freed up quota), but now have access to it again. Each
    follower has VISIBLE_TO incremented by the size of the viewpoint VISIBLE_TO, and SHARED_BY
    incremented by the size of the corresponding viewpoint SHARED_BY.
    """
    if len(revive_follower_ids) > 0:
      # The VISIBLE_TO adjustment is identical to that done for the AddFollowers operation.
      yield self.AddFollowers(client, viewpoint_id, revive_follower_ids)

      # Now make the SHARED_BY adjustment.
      vp_sb_acc_list = yield [gen.Task(Accounting.QueryViewpointSharedBy,
                                       client,
                                       viewpoint_id,
                                       follower_id,
                                       must_exist=False)
                              for follower_id in revive_follower_ids]

      for follower_id, vp_sb_acc in zip(revive_follower_ids, vp_sb_acc_list):
        if vp_sb_acc is not None:
          self.GetUserSharedBy(follower_id).IncrementStatsFrom(vp_sb_acc)

  @gen.coroutine
  def SavePhotos(self, client, user_id, viewpoint_id, photo_ids):
    """Generate and update accounting entries for a SavePhotos event.
      - photo_ids: list of *new* photos that were added (caller should exclude the ids of any
                   photos that already existed).

    We need to query all photos for size information. Creates the following entries:
      - (vs:<viewpoint>, ow:<user>): stats for user in default viewpoint.
      - (us:<user>, ow): overall stats for user.
    """
    photo_keys = [DBKey(photo_id, None) for photo_id in photo_ids]
    photos = yield gen.Task(Photo.BatchQuery, client, photo_keys, None)

    # Increment owned by stats on both the viewpoint and the user.
    self.GetViewpointOwnedBy(viewpoint_id, user_id).IncrementFromPhotos(photos)

    # Don't recompute owned-by stats, just copy them from the viewpoint accounting object.
    self.GetUserOwnedBy(user_id).CopyStatsFrom(self.GetViewpointOwnedBy(viewpoint_id, user_id))

  @gen.coroutine
  def SharePhotos(self, client, sharer_id, viewpoint_id, photo_ids, follower_ids):
    """Generate and update accounting entries for a ShareNew or ShareExisting event.
      - photo_ids: list of *new* photos that were added (caller should exclude the ids of any
                   photos that already existed).
      - follower_ids: list of ids of all followers of the viewpoint, *including* the sharer
                      if it is not removed from the viewpoint.

    We need to query all photos for size information. Creates the following entries:
      - (vs:<viewpoint>, sb:<sharer>): sum across all new photos for the sharer
      - (vs:<viewpoint>, vt): sum across all new photos
      - (us:<sharer>, sb): sum across all new photos for the sharer
    """
    photo_keys = [DBKey(photo_id, None) for photo_id in photo_ids]
    photos = yield gen.Task(Photo.BatchQuery, client, photo_keys, None)

    acc = Accounting()
    acc.IncrementFromPhotos(photos)

    # Viewpoint visible_to for viewpoint.
    self.GetViewpointVisibleTo(viewpoint_id).IncrementStatsFrom(acc)

    if sharer_id in follower_ids:
      # Viewpoint shared_by for sharer.
      self.GetViewpointSharedBy(viewpoint_id, sharer_id).IncrementStatsFrom(acc)

      # User shared_by for sharer.
      self.GetUserSharedBy(sharer_id).IncrementStatsFrom(acc)

    # Viewpoint visible_to for followers.
    for follower_id in follower_ids:
      self.GetUserVisibleTo(follower_id).IncrementStatsFrom(acc)

  @gen.coroutine
  def Unshare(self, client, viewpoint, ep_dicts, followers):
    """Generate and update accounting entries for an Unshare event. Multiple episodes may be
    impacted and multiple photos per episode.
      - viewpoint: viewpoint that contains the episodes and photos in ep_dicts.
      - ep_dicts: dict containing episode and photos ids: {ep_id0: [ph_id0, ph_id1], ep_id1: [ph_id2]}.
      - followers: list of all followers of the viewpoint, *including* the sharer.

    We need to look up all photos to fetch size information. Creates the following entries:
    - (vs:<viewpoint>, sb:<user>): stats for episode owners in this viewpoint.
    - (vs:<viewpoint>, vt): shared-with stats.

    Creates/adjusts entries for user_accountings based on adjustments to this viewpoint:
    - (us:<user>, sb): stats for episode owners.
    - (us:<followers>, vt): stats for all followers of the viewpoint.
    """
    from viewfinder.backend.db.episode import Episode

    # Gather db keys for all episodes and photos.
    episode_keys = []
    photo_keys = []
    for episode_id, photo_ids in ep_dicts.iteritems():
      episode_keys.append(DBKey(episode_id, None))
      for photo_id in photo_ids:
        photo_keys.append(DBKey(photo_id, None))

    # Query for all episodes and photos in parallel and in batches.
    episodes, photos = yield [gen.Task(Episode.BatchQuery,
                                       client,
                                       episode_keys,
                                       None,
                                       must_exist=False),
                              gen.Task(Photo.BatchQuery,
                                       client,
                                       photo_keys,
                                       None,
                                       must_exist=False)]

    viewpoint_id = viewpoint.viewpoint_id
    user_id = viewpoint.user_id
    ep_iter = iter(episodes)
    ph_iter = iter(photos)
    for episode_id, photo_ids in ep_dicts.iteritems():
      unshare_episode = next(ep_iter)
      acc = Accounting()
      unshare_photos = []
      for photo_id in photo_ids:
        acc.IncrementFromPhoto(next(ph_iter))

      if viewpoint.IsDefault():
        # Decrement owned by stats on both the viewpoint and the user.
        self.GetViewpointOwnedBy(viewpoint_id, user_id).DecrementStatsFrom(acc)
        # Don't recompute owned-by stats, just copy them from the viewpoint accounting object.
        self.GetUserOwnedBy(user_id).CopyStatsFrom(self.GetViewpointOwnedBy(viewpoint_id, user_id))
      else:
        # Viewpoint shared_by for sharer.
        self.GetViewpointSharedBy(viewpoint_id, unshare_episode.user_id).DecrementStatsFrom(acc)
        # Viewpoint visible_to for viewpoint.
        self.GetViewpointVisibleTo(viewpoint_id).DecrementStatsFrom(acc)
        # User shared_by for sharer.
        self.GetUserSharedBy(unshare_episode.user_id).DecrementStatsFrom(acc)

        # Viewpoint visible_to for followers.
        for follower in followers:
          if not follower.IsRemoved():
            self.GetUserVisibleTo(follower.user_id).DecrementStatsFrom(acc)

  @gen.coroutine
  def UploadEpisode(self, client, user_id, viewpoint_id, ph_dicts):
    """Generate and update accounting entries for an UploadEpisode event.
      - ph_dicts: list of *new* photo dicts that were added (caller should exclude any photos
                  that already existed).

    Creates the following entries:
      - (vs:<viewpoint>, ow:<user>): stats for user in default viewpoint.
      - (us:<user>, ow): overall stats for user.
    """
    # Increment owned by stats on both the viewpoint and the user.
    self.GetViewpointOwnedBy(viewpoint_id, user_id).IncrementFromPhotoDicts(ph_dicts)
    # Don't recompute owned-by stats, just copy them from the viewpoint accounting object.
    self.GetUserOwnedBy(user_id).CopyStatsFrom(self.GetViewpointOwnedBy(viewpoint_id, user_id))

  @gen.coroutine
  def Apply(self, client):
    """Applies all of the accounting deltas that have been collected in the accumulator."""
    # Apply all of the collected user accounting entries.
    tasks = []
    for us_ow_acc in self.us_ow_acc_dict.values():
      tasks.append(gen.Task(Accounting.ApplyAccounting, client, us_ow_acc))
    for us_vt_acc in self.us_vt_acc_dict.values():
      tasks.append(gen.Task(Accounting.ApplyAccounting, client, us_vt_acc))
    for us_sb_acc in self.us_sb_acc_dict.values():
      tasks.append(gen.Task(Accounting.ApplyAccounting, client, us_sb_acc))
    yield tasks

    # NOTE: It's important (for idempotency) to complete all user accounting updates before
    #       starting the viewpoint accounting updates because the removed follower deltas
    #       are derived from current values of the viewpoint accounting.

    # Apply all of the collected viewpoint accounting entries.
    tasks = []
    for vp_ow_acc in self.vp_ow_acc_dict.values():
      tasks.append(gen.Task(Accounting.ApplyAccounting, client, vp_ow_acc))
    for vp_vt_acc in self.vp_vt_acc_dict.values():
      tasks.append(gen.Task(Accounting.ApplyAccounting, client, vp_vt_acc))
    for vp_sb_acc in self.vp_sb_acc_dict.values():
      tasks.append(gen.Task(Accounting.ApplyAccounting, client, vp_sb_acc))
    yield tasks
