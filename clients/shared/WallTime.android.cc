// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "WallTime.h"
#import "WallTime.android.h"

std::function<jlong (jlong)> time_zone_offset;
std::function<string ()> time_zone_name;

struct tm LocalTime(WallTime time) {
  // Timezones appear to be broken in Android JNI code. Specifically, the
  // current timezone appears to always be either UTC or GMT with no ability to
  // change via tzset(). Google reveals that localtime_r() is essentially just
  // a small wrapper around gmtime_r().
  //
  // NOTE(peter): Note that time_zone_offset results in a call into Java. I
  // hope this is fast enough because making it faster will be painful.
  const time_t time_sec = static_cast<time_t>(time);
  const time_t local_time_sec = time_sec -
      (time_zone_offset ? time_zone_offset(time_sec) : 0);
  struct tm t;
  gmtime_r(&local_time_sec, &t);
  return t;
}
