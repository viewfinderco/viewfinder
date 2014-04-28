// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIButton.h>
#import <UIKit/UIControl.h>
#import <objc/runtime.h>
#import "ControlDelegate.h"

void AddButtonCallback(UIButton* b, void (^callback)()) {
  if (!callback) {
    return;
  }
  [ControlDelegate delegateWithControl:b].callbacks->Add(callback);
}

@implementation ControlDelegate

+ (ControlDelegate*)delegateWithControl:(UIControl*)control {
  return [[ControlDelegate alloc] initWithControl:control];
}

- (id)initWithControl:(UIControl*)control {
  if (self = [super init]) {
    [control addTarget:self
               action:@selector(action)
     forControlEvents:UIControlEventTouchUpInside];
    // Tell objective-c to associate a reference to "self" with "control". When
    // "control" gets deallocated, "self" will get released.
    objc_setAssociatedObject(control, _cmd, self, OBJC_ASSOCIATION_RETAIN);
  }
  return self;
}

- (void)action {
  callbacks_.Run();
}

- (CallbackSet*)callbacks {
  return &callbacks_;
}

@end  // ControlDelegate
