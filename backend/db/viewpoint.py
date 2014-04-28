# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder viewpoint.

Viewpoints are collections of episodes. Every user has a 'default'
viewpoint which contains all uploaded episodes. Viewpoints of type
'event' are created when a user shares episodes. Additional viewpoints
of type 'thematic' may be created to encompass arbitrary content. For
example, a shared set of family events, funny things you've seen in
NYC, all concerts at an event space, or a photographer's fashion
photos.

Viewpoint ids are constructed from a variable-length-encoded integer
device id and a variable-length-encoded unique id from the device. The
final value is base64-hex encoded.

Viewpoints can have followers, which are users who have permission to
view and possibly modify the viewpoint's content. Episodes are added
to a viewpoint via the 'Episode' relation.

Viewpoint types include:

  'default': every user has a default viewpoint to which all uploaded
             episodes are published.

  'event': event viewpoints are created every time an episode is shared.
           The sharees are added to the viewpoint as followers.

  'system': system-generated viewpoints used to welcome new users.

  Viewpoint: aggregation of episodes.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)',
               'spencer@emailscrubbed.com (Spencer Kimball)']

import json

from tornado import gen
from viewfinder.backend.db import db_client, vf_schema
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.asset_id import IdPrefix, ConstructAssetId, DeconstructAssetId, VerifyAssetId
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.hash_base import DBHashObject
from viewfinder.backend.db.friend import Friend
from viewfinder.backend.db.followed import Followed
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.lock import Lock
from viewfinder.backend.db.lock_resource_type import LockResourceType
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.viewpoint_lock_tracker import ViewpointLockTracker


