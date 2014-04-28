# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Contains functions for validating and versioning messages.

Messages (described below) need to be validated in order to ensure
they conform to a particular JSON schema. Also, this module provides
support for allowing and generating multiple versions of the same
message.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)'
               'andy@emailscrubbed.com (Andy Kimball)']

import re
import sys
import time
import validictory

from functools import partial

# The client uses the Unicode separator char class, but the Python re module does not support
# that, so just approximate.
FULL_NAME_RE = re.compile('\s*(\S+)\s*(.*)\s*', re.UNICODE)


class BadMessageException(Exception):
  """Raised when an invalid message is encountered."""
  pass


class Message(object):
  """A message is represented as a Python dictionary that is typically created
  from JSON text and is destined to be serialized to a network or to a
  database as JSON text. The dictionary may contain nested dictionaries or
  arrays that form the message structure. Messages may be validated,
  "sanitized", and migrated from a newer format to an older format (or vice-
  versa).
  """

  INITIAL_VERSION = 0
  """Version of the starting message format. This format does not contain a
  headers object or a version field in that object. Therefore, if a message
  is encountered without the headers object, it is assumed to have this
  version.
  """

  ADD_HEADERS_VERSION = 1
  """Add headers object to every message and version field."""

  TEST_VERSION = 2
  """Version used for testing migrators."""

  RENAME_EVENT_VERSION = 3
  """Rename fields from "event" to "episode"."""

  ADD_TO_VIEWPOINT_VERSION = 4
  """Episodes have new "viewpoint_id" and "publish_timestamp" fields that
  older clients will not understand.
  """

  QUERY_EPISODES_VERSION = 5
  """QueryEpisodes now takes additional selection fields, and by default
  photos are not selected.
  """

  UPDATE_POST_VERSION = 6
  """QueryEpisodes no longer returns a post_timestamp field."""

  UPDATE_SHARE_VERSION = 7
  """The share operation adds support for viewpoints."""

  ADD_OP_HEADER_VERSION = 8
  """Add op_id and op_timestamp to the headers of mutating operation
  requests.
  """

  ADD_ACTIVITY_VERSION = 9
  """Add activity attribute to requests that require it."""

  EXTRACT_MD5_HASHES = 10
  """Extract MD5 hashes from client_data to standalone attributes."""

  INLINE_INVALIDATIONS = 11
  """Inline certain invalidations in notification messages."""

  EXTRACT_FILE_SIZES = 12
  """Extract file sizes from client_data to standalone attributes."""

  INLINE_COMMENTS = 13
  """Inline shorter comments in notifications."""

  EXTRACT_ASSET_KEYS = 14
  """Extract asset keys from client_data to standalone attributes."""

  SPLIT_NAMES = 15
  """Split full names into given and family name parts."""

  EXPLICIT_SHARE_ORDER = 16
  """Client explicitly orders episodes and photos in share_new and share_existing."""

  SUPPRESS_BLANK_COVER_PHOTO = 17
  """Remove cover_photo field if photo_id is blank (work around client bug)."""

  SUPPORT_MULTIPLE_IDENTITIES_PER_CONTACT = 18
  """Different results format for query_contacts related to support for upload_contacts."""

  RENAME_PHOTO_LABEL = 19
  """Rename query_episodes photo label from HIDDEN back to REMOVED."""

  SUPPRESS_AUTH_NAME = 20
  """Removes name fields from /link/viewfinder."""

  SEND_EMAIL_TOKEN = 21
  """Include 4-digit access token in email rather than a button."""

  SUPPORT_REMOVED_FOLLOWERS = 22
  """Return labels for each follower returned by query_viewpoints."""

  SUPPRESS_COPY_TIMESTAMP = 23
  """Removes timestamp field from episodes in share and save operations."""

  SUPPORT_CONTACT_LIMITS = 24
  """Truncates and skips various items during upload contacts in order to stay under limits."""

  SUPPRESS_EMPTY_TITLE = 25
  """Removes empty title field from update_viewpoint request."""

  # -----------------------------------------------------------------
  # Add new message versions here, making sure to update MAX_VERSION.
  # Define an instance of the new migrator near the bottom of the
  # file, and if it's a migrator that must always be run, then add
  # it to REQUIRED_MIGRATORS. Any time you want to change messages,
  # consider the following possible usages:
  #   1. Messages to and from our service API.
  #   2. Messages used by operation.py to persist operations.
  #   3. Messages used by USER_UPDATES to store column names.
  #   4. Messages used by notification.py for invalidations as
  #      well as notification arguments.
  # -----------------------------------------------------------------

  MAX_VERSION = SUPPRESS_EMPTY_TITLE
  """This should always be set to the maximum message version."""


  _VERSION_HEADER_SCHEMA = {
    'description': 'defines message with optional headers object',
    'type': 'object',
    'properties': {
      'headers': {
        'description': 'defines headers object with required version field',
        'type': 'object',
        'properties': {
          'version': {
            'description': 'version of the message format',
            'type': 'integer',
            'minimum': ADD_HEADERS_VERSION,
            },
          'min_required_version': {
              'description': 'minimum required message format version that must be supported by the server',
              'type': 'integer',
              'required': False,
              'minimum': INITIAL_VERSION,
            },
          },
        },
      },
    }
  """Define validation schema so that header fields in the version object
  are validated "enough" so that we can pick out the version without
  worrying about getting exceptions that something doesn't exist, or is
  the wrong data-type, etc. Other header fields are ignored at this stage;
  it's just a private schema not meant to be used outside this class.
  """

  def __init__(self, message_dict, min_supported_version=INITIAL_VERSION,
               max_supported_version=MAX_VERSION, default_version=INITIAL_VERSION):
    """Construct a new message from the provided Python dictionary. Determine
    the version of the message and store it in the version field. A number of
    checks are made to make sure that the version is valid. The first
    requirement is that the message version falls within the range (inclusive)
    [min_supported_version, max_supported_version] that was passed to this
    method. However, the version of the message itself can be somewhat
    flexible. The message specifies a "version" field, but it can also specify
    a "min_required_version" field. This gives the server the latitude to
    pick a version in the range [min_required_version, version]. The server
    will find the overlap between these two ranges and pick the largest
    version value possible that still falls within both ranges. If the ranges
    are disjoint, then a BadMessageException will be raised.

    If no version is present in the message, assume it is "default_version".
    This allows messages to be easily constructed using literal dictionaries,
    without needing to always insert a version header.
    """
    assert type(message_dict) is dict, (type(message_dict), message_dict)
    self.dict = message_dict

    assert min_supported_version >= MIN_SUPPORTED_MESSAGE_VERSION
    assert max_supported_version <= MAX_MESSAGE_VERSION

    self.original_version = self._GetMessageVersion(max_supported_version, default_version)
    self.version = self.original_version

    # Verify that the message's version should be accepted.
    if self.version > max_supported_version:
      raise BadMessageException('Version %d of this message is not supported by the server.' % self.version +
                                ' The server only supports this message up to version %d.' %
                                max_supported_version)

    if self.version < min_supported_version:
      raise BadMessageException('Version %d of this message is not supported by the server.' % self.version +
                                ' The server only supports this message starting at version %d.' %
                                min_supported_version)


  def Validate(self, schema, allow_extra_fields=False):
    """Validate that the message conforms to the specified schema.
    If the "allow_extra_fields" argument is False, then fail the
    validation if the message contains any extra fields that are
    not specified explicitly in the schema. If validation fails,
    then raise a BadMessageException. If the validation succeeds,
    associate the schema with this message by saving it in the
    "self.schema" field.
    """
    assert schema, "A schema must be provided in order to validate."
    try:
      validictory.validate(self.dict, schema)
      if not allow_extra_fields:
        self._FindExtraFields(self.dict, schema, True)
      self.schema = schema
    except Exception as e:
      raise BadMessageException(e.message), None, sys.exc_info()[2]

  def Sanitize(self):
    """Remove any fields from the message that are not explicitly
    allowed by the schema. This is used to remove extraneous fields
    from objects which may have been added during message processing.
    """
    assert self.schema, "No schema available. Sanitize may only be called after Validate has been called."
    self._FindExtraFields(self.dict, self.schema, False)

  def Migrate(self, client, migrate_version, callback, migrators=None):
    """Migrate this message's content to the format with version
    "migrate_version". To do this, apply the "migrators" list in
    sequence. Each migrator will mutate the content of the message to
    conform to the next (or previous) version of the message format.
    If migrators == None, the REQUIRED_MIGRATORS will be used by
    default. The migrators list should already be merged with
    REQUIRED_MIGRATORS and sorted. Example:

      migrators = sorted(REQUIRED_MIGRATORS + [MyMigrator(), MyOtherMigrator()])

    When the migration is completed, "callback" is invoked with the
    message as its only parameter.
    """
    def _OnMigrate(intermediate_version):
      """Called each time a migrator has been applied; keep invoking Migrate
      until the final migrate version is reached.
      """
      self.version = intermediate_version

      # Update the version header to be the target version.
      if intermediate_version >= Message.ADD_HEADERS_VERSION:
        self.dict['headers']['version'] = intermediate_version

      # Continue migrating.
      self.Migrate(client, migrate_version, callback, migrators)

    assert migrate_version >= MIN_SUPPORTED_MESSAGE_VERSION
    assert migrate_version <= MAX_MESSAGE_VERSION

    if migrators is None:
      migrators = REQUIRED_MIGRATORS
    assert len(migrators) > 0 and type(migrators[0]) is AddHeadersMigrator, \
           'The first migrator is not AddHeadersMigrator. Did you forget to merge with REQUIRED_MIGRATORS and sort?'

    # If current message version is the same as the desired version, nothing more to do.
    if self.version == migrate_version:
      callback(self)
      return

    # Migrate the message version to the target version.
    migrator_count = len(migrators)
    if self.version < migrate_version:
      for i in xrange(migrator_count):
        migrator = migrators[i]
        assert i == 0 or migrators[i - 1].migrate_version < migrator.migrate_version

        # Break if we reach a migrator that is above the desired version.
        if migrator.migrate_version > migrate_version:
          break

        if self.version < migrator.migrate_version:
          migrator.MigrateForward(client, self, partial(_OnMigrate, migrator.migrate_version))
          return
    else:
      for i in xrange(migrator_count, 0, -1):
        migrator = migrators[i - 1]
        assert i == migrator_count or migrators[i].migrate_version > migrator.migrate_version

        # Break if we reach migrators that are below the desired version.
        if migrator.migrate_version <= migrate_version:
          break

        if self.version >= migrator.migrate_version:
          migrator.MigrateBackward(client, self, partial(_OnMigrate, migrator.migrate_version - 1))
          return

    # No migrators apply, so skip directly to target version.
    _OnMigrate(migrate_version)

  def Visit(self, visitor):
    """Recursively visit the fields of the message in a depth-first
    order. Invoke the visitor for each field, passing the name of
    the field and its value. If the handler returns None, then no
    changes are made to the message. If the handler returns an
    empty tuple (), then the field is removed from the message. If
    the handler returns a (name, value) tuple, then the field is
    replaced with the new name and value.
    """
    self._VisitHelper(self.dict, visitor)

  def _VisitHelper(self, node, handler):
    """Helper visitor that traverses the message tree."""
    if isinstance(node, dict):
      for key, value in node.items():
        # Recursively visit the dictionary contents.
        self._VisitHelper(value, handler)

        # Give handler a chance to modify the (key, value) pair.
        result = handler(key, value)
        if result is None:
          # None, so do nothing to this field.
          continue

        # Remove the field
        del node[key]

        # Add new field if one was returned.
        if len(result) == 2:
          node[result[0]] = result[1]
    elif isinstance(node, list):
      # Recursively visit list contents.
      for item in node:
        self._VisitHelper(item, handler)

  def _FindExtraFields(self, message_dict, schema, raise_error):
    """Recursively traverses the message, looking for extra fields that
    are not explicitly allowed in the schema. If "raise_error" is True,
    then raise a BadMessageException if such fields are found. Otherwise,
    remove the fields from the message entirely.
    """
    if schema['type'] == 'object':
      assert isinstance(message_dict, dict)
      for k in message_dict.keys():
        if 'properties' in schema:
          if k not in schema['properties']:
            if raise_error:
              raise BadMessageException('Message contains field "%s", which is not present in the schema.' % k)
            else:
              del message_dict[k]
            continue
          if schema['properties'][k]['type'] in ('object', 'array'):
            self._FindExtraFields(message_dict[k], schema['properties'][k], raise_error)
    elif schema['type'] == 'array':
      assert isinstance(message_dict, list)
      for val in message_dict:
        self._FindExtraFields(val, schema['items'], raise_error)

  def _GetMessageVersion(self, max_supported_version, default_version):
    """Extract the version from the message headers. Usually this is just
    the value of the "version" field. However, if that version is not
    supported by the server, the value of the "min_required_version"
    field is consulted. If the value of this field is less than or equal
    to the max supported version, then the server can "fall back" to
    its max supported version.
    """
    # If no version is present in the message, add it if allowed to do so.
    headers = self.dict.get('headers', None)
    if headers is None:
      if default_version == Message.INITIAL_VERSION:
        return Message.INITIAL_VERSION
      self.dict['headers'] = dict(version=default_version)
    elif not headers.has_key('version'):
      headers['version'] = default_version

    # Validate version header.
    try:
      validictory.validate(self.dict, Message._VERSION_HEADER_SCHEMA)
    except Exception as e:
      raise BadMessageException(e.message)

    # Calculate version based on "version" and "min_required_version" fields.
    version = int(self.dict['headers']['version'])

    if self.dict['headers'].has_key('min_required_version'):
      min_required_version = int(self.dict['headers']['min_required_version'])
      if min_required_version > version:
        raise BadMessageException('The "min_required_version" value (%d) ' % min_required_version +
                                  'cannot be greater than the "version" value (%d).' % version)

      # If version is not supported, then use highest supported version that is still >=
      # the min_required_version.
      if version > max_supported_version:
        version = max(min_required_version, max_supported_version)

    return version


class MessageMigrator(object):
  """Migrates a message's content to conform to the next (or previous)
  version of the message format. This is useful because from time to time,
  the format of a particular message changes. The server must accept and
  generate the new format. However, for reasons of backwards-compatibility,
  older message formats must also be accepted and generated by the server.
  Migrators enable support for multiple message formats by forming a
  pipeline of transform functions which are successively applied in order
  to migrate a message from an older format to a newer format, or vice-
  versa.

  As a message format changes, it should always maintain enough information
  so that it can be migrated backwards to the minimum supported message
  format. However, in the backwards-migration case, it is permissible to
  lose information that was present in later formats (but was not
  supported by earlier formats).
  """
  def __init__(self, migrate_version):
    """Construct a migrator that will be activated as a message's version
    is migrated to or from "migrate_version".
    """
    self.migrate_version = migrate_version

  def MigrateForward(self, client, message, callback):
    """Called in order to migrate a message to the "migrate_version" format,
    from the previous format version. "callback" is invoked with no parameters
    when the migration is complete.
    """
    raise NotImplementedError()

  def MigrateBackward(self, client, message, callback):
    """Called in order to migrate a message from the "migrate_version"
    format, to the previous format version. "callback" is invoked with no
    parameters when the migration is complete.
    """
    raise NotImplementedError()

  def __cmp__(self, other):
    """Migrators are compared to one another by "migrate_version", which
    imposes a total ordering of migrators.
    """
    assert isinstance(other, MessageMigrator)
    return cmp(self.migrate_version, other.migrate_version)


class AddHeadersMigrator(MessageMigrator):
  """Migrator that adds a headers object to the message. The headers object
  contains a single required "version" field.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.ADD_HEADERS_VERSION)

  def MigrateForward(self, client, message, callback):
    """Add the headers object to the message."""
    message.dict['headers'] = dict(version=Message.ADD_HEADERS_VERSION)
    callback()

  def MigrateBackward(self, client, message, callback):
    """Remove the headers object from the message."""
    del message.dict['headers']
    callback()


class RenameEventMigrator(MessageMigrator):
  """Migrator that renames all "event" fields in the message to
  corresponding "episode" fields.
  """
  _EVENT_FIELDS = ['event', 'events', 'event_id', 'event_ids', 'parent_event_id', 'original_event_id',
                   'device_event_id', 'event_limit', 'event_start_key', 'last_event_key']
  _EPISODE_TO_EVENT = {field.replace('event', 'episode') : field for field in _EVENT_FIELDS}
  _EVENT_TO_EPISODE = {field : field.replace('event', 'episode') for field in _EVENT_FIELDS}

  def __init__(self):
    MessageMigrator.__init__(self, Message.RENAME_EVENT_VERSION)

  def MigrateForward(self, client, message, callback):
    """Visit all fields in the message and replace event fields with episode fields."""
    def _ReplaceEventWithEpisode(key, value):
      if RenameEventMigrator._EPISODE_TO_EVENT.has_key(key):
        raise BadMessageException('Episode fields should not appear in older messages.')
      episode = RenameEventMigrator._EVENT_TO_EPISODE.get(key, None)
      return (episode, value) if episode else None

    message.Visit(_ReplaceEventWithEpisode)
    callback()

  def MigrateBackward(self, client, message, callback):
    """Visit all fields in the message and replace episode fields with event fields."""
    def _ReplaceEpisodeWithEvent(key, value):
      if RenameEventMigrator._EVENT_TO_EPISODE.has_key(key):
        raise BadMessageException('Event fields should not appear in newer messages.')
      event = RenameEventMigrator._EPISODE_TO_EVENT.get(key, None)
      return (event, value) if event else None

    message.Visit(_ReplaceEpisodeWithEvent)
    callback()


class AddToViewpointMigrator(MessageMigrator):
  """Migrator that removes new "viewpoint_id" and "publish_timestamp"
  Episode attributes from responses to older clients. These attributes
  were added to episode as part of removing the Published table. Since
  it's only necessary to remove these attributes, there's no need to
  implement MigrateForward.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.ADD_TO_VIEWPOINT_VERSION)

  def MigrateBackward(self, client, message, callback):
    if 'episodes' in message.dict:
      for ep in message.dict['episodes']:
        del ep['viewpoint_id']
        del ep['publish_timestamp']
    callback()


