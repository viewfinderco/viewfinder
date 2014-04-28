# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for querying notifications.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import contextlib
import time

from tornado.ioloop import IOLoop
from viewfinder.backend.base import util
from viewfinder.backend.db.accounting import Accounting
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.notification import Notification
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.www.test import service_base_test


class QueryNotificationsTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    self._time_adjustment = 0
    super(QueryNotificationsTestCase, self).setUp()
    self._CreateSimpleTestAssets()

  def get_new_ioloop(self):
    """Creates an IOLoop with an adjustable clock.

    Increment self._time_adjustment to advance the IOLoop's clock and trigger timeouts immediately.

    This does not use viewfinder.base.util.GetCurrentTimestamp because the IOLoop is likely to go into
    an infinite loop if time stands completely still.
    """
    return IOLoop(time_func=lambda: time.time() + self._time_adjustment)

  @contextlib.contextmanager
  def _AccelerateTime(self):
    """Speed up the IOLoop's clock by one second per iteration."""
    done = [False]
    def _Adjust():
      if not done[0]:
        self._time_adjustment += 1
        self.io_loop.add_callback(_Adjust)
    _Adjust()
    yield
    done[0] = True

  def testQueryNotificationsEmpty(self):
    """Try querying with no notifications."""
    self._validate = False

    # Delete all notifications for user #1.
    notifications = self._RunAsync(Notification.RangeQuery, self._client, self._user.user_id, None, None, None)
    for n in notifications:
      self._RunAsync(n.Delete, self._client)

    response_dict = self._tester.SendRequest('query_notifications', self._cookie, {})
    self.assertEqual(len(response_dict['notifications']), 0)

    # Scan in reverse order.
    response_dict = self._tester.SendRequest('query_notifications', self._cookie, {'scan_forward': False})
    self.assertEqual(len(response_dict['notifications']), 0)

    # Send a long-polling request.
    with self._AccelerateTime():
      real_start_time = time.time()
      ioloop_start_time = self.io_loop.time()
      # Don't use SendRequest so we can use a longer timeout on self.wait()
      self._tester.SendRequestAsync('query_notifications', self._cookie, {'max_long_poll': 60}, callback=self.stop)
      response_dict = self.wait(timeout=75)
      self.assertEqual(len(response_dict['notifications']), 0)
      real_end_time = time.time()
      ioloop_end_time = self.io_loop.time()
      # The request ran for up to max_long_poll in the artificial clock, but not in real time.
      # It should have finished just before max_long_poll expired, but the accelerated clock
      # makes it difficult to test precisely.
      self.assertGreater(ioloop_end_time - ioloop_start_time, 50)
      self.assertLess(real_end_time - real_start_time, 1)

  def testQueryNotificationsNotifications(self):
    """Simple test for querying notifications."""
    # Share in order to produce notification.
    self._tester.ShareNew(self._cookie,
                          [(self._episode_id, self._photo_ids)],
                          [self._user2.user_id])

    response_dict = self._tester.QueryNotifications(self._cookie)
    self.assertEqual(len(response_dict['notifications']), 4)

    # Long-polling requests return immediately if there are results.
    response_dict = self._tester.QueryNotifications(self._cookie, max_long_poll=60)
    self.assertEqual(len(response_dict['notifications']), 4)

    # Query again with limit.
    response_dict = self._tester.QueryNotifications(self._cookie, limit=2)
    self.assertEqual(len(response_dict['notifications']), 2)

    # Share again, post 3 comments, and query from previous high water mark.
    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._episode_id, self._photo_ids[:1])],
                                          [self._user3.user_id])
    self._PostCommentChain([self._cookie, self._cookie3], vp_id, 3)

    response_dict = self._tester.QueryNotifications(self._cookie, start_key=response_dict['last_key'])
    self.assertEqual(len(response_dict['notifications']), 6)

    # Query again with limit=1 to get clear_badges.
    response_dict = self._tester.QueryNotifications(self._cookie, start_key=response_dict['last_key'], limit=1)
    self.assertEqual(len(response_dict['notifications']), 1)
    self.assertEqual(response_dict['notifications'][0]['name'], 'clear_badges')

    # One final query with last key returns nothing.
    response_dict = self._tester.QueryNotifications(self._cookie, start_key=response_dict['last_key'],
                                                   scan_forward=True)
    self.assertEqual(len(response_dict['notifications']), 0)

    # Scan in reverse order.
    response_dict = self._tester.QueryNotifications(self._cookie, scan_forward=False)
    self.assertEqual(len(response_dict['notifications']), 9)
    self.assertEqual(response_dict['notifications'][1]['name'], 'post_comment')

    # Scan in reverse order with start_key and limit.
    start_key = str(response_dict['notifications'][1]['notification_id'])
    response_dict = self._tester.QueryNotifications(self._cookie, start_key=start_key,
                                                    limit=1, scan_forward=False)
    self.assertEqual(len(response_dict['notifications']), 1)

  def testQueryNotificationsLongPoll(self):
    """Create a notification while a long-polling request is pending."""
    # First, get the current start_key.
    response_dict = self._tester.QueryNotifications(self._cookie)
    start_key = response_dict['last_key']

    # Start the long-polling request.
    with self._AccelerateTime():
      start_time = self.io_loop.time()
      self._tester.SendRequestAsync('query_notifications', self._cookie,
                                    {'max_long_poll': 60, 'start_key': start_key},
                                    callback=self.stop)

      # Wake up after 10 seconds.
      self.io_loop.add_timeout(self.io_loop.time() + 10, lambda: self.stop('timeout'))
      response = self.wait(timeout=12)
      self.assertEqual(response, 'timeout')

    # With time at normal speed (so we don't get internal timeouts), create a share activity.
    self._tester.ShareNew(self._cookie,
                          [(self._episode_id, self._photo_ids)],
                          [self._user2.user_id])

    # Now go back to waiting for the long poll.
    with self._AccelerateTime():
      response_dict = self.wait(timeout=75)
      end_time = self.io_loop.time()
    # It completed in much less time than max_long_poll.
    self.assertLess(end_time - start_time, 30)
    self.assertEqual(len(response_dict['notifications']), 1)


  def testQueryNotificationsMultipleDevices(self):
    """Test notifications sent to multiple devices owned by same user."""
    web_cookie = self._GetSecureUserCookie(device_id=self._webapp_device_id)

    # Upload an episode.
    ep_ph_ids = self._UploadOneEpisode(self._cookie3, 2)

    # Share with user #1, who has multiple devices.
    self._tester.ShareNew(self._cookie3, [ep_ph_ids], [self._user.user_id])

    # Query notifications with non-web device first; this device should be excluded from badge=0 alert.
    self._tester.QueryNotifications(self._cookie)

    # Query same notifications with web device.
    self._tester.QueryNotifications(web_cookie)

    # Share again with user #1.
    self._tester.ShareNew(self._cookie3, [ep_ph_ids], [self._user.user_id])

    # Check notifications with web device first this time.
    self._tester.QueryNotifications(web_cookie)

    # Check same notifications with non-web device.
    self._tester.QueryNotifications(self._cookie)

  def testQueryNotificationsCoverage(self):
    """Test all notification types."""
    # Link an identity.
    self._tester.LinkFacebookUser({'id': 100}, user_cookie=self._cookie)

    # Unlink the identity
    self._tester.UnlinkIdentity(self._cookie, 'FacebookGraph:100')

    # Upload an episode.
    ep_ph_ids = self._UploadOneEpisode(self._cookie, 2)

    # Share episodes.
    vp_id, ep_ids = self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids), ep_ph_ids],
                                          [self._user2.user_id, self._user3.user_id])

    # Update an episode.
    self._tester.UpdateEpisode(self._cookie, ep_ids[0], description='An episode')

    # Post comment.
    self._tester.PostComment(self._cookie2, vp_id, message='Some comment')

    # Add follower to a viewpoint.
    self._tester.AddFollowers(self._cookie, self._user.private_vp_id, ['Local:local3'])

    # Update a viewpoint.
    self._tester.UpdateViewpoint(self._cookie, self._user.private_vp_id, title='Some title')

    # Update a follower.
    self._tester.UpdateViewpoint(self._cookie, self._user.private_vp_id, viewed_seq=2)

    # Hide photos in viewpoint.
    self._tester.HidePhotos(self._cookie, [(self._episode_id, self._photo_ids[1:])])

    # Remove photos in viewpoint.
    self._tester.RemovePhotos(self._cookie, [(self._episode_id, self._photo_ids[1:])])

    # Unshare photos.
    self._tester.Unshare(self._cookie, vp_id, [(ep_ids[0], self._photo_ids[:1])])

    # Query notifications with all users.
    self._tester.QueryNotifications(self._cookie)
    self._tester.QueryNotifications(self._cookie2)
    self._tester.QueryNotifications(self._cookie3)

  def testCommentInlining(self):
    """Test inlining of comments in notifications."""
    # Create comment that shouldn't be in-lined.
    message = 'a' * NotificationManager.MAX_INLINE_COMMENT_LEN
    self._tester.PostComment(self._cookie, self._user.private_vp_id, message=message)

    # Create comment with long message that shouldn't be in-lined.
    self._tester.PostComment(self._cookie, self._user.private_vp_id, message + 'b')

    response_dict = self._tester.QueryNotifications(self._cookie, limit=2, scan_forward=False)
    self.assertTrue('comment' not in response_dict['notifications'][0]['inline'])
    self.assertTrue('invalidate' in response_dict['notifications'][0])
    self.assertTrue('comment' in response_dict['notifications'][1]['inline'])
    self.assertTrue('invalidate' not in response_dict['notifications'][1])


  def testPostCommentNotification(self):
    """Post multiple comments with increasing timestamps and verify that
    earliest notification's start_key covers them all.
    """
    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._episode_id, self._photo_ids)],
                                          [self._user2.user_id])

    timestamp = time.time()
    message = 'a' * (NotificationManager.MAX_INLINE_COMMENT_LEN + 1)
    comment_id1 = self._tester.PostComment(self._cookie, vp_id, timestamp=timestamp, message=message)
    comment_id2 = self._tester.PostComment(self._cookie, vp_id, timestamp=timestamp + 1, message=message)
    comment_id3 = self._tester.PostComment(self._cookie, vp_id, timestamp=timestamp + 2, message=message)

    response_dict = self._tester.QueryNotifications(self._cookie)
    for n in response_dict['notifications']:
      for vp in n['invalidate'].get('viewpoints', []):
        if 'comment_start_key' in vp:
          # Get first post_comment notification and verify the start_key is less than each of the
          # comment ids.
          start_key = vp['comment_start_key']
          self.assertLess(start_key, comment_id1)
          self.assertLess(start_key, comment_id2)
          self.assertLess(start_key, comment_id3)
          return


