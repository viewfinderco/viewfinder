// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <QuartzCore/QuartzCore.h>

// An Objective-C category to add some utility properties to CALayer.
@interface CALayer (geometry)

@property (nonatomic) CGPoint frameOrigin;
@property (nonatomic) CGSize frameSize;

@property (nonatomic) CGFloat frameLeft;
@property (nonatomic) CGFloat frameTop;
@property (nonatomic) CGFloat frameRight;
@property (nonatomic) CGFloat frameBottom;

@property (nonatomic) CGFloat frameWidth;
@property (nonatomic) CGFloat frameHeight;

- (void)centerFrameWithinSuperlayer;
- (void)centerFrameWithinFrame:(CGRect)f;

@end  // CALayer (geometry)

class ScopedDisableCAActions {
 public:
  ScopedDisableCAActions() {
    [CATransaction begin];
    [CATransaction setDisableActions:YES];
  }
  ~ScopedDisableCAActions() {
    [CATransaction commit];
  }
};

// local variables:
// mode: objc
// end:
