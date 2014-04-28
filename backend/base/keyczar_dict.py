#!/usr/bin/env python
#
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Provides an implementation of a Keyczar keyset reader and writer
that stores meta information and versioned keys in a Python dict. The
dict can then be stored in our database or in files in the secrets
directory. The attributes of the dict are as follows:
  meta - contains the keyset metadata as a string
  1 - contains the first key in the set (if it exists)
  2 - contains the second key in the set (if it exists)
  ...and so on
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import json

from keyczar import errors, readers, writers


class DictReader(readers.Reader):
  """Keyczar reader that reads key data from a Python dict."""
  def __init__(self, keydata):
    """Construct reader from either a JSON string or a Python dict."""
    if isinstance(keydata, basestring):
      keydata = json.loads(keydata)
    assert isinstance(keydata, dict), keydata
    self.dict = keydata

  def GetMetadata(self):
    """Returns the "meta" attribute."""
    return self.dict['meta']

  def GetKey(self, version_number):
    """Returns a key having "version_number" as its name."""
    return self.dict[str(version_number)]

  def Close(self):
    """Does nothing, as there is nothing to close."""
    pass


class DictWriter(writers.Writer):
  """Keyczar writer that writes key data to a Python dict."""
  def __init__(self, keydata=None):
    """Construct reader from either a JSON string or a Python dict."""
    if isinstance(keydata, basestring):
      keydata = json.loads(keydata)
    assert keydata is None or isinstance(keydata, dict), keydata
    self.dict = keydata if keydata is not None else {}

  def WriteMetadata(self, metadata, overwrite=True):
    """Stores "metadata" in the "meta" attribute."""
    if not overwrite and 'meta' in metadata:
      raise errors.KeyczarError('"meta" attribute already exists')
    self.dict['meta'] = str(metadata)

  def WriteKey(self, key, version_number, encrypter=None):
    """Stores "key" in an attribute having "version_number" as its name."""
    key = str(key)
    if encrypter:
      key = encrypter.Encrypt(key)  # encrypt key info before outputting
    self.dict[str(version_number)] = key

  def Remove(self, version_number):
    """Removes the key for the given version."""
    self.dict.pop(str(version_number))

  def Close(self):
    """Does nothing, as there is nothing to close."""
    pass
