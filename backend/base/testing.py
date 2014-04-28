# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Base testing utilities.

Make sure to decorate all asynchronous test methods with @async_test.

  @async_test: use this decorator for all asynchronous tests
  @async_test_timeout(timeout=<>): use this decorator for all asynchronous tests to set timeout
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'


import functools
import logging
import re
import sys
import threading
import time
import unittest


from cStringIO import StringIO
from functools import partial
from tornado.concurrent import Future
from tornado import testing, ioloop, httpclient


def async_test(method):
  """Decorator for tests running in test cases derived from
  tornado.testing.AsyncTestCase and tornado.testing.AsyncHTTPTestCase.

  On error, calls self.stop().

  NOTE: Tests are responsible for calling self.stop() to signal to
  tornado async test framework that test is complete.
  """
  @functools.wraps(method)
  def Wrapper(self):
    method(self)
    self.wait()

  return Wrapper

# Tell nose that this method named _test isn't a test.
async_test.__test__ = False

class TestThread(threading.Thread):
  """Thread class which runs the specified test method. On
  completion, invokes the completion method.
  """
  def __init__(self, test_method, on_completion):
    super(TestThread, self).__init__()
    self._test_method = test_method
    self._on_completion = on_completion
    self._exc_info = None

  def run(self):
    try:
      self._test_method()
    except:
      self._exc_info = sys.exc_info()
    finally:
      self._on_completion()

  def MaybeRaise(self):
    if self._exc_info is not None:
      type, value, tb = self._exc_info
      raise type, value, tb


def thread_test(method):
  """Decorator for tests which need to be run synchronously. Runs
  the test in a separate thread.
  """
  @functools.wraps(method)
  def Wrapper(self):
    thread = TestThread(partial(method, self),
                        partial(self.io_loop.add_callback, self.stop))
    thread.start()
    self.wait()
    thread.MaybeRaise()

  return Wrapper

thread_test.__test__ = False

def async_test_timeout(timeout=5):
  def _async_test(method):
    def _wrapper(self, *args, **kwargs):
      method(self, *args, **kwargs)
      self.wait(timeout=timeout)

    return functools.wraps(method)(_wrapper)
  return _async_test


class BaseTestCase(testing.AsyncTestCase):
  """Base TestCase class for simple asynchronous tests.
  This class can be used as a mix-in in conjunction with tornado's AsyncHTTPTestCase.
  """
  def wait(self, condition=None, timeout=5):
    """It is convenient to repeatedly use the "wait" method in order to
    create synchronous tests. If the async call raises an exception, then
    the wait method will re-raise that exception, which is desirable.
    However, when this happens, Tornado "remembers" the exception, and
    will re-throw it *every* time that wait is called from then on. This
    override patches this behavior by clearing the private __failure
    field in Tornado's testing class so that subsequent waits will not
    fail.
    """
    try:
      return super(BaseTestCase, self).wait(condition, timeout)
    finally:
      self._AsyncTestCase__failure = None

  def _RunAsync(self, func, *args, **kwargs):
    """Runs an async function which takes a callback argument. Waits for
    the function to complete and returns any result.
    """
    func(callback=self.stop, *args, **kwargs)
    return self.wait()


class LogMatchTestCase(testing.LogTrapTestCase):
  """Mix in the methods of this class in order to intercept and possibly
  test the content of logs that are produced by the test case. This
  class turns on all logging levels and adds a convenient assert method
  that can be used to test the output of the logging for desired patterns.
  """
  def run(self, result=None):
    """Override the run method in order to set the root logger to the
    NOTSET logging level, so that no logging done by the test case will
    be suppressed. Restore the original logging level once the test
    case has been run.
    """
    logger = logging.getLogger()
    current_level = logger.level
    try:
      logger.setLevel('NOTSET')
      super(LogMatchTestCase, self).run(result)
    finally:
      logger.setLevel(current_level)

  def assertLogMatches(self, expected_regexp, msg=None):
    """Fail the test unless the intercepted log matches the regular
    expression.
    """
    format = '%s: %%r was not found in log' % (msg or 'Regexp didn\'t match')
    self._AssertLogMatches(expected_regexp, False, format)

  def assertNotLogMatches(self, expected_regexp, msg=None):
    """Fail the test if the intercepted log *does* match the regular
    expression.
    """
    format = '%s: %%r was found in log' % (msg or 'Regexp matches')
    self._AssertLogMatches(expected_regexp, True, format)

  def _AssertLogMatches(self, expected_regexp, invert, format):
    """Assert if the intercepted log matches the regular expression,
    or if "invert" is True and no match is found.
    """
    if isinstance(expected_regexp, basestring):
        expected_regexp = re.compile(expected_regexp, re.MULTILINE | re.DOTALL)

    handler = logging.getLogger().handlers[0]
    if not hasattr(handler, 'stream'):
      # Nose's test runner installs a log handler that this test isn't compatible with.
      # TODO(ben): figure out how to make this work.
      raise unittest.SkipTest()
    log_text = handler.stream.getvalue()
    matches = expected_regexp.search(log_text) is not None
    if matches == invert:
      raise self.failureException(format % expected_regexp.pattern)

class TimingTextTestResult(unittest.TextTestResult):
  def startTest(self, test):
    self.__start_time = time.time()
    super(TimingTextTestResult, self).startTest(test)

  def addSuccess(self, test):
    if self.showAll:
      delta = time.time() - self.__start_time
      self.stream.write('(%d ms) ' % int(delta * 1000))
    super(TimingTextTestResult, self).addSuccess(test)

class TimingTextTestRunner(unittest.TextTestRunner):
  """Wraps the standard unittest runner to print additional information.

  In verbose mode, each test prints how long it took to run.  Also
  prints the class and function name instead of the docstring by default.
  """
  def __init__(self, *args, **kwargs):
    kwargs.setdefault('resultclass', TimingTextTestResult)
    kwargs.setdefault('descriptions', False)
    super(TimingTextTestRunner, self).__init__(*args, **kwargs)

# not a subclass of AsyncHTTPClient to avoid __new__ magic
class MockAsyncHTTPClient(object):
  """Mock HTTP client for tests.

  Has the same interface as `tornado.httpclient.AsyncHTTPClient`,
  but returns a pre-configured response to any request.
  To use, create a MockAsyncHTTPClient, call `map` at least once
  to map urls to responses, then use `fetch` to make the requests.

  While it is recommended that any code using an AsyncHTTPClient
  allow it to be passed in as an argument, we have a lot of code
  that relies on AsyncHTTPClient's magic pseudo-singleton behavior
  and "constructs" a new client each time.  For this, we support
  `mock.patch`:

    with mock.patch('tornado.httpclient.AsyncHTTPClient', MockAsyncHTTPClient() as mock_client:
      mock_client.map(url, response)
      call_other_functions()

  Note that this is a non-standard use of patch (we're replacing a class
  with an instance); this is somewhat hacky but the simplest way of
  dealing with the instantiation magic in AsyncHTTPClient.
  """
  def __init__(self, io_loop=None):
    self.io_loop = io_loop or ioloop.IOLoop.current()
    self.url_map = []

  def map(self, regex, response):
    """Maps a url regex to a response.

    Any request whose url matches the given regex will get the corresponding
    response (if multiple regexes match, the most recently mapped one wins).
    The response may be a string (used as the body), a
    `tornado.httpclient.HTTPResponse` object, or a function that takes a
    request and returns one of the preceding types.
    """
    self.url_map.insert(0, (re.compile(regex), response))

  def fetch(self, request, callback=None, **kwargs):
    """Implementation of AsyncHTTPClient.fetch"""
    if not isinstance(request, httpclient.HTTPRequest):
      request = httpclient.HTTPRequest(url=request, **kwargs)
    for regex, response in self.url_map:
      if regex.match(request.url):
        if callable(response):
          response = response(request)
        if isinstance(response, basestring):
          response = httpclient.HTTPResponse(request, 200,
                                             buffer=StringIO(response))
        assert isinstance(response, httpclient.HTTPResponse)
        if callback is not None:
          self.io_loop.add_callback(functools.partial(callback, response))
          return None
        else:
          future = Future()
          future.set_result(response)
          return future
    raise ValueError("got request for unmapped url: %s" % request.url)

  def __call__(self, io_loop=None):
    """Hacky support for mock.patch.

    We patch the AsyncHTTPClient class and replace it with this instance,
    so "calling" the instance should act like instantiating the class.
    """
    if io_loop is not None:
      assert io_loop is self.io_loop
    return self
