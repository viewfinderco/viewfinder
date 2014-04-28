# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Secrets test.

  Test secrets module. user vs shared, encrypted vs plain.
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import getpass
import json
import logging
import mock
import os
import shutil
import tempfile
import unittest

from tornado import options
from viewfinder.backend.base import ami_metadata, base_options, secrets, testing
from viewfinder.backend.base.exceptions import CannotReadEncryptedSecretError

class SecretsTestCase(unittest.TestCase):
  def setUp(self):
    # Fake out the keyring to None for the entire test.
    self._prev_keyring = secrets.keyring
    secrets.keyring = None

    self._domain = options.options.domain
    self._prev_user_dir = options.options.user_secrets_dir
    self._prev_shared_dir = options.options.secrets_dir
    self._prev_devbox = options.options.devbox

    # Create tmp directories and set flag values.
    self._user_dir = tempfile.mkdtemp()
    options.options.user_secrets_dir = self._user_dir
    os.mkdir(os.path.join(self._user_dir, self._domain))

    self._shared_dir = tempfile.mkdtemp()
    options.options.secrets_dir = self._shared_dir
    os.mkdir(os.path.join(self._shared_dir, self._domain))


  def tearDown(self):
    # Recursively delete temp directories and restore flag values.
    shutil.rmtree(self._user_dir)
    shutil.rmtree(self._shared_dir)

    options.options.user_secrets_dir = self._prev_user_dir
    options.options.secrets_dir = self._prev_shared_dir
    options.options.devbox = self._prev_devbox

    secrets.keyring = self._prev_keyring
    secrets._user_secrets_manager = None
    secrets._shared_secrets_manager = None

  def testNoDomainDir(self):
    """Test secrets manager without a domain dir."""
    mgr = secrets.SecretsManager('test', 'fake_domain', self._shared_dir)
    # We do not fail on Init since we want to be able to support non-existent user secrets.
    mgr.Init()

    # Behaves just like an empty secrets manager.
    self.assertEqual(len(mgr.ListSecrets()), 0)

    # Trying to add a secret fails.
    self.assertRaises(IOError, mgr.PutSecret, 'foo', 'codeforfoo')


  def testPlain(self):
    """Test secrets manager with plain-text secrets."""
    mgr = secrets.SecretsManager('test', self._domain, self._shared_dir)
    # Empty directory, Init will not require a passphrase.
    mgr.Init()

    self.assertEqual(len(mgr.ListSecrets()), 0)
    self.assertRaises(KeyError, mgr.GetSecret, 'foo')
    self.assertFalse(mgr.HasSecret('foo'))

    # Put a secret, but underlying directory doesn't exist (switch domains first).
    mgr.PutSecret('foo', 'codeforfoo')
    self.assertTrue(mgr.HasSecret('foo'))
    self.assertEqual(mgr.GetSecret('foo'), 'codeforfoo')
    self.assertEqual(len(mgr.ListSecrets()), 1)

    # Now check that the underlying file exists.
    with open(os.path.join(self._shared_dir, self._domain, 'foo')) as f:
      self.assertEqual(f.read(), 'codeforfoo')

    # Overwrite secret.
    mgr.PutSecret('foo', 'newcodeforfoo')
    self.assertEqual(mgr.GetSecret('foo'), 'newcodeforfoo')
    self.assertEqual(len(mgr.ListSecrets()), 1)

    # Now check that the underlying file exists.
    with open(os.path.join(self._shared_dir, self._domain, 'foo')) as f:
      self.assertEqual(f.read(), 'newcodeforfoo')

    # Create a new secrets manager.
    mgr = secrets.SecretsManager('test', self._domain, self._shared_dir)
    mgr.Init()
    self.assertTrue(mgr.HasSecret('foo'))
    self.assertEqual(mgr.GetSecret('foo'), 'newcodeforfoo')
    self.assertEqual(len(mgr.ListSecrets()), 1)

    # Passing a passphrase as a flag does not impact plain-text secrets.
    options.options.passphrase = 'not a passphrase'
    mgr = secrets.SecretsManager('test', self._domain, self._shared_dir)
    mgr.Init()
    self.assertEqual(mgr.GetSecret('foo'), 'newcodeforfoo')


  def testEncrypted(self):
    """Test secrets manager with encrypted secrets."""

    # The only way to make a secret manager encrypt when empty is to ask it
    # to prompt for a passphrase. It does so using getpass.getpass.
    passphrase = 'my voice is my passport!'
    with mock.patch.object(secrets.getpass, 'getpass') as getpass:
      getpass.return_value = passphrase
      mgr = secrets.SecretsManager('test', self._domain, self._shared_dir)
      mgr.Init(should_prompt=True)

    # Secret will be encrypted.
    mgr.PutSecret('foo', 'codeforfoo')
    self.assertEqual(mgr.GetSecret('foo'), 'codeforfoo')
    with open(os.path.join(self._shared_dir, self._domain, 'foo')) as f:
      contents = f.read()
      self.assertNotEqual(contents, 'codeforfoo')
      (cipher, ciphertext) = json.loads(contents)
      self.assertEqual(cipher, 'AES')
      # TODO(marc): maybe we should test the encryption itself.

    # Now create a new secrets manager. We do not ask it to prompt, it will figure it out
    # all by itself. It does this in a number of ways:


    ##################### --devbox=False ########################
    options.options.devbox = False

    # Set stdin to raise an exception, just to make sure we're not using it.
    with mock.patch.object(secrets.getpass, 'getpass') as getpass:
      getpass.side_effect = Exception('you should not be using stdin in --devbox=False mode')
      # Uses --passphrase if specified.
      options.options.passphrase = passphrase
      mgr = secrets.SecretsManager('test', self._domain, self._shared_dir)
      mgr.Init()
      self.assertEqual(mgr.GetSecret('foo'), 'codeforfoo')

      # We get an assertion error when a passphrase is supplied but bad. This is because it fails on sha sum.
      options.options.passphrase = 'bad passphrase'
      mgr = secrets.SecretsManager('test', self._domain, self._shared_dir)
      self.assertRaises(AssertionError, mgr.Init)
    
      # Uses AMI metadata otherwise.
      options.options.passphrase = None
      # No AMI fetched, or passphrase not one of the fetched fields.
      mgr = secrets.SecretsManager('test', self._domain, self._shared_dir)
      self.assertRaisesRegexp(CannotReadEncryptedSecretError, 'failed to fetch passphrase from AWS instance metadata',
                              mgr.Init)
    
      # Good passphrase from AMI metadata.
      ami_metadata.SetAMIMetadata({'user-data/passphrase': passphrase})
      mgr = secrets.SecretsManager('test', self._domain, self._shared_dir)
      mgr.Init()
      self.assertEqual(mgr.GetSecret('foo'), 'codeforfoo')
    
      # Bad passphrase from AMI metadata.
      ami_metadata.SetAMIMetadata({'user-data/passphrase': 'not a good passphrase.'})
      mgr = secrets.SecretsManager('test', self._domain, self._shared_dir)
      self.assertRaises(AssertionError, mgr.Init)


    ##################### --devbox=True ########################
    options.options.devbox = True
    # Set bad AMI metadata just to show that we never use it.
    ami_metadata.SetAMIMetadata({'user-data/passphrase': 'not a good passphrase.'})

    # Uses --passphrase if specified.
    options.options.passphrase = passphrase
    mgr = secrets.SecretsManager('test', self._domain, self._shared_dir)
    mgr.Init()
    self.assertEqual(mgr.GetSecret('foo'), 'codeforfoo')

    # If --passphrase is None and we cannot prompt, we have no way of getting the passphrase.
    options.options.passphrase = None
    mgr = secrets.SecretsManager('test', self._domain, self._shared_dir)
    self.assertRaisesRegexp(CannotReadEncryptedSecretError, 'passphrase is required but was not provided',
                            mgr.Init, can_prompt=False)

    # Passphrase is read from stdin if prompting is allowed.
    with mock.patch.object(secrets.getpass, 'getpass') as getpass:
      getpass.return_value = passphrase
      mgr = secrets.SecretsManager('test', self._domain, self._shared_dir)
      mgr.Init()
      self.assertEqual(mgr.GetSecret('foo'), 'codeforfoo')

    # Pass a bad passphrase on stdin.
    with mock.patch.object(secrets.getpass, 'getpass') as getpass:
      getpass.return_value = 'not a good passphrase'
      mgr = secrets.SecretsManager('test', self._domain, self._shared_dir)
      self.assertRaises(AssertionError, mgr.Init)


  def testMultipleManagers(self):
    """Test the secrets managers in their natural habitat: automatic selection of user vs shared based on flags."""
    # these may not be None if we've been running other tests using run-tests.
    secrets._user_secrets_manager = None
    secrets._shared_secrets_manager = None

    # Devbox mode: init user secrets, and lazily init shared secrets is requesting a secret on in user secrets.
    options.options.devbox = True
    secrets.InitSecrets()
    self.assertIsNotNone(secrets._user_secrets_manager)
    self.assertIsNone(secrets._shared_secrets_manager)

    # Request a secret contained in user secrets: shared secrets remain uninitialized.
    secrets._user_secrets_manager.PutSecret('foo', 'codeforfoo')
    self.assertEqual(secrets.GetSecret('foo'), 'codeforfoo')
    self.assertIsNotNone(secrets._user_secrets_manager)
    self.assertIsNone(secrets._shared_secrets_manager)

    # Request a secret not contained anywhere. As soon as we notice that it's not in user secrets, we initialize
    # the shared secrets and look there, which fails.
    self.assertRaises(KeyError, secrets.GetSecret, 'bar')
    self.assertIsNotNone(secrets._user_secrets_manager)
    self.assertIsNotNone(secrets._shared_secrets_manager)

    # Non-devbox mode: user secrets are never used. shared secrets are initialized right away.
    options.options.devbox = False
    secrets._user_secrets_manager = None
    secrets._shared_secrets_manager = None

    secrets.InitSecrets()
    self.assertIsNone(secrets._user_secrets_manager)
    self.assertIsNotNone(secrets._shared_secrets_manager)

    # Lookup whatever we want, we still won't use the user secrets.:w
    secrets._shared_secrets_manager.PutSecret('foo', 'codeforfoo')
    self.assertEqual(secrets.GetSecret('foo'), 'codeforfoo')
    self.assertRaises(KeyError, secrets.GetSecret, 'bar')
    self.assertIsNone(secrets._user_secrets_manager)
    self.assertIsNotNone(secrets._shared_secrets_manager)
