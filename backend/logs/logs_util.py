# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Utility functions to handle server logs and metrics.

ServerLogPaths and UserAnalyticsLogsPaths: classes to handle various paths to logs, and path parsing.

IsEC2Instance: return true if instance is an AWS instance name

# Server log contents parsing.
ParseLogLine: parse a raw log line.
ParseSuccessMsg: parse the message logged by user_op_managed SUCCESS.

# Registry of processed files.
GetRegistry: read a "file registry" from a given path.
WriteRegistry: write a "file registry" to a given path.

ListClientLogUsers: return the list of users in the client logs repository.

UpdateMetrics: update the metrics in dynamodb. Merges with existing metrics.

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import cStringIO
import json
import logging
import os
import re

from collections import Counter, defaultdict
from tornado import gen

from viewfinder.backend.base import retry, util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import metric
from viewfinder.backend.storage import file_object_store, s3_object_store, store_utils
from viewfinder.backend.storage.object_store import ObjectStore

# AWS production instance names.
# TODO(marc): how reliable is this?
kEC2InstanceRe = r'(i-[a-f0-9]+)$'

kDayRe = r'(\d{4})-(\d{2})-(\d{2})'
kTimeRe = r'(\d{2}):(\d{2}):(\d{2}):(\d{3})'

################## Server log regexps. ###################
# Some regular expressions to parse log file entries. We don't bother using a compiled version of each
# since python caches the last 100 regexps used on match() or search().
# Single log line. extracts (date, time, pid, module, message).
kLineRe = r'([-0-9]+) ([-:\.0-9]+) (\[pid:\d+\]) (\w+:\d+): ([^\n]+$)'
# Date from server log file names. Extract (date, time).
kDateRe = r'(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2}.\d+)$'
# Message part of a log line for user_op_manager SUCCESS. Extracts (user, device, op, class, method_name).
kSuccessMsgRe = r'SUCCESS: user: (\d+), device: (\d+), op: ([-_0-9a-zA-Z]+), method: (\w+)\.(\w+) .*$'
# Message part of a log line for user_op_manager EXECUTE. Extracts (user, device, op, class, method_name, request).
kExecuteMsgRe = r'EXECUTE: user: (\d+), device: (\d+), op: ([-_0-9a-zA-Z]+), method: (\w+)\.(\w+): (.*)$'
# Message part of a log line for user_op_manager ABORT. Extracts (user, device, op, class, method_name, request).
kAbortMsgRe = r'ABORT: user: (\d+), device: (\d+), op: ([-_0-9a-zA-Z]+), method: (\w+)\.(\w+) (.*)$'
# Ping request with full message. Extract the request dict.
kPingMsgRe = r'/ping OK: request: (.*)$'
# Ping request with full message (using new format). Extract the request and response dicts.
kNewPingMsgRe = r'ping OK: request: (.*) response: (.*)$'
# Code location line of a trace dump. Used to split the stack trace.
kTraceCodeLine = r'( File "/home/[^"]+", line [0-9]+, in [^ ]+)'
# Code location line of a trace dump. Used to extract the file, line and method.
kCodeLocationLine = r' File "([^"]+)", line ([0-9]+), in ([^ ]+)'

################## Client log regexps. ###################
# Full path to a client-generated log file. <user_id>/<date>/dev-<device_id>-<time>-<version>.(analytics|log|crash).gz
# Extract: user_id, device_id, version, analytics|log|crash
# Some user analytics logs don't have a version. For those, the third group will be None.
# The millisecond part of the time can also be missing. The (?:...) expression is not saved to a group.
kUserLogPathRe = r'^(\d+)/[-0-9]+/dev-(\d+)-\d+-\d+\-\d+(?:\.\d+)?(?:-(.*))?\.(analytics|log|crash)(?:\.gz)?$'

