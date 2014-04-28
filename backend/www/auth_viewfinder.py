# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Viewfinder identity authentication system.

Viewfinder contains internal support for authenticating users by directly verifying ownership
of their email address or SMS number, rather than using an external identity system.

The email identity verification flow via the mobile app is:
  - /<auth>/viewfinder: send Email which contains a ShortURL link to:

  - /verify_id: html page that tries to redirect back to the app on the user's device, or
                else instructs user to type code into the app; the app then invokes:

  - /verify/viewfinder: validates the access token and completes auth.

The email identity verification flow via the web is:
  - /<auth>/viewfinder: send Email which contains a ShortURL link to:

  - /verify_id: html page that will confirm the user's password if the user opens on a
                different computer than sent the email; the page then invokes:

  - /verify/viewfinder: validates the access token and completes auth.

  RegisterViewfinderHandler: /register/viewfinder
  LoginViewfinderHandler: /login/viewfinder
  VerifyIdMobileHandler: /idm/<random_key> (ShortURL)
  VerifyIdWebHandler: /idw/<random_key> (ShortURL)
  VerifyViewfinderHandler: /verify/viewfinder
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import json
import logging
import platform
import re
import subprocess
import time

from tornado import escape, gen, web, options
from tornado.ioloop import IOLoop
from viewfinder.backend.base import base64hex, constants, handler, message, util
from viewfinder.backend.base.exceptions import ExpiredError, InvalidRequestError, PermissionError
from viewfinder.backend.base.environ import ServerEnvironment
from viewfinder.backend.db.identity import EXPIRED_EMAIL_LINK_ERROR, Identity
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.short_url import ShortURL
from viewfinder.backend.db.user import User
from viewfinder.backend.www import base, json_schema, mdetect, password_util
from viewfinder.backend.www.auth import AuthHandler
from viewfinder.backend.www.base import ViewfinderContext
from viewfinder.backend.www.short_url_base import ShortURLBaseHandler
from viewfinder.backend.resources.message import auth_messages
from viewfinder.backend.resources.message.error_messages import ALREADY_LINKED, INVALID_VERIFY_VIEWFINDER
from viewfinder.backend.resources.message.error_messages import MERGE_REQUIRES_LOGIN, TOO_MANY_MESSAGES_DAY
from viewfinder.backend.resources.resources_mgr import ResourcesManager
from viewfinder.backend.services.email_mgr import EmailManager
from viewfinder.backend.services.sms_mgr import SMSManager


_IDENTITY_NOT_SUPPORTED = 'Invalid identity "%s". Only email identities are supported.'

_MISSING_USER_NAME = 'Missing user name in the %s request.'

_FAKE_AUTHORIZATION_FORBIDDEN = 'Fake authorization is not allowed when running against a ' + \
                                'non-local database.'

_REQUEST_MIGRATORS = message.REQUIRED_MIGRATORS + [message.SPLIT_NAMES]


