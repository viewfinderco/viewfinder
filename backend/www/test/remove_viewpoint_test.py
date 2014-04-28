# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Tests remove_viewpoint method for removing a viewpoint from a user's inbox.
"""

__author__ = 'mike@emailscrubbed.com (Mike Purtell)'

import mock

from copy import deepcopy
from viewfinder.backend.base import util
from viewfinder.backend.db.accounting import Accounting
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.www.test import service_base_test

class RemoveViewpointTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(RemoveViewpointTestCase, self).setUp()
    self._CreateSimpleTestAssets()

    self._existing_vp_id, existing_ep_ids = self._tester.ShareNew(self._cookie,
                                                                  [(self._episode_id2, self._photo_ids2)],
                                                                  [self._user2.user_id],
                                                                  **self._CreateViewpointDict(self._cookie))
    self._new_vp_id, new_ep_ids = self._tester.ShareNew(self._cookie,
                                                        [(self._episode_id, self._photo_ids)],
                                                        [self._user2.user_id],
                                                        **self._CreateViewpointDict(self._cookie))

    self._existing_ep_id = existing_ep_ids[0]
    self._new_ep_id = new_ep_ids[0]

    image_data = 'original image data'
    self._tester.PutPhotoImage(self._cookie,
                               self._new_ep_id,
                               self._photo_ids[0],
                               '.o',
                               image_data,
                               content_md5=util.ComputeMD5Base64(image_data))

  def testRemoveViewpoint(self):
    """Remove a viewpoint from a user's inbox."""
    self._UpdateOrAllocateDBObject(Follower, user_id=self._user.user_id,
      viewpoint_id=self._new_vp_id, labels=[])

    # Remove the viewpoint.
    self._tester.RemoveViewpoint(self._cookie, self._new_vp_id)

    # Sanity check that the follower has the removed label.
    follower = self._RunAsync(Follower.Query, self._client, self._user.user_id, self._new_vp_id, None)
    self.assertTrue(follower.IsRemoved())

    # Try a second time as it should be idempotent.
    self._tester.RemoveViewpoint(self._cookie, self._new_vp_id)

  def testAccessAfterRemoveViewpoint(self):
    """Error: Remove a viewpoint and then attempt other operations against that viewpoint."""
    self._UpdateOrAllocateDBObject(Follower, user_id=self._user.user_id,
                                   viewpoint_id=self._new_vp_id, labels=[])

    # Remove the viewpoint.
    self._tester.RemoveViewpoint(self._cookie, self._new_vp_id)

    # Try to add a follower and observe that it fails.
    self.assertRaisesHttpError(403,
                               self._tester.AddFollowers,
                               self._cookie,
                               self._new_vp_id,
                               ['Email:extra.user1@emailscrubbed.com'])

    # Try to post a comment and observe that it fails.
    self.assertRaisesHttpError(403, self._tester.PostComment, self._cookie, self._new_vp_id, "my message")

    # Try to hide photos from episode in a removed viewpoint and observe that it fails.
    self.assertRaisesHttpError(403, self._tester.HidePhotos, self._cookie, [(self._new_ep_id, self._photo_ids[:1])])

    # Unshare episode from removed viewpoint should fail.
    self.assertRaisesHttpError(403,
                               self._tester.Unshare,
                               self._cookie,
                               self._new_vp_id,
                               [(self._new_ep_id, self._photo_ids[:1])])

    # Try to save photos to default viewpoint from episode in a removed viewpoint and observe that it fails.
    self.assertRaisesHttpError(403, self._tester.SavePhotos, self._cookie, [(self._new_ep_id, self._photo_ids[:1])])

    # Try to share an existing episode into an episode in a removed viewpoint and observe that it fails.
    self.assertRaisesHttpError(403,
                               self._tester.ShareExisting,
                               self._cookie,
                               self._new_vp_id,
                               [(self._existing_ep_id, self._photo_ids2[:1])])

    # Try to share from an episode in a removed viewpoint to an existing viewpoint and observe that it fails.
    self.assertRaisesHttpError(403,
                               self._tester.ShareExisting,
                               self._cookie,
                               self._existing_vp_id,
                               [(self._new_ep_id, self._photo_ids[:1])])

    # Try creating a new share from an episode in a removed viewpoint and observe that it fails.
    self.assertRaisesHttpError(403,
                               self._tester.ShareNew,
                               self._cookie,
                               [(self._new_ep_id, self._photo_ids[:1])],
                               [self._user2.user_id],
                               **self._CreateViewpointDict(self._cookie))

    # Try getting photo from episode in removed viewpoint and observe that we get a 404 (Not Found) response code.
    response = self._tester.GetPhotoImage(self._cookie, self._new_ep_id, self._photo_ids[0], '.o')
    self.assertEqual(response.code, 404)

    # Try putting photo for episode in removed viewpoint and observe that we get a 404 (Not Found) response code.
    image_data = 'original image data'
    response = self._tester.PutPhotoImage(self._cookie,
                               self._new_ep_id,
                               self._photo_ids[1],
                               '.o',
                               image_data,
                               content_md5=util.ComputeMD5Base64(image_data))
    self.assertEqual(response.code, 404)

    # Try QueryViewpoints against a removed viewpoint and observe that it's empty.
    result = self._tester.QueryViewpoints(self._cookie, [self._tester.CreateViewpointSelection(self._new_vp_id)])
    # QueryViewpoints should return viewpoint metadata without any content.
    self.assertIsNone(result['viewpoints'][0].get('activities', None))
    self.assertIsNone(result['viewpoints'][0].get('comments', None))
    self.assertIsNone(result['viewpoints'][0].get('episodes', None))
    self.assertIsNone(result['viewpoints'][0].get('followers', None))

    # Try UpdateViewpoint on a removed viewpoint and expect that it fails.
    self.assertRaisesHttpError(403,
                               self._tester.UpdateViewpoint,
                               self._cookie,
                               self._new_vp_id,
                               title='a new title')

    # Try UpdateEpisode on an episode in a removed viewpoint and expect failure.
    self.assertRaisesHttpError(403,
                               self._tester.UpdateEpisode,
                               self._cookie,
                               self._new_ep_id,
                               description='A newly added description')

    # Try QueryEpisodes for an episode in a removed viewpoint and expect and empty episode list in the response.
    result = self._tester.QueryEpisodes(self._cookie, [self._tester.CreateEpisodeSelection(self._new_ep_id)])
    self.assertEquals(len(result['episodes']), 0)

  def testRemoveNonExistentViewpointFails(self):
    """Error: Remove a non-existent viewpoint."""

    # Make up a viewpoint id for the test user's device.
    vp_id = Viewpoint.ConstructViewpointId(self._device_ids[0], 129)

    # Try to remove the viewpoint and expect failure.
    self.assertRaisesHttpError(403, self._tester.RemoveViewpoint, self._cookie, vp_id)

  def testRemoveViewpointCreatedByOtherUser(self):
    """Remove a viewpoint that was created by another user."""
    self._UpdateOrAllocateDBObject(Follower, user_id=self._user2.user_id,
      viewpoint_id=self._new_vp_id, labels=[])

    # Remove the viewpoint.
    self._tester.RemoveViewpoint(self._cookie2, self._new_vp_id)

  def testRemoveViewpointThatUserIsNotFollowingFails(self):
    """Error: Remove a viewpoint which user isn't following."""

    # Try to remove the viewpoint and observe that it fails.
    self.assertRaisesHttpError(403, self._tester.RemoveViewpoint, self._cookie3, self._new_vp_id)

  def testRemoveDefaultViewpointFails(self):
    """Error: Remove a viewpoint that's not owned by the user."""
    self._UpdateOrAllocateDBObject(Follower, user_id=self._user.user_id,
      viewpoint_id=self._user.private_vp_id, labels=[])

    # Try to remove the user's default viewpoint and expect failure.
    self.assertRaisesHttpError(403, self._tester.RemoveViewpoint, self._cookie, self._user.private_vp_id)

  def testRemoveViewpointByNonOwnerAndUnshare(self):
    """Share photo from originator to user2, non-owner removes viewpoint, then owner unshares."""
    self._tester.RemoveViewpoint(self._cookie2, self._new_vp_id)
    self._tester.Unshare(self._cookie, self._new_vp_id, [(self._new_ep_id, self._photo_ids[:1])])

  def testUnshareSecondLevelRemoved(self):
    """Re-share photos, remove the reshared viewpoint, then unshare the source viewpoint."""
    child_vp_id, child_ep_ids = self._tester.ShareNew(self._cookie2,
                                                      [(self._new_ep_id, self._photo_ids)],
                                                      [self._user3.user_id],
                                                      **self._CreateViewpointDict(self._cookie2))
    self._tester.RemoveViewpoint(self._cookie3, child_vp_id)
    self._tester.Unshare(self._cookie, self._new_vp_id, [(self._new_ep_id, self._photo_ids[:1])])

  def testRevivalAfterRemovingMultipleFollowers(self):
    """Test removing multiple followers and then observe that they're all revived."""
    self._tester.AddFollowers(self._cookie, self._new_vp_id, ['Email:user3@emailscrubbed.com'])
    self._tester.RemoveViewpoint(self._cookie2, self._new_vp_id)
    self._tester.RemoveViewpoint(self._cookie3, self._new_vp_id)

    self._tester.UpdateViewpoint(self._cookie, self._new_vp_id, description='a new description')

    # Sanity check that none of the followers are removed at this point.
    followers, _ = self._RunAsync(Viewpoint.QueryFollowers, self._client, self._new_vp_id)
    for follower in followers:
      self.assertFalse(follower.IsRemoved())

  def testUpdateViewpointAfterRemoveViewpoint(self):
    """Test revival of removed follower after updating viewpoint."""
    # Turn off alert validation, since this test updates title, which changes alert text.
    self._skip_validation_for = ['Alerts']

    self._tester.RemoveViewpoint(self._cookie2, self._new_vp_id)
    self._tester.UpdateViewpoint(self._cookie, self._new_vp_id, title='a new title')

  def testUpdateEpisodeAfterRemoveViewpoint(self):
    """Test revival of removed follower after updating an episode in viewpoint."""
    self._tester.RemoveViewpoint(self._cookie2, self._new_vp_id)
    self._tester.UpdateEpisode(self._cookie, self._episode_id, description='A newly added description')

  def testAddFollowersAfterRemoveViewpoint(self):
    """Test revival of removed follower after adding follower to viewpoint."""
    self._tester.RemoveViewpoint(self._cookie2, self._new_vp_id)
    self._tester.AddFollowers(self._cookie, self._new_vp_id, ['Email:extra.user1@emailscrubbed.com'])

  def testPostCommentAfterRemoveViewpoint(self):
    """Test revival of removed follower after posting comment to viewpoint."""
    self._tester.RemoveViewpoint(self._cookie2, self._new_vp_id)
    self._tester.PostComment(self._cookie, self._new_vp_id, message='My enlightening comment.')

  def testShareExistingAfterRemoveViewpoint(self):
    """Test that sharing to an existing viewpoint revives the removed follower."""
    self._tester.RemoveViewpoint(self._cookie2, self._new_vp_id)
    self._tester.ShareExisting(self._cookie, self._new_vp_id,
                               [(self._episode_id2, self._photo_ids2)])

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    self._tester.RemoveViewpoint(self._cookie2, self._new_vp_id)
    self._tester.RemoveViewpoint(self._cookie2, self._new_vp_id)

def _TestRemoveViewpoint(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test remove_viewpoint
  service API call.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)
  viewpoint_id = request_dict['viewpoint_id']

  # Send remove_viewpoint request.
  actual_dict = tester.SendRequest('remove_viewpoint', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  request_dict['user_id'] = user_id

  # Validate Follower object.
  follower = validator.GetModelObject(Follower, DBKey(user_id, viewpoint_id))
  if not follower.IsRemoved():
    # Adjust labels to reflect addition of REMOVED label.
    labels = follower.labels.union([Follower.REMOVED])
    validator.ValidateUpdateDBObject(Follower, user_id=user_id, viewpoint_id=viewpoint_id, labels=labels)

    # Validate activity and notifications for the update.
    invalidate = {'viewpoints': [{'viewpoint_id': viewpoint_id,
                                  'get_attributes': True}]}

    # Only follower attributes were updated, so validate single notification to calling user.
    validator.ValidateNotification('remove_viewpoint',
                                   user_id,
                                   op_dict,
                                   invalidate,
                                   viewpoint_id=viewpoint_id)

  validator.ValidateViewpointAccounting(viewpoint_id)
  tester._CompareResponseDicts('remove_viewpoint', user_id, request_dict, {}, actual_dict)
  return actual_dict