class ServerLogsPaths(object):
  """Hold various paths for the server logs."""
  SOURCE_LOGS_BUCKET = ObjectStore.SERVER_LOG
  MERGED_LOGS_BUCKET = ObjectStore.SERVER_DATA

  # A few paths.
  kMergedLogsPrefix = 'merged_server_logs'
  kRegistryName = 'PROCESSED'

  def __init__(self, application, log_type):
    """Application is the name of the binary that generated the logs.
    eg: dbchk.py, itunes-trends.py etc... For the backend, the name is fixed at 'viewfinder'.
    log_type is either 'full' or 'error'.
    """
    self._app = application
    self._log_type = log_type

  def RawDirectory(self):
    """The base directory for raw logs."""
    return os.path.join(self._app, self._log_type)

  def MergedDirectory(self):
    """Base directory for the merged logs."""
    return os.path.join(self.kMergedLogsPrefix, self._app, self._log_type)

  def ProcessedRegistryPath(self):
    """Path to the registry file containing the list of processed raw logs."""
    return os.path.join(self.MergedDirectory(), self.kRegistryName)

  def RawLogPathToInstance(self, path):
    """Given the full path to a raw log, return the instance name, or None if parsing fails."""
    tokens = path.split('/')
    if len(tokens) != 5 or tokens[0] != self._app or tokens[1] != self._log_type:
      return None
    return tokens[3]

  def _SplitLogPathName(self, path):
    """Extract (date, instance) from the full path to a merged log file. Return None if parsing fails."""
    path_tokens = path.split('/')
    if len(path_tokens) != 5 or path_tokens[0] != self.kMergedLogsPrefix or \
       path_tokens[1] != self._app or path_tokens[2] != self._log_type:
      return None
    return (path_tokens[3], path_tokens[4])

  def MergedLogPathToInstance(self, path):
    """Extract the instance name from a merged log path. Return None if parsing fails."""
    parsed = self._SplitLogPathName(path)
    return parsed[1] if parsed is not None else None

  def MergedLogPathToDate(self, path):
    """Extract the date from a merged log path. Return None if parsing fails."""
    parsed = self._SplitLogPathName(path)
    return parsed[0] if parsed is not None else None


class UserAnalyticsLogsPaths(object):
  """Hold various paths for a single user's analytics logs."""
  SOURCE_LOGS_BUCKET = ObjectStore.USER_LOG
  MERGED_LOGS_BUCKET = ObjectStore.SERVER_DATA

  # A few paths.
  kMergedLogsPrefix = 'merged_user_analytics'
  kRegistryDir = 'PROCESSED'

  def __init__(self, user_id):
    """user_id is the user's viewfinder ID."""
    self._user_id = user_id

  def RawDirectory(self):
    """The base directory for analytics logs."""
    return self._user_id + '/'

  def MergedDirectory(self):
    """Base directory for the merged logs."""
    return self.kMergedLogsPrefix + '/'

  def ProcessedRegistryPath(self):
    """Path to the registry file containing the list of processed analytics logs for the given user."""
    return os.path.join(self.MergedDirectory(), self.kRegistryDir, self._user_id)

  def ParseRawLogPath(self, path):
    """Parse the full path to a user log file.
    Returns a tuple consisting of: (type, user_id, device_id, version). Currently-known types are "analytics" or "log".
    Some log files do not have a version in the path, in which case the version part of the tuple will be None.
    Returns None if parsing failed.
    """
    res = re.match(kUserLogPathRe, path)
    if res is None:
      return None
    assert len(res.groups()) == 4
    user_id, device_id, version, typ = res.groups()
    assert user_id == self._user_id
    return (typ, user_id, device_id, version)


class UserCrashLogsPaths(object):
  """Hold various paths for a single user's crash logs."""
  SOURCE_LOGS_BUCKET = ObjectStore.USER_LOG
  MERGED_LOGS_BUCKET = ObjectStore.SERVER_DATA

  # A few paths.
  kMergedLogsPrefix = 'merged_user_crashes'
  kRegistryDir = 'PROCESSED'

  def __init__(self, user_id):
    """user_id is the user's viewfinder ID."""
    self._user_id = user_id

  def RawDirectory(self):
    """The base directory for this user's crash logs."""
    return self._user_id + '/'

  def MergedDirectory(self):
    """Base directory for this user's merged crash logs."""
    return os.path.join(self.kMergedLogsPrefix, self._user_id) + '/'

  def ParseRawLogPath(self, path):
    """Parse the full path to a user crash file.
    Returns a tuple consisting of: (user_id, date, filename) or None if parsing failed.
    """
    components = path.split('/')
    if len(components) != 3:
      return None
    assert components[0] == self._user_id, '%r vs %r' % (components[0], self._user_id)
    return tuple(components)

  def ParseMergedLogPath(self, path):
    """Parse the full path to a user merged crash file.
    Returns a tuple consisting of: (user_id, date, filename) or None if parsing failed.
    """
    components = path.split('/')
    if len(components) != 4 or components[0] != self.kMergedLogsPrefix:
      return None
    assert components[1] == self._user_id, '%r vs %r' % (components[1], self._user_id)
    return tuple(components[1:])


def IsEC2Instance(instance):
  """Return true if the instance name passed in matches the AWS instance naming pattern."""
  return re.match(kEC2InstanceRe, instance) is not None


def DayTimeStringsToUTCTimestamp(day, time):
  """Given day (YYYY-MM-DD) and time (HH:MM:SS:ms) strings, return the timestamp in UTC, or None if parsing failed."""
  try:
    hour, minute, second, _ = re.match(kTimeRe, time).groups()
    return util.ISO8601ToUTCTimestamp(day, hour=int(hour), minute=int(minute), second=int(second))
  except Exception as e:
    logging.warning('Error parsing day and time strings: %s %s, error: %r' % (day, time, e))
    return None


def ParseLogLine(line):
  """Attempt to parse a log line and extract day, time, module and msg. Returns None if regexp match failed."""
  parsed = re.match(kLineRe, line)
  if not parsed:
    return None
  try:
    day, time, pid, module, msg = parsed.groups()
    return (day, time, module, msg)
  except Exception as e:
    logging.warning('RE matched "%s", but extracted wrong numbers of items: %r' % (line, e))
    return None


def ParseSuccessMsg(msg):
  """Attempt to parse the message for a user_op_manager SUCCESS line and extract user, device, op, class, and method.
  Return None otherwise.
  """
  parsed = re.match(kSuccessMsgRe, msg)
  if not parsed:
    return None
  try:
    user, device, op, class_name, method_name = parsed.groups()
    return (user, device, op, class_name, method_name)
  except Exception as e:
    logging.warning('RE matched "%s", but extracted wrong numbers of items: %r' % (msg, e))
    return None


def ParseExecuteMsg(msg):
  """Attempt to parse the message for a user_op_manager EXECUTE line and extract user, device, op, class, and method.
  Return None otherwise.
  """
  parsed = re.match(kExecuteMsgRe, msg)
  if not parsed:
    return None
  try:
    user, device, op, class_name, method_name, request = parsed.groups()
    return (user, device, op, class_name, method_name, request)
  except Exception as e:
    logging.warning('RE matched "%s", but extracted wrong numbers of items: %r' % (msg, e))
    return None


def ParseAbortMsg(msg):
  """Attempt to parse the message for a user_op_manager ABORT line and extract user, device, op, class, and method.
  Return None otherwise.
  """
  parsed = re.match(kAbortMsgRe, msg)
  if not parsed:
    return None
  try:
    user, device, op, class_name, method_name, request = parsed.groups()
    return (user, device, op, class_name, method_name, request)
  except Exception as e:
    logging.warning('RE matched "%s", but extracted wrong numbers of items: %r' % (msg, e))
    return None


def ParsePingMsg(msg):
  """Attempt to parse the message for a ping. Return the request string (json-ified dict).
  Return None otherwise.
  """
  parsed = re.match(kPingMsgRe, msg)
  if not parsed:
    return None
  try:
    return parsed.group(1)
  except IndexError as e:
    logging.warning('RE matched "%s", but extracted wrong numbers of items: %r' % (msg, e))
    return None


def ParseNewPingMsg(msg):
  """Attempt to parse the message for a ping (in the new format). Return the request and response strings
  (json-ified dict) if parsing succeeded. Return None otherwise.
  """
  parsed = re.match(kNewPingMsgRe, msg)
  if not parsed:
    return None
  try:
    return (parsed.group(1), parsed.group(2))
  except IndexError as e:
    logging.warning('RE matched "%s", but extracted wrong numbers of items: %r' % (msg, e))
    return None


def ParseTraceDump(msg):
  """Parse a full backtrace. Returns a list of strings split by the location lines (File ..., line ..., in ...).
  These lines are included in the output.
  """
  return re.split(kTraceCodeLine, msg)


def ParseTraceLocationLine(msg):
  """Parse the location line of a stack trace. If successfully parsed, returns (filename, line, method)."""
  parsed = re.match(kCodeLocationLine, msg)
  if not parsed:
    return None
  try:
    return (parsed.group(1), parsed.group(2), parsed.group(3))
  except IndexError as e:
    logging.warning('RE matched "%s", but extracted wrong number of items: %r' % (msg, e))
    return None


@gen.engine
def GetRegistry(logs_store, path, callback):
  """Open the registry at 'path' in S3. Returns a list of filenames or None if the file does not exist."""
  contents = ''
  contents = yield gen.Task(logs_store.Get, path, must_exist=False)
  if contents is None:
    callback(None)
    return

  buf = cStringIO.StringIO(contents)
  buf.seek(0)
  files = []
  entries = buf.readlines()
  for f in entries:
    if f:
      files.append(f.strip())
  buf.close()
  callback(files)


@gen.engine
def WriteRegistry(logs_store, path, processed_list, callback):
  """Turns 'processed_list' into a new-line separated string and writes it to 'path' in S3."""
  contents = '\n'.join(processed_list)
  yield gen.Task(logs_store.Put, path, contents)
  callback()


@gen.engine
def ListClientLogUsers(logs_store, callback):
  """Return the list of all users with data in the client log repository.
  Returns a sorted list of user ids.
  """
  user_dir_re = re.compile(r'^([0-9]+)/$')
  subdirs, _ = yield gen.Task(store_utils.ListFilesAndDirs, logs_store, '/')
  # Only return numeric directory names.
  filtered = []
  for s in subdirs:
    res = user_dir_re.match(s)
    if res is not None:
      filtered.append(res.group(1))

  callback(sorted(filtered))


# Timestamps at which to write the metrics entry for various log types.
# Dictionary of 'log_type' to (hour, minute, second)
# We keep a sizeable amount of space between each to be able to add more. Since these are generated daily and
# are using an arbitrary timestamp anyway, minutes and seconds don't matter much.
# (12, 0, 0) should not be used. It is the default when hms_tuple is not passed to UpdateMetrics.
kDailyMetricsTimeByLogType = {
  # Source: server logs
  'active_users': (12, 1, 0),
  'device_installs': (12, 1, 1),
  'device_count': (12, 1, 2),
  # Source: client analytics logs
  'analytics_logs': (12, 2, 0),
  # Source: dynamodb table sizes (job get_table_sizes.py)
  'dynamodb_stats': (12, 3, 0),
  # Source: misc
  'itunes_trends': (12, 5, 0),
  # Source: dynamodb stats (job analyze_dynamodb.py). Broken down by category of stats (eg: user, viewpoint, etc..)
  'dynamodb_user': (13, 0, 0)
}

