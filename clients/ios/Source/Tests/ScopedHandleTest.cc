// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import <thread>
#import "ScopedHandle.h"
#import "Testing.h"

namespace {

TEST(ScopedHandleTest, AtomicRefCount) {
  const int kThreads = 10;
  const int kIterations = 1000;

  AtomicRefCount r;
  AtomicRefCount* r_ptr = &r;
  r.Ref();

  for (int i = 0; i < kThreads; ++i) {
    dispatch_high_priority(^{
        for (int j = 0; j < kIterations; ++j) {
          r_ptr->Ref();
          std::this_thread::yield();
        }
      });
  }

  while (r.val() != kThreads * kIterations + 1) {
    std::this_thread::yield();
  }

  for (int i = 0; i < kThreads; ++i) {
    dispatch_high_priority(^{
        for (int j = 0; j < kIterations; ++j) {
          CHECK(!r_ptr->Unref());
          std::this_thread::yield();
        }
      });
  }

  while (r.val() != 1) {
    std::this_thread::yield();
  }

  CHECK(r.Unref());
}

}  // namespace

#endif  // TESTING
