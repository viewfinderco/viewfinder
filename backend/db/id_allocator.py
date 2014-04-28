# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""ID allocation from a monotonically increasing sequence.

An instance of IdAllocator is created by specifying the id-allocation key.
This is typically a table name (e.g. 'users'), though can be
any arbitrary key. Each instance maintains a block of sequential IDs. The
size of the block can be controlled at instantiation but defaults to
IdAllocator._DEFAULT_ALLOCATION.

Allocation of IDs starts at _START_ID (default is 1).

  IdAllocator: keeps track of a block of IDs, mapped from id_allocator table
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import struct
import zlib

from collections import deque
from functools import partial

from viewfinder.backend.base import util
from viewfinder.backend.db import db_client, vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.hash_base import DBHashObject


@DBObject.map_table_attributes
class IdAllocator(DBHashObject):
  """Viewfinder ID allocator."""
  __slots__ = ['_allocation', '_next_id_key', '_cur_id', '_last_id',
               '_allocation_pending', '_waiters']

  _START_ID = 1
  _DEFAULT_ALLOCATION = 7

  _table = DBObject._schema.GetTable(vf_schema.ID_ALLOCATOR)
  _instances = list()

  def __init__(self, id_type=None, allocation=None):
    """Allocates a block of 'allocation' IDs from the 'id_allocator'
    table.

    Specify allocation as a prime number to make it less likely that
    two allocating servers are handing out numbers with synchronized
    mod offsets. This shouldn't in practice be an issue as the hash
    prefix we compute is constructed via a crc32--synchronized mod
    offsets shouldn't be a problem here.
    """
    super(IdAllocator, self).__init__()
    self.id_type = id_type
    self._allocation = allocation or IdAllocator._DEFAULT_ALLOCATION
    self._next_id_key = self._table.GetColumn('next_id').key
    self._cur_id = IdAllocator._START_ID
    self._last_id = IdAllocator._START_ID
    self._allocation_pending = False
    self._waiters = deque()
    # Add to the global instance list so we can reset from unittest setup.
    IdAllocator._instances.append(self)

  def Reset(self):
    assert len(self._waiters) == 0, self._waiters
    assert not self._allocation_pending
    self._cur_id = IdAllocator._START_ID
    self._last_id = IdAllocator._START_ID
    self._allocation_pending = False

  def NextId(self, client, callback):
    """Executes callback with the value of _cur_id++. If _cur_id is None or
    _cur_id == _last_id, allocates a new block from the 'id_allocator' table.
    """
    if self._allocation_pending:
      self._waiters.append(partial(self._AllocateId, callback))
    elif self._cur_id == self._last_id:
      self._waiters.append(partial(self._AllocateId, callback))
      self._AllocateIds(client)
    else:
      self._AllocateId(callback)

  def _AllocateId(self, callback, type=None, value=None, traceback=None):
    """Invokes callback with a new id from the sequence; if type, value or
    traceback are not None, raises an exception.
    """
    if (type, value, traceback) != (None, None, None):
      raise type, value, traceback
    assert self._cur_id < self._last_id
    new_id = self._cur_id
    self._cur_id += 1
    callback(new_id)

  def _ProcessWaiters(self):
    """Iterates over list of waiters, returning new ids from the
    allocation stream. Returns true if all waiters were processed;
    false otherwise.
    """
    while len(self._waiters) and self._cur_id < self._last_id:
      self._waiters.popleft()()
    return len(self._waiters) == 0

  def _AllocateIds(self, client):
    """Allocates the next batch of IDs. On success, processes all
    pending waiters. If there are more waiters than ids, re-allocates.
    Otherwise, resets _allocation_pending.
    """
    assert self._cur_id == self._last_id, (self._cur_id, self._last_id)

    def _OnAllocate(result):
      self._last_id = result.return_values[self._next_id_key]
      if self._last_id <= IdAllocator._START_ID:
        self._cur_id = self._last_id
        return self._AllocateIds(client)
      self._cur_id = max(IdAllocator._START_ID, self._last_id - self._allocation)
      assert self._cur_id < self._last_id, 'cur id %d >= allocated last id %d' % \
          (self._cur_id, self._last_id)
      logging.debug("allocated %d %s IDs (%d-%d)" %
                    (self._allocation, self.id_type, self._cur_id, self._last_id))
      if not self._ProcessWaiters():
        self._AllocateIds(client)
      else:
        self._allocation_pending = False

    def _OnError(type, value, traceback):
      logging.error('failed to allocate new id; returning waiters...', exc_info=(type, value, traceback))
      while len(self._waiters):
        self._waiters.popleft()(type, value, traceback)

    self._allocation_pending = True
    with util.MonoBarrier(_OnAllocate, on_exception=_OnError) as b:
      client.UpdateItem(table=self._table.name, key=self.GetKey(),
                        attributes={self._next_id_key:
                                    db_client.UpdateAttr(value=self._allocation, action='ADD')},
                        return_values='UPDATED_NEW', callback=b.Callback())

  @staticmethod
  def ComputeHashPrefix(id, num_bytes=1):
    """Returns a hash prefix from 64-bit id with the specified number
    of bytes. The hash prefix for an ID is typically used to achieve
    uniform distribution of keys across shards. The high bytes of the
    crc32 checksum are used first.
    """
    assert num_bytes - 1 in xrange(4), num_bytes
    return zlib.crc32(struct.pack('>Q', id)) & [0xff, 0xffff, 0xffffff, 0xffffffff][num_bytes - 1]

  @classmethod
  def ResetState(cls):
    """Resets the internal state of all ID allocators; for testing."""
    for id_alloc in IdAllocator._instances:
      id_alloc.Reset()

