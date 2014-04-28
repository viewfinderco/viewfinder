# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Test saving photos to a default viewpoint.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import mock
import time

from copy import deepcopy
from functools import partial
from operator import itemgetter
from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user import User
from viewfinder.backend.www.test import service_base_test


class SavePhotosTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(SavePhotosTestCase, self).setUp()
    self._CreateSimpleTestAssets()

    self._existing_vp_id, existing_ep_ids = self._tester.ShareNew(self._cookie,
                                                                  [(self._episode_id, self._photo_ids)],
                                                                  [self._user2.user_id],
                                                                  **self._CreateViewpointDict(self._cookie))
    self._existing_ep_id = existing_ep_ids[0]

  def testSave(self):
    """Save a single photo to the default viewpoint."""
    self._tester.SavePhotos(self._cookie, [(self._existing_ep_id, self._photo_ids[:1])])

  def testSaveMultiple(self):
    """Save two photos to the default viewpoint."""
    self._tester.SavePhotos(self._cookie, [(self._existing_ep_id, self._photo_ids)])

  def testSaveToSelf(self):
    """Save photos from default viewpoint to default viewpoint."""
    self._tester.SavePhotos(self._cookie, [(self._episode_id, self._photo_ids)])

  def testSaveNoEpisodes(self):
    """Save empty episode list."""
    self._tester.SavePhotos(self._cookie, [])

  def testSaveMultipleEpisodes(self):
    """Save photos from multiple episodes."""
    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._episode_id2, self._photo_ids2)],
                                          [self._user3.user_id],
                                          **self._CreateViewpointDict(self._cookie))

    self._tester.SavePhotos(self._cookie,
                            [(self._existing_ep_id, self._photo_ids),
                             (ep_ids[0], self._photo_ids2)])

  def testSaveDuplicatePhotos(self):
    """Save same photos from same source episode to same target episode."""
    self._tester.SavePhotos(self._cookie, [(self._existing_ep_id, self._photo_ids)])
    self._tester.SavePhotos(self._cookie, [(self._existing_ep_id, self._photo_ids[:1])])
    self._tester.SavePhotos(self._cookie, [(self._existing_ep_id, self._photo_ids[1:])])

  def testSaveSameEpisode(self):
    """Save different photos from same source episode to same target episode."""
    self._tester.SavePhotos(self._cookie, [(self._existing_ep_id, self._photo_ids[:1])])
    self._tester.SavePhotos(self._cookie, [(self._existing_ep_id, self._photo_ids[1:])])

  def testSaveDifferentUser(self):
    """Save episode created by a different user."""
    self._tester.SavePhotos(self._cookie2, [(self._existing_ep_id, self._photo_ids)])

  def testSaveDuplicatePhotos(self):
    """Save same photos from same source episode to same target episode in default viewpoint."""
    new_episode_id = Episode.ConstructEpisodeId(time.time(), self._device_ids[0], self._test_id)
    self._test_id += 1
    share_list = [{'existing_episode_id': self._existing_ep_id,
                   'new_episode_id': new_episode_id,
                   'photo_ids': self._photo_ids}]
    self._tester.SavePhotos(self._cookie, share_list)
    self._tester.SavePhotos(self._cookie, share_list)

  def testSaveToSameEpisode(self):
    """Save multiple photos to same target episode in default viewpoint."""
    timestamp = time.time()
    new_episode_id = Episode.ConstructEpisodeId(timestamp, self._device_ids[0], self._test_id)
    self._test_id += 1
    share_dict1 = {'existing_episode_id': self._existing_ep_id,
                   'new_episode_id': new_episode_id,
                   'photo_ids': self._photo_ids[:1]}
    share_dict2 = {'existing_episode_id': self._existing_ep_id,
                   'new_episode_id': new_episode_id,
                   'photo_ids': self._photo_ids[1:]}

    self._tester.SavePhotos(self._cookie, [share_dict1, share_dict2])

  def testSaveAfterRemove(self):
    """Save photos after having removed them."""
    # Save photos into user #2's default viewpoint.
    ep_ids = self._tester.SavePhotos(self._cookie2, [(self._existing_ep_id, self._photo_ids)])

    # Remove photo from the viewpoint.
    self._tester.RemovePhotos(self._cookie2, [(ep_ids[0], self._photo_ids[:1])])
    post = self._RunAsync(Post.Query, self._client, ep_ids[0], self._photo_ids[0], None)
    self.assertIn(Post.REMOVED, post.labels)

    # Save again, expecting the REMOVED label to be deleted.
    self._tester.SavePhotos(self._cookie2,
                            [{'existing_episode_id': self._existing_ep_id,
                              'new_episode_id': ep_ids[0],
                              'photo_ids': self._photo_ids}])
    post = self._RunAsync(Post.Query, self._client, ep_ids[0], self._photo_ids[0], None)
    self.assertNotIn(Post.REMOVED, post.labels)

  def testSaveAfterUnshare(self):
    """Save photos after having unshared them."""
    # Save photos into user #2's default viewpoint.
    ep_ids = self._tester.SavePhotos(self._cookie2, [(self._existing_ep_id, self._photo_ids)])

    # Unshare photo from the viewpoint.
    self._tester.Unshare(self._cookie2, self._user2.private_vp_id, [(ep_ids[0], self._photo_ids[:1])])
    post = self._RunAsync(Post.Query, self._client, ep_ids[0], self._photo_ids[0], None)
    self.assertIn(Post.UNSHARED, post.labels)

    # Save again, expecting the REMOVED label to be deleted.
    self._tester.SavePhotos(self._cookie2,
                            [{'existing_episode_id': self._existing_ep_id,
                              'new_episode_id': ep_ids[0],
                              'photo_ids': self._photo_ids}])
    post = self._RunAsync(Post.Query, self._client, ep_ids[0], self._photo_ids[0], None)
    self.assertNotIn(Post.UNSHARED, post.labels)

  def testSaveOneViewpoint(self):
    """Save all episodes from single viewpoint."""
    # ------------------------------
    # Save viewpoint that doesn't exist (no-op). 
    # ------------------------------
    self._tester.SavePhotos(self._cookie2, viewpoint_ids=['vunk'])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 0)

    # ------------------------------
    # Save single episode from single viewpoint. 
    # ------------------------------
    self._tester.SavePhotos(self._cookie2, viewpoint_ids=[self._existing_vp_id])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 1)

    # ------------------------------
    # Save multiple episodes from single viewpoint. 
    # ------------------------------
    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._episode_id, self._photo_ids),
                                           (self._episode_id2, self._photo_ids2)],
                                          [self._user2.user_id, self._user3.user_id],
                                          **self._CreateViewpointDict(self._cookie))

    self._tester.SavePhotos(self._cookie2, viewpoint_ids=[vp_id])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 3)

    # ------------------------------
    # Save multiple episodes, but specify one episode explicitly. 
    # ------------------------------
    ep_save_list = [(ep_ids[0], self._photo_ids[:1])]
    self._tester.SavePhotos(self._cookie3, ep_save_list=ep_save_list, viewpoint_ids=[vp_id])
    self.assertEqual(self._CountEpisodes(self._cookie3, self._user3.private_vp_id), 2)

    # ------------------------------
    # Save multiple episodes, and specify all episodes explicitly. 
    # ------------------------------
    ep_save_list = [(ep_ids[0], []), (ep_ids[1], self._photo_ids2)]
    self._tester.SavePhotos(self._cookie, ep_save_list=ep_save_list, viewpoint_ids=[vp_id])
    self.assertEqual(self._CountEpisodes(self._cookie, self._user.private_vp_id), 4)

  def testSaveMultipleViewpoints(self):
    """Save all episodes from multiple viewpoints."""
    # ------------------------------
    # Save multiple episodes from multiple viewpoints. 
    # ------------------------------
    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._episode_id, self._photo_ids),
                                           (self._episode_id2, self._photo_ids2)],
                                          [self._user2.user_id, self._user3.user_id],
                                          **self._CreateViewpointDict(self._cookie))

    self._tester.SavePhotos(self._cookie2, viewpoint_ids=[self._existing_vp_id, vp_id])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 3)

    # ------------------------------
    # Save multiple episodes from multiple viewpoints, but specify episode explicitly. 
    # ------------------------------
    ep_save_list = [(ep_ids[0], self._photo_ids), (self._existing_ep_id, self._photo_ids)]
    self._tester.SavePhotos(self._cookie, ep_save_list=ep_save_list, viewpoint_ids=[self._existing_vp_id, vp_id])
    self.assertEqual(self._CountEpisodes(self._cookie, self._user.private_vp_id), 5)

    # ------------------------------
    # Save episode explicitly from one viewpoint, then save another entire viewpoint. 
    # ------------------------------
    vp_id2, ep_ids2 = self._tester.ShareNew(self._cookie,
                                            [(self._episode_id2, self._photo_ids2)],
                                            [self._user2.user_id, self._user3.user_id],
                                            **self._CreateViewpointDict(self._cookie))

    ep_save_list = [(self._existing_ep_id, self._photo_ids)]
    self._tester.SavePhotos(self._cookie2, ep_save_list=ep_save_list, viewpoint_ids=[vp_id2])
    self.assertEqual(self._CountEpisodes(self._cookie2, self._user2.private_vp_id), 5)

    # ------------------------------
    # Save from empty list of viewpoints. 
    # ------------------------------
    self._tester.SavePhotos(self._cookie, viewpoint_ids=[])

  def testSaveDuplicateIds(self):
    """Save duplicate episode and photo ids."""
    # ------------------------------
    # Duplicate photo ids. 
    # ------------------------------
    self._tester.SavePhotos(self._cookie,
                            [(self._existing_ep_id, self._photo_ids + self._photo_ids)])
    self.assertEqual(self._CountEpisodes(self._cookie, self._user.private_vp_id), 3)

    # ------------------------------
    # Duplicate episode ids. 
    # ------------------------------
    self._tester.SavePhotos(self._cookie,
                            [(self._existing_ep_id, self._photo_ids),
                             (self._existing_ep_id, self._photo_ids)])
    self.assertEqual(self._CountEpisodes(self._cookie, self._user.private_vp_id), 5)

    # ------------------------------
    # Save same episode to same target episode multiple times. 
    # ------------------------------
    new_episode_id = Episode.ConstructEpisodeId(time.time(), self._device_ids[0], self._test_id)
    self._test_id += 1
    self._tester.SavePhotos(self._cookie,
                            [{'existing_episode_id': self._existing_ep_id,
                              'new_episode_id': new_episode_id,
                              'photo_ids': self._photo_ids[:1]},
                             {'existing_episode_id': self._existing_ep_id,
                              'new_episode_id': new_episode_id,
                              'photo_ids': self._photo_ids}])
    self.assertEqual(self._CountEpisodes(self._cookie, self._user.private_vp_id), 6)

    # ------------------------------
    # Duplicate viewpoint ids. 
    # ------------------------------
    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._episode_id2, self._photo_ids2)],
                                          [self._user3.user_id],
                                          **self._CreateViewpointDict(self._cookie))

    self._tester.SavePhotos(self._cookie,
                            ep_save_list=[(self._existing_ep_id, self._photo_ids),
                                          (self._existing_ep_id, self._photo_ids)],
                            viewpoint_ids=[vp_id, vp_id])
    self.assertEqual(self._CountEpisodes(self._cookie, self._user.private_vp_id), 9)

  def testSaveViewpointNoPermission(self):
    """ERROR: Try to save viewpoint with no permissions."""
    self.assertRaisesHttpError(403, self._tester.SavePhotos, self._cookie3, viewpoint_ids=[self._existing_vp_id])

  def testSaveFromMultipleParents(self):
    """ERROR: Try to save to the same episode from multiple parent episodes."""
    save_ep_ids = self._tester.SavePhotos(self._cookie, [(self._existing_ep_id, self._photo_ids)])

    share_ep_ids = self._tester.ShareExisting(self._cookie,
                                              self._existing_vp_id,
                                              [(self._episode_id2, self._photo_ids2)])
    share_dict = {'existing_episode_id': share_ep_ids[0],
                  'new_episode_id': save_ep_ids[0],
                  'photo_ids': self._photo_ids}
    self.assertRaisesHttpError(400, self._tester.SavePhotos, self._cookie, [share_dict])

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    self._tester.SavePhotos(self._cookie, [(self._existing_ep_id, self._photo_ids[:1])])
    self._tester.SavePhotos(self._cookie, [(self._existing_ep_id, self._photo_ids)])

  def testSaveNoAccess(self):
    """ERROR: Try to share episodes from viewpoint which user does not follow."""
    self.assertRaisesHttpError(403, self._tester.SavePhotos, self._cookie3,
                               [(self._existing_ep_id, self._photo_ids)])

  def testSaveInvalidEpisode(self):
    """ERROR: Try to save a non-existing episode."""
    self.assertRaisesHttpError(400, self._tester.SavePhotos, self._cookie2,
                               [('eunknown', self._photo_ids)])

  def testWrongDeviceId(self):
    """ERROR: Try to create an episode using a device id that is different
    than the one in the user cookie.
    """
    save_list = [self._tester.CreateCopyDict(self._cookie2, self._existing_ep_id, self._photo_ids)]
    self.assertRaisesHttpError(403, self._tester.SavePhotos, self._cookie, save_list)

  def testSaveToSameEpisode(self):
    """ERROR: Try to save from two source episodes to the same target episode."""
    share_ep_ids = self._tester.ShareExisting(self._cookie,
                                              self._existing_vp_id,
                                              [(self._episode_id2, self._photo_ids2)])

    new_episode_id = Episode.ConstructEpisodeId(time.time(), self._device_ids[0], self._test_id)
    self._test_id += 1
    self.assertRaisesHttpError(400,
                               self._tester.SavePhotos,
                               self._cookie,
                               [{'existing_episode_id': self._existing_ep_id,
                                 'new_episode_id': new_episode_id,
                                 'photo_ids': self._photo_ids},
                                {'existing_episode_id': share_ep_ids[0],
                                 'new_episode_id': new_episode_id,
                                 'photo_ids': self._photo_ids2}])

