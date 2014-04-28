// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <phonenumbers/phonenumberutil.h>
#import <re2/re2.h>
#import "IdentityManager.h"
#import "LazyStaticPtr.h"
#import "LocaleUtils.h"
#import "Logging.h"

// Authority types.
const string IdentityManager::kViewfinderAuthority = "Viewfinder";
const string IdentityManager::kGoogleAuthority = "Google";
const string IdentityManager::kFacebookAuthority = "Facebook";

// Identity types (by prefix).
const string IdentityManager::kEmailIdentityPrefix = "Email:";
const string IdentityManager::kPhoneIdentityPrefix = "Phone:";
const string IdentityManager::kFacebookIdentityPrefix = "FacebookGraph:";
const string IdentityManager::kViewfinderIdentityPrefix = "VF:";

namespace {

// Quick check for phone numbers in E164 format: starts with a plus, and then only digits.
LazyStaticPtr<RE2, const char*> kPhoneNumberRE = { "^\\+[0-9]+$" };

}  // namespace

string IdentityManager::IdentityToName(const Slice& identity) {
  if (IsEmailIdentity(identity)) {
    return EmailFromIdentity(identity);
  } else if (IsPhoneIdentity(identity)) {
    return PhoneFromIdentity(identity);
  }
  return string();
}

string IdentityManager::IdentityToDisplayName(const Slice& identity) {
  if (IsEmailIdentity(identity)) {
    return EmailFromIdentity(identity);
  } else if (IsPhoneIdentity(identity)) {
    return PhoneFromIdentity(identity);
  } else if (IsFacebookIdentity(identity)) {
    return "Facebook";
  }
  return string();
}

string IdentityManager::IdentityType(const Slice& identity) {
  if (IsEmailIdentity(identity)) {
    return "email";
  } else if (IsPhoneIdentity(identity)) {
    return "mobile";
  } else if (IsFacebookIdentity(identity)) {
    return "Facebook";
  } else if (IsViewfinderIdentity(identity)) {
    return "Viewfinder";
  }
  return string();
}

bool IdentityManager::IsEmailIdentity(const Slice& identity) {
  return identity.starts_with(kEmailIdentityPrefix);
}

bool IdentityManager::IsPhoneIdentity(const Slice& identity) {
  return identity.starts_with(kPhoneIdentityPrefix);
}

bool IdentityManager::IsFacebookIdentity(const Slice& identity) {
  return identity.starts_with(kFacebookIdentityPrefix);
}

bool IdentityManager::IsViewfinderIdentity(const Slice& identity) {
  return identity.starts_with(kViewfinderIdentityPrefix);
}

string IdentityManager::IdentityForUserId(int64_t user_id) {
  return Format("%s%s", kViewfinderIdentityPrefix, user_id);
}

string IdentityManager::IdentityForEmail(const string& email) {
  return Format("%s%s", kEmailIdentityPrefix, ToLowercase(email));
}

string IdentityManager::IdentityForPhone(const Slice& phone) {
  CHECK(RE2::FullMatch(phone, *kPhoneNumberRE));
  return Format("%s%s", kPhoneIdentityPrefix, phone);
}

string IdentityManager::EmailFromIdentity(const Slice& identity) {
  if (IsEmailIdentity(identity)) {
    return identity.substr(kEmailIdentityPrefix.size()).ToString();
  }
  return string();
}

string IdentityManager::PhoneFromIdentity(const Slice& identity) {
  const string raw_phone = RawPhoneFromIdentity(identity);
  using i18n::phonenumbers::PhoneNumberUtil;
  i18n::phonenumbers::PhoneNumber number;
  PhoneNumberUtil* phone_util = PhoneNumberUtil::GetInstance();
  PhoneNumberUtil::ErrorType error = phone_util->Parse(raw_phone, "ZZ", &number);
  if (error != PhoneNumberUtil::NO_PARSING_ERROR) {
    return string();
  }
  const bool in_country = (number.country_code() == phone_util->GetCountryCodeForRegion(GetPhoneNumberCountryCode()));
  string formatted;
  phone_util->Format(number, in_country ? PhoneNumberUtil::NATIONAL : PhoneNumberUtil::INTERNATIONAL, &formatted);
  return formatted;
}

string IdentityManager::RawPhoneFromIdentity(const Slice& identity) {
  if (!IsPhoneIdentity(identity)) {
    return string();
  }
  return ToString(identity.substr(kPhoneIdentityPrefix.size()));
}

// local variables:
// mode: c++
// end:
