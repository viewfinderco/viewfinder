// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#import "Utils.h"

// Returns true if the given string is a valid phone number in the
// current locale.
bool IsValidPhoneNumber(const string& s, const string& country_code);

// Returns true if the string could be the beginning of a phone number (i.e. it
// contains only digits and formatting characters).
bool IsPhoneNumberPrefix(const string& s);

// Returns a partial number formatted for the given locale.  See also
// PhoneNumberFormatter for additional integration with a UITextField.
string FormatPhoneNumberPrefix(const string& s, const string& country_code);

// Returns a normalized (E164) version of the given phone number.
string NormalizedPhoneNumber(const string& s, const string& country_code);

// Digits and plus signs are considered significant on input; all other formatting characters are
// ignored on input and inserted by the formatter.
bool IsPhoneDigit(int chr);
