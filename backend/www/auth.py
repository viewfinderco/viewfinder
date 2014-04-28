# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Base class for various handlers which authenticate user identities and request necessary
permissions for them:

  AuthGoogleHandler: authenticates via Google.
  AuthFacebookHandler: authenticates via Facebook.
  AuthViewfinderHandler: authenticates using Viewfinder's own identity system.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import logging
import validictory

from copy import deepcopy
from tornado import gen, options, web
from viewfinder.backend.base import handler, util
from viewfinder.backend.base.exceptions import PermissionError
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.user import User
from viewfinder.backend.resources.message.error_messages import ALREADY_LINKED, ALREADY_REGISTERED, NO_USER_ACCOUNT
from viewfinder.backend.resources.message.error_messages import MERGE_REQUIRES_LOGIN, LOGIN_REQUIRES_REGISTER
from viewfinder.backend.www import base, json_schema, www_util


options.define('freeze_new_accounts', False,
               help='disallow creation of new accounts from mobile application')

_NEED_INVITATION_MESSAGE = 'You must receive an invitation to register a Viewfinder account.'

_ACCOUNT_ALREADY_LINKED_MESSAGE = 'There is already a Viewfinder user linked to this account.'

_CANNOT_SET_DEVICE_FOR_USER_MESSAGE = 'Cannot set device for non-existent Viewfinder account.'

_FREEZE_NEW_ACCOUNTS_MESSAGE = 'Due to soaring popularity and demand, we can\'t provide you ' + \
                               'with a Viewfinder account right now. But please do try again later.'

_CANNOT_LINK_TO_PROSPECTIVE = 'You have not registered your Viewfinder account. Register your ' + \
                              'account before adding new email addresses.'


class AuthHandler(base.BaseHandler):
  """Base class for all auth handlers that contains utility methods used
  by multiple derived classes.
  """
  _AUTH_ATTRIBUTE_MAP = {'email': 'email',
                         'first': 'given_name',
                         'first_name': 'given_name',
                         'given_name': 'given_name',
                         'last': 'family_name',
                         'last_name': 'family_name',
                         'family_name': 'family_name',
                         'gender': 'gender',
                         'link': 'link',
                         'locale': 'locale',
                         'name': 'name',
                         'phone': 'phone',
                         'picture': 'picture',
                         'timezone': 'timezone',
                         'pwd_hash': 'pwd_hash',
                         'salt': 'salt'}
  """Maps from attribute names provided by the various auth handlers to attribute names used
  in the user schema.
  """
  @gen.coroutine
  def _StartJSONRequest(self, action, request, schema, migrators=None):
    """Validates the request using the specified schema, and saves the message object as
    self._request_message. A call to this method is matched by a later call to _FinishJSONRequest.
    """
    try:
      # Set api_name for use in any error response.
      self.api_name = action

      self._action = action
      self._request_message = yield gen.Task(base.BaseHandler._CreateRequestMessage,
                                             self._client,
                                             self._LoadJSONRequest(),
                                             schema,
                                             migrators=migrators)
    except Exception as e:
      logging.warning('invalid authentication request:\n%s: %r\n%s' %
                      (type(e).__name__, e.message, util.FormatLogArgument(request.body)))
      raise web.HTTPError(400, 'Invalid registration request.')

  @gen.engine
  def _FinishJSONRequest(self, op, response_dict, schema):
    """Finishes an authentication request by a mobile client and sends back the specified
    response as JSON.
    """
    # Add operation id and timestamp to the response header.
    if op is not None:
      scratch_response_dict = deepcopy(response_dict)
      scratch_response_dict['headers'] = {'op_id': op.operation_id,
                                          'op_timestamp': op.timestamp}
    else:
      scratch_response_dict = response_dict

    self.set_header('Content-Type', 'application/json; charset=UTF-8')
    response_message = yield gen.Task(base.BaseHandler._CreateResponseMessage,
                                      self._client, scratch_response_dict, schema,
                                      self._request_message.original_version)

    # Write response back to the client.
    self.write(response_message.dict)
    self.finish()

  def _StartInteractiveRequest(self, action):
    """Called when an interactive requester has started the authentication
    process. Enables HTML exceptions.
    """
    self._action = action

  def _FinishInteractiveRequest(self):
    """Called when an interactive requester has been authenticated as
    a Viewfinder user. Sets the user cookie and redirects the user to
    either the original URL that was requested, or to the user's photo
    view.
    """
    next = self.get_argument('next', None)
    if next is not None:
      self.redirect(next)
    else:
      self.redirect('/view')

  @gen.coroutine
  def _PrepareAuthUser(self, user_dict, ident_dict, device_dict):
    """Validates incoming user, identity, and device information in preparation for login,
    register, or link action. Derives user id and name and sets them into the user dict.
    """
    # Create json_attrs from the user_dict returned by the auth service.
    ident_dict['json_attrs'] = user_dict

    # Check whether identity is already created.
    identity = yield gen.Task(Identity.Query, self._client, ident_dict['key'], None, must_exist=False)

    # Ensure that user id and device id are allocated.
    current_user = self.get_current_user()

    # Find or allocate the user id.
    if self._action in ['login', 'login_reset']:
      # Require identity to already be linked to an account.
      if identity is not None and identity.user_id is not None:
        user = yield gen.Task(User.Query, self._client, identity.user_id, None, must_exist=False)
      else:
        user = None

      if user is None:
        raise PermissionError(NO_USER_ACCOUNT, account=Identity.GetDescription(ident_dict['key']))

      if not user.IsRegistered():
        # Cannot log into an unregistered account.
        raise PermissionError(LOGIN_REQUIRES_REGISTER)

      user_dict['user_id'] = identity.user_id
    elif self._action == 'register':
      if identity is not None and identity.user_id is not None:
        # Identity should already be bound to a user, so only proceed if registering a prospective user.
        user = yield gen.Task(User.Query, self._client, identity.user_id, None, must_exist=False)
        if user is None or user.IsRegistered():
          # User can be None if there's a DB corruption, or if it's still in the process of
          # creation. Treat this case the same as if the user exists but is already registered. 
          raise PermissionError(ALREADY_REGISTERED, account=Identity.GetDescription(identity.key))

        user_dict['user_id'] = user.user_id
      else:
        # Construct a prospective user with newly allocated user id and web device id.
        user_id, webapp_dev_id = yield User.AllocateUserAndWebDeviceIds(self._client)
        user_dict['user_id'] = user_id

        request = {'headers': {'synchronous': True},
                   'user_id': user_id,
                   'webapp_dev_id': webapp_dev_id,
                   'identity_key': ident_dict['key'],
                   'reason': 'register'}
        yield gen.Task(Operation.CreateAndExecute,
                       self._client,
                       user_id,
                       webapp_dev_id,
                       'CreateProspectiveOperation.Execute',
                       request)

        user = yield gen.Task(User.Query, self._client, user_id, None)
        identity = yield gen.Task(Identity.Query, self._client, ident_dict['key'], None)

      if options.options.freeze_new_accounts:
        raise web.HTTPError(403, _FREEZE_NEW_ACCOUNTS_MESSAGE)
    else:
      assert self._action == 'link', self._action
      if current_user is None:
        # This case should never happen in the mobile or web clients, since they will not offer
        # the option to link if the user is not already logged in. But it could happen with a
        # direct API call.
        raise PermissionError(MERGE_REQUIRES_LOGIN)

      if not current_user.IsRegistered():
        raise web.HTTPError(403, _CANNOT_LINK_TO_PROSPECTIVE)

      if identity is not None and identity.user_id is not None and current_user.user_id != identity.user_id:
        raise PermissionError(ALREADY_LINKED, account=Identity.GetDescription(ident_dict['key']))

      # Ensure that the new identity is created.
      if identity is None:
        identity = Identity.CreateFromKeywords(key=ident_dict['key'])
        yield gen.Task(identity.Update, self._client)

      user = current_user
      user_dict['user_id'] = current_user.user_id

    assert user, user_dict
    assert identity, ident_dict

    if device_dict is not None:
      if 'device_id' in device_dict:
        # If device_id was specified, it must be owned by the calling user.
        if 'user_id' in user_dict:
          # Raise error if the device specified in the device dict is not owned by the calling user.
          device = yield gen.Task(Device.Query, self._client, user_dict['user_id'], device_dict['device_id'],
                                  None, must_exist=False)
          if device is None:
            raise web.HTTPError(403, 'user %d does not own device %d' %
                                (user_dict['user_id'], device_dict['device_id']))
        else:
          logging.warning('device_id cannot be set when user does not yet exist: %s' % device_dict)
          raise web.HTTPError(403, _CANNOT_SET_DEVICE_FOR_USER_MESSAGE)

    raise gen.Return(user)

  @gen.engine
  def _AuthUser(self, user_dict, ident_dict, device_dict, confirmed=False):
    """Called when a requester has been authenticated as a Viewfinder user by a trusted authority
    that provides additional information about the user, such as name, email, gender, etc. At
    this point, we can trust that the identity key provided in "ident_dict" is controlled by the
    calling user.

    Completes the authentication action in two steps: first, makes sure the user id and device
    id are retrieved or allocated as necessary; second, starts a user registration operation and
    returns a login cookie. If "confirmed" is True, then the "confirm_time" field in the user
    cookie is set, indicating the time at which the user confirmed their control of the identity
    via email or SMS. This type of cookie is necessary to perform certain high-privilege
    operations, such as updating the password.

    Registration is synchronous, meaning that the caller will wait until it is complete. This
    ensures that when the caller tries to login immediately following this call, the new user
    will be created and ready.
    """
    before_user = yield gen.Task(self._PrepareAuthUser, user_dict, ident_dict, device_dict)

    # Map auth attribute names to those used by User schema and exclude any attributes that are not yet stored
    # in the User table.
    scratch_user_dict = {'user_id': user_dict['user_id']}
    for k, v in user_dict.items():
      user_key = AuthHandler._AUTH_ATTRIBUTE_MAP.get(k, None)
      if user_key is not None:
        if getattr(before_user, user_key) is None:
          scratch_user_dict[user_key] = v

        # Set facebook email if it has not yet been set.
        if user_key == 'email' and ident_dict['authority'] == 'Facebook':
          if getattr(before_user, 'facebook_email') is None:
            scratch_user_dict['facebook_email'] = v

    # If the device id is not present, then allocate it now.
    if device_dict is not None and 'device_id' not in device_dict:
      device_dict['device_id'] = yield gen.Task(Device._allocator.NextId, self._client)

    # Make synchronous request to ensure user is fully created before returning.
    request = {'headers': {'synchronous': True},
               'user_dict': scratch_user_dict,
               'ident_dict': ident_dict,
               'device_dict': device_dict}
    op = yield gen.Task(Operation.CreateAndExecute,
                        self._client,
                        user_dict['user_id'],
                        device_dict['device_id'] if device_dict is not None else before_user.webapp_dev_id,
                        'RegisterUserOperation.Execute',
                        request)

    if self._action == 'link':
      # Now make asynchronous request (or synchronous if requested by client) to fetch contacts.
      # Fetching contacts can take a long time, so best to do this in the background by default.
      request = {'key': ident_dict['key'],
                 'user_id': user_dict['user_id']}
      if self._IsInteractiveRequest() or self._request_message.dict['headers'].get('synchronous', False):
        request['headers'] = {'synchronous': True}

      op = yield gen.Task(Operation.CreateAndExecute,
                          self._client,
                          user_dict['user_id'],
                          device_dict['device_id'] if device_dict is not None else before_user.webapp_dev_id,
                          'FetchContactsOperation.Execute',
                          request)

    # Get the user that was registered by the operation.
    after_user = yield gen.Task(User.Query, self._client, user_dict['user_id'], None)

    # If the identity was confirmed via email/SMS, set the cookie "confirm_time", which allows
    # the cookie to authorize higher privilege operations, such as setting the user password.
    confirm_time = util.GetCurrentTimestamp() if confirmed else None

    # Create the user cookie dict that will be returned to the caller.
    device_id = after_user.webapp_dev_id if device_dict is None else device_dict['device_id']
    user_cookie_dict = self.CreateUserCookieDict(after_user.user_id,
                                                 device_id,
                                                 after_user.name,
                                                 confirm_time=confirm_time)

    # Sets the user cookie and finishes the request.
    if self._IsInteractiveRequest():
      self.SetUserCookie(user_cookie_dict)
      self._FinishInteractiveRequest()
    else:
      response_dict = {'user_id': user_dict['user_id']}
      if device_dict is not None:
        response_dict['device_id'] = device_dict['device_id']

      use_session_cookie = self._request_message.dict.get('use_session_cookie', None)
      util.SetIfNotNone(user_cookie_dict, 'is_session_cookie', use_session_cookie)

      self.SetUserCookie(user_cookie_dict)
      self._FinishJSONRequest(op, response_dict, json_schema.AUTH_RESPONSE)


class AuthFormHandler(base.BaseHandler):
  """Displays a form allowing users to sign in or register.  The form will be adjusted depending
  on if this is a 'cold' login, or a registration by a prospective user.
  """

  @handler.asynchronous(datastore=True)
  @gen.engine
  def get(self):
    current_user = self.get_current_user()

    if self.get_argument('clear', None) is not None:
      self.ClearUserCookie()
      current_user = None

    if not current_user:
      self.render('auth_login.html')
    elif not current_user.IsRegistered():
      signup_ident = yield gen.Task(current_user.QueryPrimaryIdentity, self._client)

      # The user will have a confirmed cookie in some cases - the signup process does
      # not need to reconfirm the user's identity in this case.  To handle the merge
      # case, we need to provide the original confirmed user cookie in the page's html.
      is_confirmed = base.ViewfinderContext.current().IsConfirmedUser()
      merge_cookie = self.get_cookie(base._USER_COOKIE_NAME) if is_confirmed else None
      self.render('auth_register.html',
                  signup_ident=signup_ident.key,
                  merge_cookie=merge_cookie)
    else:
      self.redirect('/view')


class LogoutHandler(base.BaseHandler):
  """Simple handler to log out the current user by clearing their cookie."""

  def get(self):
    self.ClearUserCookie()
    self.redirect('/')


