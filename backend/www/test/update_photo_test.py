# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests update_photo method.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import time

from copy import deepcopy
from viewfinder.backend.base import util
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.user_photo import UserPhoto
from viewfinder.backend.www.test import service_base_test

class UpdatePhotoTestCase(service_base_test.ServiceBaseTestCase):
  def testUpdatePhoto(self):
    """Creates a new photo and photo and updates both."""
    photo_id = self._UploadEpisodeWithPhoto()

    self._tester.UpdatePhoto(self._cookie, photo_id, caption='An Updated Caption',
                             placemark={'iso_country_code': 'US', 'country': 'United States',
                                        'state': 'NY', 'locality': 'New York', 'sublocality': 'NoHo',
                                        'thoroughfare': 'Broadway', 'subthoroughfare': '682'})

  def testUpdatePhotoForbidden(self):
    """Creates a new episode and photo and fails to update photo using different user."""
    photo_id = self._UploadEpisodeWithPhoto()

    # Now, after creating the episode and photo with 'user' (self._cookie), try to update with 'user3' (self._cookie3).
    self.assertRaisesHttpError(403, self._tester.UpdatePhoto, self._cookie3, photo_id, caption='An Updated Caption',
                               placemark={'iso_country_code': 'US', 'country': 'United States',
                                          'state': 'NY', 'locality': 'New York', 'sublocality': 'NoHo',
                                          'thoroughfare': 'Broadway', 'subthoroughfare': '682'})

  def testAssetKey(self):
    photo_id = self._UploadEpisodeWithPhoto()

    self._tester.UpdatePhoto(self._cookie, photo_id, asset_keys=['a/#asset_key1'])

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

    return photo_id

def _TestUpdatePhoto(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test update_photo
  service API call.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  # Send update_photo request.
  actual_dict = tester.SendRequest('update_photo', user_cookie, request_dict)

  photo_dict = deepcopy(request_dict)
  photo_dict['user_id'] = user_id
  photo_dict.pop('headers', None)
  photo_dict.pop('activity', None)
  photo_dict.pop('asset_keys', None)
  validator.ValidateUpdateDBObject(Photo, **photo_dict)

  if request_dict.get('asset_keys'):
    up_dict = {
      'user_id': user_id,
      'photo_id': request_dict['photo_id'],
      'asset_keys': request_dict['asset_keys'],
      }
    validator.ValidateUpdateDBObject(UserPhoto, **up_dict)


  tester._CompareResponseDicts('update_photo', user_id, request_dict, {}, actual_dict)
  return actual_dict
