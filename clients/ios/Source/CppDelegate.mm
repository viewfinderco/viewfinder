// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <objc/runtime.h>
#import "CppDelegate.h"

@interface DynamicDelegate : NSObject {
  CppDelegate* cpp_delegate_;
}

- (id)initWithCppDelegate:(CppDelegate*)cpp_delegate;
- (void)setCppDelegate:(CppDelegate*)cpp_delegate;
- (BOOL)respondsToSelector:(SEL)selector;
- (NSMethodSignature*)methodSignatureForSelector:(SEL)selector;
- (void)forwardInvocation:(NSInvocation *)invocation;

@end  // DynamicDelegate

@implementation DynamicDelegate

- (id)initWithCppDelegate:(CppDelegate*)cpp_delegate {
  if (self = [super init]) {
    cpp_delegate_ = cpp_delegate;
  }
  return self;
}

- (void)setCppDelegate:(CppDelegate *)cpp_delegate {
  cpp_delegate_ = cpp_delegate;
}

- (BOOL)respondsToSelector:(SEL)selector {
  if ([self methodSignatureForSelector:selector] != nil) {
    return YES;
  } else {
    return NO;
  }
}

- (NSMethodSignature*)methodSignatureForSelector:(SEL)selector {
  if (cpp_delegate_) {
    return cpp_delegate_->GetMethodSignatureForSelector(selector);
  } else {
    return nil;
  }
}

- (void)forwardInvocation:(NSInvocation *)invocation {
  if (cpp_delegate_) {
    cpp_delegate_->InvokeCallback(invocation);
  }
}

@end  // DynamicDelegate

CppDelegate::CppDelegate() {
  delegate_ = [[DynamicDelegate alloc] initWithCppDelegate:this];
}

CppDelegate::~CppDelegate() {
  [delegate_ setCppDelegate:NULL];
}

void CppDelegate::AddInvocation(Protocol* protocol, SEL selector, CallbackType callback) {
  // third parameter is "is_required".  Some protocols mark their methods as
  // optional and some don't, so if we get an error looking for a required
  // method try again for optional.
  objc_method_description descr = protocol_getMethodDescription(protocol, selector, YES, YES);
  if (!descr.types) {
    descr = protocol_getMethodDescription(protocol, selector, NO, YES);
  }
  NSMethodSignature* sig = [NSMethodSignature signatureWithObjCTypes:descr.types];
  callbacks_[selector] = callback;
  method_signatures_[selector] = sig;
}

NSMethodSignature* CppDelegate::GetMethodSignatureForSelector(SEL selector) {
  return FindOrNull(method_signatures_, selector);
}

void CppDelegate::InvokeCallback(NSInvocation* invocation) {
  CallbackType callback = FindOrNull(callbacks_, invocation.selector);
  if (callback != NULL) {
    callback(invocation);
  }
}