class AuthViewfinderHandler(AuthHandler):
  """Base class from which register and login handlers are derived, containing common methods."""
  @gen.coroutine
  def _StartAuthViewfinder(self, action):
    """Validates the request and prepares to authenticate by creating user, identity, and device
    dicts. Returns a tuple of (user_dict, ident_dict, device_dict).
    """
    # Validate the request.
    if action == 'register':
      schema = json_schema.REGISTER_VIEWFINDER_REQUEST
    elif action == 'login':
      schema = json_schema.LOGIN_VIEWFINDER_REQUEST
    else:
      schema = json_schema.AUTH_VIEWFINDER_REQUEST

    # Strip out names in all but register case for older clients.
    if action == 'register':
      migrators = _REQUEST_MIGRATORS
    else:
      migrators = _REQUEST_MIGRATORS + [message.SUPPRESS_AUTH_NAME]

    yield gen.Task(self._StartJSONRequest, action, self.request, schema, migrators=migrators)

    auth_info_dict = self._request_message.dict['auth_info']

    # Validate the identity key.
    identity_key = auth_info_dict['identity']
    identity_type, identity_value = AuthViewfinderHandler._ValidateIdentityKey(identity_key)

    # Create identity dict.
    ident_dict = {'key': identity_key,
                  'authority': 'Viewfinder'}

    # Create user dict.
    user_dict = {identity_type.lower(): identity_value}
    if action == 'register':
      user_dict['name'] = auth_info_dict['name']
      util.SetIfNotNone(user_dict, 'given_name', auth_info_dict.get('given_name', None))
      util.SetIfNotNone(user_dict, 'family_name', auth_info_dict.get('family_name', None))

      # If password is specified, compute hash and generate salt (if not already generated). 
      password = self._request_message.dict['auth_info'].get('password', None)
      if password is not None:
        # Generate password hash and salt.
        pwd_hash, salt = password_util.GeneratePasswordHash(password)
        user_dict['pwd_hash'] = pwd_hash
        user_dict['salt'] = salt

    # Create device_dict.
    device_dict = self._request_message.dict.get('device', None)

    # Validate input and fill out the dicts.
    yield self._PrepareAuthUser(user_dict, ident_dict, device_dict)

    raise gen.Return((user_dict, ident_dict, device_dict))

  def _FinishAuthViewfinder(self, identity_key):
    """Finishes the Viewfinder auth response, passing back the number of digits used in the
    access token.
    """
    identity_type, identity_value = Identity.SplitKey(identity_key)
    num_digits, good_for = Identity.GetAccessTokenSettings(identity_type, self._UseShortToken())
    self._FinishJSONRequest(None, {'token_digits': num_digits}, json_schema.AUTH_VIEWFINDER_RESPONSE)

  @gen.coroutine
  def _SendVerifyIdMessage(self, user_id, user_name, user_dict, ident_dict, device_dict):
    """Sends an identity verification email or SMS message in order to verify that the user
    controls the identity.
    """
    yield VerifyIdBaseHandler.SendVerifyIdMessage(self._client,
                                                  self._action,
                                                  use_short_token=self._UseShortToken(),
                                                  is_mobile_app=device_dict is not None,
                                                  identity_key=ident_dict['key'],
                                                  user_id=user_id,
                                                  user_name=user_name,
                                                  user_dict=user_dict,
                                                  ident_dict=ident_dict,
                                                  device_dict=device_dict)

  @classmethod
  def _ValidateIdentityKey(cls, identity_key):
    """Validates that the identity key is in canonical format, and that it's either an Email
    or a Phone identity. Returns a tuple containing: (identity_type, identity_value).
    """
    Identity.ValidateKey(identity_key)
    identity_type, identity_value = Identity.SplitKey(identity_key)
    if identity_type not in ['Email', 'Phone']:
      raise web.HTTPError(400, _IDENTITY_NOT_SUPPORTED % identity_key)
    return (identity_type, identity_value)

  def _UseShortToken(self):
    """Returns true if an auth email should directly in-line a short 4-digit access token so
    that the user can manually type it into the mobile or web client.
    """
    return (self._request_message is not None and
            self._request_message.original_version >= message.Message.SEND_EMAIL_TOKEN)


class RegisterViewfinderHandler(AuthViewfinderHandler):
  """Validates register request and sends email or SMS in order to verify control of the identity.
  The VerifyViewfinderHandler will invoke _Finish once the user has proved ownership.
  """
  @handler.asynchronous(datastore=True)
  @gen.engine
  def post(self):
    """POST is used when authenticating via the mobile application."""
    user_dict, ident_dict, device_dict = yield gen.Task(self._StartAuthViewfinder, 'register')

    # If user to register is already logged in with a confirmed cookie, and the requested
    # identity is already bound to the user, then skip the email confirmation step.
    identity = yield gen.Task(Identity.Query, self._client, ident_dict['key'], None)
    context = base.ViewfinderContext.current()
    if context.user is not None and context.user.user_id == identity.user_id and context.IsConfirmedUser():
      assert 'user_id' in user_dict, user_dict
      self._AuthUser(user_dict, ident_dict, device_dict, confirmed=True)
      return

    # Send the email or SMS message in order to verify that the user controls it.
    yield self._SendVerifyIdMessage(identity.user_id, user_dict['name'], user_dict, ident_dict, device_dict)

    self._FinishAuthViewfinder(ident_dict['key'])

  @classmethod
  def _Finish(cls, handler, client, user_dict, ident_dict, device_dict):
    """Invoked by VerifyViewfinderHandler to complete the register action."""
    handler._AuthUser(user_dict, ident_dict, device_dict, confirmed=True)


class LoginViewfinderHandler(AuthViewfinderHandler):
  """Validates login request and sends email or SMS in order to verify control of the identity.
  The VerifyViewfinderHandler will invoke _Finish once the user has proved ownership.

  If the password field is set, then the account does not need to be confirmed in order to
  login, so we don't send email. If the password is *not* set, then we send an account
  confirmation email or SMS. Once the user confirms their account, they get a special
  "confirmed cookie", which gives them a higher level of privilege, such as the ability to
  update their password via the "update_user" service API.
  """
  @handler.asynchronous(datastore=True)
  @gen.engine
  def post(self):
    """POST is used when authenticating via the mobile application."""
    user_dict, ident_dict, device_dict = yield gen.Task(self._StartAuthViewfinder, 'login')

    # Get user to log in (already validated to exist).
    user = yield gen.Task(User.Query, self._client, user_dict['user_id'], None)

    # If password is specified, verify it (raises 403 if it's not correct).
    password = self._request_message.dict['auth_info'].get('password', None)
    if password is not None:
      yield password_util.ValidateUserPassword(self._client, user, password)

      # No need to send email in this case, since user has proved they possess the password.
      self._AuthUser(user_dict, ident_dict, device_dict)
      return

    # Send the email or SMS message in order to verify that the user controls it.
    yield self._SendVerifyIdMessage(user.user_id, user.name, user_dict, ident_dict, device_dict)

    self._FinishAuthViewfinder(ident_dict['key'])

  @classmethod
  def _Finish(cls, handler, client, user_dict, ident_dict, device_dict):
    """Invoked by VerifyViewfinderHandler to complete the login action."""
    handler._AuthUser(user_dict, ident_dict, device_dict, confirmed=True)


class LoginResetViewfinderHandler(AuthViewfinderHandler):
  """This handler is similar to the LoginViewfinderHandler, except that it's used in order
  to obtain a confirmed login cookie that will be used to update the user password. It
  differs in these ways from the stock login case:

  1. The confirmation email is worded differently, since the user is resetting password.

  2. Login via a password is not allowed.
  """
  @handler.asynchronous(datastore=True)
  @gen.engine
  def post(self):
    """POST is used when authenticating via the mobile application."""
    user_dict, ident_dict, device_dict = yield gen.Task(self._StartAuthViewfinder, 'login_reset')

    # Get user to log in (already validated to exist).
    user = yield gen.Task(User.Query, self._client, user_dict['user_id'], None)

    # Send the email or SMS message in order to verify that the user controls it.
    yield self._SendVerifyIdMessage(user.user_id, user.name, user_dict, ident_dict, device_dict)

    self._FinishAuthViewfinder(ident_dict['key'])

  @classmethod
  def _Finish(cls, handler, client, user_dict, ident_dict, device_dict):
    """Invoked by VerifyViewfinderHandler to complete the login action."""
    handler._AuthUser(user_dict, ident_dict, device_dict, confirmed=True)


