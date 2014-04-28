#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Uploads a number of episodes and photos and tests query of
episodes by episode, with limits and start keys.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import random
import time

from copy import copy
from functools import partial
from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.accounting import Accounting
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user import User
from viewfinder.backend.db.user_photo import UserPhoto
from viewfinder.backend.db.user_post import UserPost
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.www import json_schema
from viewfinder.backend.www.service import _AddPhotoUrls
from viewfinder.backend.www.test import service_base_test


class QueryEpisodesTestCase(service_base_test.ServiceBaseTestCase):
  def testQueryEpisodes(self):
    """Tests various episode queries.
    """
    cookie = self._cookies[0]

    self._CreateQueryAssets()
    self._all_episodes = self._validator.QueryModelObjects(Episode, hash_key=None)
    episode_count = len(self._all_episodes)

    # Query empty episode list.
    self._QueryEpisodes(cookie, self._CreateEpisodeSelection([]))

    # Query single episodes, no start or end, no limit.
    self._QueryEpisodes(cookie, self._CreateEpisodeSelection([0]))

    # Query all episodes, no start or end, no limit.
    self._QueryEpisodes(cookie, self._CreateEpisodeSelection(range(episode_count)))

    # Query every other episode, no start or end, no limit.
    self._QueryEpisodes(cookie, self._CreateEpisodeSelection(range(0, episode_count, 2)))

    # Query all episodes, limit of 1.
    self._QueryEpisodes(cookie, self._CreateEpisodeSelection(range(episode_count)), photo_limit=1)

    # Query all episodes, limit of 3.
    self._QueryEpisodes(cookie, self._CreateEpisodeSelection(range(episode_count)), photo_limit=3)

    # Query all episodes, limit of 4, fetch-all.
    self._QueryEpisodes(cookie, self._CreateEpisodeSelection(range(episode_count)), photo_limit=4,
                        fetch_all=True)

    # Query shallow episodes.
    ep_select_list = [{'episode_id': self._all_episodes[0].episode_id},
                      {'episode_id': self._all_episodes[1].episode_id, 'get_attributes': True},
                      {'episode_id': self._all_episodes[2].episode_id, 'get_photos': True},
                      {'episode_id': self._all_episodes[3].episode_id, 'get_photos': False, 'get_attributes': True},
                      {'episode_id': self._all_episodes[4].episode_id, 'get_photos': False, 'get_attributes': False},
                      {'episode_id': self._all_episodes[5].episode_id, 'get_photos': True, 'get_attributes': True},
                      {'episode_id': self._all_episodes[6].episode_id, 'get_photos': True, 'get_attributes': False},
                      {'episode_id': self._all_episodes[7].episode_id, 'get_photos': False, 'photo_start_key': '-'},
                      {'episode_id': self._all_episodes[8].episode_id, 'get_photos': True, 'photo_start_key': '-'}]
    self._QueryEpisodes(cookie, ep_select_list)

    # Query shallow episodes, limit of 1, fetch-all.
    self._QueryEpisodes(cookie, ep_select_list, photo_limit=2, fetch_all=True)

    # User #3 queries for all episodes, but only episodes he can see should be returned.
    self._QueryEpisodes(self._cookies[2], self._CreateEpisodeSelection(range(episode_count)))

    # Query for non-existent episode.
    self._QueryEpisodes(cookie, [{'episode_id': 'e-unknown'}])

  def testPostLabels(self):
    """Ensure that post labels are returned by query_episodes."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 9)

    # Hide some of the photos from the user's personal collection.
    self._tester.HidePhotos(self._cookie, [(ep_id, ph_ids[::2])])

    self._tester.QueryEpisodes(self._cookie, [self._tester.CreateEpisodeSelection(ep_id)])

  def testPhotoAccess(self):
    """Shares a subset of photos with another user and ensures that
    only that subset can be retrieved. The service_tester is already
    doing this, but correct access control is so important that it
    justifies redundant testing.
    """
    # Upload some photos and share 1/2 of them with user #2.
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 12)
    vp_id, new_ep_ids = self._tester.ShareNew(self._cookie, [(ep_id, ph_ids[::2])],
                                              [self._user2.user_id],
                                              **self._CreateViewpointDict(self._cookie))

    # Verify that no episodes are returned from QueryEpisodes against original viewpoint.
    response_dict = self._tester.QueryEpisodes(self._cookie2, [self._tester.CreateEpisodeSelection(ep_id)])
    self.assertTrue(len(response_dict['episodes']) == 0)

    # Verify that subset is returned from QueryEpisodes against new viewpoint.
    response_dict = self._tester.QueryEpisodes(self._cookie2, [self._tester.CreateEpisodeSelection(new_ep_ids[0])])
    self.assertTrue(len(response_dict['episodes'][0]['photos']) == 6)

  def testMissingMD5Attributes(self):
    """Query for photos that are missing the MD5 attributes."""
    # Objects are created manually, so no corresponding entries will be found in the real DB.
    self._skip_validation_for.append('Accounting')

    self._UpdateOrAllocateDBObject(Episode,
                                   episode_id='e1',
                                   user_id=self._user.user_id,
                                   timestamp=time.time(),
                                   parent_ep_id='e2',
                                   publish_timestamp=time.time(),
                                   viewpoint_id=self._user.private_vp_id)

    self._UpdateOrAllocateDBObject(Photo,
                                   photo_id='p1',
                                   user_id=self._user.user_id,
                                   aspect_ratio=.75, timestamp=time.time(),
                                   tn_size=5 * 1024,
                                   med_size=40 * 1024,
                                   full_size=150 * 1024,
                                   orig_size=1200 * 1024)

    self._UpdateOrAllocateDBObject(Post, episode_id='e1', photo_id='p1')

    self._tester.QueryEpisodes(self._cookie, [self._tester.CreateEpisodeSelection('e1')])

  def testProspectiveUser(self):
    """Tests that a prospective user only has access to episodes in the cookie viewpoint."""
    # Create prospective user and restricted cookie.
    self._CreateSimpleTestAssets()
    prospective_user, vp_id, ep_id = self._CreateProspectiveUser()
    prospective_cookie = self._tester.GetSecureUserCookie(user_id=prospective_user.user_id,
                                                          device_id=prospective_user.webapp_dev_id,
                                                          user_name=None,
                                                          viewpoint_id=vp_id)

    # Share again to the prospective user to create a second viewpoint.
    vp_id2, ep_ids2 = self._tester.ShareNew(self._cookie,
                                            [(self._episode_id2, self._photo_ids2)],
                                            ['Email:prospective@emailscrubbed.com'])

    # Create a system viewpoint.    
    vp_id3, ep_ids3 = self._tester.ShareNew(self._cookie,
                                            [(self._episode_id2, self._photo_ids2)],
                                            ['Email:prospective@emailscrubbed.com'])
    self._MakeSystemViewpoint(vp_id3)

    ep_selection = [self._tester.CreateEpisodeSelection(ep_id),
                    self._tester.CreateEpisodeSelection(ep_ids2[0]),
                    self._tester.CreateEpisodeSelection(ep_ids3[0]),
                    self._tester.CreateEpisodeSelection(self._episode_id)]
    response_dict = self._tester.QueryEpisodes(prospective_cookie, ep_selection)
    self.assertEqual(len(response_dict['episodes']), 2)
    self.assertEqual(response_dict['episodes'][0]['episode_id'], ep_id)

  def _CreateEpisodeSelection(self, ep_index_list):
    """Given a list of indexes into self._all_episodes, return a
    selection of the indexed episodes that can be passed to
    QueryEpisodes.
    """
    return [self._tester.CreateEpisodeSelection(self._all_episodes[i].episode_id,
                                                get_attributes=True,
                                                get_photos=True)
            for i in ep_index_list]

  def _QueryEpisodes(self, cookie, ep_select_list, photo_limit=None, fetch_all=False):
    """Repeatedly invokes the QueryEpisodes service tester.

    Sends an episode query request using "request_dict". If "fetch_all"
    is true, then queries are repeated in case of limits. Returns when
    either there are no more episodes to query, or a single query was made
    and "fetch_all" was specified as False.
    """
    while True:
      response_dict = self._tester.QueryEpisodes(cookie, ep_select_list, photo_limit=photo_limit)

      if fetch_all:
        response_ep_dict = {ep_dict['episode_id']: ep_dict for ep_dict in response_dict['episodes']}
        for ep_select in ep_select_list:
          response_ep = response_ep_dict.get(ep_select['episode_id'], None)

          if response_ep is None or 'last_key' not in response_ep:
            ep_select_list.remove(ep_select)
          else:
            ep_select['photo_start_key'] = response_ep['last_key']

        # If there are no more episodes, then return.
        if len(ep_select_list) == 0:
          break
      else:
        break

    return response_dict


def _TestQueryEpisodes(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test query_episodes
  service API call.
  """
  validator = tester.validator
  cookie_dict = tester.DecodeUserCookie(user_cookie)
  user_id = cookie_dict.get('user_id', None)
  device_id = cookie_dict.get('device_id', None)
  cookie_viewpoint_id = cookie_dict.get('viewpoint_id', None)

  # Send query_episodes request.
  actual_dict = tester.SendRequest('query_episodes', user_cookie, request_dict)

  limit = request_dict.get('photo_limit', None)

  expected_dict = {'episodes': []}
  for request_ep in request_dict['episodes']:
    episode_id = request_ep['episode_id']
    expected_ep = validator.GetModelObject(Episode, episode_id, must_exist=False)
    if expected_ep is not None:
      viewpoint_id = expected_ep.viewpoint_id
      expected_vp = validator.GetModelObject(Viewpoint, viewpoint_id)
      expected_foll = validator.GetModelObject(Follower, DBKey(user_id, viewpoint_id), must_exist=False)

      # If follower can't view, or if there is a non-matching viewpoint in the cookie, then skip the episode.
      is_cookie_viewpoint = cookie_viewpoint_id is None or cookie_viewpoint_id == viewpoint_id
      can_view_content = is_cookie_viewpoint or expected_vp.IsSystem()
      if can_view_content and expected_foll is not None and expected_foll.CanViewContent():
        expected_ep_dict = {'episode_id': episode_id}
        if request_ep.get('get_attributes', False):
          expected_ep_dict.update(expected_ep._asdict())

        if request_ep.get('get_photos', False):
          photo_dicts, last_key = _CreateExpectedPhotos(validator, user_id, device_id, episode_id, limit=limit,
                                                        start_key=request_ep.get('photo_start_key', None))
          expected_ep_dict['photos'] = photo_dicts
          if last_key is not None:
            expected_ep_dict['last_key'] = last_key

        expected_dict['episodes'].append(expected_ep_dict)

  tester._CompareResponseDicts('query_episodes', user_id, request_dict, expected_dict, actual_dict)
  return actual_dict


