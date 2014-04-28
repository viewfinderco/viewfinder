// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <UIKit/UIScrollView.h>
#import <UIKit/UITableView.h>
#import <UIKit/UIViewController.h>
#import "ContactManager.h"
#import "ScopedNotification.h"
#import "SearchTextField.h"
#import "ValueUtils.h"
#import "WallTime.h"

@class AddContactsController;
@class UISegmentedControl;

class UIAppState;

typedef vector<pair<int, NSString*> > ListContactsSectionVec;

@interface ListContactsController
    : UIViewController<SearchTextFieldDelegate,
                       UIScrollViewDelegate,
                       UITableViewDataSource,
                       UITableViewDelegate> {
 @private
  UIAppState* state_;
  AddContactsController* add_contacts_;
  UITableView* table_view_;
  SearchTextField* search_view_;
  UIView* search_bottom_separator_;
  UIView* search_top_separator_;
  UIView* keyboard_;
  ScopedNotification keyboard_did_show_;
  ScopedNotification keyboard_did_hide_;
  ScopedNotification keyboard_will_show_;
  ScopedNotification keyboard_will_hide_;
  CGRect keyboard_frame_;
  ContactManager::ContactVec contacts_;
  ScopedPtr<RE2> search_filter_;
  // The start index (into the contacts_ vector) and title of each section.
  ListContactsSectionVec sections_;
  Array section_index_titles_;
}

@property (nonatomic, readonly) AddContactsController* addContacts;

- (id)initWithState:(UIAppState*)state;
- (void)clearContacts;

@end  // ListContactsController

// local variables:
// mode: objc
// end:
