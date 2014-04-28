// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "AppState.h"
#import "DB.h"
#import "Logging.h"
#import "NetworkManager.h"
#import "NotificationManager.h"
#import "Server.pb.h"
#import "StringUtils.h"

namespace {

const string kNotificationSelectionKey =
    DBFormat::metadata_key("notification_selection");

const DBRegisterKeyIntrospect kNotificationSelectionKeyIntrospect(
    kNotificationSelectionKey, NULL, [](Slice value) {
      return DBIntrospect::FormatProto<NotificationSelection>(value);
    });

}  // namespace


NotificationManager::NotificationManager(AppState* state)
    : state_(state) {
  CommonInit();
}

NotificationManager::~NotificationManager() {
}

void NotificationManager::RemoteNotification(const string& message) {
  DBHandle updates = state_->NewDBTransaction();
  Invalidate(updates);
  updates->Commit();

  state_->net_manager()->ResetBackoff();
  state_->net_manager()->Dispatch();
}

void NotificationManager::ProcessQueryNotifications(const QueryNotificationsResponse& p,
                                                    const NotificationSelection& ns,
                                                    bool process, const DBHandle& updates) {
  last_query_time_ = WallTime_Now();

  Validate(ns, updates);

  // A "nuclear" invalidation happens when the last key is cleared in
  // the notification selection. This can happen from an invalidate
  // all request or a missing notification sequence number.
  if (!ns.query_done() && ns.last_key().empty()) {
    LOG("notification: initiating nuclear invalidation of all assets");
    nuclear_invalidations_.Run(updates);
  } else if (process) {
    process_notifications_.Run(p, updates);
  }
}

void NotificationManager::Validate(const NotificationSelection& ns, const DBHandle& updates) {
  NotificationSelection existing;
  updates->GetProto(kNotificationSelectionKey, &existing);
  if (ns.has_last_key()) {
    existing.set_last_key(ns.last_key());
  }
  if (ns.has_query_done()) {
    existing.set_query_done(ns.query_done());
  }

  // Track the low-water mark for notifications which arrive with a
  // min-required-version which this client doesn't understand.
  if (ns.has_max_min_required_version() &&
      ns.max_min_required_version() > existing.max_min_required_version()) {
    existing.set_max_min_required_version(ns.max_min_required_version());
  }
  if (ns.has_low_water_notification_id() &&
      ns.low_water_notification_id() <= existing.low_water_notification_id()) {
    existing.set_low_water_notification_id(ns.low_water_notification_id());
  }

  // Handle low water notification id and max min_required version in
  // case of a nuclear invalidation.
  if (!ns.query_done() && ns.last_key().empty()) {
    // If the server is insisting on a min required version this
    // client doesn't understand, the low-water mark on a nuclear
    // invalidation must reset to the very beginning.
    if (existing.max_min_required_version() > state_->protocol_version()) {
      existing.set_low_water_notification_id(0);
    }
  }
  updates->PutProto(kNotificationSelectionKey, existing);
}

void NotificationManager::Invalidate(const DBHandle& updates) {
  NotificationSelection existing;
  updates->GetProto(kNotificationSelectionKey, &existing);
  existing.clear_query_done();
  updates->PutProto(kNotificationSelectionKey, existing);
}

bool NotificationManager::GetInvalidation(NotificationSelection* ns) {
  if (!state_->db()->GetProto(kNotificationSelectionKey, ns)) {
    LOG("notification: WARNING, notification selection missing");
    CommonInit();
    state_->db()->GetProto(kNotificationSelectionKey, ns);
  }
  // If "query_done" is false, we're ready to query invalidations.
  return !ns->query_done();
}

void NotificationManager::CommonInit() {
  last_query_time_ = 0;

  // Query the notification selection in case this client is finally
  // new enough to understand past notifications. If so, update last key
  // and clear the max_min_required_version and low_water_notification_id.
  NotificationSelection ns;
  if (state_->db()->GetProto(kNotificationSelectionKey, &ns)) {
    if (ns.has_max_min_required_version() &&
        ns.max_min_required_version() <= state_->protocol_version()) {
      if (!ns.low_water_notification_id()) {
        ns.set_last_key("");
      } else {
        ns.set_last_key(ToString(ns.low_water_notification_id()));
      }
      ns.clear_low_water_notification_id();
      ns.clear_max_min_required_version();
    }
    ns.clear_query_done();
    state_->db()->PutProto(kNotificationSelectionKey, ns);
  } else {
    ns.Clear();
    ns.clear_query_done();
    ns.set_last_key("");
    state_->db()->PutProto(kNotificationSelectionKey, ns);
  }
}

// local variables:
// mode: c++
// end:
