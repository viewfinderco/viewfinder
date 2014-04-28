# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder identity.

Identities are provided by OAuth authorities such as Google, Facebook
or Twitter. A viewfinder user account may have multiple identities for
a user. However, each identity may be associated with only one viewfinder
account.

TODO(spencer): notice contacts no longer being fetched and delete them.
               The hard part is figuring out a good way to communicate
               this info to the client. The deletion just requires keeping
               track of which contacts in the full contacts dict are no
               longer being fetched. Not a huge priority as contacts are
               not often deleted (though Facebook friends may be).

  Identity: viewfinder identity.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import calendar
import iso8601
import json
import logging
import math
import phonenumbers
import time
import urllib

from Crypto.Random import random
from functools import partial
from itertools import izip
from operator import itemgetter
from tornado import gen, httpclient, web
from viewfinder.backend.base import base64hex, constants, secrets, util
from viewfinder.backend.base.exceptions import ExpiredError, InvalidRequestError
from viewfinder.backend.base.exceptions import PermissionError, TooManyGuessesError
from viewfinder.backend.base.exceptions import TooManyRetriesError
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.guess import Guess
from viewfinder.backend.db.hash_base import DBHashObject
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.notification import Notification
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.short_url import ShortURL
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.resources.message.error_messages import BAD_IDENTITY, INCORRECT_ACCESS_CODE
from viewfinder.backend.www import www_util


EXPIRED_EMAIL_LINK_ERROR = 'The link in your email has expired or already been used. ' + \
                           'Please retry account sign up or log on.'

EXPIRED_ACCESS_CODE_ERROR = 'The access code has expired or already been used. ' + \
                            'Please retry account sign up or log on.'

TOO_MANY_GUESSES_ERROR = 'Your account has been locked for 24 hours, due to repeated unsuccessful attempts ' + \
                         'to log on. If this was not you, please e-mail support@emailscrubbed.com.'


@DBObject.map_table_attributes
class Identity(DBHashObject):
  """Viewfinder identity."""

  _IDENTITY_SCHEMES = ('FacebookGraph', 'Email', 'Phone', 'Local')
  _GOOGLE_REFRESH_URL = 'https://accounts.google.com/o/oauth2/token'

  _TIME_TO_INVITIATION_EXPIRATION = constants.SECONDS_PER_DAY * 30
  """Expire prospective user links after 30 days."""

  _MAX_GUESSES = 10
  """Maximum number of access token guesses before lock-out."""

  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.IDENTITY)

  def __init__(self, key=None, user_id=None):
    """Creates a new identity with the specified key."""
    super(Identity, self).__init__()
    self.key = key
    self.user_id = user_id

  @classmethod
  def ShouldScrubColumn(cls, name):
    return name in ('access_code', 'access_token', 'refresh_token')

  @classmethod
  def ValidateKey(cls, identity_key):
    """Validates that the identity key has a valid format and is canonicalized."""
    if Identity.Canonicalize(identity_key) != identity_key:
      raise InvalidRequestError('Identity %s is not in canonical form.' % identity_key)

  @classmethod
  def Canonicalize(cls, identity_key):
    """Returns the canonical form of the given identity key."""
    for prefix in ['Email:', 'Phone:', 'FacebookGraph:', 'Local:', 'VF:']:
      if identity_key.startswith(prefix):
        value = identity_key[len(prefix):]
        if prefix == 'Email:':
          canonical_value = Identity.CanonicalizeEmail(value)
          if value is not canonical_value:
            identity_key = prefix + canonical_value
        elif prefix == 'Phone:':
          canonical_value = Identity.CanonicalizePhone(value)
          if value is not canonical_value:
            identity_key = prefix + canonical_value

        # Valid prefix, but no canonicalization necessary.
        return identity_key

    raise InvalidRequestError('Scheme for identity %s unknown.' % identity_key)

  @classmethod
  def CanonicalizeEmail(cls, email):
    """Given an arbitrary string, validates that it is in legal email format. Normalizes
    the email by converting it to lower case and returns it.

    TODO(Andy): Add validation that email at least contains the '@' symbol.

    Consistent with the iOS client's ContactManager::CanonicalizeEmail() function.
    """
    return email if email.islower() else email.lower()

  @classmethod
  def CanonicalizePhone(cls, phone):
    """Given an arbitrary string, validates that it is in the expected E.164 phone number
    format. Since E.164 phone numbers are already canonical, there is no additional
    normalization step to take. Returns the valid, canonical phone number in E.164 format.
    """
    if not phone:
      raise InvalidRequestError('Phone number cannot be empty.')

    if phone[0] != '+':
      raise InvalidRequestError('Phone number "%s" is not in E.164 format.' % phone)

    try:
      phone_num = phonenumbers.parse(phone)
    except phonenumbers.phonenumberutil.NumberParseException:
      raise InvalidRequestError('"%s" is not a phone number.' % phone)

    if not phonenumbers.is_possible_number(phone_num):
      raise InvalidRequestError('"%s" is not a possible phone number.' % phone)

    return phone

  @classmethod
  def CanCanonicalizePhone(cls, phone):
    """Given an arbitrary string, checks that it is in the expected E.164 phone number
    format.
    Returns: True if phone number can be successfully canonicalized.
    """
    try:
      Identity.CanonicalizePhone(phone)
    except InvalidRequestError:
      return False
    return True

  @classmethod
  @gen.coroutine
  def CreateProspective(cls, client, identity_key, user_id, timestamp):
    """Creates identity for a new prospective user. This typically happens when photos are
    shared with a contact that is not yet a Viewfinder user.
    """
    # Make sure that identity is not being bound to a different user.
    identity = yield gen.Task(Identity.Query, client, identity_key, None, must_exist=False)
    if identity is None:
      identity = Identity.CreateFromKeywords(key=identity_key)
    else:
      assert identity.user_id is None or identity.user_id == user_id, \
             'the identity is already in use: %s' % identity

    identity.user_id = user_id

    # Prospective user linking always done by authority of Viewfinder. 
    identity.authority = 'Viewfinder'

    yield gen.Task(identity.Update, client)

    # Update all contacts that refer to this identity.
    yield identity._RewriteContacts(client, timestamp)

    raise gen.Return(identity)

  @classmethod
  @gen.coroutine
  def CreateInvitationURL(cls, client, user_id, identity_key, viewpoint_id, default_url):
    """Creates and returns a prospective user invitation ShortURL object. The URL is handled
    by an instance of AuthProspectiveHandler, which is "listening" at "/pr/...". The ShortURL
    group is partitioned by user id so that incorrect guesses only affect a single user.
    """
    identity_type, identity_value = Identity.SplitKey(identity_key)
    now = util.GetCurrentTimestamp()
    expires = now + Identity._TIME_TO_INVITIATION_EXPIRATION
    encoded_user_id = base64hex.B64HexEncode(util.EncodeVarLengthNumber(user_id), padding=False)
    short_url = yield ShortURL.Create(client,
                                      group_id='pr/%s' % encoded_user_id,
                                      timestamp=now,
                                      expires=expires,
                                      identity_key=identity_key,
                                      viewpoint_id=viewpoint_id,
                                      default_url=default_url,
                                      is_sms=identity_type == 'Phone')

    raise gen.Return(short_url)

  @gen.coroutine
  def CreateAccessTokenURL(self, client, group_id, use_short_token, **kwargs):
    """Creates a verification access token.

    The token is associated with a ShortURL that will be sent to the identity email address
    or phone number. Following the URL will reveal the access token. The user that presents
    the correct token to Identity.VerifyAccessToken is assumed to be in control of that email
    address or SMS number.

    Returns the ShortURL that was generated.
    """
    identity_type, value = Identity.SplitKey(self.key)
    num_digits, good_for = Identity.GetAccessTokenSettings(identity_type, use_short_token)

    now = util.GetCurrentTimestamp()
    access_token = None
    if self.authority == 'Viewfinder' and now < self.expires and \
       self.access_token is not None and len(self.access_token) == num_digits:
      # Re-use the access token.
      access_token = self.access_token

    if access_token is None:
      # Generate new token, which is a random decimal number of 4 or 9 decimal digits.
      format = '%0' + str(num_digits) + 'd'
      access_token = format % random.randint(0, 10 ** num_digits - 1)

    # Create a ShortURL that contains the access token, along with caller-supplied parameters.
    expires = now + good_for
    short_url = yield ShortURL.Create(client,
                                      group_id,
                                      timestamp=now,
                                      expires=expires,
                                      access_token=access_token,
                                      **kwargs)

    # Update the identity to record the access token and short url information.
    self.authority = 'Viewfinder'
    self.access_token = access_token
    self.expires = expires
    self.json_attrs = {'group_id': short_url.group_id, 'random_key': short_url.random_key}
    yield gen.Task(self.Update, client)

    # Check whether user account is locked due to too many guesses.
    guess_id = self._ConstructAccessTokenGuessId(identity_type, self.user_id)
    if not (yield Guess.CheckGuessLimit(client, guess_id, Identity._MAX_GUESSES)):
      raise TooManyGuessesError(TOO_MANY_GUESSES_ERROR)

    raise gen.Return(short_url)

  @gen.coroutine
  def VerifyAccessToken(self, client, access_token):
    """Verifies the correctness of the given access token, that was previously generated in
    response to a CreateAccessTokenURL call. Verification will fail if any of these conditions
    is false.

      1. The access token is expired.
      2. Too many incorrect attempts to guess the token have been made in the past.
      3. The access token does not match.
    """
    identity_type, identity_value = Identity.SplitKey(self.key)
    now = time.time()

    if identity_type == 'Email':
      error = ExpiredError(EXPIRED_EMAIL_LINK_ERROR)
    else:
      error = ExpiredError(EXPIRED_ACCESS_CODE_ERROR)

    if self.authority != 'Viewfinder':
      # The most likely case here is that the user clicked an old link in their inbox. In the interim since
      # receiving the link, they may have logged in with Google, which would update the authority to Google.
      # In this case, the ExpiredError is an appropriate error message since the link is expired.
      logging.warning('the authority is not "Viewfinder" for identity "%s"', self.key)
      raise error

    if now >= self.expires:
      # Either the access token has expired, or has already been used up.
      logging.warning('the access token has expired for identity "%s"', self.key)
      raise error

    # Fail if too many incorrect guesses have been made.
    guess_id = self._ConstructAccessTokenGuessId(identity_type, self.user_id)
    if not (yield Guess.CheckGuessLimit(client, guess_id, Identity._MAX_GUESSES)):
      logging.warning('too many access token guesses have been made for identity "%s"', self.key)
      raise TooManyGuessesError(TOO_MANY_GUESSES_ERROR)

    # Increment incorrect guess account and raise permission error if the access code did not match.
    if not web._time_independent_equals(self.access_token, access_token):
      logging.warning('the access token "%s" does not match for identity "%s"', access_token, self.key)
      yield Guess.ReportIncorrectGuess(client, guess_id)
      raise PermissionError(INCORRECT_ACCESS_CODE, identity_value=Identity.GetDescription(self.key))

  @classmethod
  @gen.coroutine
  def VerifyConfirmedIdentity(cls, client, identity_key, access_token):
    """Verifies that the specified access token matches the one stored in the identity. If
    this is the case, then the caller has confirmed control of the identity. Returns the
    identity DB object if so, else raises a permission exception.
    """
    # Validate the identity and access token.
    Identity.ValidateKey(identity_key)
    identity = yield gen.Task(Identity.Query, client, identity_key, None, must_exist=False)
    if identity is None:
      raise InvalidRequestError(BAD_IDENTITY, identity_key=identity_key)

    yield identity.VerifyAccessToken(client, access_token)

    # Expire the access token now that it has been used.
    identity.expires = 0

    # Reset auth throttling limit since access token has been successfully redeemed.
    identity.auth_throttle = None

    identity.Update(client)

    raise gen.Return(identity)

  @classmethod
  @gen.coroutine
  def UnlinkIdentity(cls, client, user_id, key, timestamp):
    """Unlinks the specified identity from the account identified by 'user_id'. Queries all
    contacts which reference the identity and update their timestamps so that they will be
    picked up by query_contacts.
    """
    identity = yield gen.Task(Identity.Query, client, key, None)
    assert identity.user_id is None or identity.user_id == user_id, identity
    yield identity._RewriteContacts(client, timestamp)
    yield gen.Task(identity.Delete, client)

  @classmethod
  def GetDescription(cls, identity_key):
    """Returns a description of the specified identity key suitable for UI display."""
    identity_type, value = Identity.SplitKey(identity_key)
    if identity_type == 'Email':
      return value
    elif identity_type == 'FacebookGraph':
      return 'your Facebook account'
    elif identity_type == 'Phone':
      phone = phonenumbers.parse(value)
      return phonenumbers.format_number(phone, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    elif identity_type == 'Local':
      return 'local identity'
    raise InvalidRequestError('Scheme for identity %s unknown.' % identity_key)

  @classmethod
  def SplitKey(cls, identity_key):
    """Splits the given identity key of the form <type>:<value> and returns the (type, value)
    as a tuple.
    """
    return identity_key.split(':', 1)

  @classmethod
  def GetAccessTokenSettings(cls, identity_type, use_short_token):
    """Returns settings that control how the access token for various identity types behaves.
    The settings are returned as a tuple:

      (digit_count, good_for)

    digit_count: number of decimal digits in the access code
    good_for: time span (in seconds) during which the token is accepted
    """
    if identity_type == 'Phone' or use_short_token:
      # 4-digit token, expire token after an hour.
      return (4, constants.SECONDS_PER_HOUR)
    elif identity_type == 'Email':
      # 9-digit token, expire token after a day.
      return (9, constants.SECONDS_PER_DAY)

    assert False, 'unsupported identity type "%s"' % identity_type

  def RefreshGoogleAccessToken(self, client, callback):
    """Refreshes an expired google access token using the refresh token.
    """
    def _OnRefresh(response):
      try:
        response_dict = www_util.ParseJSONResponse(response)
      except web.HTTPError as e:
        if e.status_code == 400:
          logging.error('%s: failed to refresh access token; clearing refresh token' % e)
          with util.ExceptionBarrier(util.LogExceptionCallback):
            self.refresh_token = None
            self.Update(client, util.NoCallback)
        raise

      self.access_token = response_dict['access_token']
      self.expires = time.time() + response_dict['expires_in']
      callback()

    body = urllib.urlencode({'refresh_token': self.refresh_token,
                             'client_id': secrets.GetSecret('google_client_id'),
                             'client_secret': secrets.GetSecret('google_client_secret'),
                             'grant_type': 'refresh_token'})
    http_client = httpclient.AsyncHTTPClient()
    http_client.fetch(Identity._GOOGLE_REFRESH_URL, method='POST', callback=_OnRefresh, body=body)

  @classmethod
  def _ConstructAccessTokenGuessId(cls, identity_type, user_id):
    """Constructs an access token guess id value, used to limit the number of incorrect guesses
    that can be made for a particular identity type + user.
    """
    if identity_type == 'Email':
      return Guess.ConstructGuessId('em', user_id)

    assert identity_type == 'Phone', identity_type
    return Guess.ConstructGuessId('ph', user_id)

  @gen.coroutine
  def _RewriteContacts(self, client, timestamp):
    """Rewrites all contacts which refer to this identity. All timestamps are updated so that
    query_contacts will pick them up.
    """
    @gen.coroutine
    def _RewriteOneContact(co):
      """Update the given contact's timestamp."""
      new_co = Contact.CreateFromKeywords(co.user_id,
                                          co.identities_properties,
                                          timestamp,
                                          co.contact_source,
                                          name=co.name,
                                          given_name=co.given_name,
                                          family_name=co.family_name,
                                          rank=co.rank)

      # Only rewrite if timestamp is different.
      if co.sort_key != new_co.sort_key:
        yield gen.Task(new_co.Update, client)
        yield gen.Task(co.Delete, client)

    query_expr = ('contact.identities={id}', {'id': self.key})
    contacts = yield gen.Task(Contact.IndexQuery, client, query_expr, None)

    # Update each contact which points to this identity.
    yield [_RewriteOneContact(co) for co in contacts]

  @classmethod
  @gen.coroutine
  def UnlinkIdentityOperation(cls, client, user_id, identity):
    """Unlinks the specified identity from any associated viewfinder user."""
    # All contacts created during UnlinkIdentity are based on the current operation's timestamp.
    timestamp = Operation.GetCurrent().timestamp

    yield Identity.UnlinkIdentity(client, user_id, identity, timestamp)

    # Notify clients of any contacts that have been updated.
    yield NotificationManager.NotifyUnlinkIdentity(client, user_id, identity, timestamp)
