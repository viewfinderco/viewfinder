# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Base TestCase class for simple, single-shard db unittests.

Provides some pre-created objects for sub-classes.

  BaseTestCase: subclass this for all datastore object test cases
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import shutil
import tempfile
import time

from tornado import options

from viewfinder.backend.base import base_options
from viewfinder.backend.base import secrets, testing, util
from viewfinder.backend.db import local_client, vf_schema
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.id_allocator import IdAllocator
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.user import User
from viewfinder.backend.op.op_manager import OpManager
from viewfinder.backend.op.operation_map import DB_OPERATION_MAP
from viewfinder.backend.storage import object_store, server_log

class DBBaseTestCase(testing.BaseTestCase):
  """Base testing class for datastore objects. This test case
  subclasses tornado's AsyncTestCase, which provides glue for
  asynchronous tests--an IOLoop object and a means of waiting for the
  completion of asynchronous events.
  """
  def setUp(self):
    """Sets up _client as a test emulation of DynamoDB. Creates the full
    database schema, a test user, and two devices (one for mobile, one
    for web-application).
    """
    options.options.localdb = True
    options.options.fileobjstore = True
    options.options.localdb_dir = ''

    super(DBBaseTestCase, self).setUp()
    options.options.localdb_dir = ''
    self._client = local_client.LocalClient(vf_schema.SCHEMA)
    object_store.InitObjectStore(temporary=True)
    self._temp_dir = tempfile.mkdtemp()
    server_log.LogBatchPersistor.SetInstance(server_log.LogBatchPersistor(backup_dir=self._temp_dir))
    IdAllocator.ResetState()

    options.options.domain = 'goviewfinder.com'
    secrets.InitSecretsForTest()

    # Set deterministic testing timestamp used in place of time.time() in server code.
    util._TEST_TIME = time.time()

    self._RunAsync(vf_schema.SCHEMA.VerifyOrCreate, self._client)
    OpManager.SetInstance(OpManager(op_map=DB_OPERATION_MAP, client=self._client, scan_ops=True))

    # Create users with linked email identity and default viewpoint.
    self._user, self._mobile_dev = self._CreateUserAndDevice(user_dict={'user_id': 1, 'name': 'Spencer Kimball'},
                                                             ident_dict={'key': 'Email:spencer.kimball@emailscrubbed.com',
                                                                         'authority': 'Google'},
                                                             device_dict={'device_id': 1, 'name': 'Spencer\'s iPhone'})

    self._user2, _ = self._CreateUserAndDevice(user_dict={'user_id': 2, 'name': 'Peter Mattis'},
                                               ident_dict={'key': 'Email:peter.mattis@emailscrubbed.com',
                                                           'authority': 'Google'},
                                               device_dict=None)

  def tearDown(self):
    """Cleanup after test is complete."""
    self._RunAsync(server_log.LogBatchPersistor.Instance().close)
    self._RunAsync(OpManager.Instance().Drain)

    shutil.rmtree(self._temp_dir)
    super(DBBaseTestCase, self).tearDown()
    self.assertIs(Operation.GetCurrent().operation_id, None)

  def UpdateDBObject(self, cls, **db_dict):
    """Update (or create if it doesn't exist) a DB object. Returns the
    object.
    """
    o = cls.CreateFromKeywords(**db_dict)
    self._RunAsync(o.Update, self._client)
    return o

  def _CreateUserAndDevice(self, user_dict, ident_dict, device_dict=None):
    """Creates a new, registered user from the fields in "user_dict". If "device_dict" is
    defined, then creates a new device from those fields.

    Returns a tuple containing the new user and device (if "device_dict" was given).
    """
    # Allocate web device id.
    webapp_dev_id = self._RunAsync(Device._allocator.NextId, self._client)

    # Create prospective user.
    user, identity = self._RunAsync(User.CreateProspective,
                                    self._client,
                                    user_dict['user_id'],
                                    webapp_dev_id,
                                    ident_dict['key'],
                                    util._TEST_TIME)

    # Register the user.
    user = self._RunAsync(User.Register,
                          self._client,
                          user_dict,
                          ident_dict,
                          util._TEST_TIME,
                          rewrite_contacts=True)

    # Register the device.
    if device_dict is not None:
      device = self._RunAsync(Device.Register, self._client, user.user_id, device_dict, is_first=True)
    else:
      device = None

    return (user, device)
