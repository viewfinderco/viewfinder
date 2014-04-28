# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Unit test short URL classes.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

import json
import mock

from tornado import options
from viewfinder.backend.base import constants, util
from viewfinder.backend.base.exceptions import TooManyRetriesError
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.guess import Guess
from viewfinder.backend.db.short_url import ShortURL
from viewfinder.backend.www import base
from viewfinder.backend.www.short_url_base import ShortURLBaseHandler
from viewfinder.backend.www.test import service_base_test


class TestShortURLBaseHandler(ShortURLBaseHandler, base.BaseHandler):
  """Derive test class from ShortURLBaseHandler that simply echoes its arguments in a JSON
  response.
  """
  _MAX_GUESSES = 50

  def _HandleGet(self, short_url, arg1, arg2):
    self.write({'method': 'GET',
                'group_id': short_url.group_id,
                'random_key': short_url.random_key,
                'timestamp': short_url.timestamp,
                'expires': short_url.expires,
                'arg1': arg1,
                'arg2': arg2})
    self.finish()

  def _HandlePost(self, short_url, arg1, arg2):
    self.write({'method': 'POST',
                'group_id': short_url.group_id,
                'random_key': short_url.random_key,
                'timestamp': short_url.timestamp,
                'expires': short_url.expires,
                'arg1': arg1,
                'arg2': arg2})
    self.finish()


class ShortURLTestCase(service_base_test.ServiceBaseTestCase):
  """Unit test short URL classes."""
  def setUp(self):
    super(ShortURLTestCase, self).setUp()

    self._app.add_handlers(r'.*', [(r'/(test/.*)', TestShortURLBaseHandler)])

    self._short_url = self._RunAsync(ShortURL.Create,
                                     self._client,
                                     group_id='test/abcd',
                                     timestamp=util._TEST_TIME,
                                     expires=util._TEST_TIME + constants.SECONDS_PER_DAY,
                                     arg1=1,
                                     arg2='foo')
    self._url = self.get_url('/%s%s' % (self._short_url.group_id, self._short_url.random_key))

  def testShortURLGet(self):
    """Test valid short URL generation and redemption via GET request."""
    response = self._RunAsync(self.http_client.fetch, self._url, method='GET')
    self.assertEqual(response.code, 200)
    self.assertEqual(json.loads(response.body), {'method': 'GET',
                                                 'group_id': 'test/abcd',
                                                 'random_key': self._short_url.random_key,
                                                 'timestamp': util._TEST_TIME,
                                                 'expires': util._TEST_TIME + constants.SECONDS_PER_DAY,
                                                 'arg1': 1,
                                                 'arg2': 'foo'})

  def testShortURLPost(self):
    """Test valid short URL generation and redemption via POST requeset."""
    response = self._RunAsync(self.http_client.fetch,
                              self._url,
                              method='POST',
                              headers={'Cookie': '_xsrf="fake_xsrf";', 'X-Xsrftoken': 'fake_xsrf'},
                              body='{}')
    self.assertEqual(response.code, 200)
    self.assertEqual(json.loads(response.body), {'method': 'POST',
                                                 'group_id': 'test/abcd',
                                                 'random_key': self._short_url.random_key,
                                                 'timestamp': util._TEST_TIME,
                                                 'expires': util._TEST_TIME + constants.SECONDS_PER_DAY,
                                                 'arg1': 1,
                                                 'arg2': 'foo'})

  @mock.patch.object(TestShortURLBaseHandler, '_MAX_GUESSES', 1)
  def testMaxGuesses(self):
    """Test enforcement of max guesses for a particular group id."""
    # ------------------------------
    # Try to access non-existent link (404).
    # ------------------------------
    url = self.get_url('/test/abcd12345678')
    response = self._RunAsync(self.http_client.fetch, url, method='GET')
    self.assertEqual(response.code, 404)

    # ------------------------------
    # No more guesses should be allowed (403).
    # ------------------------------
    response = self._RunAsync(self.http_client.fetch, url, method='GET')
    self.assertEqual(response.code, 403)

    # ------------------------------
    # Not even correct guesses (403).
    # ------------------------------
    response = self._RunAsync(self.http_client.fetch, self._url, method='GET')
    self.assertEqual(response.code, 403)

    # ------------------------------
    # But do allow guesses on other group ids.
    # ------------------------------
    url = self.get_url('/test/another12345678')
    response = self._RunAsync(self.http_client.fetch, url, method='GET')
    self.assertEqual(response.code, 404)

    # ------------------------------
    # Now "wait" 24 hours and make sure another guess is allowed.
    # ------------------------------
    util._TEST_TIME += constants.SECONDS_PER_DAY
    response = self._RunAsync(self.http_client.fetch, url, method='GET')
    self.assertEqual(response.code, 404)

  def testExpire(self):
    """Test forced expiration of a ShortURL."""
    self._RunAsync(self._short_url.Expire, self._client)
    response = self._RunAsync(self.http_client.fetch, self._url, method='GET')
    self.assertEqual(response.code, 403)

  def testShortURLErrors(self):
    """Test various short URL error cases."""
    # ------------------------------
    # Non-existent short URL.
    # ------------------------------
    url = self.get_url('/test/1234567890')
    response = self._RunAsync(self.http_client.fetch, url, method='GET')
    self.assertEqual(response.code, 404)

    # ------------------------------
    # Malformed short URL.
    # ------------------------------
    url = self.get_url('/test/1')
    response = self._RunAsync(self.http_client.fetch, url, method='GET')
    self.assertEqual(response.code, 400)

    # ------------------------------
    # Expired short URL.
    # ------------------------------
    util._TEST_TIME += constants.SECONDS_PER_DAY
    response = self._RunAsync(self.http_client.fetch, self._url, method='GET')
    self.assertEqual(response.code, 403)

    # ------------------------------
    # Unique key cannot be found.
    # ------------------------------
    with mock.patch.object(ShortURL, '_KEY_GEN_TRIES', 0):
      self.assertRaises(TooManyRetriesError,
                        self._RunAsync,
                        ShortURL.Create,
                        self._client,
                        group_id='test/abcd',
                        timestamp=util._TEST_TIME,
                        expires=util._TEST_TIME + constants.SECONDS_PER_DAY,
                        arg1=1,
                        arg2='foo')

  def testShortDomainRedirectHandler(self):
    """Test the short domain redirect handler."""
    url = 'http://%s:%d/p12345' % (options.options.short_domain, self.get_http_port())
    response = self._RunAsync(self.http_client.fetch, url, method='GET', follow_redirects=False)
    self.assertEqual(response.code, 302)
    self.assertEqual(response.headers['location'], 'https://goviewfinder.com/pr/12345')
