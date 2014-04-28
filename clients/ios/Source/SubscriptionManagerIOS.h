// Copyright 2012 Viewfinder. All rights reserved.
// Author: Ben Darnell

#ifndef VIEWFINDER_SUBSCRIPTION_MANAGER_IOS_H
#define VIEWFINDER_SUBSCRIPTION_MANAGER_IOS_H

#import <deque>
#import <map>
#import <set>
#import <StoreKit/SKProduct.h>
#import <StoreKit/SKPaymentQueue.h>
#import "Callback.h"
#import "DB.h"
#import "Mutex.h"
#import "ScopedPtr.h"
#import "SubscriptionManager.h"
#import "Utils.h"

class CppDelegate;
class QueryUsersResponse;
class UIAppState;

// A Product can represent either a current subscription or one available for
// purchase.  Note that access to most fields of Product requires that
// SubscriptionManagerIOS::MaybeLoad has completed.
class Product {
 public:
  virtual ~Product() {};

  virtual string product_type() const = 0;
  virtual string title() const = 0;
  // price() returns 0 for non-iTunes subscriptions.
  virtual double price() const = 0;
  // price_str() will return "Free" for completely free products or an empty string for non-iTunes products.
  virtual string price_str() const = 0;
  virtual int64_t space_bytes() const = 0;

  // True if this product confers the cloud storage permission.
  virtual bool has_cloud_storage() const = 0;

  // Returns a string like "$1.99 / month", or "Free".
  static string FormatPrice(double value, NSLocale* locale);
};

// SubscriptionManagerIOS uses StoreKit to manage in-app purchases.
// It is a singleton because it interacts with the global SKPaymentQueue.
class SubscriptionManagerIOS : public SubscriptionManager {
 public:
  SubscriptionManagerIOS(UIAppState* state);
  virtual ~SubscriptionManagerIOS();

  // Initiate loading of the products and invoke completion when the loading is
  // done. The products are only loaded once per app run, but completion will
  // always be called even if the products have already been loaded.
  void MaybeLoad(void (^completion)());

  enum PurchaseStatus {
    kPurchaseSuccess,
    kPurchaseFailure,
    kPurchaseCancel,
  };
  typedef void (^PurchaseCallback)(PurchaseStatus);

  // Initiates a purchase of `product`.  The iTunes store will take over
  // the UI to prompt the user for confirmation, authentication, etc.
  // The callback will be invoked when this operation is complete.
  void PurchaseProduct(SKProduct* product, PurchaseCallback callback);

  // Returns true if the user has a subscription to the specified product.
  bool HasSubscription(const Slice& product_type);

  // Returns true if the user has permission to use the cloud storage feature.
  bool HasCloudStorage();

  // Returns true if a subscription for this product has been initiated,
  // even if it hasn't completed yet.
  bool HasPendingSubscription(const Slice& product_type);

  // Adds a receipt (SKPaymentTransaction.transactionReceipt) to the queue,
  // and runs the given block when it has been submitted to the server.
  // For internal/testing use only.
  void QueueReceipt(NSData* receipt, void (^callback)());

  // Returns the first queued receipt, or NULL.
  virtual const RecordSubscription* GetQueuedRecordSubscription();

  // Marks the queued receipt as completed and schedules its callback.
  // Records the metadata returned by the server.
  virtual void CommitQueuedRecordSubscription(
      const ServerSubscriptionMetadata& sub, bool success, const DBHandle& updates);

  void ProcessQueryUsers(
      const QueryUsersResponse& r,
      const vector<int64_t>& user_ids, const DBHandle& updates);

  CallbackSet* changed() { return &changed_; }
  bool loading() const { return load_callbacks_.get(); }
  const vector<Product*>& products() const { return products_; }
  const vector<Product*>& subscriptions() const {
    return subscriptions_;
  }

  SKProduct* GetSKProduct(const Slice& product_type) const;

  // Returns the locale to be used for displaying prices.
  NSLocale* price_locale() const;

  // Internal/testing use only.
  void InitFromDB();

 private:
  // Must be called before making a purchase or restoring purchases;
  // may be called more than once.
  void InstallTransactionObserver();

  // Called via the transaction observer.  `transactions` is an
  // array of SKPaymentTransaction*.
  void UpdateTransactions(SKPaymentQueue* queue, NSArray* transactions);
  void RunPurchaseCallback(PurchaseStatus status);

  // Mark the given transaction as recorded in the database.
  // transaction_key is given by DBFormat::subscription_key(transactionIdentifier).
  void MarkRecorded(const string& transaction_key);

  // Add a product to subscription_ if no equivalent product is already present.
  // Product must be heap-allocated and may be deleted if it is redundant.
  void AddSubscription(Product* product);

  // Disallow evil constructors.
  SubscriptionManagerIOS(const SubscriptionManagerIOS&);
  void operator=(const SubscriptionManagerIOS&);

 private:
  UIAppState* const state_;
  CallbackSet changed_;
  vector<Product*> products_;
  std::set<string> in_flight_purchases_;
  vector<LocalSubscriptionMetadata> local_subscriptions_;
  vector<Product*> subscriptions_;
  std::map<string, SKProduct*> sk_products_;
  ScopedPtr<CallbackSet> load_callbacks_;
  CppDelegate* transaction_observer_;
  PurchaseCallback purchase_callback_;

  Mutex queue_lock_;
  std::deque<std::pair<string, void(^)()> > queued_receipts_;
  ScopedPtr<RecordSubscription> queued_record_;
};

#endif  // VIEWFINDER_SUBSCRIPTION_MANAGER_IOS_H
