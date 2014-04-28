// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_MUTEX_H
#define VIEWFINDER_MUTEX_H

#import <functional>
#import <pthread.h>
#import "Logging.h"
#import "Utils.h"
#import "WallTime.h"

class Mutex {
  typedef std::function<bool ()> Predicate;

 public:
  Mutex()
      : cond_(NULL) {
    pthread_mutex_init(&mu_, NULL);
  }
  ~Mutex();

  void Lock() {
    pthread_mutex_lock(&mu_);
  }
  bool TryLock() {
    return pthread_mutex_trylock(&mu_) == 0;
  }
  void Unlock() {
    if (cond_) {
      pthread_cond_broadcast(cond_);
    }
    pthread_mutex_unlock(&mu_);
  }

  void Wait(const Predicate& pred);
  bool TimedWait(WallTime max_wait, const Predicate& pred);

  // In debug builds, fail a CHECK if the lock is not held.  This does not
  // guarantee that the lock is held by the current thread, but it allows
  // unittests to catch cases where the lock is not held at all.
  void AssertHeld() {
#ifdef DEBUG
    const int result = pthread_mutex_trylock(&mu_);
    if (result == 0) {
      pthread_mutex_unlock(&mu_);
      DIE("mutex was not held");
    }
#endif  // DEBUG
  }

 private:
  pthread_mutex_t mu_;
  pthread_cond_t* cond_;

 private:
  // Catch the error of writing Mutex when intending MutexLock.
  Mutex(Mutex*) = delete;
  // Disallow "evil" constructors
  Mutex(const Mutex&) = delete;
  void operator=(const Mutex&) = delete;
};

class MutexLock {
 public:
  explicit MutexLock(Mutex *mu)
      : mu_(mu) {
    mu_->Lock();
  }
  ~MutexLock() {
    mu_->Unlock();
  }

 private:
  Mutex * const mu_;

 private:
  // Disallow "evil" constructors
  MutexLock(const MutexLock&);
  void operator=(const MutexLock&);
};

// Catch bug where variable name is omitted, e.g. MutexLock (&mu);
// #define MutexLock(x) COMPILE_ASSERT(0, mutex_lock_decl_missing_var_name)

class Barrier {
 public:
  Barrier(int n)
      : count_(n) {
  }

  void Signal();
  void Wait();

 private:
  Mutex mu_;
  int count_;
};

#endif  // VIEWFINDER_MUTEX_H
