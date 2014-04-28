# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test upload_episode service method.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import base64
import mock
import time

from copy import deepcopy
from viewfinder.backend.base import util
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user import User
from viewfinder.backend.db.user_photo import UserPhoto
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.www.test import service_base_test

class UploadEpisodeTestCase(service_base_test.ServiceBaseTestCase):
  def testMobileUploadEpisode(self):
    """Create 10 new photos using mobile device."""
    photos = [{'aspect_ratio': 1.3333,
               'tn_md5': util.ComputeMD5Hex('thumbnail image data'),
               'med_md5': util.ComputeMD5Hex('medium image data'),
               'full_md5': util.ComputeMD5Hex('full image data'),
               'orig_md5': util.ComputeMD5Hex('original image data'),
               'tn_size': 5 * 1024,
               'med_size': 10 * 1024,
               'full_size': 150 * 1024,
               'orig_size': 1200 * 1024,
               'caption': 'caption number %d' % i} \
              for i in xrange(10)]

    # Simulate the mobile device by letting _UploadEpisode generate photo device ids.
    self._tester.UploadEpisode(self._cookie, {}, photos)

  def testWebappUploadEpisode(self):
    """Create 10 new photos using web."""
    photos = [{'aspect_ratio': 1.3333,
               'timestamp': time.time(),
               'content_type': 'text/plain',
               'tn_md5': util.ComputeMD5Hex('thumbnail image data'),
               'med_md5': util.ComputeMD5Hex('medium image data'),
               'full_md5': util.ComputeMD5Hex('full image data'),
               'orig_md5': util.ComputeMD5Hex('original image data'),
               'tn_size': 5 * 1024,
               'med_size': 10 * 1024,
               'full_size': 150 * 1024,
               'orig_size': 1200 * 1024,
               'caption': 'caption number %d' % i} \
              for i in xrange(10)]

    # Simulate the web app by allocating ids.
    response_dict = self._SendRequest('allocate_ids', self._cookie2, {'asset_types': list('p' * len(photos))})

    for i, p in enumerate(photos):
      p['photo_id'] = response_dict['asset_ids'][i]

    self._tester.UploadEpisode(self._cookie2, {}, photos)

  def testUploadDifferentEpisodesFail(self):
    """Upload the same photo to multiple episodes and expect that it fails to load the same photo to
    a different episode.
    """
    photos = [self._CreatePhotoDict(self._cookie)]
    self._UploadEpisode(self._cookie, photos)
    # Not allowed to upload the same photo (photo_id) into different episodes.
    self.assertRaisesHttpError(400, self._UploadEpisode, self._cookie, photos)

  def testUploadSameEpisodeTwice(self):
    """Upload the same photo in the same episode twice.  Test client scenario where it sometimes
    uploads an episode with photos and then (due to a crash or restart) will upload the same episode
    again with the same photos and sometimes additional photos.  Server should be able to tolerate this."""
    photos = [self._CreatePhotoDict(self._cookie)]
    ep_dict = {'timestamp': time.time()}
    ep_id, _ = self._UploadEpisode(self._cookie, photos, ep_dict)
    ep_dict['episode_id'] = ep_id
    # Add another photo for the second upload.
    photos.append(self._CreatePhotoDict(self._cookie))
    # Now, upload same episode(id) and same timestamp.
    ep_id2, _ = self._UploadEpisode(self._cookie, photos, ep_dict)
    self.assertEqual(ep_id, ep_id2)

  def testRepeatUpload(self):
    """Verify the same photo/episode upload twice is idempotent."""
    request_dict = {'activity': self._tester.CreateActivityDict(self._cookie),
                    'episode': self._CreateEpisodeDict(self._cookie),
                    'photos': [self._CreatePhotoDict(self._cookie)]}
    response_dict1 = _TestUploadEpisode(self._tester, self._cookie, request_dict)
    response_dict2 = _TestUploadEpisode(self._tester, self._cookie, request_dict)
    self.assertEqual(response_dict1, response_dict2)

  def testWrongDeviceIds(self):
    """ERROR: Try to create an episode and photo using device ids that
    are different than the ones in the user cookies.
    """
    bad_episode_id = Episode.ConstructEpisodeId(100, 1000, 1)
    self.assertRaisesHttpError(403, self._tester.UploadEpisode, self._cookie,
                               ep_dict={'episode_id': bad_episode_id, 'timestamp': 100},
                               ph_dict_list=[])

    episode_id = Episode.ConstructEpisodeId(100, self._device_ids[0], 100)
    bad_photo_id = Photo.ConstructPhotoId(100, 1000, 1)
    self.assertRaisesHttpError(403, self._tester.UploadEpisode, self._cookie,
                               ep_dict={},
                               ph_dict_list=[self._CreatePhotoDict(self._cookie, photo_id=bad_photo_id)])

  def testBadUserEpisodeUpload(self):
    """Upload an episode twice, and on the second time from a bad user-id."""
    request_dict = {'activity': self._tester.CreateActivityDict(self._cookie),
                    'episode': self._CreateEpisodeDict(self._cookie),
                    'photos': [self._CreatePhotoDict(self._cookie)]}
    _TestUploadEpisode(self._tester, self._cookie, request_dict)
    self.assertRaisesHttpError(403, _TestUploadEpisode, self._tester, self._cookie2, request_dict)

  def testUploadImageFiles(self):
    """Create new photos using mobile device and upload image file
    assets.
    """
    request_dict = {'activity': self._tester.CreateActivityDict(self._cookie),
                    'episode': self._CreateEpisodeDict(self._cookie),
                    'photos': [self._CreatePhotoDict(self._cookie)]}
    response_dict = _TestUploadEpisode(self._tester, self._cookie, request_dict)

    photos = response_dict['photos']
    for p in photos:
      self._UploadImageFile(p['tn_put_url'], 'thumbnail image data')
      self.assertEqual(self._DownloadImageFile(p['tn_put_url']), 'thumbnail image data')

      self._UploadImageFile(p['med_put_url'], 'medium image data')
      self.assertEqual(self._DownloadImageFile(p['med_put_url']), 'medium image data')

      self._UploadImageFile(p['full_put_url'], 'full image data')
      self.assertEqual(self._DownloadImageFile(p['full_put_url']), 'full image data')

      self._UploadImageFile(p['orig_put_url'], 'original image data')
      self.assertEqual(self._DownloadImageFile(p['orig_put_url']), 'original image data')

  def testPlacemarks(self):
    """Create new photos with placemarks, some with unicode characters,
    some with missing place names.
    """
    photos = [self._CreatePhotoDict(self._cookie,
                                    placemark={'iso_country_code': 'US',
                                               'country': 'United States',
                                               'state': 'NY',
                                               'locality': 'New York',
                                               'sublocality': 'NoHo',
                                               'thoroughfare': 'Broadway',
                                               'subthoroughfare': '682'}),
              self._CreatePhotoDict(self._cookie,
                                    placemark={'iso_country_code': 'DR',
                                               'country': 'Dominican Republic',
                                               'state': u'Mar\xeda Trinidad S\xe1nchez',
                                               'locality': 'Cabrera'})]

    self._UploadEpisode(self._cookie, photos)

  def testExistingPhotoId(self):
    """Upload a photo with an ID that already exists."""
    photos = [self._CreatePhotoDict(self._cookie, caption='first caption')]
    ep_id, _ = self._UploadEpisode(self._cookie, photos)

    photos[0]['caption'] = 'second caption'
    self._UploadEpisode(self._cookie, photos, {'episode_id': ep_id})

  def testAssetKey(self):
    """Upload photos with asset keys."""
    photos = [self._CreatePhotoDict(self._cookie, asset_keys=['a/#asset1'])]
    self._UploadEpisode(self._cookie, photos)#

  def testMD5(self):
    """Upload photos with md5 checksums set."""
    orig_md5 = '4ae4aa09eb9fd9ceab65794d4f7fb29d'
    full_md5 = 'a37bdd4d2338f5ac338f766e255eb4b3'
    med_md5 = '373bf078574d0bae9a76268ee087e7c4'
    tn_md5 = 'dd8d288cff109fed6bf1b8cdfac2f4b0'

    photos = [{'aspect_ratio': 0.75, 'timestamp': time.time(),
               'orig_md5': orig_md5,
               'full_md5': full_md5,
               'med_md5': med_md5,
               'tn_md5': tn_md5,
               'tn_size': 5 * 1024,
               'med_size': 10 * 1024,
               'full_size': 150 * 1024,
               'orig_size': 1200 * 1024}]
    episode_id, photo_ids = self._UploadEpisode(self._cookie, photos)

    self.assertEqual(len(photo_ids), 1)
    photo_id = photo_ids[0]

    # Index query photos for md5 checksums.
    query_expr = ('photo.orig_md5={md5}', {'md5':orig_md5})
    orig = self._RunAsync(Photo.IndexQueryKeys, self._client, query_expr)
    self.assertEqual(len(orig), 1)
    self.assertEqual(photo_id, orig[0].hash_key)

    query_expr = ('photo.full_md5={md5}', {'md5':full_md5})
    full = self._RunAsync(Photo.IndexQueryKeys, self._client, query_expr)
    self.assertEqual(len(full), 1)
    self.assertEqual(photo_id, full[0].hash_key)

  def testUploadMD5Mismatch(self):
    """Call upload_episode once. Then call it again, but with different
    MD5 image values. Because the photo image data does not yet exist,
    the metadata should be overwritten with the new values. Then actually
    upload the image data and try to overwrite the MD5 values again,
    expecting an error this time.
    """
    upload_data = [('tn_md5', '.t', 'new thumbnail image data'),
                   ('med_md5', '.m', 'new medium image data'),
                   ('full_md5', '.f', 'new full image data'),
                   ('orig_md5', '.o', 'new original image data')]

    ph_dict = {'aspect_ratio': 0.75,
               'timestamp': time.time(),
               'tn_size': 5 * 1024,
               'med_size': 10 * 1024,
               'full_size': 150 * 1024,
               'orig_size': 1200 * 1024}

    # Do first upload.
    for data in upload_data:
      attr_name, suffix, image_data = data
      ph_dict[attr_name] = util.ComputeMD5Hex(image_data)

    ep_dict = {'timestamp': time.time()}
    ep_id, ph_ids = self._UploadEpisode(self._cookie, [ph_dict], ep_dict)
    ph_dict['photo_id'] = ph_ids[0]

    # Update the photo MD5 values and upload again.
    for data in upload_data:
      attr_name, suffix, image_data = data
      ph_dict[attr_name] = util.ComputeMD5Hex('really ' + image_data)

    ep_dict['episode_id'] = ep_id
    ep_id, ph_ids = self._UploadEpisode(self._cookie, [ph_dict], ep_dict)
    assert ph_dict['photo_id'] == ph_ids[0], (ph_dict, ph_ids)

    for data in upload_data:
      # Upload the image data for this size of photo.
      attr_name, suffix, image_data = data
      etag = util.ComputeMD5Hex('really ' + image_data)
      self._tester.PutPhotoImage(self._cookie, ep_id, ph_ids[0],
                                 suffix, 'really ' + image_data,
                                 content_md5=util.ComputeMD5Base64('really ' + image_data),
                                 etag=etag)

      # Validate that the photo's MD5 was updated.
      update_ph_dict = {'photo_id': ph_ids[0],
                        attr_name: etag}
      self._validator.ValidateUpdateDBObject(Photo, **update_ph_dict)

      # Verify the MD5 value can no longer be updated.
      copy_ph_dict = deepcopy(ph_dict)
      copy_ph_dict[attr_name] = util.ComputeMD5Hex('bad ' + image_data)
      self.assertRaisesHttpError(403, self._UploadEpisode, self._cookie, [copy_ph_dict], ep_dict)

      # Test changing one MD5 and not others.
      if suffix == '.m':
        copy_ph_dict = deepcopy(ph_dict)
        copy_ph_dict['full_md5'] = util.ComputeMD5Hex('only this ' + image_data)
        self._UploadEpisode(self._cookie, [copy_ph_dict], ep_dict)

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    ph_dict = self._CreatePhotoDict(self._cookie)
    location = ph_dict.pop('location')
    placemark = ph_dict.pop('placemark')

    ep_dict = self._CreateEpisodeDict(self._cookie)

    request_dict = {'activity': self._tester.CreateActivityDict(self._cookie),
                    'episode': ep_dict,
                    'photos': [ph_dict]}
    _TestUploadEpisode(self._tester, self._cookie, request_dict)

    request_dict = {'activity': self._tester.CreateActivityDict(self._cookie),
                    'episode': ep_dict,
                    'photos': [self._CreatePhotoDict(self._cookie)]}
    _TestUploadEpisode(self._tester, self._cookie, request_dict)

  def _UploadEpisode(self, user_cookie, photos, ep_dict=None):
    """Returns an upload_episode request dict."""
    if ep_dict is None:
      ep_dict = {}
    ep_dict['title'] = 'Episode Title'
    return self._tester.UploadEpisode(user_cookie, ep_dict, photos)

  def _DownloadImageFile(self, url):
    """Makes a GET request to the specified 'url' to download file."""
    response = self._RunAsync(self._tester.http_client.fetch, url, method='GET')
    assert response.code == 200, response
    assert response.headers['Content-Type'] == 'image/jpeg', response.headers['Content-Type']
    return response.body

  def _UploadImageFile(self, url, image_data):
    """Makes a PUT request to the specified 'url' to upload 'image_data'."""
    md5_hex = util.ComputeMD5Base64(image_data)
    response = self._RunAsync(self._tester.http_client.fetch, url,
                              method='PUT', body=image_data,
                              headers={'Content-Type': 'image/jpeg',
                                       'Content-MD5': md5_hex})
    assert response.code == 200, response
    return response.body


def _TestUploadEpisode(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test upload_episode
  service API call.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  def _GenerateUploadUrl(obj_store, photo, suffix, md5_hex):
    """Create expected URL to which to upload image data."""
    content_md5 = base64.b64encode(md5_hex.decode('hex'))
    return obj_store.GenerateUploadUrl('%s%s' % (photo.photo_id, suffix),
                                       content_type=photo.content_type,
                                       content_md5=content_md5)
  # Send upload_episode request.
  actual_dict = tester.SendRequest('upload_episode', user_cookie, request_dict)

  # Start construction of dict containing expected episode attributes.
  ep_dict = request_dict['episode']
  ep_dict['user_id'] = user_id
  ep_dict['viewpoint_id'] = validator.GetModelObject(User, user_id).private_vp_id
  ep_dict['publish_timestamp'] = request_dict['headers']['op_timestamp']

  existing_episode = validator.GetModelObject(Episode, ep_dict['episode_id'], must_exist=False)
  if existing_episode is not None:
    # If episode already exists, only allow update of location and placemark.
    ep_dict = {'episode_id': ep_dict['episode_id']}

  new_photo_ids = []
  expected_dict = {'photos': []}
  for ph_dict, actual_ph_dict in zip(request_dict['photos'], actual_dict['photos']):
    if 'location' not in ep_dict and 'location' in ph_dict:
      if existing_episode is None or existing_episode.location == None:
        ep_dict['location'] = ph_dict['location']

    if 'placemark' not in ep_dict and 'placemark' in ph_dict:
      if existing_episode is None or existing_episode.placemark == None:
        ep_dict['placemark'] = ph_dict['placemark']

    asset_keys = ph_dict.pop('asset_keys', None)
    if asset_keys:
      assert user_id

      up_dict = {
        'user_id': user_id,
        'photo_id': ph_dict['photo_id'],
        'asset_keys': asset_keys,
        }
      validator.ValidateCreateDBObject(UserPhoto, **up_dict)

    # Validate update of photo object.
    if validator.GetModelObject(Photo, ph_dict['photo_id'], must_exist=False) is None:
      ph_dict['episode_id'] = ep_dict['episode_id']
    else:
      # Photo exists, so remove all but MD5 attributes (only these can be updated).
      for key in ph_dict.keys():
        if key not in ['photo_id', 'tn_md5', 'med_md5', 'full_md5', 'orig_md5']:
          del ph_dict[key]

    ph_dict['user_id'] = user_id
    photo = validator.ValidateUpdateDBObject(Photo, **ph_dict)

    # Post is only included in accounting totals if it did not exist before.
    if validator.GetModelObject(Post, DBKey(ep_dict['episode_id'], photo.photo_id), must_exist=False) is None:
      new_photo_ids.append(ph_dict['photo_id'])

    # Validate creation of post object.
    validator.ValidateCreateDBObject(Post, episode_id=ep_dict['episode_id'], photo_id=photo.photo_id)

    obj_store = ObjectStore.GetInstance(ObjectStore.PHOTO)
    expected_dict['photos'].append({'photo_id': photo.photo_id,
                                    'tn_put_url': _GenerateUploadUrl(obj_store, photo, '.t', photo.tn_md5),
                                    'med_put_url': _GenerateUploadUrl(obj_store, photo, '.m', photo.med_md5),
                                    'full_put_url': _GenerateUploadUrl(obj_store, photo, '.f', photo.full_md5),
                                    'orig_put_url': _GenerateUploadUrl(obj_store, photo, '.o', photo.orig_md5)})

  # Validate update of episode object.
  episode = validator.ValidateUpdateDBObject(Episode, **ep_dict)

  # Validate activity and notifications for the upload.
  activity_dict = {'name': 'upload_episode',
                   'activity_id': request_dict['activity']['activity_id'],
                   'timestamp': request_dict['activity']['timestamp'],
                   'episode_id': episode.episode_id,
                   'photo_ids': [ph_dict['photo_id'] for ph_dict in request_dict['photos']]}

  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  invalidate = {'episodes': [{'episode_id': ep_dict['episode_id'],
                              'get_attributes': True,
                              'get_photos': True}]}

  validator.ValidateFollowerNotifications(episode.viewpoint_id, activity_dict, op_dict, invalidate)

  validator.ValidateViewpointAccounting(episode.viewpoint_id)
  tester._CompareResponseDicts('update_episode', user_id, request_dict, expected_dict, actual_dict)
  return actual_dict
