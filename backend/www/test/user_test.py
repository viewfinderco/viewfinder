#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Creates and tests various user types.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

from tornado import httpclient
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.user import User
from viewfinder.backend.www import service
from viewfinder.backend.www.test import service_base_test

class UserTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(UserTestCase, self).setUp()
    self._CreateSimpleTestAssets()
    self._prospective_user, _, _ = self._CreateProspectiveUser()
    self._prospective_cookie = self._GetSecureUserCookie(user=self._prospective_user,
                                                         device_id=self._prospective_user.webapp_dev_id)

  def testProspectiveUserPermissions(self):
    """Verify that all allow_prospective service methods can be called by a
    prospective user, and that all other methods result in a permission
    error.
    """
    allow_prospective_names = set(['query_episodes', 'query_users', 'query_viewpoints', 'query_followed'])
    for name, method in service.ServiceHandler.SERVICE_MAP.items():
      self.assertEqual(name in allow_prospective_names, method.allow_prospective)

      # allow_prospective methods will fail because request is ill-formed, whereas other methods will fail
      # with permission error, since prospective user should not have access to those methods.
      try:
        self._SendRequest(name, self._prospective_cookie, {})
        self.assertTrue(name in allow_prospective_names)
      except httpclient.HTTPError as e:
        if name in allow_prospective_names:
          self.assertEqual(e.code, 400)
        else:
          self.assertEqual(e.code, 403)

  def testInvalidUser(self):
    """ERROR: Test various invalid and missing cookies."""
    # Invalid user_id.
    bad_cookie = self._tester.GetSecureUserCookie(1000, 1000, 'andy')
    self.assertRaisesHttpError(401, self._SendRequest, 'query_episodes', bad_cookie, {})

    # Missing fields.
    bad_cookie = self._tester.EncodeUserCookie({})
    self.assertRaisesHttpError(401, self._SendRequest, 'query_episodes', bad_cookie, {})

    # Missing cookie.
    response = self._RunAsync(self._tester.http_client.fetch,
                              self._tester.GetUrl('/service/query_episodes'),
                              method='POST', body='{}',
                              headers={'Content-Type': 'application/json',
                                       'X-Xsrftoken': 'fake_xsrf',
                                       'Cookie': '_xsrf=fake_xsrf'})
    self.assertEqual(response.code, 401)
