// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>
#import "WallTime.h"

@protocol PullToRefreshEnv
- (bool)pullToRefreshUpdate;
- (UIScrollView*)pullToRefreshScrollView;
@end  // PullToRefreshEnv

@interface PullToRefreshView : UIView {
 @private
  __weak id<PullToRefreshEnv> env_;
  UILabel* label_;
  UILabel* sublabel_;
  UIView* arrow_;
  UIActivityIndicatorView* spinner_;
  WallTime loading_start_;
  int state_;
}

@property (nonatomic) NSString* label;
@property (nonatomic) NSString* sublabel;

- (id)initWithEnv:(id<PullToRefreshEnv>)env_;
- (void)dragUpdate;
- (bool)dragEnd;
- (void)start;
- (void)stop;

@end  // PullToRefreshView

// local variables:
// mode: objc
// end:
