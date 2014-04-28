# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests remove_photos method.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import mock
import time

from copy import deepcopy
from functools import partial
from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.accounting import Accounting
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user import User
from viewfinder.backend.www.test import service_base_test


class RemovePhotosTestCase(service_base_test.ServiceBaseTestCase):
  def testRemovePhotos(self):
    """Remove photos from user's default viewpoint."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 9)
    self._tester.RemovePhotos(self._cookie, [(ep_id, ph_ids[::2])])
    self.assertEqual(self._CountRemovedPhotos(self._cookie), 5)

  def testRemoveMultipleEpisodes(self):
    """Remove photos from multiple episodes."""
    ep_ph_ids_list = self._UploadMultipleEpisodes(self._cookie, 17)
    self._tester.RemovePhotos(self._cookie, ep_ph_ids_list[::2])
    self.assertEqual(self._CountRemovedPhotos(self._cookie), 12)

  def testRemoveDuplicatePhotos(self):
    """Remove the same photos multiple times."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 3)
    self._tester.RemovePhotos(self._cookie, [(ep_id, ph_ids)])
    self._tester.RemovePhotos(self._cookie, [(ep_id, ph_ids)])
    self._tester.RemovePhotos(self._cookie, [(ep_id, ph_ids)])
    self.assertEqual(self._CountRemovedPhotos(self._cookie), 3)

  def testRemoveOverlappingPhotos(self):
    """Remove photos from the same episode in different patterns."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 5)
    self._tester.RemovePhotos(self._cookie, [(ep_id, ph_ids[3:4])])
    self._tester.RemovePhotos(self._cookie, [(ep_id, ph_ids[2:4])])
    self._tester.RemovePhotos(self._cookie, [(ep_id, ph_ids[4:])])
    self.assertEqual(self._CountRemovedPhotos(self._cookie), 3)

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 2)
    self._tester.RemovePhotos(self._cookie, [(ep_id, ph_ids[:1])])
    self._tester.RemovePhotos(self._cookie, [(ep_id, ph_ids)])
    self.assertEqual(self._CountRemovedPhotos(self._cookie), 2)

  def testRemoveNonExistingPhoto(self):
    """ERROR: Remove from an episode without a POST entry."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 3)
    self.assertRaisesHttpError(400, self._tester.RemovePhotos, self._cookie, [(ep_id, ['punknown'])])

  def testRemoveFromNonExistingEpisode(self):
    """ERROR: Remove from a non-existing episode."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 3)
    self.assertRaisesHttpError(400, self._tester.RemovePhotos, self._cookie, [('eunknown', ph_ids)])

  def testRemovePhotosAccess(self):
    """ERROR: Ensure that only photos visible to the user can be removed."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 1)
    self.assertRaisesHttpError(403, self._tester.RemovePhotos, self._cookie2, [(ep_id, ph_ids)])

    vp_id, new_ep_ids = self._tester.ShareNew(self._cookie,
                                              [(ep_id, ph_ids)],
                                              [self._user2.user_id])
    self.assertRaisesHttpError(403, self._tester.RemovePhotos, self._cookie3, [(new_ep_ids[0], ph_ids)])

  def testRemoveFromSharedViewpoint(self):
    """ERROR: Try to remove from a shared viewpoint."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 3)
    vp_id, new_ep_ids = self._tester.ShareNew(self._cookie,
                                              [(ep_id, ph_ids)],
                                              [self._user2.user_id])
    self.assertRaisesHttpError(403, self._tester.RemovePhotos, self._cookie, [(new_ep_ids[0], ph_ids)])

  def _CountRemovedPhotos(self, user_cookie):
    """Returns count of all removed photos in the user's default viewpoint."""
    user_id, device_id = self._tester.GetIdsFromCookie(user_cookie)
    user = self._RunAsync(User.Query, self._client, user_id, None)
    vp_select = self._tester.CreateViewpointSelection(user.private_vp_id)
    vp_response_dict = self._tester.QueryViewpoints(user_cookie, [vp_select])

    count = 0
    for ep_dict in vp_response_dict['viewpoints'][0]['episodes']:
      ep_select = self._tester.CreateEpisodeSelection(ep_dict['episode_id'])
      ep_response_dict = self._tester.QueryEpisodes(user_cookie, [ep_select])
      for ph_dict in ep_response_dict['episodes'][0]['photos']:
        if Post.REMOVED in ph_dict.get('labels', []):
          count += 1

    return count


def _TestRemovePhotos(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test remove_photos service API call."""
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)
  user = validator.GetModelObject(User, user_id)

  # Send remove_photos request.
  actual_dict = tester.SendRequest('remove_photos', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # Validate POST objects.
  for request_ep in request_dict['episodes']:
    episode_id = request_ep['episode_id']
    episode = validator.GetModelObject(Episode, episode_id)

    for photo_id in request_ep['photo_ids']:
      post = validator.GetModelObject(Post, DBKey(episode_id, photo_id))

      if not post.IsRemoved():
        # Validate that REMOVED label was added.
        validator.ValidateUpdateDBObject(Post,
                                         episode_id=episode_id,
                                         photo_id=photo_id,
                                         labels=post.labels.combine().union([Post.REMOVED]))

  # Validate notification for the remove.
  invalidate = {'episodes': [{'episode_id': request_ep['episode_id'], 'get_photos': True}
                             for request_ep in request_dict['episodes']]}
  validator.ValidateNotification('remove_photos', user_id, op_dict, invalidate)

  validator.ValidateViewpointAccounting(user.private_vp_id)
  tester._CompareResponseDicts('remove_photos', user_id, request_dict, {}, actual_dict)
  return actual_dict
