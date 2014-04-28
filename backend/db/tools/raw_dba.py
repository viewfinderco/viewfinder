# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Utility to list, create, delete & describe tables.

Usage:

--op specifies the database operation:
  create
  REALLY_DELETE_TABLE
  list
  describe
  delete-item
  get-item
  update-item
  delete-range
  scan
  query

Hash key and range key (--hash_key, --range_key) are eval'd. This means
that string values should be quoted. An example with a string as hash
key and an integer as range key:

--hash_key="'Email:spencer.kimball@emailscrubbed.com'" --range_key=5

Attributes for update-item are specified with the actual column names (NOT keys!).
This is a comma-separated list of column-name/colum-value pairs. Each column value
will be eval'd in python--this allows sets to be specified, as well as None, etc.

The quoting from the command line can be tricky. Here's an example of how to get
it to work. The trick is to put double quote around the entire comma-separated
list and then escape any double-quoted attribute values inside:

--attributes="col_names=\"set([u'photo_id', u'episode_id', u'timestamp', u'placemark', u'_version', u'client_data', u'location', u'content_type', u'aspect_ratio', u'user_id'])\",labels=\"set([u'+owned'])\",_version=0,user_id=7,user_update_id=528,photo_id=\"'pgBXxbGuh-F'\""


python -m viewfinder.backend.db.tools.raw_dba \
    [--tables=table0[,table1[,...]]] [--op=<op>]

"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import pprint
import sys

from functools import partial
from tornado import options
from viewfinder.backend.base import main, util
from viewfinder.backend.db import db_client, vf_schema
from viewfinder.backend.db.tools.util import AttrParser

options.define('tables', default=None, multiple=True,
               help='list of tables to upgrade; "ALL" for all tables')
options.define('verify_or_create', default=True,
               help='verify or create schema on database')
options.define('op', default='list',
               help='DBA operation on tables; one of (create, delete, list, describe)')
options.define('hash_key', default=None, help='primary hash key for item-level ops')
options.define('range_key', default=None, help='primary range key for item-level ops')
options.define('attributes', default=None, help='value attributes pairs (attr0=value0,attr1=value1,...) '
               'can be quoted strings. Values are eval\'d')
options.define('col_names', default=None, multiple=True, help='column names to print when querying items')


def Scan(client, table, callback):
  """Scans an entire table.
  """
  def _OnScan(retry_cb, count, result):
    for item in result.items:
      if options.options.col_names:
        item = dict([(k, v) for k, v in item.items() if k in options.options.col_names])
      pprint.pprint(item)
    if result.last_key:
      retry_cb(result.last_key, count + len(result.items))
    else:
      return callback('scanned %d items' % (count + len(result.items)))

  def _Scan(last_key=None, count=0):
    client.Scan(table.name, partial(_OnScan, _Scan, count),
                None, limit=50, excl_start_key=last_key)

  _Scan()

def QueryRange(client, table, callback):
  """Queries the contents of a range identified by --hash_key.
  """
  def _OnQuery(retry_cb, count, result):
    for item in result.items:
      if options.options.col_names:
        item = dict([(k, v) for k, v in item.items() if k in options.options.col_names])
      pprint.pprint(item)
    if result.last_key:
      retry_cb(result.last_key, count + len(result.items))
    else:
      return callback('queried %d items' % count)

  def _Query(last_key=None, count=0):
    client.Query(table.name, options.options.hash_key, None, partial(_OnQuery, _Query, count),
                 None, limit=100, excl_start_key=last_key)

  _Query()

def DeleteRange(client, table, callback):
  """Deletes all items in the range identified by --hash_key.
  """
  def _OnQuery(retry_cb, count, result):
    count += len(result.items)
    if not result.last_key:
      result_cb = partial(callback, 'deleted %d items' % count)
    else:
      logging.info('deleting next %d items from %s' % (len(result.items), table.name))
      result_cb = partial(retry_cb, result.last_key, count)
    with util.Barrier(result_cb) as b:
      for item in result.items:
        key = db_client.DBKey(options.options.hash_key, item[table.range_key_col.key])
        client.DeleteItem(table=table.name, key=key, callback=b.Callback())

  def _Query(last_key=None, count=0):
    client.Query(table.name, options.options.hash_key, None, partial(_OnQuery, _Query, count),
                 None, limit=100, excl_start_key=last_key)

  _Query()


def RunOpOnTable(client, table, op, callback):
  """Runs the specified op on the table."""
  if options.options.hash_key and options.options.range_key:
    key = db_client.DBKey(eval(options.options.hash_key), eval(options.options.range_key))
  elif options.options.hash_key:
    key = db_client.DBKey(eval(options.options.hash_key), None)
  else:
    key = None

  def _OnOp(result):
    logging.info('%s: %s' % (table.name, repr(result)))
    callback()

  logging.info('executing %s on table %s' % (op, table.name))
  if op == 'create':
    client.CreateTable(table=table.name, hash_key_schema=table.hash_key_schema,
                       range_key_schema=table.range_key_schema,
                       read_units=table.read_units, write_units=table.write_units,
                       callback=_OnOp)
  elif op == 'describe':
    client.DescribeTable(table=table.name, callback=_OnOp)
  elif op == 'REALLY_DELETE_TABLE':
    client.DeleteTable(table=table.name, callback=_OnOp)
  elif op == 'get-item':
    client.GetItem(table=table.name, key=key, callback=_OnOp,
                   attributes=options.options.col_names)
  elif op == 'update-item':
    parser = AttrParser(table, raw=True)
    attrs = parser.Run(options.options.attributes)
    client.UpdateItem(table=table.name, key=key, callback=_OnOp,
                      attributes=attrs, return_values='ALL_NEW')
  elif op == 'delete-item':
    client.DeleteItem(table=table.name, key=key, callback=_OnOp,
                      return_values='ALL_OLD')
  elif op == 'delete-range':
    assert table.range_key_col, 'Table %s is not composite' % table.name
    DeleteRange(client, table, _OnOp)
  elif op == 'query':
    assert table.range_key_col, 'Table %s is not composite' % table.name
    QueryRange(client, table, _OnOp)
  elif op == 'scan':
    Scan(client, table, _OnOp)
  else:
    raise Exception('unrecognized op: %s; ignoring...' % op)


def RunDBA(callback):
  """Runs op on each table listed in --tables."""
  logging.warning('WARNING: this tool can modify low-level DynamoDB tables and '
                  'attributes and should be used with caution. For example, '
                  'modifying a photo or adding a label directly will '
                  'not update secondary indexes nor create user updates.')

  def _OnInit(verified_schema):
    if options.options.op == 'list':
      def _OnList(result):
        logging.info(result)
        callback()
      db_client.DBClient.Instance().ListTables(callback=_OnList)
    else:
      if options.options.tables == 'ALL':
        tables = vf_schema.SCHEMA.GetTables()
      else:
        tables = [vf_schema.SCHEMA.GetTable(n) for n in options.options.tables]
      assert tables, 'no tables were specified'

      with util.Barrier(callback) as b:
        for table in tables:
          RunOpOnTable(db_client.DBClient.Instance(), table, options.options.op, b.Callback())

  db_client.InitDB(vf_schema.SCHEMA, callback=_OnInit,
                   verify_or_create=options.options.verify_or_create)


if __name__ == '__main__':
  sys.exit(main.InitAndRun(RunDBA, init_db=False))
