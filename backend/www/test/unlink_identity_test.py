# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test unlink_identity service API.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import time

from copy import deepcopy
from viewfinder.backend.base import util
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.www.test import service_base_test


class UnlinkIdentityTestCase(service_base_test.ServiceBaseTestCase):
  def testUnlinkIdentity(self):
    """Test basic unlinking of identities."""
    self._tester.LinkFacebookUser({'id': 100}, user_cookie=self._cookie)
    self.assertEqual(len(self._tester.ListIdentities(self._cookie)), 2)
    self._tester.UnlinkIdentity(self._cookie, 'FacebookGraph:100')
    self._tester.UnlinkIdentity(self._cookie, 'FacebookGraph:100')
    self.assertEqual(len(self._tester.ListIdentities(self._cookie)), 1)

  def testUnlinkContacts(self):
    """Test unlinking identity that is referenced by contacts."""
    for i in xrange(3):
      contact_dict = Contact.CreateContactDict(self._users[i].user_id,
                                               [('FacebookGraph:100', None)],
                                               util._TEST_TIME,
                                               Contact.FACEBOOK,
                                               rank=i)
      self._UpdateOrAllocateDBObject(Contact, **contact_dict)

    self._tester.LinkFacebookUser({'id': 100}, user_cookie=self._cookie)
    response_dict = self._tester.QueryContacts(self._cookie2, start_key=Contact.CreateSortKey(None, util._TEST_TIME))
    self.assertEqual(len(response_dict['contacts']), 1)

    # Now unlink the identity and make sure contacts are updated.
    util._TEST_TIME += 1
    self._tester.UnlinkIdentity(self._cookie, 'FacebookGraph:100')
    response_dict = self._tester.QueryContacts(self._cookie2, start_key=Contact.CreateSortKey(None, util._TEST_TIME))
    self.assertEqual(len(response_dict['contacts']), 1)

    # Now repeat, but with older contacts.
    util._TEST_TIME += 1
    timestamp = time.time() - 100
    for i in xrange(3):
      contact_dict = Contact.CreateContactDict(self._users[i].user_id,
                                               [('FacebookGraph:101', None)],
                                               timestamp,
                                               Contact.FACEBOOK,
                                               rank=i)
      contact = self._UpdateOrAllocateDBObject(Contact, **contact_dict)

    self._tester.LinkFacebookUser({'id': 101}, user_cookie=self._cookie)
    self._tester.UnlinkIdentity(self._cookie, 'FacebookGraph:101')
    response_dict = self._tester.QueryContacts(self._cookie3, start_key=Contact.CreateSortKey(None, util._TEST_TIME))
    self.assertEqual(len(response_dict['contacts']), 1)

  def testLinkAfterUnlink(self):
    """Link an identity to a different user after unlinking it."""
    self._tester.LinkFacebookUser({'id': 100}, user_cookie=self._cookie)
    self._tester.UnlinkIdentity(self._cookie, 'FacebookGraph:100')
    self._tester.LinkFacebookUser({'id': 100}, user_cookie=self._cookie2)
    self.assertEqual(len(self._tester.ListIdentities(self._cookie2)), 2)

  def testUnlinkUnboundIdentity(self):
    """ERROR: Try to unlink an identity that exists, but is not bound to any user."""
    # Create the unbound identity and add it to the model.
    identity_key = 'Email:new.user@emailscrubbed.com'
    self._UpdateOrAllocateDBObject(Identity, key=identity_key)
    self.assertRaisesHttpError(403, self._tester.UnlinkIdentity, self._cookie, identity_key)

  def testNonCanonicalId(self):
    """ERROR: Try to unlink identity using non-canonical form."""
    self.assertRaisesHttpError(400, self._tester.UnlinkIdentity, self._cookie, 'Email:User1@Yahoo.com')

  def testUnlinkLastAuthorizedIdentity(self):
    """ERROR: Verify the last authorized identity cannot be unlinked."""
    self.assertRaisesHttpError(403, self._tester.UnlinkIdentity, self._cookie, 'Email:user1@emailscrubbed.com')

  def testUnlinkIdentityWithoutPermission(self):
    """ERROR: Verify identity cannot be unlinked without permission."""
    self._tester.LinkFacebookUser({'id': 100}, user_cookie=self._cookie)
    self.assertRaisesHttpError(403, self._tester.UnlinkIdentity, self._cookie2, 'FacebookGraph:100')

  def testUnknownScheme(self):
    """ERROR: Try to unlink identity with unknown scheme."""
    self.assertRaisesHttpError(400, self._tester.UnlinkIdentity, self._cookie, 'Unknown:foo')


def _TestUnlinkIdentity(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test unlink_identity service API call."""
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  # Send identity/link request.
  actual_dict = tester.SendRequest('unlink_identity', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  validator.ValidateUnlinkIdentity(op_dict, request_dict['identity'])

  tester._CompareResponseDicts('unlink_identity', user_id, request_dict, {}, actual_dict)
  return actual_dict
