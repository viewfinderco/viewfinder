# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Utility methods.

  Barrier: synchronization barrier with no results
  MonoBarrier: synchronization barrier that returns a single result
  ArrayBarrier: synchronization barrier with ordered results
  DictBarrier: synchronization barrier with dictionary of results
  ParseJSONResponse(): parses a JSON response body into python data structures
  ParseHostPort(): parses host:port string and returns tuple
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import base64
import calendar
import collections
import hashlib
import json
import logging
import math
import os
import pwd
import random
import re
import struct
import sys
import time

from datetime import date, datetime, timedelta
from functools import partial
from tornado import gen, ioloop, stack_context
from viewfinder.backend.base import base64hex


def NoCallback(*args, **kwargs):
  """Used where the conclusion of an asynchronous operation can be
  ignored.
  """
  pass


def LogExceptionCallback(type, value, tb):
  """Logs and then ignores the exception."""
  logging.error('unexpected error', exc_info=(type, value, tb))


class _BarrierContext(object):
  """A context manager which returns a synchronization barrier for
  managing any number of asynchronous operations started within its
  context. A final callback is specified on construction to be invoked
  after all callbacks allocated during the __enter__ phase of the
  barrier context have been invoked.

  If an exception is thrown at any time during the execution of the
  barrier (including in its entire hierarchical sub tree of
  asynchronous operations), the barrier is aborted and will never
  finish. Its current batch of results and any incoming results are
  discarded. The barrier completion callback will never be run. Only
  the first exception is acted upon; all others thrown in subsequent
  processing of extant async execution pathways are logged tersely.

  If 'on_exception' is specified, it is invoked to handle intentional
  cleanup and/or to continue processing along an alternate (error
  recovery) execution pathway. The stack context that existed when the
  barrier was created is restored in order to run 'on_exception'. If
  'on_exception' would like to propagate the exception, the exception
  should be re-raised. The exception handler can optionally return a
  boolean value to indicate whether or not the underlying exception
  should be logged.
  """
  def __init__(self, callback, barrier_type, on_exception=None):
    callback = stack_context.wrap(callback)
    on_exception = stack_context.wrap(on_exception)
    # Parent frame is derived class __init__, so get grandparent frame.
    frame = sys._getframe().f_back.f_back
    self._barrier = _Barrier(callback, on_exception, barrier_type, frame)
    self._stack_context = stack_context.ExceptionStackContext(self._barrier.ReportException)

  def __enter__(self):
    self._stack_context.__enter__()
    return self._barrier

  def __exit__(self, type, value, traceback):
    if (type, value, traceback) == (None, None, None):
      self._barrier.Start()
    return self._stack_context.__exit__(type, value, traceback)


class Barrier(_BarrierContext):
  """Barrier that discards all return values and invokes final
  callback without arguments.
  """
  def __init__(self, callback, on_exception=None):
    super(Barrier, self).__init__(callback, _Barrier.BARRIER,
                                  on_exception=on_exception)


class MonoBarrier(_BarrierContext):
  """Barrier that expects and returns a single value from a single
  constituent op, or None, if no ops are run.
  """
  def __init__(self, callback, on_exception=None):
    super(MonoBarrier, self).__init__(callback, _Barrier.MONO_BARRIER,
                                      on_exception=on_exception)


class ArrayBarrier(_BarrierContext):
  """Barrier that returns results from asynchronous ops as an
  ordered list.
  """
  def __init__(self, callback, compact=False, on_exception=None):
    super(ArrayBarrier, self).__init__(
      callback, _Barrier.COMPACT_ARRAY_BARRIER if compact else _Barrier.ARRAY_BARRIER,
      on_exception=on_exception)


class DictBarrier(_BarrierContext):
  """Barrier that returns results from asynchronous ops as a dict.
  """
  def __init__(self, callback, on_exception=None):
    super(DictBarrier, self).__init__(callback, _Barrier.DICT_BARRIER,
                                      on_exception=on_exception)


class ExceptionBarrier(_BarrierContext):
  """Barrier that handles exceptions by routing the first exception to
  the 'on_exception' handler and logging any subsequent exceptions.
  """
  def __init__(self, on_exception):
    super(ExceptionBarrier, self).__init__(NoCallback, _Barrier.EXC_BARRIER,
                                           on_exception=on_exception)


class _Barrier(object):
  """Provides a synchronization barrier for invoking a final callback
  when the barrier has been invoked the specified number of times.
  Each invocation of the barrier expects a result object which is
  appended to a final list. The final list is passed to the barrier
  callback.
  """
  BARRIER = 0
  MONO_BARRIER = 1
  ARRAY_BARRIER = 2
  COMPACT_ARRAY_BARRIER = 3
  DICT_BARRIER = 4
  EXC_BARRIER = 5

  _types = {
    BARRIER: 'barrier',
    MONO_BARRIER: 'mono barrier',
    ARRAY_BARRIER: 'array barrier',
    COMPACT_ARRAY_BARRIER: 'compact array barrier',
    DICT_BARRIER: 'dict barrier',
    EXC_BARRIER: 'exception barrier',
    }

  _INITIALIZING = 0
  """Callbacks are being accumulated in initial "with" statement."""

  _STARTED = 1
  """Initial "with" statement is complete; now waiting for async callbacks."""

  _COMPLETED = 2
  """All async callbacks have been invoked successfully."""

  _FAULTED = 3
  """An exception occurred during initialization or async execution."""

  def __init__(self, callback, on_exception, barrier_type, frame):
    self._callback = callback
    self._on_exception = on_exception
    self._type = barrier_type
    self._filename = os.path.basename(frame.f_code.co_filename)
    self._lineno = frame.f_lineno
    self._n = 0
    self._cur = 0
    self._state = _Barrier._INITIALIZING
    if self._type == _Barrier.BARRIER:
      self._results = None
    elif self._type == _Barrier.MONO_BARRIER:
      self._results = None
    elif self._type in (_Barrier.ARRAY_BARRIER, _Barrier.COMPACT_ARRAY_BARRIER):
      self._results = []
    elif self._type == _Barrier.DICT_BARRIER:
      self._results = {}
    else:
      assert self._type == _Barrier.EXC_BARRIER
      self._results = None
    logging.debug('constructed %s', _Barrier._types[barrier_type])

  def Callback(self, key=None):
    """Returns a callback upon which the barrier will be gated.  For
    completion, every callback returned via invocations of this method
    must be invoked. If 'key' is not None, the result returned with
    the callback will be a dict. Otherwise, results (if any) will be
    returned as an ordered list.
    """
    assert self._type != _Barrier.EXC_BARRIER, \
           'exception barriers do not have results'

    if key is not None:
      assert self._type == _Barrier.DICT_BARRIER, \
          'this barrier is not configured as a dictionary of results'
    else:
      if self._type == _Barrier.ARRAY_BARRIER:
        self._results.append(None)
      key = self._cur

    if self._type == _Barrier.MONO_BARRIER:
      assert self._cur == 0, 'mono-barrier cannot return multiple results'

    self._cur += 1
    self._n += 1
    return partial(self._Invoke, key)

  def Start(self):
    """Invoked when all constituent async ops which this barrier is
    gated on have been launched. This is called from the
    BarrierContext's __exit__ method.
    """
    logging.debug('starting %s with %d async execution pathways...',
                  _Barrier._types[self._type], self._cur)
    assert self._state == _Barrier._INITIALIZING, 'barrier was already started'
    self._state = _Barrier._STARTED
    self._MaybeReturn()

  def ReportException(self, type, value, tb):
    """Called when an exception occurs during initialization or during
    async op execution. Discards all results, transitions the barrier
    to the FAULTED state, and invokes the '_on_exception' callback.
    Returns True if the exception should not be propagated further.
    """
    if self._state == _Barrier._INITIALIZING or self._state == _Barrier._STARTED:
      self._state = _Barrier._FAULTED
      self._results = None
      self._callback = None

      if self._on_exception is not None:
        ioloop.IOLoop.current().add_callback(self._on_exception, type, value, tb)
        return True
      else:
        logging.info('exception in barrier (%s) with no exception handler: %s; propagating...' %
                     (self._FormatBarrierLocation(), FormatLogArgument(value)))
        return False
    elif self._state == _Barrier._COMPLETED:
      logging.error('exception in barrier (%s) that is already completed; propagating...' %
                    self._FormatBarrierLocation(), exc_info=(type, value, tb))
      return False

    assert self._state == _Barrier._FAULTED, self._state
    logging.info('more than one exception in barrier (%s): %s; ignoring...' %
                 (self._FormatBarrierLocation(), FormatLogArgument(value)))
    return True

  def _FormatBarrierLocation(self):
    """Return a human-readable format of the location of the barrier in
    the source code.
    """
    return '%s:%d' % (self._filename, self._lineno)

  def _Invoke(self, *args):
    """Result callback for constituent asynchronous operations which
    the barrier is gated on. The results are aggregated in self._result
    based on '*args'.
    """
    assert len(args) >= 1, args
    key = args[0]
    val = None
    if len(args) > 1:
      val = args[1] if len(args) == 2 else args[1:]

    if self._state == _Barrier._FAULTED:
      logging.info('discarding result %r intended for faulted barrier (%d): %r' %
                   (key, self._cur, FormatLogArgument(val)))
      return

    assert self._state != _Barrier._COMPLETED, 'Why still getting results after completion?'

    if self._type == _Barrier.COMPACT_ARRAY_BARRIER:
      if val is not None:
        self._results.append(val)
      else:
        logging.debug('discarding empty result')
    elif self._type == _Barrier.MONO_BARRIER:
      assert self._results is None, self._results
      self._results = val
    elif self._type != _Barrier.BARRIER:
      self._results[key] = val
    self._n -= 1
    assert self._n >= 0, 'barrier invoked more than %d times Callback() was invoked' % self._cur
    self._MaybeReturn()

  def _MaybeReturn(self):
    """Schedules the barrier callback if the barrier has been started
    and all results have been received. If all results were empty,
    schedules the barrier callback with no arguments. If the barrier is
    a mono barrier, and the results are a list, schedules the callback with
    the list expanded into positional arguments.  The callback is scheduled,
    rather than invoked directly, to ensure that any contexts established
    inside the scope of the barrier are properly unrolled before the
    callback is invoked.
    """
    if self._n == 0 and self._state == _Barrier._STARTED and self._type != _Barrier.EXC_BARRIER:
      self._state = _Barrier._COMPLETED

      callback = self._callback
      self._callback = None

      results = self._results
      self._results = None

      if self._type == _Barrier.BARRIER:
        logging.debug('%s finished', _Barrier._types[self._type])
        if callback is not None:
          ioloop.IOLoop.current().add_callback(callback)
      elif self._type == _Barrier.MONO_BARRIER and type(results) == tuple:
        logging.debug('%s finished with tuple result: %r', _Barrier._types[self._type], results)
        if callback is not None:
          ioloop.IOLoop.current().add_callback(callback, *results)
      else:
        logging.debug('%s finished with result: %r', _Barrier._types[self._type], results)
        if callback is not None:
          ioloop.IOLoop.current().add_callback(callback, results)


_TEST_TIME = None
"""If not None, _TEST_TIME is used in various places in the server where
time.time() is normally called. This value is overridden by tests that
require determinism.
"""


def GetCurrentTimestamp():
  """If _TEST_TIME has been set, returns it. Otherwise, returns the
  current timestamp. Doing this enables tests to be more deterministic.
  """
  return _TEST_TIME if _TEST_TIME is not None else time.time()


def CreateSortKeyPrefix(timestamp, randomness=True, reverse=False):
  """Returns a sort key which will sort by 'timestamp'. If
  'randomness' is True, 16 bits of randomness (which would otherwise
  be lost to b64-encoding padding) are added into the free bits. These
  are meant to minimize the chance of collision when the sort key
  prefix is meant to provide uniqueness but many keys may be created
  in the same second. If 'reverse' is True, the timestamp is reversed
  by subtracting from 2^32. The result is base64hex-encoded.
  """
  assert timestamp < 1L << 32, timestamp
  if reverse:
    timestamp = (1L << 32) - int(timestamp) - 1
  if randomness:
    random_bits = random.getrandbits(16) & 0xffff
  else:
    random_bits = 0
  return base64hex.B64HexEncode(struct.pack(
      '>IH', int(timestamp), random_bits))


def UnpackSortKeyPrefix(prefix):
  """Returns the timestamp in the provided sort key prefix. The
  timestamp may be reversed, if reverse=True was specified when
  the sort key prefix was created.
  """
  timestamp, random_bits = struct.unpack('>IH', base64hex.B64HexDecode(prefix))
  return timestamp


def ParseHostPort(address):
  """Parses the provided address string as host:port and
  returns a tuple of (str host, int port).
  """
  host_port_re = re.match(r"([a-zA-Z0-9-\.]+):([0-9]{1,5})$", address)
  if not host_port_re:
    raise TypeError("bad host:port: %s" % address)
  host = host_port_re.group(1)
  port = int(host_port_re.group(2))
  if port >= 65536:
    raise TypeError("invalid port: %d" % port)
  return (host, port)


