# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Handlers for viewfinder web application administration.

  AdminHandler: top-level admin handler
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import httplib
import logging
import os
import traceback
from tornado import gen, web
from viewfinder.backend.base import counters, handler
from viewfinder.backend.db.db_client import DBClient
from viewfinder.backend.db import schema, vf_schema
from viewfinder.backend.db.admin_permissions import AdminPermissions
from viewfinder.backend.www import basic_auth

_req_per_sec = counters.define_rate('viewfinder.admin.www.requests_per_second',
                                    'Administrator website requests handled per second.')



def require_permission(level=None):
  """Decorator to be used in admin get/post methods.
  Permission required may be 'root', 'support', or None.
  If None is specified, the user must still be in the AdminPermissions table.
  Permissions are stored in self._permissions for later access.
  """
  def decorator(f):
    @gen.engine
    def wrapper(self, *args, **kwargs):
      assert level in [None, 'root', 'support']
      self._permissions = yield gen.Task(self.QueryAdminPermissions)

      if level == 'root':
        self.CheckIsRoot()
      elif level == 'support':
        self.CheckIsSupport()

      f(self, *args, **kwargs)
    return wrapper
  return decorator


class AdminHandler(basic_auth.BasicAuthHandler):
  """Directory of administration tasks."""
  def prepare(self):
    basic_auth.BasicAuthHandler.prepare(self)
    self._auth_credentials = self.get_current_user()
    _req_per_sec.increment()

  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  # We only require that the user exists. Actual rights are only used here to build the link table.
  # They will be checked by each sub page.
  @require_permission()
  def get(self):
    t_dict = self.PermissionsTemplateDict()
    self.render('admin.html', **t_dict)

  def CheckIsRoot(self):
    """Check whether the permissions object has a ROOT rights entry."""
    if not self._permissions.IsRoot():
      raise web.HTTPError(httplib.FORBIDDEN, 'User %s does not have root credentials.' % self._auth_credentials)


  def CheckIsSupport(self):
    """Check whether the permissions object has a SUPPORT rights entry. Root users do not automatically get
    granted support rights.
    """
    if not self._permissions.IsSupport():
      raise web.HTTPError(httplib.FORBIDDEN, 'User %s does not have support credentials.' % self._auth_credentials)


  def PermissionsTemplateDict(self):
    """Dict of variables used in all admin templates."""
    return { 'auth_credentials': self._auth_credentials,
             'is_root': self._permissions.IsRoot(),
             'is_support': self._permissions.IsSupport() }


  @gen.engine
  def QueryAdminPermissions(self, callback):
    """Get set of permissions for user. Raise an error if the user does not have an entry,
    of if the set of rights is empty.
    """
    permissions = yield gen.Task(AdminPermissions.Query, self._client, self._auth_credentials, None, must_exist=False)

    if permissions is None or not permissions.rights:
      raise web.HTTPError(httplib.FORBIDDEN, 'User %s has no credentials.' % self._auth_credentials)

    callback(permissions)


  def _handle_request_exception(self, value):
    """Handles presentation of an exception condition to the admin.
    """
    logging.exception('error in admin page')
    self.render('admin_error.html',
        auth_credentials=self._auth_credentials, is_root=False, is_support=False,
        title=value, message=traceback.format_exc())
    return True
