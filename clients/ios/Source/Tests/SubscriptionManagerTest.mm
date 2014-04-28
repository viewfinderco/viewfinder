// Copyright 2012 Viewfinder. All rights reserved.
// Author: Ben Darnell

#ifdef TESTING

#import "SubscriptionManagerIOS.h"
#import "Testing.h"
#import "TestUtils.h"

namespace {

class SubscriptionManagerTest : public BaseContentTest {
 public:
  SubscriptionManagerTest() {
  }
};


// This test depends on network access, and data
// returned by apple's servers.
TEST_F(SubscriptionManagerTest, TestGetProducts) {
  Barrier* barrier = new Barrier(1);
  state_.subscription_manager_ios()->MaybeLoad(^() {
    barrier->Signal();
  });
  barrier->Wait();
  delete barrier;

  const vector<Product*>& products = state_.subscription_manager_ios()->products();
  for (int i = 0; i < products.size(); ++i) {
    Product* p = products[i];
    const Slice id(p->product_type());
    if (id == "vf_sub1") {
      EXPECT_EQ("Viewfinder Plus", p->title());
    } else if (id == "vf_sub2") {
      EXPECT_EQ("Viewfinder Pro", p->title());
    } else {
      EXPECT(false);
    }
  }
}

TEST_F(SubscriptionManagerTest, TestProcessQueryUsers) {
  state_.SetDeviceId(42);  // Must be set for sub processing to happen
  state_.SetUserId(2);
  QueryUsersResponse resp;
  QueryUsersResponse::User* user;
  ServerSubscriptionMetadata* sub;

  user = resp.add_user();
  user->mutable_contact()->set_user_id(3);
  // The server should never send subscriptions belonging to another user, but in case it
  // ever does SubscriptionManager should ignore them.
  sub = user->add_subscriptions();
  sub->set_transaction_id("itunes:4567");

  user = resp.add_user();
  user->mutable_contact()->set_user_id(2);
  sub = user->add_subscriptions();
  sub->set_transaction_id("itunes:1234");
  sub->set_quantity(1);

  vector<int64_t> user_ids;
  DBHandle updates = state_.NewDBTransaction();
  state_.subscription_manager_ios()->ProcessQueryUsers(resp, user_ids, updates);
  updates->Commit();

  vector<string> keys;
  for (DB::PrefixIterator iter(state_.db(), DBFormat::server_subscription_key(""));
       iter.Valid();
       iter.Next()) {
    keys.push_back(iter.key().as_string());
    ServerSubscriptionMetadata sub_meta;
    EXPECT(sub_meta.ParseFromString(iter.value().as_string()));
    EXPECT_EQ(sub_meta.quantity(), 1);
  }
  EXPECT_EQ(keys, vector<string>(L(DBFormat::server_subscription_key("itunes:1234"))));

  // QueryUsers returns all of a user's current subscriptions, so add a subscription to
  // the previous response.  Also change the previous subscription's quantity to make sure
  // that old subscriptions can be updated (although we currently intend subscriptions
  // to be immutable once written).
  sub->set_quantity(2);
  sub = user->add_subscriptions();
  sub->set_transaction_id("itunes:8912");
  sub->set_quantity(2);

  updates.reset(state_.NewDBTransaction());
  state_.subscription_manager_ios()->ProcessQueryUsers(resp, user_ids, updates);
  updates->Commit();

  keys.clear();
  for (DB::PrefixIterator iter(state_.db(), DBFormat::server_subscription_key(""));
       iter.Valid();
       iter.Next()) {
    keys.push_back(iter.key().as_string());
    ServerSubscriptionMetadata sub_meta;
    EXPECT(sub_meta.ParseFromString(iter.value().as_string()));
    EXPECT_EQ(sub_meta.quantity(), 2);
  }
  EXPECT_EQ(keys, vector<string>(L(DBFormat::server_subscription_key("itunes:1234"),
                                   DBFormat::server_subscription_key("itunes:8912"))));
}

}  // unnamed namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
