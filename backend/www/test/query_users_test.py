# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Verifies query users functionality including:

- Filter by friendships
- Filter BLOCKED friendships
- Query for own user id
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import time

from operator import itemgetter
from functools import partial
from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.friend import Friend
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.subscription import Subscription
from viewfinder.backend.db.user import User
from viewfinder.backend.www import json_schema
from viewfinder.backend.www.test import service_base_test

class QueryUsersTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(QueryUsersTestCase, self).setUp()
    self._CreateSimpleTestAssets()

    # Create new user with all the projected user fields set.
    user_dict = {'name': 'Andrew Kimball', 'given_name': 'Andy', 'family_name': 'Kimball',
                 'email': 'kimball.andy@emailscrubbed.com', 'picture': 'http://google.com/Andy',
                 'verified_email': True}
    self._andy_user, _ = self._tester.RegisterGoogleUser(user_dict)

    # Also set merged_with.
    self._UpdateOrAllocateDBObject(User,
                                   user_id=self._andy_user.user_id,
                                   merged_with=self._user2.user_id)

    # Share from user #1 to several other interesting users (including a prospective user),
    # which creates friend relationship between them.
    self._vp_id, self._ep_ids = self._tester.ShareNew(self._cookie,
                                                      [(self._episode_id, self._photo_ids)],
                                                      [self._user3.user_id,
                                                       self._andy_user.user_id,
                                                       'Local:prospective'])

  def testQueryUser(self):
    """Verify a single user query."""
    response_dict = self._tester.QueryUsers(self._cookie, [self._andy_user.user_id])
    self.assertEqual(len(response_dict['users']), 1)

  def testQueryMultiple(self):
    """Verify multiple users query."""
    response_dict = self._tester.QueryUsers(self._cookie, [self._andy_user.user_id, self._user3.user_id])
    self.assertEqual(len(response_dict['users']), 2)

  def testQuerySelf(self):
    """Verify query for own user id."""
    response_dict = self._tester.QueryUsers(self._cookie, [self._user.user_id])
    self.assertEqual(len(response_dict['users']), 1)

  def testNoFriendship(self):
    """Verify that no friendship means the user's profile won't be revealed, but that certain
    labels will be returned.
    """
    response_dict = self._tester.QueryUsers(self._cookie2, [self._user.user_id])
    self.assertEqual(response_dict['users'][0], {'labels': ['registered'], 'user_id': self._user.user_id})

  def testMinimalUser(self):
    """Verify a user with as few fields as possible."""
    user_dict = {'name': 'Andrew Kimball', 'given_name': 'Andy', 'email': 'andy@emailscrubbed.com'}
    min_user, device_id = self._tester.RegisterViewfinderUser(user_dict, {})
    cookie = self._tester.GetSecureUserCookie(min_user.user_id, device_id, 'Andy')
    response_dict = self._tester.QueryUsers(cookie, [min_user.user_id])
    self.assertEqual(response_dict['users'][0]['name'], 'Andrew Kimball')

  def testUnknown(self):
    """Verify that non-existent user results in empty record."""
    response_dict = self._tester.QueryUsers(self._cookie, [100])
    self.assertEqual(len(response_dict['users']), 0)

  def testMix(self):
    """Verify that a mix of friends, strangers, and unknown user ids
    returns correct subset.
    """
    identity = self._RunAsync(Identity.Query, self._client, 'Local:prospective', None)
    response_dict = self._tester.QueryUsers(self._cookie, [self._user.user_id,
                                                           self._user2.user_id,
                                                           self._user3.user_id,
                                                           identity.user_id,
                                                           self._andy_user.user_id,
                                                           1000])
    self.assertEqual(len(response_dict['users']), 5)

  def testLabels(self):
    """Verify that only sub-set of user labels are projected."""
    self._UpdateOrAllocateDBObject(User,
                                   user_id=self._andy_user.user_id,
                                   labels=[User.STAGING, User.REGISTERED])

    response_dict = self._tester.QueryUsers(self._cookie, [self._andy_user.user_id])
    self.assertEqual(response_dict['users'][0]['labels'], [User.REGISTERED, 'friend'])

  def testBlockedFriendship(self):
    """Verify that a blocked friendship still returns user profile info."""
    self._UpdateOrAllocateDBObject(Friend,
                                   user_id=self._andy_user.user_id,
                                   friend_id=self._user.user_id,
                                   status=Friend.BLOCKED)

    response_dict = self._tester.QueryUsers(self._cookie, [self._andy_user.user_id])
    self.assertIn('name', response_dict['users'][0])

  def testMutedFriendship(self):
    """Verify that a muted friendship can be queried."""
    self._UpdateOrAllocateDBObject(Friend,
                                   user_id=self._andy_user.user_id,
                                   friend_id=self._user.user_id,
                                   status=Friend.MUTED)

    response_dict = self._tester.QueryUsers(self._cookie, [self._andy_user.user_id])
    self.assertEqual(len(response_dict['users']), 1)

  def testAccountSettings(self):
    """Query for a user with non-empty account settings."""
    self._tester.UpdateUser(self._cookie, settings_dict={'email_alerts': 'on_share_new',
                                                         'sms_alerts': 'on_share_new',
                                                         'storage_options': ['use_cloud']})

    response_dict = self._tester.QueryUsers(self._cookie, [self._user.user_id])
    self.assertTrue('account_settings' in response_dict['users'][0]['private'])

  def testOneSidedFriendships(self):
    """Test friendships in which only one of the users considers the other a friend."""
    self._tester.UpdateFriend(self._cookie, user_id=self._user2.user_id, nickname='Jimmy John')
    response = self._tester.QueryUsers(self._cookie, [self._user2.user_id])
    self.assertEqual(response['users'][0], {'labels': ['registered'],
                                            'user_id': self._user2.user_id,
                                            'nickname': 'Jimmy John'})
    response = self._tester.QueryUsers(self._cookie2, [self._user.user_id])
    self.assertEqual(response['users'][0]['name'], 'Viewfinder User #1')

  def testNoPassword(self):
    """Test the no_password field in the user's private section."""
    response_dict = self._tester.QueryUsers(self._cookie, [self._user.user_id])
    self.assertEqual(response_dict['users'][0]['private']['no_password'], True)

    self._tester.UpdateUser(self._cookie, password='supersecure')
    response_dict = self._tester.QueryUsers(self._cookie, [self._user.user_id])
    self.assertNotIn('no_password', response_dict['users'][0]['private'])


