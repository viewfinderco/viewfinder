#!/usr/bin/env python
#
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""An interface to access Amazon Machine Instance (AMI) metadata.

The Metadata class provides a convenient interface to AMI metadata and
userdata. Metadata is configured dynamically and for each instance
individually; it contains values such as local and public IP
addresses, AMI instance and type information, launch index, and
security groups. Userdata is specified statically at instance launch
time and all instances receive the same userdata contents.

Internally, uses the tornado asynchronous http client to retrieve AMI
instance metadata from the static IP address:
http://169.254.169.254/latest/{meta-data,user-data}.

  Metadata: retrieves commonly used metadata and userdata and provides
            an interface for retrieving additional metadata.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import sys
from functools import partial
from tornado import httpclient, options, web, ioloop
from viewfinder.backend.base import util


options.define("mock", default=False,
               help="True to create a mock server for testing")

_metadata = dict()
"""Instance-specific AMI metadata."""

def GetAMIMetadata():
  return _metadata

def SetAMIMetadata(metadata):
  global _metadata
  _metadata = metadata

class Metadata(object):
  """Data object that provides a convenient interface to the Amazon AMI
  metdata and userdata. On instantiation, a default set of most
  commonly used metadata is queried asynchronously by default. If
  callback is specified, then it is invoked upon completion of this
  first set of queries. The default set contains:

  ami-id, ami-launch-index, hostname, instance-id, instance-type,
  local-hostname, local-ipv4, public-hostname, public-ipv4
  """
  _QUERY_IP = "169.254.169.254"
  _QUERY_VERSION = "latest"

  def __init__(self, callback=None, query_ip=_QUERY_IP, query_version=_QUERY_VERSION):
    """Creates a `Metadata`.

    If `callback` is specified, launches async retrieval of commonly
    used metadata values and the userdata and invokes `callback` upon
    completion. Callback is invoked with a dictionary containing the
    common metadata and the userdata.

    :arg callback: invoked when default metadata is available
    :arg query_ip: IP address to query for metadata;
    default 169.254.169.254
    :arg query_version: Version of metadata; default 'latest'
    """
    self._query_ip = query_ip
    self._query_version = query_version
    if callback:
      self._FetchCommonMetadata(callback)

  def FetchMetadata(self, paths, callback):
    """Asynchronously fetches metadata for the specified path(s) and
    on completion invokes the callback with the retrieved metadata
    value. 'paths' can be iterable over multiple metadata to fetch;
    if not, adds it to a list.
    """
    metadata = {}

    def _OnFetch(path, callback, response):
      if response.code == 200:
        metadata[path] = response.body.strip()
      else:
        logging.error("error fetching '%s': %s", path, response.error)
      callback()

    if type(paths) in (unicode, str):
      paths = [paths]

    with util.Barrier(partial(callback, metadata)) as b:
      for path in paths:
        logging.info('fetching metadata from %s' % self._GetQueryURL(path))
        http_client = httpclient.AsyncHTTPClient()
        http_client.fetch(self._GetQueryURL(path), partial(_OnFetch, path, b.Callback()),
                                connect_timeout=1, request_timeout=5)

  def _GetQueryURL(self, path):
    """Returns a query URL for instance metadata using the specified path.
    """
    return "http://{0}/{1}/{2}".format(
      self._query_ip, self._query_version, path)

  def _FetchCommonMetadata(self, callback):
    """Fetches common metadata values and compiles the results into
    a dictionary, which is passed to the callback on completion.

    NOTE: the AWS metadata server has some sort of internal rate-limiting
          for this data and will return 404 errors if too many are done
          in parallel. So, we fetch them serially.
    """
    paths = [ "meta-data/hostname", "meta-data/instance-id", "user-data/passphrase" ]
    self.FetchMetadata(paths, callback)


def main():
  """Creates a Metadata object, fetches the default dictionary of
  metadata values, and prints them.

  If --mock was specified on the command line, creates an http server
  for testing.
  """
  query_ip = Metadata._QUERY_IP

  # If a mock server was requested for testing, start it here.
  options.parse_command_line()
  if options.options.mock:
    from tornado import testing
    port = testing.get_unused_port()
    class Handler(web.RequestHandler):
      def get(self, path):
        self.write(path.split("/")[-1])
    application = web.Application([ (r"/(.*)", Handler), ])
    application.listen(port)
    query_ip = "localhost:{0}".format(port)

  def _MetadataCallback(metadata):
    print metadata
    ioloop.IOLoop.current().stop()

  Metadata(callback=_MetadataCallback, query_ip=query_ip)
  ioloop.IOLoop.current().start()
  return 0


if __name__ == "__main__":
  sys.exit(main())
