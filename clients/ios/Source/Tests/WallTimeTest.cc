// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "Exif.h"
#import "Testing.h"
#import "WallTime.h"

namespace {

const WallTime kNow = 1343077044;   // 07/23/12 16:57:24 EST
const WallTime kMinute = 60;
const WallTime kHour = 60 * 60;
const WallTime kDay = 24 * 60 * 60;
const WallTime kMonth = 30 * 24 * 60 * 60;
const WallTime kYear = 365 * 24 * 60 * 60;

class WallTimeTest : public Test {
 public:
  virtual void SetUp() {
    if (getenv("TZ")) {
      tz_set_ = true;
      orig_tz_ = getenv("TZ");
    } else {
      tz_set_ = false;
    }
  }
  virtual void TearDown() {
    if (tz_set_) {
      setenv("TZ", orig_tz_.c_str(), 1);
    } else {
      unsetenv("TZ");
    }
    tzset();
  }

  void SetTimeZone(const char *tz) {
    setenv("TZ", tz, 1);
    tzset();
  }

 protected:
  bool tz_set_;
  string orig_tz_;
};

TEST_F(WallTimeTest, Format) {
  EXPECT_EQ("hello", ToString(WallTimeFormat("hello", 0)));
  EXPECT_EQ("1970-01-01", ToString(WallTimeFormat("%F", 0, false)));
  EXPECT_EQ("00:00:00", ToString(WallTimeFormat("%T", 0, false)));
  EXPECT_EQ("123", ToString(WallTimeFormat("%Q", 0.123456, false)));
  EXPECT_EQ("123456", ToString(WallTimeFormat("%N", 0.123456, false)));
  EXPECT_EQ("1970-01-01.123.00:00:00.123456",
            ToString(WallTimeFormat("%F.%Q.%T.%N", 0.123456, false)));
}

TEST_F(WallTimeTest, FormatRelativeTime) {
  SetTimeZone("America/New_York");
  struct {
    WallTime now;
    WallTime time;
    string expected;
  } kTestData[] = {
    { kNow, kNow, "4:57p" },
    { kNow, kNow - kHour, "3:57p" },
    { kNow, kNow - 6 * kHour, "10:57a" },
    { kNow, kNow - kDay, "Sun, 4:57p" },
    { kNow, kNow - 6 * kDay, "Tue, 4:57p" },
    { kNow, kNow - kMonth, "Jun 23, 4:57p" },
    { kNow, kNow - kYear, "Jul 24, 2011, 4:57p" },
  };
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    const string s = FormatRelativeTime(kTestData[i].time, kTestData[i].now);
    EXPECT_EQ(kTestData[i].expected, s);
  }

  SetTimeZone("US/Pacific");
  const string s = FormatRelativeTime(kNow, kNow);
  EXPECT_EQ("1:57p", s);
  struct tm t = LocalTime(kNow);
  EXPECT_EQ("PDT", string(t.tm_zone));
}

TEST_F(WallTimeTest, FormatTimeAgo) {
  SetTimeZone("America/New_York");
  struct {
    WallTime ago;
    string expected;
    string medium_expected;
    string long_expected;
  } kTestData[] = {
    { kNow, "now", "just now", "just now" },
    { kNow + 1, "now", "just now", "just now" },
    { kNow + 100, "now", "just now", "just now" },
    { kNow - 1, "1s", "1s ago", "1 second ago" },
    { kNow - 59.99, "60s", "60s ago", "60 seconds ago" },  // rounds up
    { kNow - 60, "1m", "1m ago", "1 minute ago" },
    { kNow - 61, "1m", "1m ago", "1 minute ago" },
    { kNow - 89.9, "1m", "1m ago", "1 minute ago" },  // rounds down
    { kNow - 90, "2m", "2m ago", "2 minutes ago" },  // rounds up
    { kNow - 120, "2m", "2m ago", "2 minutes ago" },
    { kNow - 60 * 59, "59m", "59m ago", "59 minutes ago" },
    { kNow - 60 * 61, "1h", "1h ago", "1 hour ago" },
    { kNow - 60 * 89, "1h", "1h ago", "1 hour ago" },  // rounds down
    { kNow - 60 * 90, "2h", "2h ago", "2 hours ago" },  // rounds up
    { kNow - 60 * 60 * 23, "23h", "23h ago", "23 hours ago" },
    { kNow - 60 * 60 * 23.5, "24h", "24h ago", "24 hours ago" },
    { kNow - 60 * 60 * 24, "1d", "1d ago", "1 day ago" },
    { kNow - 60 * 60 * 35, "1d", "1d ago", "1 day ago" },  // rounds down
    { kNow - 60 * 60 * 36, "2d", "2d ago", "2 days ago" },  // rounds up
    { kNow - 60 * 60 * 24 * 6.9, "7d", "7d ago", "7 days ago" },
    { kNow - 60 * 60 * 24 * 8, "Jul 15", "on Jul 15", "on Jul 15" },
    { kNow - 60 * 60 * 24 * 22, "Jul 1", "on Jul 1", "on Jul 1" },
    { kNow - 60 * 60 * 24 * 27, "Jun 26", "on Jun 26", "on Jun 26" },
    { kNow - kMonth, "Jun 23", "on Jun 23", "on Jun 23" },
    { kNow - kYear, "Jul 24, 2011", "on Jul 24, 2011", "on Jul 24, 2011" },
  };
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    EXPECT_EQ(kTestData[i].expected, FormatTimeAgo(kTestData[i].ago, kNow, TIME_AGO_SHORT));
    EXPECT_EQ(kTestData[i].medium_expected, FormatTimeAgo(kTestData[i].ago, kNow, TIME_AGO_MEDIUM));
    EXPECT_EQ(kTestData[i].long_expected, FormatTimeAgo(kTestData[i].ago, kNow, TIME_AGO_LONG));
  }
}

