# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests update_viewpoint method.
"""

__author__ = ['andy@emailscrubbed.com (Andy Kimball)']

import mock

from copy import deepcopy
from viewfinder.backend.base import util
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.www.test import service_base_test


class UpdateViewpointTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(UpdateViewpointTestCase, self).setUp()
    self._CreateSimpleTestAssets()
    self._new_vp_id, self._new_ep_id = self._ShareSimpleTestAssets([self._user2.user_id])

    # Turn off alert validation, since several tests update title, which changes alert text.
    self._skip_validation_for = ['Alerts']

    self._all_labels_sans_removed = Follower.ALL_LABELS[:]
    self._all_labels_sans_removed.remove(Follower.REMOVED)

  def testUpdateViewpoint(self):
    """Update existing viewpoints."""
    # Update default viewpoint.
    self._tester.UpdateViewpoint(self._cookie,
                                 self._user.private_vp_id,
                                 title='a new title',
                                 description='a new description',
                                 name='newname')

    # Update shared viewpoint for target user.
    self._tester.UpdateViewpoint(self._cookie2,
                                 self._new_vp_id,
                                 cover_photo={'episode_id': self._new_ep_id,
                                              'photo_id': self._photo_ids[1]})

    # Update shared viewpoint for sharing user.
    self._tester.UpdateViewpoint(self._cookie,
                                 self._new_vp_id,
                                 title='a new title')

  def testUpdateAttributesWithHistory(self):
    """Update viewpoint attributes for which we keep previous values."""
    self._tester.UpdateViewpoint(self._cookie,
                                 self._new_vp_id,
                                 title='a new title',
                                 cover_photo={'episode_id': self._new_ep_id,
                                              'photo_id': self._photo_ids[1]})

    response_dict = self._tester.QueryNotifications(self._cookie, 1, None, scan_forward=False)
    activity = response_dict['notifications'][0]['inline']['activity']
    self.assertEqual(activity['update_viewpoint']['prev_title'], 'Title 7')
    self.assertEqual(activity['update_viewpoint']['prev_cover_photo'],
                     {'photo_id': self._photo_ids[0], 'episode_id': self._new_ep_id})

  def testUpdateFollower(self):
    """Update follower attributes that should not trigger activity creation."""
    # Only view permission should be required to make these updates.
    self._UpdateOrAllocateDBObject(Follower, user_id=self._user.user_id,
                                   viewpoint_id=self._new_vp_id, labels=[])

    self._tester.UpdateViewpoint(self._cookie, self._new_vp_id, viewed_seq=100)
    self._tester.UpdateViewpoint(self._cookie, self._new_vp_id, viewed_seq=101, labels=[])
    self._tester.UpdateViewpoint(self._cookie, self._new_vp_id, labels=[Follower.PERSONAL])
    self._tester.UpdateViewpoint(self._cookie, self._new_vp_id, labels=[Follower.HIDDEN])

  def testNoOpUpdate(self):
    """Update viewpoint attribute to same value as it had before."""
    self._tester.UpdateViewpoint(self._cookie, self._new_vp_id, title='some title')
    self._tester.UpdateViewpoint(self._cookie, self._new_vp_id, title='some title')

  def testAdditionalAttributes(self):
    """Try to update attributes which not available for update."""
    for attr in ['sharing_user_id', 'foo']:
      self.assertRaisesHttpError(400,
                                 self._tester.UpdateViewpoint,
                                 self._cookie,
                                 self._new_vp_id,
                                 attr=attr)

  def testUnrevivable(self):
    """Update a viewpoint with an unrevivable removed follower."""
    self._tester.RemoveFollowers(self._cookie, self._new_vp_id, [self._user2.user_id])
    self._tester.UpdateViewpoint(self._cookie, self._new_vp_id, title='a new title')
    response_dict = self._tester.QueryFollowed(self._cookie2)
    self.assertIn(Follower.REMOVED, response_dict['viewpoints'][0]['labels'])
    self.assertIn(Follower.UNREVIVABLE, response_dict['viewpoints'][0]['labels'])

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    self._tester.RemoveViewpoint(self._cookie2, self._new_vp_id)
    self._tester.UpdateViewpoint(self._cookie,
                                 self._new_vp_id,
                                 title='a new title',
                                 description='a new description',
                                 name='newname',
                                 cover_photo={'episode_id': self._new_ep_id,
                                              'photo_id': self._photo_ids[1]})

  def testEmptyTitle(self):
    """ERROR: Try to update a viewpoint title to the empty string."""
    self.assertRaisesHttpError(400, self._tester.UpdateViewpoint, self._cookie, self._new_vp_id, title='')

  def testInvalidViewpoint(self):
    """ERROR: Try to update a viewpoint that does not exist."""
    self.assertRaisesHttpError(400, self._tester.UpdateViewpoint, self._cookie, 'vunknown', title='some title')

  def testViewpointNotFollowed(self):
    """ERROR: Try to update a viewpoint that is not followed."""
    self.assertRaisesHttpError(403, self._tester.UpdateViewpoint, self._cookie3, self._new_vp_id, title='some title')

  def testUpdateReadOnlyAttribute(self):
    """ERROR: Try to update read-only attribute."""
    self.assertRaisesHttpError(400, self._tester.UpdateViewpoint, self._cookie, self._new_vp_id, type='foobar')

  def testUpdateSeq(self):
    """ERROR: Try to update update_seq attribute."""
    self.assertRaisesHttpError(400, self._tester.UpdateViewpoint, self._cookie, self._new_vp_id, update_seq=100)

  def testUpdateViewpointAndFollower(self):
    """ERROR: Try to update both viewpoint and follower metadata in one call."""
    self.assertRaisesHttpError(400,
                               self._tester.UpdateViewpoint,
                               self._cookie,
                               self._new_vp_id,
                               title='some title',
                               viewed_seq=2)

  def testInvalidCoverPhotos(self):
    """ERROR: Try to add invalid cover photos."""
    # Try to set malformed cover photo.
    self.assertRaisesHttpError(400,
                               self._tester.UpdateViewpoint,
                               self._cookie,
                               self._user.private_vp_id,
                               cover_photo={})

    # Try to set cover photo on library viewpoint.
    self.assertRaisesHttpError(400,
                               self._tester.UpdateViewpoint,
                               self._cookie,
                               self._user.private_vp_id,
                               cover_photo={'episode_id': self._episode_id,
                                            'photo_id': self._photo_ids[1]})

    # Try to set cover photo that does not exist.
    self.assertRaisesHttpError(400,
                               self._tester.UpdateViewpoint,
                               self._cookie,
                               self._new_vp_id,
                               cover_photo={'episode_id': self._new_ep_id,
                                            'photo_id': 'p123'})

    # Try to set unshared cover photo.
    self._tester.Unshare(self._cookie, self._new_vp_id, [(self._new_ep_id, self._photo_ids[:1])])
    self.assertRaisesHttpError(403,
                               self._tester.UpdateViewpoint,
                               self._cookie,
                               self._new_vp_id,
                               cover_photo={'episode_id': self._new_ep_id,
                                            'photo_id': self._photo_ids[0]})

    # Try to set cover photo that is not in the viewpoint.
    self.assertRaisesHttpError(400,
                               self._tester.UpdateViewpoint,
                               self._cookie,
                               self._new_vp_id,
                               cover_photo={'episode_id': self._episode_id,
                                            'photo_id': self._photo_ids[0]})


def _TestUpdateViewpoint(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test update_viewpoint
  service API call.
  """
  from viewfinder.backend.www.test.update_follower_test import _ValidateUpdateFollower
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)
  viewpoint_id = request_dict['viewpoint_id']

  # Send update_viewpoint request.
  actual_dict = tester.SendRequest('update_viewpoint', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # Get previous values for title and cover_photo.
  viewpoint = validator.GetModelObject(Viewpoint, viewpoint_id)
  prev_title = viewpoint.title
  prev_cover_photo = viewpoint.cover_photo

  # Validate case where only follower attributes are specified (uses update_follower code path).
  follower_columns = set(['user_id', 'viewpoint_id', 'labels', 'viewed_seq', 'activity', 'headers'])
  if all(attr in follower_columns for attr in request_dict.keys()):
    # Validate Follower object.
    foll_dict = {'viewpoint_id': request_dict['viewpoint_id']}
    util.SetIfNotNone(foll_dict, 'labels', request_dict.pop('labels', None))
    util.SetIfNotNone(foll_dict, 'viewed_seq', request_dict.pop('viewed_seq', None))
    _ValidateUpdateFollower(tester, user_cookie, op_dict, foll_dict)
  else:
    # Validate Viewpoint object.
    vp_dict = deepcopy(request_dict)
    vp_dict.pop('headers', None)
    vp_dict.pop('labels', None)
    vp_dict.pop('viewed_seq', None)
    vp_dict.pop('activity', None)
    viewpoint = validator.ValidateUpdateDBObject(Viewpoint, **vp_dict)

    # Need to revive before validating the follower, below.  This also happens in
    # validator.ValidateFollowerNotifications(), below.
    validator.ValidateReviveRemovedFollowers(viewpoint_id, op_dict)

    # Validate activity and notifications for the update.
    invalidate = {'viewpoints': [{'viewpoint_id': viewpoint_id,
                                  'get_attributes': True}]}

    # Validate notifications to followers.
    activity_dict = {'name': 'update_viewpoint',
                     'activity_id': request_dict['activity']['activity_id'],
                     'timestamp': request_dict['activity']['timestamp'],
                     'viewpoint_id': viewpoint_id}

    if 'title' in vp_dict and prev_title is not None:
      util.SetIfNotNone(activity_dict, 'prev_title', prev_title)
    if 'cover_photo' in vp_dict and prev_cover_photo is not None:
      util.SetIfNotNone(activity_dict, 'prev_cover_photo', prev_cover_photo)

    validator.ValidateFollowerNotifications(viewpoint_id,
                                            activity_dict,
                                            op_dict,
                                            invalidate)

  tester._CompareResponseDicts('update_viewpoint', user_id, request_dict, {}, actual_dict)
  return actual_dict
