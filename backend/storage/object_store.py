# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Interface for client access to object storage backends.

Implemented via the S3 client (s3_object_store) and the local
file equivalent (file_object_store).
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import re

from tornado import options
from viewfinder.backend.base import constants

options.define('fileobjstore', default=False, help='use local file object storage')
options.define('fileobjstore_dir', './local/objstore', help='storage location')
options.define('fileobjstore_reset', False, help='reset contents of file object store')

options.define('readonly_store', False, help='Read-only storage')


class ObjectStore(object):
  """Interface for access to object storage backends. Methods that
  require network round-trips are asynchronous; they take a callback
  argument that will be invoked if the operation completes successfully.
  If the operation fails, then an exception is raised. To handle this
  exception, use a Barrier instance with the exception handler defined.

  Amazon bucket name rules:
  - Bucket names must be at least 3 and no more than 63 characters long
  - Bucket name must be a series of one or more labels separated by a period (.), where each label:
    Must start with a lowercase letter or a number
    Must end with a lowercase letter or a number
    Can contain lowercase letters, numbers and dashes
  - Bucket names must not be formatted as an IP address (e.g., 192.168.5.4)
  WARNING: do not use '.' in bucket names as we store them in class attributes.
  """
  PHOTO = 'photo'
  PHOTO_BUCKET = 'photos-viewfinder-co'
  # Photo logs destination bucket. These are written by S3. The ObjectStore instance is marked as read-only.
  PHOTO_LOG = 'photolog'
  PHOTO_LOG_BUCKET = 'photo_logs-viewfinder-co'
  USER_LOG = 'userlog'
  USER_LOG_BUCKET = 'userlog-viewfinder-co'
  # Zips of user's viewfinder content.
  USER_ZIPS = 'user_zips'
  USER_ZIPS_BUCKET = 'user_zips-viewfinder-co'
  SERVER_LOG = 'serverlog'
  SERVER_LOG_BUCKET = 'serverlog-viewfinder-co'
  SERVER_DATA = 'serverdata'
  SERVER_DATA_BUCKET = 'serverdata-viewfinder-co'
  PUBLIC_RO = 'public-ro'
  PUBLIC_RO_BUCKET = 'public-ro-viewfinder-co'
  # S3 bucket logging for PUBLIC_RO. ObjectStore instance is marked as read-only.
  PUBLIC_RO_LOGS = 'public-ro-logs'
  PUBLIC_RO_LOGS_BUCKET = 'public-ro_logs-viewfinder-co'
  # Destination for client crashes for non-logged-in users.
  PUBLIC_CRASHES='public-crashes'
  PUBLIC_CRASHES_BUCKET='public-crashes-viewfinder-co'
  # Logs directory for public crashes. ObjectStore instance marked as read-only.
  PUBLIC_CRASHES_LOGS='public-crashes-logs'
  PUBLIC_CRASHES_LOGS_BUCKET='public-crashes_logs-viewfinder-co'
  # Repository for AWS-generated data (eg: billing dumps).
  AWS_DUMP='aws-dump'
  AWS_DUMP_BUCKET='aws-dump-viewfinder-co'

  def Put(self, key, value, callback, content_type=None, request_timeout=None):
    """Asynchronously puts the specified key/value pair, overwriting any
    existing stored data. The value must be a byte string (str) instance.
    If "content_type" is defined, then it defines the MIME type and
    charset of the content bytes. If the operation succeeds, then the
    callback will be invoked with no arguments.
    If request_timeout is not None, pass the value in seconds to the http client (S3 only).
    """
    raise NotImplementedError('must implement in subclass')

  def Get(self, key, callback, must_exist=True):
    """Asynchronously retrieves the specified key/value pair. If the
    operation succeeds, then the callback will be invoked with a single
    byte string (str) argument containing the value.
    If must_exist is False and the file is not found, the callback will be
    invoked with None.
    """
    raise NotImplementedError('must implement in subclass')

  def ListKeys(self, callback, prefix=None, marker=None, maxkeys=None):
    """Asynchronously retrieves all keys in the bucket in alphanumeric
    order, up to a limit of "maxkeys" if specified or the AWS-defined
    limit of 1000.  If "prefix" is specified, only keys which match
    the prefix are returned.  If "marker" is specified, the list will
    begin with the first key that alphanumerically follows the marker.
    If the operation succeeds, the callback will be invoked with a
    list containing the requested keys.
    """
    raise NotImplementedError('must implement in subclass')

  def ListCommonPrefixes(self, delimiter, callback, prefix=None, marker=None, maxkeys=None):
    """Asynchronously retrieve common prefixes.
    A common prefix is a string found between "prefix" (if any) and the delimiter character.
    The returned prefixes include "prefix" and the delimiter. Delimiter cannot be None.
    Each "common prefix" will count as one against max_keys.

    The return value is (prefixes, keys) where keys is all the keys starting with prefix but no occurence
    of delimiter.

    Example:
      We have the following files in a S3 bucket:
        somedir/file1
        somedir/file2
        somedir/full/foo
        somedir/full/bar
        somedir/error/bar
        somedir/error/baz
      We issue the request:
        ListCommonPrefixes(prefix='somedir/', delimiter='/')
      The return will be:
        (['somedir/full/', 'somedir/error/'], ['somedir/file1', 'somedir/file2'])
    """
    raise NotImplementedError('must implement in subclass')


  def Delete(self, key, callback):
    """Asynchronously deletes the specified key. If the operation succeeds,
    then the callback is invoked with no arguments.
    """
    raise NotImplementedError('must implement in subclass')

  def GenerateUrl(self, key, method='GET', cache_control=None, expires_in=constants.SECONDS_PER_DAY,
                  content_type=None):
    """Generates a URL that can be used retrieve the specified key. If 'cache_control' is
    given, it will result in a Cache-Control header being added to any S3 responses. The
    expires_in parameter specifies how long (in seconds) the URL is valid for.
    content-type forces the content-type of the downloaded file. eg: use text/plain for logs.
    """
    raise NotImplementedError('must implement in subclass')

  def GenerateUploadUrl(self, key, content_type=None, content_md5=None,
                        expires_in=constants.SECONDS_PER_DAY, max_bytes=5 << 20):
    """Generates a URL for a PUT request to allow a client to store
    the specified key directly.
    """
    raise NotImplementedError('must implement in subclass')

  @staticmethod
  def GetInstance(name):
    assert hasattr(ObjectStore, ObjectStore._InstanceName(name)), \
        '%s instance not initialized' % name
    return getattr(ObjectStore, ObjectStore._InstanceName(name))

  @staticmethod
  def SetInstance(name, instance):
    """Sets a new instance for testing."""
    setattr(ObjectStore, ObjectStore._InstanceName(name), instance)

  @staticmethod
  def HasInstance(name):
    """Returns true if instance 'name' exists."""
    return hasattr(ObjectStore, ObjectStore._InstanceName(name))

  @staticmethod
  def _InstanceName(name):
    return '_%s_instance' % name

  @staticmethod
  def ListInstances():
    """Return the list of instances."""
    ret = []
    for attr_name in ObjectStore.__dict__.keys():
      parsed = re.match(r'_([-a-z0-9]+)_instance$', attr_name)
      if not parsed:
        continue
      ret.append(parsed.groups()[0])
    return ret