@DBObject.map_table_attributes
class Viewpoint(DBHashObject):
  """Viewfinder viewpoint data object."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.VIEWPOINT)

  DEFAULT = 'default'
  EVENT = 'event'
  SYSTEM = 'system'

  TYPES = [DEFAULT, EVENT, SYSTEM]
  """Kinds of viewpoints."""

  # Limit how many followers may be part of a viewpoint.
  # Any change to this value should be coordinated with viewfinder client code
  #  to ensure that our clients catch this condition before sending to the server.
  MAX_FOLLOWERS = 150

  # Attributes that are projected for removed viewpoints.
  _IF_REMOVED_ATTRIBUTES = set(['viewpoint_id',
                                'type',
                                'follower_id',
                                'user_id',
                                'timestamp',
                                'labels',
                                'adding_user_id'])

  def __init__(self, viewpoint_id=None):
    super(Viewpoint, self).__init__()
    self.viewpoint_id = viewpoint_id

  @classmethod
  def ShouldScrubColumn(cls, name):
    return name == 'title'

  def IsDefault(self):
    """Returns true if the viewpoint is a default viewpoint."""
    return self.type == Viewpoint.DEFAULT

  def IsSystem(self):
    """Returns true if the viewpoint is a system viewpoint (ex. welcome conversation)."""
    return self.type == Viewpoint.SYSTEM

  @classmethod
  def ConstructViewpointId(cls, device_id, uniquifier):
    """Returns a viewpoint id constructed from component parts. See
    "ConstructAssetId" for details of the encoding.
    """
    return ConstructAssetId(IdPrefix.Viewpoint, device_id, uniquifier)

  @classmethod
  def DeconstructViewpointId(cls, viewpoint_id):
    """Returns the components of a viewpoint id: device_id and
    uniquifier.
    """
    return DeconstructAssetId(IdPrefix.Viewpoint, viewpoint_id)

  @classmethod
  def ConstructCoverPhoto(cls, episode_id, photo_id):
    """Construct a cover_photo dict."""
    assert episode_id is not None, episode_id
    assert photo_id is not None, photo_id
    return {'episode_id': episode_id, 'photo_id': photo_id}

  @classmethod
  @gen.coroutine
  def VerifyViewpointId(cls, client, user_id, device_id, viewpoint_id):
    """Ensures that a client-provided viewpoint id is valid according
    to the rules specified in VerifyAssetId.
    """
    yield VerifyAssetId(client, user_id, device_id, IdPrefix.Viewpoint, viewpoint_id, has_timestamp=False)

  @classmethod
  @gen.engine
  def AcquireLock(cls, client, viewpoint_id, callback):
    """Acquires a persistent global lock on the specified viewpoint."""
    op = Operation.GetCurrent()
    lock = yield gen.Task(Lock.Acquire, client, LockResourceType.Viewpoint, viewpoint_id,
                          op.operation_id)
    ViewpointLockTracker.AddViewpointId(viewpoint_id)
    callback(lock)

  @classmethod
  @gen.engine
  def ReleaseLock(cls, client, viewpoint_id, lock, callback):
    """Releases a previously acquired lock on the specified viewpoint."""
    yield gen.Task(lock.Release, client)
    ViewpointLockTracker.RemoveViewpointId(viewpoint_id)
    callback()

  @classmethod
  def AssertViewpointLockAcquired(cls, viewpoint_id):
    """Asserts that a lock has been acquired on the specified viewpoint."""
    assert ViewpointLockTracker.HasViewpointId(viewpoint_id), \
    'Lock for viewpoint, %s, should be acquired at this point but isn\'t.' % viewpoint_id

  def IsCoverPhotoSet(self):
    """The cover photo is consider set if it is a non empty dict."""
    if self.cover_photo is not None:
      assert len(self.cover_photo) > 0, self
      return True
    return False

  def MakeMetadataDict(self, follower):
    """Constructs a dictionary containing viewpoint metadata attributes, overridden by follower
    attributes where required (as viewed by the follower himself). The format conforms to
    VIEWPOINT_METADATA in json_schema.py.
    """
    # Combine all attributes from the viewpoint and follower records.
    vp_dict = self._asdict()
    foll_dict = follower.MakeMetadataDict()
    vp_dict.update(foll_dict)

    # If the follower is removed from the viewpoint, then only project certain attributes.
    if follower.IsRemoved():
      for attr_name in vp_dict.keys():
        if attr_name not in Viewpoint._IF_REMOVED_ATTRIBUTES:
          del vp_dict[attr_name]

    return vp_dict

  @gen.coroutine
  def AddFollowers(self, client, adding_user_id, existing_follower_ids, add_follower_ids, timestamp):
    """Adds the specified followers to this viewpoint, giving each follower CONTRIBUTE
    permission on the viewpoint. The caller is responsible for ensuring that the user adding
    the followers has permission to do so, and that the users to add are not yet followers.
    Returns the newly added followers.
    """
    @gen.coroutine
    def _UpdateFollower(follower_id):
      """Create a new follower of this viewpoint in the database."""
      follower = Follower(user_id=follower_id, viewpoint_id=self.viewpoint_id)
      follower.timestamp = timestamp
      follower.adding_user_id = adding_user_id
      follower.viewed_seq = 0
      follower.labels = [Follower.CONTRIBUTE]

      # Create the follower and corresponding Followed record.
      yield [gen.Task(follower.Update, client),
             gen.Task(Followed.UpdateDateUpdated, client, follower_id, self.viewpoint_id,
                      old_timestamp=None, new_timestamp=timestamp)]

      raise gen.Return(follower)

    # Adding user should be an existing user.
    assert adding_user_id is None or adding_user_id in existing_follower_ids, \
           (adding_user_id, existing_follower_ids)

    # Caller should never pass overlapping existing/add user id sets.
    assert not any(follower_id in existing_follower_ids for follower_id in add_follower_ids), \
           (existing_follower_ids, add_follower_ids)

    # Ensure that friendships are created between the followers to add.
    yield gen.Task(Friend.MakeFriendsWithGroup, client, add_follower_ids)

    # Ensure that friendships are created with existing followers.
    yield [gen.Task(Friend.MakeFriends, client, existing_id, add_id)
           for existing_id in existing_follower_ids
           for add_id in add_follower_ids]

    # Add new followers to viewpoint with CONTRIBUTE permission.
    add_followers = yield [_UpdateFollower(follower_id) for follower_id in add_follower_ids]

    raise gen.Return(add_followers)

  @gen.engine
  def SelectCoverPhoto(self, client, exclude_posts_set, callback, activities_list=None, available_posts_dict=None):
    """Select a cover photo for this viewpoint.
    This is used to select a cover photo if the current cover photo gets unshared.
    The selection order here assumes that the order of episodes and photos in the
    activities reflects the intended order of selection.  This won't be true
    of activities created before this change goes into production, but we've
    decided to accept this small variation in cover photo selection for these
    older activities because we don't think it's worth the extra complexity that it
    would take to make selection of those more 'correct'.
    Newer clients should order episodes and photos within share requests according to
    cover photo selection priority.
    Although older clients provide un-ordered lists of episodes/photos, a request transform
    will order episodes/photos from those clients using the original mobile client
    algorithm for cover photo selection. So we will select a new cover photo
    assuming these activities are already ordered.
    Caller may supply list of activities to use so that querying them for the viewpoint isn't needed.
    Caller may supply dict of available (not Removed/Unshared) posts so querying for posts isn't needed.
    Search process:
    1) oldest to newest activity (share_new or share_existing activities).
    2) within activity, first to last episode.
    3) within episode, first to last photo.
    Only photos which aren't unshared qualify.
    Returns: cover_photo dict of selected photo or None if one if no selection is found.
    """
    from viewfinder.backend.db.post import Post
    batch_limit = 50

    # cover_photo is not supported on default viewpoints.
    assert not self.IsDefault(), self

    @gen.coroutine
    def _QueryAvailablePost(episode_id, photo_id):
      if available_posts_dict is not None:
        post = available_posts_dict.get(Post.ConstructPostId(episode_id, photo_id), None)
      else:
        post = yield gen.Task(Post.Query, client, episode_id, photo_id, col_names=None)
        if post.IsRemoved():
          post = None
      raise gen.Return(post)

    # Loop over activities starting from the oldest.
    excl_start_key = None
    while True:
      if activities_list is None:
        activities = yield gen.Task(Activity.RangeQuery,
                                    client,
                                    self.viewpoint_id,
                                    range_desc=None,
                                    limit=batch_limit,
                                    col_names=None,
                                    excl_start_key=excl_start_key,
                                    scan_forward=False)
      else:
        activities = activities_list

      for activity in activities:
        if activity.name == 'share_new' or activity.name == 'share_existing':
          args_dict = json.loads(activity.json)
          # Now, loop through the episodes in the activity.
          for ep_dict in args_dict['episodes']:
            episode_id = ep_dict['episode_id']
            # And loop through the photos in each episode.
            for photo_id in ep_dict['photo_ids']:
              # Save cost of query on a post that we know is UNSHARED.
              if (episode_id, photo_id) not in exclude_posts_set:
                post = yield _QueryAvailablePost(episode_id, photo_id)
                if post is not None:
                  # If it hasn't been unshared, we're good to go.
                  callback(Viewpoint.ConstructCoverPhoto(episode_id, photo_id))
                  return

      if activities_list is not None or len(activities) < batch_limit:
        break
      else:
        excl_start_key = activities[-1].GetKey()

    # No unshared photos found in this viewpoint.
    callback(None)

  @classmethod
  def SelectCoverPhotoFromEpDicts(cls, ep_dicts):
    """Select a cover photo from the ep_dicts argument.
    Selection assumes episodes and photos are ordered according to selection preference.
    Returns: Either None if no photos found, or a cover_photo dict with selected photo.
    """
    cover_photo = None
    for ep_dict in ep_dicts:
      if len(ep_dict['photo_ids']) > 0:
        cover_photo = Viewpoint.ConstructCoverPhoto(ep_dict['episode_id'], ep_dict['photo_ids'][0])
        break
    return cover_photo

  @classmethod
  def IsCoverPhotoContainedInEpDicts(cls, cover_episode_id, cover_photo_id, ep_dicts):
    """Confirm existence of specified cover_photo in ep_dicts.
    Return: True if specified cover_photo matches photo in ep_dicts. Otherwise, False."""
    for ep_dict in ep_dicts:
      if cover_episode_id == ep_dict['episode_id']:
        for photo_id in ep_dict['photo_ids']:
          if cover_photo_id == photo_id:
            return True
    # Not found.
    return False

  @classmethod
  @gen.coroutine
  def CreateDefault(cls, client, user_id, device_id, timestamp):
    """Creates and returns a new user's default viewpoint."""
    from viewfinder.backend.db.user import User
    vp_dict = {'viewpoint_id': Viewpoint.ConstructViewpointId(device_id, User.DEFAULT_VP_ASSET_ID),
               'user_id': user_id,
               'timestamp': timestamp,
               'type': Viewpoint.DEFAULT}
    viewpoint, _ = yield gen.Task(Viewpoint.CreateNew, client, **vp_dict)
    raise gen.Return(viewpoint)

  @classmethod
  @gen.coroutine
  def CreateNew(cls, client, **vp_dict):
    """Creates the viewpoint specified by 'vp_dict' and creates a follower relation between
    the requesting user and the viewpoint with the ADMIN label. The caller is responsible for
    checking permission to do this, as well as ensuring that the viewpoint does not yet exist
    (or is just being identically rewritten).

    Returns a tuple containing the newly created objects: (viewpoint, follower).
    """
    tasks = []

    # Create the viewpoint.
    assert 'viewpoint_id' in vp_dict and 'user_id' in vp_dict and 'timestamp' in vp_dict, vp_dict
    viewpoint = Viewpoint.CreateFromKeywords(**vp_dict)
    viewpoint.last_updated = viewpoint.timestamp
    viewpoint.update_seq = 0
    tasks.append(gen.Task(viewpoint.Update, client))

    # Create the follower and give all permissions, since it's the owner.
    foll_dict = {'user_id': viewpoint.user_id,
                 'viewpoint_id': viewpoint.viewpoint_id,
                 'timestamp': viewpoint.timestamp,
                 'labels': list(Follower.PERMISSION_LABELS),
                 'viewed_seq': 0}
    if viewpoint.IsDefault():
      foll_dict['labels'].append(Follower.PERSONAL)

    follower = Follower.CreateFromKeywords(**foll_dict)
    tasks.append(gen.Task(follower.Update, client))

    # Create the corresponding Followed record.
    tasks.append(gen.Task(Followed.UpdateDateUpdated,
                          client,
                          viewpoint.user_id,
                          viewpoint.viewpoint_id,
                          old_timestamp=None,
                          new_timestamp=viewpoint.last_updated))
    yield tasks

    raise gen.Return((viewpoint, follower))

  @classmethod
  @gen.coroutine
  def CreateNewWithFollowers(cls, client, follower_ids, **vp_dict):
    """Calls the "CreateWithFollower" method to create a viewpoint with a single follower
    (the current user). Then, all users identified by "follower_ids" are added to that
    viewpoint as followers. Ensure that every pair of followers is friends with each other.
    The caller is responsible for checking permission to do this, as well as ensuring that
    the viewpoint and followers do not yet exist (or are just being identically rewritten).

    Returns a tuple containing the newly created objects: (viewpoint, followers). The
    followers list includes the owner.
    """
    # Create the viewpoint with the current user as its only follower.
    viewpoint, owner_follower = yield Viewpoint.CreateNew(client, **vp_dict)

    # Now add the additional followers.
    followers = yield viewpoint.AddFollowers(client,
                                             vp_dict['user_id'],
                                             [vp_dict['user_id']],
                                             follower_ids,
                                             viewpoint.timestamp)
    followers.append(owner_follower)

    raise gen.Return((viewpoint, followers))

  @classmethod
  @gen.coroutine
  def QueryWithFollower(cls, client, user_id, viewpoint_id):
    """Queries the specified viewpoint and follower and returns them as a (viewpoint, follower)
    tuple.
    """
    viewpoint, follower = yield [gen.Task(Viewpoint.Query, client, viewpoint_id, None, must_exist=False),
                                 gen.Task(Follower.Query, client, user_id, viewpoint_id, None, must_exist=False)]
    assert viewpoint is not None or follower is None, (viewpoint, follower)
    raise gen.Return((viewpoint, follower))

  @classmethod
  @gen.engine
  def QueryEpisodes(cls, client, viewpoint_id, callback, excl_start_key=None, limit=None):
    """Queries episodes belonging to the viewpoint (up to 'limit' total) for
    the specified 'viewpoint_id'. Starts with episodes having a key greater
    than 'excl_start_key'. Returns a tuple with the array of episodes and
    the last queried key.
    """
    from viewfinder.backend.db.episode import Episode

    # Query the viewpoint_id secondary index with excl_start_key & limit.
    query_expr = ('episode.viewpoint_id={id}', {'id': viewpoint_id})
    start_index_key = db_client.DBKey(excl_start_key, None) if excl_start_key is not None else None
    episode_keys = yield gen.Task(Episode.IndexQueryKeys, client, query_expr,
                                  start_index_key=start_index_key, limit=limit)
    episodes = yield gen.Task(Episode.BatchQuery, client, episode_keys, None)
    callback((episodes, episode_keys[-1].hash_key if len(episode_keys) > 0 else None))

  @classmethod
  @gen.coroutine
  def QueryFollowers(cls, client, viewpoint_id, excl_start_key=None, limit=None):
    """Query followers belonging to the viewpoint (up to 'limit' total) for
    the specified 'viewpoint_id'. The query is for followers starting with
    (but excluding) 'excl_start_key'. The callback is invoked with an array
    of follower objects and the last queried key.
    """
    # Query the viewpoint_id secondary index with excl_start_key & limit.
    query_expr = ('follower.viewpoint_id={id}', {'id': viewpoint_id})
    start_index_key = db_client.DBKey(excl_start_key, viewpoint_id) if excl_start_key is not None else None
    follower_keys = yield gen.Task(Follower.IndexQueryKeys,
                                   client,
                                   query_expr,
                                   start_index_key=start_index_key,
                                   limit=limit)

    last_key = follower_keys[-1].hash_key if len(follower_keys) > 0 else None

    followers = yield gen.Task(Follower.BatchQuery, client, follower_keys, None)

    raise gen.Return((followers, last_key))

  @classmethod
  def QueryFollowerIds(cls, client, viewpoint_id, callback, excl_start_key=None, limit=None):
    """Query followers belonging to the viewpoint (up to 'limit' total) for
    the specified 'viewpoint_id'. The query is for followers starting with
    (but excluding) 'excl_start_key'. The callback is invoked with an array
    of follower user ids and the last queried key.
    """
    def _OnQueryFollowerKeys(follower_keys):
      follower_ids = [key.hash_key for key in follower_keys]
      last_key = follower_ids[-1] if len(follower_ids) > 0 else None

      callback((follower_ids, last_key))

    # Query the viewpoint_id secondary index with excl_start_key & limit.
    query_expr = ('follower.viewpoint_id={id}', {'id': viewpoint_id})
    start_index_key = db_client.DBKey(excl_start_key, viewpoint_id) if excl_start_key is not None else None
    Follower.IndexQueryKeys(client, query_expr, callback=_OnQueryFollowerKeys,
                            start_index_key=start_index_key, limit=limit)

  @classmethod
  def VisitFollowerIds(cls, client, viewpoint_id, visitor, callback, consistent_read=False):
    """Visit all followers of the specified viewpoint and invoke the
    "visitor" function with each follower id. See VisitIndexKeys for
    additional detail.
    """
    def _OnVisit(follower_key, visit_callback):
      visitor(follower_key.hash_key, visit_callback)

    query_expr = ('follower.viewpoint_id={id}', {'id': viewpoint_id})
    Follower.VisitIndexKeys(client, query_expr, _OnVisit, callback, consistent_read=consistent_read)

  @classmethod
  def QueryActivities(cls, client, viewpoint_id, callback, excl_start_key=None, limit=None):
    """Queries activities belonging to the viewpoint (up to 'limit' total) for
    the specified 'viewpoint_id'. Starts with activities having a key greater
    than 'excl_start_key'. Returns a tuple with the array of activities and
    the last queried key.
    """
    def _OnQueryActivities(activities):
      callback((activities, activities[-1].activity_id if len(activities) > 0 else None))

    Activity.RangeQuery(client, viewpoint_id, range_desc=None, limit=limit, col_names=None,
                        callback=_OnQueryActivities, excl_start_key=excl_start_key)

  @classmethod
  def QueryComments(cls, client, viewpoint_id, callback, excl_start_key=None, limit=None):
    """Queries comments belonging to the viewpoint (up to 'limit' total) for
    the specified 'viewpoint_id'. Starts with comments having a key greater
    than 'excl_start_key'. Returns a tuple with the array of comments and
    the last queried key.
    """
    def _OnQueryComments(comments):
      callback((comments, comments[-1].comment_id if len(comments) > 0 else None))

    Comment.RangeQuery(client, viewpoint_id, range_desc=None, limit=limit, col_names=None,
                       callback=_OnQueryComments, excl_start_key=excl_start_key)

  @classmethod
  @gen.engine
  def AddFollowersOperation(cls, client, callback, activity, user_id, viewpoint_id, contacts):
    """Adds contacts as followers to the specified viewpoint. Notifies all viewpoint
    followers about the new followers.
    """
    # TODO(Andy): Remove this once the AddFollowersOperation is in production.
    from viewfinder.backend.op.add_followers_op import AddFollowersOperation
    AddFollowersOperation.Execute(client, activity, user_id, viewpoint_id, contacts, callback=callback)

  @classmethod
  @gen.engine
  def UpdateOperation(cls, client, callback, act_dict, vp_dict):
    """Updates viewpoint metadata."""
    # TODO(Andy): Remove this once the UpdateViewpointOperation is in production.
    from viewfinder.backend.op.update_viewpoint_op import UpdateViewpointOperation
    user_id = vp_dict.pop('user_id')
    UpdateViewpointOperation.Execute(client, act_dict, user_id, vp_dict, callback=callback)
