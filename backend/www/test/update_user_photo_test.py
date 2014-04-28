# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Tests update_user_photo method.
"""

__author__ = ['ben@emailscrubbed.com (Ben Darnell)']


import time

from copy import deepcopy
from viewfinder.backend.base import util
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.user_photo import UserPhoto
from viewfinder.backend.www.test import service_base_test

class UpdateUserPhotoTestCase(service_base_test.ServiceBaseTestCase):
  def testUpdateUserPhoto(self):
    """Assign different asset keys to the same photo from different users."""
    episode_id, photo_id = self._UploadEpisodeWithPhoto()

    # Assign an asset key for user 1
    self._tester.UpdateUserPhoto(self._cookie, photo_id, asset_keys=['a/#asset-key-1'])

    # User 2 doesn't own the photo (and doesn't even have access to it!) but can still set asset keys.
    self._tester.UpdateUserPhoto(self._cookie2, photo_id, asset_keys=['a/#asset-key-2'])

    # User 2 can't read the episode yet.
    self.assertEqual([],
                     self._tester.QueryEpisodes(self._cookie2,
                                                [{'episode_id': episode_id, 'get_photos': True}])['episodes'])

    # Share the episode with user 2, and then try fetching the asset key
    vp_id, new_ep_ids = self._tester.ShareNew(self._cookie, [(episode_id, [photo_id])], [self._user2.user_id])
    self.assertEqual(sorted(self._GetAssetKeys(self._cookie2, new_ep_ids[0])), ['a/#asset-key-2'])

  def testReplaceUserPhoto(self):
    """Change the asset keys associated with a user/photo."""
    episode_id, photo_id = self._UploadEpisodeWithPhoto()

    self._tester.UpdateUserPhoto(self._cookie, photo_id, asset_keys=['a/#asset-key-1'])
    self.assertEqual(self._GetAssetKeys(self._cookie, episode_id), ['a/#asset-key-1'])

    self._tester.UpdateUserPhoto(self._cookie, photo_id, asset_keys=['a/#asset-key-1', 'a/#asset-key-2'])
    self.assertEqual(sorted(self._GetAssetKeys(self._cookie, episode_id)), ['a/#asset-key-1', 'a/#asset-key-2'])

    # Asset keys are append-only; an empty update doesn't remove what's there.
    self._tester.UpdateUserPhoto(self._cookie, photo_id, asset_keys=[])
    self.assertEqual(sorted(self._GetAssetKeys(self._cookie, episode_id)), ['a/#asset-key-1', 'a/#asset-key-2'])

  def _GetAssetKeys(self, cookie, ep_id):
    episodes = self._tester.QueryEpisodes(cookie, [{'episode_id': ep_id, 'get_photos': True}])
    photo = episodes['episodes'][0]['photos'][0]
    return photo.get('asset_keys')

  def _UploadEpisodeWithPhoto(self):
    """Create episode with photo and upload.
    Returns: photo_id of created photo.
    """
    timestamp = time.time()

    episode_id = Episode.ConstructEpisodeId(timestamp, self._device_ids[0], 100)
    ep_dict = {'episode_id': episode_id,
               'timestamp': timestamp,
               'title': 'Episode Title'}

    photo_id = Photo.ConstructPhotoId(timestamp, self._device_ids[0], 100)
    ph_dict = {'aspect_ratio': 1.3333,
               'timestamp': timestamp,
               'tn_md5': util.ComputeMD5Hex('thumbnail image data'),
               'med_md5': util.ComputeMD5Hex('medium image data'),
               'full_md5': util.ComputeMD5Hex('full image data'),
               'orig_md5': util.ComputeMD5Hex('original image data'),
               'tn_size': 5*1024,
               'med_size': 10*1024,
               'full_size': 150*1024,
               'orig_size': 1200*1024,
               'caption': 'a photo',
               'photo_id': photo_id}

    self._tester.UploadEpisode(self._cookie, ep_dict, [ph_dict])

    return episode_id, photo_id

def _TestUpdateUserPhoto(tester, user_cookie, request_dict):
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  actual_dict = tester.SendRequest('update_user_photo', user_cookie, request_dict)

  existing = validator.GetModelObject(UserPhoto, DBKey(user_id, request_dict['photo_id']), must_exist=False)
  if existing is None:
    asset_keys = request_dict['asset_keys']
  else:
    asset_keys = set(request_dict['asset_keys'])
    asset_keys.update(existing.asset_keys)

  up_dict = {'user_id': user_id,
             'photo_id': request_dict['photo_id'],
             'asset_keys': asset_keys}
  validator.ValidateUpdateDBObject(UserPhoto, **up_dict)

  tester._CompareResponseDicts('update_user_photo', user_id, request_dict, {}, actual_dict)
  return actual_dict
