# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Base classes.

  ViewfinderContext: context local storage object, used to maintain

  BaseHandler: base class for viewfinder handlers, including
               methods to get the current user.
  HealthzHandler: returns the current health of the server.
"""

from __future__ import with_statement

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import binascii
import json
import logging
import sys
import time
import toro
import urllib
import uuid
import validictory

from functools import partial
from tornado.ioloop import IOLoop
from tornado import escape, gen, httpclient, options, stack_context, web

from viewfinder.backend.base import environ, message, util
from viewfinder.backend.base.context_local import ContextLocal
from viewfinder.backend.db.db_client import DBClient
from viewfinder.backend.db.user import User
from viewfinder.backend.www import json_schema, www_util

_ERROR_MAP = {
  400: 'We could not understand your request.',
  401: 'Authentication required for that action.',
  403: 'You do not have permission for that action.',
  404: 'You requested something that does not exist.',
  500: 'Unfortunately, that request could not be processed.',
  501: 'The functionality you requested is not available yet.',
  503: 'We are experiencing technical difficulties; try again later.',
  }

_USER_COOKIE_NAME = 'user'
_USER_COOKIE_EXPIRES_DAYS = 365


class ViewfinderContext(ContextLocal):
  """Provides a context local object for storing information about a viewfinder request.
  This information will then be available to methods outside the direct scope of
  the request handler - for example, in a logging filter.

  The current ViewfinderContext, if set, is accessible using ViewfinderContext.current().
  """
  def __init__(self, request):
    super(ViewfinderContext, self).__init__()
    self.request = request
    self.user = None
    self.device_id = None
    self.viewpoint_id = None
    self.confirm_time = None
    # A toro.Event (when there is a client connection to monitor).
    self.connection_close_event = None

  def CanViewViewpoint(self, viewpoint_id):
    """Returns true if the given viewpoint can be accessed by the current user."""
    return self.viewpoint_id is None or self.viewpoint_id == viewpoint_id

  def IsConfirmedUser(self):
    """Returns true if the current user session has a confirmed cookie."""
    return www_util.IsConfirmedCookie(self.confirm_time)

  def IsMobileClient(self):
    """Returns true if the caller is a mobile client (as opposed to the web client)."""
    assert self.device_id is not None and self.user is not None
    return self.device_id != self.user.webapp_dev_id


class BaseHandler(web.RequestHandler):
  """The current user is a dictionary containing select contents of
  the viewfinder user account.
  """
  def __init__(self, application, request, **kwargs):
    super(BaseHandler, self).__init__(application, request, **kwargs)
    self._server_version = self.settings['server_version']
    self._connection_close_event = toro.Event()

  def CreateUserCookieDict(self, user_id, device_id, user_name=None, viewpoint_id=None, confirm_time=None,
                           is_session_cookie=None):
    """Creates a user cookie dict from the given arguments."""
    user_dict = {'user_id': user_id,
                 'device_id': device_id,
                 'server_version': self.settings['server_version']}
    util.SetIfNotNone(user_dict, 'name', user_name)
    util.SetIfNotNone(user_dict, 'viewpoint_id', viewpoint_id)
    util.SetIfNotNone(user_dict, 'confirm_time', confirm_time)
    util.SetIfNotNone(user_dict, 'is_session_cookie', is_session_cookie)
    return user_dict

  def SetUserCookie(self, user_cookie_dict):
    """Creates a secure user cookie, indicating that this user is now logged in. The cookie is
    a signed, json-encoded dict (obtained from CreateUserCookieDict). It can be read using
    GetUserCookie(). If the "is_session_cookie" field is True, then the cookie will typically
    expire once the user closes the browser. This is used when the user does not check
    "Remember Me".
    """
    expires_days = None if user_cookie_dict.get("is_session_cookie", False) else _USER_COOKIE_EXPIRES_DAYS
    self.set_secure_cookie(_USER_COOKIE_NAME, json.dumps(user_cookie_dict), expires_days=expires_days)

  def GetUserCookie(self):
    """Returns a dictionary of user attributes from the request
    headers. The cookie value is decrypted and json-decoded. To be
    valid, it must contain a 'user_id' and have a server version
    with a major version number equal to the major version number
    of the current server.
    """
    user_cookie = self.get_secure_cookie(_USER_COOKIE_NAME, max_age_days=_USER_COOKIE_EXPIRES_DAYS)
    if user_cookie:
      try:
        user_dict = json.loads(user_cookie)
      except ValueError:
        # Not json, so delete the broken cookie.
        logging.warning('user cookie is not valid JSON: %s' % user_cookie)
        self.clear_cookie(_USER_COOKIE_NAME)
        return None

      if 'user_id' in user_dict and 'device_id' in user_dict and 'server_version' in user_dict and \
            self._server_version == user_dict['server_version']:
        return user_dict
      else:
        logging.warning('user cookie does not have required fields: %s' % user_dict)
    else:
      cookie_header = self.request.headers.get('Cookie', None)
      if cookie_header is None:
        logging.info('missing HTTP Cookie header')
      elif _USER_COOKIE_NAME not in cookie_header:
        logging.info('HTTP Cookie header exists, but does not contain a user cookie: %s' %
                     cookie_header)
      else:
        logging.warning('user cookie exists in HTTP Cookie header, but could not be decoded: %s' %
                        cookie_header)

    return None

  def ClearUserCookie(self):
    """Clears the user cookie."""
    self.clear_cookie(_USER_COOKIE_NAME)

  def LoginUser(self, user, user_cookie, set_cookie=True):
    """Log in with the given user and cookie by setting up the current context and setting the
    user cookie (if "set_cookie" is true).
    """
    # Log in with user from cookie.
    self._current_user = user

    context = ViewfinderContext.current()
    context.user = user
    context.device_id = user_cookie['device_id']
    context.viewpoint_id = user_cookie.get('viewpoint_id', None)
    context.confirm_time = user_cookie.get('confirm_time', None)

    if set_cookie:
      # Rewrite user cookie using most up-to-date user name, server version, expiration, and
      # session cookie setting. Doing this ensures that the cookie will never expire if the
      # service is continually used.
      self.SetUserCookie(user_cookie)

  def get_current_user(self):
    """Returns the user db object that was set by the '_execute' method
    if the user cookie was found.
    """
    return self._current_user

  def set_cookie(self, *args, **kwargs):
    """Override base set_cookie to default secure and httponly to true.

    "secure" means HTTPS-only; "httponly" means the cookie is not accessible to javascript;
    "domain" allows cookie to be used with any first-level sub-domain.
    """
    kwargs.setdefault('secure', True)
    kwargs.setdefault('httponly', True)

    # Prepend dot to domain name to allow cookie to be used with any first-level sub-domain.
    assert '.' in options.options.domain, options.options.domain
    kwargs.setdefault('domain', '.%s' % options.options.domain)

    super(BaseHandler, self).set_cookie(*args, **kwargs)

  def clear_cookie(self, *args, **kwargs):
    """Override base clear_cookie to set a domain.  Necessary because the base implementation
    of clear_cookie sets the domain to None, which conflicts with the usage of setdefault
    in BaseHandler.set_cookie.
    """
    # Prepend dot to domain name to allow cookie to be used with any first-level sub-domain.
    assert '.' in options.options.domain, options.options.domain
    kwargs.setdefault('domain', '.%s' % options.options.domain)

    super(BaseHandler, self).clear_cookie(*args, **kwargs)

  @property
  def xsrf_token(self):
    """Override default xsrf_token implementation to always use persistent cookies with the same
    duration as our user cookies.
    """
    if not hasattr(self, "_xsrf_token"):
      token = self.get_cookie("_xsrf")
      if not token:
        token = binascii.b2a_hex(uuid.uuid4().bytes)
        expires_days = _USER_COOKIE_EXPIRES_DAYS
        self.set_cookie("_xsrf", token, expires_days=expires_days)
      self._xsrf_token = token
    return self._xsrf_token

  def on_connection_close(self):
    # Note that this method is not called in our StackContext, so we
    # cannot access ViewfinderContext.current() here.
    self._connection_close_event.set()

  def prepare(self):
    """Checks for logout argument and clears cookie if it is present."""
    self.set_header('X-Frame-Options', 'SAMEORIGIN')

  def _handle_request_exception(self, e):
    """Handles presentation of an exception condition to the user, either as an HTML error page,
    or as a JSON error response.
    """
    try:
      status, message = www_util.HTTPInfoFromException(e)
      self.set_status(status)

      # Write JSON error response if this was a user-level interactive request, otherwise
      # write an HTML error response.
      if self._IsInteractiveRequest():
        title = 'Unknown Error'
        if status == 500:
          logging.error('failure processing %s' % getattr(self, 'api_name', None), exc_info=sys.exc_info())
          message = 'We\'re sorry but an unforeseen error occurred; please try again later.'
        else:
          logging.warning('[%s] %s' % (type(e).__name__, message))
          if status in _ERROR_MAP:
            title = _ERROR_MAP[status]

        self.render('info.html', title=title, message=message, button_url='/', button_text='home')
      else:
        if status == 500:
          logging.error('failure processing %s:\n%s',
                        escape.utf8(getattr(self, 'api_name', 'N/A')),
                        escape.utf8(self.request.body),
                        exc_info=sys.exc_info())
        else:
          logging.warning('[%s] %s' % (type(e).__name__, message))

        error_dict = {'error': {'message': message if message else 'Unknown error.'}}
        util.SetIfNotNone(error_dict['error'], 'method', getattr(self, 'api_name', None))
        util.SetIfNotNone(error_dict['error'], 'id', getattr(e, 'id', None))
        validictory.validate(error_dict, json_schema.ERROR_RESPONSE)
        self.write(error_dict)
        self.finish()
    except Exception:
      # This is the exception handler of last resort - if we don't finish the request here, nothing will,
      # and it will just leak and time out on the client.
      logging.exception('exception in BaseHandler._handle_request_exception')
      self.set_status(500)
      self.finish()

    return True

  def _execute(self, transforms, *args, **kwargs):
    """If a user cookie is present, looks up the corresponding user object and stores it in
    the ViewfinderContext, along with the device_id and viewpoint_id fields of the cookie.
    The context is available for the execution of this request and can be retrieved by invoking
    the ViewfinderContext.current() method.
    """
    @gen.engine
    def _ExecuteTarget():
      """Invoked in the scope of a ViewfinderContext instance."""
      try:
        ViewfinderContext.current().connection_close_event = self._connection_close_event
        self._current_user = None
        self._transforms = transforms

        client = DBClient.Instance()
        user_cookie_dict, user = yield self._ProcessCookie(client)

        if user is not None:
          self.LoginUser(user, user_cookie_dict)

        # Continue on with request processing.
        if not self._MaybeRedirect():
          super(BaseHandler, self)._execute(transforms, *args, **kwargs)

      except Exception as e:
          self._handle_request_exception(e)

    # Establish Viewfinder context, and then call another func, since it is not safe to use a
    # yield in the static scope of the "with stack_context" statement.
    with stack_context.StackContext(ViewfinderContext(self.request)):
      _ExecuteTarget()

  def _IsInteractiveRequest(self):
    """Returns true if this a user-level interactive request. In this case, any error should be
    returned as an HTML page rather than as a JSON error response.
    """
    return self.request.method in ['GET', 'HEAD']

  def _MaybeRedirect(self):
    """ This contains logic for potentially redirecting requests between production and staging clusters.
    True is returned if redirection was done.
    False is returned if the request processing should continue onto next step.
    """
    if self._current_user is None:
      # No user context available, so don't redirect.  This is typical of signon/registration.
      # Continue on with processing this request.
      return False
    elif not self._current_user.IsStaging() and environ.ServerEnvironment.IsStaging():
      # Requests from non-staging users to staging cluster should always be redirected back to production cluster.
      redirect_host = environ.ServerEnvironment.GetRedirectHost()
      self.set_header('X-VF-Staging-Redirect', redirect_host)
      self.redirect('%s://%s%s' % (self.request.protocol, redirect_host, self.request.uri), permanent=True)
      return True
    elif self._current_user.IsStaging() and not environ.ServerEnvironment.IsStaging():
      # Now, check to see if this request is from a web app.
      device_id = ViewfinderContext.current().device_id
      if device_id is not None and self._current_user.webapp_dev_id == device_id:
        # We won't redirect requests from staging users from web apps.
        # Staging users are free to point their web browser at whichever cluster they'd like.
        return False
      else:
        # Redirect to staging cluster.
        redirect_host = environ.ServerEnvironment.GetRedirectHost()
        self.set_header('X-VF-Staging-Redirect', redirect_host)
        self.redirect('%s://%s%s' % (self.request.protocol, redirect_host, self.request.uri), permanent=True)
        return True
    else:
      # Already seems to be hitting the correct cluster, so continue on with processing this request.
      return False

  @gen.coroutine
  def _ProcessCookie(self, client):
    """If a user cookie exists, validates the cookie and then looks up the user id contained
    in that cookie. Returns the tuple (user_cookie, user), where both fields are None if the
    cookie doesn't exist or isn't valid.
    """
    def _ClearCookie(reason):
      """Clear an invalid cookie and log the reason."""
      logging.warning('found invalid cookie (%s): %s' % (reason, user_cookie_dict))
      self.clear_cookie(_USER_COOKIE_NAME)
      raise gen.Return((None, None))

    # Get the user from the cookie, if it exists.
    user_cookie_dict = self.GetUserCookie()
    if user_cookie_dict is None:
      raise gen.Return((None, None))

    user_id = user_cookie_dict.get('user_id', None)
    device_id = user_cookie_dict.get('device_id', None)
    if user_id is None or device_id is None:
      _ClearCookie('no user_id or device_id')

    user = yield gen.Task(User.Query, client, user_id, None, must_exist=False)

    # If "user" does not exist, logs an error and clears the cookie.
    if user is None:
      _ClearCookie('user not found')
    elif user.IsTerminated():
      _ClearCookie('user account terminated')

    raise gen.Return((user_cookie_dict, user))

  def _GetCurrentUserName(self):
    """Returns the full name of the current user. If the user exists,
    but his/her name is not known, returns the user's email address.
    If the email address is not known, returns "Unknown". If no user
    is logged in, returns None.
    """
    cur_user = self.get_current_user()
    if cur_user is None:
      return None

    if cur_user.name:
      return cur_user.name

    if cur_user.email:
      return cur_user.email

    return 'Unknown'

  def _LoadJSONRequest(self):
    """Parse the request body as json (optionally gzipped).

    Returns the parsed object if successful; if unsuccessful may
    either write an error response and return None (in which case the
    caller should simply return immediately) or pass the exception
    through to the caller.

    """
    # Verify application/json; (415: Unsupported Media Type).
    content_type = self.request.headers.get('Content-Type', '')
    if not content_type.startswith('application/json'):
      self.send_error(status_code=415)
      return None

    content_encoding = self.request.headers.get('Content-Encoding')
    if not content_encoding:
      request_body = self.request.body
    elif content_encoding == 'gzip':
      request_body = www_util.GzipDecode(self.request.body)
    else:
      self.send_error(status_code=415)
      return None

    return json.loads(request_body)


  @staticmethod
  def _CreateRequestMessage(client, request, request_schema, callback, migrators=None,
                            min_supported_version=message.MIN_SUPPORTED_MESSAGE_VERSION,
                            max_supported_version=message.MAX_SUPPORTED_MESSAGE_VERSION):
    """Validate the JSON request message according to the specified JSON
    schema, and then migrate the message from its original version to the
    latest version understood by the server. Reject any request with a
    version that does not meet the minimum required version. Reject any
    request with a version that exceeds the maximum version that the server
    fully supports. Return the created message.
    """
    def _OnMigrate(request_message):
      request_message.Validate(request_schema, allow_extra_fields=False)
      request_message.dict['headers']['original_version'] = request_message.original_version
      callback(request_message)

    request_message = message.Message(request,
                                      min_supported_version=min_supported_version,
                                      max_supported_version=max_supported_version)
    request_message.Migrate(client, migrate_version=message.MAX_MESSAGE_VERSION,
                            callback=_OnMigrate, migrators=migrators)

  @staticmethod
  def _CreateResponseMessage(client, response_dict, response_schema, response_version,
                             callback, migrators=None):
    """Validate the fields of the response according to the specified
    JSON schema, sanitize the response, and then migrate the message
    from the message version currently in use by the server to the
    specified response version. Return the created message.
    """
    # Add server message version to response, since handler won't typically add it,
    # and the migrator expects it.
    if not response_dict.has_key('headers'):
      response_dict['headers'] = dict(version=message.MAX_MESSAGE_VERSION)
    else:
      response_dict['headers']['version'] = message.MAX_MESSAGE_VERSION

    # Validate schema before migrating to response version, since the schema is
    # with respect to the server message version rather than the response version.
    response_message = message.Message(response_dict)
    response_message.Validate(response_schema, allow_extra_fields=True)
    response_message.Sanitize()
    response_message.Migrate(client, migrate_version=response_version,
                             callback=callback, migrators=migrators)


class IntervalSummaryLogger(object):
  """Logs the first request for a path, then starts to build a map
  between paths and request count. Every 'self._interval' seconds,
  logs a summary of requests. Non-200 response code values log
  normally.
  """
  _REPORT_INTERVAL_SECS = 30 * 60

  def __init__(self, interval_secs=None):
    self._interval_secs = interval_secs or IntervalSummaryLogger._REPORT_INTERVAL_SECS
    self._next_interval = time.time() + self._interval_secs
    self._request_map = {}

  def log(self, path, status, base_log_func):
    """Log count of healthz requests every _REPORT_INTERVAL_SECS."""
    if status not in (200, 304):
      return base_log_func()

    now = time.time()
    if now >= self._next_interval:
      for path, count in self._request_map.items():
        logging.info('received %d request(s) for %s since last log' % (count, path))
        self._request_map[path] = 0
      self._next_interval = now + self._interval_secs
    else:
      if path not in self._request_map:
        base_log_func()
        self._request_map[path] = 1
      else:
        self._request_map[path] += 1


class StaticFileHandler(web.StaticFileHandler):
  """Subclass of web.StaticFileHandler to do interval summary logging."""
  _logger = IntervalSummaryLogger()

  def _log(self):
    StaticFileHandler._logger.log(self.request.path, self.get_status(),
                                  partial(web.RequestHandler._log, self))


class HealthzHandler(web.RequestHandler):
  """Health of server.

  HTTP response codes and descriptions:

  200: Server is healthy.
  500: Server is not healthy.
  503: Server is lame and should no longer be served requests, but may
       still be processing extant requests.

  TODO(spencer): currently always returns OK; add laming functionality.
  """
  _logger = IntervalSummaryLogger()

  def get(self):
    self.write("OK")

  def _log(self):
    HealthzHandler._logger.log(self.request.path, self.get_status(),
                               partial(web.RequestHandler._log, self))


class JSONLoggingHandler(web.RequestHandler):
  """Logging-only handler.

  Attempt to parse the request body as json and dump as json again to INFO (to remove newlines).
  If parsing fails, log the body itself.
  Always return 200, and always log to INFO.

  We intentionally disable xsrf checks.
  """
  def check_xsrf_cookie(self):
    pass

  def post(self):
    # Verify application/json; (415: Unsupported Media Type).
    content_type = self.request.headers['Content-Type']
    if not content_type.startswith('application/json'):
      self.send_error(status_code=415)
      return

    try:
      msg = json.loads(self.request.body)
      logging.info('%s OK: request: %s' % (self.request.path, json.dumps(msg)))
    except Exception:
      # We specifically do not want to log warning or error as spam could pollute our logs.
      # Log the repr to escape newlines.
      logging.info('%s FAIL: body: %r' % (self.request.path, self.request.body[:256]))

    self.set_status(200)
    self.finish("{}")


class SimpleTemplateHandler(BaseHandler):
  def initialize(self, filename):
    self.filename = filename

  def get(self):
    self.render(self.filename, name=self._GetCurrentUserName())


class TrackingRedirectHandler(BaseHandler):
  """Like tornado.web.RedirectHandler, but logs to Google Analytics."""
  def initialize(self, url, permanent=True):
    self._url = url
    self._permanent = permanent

  def get(self):
    self.redirect(self._url, permanent=self._permanent)
    # Don't block the user request while we fire an asynchronous
    # request to GA.
    with stack_context.NullContext():
      IOLoop.current().add_callback(self.LogAnalytics)

  @gen.engine
  def LogAnalytics(self):
    client = httpclient.AsyncHTTPClient()
    params = dict(
      v='1',
      tid='UA-39428171-1',
      # Client id.  Could be saved in a cookie to track repeat visitors.
      cid=uuid.uuid4(),
      t='pageview',
      dh=self.request.host,
      dp=self.request.path,
      # Anonymous IP.  The protocol doesn't let us pass the client's IP,
      # so we don't want it to log the server's IP instead.
      aip='1',
      )
    if 'Referer' in self.request.headers:
      params['dr'] = self.request.headers['Referer']
    yield client.fetch('http://www.google-analytics.com/collect',
                       method='POST',
                       body=urllib.urlencode(params))


class PageNotFoundHandler(BaseHandler):
  """Displays a 404 error message for unknown page routes."""
  def get(self):
    self.set_status(404)
    self.render('info.html',
                title='404 Not Found.',
                message='We can\'t seem to find the thing you were looking for. '
                        'If you typed the address, double check the spelling.',
                button_url='/',
                button_text='home')
