# -*- coding: utf-8 -*-
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for DynamoDB client.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import os
import unittest

from boto.exception import DynamoDBResponseError
from functools import partial
from tornado import options
from viewfinder.backend.base.testing import async_test_timeout
from viewfinder.backend.base import base_options  # imported for option definitions
from viewfinder.backend.base import secrets, util, counters
from viewfinder.backend.db.db_client import DBKey, UpdateAttr, RangeOperator, BatchGetRequest, DBKeySchema
from viewfinder.backend.db import dynamodb_client, vf_schema

from base_test import DBBaseTestCase

_table = vf_schema.SCHEMA.GetTable(vf_schema.TEST_RENAME)


def setupModule():
  # The existence of a setupModule method tells nose's multiprocess test runner to serialize
  # the tests in this file.
  pass

@unittest.skip("needs aws credentials")
@unittest.skipIf('NO_NETWORK' in os.environ, 'no network')
class DynamoDBClientTestCase(DBBaseTestCase):
  def setUp(self):
    """Clears all rows from the 'Test' DynamoDB table."""
    super(DynamoDBClientTestCase, self).setUp()
    options.options.domain = 'goviewfinder.com'
    secrets.InitSecretsForTest()
    self._client = dynamodb_client.DynamoDBClient(schema=vf_schema.SCHEMA)
    self._ClearTestTable(self.stop)
    self.wait(timeout=30)

  def tearDown(self):
    dynamodb_client.DynamoDBClient._MAX_BATCH_SIZE = 100
    self._ClearTestTable(self.stop)
    self.wait(timeout=30)
    super(DynamoDBClientTestCase, self).tearDown()

  @async_test_timeout(timeout=30)
  def testPutAndGet(self):
    """Put an item and verify get."""
    exp_attrs = {u'a0': 2 ** 64 + 1, u'a1': 1354137666.996147, u'a2': u'test valueà朋'}

    def _VerifyGet(barrier_cb, result):
      self.assertEqual(exp_attrs, result.attributes)
      self.assertEqual(result.read_units, 0.5)
      barrier_cb()

    def _VerifyConsistentGet(barrier_cb, result):
      self.assertEqual(exp_attrs, result.attributes)
      self.assertEqual(result.read_units, 1)
      barrier_cb()

    def _VerifyEmptyGet(barrier_cb, result):
      self.assertTrue(result is None)
      barrier_cb()

    def _OnPut(result):
      key = DBKey(u'1à朋', 1)
      attrs = [u'a0', u'a1', u'a2']
      with util.Barrier(self.stop) as b:
        self._client.GetItem(table=_table.name, key=key,
                             callback=partial(_VerifyGet, b.Callback()),
                             attributes=attrs, must_exist=False, consistent_read=False)
        self._client.GetItem(table=_table.name, key=key,
                             callback=partial(_VerifyConsistentGet, b.Callback()),
                             attributes=attrs, must_exist=False, consistent_read=True)
        self._client.GetItem(table=_table.name, key=DBKey('2', 2),
                             callback=partial(_VerifyEmptyGet, b.Callback()),
                             attributes=attrs, must_exist=False, consistent_read=False)

    self._client.PutItem(table=_table.name, key=DBKey(u'1à朋', 1), callback=_OnPut,
                         attributes={'a0': 2 ** 64 + 1, 'a1': 1354137666.996147, 'a2': 'test valueà朋'})

  @async_test_timeout(timeout=30)
  def testPutValues(self):
    """Verify operation with various attribute values."""
    def _VerifyGet(result):
      self.assertEqual({u'a1': 0, u'a2': u'str',
                        u'a3': set([0]), u'a4': set([u'strà朋'])}, result.attributes)
      self.assertEqual(result.read_units, 0.5)
      self.stop()

    def _OnPut(result):
      self._client.GetItem(table=_table.name, key=DBKey(u'1', 1),
                           callback=_VerifyGet, attributes=[u'a1', u'a2', u'a3', u'a4'])

    self._client.PutItem(table=_table.name, key=DBKey(u'1', 1), callback=_OnPut,
                         attributes={'a1': 0, 'a2': u'str', 'a3': set([0]),
                                     'a4': set(['strà朋'])})

  @async_test_timeout(timeout=30)
  def testUpdate(self):
    """Update an item multiple times, varying update actions and return_values."""
    def _OnFourthUpdate(result):
      self.assertEquals(result.write_units, 1)
      self.assertEquals(result.return_values, {u'thk': u'2', u'trk': 2,
                                               u'a1': 10, u'a2': 'update str 2',
                                               u'a3': set([1, 2, 3, 4, 5, 6])})
      self.stop()

    def _OnThirdUpdate(result):
      self.assertEquals(result.write_units, 1)
      self.assertEquals(result.return_values, {u'thk': u'2', u'trk': 2,
                                               u'a1': 10, u'a2': 'update str 2',
                                               u'a3': set([1, 2, 3, 4, 5, 6])})

      # Delete non-existent value in non-existent attribute.
      self._client.UpdateItem(table=_table.name, key=DBKey(u'2', 2), callback=_OnFourthUpdate,
                              attributes={'a4': UpdateAttr(set(['100']), 'DELETE')},
                              return_values='ALL_NEW')

    def _OnSecondUpdate(result):
      self.assertEquals(result.write_units, 1)
      self.assertEquals(result.return_values, {u'a1': 10, u'a2': 'update str 2',
                                               u'a3': set([1, 2, 3, 4, 5, 6]),
                                               u'a4': set([u'3'])})

      self._client.UpdateItem(table=_table.name, key=DBKey(u'2', 2), callback=_OnThirdUpdate,
                              attributes={'a10': UpdateAttr(None, 'DELETE'),
                                          'a4': UpdateAttr(set(['3']), 'DELETE')},
                              return_values='ALL_NEW')

    def _OnFirstUpdate(result):
      self.assertEquals(result.write_units, 1)
      self.assertEquals(result.return_values, {u'thk': u'2', u'trk': 2,
                                               u'a1': 5, u'a2': u'update str',
                                               u'a3': set([1, 2, 3]), u'a4': set([u'1', u'3', u'2'])})
      self._client.UpdateItem(table=_table.name, key=DBKey(u'2', 2), callback=_OnSecondUpdate,
                              attributes={'a1': UpdateAttr(5, 'ADD'),
                                          'a2': UpdateAttr('update str 2', 'PUT'),
                                          'a3': UpdateAttr(set([4, 5, 6]), 'ADD'),
                                          'a4': UpdateAttr(set(['1', '2', '100']), 'DELETE')},
                              return_values='UPDATED_NEW')

    self._client.UpdateItem(table=_table.name, key=DBKey(u'2', 2), callback=_OnFirstUpdate,
                            attributes={'a1': UpdateAttr(5, 'ADD'),
                                        'a2': UpdateAttr('update str', 'PUT'),
                                        'a3': UpdateAttr(set([1, 2, 3]), 'ADD'),
                                        'a4': UpdateAttr(set(['1', '2', '3']), 'PUT')},
                            return_values='ALL_NEW')

  @async_test_timeout(timeout=30)
  def testUpdateNoAttributes(self):
    """Update an item with no attributes set, other than the key.  This should result in a false-positive
    from dynamodb that the record was updated, even though the record is not actually created.
    """
    def _VerifyGet(result):
      self.assertFalse(result == True)
      self.stop()

    def _OnUpdate(result):
      self.assertEquals(result.write_units, 1)
      self._client.GetItem(table=_table.name, key=DBKey(u'2', 2), attributes=[u'a1', u'a2'],
                           must_exist=False, callback=_VerifyGet)

    self._client.UpdateItem(table=_table.name, key=DBKey(u'2', 2), callback=_OnUpdate,
                            attributes={})

  @async_test_timeout(timeout=30)
  def testUpdateWithDelete(self):
    """Update an item by deleting its attributes."""
    def _OnDeleteUpdate(result):
      self.assertEquals(result.write_units, 1)
      self.assertEquals(result.return_values, {u'a0': 1, u'thk': u'2', u'trk': 2})
      self.stop()

    def _OnUpdate(result):
      self.assertEquals(result.write_units, 1)
      self._client.UpdateItem(table=_table.name, key=DBKey(u'2', 2), callback=_OnDeleteUpdate,
                              attributes={'a1': UpdateAttr(None, 'DELETE'),
                                          'a2': UpdateAttr(None, 'DELETE'),
                                          'a3': UpdateAttr(None, 'DELETE'),
                                          'a4': UpdateAttr(None, 'DELETE')},
                              return_values='ALL_NEW')

    self._client.UpdateItem(table=_table.name, key=DBKey(u'2', 2), callback=_OnUpdate,
                            attributes={'a0': UpdateAttr(1, 'PUT'),
                                        'a1': UpdateAttr(5, 'PUT'),
                                        'a2': UpdateAttr('update str', 'PUT'),
                                        'a3': UpdateAttr(set([1, 2, 3]), 'PUT'),
                                        'a4': UpdateAttr(set(['1', '2', '3']), 'PUT')})

  @async_test_timeout(timeout=30)
  def testQuery(self):
    """Adds a range of values and queries with start key and limit."""
    num_items = 10

    def _OnQuery(exp_count, result):
      for i in xrange(exp_count):
        self.assertEqual(len(result.items), exp_count)
        self.assertEqual(result.items[i], {u'thk': u'test_query', u'trk': i,
                                           u'a1': i, u'a2': ('test-%d' % i)})
      self.stop()

    def _OnPutItems():
      self._client.Query(table=_table.name, hash_key='test_query',
                         range_operator=RangeOperator([0, 5], 'BETWEEN'),
                         callback=partial(_OnQuery, 6), attributes=['thk', 'trk', 'a1', 'a2'])

    with util.Barrier(_OnPutItems) as b:
      for i in xrange(num_items):
        self._client.PutItem(table=_table.name, key=DBKey(u'test_query', i),
                             callback=b.Callback(), attributes={'a1': i, 'a2': ('test-%d' % i)})

  def _ClearTestTable(self, callback):
    """Clears the contents of the 'Test' table by scanning the rows and deleting
    items by composite key.
    """
    def _OnScan(result):
      with util.Barrier(callback) as b:
        for item in result.items:
          self._client.DeleteItem(table=_table.name, key=DBKey(item['thk'], item['trk']),
                                  callback=b.Callback())

    self._client.Scan(table=_table.name, callback=_OnScan, attributes=['thk', 'trk'])

  @async_test_timeout(timeout=30)
  def testBadRequest(self):
    """Verify exceptions are propagated on a bad request."""
    def _OnPut(result):
      assert False, 'Put should fail'

    def _OnError(type, value, callback):
      self.assertEqual(type, DynamoDBResponseError)
      self.stop()

    with util.Barrier(_OnPut, _OnError) as b:
      # Put an item with a blank string, which is disallowed by DynamoDB.
      self._client.PutItem(table=_table.name, key=DBKey(u'1', 1), attributes={'a2': ''},
                           callback=b.Callback())

  @async_test_timeout(timeout=30)
  def testExceptionPropagationInStackContext(self):
    """Verify exceptions propagated from the DynamoDB client are raised in
    the stack context of the caller.
    """
    entered = [False, False]

    def _OnPut1():
      assert False, 'Put1 should fail'

    def _OnError1(type, value, tb):
      #logging.info('in Put1 error handler')
      if entered[0]:
        print 'in error1 again!'
      assert not entered[0], 'already entered error 1'
      entered[0] = True
      if all(entered):
        self.stop()

    def _OnPut2():
      assert False, 'Put2 should fail'

    def _OnError2(type, value, tb):
      #logging.info('in Put2 error handler')
      assert not entered[1], 'already entered error 2'
      entered[1] = True
      if all(entered):
        self.stop()

    # Pause all processing to allow two put operations to queue and for the
    # latter's error handler to become the de-facto stack context.
    self._client._scheduler._Pause()

    with util.Barrier(_OnPut1, _OnError1) as b1:
      # Put an item with a blank string, which is disallowed by DynamoDB.
      self._client.PutItem(table=_table.name, key=DBKey(u'1', 1), attributes={'a2': ''},
                           callback=b1.Callback())

    with util.Barrier(_OnPut2, _OnError2) as b2:
      # Put a valid item; this should replace the previous stack context.
      self._client.PutItem(table=_table.name, key=DBKey(u'2', 1), attributes={'a2': ''},
                           callback=b2.Callback())

    # Resume the request scheduler queue processing.
    self._client._scheduler._Resume()

  @async_test_timeout(timeout=30)
  def testPerformanceCounters(self):
    """Verify that performance counters are working correctly for DynamoDB."""
    meter = counters.Meter(counters.counters.viewfinder.dynamodb)
    def _PutComplete():
      self.stop()

    self._client._scheduler._Pause()
    with util.Barrier(_PutComplete) as b:
      self._client.PutItem(table=_table.name, key=DBKey(u'1', 1),
                           attributes={'a1': 100, 'a2': 'test value'}, callback=b.Callback())
      self._client.PutItem(table=_table.name, key=DBKey(u'2', 1),
                           attributes={'a1': 200, 'a2': 'test value'}, callback=b.Callback())

    sample = meter.sample()
    self.assertEqual(2, sample.viewfinder.dynamodb.requests_queued)

    self._client._scheduler._Resume()
    sample = meter.sample()
    self.assertEqual(0, sample.viewfinder.dynamodb.requests_queued)

  @async_test_timeout(timeout=30)
  def testBatchGetItem(self):
    """Put items and verify getting them in a batch."""
    attrs = {'a0': 123.456, 'a2': 'test value', 'a4': set(['foo', 'bar'])}
    attrs2 = {'a0': 1, 'a1':-12345678901234567890, 'a3': set([1, 2, 3])}

    with util.Barrier(self.stop) as b:
      self._client.PutItem(table=_table.name, key=DBKey(u'1', 1), attributes=attrs, callback=b.Callback())
      self._client.PutItem(table=_table.name, key=DBKey('test_key', 2), attributes=attrs2, callback=b.Callback())
    self.wait()

    batch_dict = {_table.name: BatchGetRequest(keys=[DBKey('1', 1),
                                                     DBKey('unknown', 0),
                                                     DBKey('test_key', 2),
                                                     DBKey('test_key', 2)],
                                               attributes=['thk', 'trk', 'a0', 'a1', 'a2', 'a3', 'a4'],
                                               consistent_read=True)}

    # Simple batch call.
    response = self._RunAsync(self._client.BatchGetItem, batch_dict, must_exist=False)
    self.assertEqual(len(response.keys()), 1)
    response = response[_table.name]

    attrs.update({'thk': '1', 'trk': 1})
    attrs2.update({'thk': 'test_key', 'trk': 2})

    self.assertEqual(response.read_units, 3.0)
    self.assertEqual(response.items[0], attrs)
    self.assertIsNone(response.items[1])
    self.assertEqual(response.items[2], attrs2)
    self.assertEqual(response.items[3], attrs2)

    # Multiple calls to DynamoDB (force small max batch size).
    dynamodb_client.DynamoDBClient._MAX_BATCH_SIZE = 2
    response = self._RunAsync(self._client.BatchGetItem, batch_dict, must_exist=False)
    response = response[_table.name]
    dynamodb_client.DynamoDBClient._MAX_BATCH_SIZE = 100

    self.assertEqual(response.read_units, 3.0)
    self.assertEqual(response.items[0], attrs)
    self.assertIsNone(response.items[1])
    self.assertEqual(response.items[2], attrs2)
    self.assertEqual(response.items[3], attrs2)

    # ERROR: must_exist == True.
    self.assertRaises(AssertionError, self._RunAsync, self._client.BatchGetItem, batch_dict)

    # Trigger unprocessed keys by querying for many keys at once.
    batch_dict = {_table.name: BatchGetRequest(keys=[],
                                               attributes=['thk', 'trk'],
                                               consistent_read=True)}
    for i in xrange(25):
      batch_dict[_table.name].keys.append(DBKey('unknown %d' % i, 1))

    response = self._RunAsync(self._client.BatchGetItem, batch_dict, must_exist=False)
    response = response[_table.name]
    self.assertEqual(len(response.items), 25)
    [self.assertIsNone(item) for item in response.items]

    # ERROR: Only support keys from single table currently.
    batch_dict = {'foo': BatchGetRequest(keys=[], attributes=[], consistent_read=False),
                  'bar': BatchGetRequest(keys=[], attributes=[], consistent_read=False)}
    self.assertRaises(AssertionError, self._RunAsync, self._client.BatchGetItem, batch_dict)

    self.stop()


@unittest.skip("needs aws credentials")
@unittest.skipIf('NO_NETWORK' in os.environ, 'no network')
class DynamoDBReadOnlyClientTestCase(DBBaseTestCase):
  def setUp(self):
    """Creates a read-only local client.
    Manually flips the _read_only variable to populate the table, then flips it back.
    """
    super(DynamoDBReadOnlyClientTestCase, self).setUp()
    options.options.domain = 'goviewfinder.com'
    secrets.InitSecretsForTest()
    self._client = dynamodb_client.DynamoDBClient(schema=vf_schema.SCHEMA, read_only=True)

    self._client._read_only = False
    self._RunAsync(self._ClearTestTable)
    self._RunAsync(self._client.PutItem, table=_table.name, key=DBKey(hash_key='1', range_key=2), attributes={'a1': 1})
    self._client._read_only = True


  def tearDown(self):
    dynamodb_client.DynamoDBClient._MAX_BATCH_SIZE = 100
    self._client._read_only = False
    self._RunAsync(self._ClearTestTable)
    super(DynamoDBReadOnlyClientTestCase, self).tearDown()


  def _ClearTestTable(self, callback):
    """Clears the contents of the 'Test' table by scanning the rows and deleting
    items by composite key.
    """
    def _OnScan(result):
      with util.Barrier(callback) as b:
        for item in result.items:
          self._client.DeleteItem(table=_table.name, key=DBKey(item['thk'], item['trk']),
                                  callback=b.Callback())

    self._client.Scan(table=_table.name, callback=_OnScan, attributes=['thk', 'trk'])

  def testMethods(self):
    # Read-only methods:
    # We don't try ListTables as this would require giving user/test access on all tables.
    # self._RunAsync(self._client.ListTables)
    self._RunAsync(self._client.DescribeTable, _table.name)
    self._RunAsync(self._client.GetItem, table=_table.name,
                      key=DBKey('1', 2), attributes=['a1'])
    batch_dict = {_table.name: BatchGetRequest(keys=[DBKey('1', 2)], attributes=['thk', 'trk', 'a1'],
                  consistent_read=True)}
    self._RunAsync(self._client.BatchGetItem, batch_dict)
    self._RunAsync(self._client.Query, table=_table.name, hash_key='1', range_operator=None, attributes=None)
    self._RunAsync(self._client.Scan, table=_table.name, attributes=None)

    # Mutating methods:
    # We may not have permission to issue some of those requests against the test dynamodb table, but we'll raise
    # the 'read-only' exception first.
    _hash_key_schema = DBKeySchema(name='test_hk', value_type='N')
    _range_key_schema = DBKeySchema(name='test_rk', value_type='N')
    self.assertRaisesRegexp(AssertionError, 'request on read-only database', self._RunAsync,
                            self._client.CreateTable, _table.name, _hash_key_schema, _range_key_schema, 5, 10)

    self.assertRaisesRegexp(AssertionError, 'request on read-only database', self._RunAsync,
                            self._client.DeleteTable, table=_table.name)

    self.assertRaisesRegexp(AssertionError, 'request on read-only database', self._RunAsync,
                            self._client.PutItem, table=_table.name, key=DBKey(hash_key=1, range_key=2),
                            attributes={'num': 1})

    self.assertRaisesRegexp(AssertionError, 'request on read-only database', self._RunAsync,
                            self._client.DeleteItem, table=_table.name, key=DBKey(hash_key=1, range_key=2))

    self.assertRaisesRegexp(AssertionError, 'request on read-only database', self._RunAsync,
                            self._client.UpdateItem, table=_table.name, key=DBKey(hash_key=1, range_key=2),
                            attributes={'num': 1})
