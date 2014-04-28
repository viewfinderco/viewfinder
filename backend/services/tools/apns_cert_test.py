#!/usr/bin/env python
"""Test connection to the APNS servers.

This script simply attempts a connection to the various APNS servers to ensure that our
certificates and keys are configured correctly.  Run the script and look at its logs
for lines like "connected to gateway.push.apple.com".

Usage:
  python -m viewfinder.backend.services.tools.apns_cert_test --devbox
"""
import datetime
import logging
from tornado.ioloop import IOLoop

from viewfinder.backend.base.main import InitAndRun
from viewfinder.backend.services.apns import APNS

def DummyFeedbackHandler(*args, **kwargs):
  logging.warning("got feedback for %s" % `(args, kwargs)`)

def Main(callback):
  dev = APNS(environment='dev', feedback_handler=DummyFeedbackHandler)
  prod = APNS(environment='prod', feedback_handler=DummyFeedbackHandler)
  ent = APNS(environment='ent', feedback_handler=DummyFeedbackHandler)

  IOLoop.current().add_timeout(datetime.timedelta(seconds=2), callback)

if __name__ == '__main__':
  InitAndRun(Main)
