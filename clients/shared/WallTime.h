// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_WALLTIME_H
#define VIEWFINDER_WALLTIME_H

#import <iostream>
#import <time.h>
#import "Utils.h"

typedef double WallTime;

WallTime WallTime_Now();
WallTime CurrentHour(WallTime t);
WallTime CurrentDay(WallTime t);
WallTime CurrentMonth(WallTime t);
WallTime CurrentYear(WallTime t);
WallTime NextHour(WallTime t);
WallTime NextDay(WallTime t);
WallTime NextMonth(WallTime t);
WallTime NextYear(WallTime t);
struct tm LocalTime(WallTime t);

// Formats time with a trailing "a" or "p" for AM and PM respectively.
string FormatTime(WallTime time);

// Remove the double-spaces which WallTimeFormat adds in the case of
// single-digit day of month value.
string FormatDate(const char* fmt, WallTime time);

// Format a time (hours and minutes) relative to "now". Always includes
// the time, but depending on elapsed time since "t", may include
// progressively general date information as well.
string FormatRelativeTime(WallTime t, WallTime now);

enum TimeAgoFormat {
  TIME_AGO_SHORT,  // e.g. "42m"
  TIME_AGO_MEDIUM,  //  e.g. "42m ago"
  TIME_AGO_LONG,  // e.g. "42 minutes ago"
};
// Format "time ago", a relative expression of time elapsed since the
// time "ago" to "now".
string FormatTimeAgo(WallTime ago, WallTime now, TimeAgoFormat format);
// Format a time range using abbreviated weekday, month and full
// 4-digit year. If the times are within the same day or if they cross
// days but are less than 12 hours apart, displays just the time
// differential. If the times cross days and are 12 hours or more
// apart, displays full date and time range using abbreviated weekday,
// month and full 4-digit year.
string FormatTimeRange(WallTime begin, WallTime end);

// Format a date relative to "now". Time is included if the date is
// within the last week. Otherwise, depending on elapsed time since
// "t", includes progressively general date information.
string FormatRelativeDate(WallTime d, WallTime now);
// Formats a short version of the relative date.
string FormatShortRelativeDate(WallTime d, WallTime now);
// Format a date range relative to the current time.
string FormatDateRange(WallTime begin, WallTime end, WallTime now);

// Sleep the current thread for the specified duration.
void WallTimeSleep(WallTime t);

class WallTimeFormat {
 public:
  // Like strftime() format, but also accepts %Q for milliseconds and %N for
  // nanonseconds.
  WallTimeFormat(const string& fmt, WallTime time, bool localtime = true)
      : fmt_(fmt),
        time_(time),
        localtime_(localtime) {
  }

  void Print(ostream& os) const;

 private:
  string fmt_;
  const WallTime time_;
  const bool localtime_;
};

struct WallTimeInterval {
 public:
  WallTimeInterval(WallTime b = 0, WallTime e = 0)
      : begin(b),
        end(e) {
  }

  WallTime size() const { return end - begin; }

  WallTime begin;
  WallTime end;
};

inline bool operator<(const WallTimeInterval& a, const WallTimeInterval& b) {
  return a.begin < b.begin;
}

inline ostream& operator<<(
    ostream& os, const WallTimeFormat& f) {
  f.Print(os);
  return os;
}

#endif // VIEWFINDER_WALLTIME_H
