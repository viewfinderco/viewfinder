# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Tests for Post data object.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import time
import unittest

from functools import partial

from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post

from base_test import DBBaseTestCase

class PostTestCase(DBBaseTestCase):
  def testPostIdConstruction(self):
    """Verify round-trip of various post-ids."""
    def _RoundTripPostId(original_episode_id, original_photo_id):
      post_id = Post.ConstructPostId(original_episode_id, original_photo_id)
      new_episode_id, new_photo_id = Post.DeconstructPostId(post_id)
      self.assertEqual(original_episode_id, new_episode_id)
      self.assertEqual(original_photo_id, new_photo_id)

    _RoundTripPostId(Episode.ConstructEpisodeId(time.time(), 0, 0),
                     Photo.ConstructPhotoId(time.time(), 0, 0))

    _RoundTripPostId(Episode.ConstructEpisodeId(time.time(), 1, (127, 'extra')),
                     Photo.ConstructPhotoId(time.time(), 1, (127, 'extra')))

    _RoundTripPostId(Episode.ConstructEpisodeId(time.time(), 1, (128, None)),
                     Photo.ConstructPhotoId(time.time(), 1, (128, None)))

    _RoundTripPostId(Episode.ConstructEpisodeId(time.time(), 4000000000, (5000000000, 'v123')),
                     Photo.ConstructPhotoId(time.time(), 6000000000, (7000000000, 'v123')))

  def testPostIdOrdering(self):
    """Verify that post_id sorts like (episode_id, photo_id) does."""
    def _Compare(episode_id1, photo_id1, episode_id2, photo_id2):
      result = cmp(episode_id1, episode_id2)
      if result == 0:
        result = cmp(photo_id1, photo_id2)

      post_id1 = Post.ConstructPostId(episode_id1, photo_id1)
      post_id2 = Post.ConstructPostId(episode_id2, photo_id2)
      self.assertEqual(cmp(post_id1, post_id2), result)

    timestamp = time.time()

    episode_id1 = Episode.ConstructEpisodeId(timestamp, 1, (127, None))
    episode_id2 = Episode.ConstructEpisodeId(timestamp, 1, (128, None))
    photo_id1 = Photo.ConstructPhotoId(timestamp, 1, 128)
    photo_id2 = Photo.ConstructPhotoId(timestamp, 1, 127)
    _Compare(episode_id1, photo_id1, episode_id2, photo_id2)

    episode_id1 = Episode.ConstructEpisodeId(timestamp, 127, 1)
    episode_id2 = Episode.ConstructEpisodeId(timestamp, 128, 1)
    photo_id1 = Photo.ConstructPhotoId(timestamp, 128, (1, None))
    photo_id2 = Photo.ConstructPhotoId(timestamp, 127, (1, None))
    _Compare(episode_id1, photo_id1, episode_id2, photo_id2)

    episode_id1 = Episode.ConstructEpisodeId(timestamp, 0, 0)
    episode_id2 = Episode.ConstructEpisodeId(timestamp, 0, 0)
    photo_id1 = Photo.ConstructPhotoId(timestamp, 0, 0)
    photo_id2 = Photo.ConstructPhotoId(timestamp, 0, 0)
    _Compare(episode_id1, photo_id1, episode_id2, photo_id2)

    episode_id1 = Episode.ConstructEpisodeId(timestamp, 1, 0)
    episode_id2 = Episode.ConstructEpisodeId(timestamp, 1, 1)
    photo_id1 = Photo.ConstructPhotoId(timestamp, 1, 1)
    photo_id2 = Photo.ConstructPhotoId(timestamp, 1, 0)
    _Compare(episode_id1, photo_id1, episode_id2, photo_id2)

    episode_id1 = Episode.ConstructEpisodeId(0, 0, 0)
    episode_id2 = Episode.ConstructEpisodeId(1, 0, 0)
    photo_id1 = Photo.ConstructPhotoId(1, 0, (0, None))
    photo_id2 = Photo.ConstructPhotoId(0, 0, (0, None))
    _Compare(episode_id1, photo_id1, episode_id2, photo_id2)

    episode_id1 = Episode.ConstructEpisodeId(timestamp, 0, (0, '1'))
    episode_id2 = Episode.ConstructEpisodeId(timestamp, 0, (0, '2'))
    photo_id1 = Photo.ConstructPhotoId(timestamp, 0, (0, None))
    photo_id2 = Photo.ConstructPhotoId(timestamp, 0, (0, None))
    _Compare(episode_id1, photo_id1, episode_id2, photo_id2)

    episode_id1 = Episode.ConstructEpisodeId(timestamp, 0, 0)
    episode_id2 = Episode.ConstructEpisodeId(timestamp, 0, 0)
    photo_id1 = Photo.ConstructPhotoId(timestamp, 0, (0, u'ab'))
    photo_id2 = Photo.ConstructPhotoId(timestamp, 0, (0, u'cd'))
    _Compare(episode_id1, photo_id1, episode_id2, photo_id2)
