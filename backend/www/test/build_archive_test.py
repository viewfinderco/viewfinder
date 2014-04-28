# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Test build_archive service method.
"""
import re

from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.services.email_mgr import TestEmailManager

__authors__ = ['mike@emailscrubbed.com (Mike Purtell)']

from viewfinder.backend.www.test import service_base_test

class BuildArchiveTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(BuildArchiveTestCase, self).setUp()

  def testBuildArchive(self):
    """Test successful build_archive."""
    # There's a mismatch in md5's of the photo data between model and actual.
    # That needs to be fixed before validation can be enabled for this test.
    self._validate = False
    self._CreateQueryAssets(add_test_photos=True)

    all_viewpoints = self._validator.QueryModelObjects(Viewpoint)

    # Remove one of the viewpoints.
    vp_id_to_remove = all_viewpoints[1].viewpoint_id
    self._UpdateOrAllocateDBObject(Follower, user_id=self._user.user_id,
      viewpoint_id=vp_id_to_remove, labels=[])
    self._tester.RemoveViewpoint(self._cookie, vp_id_to_remove)

    # Sanity check that the follower has the removed label.
    follower = self._RunAsync(Follower.Query, self._client, self._user.user_id, vp_id_to_remove, None)
    self.assertTrue(follower.IsRemoved())

    # Send request to build archive for default test user.
    self._tester.BuildArchive(self._cookie)

    self.assertEqual(len(TestEmailManager.Instance().emails['user1@emailscrubbed.com']), 1)

    email = TestEmailManager.Instance().emails['user1@emailscrubbed.com'][0]

    url = re.search("(?P<url>https?://[^\s]+)", email['text']).group("url")

    self.assertIsNotNone(url)

def _TestBuildArchive(tester, user_cookie):
  """Called by the ServiceTester in order to test build_archive
  service API call.
  """
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = {'email': 'user1@emailscrubbed.com'}

  # Send upload_episode request.
  actual_dict = tester.SendRequest('build_archive', user_cookie, request_dict)

  tester._CompareResponseDicts('build_archive', user_id, request_dict, {}, actual_dict)
  return actual_dict

