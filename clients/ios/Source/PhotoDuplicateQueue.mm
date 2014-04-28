// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AsyncState.h"
#import "PhotoDuplicateQueue.h"
#import "PhotoTable.h"
#import "ProcessDuplicateQueueOp.h"
#import "UIAppState.h"

PhotoDuplicateQueue::PhotoDuplicateQueue(UIAppState* state)
    : state_(state),
      inflight_(false) {
  state_->assets_scan_end()->Add(^(const StringSet* not_found) {
      // [AssetsManager scanning] is still true at this point. Wait a second
      // before attempting to process the duplicate queue.
      state_->async()->dispatch_after_low_priority(1, ^{
          MaybeProcess();
        });
    });
}

PhotoDuplicateQueue::~PhotoDuplicateQueue() {
}

void PhotoDuplicateQueue::MaybeProcess() {
  MutexLock l(&mu_);
  bg_task_.Start();
  MaybeProcessLocked();
}

void PhotoDuplicateQueue::MaybeProcessLocked() {
  if (inflight_ || state_->assets_scanning()) {
    return;
  }

  for (DB::PrefixIterator iter(state_->db(), PhotoTable::kPhotoDuplicateQueueKeyPrefix);
       iter.Valid();
       iter.Next()) {
    int64_t local_id;
    if (!DecodePhotoDuplicateQueueKey(iter.key(), &local_id)) {
      state_->db()->Delete(iter.key());
      continue;
    }

    inflight_ = true;
    state_->async()->dispatch_background(^{
        ProcessDuplicateQueueOp::New(
            state_, local_id, ^{
              MutexLock l(&mu_);
              inflight_ = false;
              MaybeProcessLocked();
            });
      });
    return;
  }
  bg_task_.Stop();
}

void PhotoDuplicateQueue::Drain() {
  MutexLock l(&mu_);
  mu_.Wait(^{
      return !inflight_;
    });
}

// local variables:
// mode: c++
// end:
