# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Test remove_contacts service method.
"""

__authors__ = ['mike@emailscrubbed.com (Mike Purtell)']

import json
import mock
from copy import deepcopy
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.base import util
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.notification import Notification
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.www.test import service_base_test

class RemoveContactsTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(RemoveContactsTestCase, self).setUp()

  def testAddRemoveContact(self):
    """Test sequences of adding and removing a contact."""
    contact_dict = {'contact_source': Contact.MANUAL,
                    'identities': [{'identity': 'Email:mike@host.com', 'description': 'home'}],
                    'name': 'Mike Purtell',
                    'given_name': 'Mike',
                    'family_name': 'Purtell',
                    'rank': 42}
    self._tester.UploadContacts(self._cookie, [contact_dict])
    result = self._tester.QueryContacts(self._cookie)
    self.assertEquals(len(result['contacts']), 1)

    contact_id = result['contacts'][0]['contact_id']
    expected_present_contact_dict = deepcopy(contact_dict)
    expected_present_contact_dict['contact_id'] = contact_id
    expected_removed_contact_dict = {'contact_source': Contact.MANUAL,
                                'contact_id': contact_id,
                                'labels': ['removed']}
    self.assertEquals(result['contacts'][0], expected_present_contact_dict)

    # Remove contact and confirm result.
    self._tester.RemoveContacts(self._cookie, [contact_id])
    result = self._tester.QueryContacts(self._cookie)
    self.assertEquals(len(result['contacts']), 1)
    self.assertEqual(result['contacts'][0], expected_removed_contact_dict)

    # Remove again and confirm the same result.
    self._tester.RemoveContacts(self._cookie, [contact_id])
    result = self._tester.QueryContacts(self._cookie)
    self.assertEquals(len(result['contacts']), 1)
    self.assertEqual(result['contacts'][0], expected_removed_contact_dict)

    # Upload the same contact again and expect it's now present when queried.
    self._tester.UploadContacts(self._cookie, [contact_dict])
    result = self._tester.QueryContacts(self._cookie)
    self.assertEquals(len(result['contacts']), 1)
    self.assertEqual(result['contacts'][0], expected_present_contact_dict)

    # Remove again and confirm the same result.
    self._tester.RemoveContacts(self._cookie, [contact_id])
    result = self._tester.QueryContacts(self._cookie)
    self.assertEquals(len(result['contacts']), 1)
    self.assertEqual(result['contacts'][0], expected_removed_contact_dict)

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Variation on above test which forces op failure in order to test idempotency."""
    contact_dict = {'contact_source': Contact.MANUAL,
                    'identities': [{'identity': 'Email:mike@host.com', 'description': 'home'}],
                    'name': 'Mike Purtell',
                    'given_name': 'Mike',
                    'family_name': 'Purtell',
                    'rank': 42}
    self._tester.UploadContacts(self._cookie, [contact_dict])
    result = self._tester.QueryContacts(self._cookie)
    self.assertEquals(len(result['contacts']), 1)

    contact_id = result['contacts'][0]['contact_id']
    expected_present_contact_dict = deepcopy(contact_dict)
    expected_present_contact_dict['contact_id'] = contact_id
    expected_removed_contact_dict = {'contact_source': Contact.MANUAL,
                                'contact_id': contact_id,
                                'labels': ['removed']}
    self.assertEquals(result['contacts'][0], expected_present_contact_dict)

    # Remove contact and confirm result.
    self._tester.RemoveContacts(self._cookie, [contact_id])
    result = self._tester.QueryContacts(self._cookie)
    self.assertEquals(len(result['contacts']), 1)
    self.assertEqual(result['contacts'][0], expected_removed_contact_dict)

    # Remove again and confirm the same result.
    self._tester.RemoveContacts(self._cookie, [contact_id])
    result = self._tester.QueryContacts(self._cookie)
    self.assertEquals(len(result['contacts']), 1)
    self.assertEqual(result['contacts'][0], expected_removed_contact_dict)

    # Upload the same contact again and expect it's now present when queried.
    self._tester.UploadContacts(self._cookie, [contact_dict])
    result = self._tester.QueryContacts(self._cookie)
    self.assertEquals(len(result['contacts']), 1)
    self.assertEqual(result['contacts'][0], expected_present_contact_dict)

    # Remove again and confirm the same result.
    self._tester.RemoveContacts(self._cookie, [contact_id])
    result = self._tester.QueryContacts(self._cookie)
    self.assertEquals(len(result['contacts']), 1)
    self.assertEqual(result['contacts'][0], expected_removed_contact_dict)

  def testRemoveNonExistingContacts(self):
    """Try to remove some contacts that don't exist and expect a no-op.
    """
    remove_contacts = ['ip:lkjasdlfkjasdf', 'm:lkjasdlfkj']
    self._tester.RemoveContacts(self._cookie, remove_contacts)

  @mock.patch.object(Contact, 'MAX_CONTACTS_LIMIT', 2)
  @mock.patch.object(Contact, 'MAX_REMOVED_CONTACTS_LIMIT', 2)
  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testMaxRemovedContactsLimit(self):
    """Test exceeding removed contact limit and observe reset notification as well as deletion of all removed
    contacts.
    """

    def _CheckExpected(total_present_contact_row_count, total_removed_contact_row_count,
                       reset_removed_contacts_notification):
      actual_present_count = 0
      actual_removed_count = 0
      all_contact_rows = self._RunAsync(Contact.RangeQuery,
                                        self._client,
                                        self._user.user_id,
                                        range_desc=None,
                                        limit=100,
                                        col_names=None)
      for contact in all_contact_rows:
        if contact.IsRemoved():
          actual_removed_count += 1
        else:
          actual_present_count += 1
      self.assertEqual(total_present_contact_row_count, actual_present_count)
      self.assertEqual(total_removed_contact_row_count, actual_removed_count)

      actual_removed_contacts_reset = _CheckForRemovedContactsReset(self._tester, self._user.user_id)
      self.assertEqual(reset_removed_contacts_notification, actual_removed_contacts_reset)

    upload_result = self._tester.UploadContacts(self._cookie,
                                                [{'identities': [{'identity': 'Email:e1@a.com'}],
                                                  'contact_source': Contact.MANUAL}])
    contact1_id = upload_result['contact_ids'][0]
    _CheckExpected(1, 0, False)  # Contact state: present: [contact1_id], removed: []

    upload_result = self._tester.UploadContacts(self._cookie,
                                                [{'identities': [{'identity': 'Email:e2@a.com'}],
                                                  'contact_source': Contact.MANUAL}])
    contact2_id = upload_result['contact_ids'][0]
    _CheckExpected(2, 0, False)  # Contact state: present: [contact1_id,contact2_id], removed: []

    # This shouldn't trigger the removed contacts reset.
    self._tester.RemoveContacts(self._cookie, [contact1_id])
    _CheckExpected(1, 1, False)  # Contact state: present: [contact2_id], removed: [contact1_id]

    # Add back the first contact.
    upload_result = self._tester.UploadContacts(self._cookie,
                                                [{'identities': [{'identity': 'Email:e1@a.com'}],
                                                  'contact_source': Contact.MANUAL}])
    contact3_id = upload_result['contact_ids'][0]
    _CheckExpected(2, 0, False) # Contact state: present: [contact1_id,contact2_id], removed: []

    # This shouldn't trigger the removed contacts reset.
    self._tester.RemoveContacts(self._cookie, [contact1_id])
    _CheckExpected(1, 1, False) # Contact state: present: [contact2_id], removed: [contact1_id]

    # Upload 3rd different contact.
    upload_result = self._tester.UploadContacts(self._cookie,
                                                [{'identities': [{'identity': 'Email:e3@a.com'}],
                                                  'contact_source': Contact.MANUAL}])
    contact3_id = upload_result['contact_ids'][0]
    _CheckExpected(2, 1, False)  # Contact state: present: [contact2_id,contact3_id], removed: [contact1_id]

    # Remove 3rd one which should get us to 2 removed contacts and trigger contact reset.
    self._tester.RemoveContacts(self._cookie, [contact3_id])
    _CheckExpected(1, 0, True) # Contact state: present: [contact2_id], removed: []

    # Check that we can query_contacts with the None start_key that may be sent in a remove_contacts notification.
    query_result = self._tester.QueryContacts(self._cookie, start_key=None)
    self.assertEqual(1, len(query_result['contacts']))
    self.assertEqual(contact2_id, query_result['contacts'][0]['contact_id'])


def _CheckForRemovedContactsReset(tester, user_id):
  """Check if the last notification is a contacts notification with a None start_key.
  This indicates that all the 'removed' contacts have been deleted and the client
  should do a full reload of the contacts.
  Returns: True if all contacts should be reloaded (reset) by the client.
  """
  validator = tester.validator
  # Get the most recent notification.
  notifications = validator._RunAsync(Notification.RangeQuery,
                                      validator.client,
                                      user_id,
                                      range_desc=None,
                                      limit=1,
                                      col_names=None,
                                      scan_forward=False)
  invalidate = json.loads(notifications[0].invalidate)
  removed_contacts_reset = 'contacts' in invalidate and \
                           'all' in invalidate['contacts'] and \
                           invalidate['contacts']['all']
  return removed_contacts_reset

def _TestRemoveContacts(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test remove_contacts
  service API call.
  """
  def _ValidateRemoveOneContact(contact_id):
    predicate = lambda c: c.contact_id == contact_id
    existing_contacts = validator.QueryModelObjects(Contact, predicate=predicate, query_forward=True)
    if len(existing_contacts) > 0:
      last_contact = existing_contacts[-1]
      if last_contact.IsRemoved():
        # Keep the last matching contact because it's already been removed.
        existing_contacts = existing_contacts[:-1]
      elif not removed_contacts_reset:
        removed_contact_dict = {'user_id': user_id,
                                'contact_id': contact_id,
                                'contact_source': Contact.GetContactSourceFromContactId(contact_id),
                                'timestamp': util._TEST_TIME,
                                'sort_key': Contact.CreateSortKey(contact_id, util._TEST_TIME),
                                'labels': [Contact.REMOVED]}
        validator.ValidateCreateContact(identities_properties=None, **removed_contact_dict)

      for contact in existing_contacts:
        db_key = DBKey(user_id, contact.sort_key)
        validator.ValidateDeleteDBObject(Contact, db_key)

  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  # Send remove_contacts request.
  actual_dict = tester.SendRequest('remove_contacts', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # Cheat a little by inspecting the actual notification to see if there was a reset of removed contacts.
  removed_contacts_reset = _CheckForRemovedContactsReset(tester, user_id)
  if removed_contacts_reset:
    # Delete any 'removed' contacts from the model.
    predicate = lambda c: c.IsRemoved()
    removed_contacts = validator.QueryModelObjects(Contact, predicate=predicate, query_forward=True)
    for removed_contact in removed_contacts:
      validator.ValidateDeleteDBObject(Contact, DBKey(user_id, removed_contact.sort_key))

  for contact_id in request_dict['contacts']:
    _ValidateRemoveOneContact(contact_id)

  # Validate that a notification was created for the removal of contacts.
  timestamp = 0 if removed_contacts_reset else op_dict['op_timestamp']
  invalidate = {'contacts': {'start_key': Contact.CreateSortKey(None, timestamp)}}
  if removed_contacts_reset:
    invalidate['contacts']['all'] = True
  validator.ValidateNotification('remove_contacts', user_id, op_dict, invalidate)

  # Increment time so that subsequent contacts will use later time.
  util._TEST_TIME += 1

  tester._CompareResponseDicts('remove_contacts', user_id, request_dict, {}, actual_dict)
  return actual_dict
