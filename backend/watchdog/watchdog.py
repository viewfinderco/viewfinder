#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Runs the Viewfinder watchdog.
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import logging
import os
import signal
import sys
import time
from functools import partial

from tornado import ioloop, httpclient, options
from scenario import ScenarioDevice, Scenario
from viewfinder.backend.base import main
from viewfinder.backend.base import util, daemon, secrets, message
from viewfinder.backend.base.environ import ServerEnvironment
from viewfinder.backend.services.sms_mgr import SMSManager
from viewfinder.backend.www import www_util, server

# To avoid running as root, use home directory for lockfile.
LOCK_FILE_NAME = '~/var/run/watchdog.pid'

# A list of phone numbers where you could reach a person who lost a bet.
ALERT_PHONE_NUMBERS = ['14257615705', '14257618852', '16464174337']

# The minimum time in seconds between successive SMS Alerts.
MINIMUM_ALERT_SPACING = 300

# The maximum size of an alert text, in characters.
MAX_TEXT_SIZE = 100


def _FormatServiceHealthReport(report):
  """Create a formatted message from a service health report."""
  assert report.get('status') == 'ALERT'

  message = ''
  sub_messages = []
  alerts = report.get('alerts')
  if len(alerts) > 1:
    message += '(%d Alerts):' % len(alerts)

  for a in alerts:
    sub_message = ' ' + a.get('description', a.get('name'))
    if a.get('cluster', False):
      sub_message += '(Cluster)'
    else:
      sub_message += '(%d machines)' % a.get('count')
    sub_messages.append(sub_message)

  return message + ','.join(sub_messages)


def CheckServiceHealth(device, logger, callback):
  """Simple scenario which pings the service_health endpoint of the service.  This endpoint
  should return a json-encoded status message, which may contain a list of alerts if the
  server has judged itself to be unhealthy.  If any alerts are reported back, this scenario
  will dispatch them.
  """
  def _OnResponse(response):
    response_dict = www_util.ParseJSONResponse(response)
    if response_dict.get('status') == 'alert':
      logger.error(_FormatServiceHealthReport(response_dict))
    else:
      logger.info('CheckServiceHealth passed.')
    callback()

  device.SendRequest('service_health', _OnResponse, 'GET')


def QueryFollowed(device, logger, callback):
  """Simple scenario which calls the viewfinder service's "query_followed" method.
  This will return a list of viewpoints followed by the account to which the device
  is currently authenticated.  This is a simple read-only service query with no
  side effects.
  """
  def _OnResponse(response):
    response_dict = www_util.ParseJSONResponse(response)
    viewpoints = response_dict.get('viewpoints')
    if len(viewpoints) < 1:
      logger.error('query_followed returned 0 viewpoints, should always return at least one.')
    else:
      logger.info('QueryFollowed scenario passed.')
    callback()

  device.SendRequest('service/query_followed', _OnResponse, 'POST', limit=5,
                     headers={'version': message.MAX_SUPPORTED_MESSAGE_VERSION})

# List of scenario objects for the watchdog to run.
SCENARIO_LIST = [Scenario('ServerHealth', CheckServiceHealth, 30,
                          'Pings the service health endpoint, verifying connectivity to Viewfinder.'),
                 Scenario('QueryFollowed', QueryFollowed, 60,
                          'Invokes the query_followed method of the viewfinder service.')]


class Watchdog(logging.Handler):
  """Watchdog manager class, which is derived from the logging Handler class.  The watchdog
  is designed to run a series of watchdog scenarios and monitor log messages coming from those
  scenarios.

  If the watchdog determines that a scenario's log messages warrant an alert, it will dispatch
  an SMS message to a configured set of phone numbers.
  """
  def __init__(self, device, scenarios):
    super(Watchdog, self).__init__(logging.WARNING)
    self.device = device
    self.scenarios = {s.name:s for s in scenarios}
    self.error_stats = {s.name:util.DecayingStat(s.frequency * 2) for s in scenarios}
    self.setFormatter(logging.Formatter('[%(scenario)s] %(message)s'))
    self._alert_hook = None
    self._last_alert = 0

  def Run(self, shutdown_callback):
    """Begin running watchdog scenarios.  The shutdown callback passed into this method
    should be invoked if the Watchdog's Stop() method is invoked.
    """
    self.shutdown_callback = shutdown_callback
    logging.getLogger().addHandler(self)
    for s in self.scenarios.values():
      s.StartLoop(self.device)

  def Stop(self):
    """Stop this Watchdog's scenarios from running.  This method will call the shutdown_callback
    provided to the Run() method."""
    logging.getLogger().removeHandler(self)
    for s in self.scenarios.values():
      s.StopLoop()

    self.shutdown_callback()

  def emit(self, record):
    """The emit method is called whenever log messages of WARNING or greater level are received.
    The watchdog will determine if the specific message warrants the sending of an alert.
    """
    scenario_name = getattr(record, 'scenario', None)
    if scenario_name is not None:
      scenario = self.scenarios[scenario_name]
      error_stat = self.error_stats[scenario_name]
      if record.levelno >= logging.ERROR:
        self.Alert(scenario, self.format(record))
      else:
        error_stat.Add(1)
        if error_stat.Get() > 2:
          self.Alert(scenario, self.format(record))

  def Alert(self, scenario, message):
    """Send an SMS Alert if one has not been sent too recently."""
    logging.info('Alert was called from scenario %s with message %s', scenario.name, message)

    if self._alert_hook is not None:
      self._alert_hook(scenario, message)
      return

    now = time.time()
    if now < self._last_alert + MINIMUM_ALERT_SPACING:
      # An alert has been sent inside of the minimum spacing threshold for alerts.
      logging.info('Alert not sent because another alert had been sent within the past %d seconds: %s',
                   MINIMUM_ALERT_SPACING, message)
      return

    def _OnSendError(t, v, tb):
      logging.error('Error sending alert SMS message.', exc_info=(t, v, tb))

    def _OnSendSuccess(messages):
      self._last_alert = now
      for m in messages:
        logging.info(m)

    with util.ArrayBarrier(_OnSendSuccess, _OnSendError) as b:
      truncated_message = message[:MAX_TEXT_SIZE]
      for number in ALERT_PHONE_NUMBERS:
        SMSManager.Instance().SendSMS(b.Callback(), number, truncated_message, description=truncated_message)


def Shutdown():
  """Shut down the watchdog process."""
  ioloop.IOLoop.current().stop()


def InitAndRun():
  """Start the watchdog process.  This will enter a loop until the process is terminate via an appropriate
  OS signal.
  """
  options.parse_command_line()

  # Set up process signal handlers.
  def _OnSignal(signum, frame):
    logging.info('process stopped with signal %d' % signum)
    Shutdown()

  signal.signal(signal.SIGHUP, _OnSignal)
  signal.signal(signal.SIGINT, _OnSignal)
  signal.signal(signal.SIGQUIT, _OnSignal)
  signal.signal(signal.SIGTERM, _OnSignal)

  # Configure the default logger.
  logging.getLogger().setLevel(logging.INFO)
  logging.getLogger().handlers[0].setLevel(logging.INFO)

  # Initialize the server environment in order to derive the host name.
  ServerEnvironment.InitServerEnvironment()

  # Initialize the Watchdog object.
  watchdog = Watchdog(ScenarioDevice('user1'), SCENARIO_LIST)

  # Initialize Daemon manager.
  # The lockfile is stored in the current user's home directory in order
  # to avoid running with root permissions, which should be unnecessary.
  lock_file = os.path.expanduser(LOCK_FILE_NAME)
  if not os.path.exists(os.path.dirname(lock_file)):
    os.makedirs(os.path.dirname(lock_file))
  dm = daemon.DaemonManager(lock_file)

  _setup_error = [False]

  def _OnInitException(t, v, tb):
    logging.error('Exception during watchdog initialization.', exc_info=(t, v, tb))
    _setup_error[0] = True
    Shutdown()

  def _OnInitIOLoop(shutdown_callback):
    SMSManager.SetInstance(SMSManager())
    watchdog.Run(shutdown_callback)

  def _OnInitDaemon(shutdown_callback):
    _StartIOLoop(partial(_OnInitIOLoop, shutdown_callback))

  def _OnAuthenticated(auth_complete):
    if not auth_complete:
      print 'Waiting for user to authorize...'
      cb = partial(watchdog.device.PollForAuthentication, _OnAuthenticated)
      ioloop.IOLoop.current().add_timeout(time.time() + 15, cb)
    else:
      # Close the IOLoop, which will proceed to daemon setup.
      io_loop = ioloop.IOLoop.current()
      io_loop.stop()
      io_loop.close()

  def _OnGetUserCode(user_code, verification_url):
    print 'Please visit url:\n   %s\n and input user code:\n   %s\n to authorize scenario login.' \
      % (verification_url, user_code)
    _OnAuthenticated(False)

  def _InitWatchdog():
    if watchdog.device.IsAuthenticated():
      # Auth credentials were loaded from file.
      _OnAuthenticated(True)
    else:
      # Get a user code and begin the login process.
      watchdog.device.GetUserCode(_OnGetUserCode)

  def _InitSecrets():
    with util.ExceptionBarrier(_OnInitException):
      secrets.InitSecrets(_InitWatchdog, can_prompt=sys.stderr.isatty())

  if options.options.daemon.lower() == 'stop':
    # Short circuit the program if the daemon is being stopped.
    dm.SetupFromCommandLine(util.NoCallback, util.NoCallback)
  else:
    # The IOLoop will be stopped before entering daemon context.
    # This is because the file descriptors for kqueue cannot be easily preserved.
    _StartIOLoop(_InitSecrets)
    if not _setup_error[0]:
      dm.SetupFromCommandLine(_OnInitDaemon, Shutdown)


def _StartIOLoop(callback):
  """Creates a new IOLoop object, places it into context and schedules the given callback
  on that loop.
  """
  io_loop = ioloop.IOLoop.current()
  # Configure the default http client to use pycurl.
  try:
    httpclient.AsyncHTTPClient.configure('tornado.curl_httpclient.CurlAsyncHTTPClient')
    httpclient.AsyncHTTPClient(io_loop=io_loop, max_clients=100)
  except:
    logging.exception('failed to configure tornado AsyncHTTPClient to use pycurl')

  io_loop.add_callback(callback)
  io_loop.start()
