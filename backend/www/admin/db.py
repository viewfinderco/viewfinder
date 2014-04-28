# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Handlers for database administration.

  DBHandler: top-level status handler for datastore
  DBDataHandler: display table data either via scan or query
"""
from tornado.escape import url_escape

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import base64
import logging

from tornado import auth, gen, template
from viewfinder.backend.base import handler, util
from viewfinder.backend.db import db_client, schema, vf_schema
from viewfinder.backend.www.admin import admin, formatters, data_table


class DBHandler(admin.AdminHandler):
  """Provides a list of all datastore tables and allows each to be
  drilled down.
  """
  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  @admin.require_permission(level='root')
  def get(self):
    t_dict = {}

    def _OnVerifySchema(results):
      col_names = ['Table Name', 'Hash Key', 'Range Key', 'Indexed', 'Count', 'Bytes', 'R/U', 'W/U', 'Status']
      v_dict = dict([(t[0], t[1]) for t in results])
      s_dict = dict([(t.name, t) for t in vf_schema.SCHEMA.GetTables()])
      col_data = list()
      for table in sorted(s_dict.keys()):
        col_data.append(['<a href="https://%s/admin/db?table=%s">%s</a>' % (self.request.host, table, table),
                         s_dict[table].hash_key_col.name,
                         s_dict[table].range_key_col.name \
                           if s_dict[table].range_key_col else '-',
                         isinstance(s_dict[table], schema.IndexedTable),
                         v_dict[table].count, v_dict[table].size_bytes,
                         v_dict[table].schema.read_units, v_dict[table].schema.write_units,
                         v_dict[table].schema.status])
      t_dict['col_names'] = col_names
      t_dict['col_data'] = col_data
      self.render('db.html', **t_dict)

    t_dict.update(self.PermissionsTemplateDict())
    if self.get_argument('table', None):
      op_type = self.get_argument('type', 'scan')
      hash_key = self.get_argument('hash_key', None)
      sort_key = self.get_argument('sort_key', None)
      sort_desc = self.get_argument('sort_desc', None)
      reverse = self.get_argument('reverse', None) is not None
      table_name = self.get_argument('table')
      table = vf_schema.SCHEMA.GetTable(table_name)

      t_dict['table_name'] = table_name
      t_dict['ajax_src'] = 'https://%s/admin/data?%s' % (self.request.host, self.request.query)
      t_dict['col_data'] = []
      t_dict['op_type'] = op_type
      t_dict['hash_key'] = hash_key
      t_dict['sort_key'] = sort_key
      t_dict['sort_desc'] = sort_desc
      t_dict['reverse'] = reverse
      t_dict['has_range_key'] = table.range_key_col is not None

      if op_type == 'view':
        t_dict['col_names'] = [ 'Name', 'Key', 'Value' ]
      else:
        # First column is the magnifying glass.
        t_dict['col_names'] = [''] + table.GetColumnNames()

      self.render('db_table.html', **t_dict)
    else:
      vf_schema.SCHEMA.VerifyOrCreate(self._client, _OnVerifySchema, verify_only=True)


class DBDataHandler(data_table.AdminDataTableHandler):
  """Provides server-side scans for the contents of database
  tables. The DBHandler class maintains a mapping between table name
  and an optional table handler. The table handler allows
  customization of the table display. Table handlers should be added
  to the '_TABLE_FORMATTERS' map below.
  """
  _TABLE_FORMATTERS = {
    'Accounting': formatters.FmtAccounting,
    'Episode': formatters.FmtEpisode,
    'Identity': formatters.FmtIdentity,
    'Index': formatters.FmtIndex,
    'Lock': formatters.FmtLock,
    'Operation': formatters.FmtOperation,
    'User': formatters.FmtUser,
    'Viewpoint': formatters.FmtViewpoint,
    }

  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  @admin.require_permission(level='root')
  def get(self):
    table_name = self.get_argument('table')
    table = vf_schema.SCHEMA.GetTable(table_name)
    op_type = self.get_argument('type', 'scan')
    hash_key = self.get_argument('hash_key', None)
    if not hash_key:
      # User clicked on the "go" button but left the hash_key box blank. Perform a regular scan.
      op_type = 'scan'
    reverse = self.get_argument('reverse', None) is not None

    req = self.ReadTablePageRequest(table_name, op_type + ('.reverse' if reverse else ''))

    def _OnColData(items, table_count, last_key):
      formatter = self._GetTableFormatter(req.table)(table)
      # Build item view url.
      query_url = '/admin/db?table=%s&type=view' % table_name
      col_data = []
      for item in items:
        hk = item[table.hash_key_schema.name]
        url = '%s&hash_key=%s' % (query_url, url_escape(util.ConvertToString(hk)))
        if table.range_key_col:
          sk = item[table.range_key_schema.name]
          url += '&sort_key=%s&sort_desc=EQ' % url_escape(util.ConvertToString(sk))
        data = []
        data.append('<a href="%s"><img src="/static/css/images/zoom_in.png"</img></a>' % url)
        data.extend(formatter.FormatItemAttributes(item))
        col_data.append(data)
      last_index = req.start + len(items)
      table_count = max(table_count, last_index)
      self.WriteTablePageResponse(col_data, last_key, table_count)

    def _OnViewData(items, table_count, last_key):
      formatter = self._GetTableFormatter(req.table)(table)
      if len(items) == 0:
        self.WriteTablePageResponse([['no data', '', '']], None)
        return
      assert len(items) == 1, 'too many elements, expected just the one: %r' % items
      item = items[0]
      self.WriteTablePageResponse(formatter.FormatItemAttributesForView(item), None)


    if op_type == 'scan':
      self._ScanData(table, req.length, req.last_key, _OnColData)
    else:
      sort_key = self.get_argument('sort_key', None)
      range_operator = None
      if sort_key:
        # If we have a sort key, require a sort description.
        # TODO(marc): support BETWEEN operator.
        sort_desc = self.get_argument('sort_desc')

        if table.range_key_schema.value_type == 'N':
          sort_key = int(sort_key)
        range_operator = db_client.RangeOperator([sort_key], sort_desc)

      reverse = self.get_argument('reverse', None) is not None

      if table.hash_key_schema.value_type == 'N':
        hash_key = int(hash_key)

      if op_type == 'view':
        col_data = self._GetData(table, hash_key, sort_key, _OnViewData)
      elif table.range_key_col is None:
        col_data = self._GetData(table, hash_key, sort_key, _OnColData)
      else:
        col_data = self._QueryData(table, hash_key, range_operator, req.length,
                                   req.last_key, _OnColData, reverse)


  @gen.engine
  def _ScanData(self, table, limit, excl_start_key, callback):
    """Does a table scan. Invokes 'callback with (items, total_count, last_key)."""
    description = yield gen.Task(self._client.DescribeTable, table=table.name)
    scan_results = yield gen.Task(self._client.Scan, table=table.name,
                                  attributes=[c.key for c in table.GetColumns()],
                                  limit=limit, excl_start_key=excl_start_key)
    callback(scan_results.items, description.count, scan_results.last_key)


  @gen.engine
  def _QueryData(self, table, hash_key, range_operator, limit, excl_start_key, callback, reverse):
    """Does a range query using hash key."""
    query = yield gen.Task(self._client.Query, table=table.name, hash_key=hash_key, range_operator=range_operator,
                           attributes=[c.key for c in table.GetColumns()],
                           limit=limit, excl_start_key=excl_start_key,
                           scan_forward=not reverse)
    count = yield gen.Task(self._client.Query, table=table.name, hash_key=hash_key, range_operator=range_operator,
                           attributes=None, count=True)
    callback(query.items, count.count, query.last_key)


  @gen.engine
  def _GetData(self, table, hash_key, range_key, callback):
    """Fetch a single entry."""
    item = yield gen.Task(self._client.GetItem, table=table.name,
                           key=db_client.DBKey(hash_key, range_key),
                           attributes=[c.key for c in table.GetColumns()], must_exist=False)
    if item is None:
      callback([], 0, None)
    else:
      callback([item.attributes], 1, None)


  def _GetTableFormatter(self, table_name):
    """Returns the table handler for 'table_name', if specified in the
    _TABLE_FORMATTERS map. If none is specified in the map, return the
    default.
    """
    return DBDataHandler._TABLE_FORMATTERS.get(table_name, formatters.FmtDefault)