def _CreateExpectedPhotos(validator, user_id, device_id, episode_id, limit=None, start_key=None):
  """Return a set of photo dicts that contain all the photo metadata for
  photos in the episode with id "episode_id".
  """
  photo_dicts = []
  posts = validator.QueryModelObjects(Post, episode_id, limit=limit, start_key=start_key)

  for post in posts:
    post_dict = post._asdict()
    photo_dict = validator.GetModelObject(Photo, post.photo_id)._asdict()
    photo_dict.pop('share_seq', None)
    photo_dict.pop('client_data', None)

    # Do not return access URLs for posts which have been removed.
    if not post.IsRemoved():
      obj_store = ObjectStore.GetInstance(ObjectStore.PHOTO)
      _AddPhotoUrls(obj_store, photo_dict)

    asset_keys = set()
    user_photo = validator.GetModelObject(UserPhoto, DBKey(user_id, post.photo_id), must_exist=False)
    if user_photo is not None and user_photo.asset_keys:
      asset_keys.update(user_photo.asset_keys)
    if asset_keys:
      photo_dict['asset_keys'] = list(asset_keys)

    photo_dicts.append(photo_dict)

    post_id = Post.ConstructPostId(episode_id, post.photo_id)
    user_post = validator.GetModelObject(UserPost, DBKey(user_id, post_id), must_exist=False)
    labels = post.labels.combine()
    if user_post is not None:
      # Union together post labels and user_post labels.
      labels = labels.union(user_post.labels.combine())
    if len(labels) > 0:
      photo_dict['labels'] = list(labels)

  last_key = posts[-1].photo_id if len(posts) > 0 else None

  return (photo_dicts, last_key)
