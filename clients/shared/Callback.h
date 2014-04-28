// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

// ==================== PAY ATTENTION, THIS IS IMPORTANT ====================
//
// Combining ARC (automatic reference counting) and non-ARC code (e.g. plain
// C++) with templates is dangerous due to easy violations of the
// one-definition-rule
// (http://en.wikipedia.org/wiki/One_Definition_Rule). Consider
// Callback::Release(). When compiled with ARC it will yield one definition and
// when compiled without ARC it will yield another. At link time, the compiler
// will arbitrarily choose one definition which might differ from the
// definition it chose for Callback::Acquire() leading to a memory leak or
// memory corruption.
//
// The current solution is fragile: Ensure that specializations of Callback<>
// and CallbackSetBase<> are either always instatiated with ARC enabled or
// always with ARC disabled. This is accomplished by suppressing instantiation
// of the specializations of Callback<> and CallbackSetBase<> used by C++ code
// and then explicitly instantiating them in C++ code. See the suppressions at
// the end of this file and the instantiations in Callback.cc. Fragile.
//
// ==========================================================================

#ifndef VIEWFINDER_CALLBACK_H
#define VIEWFINDER_CALLBACK_H

#import <set>
#import <unordered_map>
#import "Mutex.h"
#import "STLUtils.h"

#if __has_extension(blocks) && !defined(__OBJC__)
#error "Objc++ compilation required"
#endif  // __has_extension(blocks) && !defined(__OBJC__)

// Callback is like std::function<> except that it knows about blocks and
// properly copies and releases them.
template <typename F> class Callback;

template <typename R, typename... ArgTypes>
class Callback<R (ArgTypes...)> {
  typedef std::function<R (ArgTypes...)> FunctionType;

#if __has_extension(blocks)
  typedef R (^BlockType)(ArgTypes...);
#endif  // __has_extension(blocks)

 public:
  Callback() {
  }
  // Needed so that we can pass NULL (a.k.a. 0) to the Callback constructor.
  Callback(int) {
  }
  Callback(std::nullptr_t) {
  }
  Callback(const FunctionType& f)
      : func_(f) {
    Acquire(&func_);
  }
  Callback(const Callback& f)
      : Callback(f.func_) {
  }
#if __has_extension(blocks)
  Callback(BlockType b)
      : func_((BlockType)[b copy]) {
  }
#endif  // __has_extension(blocks)
  template <typename F>
  Callback(F f)
      : func_(f) {
    Acquire(&func_);
  }
  ~Callback() {
    clear();
  }

  R operator()(ArgTypes... args) const {
    return func_(args...);
  }

  void clear() {
    Release(&func_);
  }

  void swap(Callback* other) {
    func_.swap(other->func_);
  }

  bool valid() const {
    // Need the ternary operator in order to get the bool operator invoked.
    return func_ ? true : false;
  }
  explicit operator bool() const {
    return valid();
  }

 private:
  static void Acquire(FunctionType* f) {
#if __has_extension(blocks)
    const BlockType* block = f->template target<BlockType>();
    if (block) {
      *f = (BlockType)[*block copy];
    }
#endif  // __has_extension(blocks)
  }

  static void Release(FunctionType* f) {
#if __has_extension(blocks)
    // Nothing to do with objc. ARC will take care of releasing the block.
#endif  // __has_extension(blocks)
    *f = nullptr;
  }

 private:
  FunctionType func_;
};

template <typename... ArgTypes>
class CallbackSetBase {
  typedef std::function<void (ArgTypes...)> FunctionType;
  typedef Callback<void (ArgTypes...)> CallbackType;
  typedef std::unordered_map<int, CallbackType> CallbackMap;
  typedef std::set<int> RemoveSet;

 public:
  CallbackSetBase()
      : next_id_(1) {
  }
  ~CallbackSetBase() {
    Clear();
  }

  // Adds the given callback to the set.  Returns an id (a nonzero
  // integer) which can be used to Remove() the callback later.  See
  // also AddSingleShot (defined in subclasses below).
  int Add(CallbackType callback) {
    MutexLock l(&mu_);
    const int id = next_id_++;
    callbacks_[id].swap(&callback);
    return id;
  }

  void AddSingleShot(const CallbackType& callback) {
    MutexLock l(&mu_);
    const int id = next_id_++;
    callbacks_[id] = [callback, id, this](ArgTypes&&... args) {
      callback(args...);
      Remove(id);
    };
  }

  void Remove(int id) {
    if (mu_.TryLock()) {
      callbacks_.erase(id);
      mu_.Unlock();
    } else {
      MutexLock l(&removed_mu_);
      removed_.insert(id);
    }
  }

  void Run(ArgTypes... args) {
    MutexLock l(&mu_);
    ApplyRemoved();
    for (typename CallbackMap::const_iterator iter(callbacks_.begin());
         iter != callbacks_.end();
         ++iter) {
      const CallbackType& callback = iter->second;
      callback(args...);
    }
    ApplyRemoved();
  }

  void Clear() {
    MutexLock l(&mu_);
    ::Clear(&callbacks_);
  }

  void Swap(CallbackSetBase* other) {
    MutexLock l(&mu_);
    MutexLock l2(&other->mu_);
    ApplyRemoved();
    other->ApplyRemoved();
    std::swap(next_id_, other->next_id_);
    callbacks_.swap(other->callbacks_);
  }

  int size() const {
    MutexLock l(&mu_);
    return callbacks_.size();
  }
  bool empty() const {
    MutexLock l(&mu_);
    return callbacks_.empty();
  }

 private:
  void ApplyRemoved() {
    MutexLock l(&removed_mu_);
    for (RemoveSet::iterator iter(removed_.begin());
         iter != removed_.end();
         ++iter) {
      callbacks_.erase(*iter);
    }
    removed_.clear();
  }

 private:
  mutable Mutex mu_;
  int next_id_;
  CallbackMap callbacks_;
  Mutex removed_mu_;
  RemoveSet removed_;
};

using CallbackSet = CallbackSetBase<>;

template <typename A1>
using CallbackSet1 = CallbackSetBase<A1>;

template <typename A1, typename A2>
using CallbackSet2 = CallbackSetBase<A1, A2>;

template <typename A1, typename A2, typename A3>
using CallbackSet3 = CallbackSetBase<A1, A2, A3>;

#endif  // VIEWFINDER_CALLBACK_H
