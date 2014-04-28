// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_ASYNC_STATE_H
#define VIEWFINDER_ASYNC_STATE_H

#import <unordered_set>
#import "Callback.h"
#import "Mutex.h"

// The AsyncState class provides a mechanism for scheduling blocks to be run on
// the various dispatch threads with the added ability to "clean up"
// outstanding state synchronously when the AsyncState object is
// destroyed. AsyncState guarantees that when its destructor returns any
// scheduled blocks have either been run, or any reference to them has been
// released causing memory associated with the block to be released. Why is
// this important? Consider the following scenario:
//
//   AsyncState* async = new AsyncState;
//   PhotoHandle p = photo_table->LoadPhoto(<some-photo-id>)
//   async->dispatch_after_low_priority(5, []() { SomePhotoOperation(p); });
//   delete async;
//   delete photo_table;
//
// If AsyncState held references to any scheduled (though un-run) blocks after
// its destructor returned the memory associated with those blocks could be
// released at an arbitrary point in the future. In the above example, the
// block would be deleted after photo_table was deleted causing the deleted
// PhotoHandle to be left referencing garbage memory.
class AsyncState {
  typedef std::unordered_set<AsyncState*> ChildMap;
  typedef Callback<void ()> AsyncBlock;

  class Impl {
    typedef std::unordered_set<AsyncBlock*> BlockMap;

   public:
    Impl();

    // Queue a new async block. If force is true, the operation is queued
    // regardless of whether alive_ is false. Returns the newly queued
    // AsyncBlock structure which should be passed to Run() or NULL if the
    // operation could not be queued.
    AsyncBlock* QueueAsyncBlock(const DispatchBlock& block, bool force = false);

    // Queue an async operation. If force is true, the operation is queued
    // regardless of whether alive_ is false.
    bool Enter(AsyncBlock* block, bool force = false);

    // Mark the async state as dead.
    void Kill();

    // Runs an async operation.
    void Run(AsyncBlock* ab, bool force = false);

    // Start an async operation. The async state destructor blocks until all
    // running operations complete. Returns true if the operation should be
    // started and false if the async state is already in the process of being
    // destroyed.
    bool Start(AsyncBlock* ab, bool force = false);

    // Finish an async operation. Returns true if the async state is still
    // alive and false if the state is in the process of being destroyed.
    bool Finish();

    // Runs the specified block on the main thread. If the current thread is
    // the main thread, the block is run synchronously.
    void dispatch_main(const DispatchBlock& block);

    // Runs the specified block on the main thread. The block is run
    // asynchronously even if the current thread is the main thread.
    void dispatch_main_async(const DispatchBlock& block);

    // Runs the specified block on the network thread. If force is true, the block
    // is run regardless of whether the AsyncState object is being destroyed or
    // not.
    void dispatch_network(bool force, const DispatchBlock& block);

    // Runs the specified block on a background thread at high priority
    void dispatch_high_priority(const DispatchBlock& block);

    // Runs the specified block on a background thread at low priority
    void dispatch_low_priority(const DispatchBlock& block);

    // Runs the specified block on a background thread at background (lower than "low") priority.
    void dispatch_background(const DispatchBlock& block);

    // Runs the specified block on the main/low-priority/background queue after
    // the specified delay (in seconds) has elapsed.
    void dispatch_after_main(double delay, const DispatchBlock& block);
    void dispatch_after_network(double delay, const DispatchBlock& block);
    void dispatch_after_low_priority(double delay, const DispatchBlock& block);
    void dispatch_after_background(double delay, const DispatchBlock& block);

   private:
    Mutex mu_;
    BlockMap blocks_;
    int inflight_;
    int running_;
    bool alive_;
  };

 public:
  AsyncState();
  // Creates a new child async state that will be killed (but not deleted) when
  // the parent async state is killed but can also be independently killed via
  // an explicit delete before the parent is killed. In other words, the child
  // async state has a lifetime that is limited by the lifetime of the parent.
  //
  // Usage: Async operations started by a class (e.g. PhotoStorage) need to be
  // stopped before either the class is deleted or the associated AppState is
  // deleted. PhotoStorage, in particular, presents a peculiar case because it
  // is usually contained within an AppState and therefore presents no
  // problem. But in tests a standalone PhotoStorage is used which is destroyed
  // before the associated AppState. PhotoStorage creates a child AsyncState of
  // AppState::async() so that its async operations are stopped if either the
  // AppState is destroyed or the PhotoStorage is destroyed.
  AsyncState(AsyncState* parent);
  ~AsyncState();

  // Called in conjunction with each other when there is not a
  // discrete block of code to run.
  bool Enter();
  // Returns false if the async state is being destroyed.
  bool Exit();

  // Runs the specified block on the main thread. If the current thread is the
  // main thread, the block is run synchronously.
  void dispatch_main(const DispatchBlock& block) {
    impl_->dispatch_main(block);
  }

  // Runs the specified block on the main thread. The block is run
  // asynchronously even if the current thread is the main thread.
  void dispatch_main_async(const DispatchBlock& block) {
    impl_->dispatch_main_async(block);
  }

  // Runs the specified block on the network queue thread. If force is true, the
  // block is run regardless of whether the AsyncState object is being
  // destroyed or not.
  void dispatch_network(bool force, const DispatchBlock& block) {
    impl_->dispatch_network(force, block);
  }

  // The following three functions share a pool of background threads with a prioritized queue.
  // (the priority in the function names refers to the priority in this queue, not thread scheduling
  // priority).  Guidance on priorities:
  // * High: User-initiated operations.
  // * Low: Background actions that may have user-visible results, like asset scans and day table refreshes.
  // * Background: Mostly-invisible operations, such as garbage collection, or expensive operations like
  //   duplicate queue processing.

  // Run the specified block on a background thread at high priority.
  void dispatch_high_priority(const DispatchBlock& block) {
    impl_->dispatch_high_priority(block);
  }

  // Run the specified block on a background thread at low priority.
  void dispatch_low_priority(const DispatchBlock& block) {
    impl_->dispatch_low_priority(block);
  }

  // Run the specified block on a background thread at background (lower than "low") priority.
  void dispatch_background(const DispatchBlock& block) {
    impl_->dispatch_background(block);
  }

  // Runs the specified block on the main/low-priority/background queue after
  // the specified delay (in seconds) has elapsed.
  void dispatch_after_network(double delay, const DispatchBlock& block) {
    impl_->dispatch_after_network(delay, block);
  }

  void dispatch_after_main(double delay, const DispatchBlock& block) {
    impl_->dispatch_after_main(delay, block);
  }

  void dispatch_after_low_priority(double delay, const DispatchBlock& block) {
    impl_->dispatch_after_low_priority(delay, block);
  }

  void dispatch_after_background(double delay, const DispatchBlock& block) {
    impl_->dispatch_after_background(delay, block);
  }

 protected:
  void Kill();

 protected:
  Impl* impl_;
  AsyncState* parent_;
  ChildMap children_;
};

#endif  // VIEWFINDER_ASYNC_STATE_H
