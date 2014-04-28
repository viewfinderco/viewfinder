// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.
//
// TODO
//
// - Allow linking multiple gmail accounts.
//
// - Provide a count of the number contacts fetched from a linked account.
//
// - Add shadow underneath contacts list navigation bar.

#import "AddContactsController.h"
#import "Analytics.h"
#import "AsyncState.h"
#import "ContactInfoController.h"
#import "ContactManager.h"
#import "ContactMetadata.pb.h"
#import "ContactsController.h"
#import "ListContactsController.h"
#import "UIAppState.h"
#import "UIStyle.h"

@implementation ContactsController

@synthesize requestedPage = requested_page_;

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;
    contact_changed_id_ = 0;
    list_contacts_ = [[ListContactsController alloc] initWithState:state_];
  }
  return self;
}

- (bool)statusBarLightContent {
  return true;
}

- (void)viewDidUnload {
  [self setViewControllers:NULL animated:NO];
  [super viewDidUnload];
}

- (void)viewWillAppear:(BOOL)animated {
  [super viewWillAppear:animated];
  state_->analytics()->ContactsPage();
}

- (void)willMoveToParentViewController:(UIViewController*)parent {
  [super willMoveToParentViewController:parent];
  if (!parent) {
    // We're being removed from our parent. Do nothing.
    return;
  }

  // We're being added to our parent. Initialize the list of view
  // controllers. This method is only called when the contacts view controller
  // is being added or removed as a child to the root view controller.
  if (self.requestedPage == MY_INFO) {
    ContactMetadata m;
    state_->contact_manager()->LookupUser(state_->user_id(), &m);
    self.viewControllers = Array(
        [[ContactInfoController alloc]
          initWithState:state_
                contact:m]);
  } else if (self.requestedPage == ADD_CONTACTS) {
    // If the caller explicitly requested the add contacts page, go there directly without putting
    // the contact list on the stack.
    self.viewControllers = Array(list_contacts_.addContacts);
  } else if (self.canShowContactsList) {
    self.viewControllers = Array(list_contacts_);
  } else {
    // If the user doesn't have contacts, go to the add contacts page, but when/if that changes
    // insert the contact list on the stack underneath it.
    self.viewControllers = Array(list_contacts_.addContacts);

    // We don't currently have any contacts. Watch for a contact to be added
    // and update the view controllers when that happens.
    if (!contact_changed_id_) {
      contact_changed_id_ = state_->contact_manager()->contact_changed()->Add(^{
          state_->contact_manager()->contact_changed()->Remove(contact_changed_id_);
          contact_changed_id_ = 0;

          state_->async()->dispatch_main(^{
              [self setViewControllers:Array(list_contacts_, list_contacts_.addContacts)
                              animated:YES];
              [list_contacts_.addContacts updateNavigation];
            });
        });
    }
  }
}

- (void)didMoveToParentViewController:(UIViewController*)parent {
  [super didMoveToParentViewController:parent];
  if (!parent) {
    // Only clear contacts if we're being removed from our parent.
    [list_contacts_ clearContacts];
  }
}

- (bool)canShowContactsList {
  if (!state_->is_registered()) {
    // Never show the contacts list if the user hasn't registered.
    return false;
  }
  const int count = state_->contact_manager()->count() + state_->contact_manager()->viewfinder_count();
  if (count <= 0) {
    return false;
  }
  if (count > 1) {
    return true;
  }
  ContactManager::ContactVec contacts;
  state_->contact_manager()->Search(
      "", &contacts, NULL,
      ContactManager::ALLOW_EMPTY_SEARCH | ContactManager::SORT_BY_NAME | ContactManager::PREFIX_MATCH);
  if (contacts.empty() ||
      (contacts.size() == 1 && contacts[0].user_id() == state_->user_id())) {
    // The only contact entry we have is for ourself.
    return false;
  }
  // We have a contact entry that is not for ourself.
  return true;
}

@end  // ContactsController
