# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder UnshareOperation.

  Unshares a set of photos that were previously posted within the specified viewpoint
  and episodes. Unsharing results in an UNSHARED attribute being added to the top-level
  posts, and to any posts which are part of the "sharing tree" -- that is, the tree formed
  by sharing episodes from viewpoint to viewpoint. This tree can become very wide and/or
  very deep, so a limit is placed on the extent to which we'll traverse. In addition, there
  is a 7-day limit following the original share, after which unsharing is no longer possible.

  Only the original contributor of the episodes can unshare them, though due to the
  recursive nature of unshare, this contributor has indirect power to unshare episodes which
  derived from the originals.
"""

__authors__ = ['mike@emailscrubbed.com (Mike Purtell)',
               'andy@emailscrubbed.com (Andy Kimball)']

import time

from collections import OrderedDict
from copy import deepcopy
from tornado import gen
from viewfinder.backend.base import constants
from viewfinder.backend.base.exceptions import InvalidRequestError, PermissionError
from viewfinder.backend.db.accounting import Accounting, AccountingAccumulator
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation
from viewfinder.backend.op.viewpoint_lock_tracker import ViewpointLockTracker


class UnshareOperation(ViewfinderOperation):
  """The Unshare operation follows the four phase pattern described in the header of
  operation_map.py.
  """

  _UNSHARE_LIMIT = 100
  """Max number of episodes that can be unshared in a single unshare
  operation.
  """

  def __init__(self, client, activity, viewpoint_id, episodes):
    super(UnshareOperation, self).__init__(client)
    self._viewpoint_id = viewpoint_id
    self._ep_dicts = episodes
    self._activity = activity
    self._unsharer_id = self._op.user_id
    self._num_unshares = 0
    self._unshares_dict = {}
    self._already_removed_ids = set()
    self._vp_followers_dict = {}
    self._cover_photo_set = set()
    self._lock_tracker = ViewpointLockTracker(client)

  @classmethod
  @gen.coroutine
  def Execute(cls, client, activity, viewpoint_id, episodes):
    """Entry point called by the operation framework."""
    yield UnshareOperation(client, activity, viewpoint_id, episodes)._Unshare()

  @gen.coroutine
  def _Unshare(self):
    """"Orchestrates the unshare operation by executing each of the phases in turn.

    As a side effect of traversal, Unshare will accumulate information about the unshare action
    in "_unshares_dict" using the following format:

      {'vp_id0': [{'ep_id0': [ph_id0, ph_id1, ...]},
                  {'ep_id1': [ph_id2]}],
       'vp_id1': ...}

    This information is later used to formulate the necessary notifications and activities that
    need to be created for the affected viewpoints.
    """

    try:
      # Lock primary viewpoint during entire operation.
      yield self._lock_tracker.AcquireViewpointLock(self._viewpoint_id)

      # Gather info about all viewpoints/episodes/posts needed to make the update.
      # Do any permission and request validity checks here.
      # Acquire all related viewpoint locks.
      yield self._Check()

      # Aborts are NOT allowed after this point because we're about to modify db state.
      # Ensure that we haven't modified it yet.
      self._client.CheckDBNotModified()

      # Update the posts that are being unshared with the UNSHARED label.
      yield self._Update()

      # Generate and write/update accounting entries based on gathered information.
      yield self._Account()

      # Generate notifications for all followers affected by these changes.
      yield self._Notify()
    finally:
      # Release all locks acquired while processing this operation.
      yield self._lock_tracker.ReleaseAllViewpointLocks()

  @gen.coroutine
  def _Check(self):
    """Gathers pre-mutation information:
       1. Queries for all viewpoints/followers that contain photos to be unshared.
       2. Queries for all episodes and posts that need to be unshared.
       3. Checkpoints ids of episodes and photos that need to be unshared.
       4. Checkpoints ids of posts that were already removed but not unshared.
       5. Checkpoints set of viewpoints which will have cover photo updated.

       Validates the following:
       1. Permission to unshare.
       2. Unshare clawback period (can't unshare after 7 days).
       3. Episode/photo existence.
       4. Unshare not allowed if photos have been shared too many times.
    """
    @gen.coroutine
    def _QueryPosts(episode_id, photo_ids):
      """Queries the posts for the given episode id and photo ids."""
      post_keys = [DBKey(episode_id, photo_id) for photo_id in photo_ids]
      posts = yield gen.Task(Post.BatchQuery, self._client, post_keys, None, must_exist=False)
      raise gen.Return(posts)

    @gen.coroutine
    def _ProcessEpisode(ep_dict):
      """Makes several permission and validation checks and initiates the gathering of unshare
      information via traversal of the sharing tree.
      """
      episode, posts = yield [gen.Task(Episode.QueryIfVisible, self._client, self._unsharer_id, ep_dict['episode_id']),
                              gen.Task(_QueryPosts, ep_dict['episode_id'], ep_dict['photo_ids'])]

      # Validate that the episode is visible to the caller.
      if episode is None or episode.user_id != self._unsharer_id:
        raise PermissionError('User %d does not have permission to unshare photos from episode "%s".' %
                              (self._unsharer_id, ep_dict['episode_id']))

      # Validate that the episode is in the requested viewpoint.
      if episode.viewpoint_id != self._viewpoint_id:
        raise InvalidRequestError('Episode "%s" is not in viewpoint "%s".' % (episode.episode_id, self._viewpoint_id))

      # Validate that the episode was shared no more than N days ago.
      if now - episode.publish_timestamp > Photo.CLAWBACK_GRACE_PERIOD:
        days = Photo.CLAWBACK_GRACE_PERIOD / constants.SECONDS_PER_DAY
        raise PermissionError('Photos from episode "%s" cannot be unshared because they were shared '
                              'more than %d days ago.' % (episode.episode_id, days))

      # Validate that each photo is in the requested episode.
      for photo_id, post in zip(ep_dict['photo_ids'], posts):
        if post is None:
          raise PermissionError('Photo "%s" is not in episode "%s".' % (photo_id, ep_dict['episode_id']))

      yield self._GatherUnshares(episode, posts)

    @gen.coroutine
    def _ProcessViewpoint(viewpoint_id):
      """Acquires a lock for the given viewpoint. Queries the viewpoint's followers and stores
      them in followers_dict.
      """
      yield self._lock_tracker.AcquireViewpointLock(viewpoint_id)

      viewpoint = yield gen.Task(Viewpoint.Query, self._client, viewpoint_id, None)
      followers, _ = yield gen.Task(Viewpoint.QueryFollowers,
                                    self._client,
                                    viewpoint_id,
                                    limit=Viewpoint.MAX_FOLLOWERS)

      self._vp_followers_dict[viewpoint_id] = (viewpoint, followers)

    # Start populating the checkpoint if this is the first time the operation has been run.
    if self._op.checkpoint is None:
      # Capture current time to use when determining clawback period violation.
      now = time.time()

      # Iterate over all of the episodes in the request.
      yield [_ProcessEpisode(ep_dict) for ep_dict in self._ep_dicts]

      # Iterate over all viewpoints containing posts to unshare, locking and querying them.
      yield [_ProcessViewpoint(viewpoint_id) for viewpoint_id in self._unshares_dict.iterkeys()]

      for viewpoint_id, ep_dicts in self._unshares_dict.iteritems():
        # Check whether a cover photo needs to be set on the viewpoint.
        viewpoint, _ = self._vp_followers_dict[viewpoint_id]
        if self._IsCoverPhotoUnshared(viewpoint, ep_dicts):
          self._cover_photo_set.add(viewpoint_id)

      # Set checkpoint.
      # Set of posts to unshare and set of followers that are already removed need to be
      # check-pointed because they may change in the UPDATE phase. If we fail after UPDATE,
      # but before NOTIFY, we would not send correct notifications on retry.
      checkpoint = {'unshares': self._unshares_dict,
                    'removed': list(self._already_removed_ids),
                    'cover': list(self._cover_photo_set)}
      yield self._op.SetCheckpoint(self._client, checkpoint)
    else:
      self._unshares_dict = self._op.checkpoint['unshare']
      self._already_removed_ids = set(self._op.checkpoint['removed'])
      self._cover_photo_set = set(self._op.checkpoint['cover'])

      # Lock and query complete set of viewpoints that were gathered the first time the operation was executed.
      yield [_ProcessViewpoint(viewpoint_id) for viewpoint_id in self._unshares_dict.iterkeys()]

  @gen.coroutine
  def _Update(self):
    """Updates the database:
       1. Unshares all request photos, as well as shares of those photos.
       2. Updates cover photo if it was unshared.
    """

    """Apply updates to db based on previously collected information. Update the affected POSTs
    with UNSHARED labels set.
    """
    @gen.coroutine
    def _UnsharePost(episode_id, photo_id):
      """Add UNSHARED label to the given post and write it to the DB."""
      post = Post.CreateFromKeywords(episode_id=episode_id, photo_id=photo_id)
      post.labels.add(Post.UNSHARED)
      post.labels.add(Post.REMOVED)
      yield gen.Task(post.Update, self._client)

    # Now that the extent of unshares has been completely discovered and accounted for, unshare all of the posts.
    yield [gen.Task(_UnsharePost, episode_id, photo_id)
           for ep_dicts in self._unshares_dict.itervalues()
           for episode_id, photo_ids in ep_dicts.iteritems()
           for photo_id in photo_ids]

    # Update any cover photos that were unshared.
    for viewpoint_id in self._cover_photo_set:
      # Cover_photo has been unshared, so need to select a new one.
      viewpoint, _ = self._vp_followers_dict[viewpoint_id]
      viewpoint.cover_photo = yield gen.Task(viewpoint.SelectCoverPhoto, self._client, set())
      yield gen.Task(viewpoint.Update, self._client)

  @gen.coroutine
  def _Account(self):
    """Makes accounting changes:
       1. For unshared photos.
    """
    acc_accum = AccountingAccumulator()

    # Make accounting changes for all unshared photos.
    tasks = []
    for viewpoint_id, ep_dicts in self._unshares_dict.iteritems():
      # Filter out any photos which were already removed.
      if len(self._already_removed_ids) > 0:
        ep_dicts = deepcopy(ep_dicts)
        for episode_id, photo_ids in ep_dicts.iteritems():
          ep_dicts[episode_id] = [photo_id for photo_id in photo_ids
                                  if Post.ConstructPostId(episode_id, photo_id) not in self._already_removed_ids]

      viewpoint, followers = self._vp_followers_dict[viewpoint_id]
      tasks.append(acc_accum.Unshare(self._client,
                                     viewpoint,
                                     ep_dicts,
                                     [follower for follower in followers]))
    yield tasks

    yield acc_accum.Apply(self._client)

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
       1. Notifies removed followers that viewpoints have new activity.
       2. Notify followers of viewpoints that photos have been unshared.
    """
    truncated_ts, device_id, (client_id, server_id) = Activity.DeconstructActivityId(self._activity['activity_id'])

    @gen.coroutine
    def _NotifyOneViewpoint(notify_viewpoint_id):
      """Notify all followers of a single viewpoint of the unshare."""
      # Add viewpoint_id to activity_id for unshares from derived viewpoints. This ensures that
      # the activity_id is globally unique, which the client requires. It also preserves the
      # guarantee of idempotency, since the viewpoint_id will always be the same no matter how
      # many times this unshare operation is executed.
      if notify_viewpoint_id != self._viewpoint_id:
        # Override the activity_id attribute in "activity".
        act_dict = deepcopy(self._activity)
        act_dict['activity_id'] = Activity.ConstructActivityId(truncated_ts, device_id,
                                                               (client_id, notify_viewpoint_id))
      else:
        act_dict = self._activity

      notify_ep_dicts = [{'episode_id': episode_id,
                          'photo_ids': photo_ids}
                         for episode_id, photo_ids in self._unshares_dict[notify_viewpoint_id].iteritems()]

      yield NotificationManager.NotifyUnshare(self._client,
                                              notify_viewpoint_id,
                                              self._vp_followers_dict[notify_viewpoint_id][1],
                                              act_dict,
                                              notify_ep_dicts,
                                              notify_viewpoint_id in self._cover_photo_set)

    # Loop over all viewpoints affected by the unshare and create
    # notifications and activities for them. Do this one at a time for
    # two reasons:
    #   1. spread out load for large unshare operations, since they're
    #      low priority
    #   2. make results more deterministic, which makes testing easier
    for notify_viewpoint_id in sorted(self._unshares_dict.keys()):
      assert self._lock_tracker.IsViewpointLocked(notify_viewpoint_id), self
      yield gen.Task(_NotifyOneViewpoint, notify_viewpoint_id)

  @gen.coroutine
  def _GatherUnshares(self, episode, posts):
    """Recursively accumulates the set of viewpoints, episodes, and posts that are affected
    by an unshare operation rooted at the specified episodes and posts. Adds the unshare
    information to "unshares_dict" in the format described in the UnshareOperation._Unshare
    docstring.

    Also gets list of ids of posts that have already been removed. Accounting will not be
    decremented again for these posts, since remove_photos already did it.

    This method does not mutate the database; it just gathers the information necessary to
    do so. Because episodes can be shared multiple times, and can even circle back to a
    previous viewpoint, it is necessary to traverse the entire sharing tree before concluding
    that all episodes to unshare have been discovered. If too many episodes have been
    traversed, raises a PermissionError. This protects the server from unshares of photos
    that have gone massively viral.
    """
    @gen.coroutine
    def _ProcessChildEpisode(child_episode, photo_ids_to_unshare):
      """For each child episode, query for the set of posts to unshare from each (might be a
      subset of parent posts). Recurse into the child episode to gather more unshares.
      """
      post_keys = [DBKey(child_episode.episode_id, ph_id) for ph_id in photo_ids_to_unshare]
      child_posts = yield gen.Task(Post.BatchQuery, self._client, post_keys, None, must_exist=False)
      yield gen.Task(self._GatherUnshares, child_episode, child_posts)

    # Check whether episode traversal limit has been exceeded.
    self._num_unshares += 1
    if self._num_unshares > UnshareOperation._UNSHARE_LIMIT:
      raise PermissionError('These photos cannot be unshared because they have already been shared too widely.')

    # Get posts that were previously gathered. 
    vp_dict = self._unshares_dict.get(episode.viewpoint_id, None)
    if vp_dict is not None and episode.episode_id in vp_dict:
      photo_ids_to_unshare = OrderedDict.fromkeys(vp_dict[episode.episode_id])
    else:
      photo_ids_to_unshare = OrderedDict()

    # Add photo ids to unshare. Don't include posts that have already been unshared, but do
    # include posts that have been removed (so that we add the UNSHARED label).
    for post in posts:
      if post is not None and not post.IsUnshared():
        photo_ids_to_unshare[post.photo_id] = None
        if post.IsRemoved():
          # Post has already been removed, so accounting should not be adjusted again for it.
          self._already_removed_ids.add(Post.ConstructPostId(post.episode_id, post.photo_id))

    if len(photo_ids_to_unshare) > 0:
      self._unshares_dict.setdefault(episode.viewpoint_id, {})[episode.episode_id] = list(photo_ids_to_unshare)

    # Recursively descend into children of the episode, looking for additional branches of the sharing tree.
    # Use secondary index to find children of "episode".
    query_expr = ('episode.parent_ep_id={id}', {'id': episode.episode_id})
    child_episodes = yield gen.Task(Episode.IndexQuery, self._client, query_expr, None)
    yield [_ProcessChildEpisode(child_episode, photo_ids_to_unshare)
           for child_episode in child_episodes]

  def _IsCoverPhotoUnshared(self, viewpoint, ep_dicts):
    """Returns true if the given viewpoint's cover photo is in the set of photos which are
    to be unshared. "ep_dicts" is in the format described in the docstring for _Unshare.
    """
    if not viewpoint.IsDefault():
      unshared_posts_set = set((episode_id, photo_id)
                               for episode_id, photo_ids in ep_dicts.iteritems()
                               for photo_id in photo_ids)

      # We should have a cover_photo set if we had photos to unshare.
      assert len(unshared_posts_set) == 0 or viewpoint.IsCoverPhotoSet(), viewpoint

      # Check if the current cover_photo is in the set of photos being unshared.
      post_id = (viewpoint.cover_photo['episode_id'], viewpoint.cover_photo['photo_id'])
      if post_id in unshared_posts_set:
        return True

    return False
