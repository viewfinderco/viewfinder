// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_IDENTITY_MANAGER_H
#define VIEWFINDER_IDENTITY_MANAGER_H

#import "Utils.h"

// The IdentityManager class handles identity syntax and parsing.
class IdentityManager {
 public:
  // Returns a human-readable representation of a contact identity for
  // contact indexing.
  static string IdentityToName(const Slice& identity);

  // Returns a human-readable representation of a contact identity for
  // display in the UI.
  static string IdentityToDisplayName(const Slice& identity);

  // Returns the type of identity in a human-readable representation.
  static string IdentityType(const Slice& identity);

  static bool IsEmailIdentity(const Slice& identity);
  static bool IsPhoneIdentity(const Slice& identity);
  static bool IsFacebookIdentity(const Slice& identity);
  static bool IsViewfinderIdentity(const Slice& identity);

  // Returns the identity string for the given viewfinder user id.
  // Note that these are "fake" identities not supported by the server.
  static string IdentityForUserId(int64_t user_id);

  // Returns the identity string for the given email address.
  // Converts the address to a canonical form, consistent with the backend
  // Identity.CanonicalizeEmail() function.
  static string IdentityForEmail(const string& email);

  // Phone number must be in normalized (E164) format.
  static string IdentityForPhone(const Slice& phone);

  // Extracts the email address from the identity. Returns an empty string if
  // no email address can be found.
  static string EmailFromIdentity(const Slice& identity);

  // Extracts the phone number from the identity (formatted for the current locale.
  // Returns an empty string if it is not a phone identity.
  static string PhoneFromIdentity(const Slice& identity);

  // Returns the unformatted (E164) version of the phone number for this identity.
  static string RawPhoneFromIdentity(const Slice& identity);

 private:
  // Authority types.
  static const string kViewfinderAuthority;
  static const string kGoogleAuthority;
  static const string kFacebookAuthority;

  // Identity types (by prefix).
  static const string kEmailIdentityPrefix;
  static const string kPhoneIdentityPrefix;
  static const string kFacebookIdentityPrefix;
  static const string kViewfinderIdentityPrefix;
};

#endif  // VIEWFINDER_IDENTITY_MANAGER_H

// local variables:
// mode: c++
// end:
