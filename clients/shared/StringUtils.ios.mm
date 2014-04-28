// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <CoreFoundation/CFUUID.h>
#import <Foundation/NSNumberFormatter.h>
#import "StringUtils.h"

int LocalizedCaseInsensitiveCompare(const Slice& a, const Slice& b) {
  // Note that this is called frequently, so we go through the hassle of
  // avoiding copying the string data.
  NSString* a_str =
      [[NSString alloc]
        initWithBytesNoCopy:(void*)a.data()
                     length:a.size()
                   encoding:NSUTF8StringEncoding
               freeWhenDone:NO];
  NSString* b_str =
      [[NSString alloc]
        initWithBytesNoCopy:(void*)b.data()
                     length:b.size()
                   encoding:NSUTF8StringEncoding
               freeWhenDone:NO];
  return [a_str localizedCaseInsensitiveCompare:b_str];
}

string LocalizedNumberFormat(int value) {
  NSString* s =
      [NSNumberFormatter
       localizedStringFromNumber:[NSNumber numberWithInt:value]
                     numberStyle:NSNumberFormatterDecimalStyle];
  return ToString(s);
}

string NewUUID() {
  CFUUIDRef uuid = CFUUIDCreate(NULL);
  CFStringRef uuid_str = CFUUIDCreateString(NULL, uuid);
  const string s = ToString((__bridge NSString*)uuid_str);
  CFRelease(uuid_str);
  CFRelease(uuid);
  return s;
}

// local variables:
// mode: c++
// end:
