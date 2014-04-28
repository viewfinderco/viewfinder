# -*- coding: utf-8 -*-
# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Tests for push alerts.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import re
import time
import unittest

from tornado import escape, options
from viewfinder.backend.base import util
from viewfinder.backend.base.environ import ServerEnvironment
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.alert_manager import AlertManager
from viewfinder.backend.services import sms_util
from viewfinder.backend.services.apns import TestService
from viewfinder.backend.services.email_mgr import EmailManager, TestEmailManager
from viewfinder.backend.services.sms_mgr import SMSManager, TestSMSManager
from viewfinder.backend.www.test import service_base_test


class AlertsTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(AlertsTestCase, self).setUp()
    self._CreateSimpleTestAssets()

    user_dict = {'name': 'Spencer Kimball', 'given_name': 'Spencer', 'email': 'spencer.kimball@emailscrubbed.com'}
    self._test_user, _ = self._tester.RegisterFakeViewfinderUser(user_dict)

    user_dict = {'name': 'Peter Mattis', 'given_name': 'Peter', 'email': 'peter.mattis@emailscrubbed.com'}
    self._test_user2, _ = self._tester.RegisterFakeViewfinderUser(user_dict)

  def testAlerts(self):
    """Test that correct alerts are sent for various operations."""
    # Start with share to user #2.
    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._episode_id, self._photo_ids)],
                                          [self._user2.user_id])

    notification = TestService.Instance().GetNotifications('device2')[0]
    self.assertEqual(notification, {'sound': 'default',
                                    'expiry': None,
                                    'badge': 1,
                                    'extra': {'v': vp_id},
                                    'alert': u'user1 shared 2 photos'})

    # Now share again to user #2 (same viewpoint).
    self._tester.ShareExisting(self._cookie, vp_id, [(self._episode_id2, self._photo_ids2[:1])])
    notification = TestService.Instance().GetNotifications('device2')[1]
    self.assertEqual(notification, {'sound': None,
                                    'expiry': None,
                                    'badge': 2,
                                    'extra': {'v': vp_id},
                                    'alert': u'user1 shared 1 photo'})

    # Now share again to user #2 (different viewpoint).
    vp_id2, ep_ids2 = self._tester.ShareNew(self._cookie,
                                            [(self._episode_id2, self._photo_ids2)],
                                            [self._user2.user_id],
                                            title='A title')
    notification = TestService.Instance().GetNotifications('device2')[2]
    self.assertEqual(notification, {'sound': 'default',
                                    'expiry': None,
                                    'badge': 3,
                                    'extra': {'v': vp_id2},
                                    'alert': u'user1 started a conversation: "A title"'})

    # Update user #2's viewed_seq on first viewpoint, and then post comment.
    self._tester.UpdateFollower(self._cookie2, vp_id, viewed_seq=2)
    self._tester.PostComment(self._cookie, vp_id, 'a comment')
    notification = TestService.Instance().GetNotifications('device2')[3]
    self.assertEqual(notification, {'sound': 'default',
                                    'expiry': None,
                                    'badge': 4,
                                    'extra': {'v': vp_id},
                                    'alert': u'user1: a comment'})

    # Register a contact.
    contact_dict = Contact.CreateContactDict(self._user.user_id,
                                             [('Email:andy@emailscrubbed.com', None)],
                                             util._TEST_TIME,
                                             Contact.GMAIL,
                                             name='Andy')
    self._UpdateOrAllocateDBObject(Contact, **contact_dict)

    user_dict = {'email': 'andy@emailscrubbed.com', 'name': 'Andy Kimball', 'given_name': 'Andy'}
    self._tester.RegisterViewfinderUser(user_dict)

    notification = TestService.Instance().GetNotifications('device1')[0]
    self.assertEqual(notification, {'sound': 'default',
                                    'expiry': None,
                                    'badge': None,
                                    'extra': None,
                                    'alert': 'Andy Kimball has joined Viewfinder'})

  def testAlertEmail(self):
    """Verify the alert email for various activity types."""
    def _Test(client_id, timestamp, vp_dict, episode_id, ph_dict):
      ep_dict = {'new_episode_id': episode_id,
                 'photo_ids': [ph_dict['photo_id']] if ph_dict is not None else []}
      activity_id = Activity.ConstructActivityId(timestamp, 1, client_id)
      activity = self._RunAsync(Activity.CreateShareNew,
                                self._client,
                                user_id=self._test_user.user_id,
                                viewpoint_id='v0',
                                activity_id=activity_id,
                                timestamp=timestamp,
                                update_seq=0,
                                ep_dicts=[ep_dict],
                                follower_ids=[self._test_user2.user_id])

      viewpoint, _ = self._RunAsync(Viewpoint.CreateNew, self._client, **vp_dict)
      if ph_dict is not None:
        photo = Photo.CreateFromKeywords(**ph_dict)
        self._RunAsync(photo.Update, self._client)
        viewpoint.cover_photo = {'episode_id': episode_id, 'photo_id': photo.photo_id}

      return self._RunAsync(AlertManager._FormatAlertEmail,
                            self._client,
                            self._test_user2.user_id,
                            viewpoint,
                            activity)

    self._validate = False

    # ------------------------------
    # Test cover photo (aspect ratio = 0.5).
    # ------------------------------
    timestamp = 1361931773
    vp_dict = {'viewpoint_id': 'vp1', 'user_id': 1, 'timestamp': timestamp, 'type': Viewpoint.EVENT}
    episode_id = Episode.ConstructEpisodeId(timestamp, 1, 1)
    ph_dict = {'photo_id': 'p10', 'aspect_ratio': 0.5}
    email_args = _Test(1, timestamp, vp_dict, episode_id, ph_dict)
    self.assertEqual(email_args['toname'], 'Peter Mattis')
    self.assertEqual(email_args['from'], 'info@mailer.viewfinder.co')
    self.assertEqual(email_args['fromname'], 'Spencer Kimball via Viewfinder')
    self.assertEqual(email_args['to'], 'peter.mattis@emailscrubbed.com')

    html = email_args['html']
    text = email_args['text']

    # ------------------------------
    # Test for name, cover photo url, viewpoint url, and unsubscribe url.
    # ------------------------------
    self.assertIn('Spencer Kimball', html)
    self.assertIn('Spencer Kimball', text)
    self.assertIsNotNone(re.match(r'.*\?next=%2Fepisodes%2Fefh9H-V30%2Fphotos%2Fp10\.f.*', html))
    self.assertIsNotNone(re.match(r'.*/pr/.{10}\".*', html))
    self.assertIn('/pr/', text)
    self.assertIsNotNone(re.match(r'.*\/unsubscribe\?cookie=', html))
    self.assertIn('height="416"', html)
    self.assertIn('width="208"', html)

    # ------------------------------
    # Test cover photo (aspect ratio = 2).
    # ------------------------------
    ph_dict = {'photo_id': 'p10', 'aspect_ratio': 2}
    email_args = _Test(1, timestamp, vp_dict, episode_id, ph_dict)
    self.assertIn('height="208"', email_args['html'])
    self.assertIn('width="416"', email_args['html'])
    self.assertIn('View&nbsp;All&nbsp;Photos', email_args['html'])

    # ------------------------------
    # Test no cover photo.
    # ------------------------------
    episode_id = Episode.ConstructEpisodeId(timestamp, 1, 2)
    email_args = _Test(2, timestamp, vp_dict, episode_id, ph_dict=None)
    self.assertNotIn('efh9H-V31%2Fphotos', email_args['html'])
    self.assertIn('View&nbsp;Conversation', email_args['html'])

    # ------------------------------
    # Test for no conversation title.
    # ------------------------------
    vp_dict = {'viewpoint_id': 'vp1', 'user_id': 1, 'timestamp': timestamp, 'type': Viewpoint.EVENT}
    email_args = _Test(3, timestamp, vp_dict, episode_id, ph_dict)
    self.assertNotIn('Test_Conversation_Title', email_args['html'])
    self.assertNotIn('Test_Conversation_Title', email_args['text'])

    # ------------------------------
    # Test for presence of conversation title.
    # ------------------------------
    vp_dict = {'viewpoint_id': 'vp1',
               'user_id': 1,
               'timestamp': timestamp,
               'type': Viewpoint.EVENT,
               'title': 'Test_Conversation_Title'}
    email_args = _Test(4, timestamp, vp_dict, episode_id, ph_dict)
    self.assertIn('Test_Conversation_Title', email_args['html'])
    self.assertIn('Test_Conversation_Title', email_args['text'])

  def testAlertText(self):
    """Verify the alert text for various activity types."""
    def _Test(expected_text, activity_func, client_id, sharer, viewpoint, *args, **kwargs):
      timestamp = time.time()
      activity_id = Activity.ConstructActivityId(timestamp, 1, client_id)

      activity = self._RunAsync(activity_func,
                                self._client,
                                sharer.user_id,
                                'v0',
                                activity_id,
                                timestamp,
                                0,
                                *args,
                                **kwargs)

      alert_text = self._RunAsync(AlertManager._FormatAlertText, self._client, viewpoint, activity)

      self.assertEqual(alert_text, expected_text)

    self._validate = False

    # Create user with no given name.
    user_dict = {'name': 'Andy Kimball', 'email': 'kimball.andy@emailscrubbed.com', 'verified_email': True}
    andy_user, _ = self._tester.RegisterGoogleUser(user_dict)

    # Create user with email.
    user_dict = {'email': 'andy@emailscrubbed.com', 'verified_email': True, 'gender': 'Male'}
    andy_email, _ = self._tester.RegisterGoogleUser(user_dict)

    # Create user with no name and no email.
    user_dict = {'id': 1234, 'picture': {'data': {'url': 'http://facebook.com/user2'}}}
    no_name, _ = self._tester.RegisterFacebookUser(user_dict)

    # Create viewpoint with no title.
    vp_dicts = {'viewpoint_id': 'vp1', 'user_id': 1, 'timestamp': time.time(), 'type': Viewpoint.EVENT}
    vp_no_title, _ = self._RunAsync(Viewpoint.CreateNew, self._client, **vp_dicts)

    # Create viewpoint with title.
    vp_title, _ = self._RunAsync(Viewpoint.CreateNew, self._client, title='Some title', **vp_dicts)

    # ------------------------------
    # Test share_existing alert text (no viewpoint title).
    # ------------------------------
    ep_dicts = [{'new_episode_id': Episode.ConstructEpisodeId(time.time(), 1, 1),
                 'photo_ids': [10, 11]}]
    _Test('Spencer shared 2 photos',
          Activity.CreateShareExisting,
          1,
          self._test_user,
          vp_no_title,
          ep_dicts)

    # ------------------------------
    # Test share_existing alert text (with viewpoint title).
    # ------------------------------
    ep_dicts = [{'new_episode_id': Episode.ConstructEpisodeId(time.time(), 1, 1),
                 'photo_ids': [11]}]
    _Test('Andy Kimball shared 1 photo to: "Some title"',
          Activity.CreateShareExisting,
          2,
          andy_user,
          vp_title,
          ep_dicts)

    # ------------------------------
    # Test share_new alert text (no viewpoint title).
    # ------------------------------
    ep_dicts = [{'new_episode_id': Episode.ConstructEpisodeId(time.time(), 1, 1),
                 'photo_ids': [10]}]
    _Test('Andy Kimball shared 1 photo',
          Activity.CreateShareNew,
          3,
          andy_user,
          vp_no_title,
          ep_dicts,
          [10])

    # ------------------------------
    # Test share_new alert text (with viewpoint title).
    # ------------------------------
    ep_dicts = [{'new_episode_id': Episode.ConstructEpisodeId(time.time(), 1, 1),
                 'photo_ids': [10, 11]}]
    _Test('andy@emailscrubbed.com started a conversation: "Some title"',
          Activity.CreateShareNew,
          4,
          andy_email,
          vp_title,
          ep_dicts,
          [10])

    # ------------------------------
    # Test share_new alert text (no title, no photos).
    # ------------------------------
    _Test('A friend added you to a conversation',
          Activity.CreateShareNew,
          5,
          no_name,
          vp_no_title,
          [],
          [10])

    # ------------------------------
    # Test post_comment alert text.
    # ------------------------------
    cm_dict = {'viewpoint_id': 'vp1', 'comment_id': 'c0', 'message': 'Amazing photo'}
    self._UpdateOrAllocateDBObject(Comment, **cm_dict)
    _Test('andy@emailscrubbed.com: Amazing photo',
          Activity.CreatePostComment,
          6,
          andy_email,
          vp_title,
          cm_dict)

    # ------------------------------
    # Test add_followers alert text (no viewpoint title).
    # ------------------------------
    _Test('Spencer added you to a conversation',
          Activity.CreateAddFollowers,
          8,
          self._test_user,
          vp_no_title,
          [andy_user.user_id])

    # ------------------------------
    # Test add_followers alert text (with viewpoint title).
    # ------------------------------
    _Test('Andy Kimball added you to a conversation: "Some title"',
          Activity.CreateAddFollowers,
          9,
          andy_user,
          vp_title,
          [100, andy_email.user_id])

  def testAlertSMS(self):
    """Verify the alert SMS message for various activity types."""
    def _Test(title=None, has_photos=True):
      ep_dict = {'new_episode_id': 'e0',
                 'photo_ids': ['p0'] if has_photos else [] }
      activity = self._RunAsync(Activity.CreateShareNew,
                                self._client,
                                user_id=self._test_user.user_id,
                                viewpoint_id='v0',
                                activity_id='a0',
                                timestamp=time.time(),
                                update_seq=0,
                                ep_dicts=[ep_dict],
                                follower_ids=[self._test_user2.user_id])

      cover_photo = {'episode_id': 'e0', 'photo_id': 'p0'} if has_photos else None
      viewpoint, _ = self._RunAsync(Viewpoint.CreateNew,
                                    self._client,
                                    viewpoint_id='v0',
                                    user_id=self._test_user.user_id,
                                    timestamp=time.time(),
                                    type=Viewpoint.EVENT,
                                    title=title,
                                    cover_photo=cover_photo)

      sms_args = self._RunAsync(AlertManager._FormatAlertSMS,
                                self._client,
                                self._test_user2.user_id,
                                viewpoint,
                                activity)
      self.assertEqual(sms_args['number'], self._test_user2.phone)
      self.assertTrue(sms_util.IsOneSMSMessage(sms_args['text']))

      index = sms_args['text'].index('vfnd.co/p')
      return sms_args['text'][:index + 10]

    # Use production short domain for this test for more accuracy.
    options.options.short_domain = 'vfnd.co'

    # Set phone for user #2.
    self._test_user2.phone = '+12121234567'
    self._UpdateOrAllocateDBObject(User, user_id=self._test_user2.user_id, phone=self._test_user2.phone)

    # ------------------------------
    # Registered user, full name + title + photos.
    # ------------------------------
    self.assertEqual(_Test(title='A Convo'),
                     'Spencer shared photos titled "A Convo". See them on Viewfinder: https://vfnd.co/p0')

    # ------------------------------
    # Registered user, full name + title.
    # ------------------------------
    self.assertEqual(_Test(title='A Convo', has_photos=False),
                     'Spencer shared "A Convo" with you. See it on Viewfinder: https://vfnd.co/p0')

    # ------------------------------
    # Registered user, title with Greek characters (need to force Unicode).
    # ------------------------------
    self.assertEqual(escape.to_unicode(_Test(title='A Title Ω')),
                     u'Spencer shared "A Title Ω" on Viewfinder:\thttps://vfnd.co/p0')

    # ------------------------------
    # Registered user, full name + photos.
    # ------------------------------
    self.assertEqual(_Test(),
                     'Spencer shared photos on Viewfinder: https://vfnd.co/p0')

    # ------------------------------
    # Registered user, full name.
    # ------------------------------
    self.assertEqual(_Test(has_photos=False),
                     'Spencer shared on Viewfinder: https://vfnd.co/p0')

    # ------------------------------
    # Registered user, long Unicode title + photos.
    # ------------------------------
    self.assertEqual(_Test(title='This is a very long title that has a 朋 character in it'),
                     'Spencer shared photos on Viewfinder: https://vfnd.co/p0')

    # ------------------------------
    # Registered user, long Unicode name + photos.
    # ------------------------------
    # Update name to be long and contain Unicode-forcing chars.
    given_name = 'ààà朋友你好ààà朋友你好ààà朋友你好ààà朋友你'
    self._UpdateOrAllocateDBObject(User,
                                   user_id=self._test_user.user_id,
                                   name=given_name + ' Smith',
                                   given_name=given_name)

    self.assertEqual(escape.to_unicode(_Test()),
                     u'ààà朋友你好ààà朋友你好ààà朋友你好ààà朋友你 shared photos: https://vfnd.co/p0')

    # ------------------------------
    # Registered user, long Unicode name.
    # ------------------------------
    self.assertEqual(escape.to_unicode(_Test(has_photos=False)),
                     u'ààà朋友你好ààà朋友你好ààà朋友你好ààà朋友你 shared: https://vfnd.co/p0')

    # ------------------------------
    # Registered user, truncated name.
    # ------------------------------
    # Update name to be too long for text. 
    given_name = 'ààà朋友你好ààà朋友你好ààà朋友你好ààà朋友你好ààà朋友你好'
    self._UpdateOrAllocateDBObject(User,
                                   user_id=self._test_user.user_id,
                                   name=given_name + ' Smith',
                                   given_name=given_name)

    self.assertEqual(escape.to_unicode(_Test(has_photos=False)),
                     u'ààà朋友你好ààà朋友你好ààà朋友你好ààà朋友你好ààà朋友你 shared: https://vfnd.co/p0')

    # Restore user #1 name.
    self._UpdateOrAllocateDBObject(User,
                                   user_id=self._test_user.user_id,
                                   name='Spencer Kimball',
                                   given_name='Spencer')

    # Mark user #2 as prospective and restore name.
    self._UpdateOrAllocateDBObject(User, user_id=self._test_user2.user_id, labels=[])

    # ------------------------------
    # Prospective user, full name + title + photos.
    # ------------------------------
    self.assertEqual(_Test(title='A Convo'),
                     'Spencer Kimball shared photos titled "A Convo". See them on Viewfinder: https://vfnd.co/p0')

    # ------------------------------
    # Registered user, full name + title.
    # ------------------------------
    self.assertEqual(_Test(title='A Convo', has_photos=False),
                     'Spencer Kimball shared "A Convo" with you. See it on Viewfinder: https://vfnd.co/p0')

    # ------------------------------
    # Prospective user, title with Greek characters (need to force Unicode).
    # ------------------------------
    self.assertEqual(escape.to_unicode(_Test(title='Σ')),
                     u'Spencer Kimball shared "Σ" on Viewfinder:\thttps://vfnd.co/p0')
    self.assertEqual(escape.to_unicode(_Test(title='ΔΦΓΛΩΠΨΣΘ')),
                     u'Spencer shared "ΔΦΓΛΩΠΨΣΘ" on Viewfinder:\thttps://vfnd.co/p0')

    # ------------------------------
    # Registered user, full name + photos.
    # ------------------------------
    self.assertEqual(_Test(),
                     'Spencer Kimball shared photos on Viewfinder: https://vfnd.co/p0')

    # ------------------------------
    # Registered user, full name.
    # ------------------------------
    self.assertEqual(_Test(has_photos=False),
                     'Spencer Kimball shared on Viewfinder: https://vfnd.co/p0')

    # ------------------------------
    # Registered user, long Unicode title + photos.
    # ------------------------------
    self.assertEqual(_Test(title='This is a very long title that has a 朋 character in it'),
                     'Spencer Kimball shared photos on Viewfinder: https://vfnd.co/p0')

    # ------------------------------
    # Registered user, long Unicode name + photos.
    # ------------------------------
    # Update name to be long and contain Unicode-forcing chars.
    given_name = 'ààà朋友你好'
    self._UpdateOrAllocateDBObject(User,
                                   user_id=self._test_user.user_id,
                                   name=given_name + ' Smith',
                                   given_name=given_name)

    self.assertEqual(escape.to_unicode(_Test()),
                     u'ààà朋友你好 Smith shared photos on Viewfinder: https://vfnd.co/p0')

    # ------------------------------
    # Registered user, long Unicode name.
    # ------------------------------
    self.assertEqual(escape.to_unicode(_Test(has_photos=False)),
                     u'ààà朋友你好 Smith shared on Viewfinder: https://vfnd.co/p0')

    # ------------------------------
    # Registered user, truncated name.
    # ------------------------------
    # Update name to be too long for text. 
    given_name = 'ààà朋友你好ààà朋友你好ààà朋友你好ààà朋友你好ààà朋友你好'
    self._UpdateOrAllocateDBObject(User,
                                   user_id=self._test_user.user_id,
                                   name=given_name + ' Smith',
                                   given_name=given_name)

    self.assertEqual(escape.to_unicode(_Test(has_photos=False)),
                     u'ààà朋友你好ààà朋友你好ààà朋友你 shared on Viewfinder: https://vfnd.co/p0')
