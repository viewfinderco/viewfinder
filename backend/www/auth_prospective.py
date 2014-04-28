# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Authenticates prospective users.

Prospective users are sent invitation URL's via email or SMS messages. These invitations take
the form of a ShortURL that is bound to a particular viewpoint. Anyone who follows the
invitation link will receive a prospective user cookie in response, which authorizes them to
fetch metadata about the viewpoint, and to load photos contained in that viewpoint. Once the
cookie has been set, the user is typically redirected to the corresponding conversation page
in the website. However, they can also be redirected to the viewpoint cover photo, or to the
unsubscribe page.
"""

__authors__ = ['andy@emailscrubbed.com (Andrew Kimball)']

import re
import urlparse

from copy import deepcopy
from tornado import gen
from urllib import urlencode
from viewfinder.backend.base import base64hex, constants, util
from viewfinder.backend.base.environ import ServerEnvironment
from viewfinder.backend.base.exceptions import ExpiredError, InvalidRequestError
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.short_url import ShortURL
from viewfinder.backend.db.user import User
from viewfinder.backend.www.auth_viewfinder import AuthViewfinderHandler
from viewfinder.backend.www.base import ViewfinderContext
from viewfinder.backend.www.photo_store import PhotoStoreHandler
from viewfinder.backend.www.short_url_base import ShortURLBaseHandler


class AuthProspectiveHandler(ShortURLBaseHandler, AuthViewfinderHandler):
  """Creates prospective user invitation links and handles their redemption and conversion
  to prospective user cookies.
  """
  @gen.engine
  def _HandleGet(self, short_url, identity_key, viewpoint_id, default_url, is_sms=False, is_first_click=True):
    """Invoked when a user follows a prospective user invitation URL. Sets a prospective user
    cookie that identifies the user and restricts access to a single viewpoint. Typically
    redirects the user to the corresponding website conversation page.
    """
    identity = yield gen.Task(Identity.Query, self._client, identity_key, None, must_exist=False)

    # Check for rare case where the identity has been unlinked since issuing the prospective user link.
    if identity is None or identity.user_id is None:
      raise ExpiredError('The requested link has expired and can no longer be used.')

    # If the "next" query argument is specified, redirect to that, otherwise fall back on default_url.
    next_url = self.get_argument('next', default_url)
    if urlparse.urlparse(next_url).hostname is not None:
      raise InvalidRequestError('Cannot redirect to absolute URL: %s' % next_url)

    # Detect photo store redirect, as we should not set a cookie or return redirection to photo store in this case.
    photostore_re = re.match(r'.*/episodes/(.*)/photos/(.*)(\..)', next_url)

    # If the link was sent via SMS, then reset the SMS alert count (since the link was followed).
    if is_sms:
      settings = AccountSettings.CreateForUser(identity.user_id, sms_count=0)
      yield gen.Task(settings.Update, self._client)

    # A registered user can no longer use prospective user links.
    user = yield gen.Task(User.Query, self._client, identity.user_id, None)
    if user.IsRegistered():
      # If not already logged in with the same user with full access, redirect to the auth page.
      context = ViewfinderContext.current()
      if context is None:
        current_user = None
        current_viewpoint_id = None
      else:
        current_user = context.user
        current_viewpoint_id = context.viewpoint_id

      if current_user is None or current_user.user_id != identity.user_id or current_viewpoint_id is not None:
        self.ClearUserCookie()
        self.redirect('/auth?%s' % urlencode(dict(next=next_url)))
        return
    else:
      # If this is the first time the link was clicked, then create a confirmed cookie.
      if is_first_click:
        confirm_time = util.GetCurrentTimestamp()

        # Update is_first_click.
        new_json = deepcopy(short_url.json)
        new_json['is_first_click'] = False
        short_url.json = new_json
        yield gen.Task(short_url.Update, self._client)
      else:
        confirm_time = None

      # Set the prospective user cookie. Make it a session cookie so that it will go away when
      # browser is closed.
      user_cookie_dict = self.CreateUserCookieDict(user.user_id,
                                                   user.webapp_dev_id,
                                                   user_name=user.name,
                                                   viewpoint_id=viewpoint_id,
                                                   confirm_time=confirm_time,
                                                   is_session_cookie=True)

      # Do not set the user cookie if this is a photo view request. 
      self.LoginUser(user, user_cookie_dict, set_cookie=photostore_re is None)

    # Handle photostore redirect request internally rather than returning the redirect to the
    # client. Email clients do not keep cookies, so it is not possible to redirect to an
    # authenticated URL.
    if photostore_re:
      episode_id = photostore_re.group(1)
      photo_id = photostore_re.group(2)
      suffix = photostore_re.group(3)
      next_url = yield PhotoStoreHandler.GetPhotoUrl(self._client, self._obj_store, episode_id, photo_id, suffix)

    # Redirect to the URL of the next page.
    self.redirect(next_url)
