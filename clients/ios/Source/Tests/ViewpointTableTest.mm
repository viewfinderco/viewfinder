// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

// TODO(spencer): add Format* tests.

#ifdef TESTING

#import "StringUtils.h"
#import "TestUtils.h"

namespace {

const WallTime kTimestamp = 1347382011;  // 2012-09-11 12:46:51.000

typedef PhotoSelection PS;

class ViewpointTableTest : public BaseContentTest {
 public:
  void SetUp() {
    BaseContentTest::SetUp();
    state_.set_now(kTimestamp);
  }

  string ListViewpointsForPhotoId(int64_t photo_id) {
    vector<int64_t> viewpoint_ids;
    viewpoint_table()->ListViewpointsForPhotoId(photo_id, &viewpoint_ids, state_.db());
    return ToString(viewpoint_ids);
  }

  string ListViewpointsForUserId(int64_t user_id) {
    vector<int64_t> viewpoint_ids;
    viewpoint_table()->ListViewpointsForUserId(user_id, &viewpoint_ids, state_.db());
    return ToString(viewpoint_ids);
  }

  ViewpointSelection NewSelection(
      const string& server_id, bool get_attributes,
      bool get_followers, const string& follower_start_key,
      bool get_activities, const string& activity_start_key,
      bool get_episodes, const string& episode_start_key,
      bool get_comments, const string& comment_start_key) {
    ViewpointSelection vps;
    vps.set_viewpoint_id(server_id);
    vps.set_get_attributes(get_attributes);
    vps.set_get_followers(get_followers);
    if (!follower_start_key.empty()) {
      vps.set_follower_start_key(follower_start_key);
    }
    vps.set_get_activities(get_activities);
    if (!activity_start_key.empty()) {
      vps.set_activity_start_key(activity_start_key);
    }
    vps.set_get_episodes(get_episodes);
    if (!episode_start_key.empty()) {
      vps.set_episode_start_key(episode_start_key);
    }
    vps.set_get_comments(get_comments);
    if (!comment_start_key.empty()) {
      vps.set_comment_start_key(comment_start_key);
    }
    return vps;
  }

  string GetRemovableFollowers(const ViewpointHandle& vh) {
    std::unordered_set<int64_t> removable_set;
    vh->GetRemovableFollowers(&removable_set);
    vector<int64_t> removable(removable_set.begin(), removable_set.end());
    std::sort(removable.begin(), removable.end());
    return ToString(removable);
  }

  void Invalidate(const ViewpointSelection& vps) {
    DBHandle updates = state_.NewDBTransaction();
    viewpoint_table()->Invalidate(vps, updates);
    updates->Commit();
  }

  void Validate(const ViewpointSelection& vps) {
    DBHandle updates = state_.NewDBTransaction();
    viewpoint_table()->Validate(vps, updates);
    updates->Commit();
  }

  void ClearAllInvalidations() {
    DBHandle updates = state_.NewDBTransaction();
    viewpoint_table()->ClearAllInvalidations(updates);
    updates->Commit();
  }

  // Returns a string representing list of invalidations.
  string Invalidations(int limit) {
    vector<ViewpointSelection> vec;
    viewpoint_table()->ListInvalidations(&vec, limit, state_.db());
    return ToString(vec);
  }

  void VerifyCoverPhoto(
      const ViewpointHandle& vh, int64_t exp_photo_id, int64_t exp_episode_id,
      WallTime exp_timestamp, float exp_aspect_ratio) {
    int64_t photo_id;
    int64_t episode_id;
    WallTime timestamp;
    float aspect_ratio;
    ASSERT(vh->GetCoverPhoto(&photo_id, &episode_id, &timestamp, &aspect_ratio));
    ASSERT_EQ(exp_photo_id, photo_id);
    ASSERT_EQ(exp_episode_id, episode_id);
    ASSERT_EQ(exp_timestamp, timestamp);
    ASSERT_EQ(exp_aspect_ratio, aspect_ratio);
  }

  int referenced_viewpoints() const {
    return viewpoint_table()->referenced_contents();
  }

