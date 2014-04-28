# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Handler to look up a user by email.

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import base64
import os
import stat
import time
from tornado import auth, template

from viewfinder.backend.base import handler, util
from viewfinder.backend.db import schema, vf_schema, user
from viewfinder.backend.www.admin import admin
from viewfinder.backend.www.admin import data_table

class FindUserIdHandler(admin.AdminHandler):
  """Support function to find a viewfinder user ID given an email address."""
  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  @admin.require_permission(level='support')
  def get(self):
    user_email = self.get_argument('user_email', None)
    t_dict = {'user_email': user_email}
    t_dict.update(self.PermissionsTemplateDict())

    if user_email is not None:
      # Email is provided - search for matching User IDs.
      t_dict['col_names'] = ['Email', 'User Id']
      template = 'finduserid_data.html'

      t_dict['ajax_src'] = 'https://%s/admin/find_user_id_data?%s' % (self.request.host, self.request.query)
      t_dict['col_data'] = list()
      t_dict['user_email'] = user_email
      self.render(template, **t_dict)
    else:
      self.render('finduserid.html', **t_dict)


class FindUserIdDataHandler(data_table.AdminDataTableHandler):
  """Handles the server-side pagination of users queried from the database.
  Users are queried based on their email address.
  """
  DB_TABLE = 'user'

  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  @admin.require_permission(level='support')
  def get(self):
    user_search = self.get_argument('user_email', '')
    query_string = ('user.email={us}', {'us':user_search})
    req = self.ReadTablePageRequest(self.DB_TABLE)

    def _OnGetUsers(users):
      last_key = users[-1]._GetIndexKey() if len(users) > 0 else None
      rows = [ [user.email, user.user_id] for user in users]
      self.WriteTablePageResponse(rows, last_key)

    user.User.IndexQuery(self._client, query_string, ['email'],
                         callback=_OnGetUsers, limit=req.length)
