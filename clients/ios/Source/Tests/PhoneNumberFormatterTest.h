// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#ifdef TESTING

#import <UIKit/UIViewController.h>
#import "PhoneNumberFormatter.h"
#import "SearchTextField.h"

@interface PhoneNumberFormatterTestController : UIViewController<PhoneNumberFormatterDelegate,
                                                                 SearchTextFieldDelegate> {
  UITextField* field1_;
  PhoneNumberFormatter* formatter1_;
  UILabel* label1_;

  SearchTextField* search_view_;
  PhoneNumberFormatter* search_formatter_;
  UILabel* search_label_;
}

@end  // PhoneNumberFormatterTestController

#endif  //TESTING
