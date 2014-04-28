# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder UploadContactsOperation.

This operation creates/updates contact metadata submitted via the service API.
Any contacts for which there is already a matching contact_id (calculated from
a contacts properties) will be skipped.  Contacts that are inserted will have
a sort key with a timestamp prefix that matches the operation timestamp.
This sort_key will be used to notify the contact user of any new inserts.
"""

__authors__ = ['mike@emailscrubbed.com (Mike Purtell)']

from tornado import gen

from viewfinder.backend.base.exceptions import LimitExceededError
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation
from viewfinder.backend.resources.message.error_messages import UPLOAD_CONTACTS_EXCEEDS_LIMIT


class UploadContactsOperation(ViewfinderOperation):
  """The UploadContacts operation follows the four phase pattern described in the header of
  operation_map.py (with the exception that no accounting is performed for this operation).
  """
  def __init__(self, client, user_id, contacts):
    super(UploadContactsOperation, self).__init__(client)
    self._user_id = user_id
    self._request_contacts = contacts
    self._notify_timestamp = self._op.timestamp
    # List of tuples (contact_dict_to_insert, removed_contact_to_delete)
    self._contact_dicts_to_insert = []
    # List of contacts to delete.
    self._contacts_to_delete = []

  @classmethod
  @gen.coroutine
  def Execute(cls, client, user_id, contacts):
    """Entry point called by the operation framework."""
    yield UploadContactsOperation(client, user_id, contacts)._UploadContacts()

  @gen.coroutine
  def _UploadContacts(self):
    """Orchestrates the upload contacts operation by executing each of the phases in turn."""
    yield self._Check()
    self._client.CheckDBNotModified()
    yield self._Update()
    # No accounting for this operation.
    yield Operation.TriggerFailpoint(self._client)
    yield self._Notify()

  @gen.coroutine
  def _Check(self):
    """Check and prepare for update.
    Query for all of the existing contacts of the user so that any non-removed matches can be skipped and removed
      matches can be replaced.
    Complete construction of the contact dict.
    Check that the upload won't cause the max number of contacts to be exceeded.
    """
    existing_contacts_dict, self._contacts_to_delete = \
        yield UploadContactsOperation._GetAllContactsWithDedup(self._client, self._user_id)

    # Total count of non-removed contacts.  Excludes contacts which will be deleted during update phase.
    total_contact_count = 0
    for existing_contact in existing_contacts_dict.itervalues():
      if not existing_contact.IsRemoved():
        total_contact_count += 1

    # Complete construction of contact dict and sort out which contacts should be deleted/inserted/skipped.
    for contact in self._request_contacts:
      request_contact = Contact.CreateContactDict(user_id=self._user_id, timestamp=self._notify_timestamp, **contact)
      existing_contact = existing_contacts_dict.get(request_contact['contact_id'], None)
      if existing_contact is None:
        # No sign of this contact on the server, so we'll insert it.
        self._contact_dicts_to_insert.append((request_contact, None))
        total_contact_count += 1
      elif existing_contact.IsRemoved():
        # If it's removed, we'll replace it.
        self._contact_dicts_to_insert.append((request_contact, existing_contact))
        # Bump total contact count because this contact is transitioning from removed to present.
        total_contact_count += 1
      # else case is no-op because this contact is already present (non-removed).

    # Check if we're exceeding any limits with this upload.
    if total_contact_count > Contact.MAX_CONTACTS_LIMIT:
      raise LimitExceededError(UPLOAD_CONTACTS_EXCEEDS_LIMIT)

  @gen.coroutine
  def _Update(self):
    """Perform insert/(replace) of uploaded contacts as well as deletion of duplicate contacts."""
    @gen.coroutine
    def _ReplaceRemovedContact(contact_dict_to_insert, removed_contact_to_delete):
      contact_to_insert = Contact.CreateFromKeywords(**contact_dict_to_insert)
      yield gen.Task(contact_to_insert.Update, self._client)
      if removed_contact_to_delete is not None:
        yield Operation.TriggerFailpoint(self._client)
        yield gen.Task(removed_contact_to_delete.Delete, self._client)

    # Delete duplicates.
    tasks = [gen.Task(contact_to_delete.Delete, self._client) for contact_to_delete in self._contacts_to_delete]
    # Insert (and maybe replace) uploaded contacts.
    for contact_to_insert, removed_contact_to_delete in self._contact_dicts_to_insert:
      tasks.append(_ReplaceRemovedContact(contact_to_insert, removed_contact_to_delete))
    yield tasks

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
    Notify of all contacts with timestamp greater than or equal to current.
    """
    yield NotificationManager.NotifyUploadContacts(self._client, self._user_id, self._notify_timestamp)

