# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Upgrades a table (or tables) in the database by scanning
sequentially through and updating each item. This relies on table
features defined in the Schema for each table. 'Features' are a
collection of rank-ordered tags, each with a corresponding alteration
to the data model. This may involve the addition of a new column, the
deprecation and removal of an existing column, and update to the
indexing algorithm, or some transformation of the data.

Each item's '_version' column is checked against the feature tags
defined for the table. All features with higher version numbers than
the item's current version are applied to the item in ordinal
succession. The item is then updated in the database.

Table names for the --tables flag are class names (i.e. no underscores).

Usage:

python -m viewfinder.backend.db.tools.upgrade [--tables=table0[,table1[,...]]]

"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import sys

from tornado import options, gen
from viewfinder.backend.base import main
from viewfinder.backend.db import db_client, db_import, versions, vf_schema
from viewfinder.backend.db.versions import Version
from viewfinder.backend.op.op_manager import OpManager
from viewfinder.backend.op.operation_map import DB_OPERATION_MAP

options.define('tables', default='', multiple=True,
               help='list of tables to upgrade; leave blank for all')
options.define('scan_limit', default=100,
               help='maximum number of items per scan')
options.define('upgrade_limit', default=None,
               help='maximum number of items to upgrade; do not specify to upgrade all')
options.define('verbose_test_run', default=True, help='set to False to mutate the database; '
               'otherwise runs in verbose test mode')
options.define('allow_s3_queries', default=None, type=bool,
               help='allow S3 queries in upgrades. Involves filling metadata from S3. '
               'Current use it for versions CREATE_MD5_HASHES and FILL_FILE_SIZES.')
options.define('excl_start_key', default=None, type=str,
               help='Start scanning from this key')
options.define('migrator', default=None, type=str,
               help='use the given migrator (a name from backend.db.versions) for each table processed')

@gen.engine
def UpgradeTable(client, table, callback):
  """Sequentially scans 'table', updating each scan item to trigger
  necessary upgrades.
  """
  upgrade_versions = []
  if options.options.migrator:
    upgrade_versions.append(getattr(versions, options.options.migrator))
  else:
    raise Exception('Upgrade requires the --migrator option.')
  if not db_import.GetTableClass(table.name):
    raise Exception('Upgrade is not supported on table %s.' % table.name)

  # Get full count of rows in the database for logging progress.
  describe = yield gen.Task(client.DescribeTable, table=table.name)
  logging.info('%s: (%d items)' % (table.name, describe.count))
  if options.options.excl_start_key:
    excl_start_key = db_client.DBKey(options.options.excl_start_key, None)
  else:
    excl_start_key = None

  # Loop while scanning in batches.  Scan will have already updated the
  # items if it was needed, so there is no need to call MaybeMigrate
  # again. If 'last_key' is None, the scan is complete.
  # Otherwise, continue with scan by supplying the last key as the exclusive start key.
  count = 0
  scan_params = {'client': client,
                 'col_names': None,
                 'limit': options.options.scan_limit,
                 'excl_start_key': excl_start_key}
  while True:
    items, last_key = yield gen.Task(db_import.GetTableClass(table.name).Scan, **scan_params)

    # Maybe migrate all items.
    yield [gen.Task(Version.MaybeMigrate, client, item, upgrade_versions)
           for item in items]

    logging.info('scanned next %d items from table %s' % (len(items), table.name))

    new_count = count + len(items)
    logging.info('processed a total of %d items from table %s' % (new_count, table.name))
    # Log a progress notification every 10% scanned.
    if describe.count and (new_count * 10) / describe.count > (count * 10) / describe.count:
      logging.info('%s: %d%%%s' %
                   (table.name, (new_count * 100) / describe.count,
                    '...' if new_count != describe.count else ''))
    if last_key is None:
      break
    elif options.options.upgrade_limit and new_count >= int(options.options.upgrade_limit):
      logging.info('exhausted --upgrade_limit=%s; exiting...' % options.options.upgrade_limit)
      break

    # Prepare for next iteration of loop.
    scan_params['excl_start_key'] = last_key
    count = new_count

  callback()

@gen.engine
def Upgrade(callback):
  """Upgrades each table in 'options.options.tables'."""
  if options.options.verbose_test_run:
    logging.info('***** NOTE: upgrade is being run in verbose testing mode; run with '
                 '--verbose_test_run=False once changes have been verified')
    Version.SetMutateItems(False)
  if options.options.allow_s3_queries is not None:
    logging.info('Setting allow_s3_queries=%r' % options.options.allow_s3_queries)
    Version.SetAllowS3Queries(options.options.allow_s3_queries)

  OpManager.SetInstance(OpManager(op_map=DB_OPERATION_MAP, client=db_client.DBClient.Instance()))

  tables = [vf_schema.SCHEMA.GetTable(n) for n in options.options.tables]
  if not tables:
    raise Exception('The --tables option has not been specified. ' +
                    'Tables to upgrade must be explicitly listed using this option.')
  yield [gen.Task(UpgradeTable, db_client.DBClient.Instance(), table) for table in tables]

  callback()

if __name__ == '__main__':
  sys.exit(main.InitAndRun(Upgrade))
