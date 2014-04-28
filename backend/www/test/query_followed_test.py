# -*- coding: utf-8 -*-
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests query of viewpoints followed by a user, with limits and
start keys.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

from viewfinder.backend.base import constants, util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.followed import Followed
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.www.service import _AddPhotoUrls
from viewfinder.backend.www.test import service_base_test

class QueryFollowedTestCase(service_base_test.ServiceBaseTestCase):
  def testQueryFollowed(self):
    """Tests various followed queries."""
    # Create a number of interesting viewpoints to query against.
    self._CreateQueryAssets()

    # Get the first followed viewpoint of user #1 to use as a start key.
    start_key = self._tester.QueryFollowed(self._cookie, limit=1)['last_key']

    for user in self._users:
      cookie = self._GetSecureUserCookie(user)
      self._tester.QueryFollowed(cookie)
      self._tester.QueryFollowed(cookie, limit=1)
      self._tester.QueryFollowed(cookie, limit=5)
      self._tester.QueryFollowed(cookie, limit=1000)
      self._tester.QueryFollowed(cookie, limit=3, start_key=start_key)
      self._tester.QueryFollowed(cookie, start_key=start_key)
      self._tester.QueryFollowed(cookie, start_key='ZZZ')

  def testOrder(self):
    """Validate that the most recently updated viewpoints are first in
    the Followed table.
    """
    episode_id, photo_ids = self._UploadOneEpisode(self._cookie, 2)

    # Add 24 hours to timestamp so that viewpoint sorts in next day (viewpoints in the same day
    # have an undefined ordering with respect to each other).
    util._TEST_TIME += constants.SECONDS_PER_DAY
    act_dict = self._tester.CreateActivityDict(self._cookie)
    act_dict['timestamp'] += constants.SECONDS_PER_DAY
    vp_dict = self._CreateViewpointDict(self._cookie)
    self._tester.ShareNew(self._cookie,
                          [(episode_id, photo_ids)],
                          [self._user2.user_id],
                          act_dict=act_dict,
                          **vp_dict)

    response = self._tester.QueryFollowed(self._cookie)

    # Verify that first viewpoint is the newly added viewpoint, and the second is the default viewpoint.
    self.assertEqual(response['viewpoints'][0]['viewpoint_id'], vp_dict['viewpoint_id'])
    self.assertEqual(response['viewpoints'][1]['viewpoint_id'], self._user.private_vp_id)

  def testProspectiveUser(self):
    """Tests that a prospective user can access metadata for all followed viewpoints."""
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

    response_dict = self._tester.QueryFollowed(prospective_cookie)
    self.assertEqual(len(response_dict['viewpoints']), 3)
    self.assertIn('cover_photo', response_dict['viewpoints'][0])
    self.assertIn('update_seq', response_dict['viewpoints'][1])
    self.assertIn('viewed_seq', response_dict['viewpoints'][2])

  def testRemovedUser(self):
    """Tests that user who has been removed from a viewpoint can see limited metadata."""
    self._CreateSimpleTestAssets()
    vp_id, _ = self._ShareSimpleTestAssets([self._user2.user_id])
    self._tester.RemoveViewpoint(self._cookie2, vp_id)

    response_dict = self._tester.QueryFollowed(self._cookie2)
    self.assertEqual(len(response_dict['viewpoints']), 2)
    for attr_name in response_dict['viewpoints'][0]:
      self.assertIn(attr_name, ['viewpoint_id', 'type', 'follower_id', 'user_id', 'timestamp', 'labels', 'adding_user_id'])


def _TestQueryFollowed(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test query_followed
  service API call.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)

  def _MakeViewpointDict(followed):
    """Create a viewpoint dict from the followed object plus its
    referenced viewpoint object.
    """
    viewpoint = validator.GetModelObject(Viewpoint, followed.viewpoint_id)
    follower = validator.GetModelObject(Follower, DBKey(followed.user_id, followed.viewpoint_id))
    metadata_dict = viewpoint.MakeMetadataDict(follower)
    if follower.CanViewContent() and 'cover_photo' in metadata_dict:
      photo_dict = metadata_dict['cover_photo']
      obj_store = ObjectStore.GetInstance(ObjectStore.PHOTO)
      _AddPhotoUrls(obj_store, photo_dict)

    return metadata_dict

  # Send query_followed request.
  actual_dict = tester.SendRequest('query_followed', user_cookie, request_dict)

  # Build expected response dict.
  followed = validator.QueryModelObjects(Followed,
                                         user_id,
                                         limit=request_dict.get('limit', None),
                                         start_key=request_dict.get('start_key', None))

  expected_dict = {'viewpoints': [_MakeViewpointDict(f) for f in followed]}
  if len(followed) > 0:
    expected_dict['last_key'] = followed[-1].sort_key

  tester._CompareResponseDicts('query_followed', user_id, request_dict, expected_dict, actual_dict)
  return actual_dict
