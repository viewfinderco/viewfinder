// Copyright 2013 Viewfinder. All rights reserved.
// Author: Marc Berhault.

#import <stdio.h>
#import <sys/limits.h>
#import "Compat.android.h"

time_t timegm(struct tm* const t) {
  // time_t is signed on Android.
  static const time_t kTimeMax = ~(1 << (sizeof(time_t) * CHAR_BIT - 1));
  static const time_t kTimeMin = (1 << (sizeof(time_t) * CHAR_BIT - 1));
  time64_t result = timegm64(t);
  if (result < kTimeMin || result > kTimeMax)
    return -1;
  return result;
}
