// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <UIKit/UIKit.h>
#import "LoginEntryDetails.pb.h"
#import "PhoneNumberFormatter.h"

class UIAppState;
@class AnimatedStat;
@class IdentityTextField;
@class MyInfoButton;
@class StatButton;
@class TextLayer;

extern const string kAddIdentityKey;
extern const string kChangePasswordKey;
extern const string kLoginEntryDetailsKey;

void GetLoginEntryDetails(
    UIAppState* state, const string& key, LoginEntryDetails* details);
void SetLoginEntryDetails(
    UIAppState* state, const string& key, const LoginEntryDetails& details);

@interface DashboardCard : UIView {
 @private
  bool keyboard_visible_;
}

@property (nonatomic) bool keyboardVisible;

@end  // DashboardCard

@interface AccountSetupDashboardCard : DashboardCard {
 @private
  UIAppState* state_;
  UIImageView* background_;
  UILabel* title_;
  UIButton* import_;
  UIButton* skip_;
  UIActivityIndicatorView* import_indicator_;
}

- (id)initWithState:(UIAppState*)state;

@end  // AccountSetupDashboardCard

@interface DefaultDashboardCard : DashboardCard {
 @private
  UIAppState* state_;
  MyInfoButton* my_info_;
  StatButton* photos_stat_;
  StatButton* contacts_stat_;
  StatButton* convos_stat_;
  UIView* divider_;
  UIButton* my_info_button_;
  UIButton* contacts_;
  UIButton* settings_;
  UIView* toolbar_divider1_;
  UIView* toolbar_divider2_;
}

- (id)initWithState:(UIAppState*)state;
- (void)rebuild;
- (void)startAnimating;

@end  // DefaultDashboardCard

@interface MaintenanceDashboardCard : DashboardCard {
 @private
  UIAppState* state_;
  UIView* overlay_;
  UIActivityIndicatorView* activity_indicator_;
  TextLayer* title_;
  TextLayer* text_;
}

@property (nonatomic) bool showActivity;

- (id)initWithState:(UIAppState*)state;
- (void)setMessage:(const string&)message body:(const string&)body;

@end  // MaintenanceDashboardCard

@interface LoginSignupDashboardCard
    : DashboardCard<UITextFieldDelegate> {
 @private
  UIAppState* state_;
  string details_key_;
  __weak UIView* parent_;
  UIImageView* background_;
  UILabel* title_;
  TextLayer* error_;
  UIImageView* bottom_bg_;
  UIImageView* middle_bg_;
  UIImageView* single_bg_;
  UIImageView* top_bg_;
  UIView* name_divider_;
  UITextField* first_;
  UITextField* last_;
  IdentityTextField* identity_;
  UITextField* password1_;
  UITextField* password2_;
  UITextField* code_;
  UITextField* dummy_;
  UIButton* signup_toggle_;
  UIButton* login_toggle_;
  UIButton* cancel_;
  UIButton* submit_;
  UIActivityIndicatorView* submit_indicator_;
  UIButton* forgot_password_;
  UIButton* resend_code_;
  LoginEntryDetails::LoginType login_type_;
  LoginEntryDetails login_details_;
  bool reset_password_;
  WallTime last_resend_;
}

@property (nonatomic, readonly) bool changingPassword;
@property (nonatomic, readonly) bool confirmMode;
@property (nonatomic, readonly) bool minimized;

+ (void)prepareForLoginSignup:(UIAppState*)state
                       forKey:(const string&)key;
+ (void)prepareForLinkIdentity:(UIAppState*)state
                        forKey:(const string&)key;
+ (void)prepareForLinkMobileIdentity:(UIAppState*)state
                              forKey:(const string&)key;
+ (void)prepareForChangePassword:(UIAppState*)state
                          forKey:(const string&)key;
+ (void)prepareForResetDeviceId:(UIAppState*)state
                         forKey:(const string&)key;

- (id)initWithState:(UIAppState*)state
         withParent:(UIView*)parent
            withKey:(const string&)details_key;
- (void)confirmedIdentity:(NSString*)msg;
- (void)showLogin:(id)sender;

@end  // LoginSignupDashboardCard

// local variables:
// mode: objc
// end:
