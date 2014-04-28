# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test photo sharing to an existing viewpoint.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import mock
import time

from copy import deepcopy
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.op_manager import OpManager
from viewfinder.backend.www.test import service_base_test

class ShareExistingTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(ShareExistingTestCase, self).setUp()
    self._CreateSimpleTestAssets()

    self._existing_vp_id, existing_ep_ids = self._tester.ShareNew(self._cookie,
                                                                  [(self._episode_id2, self._photo_ids2)],
                                                                  [self._user2.user_id],
                                                                  **self._CreateViewpointDict(self._cookie))
    self._existing_ep_id = existing_ep_ids[0]

  def testShare(self):
    """Share a single photo to a new episode in an existing viewpoint."""
    self._tester.ShareExisting(self._cookie, self._existing_vp_id,
                               [(self._episode_id, self._photo_ids[:1])])
    # Sharing more photos shouldn't cause the cover_photo to change.
    viewpoint = self._RunAsync(Viewpoint.Query, self._client, self._existing_vp_id, col_names=None)
    self.assertEqual(viewpoint.cover_photo['photo_id'], self._photo_ids2[0])

  def testShareEpisodesNoAccess(self):
    """ERROR: Try to share episodes from viewpoint which user does not
    follow.
    """
    self.assertRaisesHttpError(403, self._tester.ShareExisting, self._cookie2, self._existing_vp_id,
                               [(self._episode_id, self._photo_ids)])

  def testShareInvalidEpisode(self):
    """ERROR: Try to share a non-existing episode."""
    self.assertRaisesHttpError(400, self._tester.ShareExisting, self._cookie2, self._existing_vp_id,
                               [('eunknown', self._photo_ids)])

  def testShareViewpointNoAccess(self):
    """ERROR: Try to share episodes into a viewpoint which user does
    not follow.
    """
    self.assertRaisesHttpError(403, self._tester.ShareExisting,
                               self._cookie2, self._user.private_vp_id,
                               [(self._existing_ep_id, self._photo_ids)])

  def testShareMultiple(self):
    """Share two photos to a new episode in an existing viewpoint."""
    self._tester.ShareExisting(self._cookie, self._existing_vp_id,
                               [(self._episode_id, self._photo_ids)])

  def testShareBack(self):
    """Share photos back into a new episode in the same viewpoint."""
    self._tester.ShareExisting(self._cookie, self._existing_vp_id,
                               [(self._existing_ep_id, self._photo_ids2)])

  def testShareNoEpisodes(self):
    """Share empty episode list."""
    self._tester.ShareExisting(self._cookie, self._existing_vp_id, [])

  def testShareMultipleEpisodes(self):
    """Share photos from multiple episodes."""
    self._tester.ShareExisting(self._cookie, self._existing_vp_id,
                               [(self._episode_id, self._photo_ids),
                                (self._existing_ep_id, self._photo_ids2)])

  def testShareDuplicatePhotos(self):
    """Share same photos from same source episode to same target episode
    in new viewpoint.
    """
    share_list = [{'existing_episode_id': self._episode_id2,
                   'new_episode_id': self._existing_ep_id,
                   'photo_ids': self._photo_ids2}]
    self._tester.ShareExisting(self._cookie, self._existing_vp_id, share_list)
    self._tester.ShareExisting(self._cookie, self._existing_vp_id, share_list)

  def testShareSameEpisode(self):
    """Share different photos from same source episode to same target
    episode in new viewpoint.
    """
    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._episode_id, self._photo_ids[:1])],
                                          [self._user2.user_id])

    share_list = [{'existing_episode_id': self._episode_id,
                   'new_episode_id': ep_ids[0],
                   'photo_ids': self._photo_ids[1:]}]

    self._tester.ShareExisting(self._cookie, vp_id, share_list)

  def testShareAfterUnshare(self):
    """Share photos that were previously unshared (unshare attribute should be removed)."""
    def _CountUnsharedPhotos(ep_id):
      response_dict = self._tester.QueryEpisodes(self._cookie, [self._tester.CreateEpisodeSelection(ep_id)])
      return len([ph_dict for ph_dict in response_dict['episodes'][0]['photos']
                  if 'labels' in ph_dict and 'unshared' in ph_dict['labels']])

    self._tester.Unshare(self._cookie, self._existing_vp_id, [(self._existing_ep_id, self._photo_ids2)])
    self.assertEqual(_CountUnsharedPhotos(self._existing_ep_id), 2)

    share_dict = {'existing_episode_id': self._episode_id2,
                  'new_episode_id': self._existing_ep_id,
                  'photo_ids': self._photo_ids2}
    self._tester.ShareExisting(self._cookie, self._existing_vp_id, [share_dict])
    self.assertEqual(_CountUnsharedPhotos(self._existing_ep_id), 0)

  def testShareDifferentUser(self):
    """Share into the same viewpoint with another user."""
    ep_ph_ids = self._UploadOneEpisode(self._cookie2, 5)
    self._tester.ShareExisting(self._cookie2, self._existing_vp_id, [ep_ph_ids])

  def testShareToSameEpisode(self):
    """Share multiple photos to same target episode in new viewpoint."""
    timestamp = time.time()
    new_episode_id = Episode.ConstructEpisodeId(timestamp, self._device_ids[0], self._test_id)
    self._test_id += 1
    share_dict1 = {'existing_episode_id': self._existing_ep_id,
                   'new_episode_id': new_episode_id,
                   'photo_ids': self._photo_ids2[:1]}
    share_dict2 = {'existing_episode_id': self._existing_ep_id,
                   'new_episode_id': new_episode_id,
                   'photo_ids': self._photo_ids2[1:]}

    self._tester.ShareExisting(self._cookie, self._existing_vp_id, [share_dict1, share_dict2])

  def testUnrevivable(self):
    """Share photos to a viewpoint with an unrevivable removed follower."""
    self._tester.RemoveFollowers(self._cookie, self._existing_vp_id, [self._user2.user_id])
    self._tester.ShareExisting(self._cookie,
                               self._existing_vp_id,
                               [(self._episode_id, self._photo_ids)])
    response_dict = self._tester.QueryFollowed(self._cookie2)
    self.assertIn(Follower.REMOVED, response_dict['viewpoints'][0]['labels'])
    self.assertIn(Follower.UNREVIVABLE, response_dict['viewpoints'][0]['labels'])

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    self._tester.Unshare(self._cookie, self._existing_vp_id, [(self._existing_ep_id, self._photo_ids2)])
    self._tester.RemoveViewpoint(self._cookie2, self._existing_vp_id)
    self._tester.ShareExisting(self._cookie, self._existing_vp_id, [(self._episode_id, self._photo_ids)])

    share_dict = {'existing_episode_id': self._episode_id2,
                  'new_episode_id': self._existing_ep_id,
                  'photo_ids': self._photo_ids2}
    self._tester.ShareExisting(self._cookie, self._existing_vp_id, [share_dict])

  def testShareFromMultipleParents(self):
    """ERROR: Try to share to the same episode from multiple parent episodes."""
    share_dict = {'existing_episode_id': self._episode_id,
                  'new_episode_id': self._existing_ep_id,
                  'photo_ids': self._photo_ids}
    self.assertRaisesHttpError(400, self._tester.ShareExisting, self._cookie, self._existing_vp_id, [share_dict])

  def testShareSamePhotoSameEpisode(self):
    """ERROR: Try to share the same photo multiple times to same episode."""
    timestamp = time.time()
    new_episode_id = Episode.ConstructEpisodeId(timestamp, self._device_ids[0], self._test_id)
    self._test_id += 1
    share_dict = {'existing_episode_id': self._episode_id,
                  'new_episode_id': new_episode_id,
                  'photo_ids': self._photo_ids}
    self.assertRaisesHttpError(400,
                               self._tester.ShareExisting,
                               self._cookie,
                               self._existing_vp_id,
                               [share_dict, share_dict])

  def testWrongViewpoint(self):
    """ERROR: Try to share photos to existing episode that is not in the target viewpoint."""
    timestamp = time.time()
    new_episode_id = Episode.ConstructEpisodeId(timestamp, self._device_ids[0], self._test_id)
    self._test_id += 1
    share_dict = {'existing_episode_id': self._episode_id,
                  'new_episode_id': self._episode_id2,
                  'photo_ids': self._photo_ids}
    self.assertRaisesHttpError(400,
                               self._tester.ShareExisting,
                               self._cookie,
                               self._existing_vp_id,
                               [share_dict])

  def testWrongDeviceId(self):
    """ERROR: Try to create an episode using a device id that is different
    than the one in the user cookie.
    """
    share_list = [self._tester.CreateCopyDict(self._cookie2, self._episode_id, self._photo_ids)]
    self.assertRaisesHttpError(403, self._tester.ShareExisting, self._cookie, self._existing_vp_id, share_list)

  def testSetCoverPhoto(self):
    """Share_existing after unsharing everything in a viewpoint.  This exercises the new selection
    of a cover_photo during share_existing."""
    from viewfinder.backend.db.viewpoint import Viewpoint

    viewpoint = self._RunAsync(Viewpoint.Query, self._client, self._existing_vp_id, col_names=None)
    self.assertEqual(viewpoint.cover_photo['episode_id'], self._existing_ep_id)
    self.assertEqual(viewpoint.cover_photo['photo_id'], sorted(self._photo_ids2)[0])

    self._tester.Unshare(self._cookie, self._existing_vp_id, [(self._existing_ep_id, self._photo_ids2)])
    viewpoint = self._RunAsync(Viewpoint.Query, self._client, self._existing_vp_id, col_names=None)
    self.assertEqual(viewpoint.cover_photo, None)

    ep_ids = self._tester.ShareExisting(self._cookie, self._existing_vp_id, [(self._episode_id, self._photo_ids[:1])])
    viewpoint = self._RunAsync(Viewpoint.Query, self._client, self._existing_vp_id, col_names=None)
    self.assertEqual(viewpoint.cover_photo['episode_id'], ep_ids[0])
    self.assertEqual(viewpoint.cover_photo['photo_id'], sorted(self._photo_ids[:1])[0])

  def testAutoSave(self):
    """Test share_existing when auto-save is enabled by follower(s)."""
    # Unfortunately, the test framework uses overlapping ids in the case of user #3, since
    # it has only a web device. Work around this by updating user #3's asset_id_seq value.
    self._UpdateOrAllocateDBObject(User, user_id=self._user3.user_id, asset_id_seq=1000)

    # Share to users 2 and 3.
    vp_id, ep_id = self._ShareSimpleTestAssets([self._user2.user_id, self._user3.user_id])

    # Upload a couple episodes for user 3. 
    upload_ep_id1, upload_ph_ids1 = self._UploadOneEpisode(self._cookie3, 2)
    upload_ep_id2, upload_ph_ids2 = self._UploadOneEpisode(self._cookie3, 2)

    # ------------------------------
    # Test auto-save enabled for one user. 
    # ------------------------------
    # Enable auto-save for user #2.  
    self._tester.UpdateFollower(self._cookie2, vp_id, labels=[Follower.CONTRIBUTE, Follower.AUTOSAVE])

    self._tester.ShareExisting(self._cookie, vp_id, [(self._episode_id2, self._photo_ids2[:1])])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 1)

    # ------------------------------
    # Test auto-save enabled for multiple users. 
    # ------------------------------
    # Enable auto-save for user #3.  
    self._tester.UpdateFollower(self._cookie3, vp_id, labels=[Follower.CONTRIBUTE, Follower.AUTOSAVE])

    new_ep_ids = self._tester.ShareExisting(self._cookie, vp_id, [(self._episode_id2, self._photo_ids2[1:])])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 2)
    self.assertEqual(self._CountEpisodes(self._cookie3, self._user3.private_vp_id), 3)

    # ------------------------------
    # Test sharing same episode again (should re-use same target episode id).
    # ------------------------------
    ep_dict = {'existing_episode_id': self._episode_id2,
               'new_episode_id': new_ep_ids[0],
               'photo_ids': self._photo_ids2}
    self._tester.ShareExisting(self._cookie, vp_id, [ep_dict])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 2)
    self.assertEqual(self._CountEpisodes(self._cookie3, self._user3.private_vp_id), 3)

    # ------------------------------
    # Test sharing user with auto-save enabled; share from default viewpoint. 
    # ------------------------------
    self._tester.ShareExisting(self._cookie3, vp_id, [(upload_ep_id1, upload_ph_ids1)])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 3)
    self.assertEqual(self._CountEpisodes(self._cookie3, self._user3.private_vp_id), 3)

    # ------------------------------
    # Test sharing user with auto-save enabled; share from non-default viewpoint. 
    # ------------------------------
    self._tester.ShareExisting(self._cookie3, vp_id, [(ep_id, self._photo_ids[:1])])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 4)
    self.assertEqual(self._CountEpisodes(self._cookie3, self._user3.private_vp_id), 4)

    # ------------------------------
    # Test multiple episodes (mix from default & non-default viewpoint). 
    # ------------------------------
    self._tester.ShareExisting(self._cookie3, vp_id, [(ep_id, self._photo_ids),
                                                      (upload_ep_id1, upload_ph_ids1),
                                                      (upload_ep_id2, upload_ph_ids2)])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 7)
    self.assertEqual(self._CountEpisodes(self._cookie3, self._user3.private_vp_id), 7)

    # ------------------------------
    # Test multiple episodes, where one episode was already saved, but others were not. 
    # ------------------------------
    ep_dict = {'existing_episode_id': self._episode_id2,
               'new_episode_id': new_ep_ids[0],
               'photo_ids': self._photo_ids2}
    self._tester.ShareExisting(self._cookie, vp_id, [(ep_id, self._photo_ids),
                                                     ep_dict,
                                                     (ep_id, self._photo_ids)])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 9)
    self.assertEqual(self._CountEpisodes(self._cookie3, self._user3.private_vp_id), 9)

  def testRemovedFollowerAutoSave(self):
    """Enable auto-save, then remove the follower, then share to the viewpoint."""
    self._tester.UpdateFollower(self._cookie2, self._existing_vp_id, labels=[Follower.CONTRIBUTE, Follower.AUTOSAVE])

    # ------------------------------
    # Test removed. 
    # ------------------------------
    self._tester.RemoveViewpoint(self._cookie2, self._existing_vp_id)
    self._tester.ShareExisting(self._cookie, self._existing_vp_id, [(self._episode_id, self._photo_ids[:1])])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 1)

    # ------------------------------
    # Test removed + unrevivable.
    # ------------------------------
    self._tester.RemoveFollowers(self._cookie2, self._existing_vp_id, [self._user2.user_id])
    self._tester.ShareExisting(self._cookie, self._existing_vp_id, [(self._episode_id, self._photo_ids[1:])])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 1)


