# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Crawls over the database, looking for problems and inconsistencies that
may have crept in due to bugs or lack of strong DB consistency. When problems
are found, logs them and e-mails notifications about them. Also repairs
problems if the --repair option is specified.

Usage:
  # Check the database, logging and e-mailing any corruptions found.
  python dbchk.py

  # Lookup last successful status and only scan viewpoints updated after the previous run's start time.
  # Additionally, skip run if the previous successful run started less than 6 hours ago.
  python dbchk.py --smart_scan --hours_between_runs=6

  # Repair corruptions found in the database during the check phase.
  python dbchk.py --repair=True --viewpoints=vp1,vp2
"""

__author__ = 'andy@emailscrubbed.com (Andrew Kimball)'

import json
import logging
import sys
import traceback
import time

from collections import defaultdict
from copy import deepcopy
from functools import partial
from tornado import gen, options, stack_context
from tornado.ioloop import IOLoop
from viewfinder.backend.base import constants, main, util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import db_client, vf_schema
from viewfinder.backend.db.accounting import Accounting
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.followed import Followed
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.job import Job
from viewfinder.backend.db.notification import Notification
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user_post import UserPost
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.op_context import EnterOpContext
from viewfinder.backend.services.email_mgr import EmailManager, SendGridEmailManager


options.define('viewpoints', type=str, default=[], multiple=True,
               help='check (and possibly repair) this list of viewpoint ids, ignores smart_scan; '
                    'check all viewpoints if None')

options.define('smart_scan', type=bool, default=False,
               help='only scan viewpoints updated since the last dbchk run')

options.define('repair', type=bool, default=False,
               help='if true, automatically repair corruption in checked viewpoints')

options.define('email', default='dbchk@emailscrubbed.com',
               help='email to which to send corruption report; no report sent if set to blank')

options.define('require_lock', type=bool, default=True,
               help='attempt to grab the job:dbchk lock before running. Exit if acquire fails.')

options.define('hours_between_runs', type=int, default=0,
               help='minimum time since start of last successful full run (without --viewpoints)')


_TEST_MODE = False
"""If true, run the checker in test mode."""

_CHECK_THRESHOLD_TIMESPAN = constants.SECONDS_PER_HOUR
"""Don't check viewpoints that have been recently modified (within this
time window).
"""


class DatabaseChecker(object):
  """Collection of methods that scan the database, looking for instances
  of corruption.
  """
  _MAX_EMAIL_INTERVAL = 60 * 30
  """Send notification email at most once every thirty minutes."""

  _EMAIL_TEXT = 'Found corruption(s) in database:\n\n%s'
  """Text to send in email reporting the corruption."""

  _MAX_VISITED_USERS = 10000
  """When the visited_users set exceeds this number, trigger per-user actions for each user."""

  def __init__(self, client, repair=False):
    # Save DB client and repair flag.
    self._client = client
    self._repair = repair

    # Dictionary mapping viewpoint ids to list of detected corruptions in each viewpoint.
    self._corruptions = {}

    # Set of users that are followers of visited viewpoints. When it reaches a certain level,
    # we process each user in turn. We store the latest viewpoint that cause the visit so that
    # we know which viewpoint to process to repair errors.
    # Only followers of shared viewpoints are added since the per-user actions do not take
    # default viewpoint information into account.
    self._visited_users = {}

    # Reset time that last email was sent.
    self._last_email = util.GetCurrentTimestamp()

    self._num_visited_viewpoints = 0

    # Current viewpoint or user being processed, used in failed job message.
    self._current_viewpoint = ''
    self._current_user = ''

  @gen.engine
  def CheckAllViewpoints(self, callback, last_scan=None):
    """Scans the entire Viewpoint table, looking for corruption in each
    viewpoint that has not already been scanned in a previous pass.
    """
    # Clear email args used for testing.
    self._email_args = None

    # Only scan for newly updated viewpoints if previous scan has taken place.
    if last_scan is None:
      scan_filter = None
    else:
      scan_filter = {'last_updated': db_client.ScanFilter([last_scan], 'GE')}

    yield gen.Task(self._ThrottledScan,
                   Viewpoint,
                   visitor=self.CheckViewpoint,
                   scan_filter=scan_filter,
                   max_read_units=Viewpoint._table.read_units)

    # Force a check of all visited users, we may have some remaining.
    yield gen.Task(self._CheckVisitedUsers)

    # Check to see whether a corruption report needs to be emailed.
    yield gen.Task(self._SendEmail)

    callback()

  @gen.engine
  def CheckViewpointList(self, viewpoint_ids, callback):
    """Looks for corruption in each of the viewpoints in the
    "viewpoint_ids" list.
    """
    # Clear email args used for testing.
    self._email_args = None

    for vp_id in viewpoint_ids:
      viewpoint = yield gen.Task(Viewpoint.Query, self._client, vp_id, None)
      yield gen.Task(self.CheckViewpoint, viewpoint)

    # Force a check of all visited users, we may have some remaining.
    yield gen.Task(self._CheckVisitedUsers)

    # Check to see whether a corruption report needs to be emailed.
    yield gen.Task(self._SendEmail)

    callback()

  @gen.engine
  def CheckViewpoint(self, viewpoint, callback):
    """Checks the specified viewpoint for various kinds of corruption."""
    # Don't check viewpoints that were modified within last hour, as operation might still be in progress.
    if _TEST_MODE or viewpoint.last_updated <= time.time() - _CHECK_THRESHOLD_TIMESPAN:
      logging.info('Processing viewpoint "%s"...' % viewpoint.viewpoint_id)
      self._current_viewpoint = viewpoint.viewpoint_id
      self._num_visited_viewpoints += 1

      # Gather followers.
      query_func = partial(Viewpoint.QueryFollowerIds, self._client, viewpoint.viewpoint_id)
      follower_ids = yield gen.Task(self._CacheQuery, query_func)
      followers = yield [gen.Task(Follower.Query, self._client, f_id, viewpoint.viewpoint_id, None)
                         for f_id in follower_ids]

      # Gather activities.
      # _RepairBadCoverPhoto() depends on the order of activities produced by this query.  If it
      #   changes, _RepairBadCoverPhoto() needs to be modified to compensate.
      query_func = partial(Activity.RangeQuery, self._client, viewpoint.viewpoint_id,
                           range_desc=None, col_names=None)
      activities = yield gen.Task(self._CacheQuery, query_func)

      # Gather episodes and photos.
      query_func = partial(Viewpoint.QueryEpisodes, self._client, viewpoint.viewpoint_id)
      episodes = yield gen.Task(self._CacheQuery, query_func)
      ep_photos_list = []
      for episode in episodes:
        query_func = partial(Post.RangeQuery, self._client, episode.episode_id,
                             range_desc=None, col_names=None)
        posts = yield gen.Task(self._CacheQuery, query_func)
        photos = yield [gen.Task(Photo.Query, self._client, post.photo_id, col_names=None) for post in posts]

        user_posts = None
        if viewpoint.IsDefault():
          # Only query user_post entries if this is a default viewpoint.
          user_posts = yield [gen.Task(UserPost.Query, self._client, episode.user_id,
                                       Post.ConstructPostId(post.episode_id, post.photo_id),
                                       None, must_exist=False) for post in posts]

        ep_photos_list.append((episode, photos, posts, user_posts))
        if (len(ep_photos_list) % 100) == 0:
          logging.info('  caching photos from %d+ episode records...' % len(ep_photos_list))

      # Gather comments.
      query_func = partial(Comment.RangeQuery, self._client, viewpoint.viewpoint_id,
                           range_desc=None, col_names=None)
      comments = yield gen.Task(self._CacheQuery, query_func)

      # Gather accounting entries for this viewpoint.
      query_func = partial(Accounting.RangeQuery, self._client,
                           '%s:%s' % (Accounting.VIEWPOINT_SIZE, viewpoint.viewpoint_id),
                           range_desc=None, col_names=None)
      accounting = yield gen.Task(self._CacheQuery, query_func)

      if viewpoint.IsDefault():
        # Default viewpoint has a viewpoint-level OWNED_BY accounting entry matching exactly
        # the user-level OWNED_BY entry for the viewpoint owner. Look it up now.
        user_accounting = yield gen.Task(Accounting.Query, self._client,
                                         '%s:%d' % (Accounting.USER_SIZE, viewpoint.user_id),
                                         Accounting.OWNED_BY, None, must_exist=False)
        if user_accounting is not None:
          # Add it to the accounting list. It will be automatically checked in CheckBadViewpointAccounting.
          accounting.append(user_accounting)
      else:
        # Set each follower id in visited_users. We only do this for shared viewpoint as the per-user
        # actions do not process default viewpoint accounting.
        for f_id in follower_ids:
          self._visited_users[f_id] = viewpoint.viewpoint_id

      refreshed_viewpoint = yield gen.Task(Viewpoint.Query, self._client, viewpoint.viewpoint_id, None)
      # TODO(marc): check if other fields have changed?

      # Now that assets have been gathered, check to see if viewpoint was modified during the gathering phase.
      if _TEST_MODE or refreshed_viewpoint.last_updated <= time.time() - _CHECK_THRESHOLD_TIMESPAN:
        # Check for invalid viewpoint metadata.
        yield gen.Task(self._CheckInvalidViewpointMetadata, viewpoint, activities)

        # Check for multiple share_new activities.
        yield gen.Task(self._CheckMultipleShareNew, viewpoint, activities)

        # Check for missing activities.
        yield gen.Task(self._CheckMissingActivities, viewpoint, activities, followers, ep_photos_list, comments)

        # Check for missing posts referenced by activities.
        yield gen.Task(self._CheckMissingPosts, viewpoint, activities, ep_photos_list)

        # Check for any missing Followed records.
        yield gen.Task(self._CheckMissingFollowed, viewpoint, followers)

        # Check for empty viewpoint.
        yield gen.Task(self._CheckEmptyViewpoint, viewpoint, activities, followers, ep_photos_list, comments)

        # Check for missing/bad accounting entries.
        yield gen.Task(self._CheckBadViewpointAccounting, viewpoint, ep_photos_list, accounting)

        if not viewpoint.IsDefault():
          # Check for valid cover_photo.
          yield gen.Task(self._CheckBadCoverPhoto, viewpoint, ep_photos_list, activities)
      else:
        logging.info('Aborting viewpoint "%s" check because it was modified while gathering its assets...',
                     viewpoint.viewpoint_id)
    else:
      logging.info('Skipping viewpoint "%s" because it was modified in the last hour...', viewpoint.viewpoint_id)

    # Check users in visited_users if it has grown big enough.
    self._current_viewpoint = ''
    yield gen.Task(self._MaybeCheckVisitedUsers)
    callback()

  @gen.engine
  def _CheckMultipleShareNew(self, viewpoint, activities, callback):
    """Checks that a viewpoint has at most one share_new activity."""
    # Gather any duplicate share_new activities.
    earliest_activity = None
    dup_activities = []
    for activity in activities:
      if activity.name == 'share_new':
        if earliest_activity is None:
          earliest_activity = activity
        elif activity.timestamp < earliest_activity.timestamp and activity.user_id == viewpoint.user_id:
          dup_activities.append(earliest_activity)
          earliest_activity = activity
        else:
          dup_activities.append(activity)

    # Report corruption for each duplicate.
    if len(dup_activities) > 0:
      for activity in dup_activities:
        # Only support empty or matching or redundant follower_ids.
        follower_ids = json.loads(activity.json)['follower_ids']
        assert len(follower_ids) == 0 or follower_ids == json.loads(earliest_activity.json)['follower_ids'] or \
               (len(follower_ids) == 1 and follower_ids[0] == viewpoint.user_id), \
               (activity, earliest_activity)
        yield gen.Task(self._ReportCorruption, viewpoint.viewpoint_id,
                       'multiple share_new activities', (earliest_activity.activity_id, activity.activity_id),
                       partial(self._RepairMultipleShareNew, activity))
    callback()

  @gen.engine
  def _RepairMultipleShareNew(self, activity, callback):
    """Replaces extraneous share_new activities with corresponding
    share_existing activity.
    """
    assert activity.name == 'share_new', activity
    act_args = json.loads(activity.json)
    del act_args['follower_ids']

    # Update share_new => share_existing.
    update_activity = Activity.CreateFromKeywords(viewpoint_id=activity.viewpoint_id,
                                                  activity_id=activity.activity_id,
                                                  name='share_existing',
                                                  json=json.dumps(act_args))
    yield gen.Task(update_activity.Update, self._client)
    logging.warning('  updated activity: %s', activity.activity_id)

    callback()

  @gen.engine
  def _CheckMissingActivities(self, viewpoint, activities, followers, ep_photos_list, comments, callback):
    """Checks that every follower, episode, photo, and comment is
    referenced at least once by an activity.

    TODO: Consider checking for missing unshare activities.
    """
    # Index the activity contents.
    index = set()

    # Viewpoint creator is automatically a follower.
    index.add(viewpoint.user_id)

    has_share_new = False
    for activity in activities:
      if activity.name == 'share_new':
        has_share_new = True

      invalidate = json.loads(activity.json)
      if activity.name in ['add_followers', 'share_new']:
        [index.add(f_id) for f_id in invalidate['follower_ids']]
      if activity.name == 'merge_accounts':
        [index.add(invalidate['target_user_id'])]
      if activity.name == 'post_comment':
        index.add(invalidate['comment_id'])
      if activity.name in ['share_existing', 'share_new', 'save_photos']:
        for item in invalidate['episodes']:
          index.add(item['episode_id'])
          [index.add(ph_id) for ph_id in item['photo_ids']]
      if activity.name in ['upload_episode']:
        index.add(invalidate['episode_id'])
        [index.add(ph_id) for ph_id in invalidate['photo_ids']]

    # Iterate through each of the viewpoint assets and make sure they're "covered" by an activity.
    missing_follower_ids = [f.user_id for f in followers if f.user_id not in index]

    # Only check viewpoints with content.
    if len(ep_photos_list) > 0 or len(comments) > 0:
      for episode, photos, _, _ in ep_photos_list:
        if episode.episode_id not in index:
          if viewpoint.IsDefault():
            # Default viewpoints have upload_episode and save_photos activities.
            if episode.parent_ep_id is None:
              yield gen.Task(self._ReportCorruption, viewpoint.viewpoint_id,
                             'missing upload_episode activity', episode.episode_id,
                             partial(self._RepairMissingActivities, episode.user_id, viewpoint,
                                     'upload_episode', (episode, photos)))
            else:
              yield gen.Task(self._ReportCorruption, viewpoint.viewpoint_id,
                             'missing save_photos activity', episode.episode_id,
                             partial(self._RepairMissingActivities, episode.user_id, viewpoint,
                                     'save_photos', (episode, photos)))
          elif not has_share_new:
            # First share activity is share_new.
            has_share_new = True
            yield gen.Task(self._ReportCorruption, viewpoint.viewpoint_id,
                           'missing share_new activity', episode.episode_id,
                           partial(self._RepairMissingActivities, episode.user_id, viewpoint,
                                   'share_new', (episode, photos, missing_follower_ids)))
            missing_follower_ids = None
          else:
            yield gen.Task(self._ReportCorruption, viewpoint.viewpoint_id,
                           'missing share_existing activity', episode.episode_id,
                           partial(self._RepairMissingActivities, episode.user_id, viewpoint,
                                   'share_existing', (episode, photos, None)))

      if missing_follower_ids:
        yield gen.Task(self._ReportCorruption, viewpoint.viewpoint_id,
                       'missing add_followers activity', missing_follower_ids,
                       partial(self._RepairMissingActivities, viewpoint.user_id, viewpoint,
                               'add_followers', missing_follower_ids))

      for comment in comments:
        if comment.comment_id not in index:
          yield gen.Task(self._ReportCorruption, viewpoint.viewpoint_id,
                         'missing post_comment activity', comment.comment_id,
                         partial(self._RepairMissingActivities, comment.user_id, viewpoint,
                                 'post_comment', comment.comment_id))

    callback()

  @gen.engine
  def _RepairMissingActivities(self, user_id, viewpoint, name, act_args, callback):
    """Adds a missing activity to the specified viewpoint."""
    timestamp = util.GetCurrentTimestamp()
    unique_id = yield gen.Task(Device.AllocateSystemObjectId, self._client)
    activity_id = Activity.ConstructActivityId(timestamp, Device.SYSTEM, unique_id)

    if name == 'add_followers':
      yield gen.Task(Activity.CreateAddFollowers, self._client, user_id, viewpoint.viewpoint_id,
                     activity_id, timestamp, update_seq=0, follower_ids=act_args)
    elif name == 'upload_episode':
      episode, photos = act_args
      ep_dict = {'episode_id': episode.episode_id}
      ph_dicts = [{'photo_id': photo.photo_id} for photo in photos]
      yield gen.Task(Activity.CreateUploadEpisode, self._client, user_id, viewpoint.viewpoint_id,
                     activity_id, timestamp, update_seq=0, ep_dict=ep_dict, ph_dicts=ph_dicts)
    elif name in ['save_photos']:
      episode, photos = act_args
      ep_dict = {'new_episode_id': episode.episode_id,
                 'photo_ids': [ph.photo_id for ph in photos]}
      yield gen.Task(Activity.CreateSavePhotos, self._client, user_id, viewpoint.viewpoint_id,
                     activity_id, timestamp, update_seq=0, ep_dicts=[ep_dict])
    elif name in ['share_new', 'share_existing']:
      episode, photos, follower_ids = act_args
      ep_dict = {'new_episode_id': episode.episode_id,
                 'photo_ids': [ph.photo_id for ph in photos]}
      if name == 'share_new':
        yield gen.Task(Activity.CreateShareNew, self._client, user_id, viewpoint.viewpoint_id,
                       activity_id, timestamp, update_seq=0, ep_dicts=[ep_dict],
                       follower_ids=follower_ids)
      else:
        yield gen.Task(Activity.CreateShareExisting, self._client, user_id, viewpoint.viewpoint_id,
                       activity_id, timestamp, update_seq=0, ep_dicts=[ep_dict])
    elif name == 'post_comment':
      yield gen.Task(Activity.CreatePostComment, self._client, user_id, viewpoint.viewpoint_id,
                     activity_id, timestamp, update_seq=0, cm_dict={'comment_id': act_args})

    logging.warning('  added activity: %s', (viewpoint.viewpoint_id, name))
    callback()

  @gen.coroutine
  def _CheckMissingPosts(self, viewpoint, activities, ep_photos_list):
    """Check activities for missing posts."""
    # Build a lookup of photos for this viewpoint, grouped by episode, that we know exist.
    existing_posts = defaultdict(set)
    for _, photos, posts, _ in ep_photos_list:
      for post in posts:
        existing_posts[post.episode_id].add(post.photo_id)

    for activity in activities:
      if activity.name in ['share_new', 'share_existing']:
        for ep_dict in json.loads(activity.json)['episodes']:
          if len(ep_dict['photo_ids']) > 0:
            if ep_dict['episode_id'] not in existing_posts:
              yield gen.Task(self._ReportCorruption,
                             viewpoint.viewpoint_id,
                             'no posts found for episode referenced by activity',
                             (ep_dict['episode_id'], activity.activity_id),
                             partial(self._RepairMissingPosts, activities, existing_posts))
              raise gen.Return()
            for photo_id in ep_dict['photo_ids']:
              if photo_id not in existing_posts[ep_dict['episode_id']]:
                yield gen.Task(self._ReportCorruption,
                               viewpoint.viewpoint_id,
                               'missing post referenced by activity',
                               (ep_dict['episode_id'], photo_id, activity.activity_id),
                               partial(self._RepairMissingPosts, activities, existing_posts))
                raise gen.Return()

  @gen.coroutine
  def _RepairMissingPosts(self, activities, existing_posts):
    """Remove references to posts in activities if the posts don't exist."""
    @gen.coroutine
    def _RebuildActivity(activity, act_args):
      rebuilt_episodes = []
      for ep_dict in act_args['episodes']:
        if ep_dict['episode_id'] in existing_posts:
          new_ep_dict = {'episode_id': ep_dict['episode_id']}
          for photo_id in list(ep_dict['photo_ids']):
            if photo_id in existing_posts[ep_dict['episode_id']]:
              new_ep_dict.setdefault('photo_ids', []).append(photo_id)
          rebuilt_episodes.append(new_ep_dict)
        else:
          # Rebuilding the activity is problematic without any posts in an episode.  Creating an activity with an
          #   empty episode will lead to other dbchk errors.  Currently, there are no known cases of this, so we'll
          #   just log it and skip processing of this activity for now.  If we ever hit a
          #   case of this, we can address it then.
          logging.warning('  unable to rebuild activity: %s; missing all posts for episode: %s',
                          activity.activity_id,
                          ep_dict['episode_id'])
          return
      act_args['episodes'] = rebuilt_episodes
      update_activity = Activity.CreateFromKeywords(viewpoint_id=activity.viewpoint_id,
                                                    activity_id=activity.activity_id,
                                                    name=activity.name,
                                                    json=json.dumps(act_args))
      yield gen.Task(update_activity.Update, self._client)
      logging.warning('  updated activity: %s', activity.activity_id)

    def _IsEpisodeMissingAnyPosts(ep_dict):
      for photo_id in ep_dict['photo_ids']:
        if photo_id not in existing_posts[ep_dict['episode_id']]:
          return True
      return False

    for activity in activities:
      if activity.name in ['share_new', 'share_existing']:
        act_args = json.loads(activity.json)
        for ep_dict in act_args['episodes']:
          if ep_dict['episode_id'] not in existing_posts or _IsEpisodeMissingAnyPosts(ep_dict):
            yield _RebuildActivity(activity, act_args)
            # Move on to next activity.
            break

  @gen.engine
  def _CheckInvalidViewpointMetadata(self, viewpoint, activities, callback):
    """Checks correctness of viewpoint metadata:
         1. last_updated must be defined
         2. timestamp must be defined
    """
    if viewpoint.last_updated is None:
      yield gen.Task(self._ReportCorruption, viewpoint.viewpoint_id, 'invalid viewpoint metadata', 'last_updated',
                    partial(self._RepairInvalidViewpointMetadata, viewpoint, activities))

    if viewpoint.timestamp is None:
      yield gen.Task(self._ReportCorruption, viewpoint.viewpoint_id, 'invalid viewpoint metadata', 'timestamp',
                    partial(self._RepairInvalidViewpointMetadata, viewpoint, activities))

    callback()

  @gen.engine
  def _RepairInvalidViewpointMetadata(self, viewpoint, activities, callback):
    """Repairs invalid viewpoint metadata:
         1. sets last_updated if it was not defined
         2. sets timestamp if it was not defined
    """
    timestamp = min(a.timestamp for a in activities) if activities else 0
    if viewpoint.last_updated is None:
      viewpoint.last_updated = timestamp
      yield gen.Task(viewpoint.Update, self._client)
      logging.warning('  set last_updated to %d: %s', viewpoint.last_updated, viewpoint.viewpoint_id)

    if viewpoint.timestamp is None:
      viewpoint.timestamp = timestamp
      yield gen.Task(viewpoint.Update, self._client)
      logging.warning('  set timestamp to %d: %s', viewpoint.timestamp, viewpoint.viewpoint_id)

    callback()

  @gen.coroutine
  def _CheckBadCoverPhoto(self, viewpoint, ep_photos_list, activities):
    """Ensure that the cover photo is valid for this viewpoint."""
    # Qualified means that a post is not removed (which implies that it's not unshared, either).
    has_qualified_posts = False
    if viewpoint.IsCoverPhotoSet():
      cp_episode_id = viewpoint.cover_photo.get('episode_id')
      cp_photo_id = viewpoint.cover_photo.get('photo_id')
      if cp_episode_id is None or cp_photo_id is None:
        # If Viewpoint.cover_photo is not None, these should be present and not None.
        yield gen.Task(self._ReportCorruption,
                       viewpoint.viewpoint_id,
                       'viewpoint cover_photo is not None, but does not have proper keys',
                       viewpoint.cover_photo,
                       partial(self._RepairBadCoverPhoto, viewpoint, ep_photos_list, activities))
        raise gen.Return()
    else:
      cp_episode_id = None
      cp_photo_id = None

    for _, _, posts, _ in ep_photos_list:
      for post in posts:
        if not post.IsRemoved():
          # This post is qualified to be a cover_photo.
          has_qualified_posts = True
          if post.photo_id == cp_photo_id and post.episode_id == cp_episode_id:
            # Found qualified matching post.  Terminate check of this viewpoint.
            raise gen.Return()
        elif post.photo_id == cp_photo_id and post.episode_id == cp_episode_id:
          # Found a match, but of a non-qualifying post.
          yield gen.Task(self._ReportCorruption,
                         viewpoint.viewpoint_id,
                         'viewpoint cover_photo is not qualified to be a cover_photo',
                         post,
                         partial(self._RepairBadCoverPhoto, viewpoint, ep_photos_list, activities))
          raise gen.Return()
    if viewpoint.IsCoverPhotoSet():
      # The cover_photo that is set doesn't refer to any photos within the viewpoint, qualified or not.
      yield gen.Task(self._ReportCorruption,
                     viewpoint.viewpoint_id,
                     'viewpoint cover_photo does not match any photo in viewpoint',
                     viewpoint.cover_photo,
                     partial(self._RepairBadCoverPhoto, viewpoint, ep_photos_list, activities))
    elif has_qualified_posts:
      # No cover photo set, but there are photos available to the cover photo.
      yield gen.Task(self._ReportCorruption,
                     viewpoint.viewpoint_id,
                     'viewpoint cover_photo is set to None and there are qualified photos available',
                     viewpoint,
                     partial(self._RepairBadCoverPhoto, viewpoint, ep_photos_list, activities))

  @gen.coroutine
  def _RepairBadCoverPhoto(self, viewpoint, ep_photos_list, activities):
    """Select a new cover photo for this viewpoint.  Or clear it if none are available."""
    # Build dictionary of shared posts for looking up posts by PostId:
    shared_posts = {Post.ConstructPostId(post.episode_id, post.photo_id) : post
                    for _, _, posts, _ in ep_photos_list
                    for post in posts if not post.IsRemoved()}

    # This assumes that the activities list was generated from a forward scan query so we reverse it here.
    cover_photo = yield gen.Task(viewpoint.SelectCoverPhoto,
                                 self._client,
                                 set(),
                                 activities_list=reversed(activities),
                                 available_posts_dict=shared_posts)
    viewpoint.cover_photo = cover_photo
    yield gen.Task(viewpoint.Update, self._client)
    logging.warning('  updating cover_photo: %s, %s', viewpoint.viewpoint_id, cover_photo)

  @gen.engine
  def _CheckEmptyViewpoint(self, viewpoint, activities, followers, ep_photos_list, comments, callback):
    """Checks for empty viewpoint."""
    if not viewpoint.IsDefault() and not activities and not ep_photos_list and not comments:
      yield gen.Task(self._ReportCorruption, viewpoint.viewpoint_id, 'empty viewpoint', None,
                    partial(self._RepairEmptyViewpoint, viewpoint, followers))

    callback()

  @gen.engine
  def _RepairEmptyViewpoint(self, viewpoint, followers, callback):
    """Deletes a corrupted viewpoint."""
    for follower in followers:
      sort_key = Followed.CreateSortKey(viewpoint.viewpoint_id, viewpoint.last_updated or 0)
      followed = yield gen.Task(Followed.Query, self._client, follower.user_id, sort_key, None, must_exist=False)

      # Delete the followed object if it exists.
      if followed is not None:
        yield gen.Task(followed.Delete, self._client)
        logging.warning('  deleted followed: %s', str((followed.user_id, followed.sort_key)))

      # Delete the follower object if it exists.
      if follower is not None:
        yield gen.Task(follower.Delete, self._client)
        logging.warning('  deleted follower: %s', str((follower.user_id, viewpoint.viewpoint_id)))

    # Delete the viewpoint object.
    yield gen.Task(viewpoint.Delete, self._client)
    logging.warning('  deleted viewpoint: %s', viewpoint.viewpoint_id)

    callback()

  @gen.engine
  def _CheckMissingFollowed(self, viewpoint, followers, callback):
    """Checks for missing followed records."""
    for follower in followers:
      sort_key = Followed.CreateSortKey(viewpoint.viewpoint_id, viewpoint.last_updated or 0)
      followed = yield gen.Task(Followed.Query,
                                self._client,
                                follower.user_id,
                                sort_key,
                                None,
                                must_exist=False)
      if followed is None:
        yield gen.Task(self._ReportCorruption, viewpoint.viewpoint_id, 'missing followed',
                       (follower.user_id, sort_key),
                       partial(self._RepairMissingFollowed, viewpoint, follower, sort_key))

    callback()

  @gen.engine
  def _RepairMissingFollowed(self, viewpoint, follower, sort_key, callback):
    """Adds a Followed object for the specified user and viewpoint."""
    # Add the new Followed object.
    yield gen.Task(Followed.UpdateDateUpdated,
                   self._client,
                   follower.user_id,
                   viewpoint.viewpoint_id,
                   None,
                   viewpoint.last_updated or 0)
    logging.warning('  added followed: %s' % str((follower.user_id, sort_key)))

    # Invalidate the viewpoint so that user's device will reload it.
    yield self._CreateNotification(follower.user_id,
                                   'dbchk add_followed',
                                   NotificationManager._CreateViewpointInvalidation(viewpoint.viewpoint_id))

    callback()

  @gen.engine
  def _CheckBadViewpointAccounting(self, viewpoint, ep_photos_list, accounting_list, callback):
    """Compute all accounting entries from ep_photos_list and verify that they match the entries in 'accounting'."""
    act_dict = {}

    def _IncrementAccountingWith(hash_key, sort_key, increment_from):
      # Do not create entries if stats are zero.
      if increment_from.num_photos == 0:
        return
      key = (hash_key, sort_key)
      act_dict.setdefault(key, Accounting(hash_key, sort_key)).IncrementStatsFrom(increment_from)

    for episode, photos, posts, user_posts in ep_photos_list:
      act = Accounting()
      act.IncrementFromPhotos([photo for photo, post in zip(photos, posts) if not post.IsRemoved()])
      if viewpoint.IsDefault():
        # Default viewpoint: compute viewpoint-level owned-by:<user> and user-level owned-by.
        _IncrementAccountingWith('%s:%s' % (Accounting.VIEWPOINT_SIZE, viewpoint.viewpoint_id),
                                 '%s:%d' % (Accounting.OWNED_BY, episode.user_id),
                                 act)
        _IncrementAccountingWith('%s:%d' % (Accounting.USER_SIZE, viewpoint.user_id),
                                 Accounting.OWNED_BY, act)
      else:
        # Shared viewpoint: compute viewpoint-level shared-by:<user> and visible-to. User-level
        # accounting for those categories sums multiple viewpoint-level entries, so cannot be computed here.
        _IncrementAccountingWith('%s:%s' % (Accounting.VIEWPOINT_SIZE, viewpoint.viewpoint_id),
                                 '%s:%d' % (Accounting.SHARED_BY, episode.user_id),
                                 act)
        _IncrementAccountingWith('%s:%s' % (Accounting.VIEWPOINT_SIZE, viewpoint.viewpoint_id),
                                 Accounting.VISIBLE_TO,
                                 act)

    # Iterate over all existing accounting entries.
    for act in accounting_list:
      key = (act.hash_key, act.sort_key)
      built_act = act_dict.get(key, None)
      if built_act is None:
        # Entries can drop to 0 when photos get removed or unshared. However, we need to keep
        # such entries around to properly handle operation replays.
        built_act = Accounting(hash_key=act.hash_key, sort_key=act.sort_key)

      if not built_act.StatsEqual(act):
        yield gen.Task(self._ReportCorruption, viewpoint.viewpoint_id,
                       'wrong accounting', '%s != %s' % (act, built_act),
                       partial(self._RepairBadViewpointAccounting, 'update', built_act))

      # Remove entry from the built accounting entries.
      act_dict.pop(key, None)

    # Iterate over the remaining built accounting entries.
    for built_act in act_dict.values():
      yield gen.Task(self._ReportCorruption, viewpoint.viewpoint_id, 'missing accounting', built_act,
                     partial(self._RepairBadViewpointAccounting, 'add', built_act))

    callback()

  @gen.engine
  def _RepairBadViewpointAccounting(self, action, accounting, callback):
    if action == 'update':
      # Update wrong accounting entry.
      yield gen.Task(accounting.Update, self._client)
      logging.warning('  updated accounting entry: (%s, %s)', accounting.hash_key, accounting.sort_key)
    elif action == 'add':
      # Add missing accounting entry.
      yield gen.Task(accounting.Update, self._client)
      logging.warning('  added accounting entry: (%s, %s)', accounting.hash_key, accounting.sort_key)

    callback()

  @gen.engine
  def _MaybeCheckVisitedUsers(self, callback):
    """If visited_users has grown too large, trigger CheckVisitedUsers, otherwise, simply return.
    This is called at the end of CheckViewpoint.
    """
    if len(self._visited_users) >= DatabaseChecker._MAX_VISITED_USERS:
      yield gen.Task(self._CheckVisitedUsers)
    callback()

  @gen.engine
  def _CheckVisitedUsers(self, callback):
    """Check each user in the visited_users set and clear it. Called after processing all viewpoint."""
    logging.info('Processing %d visited users' % len(self._visited_users))
    yield [gen.Task(self._CheckUser, user_id, vp_id) for user_id, vp_id in self._visited_users.iteritems()]
    self._visited_users.clear()

    callback()

  @gen.engine
  def _CheckUser(self, user_id, viewpoint_id, callback):
    """Check a single user. viewpoint_id is the visited viewpoint that last encounter this user."""
    logging.info('Processing user %d' % user_id)
    self._current_user = user_id

    # Fetch list of followed viewpoints.
    query_func = partial(Follower.RangeQuery, self._client, user_id, range_desc=None, col_names=None)
    followed_vps = yield gen.Task(self._CacheQuery, query_func)

    accounting_vt = Accounting.CreateUserVisibleTo(user_id)
    accounting_sb = Accounting.CreateUserSharedBy(user_id)

    # Desired sort key in vp accounting. This is used to filter out SHARED_BY other users and OWNED_BY.
    vp_sb_sort_key = '%s:%d' % (Accounting.SHARED_BY, user_id)

    for f in followed_vps:
      # Only consider followers that are not REMOVED.  We don't count the visible_to and shared_by
      #   contributions from the viewpoint of a REMOVED follower.
      if not f.IsRemoved():
        # Fetch list of viewpoint-level accounting entries. This will include OWNED_BY in the default users's
        # default viewpoint as well as SHARED_BY for other users. This is probably better than doing two separate
        # queries for VISIBLE_TO and this user's SHARED_BY.
        query_func = partial(Accounting.RangeQuery,
                             self._client,
                             '%s:%s' % (Accounting.VIEWPOINT_SIZE, f.viewpoint_id),
                             range_desc=None,
                             col_names=None)
        vp_accounting = yield gen.Task(self._CacheQuery, query_func)
        for act in vp_accounting:
          if act.sort_key == vp_sb_sort_key:
            accounting_sb.IncrementStatsFrom(act)
          elif act.sort_key == Accounting.VISIBLE_TO:
            accounting_vt.IncrementStatsFrom(act)

    # Check existence of activities referenced by notifications.
    query_func = partial(Notification.RangeQuery, self._client, user_id, range_desc=None, col_names=None)
    user_notifications = yield gen.Task(self._CacheQuery, query_func)

    for n in user_notifications:
      if not n.viewpoint_id or not n.activity_id:
        continue

      activity = yield gen.Task(Activity.Query, self._client, n.viewpoint_id, n.activity_id, None, must_exist=False)
      if activity is None:
        # TODO: not sure how to auto-repair this.
        yield gen.Task(self._ReportCorruption, n.viewpoint_id,
                       'missing activity', 'user notification %s:%s references missing activity %s:%s' %
                       (user_id, n.notification_id, n.viewpoint_id, n.activity_id),
                       None)

    # Now fetch the user's accounting entries.
    user_sb = yield gen.Task(Accounting.Query, self._client, '%s:%d' % (Accounting.USER_SIZE, user_id),
                             Accounting.SHARED_BY, None, must_exist=False)
    user_vt = yield gen.Task(Accounting.Query, self._client, '%s:%d' % (Accounting.USER_SIZE, user_id),
                             Accounting.VISIBLE_TO, None, must_exist=False)

    # Check users's accounting entries against aggregated viewpoint entries.
    # If the built-up accounting is zero, we do not create missing entries as this both complicates
    # tests and increases the chances of conflict.
    if user_sb is None:
      if accounting_sb.num_photos != 0:
        yield gen.Task(self._ReportCorruption, viewpoint_id, 'missing user accounting', accounting_sb,
                       partial(self._RepairBadViewpointAccounting, 'add', accounting_sb))
    elif not user_sb.StatsEqual(accounting_sb):
      yield gen.Task(self._ReportCorruption, viewpoint_id,
                     'wrong user accounting', '%s != %s' % (user_sb, accounting_sb),
                     partial(self._RepairBadViewpointAccounting, 'update', accounting_sb))

    if user_vt is None:
      if accounting_sb.num_photos != 0:
        yield gen.Task(self._ReportCorruption, viewpoint_id, 'missing user accounting', accounting_vt,
                       partial(self._RepairBadViewpointAccounting, 'add', accounting_vt))
    elif not user_vt.StatsEqual(accounting_vt):
      yield gen.Task(self._ReportCorruption, viewpoint_id,
                     'wrong user accounting', '%s != %s' % (user_vt, accounting_vt),
                     partial(self._RepairBadViewpointAccounting, 'update', accounting_vt))

    self._current_user = ''
    callback()

  @gen.engine
  def _CacheQuery(self, query_func, callback):
    """Repeatedly invokes the specified query function that takes an
    "excl_start_key" and a "limit" argument for paging. The query
    function must return an array of result items, or a tuple of
    (items, last_key). Combines the result items from multiple calls
    into a single array of results, and invokes the callback with it.
    """
    _LIMIT = 100
    excl_start_key = None
    all_results = []
    while True:
      results = yield gen.Task(query_func, limit=_LIMIT, excl_start_key=excl_start_key)

      # Some query funcs return the items directly, some return a tuple of (items, last_key).
      if isinstance(results, tuple):
        results, excl_start_key = results
      elif len(results) > 0:
        excl_start_key = results[-1].GetKey()

      all_results.extend(results)
      if len(results) < _LIMIT:
        break

      if (len(all_results) % 1000) == 0:
        logging.info('  caching %d+ %s records...' % (len(all_results), type(results[0]).__name__.lower()))

    callback(all_results)

  @gen.engine
  def _ReportCorruption(self, viewpoint_id, name, args, repair_func, callback):
    """Logs the corruption and sends occasional emails summarizing any
    corruption that is found.
    """
    args = '' if args is None else ' (%s)' % str(args)
    logging.error('Found database corruption in viewpoint %s: %s%s' % (viewpoint_id, name, args))
    logging.error('  python dbchk.py --devbox --repair=True --viewpoints=%s' % viewpoint_id)

    # Accumulate repairs for later email.
    self._corruptions.setdefault(viewpoint_id, {}).setdefault(name, 0)
    self._corruptions[viewpoint_id][name] += 1

    # If it has been a sufficient interval of time, send notification email.
    if util.GetCurrentTimestamp() > self._last_email + DatabaseChecker._MAX_EMAIL_INTERVAL:
      yield gen.Task(self._SendEmail)

    if self._repair:
      if repair_func is not None:
        logging.warning('Repairing corruption: %s' % name)
        yield gen.Task(repair_func)
        logging.info('')
      else:
        logging.warning('No repair function for corruption: %s' % name)

    callback()

  @gen.engine
  def _SendEmail(self, callback):
    # If no corruption, don't create email.
    if len(self._corruptions) == 0:
      callback()
      return

    email_text = ''
    for i, (viewpoint_id, vp_repair_dict) in enumerate(self._corruptions.iteritems()):
      email_text += '  ---- viewpoint %s ----\n' % viewpoint_id
      for name, count in vp_repair_dict.iteritems():
        email_text += '  %s (%d instance%s)\n' % (name, count, util.Pluralize(count))
      email_text += '\n'

      if i > 50:
        email_text += '  ...too many viewpoints to list\n\n'

    email_text += 'python dbchk.py --devbox --repair=True --viewpoints=%s' % \
                  ','.join(self._corruptions.keys())

    args = {
      'from': 'dbchk@emailscrubbed.com',
      'fromname': 'DB Checker',
      'to': options.options.email,
      'subject': 'Database corruption',
      'text': DatabaseChecker._EMAIL_TEXT % email_text
      }

    # In test mode, save email args but don't send email.
    # Don't send email if problems will be repaired.
    if _TEST_MODE:
      self._email_args = args
    elif options.options.email and not self._repair:
      yield gen.Task(EmailManager.Instance().SendEmail, description=args['subject'], **args)

    self._corruptions = {}
    self._last_email = util.GetCurrentTimestamp()
    callback()

  @gen.coroutine
  def _CreateNotification(self, user_id, name, invalidate):
    """Create notification in order to notify user's devices that
    content needs to be re-loaded.
    """
    # Create dummy operation.
    op_id = Operation.ConstructOperationId(Operation.ANONYMOUS_DEVICE_ID, 0)
    op = Operation(Operation.ANONYMOUS_USER_ID, op_id)
    op.device_id = Operation.ANONYMOUS_DEVICE_ID
    op.timestamp = util.GetCurrentTimestamp()

    yield Notification.CreateForUser(self._client,
                                     op,
                                     user_id,
                                     name,
                                     invalidate=invalidate)

  @gen.engine
  def _ThrottledScan(self, scan_cls, visitor, callback, col_names=None, scan_filter=None,
                     consistent_read=False, max_read_units=None):
    """Scan over the "scan_cls" table, processing at most "max_read_units"
    items per second. Invoke the "visitor" function for each item in the
    table.
    """
    _SCAN_LIMIT = 50

    assert max_read_units is None or max_read_units >= 1.0, max_read_units
    start_key = None
    num_items = 0.0
    start_time = time.time()

    while True:
      items, start_key = yield gen.Task(scan_cls.Scan, self._client, None, limit=_SCAN_LIMIT,
                                        excl_start_key=start_key, scan_filter=scan_filter)

      for item in items:
        # Check to see if max_read_units have been exceeded and therefore a delay is needed.
        if max_read_units is not None:
          now = time.time()
          elapsed_time = now - start_time
          if elapsed_time == 0.0 or (num_items / elapsed_time) > max_read_units:
            # Wait 1 second before proceeding to the next item.
            yield gen.Task(IOLoop.current().add_timeout, now + 1)

        # Make the visit for this item.
        yield gen.Task(visitor, item)

        # Track number of items that have been processed.
        num_items += 1.0
        if (num_items % 10) == 0:
          logging.info('Scanned %d %ss...' % (num_items, scan_cls.__name__.lower()))

      # Stop or continue the scan.
      if start_key is None:
        callback()
        return


