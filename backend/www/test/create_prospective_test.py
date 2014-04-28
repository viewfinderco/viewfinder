# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for CreateProspectiveOperation.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import mock

from viewfinder.backend.base import util
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.www import system_users
from viewfinder.backend.www.system_users import CreateSystemUsers
from viewfinder.backend.www.test import service_base_test


class CreateProspectiveTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(CreateProspectiveTestCase, self).setUp()
    self._CreateSimpleTestAssets()
    self._vp_id, self._ep_id = self._ShareSimpleTestAssets([self._user2.user_id])

  def testProspectiveUser(self):
    """Test creation of a prospective user."""
    user, vp_id, ep_id = self._CreateProspectiveUser()
    self.assertEqual(user.asset_id_seq, 1)

    settings = self._RunAsync(AccountSettings.QueryByUser, self._client, user.user_id, None)
    self.assertEqual(settings.email_alerts, AccountSettings.EMAIL_ON_SHARE_NEW)
    self.assertEqual(settings.sms_alerts, AccountSettings.SMS_NONE)
    self.assertEqual(settings.push_alerts, AccountSettings.PUSH_NONE)

  @mock.patch.object(system_users, 'NARRATOR_USER', None)
  def testWelcomeUsers(self):
    """Test that users that are part of the "Welcome to Viewfinder" conversation are created."""
    def _TestUser(email):
      identity = self._RunAsync(Identity.Query, self._client, 'Email:%s' % email, None)
      self.assertEqual(identity.authority, 'Viewfinder')

      user = self._RunAsync(User.Query, self._client, identity.user_id, None)
      self.assertTrue(user.IsRegistered())
      self.assertTrue(user.IsSystem())
      self.assertEqual(user.email, email)

      settings = self._RunAsync(AccountSettings.QueryByUser, self._client, identity.user_id, None)
      self.assertEqual(settings.email_alerts, AccountSettings.EMAIL_NONE)

      return user.name, user.given_name, user.family_name

    def _TestUpload(user, upload_request):
      # Get episode that should have been uploaded.
      cookie = self._GetSecureUserCookie(user, user.webapp_dev_id)
      ep_select = self._tester.CreateEpisodeSelection(upload_request['episode']['episode_id'],
                                                      get_attributes=True,
                                                      get_photos=True)
      response_dict = self._tester.SendRequest('query_episodes', cookie, {'episodes': [ep_select]})
      ep_dict = response_dict['episodes'][0]
      self.assertEqual(len(upload_request['photos']), len(ep_dict['photos']))

      # Validate that each photo was uploaded.
      for ph_dict in response_dict['episodes'][0]['photos']:
        for suffix, size_attr in (('.f', 'full_size'), ('.m', 'med_size'), ('.t', 'tn_size')):
          response = self._tester.GetPhotoImage(cookie, ep_dict['episode_id'], ph_dict['photo_id'], suffix)
          self.assertEqual(len(response.body), ph_dict[size_attr])

    # Ensure that system users are created.
    self._RunAsync(CreateSystemUsers, self._client)

    # Verify users.
    self.assertEqual(_TestUser('narrator@emailscrubbed.com'), ('Viewfinder', 'Viewfinder', None))

    # Verify photo uploads.
    _TestUpload(system_users.NARRATOR_USER, system_users.NARRATOR_UPLOAD_PHOTOS)

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  @mock.patch.object(system_users, 'NARRATOR_USER', None)
  def testWelcomeConversation(self):
    """Test that welcome conversation is created for new users."""
    # Turn off validation, since welcome conversation is too large to validate using model.
    self._validate = False
    validator = self._tester.validator

    # Ensure that system users are created.
    self._RunAsync(CreateSystemUsers, self._client)

    # Trigger creation of two prospective users.
    request_dict = {'activity': self._tester.CreateActivityDict(self._cookie),
                    'viewpoint_id': self._vp_id,
                    'contacts': self._tester.CreateContactDicts(['Email:prospective@emailscrubbed.com', 'Email:prospective2@gmail.com'])}
    response_dict = self._tester.SendRequest('add_followers', self._cookie, request_dict)

    identity = self._RunAsync(Identity.Query, self._client, 'Email:prospective@emailscrubbed.com', None)
    user = self._RunAsync(User.Query, self._client, identity.user_id, None)

    # Validate the viewpoint.
    welcome_vp_id = Viewpoint.ConstructViewpointId(user.webapp_dev_id, 1)
    viewpoint = self._RunAsync(Viewpoint.Query, self._client, welcome_vp_id, None)

    query_expr = ('episode.parent_ep_id={id}', {'id': system_users.NARRATOR_UPLOAD_PHOTOS['episode']['episode_id']})
    cover_photo_ep = self._RunAsync(Episode.IndexQuery, self._client, query_expr, None)[0]
    cover_photo = {'episode_id': cover_photo_ep.episode_id,
                   'photo_id': system_users.NARRATOR_UPLOAD_PHOTOS['photos'][0]['photo_id']}

    validator.ValidateUpdateDBObject(Viewpoint,
                                     viewpoint_id=welcome_vp_id,
                                     user_id=system_users.NARRATOR_USER.user_id,
                                     title='Welcome...',
                                     type=Viewpoint.SYSTEM,
                                     timestamp=util._TEST_TIME,
                                     update_seq=13,
                                     cover_photo=cover_photo)

    # Validate the followers.
    followers, _ = self._RunAsync(Viewpoint.QueryFollowers, self._client, welcome_vp_id)
    for follower in followers:
      # All but the new user should have removed the viewpoint and have viewed_seq = update_seq.
      if follower.user_id != user.user_id:
        self.assertTrue(follower.IsRemoved())
        self.assertEqual(follower.viewed_seq, viewpoint.update_seq)
      else:
        self.assertTrue(not follower.IsRemoved())
        self.assertEqual(follower.viewed_seq, 0)

    # Validate the episodes and photos.
    episodes, _ = self._RunAsync(Viewpoint.QueryEpisodes, self._client, welcome_vp_id)
    self.assertEqual(len(episodes), 3)

    num_posts = sum(len(self._RunAsync(Post.RangeQuery, self._client, episode.episode_id, None, None, None))
                    for episode in episodes)
    self.assertEqual(num_posts, 9)

    cookie = self._GetSecureUserCookie(user, user.webapp_dev_id)
    vp_select = self._tester.CreateViewpointSelection(welcome_vp_id)
    response_dict = self._tester.SendRequest('query_viewpoints', cookie, {'viewpoints': [vp_select]})
    self.assertEqual(len(response_dict['viewpoints'][0]['followers']), 2)
    self.assertEqual(len(response_dict['viewpoints'][0]['activities']), 12)
    self.assertEqual(len(response_dict['viewpoints'][0]['comments']), 8)
    self.assertEqual(len(response_dict['viewpoints'][0]['episodes']), 3)

    ep_select_list = [self._tester.CreateEpisodeSelection(ep_dict['episode_id'])
                      for ep_dict in response_dict['viewpoints'][0]['episodes']]
    response_dict = self._tester.SendRequest('query_episodes', cookie, {'episodes': ep_select_list})

    self.assertEqual(len([ph_dict for ep_dict in response_dict['episodes'] for ph_dict in ep_dict['photos']]), 9)

    # Validate the accounting.
    validator.ValidateAccounting()
