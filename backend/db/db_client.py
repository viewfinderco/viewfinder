# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Interface for client access to datastore backends.

Implemented via the DynamoDB client (dynamodb_client) and the local datastore
emulation client (local_client).

Each client operation takes a callback for asynchronous operation.

  Client operations:
    - GetItem: retrieve a database item by key (can be composite key)
    - BatchGetItem: retrieve a batch of database items by key
    - PutItem: store a database item
    - DeleteItem: deletes a database item
    - UpdateItem: update attributes of a database item
    - Query: queries database item(s)
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

from collections import namedtuple
from tornado import ioloop, options

options.define('localdb', default=False, help='use local datastore emulation')
options.define('localdb_dir', default='./local/db',
               help='directory in which to store database persistence files')
options.define('localdb_sync_secs', default=1.0,
               help='seconds between successive syncs to disk')
options.define('localdb_version', default=0,
               help='specify a version other than 0 to use as the current on startup; '
               'the current version ".0" is still moved to ".1" as normal')
options.define('localdb_num_versions', default=20,
               help='number of previous versions of the database to maintain')
options.define('localdb_reset', default=False,
               help='reset all existing database files')

options.define('readonly_db', default=False, help='Read-only database')


# Operation information, including operation id and priority, 'op_id'
# == 0 means the request is not attached to an operation but is being
# made extemporaneously.
DBOp = namedtuple('DBOp', ['op_id', 'priority'])

# Named tuple for database keys. Composite keys define both the hash
# key and the range key. Objects which have only a hash key leave the
# range key as None.
DBKey = namedtuple('DBKey', ['hash_key', 'range_key'])

DBKeySchema = namedtuple('DBKeySchema', ['name', 'value_type'])

# Named tuple of calls to Client.UpdateItem. Action must be one of
# 'PUT', 'ADD', 'DELETE'.
UpdateAttr = namedtuple('UpdateAttr', ['value', 'action'])

# Named tuple for range key queries. 'key' is a list of length 1 if
# 'op' is one of (EQ|LE|LT|GE|GT|BEGINS_WITH), --or-- 'key' is a list
# of length 2 ([start, end]), if 'op' is BETWEEN.
RangeOperator = namedtuple('RangeOperator', ['key', 'op'])

# Named tuple for scan filter. The comments for RangeOperator apply
# here as well, though local_db supports only a subset of the actual
# scan filter functionality. 'value' is analagous here to 'key' in
# RangeOperator. It is a list of either one or more than one values
# depending on the value of 'op'.
ScanFilter = namedtuple('ScanFilter', ['value', 'op'])

# Description of a table.
TableSchema = namedtuple('TableSchema', ['create_time', 'hash_key_schema',
                                         'range_key_schema', 'read_units',
                                         'write_units', 'status'])

# Table metadata results.
ListTablesResult = namedtuple('ListTables', ['tables'])
CreateTableResult = namedtuple('CreateTable', ['schema'])
DescribeTableResult = namedtuple('DescribeTable', ['schema', 'count', 'size_bytes'])
DeleteTableResult = namedtuple('DeleteTable', ['schema'])

# Named tuples for results of datastore operations.
GetResult = namedtuple('GetResult', ['attributes', 'read_units'])
PutResult = namedtuple('PutResult', ['return_values', 'write_units'])
DeleteResult = namedtuple('DeleteResult', ['return_values', 'write_units'])
UpdateResult = namedtuple('UpdateResult', ['return_values', 'write_units'])
QueryResult = namedtuple('QueryResult', ['count', 'items', 'last_key', 'read_units'])
ScanResult = namedtuple('ScanResult', ['count', 'items', 'last_key', 'read_units'])

# Batch tuples (batch operations use dictionary that maps from table name => tuple).
BatchGetRequest = namedtuple('BatchGetRequest', ['keys', 'attributes', 'consistent_read'])
BatchGetResult = namedtuple('BatchGetResult', ['items', 'read_units'])


class DBClient(object):
  """Interface for asynchronous access to backend datastore.
  """
  def Shutdown(self):
    """Cleanup on process exit."""
    raise NotImplementedError()

  def ListTables(self, callback):
    """Lists the set of tables."""
    raise NotImplementedError()

  def CreateTable(self, table, hash_key_schema, range_key_schema,
                  read_units, write_units, callback):
    """Create a table with specified name, key schema and provisioned
    throughput settings.
    """
    raise NotImplementedError()

  def DeleteTable(self, table, callback):
    """Create a table with specified name, key schema and provisioned
    throughput settings.
    """
    raise NotImplementedError()

  def DescribeTable(self, table, callback):
    """Describes the named table."""
    raise NotImplementedError()

  def GetItem(self, table, key, callback, attributes, must_exist=True,
              consistent_read=False):
    """Gets the specified attribute values by key. 'must_exist'
    specifies whether to throw an exception if the item is not found.
    If False, None is returned if not found. 'consistent_read'
    designates whether to fetch an authoritative value for the item.
    """
    raise NotImplementedError()

  def BatchGetItem(self, batch_dict, callback, must_exist=True):
    """Gets a batch of items from the database. Items to get are described in 'batch_dict',
    which has the following format:

      {'table-name-0': BatchGetRequest(keys=<list of db-keys from the table>,
                                       attributes=[attr-0, attr-1, ...],
                                       consistent_read=<bool>),
       'table-name-1': ...}

    Returns results in the following format:

      {'table-name-0': BatchGetResult(items={'attr-0': value-0, 'attr-1': value-1, ...},
                                      read_units=3.0),
       'table-name-1': ...}

    If 'must_exist' is true, then raises an error if a db-key is not found in the table.
    Otherwise, returns None in corresponding positions in the 'items' array.
    """
    raise NotImplementedError()

  def PutItem(self, table, key, callback, attributes, expected=None,
              return_values=None):
    """Sets the specified item attributes by key. 'attributes' is a
    dict {attr: value}. If 'expected' is not None, requires that the
    values specified in the expected dict {attr: value} match before
    mutation. 'return_values', if not None, must be one of (NONE,
    ALL_OLD); if ALL_OLD, the previous values for the named attributes
    are returned as an attribute dict.
    """
    raise NotImplementedError()

  def DeleteItem(self, table, key, callback, expected=None,
                 return_values=None):
    """Deletes the specified item by key. 'expected' and
    'return_values' are identical to PutItem().
    """
    raise NotImplementedError()

  def UpdateItem(self, table, key, callback, attributes, expected=None,
                 return_values=None):
    """Updates the specified item attributes by key. 'attributes' is a
    dict {attr: AttrUpdate} (see AttrUpdate named tuple above).
    'expected' and 'return_values' are the same as for PutItem(),
    except that 'return_values' may contain any of (NONE, ALL_OLD,
    UPDATED_OLD, ALL_NEW, UPDATED_NEW).
    """
    raise NotImplementedError()

  def Query(self, table, hash_key, range_operator, callback, attributes,
            limit=None, consistent_read=False, count=False,
            scan_forward=True, excl_start_key=None):
    """Queries a range of values by 'hash_key' and 'range_operator'.
    'range_operator' is of type RangeOperator (see named tuple above;
    if None, selects all values). 'attributes' is a list of
    attributes to query, limit is an upper limit on the number of
    results. If True, 'count' will return just a count of items, but
    no actual data. 'scan_forward', if False, causes a reverse scan
    according to the range operator. If not None, 'excl_start_key'
    allows the query operation to start partway through the
    range. 'excl_start_key' specifies just the range key.
    """
    raise NotImplementedError()

  def Scan(self, table, callback, attributes, limit=None,
           excl_start_key=None, scan_filter=None):
    """Scans the table starting at 'excl_start_key' (if provided) and
    reading the next 'limit' rows, reading the specified 'attributes'.
    If 'scan_filter' is specified, it is applied to each scanned item
    to pre-filter returned results. 'scan_filter' is a map from
    attribute name to ScanFilter tuple.
    """
    raise NotImplementedError()

  def AddTimeout(self, deadline_secs, callback):
    """Invokes the specified callback after 'deadline_secs'. Returns a
    handle which can be suppled to RemoveTimeout to disable the
    timeout.
    """
    raise NotImplementedError()

  def AddAbsoluteTimeout(self, abs_timeout, callback):
    """Invokes the specified callback at wall time
    'abs_timeout'. Returns a handle which can be supplied to
    RemoveTimeout to disable the timeout."""
    raise NotImplementedError()

  def RemoveTimeout(self, timeout):
    """Removes a timeout added via AddTimeout or AddAbsoluteTimeout."""
    raise NotImplementedError()

  @staticmethod
  def Instance():
    assert hasattr(DBClient, "_instance"), 'instance not initialized'
    return DBClient._instance

  @staticmethod
  def SetInstance(client):
    """Sets a new instance for testing."""
    DBClient._instance = client


def InitDB(schema=None, callback=None, verify_or_create=True):
  """Sets the db client instance.
  Initialize the local datastore if --localdb was specified.

  Callback is invoked with the verified table schemas if
  'verify_or_create' is True; None otherwise.
  """
  assert not hasattr(DBClient, "_instance"), 'instance already initialized'
  assert schema is not None
  if options.options.localdb:
    from local_client import LocalClient
    DBClient.SetInstance(LocalClient(schema, read_only=options.options.readonly_db))
  else:
    from dynamodb_client import DynamoDBClient
    DBClient._instance = DynamoDBClient(schema, read_only=options.options.readonly_db)
  if verify_or_create:
    schema.VerifyOrCreate(DBClient.Instance(), callback)
  else:
    callback([])

def ShutdownDB():
  """Shuts down the currently running instance."""
  if hasattr(DBClient, "_instance"):
    DBClient.Instance().Shutdown()
