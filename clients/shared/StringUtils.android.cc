// Copryright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault

#import "StringUtils.h"
#import "StringUtils.android.h"

std::function<int (string, string)> localized_case_insensitive_compare;
std::function<string (int)> localized_number_format;
std::function<string ()> new_uuid;

int LocalizedCaseInsensitiveCompare(const Slice& a, const Slice& b) {
  if (!localized_case_insensitive_compare) {
    return a.compare(b);
  }
  return localized_case_insensitive_compare(a.ToString(), b.ToString());
}

string LocalizedNumberFormat(int value) {
  if (!localized_number_format) {
    return ToString(value);
  }
  return localized_number_format(value);
}

string NewUUID() {
  if (!new_uuid) {
    return ToString(-1);
  }
  return new_uuid();
}
