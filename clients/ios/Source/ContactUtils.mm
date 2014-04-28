// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.

#import "CppDelegate.h"
#import "ContactManager.h"
#import "ContactMetadata.pb.h"
#import "ContactUtils.h"
#import "IdentityManager.h"

void ChooseIdentityForContact(
    const ContactMetadata& base_contact, UIView* parent_view,
    void (^callback)(const ContactMetadata*)) {
  __block ContactMetadata contact(base_contact);
  __block std::unordered_map<int, string> button_identity_map;
  CppDelegate* cpp_delegate = new CppDelegate;
  cpp_delegate->Add(
      @protocol(UIActionSheetDelegate), @selector(actionSheet:clickedButtonAtIndex:),
      ^(UIActionSheet* sheet, NSInteger index) {
        if (ContainsKey(button_identity_map, index)) {
          const string& identity = button_identity_map[index];
          // Construct a new contact that contains only the correct identity.
          ContactMetadata new_contact(contact);
          new_contact.set_primary_identity(identity);
          new_contact.clear_identities();
          new_contact.add_identities()->set_identity(identity);
          // These fields shouldn't make any difference with this usage of ContactMetadata, but
          // clear them anyway just in case.  Removing contact_source will ensure we get an
          // error if we try to write this contact back to the database.
          new_contact.clear_indexed_names();
          new_contact.clear_contact_id();
          new_contact.clear_server_contact_id();
          new_contact.clear_contact_source();
          callback(&new_contact);
        } else {
          callback(NULL);
        }
        sheet.delegate = NULL;
        delete cpp_delegate;
      });
  UIActionSheet* sheet = [[UIActionSheet alloc]
                             initWithTitle:Format("How would you like to invite %s?",
                                                  ContactManager::FormatName(contact, false, false))
                                  delegate:cpp_delegate->delegate()
                           cancelButtonTitle:nil
                           destructiveButtonTitle:nil
                           otherButtonTitles:nil];
  for (int i = 0; i < contact.identities_size(); i++) {
    const string& identity = contact.identities(i).identity();
    if (IdentityManager::IsEmailIdentity(identity) ||
        IdentityManager::IsPhoneIdentity(identity)) {
      string button_text = IdentityManager::IdentityToName(identity);
      const string& description = contact.identities(i).description();
      if (!description.empty()) {
        button_text = Format("%s: %s", description, button_text);
      }
      const int index = [sheet addButtonWithTitle:NewNSString(button_text)];
      button_identity_map[index] = identity;
    }
  }
  sheet.cancelButtonIndex = [sheet addButtonWithTitle:@"Cancel"];
  [sheet showInView:parent_view];
}
