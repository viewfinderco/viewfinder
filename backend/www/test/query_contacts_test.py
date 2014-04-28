#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for querying user contacts.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

from viewfinder.backend.base import util
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.www.test import service_base_test

class QueryContactsTestCase(service_base_test.ServiceBaseTestCase):
  def testQueryContacts(self):
    """Fetch all contacts via query_contacts."""
    self._CreateContacts()
    response_dict = self._tester.QueryContacts(self._cookie)
    self.assertEqual(response_dict['num_contacts'], len(self._contacts))

  def testQueryContactsWithLimit(self):
    """Fetch contacts via query_contacts with a limit."""
    self._CreateContacts()
    response_dict = self._tester.QueryContacts(self._cookie, limit=1)

    # Verify limit=1 query and send a new query for the remainder, starting at the last key.
    self.assertEqual(response_dict['num_contacts'], 1)
    first_contact = response_dict['contacts'][0]
    self.assertTrue('last_key' in response_dict)

    response_dict = self._tester.QueryContacts(self._cookie, start_key=response_dict['last_key'])

    # Verify the remainder of the contacts were returned, append the first contact result,
    # and verify all contacts.
    self.assertEqual(response_dict['num_contacts'], len(self._contacts) - 1)
    contacts = response_dict['contacts']
    contacts.append(first_contact)

  def testQueryContactNoIdentity(self):
    """Fetch a contact with no corresponding identity object."""
    self._CreateContact([('Local:1', None)], no_identity=True)
    response_dict = self._tester.QueryContacts(self._cookie)
    contact_dict = {'identities_properties': [('Local:1', None)],
                    'contact_source': Contact.GMAIL}
    contact_dict['contact_id'] = Contact.CalculateContactId(contact_dict)
    contact_dict['identities'] = [{'identity': 'Local:1'}]
    contact_dict.pop('identities_properties')
    self.assertEqual(response_dict['contacts'][0], contact_dict)

  def testQueryBoundContact(self):
    """Fetch a contact that is bound to a user."""
    self._CreateContact([('Local:1', None, 100)])
    response_dict = self._tester.QueryContacts(self._cookie)
    contact_dict = {'identities_properties': [('Local:1', None)],
                    'contact_source': Contact.GMAIL}
    contact_dict['contact_id'] = Contact.CalculateContactId(contact_dict)
    contact_dict['identities'] = [{'identity': 'Local:1', 'user_id': 100}]
    contact_dict.pop('identities_properties')
    self.assertEqual(response_dict['contacts'][0], contact_dict)

  def _CreateContact(self, identities_properties, no_identity=False, **kwargs):
    if not no_identity:
      for identity_properties in identities_properties:
        contact_user_id = identity_properties[2] if len(identity_properties) > 2 else None
        self._UpdateOrAllocateDBObject(Identity,
                                       key=Identity.Canonicalize(identity_properties[0]),
                                       user_id=contact_user_id)

    contact_identities_properties = []
    for identity_properties in identities_properties:
      contact_identities_properties.append(identity_properties[:2])

    contact_dict = Contact.CreateContactDict(self._user.user_id,
                                             contact_identities_properties,
                                             util._TEST_TIME,
                                             Contact.GMAIL,
                                             **kwargs)
    self._UpdateOrAllocateDBObject(Contact, **contact_dict)

  def _CreateContacts(self):
    """Creates a number of test contacts. Invokes callback on completion."""
    self._contacts = [{'name': 'Georgina Cantwell', 'rank': 1, 'identities_properties': [('Local:1', None)]},
                      {'name': 'Brett Eisenman',
                       'rank': 2,
                       'identities_properties': [('Local:2', None, 6)]},
                      {'name': 'Philip Gaucher',
                       'rank': 3,
                       'identities_properties': [('Local:3', None)],
                       'no_identity': True},
                      {'name': 'Annie Wickman',
                       'rank': 4,
                       'identities_properties': [('Local:5', None, 22)],
                       'no_identity': True},
                      {'rank': 5, 'identities_properties': [('Local:10', None)]},
                      {'name': 'Juan Valdez',
                       'identities_properties': [('Local:101', 'home'), ('Local:102', 'work')]},
                      {'name': 'Juanita Valdez',
                       'identities_properties': [('Local:101', 'home', 32), ('Local:103', 'work', 42)]},
                      {'name': 'John Valdez',
                       'identities_properties': [('Local:101', 'home'), ('Local:101', 'work')],
                       'no_identity': True},
                      {'name': 'Johanna Valdez',
                       'identities_properties': [('Local:104', 'home'), ('Local:105', 'home')]},
                      {'name': 'Sam Valdez',
                       'identities_properties': [('Local:106', 'home'), ('Local:106', 'home', 55)]},
                      {'name': 'Samual Valdez',
                       'identities_properties': [('Local:107', 'home'), ('Local:108', 'mobile')]},
                      {'name': 'Andy Kimball',
                       'given_name': 'Andy',
                       'family_name': 'Kimball',
                       'identities_properties': [('Local:11', None)]},
                      {'given_name': 'Andy',
                       'family_name': 'Kimball',
                       'rank': 6,
                       'identities_properties': [('Local:12', None)],
                       'no_identity': True},
                      {'name': 'Giulia Auricchio', 'identities_properties': [('Local:13', None)]}]

    for contact in self._contacts:
      self._CreateContact(**contact)


def _TestQueryContacts(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test query_contacts service API call."""
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)

  def _MakeContactDict(contact):
    """Create a contact dict from the contact object plus its referenced identity object.
    """
    identity_dict = dict()
    for identity_key in contact.identities:
      identity = validator.GetModelObject(Identity, identity_key, must_exist=False)
      identity_dict[identity_key] = identity
    contact_dict = {'contact_id': contact.contact_id,
                    'contact_source': contact.contact_source}
    util.SetIfNotNone(contact_dict, 'name', contact.name)
    util.SetIfNotNone(contact_dict, 'given_name', contact.given_name)
    util.SetIfNotNone(contact_dict, 'family_name', contact.family_name)
    util.SetIfNotNone(contact_dict, 'rank', contact.rank)
    if contact.labels is not None and len(contact.labels) > 0:
      contact_dict['labels'] = list(contact.labels)
    identities_list = []
    if contact.identities_properties is not None:
      for identity_properties in contact.identities_properties:
        identity_key = identity_properties[0]
        properties = {'identity': identity_key}
        util.SetIfNotNone(properties, 'description', identity_properties[1])
        if identity_dict[Identity.Canonicalize(identity_key)] is None:
          user_id = None
        else:
          user_id = identity_dict[Identity.Canonicalize(identity_key)].user_id
        util.SetIfNotNone(properties, 'user_id', user_id)
        identities_list.append(properties)
      contact_dict['identities'] = identities_list
    return contact_dict

  # Send query_contacts request.
  actual_dict = tester.SendRequest('query_contacts', user_cookie, request_dict)

  # Build expected response dict.
  contacts = validator.QueryModelObjects(Contact,
                                         user_id,
                                         limit=request_dict.get('limit', None),
                                         start_key=request_dict.get('start_key', None))
  expected_dict = {'contacts': [_MakeContactDict(co) for co in contacts]}
  expected_dict['num_contacts'] = len(contacts)
  if len(contacts) > 0:
    expected_dict['last_key'] = contacts[-1].sort_key

  tester._CompareResponseDicts('query_contacts', user_id, request_dict, expected_dict, actual_dict)
  return actual_dict
