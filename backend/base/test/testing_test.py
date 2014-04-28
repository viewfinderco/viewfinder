import mock

from cStringIO import StringIO
from tornado import httpclient
from viewfinder.backend.base import testing

kURL = "http://www.example.com/"

class MockAsyncHTTPClientTestCase(testing.BaseTestCase):
  def setUp(self):
    super(MockAsyncHTTPClientTestCase, self).setUp()
    self.http_client = testing.MockAsyncHTTPClient()

  def test_unmapped(self):
    """Requests not on the whitelist raise an error."""
    with self.assertRaises(ValueError):
      self.http_client.fetch(kURL, self.stop)

  def test_string(self):
    """Map a url to a constant string."""
    self.http_client.map(kURL, "hello world")
    self.http_client.fetch(kURL, self.stop)
    response = self.wait()
    self.assertEqual(response.body, "hello world")

  def test_callable(self):
    """Map a url to a function returning a string."""
    self.http_client.map(kURL, lambda request: "hello world")
    self.http_client.fetch(kURL, self.stop)
    response = self.wait()
    self.assertEqual(response.body, "hello world")

  def test_response(self):
    """Map a url to a function returning an HTTPResponse.

    HTTPResponse's constructor requires a request object, so there is no
    fourth variant that returns a constant HTTPResponse.
    """
    self.http_client.map(kURL, lambda request: httpclient.HTTPResponse(
        request, 404, buffer=StringIO("")))
    self.http_client.fetch(kURL, self.stop)
    response = self.wait()
    self.assertEqual(response.code, 404)

  def test_with_patch(self):
    """Replace the AsyncHTTPClient class using mock.patch."""
    self.http_client.map(kURL, "hello world")
    with mock.patch('tornado.httpclient.AsyncHTTPClient', self.http_client):
      real_client = httpclient.AsyncHTTPClient()
      self.assertIs(self.http_client, real_client)
      real_client.fetch(kURL, self.stop)
      response = self.wait()
    self.assertEqual(response.body, "hello world")