TEST_F(WallTimeTest, FormatRelativeDate) {
  struct {
    WallTime time;
    string expected;
  } kTestData[] = {
    { kNow, "Mon, Jul 23" },
    { kNow - kDay * 5, "Wed, Jul 18" },
    { kNow - kMonth - kDay, "Fri, Jun 22" },
    { kNow - kDay * 20, "Tue, Jul 3" },
    { kNow - kYear, "Jul 24, 2011" },
  };
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    const string s = FormatRelativeDate(kTestData[i].time, kNow);
    EXPECT_EQ(kTestData[i].expected, s);
  }
}

TEST_F(WallTimeTest, FormatShortRelativeDate) {
  struct {
    WallTime time;
    string expected;
  } kTestData[] = {
    { kNow, "Jul 23" },
    { kNow - kDay * 5, "Jul 18" },
    { kNow - kMonth - kDay, "Jun 22" },
    { kNow - kYear, "Jul 24 '11" },
  };
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    const string s = FormatShortRelativeDate(kTestData[i].time, kNow);
    EXPECT_EQ(kTestData[i].expected, s);
  }
}

TEST_F(WallTimeTest, FormatTimeRange) {
  struct {
    WallTime begin;
    WallTime end;
    string expected;
  } kTestData[] = {
    { kNow, kNow, "Mon, Jul 23, 2012, 4:57p" },
    { kNow - 1, kNow, "Mon, Jul 23, 2012, 4:57p" },
    { kNow - 60, kNow, "Mon, Jul 23, 2012, 4:56p \u2014 4:57p" },
    { kNow - kHour * 16, kNow, "Mon, Jul 23, 2012, 12:57a \u2014 4:57p" },
    { kNow, kNow + kHour, "Mon, Jul 23, 2012, 4:57p \u2014 5:57p" },
    { kNow, kNow + kHour * 8, "Mon, Jul 23, 2012, 4:57p \u2014 12:57a" },
    { kNow, kNow + kHour * 12, "Mon, Jul 23, 2012, 4:57p \u2014 Tue, Jul 24, 2012, 4:57a" },
    { kNow, kNow + kDay * 2, "Mon, Jul 23, 2012, 4:57p \u2014 Wed, Jul 25, 2012, 4:57p" },
  };
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    const string s = FormatTimeRange(
        kTestData[i].begin, kTestData[i].end);
    EXPECT_EQ(kTestData[i].expected, s);
  }
}

TEST_F(WallTimeTest, FormatDateRange) {
  struct {
    WallTime begin;
    WallTime end;
    string expected;
  } kTestData[] = {
    { kNow, kNow, "Mon, Jul 23" },
    { kNow - 1, kNow, "Mon, Jul 23" },
    { kNow - 60, kNow, "Mon, Jul 23" },
    { kNow - 6 * kHour, kNow, "Mon, Jul 23" },
    { kNow - kDay, kNow, "Sun, Jul 22 \u2014 Mon, Jul 23" },
    { kNow - kDay, kNow - kDay, "Sun, Jul 22" },
    { kNow - kDay - 60, kNow - kDay, "Sun, Jul 22" },
    { kNow - kMonth, kNow, "Sat, Jun 23 \u2014 Mon, Jul 23" },
    { kNow - kYear, kNow, "Jul 24, 2011 \u2014 Mon, Jul 23" },
    { kNow - kYear, kNow - kMonth, "Jul 24, 2011 \u2014 Sat, Jun 23" },
  };
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    const string s = FormatDateRange(
        kTestData[i].begin, kTestData[i].end, kNow);
    EXPECT_EQ(kTestData[i].expected, s);
  }
}

TEST_F(WallTimeTest, ParseExifDate) {
  SetTimeZone("GMT");
  EXPECT_EQ(-1, ParseExifDate("1969:12:31 23:59:59"));
  EXPECT_EQ(-60, ParseExifDate("1969:12:31 23:59:00"));
  EXPECT_EQ(-86401, ParseExifDate("1969:12:30 23:59:59"));

  // Verify proper handling of daylight savings time.
  SetTimeZone("EST");
  // A date that is in daylight savings.
  EXPECT_EQ("2012-10-10 16:04:13",
            ToString(WallTimeFormat("%F %T", ParseExifDate("2012:10:10 16:04:13"))));
  // A date that is not in daylight savings.
  EXPECT_EQ("2012-11-10 16:04:13",
            ToString(WallTimeFormat("%F %T", ParseExifDate("2012:11:10 16:04:13"))));
}

}  // namespace

#endif  // TESTING
