# Copyright 2012 Viewfinder Inc. All Rights Reserved
"""Interface to the iTunes Connect sales and trend.

Fetches daily download stats from iTunes Connect and saves them to the metrics table.
Specify the apple user to log in with (eg: --user=marc to use marc@emailscrubbed.com). We get the user's
apple password from the secret 'itunes_connect_${user}'.
Default user is 'itunes_viewer', a special user with "sales" data access only.

Run with:
$ python -m viewfinder.backend.logs.itunes_trends --start_date=2013-01-20

Appropriate for cron: Detect start date, update metrics table. Don't run if last run was less than 6h ago.
$ python -m viewfinder.backend.logs.itunes_trends --dry_run=False --smart_scan=True --hours_between_runs=6

 ExceptionOptions:
- user: default=itunes_viewer: apple user. We expand this to ${user}@emailscrubbed.com
- vendor_id: default=<our ID>: the vendor ID, from the iTunes Connect dashboard.
- dry_run: default=True: display stats only, do not update Metrics table or write job summary.
- start_date: default=None: look up stats from that date until yesterday. format: YYYY-MM-DD.
- smart_scan: default=False: determine the start date from previous successful run.
- require_lock: default=True: grab the job:itunes_trends lock for the duration of the job.
- hours_between_runs: default=0: don't run if the last successful run was less than this many hours ago.

"""

import gzip
import cStringIO
import getpass
import json
import logging
import os
import re
import sys
import time
import traceback
import urllib
import urllib2

from tornado import gen, options
from urlparse import urljoin
from viewfinder.backend.base import constants, main, secrets, util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import db_client, metric
from viewfinder.backend.db.job import Job
from viewfinder.backend.logs import logs_util
from viewfinder.backend.services import itunes_trends_codes
from viewfinder.backend.storage.object_store import ObjectStore

options.define('user', default='itunes_viewer', help='User for iTunesConnect. Will expand to user@emailscrubbed.com and '
                                                     'lookup the itunes password in secrets/itunes_connect_${user}')
# vendor_id comes from the iTunes Connect dashboard.
options.define('vendor_id', default='85575078', help='iTunes vendor ID')

options.define('dry_run', default=True, help='Print output only, do not write to metrics table.')
options.define('start_date', default=None, help='Lookup stats from date onwards (YYYY-MM-DD)')
options.define('smart_scan', type=bool, default=False,
               help='determine start_date from previous successful runs. Overrides start_date.')
options.define('require_lock', type=bool, default=True,
               help='attempt to grab the job:itunes_trends lock before running. Exit if acquire fails.')
options.define('hours_between_runs', type=int, default=0,
               help='minimum time since start of last successful run (with dry_run=False)')
options.define('download_from_s3', type=bool, default=False,
               help='Fetch raw gzipped files from S3 (if false, fetch from iTunesConnect)')

kITCBaseURL = 'https://reportingitc.apple.com/autoingestion.tft'
kS3Bucket = ObjectStore.SERVER_DATA
kS3Base = 'itunes-trends/'

class ITunesTrends(object):
  def __init__(self, apple_id, password, vendor_id, html_retries=3):
    self._apple_id = apple_id
    self._password = password
    self._vendor_id = vendor_id
    self._html_retries=3

    self._form_fields = None
    self._available_days = None
    self._available_weeks = None

    self._object_store = ObjectStore.GetInstance(kS3Bucket)

  def _Fetch(self, url, data=None):
    """Attempt to fetch 'url' with optional 'data'. We retry self._retry times, regardless of the error."""
    retries = 0
    while True:
      logging.info('fetching (%d) %s' % (retries, url))
      request = urllib2.Request(url, data)
      handle = urllib2.urlopen(request)
      logging.info('fetch reply headers: %s' % handle.info())
      return handle.read()
      try:
        pass
      except Exception:
        if retries >= self._html_retries:
          raise

      time.sleep(2**retries)
      retries += 1


  @gen.engine
  def FetchOneDay(self, day, callback):
    """Fetch a single day's worth of data. Exception could be due to http errors, unavailable date, or failed parsing.
    TODO(marc): handle these cases separately.
    """
    s3_filename = os.path.join(kS3Base, '%s.gz' % day)

    def DownloadFromiTunes():
      # We use our own date format in the entire tool. Only now do we convert to iTuneConnect's YYYYMMDD.
      y, m, d = day.split('-')
      itunes_date = '%s%s%s' % (y, m, d)
      data = urllib.urlencode({'USERNAME': self._apple_id,
                               'PASSWORD': self._password,
                               'VNDNUMBER': self._vendor_id,
                               'TYPEOFREPORT': 'Sales',
                               'DATETYPE': 'Daily',
                               'REPORTTYPE': 'Summary',
                               'REPORTDATE': itunes_date })
      buf = self._Fetch(kITCBaseURL, data)
      return buf

    def ParseContents(contents):
      result = DotDict()
      skipped_lines = []
      for line in contents.splitlines():
        tokens = line.split('\t')
        if tokens[0] == 'Provider':
          # Skip header line.
          skipped_lines.append(line)
          continue
        # Replace dots with underscores as we'll be using the version in a DotDict.
        version = tokens[5].replace('.', '_')
        if not version or version == ' ':
          # subscriptions do not have a version, use 'all'.
          version = 'all'
        type_id = tokens[6]
        # Use the type id if we don't have a name for it.
        type_name = itunes_trends_codes.PRODUCT_TYPE_IDENTIFIER.get(type_id, type_id)
        units = int(tokens[7])
        # Ignore proceeds, it does not reflect in-app purchases.
        store = tokens[12]
        result['itunes.%s.%s.%s' % (type_name, version, store)] = units
      assert len(skipped_lines) <= 1, 'Skipped too many lines: %r' % skipped_lines
      return result

    # Failures in any of Get/Download/Put will interrupt this day's processing.
    if options.options.download_from_s3:
      logging.info('S3 get %s' % s3_filename)
      buf = yield gen.Task(self._object_store.Get, s3_filename)
    else:
      buf = DownloadFromiTunes()
      logging.info('S3 put %s' % s3_filename)
      yield gen.Task(self._object_store.Put, s3_filename, buf)

    iobuffer = cStringIO.StringIO(buf)
    gzipIO = gzip.GzipFile('rb', fileobj=iobuffer)
    contents = gzipIO.read()
    iobuffer.close()
    logging.info('Contents: %s' % contents)

    callback(ParseContents(contents))


@gen.engine
def DetermineStartDate(client, job, callback):
  """If smart_scan is true, lookup the start date from previous job summaries, otherwise use --start_date.
  --start_date and job summary days are of the form YYYY-MM-DD.
  """
  start_date = options.options.start_date

  # Lookup previous runs started in the last week.
  if options.options.smart_scan:
    # Search for successful full-scan run in the last week.
    last_run = yield gen.Task(job.FindLastSuccess, with_payload_key='stats.last_day')
    if last_run is None:
      logging.info('No previous successful scan found, rerun with --start_date')
      callback(None)
      return

    last_run_start = last_run['start_time']
    if (last_run_start + options.options.hours_between_runs * constants.SECONDS_PER_HOUR > time.time()):
      logging.info('Last successful run started at %s, less than %d hours ago; skipping.' %
                   (time.asctime(time.localtime(last_run_start)), options.options.hours_between_runs))
      callback(None)
      return

    # Start start_date to the last processed day + 1.
    last_day = last_run['stats.last_day']
    start_time = util.ISO8601ToUTCTimestamp(last_day) + constants.SECONDS_PER_DAY
    start_date = util.TimestampUTCToISO8601(start_time)
    logging.info('Last successful run (%s) scanned up to %s, setting start date to %s' %
                 (time.asctime(time.localtime(last_run_start)), last_day, start_date))

  callback(start_date)


@gen.engine
def RunOnce(client, job, apple_id, password, callback):
  start_date = yield gen.Task(DetermineStartDate, client, job)
  if start_date is None:
    logging.info('Start date not specified, last run too recent, or smart_scan could not determine a date; exiting.')
    callback(None)
    return

  query_dates = []
  start_time = util.ISO8601ToUTCTimestamp(start_date)
  today = util.NowUTCToISO8601()
  while start_time < time.time():
    date = util.TimestampUTCToISO8601(start_time)
    if date != today:
      query_dates.append(date)
    start_time += constants.SECONDS_PER_DAY

  logging.info('fetching data for dates: %r' % query_dates)
  results = {}
  itc = ITunesTrends(apple_id, password, options.options.vendor_id)
  failed = False
  for day in query_dates:
    if failed:
      break
    try:
      result = yield gen.Task(itc.FetchOneDay, day)
      if not result:
        # We don't get an exception when iTunesConnect has no data. We also don't want to
        # fail as there's no way it will have this data later.
        logging.warning('No data for day %s' % day)
      else:
        results[day] = result
    except Exception:
      msg = traceback.format_exc()
      logging.warning('Error fetching iTunes Connect data for day %s: %s', day, msg)
      failed = True

  if len(results) == 0:
    callback(None)
  else:
    # Replace the entire 'itunes' category of previous metrics. This is so we can fix any processing errors we
    # may have had.
    hms = logs_util.kDailyMetricsTimeByLogType['itunes_trends']
    yield gen.Task(logs_util.UpdateMetrics, client, results, prefix_to_erase='itunes',
                   dry_run=options.options.dry_run, hms_tuple=hms)
    callback(sorted(results.keys())[-1])


@gen.engine
def _Start(callback):
  """Grab a lock on job:itunes_trends and call RunOnce. If we get a return value, write it to the job summary."""
  assert options.options.user is not None and options.options.vendor_id is not None
  apple_id = '%s@emailscrubbed.com' % options.options.user
  # Attempt to lookup iTunes Connect password from secrets.
  password = secrets.GetSecret('itunes_connect_%s' % options.options.user)
  assert password

  client = db_client.DBClient.Instance()
  job = Job(client, 'itunes_trends')

  if options.options.require_lock:
    got_lock = yield gen.Task(job.AcquireLock)
    if got_lock == False:
      logging.warning('Failed to acquire job lock: exiting.')
      callback()
      return

  result = None
  job.Start()
  try:
    result = yield gen.Task(RunOnce, client, job, apple_id, password)
  except:
    # Failure: log run summary with trace.
    msg = traceback.format_exc()
    logging.info('Registering failed run with message: %s' % msg)
    yield gen.Task(job.RegisterRun, Job.STATUS_FAILURE, failure_msg=msg)
  else:
    if result is not None and not options.options.dry_run:
      # Successful run with data processed and not in dry-run mode: write run summary.
      stats = DotDict()
      stats['last_day'] = result
      logging.info('Registering successful run with stats: %r' % stats)
      yield gen.Task(job.RegisterRun, Job.STATUS_SUCCESS, stats=stats)
  finally:
    yield gen.Task(job.ReleaseLock)

  callback()


if __name__ == '__main__':
  sys.exit(main.InitAndRun(_Start))
