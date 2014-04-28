#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test PhotoStore GET and PUT.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import base64
import hashlib
import json
import time

from functools import partial
from viewfinder.backend.base import util
from viewfinder.backend.base.message import Message
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.friend import Friend
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.user import User
from viewfinder.backend.www import json_schema
from viewfinder.backend.www.test import service_base_test


class PhotoStoreTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(PhotoStoreTestCase, self).setUp()
    self._CreateSimpleTestAssets()

  def testUploadAndGetPut(self):
    """Upload a photo, PUT the photo image data, then access it in
    various ways.
    """
    episode_id = self._episode_id
    photo_id = self._photo_ids[0]
    orig_image_data = 'original image data' # Same as used in self._UploadEpisode

    self._PutPhotoAndVerify(self._cookie, 200, episode_id, photo_id, '.o', orig_image_data)
    self._PutPhotoAndVerify(self._cookie, 200, episode_id, photo_id, '.f', 'full image data')
    self._PutPhotoAndVerify(self._cookie, 200, episode_id, photo_id, '.t', 'thumbnail image data')

    # Test legit downloads.
    self._GetPhotoAndVerify(self._cookie, 200, episode_id, photo_id, '.o')
    self._GetPhotoAndVerify(self._cookie, 200, episode_id, photo_id, '.f')
    self._GetPhotoAndVerify(self._cookie, 200, episode_id, photo_id, '.t')

    # Try get and put with no cookie.
    self._PutPhotoAndVerify(None, 401, episode_id, photo_id, '.o', orig_image_data)
    self._GetPhotoAndVerify(None, 401, episode_id, photo_id, '.o')

    # Try get and put of missing photo.
    self._PutPhotoAndVerify(self._cookie, 404, episode_id, 'p-unk', '.m', orig_image_data)
    self._GetPhotoAndVerify(self._cookie, 404, episode_id, 'p-unk', '.m')

    # Try get and put without permission.
    self._PutPhotoAndVerify(self._cookie2, 404, episode_id, photo_id, '.o', orig_image_data)
    self._GetPhotoAndVerify(self._cookie2, 404, episode_id, photo_id, '.o')

    # Omit the Content-MD5 header.
    response = self._PutPhoto(self._cookie, episode_id, photo_id, '.o', orig_image_data)
    assert response.code == 400, response

    # Try to use a non well-formed Content-MD5 header.
    response = self._PutPhoto(self._cookie, episode_id, photo_id, '.o', orig_image_data,
                              content_md5='not well-formed')
    assert response.code == 400, response

    # Try to use a Content-MD5 header that does not match the data.
    response = self._PutPhoto(self._cookie, episode_id, photo_id, '.o', orig_image_data,
                              content_md5=util.ComputeMD5Base64('mismatched md5'))
    assert response.code == 400, response

    # Try put with user that is not episode owner.
    new_vp_id, new_ep_ids = self._tester.ShareNew(self._cookie,
                                                  [(episode_id, [photo_id])],
                                                  [self._user2.user_id])
    self._PutPhotoAndVerify(self._cookie2, 403, new_ep_ids[0], photo_id, '.o', orig_image_data)

    # Try get of photo using removed follower.
    self._tester.RemoveFollowers(self._cookie2, new_vp_id, [self._user2.user_id])
    self._GetPhotoAndVerify(self._cookie2, 404, new_ep_ids[0], photo_id, '.o')

    # Try get and put of unshared photo.
    self._tester.Unshare(self._cookie, new_vp_id, [(new_ep_ids[0], [photo_id])])
    self._PutPhotoAndVerify(self._cookie, 403, new_ep_ids[0], photo_id, '.o', orig_image_data)
    self._GetPhotoAndVerify(self._cookie, 403, new_ep_ids[0], photo_id, '.o')

    # Try get and put of photo that has been shared again in order to override unshare.
    self._tester.ShareExisting(self._cookie, new_vp_id, [(self._episode_id, self._photo_ids)])
    self._PutPhotoAndVerify(self._cookie, 200, self._episode_id, self._photo_ids[0], '.o', orig_image_data)
    self._GetPhotoAndVerify(self._cookie, 200, self._episode_id, self._photo_ids[0], '.o')

    # Try get and put of hidden photo.
    self._tester.HidePhotos(self._cookie, [(self._episode_id, self._photo_ids)])
    self._PutPhotoAndVerify(self._cookie, 200, self._episode_id, self._photo_ids[0], '.o', orig_image_data)
    self._GetPhotoAndVerify(self._cookie, 200, self._episode_id, self._photo_ids[0], '.o')

    # Try get and put of removed photo.
    self._tester.RemovePhotos(self._cookie, [(self._episode_id, self._photo_ids)])
    self._PutPhotoAndVerify(self._cookie, 200, self._episode_id, self._photo_ids[0], '.o', orig_image_data)
    self._GetPhotoAndVerify(self._cookie, 200, self._episode_id, self._photo_ids[0], '.o')

  def testErrorResponse(self):
    """Test that error response is always in JSON format."""
    response = self._PutPhoto(self._cookie, 'unk', 'unk', '.o', '')
    self.assertEqual(json.loads(response.body), {"error": {"message": "Missing Content-MD5 header."}})

    response = self._GetPhoto(self._cookie, 'unk', 'unk', '.o')
    self.assertEqual(json.loads(response.body),
                     {u'error': {u'message': u'Photo was not found or you do not have permission to view it.'}})

  def testReUpload(self):
    """Upload a new photo and attempt to re-upload using If-None-Match
    header to simulate a phone reinstall where the client uses the
    /photos/<photo_id> interface to get a redirect to a PUT URL. In
    the case of the photo existing, the Etag should match and result
    in a 304 response, saving the client the upload bandwidth.
    """
    full_image_data = 'full image data'

    for photo_id in self._photo_ids:
      response = self._PutPhoto(self._cookie, self._episode_id, photo_id, '.f', full_image_data,
                                content_md5=util.ComputeMD5Base64(full_image_data),
                                etag=util.ComputeMD5Hex(full_image_data))
      self.assertEqual(response.code, 200)

    for photo_id in self._photo_ids:
      response = self._PutPhoto(self._cookie, self._episode_id, photo_id, '.f', full_image_data,
                                content_md5=util.ComputeMD5Base64(full_image_data),
                                etag='"%s"' % util.ComputeMD5Hex(full_image_data))
      self.assertEqual(response.code, 304)

      response = self._PutPhoto(self._cookie, self._episode_id, photo_id, '.f', full_image_data,
                                content_md5=util.ComputeMD5Base64(full_image_data),
                                etag='*')
      self.assertEqual(response.code, 304)

  def testUploadMismatch(self):
    """Upload photo image data with a different MD5 than was originally
    provided to upload_episode. Because the photo image data does not
    yet exist, the metadata should be overwritten with the new values.
    Then try to upload a different MD5 again, expecting an error this
    time.
    """
    for attr_name, suffix, image_data in [('tn_md5', '.t', 'new thumbnail image data'),
                                          ('med_md5', '.m', 'new medium image data'),
                                          ('full_md5', '.f', 'new full image data'),
                                          ('orig_md5', '.o', 'new original image data')]:
      # Expect success on first upload.
      response = self._PutPhoto(self._cookie, self._episode_id, self._photo_ids[0], suffix,
                                image_data, content_md5=util.ComputeMD5Base64(image_data),
                                etag=util.ComputeMD5Hex(image_data))
      self.assertEqual(response.code, 200)

      # Validate that the photo's MD5 was updated.
      ph_dict = {'photo_id': self._photo_ids[0],
                 attr_name: util.ComputeMD5Hex(image_data)}
      self._validator.ValidateUpdateDBObject(Photo, **ph_dict)

      # Expect failure on second upload with different MD5.
      new_image_data = 'really ' + image_data
      response = self._PutPhoto(self._cookie, self._episode_id, self._photo_ids[0], suffix,
                                new_image_data, content_md5=util.ComputeMD5Base64(new_image_data),
                                etag=util.ComputeMD5Hex(new_image_data))
      self.assertEqual(response.code, 400)

  def testProspectiveCookie(self):
    """Gets photos using a prospective user cookie."""
    orig_image_data = 'original image data' # Same as used in self._UploadEpisode
    self._PutPhotoAndVerify(self._cookie, 200, self._episode_id, self._photo_ids[0], '.o', orig_image_data)

    prospective_user, vp_id, ep_id = self._CreateProspectiveUser()
    prospective_cookie = self._tester.GetSecureUserCookie(user_id=prospective_user.user_id,
                                                          device_id=prospective_user.webapp_dev_id,
                                                          user_name=None,
                                                          viewpoint_id=vp_id)
    self._GetPhotoAndVerify(prospective_cookie, 200, ep_id, self._photo_ids[0], '.o')

    # Share again to the prospective user to create a second viewpoint.
    vp_id2, ep_ids2 = self._tester.ShareNew(self._cookie,
                                            [(self._episode_id, self._photo_ids)],
                                            ['Email:prospective@emailscrubbed.com'])

    # Now try to get the photo using the prospective cookie that is keyed to the first viewpoint.
    response = self._GetPhoto(prospective_cookie, ep_ids2[0], self._photo_ids[0], '.o')
    self.assertEqual(response.code, 403)

  def _GetPhotoAndVerify(self, user_cookie, exp_code, episode_id, photo_id, suffix):
    """Call _GetPhoto and verify return code equals "exp_code"."""
    response = self._GetPhoto(user_cookie, episode_id, photo_id, suffix)
    self.assertEqual(response.code, exp_code)
    if response.code == 200:
      self.assertEqual(response.headers['Cache-Control'], 'private,max-age=31536000')
    return response

  def _PutPhotoAndVerify(self, user_cookie, exp_code, episode_id, photo_id, suffix, image_data):
    """Call _PutPhoto and verify return code equals "exp_code"."""
    response = self._PutPhoto(user_cookie, episode_id, photo_id, suffix, image_data,
                              content_md5=util.ComputeMD5Base64(image_data))
    self.assertEqual(response.code, exp_code)
    return response

  def _GetPhoto(self, user_cookie, episode_id, photo_id, suffix):
    """Sends a GET request to the photo store URL for the specified
    photo and user cookie.
    """
    return self._tester.GetPhotoImage(user_cookie, episode_id, photo_id, suffix)

  def _PutPhoto(self, user_cookie, episode_id, photo_id, suffix, image_data,
                etag=None, content_md5=None):
    """Sends a PUT request to the photo store URL for the specified
    photo and user cookie. The put request body is set to "image_data".
    """
    return self._tester.PutPhotoImage(user_cookie, episode_id, photo_id, suffix, image_data,
                                      etag=etag, content_md5=content_md5)
