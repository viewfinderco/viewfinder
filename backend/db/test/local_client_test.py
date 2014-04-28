# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for local emulation of DynamoDB client.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import random

from tornado import options
from viewfinder.backend.base.testing import async_test, BaseTestCase
from viewfinder.backend.db.db_client import DBKey, DBKeySchema, UpdateAttr, BatchGetRequest, RangeOperator, ScanFilter
from viewfinder.backend.db.local_client import LocalClient
from viewfinder.backend.db.schema import Schema, Table, Column, HashKeyColumn, RangeKeyColumn

_hash_key_schema = DBKeySchema(name='test_hk', value_type='N')
_range_key_schema = DBKeySchema(name='test_rk', value_type='N')

test_SCHEMA = Schema([
    Table('LocalTest', 'lt', read_units=10, write_units=5,
          columns=[HashKeyColumn('test_hk', 'test_hk', 'N'),
                   RangeKeyColumn('test_rk', 'test_rk', 'N'),
                   Column('num', 'num', 'N'),
                   Column('str', 'str', 'S'),
                   Column('num_set', 'num_set', 'NS'),
                   Column('str_set', 'str_set', 'SS')]),

    Table('LocalTest2', 'lt2', read_units=10, write_units=5,
          columns=[HashKeyColumn('test_hk', 'test_hk', 'N'),
                   Column('num', 'num', 'N'),
                   Column('str', 'str', 'S'),
                   Column('num_set', 'num_set', 'NS'),
                   Column('str_set', 'str_set', 'SS')]),

    Table('Cond', 'co', read_units=10, write_units=5,
          columns=[HashKeyColumn('test_hk', 'test_hk', 'N'),
                   Column('attr1', 'attr1', 'S')]),

    Table('Cond2', 'co2', read_units=10, write_units=5,
          columns=[HashKeyColumn('test_hk', 'test_hk', 'N'),
                   RangeKeyColumn('test_rk', 'test_rk', 'N'),
                   Column('attr1', 'attr1', 'S')]),

    Table('RangeTest', 'rt', read_units=10, write_units=5,
          columns=[HashKeyColumn('test_hk', 'test_hk', 'N'),
                   RangeKeyColumn('test_rk', 'test_rk', 'N'),
                   Column('attr1', 'attr1', 'N'),
                   Column('attr2', 'attr2', 'S')]),

    Table('Errors', 'err', read_units=10, write_units=5,
          columns=[HashKeyColumn('test_hk', 'test_hk', 'N'),
                   RangeKeyColumn('test_rk', 'test_rk', 'N'),
                   Column('attr1', 'attr1', 'S')]),
    ])


class LocalClientTestCase(BaseTestCase):
  def setUp(self):
    """Sets up _client as a test emulation of DynamoDB. Creates the full
    database schema, a test user, and two devices (one for mobile, one
    for web-application).
    """
    super(LocalClientTestCase, self).setUp()
    options.options.localdb_dir = ''
    self._client = LocalClient(test_SCHEMA)
    test_SCHEMA.VerifyOrCreate(self._client, self.stop)
    self.wait()

  @async_test
  def testTables(self):
    # Empty list tables.
    lr = self._client.ListTables(callback=None)
    self.assertTrue('NewTable1' not in lr.tables)
    # Create a table.
    cr = self._client.CreateTable('NewTable1', _hash_key_schema,
                                  _range_key_schema, 5, 10, callback=None)
    self.assertEqual(cr.schema.status, 'CREATING')
    # Create a second table.
    cr = self._client.CreateTable('NewTable2', _hash_key_schema,
                                  None, 5, 10, callback=None)
    self.assertEqual(cr.schema.status, 'CREATING')
    # List tables.
    lr = self._client.ListTables(callback=None)
    self.assertTrue('NewTable1' in lr.tables)
    self.assertTrue('NewTable2' in lr.tables)
    # Describe tables.
    for table in lr.tables:
      dr = self._client.DescribeTable(table, callback=None)
      self.assertEqual(dr.schema.status, 'ACTIVE')
    # Delete tables.
    cr1 = self._client.DeleteTable(table='NewTable1', callback=None)
    cr2 = self._client.DeleteTable(table='NewTable2', callback=None)
    self.assertEqual(cr1.schema.status, 'DELETING')
    self.assertEqual(cr2.schema.status, 'DELETING')
    # Verify tables are gone.
    lr = self._client.ListTables(callback=None)
    self.assertTrue('NewTable1' not in lr.tables)
    self.assertTrue('NewTable2' not in lr.tables)
    self.stop()

  @async_test
  def testErrors(self):
    self.assertRaises(Exception, self._client.DeleteTable,
                      table='NonExistent', callback=None)
    # Missing range key.
    self.assertRaises(Exception, self._client.PutItem, table='Errors',
                      key=DBKey(hash_key=1, range_key=None), attributes={'attr1': 1})

    # Bad hash key type.
    self.assertRaises(Exception, self._client.PutItem, table='Errors',
                      key=DBKey(hash_key='a', range_key=1), attributes={'attr1': 1})

    # Bad range key.
    self.assertRaises(Exception, self._client.PutItem, table='Errors',
                      key=DBKey(hash_key=1, range_key='a'), attributes={'attr1': 1})

    # Success
    self._client.PutItem(table='Errors', key=DBKey(hash_key=1, range_key=1),
                         attributes={'attr1': 1}, callback=None)

    # Missing hash key on get.
    self.assertRaises(Exception, self._client.GetItem, table='Errors',
                      key=DBKey(hash_key=None, range_key=1), attributes=['attr1'])

    # Missing range key on get.
    self.assertRaises(Exception, self._client.GetItem, table='Errors',
                      key=DBKey(hash_key=1, range_key=None), attributes=['attr1'])

    self.stop()

  @async_test
  def testPutAndGet(self):
    # Add some new items with attributes.
    items = {}
    for i in xrange(100):
      attrs = {'num': i * 2, 'str': 'test-%d' % i, 'num_set': set([i, (i + 1) * 2, (i + i) ** 2]),
               'str_set': set(['s%d' % i, 's%d' % (i + 1) * 2, 's%d' % (i + 1) ** 2])}
      items[i] = attrs
      result = self._client.PutItem(table='LocalTest2',
                                    key=DBKey(hash_key=i, range_key=None), attributes=attrs,
                                    return_values='ALL_OLD', callback=None)
      self.assertEqual(result.write_units, 1)
      self.assertFalse(result.return_values)

    # Get the items.
    for i in xrange(100):
      fetch_list = items[i].keys()
      random.shuffle(items[i].keys())
      fetch_list = fetch_list[0:random.randint(1, len(fetch_list))]
      result = self._client.GetItem(table='LocalTest2', key=DBKey(hash_key=i, range_key=None),
                                    attributes=fetch_list, callback=None)
      self.assertEqual(result.read_units, 1)
      self.assertEqual(len(result.attributes), len(fetch_list))
      for attr in fetch_list:
        self.assertEqual(result.attributes[attr], items[i][attr])

    # Batch get the items
    batch_dict = {'LocalTest2': BatchGetRequest(keys=[DBKey(i, None) for i in xrange(100)],
                                                attributes=['test_hk', 'num', 'str', 'num_set', 'str_set'],
                                                consistent_read=True)}
    result = self._client.BatchGetItem(batch_dict, callback=None)['LocalTest2']
    self.assertEqual(result.read_units, 100)
    self.assertEqual(len(result.items), 100)
    for i in xrange(100):
      self.assertEqual(result.items[i], items[i])

    # Delete the items.
    for i in xrange(100):
      result = self._client.DeleteItem(table='LocalTest2', key=DBKey(hash_key=i, range_key=None),
                                       callback=None)
    for i in xrange(100):
      self.assertRaises(Exception, self._client.GetItem, table='LocalTest2',
                        key=DBKey(hash_key=i, range_key=None), attributes=None, callback=None)

    self.stop()

  @async_test
  def testConditionalPutAndUpdate(self):
    # Try to put an item with an attribute which must exist.
    self.assertRaises(Exception, self._client.PutItem, table='Cond',
                      key=DBKey(hash_key=1, range_key=None), expected={'attr1': 'val'},
                      attributes={'attr1': 'new_val'})
    # Now add this item and try again.
    self._client.PutItem(table='Cond', key=DBKey(hash_key=1, range_key=None),
                         attributes={'attr1': 'new_val'}, callback=None)
    # But with wrong value.
    self.assertRaises(Exception, self._client.PutItem, table='Cond',
                      key=DBKey(hash_key=1, range_key=None), expected={'attr1': 'val'},
                      attributes={'attr1': 'new_val'})
    # Now with correct value.
    self._client.PutItem(table='Cond', key=DBKey(hash_key=1, range_key=None),
                         expected={'attr1': 'new_val'}, attributes={'attr1': 'even_newer_val'},
                         callback=None)

    # Try to put an item which already exists, but which mustn't.
    self.assertRaises(Exception, self._client.PutItem, table='Cond',
                      key=DBKey(hash_key=1, range_key=None),
                      expected={_hash_key_schema.name: False},
                      attributes={'attr1': 'new_val'}, callback=None)

    # Try with a composite key object.
    self.assertRaises(Exception, self._client.PutItem, table='Cond2',
                      key=DBKey(hash_key=1, range_key=1), expected={'attr1': 'val'},
                      attributes={'attr1': 'new_val'})
    self._client.PutItem(table='Cond2', key=DBKey(hash_key=1, range_key=1),
                         attributes={'attr1': 'new_val'}, callback=None)
    self.assertRaises(Exception, self._client.PutItem, table='Cond2',
                      key=DBKey(hash_key=1, range_key=1),
                      expected={_hash_key_schema.name: False},
                      attributes={'attr1': 'even_newer_val'}, callback=None)

    self.stop()

  @async_test
  def testUpdate(self):
    def _VerifyUpdate(updates, get_attrs, new_attrs, rv, rvs):
      update_res = self._client.UpdateItem(
        table='LocalTest2', key=DBKey(hash_key=1, range_key=None),
        callback=None, attributes=updates, return_values=rv)
      for k, v in rvs.items():
        self.assertEqual(update_res.return_values[k], v)

      get_res = self._client.GetItem(
        table='LocalTest2', key=DBKey(hash_key=1, range_key=None),
        callback=None, attributes=get_attrs)

      if get_res.attributes:
        self.assertEqual(len(get_res.attributes), len(new_attrs))
        for k, v in new_attrs.items():
          self.assertEqual(get_res.attributes[k], v)
      else:
        self.assertEqual(get_res.attributes, {})

    # Add a test item.
    attrs = {'num': 1, 'str': 'test', 'num_set': list([1, 2, 3]),
             'str_set': list(['a', 'b', 'c'])}
    self._client.PutItem(table='LocalTest2', key=DBKey(hash_key=1, range_key=None),
                         attributes=attrs, callback=None)

    # Update values, getting different return values type on each iteration.
    _VerifyUpdate({'num': UpdateAttr(value=2, action='PUT')},
                  ['num'], {'num': 2}, 'NONE', {})

    _VerifyUpdate({'num': UpdateAttr(value=2, action='ADD')},
                  ['num'], {'num': 4}, 'UPDATED_NEW', {'num': 4})

    _VerifyUpdate({'num': UpdateAttr(value=2, action='DELETE')},
                  ['num'], None, 'UPDATED_OLD', {'num': 4})

    _VerifyUpdate({'num': UpdateAttr(value= -1, action='ADD'),
                   'num_set': UpdateAttr(value=list([4, 5, 6]), action='PUT')},
                  ['num', 'num_set'], {'num':-1, 'num_set': list([4, 5, 6])},
                  'ALL_OLD', {'str': 'test', 'num_set': list([1, 2, 3]),
                              'str_set': list(['a', 'b', 'c'])})

    _VerifyUpdate({'str': UpdateAttr(value='new_test', action='PUT'),
                   'num_set': UpdateAttr(value=list([2, 3, 4]), action='ADD')},
                  ['str', 'num_set'], {'str': 'new_test', 'num_set': list([2, 3, 4, 5, 6])},
                  'ALL_NEW', {'num':-1, 'str': 'new_test', 'num_set': list([2, 3, 4, 5, 6]),
                              'str_set': list(['a', 'b', 'c'])})

    _VerifyUpdate({'str_set': UpdateAttr(value=list(['a', 'd']), action='DELETE'),
                   'num_set': UpdateAttr(value=list([3, 4, 6, 100]), action='DELETE'),
                   'unknown': UpdateAttr(value=list([100]), action='DELETE')},
                  ['str_set', 'num_set'],
                  {'str_set': list(['b', 'c']), 'num_set': list([2, 5])}, 'NONE', {})

    _VerifyUpdate({'str_set': UpdateAttr(value=None, action='DELETE'),
                   'str': UpdateAttr(value=None, action='DELETE')},
                  ['str_set', 'str'], {}, 'NONE', {})

    self.stop()

  @async_test
  def testRangeQuery(self):
    items = {}
    hash_key = 1
    for i in xrange(100):
      items[i] = {'attr1': i * 2, 'attr2': 'test-%d' % i}
      result = self._client.PutItem('RangeTest', key=DBKey(hash_key=hash_key, range_key=i),
                                    attributes=items[i], callback=None)
      self.assertEqual(result.write_units, 1)
      self.assertFalse(result.return_values)

    def _VerifyRange(r_op, limit, forward, start_key, exp_keys, exp_last_key):
      """Returns the result"""
      result = self._client.Query(table='RangeTest', hash_key=hash_key,
                                  range_operator=r_op, callback=None,
                                  attributes=['test_hk', 'test_rk', 'attr1', 'attr2'],
                                  limit=limit, scan_forward=forward,
                                  excl_start_key=(DBKey(hash_key, start_key) if start_key else None))
      self.assertEqual(len(exp_keys), result.count)
      self.assertEqual(len(exp_keys), len(result.items))
      self.assertEqual(exp_keys, [item['test_rk'] for item in result.items])
      for item in result.items:
        self.assertEqual(items[item['test_rk']]['attr1'], item['attr1'])
        self.assertEqual(items[item['test_rk']]['attr2'], item['attr2'])
      if exp_last_key is not None:
        self.assertEqual(DBKey(hash_key, exp_last_key), result.last_key)
      else:
        self.assertTrue(result.last_key is None)

    _VerifyRange(None, limit=None, forward=True, start_key=None,
                 exp_keys=range(0, 100), exp_last_key=None)

    _VerifyRange(None, limit=0, forward=True, start_key=None,
                 exp_keys=[], exp_last_key=None)

    _VerifyRange(RangeOperator(key=[25, 75], op='BETWEEN'), limit=None,
                 forward=True, start_key=None, exp_keys=range(25, 76), exp_last_key=None)

    _VerifyRange(RangeOperator(key=[25, 75], op='BETWEEN'), limit=25,
                 forward=True, start_key=None, exp_keys=range(25, 50), exp_last_key=49)

    _VerifyRange(RangeOperator(key=[25, 75], op='BETWEEN'), limit=None,
                 forward=False, start_key=None, exp_keys=range(75, 24, -1), exp_last_key=None)

    _VerifyRange(RangeOperator(key=[25, 75], op='BETWEEN'), limit=25,
                 forward=False, start_key=None, exp_keys=range(75, 50, -1), exp_last_key=51)

    _VerifyRange(RangeOperator(key=[25], op='GT'), limit=1,
                 forward=True, start_key=None, exp_keys=[26], exp_last_key=26)

    _VerifyRange(RangeOperator(key=[25], op='GT'), limit=1,
                 forward=True, start_key=26,
                 exp_keys=[27], exp_last_key=27)

    _VerifyRange(RangeOperator(key=[50], op='LT'), limit=10,
                 forward=False, start_key=48,
                 exp_keys=range(47, 37, -1), exp_last_key=38)

    _VerifyRange(RangeOperator(key=[10], op='GE'), limit=None,
                 forward=True, start_key=None,
                 exp_keys=range(10, 100), exp_last_key=None)

    _VerifyRange(None, limit=10, forward=True, start_key=None,
                 exp_keys=range(0, 10), exp_last_key=9)

    self.stop()

  @async_test
  def testRangeScan(self):
    items = {}
    for h in xrange(2):
      items[h] = {}
      for r in xrange(2):
        items[h][r] = {'attr1': (h + r * 2), 'attr2': 'test-%d' % (h + r)}
        result = self._client.PutItem('RangeTest', key=DBKey(hash_key=h, range_key=r),
                                      attributes=items[h][r], callback=None)
        self.assertEqual(result.write_units, 1)
        self.assertFalse(result.return_values)

    def _VerifyScan(limit, start_key, exp_keys, exp_last_key):
      result = self._client.Scan(table='RangeTest', callback=None,
                                 attributes=['test_hk', 'test_rk', 'attr1', 'attr2'],
                                 limit=limit, excl_start_key=start_key)
      for item in result.items:
        self.assertTrue((item['test_hk'], item['test_rk']) in exp_keys)
      if exp_last_key is not None:
        self.assertEqual(exp_last_key, result.last_key)
      else:
        self.assertTrue(result.last_key is None)

    _VerifyScan(None, None, set([(0, 0), (0, 1), (1, 0), (1, 1)]), None)

    self.stop()

  @async_test
  def testScanFilter(self):
    items = {}
    for h in xrange(2):
      items[h] = {}
      for r in xrange(2):
        items[h][r] = {'attr1': (h + r * 2), 'attr2': 'test-%d' % (h + r)}
        self._client.PutItem('RangeTest', key=DBKey(hash_key=h, range_key=r),
                             attributes=items[h][r], callback=None)

    def _VerifyScan(scan_filter, exp_keys):
      result = self._client.Scan(table='RangeTest', callback=None,
                                 attributes=['test_hk', 'test_rk', 'attr1', 'attr2'],
                                 scan_filter=scan_filter)
      for item in result.items:
        key = (item['test_hk'], item['test_rk'])
        self.assertTrue(key in exp_keys)
        exp_keys.remove(key)
      self.assertEqual(len(exp_keys), 0)

    _VerifyScan(None, set([(0, 0), (0, 1), (1, 0), (1, 1)]))
    _VerifyScan({'attr1': ScanFilter([0], 'EQ')}, set([(0, 0)]))
    _VerifyScan({'attr1': ScanFilter([0], 'GE')}, set([(0, 0), (0, 1), (1, 0), (1, 1)]))
    _VerifyScan({'attr1': ScanFilter([0], 'GT')}, set([(0, 1), (1, 0), (1, 1)]))
    # Try two conditions.
    _VerifyScan({'attr1': ScanFilter([0], 'EQ'),
                 'attr2': ScanFilter(['test-0'], 'EQ')}, set([(0, 0)]))
    _VerifyScan({'attr1': ScanFilter([0], 'EQ'),
                 'attr2': ScanFilter(['test-1'], 'EQ')}, set([]))

    self.stop()


class LocalReadOnlyClientTestCase(BaseTestCase):
  def setUp(self):
    """Creates a read-only local client.
    Manually flips the _read_only variable to populate the table, then flips it back.
    """
    super(LocalReadOnlyClientTestCase, self).setUp()
    options.options.localdb_dir = ''
    self._client = LocalClient(test_SCHEMA, read_only=True)

    self._client._read_only = False
    self._RunAsync(test_SCHEMA.VerifyOrCreate, self._client)
    self._RunAsync(self._client.PutItem, table='LocalTest', key=DBKey(hash_key=1, range_key=1), attributes={'num': 1})
    self._client._read_only = True


  def testMethods(self):
    # Read-only methods:
    self._RunAsync(self._client.ListTables)
    self._RunAsync(self._client.DescribeTable, 'LocalTest')
    self._RunAsync(self._client.GetItem, table='LocalTest',
                      key=DBKey(hash_key=1, range_key=1), attributes=['num'])
    batch_dict = {'LocalTest': BatchGetRequest(keys=[DBKey(1, 1)], attributes=['num'], consistent_read=True)}
    self._RunAsync(self._client.BatchGetItem, batch_dict)
    self._RunAsync(self._client.Query, table='LocalTest', hash_key=1, range_operator=None, attributes=None)
    self._RunAsync(self._client.Scan, table='LocalTest', attributes=None)

    # Mutating methods:
    self.assertRaisesRegexp(AssertionError, 'request on read-only database', self._RunAsync,
                            self._client.CreateTable, 'LocalTest', _hash_key_schema, _range_key_schema, 5, 10)

    self.assertRaisesRegexp(AssertionError, 'request on read-only database', self._RunAsync,
                            self._client.DeleteTable, table='LocalTest')

    self.assertRaisesRegexp(AssertionError, 'request on read-only database', self._RunAsync,
                            self._client.PutItem, table='LocalTest', key=DBKey(hash_key=1, range_key=2),
                            attributes={'num': 1})

    self.assertRaisesRegexp(AssertionError, 'request on read-only database', self._RunAsync,
                            self._client.DeleteItem, table='LocalTest', key=DBKey(hash_key=1, range_key=2))

    self.assertRaisesRegexp(AssertionError, 'request on read-only database', self._RunAsync,
                            self._client.UpdateItem, table='LocalTest', key=DBKey(hash_key=1, range_key=2),
                            attributes={'num': 1})
