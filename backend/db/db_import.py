# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Imports all database tables and sets up a mapping from table
name to table object class.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import re
from tornado.util import import_object

# List tables here if they do not follow our naming convention.
TABLE_ALIAS_MAP = {
  'Index': None,
  'TestRename': 'viewfinder.backend.db.test.test_rename.TestRename',
}

def GetTableClass(class_name):
  if class_name in TABLE_ALIAS_MAP:
    qualified_name = TABLE_ALIAS_MAP[class_name]
  else:
    # Convert CamelCase to underscore_separated.
    package_name = re.sub(r'(.)([A-Z])', r'\1_\2', class_name).lower()
    qualified_name = 'viewfinder.backend.db.%s.%s' % (package_name, class_name)
  if qualified_name is None:
    return None
  return import_object(qualified_name)
