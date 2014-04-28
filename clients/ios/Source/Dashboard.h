// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <map>
#import <UIKit/UIKit.h>
#import "PhotoLoader.h"
#import "PhotoPickerView.h"
#import "ScopedNotification.h"

class UIAppState;
@class AccountSetupDashboardCard;
@class DashboardNotice;
@class DefaultDashboardCard;
@class LoginSignupDashboardCard;
@class MaintenanceDashboardCard;
@class PhotoView;

typedef std::map<int, DashboardNotice*> DashboardNoticeMap;

@protocol DashboardEnv
- (void)dashboardMaintenanceBegin;
- (void)dashboardMaintenanceEnd;
@end  // DashboardEnv

@interface Dashboard : UIView<PhotoPickerEnv,
                              UIGestureRecognizerDelegate,
                              UIScrollViewDelegate> {
 @private
  UIAppState* state_;
  __weak id<DashboardEnv> env_;
  bool active_;
  bool maintenance_done_;
  bool registered_;
  PhotoView* background_;
  UIScrollView* content_;
  UIButton* bg_edit_;
  AccountSetupDashboardCard* account_setup_card_;
  DefaultDashboardCard* default_card_;
  LoginSignupDashboardCard* login_signup_card_;
  MaintenanceDashboardCard* maintenance_card_;
  UIImageView* signup_logo_;
  UIView* tour_;
  UIView* tour_page_[4];
  ScopedNotification keyboard_will_show_;
  ScopedNotification keyboard_will_hide_;
  CGRect keyboard_frame_;
  PhotoPickerView* photo_picker_;
  PhotoQueue photo_queue_;
  UITapGestureRecognizer* single_tap_recognizer_;
  DashboardNoticeMap notices_;
}

@property (nonatomic) bool active;
@property (nonatomic, readonly) bool keyboardVisible;
@property (nonatomic, readonly) bool maintenanceDone;
@property (nonatomic, readonly) int noticeCount;

- (id)initWithState:(UIAppState*)state
                env:(id<DashboardEnv>)env;
- (void)rebuild;
- (void)resetBackground;

@end  // Dashboard

// local variables:
// mode: objc
// end:
