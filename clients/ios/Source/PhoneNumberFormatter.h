// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <UIKit/UITextField.h>
#import "ScopedPtr.h"
#import "Utils.h"

namespace i18n {
namespace phonenumbers {

class PhoneNumberUtil;
class AsYouTypeFormatter;

}  // phonenumbers
}  // i18n

@class PhoneNumberFormatter;

@protocol PhoneNumberFormatterDelegate

- (void)phoneNumberFormatterDidChange:(PhoneNumberFormatter*)field;

@end  // PhoneNumberFormatterDelegate

@interface PhoneNumberFormatter : NSObject<UITextFieldDelegate> {
 @private
  __weak id<PhoneNumberFormatterDelegate> delegate_;
  UITextField* field_;
  i18n::phonenumbers::PhoneNumberUtil* phone_util_;
  string country_code_;
  ScopedPtr<i18n::phonenumbers::AsYouTypeFormatter> formatter_;
}

@property (nonatomic, weak) id<PhoneNumberFormatterDelegate> delegate;
@property (nonatomic) string countryCode;
@property (nonatomic, readonly) bool isValid;
@property (nonatomic, readonly) string normalizedNumber;
@property (nonatomic, readonly) UITextField* field;

// Creates a PhoneNumberFormatter for the given field. Does not change the
// text_field's delegate. The text field's actual delegate is responsible for
// forwarding textField:shouldChangeCharactersInRange:replacementString:
// messages to the formatter.
- (id)initForField:(UITextField*)field;
- (void)reformatField;

@end  // PhoneNumberFormatter
