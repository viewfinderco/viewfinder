// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#ifdef TESTING

#import <UIKit/UILabel.h>
#import "Logging.h"
#import "PhoneNumberFormatter.h"
#import "PhoneNumberFormatterTest.h"
#import "UIView+geometry.h"

namespace {

const int kPadding = 8;
const int kHeight = 32;
const int kWidth = 200;

}  // namespace

@implementation PhoneNumberFormatterTestController

- (id)init {
  if (self = [super init]) {
  }
  return self;
}

- (void)loadView {
  self.view = [UIView new];
  self.view.backgroundColor = [UIColor whiteColor];

  field1_ = [UITextField new];
  field1_.borderStyle = UITextBorderStyleBezel;
  field1_.frameTop = kPadding;
  field1_.frameHeight = kHeight;
  field1_.frameLeft = kPadding;
  field1_.frameWidth = kWidth;
  field1_.keyboardType = UIKeyboardTypePhonePad;
  formatter1_ = [[PhoneNumberFormatter alloc] initForField:field1_];
  formatter1_.countryCode = "US";
  formatter1_.delegate = self;
  field1_.delegate = formatter1_;
  [self.view addSubview:field1_];

  label1_ = [UILabel new];
  label1_.frameLeft = kPadding;
  label1_.frameTop = field1_.frameBottom + kPadding;
  label1_.frameHeight = kHeight;
  label1_.frameWidth = kWidth;
  label1_.text = NewNSString(formatter1_.countryCode);
  [self.view addSubview:label1_];

  search_view_ = [[SearchTextField alloc] initWithFrame:CGRectMake(kPadding, label1_.frameBottom + kPadding * 3,
                                                                     kWidth, [SearchTextField defaultHeight])];
  search_view_.delegate = self;
  search_view_.searchField.keyboardType = UIKeyboardTypePhonePad;
  search_formatter_ = [[PhoneNumberFormatter alloc]
                        initForField:search_view_.searchField];
  search_formatter_.delegate = self;
  search_formatter_.countryCode = "FR";
  [self.view addSubview:search_view_];

  search_label_ = [UILabel new];
  search_label_.frameLeft = kPadding;
  search_label_.frameTop = search_view_.frameBottom + kPadding;
  search_label_.frameHeight = kHeight;
  search_label_.frameWidth = kWidth;
  search_label_.text = NewNSString(search_formatter_.countryCode);
  [self.view addSubview:search_label_];
}

- (void)phoneNumberFormatterDidChange:(PhoneNumberFormatter*)formatter {
  UILabel* label;
  if (formatter == formatter1_) {
    label = label1_;
  } else {
    label = search_label_;
  }
  label.text = NewNSString(formatter.normalizedNumber);
  if (formatter.isValid) {
    label.textColor = [UIColor greenColor];
  } else {
    label.textColor = [UIColor redColor];
  }
}

- (BOOL)searchField:(SearchTextField*)view
shouldChangeCharactersInRange:(NSRange)range
    replacementString:(NSString*)string {
  return [search_formatter_ textField:view.searchField
        shouldChangeCharactersInRange:range
                    replacementString:string];
}

- (void)searchFieldDidChange:(SearchTextField*)field {
  LOG("search contacts for: %s", field.text);
}

@end  // PhoneNumberFormatterTestController

#endif  //TESTING
