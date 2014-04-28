# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Tests for Friend data object.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import unittest
from functools import partial

from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.friend import Friend

from base_test import DBBaseTestCase

class FriendTestCase(DBBaseTestCase):
  def testMakeFriends(self):
    """Creates a bidirectional friendship between two users."""
    friend, reverse_friend = self._RunAsync(Friend.MakeFriends,
                                            self._client,
                                            self._user.user_id,
                                            self._user2.user_id)

    # Check the friends returned from make friends.
    self.assertEqual(friend.user_id, self._user.user_id)
    self.assertEqual(friend.friend_id, self._user2.user_id)
    self.assertEqual(reverse_friend.user_id, self._user2.user_id)
    self.assertEqual(reverse_friend.friend_id, self._user.user_id)

  def testOneSidedFriends(self):
    """Test friendships that are only recognized by one of the users."""
    # Create one-sided friendship.
    self._RunAsync(Friend.MakeFriendAndUpdate,
                   self._client,
                   self._user.user_id,
                   {'user_id': self._user2.user_id, 'nickname': 'Slick'})

    # Forward friend should exist.
    forward_friend = self._RunAsync(Friend.Query,
                                    self._client,
                                    self._user.user_id,
                                    self._user2.user_id,
                                    None,
                                    must_exist=False)
    self.assertIsNotNone(forward_friend)

    # Reverse friend should not exist.
    reverse_friend = self._RunAsync(Friend.Query,
                                    self._client,
                                    self._user2.user_id,
                                    self._user.user_id,
                                    None,
                                    must_exist=False)
    self.assertIsNone(reverse_friend)

    # MakeFriends should add the bi-directional friendship.
    forward_friend, reverse_friend = self._RunAsync(Friend.MakeFriends,
                                                    self._client,
                                                    self._user.user_id,
                                                    self._user2.user_id)
    self.assertIsNotNone(forward_friend)
    self.assertIsNotNone(reverse_friend)
