// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_LAZY_STATIC_PTR_H
#define VIEWFINDER_LAZY_STATIC_PTR_H

#import <mutex>

template<typename Type, typename A1, typename A2, typename A3>
class LazyStaticPtr;

namespace internal {

struct NoArg { };

template <typename Type, typename A1, typename A2, typename A3>
struct Helper {
  static void Init(LazyStaticPtr<Type, A1, A2, A3>* p) {
    p->u_.ptr_ = new Type(p->arg1_, p->arg2_, p->arg3_);
  }
};

template <typename Type, typename A1, typename A2>
struct Helper<Type, A1, A2, NoArg> {
  static void Init(LazyStaticPtr<Type, A1, A2, NoArg>* p) {
    p->u_.ptr_ = new Type(p->arg1_, p->arg2_);
  }
};

template <typename Type, typename A1>
struct Helper<Type, A1, NoArg, NoArg> {
  static void Init(LazyStaticPtr<Type, A1, NoArg, NoArg>* p) {
    p->u_.ptr_ = new Type(p->arg1_);
  }
};

template <typename Type>
struct Helper<Type, NoArg, NoArg, NoArg> {
  static void Init(LazyStaticPtr<Type, NoArg, NoArg, NoArg>* p) {
    p->u_.ptr_ = new Type();
  }
};

}  // namespace internal

template <typename Type,
          typename Arg1 = internal::NoArg,
          typename Arg2 = internal::NoArg,
          typename Arg3 = internal::NoArg>
class LazyStaticPtr {
  typedef internal::NoArg NoArg;
  typedef internal::Helper<Type, Arg1, Arg2, Arg3> Helper;

 public:
  Type& operator*() { return *get(); }
  Type* operator->() { return get(); }

  Type* get() {
    typedef void (*function_t)(void*);
    // Note(peter): This sucks. If std::once_flag is a member of LazyStaticPtr
    // then the compiler generates a constructor for LazyStaticPtr which clears
    // out the various members at an arbitrary time in the initialization
    // process which is very problematic if we've already called
    // LazyStaticPtr::get() for that LazyStaticPtr instance. We don't want
    // LazyStaticPtr to have a constructor and instead want it to be statically
    // initialized. There is likely some bit of c++11 magic that could make
    // this hack go away, I just haven't found it yet. Or maybe this is a
    // compiler bug.
    std::once_flag* once = reinterpret_cast<std::once_flag*>(once_buf_);
    std::call_once(*once, &Helper::Init, this);
    return u_.ptr_;
  }

 public:
  Arg1 arg1_;
  Arg2 arg2_;
  Arg3 arg3_;

  union {
    Type* ptr_;
  } u_;

  char once_buf_[sizeof(std::once_flag)];

 private:
  // Disable assignment.
  void operator=(const LazyStaticPtr&);
};

#endif  // VIEWFINDER_LAZY_STATIC_PTR_H
