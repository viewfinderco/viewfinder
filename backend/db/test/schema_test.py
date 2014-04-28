# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Schema tests.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import json
import unittest

from contextlib import contextmanager
from keyczar import errors, keyczar, keyinfo
from tornado import options
from viewfinder.backend.base import base_options  # imported for option definitions
from viewfinder.backend.base import keyczar_dict, secrets
from viewfinder.backend.db.schema import Column, CryptColumn, _CryptValue
from viewfinder.backend.db.indexers import Indexer, SecondaryIndexer, FullTextIndexer

class IndexerTestCase(unittest.TestCase):
  def setUp(self):
    self.col = Column('test', 'te', str)

  def testOptions(self):
    """Test the optional indexer expansion settings."""
    value = 'one two three'
    pos_single = [[0], [1], [2]]
    pos_mphone = [[0], [1], [2], [2]]
    self._VerifyIndex(FullTextIndexer(metaphone=Indexer.Option.NO), value,
                      ['te:one', 'te:two', 'te:three'], pos_single)
    self._VerifyIndex(FullTextIndexer(metaphone=Indexer.Option.YES), value,
                      ['te:one', 'te:two', 'te:three', 'te:AN', 'te:T', 'te:0R', 'te:TR'],
                      pos_single + pos_mphone)
    self._VerifyIndex(FullTextIndexer(metaphone=Indexer.Option.ONLY), value,
                      ['te:AN', 'te:T', 'te:0R', 'te:TR'], pos_mphone)
    self._VerifyIndex(FullTextIndexer(metaphone=Indexer.Option.YES), 'food foot',
                      ['te:food', 'te:foot', 'te:FT'], [[0], [1], [0, 1]])

  def testFullTextIndexer(self):
    """Verifies operation of the full-text indexer, including stop words,
    punctuation separation and position lists.
    """
    tok = FullTextIndexer()
    self._VerifyIndex(tok, 'one two three', ['te:one', 'te:two', 'te:three'], [[0], [1], [2]])
    self._VerifyIndex(tok, 'one-two.three', ['te:one', 'te:two', 'te:three'], [[0], [1], [2]])
    self._VerifyIndex(tok, 'one_two=three', ['te:one', 'te:two', 'te:three'], [[0], [1], [2]])
    self._VerifyIndex(tok, 'one t three', ['te:one', 'te:three'], [[0], [2]])
    self._VerifyIndex(tok, 'one one three', ['te:one', 'te:three'], [[0, 1], [2]])
    self._VerifyIndex(tok, "my, ain't it grand to have her to myself?", ["te:ain't", 'te:grand'], [[1], [3]])

  def testQueryString(self):
    """Verifies query string generation."""
    indexer = SecondaryIndexer()
    self.assertEqual(indexer.GetQueryString(self.col, 'foo'), '"te:foo"')
    tok = FullTextIndexer()
    self.assertEqual(tok.GetQueryString(self.col, 'foo'), 'te:foo')
    self.assertEqual(tok.GetQueryString(self.col, 'foo bar'), '(te:foo + te:bar)')
    self.assertEqual(tok.GetQueryString(self.col, 'is foo = bar?'), '(_ + te:foo + te:bar)')
    self.assertEqual(tok.GetQueryString(self.col, 'is foo equal to bar or is it not equal?'),
                     '(_ + te:foo + te:equal + _ + te:bar + _ + _ + _ + _ + te:equal)')
    tok = FullTextIndexer(metaphone=Indexer.Option.YES)
    self.assertEqual(tok.GetQueryString(self.col, 'foo'), '(te:foo | te:F)')
    self.assertEqual(tok.GetQueryString(self.col, 'one or two or three'),
                     '((te:AN | te:one) + _ + (te:T | te:two) + _ + (te:TR | te:three | te:0R))')

  # Disable this test as it takes longer than is useful.
  def TestLongPosition(self):
    """Verifies position works up to 2^16 words and then is ignored after.
    """
    tok = FullTextIndexer()
    value = 'test ' * (1 << 16 + 1) + 'test2'
    positions = [range(1 << 16), []]
    self._VerifyIndex(tok, value, ['te:test', 'te:test2'], positions)

  def testSecondaryIndexer(self):
    """Test secondary indexer emits column values."""
    indexer = SecondaryIndexer()
    self._VerifyIndex(indexer, 'foo', ['te:foo'], None)
    self._VerifyIndex(indexer, 'bar', ['te:bar'], None)
    self._VerifyIndex(indexer, 'baz', ['te:baz'], None)

  def _VerifyIndex(self, tok, value, terms, freight=None):
    term_dict = tok.Index(self.col, value)
    self.assertEqual(set(terms), set(term_dict.keys()))
    if freight:
      assert len(terms) == len(freight)
      for term, data in zip(terms, freight):
        self.assertEqual(data, tok.UnpackFreight(self.col, term_dict[term]))
    else:
      for term in terms:
        self.assertFalse(term_dict[term])


