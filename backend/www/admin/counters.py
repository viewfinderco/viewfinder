# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Handlers for viewing performance counter data.
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import json
import os
import time
import logging
from functools import partial
from tornado import auth, template, web

from viewfinder.backend.base import handler, counters
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import metric
from viewfinder.backend.db.db_client import RangeOperator
from viewfinder.backend.www.admin import admin

class CountersHandler(admin.AdminHandler):
  """Handler which returns the counter admin page."""
  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  @admin.require_permission(level='root')
  def get(self):
    logging.info('Counters: %r' % counters.counters)
    t_dict = self.PermissionsTemplateDict()
    t_dict['page_title'] = 'Viewfinder Backend Counters'
    t_dict['data_src'] = 'counters_data'
    t_dict['default_interval'] = '1h'
    self.render("counters.html", **t_dict)


class CountersDataHandler(admin.AdminHandler):
  """Handler which responds to ajax queries for performance counter data."""

  MAX_TICK_COUNT = 150
  """Desired maximum number of data points to return for a single query."""

  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  @admin.require_permission(level='root')
  def get(self):
    """Responds to a single request for performance counter data.  Each request has two required
    parameters in the query string, 'start' and 'end', which specify the beginning and end of the
    time range to be queried.  The times should be expressed as the number of seconds since the
    unix epoch.
    """
    def _OnAggregation(aggregator):
      self.set_header('Content-Type', 'application/json; charset=UTF-8')
      self.write(json.dumps(aggregator, default=_SerializeAggregateMetrics))
      self.finish()

    start_time = float(self.get_argument('start'))
    end_time = float(self.get_argument('end'))

    # Select an appropriate interval resolution based on the requested time span.
    intervals = metric.METRIC_INTERVALS
    min_resolution = (end_time - start_time) / self.MAX_TICK_COUNT
    selected_interval = next((i for i in intervals if i.length > min_resolution), intervals[-1])
    group_key = metric.Metric.EncodeGroupKey(metric.DEFAULT_CLUSTER_NAME, selected_interval)
    logging.info('Query performance counters, range: %s - %s, resolution: %s'
                  % (time.ctime(start_time), time.ctime(end_time), selected_interval.name))

    metric.AggregatedMetric.CreateAggregateForTimespan(self._client, group_key, start_time, end_time,
                                                       counters.counters, _OnAggregation)


def _SerializeAggregateMetrics(obj):
  """Utility method to serialize AggregateMetric and AggregatedCounter objects to JSON.
  This method is designed to be passed to json.dumps().
  """
  if isinstance(obj, metric.AggregatedMetric):
    return {'start_time': obj.start_time,
            'end_time': obj.end_time,
            'group_key': obj.group_key,
            'machines': list(obj.machines),
            'data': obj.counter_data
            }
  elif isinstance(obj, metric.AggregatedMetric.AggregatedCounter):
    logging.info('description: %r' % obj.description)
    return {'description': obj.description,
            'is_average': obj.is_average,
            'machine_data': obj.machine_data,
            'cluster_total': obj.cluster_total,
            'cluster_avg': obj.cluster_avg
            }
  else:
    raise web.HTTPError(400, "Expected instance of AggregatedMetric or AggregatedCounter, got %r" % obj)
