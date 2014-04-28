// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.

#import "DashboardCard.h"
#import "ScopedNotification.h"

// Container for a LoginSignupDashboardCard to be used as an overlay on top of other views.
@interface DashboardCardContainer : UIView {
  LoginSignupDashboardCard* login_signup_card_;
  ScopedNotification keyboard_will_show_;
  ScopedNotification keyboard_will_hide_;
  CGRect keyboard_frame_;
  UIView* parent_;
  void (^callback_)(DashboardCardContainer*);
}

- (id)initWithState:(UIAppState*)state
         withParent:(UIView*)parent
            withKey:(const string&)key
       withCallback:(void(^)(DashboardCardContainer*))callback;

@end  // DashboardCardContainer

// local variables:
// mode: objc
// end:
