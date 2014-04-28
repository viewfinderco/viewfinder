# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Handlers to collect profile data from the server."""

__author__ = 'ben@emailscrubbed.com (Ben Darnell)'

import datetime
import logging
from plop.collector import Collector
from tornado import gen
from tornado.ioloop import IOLoop
from viewfinder.backend.base import handler
from viewfinder.backend.www.admin import admin

class ProfileHandler(admin.AdminHandler):
  # Amazon ELB will cut off requests at 60 seconds.  (If we need to collect longer profiles
  # we can ask amazon to raise the limit, but there doesn't appear to be a self-service way
  # to do so)
  DURATION = 55.0

  profile_running = False
  waiters = []

  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  @admin.require_permission(level='root')
  @gen.engine
  def get(self):
    data = yield gen.Task(ProfileHandler.start_profile)
    self.set_header('Content-Type', 'text/plain')
    self.finish(data)

  @staticmethod
  @gen.engine
  def start_profile(callback):
    ProfileHandler.waiters.append(callback)
    if ProfileHandler.profile_running:
      return

    logging.info('starting profiler, will run for %ds' % ProfileHandler.DURATION)
    ProfileHandler.profile_running = True
    collector = Collector()
    collector.start(ProfileHandler.DURATION)

    yield gen.Task(IOLoop.current().add_timeout, datetime.timedelta(seconds=ProfileHandler.DURATION))
    collector.stop()
    data = repr(dict(collector.stack_counts))
    for waiter in ProfileHandler.waiters:
      waiter(data)
    logging.info('finished profile collection')
    ProfileHandler.profile_running = False
