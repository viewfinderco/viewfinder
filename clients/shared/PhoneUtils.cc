// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <unicode/uchar.h>
#import <re2/re2.h>
#import <phonenumbers/asyoutypeformatter.h>
#import <phonenumbers/phonenumberutil.h>
#import "LazyStaticPtr.h"
#import "PhoneUtils.h"
#import "ScopedPtr.h"

using namespace i18n::phonenumbers;

namespace {

LazyStaticPtr<RE2, const char*> kPhonePrefixRE = { "^[-+() 0-9]*$" };

}  // namespace

bool IsValidPhoneNumber(const string& s, const string& country_code) {
  PhoneNumber number;
  PhoneNumberUtil::ErrorType error =
      PhoneNumberUtil::GetInstance()->Parse(s, country_code, &number);
  if (error != PhoneNumberUtil::NO_PARSING_ERROR) {
    return false;
  }
  return PhoneNumberUtil::GetInstance()->IsValidNumber(number);
}

bool IsPhoneNumberPrefix(const string& s) {
  return RE2::FullMatch(s, *kPhonePrefixRE);
}

string FormatPhoneNumberPrefix(const string& s, const string& country_code) {
  ScopedPtr<AsYouTypeFormatter> formatter(
      PhoneNumberUtil::GetInstance()->GetAsYouTypeFormatter(country_code));
  string result;
  for (int i = 0; i < s.size(); i++) {
    if (IsPhoneDigit(s[i])) {
      formatter->InputDigit(s[i], &result);
    }
  }
  return result;
}

string NormalizedPhoneNumber(const string& s, const string& country_code) {
  PhoneNumber number;
  PhoneNumberUtil::ErrorType error =
      PhoneNumberUtil::GetInstance()->Parse(s, country_code, &number);
  if (error != PhoneNumberUtil::NO_PARSING_ERROR) {
    return "";
  }
  string result;
  PhoneNumberUtil::GetInstance()->Format(number, PhoneNumberUtil::E164, &result);
  return result;
}

bool IsPhoneDigit(int chr) {
  return u_isdigit(chr) || chr == '+';
}
