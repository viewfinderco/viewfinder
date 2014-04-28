# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Generate graphs from metrics data and output as pdf.

The PDF files are written to S3 and links send by email.

Simply run with:
python -m viewfinder.backend.logs.generate_pdf_report --devbox

Options:
- require_lock: default=True: grab a lock on 'generate_pdf_reports' before running
- analysis_intervals_days: default=14,90: generate one file for each interval
- upload_to_s3: default=True: upload PDF files to S3
- s3_dest: default='pdf_reports': directory in S3 to write to (inside bucket 'serverdata')
- local_working_dir: default='/tmp/': write pdf files to this local dir (they are not deleted)
- send_email: default=True: send an email report. If false, uses the LoggingEmailManager
- email: default=marketing@emailscrubbed.com: email recipient
- s3_url_expiration_days: default=14: time to live for the generated S3 urls.
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import json
import logging
import os
import re
import sys
import time
import traceback

from collections import Counter, defaultdict
from datetime import datetime
from tornado import gen, options
from viewfinder.backend.base import constants, main, retry, util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import db_client, metric
from viewfinder.backend.db.job import Job
from viewfinder.backend.logs import logs_util
from viewfinder.backend.services.email_mgr import EmailManager, LoggingEmailManager, SendGridEmailManager
from viewfinder.backend.storage.object_store import ObjectStore

import matplotlib.pyplot as plt
from matplotlib import dates as mdates
from matplotlib.backends.backend_pdf import PdfPages

options.define('require_lock', default=True, help='Acquire job lock on "generate_pdf_reports" before running')
options.define('analysis_intervals_days', default=[14, 90], help='Intervals to analyze, in days')
options.define('upload_to_s3', default=True, help='Upload generated files to S3')
options.define('s3_dest', default='pdf_reports', help='S3 directory to write to (in serverdata bucket)')
options.define('local_working_dir', default='/tmp/', help='Local directory to write generated pdf files to')
options.define('send_email', default=True, help='Email links to reports')
options.define('email', default='analytics-reports@emailscrubbed.com', help='Email recipient')
options.define('s3_url_expiration_days', default=14, help='Expiration time in days for S3 URLs')

# Retry policy for uploading files to S3.
kS3UploadRetryPolicy = retry.RetryPolicy(max_tries=5, timeout=300,
                                         min_delay=1, max_delay=30,
                                         check_exception=retry.RetryPolicy.AlwaysRetryOnException)

# Metrics to sum up into a new one.
kSummedMetrics = [ (re.compile(r'itunes\.downloads.*'), r'itunes.downloads'),
                   (re.compile(r'itunes\.updates.*'), r'itunes.updates'),
                 ]

# Metric selection.
kFilteredMetrics = [ r'itunes\.updates',
                     r'itunes\.download',
                     r'db\.table\.count\.(Comment|Photo|User)$',
                     r'active_users\.requests_(all|share|post)\.(1d|7d|30d)',
                   ]

# Metrics to draw on the same graph, associated title and legend.
kPlotAggregates = {
  r'(active_users\.requests_all)\.(1d|7d|30d)': {
    'title_rep': r'Active users (all requests)',
    'legend_rep': r'\2',
  },
  r'(active_users\.requests_post)\.(1d|7d|30d)': {
    'title_rep': r'Active users posting comments',
    'legend_rep': r'\2',
  },
  r'(active_users\.requests_share)\.(1d|7d|30d)': {
    'title_rep': r'Active users sharing photos',
    'legend_rep': r'\2',
  },
  r'db\.table\.count\.(Comment|Photo|User)': {
    'title_rep': r'Total \1s',
    'legend_rep': None,
  },
  r'itunes\.(downloads|update)': {
    'title_rep': r'Daily iTunes \1',
    'legend_rep': None,
  },
}

def SerializeMetrics(metrics):
  def _SkipMetric(name):
    for regex in kFilteredMetrics:
      res = re.match(regex, k)
      if res is not None:
        return False
    return True

  def _AggregateMetric(running_sum, metric_name):
    """Given a metric name, determine whether we sum it into a different metric name or not.
    Returns whether the original metric needs to be processed.
    """
    keep = True
    for regex, replacement, in kSummedMetrics:
      res = regex.sub(replacement, metric_name)
      if res != metric_name:
        keep = False
        if not _SkipMetric(res):
          running_sum[res] += v
    return keep

  data = defaultdict(list)
  prev_metrics = {}
  seen_vars = set()
  for m in metrics:
    running_sum = Counter()
    timestamp = m.timestamp
    payload = DotDict(json.loads(m.payload)).flatten()
    for k, v in payload.iteritems():
      keep_original = _AggregateMetric(running_sum, k)
      if keep_original and not _SkipMetric(k):
        running_sum[k] += v
    for k, v in running_sum.iteritems():
      data[k].append((timestamp, v))

  return data

