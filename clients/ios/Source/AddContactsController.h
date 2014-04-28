// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIViewController.h>
#import <UIKit/UIScrollView.h>
#import "IdentityTextField.h"
#import "ScopedPtr.h"
#import "WallTime.h"

@class TextLayer;
@class UIActivityIndicatorView;

class AddressBookSection;
class UIAppState;
class ContactMetadata;
class FacebookSection;
class GoogleSection;

@interface AddContactsController : UIViewController<IdentityTextFieldDelegate,
                                                      UIScrollViewDelegate> {
 @private
  UIAppState* state_;
  UIScrollView* scroll_view_;
  ScopedPtr<AddressBookSection> address_book_;
  ScopedPtr<GoogleSection> google_;
  ScopedPtr<FacebookSection> facebook_;
  UIView* add_footer_;
  UIView* import_header_;
  UIView* login_entry_;
  UINavigationItem* navigation_item_;
}

// Last import time across all contacts sources.
@property (nonatomic, readonly) WallTime lastImportTime;

- (id)initWithState:(UIAppState*)state;
- (void)updateNavigation;

@end  // AddContactsController

// local variables:
// mode: objc
// end:
