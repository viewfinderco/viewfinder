# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test photo unsharing.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import mock
import time

from copy import deepcopy
from viewfinder.backend.base import util
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.unshare_op import UnshareOperation
from viewfinder.backend.www.test import service_base_test


class UnshareTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    """Upload two photos."""
    super(UnshareTestCase, self).setUp()
    self._CreateSimpleTestAssets()

    self._new_vp_id, new_ep_ids = self._tester.ShareNew(self._cookie,
                                                        [(self._episode_id, self._photo_ids)],
                                                        [self._user2.user_id])
    self._new_ep_id = new_ep_ids[0]

    # Turn off SMS alerts for user #2, since often we are unsharing cover photos, which causes
    # mismatch when validating at the end of the test.
    settings = AccountSettings.CreateForUser(self._user2.user_id, sms_alerts=AccountSettings.SMS_NONE)
    self._UpdateOrAllocateDBObject(AccountSettings, **settings._asdict())

  def tearDown(self):
    """Restore constants for future tests."""
    Photo.CLAWBACK_GRACE_PERIOD = 60 * 60 * 24 * 7
    UnshareOperation._UNSHARE_LIMIT = 200
    super(UnshareTestCase, self).tearDown()

  def testUnshare(self):
    """Share photo from originator to user2, and unshare."""
    # Set the unshare limit in order to verify that only one episode is being unshared. If more
    # than that are mistakenly unshared, then the unshare operation will raise an exception.
    UnshareOperation._UNSHARE_LIMIT = 1
    before_cover_photo = self._RunAsync(Viewpoint.Query, self._client, self._new_vp_id, col_names=None).cover_photo

    self._tester.Unshare(self._cookie, self._new_vp_id, [(self._new_ep_id, self._photo_ids[:1])])
    # Show that the cover_photo has changed as a side effect of the unshare.
    viewpoint = self._RunAsync(Viewpoint.Query, self._client, self._new_vp_id, col_names=None)
    self.assertNotEqual(viewpoint.cover_photo, before_cover_photo)
    self.assertEqual(viewpoint.cover_photo['photo_id'], self._photo_ids[1])

  def testSerialUnshare(self):
    """Share both photos from originator to user2, then user2 to user3,
    then unshare from originator.
    """
    UnshareOperation._UNSHARE_LIMIT = 2
    self._tester.ShareNew(self._cookie2,
                          [(self._new_ep_id, self._photo_ids)],
                          [self._user3.user_id])

    self._tester.Unshare(self._cookie, self._new_vp_id, [(self._new_ep_id, self._photo_ids)])

  def testTreeUnshare(self):
    """Share both photos from originator to multiple viewpoints, then
    unshare from originator.
    """
    UnshareOperation._UNSHARE_LIMIT = 7
    for i in xrange(2):
      vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                            [(self._new_ep_id, self._photo_ids)],
                                            [self._user2.user_id])
      for j in xrange(1):
        self._tester.ShareNew(self._cookie2,
                              [(ep_ids[0], self._photo_ids)],
                              [self._user3.user_id])

    self._tester.Unshare(self._cookie, self._new_vp_id, [(self._new_ep_id, self._photo_ids)])

  def testUnshareSubsetShares(self):
    """Share both photos from originator to user2, then share only one
    photo to user3, then unshare all photos.
    """
    UnshareOperation._UNSHARE_LIMIT = 2
    self._tester.ShareNew(self._cookie2,
                          [(self._new_ep_id, self._photo_ids[:1])],
                          [self._user3.user_id])

    self._tester.Unshare(self._cookie, self._new_vp_id, [(self._new_ep_id, self._photo_ids)])

  def testCircularUnshare(self):
    """Share both photos from originator to user2, then user2 back to
    the the originating viewpoint (but different episode), then unshare.
    """
    UnshareOperation._UNSHARE_LIMIT = 3
    vp_id, ep_ids = self._tester.ShareNew(self._cookie2,
                                          [(self._new_ep_id, self._photo_ids)],
                                          [self._user3.user_id])

    self._tester.ShareExisting(self._cookie2, self._new_vp_id, [(ep_ids[0], self._photo_ids)])

    self._tester.Unshare(self._cookie, self._new_vp_id, [(self._new_ep_id, self._photo_ids)])

  def testSubUnshare(self):
    """Share both photos from originator to user2, then user2 to user3,
    the unshare from user2.
    """
    UnshareOperation._UNSHARE_LIMIT = 1
    vp_id, ep_ids = self._tester.ShareNew(self._cookie2,
                                          [(self._new_ep_id, self._photo_ids)],
                                          [self._user3.user_id])

    self._tester.Unshare(self._cookie2, vp_id, [(ep_ids[0], self._photo_ids)])

  def testMultiplePaths(self):
    """Share photo from originator to user2, then user2 to user3, then
    from originator to user3. Verify that when user2 unshares, photos
    shared by originator are not unshared as well.
    """
    UnshareOperation._UNSHARE_LIMIT = 1
    vp_id, ep_ids = self._tester.ShareNew(self._cookie2,
                                          [(self._new_ep_id, self._photo_ids)],
                                          [self._user3.user_id])

    vp_id_2, ep_ids_2 = self._tester.ShareNew(self._cookie,
                                              [(self._episode_id, self._photo_ids)],
                                              [self._user3.user_id])

    # Unshare by user #2.
    self._tester.Unshare(self._cookie2, vp_id, [(ep_ids[0], self._photo_ids)])

  def testMultipleUnshares(self):
    """Share photo from originator to user2 to user3, then unshare multiple times."""
    vp_id, ep_ids = self._tester.ShareNew(self._cookie2,
                                          [(self._new_ep_id, self._photo_ids[:1]),
                                           (self._new_ep_id, self._photo_ids[1:])],
                                          [self._user3.user_id])

    UnshareOperation._UNSHARE_LIMIT = 3
    self._tester.Unshare(self._cookie, self._new_vp_id, [(self._new_ep_id, self._photo_ids[:1])])

    UnshareOperation._UNSHARE_LIMIT = 3
    self._tester.Unshare(self._cookie, self._new_vp_id, [(self._new_ep_id, self._photo_ids[1:])])

    UnshareOperation._UNSHARE_LIMIT = 3
    self._tester.Unshare(self._cookie, self._new_vp_id, [(self._new_ep_id, self._photo_ids)])

    # Use unshare limits to validate that the unshare operation *does* recurse into already
    # unshared episodes.
    UnshareOperation._UNSHARE_LIMIT = 2
    self.assertRaisesHttpError(403,
                               self._tester.Unshare,
                               self._cookie,
                               self._new_vp_id,
                               [(self._new_ep_id, self._photo_ids)])

  def testDuplicates(self):
    """Test same episode and photos unshared in same request."""
    self._tester.Unshare(self._cookie,
                         self._new_vp_id,
                         [(self._new_ep_id, self._photo_ids[:1]),
                          (self._new_ep_id, [self._photo_ids[0], self._photo_ids[0]])])

  def testInvalidViewpointId(self):
    """ERROR: Try to unshare invalid viewpoint id. Returns InvalidRequest."""
    self.assertRaisesHttpError(400, self._tester.Unshare, self._cookie, 'vunknown',
                               [(self._new_ep_id, self._photo_ids)])

  def testInvalidEpisodeId(self):
    """ERROR: Try to unshare invalid episode id. Returns InvalidRequest."""
    self.assertRaisesHttpError(400, self._tester.Unshare, self._cookie, self._new_vp_id,
                               [('eunknown', self._photo_ids)])

  def testInvalidPhotoId(self):
    """ERROR: Try to unshare invalid photo id."""
    self.assertRaisesHttpError(403, self._tester.Unshare, self._cookie, self._new_vp_id,
                               [(self._new_ep_id, ['punknown'])])

  def testNoPermission(self):
    """ERROR: Try to unshare a photo which the caller has no permission
    to access.
    """
    self.assertRaisesHttpError(403, self._tester.Unshare, self._cookie3, self._new_vp_id,
                               [(self._new_ep_id, self._photo_ids)])

  def testNotSharer(self):
    """ERROR: Try to unshare a photo which the caller did not originally share.
    """
    self.assertRaisesHttpError(403, self._tester.Unshare, self._cookie2, self._new_vp_id,
                               [(self._new_ep_id, self._photo_ids)])

  def testShareLimit(self):
    """ERROR: Try to unshare more episodes than the limit.
    """
    UnshareOperation._UNSHARE_LIMIT = 3

    for i in xrange(3):
      self._tester.ShareNew(self._cookie,
                            [(self._new_ep_id, self._photo_ids)],
                            [self._user2.user_id])

    self.assertRaisesHttpError(403, self._tester.Unshare, self._cookie, self._new_vp_id,
                               [(self._new_ep_id, self._photo_ids)])

  def testRevokedPrivileges(self):
    """ERROR: Share from originator to user2, then unshare. Verify that user2
    is unable to reshare.
    """
    self._tester.Unshare(self._cookie, self._new_vp_id, [(self._new_ep_id, self._photo_ids)])

    self.assertRaisesHttpError(403, self._tester.ShareNew, self._cookie2,
                              [(self._new_ep_id, self._photo_ids)],
                              [self._user3.user_id])

  def testClawbackGracePeriod(self):
    """Set grace period to a fraction of a second. Share both photos
    from originator to user2. Unshare photo 1 immediately and verify
    all privileges are revoked.  Wait the grace period, unshare photo
    2 and verify error is raised.
    """
    Photo.CLAWBACK_GRACE_PERIOD = 0.500
    util._TEST_TIME = time.time()

    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._episode_id, self._photo_ids)],
                                          [self._user2.user_id])

    self._tester.Unshare(self._cookie, vp_id, [(ep_ids[0], self._photo_ids[:1])])

    self._RunAsync(self.io_loop.add_timeout, util._TEST_TIME + Photo.CLAWBACK_GRACE_PERIOD)

    self.assertRaisesHttpError(403, self._tester.Unshare, self._cookie, vp_id,
                               [(ep_ids[0], self._photo_ids[1:])])

  def testUnshareTimestamps(self):
    """Create episode with an old timestamp that is older than the
    clawback grace period. Then upload the episode so that its
    publish_timestamp is now. Verify that unshare is allowed, since
    unshare should use the publish_timestamp, not the episode
    timestamp.
    """
    timestamp = time.time() - Photo.CLAWBACK_GRACE_PERIOD - 1
    ep_id, ph_ids = self._tester.UploadEpisode(self._cookie, {'timestamp': timestamp},
                                               [self._CreatePhotoDict(self._cookie)])

    new_vp_id, new_ep_ids = self._tester.ShareNew(self._cookie,
                                                  [(ep_id, ph_ids)],
                                                  [self._user2.user_id])

    self._tester.Unshare(self._cookie, new_vp_id, [(new_ep_ids[0], ph_ids)])

  def testMultipleEpisodeUnshare(self):
    """Unshare photos from multiple episodes inside the same viewpoint."""
    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._new_ep_id, self._photo_ids)],
                                          [self._user2.user_id])
    timestamp = time.time()

    episode_id = Episode.ConstructEpisodeId(timestamp, self._device_ids[0], 100)

    ep_id, ph_ids = self._tester.UploadEpisode(self._cookie, {}, [self._CreatePhotoDict(self._cookie)])
    new_ep_ids = self._tester.ShareExisting(self._cookie, vp_id, [(ep_id, ph_ids)])

    self._tester.Unshare(self._cookie, vp_id,
                         [(ep_ids[0], self._photo_ids), (new_ep_ids[0], ph_ids)])

  def testDefaultViewpointUnshare(self):
    """Unshare photos from default viewpoint."""
    self._tester.SavePhotos(self._cookie2, [(self._new_ep_id, self._photo_ids)])
    self._tester.Unshare(self._cookie, self._new_vp_id, [(self._new_ep_id, self._photo_ids)])

  def testUnshareRemoved(self):
    """Unshare photos which have been removed from default viewpoint."""
    ep_ids = self._tester.SavePhotos(self._cookie2, [(self._new_ep_id, self._photo_ids)])
    self._tester.RemovePhotos(self._cookie2, [(ep_ids[0], self._photo_ids[:1])])
    self._tester.Unshare(self._cookie, self._new_vp_id, [(self._new_ep_id, self._photo_ids)])

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    new_vp_id2, new_ep_ids2 = self._tester.ShareNew(self._cookie2,
                                                    [(self._new_ep_id, self._photo_ids)],
                                                    [self._user3.user_id])

    self._tester.RemoveViewpoint(self._cookie2, self._new_vp_id)
    self._tester.Unshare(self._cookie,
                         self._new_vp_id,
                         [(self._new_ep_id, self._photo_ids[:1]),
                          (self._new_ep_id, self._photo_ids[1:])])


def _TestUnshare(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test unshare
  service API call.

  Limitations: No error checking, no unshare limit checking.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)
  unshares_dict = {}

  def _Unshare(ep_dicts):
    """Recursively validates all photos that were unshared."""
    for ep_dict in ep_dicts:
      episode = validator.GetModelObject(Episode, ep_dict['episode_id'])
      unshared_photo_ids = unshares_dict.get(episode.viewpoint_id, {}).get(episode.episode_id, [])
      for ph_id in ep_dict['photo_ids']:
        # Validate that each unshared post has UNSHARED label added to it.
        key = DBKey(ep_dict['episode_id'], ph_id)
        post = validator.GetModelObject(Post, key, must_exist=False)
        if post is not None and Post.UNSHARED not in post.labels:
          validator.ValidateUpdateDBObject(Post,
                                           episode_id=ep_dict['episode_id'],
                                           photo_id=ph_id,
                                           labels=post.labels.union([Post.UNSHARED, Post.REMOVED]))
          if post.photo_id not in unshared_photo_ids:
            unshared_photo_ids.append(post.photo_id)

      if len(unshared_photo_ids) > 0:
        unshares_dict.setdefault(episode.viewpoint_id, {})[episode.episode_id] = unshared_photo_ids

        predicate = lambda e: e.parent_ep_id == episode.episode_id
        child_episodes = validator.QueryModelObjects(Episode, predicate=predicate)
        if len(child_episodes) > 0:
          _Unshare([{'episode_id': ep.episode_id,
                     'photo_ids': ep_dict['photo_ids']}
                    for ep in child_episodes])

  # Send unshare request.
  actual_dict = tester.SendRequest('unshare', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # Recursively validate the unshared photos.
  _Unshare(request_dict['episodes'])

  # Validate activity and notifications for the unshare.
  for viewpoint_id in sorted(unshares_dict.keys()):
    viewpoint = validator.GetModelObject(Viewpoint, viewpoint_id)
    if not viewpoint.IsDefault():
      viewpoint_changed = validator.ValidateCoverPhoto(viewpoint_id, unshare_ep_dicts=unshares_dict[viewpoint_id])
    else:
      viewpoint_changed = False

    # Validate that viewpoint_id is appended to activity_id for any derived viewpoints that are unshared.
    activity_id = request_dict['activity']['activity_id']
    if request_dict['viewpoint_id'] != viewpoint_id:
      truncated_ts, act_device_id, (client_id, server_id) = Activity.DeconstructActivityId(activity_id)
      activity_id = Activity.ConstructActivityId(truncated_ts, act_device_id, (client_id, viewpoint_id))

    ep_dicts = unshares_dict[viewpoint_id]
    activity_dict = {'name': 'unshare',
                     'activity_id': activity_id,
                     'timestamp': request_dict['activity']['timestamp'],
                     'episodes': [{'episode_id': episode_id,
                                   'photo_ids': photo_ids}
                                  for episode_id, photo_ids in ep_dicts.items()]}

    invalidate = {'episodes': [{'episode_id': episode_id,
                                'get_attributes': True,
                                'get_photos': True}
                               for episode_id in ep_dicts.keys()]}
    if viewpoint_changed:
      invalidate['viewpoints'] = [{'viewpoint_id': viewpoint_id,
                                   'get_attributes': True}]

    validator.ValidateFollowerNotifications(viewpoint_id, activity_dict, op_dict, invalidate, sends_alert=True)
    validator.ValidateViewpointAccounting(viewpoint_id)

  tester._CompareResponseDicts('unshare', user_id, request_dict, {}, actual_dict)
  return actual_dict