def EncodeVarLengthNumber(value):
  """Uses a variable length encoding scheme. The first 7 bits of each
  byte contain the value and the 8th bit is a continuation bit. Returns
  a string of raw bytes. Supply the output to DecodeVarLengthNumber to
  decode and retrieve the original number.
  """
  byte_str = ''
  while value >= 128:
    byte_str += struct.pack('>B', (value & 127) | 128)
    value >>= 7
  byte_str += struct.pack('>B', value & 127)
  return byte_str


def DecodeVarLengthNumber(byte_str):
  """Interprets a raw byte string as a variable length encoded number
  and decodes. Returns a pair consisting of the decoded number and the
  number of bytes consumed to decode the number.
  """
  value = 0
  num_bytes = 0
  for shift in xrange(0, 64, 7):
    byte, = struct.unpack('>B', byte_str[num_bytes:num_bytes + 1])
    num_bytes += 1
    if byte & 128:
      value |= ((byte & 127) << shift)
    else:
      value |= (byte << shift)
      return value, num_bytes
  raise TypeError('string not decodable as variable length number')


class DecayingStat(object):
  """Decaying stat class which exponentially decays stat measurements
  according to a 'half-life' setting specified to the constructor.
  """
  def __init__(self, half_life, now=None):
    """The 'half_life' is specified in seconds."""
    self._half_life = half_life
    self._last_time = now if now is not None else time.time()
    self._value = 0

  def Add(self, value, now=None, ceiling=None):
    now = now if now is not None else time.time()
    self._value = self._Decay(self._value, now) + value
    if ceiling is not None:
      self._value = min(ceiling, self._value)
    self._last_time = now

  def Get(self, now=None):
    now = now if now is not None else time.time()
    return self._Decay(self._value, now)

  def _Decay(self, value, now):
    delta_secs = now - self._last_time
    if delta_secs == 0.0:
      return value
    return value * math.exp(-math.log(2.0) * delta_secs / self._half_life)


class GenConstant(gen.YieldPoint):
  """Yields a constant value. Used with the tornado.gen infrastructure."""
  def __init__(self, constant):
    self._constant = constant

  def start(self, runner):
    pass

  def is_ready(self):
    return True

  def get_result(self):
    return self._constant


def GenSleep(seconds):
  """Wait for a period of time without blocking. Used with the tornado.gen infrastructure."""
  io_loop = ioloop.IOLoop.current()
  return gen.Task(io_loop.add_timeout, io_loop.time() + seconds)


def FormatLogArgument(s):
  """Format "s" in a human-readable way for logging by truncating it
  to at most 256 characters.
  """
  MAX_LEN = 256
  if isinstance(s, unicode):
    s = s.encode('utf-8')
  else:
    s = str(s)
  if len(s) <= MAX_LEN:
    return s
  return '%s...[%d bytes truncated]' % (s[:MAX_LEN], len(s) - MAX_LEN)


def FormatArguments(*args, **kwargs):
  """Format function call arguments in a human-readable way for logging."""
  def _FormatArg(arg):
    return FormatLogArgument(arg)

  # Truncate arguments.
  args = [_FormatArg(arg) for arg in args]
  kwargs = {key: _FormatArg(value) for key, value in kwargs.items()}

  return "(args=%s, kwargs=%s)" % (args, kwargs)


def FormatFunctionCall(func, *args, **kwargs):
  """Format a function and its arguments in a human-readable way for logging."""
  while type(func) is partial:
    args = func.args + args
    if func.keywords:
      kwargs.update(func.keywords)
    func = func.func

  return "%s%s" % (func.__name__, FormatArguments(*args, **kwargs))


def TimestampUTCToISO8601(timestamp):
  """Return the timestamp (UTC) ISO 8601 format: YYYY-MM-DD."""
  utc_tuple = datetime.utcfromtimestamp(timestamp)
  return '%0.4d-%0.2d-%0.2d' % (utc_tuple.year, utc_tuple.month, utc_tuple.day)


def NowUTCToISO8601():
  """Return the current date (UTC) in ISO 8601 format: YYYY-MM-DD."""
  return TimestampUTCToISO8601(time.time())


def ISO8601ToUTCTimestamp(day, hour=0, minute=0, second=0):
  """Convert the day in ISO 8601 format (YYYY-MM-DD) to timestamp."""
  y, m, d = day.split('-')
  return calendar.timegm(datetime(int(y), int(m), int(d), hour, minute, second).timetuple())


def SecondsSince(timestamp):
  """Seconds since a given timestamp."""
  return time.time() - timestamp