class QueryEpisodesMigrator(MessageMigrator):
  """Migrator that always sets the QueryEpisodes "get_photos" field
  to True, since older clients expect the photos to be projected by
  default. Since it's only necessary to do this on the incoming
  request, there's no need to implement MigrateBackward.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.QUERY_EPISODES_VERSION)

  def MigrateForward(self, client, message, callback):
    if 'episodes' in message.dict:
      for ep in message.dict['episodes']:
        ep['get_photos'] = True
    callback()


class UpdatePostMigrator(MessageMigrator):
  """Migrator that adds back the "post_timestamp" field to the
  QueryEpisodes response message (so no need to implement MigrateForward).
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.UPDATE_POST_VERSION)

  def MigrateBackward(self, client, message, callback):
    if 'episodes' in message.dict:
      for ep in message.dict['episodes']:
        if 'photos' in ep:
          for ph in ep['photos']:
            ph['post_timestamp'] = ph['timestamp']
    callback()


class UpdateShareMigrator(MessageMigrator):
  """Migrator that adds support for viewpoints to the "share" operation,
  as well as sharing photos from multiple episodes.

  NOTE: This migrator is now a no-op, because the new viewpoint support
  was removed from the "share" operation, and instead put into "share_new"
  and "share_existing" operations.
  """
  pass


class AddOpHeaderMigrator(MessageMigrator):
  """Migrator that adds op_id and op_timestamp headers to mutating operation
  requests. The op_id is generated using the system device allocator so that
  it's guaranteed to be globally unique.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.ADD_OP_HEADER_VERSION)

  def MigrateForward(self, client, message, callback):
    from viewfinder.backend.db.operation import Operation

    def _OnAllocateId(id):
      message.dict['headers']['op_id'] = id
      message.dict['headers']['op_timestamp'] = time.time()
      callback()

    Operation.AllocateSystemOperationId(client, _OnAllocateId)


class AddActivityMigrator(MessageMigrator):
  """Migrator that adds activity attribute to operation requests which need
  to create an activity. The activity_id is derived from the op_timestamp
  and op_id headers.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.ADD_ACTIVITY_VERSION)

  def MigrateForward(self, client, message, callback):
    from viewfinder.backend.db.activity import Activity
    from viewfinder.backend.db.operation import Operation

    timestamp = message.dict['headers']['op_timestamp']
    activity_id = Activity.ConstructActivityIdFromOperationId(timestamp, message.dict['headers']['op_id'])
    message.dict['activity'] = {'activity_id': activity_id,
                                'timestamp': timestamp}
    callback()


class ExtractMD5Hashes(MessageMigrator):
  """Migrator that extracts thumbnail and medium MD5 hashes from the
  "client_data" field of photo metadata and puts them into standalone
  attributes.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.EXTRACT_MD5_HASHES)

  def MigrateForward(self, client, message, callback):
    from viewfinder.backend.db.photo import Photo

    for ph_dict in message.dict['photos']:
      if 'tn_md5' not in ph_dict:
        client_data = ph_dict['client_data']
        ph_dict['tn_md5'] = client_data['tn_md5']
        ph_dict['med_md5'] = client_data['med_md5']

    callback()


class InlineInvalidations(MessageMigrator):
  """Migrator that removes the new "inline" attribute in the
  query_notifications response for older clients. The activity
  attribute moves to the top-level of the notification, and the
  "update_seq" attribute is moved to the "activity" section from
  the "viewpoint" section.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.INLINE_INVALIDATIONS)

  def MigrateBackward(self, client, message, callback):
    from viewfinder.backend.db.photo import Photo

    for notify_dict in message.dict['notifications']:
      inline_dict = notify_dict.pop('inline', None)
      if inline_dict is not None and 'activity' in inline_dict:
        notify_dict['activity'] = inline_dict['activity']

    callback()


class ExtractFileSizes(MessageMigrator):
  """Migrator that extracts file (tn/med/full/orig) sizes from the
  "client_data" field of photo metadata and puts them into standalone attributes.
  Some really old clients do not have said sizes in client_data, we skip those.
  We assume that if tn_size is specified, so are the others. This is currently true.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.EXTRACT_FILE_SIZES)

  def MigrateForward(self, client, message, callback):
    from viewfinder.backend.db.photo import Photo

    for ph_dict in message.dict['photos']:
      if 'client_data' not in ph_dict:
        continue
      if 'tn_size' not in ph_dict:
        client_data = ph_dict['client_data']
        if 'tn_size' in client_data:
          ph_dict['tn_size'] = int(client_data.get('tn_size', 0))
          ph_dict['med_size'] = int(client_data.get('med_size', 0))
          ph_dict['full_size'] = int(client_data.get('full_size', 0))
          ph_dict['orig_size'] = int(client_data.get('orig_size', 0))

    callback()


class InlineComments(MessageMigrator):
  """Migrator that removes inlined comments from the query_notifications response for older
  clients. A comment invalidation is instead created for older clients.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.INLINE_COMMENTS)

  def MigrateBackward(self, client, message, callback):
    from viewfinder.backend.db.comment import Comment

    for notify_dict in message.dict['notifications']:
      if 'inline' in notify_dict and 'comment' in notify_dict['inline']:
        comment_dict = notify_dict['inline'].pop('comment')
        start_key = Comment.ConstructCommentId(comment_dict['timestamp'], 0, 0)
        notify_dict['invalidate'] = {'viewpoints': [{'viewpoint_id': comment_dict['viewpoint_id'],
                                                     'get_comments': True,
                                                     'comment_start_key': start_key}]}

    callback()


class ExtractAssetKeys(MessageMigrator):
  """Migrator that extracts asset keys from the 'client_data' field of photo metadata
  and puts them into standalone attributes.  This is the last use of client_data, so
  the field is removed by this migration.

  Unlike the other client_data extractor migrations, the client uses the asset key field
  so this migration must be applied in both directions.

  This migration also changes asset keys from a single value to a list.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.EXTRACT_ASSET_KEYS)

  def _FindPhotos(self, message):
    # QUERY_EPISODES_RESPONSE
    for episode in message.dict.get('episodes', []):
      for photo in episode.get('photos', []):
        yield photo

    # UPDATE_PHOTO_REQUEST
    yield message.dict

    # UPLOAD_EPISODE_REQUEST
    for photo in message.dict.get('photos', []):
      yield photo

  def MigrateForward(self, client, message, callback):
    for photo in self._FindPhotos(message):
      client_data = photo.pop('client_data', {})
      if 'asset_key' in client_data:
        photo['asset_keys'] = [client_data.pop('asset_key')]
    callback()

  def MigrateBackward(self, client, message, callback):
    for photo in self._FindPhotos(message):
      asset_keys = photo.pop('asset_keys', None)
      if asset_keys:
        photo.setdefault('client_data', {})['asset_key'] = asset_keys[0]
    callback()


class SplitNames(MessageMigrator):
  """Migrator that splits full names passed to VF auth and update_user methods. Full names
  are split into given and family name parts.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.SPLIT_NAMES)

  def MigrateForward(self, client, message, callback):
    # Handle VF auth case and update_user case here.
    update_dict = message.dict.get('auth_info', message.dict)

    # Only do split if name exists but given_name and family_name do not.
    if update_dict and 'name' in update_dict and 'given_name' not in update_dict and 'family_name' not in update_dict:
      match = FULL_NAME_RE.match(update_dict['name'])
      if match is not None:
        update_dict['given_name'] = match.group(1)
        if match.group(2):
          update_dict['family_name'] = match.group(2)

    callback()


class ExplictShareOrder(MessageMigrator):
  """Migrator that orders episodes and photos in share requests according to the original
  mobile client algorithm for selecting cover photos:
  1) Within share request, oldest to newest episode.
  2) Within episode, newest to oldest photo.
  Messages at this version level are expected to be ordered based on the client's intended order for
  cover photo selection.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.EXPLICIT_SHARE_ORDER)

  def MigrateForward(self, client, message, callback):
    # Sort incoming episodes oldest to newest based on episode_id.
    # Episode_ids naturally sort from newest to oldest, so reverse this sort.
    message.dict['episodes'].sort(key=lambda episode: episode['new_episode_id'], reverse=True)
    # Sort photos from newest to oldest (photo_ids sort this way naturally)
    for ep_dict in message.dict['episodes']:
      ep_dict['photo_ids'].sort()

    callback()


class SuppressBlankCoverPhoto(MessageMigrator):
  """Migrator that works around a client bug, in which the client sends a cover photo record
  in a share_new request that has a blank photo_id.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.SUPPRESS_BLANK_COVER_PHOTO)

  def MigrateForward(self, client, message, callback):
    vp_dict = message.dict.get('viewpoint', None)
    if vp_dict is not None:
      cover_photo_dict = vp_dict.get('cover_photo', None)
      if cover_photo_dict is not None:
        photo_id = cover_photo_dict.get('photo_id', None)
        if not photo_id:
          # Remove the entire cover_photo attribute.
          del message.dict['viewpoint']['cover_photo']

    callback()


class SupportMultipleIdentitiesPerContact(MessageMigrator):
  """Migrator that transforms new format for query_contacts response for downlevel clients."""
  def __init__(self):
    MessageMigrator.__init__(self, Message.SUPPORT_MULTIPLE_IDENTITIES_PER_CONTACT)

  def MigrateBackward(self, client, message, callback):
    """Migration steps:
    * add 'contact_user_id' if first identities entry has user_id property.
    * add 'identity' from first identities entry.
    * remove 'identities'
    * remove 'contact_source'
    * remove 'contact_id'
    * remove 'labels' if present.
    * remove any contacts that have only phone numbers.
    * remove any contacts that don't have any identities.
    """
    from viewfinder.backend.db.contact import Contact
    contacts_list = []
    for contact in message.dict['contacts']:
      if 'labels' in contact and Contact.REMOVED in contact['labels']:
        continue
      if len(contact['identities']) == 0:
        continue
      first_identity_properties = contact['identities'][0]
      if (not first_identity_properties['identity'].startswith('Email:') and
          not first_identity_properties['identity'].startswith('FacebookGraph:')):
        # Some contacts may have just phone numbers.  If there are any email addresses
        #   or FacebookGraph ids, at least one of them will be the first in the list.
        continue
      if 'user_id' in first_identity_properties:
        contact['contact_user_id'] = first_identity_properties['user_id']
      contact['identity'] = first_identity_properties['identity']
      contact.pop('identities')
      contact.pop('contact_source')
      contact.pop('contact_id')
      assert 'labels' not in contact, 'Migrator should be updated to support labels if present.'
      contact.pop('labels', None)
      # Add to list because it hasn't been removed.
      contacts_list.append(contact)

    # Set new list of contacts which doesn't have 'removed' contacts because we don't want to show
    #   them to down-level clients.  They'll assume they're not present.
    message.dict['contacts'] = contacts_list
    message.dict['num_contacts'] = len(contacts_list)

    callback()


class RenamePhotoLabel(MessageMigrator):
  """Migrator that renames the query_episodes photo label from HIDDEN to REMOVED for older
  clients.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.RENAME_PHOTO_LABEL)

  def MigrateBackward(self, client, message, callback):
    from viewfinder.backend.db.user_post import UserPost

    for ep_dict in message.dict['episodes']:
      if 'photos' in ep_dict:
        for ph_dict in ep_dict['photos']:
          if 'labels' in ph_dict:
            labels = set(ph_dict['labels'])
            if UserPost.HIDDEN in labels:
              labels.remove(UserPost.HIDDEN)
              labels.add('removed')
              ph_dict['labels'] = list(labels)

    callback()


class SuppressAuthName(MessageMigrator):
  """Migrator that works around a client bug, in which the client sends a user name to
  /link/viewfinder.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.SUPPRESS_AUTH_NAME)

  def MigrateForward(self, client, message, callback):
    auth_info_dict = message.dict.get('auth_info', None)
    if auth_info_dict is not None:
      auth_info_dict.pop('name', None)
      auth_info_dict.pop('given_name', None)
      auth_info_dict.pop('family_name', None)
    callback()