@gen.engine
def UpdateMetrics(db_client, day_stats, callback, dry_run=True, prefix_to_erase=None, hms_tuple=None):
  """Write 'day_stats' to the metrics table. First lookup any existing metrics and update them.
  'day_stats' is a dictionary of {day_in_iso8601: DotDict}.
  If 'dry_run' is True, don't commit the changes to the metrics table, but perform all the work and log to info.
  If 'prefix_to_erase' is not None, we first replace the passed-in prefix with an empty dotdict.
  If 'hms_tuple' is not None, the timestamp for the metric entry will be with the specified hour/minute/second,
  otherwise, we use noon. To help with consistency, hms_tuple should come from kDailyMetricsTimeByLogType above.

  For example, given the existing metric: { itunes: { downloads: { 'US': 5, 'UK': 3 }, update: { ... }}}
  We can either:
    - Replace the downloads numbers: (the entire tree under 'prefix_to_erase' gets replaced)
      UpdateMetrics({'2013-02-01': {'itunes': {'downloads': { 'DE': 3, 'FR': 1 }}}}, prefix_to_erase='itunes.downloads')
      resulting in: { itunes: { downloads: { 'DE': 3, 'FR': 1 }, update: { ... }}}
    - Or we can update with partial stats:
      UpdateMetrics({'2013-02-01': {'itunes': { 'downloads': { 'DE': 3, 'FR': 1 }}}}, replace=False)
      resulting in: { itunes: { downloads: { 'US': 5, 'UK': 3, 'DE': 3, 'FR': 3 }, update: { ... }}}
  """
  if len(day_stats) == 0:
    callback()
    return

  cluster = metric.LOGS_STATS_NAME
  group_key = metric.Metric.EncodeGroupKey(cluster, metric.Metric.FindIntervalForCluster(cluster, 'daily'))

  # Convert YYYY-MM-DD into the timestamp for noon UTC.
  h, m, s = hms_tuple if hms_tuple is not None else (12, 0, 0)
  timestamps = [(util.ISO8601ToUTCTimestamp(day, hour=h, minute=m, second=s), day) for day in sorted(day_stats.keys())]

  # Query Metrics table for all metrics between the timestamps we have data for.
  existing_metrics = yield gen.Task(metric.Metric.QueryTimespan, db_client, group_key,
                                    timestamps[0][0], timestamps[-1][0])
  existing_dict = dict((m.timestamp, m) for m in existing_metrics)

  tasks = []
  for t, day in timestamps:
    data = day_stats[day]
    prev_metric = existing_dict.get(t, None)

    payload = json.dumps(data)
    if prev_metric is None:
      logging.info('%s: new metric: %r' % (day, payload))
    else:
      prev_payload = prev_metric.payload
      # We do this twice, it's simpler than making deepcopy work on DotDict.
      prev_data = DotDict(json.loads(prev_payload))
      new_data = DotDict(json.loads(prev_payload))
      if prefix_to_erase is not None:
        # We can't call 'del' on a DotDict's internals, so simply replace with an empty dotdict, we'll be repopulating.
        new_data[prefix_to_erase] = DotDict()

      # DotDict doesn't have an update() method.
      flat = new_data.flatten()
      flat.update(data.flatten())
      new_data = DotDict(flat)

      payload = json.dumps(new_data)
      if new_data.flatten() == prev_data.flatten():
        logging.info('%s: metric has not changed, skipping' % day)
        continue
      else:
        logging.info('%s: changed metric: %s -> %s' % (day, prev_payload, payload))

    if not dry_run:
      new_metric = metric.Metric.Create(group_key, 'logs_daily', t, payload)
      tasks.append(gen.Task(new_metric.Update, db_client))

  yield tasks
  callback()


class DayUserRequestStats(object):
  """Class to keep track of request count per user for a given day."""
  def __init__(self, day):
    self.day = day
    self._active_all = Counter()
    self._active_post = Counter()
    self._active_share = Counter()
    self._active_view = Counter()

  def ActiveAll(self, user, val=1):
    self._active_all[user] += val

  def ActivePost(self, user, val=1):
    self._active_post[user] += val

  def ActiveShare(self, user, val=1):
    self._active_share[user] += val

  def ActiveView(self, user, val=1):
    self._active_view[user] += val

  def PrintSummary(self):
    logging.info('active users for %s: all=%d post=%d share=%d view=%d' %
                 (self.day, len(self._active_all), len(self._active_post), len(self._active_share),
                  len(self._active_view)))

  def SummaryDict(self, prefix):
    if prefix and not prefix.endswith('_'):
      prefix += '_'
    return {'%sactive_all' % prefix: len(self._active_all),
            '%sactive_post' % prefix: len(self._active_post),
            '%sactive_share' % prefix: len(self._active_share),
            '%sactive_view' % prefix: len(self._active_view) }

  def MergeFrom(self, src):
    self._active_all += src._active_all
    self._active_post += src._active_post
    self._active_share += src._active_share
    self._active_view += src._active_view

  def ToDotDict(self):
    """Returns the full data contained in this object in the form of a dotdict."""
    dt = DotDict()
    dt['user_requests.all'] = self._active_all
    dt['user_requests.post'] = self._active_post
    dt['user_requests.share'] = self._active_share
    dt['user_requests.view'] = self._active_view
    return dt

  def FromDotDict(self, dt):
    """Load full data from a dotdict. This overwrites any existing data."""
    assert 'user_requests' in dt
    base = dt['user_requests']
    for k, v in base['all'].iteritems():
      self.ActiveAll(k, v)
    for k, v in base['post'].iteritems():
      self.ActivePost(k, v)
    for k, v in base['share'].iteritems():
      self.ActiveShare(k, v)
    for k, v in base['view'].iteritems():
      self.ActiveView(k, v)
