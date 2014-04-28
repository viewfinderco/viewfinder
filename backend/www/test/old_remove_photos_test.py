# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests remove_photos method as an old client.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import mock
import time

from copy import deepcopy
from functools import partial
from viewfinder.backend.base import message, util
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


class OldRemovePhotosTestCase(service_base_test.ServiceBaseTestCase):
  def testRemovePhotos(self):
    """Remove photos from default and shared viewpoints."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 9)
    self._OldRemovePhotos(self._cookie, [(ep_id, ph_ids[::2])])

    vp_id, new_ep_ids = self._tester.ShareNew(self._cookie, [(ep_id, ph_ids[1::2])],
                                              [self._user2.user_id])
    self._OldRemovePhotos(self._cookie, [(new_ep_ids[0], ph_ids[1::2])])

  def testRemoveMultipleEpisodes(self):
    """Remove photos from multiple episodes."""
    ep_ph_ids_list = self._UploadMultipleEpisodes(self._cookie, 17)
    vp_id, new_ep_ids = self._tester.ShareNew(self._cookie, ep_ph_ids_list,
                                              [self._user3.user_id])

    # Build list of (ep_id, ph_ids) pairs from subset of uploaded episodes and photos.
    ep_ph_ids_list2 = [(new_ep_id, ph_ids[::3])
                       for new_ep_id, (old_ep_id, ph_ids) in zip(new_ep_ids, ep_ph_ids_list)[::2]]
    self._OldRemovePhotos(self._cookie, ep_ph_ids_list[::3] + ep_ph_ids_list2)

  def testRemoveDuplicatePhotos(self):
    """Remove the same photos multiple times."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 3)
    self._OldRemovePhotos(self._cookie, [(ep_id, ph_ids)])
    self._OldRemovePhotos(self._cookie, [(ep_id, ph_ids)])
    self._OldRemovePhotos(self._cookie, [(ep_id, ph_ids + ph_ids)])

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 2)
    self._OldRemovePhotos(self._cookie, [(ep_id, ph_ids[:1])])
    self._OldRemovePhotos(self._cookie, [(ep_id, ph_ids)])

    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 2)
    vp_id, new_ep_ids = self._tester.ShareNew(self._cookie,
                                              [(ep_id, ph_ids)],
                                              [self._user2.user_id])
    self._OldRemovePhotos(self._cookie, [(new_ep_ids[0], ph_ids[1:])])
    self._OldRemovePhotos(self._cookie, [(new_ep_ids[0], ph_ids)])

  def testRemoveNonExistingPhoto(self):
    """ERROR: Remove from an episode without a POST entry."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 3)
    self.assertRaisesHttpError(400, self._OldRemovePhotos, self._cookie, [(ep_id, ['punknown'])])

  def testRemoveFromNonExistingEpisode(self):
    """ERROR: Remove from a non-existing episode."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 3)
    self.assertRaisesHttpError(400, self._OldRemovePhotos, self._cookie, [('eunknown', ph_ids)])

  def testRemovePhotosAccess(self):
    """ERROR: Ensure that only photos visible to the user can be removed."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 1)
    self.assertRaisesHttpError(403, self._OldRemovePhotos, self._cookie2, [(ep_id, ph_ids)])

    vp_id, new_ep_ids = self._tester.ShareNew(self._cookie,
                                              [(ep_id, ph_ids)],
                                              [self._user2.user_id])
    self.assertRaisesHttpError(403, self._OldRemovePhotos, self._cookie3, [(new_ep_ids[0], ph_ids)])

  def _OldRemovePhotos(self, user_cookie, ep_ph_ids_list):
    """remove_photos: Removes photos from a user's personal library in older clients.

    "ep_ph_ids_list" is a list of tuples in this format:
      [(episode, [photo_id, ...]), ...]
    """
    request_dict = {'episodes': [{'episode_id': episode_id,
                                  'photo_ids': photo_ids}
                                 for episode_id, photo_ids in ep_ph_ids_list]}

    _TestOldRemovePhotos(self._tester, user_cookie, request_dict)


def _TestOldRemovePhotos(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test remove_photos service API call."""
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)
  user = validator.GetModelObject(User, user_id)

  # Send remove_photos request.
  actual_dict = tester.SendRequest('remove_photos',
                                   user_cookie,
                                   request_dict,
                                   version=message.Message.SUPPORT_MULTIPLE_IDENTITIES_PER_CONTACT)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # Validate UserPost objects.
  remove_ep_dicts = []
  hide_ep_dicts = []
  for request_ep in request_dict['episodes']:
    episode_id = request_ep['episode_id']
    episode = validator.GetModelObject(Episode, episode_id)

    if episode.viewpoint_id == user.private_vp_id:
      remove_ep_dicts.append(request_ep)
      for photo_id in request_ep['photo_ids']:
        post = validator.GetModelObject(Post, DBKey(episode_id, photo_id))
        if not post.IsRemoved():
          # Validate that REMOVED label was added.
          validator.ValidateUpdateDBObject(Post,
                                           episode_id=episode_id,
                                           photo_id=photo_id,
                                           labels=post.labels.combine().union([Post.REMOVED]))
    else:
      hide_ep_dicts.append(request_ep)
      for photo_id in request_ep['photo_ids']:
        found_hide = True
        post_id = Post.ConstructPostId(episode_id, photo_id)
        user_post = validator.GetModelObject(UserPost, DBKey(user_id, post_id), must_exist=False)

        timestamp = op_dict['op_timestamp'] if user_post is None else user_post.timestamp
        labels = [UserPost.HIDDEN] if user_post is None else user_post.labels.union([UserPost.HIDDEN])
        validator.ValidateUpdateDBObject(UserPost,
                                         user_id=user_id,
                                         post_id=post_id,
                                         timestamp=timestamp,
                                         labels=labels)

  # Validate notification for the hide (if one existed).
  if len(hide_ep_dicts) > 0:
    invalidate = {'episodes': [{'episode_id': request_ep['episode_id'], 'get_photos': True}
                               for request_ep in hide_ep_dicts]}
    validator.ValidateNotification('hide_photos', user_id, op_dict, invalidate)

  # Validate notification for the remove.
  invalidate = {'episodes': [{'episode_id': request_ep['episode_id'], 'get_photos': True}
                             for request_ep in remove_ep_dicts]}
  validator.ValidateNotification('remove_photos', user_id, op_dict, invalidate)

  validator.ValidateViewpointAccounting(user.private_vp_id)
  tester._CompareResponseDicts('remove_photos', user_id, request_dict, {}, actual_dict)
  return actual_dict