@gen.engine
def ProcessOneInterval(client, num_days, callback):
  end_time = time.time()
  start_time = time.time() - constants.SECONDS_PER_DAY * num_days

  selected_interval = metric.LOGS_INTERVALS[-1]
  group_key = metric.Metric.EncodeGroupKey(metric.LOGS_STATS_NAME, selected_interval)
  logging.info('Query performance counters %s, range: %s - %s, resolution: %s'
                % (group_key, time.ctime(start_time), time.ctime(end_time), selected_interval.name))

  metrics = list()
  start_key = None
  while True:
    new_metrics = yield gen.Task(metric.Metric.QueryTimespan, client, group_key,
                                 start_time, end_time, excl_start_key=start_key)
    if len(new_metrics) > 0:
      metrics.extend(new_metrics)
      start_key = metrics[-1].GetKey()
    else:
      break

  data = SerializeMetrics(metrics)

  def _DetermineTitle(metric_name):
    for regex, props in kPlotAggregates.iteritems():
      if not re.match(regex, metric_name):
        continue
      tres = re.sub(regex, props['title_rep'], metric_name)
      legend_rep = props.get('legend_rep', None)
      if not legend_rep:
        return (tres, None)
      else:
        vres = re.sub(regex, legend_rep, metric_name)
        return (tres, vres)
    return (metric_name, metric_name)

  def _SaveFig(legend_data):
    logging.info('Drawing with legend_data=%r' % legend_data)
    if legend_data:
      # Shrink the figure vertically.
      box = plt.gca().get_position()
      plt.gca().set_position([box.x0, box.y0 + box.height * 0.2, box.width, box.height * 0.8])

      # Put a legend below current axis
      plt.legend(legend_data, loc='upper center', bbox_to_anchor=(0.5, -0.20),
                 fancybox=True, shadow=True, ncol=5)
    elif plt.legend():
      plt.legend().set_visible(False)

    # Write to pdf as a new page.
    plt.savefig(pp, format='pdf')

    # Clear all.
    plt.clf()
    plt.cla()

  # PdfPages overwrites any existing files. Should unlink fail, we'll let the exception surface.
  filename = '%dd-viewfinder-report.%s.pdf' % (num_days, util.NowUTCToISO8601())
  pp = PdfPages(os.path.join(options.options.local_working_dir, filename))
  last_entry = None
  legend_strings = []
  for k in sorted(data.keys()):
    timestamps = []
    y_axis = []
    for a, b in data[k]:
      dt = datetime.utcfromtimestamp(a)
      dt = dt.replace(hour=0)
      timestamps.append(dt)
      y_axis.append(b)

    x_axis = mdates.date2num(timestamps)

    title, label = _DetermineTitle(k)

    if last_entry is not None and last_entry != title:
      # Different data set: draw figure, write to pdf and clear everything.
      _SaveFig(legend_strings)
      legend_strings = []

    last_entry = title
    if label:
      legend_strings.append(label)

    # autofmt_xdate sets the formatter and locator to AutoDate*. It seems smart enough.
    # plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m/%d/%Y'))
    # plt.gca().xaxis.set_major_locator(mdates.DayLocator())
    plt.title(title)
    plt.grid(True)

    # Plot data.
    plt.plot_date(x_axis, y_axis, '-')
    plt.gcf().autofmt_xdate()

  _SaveFig(legend_strings)
  pp.close()

  callback(filename)

@gen.engine
def UploadFiles(object_store, filenames, callback):
  for f in filenames:
    local_file = os.path.join(options.options.local_working_dir, f)
    contents = open(local_file, 'r').read()

    remote_file = os.path.join(options.options.s3_dest, f)

    # Assume 1MB/s transfer speed. If we don't have that good a connection, we really shouldn't be uploading big files.
    timeout = max(20.0, len(contents) / 1024 * 1024)
    yield gen.Task(retry.CallWithRetryAsync, kS3UploadRetryPolicy,
                   object_store.Put, remote_file, contents, request_timeout=timeout)
    logging.info('Uploaded %d bytes to S3 file %s' % (len(contents), remote_file))

  callback()


@gen.engine
def SendEmail(title, text, callback):
  args = {
    'from': 'analytics-reports@emailscrubbed.com',
    'fromname': 'Viewfinder reports',
    'to': options.options.email,
    'subject': title,
    'text': text
  }
  yield gen.Task(EmailManager.Instance().SendEmail, description=title, **args)
  callback()


@gen.engine
def SendReport(object_store, filename_dict, callback):
  text = 'Viewfinder statistics report:\n'
  text += '(URLs expire after %d days)\n\n' % options.options.s3_url_expiration_days
  for days in sorted(filename_dict.keys()):
    filename = filename_dict[days]
    remote_file = os.path.join(options.options.s3_dest, filename)
    url = object_store.GenerateUrl(remote_file,
                                   expires_in=constants.SECONDS_PER_DAY * options.options.s3_url_expiration_days,
                                   content_type='application/pdf')
    text += 'Past %d days: %s\n\n' % (days, url)

  title = 'Viewfinder statistics report: %s' % util.NowUTCToISO8601()
  yield gen.Task(SendEmail, title, text)
  callback()


@gen.engine
def RunOnce(client, callback):
  object_store = ObjectStore.GetInstance(ObjectStore.SERVER_DATA)
  filenames = {}

  for num_days in options.options.analysis_intervals_days:
    filename = yield gen.Task(ProcessOneInterval, client, num_days)
    filenames[num_days] = filename

  yield gen.Task(UploadFiles, object_store, filenames.values())
  yield gen.Task(SendReport, object_store, filenames)
  callback()


@gen.engine
def Start(callback):
  client = db_client.DBClient.Instance()

  job = Job(client, 'generate_pdf_reports')
  if options.options.require_lock:
    got_lock = yield gen.Task(job.AcquireLock)
    if got_lock == False:
      logging.warning('Failed to acquire job lock: exiting.')
      callback()
      return

  if options.options.send_email:
    # When running on devbox, this prompts for the passphrase. Skip if not sending email.
    EmailManager.SetInstance(SendGridEmailManager())
  else:
    EmailManager.SetInstance(LoggingEmailManager())

  # We never call job.Start() since we don't want a summary status written to the DB, just the lock.
  try:
    yield gen.Task(RunOnce, client)
  except:
    logging.error(traceback.format_exc())
  finally:
    yield gen.Task(job.ReleaseLock)

  callback()

if __name__ == '__main__':
  sys.exit(main.InitAndRun(Start))
