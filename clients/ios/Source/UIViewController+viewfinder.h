// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>

// Viewfinder-specific UIViewController extensions.
@interface UIViewController (viewfinder)

- (bool)animateTransitionCommit;
- (bool)statusBarHidden;
- (bool)statusBarLightContent;

@end  // UIViewController (viewfinder)

// local variables:
// mode: objc
// end:
