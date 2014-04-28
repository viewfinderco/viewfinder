#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test staging cluster redirection.
"""

__author__ = 'mike@emailscrubbed.com (Mike Purtell)'

from tornado import options
from viewfinder.backend.base.environ import ServerEnvironment
from viewfinder.backend.db.user import User
from viewfinder.backend.www.test import service_base_test

class StagingRedirectionBaseTestCase(service_base_test.ServiceBaseTestCase):
  """Contains common setup for cases covering requests from both production and staging servers.
  """
  def setUp(self):
    super(StagingRedirectionBaseTestCase, self).setUp()

    # Validation will fail due to redirection that will happen because we're running as staging server, or because
    # user #2 is a staging user, so disable.
    self._validate = False

    # Make user #2 into a staging user.
    self._staging_user = self._user2
    self._UpdateOrAllocateDBObject(User,
                                   user_id=self._staging_user.user_id,
                                   labels=[User.REGISTERED, User.STAGING])
    self._staging_device_id = self._device_ids[1]
    self._staging_cookie = self._cookie2

    # Create cookie with webapp device id.
    self._staging_webapp_cookie = self._GetSecureUserCookie(user=self._staging_user,
                                                            device_id=self._staging_user.webapp_dev_id)

  def tearDown(self):
    # Restore options for subsequent tests and for base class cleanup.
    options.options.is_staging = None
    super(StagingRedirectionBaseTestCase, self).tearDown()

class StagingRedirectionFromStagingServerOptionTestCase(StagingRedirectionBaseTestCase):
  """Tests specific to requests to a staging server where server identified it's self as staging based on
  command line options (code path is very similar to determining server type based on EC2 environment).
  """
  def setUp(self):
    options.options.is_staging = True
    super(StagingRedirectionFromStagingServerOptionTestCase, self).setUp()

  def testRedirectStagingUserMobileClientFromStagingServer(self):
    """Send request on behalf of staging user from mobile client to staging server and expect success (not redirection).
    """
    self._SendRequest('get_calendar', self._staging_cookie,
                      {'calendars': [{'calendar_id': 'EnglishHolidays.ics', 'year': 2012}]})

  def testRedirectStagingUserWebClientFromStagingServer(self):
    """Send request on behalf of staging user from web app to staging server and expect success (no redirection).
    """
    self._SendRequest('get_calendar', self._staging_webapp_cookie,
                      {'calendars': [{'calendar_id': 'EnglishHolidays.ics', 'year': 2012}]})

  def testRedirectProductionUserWebClientFromStagingServer(self):
    """Send request on behalf of production user from web app to staging server and expect redirection to production.
    """
    exc = self.assertRaisesHttpError(301, self._SendRequest, 'get_calendar', self._cookie,
                                     {'calendars': [{'calendar_id': 'EnglishHolidays.ics', 'year': 2012}]})
    self.assertEqual(exc.response.headers['Location'], 'http://www.goviewfinder.com/service/get_calendar')
    self.assertEqual(exc.response.headers['X-VF-Staging-Redirect'], 'www.goviewfinder.com')


class StagingRedirectionFromStagingUrlTestCase(StagingRedirectionBaseTestCase):
  """Tests specific to requests to a staging server (based on request url).
  """
  def setUp(self):
    options.options.is_staging = True
    super(StagingRedirectionFromStagingUrlTestCase, self).setUp()
    self._url_host = 'staging.goviewfinder.com' # Form requests directed to staging URL

  def testRedirectStagingUserMobileClientFromStagingUrl(self):
    """Send request on behalf of staging user from mobile client to staging server and expect success (not redirection).
    """
    self._SendRequest('get_calendar', self._staging_cookie,
                      {'calendars': [{'calendar_id': 'EnglishHolidays.ics', 'year': 2012}]})

  def testRedirectStagingUserWebClientFromStagingUrl(self):
    """Send request on behalf of staging user from web app to staging server and expect success (no redirection).
    """
    self._SendRequest('get_calendar', self._staging_webapp_cookie,
                      {'calendars': [{'calendar_id': 'EnglishHolidays.ics', 'year': 2012}]})

  def testRedirectProductionUserWebClientFromStagingUrl(self):
    """Send request on behalf of production user from web app to staging server and expect redirection to production.
    """
    exc = self.assertRaisesHttpError(301, self._SendRequest, 'get_calendar', self._cookie,
                                     {'calendars': [{'calendar_id': 'EnglishHolidays.ics', 'year': 2012}]})
    self.assertEqual(exc.response.headers['Location'], 'http://www.goviewfinder.com/service/get_calendar')
    self.assertEqual(exc.response.headers['X-VF-Staging-Redirect'], 'www.goviewfinder.com')

class StagingRedirectionFromProductionTestCase(StagingRedirectionBaseTestCase):
  """Tests specific to requests to production server.
  """
  def testRedirectStagingMobileClientFromProduction(self):
    """Send request on behalf of staging user mobile client to production server and expect redirection.
    """
    exc = self.assertRaisesHttpError(301, self._SendRequest, 'get_calendar', self._staging_cookie,
                                     {'calendars': [{'calendar_id': 'EnglishHolidays.ics', 'year': 2012}]})
    self.assertEqual(exc.response.headers['Location'], 'http://staging.goviewfinder.com/service/get_calendar')
    self.assertEqual(exc.response.headers['X-VF-Staging-Redirect'], 'staging.goviewfinder.com')

  def testRedirectStagingWebClientFromProduction(self):
    """Send request on behalf of staging user from web app to production server and expect success (no redirection).
    """
    self._SendRequest('get_calendar', self._staging_webapp_cookie,
                      {'calendars': [{'calendar_id': 'EnglishHolidays.ics', 'year': 2012}]})
