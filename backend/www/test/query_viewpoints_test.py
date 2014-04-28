# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Uploads a number of viewpoints and episodes and tests query of
viewpoints by viewpoint id, with limits and start keys.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import random
import time

from copy import copy
from functools import partial
from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.www import json_schema
from viewfinder.backend.www.service import _AddPhotoUrls
from viewfinder.backend.www.test import service_base_test


class QueryViewpointsTestCase(service_base_test.ServiceBaseTestCase):
  def testQueryViewpoints(self):
    """Tests various viewpoint queries."""
    cookie = self._cookies[0]
    self._CreateQueryAssets()
    self._all_viewpoints = self._validator.QueryModelObjects(Viewpoint)

    # Get all viewpoints created by user #1.
    vp_count = len(self._all_viewpoints)

    # Query empty viewpoint list.
    self._QueryViewpoints(cookie, self._CreateViewpointSelection([]))

    # Query single viewpoint, no start or end, no limit.
    self._QueryViewpoints(cookie, self._CreateViewpointSelection([2]))

    # Query all viewpoints, no start or end, no limit.
    self._QueryViewpoints(cookie, self._CreateViewpointSelection(range(vp_count)))

    # Query every other viewpoint, no start or end, no limit.
    self._QueryViewpoints(cookie, self._CreateViewpointSelection(range(0, vp_count, 2)))

    # Query all viewpoints, limit of 1.
    self._QueryViewpoints(cookie, self._CreateViewpointSelection(range(vp_count), limit=1),
                          fetch_all=True)

    # Query all viewpoints, limit of 2.
    self._QueryViewpoints(cookie, self._CreateViewpointSelection(range(vp_count), limit=2),
                          fetch_all=True)

    # Query all viewpoints, limit of 3.
    self._QueryViewpoints(cookie, self._CreateViewpointSelection(range(vp_count), limit=3),
                          fetch_all=True)

    # Omit all metadata and collections.
    selection = self._CreateViewpointSelection(range(vp_count), get_attributes=None, get_followers=None,
                                               get_activities=None, get_episodes=None)
    self._QueryViewpoints(cookie, selection, fetch_all=True)

    # Explicitly remove all metadata and collections.
    selection = self._CreateViewpointSelection(range(vp_count), get_attributes=False, get_followers=False,
                                               get_activities=False, get_episodes=False, get_comments=False)
    self._QueryViewpoints(cookie, selection, fetch_all=True)

    # Test start keys with limits.
    selection = self._CreateViewpointSelection(range(vp_count), get_attributes=False,
                                               get_followers=True, follower_start_key='0',
                                               get_activities=True, activity_start_key='-',
                                               get_episodes=True, episode_start_key='-',
                                               get_comments=True, comment_start_key='-')
    self._QueryViewpoints(cookie, selection, limit=2, fetch_all=True)

    # Test start keys used without collections projected.
    selection = self._CreateViewpointSelection(range(vp_count), get_attributes=True,
                                               get_followers=False, follower_start_key='0',
                                               get_activities=False, activity_start_key='-',
                                               get_episodes=False, episode_start_key='-',
                                               get_comments=False, comment_start_key='-')
    self._QueryViewpoints(cookie, selection, fetch_all=True)

    # Query for non-existent viewpoint.
    self._QueryViewpoints(cookie, [{'viewpoint_id': 'v-unknown'}])

  def testEpisodeAccess(self):
    """Shares a subset of episodes with another user and ensures that
    only that subset can be retrieved. The service_tester is already
    doing this, but correct access control is so important that it
    justifies redundant testing.
    """
    # Upload some episodes and share 1/2 of them with user #2.
    ep_ph_ids_list = self._UploadMultipleEpisodes(self._cookie, num_photos=37)
    vp_id, ep_ids = self._tester.ShareNew(self._cookie, ep_ph_ids_list[::2],
                                          [self._user2.user_id])

    # Verify that user #2 cannot see the original viewpoint.
    selection = self._tester.CreateViewpointSelection(self._user.private_vp_id)
    response_dict = self._QueryViewpoints(self._cookie2, [selection])
    self.assertTrue(len(response_dict['viewpoints']) == 0)

    # Verify that user #2 can only see 1/2 the episodes.
    selection = self._tester.CreateViewpointSelection(vp_id)
    response_dict = self._QueryViewpoints(self._cookie2, [selection])
    self.assertTrue(len(response_dict['viewpoints'][0]['episodes']) == len(ep_ids))

  def testProspectiveUser(self):
    """Tests that a prospective user does not have access to the content of more than a single
    viewpoint and any system viewpoints.
    """
    # Create prospective user and restricted cookie.
    self._CreateSimpleTestAssets()
    prospective_user, vp_id, ep_id = self._CreateProspectiveUser()
    prospective_cookie = self._tester.GetSecureUserCookie(user_id=prospective_user.user_id,
                                                          device_id=prospective_user.webapp_dev_id,
                                                          user_name=None,
                                                          viewpoint_id=vp_id)

    # Create another viewpoint shared with the prospective user.
    vp_id2, ep_ids2 = self._tester.ShareNew(self._cookie,
                                            [(self._episode_id2, self._photo_ids2)],
                                            ['Email:prospective@emailscrubbed.com'])

    # Create a system viewpoint.    
    vp_id3, ep_ids3 = self._tester.ShareNew(self._cookie,
                                            [(self._episode_id2, self._photo_ids2)],
                                            ['Email:prospective@emailscrubbed.com'])
    self._MakeSystemViewpoint(vp_id3)

    vp_selection = [self._tester.CreateViewpointSelection(vp_id),
                    self._tester.CreateViewpointSelection(vp_id2),
                    self._tester.CreateViewpointSelection(vp_id3),
                    self._tester.CreateViewpointSelection(prospective_user.private_vp_id),
                    self._tester.CreateViewpointSelection(self._user.private_vp_id)]
    response_dict = self._tester.QueryViewpoints(prospective_cookie, vp_selection)
    self.assertEqual(len(response_dict['viewpoints']), 4)
    self.assertIn('activities', response_dict['viewpoints'][0])
    self.assertIn('followers', response_dict['viewpoints'][0])
    self.assertNotIn('activities', response_dict['viewpoints'][1])
    self.assertIn('followers', response_dict['viewpoints'][1])

  def testRemovedUsers(self):
    """Tests that users who have permanently left the viewpoint are reported correctly."""
    self._CreateSimpleTestAssets()
    vp_id, _ = self._ShareSimpleTestAssets([self._user2.user_id, self._user3.user_id])
    selection = self._tester.CreateViewpointSelection(vp_id)

    # ------------------------------
    # Remove the follower (revivable).
    # ------------------------------
    self._tester.RemoveViewpoint(self._cookie2, vp_id)

    # Look at viewpoint from point of view of follower that was not removed.
    response_dict = self._QueryViewpoints(self._cookie, [selection])
    self.assertIn('cover_photo', response_dict['viewpoints'][0])
    self.assertEqual(response_dict['viewpoints'][0]['followers'],
                     [{'follower_id': 1, 'follower_timestamp': util._TEST_TIME},
                      {'follower_id': 2, 'adding_user_id': 1, 'follower_timestamp': util._TEST_TIME},
                      {'follower_id': 3, 'adding_user_id': 1, 'follower_timestamp': util._TEST_TIME}])

    # Look at viewpoint from point of view of removed follower.
    response_dict = self._QueryViewpoints(self._cookie2, [selection])
    self.assertNotIn('title', response_dict['viewpoints'][0])
    self.assertNotIn('cover_photo', response_dict['viewpoints'][0])
    self.assertNotIn('followers', response_dict['viewpoints'][0])

    # ------------------------------
    # Remove the follower (un-revivable).
    # ------------------------------
    self._tester.RemoveFollowers(self._cookie, vp_id, [self._user3.user_id])

    # Look at viewpoint from point of view of follower that was not removed.
    response_dict = self._QueryViewpoints(self._cookie, [selection])
    self.assertEqual(response_dict['viewpoints'][0]['followers'],
                     [{'follower_id': 1,
                       'follower_timestamp': util._TEST_TIME},
                      {'follower_id': 2,
                       'adding_user_id': 1,
                       'follower_timestamp': util._TEST_TIME},
                      {'follower_id': 3,
                       'labels': ['removed', 'unrevivable'],
                       'adding_user_id': 1,
                       'follower_timestamp': util._TEST_TIME}])

    # Look at viewpoint from point of view of removed follower.
    response_dict = self._QueryViewpoints(self._cookie3, [selection])
    self.assertNotIn('update_seq', response_dict['viewpoints'][0])
    self.assertNotIn('viewed_seq', response_dict['viewpoints'][0])
    self.assertNotIn('followers', response_dict['viewpoints'][0])

  def _CreateViewpointSelection(self, vp_index_list, limit=None, **kwargs):
    """Given a list of indexes into self._all_viewpoints, return a
    selection of the indexed viewpoints that can be passed to
    QueryViewpoints.
    """
    return [self._tester.CreateViewpointSelection(self._all_viewpoints[i].viewpoint_id, **kwargs)
            for i in vp_index_list]

  def _QueryViewpoints(self, cookie, vp_select_list, limit=None, fetch_all=False):
    """Sends a viewpoint query request using "request_dict". If "fetch_all"
    is true, then queries are repeated in case of limits. The "callback"
    is invoked when either there are no more viewpoints to query, or a single
    query was made and "fetch_all" was specified as False.
    """
    while True:
      response_dict = self._tester.QueryViewpoints(cookie, vp_select_list, limit=limit)

      if fetch_all:
        response_vp_dict = {vp_dict['viewpoint_id']: vp_dict for vp_dict in response_dict['viewpoints']}
        for vp_select in vp_select_list:
          response_vp = response_vp_dict.get(vp_select['viewpoint_id'], None)
          remove = True

          # Translate each "last_key" into corresponding "start_key"
          if response_vp is not None:
            if 'follower_last_key' in response_vp:
              vp_select['follower_start_key'] = response_vp['follower_last_key']
              remove = False

            if 'activity_last_key' in response_vp:
              vp_select['activity_start_key'] = response_vp['activity_last_key']
              remove = False

            if 'episode_last_key' in response_vp:
              vp_select['episode_start_key'] = response_vp['episode_last_key']
              remove = False

            if 'comment_last_key' in response_vp:
              vp_select['comment_start_key'] = response_vp['comment_last_key']
              remove = False

          # If no last keys found, then viewpoint is complete.
          if remove:
            vp_select_list.remove(vp_select)

        # If there are no more viewpoints, then return.
        if len(vp_select_list) == 0:
          break
      else:
        break

    return response_dict


def _TestQueryViewpoints(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test query_viewpoints
  service API call.
  """
  validator = tester.validator
  cookie_dict = tester.DecodeUserCookie(user_cookie)
  user_id = cookie_dict.get('user_id', None)
  device_id = cookie_dict.get('device_id', None)
  cookie_viewpoint_id = cookie_dict.get('viewpoint_id', None)

  # Send query_viewpoints request.
  actual_dict = tester.SendRequest('query_viewpoints', user_cookie, request_dict)

  limit = request_dict.get('limit', None)

  expected_dict = {'viewpoints': []}
  for request_vp in request_dict['viewpoints']:
    viewpoint_id = request_vp['viewpoint_id']

    expected_vp = validator.GetModelObject(Viewpoint, viewpoint_id, must_exist=False)
    expected_foll = validator.GetModelObject(Follower, DBKey(user_id, viewpoint_id), must_exist=False)

    # Skip any viewpoints which the user does not follow.
    if expected_foll is not None:
      expected_vp_dict = {'viewpoint_id': viewpoint_id}
      if request_vp.get('get_attributes', False):
        expected_vp_dict.update(expected_vp.MakeMetadataDict(expected_foll))
        if 'cover_photo' in expected_vp_dict:
          photo_dict = expected_vp_dict['cover_photo']
          obj_store = ObjectStore.GetInstance(ObjectStore.PHOTO)
          _AddPhotoUrls(obj_store, photo_dict)

      if not expected_foll.IsRemoved() and request_vp.get('get_followers', False):
        def _TestFollower(foll):
          return foll.viewpoint_id == viewpoint_id and foll.user_id > int(request_vp.get('follower_start_key', 0))

        followers = validator.QueryModelObjects(Follower, predicate=_TestFollower, limit=limit)
        expected_vp_dict['followers'] = [foll.MakeFriendMetadataDict() for foll in followers]

        if len(followers) > 0:
          expected_vp_dict['follower_last_key'] = '%015d' % followers[-1].user_id

      # If follower can't view viewpoint content, then nothing beyond viewpoint metadata will be returned.
      # The follower can't view viewpoint content if there is a non-matching viewpoint in the cookie.
      is_cookie_viewpoint = cookie_viewpoint_id is None or cookie_viewpoint_id == viewpoint_id
      can_view_content = is_cookie_viewpoint or expected_vp.IsSystem()
      if expected_foll.CanViewContent() and can_view_content:
        if request_vp.get('get_activities', False):
          def _TestActivity(act):
            return act.viewpoint_id == viewpoint_id and act.activity_id > request_vp.get('activity_start_key', '')

          activities = validator.QueryModelObjects(Activity, predicate=_TestActivity, limit=limit)
          expected_vp_dict['activities'] = [act.MakeMetadataDict() for act in activities]

          if len(activities) > 0:
            expected_vp_dict['activity_last_key'] = activities[-1].activity_id

        if request_vp.get('get_episodes', False):
          def _TestEpisode(ep):
            return ep.viewpoint_id == viewpoint_id and ep.episode_id > request_vp.get('episode_start_key', '')

          episodes = validator.QueryModelObjects(Episode, predicate=_TestEpisode, limit=limit)
          expected_vp_dict['episodes'] = [ep._asdict() for ep in episodes]

          if len(episodes) > 0:
            expected_vp_dict['episode_last_key'] = episodes[-1].episode_id

        if request_vp.get('get_comments', False):
          def _TestComment(cm):
            return cm.viewpoint_id == viewpoint_id and cm.comment_id > request_vp.get('comment_start_key', '')

          comments = validator.QueryModelObjects(Comment, predicate=_TestComment, limit=limit)
          expected_vp_dict['comments'] = [cm._asdict() for cm in comments]

          if len(comments) > 0:
            expected_vp_dict['comment_last_key'] = comments[-1].comment_id

      expected_dict['viewpoints'].append(expected_vp_dict)

  # Validate response dict.
  tester._CompareResponseDicts('query_viewpoints', user_id, request_dict, expected_dict, actual_dict)
  return actual_dict
