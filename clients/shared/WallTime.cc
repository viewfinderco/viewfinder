// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <sys/time.h>
#import <math.h>
#import "Logging.h"
#import "StringUtils.h"
#import "WallTime.h"

namespace {

const WallTime kMinute = 60;
const WallTime kHour = 60 * kMinute;
const WallTime kDay = 24 * kHour;
const WallTime kHalfDay = 12 * kHour;
const WallTime kWeek = 7 * kDay;
const WallTime kMonth = 30 * kDay;

void PrintOne(ostream& os, struct tm& t,
              const string& fmt, int begin, int end) {
  if (begin != end) {
    char buf[128];
    if ((begin == 0) && (end == fmt.size())) {
      strftime(buf, sizeof(buf), fmt.c_str(), &t);
    } else {
      strftime(buf, sizeof(buf), fmt.substr(begin, end - begin).c_str(), &t);
    }
    os << buf;
  }
}

struct {
  double max_seconds;
  int divisor;
  const char* fmt;
  const char* medium_fmt;
  const char* long_fmt;
} kTimeAgoRanges[] = {
  { 1, 1, "now", "just now", "just now" },
  // Fractions are rounded, so the transition between singular and plural happens at 1.5x the base unit.
  { 1.5, 1, "%.0fs", "%.0fs ago", "%.0f second ago" },
  { 60, 1, "%.0fs", "%.0fs ago", "%.0f seconds ago" },
  { 60 * 1.5, 60, "%.0fm", "%.0fm ago", "%.0f minute ago" },
  { 60 * 60, 60, "%.0fm", "%.0fm ago", "%.0f minutes ago" },
  { 60 * 60 * 1.5, 60 * 60, "%.0fh", "%.0fh ago", "%.0f hour ago" },
  { 60 * 60 * 24, 60 * 60, "%.0fh", "%.0fh ago", "%.0f hours ago" },
  { 60 * 60 * 24 * 1.5, 60 * 60 * 24, "%.0fd", "%.0fd ago", "%.0f day ago" },
  { 60 * 60 * 24 * 7, 60 * 60 * 24, "%.0fd", "%.0fd ago", "%.0f days ago" },
};

}  // namespace

WallTime WallTime_Now() {
  struct timeval t;
  gettimeofday(&t, NULL);
  return t.tv_sec + (t.tv_usec / 1e6);
}

WallTime CurrentHour(WallTime time) {
  struct tm t = LocalTime(time);
  t.tm_sec = 0;
  t.tm_min = 0;
  t.tm_isdst = -1;
  return mktime(&t);
}

WallTime CurrentDay(WallTime time) {
  struct tm t = LocalTime(time);
  t.tm_sec = 0;
  t.tm_min = 0;
  t.tm_hour = 0;
  t.tm_isdst = -1;
  return mktime(&t);
}

WallTime CurrentMonth(WallTime time) {
  struct tm t = LocalTime(time);
  t.tm_sec = 0;
  t.tm_min = 0;
  t.tm_hour = 0;
  t.tm_mday = 1;
  t.tm_isdst = -1;
  return mktime(&t);
}

WallTime CurrentYear(WallTime time) {
  struct tm t = LocalTime(time);
  t.tm_sec = 0;
  t.tm_min = 0;
  t.tm_hour = 0;
  t.tm_mday = 1;
  t.tm_mon = 0;
  t.tm_isdst = -1;
  return mktime(&t);
}

WallTime NextHour(WallTime time) {
  struct tm t = LocalTime(time);
  t.tm_sec = 0;
  t.tm_min = 0;
  t.tm_hour += 1;
  t.tm_isdst = -1;
  return mktime(&t);
}

WallTime NextDay(WallTime time) {
  struct tm t = LocalTime(time);
  t.tm_sec = 0;
  t.tm_min = 0;
  t.tm_hour = 0;
  t.tm_mday += 1;
  t.tm_isdst = -1;
  return mktime(&t);
}

WallTime NextMonth(WallTime time) {
  struct tm t = LocalTime(time);
  t.tm_sec = 0;
  t.tm_min = 0;
  t.tm_hour = 0;
  t.tm_mday = 1;
  if (t.tm_mon == 11) {
    t.tm_year += 1;
    t.tm_mon = 0;
  } else {
    t.tm_mon += 1;
  }
  t.tm_isdst = -1;
  return mktime(&t);
}

WallTime NextYear(WallTime time) {
  struct tm t = LocalTime(time);
  t.tm_sec = 0;
  t.tm_min = 0;
  t.tm_hour = 0;
  t.tm_mday = 1;
  t.tm_mon = 0;
  t.tm_year += 1;
  t.tm_isdst = -1;
  return mktime(&t);
}

string FormatTime(WallTime time) {
  const WallTime cur_day = CurrentDay(time);
  return Trim(Format("%s%s", WallTimeFormat("%l:%M", time),
                     (time - cur_day < kHalfDay ? "a" : "p")));
}

string FormatDate(const char* fmt, WallTime time) {
  string date = Format("%s", WallTimeFormat(fmt, time));
  for (int pos = 0; (pos = date.find("  ", pos)) != string::npos; ) {
    date.erase(pos, 1);
  }
  return date;
}

