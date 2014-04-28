# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Object store high level utilities.

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import cStringIO
import gzip
import logging
import subprocess
import sys
import traceback

from functools import partial
from tornado import gen, options
from viewfinder.backend.base import main
from viewfinder.backend.db import db_client
from viewfinder.backend.storage.object_store import ObjectStore

def ListBuckets():
  """Return the list of bucket names initialized in the object store."""
  return ObjectStore.ListInstances()


def IsBucket(name):
  """Returns true if there is a bucket under this name in the object store."""
  return ObjectStore.HasInstance(name)


def ParseFullPath(full_path):
  """Parse a full path and return a (bucket, relative_path). If the bucket is not registered, return None."""
  bucket, _, path = full_path.partition('/')
  if not bucket or not IsBucket(bucket):
    return None
  else:
    return (bucket, path)


def PrefixFromPattern(pattern):
  """Given a path pattern, return the prefix to use in ListKeys.
  If a pattern ends with '*', the prefix is the pattern without the '*', otherwise, we format is as a directory.
  """
  if pattern.endswith('*'):
    return pattern[:-1]
  elif pattern.endswith('/'):
    return '' if pattern == '/' else pattern
  elif pattern == '':
    return pattern
  else:
    return pattern + '/'


@gen.engine
def FileExists(store, filename, callback):
  """Returns true if a given S3 key exists."""
  ret = yield gen.Task(store.ListKeys, prefix=filename, maxkeys=1)
  logging.info('File: %s -> ret: %r' % (filename, ret))
  callback(len(ret) > 0 and ret[0] == filename)


@gen.engine
def ListAllKeys(store, callback, prefix=None, marker=None, batch_size=1000):
  """List all keys (repeatedly call ListKeys)."""
  # maxkeys=1000 is the S3 ListKeys limit.
  batch_size = min(1000, batch_size)
  keys = []
  done = False
  while not done:
    new_keys = yield gen.Task(store.ListKeys, prefix=prefix, marker=marker, maxkeys=batch_size)
    keys.extend(new_keys)
    if len(new_keys) < batch_size:
      break
    marker = new_keys[-1]

  callback(keys)


@gen.engine
def ListAllCommonPrefixes(store, delimiter, callback, prefix=None, marker=None):
  """List all common prefixes (repeatedly call ListCommonPrefixes)."""
  prefixes = set()
  keys = []

  while True:
    # maxkeys=1000 is the S3 ListKeys limit.
    new_prefixes, new_keys = yield gen.Task(store.ListCommonPrefixes, delimiter, prefix=prefix,
                                            marker=marker, maxkeys=1000)
    prefixes = prefixes.union(set(new_prefixes))
    keys.extend(new_keys)
    if (len(new_prefixes) + len(new_keys)) < 1000:
      break
    # maxkeys includes both prefixes and items. The marker for the next lookup is the lexicographically greatest
    # key we've received (either a prefix or an item).
    marker = ''
    if len(new_prefixes) > 0:
      marker = max(marker, new_prefixes[-1])
    if len(new_keys) > 0:
      marker = max(marker, new_keys[-1])
  callback((sorted(list(prefixes)), keys))


@gen.engine
def ListFilesAndDirs(store, pattern, callback):
  """List all subdirectories and files in a directory. Not recursive. Returns (subdirs, files)."""
  result = yield gen.Task(ListAllCommonPrefixes, store, '/', prefix=PrefixFromPattern(pattern))
  callback(result)


@gen.engine
def ListRecursively(store, pattern, callback):
  """Recursively list all files matching 'pattern'. This does not return directories."""
  results = yield gen.Task(ListAllKeys, store, prefix=PrefixFromPattern(pattern))
  callback(results)


@gen.engine
def GetFileContents(store, path, callback, auto_gunzip=True):
  """Get the contents of a file in S3. If the extension is .gz, gunzip it first."""
  buf = yield gen.Task(store.Get, path)
  if auto_gunzip and path.endswith('.gz'):
    iobuffer = cStringIO.StringIO(buf)
    gzipIO = gzip.GzipFile('rb', fileobj=iobuffer)
    contents = gzipIO.read()
    iobuffer.close()
  else:
    contents = buf

  callback(contents)
