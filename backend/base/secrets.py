#!/usr/bin/env python
#
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Provides a central mechanism for accessing secrets, such
as private keys, cookie secrets, and authentication service
secrets.

A particular secret is stored in a file in the --secrets_dir
directory. The secret is accessed using the name of the file.

Secrets may be encrypted (determined at Init time). If so, the
secrets manager will attempt to get the passphrase, either
by looking it up from AMI (if running with --devbox=False), or
getting it from the user.

If secrets are not encrypted, they may be read and written without
invoking InitSecrets. If they are encrypted, but InitSecrets is not
invoked, then the fetched contents will be the still-encrypted secret.

There are two secrets managers. One for shared secrets stored in the
repository and encrypted with the master viewfinder passphrase, the
other for user secrets, stored in ~/.secrets/.

User secrets are only loaded if --devbox is True. In that case, the
shared secrets manager is loaded lazily if needed (a secret is requested
that does not exist in the user secrets manager).

With --devbox=False (on AWS), the user secrets manager is never used
and the shared secrets manager is initialized right away.
In such a case, AMI metadata must have been successfully fetched before
calling InitSecrets. 'user-data/passphrase' must be in the fetched metadata.

  InitSecrets(): looks up (in AMI metadata) or prompts for pass phrase.
  GetSecret(): returns the data of a named secret.
  PutSecret(): writes a new secret the the secrets dir.
  ListSecrets(): returns a list of available secrets.
  GetCrypter(): get Keyczar Crypter using a named secret.
  GetSigner(): get Keyczar Signer using a named secret.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import atexit
import base64
import getpass
import json
import logging
import os
import stat
import sys
import tempfile

from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from keyczar import keyczar, keydata, keyinfo
from tornado import options
from tornado.platform.auto import set_close_exec
from viewfinder.backend.base import ami_metadata, keyczar_dict, base_options
from viewfinder.backend.base.exceptions import CannotReadEncryptedSecretError
from viewfinder.backend.base import base_options  # imported for option definitions

try:
  import keyring
except ImportError:
  keyring = None

_tempfile_map = dict()
"""Temporary files for modules which require a file for certificate or key data."""

# Secrets manager for user keys (domain=viewfinder.co only)
_user_secrets_manager = None
# Secrets manager for shared keys
_shared_secrets_manager = None


class SecretsManager(object):
  """Manages secrets subdirectory."""
  # SHA256 Digest size in bytes.
  DIGEST_BYTES = 256 / 8

  # The block size for the cipher object; must be 16, 24, or 32 for AES.
  BLOCK_SIZE = 32

  # The character used for padding--with a block cipher such as AES,
  # the value you encrypt must be a multiple of BLOCK_SIZE in
  # length. This character is used to ensure that your value is always
  # a multiple of BLOCK_SIZE.
  PADDING = '{'

  def __init__(self, name, domain, secrets_dir):
    """Configures the secrets module to get and write secrets to a
    subdirectory of --secrets_dir corresponding to 'domain'.
    """
    self._secrets = dict()
    self._name = name
    self.__secrets_subdir = os.path.join(secrets_dir, domain)
    self.__passphrase = None

  def Init(self, can_prompt=True, should_prompt=False, query_twice=False):
    """If 'encrypted' is True, a passphrase must be determined. The AMI
    user-data is queried first for the secrets pass phrase. If
    unavailable, the user is prompted via the console for the
    pass-phrase before continuing. If 'encrypted' is True, 'query_twice'
    determines whether to ask the user twice for the passphrase for
    confirmation. This is done when encrypting files so there is less
    chance of a user error causing the file contents to be unretrievable.
    """
    passphrase_key = 'user-data/passphrase'


    def _GetPassphraseFromKeyring():
      """Retrieve the passphrase from keyring. Prompts whether to store it if not found.
      If a passphrase was retrieved or stored, save to self.__passphrase and return True.
      Passphrase is stored in keyring as ('vf-passphrase', os.getlogin()).
      """
      # TODO(marc): store passphrase as a keyczar dict.

      if keyring is None:
        print "No keyring found"
        return False

      user = os.getlogin()
      try:
        passphrase = keyring.get_password('%s-vf-passphrase' % self._name, user)
      except Exception:
        logging.warning("Failed to get %s passphrase from keyring" % self._name)
        passphrase = None

      if passphrase is not None:
        logging.info("Using %s passphrase from system keyring." % self._name)
        self.__passphrase = passphrase
        return True
      return False


    def _MaybeStorePassphraseInKeyring():
      if keyring is None:
        return

      assert self.__passphrase
      answer = raw_input("Store %s passphrase in system keyring? [y/N] " % self._name).strip()
      user = os.getlogin()
      if answer == "y":
        try:
          keyring.set_password('%s-vf-passphrase' % self._name, user, self.__passphrase)
        except Exception:
          logging.warning("Failed to store %s passphrase in keyring" % self._name)


    def _PromptPassphrase():
      if not can_prompt:
        raise CannotReadEncryptedSecretError('passphrase is required but was not provided')

      if _GetPassphraseFromKeyring():
        self._ReadSecrets()
      else:
        # We did not fetch the passphrase from the keyring, ask for it and maybe store it in the keyring.
        if query_twice:
          print 'Enter %s passphrase twice for confirmation' % self._name
          pp1 = getpass.getpass('passphrase: ')
          pp2 = getpass.getpass('passphrase: ')
          assert pp1 == pp2, 'passphrases don\'t match'
          self.__passphrase = pp1
        else:
          self.__passphrase = getpass.getpass('%s passphrase: ' % self._name)

        # Make sure the passphrase is correct before trying to store it in the keyring.
        self._ReadSecrets()
        _MaybeStorePassphraseInKeyring()


    def _GetPassphrase():
      if options.options.passphrase:
        # Passphrase passed as command-line option.
        self.__passphrase = options.options.passphrase
        self._ReadSecrets()
      elif options.options.passphrase_file:
        # Passphrase contained in a file
        filename = os.path.expanduser(os.path.expandvars(options.options.passphrase_file))
        self.__passphrase = open(filename, 'r').read().strip()
        self._ReadSecrets()
      elif not options.options.devbox:
        # Passphrase is available in AMI metadata.
        metadata = ami_metadata.GetAMIMetadata()
        if passphrase_key not in metadata:
          raise CannotReadEncryptedSecretError('failed to fetch passphrase from AWS instance metadata; '
                                               'if running on dev box, use the --devbox option')
        self.__passphrase = metadata[passphrase_key]
        self._ReadSecrets()
      else:
        # Prompt for passphrase at command-line.
        _PromptPassphrase()

    if should_prompt:
      # should_prompt is true, so prompt for the passphrase even if we already have it.
      assert can_prompt, 'if should_prompt is true, then can_prompt must also be true'
      _PromptPassphrase()

    # Try to read the secrets with no passphrase. This will work if the secrets are not
    # encrypted (e.g. test secrets).
    try:
      self._ReadSecrets()
      # Read succeeded, so initialization is complete.
    except CannotReadEncryptedSecretError:
      # Must get passphrase from command-line, AMI metadata, or by prompting for it.
      _GetPassphrase()

  def InitForTest(self):
    """Reads the secrets with assumption they are not encrypted."""
    self._need_passphrase = False
    self._ReadSecrets()

  def ListSecrets(self):
    """Returns a list of available secrets."""
    return self._secrets.keys()

  def HasSecret(self, secret):
    """Returns true if the secret is in the secrets map."""
    return secret in self._secrets

  def GetSecret(self, secret):
    """Returns the secret from the secrets map."""
    return self._secrets[secret].strip()

  def PutSecret(self, secret, secret_value):
    """Writes the secrets file and possibly encrypts the value."""
    self._secrets[secret] = secret_value.strip()
    fn = self._GetSecretFile(secret, verify=False)
    with open(fn, 'w') as f:
      os.chmod(fn, stat.S_IRUSR | stat.S_IWUSR)
      if self.__passphrase:
        encrypted_secret = self._EncryptSecret(self._secrets[secret])
        f.write(json.dumps(encrypted_secret))
      else:
        f.write(self._secrets[secret])

  def GetCrypter(self, secret):
    """Assumes the secret is a Keyczar crypt keyset. Loads the secret
    value and returns a Keyczar Crypter object already initialized with
    the keyset value.
    """
    return keyczar.Crypter(keyczar_dict.DictReader(self.GetSecret(secret)))

  def GetSigner(self, secret):
    """Assumes the secret is a Keyczar signing keyset. Loads the secret
    value and returns a Keyczar Signer object already initialized with
    the keyset value.
    """
    return keyczar.Signer(keyczar_dict.DictReader(self.GetSecret(secret)))

  def _GetSecretFile(self, secret, verify=True):
    """Concatenates the secret name with the --secrets_dir command
    line flag.
    """
    path = os.path.join(self.__secrets_subdir, secret)
    if verify and not os.access(path, os.R_OK):
      raise IOError('unable to access {0}'.format(path))
    return path

  def _ReadSecret(self, secret):
    """Reads the secrets file and possibly decrypts it."""
    with open(self._GetSecretFile(secret), 'r') as f:
      contents = f.read()
      try:
        (cipher, ciphertext) = json.loads(contents)
        if cipher != 'AES':
          # Contents are not in our encryption format, so assume they're not encrypted.
          return contents
      except:
        # Contents are not in legal JSON format, so assume they're not encrypted.
        return contents

      return self._DecryptSecret(cipher, ciphertext)

  def _ReadSecrets(self):
    """Reads all secrets from the secrets subdir.
    """
    try:
      secrets = os.listdir(self.__secrets_subdir)
    except Exception:
      return
    for secret in secrets:
      self._secrets[secret] = self._ReadSecret(secret)

  def _DecryptSecret(self, cipher, ciphertext):
    """Decrypts the ciphertext secret, splits it into the first
    DIGEST_BYTES bytes (sha256 message digest), and verifies the digest
    matches the secret. Returns the plaintext secret on success.
    """
    if not self.__passphrase:
      raise CannotReadEncryptedSecretError('no passphrase initialized')
    assert cipher == 'AES', 'cipher %s not supported' % cipher
    aes_cipher = AES.new(self._PadText(self.__passphrase))
    plaintext = aes_cipher.decrypt(base64.b64decode(ciphertext)).rstrip(SecretsManager.PADDING)
    sha256_digest = plaintext[:SecretsManager.DIGEST_BYTES]
    plaintext_secret = plaintext[SecretsManager.DIGEST_BYTES:]
    sha256 = SHA256.new(plaintext_secret)
    assert sha256.digest() == sha256_digest, 'secret integrity compromised: sha256 hash does not match'
    return plaintext_secret

  def _EncryptSecret(self, plaintext_secret):
    """Computes a SHA256 message digest of the secret, prepends the
    digest, pads to a multiple of BLOCK_SIZE, encrypts using an AES
    cipher, and base64 encodes. Returns a tuple containing the cipher
    used and the base64-encoded, encrypted value.
    """
    aes_cipher = AES.new(self._PadText(self.__passphrase))
    sha256 = SHA256.new(plaintext_secret)
    assert len(sha256.digest()) == SecretsManager.DIGEST_BYTES, \
        'expected length of sha256 message digest not 256 bits'
    plaintext = self._PadText(sha256.digest() + plaintext_secret)
    ciphertext = base64.b64encode(aes_cipher.encrypt(plaintext))
    return ('AES', ciphertext)

  def _PadText(self, text):
    """Pads the provided text so that it is a multiple of BLOCK_SIZE.
    The padding character is specified by PADDING. Returns the padded
    version of 'text'.
    """
    if len(text) in (16, 24, 32):
      return text
    return text + (SecretsManager.BLOCK_SIZE -
                   len(text) % SecretsManager.BLOCK_SIZE) * SecretsManager.PADDING


def GetSharedSecretsManager(can_prompt=None):
  """Returns the shared secrets manager. Creates it from options if None.
  If can_prompt is None, determine automatically.
  """
  global _shared_secrets_manager
  if _shared_secrets_manager is None:
    _shared_secrets_manager = SecretsManager('shared', options.options.domain, options.options.secrets_dir)
    prompt = can_prompt if can_prompt is not None else sys.stderr.isatty()
    _shared_secrets_manager.Init(can_prompt=prompt)
  return _shared_secrets_manager


def GetUserSecretsManager(can_prompt=None):
  """Returns the user secrets manager. Creates it from options if None.
  If can_prompt is None, determine automatically.
  Fails in --devbox=False mode.
  """
  assert options.options.devbox, 'User secrets manager is only available in --devbox mode.'

  global _user_secrets_manager
  if _user_secrets_manager is None:
    # Create the user secrets manager.
    _user_secrets_manager = SecretsManager('user', options.options.domain, options.options.user_secrets_dir)
    prompt = can_prompt if can_prompt is not None else sys.stderr.isatty()
    _user_secrets_manager.Init(can_prompt=prompt)
  return _user_secrets_manager


def GetSecretsManagerForSecret(secret):
  """Returns the appropriate secrets manager for a secret.
  If we have a user secrets manager and it holds this secret, return it, otherwise use the shared secrets manager.
  The user secrets manager is always initialized (if needed).
  """
  global _user_secrets_manager
  if _user_secrets_manager is not None and _user_secrets_manager.HasSecret(secret):
    return _user_secrets_manager
  return GetSharedSecretsManager()