def _TestQueryUsers(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test query_users
  service API call.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)

  def _MakeMetadataDict(friend_user, forward_friend, reverse_friend):
    user_dict = {'user_id': friend_user.user_id}

    # Certain labels are visible even to non-friends.
    labels = list(friend_user.labels.intersection([User.REGISTERED, User.TERMINATED]))

    # User profile attributes should only be visible to those who consider caller a friend.
    if reverse_friend is not None:
      util.SetIfNotNone(user_dict, 'name', friend_user.name)
      util.SetIfNotNone(user_dict, 'given_name', friend_user.given_name)
      util.SetIfNotNone(user_dict, 'family_name', friend_user.family_name)
      util.SetIfNotNone(user_dict, 'email', friend_user.email)
      util.SetIfNotNone(user_dict, 'picture', friend_user.picture)
      util.SetIfNotNone(user_dict, 'merged_with', friend_user.merged_with)
      labels.append('friend')

    user_dict['labels'] = labels

    if friend_user.user_id == user_id:
      # Subscriptions don't currently use the model so we can't access them here,
      # but since most tests don't have subscriptions we just turn off validation
      # in the ones that do.
      user_dict['private'] = {'subscriptions': [], 'user_identities': []}
      if friend_user.pwd_hash is None:
        user_dict['private']['no_password'] = True

      db_key = DBKey('us:%d' % user_id, AccountSettings.GROUP_NAME)
      settings = validator.GetModelObject(AccountSettings, db_key, must_exist=False)
      if settings is not None:
        settings_dict = user_dict['private'].setdefault('account_settings', {})
        util.SetIfNotNone(settings_dict, 'email_alerts', settings.email_alerts)
        util.SetIfNotNone(settings_dict, 'sms_alerts', settings.sms_alerts)
        util.SetIfNotEmpty(settings_dict, 'storage_options', list(settings.storage_options))

      predicate = lambda ident: ident.user_id == user_id
      for expected_ident in validator.QueryModelObjects(Identity, predicate=predicate):
        ident_dict = {'identity': expected_ident.key}
        if expected_ident.authority is not None:
          ident_dict['authority'] = expected_ident.authority

        user_dict['private']['user_identities'].append(ident_dict)


    # Add attributes assigned to the friend by the user himself (such as nickname).
    if forward_friend is not None:
      util.SetIfNotNone(user_dict, 'nickname', forward_friend.nickname)

    return user_dict

  # Send query_users request.
  actual_dict = tester.SendRequest('query_users', user_cookie, request_dict)

  expected_dict = {'users': []}

  for friend_id in request_dict['user_ids']:
    # Return user info for the user and for any friends who are not blocking the user.
    friend_user = validator.GetModelObject(User, friend_id, must_exist=False)
    if friend_user is not None:
      forward_friend = validator.GetModelObject(Friend, DBKey(user_id, friend_id), must_exist=False)
      reverse_friend = validator.GetModelObject(Friend, DBKey(friend_id, user_id), must_exist=False)
      expected_dict['users'].append(_MakeMetadataDict(friend_user, forward_friend, reverse_friend))

  tester._CompareResponseDicts('query_users', user_id, request_dict, expected_dict, actual_dict)
  return actual_dict
