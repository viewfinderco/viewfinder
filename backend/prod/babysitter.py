#!/usr/bin/env python
#
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Babysitter server starts instances of servers defined in a deployment
template.

Each server instance is started, monitored, and restarted as
necessary. Log files for each server are archived to S3 as
appropriate, custom cloud watch metrics are reported, and AWS SNS is
used to notify of any unrecoverable failures.

  Start(): Launch the babysitter application (called from main)
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import sys

from tornado import ioloop, options, template

from viewfinder.backend.base import admin_server, basic_auth, handler


options.define("babysitter_port", default=1025,
               help="Port for babysitter status")


class _MainHandler(basic_auth.BasicAuthHandler):
  """Displays the servers being babysat, with status information."""

  _TEMPLATE = template.Template("""
<html>
  <title>Babysitter Status</title>
  <body>Admin: {{ user }}</body>
</html>
""")

  @handler.authenticated()
  def get(self):
    self.write(_MainHandler._TEMPLATE.generate(
        user=self.get_current_user()))


def Start(servers=None):
  """Starts the babysitter tornado web server with SSL.

  :arg servers: server deployment specification.
  """
  print "in babysitter"
  options.parse_command_line()

  babysitter = admin_server.AdminServer(
    handlers=[(r"/", _MainHandler), ],
    port=options.options.babysitter_port)

  print "connect to babysitter via https://{0}:{1}/".format(
    'localhost', options.options.babysitter_port)
  ioloop.IOLoop.instance().start()


def main():
  Start()


if __name__ == "__main__":
  sys.exit(main())
