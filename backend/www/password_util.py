# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Password-related utilities.

Utility methods for generating a password salt and hash and verifying password against a hash.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import base64
import os

from Crypto.Hash import HMAC, SHA512
from Crypto.Protocol.KDF import PBKDF2
from tornado import escape, gen, web
from viewfinder.backend.base.exceptions import InvalidRequestError, PermissionError
from viewfinder.backend.db.guess import Guess
from viewfinder.backend.db.identity import TOO_MANY_GUESSES_ERROR


_NO_PASSWORD_SET = 'You have not yet set a password for your account.'

_PASSWORD_MISMATCH = 'The password you provided is incorrect.'

_PASSWORD_TOO_SHORT = 'The password you provided is too short. It must be at least 8 characters long.'

_MAX_PASSWORD_GUESSES = 50
"""Limit the number of incorrect attempts to guess the password in any 24-hour period."""


def HashPassword(password, salt):
  """Computes the hash of the given password using 1000 SHA512 iterations."""
  prf = lambda p, s: HMAC.new(p, s, SHA512).digest()
  return base64.b64encode(PBKDF2(escape.utf8(password), base64.b64decode(salt), count=1000, prf=prf))


def GeneratePasswordHash(password):
  """Generates a password hash from the given password str, using a newly generated salt.

  Returns a tuple: (pwd_hash, salt).
  """
  # Ensure that password is at least 8 bytes long.
  if len(password) < 8:
    raise InvalidRequestError(_PASSWORD_TOO_SHORT)

  # The salt value is 16 bytes according to the official recommendation:
  # http://csrc.nist.gov/publications/nistpubs/800-132/nist-sp800-132.pdf
  salt = base64.b64encode(os.urandom(16))

  # Generate the password hash and return it + the salt.
  pwd_hash = HashPassword(password, salt)
  return (pwd_hash, salt)


@gen.coroutine
def ValidateUserPassword(client, user, password):
  """Validates that the user's password matches the given password and that the maximum
  incorrect guess count has not been reached. Raises a PermissionError if it does not match.
  """
  assert user is not None, 'user should exist in login case'
  if user.pwd_hash is None:
    raise PermissionError(_NO_PASSWORD_SET)

  # Salt must already exist.
  assert user.salt, user
  user_salt = user.salt.Decrypt()
  user_pwd_hash = user.pwd_hash.Decrypt()

  yield ValidatePassword(client, user.user_id, password, user_salt, user_pwd_hash)


@gen.coroutine
def ValidatePassword(client, user_id, password, salt, expected_hash):
  """Hashes the given user's password using the given salt, and validates that it matches the
  expected hash. Also ensures that the maximum incorrect guess count has not been exceeded.
  Raises a PermissionError if validation fails.
  """
  actual_hash = HashPassword(password, salt)

  # Limit the number of incorrect password guesses.
  guess_id = Guess.ConstructGuessId('pw', user_id)
  if not (yield Guess.CheckGuessLimit(client, guess_id, _MAX_PASSWORD_GUESSES)):
    raise PermissionError(TOO_MANY_GUESSES_ERROR)

  # If password does not match, increase incorrect guess count and raise error.
  if not web._time_independent_equals(actual_hash, expected_hash):
    yield Guess.ReportIncorrectGuess(client, guess_id)
    raise PermissionError(_PASSWORD_MISMATCH)