def HoursSince(timestamp):
  """Hours since a given timestamp. Floating point."""
  return SecondsSince(timestamp) / 3600.


def GetSingleListItem(list, default=None):
  """Return the first item in the list, or "default" if the list is None
  or empty. Assert that the list contains at most one item.
  """
  if list:
    assert len(list) == 1, list
    return list[0]
  return default


def Pluralize(count, singular='', plural='s'):
  """Return the pluralization suffix for "count" item(s). For example:
       'item' + Pluralize(1) = 'item'
       'item' + Pluralize(2) = 'items'
       'activit' + Pluralize(1, 'y', 'ies') = 'activity'
       'activit' + Pluralize(0, 'y', 'ies') = 'activities'
  """
  return singular if count == 1 else plural


def ComputeMD5Hex(byte_str):
  """Compute MD5 hash of "byte_str" and return it encoded as hex string."""
  hasher = hashlib.md5()
  hasher.update(byte_str)
  return hasher.hexdigest()


def ComputeMD5Base64(byte_str):
  """Compute MD5 hash of "byte_str" and return it encoded as a base-64
  string.
  """
  hasher = hashlib.md5()
  hasher.update(byte_str)
  return base64.b64encode(hasher.digest())


def ToCanonicalJSON(dict, indent=False):
  """Convert "dict" to a canonical JSON string. Sort keys so that output
  ordering is always the same.
  """
  return json.dumps(dict, sort_keys=True, indent=indent)


def SetIfNotNone(dict, attr_name, value):
  """If "value" is not None, then set the specified attribute of "dict"
  to its value.
  """
  if value is not None:
    dict[attr_name] = value


def SetIfNotEmpty(dict, attr_name, value):
  """If "value" is not empty and non-zero, then set the specified attribute of "dict" to
  its value.
  """
  if value:
    dict[attr_name] = value


def ConvertToString(value):
  """Converts value, if a number, to a string."""
  if type(value) in (int, long):
    return str(value)
  elif type(value) == float:
    # Need to use repr(), since str() rounds floats. However, can't use repr() for longs,
    # since it adds an "L".
    return repr(value)
  else:
    return value


def ConvertToNumber(value):
  """Converts value, a string, into either an integer or a floating point
  decimal number.
  """
  try:
    # int() automatically promotes to long if necessary
    return int(value)
  except:
    return float(value)


class LRUCache(object):
  """Simple LRU cache.

  Usage:
    value = cache.Get(key, lambda: CreateValue(...))

  The factory function will be called only if the value does not exist in the cache.
  """
  def __init__(self, max_size):
    self._max_size = max_size
    self._cache = collections.OrderedDict()

  def Get(self, key, factory):
    if key in self._cache:
      # Delete and re-add the object to move it to the top of the list.
      value = self._cache.pop(key)
    else:
      value = factory()
    self._cache[key] = value
    while len(self._cache) > self._max_size:
      self._cache.popitem(False)
    return value


def CheckRequirements(filename):
  """Parse a pip requirements.txt and raise an exception if any packages
  are not installed.
  """
  from pip.req import parse_requirements
  errors = []
  for req in parse_requirements(filename):
    req.check_if_exists()
    if not req.satisfied_by:
      errors.append(req)
  if errors:
    raise RuntimeError("Requirements not installed: %s" % [str(e) for e in errors])


def GetLocalUser():
  """Return the local user running the program.
  os.getlogin() fails on ubuntu cron jobs, hence the getuid method.
  """
  return pwd.getpwuid(os.getuid())[0] or os.getlogin()


def ThrottleRate(throttle_dict, max_count, time_period):
  """Throttle the rate at which occurrences of some event can occur. The maximum rate is given
  as a period of time and the max number of occurrences that can happen within that period.

  The current count and elapsed time is stored in "throttle_dict":
    - start_time: time at which the current period started
    - count: number of occurrences so far in the current period

  Returns a 2-tuple containing an updated throttle_dict and a boolean indicating whether the
  occurrence rate has exceeded the maximum allowed:
    (throttle_dict, is_throttled)
  """
  now = GetCurrentTimestamp()
  if not throttle_dict or now >= throttle_dict['start_time'] + time_period:
    throttle_dict = {'start_time': now,
                     'count': 0}
  else:
    throttle_dict = {'start_time': throttle_dict['start_time'],
                     'count': throttle_dict['count']}

  if throttle_dict['count'] >= max_count:
    return (throttle_dict, True)

  throttle_dict['count'] += 1
  return (throttle_dict, False)
