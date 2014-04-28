// Copyright 2012 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <StoreKit/StoreKit.h>
#import <re2/re2.h>
#import "AsyncState.h"
#import "Callback.h"
#import "ContactManager.h"
#import "CppDelegate.h"
#import "LazyStaticPtr.h"
#import "Logging.h"
#import "ServerUtils.h"
#import "SubscriptionManagerIOS.h"
#import "UIAppState.h"
#import "ValueUtils.h"

namespace {

// Product types
const string kSub1 = "vf_sub1";
const string kSub2 = "vf_sub2";
const string kFreeTier = "free_tier";
const string kBetaBonus = "beta_bonus";

// StoreKit product identifiers, which include both the product type and billing cycle
const string kSub1Month = "vf_sub1_month";
const string kSub2Month = "vf_sub2_month";

LazyStaticPtr<RE2, const char*> kProductTypeRE = { "^(.*)_(month|year)$" };

const DBRegisterKeyIntrospect kLocalSubscriptionKeyIntrospect(
    DBFormat::local_subscription_key(""), NULL, ^(Slice value) {
      return DBIntrospect::FormatProto<LocalSubscriptionMetadata>(value);
    });

const DBRegisterKeyIntrospect kServerSubscriptionKeyIntrospect(
    DBFormat::server_subscription_key(""), NULL, ^(Slice value) {
      return DBIntrospect::FormatProto<ServerSubscriptionMetadata>(value);
    });

void InvokeAndDeleteCallbacks(ScopedPtr<CallbackSet>* callbacks) {
  if (!callbacks->get()) {
    return;
  }
  ScopedPtr<CallbackSet> tmp(callbacks->release());
  tmp->Run();
}

bool IsITunesProduct(const Slice& product_type) {
  return product_type == kSub1 || product_type == kSub2;
}

string GetProductType(const Slice& id) {
  // Server subscriptions report the product type without the _month
  // suffix.  This will change when/if we start to offer multiple billing
  // options for the same product.
  string type, period;
  if (!RE2::FullMatch(id, *kProductTypeRE, &type, &period)) {
    LOG("malformed product id %s", id);
    return "";
  }
  return type;
}

class ITunesProduct : public Product {
 public:
  // SKProducts are loaded indirectly from the SubscriptionManagerIOS because products
  // for existing subscriptions are loaded from the database at startup,
  // but SKProducts aren't loaded from the store until requested.
  ITunesProduct(SubscriptionManagerIOS* sub_mgr, Slice product_type)
      : sub_mgr_(sub_mgr),
        product_type_(product_type.as_string()) {
  }

  virtual string product_type() const {
    return product_type_;
  }

  virtual string title() const {
    return ToString(GetProduct().localizedTitle);
  }

  virtual double price() const {
    return GetProduct().price.doubleValue;
  }

  virtual string price_str() const {
    return FormatPrice(price(), GetProduct().priceLocale);
  }

  virtual int64_t space_bytes() const {
    // Note that space_bytes() is called early to compute a total quota, so
    // it should not depend on anything but product_type().  (this information
    // is not available from the SKProduct anyway).
    const string id = product_type();
    if (id == kSub1) {
      return 5LL << 30;
    } else if (id == kSub2) {
      return 50LL << 30;
    }
    return 0;
  }

  virtual bool has_cloud_storage() const {
    // All our current itunes subscriptions include cloud storage.
    return true;
  }

 private:
  SKProduct* GetProduct() const {
    return sub_mgr_->GetSKProduct(product_type_);
  }

  SubscriptionManagerIOS* sub_mgr_;
  const string product_type_;
};

class ServerProduct : public Product {
 public:
  static Product* Create(SubscriptionManagerIOS* sub, const ServerSubscriptionMetadata& metadata) {
    if (IsITunesProduct(metadata.product_type())) {
      return new ITunesProduct(sub, metadata.product_type());
    } else {
      return new ServerProduct(metadata);
    }
  }

  virtual string product_type() const {
    return metadata_.product_type();
  }

  virtual string title() const {
    const string type = product_type();
    if (type == kBetaBonus) {
      return "Beta bonus";
    }
    return "Unknown";
  }

  virtual double price() const {
    return 0;
  }

  // Server products display "" instead of "Free" since we don't know whether they were paid for by other means.
  virtual string price_str() const {
    return "";
  }

  virtual int64_t space_bytes() const {
    return metadata_.quantity() * (1LL << 30);
  }

  virtual bool has_cloud_storage() const {
    // Assume for now that any new subscription products we create will include cloud storage permissions.
    return true;
  }

 private:
  explicit ServerProduct(const ServerSubscriptionMetadata& metadata)
      : metadata_(metadata) {
  }

  const ServerSubscriptionMetadata metadata_;
};

class FreeTierProduct : public Product {
 public:
  virtual string product_type() const {
    return kFreeTier;
  }
  virtual string title() const {
    return "Organize and Share Photos";
  }
  virtual double price() const {
    return 0;
  }
  virtual string price_str() const {
    return "Free";
  }
  virtual int64_t space_bytes() const {
    return 1LL << 30;
  }

  virtual bool has_cloud_storage() const {
    return false;
  }
};

}  // namespace

string Product::FormatPrice(double value, NSLocale* locale) {
  if (value == 0) {
    return "Free";
  }
  NSNumberFormatter* fmt = [NSNumberFormatter new];
  fmt.formatterBehavior = NSNumberFormatterBehavior10_4;
  fmt.locale = locale;
  fmt.numberStyle = NSNumberFormatterCurrencyStyle;
  return Format("%s / month", [fmt stringFromNumber:[NSNumber numberWithDouble:value]]);
}

SubscriptionManagerIOS::SubscriptionManagerIOS(UIAppState* state)
    : state_(state),
      products_(NULL),
      transaction_observer_(NULL),
      purchase_callback_(NULL) {
  AddSubscription(new FreeTierProduct);
  InitFromDB();

  state_->contact_manager()->process_users()->Add(
      [this](const QueryUsersResponse& r,
             const vector<int64_t>& user_ids,
             const DBHandle& updates) {
        ProcessQueryUsers(r, user_ids, updates);
      });
}

SubscriptionManagerIOS::~SubscriptionManagerIOS() {
  Clear(&products_);
  Clear(&subscriptions_);
}

void SubscriptionManagerIOS::InitFromDB() {
  for (DB::PrefixIterator iter(state_->db(), DBFormat::local_subscription_key(""));
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const Slice value = iter.value();
    LocalSubscriptionMetadata m;
    if (!m.ParseFromArray(value.data(), value.size())) {
      LOG("subscription: unable to parse local subscription metadata: %s", key);
      continue;
    }
    VLOG("local subscription: %s: %s",
        WallTimeFormat("%F %T", m.timestamp()), m.product());
    local_subscriptions_.push_back(m);

    if (!m.recorded()) {
      string key_copy = key.as_string();
      QueueReceipt(NewNSData(m.receipt()), ^{
          MarkRecorded(key_copy);
        });
    }
  }
  for (DB::PrefixIterator iter(state_->db(), DBFormat::server_subscription_key(""));
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const Slice value = iter.value();
    ServerSubscriptionMetadata m;
    if (!m.ParseFromArray(value.data(), value.size())) {
      LOG("subscription: unable to parse server subscription metadata: %s", key);
      continue;
    }
    VLOG("server subscription: %s: %s",
        WallTimeFormat("%F %T", m.timestamp()), m.product_type());
    AddSubscription(ServerProduct::Create(this, m));
  }
}

void SubscriptionManagerIOS::MaybeLoad(void (^completion)()) {
  if (!products_.empty() || load_callbacks_.get()) {
    if (completion) {
      if (load_callbacks_.get()) {
        load_callbacks_->Add(completion);
      } else {
        state_->async()->dispatch_after_main(0, completion);
      }
    }
    return;
  }
  load_callbacks_.reset(new CallbackSet);
  if (completion) {
    load_callbacks_->Add(completion);
  }

  const Set products(kSub1Month, kSub2Month);
  SKProductsRequest* request =
      [[SKProductsRequest alloc] initWithProductIdentifiers:products];

  CppDelegate* cpp_delegate = new CppDelegate;
  cpp_delegate->Add(
      @protocol(SKProductsRequestDelegate), @selector(productsRequest:didReceiveResponse:),
      ^(SKProductsRequest* request, SKProductsResponse* response) {
        LOG("subscription: did receive response: %d", response.products.count);
        for (SKProduct* p in response.products) {
          const string product_type(GetProductType(ToSlice(p.productIdentifier)));
          products_.push_back(new ITunesProduct(this, product_type));
          sk_products_[product_type] = p;
        }
        // We'll be getting a requestDidFinish immediately after this,
        // so we can't deallocate the CppDelegate until then.
        // Run the callbacks then too, so we don't have problems in tests where the
        // SubscriptionManagerIOS is deleted while the CppDelegate has outstanding callbacks.
      });

  cpp_delegate->Add(
      @protocol(SKProductsRequestDelegate), @selector(request:didFailWithError:),
      ^(SKProductsRequest* request, NSError* error) {
        LOG("subscription: error getting product data from store: %@", error);
        InvokeAndDeleteCallbacks(&load_callbacks_);
        request.delegate = NULL;
        delete cpp_delegate;
      });

  cpp_delegate->Add(
      @protocol(SKProductsRequestDelegate), @selector(requestDidFinish:),
      ^(SKProductsRequest* request) {
        LOG("subscription: request did finish");
        InvokeAndDeleteCallbacks(&load_callbacks_);
        request.delegate = NULL;
        delete cpp_delegate;
      });

  request.delegate = cpp_delegate->delegate();
  [request start];
}

void SubscriptionManagerIOS::PurchaseProduct(SKProduct* product, PurchaseCallback callback) {
  if (purchase_callback_) {
    DIE("subscription: purchase already in progress");
  }
  purchase_callback_ = callback;
  in_flight_purchases_.insert(GetProductType(ToSlice(product.productIdentifier)));

  InstallTransactionObserver();
  SKPayment* payment = [SKPayment paymentWithProduct:product];
  SKPaymentQueue* queue = [SKPaymentQueue defaultQueue];
  [queue addPayment:payment];
}

bool SubscriptionManagerIOS::HasSubscription(const Slice& product_type) {
  for (int i = 0; i < subscriptions_.size(); ++i) {
    if (product_type == subscriptions_[i]->product_type()) {
      return true;
    }
  }
  return false;
}

bool SubscriptionManagerIOS::HasCloudStorage() {
#ifdef DEVELOPMENT
  // Dev builds have cloud storage enabled so we can turn it on in unit tests.
  return true;
#else
  for (int i = 0; i < subscriptions_.size(); ++i) {
    if (subscriptions_[i]->has_cloud_storage()) {
      return true;
    }
  }
  return false;
#endif
}

bool SubscriptionManagerIOS::HasPendingSubscription(const Slice& product_type) {
  if (ContainsKey(in_flight_purchases_, product_type.as_string())) {
    return true;
  }
  for (int i = 0; i < local_subscriptions_.size(); ++i) {
    if (product_type == GetProductType(local_subscriptions_[i].product())) {
      return true;
    }
  }
  return false;
}

void SubscriptionManagerIOS::QueueReceipt(NSData* receipt, void (^callback)()) {
  MutexLock lock(&queue_lock_);
  queued_receipts_.push_back(std::make_pair(ToString(receipt), callback));
}

