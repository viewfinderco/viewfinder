# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests hide_photos method.
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
from viewfinder.backend.db.user_post import UserPost
from viewfinder.backend.www.test import service_base_test


class HidePhotosTestCase(service_base_test.ServiceBaseTestCase):
  def testHidePhotos(self):
    """Hide photos from default and shared viewpoints."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 9)
    self._tester.HidePhotos(self._cookie, [(ep_id, ph_ids[::2])])

    vp_id, new_ep_ids = self._tester.ShareNew(self._cookie, [(ep_id, ph_ids)],
                                              [self._user2.user_id])
    self._tester.HidePhotos(self._cookie, [(new_ep_ids[0], ph_ids[::2])])

  def testHideMultipleEpisodes(self):
    """Hide photos from multiple episodes."""
    ep_ph_ids_list = self._UploadMultipleEpisodes(self._cookie, 17)
    vp_id, new_ep_ids = self._tester.ShareNew(self._cookie, ep_ph_ids_list,
                                              [self._user3.user_id])

    # Build list of (ep_id, ph_ids) pairs from subset of uploaded episodes and photos.
    ep_ph_ids_list2 = [(new_ep_id, ph_ids[::3])
                       for new_ep_id, (old_ep_id, ph_ids) in zip(new_ep_ids, ep_ph_ids_list)[::2]]
    self._tester.HidePhotos(self._cookie, ep_ph_ids_list[::3] + ep_ph_ids_list2)

  def testHideDuplicatePhotos(self):
    """Hide the same photos multiple times."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 3)
    self._tester.HidePhotos(self._cookie, [(ep_id, ph_ids)])
    self._tester.HidePhotos(self._cookie, [(ep_id, ph_ids)])
    self._tester.HidePhotos(self._cookie, [(ep_id, ph_ids + ph_ids)])

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 2)
    self._tester.HidePhotos(self._cookie, [(ep_id, ph_ids[:1])])
    self._tester.HidePhotos(self._cookie, [(ep_id, ph_ids)])

    vp_id, new_ep_ids = self._tester.ShareNew(self._cookie,
                                              [(ep_id, ph_ids)],
                                              [self._user2.user_id])
    self._tester.HidePhotos(self._cookie, [(new_ep_ids[0], ph_ids[1:])])
    self._tester.HidePhotos(self._cookie, [(new_ep_ids[0], ph_ids)])

  def testHideNonExistingPhoto(self):
    """ERROR: Hide from an episode without a POST entry."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 3)
    self.assertRaisesHttpError(400, self._tester.HidePhotos, self._cookie, [(ep_id, ['punknown'])])

  def testHideFromNonExistingEpisode(self):
    """ERROR: Remove from a non-existing episode."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 3)
    self.assertRaisesHttpError(400, self._tester.HidePhotos, self._cookie, [('eunknown', ph_ids)])

  def testHideRemoved(self):
    """ERROR: Try to hide photo which has been unshared or removed."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 1)
    self._tester.RemovePhotos(self._cookie, [(ep_id, ph_ids)])
    self.assertRaisesHttpError(403, self._tester.HidePhotos, self._cookie, [(ep_id, ph_ids)])

    self._tester.Unshare(self._cookie, self._user.private_vp_id, [(ep_id, ph_ids)])
    self.assertRaisesHttpError(403, self._tester.HidePhotos, self._cookie, [(ep_id, ph_ids)])

  def testHidePhotosAccess(self):
    """ERROR: Ensure that only photos visible to the user can be hidden."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 1)
    self.assertRaisesHttpError(403, self._tester.HidePhotos, self._cookie2, [(ep_id, ph_ids)])

    vp_id, new_ep_ids = self._tester.ShareNew(self._cookie,
                                              [(ep_id, ph_ids)],
                                              [self._user2.user_id])
    self.assertRaisesHttpError(403, self._tester.HidePhotos, self._cookie3, [(new_ep_ids[0], ph_ids)])


def _TestHidePhotos(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test hide_photos service API call."""
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)
  user = validator.GetModelObject(User, user_id)

  # Send hide_photos request.
  actual_dict = tester.SendRequest('hide_photos', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # Validate UserPost objects.
  ph_act_dict = {}
  for request_ep in request_dict['episodes']:
    episode_id = request_ep['episode_id']
    episode = validator.GetModelObject(Episode, episode_id)

    for photo_id in request_ep['photo_ids']:
      post_id = Post.ConstructPostId(episode_id, photo_id)
      user_post = validator.GetModelObject(UserPost, DBKey(user_id, post_id), must_exist=False)

      # Gather set of photos that should have been hidden and will affect accounting.
      if episode.viewpoint_id == user.private_vp_id:
        if user_post is None or not user_post.IsHidden():
          ph_act_dict.setdefault(episode.viewpoint_id, {}).setdefault(episode_id, []).append(photo_id)

      timestamp = op_dict['op_timestamp'] if user_post is None else user_post.timestamp

      # Add HIDDEN label if not already there.
      if user_post is None:
        labels = [UserPost.HIDDEN]
      else:
        labels = user_post.labels
        if not user_post.IsHidden():
          labels = labels.union([UserPost.HIDDEN])

      validator.ValidateUpdateDBObject(UserPost,
                                       user_id=user_id,
                                       post_id=post_id,
                                       timestamp=timestamp,
                                       labels=labels)

  # Validate notification for the hide.
  invalidate = {'episodes': [{'episode_id': request_ep['episode_id'], 'get_photos': True}
                             for request_ep in request_dict['episodes']]}
  validator.ValidateNotification('hide_photos', user_id, op_dict, invalidate)

  return actual_dict
