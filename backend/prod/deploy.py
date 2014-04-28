#!/usr/bin/env python
#
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Sets up the Viewfinder production environment and launches the
babysitter.py server.

Setting up the production environment requires two steps. The first
is to install "tornado" and "boto", used to launch the babysitter.py
webserver. The babysitter runs each of the server instances configured
in the deployment template and is responsible for ensuring they remain
healthy, restarting them as necessary, archiving their logs (copying
them to S3), and reporting to the notification service (SNS).

By default "tornado", "python-daemon" and "boto" are installed. Any
additional production deployment setup is provided to the deploy
script via the setup_script of the deployment template. This script is
run via subprocess and output is sent to this process' stdout and
stderr.

The babysitter is started via a daemon process with stdout and stderr
being directed into logs/STDOUT and logs/STDERR.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import os
import sys
import signal
import subprocess

# Add the viewfinder parent directory to the module search path.
sys.path = [os.path.abspath(os.path.join(os.getcwd(), '..'))] + sys.path

# Standard environment script.
_ENV_SCRIPT = """
easy_install tornado
easy_install boto
easy_install python-daemon
"""

def _RunCommand(args):
  """Runs specified args as a subprocess, redirecting stdout and stderr.
  """
  logging.info("$ %s", " ".join(args))
  p = subprocess.Popen(args)
  if p.wait() != 0:
    sys.exit(p.returncode)


def _ImportDeployTemplate():
  """Returns the setup_script and servers objects from the deployment
  template specified by the first command line argument.
  """
  deploy_template = "viewfinder.backend.prod.deploy.{0}".format(sys.argv[1])
  __import__(deploy_template)
  servers = sys.modules[deploy_template].__dict__["servers"][0]
  setup_script = sys.modules[deploy_template].__dict__["setup_script"][0]
  return servers, setup_script


def _StartBabysitter(servers):
  """Runs the babysitter as a daemon process.
  """
  import daemon
  from viewfinder.backend.prod import babysitter

  os.mkdir('logs')
  context = daemon.DaemonContext(
    working_directory=os.getcwd(),
    stdout=open(os.path.join(os.getcwd(), "logs", "STDOUT"), 'w+'),
    stderr=open(os.path.join(os.getcwd(), "logs", "STDERR"), 'w+'),
    umask=0o002,
    #pidfile=lockfile.FileLock('/var/run/babysitter.pid'),
    )

  context.signal_map = {
    signal.SIGTERM: 'terminate',
    signal.SIGHUP: 'terminate',
    }

  with context:
    babysitter.Start(servers)


def main():
  servers, setup_script = _ImportDeployTemplate()

  # Run standard env script and the deployment startup script.
  cmds = _ENV_SCRIPT.splitlines() + setup_script.splitlines()
  [_RunCommand(cmd.split()) for cmd in cmds if cmd]

  # Start the babysitter as a daemon process.
  _StartBabysitter(servers)

  return 0


if __name__ == "__main__":
  logging.info("starting deployment with template %s",
               sys.argv[1])
  assert len(sys.argv) == 2
  sys.exit(main())

