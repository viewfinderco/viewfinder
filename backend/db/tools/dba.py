# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Utility to manage high-level data objects. This is in
contrast to dba.py, which directly accesses and mutates
DynamoDB rows. Direct mutation is dangerous as it skirts
the layers observed by the Python backend/db/* classes,
which properly update secondary indexes and auxillary
tables such as Notification.

See raw_dba.py for notes on quoting keys and attributes.


Usage:

--op specifies the operation:

  SIMPLE OPERATIONS:

  - query: query a range for a table
      --hash_key=<hash_key> [--start_key=<start_key] [--end_key=<end_key>]
  - update: update an item in a table
      --hash_key=<hash_key> [--range_key=<range_key] --attributes=<attributes-list>

  COMPLEX OPERATIONS:

  - None


python -m viewfinder.backend.db.tools.dba --op=<op> [--table=<table>] \
    [--hash_key=<hash-key>] [--range_key=<range-key>]
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import pprint
import sys

from functools import partial
from tornado import options
from viewfinder.backend.base import main
from viewfinder.backend.db import db_client, db_import, vf_schema
from viewfinder.backend.db.tools.util import AttrParser

options.define('table', default=None, help='table name')
options.define('op', default=None, help='operation on database entities')
options.define('user_id', default=None, help='user id for operation, if applicable')
options.define('hash_key', default=None, help='primary hash key for item-level ops')
options.define('range_key', default=None, help='primary range key for item-level ops')
options.define('start_key', default=None, help='start range key for query')
options.define('end_key', default=None, help='end range key for query')
options.define('limit', default=None, help='maximum row limit on queries')
options.define('attributes', default=None, help='value attributes pairs (attr0=value0,attr1=value1,...) '
               'can be quoted strings. Values are eval\'d')
options.define('col_names', default=None, multiple=True, help='column names to print when querying items')


def QueryRange(client, table, cls, key, range_desc, callback):
  """Queries the contents of a range identified by --hash_key.
  """
  def _OnQuery(retry_cb, count, items):
    for item in items:
      pprint.pprint(item)
    if len(items) == 100:
      retry_cb(items[-1].GetKey(), count + len(items))
    else:
      return callback('queried %d items' % count)

  def _Query(last_key=None, count=0):
    cls.RangeQuery(client, key.hash_key, range_desc, limit=100,
                   col_names=(options.options.col_names or None),
                   callback=partial(_OnQuery, _Query, count),
                   excl_start_key=last_key)

  _Query()


def RunDBA(callback):
  """Runs op on each table listed in --tables."""
  client = db_client.DBClient.Instance()
  op = options.options.op

  table = None
  if options.options.table:
    table = vf_schema.SCHEMA.GetTable(options.options.table)
    assert table, 'unrecognized table name: %s' % options.options.table
    cls = db_import.GetTableClass(table.name)

  key = None
  if options.options.hash_key and options.options.range_key:
    assert table.range_key_col
    key = db_client.DBKey(eval(options.options.hash_key), eval(options.options.range_key))
  elif options.options.hash_key:
    assert not table.range_key_col
    key = db_client.DBKey(eval(options.options.hash_key), None)

  start_key = eval(options.options.start_key) if options.options.start_key else None
  end_key = eval(options.options.end_key) if options.options.end_key else None
  range_desc = None
  if start_key and end_key:
    range_desc = db_client.RangeOperator([start_key, end_key], 'BETWEEN')
  elif start_key:
    range_desc = db_client.RangeOperator([start_key], 'GT')
  elif end_key:
    range_desc = db_client.RangeOperator([end_key], 'LT')

  user_id = None
  if options.options.user_id:
    user_id = eval(options.options.user_id)

  limit = None
  if options.options.limit:
    limit = eval(options.options.limit)

  if options.options.attributes:
    parser = AttrParser(table)
    attrs = parser.Run(options.options.attributes)
    if table and key:
      attrs[table.hash_key_col.name] = key.hash_key
      if key.range_key:
        attrs[table.range_key_col.name] = key.range_key
    logging.info('attributes: %s' % attrs)

  def _OnOp(*args, **kwargs):
    if args:
      logging.info('positional result args: %s' % pprint.pformat(args))
    if kwargs:
      logging.info('keyword result args: %s' % pprint.pformat(kwargs))
    callback()

  if op in ('query', 'update'):
    assert table, 'no table name specified for operation'
  if op in ('query'):
    assert table.range_key_col, 'Table %s is not composite' % table.name

  # Run the operation
  logging.info('executing %s' % op)
  if op == 'query':
    QueryRange(client, table, cls, key, range_desc, _OnOp)
  elif op == 'update':
    o = cls()
    o.UpdateFromKeywords(**attrs)
    o.Update(client, _OnOp)
  else:
    raise Exception('unrecognized op: %s' % op)


if __name__ == '__main__':
  sys.exit(main.InitAndRun(RunDBA))
