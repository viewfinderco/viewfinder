// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_SCOPED_PTR_H
#define VIEWFINDER_SCOPED_PTR_H

#import <stddef.h>

template <typename T>
class ScopedPtr {
 public:
  ScopedPtr(T* ptr = NULL)
      : ptr_(ptr) {
  }
  ~ScopedPtr() {
    reset(NULL);
  }

  T* get() const { return ptr_;  }
  T* operator->() const { return ptr_;  }
  T& operator*() const { return *ptr_; }

  bool operator==(T* p) const {
    return ptr_ == p;
  }
  bool operator!=(T* p) const {
    return ptr_ != p;
  }

  void reset(T* new_ptr) {
    if (ptr_ != new_ptr) {
      enum { type_must_be_complete = sizeof(T) };
      delete ptr_;
      ptr_ = new_ptr;
    }
  }

  void swap(ScopedPtr& other) {
    T* tmp = ptr_;
    ptr_ = other.ptr_;
    other.ptr_ = tmp;
  }

  T* release() {
    T* released_ptr = ptr_;
    ptr_ = NULL;
    return released_ptr;
  }

 private:
  // Disallow evil constructors
  ScopedPtr(const ScopedPtr&);
  void operator=(const ScopedPtr&);

 private:
  T* ptr_;
};

template <typename T>
void swap(ScopedPtr<T>& a, ScopedPtr<T>& b) {
  a.swap(b);
}

template <typename T>
class ScopedArray {
 public:
  ScopedArray(T* ptr = NULL)
      : ptr_(ptr) {
  }
  ~ScopedArray() {
    reset(NULL);
  }

  T* get() const { return ptr_;  }
  T* operator->() const { return ptr_;  }
  T& operator*() const { return *ptr_; }

  T& operator[](ptrdiff_t i) const {
    return ptr_[i];
  }

  bool operator==(T* p) const {
    return ptr_ == p;
  }
  bool operator!=(T* p) const {
    return ptr_ != p;
  }

  void reset(T* new_ptr) {
    if (ptr_ != new_ptr) {
      enum { type_must_be_complete = sizeof(T) };
      delete [] ptr_;
      ptr_ = new_ptr;
    }
  }

  void swap(ScopedArray& other) {
    T* tmp = ptr_;
    ptr_ = other.ptr_;
    other.ptr_ = tmp;
  }

  T* release() {
    T* released_ptr = ptr_;
    ptr_ = NULL;
    return released_ptr;
  }

 private:
  // Disallow evil constructors
  ScopedArray(const ScopedArray&);
  void operator=(const ScopedArray&);

 private:
  T* ptr_;
};

template <typename T>
void swap(ScopedArray<T>& a, ScopedArray<T>& b) {
  a.swap(b);
}

#endif // VIEWFINDER_SCOPED_PTR_H
