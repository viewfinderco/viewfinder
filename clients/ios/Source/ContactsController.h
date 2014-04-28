// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIKit.h>

class UIAppState;
@class ListContactsController;

enum ContactsControllerPage {
  CONTACTS_LIST,
  MY_INFO,
  ADD_CONTACTS,
};

@interface ContactsController
    : UINavigationController<UINavigationControllerDelegate> {
 @private
  UIAppState* state_;
  ContactsControllerPage requested_page_;
  int contact_changed_id_;
  ListContactsController* list_contacts_;
}

@property (nonatomic) ContactsControllerPage requestedPage;

- (id)initWithState:(UIAppState*)state;

@end  // ContactsController

// local variables:
// mode: objc
// end:
