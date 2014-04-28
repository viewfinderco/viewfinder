// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "WallTime.h"

struct tm LocalTime(WallTime time) {
  const time_t time_sec = static_cast<time_t>(time);
  struct tm t;
  localtime_r(&time_sec, &t);
  return t;
}
