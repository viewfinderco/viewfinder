# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Handler for service health status.
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import logging
import time
from collections import namedtuple

from viewfinder.backend.base import handler, counters
from viewfinder.backend.db import metric
from viewfinder.backend.db.health_report import HealthReport, HealthCriteria, CLUSTER_TOKEN
from viewfinder.backend.www.base import BaseHandler

class ServiceHealthHandler(BaseHandler):
  """Handler for monitoring service health.  This endpoint is designed to be called
  from an external watchdog, and returns the status of the server via an HTTP response
  code.  The server status is computed using the HealthReport system, which considers
  recent performance counters in order to detect possible problems with the service.
  """
  _CachedReport = namedtuple('_CachedReport', ['report', 'expiration'])

  # A collection delay, specified in seconds.  This delay will allow individual machines to
  # upload their metrics for a given time interval before a health report is generated
  # based on them.
  COLLECTION_DELAY = 5

  # Cached report dictionary - up to one report may be cached per metrics group.  This is
  # used because health report queries may be run in response to service endpoints which
  # are exposed to the public.
  _cachedReports = dict()

  @handler.asynchronous(datastore=True)
  def get(self):
    """Returns a simple JSON report of the health of the cluster.  This will be a simple
    status message of 'OK' unless there are active alerts on the cluster.  An example
    of an alerting status message:

    {
      'status': 'ALERT',
      'alerts': [
        {'name': 'Alert1', 'count': 1, 'cluster': False, 'description': 'Alert description.'},
       ]
    }
    """
    cluster = metric.DEFAULT_CLUSTER_NAME
    interval = metric.METRIC_INTERVALS[0]
    now = time.time()

    def _OnGetHealthReport(report):
      expiration = report.timestamp + interval.length + self.COLLECTION_DELAY
      cached = self._CachedReport(report, expiration)
      self._cachedReports[cluster] = cached

      response_dict = dict()
      if (len(report.alerts) > 0):
        criteria_list = HealthCriteria.GetCriteriaList()
        summaries = dict()
        for a in report.alerts:
          alert_name, machine = a.split(':')
          if not alert_name in summaries:
            summaries[alert_name] = {'name': alert_name, 'count': 0, 'cluster': False}
            criteria = next((c for c in criteria_list if c.name == alert_name), None)
            if criteria is not None:
              summaries[alert_name]['description'] = criteria.description

          if machine == CLUSTER_TOKEN:
            summaries[alert_name]['cluster'] = True
          else:
            summaries[alert_name]['count'] += 1

        response_dict['status'] = 'ALERT'
        response_dict['alerts'] = list(summaries.values())
      else:
        response_dict['status'] = 'OK'

      self.write(response_dict)
      self.finish()

    # Return cached report if it is still valid.
    cached = self._cachedReports.get(cluster, None)
    if cached is not None and cached.expiration > now:
      _OnGetHealthReport(cached.report)
    else:
      report = HealthReport.GetHealthReport(self._client, cluster, interval, now - self.COLLECTION_DELAY, _OnGetHealthReport)
