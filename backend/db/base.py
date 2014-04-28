# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Base object for building python classes to represent the data
in a database row.

See DBHashObject and DBRangeObject.

  DBObject: base class of all data objects
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

from functools import partial
import logging

from tornado import gen
from viewfinder.backend.base import util
from tornado.concurrent import return_future
from viewfinder.backend.db import db_client, query_parser, schema, vf_schema
from viewfinder.backend.db.versions import Version

class DBObject(object):
  """Base class for representing a row of data. Setting a column value
  to None will delete the column from the datastore on Update().
  """
  _VISIT_LIMIT = 50

  _schema = vf_schema.SCHEMA

  __slots__ = ['_columns', '_reindex']

  def __init__(self, columns=None):
    """The base datastore object class manages columns according to
    the database schema as defined by the subclass' schema table
    definition. However, derived classes can override the column set
    by specifying the "columns" argument. Columns of type IndexTermsColumn
    are ignored here. They will not create column values which can be
    accessed via the __{Get,Set}Property() methods.

    Creates a new python property for each column in the table for the
    data object according to the schema. This is only done once per class,
    as properties actually modify the class, not the instance.
    """
    self._columns = {}
    self._reindex = False
    columns = columns or self._table.GetColumns()
    for c in columns:
      if not isinstance(c, schema.IndexTermsColumn):
        self._columns[c.name] = c.NewInstance()

  @staticmethod
  def map_table_attributes(cls):
    """Class decorator which adds properties for all columns defined in a table.

    The class must define a class attribute _table.

    Example:
      @DBObject.map_table_attributes
      class Foo(DBRangeObject):
        _table = DBObject._schema.GetTable(vf_schema.FOO)
    """
    assert issubclass(cls, DBObject)
    for c in cls._table.GetColumns():
      if not isinstance(c, schema.IndexTermsColumn):
        fget = (lambda name: lambda self: self.__GetProperty(name))(c.name)
        fset = (lambda name: lambda self, value: self.__SetProperty(name, value))(c.name)
        setattr(cls, c.name, property(fget, fset))
    return cls

  def __dir__(self):
    return self._columns.keys()

  def __repr__(self):
    items = []
    for name, column in self._columns.iteritems():
      if column.Get() is None:
        continue
      value = repr(column.Get())
      if self.ShouldScrubColumn(name):
        value = '...scrubbed %s bytes...' % len(value)
      items.append((name, value))
    return '{' + ', '.join('\'%s\': %s' % (n, v) for n, v in items) + '}'

  @classmethod
  def ShouldScrubColumn(cls, name):
    """Override to return True for columns that should not appear in logs."""
    return False

  def __GetProperty(self, name):
    return self._columns[name].Get()

  def __SetProperty(self, name, value):
    return self._columns[name].Set(value)

  def _asdict(self):
    return dict([(n, c.Get(asdict=True)) for n, c in self._columns.items() \
                   if c.Get() is not None])

  def _Clone(self):
    # Construct new instance of this type and transfer raw in-memory column values.
    o = type(self)()
    for n, col in self._columns.items():
      o._columns[n]._value = col._value
    return o

  def _IsModified(self, name):
    """Returns whether or not a column value has been modified."""
    return self._columns[name].IsModified()

  def GetColNames(self):
    """Returns all column names."""
    return self._columns.keys()

  def GetModifiedColNames(self):
    """Returns all column names where the column value has been modified."""
    return [c.col_def.name for c in self._columns.values() if c.IsModified()]

  def SetReindexOnUpdate(self, reindex):
    """Sets the _reindex boolean. If set to True, index terms for all
    columns will be re-generated on update, regardless of whether or
    not the column has been modified. This is used during data
    migrations when the indexing algorithm for a particular column
    type (or types) has been modified. Only generates writes (and
    deletes for pre-existing, now obsolete terms) to the index table
    when terms for a column change.
    """
    self._reindex = reindex

  @classmethod
  def CreateFromKeywords(cls, **obj_dict):
    """Creates a new object of type 'cls' with attributes as specified
    in 'obj_dict'. The key columns must be present in the attribute
    dictionary. Returns new object instance.
    """
    assert obj_dict.has_key(cls._table.hash_key_col.name)
    if cls._table.range_key_col:
      assert obj_dict.has_key(cls._table.range_key_col.name), (cls._table.range_key_col.name, obj_dict)
    o = cls()
    o.UpdateFromKeywords(**obj_dict)
    o._columns[schema.Table.VERSION_COLUMN.name].Set(Version.GetCurrentVersion())
    return o

  def UpdateFromKeywords(self, **obj_dict):
    """Updates the contents of the object according to **obj_dict."""
    for k, v in obj_dict.items():
      if k in self._columns:
        self._columns[k].Set(v)
      else:
        raise KeyError('column %s (value %r) not found in class %s' % (k, v, self.__class__))

  def HasMismatchedValues(self, mismatch_allowed_set=None, **obj_dict):
    """Check that each of the dictionary values matches what's in the object.
    The only keys that don't need to match are ones contained in the mismatch_allowed_set.
    Returns: True if mismatch found.  Otherwise, False.
    """
    for k, v in obj_dict.items():
      if k in self._columns:
        if mismatch_allowed_set is None or k not in mismatch_allowed_set:
          if self._columns[k].Get(asdict=isinstance(v, dict)) != v:
            return True
    return False

  @return_future
  def Update(self, client, callback, expected=None, replace=True, return_col_names=False):
    """Updates or inserts the object. Only modified columns are
    updated. Updates the index terms first and finally the object, so
    the update operation, on retry, will be idempotent.

    'expected' are preconditions for attribute values for the update
    to succeed.

    If 'replace' is False, forces a conditional update which verifies
    that the primary key does not already exist in the datastore.

    If 'return_col_names' is True, 'callback' is invoked with a list
    of the modified column names.
    """
    mod_cols = [c for c in self._columns.values() if c.IsModified()]
    if return_col_names:
      callback = partial(callback, [c.col_def.name for c in mod_cols])

    if not mod_cols and not self._reindex:
      callback()
      return

    # Transform expected attributes dict to refer to column keys instead of names.
    if expected:
      expected = dict([(self._table.GetColumn(k).key, v) for k, v in expected.items()])
    else:
      expected = {}

    def _OnUpdate(result):
      [col.OnUpdate() for col in mod_cols]
      callback()

    def _OnUpdateIndexTerms(term_attrs):
      attrs = dict()
      for c in mod_cols:
        update = c.Update()
        if update:
          attrs[c.col_def.key] = update
      if term_attrs:
        attrs.update(term_attrs)
      if not replace:
        expected[self._table.hash_key_col.key] = False
        if self._table.range_key_col:
          expected[self._table.range_key_col.key] = False
      client.UpdateItem(table=self._table.name, key=self.GetKey(),
                        attributes=attrs, expected=expected, callback=_OnUpdate)

    def _OnQueryIndexTerms(term_updates, result):
      old_dict = result.attributes or {}
      term_attrs = {}
      add_terms = {}  # dict of term dicts by term key
      del_terms = []  # list of term keys
      for name, update in term_updates.items():
        key = self._table.GetColumn(name).key + ':t'
        terms = set(update.value.keys()) if update.value else set()

        # Special check here; you cannot 'PUT' an empty set. Must 'DELETE'.
        if update.action == 'PUT' and not terms:
          term_attrs[key] = db_client.UpdateAttr(value=None, action='DELETE')
        else:
          term_attrs[key] = db_client.UpdateAttr(value=list(terms), action=update.action)

        # Compute which index terms to add and which to delete.
        if update.action == 'PUT':
          old_terms = set(old_dict.get(key, []))
          add_terms.update(dict([(t, update.value[t]) for t in terms.difference(old_terms)]))
          del_terms += old_terms.difference(terms)
        elif update.action == 'ADD':
          add_terms.update(update.value)
        elif update.action == 'DELETE':
          del_terms += terms

      # Add and delete all terms as necessary.
      with util.Barrier(partial(_OnUpdateIndexTerms, term_attrs)) as b:
        index_key = self._GetIndexKey()
        for term, data in add_terms.items():
          attrs = {'d': data} if data else {}
          client.PutItem(table=vf_schema.INDEX, callback=b.Callback(), attributes=attrs,
                         key=db_client.DBKey(hash_key=term, range_key=index_key))
        for term in del_terms:
          client.DeleteItem(table=vf_schema.INDEX, callback=b.Callback(),
                            key=db_client.DBKey(hash_key=term, range_key=index_key))

    if isinstance(self._table, schema.IndexedTable):
      index_cols = mod_cols if not self._reindex else \
          [c for c in self._columns.values() if c.Get() is not None]
      index_cols = [c for c in index_cols if c.col_def.indexer]
      # Get a dictionary of term updates for the object.
      term_updates = dict([(c.col_def.name, c.IndexTerms()) for c in index_cols])
      col_names = [n for n, u in term_updates.items() if u.action == 'PUT']
      # For any term updates which are PUT, fetch the previous term sets.
      self._QueryIndexTerms(client, col_names=col_names,
                            callback=partial(_OnQueryIndexTerms, term_updates))
    else:
      _OnUpdateIndexTerms(None)

  def Delete(self, client, callback, expected=None):
    """Deletes all columns of the object and all associated index
    terms. Deletes the index terms first and finally the object, so
    the deletion operation, on retry, will be idempotent.

    'expected' are preconditions for attribute values for the delete
    to succeed.
    """
    # Transform expected attributes dict to refer to column keys instead of names.
    if expected:
      expected = dict([(self._table.GetColumn(k).key, v) for k, v in expected.items()])

    def _OnDelete(result):
      callback()

    def _OnDeleteIndexTerms():
      client.DeleteItem(table=self._table.name, key=self.GetKey(),
                        callback=_OnDelete, expected=expected)

    def _OnQueryIndexTerms(get_result):
      terms = [t for term_set in get_result.attributes.values() for t in term_set]
      with util.Barrier(_OnDeleteIndexTerms) as b:
        index_key = self._GetIndexKey()
        [client.DeleteItem(table=vf_schema.INDEX,
                           key=db_client.DBKey(hash_key=term, range_key=index_key),
                           callback=b.Callback()) for term in terms]

    if isinstance(self._table, schema.IndexedTable):
      assert expected is None, expected
      self._QueryIndexTerms(client, col_names=self._table.GetColumnNames(),
                            callback=_OnQueryIndexTerms)
    else:
      _OnDeleteIndexTerms()

  def _QueryIndexTerms(self, client, col_names, callback):
    """Queries the index terms for the specified columns. If no
    columns are specified, invokes callback immediately. When a column
    is indexed, the set of index terms produced is stored near the
    column value to be queried on modifications. Having access to the
    old set is especially crucial if the indexing algorithm changes.
    """
    idx_cols = [self._columns[name] for name in col_names if self._table.GetColumn(name).indexer]
    attrs = [c.col_def.key + ':t' for c in idx_cols]

    def _OnQuery(get_result):
      """Handle case of new object and a term attributes query failure."""
      if get_result is None:
        callback(db_client.GetResult(attributes=dict([(a, set()) for a in attrs]), read_units=0))
      else:
        callback(get_result)

    if attrs:
      client.GetItem(table=self._table.name, key=self.GetKey(), attributes=attrs,
                     must_exist=False, consistent_read=True, callback=_OnQuery)
    else:
      # This may happen if no indexed columns were updated. Simply
      # supply an empty attribute dict to the callback.
      callback(db_client.GetResult(attributes=dict(), read_units=0))

  def _GetIndexKey(self):
    """Returns the indexing key for this object by calling the
    _MakeIndexKey class method, which is overridden by derived classes.
    """
    return self._MakeIndexKey(self.GetKey())

  @classmethod
  def _CreateFromQuery(cls, **attr_dict):
    """Creates a new instance of cls and sets the values of its
    columns from 'attr_dict'. Returns the new object instance.
    """
    assert attr_dict.has_key(cls._table.hash_key_col.key), attr_dict
    if cls._table.range_key_col:
      assert attr_dict.has_key(cls._table.range_key_col.key), attr_dict

    o = cls()
    for k, v in attr_dict.items():
      name = cls._table.GetColumnName(k)
      o._columns[name].Load(v)

    return o

  @classmethod
  def Scan(cls, client, col_names, callback, limit=None, excl_start_key=None,
           scan_filter=None):
    """Scans the table up to a count of 'limit', starting at the hash
    key value provided in 'excl_start_key'. Invokes the callback with
    the list of elements and the last scanned key (list, last_key).
    The last_key will be None if the last item was scanned.

    'scan_filter' is a map from attribute name to a tuple of
    ([attr_value], ('EQ'|'LE'|'LT'|'GE'|'GT'|'BEGINS_WITH')),
    --or-- ([start_attr_value, end_attr_value], 'BETWEEN').
    """
    if limit == 0:
      callback(([], None))

    col_set = cls._CreateColumnSet(col_names)

    # Convert scan filter from attribute names to keys.
    if scan_filter:
      scan_filter = dict([(cls._table.GetColumn(k).key, v) for k, v in scan_filter.items()])

    def _OnScan(result):
      objs = []
      for item in result.items:
        objs.append(cls._CreateFromQuery(**item))
      callback((objs, result.last_key))

    client.Scan(table=cls._table.name, callback=_OnScan,
                attributes=[cls._table.GetColumn(name).key for name in col_set],
                limit=limit, excl_start_key=excl_start_key, scan_filter=scan_filter)

  @classmethod
  @gen.engine
  def BatchQuery(cls, client, keys, col_names, callback,
                 must_exist=True, consistent_read=False):
    """Queries for a batch of items identified by DBKey objects in the 'keys' array. Projects
    the specified columns (or all columns if col_names==None). If 'must_exist' is False, then
    return None for each item that does not exist in the database.
    """
    col_set = cls._CreateColumnSet(col_names)

    request = db_client.BatchGetRequest(keys=keys,
                                        attributes=[cls._table.GetColumn(name).key
                                                    for name in col_set],
                                        consistent_read=consistent_read)
    result = yield gen.Task(client.BatchGetItem,
                            batch_dict={cls._table.name: request},
                            must_exist=must_exist)

    result_objects = []
    for item in result[cls._table.name].items:
      if item is not None:
        result_objects.append(cls._CreateFromQuery(**item))
      else:
        result_objects.append(None)

    callback(result_objects)

  @classmethod
  def KeyQuery(cls, client, key, col_names, callback,
               must_exist=True, consistent_read=False):
    """Queries the specified columns (or all columns if
    col_names==None), using key as the object hash key.
    """
    col_set = cls._CreateColumnSet(col_names)

    def _OnQuery(result):
      o = None
      if result and result.attributes:
        o = cls._CreateFromQuery(**result.attributes)
      callback(o)

    client.GetItem(table=cls._table.name, key=key,
                   attributes=[cls._table.GetColumn(name).key for name in col_set],
                   must_exist=must_exist, consistent_read=consistent_read,
                   callback=_OnQuery)

  @classmethod
  def IndexQueryKeys(cls, client, bound_query_str, callback,
                     start_index_key=None, end_index_key=None,
                     limit=50, consistent_read=False):
    """Returns a sequence of object keys to 'callback' resulting from
    execution of 'bound_query_str'.
    """
    def _OnQueryKeys(index_keys):
      callback([cls._ParseIndexKey(index_key) for index_key in index_keys])

    try:
      start_key = cls._MakeIndexKey(start_index_key) if start_index_key is not None else None
      end_key = cls._MakeIndexKey(end_index_key) if end_index_key is not None else None
      query, param_dict = query_parser.CompileQuery(cls._schema, bound_query_str)
      query.Evaluate(client,
                     callback=_OnQueryKeys,
                     start_key=start_key,
                     end_key=end_key,
                     limit=limit,
                     consistent_read=consistent_read,
                     param_dict=param_dict)
    except:
      logging.exception('query evaluates to empty: ' + str(bound_query_str))
      callback([])

  @classmethod
  @gen.engine
  def IndexQuery(cls, client, bound_query_str, col_names, callback,
                 start_index_key=None, end_index_key=None,
                 limit=50, consistent_read=False):
    """Returns a sequence of Objects resulting from the execution of
    'query' as the first parameter to 'callback'. Only the columns
    specified in 'col_names' are queried, or all columns if None.
    """
    try:
      start_key = cls._MakeIndexKey(start_index_key) if start_index_key is not None else None
      end_key = cls._MakeIndexKey(end_index_key) if end_index_key is not None else None
      query, param_dict = query_parser.CompileQuery(cls._schema, bound_query_str)
      index_keys = yield gen.Task(query.Evaluate,
                                  client,
                                  start_key=start_key,
                                  end_key=end_key,
                                  limit=limit,
                                  consistent_read=consistent_read,
                                  param_dict=param_dict)
    except:
      logging.exception('query evaluates to empty: ' + str(bound_query_str))
      callback([])
      return

    query_keys = [cls._ParseIndexKey(index_key) for index_key in index_keys]
    objects = yield gen.Task(cls._GetIndexedObjectClass().BatchQuery,
                             client,
                             query_keys,
                             col_names,
                             must_exist=False,
                             consistent_read=consistent_read)
    # Compact results
    compacted_result = [obj for obj in objects if obj is not None]
    callback(compacted_result)

  @classmethod
  def VisitIndexKeys(cls, client, bound_query_str, visitor, callback,
                     start_index_key=None, end_index_key=None, consistent_read=False):
    """Query for all object keys in the specified key range. For each key,
    invoke the "visitor" function:

      visitor(object_key, visit_callback)

    When the visitor function has completed the visit, it should invoke
    "visit_callback" with no parameters. Once all object keys have been
    visited, then "callback" is invoked.
    """
    def _OnQueryKeys(index_keys):
      if len(index_keys) < DBObject._VISIT_LIMIT:
        barrier_callback = callback
      else:
        barrier_callback = partial(DBObject.VisitIndexKeys, client, bound_query_str, visitor, callback,
                                   start_index_key=index_keys[-1], end_index_key=end_index_key,
                                   consistent_read=consistent_read)

      with util.Barrier(barrier_callback) as b:
        for index_key in index_keys:
          visitor(index_key, callback=b.Callback())

    cls.IndexQueryKeys(client, bound_query_str, _OnQueryKeys, limit=DBObject._VISIT_LIMIT,
                       start_index_key=start_index_key, end_index_key=end_index_key,
                       consistent_read=consistent_read)

  @classmethod
  def VisitIndex(cls, client, bound_query_str, visitor, col_names, callback,
                 start_index_key=None, end_index_key=None, consistent_read=False):
    """Query for all objects in the specified key range. For each object,
    invoke the "visitor" function:

      visitor(object, visit_callback)

    When the visitor function has completed the visit, it should invoke
    "visit_callback" with no parameters. Once all objects have been
    visited, then "callback" is invoked.
    """
    def _OnQuery(objects):
      if len(objects) < DBObject._VISIT_LIMIT:
        barrier_callback = callback
      else:
        barrier_callback = partial(DBObject.VisitIndex, client, bound_query_str, visitor, col_names, callback,
                                   start_index_key=objects[-1]._GetIndexKey(), end_index_key=end_index_key,
                                   consistent_read=consistent_read)

      with util.Barrier(barrier_callback) as b:
        for object in objects:
          visitor(object, b.Callback())

    cls.IndexQuery(client, bound_query_str, col_names, _OnQuery, limit=DBObject._VISIT_LIMIT,
                   start_index_key=start_index_key, end_index_key=end_index_key,
                   consistent_read=consistent_read)

  @classmethod
  def _CreateColumnSet(cls, col_names):
    """Creates a set of column names from the 'col_names' list (all columns in the table if
    col_names == None). Ensures that the hash key, range key, and version column are always
    included in the set.
    """
    col_set = set(col_names or cls._table.GetColumnNames())
    col_set.add(cls._table.hash_key_col.name)
    if cls._table.range_key_col:
      col_set.add(cls._table.range_key_col.name)
    col_set.add(schema.Table.VERSION_COLUMN.name)
    return col_set
