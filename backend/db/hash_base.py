# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Base object for database objects from tables with a simple hash key.

Sub classes must implement GetKey, _GetIndexKey, and _ParseIndexKey.
See the comments below for a description of each method.

  DBHashObject: base class of all hash-key data objects
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging

from tornado.concurrent import return_future

from viewfinder.backend.base import util
from viewfinder.backend.db import db_client, schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.versions import Version


class DBHashObject(DBObject):
  """Base class for items from tables with a hash key.
  """
  __slots__ = []

  def __init__(self, columns=None):
    super(DBHashObject, self).__init__(columns=columns)

  @classmethod
  @return_future
  def Query(cls, client, hash_key, col_names, callback,
            must_exist=True, consistent_read=False):
    """Queries a object by primary hash key."""
    cls.KeyQuery(client, key=db_client.DBKey(hash_key=hash_key, range_key=None),
                 col_names=col_names, callback=callback, must_exist=must_exist,
                 consistent_read=consistent_read)

  @classmethod
  def Allocate(cls, client, callback):
    """Allocates a new primary key via the id_allocator table. Invokes
    the provided callback with new object.
    """
    assert cls._allocator, 'class has no id allocator declared'
    def _OnAllocate(obj_id):
      o = cls(obj_id)
      o._columns[schema.Table.VERSION_COLUMN.name].Set(Version.GetCurrentVersion())
      callback(o)
    cls._allocator.NextId(client, _OnAllocate)

  def GetKey(self):
    """Returns the object's primary hash key."""
    return db_client.DBKey(hash_key=self._columns[self._table.hash_key_col.name].Get(),
      range_key=None)

  @classmethod
  def _MakeIndexKey(cls, db_key):
    """Creates an indexing key from the provided object key. This is
    symmetric with _ParseIndexKey. All index keys are stored as strings,
    so we get a string representation here in case the hash key column
    is a number.
    """
    val = db_key.hash_key
    if cls._table.hash_key_col.value_type == 'N':
      assert isinstance(val, (int, long)), 'primary hash key not of type int or long'
      val = str(val)
    return val

  @classmethod
  def _ParseIndexKey(cls, index_key):
    """Returns the object's key by parsing the index key. This is
    symmetric with _MakeIndexKey, and is used to extract the actual
    object key from results of index queries. By default, returns the
    unadulterated index_key.

    Because all keys are stored in the index table as strings, if the
    hash key column type is a number, convert here from a string to a
    number.
    """
    if cls._table.hash_key_col.value_type == 'N':
      index_key = int(index_key)
    return db_client.DBKey(hash_key=index_key, range_key=None)

  @classmethod
  def _GetIndexedObjectClass(cls):
    return cls