class MergeTokenViewfinderHandler(AuthViewfinderHandler):
  """This handler produces an access token that proves control of a particular identity that
  needs to be merged into the current user account. The access token will be passed directly
  to the merge_accounts service API method, rather than to /verify/viewfinder.

  This handler expects the target merge user to already be logged in, as that user's name and
  id will be used to generate the email.

  If the "error_if_linked" parameter is true, then the handler raises ALREADY_LINKED if the
  identity is already linked to a user account.
  """
  @handler.asynchronous(datastore=True)
  @gen.engine
  def post(self):
    """POST is used when authenticating via the mobile application."""
    # Validate the request.
    yield gen.Task(self._StartJSONRequest,
                   'merge_token',
                   self.request,
                   json_schema.MERGE_TOKEN_REQUEST,
                   migrators=_REQUEST_MIGRATORS)

    # Validate the identity key.
    identity_key = self._request_message.dict['identity']
    AuthViewfinderHandler._ValidateIdentityKey(identity_key)

    # Require target merge account to be logged in, so that we can get target user name, id, and device type. 
    context = ViewfinderContext.current()
    if context.user is None:
      # This case should never happen in the mobile or web clients, since they will not offer
      # the option to merge if the user is not already logged in. But it could happen with a
      # direct API call.
      raise PermissionError(MERGE_REQUIRES_LOGIN)

    identity = yield gen.Task(Identity.Query, self._client, identity_key, None, must_exist=False)
    if identity is not None and identity.user_id is not None:
      # If "error_if_linked" is true, raise an error, since the identity is already linked to a user.
      if self._request_message.dict.get('error_if_linked', False):
          raise PermissionError(ALREADY_LINKED, account=Identity.GetDescription(identity_key))

    # Send the email or SMS message in order to verify that the user controls it.
    yield VerifyIdBaseHandler.SendVerifyIdMessage(self._client,
                                                  'merge_token',
                                                  use_short_token=self._UseShortToken(),
                                                  is_mobile_app=context.IsMobileClient(),
                                                  identity_key=identity_key,
                                                  user_id=context.user.user_id,
                                                  user_name=context.user.name)

    self._FinishAuthViewfinder(identity_key)


class LinkViewfinderHandler(AuthViewfinderHandler):
  """Validates identity link request and sends email or SMS in order to verify control of the
  identity. The VerifyViewfinderHandler will invoke _Finish once the user has proved ownership.
  """
  @handler.asynchronous(datastore=True)
  @gen.engine
  def post(self):
    """POST is used when authenticating via the mobile application."""
    user_dict, ident_dict, device_dict = yield gen.Task(self._StartAuthViewfinder, 'link')

    # Send the email or SMS message in order to verify that the user controls it.
    current_user = self.get_current_user()
    yield self._SendVerifyIdMessage(current_user.user_id, current_user.name, user_dict, ident_dict, device_dict)

    self._FinishAuthViewfinder(ident_dict['key'])

  @classmethod
  def _Finish(cls, handler, client, user_dict, ident_dict, device_dict):
    """Invoked by VerifyViewfinderHandler to complete the link action."""
    handler._AuthUser(user_dict, ident_dict, device_dict)


