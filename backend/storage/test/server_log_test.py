# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Server log tests.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import os
import re
import sys
import tempfile
import time

from functools import partial
from tornado import options, testing
from viewfinder.backend.storage.object_store import ObjectStore, InitObjectStore
from viewfinder.backend.storage.file_object_store import FileObjectStore
from viewfinder.backend.storage.server_log import BatchingLogHandler, LogBatch, LogBatchPersistor, InitServerLog, FinishServerLog
from viewfinder.backend.base import util, counters
from viewfinder.backend.base.testing import async_test, BaseTestCase


class _BadObjectStore(FileObjectStore):
  """A file object store which simply does not return requests for
  puts. If 'fail_fast' is True, returns an error immediately.
  """
  def __init__(self, bucket_name, temporary=False, fail_fast=False):
    super(_BadObjectStore, self).__init__(bucket_name, temporary)
    self._fail_fast = fail_fast
    self._put_map = dict()

  def Put(self, key, value, callback):
    self._put_map[key] = value
    if self._fail_fast:
      raise Exception('failed to put key %s' % key)

  def GetPutValue(self, key):
    return self._put_map[key]


class _FakePersistor(object):
  """Fake log persistor - simply accepts batches without accepting them."""
  def __init__(self):
    self.batches = {}
    self._handlers = []

  def PersistLogBatch(self, batch):
    self.batches[batch.Key()] = batch

  def AddHandler(self, handler):
    """Add a handler to the list of handlers registered with this persistor."""
    if not handler in self._handlers:
      self._handlers.append(handler)

  def RemoveHandler(self, handler):
    """Remove a handler from the list of handlers registered with this persistor."""
    if handler in self._handlers:
      self._handlers.remove(handler)

  def close(self, callback=None):
    for h in list(self._handlers):
      h.close()
    if callback:
      callback()


class _BasicLogHandler(BatchingLogHandler):
  STORE_NAME = 'basic_store'

  def __init__(self, *args, **kwargs):
    super(_BasicLogHandler, self).__init__(*args, **kwargs)
    self.batch_no = 0

  def MakeBatch(self, buffer):
    self.batch_no += 1
    return LogBatch(buffer, self.STORE_NAME, 'basic', self.batch_no)


