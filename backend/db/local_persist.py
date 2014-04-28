# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Persistence for local DB.

If --localdb_dir=<> is specified, then the in-memory python data is
persisted to disk every --localdb_sync_secs=<> seconds.

PERIODIC PERSISTENCE: the in-memory python data structures
representing the local database are persisted to disk every
--localdb_sync_secs with a corresponding fsync call. Each successive
sync requires that the previous sync has completed. The on-disk sync
are synchronous and all other processing in the server will come to a
halt during this period.  Each sync is written to the current run's
filename plus a '.sync' suffix. Upon completion and fsync, the .sync
file is renamed to the original in an atomic step.

SUCCESSIVE RUNS: upon restart the server looks in --localdb_dir for
the most recent, fully-written datastore persistence file. These files
are named "viewfinder.db.0". There are at most 5 recent versions of
the database, starting with no suffix and ending with ".4". On
startup, the current set of files are 'rolled'. The file with suffix
".4" is deleted; the file with suffix ".3" is moved to ".4",
etc. During a run, only the file with ".0" is updated.

A specific version of the database may be used instead of ".0" as the
current on a new run by specifying --localdb_version=<>.

Specify --localdb_reset to clear all old versions and start from
scratch.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import os
import cPickle as pickle
import shutil
import re
import time

from tornado import ioloop, options


class DBPersist(object):
  """Local datastore persistence for extended testing scenarios that
  must survive server restarts.
  """
  _BASE_NAME = 'server.db'

  def __init__(self, tables, table_schemas):
    """Sets up a periodic callback for sync operations."""
    self._tables = tables
    self._table_schemas = table_schemas
    self._is_dirty = False
    self._db_dir = options.options.localdb_dir
    if options.options.localdb_dir:
      logging.info('enabling local datastore persistence')
      self._sync_callback = ioloop.PeriodicCallback(
        self._DBSync, options.options.localdb_sync_secs * 1000)
      self._sync_callback.start()
      # Initialize output directory and files.
      self._InitFiles()

  def Shutdown(self):
    """Does a final sync on shutdown."""
    self._DBSync()

  def MarkDirty(self):
    """Called by the local datastore when its contents have been
    modified and another sync should be scheduled.
    """
    self._is_dirty = True

  def _InitFiles(self):
    """Initializes the output directory and output files. The selected
    previous version is copied to '<file>.0.sync', and versions from
    previous runs are rolled. '<file>.0.sync' is then renamed to
    '<file>.0'.
    """
    # Verify / create db output directory.
    try:
      files = os.listdir(self._db_dir)
    except:
      files = []
      os.makedirs(self._db_dir)

    if files and options.options.localdb_reset:
      logging.warning('resetting local datastore persistence')

    version_re = re.compile(r'%s.([0-9]+)$' % DBPersist._BASE_NAME)
    versions = dict()
    for f in files:
      match = version_re.match(f)
      if match:
        if options.options.localdb_reset:
          os.unlink(os.path.join(self._db_dir, f))
        else:
          versions[int(match.group(1))] = f

    # Do a hard-link shuffle to rotate files.
    def _GetPath(v):
      return os.path.join(self._db_dir, '%s.%d' % (DBPersist._BASE_NAME, v))

    use_version = options.options.localdb_version
    srcs = [_GetPath(use_version)]
    dsts = [_GetPath(0) + '.sync']
    for i in xrange(options.options.localdb_num_versions - 1, 0, -1):
      srcs.append(_GetPath(i - 1))
      dsts.append(_GetPath(i))
    for src, dst in zip(srcs, dsts):
      if os.access(dst, os.W_OK): os.unlink(dst)
      if os.access(src, os.W_OK): os.link(src, dst)

    self._cur_file = _GetPath(0)
    self._tmp_file = _GetPath(0) + '.sync'
    if os.access(self._cur_file, os.W_OK): os.unlink(self._cur_file)
    if os.access(self._tmp_file, os.W_OK):
      shutil.copyfile(self._tmp_file, self._cur_file)
      os.unlink(self._tmp_file)

    # Initialize the database from the source database file.
    if os.access(self._cur_file, os.W_OK):
      logging.info('initializing from persisted db file %s...' % self._cur_file)
      start_time = time.time()
      with open(self._cur_file, 'r') as f:
        (tables, schemas) = pickle.load(f)
        self._tables.update(tables)
        self._table_schemas.update(schemas)
      logging.info('initialization took %.4fs' % (time.time() - start_time))

  def _DBSync(self):
    """Periodic callback for data persistence.
    """
    if not self._is_dirty:
      return
    self._is_dirty = False
    assert self._cur_file, self._tmp_file

    logging.info('syncing local datastore...')
    start_time = time.time()
    with open(self._tmp_file, 'w') as f:
      pickle.dump((self._tables, self._table_schemas), f, pickle.HIGHEST_PROTOCOL)
      os.fsync(f)

    if os.access(self._cur_file, os.W_OK): os.unlink(self._cur_file)
    os.link(self._tmp_file, self._cur_file)
    assert os.access(self._cur_file, os.W_OK)

    logging.info('sync took %.4fs' % (time.time() - start_time))