  vector<int64_t> Search(const Slice& query) {
    ViewpointTable::ViewpointSearchResults results;
    state_.viewpoint_table()->Search(query, &results);
    std::sort(results.begin(), results.end());
    return results;
  }
};

TEST_F(ViewpointTableTest, NewViewpoint) {
  for (int i = 1; i < 10; ++i) {
    ASSERT_EQ(i, NewViewpoint()->id().local_id());
    ASSERT_EQ(0, referenced_viewpoints());
  }
}

TEST_F(ViewpointTableTest, Basic) {
  // Create a new viewpoint.
  ASSERT_EQ(0, referenced_viewpoints());
  ViewpointHandle v = NewViewpoint();
  ASSERT_EQ(1, v->id().local_id());
  ASSERT_EQ(1, referenced_viewpoints());
  // Though we never saved the viewpoint, we can load it because there is still a
  // reference to it.
  ASSERT_EQ(v.get(), LoadViewpoint(1).get());
  ASSERT_EQ(1, referenced_viewpoints());
  // Release the reference.
  v.reset();
  ASSERT_EQ(0, referenced_viewpoints());
  // We never saved the viewpoint and there are no other references, so we won't
  // be able to load it.
  ASSERT(!LoadViewpoint(1).get());
  ASSERT_EQ(0, referenced_viewpoints());
  v = NewViewpoint();
  ASSERT_EQ(2, v->id().local_id());
  ASSERT_EQ(1, referenced_viewpoints());
  // Verify we can retrieve it.
  ASSERT_EQ(v.get(), LoadViewpoint(2).get());
  ASSERT_EQ(1, referenced_viewpoints());
  // Verify that setting a server id sets up a mapping to the local id.
  v->Lock();
  v->mutable_id()->set_server_id("a");
  SaveViewpoint(v);
  ASSERT_EQ(v.get(), LoadViewpoint("a").get());
  // Verify that changing the server id works properly.
  v->Lock();
  v->mutable_id()->set_server_id("b");
  SaveViewpoint(v);
  ASSERT_EQ(v.get(), LoadViewpoint("b").get());
  ASSERT(!LoadViewpoint("a").get());
}

TEST_F(ViewpointTableTest, Followers) {
  ViewpointHandle a = NewViewpoint();
  a->Lock();
  ASSERT_EQ("<>", ListFollowers(a));
  // Add follower id 1 to viewpoint id 1.
  a->AddFollower(1);
  SaveViewpoint(a);
  a->Lock();
  ASSERT_EQ("<1>", ListFollowers(a));
  // Add follower id 3 to viewpoint id 1.
  a->AddFollower(3);
  SaveViewpoint(a);
  a->Lock();
  ASSERT_EQ("<1 3>", ListFollowers(a));
  // Add follower id 2 to viewpoint id 1.
  a->AddFollower(2);
  SaveViewpoint(a);
  ASSERT_EQ("<1 2 3>", ListFollowers(a));

  // List viewpoints for each follower and verify.
  const string vp_list = Format("<%d>", a->id().local_id());
  for (int i = 1; i <= 3; ++i) {
    ASSERT_EQ(vp_list, ListViewpointsForUserId(i));
  }
}

TEST_F(ViewpointTableTest, FollowerViewpoints) {
  ViewpointHandle a = NewViewpoint();
  a->Lock();
  a->AddFollower(1);
  SaveViewpoint(a);

  ViewpointHandle b = NewViewpoint();
  b->Lock();
  b->AddFollower(1);
  SaveViewpoint(b);

  // List viewpoints for each follower and verify.
  const string vp_list = Format("<%d %d>", a->id().local_id(), b->id().local_id());
  ASSERT_EQ(vp_list, ListViewpointsForUserId(1));
}

TEST_F(ViewpointTableTest, SimpleInvalidation) {
  ASSERT_EQ("<>", Invalidations(1));
  Invalidate(NewSelection("v1", true, true, "f", true, "a", true, "e", true, "c"));
  ASSERT_EQ("<viewpoint_id: \"v1\"\n"
            "get_attributes: true\n"
            "get_followers: true\n"
            "follower_start_key: \"f\"\n"
            "get_activities: true\n"
            "activity_start_key: \"a\"\n"
            "get_episodes: true\n"
            "episode_start_key: \"e\"\n"
            "get_comments: true\n"
            "comment_start_key: \"c\"\n"
            ">", Invalidations(1));
}

TEST_F(ViewpointTableTest, MergeInvalidates) {
  Invalidate(NewSelection("v1", true, false, "", false, "", false, "", false, ""));
  ASSERT_EQ("<viewpoint_id: \"v1\"\n"
            "get_attributes: true\n"
            ">",
            Invalidations(1));
  Invalidate(NewSelection("v1", true, true, "", false, "", false, "", false, ""));
  ASSERT_EQ("<viewpoint_id: \"v1\"\n"
            "get_attributes: true\n"
            "get_followers: true\n"
            "follower_start_key: \"\"\n"
            ">", Invalidations(1));
  Invalidate(NewSelection("v1", false, true, "f1", true, "a1", true, "e1", true, "c1"));
  ASSERT_EQ("<viewpoint_id: \"v1\"\n"
            "get_attributes: true\n"
            "get_followers: true\n"
            "follower_start_key: \"\"\n"
            "get_activities: true\n"
            "activity_start_key: \"a1\"\n"
            "get_episodes: true\n"
            "episode_start_key: \"e1\"\n"
            "get_comments: true\n"
            "comment_start_key: \"c1\"\n"
            ">", Invalidations(1));
}

TEST_F(ViewpointTableTest, MergeInvalidatesAndValidates) {
  Invalidate(NewSelection("v1", true, false, "", false, "", false, "", false, ""));
  Validate(NewSelection("v1", true, false, "", false, "", false, "", false, ""));
  ASSERT_EQ("<>", Invalidations(1));

  Invalidate(NewSelection("v1", true, true, "", true, "", true, "", true, ""));
  Validate(NewSelection("v1", true, false, "", false, "", false, "", false, ""));
  ASSERT_EQ("<viewpoint_id: \"v1\"\n"
            "get_followers: true\n"
            "follower_start_key: \"\"\n"
            "get_activities: true\n"
            "activity_start_key: \"\"\n"
            "get_episodes: true\n"
            "episode_start_key: \"\"\n"
            "get_comments: true\n"
            "comment_start_key: \"\"\n"
            ">", Invalidations(1));

  Validate(NewSelection("v1", false, true, "", true, "", true, "", true, ""));
  ASSERT_EQ("<>", Invalidations(1));

  // Verify that validating clears keys by correctly comparing values.
  Invalidate(NewSelection("v1", false, true, "f1", true, "a1", true, "", true, ""));
  Validate(NewSelection("v1", false, true, "f1", true, "a2", false, "e1", false, "c1"));
  ASSERT_EQ("<viewpoint_id: \"v1\"\n"
            "get_activities: true\n"
            "activity_start_key: \"a1\"\n"
            "get_episodes: true\n"
            "episode_start_key: \"e1\"\n"
            "get_comments: true\n"
            "comment_start_key: \"c1\"\n"
            ">", Invalidations(1));

  // Verify that a partial validation updates the start_keys.
  Invalidate(NewSelection("v1", false, true, "f1", true, "a1", true, "e1", true, "c1"));
  Validate(NewSelection("v1", false, false, "f2", false, "a2", false, "e2", false, "c2"));
  ASSERT_EQ("<viewpoint_id: \"v1\"\n"
            "get_followers: true\n"
            "follower_start_key: \"f2\"\n"
            "get_activities: true\n"
            "activity_start_key: \"a2\"\n"
            "get_episodes: true\n"
            "episode_start_key: \"e2\"\n"
            "get_comments: true\n"
            "comment_start_key: \"c2\"\n"
            ">", Invalidations(1));
  Invalidate(NewSelection("v1", false, true, "f1", true, "a1", true, "e1", true, "c1"));
  Validate(NewSelection("v1", false, false, "f0", false, "a0", false, "e0", false, "c0"));
  ASSERT_EQ("<viewpoint_id: \"v1\"\n"
            "get_followers: true\n"
            "follower_start_key: \"f1\"\n"
            "get_activities: true\n"
            "activity_start_key: \"a1\"\n"
            "get_episodes: true\n"
            "episode_start_key: \"e1\"\n"
            "get_comments: true\n"
            "comment_start_key: \"c1\"\n"
            ">", Invalidations(1));
}

TEST_F(ViewpointTableTest, ListInvalidations) {
  vector<string> expected(10);
  for (int i = 0; i < expected.size(); i++) {
    string key(Format("v%d/0/0", i));
    Invalidate(NewSelection(key, true, false, "", false, "", false, "", false, ""));
    expected[i] = "viewpoint_id: \"" + key + "\"\n"
                  "get_attributes: true\n";
  }

  ASSERT_EQ("<" + Join(expected, " ", 0, 0) + ">", Invalidations(1));
  ASSERT_EQ("<" + Join(expected, " ", 0, 4) + ">", Invalidations(5));
  ASSERT_EQ("<" + Join(expected, " ") + ">", Invalidations(10));

  ClearAllInvalidations();
  ASSERT_EQ("<>", Invalidations(10));
}

TEST_F(ViewpointTableTest, ShareNewOnePhoto) {
  ASSERT_EQ(1, NewEpisode(1)->id().local_id());

  // Sharing should fail if we have an invalid user_id.
  ASSERT(!ShareNew(1, 0, kTimestamp, L(PS(2, 1)), L(2)).get());

  ASSERT_EQ("<>", ListViewpointsForPhotoId(2));

  // Share a single photo to a new viewpoint.
  ViewpointHandle vh = ShareNew(1, 1, kTimestamp, L(PS(2, 1)), L(2));
  ASSERT(vh.get());
  ASSERT_EQ(3, vh->id().local_id());
  ASSERT_EQ("<4>", ListActivities(vh->id().local_id()));
  ASSERT_EQ("activity_id {\n"
            "  local_id: 4\n"
            "  server_id: \"afv1K0-33\"\n"
            "}\n"
            "viewpoint_id {\n"
            "  local_id: 3\n"
            "  server_id: \"v-FB\"\n"
            "}\n"
            "user_id: 1\n"
            "timestamp: 1347382011\n"
            "queue {\n"
            "  priority: 50\n"
            "  sequence: 1\n"
            "}\n"
            "share_new {\n"
            "  episodes {\n"
            "    episode_id {\n"
            "      local_id: 5\n"
            "      server_id: \"efv1K0-34\"\n"
            "    }\n"
            "    photo_ids {\n"
            "      local_id: 2\n"
            "    }\n"
            "  }\n"
            "  contacts {\n"
            "    user_id: 2\n"
            "  }\n"
            "}\n"
            "upload_activity: true\n",
            ToString(*LoadActivity(4)));
  ASSERT_EQ("<4>", ListNetworkQueue());
  ASSERT_EQ("<2>", ListPhotos(5));
  ASSERT_EQ("<3>", ListViewpointsForPhotoId(2));

  ASSERT(LoadPhoto(2)->shared());

  VerifyCoverPhoto(vh, 2, 5, kTimestamp, 0);
}

TEST_F(ViewpointTableTest, ShareNewMultiplePhotos) {
  ASSERT_EQ(1, NewEpisode(3)->id().local_id());

  // Share multiple photos from a single episode to a new viewpoint.
  ViewpointHandle vh = ShareNew(
      2, 3, kTimestamp, L(PS(2, 1), PS(3, 1), PS(4, 1)), L(4));
  ASSERT(vh.get());
  ASSERT_EQ(5, vh->id().local_id());
  ASSERT_EQ("<6>", ListActivities(vh->id().local_id()));
  ASSERT_EQ("activity_id {\n"
            "  local_id: 6\n"
            "  server_id: \"afv1K0-75\"\n"
            "}\n"
            "viewpoint_id {\n"
            "  local_id: 5\n"
            "  server_id: \"v-VJ\"\n"
            "}\n"
            "user_id: 3\n"
            "timestamp: 1347382011\n"
            "queue {\n"
            "  priority: 50\n"
            "  sequence: 1\n"
            "}\n"
            "share_new {\n"
            "  episodes {\n"
            "    episode_id {\n"
            "      local_id: 7\n"
            "      server_id: \"efv1K0-76\"\n"
            "    }\n"
            "    photo_ids {\n"
            "      local_id: 2\n"
            "    }\n"
            "    photo_ids {\n"
            "      local_id: 3\n"
            "    }\n"
            "    photo_ids {\n"
            "      local_id: 4\n"
            "    }\n"
            "  }\n"
            "  contacts {\n"
            "    user_id: 4\n"
            "  }\n"
            "}\n"
            "upload_activity: true\n",
            ToString(*LoadActivity(6)));
  ASSERT_EQ("<6>", ListNetworkQueue());
  ASSERT_EQ("<2 3 4>", ListPhotos(7));
  ASSERT_EQ("<5>", ListViewpointsForPhotoId(2));
  ASSERT_EQ("<5>", ListViewpointsForPhotoId(3));
  ASSERT_EQ("<5>", ListViewpointsForPhotoId(4));

  ASSERT(LoadPhoto(2)->shared());
  ASSERT(LoadPhoto(3)->shared());
  ASSERT(LoadPhoto(4)->shared());

  VerifyCoverPhoto(vh, 2, 7, kTimestamp, 0);
}

TEST_F(ViewpointTableTest, ShareNewMultipleEpisodes) {
  ASSERT_EQ(1, NewEpisode(2)->id().local_id());
  ASSERT_EQ(4, NewEpisode(2)->id().local_id());

  // Share multiple photos from multiple episodes to a new viewpoint.
  ViewpointHandle vh = ShareNew(
      5, 6, kTimestamp, L(PS(2, 1), PS(5, 4), PS(3, 1), PS(6, 4)), L(7, 8));
  ASSERT(vh.get());
  ASSERT_EQ(7, vh->id().local_id());
  ASSERT_EQ("<8>", ListActivities(vh->id().local_id()));
  ASSERT_EQ("activity_id {\n"
            "  local_id: 8\n"
            "  server_id: \"afv1K0-J7\"\n"
            "}\n"
            "viewpoint_id {\n"
            "  local_id: 7\n"
            "  server_id: \"v0FR\"\n"
            "}\n"
            "user_id: 6\n"
            "timestamp: 1347382011\n"
            "queue {\n"
            "  priority: 50\n"
            "  sequence: 1\n"
            "}\n"
            "share_new {\n"
            "  episodes {\n"
            "    episode_id {\n"
            "      local_id: 9\n"
            "      server_id: \"efv1K0-J8\"\n"
            "    }\n"
            "    photo_ids {\n"
            "      local_id: 2\n"
            "    }\n"
            "    photo_ids {\n"
            "      local_id: 3\n"
            "    }\n"
            "  }\n"
            "  episodes {\n"
            "    episode_id {\n"
            "      local_id: 10\n"
            "      server_id: \"efv1K0-J9\"\n"
            "    }\n"
            "    photo_ids {\n"
            "      local_id: 5\n"
            "    }\n"
            "    photo_ids {\n"
            "      local_id: 6\n"
            "    }\n"
            "  }\n"
            "  contacts {\n"
            "    user_id: 7\n"
            "  }\n"
            "  contacts {\n"
            "    user_id: 8\n"
            "  }\n"
            "}\n"
            "upload_activity: true\n",
            ToString(*LoadActivity(8)));
  ASSERT_EQ("<8>", ListNetworkQueue());
  ASSERT_EQ("<2 3>", ListPhotos(9));
  ASSERT_EQ("<5 6>", ListPhotos(10));
  ASSERT_EQ("<7>", ListViewpointsForPhotoId(2));
  ASSERT_EQ("<7>", ListViewpointsForPhotoId(3));
  ASSERT_EQ("<7>", ListViewpointsForPhotoId(5));
  ASSERT_EQ("<7>", ListViewpointsForPhotoId(6));
  ASSERT(LoadPhoto(2)->shared());
  ASSERT(LoadPhoto(3)->shared());
  ASSERT(LoadPhoto(5)->shared());
  ASSERT(LoadPhoto(6)->shared());

  VerifyCoverPhoto(vh, 2, 9, kTimestamp, 0);
}

TEST_F(ViewpointTableTest, ShareNewNonExistentEpisode) {
  ASSERT_EQ(1, NewEpisode(1)->id().local_id());
  // Share a photo from a non-existent episode. No activity or viewpoint will
  // be created.
  ViewpointHandle vh = ShareNew(1, 1, kTimestamp, L(PS(1, 2)), L(1));
  ASSERT(!vh.get());
  ASSERT_EQ("<>", ListNetworkQueue());
}

TEST_F(ViewpointTableTest, ShareExistingExistingEpisode) {
  ASSERT_EQ(1, NewEpisode(2)->id().local_id());

  ViewpointHandle vh = ShareNew(1, 1, kTimestamp, L(PS(2, 1)), L(2));
  ASSERT(vh.get());
  ASSERT_EQ(4, vh->id().local_id());

  // Sharing should fail if we have an invalid user_id.
  ASSERT(!ShareExisting(1, 0, kTimestamp, 1, L(PS(3, 1))).get());
  // Share a photo to an existing episode on an existing viewpoint.
  vh = ShareExisting(1, 1, kTimestamp, 4, L(PS(3, 1)));
  ASSERT(vh.get());
  ASSERT_EQ(4, vh->id().local_id());
  ASSERT_EQ("<5 8>", ListActivities(vh->id().local_id()));
  ASSERT_EQ("activity_id {\n"
            "  local_id: 8\n"
            "  server_id: \"afv1K0-37\"\n"
            "}\n"
            "viewpoint_id {\n"
            "  local_id: 4\n"
            "  server_id: \"v-FF\"\n"
            "}\n"
            "user_id: 1\n"
            "timestamp: 1347382011\n"
            "queue {\n"
            "  priority: 50\n"
            "  sequence: 2\n"
            "}\n"
            "share_existing {\n"
            "  episodes {\n"
            "    episode_id {\n"
            "      local_id: 6\n"
            "      server_id: \"efv1K0-35\"\n"
            "    }\n"
            "    photo_ids {\n"
            "      local_id: 3\n"
            "    }\n"
            "  }\n"
            "}\n"
            "upload_activity: true\n",
            ToString(*LoadActivity(8)));
  ASSERT_EQ("<5 8>", ListNetworkQueue());
  ASSERT_EQ("<2 3>", ListPhotos(6));
  ASSERT(LoadPhoto(3)->shared());
}

TEST_F(ViewpointTableTest, ShareExistingNewEpisode) {
  ASSERT_EQ(1, NewEpisode(1)->id().local_id());
  ASSERT_EQ(3, NewEpisode(1)->id().local_id());

  ViewpointHandle vh = ShareNew(1, 1, kTimestamp, L(PS(2, 1)), L(2));
  ASSERT(vh.get());
  ASSERT_EQ(5, vh->id().local_id());

  // Share a photo to an existing episode on an existing viewpoint.
  vh = ShareExisting(1, 1, kTimestamp, 5, L(PS(4, 3)));
  ASSERT(vh.get());
  ASSERT_EQ(5, vh->id().local_id());
  ASSERT_EQ("<6 9>", ListActivities(vh->id().local_id()));
  ASSERT_EQ("activity_id {\n"
            "  local_id: 9\n"
            "  server_id: \"afv1K0-38\"\n"
            "}\n"
            "viewpoint_id {\n"
            "  local_id: 5\n"
            "  server_id: \"v-FJ\"\n"
            "}\n"
            "user_id: 1\n"
            "timestamp: 1347382011\n"
            "queue {\n"
            "  priority: 50\n"
            "  sequence: 2\n"
            "}\n"
            "share_existing {\n"
            "  episodes {\n"
            "    episode_id {\n"
            "      local_id: 10\n"
            "      server_id: \"efv1K0-39\"\n"
            "    }\n"
            "    photo_ids {\n"
            "      local_id: 4\n"
            "    }\n"
            "  }\n"
            "}\n"
            "upload_activity: true\n",
            ToString(*LoadActivity(9)));
  ASSERT_EQ("<6 9>", ListNetworkQueue());
  ASSERT_EQ("<4>", ListPhotos(10));
  ASSERT(LoadPhoto(4)->shared());
}

TEST_F(ViewpointTableTest, AddFollowers) {
  ASSERT_EQ(1, NewEpisode(1)->id().local_id());
  ViewpointHandle vh = ShareNew(3, 4, kTimestamp, L(PS(2, 1)), L(2));
  ASSERT(vh.get());
  ASSERT_EQ(3, vh->id().local_id());

  // Adding a follower should fail if we have an invalid user id.
  ASSERT(!AddFollowers(1, 0, kTimestamp, 3, L("a")).get());
  // Add a single follower to an existing viewpoint.
  vh = AddFollowers(3, 4, kTimestamp, 3, L("a"));
  ASSERT(vh.get());
  ASSERT_EQ(3, vh->id().local_id());
  ASSERT_EQ("<4 7>", ListActivities(vh->id().local_id()));
  ASSERT_EQ("activity_id {\n"
            "  local_id: 7\n"
            "  server_id: \"afv1K0-B6\"\n"
            "}\n"
            "viewpoint_id {\n"
            "  local_id: 3\n"
            "  server_id: \"v-kB\"\n"
            "}\n"
            "user_id: 4\n"
            "timestamp: 1347382011\n"
            "queue {\n"
            "  priority: 50\n"
            "  sequence: 2\n"
            "}\n"
            "add_followers {\n"
            "  contacts {\n"
            "    primary_identity: \"a\"\n"
            "    identities {\n"
            "      identity: \"a\"\n"
            "    }\n"
            "  }\n"
            "}\n"
            "upload_activity: true\n",
            ToString(*LoadActivity(7)));
  ASSERT_EQ("<4 7>", ListNetworkQueue());

  // Add multiple followers to an existing viewpoint.
  vh = AddFollowers(3, 4, kTimestamp, 3, L("b", "c", "d"));
  ASSERT(vh.get());
  ASSERT_EQ(3, vh->id().local_id());
  ASSERT_EQ("<4 7 9>", ListActivities(vh->id().local_id()));
  ASSERT_EQ("activity_id {\n"
            "  local_id: 9\n"
            "  server_id: \"afv1K0-B8\"\n"
            "}\n"
            "viewpoint_id {\n"
            "  local_id: 3\n"
            "  server_id: \"v-kB\"\n"
            "}\n"
            "user_id: 4\n"
            "timestamp: 1347382011\n"
            "queue {\n"
            "  priority: 50\n"
            "  sequence: 3\n"
            "}\n"
            "add_followers {\n"
            "  contacts {\n"
            "    primary_identity: \"b\"\n"
            "    identities {\n"
            "      identity: \"b\"\n"
            "    }\n"
            "  }\n"
            "  contacts {\n"
            "    primary_identity: \"c\"\n"
            "    identities {\n"
            "      identity: \"c\"\n"
            "    }\n"
            "  }\n"
            "  contacts {\n"
            "    primary_identity: \"d\"\n"
            "    identities {\n"
            "      identity: \"d\"\n"
            "    }\n"
            "  }\n"
            "}\n"
            "upload_activity: true\n",
            ToString(*LoadActivity(9)));
  ASSERT_EQ("<4 7 9>", ListNetworkQueue());
}

TEST_F(ViewpointTableTest, PostComment) {
  ASSERT_EQ(1, NewEpisode(1)->id().local_id());
  ViewpointHandle vh = ShareNew(9, 10, kTimestamp, L(PS(2, 1)), L(2));
  ASSERT(vh.get());
  ASSERT_EQ(3, vh->id().local_id());

  // Posting a comment should fail if we have an invalid user id.
  ASSERT(!PostComment(1, 0, kTimestamp, 3, "hello").get());
  // Post a comment.
  vh = PostComment(9, 10, kTimestamp, 3, "hello");
  ASSERT(vh.get());
  ASSERT_EQ(3, vh->id().local_id());
  ASSERT_EQ("<4 7>", ListActivities(vh->id().local_id()));
  ASSERT_EQ("activity_id {\n"
            "  local_id: 7\n"
            "  server_id: \"afv1K0-Z6\"\n"
            "}\n"
            "viewpoint_id {\n"
            "  local_id: 3\n"
            "  server_id: \"v1FB\"\n"
            "}\n"
            "user_id: 10\n"
            "timestamp: 1347382011\n"
            "queue {\n"
            "  priority: 50\n"
            "  sequence: 2\n"
            "}\n"
            "post_comment {\n"
            "  comment_id {\n"
            "    local_id: 8\n"
            "    server_id: \"cJ3xeykZ7\"\n"
            "  }\n"
            "}\n"
            "upload_activity: true\n",
            ToString(*LoadActivity(7)));
  CommentHandle ch = LoadComment(8);
  ch->clear_indexed_terms();
  ASSERT_EQ("comment_id {\n"
            "  local_id: 8\n"
            "  server_id: \"cJ3xeykZ7\"\n"
            "}\n"
            "viewpoint_id {\n"
            "  local_id: 3\n"
            "  server_id: \"v1FB\"\n"
            "}\n"
            "user_id: 10\n"
            "timestamp: 1347382011\n"
            "message: \"hello\"\n",
            ToString(*ch));
  ASSERT_EQ("<4 7>", ListNetworkQueue());
}

TEST_F(ViewpointTableTest, Unshare) {
  ASSERT_EQ(1, NewEpisode(1)->id().local_id());
  // Note that the share creates episode 5.
  ViewpointHandle vh = ShareNew(9, 10, kTimestamp, L(PS(2, 1)), L(2));
  ASSERT(vh.get());
  ASSERT_EQ(3, vh->id().local_id());

  // Unsharing should fail if we have an invalid user_id.
  ASSERT(!Unshare(1, 0, kTimestamp, 3, L(PS(2, 5))).get());
  // Unsharing should fail for an invalid viewpoint-id.
  ASSERT(!Unshare(1, 1, kTimestamp, 10000, L(PS(2, 5))).get());
  // Unsharing should fail for an invalid photo-id.
  ASSERT(!Unshare(1, 1, kTimestamp, 3, L(PS(10000, 5))).get());
  // Unsharing should fail for an invalid episode-id.
  ASSERT(!Unshare(1, 1, kTimestamp, 3, L(PS(2, 10000))).get());
  // Unsharing should fail for a valid episode-id that isn't part of the
  // viewpoint.
  ASSERT(!Unshare(1, 1, kTimestamp, 3, L(PS(2, 1))).get());
  // Unshare a photo.
  vh = Unshare(1, 1, kTimestamp, 3, L(PS(2, 5)));
  ASSERT(vh.get());
  ASSERT_EQ(3, vh->id().local_id());
  ASSERT_EQ("<4 10>", ListActivities(vh->id().local_id()));
  ASSERT_EQ("<4 10>", ListNetworkQueue());
  ASSERT_EQ("activity_id {\n"
            "  local_id: 10\n"
            "  server_id: \"afv1K0-39\"\n"
            "}\n"
            "viewpoint_id {\n"
            "  local_id: 3\n"
            "  server_id: \"v1FB\"\n"
            "}\n"
            "user_id: 1\n"
            "timestamp: 1347382011\n"
            "queue {\n"
            "  priority: 50\n"
            "  sequence: 2\n"
            "}\n"
            "unshare {\n"
            "  episodes {\n"
            "    episode_id {\n"
            "      local_id: 5\n"
            "      server_id: \"efv1K0-Z4\"\n"
            "    }\n"
            "    photo_ids {\n"
            "      local_id: 2\n"
            "    }\n"
            "  }\n"
            "}\n"
            "upload_activity: true\n",
            ToString(*LoadActivity(10)));
}

TEST_F(ViewpointTableTest, FullText) {
  ViewpointHandle v1 = NewViewpoint();
  v1->Lock();
  v1->set_title("abc def");
  SaveViewpoint(v1);
  ViewpointHandle v2 = NewViewpoint();
  v2->Lock();
  v2->set_title("ghi abc");
  SaveViewpoint(v2);

  EXPECT_EQ(Search("abc"), vector<int64_t>(L(v1->id().local_id(), v2->id().local_id())));
  EXPECT_EQ(Search("def"), vector<int64_t>(L(v1->id().local_id())));
  EXPECT_EQ(Search("ghi"), vector<int64_t>(L(v2->id().local_id())));
}

TEST_F(ViewpointTableTest, GetRemovableFollowers) {
  ASSERT_EQ(1, NewEpisode(2)->id().local_id());

  ViewpointHandle vh = ShareNew(1, 1, kTimestamp, L(PS(2, 1)), L(3));
  ASSERT(vh.get());
  ASSERT_EQ("<1 3>", GetRemovableFollowers(vh));

  // Add another follower from user 1.
  ASSERT(AddFollowersByIds(1, 1, kTimestamp + 1, vh->id().local_id(), L(4)).get());
  ASSERT_EQ("<1 3 4>", GetRemovableFollowers(vh));

  // Now let user 3 add a follower.
  ASSERT(AddFollowersByIds(3, 3, kTimestamp + 2, vh->id().local_id(), L(5)).get());
  // User 1 will still only see they can remove users 1, 3 & 4.
  state_.SetUserId(1);
  ASSERT_EQ("<1 3 4>", GetRemovableFollowers(vh));
  // User 3 will see they can delete users 3 & 5.
  state_.SetUserId(3);
  ASSERT_EQ("<3 5>", GetRemovableFollowers(vh));

  // Advance time by the clawback grace period - 1s.
  state_.SetUserId(1);
  state_.set_now(kTimestamp + 7 * 24 * 60 * 60 - 1);
  ASSERT_EQ("<1 3 4>", GetRemovableFollowers(vh));
  state_.set_now(kTimestamp + 7 * 24 * 60 * 60);
  ASSERT_EQ("<1 3 4>", GetRemovableFollowers(vh));
  state_.set_now(kTimestamp + 7 * 24 * 60 * 60 + 1);
  ASSERT_EQ("<1 4>", GetRemovableFollowers(vh));
  state_.set_now(kTimestamp + 7 * 24 * 60 * 60 + 2);
  ASSERT_EQ("<1>", GetRemovableFollowers(vh));

  // Switch to user 3.
  state_.SetUserId(3);
  ASSERT_EQ("<3 5>", GetRemovableFollowers(vh));
  state_.set_now(kTimestamp + 7 * 24 * 60 * 60 + 3);
  ASSERT_EQ("<3>", GetRemovableFollowers(vh));
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
