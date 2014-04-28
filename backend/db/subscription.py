# Copyright 2012 Viewfinder Inc. All Rights Reserved
"""User subscription table.

A subscription is any time-limited modification to a user's privileges,
such as increased storage quota.  Subscriptions may be paid (initially
supporting iOS in-app purchases) or granted for other reasons such as
referring new users.
"""

__author__ = 'ben@emailscrubbed.com (Ben Darnell)'

from copy import deepcopy
import time

from viewfinder.backend.base import util
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.range_base import DBRangeObject
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.services import itunes_store

kITunesPrefix = 'itunes:'

@DBObject.map_table_attributes
class Subscription(DBRangeObject):
  """User subscription data object."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.SUBSCRIPTION)

  # Since our subscriptions are a combination of storage quotas and
  # feature access, give each one its own product type for now.
  _ITUNES_PRODUCTS = {
    # vf_sub1 = "Viewfinder Plus" - cloud storage option and 5GB
    'vf_sub1': dict(product_type='vf_sub1', quantity=5),
    # vf_sub2 = "Viewfinder Pro" - cloud storage, store originals, and 50GB
    'vf_sub2': dict(product_type='vf_sub2', quantity=50),
    }

  _JSON_ATTRIBUTES = set(['transaction_id', 'subscription_id', 'timestamp', 'expiration_ts', 'product_type',
                          'quantity', 'payment_type'])
  """Subset of subscription attributes that are returned to the owning user in query_users."""


  @classmethod
  def _GetITunesProductInfo(cls, verify_response):
    """Maps iTunes product names to Subscription attributes.

    An iTunes "product" also includes information about the billing
    cycle; by convention we name our products with a suffix of "_month"
    or "_year" (etc).
    """
    product_id = verify_response.GetProductId()
    base_product, billing_cycle = product_id.rsplit('_', 1)
    assert billing_cycle in ('month', 'year'), billing_cycle
    return Subscription._ITUNES_PRODUCTS[base_product]

  @classmethod
  def GetITunesTransactionId(cls, verify_response):
    """Returns the transaction id for an iTunes transaction.

    The returned id is usable as a range key for Subscription.Query.
    """
    return kITunesPrefix + verify_response.GetRenewalTransactionId()

  @classmethod
  def GetITunesSubscriptionId(cls, verify_response):
    """Returns the subscription id for an iTunes transaction.

    THe returned id will be the same for all transactions in a series of renewals.
    """
    return kITunesPrefix + verify_response.GetOriginalTransactionId()

  @classmethod
  def CreateFromITunes(cls, user_id, verify_response):
    """Creates a subscription object for an iTunes transaction.

    The verify_response argument is a response from
    viewfinder.backend.services.itunes_store.ITunesStoreClient.VerifyReceipt.

    The new object is returned but not saved to the database.
    """
    assert verify_response.IsValid()
    sub_dict = dict(
      user_id=user_id,
      transaction_id=Subscription.GetITunesTransactionId(verify_response),
      subscription_id=Subscription.GetITunesSubscriptionId(verify_response),
      timestamp=verify_response.GetTransactionTime(),
      expiration_ts=verify_response.GetExpirationTime(),
      payment_type='itunes',
      extra_info=verify_response.GetLatestReceiptInfo(),
      renewal_data=verify_response.GetRenewalData(),
      )
    sub_dict.update(**Subscription._GetITunesProductInfo(verify_response))
    sub = Subscription.CreateFromKeywords(**sub_dict)
    return sub


  @classmethod
  def RecordITunesTransaction(cls, client, callback, user_id, verify_response):
    """Creates a subscription record for an iTunes transaction and saves it to the database.

    The verify_response argument is a response from
    viewfinder.backend.services.itunes_store.ITunesStoreClient.VerifyReceipt.
    """
    sub = Subscription.CreateFromITunes(user_id, verify_response)
    sub.Update(client, callback)

  @classmethod
  def RecordITunesTransactionOperation(cls, client, callback, user_id, verify_response_str):
    def _OnRecord():
      NotificationManager.NotifyRecordSubscription(client, user_id, callback=callback)
    verify_response = itunes_store.VerifyResponse.FromString(verify_response_str)
    assert verify_response.IsValid()
    Subscription.RecordITunesTransaction(client, _OnRecord, user_id, verify_response)

  @classmethod
  def QueryByUser(cls, client, callback, user_id, include_expired=False,
                  include_history=False):
    """Returns a list of Subscription objects for the given user.

    By default only includes currently-active subscriptions, and only
    one transaction per subscription.  To return expired subscriptions,
    pass include_expired=True.  To return all transactions (even those
    superceded by a renewal transaction for the same subscription),
    pass include_history=True (which implies include_expired=True).
    """
    history_results = []
    latest = {}
    def _VisitSub(sub, callback):
      if include_history:
        history_results.append(sub)
      else:
        if sub.expiration_ts < time.time() and not include_expired:
          callback()
          return
        # Only one transaction per subscription.
        if (sub.subscription_id in latest and
            latest[sub.subscription_id].timestamp > sub.timestamp):
          callback()
          return
        latest[sub.subscription_id] = sub
      callback()

    def _OnVisitDone():
      if include_history:
        assert not latest
        callback(history_results)
      else:
        assert not history_results
        callback(latest.values())

    Subscription.VisitRange(client, user_id, None, None, _VisitSub, _OnVisitDone)

  def MakeMetadataDict(self):
    """Project a subset of subscription attributes that can be provided to the user."""
    sub_dict = {}
    for attr_name in Subscription._JSON_ATTRIBUTES:
      util.SetIfNotNone(sub_dict, attr_name, getattr(self, attr_name, None))
    if self.extra_info:
      sub_dict['extra_info'] = deepcopy(self.extra_info)
    return sub_dict
