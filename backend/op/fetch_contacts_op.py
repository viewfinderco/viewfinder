# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder FetchContactsOperation.

This operation fetches contacts information from google or facebook for a user.
"""

__authors__ = ['mike@emailscrubbed.com (Mike Purtell)']

import calendar
import iso8601
import json
import logging
import math
import time
import urllib

from itertools import izip
from operator import itemgetter
from tornado import gen, httpclient

from viewfinder.backend.base.exceptions import TooManyRetriesError
from viewfinder.backend.db.base import util
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation
from viewfinder.backend.www import www_util


class FetchContactsOperation(ViewfinderOperation):
  """The FetchContacts operation follows the four phase pattern described in the header of
  operation_map.py (with the exception that no accounting is performed for this operation).
  """

  _FACEBOOK_CONNECTION_HALF_LIFE = 60 * 60 * 24 * 30 * 6  # 1/2 year
  _FACEBOOK_FRIENDS_URL = 'https://graph.facebook.com/me/friends'
  _FACEBOOK_PHOTOS_URL = 'https://graph.facebook.com/me/photos'
  _FACEBOOK_PROFILE_URL = 'https://graph.facebook.com/%s'
  _GOOGLE_CONTACTS_URL = 'https://www.google.com/m8/feeds/contacts/default/full'

  # The source of the following is: https://developers.google.com/gdata/docs/2.0/elements#gdPhoneNumber
  #   These are phone number elements which are a super-set of the email elements.  We'll just use one lookup.
  _GOOGLE_TYPE_LOOKUP = {'http://schemas.google.com/g/2005#assistant': 'Assistant',
                         'http://schemas.google.com/g/2005#callback': 'Callback',
                         'http://schemas.google.com/g/2005#car': 'Car',
                         'http://schemas.google.com/g/2005#company_main': 'Company Main',
                         'http://schemas.google.com/g/2005#fax': 'Fax',
                         'http://schemas.google.com/g/2005#home': 'Home',
                         'http://schemas.google.com/g/2005#home_fax': 'Home Fax',
                         'http://schemas.google.com/g/2005#isdn': 'ISDN',
                         'http://schemas.google.com/g/2005#main': 'Main',
                         'http://schemas.google.com/g/2005#mobile': 'Mobile',
                         # '...#other' means to defer to whatever is in the labels field.
                         # The labels field, if present, will take priority over the rel field where this is.
                         #   If there's nothing in the labels field, we want to stick with None in this case.
                         'http://schemas.google.com/g/2005#other': None,
                         'http://schemas.google.com/g/2005#other_fax': 'Other Fax',
                         'http://schemas.google.com/g/2005#pager': 'Pager',
                         'http://schemas.google.com/g/2005#radio': 'Radio',
                         'http://schemas.google.com/g/2005#telex': 'Telex',
                         'http://schemas.google.com/g/2005#tty_tdd': 'TTY TDD',
                         'http://schemas.google.com/g/2005#work': 'Work',
                         'http://schemas.google.com/g/2005#work_fax': 'Work Fax',
                         'http://schemas.google.com/g/2005#work_mobile': 'Work Mobile',
                         'http://schemas.google.com/g/2005#work_pager': 'Work Pager'}

  _MAX_FETCH_COUNT = 100
  _MAX_FETCH_RETRIES = 3
  _MAX_GOOGLE_CONTACTS = 5000
  _MAX_GOOGLE_RANK = 50

  _PHOTO_CONNECTION_STRENGTHS = {'from': 1.0, 'tag': 1.0, 'like': 0.05}

  # Some tests will set this to skip fetch and update.
  _SKIP_UPDATE_FOR_TEST = False

  def __init__(self, client, user_id, key):
    super(FetchContactsOperation, self).__init__(client)
    self._user_id = user_id
    self._key = key
    self._notify_timestamp = self._op.timestamp
    self._identity = None

    # At a certain point, we determine if we're going to go through the the fetch and update.
    #   This notes the outcome of that decision.
    self._do_fetch_and_update = False

    # Dict of currently known contacts for the contact_source that's being fetched (keyed by contact_id).
    self._existing_contacts_dict = dict()
    # Dict of all contacts fetched (keyed by contact_id).
    self._fetched_contacts = dict()

    # List of tuples (contact_to_insert, contact_to_delete or None)
    #   This also includes 'removed' contacts that may be getting inserted/deleted.
    #   The insert is completed before the delete is initiated.
    self._create_delete_contacts = []
    # List of contacts to delete.  These are garbage collected 'removed' or duplicate contacts.
    #   If a removed contacts reset is triggered, removed contacts are added to this list.
    self._contacts_to_delete = []
    # Dict of all contacts from all sources.  This may be used if removed contacts reset is triggered.
    self._all_contacts_dict = dict()

    # Set to True if removal of contacts would increase the number of removed contacts above
    #   threshold for reset of removed contacts.  This value is checkpointed and once True will
    #   always be True.
    self._removed_contacts_reset = False

    # Number of contact creates skipped because it would have caused Contact.MAX_CONTACTS_LIMIT to be exceeded.
    #   This is for the purpose of logging a warning.
    self._skipped_contact_create_count = 0

    # Track number of removed and present contacts across all contact sources.  This is used to enforce max
    #   contacts limit and for determining if a removed contacts reset should be triggered.
    self._all_removed_contacts_count = 0
    self._all_present_contacts_count = 0

  @classmethod
  @gen.coroutine
  def Execute(cls, client, key, user_id):
    """Entry point called by the operation framework."""
    yield FetchContactsOperation(client, user_id, key)._FetchContactsOp()

  @gen.coroutine
  def _FetchContactsOp(self):
    """Orchestrates the fetch contacts operation by executing each of the phases in turn."""
    yield self._Check()
    self._client.CheckDBNotModified()
    if self._do_fetch_and_update:
      yield self._Update()
    yield Operation.TriggerFailpoint(self._client)
    yield self._Notify()

  @gen.coroutine
  def _Check(self):
    """Check and prepare for update.
    1) Get Identity record for requested identity.
    2) Gather all of the existing known contacts for the relevant contact source.
    3) Fetch the contacts from the relevant contact source (Facebook or GMail).
    4) Prepare for update be determine which contacts should be Created/Removed/Deleted.
    """
    self._identity = yield gen.Task(Identity.Query, self._client, hash_key=self._key, col_names=None)
    assert self._identity.user_id == self._user_id, self

    self._do_fetch_and_update = (self._identity.access_token is not None and
                                 not FetchContactsOperation._SKIP_UPDATE_FOR_TEST and
                                 self._identity.authority in ['Facebook', 'Google'])

    # Get existing contacts and fetch contacts for the given identity.
    if self._do_fetch_and_update:
      yield self._GatherExistingContacts()

      if self._identity.authority == 'Facebook':
        assert not self._identity.expires
        yield self._FetchFacebookContacts()
      else:
        assert self._identity.authority == 'Google', self._identity
        yield self._FetchGoogleContacts()

    if self._op.checkpoint is not None:
      # Recall what we determined last time about removed contacts reset.
      self._removed_contacts_reset = self._op.checkpoint['removed_contacts_reset']

    if self._do_fetch_and_update:
      # Process everything we know at this point and get it into shape for the update phase.
      self._PrepareFetchedContactsForUpdate()

    # Set checkpoint.
    if self._removed_contacts_reset:
      # Only need to set checkpoint if we determined that we need to do the removed contacts reset.
      # We never set it to False once it's been set to True.
      yield self._op.SetCheckpoint(self._client, {'removed_contacts_reset': self._removed_contacts_reset})

  @gen.coroutine
  def _Update(self):
    """Perform insert/(replace) of fetched contacts as well as deletion of duplicate contacts."""
    @gen.coroutine
    def _InsertDeleteContact(contact_to_insert, contact_to_delete):
      """Insert followed by delete (after insert is complete)."""
      if contact_to_insert is not None:
        yield gen.Task(contact_to_insert.Update, self._client)
      yield Operation.TriggerFailpoint(self._client)
      if contact_to_delete is not None:
        yield gen.Task(contact_to_delete.Delete, self._client)

    # Delete superfluous contact rows and 'removed' contacts for removed contacts reset.
    tasks = [gen.Task(contact_to_delete.Delete, self._client) for contact_to_delete in self._contacts_to_delete]
    # Insert (and maybe replace) fetched contacts.
    for contact_to_insert, contact_to_delete in self._create_delete_contacts:
      tasks.append(_InsertDeleteContact(contact_to_insert, contact_to_delete))
    yield tasks

    logging.info('successfully imported %d %s contacts for user %d' %
                 (len(self._fetched_contacts) - self._skipped_contact_create_count,
                  self._identity.authority,
                  self._user_id))
    self._identity.last_fetch = util.GetCurrentTimestamp()
    yield gen.Task(self._identity.Update, self._client)

  @gen.coroutine
  def _Notify(self):
    """Creates notification:
    Notify of all contacts with timestamp greater than or equal to current.
    May also indicate that all 'removed' contacts have been deleted and the client should reset by reloading
    all contacts.
    """
    yield NotificationManager.NotifyFetchContacts(self._client,
                                                  self._user_id,
                                                  self._notify_timestamp,
                                                  self._removed_contacts_reset)

  @gen.coroutine
  def _FetchGoogleContacts(self):
    """Do GMail specific data gathering and checking.
    Queries Google data API for contacts in JSON format.
    """
    # Track fetched contacts regardless of rank in order to dedup contacts retrieved from Google.
    assert self._identity.refresh_token is not None, self._identity

    if self._identity.expires and self._identity.expires < time.time():
      yield gen.Task(self._identity.RefreshGoogleAccessToken, self._client)

    logging.info('fetching Google contacts for identity %r...' % self._identity)
    http_client = httpclient.AsyncHTTPClient()
    # Google data API uses 1-based start index.
    start_index = 1
    retries = 0
    count = FetchContactsOperation._MAX_FETCH_COUNT
    while True:
      if retries >= FetchContactsOperation._MAX_FETCH_RETRIES:
        raise TooManyRetriesError('failed to fetch contacts %d times; aborting' % retries)
      logging.info('fetching next %d Google contacts for user %d' %
                   (count, self._user_id))
      url = FetchContactsOperation._GOOGLE_CONTACTS_URL + '?' + \
          urllib.urlencode({'max-results': count,
                            'start-index': start_index,
                            'alt': 'json'})
      response = yield gen.Task(http_client.fetch,
                                url,
                                method='GET',
                                headers={'Authorization': 'OAuth %s' % self._identity.access_token,
                                        'GData-Version': 3.0})
      try:
        response_dict = www_util.ParseJSONResponse(response)['feed']
      except Exception as exc:
        logging.warning('failed to fetch Google contacts: %s' % exc)
        retries += 1
        continue

      # Temporarily log additional information to figure out why some responses don't seem to have "entry" fields.
      if 'entry' not in response_dict:
        logging.warning('Missing entry: %s' % json.dumps(response_dict, indent=True))

      for c_dict in response_dict.get('entry', []):
        # Build identities_properties list from all emails/phone numbers associated with this contact.
        identities_properties = []
        # Process emails first so that if there are any emails, one of them will be first in the
        #   identities_properties list.  This will be *the* identity used for down-level client message
        #   migration.
        for email_info in c_dict.get('gd$email', []):
          email = email_info.get('address', None)
          if email is not None:
            email_type = FetchContactsOperation._GOOGLE_TYPE_LOOKUP.get(email_info.get('rel', None), None)
            identity_properties = ('Email:' + Identity.CanonicalizeEmail(email),
                                   email_info.get('label', email_type))
            if email_info.get('primary', False):
              # Insert the primary email address at the head of the list.  Older clients will get this
              #   as the only email address for this contact when they query_contacts.
              identities_properties.insert(0, identity_properties)
            else:
              identities_properties.append(identity_properties)
        for phone_info in c_dict.get('gd$phoneNumber', []):
          # See RFC3966: "The tel URI for Telephone Numbers" for more information about this format.
          #   It should be 'tel:' + E.164 format phone number.
          phone = phone_info.get('uri', None)
          if phone is not None and phone.startswith('tel:+') and Identity.CanCanonicalizePhone(phone[4:]):
            phone_type = FetchContactsOperation._GOOGLE_TYPE_LOOKUP.get(phone_info.get('rel', None), None)
            identities_properties.append(('Phone:' + Identity.CanonicalizePhone(phone[4:]),
                                          phone_info.get('label', phone_type)))

        if len(identities_properties) == 0:
          continue

        # Normalize name to None if empty.
        gd_name = c_dict.get('gd$name', None)
        if gd_name is not None:
          names = {'name': gd_name.get('gd$fullName', {}).get('$t', None),
                   'given_name': gd_name.get('gd$givenName', {}).get('$t', None),
                   'family_name': gd_name.get('gd$familyName', {}).get('$t', None)}
        else:
          names = {'name': None, 'given_name': None, 'family_name': None}

        fetched_contact = Contact.CreateFromKeywords(self._user_id,
                                                     identities_properties,
                                                     self._notify_timestamp,
                                                     Contact.GMAIL,
                                                     rank=None,
                                                     **names)
        self._fetched_contacts[fetched_contact.contact_id] = fetched_contact

      # Prepare to fetch next batch.
      # Indexes are 1-based, so add 1 to max_index.
      if 'openSearch$totalResults' in response_dict:
        max_index = int(response_dict['openSearch$totalResults']['$t']) + 1
      else:
        max_index = FetchContactsOperation._MAX_GOOGLE_CONTACTS + 1
      next_index = int(response_dict['openSearch$startIndex']['$t']) + len(response_dict.get('entry', []))
      count = min(max_index - next_index, FetchContactsOperation._MAX_FETCH_COUNT)
      if len(self._fetched_contacts) < FetchContactsOperation._MAX_GOOGLE_CONTACTS and count > 0:
        start_index = next_index
        retries = 0
        continue
      else:
        raise gen.Return()

  @gen.coroutine
  def _FetchFacebookContacts(self):
    """Do Facebook specific data gathering and checking.
    Queries Facebook graph API for friend list using the identity's access token.
    """
    @gen.coroutine
    def _DetermineFacebookRankings():
      """Uses The tags from friends and the authors of the
      photos are used to determine friend rank for facebook contacts. The
      basic algorithm is:

      sorted([sum(exp_decay(pc.time) * strength(pc)) for pc in photos])

      A 'pc' in is a photo connection. There are three types, ordered by
      the 'strength' they impart in the summation equation:
        - from: the poster of a photo (strength=1.0)
        - tag: another user tagged in the photo (strength=1.0)
        - like: a facebook user who 'liked' the photo (strength=0.25)
      Exponential decay uses _FACEBOOK_CONNECTION_HALF_LIFE for half life.

      The rankings are passed to the provided callback as a dictionary of
      identity ('FacebookGraph:<id>') => rank.
      """
      logging.info('determining facebook contact rankings for identity %r...' % self._identity)
      http_client = httpclient.AsyncHTTPClient()
      friends = dict()  # facebook id => connection strength
      likes = dict()
      now = util.GetCurrentTimestamp()

      def _ComputeScore(create_iso8601, conn_type):
        """Computes the strength of a photo connection based on the time
        that's passed and the connection type.
        """
        decay = 0.001  # default is 1/1000th
        if create_iso8601:
          dt = iso8601.parse_date(create_iso8601)
          create_time = calendar.timegm(dt.utctimetuple())
          decay = math.exp(-math.log(2) * (now - create_time) /
                            FetchContactsOperation._FACEBOOK_CONNECTION_HALF_LIFE)
        return decay * FetchContactsOperation._PHOTO_CONNECTION_STRENGTHS[conn_type]

      # Construct the URL that will kick things off.
      url = FetchContactsOperation._FACEBOOK_PHOTOS_URL + '?' + \
          urllib.urlencode({'access_token': self._identity.access_token,
                            'format': 'json', 'limit': FetchContactsOperation._MAX_FETCH_COUNT})
      while True:
        logging.info('querying next %d Facebook photos for user %d' %
                     (FetchContactsOperation._MAX_FETCH_COUNT, self._user_id))
        response = yield gen.Task(http_client.fetch, url, method='GET')
        response_dict = www_util.ParseJSONResponse(response)
        for p_dict in response_dict['data']:
          created_time = p_dict.get('created_time', None)
          if p_dict.get('from', None) and p_dict['from']['id']:
            from_id = p_dict['from']['id']
            friends[from_id] = friends.get(from_id, 0.0) + \
                _ComputeScore(created_time, 'from')

          if p_dict.get('tags', None):
            for tag in p_dict['tags']['data']:
              if tag.get('id', None) is not None:
                friends[tag['id']] = friends.get(tag['id'], 0.0) + \
                    _ComputeScore(tag.get('created_time', None), 'tag')

          if p_dict.get('likes', None):
            for like in p_dict['likes']['data']:
              if like.get('id', None) is not None:
                likes[like['id']] = likes.get(like['id'], 0.0) + \
                    _ComputeScore(created_time, 'like')

        if (len(response_dict['data']) == FetchContactsOperation._MAX_FETCH_COUNT and
            response_dict.has_key('paging') and response_dict['paging'].has_key('next')):
          url = response_dict['paging']['next']
        else:
          for fb_id in friends.keys():
            friends[fb_id] += likes.get(fb_id, 0.0)
          ranked_friends = sorted(friends.items(), key=itemgetter(1), reverse=True)
          logging.info('successfully ranked %d Facebook contacts for user %d' %
                       (len(ranked_friends), self._user_id))
          raise gen.Return(dict([('FacebookGraph:%s' % fb_id, rank) for rank, (fb_id, _) in \
                                izip(xrange(len(ranked_friends)), ranked_friends)]))

    logging.info('fetching Facebook contacts for identity %r...' % self._identity)
    http_client = httpclient.AsyncHTTPClient()
    # Track fetched contacts regardless of rank in order to dedup contacts retrieved from Facebook.
    rankless_ids = set()

    # First get the rankings and then fetch the contacts.
    rankings = yield _DetermineFacebookRankings()
    url = FetchContactsOperation._FACEBOOK_FRIENDS_URL + '?' + \
        urllib.urlencode({'fields': 'first_name,name,last_name',
                          'access_token': self._identity.access_token,
                          'format': 'json', 'limit': FetchContactsOperation._MAX_FETCH_COUNT})
    retries = 0
    while True:
      if retries >= FetchContactsOperation._MAX_FETCH_RETRIES:
        raise TooManyRetriesError('failed to fetch contacts %d times; aborting' % retries)
      logging.info('fetching next %d Facebook contacts for user %d' %
                   (FetchContactsOperation._MAX_FETCH_COUNT, self._user_id))
      response = yield gen.Task(http_client.fetch, url, method='GET')
      try:
        response_dict = www_util.ParseJSONResponse(response)
      except Exception as exc:
        logging.warning('failed to fetch Facebook contacts: %s' % exc)
        retries += 1
        continue

      for c_dict in response_dict['data']:
        if c_dict.has_key('id'):
          ident = 'FacebookGraph:%s' % c_dict['id']

          # Skip contact if name is not present, or is empty.
          name = c_dict.get('name', None)
          if name:
            names = {'name': name,
                     'given_name': c_dict.get('first_name', None),
                     'family_name': c_dict.get('last_name', None)}

            # Check to see if we've already processed an identical contact.
            rankless_id = Contact.CalculateContactEncodedDigest(identities_properties=[(ident, None)], **names)
            if rankless_id in rankless_ids:
              # Duplicate among fetched contacts. Skip it.
              continue
            else:
              rankless_ids.add(rankless_id)

            rank = rankings[ident] if ident in rankings else None
            fetched_contact = Contact.CreateFromKeywords(self._user_id,
                                                         [(ident, None)],
                                                         self._notify_timestamp,
                                                         Contact.FACEBOOK,
                                                         rank=rank,
                                                         **names)
            self._fetched_contacts[fetched_contact.contact_id] = fetched_contact

      # Prepare to fetch next batch.
      if (len(response_dict['data']) == FetchContactsOperation._MAX_FETCH_COUNT and
          response_dict.has_key('paging') and response_dict['paging'].has_key('next')):
        retries = 0
        url = response_dict['paging']['next']
      else:
        break

  @gen.coroutine
  def _GatherExistingContacts(self):
    """Query all contacts in preparation for refresh; this allows us to
    update only contacts which have been modified.  Also get list of contacts that should be
    deleted (during update phase) for the purpose of garbage collection/dedup.
    """
    self._all_contacts_dict, self._contacts_to_delete = \
        yield FetchContactsOperation._GetAllContactsWithDedup(self._client, self._user_id)

    for contact in self._all_contacts_dict.itervalues():
      # Compute total count of present and removed contacts to be used for enforcing Contact.MAX_CONTACTS_LIMIT
      # and determining if a removed contacts reset is needed.
      if contact.IsRemoved():
        self._all_removed_contacts_count += 1
      else:
        self._all_present_contacts_count += 1

      # Create contact dict from contact list filtered for the appropriate contact source.
      if ((self._identity.authority == 'Facebook' and contact.contact_source == Contact.FACEBOOK) or
          (self._identity.authority == 'Google' and contact.contact_source == Contact.GMAIL)):
        self._existing_contacts_dict[contact.contact_id] = contact

  def _PrepareFetchedContactsForUpdate(self):
    """Process fetched contacts.  Figure out which ones to create/remove/delete/keep.
    On entry, we have three dicts with contacts:
    * All of the contacts that we just fetched: self._fetched_contacts
    * All of the contacts from the same source that are currently persisted: self._existing_contacts_dict.
    * All of the contacts (regardless of source) that are currently persisted: self._all_contacts_dict.
    The existing_contacts_dict contains contacts that are either present or in the 'removed' state.
    Two lists are consumed by the update phase after this phase is complete:
    * self._create_delete_contacts: tuples of insert/delete contacts pairs.
    * self._contacts_to_delete: contacts to be deleted.
    """
    contacts_to_unremove = []  # Are currently 'removed' and will now be present.
    contacts_to_create = []  # Currently unknown but will now be present.
    # Create a dict of all present contacts and then while iterating, remove fetched contacts so that the remaining
    #   contacts will be the ones that have been removed from the contact source since the last fetch operation.
    contacts_to_remove = {c.contact_id: c for c in self._existing_contacts_dict.itervalues() if not c.IsRemoved()}
    for fetched_contact in self._fetched_contacts.itervalues():
      existing_contact = self._existing_contacts_dict.get(fetched_contact.contact_id, None)
      if existing_contact is None:
        # We don't know anything about this contact_id, so we'll create a contact.
        contacts_to_create.append(fetched_contact)
      else:
        if existing_contact.IsRemoved():
          # Currently this contact is in a removed state, but the contact source now says it's present
          #   so add it to un-remove list.  A new contact will be created the the 'removed' contact will be deleted.
          contacts_to_unremove.append(fetched_contact)
        else:
          # This existing contact is also present in fetched contacts, so remove it from removed dict.  After
          #   we're done iterating over all the fetched contacts, this dict will contain all currently existing
          #   contacts which should be removed because the fetched contacts source no longer contains it.
          contacts_to_remove.pop(fetched_contact.contact_id, None)

    # Determine if the contacts being removed should trigger a removed contacts reset.
    if self._all_removed_contacts_count + len(contacts_to_remove) >= Contact.MAX_REMOVED_CONTACTS_LIMIT:
      self._removed_contacts_reset = True

    # Get self._create_delete_contacts into desired state for update phase.
    for contact in contacts_to_remove.itervalues():
      if self._removed_contacts_reset:
        # Don't create any removed contacts if we decided to do a removed contacts reset.
        removed_contact = None
      else:
        removed_contact = Contact.CreateRemovedContact(self._user_id, contact.contact_id, self._notify_timestamp)
      self._create_delete_contacts.append((removed_contact, contact))
      assert not contact.IsRemoved(), contact
      self._all_present_contacts_count -= 1
    for contact in contacts_to_unremove:
      delete_contact = self._existing_contacts_dict[contact.contact_id]
      assert delete_contact.IsRemoved(), delete_contact
      if self._all_present_contacts_count < Contact.MAX_CONTACTS_LIMIT:
        self._create_delete_contacts.append((contact, delete_contact))
        self._all_present_contacts_count += 1
      else:
        # This contact will remain in the 'removed' state.
        self._skipped_contact_create_count += 1
    for contact in contacts_to_create:
      if self._all_present_contacts_count < Contact.MAX_CONTACTS_LIMIT:
        self._create_delete_contacts.append((contact, None))
        self._all_present_contacts_count += 1
      else:
        # This just won't get created.
        self._skipped_contact_create_count += 1
    if self._removed_contacts_reset:
      for contact in self._all_contacts_dict.itervalues():
        if contact.IsRemoved():
          self._contacts_to_delete.append(contact)

    if self._skipped_contact_create_count > 0:
      logging.warning('Skipped creation of %d fetched contacts due to max contact limit' %
                      self._skipped_contact_create_count)
