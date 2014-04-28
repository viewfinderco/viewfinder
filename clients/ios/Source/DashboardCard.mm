// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <QuartzCore/QuartzCore.h>
#import "AddressBookManager.h"
#import "Analytics.h"
#import "Appearance.h"
#import "AsyncState.h"
#import "AttrStringUtils.h"
#import "CALayer+geometry.h"
#import "ContactManager.h"
#import "ContactMetadata.pb.h"
#import "CppDelegate.h"
#import "DashboardCard.h"
#import "DashboardCardContainer.h"
#import "DayTable.h"
#import "DBFormat.h"
#import "Defines.h"
#import "IdentityManager.h"
#import "IdentityTextField.h"
#import "Logging.h"
#import "NetworkManager.h"
#import "PhotoTable.h"
#import "PhotoView.h"
#import "RootViewController.h"
#import "TextLayer.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kAnimatedStatDelay = 0.020;

const float kCardContainerShadowInset = 2;
const float kSpacing = 8;
const float kTextRightMargin = 4;
const float kTextVerticalInset = 9;
const float kTextPadding = 12;
const float kTitleBaseline = 28;
const float kStatsOffset = 48;
const float kStatsHeight = 34;
const float kStatsBottomMargin = 43.5;
const float kMaxTitleScale = 0.5;
const float kStatsSpacing = 80;
const float kStatsLeading = 15;
const float kToolbarButtonTitleTopMargin = 32;
const float kLoginEntryFieldHeight = 24;
const float kMaintenanceActivitySpacing = 32;

const float kModalTopInset = 17;
const float kModalBottomInset = 22;

const float kTabLoginExtraSpacing = 8;
const float kTabSignupExtraSpacing = 0;

// The server tells us how many digits it is expecting; this value is used only as a fallback
// during error conditions.
const int kConfirmationCodeLength = 4;

const float kToolbarDividerMargin = 8;
const float kToolbarDividerHeight = 40;

const string kNumPhotosKey = "num_photos";
const string kNumContactsKey = "num_contacts";
const string kNumConvosKey = "num_convos";

LazyStaticUIFont kLoginSignupButtonUIFont = {
  kProximaNovaBold, 20
};
LazyStaticUIFont kLoginSignupEntryUIFont = {
  kProximaNovaRegular, 20
};
LazyStaticCTFont kMaintenanceBodyFont = {
  kProximaNovaRegular, 14
};
LazyStaticCTFont kMaintenanceTitleFont = {
  kProximaNovaBold, 20
};
LazyStaticUIFont kSignupButtonUIFont = {
  kProximaNovaBold, 20
};
LazyStaticCTFont kSignupMessageFont = {
  kProximaNovaRegular, 14
};
LazyStaticCTFont kSignupBoldMessageFont = {
  kProximaNovaBold, 14
};
LazyStaticCTFont kSignupTitleFont = {
  kProximaNovaBold, 20
};
LazyStaticUIFont kSignupTitleUIFont = {
  kProximaNovaBold, 20
};
LazyStaticCTFont kSubtitleFont = {
  kProximaNovaRegular, 18
};
LazyStaticCTFont kStatsValueFont = {
  kProximaNovaBold, 17
};
LazyStaticUIFont kStatsTitleFont = {
  kProximaNovaRegular, 12
};
LazyStaticUIFont kTextButtonFont = {
  kProximaNovaRegular, 14
};
LazyStaticCTFont kTitleFont = {
  kProximaNovaRegular, 28
};
LazyStaticUIFont kToolbarFont = {
  kProximaNovaRegular, 12
};
LazyStaticHexColor kDividerColor = { "#cfcbcb" };
LazyStaticHexColor kLoginSignupToggleColor = { "#ffffff" };
LazyStaticHexColor kMaintenanceTextColor = { "#ece9e9" };
LazyStaticHexColor kSignupMergeColor = { "#ec8d27" };
LazyStaticHexColor kSignupMessageColor = { "#ffffff" };
LazyStaticHexColor kSignupTextColor = { "#3f3e3e" };
LazyStaticHexColor kSignupTitleColor = { "#ffffff" };
LazyStaticHexColor kStatsValueColor = { "#ff9625" };
LazyStaticHexColor kStatsTitleColor = { "#9f9c9c" };
LazyStaticHexColor kStatsTitleColorActive = { "#3f3e3e" };
LazyStaticHexColor kTitleColor = { "#3f3f3e" };
LazyStaticHexColor kToolbarButtonColor = { "#9f9c9c" };
LazyStaticHexColor kToolbarButtonActiveColor = { "#3f3e3e" };

LazyStaticImage kDashboardCardContainer(
    @"dashboard-card-container", UIEdgeInsetsMake(7, 7, 7, 7));

LazyStaticImage kSignupCodeVerified(
    @"signup_code_verified_icon.png");

LazyStaticImage kEditIcon(
    @"edit-icon.png");

LazyStaticImage kSignupTextFieldBottom(
    @"signup-text-inputs-bottom.png", UIEdgeInsetsMake(1, 4, 4, 5));
LazyStaticImage kSignupTextFieldMiddle(
    @"signup-text-inputs-middle.png", UIEdgeInsetsMake(4, 4, 1, 5));
LazyStaticImage kSignupTextFieldSingle(
    @"signup-text-inputs-single.png", UIEdgeInsetsMake(4, 4, 5, 5));
LazyStaticImage kSignupTextFieldTop(
    @"signup-text-inputs-top.png", UIEdgeInsetsMake(4, 4, 1, 5));

LazyStaticImage kSquareModal(
    @"square-modal.png", UIEdgeInsetsMake(49, 49, 49, 49));
LazyStaticImage kTabsModalDefault(
    @"tabs-modal-default.png", UIEdgeInsetsMake(68, 0, 30, 0));
LazyStaticImage kTabsModalLoginSelected(
    @"tabs-modal-login-selected.png", UIEdgeInsetsMake(68, 0, 30, 0));
LazyStaticImage kTabsModalSignupSelected(
    @"tabs-modal-signup-selected.png", UIEdgeInsetsMake(68, 0, 30, 0));

LazyStaticImage kDashboardContacts(
    @"dashboard-contacts.png");
LazyStaticImage kDashboardContactsActive(
    @"dashboard-contacts-active.png");
LazyStaticImage kDashboardMyInfo(
    @"dashboard-myinfo.png");
LazyStaticImage kDashboardMyInfoActive(
    @"dashboard-myinfo-active.png");
LazyStaticImage kDashboardSettings(
    @"dashboard-settings.png");
LazyStaticImage kDashboardSettingsActive(
    @"dashboard-settings-active.png");

const LoginEntryDetails::LoginType SIGN_UP = LoginEntryDetails::SIGN_UP;
const LoginEntryDetails::LoginType LOG_IN = LoginEntryDetails::LOG_IN;
const LoginEntryDetails::LoginType RESET = LoginEntryDetails::RESET;
const LoginEntryDetails::LoginType LINK = LoginEntryDetails::LINK;
const LoginEntryDetails::LoginType MERGE = LoginEntryDetails::MERGE;
const LoginEntryDetails::LoginType CHANGE_PASSWORD = LoginEntryDetails::CHANGE_PASSWORD;
const LoginEntryDetails::LoginType RESET_DEVICE_ID = LoginEntryDetails::RESET_DEVICE_ID;

enum ModalType {
  MODAL_SQUARE = 1,
  MODAL_TABS_DEFAULT,
  MODAL_TABS_LOG_IN_SELECTED,
  MODAL_TABS_SIGN_UP_SELECTED,
};

const char* kCodePlaceholder = "Enter %d-Digit Code";
NSString* const kLoginSignupCancelTitle[] = {
  @"Cancel",              // SIGN_UP
  @"Cancel",              // LOG_IN
  @"Back",                // RESET
  @"Cancel",              // LINK
  @"Cancel",              // CHANGE_PASSWORD
  @"No",                  // MERGE
  @"Cancel",              // RESET_DEVICE_ID
};
NSString* const kLoginSignupSubmitTitle[] = {
  @"Create Account",      // SIGN_UP
  @"Log In",              // LOG_IN
  @"Submit",              // RESET
  @"Add",                 // LINK
  @"Submit",              // CHANGE_PASSWORD
  @"Yes",                 // MERGE
  @"Log In",              // RESET_DEVICE_ID
};

const string* kEndpoint[] = {
  &AppState::kRegisterEndpoint,     // SIGN_UP
  &AppState::kLoginEndpoint,        // LOG_IN
  &AppState::kLoginResetEndpoint,   // RESET
  &AppState::kMergeTokenEndpoint,   // LINK
  NULL,                             // CHANGE_PASSWORD
  &AppState::kMergeTokenEndpoint,   // MERGE
  &AppState::kLoginEndpoint,        // RESET_DEVICE_ID
};

UIButton* NewToolbarButton(NSString* title, UIImage* image, UIImage* active) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.titleLabel.font = kToolbarFont;
  [b setTitle:title
     forState:UIControlStateNormal];
  [b setTitleColor:kToolbarButtonColor
          forState:UIControlStateNormal];
  [b setTitleColor:kToolbarButtonActiveColor
          forState:UIControlStateHighlighted];
  b.titleEdgeInsets = UIEdgeInsetsMake(kToolbarButtonTitleTopMargin, 0, 0, 0);
  [b setBackgroundImage:image
               forState:UIControlStateNormal];
  [b setBackgroundImage:active
               forState:UIControlStateHighlighted];
  [b sizeToFit];
  return b;
}

UIView* NewHorizontalDivider() {
  UIView* divider = [UIView new];
  divider.autoresizingMask = UIViewAutoresizingFlexibleWidth;
  divider.backgroundColor = kDividerColor;
  divider.frameHeight = UIStyle::kDividerSize;
  return divider;
}

UIButton* NewLoginSignupToggle(
    NSString* title, UIFont* font,
    UIEdgeInsets content_insets, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.contentEdgeInsets = content_insets;
  b.titleLabel.font = font;
  [b setTitle:title
     forState:UIControlStateNormal];
  [b setTitleColor:kLoginSignupToggleColor
          forState:UIControlStateNormal];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  [b sizeToFit];
  return b;
}

UIButton* NewSignupToggle(id target, SEL selector) {
  return NewLoginSignupToggle(
      @"Sign Up", kLoginSignupButtonUIFont,
      UIEdgeInsetsMake(9, 13, 13, 29),
      target, selector);
}

UIButton* NewLoginToggle(id target, SEL selector) {
  return NewLoginSignupToggle(
      @"Log In", kLoginSignupButtonUIFont,
      UIEdgeInsetsMake(9, 29, 13, 13),
      target, selector);
}

UIButton* NewTextButton(id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.contentEdgeInsets = UIEdgeInsetsMake(8, 13, 8, 13);
  b.contentHorizontalAlignment = UIControlContentHorizontalAlignmentCenter;
  b.contentVerticalAlignment = UIControlContentVerticalAlignmentCenter;
  b.titleLabel.font = kTextButtonFont;
  b.titleLabel.lineBreakMode = NSLineBreakByWordWrapping;
  b.titleLabel.textAlignment = NSTextAlignmentLeft;
  [b setTitleColor:kSignupMessageColor
          forState:UIControlStateNormal];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  [b sizeToFit];
  b.frameHeight = kLoginEntryFieldHeight + kSpacing * 2;
  return b;
}

UIButton* NewForgotPassword(id target, SEL selector) {
  UIButton* b = NewTextButton(target, selector);
  [b setTitle:@"Forgot your password?"
     forState:UIControlStateNormal];
  return b;
}

UIButton* NewResendCode(id target, SEL selector) {
  UIButton* b = NewTextButton(target, selector);
  [b setTitle:@"Send code again?"
     forState:UIControlStateNormal];
  return b;
}

void StyleTextField(UITextField* text_field) {
  text_field.backgroundColor = [UIColor clearColor];
  text_field.borderStyle = UITextBorderStyleNone;
  text_field.clearButtonMode = UITextFieldViewModeWhileEditing;
  text_field.contentVerticalAlignment = UIControlContentVerticalAlignmentCenter;
  text_field.font = kLoginSignupEntryUIFont;
  text_field.frameHeight = kLoginEntryFieldHeight;
  text_field.keyboardAppearance = UIKeyboardAppearanceLight;
  text_field.textColor = kSignupTextColor;
}

UITextField* NewTextField(NSString* placeholder) {
  UITextField* text_field = [UITextField new];
  // Dummy inputAccessoryView ensures that we get keyboardWillShow notifications even when
  // a hardware keyboard is used instead of the on-screen one.
  text_field.inputAccessoryView = [UIView new];
  text_field.placeholder = placeholder;
  StyleTextField(text_field);
  return text_field;
}

UIView* NewVerticalDivider() {
  UIView* divider = [UIView new];
  divider.backgroundColor = kDividerColor.get();
  divider.frameWidth = UIStyle::kDividerSize;
  return divider;
}

CAKeyframeAnimation* NewShakeAnimation() {
  CAKeyframeAnimation* a = [CAKeyframeAnimation animationWithKeyPath:@"transform"];
  a.autoreverses = YES;
  a.duration = 0.07;
  a.repeatCount = 2.0;
  a.values = Array(
      CATransform3DMakeTranslation(-5, 0, 0),
      CATransform3DMakeTranslation(5, 0, 0));
  return a;
}

void ScaleTextToFit(TextLayer* text_layer, float max_width, float max_scale) {
  // Scale the title to fit, using multiple lines if necessary.
  text_layer.maxWidth = CGFLOAT_MAX;
  if (text_layer.frameWidth <= max_width) {
    return;
  }
  float s = max_width / text_layer.frameWidth;
  if (s < max_scale) {
    s = max_scale;
    text_layer.maxWidth = max_width / s;
  }
  text_layer.transform = CATransform3DMakeScale(s, s, 1);
}

bool IsDigit(int chr) {
  return chr >= '0' && chr <= '9';
}

int CountDigits(NSString* str) {
  int count = 0;
  for (int i = 0; i < str.length; i++) {
    if (IsDigit([str characterAtIndex:i])) {
      count++;
    }
  }
  return count;
}

// Returns a position just after the nth digit.
int SkipNDigits(NSString* str, int n) {
  int num_digits = 0;
  for (int i = 0; i < str.length; i++) {
    if (IsDigit([str characterAtIndex:i])) {
      num_digits++;
      if (num_digits >= n) {
        return i + 1;
      }
    }
  }
  // We expect to find N digits unless the string was empty.
  DCHECK_EQ(str.length, 0);
  DCHECK_EQ(n, 0);
  return str.length;
}

// Returns a formatted version of str, either for display (with spaces every n
// digits, where n = {3, 4} depending on whether the code length is divisible
// by 3 or 4) or for the server (all non-digits removed)
//
// TODO(ben): there's a lot of overlap between this and PhoneNumberFormatter;
// consider making a generic number-formatting text field.
NSString* FormatCodeString(NSString* str, int code_length) {
  int spaces_every_n_digits = 0;
  if (code_length % 3 == 0) {
    spaces_every_n_digits = 3;
  } else if (code_length % 4 == 0) {
    spaces_every_n_digits = 4;
  }

  NSMutableString* new_str = [NSMutableString new];
  int num_digits = 0;
  for (int i = 0; i < str.length; i++) {
    int chr = [str characterAtIndex:i];
    if (!IsDigit(chr)) {
      continue;
    }
    [new_str appendFormat:@"%c", chr];
    num_digits++;
    if (spaces_every_n_digits && (num_digits % spaces_every_n_digits == 0)) {
      [new_str appendFormat:@"%c", ' '];
    }
  }
  return new_str;
}

void AuthViewfinder(
    UIAppState* state, const string& endpoint, const string& identity,
    const string& password, const string& first, const string& last,
    const string& name, bool error_if_linked,
    void (^done)(int, int, const string&)) {
  if (state->fake_logout()) {
    const string identity_copy(identity);
    const string password_copy(password);
    state->async()->dispatch_after_low_priority(1, ^{
        if (identity_copy == "Email:exists@emailscrubbed.com") {
          done(403, ErrorResponse::UNKNOWN, "Fake user already exists error.");
        } else if (password_copy == "bad") {
          done(403, ErrorResponse::UNKNOWN, "Fake signup/login error.");
        } else if (password_copy == "-") {
          done(403, ErrorResponse::NO_USER_ACCOUNT, "");
        } else {
          done(200, ErrorResponse::OK, "");
          if (endpoint == UIAppState::kLoginEndpoint) {
            state->FakeLogin();
          }
        }
      });
  } else {
    state->net_manager()->AuthViewfinder(
        endpoint, identity, password, first, last,
        name, error_if_linked, done);
  }
}

void VerifyViewfinder(
    UIAppState* state, const string& identity, const string& access_token,
    bool manual_entry, void (^done)(int, int, const string&)) {
  if (state->fake_logout()) {
    const string access_token_copy(access_token);
    state->async()->dispatch_after_low_priority(1, ^{
        if (access_token_copy == "1111" || access_token_copy == "111111111") {
          done(403, ErrorResponse::UNKNOWN, "Fake verification error.");
        } else {
          done(200, ErrorResponse::OK, "");
          state->FakeLogin();
        }
      });
  } else {
    state->net_manager()->VerifyViewfinder(
        identity, access_token, manual_entry, done);
  }
}

const DBRegisterKeyIntrospect kAnimatedStatKeyIntrospect(
    DBFormat::animated_stat_key(""), NULL, ^(Slice value) {
      return value.ToString();
    });

void PopulateLoginEntryDetails(LoginEntryDetails* details) {
#ifdef SIGNUP_FIRST_NAME
  details->set_first(SIGNUP_FIRST_NAME);
#endif
#ifdef SIGNUP_LAST_NAME
  details->set_last(SIGNUP_LAST_NAME);
#endif
#ifdef SIGNUP_IDENTITY
  details->set_identity_text(SIGNUP_IDENTITY);
#endif
#ifdef SIGNUP_PASSWORD
  details->set_password(SIGNUP_PASSWORD);
#endif
}

}  // namespace

const string kAddIdentityKey =
    DBFormat::metadata_key("add_identity_details");
const string kChangePasswordKey =
    DBFormat::metadata_key("change_password_details");
const string kLoginEntryDetailsKey =
    DBFormat::metadata_key("login_entry_details");

void GetLoginEntryDetails(
    UIAppState* state, const string& key, LoginEntryDetails* details) {
  if (!state->fake_logout()) {
    if (state->db()->GetProto(key, details)) {
      return;
    }
  }
}

void SetLoginEntryDetails(
    UIAppState* state, const string& key, const LoginEntryDetails& details) {
  if (!state->fake_logout()) {
    state->db()->PutProto(key, details);
  }
}

@interface AnimatedStat : UIView {
 @private
  UIAppState* state_;
  string key_;
  int value_;
  int current_value_;
  TextLayer* text_;
  NSTimer* timer_;
}

@property (nonatomic) int value;
@property (nonatomic, readonly) TextLayer* text;

- (id)initWithState:(UIAppState*)state
             forKey:(const string&)key;
- (void)startAnimating;

@end  // AnimatedStat

@implementation AnimatedStat

@synthesize text = text_;

- (id)initWithState:(UIAppState*)state
             forKey:(const string&)key {
  if (self = [super init]) {
    state_ = state;
    key_ = DBFormat::animated_stat_key(key);
    self.userInteractionEnabled = NO;
  }

  return self;
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];
  text_.frame = self.bounds;
}

- (void)startAnimating {
  if (current_value_ == value_ || timer_) {
    return;
  }
  timer_ = [NSTimer scheduledTimerWithTimeInterval:kAnimatedStatDelay
                                            target:self
                                          selector:@selector(incrementStat)
                                          userInfo:NULL
                                           repeats:NO];
}

- (void)incrementStat {
  timer_ = NULL;
  const int diff = fabs(value_ - current_value_);
  const int step = std::min<int>(diff, std::max<int>(1, diff / 10));
  self.currentValue = current_value_ + ((value_ > current_value_) ? step : -step);
  [self startAnimating];
}

- (void)setCurrentValue:(int)current_value {
  current_value_ = current_value;
  state_->db()->Put<int>(key_, current_value_);
  text_.attrStr = NewAttrString(ToString(LocalizedNumberFormat(current_value_)),
                                kStatsValueFont, kStatsValueColor.get().CGColor);
  self.frameSize = text_.frameSize;
}

- (int)value {
  return value_;
}

- (void)setValue:(int)value {
  if (!text_) {
    text_ = [TextLayer new];
    [self.layer addSublayer:text_];
    //[self setCurrentValue:0];
    [self setCurrentValue:state_->db()->Get<int>(key_, 0)];
  }
  value_ = value;
  // Don't animate decreasing values.
  if (value_ < current_value_) {
    [self setCurrentValue:value_];
  }
}

@end  // AnimatedStat


@interface StatButton : UIButton {
 @private
  AnimatedStat* stat_;
}

- (id)initWithState:(UIAppState*)state
             forKey:(const string&)key
          withTitle:(const string&)title
             target:(id)target
           selector:(SEL)selector;

@property (nonatomic) AnimatedStat* stat;

@end  // StatButton

@implementation StatButton

@synthesize stat = stat_;

- (id)initWithState:(UIAppState*)state
             forKey:(const string&)key
          withTitle:(const string&)title
             target:(id)target
           selector:(SEL)selector {
  if (self = [super init]) {
    self.contentHorizontalAlignment = UIControlContentHorizontalAlignmentLeft;
    self.contentVerticalAlignment = UIControlContentVerticalAlignmentBottom;
    [self setTitle:NewNSString(title)
          forState:UIControlStateNormal];
    self.titleLabel.font = kStatsTitleFont;
    self.titleEdgeInsets = UIEdgeInsetsMake(0, 0, 0, 0);
    [self setTitleColor:kStatsTitleColor
               forState:UIControlStateNormal];
    [self setTitleColor:kStatsTitleColorActive
               forState:UIControlStateHighlighted];
    [self addTarget:target
             action:selector
          forControlEvents:UIControlEventTouchUpInside];
    self.frameSize = CGSizeMake(kStatsSpacing, kStatsHeight);

    stat_ = [[AnimatedStat alloc] initWithState:state forKey:key];
    [self addSubview:stat_];
  }

  return self;
}

@end  // StatButton


@interface MyInfoButton : UIButton {
 @private
  TextLayer* name_;
}

@property (nonatomic, readonly) float baseline;

- (id)initWithTarget:(id)target
         forSelector:(SEL)selector;
- (void)setName:(NSAttributedString*)name;

@end  // MyInfoButton

@implementation MyInfoButton

- (id)initWithTarget:(id)target
         forSelector:(SEL)selector {
  if (self = [super init]) {
    self.contentHorizontalAlignment = UIControlContentHorizontalAlignmentLeft;
    self.contentVerticalAlignment = UIControlContentVerticalAlignmentBottom;
    [self setImage:kEditIcon forState:UIControlStateNormal];
    [self addTarget:target
             action:selector
          forControlEvents:UIControlEventTouchUpInside];

    name_ = [TextLayer new];
    [self.layer addSublayer:name_];
  }

  return self;
}

- (void)setFrame:(CGRect)f {
  const float avail_width = f.size.width - kEditIcon.get().size.width - kTextPadding * 2;
  name_.transform = CATransform3DIdentity;
  name_.anchorPoint = CGPointMake(0, 0);
  name_.frameLeft = kTextPadding;
  ScaleTextToFit(name_, avail_width, kMaxTitleScale);
  f.size = CGSizeMake(name_.frameRight + kTextPadding + kEditIcon.get().size.width,
                      std::max<float>(name_.frameHeight, kEditIcon.get().size.height));

  self.imageEdgeInsets = UIEdgeInsetsMake(0, name_.frameRight + kTextPadding,
                                          name_.descent, 0);
  [super setFrame:f];
}

- (float)baseline {
  return name_.baseline;
}

- (void)setName:(NSAttributedString*)name_str {
  name_.attrStr = name_str;
}

@end  // MyInfoButton


@implementation DashboardCard

@synthesize keyboardVisible = keyboard_visible_;

@end  // DashboardCard

@implementation AccountSetupDashboardCard

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;

    self.autoresizesSubviews = YES;
    self.backgroundColor = [UIColor clearColor];

    title_ = [UILabel new];
    title_.backgroundColor = [UIColor clearColor];
    title_.font = kSignupTitleUIFont;
    title_.frameHeight = title_.font.lineHeight;
    title_.textAlignment = NSTextAlignmentCenter;
    title_.textColor = kLoginSignupToggleColor;
    title_.text = @"Connect with Friends";
    [self addSubview:title_];

    import_ = UIStyle::NewSignupButtonGreen(
        @"Import Mobile Contacts", kSignupButtonUIFont, self, @selector(import));
    [self addSubview:import_];

    import_indicator_ =
        [[UIActivityIndicatorView alloc]
          initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleWhite];

    skip_ = NewTextButton(self, @selector(skipImport));
    [skip_ setTitle:@"Skip contacts import"
           forState:UIControlStateNormal];
    [self addSubview:skip_];
  }
  return self;
}

- (void)setFrame:(CGRect)f {
  {
    const ScopedDisableCAActions disable_ca_actions;
    f.size.height = [self setSubviewFrames:f];
    f.origin.x = kSpacing;
    [self setBackground:f.size];
  }

  const float parent_height = self.superview.boundsHeight;
  f.origin.y = (parent_height - f.size.height) / 2;

  [super setFrame:f];
}

- (float)setSubviewFrames:(CGRect)f {
  float y = kSpacing;
  float w = f.size.width - kSpacing * 2;

  title_.frameOrigin = CGPointMake(kSpacing, y);
  title_.frameWidth = w;
  y = ceilf(title_.frameBottom) + kSpacing * 2;

  import_.frameOrigin = CGPointMake(kSpacing, y);
  import_.frameWidth = w;
  y = ceilf(import_.frameBottom);

  skip_.frameOrigin = CGPointMake(kSpacing, y);
  skip_.frameWidth = w;
  y = ceilf(skip_.frameBottom);

  return y;
}

- (void)disableImport {
  [import_ addSubview:import_indicator_];
  [import_indicator_ centerFrameWithinSuperview];
  [import_indicator_ startAnimating];
  [import_ setTitle:@""
           forState:UIControlStateNormal];
  import_.enabled = NO;
}

- (void)setBackground:(CGSize)size {
  if (!background_) {
    background_ = [[UIImageView alloc] initWithImage:kSquareModal];
    background_.frameLeft = -kSpacing;
    background_.frameTop = -kModalTopInset;
    background_.tag = MODAL_SQUARE;
  }
  background_.frameWidth = size.width + kSpacing * 2;
  background_.frameHeight = size.height + kModalTopInset + kModalBottomInset;
  if (!background_.superview) {
    [self insertSubview:background_ atIndex:0];
  }
}

- (bool)hasPhoneLinked {
  ContactMetadata m;
  state_->contact_manager()->LookupUser(state_->user_id(), &m);
  if (ContactManager::GetPhoneIdentity(m, NULL)) {
    // A fully linked and confirmed identity.
    return true;
  }
  return false;
}

- (void)maybeLinkPhone {
  state_->analytics()->AddContactsLinkPhoneStart();
  CppDelegate* cpp_delegate = new CppDelegate;
  cpp_delegate->Add(
      @protocol(UIAlertViewDelegate), @selector(alertView:clickedButtonAtIndex:),
      ^(UIAlertView* alert, NSInteger index) {
        if (index == 1) {
          [LoginSignupDashboardCard
            prepareForLinkMobileIdentity:state_
                                  forKey:kAddIdentityKey];
          UIView* container = [[DashboardCardContainer alloc]
                                initWithState:state_
                                   withParent:self.superview
                                      withKey:kAddIdentityKey
                                 withCallback:^(DashboardCardContainer* container) {
              [container removeFromSuperview];
              [self importDone];
            }];
          [self.superview addSubview:container];
        } else {
          [self importDone];
        }
        alert.delegate = NULL;
        delete cpp_delegate;
      });

  [[[UIAlertView alloc]
           initWithTitle:@"Add Mobile Number"
                 message:@"Help your friends find you on Viewfinder."
                delegate:cpp_delegate->delegate()
       cancelButtonTitle:@"Skip"
       otherButtonTitles:@"OK", NULL] show];
}

- (void)import {
  state_->analytics()->OnboardingImportContacts();
  [self disableImport];
  state_->address_book_manager()->ImportContacts(^(bool success) {
      if (success) {
        state_->analytics()->ContactsFetchComplete("AddressBook");
        if ([self hasPhoneLinked]) {
          [self importDone];
        } else {
          [self maybeLinkPhone];
        }
      } else {
        [[[UIAlertView alloc]
            initWithTitle:@"Permission denied"
                  message:@"To import your address book you must grant access to your contacts. "
           "Enable access via: Settings > Privacy > Contacts > Viewfinder"
                 delegate:NULL
           cancelButtonTitle:@"OK"
           otherButtonTitles:NULL]
          show];
        state_->analytics()->ContactsFetchError("AddressBook", "import_failed");
        [self importDone];
      }
    });
}

- (void)importDone {
  state_->set_account_setup(false);
  state_->analytics()->OnboardingComplete();
  [state_->root_view_controller() showInbox:ControllerState()];
}

- (void)skipImport {
  state_->analytics()->OnboardingSkipImportContacts();
  [self importDone];
}

@end  // AccountSetupDashboardCard

@implementation DefaultDashboardCard

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;

    self.autoresizesSubviews = YES;
    self.backgroundColor = [UIColor clearColor];

    // Dashboard card container.
    UIImageView* bg = [[UIImageView alloc] initWithImage:kDashboardCardContainer];
    bg.autoresizingMask =
        UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    bg.frame = CGRectInset(self.bounds, -kCardContainerShadowInset, -kCardContainerShadowInset);
    [self addSubview:bg];

    // Full name (added as a sublayer to the my info button).
    my_info_ = [[MyInfoButton alloc] initWithTarget:self forSelector:@selector(toolbarMyInfo:)];
    [self addSubview:my_info_];

    // Stats.
    photos_stat_ = [[StatButton alloc] initWithState:state_
                                              forKey:kNumPhotosKey
                                           withTitle:"Photos"
                                              target:self
                                            selector:@selector(statButtonPhotos:)];
    [self addSubview:photos_stat_];

    contacts_stat_ = [[StatButton alloc] initWithState:state_
                                                forKey:kNumContactsKey
                                             withTitle:"Contacts"
                                                target:self
                                              selector:@selector(statButtonContacts:)];
    [self addSubview:contacts_stat_];

    convos_stat_ = [[StatButton alloc] initWithState:state_
                                              forKey:kNumConvosKey
                                           withTitle:"Conversations"
                                              target:self
                                            selector:@selector(statButtonConvos:)];
    [self addSubview:convos_stat_];

    divider_ = NewHorizontalDivider();
    [self addSubview:divider_];

    // Toolbar buttons.
    my_info_button_ = NewToolbarButton(
        @"My Info", kDashboardMyInfo, kDashboardMyInfoActive);
    [my_info_button_ addTarget:self
                 action:@selector(toolbarMyInfo:)
        forControlEvents:UIControlEventTouchUpInside];
    [self addSubview:my_info_button_];

    contacts_ = NewToolbarButton(
        @"Contacts", kDashboardContacts, kDashboardContactsActive);
    [contacts_ addTarget:self
                  action:@selector(toolbarContacts:)
        forControlEvents:UIControlEventTouchUpInside];
    [self addSubview:contacts_];

    toolbar_divider1_ = NewVerticalDivider();
    toolbar_divider1_.frameHeight = kToolbarDividerHeight;
    [self addSubview:toolbar_divider1_];

    toolbar_divider2_ = NewVerticalDivider();
    toolbar_divider2_.frameHeight = kToolbarDividerHeight;
    [self addSubview:toolbar_divider2_];

    settings_ = NewToolbarButton(
        @"Settings", kDashboardSettings, kDashboardSettingsActive);
    [settings_ addTarget:self
                  action:@selector(toolbarSettings:)
        forControlEvents:UIControlEventTouchUpInside];
    [self addSubview:settings_];

  }
  return self;
}

