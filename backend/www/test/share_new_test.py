# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test photo sharing to a newly created viewpoint.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import mock
import time

from copy import deepcopy
from viewfinder.backend.base import util
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.versions import Version
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.www.test import service_base_test


class ShareNewTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(ShareNewTestCase, self).setUp()
    self._CreateSimpleTestAssets()
    self._CreateSimpleContacts()

  def testShare(self):
    """Share a single photo with two other users."""
    vp_dict = self._CreateViewpointDict(self._cookie)
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids[:1])],
                          [self._user2.user_id, self._user3.user_id],
                          **vp_dict)
    viewpoint = self._RunAsync(Viewpoint.Query, self._client, vp_dict['viewpoint_id'], col_names=None)
    self.assertEqual(viewpoint.cover_photo['photo_id'], self._photo_ids[0])

  def testInvalidShare(self):
    """ERROR: Try to share episode from viewpoint that is not followed."""
    self.assertRaisesHttpError(403, self._tester.ShareNew, self._cookie2,
                               [(self._episode_id, self._photo_ids[:1])],
                               [self._user3.user_id])

  def testInvalidOverrides(self):
    """Try to override user_id, device_id, sharing_user_id, etc."""
    for attr in ['user_id', 'device_id', 'sharing_user_id']:
      self.assertRaisesHttpError(400, self._tester.ShareNew, self._cookie,
                                 [(self._episode_id, self._photo_ids)],
                                 [{'user_id': self._user2.user_id}],
                                 **self._CreateViewpointDict(self._cookie, **{attr: 100}))

  def testViewpointAttributes(self):
    """Set all possible attributes, then as few attributes as possible."""
    # CreateViewpointDict already sets most of the attributes.
    vp_dict = self._CreateViewpointDict(self._cookie)
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)],
                          [{'user_id': self._user2.user_id}], **vp_dict)

    viewpoint_id = Viewpoint.ConstructViewpointId(self._device_ids[0], self._test_id)
    self._test_id += 1
    self._tester.ShareNew(self._cookie, [], [], viewpoint_id=viewpoint_id, type=Viewpoint.EVENT)
    viewpoint = self._RunAsync(Viewpoint.Query, self._client, vp_dict['viewpoint_id'], col_names=None)
    self.assertEqual(viewpoint.cover_photo['photo_id'], self._photo_ids[0])

  def testShareMultiple(self):
    """Share two photos with two other users."""
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)],
                          [self._user2.user_id, self._user3.user_id],
                          **self._CreateViewpointDict(self._cookie))

  # Artificially lower limit on followers for test.
  @mock.patch.object(Viewpoint, 'MAX_FOLLOWERS', 2)
  def testShareMultipleTooMany(self):
    """Share two photos with two other users which exceeds too many followers."""
    # Create viewpoint with two followers in addition to the one follower added for the creator and exepct
    #  that it will fail.
    self.assertRaisesHttpError(403, self._tester.ShareNew, self._cookie,
                               [(self._episode_id, self._photo_ids)],
                               [self._user2.user_id, self._user3.user_id])

  def testSeriallyShare(self):
    """Share photos from originator to user2, and from user2 to user3."""
    vp_id, ep_ids = self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)],
                                          [self._user2.user_id],
                                          **self._CreateViewpointDict(self._cookie))

    self._tester.ShareNew(self._cookie2, [(ep_ids[0], self._photo_ids)],
                          [self._user3.user_id],
                          **self._CreateViewpointDict(self._cookie2))

  def testMultipleEpisodes(self):
    """Share photos to multiple episodes in the new viewpoint."""
    vp_dict = self._CreateViewpointDict(self._cookie)
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids[:1]),
                                         (self._episode_id, self._photo_ids[1:]),
                                         (self._episode_id, self._photo_ids)],
                          [self._user2.user_id, self._user3.user_id],
                          **vp_dict)
    viewpoint = self._RunAsync(Viewpoint.Query, self._client, vp_dict['viewpoint_id'], col_names=None)
    self.assertEqual(viewpoint.cover_photo['photo_id'], self._photo_ids[0])

  def testShareToSameEpisode(self):
    """Share multiple photos to same target episode in new viewpoint."""
    timestamp = time.time()
    new_episode_id = Episode.ConstructEpisodeId(timestamp, self._device_ids[0], self._test_id)
    self._test_id += 1
    share_dict1 = {'existing_episode_id': self._episode_id,
                   'new_episode_id': new_episode_id,
                   'photo_ids': self._photo_ids[:1]}
    share_dict2 = {'existing_episode_id': self._episode_id,
                   'new_episode_id': new_episode_id,
                   'photo_ids': self._photo_ids[1:]}

    self._tester.ShareNew(self._cookie, [share_dict1, share_dict2], [self._user2.user_id])

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    self._tester.ShareNew(self._cookie,
                          [(self._episode_id, self._photo_ids)],
                          ['Local:identity1',
                           {'identity': 'Local:identity2',
                            'name': 'Andy Kimball'},
                           {'identity': 'Email:me@emailscrubbed.com',
                            'name': 'Someone'},
                           'Phone:+14251234567',
                           'Email:spam@emailscrubbed.com'])

  def testShareSamePhotoSameEpisode(self):
    """ERROR: Try to share the same photo multiple times to same episode."""
    timestamp = time.time()
    new_episode_id = Episode.ConstructEpisodeId(timestamp, self._device_ids[0], self._test_id)
    self._test_id += 1
    share_dict = {'existing_episode_id': self._episode_id,
                  'new_episode_id': new_episode_id,
                  'timestamp': timestamp,
                  'photo_ids': self._photo_ids}
    self.assertRaisesHttpError(400, self._tester.ShareNew, self._cookie, [share_dict, share_dict], [])

  def testInvalidLabel(self):
    """ERROR: Try to set an invalid label in the viewpoint."""
    self.assertRaisesHttpError(400, self._tester.ShareNew, self._cookie,
                               [(self._episode_id, self._photo_ids)],
                               [{'user_id': self._user2.user_id}],
                               **self._CreateViewpointDict(self._cookie, labels=['UNKNOWN']))

  def testWrongDeviceIds(self):
    """ERROR: Try to create a viewpoint and episode using device ids that
    are different than the ones in the user cookies.
    """
    self.assertRaisesHttpError(403, self._tester.ShareNew, self._cookie,
                               [(self._episode_id, self._photo_ids)],
                               [{'user_id': self._user2.user_id}],
                               **self._CreateViewpointDict(self._cookie2))

    self.assertRaisesHttpError(403, self._tester.ShareNew, self._cookie,
                               [self._tester.CreateCopyDict(self._cookie2, self._episode_id, self._photo_ids)],
                               [{'user_id': self._user2.user_id}])

  def testProspectiveShare(self):
    """Verify that sharing with an unrecognized contact results in the
    creation of a prospective user that is added as a follower.
    """
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)],
                          ['Local:identity1'],
                          **self._CreateViewpointDict(self._cookie))

  def testMultipleProspectiveShares(self):
    """Verify that sharing multiple unrecognized contacts results in
    multiple prospective users added as followers.
    """
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)],
                          ['Local:identity1',
                           {'identity': 'Local:identity2',
                            'name': 'Andy Kimball'},
                           {'identity': 'Email:me@emailscrubbed.com',
                            'name': 'Someone'},
                           'Phone:+14251234567',
                           'Email:spam@emailscrubbed.com'])

  def testMixedProspectiveShares(self):
    """Verify that sharing unrecognized contacts with existing users
    adds the correct followers.
    """
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)],
                          ['Local:identity1',
                           {'identity': 'Local:identity2',
                            'name': 'Andy Kimball'},
                           self._user2.user_id,
                           self._user3.user_id])

  def testSequenceProspectiveShares(self):
    """Verify that sharing to the same unrecognized contact in sequence
    results in the creation of a single prospective user.
    """
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)],
                          ['Local:identity1'])
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)],
                          ['Local:identity1'])

  def testProspectiveUnboundIdentity(self):
    """Add a contact as a follower using an identity that exists, but is not bound to a user."""
    # Create the unbound identity and add it to the model.
    identity_key = 'Email:new.user@emailscrubbed.com'
    self._UpdateOrAllocateDBObject(Identity, key=identity_key)

    # Now use it as as target contact in a share_new operation.
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)],
                          [identity_key])

  def testShareNoEpisodes(self):
    """Verify that sharing an empty episode list works."""
    self._tester.ShareNew(self._cookie, [], [self._user2.user_id],
                          **self._CreateViewpointDict(self._cookie))

  def testShareNoContacts(self):
    """Verify that sharing an empty contact list works."""
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)], [],
                          **self._CreateViewpointDict(self._cookie))

  def testShareMultipleEpisodes(self):
    """Verify that sharing photos from multiple episodes works."""
    vp_dict = self._CreateViewpointDict(self._cookie)
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids),
                                         (self._episode_id2, self._photo_ids2)],
                          [self._user2.user_id, self._user3.user_id],
                          **vp_dict)
    viewpoint = self._RunAsync(Viewpoint.Query, self._client, vp_dict['viewpoint_id'], col_names=None)
    self.assertEqual(viewpoint.cover_photo['photo_id'], self._photo_ids[0])

  def testShareWithSelf(self):
    """Share into a new viewpoint, with self as a follower."""
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)],
                          [self._user.user_id])

  def testShareWithDuplicateUsers(self):
    """Share into a new viewpoint, with duplicate followers."""
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)],
                          [self._user2.user_id, self._user2.user_id],
                          **self._CreateViewpointDict(self._cookie))

  def testMultipleSharesToSameUser(self):
    """Share photo from originator to user2, then another photo to user2."""
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids[:1])],
                          [self._user2.user_id])

    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids[1:])],
                          [self._user2.user_id])

  def testMultiplePathsToSameUser(self):
    """Share photo from originator to user2, then to user3. Then share a
    different photo directly from user1 to user3"""
    vp_id, ep_ids = self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids[:1])],
                                          [self._user2.user_id])

    self._tester.ShareNew(self._cookie2, [(ep_ids[0], self._photo_ids[:1])],
                          [self._user3.user_id])

    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids[1:])],
                          [self._user3.user_id])

  def testOverlappingShares(self):
    """Share 2 photos from same episode to user2, then 2 photos (1 of which
    is in first set) with user3.
    """
    episode_id, photo_ids = self._UploadOneEpisode(self._cookie, 3)

    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids[:2])],
                          [self._user2.user_id])

    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids[1:])],
                          [self._user3.user_id])

  def testRepeatedShareNew(self):
    """Test sending the same share_new request in two different operations and observe that it succeeds.
    A client may do this if it crashes while sending a share_new request.
    """
    vp_id, _ = self._tester.ShareNew(self._cookie,
                                     [(self._episode_id, self._photo_ids[1:])],
                                     [self._user2.user_id])
    vp_dict = {'viewpoint_id': vp_id}
    vp_id2, _ = self._tester.ShareNew(self._cookie,
                                     [(self._episode_id, self._photo_ids)],
                                     [self._user2.user_id],
                                     **vp_dict)
    self.assertEqual(vp_id, vp_id2)

  def testShareWithCoverPhoto(self):
    """Share photos and specify one of them as the cover_photo."""
    update_vp_dict = {'cover_photo': (self._episode_id, self._photo_ids[0])}
    vp_dict = self._CreateViewpointDict(self._cookie, **update_vp_dict)
    self._tester.ShareNew(self._cookie,
                          [(self._episode_id, self._photo_ids)],
                          [self._user2.user_id, self._user3.user_id],
                          **vp_dict)
    viewpoint = self._RunAsync(Viewpoint.Query, self._client, vp_dict['viewpoint_id'], col_names=None)
    self.assertEqual(viewpoint.cover_photo['photo_id'], self._photo_ids[0])

  def testShareWithMissingCoverPhoto(self):
    """ERROR: try sharing with a cover photo specified that is not being shared and expect failure."""
    update_vp_dict = {'cover_photo': (self._episode_id, self._photo_ids[1])}
    self.assertRaisesHttpError(400,
                               self._tester.ShareNew,
                               self._cookie,
                               [(self._episode_id, self._photo_ids[:1])],
                               [self._user2.user_id, self._user3.user_id],
                               **self._CreateViewpointDict(self._cookie, **update_vp_dict))

  def testShareWithBlankCoverPhotoId(self):
    """ERROR: Try to share a cover photo that has a blank photo_id."""
    update_vp_dict = {'cover_photo': (self._episode_id, '')}
    self.assertRaisesHttpError(400,
                               self._tester.ShareNew,
                               self._cookie,
                               [(self._episode_id, self._photo_ids[:1])],
                               [self._user2.user_id, self._user3.user_id],
                               **self._CreateViewpointDict(self._cookie, **update_vp_dict))

  def testShareInvalidTypes(self):
    """ERROR: Try to create a default and system viewpoint."""
    self.assertRaisesHttpError(400,
                               self._tester.ShareNew,
                               self._cookie,
                               [(self._episode_id, self._photo_ids)],
                               [self._user2.user_id],
                               **self._CreateViewpointDict(self._cookie, type=Viewpoint.DEFAULT))

    self.assertRaisesHttpError(400,
                               self._tester.ShareNew,
                               self._cookie,
                               [(self._episode_id, self._photo_ids)],
                               [self._user2.user_id],
                               **self._CreateViewpointDict(self._cookie, type=Viewpoint.SYSTEM))


