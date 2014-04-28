# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Server log handling.

 - ServerLogHandler: buffers server logs up to a maximum buffer size or
     outstanding time before sending to the server log object store.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import datetime
import logging
import os
import socket
import sys
import time

from collections import deque
from contextlib import contextmanager
from functools import partial
from logging import Filter, Handler
from StringIO import StringIO
from tornado import gen, options, stack_context
from tornado.ioloop import IOLoop
from viewfinder.backend.base import logging_utils, util, ami_metadata, counters, process_util
from viewfinder.backend.storage.object_store import ObjectStore

options.define('server_log_max_buffer_bytes', 1 << 20,
               help='maximum bytes buffered before a flush is forced')
options.define('server_log_flush_interval_secs', 60 * 60,
               help='seconds between log flushes')
options.define('error_log_flush_interval_secs', 2 * 60,
               help='seconds between log flushes')
options.define('server_log_backup_dir', '~/local/server_log_backup',
               help='backup location in case object store is down')


# Performance counters for warnings and errors.
_warning_count = counters.define_delta('viewfinder.errors.warning', 'Count of logged warnings during sample period.')
_error_count = counters.define_delta('viewfinder.errors.error', 'Count of logged errors during sample period.')


class LogBatch(object):
  """A log batch is simply a buffer of log records associated with an object
  store and a key.  Log batches may be sent to different object stores depending
  on the context from which they are collected.
  """
  def __init__(self, buffer, store_name, *keyparts):
    """Create a new batch for the given buffer which will be saved in the object
    store with the given name.  They key within the object store will be synthesized
    using any additional positional arguments.
    """
    self.buffer = buffer
    self.store_name = store_name
    assert len(keyparts) > 0, 'Must provide at least one parameter to create a batch key.'
    keyparts = [str(part) for part in keyparts]
    for part in keyparts:
      assert '_' not in keyparts
      assert '/' not in keyparts

    self.keyparts = keyparts

  def Key(self):
    """Synthesize a string key for this batch which will be used to identify this batch
    in the object store.
    """
    return '/'.join(self.keyparts)

  def FileSystemKey(self):
    """Synthesize a string key for this batch which will be used to identify this batch
    in a local file system, which may have different character requirements.
    """
    return '_'.join(self.keyparts)

  @classmethod
  def DecodeKey(cls, key):
    """Decode the key from a previously created log batch."""
    return key.split('/')

  @classmethod
  def DecodeFileSystemKey(cls, key):
    """Decode the file system key from a previously created log batch."""
    return key.split('_')


class BatchingLogHandler(Handler):
  """A log handler which maintains buffers bytes over a flush interval, after
  which the data is sent to the server log object store.  The exact object store
  and key details are left to subclasses of BatchingLogHandler.
  """

  def __init__(self, max_buffer_bytes=None, flush_interval_secs=None, persistor=None):
    """Initialize a new BatchingLogHandler.  max_buffer_bytes determines the maximum size of each batch,
    while flush_interval_secs determines the maximum amount of time that a batch can be active before
    persisting it.

    'persistor' should be a LogBatchPersistor - each completed batch from this handler will be sent to this
    persistor upon completion.  If no persistor is specified, then the default instance of LogBatchPersistor
    will be used.  This log hander will also automatically register itself with the persistor - this is
    necessary for a shutdown scenario.
    """
    super(BatchingLogHandler, self).__init__()
    self._max_buffer_bytes = max_buffer_bytes or options.options.server_log_max_buffer_bytes
    self._flush_interval_secs = flush_interval_secs or options.options.server_log_flush_interval_secs
    self._persistor = persistor or LogBatchPersistor.Instance()
    self._buffer = None
    self._inner_handler = None
    self._start_timestamp = None
    self._flush_timeout = None
    self._closing = False
    self._Register()

  def flush(self):
    """Flush this handler by saving the current buffer as a complete batch and
    beginning a new batch.
    """
    if self._closing:
      return

    with _DisableLoggingContext(self):
      if self._flush_timeout and IOLoop.current() is not None:
        IOLoop.current().remove_timeout(self._flush_timeout)
        self._flush_timeout = None

      self._CutBatch()

  def emit(self, record):
    """Emits the specified record by writing it to the in-memory log
    handler. If the size of the in-memory handler's buffer exceeds
    _max_buffer_bytes, flushes it to the object store.
    """
    if self._closing:
      return

    if self._buffer is None:
      self._NewBatch()

    self._inner_handler.emit(record)
    if self._buffer.tell() >= self._max_buffer_bytes:
      self.flush()
    elif not self._flush_timeout:
      deadline = self._start_timestamp + self._flush_interval_secs
      with stack_context.NullContext():
        self._flush_timeout = IOLoop.current().add_timeout(deadline, self.flush)

  @contextmanager
  def LoggingContext(self, logger=None):
    """Returns a ContextManager that adds this handler to the given logger when
    entered, removing it upon exit.  If no logger is given, the default logger
    from logging.getLogger will be used.
    """
    try:
      logger = logger or logging.getLogger()
      logger.addHandler(self)
      yield
    finally:
      logger.removeHandler(self)

  def LoggingStackContext(self, logger=None):
    """Returns a tornado StackContext which adds this handler to the given logger when
    entered, removing it upon exit.  If no logger is given, the default logger
    from logging.getLogger will be used.
    """
    return stack_context.StackContext(partial(self.LoggingContext, logger))

  def close(self, save_batch=True):
    """Close this handler, persisting any outstanding logs as a new batch.  The batch can
    be suppressed by passing save_batch=False to this method.
    """
    super(BatchingLogHandler, self).close()
    self._closing = True
    with _DisableLoggingContext(self):
      if save_batch:
        self._CutBatch()
      self._Unregister()

  def MakeBatch(self, buffer):
    """Method which wraps a buffer into a log batch in order to persist it.  This
    method is intended to be overridden in derived classes in order to properly
    generate the keys for different log types.
    """
    raise NotImplementedError('Must implement MakeBatch in a subclass.')

  def _CutBatch(self):
    """Generates a logging batch from the current log buffer and sends it to the persistor
    in order to be saved.
    """
    if self._buffer is not None:
      batch = None
      try:
        log_buf = self._buffer.getvalue()
        if type(log_buf) is unicode:
          import tornado.escape
          log_buf = tornado.escape.utf8(log_buf)
        batch = self.MakeBatch(log_buf)
      except:
        logging.exception('Failure to generate log batch!')
        pass

      if batch:
        try:
          self._persistor.PersistLogBatch(batch)
        except:
          logging.exception('Failure to persist log batch!')
          pass

      self._buffer.close()
      self._buffer = None
      self._inner_handler = None

  def _NewBatch(self):
    """Begins a new log batch."""
    self._buffer = StringIO()
    self._inner_handler = logging.StreamHandler(self._buffer)
    self._inner_handler.setLevel(logging.INFO)
    self._inner_handler.setFormatter(logging_utils.FORMATTER)
    self._start_timestamp = time.time()

  def _Register(self):
    """Registers this handler with its persistor."""
    self._persistor.AddHandler(self)

  def _Unregister(self):
    """Unregisters this handler from its persistor."""
    self._persistor.RemoveHandler(self)

  def _FormattedTime(self, timestamp=None):
    timestamp = timestamp or self._start_timestamp
    return datetime.datetime.fromtimestamp(timestamp).isoformat()

  def _FormattedDate(self, timestamp=None):
    timestamp = timestamp or self._start_timestamp
    return datetime.date.fromtimestamp(timestamp).isoformat()


class ServerLogHandler(BatchingLogHandler):
  """Subclass of BatchingServerLog designed to capture general logs for a server
  instance.  Batches are stored in the SERVER_LOG object store, and the key is a
  combination of a current timestamp, the instance name and the process id.
  """
  SERVER_LOG_CATEGORY = 'full'

  def __init__(self, *args, **kwargs):
    super(ServerLogHandler, self).__init__(*args, **kwargs)
    self._pid = os.getpid()
    # Underscores are used as delimited in the local file name. They are then turned into '/' for object store keys.
    self._jobname = process_util.GetProcessName().replace('_', '-')

  def MakeBatch(self, buffer):
    """Constructs a server log batch for the given buffer.  Batches are destined
    for the server log object store, with a key derived from a current timestamp
    and process information.
    """
    try:
      from viewfinder.backend.base import main
      instance_id = ami_metadata.GetAMIMetadata()['meta-data/instance-id']
    except (KeyError, TypeError):
      # According to RFC 952, hostnames cannot contain underscore characters.
      instance_id = socket.gethostname()

    return LogBatch(buffer, ObjectStore.SERVER_LOG, self._jobname, self.SERVER_LOG_CATEGORY,
                    self._FormattedTime(), instance_id, self._pid)


class ErrorLogHandler(ServerLogHandler):
  """Subclass of ServerLogHandler designed to capture only error types.  There should
  only be one instance of this handler type, as it is also responsible for incrementing
  performance counters related to errors.
  """
  SERVER_LOG_CATEGORY = 'error'

  def __init__(self, *args, **kwargs):
    kwargs.setdefault('flush_interval_secs', options.options.error_log_flush_interval_secs)
    super(ErrorLogHandler, self).__init__(*args, **kwargs)

  def emit(self, record):
    """Checks the level of record.  Records of level WARNING or above will be noted in performance
    counters, which are used for monitoring purposes.
    """
    super(ErrorLogHandler, self).emit(record)
    if self._closing:
      return

    if record.levelno >= logging.ERROR:
      _error_count.increment()
    elif record.levelno >= logging.WARNING:
      _warning_count.increment()


class UserRequestLogHandler(BatchingLogHandler):
  """Subclass of BatchingLogHandler designed to capture logs for a specific user request.
  Log key format is [userId]/[date]/req/[request_type]/[timestamp].
  """
  def __init__(self, user_id, request_type, *args, **kwargs):
    super(UserRequestLogHandler, self).__init__(*args, **kwargs)
    self._user_id = user_id
    self._request_type = request_type.replace('_', '-')

  def MakeBatch(self, buffer):
    return LogBatch(buffer, ObjectStore.USER_LOG,
                    self._user_id, self._FormattedDate(), 'req', self._request_type,
                    self._FormattedTime())


class UserOperationLogHandler(BatchingLogHandler):
  """Subclass of BatchingLogHandler designed to capture logs for a specific user operation.
  Log key format is [userId]/[date]/op/[opId]/[retry-num].
  """
  def __init__(self, operation, *args, **kwargs):
    super(UserOperationLogHandler, self).__init__(*args, **kwargs)
    self._user_id = operation.user_id
    self._op_id = operation.operation_id
    self._op_timestamp = operation.timestamp
    self._op_retry = operation.attempts
    self._op_method = operation.method.replace('_', '')

  def MakeBatch(self, buffer):
    return LogBatch(buffer, ObjectStore.USER_LOG,
                    self._user_id, self._FormattedDate(self._op_timestamp), 'op',
                    self._op_method, self._op_id, self._op_retry)

