// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "UIViewController+viewfinder.h"

@implementation UIViewController (viewfinder)

- (bool)animateTransitionCommit {
  return false;
}

- (bool)statusBarHidden {
  return false;
}

- (bool)statusBarLightContent {
  return false;
}

@end  // UIViewController (viewfinder)
