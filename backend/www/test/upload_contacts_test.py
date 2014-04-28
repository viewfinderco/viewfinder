# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Test upload_contacts service method.
"""

__authors__ = ['mike@emailscrubbed.com (Mike Purtell)']

import json
import mock

from copy import deepcopy
from viewfinder.backend.base import util
from viewfinder.backend.www.test import service_base_test
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.notification import Notification
from viewfinder.backend.db.operation import Operation

class UploadContactsTestCase(service_base_test.ServiceBaseTestCase):
  def testUploadContacts(self):
    """Test successful upload_contacts."""
    contacts = [{'identities': [{'identity': 'Email:mikep@non.com', 'description': 'work'}],
                 'contact_source': Contact.MANUAL,
                 'name': 'Mike Purtell',
                 'given_name': 'Mike',
                 'family_name': 'Purtell'},
                {'identities': [{'identity': 'Phone:+13191231111', 'description': 'home'},
                                {'identity': 'Phone:+13191232222', 'description': 'mobile'},
                                {'identity': 'Phone:+13191233333', 'description': 'a'},
                                {'identity': 'Phone:+13195555555'},
                                {'identity': 'FacebookGraph:1232134234'}],
                 'contact_source': Contact.IPHONE,
                 'name': 'Mike Purtell',
                 'given_name': 'Mike',
                 'family_name': 'Purtell'}]
    result_0 = self._tester.QueryContacts(self._cookie)
    upload_result = self._tester.UploadContacts(self._cookie, contacts)
    self.assertEqual(len(upload_result['contact_ids']), 2)
    result_1 = self._tester.QueryContacts(self._cookie)
    # Observe that the number of contacts increased by 2.
    self.assertEqual(result_0['num_contacts'] + 2, result_1['num_contacts'])
    self.assertEqual(upload_result['contact_ids'][1], result_1['contacts'][0]['contact_id'])
    self.assertEqual(upload_result['contact_ids'][0], result_1['contacts'][1]['contact_id'])

    # Try to upload the same contacts again and see that there's no error and no changes in contacts on server.
    self._tester.UploadContacts(self._cookie, contacts)
    result_2 = self._tester.QueryContacts(self._cookie)
    self.assertEqual(result_1, result_2)

    # Slightly modify one of the contacts and see that a new contact is added.
    contacts[1]['name'] = 'John Purtell'
    self._tester.UploadContacts(self._cookie, contacts)
    # This should result in just one additional contact on the server.
    result_3 = self._tester.QueryContacts(self._cookie)
    self.assertEqual(result_2['num_contacts'] + 1, result_3['num_contacts'])

  def testContactsWithRegisteredUsers(self):
    """Test interaction between user registration, contacts and notifications."""
    def _RegisterUser(name, given_name, email):
      user, _ = self._tester.RegisterFakeViewfinderUser({'name': name, 'given_name': given_name, 'email': email}, {})
      return user

    def _ValidateContactUpdate(expected_notification_name, expected_user_ids):
      notification_list = self._tester._RunAsync(Notification.RangeQuery,
                                                 self._client,
                                                 self._user.user_id,
                                                 range_desc=None,
                                                 limit=1,
                                                 col_names=None,
                                                 scan_forward=False)
      self.assertEqual(notification_list[0].name, expected_notification_name)
      invalidation = json.loads(notification_list[0].invalidate)
      start_key = invalidation['contacts']['start_key']
      query_result = self._tester.QueryContacts(self._cookie, start_key=start_key)
      found_user_ids = set()
      for contact in query_result['contacts']:
        for identity in contact['identities']:
          if identity.has_key('user_id'):
            found_user_ids.add(identity['user_id'])
      self.assertEqual(expected_user_ids, found_user_ids)

    contacts = [{'identities': [{'identity': 'Email:mike@boat.com'}],
                 'contact_source': Contact.MANUAL,
                 'name': 'Mike Boat'},
                {'identities': [{'identity': 'Email:mike@porsche.com'}, {'identity': 'Email:mike@vw.com'}],
                 'contact_source': Contact.MANUAL,
                 'name': 'Mike Cars'}]

    util._TEST_TIME += 1
    user_boat = _RegisterUser('Mike Purtell', 'Mike', 'mike@boat.com')
    self._tester.UploadContacts(self._cookie, contacts)
    _ValidateContactUpdate('upload_contacts', set([user_boat.user_id]))

    util._TEST_TIME += 1
    user_vw = _RegisterUser('Mike VW', 'Mike', 'mike@vw.com')
    _ValidateContactUpdate('first register contact', set([user_vw.user_id]))

    util._TEST_TIME += 1
    user_porsche = _RegisterUser('Mike Porsche', 'Mike', 'mike@porsche.com')
    _ValidateContactUpdate('first register contact', set([user_vw.user_id, user_porsche.user_id]))

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    self._tester.UploadContacts(self._cookie,
                                [{'identities': [{'identity': 'Email:mikep@non.com', 'description': 'work'}],
                                  'contact_source': Contact.MANUAL,
                                  'name': 'Mike Purtell',
                                  'given_name': 'Mike',
                                  'family_name': 'Purtell'}])

  def testUploadContactsFailures(self):
    """ERROR: Test some failure cases."""
    good_contact = {'identities': [{'identity': 'Email:mikep@non.com', 'description': 'work'}],
                    'contact_source': Contact.MANUAL,
                    'name': 'Mike Purtell',
                    'given_name': 'Mike',
                    'family_name': 'Purtell'}

    # ERROR: Empty identities:
    bad_contact = deepcopy(good_contact)
    bad_contact['identities'] = [{}]
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: Missing identities:
    bad_contact = deepcopy(good_contact)
    bad_contact.pop('identities')
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: Missing contact_source:
    bad_contact = deepcopy(good_contact)
    bad_contact.pop('contact_source')
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: Unknown contact source:
    bad_contact = deepcopy(good_contact)
    bad_contact['contact_source'] = 'x'
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: Attempt to upload a contact as if it's from facebook:
    bad_contact = deepcopy(good_contact)
    bad_contact['contact_source'] = Contact.FACEBOOK
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: Attempt to upload a contact as if it's from gmail:
    bad_contact = deepcopy(good_contact)
    bad_contact['contact_source'] = Contact.GMAIL
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: Malformed identities field:
    bad_contact = deepcopy(good_contact)
    bad_contact['identities'] = ['invalid']
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: Invalid identity properties field:
    bad_contact = deepcopy(good_contact)
    bad_contact['identities'] = [{'something': 'invalid'}]
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: Unknown identity type:
    bad_contact = deepcopy(good_contact)
    bad_contact['identities'] = [{'identity': 'Blah:234'}]
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: Invalid additional identity properties field:
    bad_contact = deepcopy(good_contact)
    bad_contact['identities'] = [{'identity': 'Email:me@my.com', 'bad': 'additional field'}]
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: Extra/unknown field:
    bad_contact = deepcopy(good_contact)
    bad_contact['unknown'] = 'field'
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: identity not in canonical form (upper case character):
    bad_contact = deepcopy(good_contact)
    bad_contact['identities'] = [{'identity': 'Email:Me@my.com'}]
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: too many contacts in a single request:
    too_many_contacts = [good_contact for i in xrange(51)]
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, too_many_contacts)

    # ERROR: too many identities in a single contact:
    bad_contact = deepcopy(good_contact)
    bad_contact['identities'] = [{'identity': 'Email:me@my.com'} for i in xrange(51)]
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: contact name too long:
    bad_contact = deepcopy(good_contact)
    bad_contact['name'] = 'a' * 1001
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: contact given_name too long:
    bad_contact = deepcopy(good_contact)
    bad_contact['given_name'] = 'a' * 1001
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: contact family_name too long:
    bad_contact = deepcopy(good_contact)
    bad_contact['family_name'] = 'a' * 1001
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: contact identity key too long:
    bad_contact = deepcopy(good_contact)
    bad_contact['identities'] = [{'identity': 'Email:%s' % ('a' * 1001)}]
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

    # ERROR: contact description too long:
    bad_contact = deepcopy(good_contact)
    bad_contact['identities'] = [{'identity': 'Email:me@my.com', 'description': 'a' * 1001}]
    self.assertRaisesHttpError(400, self._tester.UploadContacts, self._cookie, [bad_contact])

  @mock.patch.object(Contact, 'MAX_CONTACTS_LIMIT', 2)
  def testMaxContactLimit(self):
    """Test exceed limit error."""

    # This should increase the total to 1 and succeed.
    self._tester.UploadContacts(self._cookie,
                                [{'identities': [{'identity': 'Email:e1@a.com'}],
                                  'contact_source': Contact.IPHONE}])

    # This should fail because it would bring the total above 2.
    self.assertRaisesHttpError(403,
                               self._tester.UploadContacts,
                               self._cookie,
                               [{'identities': [{'identity': 'Email:e2@a.com'}],
                                 'contact_source': Contact.IPHONE},
                                {'identities': [{'identity': 'Email:e3@a.com'}],
                                 'contact_source': Contact.MANUAL}])

    # This should increase the total to 2 and succeed.
    self._tester.UploadContacts(self._cookie,
                                [{'identities': [{'identity': 'Email:e2@a.com'}],
                                  'contact_source': Contact.MANUAL}])

  def testUploadContactWithNoIdentities(self):
    """Verify that a contact without any identities succeeds."""
    contacts = [{'identities': [],
                 'contact_source': Contact.IPHONE,
                 'name': 'Mike Purtell',
                 'given_name': 'Mike',
                 'family_name': 'Purtell'}]
    upload_result = self._tester.UploadContacts(self._cookie, contacts)
    self.assertEqual(len(upload_result['contact_ids']), 1)
    contact_id = upload_result['contact_ids'][0]
    result = self._tester.QueryContacts(self._cookie)
    # Observe that query_contacts returns contact with empty identities list.
    self.assertEqual(len(result['contacts']), 1)
    self.assertEqual(len(result['contacts'][0]['identities']), 0)
    # Ensure that we can also remove this contact.
    self._tester.RemoveContacts(self._cookie, [contact_id])
    result = self._tester.QueryContacts(self._cookie)
    self.assertEqual(len(result['contacts']), 1)
    self.assertIn('removed', result['contacts'][0]['labels'])

def _TestUploadContacts(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test upload_contacts
  service API call.
  """
  def _ValidateUploadOneContact(contact):
    contact = deepcopy(contact)

    # Transform into proper form for Contact.CalculateContactId()
    identities_properties = [(identity_properties['identity'], identity_properties.get('description', None))
                                        for identity_properties in contact['identities']]
    contact.pop('identities')
    contact_dict = Contact.CreateContactDict(user_id, identities_properties, op_dict['op_timestamp'], **contact)
    predicate = lambda c: c.contact_id == contact_dict['contact_id']
    existing_contacts = validator.QueryModelObjects(Contact, predicate=predicate)
    # Create contact if it doesn't already exist or it's in a 'removed' state.
    if len(existing_contacts) == 0 or existing_contacts[-1].IsRemoved():
      if len(existing_contacts) != 0:
        # Delete the 'removed' contact.
        validator.ValidateDeleteDBObject(Contact, DBKey(user_id, existing_contacts[-1].sort_key))
      validator.ValidateCreateContact(**contact_dict)
    return contact_dict['contact_id']

  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  # Send upload_episode request.
  actual_dict = tester.SendRequest('upload_contacts', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  result_contact_ids = []
  for contact in request_dict['contacts']:
    contact_id = _ValidateUploadOneContact(contact)
    result_contact_ids.append(contact_id)

  # Validate that a notification was created for the upload of contacts.
  invalidate = {'contacts': {'start_key': Contact.CreateSortKey(None, op_dict['op_timestamp'])}}
  validator.ValidateNotification('upload_contacts', user_id, op_dict, invalidate)

  # Increment time so that subsequent contacts will use later time.
  util._TEST_TIME += 1

  tester._CompareResponseDicts('upload_contacts', user_id, request_dict, {'contact_ids': result_contact_ids}, actual_dict)
  return actual_dict
