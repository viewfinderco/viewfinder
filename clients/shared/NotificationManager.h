// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_NOTIFICATION_MANAGER_H
#define VIEWFINDER_NOTIFICATION_MANAGER_H

#import "Callback.h"
#import "DB.h"
#import "InvalidateMetadata.pb.h"
#import "ScopedPtr.h"
#import "WallTime.h"

class AppState;
class NotificationSelection;
class QueryNotificationsResponse;

class NotificationManager {
 public:
  NotificationManager(AppState* state);
  ~NotificationManager();

  // Application received a remote APNs notification message.
  void RemoteNotification(const string& message);

  // Processes the results of call to query_notifications.  The last
  // query notification key is updated, and if necessary, the
  // low-water mark for notifications with min_required_version set
  // too high for this client to understand. Invokes the callbacks in
  // the ProcessNotificationsCallback set under normal conditions. If
  // a nuclear, all-out invalidation is specified, or if a gap in the
  // notification sequence is detected, internal query state is fully
  // reset and the callbacks in NuclearInvalidationCallback are invoked.
  //
  // If "process" is false, the notification process callbacks are not
  // invoked. This is the case when querying notifications to find the
  // high water mark at the start of rebuilding full asset state.
  void ProcessQueryNotifications(const QueryNotificationsResponse& p,
                                 const NotificationSelection& cs,
                                 bool process, const DBHandle& updates);

  // Validates queried notifications.
  void Validate(const NotificationSelection& s, const DBHandle& updates);

  // Invalidates notification selection so that new notifications are
  // queried. If applicable, augments or creates the
  // NotificationSelection which indicates which notifications are
  // considered invalid due to a server response with
  // min_required_version too high for the client to understand.
  void Invalidate(const DBHandle& updates);

  // Gets the current notification selection. Returns true if the
  // notification selection is invalidated and requires re-querying;
  // false otherwise.
  bool GetInvalidation(NotificationSelection* cs);

  // Callback set for processing query notifications.
  // Used by PhotoManager and ContactManager.
  typedef CallbackSet2<const QueryNotificationsResponse&, const DBHandle&> ProcessNotificationsCallback;
  ProcessNotificationsCallback* process_notifications() { return &process_notifications_; }

  // Callback set for resetting query state.
  // Used by PhotoManager, ContactManager, & NetworkManager.
  typedef CallbackSet1<const DBHandle&> NuclearInvalidationCallback;
  NuclearInvalidationCallback* nuclear_invalidations() { return &nuclear_invalidations_; }

 private:
  void CommonInit();

 private:
  AppState* state_;
  WallTime last_query_time_;
  string query_notifications_last_key_;
  NotificationSelection notification_selection_;
  ProcessNotificationsCallback process_notifications_;
  NuclearInvalidationCallback nuclear_invalidations_;
};

#endif  // VIEWFINDER_NOTIFICATION_MANAGER_H
