# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test object for the TEST_RENAME database testing table.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.range_base import DBRangeObject

@DBObject.map_table_attributes
class TestRename(DBRangeObject):
  """Used for testing."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.TEST_RENAME)
