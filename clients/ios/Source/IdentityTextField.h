// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <UIKit/UITextField.h>
#import "LoginEntryDetails.pb.h"
#import "PhoneNumberFormatter.h"
#import "ScopedNotification.h"

class UIAppState;
@class IdentityTextField;

@protocol IdentityTextFieldDelegate <NSObject>
@optional
- (void)identityTextFieldChanged:(IdentityTextField*)field;
- (void)identityTextFieldDidBeginEditing:(IdentityTextField*)field;
- (void)identityTextFieldDidEndEditing:(IdentityTextField*)field;
- (BOOL)identityTextFieldShouldReturn:(IdentityTextField*)field;
@end  // IdentityTextFieldDelegate

// IdentityTextField combines a text field with a button to switch
// between email and phone number modes.  Callers are responsible for
// adding the textField and toggle properties to a superview and
// sizing/styling appropriately.
@interface IdentityTextField : NSObject<PhoneNumberFormatterDelegate,
                                        UITextFieldDelegate> {
  UIAppState* state_;
  LoginEntryDetails::IdentityType identity_type_;
  UITextField* text_field_;
  UIButton* identity_toggle_;
  PhoneNumberFormatter* phone_formatter_;
  __weak id<IdentityTextFieldDelegate> delegate_;
  ScopedNotification change_notification_;
}

@property (nonatomic, weak) id<IdentityTextFieldDelegate> delegate;
@property (nonatomic) NSString* text;
@property (nonatomic, readonly) UITextField* textField;
@property (nonatomic, readonly) UIButton* toggle;
@property (nonatomic, readonly) LoginEntryDetails::IdentityType type;

- (id)initWithState:(UIAppState*)state type:(LoginEntryDetails::IdentityType)type;
- (void)resetPlaceholder;
- (string)normalizedIdentityAndType:(LoginEntryDetails::IdentityType*)type showAlerts:(bool)show_alerts;

@end  // IdentityTextField
