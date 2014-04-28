// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_SCOPED_REF_H
#define VIEWFINDER_SCOPED_REF_H

#include "Utils.h"

template <typename T>
class ScopedRef {
 public:
  ScopedRef()
      : ref_(NULL) {
  }
  // Acquires the reference without incrementing the reference count.
  explicit ScopedRef(T ref)
      : ref_(ref) {
  }
  // Initializes the reference and increments the reference count.
  ScopedRef(const ScopedRef& other)
      : ref_(NULL) {
    reset(other.ref_);
  }
  ~ScopedRef() {
    reset(NULL);
  }

  T get() const { return ref_; }
  T* mutable_ptr() { return &ref_; }
  operator T() const { return ref_; }

  void acquire(T new_ref) {
    if (ref_ != new_ref) {
      if (ref_) {
        CFRelease(ref_);
      }
      ref_ = new_ref;
    }
  }

  // Initializes the reference and increments the reference count.
  void reset(T new_ref) {
    if (ref_ != new_ref) {
      if (ref_) {
        CFRelease(ref_);
      }
      ref_ = new_ref;
      if (ref_) {
        CFRetain(ref_);
      }
    }
  }

  void swap(ScopedRef& other) {
    T tmp = ref_;
    ref_ = other.ref_;
    other.ref_ = tmp;
  }

  T release() {
    T released_ref = ref_;
    ref_ = NULL;
    return released_ref;
  }

  ScopedRef<T>& operator=(const ScopedRef<T>& other) {
    reset(other.ref_);
    return *this;
  }

 private:
  ScopedRef<T>& operator=(T ref);

 private:
  T ref_;
};

template <typename T>
void swap(ScopedRef<T>& a, ScopedRef<T>& b) {
  a.swap(b);
}

template <typename T>
ostream& operator<<(ostream& os, const ScopedRef<T>& r) {
  os << r.get();
  return os;
}

#endif // VIEWFINDER_SCOPED_REF_H