class LogBatchPersistor(object):
  """ Class which persists log batches to object storage in a reliable fashion.  A completed batch of
  logs can simply be passed to the PersistLogBatch() method.

  This class will immediately attempt to upload the log batch to the object store indicated in
  the batch - if this attempt fails, the log will instead be saved to the local filesystem.
  This class will attempt to re-upload log batches from the local filesystem every ten minutes.
  """

  _CLOSE_TIMEOUT_SECS = 5
  """The maximum time before giving up on on-flight log batch puts after a call to ServerLogHandler.close().
  """

  _RESTORE_INTERVAL_SECS = 10 * 60  # 10 minutes
  """The interval after which the server reattempts to push any server logs
  which failed to be written to the object store.
  """

  def __init__(self, backup_dir=None):
    """'backup_dir' is augmented using the process name (as taken from sys.argv[0])."""
    self._proc_name = os.path.basename(sys.argv[0])
    self._backup_dir = os.path.join(backup_dir or os.path.expanduser(options.options.server_log_backup_dir),
                                    self._proc_name)
    self._in_flight = {}
    self._handlers = []
    self._wait_callbacks = deque()
    self._restore_timeout = None
    self._closing = False
    self._SetRestoreTimeout(0)

  def PersistLogBatch(self, batch):
    """Relibably persists the given LogBatch to object storage.  If the batch cannot immediately
    be uploaded to object storage, it is instead persisted to the local filesystem and will be
    uploaded to storage at a later time.
    """
    self._PersistToObjStore(batch)

  def AddHandler(self, handler):
    """Add a handler to the list of handlers registered with this persistor."""
    if not handler in self._handlers:
      self._handlers.append(handler)

  def RemoveHandler(self, handler):
    """Remove a handler from the list of handlers registered with this persistor."""
    if handler in self._handlers:
      self._handlers.remove(handler)

  def close(self, callback=None):
    """Closes this LogBatchPersistor. Any extant, in-flight puts to the object store are persisted
    to the backup directory immediately.
    """
    timeout = None
    callback = stack_context.wrap(callback)
    self._closing = True

    def _OnFlush():
      if timeout is not None:
        IOLoop.current().remove_timeout(timeout)
      if self._in_flight:
        logging.warning('unflushed server log buffers; writing to backup dir')
        for batch in self._in_flight.values():
          self._PersistToBackup(batch)
      self._in_flight.clear()
      if callback:
        callback()

    if IOLoop.current() is not None:
      # IOLoop is still available.
      if self._restore_timeout:
        IOLoop.current().remove_timeout(self._restore_timeout)
        self._restore_timeout = None

      # Close all registered handlers - this should cut a batch from all of them.
      for h in self._handlers:
        h.close()

      # Begin countdown for log persisting.
      deadline = time.time() + self._CLOSE_TIMEOUT_SECS
      timeout = IOLoop.current().add_timeout(deadline, _OnFlush)

      # Register with Wait, which will let us exit more quickly if persisting completes
      # before the deadline.
      self.Wait(_OnFlush)
    else:
      # IOLoop is already closed.
      _OnFlush()

  def Wait(self, callback):
    """Registers a callback to be invoked when all currently in-flight logs have been
    successfully persisted to either the object store or local storage.  Intended
    only for use in testing.
    """
    if self._in_flight:
      callback = stack_context.wrap(callback)
      self._wait_callbacks.append(callback)
    else:
      callback()

  def _PersistToObjStore(self, batch, restore=False):
    """Writes the given log batch to the object store. The 'restore'
    parameter indicates that this is an attempt to restore the log, in
    which case we do not rewrite it to backup on a subsequent failure.

    If there are callbacks waiting on a pending flush and there are no
    more inflight log buffers, returns all callbacks.
    """

    batch_key = batch.Key()

    def _ProcessWaitCallbacks():
      # If this was the last currently uploading ('in-flight') log batch,
      # invokes any callbacks waiting on the persistor to finish.  This functionality
      # is only intended for testing.
      del self._in_flight[batch_key]
      if not self._in_flight:
        while self._wait_callbacks:
          self._wait_callbacks.popleft()()

    def _OnPut():
      logging.info('Successfully persisted log batch %s to object store' % batch_key)
      # Delete the local backup file if this was a restore attempt.
      if restore:
        os.unlink(self._BackupFileName(batch))
      _ProcessWaitCallbacks()

    def _OnError(type, value, tb):
      logging.error('Failed to put log batch %s to object store' % batch_key, exc_info=(type, value, tb))
      # If this was the original attempt to upload a batch, save to local backup.
      if not restore:
        self._PersistToBackup(batch)
      _ProcessWaitCallbacks()

    # Add this batch to the 'in-flight' collection.  This helps track any outstanding S3 requests, which
    # is important if the persistor is closed with outstanding batches remaining.
    if IOLoop.current() is not None:
      # Because this can be called during a process-exit scenario with no IOLoop available, we need to
      # check for it before using a barrier.  Otherwise we persist to backup, which does not require an
      # IOLoop.
      self._in_flight[batch_key] = batch
      with util.Barrier(_OnPut, on_exception=_OnError) as b:
        ObjectStore.GetInstance(batch.store_name).Put(batch_key, batch.buffer, callback=b.Callback())
    else:
      self._PersistToBackup(batch)

  def _PersistToBackup(self, batch):
    """Writes a batch to the local filesystem."""
    filename = self._BackupFileName(batch)
    assert not os.path.isfile(filename)
    try:
      os.makedirs(os.path.dirname(filename))
    except:
      pass
    with open(filename, 'w') as f:
      f.write(batch.buffer)
    logging.info('Persisted log batch %s/%s to local backup directory.' %
                 (batch.store_name, batch.FileSystemKey()))

    if not self._closing:
      self._SetRestoreTimeout()

  def _BackupFileName(self, batch):
    return os.path.join(self._backup_dir, batch.store_name, batch.FileSystemKey())

  def _RestoreBackups(self):
    """Restores all server logs which are currently persisted to the
    backup directory. Each is sent in turn to the object store.
    """
    # Reset timeout.
    if self._restore_timeout:
      IOLoop.current().remove_timeout(self._restore_timeout)
      self._restore_timeout = None

    # Verify or create backup directory.
    if not os.path.isdir(self._backup_dir):
      os.makedirs(self._backup_dir)

    try:
      assert os.path.isdir(self._backup_dir), self._backup_dir
      store_names = os.listdir(self._backup_dir)
      for store_name in store_names:
        # Each sub-directory contains backup logs for a different object store.
        store_name_dir = os.path.join(self._backup_dir, store_name)
        files = os.listdir(store_name_dir)
        if files:
          logging.info('restoring %d server log(s) from store %s' % (len(files), store_name))
          for file in files:
            filepath = os.path.join(store_name_dir, file)
            with open(filepath, 'r') as f:
              batch = LogBatch(f.read(), store_name, *LogBatch.DecodeFileSystemKey(file))

            self._PersistToObjStore(batch, restore=True)
        else:
          # Remove empty store directory.
          os.rmdir(store_name_dir)
    except:
      logging.exception('Error restoring server logs from backup directory')

  def _SetRestoreTimeout(self, timeout_secs=None):
    """Sets the restore timeout if it is not already set.  The timeout will trigger
    an attempt to upload local batch backups to the server.
    """
    if timeout_secs is None:
      timeout_secs = self._RESTORE_INTERVAL_SECS
    if not self._restore_timeout:
      if timeout_secs > 0:
        logging.info('setting a timeout of %fs to reattempt object store persistance' %
                     self._RESTORE_INTERVAL_SECS)
        deadline = time.time() + timeout_secs
        with stack_context.NullContext():
          self._restore_timeout = IOLoop.current().add_timeout(deadline, self._RestoreBackups)
      else:
        self._RestoreBackups()

  @staticmethod
  def Instance():
    assert hasattr(LogBatchPersistor, '_instance'), 'instance not initialized'
    return LogBatchPersistor._instance

  @staticmethod
  def SetInstance(persistor):
    """Sets a new instance for testing."""
    LogBatchPersistor._instance = persistor


