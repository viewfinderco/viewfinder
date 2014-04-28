# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Verifies operation of ping handler.
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import json
import logging
import urllib

from viewfinder.backend.base import message, util
from viewfinder.backend.www.test import service_base_test
from viewfinder.backend.www.www_util import GzipEncode

class PingTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(PingTestCase, self).setUp()

  def testNoInfoPing(self):
    """Test pings with very little info in the request. Since the ping handler does not go through
    the standard service methods, validation is much more lenient.
    """
    # No header and no device dict.
    req_dict = {}
    response = self._RunAsync(self._tester.http_client.fetch,
                              self._tester.GetUrl('/ping'),
                              method='POST',
                              headers={'Content-Type': 'application/json'},
                              body=json.dumps(req_dict))
    self.assertEqual(response.code, 200)

    # Header without version info, device_dict without version.
    req_dict = { 'headers': {'synchronous': True},
                 'device': {'country': 'US'}}
    response = self._RunAsync(self._tester.http_client.fetch,
                              self._tester.GetUrl('/ping'),
                              method='POST',
                              headers={'Content-Type': 'application/json'},
                              body=json.dumps(req_dict))
    self.assertEqual(response.code, 200)


  def testGzip(self):
    """Test pings with gzip-encoded bodies."""
    req_dict = {}
    response = self._RunAsync(self._tester.http_client.fetch,
                              self._tester.GetUrl('/ping'),
                              method='POST',
                              headers={'Content-Type': 'application/json',
                                       'Content-Encoding': 'gzip'},
                              body=GzipEncode(json.dumps(req_dict)))
    self.assertEqual(response.code, 200)


  def testInfoPing(self):
    """version known to trigger an INFO response message."""
    device_dict = {'version': '1.6.0.41.dev'}
    resp = json.loads(self._SendPing(device_dict))
    self.assertFalse(resp.has_key('message'))
    # Temporarily commented out.
    # self.assertTrue(resp.has_key('message'))
    # msg = resp['message']
    # logging.info(resp)
    # self.assertEqual(msg['title'], 'congrats on running 1.6.0.41.dev')
    # self.assertEqual(msg['body'], 'you have the latest development version')
    # self.assertEqual(msg['link'], 'http://appstore.com/minetta/viewfinder')
    # self.assertEqual(msg['identifier'], 'latest-dev-1.6.0.41.dev')
    # self.assertEqual(msg['severity'], 'INFO')

    # Slightly different version.
    device_dict = {'version': '1.6.0.40.dev'}
    resp = json.loads(self._SendPing(device_dict))
    self.assertFalse(resp.has_key('message'))


  def testAllReleasedVersions(self):
    """We should keep this updated as app store and test flight versions are pushed to ensure that
    we do not accidentally disable some.
    """
    testflight_versions = ['1.4.1.25.adhoc', '1.5.0.26.adhoc', '1.5.0.27.adhoc', '1.5.0.28.adhoc', '1.5.0.29.adhoc',
                           '1.5.0.30.adhoc', '1.5.0.31.adhoc', '1.5.0.32.adhoc', '1.5.0.33.adhoc', '1.5.0.34.adhoc',
                           '1.5.0.35.adhoc', '1.5.0.37.adhoc', '1.5.0.38.adhoc', '1.5.0.39.adhoc', '1.6.0.40.adhoc',
                           '1.6.0.41.adhoc']
    appstore_versions = ['1.3.0.14', '1.3.1.15', '1.3.1.16', '1.4.0.18', '1.4.0.19', '1.4.0.21', '1.4.0.22',
                         '1.4.0.24', '1.4.1.25', '1.5.0.26', '1.5.0.28', '1.5.0.31', '1.5.0.37']

    for v in testflight_versions:
      device_dict = {'version': v}
      resp = json.loads(self._SendPing(device_dict))
      self.assertFalse(resp.has_key('message'), 'Testflight version %s' % v)

    for v in appstore_versions:
      device_dict = {'version': v}
      resp = json.loads(self._SendPing(device_dict))
      self.assertFalse(resp.has_key('message'), 'Appstore version %s' % v)


  def _SendPing(self, device_dict=None):
    """Invoke the /ping handler."""
    req_dict = {'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION}}
    req_dict['device'] = device_dict
    response = self._RunAsync(self._tester.http_client.fetch,
                              self._tester.GetUrl('/ping'),
                              method='POST',
                              headers={'Content-Type': 'application/json'},
                              body=json.dumps(req_dict))
    return response.body
