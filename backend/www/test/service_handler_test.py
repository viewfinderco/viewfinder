# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""General service handler tests."""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import base64
import email
import json
import re
import time

from tornado import options
from viewfinder.backend.base import constants, message
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.www import base
from viewfinder.backend.www.test import service_base_test
from viewfinder.backend.www.test.service_tester import ServiceTester


class ServiceHandlerTestCase(service_base_test.ServiceBaseTestCase):
  def testEmptyContentType(self):
    """Test empty HTTP Content-Type header."""
    request_dict = {'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION}}
    response = self._RunAsync(self._tester.http_client.fetch,
                              self._tester.GetUrl('/service/query_followed'),
                              method='POST',
                              body=json.dumps(request_dict),
                              headers={'Content-Type': '',
                                       'X-Xsrftoken': 'fake_xsrf',
                                       'Cookie': 'user=%s;_xsrf=fake_xsrf' % self._cookie})
    self.assertEqual(response.code, 415)

  def testCookie(self):
    """Ensure that various fields in cookie returned by service handler are correct."""
    now = time.time()

    request_dict = {'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION}}
    response = self._RunAsync(self._tester.http_client.fetch,
                              self._tester.GetUrl('/service/query_followed'),
                              method='POST',
                              body=json.dumps(request_dict),
                              headers={'Content-Type': 'application/json',
                                       'Cookie': 'user=%s' % self._cookie})

    user_cookie_header = [h for h in response.headers.get_list('Set-Cookie') if h.startswith('user=')][-1]
    matches = re.match(r'user="?([^";]*).*expires=([^;]*)', user_cookie_header)

    # Check that cookie has "secure" and "httponly" specifiers included in it.
    self.assertIn('secure', user_cookie_header)
    self.assertIn('httponly', user_cookie_header)

    # Check that path is /.
    self.assertIn('Path=/;', user_cookie_header)

    # Check that cookie domain is suitable for any first-level sub-domain.
    self.assertIn('Domain=.%s' % options.options.domain, user_cookie_header)

    # Check that cookie expiration is at least 365 days in future.
    expires = time.mktime(email.utils.parsedate(matches.group(2)))
    self.assertGreaterEqual(expires, now + constants.SECONDS_PER_DAY * base._USER_COOKIE_EXPIRES_DAYS)

    # Check that cookie body can be decoded as base-64 encoded JSON.
    value, timestamp, sig = matches.group(1).split('|')
    cookie_dict = json.loads(base64.b64decode(value))
    self.assertEqual(cookie_dict['user_id'], self._user.user_id)
    self.assertEqual(cookie_dict['name'], self._user.name)
    self.assertEqual(cookie_dict['device_id'], self._device_ids[0])
    self.assertEqual(cookie_dict['server_version'], ServiceTester.SERVER_VERSION)

  def testErrorFormat(self):
    """Test that error returned by the service handler is properly formed."""
    request_dict = {'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION}}
    response = self._RunAsync(self._tester.http_client.fetch,
                              self._tester.GetUrl('/service/add_followers'),
                              method='POST',
                              body=json.dumps(request_dict),
                              headers={'Content-Type': 'application/json',
                                       'X-Xsrftoken': 'fake_xsrf',
                                       'Cookie': 'user=%s;_xsrf=fake_xsrf' % self._cookie})

    self.assertEqual(json.loads(response.body),
                     {'error': {'id': 'INVALID_JSON_REQUEST',
                                'method': 'add_followers',
                                'message': 'Invalid JSON request: Required field \'op_id\' is missing'}})

  def testAssetIdAltDevice(self):
    """Test construction of assets using a different device than the calling device."""
    # ------------------------------
    # Try to upload using a device not owned by the user at all.
    # ------------------------------
    ep_dict = self._CreateEpisodeDict(self._cookie)
    ep_dict['episode_id'] = Episode.ConstructEpisodeId(time.time(), self._device_ids[2], self._test_id)
    self._test_id += 1

    ph_dict = self._CreatePhotoDict(self._cookie)
    ph_dict['photo_id'] = Photo.ConstructPhotoId(time.time(), self._device_ids[2], self._test_id)
    self._test_id += 1

    self.assertRaisesHttpError(403, self._tester.UploadEpisode, self._cookie, ep_dict, [ph_dict])

    # ------------------------------
    # Upload using alternate devices owned by the user.
    # ------------------------------
    ep_dict = self._CreateEpisodeDict(self._cookie)
    ep_dict['episode_id'] = Episode.ConstructEpisodeId(time.time(), self._extra_device_id1, self._test_id)
    self._test_id += 1

    ph_dict = self._CreatePhotoDict(self._cookie)
    ph_dict['photo_id'] = Photo.ConstructPhotoId(time.time(), self._extra_device_id2, self._test_id)
    self._test_id += 1

    act_dict = self._tester.CreateActivityDict(self._cookie)
    act_dict['activity_id'] = Activity.ConstructActivityId(time.time(), self._extra_device_id1, self._test_id)
    self._test_id += 1

    self._tester.UploadEpisode(self._cookie, ep_dict, [ph_dict], act_dict)

    # ------------------------------
    # Share to a new viewpoint using alternate devices owned by the user.
    # ------------------------------
    viewpoint_id = Viewpoint.ConstructViewpointId(self._extra_device_id2, self._test_id)
    self._test_id += 1

    self._tester.ShareNew(self._cookie,
                          [(ep_dict['episode_id'], [ph_dict['photo_id']])],
                          [self._user2.user_id],
                          viewpoint_id=viewpoint_id)

    # ------------------------------
    # Post to the new viewpoint using alternate devices owned by the user.
    # ------------------------------
    comment_id = Comment.ConstructCommentId(time.time(), self._extra_device_id1, self._test_id)
    self._test_id += 1

    self._tester.PostComment(self._cookie, viewpoint_id, 'hi')
