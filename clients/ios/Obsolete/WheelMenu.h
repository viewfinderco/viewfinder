// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>

class AppState;

@class CAShapeLayer;

@interface WheelMenu : UIControl {
 @private
  AppState* state_;
  UIView* buttons_;
  CAShapeLayer* wheel_;
  bool hidden_;
  bool expanded_;
  bool tracking_;
  bool had_selected_button_;
  UIButton* selected_button_;
  CGPoint tracking_center_;
  CGPoint tracking_start_;
  float scale_;
  float angle_;
  float animation_scale_;
  float wheel_pos_;
  float old_wheel_pos_;
}

- (id)initWithState:(AppState*)state;
- (UIButton*)homeButton;
- (UIButton*)cameraButton;
- (UIButton*)settingsButton;
- (UIButton*)developerButton;
- (void)setHidden:(bool)hidden duration:(float)duration;

@end  // WheelMenu

// local variables:
// mode: objc
// end:
