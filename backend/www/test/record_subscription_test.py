# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test record_subscription method."""

__author__ = 'ben@emailscrubbed.com (Ben Darnell)'

import base64
from functools import partial
from viewfinder.backend.base.testing import MockAsyncHTTPClient
from viewfinder.backend.db.subscription import Subscription
from viewfinder.backend.services.itunes_store import ITunesStoreClient
from viewfinder.backend.services.test import itunes_store_test
from viewfinder.backend.www.test import service_base_test

class RecordSubscriptionTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(RecordSubscriptionTestCase, self).setUp()
    self.mock_http = MockAsyncHTTPClient(self.io_loop)
    self._validate = False

    ITunesStoreClient.SetInstance('prod', ITunesStoreClient(environment='prod', http_client=self.mock_http))
    ITunesStoreClient.SetInstance('dev', ITunesStoreClient(environment='dev', http_client=self.mock_http))

  def tearDown(self):
    ITunesStoreClient.ClearInstance('prod')
    ITunesStoreClient.ClearInstance('dev')

    super(RecordSubscriptionTestCase, self).tearDown()

  def _CheckSubscriptionMetadata(self, json_dict, transaction_id=itunes_store_test.kTransactionId):
    self.assertEqual(json_dict['transaction_id'], 'itunes:%s' % transaction_id)
    self.assertEqual(json_dict['product_type'], 'vf_sub1')
    self.assertEqual(json_dict['quantity'], 5)
    self.assertEqual(json_dict['extra_info']['transaction_id'], transaction_id)

  def _RecordSubscription(self, user_cookie, receipt_data):
    return self._SendRequest('record_subscription', self._cookie,
                             {'receipt_data': base64.b64encode(receipt_data)})

  def _GetSubscriptions(self, include_history=True):
    return self._RunAsync(Subscription.QueryByUser, self._client, user_id=self._user.user_id,
                          include_history=include_history)

  def testValidReceipt(self):
    """Valid receipts get added to the user's subscriptions."""
    self.mock_http.map('.*', itunes_store_test.MakeNewResponse())
    response = self._RecordSubscription(self._cookie, itunes_store_test.kReceiptData)
    self._CheckSubscriptionMetadata(response['subscription'])
    subs = self._GetSubscriptions()
    self.assertEqual(1, len(subs))
    self.assertEqual(subs[0].transaction_id, 'itunes:%s' % itunes_store_test.kTransactionId)

  def testFreshReceipt(self):
    """Receipts with expiration in the future are returned without include_history=True."""
    # Subscriptions do not currently go through the ServiceTester/DBValidator apparatus,
    # so validation will fail.
    self._validate = False

    self.mock_http.map('.*', itunes_store_test.MakeFreshResponse())
    response = self._RecordSubscription(self._cookie, itunes_store_test.kReceiptData)
    self._CheckSubscriptionMetadata(response['subscription'])
    subs = self._GetSubscriptions(include_history=False)
    self.assertEqual(1, len(subs))
    self.assertEqual(subs[0].transaction_id, 'itunes:%s' % itunes_store_test.kTransactionId)

    # query_users will return non-expired subscriptions
    response = self._SendRequest('query_users', self._cookie, {'user_ids': [self._user.user_id]})
    json_subs = response['users'][0]['private']['subscriptions']
    self.assertEqual(len(json_subs), 1)
    self._CheckSubscriptionMetadata(json_subs[0])

    # a notification was also sent for the user
    response = self._SendRequest('query_notifications', self._cookie, {})
    for n in response['notifications']:
      if n['name'] == 'record_subscription':
        self.assertEqual(n['invalidate'], {'users': [self._user.user_id]})
        break
    else:
      raise AssertionError('did not find record_subscription invalidation in %r' % response)

  def testDuplicateReceipt(self):
    """Repeated upload of the same receipt succeeds but doesn't create
    duplicate records.
    """
    self.mock_http.map('.*', itunes_store_test.MakeNewResponse())
    response = self._RecordSubscription(self._cookie, itunes_store_test.kReceiptData)
    self._CheckSubscriptionMetadata(response['subscription'])
    response = self._RecordSubscription(self._cookie, itunes_store_test.kReceiptData)
    self._CheckSubscriptionMetadata(response['subscription'])
    subs = self._GetSubscriptions()
    self.assertEqual(1, len(subs))

  def testMultipleReceipts(self):
    """Different receipts create new records."""
    self.mock_http.map('.*', itunes_store_test.MakeNewResponse())
    response = self._RecordSubscription(self._cookie, 'receipt1')
    self._CheckSubscriptionMetadata(response['subscription'])
    self.mock_http.map('.*', itunes_store_test.MakeRenewedResponse())
    response = self._RecordSubscription(self._cookie, 'receipt2')
    self._CheckSubscriptionMetadata(response['subscription'], transaction_id=itunes_store_test.kTransactionId2)
    subs = self._GetSubscriptions()
    self.assertEqual(2, len(subs))
    self.assertItemsEqual(
      ['itunes:%s' % i for i in [itunes_store_test.kTransactionId, itunes_store_test.kTransactionId2]],
      [sub.transaction_id for sub in subs])

  def testInvalidReceipt(self):
    """ERROR: an invalid signature fails cleanly with a 400 status code,
    indicating the retrying is futile."""
    self.mock_http.map('.*', itunes_store_test.MakeBadSignatureResponse())
    self.assertRaisesHttpError(400, self._RecordSubscription, self._cookie, itunes_store_test.kReceiptData)
    self.assertEqual([], self._GetSubscriptions())

  def testServerError(self):
    """ERROR: server errors fail with a 500 status code, indicating
    that the request should be retried in the future."""
    self.mock_http.map('.*', itunes_store_test.MakeServerErrorResponse())
    self.assertRaisesHttpError(500, self._RecordSubscription, self._cookie, itunes_store_test.kReceiptData)
    self.assertEqual([], self._GetSubscriptions())

  def testSandboxReceipt(self):
    """Receipts from the itunes sandbox are validated, but not recorded."""
    self.mock_http.map(ITunesStoreClient._SETTINGS['prod']['verify_url'],
                       itunes_store_test.MakeSandboxOnProdResponse())
    self.mock_http.map(ITunesStoreClient._SETTINGS['dev']['verify_url'],
                       itunes_store_test.MakeNewResponse())
    response = self._RecordSubscription(self._cookie, itunes_store_test.kReceiptData)
    # Metadata is returned in the response, but will not be present when queried later.
    self._CheckSubscriptionMetadata(response['subscription'])
    self.assertEqual([], self._GetSubscriptions())
