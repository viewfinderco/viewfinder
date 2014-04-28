// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>
#import "Callback.h"

@interface RotatingView : UIView {
 @private
  CallbackSet prepare_;
  CallbackSet1<float> commit_;
  UIInterfaceOrientation orientation_;
  float current_angle_;
  float last_angle_;
}

@property (nonatomic, readonly) CallbackSet* prepare;
@property (nonatomic, readonly) CallbackSet1<float>* commit;
@property (nonatomic, readonly) float currentAngle;
@property (nonatomic, readonly) float lastAngle;
@property (nonatomic, readonly) UIInterfaceOrientation orientation;

- (void)willAppear;
- (void)willDisappear;

@end  // RotatingView

// local variables:
// mode: objc
// end:
