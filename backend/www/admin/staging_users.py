# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Handlers for setting/resetting staging attribute on users.
Users with the staging attribute set will have their requests routed to the staging cluster
instead of the production cluster.

  ModifyStagingUserHandler: Handles most of the requests relating to administrating the user staging setting.
  ModifyStagingNameDataHandler: Handles results of query over user table to locate user to change settings on.
"""

__author__ = 'mike@emailscrubbed.com (Mike Purtell)'

import logging
from tornado import web, escape
from viewfinder.backend.base import handler, util
from viewfinder.backend.db.user import User
from viewfinder.backend.www.admin import admin, data_table


class ModifyStagingUserHandler(admin.AdminHandler):
  """Staging Users administration panel.
  """

  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  @admin.require_permission(level='root')
  def get(self):
    user_id = self.get_argument('user_id', None)
    user_email = self.get_argument('user_email', None)  # User email retrieved for display only.
    t_dict = {'user_id': user_id,
              'user_email': user_email,
              'staging_change_succeeded' : False,
              'query_error': None}

    def _OnQueryUser(user):
      if user is None:
        t_dict['query_error'] = 'User id not found: %s' % user_id
        self.render('staging_admin.html', **t_dict)
      else:
        t_dict['user_name'] = user.name
        t_dict['user_email'] = user.email
        t_dict['is_staging_user'] = user.IsStaging()
        self.render('staging_admin_settings.html', **t_dict)

    t_dict.update(self.PermissionsTemplateDict())

    if user_id is not None:
      if user_id.isdigit():
        # user id is provided - look up user data for display.
        User.Query(self._client, int(user_id), None, _OnQueryUser, must_exist=False)
      else:
        # User name is provided - search for matching User IDs and display list of results.
        t_dict['col_names'] = ['User Name', 'Email', 'User Id', 'Labels']
        t_dict['ajax_src'] = 'https://%s/admin/staging_names_data?%s' % (self.request.host, self.request.query)
        t_dict['col_data'] = list()
        self.render('staging_admin_users.html', **t_dict)
    else:
      self.render('staging_admin.html', **t_dict)


  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  @admin.require_permission(level='root')
  def post(self):
    user_id = self.get_argument('user_id', None)
    user_email = self.get_argument('user_email', None)  # User email retrieved for display only
    change_user = self.get_argument('change_user', None)  # Set if button pressed to change staging status
    t_dict = {'user_id': user_id,
              'user_email': user_email,
              'staging_change_succeeded' : False,
              'query_error': None}

    def _OnUpdateUser():
      t_dict['staging_change_succeeded'] = True
      t_dict['is_staging_user'] = not t_dict['is_staging_user']
      self.render('staging_admin_settings.html', **t_dict)

    def _OnQueryUser(user):
      t_dict['user_name'] = user.name
      t_dict['user_email'] = user.email
      t_dict['is_staging_user'] = user.IsStaging()

      # Do we need to update the label with a change?
      if user.IsStaging() and change_user == 'production':
        user.labels.remove(User.STAGING)
      elif not user.IsStaging() and change_user == 'staging':
        user.labels.add(User.STAGING)
      else:
        # No change, so just go back to the settings page.
        self.render('staging_admin_settings.html', **t_dict)
        return

      # Do update.
      # This update is done outside the op manager because it's an
      # isolated add/remove of a label and best effort is sufficient.
      # If it were to fail, an admin can just rety and it will be obvious if it worked.
      user.Update(self._client, _OnUpdateUser)

    t_dict.update(self.PermissionsTemplateDict())

    if user_id is not None and user_id.isdigit():
      User.Query(self._client, int(user_id), None, _OnQueryUser)
    else:
      raise web.HTTPError(400, "Expecting a user id.")


class ModifyStagingNameDataHandler(data_table.AdminDataTableHandler):
  """Handles the server-side pagination of users queried from the database.
  Users are queried based on their full name and email address.
  """
  DB_TABLE = 'user'

  def _FormatResult(self, user):
    email = escape.url_escape(user.email) if user.email else '-'
    user_url = '<a href="/admin/staging_users?user_id=%d&user_email=%s">{0}</a>' % (user.user_id, email)
    return [user_url.format(escape.utf8(escape.xhtml_escape(item)))
            for item in [user.name or '-', email, str(user.user_id), str(list(user.labels.combine()))]]

  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  @admin.require_permission(level='root')
  def get(self):
    user_search = self.get_argument('user_id', '')
    query_string = ('user.name={us} | user.email={us}', {'us':user_search})
    req = self.ReadTablePageRequest(self.DB_TABLE)

    def _OnGetUsers(users_with_potential_dups):
      # remove duplicate rows.
      users = []
      exists = set()
      for x in users_with_potential_dups:
        if x.user_id not in exists:
          exists.add(x.user_id)
          users.append(x)

      last_key = users[-1]._GetIndexKey() if len(users) > 0 else None
      rows = [self._FormatResult(user) for user in users]
      self.WriteTablePageResponse(rows, last_key)

    User.IndexQuery(self._client, query_string, ['name', 'user_id', 'email', 'labels'],
                    callback=_OnGetUsers, limit=req.length, start_index_key=req.last_key)
