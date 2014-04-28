# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder storage of client logs.

Viewfinder client applications can write logs to S3 in a manner
analogous to server operation logs. The client makes an API request to
/service/get_client_log and supplies a unique log identification
number. MD5 and bytes may be optionally specified as well. The
response from the server contains a permissioned S3 PUT URL.

  ClientLog
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import datetime
import logging
import re
import time

from functools import partial
from viewfinder.backend.base import constants, util
from viewfinder.backend.storage.object_store import ObjectStore

CLIENT_LOG_CONTENT_TYPE = 'application/octet-stream'
MAX_CLIENT_LOGS = 1000

class ClientLog(object):
  """Viewfinder client log."""
  @classmethod
  def _IsoDate(cls, timestamp):
    """Gets an ISO date string for the specified UTC "timestamp"."""
    return datetime.datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')

  @classmethod
  def _LogKeyPrefix(cls, user_id, iso_date_str):
    """Creates a key prefix for user log files based on "user_id" and
    the "iso_date_str".
    """
    return '%d/%s' % (user_id, iso_date_str)

  @classmethod
  def GetPutUrl(cls, user_id, device_id, timestamp, client_log_id,
                content_type=CLIENT_LOG_CONTENT_TYPE,
                content_md5=None, max_bytes=10 << 20):
    """Returns a URL for the client to write device logs to S3. URLs
    expire by default in a day and expect content-type
    CLIENT_LOG_CONTENT_TYPE.
    """
    iso_date_str = ClientLog._IsoDate(timestamp)
    key = '%s/dev-%d-%s' % (ClientLog._LogKeyPrefix(user_id, iso_date_str),
                            device_id, client_log_id)

    obj_store = ObjectStore.GetInstance(ObjectStore.USER_LOG)
    return obj_store.GenerateUploadUrl(
      key, content_type=content_type, content_md5=content_md5,
      expires_in=constants.SECONDS_PER_DAY, max_bytes=max_bytes)

  @classmethod
  def ListClientLogs(cls, user_id, start_timestamp, end_timestamp, filter, callback):
    """Queries S3 based on specified "user_id", and the specified
    array of ISO date strings. The results are filtered according to
    the regular expression "filter". Returns an array of {filename,
    URL} objects for each date in "iso_dates".
    """
    obj_store = ObjectStore.GetInstance(ObjectStore.USER_LOG)

    def _OnListDates(date_listings):
      """Assemble {filename, url} objects for each date listing."""
      filter_re = re.compile(filter or '.*')
      callback([{'filename': key, 'url': obj_store.GenerateUrl(key)}
                for logs in date_listings for key in logs if filter_re.search(key)])

    with util.ArrayBarrier(_OnListDates) as b:
      iso_dates = set()
      t = start_timestamp
      while t < end_timestamp:
        iso_dates.add(ClientLog._IsoDate(t))
        t += constants.SECONDS_PER_DAY
      iso_dates.add(ClientLog._IsoDate(end_timestamp))
      iso_dates = sorted(iso_dates)

      for iso_date in iso_dates:
        ClientLog._ListAllKeys(obj_store, ClientLog._LogKeyPrefix(user_id, iso_date), b.Callback())

  @classmethod
  def _ListAllKeys(cls, obj_store, prefix, callback):
    """Lists all keys for the given prefix, making multiple calls as necessary."""
    def _AppendResults(results, keys):
      results += keys
      if len(keys) < MAX_CLIENT_LOGS:
        callback(results)
      else:
        obj_store.ListKeys(partial(_AppendResults, results),
                           prefix=prefix, marker=keys[-1], maxkeys=MAX_CLIENT_LOGS)

    obj_store.ListKeys(partial(_AppendResults, []), prefix=prefix, maxkeys=MAX_CLIENT_LOGS)
