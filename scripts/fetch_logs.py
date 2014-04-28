#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Fetch user client device / server operation logs.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import datetime
import gzip
import heapq
import iso8601
import logging
import os
import re
import sys
import time

from collections import namedtuple
from operator import itemgetter
from tornado import httpclient, ioloop, options
from tornado.escape import _unicode
from viewfinder.backend.base import otp, util
from viewfinder.backend.base.constants import SECONDS_PER_DAY
from viewfinder.backend.www.admin import admin_api


options.define('api_host', 'www.viewfinder.co', help='hostname for admin service API')
options.define('user_id', None, type=int, help='user id')
options.define('start_date', None, help='ISO 8601-formatted start date (local time; converts to UTC)')
options.define('start_timestamp', None, type=float, help='start timestamp in seconds (in UTC)')
options.define('end_date', None, help='ISO 8601-formatted end date (local time; converts to UTC)')
options.define('end_timestamp', None, type=float, help='end timestamp in seconds (in UTC)')
options.define('filter', '/op/|/req/|dev-.*\\.(analytics|log|crash)(\\.gz)?',
               help='filter for log filenames')
options.define('fetch_dir', None, help='directory in which to store fetched logs')
options.define('cache_logs', True, help='whether or not to keep logs on successive runs')
options.define('merge_logs', False, help='after fetching logs, merge by timestamp and output to stdout')
options.define('merge_filter', '/op/|/req/|dev-.*\\.log(\\.gz)?',
               help='merge only log files matching this regexp')
options.define('use_utc', False, help='enable to display UTC timestamps; by default, converts to local timezone')
options.define('colorize', default=['dev-.*\\.log=4', '/op/=2', '/req/=3'],
               multiple=True, help='one or more "<regexp>=<ansi-color>" directives')
options.define('color', 'auto', help='one of {yes, no, auto} for colorization; specify "yes" if sending '
               'output to "less"; use less -R to see colorized output through less')

# Iso date / time regular expression.
_ISO_DATE_RE = re.compile('^(\d{4,4}-\d{2,2}-\d{2,2} \d{2,2}:\d{2,2}:\d{2,2}:\d{3,3})(.*)',
                          re.MULTILINE | re.DOTALL)

EPOCH = datetime.datetime.utcfromtimestamp(0)

def UTCDatetimeToTimestamp(dt):
  return (dt.replace(tzinfo=None) - EPOCH).total_seconds()

def UTCDatetimeToLocalDatetime(dt):
  return datetime.datetime.fromtimestamp(UTCDatetimeToTimestamp(dt))

def LocalDatetimeToTimestamp(dt):
  return (dt.replace(tzinfo=None) + datetime.timedelta(seconds=time.timezone) - EPOCH).total_seconds()

def LocalDatetimeToUTCDatetime(dt):
  return datetime.datetime.utcfromtimestamp(LocalDatetimeToTimestamp(dt))

def ParseIso8601DatetimeToUTCDatetime(dt_str):
  if re.compile('\d{4,4}-\d{2,2}-\d{2,2}').search(dt_str):
    dt_str += ' 00:00:00'
  return iso8601.parse_date(dt_str)

def SafeUnicode(s):
  try:
    return _unicode(s)
  except UnicodeDecodeError:
    return repr(s)


# Maximum number of open files to cache while merging.
MAX_OPEN_FILES = 100

# Describes how lines matching the filename_re should be colorized.
ColorDirective = namedtuple('ColorDirective', ['filename_re', 'prefix', 'suffix'])

# For colorizing merged log output, if curses is available.
try:
  import curses
except ImportError:
  curses = None


def GetLogUrls(opener, api_host):
  """Calls into the admin API to get log urls for the user,
  time range and log filename regular expression specified in
  the command line arguments.
  """
  start_timestamp, end_timestamp = _GetTimestamps()
  logging.info('time range %s => %s' %
               (datetime.datetime.fromtimestamp(start_timestamp).strftime('%Y-%m-%d %H:%M:%S'),
                datetime.datetime.fromtimestamp(end_timestamp).strftime('%Y-%m-%d %H:%M:%S')))

  request_dict = {'user_id': options.options.user_id,
                  'start_timestamp': start_timestamp,
                  'end_timestamp': end_timestamp}

  if options.options.filter:
    request_dict['filter'] = options.options.filter

  response_dict = admin_api.ServiceRequest(
    opener, api_host, 'list_client_logs', request_dict)
  return response_dict['log_urls']


def FetchLogs(opener, api_host):
  """Queries logs urls from the admin service API and fetches
  the files into --fetch_dir. The log urls returned from the admin
  API are augmented with local filenames and returned.
  """
  fetch_dir = os.path.join(options.options.fetch_dir or os.getcwd(), 'logs')
  logging.info('writing logs for user %s to %s' %
               (options.options.user_id, fetch_dir))
  _InitDir(fetch_dir)

  io_loop = ioloop.IOLoop.instance()
  http_client = httpclient.AsyncHTTPClient(io_loop)
  log_urls = GetLogUrls(opener, api_host)
  with util.Barrier(io_loop.stop) as b:
    for log_record in log_urls:
      output_file = os.path.join(fetch_dir, log_record['filename'])

      # Check whether the output file already exists; skip if yes
      # and --cache_logs is true.
      if os.path.exists(output_file) and options.options.cache_logs:
        log_record['local_filename'] = output_file
        continue

      _InitDir(os.path.dirname(output_file))
      try:
        _FetchLog(http_client, log_record['url'], output_file, b.Callback())
        log_record['local_filename'] = output_file
      except:
        logging.exception('failed to fetch %s' % log_record['url'])
        log_record['local_filename'] = None

  io_loop.start()
  logging.info('fetched %d log files for user %s' %
               (len(log_urls), options.options.user_id))
  return log_urls


def MergeLogs(log_urls, output_file=sys.stdout):
  """Merges the array of log_urls, color codes the lines according to
  --colorize, which specifies a list of (regexp, curses-fg-color) pairs
  directing how the timestamp of each line in the merged log should be
  colored.
  """
  start_timestamp, end_timestamp = _GetTimestamps()
  fd_cache = {}  # filename => (last_access, file-descriptor)
  log_heap = []
  def _HeapPush(next_log_record, fn, pos):
    """Starting with the contents of "next_line", reads lines from the
    file until the start of the next log record, which is defined as a
    line starting with the iso date regexp. If there are no more bytes
    in the file, returns without pushing. Otherwise, pushes the log
    line, filename ("fn"), and file object ("f") to the log heap for
    merging.
    """
    # Get file descriptor.
    fd = _GetFD(fn, pos, fd_cache)

    # Skip any lines at the beginning of a file which don't match date.
    while next_log_record != '' and not _ISO_DATE_RE.search(next_log_record):
      print 'not merging log line: "%s"' % next_log_record.rstrip()
      next_log_record = fd.readline()

    next_line = fd.readline()
    while next_line != '':
      if not _ISO_DATE_RE.search(next_line):
        next_log_record += next_line
      else:
        break
      next_line = fd.readline()

    if next_log_record == '':
      fd.close()
      del fd_cache[fn]
      return

    next_log_record = next_log_record.rstrip()
    heapq.heappush(log_heap, (next_log_record, next_line, fn, fd.tell()))

  directives = _InitColorize(output_file)
  # Create a map from log filename to directive so we don't have to
  # do an RE match on every log line.
  re_map = dict()
  merge_re = re.compile(options.options.merge_filter)

  # Construct initial min-heap, sorted by log records.
  for log_url in log_urls:
    fn = log_url['local_filename']
    if merge_re.search(fn) is None:
      continue

    try:
      directive, = [d for d in directives if d.filename_re.search(fn)]
      re_map[fn] = directive
    except:
      pass

    fd = _GetFD(fn, 0, fd_cache)
    _HeapPush(fd.readline(), fn, fd.tell())

  # Process min-heap until all log files are exhausted.
  while len(log_heap) > 0:
    lr, nl, fn, pos = heapq.heappop(log_heap)
    iso_match = _ISO_DATE_RE.match(lr)
    if iso_match:
      utc_aware_dt = iso8601.parse_date(iso_match.group(1))
      utc_aware_ts = UTCDatetimeToTimestamp(utc_aware_dt)

      # Skip any timestamps outside of the range we're looking for.
      if utc_aware_ts >= start_timestamp and utc_aware_ts < end_timestamp:
        if options.options.use_utc:
          timestamp_str = iso_match.group(1)
        else:
          local_dt = UTCDatetimeToLocalDatetime(utc_aware_dt)
          timestamp_str = local_dt.strftime('%Y-%m-%d %H:%M:%S')
        log_message = SafeUnicode(iso_match.group(2))
        directive = re_map.get(fn, None)
        if directive:
          try:
            log_line = '%s%s%s%s\n' % (directive.prefix, timestamp_str, directive.suffix, log_message)
            output_file.write(log_line)
          except:
            output_file.write('%s\n' % lr)
        else:
          output_file.write('%s\n' % lr)
    else:
      logging.error('bad log line: %s' % lr)
    _HeapPush(nl, fn, pos)


def _GetFD(filename, file_pos, fd_cache):
  """Returns the file descriptor matching "filename" if present in the
  cache. Otherwise, opens the file (and seeks to "file_pos"). If too
  many file descriptors are in the cache, cleans out 10% of them.
  The cache includes tuples of the form (access time, file descriptor).
  """
  if filename in fd_cache:
    at, fd = fd_cache[filename]
    fd_cache[filename] = (time.time(), fd)
    return fd

  if len(fd_cache) == MAX_OPEN_FILES:
    # Evict the least-recently used 10%.
    lru = sorted(fd_cache.items(), key=itemgetter(1))[:int(0.1 * MAX_OPEN_FILES)]
    for key,(at,fd) in lru:
      # logging.info('evicting log %s' % key)
      fd.close()
      del fd_cache[key]

  if filename.endswith('.gz') or filename.endswith('.gz.tmp'):
    fd = gzip.open(filename, 'rb')
  else:
    fd = open(filename, 'r')
  fd.seek(file_pos)
  fd_cache[filename] = (time.time(), fd)
  return fd


def _GetTimestamps():
  """Returns the start and end timestamps based on command line flags.
  If --use_utc is False (the default), timestamps are adjusted such
  that if dates were specified, they fall on localtime day boundaries.
  """
  time_offset = 0 if options.options.use_utc else time.timezone
  cur_day = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
  utc_cur_day = LocalDatetimeToUTCDatetime(cur_day)

  if options.options.start_timestamp:
    start_timestamp = options.options.start_timestamp
  elif options.options.start_date:
    utc_dt = ParseIso8601DatetimeToUTCDatetime(options.options.start_date)
    start_timestamp = UTCDatetimeToTimestamp(utc_dt) + time_offset
  else:
    start_timestamp = UTCDatetimeToTimestamp(utc_cur_day)

  if options.options.end_timestamp:
    end_timestamp = options.options.end_timestamp
  elif options.options.end_date:
    utc_dt = ParseIso8601DatetimeToUTCDatetime(options.options.end_date)
    end_timestamp = UTCDatetimeToTimestamp(utc_dt) + time_offset
  else:
    end_timestamp = UTCDatetimeToTimestamp(utc_cur_day) + SECONDS_PER_DAY

  return start_timestamp, end_timestamp


def _InitColorize(output_file):
  """Initializes the colorization directives via --colorize as a mapping
  between compiled regular expressions meant to be matched against log
  filename and target curses color escape codes. The curses escape codes
  are represented as a pair containing codes for prepending and appending.

  Returns: [ColorDirective], or None if
  colorization is disabled or unavailable on the current terminal.

  Based on tornado's code to colorize log output.
  """
  color = False
  # Set up color if we are in a tty, curses is available, and --colorize
  # was specified.
  if options.options.colorize is not None and curses and \
        (options.options.color == 'yes' or \
           (options.options.color == 'auto' and output_file.isatty())):
    try:
      curses.setupterm()
      if curses.tigetnum("colors") > 0:
        color = True
    except Exception:
      pass
  if not color:
    return []

  directives = []
  normal = unicode(curses.tigetstr("sgr0"), "ascii")
  fg_color = unicode(curses.tigetstr("setaf") or curses.tigetstr("setf") or "", "ascii")
  for directive in options.options.colorize:
    regexp, color_index = directive.split('=')
    color = unicode(curses.tparm(fg_color, int(color_index)), "ascii")
    directives.append(ColorDirective(re.compile(regexp), color, normal))
  return directives


def _FetchLog(http_client, log_url, output_file, callback):
  """Fetches the log file at "log_url" and stores it in
  "output_file".
  """
  def _OnFetch(response):
    if response.code == 200:
      with open(output_file, 'w') as f:
        f.write(response.body)
        logging.info('wrote %d bytes to %s' % (len(response.body), output_file))
    else:
      logging.error('failed to fetch %s' % log_url)
    callback()

  http_client.fetch(log_url, callback=_OnFetch, method='GET')


def _InitDir(output_dir):
  """Initializes the output directory for fetching user logs."""
  try:
    os.listdir(output_dir)
  except:
    os.makedirs(output_dir)


def main():
  options.parse_command_line()
  assert options.options.user_id is not None
  opener = otp.GetAdminOpener(options.options.api_host)
  log_urls = FetchLogs(opener, options.options.api_host)
  if options.options.merge_logs:
    MergeLogs(log_urls)

if __name__ == '__main__':
  main()
