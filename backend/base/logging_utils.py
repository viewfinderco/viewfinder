# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Common logging utilities and code.

  - FORMATTER: default Viewfinder log formatter
  - ErrorLogFilter: Filter used to count errors from a central location.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
              'matt@emailscrubbed.com (Matt Tracy)']

import datetime
import logging
import counters
import sys


class _LogFormatter(logging.Formatter):
  converter = datetime.datetime.fromtimestamp
  def formatTime(self, record, datefmt=None):
    ct = self.converter(record.created)
    if datefmt:
      s = ct.strftime(datefmt)
    else:
      t = ct.strftime('%Y-%m-%d %H:%M:%S')
      s = '%s:%03d' % (t, record.msecs)
    return s

  def format(self, record):
    """Ensure that the log is consistently encoded as UTF-8."""
    msg = super(_LogFormatter, self).format(record)
    if isinstance(msg, unicode):
      msg = msg.encode('utf-8')
    return msg

FORMATTER = _LogFormatter('%(asctime)s [pid:%(process)d] %(module)s:%(lineno)d: %(message)s')


class StdStreamProxy(object):
  """Proxy for sys.std{out,err} to ensure it can be updated.

  The logging module (at least in its default configuration) makes
  a copy of sys.std{out,err} at startup and writes to those objects.
  This is incompatible with unittest's "buffer" feature, which points
  the variables in sys to new values.  By wrapping sys.std{out,err}
  with this proxy before logging is configured, we ensure that
  unittest's changes have the desired effect.

  Usage: Before logging is initialized (i.e. before
  tornado.options.parse_command_line), do
    sys.stdout = StdStreamProxy('stdout')
    sys.stderr = StdStreamProxy('stderr')
  """
  def __init__(self, name):
    assert name in ('stdout', 'stderr')
    self.name = name
    self.real_stream = getattr(sys, name)

  def __getattr__(self, name):
    current_stream = getattr(sys, self.name)
    if current_stream is self:
      # not redirected, so write through to the original stream
      return getattr(self.real_stream, name)
    else:
      # write to the new current stream
      return getattr(current_stream, name)
