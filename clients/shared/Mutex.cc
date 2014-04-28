// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "Mutex.h"

Mutex::~Mutex() {
  pthread_mutex_destroy(&mu_);
  if (cond_) {
    pthread_cond_destroy(cond_);
    delete cond_;
  }
}

void Mutex::Wait(const Predicate& pred) {
  if (pred()) {
    return;
  }
  if (!cond_) {
    cond_ = new pthread_cond_t;
    pthread_cond_init(cond_, NULL);
  }
  do {
    pthread_cond_wait(cond_, &mu_);
  } while (!pred());
}

bool Mutex::TimedWait(WallTime max_wait, const Predicate& pred) {
  if (pred()) {
    return true;
  }
  const WallTime end_time = WallTime_Now() + max_wait;
  if (!cond_) {
    cond_ = new pthread_cond_t;
    pthread_cond_init(cond_, NULL);
  }
  timespec ts;
  ts.tv_sec = static_cast<time_t>(end_time);
  ts.tv_nsec = static_cast<long>((end_time - ts.tv_sec) * 1e9);
  do {
    if (pthread_cond_timedwait(cond_, &mu_, &ts) != 0) {
      return false;
    }
  } while (!pred());
  return true;
}


void Barrier::Signal() {
  MutexLock l(&mu_);
  CHECK_GT(count_, 0);
  --count_;
}

void Barrier::Wait() {
  MutexLock l(&mu_);
  CHECK_GE(count_, 0);
  mu_.Wait([this] { return count_ == 0; });
}
