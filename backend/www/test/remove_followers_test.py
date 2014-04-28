# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test removing followers from an existing viewpoint.
"""

__author__ = ['andy@emailscrubbed.com (Andy Kimball)']

import mock

from copy import deepcopy
from functools import partial
from viewfinder.backend.base import constants, util
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.accounting import Accounting
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.services.email_mgr import EmailManager, TestEmailManager
from viewfinder.backend.www.test import service_base_test

class RemoveFollowersTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(RemoveFollowersTestCase, self).setUp()
    self._CreateSimpleTestAssets()
    self._vp_id, self._ep_id = self._ShareSimpleTestAssets([self._user2.user_id, self._user3.user_id])

  def testRemoveFollower(self):
    """Remove single follower from viewpoint."""
    # ------------------------------
    # Remove another user.
    # ------------------------------
    self._tester.RemoveFollowers(self._cookie, self._vp_id, [self._user2.user_id])
    response_dict = self._tester.QueryFollowed(self._cookie2)
    vp_dict = util.GetSingleListItem([vp_dict for vp_dict in response_dict['viewpoints']
                                      if vp_dict['viewpoint_id'] == self._vp_id])
    self.assertIn('removed', vp_dict['labels'])
    self.assertIn('unrevivable', vp_dict['labels'])

    # ------------------------------
    # Remove self.
    # ------------------------------
    self._tester.RemoveFollowers(self._cookie, self._vp_id, [self._user.user_id])
    response_dict = self._tester.QueryFollowed(self._cookie)
    vp_dict = util.GetSingleListItem([vp_dict for vp_dict in response_dict['viewpoints']
                                      if vp_dict['viewpoint_id'] == self._vp_id])
    self.assertIn('removed', vp_dict['labels'])
    self.assertIn('unrevivable', vp_dict['labels'])

  def testRemoveMultipleFollowers(self):
    """Remove multiple followers from viewpoint."""
    self._tester.RemoveFollowers(self._cookie,
                                 self._vp_id,
                                 [self._user.user_id, self._user2.user_id])

  def testRemoveOnlySelf(self):
    """Remove self from viewpoint, with no permission to remove others."""
    self._tester.RemoveFollowers(self._cookie2, self._vp_id, [self._user2.user_id])

  def testRemoveAfterAdd(self):
    """Remove a follower after adding it to a viewpoint."""
    vp_id, _ = self._ShareSimpleTestAssets([])
    self._tester.AddFollowers(self._cookie, vp_id, [self._user2.user_id])
    self._tester.RemoveFollowers(self._cookie, vp_id, [self._user2.user_id])

  def testDuplicateFollowers(self):
    """Remove same followers multiple times."""
    self._tester.RemoveFollowers(self._cookie, self._vp_id, [self._user2.user_id])
    self._tester.RemoveFollowers(self._cookie, self._vp_id, [self._user3.user_id])

    self._tester.RemoveFollowers(self._cookie,
                                 self._vp_id,
                                 [self._user2.user_id, self._user3.user_id])

  def testRemoveAfterRemoveViewpoint(self):
    """Remove a viewpoint, then remove the follower."""
    self._tester.RemoveViewpoint(self._cookie2, self._vp_id)
    self._tester.RemoveViewpoint(self._cookie3, self._vp_id)
    self._tester.RemoveFollowers(self._cookie, self._vp_id, [self._user2.user_id])

    # Try to revive the viewpoint; verify follower #2 is not revived, but follower #3 is.
    self._tester.PostComment(self._cookie, self._vp_id, 'try to revive user #2')
    response_dict = self._tester.QueryFollowed(self._cookie2)
    self.assertIn(Follower.REMOVED, response_dict['viewpoints'][0]['labels'])
    self.assertIn(Follower.UNREVIVABLE, response_dict['viewpoints'][0]['labels'])

    response_dict = self._tester.QueryFollowed(self._cookie3)
    self.assertEqual(response_dict['viewpoints'][0]['labels'], [Follower.CONTRIBUTE])

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    self._tester.RemoveFollowers(self._cookie, self._vp_id, [self._user3.user_id])
    self._tester.RemoveFollowers(self._cookie,
                                 self._vp_id,
                                 [self._user2.user_id, self._user3.user_id])

  def testNonFollowers(self):
    """Try to remove followers that don't exist on viewpoint."""
    self._tester.RemoveFollowers(self._cookie, self._vp_id, [self._user3.user_id, 1000, 1001])

  def testEmptyFollowers(self):
    """Remove empty set of followers."""
    self._tester.RemoveFollowers(self._cookie, self._vp_id, [])

  def testRemovedFollowerPermission(self):
    """Ensure that removed follower has lost all permissions on the viewpoint."""
    self._tester.RemoveFollowers(self._cookie, self._vp_id, [self._user2.user_id])

    # ------------------------------
    # Share from the viewpoint.
    # ------------------------------
    self.assertRaisesHttpError(403,
                               self._tester.ShareExisting,
                               self._cookie2,
                               self._vp_id,
                               [(self._ep_id, self._photo_ids)])

    # ------------------------------
    # Add followers to the viewpoint.
    # ------------------------------
    self.assertRaisesHttpError(403,
                               self._tester.AddFollowers,
                               self._cookie2,
                               self._vp_id,
                               [self._user.user_id])

    # ------------------------------
    # Remove followers from the viewpoint.
    # ------------------------------
    self.assertRaisesHttpError(403,
                               self._tester.RemoveFollowers,
                               self._cookie2,
                               self._vp_id,
                               [self._user.user_id])

    # ------------------------------
    # Post comment to the viewpoint.
    # ------------------------------
    self.assertRaisesHttpError(403,
                               self._tester.PostComment,
                               self._cookie2,
                               self._vp_id,
                               'Some comment')

    # ------------------------------
    # Save photos from the viewpoint.
    # ------------------------------
    self.assertRaisesHttpError(403,
                               self._tester.SavePhotos,
                               self._cookie2,
                               [(self._ep_id, self._photo_ids)])

  def testNonExistentViewpoint(self):
    """ERROR: Try to remove follower from viewpoint that doesn't exist."""
    self.assertRaisesHttpError(404,
                               self._tester.RemoveFollowers,
                               self._cookie,
                               'vunk',
                               [self._user.user_id])

  def testDefaultViewpoint(self):
    """ERROR: Try to remove user from own default viewpoint."""
    self.assertRaisesHttpError(403,
                               self._tester.RemoveFollowers,
                               self._cookie,
                               self._user.private_vp_id,
                               [self._user.user_id])

  def testNotFollower(self):
    """ERROR: Try to remove follower from viewpoint that is not followed."""
    vp_id, _ = self._ShareSimpleTestAssets([self._user2.user_id])
    self.assertRaisesHttpError(403,
                               self._tester.RemoveFollowers,
                               self._cookie3,
                               vp_id,
                               [self._user3.user_id])

  def testNotContributor(self):
    """ERROR: Try to remove follower from viewpoint without CONTRIBUTOR rights."""
    self._UpdateOrAllocateDBObject(Follower,
                                   viewpoint_id=self._vp_id,
                                   user_id=self._user3.user_id,
                                   labels=[])
    self.assertRaisesHttpError(403,
                               self._tester.RemoveFollowers,
                               self._cookie3,
                               self._vp_id,
                               [self._user3.user_id])

  def testRemoveFollowerNotAdded(self):
    """ERROR: Try to remove a follower not added by that user."""
    self.assertRaisesHttpError(403,
                               self._tester.RemoveFollowers,
                               self._cookie2,
                               self._vp_id,
                               [self._user3.user_id])

  def testRemoveOldFollower(self):
    """ERROR: Try to remove a follower added more than 7 days ago."""
    util._TEST_TIME -= constants.SECONDS_PER_WEEK
    vp_id, _ = self._ShareSimpleTestAssets([self._user2.user_id])

    util._TEST_TIME += constants.SECONDS_PER_WEEK + 1
    self.assertRaisesHttpError(403,
                               self._tester.RemoveFollowers,
                               self._cookie,
                               vp_id,
                               [self._user2.user_id])