class LogBatchPersistorTestCase(BaseTestCase, testing.LogTrapTestCase):
  def setUp(self):
    options.options.fileobjstore = True
    super(LogBatchPersistorTestCase, self).setUp()
    InitObjectStore(temporary=True)

  def tearDown(self):
    super(LogBatchPersistorTestCase, self).tearDown()

  def testPersistor(self):
    """Basic test for a log persistor."""
    backup_dir = tempfile.mkdtemp()
    persistor = LogBatchPersistor(backup_dir=backup_dir)
    batches = [LogBatch('Log batch buffer 1A', ObjectStore.SERVER_LOG, 'test1', 'keyA'),
               LogBatch('Log batch buffer 2B', ObjectStore.SERVER_LOG, 'test2', 'keyB'),
               LogBatch('Log batch buffer 3C', ObjectStore.SERVER_LOG, 'test3', 'keyC'),
               LogBatch('Log batch buffer 4D', ObjectStore.USER_LOG, 'test4', 'keyD'),
               LogBatch('Log batch buffer 5E', ObjectStore.USER_LOG, 'test5', 'keyE')]

    for batch in batches:
      persistor.PersistLogBatch(batch)
    self._RunAsync(persistor.Wait)

    # No files should have been backed up.
    files = os.listdir(os.path.join(backup_dir, os.path.basename(sys.argv[0])))
    self.assertEqual(0, len(files))
    self._RunAsync(self._VerifyObjStoreBatches, batches)

  def testBadObjStore(self):
    """Tests backup storage in case the object store is down.  Also verifies close() method."""
    backup_dir = tempfile.mkdtemp()
    persistor = LogBatchPersistor(backup_dir=backup_dir)
    batches = [LogBatch('Log batch buffer 1A', ObjectStore.SERVER_LOG, 'test1', 'keyA'),
               LogBatch('Log batch buffer 2B', ObjectStore.SERVER_LOG, 'test2', 'keyB'),
               LogBatch('Log batch buffer 3C', ObjectStore.SERVER_LOG, 'test3', 'keyC'),
               LogBatch('Log batch buffer 4D', ObjectStore.USER_LOG, 'test4', 'keyD'),
               LogBatch('Log batch buffer 5E', ObjectStore.USER_LOG, 'test5', 'keyE')]

    oldStores = [ObjectStore.GetInstance(ObjectStore.SERVER_LOG),
                 ObjectStore.GetInstance(ObjectStore.USER_LOG)]
    ObjectStore.SetInstance(ObjectStore.SERVER_LOG,
                            _BadObjectStore(ObjectStore.SERVER_LOG_BUCKET,
                                            temporary=True, fail_fast=False))
    ObjectStore.SetInstance(ObjectStore.USER_LOG,
                            _BadObjectStore(ObjectStore.USER_LOG_BUCKET,
                                            temporary=True, fail_fast=False))

    # Cut the timeout allowed for flushing buffers on close to something small.
    persistor._CLOSE_TIMEOUT_SECS = 0.100
    for batch in batches:
      persistor.PersistLogBatch(batch)
    self._RunAsync(persistor.close)

    self._VerifyBackupBatches(backup_dir, batches)

    # Set a functional file object store instance and verify that it
    # restores the pending server logs.
    ObjectStore.SetInstance(ObjectStore.SERVER_LOG,
                            oldStores[0])
    ObjectStore.SetInstance(ObjectStore.USER_LOG,
                            oldStores[1])
    persistor = LogBatchPersistor(backup_dir=backup_dir)
    self._RunAsync(persistor.Wait)

    self._RunAsync(self._VerifyObjStoreBatches, batches)

  def testRestoreTimeout(self):
    """Verifies the persistor will reattempt failed object store writes after a timeout"""
    backup_dir = tempfile.mkdtemp()
    persistor = LogBatchPersistor(backup_dir=backup_dir)
    batches = [LogBatch('Log batch buffer 1A', ObjectStore.SERVER_LOG, 'test1', 'keyA'),
               LogBatch('Log batch buffer 2B', ObjectStore.SERVER_LOG, 'test2', 'keyB'),
               LogBatch('Log batch buffer 3C', ObjectStore.SERVER_LOG, 'test3', 'keyC')]
    persistor._RESTORE_INTERVAL_SECS = 0.100

    # The "bad" object store which does nothing with puts.
    oldStore = ObjectStore.GetInstance(ObjectStore.SERVER_LOG)
    ObjectStore.SetInstance(ObjectStore.SERVER_LOG,
                            _BadObjectStore(ObjectStore.SERVER_LOG_BUCKET,
                                            temporary=True, fail_fast=True))
    for batch in batches:
      persistor.PersistLogBatch(batch)

    self.io_loop.add_callback(partial(self._VerifyBackupBatches, backup_dir, batches))

    # Reinstate the "good" object store.
    ObjectStore.SetInstance(ObjectStore.SERVER_LOG, oldStore)
    self._RunAsync(self.io_loop.add_timeout, time.time() + 0.200)
    self._RunAsync(self._VerifyObjStoreBatches, batches)

  def _SortBatchesByStore(self, batches):
    batches_by_store = {}
    for batch in batches:
      key = batch.store_name
      store_batches = batches_by_store.setdefault(key, [])
      store_batches.append(batch)

    return batches_by_store

  def _VerifyObjStoreBatches(self, exp_batches, callback):
    def _OnGetBatch(exp_batch, cb, buffer):
      self.assertEqual(exp_batch.buffer, buffer)
      cb()

    def _OnListKeys(store, batches, cb, keys):
      self.assertEqual(len(batches), len(keys))
      with util.Barrier(cb) as b2:
        for batch in batches:
          self.assertIn(batch.Key(), keys)
          store.Get(batch.Key(), partial(_OnGetBatch, batch, b2.Callback()))

    batches_by_store = self._SortBatchesByStore(exp_batches)
    with util.Barrier(callback) as b:
      for store in batches_by_store.keys():
        batches = batches_by_store[store]
        store = ObjectStore.GetInstance(store)
        store.ListKeys(partial(_OnListKeys, store, batches, b.Callback()))

  def _VerifyBackupBatches(self, backup_dir, exp_batches):
    batches_by_store = self._SortBatchesByStore(exp_batches)
    dir = os.path.join(backup_dir, os.path.basename(sys.argv[0]))
    store_dirs = os.listdir(dir)

    self.assertEqual(len(batches_by_store.keys()), len(store_dirs))
    for store in batches_by_store.keys():
      self.assertIn(store, store_dirs)
      store_dir = os.path.join(dir, store)
      batches = batches_by_store[store]
      self.assertEqual(len(batches), len(os.listdir(store_dir)))
      for batch in batches:
        file = os.path.join(store_dir, batch.FileSystemKey())
        self.assertTrue(os.path.exists(file))
        self.assertTrue(os.path.isfile(file))
        with open(file, 'r') as f:
          buffer = f.read()
          self.assertEqual(batch.buffer, buffer)