- (void)setSubviewFrames:(CGRect)f {
  my_info_.frameWidth = f.size.width - kTextPadding * 2;
  my_info_.frameTop = kTitleBaseline - my_info_.baseline;

  float y = kStatsOffset;
  photos_stat_.frameLeft = kTextPadding;
  photos_stat_.frameTop = y;
  contacts_stat_.frameLeft = kTextPadding + kStatsSpacing;
  contacts_stat_.frameTop = y;
  convos_stat_.frameLeft = kTextPadding + kStatsSpacing * 2;
  convos_stat_.frameTop = y;

  y += kStatsBottomMargin;

  divider_.frameTop = y;
  y += divider_.frameHeight;

  float x = 0;
  my_info_button_.frameOrigin = CGPointMake(x, y);
  x = my_info_button_.frameRight;
  toolbar_divider1_.frameOrigin = CGPointMake(x, y + kToolbarDividerMargin);
  x += toolbar_divider1_.frameWidth;
  contacts_.frameOrigin = CGPointMake(x, y);
  x = contacts_.frameRight;
  toolbar_divider2_.frameOrigin = CGPointMake(x, y + kToolbarDividerMargin);
  x += toolbar_divider2_.frameWidth;
  settings_.frameOrigin = CGPointMake(x, y);
}

- (void)setFrame:(CGRect)f {
  [self setSubviewFrames:f];
  // Size card to fit content.
  f.size.height = settings_.frameBottom;
  f.origin.x = kSpacing;
  f.origin.y = self.superview.boundsHeight - f.size.height - kSpacing;
  [super setFrame:f];
}

- (void)startAnimating {
  [photos_stat_.stat startAnimating];
  [contacts_stat_.stat startAnimating];
  [convos_stat_.stat startAnimating];
}

- (void)statButtonPhotos:(UIView*)sender {
  state_->analytics()->DashboardPhotoCount();
  // Does nothing currently.
}

- (void)statButtonContacts:(UIView*)sender {
  state_->analytics()->DashboardContactCount();
  [state_->root_view_controller() showContacts:ControllerTransition(TRANSITION_SLIDE_OVER_UP)];
}

- (void)statButtonConvos:(UIView*)sender {
  state_->analytics()->DashboardConversationCount();
  [state_->root_view_controller() showInbox:ControllerTransition()];
}

- (void)toolbarMyInfo:(UIView*)sender {
  state_->analytics()->DashboardMyInfoButton();
  [state_->root_view_controller() showMyInfo:ControllerTransition(TRANSITION_SLIDE_OVER_UP)];
}

- (void)toolbarContacts:(UIView*)sender {
  state_->analytics()->DashboardContactsButton();
  [state_->root_view_controller() showContacts:ControllerTransition(TRANSITION_SLIDE_OVER_UP)];
}

- (void)toolbarSettings:(UIView*)sender {
  state_->analytics()->DashboardSettingsButton();
  [state_->root_view_controller() showSettings:ControllerTransition(TRANSITION_SLIDE_OVER_UP)];
}

- (void)rebuild {
  DayTable::SnapshotHandle snap = state_->day_table()->GetSnapshot(NULL);

  ContactMetadata c;
  string name_str = "Who are you?";
  state_->contact_manager()->LookupUser(state_->user_id(), &c);
  if (c.has_name()) {
    name_str = c.name();
  } else {
    LoginEntryDetails details;
    if (state_->db()->GetProto(kLoginEntryDetailsKey, &details)) {
      name_str = state_->contact_manager()->ConstructFullName(
          details.first(), details.last());
    }
  }
  [my_info_ setName:NewAttrString(name_str, kTitleFont, kTitleColor)];

  // Only enable the "My Info" button after we've retrieved the metadata for
  // the user. This usually happens immediately after the user registers, but
  // can sometimes take a few seconds in test environments.
  my_info_.enabled = c.has_user_id();

  photos_stat_.stat.value = snap->events()->photo_count();
  convos_stat_.stat.value = snap->conversations()->row_count();
  contacts_stat_.stat.value = state_->contact_manager()->viewfinder_count();

  [self startAnimating];
}

@end  // DefaultDashboardCard

@implementation MaintenanceDashboardCard

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;

    self.autoresizesSubviews = YES;
    self.backgroundColor = [UIColor clearColor];

    // Dashboard card container.
    overlay_ = [UIView new];
    overlay_.alpha = 0.65;
    overlay_.backgroundColor = [UIColor blackColor];
    [self addSubview:overlay_];

    title_ = [TextLayer new];
    [self.layer addSublayer:title_];

    text_ = [TextLayer new];
    [self.layer addSublayer:text_];

    activity_indicator_ =
        [[UIActivityIndicatorView alloc]
          initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleWhiteLarge];
    activity_indicator_.color = kMaintenanceTextColor;
    [self addSubview:activity_indicator_];
    [activity_indicator_ startAnimating];
  }
  return self;
}

- (void)setSubviewFrames:(CGRect)f {
  activity_indicator_.frameLeft =
      (f.size.width - activity_indicator_.frameWidth) / 2;
  activity_indicator_.frameTop = 0;
  float y = activity_indicator_.frameBottom + kMaintenanceActivitySpacing;

  const float max_width = f.size.width;
  title_.transform = CATransform3DIdentity;
  title_.anchorPoint = CGPointMake(0, 0);
  title_.frameOrigin = CGPointMake(0, y);
  title_.frameWidth = max_width;
  ScaleTextToFit(title_, max_width, kMaxTitleScale);
  y += title_.frameHeight;

  text_.maxWidth = max_width;
  text_.anchorPoint = CGPointMake(0, 0);
  text_.frameOrigin = CGPointMake(0, y);
  text_.frameWidth = max_width;
}

- (void)setFrame:(CGRect)f {
  [self setSubviewFrames:f];
  if (activity_indicator_.isAnimating) {
    f.size.height = activity_indicator_.frameBottom + kTextPadding;
  } else {
    f.size.height = text_.frameHeight + kTextPadding;
  }
  f.origin.x = kSpacing;
  f.origin.y = (self.superview.boundsHeight - f.size.height) / 2;
  overlay_.frame = CGRectOffset(
      self.superview.bounds, -f.origin.x, -f.origin.y);
  [super setFrame:f];
}

- (bool)showActivity {
  return activity_indicator_.isAnimating;
}

- (void)setShowActivity:(bool)show_activity {
  if (show_activity) {
    [activity_indicator_ startAnimating];
  } else {
    [activity_indicator_ stopAnimating];
  }
}

- (void)setMessage:(const string&)message
              body:(const string&)body {
  const ScopedDisableCAActions disable_ca_actions;
  title_.attrStr = AttrCenterAlignment(
      NewAttrString(message, kMaintenanceTitleFont, kMaintenanceTextColor));
  text_.attrStr  = AttrCenterAlignment(
      NewAttrString(body, kMaintenanceBodyFont, kMaintenanceTextColor));
  [self setFrame:self.frame];
}

@end  // MaintenanceDashboardCard

// Declare that LoginSignupDashboardCard adheres to the
// IdentityTextFieldDelegate protocol.
@interface LoginSignupDashboardCard (internal)<IdentityTextFieldDelegate>
@end  // LoginSignupDashboardCard (internal)<IdentityTextFieldDelegate>

@implementation LoginSignupDashboardCard

+ (void)prepareForLoginSignup:(UIAppState*)state
                       forKey:(const string&)key {
  LoginEntryDetails details;
  GetLoginEntryDetails(state, key, &details);
  if (details.type() != LOG_IN) {
    details.Clear();
    details.set_type(LOG_IN);
    PopulateLoginEntryDetails(&details);
    SetLoginEntryDetails(state, key, details);
  }
}

+ (void)prepareForLinkIdentity:(UIAppState*)state
                        forKey:(const string&)key {
  LoginEntryDetails details;
  GetLoginEntryDetails(state, key, &details);
  if (details.type() != LINK) {
    details.Clear();
    details.set_type(LINK);
    SetLoginEntryDetails(state, key, details);
  }
}

+ (void)prepareForLinkMobileIdentity:(UIAppState*)state
                              forKey:(const string&)key {
  LoginEntryDetails details;
  GetLoginEntryDetails(state, key, &details);
  if (details.type() != LINK ||
      details.identity_type() != LoginEntryDetails::PHONE_ONLY) {
    details.Clear();
    details.set_type(LINK);
    details.set_identity_type(LoginEntryDetails::PHONE_ONLY);
    SetLoginEntryDetails(state, key, details);
  }
}

+ (void)prepareForChangePassword:(UIAppState*)state
                          forKey:(const string&)key {
  LoginEntryDetails details;
  GetLoginEntryDetails(state, key, &details);
  if (details.type() != CHANGE_PASSWORD) {
    details.Clear();
    details.set_type(CHANGE_PASSWORD);
    SetLoginEntryDetails(state, key, details);
  }
}

+ (void)prepareForResetDeviceId:(UIAppState*)state
                         forKey:(const string&)key {
  LoginEntryDetails details;
  GetLoginEntryDetails(state, key, &details);
  details.Clear();
  details.set_type(RESET_DEVICE_ID);

  ContactMetadata c;
  if (state->contact_manager()->LookupUser(state->user_id(), &c)) {
    details.set_identity_type(
        IdentityManager::IsPhoneIdentity(c.primary_identity()) ?
        LoginEntryDetails::PHONE : LoginEntryDetails::EMAIL);
    details.set_identity_text(
        IdentityManager::IdentityToDisplayName(c.primary_identity()));
    details.set_identity_key(c.primary_identity());
  }

  SetLoginEntryDetails(state, key, details);
}

- (id)initWithState:(UIAppState*)state
         withParent:(UIView*)parent
            withKey:(const string&)details_key {
  if (self = [super init]) {
    state_ = state;
    details_key_ = details_key;
    parent_ = parent;
    login_type_ = SIGN_UP;
    LoginEntryDetails::IdentityType identity_type = LoginEntryDetails::EMAIL;

    self.autoresizesSubviews = YES;

    GetLoginEntryDetails(state, details_key_, &login_details_);
    if (login_details_.has_identity_type()) {
      identity_type = login_details_.identity_type();
    }
    if (login_details_.has_type()) {
      login_type_ = login_details_.type();
    }

    title_ = [UILabel new];
    title_.backgroundColor = [UIColor clearColor];
    title_.font = kSignupTitleUIFont;
    title_.frameHeight = title_.font.lineHeight;
    title_.textAlignment = NSTextAlignmentCenter;
    title_.textColor = kLoginSignupToggleColor;

    error_ = [TextLayer new];
    error_.anchorPoint = CGPointMake(0, 0);

    top_bg_ = [[UIImageView alloc] initWithImage:kSignupTextFieldTop];
    top_bg_.userInteractionEnabled = YES;

    name_divider_ = NewVerticalDivider();
    [top_bg_ addSubview:name_divider_];

    first_ = NewTextField(@"First");
    first_.autocapitalizationType = UITextAutocapitalizationTypeWords;
    first_.delegate = self;
    first_.returnKeyType = UIReturnKeyNext;
    if (login_details_.has_first()) {
      first_.text = NewNSString(login_details_.first());
    }

    last_ = NewTextField(@"Last");
    last_.autocapitalizationType = UITextAutocapitalizationTypeWords;
    last_.delegate = self;
    last_.returnKeyType = UIReturnKeyNext;
    if (login_details_.has_last()) {
      last_.text = NewNSString(login_details_.last());
    }

    middle_bg_ = [[UIImageView alloc] initWithImage:kSignupTextFieldMiddle];
    middle_bg_.userInteractionEnabled = YES;

    identity_ = [[IdentityTextField alloc] initWithState:state_ type:identity_type];
    identity_.delegate = self;
    StyleTextField(identity_.textField);
    identity_.textField.autocapitalizationType = UITextAutocapitalizationTypeNone;
    identity_.textField.backgroundColor = [UIColor clearColor];
    if (login_details_.has_identity_text()) {
      identity_.text = NewNSString(login_details_.identity_text());
    }

    bottom_bg_ = [[UIImageView alloc] initWithImage:kSignupTextFieldBottom];
    bottom_bg_.userInteractionEnabled = YES;

    password1_ = NewTextField(@"");
    password1_.autocapitalizationType = UITextAutocapitalizationTypeNone;
    password1_.delegate = self;
    password1_.secureTextEntry = YES;
    if (login_details_.has_password()) {
      password1_.text = NewNSString(login_details_.password());
    }

    password2_ = NewTextField(@"");
    password2_.autocapitalizationType = UITextAutocapitalizationTypeNone;
    password2_.delegate = self;
    password2_.secureTextEntry = YES;

    single_bg_ = [[UIImageView alloc] initWithImage:kSignupTextFieldSingle];
    single_bg_.userInteractionEnabled = YES;

    code_ = NewTextField(@"");
    code_.autocapitalizationType = UITextAutocapitalizationTypeNone;
    code_.delegate = self;
    code_.keyboardType = UIKeyboardTypeNumberPad;
    code_.returnKeyType = UIReturnKeyDone;
    code_.textAlignment = NSTextAlignmentCenter;

    dummy_ = NewTextField(@"");

    signup_toggle_ = NewSignupToggle(self, @selector(showSignup:));
    login_toggle_ = NewLoginToggle(self, @selector(showLogin:));

    cancel_ = UIStyle::NewSignupButtonGrey(
        @"", kSignupButtonUIFont, self, @selector(cancelButton));
    submit_ = UIStyle::NewSignupButtonGreen(
        @"", kSignupButtonUIFont, self, @selector(submit));
    submit_indicator_ =
        [[UIActivityIndicatorView alloc]
          initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleWhite];
    forgot_password_ = NewForgotPassword(self, @selector(showReset));
    resend_code_ = NewResendCode(self, @selector(resend));

    if (self.confirmMode) {
      // We've already sent the signup/login request to the server. Show the
      // confirmation screen.
      [self showConfirm];
    } else if (login_type_ == LINK) {
      [self showLink:self];
    } else if (login_type_ == CHANGE_PASSWORD) {
      [self showChangePassword:self];
    } else if (login_type_ == RESET_DEVICE_ID) {
      [self showResetDeviceId:self];
    } else {
      [self showSignup:NULL];
    }
  }
  return self;
}

- (BOOL)textField:(UITextField*)text_field
shouldChangeCharactersInRange:(NSRange)range
replacementString:(NSString*)str {
  if (text_field == code_) {
    NSMutableString* new_str =
        [[NSMutableString alloc] initWithString:
                   [code_.text substringToIndex:range.location]];
    [new_str appendString:str];
    const int num_digits_before_cursor = CountDigits(new_str);
    [new_str appendString:[code_.text substringFromIndex:range.location + range.length]];
    const int num_digits = CountDigits(new_str);
    if (num_digits <= self.codeLength) {
      code_.text = FormatCodeString(new_str, self.codeLength);
      // Assigning to .text moves the cursor to the end; put it back in the right place.
      UITextPosition* position =
          [code_ positionFromPosition:code_.beginningOfDocument
                               offset:SkipNDigits(code_.text, num_digits_before_cursor)];
      code_.selectedTextRange =
          [code_ textRangeFromPosition:position toPosition:position];
      [self codeTextChanged];
    }
    return NO;
  }
  return YES;
}

- (BOOL)textFieldShouldClear:(UITextField*)text_field {
  if (text_field == code_) {
    state_->async()->dispatch_after_main(0, ^{
        [self codeTextChanged];
      });
  }
  return YES;
}

- (BOOL)textFieldShouldReturn:(UITextField*)text_field {
  // Logic to support switching between the text fields using the "next"
  // key. I'm not aware of an easier/cleaner way to do this.
  if (text_field == first_) {
    [last_ becomeFirstResponder];
    return NO;
  } else if (text_field == last_) {
    [identity_.textField becomeFirstResponder];
    return NO;
  } else if (text_field == identity_.textField) {
    if (password1_.superview) {
      [password1_ becomeFirstResponder];
      return NO;
    }
  } else if (text_field == password1_) {
    if (password2_.superview) {
      [password2_ becomeFirstResponder];
      return NO;
    }
    if (first_.superview) {
      [first_ becomeFirstResponder];
      return NO;
    }
    if (identity_.textField.superview) {
      [identity_.textField becomeFirstResponder];
      return NO;
    }
  } else if (text_field == password2_) {
    [password1_ becomeFirstResponder];
    return NO;
  }
  if (submit_.enabled) {
    [self submit];
  }
  return NO;
}

- (BOOL)identityTextFieldShouldReturn:(IdentityTextField*)field {
  return [self textFieldShouldReturn:field.textField];
}

- (int)codeLength {
  if (login_details_.has_token_digits()) {
    return login_details_.token_digits();
  }
  return kConfirmationCodeLength;
}

- (bool)codeValid {
  if (!code_.text) {
    return false;
  }
  return CountDigits(code_.text) == self.codeLength;
}

- (void)codeTextChanged {
  if (self.codeValid) {
    code_.rightView = [[UIImageView alloc] initWithImage:kSignupCodeVerified];
    code_.rightView.contentMode = UIViewContentModeLeft;
    code_.rightView.frameWidth = code_.rightView.frameWidth + 6;
    code_.rightViewMode = UITextFieldViewModeAlways;
    code_.clearButtonMode = UITextFieldViewModeNever;
  } else {
    code_.rightView = NULL;
    code_.rightViewMode = UITextFieldViewModeNever;
    code_.clearButtonMode = UITextFieldViewModeWhileEditing;
  }
}

- (float)setSubviewFrames:(CGRect)f {
  float y = kSpacing;
  float w = f.size.width - kSpacing * 2;

  if (title_.superview) {
    title_.frameOrigin = CGPointMake(kSpacing, y);
    title_.frameWidth = w;
    y = ceilf(title_.frameBottom) + kSpacing;
  } else if (signup_toggle_.superview) {
    signup_toggle_.frameTop = 0;
    signup_toggle_.frameLeft = 0;
    signup_toggle_.frameWidth = f.size.width / 2;

    login_toggle_.frameTop = 0;
    login_toggle_.frameLeft = signup_toggle_.frameRight;
    login_toggle_.frameWidth = signup_toggle_.frameWidth;
    y = login_toggle_.frameBottom + kSpacing;

    if (login_type_ == SIGN_UP) {
      y += kTabSignupExtraSpacing;
    } else {
      y += kTabLoginExtraSpacing;
    }
  }

  if (error_.superlayer) {
    error_.frameOrigin = CGPointMake(kSpacing, y - kSpacing);
    error_.maxWidth = w;
    error_.frameWidth = w;
    y = ceilf(error_.frameBottom) + kSpacing;
  }

  if (top_bg_.superview) {
    top_bg_.frameTop = y;
    top_bg_.frameLeft = kSpacing;
    top_bg_.frameWidth = w;
    top_bg_.frameHeight = first_.frameHeight + kSpacing * 2;
    y = top_bg_.frameBottom;
  }

  if (first_.superview) {
    first_.frameTop = kTextVerticalInset;
    first_.frameLeft = kSpacing;
    first_.frameWidth = w / 2 - kSpacing - kTextRightMargin;

    name_divider_.frameTop = kSpacing;
    name_divider_.frameLeft = first_.frameRight + kTextRightMargin;
    name_divider_.frameHeight = first_.frameHeight;

    last_.frameTop = kTextVerticalInset;
    last_.frameLeft = name_divider_.frameLeft + kSpacing;
    last_.frameWidth = first_.frameWidth;
  }

  if (middle_bg_.superview) {
    middle_bg_.frameTop = y;
    middle_bg_.frameLeft = kSpacing;
    middle_bg_.frameWidth = w;
    middle_bg_.frameHeight = identity_.textField.frameHeight + kSpacing * 2;
    y = middle_bg_.frameBottom;
  }

  if (identity_.textField.superview) {
    identity_.toggle.frameTop = 0;
    identity_.toggle.frameRight = w - kTextRightMargin;

    identity_.textField.frameTop = kTextVerticalInset;
    identity_.textField.frameLeft = kSpacing;
    identity_.textField.frameWidth = w - kSpacing - kTextRightMargin;
  }

  if (bottom_bg_.superview) {
    bottom_bg_.frameTop = y;
    bottom_bg_.frameLeft = kSpacing;
    bottom_bg_.frameWidth = w;
    bottom_bg_.frameHeight = password1_.frameHeight + kSpacing * 2;
    y = bottom_bg_.frameBottom + kSpacing;
  }

  if (password1_.superview) {
    password1_.frameTop = kTextVerticalInset;
    password1_.frameLeft = kSpacing;
    password1_.frameWidth = w - kSpacing - kTextRightMargin;
  }

  if (password2_.superview) {
    password2_.frameTop = kTextVerticalInset;
    password2_.frameLeft = kSpacing;
    password2_.frameWidth = w - kSpacing - kTextRightMargin;
  }

  if (single_bg_.superview) {
    single_bg_.frameTop = y;
    single_bg_.frameLeft = kSpacing;
    single_bg_.frameWidth = w;
    single_bg_.frameHeight = code_.frameHeight + kSpacing * 2;
    y = single_bg_.frameBottom + kSpacing;
  }

  if (code_.superview) {
    code_.frameTop = kTextVerticalInset;
    code_.frameLeft = kSpacing;
    code_.frameWidth = w - kSpacing - kTextRightMargin;
  }

  cancel_.frameTop = y;
  cancel_.frameLeft = kSpacing;
  if (submit_.superview) {
    cancel_.frameWidth = (w - kSpacing) / 3;
  } else {
    cancel_.frameWidth = w;
  }

  if (submit_.superview) {
    submit_.frameTop = y;
    submit_.frameLeft =
        login_type_ == RESET_DEVICE_ID ?
        kSpacing : cancel_.frameRight + kSpacing;
    submit_.frameWidth =
        login_type_ == RESET_DEVICE_ID ?
        self.frameWidth - kSpacing * 2 : 2 * cancel_.frameWidth;
  }

  if (forgot_password_.superview) {
    forgot_password_.frameTop = cancel_.frameBottom;
    forgot_password_.frameLeft = kSpacing;
    forgot_password_.frameWidth = w;
    return forgot_password_.frameBottom;
  }

  if (resend_code_.superview) {
    resend_code_.frameTop = cancel_.frameBottom;
    resend_code_.frameLeft = kSpacing;
    resend_code_.frameWidth = w;
    return resend_code_.frameBottom;
  }

  return cancel_.frameBottom + kSpacing;
}

- (float)parentHeight {
  if (parent_) {
    return parent_.boundsHeight;
  }
  return [UIScreen mainScreen].bounds.size.height;
}

- (float)parentMinimizedHeight {
  if ([parent_ isKindOfClass:[UIScrollView class]]) {
    UIScrollView* parent_scroll = (UIScrollView*)parent_;
    return parent_scroll.contentSize.height;
  }
  return self.parentHeight;
}

- (void)setFrame:(CGRect)f {
  {
    const ScopedDisableCAActions disable_ca_actions;
    f.size.height = [self setSubviewFrames:f];
    f.origin.x = kSpacing;
    [self resetBackground:f.size];
  }

  if (self.minimized) {
    const float parent_height = self.parentMinimizedHeight;
    if (signup_toggle_.superview) {
      f.origin.y = parent_height -
          signup_toggle_.frameBottom - kSpacing / 2;
    } else {
      f.origin.y = parent_height;
    }
  } else {
    const float parent_height = self.parentHeight;
    if (self.keyboardVisible) {
      // Non-integer offsets cause rendering problems on non-retina displays. In
      // particular, the "clear button" of text fields gets clipped.
      f.origin.y = floorf((parent_height - f.size.height) / 2);
    } else {
      f.origin.y = parent_height - f.size.height - kSpacing;
    }
    if ([parent_ isKindOfClass:[UIScrollView class]]) {
      // Our parent is a scroll view, adjust for the current content offset.
      UIScrollView* parent_scroll = (UIScrollView*)parent_;
      f.origin.y += parent_scroll.contentOffset.y;
    }
  }
  [super setFrame:f];
}

- (bool)changingPassword {
  return login_type_ == CHANGE_PASSWORD &&
      ([self findFirstResponder] != NULL);
}

- (bool)minimized {
  return !self.keyboardVisible && !self.confirmMode;
}

- (bool)identityRequired {
  return login_type_ == SIGN_UP ||
      login_type_ == LOG_IN ||
      login_type_ == RESET;
}

- (bool)passwordRequired {
  return login_type_ == SIGN_UP ||
      login_type_ == LOG_IN ||
      login_type_ == CHANGE_PASSWORD ||
      login_type_ == RESET_DEVICE_ID;
}

- (void)enableSubmit {
  [submit_indicator_ removeFromSuperview];
  [submit_ setTitle:self.submitTitle
           forState:UIControlStateNormal];
  submit_.enabled = YES;
}

- (void)disableSubmit {
  [submit_ addSubview:submit_indicator_];
  [submit_indicator_ centerFrameWithinSuperview];
  [submit_indicator_ startAnimating];
  [submit_ setTitle:@""
           forState:UIControlStateNormal];
  submit_.enabled = NO;
}

- (NSString*)cancelTitle {
  if (self.confirmMode) {
    return @"Exit";
  }
  return kLoginSignupCancelTitle[login_type_];
}

- (NSString*)submitTitle {
  if (self.confirmMode) {
    return @"Continue";
  }
  return kLoginSignupSubmitTitle[login_type_];
}

- (void)resetBackground:(CGSize)size {
  int desired_type = -1;
  if (self.confirmMode) {
    desired_type = MODAL_SQUARE;
  } else if (self.keyboardVisible) {
    if (login_type_ == LINK ||
        login_type_ == MERGE ||
        login_type_ == RESET ||
        login_type_ == CHANGE_PASSWORD ||
        login_type_ == RESET_DEVICE_ID) {
      desired_type = MODAL_SQUARE;
    } else if (login_type_ == SIGN_UP) {
      desired_type = MODAL_TABS_SIGN_UP_SELECTED;
    } else {
      desired_type = MODAL_TABS_LOG_IN_SELECTED;
    }
  } else {
    if (login_type_ == LINK ||
        login_type_ == MERGE ||
        login_type_ == CHANGE_PASSWORD ||
        login_type_ == RESET_DEVICE_ID) {
      desired_type = MODAL_SQUARE;
    } else {
      desired_type = MODAL_TABS_DEFAULT;
    }
  }

  if (background_.tag != desired_type) {
    [background_ removeFromSuperview];
    UIImage* image = NULL;
    switch (desired_type) {
      case MODAL_SQUARE:
        image = kSquareModal;
        break;
      case MODAL_TABS_DEFAULT:
        image = kTabsModalDefault;
        break;
      case MODAL_TABS_LOG_IN_SELECTED:
        image = kTabsModalLoginSelected;
        break;
      case MODAL_TABS_SIGN_UP_SELECTED:
        image = kTabsModalSignupSelected;
        break;
    }
    background_ = [[UIImageView alloc] initWithImage:image];
    background_.frameLeft = -kSpacing;
    background_.frameTop = -kModalTopInset;
    background_.tag = desired_type;
  }

  background_.frameWidth = size.width + kSpacing * 2;
  background_.frameHeight = size.height + kModalTopInset + kModalBottomInset;

  if (!background_.superview) {
    [self insertSubview:background_ atIndex:0];
  }
}

- (void)resetButtons {
  [cancel_ setTitle:self.cancelTitle
           forState:UIControlStateNormal];
  [submit_ setTitle:self.submitTitle
           forState:UIControlStateNormal];
}

- (void)resetPlaceholders:(bool)required {
  first_.placeholder =
      required && !first_.text.length ? @"Required!" : @"First";
  last_.placeholder =
      required && !last_.text.length ? @"Required!" : @"Last";
  if (reset_password_) {
    password2_.placeholder =
        required && !password2_.text.length ?
        @"New Password Required!" : @"New Password";
    password1_.placeholder =
        required && !password1_.text.length ?
        @"Re-enter Password Required!" : @"Re-enter Password";
  } else {
    password2_.placeholder =
        required && !password2_.text.length ?
        @"Old Password Required!" : @"Old Password";
    if (login_type_ == CHANGE_PASSWORD) {
      password1_.placeholder =
          required && !password1_.text.length ?
          @"New Password Required!" : @"New Password";
    } else if (login_type_ == RESET_DEVICE_ID) {
      password1_.placeholder =
          required && !password1_.text.length ?
          @"Password Required!" : @"Password";
    } else {
      password1_.placeholder =
          required && !password1_.text.length ?
          @"Password Required!" : @"Password (min. 8 characters)";
    }
  }
  [identity_ resetPlaceholder];
  if (required && !identity_.textField.text.length) {
    identity_.textField.placeholder =
        Format("%s Required!", identity_.textField.placeholder);
  }
  code_.placeholder = Format(kCodePlaceholder, login_details_.token_digits());
}

- (void)resetReturnKey {
  switch (login_type_) {
    case SIGN_UP:
      identity_.textField.returnKeyType = UIReturnKeyNext;
      password1_.returnKeyType = UIReturnKeyNext;
      break;
    case LOG_IN:
      identity_.textField.returnKeyType = UIReturnKeyNext;
      password1_.returnKeyType = UIReturnKeyNext;
      break;
    case RESET:
      identity_.textField.returnKeyType = UIReturnKeyDone;
      break;
    case LINK:
      identity_.textField.returnKeyType = UIReturnKeyDone;
      break;
    case MERGE:
      identity_.textField.returnKeyType = UIReturnKeyDone;
      break;
    case CHANGE_PASSWORD:
      if (state_->no_password()) {
        password1_.returnKeyType = UIReturnKeyDone;
      } else {
        password1_.returnKeyType = UIReturnKeyNext;
        password2_.returnKeyType = UIReturnKeyNext;
      }
      break;
    case RESET_DEVICE_ID:
      identity_.textField.returnKeyType = UIReturnKeyDone;
      break;
  }
}

- (void)showSignup:(id)sender {
  login_type_ = SIGN_UP;

  [self resetButtons];
  [self resetPlaceholders:false];
  [self resetReturnKey];
  [self enableSubmit];

  [self addSubview:signup_toggle_];
  [self addSubview:login_toggle_];
  [self addSubview:cancel_];
  [self addSubview:submit_];

  [self addSubview:top_bg_];
  [top_bg_ addSubview:first_];
  [top_bg_ addSubview:last_];
  [top_bg_ addSubview:name_divider_];
  if (sender) {
    state_->analytics()->OnboardingSignupCard();
    [first_ becomeFirstResponder];
  }

  [self addSubview:middle_bg_];
  [middle_bg_ addSubview:identity_.textField];
  [middle_bg_ addSubview:identity_.toggle];

  [self addSubview:bottom_bg_];
  [bottom_bg_ addSubview:password1_];

  [title_ removeFromSuperview];
  [error_ removeFromSuperlayer];
  [single_bg_ removeFromSuperview];
  [code_ removeFromSuperview];
  [dummy_ removeFromSuperview];
  [resend_code_ removeFromSuperview];

  [forgot_password_ removeFromSuperview];

  [self setFrame:self.frame];
}

- (void)showLogin:(id)sender {
  login_type_ = LOG_IN;

  [self resetButtons];
  [self resetPlaceholders:false];
  [self resetReturnKey];
  [self enableSubmit];

  [self addSubview:signup_toggle_];
  [self addSubview:login_toggle_];
  [self addSubview:cancel_];
  [self addSubview:submit_];

  [self addSubview:top_bg_];
  [top_bg_ addSubview:identity_.textField];
  [top_bg_ addSubview:identity_.toggle];
  if (sender) {
    state_->analytics()->OnboardingLoginCard();
    [identity_.textField becomeFirstResponder];
  }

  [first_ removeFromSuperview];
  [last_ removeFromSuperview];
  [name_divider_ removeFromSuperview];

  [middle_bg_ removeFromSuperview];

  [self addSubview:bottom_bg_];
  [bottom_bg_ addSubview:password1_];

  [title_ removeFromSuperview];
  [error_ removeFromSuperlayer];
  [single_bg_ removeFromSuperview];
  [first_ removeFromSuperview];
  [last_ removeFromSuperview];
  [code_ removeFromSuperview];
  [dummy_ removeFromSuperview];
  [resend_code_ removeFromSuperview];

  [self addSubview:forgot_password_];

  [self setFrame:self.frame];
}

- (void)showReset {
  login_type_ = RESET;

  [self resetButtons];
  [self resetPlaceholders:false];
  [self resetReturnKey];

  [self addSubview:cancel_];
  [self addSubview:submit_];

  title_.text = @"Reset Your Password";
  [self addSubview:title_];

  [self addSubview:single_bg_];
  [single_bg_ addSubview:identity_.textField];
  [single_bg_ addSubview:identity_.toggle];
  state_->analytics()->OnboardingResetPasswordCard();
  [identity_.textField becomeFirstResponder];

  [error_ removeFromSuperlayer];
  [signup_toggle_ removeFromSuperview];
  [login_toggle_ removeFromSuperview];
  [top_bg_ removeFromSuperview];
  [middle_bg_ removeFromSuperview];
  [bottom_bg_ removeFromSuperview];
  [first_ removeFromSuperview];
  [last_ removeFromSuperview];
  [password1_ removeFromSuperview];
  [password2_ removeFromSuperview];
  [code_ removeFromSuperview];
  [dummy_ removeFromSuperview];
  [forgot_password_ removeFromSuperview];
  [resend_code_ removeFromSuperview];

  [self setFrame:self.frame];
}

- (void)showLink:(id)sender {
  login_type_ = LINK;

  [self resetButtons];
  [self resetPlaceholders:false];
  [self resetReturnKey];

  [self addSubview:cancel_];
  [self addSubview:submit_];

  if (login_details_.identity_type() == LoginEntryDetails::PHONE_ONLY) {
    title_.text = @"Add Mobile Number";
  } else {
    title_.text = @"Add an Identity";
  }
  [self addSubview:title_];

  [self addSubview:single_bg_];
  [single_bg_ addSubview:identity_.textField];
  [single_bg_ addSubview:identity_.toggle];
  if (sender) {
    state_->analytics()->OnboardingLinkCard();
    [identity_.textField becomeFirstResponder];
  }

  [error_ removeFromSuperlayer];
  [signup_toggle_ removeFromSuperview];
  [login_toggle_ removeFromSuperview];
  [top_bg_ removeFromSuperview];
  [middle_bg_ removeFromSuperview];
  [bottom_bg_ removeFromSuperview];
  [first_ removeFromSuperview];
  [last_ removeFromSuperview];
  [password1_ removeFromSuperview];
  [password2_ removeFromSuperview];
  [code_ removeFromSuperview];
  [dummy_ removeFromSuperview];
  [forgot_password_ removeFromSuperview];
  [resend_code_ removeFromSuperview];

  [self setFrame:self.frame];
}

- (void)showMerge:(id)sender {
  login_type_ = MERGE;

  [self resetButtons];
  [self resetPlaceholders:false];
  [self resetReturnKey];

  [self addSubview:cancel_];
  [self addSubview:submit_];

  NSMutableAttributedString* attr_str = NewAttrString(
      "\nAn account already exists with this identity.\n"
      "Do you want to merge\n",
      kSignupMessageFont, kSignupMessageColor);
  AppendAttrString(
      attr_str, Format("%s\n", login_details_.identity_text()),
      kSignupTitleFont, kSignupMergeColor);
  AppendAttrString(
      attr_str, "with your existing account?\n\n",
      kSignupMessageFont, kSignupMessageColor);
  error_.attrStr = AttrCenterAlignment(attr_str);
  [self.layer addSublayer:error_];

  // Copy the keyboard traits from the identity text field to the dummy text
  // field.
  dummy_.autocapitalizationType = identity_.textField.autocapitalizationType;
  dummy_.keyboardAppearance = identity_.textField.keyboardAppearance;
  dummy_.keyboardType = identity_.textField.keyboardType;
  dummy_.returnKeyType = identity_.textField.returnKeyType;
  // Position the dummy text field well offscreen.
  dummy_.frameTop = -10000;
  [self addSubview:dummy_];
  if (sender) {
    state_->analytics()->OnboardingMergeCard();
    [dummy_ becomeFirstResponder];
  }

  [title_ removeFromSuperview];
  [signup_toggle_ removeFromSuperview];
  [login_toggle_ removeFromSuperview];
  [single_bg_ removeFromSuperview];
  [top_bg_ removeFromSuperview];
  [middle_bg_ removeFromSuperview];
  [bottom_bg_ removeFromSuperview];
  [first_ removeFromSuperview];
  [last_ removeFromSuperview];
  [identity_.textField removeFromSuperview];
  [identity_.toggle removeFromSuperview];
  [password1_ removeFromSuperview];
  [password2_ removeFromSuperview];
  [code_ removeFromSuperview];
  [forgot_password_ removeFromSuperview];
  [resend_code_ removeFromSuperview];

  [self setFrame:self.frame];
}

- (void)showChangePassword:(id)sender {
  login_type_ = CHANGE_PASSWORD;

  [self resetButtons];
  [self resetPlaceholders:false];
  [self resetReturnKey];

  [self addSubview:cancel_];
  [self addSubview:submit_];

  if (state_->no_password()) {
    // The user doesn't have a password. A single password field is sufficient.
    title_.text = @"Set Password";
    [self addSubview:title_];

    [self addSubview:single_bg_];
    [single_bg_ addSubview:password1_];
    if (sender) {
      state_->analytics()->OnboardingSetPasswordCard();
      [password1_ becomeFirstResponder];
    }

    [top_bg_ removeFromSuperview];
    [bottom_bg_ removeFromSuperview];
    [password2_ removeFromSuperview];
  } else {
    // Note that if we're going through the reset password process we show 2
    // password fields which must be identical.
    title_.text = @"Change Password";
    [self addSubview:title_];

    [self addSubview:top_bg_];
    [top_bg_ addSubview:password2_];
    [self addSubview:bottom_bg_];
    [bottom_bg_ addSubview:password1_];
    if (sender) {
      state_->analytics()->OnboardingChangePasswordCard();
      [password2_ becomeFirstResponder];
    }

    [single_bg_ removeFromSuperview];
  }

  [error_ removeFromSuperlayer];
  [signup_toggle_ removeFromSuperview];
  [login_toggle_ removeFromSuperview];
  [middle_bg_ removeFromSuperview];
  [first_ removeFromSuperview];
  [last_ removeFromSuperview];
  [identity_.textField removeFromSuperview];
  [identity_.toggle removeFromSuperview];
  [code_ removeFromSuperview];
  [dummy_ removeFromSuperview];
  [forgot_password_ removeFromSuperview];
  [resend_code_ removeFromSuperview];

  [self setFrame:self.frame];
}

- (void)showConfirm {
  [self resetButtons];
  [self resetPlaceholders:false];
  [self resetReturnKey];

  [self addSubview:cancel_];
  [self addSubview:submit_];

  title_.text = @"Confirm Your Account";
  [self addSubview:title_];

  NSMutableAttributedString* attr_str = NewAttrString(
      "We've sent a code to ", kSignupMessageFont, kSignupMessageColor);
  AppendAttrString(
      attr_str, Format("%s", login_details_.identity_text()),
      kSignupBoldMessageFont, kSignupTitleColor);
  error_.attrStr = AttrCenterAlignment(attr_str);
  [self.layer addSublayer:error_];

  [self addSubview:resend_code_];
  [self addSubview:single_bg_];
  [single_bg_ addSubview:code_];
  code_.text = @"";
  [self codeTextChanged];
  state_->analytics()->OnboardingConfirmCard();
  switch (login_details_.identity_type()) {
    case LoginEntryDetails::EMAIL:
      state_->analytics()->OnboardingConfirmEmail();
      break;
    case LoginEntryDetails::PHONE:
    case LoginEntryDetails::PHONE_ONLY:
      state_->analytics()->OnboardingConfirmPhone();
      break;
  }
  [code_ becomeFirstResponder];

  [signup_toggle_ removeFromSuperview];
  [login_toggle_ removeFromSuperview];
  [top_bg_ removeFromSuperview];
  [middle_bg_ removeFromSuperview];
  [bottom_bg_ removeFromSuperview];
  [first_ removeFromSuperview];
  [last_ removeFromSuperview];
  [identity_.textField removeFromSuperview];
  [identity_.toggle removeFromSuperview];
  [password1_ removeFromSuperview];
  [password2_ removeFromSuperview];
  [dummy_ removeFromSuperview];
  [forgot_password_ removeFromSuperview];

  [self setFrame:self.frame];
}

- (void)showResetDeviceId:(id)sender {
  login_type_ = RESET_DEVICE_ID;

  [self resetButtons];
  [self resetPlaceholders:false];
  [self resetReturnKey];
  [self enableSubmit];

  [self addSubview:submit_];

  title_.text = @"Verify Account";
  [self addSubview:title_];

  [self addSubview:single_bg_];
  [single_bg_ addSubview:password1_];
  if (sender) {
    state_->analytics()->OnboardingResetDeviceIdCard();
    [password1_ becomeFirstResponder];
  }

  [identity_.textField removeFromSuperview];
  [identity_.toggle removeFromSuperview];
  [first_ removeFromSuperview];
  [last_ removeFromSuperview];
  [name_divider_ removeFromSuperview];
  [top_bg_ removeFromSuperview];
  [middle_bg_ removeFromSuperview];
  [bottom_bg_ removeFromSuperview];
  [error_ removeFromSuperlayer];
  [first_ removeFromSuperview];
  [last_ removeFromSuperview];
  [code_ removeFromSuperview];
  [dummy_ removeFromSuperview];
  [resend_code_ removeFromSuperview];

  [self addSubview:forgot_password_];

  [self setFrame:self.frame];
}

- (void)showError:(NSString*)title
             body:(NSString*)body {
  state_->analytics()->OnboardingError();
  [[[UIAlertView alloc]
     initWithTitle:title
           message:body
          delegate:NULL
     cancelButtonTitle:@"OK"
     otherButtonTitles:NULL] show];
}

- (void)showNetworkError:(int)error_id {
  state_->analytics()->OnboardingNetworkError();
  if (!state_->network_up() || error_id == ErrorResponse::NETWORK_UNAVAILABLE) {
    [self showError:@"Uh-oh!"
               body:@"The network is currently unavailable. Check your iPhone's "
                    @"network settings or move out of that cave you're hiding in."];
  } else {
    [self showError:@"Uh-oh!"
               body:@"The Viewfinder servers appear to be down. "
                    @"But don't worry, our best people are on it."];
  }
}

- (void)cancelButton {
  state_->analytics()->OnboardingCancel();
  [self cancel];
}

- (void)cancel {
  if (!self.confirmMode) {
    if (login_type_ == RESET) {
      // Refer to original login type in the login entry details field
      // to determine whether to return to ResetDeviceId or Login/Signup
      if (login_details_.type() == RESET_DEVICE_ID) {
        [self showResetDeviceId:NULL];
      } else {
        [self showLogin:self];
      }
      return;
    }
    [self endEditing:YES];
    if (login_type_ == LINK) {
      [self showLink:NULL];
    } else if (login_type_ == MERGE) {
      [self showMerge:NULL];
    } else if (login_type_ == CHANGE_PASSWORD) {
      [self showChangePassword:NULL];
      // Whether the password was changed or not, we run the settings_changed
      // callbacks in order to notify the dashboard that we're done resetting
      // the password.
      state_->settings_changed()->Run(true);
    } else if (login_type_ == RESET_DEVICE_ID) {
      [self showResetDeviceId:NULL];
    } else {
      [self showSignup:NULL];
    }
    return;
  }

  login_details_.clear_type();
  login_details_.clear_confirm_mode();
  SetLoginEntryDetails(state_, details_key_, login_details_);

  if (login_type_ == SIGN_UP) {
    [self showSignup:self];
  } else if (login_type_ == LOG_IN) {
    [self showLogin:self];
  } else if (login_type_ == LINK) {
    [self showLink:self];
  } else if (login_type_ == MERGE) {
    [self showMerge:self];
  } else if (login_type_ == CHANGE_PASSWORD) {
    [self showChangePassword:self];
  } else if (login_type_ == RESET_DEVICE_ID) {
    [self showResetDeviceId:self];
  } else {
    DCHECK_EQ(login_type_, RESET);
    [self showReset];
  }
}

- (void)submitVerify {
  const string access_code = ToString(FormatCodeString(code_.text, -1));
  if (access_code.size() != self.codeLength) {
    const int delta = self.codeLength - access_code.size();
    [self showError:@"That's Not A Valid Code"
               body:Format("We need a %d digit access code "
                           "and you gave us %d. %s",
                           self.codeLength, access_code.size(),
                           (delta >= 3) ? "Work with me." : "Almost there.")];
    return;
  }

  [self disableSubmit];
  if (login_type_ == LINK || login_type_ == MERGE) {
    state_->net_manager()->MergeAccounts(
        login_details_.identity_key(), access_code, details_key_,
        ^(int status, int error_id, const string& msg) {
          NSString* msg_str = NewNSString(msg);
          state_->async()->dispatch_main(^{
              [self enableSubmit];
              if (status != 200) {
                if (status == -1) {
                  [self showNetworkError:error_id];
                } else {
                  [self showError:@"Uh-oh!"
                             body:msg_str];
                }
              } else {
                login_details_.set_merging(true);
                login_details_.clear_confirm_mode();
                SetLoginEntryDetails(state_, details_key_, login_details_);
                // Notify the "My Info" card that the login details have changed.
                //
                // TODO(peter): This is sort of hacky. Make cleaner.
                state_->settings_changed()->Run(true);
                [self cancel];
              }
            });
        });
  } else {
    VerifyViewfinder(
        state_, login_details_.identity_key(), access_code, true,
        ^(int status, int error_id, const string& msg) {
          NSString* msg_str = NewNSString(msg);
          state_->async()->dispatch_main(^{
              [self enableSubmit];
              if (status != 200) {
                if (status == -1) {
                  [self showNetworkError:error_id];
                } else {
                  [self showError:@"Verification Failed"
                             body:msg_str];
                }
              } else {
                [self confirmedIdentity:msg_str];
              }
            });
        });
  }
}

- (void)submitChangePassword {
  [self resetPlaceholders:true];
  string old_password = ToString(password2_.text);
  const string new_password = ToString(password1_.text);
  if (!state_->no_password() && reset_password_ &&
      old_password != new_password) {
    [self showError:@"Uh-oh!"
               body:@"The passwords you entered do not match."];
    return;
  }
  if (!password1_.text.length ||
      (!state_->no_password() && !password2_.text.length)) {
    return;
  }

  if (reset_password_) {
    old_password.clear();
  }
  [self disableSubmit];
  state_->net_manager()->ChangePassword(
      old_password, new_password,
      ^(int status, int error_id, const string& msg) {
        NSString* msg_str = NewNSString(msg);
        state_->async()->dispatch_main(^{
            [self enableSubmit];
            if (status != 200) {
              if (status == -1) {
                [self showNetworkError:error_id];
              } else {
                [self showError:@"Uh-oh!"
                           body:msg_str];
              }
            } else {
              state_->analytics()->OnboardingChangePasswordComplete();
              state_->set_no_password(false);
              login_details_.Clear();
              SetLoginEntryDetails(state_, details_key_, login_details_);
              [self cancel];
            }
          });
      });
}

- (void)submit {
  if (self.confirmMode) {
    [self submitVerify];
    return;
  }
  if (login_type_ == CHANGE_PASSWORD) {
    [self submitChangePassword];
    return;
  }

  [self resetPlaceholders:true];
  if (login_type_ == SIGN_UP &&
      (!first_.text.length || !last_.text.length)) {
    return;
  }
  if (self.identityRequired && !identity_.textField.text.length) {
    return;
  }
  if (self.passwordRequired && !password1_.text.length) {
    return;
  }

  LoginEntryDetails::IdentityType identity_type;
  const string normalized_identity =
      [identity_ normalizedIdentityAndType:&identity_type showAlerts:true];
  if (normalized_identity.empty()) {
    return;
  }
  if (login_type_ == LINK || login_type_ == MERGE) {
    // Verify the identity isn't already linked to the user's account.
    ContactMetadata c;
    state_->contact_manager()->LookupUser(state_->user_id(), &c);
    for (int i = 0; i < c.identities_size(); ++i) {
      if (c.identities(i).identity() == normalized_identity) {
        [self showError:@"Hmmm…"
                   body:Format("%s is already linked to your account.",
                               identity_.textField.text)];
        return;
      }
    }
  }

  login_details_.set_first(ToString(first_.text));
  login_details_.set_last(ToString(last_.text));
  if (password1_.superview) {
    login_details_.set_password(ToString(password1_.text));
  } else {
    login_details_.clear_password();
  }
  login_details_.set_identity_type(identity_type);
  login_details_.set_identity_text(ToString(identity_.textField.text));
  login_details_.set_identity_key(normalized_identity);

  [self submitAuth];
}

- (void)resend {
  if (WallTime_Now() - last_resend_ < 10) {
    const int delta = WallTime_Now() - last_resend_;
    [self showError:@"It's coming…"
               body:Format("I sent a confirmation code %.0f second%s "
                           "ago. Give it a few more seconds to arrive.",
                           delta, Pluralize(delta))];
    return;
  }

  state_->analytics()->OnboardingResendCode();
  [self submitAuth];
}

- (void)submitAuth {
  const string& first = login_details_.first();
  const string& last = login_details_.last();
  const string full = state_->contact_manager()->ConstructFullName(first, last);
  const string& password = login_details_.password();
  const string endpoint = *kEndpoint[login_type_];
  const bool error_if_linked = (login_type_ != MERGE);

  if (!login_details_.confirm_mode()) {
    // Only disable the submit button if we are not already in confirm mode.
    [self disableSubmit];
  }

  AuthViewfinder(
      state_, endpoint, login_details_.identity_key(),
      password, first, last, full, error_if_linked,
      ^(int status, int error_id, const string& msg) {
        NSString* msg_str = NewNSString(msg);
        state_->async()->dispatch_main(^{
            [self enableSubmit];

            if (status != 200) {
              if (status == -1) {
                [self showNetworkError:error_id];
              } else {
                if (login_type_ == LINK && status == 403) {
                  [self showMerge:self];
                } else if (error_id == ErrorResponse::ALREADY_REGISTERED) {
                  [self showLogin:self];
                  [self showError:@"Uh-oh!"
                             body:Format(
                                 "A Viewfinder account for %s already exists. Try logging in.",
                                 login_details_.identity_text())];
                } else {
                  [self showError:@"Uh-oh!"
                             body:msg_str];
                }
              }
            } else {
              last_resend_ = WallTime_Now();
              if (login_details_.confirm_mode()) {
                // We were already in confirm mode. Give the user a heads-up
                // that the code was resent.
                [error_ addAnimation:NewShakeAnimation() forKey:NULL];
              }

              if (login_type_ != LOG_IN &&
                  login_type_ != RESET_DEVICE_ID) {
                login_details_.set_confirm_mode(true);
                login_details_.set_type(login_type_);
                if (error_id != 0) {
                  // HACK: When status==200, we pass the number of digits in the error_id field.
                  // See the TODO in AuthViewfinderRequest::HandleDone.
                  login_details_.set_token_digits(error_id);
                } else {
                  login_details_.set_token_digits(kConfirmationCodeLength);
                }
                SetLoginEntryDetails(state_, details_key_, login_details_);
                [self showConfirm];
              } else {
                // If the user is logging in with a password, there is no need
                // to show the confirmation dialog.
                [self confirmedIdentity:NULL];
              }
            }
          });
      });
}

- (void)confirmedIdentity:(NSString*)msg {
  state_->analytics()->OnboardingConfirmComplete();
  switch (login_details_.identity_type()) {
    case LoginEntryDetails::EMAIL:
      state_->analytics()->OnboardingConfirmEmailComplete();
      break;
    case LoginEntryDetails::PHONE:
    case LoginEntryDetails::PHONE_ONLY:
      state_->analytics()->OnboardingConfirmPhoneComplete();
      break;
  }
  // Clear only confirm_mode, password, and type so that any re-login keeps
  // the entered information but still prompts for a password.
  login_details_.clear_confirm_mode();
  login_details_.clear_password();
  SetLoginEntryDetails(state_, details_key_, login_details_);

  // If we just signed up, set account setup mode.
  if (login_type_ == SIGN_UP) {
    state_->set_account_setup(true);
  }

  if (state_->user_id()) {
    // After successfully confirming an identity, queue the user for retrieval
    // so that we can refresh the list of identities linked to the user.
    DBHandle updates = state_->NewDBTransaction();
    state_->contact_manager()->QueueUser(state_->user_id(), updates);
    updates->Commit();
  }

  if (login_type_ == RESET) {
    reset_password_ = true;
    password1_.text = @"";
    password2_.text = @"";
    [self showChangePassword:self];
  } else {
    [self cancel];
  }
}

- (bool)confirmMode {
  return login_details_.confirm_mode();
}

@end  // LoginSignupDashboardCard
