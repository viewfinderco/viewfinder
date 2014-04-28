// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>

@class CameraViewController;
@class PhotoViewController;
@class SettingsViewController;
@class WheelMenu;

@interface RootViewController : UIViewController {
 @private
  AppState* state_;
  CameraViewController* camera_view_controller_;
  PhotoViewController* photo_view_controller_;
  SettingsViewController* settings_view_controller_;
  UIViewController* current_view_controller_;
  UIViewController* prev_view_controller_;
}

- (id)initWithState:(AppState*)state;

@end  // RootViewController

// local variables:
// mode: objc
// end:
