# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Operation Manager DBClient Wrapper

This will intercept db updates so that we can note whether or not an update happened
before an operation attempted to abort.  We don't want to abort after any updates because
it could leave whatever the operation was attempting to do in an inconsistent state.
The abort code can use one of these wrapped DBClients to determine if it should assert
instead of going ahead with the abort.

  OpMgrDBClient: Wraps DBClient during operations to detect updates.
"""

__author__ = 'mike@emailscrubbed.com (Mike Purtell)'

import traceback
from viewfinder.backend.db.db_client import DBClient
from viewfinder.backend.db.vf_schema import ID_ALLOCATOR, LOCK, OPERATION, USER


class OpMgrDBClient(DBClient):
  """Wrap DBClient to intercept update calls.
  """
  def __init__(self, dbClient):
    self._db_client = dbClient
    self._modifiedDBStack = None

  def HasDBBeenModified(self):
    return self._modifiedDBStack is not None

  def CheckDBNotModified(self):
    """Raise assert if the DB has been modified by this client since ResetDBModified() was last called."""
    assert not self.HasDBBeenModified(), \
      'Something modified the db in an operation before it should have: %s' % self.GetModifiedDBStack()

  def GetModifiedDBStack(self):
    return self._modifiedDBStack

  def _LogDBUpdate(self, table, attributes=None):
    # Called by any of DBClients methods which may results in a modification to the db.
    # Just capture the first stack.
    if self._modifiedDBStack is None:
      # 1. Locking may happen early in an operation but isn't a concern with respect to
      #    aborting an operation and leaving it partially completed.  Any locks acquired
      #    will be released even in the case of an abort.
      # 2. Operation checkpoints may happen early in an operation, but since it is not
      #    part of user data, there is no impact if the operation aborts early.
      # 3. Asset ids may be allocated early in an operation.
      if table == LOCK or table == OPERATION or table == ID_ALLOCATOR:
        return

      if table == USER and attributes and len(attributes) == 1 and 'ais' in attributes:
        return

      self._modifiedDBStack = traceback.extract_stack()

  def ResetDBModified(self):
    self._modifiedDBStack = None

  # Methods of the wrapped class being passed through below here:

  def Shutdown(self, *args, **kwargs):
    return self._db_client.Shutdown(*args, **kwargs)

  def ListTables(self, *args, **kwargs):
    return self._db_client.ListTables(*args, **kwargs)

  def CreateTable(self, *args, **kwargs):
    self._LogDBUpdate(kwargs['table'])
    return self._db_client.CreateTable(*args, **kwargs)

  def DeleteTable(self, *args, **kwargs):
    self._LogDBUpdate(kwargs['table'])
    return self._db_client.DeleteTable(*args, **kwargs)

  def DescribeTable(self, *args, **kwargs):
    return self._db_client.DescribeTable(*args, **kwargs)

  def GetItem(self, *args, **kwargs):
    return self._db_client.GetItem(*args, **kwargs)

  def BatchGetItem(self, *args, **kwargs):
    return self._db_client.BatchGetItem(*args, **kwargs)

  def PutItem(self, *args, **kwargs):
    self._LogDBUpdate(kwargs['table'], kwargs['attributes'])
    return self._db_client.PutItem(*args, **kwargs)

  def DeleteItem(self, *args, **kwargs):
    self._LogDBUpdate(kwargs['table'])
    return self._db_client.DeleteItem(*args, **kwargs)

  def UpdateItem(self, *args, **kwargs):
    self._LogDBUpdate(kwargs['table'], kwargs['attributes'])
    return self._db_client.UpdateItem(*args, **kwargs)

  def Query(self, *args, **kwargs):
    return self._db_client.Query(*args, **kwargs)

  def Scan(self, *args, **kwargs):
    return self._db_client.Scan(*args, **kwargs)

  def AddTimeout(self, *args, **kwargs):
    return self._db_client.AddTimeout(*args, **kwargs)

  def AddAbsoluteTimeout(self, *args, **kwargs):
    return self._db_client.AddAbsoluteTimeout(*args, **kwargs)

  def RemoveTimeout(self, *args, **kwargs):
    return self._db_client.RemoveTimeout(*args, **kwargs)
