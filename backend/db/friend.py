# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Friend relation.

Viewfinder friends define a relationship between two users predicated on confirmation of photo
sharing permission. Each friend has an associated 'status', which can be:

  - 'friend':  user has been marked as a friend; however, that user may not have the reverse
               friendship object.
  - 'muted':   a friend who has attained special status as an unwanted irritant. Content shared
               from these friends is not shown, though still received and can be retrieved.
  - 'blocked': a friend who has attained special status as an unwanted irritant. These users will
               not show up in suggestions lists and cannot be contacted for sharing.

Friends are different than contacts. Contacts are the full spectrum of social connections. A
contact doesn't become a viewfinder friend until a share has been completed.

NOTE: Next comment is outdated, but we may re-enable something similar in future.
The 'colocated_shares', 'total_shares', 'last_colocated' and 'last_share' values are used to
quantify the strength of the sharing relationship. Each time the users in a friend relationship
are co-located, 'colocated_shares' is decayed based on 'last_colocated' and the current time
and updated either with a +1 if the sharing occurs or a -1 if not. 'total_shares' is similarly
updated, though not just when the users are co-located, but on every share that a user initiates.

  Friend: viewfinder friend information
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import logging
import math

from functools import partial
from tornado import gen
from viewfinder.backend.base import util
from viewfinder.backend.base.exceptions import NotFoundError
from viewfinder.backend.db import db_client, vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.range_base import DBRangeObject
from viewfinder.backend.op.notification_manager import NotificationManager


@DBObject.map_table_attributes
class Friend(DBRangeObject):
  """Viewfinder friend data object."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.FRIEND)

  FRIEND = 'friend'
  MUTED = 'muted'
  BLOCKED = 'blocked'

  FRIEND_ATTRIBUTES = set(['nickname'])
  """Subset of friend attributes that should be projected to the user."""

  _SHARE_HALF_LIFE = 60 * 60 * 24 * 30  # 1 month

  def __init__(self, user_id=None, friend_id=None):
    super(Friend, self).__init__()
    self.user_id = user_id
    self.friend_id = friend_id
    self.status = Friend.FRIEND

  def IsBlocked(self):
    """Returns true if the "friend" identified by self.friend_id is blocked."""
    return self.status == Friend.BLOCKED

  def DecayShares(self, timestamp):
    """Decays 'total_shares' and 'colocated_shares' based on 'timestamp'. Updates 'last_share'
    and 'last_colocated' to 'timestamp'.
    """
    def _ComputeDecay(shares, last_time):
      if last_time is None:
        assert shares is None, shares
        return 0
      decay = math.exp(-math.log(2) * (timestamp - last_time) /
                        Friend._SHARE_HALF_LIFE)
      return shares * decay

    self.total_shares = _ComputeDecay(self.total_shares, self.last_share)
    self.last_share = timestamp
    self.colocated_shares = _ComputeDecay(self.colocated_shares, self.last_colocated)
    self.last_colocated = timestamp

  def IncrementShares(self, timestamp, shared, colocated):
    """Decays and updates 'total_shares' and 'last_share' based on whether sharing occurred
    ('shared'==True). If 'colocated', the 'colocated_shares' and 'last_colocated' are updated
    similarly.
    """
    self.DecayShares(timestamp)
    self.total_shares += (1.0 if shared else -1.0)
    if colocated:
      self.colocated_shares += (1.0 if shared else -1.0)

  @classmethod
  @gen.engine
  def MakeFriends(cls, client, user_id, friend_id, callback):
    """Creates a bi-directional friendship between user_id and friend_id if it does not already
    exist. Invokes the callback with the pair of friendship objects:
      [(user_id=>friend_id), (friend_id=>user_id)]
    """
    from viewfinder.backend.db.user import User

    # Determine whether one or both sides of the friendship are missing.
    forward_friend, reverse_friend = \
      yield [gen.Task(Friend.Query, client, user_id, friend_id, None, must_exist=False),
             gen.Task(Friend.Query, client, friend_id, user_id, None, must_exist=False)]

    # Make sure that both sides of the friendship have been created.
    if forward_friend is None:
      forward_friend = Friend.CreateFromKeywords(user_id=user_id, friend_id=friend_id, status=Friend.FRIEND)
      yield gen.Task(forward_friend.Update, client)

    if reverse_friend is None:
      reverse_friend = Friend.CreateFromKeywords(user_id=friend_id, friend_id=user_id, status=Friend.FRIEND)
      yield gen.Task(reverse_friend.Update, client)

    callback((forward_friend, reverse_friend))

  @classmethod
  @gen.engine
  def MakeFriendsWithGroup(cls, client, user_ids, callback):
    """Creates bi-directional friendships between all the specified users. Each user will be
    friends with every other user.
    """
    yield [gen.Task(Friend.MakeFriends, client, user_id, friend_id)
           for index, user_id in enumerate(user_ids)
           for friend_id in user_ids[index + 1:]
           if user_id != friend_id]
    callback()

  @classmethod
  @gen.engine
  def MakeFriendAndUpdate(cls, client, user_id, friend_dict, callback):
    """Ensures that the given user has at least a one-way friend relationship with the given
    friend. Updates the friend relationship attributes with those given in "friend_dict".
    """
    from viewfinder.backend.db.user import User

    friend = yield gen.Task(Friend.Query, client, user_id, friend_dict['user_id'], None, must_exist=False)

    if friend is None:
      # Ensure that the friend exists as user in the system.
      friend_user = yield gen.Task(User.Query, client, friend_dict['user_id'], None, must_exist=False)
      if friend_user is None:
        raise NotFoundError('User %d does not exist.' % friend_dict['user_id'])

      # Create a one-way friend relationship from the calling user to the friend user.
      friend = Friend.CreateFromKeywords(user_id=user_id, friend_id=friend_dict['user_id'], status=Friend.FRIEND)

    # Update all given attributes.
    assert friend_dict['user_id'] == friend.friend_id, (friend_dict, friend)
    for key, value in friend_dict.iteritems():
      if key != 'user_id':
        assert key in Friend.FRIEND_ATTRIBUTES, friend_dict
        setattr(friend, key, value)

    yield gen.Task(friend.Update, client)
    callback()

  @classmethod
  @gen.engine
  def UpdateOperation(cls, client, callback, user_id, friend):
    """Updates friend metadata for the relationship between the given user and friend."""
    # Update the metadata.
    yield gen.Task(Friend.MakeFriendAndUpdate, client, user_id, friend)

    # Send notifications to all the calling user's devices.
    yield NotificationManager.NotifyUpdateFriend(client, friend)

    callback()
