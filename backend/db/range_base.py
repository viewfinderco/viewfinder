# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Base object for database objects from tables with a composite key
{hash-key, range-key}.

  DBRangeObject: superclass of all composite-key data objects
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

from functools import partial
from tornado import gen
from viewfinder.backend.base import util
from viewfinder.backend.db import db_client, schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.versions import Version

class DBRangeObject(DBObject):
  """Base class for items from tables built with a composite
  {hash-key, range-key} key.
  """
  __slots__ = []

  def __init__(self, columns=None):
    super(DBRangeObject, self).__init__(columns=columns)

  @classmethod
  def Query(cls, client, hash_key, range_key, col_names, callback,
            must_exist=True, consistent_read=False):
    """Queries a object by composite hash/range key."""
    cls.KeyQuery(client, key=db_client.DBKey(hash_key=hash_key, range_key=range_key),
                 col_names=col_names, callback=callback, must_exist=must_exist,
                 consistent_read=consistent_read)

  @classmethod
  def Allocate(cls, client, hash_key, callback):
    """Allocates a new range key via the id_allocator table.
    Instantiates a new object using provided 'hash_key' and the
    allocated 'range_key' and Invokes the provided callback with new ojb.
    """
    assert cls._allocator, 'class has no id allocator declared'
    def _OnAllocate(range_key):
      o = cls(hash_key, range_key)
      o._columns[schema.Table.VERSION_COLUMN.name].Set(Version.GetCurrentVersion())
      callback(o)
    cls._allocator.NextId(client, _OnAllocate)

  @classmethod
  @gen.engine
  def RangeQuery(cls, client, hash_key, range_desc, limit, col_names, callback,
                 excl_start_key=None, consistent_read=False, count=False, scan_forward=True):
    """Executes a range query using the predicate contained in 'range_desc'
    to select a set of items. If 'limit' is not None, then the database will
    be queried until 'limit' items have been fetched, or until there are no
    more items to fetch. If 'limit' is None, then the first page of results
    is returned (i.e. whatever DynamoDB returns).

    'range_desc' is a tuple of ([range_key], ('EQ'|'LE'|'LT'|'GE'|'GT'|'BEGINS_WITH')),
    --or-- ([range_start_key, range_end_key], 'BETWEEN').

    If 'excl_start_key' is not of type DBKey, assumes that 'excl_start_key'
    only specifies the range key and build an appropriate DBKey object using
    hash_key to feed to the db client interface.

    On completion, invokes callback with a list of queried objects. If
    count is True, invokes callback with count.
    """
    if limit == 0:
      assert not count
      callback([])
      return

    if not count:
      col_set = cls._CreateColumnSet(col_names)
      attrs = [cls._table.GetColumn(name).key for name in col_set]
    else:
      attrs = None

    if excl_start_key is not None and not isinstance(excl_start_key, db_client.DBKey):
      excl_start_key = db_client.DBKey(hash_key, excl_start_key)

    instance_count = 0
    instances = []
    while True:
      remaining = limit - instance_count if limit is not None else None
      query_result = yield gen.Task(client.Query, table=cls._table.name, hash_key=hash_key,
                                    range_operator=range_desc, attributes=attrs,
                                    limit=remaining, consistent_read=consistent_read,
                                    count=count, excl_start_key=excl_start_key, scan_forward=scan_forward)

      instance_count += query_result.count
      if not count:
        for item in query_result.items:
          instance = cls._CreateFromQuery(**item)
          instances.append(instance)

      assert limit is None or instance_count <= limit, (limit, instance_count)
      if query_result.last_key is None or limit is None or instance_count == limit:
        callback(instance_count if count else instances)
        break

      excl_start_key = query_result.last_key

  @classmethod
  def VisitRange(cls, client, hash_key, range_desc, col_names, visitor, callback,
                 consistent_read=False, scan_forward=True):
    """Query for all items in the specified key range. For each key,
    invoke the "visitor" function:

      visitor(object, visit_callback)

    When the visitor function has completed the visit, it should invoke
    "visit_callback" with no parameters. Once all object keys have been
    visited, then "callback" is invoked.
    """
    def _OnQuery(items):
      if len(items) < DBObject._VISIT_LIMIT:
        barrier_callback = callback
      else:
        barrier_callback = partial(_DoQuery, excl_start_key=items[-1].GetKey())

      with util.Barrier(barrier_callback) as b:
        for item in items:
          visitor(item, callback=b.Callback())

    def _DoQuery(excl_start_key):
      cls.RangeQuery(client, hash_key, range_desc, limit=DBObject._VISIT_LIMIT,
                     col_names=col_names, excl_start_key=excl_start_key,
                     callback=_OnQuery, consistent_read=consistent_read)

    _DoQuery(None)

  def GetKey(self):
    """Returns the object's composite (hash, range) key."""
    return db_client.DBKey(
      hash_key=self._columns[self._table.hash_key_col.name].Get(),
      range_key=self._columns[self._table.range_key_col.name].Get())

  @classmethod
  def _MakeIndexKey(cls, db_key):
    """Creates an indexing key from the provided object key. This is an
    amalgamation of the composite key. Separates the hash and range
    keys by a colon ':'. This method is symmetric with _ParseIndexKey.

    Override for more efficient formulation (e.g. Breadcrumb).
    """
    hash_key = util.ConvertToString(db_key.hash_key)
    range_key = util.ConvertToString(db_key.range_key)
    index_key = '%d:' % len(hash_key) + hash_key + range_key
    return index_key

  @classmethod
  def _ParseIndexKey(cls, index_key):
    """Returns a tuple representing the object's composite key by
    parsing the provided index key. This is symmetric with
    _MakeIndexKey, and is used to extract the actual object key from
    results of index queries.
    """
    colon_loc = index_key.find(':')
    assert colon_loc != -1, index_key
    hash_key_len = int(index_key[:colon_loc])
    index_key = index_key[colon_loc + 1:]
    hash_key = index_key[:hash_key_len]
    range_key = index_key[hash_key_len:]
    if cls._table.hash_key_col.value_type == 'N':
      hash_key = int(hash_key)
    if cls._table.range_key_col.value_type == 'N':
      range_key = int(range_key)
    return db_client.DBKey(hash_key=hash_key, range_key=range_key)

  @classmethod
  def _GetIndexedObjectClass(cls):
    """Can be overridden by derived range-type classes to specify what
    class of object can be created from a parsed index key, if not the
    DBRangeObject-derived class itself. For example, Breadcrumb index
    keys yield User instances, but Post index keys yield Post instances.
    """
    return cls
