# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Provides decorators for request handler methods:

  @handler.asynchronous: similar to tornado.web.asynchronous. It disables the auto-completion
                         on handler exit, but also optionally provides a client stub to the
                         DynamoDB datastore backend, and to the photo object store.

  @handler.authenticated: similar to tornado.web.authenticated, except that it raises HTTP
                          401 rather than 403, and allows additional options.

Example usage:

class MyApp(tornado.web.RequestHandler):
  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  def get(self):
    self.write(self._client(...))
    self.finish()
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import functools
import logging
import urllib
import urlparse

from tornado import web
from viewfinder.backend.db.db_client import DBClient
from viewfinder.backend.db.user import User
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.base import util


def asynchronous(datastore=False, obj_store=False, log_store=False):
  """Wrap request handler methods with this decorator if they will require asynchronous
  access to DynamoDB datastore or S3 object store for photo storage.

  If datastore=True, then a DynamoDB client is available to the handler as self._client. If
  obj_store=True, then an S3 client for the photo storage bucket is available as self._obj_store.
  If log_store is true, then an S3 client for the user log storage bucket is available as
  self._log_store

  Like tornado.web.asynchronous, this decorator disables the auto-finish functionality.
  """
  def _asynchronous(method):
    def _wrapper(self, *args, **kwargs):
      """Disables automatic HTTP response completion on exit."""
      self._auto_finish = False
      if datastore:
        self._client = DBClient.Instance()
      if obj_store:
        self._obj_store = ObjectStore.GetInstance(ObjectStore.PHOTO)
      if log_store:
        self._log_store = ObjectStore.GetInstance(ObjectStore.USER_LOG)

      with util.ExceptionBarrier(self._stack_context_handle_exception):
        return method(self, *args, **kwargs)

    return functools.wraps(method)(_wrapper)
  return _asynchronous


def authenticated(allow_prospective=False):
  """Wrap request handler methods with this decorator to require that the user be logged in.
  Raises an HTTP 401 error if not.

  This method is exactly the same as tornado.web.authenticated, except that 401 is raised
  instead of 403. This is important, because the clients will re-authenticate only if they
  receive a 401.

  If allow_prospective=False, then prospective user cookies are not authorized access.
  WARNING: Before changing allow_prospective to True, make certain to think through the
           permissions that a prospective user should have for that particular handler.
  """
  def _authenticated(method):
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
      if not self.current_user:
        if self.request.method in ("GET", "HEAD"):
          url = self.get_login_url()
          if "?" not in url:
            if urlparse.urlsplit(url).scheme:
              # if login url is absolute, make next absolute too
              next_url = self.request.full_url()
            else:
              next_url = self.request.uri
            url += "?" + urllib.urlencode(dict(next=next_url))
          self.redirect(url)
          return
        raise web.HTTPError(401, 'You are not logged in. Only users that have logged in can access this page.')
      elif isinstance(self.current_user, User) and not allow_prospective and not self.current_user.IsRegistered():
        raise web.HTTPError(403, 'You are not a registered user. Sign up for Viewfinder to gain access to this page.')
      return method(self, *args, **kwargs)
    return wrapper
  return _authenticated
