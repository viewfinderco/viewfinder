# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for Episode data object.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import time

from viewfinder.backend.base.exceptions import PermissionError
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.op_context import EnterOpContext

from base_test import DBBaseTestCase

class EpisodeTestCase(DBBaseTestCase):
  def testCreateAndUpdate(self):
    """Creates a episode with id pre-allocated on mobile device. Then updates the episode."""
    with EnterOpContext(Operation(1, 'o1')):
      timestamp = time.time()
      episode_id = Episode.ConstructEpisodeId(timestamp, self._mobile_dev.device_id, 15)
      ep_dict = {'user_id': self._user.user_id,
                 'episode_id': episode_id,
                 'viewpoint_id': self._user.private_vp_id,
                 'timestamp': time.time(),
                 'publish_timestamp': time.time(),
                 'description': 'yada yada this is a episode',
                 'title': 'Episode #1'}

      episode = self._RunAsync(Episode.CreateNew, self._client, **ep_dict)
      episode._version = None
      self.assertEqual(ep_dict, episode._asdict())

      update_dict = {'episode_id': episode.episode_id,
                     'user_id': episode.user_id,
                     'description': 'updated description',
                     'title': 'Episode #1a'}
      self._RunAsync(episode.UpdateExisting, self._client, **update_dict)
      episode._version = None
      ep_dict.update(update_dict)
      self.assertEqual(ep_dict, episode._asdict())

  def testAnotherViewpoint(self):
    """Create an episode in a non-default viewpoint."""
    vp_dict = {'viewpoint_id': 'vp1', 'user_id': 1, 'timestamp': time.time(), 'type': Viewpoint.EVENT}
    self._RunAsync(Viewpoint.CreateNew, self._client, **vp_dict)

    ep_dict = {'viewpoint_id': 'vp1', 'episode_id': 'ep1', 'user_id': 1,
               'timestamp': 100, 'publish_timestamp': 100}

    episode = self._RunAsync(Episode.CreateNew, self._client, **ep_dict)
    episode._version = None
    self.assertEqual(ep_dict, episode._asdict())