class BatchingLogHandlerTestCase(BaseTestCase, testing.LogTrapTestCase):
  def setUp(self):
    super(BatchingLogHandlerTestCase, self).setUp()
    self._persistor = _FakePersistor()
    LogBatchPersistor.SetInstance(self._persistor)

  def testBatching(self):
    """Tests that the server log writes to object store."""
    basic_log = _BasicLogHandler(max_buffer_bytes=100)
    record = logging.makeLogRecord({'level': logging.INFO, 'msg': 'test'})
    basic_log.emit(record)
    basic_log.flush()
    self._RunAsync(self._VerifyLog, ['test'])

  def testBadLogMessages(self):
    """Tests log messages with both 8-bit byte strings and unicode."""
    basic_log = _BasicLogHandler(max_buffer_bytes=100)
    record = logging.makeLogRecord({'level': logging.INFO, 'msg': '\x80abc'})
    basic_log.emit(record)
    record = logging.makeLogRecord({'level': logging.INFO, 'msg': u'\x80abc'})
    basic_log.emit(record)
    basic_log.flush()

  def testMultipleFlushes(self):
    """Tests multiple flushes."""
    basic_log = _BasicLogHandler(flush_interval_secs=0.100)
    for i in xrange(8):
      record = logging.makeLogRecord({'level': logging.INFO, 'msg': 'test%d' % i})
      basic_log.emit(record)
      basic_log.flush()
    self._RunAsync(self._VerifyLog, ['test%d' % i for i in range(8)])

  def testMaxBytesFlush(self):
    """Tests that the server log flushes based on maximum bytes written."""
    basic_log = _BasicLogHandler(max_buffer_bytes=100)
    msg = 'test' * 100
    record = logging.makeLogRecord({'level': logging.INFO, 'msg': msg})
    basic_log.emit(record)
    self._RunAsync(self._VerifyLog, [msg])

  def testTimeoutFlush(self):
    """Tests that the server log flushes after maximum flush interval."""
    basic_log = _BasicLogHandler(flush_interval_secs=0.100)
    record = logging.makeLogRecord({'level': logging.INFO, 'msg': 'test'})
    basic_log.emit(record)
    self._RunAsync(self.io_loop.add_timeout, time.time() + 0.150)
    self._RunAsync(self._VerifyLog, ['test'])

  def testFinishServerLog(self):
    """Verify that 'close()' is called on the server handler when the persistor
    is closed.
    """
    persistor = _FakePersistor()
    InitServerLog(persistor)
    self.assertEqual(2, len(persistor._handlers))

    basic_handler = _BasicLogHandler()
    basic_handler.setLevel(logging.INFO)
    with basic_handler.LoggingContext():
      self.assertEqual(3, len(persistor._handlers))
      self.assertEqual(0, len(persistor.batches))
      logging.info('Test Message')

    self.assertEqual(3, len(persistor._handlers))
    self._RunAsync(FinishServerLog)
    self.assertEqual(0, len(persistor._handlers))
    self.assertEqual(2, len(persistor.batches))

  def testFinishServerLogWithErrors(self):
    """Verify that the error log handler properly batches.
    """
    persistor = _FakePersistor()
    InitServerLog(persistor)
    self.assertEqual(2, len(persistor._handlers))

    basic_handler = _BasicLogHandler()
    basic_handler.setLevel(logging.INFO)
    with basic_handler.LoggingContext():
      self.assertEqual(3, len(persistor._handlers))
      self.assertEqual(0, len(persistor.batches))
      logging.error('Test Error')

    self.assertEqual(3, len(persistor._handlers))
    self._RunAsync(FinishServerLog)
    self.assertEqual(0, len(persistor._handlers))
    self.assertEqual(3, len(persistor.batches))

  def _VerifyLog(self, exp_msgs, callback):
    """Verifies that there are len('exp_msg') batches stored
    and that each contains the expected message as contents.
    """
    def _DoVerify():
      batches = self._persistor.batches
      self.assertEqual(len(batches), len(exp_msgs))
      for key, msg in zip(sorted(batches.keys()), exp_msgs):
        value = batches[key].buffer
        regexp = re.compile('\[pid:[0-9]+\] .*:[0-9]+: %s' % msg)
        self.assertTrue(regexp.search(value) is not None, '%s not found in %s' % (msg, value))

      callback()

    self.io_loop.add_callback(_DoVerify)


class ServerLogHandlerTestCase(BaseTestCase, testing.LogTrapTestCase):
  def testErrorCounters(self):
    """Verify that error-counting performance counters are working correctly.
    These performance counters are implemented as a log filter.
    """
    meter = counters.Meter(counters.counters.viewfinder.errors)
    InitServerLog(_FakePersistor())

    def _CheckCounters(expected_errors, expected_warnings):
      sample = meter.sample()
      self.assertEqual(expected_errors, sample.viewfinder.errors.error)
      self.assertEqual(expected_warnings, sample.viewfinder.errors.warning)

    _CheckCounters(0, 0)
    old_level = logging.getLogger().level
    logging.getLogger().setLevel(logging.DEBUG)
    logging.critical('Critical')
    logging.error('Error1')
    logging.warning('Warning1')
    logging.warning('Warning2')
    logging.getLogger().setLevel(old_level)
    self._RunAsync(FinishServerLog)
    _CheckCounters(2, 2)
    _CheckCounters(0, 0)
