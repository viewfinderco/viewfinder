# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Handlers for database administration.

  MetricsHandler: main handler for detailed metrics. We don't use ajax-y tables, so there is no data handler.
"""
from tornado.escape import url_escape

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import base64
import json
import logging
import re
import time

from collections import Counter, defaultdict
from tornado import auth, gen, template
from viewfinder.backend.base import constants, handler, util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import db_client, metric, schema, vf_schema
from viewfinder.backend.www.admin import admin, formatters, data_table

kDefaultMetricName = 'itunes.downloads'

class MetricsHandler(admin.AdminHandler):
  """Provides a list of all datastore tables and allows each to be
  drilled down.
  """
  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  @admin.require_permission(level='support')
  @gen.engine
  def get(self):
    metric_name = self.get_argument('metric_name', kDefaultMetricName)
    end_time = int(self.get_argument('end-secs', time.time()))
    start_time = int(self.get_argument('start-secs', end_time - constants.SECONDS_PER_WEEK))

    # Select an appropriate interval resolution based on the requested time span.
    selected_interval = metric.LOGS_INTERVALS[-1]
    group_key = metric.Metric.EncodeGroupKey(metric.LOGS_STATS_NAME, selected_interval)
    logging.info('Query performance counters %s, range: %s - %s, resolution: %s'
                  % (group_key, time.ctime(start_time), time.ctime(end_time), selected_interval.name))

    metrics = list()
    start_key = None
    while True:
      new_metrics = yield gen.Task(metric.Metric.QueryTimespan, self._client, group_key,
                                   start_time, end_time, excl_start_key=start_key)
      if len(new_metrics) > 0:
        metrics.extend(new_metrics)
        start_key = metrics[-1].GetKey()
      else:
        break
    columns, data = _SerializeMetrics(metrics, metric_name)

    t_dict = {}
    t_dict.update(self.PermissionsTemplateDict())
    t_dict['col_names'] = columns
    t_dict['col_data'] = data
    t_dict['metric_name'] = metric_name
    t_dict['start_secs'] = start_time
    t_dict['end_secs'] = end_time
    self.render('metrics_table.html', **t_dict)

# This is very hacky: basically, we only care about some part of the metric name.
# eg: in itunes.downloads.1_2.US, we just want the US part. itunes.downloads is already removed, so the index
# we care about is the 1st (zero indexed) in the remainder.
kMetricSignificantLevel = { 'itunes.downloads': 1, 'itunes.inapp_subscriptions_auto_renew': 1, 'itunes.updates': 1 }

# Display and sort properties. Array of (regexp, sort_by_count, show_total_in_column_name).
# If the base metric name matches the regexp, we apply sort_by_cound and show_total_in_column_name.
# Defaults are: sort_by_count = False, show_total_in_column_name = False.
kSortByCount = [ ('itunes.*', True, True) ]

def _SerializeMetrics(metrics, metric_name):
  def _DisplayParams():
    for regexp, sort, show in kSortByCount:
      if re.match(regexp, metric_name):
        return (sort, show)
    return (False, False)

  columns = Counter()
  data = []
  for m in metrics:
    timestamp = m.timestamp
    d = defaultdict(int)
    d['day'] = util.TimestampUTCToISO8601(timestamp).replace('-', '/')

    dd = DotDict(json.loads(m.payload))
    if metric_name not in dd:
      continue
    payload = dd[metric_name].flatten()
    for k, v in payload.iteritems():
      if metric_name in kMetricSignificantLevel:
        k = k.split('.')[kMetricSignificantLevel[metric_name]]
      columns[k] += v
      d[k] += v
      d['Total'] += v
      columns['Total'] += v
    data.append(d)

  # We now have "columns" with totals for each column. We need to sort everything.
  sort_by_count, show_total = _DisplayParams()
  if sort_by_count:
    sorted_cols = columns.most_common()
  else:
    sorted_cols = sorted([(k, v) for k, v in columns.iteritems()])
  cols = ['Day']
  cols.append('Total %d' % columns['Total'] if show_total else 'Total')
  for k, v in sorted_cols:
    if k == 'Total':
      continue
    cols.append('%s %d' % (k, v) if show_total else k)

  sorted_data = []
  for d in reversed(data):
    s = [d['day'], d['Total']]
    for k, _ in sorted_cols:
      if k == 'Total':
        continue
      s.append(d[k] if d[k] > 0 else '')
    sorted_data.append(s)

  return (cols, sorted_data)
