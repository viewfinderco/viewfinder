# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for Versions class.
"""

__author__ = 'andy@emailscrubbed.comm (Andy Kimball)'

from tornado import options
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.test.base_test import DBBaseTestCase
from viewfinder.backend.db.test.test_rename import TestRename
from viewfinder.backend.db.versions import Version, TEST_VERSION, TEST_VERSION2
from viewfinder.backend.db.tools import upgrade


class DbVersionsTestCase(DBBaseTestCase):
  def setUp(self):
    super(DbVersionsTestCase, self).setUp()

    def _CreateTestObject(**test_dict):
      o = TestRename()
      o.UpdateFromKeywords(**test_dict)
      o.Update(self._client, self.stop)
      self.wait()

    # Create some rows for the tests.
    test_dict = {
      'test_hk': 't1',
      'test_rk': 1,
      'attr1': 1000,
      'attr2': 'hello world',
      '_version': 0
      }
    _CreateTestObject(**test_dict)

    test_dict['test_rk'] = 2
    del test_dict['attr1']
    _CreateTestObject(**test_dict)

    # Should only run one migrator.
    test_dict['test_rk'] = 3
    test_dict['_version'] = TEST_VERSION.rank
    _CreateTestObject(**test_dict)

    test_dict['test_rk'] = 4
    test_dict['attr1'] = 2000
    test_dict['_version'] = Version.GetCurrentVersion()
    _CreateTestObject(**test_dict)

  def testMaybeMigrate(self):
    """Explicit migration."""
    obj_list, _ = self._RunAsync(TestRename.Scan, self._client, col_names=None)
    for obj in obj_list:
      # Migrate object.
      self._RunAsync(Version.MaybeMigrate, self._client, obj, [TEST_VERSION, TEST_VERSION2])

    # Now, re-query and validate.
    obj_list, _ = self._RunAsync(TestRename.Scan, self._client, col_names=None)
    self._Validate(obj_list[0],obj_list[1],obj_list[2],obj_list[3])

  def testUpgradeTool(self):
    """Test the upgrade.py tool against the TestRename table."""
    options.options.migrator = 'TEST_VERSION'
    self._RunAsync(upgrade.UpgradeTable, self._client, TestRename._table)
    options.options.migrator = 'TEST_VERSION2'
    self._RunAsync(upgrade.UpgradeTable, self._client, TestRename._table)

    # Verify that the upgrades happened.
    list = self._RunAsync(TestRename.RangeQuery, self._client, 't1', range_desc=None, limit=None, col_names=None)
    self._Validate(list[0], list[1], list[2], list[3])

  @async_test
  def testNoMutation(self):
    """Test migration with mutations turned off."""
    def _OnQuery(o):
      Version.SetMutateItems(True)
      assert o.attr0 is None, o.attr0
      assert o.attr1 == 1000, o.attr1
      assert o._version == 0, o._version
      self.stop()

    def _OnUpgrade():
      TestRename.KeyQuery(self._client, DBKey(hash_key='t1', range_key=1),
                          col_names=['attr0', 'attr1'], callback=_OnQuery)

    Version.SetMutateItems(False)
    options.options.migrator = 'TEST_VERSION'
    upgrade.UpgradeTable(self._client, TestRename._table, _OnUpgrade)

  def _Validate(self, test_obj, test_obj2=None, test_obj3=None, test_obj4=None):
    assert test_obj.attr0 == 100, test_obj.attr0
    assert test_obj.attr1 is None, test_obj.attr1
    assert test_obj._version >= TEST_VERSION2.rank, test_obj._version

    if test_obj2:
      assert test_obj2.attr0 == 100, test_obj2.attr0
      assert test_obj2.attr1 is None, test_obj2.attr1
      assert test_obj2._version >= TEST_VERSION2.rank, test_obj2._version

    if test_obj3:
      assert test_obj3.attr0 is None, test_obj3.attr0
      assert test_obj3.attr1 is None, test_obj3.attr1
      assert test_obj3._version >= TEST_VERSION2.rank, test_obj3._version

    if test_obj4:
      assert test_obj4.attr0 is None, test_obj4.attr0
      assert test_obj4.attr1 == 2000, test_obj4.attr1
      assert test_obj4._version >= TEST_VERSION2.rank, test_obj4._version