def InitObjectStore(temporary=False):
  """Sets up object stores using either local, file-based object stores
  if --fileobjstore is specified, or S3-based object stores otherwise.
  """
  if options.options.fileobjstore:
    from file_object_store import FileObjectStore
    cls = FileObjectStore
  else:
    from s3_object_store import S3ObjectStore
    cls = S3ObjectStore

  # Constructor options so we can't override it after startup.
  ro = options.options.readonly_store
  ObjectStore.SetInstance(ObjectStore.SERVER_LOG,
                          cls(ObjectStore.SERVER_LOG_BUCKET, temporary=temporary, read_only=ro))
  ObjectStore.SetInstance(ObjectStore.USER_LOG,
                          cls(ObjectStore.USER_LOG_BUCKET, temporary=temporary, read_only=ro))
  ObjectStore.SetInstance(ObjectStore.USER_ZIPS,
                          cls(ObjectStore.USER_ZIPS_BUCKET, temporary=temporary, read_only=ro))
  ObjectStore.SetInstance(ObjectStore.PHOTO,
                          cls(ObjectStore.PHOTO_BUCKET, temporary=temporary, read_only=ro))
  ObjectStore.SetInstance(ObjectStore.PHOTO_LOG,
                          cls(ObjectStore.PHOTO_LOG_BUCKET, temporary=temporary, read_only=True))
  ObjectStore.SetInstance(ObjectStore.SERVER_DATA,
                          cls(ObjectStore.SERVER_DATA_BUCKET, temporary=temporary, read_only=ro))
  ObjectStore.SetInstance(ObjectStore.PUBLIC_RO,
                          cls(ObjectStore.PUBLIC_RO_BUCKET, temporary=temporary, read_only=ro))
  ObjectStore.SetInstance(ObjectStore.PUBLIC_RO_LOGS,
                          cls(ObjectStore.PUBLIC_RO_LOGS_BUCKET, temporary=temporary, read_only=True))
  ObjectStore.SetInstance(ObjectStore.PUBLIC_CRASHES,
                          cls(ObjectStore.PUBLIC_CRASHES_BUCKET, temporary=temporary, read_only=ro))
  ObjectStore.SetInstance(ObjectStore.PUBLIC_CRASHES_LOGS,
                          cls(ObjectStore.PUBLIC_CRASHES_LOGS_BUCKET, temporary=temporary, read_only=True))
  ObjectStore.SetInstance(ObjectStore.AWS_DUMP,
                          cls(ObjectStore.AWS_DUMP_BUCKET, temporary=temporary, read_only=ro))