class VerifyIdBaseHandler(ShortURLBaseHandler, AuthViewfinderHandler):
  """This is the base request handler for verifying identities. The SendVerifyIdMessage method
  sends out a ShortURL link in a verification email for one of these two scenarios:

    1. Mobile app - handler returns web page that passes access token to web app, either
                    directly, or by instructing the user to enter it manually.

    2. Web - handler returns web page that finalizes registration.

  Derived classes should override the _HandleGet and/or _HandlePost ShortURL methods.
  """
  _MAX_MESSAGES_PER_MIN = 2
  """Maximum number of messages that will be sent to a particular identity per minute."""

  _MAX_MESSAGES_PER_DAY = 20
  """Maximum number of messages that will be sent to a particular identity per day."""

  class ActionInfo(object):
    """Describes the behavior and presentation of each auth action:
         title: title of verification web pages and subject of any email.
         email_type: used to describe the type of email that was sent (e.g. activation).
         email_template: HTML/Text email template from resources directory.
         web_verify_template: Web template to use when displaying a web verification page.
         handler: handler invoked by /verify/viewfinder when verification is complete.
    """
    def __init__(self, title, email_type, email_template, web_verify_template, handler=None):
      self.title = title
      self.email_type = email_type
      self.email_template = email_template
      self.web_verify_template = web_verify_template
      self.handler = handler

  ACTION_MAP = {
    'register': ActionInfo(title=auth_messages.REGISTER_TITLE,
                           email_type=auth_messages.REGISTER_EMAIL_TYPE,
                           email_template='auth_verify_register.email',
                           web_verify_template='auth_verify.html',
                           handler=RegisterViewfinderHandler._Finish),

    'login': ActionInfo(title=auth_messages.LOGIN_TITLE,
                        email_type=auth_messages.LOGIN_EMAIL_TYPE,
                        email_template='auth_verify_login.email',
                        web_verify_template='auth_reset.html',
                        handler=LoginViewfinderHandler._Finish),

    'login_reset': ActionInfo(title=auth_messages.LOGIN_RESET_TITLE,
                              email_type=auth_messages.LOGIN_RESET_EMAIL_TYPE,
                              email_template='auth_verify_reset.email',
                              web_verify_template='auth_reset.html',
                              handler=LoginResetViewfinderHandler._Finish),

    'merge_token': ActionInfo(title=auth_messages.MERGE_TOKEN_TITLE,
                              email_type=auth_messages.MERGE_TOKEN_EMAIL_TYPE,
                              email_template='auth_verify_merge.email',
                              web_verify_template='auth_merge.html'),

    'link': ActionInfo(title=auth_messages.LINK_TITLE,
                       email_type=auth_messages.LINK_EMAIL_TYPE,
                       email_template='auth_verify_link.email',
                       web_verify_template='auth_verify.html',
                       handler=LinkViewfinderHandler._Finish),
    }

  @classmethod
  @gen.coroutine
  def SendVerifyIdMessage(cls, client, action, use_short_token, is_mobile_app, identity_key,
                          user_id, user_name, **kwargs):
    """Sends a verification email or SMS message to the given identity. This message may
    directly contain an access code (e.g. if an SMS is sent), or it may contain a ShortURL
    link to a page which reveals the access code (e.g. if email was triggered by the mobile
    app). Or it may contain a link to a page which confirms the user's password and redirects
    them to the web site (e.g. if email was triggered by the web site).
    """
    # Ensure that identity exists.
    identity = yield gen.Task(Identity.Query, client, identity_key, None, must_exist=False)
    if identity is None:
      identity = Identity.CreateFromKeywords(key=identity_key)
      yield gen.Task(identity.Update, client)

    identity_type, identity_value = Identity.SplitKey(identity.key)
    message_type = 'emails' if identity_type == 'Email' else 'messages'

    # Throttle the rate at which email/SMS messages can be sent to this identity. The updated
    # count will be saved by CreateAccessTokenURL.
    auth_throttle = identity.auth_throttle or {}

    per_min_dict, is_throttled = util.ThrottleRate(auth_throttle.get('per_min', None),
                                                   VerifyIdBaseHandler._MAX_MESSAGES_PER_MIN,
                                                   constants.SECONDS_PER_MINUTE)
    if is_throttled:
      # Bug 485: Silently do not send the email if throttled. We don't want to give user error
      #          if they exit out of confirm code screen, then re-create account, etc.  
      return

    per_day_dict, is_throttled = util.ThrottleRate(auth_throttle.get('per_day', None),
                                                   VerifyIdBaseHandler._MAX_MESSAGES_PER_DAY,
                                                   constants.SECONDS_PER_DAY)
    if is_throttled:
      raise InvalidRequestError(TOO_MANY_MESSAGES_DAY,
                                message_type=message_type,
                                identity_value=Identity.GetDescription(identity.key))

    identity.auth_throttle = {'per_min': per_min_dict,
                              'per_day': per_day_dict}

    # Create a ShortURL link that will supply the access token to the user when clicked.
    # Use a URL path like "idm/*" for the mobile app, and "idw/*" for the web.
    encoded_user_id = base64hex.B64HexEncode(util.EncodeVarLengthNumber(user_id), padding=False)
    group_id = '%s/%s' % ('idm' if is_mobile_app else 'idw', encoded_user_id)
    short_url = yield gen.Task(identity.CreateAccessTokenURL,
                               client,
                               group_id,
                               use_short_token=use_short_token,
                               action=action,
                               identity_key=identity.key,
                               user_name=user_name,
                               **kwargs)

    # Send email/SMS in order to verify that the user controls the identity.
    if identity_type == 'Email':
      args = VerifyIdBaseHandler._GetAuthEmail(client, action, use_short_token, user_name, identity, short_url)
      yield gen.Task(EmailManager.Instance().SendEmail, description=action, **args)
    else:
      args = VerifyIdBaseHandler._GetAccessTokenSms(identity)
      yield gen.Task(SMSManager.Instance().SendSMS, description=action, **args)

    # In dev servers, display a popup with the generated code (OS X 10.9-only).
    if (options.options.localdb and
        platform.system() == 'Darwin' and
        platform.mac_ver()[0] == '10.9'):
      subprocess.call(['osascript', '-e',
                       'display notification "%s" with title "Viewfinder"' % identity.access_token])

  @classmethod
  def _GetAuthEmail(cls, client, action, use_short_token, user_name, identity, short_url):
    """Returns a dict of parameters that will be passed to EmailManager.SendEmail in order to
    email an access token to a user who is verifying his/her account.
    """
    action_info = VerifyIdBaseHandler.ACTION_MAP[action]
    identity_type, identity_value = Identity.SplitKey(identity.key)

    # Create arguments for the email.
    args = {'from': EmailManager.Instance().GetInfoAddress(),
            'fromname': 'Viewfinder',
            'to': identity_value}
    util.SetIfNotNone(args, 'toname', user_name)

    # Create arguments for the email template.
    fmt_args = {'user_name': user_name or identity_value,
                'user_email': identity_value,
                'url': 'https://%s/%s%s' % (ServerEnvironment.GetHost(), short_url.group_id, short_url.random_key),
                'title': action_info.title,
                'use_short_token': use_short_token,
                'access_token': identity.access_token}

    # The email html format is designed to meet these requirements:
    #   1. It must be viewable on even the most primitive email html viewer. Avoid fancy CSS.
    #   2. It cannot contain any images. Some email systems (like Gmail) do not show images by default.
    #   3. It must be short and look good on an IPhone 4S screen. The action button should be visible
    #      without any scrolling necessary.
    resources_mgr = ResourcesManager.Instance()
    if use_short_token:
      args['subject'] = 'Viewfinder Code: %s' % identity.access_token
    else:
      args['subject'] = action_info.title
    args['html'] = resources_mgr.GenerateTemplate(action_info.email_template, is_html=True, **fmt_args)
    args['text'] = resources_mgr.GenerateTemplate(action_info.email_template, is_html=False, **fmt_args)

    # Remove extra whitespace in the HTML (seems to help it avoid Gmail spam filter).
    args['html'] = escape.squeeze(args['html'])

    return args

  @classmethod
  def _GetAccessTokenSms(cls, identity):
    """Returns a dict of parameters that will be passed to SMSManager.SendSMS in order to
    text an access token to a user who is verifying his/her account.
    """
    identity_type, identity_value = Identity.SplitKey(identity.key)
    return {'number': identity_value,
            'text': 'Viewfinder code: %s' % identity.access_token}


