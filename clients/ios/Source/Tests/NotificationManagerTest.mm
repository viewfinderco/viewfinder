// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifdef TESTING

#import "InvalidateMetadata.pb.h"
#import "NotificationManager.h"
#import "Server.pb.h"
#import "Testing.h"
#import "TestUtils.h"

namespace {

class NotificationManagerTest : public Test {
 public:
  NotificationManagerTest()
      : state_(dir()) {
  }

  void Invalidate() {
    DBHandle updates = state_.NewDBTransaction();
    notification_manager()->Invalidate(updates);
    updates->Commit();
  }

  void Validate(const NotificationSelection& ns) {
    DBHandle updates = state_.NewDBTransaction();
    notification_manager()->Validate(ns, updates);
    updates->Commit();
  }

  // Returns a current invalidation start key.
  string GetInvalidation() {
    NotificationSelection ns;
    EXPECT(notification_manager()->GetInvalidation(&ns));
    string str = ns.last_key();
    if (ns.has_max_min_required_version()) {
      str.append(Format(", mmrv: %d", ns.max_min_required_version()));
    }
    if (ns.has_low_water_notification_id()) {
      str.append(Format(", lwni: %d", ns.low_water_notification_id()));
    }
    return str;
  }

  bool HasInvalidation() {
    NotificationSelection ns;
    return notification_manager()->GetInvalidation(&ns);
  }

  // Processes the specified query notification response protobuf.
  void ProcessQueryNotifications(const QueryNotificationsResponse& r,
                                 const NotificationSelection& ns,
                                 bool process = true) {
    DBHandle updates = state_.NewDBTransaction();
    notification_manager()->ProcessQueryNotifications(r, ns, process, updates);
    updates->Commit();
  }

  void AddProcessCallback(void (^cb)(const QueryNotificationsResponse&, const DBHandle&)) {
    notification_manager()->process_notifications()->Add(cb);
  }

  void AddNuclearCallback(void (^cb)(const DBHandle&)) {
    notification_manager()->nuclear_invalidations()->Add(cb);
  }

  const DBHandle& db() {
    return state_.db();
  }
  NotificationManager* notification_manager() {
    return state_.notification_manager();
  }

 private:
  TestUIAppState state_;
};

// Verify validation & invalidation.
TEST_F(NotificationManagerTest, Invalidation) {
  // Starts invalidated.
  EXPECT_EQ("", GetInvalidation());
  // Another invalidate is idempotent.
  Invalidate();
  EXPECT_EQ("", GetInvalidation());

  // Validate, as in the case of processing query notifications.
  NotificationSelection ns;
  ns.set_last_key("1");
  ns.set_query_done(false);
  Validate(ns);
  EXPECT_EQ("1", GetInvalidation());

  ns.set_query_done(true);
  Validate(ns);
  EXPECT(!HasInvalidation());

  // A new invalidation.
  Invalidate();
  EXPECT_EQ("1", GetInvalidation());
  ns.set_last_key("10");
  ns.set_query_done(true);
  Validate(ns);
  EXPECT(!HasInvalidation());

  Invalidate();
  EXPECT_EQ("10", GetInvalidation());
}

// Verify min-required-version validations.
TEST_F(NotificationManagerTest, MinRequiredVersionValidations) {
  NotificationSelection ns;
  ns.set_last_key("1");
  ns.set_query_done(false);
  ns.set_max_min_required_version(1000);
  ns.set_low_water_notification_id(0);
  Validate(ns);
  EXPECT_EQ("1, mmrv: 1000, lwni: 0", GetInvalidation());

  // On second query, we don't update the low-water mark.
  ns.set_last_key("2");
  ns.set_query_done(false);
  ns.set_max_min_required_version(1000);
  ns.set_low_water_notification_id(1);
  Validate(ns);
  EXPECT_EQ("2, mmrv: 1000, lwni: 0", GetInvalidation());

  // Increment min required version by 1.
  ns.set_last_key("5");
  ns.set_query_done(false);
  ns.set_max_min_required_version(1001);
  ns.set_low_water_notification_id(2);
  Validate(ns);
  EXPECT_EQ("5, mmrv: 1001, lwni: 0", GetInvalidation());

  ns.set_query_done(true);
  Validate(ns);
  EXPECT(!HasInvalidation());

  ns.set_last_key("6");
  ns.set_query_done(false);
  ns.set_max_min_required_version(1001);
  ns.set_low_water_notification_id(5);
  Validate(ns);
  EXPECT_EQ("6, mmrv: 1001, lwni: 0", GetInvalidation());
}

// Verify nuclear invalidation.
TEST_F(NotificationManagerTest, NuclearInvalidation) {
  NotificationSelection ns;
  ns.set_last_key("10");
  ns.set_query_done(true);
  Validate(ns);
  EXPECT(!HasInvalidation());

  ns.set_last_key("");
  ns.set_query_done(false);
  Validate(ns);
  EXPECT_EQ("", GetInvalidation());

  ns.set_last_key("11");
  ns.set_query_done(true);
  ns.set_max_min_required_version(1000);
  ns.set_low_water_notification_id(10);
  Validate(ns);

  ns.Clear();
  ns.set_last_key("");
  ns.set_query_done(false);
  Validate(ns);
  EXPECT_EQ(", mmrv: 1000, lwni: 0", GetInvalidation());
}

// Verify firing of process query callbacks.
TEST_F(NotificationManagerTest, ProcessCallbacks) {
  __block bool process1 = false;
  __block bool process2 = false;

  AddProcessCallback(^(const QueryNotificationsResponse& p, const DBHandle& updates) {
      EXPECT_EQ(2, p.notifications_size());
      process1 = true;
    });
  AddProcessCallback(^(const QueryNotificationsResponse& p, const DBHandle& updates) {
      EXPECT_EQ(2, p.notifications_size());
      process2 = true;
    });

  NotificationSelection ns;
  ns.set_last_key("2");
  ns.set_query_done(true);

  QueryNotificationsResponse r;
  r.add_notifications()->set_notification_id(1);
  r.add_notifications()->set_notification_id(2);
  ProcessQueryNotifications(r, ns, false /* process */);
  EXPECT_EQ(false, process1);
  EXPECT_EQ(false, process2);

  ProcessQueryNotifications(r, ns, true /* process */);
  EXPECT_EQ(true, process1);
  EXPECT_EQ(true, process2);
}

// Verify firing of nuclear invalidation callbacks.
TEST_F(NotificationManagerTest, NuclearCallbacks) {
  __block bool nuclear1 = false;
  __block bool nuclear2 = false;

  AddNuclearCallback(^(const DBHandle& updates) {
      nuclear1 = true;
    });
  AddNuclearCallback(^(const DBHandle& updates) {
      nuclear2 = true;
    });

  NotificationSelection ns;
  ns.set_last_key("");
  ns.set_query_done(false);

  QueryNotificationsResponse r;
  ProcessQueryNotifications(r, ns, true);
  EXPECT_EQ(true, nuclear1);
  EXPECT_EQ(true, nuclear2);
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
