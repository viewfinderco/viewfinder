# Copyright 2012 Viewfinder Inc. All Rights Reserved.

""" Module to collect details about current environment and make these details available to other modules.

Initially, the main purpose of this is to distinguish a server's role as far as production versus staging.  The first
use of this information (along with user data) is to determine if a request should be redirected to the production
or staging cluster.

If running on a dev machine, the '--devbox' option should be provided so that failure to contact AWS/EC2 for
metadata and EC2 tags won't cause a startup failure.
"""

__author__ = 'mike@emailscrubbed.com (Mike Purtell)'

import atexit
import boto
import logging
import shutil
import sys
import tempfile
import time
import os

from viewfinder.backend.base import base_options
from viewfinder.backend.base.ami_metadata import GetAMIMetadata, SetAMIMetadata, Metadata
from viewfinder.backend.base.exceptions import *
from tornado import options, ioloop
from secrets import GetSecret, InitSecrets
from viewfinder.backend.base import base_options  # imported for option definitions

# Holds global ServerEnvironment object
_server_environment = None

# Retry interval while trying to retrieve EC2 instance tags.  This only happens during server startup and
#   10 seconds allows for transient AWS infrastructure problems to clear up without slamming the infrastructure.
_EC2_TAGS_RETRIEVAL_RETRY_SECS = 10

# These values are stored in the EC2 tag, NodeType.
_EC2_TAG_NODETYPE_PRODUCTION = 'PROD'
_EC2_TAG_NODETYPE_STAGING = 'STAGING'

# This directory should be availalbe on all EC2 instances.  It's a 100GB EBS volume.
_EC2_TEMP_DIR = '/mnt/vf_temp'

class ServerEnvironment(object):
  """Encapsulates collection of server environment details."""
  def __init__(self, is_devbox, is_staging):
    self._is_devbox = is_devbox
    self._is_staging = is_staging
    self._staging_host = 'staging.%s' % options.options.domain
    self._prod_host = '%s.%s' % (options.options.www_label, options.options.domain)
    self._vf_temp_dir = options.options.vf_temp_dir if is_devbox else _EC2_TEMP_DIR

  @staticmethod
  def IsDevBox():
    """Returns true if running as if on a developer machine."""
    assert _server_environment is not None
    return _server_environment._is_devbox

  @staticmethod
  def IsStaging():
    """Returns true if running as a staging server."""
    assert _server_environment is not None
    return _server_environment._is_staging
  @staticmethod
  def GetHost():
    """Gets name of current host. This will be staging.<domain> if running as staging server,
    or www.<domain> if running as production server.
    """
    assert _server_environment is not None
    return _server_environment._staging_host if _server_environment._is_staging else _server_environment._prod_host

  @staticmethod
  def GetViewfinderTempDirPath():
    """Gets the path to the temp dir that viewfinder should use as temp.
    """
    assert _server_environment is not None
    if not _server_environment._vf_temp_dir:
      # If running as production, this should already be set.
      # Even if this is devbox, it may have been set explicitly with the vf_temp_dir option.
      assert _server_environment._is_devbox
      # This is commonly the path that will be taken for tests.
      _server_environment._vf_temp_dir = tempfile.mkdtemp()
      atexit.register(shutil.rmtree, _server_environment._vf_temp_dir)

    return _server_environment._vf_temp_dir

  @staticmethod
  def GetRedirectHost():
    """Gets name of host to which staging/production users are redirected if they don't "match"
    the current host. This will be staging.<domain> if running as production server, or
    www.<domain> if running as staging server.
    """
    assert _server_environment is not None
    return _server_environment._prod_host if _server_environment._is_staging else _server_environment._staging_host

  @staticmethod
  def InitServerEnvironment():
    """Collects information during startup about the current server environment.
    This will retry on transient errors and assert for non-transient issues such as mis-configuration.
    """
    global _server_environment

    # Start with options settings.
    is_devbox = options.options.devbox
    is_staging = options.options.is_staging

    # Determine whether running as a staging server if not specified on the command-line.
    if is_staging is None:
      if is_devbox:
        # This is used to skip trying to retrieve AWS metadata and primarily for desktop development.
        is_staging = False
      else:
        # No override has been provided, so dynamically determine which type of instance we're on.

        # Get the AWS/EC2 instance id for the instance this is executing on.
        instance_id = GetAMIMetadata().get('meta-data/instance-id', None)
        if instance_id is None:
          raise ViewfinderConfigurationError(
                "We should have already retrieved the instance id by this point.  " +
                "If running on dev box, use the --devbox option.")

        reservations = None

        # Connect to EC2 and get instance tags.  This is done synchronously as there's nothing else the server
        #   should be doing until this has completed successfully.
        while not reservations:
          try:
            logging.info("Connecting to EC2 to retrieve instance tags")
            ec2conn = boto.connect_ec2(aws_access_key_id=GetSecret('aws_access_key_id'),
                                       aws_secret_access_key=GetSecret('aws_secret_access_key'))
            logging.info("Querying EC2 for instance data for instance: %s" % instance_id)
            reservations = ec2conn.get_all_instances([instance_id, ])
          except Exception  as e:
            logging.warning("Exception while trying to retrieve EC2 instance tags: %s: %s, %s",
                            type(e), e.message, e.args)
            time.sleep(_EC2_TAGS_RETRIEVAL_RETRY_SECS)
          else:
            if reservations is None:
              logging.warning("Empty result while trying to retrieve EC2 instance tags.")
              time.sleep(_EC2_TAGS_RETRIEVAL_RETRY_SECS)

        if len(reservations) != 1:
          raise ViewfinderConfigurationError("Should have gotten one and only one reservation.")
        reservation = reservations[0]
        if len(reservation.instances) != 1:
          raise ViewfinderConfigurationError("There should be one and only one instance in this reservation.")
        instance = reservation.instances[0]
        if instance is None:
          raise ViewfinderConfigurationError("Instance not found in reservation metadata.")
        if instance.__dict__.get('id', None) != instance_id:
          raise ViewfinderConfigurationError(
                "instance id in reservation metadata doesn't match expected value: %s vs. %s." %
                (instance.__dict__.get('id', None), instance_id))

        # Enumerate all the EC2 tags and their values to the log.
        for tagName in instance.__dict__['tags']:
          logging.info("This EC2 Instance Tag[%s]: '%s'" % (tagName, instance.__dict__['tags'][tagName]))

        nodetype = instance.__dict__['tags'].get('NodeType', None)

        logging.info("Retrieved instance tag for NodeType: %s" % nodetype)

        if nodetype == _EC2_TAG_NODETYPE_PRODUCTION:
          is_staging = False
        elif nodetype == _EC2_TAG_NODETYPE_STAGING:
          is_staging = True
        else:
          raise ViewfinderConfigurationError("Invalid EC2 tag for NodeType on this instance.  Tag: %s" % nodetype)

    if is_devbox:
      logging.info("server starting as DevBox instance.")

    if is_staging:
      _server_environment = ServerEnvironment(is_devbox, is_staging)
      logging.info('server starting as Staging instance: %s' % _server_environment.GetHost())
    else:
      _server_environment = ServerEnvironment(is_devbox, is_staging)
      logging.info('server starting as Production instance: %s' % _server_environment.GetHost())

    # Make a record in the log of what revision was last copied to this instance.
    hg_revision = ServerEnvironment.GetHGRevision()
    logging.info("Hg revision: %s" % hg_revision)

  @staticmethod
  def GetHGRevision():
    """Attempts to retrieve the current mercurial revision number from the local
    filesystem.
    """
    filename = os.path.join(os.path.dirname(__file__), '../../hg_revision.txt')
    try:
      with open(filename) as f:
        return f.read().strip()
    except IOError:
      return None


def main():
  """Test/Exercise ServerEnvironment on EC2 instance.
  Initializes AMI Metadata and initializes ServerEnvironment object followed by output of results.
  """
  query_ip = Metadata._QUERY_IP

  options.parse_command_line()

  def _OnInitSecrets():
    ServerEnvironment.InitServerEnvironment()

    if ServerEnvironment.IsDevBox():
      print "IsDevBox environment"
    if ServerEnvironment.IsStaging():
      print "IsStaging environment"
    else:
      print "IsProduction environment"

    ioloop.IOLoop.current().stop()

  def _MetadataCallback(metadata):
    SetAMIMetadata(metadata)
    InitSecrets(_OnInitSecrets, False)

  Metadata(callback=_MetadataCallback, query_ip=query_ip)
  ioloop.IOLoop.current().start()
  return 0


if __name__ == "__main__":
  sys.exit(main())