def ThrottleUsage():
  """Ensures that only a portion of total read/write capacity is consumed
  by this checker.
  """
  for table in vf_schema.SCHEMA.GetTables():
    table.read_units = max(1, table.read_units // 4)
    table.write_units = max(1, table.write_units // 4)

@gen.engine
def RunOnce(client, job, callback):
  """Perform a single dbchk run based on the options and previous runs.
  We catch all exceptions within the database checker and register the run as a failure.
  We must be called with the job lock held or not require locking.
  """
  assert not options.options.require_lock or job.HasLock() == True
  checker = DatabaseChecker(client, repair=options.options.repair)

  last_scan = None
  if options.options.smart_scan:
    # Search for successful full-scan run in the last week.
    last_run = yield gen.Task(job.FindLastSuccess, with_payload_key='stats.full_scan', with_payload_value=True)

    if last_run is None:
      logging.info('No successful run found in the last week; performing full scan.')
    else:
      # Make sure enough time has passed since the last run.
      last_run_start = last_run['start_time']
      if util.HoursSince(last_run_start) < options.options.hours_between_runs:
        logging.info('Last successful run started at %s, less than %d hours ago; skipping.' %
                     (time.asctime(time.localtime(last_run_start)), options.options.hours_between_runs))
        callback()
        return

      # Set scan_start to start of previous run - 1h (dbchk does not scan viewpoints updated in the last hour).
      last_scan = last_run_start - _CHECK_THRESHOLD_TIMESPAN
      # We intentionally log local times to avoid confusion.
      logging.info('Last successful DBCHK run was at %s, scanning viewpoints updated after %s' %
                   (time.asctime(time.localtime(last_run_start)), time.asctime(time.localtime(last_scan))))

  job.Start()
  try:
    if options.options.viewpoints:
      yield gen.Task(checker.CheckViewpointList, options.options.viewpoints)
    else:
      yield gen.Task(checker.CheckAllViewpoints, last_scan=last_scan)
  except:
    # Failure: log run summary with trace.
    typ, val, tb = sys.exc_info()
    msg = 'Error while visiting viewpoint=%s or user=%s\n' % (checker._current_viewpoint, checker._current_user)
    msg += ''.join(traceback.format_exception(typ, val, tb))
    logging.info('Registering failed run with message: %s' % msg)
    yield gen.Task(job.RegisterRun, Job.STATUS_FAILURE, failure_msg=msg)
  else:
    # Successful: write run summary.
    stats = DotDict()
    stats['full_scan'] = len(options.options.viewpoints) == 0
    stats['dbchk.visited_viewpoints'] = checker._num_visited_viewpoints
    logging.info('Registering successful run with stats: %r' % stats)
    yield gen.Task(job.RegisterRun, Job.STATUS_SUCCESS, stats=stats)

  callback()

@gen.engine
def Dispatch(client, callback):
  """Dispatches according to command-line options."""
  job = Job(client, 'dbchk')

  if options.options.require_lock:
    got_lock = yield gen.Task(job.AcquireLock)
    if got_lock == False:
      logging.warning('Failed to acquire job lock: exiting.')
      callback()
      return

  try:
    yield gen.Task(RunOnce, client, job)
  finally:
    yield gen.Task(job.ReleaseLock)

  callback()

@gen.engine
def SetupAndDispatch(callback):
  """Sets the environment and dispatches according to command-line options."""
  EmailManager.SetInstance(SendGridEmailManager())

  # Try not to disturb production usage while checking and repairing the database.
  ThrottleUsage()

  client = db_client.DBClient.Instance()

  # Dispatch command-line options.
  yield gen.Task(Dispatch, client)
  callback()

if __name__ == '__main__':
  sys.exit(main.InitAndRun(SetupAndDispatch))
