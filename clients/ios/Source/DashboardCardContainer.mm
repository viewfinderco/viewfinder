// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.

#import "Appearance.h"
#import "DashboardCardContainer.h"
#import "UIView+geometry.h"
#import "ValueUtils.h"

namespace {

const int kSpacing = 8;

}  // namespace

@implementation DashboardCardContainer

- (id)initWithState:(UIAppState*)state
         withParent:(UIView*)parent
            withKey:(const string&)key
       withCallback:(void(^)(DashboardCardContainer*))callback {
  if (self = [super init]) {
    parent_ = parent;
    callback_ = callback;

    self.frame = parent.bounds;

    login_signup_card_ = [[LoginSignupDashboardCard alloc]
                           initWithState:state
                              withParent:self
                                 withKey:key];

    login_signup_card_.frameWidth = self.frameWidth - kSpacing * 2;
    [self addSubview:login_signup_card_];
  }
  return self;
}

- (void)willMoveToSuperview:(UIView*)new_superview {
  if (new_superview) {
    keyboard_will_show_.Init(
        UIKeyboardWillShowNotification,
        ^(NSNotification* n) {
          if (login_signup_card_) {
            const Dict d(n.userInfo);
            keyboard_frame_ =
                d.find_value(UIKeyboardFrameEndUserInfoKey).rect_value();
            keyboard_frame_ =
                [parent_ convertRect:keyboard_frame_ fromView:NULL];
            const double duration =
                d.find_value(UIKeyboardAnimationDurationUserInfoKey).double_value();
            const int curve =
                d.find_value(UIKeyboardAnimationCurveUserInfoKey).int_value();
            const int options =
                (curve << 16) | UIViewAnimationOptionBeginFromCurrentState;
            [UIView animateWithDuration:duration
                                  delay:0
                                options:options
                             animations:^{
                self.backgroundColor = MakeUIColor(0, 0, 0, 0.7);
                self.frameHeight = keyboard_frame_.origin.y;
                login_signup_card_.keyboardVisible = true;
                [login_signup_card_ setFrame:login_signup_card_.frame];
              }
           completion:NULL];
          }
        });
    keyboard_will_hide_.Init(
        UIKeyboardWillHideNotification,
        ^(NSNotification* n) {
          keyboard_frame_ = CGRectZero;
          if (login_signup_card_) {
            const Dict d(n.userInfo);
            const double duration =
                d.find_value(UIKeyboardAnimationDurationUserInfoKey).double_value();
            const int curve =
                d.find_value(UIKeyboardAnimationCurveUserInfoKey).int_value();
            const int options =
                (curve << 16) | UIViewAnimationOptionBeginFromCurrentState;
            [UIView animateWithDuration:duration
                                  delay:0
                                options:options
                             animations:^{
                self.alpha = 0;
                self.frame = parent_.bounds;
                login_signup_card_.keyboardVisible = false;
                [login_signup_card_ setFrame:login_signup_card_.frame];
              }
                             completion:^(BOOL finished) {
                callback_(self);
                callback_ = NULL;
                login_signup_card_ = NULL;
              }];
          }
        });
  } else {
    keyboard_will_show_.Clear();
    keyboard_will_hide_.Clear();
  }
}

@end  // DashboardCardContainer
