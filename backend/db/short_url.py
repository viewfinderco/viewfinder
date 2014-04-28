# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Short URL support.

This DB class stores state associated with a particular ShortURL. The state is recovered
from the database when a ShortURL link is followed. See the doc header for ShortURLBaseHandler
for more details.

See the header for the SHORT_URL table in vf_schema.py for additional details about the table.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import logging
import os
import time

from tornado import gen
from viewfinder.backend.base import base64hex, constants, util
from viewfinder.backend.base.exceptions import DBConditionalCheckFailedError, TooManyRetriesError
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.guess import Guess
from viewfinder.backend.db.range_base import DBRangeObject


@DBObject.map_table_attributes
class ShortURL(DBRangeObject):
  """Viewfinder short url data object."""
  __slots__ = []

  KEY_LEN_IN_BYTES = 6
  assert KEY_LEN_IN_BYTES % 3 == 0
  """Size of random key, in bytes. This should always be a multiple of 3."""

  KEY_LEN_IN_BASE64 = KEY_LEN_IN_BYTES * 4 / 3
  """Size of random key, in base-64 chars."""

  _KEY_GEN_TRIES = 5
  """Number of tries to generate a unique key."""

  _table = DBObject._schema.GetTable(vf_schema.SHORT_URL)

  def __init__(self, group_id=None, random_key=None):
    super(ShortURL, self).__init__()
    self.group_id = group_id
    self.random_key = random_key

  def IsExpired(self):
    """Returns true if this ShortURL has expired."""
    return util.GetCurrentTimestamp() >= self.expires

  @gen.coroutine
  def Expire(self, client):
    """Expires the ShortURL by setting the expires field to 0 and calling Update."""
    self.expires = 0
    yield gen.Task(self.Update, client)

  @classmethod
  @gen.coroutine
  def Create(cls, client, group_id, timestamp, expires, **kwargs):
    """Allocate a new ShortURL DB object by finding an unused random key within the group."""
    # Try several times to generate a unique key.
    for i in xrange(ShortURL._KEY_GEN_TRIES):
      # Generate a random 6-byte key, using URL-safe base64 encoding.
      random_key = base64hex.B64HexEncode(os.urandom(ShortURL.KEY_LEN_IN_BYTES))
      short_url = ShortURL(group_id, random_key)
      short_url.timestamp = timestamp
      short_url.expires = expires
      short_url.json = kwargs

      try:
        yield short_url.Update(client, expected={'random_key': False})
      except DBConditionalCheckFailedError as ex:
        # Key is already in use, generate another.
        continue

      raise gen.Return(short_url)

    logging.warning('cannot allocate a unique random key for group id "%s"', group_id)
    raise TooManyRetriesError('Failed to allocate unique URL key.')
