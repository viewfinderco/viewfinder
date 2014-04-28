#!/usr/bin/env python
#
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Command-line tool for creating and encrypting secrets using the
secrets_manager module.

% python -m viewfinder.backend.base.secrets_tool \
    --secrets_mode={list_secrets, encrypt_secrets, get_secret,
                    put_secret, put_crypt_keyset}
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import json
import logging
import sys

from tornado import ioloop, options
from viewfinder.backend.base import base_options  # imported for option definitions
from viewfinder.backend.base import secrets, util


options.define('secrets_mode', 'list_secrets',
               help='mode for command line operation; see help text in module')

options.define('secret', '', help='name of the secret to put or get')

options.define('shared', default=True,
               help='work on the shared secrets manager. If false, use the user secrets manager')


def _GetSecretsManager():
  if options.options.shared:
    return secrets.GetSharedSecretsManager()
  else:
    return secrets.GetUserSecretsManager()


def _ListSecrets(io_loop):
  """Lists all secrets."""
  for f in _GetSecretsManager().ListSecrets():
    print '  %s' % f
  io_loop.stop()


def _GetSecret(io_loop, secret):
  """Get a secret by name and output to stdout."""
  print '%s:\n%s' % (secret, _GetSecretsManager().GetSecret(secret))
  io_loop.stop()


def _PutSecret(io_loop, secret):
  """Reads the new secret from stdin and writes to secrets subdir."""
  _GetSecretsManager().PutSecret(secret, sys.stdin.read())
  io_loop.stop()


def _PutCryptKeyset(io_loop, secret):
  """Creates a new Keyczar crypt keyset used for encryption and decryption
  and writes it to secrets subdir."""
  _GetSecretsManager().PutSecret(secret, json.dumps(secrets.CreateCryptKeyset(secret)))
  io_loop.stop()


def _PutSigningKeyset(io_loop, secret):
  """Creates a new Keyczar crypt keyset used for signing and signature
  verification and writes it to secrets subdir."""
  _GetSecretsManager().PutSecret(secret, json.dumps(secrets.CreateSigningKeyset(secret)))
  io_loop.stop()


def _EncryptSecrets(io_loop):
  """Lists all secrets files and encrypts each in turn. The passphrase
  for encryption is solicited twice for confirmation.
  """
  print 'Initializing existing secrets manager...'
  ex_sm = _GetSecretsManager()

  print 'Initializing new secrets manager...'
  if options.options.shared:
    new_sm = secrets.SecretsManager('shared', options.options.domain, options.options.secrets_dir)
  else:
    new_sm = secrets.SecretsManager('user', options.options.domain, options.options.user_secrets_dir)
  new_sm.Init(should_prompt=True, query_twice=True)

  print 'Encrypting secrets...'
  for secret in ex_sm.ListSecrets():
    print '  %s' % secret
    new_sm.PutSecret(secret, ex_sm.GetSecret(secret))
  io_loop.stop()


def main():
  """Parses command line options and, if directed, executes some operation
  to transform or create secrets from the command line.
  """
  io_loop = ioloop.IOLoop.current()
  options.parse_command_line()

  def _OnException(type, value, traceback):
    logging.error('failed %s' % options.options.secrets_mode, exc_info=(type, value, traceback))
    io_loop.stop()
    sys.exit(1)

  with util.ExceptionBarrier(_OnException):
    if options.options.secrets_mode == 'list_secrets':
      _ListSecrets(io_loop)
    elif options.options.secrets_mode == 'get_secret':
      _GetSecret(io_loop, options.options.secret)
    elif options.options.secrets_mode == 'put_secret':
      _PutSecret(io_loop, options.options.secret)
    elif options.options.secrets_mode == 'put_crypt_keyset':
      _PutCryptKeyset(io_loop, options.options.secret)
    elif options.options.secrets_mode == 'put_signing_keyset':
      _PutSigningKeyset(io_loop, options.options.secret)
    elif options.options.secrets_mode == 'encrypt_secrets':
      _EncryptSecrets(io_loop)
    else:
      raise Exception('unknown secrets_mode: %s' % options.options.secrets_mode)

  io_loop.start()

if __name__ == '__main__':
  sys.exit(main())
