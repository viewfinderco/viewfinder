// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "PlacemarkTable.h"
#import "StringUtils.h"
#import "Testing.h"
#import "TestUtils.h"

namespace {

class PlacemarkTableTest : public Test {
 public:
  PlacemarkTableTest()
      : state_(dir()) {
  }

  PlacemarkHandle FindPlacemark(double lat, double lng) {
    Location location;
    location.set_latitude(lat);
    location.set_longitude(lng);
    return state_.placemark_table()->FindPlacemark(location, state_.db());
  }

  void SavePlacemark(const PlacemarkHandle& h) {
    DBHandle updates = state_.NewDBTransaction();
    h->SaveAndUnlock(updates);
    updates->Commit();
  }

  string ListPlacemarks() {
    vector<string> v;
    for (DB::PrefixIterator iter(state_.db(), DBFormat::placemark_key(""));
         iter.Valid();
         iter.Next()) {
      const Slice value = iter.value();
      Placemark p;
      CHECK(p.ParseFromArray(value.data(), value.size()));
      v.push_back(p.state());
    }
    std::sort(v.begin(), v.end());
    return Join(v, ",");
  }

  int referenced_placemarks() const {
    return state_.placemark_table()->referenced_placemarks();
  }

 protected:
  TestUIAppState state_;
};

TEST_F(PlacemarkTableTest, Basic) {
  ASSERT_EQ(0, referenced_placemarks());
  // Create a new placemark.
  PlacemarkHandle a = FindPlacemark(0, 1);
  ASSERT_EQ(1, referenced_placemarks());
  // Verify it is invalid.
  ASSERT(!a->valid());
  // Verify a subsequent retrieval returns the same pointer.
  ASSERT_EQ(a.get(), FindPlacemark(0, 1).get());
  ASSERT_EQ(1, referenced_placemarks());
  // Create another placemark.
  PlacemarkHandle b = FindPlacemark(2, 3);
  ASSERT_EQ(2, referenced_placemarks());
  ASSERT_EQ(b.get(), FindPlacemark(2, 3).get());
  b.reset();
  ASSERT_EQ(1, referenced_placemarks());
  // Verify we can save the first placemark and retrieve it.
  a->Lock();
  a->set_state("nowhere");
  SavePlacemark(a);
  ASSERT(a->valid());
  ASSERT_EQ("nowhere", ListPlacemarks());
  a.reset();
  ASSERT_EQ(0, referenced_placemarks());
  a = FindPlacemark(0, 1);
  ASSERT_EQ(1, referenced_placemarks());
  ASSERT(a->valid());
  ASSERT_EQ("nowhere", a->state());
  // Save the second placemark and verify the placemark table now has 2
  // entries.
  b = FindPlacemark(2, 3);
  ASSERT_EQ(2, referenced_placemarks());
  b->Lock();
  b->set_state("somewhere");
  SavePlacemark(b);
  ASSERT(b->valid());
  ASSERT_EQ("nowhere,somewhere", ListPlacemarks());
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
