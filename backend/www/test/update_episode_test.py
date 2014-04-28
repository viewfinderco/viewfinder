# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests update_episode method.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import mock
import time

from copy import deepcopy
from functools import partial
from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.www.test import service_base_test

class UpdateEpisodeTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(UpdateEpisodeTestCase, self).setUp()
    self._CreateSimpleTestAssets()
    self._vp_id, self._ep_id = self._ShareSimpleTestAssets([self._user2.user_id])

  def testUpdateEpisode(self):
    """Creates a new episode and photo and updates both."""
    timestamp = time.time()

    episode_id = Episode.ConstructEpisodeId(timestamp, self._device_ids[0], 100)
    ep_dict = {'episode_id': episode_id,
               'timestamp': timestamp,
               'title': 'Episode Title'}

    photo_id = Photo.ConstructPhotoId(timestamp, self._device_ids[0], 100)
    ph_dict = {'aspect_ratio': 1.3333,
               'timestamp': time.time(),
               'tn_md5': util.ComputeMD5Hex('thumbnail image data'),
               'med_md5': util.ComputeMD5Hex('medium image data'),
               'full_md5': util.ComputeMD5Hex('full image data'),
               'orig_md5': util.ComputeMD5Hex('original image data'),
               'tn_size': 5 * 1024,
               'med_size': 10 * 1024,
               'full_size': 150 * 1024,
               'orig_size': 1200 * 1024,
               'photo_id': photo_id}

    self._tester.UploadEpisode(self._cookie, ep_dict, [ph_dict])
    self._tester.UpdateEpisode(self._cookie, episode_id, description='A newly added description')

  def testUpdateSharedEpisode(self):
    """Updates an episode that was created as part of a share."""
    self._tester.UpdateEpisode(self._cookie, self._ep_id, title='Changed title')

  def testUnrevivable(self):
    """Update an episode in a viewpoint with an unrevivable removed follower."""
    self._tester.RemoveFollowers(self._cookie, self._vp_id, [self._user2.user_id])
    self._tester.UpdateEpisode(self._cookie, self._ep_id, title='Changed title')
    response_dict = self._tester.QueryFollowed(self._cookie2)
    self.assertIn(Follower.REMOVED, response_dict['viewpoints'][0]['labels'])
    self.assertIn(Follower.UNREVIVABLE, response_dict['viewpoints'][0]['labels'])

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    self._tester.RemoveViewpoint(self._cookie2, self._vp_id)
    self._tester.UpdateEpisode(self._cookie, self._ep_id, title='Changed title')

  def testUpdateInvalidEpisode(self):
    """ERROR: Try to update an episode that does not exist."""
    self.assertRaisesHttpError(400, self._tester.UpdateEpisode, self._cookie,
                               'totally unknown, invalid, etc')

  def testUpdateReadOnlyAttribute(self):
    """ERROR: Try to update a read-only episode attribute."""
    self.assertRaisesHttpError(400, self._tester.UpdateEpisode, self._cookie, self._episode_id,
                               viewpoint_id='v-invalid')

  def testUpdateViewpointNotFollowed(self):
    """ERROR: Try to update an episode in a viewpoint that the user does
    not follow.
    """
    self.assertRaisesHttpError(403, self._tester.UpdateEpisode, self._cookie2, self._episode_id)

  def testUpdateEpisodeNotOwned(self):
    """ERROR: Try to update an episode that user did not create."""
    vp_id, ep_ids = self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)],
                                          [self._user2.user_id])
    self.assertRaisesHttpError(403, self._tester.UpdateEpisode, self._cookie2, ep_ids[0])


def _TestUpdateEpisode(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test update_episode
  service API call.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  # Send update_episode request.
  actual_dict = tester.SendRequest('update_episode', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # Validate episode.
  episode_dict = deepcopy(request_dict)
  episode_dict['user_id'] = user_id
  episode_dict.pop('headers', None)
  episode_dict.pop('activity', None)
  episode = validator.ValidateUpdateDBObject(Episode, **episode_dict)

  # Validate activity and notifications for the update.
  activity_dict = {'name': 'update_episode',
                   'activity_id': request_dict['activity']['activity_id'],
                   'timestamp': request_dict['activity']['timestamp'],
                   'episode_id': episode.episode_id}

  invalidate = {'episodes': [{'episode_id': request_dict['episode_id'],
                              'get_attributes': True}]}

  validator.ValidateFollowerNotifications(episode.viewpoint_id,
                                          activity_dict,
                                          op_dict,
                                          invalidate)

  tester._CompareResponseDicts('update_episode', user_id, request_dict, {}, actual_dict)
  return actual_dict
