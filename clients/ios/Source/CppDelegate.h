// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.

#ifndef VIEWFINDER_CPP_DELEGATE_H
#define VIEWFINDER_CPP_DELEGATE_H

#import <unordered_map>
#import <Foundation/NSInvocation.h>
#import <Foundation/NSMethodSignature.h>
#import "Logging.h"

// CppDelegate allows the use of delegate protocols from C++ code
// without the creation of objective-c classes that just forward
// methods back and forth.  It also ensures that there is a strong
// reference to the objc delegate object for the lifetime of the
// CppDelegate (throwaway delegates sometimes have no strong
// references and get deallocated too soon).
//
// Usage:  Create a CppDelegate and call Add() one or more times to bind
// selectors to blocks.  Assign cpp_delegate.delegate() as the
// objective-c delegate object.  See the unit test for more examples.
//
// Tips: Some classes call respondsToSelector: as soon as the delegate
// is assigned and cache the results, so don't assign the delegate
// until after binding all your selectors.  If you delete the
// CppDelegate while the object using it is still alive, be sure to
// set the delegate back to nil.  Some classes don't like having their
// delegates reassigned, so it's best to delete the CppDelegate from
// the last possible callback (didFinish, didDismiss, etc).
class CppDelegate {
 public:
  typedef void(^CallbackType)(NSInvocation*);

  CppDelegate();
  ~CppDelegate();

  // Returns the objective-c delegate object.
  id delegate() const { return delegate_; }

  // Binds a block to the given protocol and selector (which are
  // created with the @protocol and @selector functions).  Variants
  // are provided for functions of 0 to 5 arguments, with void and
  // non-void return types.  (Return types must be primitive or c++
  // types, not objc pointers)
  void Add(Protocol* protocol, SEL selector, void (^callback)()) {
    AddInvocation(protocol, selector, ^(NSInvocation* invocation) {
        callback();
      });
  }

  template<typename P1>
  void Add(Protocol* protocol, SEL selector, void (^callback)(P1)) {
    AddInvocation(protocol, selector, ^(NSInvocation* invocation) {
        P1 p1;
        GetArgument<P1>(invocation, 2, &p1);
        callback(p1);
      });
  }

  template<typename P1, typename P2>
  void Add(Protocol* protocol, SEL selector, void (^callback)(P1, P2)) {
    AddInvocation(protocol, selector, ^(NSInvocation* invocation) {
        P1 p1; P2 p2;
        GetArgument<P1>(invocation, 2, &p1);
        GetArgument<P2>(invocation, 3, &p2);
        callback(p1, p2);
      });
  }

  template<typename P1, typename P2, typename P3>
  void Add(Protocol* protocol, SEL selector, void (^callback)(P1, P2, P3)) {
    AddInvocation(protocol, selector, ^(NSInvocation* invocation) {
        P1 p1; P2 p2; P3 p3;
        GetArgument<P1>(invocation, 2, &p1);
        GetArgument<P2>(invocation, 3, &p2);
        GetArgument<P3>(invocation, 4, &p3);
        callback(p1, p2, p3);
      });
  }

  template<typename P1, typename P2, typename P3, typename P4>
  void Add(Protocol* protocol, SEL selector, void (^callback)(P1, P2, P3, P4)) {
    AddInvocation(protocol, selector, ^(NSInvocation* invocation) {
        P1 p1; P2 p2; P3 p3; P4 p4;
        GetArgument<P1>(invocation, 2, &p1);
        GetArgument<P2>(invocation, 3, &p2);
        GetArgument<P3>(invocation, 4, &p3);
        GetArgument<P4>(invocation, 5, &p4);
        callback(p1, p2, p3, p4);
      });
  }

  template<typename P1, typename P2, typename P3, typename P4, typename P5>
  void Add(Protocol* protocol, SEL selector, void (^callback)(P1, P2, P3, P4, P5)) {
    AddInvocation(protocol, selector, ^(NSInvocation* invocation) {
        P1 p1; P2 p2; P3 p3; P4 p4; P5 p5;
        GetArgument<P1>(invocation, 2, &p1);
        GetArgument<P2>(invocation, 3, &p2);
        GetArgument<P3>(invocation, 4, &p3);
        GetArgument<P4>(invocation, 5, &p4);
        GetArgument<P5>(invocation, 6, &p5);
        callback(p1, p2, p3, p4, p5);
      });
  }

  template<typename R, typename P1>
  void Add(Protocol* protocol, SEL selector, R (^callback)(P1)) {
    AddInvocation(protocol, selector, ^(NSInvocation* invocation) {
        P1 p1;
        GetArgument<P1>(invocation, 2, &p1);
        R r = callback(p1);
        SetReturn<R>(invocation, &r);
      });
  }

