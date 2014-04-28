# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test message validation and migration.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

from copy import deepcopy
from tornado.ioloop import IOLoop
from viewfinder.backend.base import testing
from viewfinder.backend.base.message import Message, MessageMigrator, BadMessageException, REQUIRED_MIGRATORS

class RenameTestMigrator(MessageMigrator):
  """Rename a field in the message."""
  def __init__(self):
    MessageMigrator.__init__(self, Message.TEST_VERSION)

  def MigrateForward(self, client, message, callback):
    assert message.dict['headers']
    message.dict['renamed-scalar'] = message.dict['scalar']
    del message.dict['scalar']
    callback()

  def MigrateBackward(self, client, message, callback):
    assert message.dict['headers']
    message.dict['scalar'] = message.dict['renamed-scalar']
    del message.dict['renamed-scalar']
    IOLoop.current().add_callback(callback)


class MessageTestCase(testing.BaseTestCase):
  SCHEMA_NO_VERSION = {
    'description': 'test schema',
    'type': 'object',
    'properties': {
      'scalar': {'type': 'string', 'blank': True},
      'list': {
        'type': 'array',
        'items': {'type': 'any'},
        },
      'sub-dict': {
        'description': 'nested dictionary',
        'required': False,
        'type': 'object',
        'properties': {
          'none': {'type': 'null'},
          'sub-scalar': {'type': 'string'},
          'sub-list': {
            'type': 'array',
            'items': {
              'description': 'dictionary in list',
              'type': 'object',
              'properties': {
                'value': {'type': 'number'}
                },
              },
            },
          },
        },
      },
    }

  SCHEMA_WITH_VERSION = deepcopy(SCHEMA_NO_VERSION)
  SCHEMA_WITH_VERSION['properties']['headers'] = {
    'description': 'defines required version field',
    'required': False,
    'type': 'object',
    'properties': {
      'version': {'type': 'number', 'minimum': Message.ADD_HEADERS_VERSION},
      },
    }

  RENAMED_SCHEMA_WITH_VERSION = deepcopy(SCHEMA_WITH_VERSION)
  del RENAMED_SCHEMA_WITH_VERSION['properties']['scalar']
  RENAMED_SCHEMA_WITH_VERSION['properties']['renamed-scalar'] = {'type': 'string'}

  MSG_NO_VERSION = {
    'scalar': 'Simple scalar field',
    'list': [10, 'list item', []],
    'sub-dict': {
      'none': None,
      'sub-scalar': 'Simple scalar field within sub-dict',
      'sub-list': [{'value': 20, 'extra': 'extra field that does not appear in schema'}],
      'extra': 'extra field that does not appear in schema',
      },
    'extra': 'extra field that does not appear in schema',
    }

  MSG_WITH_VERSION = deepcopy(MSG_NO_VERSION)
  MSG_WITH_VERSION['headers'] = dict(version=Message.ADD_HEADERS_VERSION)

  def testMessage(self):
    """Basic tests of the Message class."""
    # Message with no version, no schema.
    self._TestMessage(MessageTestCase.MSG_NO_VERSION, original_version=Message.INITIAL_VERSION)

    # Message with version, no schema.
    self._TestMessage(MessageTestCase.MSG_WITH_VERSION, original_version=Message.ADD_HEADERS_VERSION)

    # Default version.
    self._TestMessage(MessageTestCase.MSG_NO_VERSION, default_version=Message.ADD_HEADERS_VERSION,
                      original_version=Message.ADD_HEADERS_VERSION)
    message_dict = deepcopy(MessageTestCase.MSG_NO_VERSION)
    message_dict['headers'] = {}
    self._TestMessage(message_dict, default_version=Message.ADD_HEADERS_VERSION,
                      original_version=Message.ADD_HEADERS_VERSION)

    # ERROR: Message version not present.
    message_dict = deepcopy(MessageTestCase.MSG_WITH_VERSION)
    del message_dict['headers']['version']
    self.assertRaises(BadMessageException, self._TestMessage, message_dict)

    # ERROR: Message version was present, but anachronistic (i.e. try to use headers in version
    # that didn't support them).
    message_dict = deepcopy(MessageTestCase.MSG_WITH_VERSION)
    message_dict['headers']['version'] = Message.INITIAL_VERSION
    self.assertRaises(BadMessageException, self._TestMessage, message_dict)

    # ERROR: Message version not high enough to be supported.
    message_dict = deepcopy(MessageTestCase.MSG_WITH_VERSION)
    message_dict['headers']['version'] = -1
    self.assertRaises(BadMessageException, self._TestMessage, message_dict)

    self.assertRaises(BadMessageException, self._TestMessage, MessageTestCase.MSG_WITH_VERSION,
                      min_supported_version=Message.TEST_VERSION)

    # ERROR: Message version not low enough to be supported.
    message_dict = deepcopy(MessageTestCase.MSG_WITH_VERSION)
    message_dict['headers']['version'] = Message.ADD_HEADERS_VERSION
    self.assertRaises(BadMessageException, self._TestMessage, message_dict,
                      max_supported_version=Message.INITIAL_VERSION)

    # Min required version specified in the message.
    message_dict = deepcopy(MessageTestCase.MSG_WITH_VERSION)
    message_dict['headers']['version'] = 1000
    message_dict['headers']['min_required_version'] = Message.ADD_HEADERS_VERSION
    self._TestMessage(message_dict, original_version=Message.MAX_VERSION)

    message_dict['headers']['version'] = Message.ADD_HEADERS_VERSION
    self._TestMessage(message_dict, original_version=Message.ADD_HEADERS_VERSION)

    # ERROR: Min required version specified in the message, but greater than max supported version.
    message_dict['headers']['version'] = 3
    message_dict['headers']['min_required_version'] = Message.TEST_VERSION
    self.assertRaises(BadMessageException, self._TestMessage, message_dict,
                      max_supported_version=Message.ADD_HEADERS_VERSION)

    # ERROR: Min required version specified in the message, but less than min required message version.
    message_dict['headers']['version'] = Message.TEST_VERSION
    message_dict['headers']['min_required_version'] = Message.ADD_HEADERS_VERSION
    self.assertRaises(BadMessageException, self._TestMessage, message_dict,
                      min_supported_version=1000,
                      max_supported_version=Message.ADD_HEADERS_VERSION)

    # ERROR: Min required version specified in the message, but greater than version.
    message_dict = deepcopy(MessageTestCase.MSG_WITH_VERSION)
    message_dict['headers']['min_required_version'] = 100
    self.assertRaises(BadMessageException, self._TestMessage, message_dict)

    # Message with sanitize + schema.
    self._TestMessage(MessageTestCase.MSG_NO_VERSION, original_version=Message.INITIAL_VERSION,
                      schema=MessageTestCase.SCHEMA_NO_VERSION, sanitize=True)

    # Message with allow_extra_fields=True.
    self._TestMessage(MessageTestCase.MSG_NO_VERSION, original_version=Message.INITIAL_VERSION,
                      schema=MessageTestCase.SCHEMA_NO_VERSION, allow_extra_fields=True)

    # ERROR: Message violates schema due to extra fields.
    self.assertRaises(BadMessageException, self._TestMessage, MessageTestCase.MSG_NO_VERSION,
                      original_version=Message.INITIAL_VERSION, schema=MessageTestCase.SCHEMA_NO_VERSION)

    # Visit message.
    def _TestVisitor(key, value):
      """Remove extra fields, replace "list" field."""
      if key == 'extra':
        return ()
      elif key == 'list':
        return ('new-field', 'new value')

    message = Message(deepcopy(MessageTestCase.MSG_NO_VERSION))
    message.Visit(_TestVisitor)
    message.Visit(self._TestExtraField)
    self.assertTrue(message.dict.has_key('scalar'))
    self.assertTrue(message.dict.has_key('new-field'))
    self.assertFalse(message.dict.has_key('list'))

  def testMigrate(self):
    """Test version migration functionality on the Message class."""
    # Migrate message with no header to have a header.
    message = self._TestMessage(MessageTestCase.MSG_NO_VERSION,
                                original_version=Message.INITIAL_VERSION,
                                max_supported_version=Message.INITIAL_VERSION,
                                schema=MessageTestCase.SCHEMA_WITH_VERSION,
                                allow_extra_fields=True,
                                migrate_version=Message.ADD_HEADERS_VERSION)

    # Migrate message with header to have no header.
    message = self._TestMessage(message.dict,
                                sanitize=True,
                                schema=MessageTestCase.SCHEMA_NO_VERSION,
                                original_version=Message.ADD_HEADERS_VERSION,
                                migrate_version=Message.INITIAL_VERSION)

    # Add a migrator to the list of migrators and migrate from initial version.
    message = self._TestMessage(MessageTestCase.MSG_NO_VERSION,
                                original_version=Message.INITIAL_VERSION,
                                sanitize=True,
                                schema=MessageTestCase.RENAMED_SCHEMA_WITH_VERSION,
                                migrate_version=Message.TEST_VERSION,
                                migrators=[RenameTestMigrator()])
    renamed_dict = message.dict

    # Migrate message with renamed field all the way back to initial version.
    message = self._TestMessage(renamed_dict,
                                original_version=Message.TEST_VERSION,
                                schema=MessageTestCase.SCHEMA_NO_VERSION,
                                migrate_version=Message.INITIAL_VERSION,
                                migrators=[RenameTestMigrator()])

    # Migrate message with renamed field back to add headers version (not all the way).
    message = self._TestMessage(renamed_dict,
                                original_version=Message.TEST_VERSION,
                                schema=MessageTestCase.SCHEMA_WITH_VERSION,
                                migrate_version=Message.ADD_HEADERS_VERSION,
                                migrators=[RenameTestMigrator()])

    # Migrate message with renamed field back to initial version.
    message = self._TestMessage(message.dict,
                                original_version=Message.ADD_HEADERS_VERSION,
                                schema=MessageTestCase.SCHEMA_NO_VERSION,
                                migrate_version=Message.INITIAL_VERSION,
                                migrators=[RenameTestMigrator()])

    # No migration necessary.
    message = self._TestMessage(message.dict,
                                original_version=Message.INITIAL_VERSION,
                                schema=MessageTestCase.SCHEMA_NO_VERSION,
                                migrate_version=Message.INITIAL_VERSION,
                                migrators=[RenameTestMigrator()])

  def _TestMessage(self, message_dict, original_version=None, default_version=Message.INITIAL_VERSION,
                   min_supported_version=Message.INITIAL_VERSION, max_supported_version=Message.MAX_VERSION,
                   schema=None, allow_extra_fields=False, sanitize=False, migrate_version=None, migrators=None):
    # Create the message.
    message_dict = deepcopy(message_dict)
    message = Message(message_dict, default_version=default_version, min_supported_version=min_supported_version,
                      max_supported_version=max_supported_version)
    self.assertEqual(message.dict, message_dict)
    self.assertEqual(message.original_version, original_version)
    self.assertEqual(message.version, original_version)
    self.assertTrue(message.version == Message.INITIAL_VERSION or message.dict['headers'].has_key('version'))

    # Migrate the message to "migrate_version".
    if migrate_version is not None:
      migrators = None if migrators is None else sorted(REQUIRED_MIGRATORS + migrators)
      message.Migrate(None, migrate_version, lambda message: self.stop(message), migrators)
      self.assert_(self.wait() is message)
      self.assertEqual(message.version, migrate_version)

    # Sanitize the message if requested.
    if sanitize:
      message.Validate(schema, True)
      message.Sanitize()
      message.Visit(self._TestExtraField)

    # Validate the message according to "schema".
    if schema:
      message.Validate(schema, allow_extra_fields)
      self.assertEqual(message.schema, schema)
      if not allow_extra_fields:
        message.Visit(self._TestExtraField)

    return message

  def _TestExtraField(self, key, value):
    self.assertNotEqual(key, 'extra')
