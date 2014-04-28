# Copyright 2012 Viewfinder Inc. All Rights Reserved.
"""Test resolve_contacts method."""

__author__ = 'ben@emailscrubbed.com (Ben Darnell)'

from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.user import User
from viewfinder.backend.www.test import service_base_test

class ResolveContactsTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(ResolveContactsTestCase, self).setUp()

    # Create a new phone-only user.
    user, _ = self._tester.RegisterFakeViewfinderUser({'phone': '+14241234567',
                                                       'name': 'Ben Darnell',
                                                       'given_name': 'Ben',
                                                       'family_name': 'Darnell',
                                                       })

    self.phone_user_id = user.user_id

  def _Resolve(self, identities):
    response = self._SendRequest('resolve_contacts', self._cookie,
                                 {'identities': identities})
    return response['contacts']

  def testOne(self):
    """Successfully resolve a single email."""
    users = self._Resolve(['Email:user1@emailscrubbed.com'])
    self.assertEqual(users, [{'identity': 'Email:user1@emailscrubbed.com',
                              'user_id': self._user.user_id,
                              'name': self._user.name,
                              'given_name': self._user.given_name,
                              'labels': [User.REGISTERED]}])

  def testMissing(self):
    """Unsuccessfully resolve a single email."""
    users = self._Resolve(['Email:nobody@emailscrubbed.com'])
    self.assertEqual(users, [{'identity': 'Email:nobody@emailscrubbed.com'}])

  def testPhone(self):
    """Resolve a phone identity."""
    users = self._Resolve(['Phone:+14241234567'])
    self.assertEqual(users, [{'identity': 'Phone:+14241234567',
                              'user_id': self.phone_user_id,
                              'name': 'Ben Darnell',
                              'given_name': 'Ben',
                              'family_name': 'Darnell',
                              'labels': [User.REGISTERED]}])

  def testFacebook(self):
    """ERROR: Facebook identities cannot be resolved."""
    users = self._Resolve(['FacebookGraph:2'])
    self.assertEqual(users, [{'identity': 'FacebookGraph:2'}])

  def testMultiple(self):
    """Resolve multiple identities in one request."""
    users = self._Resolve(['Email:user1@emailscrubbed.com',
                           'FacebookGraph:2',
                           'Phone:+14241234567',
                           'Email:nobody@emailscrubbed.com'])
    self.assertEqual(users, [{'identity': 'Email:user1@emailscrubbed.com',
                              'user_id': self._user.user_id,
                              'name': self._user.name,
                              'given_name': self._user.given_name,
                              'labels': [User.REGISTERED]},
                             {'identity': 'FacebookGraph:2'},
                             {'identity': 'Phone:+14241234567',
                              'user_id': self.phone_user_id,
                              'name': 'Ben Darnell',
                              'given_name': 'Ben',
                              'family_name': 'Darnell',
                              'labels': [User.REGISTERED]},
                             {'identity': 'Email:nobody@emailscrubbed.com'}])

  def testUnboundIdentity(self):
    """Try to resolve an identity that exists, but is not bound to any user."""
    identity_key = 'Email:new.user@emailscrubbed.com'
    self._UpdateOrAllocateDBObject(Identity, key=identity_key)
    users = self._Resolve([identity_key])
    self.assertEqual(users, [{u'identity': identity_key}])

  def testNonCanonicalId(self):
    """ERROR: Try to resolve identity using non-canonical form."""
    self.assertRaisesHttpError(400, self._Resolve, ['Email:User1@YAHOO.com'])

  def testTerminatedUser(self):
    """Terminated users cannot be resolved."""
    # Validation won't work because we terminate one of the test users.
    self._validate = False
    # Make sure the user exists to start.
    users = self._Resolve(['Email:user3@emailscrubbed.com'])
    self.assertEqual(users, [{'identity': 'Email:user3@emailscrubbed.com',
                              'user_id': self._user3.user_id,
                              'name': self._user3.name,
                              'labels': [User.REGISTERED]}])
    # After termination, we can't find the user any more.
    self._tester.TerminateAccount(self._cookie3)
    users = self._Resolve(['Email:user3@emailscrubbed.com'])
    self.assertEqual(users, [{'identity': 'Email:user3@emailscrubbed.com'}])

  def testProspectiveUser(self):
    """Prospective users can be resolved."""
    self._CreateSimpleTestAssets()
    new_user, _, _ = self._CreateProspectiveUser()
    users = self._Resolve(['Email:prospective@emailscrubbed.com'])
    self.assertEqual(users, [{'identity': 'Email:prospective@emailscrubbed.com',
                              'user_id': 5,
                              'labels': []}])

    # Activate the user.
    self._UpdateOrAllocateDBObject(User,
                                   user_id=new_user.user_id,
                                   labels=[User.REGISTERED])
    users = self._Resolve(['Email:prospective@emailscrubbed.com'])
    self.assertEqual(users, [{'user_id': new_user.user_id,
                              'identity': 'Email:prospective@emailscrubbed.com',
                              'labels': [User.REGISTERED]}])
