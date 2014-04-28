// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifdef TESTING

#import "AsyncState.h"
#import "DayTable.h"
#import "StringUtils.h"
#import "TestUtils.h"

namespace {

const int64_t kUserId = 1;
const int64_t kDeviceId = 1;
const WallTime kTimestamp = 1347382011;  // 2012-09-11 12:46:51.000

Placemark MakePlacemark(const string& iso_country_code,
                        const string& country,
                        const string& state,
                        const string& locality,
                        const string& sublocality,
                        const string& thoroughfare,
                        const string& subthoroughfare) {
  Placemark pm;
  pm.set_iso_country_code(iso_country_code);
  pm.set_country(country);
  pm.set_state(state);
  pm.set_locality(locality);
  pm.set_sublocality(sublocality);
  pm.set_thoroughfare(thoroughfare);
  pm.set_subthoroughfare(subthoroughfare);
  return pm;
}

Location MakeLocation(double latitude, double longitude) {
  Location loc;
  loc.set_latitude(latitude);
  loc.set_longitude(longitude);
  return loc;
}

typedef std::pair<int64_t, int64_t> P;

class DayTableTest : public BaseContentTest {
 public:
  DayTableTest()
      : BaseContentTest() {
    state_.SetDeviceId(kDeviceId);
    state_.SetUserId(kUserId);
    state_.set_now(kTimestamp);
  }

  DayTable* day_table() const { return state_.day_table(); }
  DayTable::SnapshotHandle snapshot() const { return snapshot_; }

  // Update to latest snapshot. Returns latest epoch.
  int UpdateSnapshot() {
    int epoch;
    snapshot_ = state_.day_table()->GetSnapshot(&epoch);
    return epoch;
  }

  // Loads event using kUserId and kDeviceId.
  EventHandle LoadEvent(
      WallTime timestamp, int index, int64_t user_id, int64_t device_id) {
    state_.SetUserId(user_id);
    state_.SetDeviceId(device_id);
    return snapshot_->LoadEvent(timestamp, index);
  }

  // Loads trapdoor using kUserId and kDeviceId.
  TrapdoorHandle LoadTrapdoor(
      int64_t viewpoint_id, int64_t user_id, int64_t device_id) {
    state_.SetUserId(user_id);
    state_.SetDeviceId(device_id);
    return snapshot_->LoadTrapdoor(viewpoint_id);
  }

  void InvalidateActivity(const ActivityHandle& ah) {
    DBHandle updates = state_.NewDBTransaction();
    state_.day_table()->InvalidateActivity(ah, updates);
    updates->Commit();
  }

  void InvalidateDay(WallTime timestamp) {
    DBHandle updates = state_.NewDBTransaction();
    state_.day_table()->InvalidateDay(timestamp, updates);
    updates->Commit();
  }

  void InvalidateEpisode(const EpisodeHandle& eh) {
    DBHandle updates = state_.NewDBTransaction();
    state_.day_table()->InvalidateEpisode(eh, updates);
    updates->Commit();
  }

  void AssignActivityUpdateSequenceNos(int64_t viewpoint_id) {
    ScopedPtr<ActivityTable::ActivityIterator> iter(
        state_.activity_table()->NewViewpointActivityIterator(
            viewpoint_id, 0, false, state_.db()));
    int update_seq = 1;
    for (; !iter->done(); iter->Next()) {
      ActivityHandle ah = iter->GetActivity();
      DBHandle updates = state_.NewDBTransaction();
      ah->Lock();
      ah->set_update_seq(update_seq++);
      ah->SaveAndUnlock(updates);
      updates->Commit();
    }
  }

 protected:
  void SetViewfinderLoc() {
    SetLocation(kViewfinderLoc, kViewfinder);
  }

  void SetSohoHouseLoc() {
    SetLocation(kSohoHouseLoc, kSohoHouse);
  }

  void SetKimballEastLoc() {
    SetLocation(kKimballEastLoc, kKimballEast);
  }

  void SetSurfLodgeLoc() {
    SetLocation(kSurfLodgeLoc, kSurfLodge);
  }

 protected:
  DayTable::SnapshotHandle snapshot_;

  static const double kDayDelta;

  static const Location kViewfinderLoc;
  static const Location kSohoHouseLoc;
  static const Location kKimballEastLoc;
  static const Location kSurfLodgeLoc;

