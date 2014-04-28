// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <phonenumbers/phonenumberutil.h>
#import "AddressBookManager.h"
#import "ContactManager.h"
#import "ContactMetadata.pb.h"
#import "IdentityManager.h"
#import "LocaleUtils.h"
#import "Logging.h"
#import "ScopedRef.h"
#import "UIAppState.h"
#import "Utils.h"
#import "ValueUtils.h"


namespace {

// Some users have contacts with hundreds of identities.  These will cause problems if uploaded
// to the server, so truncate them at import time.
const int kMaxIdentitiesPerContact = 50;

// No contact field is allowed to exceed this length (in utf8-encoded bytes).
// Contacts with excessively long fields are assumed to be invalid and skipped.
// The server applies a limit of 1000 characters, which is strictly greater than
// this byte limit.
const int kMaxFieldSize = 1000;

bool AuthorizationSupported() {
  // Prior to iOS 6.0, no authorization was needed to access the address book.
  return kIOSVersion >= "6.0";
}

string ConstructFullName(const Value& first, const Value& last) {
  // The address book has a method ABRecordCopyCompositeName which does this for us.
  // However, it also includes prefixes, middle name/initial, and suffixes, which we
  // cannot represent in our current data model.  Any of this data we collected from
  // the address book would disappear when the contact converted to a full user, so it's
  // better to only use first and last name from the beginning.
  // TODO(ben): merge with ContactManager::ConstructFullName.  This version uses optional Values
  // while the one in ContactManager uses const string&s.
  if (!first.get()) {
    return ToString(last);
  } else if (!last.get()) {
    return ToString(first);
  } else {
    return Format("%s %s", first, last);
  }
}

string GetLabelAtIndex(ABMultiValueRef multi, int i) {
  ScopedRef<CFStringRef> label((CFStringRef)ABMultiValueCopyLabelAtIndex(multi, i));
  if (label.get()) {
    // The label field is usually an opaque token which must be converted into
    // a localized form for display.
    Value localized_label((CFStringRef)ABAddressBookCopyLocalizedLabel(label.get()));
    return ToString(localized_label);
  }
  return "";
}

}  // namespace

AddressBookManager::AddressBookManager(UIAppState* state)
    : state_(state),
      authorization_determined_(false),
      authorized_(false) {
  if (!AuthorizationSupported()) {
    authorization_determined_ = true;
    authorized_ = true;
  } else {
    // iOS guarantees that permissions will not change while the app is running or in the
    // background except to change from "undetermined" to another state (if the app is in the
    // background while the user toggles the permission in the settings app, it will be killed).
    // Therefore we don't need to refresh this status once authorization has been determined.
    switch (ABAddressBookGetAuthorizationStatus()) {
      case kABAuthorizationStatusRestricted:
      case kABAuthorizationStatusDenied:
        authorization_determined_ = true;
        authorized_ = false;
        break;

      case kABAuthorizationStatusAuthorized:
        authorization_determined_ = true;
        authorized_ = true;
        break;
      case kABAuthorizationStatusNotDetermined:
        break;
    }
  }
}

AddressBookManager::~AddressBookManager() {
}

void AddressBookManager::Authorize(void (^callback)()) {
  if (authorization_determined_) {
    callback();
  }
  CreateAuthorizedAddressBook(^(ABAddressBookRef address_book) {
      dispatch_main(callback);
    });
}

