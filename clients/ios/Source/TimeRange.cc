// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#include <sys/time.h>
#include <math.h>
#include "Logging.h"
#include "StringUtils.h"
#include "TimeRange.h"

namespace {

const float kMinute = 60;
const float kFifteen = kMinute * 15;
const float kHour = 60 * kMinute;
const float kDay = kHour * 24;
const float kWeek = 7 * kDay;
const float kMonth = 31 * kDay;
const float kYear = 365 * kDay;

// Remove the double-spaces which WallTimeFormat adds in the case of
// single-digit day of month value.
string FormatDate(const char* fmt, WallTime time) {
  string date = Format("%s", WallTimeFormat(fmt, time));
  while (!date.empty() && date[0] == ' ') {
    date.erase(0, 1);
  }
  for (int pos = 0; (pos = date.find("  ", pos)) != string::npos; ) {
    date.erase(pos, 1);
  }
  return date;
}

struct TimeScale {
  const float delta_secs;
  string (^format_inner)(WallTime, WallTime, bool);
  string (^format_outer)(WallTime, WallTime, bool);
  WallTime (^current_inner)(WallTime);
  WallTime (^current_outer)(WallTime);
  WallTime (^next_inner)(WallTime);
  WallTime (^next_outer)(WallTime);
};

TimeScale kTimeScales[] = {
  // Hours
  { kDay,
    ^(WallTime st, WallTime et, bool ascending) {
      if (st == et) {
        return string(Format("%s", FormatDate("%l:%M %p", et)));
      } else {
        if (!ascending) std::swap(st, et);
        if (et - st <= kFifteen) {
          return string(Format("%s - %s", FormatDate("%l:%M", st),
                               FormatDate("%l:%M %p", et)));
        } else {
          return string(Format("%s - %s", FormatDate("%l:%M %p", st),
                               FormatDate("%l:%M %p", et)));
        }
      }
    },
    ^(WallTime st, WallTime et, bool ascending) {
      if (et - st <= kHour + 1) {  // account for leap seconds
        return string(Format("%s", FormatDate("%a, %l %p", st)));
      } else {
        if (!ascending) std::swap(st, et);
        if (CurrentDay(st) == CurrentDay(et - 1)) {
          return string(Format("%s - %s", FormatDate("%a, %l%p", st),
                               FormatDate("%l%p", et)));
        } else {
          return string(Format("%s - %s", FormatDate("%a, %l%p", st),
                               FormatDate("%a, %l%p", et)));
        }
      }
    },
    ^(WallTime t) { return CurrentHour(t) + int((t - CurrentHour(t)) / kFifteen) * kFifteen; },
    ^(WallTime t) { return CurrentHour(t); },
    ^(WallTime t) { return CurrentHour(t) + int((t - CurrentHour(t)) / kFifteen) * kFifteen + kFifteen; },
    ^(WallTime t) { return NextHour(t); },
  },
  // Days
  { kWeek,
    ^(WallTime st, WallTime et, bool ascending) {
      if (et - st <= kHour + 1) {  // account for leap seconds
        return string(Format("%s", FormatDate("%l %p", st)));
      } else {
        if (!ascending) std::swap(st, et);
        return string(Format("%s - %s", FormatDate("%l:%M %p", st),
                             FormatDate("%l%p", et)));
      }
    },
    ^(WallTime st, WallTime et, bool ascending) {
      if (et - st <= kDay + 1) {  // account for leap seconds
        return string(Format("%s", FormatDate("%a, %b %e", st)));
      } else {
        et -= 1;  // exclusive of days.
        if (!ascending) std::swap(st, et);
        return string(Format("%s - %s", FormatDate("%b %e", st),
                             FormatDate("%b %e", et)));
      }
    },
    ^(WallTime t) { return CurrentHour(t); },
    ^(WallTime t) { return CurrentDay(t); },
    ^(WallTime t) { return NextHour(t); },
    ^(WallTime t) { return NextDay(t); },
  },
  // Months
  { 3 * kMonth,
    ^(WallTime st, WallTime et, bool ascending) {
      if (et - st <= kDay + 1) {  // account for leap seconds
        return string(Format("%s", FormatDate("%b %e", st)));
      } else {
        et -= 1;  // exclusive of days.
        if (!ascending) std::swap(st, et);
        return string(Format("%s - %s", FormatDate("%b %e", st),
                             FormatDate("%b %e", et)));
      }
    },
    ^(WallTime st, WallTime et, bool ascending) {
      if (et - st <= kMonth + 1) {  // account for leap seconds
        return string(Format("%s", FormatDate("%B", st)));
      } else {
        et -= 1;  // exclusive of months.
        if (!ascending) std::swap(st, et);
        return string(Format("%s - %s", FormatDate("%b", st),
                             FormatDate("%b", et)));
      }
    },
    ^(WallTime t) { return CurrentDay(t); },
    ^(WallTime t) { return CurrentMonth(t); },
    ^(WallTime t) { return NextDay(t); },
    ^(WallTime t) { return NextMonth(t); },
  },
  // Years
  { std::numeric_limits<double>::max(),
    ^(WallTime st, WallTime et, bool ascending) {
      if (et - st <= kMonth + 1) {  // account for leap seconds
        return string(Format("%s", FormatDate("%b", st)));
      } else if (CurrentYear(st) == CurrentYear(et - 1)) {
        et -= 1;  // exclusive of days.
        if (!ascending) std::swap(st, et);
        return string(Format("%s - %s", FormatDate("%b", st),
                             FormatDate("%b", et)));
      } else {
        et -= 1;  // exclusive of months.
        if (!ascending) std::swap(st, et);
        return string(Format("%s - %s", FormatDate("%b %Y", st),
                             FormatDate("%b %Y", et)));
      }
    },
    ^(WallTime st, WallTime et, bool ascending) {
      if (et - st <= kYear + kDay + 1) {  // account for leap year & leap second
        return string(Format("%s", FormatDate("%Y", st)));
      } else {
        et -= 1;  // exclusive of years.
        if (!ascending) std::swap(st, et);
        return string(Format("%s - %s", FormatDate("%Y", st),
                             FormatDate("%Y", et)));
      }
    },
    ^(WallTime t) { return CurrentMonth(t); },
    ^(WallTime t) { return CurrentYear(t); },
    ^(WallTime t) { return NextMonth(t); },
    ^(WallTime t) { return NextYear(t); },
  },
};

const TimeScale& GetTimeScale(float time_scale) {
  for (int i = 0; i < ARRAYSIZE(kTimeScales); ++i) {
    if (time_scale < kTimeScales[i].delta_secs) {
      return kTimeScales[i];
    }
  }
  return kTimeScales[ARRAYSIZE(kTimeScales) - 1];
}

}  // namespace


string FormatOuterTimeRange(float time_scale, WallTime st, WallTime et, bool ascending) {
  return ToUppercase(GetTimeScale(time_scale).format_outer(st, et, ascending));
}

string FormatInnerTimeRange(float time_scale, WallTime st, WallTime et, bool ascending) {
  return ToUppercase(GetTimeScale(time_scale).format_inner(st, et, ascending));
}

WallTime GetCurrentOuterTime(float time_scale, WallTime ts) {
  return GetTimeScale(time_scale).current_outer(ts);
}

WallTime GetCurrentInnerTime(float time_scale, WallTime ts) {
  return GetTimeScale(time_scale).current_inner(ts);
}

WallTime GetNextOuterTime(float time_scale, WallTime ts) {
  return GetTimeScale(time_scale).next_outer(ts);
}

WallTime GetNextInnerTime(float time_scale, WallTime ts) {
  return GetTimeScale(time_scale).next_inner(ts);
}
