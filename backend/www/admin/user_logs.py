# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Handlers for viewing user client & server operation logs.

  LogHandler: .
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import base64
import os
import stat
import time
import logging
from tornado import auth, template, escape

from viewfinder.backend.base import handler, util
from viewfinder.backend.db import db_client, schema, vf_schema, user
from viewfinder.backend.www.admin import admin
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.www.admin import data_table

class UserLogHandler(admin.AdminHandler):
  """User Logs administration panel.  This handler allows administrators
  to view user logs which are stored in S3.
  Logs can currently only be queried using a specified user id.
  """

  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  @admin.require_permission(level='root')
  def get(self):
    user_id = self.get_argument('user_id', None)
    user_email = self.get_argument('user_email', None)  # User email retrieved for display only
    t_dict = {'user_id': user_id, 'user_email': user_email}
    t_dict.update(self.PermissionsTemplateDict())

    if user_id is not None:
      if user_id.isdigit():
        # User ID is provided - look up logs directly for this user id.
        t_dict['col_names'] = ['Date', 'Operation Method', 'Operation ID', 'Attempt #', 'View Link']
        data_source_page = 'user_logs_data'
        template = 'userlogs_table.html'
      else:
        # User name is provided - search for matching User IDs.
        t_dict['col_names'] = ['User Name', 'Email', 'User Id']
        data_source_page = 'user_names_data'
        template = 'userlogs_users.html'

      t_dict['ajax_src'] = 'https://%s/admin/%s?%s' % (self.request.host, data_source_page, self.request.query)
      t_dict['col_data'] = list()
      t_dict['user_email'] = user_email
      self.render(template, **t_dict)
    else:
      self.render('userlogs.html', **t_dict)


class UserLogDataHandler(data_table.AdminDataTableHandler):
  """Handles the server-side pagination of user logs stored in S3.
  The list of logs is retrieved from S3 by a key search, the results
  of which are retrieved one page at a time via ajax requests.
  The current page is maintained using a cookie.
  """
  DB_TABLE = 's3_user_logs'

  def _FormatResult(self, key):
    loginfo = key.split('/')
    if loginfo[2] == 'op':
      loginfo = loginfo[1:2] + loginfo[3:]
    else:
      # Older OP logs did not save method name or retry number in key.
      loginfo = [loginfo[1], None, loginfo[2], None]
    url = self._log_store.GenerateUrl(key)
    loginfo.append('<a href="%s">%s</a>' % (url, url))
    return loginfo

  def _GetOpLogPrefix(self, user_id, timestamp=None):
    return '%s/' % user_id

  @handler.authenticated()
  @handler.asynchronous(datastore=True, log_store=True)
  @admin.require_permission(level='root')
  def get(self):
    user_id = self.get_argument('user_id', None)
    key_prefix = self._GetOpLogPrefix(user_id)
    # Table paging saves a DBKey. We store the S3 key into the field normally used for the hash key.
    req = self.ReadTablePageRequest(self.DB_TABLE)
    last_key, _ = req.last_key if req.last_key is not None else (None, None)

    def _OnGetKeys(items):
      rows = [self._FormatResult(item) for item in items]
      last_marker = items[-1] if len(items) > 0 else ''
      self.WriteTablePageResponse(rows, db_client.DBKey(last_marker, None))

    self._log_store.ListKeys(_OnGetKeys, prefix=key_prefix, marker=last_key, maxkeys=req.length)


class UserNameDataHandler(data_table.AdminDataTableHandler):
  """Handles the server-side pagination of users queried from the database.
  Users are queried based on their full name and email address.
  """
  DB_TABLE = 'user'

  def _FormatResult(self, user):
    email = escape.url_escape(user.email) if user.email else '-'
    user_url = '<a href="/admin/user_logs?user_id=%d&user_email=%s">{0}</a>' % (user.user_id, email)
    return [user_url.format(escape.utf8(escape.xhtml_escape(item)))
            for item in [user.name or '-', email, str(user.user_id)]]

  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  @admin.require_permission(level='root')
  def get(self):
    user_search = self.get_argument('user_id', '')
    query_string = ('user.name={us} | user.email={us}', {'us':user_search})
    req = self.ReadTablePageRequest(self.DB_TABLE)

    def _OnGetUsers(users):
      last_key = users[-1]._GetIndexKey() if len(users) > 0 else None
      rows = [self._FormatResult(user) for user in users]
      self.WriteTablePageResponse(rows, last_key)

    user.User.IndexQuery(self._client, query_string, ['name', 'user_id', 'email'],
                         callback=_OnGetUsers, limit=req.length, start_index_key=req.last_key)