class _NullFilter(Filter):
  """Simple logging filter which disables all logging when active."""
  def __init__(self):
    super(_NullFilter, self).__init__()

  def filter(self, record):
    return 0


class _DisableLoggingContext(stack_context.StackContext):
  """Applies a null filter, which disables all logging, to the given
  log filterer (usually either a logger or a handler) while this context
  is active.
  """
  def __init__(self, filterer):
    super(_DisableLoggingContext, self).__init__(self._FilterContext)
    self._filterer = filterer

  @contextmanager
  def _FilterContext(self):
    with util.ExceptionBarrier(util.LogExceptionCallback):
      try:
        filter = _NullFilter()
        self._filterer.addFilter(filter)
        yield
      finally:
        self._filterer.removeFilter(filter)


def InitServerLog(persistor=None):
  """Establishes an instance of LogBatchPersistor, used to manage the
  reliable upload of logs to object storage.

  Also creates a ServerLogHandler which records all log messages from
  the server, regardless of context.  ServerLogHandler is set to INFO
  level.
  """
  persistor = persistor or LogBatchPersistor()
  LogBatchPersistor.SetInstance(persistor)

  server_log_handler = ServerLogHandler()
  server_log_handler.setLevel(logging.INFO)
  error_log_handler = ErrorLogHandler()
  error_log_handler.setLevel(logging.WARNING)
  logging.getLogger().addHandler(server_log_handler)
  logging.getLogger().addHandler(error_log_handler)


@gen.coroutine
def FinishServerLog():
  """Flushes server log to object store with a timeout."""
  if hasattr(LogBatchPersistor, '_instance'):
    yield gen.Task(LogBatchPersistor.Instance().close)
    delattr(LogBatchPersistor, '_instance')
