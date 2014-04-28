# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Classes to handle file object storage.
 Intended for local testing.

 FileObjectStore: store files in a temporary directory
 FileObjectStoreHandler: serves and stores files on GET and PUT
   requests.
"""

__author__ = 'peter@emailscrubbed.com (Peter Mattis)'

import atexit
import base64
import errno
import logging
import os
import shutil
import tempfile
import time
import functools

from tornado import gen, options, web
from tornado.ioloop import IOLoop
from viewfinder.backend.base import constants, handler, util
from viewfinder.backend.storage.object_store import ObjectStore

def GetS3CompatibleFileList(root, prefix=None):
  """Returns a list of filenames from the local object store
  which emulates the sorting order of keys returned from an
  AWS S3 file store.
  """
  def _ListFiles(dir):
    for obj in os.listdir(dir):
      objpath = os.path.join(dir, obj)
      if os.path.isfile(objpath):
        yield os.path.relpath(objpath, root)
      elif os.path.isdir(objpath):
        for f in _ListFiles(objpath):
          yield f

  filelist = [x for x in _ListFiles(root) if not prefix or x.startswith(prefix)]
  return sorted(filelist)

class FileObjectStore(ObjectStore):
  """Simple object storage interface supporting key/value pairs backed
  by the file system. URLs are created based on a supplied URL which
  is formatted with the key name.
  """
  def __init__(self, bucket_name, temporary=False, read_only=False):
    logging.info('initializing local file object store bucket %s' % bucket_name)
    self._read_only = read_only
    if temporary:
      dir = tempfile.mkdtemp()
      atexit.register(shutil.rmtree, dir)
      self._bucket_name = os.path.join(dir, bucket_name)
    else:
      self._bucket_name = os.path.join(options.options.fileobjstore_dir, bucket_name)
      try:
        if options.options.fileobjstore_reset:
          logging.warning('clearing file object store')
          shutil.rmtree(self._bucket_name)
      except:
        pass

  def _MakePath(self, key):
    return os.path.join(self._bucket_name, key)

  def Put(self, key, value, callback, content_type=None, request_timeout=None):
    assert not self._read_only, 'Received "Put" request on read-only object store.'

    # Only support byte strings.
    assert not value or type(value) is str, \
      'Put does not support type "%s". Only byte strings are supported.' % type(value)

    path = self._MakePath(key)
    try:
      os.makedirs(os.path.dirname(path))
    except:
      pass
    fp = open(path, 'wb')
    try:
      fp.write(value)
      IOLoop.current().add_callback(callback)
    finally:
      fp.close()

  def Get(self, key, callback, must_exist=True):
    path = self._MakePath(key)
    # First attempt to open the file and catch "no such file" exception.
    try:
      fp = open(path, 'rb')
    except IOError as e:
      if must_exist or e.errno != errno.ENOENT:
        raise
      else:
        IOLoop.current().add_callback(functools.partial(callback, None))
        return

    # Now read it.
    try:
      value = fp.read()
      IOLoop.current().add_callback(functools.partial(callback, value))
    finally:
      fp.close()


  def ListKeys(self, callback, prefix=None, marker=None, maxkeys=None):
    maxkeys = min(maxkeys, 1000) if maxkeys else 1000
    filelist = GetS3CompatibleFileList(self._bucket_name, prefix)
    index = 0
    if marker:
      # Marker is "excluded first key". It does not have to match an existing key.
      for f in filelist:
        if f == marker:
          index += 1
          break
        elif f > marker:
          break
        index += 1
    IOLoop.current().add_callback(functools.partial(callback, filelist[index:index + maxkeys]))

  @gen.engine
  def ListCommonPrefixes(self, delimiter, callback, prefix=None, marker=None, maxkeys=None):
    # We can just call ListKeys with no limit, then compute the prefixes.
    assert delimiter is not None, 'delimiter arg is required on ListCommonPrefixes'

    file_list = yield gen.Task(self.ListKeys, prefix=prefix, marker=marker, maxkeys=None)
    prefixes = set()
    keys = []
    prefix_length = len(prefix) if prefix else 0
    for f in file_list:
      # We search for the first occurence of the delimiter after the prefix.
      ind = f.find(delimiter, prefix_length)
      if ind != -1:
        prefixes.add(f[0:ind + 1])   # include the delimiter
      else:
        keys.append(f)
      if maxkeys is not None and (len(prefixes) + len(keys)) >= maxkeys:
        break
    IOLoop.current().add_callback(functools.partial(callback, (sorted(prefixes), keys)))


  def Delete(self, key, callback):
    assert not self._read_only, 'Received "Delete" request on read-only object store.'

    path = self._MakePath(key)
    try:
      os.remove(path)
      IOLoop.current().add_callback(callback)
    except:
      pass

  def SetUrlFmtString(self, url_fmt_str):
    self._url_fmt_str = url_fmt_str

  def GenerateUrl(self, key, method='GET', cache_control=None, expires_in=constants.SECONDS_PER_DAY,
                  content_type=None):
    assert self._url_fmt_str
    url = self._url_fmt_str % key

    if cache_control is not None:
      url += '?response-cache-control=%s' % cache_control

    return url

  def GenerateUploadUrl(self, key, content_type=None, content_md5=None,
                        expires_in=constants.SECONDS_PER_DAY, max_bytes=5 << 20):
    assert self._url_fmt_str
    url = self._url_fmt_str % key

    if content_md5 is not None:
      # Re-encode Content-MD5 value in URL friendly format.
      url += '?MD5=%s' % base64.b64decode(content_md5).encode('hex')

    return url


class FileObjectStoreHandler(web.RequestHandler):
  """Simple request handler which returns contents of specified key in
  response on a 'GET' or 'HEAD' request, or 404 if not found. An
  object may be stored by making a 'PUT' request and supplying the
  object contents in the request body.
  """
  _CACHE_MAX_AGE = 86400 * 365 * 10 #10 years

  def initialize(self, storename, contenttype):
    self.content_type = contenttype
    self.object_store = ObjectStore.GetInstance(storename)

  @handler.asynchronous()
  def get(self, key):
    self._Get(key)

  @handler.asynchronous()
  def head(self, key):
    self._Get(key, include_body=False)

  @handler.asynchronous()
  def put(self, key):
    def _OnCompletedPut():
      self.finish()

    # Check that Content-MD5 header matches the MD5 query argument (if it's specified).
    expected_md5 = self.get_argument('MD5', None)
    if expected_md5 is not None:
      if 'Content-MD5' not in self.request.headers:
        raise web.HTTPError(400, 'expected Content-MD5 "%s", received nothing' % expected_md5)

      actual_md5 = base64.b64decode(self.request.headers['Content-MD5']).encode('hex')
      if actual_md5 != expected_md5:
        raise web.HTTPError(400, 'expected Content-MD5 "%s", received "%s"' %
                            (expected_md5, actual_md5))

    self.object_store.Put(key, self.request.body, callback=_OnCompletedPut)

  def _Get(self, key, include_body=True):

    # On error, return 404 to client.
    def _OnError(type, value, traceback):
      self.send_error(404)

    def _OnCompletedGet(content):
      md5_hex = util.ComputeMD5Hex(content)
      self.set_header("Expires", int(time.time()) + FileObjectStoreHandler._CACHE_MAX_AGE)
      self.set_header('Content-Type', self.content_type)
      self.set_header('Content-Length', len(content))
      self.set_header('Content-MD5', md5_hex)
      self.set_header('Etag', '"%s"' % md5_hex)

      cache_control = self.get_argument('response-cache-control', None)
      if cache_control is not None:
        self.set_header("Cache-Control", cache_control)

      if include_body:
        self.write(content)
      self.finish()

    with util.MonoBarrier(_OnCompletedGet, on_exception=_OnError) as b:
      self.object_store.Get(key, b.Callback())

  def check_xsrf_cookie(self):
    """Override tornado's xsrf cookie check.
    S3 doesn't require XSRF, so we won't expect it for the file object store in the local server.
    """
    pass
