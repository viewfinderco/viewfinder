# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder watchdog tests.
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import logging
import time
from functools import partial

from viewfinder.backend.base import util, testing
from viewfinder.backend.watchdog import watchdog
from viewfinder.backend.watchdog.scenario import ScenarioDevice, Scenario
from viewfinder.backend.base.testing import async_test, async_test_timeout

class LogCatcher(logging.Handler):
  def __init__(self, max_records, max_callback):
    super(LogCatcher, self).__init__(logging.INFO)
    self.saved_records = []
    self.max_records = max_records
    self.max_callback = max_callback

  def emit(self, record):
    self.saved_records.append(record)
    if len(self.saved_records) == self.max_records:
      self.max_callback()

  def __enter__(self):
    logging.getLogger().addHandler(self)

  def __exit__(self, t, v, tb):
    logging.getLogger().removeHandler(self)


class WatchdogTestCase(testing.BaseTestCase, testing.LogMatchTestCase):
  def testScenario(self):
    """Test that a scenario properly handles log messages."""
    fake_device = object()

    def _ScenarioOne(device, logger, callback):
      self.assertTrue(device is fake_device)
      logger.info('Info message')
      callback()

    scenario = Scenario('My Scenario', _ScenarioOne, 0.5)
    catcher = LogCatcher(5, self.stop)
    with catcher:
      scenario.StartLoop(fake_device)
      self.wait(timeout=10)

    self.assertEqual(5, len(catcher.saved_records))
    for r in catcher.saved_records:
      self.assertEqual(r.scenario, 'My Scenario')
      self.assertEqual(r.levelno, logging.INFO)

  def testScenarioError(self):
    """Test that a scenario properly handles thrown exceptions."""
    fake_device = object()

    def _ScenarioTwo(device, logger, callback):
      raise ValueError('Value Error')

    scenario = Scenario('My Scenario', _ScenarioTwo, 0.5)
    catcher = LogCatcher(5, self.stop)
    with catcher:
      scenario.StartLoop(fake_device)
      self.wait(timeout=10)

    self.assertEqual(5, len(catcher.saved_records))
    for r in catcher.saved_records:
      self.assertEqual(r.scenario, 'My Scenario')
      self.assertEqual(r.levelno, logging.ERROR)

  def testServiceHealthMessage(self):
    """Test that the formatted message for service health alerts matches the expected format."""
    expected = '(2 Alerts): Alert description.(2 machines), Cluster alert.(Cluster)'
    report = {'status': 'ALERT',
              'alerts': [
                {'name': 'Alert1', 'count': 2, 'cluster': False, 'description': 'Alert description.'},
                {'name': 'Alert2', 'count': 1, 'cluster': True, 'description': 'Cluster alert.'},
                ]
              }
    self.assertEqual(expected, watchdog._FormatServiceHealthReport(report))

  def testWatchdog(self):
    alerts = {'crit': [], 'err': [], 'warn': [], 'info': []}
    called = {'crit': 0, 'err': 0, 'warn': 0, 'info': 0}

    def _CriticalScenario(device, logger, callback):
      called['crit'] += 1
      logger.critical('Critical error')
      callback()

    def _ErrorScenario(device, logger, callback):
      called['err'] += 1
      logger.error('Error')
      callback()

    def _WarningScenario(device, logger, callback):
      called['warn'] += 1
      logger.warning('Warning')
      callback()

    def _InfoScenario(device, logger, callback):
      called['info'] += 1
      logger.info('Info')
      callback()

    def _AlertHook(scenario, message):
      alerts[scenario.name].append(message)

    wd = watchdog.Watchdog(object(), [Scenario('crit', _CriticalScenario, 0.5),
                                      Scenario('err', _ErrorScenario, 0.5),
                                      Scenario('warn', _WarningScenario, 0.5),
                                      Scenario('info', _InfoScenario, 0.5)
                                      ])
    wd._alert_hook = _AlertHook

    catcher = LogCatcher(23, self.stop)
    with catcher:
      wd.Run(self.stop)
      self.wait()

    self.assertTrue(called['crit'] > 0)
    self.assertTrue(len(alerts['crit']) == called['crit'])
    self.assertTrue(all([m == '[crit] Critical error' for m in alerts['crit']]))

    self.assertTrue(called['err'] > 0)
    self.assertTrue(len(alerts['err']) == called['err'])
    self.assertTrue(all([m == '[err] Error' for m in alerts['err']]))

    self.assertTrue(called['warn'] > 0)
    self.assertTrue(len(alerts['warn']) == called['warn'] - 2)
    self.assertTrue(all([m == '[warn] Warning' for m in alerts['warn']]))

    self.assertTrue(called['info'] > 0)
    self.assertTrue(len(alerts['info']) == 0)