void AddressBookManager::ImportContacts(void (^callback)(bool success)) {
  CreateAuthorizedAddressBook(^(ABAddressBookRef address_book) {
      if (!address_book) {
        dispatch_main(^{
            callback(false);
          });
        return;
      }

      const string iso_code = GetPhoneNumberCountryCode();
      const i18n::phonenumbers::PhoneNumberUtil& phone_util =
          *i18n::phonenumbers::PhoneNumberUtil::GetInstance();

      Array entries(ABAddressBookCopyArrayOfAllPeople(address_book));
      LOG("address book: importing %d entries", entries.size());

      vector<ContactMetadata> contacts;

      for (int i = 0; i < entries.size(); ++i) {
        ABRecordRef entry = (__bridge ABRecordRef)entries[i].get();
        Value first(ABRecordCopyValue(entry, kABPersonFirstNameProperty));
        Value last(ABRecordCopyValue(entry, kABPersonLastNameProperty));

        if (!first.get() && !last.get()) {
          // No first or last name, must be a company instead of a person.
          continue;
        }

        const string full_name = ConstructFullName(first, last);
        if (full_name.size() > kMaxFieldSize) {
          continue;
        }

        ContactMetadata contact;
        contact.set_contact_source(ContactManager::kContactSourceIOSAddressBook);
        if (first.get()) {
          contact.set_first_name(ToString(first));
          if (contact.first_name().size() > kMaxFieldSize) {
            continue;
          }
        }
        if (last.get()) {
          contact.set_last_name(ToString(last));
          if (contact.last_name().size() > kMaxFieldSize) {
            continue;
          }
        }
        contact.set_name(full_name);

        ScopedRef<ABMultiValueRef> email(
            (ABMultiValueRef)ABRecordCopyValue(entry, kABPersonEmailProperty));
        if (email) {
          for (int i = 0;
               i < ABMultiValueGetCount(email) && contact.identities_size() < kMaxIdentitiesPerContact;
               ++i) {
            Value value((CFStringRef)ABMultiValueCopyValueAtIndex(email, i));

            const string email_str = ToString(value);
            string email_error;
            if (!IsValidEmailAddress(email_str, &email_error)) {
              continue;
            }

            const string label = GetLabelAtIndex(email, i);

            if (email_str.size() > kMaxFieldSize ||
                label.size() > kMaxFieldSize) {
              continue;
            }

            ContactIdentityMetadata* contact_id = contact.add_identities();
            contact_id->set_identity(IdentityManager::IdentityForEmail(email_str));

            if (!label.empty()) {
              contact_id->set_description(label);
            }
          }
        }

        ScopedRef<ABMultiValueRef> phone(
            (ABMultiValueRef)ABRecordCopyValue(entry, kABPersonPhoneProperty));
        if (phone) {
          for (int i = 0;
               i < ABMultiValueGetCount(phone) && contact.identities_size() < kMaxIdentitiesPerContact;
               ++i) {
            Value value((CFStringRef)ABMultiValueCopyValueAtIndex(phone, i));

            i18n::phonenumbers::PhoneNumber number;
            i18n::phonenumbers::PhoneNumberUtil::ErrorType error =
                phone_util.Parse([value UTF8String], iso_code, &number);

            if (error != phone_util.NO_PARSING_ERROR) {
              LOG("address book: parse error %s", error);
              continue;
            }
            if (!phone_util.IsValidNumber(number)) {
              // In real data, this is most common for old 7-digit numbers without area code.  They
              // will parse without error, but they are not "valid" and it would be incorrect to
              // format them as E164.
              // This will also reject numbers from area codes that do not exist, which tends to exclude
              // randomly-typed test data.
              //LOG("address book: invalid number %s", value);
              continue;
            }

            string formatted;
            phone_util.Format(number, phone_util.E164, &formatted);

            const string label = GetLabelAtIndex(phone, i);

            if (formatted.size() > kMaxFieldSize ||
                label.size() > kMaxFieldSize) {
              continue;
            }

            ContactIdentityMetadata* contact_id = contact.add_identities();
            contact_id->set_identity(IdentityManager::IdentityForPhone(formatted));

            if (!label.empty()) {
              contact_id->set_description(label);
            }
          }
        }

        if (contact.identities_size() == 0) {
          //LOG("address book: no identities for %s, skipping", full_name);
          continue;
        }

        contacts.push_back(contact);
      }

      DBHandle updates = state_->NewDBTransaction();
      // If we're in initial mobile contacts import state, invoke done
      // synchronously as we can't wait for network queue to process
      // upload, as that's only done while state is OK.
      auto fetch_cb = ^{
        dispatch_main(^{
            callback(true);
          });
      };
      state_->contact_manager()->ProcessAddressBookImport(contacts, updates, ^{});
      updates->Commit();
      fetch_cb();
    });
}

void AddressBookManager::CreateAuthorizedAddressBook(
    void (^callback)(ABAddressBookRef address_book)) {
  if (authorization_determined_ && !authorized_) {
    LOG("address book: not authorized");
    dispatch_high_priority(^{
        callback(NULL);
      });
    return;
  }
  CFErrorRef error;
  ABAddressBookRef address_book = ABAddressBookCreateWithOptions(NULL, &error);
  if (!address_book) {
    LOG("address book: ABAddressBookCreate failed: %s", error);
    dispatch_high_priority(^{
        callback(NULL);
      });
    return;
  }
  // On iOS 6, we must request access for each ABAddressBook created.  On older versions,
  // the necessary functions don't exist.
  if (!AuthorizationSupported()) {
    dispatch_high_priority(^{
        CFRelease(address_book);
        callback(NULL);
      });
    return;
  }
  ABAddressBookRequestAccessWithCompletion(
      address_book,
      ^(bool granted, CFErrorRef error) {
        if (error) {
          LOG("address book: error requesting access: %s", error);
        } else {
          authorization_determined_ = true;
          authorized_ = granted;
        }
        if (!granted) {
          dispatch_high_priority(^{
              callback(NULL);
              CFRelease(address_book);
            });
        } else {
          dispatch_high_priority(^{
              callback(address_book);
              CFRelease(address_book);
            });
        }
      });
}

// local variables:
// mode: c++
// end:
