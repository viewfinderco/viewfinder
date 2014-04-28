# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Utility to scan and cleanup the index table.
Usage:
# Look for all entries with index terms for old tables:
python -m viewfinder.backend.db.tools.clean_index_table --hash_key_prefixes='df:,la:,me:'

# Delete the entries.
python -m viewfinder.backend.db.tools.clean_index_table --hash_key_prefixes='df:,la:,me:' --delete=True

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import logging
import sys

from tornado import gen, options
from viewfinder.backend.base import main
from viewfinder.backend.db import db_client, vf_schema

options.define('hash_key_prefixes', default=[], multiple=True,
               help='hash_key prefixes to delete.')
options.define('delete', default=False,
               help='Actually delete entries.')

@gen.engine
def Scan(client, table, callback):
  """Scans an entire table.
  """
  found_entries = {}
  for prefix in options.options.hash_key_prefixes:
    found_entries[prefix] = 0
  deleted = 0
  last_key = None
  count = 0
  while True:
    result = yield gen.Task(client.Scan, table.name, attributes=None, limit=50, excl_start_key=last_key)
    count += len(result.items)

    for item in result.items:
      value = item.get('t', None)
      sort_key = item.get('k', None)
      if value is None or sort_key is None:
        continue
      for prefix in options.options.hash_key_prefixes:
        if value.startswith(prefix):
          logging.info('matching item: %r' % item)
          found_entries[prefix] += 1
          if options.options.delete:
            logging.info('deleting item: %r' % item)
            yield gen.Task(client.DeleteItem, table=table.name, key=db_client.DBKey(value, sort_key))
            deleted += 1
    if result.last_key:
      last_key = result.last_key
    else:
      break

  logging.info('Found entries: %r' % found_entries)
  logging.info('scanned %d items, deleted %d' % (count, deleted))
  callback()

@gen.engine
def RunDBA(callback):
  yield gen.Task(db_client.InitDB, vf_schema.SCHEMA, verify_or_create=True)

  table = vf_schema.SCHEMA.GetTable('Index')
  client = db_client.DBClient.Instance()

  yield gen.Task(Scan, client, table)

  callback()

if __name__ == '__main__':
  sys.exit(main.InitAndRun(RunDBA, init_db=False))
