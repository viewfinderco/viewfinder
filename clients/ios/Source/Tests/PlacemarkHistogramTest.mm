// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifdef TESTING

#import "LocationUtils.h"
#import "PlacemarkHistogram.h"
#import "STLUtils.h"
#import "Testing.h"
#import "TestUtils.h"

namespace {

class PlacemarkHistogramTest : public Test {
 protected:
  PlacemarkHistogramTest()
      : state_(dir()),
        pm_hist_(&state_),
        pm1_(CreatePlacemark("l1", "s1", "c1")),
        pm2_(CreatePlacemark("l2", "s1", "c1")),
        pm3_(CreatePlacemark("l1", "s1", "c2")),
        pm4_(CreatePlacemark("l1", "s2", "c1")),
        loc1_(CreateLocation(40, 40)),
        loc2_(CreateLocation(50, 50)),
        loc3_(CreateLocation(60, 60)),
        loc4_(CreateLocation(70, 70)) {
  }

  Placemark CreatePlacemark(const string& locality,
                            const string& state,
                            const string& country) {
    Placemark pm;
    pm.set_locality(locality);
    pm.set_state(state);
    pm.set_country(country);
    return pm;
  }

  Placemark CreatePlacemark(const string& sublocality,
                            const string& locality,
                            const string& state,
                            const string& country) {
    Placemark pm;
    pm.set_sublocality(sublocality);
    pm.set_locality(locality);
    pm.set_state(state);
    pm.set_country(country);
    return pm;
  }

  Location CreateLocation(double latitude, double longitude) {
    Location loc;
    loc.set_latitude(latitude);
    loc.set_longitude(longitude);
    return loc;
  }

  // Measure the distance from the specified
  void VerifyDistance(const Location& loc, const Placemark& exp_pm,
                      const Location& exp_loc, const bool exp_useful_sublocality) {
    double distance;
    PlacemarkHistogram::TopPlacemark top;
    CHECK(pm_hist_.DistanceToTopPlacemark(loc, &distance, &top));
    CHECK(fabs(distance - DistanceBetweenLocations(loc, exp_loc)) < 1);
    CHECK_EQ(top.placemark.locality(), exp_pm.locality());
    CHECK_EQ(top.placemark.state(), exp_pm.state());
    CHECK_EQ(top.placemark.country(), exp_pm.country());
    CHECK_EQ(top.useful_sublocality, exp_useful_sublocality);
  }

  void AdvanceWallTimeForRefresh() {
    state_.set_now(state_.WallTime_Now() + PlacemarkHistogram::kMinRefreshIntervalSeconds);
  }