def _TestSavePhotos(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test save_photos service API call."""
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  # Send save_photos request.
  actual_dict = tester.SendRequest('save_photos', user_cookie, request_dict)

  _ValidateSavePhotos(tester, user_id, device_id, request_dict)

  tester._CompareResponseDicts('save_photos', user_id, request_dict, {}, actual_dict)
  return actual_dict


def _ValidateSavePhotos(tester, user_id, device_id, request_dict):
  """Validates that episodes and photos listed in the request have been saved to the given
  user's default viewpoint. Validates that the correct activity and notifications have been
  created for a save_photos operation.
  """
  validator = tester.validator
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)
  user = validator.GetModelObject(User, user_id)
  request_ep_dicts = request_dict.get('episodes', [])

  # Need to validate episodes specified in the request. 
  save_ep_dicts = {}
  for ep_dict in request_ep_dicts:
    new_episode_id = ep_dict['new_episode_id']
    if new_episode_id in save_ep_dicts:
      save_ep_dicts[new_episode_id]['photo_ids'].extend(ep_dict['photo_ids'])
    else:
      save_ep_dicts[new_episode_id] = ep_dict

  # Need to validate episodes from viewpoints specified in the request. 
  if 'viewpoint_ids' in request_dict:
    for viewpoint_id in set(request_dict['viewpoint_ids']):
      source_eps = validator.QueryModelObjects(Episode, predicate=lambda e: e.viewpoint_id == viewpoint_id)
      for source_ep in source_eps:
        # Find the id of the target episode.
        query_expr = ('episode.parent_ep_id={ep_id} & episode.viewpoint_id={vp_id}',
                      {'ep_id': source_ep.episode_id, 'vp_id': user.private_vp_id})
        target_ep_key = util.GetSingleListItem(tester._RunAsync(Episode.IndexQueryKeys, validator.client, query_expr))

        posts = validator.QueryModelObjects(Post, source_ep.episode_id)
        save_ep_dicts[target_ep_key.hash_key] = {'existing_episode_id': source_ep.episode_id,
                                                 'new_episode_id': target_ep_key.hash_key,
                                                 'photo_ids': [post.photo_id for post in posts]}

  save_ep_dicts = sorted([{'existing_episode_id': ep_dict['existing_episode_id'],
                           'new_episode_id': ep_dict['new_episode_id'],
                           'photo_ids': sorted(set(ep_dict['photo_ids']))}
                          for ep_dict in save_ep_dicts.itervalues()],
                         key=itemgetter('new_episode_id'))

  # Validate all episodes and posts are created.
  validator.ValidateCopyEpisodes(op_dict, user.private_vp_id, save_ep_dicts)

  # Validate activity and notifications for the save.
  activity_dict = {'name': 'save_photos',
                   'activity_id': request_dict['activity']['activity_id'],
                   'timestamp': request_dict['activity']['timestamp'],
                   'episodes': [{'episode_id': ep_dict['new_episode_id'],
                                 'photo_ids': ep_dict['photo_ids']}
                                for ep_dict in save_ep_dicts]}

  invalidate = {'episodes': [{'episode_id': ep_dict['new_episode_id'],
                              'get_attributes': True,
                              'get_photos': True}
                             for ep_dict in save_ep_dicts]}

  validator.ValidateFollowerNotifications(user.private_vp_id,
                                          activity_dict,
                                          op_dict,
                                          invalidate)

  validator.ValidateViewpointAccounting(user.private_vp_id)
