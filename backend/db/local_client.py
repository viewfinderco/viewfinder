# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Local emulation of DynamoDB client.

Implements the DBClient interface identically (or as near as possible)
to the behavior expected from DynamoDB but using in-memory python data
structures for storage.
"""

__author__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
              'andy@emailscrubbed.com (Andy Kimball)']

from functools import partial
from bisect import bisect_left, bisect_right
import copy
import time

from tornado.ioloop import IOLoop
from viewfinder.backend.base.exceptions import DBConditionalCheckFailedError
from db_client import DBClient, DBKey, ListTablesResult, CreateTableResult, DescribeTableResult, DeleteTableResult, GetResult, PutResult, DeleteResult, UpdateResult, QueryResult, ScanResult, BatchGetResult, TableSchema, UpdateAttr

from viewfinder.backend.db import local_persist

class LocalClient(DBClient):
  """Local client for testing.

  - Datastore: dictionary of name => (HashTable, RangeTable)
    - HashTable: dictionary of hash_key => Item
      - Item: dictionary of attribute => value
    - RangeTable: dictionary of hash_key => dictionary of range_key => Item
      - Item: dictionary of attribute => value
  """
  _MUTATING_RESULTS = [CreateTableResult, DeleteTableResult, PutResult, DeleteResult, UpdateResult]

  def __init__(self, schema, read_only=False):
    self._schema = schema
    self._read_only = read_only
    self._tables = {}
    self._table_schemas = {}
    self._persist = local_persist.DBPersist(self._tables, self._table_schemas)

  def Shutdown(self):
    """Shutdown persistence on process exit."""
    self._persist.Shutdown()

  def ListTables(self, callback):
    table_names = [self._schema.TranslateNameInDb(name_in_db)
                   for name_in_db in self._tables.keys()]
    result = ListTablesResult(tables=table_names)
    return self._HandleCallback(callback, result)

  def CreateTable(self, table, hash_key_schema, range_key_schema,
                  read_units, write_units, callback):
    assert not self._read_only, 'Received "CreateTable" request on read-only database'

    assert table not in self._tables, 'table %s already exists' % table
    self._tables[table] = dict()
    schema = TableSchema(create_time=time.time(), hash_key_schema=hash_key_schema,
                         range_key_schema=range_key_schema, read_units=read_units,
                         write_units=write_units, status='CREATING')
    self._table_schemas[table] = self._NewSchemaStatus(schema, 'ACTIVE')
    result = CreateTableResult(schema=schema)
    return self._HandleCallback(callback, result)

  def DeleteTable(self, table, callback):
    assert not self._read_only, 'Received "DeleteTable" request on read-only database'

    assert table in self._tables, 'table %s does not exist' % table
    del self._tables[table]
    del_schema = self._NewSchemaStatus(self._table_schemas[table], 'DELETING')
    del self._table_schemas[table]
    result = DeleteTableResult(schema=del_schema)
    return self._HandleCallback(callback, result)

  def DescribeTable(self, table, callback):
    assert table in self._tables, 'table %s does not exist' % table
    result = DescribeTableResult(schema=self._table_schemas[table],
                                 count=self._GetTableSize(table), size_bytes=None)
    return self._HandleCallback(callback, result)

  def GetItem(self, table, key, callback, attributes, must_exist=True,
              consistent_read=False):
    self._CheckKey(table, key, True if must_exist else None, None)
    if key.hash_key not in self._tables[table]:
      return self._HandleCallback(callback, None)
    item = self._tables[table][key.hash_key]
    if key.range_key is not None:
      if key.range_key not in item:
        return self._HandleCallback(callback, None)
      item = item[key.range_key]
    result = GetResult(attributes=self._GetAttributes(item, attributes), read_units=1)
    return self._HandleCallback(callback, result)

  def BatchGetItem(self, batch_dict, callback, must_exist=True):
    assert len(batch_dict) == 1, 'BatchGetItem currently supports only a single table'
    table_name, (keys, attributes, consistent_read) = next(batch_dict.iteritems())

    result_items = []
    for key in keys:
      result = self.GetItem(table_name, key, None, attributes,
                            must_exist=must_exist, consistent_read=consistent_read)
      result_items.append(result.attributes if result is not None else None)

    result = {table_name: BatchGetResult(items=result_items, read_units=len(keys))}
    return self._HandleCallback(callback, result)

  def PutItem(self, table, key, callback, attributes, expected=None, return_values=None):
    assert not self._read_only, 'Received "PutItem" request on read-only database'

    self._CheckKey(table, key, None, expected)
    item = self._GetItem(table, key)
    # Make sure to add the keys as attributes.
    schema = self._table_schemas[table]
    attributes[schema.hash_key_schema.name] = key.hash_key
    if key.range_key is not None:
      attributes[schema.range_key_schema.name] = key.range_key
    return_attrs = self._UpdateItem(item, attributes, expected, return_values)
    result = PutResult(return_values=return_attrs, write_units=1)
    return self._HandleCallback(callback, result)

  def DeleteItem(self, table, key, callback, expected=None,
                 return_values=None):
    assert not self._read_only, 'Received "DeleteItem" request on read-only database'

    self._CheckKey(table, key, None, expected)
    item = self._GetItem(table, key)
    return_attrs = self._UpdateItem(item, None, expected, return_values)
    self._GetItem(table, key, delete=True)
    result = DeleteResult(return_values=return_attrs, write_units=1)
    return self._HandleCallback(callback, result)

  def UpdateItem(self, table, key, callback, attributes, expected=None, return_values=None):
    self._CheckKey(table, key, None, expected)
    assert not self._read_only, 'Received "UpdateItem" request on read-only database'

    if len(attributes) == 0:
      # If an UpdateItem request has a valid key but no additional attributes, DynamoDB returns
      # a seemingly positive result but does not actually create the item.  We are just emulating
      # that behavior here.
      result = UpdateResult(return_values={}, write_units=1)
      return self._HandleCallback(callback, result)
    item = self._GetItem(table, key)
    # Make sure to add the keys as attributes.
    schema = self._table_schemas[table]
    attributes[schema.hash_key_schema.name] = key.hash_key
    if key.range_key is not None:
      attributes[schema.range_key_schema.name] = key.range_key
    return_attrs = self._UpdateItem(item, attributes, expected, return_values)
    result = UpdateResult(return_values=return_attrs, write_units=1)
    return self._HandleCallback(callback, result)

  def Query(self, table, hash_key, range_operator, callback, attributes,
            limit=None, consistent_read=False, count=False,
            scan_forward=True, excl_start_key=None):
    schema = self._table_schemas[table]
    assert schema.range_key_schema, 'schema has no range key'
    self._CheckKeyType(table, schema.hash_key_schema, 'hash key', hash_key)
    range_dict = self._tables[table].get(hash_key, {})
    keys = sorted(range_dict.keys())
    if count:
      assert not attributes, 'cannot specify attributes and count=True'
      # TODO(spencer): determine what the read-units ought to be here.
      result = QueryResult(count=len(keys), items=[], last_key=None,
                           read_units=(len(keys) + 1023) / 1024)
      return self._HandleCallback(callback, result)

    # Handle range operator.
    if range_operator:
      key = range_operator.key[0]
      if range_operator.op == 'EQ':
        i = bisect_left(keys, key)
        keys = keys[i:i + 1] if i != len(keys) and keys[i] == key else []
      elif range_operator.op == 'LT':
        i = bisect_left(keys, key)
        keys = keys[0:i] if i else []
      elif range_operator.op == 'LE':
        i = bisect_right(keys, key)
        keys = keys[0:i] if i else []
      elif range_operator.op == 'GT':
        i = bisect_right(keys, key)
        keys = keys[i:] if i != len(keys) else []
      elif range_operator.op == 'GE':
        i = bisect_left(keys, key)
        keys = keys[i:] if i != len(keys) else []
      elif range_operator.op == 'BEGINS_WITH':
        keys = [v for v in keys if v.startswith(key)]
      elif range_operator.op == 'BETWEEN':
        s = bisect_left(keys, key)
        e = bisect_right(keys, range_operator.key[1])
        if s < len(keys) and e > 0:
          keys = keys[s:e]
        else:
          keys = []

    # Skip everything before (or after) excl_start_key if given.
    if excl_start_key is not None:
      assert excl_start_key.range_key != '', 'empty start key not supported (same as DynamoDB)'
      self._CheckKeyType(table, schema.range_key_schema, 'start key', excl_start_key.range_key)
      if scan_forward:
        i = bisect_right(keys, excl_start_key.range_key)
        keys = keys[i:] if i != len(keys) else []
      else:
        i = bisect_left(keys, excl_start_key.range_key)
        keys = keys[0:i] if i else []
    # Reverse keys if scanning backwards.
    if not scan_forward:
      keys.reverse()
    # Limit size of results.
    if limit is not None and limit < len(keys):
      keys = keys[0:limit]
      last_key = DBKey(hash_key=hash_key, range_key=keys[-1]) if len(keys) > 0 else None
    else:
      last_key = None

    bytes_read = 0
    items = []
    for k in keys:
      item = self._GetAttributes(range_dict[k], attributes)
      if item:
        items.append(item)
        bytes_read += len(k) if isinstance(k, (str, unicode)) else 8
        bytes_read += sum([len(a) + (len(d) if isinstance(d, (str, unicode)) else 8) for a, d in item.items()])

    read_units = (bytes_read / (1 if consistent_read else 2) + 1023) / 1024
    result = QueryResult(count=len(keys), items=items, last_key=last_key, read_units=read_units)
    return self._HandleCallback(callback, result)

  def Scan(self, table, callback, attributes, limit=None, excl_start_key=None, scan_filter=None):
    """Moves sequentially through entire table until 'excl_start_key'
    is located. Then iterates, passing each item through the
    conditions of 'scan_filter', accumulating up to 'limit' results.
    """
    assert limit is None or limit > 0, limit
    items = []
    last_key = None
    bytes_read = 0
    found = False

    def _FilterItem(item):
      """Returns whether the item passes the conditions of
      'scan_filter'.  This implementation is incomplete and supports
      only a subset of operators.
      """
      if scan_filter:
        for attr, condition in scan_filter.items():
          if attr not in item:
            return False
          elif condition.op == 'EQ':
            if item[attr] != condition.value[0]:
              return False
          elif condition.op == 'LT':
            if item[attr] >= condition.value[0]:
              return False
          elif condition.op == 'LE':
            if item[attr] > condition.value[0]:
              return False
          elif condition.op == 'GT':
            if item[attr] <= condition.value[0]:
              return False
          elif condition.op == 'GE':
            if item[attr] < condition.value[0]:
              return False
          elif condition.op == 'BEGINS_WITH':
            if item[attr] != condition.value[0]:
              return False
          elif condition.op == 'BETWEEN':
            if item[attr] < condition.value[0] or item[attr] > condition.value[1]:
              return False
      return True

    for hash_key, value in self._tables[table].items():
      # Iterate until we find last processed exclusive start key hash value.
      # These aren't in sorted order, so we just iterate until we find start
      # hash key before starting the scan.
      if not found and excl_start_key and excl_start_key.hash_key != hash_key:
        continue
      else:
        found = True
      # Handle composite-key scan.
      if self._table_schemas[table].range_key_schema:
        keys = sorted(value.keys())
        if excl_start_key and excl_start_key.hash_key == hash_key:
          assert excl_start_key.range_key != '', 'empty start key not supported (same as DynamoDB)'
          i = bisect_right(keys, excl_start_key.range_key)
          keys = keys[i:] if i != len(keys) else []
        for key in keys:
          bytes_read += sum([len(a) + (len(d) if isinstance(d, (str, unicode)) else 8) for a, d in value[key].items()])
          if _FilterItem(value[key]):
            item = self._GetAttributes(value[key], attributes)
            if item:
              items.append(item)
          if len(items) == limit:
            last_key = DBKey(hash_key=hash_key, range_key=key)
            break
      else:
        if not excl_start_key or excl_start_key.hash_key != hash_key:
          bytes_read += sum([len(a) + (len(d) if isinstance(d, (str, unicode)) else 8) for a, d in value.items()])
          if _FilterItem(value):
            item = self._GetAttributes(value, attributes)
            if item:
              items.append(item)
          if limit is not None and len(items) == limit:
            if hash_key != self._tables[table].keys()[-1]:
              last_key = DBKey(hash_key=hash_key, range_key=None)
            break

    read_units = (bytes_read / 2 + 1023) / 1024
    result = ScanResult(count=len(items), items=items, last_key=last_key, read_units=read_units)
    return self._HandleCallback(callback, result)

  def AddTimeout(self, deadline_secs, callback):
    """Invokes the specified callback after 'deadline_secs'."""
    return IOLoop.current().add_timeout(time.time() + deadline_secs, callback)

  def AddAbsoluteTimeout(self, abs_timeout, callback):
    """Invokes the specified callback at time 'abs_timeout'."""
    return IOLoop.current().add_timeout(abs_timeout, callback)

  def RemoveTimeout(self, timeout):
    """Removes an existing timeout."""
    IOLoop.current().remove_timeout(timeout)

  def _CheckKey(self, table, key, must_exist, expected):
    """Verifies the key matches the key schema."""
    assert table in self._table_schemas, 'table %s does not exist in %r' % (table, self._table_schemas)
    schema = self._table_schemas[table]

    if expected and expected.has_key(schema.hash_key_schema.name):
      assert expected[schema.hash_key_schema.name] == False
      must_exist = False

    assert key.hash_key is not None, 'need hash key: %s' % repr(key)
    self._CheckKeyType(table, schema.hash_key_schema, 'hash key', key.hash_key)
    if must_exist == True:
      assert key.hash_key in self._tables[table], 'key %s does not exist' % key.hash_key
    elif must_exist == False and schema.range_key_schema == None:
      if key.hash_key in self._tables[table]:
        raise DBConditionalCheckFailedError('key %s already exists' % key.hash_key)

    if key.range_key is not None:
      assert schema.range_key_schema is not None, 'table has no range key in schema'
      self._CheckKeyType(table, schema.range_key_schema, 'range key', key.range_key)

      if must_exist == True:
        assert key.range_key in self._tables[table][key.hash_key], \
            'range key %s does not exist' % key.range_key
      elif must_exist == False and key.hash_key in self._tables[table]:
        if key.range_key in self._tables[table][key.hash_key]:
          raise DBConditionalCheckFailedError('range key %s already exists' % key.range_key)

    else:
      assert schema.range_key_schema is None, 'missing range key'

  def _CheckKeyType(self, table, key_schema, key_type, value):
    """Ensures that 'value' is of a type compatible with 'key_schema'
    (which is either 'N' for number or 'S' for string).
    """
    if key_schema.value_type == 'N':
      assert isinstance(value, (int, long, float)), \
          '%s for column "%s" in table "%s" must be a number: %s' % (key_type, key_schema.name, table, repr(value))
    elif key_schema.value_type == 'S':
      assert isinstance(value, (str, unicode)), \
          '%s for column "%s" in table "%s" must be a string: %s' % (key_type, key_schema.name, table, repr(value))
    else:
      assert False, 'unexpected schema type "%s"' % key_schema.schema_type

  def _NewSchemaStatus(self, schema, new_status):
    """Returns a new schema with status set to 'new_status'."""
    return TableSchema(create_time=schema.create_time,
                       hash_key_schema=schema.hash_key_schema,
                       range_key_schema=schema.range_key_schema,
                       read_units=schema.read_units,
                       write_units=schema.write_units,
                       status=new_status)

  def _GetItem(self, table, key, delete=False):
    """Fetches the item from the store by table & key. If 'delete',
    deletes the item.
    """
    if key.range_key is not None:
      if key.hash_key not in self._tables[table]:
        self._tables[table][key.hash_key] = dict()
      if key.range_key not in self._tables[table][key.hash_key]:
        self._tables[table][key.hash_key][key.range_key] = dict()
      if not delete:
        return self._tables[table][key.hash_key][key.range_key]
      else:
        del self._tables[table][key.hash_key][key.range_key]
    else:
      if not delete:
        if key.hash_key not in self._tables[table]:
          self._tables[table][key.hash_key] = dict()
        return self._tables[table][key.hash_key]
      else:
        del self._tables[table][key.hash_key]

  def _GetAttributes(self, item, attributes):
    """Gets the list of named 'attributes' from the item. If an
    attribute is not present in the item, it won't be returned.
    If attributes is None, all attributes are returned.
    """
    if not attributes:
      return item
    result = dict([(a, item[a]) for a in attributes if item.has_key(a)])
    return result

  def _UpdateItem(self, item, attributes, expected, return_values):
    """Logic to update a data item. Called from PutItem() and
    UpdateItem().
    """
    if expected:
      for k, v in expected.items():
        if isinstance(v, bool):
          assert v == False
          if item.has_key(k):
            raise DBConditionalCheckFailedError('expected attr %s not to exist, but exists with value %r'
                                                % (k, item[k]))
        else:
          if not item.has_key(k):
            raise DBConditionalCheckFailedError('expected attr %s does not exist: %r' % (k, item))
          if item[k] != v:
            raise DBConditionalCheckFailedError('expected mismatch: %s != %s' % (repr(item[k]), repr(v)))
    return_attrs = None
    if return_values == 'ALL_OLD':
      return_attrs = copy.deepcopy(item)
    elif return_values == 'UPDATED_OLD':
      if not attributes:
        return_attrs = copy.deepcopy(item)
      else:
        return_attrs = dict([(k, copy.deepcopy(item[k])) for k in attributes.keys()])

    # Update (or delete) the item.
    if attributes:
      for key, update in attributes.items():
        if isinstance(update, UpdateAttr):
          if update.action == 'PUT':
            assert not isinstance(update.value, list) or update.value, \
                   'PUT of empty list is not supported (matches DynamoDB behavior)'
            item[key] = update.value
          elif update.action == 'ADD':
            if isinstance(update.value, list):
              if not key in item:
                item[key] = list()
              for v in update.value:
                if v not in item[key]:
                  item[key].append(v)
              item[key].sort()
            else:
              assert isinstance(update.value, (int, long, float)), \
                  'value not number: %s' % repr(update.value)
              if not key in item:
                item[key] = 0
              item[key] += update.value
          elif update.action == 'DELETE':
            if isinstance(update.value, list):
              for v in update.value:
                if key in item and v in item[key]:
                  item[key].remove(v)
            elif key in item:
              # Delete attribute in item, if it exists (matches DynamoDB behavior).
              del item[key]
        else:
          item[key] = update
    else:
      item.clear()

    if return_values == 'ALL_NEW':
      return_attrs = copy.deepcopy(item)
    elif return_values == 'UPDATED_NEW':
      if not attributes:
        return_attrs = dict()
      else:
        return_attrs = dict([(k, copy.deepcopy(item[k])) for k in attributes.keys()])

    return return_attrs

  def _HandleCallback(self, callback, result):
    """If callback is not None, runs asynchronously; otherwise, runs
    synchronously.
    """
    if any(isinstance(result, rt) for rt in LocalClient._MUTATING_RESULTS):
      self._persist.MarkDirty()
    if callback:
      IOLoop.current().add_callback(partial(callback, result))
    else:
      return result

  def _GetTableSize(self, table):
    """Computes the number of elements in the table. If the table
    schema has a composite key, iterates over each hash key to compute
    the full length.
    """
    schema = self._table_schemas[table]
    if schema.range_key_schema:
      return sum([len(rd) for rd in self._tables[table].values()])
    else:
      return len(self._tables[table])
