// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell
//
// The AddressBookManager interacts with the iOS Address Book to synchronize it with the ContactManager.

#import <AddressBook/AddressBook.h>
#import "ScopedRef.h"

class UIAppState;

class AddressBookManager {
 public:
  AddressBookManager(UIAppState* state);
  ~AddressBookManager();

  // Requests authorization from the user.  Invokes callback once the authorization status has been determined.
  void Authorize(void (^callback)());

  void ImportContacts(void (^callback)(bool success));

  // Returns true if we have attempted to authorize, or if we are on an older version of iOS where
  // authorization is not required.
  bool authorization_determined() const { return authorization_determined_; }
  // Returns true if authorization was granted.  Meaningful only if authorization_determined is true.
  bool authorized() const { return authorized_; }

 private:
  // Populates *ab_ref with an authorized ABAddressBook, or sets it to NULL if authorization is not granted.
  void CreateAuthorizedAddressBook(void (^callback)(ABAddressBookRef address_book));

  UIAppState* state_;

  bool authorization_determined_;
  bool authorized_;
};
