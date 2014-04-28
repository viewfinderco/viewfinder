#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder web request handler tests.

  HandlerTestCase: sets up an HTTP server-based test case with
    ViewfinderHandler-derived handlers using asynchronous decorators.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import random
import struct
import sys
import unittest

from functools import partial
from tornado import httpclient, options, web, testing
from tornado.stack_context import StackContext


from viewfinder.backend.base import handler, util
from viewfinder.backend.base.testing import async_test, BaseTestCase
from viewfinder.backend.db.local_client import LocalClient
from viewfinder.backend.db.db_client import DBClient, DBKey, DBKeySchema


class _DatastoreHandler(web.RequestHandler):
  """Handler for datastore database set/retrieval."""
  @handler.asynchronous(datastore=True)
  def get(self):
    def _OnGet(result):
      self.write('%s' % result.attributes['v'])
      self.finish()

    self._client.GetItem(table='test',
                         key=DBKey(hash_key=self.get_argument('k'), range_key=None),
                         attributes=['v'], callback=_OnGet)

  @handler.asynchronous(datastore=True)
  def post(self):
    def _OnPut(result):
      self.write('ok')
      self.finish()

    self._client.PutItem(table='test',
                         key=DBKey(hash_key=self.get_argument('k'), range_key=None),
                         attributes={'v': self.get_argument('v')}, callback=_OnPut)


class HandlerTestCase(BaseTestCase, testing.AsyncHTTPTestCase):
  """Sets up a web server which handles various backend asynchronous
  services, such as datastore db operations.
  """
  def setUp(self):
    super(HandlerTestCase, self).setUp()

    # Redefine http client to increase the maximum number of outstanding clients.
    self.http_client = httpclient.AsyncHTTPClient(
      io_loop=self.io_loop, max_clients=100, force_instance=True)
    # Setup a test table in a test datastore client instance.
    options.options.localdb_dir = ''

    DBClient.SetInstance(LocalClient(None))
    DBClient.Instance().CreateTable(
          table='test', hash_key_schema=DBKeySchema(name='k', value_type='S'),
          range_key_schema=None, read_units=10, write_units=5, callback=None)

  def get_app(self):
    """Creates a web server which handles:

     - GET  /datastore?k=<key> - retrieve value for <key>; shard is hash of key
     - POST /datastore?k=<key>&v=<value> - set datastore <key>:<value>; shard is hash of key
    """
    return web.Application([(r"/datastore", _DatastoreHandler)])

  @async_test
  def testDatastore(self):
    """Test the webserver handles datastore key/value store and retrieval
    by inserting a collection of random values and verifying their
    retrieval, in parallel.
    """
    values = self._CreateRandomValues(num_values=100)

    def _InsertDone():
      self._RetrieveValues(values, self.stop)

    self._InsertValues(values, _InsertDone)

  def _CreateRandomValues(self, num_values=100):
    """Creates num_values random integers between [0, 1<<20)
    """
    return [int(random.uniform(0, 1 << 20)) for i in xrange(num_values)]

  def _InsertValues(self, values, callback):
    """Inserts values into datastore via the tornado web server and
    invokes callback with the sequence of values when complete. The
    values are randomly distributed over the available shards.

    - The key of each value is computed as: 'k%d' % value
    """
    def _VerifyResponse(cb, resp):
      self.assertEqual(resp.body, 'ok')
      cb()

    with util.Barrier(callback) as b:
      for val in values:
        self.http_client.fetch(
          httpclient.HTTPRequest(self.get_url('/datastore'), method='POST',
                                 body='k=k%d&v=%d' % (val, val)),
          callback=partial(_VerifyResponse, b.Callback()))

  def _RetrieveValues(self, values, callback):
    """Retrieves and verifies the specified values from Datastore database
    via the tornado web server.
    """
    def _VerifyResponse(val, cb, resp):
      self.assertEqual(resp.body, repr(val))
      cb()

    with util.Barrier(callback) as b:
      for val in values:
        self.http_client.fetch(
          httpclient.HTTPRequest(self.get_url('/datastore?k=k%d' % val), method='GET'),
          callback=partial(_VerifyResponse, val, b.Callback()))

