// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_SCOPED_HANDLE_H
#define VIEWFINDER_SCOPED_HANDLE_H

#import <atomic>

class AtomicRefCount {
 public:
  AtomicRefCount()
      : val_(0) {
  }
  AtomicRefCount(const AtomicRefCount& v)
      : val_(v.val_.load()) {
  }

  // Atomically increments the reference count.
  void Ref() {
    val_.fetch_add(1);
  }

  // Atomically decrements the reference count and returns true iff the
  // reference count has reached 0.
  bool Unref() {
    // std::atomic_int::fetch_sub() returns the previous value before the
    // subtraction occurs.
    return val_.fetch_sub(1) == 1;
  }

  AtomicRefCount& operator=(const AtomicRefCount& v) {
    val_.store(v.val_.load());
    return *this;
  }

  int32_t val() const { return val_; }

 private:
  std::atomic_int val_;
};

template <typename T>
class ScopedHandle {
 public:
  ScopedHandle(T* ptr = NULL)
      : ptr_(ptr) {
    if (ptr_) {
      ptr_->Ref();
    }
  }
  ScopedHandle(const ScopedHandle& other)
      : ptr_(NULL) {
    reset(other);
  }
  ~ScopedHandle() {
    if (ptr_) {
      ptr_->Unref();
    }
  }

  void reset(const ScopedHandle& other = ScopedHandle()) {
    if (ptr_ != other.ptr_) {
      if (ptr_) {
        ptr_->Unref();
      }
      ptr_ = other.ptr_;
      if (ptr_) {
        ptr_->Ref();
      }
    }
  }

  T* get() const { return ptr_;  }
  T* operator->() const { return ptr_;  }
  T& operator*() const { return *ptr_; }

  ScopedHandle& operator=(const ScopedHandle& other) {
    reset(other);
    return *this;
  }

 private:
  T* ptr_;
};

#endif // VIEWFINDER_SCOPED_HANDLE_H
