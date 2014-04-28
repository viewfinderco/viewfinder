# Copyright 2012 Viewfinder Inc. All Rights Reserved.

__author__ = 'ben@emailscrubbed.com (Ben Darnell)'

from viewfinder.backend.db.test.base_test import DBBaseTestCase
from viewfinder.backend.db.subscription import Subscription
from viewfinder.backend.services import itunes_store
from viewfinder.backend.services.test import itunes_store_test

class SubscriptionTestCase(DBBaseTestCase):
  def testCreateFromITunes(self):
    # Create an initial subscription.
    verify_response = itunes_store.VerifyResponse(itunes_store_test.kReceiptData, itunes_store_test.MakeNewResponse())
    Subscription.RecordITunesTransaction(self._client, self.stop, user_id=self._user.user_id, verify_response=verify_response)
    self.wait()

    # The test subscription is expired, so it won't be returned by default.
    Subscription.QueryByUser(self._client, self.stop, self._user.user_id)
    subs = self.wait()
    self.assertEqual(len(subs), 0)

    # It's there with include_expired=True.
    Subscription.QueryByUser(self._client, self.stop, self._user.user_id, include_expired=True)
    subs = self.wait()
    self.assertEqual(len(subs), 1)
    self.assertEqual(subs[0].expiration_ts, itunes_store_test.kExpirationTime)
    first_transaction_id = subs[0].transaction_id

    # Now add a renewal.
    verify_response = itunes_store.VerifyResponse(itunes_store_test.kReceiptData, itunes_store_test.MakeRenewedResponse())
    Subscription.RecordITunesTransaction(self._client, self.stop, user_id=self._user.user_id, verify_response=verify_response)
    self.wait()

    # Only the latest transaction is returned.
    Subscription.QueryByUser(self._client, self.stop, self._user.user_id, include_expired=True)
    subs = self.wait()
    self.assertEqual(len(subs), 1)
    self.assertEqual(subs[0].expiration_ts, itunes_store_test.kExpirationTime2)
    self.assertNotEqual(subs[0].transaction_id, first_transaction_id)

    # With include_history=True we get both transactions.
    Subscription.QueryByUser(self._client, self.stop, self._user.user_id, include_history=True)
    subs = self.wait()
    self.assertEqual(len(subs), 2)
    self.assertItemsEqual([sub.expiration_ts for sub in subs],
                          [itunes_store_test.kExpirationTime, itunes_store_test.kExpirationTime2])
