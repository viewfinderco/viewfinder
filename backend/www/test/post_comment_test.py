# -*- coding: utf-8 -*-
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests post_comment method.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import mock
import time

from copy import deepcopy
from functools import partial
from viewfinder.backend.base import constants, util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.www.test import service_base_test


class PostCommentTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(PostCommentTestCase, self).setUp()
    self._CreateSimpleTestAssets()
    self._vp_id, self._ep_ids = self._tester.ShareNew(self._cookie,
                                                      [(self._episode_id, self._photo_ids)],
                                                      [self._user2.user_id],
                                                      **self._CreateViewpointDict(self._cookie))

  def testPostComment(self):
    """Post multiple comments to a viewpoint."""
    # Comment not linked to any other comment.
    comment_id = self._tester.PostComment(self._cookie, self._vp_id, message='A comment 朋友你好')

    # Comments linked to previous comment, posted by another user.
    self._tester.PostComment(self._cookie2, self._vp_id, message='A linked comment', asset_id=comment_id)
    self._tester.PostComment(self._cookie2, self._vp_id, message='Multiple children', asset_id=comment_id)

    # Comment linked to photo.
    self._tester.PostComment(self._cookie, self._vp_id, message='Linked to photo', asset_id=self._photo_ids[0])

    # Post same comment twice (should be idempotent).
    comment_id = self._tester.PostComment(self._cookie, self._vp_id, timestamp=100, message='same')
    self._tester.PostComment(self._cookie, self._vp_id, comment_id=comment_id, timestamp=100, message='diff')

  def testPostAfterDay(self):
    """Post a comment after at least 24 hours have passed since viewpoint was created."""
    util._TEST_TIME += constants.SECONDS_PER_DAY
    self._tester.PostComment(self._cookie, self._vp_id, message='It took some time for me to respond')
    self._tester.PostComment(self._cookie2, self._vp_id, message='I\'m just glad you acknowledged my existence')

    util._TEST_TIME += constants.SECONDS_PER_DAY
    self._tester.PostComment(self._cookie2, self._vp_id, message='Are you there???!!!')

  def testUnrevivable(self):
    """Post a comment on a viewpoint with an unrevivable removed follower."""
    self._tester.RemoveFollowers(self._cookie, self._vp_id, [self._user2.user_id])
    self._tester.PostComment(self._cookie, self._vp_id, 'Hi there')
    response_dict = self._tester.QueryFollowed(self._cookie2)
    self.assertIn(Follower.REMOVED, response_dict['viewpoints'][0]['labels'])
    self.assertIn(Follower.UNREVIVABLE, response_dict['viewpoints'][0]['labels'])

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    self._tester.RemoveViewpoint(self._cookie2, self._vp_id)
    self._tester.PostComment(self._cookie, self._vp_id, message='Revival comment')

  def testInvalidFields(self):
    """ERROR: Try to send invalid fields."""
    for attr in ['user_id', 'device_id']:
      self.assertRaisesHttpError(400, self._tester.PostComment, self._cookie, self._vp_id, timestamp=0,
                                 asset_id='unknown asset', message='override',
                                 attr=100)

  def testPostViewpointNotFollowed(self):
    """ERROR: Try to post a comment in a viewpoint that the user does not follow."""
    self.assertRaisesHttpError(403, self._tester.PostComment, self._cookie3, self._vp_id, message='message')

  def testWrongDeviceId(self):
    """ERROR: Try to create a comment using a device id that is different
    than the one in the user cookie.
    """
    self.assertRaisesHttpError(403, self._tester.PostComment, self._cookie3, self._vp_id, message='message',
                               comment_id=Comment.ConstructCommentId(100, 1000, 1))

  def testMessageTooLarge(self):
    """Verify that a comment message that is too large fails."""
    msg = 'a' * Comment.COMMENT_SIZE_LIMIT_BYTES
    # This should be ok as it doesn't exceed the limit.
    self._tester.PostComment(self._cookie, self._vp_id, message=msg)
    # This should fail because it's one more than the limit
    self.assertRaisesHttpError(403, self._tester.PostComment, self._cookie, self._vp_id, message=msg + 'a')

def _TestPostComment(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test post_comment
  service API call.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  # Send post_comment request.
  actual_dict = tester.SendRequest('post_comment', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # post_comment is no-op if comment already exists.
  db_key = DBKey(request_dict['viewpoint_id'], request_dict['comment_id'])
  if validator.GetModelObject(Comment, db_key, must_exist=False) is None:
    # Validate Comment object.
    comment_dict = deepcopy(request_dict)
    comment_dict['user_id'] = user_id
    comment_dict.pop('headers', None)
    comment_dict.pop('activity', None)
    expected_comment = validator.ValidateCreateDBObject(Comment, **comment_dict)

    # Validate activity and notifications for the post.
    activity_dict = {'name': 'post_comment',
                     'activity_id': request_dict['activity']['activity_id'],
                     'timestamp': request_dict['activity']['timestamp'],
                     'comment_id': expected_comment.comment_id}

    if len(expected_comment.message) > NotificationManager.MAX_INLINE_COMMENT_LEN:
      start_key = Comment.ConstructCommentId(expected_comment.timestamp, 0, 0)
      invalidate = {'viewpoints': [{'viewpoint_id': expected_comment.viewpoint_id,
                                    'get_comments': True,
                                    'comment_start_key': start_key}]}
    else:
      invalidate = None

    validator.ValidateFollowerNotifications(expected_comment.viewpoint_id,
                                            activity_dict,
                                            op_dict,
                                            invalidate,
                                            sends_alert=True)

  # Validate response dict.
  tester._CompareResponseDicts('post_comment', user_id, request_dict, {}, actual_dict)
  return actual_dict
