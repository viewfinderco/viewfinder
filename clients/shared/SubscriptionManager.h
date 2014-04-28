// Copyright 2012 Viewfinder. All rights reserved.
// Author: Ben Darnell

#ifndef VIEWFINDER_SUBSCRIPTION_MANAGER_H
#define VIEWFINDER_SUBSCRIPTION_MANAGER_H

#import "Server.pb.h"
#import "SubscriptionMetadata.pb.h"
#import "Utils.h"

class SubscriptionManager {
 public:
  struct RecordSubscription {
    OpHeaders headers;
    string receipt_data;
  };

 public:
  virtual ~SubscriptionManager() { }

  // Returns the first queued receipt, or NULL.
  virtual const RecordSubscription* GetQueuedRecordSubscription() = 0;

  // Marks the queued receipt as completed and schedules its callback.
  // Records the metadata returned by the server.
  virtual void CommitQueuedRecordSubscription(
      const ServerSubscriptionMetadata& sub, bool success, const DBHandle& updates) = 0;
};

#endif  // VIEWFINDER_SUBSCRIPTION_MANAGER_H