def InitSecrets(callback=None, shared_only=False, can_prompt=True):
  """Init secrets.
  If running with --devbox, initialize the user secrets manager only (the shared secrets manager will be initialized
  lazily if needed).
  If --devbox is False and shared_only=False, only initialize the shared secrets manager.
  shared_only=True should only be used when we know the secrets should NOT be stored in the user secrets (eg: OTP).
  """
  if options.options.devbox and not shared_only:
    GetUserSecretsManager()
  else:
    GetSharedSecretsManager()
  if callback is not None:
    callback()


def InitSecretsForTest():
  """Init secrets for test. We only use the shared secrets manager."""
  GetSharedSecretsManager(can_prompt=False)


def GetSecret(secret):
  """Fetched the named secret."""
  return GetSecretsManagerForSecret(secret).GetSecret(secret)

def GetSecretFile(secret):
  """Fetches the named secret into a temporary file for use with
  modules requiring the contents be accessible via a named file (e.g.
  Python SSL for keys and certificates).
  """
  if sys.platform.startswith('linux'):
    # Linux-specific implementation:  use an unnamed tempfile, which
    # will cease to exist when this process does.  Use /dev/fd to get
    # a name for the file.
    # Note that other platforms (including Mac) have /dev/fd as well,
    # but its semantics are different (all copies of a /dev/fd
    # file share one seek position, and that position is not reset on
    # open), so it's only safe to use on linux.
    if secret not in _tempfile_map:
      f = tempfile.TemporaryFile()
      set_close_exec(f.fileno())
      f.write(GetSecret(secret))
      f.flush()
      _tempfile_map[secret] = f

    return '/dev/fd/%d' % _tempfile_map[secret].fileno()
  else:
    # Default implementation: use a normal named tempfile, and delete
    # it when possible with atexit.
    if secret not in _tempfile_map:
      _, name = tempfile.mkstemp()
      with open(name, 'w') as f:
        f.write(GetSecret(secret))
      _tempfile_map[secret] = name
      atexit.register(os.remove, name)

    return _tempfile_map[secret]


def PutSecret(secret, secret_value):
  """Writes the specified secret value to a file in the secrets
  directory named `secret`.
  """
  GetSecretsManagerForSecret(secret).PutSecret(secret, secret_value)


def GetCrypter(secret):
  """Returns the Keyczar Crypter object returned by the secrets manager
  instance GetCrypter method."""
  return GetSecretsManagerForSecret(secret).GetCrypter(secret)


def GetSigner(secret):
  """Returns the Keyczar Signer object returned by the secrets manager
  instance GetSigner method."""
  return GetSecretsManagerForSecret(secret).GetSigner(secret)


def CreateCryptKeyset(name):
  """Returns a Keyczar keyset to be used for encryption and decryption.
  'name' is the name of the keyset. The keyset is returned as a Python
  dict in the format described in the keyczar_dict.py header.
  """
  return _CreateKeyset(name, keyinfo.DECRYPT_AND_ENCRYPT, keyinfo.AES)


def CreateSigningKeyset(name):
  """Returns a Keyczar keyset to be used for signing and signature
  verification. 'name' is the name of the keyset. The keyset is
  returned as a Python dict in the format described in the
  keyczar_dict.py header.
  """
  return _CreateKeyset(name, keyinfo.SIGN_AND_VERIFY, keyinfo.HMAC_SHA1)


def _CreateKeyset(name, purpose, key_type):
  """Constructs a Keyczar keyset, passing the specified arguments to the
  KeyMetadata constructor. Adds one primary key to the keyset and returns
  the keyset as a Python dict.
  """
  # Construct the metadata and add the first crypt key with primary status, meaning
  # it will be used to both encrypt/sign and decrypt/verify (rather than just
  # decrypt/verify).
  meta = keydata.KeyMetadata(name, purpose, key_type)
  writer = keyczar_dict.DictWriter()
  writer.WriteMetadata(meta)
  czar = keyczar.GenericKeyczar(keyczar_dict.DictReader(writer.dict))
  czar.AddVersion(keyinfo.PRIMARY)
  czar.Write(writer)
  return writer.dict