class VerifyIdMobileHandler(VerifyIdBaseHandler):
  """This web request handler is invoked when a user clicks an identity verification link in an
  email that was triggered by the mobile app. It renders a page that redirects the user to the
  IOS app if on a mobile device, or instructs the user to enter the access token into the app
  if not.
  """
  # Number of times to try to verify the access token.
  _ACCESS_TOKEN_TRIES = 5

  # Amount of time (in seconds) to wait between access token verification checks.
  _ACCESS_TOKEN_WAIT = 1

  @gen.engine
  def _HandleGet(self, short_url, action, identity_key, user_name, access_token, **kwargs):
    """This handler is invoked in two cases:

      1. The user clicks a ShortURL link in a verification email that was sent to them. In
         this case, we return a page that tries to redirect to the mobile app in order to
         provide it the access code.

      2. Once the redirect has been attempted, the page calls here with a redirected=True
         query parameter. We then poll the server to determine whether the redirect
         succeeded (i.e. if access token was redeemed). If redirect was not successful,
         we return a page to the user that prompts them to manually enter the access code.
    """
    action_info = VerifyIdBaseHandler.ACTION_MAP[action]
    identity = yield gen.Task(Identity.Query, self._client, identity_key, None)

    # The "redirected" flag indicates whether the app redirect has already been attempted.
    redirected = self.get_argument('redirected', None) == 'True'
    if not redirected:
      # If we haven't yet tried to re-direct to the app, verify the access token before giving
      # it back to the client, in order to detect if it has expired.
      try:
        yield identity.VerifyAccessToken(self._client, access_token)
      except Exception as ex:
        logging.info('error during access token verification: %s', ex)
        raise ExpiredError(EXPIRED_EMAIL_LINK_ERROR)

      # If user agent is mobile IOS device, then returned page should try to switch to app.
      user_agent_info = mdetect.UAgentInfo(self.request.headers.get("User-Agent"),
                                           self.request.headers.get("Accept"))
      may_have_app = user_agent_info.detectIos()
    else:
      # The app re-direct attempt is done, so wait several seconds to see if it was successful.
      for i in xrange(VerifyIdMobileHandler._ACCESS_TOKEN_TRIES):
        now = util.GetCurrentTimestamp()
        if now >= identity.expires:
          # Token was redeemed, so assume the app re-direct was successful.
          logging.info('verification of %s succeeded', identity.key)
          self.render('verify_id_success.html', title=action_info.title)
          return

        # Wait and try again.
        logging.info('waiting, then re-checking access token for %s...', identity.key);
        yield gen.Task(IOLoop.current().add_timeout, now + VerifyIdMobileHandler._ACCESS_TOKEN_WAIT)

      # Redirect was attempted, but failed, so user needs to enter access token.
      may_have_app = False

    # Separate groups of three digits.
    access_token_re = re.match(r'(\d\d\d)(\d\d\d)(\d\d\d)', access_token)

    self.render('verify_id.html',
                redirect_failed=redirected,
                may_have_app=may_have_app,
                title=action_info.title,
                email_type=action_info.email_type,
                identity_key=identity.key,
                access_token=access_token,
                code_1=access_token_re.group(1),
                code_2=access_token_re.group(2),
                code_3=access_token_re.group(3))


