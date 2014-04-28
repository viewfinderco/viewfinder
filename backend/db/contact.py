# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder contact.

  Contact: contact information for a user account
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import base64
import hashlib

from tornado import gen

from viewfinder.backend.base import util
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.range_base import DBRangeObject

@DBObject.map_table_attributes
class Contact(DBRangeObject):
  """Viewfinder contact data object."""
  __slots__ = []

  FACEBOOK = 'fb'
  """Facebook contact source."""

  GMAIL = 'gm'
  """GMail contact source."""

  IPHONE = 'ip'
  """iPhone contact source."""

  MANUAL = 'm'
  """Manual contact source."""

  ALL_SOURCES = [FACEBOOK, GMAIL, IPHONE, MANUAL]
  UPLOAD_SOURCES = [IPHONE, MANUAL]

  MAX_CONTACTS_LIMIT = 10000
  """Max allowed contacts on the server per user (including removed contacts)."""

  MAX_REMOVED_CONTACTS_LIMIT = 1000
  """Number of removed contacts which will trigger garbage collection of removed contacts."""

  REMOVED = 'removed'
  """This contact has been removed from the user's address book."""

  _table = DBObject._schema.GetTable(vf_schema.CONTACT)

  def __init__(self, user_id=None, sort_key=None):
    super(Contact, self).__init__()
    self.user_id = user_id
    self.sort_key = sort_key

  def IsRemoved(self):
    """Returns True if the contact has the Contact.REMOVED label."""
    return Contact.REMOVED in self.labels

  def Update(self, client, callback, expected=None, replace=True, return_col_names=False):
    """Intercept base Update method to ensure that contact_id and sort_key are valid and correct for
    current attribute values."""
    self._AssertValid()
    super(Contact, self).Update(client,
                                callback,
                                expected=expected,
                                replace=replace,
                                return_col_names=return_col_names)

  @classmethod
  def CalculateContactEncodedDigest(cls, **dict_to_hash):
    """Calculate an encoded digest based on the dictionary passed in.  The result is suitable for use
    in constructing the contact_id.
    """
    json_to_hash = util.ToCanonicalJSON(dict_to_hash)
    m = hashlib.sha256()
    m.update(json_to_hash)
    base64_encoded_digest = base64.b64encode(m.digest())
    # Just use half of the base64 encoded digest to save some space.  It will still be quite unique and the
    #   design of the contact_id only depends on uniqueness for reasonable performance, not correctness.
    return base64_encoded_digest[:len(base64_encoded_digest) / 2]

  @classmethod
  def CalculateContactId(cls, contact_dict):
    """Calculate hash from contact dictionary."""
    # We explicitly don't hash identity(deprecated), identities(only present for indexing),
    # contact_source(explicitly part of contact_id), contact_id, sort_key, and user_id
    assert contact_dict.has_key('contact_source'), contact_dict
    assert contact_dict.has_key('identities_properties'), contact_dict
    assert contact_dict['contact_source'] in Contact.ALL_SOURCES, contact_dict
    for identity_properties in contact_dict['identities_properties']:
      assert len(identity_properties) <= 2, contact_dict

    dict_to_hash = {'name': contact_dict.get('name', None),
                    'given_name': contact_dict.get('given_name', None),
                    'family_name': contact_dict.get('family_name', None),
                    'rank': contact_dict.get('rank', None),
                    'identities_properties': contact_dict.get('identities_properties')}
    return contact_dict.get('contact_source') + ':' + Contact.CalculateContactEncodedDigest(**dict_to_hash)

  @classmethod
  def CreateContactDict(cls, user_id, identities_properties, timestamp, contact_source, **kwargs):
    """Creates a dict with all properties needed for a contact.
    The identities_properties parameter is a list of tuples where each tuple is:
      (identity_key, description_string).  Description string is for 'work', 'mobile', 'home', etc...
      designation and may be None.
    This includes calculation of the contact_id and sort_key from timestamp, contact_source, and other attributes.
    Returns: contact dictionary.
    """
    from viewfinder.backend.db.identity import Identity

    contact_dict = {'user_id': user_id,
                    'timestamp': timestamp,
                    'contact_source': contact_source}

    if Contact.REMOVED not in kwargs.get('labels', []):
      # identities is the unique set of canonicalized identities associated with this contact.
      contact_dict['identities'] = {Identity.Canonicalize(identity_properties[0])
                                    for identity_properties in identities_properties}
      contact_dict['identities_properties'] = identities_properties

    contact_dict.update(kwargs)
    if 'contact_id' not in contact_dict:
      contact_dict['contact_id'] = Contact.CalculateContactId(contact_dict)
    if 'sort_key' not in contact_dict:
      contact_dict['sort_key'] = Contact.CreateSortKey(contact_dict['contact_id'], timestamp)

    return contact_dict

  @classmethod
  def CreateFromKeywords(cls, user_id, identities_properties, timestamp, contact_source, **kwargs):
    """Override base CreateWithKeywords which ensures contact_id and sort_key are defined if not provided
    by the caller.
    Returns: Contact object."""
    contact_dict = Contact.CreateContactDict(user_id,
                                             identities_properties,
                                             timestamp,
                                             contact_source,
                                             **kwargs)
    return super(Contact, cls).CreateFromKeywords(**contact_dict)

  @classmethod
  def CreateRemovedContact(cls, user_id, contact_id, timestamp):
    """Create instance of a removed contact for given user_id, contact_id, and timestamp."""
    removed_contact_dict = {'user_id': user_id,
                            'identities_properties': None,
                            'timestamp': timestamp,
                            'contact_source': Contact.GetContactSourceFromContactId(contact_id),
                            'contact_id': contact_id,
                            'sort_key': Contact.CreateSortKey(contact_id, timestamp),
                            'labels': [Contact.REMOVED]}
    return Contact.CreateFromKeywords(**removed_contact_dict)

  @classmethod
  def CreateSortKey(cls, contact_id, timestamp):
    """Create value for sort_key attribute.  This is derived from timestamp and contact_id."""
    prefix = util.CreateSortKeyPrefix(timestamp, randomness=False)
    return prefix + (contact_id if contact_id is not None else '')

  @classmethod
  @gen.coroutine
  def DeleteDuplicates(cls, client, contacts):
    """Given list of contacts, delete any duplicates (preserving the newer contact).
    Returns: list of retained contacts.
    """
    contacts_dict = dict()
    tasks = []
    for contact in contacts:
      if contact.contact_id in contacts_dict:
        if contact.timestamp > contacts_dict[contact.contact_id].timestamp:
          # Delete the one in dictionary and keep the current one.
          contact_to_delete = contacts_dict[contact.contact_id]
          contacts_dict[contact.contact_id] = contact
        else:
          # Keep the one in the dictionary and delete the current one.
          contact_to_delete = contact
        tasks.append(gen.Task(contact_to_delete.Delete, client))
      else:
        contacts_dict[contact.contact_id] = contact

    yield tasks

    raise gen.Return(contacts_dict.values())

  @classmethod
  def GetContactSourceFromContactId(cls, contact_id):
    """Return the contact_id prefix which is the contact_source."""
    return contact_id.split(':', 1)[0]

  @classmethod
  @gen.coroutine
  def VisitContactUserIds(cls, client, contact_identity_key, visitor, consistent_read=False):
    """Visits all users that have the given identity among their contacts. Invokes the
    "visitor" function with each user id. See VisitIndexKeys for additional detail.
    """
    def _VisitContact(contact_key, callback):
      visitor(contact_key.hash_key, callback=callback)

    query_expr = ('contact.identities={id}', {'id': contact_identity_key})
    yield gen.Task(Contact.VisitIndexKeys, client, query_expr, _VisitContact)

  def _AssertValid(self):
    """Assert that contact_id and sort_key are valid and correct for the current contact attributes."""
    # CalculateContactId will assert several things, too.
    if self.IsRemoved():
      # A removed contact is not expected to have a contact_id calculated from it's details
      #   because removed contacts are stored without contact details.
      assert self.contact_source is not None and self.contact_source in Contact.ALL_SOURCES, self
    else:
      contact_id = Contact.CalculateContactId(self._asdict())
      assert contact_id == self.contact_id, self
    assert self.timestamp is not None, self
    sort_key = Contact.CreateSortKey(self.contact_id, self.timestamp)
    assert sort_key == self.sort_key, self
