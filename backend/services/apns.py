# -*- coding: utf-8 -*-
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Apple Push Notification service client.

Original copyright for this code: https://github.com/jayridge/apnstornado

The SSL handshake and connection can be tested on the command line via:

% openssl s_client -connect gateway.sandbox.push.apple.com:2195 -cert ~/.ssh/apns_sandbox_cert.pem -debug

  TestService: mock version of APNs cloud service for testing
  APNS: APNs client
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import ctypes
import logging
import socket
import struct
import time

from collections import deque
from tornado.ioloop import IOLoop
from tornado.iostream import SSLIOStream
from viewfinder.backend.base import secrets
from viewfinder.backend.services.apns_util import TokenFromBinary, CreateMessage, ParseResponse


class _BaseSSLService(object):
  """Base SSL connection to Apple's push notification servers. Retry on
  disconnect is handled via an exponential backoff.
  """
  _MAX_BACKOFF_SECS = 600.0  # 10 minutes
  _PUSH_TOKEN_FMT = '%s:%s'

  def __init__(self, settings, host_key):
    self._settings = settings
    self._host = settings[host_key]
    self._retries = 0
    self._io_loop = IOLoop.current()
    self._ResetBackoff()
    self._Connect()

  def IsValid(self):
    return self._stream is not None

  def _FormatPushToken(self, token):
    return _BaseSSLService._PUSH_TOKEN_FMT % (self._settings['token-prefix'], token)

  def _Connect(self):
    try:
      ssl_options = {'certfile': secrets.GetSecretFile(self._settings['certfile'])}
      self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
      self._stream = SSLIOStream(self._sock, io_loop=self._io_loop, ssl_options=ssl_options)
      self._stream.set_close_callback(self._OnClose)
      self._stream.connect(self._host, self._OnConnect)
    except KeyError:
      logging.warning('failed to initialize connection to APN service at %s:%d '
                      'whose certificate is missing from secrets/%s' %
                      (self._host[0], self._host[1], self._settings['certfile']))
      return
    except:
      self._stream = None
      raise

  def _OnConnect(self):
    logging.info("connected to %s:%d" % (self._host[0], self._host[1]))

  def _ResetBackoff(self):
    """Resets backoff to 'reconnect_lag' setting."""
    self._backoff = self._settings.get('reconnect_lag')

  def _OnClose(self):
    logging.info("disconnected from %s:%d" % (self._host[0], self._host[1]))
    try:
      self._stream.close()
    except:
      pass
    finally:
      self._stream = None

    timeout = time.time() + self._backoff
    self._io_loop.add_timeout(timeout, self._Connect)
    self._backoff = min(_BaseSSLService._MAX_BACKOFF_SECS, self._backoff * 2)


class _FeedbackService(_BaseSSLService):
  """A binary connection to the APNs feedback loop, which notifies
  the provider of message delivery failures.
  """
  MESSAGE_SIZE = 38

  def __init__(self, settings, feedback_handler):
    self._feedback_handler = feedback_handler
    super(_FeedbackService, self).__init__(settings, 'feedback_host')

  def _OnConnect(self):
    super(_FeedbackService, self)._OnConnect()
    # The feedback server may close the connection immediately after the SSL handshake, so
    # the stream may already be closed by the time the connect callback is run (this is more
    # common under heavy load since we may process multiple packets per IOLoop iteration).
    if not self._stream.closed():
      self._stream.read_bytes(_FeedbackService.MESSAGE_SIZE, self._OnRead)

  def _OnRead(self, data):
    try:
      assert len(data) == _FeedbackService.MESSAGE_SIZE
      timestamp, toklen, token = struct.unpack_from('!IH32s', data, 0)
      if self._feedback_handler:
        self._feedback_handler(self._FormatPushToken(TokenFromBinary(token)), timestamp)
      # Since data was successfully read, we reset backoff.
      self._ResetBackoff()
    finally:
      if not self._stream.closed():
        self._stream.read_bytes(_FeedbackService.MESSAGE_SIZE, self._OnRead)