class VerifyIdWebHandler(VerifyIdBaseHandler):
  """This web request handler is invoked when a user clicks an identity verification link in an
  email that was triggered by a web site page. It renders a page that guides the user through
  the completion of the auth action. This may include confirmation of the user's password, and
  ends with a "well done" kind of page to notify the user that the operation was successful.
  """
  @gen.engine
  def _HandleGet(self, short_url, action, identity_key, user_name, access_token, **kwargs):
    """This handler is invoked when the user clicks a ShortURL link in a verification email
    that was sent to them. Returns a page that guides the user through the completion of
    the operation.
    """
    identity = yield gen.Task(Identity.Query, self._client, identity_key, None)

    # Verify the access token, in case it has expired.
    try:
      yield identity.VerifyAccessToken(self._client, identity.access_token)
    except Exception as ex:
      logging.info('error during access token verification: %s', ex)
      raise ExpiredError(EXPIRED_EMAIL_LINK_ERROR)

    self.render(VerifyIdBaseHandler.ACTION_MAP[action].web_verify_template,
                identity=identity.key,
                access_token=access_token)

  @gen.engine
  def _HandlePost(self, short_url, action, identity_key, user_name, access_token, **kwargs):
    """Used by the auth.html page to validate the user's password as part of the registration
    completion process. This is necessary if the user clicks the email verification link on a
    machine that was different than the one that sent the email in the first place.

    In the case of register, the password sent in the POST body is validated against the
    password hash that was originally stored in the ShortURL that was created by
    RegisterViewfinderHandler. Otherwise, the password is validated against the password hash
    stored in the user record.
    """
    yield gen.Task(self._StartJSONRequest, action, self.request, json_schema.CONFIRM_PASSWORD_REQUEST)

    identity = yield gen.Task(Identity.Query, self._client, identity_key, None)

    # In special case of register, password may not yet be attached to the user object, so get
    # it from a registration parameter rather than from the user.
    if action == 'register':
      salt = kwargs['user_dict']['salt']
      pwd_hash = kwargs['user_dict']['pwd_hash']
    else:
      user = yield gen.Task(User.Query, self._client, identity.user_id, None)
      salt = user.salt.Decrypt()
      pwd_hash = user.pwd_hash.Decrypt()

    yield password_util.ValidatePassword(self._client,
                                         identity.user_id,
                                         self._request_message.dict['password'],
                                         salt,
                                         pwd_hash)

    self._FinishJSONRequest(None, {}, json_schema.CONFIRM_PASSWORD_RESPONSE)


