# -*- coding: utf-8 -*-
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for Contact.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

from viewfinder.backend.base import util
from viewfinder.backend.db import versions
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.identity import Identity

from base_test import DBBaseTestCase

class ContactTestCase(DBBaseTestCase):
  def testUnlinkIdentity(self):
    """Verify unlinking an identity causes every referencing contact to be updated."""
    # Create a Peter contact for Spencer.
    timestamp = util.GetCurrentTimestamp()
    spencer = self._user
    contact_identity = 'Email:peter.mattis@emailscrubbed.com'
    contact_name = 'Peter Mattis'
    contact_given_name = 'Peter'
    contact_family_name = 'Mattis'
    contact_rank = 42
    contact = Contact.CreateFromKeywords(spencer.user_id,
                                         [(contact_identity, None)],
                                         timestamp,
                                         Contact.GMAIL,
                                         name='Peter Mattis',
                                         given_name='Peter',
                                         family_name='Mattis',
                                         rank=42)
    self._RunAsync(contact.Update, self._client)

    peter_ident = self._RunAsync(Identity.Query, self._client, contact_identity, None)

    # Unlink peter's identity, which should cause Spencer's contact to be updated.
    self._RunAsync(peter_ident.UnlinkIdentity,
                   self._client,
                   self._user2.user_id,
                   contact_identity,
                   timestamp + 1)

    contacts = self._RunAsync(Contact.RangeQuery, self._client, spencer.user_id, None, None, None)
    self.assertEqual(len(contacts), 1)
    self.assertEqual(contacts[0].sort_key, Contact.CreateSortKey(contact.contact_id, timestamp + 1))
    self.assertEqual(contacts[0].name, contact_name)
    self.assertEqual(contacts[0].given_name, contact_given_name)
    self.assertEqual(contacts[0].family_name, contact_family_name)
    self.assertEqual(contacts[0].rank, contact_rank)

  def testDerivedAttributes(self):
    """Test that the identity and identities attributes are being properly derived from the
    identities_properties attribute.
    """
    # Create a Peter contact for Spencer with multiple identical and nearly identical identities.
    spencer = self._user
    contact_identity_a = 'Email:peter.mattis@Gmail.com'
    contact_identity_b = 'Email:peterMattis@emailscrubbed.com'
    contact_identity_c = 'Email:peterMattis@emailscrubbed.com'
    timestamp = util.GetCurrentTimestamp()

    contact = Contact.CreateFromKeywords(spencer.user_id,
                                         [(contact_identity_a, None),
                                          (contact_identity_b, 'home'),
                                          (contact_identity_c, 'work')],
                                         timestamp,
                                         Contact.GMAIL,
                                         name='Peter Mattis',
                                         given_name='Peter',
                                         family_name='Mattis',
                                         rank=42)

    self.assertEqual(len(contact.identities_properties), 3)
    self.assertEqual(len(contact.identities), 2)
    self.assertFalse(contact_identity_a in contact.identities)
    self.assertFalse(contact_identity_b in contact.identities)
    self.assertFalse(contact_identity_c in contact.identities)
    self.assertTrue(Identity.Canonicalize(contact_identity_a) in contact.identities)
    self.assertTrue(Identity.Canonicalize(contact_identity_b) in contact.identities)
    self.assertTrue(Identity.Canonicalize(contact_identity_c) in contact.identities)
    self.assertTrue([contact_identity_a, None] in contact.identities_properties)
    self.assertTrue([contact_identity_b, 'home'] in contact.identities_properties)
    self.assertTrue([contact_identity_c, 'work'] in contact.identities_properties)

  def testUnicodeContactNames(self):
    """Test that contact_id generation works correctly when names include non-ascii characters."""
    name = u'ààà朋友你好abc123\U00010000\U00010000\x00\x01\b\n\t '

    # The following will assert if there are problems when calculating the hash for the contact_id:
    contact_a = Contact.CreateFromKeywords(1,
                                           [('Email:me@my.com', None)],
                                           util.GetCurrentTimestamp(),
                                           Contact.GMAIL,
                                           name=name)

    contact_b = Contact.CreateFromKeywords(1,
                                           [('Email:me@my.com', None)],
                                           util.GetCurrentTimestamp(),
                                           Contact.GMAIL,
                                           name=u'朋' + name[1:])

    # Check that making a slight change to a unicode
    self.assertNotEqual(contact_a.contact_id, contact_b.contact_id)
