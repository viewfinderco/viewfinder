// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <QuartzCore/QuartzCore.h>
#import "RotatingView.h"
#import "ValueUtils.h"
#import "Vector.h"

namespace {

UIInterfaceOrientation DeviceToInterfaceOrientation(
    UIDeviceOrientation device_orientation,
    UIInterfaceOrientation current_orientation) {
  switch (device_orientation) {
    case UIDeviceOrientationPortrait:
    case UIDeviceOrientationPortraitUpsideDown:
    case UIDeviceOrientationLandscapeLeft:
    case UIDeviceOrientationLandscapeRight:
      return static_cast<UIInterfaceOrientation>(device_orientation);
    case UIDeviceOrientationUnknown:
    case UIDeviceOrientationFaceUp:
    case UIDeviceOrientationFaceDown:
      break;
  }
  return current_orientation;
}

float UIOrientationToAngle(UIInterfaceOrientation o) {
  switch (o) {
    case UIInterfaceOrientationPortrait:
    default:
      return 0;
    case UIInterfaceOrientationPortraitUpsideDown:
      return kPi;
    case UIInterfaceOrientationLandscapeLeft:
      return -kPi / 2;
    case UIInterfaceOrientationLandscapeRight:
      return kPi / 2;
  }
}

CGAffineTransform UIOrientationToTransform(UIInterfaceOrientation o) {
  return CGAffineTransformMakeRotation(UIOrientationToAngle(o));
}

}  // namespace

@interface RotatingView (internal)
- (void)orientationChanged:(NSNotification*)notification;
@end  // RotatingView (internal)

@implementation RotatingView

@synthesize currentAngle = current_angle_;
@synthesize lastAngle = last_angle_;
@synthesize orientation = orientation_;

- (id)init {
  if (self = [super init]) {
    self.backgroundColor = [UIColor clearColor];
    self.autoresizesSubviews = YES;
    self.autoresizingMask =
        UIViewAutoresizingFlexibleHeight |
        UIViewAutoresizingFlexibleWidth;
    orientation_ = UIInterfaceOrientationPortrait;

    [[NSNotificationCenter defaultCenter]
      addObserver:self
         selector:@selector(orientationChanged:)
             name:UIDeviceOrientationDidChangeNotification
           object:nil];
  }
  return self;
}

- (CallbackSet*)prepare {
  return &prepare_;
}

- (CallbackSet1<float>*)commit {
  return &commit_;
}

- (void)changeOrientation:(float)duration {
  const UIInterfaceOrientation orientation =
      DeviceToInterfaceOrientation(
          [UIDevice currentDevice].orientation, orientation_);
  if (orientation_ == orientation) {
    // Nothing to do.
    return;
  }
  const UIInterfaceOrientation old_orientation = orientation_;
  orientation_ = orientation;

  // Setting the status bar orientation also causes the keyboard orientation to
  // change.
  [UIApplication sharedApplication].statusBarOrientation = orientation_;

  const CGSize old_size = self.bounds.size;
  CGRect untransformed_bounds = self.bounds;
  // Compute the untransformed bounds of the rotating view. We can't use
  // self.superview because this method might be called when the rotating view
  // does not have a superview.
  untransformed_bounds.size = CGSizeApplyAffineTransform(
      untransformed_bounds.size, CGAffineTransformInvert(self.transform));

  // Compute the new transformed bounds of the rotating view.
  const CGAffineTransform transform = UIOrientationToTransform(orientation_);
  CGRect transformed_bounds = untransformed_bounds;
  transformed_bounds.size = CGSizeApplyAffineTransform(
      untransformed_bounds.size, transform);
  transformed_bounds.size.width = fabs(transformed_bounds.size.width);
  transformed_bounds.size.height = fabs(transformed_bounds.size.height);

  if (duration > 0) {
    last_angle_ = UIOrientationToAngle(old_orientation);
    current_angle_ = UIOrientationToAngle(orientation_);
    while ((current_angle_ - last_angle_) > kPi) {
      last_angle_ += 2 * kPi;
    }
    while ((last_angle_ - current_angle_) > kPi) {
      current_angle_ += 2 * kPi;
    }

    CAKeyframeAnimation* rotation =
        [CAKeyframeAnimation animationWithKeyPath:@"transform.rotation.z"];
    rotation.values = Array(last_angle_, current_angle_);
    rotation.keyTimes = Array(0.0, 1.0);
    rotation.duration = duration;

    CAKeyframeAnimation* scale =
        [CAKeyframeAnimation animationWithKeyPath:@"transform.scale"];
    scale.values = Array(transformed_bounds.size.width / fabs(old_size.width), 1.0);
    scale.keyTimes = Array(0, 1.0);
    scale.duration = duration;

    CAAnimationGroup* animation = [CAAnimationGroup animation];
    animation.animations = Array(scale, rotation);
    animation.duration = duration;
    animation.timingFunction =
        [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionEaseOut];
    animation.fillMode = kCAFillModeForwards;

    [self.layer addAnimation:animation forKey:nil];
  }

  prepare_.Run();
  self.transform = transform;
  self.bounds = transformed_bounds;
  commit_.Run(duration);
}

- (void)orientationChanged:(NSNotification*)notification {
  if (!self.window) {
    return;
  }
  [self changeOrientation:0.3];
}

- (void)willAppear {
  [self changeOrientation:0];
}

- (void)willDisappear {
  // Setting the status bar orientation also causes the keyboard orientation to
  // change.
  [UIApplication sharedApplication].statusBarOrientation =
      UIInterfaceOrientationPortrait;
}

- (void)dealloc {
  [[NSNotificationCenter defaultCenter]
    removeObserver:self
              name:UIDeviceOrientationDidChangeNotification
            object:nil];
}

@end  // RotatingView
