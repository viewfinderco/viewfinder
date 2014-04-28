# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder RemoveContactsOperation.

This operation removes contacts.
"""

__authors__ = ['mike@emailscrubbed.com (Mike Purtell)']

from tornado import gen

from viewfinder.backend.base.exceptions import InvalidRequestError
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation
from viewfinder.backend.resources.message.error_messages import BAD_CONTACT_SOURCE


class RemoveContactsOperation(ViewfinderOperation):
  """The RemoveContacts operation follows the four phase pattern described in the header of
  operation_map.py (with the exception that no accounting is performed for this operation).
  """
  def __init__(self, client, user_id, contacts):
    super(RemoveContactsOperation, self).__init__(client)
    self._user_id = user_id
    self._request_contact_ids = set(contacts)
    self._notify_timestamp = self._op.timestamp
    self._removed_contacts_reset = False
    # List of contacts to delete (these were found to be duplicates).
    self._contacts_to_delete = []
    # These are the contacts which exist and need to be replaced by a 'removed' contact.
    self._contacts_to_remove = []

  @classmethod
  @gen.coroutine
  def Execute(cls, client, user_id, contacts):
    """Entry point called by the operation framework."""
    yield RemoveContactsOperation(client, user_id, contacts)._RemoveContacts()

  @gen.coroutine
  def _RemoveContacts(self):
    """Orchestrates the remove contacts operation by executing each of the phases in turn."""
    yield self._Check()
    self._client.CheckDBNotModified()
    yield self._Update()
    # No accounting for this operation.
    yield Operation.TriggerFailpoint(self._client)
    yield self._Notify()

  @gen.coroutine
  def _Check(self):
    """Check and prepare for remove.
    Along with checks, builds two lists for the Update phase.
    1) self._contacts_to_delete: list of contacts which have been superseded by more recent
        contacts with the same contact_id and because they no longer serve any purpose should
        be deleted.  These may exist due to lack of transactional atomicity when replacing
        a contact as part of removal or upload.  If too many removed contacts are or will exist, this
        list will also contain all of the removed contacts as well as any contacts that are
        part of the removal request.
    2) self._contacts_to_remove: list of contacts which should be transitioned to 'removed', but
        currently are not in the 'removed' state.
    """
    # Check for well formed input and build dict of all contacts that have been requested for removal.
    for request_contact_id in self._request_contact_ids:
      if Contact.GetContactSourceFromContactId(request_contact_id) not in Contact.UPLOAD_SOURCES:
        # remove_contacts only allows removal of Manual and iPhone sourced contacts.
        raise InvalidRequestError(BAD_CONTACT_SOURCE, Contact.GetContactSourceFromContactId(request_contact_id))

    # Get existing contacts along with list of contacts that should be deleted as part of dedup.
    existing_contacts_dict, self._contacts_to_delete = \
        yield RemoveContactsOperation._GetAllContactsWithDedup(self._client, self._user_id)

    # Projected count of removed contacts after this operation.
    removed_contact_count = 0
    # Build list of contacts to be removed.
    for existing_contact in existing_contacts_dict.itervalues():
      if existing_contact.IsRemoved():
        removed_contact_count += 1
      elif existing_contact.contact_id in self._request_contact_ids:
        # Not already in removed state, so add to list of contacts to remove during update stage.
        self._contacts_to_remove.append(existing_contact)
        removed_contact_count += 1
      # else case is no-op because there's no match of existing present contact and one being requested for removal.

    if removed_contact_count >= Contact.MAX_REMOVED_CONTACTS_LIMIT:
      # Trigger removed contact reset (garbage collection).
      self._removed_contacts_reset = True

    if self._op.checkpoint is None:
      # Set checkpoint.
      # Checkpoint whether or not we decided to reset the removed contacts.
      yield self._op.SetCheckpoint(self._client, {'removed_contacts_reset': self._removed_contacts_reset})
    elif not self._removed_contacts_reset:
      # Even if we didn't decide during this operation retry to reset the removed contacts, we still need to do it
      #   if we previously decided to because we may have already deleted some of the removed contacts and need to
      #   indicate the removed contact reset in the notification.
      self._removed_contacts_reset = self._op.checkpoint['removed_contacts_reset']

    if self._removed_contacts_reset:
      # Because we've decided to reset the contacts, we'll add more contacts to the delete list:
      #  * Any current contact that's in the 'removed' state.
      #  * Any current non-removed contact that was in the list of contacts to remove.
      for existing_contact in existing_contacts_dict.itervalues():
        if existing_contact.IsRemoved() or existing_contact.contact_id in self._request_contact_ids:
          self._contacts_to_delete.append(existing_contact)

  @gen.coroutine
  def _Update(self):
    """Perform delete/insert of contacts as determined by check phase."""

    @gen.coroutine
    def _RemoveContact(contact_to_remove):
      """Insert a 'removed' contact with the same contact_id as the one being removed and then
      delete the actual contact that's being removed."""
      removed_contact = Contact.CreateRemovedContact(contact_to_remove.user_id,
                                                     contact_to_remove.contact_id,
                                                     self._notify_timestamp)
      yield gen.Task(removed_contact.Update, self._client)
      yield Operation.TriggerFailpoint(self._client)
      yield gen.Task(contact_to_remove.Delete, self._client)

    # First, take care of deleting garbage collected contacts.
    tasks = [gen.Task(contact.Delete, self._client) for contact in self._contacts_to_delete]

    # We only need to replace present contacts with removed contacts if we're NOT doing a removed contacts reset.
    if not self._removed_contacts_reset:
      # Replace contacts being removed with contacts that have a remove label.
      for contact in self._contacts_to_remove:
        tasks.append(_RemoveContact(contact))

    yield tasks

  @gen.coroutine
  def _Notify(self):
    """Creates notifications:
    Notify of all contacts with timestamp greater than or equal to current.
    May also indicate that all 'removed' contacts have been deleted and the client should reset by reloading
    all contacts.
    """
    yield NotificationManager.NotifyRemoveContacts(self._client,
                                                   self._user_id,
                                                   self._notify_timestamp,
                                                   self._removed_contacts_reset)
