# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Handler for unsubscribing to email alerts.

Emails that we send contain a link that allows the recipient to unsubscribe to future emails.
The handler only supports GET requests, since POST updates are not supported by email.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'


import logging

from tornado import gen
from viewfinder.backend.base import handler, secrets, util
from viewfinder.backend.base.exceptions import InvalidRequestError
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.user import User
from viewfinder.backend.resources.message.error_messages import EXPIRED_LINK, MISSING_PARAMETER
from viewfinder.backend.www import base


class UnsubscribeHandler(base.BaseHandler):
  """Handler that allows users to unsubscribe from email alerts and marketing emails."""
  @handler.asynchronous(datastore=True)
  @gen.engine
  def get(self):
    unsubscribe_cookie = self.get_argument('cookie', None)
    if unsubscribe_cookie is None:
      raise InvalidRequestError(MISSING_PARAMETER, name='unsubscribe_cookie')

    # Get information about the unsubscribe operation from the cookie (passed as query parameter).
    unsubscribe_dict = User.DecodeUnsubscribeCookie(unsubscribe_cookie)
    if unsubscribe_dict is None:
      # The signature doesn't match, so the secret has probably been changed.
      raise InvalidRequestError(EXPIRED_LINK)

    user_id = unsubscribe_dict['user_id']
    email_type = unsubscribe_dict['email_type']
    message = None

    if email_type == AccountSettings.EMAIL_ALERTS:
      logging.info('user %d unsubscribed from email alerts', user_id)
      settings = AccountSettings.CreateForUser(user_id, email_alerts=AccountSettings.EMAIL_NONE)
      message = 'You have successfully unsubscribed from Viewfinder Conversation notifications.'
    else:
      assert email_type == AccountSettings.MARKETING, unsubscribe_dict
      logging.info('user %d unsubscribed from marketing communication', user_id)
      settings = AccountSettings.CreateForUser(user_id, marketing=AccountSettings.MARKETING_NONE)
      message = 'You have successfully unsubscribed from Viewfinder announcements.'

    yield gen.Task(settings.Update, self._client)
    self.render('info.html',
                title='Sad to see you go!',
                message=message,
                button_url=None,
                button_text=None)
