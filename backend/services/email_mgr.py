# -*- coding: utf-8 -*-
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder email send manager.

Example::

  email_mgr = EmailManager()

  email_mgr.SendEmail(from=u'朋友你好 <john@doe.com>',
                      to='blah@blah.com',
                      subject='Hello friend',
                      text='Just a message',
                      html='<b>Just a message</b>',
                      replyto='Ascii Sender <no_reply@wedoist.com>')
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import base64
import logging
import os
import pprint
import types

from collections import defaultdict
from copy import deepcopy
from tornado import escape, gen, httpclient, options
from viewfinder.backend.base import secrets
from viewfinder.backend.base.exceptions import EmailError

options.define('mailer_domain', default='mailer.viewfinder.co',
               help='domain from which system mail originates; this domain is setup in '
               'conjunction with sendgrid and AWS DNS records so that email sent from '
               'it is signed via DKIM, proving the origin is in fact the stated domain.')
options.define('info', default='info', help='account name for system informational emails')


class EmailManager(object):
  """Abstract email interface.

  Subclasses should override SendEmail.
  """
  _instance = None

  _ATTRS = frozenset(['toname', 'x-smtpapi', 'fromname', 'replyto', 'date', 'files'])
  _REQUIRED_ATTRS = frozenset(['to', 'subject', 'from'])

  def SendEmail(self, callback, description=None, **kwargs):
    """Sends an email message.  Invokes 'callback' on successful completion.

    All Unicode strings will be encoded.  Subclasses should call self._ValidateArgs.
    """
    raise NotImplementedError()

  def _ValidateArgs(self, kwargs):
    if 'text' not in kwargs and 'html' not in kwargs:
      raise EmailError('message not sent; \'text\' or \'html\' fields required')
    for required in self._REQUIRED_ATTRS:
      if required not in kwargs:
        raise EmailError('message not sent; missing required argument %s' % required)

  def GetInfoAddress(self):
    """Returns the address for system informational emails
    (e.g. info@mailer.viewfinder.co).
    """
    return '%s@%s' % (options.options.info, options.options.mailer_domain)

  @staticmethod
  def Instance():
    assert hasattr(EmailManager, '_instance'), 'instance not initialized'
    return EmailManager._instance

  @staticmethod
  def SetInstance(email_mgr):
    """Sets a new instance for testing."""
    EmailManager._instance = email_mgr


class SendGridEmailManager(EmailManager):
  """Sends email via the send grid web API."""
  _BASE_URL = 'https://sendgrid.com/api/mail.send'
  _FORMAT = 'json'

  def __init__(self):
    self._api_user = secrets.GetSecret('sendgrid_api_user')
    self._api_key = secrets.GetSecret('sendgrid_api_key')

  def SendEmail(self, callback, description=None, **kwargs):
    """Sends an email message through SendGrid. Returns 'callback' on
    successful completion. All unicode strings are encoded before
    being sent to SendGrid.
    """
    self._ValidateArgs(kwargs)
    def _OnSend(response):
      """Parses JSON response."""
      if response.error:
        raise EmailError('SendGrid API error: %d %.1024s [%s]' % (response.code, response.error, response.body))
      result = escape.json_decode(response.body)
      if result.get('errors', None):
        raise EmailError('SendGrid API error: %s' % result['errors'])
      logging.info('sent email to: %s, from: %s, description: %s' %
                   (kwargs['to'], kwargs['from'], description or ''))
      callback()

    # Add SendGrid user and key to args.
    kwargs = deepcopy(kwargs)
    kwargs.update({'api_user': self._api_user, 'api_key': self._api_key})
    url = '%s.%s' % (self._BASE_URL, self._FORMAT)

    # Construct multi-part MIME message body.
    boundary = base64.urlsafe_b64encode(os.urandom(16))
    body = ''
    for k, v in kwargs.items():
      body += '--%s\r\n' % boundary
      body += 'Content-Disposition: form-data; name="%s"\r\n\r\n' % k
      body += '%s\r\n' % escape.utf8(v)
    body += '--%s--\r\n' % boundary

    # Construct the HTTP request.
    headers = {'Content-Type' : 'multipart/form-data; boundary=%s' % boundary}
    request = httpclient.HTTPRequest(url,
                                     method='POST',
                                     headers=headers,
                                     body=body)

    http_client = httpclient.AsyncHTTPClient()
    http_client.fetch(request, _OnSend)


class LoggingEmailManager(EmailManager):
  """Dummy email API that just writes its messages to the logs."""
  @gen.coroutine
  def SendEmail(self, description=None, **kwargs):
    self._ValidateArgs(kwargs)
    body = kwargs.pop('text')
    kwargs.pop('html', None)
    logging.info('SENDING EMAIL: %s\n%s' % (description or '', pprint.pformat(kwargs)))
    logging.info('MESSAGE BODY:\n%s' % body)


class TestEmailManager(EmailManager):
  """Dummy email API that just pushes messages into a dictionary keyed by the destination
  email address.
  """
  def __init__(self):
    self.emails = defaultdict(list)

  @gen.coroutine
  def SendEmail(self, description=None, **kwargs):
    self._ValidateArgs(kwargs)
    self.emails[kwargs['to']].append(kwargs)
