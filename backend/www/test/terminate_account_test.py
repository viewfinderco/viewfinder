# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test terminate_accont service API.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

from copy import deepcopy
from functools import partial
from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.user import User
from viewfinder.backend.www.test import service_base_test


class TerminateAccountTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(TerminateAccountTestCase, self).setUp()
    self._CreateSimpleTestAssets()

  def testSimpleTerminate(self):
    """Terminate user account with a single identity."""
    self._tester.TerminateAccount(self._cookie2)

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie2)

  def testMultipleTerminate(self):
    """Terminate user account with multiple linked identities."""
    self._tester.LinkFacebookUser({'id': 100}, user_cookie=self._cookie)
    self._tester.TerminateAccount(self._cookie)

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie)

  def testTerminateWithFriend(self):
    """Terminate user account that is friends with another account."""
    # Share to make friends.
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)],
                          [self._user2.user_id, self._user3.user_id])
    self._tester.TerminateAccount(self._cookie2)

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie2)

  def testShareToTerminatedAccount(self):
    """Share to identity that was formerly connected to terminated account."""
    self._tester.TerminateAccount(self._cookie2)
    self._tester.ShareNew(self._cookie, [(self._episode_id, self._photo_ids)],
                          ['FacebookGraph:2'])

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie2)

  def testLoginAfterTerminate(self):
    """Try to log in with a terminated user cookie."""
    self._tester.TerminateAccount(self._cookie3)
    self.assertRaisesHttpError(401, self._tester.TerminateAccount, self._cookie3)

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie3)

  def testTerminateWithContact(self):
    """Terminate user account to which a contact was linked."""
    # Create contact for user #1
    identity_key = 'Email:foo@emailscrubbed.com'
    contact_dict = Contact.CreateContactDict(self._user.user_id,
                                             [('Email:user3@emailscrubbed.com', None)],
                                             util._TEST_TIME,
                                             Contact.GMAIL)
    self._UpdateOrAllocateDBObject(Contact, **contact_dict)

    self._tester.TerminateAccount(self._cookie3)
    response_dict = self._tester.QueryNotifications(self._cookie, 1, scan_forward=False)
    self.assertEqual(response_dict['notifications'][0]['name'], 'unlink_identity')

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie3)


def _TestTerminateAccount(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test terminate_account
  service API call.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  # Send terminate_account request.
  actual_dict = tester.SendRequest('terminate_account', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # Validate the account termination.
  validator.ValidateTerminateAccount(user_id, op_dict)

  tester._CompareResponseDicts('terminate_account', user_id, request_dict, {}, actual_dict)
  return actual_dict