  static const Placemark kViewfinder;
  static const Placemark kSohoHouse;
  static const Placemark kKimballEast;
  static const Placemark kSurfLodge;
};

const double DayTableTest::kDayDelta = 60 * 60 * 24;

const Location DayTableTest::kViewfinderLoc = MakeLocation(40.720169, -73.998756);
const Location DayTableTest::kSohoHouseLoc = MakeLocation(40.740616, -74.005880);
const Location DayTableTest::kKimballEastLoc = MakeLocation(41.034184, -72.210603);
const Location DayTableTest::kSurfLodgeLoc = MakeLocation(41.044048, -71.950622);

const Placemark DayTableTest::kViewfinder =
    MakePlacemark("US", "United States", "NY", "New York City", "SoHo", "Grand St", "154");
const Placemark DayTableTest::kSohoHouse =
    MakePlacemark("US", "United States", "NY", "New York City", "Meatpacking District", "9th Avenue", "29-35");
const Placemark DayTableTest::kKimballEast =
    MakePlacemark("US", "United States", "NY", "East Hampton", "Northwest Harbor", "Milina", "35");
const Placemark DayTableTest::kSurfLodge =
    MakePlacemark("US", "United States", "NY", "Montauk", "", "Edgemere St", "183");


// Test day table with no content.
TEST_F(DayTableTest, NoContent) {
  UpdateSnapshot();
  // An empty day.
  EventHandle evh = LoadEvent(kTimestamp, 0, kUserId, kDeviceId);
  EXPECT(!evh.get());
  TrapdoorHandle trh = LoadTrapdoor(0, kUserId, kDeviceId);
  EXPECT(!trh.get());
}

// Test timestamp canonicalization.
TEST_F(DayTableTest, TimestampCanonicalization) {
  EXPECT_EQ(CanonicalizeTimestamp(kTimestamp),
            CanonicalizeTimestamp(kTimestamp + 1));
  EXPECT_EQ(CanonicalizeTimestamp(kTimestamp),
            CanonicalizeTimestamp(kTimestamp + 60));
  EXPECT_EQ(CanonicalizeTimestamp(kTimestamp) + 60 * 60 * 24,
            CanonicalizeTimestamp(kTimestamp + 60 * 60 * 24));
  EXPECT_EQ(CanonicalizeTimestamp(kTimestamp),
            CanonicalizeTimestamp(kTimestamp + 60 * 60 * 12));
}

// Test a single episode in a day with 1 photo.
TEST_F(DayTableTest, OneEpisode) {
  /*
  EpisodeHandle eh = NewEpisode(1);
  vector<int64_t> photo_ids;
  eh->ListPhotos(&photo_ids);

  DayHandle dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  ASSERT(dh.get());
  EXPECT_EQ(1, dh->events().size());
  EXPECT_EQ(kTimestamp, dh->events()[0].earliest_timestamp());
  EXPECT_EQ(kTimestamp, dh->events()[0].latest_timestamp());
  EXPECT_EQ(1, dh->events()[0].photo_count());
  EXPECT_EQ(1, dh->events()[0].photos_size());
  EXPECT_EQ(photo_ids[0], dh->events()[0].photos(0).photo_id());
  EXPECT_EQ(eh->id().local_id(), dh->events()[0].episodes(0).episode_id());
  EXPECT_EQ(1, dh->events()[0].episodes_size());
  // The user himself is not listed as an event contributor; it's assumed.
  EXPECT_EQ(0, dh->events()[0].contributors_size());
  EXPECT(!dh->events()[0].has_location());
  EXPECT(!dh->events()[0].has_placemark());
  EXPECT(!dh->events()[0].has_distance());
  EXPECT_EQ(0, dh->trapdoors().size());
  EXPECT_EQ("1 photo on", dh->events()[0].FormatEventViewTitle());
  EXPECT_EQ("Tuesday, September 11, 2012", dh->events()[0].FormatEventViewTimestamp());
  */
}

// Test a multiple episodes with multiple photos.
TEST_F(DayTableTest, MultipleEpisodes) {
  /*
  EpisodeHandle eh1 = NewEpisode(2);
  EpisodeHandle eh2 = NewEpisode(2);

  // Day will combine both episodes into a single group (both have no location).
  DayHandle dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  ASSERT(dh.get());
  EXPECT_EQ(1, dh->events().size());
  EXPECT_EQ(kTimestamp, dh->events()[0].earliest_timestamp());
  EXPECT_EQ(kTimestamp + 1, dh->events()[0].latest_timestamp());
  EXPECT_EQ(4, dh->events()[0].photo_count());
  // Sample will be between 1 and 4 photos.
  EXPECT_GE(dh->events()[0].photos_size(), 1);
  EXPECT_LE(dh->events()[0].photos_size(), 4);
  EXPECT_EQ("4 photos on", dh->events()[0].FormatEventViewTitle());
  */
}

// Test a single activity in a day by sharing an episode to two users.
TEST_F(DayTableTest, ShareEpisode) {
  /*
  AddContact("a", 10, "Spencer", "Spencer Kimball");
  AddContact("b", 20, "Brian", "Brian McGinnis");
  ASSERT_EQ(1, NewEpisode(1)->id().local_id());
  ViewpointHandle vh = ShareNew(kDeviceId, kUserId, kTimestamp,
                                L(P(2, 1)), L(10, 20));

  DayHandle dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  ASSERT(dh.get());
  EXPECT_EQ(1, dh->events().size());
  ASSERT_EQ(1, dh->trapdoors().size());
  std::unordered_set<string> first_names;
  std::unordered_set<string> full_names;
  for (int i = 0; i < 3; ++i) {
    first_names.insert(dh->trapdoors()[0].contributors(i).first_name());
    full_names.insert(dh->trapdoors()[0].contributors(i).full_name());
  }
  EXPECT(ContainsKey(first_names, "You"));
  EXPECT(ContainsKey(first_names, "Brian"));
  EXPECT(ContainsKey(first_names, "Spencer"));
  EXPECT(ContainsKey(full_names, "You"));
  EXPECT(ContainsKey(full_names, "Brian McGinnis"));
  EXPECT(ContainsKey(full_names, "Spencer Kimball"));
  */
}

// Test a single activity in a day adding followers.
TEST_F(DayTableTest, AddFollowers) {
  /*
  AddContact("a", 10, "Spencer", "Spencer Kimball");
  ViewpointHandle vh = NewViewpoint();
  // Add three contacts: one with user_id, one with first name, one with
  // full name. The latest activity should blend what's available.
  vector<ContactMetadata> contacts(3);
  contacts[0].set_user_id(10);
  contacts[1].set_first_name("Brian");
  contacts[2].set_name("Peter Mattis");
  vh = viewpoint_table()->AddFollowers(vh->id().local_id(), contacts);

  // There will be no trapdoor because the viewpoint has
  // no photos or comments (this shouldn't happen in practice).
  DayHandle dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  ASSERT(dh.get());
  EXPECT_EQ(0, dh->events().size());
  EXPECT_EQ(0, dh->trapdoors().size());

  // Add an older comment to provide content.
  PostComment(kDeviceId, kUserId, kTimestamp - kDayDelta * 2, vh->id().local_id(), "hello");
  InvalidateDay(kTimestamp);  // invalidate so we can see user 2's view
  dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  ASSERT_EQ(1, dh->trapdoors().size());
  // Only kUserId and "Spencer" are listed as contributors, as only
  // those users have ids.
  EXPECT_EQ(2, dh->trapdoors()[0].contributors_size());
  */
}

// Test a single activity in a day by posting a comment.
TEST_F(DayTableTest, PostComment) {
  /*
  // Post a comment.
  ViewpointHandle vh = NewViewpoint();
  PostComment(kDeviceId, kUserId, kTimestamp, vh->id().local_id(), "hello");

  DayHandle dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  ASSERT(dh.get());
  EXPECT_EQ(0, dh->events().size());
  EXPECT_EQ(1, dh->trapdoors().size());
  EXPECT_EQ(vh->id().local_id(), dh->trapdoors()[0].viewpoint_id());
  EXPECT_EQ(kTimestamp, dh->trapdoors()[0].earliest_timestamp());
  EXPECT_EQ(kTimestamp, dh->trapdoors()[0].latest_timestamp());
  EXPECT_EQ("You", dh->trapdoors()[0].contributors(0).first_name());
  EXPECT_EQ("You", dh->trapdoors()[0].contributors(0).full_name());
  EXPECT_EQ(0, dh->trapdoors()[0].photos_size());
  EXPECT_EQ(0, dh->trapdoors()[0].photo_count());
  EXPECT_EQ(1, dh->trapdoors()[0].comment_count());
  */
}

// Verify that successive activities invalidate days.
TEST_F(DayTableTest, ActivityInvalidatesDay) {
  /*
  // Post a comment.
  ViewpointHandle vh = NewViewpoint();
  PostComment(kDeviceId, kUserId, kTimestamp, vh->id().local_id(), "hello");

  DayHandle dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  ASSERT(dh.get());
  EXPECT_EQ(0, dh->events().size());
  EXPECT_EQ(1, dh->trapdoors().size());
  EXPECT_EQ(vh->id().local_id(), dh->trapdoors()[0].viewpoint_id());

  // 2nd comment should invalidate.
  PostComment(kDeviceId, kUserId, kTimestamp + 1, vh->id().local_id(), "world");

  dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  EXPECT_EQ(0, dh->events().size());
  EXPECT_EQ(1, dh->trapdoors().size());
  EXPECT_EQ(vh->id().local_id(), dh->trapdoors()[0].viewpoint_id());
  EXPECT_EQ(2, dh->trapdoors()[0].comment_count());
  */
}

// Test multiple activities in a day using a share and a comment to
// the same viewpoint.
TEST_F(DayTableTest, MultipleActivities) {
  /*
  AddContact("a", 10, "Spencer", "Spencer Kimball");
  ASSERT_EQ(1, NewEpisode(2)->id().local_id());
  ViewpointHandle vh = ShareNew(kDeviceId, 10, kTimestamp, L(P(2, 1), P(3, 1)), L(kUserId));
  PostComment(kDeviceId, kUserId, kTimestamp, vh->id().local_id(), "hello world");

  DayHandle dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  ASSERT(dh.get());
  EXPECT_EQ(1, dh->events().size());
  ASSERT_EQ(1, dh->trapdoors().size());
  EXPECT_EQ(vh->id().local_id(), dh->trapdoors()[0].viewpoint_id());
  EXPECT_EQ(2, dh->trapdoors()[0].contributors_size());
  EXPECT_GE(dh->trapdoors()[0].photos_size(), 1);
  EXPECT_EQ(2, dh->trapdoors()[0].photo_count());
  */
}

// Test multiple conversations in a day.
TEST_F(DayTableTest, MultipleViewpoints) {
  /*
  ASSERT_EQ(1, NewEpisode(2)->id().local_id());
  // The two shares combine into a single episode.
  ViewpointHandle vh1 = ShareNew(kDeviceId, kUserId, kTimestamp, L(P(2, 1)), L(10));
  ViewpointHandle vh2 = ShareNew(kDeviceId, kUserId, kTimestamp + 1, L(P(3, 1)), L(10));

  DayHandle dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  ASSERT(dh.get());
  EXPECT_EQ(1, dh->events().size());
  EXPECT_EQ(2, dh->trapdoors().size());
  EXPECT_EQ(vh1->id().local_id(), dh->trapdoors()[0].viewpoint_id());
  EXPECT_EQ(vh2->id().local_id(), dh->trapdoors()[1].viewpoint_id());
  */
}

// Test a share to contacts without user id.
TEST_F(DayTableTest, ShareToUnresolvedContacts) {
  /*
  ASSERT_EQ(1, NewEpisode(1)->id().local_id());
  vector<ContactMetadata> contacts(2);
  contacts[0].set_first_name("Brian");
  contacts[1].set_first_name("Brett");
  ViewpointHandle vh = viewpoint_table()->ShareNew(L(P(2, 1)), contacts);

  DayHandle dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  ASSERT(dh.get());
  EXPECT_EQ(1, dh->events().size());
  ASSERT_EQ(1, dh->trapdoors().size());
  EXPECT_EQ(1, dh->trapdoors()[0].contributors_size());
  EXPECT_EQ("You", dh->trapdoors()[0].contributors(0).full_name());
  */
}

// Test that episodes with disparate locations and no locations are
// split into separate events.
TEST_F(DayTableTest, Events) {
  /*
  const int kDeviceId2 = 2;
  const int kUserId2 = 2;
  AddContact("a", kUserId2, "Spencer", "Spencer Kimball");

  // Create first episode with no location.
  state_.set_now(kTimestamp + 30);  // create successive timestamp in reverse order
  EpisodeHandle eh1 = NewEpisode(1);  // photo id 2

  SetViewfinderLoc();
  state_.set_now(kTimestamp + 25);
  EpisodeHandle eh2 = NewEpisode(2); // overweight viewfinder (ids 4 & 5)

  SetSohoHouseLoc();
  state_.set_now(kTimestamp + 20);
  EpisodeHandle eh3 = NewEpisode(1); // underweight soho house (id 7)

  SetKimballEastLoc();
  state_.set_now(kTimestamp + 15);
  EpisodeHandle eh4 = NewEpisode(1); // underweight kimball east (id 9)

  SetSurfLodgeLoc();
  state_.set_now(kTimestamp + 10);
  EpisodeHandle eh5 = NewEpisode(2); // overweight surf lodge (ids 11 & 12)

  // Day will combine episodes into three groups. The first centered
  // around Manhattan (but with viewfinder as location as 2 photos
  // were from viewfinder vs. one from soho house). The second in
  // Long Island but located at Surf Lodge. The third is unaffiliated.
  DayHandle dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  ASSERT(dh.get());
  EXPECT_EQ(3, dh->events().size());
  // Group 1.
  EXPECT_EQ(kTimestamp + 10, dh->events()[0].earliest_timestamp());
  EXPECT_EQ(kTimestamp + 15, dh->events()[0].latest_timestamp());
  EXPECT_EQ(3, dh->events()[0].photo_count());
  EXPECT_EQ(2, dh->events()[0].episodes_size());
  EXPECT_EQ(10, dh->events()[0].episodes(0).episode_id());
  EXPECT_EQ(8, dh->events()[0].episodes(1).episode_id());
  EXPECT_EQ(0, dh->events()[0].contributors_size());
  EXPECT_EQ("Montauk", dh->events()[0].placemark().locality());
  EXPECT_EQ("MONTAUK, NY", dh->events()[0].FormatTitle(false));
  EXPECT_EQ("MONTAUK, NY", dh->events()[0].FormatTitle(true));
  EXPECT_EQ("3 photos on", dh->events()[0].FormatEventViewTitle());
  // Group 2.
  EXPECT_EQ(kTimestamp + 20, dh->events()[1].earliest_timestamp());
  EXPECT_EQ(kTimestamp + 26, dh->events()[1].latest_timestamp());
  EXPECT_EQ(3, dh->events()[1].photo_count());
  ASSERT_EQ(2, dh->events()[1].episodes_size());
  EXPECT_EQ(6, dh->events()[1].episodes(0).episode_id());
  EXPECT_EQ(3, dh->events()[1].episodes(1).episode_id());
  EXPECT_EQ(0, dh->events()[1].contributors_size());
  EXPECT_EQ("SoHo", dh->events()[1].placemark().sublocality());
  EXPECT_EQ("SOHO, NEW YORK CITY", dh->events()[1].FormatTitle(false));
  EXPECT_EQ("SOHO, NYC", dh->events()[1].FormatTitle(true));
  EXPECT_EQ("3 photos on", dh->events()[1].FormatEventViewTitle());
  // Group 3.
  EXPECT_EQ(kTimestamp + 30, dh->events()[2].earliest_timestamp());
  EXPECT_EQ(kTimestamp + 30, dh->events()[2].latest_timestamp());
  EXPECT_EQ(1, dh->events()[2].photo_count());
  EXPECT_EQ(1, dh->events()[2].episodes_size());
  EXPECT_EQ(1, dh->events()[2].episodes(0).episode_id());
  EXPECT_EQ(0, dh->events()[2].contributors_size());
  EXPECT(!dh->events()[2].has_placemark());
  EXPECT_EQ("1 photo on", dh->events()[2].FormatEventViewTitle());

  // Also, share all episodes into a single viewpoint to verify that
  // disparate locations still blend into a single trapdoor.
  ViewpointHandle vh = ShareNew(kDeviceId2, kUserId2,
                                kTimestamp + 100, L(P(2, 1)), L(1));
  ShareExisting(kDeviceId2, kUserId2, kTimestamp + 101,
                vh->id().local_id(), L(P(4, 3), P(5, 3)));
  ShareExisting(kDeviceId2, kUserId2, kTimestamp + 102,
                vh->id().local_id(), L(P(7, 6)));
  ShareExisting(kDeviceId2, kUserId2, kTimestamp + 103,
                vh->id().local_id(), L(P(9, 8)));
  ShareExisting(kDeviceId2, kUserId2, kTimestamp + 104,
                vh->id().local_id(), L(P(11, 10), P(12, 10)));

  // Trapdoor.
  dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  EXPECT_EQ(1, dh->trapdoors().size());
  EXPECT_EQ(kTimestamp + 100, dh->trapdoors()[0].earliest_timestamp());
  EXPECT_EQ(kTimestamp + 104, dh->trapdoors()[0].latest_timestamp());
  EXPECT_EQ(2, dh->trapdoors()[0].contributors_size());
  EXPECT_EQ("Spencer Kimball", dh->trapdoors()[0].contributors(0).full_name());
  EXPECT_EQ("Spencer, You", dh->trapdoors()[0].FormatContributors(false));
  EXPECT_EQ("", dh->trapdoors()[0].FormatContributors(
                false, DayContributor::UNVIEWED_CONTENT));
  EXPECT_EQ("Spencer, You", dh->trapdoors()[0].FormatContributors(
                false, DayContributor::VIEWED_CONTENT));
  // Should be 6 sampled photos out of 7.
  EXPECT_EQ(6, dh->trapdoors()[0].photos_size());
  EXPECT_EQ(11, dh->trapdoors()[0].photos(0).photo_id());
  EXPECT_EQ(12, dh->trapdoors()[0].photos(1).photo_id());
  EXPECT_EQ(9, dh->trapdoors()[0].photos(2).photo_id());
  EXPECT_EQ(7, dh->trapdoors()[0].photos(3).photo_id());
  EXPECT_EQ(4, dh->trapdoors()[0].photos(4).photo_id());
  EXPECT_EQ(2, dh->trapdoors()[0].photos(5).photo_id());
  EXPECT_EQ(7, dh->trapdoors()[0].photo_count());
  */
}

// Verify multiple locations in a viewpoint event trapdoor.
TEST_F(DayTableTest, MultipleLocationsEventTrapdoor) {
  /*
  // Create first episode with no location.
  state_.set_now(kTimestamp);
  EpisodeHandle eh1 = NewEpisode(1);

  SetViewfinderLoc();
  EpisodeHandle eh2 = NewEpisode(1);

  SetSohoHouseLoc();
  EpisodeHandle eh3 = NewEpisode(2);  // overweight

  SetKimballEastLoc();
  EpisodeHandle eh4 = NewEpisode(2);  // overweight

  SetSurfLodgeLoc();
  EpisodeHandle eh5 = NewEpisode(1);

  // Share all episodes into a single viewpoint to verify that
  // disparate locations still blend into a single trapdoor.
  const WallTime now = kTimestamp + kDayDelta;
  ViewpointHandle vh = ShareNew(kDeviceId, kUserId, now, L(P(2, 1)), L(2));
  ShareExisting(kDeviceId, kUserId, now, vh->id().local_id(), L(P(4, 3)));
  ShareExisting(kDeviceId, kUserId, now, vh->id().local_id(), L(P(6, 5), P(7, 5)));
  ShareExisting(kDeviceId, kUserId, now, vh->id().local_id(), L(P(9, 8), P(10, 8)));
  ShareExisting(kDeviceId, kUserId, now, vh->id().local_id(), L(P(12, 11)));

  // With the sharing user himself looking at kTimestamp, there should
  // be 3 events and no viewpoint trapdoor.
  DayHandle dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  ASSERT(dh.get());
  EXPECT_EQ(3, dh->events().size());
  EXPECT_EQ(0, dh->trapdoors().size());

  // Set the user to 2 in order to see the event trapdoor at kTimestamp.
  InvalidateDay(kTimestamp);  // invalidate so we can see user 2's view
  dh = LoadDay(kTimestamp, 2, 2);
  ASSERT_EQ(1, dh->trapdoors().size());
  EXPECT_EQ(1, dh->trapdoors()[0].contributors_size());
  EXPECT_EQ(1, dh->trapdoors()[0].contributors(0).user_id());
  */
}

// Verify that unknown contributors (stored as a user_id) are properly
// handled when formatting contributors post-hoc.
TEST_F(DayTableTest, UnknownContributor) {
  /*
  // Unknown contributor.
  const int kDeviceId2 = 2;
  const int kUserId2 = 2;

  EpisodeHandle eh = NewEpisode(2);
  ViewpointHandle vh = ShareNew(kDeviceId, kUserId, kTimestamp,
                                L(P(2, 1), P(3, 1)), L(2));

  // Now, share the 2nd photo from the episode as a new episode.
  ShareExisting(kDeviceId2, kUserId2, kTimestamp, vh->id().local_id(), L(P(3, 1)));

  DayHandle dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  ASSERT(dh.get());
  ASSERT_EQ(1, dh->trapdoors().size());
  EXPECT_EQ(2, dh->trapdoors()[0].contributors_size());
  EXPECT_EQ(2, dh->trapdoors()[0].contributors(0).user_id());
  EXPECT(dh->trapdoors()[0].contributors(1).has_user_id());
  EXPECT_EQ("You", dh->trapdoors()[0].contributors(1).first_name());

  // Since we don't know user id 2 yet, contributors will only include "You".
  EXPECT_EQ("You", dh->trapdoors()[0].FormatContributors(false));

  // Now, add contact info for unknown contributor and verify we get full list.
  AddContact("a", 2, "Spencer", "Spencer Kimball");
  EXPECT_EQ("Spencer, You", dh->trapdoors()[0].FormatContributors(false));
  */
}

// Make a viewpoint personal.
TEST_F(DayTableTest, PersonalViewpoint) {
  /*
  const int kDeviceId2 = 2;
  const int kUserId2 = 2;
  AddContact("a", 2, "Spencer", "Spencer Kimball");

  EpisodeHandle eh = NewEpisode(2);
  ViewpointHandle vh = ShareNew(kDeviceId, kUserId, kTimestamp,
                                L(P(2, 1), P(3, 1)), L(2));

  // Now, share the 2nd photo from the episode as a new episode.
  ShareExisting(kDeviceId2, kUserId2, kTimestamp, vh->id().local_id(), L(P(3, 1)));

  // Day should contain just a single episode (the original).
  DayHandle dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  ASSERT(dh.get());
  EXPECT_EQ(1, dh->events().size());
  EXPECT_EQ(1, dh->events()[0].episodes_size());
  EXPECT_EQ(eh->id().local_id(), dh->events()[0].episodes(0).episode_id());

  // Set the viewpoint to personal, which invalidates the day.
  {
    DBHandle updates = state_.NewDBTransaction();
    vh->Lock();
    vh->set_label_personal(true);
    vh->SaveAndUnlock(updates);
    updates->Commit();
  }

  // DayHandle, however, should maintain the previous values until released.
  EXPECT_EQ(1, dh->events()[0].episodes_size());
  EXPECT_EQ(eh->id().local_id(), dh->events()[0].episodes(0).episode_id());

  // Re-fetching the handle releases old and gets new.
  dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  EXPECT_EQ(1, dh->events().size());
  EXPECT_EQ(2, dh->events()[0].episodes_size());
  */
}

// Test trapdoor, sums all activity and leaves a single
// trapdoor at the most recent activity. There are photos shared
// on both the first and fourth days. Both of those days will have
// photos sampled. The first day will be an "event" trapdoor. The
// fourth will be a hybrid trapdoor.
TEST_F(DayTableTest, Trapdoors) {
  /*
  const int kDeviceId2 = 2;
  const int kUserId2 = 2;
  AddContact("a", kUserId2, "Spencer", "Spencer Kimball");

  // First day.
  SetViewfinderLoc();
  state_.set_now(kTimestamp);
  EpisodeHandle eh1 = NewEpisode(2);
  // Share from user 2 so we keep a trapdoor for user 1.
  ViewpointHandle vh = ShareNew(kDeviceId2, kUserId2, kTimestamp,
                                L(P(2, 1), P(3, 1)), L(1));

  // Second day.
  state_.set_now(kTimestamp + kDayDelta);
  PostComment(kDeviceId, kUserId, state_.WallTime_Now(),
              vh->id().local_id(), "comment #1");

  // Third day.
  state_.set_now(kTimestamp + kDayDelta * 2);
  PostComment(kDeviceId, kUserId, state_.WallTime_Now(),
              vh->id().local_id(), "comment #2");

  // Fourth day.
  SetKimballEastLoc();
  state_.set_now(kTimestamp + kDayDelta * 3);
  EpisodeHandle eh2 = NewEpisode(2);
  ShareExisting(kDeviceId, kUserId, kTimestamp + kDayDelta * 3,
                vh->id().local_id(), L(P(15, 14), P(16, 14)));
  */
}

// Verify new content is properly accounted for in viewpoint summaries.
TEST_F(DayTableTest, NewContent) {
  /*
  state_.set_now(kTimestamp);
  // Share photo from user 2.
  EpisodeHandle eh1 = NewEpisode(2);
  ViewpointHandle vh = ShareNew(2, 2, kTimestamp, L(P(2, 1)), L(kUserId));

  // Post a comment from user 3.
  PostComment(3, 3, kTimestamp + 1, vh->id().local_id(), "comment #1");

  // Add another share from user 4.
  ShareExisting(4, 4, kTimestamp + 2, vh->id().local_id(), L(P(3, 1)));

  // Post a comment from user 5.
  PostComment(5, 5, kTimestamp + 3, vh->id().local_id(), "comment #2");

  // Go through the activities and assign successive update_seq values.
  AssignActivityUpdateSequenceNos(vh->id().local_id());

  struct {
    int viewed_seq;
    int new_photo_count;
    int new_comment_count;
    int last_new_contributor;
  } test_params[] = {
    { 0, 2, 2, 4 },
    { 1, 1, 2, 3 },
    { 2, 1, 1, 2 },
    { 3, 0, 1, 1 },
    { 4, 0, 0, 0 },
  };

  for (int i = 0; i < ARRAYSIZE(test_params); ++i) {
    {
      DBHandle updates = state_.NewDBTransaction();
      vh->Lock();
      vh->set_viewed_seq(test_params[i].viewed_seq);
      vh->SaveAndUnlock(updates);
      updates->Commit();
    }

    DayHandle dh = LoadDay(kTimestamp, kUserId, kDeviceId);
    ASSERT(dh.get());
    EXPECT_EQ(1, dh->trapdoors().size());
    EXPECT_EQ(test_params[i].new_photo_count,
              dh->trapdoors()[0].new_photo_count());
    EXPECT_EQ(test_params[i].new_comment_count,
              dh->trapdoors()[0].new_comment_count());
    for (int j = 0; j < 4; ++j) {
      if (j < test_params[i].last_new_contributor) {
        EXPECT_EQ(DayContributor::UNVIEWED_CONTENT,
                  dh->trapdoors()[0].contributors(j).type());
      } else {
        EXPECT_EQ(DayContributor::VIEWED_CONTENT,
                  dh->trapdoors()[0].contributors(j).type());
      }
    }
  }
  */
}

// Verify locations are reverse geo-located on demand in
// the order which photos are sampled.
TEST_F(DayTableTest, ReverseGeocode) {
  /*
  Mutex* mu = new Mutex;
  __block int geo_locations = 0;

  state_.reverse_geocode()->Add(^(const Location* l, void (^completion)(const Placemark* p)) {
      const Placemark* pm;
      if (l->latitude() == kKimballEastLoc.latitude()) {
        pm = &kKimballEast;
      } else {
        pm = &kViewfinder;
      }
      state_.async()->dispatch_main(^{
          MutexLock l(mu);
          completion(pm);
          geo_locations++;
        });
    });

  state_.set_now(kTimestamp);
  SetLocation(kKimballEastLoc);
  EpisodeHandle eh1 = NewEpisode(1);

  SetLocation(kViewfinderLoc);
  EpisodeHandle eh2 = NewEpisode(1);

  // The first time the day is loaded, the 1st geocode will be inflight.
  DayHandle dh;
  {
    MutexLock l(mu);
    dh = LoadDay(kTimestamp, kUserId, kDeviceId);
    ASSERT(dh.get());
    mu->Wait(^{ return geo_locations == 1; });
  }
  EXPECT_EQ(2, dh->events().size());
  EXPECT_EQ(0, dh->trapdoors().size());
  EXPECT_EQ(kKimballEastLoc.latitude(), dh->events()[0].location().latitude());
  EXPECT(!dh->events()[0].placemark().has_locality());
  EXPECT_EQ(kViewfinderLoc.latitude(), dh->events()[1].location().latitude());
  EXPECT(!dh->events()[1].placemark().has_locality());

  // The second time, the 1st is placemarked, the 2nd is inflight.
  {
    MutexLock l(mu);
    dh = LoadDay(kTimestamp, kUserId, kDeviceId);
    mu->Wait(^{ return geo_locations == 2; });
  }
  EXPECT_EQ(2, dh->events().size());
  EXPECT_EQ("East Hampton", dh->events()[0].placemark().locality());
  EXPECT(!dh->events()[1].placemark().has_locality());

  // The third time, both are placemarked.
  dh = LoadDay(kTimestamp, kUserId, kDeviceId);
  EXPECT_EQ(2, dh->events().size());
  EXPECT_EQ("East Hampton", dh->events()[0].placemark().locality());
  EXPECT_EQ("New York City", dh->events()[1].placemark().locality());

  delete mu;
  */
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