def _TestShareExisting(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test share_existing service API call."""
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  # Send share_existing request.
  actual_dict = tester.SendRequest('share_existing', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # Validate all episodes and posts are created.
  validator.ValidateCopyEpisodes(op_dict, request_dict['viewpoint_id'], request_dict['episodes'])

  # Validate new cover_photo is selected and updated, if needed.
  viewpoint_changed = validator.ValidateCoverPhoto(request_dict['viewpoint_id'])

  # Validate activity and notifications for the share.
  activity_dict = {'name': 'share_existing',
                   'activity_id': request_dict['activity']['activity_id'],
                   'timestamp': request_dict['activity']['timestamp'],
                   'episodes': [{'episode_id': ep_dict['new_episode_id'],
                                 'photo_ids': ep_dict['photo_ids']}
                                for ep_dict in request_dict['episodes']]}

  invalidate = {'episodes': [{'episode_id': ep_dict['new_episode_id'],
                              'get_attributes': True,
                              'get_photos': True}
                             for ep_dict in request_dict['episodes']]}
  if viewpoint_changed:
    invalidate['viewpoints'] = [{'viewpoint_id': request_dict['viewpoint_id'],
                                 'get_attributes': True}]

  validator.ValidateFollowerNotifications(request_dict['viewpoint_id'],
                                          activity_dict,
                                          op_dict,
                                          invalidate,
                                          sends_alert=True)

  validator.ValidateViewpointAccounting(request_dict['viewpoint_id'])
  tester._CompareResponseDicts('share_existing', user_id, request_dict, {}, actual_dict)

  _ValidateAutoSave(tester, user_id, device_id, request_dict)

  return actual_dict


def _ValidateAutoSave(tester, user_id, device_id, request_dict):
  """Validates that the shared photos have been saved to the default viewpoint of any follower
  that has the target viewpoint marked as "auto-save".
  """
  from viewfinder.backend.www.test.save_photos_test import _ValidateSavePhotos
  validator = tester.validator

  # Validate auto-save.
  follower_matches = lambda f: f.viewpoint_id == request_dict['viewpoint_id']
  for follower in validator.QueryModelObjects(Follower, predicate=follower_matches):
    # Only validate current followers that have viewpoint marked as auto-save.
    if not follower.ShouldAutoSave() or follower.IsRemoved():
      continue

    follower_user = tester._RunAsync(User.Query, validator.client, follower.user_id, None)

    # Skip validation of follower that is sharing from default viewpoint.
    source_episodes = [validator.GetModelObject(Episode, ep_dict['existing_episode_id'])
                       for ep_dict in request_dict['episodes']]
    if all(ep.viewpoint_id == follower_user.private_vp_id for ep in source_episodes):
      continue

    # The share_existing op triggered a save_photos op, so wait for that to complete.
    tester._RunAsync(OpManager.Instance().WaitForUserOps, validator.client, follower.user_id)

    # Get the ids of episodes that should have been created during the auto-save.
    expected_asset_id = follower_user.asset_id_seq

    save_request_dict = deepcopy(request_dict)

    # Iterate backwards, since last episode should have used last asset id.
    for ep_dict in reversed(save_request_dict['episodes']):
      # The share_existing "new_episode_id" becomes the "existing_episode_id" for save_photos.
      ep_dict['existing_episode_id'] = ep_dict['new_episode_id']

      # If target episode already existed, that should have been used.
      episode_matches = lambda e: e.user_id == follower.user_id and e.parent_ep_id == ep_dict['existing_episode_id']
      episodes = validator.QueryModelObjects(Episode, predicate=episode_matches)
      if episodes:
        ep_dict['new_episode_id'] = episodes[0].episode_id
      else:
        expected_asset_id -= 1
        timestamp, _, _ = Episode.DeconstructEpisodeId(ep_dict['existing_episode_id'])
        ep_dict['new_episode_id'] = Episode.ConstructEpisodeId(timestamp,
                                                               follower_user.webapp_dev_id,
                                                               expected_asset_id)

    # Create expected activity dict for the save_photos op.
    expected_asset_id -= 1
    save_activity_id = Activity.ConstructActivityId(request_dict['activity']['timestamp'],
                                                    follower_user.webapp_dev_id,
                                                    expected_asset_id)
    save_request_dict['activity']['activity_id'] = save_activity_id

    # Create expected operation id for the save_photos op.
    expected_asset_id -= 1
    save_op_id = Operation.ConstructOperationId(follower_user.webapp_dev_id, expected_asset_id)
    save_request_dict['headers']['op_id'] = save_op_id

    _ValidateSavePhotos(tester, follower.user_id, follower_user.webapp_dev_id, save_request_dict)
