# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Tests update_friend method.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

from copy import deepcopy
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.friend import Friend
from viewfinder.backend.www.test import service_base_test


class UpdateFriendTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(UpdateFriendTestCase, self).setUp()
    self._CreateSimpleTestAssets()

    # Share with another user in order to make friends with them.
    self._tester.ShareNew(self._cookie,
                          [(self._episode_id, self._photo_ids)],
                          [self._user2.user_id])

  def testUpdateFriend(self):
    """Update a friend attribute."""
    self._tester.UpdateFriend(self._cookie, user_id=self._user2.user_id, nickname='Bob')
    response = self._tester.QueryUsers(self._cookie, [self._user2.user_id])
    self.assertEqual(response['users'][0]['nickname'], 'Bob')

  def testUpdateSelf(self):
    """Update friend attributes on self."""
    self._tester.UpdateFriend(self._cookie, user_id=self._user.user_id, nickname='Frank')
    response = self._tester.QueryUsers(self._cookie, [self._user.user_id])
    self.assertEqual(response['users'][0]['nickname'], 'Frank')

  def testMultipleUpdates(self):
    """Test multiple updates of various attributes."""
    self._tester.UpdateFriend(self._cookie, user_id=self._user2.user_id)
    self._tester.UpdateFriend(self._cookie, user_id=self._user2.user_id, nickname='Jim')
    self._tester.UpdateFriend(self._cookie, user_id=self._user2.user_id, nickname='Jim Bob')
    response = self._tester.QueryUsers(self._cookie, [self._user2.user_id])
    self.assertEqual(response['users'][0]['nickname'], 'Jim Bob')

  def testClearNickname(self):
    """Set nickname, then clear it by passing null."""
    self._tester.UpdateFriend(self._cookie, user_id=self._user2.user_id, nickname='Nick')
    self._tester.UpdateFriend(self._cookie, user_id=self._user2.user_id, nickname=None)
    response = self._tester.QueryUsers(self._cookie, [self._user2.user_id])
    self.assertNotIn('nickname', response['users'][0])

  def testUpdateNonFriend(self):
    """Update user that is not currently a friend."""
    self._tester.UpdateFriend(self._cookie, user_id=self._user3.user_id, nickname='Han Solo')
    response = self._tester.QueryUsers(self._cookie, [self._user3.user_id])
    self.assertEqual(response['users'][0], {'user_id': self._user3.user_id,
                                            'nickname': 'Han Solo',
                                            'labels': ['registered']})

  def testUpdateNonUser(self):
    """ERROR: Try to update a non-existent user."""
    self.assertRaisesHttpError(404, self._tester.UpdateFriend, self._cookie, user_id=1000, nickname='Foo Bar')

  def testBadRequests(self):
    """ERROR: Send bad requests."""
    self.assertRaisesHttpError(400, self._tester.UpdateFriend, self._cookie)
    self.assertRaisesHttpError(400, self._tester.UpdateFriend, self._cookie, user_id=self._user2.user_id, friend_id=100)
    self.assertRaisesHttpError(400, self._tester.UpdateFriend, self._cookie, user_id=self._user2.user_id, nickname=5)


def _TestUpdateFriend(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test update_friend service API call."""
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  # Send update_friend request.
  actual_dict = tester.SendRequest('update_friend', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # Validate updates to the Friend object.
  friend_dict = request_dict['friend']
  friend_dict['friend_id'] = friend_dict.pop('user_id')
  friend_dict['user_id'] = user_id
  validator.ValidateUpdateDBObject(Friend, **friend_dict)

  # Validate notifications.
  invalidate = {'users': [friend_dict['friend_id']]}
  validator.ValidateNotification('update_friend', user_id, op_dict, invalidate)

  tester._CompareResponseDicts('update_friend', user_id, request_dict, {}, actual_dict)
  return actual_dict