def SortShareEpDicts(ep_dicts):
  """Cover_photo selection depends on episode/photo order in share_new and share_existing.
  This sorts into an order that's compatible with cover photo selection in the original mobile client.
  Using this will allow the test model to select a cover_photo consistent with what the implementation does.
  """
  ep_dicts.sort(key=lambda episode: episode['new_episode_id'], reverse=True)
  for episode in ep_dicts:
    episode['photo_ids'].sort()


def _TestShareNew(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test share_new
  service API call.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)
  vp_dict = request_dict['viewpoint']

  # Send share_new request.
  actual_dict = tester.SendRequest('share_new', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # share_new is no-op if viewpoint already exists.
  if validator.GetModelObject(Viewpoint, vp_dict['viewpoint_id'], must_exist=False) is None:
    # Validate all prospective users were created.
    users = validator.ValidateCreateProspectiveUsers(op_dict, request_dict['contacts'])

    # Validate creation of the new viewpoint and follower.
    vp_dict['user_id'] = user_id
    vp_dict['timestamp'] = op_dict['op_timestamp']

    assert vp_dict['type'] == Viewpoint.EVENT, vp_dict
    if vp_dict.get('cover_photo', None) is None:
      # Heuristically select photo if it wasn't set in the vp_dict.
      # First episode and first photo are selected based on order of request_dict['episodes'].
      vp_dict['cover_photo'] = None
      for episode in request_dict['episodes']:
        for photo_id in episode['photo_ids']:
          vp_dict['cover_photo'] = {'episode_id': episode['new_episode_id'], 'photo_id': photo_id}
          break
        if vp_dict['cover_photo'] is not None:
          break

    validator.ValidateCreateDBObject(Viewpoint, **vp_dict)

    validator.ValidateFollower(user_id=user_id,
                               viewpoint_id=vp_dict['viewpoint_id'],
                               timestamp=op_dict['op_timestamp'],
                               labels=Follower.PERMISSION_LABELS,
                               last_updated=op_dict['op_timestamp'])

    for other_user in users:
      if other_user.user_id != user_id:
        validator.ValidateFollower(user_id=other_user.user_id,
                                   viewpoint_id=vp_dict['viewpoint_id'],
                                   timestamp=op_dict['op_timestamp'],
                                   labels=[Follower.CONTRIBUTE],
                                   last_updated=op_dict['op_timestamp'],
                                   adding_user_id=user_id,
                                   viewed_seq=0)

    # Validate all followers are friends.
    new_follower_ids = list(set([user_id] + [u.user_id for u in users]))
    validator.ValidateFriendsInGroup(new_follower_ids)

    # Validate all episodes and posts are created.
    validator.ValidateCopyEpisodes(op_dict, vp_dict['viewpoint_id'], request_dict['episodes'])

    # Validate activity and notifications for the share.
    activity_dict = {'name': 'share_new',
                     'activity_id': request_dict['activity']['activity_id'],
                     'timestamp': request_dict['activity']['timestamp'],
                     'episodes': [{'episode_id': ep_dict['new_episode_id'],
                                   'photo_ids': ep_dict['photo_ids']}
                                  for ep_dict in request_dict['episodes']],
                     'follower_ids': [u.user_id for u in users]}

    invalidate = validator.CreateViewpointInvalidation(vp_dict['viewpoint_id'])
    validator.ValidateFollowerNotifications(vp_dict['viewpoint_id'],
                                            activity_dict,
                                            op_dict,
                                            invalidate=invalidate,
                                            sends_alert=True)

    validator.ValidateUpdateDBObject(Viewpoint,
                                     viewpoint_id=vp_dict['viewpoint_id'],
                                     last_updated=vp_dict['timestamp'])

  validator.ValidateViewpointAccounting(vp_dict['viewpoint_id'])
  tester._CompareResponseDicts('share_new', user_id, request_dict, {}, actual_dict)
  return actual_dict