  template<typename R, typename P1, typename P2>
  void Add(Protocol* protocol, SEL selector, R (^callback)(P1, P2)) {
    AddInvocation(protocol, selector, ^(NSInvocation* invocation) {
        P1 p1;
        P2 p2;
        GetArgument<P1>(invocation, 2, &p1);
        GetArgument<P2>(invocation, 3, &p2);
        R r = callback(p1, p2);
        SetReturn<R>(invocation, &r);
      });
  }

  template<typename R, typename P1, typename P2, typename P3>
  void Add(Protocol* protocol, SEL selector, R (^callback)(P1, P2, P3)) {
    AddInvocation(protocol, selector, ^(NSInvocation* invocation) {
        P1 p1;
        P2 p2;
        P3 p3;
        GetArgument<P1>(invocation, 2, &p1);
        GetArgument<P2>(invocation, 3, &p2);
        GetArgument<P3>(invocation, 4, &p3);
        R r = callback(p1, p2, p3);
        SetReturn<R>(invocation, &r);
      });
  }

  template<typename R, typename P1, typename P2, typename P3, typename P4>
  void Add(Protocol* protocol, SEL selector, R (^callback)(P1, P2, P3, P4)) {
    AddInvocation(protocol, selector, ^(NSInvocation* invocation) {
        P1 p1;
        P2 p2;
        P3 p3;
        P4 p4;
        GetArgument<P1>(invocation, 2, &p1);
        GetArgument<P2>(invocation, 3, &p2);
        GetArgument<P3>(invocation, 4, &p3);
        GetArgument<P4>(invocation, 5, &p4);
        R r = callback(p1, p2, p3, p4);
        SetReturn<R>(invocation, &r);
      });
  }

  template<typename R, typename P1, typename P2, typename P3, typename P4, typename P5>
  void Add(Protocol* protocol, SEL selector, R (^callback)(P1, P2, P3, P4, P5)) {
    AddInvocation(protocol, selector, ^(NSInvocation* invocation) {
        P1 p1;
        P2 p2;
        P3 p3;
        P4 p4;
        P5 p5;
        GetArgument<P1>(invocation, 2, &p1);
        GetArgument<P2>(invocation, 3, &p2);
        GetArgument<P3>(invocation, 4, &p3);
        GetArgument<P4>(invocation, 5, &p4);
        GetArgument<P5>(invocation, 6, &p5);
        R r = callback(p1, p2, p3, p4, p5);
        SetReturn<R>(invocation, &r);
      });
  }

  // Raw version of Add(), which supports any number and type of arguments.
  void AddInvocation(Protocol* protocol, SEL selector, CallbackType callback);

  // The following methods should only be used internally by DynamicDelegate.
  NSMethodSignature* GetMethodSignatureForSelector(SEL selector);
  void InvokeCallback(NSInvocation* invocation);

 private:
  // Returns the given argument from the invocation.  Note that arguments
  // 0 and 1 are the implicit self and selector arguments; the real arguments
  // start at index 2.
  template<typename T>
  void GetArgument(NSInvocation* invocation, int index, void* arg);

  // Sets *r as the return value for the invocation.
  template<typename T>
  void SetReturn(NSInvocation* invocation, void* ret);

  id delegate_;
  std::unordered_map<SEL, CallbackType> callbacks_;
  std::unordered_map<SEL, NSMethodSignature*> method_signatures_;
};

template<typename T>
void CppDelegate::GetArgument(NSInvocation* invocation, int index, void* arg) {
  const Slice expected_type = Slice([invocation.methodSignature getArgumentTypeAtIndex:index]);
  const Slice actual_type = Slice(@encode(T));
  CHECK_EQ(expected_type, actual_type);

  // Automatic reference counting doesn't know anything about assignment via
  // pointers, so we need to adjust reference counts if and only if the
  // argument type is an objc object.
  const Slice kIdEncoding(@encode(id));
  if (expected_type == kIdEncoding) {
    // Step 1: Get the argument into a normal void*.
    void* v;
    [invocation getArgument:&v atIndex:index];
    // Step 2: Explicit bridging cast to turn it into an object (with a
    // reference that's local to this function).
    id obj = (__bridge id)v;
    // Step 3: Pass the pointer to our out parameter so that the calling
    // function will own a reference when we're done.
    *(void**)(arg) = (__bridge_retained void*)obj;
  } else {
    // Non objective-c types just work normally.
    [invocation getArgument:arg atIndex:index];
  }
}

template<typename T>
void CppDelegate::SetReturn(NSInvocation* invocation, void* ret) {
  const Slice expected_type = Slice(invocation.methodSignature.methodReturnType);
  const Slice actual_type = Slice(@encode(T));
  CHECK_EQ(expected_type, actual_type);

  const Slice kIdEncoding(@encode(id));
  if (expected_type == kIdEncoding) {
    // Need to figure out the right refcount tricks here.
    DIE("TODO: CppDelegate does not yet support objc return values");
  } else {
    [invocation setReturnValue:ret];
  }
}

#endif  // VIEWFINDER_CPP_DELEGATE_H
