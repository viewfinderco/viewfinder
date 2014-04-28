// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifdef TESTING

#import "Testing.h"
#import "TimeRange.h"

namespace {

const WallTime kNow = 1343077044;   // 07/23/12 16:57:24 EST
const WallTime kMinute = 60;
const WallTime kHour = 60 * 60;
const WallTime kDay = 24 * 60 * 60;
const WallTime kMonth = 31 * 24 * 60 * 60;
const WallTime kYear = 365 * 24 * 60 * 60;

class TimeRangeTest : public Test {
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

 private:
  bool tz_set_;
  string orig_tz_;
};

TEST_F(TimeRangeTest, FormatOuterRange) {
  struct {
    float time_scale;
    WallTime start;
    WallTime end;
    bool ascending;
    string exp_str;
  } test[] = {
    { kHour, kNow, kNow, true, "MON, 4 PM" },
    { kHour, kNow - kHour, kNow, true, "MON, 3 PM" },
    { kHour, kNow - kHour, kNow, false, "MON, 3 PM" },
    { kHour, kNow - kHour * 2, kNow, true, "MON, 2PM - 4PM" },
    { kHour, kNow - kHour * 2, kNow, false, "MON, 4PM - 2PM" },
    { kDay, kNow, kNow, true, "MON, JUL 23" },
    { kDay, kNow - kDay, kNow, true, "SUN, JUL 22" },
    { kDay, kNow - kDay, kNow, false, "SUN, JUL 22" },
    { kDay, kNow - kDay * 2, kNow, true, "JUL 21 - JUL 22" },
    { kDay, kNow - kDay * 2, kNow, false, "JUL 22 - JUL 21" },
    { kMonth * 2, kNow, kNow, true, "JULY" },
    { kMonth * 2, kNow - kMonth, kNow, true, "JUNE" },
    { kMonth * 2, kNow - kMonth, kNow, false, "JUNE" },
    { kMonth * 2, kNow - kMonth * 2, kNow, true, "MAY - JUN" },
    { kMonth * 2, kNow - kMonth * 2, kNow, false, "JUN - MAY" },
    { kMonth * 6, kNow, kNow, true, "2012" },
    { kYear, kNow - kYear, kNow, true, "2011" },
    { kYear, kNow - kYear, kNow, false, "2011" },
    { kYear, kNow - kYear * 2, kNow, true, "2010 - 2011" },
    { kYear, kNow - kYear * 2, kNow, false, "2011 - 2010" },
  };
  for (int i = 0; i < ARRAYSIZE(test); ++i) {
    EXPECT_EQ(test[i].exp_str, FormatOuterTimeRange(
                  test[i].time_scale,
                  GetCurrentOuterTime(test[i].time_scale, test[i].start),
                  GetCurrentOuterTime(test[i].time_scale, test[i].end),
                  test[i].ascending));
  }
}

TEST_F(TimeRangeTest, FormatInnerRange) {
  struct {
    float time_scale;
    WallTime start;
    WallTime end;
    bool ascending;
    string exp_str;
  } test[] = {
    { kHour, kNow, kNow, true, "4:45 PM" },
    { kHour, kNow, kNow, false, "4:45 PM" },
    { kHour, kNow - kMinute * 15, kNow, true, "4:30 - 4:45 PM" },
    { kHour, kNow - kMinute * 15, kNow, false, "4:45 - 4:30 PM" },
    { kHour, kNow - kMinute * 15, kNow + kMinute * 15, true, "4:30 PM - 5:00 PM" },
    { kHour, kNow - kMinute * 15, kNow + kMinute * 15, false, "5:00 - 4:30 PM" },
    { kDay, kNow, kNow, true, "4 PM" },
    { kDay, kNow - kHour, kNow, true, "3 PM" },
    { kDay, kNow - kHour, kNow, false, "3 PM" },
    { kDay, kNow - kHour * 2, kNow, true, "2:00 PM - 4PM" },
    { kDay, kNow - kHour * 2, kNow, false, "4:00 PM - 2PM" },
    { kMonth * 2, kNow, kNow, true, "JUL 23" },
    { kMonth * 2, kNow - kDay, kNow, true, "JUL 22" },
    { kMonth * 2, kNow - kDay, kNow, false, "JUL 22" },
    { kMonth * 2, kNow - kDay * 2, kNow, true, "JUL 21 - JUL 22" },
    { kMonth * 2, kNow - kDay * 2, kNow, false, "JUL 22 - JUL 21" },
    { kMonth * 6, kNow, kNow, true, "JUL" },
    { kYear, kNow - kMonth, kNow, true, "JUN" },
    { kYear, kNow - kMonth, kNow, false, "JUN" },
    { kYear, kNow - kMonth * 2, kNow, true, "MAY - JUN" },
    { kYear, kNow - kMonth * 2, kNow, false, "JUN - MAY" },
    { kYear, kNow - kYear, kNow, true, "JUL 2011 - JUN 2012" },
    { kYear, kNow - kYear, kNow, false, "JUN 2012 - JUL 2011" },
  };
  for (int i = 0; i < ARRAYSIZE(test); ++i) {
    EXPECT_EQ(test[i].exp_str, FormatInnerTimeRange(
                  test[i].time_scale,
                  GetCurrentInnerTime(test[i].time_scale, test[i].start),
                  GetCurrentInnerTime(test[i].time_scale, test[i].end),
                  test[i].ascending));
  }
}

TEST_F(TimeRangeTest, CurrentOuterTime) {
  // At hours time scale.
  EXPECT_EQ(CurrentHour(kNow), GetCurrentOuterTime(kHour, kNow));
  EXPECT_EQ(NextHour(kNow), GetCurrentOuterTime(kHour, kNow + 4 * kMinute));
  // At days time scale.
  EXPECT_EQ(CurrentDay(kNow), GetCurrentOuterTime(kDay, kNow));
  EXPECT_EQ(NextDay(kNow), GetCurrentOuterTime(kDay, kNow + kDay));
  // At months time scale.
  EXPECT_EQ(CurrentMonth(kNow), GetCurrentOuterTime(kMonth * 2, kNow));
  EXPECT_EQ(NextMonth(kNow), GetCurrentOuterTime(kMonth * 2, kNow + kMonth));
  // At years time scale.
  EXPECT_EQ(CurrentYear(kNow), GetCurrentOuterTime(kMonth * 4, kNow));
  EXPECT_EQ(NextYear(kNow), GetCurrentOuterTime(kYear, kNow + kYear));
}

TEST_F(TimeRangeTest, CurrentInnerTime) {
  // At hours time scale.
  EXPECT_EQ(CurrentHour(kNow) + kMinute * 15, GetCurrentInnerTime(kHour, kNow - kMinute * 30));
  EXPECT_EQ(CurrentHour(kNow) + kMinute * 45, GetCurrentInnerTime(kHour, kNow));
  EXPECT_EQ(CurrentHour(kNow) + kHour, GetCurrentInnerTime(kHour, kNow + kMinute * 4));
  // At days time scale.
  EXPECT_EQ(CurrentHour(kNow), GetCurrentInnerTime(kDay, kNow));
  EXPECT_EQ(NextHour(kNow), GetCurrentInnerTime(kDay, kNow + 4 * kMinute));
  // At months time scale.
  EXPECT_EQ(CurrentDay(kNow), GetCurrentInnerTime(kMonth * 2, kNow));
  EXPECT_EQ(NextDay(kNow), GetCurrentInnerTime(kMonth * 2, kNow + kDay));
  // At years time scale.
  EXPECT_EQ(CurrentMonth(kNow), GetCurrentInnerTime(kMonth * 4, kNow));
  EXPECT_EQ(NextMonth(kNow), GetCurrentInnerTime(kYear, kNow + kMonth));
}

TEST_F(TimeRangeTest, NextOuterTime) {
  // At hours time scale.
  EXPECT_EQ(NextHour(kNow), GetNextOuterTime(kHour, kNow));
  EXPECT_EQ(NextHour(NextHour(kNow)), GetNextOuterTime(kHour, kNow + 4 * kMinute));
  // At days time scale.
  EXPECT_EQ(NextDay(kNow), GetNextOuterTime(kDay, kNow));
  EXPECT_EQ(NextDay(NextDay(kNow)), GetNextOuterTime(kDay, kNow + kDay));
  // At months time scale.
  EXPECT_EQ(NextMonth(kNow), GetNextOuterTime(kMonth * 2, kNow));
  EXPECT_EQ(NextMonth(NextMonth(kNow)), GetNextOuterTime(kMonth * 2, kNow + kMonth));
  // At years time scale.
  EXPECT_EQ(NextYear(kNow), GetNextOuterTime(kMonth * 4, kNow));
  EXPECT_EQ(NextYear(NextYear(kNow)), GetNextOuterTime(kYear, kNow + kYear));
}

TEST_F(TimeRangeTest, NextInnerTime) {
  // At hours time scale.
  EXPECT_EQ(CurrentHour(kNow) + kMinute * 30, GetNextInnerTime(kHour, kNow - kMinute * 30));
  EXPECT_EQ(NextHour(kNow), GetNextInnerTime(kHour, kNow));
  EXPECT_EQ(NextHour(kNow) + kMinute * 15, GetNextInnerTime(kHour, kNow + kMinute * 4));
  // At days time scale.
  EXPECT_EQ(NextHour(kNow), GetNextInnerTime(kDay, kNow));
  EXPECT_EQ(NextHour(NextHour(kNow)), GetNextInnerTime(kDay, kNow + 4 * kMinute));
  // At months time scale.
  EXPECT_EQ(NextDay(kNow), GetNextInnerTime(kMonth * 2, kNow));
  EXPECT_EQ(NextDay(NextDay(kNow)), GetNextInnerTime(kMonth * 2, kNow + kDay));
  // At years time scale.
  EXPECT_EQ(NextMonth(kNow), GetNextInnerTime(kMonth * 4, kNow));
  EXPECT_EQ(NextMonth(NextMonth(kNow)), GetNextInnerTime(kYear, kNow + kMonth));
}

}  // namespace

#endif  // TESTING