class VerifyViewfinderHandler(AuthHandler):
  """Validates the access token provided in the request. The token was originally sent to an
  email address or SMS number by VerifyIdBaseHandler. Invokes the auth action handler in order
  to complete the operation. If the token has already been redeemed or is expired, returns 403.
  """
  @handler.asynchronous(datastore=True)
  @gen.engine
  def post(self):
    """POST is used when authenticating via the mobile application."""
    yield gen.Task(self._StartJSONRequest, 'verify', self.request, json_schema.VERIFY_VIEWFINDER_REQUEST)

    # Validate the identity and access token.
    identity = yield Identity.VerifyConfirmedIdentity(self._client,
                                                      self._request_message.dict['identity'],
                                                      self._request_message.dict['access_token'])

    # Get the ShortURL associated with the access token.
    group_id = identity.json_attrs['group_id']
    random_key = identity.json_attrs['random_key']
    short_url = yield gen.Task(ShortURL.Query, self._client, group_id, random_key, None)

    # Extract parameters that shouldn't be passed to handler.
    json = short_url.json
    self._action = json.pop('action')
    json.pop('identity_key')
    json.pop('user_name')
    json.pop('access_token')

    # If there is no verification handler, then token was not intended to be redeemed via
    # /verify/viewfinder.
    handler = VerifyIdBaseHandler.ACTION_MAP[self._action].handler
    if handler is None:
      raise InvalidRequestError(INVALID_VERIFY_VIEWFINDER, action=self._action)

    # Invoke the action handler.
    handler(self, self._client, **json)


class FakeAuthViewfinderHandler(AuthViewfinderHandler):
  """Authorization handler used for testing purposes.  Accepts an authorization request
  (consisting of an email identity and a name), and automatically gives authorization to that
  identity without further verifying the content.
  """
  @handler.asynchronous(datastore=True)
  @gen.engine
  def post(self, action):
    """POST is used when authenticating via the mobile application."""
    if not ServerEnvironment.IsDevBox():
      raise web.HTTPError(403, _FAKE_AUTHORIZATION_FORBIDDEN)

    user_dict, ident_dict, device_dict = yield gen.Task(self._StartAuthViewfinder, action)

    # Finish user authentication.
    self._AuthUser(user_dict, ident_dict, device_dict)