def _TestQueryNotifications(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test query_notifications
  service API call.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)

  def _MakeNotificationDict(notification):
    """Create a viewpoint dict from the followed object plus its
    referenced viewpoint object.
    """
    notification_dict = {'notification_id': notification.notification_id,
                         'name': notification.name,
                         'sender_id': notification.sender_id,
                         'timestamp': notification.timestamp}

    util.SetIfNotNone(notification_dict, 'op_id', notification.op_id)

    if notification.update_seq is not None or notification.viewed_seq is not None:
      vp_dict = notification_dict.setdefault('inline', {}).setdefault('viewpoint', {})
      vp_dict['viewpoint_id'] = notification.viewpoint_id
      util.SetIfNotNone(vp_dict, 'update_seq', notification.update_seq)
      util.SetIfNotNone(vp_dict, 'viewed_seq', notification.viewed_seq)

    if notification.activity_id is not None:
      viewpoint_id = notification.viewpoint_id
      activity = validator.GetModelObject(Activity, DBKey(viewpoint_id, notification.activity_id))
      activity_dict = activity.MakeMetadataDict()
      notification_dict.setdefault('inline', {})['activity'] = activity_dict

      if activity.name == 'post_comment' and notification.invalidate is None:
        comment_id = activity_dict['post_comment']['comment_id']
        comment = validator.GetModelObject(Comment, DBKey(viewpoint_id, comment_id))
        notification_dict['inline']['comment'] = comment._asdict()

    invalidate = notification.GetInvalidate()
    if invalidate is not None:
      invalidate.pop('headers')
      notification_dict['invalidate'] = invalidate

    return notification_dict

  def _MakeUsageDict():
    """Lookup the user's accounting entries and build a USAGE_METADATA dict."""
    # Make sure that the accounting model is up-to-date.
    validator.ValidateAccounting()

    user_hash = '%s:%d' % (Accounting.USER_SIZE, user_id)

    def _AccountingAsDict(sort_key):
      act = validator.GetModelObject(Accounting, DBKey(user_hash, sort_key), must_exist=False)
      if act is None:
        return None
      act_dict = act._asdict()
      # GetModelObject just returns everything, with no possibility of selecting the columns.
      act_dict.pop('hash_key', None)
      act_dict.pop('sort_key', None)
      act_dict.pop('op_ids', None)
      return act_dict

    usage_dict = {}
    util.SetIfNotNone(usage_dict, 'owned_by', _AccountingAsDict(Accounting.OWNED_BY))
    util.SetIfNotNone(usage_dict, 'shared_by', _AccountingAsDict(Accounting.SHARED_BY))
    util.SetIfNotNone(usage_dict, 'visible_to', _AccountingAsDict(Accounting.VISIBLE_TO))
    if len(usage_dict.keys()) > 0:
      return usage_dict
    return None

  # Send query_notifications request.
  actual_dict = tester.SendRequest('query_notifications', user_cookie, request_dict)

  # Build expected response dict.
  start_key = int(request_dict['start_key']) if 'start_key' in request_dict else None
  limit = request_dict.get('limit', None)
  scan_forward = request_dict.get('scan_forward', True)
  notifications = validator.QueryModelObjects(Notification,
                                              user_id,
                                              start_key=start_key,
                                              limit=limit,
                                              query_forward=scan_forward)

  expected_dict = {'notifications': [_MakeNotificationDict(n) for n in notifications]}
  if len(notifications) > 0:
    expected_dict['last_key'] = '%015d' % notifications[-1].notification_id
  if len(expected_dict['notifications']) > 0:
    usage_dict = _MakeUsageDict()
    if usage_dict is not None:
      last_notification = expected_dict['notifications'][-1]
      last_notification.setdefault('inline', {})['user'] = { 'usage': usage_dict }

  # Create a clear_badges notification if badge needs to be reset.
  notifications = validator.QueryModelObjects(Notification, user_id)
  last_notification = notifications[-1] if notifications else None
  if last_notification is not None and last_notification.badge != 0 and scan_forward:
    validator.ValidateCreateDBObject(Notification,
                                     notification_id=last_notification.notification_id + 1,
                                     user_id=user_id,
                                     name='clear_badges',
                                     timestamp=util._TEST_TIME,
                                     sender_id=user_id,
                                     sender_device_id=device_id,
                                     badge=0)

  tester._CompareResponseDicts('query_notifications', user_id, request_dict, expected_dict, actual_dict)
  return actual_dict
