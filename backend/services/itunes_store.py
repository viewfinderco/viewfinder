# Copyright 2012 Viewfinder Inc. All Rights Reserved
"""iTunes Store service client.

Server-side code for working with iTunes/App Store in-app purchases.

Contents:
* ITunesStoreClient: Communicates with the store to verify receipts and
  process renewals.
"""

import base64
import json
import logging
import time

from tornado.httpclient import AsyncHTTPClient
from viewfinder.backend.base import secrets

class ITunesStoreError(Exception):
  pass

kViewfinderBundleId = 'co.viewfinder.Viewfinder'

class VerifyResponse(object):
  # error codes from https://developer.apple.com/library/ios/#documentation/NetworkingInternet/Conceptual/StoreKitGuide/RenewableSubscriptions/RenewableSubscriptions.html#//apple_ref/doc/uid/TP40008267-CH4-SW2
  # Note that these errors are *only* for auto-renewing subscriptions;
  # non-renewing purchases have a different error table.
  JSON_ERROR = 21000
  MALFORMED_RECEIPT_ERROR = 21002
  SIGNATURE_ERROR = 21003
  PASSWORD_ERROR = 21004
  SERVER_UNAVAILABLE_ERROR = 21005
  EXPIRED_ERROR = 21006
  SANDBOX_ON_PROD_ERROR = 21007
  PROD_ON_SANDBOX_ERROR = 21008

  # A "final" error means that the data is definitely invalid; a non-final
  # error means the validity of the data could not be determined.
  # EXPIRED_ERROR doesn't appear on either list, since it means that the
  # receipt was once valid (and we'll check the expiration date separately).
  # SANDBOX_ON_PROD_ERROR is final because it may indicate tampering (and
  # sandbox receipts are free so there's no harm in throwing them out in
  # the event of a misconfiguration), but PROD_ON_SANDBOX_ERROR is non-final
  # so that if we ever misconfigure the prod servers to talk to the itunes
  # sandbox we'll retry any receipts processed during that time.
  FINAL_ERRORS = set([JSON_ERROR, MALFORMED_RECEIPT_ERROR, SIGNATURE_ERROR,
                     SANDBOX_ON_PROD_ERROR])
  NON_FINAL_ERRORS = set([PASSWORD_ERROR, SERVER_UNAVAILABLE_ERROR,
                         PROD_ON_SANDBOX_ERROR])

  def __init__(self, orig_receipt, response_body):
    self.orig_receipt = orig_receipt
    self.response = json.loads(response_body)

  def GetStatus(self):
    """Returns the verification status code.

    Status is 0 on success, or one of the error codes defined in this class.
    """
    return self.response['status']

  def IsValid(self):
    """Returns True if the receipt is properly formatted and signed.

    Returns False if the receipt is invalid; raises an ITunesStoreError
    if the validity could not be determined and will need to be retried
    later.

    Note that expired receipts are still considered "valid" by this function,
    so the expiration date must be checked separately.
    """
    status = self.GetStatus()
    if status == 0 or status == VerifyResponse.EXPIRED_ERROR:
      if self.GetBundleId() != kViewfinderBundleId:
        logging.warning('got signed receipt for another app: %s', self.GetBundleId())
        return False
      return True
    elif status in VerifyResponse.FINAL_ERRORS:
      return False
    else:
      raise ITunesStoreError('Error verfiying receipt: %r' % status)

  def GetLatestReceiptInfo(self):
    """Returns the latest decoded receipt info as a dict.

    This may be different than the receipt originally passed in if a
    renewal has occurred.
    """
    if 'latest_receipt_info' in self.response:
      return self.response['latest_receipt_info']
    elif 'latest_expired_receipt_info' in self.response:
      return self.response['latest_expired_receipt_info']
    else:
      return self.response['receipt']

  def GetBundleId(self):
    """Returns the bundle id for this subscription.

    Our bundle id is "co.viewfinder.Viewfinder".
    """
    return self.GetLatestReceiptInfo()['bid']

  def GetProductId(self):
    """Returns the product id for this subscription.

    Product ids are created via itunes connect and encapsulate both
    a subscription type and a billing cycle (i.e. if we offered
    50 and 100GB subscriptions and a choice of monthly and yearly
    billing, we'd have four product ids).
    """
    return self.GetLatestReceiptInfo()['product_id']

  def GetTransactionTime(self):
    """Returns the time at which this transaction occurred."""
    time_ms = int(self.GetLatestReceiptInfo()['purchase_date_ms'])
    return float(time_ms) / 1000

  def GetExpirationTime(self):
    """Returns the expiration time of this subscription.

    Result is a python timestamp, i.e. floating-point seconds since 1970.
    """
    expires_ms = int(self.GetLatestReceiptInfo()['expires_date'])
    return float(expires_ms) / 1000

  def IsExpired(self):
    """Returns true if the subscription has expired."""
    return self.GetExpirationTime() < time.time()

  def IsRenewable(self):
    """Returns true if a renewal should be scheduled after expiration."""
    return self.response['status'] == 0

  def GetRenewalData(self):
    """Returns a blob of receipt data to be used when this subscription is
    due for renewal.

    Present only when IsRenewable is true.
    """
    if 'latest_receipt' in self.response:
      return base64.b64decode(self.response['latest_receipt'])
    else:
      return self.orig_receipt

  def GetOriginalTransactionId(self):
    """Returns the original transaction id for a renewing subscription.

    This id is constant for all renewals of a single subscription.
    """
    return self.GetLatestReceiptInfo()['original_transaction_id']

  def GetRenewalTransactionId(self):
    """Returns the transaction id for the most recent renewal transaction.

    Will be equal to self.GetOriginalTransactionId() if no renewals have
    happened yet.
    """
    return self.GetLatestReceiptInfo()['transaction_id']

  def ToString(self):
    return json.dumps(dict(orig_receipt=self.orig_receipt,
                           response=json.dumps(self.response)))

  @classmethod
  def FromString(cls, s):
    data = json.loads(s)
    return cls(data['orig_receipt'], data['response'])


class ITunesStoreClient(object):
  _SETTINGS = {
    'dev': {
      'verify_url': 'https://sandbox.itunes.apple.com/verifyReceipt',
      },
    'prod': {
      'verify_url': 'https://buy.itunes.apple.com/verifyReceipt',
      },
    }

  _instance_map = dict()

  def __init__(self, environment='dev', http_client=None):
    self._settings = ITunesStoreClient._SETTINGS[environment]
    if http_client is None:
      self.http_client = AsyncHTTPClient()
    else:
      self.http_client = http_client

  def VerifyReceipt(self, receipt_data, callback):
    """Verifies a receipt.  Callback receives a VerifyResponse."""
    def _OnFetch(response):
      response.rethrow()
      callback(VerifyResponse(receipt_data, response.body))
    request = {
      'receipt-data': base64.b64encode(receipt_data),
      'password': secrets.GetSecret('itunes_subscription_secret'),
      }
    self.http_client.fetch(self._settings['verify_url'], method='POST',
                           body=json.dumps(request), callback=_OnFetch)

  @staticmethod
  def Instance(environment):
    assert environment in ITunesStoreClient._instance_map, '%s iTunes instance not available' % environment
    return ITunesStoreClient._instance_map[environment]

  @staticmethod
  def SetInstance(environment, itunes_client):
    """Sets a new instance for testing."""
    ITunesStoreClient._instance_map[environment] = itunes_client

  @staticmethod
  def ClearInstance(environment):
    """Removes a previously-set instance."""
    del ITunesStoreClient._instance_map[environment]
