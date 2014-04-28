# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for DBObject.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import json
import mock
import time
import unittest

from cStringIO import StringIO
from functools import partial
from tornado import httpclient
from viewfinder.backend.base.testing import MockAsyncHTTPClient
from viewfinder.backend.db import dynamodb_client, vf_schema
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.test.base_test import DBBaseTestCase


class DBObjectTestCase(DBBaseTestCase):
  @unittest.skip("needs aws credentials")
  def testRangeQuery(self):
    """Test DBRangeObject.RangeQuery."""
    def _MakeResponse(max_index, request):
      # Enforce maximum limit of 2.
      request_dict = json.loads(request.body)
      limit = min(request_dict.get('Limit', 2), 2)
      is_count = request_dict.get('Count')

      if 'ExclusiveStartKey' in request_dict:
        start_index = int(request_dict['ExclusiveStartKey']['RangeKeyElement']['S']['S'][-1]) + 1
      else:
        start_index = 0

      count = min(max_index - start_index, limit)
      items = []
      for i in xrange(start_index, start_index + count):
        items.append({'ei': {'S': 'e0'},
                      'sk': {'S': 'p%d' % i}})

      response_dict = {'Count': count,
                       'ConsumedCapacityUnits': 0.5}
      if not is_count:
        response_dict['Items'] = items

      if start_index + count < max_index:
       response_dict['LastEvaluatedKey'] = {'HashKeyElement': {'S': items[-1]['ei']},
                                            'RangeKeyElement': {'S': items[-1]['sk']}}

      return httpclient.HTTPResponse(request, 200,
                                     headers={'Content-Type': 'application/json'},
                                     buffer=StringIO(json.dumps(response_dict)))

    # Get session token from Amazon (no need to mock that).
    client = dynamodb_client.DynamoDBClient(schema=vf_schema.SCHEMA)
    self._RunAsync(client.GetItem, vf_schema.TEST_RENAME, DBKey('1', 1), attributes=None, must_exist=False)

    with mock.patch('tornado.httpclient.AsyncHTTPClient', MockAsyncHTTPClient()) as mock_client:
      mock_client.map(r'https://dynamodb.us-east-1.amazonaws.com', partial(_MakeResponse, 5))

      # Limit = None.
      posts = self._RunAsync(Post.RangeQuery, client, 'e0', None, None, None)
      self.assertEqual(len(posts), 2)

      # Limit = 2.
      posts = self._RunAsync(Post.RangeQuery, client, 'e0', None, 2, None)
      self.assertEqual(len(posts), 2)

      # Limit = 5.
      posts = self._RunAsync(Post.RangeQuery, client, 'e0', None, 5, None)
      self.assertEqual(len(posts), 5)

      # Limit = 7.
      posts = self._RunAsync(Post.RangeQuery, client, 'e0', None, 7, None)
      self.assertEqual(len(posts), 5)

      # Limit = None, count = True.
      count = self._RunAsync(Post.RangeQuery, client, 'e0', None, None, None, count=True)
      self.assertEqual(count, 2)

      # Limit = 2, count = True.
      count = self._RunAsync(Post.RangeQuery, client, 'e0', None, 2, None, count=True)
      self.assertEqual(count, 2)

      # Limit = 5, count = True.
      count = self._RunAsync(Post.RangeQuery, client, 'e0', None, 5, None, count=True)
      self.assertEqual(count, 5)

      # Limit = 7, count = True.
      count = self._RunAsync(Post.RangeQuery, client, 'e0', None, 7, None, count=True)
      self.assertEqual(count, 5)

  def testBatchQuery(self):
    """Test DBObject.BatchQuery."""
    # Create some data to query.
    keys = []
    for i in xrange(3):
      photo_id = Photo.ConstructPhotoId(time.time(), self._mobile_dev.device_id, 1)
      episode_id = Episode.ConstructEpisodeId(time.time(), self._mobile_dev.device_id, 1)
      ph_dict = {'photo_id': photo_id,
                 'user_id': self._user.user_id,
                 'episode_id': episode_id}
      self._RunAsync(Photo.CreateNew, self._client, **ph_dict)
      keys.append(DBKey(photo_id, None))

    # Add a key that will not be found.
    keys.append(DBKey('unk-photo', None))

    photos = self._RunAsync(Photo.BatchQuery, self._client, keys, None, must_exist=False)
    self.assertEqual(len(photos), 4)
    for i in xrange(3):
      self.assertEqual(photos[i].GetKey(), keys[i])
    self.assertIsNone(photos[3])
