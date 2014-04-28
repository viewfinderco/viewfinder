# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for asset ids.

The output of this test should be used to verify the client-side
server id generation tests.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import time
import unittest

from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.asset_id import AssetIdUniquifier
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.viewpoint import Viewpoint

class IdTestCase(unittest.TestCase):
  _PRINT_RESULTS = False

  def testActivityIds(self):
    """Test activity ids."""
    self._TestIdRoundTripWithTimestamp(Activity.ConstructActivityId, Activity.DeconstructActivityId)

  def testCommentIds(self):
    """Test comment ids."""
    self._TestIdRoundTripWithTimestamp(Comment.ConstructCommentId, Comment.DeconstructCommentId)

  def testEpisodeIds(self):
    """Test episode ids."""
    self._TestIdRoundTripWithTimestamp(Episode.ConstructEpisodeId, Episode.DeconstructEpisodeId)

  def testOperationIds(self):
    """Test operation ids."""
    self._TestIdRoundTrip(Operation.ConstructOperationId, Operation.DeconstructOperationId)

  def testPhotoIds(self):
    """Test photo ids."""
    self._TestIdRoundTripWithTimestamp(Photo.ConstructPhotoId, Photo.DeconstructPhotoId)

  def testViewpointIds(self):
    """Test viewpoint ids."""
    self._TestIdRoundTrip(Viewpoint.ConstructViewpointId, Viewpoint.DeconstructViewpointId)

  def _TestIdRoundTripWithTimestamp(self, construct, deconstruct):
    """Round-trip id with a timestamp."""
    def _RoundTrip(timestamp, device_id, uniquifier):
      asset_id = construct(timestamp, device_id, uniquifier)
      actual_timestamp, actual_device_id, actual_uniquifier = \
          deconstruct(asset_id)
      self.assertEqual(int(timestamp), actual_timestamp)
      self.assertEqual(device_id, actual_device_id)
      self.assertEqual(uniquifier, actual_uniquifier)
      if IdTestCase._PRINT_RESULTS:
        print '%r => %s' % ((timestamp, device_id, uniquifier), asset_id)

    _RoundTrip(0, 0, (0, None))
    _RoundTrip(1234234.123423, 127, (128, None))
    _RoundTrip(time.time(), 128, (127, None))
    _RoundTrip(time.time(), 128, (128, None))
    _RoundTrip(time.time(), 123512341234, (827348273422, None))

    _RoundTrip(0, 0, (0, 'v1234'))
    _RoundTrip(1234234.123423, 127, (128, '\n\t\r\b\0abc123\x1000'))
    _RoundTrip(time.time(), 128, (127, u'1'))
    _RoundTrip(time.time(), 128, (128, '   '))

  def _TestIdRoundTrip(self, construct, deconstruct):
    """Round-trip id."""
    def _RoundTrip(device_id, device_local_id):
      server_id = construct(device_id, device_local_id)
      actual_device_id, actual_device_local_id = deconstruct(server_id)
      self.assertEqual(device_id, actual_device_id)
      self.assertEqual(device_local_id, actual_device_local_id)
      if IdTestCase._PRINT_RESULTS:
        print '%r => %s' % ((device_id, device_local_id), server_id)

    _RoundTrip(0, (0, None))
    _RoundTrip(127, (128, None))
    _RoundTrip(128, (127, None))
    _RoundTrip(128, (128, None))
    _RoundTrip(123512341234, (827348273422, None))

    _RoundTrip(0, (0, 'v1234'))
    _RoundTrip(127, (128, '\n\t\r\b\0abc123\x1000'))
    _RoundTrip(128, (127, u'1'))
    _RoundTrip(128, (128, '   '))
