# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Handlers for server-side data table paging for administration pages.

These handlers are designed to work with the jQuery Datatable plugin (http://datatables.net/)
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import base64
import json
import logging

from collections import namedtuple
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.www.admin import admin

# Named tuple to hold a table page request from the jQuery datatable plugin.
_TablePageRequest = namedtuple('_TablePageRequest', ['table', 'op_type', 'start', 'length', 'last_key', 'echo'])

class AdminDataTableHandler(admin.AdminHandler):
  """Base data table handler - provides support methods to interact
  with the jQuery data table plug-in, providing read-forward access to
  supported data tables.
  """

  def _GetCookieName(self):
    """Returns a cookie name, which is currently based on the base class type name."""
    return type(self).__name__ + '_last_key'

  def ReadTablePageRequest(self, table_name, op_type=None):
    """Formats the request data received from jQuery data table. The 'table_name'
    parameter is required if a single handler can query more than one data table.
    """
    requested_start = int(self.get_argument('iDisplayStart'))
    requested_length = int(self.get_argument('iDisplayLength'))
    s_echo = self.get_argument('sEcho')

    # Load last key, which is stored in a cookie
    cookie = self.get_secure_cookie(self._GetCookieName())
    try:
      last_table, op_type, last_index, last_key = json.loads(cookie)
      if last_table != table_name or last_index != requested_start:
        last_key = None
        requested_start = 0
    except:
      logging.warn('Bad cookie value: %s = %s' % (self._GetCookieName(), cookie))
      self.clear_cookie(self._GetCookieName())
      last_key = None
      requested_start = 0

    if last_key:
      # Convert last key back into DBKey - this is lost in json serialization.
      last_key = DBKey(last_key[0], last_key[1])

    self._table_request = _TablePageRequest(table=table_name, op_type=op_type, start=requested_start,
                                            length=requested_length, last_key=last_key, echo=s_echo)
    return self._table_request

  def WriteTablePageResponse(self, rows, last_key, table_count=None):
    """Writes the appropriate json response and tracking cookie."""
    req = self._table_request
    last_index = req.start + len(rows)
    if table_count:
      table_count = max(table_count, last_index)
    elif len(rows) == req.length:
      # There may be additional rows - this tricks the jquery data table into displaying a 'Next' button anyway.
      table_count = last_index + 1
    else:
      table_count = last_index

    json_dict = {
      'sEcho': int(req.echo),
      'iDisplayStart': req.start,
      'iTotalRecords': table_count,
      'iTotalDisplayRecords': table_count,
      'aaData': rows,
      }

    cookie = json.dumps((req.table, req.op_type, last_index, last_key))
    self.set_secure_cookie(self._GetCookieName(), cookie)
    self.set_header('Content-Type', 'application/json; charset=UTF-8')
    self.write(json_dict)
    self.finish()
