# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Admin permissions table.

Stores users allowed to access the admin page. User names should be viewfinder.co user.
The set of rights determines what each user is allowed to access on viewfinder.co/admin.

  'root':   admin functions: DB, logs, counter, etc...
  'support': read-only support function. eg: lookup user id from email address.

This table only details permissions. Authentication uses per-domain secrets.
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

from viewfinder.backend.db import db_client, vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.hash_base import DBHashObject

@DBObject.map_table_attributes
class AdminPermissions(DBHashObject):
  """AdminPermissions object."""
  __slots__ = []

  # Types of rights. Any number can be set.
  ROOT = 'root'
  SUPPORT = 'support'

  _table = DBObject._schema.GetTable(vf_schema.ADMIN_PERMISSIONS)

  def __init__(self, username=None, rights=None):
    """Initialize a new permissions object."""
    super(AdminPermissions, self).__init__()
    self.username = username
    if rights is not None:
      self.SetRights(rights)

  def IsRoot(self):
    """Returns true if 'root' is in the set of rights."""
    return AdminPermissions.ROOT in self.rights

  def IsSupport(self):
    """Returns true if 'support' is in the set of rights."""
    return AdminPermissions.SUPPORT in self.rights

  def SetRights(self, rights):
    """Clear current set of rights and add the passed-in ones."""
    self.rights = set()
    for r in rights:
      assert r == self.ROOT or r == self.SUPPORT, 'unknown right: %s' % r
      self.rights.add(r)