 protected:
  TestUIAppState state_;
  PlacemarkHistogram pm_hist_;
  Placemark pm1_;
  Placemark pm2_;
  Placemark pm3_;
  Placemark pm4_;
  Location loc1_;
  Location loc2_;
  Location loc3_;
  Location loc4_;
};

TEST_F(PlacemarkHistogramTest, SortKeys) {
  CHECK_EQ(DBFormat::placemark_histogram_sort_key("test", 0),
           "phs/0000000000/test");
  CHECK_EQ(DBFormat::placemark_histogram_sort_key("test", 1),
           "phs/0000000001/test");
  CHECK_EQ(DBFormat::placemark_histogram_sort_key("test", 0x7fffffff),
           "phs/2147483647/test");
  CHECK_EQ(DBFormat::placemark_histogram_sort_key("test", 0x7ffffffe),
           "phs/2147483646/test");
}

TEST_F(PlacemarkHistogramTest, CanonicalizedPlacenames) {
  DBHandle updates = state_.NewDBTransaction();
  pm_hist_.AddPlacemark(CreatePlacemark("LOCALITY", "STate:name", ":Country:"),
                        loc1_, updates);
  updates->Commit();
  string value;
  CHECK(state_.db()->Get(Slice("phs/2147483646/-country-:state-name:locality"), &value));
  // Sort keys store no values.
  CHECK(value.empty());
}

TEST_F(PlacemarkHistogramTest, Empty) {
  double distance;
  // No top locations; returns false.
  CHECK(!pm_hist_.DistanceToTopPlacemark(loc1_, &distance, NULL));
  // Noop, as nothing there to remove.
  {
    DBHandle updates = state_.NewDBTransaction();
    pm_hist_.RemovePlacemark(pm1_, loc1_, updates);
    pm_hist_.AddPlacemark(pm1_, loc1_, updates);
    updates->Commit();
  }
  AdvanceWallTimeForRefresh();
  CHECK(pm_hist_.DistanceToTopPlacemark(loc1_, &distance, NULL));
  CHECK_EQ(distance, 0);

  // Removes single placemark.
  {
    DBHandle updates = state_.NewDBTransaction();
    pm_hist_.RemovePlacemark(pm1_, loc1_, updates);
    updates->Commit();
  }
  AdvanceWallTimeForRefresh();
  CHECK(!pm_hist_.DistanceToTopPlacemark(loc1_, &distance, NULL));
}

TEST_F(PlacemarkHistogramTest, DistanceToTopLocation) {
  DBHandle updates = state_.NewDBTransaction();
  pm_hist_.AddPlacemark(pm1_, loc1_, updates);
  pm_hist_.AddPlacemark(pm2_, loc2_, updates);
  pm_hist_.AddPlacemark(pm3_, loc3_, updates);
  pm_hist_.AddPlacemark(pm4_, loc4_, updates);
  updates->Commit();
  AdvanceWallTimeForRefresh();

  VerifyDistance(loc1_, pm1_, loc1_, false);
  VerifyDistance(loc2_, pm2_, loc2_, false);
  VerifyDistance(loc3_, pm3_, loc3_, false);
  VerifyDistance(loc4_, pm4_, loc4_, false);
  VerifyDistance(CreateLocation(41, 41), pm1_, loc1_, false);
  VerifyDistance(CreateLocation(51, 51), pm2_, loc2_, false);
  VerifyDistance(CreateLocation(61, 61), pm3_, loc3_, false);
  VerifyDistance(CreateLocation(71, 71), pm4_, loc4_, false);
}

// Verify that only the top percentile of locations are
// matched.
TEST_F(PlacemarkHistogramTest, CullTopLocations) {
  DBHandle updates = state_.NewDBTransaction();
  for (int i = 0; i < 97; i++) {
    pm_hist_.AddPlacemark(pm1_, loc1_, updates);
  }
  pm_hist_.AddPlacemark(pm2_, loc2_, updates);
  pm_hist_.AddPlacemark(pm3_, loc3_, updates);
  pm_hist_.AddPlacemark(pm4_, loc4_, updates);
  updates->Commit();
  AdvanceWallTimeForRefresh();

  VerifyDistance(loc1_, pm1_, loc1_, false);
  VerifyDistance(loc2_, pm1_, loc1_, false);
  VerifyDistance(loc3_, pm1_, loc1_, false);
  VerifyDistance(loc4_, pm1_, loc1_, false);
}

// Verify that sublocalities for a top placemark are considered
// "useful" only if:
// - there are at least three and each is at least 5% of total.
TEST_F(PlacemarkHistogramTest, UsefulSublocalitiesAtLeastThree) {
  Placemark pm1 = CreatePlacemark("sl1", "l1", "s1", "c1");
  Placemark pm2 = CreatePlacemark("sl2", "l1", "s1", "c1");
  Placemark pm3 = CreatePlacemark("sl3", "l1", "s1", "c1");

  // Verify that three sublocalities for a placemark with >= 5% each
  // are sufficient to make sublocalities useful.
  DBHandle updates = state_.NewDBTransaction();
  pm_hist_.AddPlacemark(pm1, loc1_, updates);
  pm_hist_.AddPlacemark(pm2, loc1_, updates);
  pm_hist_.AddPlacemark(pm3, loc1_, updates);
  updates->Commit();
  AdvanceWallTimeForRefresh();
  VerifyDistance(loc1_, pm1, loc1_, true);
}

// Verify sublocalities aren't useful in the event that we have three,
// but not all exceed 5% of total.
TEST_F(PlacemarkHistogramTest, UsefulSublocalitiesAtLeastFivePct) {
  Placemark pm1 = CreatePlacemark("sl1", "l1", "s1", "c1");
  Placemark pm2 = CreatePlacemark("sl2", "l1", "s1", "c1");
  Placemark pm3 = CreatePlacemark("sl3", "l1", "s1", "c1");

  DBHandle updates = state_.NewDBTransaction();
  for (int i = 0; i < 98; ++i) {
    pm_hist_.AddPlacemark(pm1, loc1_, updates);
  }
  pm_hist_.AddPlacemark(pm1, loc1_, updates);
  pm_hist_.AddPlacemark(pm1, loc1_, updates);
  updates->Commit();
  AdvanceWallTimeForRefresh();
  VerifyDistance(loc1_, pm1, loc1_, false);
}

// Verify >= 10 sublocalities makes them useful, even when there are
// < 5% for the top 3.
TEST_F(PlacemarkHistogramTest, UsefulSublocalitiesTenOrMore) {
  Placemark pm1 = CreatePlacemark("sl0", "l1", "s1", "c1");
  DBHandle updates = state_.NewDBTransaction();
  for (int i = 0; i < 90; ++i) {
    pm_hist_.AddPlacemark(pm1, loc1_, updates);
  }
  for (int i = 91; i < 100; ++i) {
    pm_hist_.AddPlacemark(CreatePlacemark(Format("sl%d", i - 90),
                                          "l1", "s1", "c1"), loc1_, updates);
  }
  updates->Commit();
  AdvanceWallTimeForRefresh();
  VerifyDistance(loc1_, pm1, loc1_, true);
}

// Verify that sort order works properly.
TEST_F(PlacemarkHistogramTest, SortKeyZeroPadding) {
  // Count will be 100, which would sort less than
  // 2 for loc_2_ below without 0 padding in sort key.
  DBHandle updates = state_.NewDBTransaction();
  for (int i = 0; i < 100; i++) {
    pm_hist_.AddPlacemark(pm1_, loc1_, updates);
  }
  for (int i = 0; i < 2; i++) {
    pm_hist_.AddPlacemark(pm2_, loc2_, updates);
  }
  updates->Commit();
  AdvanceWallTimeForRefresh();

  VerifyDistance(loc1_, pm1_, loc1_, false);
  VerifyDistance(loc2_, pm1_, loc1_, false);
}

// Verify that adding updates the centroid and removing
// also updates the centroid.
TEST_F(PlacemarkHistogramTest, LocationCentroid) {
  // Add two different locations.
  {
    DBHandle updates = state_.NewDBTransaction();
    pm_hist_.AddPlacemark(pm1_, CreateLocation(50, 50), updates);
    pm_hist_.AddPlacemark(pm1_, CreateLocation(51, 51), updates);
    updates->Commit();
  }

  // Verify they've been averaged.
  double distance;
  PlacemarkHistogram::TopPlacemark top;
  CHECK(pm_hist_.DistanceToTopPlacemark(CreateLocation(50, 50), &distance, &top));
  CHECK_EQ(top.centroid.latitude(), 50.5);
  CHECK_EQ(top.centroid.longitude(), 50.5);

  // Now, remove the 50, 50 and verify new centroid is 51, 51.
  {
    DBHandle updates = state_.NewDBTransaction();
    pm_hist_.RemovePlacemark(pm1_, CreateLocation(50, 50), updates);
    updates->Commit();
  }
  AdvanceWallTimeForRefresh();
  CHECK(pm_hist_.DistanceToTopPlacemark(CreateLocation(50, 50), &distance, &top));
  CHECK_EQ(top.centroid.latitude(), 51);
  CHECK_EQ(top.centroid.longitude(), 51);
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