class _APNService(_BaseSSLService):
  """A binary connection to the APNs service, which pushes
  notifications to iOS and MacOS devices.

  Note that due to the limitations of the APNS protocol (i.e. the lack of
  acknowledgement of successful messages), messages may be dropped
  if a connection closes due to network errors or if this process terminates.
  """
  MESSAGE_SIZE = 6

  def __init__(self, settings, feedback_handler):
    self._feedback_handler = feedback_handler
    self._write_queue = deque()
    self._recent = None
    self._ready = False
    self._generation = ctypes.c_uint32(0)
    super(_APNService, self).__init__(settings, 'apns_host')

  def IsIdle(self):
    """Best guess at whether we've dispatched all work. Due to the lack of response on successful
    requests, we can't actually be 100% sure.
    """
    return len(self._write_queue) == 0 and (self._stream is None or not self._stream.writing())

  def Push(self, token, alert=None, badge=None, sound=None, expiry=None, extra=None, timestamp=None):
    """Creates a binary message from input parameters and adds it to the
    outgoing write queue.
    """
    self._generation.value += 1
    identifier = self._generation.value
    logging.debug('pushing notification to APNs for token %s, badge %r, alert %s' %
                  (token, badge, alert))
    msg = CreateMessage(token, alert=alert, badge=badge, sound=sound,
                        identifier=identifier, expiry=expiry, extra=extra)

    self._write_queue.append(dict(identifier=identifier, token=token, msg=msg))
    self._io_loop.add_callback(self._PushOne)

  def _PushOne(self):
    # IsValid means the IOStream exists; _ready means it's connected
    # and hasn't been invalidated by an error.
    if len(self._write_queue) and self.IsValid() and self._ready:
      msg = self._write_queue.popleft()
      try:
        self._stream.write(msg['msg'])
      except Exception:
        self._write_queue.appendleft(msg)
        return False
      self._recent.append(msg)
      # Since data was successfully written, we reset backoff.
      self._ResetBackoff()
      return True
    return False

  def _OnConnect(self):
    """On connection, immediately process all enqueued push notifications."""
    _BaseSSLService._OnConnect(self)
    self._recent = deque(maxlen=100)
    self._ready = True
    while self._PushOne():
      pass
    self._stream.read_bytes(_APNService.MESSAGE_SIZE, self._OnRead)

  def _OnRead(self, data):
    """If a pushed message is invalid, APNs returns an error message specifying
    the identifier. The connection is also closed and must be reopened.
    """
    logging.debug('_OnRead: %d bytes' % (len(data)))
    try:
      status, identifier, err_string = ParseResponse(data)
      # Zero means "no error".  Apple apparently does not send non-error acks,
      # but the error code is in their docs.
      if status == 0:
        # In case apple starts sending these, just skip it and read the next one.
        self._stream.read_bytes(_APNService.MESSAGE_SIZE, self._OnRead)
        return

      logging.warning('error pushing notification: %d %d %s' % (status, identifier, err_string))
      self._ready = False
      found = None
      recent = list(self._recent)  # deques don't support slicing
      for i, msg in enumerate(recent):
        if msg['identifier'] == identifier:
          found = i
          break
      if found is not None:
        # We got an error on one message; anything later must be re-sent.
        for msg in recent[found + 1:]:
          self._write_queue.appendleft(msg)
        if status == 8:  # "bad token"
          token = msg['token']
          if self._feedback_handler:
            self._feedback_handler(self._FormatPushToken(token))
      # Since data was successfully read, we reset backoff.
      self._ResetBackoff()
    except:
      logging.exception('Processing APNS failed')
    # Close the connection; apple doesn't accept any more traffic after
    # an error (and should be closing the connection from their side too).
    self._stream.close()


class TestService(object):
  """A mocked version of APNs which stores all pushed notifications
  and allows a token to be marked as bad in order to test the
  feedback handler mechanism.
  """
  _instance = None

  """Prefix for test tokens."""
  PREFIX = 'apns-test:'

  def __init__(self, feedback_handler):
    self._feedback_handler = feedback_handler
    self._notifications = dict()
    self._bad_tokens = set()

  def IsIdle(self):
    # Test APNS service is instantaneous.
    return True

  def MarkTokenBad(self, token):
    """Marks the specified token as bad. The next notification
    pushed to this token will activate the feedback handler.
    """
    if token.startswith(TestService.PREFIX):
      token = token[len(TestService.PREFIX):]
    self._bad_tokens.add(token)

  def GetNotifications(self, token):
    """Returns the list of notifications which have been pushed to
    this token.
    """
    return self._notifications.get(token, [])

  def Push(self, token, alert=None, badge=None, sound=None, expiry=None, extra=None, timestamp=None):
    """If the token is bad, invokes the feedback handler. Otherwise,
    adds the notification to a list of notifications sent for this
    token.
    """
    if token in self._bad_tokens:
      self._feedback_handler('%s%s' % (TestService.PREFIX, token), time.time())
    else:
      msg = {'alert': alert, 'badge': badge, 'sound': sound, 'expiry': expiry, 'extra': extra}
      if token not in self._notifications:
        self._notifications[token] = list()
      self._notifications[token].append(msg)

  @staticmethod
  def Instance():
    assert hasattr(TestService, '_instance'), 'test service not initialized'
    return TestService._instance

  @staticmethod
  def SetInstance(instance):
    TestService._instance = instance


class APNS(object):
  """Maintains connections to the APNs service and to the feedback
  service. The feedback connection is processed periodically in an
  async timer callback to handle push notification delivery failures.
  The APNs connection is used on demand to push notifications.
  """
  _SETTINGS = {
    'dev': {
      'token-prefix': 'apns-dev',
      'certfile': 'apns_sandbox_cert.pem',
      'apns_host': ('gateway.sandbox.push.apple.com', 2195),
      'feedback_host': ('feedback.sandbox.push.apple.com', 2196),
      'reconnect_lag': 5, # seconds
      },
    'ent': {
      'token-prefix': 'apns-ent',
      'certfile': 'apns_enterprise_cert.pem',
      'apns_host': ('gateway.push.apple.com', 2195),
      'feedback_host': ('feedback.push.apple.com', 2196),
      'reconnect_lag': 1, # seconds
      },

    'prod': {
      'token-prefix': 'apns-prod',
      'certfile': 'apns_cert.pem',
      'apns_host': ('gateway.push.apple.com', 2195),
      'feedback_host': ('feedback.push.apple.com', 2196),
      'reconnect_lag': 1, # seconds
      },
    }

  _instance_map = dict()

  def __init__(self, environment='dev', feedback_handler=None):
    if environment == 'test':
      TestService.SetInstance(TestService(feedback_handler))
      self._apn_service = TestService.Instance()
      return
    self._settings = APNS._SETTINGS[environment]
    self._apn_service = _APNService(self._settings, feedback_handler)
    self._feedback_service = _FeedbackService(self._settings, feedback_handler)

  def IsIdle(self):
    return self._apn_service.IsIdle()

  def Push(self, token, alert, badge, sound, expiry, extra, timestamp):
    """Pushes the notification specified by the supplied parameters to APNs.
    """
    self._apn_service.Push(token, alert, badge, sound, expiry, extra, timestamp)

  @staticmethod
  def Instance(environment):
    assert environment in APNS._instance_map, '%s APNs instance not available' % environment
    return APNS._instance_map[environment]

  @staticmethod
  def SetInstance(environment, apns):
    """Sets a new instance for testing."""
    APNS._instance_map[environment] = apns
