// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <phonenumbers/asyoutypeformatter.h>
#import <phonenumbers/phonenumberutil.h>
#import "LocaleUtils.h"
#import "PhoneNumberFormatter.h"
#import "PhoneUtils.h"

namespace {

int CountPhoneDigits(const Slice& str) {
  int count = 0;
  for (int i = 0; i < str.size(); i++) {
    if (IsPhoneDigit(str[i])) {
      count++;
    }
  }
  return count;
}

// Returns a position just after the nth digit.
int SkipNDigits(NSString* str, int n) {
  int num_digits = 0;
  for (int i = 0; i < str.length; i++) {
    if (IsPhoneDigit([str characterAtIndex:i])) {
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

}  // namespace

@implementation PhoneNumberFormatter

@synthesize delegate = delegate_;
@synthesize countryCode = country_code_;
@synthesize field = field_;

- (id)initForField:(UITextField*)field {
  if (self = [super init]) {
    phone_util_ = i18n::phonenumbers::PhoneNumberUtil::GetInstance();
    self.countryCode = GetPhoneNumberCountryCode();
    field_ = field;
  }
  return self;
}

- (void)setCountryCode:(string)s {
  country_code_ = s;
  formatter_.reset(phone_util_->GetAsYouTypeFormatter(country_code_));
}

- (void)reformatField {
  // TODO(peter): This method is similar to shouldChangeCharactersInRange. Find
  // a way to unify.
  const int offset =
      [field_ offsetFromPosition:field_.beginningOfDocument
                      toPosition:field_.selectedTextRange.start];
  formatter_->Clear();

  string result;
  [self appendAndFormatString:[field_.text substringToIndex:offset] to:&result];
  const int num_digits = CountPhoneDigits(result);
  [self appendAndFormatString:[field_.text substringFromIndex:offset] to:&result];

  NSString* new_text = NewNSString(result);
  if (![field_.text isEqualToString:new_text]) {
    field_.text = NewNSString(result);
    // Assigning to .text moves the cursor to the end; put it back in the right place.
    UITextPosition* position = [field_ positionFromPosition:field_.beginningOfDocument
                                                     offset:SkipNDigits(field_.text, num_digits)];
    field_.selectedTextRange = [field_ textRangeFromPosition:position toPosition:position];
    [delegate_ phoneNumberFormatterDidChange:self];
  }
}

- (BOOL)textFieldShouldClear:(UITextField*)text_field {
  dispatch_after_main(0, ^{
      [delegate_ phoneNumberFormatterDidChange:self];
    });
  return YES;
}

- (BOOL)textField:(UITextField*)text_field
shouldChangeCharactersInRange:(NSRange)range
replacementString:(NSString*)new_str {
  // There's no way to tell the formatter that we've deleted something, so we have to start over
  // whenever we do anything but append at the end.  For simplicity's sake, we start over every time,
  // and process the field in three chunks: the range before the edit, the replacement string, and the range
  // after the edit.
  formatter_->Clear();

  string result;
  [self appendAndFormatString:[field_.text substringToIndex:range.location] to:&result];
  [self appendAndFormatString:new_str to:&result];
  // Remember the current state to set the cursor at the location of the edit.
  // The formatter's GetRememberedPosition method is unfortunately not very helpful here since it sometimes
  // points to a formatting character and sometimes to a digit, which leads to extra complexity around
  // deletion as deleted formatting characters may be immediately re-added.  Ignore that method and
  // position the cursor ourselves so it is always just after a digit.
  const int num_digits = CountPhoneDigits(result);
  [self appendAndFormatString:[field_.text substringFromIndex:range.location + range.length] to:&result];

  field_.text = NewNSString(result);
  // Assigning to .text moves the cursor to the end; put it back in the right place.
  UITextPosition* position = [field_ positionFromPosition:field_.beginningOfDocument
                                                   offset:SkipNDigits(field_.text, num_digits)];
  field_.selectedTextRange = [field_ textRangeFromPosition:position toPosition:position];
  [delegate_ phoneNumberFormatterDidChange:self];
  return NO;
}

// Appends the digits in the input string to the formatter.  If any digits were added, returns the
// new formatted string in *result.  If no digits were added, *result is left unchanged.
// The "append" in the name refers to the formatter's internal state; if *result is changed it is
// entirely overwritten, not just appended to.
- (void)appendAndFormatString:(NSString*)input to:(string*)result {
  // UITextField may give us multiple characters at once, so break the incoming string into characters.
  for (int i = 0; i < input.length; i++) {
    // Are there any digits outside the BMP?  If so we'll need to decode utf16 here.
    const int chr = [input characterAtIndex:i];
    if (IsPhoneDigit(chr)) {
      formatter_->InputDigit(chr, result);
    }
  }
}

- (bool)isValid {
  return IsValidPhoneNumber(ToString(field_.text), country_code_);
}

- (string)normalizedNumber {
  return NormalizedPhoneNumber(ToString(field_.text), country_code_);
}

@end  // PhoneNumberFormatter
