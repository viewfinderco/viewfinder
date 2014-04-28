// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell.

@class UIView;

class ContactMetadata;

// Displays a UIActionSheet to let the user choose one of the identities of a
// contact.  The callback is invoked with a new ContactMetadata containing a
// single identity along with other fields copied from the original source, or
// null if the sheet was cancelled.  The resulting contact is valid to be added
// to a conversation as a prospective user but should not be saved with
// SaveContact.
void ChooseIdentityForContact(
    const ContactMetadata& base_contact, UIView* parent_view,
    void (^callback)(const ContactMetadata*));
