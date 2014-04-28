# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Tests for Photo data object.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import time

from functools import partial

from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.photo import Photo

from base_test import DBBaseTestCase

class PhotoTestCase(DBBaseTestCase):
  def testPhotoIdSortOrder(self):
    """Create a series of photo ids and verify sort order. Sort order
    is by time first (from newest to oldest), then from oldest to newest
    device id, then from oldest to newest device photo id.
    """
    # attributes are a tuple of time, device id, and device photo id.
    photo_attributes = [(100, 1, 1), (100, 1, 2), (100, 1, 3),
                        (100, 2, 1), (100, 2, 2), (100, 2, 3),
                        (99, 1, 3), (99, 2, 2), (99, 3, 1),
                        (98, 3, 1), (97, 2, 1), (96, 1, 1)]
    photo_ids = [Photo.ConstructPhotoId(p[0], p[1], p[2]) for p in photo_attributes]
    self.assertEqual(photo_ids, sorted(photo_ids))

  @async_test
  def testQuery(self):
    """Verify photo creation and query by photo id."""
    def _OnQuery(p, p2):
      self.assertEqual(p2.caption, p.caption)
      self.assertEqual(p2.photo_id, p.photo_id)
      self.stop()

    def _OnCreatePhoto(p):
      Photo.Query(self._client, p.photo_id, None, partial(_OnQuery, p))

    photo_id = Photo.ConstructPhotoId(time.time(), self._mobile_dev.device_id, 1)
    episode_id = Episode.ConstructEpisodeId(time.time(), self._mobile_dev.device_id, 2)
    p_dict = {'photo_id': photo_id,
              'episode_id' : episode_id,
              'user_id': self._user.user_id,
              'caption': 'a photo'}
    Photo.CreateNew(self._client, callback=_OnCreatePhoto, **p_dict)

  @async_test
  def testUpdateAttribute(self):
    """Verify update of a photo attribute."""
    def _OnUpdate(p):
      p.aspect_ratio = None
      p.Update(self._client, self.stop)

    def _OnQuery(p):
      p.content_type = 'image/png'
      p.Update(self._client, partial(_OnUpdate, p))

    def _OnCreatePhoto(p):
      Photo.Query(self._client, p.photo_id, None, _OnQuery)

    photo_id = Photo.ConstructPhotoId(time.time(), self._mobile_dev.device_id, 1)
    episode_id = Episode.ConstructEpisodeId(time.time(), self._mobile_dev.device_id, 2)
    p_dict = {'photo_id': photo_id,
              'episode_id' : episode_id,
              'user_id': self._user.user_id,
              'caption': 'A Photo'}
    Photo.CreateNew(self._client, callback=_OnCreatePhoto, **p_dict)

  @async_test
  def testMissing(self):
    """Verify query for a missing photo fails."""
    def _OnQuery(p):
      assert False, 'photo query should fail with missing key'
    def _OnMissing(type, value, traceback):
      self.stop()
      return True

    with util.MonoBarrier(_OnQuery, on_exception=_OnMissing) as b:
      Photo.Query(self._client, str(1L << 63), None, b.Callback())
