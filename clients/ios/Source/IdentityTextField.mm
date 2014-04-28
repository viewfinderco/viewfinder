// Copyright 2013 Viewfinder. All rights Reserved.
// Author: Ben Darnell

#import <UIKit/UIButton.h>
#import "Appearance.h"
#import "AsyncState.h"
#import "ContactManager.h"
#import "IdentityManager.h"
#import "IdentityTextField.h"
#import "UIAppState.h"
#import "UIView+geometry.h"

namespace {

NSString* const kIdentityPlaceholder[] = { @"Mobile or Email", @"Mobile or Email", @"Mobile Number" };

LazyStaticImage kSignupKeypadToggleEmail(
    @"signup-keypad-toggle-icon-email.png");
LazyStaticImage kSignupKeypadToggleEmailActive(
    @"signup-keypad-toggle-icon-email-active.png");
LazyStaticImage kSignupKeypadToggleMobile(
    @"signup-keypad-toggle-icon-mobile.png");
LazyStaticImage kSignupKeypadToggleMobileActive(
    @"signup-keypad-toggle-icon-mobile-active.png");

const float kSpacing = 8;

UIButton* NewIdentityToggle(id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.contentEdgeInsets = UIEdgeInsetsMake(10, 8, 10, 6);
  [b setImage:kSignupKeypadToggleEmail
     forState:UIControlStateNormal];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  [b sizeToFit];
  return b;
}

}  // namespace

@implementation IdentityTextField

@synthesize delegate = delegate_;
@synthesize textField = text_field_;
@synthesize toggle = identity_toggle_;
@synthesize type = identity_type_;

- (id)initWithState:(UIAppState*)state type:(LoginEntryDetails::IdentityType)type {
  if (self = [super init]) {
    state_ = state;
    identity_type_ = type;

    text_field_ = [UITextField new];
    text_field_.autocapitalizationType = UITextAutocapitalizationTypeNone;
    // iOS will detect common names and "helpfully" correct them to
    // capitalized form even when autocapitalization is off (and occasionally
    // makes other corrections that are undesirable for email addresses).
    text_field_.autocorrectionType = UITextAutocorrectionTypeNo;
    text_field_.clearButtonMode = UITextFieldViewModeWhileEditing;
    // Dummy inputAccessoryView ensures that we get keyboardWillShow notifications even when
    // a hardware keyboard is used instead of the on-screen one.
    text_field_.inputAccessoryView = [UIView new];
    text_field_.placeholder = kIdentityPlaceholder[identity_type_];
    text_field_.delegate = self;

    phone_formatter_ = [[PhoneNumberFormatter alloc] initForField:text_field_];
    phone_formatter_.delegate = self;

    identity_toggle_ = NewIdentityToggle(self, @selector(toggleIdentity));
    identity_toggle_.hidden = YES;
    [self resetIdentityToggle];

    __weak IdentityTextField* weak_self = self;
    change_notification_.Init(
        UITextFieldTextDidChangeNotification,
        text_field_,
        ^(NSNotification* n) {
          [weak_self identityTextChanged];
        });
    [self identityTextChanged];
  }
  return self;
}

- (void)phoneNumberFormatterDidChange:(PhoneNumberFormatter*)field {
  [self identityTextChanged];
}

- (BOOL)textField:(UITextField*)text_field
shouldChangeCharactersInRange:(NSRange)range
replacementString:(NSString*)str {
  if (identity_type_ == LoginEntryDetails::PHONE ||
      identity_type_ == LoginEntryDetails::PHONE_ONLY) {
    return [phone_formatter_ textField:text_field
                             shouldChangeCharactersInRange:range
                     replacementString:str];
  }
  return YES;
}

- (BOOL)textFieldShouldClear:(UITextField*)text_field {
  if (identity_type_ == LoginEntryDetails::PHONE) {
    return [phone_formatter_ textFieldShouldClear:text_field];
  }
  return YES;
}

- (void)textFieldDidBeginEditing:(UITextField*)text_field {
  [self identityTextChanged];
  if ([self.delegate respondsToSelector:@selector(identityTextFieldDidBeginEditing:)]) {
    [self.delegate identityTextFieldDidBeginEditing:self];
  }
}

- (void)textFieldDidEndEditing:(UITextField*)text_field {
  identity_toggle_.hidden = YES;
  if ([self.delegate respondsToSelector:@selector(identityTextFieldDidEndEditing:)]) {
    [self.delegate identityTextFieldDidEndEditing:self];
  }
}

- (BOOL)textFieldShouldReturn:(UITextField*)text_field {
  if ([self.delegate respondsToSelector:@selector(identityTextFieldShouldReturn:)]) {
    return [self.delegate identityTextFieldShouldReturn:self];
  }
  return YES;
}

- (void)identityTextChanged {
  identity_toggle_.hidden = identity_type_ == LoginEntryDetails::PHONE_ONLY ||
                            ![text_field_ isFirstResponder] ||
                            (text_field_.text.length > 0);
  text_field_.placeholder = kIdentityPlaceholder[identity_type_];
  if ([self.delegate respondsToSelector:@selector(identityTextFieldChanged:)]) {
    [self.delegate identityTextFieldChanged:self];
  }
}

- (void)resetIdentityToggle {
  if (identity_type_ == LoginEntryDetails::EMAIL) {
    text_field_.keyboardType = UIKeyboardTypeEmailAddress;
    [identity_toggle_ setImage:kSignupKeypadToggleMobile
                      forState:UIControlStateNormal];
    [identity_toggle_ setImage:kSignupKeypadToggleMobileActive
                      forState:UIControlStateHighlighted];
  } else {
    text_field_.keyboardType = UIKeyboardTypePhonePad;
    [identity_toggle_ setImage:kSignupKeypadToggleEmail
                      forState:UIControlStateNormal];
    [identity_toggle_ setImage:kSignupKeypadToggleEmailActive
                      forState:UIControlStateHighlighted];
    [phone_formatter_ reformatField];
  }
  text_field_.placeholder = kIdentityPlaceholder[identity_type_];
  [text_field_ reloadInputViews];
}

- (void)resetPlaceholder {
  text_field_.placeholder = kIdentityPlaceholder[identity_type_];
}

- (string)normalizedIdentityAndType:(LoginEntryDetails::IdentityType*)type showAlerts:(bool)show_alerts {
  if (phone_formatter_.isValid) {
    // We allow valid phone numbers regardless of whether they were typed in
    // the email or phone fields.
    [phone_formatter_ reformatField];
    *type = LoginEntryDetails::PHONE;
    return IdentityManager::IdentityForPhone(phone_formatter_.normalizedNumber);
  }
  if (identity_type_ == LoginEntryDetails::PHONE ||
      identity_type_ == LoginEntryDetails::PHONE_ONLY) {
    NSLocale* english = [[NSLocale alloc] initWithLocaleIdentifier:@"en_US"];
    NSString* country_name =
        [english displayNameForKey:NSLocaleCountryCode
                             value:NewNSString(phone_formatter_.countryCode)];
    if (show_alerts) {
      [[[UIAlertView alloc]
         initWithTitle:@"That's Not A Valid Number"
               message:Format("For non-%s numbers, start with a \"+\". "
                              "Try entering it again",
                              country_name)
              delegate:NULL
         cancelButtonTitle:@"Let me fix that…"
         otherButtonTitles:NULL] show];
    }
    return string();
  }

  DCHECK_EQ(identity_type_, LoginEntryDetails::EMAIL);
  string error;
  if (IsValidEmailAddress(ToSlice(text_field_.text), &error)) {
    *type = LoginEntryDetails::EMAIL;
    return IdentityManager::IdentityForEmail(ToString(text_field_.text));
  }

  if (show_alerts) {
    state_->ShowInvalidEmailAlert(ToString(text_field_.text), error);
  }
  return string();
}

- (void)toggleIdentity {
  if (identity_type_ == LoginEntryDetails::PHONE) {
    identity_type_ = LoginEntryDetails::EMAIL;
  } else {
    identity_type_ = LoginEntryDetails::PHONE;
  }
  [self resetIdentityToggle];
}

- (NSString*)text {
  return text_field_.text;
}

- (void)setText:(NSString*)text {
  text_field_.text = text;
  [self identityTextChanged];
}

@end  // IdentityTextField
