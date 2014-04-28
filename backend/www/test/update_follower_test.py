# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests update_follower method.
"""

__author__ = ['andy@emailscrubbed.com (Andy Kimball)']

import mock

from copy import deepcopy
from viewfinder.backend.base.util import SetIfNotNone
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.services.apns import TestService
from viewfinder.backend.www.test import service_base_test


class UpdateFollowerTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(UpdateFollowerTestCase, self).setUp()
    self._CreateSimpleTestAssets()
    self._new_vp_id, ep_id = self._ShareSimpleTestAssets([self._user2.user_id])

    self._all_labels_sans_removed = Follower.ALL_LABELS[:]
    self._all_labels_sans_removed.remove(Follower.REMOVED)
    self._all_labels_sans_removed.remove(Follower.UNREVIVABLE)

  def testUpdateFollower(self):
    """Update existing followers."""
    # Update follower of default viewpoint.
    self._tester.UpdateFollower(self._cookie,
                                self._user.private_vp_id,
                                labels=self._all_labels_sans_removed)

    # Update shared viewpoint for target user.
    self._tester.UpdateFollower(self._cookie2,
                                self._new_vp_id,
                                labels=[Follower.CONTRIBUTE])

    # Update shared viewpoint for sharing user.
    self._tester.UpdateFollower(self._cookie, self._new_vp_id, labels=self._all_labels_sans_removed)

  def testViewPermissions(self):
    """Update follower attributes with only viewing permission."""
    # Only view permission should be required to make these updates.
    self._UpdateOrAllocateDBObject(Follower, user_id=self._user.user_id,
                                   viewpoint_id=self._new_vp_id, labels=[])

    self._tester.UpdateFollower(self._cookie, self._new_vp_id, viewed_seq=100)
    self._tester.UpdateFollower(self._cookie, self._new_vp_id, viewed_seq=101, labels=[])
    self._tester.UpdateFollower(self._cookie, self._new_vp_id, labels=[Follower.PERSONAL])
    self._tester.UpdateFollower(self._cookie, self._new_vp_id, labels=[Follower.HIDDEN])

  def testUpdateFollowerFailure(self):
    """Error: Update follower with REMOVED labels should fail because it's not allowed."""
    self._UpdateOrAllocateDBObject(Follower, user_id=self._user.user_id,
                                   viewpoint_id=self._new_vp_id, labels=[])

    self.assertRaisesHttpError(403,
                               self._tester.UpdateFollower,
                               self._cookie,
                               self._new_vp_id,
                               labels=[Follower.REMOVED])

  def testRatchetViewedSeq(self):
    """Verify that attempt to decrease viewed_seq is ignored."""
    self._tester.UpdateFollower(self._cookie, self._new_vp_id, viewed_seq=2)
    self._tester.UpdateFollower(self._cookie, self._new_vp_id, viewed_seq=1)

  def testViewedSeqTooHigh(self):
    """Verify that attempt to set viewed_seq > update_seq is not allowed."""
    self._tester.UpdateFollower(self._cookie, self._new_vp_id, viewed_seq=1000)

    follower = self._RunAsync(Follower.Query, self._client, self._user2.user_id, self._new_vp_id, None)
    self.assertEqual(follower.viewed_seq, 0)
    self._tester.UpdateFollower(self._cookie2, self._new_vp_id, viewed_seq=1000)
    follower = self._RunAsync(Follower.Query, self._client, self._user2.user_id, self._new_vp_id, None)
    self.assertEqual(follower.viewed_seq, 1)

  def testNoOpUpdate(self):
    """Update follower attribute to same value as it had before."""
    follower = self._RunAsync(Follower.Query, self._client, self._user.user_id, self._new_vp_id, None)
    self._tester.UpdateFollower(self._cookie, self._new_vp_id, labels=list(follower.labels))
    self._tester.UpdateFollower(self._cookie, self._new_vp_id, labels=list(follower.labels))

  def testRemoveLabels(self):
    """Remove labels from the viewpoint after setting them there."""
    self._tester.UpdateFollower(self._cookie, self._new_vp_id, labels=self._all_labels_sans_removed)
    self._tester.UpdateFollower(self._cookie, self._new_vp_id, labels=Follower.PERMISSION_LABELS)

  def testSetRemovedLabel(self):
    """Set the REMOVED label when it's already set."""
    self._tester.RemoveViewpoint(self._cookie, self._new_vp_id)
    self._tester.UpdateFollower(self._cookie, self._new_vp_id, labels=Follower.PERMISSION_LABELS + [Follower.REMOVED])

  def testMuteViewpoint(self):
    """Test the MUTED label on a follower."""
    # Validate alerts directly in this test rather than relying on cleanup validation.
    self._skip_validation_for = ['Alerts']

    # Get push token for user #2.
    device = self._RunAsync(Device.Query, self._client, self._user2.user_id, self._device_ids[1], None)
    push_token = device.push_token[len(TestService.PREFIX):]

    # ------------------------------
    # Test that APNS and email alerts are suppressed for muted viewpoint.
    # ------------------------------
    self._tester.UpdateFollower(self._cookie2,
                                self._new_vp_id,
                                labels=[Follower.CONTRIBUTE, Follower.MUTED])
    self._tester.ShareExisting(self._cookie, self._new_vp_id, [(self._episode_id2, self._photo_ids2)])
    self.assertEqual(len(TestService.Instance().GetNotifications(push_token)), 1)

    # ------------------------------
    # Un-mute and test that alerts are again sent.
    # ------------------------------
    self._tester.UpdateFollower(self._cookie2,
                                self._new_vp_id,
                                labels=[Follower.CONTRIBUTE])
    self._tester.PostComment(self._cookie, self._new_vp_id, 'Hi')
    self.assertEqual(len(TestService.Instance().GetNotifications(push_token)), 2)

  def testAutoSave(self):
    """Test enabling auto-save, then disabling it."""
    self._tester.UpdateFollower(self._cookie2, self._new_vp_id, labels=[Follower.CONTRIBUTE, Follower.AUTOSAVE])
    self._tester.ShareExisting(self._cookie, self._new_vp_id, [(self._episode_id2, self._photo_ids2[:1])])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 1)

    self._tester.UpdateFollower(self._cookie2, self._new_vp_id, labels=[Follower.CONTRIBUTE])
    self._tester.ShareExisting(self._cookie, self._new_vp_id, [(self._episode_id2, self._photo_ids2[1:])])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 1)


  def testAdditionalAttributes(self):
    """Try to update attributes which not available for update."""
    for attr in ['sharing_user_id', 'foo', 'title']:
      self.assertRaisesHttpError(400,
                                 self._tester.UpdateFollower,
                                 self._cookie,
                                 self._new_vp_id,
                                 attr=attr)

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    self._tester.UpdateFollower(self._cookie, self._new_vp_id, viewed_seq=2, labels=self._all_labels_sans_removed)

  def testInvalidViewpoint(self):
    """ERROR: Try to update a follower on a viewpoint that does not exist."""
    self.assertRaisesHttpError(403, self._tester.UpdateFollower, self._cookie, 'vunknown')

  def testViewpointNotFollowed(self):
    """ERROR: Try to update a viewpoint that is not followed."""
    self.assertRaisesHttpError(403, self._tester.UpdateFollower, self._cookie3, self._new_vp_id)

  def testClearPermissionLabels(self):
    """ERROR: Try to clear follower permission labels."""
    self.assertRaisesHttpError(403,
                               self._tester.UpdateFollower,
                               self._cookie,
                               self._new_vp_id,
                               labels=[])


def _ValidateUpdateFollower(tester, user_cookie, op_dict, foll_dict):
  """Validates the results of a call to update_follower. Also used to validate update_viewpoint
  in the case where only follower attributes are modified (backwards-compatibility case).
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  viewpoint_id = foll_dict['viewpoint_id']

  # Validate that viewed_seq value ratchets upwards.
  has_viewed_seq = 'viewed_seq' in foll_dict
  if has_viewed_seq:
    update_seq = validator.GetModelObject(Viewpoint, viewpoint_id).update_seq
    old_viewed_seq = validator.GetModelObject(Follower, DBKey(user_id, viewpoint_id)).viewed_seq

    if foll_dict['viewed_seq'] > update_seq:
      foll_dict['viewed_seq'] = update_seq

    if foll_dict['viewed_seq'] < old_viewed_seq:
      del foll_dict['viewed_seq']

  # Validate Follower object.
  foll_dict['user_id'] = user_id
  follower = validator.ValidateUpdateDBObject(Follower, **foll_dict)

  # Validate notifications for the update.
  invalidate = {'viewpoints': [{'viewpoint_id': viewpoint_id,
                                'get_attributes': True}]}

  if has_viewed_seq and 'labels' not in foll_dict:
    # Only viewed_seq attribute was updated, and it will be inlined in notification.
    invalidate = None

  # Only follower attributes were updated, so validate single notification to calling user.
  validator.ValidateNotification('update_follower',
                                 user_id,
                                 op_dict,
                                 invalidate,
                                 viewpoint_id=viewpoint_id,
                                 seq_num_pair=(None, follower.viewed_seq if has_viewed_seq else None))


def _TestUpdateFollower(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test update_follower service API call."""
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  # Send update_follower request.
  actual_dict = tester.SendRequest('update_follower', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # Validate results.
  _ValidateUpdateFollower(tester, user_cookie, op_dict, request_dict['follower'])

  tester._CompareResponseDicts('update_follower', user_id, request_dict, {}, actual_dict)
  return actual_dict
