# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Verifies operation of unsubscribe handler.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import re
import urllib

from viewfinder.backend.base import util
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.user import User
from viewfinder.backend.services.email_mgr import EmailManager, TestEmailManager
from viewfinder.backend.www.unsubscribe import UnsubscribeHandler
from viewfinder.backend.www.test import service_base_test

_unsubscribe_re = re.compile('.*(\/unsubscribe\?cookie=[^\"]*)\".*')


class UnsubscribeTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(UnsubscribeTestCase, self).setUp()

    self._CreateSimpleTestAssets()
    self._emails = TestEmailManager.Instance().emails

  def testUnsubscribeEmailAlerts(self):
    """Test unsubscribing from email alerts."""
    # Enable email alerts for user #2.
    self._tester.UpdateUser(self._cookie2, settings_dict={'email_alerts': 'on_share_new'})

    # Now share a new viewpoint to user #2 (should generate email).
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)], [self._user2.user_id])
    assert len(self._emails[self._user2.email]) == 1, len(self._emails[self._user2.email])

    # Now turn off email alerts for user #2 and share again (should not generate email).
    self._TestUnsubscribe(self._cookie2, AccountSettings.EMAIL_ALERTS)
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)], [self._user2.user_id])
    assert len(self._emails[self._user2.email]) == 1, len(self._emails[self._user2.email])

  def testUnsubscribeMarketing(self):
    """Test unsubscribing from marketing communication."""
    # Test unsubscribing for a user that does not yet have a marketing setting.
    self._TestUnsubscribe(self._cookie2, AccountSettings.MARKETING)

    # Test unsubscribing for a user that has marketing communications explicitly enabled.
    self._UpdateOrAllocateDBObject(AccountSettings,
                                   settings_id=AccountSettings.ConstructSettingsId(self._user2.user_id),
                                   group_name=AccountSettings.GROUP_NAME,
                                   marketing='all')
    self._TestUnsubscribe(self._cookie2, AccountSettings.MARKETING)

    settings = self._RunAsync(AccountSettings.QueryByUser, self._client, self._user2.user_id, None)
    self.assertFalse(settings.AllowMarketing())

  def testProspectiveUnsubscribe(self):
    """Test share_new with prospective user, then unsubscribe with no cookie."""
    email_address = 'andy@emailscrubbed.com'
    identity_key = 'Email:%s' % email_address
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)], [identity_key])

    # Get information about the prospective user.
    identity = self._RunAsync(Identity.Query, self._client, identity_key, None)
    user = self._RunAsync(User.Query, self._client, identity.user_id, None)

    # Pick unsubscribe URL out of the email that was generated.
    html = self._emails[email_address][0]['html']
    unsubscribe_url = self._tester.GetUrl(_unsubscribe_re.match(html).group(1))

    # Now unsubscribe.
    response = self._RunAsync(self._tester.http_client.fetch,
                              unsubscribe_url,
                              method='GET',
                              follow_redirects=False)
    self.assertEqual(response.code, 200)

    # Validate that email will no longer be sent.
    settings = AccountSettings.CreateForUser(user.user_id, email_alerts=AccountSettings.EMAIL_NONE)
    self._tester.validator.ValidateUpdateDBObject(AccountSettings, **settings._asdict())

  def testMultipleUnsubscribes(self):
    """Test unsubscribing multiple times."""
    self._TestUnsubscribe(self._cookie, AccountSettings.EMAIL_ALERTS)
    self._TestUnsubscribe(self._cookie, AccountSettings.EMAIL_ALERTS)
    self._TestUnsubscribe(self._cookie, AccountSettings.MARKETING)
    self._TestUnsubscribe(self._cookie, AccountSettings.MARKETING)

  def testInvalidCookie(self):
    """Test unsubscribe with invalid cookie."""
    unsubscribe_url = self._tester.GetUrl('/unsubscribe?cookie=unknown')
    response = self._RunAsync(self._tester.http_client.fetch,
                              unsubscribe_url,
                              method='GET',
                              follow_redirects=False)
    self.assertEqual(response.code, 400)
    self.assertIn('The requested link has expired and can no longer be used.', response.body)

  def _TestUnsubscribe(self, user_cookie, email_type):
    """Invoke the /unsubscribe handler and validate that emails were turned off."""
    user_id, device_id = self._tester.GetIdsFromCookie(user_cookie)
    unsubscribe_cookie = User.CreateUnsubscribeCookie(user_id, email_type)
    unsubscribe_url = self._tester.GetUrl('/unsubscribe?cookie=%s') % unsubscribe_cookie

    response = self._RunAsync(self._tester.http_client.fetch,
                              unsubscribe_url,
                              method='GET',
                              follow_redirects=False)
    if response.code >= 400:
      response.rethrow()

    self.assertIn('You have successfully unsubscribed', response.body)

    # Validate that settings were updated.
    if email_type == AccountSettings.EMAIL_ALERTS:
      settings = AccountSettings.CreateForUser(user_id, email_alerts=AccountSettings.EMAIL_NONE)
    else:
      settings = AccountSettings.CreateForUser(user_id, marketing=AccountSettings.MARKETING_NONE)

    self._tester.validator.ValidateUpdateDBObject(AccountSettings, **settings._asdict())
