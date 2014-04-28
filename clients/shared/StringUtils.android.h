// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_STRING_UTILS_ANDROID_H
#define VIEWFINDER_STRING_UTILS_ANDROID_H

#import <functional>
#import "Utils.h"

extern std::function<int (string, string)> localized_case_insensitive_compare;
extern std::function<string (int)> localized_number_format;
extern std::function<string ()> new_uuid;

#endif  // VIEWFINDER_STRING_UTILS_ANDROID_H
