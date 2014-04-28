# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder SMS gateway manager.

Example::

  sms_mgr = SMSManager()
  sms_mgr.SendSMS(callback, number='16464174337', text='Hello, world!')
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'greg@emailscrubbed.com (Greg Vandenberg)']

import json
import logging
import urllib

from collections import defaultdict
from tornado import escape, gen, httpclient
from viewfinder.backend.base import secrets
from viewfinder.backend.base.exceptions import SMSError

class SMSManager(object):
  """Sends sms via the send grid web API."""
  _instance = None

  def _ValidateArgs(self, number, text):
    assert number, number
    assert text, text

  @staticmethod
  def Instance():
    assert hasattr(SMSManager, '_instance'), 'instance not initialized'
    return SMSManager._instance

  @staticmethod
  def SetInstance(sms_mgr):
    """Sets a new instance for testing."""
    SMSManager._instance = sms_mgr


class TwilioSMSManager(SMSManager):
  """Sends sms via the twilio api."""
  def __init__(self):
    self._api_account_sid = secrets.GetSecret('twilio_account_sid')
    self._api_token = secrets.GetSecret('twilio_auth_token')
    self._api_number = secrets.GetSecret('twilio_api_number')
    self._sms_gateway_api_url = 'https://api.twilio.com/2010-04-01/Accounts/%s/SMS/Messages.json' % \
                                self._api_account_sid

  @gen.coroutine
  def SendSMS(self, description=None, **kwargs):
    """Sends an SMS message through the SMS gateway to 'number' with the
    specified 'text' content.
    """
    number = kwargs['number']
    text = kwargs['text']
    self._ValidateArgs(number, text)

    args = {
      'Body': escape.utf8(text),
      'To': number,
      'From': self._api_number
    }

    http_client = httpclient.AsyncHTTPClient()
    response = yield gen.Task(http_client.fetch,
                              self._sms_gateway_api_url,
                              method='POST',
                              body=urllib.urlencode(args),
                              auth_username=self._api_account_sid,
                              auth_password=self._api_token)
    if response.error:
      raise SMSError('Twilio API error: %d %r [%s] (args: %r)' % (response.code, response.error, response.body, args))

    logging.info('sent sms to: %s, description: %s' % (number, description or ''))
    raise gen.Return(json.loads(response.body))


class ClickatellSMSManager(SMSManager):
  """Sends sms via the clickatell api."""
  _SMS_GATEWAY_API_URL = 'https://api.clickatell.com/http/sendmsg'

  def __init__(self):
    self._api_user = secrets.GetSecret('clickatell_api_user')
    self._api_password = secrets.GetSecret('clickatell_api_password')
    self._api_id = secrets.GetSecret('clickatell_api_id')
    self._api_number = secrets.GetSecret('clickatell_api_number')

  @gen.coroutine
  def SendSMS(self, description=None, **kwargs):
    """Sends an SMS message through the SMS gateway to 'number' withe
    specified 'text' content.
    """
    number = kwargs['number']
    text = kwargs['text']
    self._ValidateArgs(number, text)

    args = {
      'user': self._api_user,
      'password': self._api_password,
      'api_id': self._api_id,
      'to': number,
      'MO': '1',
      'from': self._api_number,
      'text': escape.utf8(text),
    }

    http_client = httpclient.AsyncHTTPClient()
    response = yield gen.Task(http_client.fetch,
                              self._SMS_GATEWAY_API_URL,
                              method='POST',
                              body=urllib.urlencode(args))

    if response.error:
      response.rethrow()
    logging.info('sent sms to: %s, description: %s' % (number, description or ''))
    raise gen.Return(json.loads(response.body))


class LoggingSMSManager(SMSManager):
  """Dummy SMS API that just writes its messages to the logs."""
  @gen.coroutine
  def SendSMS(self, description=None, **kwargs):
    number = kwargs['number']
    text = kwargs['text']
    self._ValidateArgs(number, text)
    logging.info('SENDING TEXT TO %s: %s, description: %s' % (number, escape.utf8(text), description or ''))


class TestSMSManager(SMSManager):
  """Dummy sms API that just pushes messages into a dictionary keyed by the destination
  phone number.
  """
  def __init__(self):
    self.phone_numbers = defaultdict(list)

  @gen.coroutine
  def SendSMS(self, description=None, **kwargs):
    number = kwargs['number']
    text = kwargs['text']
    args = {
      'Body': escape.utf8(text),
      'To': number,
    }

    self._ValidateArgs(number, text)
    self.phone_numbers[args['To']].append(args)