string FormatRelativeTime(WallTime t, WallTime now) {
  if (CurrentDay(t) == CurrentDay(now)) {
    return FormatTime(t);
  }
  if (fabs(t - now) < kWeek) {
    return Format("%s%s", WallTimeFormat("%a, ", t), FormatTime(t));
  } else if (CurrentYear(t) == CurrentYear(now)) {
    return Format("%s%s", FormatDate("%b %e, ", t), FormatTime(t));
  }
  return Format("%s%s", FormatDate("%b %e, %Y, ", t), FormatTime(t));
}

string FormatTimeAgo(WallTime ago, WallTime now, TimeAgoFormat format) {
  double elapsed = now - ago;
  if (elapsed < 1) {
    return (format == TIME_AGO_SHORT) ? "now" : "just now";
  }
  for (int i = 0; i < ARRAYSIZE(kTimeAgoRanges); ++i) {
    if (elapsed < kTimeAgoRanges[i].max_seconds) {
      const char* format_string;
      if (format == TIME_AGO_SHORT) {
        format_string = kTimeAgoRanges[i].fmt;
      } else if (format == TIME_AGO_MEDIUM) {
        format_string = kTimeAgoRanges[i].medium_fmt;
      } else {
        format_string = kTimeAgoRanges[i].long_fmt;
      }
      return Format(format_string, elapsed / kTimeAgoRanges[i].divisor);
    }
  }
  if (CurrentYear(ago) != CurrentYear(now)) {
    if (format == TIME_AGO_SHORT) {
      return Format("%s", WallTimeFormat("%b %e, %Y", ago));
    } else {
      return Format("%s", WallTimeFormat("on %b %e, %Y", ago));
    }
  } else {
    if (format == TIME_AGO_SHORT) {
      return Format("%s", FormatDate("%b %e", ago));
    } else {
      return Format("%s", FormatDate("on %b %e", ago));
    }
  }
}

string FormatTimeRange(WallTime begin, WallTime end) {
  const bool within_12_hours = fabs(end - begin) < kDay / 2;
  const bool same_day = int(end / kDay) == int(begin / kDay);

  if (within_12_hours || same_day) {
    if (int(end / kMinute) == int(begin / kMinute)) {
      return Format("%s, %s", WallTimeFormat("%a, %b %e, %Y", begin), FormatTime(begin));
    } else {
      return Format("%s, %s \u2014 %s", WallTimeFormat("%a, %b %e, %Y", begin),
                    FormatTime(begin), FormatTime(end));
    }
  }
  return Format("%s, %s \u2014 %s, %s",
                WallTimeFormat("%a, %b %e, %Y", begin), FormatTime(begin),
                WallTimeFormat("%a, %b %e, %Y", end), FormatTime(end));
}

string FormatRelativeDate(WallTime d, WallTime now) {
  if (CurrentYear(d) == CurrentYear(now)) {
    return Format("%s", FormatDate("%a, %b %e", d));
  }
  return Format("%s", FormatDate("%b %e, %Y", d));
}

string FormatShortRelativeDate(WallTime d, WallTime now) {
  if (CurrentYear(d) == CurrentYear(now)) {
    return Format("%s", FormatDate("%b %e", d));
  } else {
    return Format("%s", WallTimeFormat("%b %e '%y", d));
  }
}

string FormatDateRange(WallTime begin, WallTime end, WallTime now) {
  bool same_day = fabs(end - begin) < kDay;

  if (same_day) {
    return FormatRelativeDate(end, now);
  }
  return Format("%s \u2014 %s", FormatRelativeDate(begin, now),
                FormatRelativeDate(end, now));
}

void WallTimeSleep(WallTime t) {
  timespec ts;
  ts.tv_sec = static_cast<time_t>(t);
  ts.tv_nsec = (t - ts.tv_sec) * 1e9;
  nanosleep(&ts, NULL);
}

void WallTimeFormat::Print(ostream& os) const {
  const time_t time_sec = static_cast<time_t>(time_);
  struct tm t;
  if (localtime_) {
    localtime_r(&time_sec, &t);
  } else {
    gmtime_r(&time_sec, &t);
  }

  int last = 0;
  for (int i = 0; i < fmt_.size(); ) {
    const int p = fmt_.find('%', i);
    if (p == fmt_.npos) {
      break;
    }
    if (p + 1 < fmt_.size()) {
      if ((fmt_[p + 1] == 'Q') || (fmt_[p + 1] == 'N')) {
        // One of our special formatting characters. Output everything up to the
        // last
        PrintOne(os, t, fmt_, last, p);
        if (fmt_[p + 1] == 'Q') {
          os << Format("%03d") % static_cast<int>(1e3 * (time_ - time_sec));
        } else if (fmt_[p + 1] == 'N') {
          os << Format("%06d") % static_cast<int>(1e6 * (time_ - time_sec));
        }
        i = p + 2;
        last = i;
        continue;
      }
    }
    i = p + 1;
  }

  PrintOne(os, t, fmt_, last, fmt_.size());
}
