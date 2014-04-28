// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

// TODO(spencer): add Format* tests.

#ifdef TESTING

#import "ActivityTable.h"
#import "Testing.h"
#import "TestUtils.h"

namespace {

class ActivityTableTest : public Test {
 public:
  ActivityTableTest()
      : state_(dir()) {
  }

  ActivityHandle NewActivity() {
    DBHandle updates = state_.NewDBTransaction();
    ActivityHandle h = state_.activity_table()->NewContent(updates);
    updates->Commit();
    return h;
  }

  ActivityHandle LoadActivity(int64_t id) {
    return state_.activity_table()->LoadContent(id, state_.db());
  }

  ActivityHandle LoadActivity(const string& server_id) {
    return state_.activity_table()->LoadContent(server_id, state_.db());
  }

  void SaveActivity(const ActivityHandle& h) {
    DBHandle updates = state_.NewDBTransaction();
    h->SaveAndUnlock(updates);
    updates->Commit();
  }

  // Returns the activity which added the specified episode.
  ActivityHandle GetEpisodeActivity(const string& episode_server_id) {
    vector<int64_t> activity_ids;
    state_.activity_table()->ListEpisodeActivities(
        episode_server_id, &activity_ids, state_.db());
    if (activity_ids.empty()) {
      return ActivityHandle();
    }
    CHECK_EQ(activity_ids.size(), 1);
    return state_.activity_table()->LoadActivity(activity_ids[0], state_.db());
  }

  // Returns the latest activity for viewpoint.
  ActivityHandle GetLatestActivity(int64_t vp_id) {
    return state_.activity_table()->GetLatestActivity(vp_id, state_.db());
  }

  // Returns a string with a list of activity_id,timestamp pairs
  // in the format: <id1:ts1 id2:ts2 ...>
  string ScanActivities(WallTime start, WallTime end, bool reverse) {
    ScopedPtr<ActivityTable::ActivityIterator> iter(
        state_.activity_table()->NewTimestampActivityIterator(start, reverse, state_.db()));
    vector<std::pair<int64_t, WallTime> > activities;
    for (; !iter->done() && (reverse ?
                             iter->timestamp() >= end :
                             iter->timestamp() <= end);
         reverse ? iter->Prev() : iter->Next()) {
      ActivityHandle a = iter->GetActivity();
      activities.push_back(
          std::make_pair(a->activity_id().local_id(), a->timestamp()));
    }
    return ToString(activities);
  }

  // Returns a string with a list of activity_id values
  // in the format: <id1 id2 ...>
  string ScanViewpointActivities(int64_t viewpoint_id, WallTime start, bool reverse = false) {
    ScopedPtr<ActivityTable::ActivityIterator> iter(
        state_.activity_table()->NewViewpointActivityIterator(
            viewpoint_id, start, reverse, state_.db()));
    vector<int64_t> activities;
    for (; !iter->done(); reverse ? iter->Prev() : iter->Next()) {
      ActivityHandle a = iter->GetActivity();
      activities.push_back(a->activity_id().local_id());
    }
    return ToString(activities);
  }

  int referenced_activities() const {
    return state_.activity_table()->referenced_contents();
  }

 protected:
  TestUIAppState state_;
};

TEST_F(ActivityTableTest, NewActivity) {
  for (int i = 1; i < 10; ++i) {
    ASSERT_EQ(i, NewActivity()->activity_id().local_id());
    ASSERT_EQ(0, referenced_activities());
  }
}

TEST_F(ActivityTableTest, Basic) {
  // Create a new activity.
  ASSERT_EQ(0, referenced_activities());
  ActivityHandle a = NewActivity();
  ASSERT_EQ(1, a->activity_id().local_id());
  ASSERT_EQ(1, referenced_activities());
  // Though we never saved the activity, we can load it because there is still a
  // reference to it.
  ASSERT_EQ(a.get(), LoadActivity(1).get());
  ASSERT_EQ(1, referenced_activities());
  // Release the reference.
  a.reset();
  ASSERT_EQ(0, referenced_activities());
  // We never saved the activity and there are no other references, so we won't
  // be able to load it.
  ASSERT(!LoadActivity(1).get());
  ASSERT_EQ(0, referenced_activities());
  a = NewActivity();
  ASSERT_EQ(2, a->activity_id().local_id());
  ASSERT_EQ(1, referenced_activities());
  // Verify we can retrieve it.
  ASSERT_EQ(a.get(), LoadActivity(2).get());
  ASSERT_EQ(1, referenced_activities());
  // Verify that setting a server id sets up a mapping to the local id.
  a->Lock();
  a->mutable_activity_id()->set_server_id("a");
  SaveActivity(a);
  ASSERT_EQ(a.get(), LoadActivity("a").get());
  // Verify that changing the server id works properly.
  a->Lock();
  a->mutable_activity_id()->set_server_id("b");
  SaveActivity(a);
  ASSERT_EQ(a.get(), LoadActivity("b").get());
  ASSERT(!LoadActivity("a").get());
}

TEST(ActivityTableTest, ActivityTimestampKey) {
  struct {
    WallTime timestamp;
    int64_t activity_id;
  } testdata[] = {
    { 1, 1 },
    { 1, 2 },
    { 2, 1 },
    // Verify photo ids greater than 2^32 work.
    { 3, 1ULL << 35 },
    // Verify that negative photo ids work (should get encoded as a very large
    // positive number).
    { 4, -1 },
  };

  string last_key(DBFormat::activity_timestamp_key(""));
  for (int i = 0; i < ARRAYSIZE(testdata); ++i) {
    const string key = EncodeActivityTimestampKey(
        testdata[i].timestamp, testdata[i].activity_id);
    ASSERT_GT(key, last_key) << ": " << i;
    last_key = key;

    WallTime timestamp;
    int64_t activity_id;
    ASSERT(DecodeActivityTimestampKey(key, &timestamp, &activity_id));
    ASSERT_EQ(testdata[i].timestamp, timestamp);
    ASSERT_EQ(testdata[i].activity_id, activity_id);
  }
}

TEST_F(ActivityTableTest, TimestampActivityIterator) {
  ASSERT_EQ("<>", ScanActivities(1, 5, false));

  ActivityHandle activities[5];
  for (int i = 0; i < ARRAYSIZE(activities); ++i) {
    activities[i] = NewActivity();
    activities[i]->Lock();
    ASSERT_EQ(i + 1, activities[i]->activity_id().local_id());
    activities[i]->set_timestamp(i + 1);
    SaveActivity(activities[i]);
  }

  ASSERT_EQ("<1:1 2:2 3:3 4:4 5:5>", ScanActivities(1, 5, false));
  ASSERT_EQ("<5:5 4:4 3:3 2:2 1:1>", ScanActivities(5, 1, true));
  ASSERT_EQ("<1:1 2:2 3:3 4:4>", ScanActivities(1, 4, false));
  ASSERT_EQ("<4:4 3:3 2:2 1:1>", ScanActivities(4, 1, true));
  ASSERT_EQ("<1:1 2:2 3:3>", ScanActivities(1, 3, false));
  ASSERT_EQ("<3:3 2:2 1:1>", ScanActivities(3, 1, true));
  ASSERT_EQ("<2:2 3:3 4:4 5:5>", ScanActivities(2, 5, false));
  ASSERT_EQ("<5:5 4:4 3:3 2:2>", ScanActivities(5, 2, true));
  ASSERT_EQ("<5:5>", ScanActivities(5, 5, false));
  ASSERT_EQ("<5:5>", ScanActivities(5, 5, true));
  ASSERT_EQ("<3:3>", ScanActivities(3, 3, false));
  ASSERT_EQ("<3:3>", ScanActivities(3, 3, true));
  ASSERT_EQ("<1:1>", ScanActivities(1, 1, false));
  ASSERT_EQ("<1:1>", ScanActivities(1, 1, true));
}

TEST_F(ActivityTableTest, ViewpointActivityIterator) {
  ASSERT_EQ("<>", ScanViewpointActivities(1, 0, false));
  ASSERT_EQ("<>", ScanViewpointActivities(1, 0, true));

  ActivityHandle activities[5];
  for (int i = 0; i < ARRAYSIZE(activities); ++i) {
    activities[i] = NewActivity();
    activities[i]->Lock();
    ASSERT_EQ(i + 1, activities[i]->activity_id().local_id());
    activities[i]->mutable_viewpoint_id()->set_local_id(i < 2 ? 1 : 2);
    activities[i]->set_timestamp(i);
    SaveActivity(activities[i]);
  }

  ASSERT_EQ("<1 2>", ScanViewpointActivities(1, 0, false));
  ASSERT_EQ("<1>", ScanViewpointActivities(1, 0, true));
  ASSERT_EQ("<2 1>", ScanViewpointActivities(1, 1, true));
  ASSERT_EQ("<3 4 5>", ScanViewpointActivities(2, 0, false));
  ASSERT_EQ("<>", ScanViewpointActivities(2, 1, true));
  ASSERT_EQ("<3>", ScanViewpointActivities(2, 2, true));
  ASSERT_EQ("<5 4 3>", ScanViewpointActivities(2, 4, true));
}

TEST_F(ActivityTableTest, EpisodeActivityLookup) {
  ActivityHandle ah = GetEpisodeActivity("e1");
  ASSERT(!ah.get());

  ActivityHandle a1h = NewActivity();
  a1h->Lock();
  a1h->mutable_activity_id()->set_server_id("a1");
  ActivityMetadata::Episode* e = a1h->mutable_share_new()->add_episodes();
  e->mutable_episode_id()->set_server_id("e1");
  SaveActivity(a1h);

  ah = GetEpisodeActivity("e1");
  ASSERT_EQ(ah->activity_id().local_id(), a1h->activity_id().local_id());

  ActivityHandle a2h = NewActivity();
  a2h->Lock();
  a2h->mutable_activity_id()->set_server_id("a2");
  e = a2h->mutable_share_existing()->add_episodes();
  e->mutable_episode_id()->set_server_id("e2");
  e = a2h->mutable_share_existing()->add_episodes();
  e->mutable_episode_id()->set_server_id("e3");
  SaveActivity(a2h);

  ah = GetEpisodeActivity("e2");
  ASSERT_EQ(ah->activity_id().local_id(), a2h->activity_id().local_id());
  ah = GetEpisodeActivity("e3");
  ASSERT_EQ(ah->activity_id().local_id(), a2h->activity_id().local_id());
}

TEST_F(ActivityTableTest, ViewpointActivityIteratorWithPendingSave) {
  ActivityHandle a1h = NewActivity();
  a1h->Lock();
  a1h->mutable_viewpoint_id()->set_local_id(1);
  a1h->set_timestamp(1);
  SaveActivity(a1h);

  ASSERT_EQ(a1h->activity_id().local_id(),
            GetLatestActivity(1)->activity_id().local_id());

  DBHandle updates = state_.NewDBTransaction();
  ActivityHandle a2h = state_.activity_table()->NewContent(updates);
  a2h->Lock();
  a2h->mutable_viewpoint_id()->set_local_id(1);  // same viewpoint
  a2h->set_timestamp(2);  // newer timestamp
  a2h->SaveAndUnlock(updates);

  // From updates, we should see the latest.
  ActivityHandle latest = state_.activity_table()->GetLatestActivity(1, updates);
  ASSERT_EQ(a2h->activity_id().local_id(), latest->activity_id().local_id());

  // From straight db, we shouldn't see latest yet.
  latest = state_.activity_table()->GetLatestActivity(1, state_.db());
  ASSERT_EQ(a1h->activity_id().local_id(), latest->activity_id().local_id());

  DBHandle snap = state_.NewDBSnapshot();
  updates->Commit();

  // We should see from database now that it's been committed.
  latest = state_.activity_table()->GetLatestActivity(1, state_.db());
  ASSERT_EQ(a2h->activity_id().local_id(), latest->activity_id().local_id());

  // Snapshot still shouldn't see change.
  latest = state_.activity_table()->GetLatestActivity(1, snap);
  ASSERT_EQ(a1h->activity_id().local_id(), latest->activity_id().local_id());
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