class ColumnTestCase(unittest.TestCase):
  def setUp(self):
    options.options.domain = 'goviewfinder.com'
    secrets.InitSecretsForTest()
    self._crypt_inst = CryptColumn('foo', 'f').NewInstance()

  def testCryptColumn(self):
    """Unit test the CryptColumn object."""
    def _Roundtrip(value):
      # Set the value.
      self._crypt_inst.Set(value)
      self.assertTrue(value is None or self._crypt_inst.IsModified())

      # Get the value as a _DelayedCrypt instance.
      delayed_value = self._crypt_inst.Get()
      if value is None:
        self.assertIsNone(delayed_value)
      else:
        self.assertEqual(delayed_value, delayed_value)
        self.assertNotEqual(delayed_value, None)
        self.assertEqual(value, delayed_value.Decrypt())

      # Get the value as a JSON-serializable dict.
      value2 = self._crypt_inst.Get(asdict=True)
      if value is None:
        self.assertIsNone(value2)
      else:
        self.assertEqual(value2, {'__crypt__': delayed_value._encrypted_value})

      # Set the value as a __crypt__ dict.
      self._crypt_inst.SetModified(False)
      self._crypt_inst.Set(value2)
      self.assertFalse(self._crypt_inst.IsModified())

    _Roundtrip(None)
    _Roundtrip(1.23)
    _Roundtrip('')
    _Roundtrip('some value')
    _Roundtrip('some value')
    _Roundtrip(' \t\n\0#:&*01fjsbos\x100\x1234\x12345678 {')
    _Roundtrip([])
    _Roundtrip([1, 2, -1, 0])
    _Roundtrip({'foo': 'str', 'bar': 1.23, 'baz': [1, 2], 'bat': {}})

  def testDbKeyRotation(self):
    """Verify that db_crypt key can be rotated."""
    @contextmanager
    def _OverrideSecret(secret, secret_value):
      try:
        old_secret_value = secrets.GetSharedSecretsManager()._secrets[secret]
        secrets.GetSharedSecretsManager()._secrets[secret] = secret_value
        # Clear the cached crypter.
        if hasattr(_CryptValue, '_crypter'):
          del _CryptValue._crypter
        yield
      finally:
        secrets.GetSharedSecretsManager()._secrets[secret] = old_secret_value
        if hasattr(_CryptValue, '_crypter'):
          del _CryptValue._crypter

    # Encrypt a value using the original key.
    plaintext = 'quick brown fox'
    self._crypt_inst.Set(plaintext)

    # Add a new key to the keyset and make it primary and ensure that plaintext can still be recovered.
    writer = keyczar_dict.DictWriter(secrets.GetSharedSecretsManager()._secrets['db_crypt'])
    czar = keyczar.GenericKeyczar(keyczar_dict.DictReader(writer.dict))
    czar.AddVersion(keyinfo.PRIMARY)
    czar.Write(writer)

    with _OverrideSecret('db_crypt', json.dumps(writer.dict)):
      self.assertEqual(self._crypt_inst.Get().Decrypt(), plaintext)

    # Now remove old key and verify that plaintext cannot be recovered.
    czar.Demote(1)
    czar.Revoke(1)
    czar.Write(writer)
    with _OverrideSecret('db_crypt', json.dumps(writer.dict)):
      self.assertRaises(errors.KeyNotFoundError, self._crypt_inst.Get().Decrypt)
