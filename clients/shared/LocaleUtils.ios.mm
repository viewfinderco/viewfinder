// Copryright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import <mutex>
#import <CoreTelephony/CTCarrier.h>
#import <CoreTelephony/CTTelephonyNetworkInfo.h>
#import "LocaleUtils.h"
#import "StringUtils.h"

namespace {

std::once_flag once;
string phone_number_country_code;

}  // namespace

string GetPhoneNumberCountryCode() {
  std::call_once(once, [] {
      // If there is a cellular provider, use its country code.
      CTTelephonyNetworkInfo* info = [CTTelephonyNetworkInfo new];
      const string from_carrier =
          ToUppercase(ToString(info.subscriberCellularProvider.isoCountryCode));
      if (!from_carrier.empty()) {
        phone_number_country_code = from_carrier;
        return;
      }

      // If there is no carrier info (simulator, ipod touch, etc), fall back to the system locale.
      const string from_locale = ToString([[NSLocale currentLocale] objectForKey:NSLocaleCountryCode]);
      if (!from_locale.empty()) {
        phone_number_country_code = from_locale;
        return;
      }
      // As a last resort, default to US.
      phone_number_country_code = "US";
    });
  return phone_number_country_code;
}
