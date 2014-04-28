// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AsyncState.h"
#import "Utils.h"

AsyncState::Impl::Impl()
    : inflight_(0),
      running_(0),
      alive_(true) {
}

AsyncState::AsyncBlock* AsyncState::Impl::QueueAsyncBlock(
    const DispatchBlock& block, bool force) {
  AsyncBlock* ab = new AsyncBlock(block);
  if (Enter(ab, force)) {
    return ab;
  }
  delete ab;
  return NULL;
}

bool AsyncState::Impl::Enter(AsyncBlock* ab, bool force) {
  MutexLock l(&mu_);
  if (!force && !alive_) {
    return false;
  }
  ++inflight_;
  if (ab) {
    blocks_.insert(ab);
  }
  return true;
}

void AsyncState::Impl::Kill() {
  mu_.Lock();
  // Set alive to false to prevent new ops from entering the running state.
  alive_ = false;
  // Bump the inflight count to prevent deletion while we're waiting for the
  // running ops to finish.
  ++inflight_;
  mu_.Wait([this] {
      return running_ == 0;
    });
  CHECK_EQ(0, running_);
  --inflight_;

  // Loop over any inflight (but not running) blocks and clear the block
  // variable in order to release any memory associated with the block.
  for (BlockMap::iterator iter(blocks_.begin());
       iter != blocks_.end();
       ++iter) {
    AsyncBlock* ab = *iter;
    ab->clear();
  }

  const bool del = !inflight_;
  mu_.Unlock();
  if (del) {
    delete this;
  }
}

void AsyncState::Impl::Run(AsyncBlock* ab, bool force) {
  dispatch_autoreleasepool([this, ab, force] {
      if (Start(ab, force)) {
        Finish();
      }
    });
}

bool AsyncState::Impl::Start(AsyncBlock* ab, bool force) {
  mu_.Lock();
  --inflight_;
  const bool alive = force || alive_;
  if (alive) {
    ++running_;
  }
  if (ab) {
    if (!alive) {
      // If the AsyncState is being killed, clear the block before we release
      // the lock in order to release any memory associated with the block.
      ab->clear();
    }
    blocks_.erase(ab);
  }
  const bool del = !alive && !inflight_ && !running_;
  mu_.Unlock();
  if (del) {
    delete this;
  }
  if (ab && ab->valid()) {
    (*ab)();
  }
  delete ab;
  return alive;
}

bool AsyncState::Impl::Finish() {
  mu_.Lock();
  --running_;
  const bool alive = alive_;
  const bool del = !alive && !inflight_ && !running_;
  mu_.Unlock();
  if (del) {
    delete this;
  }
  return alive;
}

void AsyncState::Impl::dispatch_main(const DispatchBlock& block) {
  AsyncBlock* ab = QueueAsyncBlock(block);
  if (!ab) {
    return;
  }
  ::dispatch_main([this, ab] { Run(ab); });
}

void AsyncState::Impl::dispatch_main_async(const DispatchBlock& block) {
  AsyncBlock* ab = QueueAsyncBlock(block);
  if (!ab) {
    return;
  }
  ::dispatch_main_async([this, ab] { Run(ab); });
}

void AsyncState::Impl::dispatch_network(bool force, const DispatchBlock& block) {
  AsyncBlock* ab = QueueAsyncBlock(block, force);
  if (!ab) {
    return;
  }
  ::dispatch_network([this, ab, force] { Run(ab, force); });
}

void AsyncState::Impl::dispatch_high_priority(const DispatchBlock& block) {
  AsyncBlock* ab = QueueAsyncBlock(block);
  if (!ab) {
    return;
  }
  ::dispatch_high_priority([this, ab] { Run(ab); });
}

void AsyncState::Impl::dispatch_low_priority(const DispatchBlock& block) {
  AsyncBlock* ab = QueueAsyncBlock(block);
  if (!ab) {
    return;
  }
  ::dispatch_low_priority([this, ab] { Run(ab); });
}

void AsyncState::Impl::dispatch_background(const DispatchBlock& block) {
  AsyncBlock* ab = QueueAsyncBlock(block);
  if (!ab) {
    return;
  }
  ::dispatch_background([this, ab] { Run(ab); });
}

void AsyncState::Impl::dispatch_after_main(
    double delay, const DispatchBlock& block) {
  AsyncBlock* ab = QueueAsyncBlock(block);
  if (!ab) {
    return;
  }
  ::dispatch_after_main(delay, [this, ab] { Run(ab); });
}

void AsyncState::Impl::dispatch_after_network(
    double delay, const DispatchBlock& block) {
  AsyncBlock* ab = QueueAsyncBlock(block);
  if (!ab) {
    return;
  }
  ::dispatch_after_network(delay, [this, ab] { Run(ab); });
}

void AsyncState::Impl::dispatch_after_low_priority(
    double delay, const DispatchBlock& block) {
  AsyncBlock* ab = QueueAsyncBlock(block);
  if (!ab) {
    return;
  }
  ::dispatch_after_low_priority(delay, [this, ab] { Run(ab); });
}

void AsyncState::Impl::dispatch_after_background(
    double delay, const DispatchBlock& block) {
  AsyncBlock* ab = QueueAsyncBlock(block);
  if (!ab) {
    return;
  }
  ::dispatch_after_background(delay, [this, ab] { Run(ab); });
}

AsyncState::AsyncState()
    : impl_(new Impl),
      parent_(NULL) {
}

AsyncState::AsyncState(AsyncState* parent)
    : impl_(new Impl),
      parent_(parent) {
  parent_->children_.insert(this);
}

AsyncState::~AsyncState() {
  Kill();
}

bool AsyncState::Enter() {
  if (!impl_->Enter(NULL)) {
    return false;
  }
  return impl_->Start(NULL);
}

bool AsyncState::Exit() {
  return impl_->Finish();
}

void AsyncState::Kill() {
  ChildMap tmp_children;
  tmp_children.swap(children_);
  for (ChildMap::iterator iter(tmp_children.begin());
       iter != tmp_children.end();
       ++iter) {
    AsyncState* child = *iter;
    child->parent_ = NULL;
    child->Kill();
  }

  if (parent_) {
    parent_->children_.erase(this);
  }

  if (impl_) {
    impl_->Kill();
    impl_ = NULL;
  }
}

// local variables:
// mode: c++
// end:
