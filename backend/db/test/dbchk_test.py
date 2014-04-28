# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Tests for dbchk tool.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import time

from tornado import options
from viewfinder.backend.base import constants, util
from viewfinder.backend.db.accounting import Accounting
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.followed import Followed
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.job import Job
from viewfinder.backend.db.lock import Lock
from viewfinder.backend.db.lock_resource_type import LockResourceType
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.test.db_validator import DBValidator
from viewfinder.backend.db.tools import dbchk
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager

from base_test import DBBaseTestCase

class DbChkTestCase(DBBaseTestCase):
  def setUp(self):
    super(DbChkTestCase, self).setUp()

    self._start_test_time = util._TEST_TIME
    self._validator = DBValidator(self._client, self.stop, self.wait)

    dbchk._TEST_MODE = True
    self._checker = dbchk.DatabaseChecker(self._client)
    self.maxDiff = 2048

    # Create op_dict, using same dummy operation values as used in dbchk.py.
    self._op_dict = {'op_id': Operation.ConstructOperationId(Operation.ANONYMOUS_DEVICE_ID, 0),
                     'op_timestamp': util._TEST_TIME,
                     'user_id': Operation.ANONYMOUS_USER_ID,
                     'device_id': Operation.ANONYMOUS_DEVICE_ID}

  def tearDown(self):
    # Restore default dbchk options.
    options.options.viewpoints = []
    options.options.repair = False
    options.options.email = 'dbchk@emailscrubbed.com'

    super(DbChkTestCase, self).tearDown()

  def testMultipleCorruptions(self):
    """Verifies detection of multiple corruption issues."""
    # Create 2 empty viewpoints without Followed records.
    self._CreateTestViewpoint('vp1', self._user.user_id, [], delete_followed=True)
    self._CreateTestViewpoint('vp2', self._user.user_id, [], delete_followed=True)

    self._RunAsync(self._checker.CheckAllViewpoints)

    corruption_text = \
    '  ---- viewpoint vp1 ----\n' \
    '  missing followed (1 instance)\n' \
    '  empty viewpoint (1 instance)\n' \
    '\n' \
    '  ---- viewpoint vp2 ----\n' \
    '  missing followed (1 instance)\n' \
    '  empty viewpoint (1 instance)\n' \
    '\n' \
    'python dbchk.py --devbox --repair=True --viewpoints=vp1,vp2'

    self.assertEqual(self._checker._email_args,
                     {'fromname': 'DB Checker',
                      'text': 'Found corruption(s) in database:\n\n%s' % corruption_text,
                      'subject': 'Database corruption',
                      'from': 'dbchk@emailscrubbed.com',
                      'to': 'dbchk@emailscrubbed.com'})

    # Check again, but with last_scan value that should find nothing new.
    self._RunAsync(self._checker.CheckAllViewpoints, last_scan=time.time() + 1)
    self.assertIsNone(self._checker._email_args)

  def testEmail(self):
    """Verifies the --email command line option."""
    self._CreateTestViewpoint('vp1', self._user.user_id, [], delete_followed=True)

    options.options.email = 'kimball.andy@emailscrubbed.com'
    self._RunAsync(self._checker.CheckAllViewpoints)

    corruption_text = \
    '  ---- viewpoint vp1 ----\n' \
    '  missing followed (1 instance)\n' \
    '  empty viewpoint (1 instance)\n' \
    '\n' \
    'python dbchk.py --devbox --repair=True --viewpoints=vp1'

    self.assertEqual(self._checker._email_args,
                     {'fromname': 'DB Checker',
                      'text': 'Found corruption(s) in database:\n\n%s' % corruption_text,
                      'subject': 'Database corruption',
                      'from': 'dbchk@emailscrubbed.com',
                      'to': 'kimball.andy@emailscrubbed.com'})

  def testExclusiveLock(self):
    """Test running dbchk with locking."""
    # Create empty non-default viewpoints (already have empty default viewpoints).
    self._CreateTestViewpoint('vp1', self._user.user_id, [])

    self._RunAsync(self._checker.CheckAllViewpoints)

    corruption_text = \
      '  ---- viewpoint vp1 ----\n' \
      '  empty viewpoint (1 instance)\n' \
      '\n' \
      'python dbchk.py --devbox --repair=True --viewpoints=vp1'

    self.assertEqual(self._checker._email_args['text'],
                     'Found corruption(s) in database:\n\n%s' % corruption_text)

    # Grab lock and run in repair mode. There should still be errors.
    lock = self._RunAsync(Lock.Acquire, self._client, LockResourceType.Job, 'dbchk', 'dbck')
    assert lock is not None

    self._RunDbChk({'viewpoints': ['vp1', self._user.private_vp_id], 'repair': True, 'require_lock': True})
    self.assertEqual(self._checker._email_args['text'],
                     'Found corruption(s) in database:\n\n%s' % corruption_text)

    # Now release the lock and run dbchk in repair mode again.
    self._RunAsync(lock.Release, self._client)
    self._RunDbChk({'viewpoints': ['vp1', self._user.private_vp_id], 'repair': True, 'require_lock': True})

    # Validate by checking again and finding no issues.
    self._RunAsync(self._checker.CheckAllViewpoints)
    self.assertIsNone(self._checker._email_args)

  def testSmartScan(self):
    """Test detection of last scan and smart-scan setting."""
    # Change viewpoint last_updated times to be more ancient.
    vp1 = self._RunAsync(Viewpoint.Query, self._client, self._user.private_vp_id, None)
    vp1.last_updated = time.time() - constants.SECONDS_PER_DAY
    self._RunAsync(vp1.Update, self._client)

    vp2 = self._RunAsync(Viewpoint.Query, self._client, self._user2.private_vp_id, None)
    vp2.last_updated = time.time() - constants.SECONDS_PER_DAY * 2
    self._RunAsync(vp2.Update, self._client)

    # Job to query/write run entries.
    job = Job(self._client, 'dbchk')
    prev_runs = self._RunAsync(job.FindPreviousRuns)
    self.assertEqual(len(prev_runs), 0)

    # Run a partial dbchk.
    self._RunDbChk({'viewpoints': [self._user.private_vp_id]})
    prev_runs = self._RunAsync(job.FindPreviousRuns, status=Job.STATUS_SUCCESS)
    self.assertEqual(len(prev_runs), 1)

    # Wait a second between runs so they end up in different entries.
    time.sleep(1)

    # Run a full dbchk with smart scan: previous run was a partial scan, so we proceed and scan everything.
    self._RunDbChk({'viewpoints': [], 'smart_scan': True})
    prev_runs = self._RunAsync(job.FindPreviousRuns, status=Job.STATUS_SUCCESS)
    self.assertEqual(len(prev_runs), 2)

    # Wait a second between runs so they end up in different entries.
    time.sleep(1)

    # A failed dbchk run does not impact the following run.
    # We trigger a failure by specifying a non-existing viewpoint.
    self._RunDbChk({'viewpoints': ['vp1']})
    prev_runs = self._RunAsync(job.FindPreviousRuns, status=Job.STATUS_SUCCESS)
    self.assertEqual(len(prev_runs), 2)
    prev_runs = self._RunAsync(job.FindPreviousRuns, status=Job.STATUS_FAILURE)
    self.assertEqual(len(prev_runs), 1)

    # Run smart scan again. This time it should not scan anything.
    self._RunDbChk({'viewpoints': [], 'smart_scan': True})
    prev_runs = self._RunAsync(job.FindPreviousRuns, status=Job.STATUS_SUCCESS)
    self.assertEqual(len(prev_runs), 3)

    # Verify per-run stats.
    self.assertEqual(prev_runs[0]['stats.full_scan'], False)
    self.assertEqual(prev_runs[0]['stats.dbchk.visited_viewpoints'], 1)
    self.assertEqual(prev_runs[1]['stats.full_scan'], True)
    self.assertEqual(prev_runs[1]['stats.dbchk.visited_viewpoints'], 2)
    self.assertEqual(prev_runs[2]['stats.full_scan'], True)
    self.assertEqual(prev_runs[2]['stats.dbchk.visited_viewpoints'], 0)


  def testEmptyViewpoints(self):
    """Verifies detection of empty viewpoint records."""
    def _Validate(viewpoint_id):
      self._validator.ValidateDeleteDBObject(Follower, DBKey(self._user.user_id, viewpoint_id))
      self._validator.ValidateDeleteDBObject(Follower, DBKey(self._user2.user_id, viewpoint_id))

      sort_key = Followed.CreateSortKey(viewpoint_id, 0)
      self._validator.ValidateDeleteDBObject(Followed, DBKey(self._user.user_id, sort_key))
      self._validator.ValidateDeleteDBObject(Followed, DBKey(self._user2.user_id, sort_key))

      self._validator.ValidateDeleteDBObject(Viewpoint, viewpoint_id)

    # Create empty non-default viewpoints (already have empty default viewpoints).
    self._CreateTestViewpoint('vp1', self._user.user_id, [])
    self._CreateTestViewpoint('vp2', self._user.user_id, [])

    self._RunAsync(self._checker.CheckAllViewpoints)

    corruption_text = \
      '  ---- viewpoint vp1 ----\n' \
      '  empty viewpoint (1 instance)\n' \
      '\n' \
      '  ---- viewpoint vp2 ----\n' \
      '  empty viewpoint (1 instance)\n' \
      '\n' \
      'python dbchk.py --devbox --repair=True --viewpoints=vp1,vp2'

    self.assertEqual(self._checker._email_args['text'],
                     'Found corruption(s) in database:\n\n%s' % corruption_text)

    self._RunDbChk({'viewpoints': ['vp1', 'vp2', self._user.private_vp_id], 'repair': True})
    _Validate('vp1')
    _Validate('vp2')

  def testInvalidViewpointMetadata(self):
    """Verifies detection of invalid viewpoint metadata."""
    viewpoint = self._CreateTestViewpoint('vp1', self._user.user_id, [])
    self._RunAsync(Activity.CreateShareNew, self._client, self._user.user_id, 'vp1', 'a1',
                   time.time() - 10, 0, [{'new_episode_id': 'ep1', 'photo_ids': []}], [])

    # Bypass checks in DBObject and force last_updated and timestamp to be updated to None.
    viewpoint = Viewpoint.CreateFromKeywords(viewpoint_id='vp1')
    viewpoint._columns['last_updated'].SetModified(True)
    viewpoint._columns['timestamp'].SetModified(True)
    self._RunAsync(viewpoint.Update, self._client)

    self._RunAsync(self._checker.CheckAllViewpoints)

    corruption_text = \
      '  ---- viewpoint vp1 ----\n' \
      '  invalid viewpoint metadata (2 instances)\n' \
      '  missing followed (1 instance)\n' \
      '\n' \
      'python dbchk.py --devbox --repair=True --viewpoints=vp1'

    self.assertEqual(self._checker._email_args['text'],
                     'Found corruption(s) in database:\n\n%s' % corruption_text)

    self._RunDbChk({'viewpoints': ['vp1'], 'repair': True})

    # Validate by checking again and finding no issues.
    self._RunAsync(self._checker.CheckAllViewpoints)
    self.assertIsNone(self._checker._email_args)

  def testMissingFollowed(self):
    """Verifies detection and repair of missing Followed records."""
    def _Validate(follower_id, viewpoint_id, last_updated):
      sort_key = Followed.CreateSortKey(viewpoint_id, last_updated)
      self._validator.ValidateCreateDBObject(Followed,
                                             user_id=follower_id,
                                             sort_key=sort_key,
                                             date_updated=Followed._TruncateToDay(last_updated),
                                             viewpoint_id=viewpoint_id)

      invalidate = NotificationManager._CreateViewpointInvalidation(viewpoint_id)
      self._validator.ValidateNotification('dbchk add_followed',
                                           follower_id,
                                           self._op_dict,
                                           invalidate)

    # Remove Followed record from default viewpoint.
    sort_key = Followed.CreateSortKey(self._user.private_vp_id, util._TEST_TIME)
    followed = self._RunAsync(Followed.Query, self._client, self._user.user_id, sort_key, None)
    self._RunAsync(followed.Delete, self._client)

    # Create non-default viewpoint and change last_updated to "orphan" followed records.
    viewpoint = self._CreateTestViewpoint('vp1', self._user.user_id, [self._user2.user_id])
    viewpoint.last_updated += constants.SECONDS_PER_DAY
    self._RunAsync(viewpoint.Update, self._client)
    self._RunAsync(Activity.CreateAddFollowers, self._client, self._user.user_id, 'vp1', 'a1',
                   time.time(), 0, [self._user2.user_id])

    self._RunAsync(self._checker.CheckAllViewpoints)

    # Default viewpoints created by DBBaseTestCase are missing Followed records.
    corruption_text = \
      '  ---- viewpoint v-F- ----\n' \
      '  missing followed (1 instance)\n' \
      '\n' \
      '  ---- viewpoint vp1 ----\n' \
      '  missing followed (2 instances)\n' \
      '\n' \
      'python dbchk.py --devbox --repair=True --viewpoints=v-F-,vp1'

    self.assertEqual(self._checker._email_args['text'],
                     'Found corruption(s) in database:\n\n%s' % corruption_text)

    self._RunDbChk({'viewpoints': ['vp1', 'v-F-'], 'repair': True})
    _Validate(self._user.user_id, 'vp1', util._TEST_TIME)
    _Validate(self._user.user_id, 'v-F-', util._TEST_TIME)

  def testMultipleShareNew(self):
    """Verifies detection of multiple share_new activities."""
    self._CreateTestViewpoint('vp1', self._user.user_id, [self._user2.user_id])
    self._RunAsync(Activity.CreateShareNew, self._client, self._user.user_id, 'vp1', 'a1',
                   time.time() + 1, 0, [{'new_episode_id': 'ep2', 'photo_ids': []}], [self._user2.user_id])
    self._RunAsync(Activity.CreateShareNew, self._client, self._user.user_id, 'vp1', 'a2',
                   time.time(), 0, [{'new_episode_id': 'ep1', 'photo_ids': []}], [self._user2.user_id])
    self._RunAsync(Activity.CreateShareNew, self._client, self._user.user_id, 'vp1', 'a3',
                   time.time() + 2, 0, [{'new_episode_id': 'ep3', 'photo_ids': []}], [])
    self._RunAsync(Activity.CreateShareNew, self._client, self._user.user_id, 'vp1', 'a4',
                   time.time() + 3, 0, [{'new_episode_id': 'ep4', 'photo_ids': []}], [self._user.user_id])
    self._RunAsync(Activity.CreateShareNew, self._client, self._user2.user_id, 'vp1', 'a5',
                   time.time() - 1, 0, [{'new_episode_id': 'ep5', 'photo_ids': []}], [self._user.user_id])

    self._RunAsync(self._checker.CheckAllViewpoints)

    corruption_text = \
      '  ---- viewpoint vp1 ----\n' \
      '  multiple share_new activities (4 instances)\n' \
      '\n' \
      'python dbchk.py --devbox --repair=True --viewpoints=vp1'

    self.assertEqual(self._checker._email_args['text'],
                     'Found corruption(s) in database:\n\n%s' % corruption_text)

    self._RunDbChk({'viewpoints': ['vp1'], 'repair': True})

    # Validate by checking again and finding no issues.
    self._RunAsync(self._checker.CheckAllViewpoints)
    self.assertIsNone(self._checker._email_args)

  def testMissingActivities(self):
    """Verifies detection of missing activities."""
    self._CreateTestViewpoint('vp1', self._user.user_id, [self._user2.user_id])
    self._CreateTestEpisode('vp1', 'ep1', self._user.user_id)
    self._CreateTestEpisode('vp1', 'ep2', self._user.user_id)
    self._CreateTestEpisode('vp1', 'ep3', self._user.user_id)
    self._CreateTestViewpoint('vp2', self._user.user_id, [self._user2.user_id])
    self._CreateTestEpisode('vp2', 'ep4', self._user.user_id)
    self._CreateTestComment('vp2', 'cm1', self._user.user_id, 'a comment')
    self._RunAsync(Activity.CreateShareNew, self._client, self._user.user_id, 'vp2', 'a1',
                   time.time(), 0, [{'new_episode_id': 'ep4', 'photo_ids': []}], [])
    self._CreateTestEpisode(self._user.private_vp_id, 'ep5', self._user.user_id)

    # Create an episode that would be created by save_photos.
    ep_dict = {'episode_id': 'ep6',
               'user_id': self._user.user_id,
               'viewpoint_id': self._user.private_vp_id,
               'parent_ep_id': 'ep4',
               'publish_timestamp': time.time(),
               'timestamp': time.time()}
    self._RunAsync(Episode.CreateNew, self._client, **ep_dict)

    # Create viewpoint that's missing a follower activity.
    self._CreateTestViewpoint('vp3', self._user.user_id, [])
    follower = Follower.CreateFromKeywords(user_id=self._user2.user_id, viewpoint_id='vp3')
    self._RunAsync(follower.Update, self._client)

    # Create viewpoint with a follower covered by merge_accounts (shouldn't be tagged as missing follower).
    self._CreateTestViewpoint('vp4', self._user.user_id, [self._user2.user_id])
    self._RunAsync(Activity.CreateMergeAccounts, self._client, self._user.user_id, 'vp2', 'a1',
                   time.time(), 0, self._user2.user_id, self._user.user_id)

    self._RunAsync(self._checker.CheckAllViewpoints)

    # Default viewpoints created by DBBaseTestCase are missing Followed records.
    corruption_text = \
      '  ---- viewpoint v-F- ----\n' \
      '  missing save_photos activity (1 instance)\n' \
      '  missing upload_episode activity (1 instance)\n' \
      '\n' \
      '  ---- viewpoint vp4 ----\n' \
      '  empty viewpoint (1 instance)\n' \
      '\n' \
      '  ---- viewpoint vp1 ----\n' \
      '  missing share_existing activity (2 instances)\n' \
      '  missing share_new activity (1 instance)\n' \
      '\n' \
      '  ---- viewpoint vp3 ----\n' \
      '  missing followed (1 instance)\n' \
      '  empty viewpoint (1 instance)\n' \
      '\n' \
      '  ---- viewpoint vp2 ----\n' \
      '  missing post_comment activity (1 instance)\n' \
      '  missing add_followers activity (1 instance)\n' \
      '\n' \
      'python dbchk.py --devbox --repair=True --viewpoints=v-F-,vp4,vp1,vp3,vp2'

    self.assertEqual(self._checker._email_args['text'],
                     'Found corruption(s) in database:\n\n%s' % corruption_text)

    self._RunDbChk({'viewpoints': ['vp1', 'vp2', 'vp3', 'vp4', 'v-F-'], 'repair': True})

    # Validate by checking again and finding no issues.
    self._RunAsync(self._checker.CheckAllViewpoints)
    self.assertIsNone(self._checker._email_args)

  def testMissingSomePosts(self):
    """Verifies detection of activities that refer to some missing posts."""
    # Create activity that has one episode referring to two posts where only one exists.
    self._CreateTestViewpoint('vp1', self._user.user_id, [])
    self._CreateTestEpisode('vp1', 'ep1', self._user.user_id)
    # Skip creation of one of the posts so that a repair is needed.
    self._CreateTestPhotoAndPosts('ep1', self._user.user_id, {'photo_id':'p10'})
    self._RunAsync(Activity.CreateShareNew, self._client, self._user.user_id, 'vp1', 'a1',
                   time.time() + 1, 0, [{'new_episode_id': 'ep1', 'photo_ids': ['p10', 'p11']}], [self._user2.user_id])

    # Now, create something with more complexity where only a few of the activities/episodes need repair.
    # There are 2 problems with this viewpoint:
    # * Activity a2, episode ep2 is missing photo p21
    # * Activity a4, episode ep5 is missing photo p50
    self._CreateTestViewpoint('vp2', self._user.user_id, [])
    self._CreateTestEpisode('vp2', 'ep2', self._user.user_id)
    # Create a post, but skip the other one to cause a corruption.
    self._CreateTestPhotoAndPosts('ep2', self._user.user_id, {'photo_id':'p20'})
    # Create another episode with posts.
    self._CreateTestPhotoAndPosts('ep3', self._user.user_id, {'photo_id':'p30'})
    self._CreateTestPhotoAndPosts('ep3', self._user.user_id, {'photo_id':'p31'})
    self._CreateTestEpisode('vp2', 'ep3', self._user.user_id)
    self._RunAsync(Activity.CreateShareNew,
                   self._client,
                   self._user.user_id,
                   'vp2',
                   'a2',
                   time.time() + 2,
                   0,
                   [{'new_episode_id': 'ep2', 'photo_ids': ['p20', 'p21']},
                    {'new_episode_id': 'ep3', 'photo_ids': ['p30', 'p31']}],
                   [self._user2.user_id])
    self._CreateTestPhotoAndPosts('ep4', self._user.user_id, {'photo_id':'p40'})
    self._CreateTestPhotoAndPosts('ep4', self._user.user_id, {'photo_id':'p41'})
    self._CreateTestEpisode('vp2', 'ep4', self._user.user_id)
    self._RunAsync(Activity.CreateShareExisting,
                   self._client,
                   self._user.user_id,
                   'vp2',
                   'a3',
                   time.time() + 3,
                   0,
                   [{'new_episode_id': 'ep4', 'photo_ids': ['p40', 'p41']}])
    # Skip creation of one of the posts to require a repair.
    self._CreateTestPhotoAndPosts('ep5', self._user.user_id, {'photo_id':'p51'})
    self._CreateTestEpisode('vp2', 'ep5', self._user.user_id)
    self._RunAsync(Activity.CreateShareExisting,
                   self._client,
                   self._user.user_id,
                   'vp2',
                   'a4',
                   time.time() + 4,
                   0,
                   [{'new_episode_id': 'ep5', 'photo_ids': ['p50', 'p51']}])

    self._RunAsync(self._checker.CheckAllViewpoints)

    # Viewpoint is missing post in an activity.
    corruption_text = \
      '  ---- viewpoint vp1 ----\n' \
      '  missing accounting (2 instances)\n' \
      '  missing post referenced by activity (1 instance)\n' \
      '  viewpoint cover_photo is set to None and there are qualified photos available (1 instance)\n' \
      '\n' \
      '  ---- viewpoint vp2 ----\n' \
      '  missing accounting (2 instances)\n' \
      '  missing post referenced by activity (1 instance)\n' \
      '  viewpoint cover_photo is set to None and there are qualified photos available (1 instance)\n' \
      '\n' \
      'python dbchk.py --devbox --repair=True --viewpoints=vp1,vp2'

    self.assertEqual(self._checker._email_args['text'],
                     'Found corruption(s) in database:\n\n%s' % corruption_text)

    self._RunDbChk({'viewpoints': ['vp1', 'vp2'], 'repair': True})

    # Validate by checking again and finding no issues.
    self._RunAsync(self._checker.CheckAllViewpoints)
    self.assertIsNone(self._checker._email_args)

  def testMissingAllPostsFromEpisode(self):
    """Verifies detection of activities that refer to all missing posts from an episode."""
    # Create activity that has one episode referring to two posts, neither of which exist.
    self._CreateTestViewpoint('vp1', self._user.user_id, [])
    self._CreateTestEpisode('vp1', 'ep1', self._user.user_id)
    # Don't create any posts for this.
    self._RunAsync(Activity.CreateShareNew, self._client, self._user.user_id, 'vp1', 'a1',
                   time.time() + 1, 0, [{'new_episode_id': 'ep1', 'photo_ids': ['p10', 'p11']}], [self._user2.user_id])

    self._RunAsync(self._checker.CheckAllViewpoints)

    # Viewpoint is missing posts in an activity.
    corruption_text = \
      '  ---- viewpoint vp1 ----\n' \
      '  no posts found for episode referenced by activity (1 instance)\n' \
      '\n' \
      'python dbchk.py --devbox --repair=True --viewpoints=vp1'

    self.assertEqual(self._checker._email_args['text'],
                     'Found corruption(s) in database:\n\n%s' % corruption_text)

    self._RunDbChk({'viewpoints': ['vp1'], 'repair': True})

    # Validate by checking again and finding no issues.
    self._RunAsync(self._checker.CheckAllViewpoints)
    # Is *not* None because we don't fix this particular case, right now.
    self.assertIsNotNone(self._checker._email_args)

  def testBadViewpointAccounting(self):
    """Verifies detection and repair of bad accounting entries at the viewpoint level.
    We also test user-level OWNED_BY since it's a 1-1 mapping with default viewpoint:OWNED_BY.
    """
    # Accounting entries to write.
    accounting = {}

    # Photos created. Some may be labeled as removed or unshared.
    # Some photos may be missing some or all size fields.
    ph_dicts = [ {'photo_id':'p0', 'tn_size':1, 'med_size':10, 'full_size':100, 'orig_size':1000},
                 {'photo_id':'p1', 'tn_size':2, 'med_size':20, 'full_size':200, 'orig_size':2000},
                 {'photo_id':'p2', 'tn_size':4, 'med_size':40, 'full_size':400, 'orig_size':4000},
                 {'photo_id':'p3', 'tn_size':8, 'med_size':80, 'full_size':800, 'orig_size':8000},
                 {'photo_id':'p4', 'tn_size':16, 'med_size':160, 'full_size':1600, 'orig_size':16000},
                 {'photo_id':'p5', 'tn_size':32, 'orig_size':32000} ]

    # Add unshared and removed photos to the default viewpoint. Unshared
    # photos are still counted towards accounting.
    # Accounting is correct for this viewpoint.
    act_ob = Accounting.CreateViewpointOwnedBy(self._user.private_vp_id, self._user.user_id)
    self._CreateTestEpisode(self._user.private_vp_id, 'ep1', self._user.user_id)
    self._CreateTestPhotoAndPosts('ep1', self._user.user_id, ph_dicts[0], unshared=True)
    self._CreateTestPhotoAndPosts('ep1', self._user.user_id, ph_dicts[1], removed=True)
    self._CreateTestAccounting(act_ob)

    user_ob = Accounting.CreateUserOwnedBy(self._user.user_id)
    user_ob.CopyStatsFrom(act_ob)
    self._CreateTestAccounting(user_ob)

    # Add unshared and removed photos to the default viewpoint for user 2.
    # Wrong viewpoint-level accounting, and missing user-level accounting.
    act_ob = Accounting.CreateViewpointOwnedBy(self._user2.private_vp_id, self._user2.user_id)
    self._CreateTestEpisode(self._user2.private_vp_id, 'ep2.1', self._user2.user_id)
    self._CreateTestPhotoAndPosts('ep2.1', self._user2.user_id, ph_dicts[0], unshared=True)
    self._CreateTestPhotoAndPosts('ep2.1', self._user2.user_id, ph_dicts[1], removed=True)
    self._CreateTestPhotoAndPosts('ep2.1', self._user2.user_id, ph_dicts[2])
    act_ob.IncrementFromPhotoDicts([ph_dicts[1]])
    self._CreateTestAccounting(act_ob)

    self._CreateTestViewpoint('vp1', self._user.user_id, [self._user2.user_id])
    # No photos in episode. No entries will be created for user2.
    self._CreateTestEpisode('vp1', 'ep2', self._user2.user_id)

    # Some photos, including unshared.
    act_sb = Accounting.CreateViewpointSharedBy('vp1', self._user.user_id)
    act_vt = Accounting.CreateViewpointVisibleTo('vp1')
    act_user_sb = Accounting.CreateUserSharedBy(self._user.user_id)
    act_user_vt = Accounting.CreateUserVisibleTo(self._user.user_id)
    self._CreateTestEpisode('vp1', 'ep3', self._user.user_id)
    self._CreateTestPhotoAndPosts('ep3', self._user.user_id, ph_dicts[0])
    self._CreateTestPhotoAndPosts('ep3', self._user.user_id, ph_dicts[1])
    self._CreateTestPhotoAndPosts('ep3', self._user.user_id, ph_dicts[2], unshared=True)
    self._CreateTestPhotoAndPosts('ep3', self._user.user_id, ph_dicts[3], unshared=True)
    self._CreateTestPhotoAndPosts('ep3', self._user.user_id, ph_dicts[4])
    self._CreateTestPhotoAndPosts('ep3', self._user.user_id, ph_dicts[5])
    self._SetCoverPhotoOnViewpoint('vp1', 'ep3', ph_dicts[0]['photo_id'])

    act_sb.IncrementFromPhotoDicts(ph_dicts)
    act_sb.DecrementFromPhotoDicts([ph_dicts[2], ph_dicts[3]])
    self._CreateTestAccounting(act_sb)
    act_user_sb.CopyStatsFrom(act_sb)
    self._CreateTestAccounting(act_user_sb)

    act_vt.IncrementFromPhotoDicts(ph_dicts)
    act_vt.DecrementFromPhotoDicts([ph_dicts[2], ph_dicts[3]])
    self._CreateTestAccounting(act_vt)
    act_user_vt.CopyStatsFrom(act_vt)
    self._CreateTestAccounting(act_user_vt)

    # No accounting entry in table for either viewpoint or user.
    # User-level accounting depends on correct (or fixed) viewpoint-level accounting,
    # so the missing user entries for vp2 will not show up.
    self._CreateTestViewpoint('vp2', self._user.user_id, [self._user2.user_id])
    self._CreateTestEpisode('vp2', 'ep4', self._user.user_id)
    self._CreateTestPhotoAndPosts('ep4', self._user.user_id, ph_dicts[0])
    self._CreateTestPhotoAndPosts('ep4', self._user.user_id, ph_dicts[1])
    self._SetCoverPhotoOnViewpoint('vp2', 'ep4', ph_dicts[0]['photo_id'])

    self._RunAsync(self._checker.CheckAllViewpoints)

    # Default viewpoints created by DBBaseTestCase are missing Followed records.
    corruption_text = \
      '  ---- viewpoint v-F- ----\n' \
      '  missing upload_episode activity (1 instance)\n' \
      '\n' \
      '  ---- viewpoint v-V- ----\n' \
      '  missing accounting (1 instance)\n' \
      '  wrong accounting (1 instance)\n' \
      '  missing upload_episode activity (1 instance)\n' \
      '\n' \
      '  ---- viewpoint vp1 ----\n' \
      '  missing share_existing activity (1 instance)\n' \
      '  missing share_new activity (1 instance)\n' \
      '\n' \
      '  ---- viewpoint vp2 ----\n' \
      '  missing accounting (2 instances)\n' \
      '  missing share_new activity (1 instance)\n' \
      '\n' \
      'python dbchk.py --devbox --repair=True --viewpoints=v-F-,v-V-,vp1,vp2'

    print self._checker._email_args['text']
    self.assertEqual(self._checker._email_args['text'],
                     'Found corruption(s) in database:\n\n%s' % corruption_text)

    self._RunDbChk({'viewpoints': ['v-F-', 'v-V-', 'vp1', 'vp2' ], 'repair': True})

    # Validate by checking again and finding no issues.
    self._RunAsync(self._checker.CheckAllViewpoints)
    self.assertIsNone(self._checker._email_args)

  def testBadUserAccounting(self):
    """Verifies detection and repair of bad accounting entries at the user level."""

    # Photos created. Some may be labeled as removed or unshared.
    # Some photos may be missing some or all size fields.
    ph_dicts = [ {'photo_id':'p0', 'tn_size':1, 'med_size':10, 'full_size':100, 'orig_size':1000},
                 {'photo_id':'p1', 'tn_size':2, 'med_size':20, 'full_size':200, 'orig_size':2000} ]

    # Accurate viewpoint-level accounting (simulates the previous case + fixes), but
    # missing user-level entries.
    # User-level accounting depends on correct (or fixed) viewpoint-level accounting,
    self._CreateTestViewpoint('vp1', self._user.user_id, [self._user2.user_id])
    self._CreateTestEpisode('vp1', 'ep1', self._user.user_id)
    self._CreateTestPhotoAndPosts('ep1', self._user.user_id, ph_dicts[0])
    self._CreateTestPhotoAndPosts('ep1', self._user.user_id, ph_dicts[1])
    self._SetCoverPhotoOnViewpoint('vp1', 'ep1', ph_dicts[0]['photo_id'])
    act_sb = Accounting.CreateViewpointSharedBy('vp1', self._user.user_id)
    act_vt = Accounting.CreateViewpointVisibleTo('vp1')
    act_sb.IncrementFromPhotoDicts(ph_dicts[0:2])
    act_vt.IncrementFromPhotoDicts(ph_dicts[0:2])
    self._CreateTestAccounting(act_sb)
    self._CreateTestAccounting(act_vt)
    # Count only one photo for VISIBLE_2:user2
    act_user_vt = Accounting.CreateUserVisibleTo(self._user2.user_id)
    act_user_vt.IncrementFromPhotoDicts(ph_dicts[0:1])
    self._CreateTestAccounting(act_user_vt)

    # We will detect the following user-level accounting problems:
    # - missing SHARED_BY for self._user
    # - missing VISIBLE_TO for both self._user
    # - wrong VISIBLE_TO for both self._user2

    self._RunAsync(self._checker.CheckAllViewpoints)

    # Default viewpoints created by DBBaseTestCase are missing Followed records.
    corruption_text = \
      '  ---- viewpoint vp1 ----\n' \
      '  wrong user accounting (1 instance)\n' \
      '  missing share_new activity (1 instance)\n' \
      '  missing user accounting (2 instances)\n' \
      '\n' \
      'python dbchk.py --devbox --repair=True --viewpoints=vp1'

    self.assertEqual(self._checker._email_args['text'],
                     'Found corruption(s) in database:\n\n%s' % corruption_text)

    self._RunDbChk({'viewpoints': ['vp1' ], 'repair': True})

    # Validate by checking again and finding no issues.
    self._RunAsync(self._checker.CheckAllViewpoints)
    self.assertIsNone(self._checker._email_args)

  def testBadRemovedUserAccounting(self):
    """Verifies detection and repair of bad accounting entries at the user level for a REMOVED follower."""

    # Photos created. Some may be labeled as removed or unshared.
    # Some photos may be missing some or all size fields.
    ph_dicts = [ {'photo_id':'p0', 'tn_size':1, 'med_size':10, 'full_size':100, 'orig_size':1000},
                 {'photo_id':'p1', 'tn_size':2, 'med_size':20, 'full_size':200, 'orig_size':2000} ]

    # Create accurate user and viewpoint level accounting as if no followers are removed.
    self._CreateTestViewpoint('vp1', self._user.user_id, [])
    self._RunAsync(Activity.CreateShareNew, self._client, self._user.user_id, 'vp1', 'a1',
                   time.time(), 0, [{'new_episode_id': 'ep1', 'photo_ids': []}], [])
    self._CreateTestEpisode('vp1', 'ep1', self._user.user_id)
    self._CreateTestPhotoAndPosts('ep1', self._user.user_id, ph_dicts[0])
    self._CreateTestPhotoAndPosts('ep1', self._user.user_id, ph_dicts[1])
    self._SetCoverPhotoOnViewpoint('vp1', 'ep1', ph_dicts[0]['photo_id'])
    # Create correct viewpoint level accounting.
    act_sb = Accounting.CreateViewpointSharedBy('vp1', self._user.user_id)
    act_vt = Accounting.CreateViewpointVisibleTo('vp1')
    act_sb.IncrementFromPhotoDicts(ph_dicts[0:2])
    act_vt.IncrementFromPhotoDicts(ph_dicts[0:2])
    self._CreateTestAccounting(act_sb)
    self._CreateTestAccounting(act_vt)
    # Create correct user level accounting for self._user.
    act_user_vt = Accounting.CreateUserVisibleTo(self._user.user_id)
    act_user_vt.IncrementFromPhotoDicts(ph_dicts[0:2])
    self._CreateTestAccounting(act_user_vt)
    act_user_sb = Accounting.CreateUserSharedBy(self._user.user_id)
    act_user_sb.IncrementFromPhotoDicts(ph_dicts[0:2])
    self._CreateTestAccounting(act_user_sb)

    # Set the REMOVED label on the follower to see that we correctly identify the incorrect accounting.
    follower = self._RunAsync(Follower.Query, self._client, self._user.user_id, 'vp1', None)
    follower.labels.add(Follower.REMOVED)
    self._RunAsync(follower.Update, self._client)

    # We will detect the following user-level accounting problems:
    # - wrong VISIBLE_TO and SHARED_BY for self._user

    self._RunAsync(self._checker.CheckAllViewpoints)

    # User accounting is wrong for both visible_to and shared_by records.
    corruption_text = \
    '  ---- viewpoint vp1 ----\n'\
    '  wrong user accounting (2 instances)\n'\
    '\n'\
    'python dbchk.py --devbox --repair=True --viewpoints=vp1'

    self.assertEqual(self._checker._email_args['text'],
                     'Found corruption(s) in database:\n\n%s' % corruption_text)

    self._RunDbChk({'viewpoints': ['vp1' ], 'repair': True})

    # Validate by checking again and finding no issues.
    self._RunAsync(self._checker.CheckAllViewpoints)
    self.assertIsNone(self._checker._email_args)

  def testBadCoverPhoto(self):
    """Test various corruption code paths for bad cover_photos."""

    # Photos created. Some may be labeled as removed or unshared.
    ph_dicts = [ {'photo_id':'p0'},
                 {'photo_id':'p1'},
                 {'photo_id':'p2'}]

    # Should be OK to not have a cover photo set on a default viewpoint.
    self._CreateTestEpisode(self._user.private_vp_id, 'ep1', self._user.user_id)
    self._CreateTestPhotoAndPosts('ep1', self._user.user_id, ph_dicts[0], unshared=True)
    self._CreateTestPhotoAndPosts('ep1', self._user.user_id, ph_dicts[1], removed=True)

    # Some photos, including unshared/removed. Cover_photo already correctly set.
    self._CreateTestViewpoint('vp2', self._user.user_id, [])
    self._CreateTestEpisode('vp2', 'ep2', self._user.user_id)
    self._CreateTestPhotoAndPosts('ep2', self._user.user_id, ph_dicts[0])
    self._CreateTestPhotoAndPosts('ep2', self._user.user_id, ph_dicts[1], unshared=True)
    self._CreateTestPhotoAndPosts('ep2', self._user.user_id, ph_dicts[2], removed=True)
    self._SetCoverPhotoOnViewpoint('vp2', 'ep2', ph_dicts[0]['photo_id'])

    # Corruption: Some photos, but didn't set a cover_photo.
    self._CreateTestViewpoint('vp3', self._user.user_id, [])
    self._CreateTestEpisode('vp3', 'ep3', self._user.user_id)
    self._CreateTestPhotoAndPosts('ep3', self._user.user_id, ph_dicts[0])
    self._CreateTestPhotoAndPosts('ep3', self._user.user_id, ph_dicts[1])
    self._RunAsync(Activity.CreateShareNew, self._client, self._user.user_id, 'vp3', 'a3',
                   time.time() + 1, 0, [{'new_episode_id': 'ep3',
                                         'photo_ids': ['p0', 'p1']}], [])

    # Some photos, but all are removed/unshared.  Cover_photo not set. Should be OK.
    self._CreateTestViewpoint('vp4', self._user.user_id, [])
    self._CreateTestEpisode('vp4', 'ep4', self._user.user_id)
    self._CreateTestPhotoAndPosts('ep4', self._user.user_id, ph_dicts[0], unshared=True)
    self._CreateTestPhotoAndPosts('ep4', self._user.user_id, ph_dicts[1], removed=True)
    self._RunAsync(Activity.CreateShareNew, self._client, self._user.user_id, 'vp4', 'a4',
                   time.time(), 0, [{'new_episode_id': 'ep4',
                                         'photo_ids': ['p0', 'p1']}], [])

    # Corruption: Some photos, but all are removed/unshared.  Cover_photo set to one of them.
    self._CreateTestViewpoint('vp5', self._user.user_id, [])
    self._CreateTestEpisode('vp5', 'ep5', self._user.user_id)
    self._CreateTestPhotoAndPosts('ep5', self._user.user_id, ph_dicts[0], unshared=True)
    self._CreateTestPhotoAndPosts('ep5', self._user.user_id, ph_dicts[1], removed=True)
    self._SetCoverPhotoOnViewpoint('vp5', 'ep5', ph_dicts[1]['photo_id'])
    self._RunAsync(Activity.CreateShareNew, self._client, self._user.user_id, 'vp5', 'a5',
                   time.time() - 1, 0, [{'new_episode_id': 'ep5',
                                         'photo_ids': ['p0', 'p1']}], [])

    # Corruption: Cover_photo property in bad state.  Cover_photo is not None, but missing key.
    self._CreateTestViewpoint('vp6', self._user.user_id, [])
    self._CreateTestEpisode('vp6', 'ep6', self._user.user_id)
    self._CreateTestPhotoAndPosts('ep6', self._user.user_id, ph_dicts[0])
    self._CreateTestPhotoAndPosts('ep6', self._user.user_id, ph_dicts[1])
    viewpoint = self._RunAsync(Viewpoint.Query, self._client, 'vp6', None)
    viewpoint.cover_photo = {'episode_id': 'ep6'}  # intentionally omit photo_id.
    self._RunAsync(viewpoint.Update, self._client)
    self._RunAsync(Activity.CreateShareNew, self._client, self._user.user_id, 'vp6', 'a6',
                   time.time() - 2, 0, [{'new_episode_id': 'ep6',
                                         'photo_ids': ['p0', 'p1']}], [])

    # Corruption: Cover_photo referenced photo not in viewpoint.
    self._CreateTestViewpoint('vp7', self._user.user_id, [])
    self._CreateTestEpisode('vp7', 'ep7', self._user.user_id)
    self._CreateTestPhotoAndPosts('ep7', self._user.user_id, ph_dicts[0])
    self._CreateTestPhotoAndPosts('ep7', self._user.user_id, ph_dicts[1])
    self._SetCoverPhotoOnViewpoint('vp7', 'ep7', 'p99')
    self._RunAsync(Activity.CreateShareNew, self._client, self._user.user_id, 'vp7', 'a7',
                   time.time() - 2, 0, [{'new_episode_id': 'ep7',
                                         'photo_ids': ['p0', 'p1']}], [])

    self._RunAsync(self._checker.CheckAllViewpoints)

    # Default viewpoints created by DBBaseTestCase are missing Followed records.
    corruption_text = \
      '  ---- viewpoint vp5 ----\n' \
      '  viewpoint cover_photo is not qualified to be a cover_photo (1 instance)\n' \
      '\n' \
      '  ---- viewpoint vp7 ----\n' \
      '  missing accounting (2 instances)\n' \
      '  viewpoint cover_photo does not match any photo in viewpoint (1 instance)\n' \
      '\n' \
      '  ---- viewpoint vp6 ----\n' \
      '  missing accounting (2 instances)\n' \
      '  viewpoint cover_photo is not None, but does not have proper keys (1 instance)\n' \
      '\n' \
      '  ---- viewpoint vp3 ----\n' \
      '  missing accounting (2 instances)\n' \
      '  viewpoint cover_photo is set to None and there are qualified photos available (1 instance)\n' \
      '\n' \
      '  ---- viewpoint vp2 ----\n' \
      '  missing accounting (2 instances)\n' \
      '  missing share_new activity (1 instance)\n' \
      '\n' \
      '  ---- viewpoint v-F- ----\n' \
      '  missing upload_episode activity (1 instance)\n' \
      '\n' \
      'python dbchk.py --devbox --repair=True --viewpoints=vp5,vp7,vp6,vp3,vp2,v-F-'

    print self._checker._email_args['text']
    self.assertEqual(self._checker._email_args['text'],
                     'Found corruption(s) in database:\n\n%s' % corruption_text)

    self._RunDbChk({'viewpoints': ['v-F-', 'vp2', 'vp3', 'vp4', 'vp5', 'vp6', 'vp7'], 'repair': True})

    # Validate by checking again and finding no issues.
    self._RunAsync(self._checker.CheckAllViewpoints)
    self.assertIsNone(self._checker._email_args)

  def _CreateTestViewpoint(self, viewpoint_id, user_id, follower_ids, delete_followed=False):
    """Create viewpoint_id for testing purposes."""
    vp_dict = {'viewpoint_id': viewpoint_id,
               'user_id': user_id,
               'timestamp': util._TEST_TIME,
               'last_updated': util._TEST_TIME,
               'type': Viewpoint.EVENT}
    viewpoint, _ = self._RunAsync(Viewpoint.CreateNewWithFollowers, self._client, follower_ids, **vp_dict)

    if delete_followed:
      for f_id in [user_id] + follower_ids:
        sort_key = Followed.CreateSortKey(viewpoint_id, util._TEST_TIME)
        followed = self._RunAsync(Followed.Query, self._client, f_id, sort_key, None)
        self._RunAsync(followed.Delete, self._client)

    return viewpoint

  def _CreateTestEpisode(self, viewpoint_id, episode_id, user_id):
    """Create episode for testing purposes."""
    ep_dict = {'episode_id': episode_id,
               'user_id': user_id,
               'viewpoint_id': viewpoint_id,
               'publish_timestamp': time.time(),
               'timestamp': time.time()}
    return self._RunAsync(Episode.CreateNew, self._client, **ep_dict)

  def _CreateTestComment(self, viewpoint_id, comment_id, user_id, message):
    """Create comment for testing purposes."""
    comment = Comment.CreateFromKeywords(viewpoint_id=viewpoint_id, comment_id=comment_id,
                                         user_id=user_id, message=message)
    self._RunAsync(comment.Update, self._client)
    return comment

  def _CreateTestPhotoAndPosts(self, episode_id, user_id, ph_dict, unshared=False, removed=False):
    """Create photo/post/user_post for testing purposes."""
    self._CreateTestPhoto(ph_dict)
    self._CreateTestPost(episode_id, ph_dict['photo_id'], unshared=unshared, removed=removed)

  def _CreateTestPost(self, episode_id, photo_id, unshared=False, removed=False):
    """Create post for testing purposes."""
    post = Post.CreateFromKeywords(episode_id=episode_id, photo_id=photo_id)
    if unshared:
      post.labels.add(Post.UNSHARED)
    if unshared or removed:
      post.labels.add(Post.REMOVED)
    self._RunAsync(post.Update, self._client)

  def _CreateTestPhoto(self, ph_dict):
    """Create photo for testing purposes."""
    photo = Photo.CreateFromKeywords(**ph_dict)
    self._RunAsync(photo.Update, self._client)

  def _CreateTestAccounting(self, act):
    """Create accounting entry for testing purposes."""
    self._RunAsync(act.Update, self._client)

  def _SetCoverPhotoOnViewpoint(self, viewpoint_id, episode_id, photo_id):
    """Updates a viewpoint with the given selected cover_photo."""
    viewpoint = self._RunAsync(Viewpoint.Query, self._client, viewpoint_id, None)
    viewpoint.cover_photo = Viewpoint.ConstructCoverPhoto(episode_id, photo_id)
    self._RunAsync(viewpoint.Update, self._client)

  def _RunDbChk(self, option_dict=None):
    """Call dbchk.Dispatch after setting the specified options."""
    if option_dict:
      [setattr(options.options, name, value) for name, value in option_dict.iteritems()]

    self._RunAsync(dbchk.Dispatch, self._client)