def _TestRemoveFollowers(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test remove_followers service API call."""
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)
  viewpoint_id = request_dict['viewpoint_id']
  remove_ids = request_dict['remove_ids']

  # Send remove_followers request.
  actual_dict = tester.SendRequest('remove_followers', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # Validate each of the removed followers.
  for follower_id in remove_ids:
    follower = validator.GetModelObject(Follower, DBKey(follower_id, viewpoint_id), must_exist=False)
    if follower is not None:
      new_labels = follower.labels.union([Follower.REMOVED, Follower.UNREVIVABLE])
      follower = validator.ValidateFollower(user_id=follower_id,
                                            viewpoint_id=viewpoint_id,
                                            labels=new_labels,
                                            last_updated=op_dict['op_timestamp'])

  # Validate activity and notifications for the add.
  activity_dict = {'name': 'remove_followers',
                   'activity_id': request_dict['activity']['activity_id'],
                   'timestamp': request_dict['activity']['timestamp'],
                   'follower_ids': remove_ids}

  def _GetInvalidate(follower_id):
    if follower_id in remove_ids:
      return {'viewpoints': [{'viewpoint_id': viewpoint_id, 'get_attributes': True}]}
    else:
      return {'viewpoints': [{'viewpoint_id': viewpoint_id, 'get_followers': True}]}

  validator.ValidateFollowerNotifications(viewpoint_id,
                                          activity_dict,
                                          op_dict,
                                          _GetInvalidate)

  validator.ValidateViewpointAccounting(viewpoint_id)
  tester._CompareResponseDicts('remove_followers', user_id, request_dict, {}, actual_dict)
  return actual_dict
