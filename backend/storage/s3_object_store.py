#!/usr/bin/env python
#
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

__author__ = 'peter@emailscrubbed.com (Peter Mattis)'

import boto
import time
import urllib

from boto.s3.connection import S3Connection
from functools import partial
from viewfinder.backend.base import constants, counters, util
from viewfinder.backend.base.secrets import GetSecret
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.storage.async_s3 import AsyncS3Connection
from xml.etree import ElementTree

_puts_per_min = counters.define_rate('viewfinder.s3.puts_per_min', 'Average S3 puts per minute.', 60)
_secs_per_put = counters.define_average('viewfinder.s3.secs_per_put', 'Average time in seconds to complete each S3 put')
_gets_per_min = counters.define_rate('viewfinder.s3.gets_per_min', 'Average S3 gets per minute.', 60)

class S3ObjectStore(ObjectStore):
  """Simple object storage interface supporting key/value pairs backed by S3.
  Methods that require network round-trips are asynchronous; they take a
  callback argument that will be invoked if the operation completes
  successfully. If the operation fails, then an exception is raised. To
  handle this exception, use a Barrier instance with the exception handler
  defined.
  """
  def __init__(self, bucket_name, temporary=False, read_only=False):
    assert not temporary, 'temporary can only be specified True for file object store'
    self._bucket_name = bucket_name
    self._read_only = read_only

    # Used for generate_url.
    self._s3_conn = S3Connection(aws_access_key_id=GetSecret('aws_access_key_id'),
                                 aws_secret_access_key=GetSecret('aws_secret_access_key'))

    # Used for async operations.
    self._async_s3_conn = AsyncS3Connection(aws_access_key_id=GetSecret('aws_access_key_id'),
                                            aws_secret_access_key=GetSecret('aws_secret_access_key'))

  def Put(self, key, value, callback, content_type=None, request_timeout=20.0):
    """Asynchronously puts the specified S3 key/value pair, overwriting any
    existing stored data. The value must be a byte string (str) instance.
    The raw str bytes are stored in S3. If "content_type" is defined, then
    the Content-Type header is set to its value. If the operation succeeds,
    then the callback will be invoked with no arguments.
    """
    assert not self._read_only, 'Received "Put" request on read-only object store.'

    # Define callback function which raises any error and then invokes the user callback function.
    def _OnCompletedPut(start_time, response):
      if response.error:
        raise response.error
      _secs_per_put.add(time.time() - start_time)
      callback()

    start_time = time.time()
    _puts_per_min.increment()
    headers = { "Content-Type": content_type } if content_type else None
    self._async_s3_conn.make_request('PUT', bucket=self._bucket_name, key=key, headers=headers,
                                     body=value, request_timeout=request_timeout,
                                     callback=partial(_OnCompletedPut, start_time))

  def Get(self, key, callback, must_exist=True):
    """Asynchronously retrieves the specified key/value pair. If the
    operation succeeds, then the callback will be invoked with a single
    byte string (str) argument containing the value.
    If must_exist is False and the file is not found, the callback will be
    invoked with None.
    """
    # Define callback function which raises any error and then invokes the user callback function.
    def _OnCompletedGet(response):
      if response.error:
        if must_exist or response.error.code != 404:
          raise response.error
        else:
          callback(None)
      else:
        callback(response.body)

    _gets_per_min.increment()
    self._async_s3_conn.make_request('GET', bucket=self._bucket_name, key=key, callback=_OnCompletedGet)

  def ListKeys(self, callback, prefix=None, marker=None, maxkeys=None):
    """List files in a S3 bucket."""
    def _OnCompletedGet(response):
      if response.error:
        raise response.error

      # Expected XML format documented at http://docs.amazonwebservices.com/AmazonS3/latest/API/RESTBucketGET.html
      # Example for a response with 2 keys:
      # <?xml version="1.0" encoding="UTF-8"?>
      # <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
      #   <Contents>
      #     <Key>path/to/object1</Key>
      #   </Contents>
      #   <Contents>
      #     <Key>path/to/object2</Key>
      #   </Contents>
      # </ListBucketResult>
      ns = '{http://s3.amazonaws.com/doc/2006-03-01/}'
      item_element = '%sContents' % ns
      key_element = '%sKey' % ns

      bucket_list = ElementTree.XML(response.body)
      result = [item.find(key_element).text for item in bucket_list.iter(item_element)]
      callback(result)

    params = dict()
    if prefix:
      params['prefix'] = prefix
    if marker:
      params['marker'] = marker
    if maxkeys is not None:
      params['max-keys'] = maxkeys

    self._async_s3_conn.make_request('GET', bucket=self._bucket_name, key='', params=params, callback=_OnCompletedGet)

  def ListKeyMetadata(self, callback, prefix=None, marker=None,
                      maxkeys=None, fields=None):
    """List files in a S3 bucket and return metadata fields.
    Generates a dictionary of {'file0': {'field0':'fieldvalue', ...}, ... 'fileN': {'field0':'fieldvalue'}}.
    """
    def _OnCompletedGet(response):
      if response.error:
        raise response.error

      ns = '{http://s3.amazonaws.com/doc/2006-03-01/}'
      item_element = '%sContents' % ns
      key_element = '%sKey' % ns

      # build dictionary of wanted fields with ns prefix.
      wanted = {}
      for f in fields:
        wanted['%s%s' % (ns, f)] = f

      results = {}
      bucket_list = ElementTree.XML(response.body)
      for item in bucket_list.iter(item_element):
        item_result = {}
        key = item.find(key_element).text
        assert key is not None, item
        for p in item.iter():
          if p.tag in wanted:
            item_result[wanted[p.tag]] = p.text
        results[key] = item_result
      callback(results)

    params = dict()
    if prefix:
      params['prefix'] = prefix
    if marker:
      params['marker'] = marker
    if maxkeys is not None:
      params['max-keys'] = maxkeys

    self._async_s3_conn.make_request('GET', bucket=self._bucket_name, key='', params=params, callback=_OnCompletedGet)


  def ListCommonPrefixes(self, delimiter, callback, prefix=None, marker=None, maxkeys=None):
    """List files in a S3 bucket."""
    assert delimiter is not None, 'delimiter arg is required on ListCommonPrefixes'
    def _OnCompletedGet(response):
      if response.error:
        raise response.error

      # Expected XML format documented at http://docs.amazonwebservices.com/AmazonS3/latest/API/RESTBucketGET.html
      # Example for a response with 2 keys:
      # <?xml version="1.0" encoding="UTF-8"?>
      # <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
      #   <Contents>
      #     <Key>path/to/object1</Key>
      #   </Contents>
      #   <Contents>
      #     <Key>path/to/object2</Key>
      #   </Contents>
      # </ListBucketResult>
      ns = '{http://s3.amazonaws.com/doc/2006-03-01/}'
      common_prefix_element = '%sCommonPrefixes' % ns
      prefix_element = '%sPrefix' % ns

      item_element = '%sContents' % ns
      key_element = '%sKey' % ns

      bucket_list = ElementTree.XML(response.body)
      prefixes = [item.find(prefix_element).text for item in bucket_list.iter(common_prefix_element)]
      items = [item.find(key_element).text for item in bucket_list.iter(item_element)]
      callback((prefixes, items))

    params = dict()
    if prefix:
      params['prefix'] = prefix
    if marker:
      params['marker'] = marker
    if maxkeys is not None:
      params['max-keys'] = maxkeys
    params['delimiter'] = delimiter

    self._async_s3_conn.make_request('GET', bucket=self._bucket_name, key='', params=params, callback=_OnCompletedGet)


  def Delete(self, key, callback):
    """Asynchronously deletes the specified key. If the operation succeeds,
    then the callback is invoked with no arguments.
    """
    assert not self._read_only, 'Received "Delete" request on read-only object store.'

    # Define callback function which raises any error and then invokes the user callback function.
    def _OnCompletedDelete(response):
      if response.error:
        raise response.error
      callback()

    self._async_s3_conn.make_request('DELETE', bucket=self._bucket_name, key=key, callback=_OnCompletedDelete)

  def GenerateUrl(self, key, method='GET', cache_control=None, expires_in=constants.SECONDS_PER_DAY,
                  content_type=None):
    """Generates a URL that can be used retrieve the specified key. If 'cache_control' is
    given, it will result in a Cache-Control header being added to any S3 responses. The
    expires_in parameter specifies how long (in seconds) the URL is valid for.
    content-type forces the content-type of the downloaded file. eg: use text/plain for logs.
    """
    response_headers = {}
    util.SetIfNotNone(response_headers, 'response-cache-control', cache_control)
    util.SetIfNotNone(response_headers, 'response-content-type', content_type)
    return self._s3_conn.generate_url(expires_in,
                                      method,
                                      self._bucket_name,
                                      key,
                                      response_headers=response_headers or None)

  def GenerateUploadUrl(self, key, content_type=None, content_md5=None, expires_in=constants.SECONDS_PER_DAY,
                        max_bytes=5 << 20):
    """Generates a URL for a PUT request to allow a client to store the specified key directly
    to S3 from a browser or mobile client. 'max_bytes' limits the upload file size to prevent
    D.O.S. attacks.
    TODO(andy) max_bytes is not currently enforced, need to fix this.
    """
    headers = {}
    util.SetIfNotNone(headers, 'Content-Type', content_type)
    util.SetIfNotNone(headers, 'Content-MD5', content_md5)

    return self._s3_conn.generate_url(expires_in,
                                      'PUT',
                                      self._bucket_name,
                                      key,
                                      headers=headers or None)
