# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Tracks the number of incorrect attempts that have been made to guess a protected secret.

It is important to track incorrect guesses in order to mitigate brute-force attacks. Each
time a guess is made (correct or incorrect), call Guess.Report, which will track and limit
the number of incorrect guesses.

See the header for the GUESS table in vf_schema.py for additional details about the table.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

from tornado import gen
from viewfinder.backend.base import constants, util
from viewfinder.backend.base.exceptions import TooManyGuessesError
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.hash_base import DBHashObject


@DBObject.map_table_attributes
class Guess(DBHashObject):
  """Viewfinder guess data object."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.GUESS)
  _guesses_key = _table.GetColumn('guesses').key

  def __init__(self, guess_id=None):
    super(Guess, self).__init__()
    self.guess_id = guess_id

  @classmethod
  def ConstructGuessId(cls, type, id):
    """Construct a guess id of the form <type>:<id>."""
    return "%s:%s" % (type, id)

  @classmethod
  @gen.coroutine
  def CheckGuessLimit(cls, client, guess_id, max_guesses):
    """Returns false if the number of incorrect guesses has already exceeded "max_guesses"."""
    guess = yield gen.Task(Guess.Query, client, guess_id, None, must_exist=False)

    # If guess record is expired, ignore it -- it will be re-created in that case.
    now = util.GetCurrentTimestamp()
    if guess is not None and now >= guess.expires:
      guess = None

    raise gen.Return(guess is None or guess.guesses < max_guesses)

  @classmethod
  @gen.coroutine
  def ReportIncorrectGuess(cls, client, guess_id):
    """Records an incorrect guess attempt by incrementing the guesses count."""
    guess = yield gen.Task(Guess.Query, client, guess_id, None, must_exist=False)

    # Increment the incorrect guess count.
    now = util.GetCurrentTimestamp()
    if guess is not None and now < guess.expires:
      guess.guesses += 1
    else:
      guess = Guess(guess_id)
      guess.expires = now + constants.SECONDS_PER_DAY
      guess.guesses = 1

    yield gen.Task(guess.Update, client)