class SupportRemovedFollowers(MessageMigrator):
  """Migrator that extracts and projects only the follower ids from the follower list in a
  query_viewpoints response. Later versions of the server return an additional "labels" field
  for each follower.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.SUPPORT_REMOVED_FOLLOWERS)

  def MigrateBackward(self, client, message, callback):
    for vp_dict in message.dict['viewpoints']:
      if 'followers' in vp_dict:
        vp_dict['followers'] = [foll_dict['follower_id'] for foll_dict in vp_dict['followers']]
    callback()


class SuppressCopyTimestamp(MessageMigrator):
  """Migrator that removes the episode timestamp on incoming share and save operations."""
  def __init__(self):
    MessageMigrator.__init__(self, Message.SUPPRESS_COPY_TIMESTAMP)

  def MigrateForward(self, client, message, callback):
    for ep_dict in message.dict.get('episodes', []):
      ep_dict.pop('timestamp', None)
    callback()


class SupportContactLimits(MessageMigrator):
  """Migrator that truncates and skips various items during upload contacts in order to stay
  under limits.
  """
  def __init__(self):
    MessageMigrator.__init__(self, Message.SUPPORT_CONTACT_LIMITS)

  def MigrateForward(self, client, message, callback):
    def _TruncateField(dict, name, limit):
      # BUG(Andy): In production, limit is in Unicode UCS-4 chars (Python wide build). Some of
      # our dev machines are using a Python narrow build, which means this will be UTF-16
      # codepoints. To fix this, we need to configure all dev machines to use a narrow build.
      if len(dict.get(name, '')) > limit:
        dict[name] = dict[name][:limit]

    for contact_dict in message.dict.get('contacts', []):
      _TruncateField(contact_dict, 'name', 1000)
      _TruncateField(contact_dict, 'given_name', 1000)
      _TruncateField(contact_dict, 'family_name', 1000)

      _TruncateField(contact_dict, 'identities', 50)
      for ident_dict in contact_dict.get('identities', []):
        _TruncateField(ident_dict, 'identity', 1000)
        _TruncateField(ident_dict, 'description', 1000)

    callback()


class SuppressEmptyTitle(MessageMigrator):
  """Migrator that removes the viewpoint title from incoming update_viewpoint operations."""
  def __init__(self):
    MessageMigrator.__init__(self, Message.SUPPRESS_EMPTY_TITLE)

  def MigrateForward(self, client, message, callback):
    if not message.dict.get('title', None):
      message.dict.pop('title', None)
    callback()


REQUIRED_MIGRATORS = [AddHeadersMigrator()]
"""Define list of migrators that *every* message needs to include in
its migration list. The required list can easily be merged with a
message-specific list using a statement like:

  sorted(REQUIRED_MIGRATORS + [MY_MIGRATOR])
"""

# -----------------------------------------------------------------
# Define an instance of each optional migrator so that they can be
# easily included in migration lists.
# -----------------------------------------------------------------
RENAME_EVENT = RenameEventMigrator()
ADD_TO_VIEWPOINT = AddToViewpointMigrator()
QUERY_EPISODES = QueryEpisodesMigrator()
UPDATE_POST = UpdatePostMigrator()
ADD_OP_HEADER = AddOpHeaderMigrator()
ADD_ACTIVITY = AddActivityMigrator()
EXTRACT_MD5_HASHES = ExtractMD5Hashes()
INLINE_INVALIDATIONS = InlineInvalidations()
EXTRACT_FILE_SIZES = ExtractFileSizes()
INLINE_COMMENTS = InlineComments()
EXTRACT_ASSET_KEYS = ExtractAssetKeys()
SPLIT_NAMES = SplitNames()
EXPLICIT_SHARE_ORDER = ExplictShareOrder()
SUPPRESS_BLANK_COVER_PHOTO = SuppressBlankCoverPhoto()
SUPPORT_MULTIPLE_IDENTITIES_PER_CONTACT = SupportMultipleIdentitiesPerContact()
RENAME_PHOTO_LABEL = RenamePhotoLabel()
SUPPRESS_AUTH_NAME = SuppressAuthName()
SUPPORT_REMOVED_FOLLOWERS = SupportRemovedFollowers()
SUPPRESS_COPY_TIMESTAMP = SuppressCopyTimestamp()
SUPPORT_CONTACT_LIMITS = SupportContactLimits()
SUPPRESS_EMPTY_TITLE = SuppressEmptyTitle()


MAX_MESSAGE_VERSION = Message.MAX_VERSION
"""Maximum message version that the server *understands*. However, just
because the server understands this version doesn't mean it will accept
messages from the client that have this version, nor generate messages of
this format when storing into the operations table. See
"SUPPORTED_MESSAGE_VERSION" for more details. When messages having older
formats arrive from the client or are read from the operations table,
they are migrated to this max version so that internal server code only
has to deal with one format.
"""

MAX_SUPPORTED_MESSAGE_VERSION = Message.SUPPRESS_EMPTY_TITLE
"""Maximum message version that the server *fully supports*. The
supported message version is also guaranteed to be fully rolled out and
supported by *all* other servers. The server will accept messages from
the client that do not exceed this version. In addition, the server will
always generate operation table messages using this format, as it can be
confident that other servers will be able to process this version. Doing
this avoids problems like these:

  - New server stores new operation message. Older server tries to pick
    up the operation message in order to run it.

  - New version is rolled out to production. New operation message is saved
    in the operations table. New version has problems, and so is rolled
    back. Restored server running old version tries to pick up the
    operation message in order to run it.
"""

MIN_SUPPORTED_MESSAGE_VERSION = Message.INITIAL_VERSION
"""Minimum message version that the server understands. If it receives a
message with a version that is less than this version, it will return an
error. This version will be increased as we drop support for older message
formats.
"""