const SubscriptionManagerIOS::RecordSubscription* SubscriptionManagerIOS::GetQueuedRecordSubscription() {
  MutexLock lock(&queue_lock_);
  if (!queued_record_.get() & !queued_receipts_.empty()) {
    queued_record_.reset(new RecordSubscription);
    queued_record_->headers.set_op_id(state_->NewLocalOperationId());
    queued_record_->headers.set_op_timestamp(WallTime_Now());
    queued_record_->receipt_data = queued_receipts_.front().first;
  }
  return queued_record_.get();
}

void SubscriptionManagerIOS::CommitQueuedRecordSubscription(const ServerSubscriptionMetadata& sub,
                                                         bool success, const DBHandle& updates) {
  MutexLock lock(&queue_lock_);
  if (!queued_record_.get()) {
    LOG("subscription: commit failed: no record subscription queued");
    return;
  }
  CHECK_EQ(queued_record_->receipt_data, queued_receipts_.front().first);
  void (^callback)() = queued_receipts_.front().second;
  queued_receipts_.pop_front();
  queued_record_.reset(NULL);

  if (!success) {
    LOG("subscription: got 4xx error from server; won't retry this session");
    return;
  }

  LOG("subscription: received transaction %s from the server (record_subscription)", sub.transaction_id());
  const string key(DBFormat::server_subscription_key(sub.transaction_id()));
  updates->PutProto(key, sub);
  AddSubscription(ServerProduct::Create(this, sub));

  updates->AddCommitTrigger(Format("SubscriptionManagerIOS::CommitQueuedRecordSubscription(%s)", key), ^{
      dispatch_main(callback);
    });
}

void SubscriptionManagerIOS::ProcessQueryUsers(const QueryUsersResponse& r, const vector<int64_t>& user_ids,
                                            const DBHandle& updates) {
  for (int i = 0; i < r.user_size(); ++i) {
    const QueryUsersResponse::User& u = r.user(i);
    if (state_->is_registered() && u.contact().user_id() == state_->user_id()) {
      for (int j = 0; j < u.subscriptions_size(); ++j) {
        const ServerSubscriptionMetadata& sub = u.subscriptions(j);
        if (!sub.has_transaction_id() || sub.transaction_id().empty()) {
          VLOG("got subscription with no transaction id: %s", sub);
          continue;
        }
        const string key(DBFormat::server_subscription_key(sub.transaction_id()));
        LOG("subscription: received transaction %s from the server (query_users)", sub.transaction_id());
        updates->PutProto(key, sub);
        AddSubscription(ServerProduct::Create(this, sub));
        changed_.Run();
      }
    }
  }
}

SKProduct* SubscriptionManagerIOS::GetSKProduct(const Slice& product_type) const {
  return FindOrNull(sk_products_, product_type.as_string());
}

NSLocale* SubscriptionManagerIOS::price_locale() const {
  if (sk_products_.empty()) {
    // Fall back in case we don't have any information from the app store.
    return [NSLocale currentLocale];
  }
  // All products should be priced in the same currency, so just pick the first one.
  // (if this ever changes we'll need to change the "total cost" section in settings)
  return sk_products_.begin()->second.priceLocale;
}

void SubscriptionManagerIOS::InstallTransactionObserver() {
  if (transaction_observer_) {
    return;
  }

  transaction_observer_ = new CppDelegate;
  transaction_observer_->Add(
      @protocol(SKPaymentTransactionObserver), @selector(paymentQueue:updatedTransactions:),
      ^(SKPaymentQueue* queue, NSArray* transactions) {
        UpdateTransactions(queue, transactions);
      });
  [[SKPaymentQueue defaultQueue] addTransactionObserver:transaction_observer_->delegate()];
}

void SubscriptionManagerIOS::UpdateTransactions(SKPaymentQueue* queue, NSArray* transactions) {
  // TODO: handle multiple transactions at a time (should only happen when
  // we add "restore purchases" support).
  for (SKPaymentTransaction* txn in transactions) {
    if (txn.transactionState == SKPaymentTransactionStatePurchased) {
      // It worked.
      LOG("subscription: transaction completed: %s %s",
          txn.payment.productIdentifier, txn.transactionDate);
      in_flight_purchases_.erase(GetProductType(ToSlice(txn.payment.productIdentifier)));

      LocalSubscriptionMetadata m;
      m.set_product(ToString(txn.payment.productIdentifier));
      m.set_timestamp([txn.transactionDate timeIntervalSince1970]);
      m.set_receipt(ToString(txn.transactionReceipt));
      const string key = DBFormat::local_subscription_key(
          ToString(txn.transactionIdentifier));
      state_->db()->PutProto(key, m);
      local_subscriptions_.push_back(m);
      changed_.Run();

      QueueReceipt(txn.transactionReceipt, ^{
          MarkRecorded(ToString(key));
          [queue finishTransaction:txn];
          RunPurchaseCallback(kPurchaseSuccess);
        });
    } else if (txn.transactionState == SKPaymentTransactionStateFailed) {
      // Something went wrong; alert the caller and mark the transaction
      // as finished.

      LOG("subscription: purchase error: %@", txn.error);
      in_flight_purchases_.erase(GetProductType(ToSlice(txn.payment.productIdentifier)));
      PurchaseStatus status = kPurchaseFailure;
      if ([txn.error.domain isEqualToString:SKErrorDomain] &&
          txn.error.code == SKErrorPaymentCancelled) {
        status = kPurchaseCancel;

      // On the simulator, let cancellation initialize the subscription locally
      // (in memory only) to ease development of the subscription UI.
#if 1 && TARGET_IPHONE_SIMULATOR
        LocalSubscriptionMetadata m;
        m.set_product(ToString(txn.payment.productIdentifier));
        m.set_timestamp([txn.transactionDate timeIntervalSince1970]);
        m.set_receipt(ToString(txn.transactionReceipt));
        const string key = DBFormat::local_subscription_key(
            ToString(txn.transactionIdentifier));
        local_subscriptions_.push_back(m);
        changed_.Run();
        status = kPurchaseSuccess;
        // For further testing, send the transaction to the server (although
        // since the request was cancelled, the receipt is invalid).  For
        // end-to-end testing modify the server to return a successful
        // subscription on an invalid receipt.
        //QueueReceipt(txn.transactionReceipt, ^{
        //    MarkRecorded(ToString(key));
        //    [queue finishTransaction:txn];
        //    RunPurchaseCallback(kPurchaseSuccess);
        //  });
        return;
#endif  // TARGET_IPHONE_SIMULATOR
      } else {
        // TODO: Do we need this or does StoreKit handle all necessary error
        // reporting?  Should we display the NSError's message to the user?
        [[[UIAlertView alloc]
           initWithTitle:@"Purchase Error"
                 message:@"Your purchase failed. Try again."
                delegate:NULL
           cancelButtonTitle:@"OK"
           otherButtonTitles:NULL] show];
      }
      [queue finishTransaction:txn];
      RunPurchaseCallback(status);
    }
  }
}

void SubscriptionManagerIOS::RunPurchaseCallback(PurchaseStatus status) {
  PurchaseCallback callback = purchase_callback_;
  purchase_callback_ = NULL;
  if (callback) {
    callback(status);
  }
}

void SubscriptionManagerIOS::MarkRecorded(const string& transaction_key) {
  LocalSubscriptionMetadata m;
  if (!state_->db()->GetProto(transaction_key, &m)) {
    LOG("Transaction %s not found in DB", transaction_key);
    return;
  }
  m.set_recorded(true);
  state_->db()->PutProto(transaction_key, m);
  changed_.Run();
}

void SubscriptionManagerIOS::AddSubscription(Product* product) {
  if (HasSubscription(product->product_type())) {
    delete product;
  } else {
    subscriptions_.push_back(product);
  }
}

// local variables:
// mode: c++
// end:
