# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""
Utility class which helps run a process as a daemon.

Designed to be used as part of the Viewfinder asynchronous initialization
process.
"""
from __future__ import absolute_import

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import errno
import io
import signal
import os
import sys
import daemon

from lockfile import pidlockfile
from functools import partial
from tornado import options

options.define('daemon', 'none',
               help='Specifies an option for running a daemon process.  Should be one of: '
                    '(start, stop, restart)')


class DaemonError(Exception):
  """Represents errors from the daemon manager.  Should only be raised during the process
  of stopping or starting a daemon process, and should not be raised once then actual
  daemon process is running."""
  pass


class DaemonManager(object):
  """Class which manages the running of a process as a daemon.

  Depending on the value of the command-line value of the --daemon option, this class
  can optionally run a process as a daemon, stop a running daemon process, or restart
  it.  The uniqueness of a daemon is enforced through use of a named lockfile - operations
  which check for a currently running daemon will do so using this lockfile.

  When the 'start' option is specified, the current process will be converted to a daemon.
  If an existing daemon process is already running, this process will fail with an
  exception.

  When 'stop' is specified, any existing daemon process will be aborted and this process
  will end.  If no daemon was running, an error will be raised.

  When 'restart' is specified, any existing daemon process will be stopped and the current
  process will be converted to a daemon.
  """
  action_funcs = ('start', 'stop', 'restart')

  def __init__(self, lock_file_name):
    self.lockfile = pidlockfile.PIDLockFile(lock_file_name)

  def SetupFromCommandLine(self, run_callback, shutdown_callback):
    """Configures the daemon based on the command line --daemon option.

    If no option is specified, then run_callback is invoked with shutdown_callback
    as a parameter.

    If 'start' or 'restart' is specified, then the current process will be converted
    to a daemon before invoking run_callback.

    If 'stop' is specified, then any running daemon will be terminated and the
    shutdown_callback will be invoked."""
    opt = options.options.daemon.lower()

    if opt == 'none':
      # Not running as a daemon, run callback immediately.
      run_callback(shutdown_callback)
      return

    def _shutdown_daemon():
      self._context.close()
      shutdown_callback()

    opt = options.options.daemon.lower()
    if opt == 'start':
      self.StartDaemon()
      run_callback(_shutdown_daemon)
    elif opt == 'stop':
      self.StopDaemon(True)
      shutdown_callback()
    elif opt == 'restart':
      self.StopDaemon(False)
      self.StartDaemon()
      run_callback(_shutdown_daemon)
    else:
      raise ValueError('"%s" is not a valid choice for the --daemon option.  Must be one of %s'
                       % (opt, self.action_funcs))

  def StartDaemon(self):
    """Converts the current process to a daemon unless another daemon process
    is already running on the system.
    """
    current_pid = self._get_current_pid()
    if current_pid is not None:
      raise DaemonError('Daemon process is already started with PID:%s' % current_pid)

    self._context = daemon.daemon.DaemonContext(pidfile=self.lockfile)
    try:
      self._context.open()
    except pidlockfile.AlreadyLocked:
      pid = self.lockfile.read_pid()
      raise DaemonError('Daemon process is already started with PID:%s' % pid)

  def StopDaemon(self, require_running=True):
    """Stops any currently running daemon process on the system."""
    current_pid = self._get_current_pid()
    if require_running and current_pid is None:
      raise DaemonError('Daemon process was not running.')

    try:
      os.kill(current_pid, signal.SIGTERM)
    except OSError, exc:
      raise DaemonError('Failed to stop daemon process %d: %s' % (current_pid, exc))

  def _get_current_pid(self):
    """Get the process ID of any currently running daemon process.  Returns
    None if no process is running.
    """
    current_pid = None
    if self.lockfile.is_locked():
      current_pid = self.lockfile.read_pid()
      if current_pid is not None:
        try:
          # A 0 signal will do nothing if the process exists.
          os.kill(current_pid, 0)
        except OSError, exc:
          if exc.errno == errno.ESRCH:
            # PID file was stale, delete it.
            current_pid = None
            self.lockfile.break_lock()

    return current_pid
