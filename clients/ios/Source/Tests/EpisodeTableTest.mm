// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "EpisodeTable.h"
#import "PhotoStorage.h"
#import "PhotoTable.h"
#import "Random.h"
#import "ServerId.h"
#import "StringUtils.h"
#import "Testing.h"
#import "TestUtils.h"
#import "Timer.h"

namespace {

typedef PhotoSelection PS;
typedef pair<int64_t, int64_t> EPP;

class EpisodeTableTest : public BaseContentTest {
 public:
  EpisodeHandle NewEpisode() {
    DBHandle updates = state_.NewDBTransaction();
    EpisodeHandle h = state_.episode_table()->NewContent(updates);
    updates->Commit();
    return h;
  }

  EpisodeHandle NewEpisode(WallTime timestamp) {
    DBHandle updates = state_.NewDBTransaction();
    EpisodeHandle h = state_.episode_table()->NewContent(updates);
    h->Lock();
    h->set_timestamp(timestamp);
    h->SaveAndUnlock(updates);
    updates->Commit();
    return h;
  }

  EpisodeHandle NewEpisodeWithTimeAndDevice(WallTime timestamp, int64_t device_id) {
    DBHandle updates = state_.NewDBTransaction();
    EpisodeHandle h = state_.episode_table()->NewContent(updates);
    h->Lock();
    h->set_timestamp(timestamp);
    h->mutable_id()->set_server_id(
        EncodeEpisodeId(device_id, h->id().local_id(), timestamp));
    h->SaveAndUnlock(updates);
    updates->Commit();
    return h;
  }

  PhotoHandle NewPhoto(WallTime timestamp = 0,
                       double latitude = 0, double longitude = 0) {
    DBHandle updates = state_.NewDBTransaction();
    PhotoHandle h = state_.photo_table()->NewContent(updates);
    h->Lock();
    h->set_timestamp(timestamp);
    h->mutable_location()->set_latitude(latitude);
    h->mutable_location()->set_longitude(longitude);
    h->SaveAndUnlock(updates);
    updates->Commit();
    return h;
  }

  PhotoHandle NewPhotoWithTimeAndDevice(WallTime timestamp, int64_t device_id) {
    DBHandle updates = state_.NewDBTransaction();
    PhotoHandle h = state_.photo_table()->NewContent(updates);
    h->Lock();
    h->set_timestamp(timestamp);
    h->mutable_id()->set_server_id(
        EncodePhotoId(device_id, h->id().local_id(), timestamp));
    h->SaveAndUnlock(updates);
    updates->Commit();
    return h;
  }

  EpisodeSelection NewSelection(const string& server_id, bool get_attributes,
                                bool get_photos, const string& photo_start_key) {
    EpisodeSelection eps;
    eps.set_episode_id(server_id);
    eps.set_get_attributes(get_attributes);
    eps.set_get_photos(get_photos);
    if (!photo_start_key.empty()) {
      eps.set_photo_start_key(photo_start_key);
    }
    return eps;
  }

  EpisodeHandle LoadEpisode(int64_t id) {
    return state_.episode_table()->LoadContent(id, state_.db());
  }

  EpisodeHandle LoadEpisode(const string& server_id) {
    return state_.episode_table()->LoadContent(server_id, state_.db());
  }

  void SaveEpisode(const EpisodeHandle& h) {
    DBHandle updates = state_.NewDBTransaction();
    h->SaveAndUnlock(updates);
    updates->Commit();
  }

  string ListPhotos(int64_t episode_id) {
    return ListPhotos(LoadEpisode(episode_id));
  }

  string ListPhotos(const EpisodeHandle& h) {
    vector<int64_t> photo_ids;
    h->ListPhotos(&photo_ids);
    return ToString(photo_ids);
  }

  string ListEpisodes(int64_t photo_id) {
    vector<int64_t> episode_ids;
    state_.episode_table()->ListEpisodes(photo_id, &episode_ids, state_.db());
    return ToString(episode_ids);
  }

  string ScanEpisodes(WallTime begin, bool reverse) {
    ScopedPtr<EpisodeTable::EpisodeIterator> iter(
        state_.episode_table()->NewEpisodeIterator(begin, reverse, state_.db()));
    vector<std::pair<int64_t, WallTime> > episodes;
    for (; !iter->done(); reverse ? iter->Prev() : iter->Next()) {
      episodes.push_back(
          std::make_pair(iter->episode_id(), iter->timestamp()));
    }
    return ToString(episodes);
  }

  void RemovePhotos(const PhotoSelectionVec& photos) {
    DBHandle updates = state_.NewDBTransaction();
    episode_table()->RemovePhotos(photos, updates);
    updates->Commit();
  }

  EpisodeHandle GetEpisodeForPhoto(const PhotoHandle& ph) {
    return state_.episode_table()->GetEpisodeForPhoto(ph, state_.db());
  }

  void Invalidate(const EpisodeSelection& vps) {
    DBHandle updates = state_.NewDBTransaction();
    state_.episode_table()->Invalidate(vps, updates);
    updates->Commit();
  }

  void Validate(const EpisodeSelection& vps) {
    DBHandle updates = state_.NewDBTransaction();
    state_.episode_table()->Validate(vps, updates);
    updates->Commit();
  }

  void ClearAllInvalidations() {
    DBHandle updates = state_.NewDBTransaction();
    state_.episode_table()->ClearAllInvalidations(updates);
    updates->Commit();
  }

  // Returns a string representing list of invalidations.
  string Invalidations(int limit) {
    vector<EpisodeSelection> vec;
    state_.episode_table()->ListInvalidations(&vec, limit, state_.db());
    return ToString(vec);
  }

  string Stats() {
    EpisodeStats stats = state_.episode_table()->stats();
    return ToString(stats);
  }

  int referenced_episodes() const {
    return state_.episode_table()->referenced_contents();
  }

  vector<int64_t> Search(const Slice& query) {
    EpisodeTable::EpisodeSearchResults results;
    state_.episode_table()->Search(query, &results);
    std::sort(results.begin(), results.end());
    return results;
  }
};

TEST_F(EpisodeTableTest, NewEpisode) {
  for (int i = 1; i < 10; ++i) {
    ASSERT_EQ(i, NewEpisode()->id().local_id());
    ASSERT_EQ(0, referenced_episodes());
  }
}

TEST_F(EpisodeTableTest, Basic) {
  // Create a new episode.
  ASSERT_EQ(0, referenced_episodes());
  EpisodeHandle e = NewEpisode();
  ASSERT_EQ(1, e->id().local_id());
  ASSERT_EQ(1, referenced_episodes());
  // Though we never saved the episode, we can load it because there is still a
  // reference to it.
  ASSERT_EQ(e.get(), LoadEpisode(1).get());
  ASSERT_EQ(1, referenced_episodes());
  // Release the reference.
  e.reset();
  ASSERT_EQ(0, referenced_episodes());
  // We never saved the episode and there are no other references, so we won't
  // be able to load it.
  ASSERT(!LoadEpisode(1).get());
  ASSERT_EQ(0, referenced_episodes());
  e = NewEpisode();
  ASSERT_EQ(2, e->id().local_id());
  ASSERT_EQ(1, referenced_episodes());
  // Verify we can retrieve it.
  ASSERT_EQ(e.get(), LoadEpisode(2).get());
  ASSERT_EQ(1, referenced_episodes());
  // Verify that setting a server id sets up a mapping to the local id.
  e->Lock();
  e->mutable_id()->set_server_id("a");
  // Without a save, the episode isn't fetchable by server id.
  ASSERT(!LoadEpisode("a").get());
  SaveEpisode(e);
  ASSERT_EQ(e.get(), LoadEpisode("a").get());
  // Verify that changing the server id works properly.
  e->Lock();
  e->mutable_id()->set_server_id("b");
  SaveEpisode(e);
  ASSERT_EQ(e.get(), LoadEpisode("b").get());
  ASSERT(!LoadEpisode("a").get());
}

// Verify that after we save, but before pending batch updates
// are written to the database, we're still able to load an
// episode by server_id. This is important for bootstrapping
// state.
TEST_F(EpisodeTableTest, InMemoryServerIdQueries) {
  DBHandle updates = state_.NewDBTransaction();

  EpisodeHandle h = state_.episode_table()->NewContent(updates);
  h->Lock();
  h->mutable_id()->set_server_id("a");
  // We can't load until saving.
  ASSERT(!LoadEpisode("a").get());
  h->SaveAndUnlock(updates);
  // Now that we've saved (even though the writes haven't been
  // persisted to the database), we're able to query by server id as
  // the episode is referenced.
  ASSERT_EQ(h.get(), state_.episode_table()->LoadContent("a", updates).get());
  updates->Commit();
  ASSERT_EQ(h.get(), LoadEpisode("a").get());
}

TEST(EpisodeTableTest, EpisodePhotoKey) {
  struct {
    int64_t episode_id;
    int64_t photo_id;
  } testdata[] = {
    { 1, 1 },
    { 1, 2 },
    { 2, 1 },
    { 2, 2 },
    { 2, 3 },
    // Verify episode/photo ids greater than 2^32 work.
    { 2, 1ULL << 35 },
    { 1ULL << 35, 2 },
    // Verify that negative episode/photo ids work (should get encoded as a
    // very large positive number).
    { -1, 1 },
    { -1, -1 },
  };

  string last_key;
  for (int i = 0; i < ARRAYSIZE(testdata); ++i) {
    const string key = EncodeEpisodePhotoKey(
        testdata[i].episode_id, testdata[i].photo_id);
    ASSERT_GT(key, last_key) << ": " << i;
    last_key = key;

    int64_t episode_id;
    int64_t photo_id;
    ASSERT(DecodeEpisodePhotoKey(key, &episode_id, &photo_id));
    ASSERT_EQ(testdata[i].episode_id, episode_id);
    ASSERT_EQ(testdata[i].photo_id, photo_id);
  }
}

TEST(EpisodeTableTest, PhotoEpisodeKey) {
  struct {
    int64_t photo_id;
    int64_t episode_id;
  } testdata[] = {
    { 1, 1 },
    { 1, 2 },
    { 2, 1 },
    { 2, 2 },
    { 2, 3 },
    // Verify episode/photo ids greater than 2^32 work.
    { 2, 1ULL << 35 },
    { 1ULL << 35, 2 },
    // Verify that negative episode/photo ids work (should get encoded as a
    // very large positive number).
    { -1, 1 },
    { -1, -1 },
  };

  string last_key;
  for (int i = 0; i < ARRAYSIZE(testdata); ++i) {
    const string key = EncodePhotoEpisodeKey(
        testdata[i].photo_id, testdata[i].episode_id);
    ASSERT_GT(key, last_key) << ": " << i;
    last_key = key;

    int64_t photo_id;
    int64_t episode_id;
    ASSERT(DecodePhotoEpisodeKey(key, &photo_id, &episode_id));
    ASSERT_EQ(testdata[i].photo_id, photo_id);
    ASSERT_EQ(testdata[i].episode_id, episode_id);
  }
}

TEST(EpisodeTableTest, EpisodeTimestampKey) {
  struct {
    WallTime timestamp;
    int64_t episode_id;
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

  string last_key(DBFormat::episode_timestamp_key(""));
  for (int i = 0; i < ARRAYSIZE(testdata); ++i) {
    const string key = EncodeEpisodeTimestampKey(
        testdata[i].timestamp, testdata[i].episode_id);
    ASSERT_GT(key, last_key) << ": " << i;
    last_key = key;

    WallTime timestamp;
    int64_t episode_id;
    ASSERT(DecodeEpisodeTimestampKey(key, &timestamp, &episode_id));
    ASSERT_EQ(testdata[i].timestamp, timestamp);
    ASSERT_EQ(testdata[i].episode_id, episode_id);
  }
}

TEST_F(EpisodeTableTest, AddRemovePhoto) {
  EpisodeHandle a = NewEpisode();
  ASSERT_EQ("<>", ListPhotos(a));
  ASSERT_EQ("<>", ListEpisodes(1));
  // Add photo id 1 to episode id 1.
  PhotoHandle p1 = NewPhotoWithTimeAndDevice(10, 1);
  a->Lock();
  a->AddPhoto(p1->id().local_id());
  SaveEpisode(a);
  ASSERT_EQ(10, a->earliest_photo_timestamp());
  ASSERT_EQ(10, a->latest_photo_timestamp());
  ASSERT_EQ("<2>", ListPhotos(a));
  ASSERT_EQ("<1>", ListEpisodes(2));
  // Add photo to episode id 1.
  PhotoHandle p3 = NewPhotoWithTimeAndDevice(11, 1);
  a->Lock();
  a->AddPhoto(p3->id().local_id());
  SaveEpisode(a);
  ASSERT_EQ(10, a->earliest_photo_timestamp());
  ASSERT_EQ(11, a->latest_photo_timestamp());
  ASSERT_EQ("<2 3>", ListPhotos(a));
  ASSERT_EQ("<1>", ListEpisodes(3));
  // Add photo to episode id 1.
  PhotoHandle p2 = NewPhotoWithTimeAndDevice(1, 1);
  a->Lock();
  a->AddPhoto(p2->id().local_id());
  SaveEpisode(a);
  ASSERT_EQ(1, a->earliest_photo_timestamp());
  ASSERT_EQ(11, a->latest_photo_timestamp());
  ASSERT_EQ("<2 3 4>", ListPhotos(a));
  ASSERT_EQ("<1>", ListEpisodes(4));
  // Add photo to episode id 2.
  EpisodeHandle b = NewEpisode();
  b->Lock();
  b->AddPhoto(p2->id().local_id());
  SaveEpisode(b);
  ASSERT_EQ("<2 3 4>", ListPhotos(a));
  ASSERT_EQ("<4>", ListPhotos(b));
  ASSERT_EQ("<1 5>", ListEpisodes(4));
  // Remove photo from episode id 1.
  a->Lock();
  a->RemovePhoto(p3->id().local_id());
  SaveEpisode(a);
  ASSERT_EQ("<2 4>", ListPhotos(a));
  ASSERT_EQ("<>", ListEpisodes(3));
  // Clean up.
  a->Lock();
  b->Lock();
  a->RemovePhoto(p1->id().local_id());
  a->RemovePhoto(p2->id().local_id());
  b->RemovePhoto(p2->id().local_id());
  SaveEpisode(a);
  SaveEpisode(b);
  ASSERT_EQ("<>", ListPhotos(a));
  ASSERT_EQ("<>", ListPhotos(b));
  ASSERT_EQ("<>", ListEpisodes(1));
  ASSERT_EQ("<>", ListEpisodes(2));
  ASSERT_EQ("<>", ListEpisodes(3));
}

// 1. Verify photo unshare from episode.
// 2. Verify photo unshare after remove.
TEST_F(EpisodeTableTest, UnsharePhoto) {
  EpisodeHandle a = NewEpisode();

  // 1.
  PhotoHandle p1 = NewPhotoWithTimeAndDevice(10, 1);
  a->Lock();
  a->AddPhoto(p1->id().local_id());
  SaveEpisode(a);
  ASSERT_EQ("<2>", ListPhotos(a));
  ASSERT_EQ("<1>", ListEpisodes(2));
  // Unshare photo.
  a->Lock();
  a->UnsharePhoto(p1->id().local_id());
  SaveEpisode(a);
  ASSERT_EQ("<>", ListPhotos(a));
  ASSERT_EQ("<>", ListEpisodes(2));

  // 2.
  // Add 2nd photo to episode 1.
  PhotoHandle p2 = NewPhotoWithTimeAndDevice(11, 1);
  a->Lock();
  a->AddPhoto(p2->id().local_id());
  SaveEpisode(a);
  ASSERT_EQ("<3>", ListPhotos(a));
  ASSERT_EQ("<1>", ListEpisodes(3));
  // Remove 2nd photo.
  a->Lock();
  a->RemovePhoto(p2->id().local_id());
  SaveEpisode(a);
  ASSERT_EQ("<>", ListPhotos(a));
  ASSERT_EQ("<>", ListEpisodes(2));
  // Now, unshare the already-removed photo.
  a->Lock();
  a->UnsharePhoto(p2->id().local_id());
  SaveEpisode(a);
  ASSERT_EQ("<>", ListPhotos(a));
  ASSERT_EQ("<>", ListEpisodes(2));
}

TEST_F(EpisodeTableTest, RemovePhotos) {
  // Create 2 episodes with 3 photos each.
  int64_t p[6];
  for (int i = 0; i < ARRAYSIZE(p); ++i) {
    PhotoHandle ph = NewPhoto(i, 0, 0);
    p[i] = ph->id().local_id();
  }
  int64_t e[2];
  for (int i = 0; i < ARRAYSIZE(e); ++i) {
    EpisodeHandle eh = NewEpisode();
    eh->Lock();
    for (int j = 0; j < 3; ++j) {
      const int index = 3 * i + j;
      eh->AddPhoto(p[index]);
    }
    SaveEpisode(eh);
    e[i] = eh->id().local_id();
  }

  // Removing a photo from an episode it doesn't exist in does nothing.
  RemovePhotos(L(PS(p[0], 100000)));
  ASSERT_EQ(ToString(L(e[0])), ListEpisodes(p[0]));
  ASSERT_EQ(ToString(L(p[0], p[1], p[2])), ListPhotos(e[0]));
  ASSERT_EQ("<>", ListNetworkQueue());

  // Remove a non-existent photo does nothing.
  RemovePhotos(L(PS(100000, e[0])));
  ASSERT_EQ(ToString(L(e[0])), ListEpisodes(p[0]));
  ASSERT_EQ(ToString(L(p[0], p[1], p[2])), ListPhotos(e[0]));
  ASSERT_EQ("<>", ListNetworkQueue());

  // Remove 1 photo from 1 episode.
  RemovePhotos(L(PS(p[0], e[0])));
  ASSERT_EQ("<>", ListEpisodes(p[0]));
  ASSERT_EQ(ToString(L(p[1], p[2])), ListPhotos(e[0]));
  ASSERT_EQ(ToString(L(L(EPP(e[0], p[0])))),
            ListNetworkQueue());
  ClearNetworkQueue();

  // Remove 2 photos from 1 episode.
  RemovePhotos(L(PS(p[5], e[1]), PS(p[3], e[1])));
  ASSERT_EQ("<>", ListEpisodes(p[3]));
  ASSERT_EQ("<>", ListEpisodes(p[5]));
  ASSERT_EQ(ToString(L(p[4])), ListPhotos(e[1]));
  ASSERT_EQ(ToString(L(L(EPP(e[1], p[5]), EPP(e[1], p[3])))),
            ListNetworkQueue());
  ClearNetworkQueue();

  // Remove 3 photos from 2 episodes.
  RemovePhotos(L(PS(p[4], e[1]), PS(p[1], e[0]), PS(p[2], e[0])));
  ASSERT_EQ("<>", ListEpisodes(p[1]));
  ASSERT_EQ("<>", ListEpisodes(p[2]));
  ASSERT_EQ("<>", ListEpisodes(p[4]));
  ASSERT_EQ("<>", ListPhotos(e[0]));
  ASSERT_EQ("<>", ListPhotos(e[1]));
  ASSERT_EQ(ToString(L(L(EPP(e[1], p[4]), EPP(e[0], p[1]), EPP(e[0], p[2])))),
            ListNetworkQueue());
  ClearNetworkQueue();
}

TEST_F(EpisodeTableTest, GetEpisodeForPhoto) {
  // A completely disassociated photo has not episode.
  PhotoHandle orphan_ph = NewPhoto();
  ASSERT(!GetEpisodeForPhoto(orphan_ph).get());

  state_.SetUserId(1);
  EpisodeHandle orig_eh = NewEpisode();

  // Create a photo with episode id set.
  PhotoHandle ph0 = NewPhoto();
  ph0->Lock();
  ph0->mutable_episode_id()->set_local_id(orig_eh->id().local_id());
  ph0->SaveAndUnlock(state_.db());
  ASSERT_EQ(orig_eh->id().local_id(), GetEpisodeForPhoto(ph0)->id().local_id());

  // Create an episode and add ph1.
  PhotoHandle ph1 = NewPhoto();
  orig_eh->Lock();
  orig_eh->mutable_id()->set_server_id("e1");
  orig_eh->set_user_id(1);
  orig_eh->AddPhoto(ph1->id().local_id());
  SaveEpisode(orig_eh);
  // Verify ph1's episode; since upload_episode bit is not set, this works.
  ASSERT_EQ(orig_eh->id().local_id(), GetEpisodeForPhoto(ph1)->id().local_id());

  // Create a derivative episode by saving the orig_eh.
  PhotoSelectionVec photo_ids;
  photo_ids.push_back(PhotoSelection(ph1->id().local_id(), orig_eh->id().local_id()));
  SavePhotos(1, 1, 0, photo_ids);

  // Verify ph1 now belongs to two episodes.
  vector<int64_t> episode_ids;
  state_.episode_table()->ListEpisodes(
      ph1->id().local_id(), &episode_ids, state_.db());
  ASSERT_EQ(2, episode_ids.size());
  int64_t derived_ep_id = episode_ids[0] == orig_eh->id().local_id() ?
                          episode_ids[1] : episode_ids[0];
  EpisodeHandle derived_eh = LoadEpisode(derived_ep_id);
  ASSERT(derived_eh->upload_episode());

  // ph1's episode is still orig_eh, not the derived episode.
  ASSERT_EQ(orig_eh->id().local_id(), GetEpisodeForPhoto(ph1)->id().local_id());

  // However, if we remove ph1 from the original episode, we'll end up
  // with no appropriate episode, as derived episode is still awaiting
  // upload.
  orig_eh->Lock();
  orig_eh->RemovePhoto(ph1->id().local_id());
  SaveEpisode(orig_eh);
  ASSERT(!GetEpisodeForPhoto(ph1).get());

  // Clear the upload_episode bit to correct for this.
  derived_eh->Lock();
  derived_eh->clear_upload_episode();
  SaveEpisode(derived_eh);
  ASSERT_EQ(derived_eh->id().local_id(), GetEpisodeForPhoto(ph1)->id().local_id());
}

TEST_F(EpisodeTableTest, EpisodeStats) {
  ASSERT_EQ("{\n  posted_photos: 0,\n  removed_photos: 0\n}", Stats());
  EpisodeHandle a = NewEpisode();
  PhotoHandle p = NewPhoto();
  a->Lock();
  a->AddPhoto(p->id().local_id());
  // Stats don't update until save.
  ASSERT_EQ("{\n  posted_photos: 0,\n  removed_photos: 0\n}", Stats());
  SaveEpisode(a);
  ASSERT_EQ("{\n  posted_photos: 1,\n  removed_photos: 0\n}", Stats());
  // Remove photo id 1 from episode id 1.
  a->Lock();
  a->RemovePhoto(p->id().local_id());
  // Stats don't update until save.
  ASSERT_EQ("{\n  posted_photos: 1,\n  removed_photos: 0\n}", Stats());
  SaveEpisode(a);
  ASSERT_EQ("{\n  posted_photos: 0,\n  removed_photos: 1\n}", Stats());
  EpisodeHandle b = NewEpisode();
  PhotoHandle p2 = NewPhoto();
  PhotoHandle p3 = NewPhoto();
  b->Lock();
  b->AddPhoto(p2->id().local_id());
  b->AddPhoto(p3->id().local_id());
  SaveEpisode(b);
  ASSERT_EQ("{\n  posted_photos: 2,\n  removed_photos: 1\n}", Stats());
  // Photo in more than one episode.
  a->Lock();
  a->AddPhoto(p2->id().local_id());
  SaveEpisode(a);
  ASSERT_EQ("{\n  posted_photos: 3,\n  removed_photos: 1\n}", Stats());
  // Clean up.
  a->Lock();
  b->Lock();
  a->RemovePhoto(p2->id().local_id());
  b->RemovePhoto(p2->id().local_id());
  b->RemovePhoto(p3->id().local_id());
  SaveEpisode(a);
  SaveEpisode(b);
  ASSERT_EQ("{\n  posted_photos: 0,\n  removed_photos: 4\n}", Stats());
}

TEST_F(EpisodeTableTest, EpisodeIterator) {
  EpisodeHandle episodes[5];
  for (int i = 0; i < ARRAYSIZE(episodes); ++i) {
    episodes[i] = NewEpisode();
    ASSERT_EQ(i + 1, episodes[i]->id().local_id());
    episodes[i]->Lock();
    episodes[i]->set_timestamp(i + 1);
    SaveEpisode(episodes[i]);
  }

  // None of the episodes should be visible yet because they are all empty.
  ASSERT_EQ("<>", ScanEpisodes(0, false));
  ASSERT_EQ("<>", ScanEpisodes(0, true));

  PhotoHandle p = NewPhotoWithTimeAndDevice(1, 1);
  const int64_t pid = p->id().local_id();

  // Build it up.
  episodes[0]->Lock();
  episodes[0]->AddPhoto(pid);
  SaveEpisode(episodes[0]);
  ASSERT_EQ("<1:1>", ScanEpisodes(0, false));
  ASSERT_EQ("<>", ScanEpisodes(0, true));
  ASSERT_EQ("<1:1>", ScanEpisodes(1, true));
  ASSERT_EQ("<1:1>", ScanEpisodes(2, true));
  episodes[1]->Lock();
  episodes[1]->AddPhoto(pid);
  SaveEpisode(episodes[1]);
  ASSERT_EQ("<1:1 2:2>", ScanEpisodes(0, false));
  ASSERT_EQ("<2:2 1:1>", ScanEpisodes(2, true));
  episodes[2]->Lock();
  episodes[2]->AddPhoto(pid);
  SaveEpisode(episodes[2]);
  ASSERT_EQ("<1:1 2:2 3:3>", ScanEpisodes(0, false));
  ASSERT_EQ("<3:3 2:2 1:1>", ScanEpisodes(3, true));
  episodes[3]->Lock();
  episodes[3]->AddPhoto(pid);
  SaveEpisode(episodes[3]);
  ASSERT_EQ("<1:1 2:2 3:3 4:4>", ScanEpisodes(0, false));
  ASSERT_EQ("<4:4 3:3 2:2 1:1>", ScanEpisodes(4, true));
  episodes[4]->Lock();
  episodes[4]->AddPhoto(pid);
  SaveEpisode(episodes[4]);
  ASSERT_EQ("<1:1 2:2 3:3 4:4 5:5>", ScanEpisodes(0, false));
  ASSERT_EQ("<5:5 4:4 3:3 2:2 1:1>", ScanEpisodes(5, true));

  // Tear it down.
  episodes[0]->Lock();
  episodes[0]->RemovePhoto(pid);
  SaveEpisode(episodes[0]);
  ASSERT_EQ("<2:2 3:3 4:4 5:5>", ScanEpisodes(0, false));
  ASSERT_EQ("<5:5 4:4 3:3 2:2>", ScanEpisodes(5, true));
  episodes[1]->Lock();
  episodes[1]->RemovePhoto(pid);
  SaveEpisode(episodes[1]);
  ASSERT_EQ("<3:3 4:4 5:5>", ScanEpisodes(0, false));
  ASSERT_EQ("<5:5 4:4 3:3>", ScanEpisodes(5, true));
  episodes[2]->Lock();
  episodes[2]->RemovePhoto(pid);
  SaveEpisode(episodes[2]);
  ASSERT_EQ("<4:4 5:5>", ScanEpisodes(0, false));
  ASSERT_EQ("<5:5 4:4>", ScanEpisodes(5, true));
  episodes[3]->Lock();
  episodes[3]->RemovePhoto(pid);
  SaveEpisode(episodes[3]);
  ASSERT_EQ("<5:5>", ScanEpisodes(0, false));
  ASSERT_EQ("<5:5>", ScanEpisodes(5, true));
  episodes[4]->Lock();
  episodes[4]->RemovePhoto(pid);
  SaveEpisode(episodes[4]);
  ASSERT_EQ("<>", ScanEpisodes(0, false));
  ASSERT_EQ("<>", ScanEpisodes(5, true));
}


TEST_F(EpisodeTableTest, SimpleInvalidation) {
  ASSERT_EQ("<>", Invalidations(1));
  Invalidate(NewSelection("e1", true, true, "f"));
  ASSERT_EQ("<episode_id: \"e1\"\n"
            "get_attributes: true\n"
            "get_photos: true\n"
            "photo_start_key: \"f\"\n"
            ">", Invalidations(1));
}

TEST_F(EpisodeTableTest, MergeInvalidates) {
  Invalidate(NewSelection("e1", true, false, ""));
  ASSERT_EQ("<episode_id: \"e1\"\n"
            "get_attributes: true\n"
            ">", Invalidations(1));
  Invalidate(NewSelection("e1", true, true, ""));
  ASSERT_EQ("<episode_id: \"e1\"\n"
            "get_attributes: true\n"
            "get_photos: true\n"
            "photo_start_key: \"\"\n"
            ">", Invalidations(1));
  Invalidate(NewSelection("e1", false, true, "f1"));
  ASSERT_EQ("<episode_id: \"e1\"\n"
            "get_attributes: true\n"
            "get_photos: true\n"
            "photo_start_key: \"\"\n"
            ">", Invalidations(1));
}

TEST_F(EpisodeTableTest, MergeInvalidatesAndValidates) {
  Invalidate(NewSelection("e1", true, false, ""));
  Validate(NewSelection("e1", true, false, ""));
  ASSERT_EQ("<>", Invalidations(1));

  Invalidate(NewSelection("e1", true, true, ""));
  Validate(NewSelection("e1", true, false, ""));
  ASSERT_EQ("<episode_id: \"e1\"\n"
            "get_photos: true\n"
            "photo_start_key: \"\"\n"
            ">", Invalidations(1));

  Validate(NewSelection("e1", false, true, ""));
  ASSERT_EQ("<>", Invalidations(1));

  // Verify that validating clears keys by correctly comparing values.
  Invalidate(NewSelection("e1", false, true, "p1"));
  Validate(NewSelection("e1", false, true, "p2"));
  ASSERT_EQ("<episode_id: \"e1\"\n"
            "get_photos: true\n"
            "photo_start_key: \"p1\"\n"
            ">", Invalidations(1));

  // Verify that a partial validation updates the start_key.
  Invalidate(NewSelection("e1", false, true, "p1"));
  Validate(NewSelection("e1", false, false, "p2"));
  ASSERT_EQ("<episode_id: \"e1\"\n"
            "get_photos: true\n"
            "photo_start_key: \"p2\"\n"
            ">", Invalidations(1));
  Invalidate(NewSelection("e1", false, true, "p1"));
  Validate(NewSelection("e1", false, false, "p0"));
  ASSERT_EQ("<episode_id: \"e1\"\n"
            "get_photos: true\n"
            "photo_start_key: \"p1\"\n"
            ">", Invalidations(1));
}

TEST_F(EpisodeTableTest, ListInvalidations) {
  vector<string> expected(10);
  for (int i = 0; i < expected.size(); i++) {
    string key(Format("v%d", i));
    Invalidate(NewSelection(key, true, false, ""));
    expected[i] = "episode_id: \"" + key + "\"\n"
                  "get_attributes: true\n";
  }

  ASSERT_EQ("<" + Join(expected, " ", 0, 0) + ">", Invalidations(1));
  ASSERT_EQ("<" + Join(expected, " ", 0, 4) + ">", Invalidations(5));
  ASSERT_EQ("<" + Join(expected, " ") + ">", Invalidations(10));

  ClearAllInvalidations();
  ASSERT_EQ("<>", Invalidations(10));
}

TEST_F(EpisodeTableTest, MatchPhotoToEpisode) {
  // NOTE(peter): This test data came from on old set of photos on my
  // iphone. The dates and locations are from actual photos. The expected
  // episode id was computed and then manually verified.
  struct {
    WallTime timestamp;
    double latitude;
    double longitude;
    int64_t expected_episode_id;
  } kTestData[] = {
    { 1269033177, 40.725167, -74.002333, 2 },
    { 1269034389, 40.725333, -74.003333, 2 },
    { 1269034392, 40.725333, -74.003333, 2 },
    { 1269034405, 40.725333, -74.003167, 2 },
    { 1269034412, 40.725333, -74.003167, 2 },
    { 1269034419, 40.725333, -74.003167, 2 },
    { 1270240917, 40.722833, -73.998667, 9 },
    { 1279493967, 38.404333, -122.365000, 11 },
    { 1282005790, 40.911000, -72.352167, 13 },
    { 1282005799, 40.903167, -72.306000, 13 },
    { 1282005801, 40.903167, -72.306000, 13 },
    { 1282005804, 40.903167, -72.306000, 13 },
    { 1282344431, 40.938000, -72.379833, 18 },
    { 1282344433, 40.937833, -72.379833, 18 },
    { 1283466300, 40.989167, -72.360333, 21 },
    { 1283466304, 40.937833, -72.380333, 21 },
    { 1283466424, 40.938000, -72.379833, 21 },
    { 1283466426, 40.989167, -72.360333, 21 },
    { 1283783247, 40.667167, -73.972833, 26 },
    { 1284828520, 40.675500, -73.981333, 28 },
    { 1285191161, 40.671333, -73.971333, 30 },
    { 1286050930, 40.671333, -73.971333, 32 },
    { 1286050932, 40.671333, -73.971333, 32 },
    { 1286050940, 40.671333, -73.971333, 32 },
    { 1286050946, 40.671333, -73.971333, 32 },
    { 1288178072, 40.671500, -73.971333, 37 },
    { 1288178076, 40.671500, -73.971333, 37 },
    { 1288178081, 40.671500, -73.971333, 37 },
    { 1288354597, 40.671500, -73.971500, 41 },
    { 1288354597, 40.671500, -73.971500, 41 },
    { 1288354899, 40.671500, -73.971500, 41 },
    { 1288354899, 40.671500, -73.971500, 41 },
    { 1288354906, 40.671500, -73.971500, 41 },
    { 1288354907, 40.671500, -73.971500, 41 },
    { 1288355660, 40.673833, -73.978167, 41 },
    { 1288355660, 40.673833, -73.978167, 41 },
    { 1288356079, 40.674000, -73.978167, 41 },
    { 1288356158, 40.674000, -73.978167, 41 },
    { 1288451417, 40.674500, -73.977500, 52 },
    { 1288451419, 40.674500, -73.977500, 52 },
    { 1288452554, 40.674333, -73.977667, 52 },
    { 1288452556, 40.674333, -73.977667, 52 },
    { 1288452557, 40.674333, -73.977667, 52 },
    { 1288452560, 40.674333, -73.977667, 52 },
    { 1288452562, 40.674333, -73.977667, 52 },
    { 1288563708, 40.671500, -73.971333, 60 },
    { 1288563708, 40.671500, -73.971333, 60 },
    { 1289242733, 40.742167, -73.992500, 63 },
    { 1289242733, 40.742167, -73.992500, 63 },
    { 1289242752, 40.742167, -73.992500, 63 },
    { 1289693109, 40.671500, -73.971667, 67 },
    { 1289693110, 40.671500, -73.971667, 67 },
    { 1289746700, 40.667167, -73.973167, 70 },
    { 1289746700, 40.667167, -73.973167, 70 },
    { 1289746740, 40.667333, -73.973167, 70 },
    { 1289746756, 40.667333, -73.973167, 70 },
    { 1289746768, 40.667333, -73.973167, 70 },
    { 1289746914, 40.667667, -73.973667, 70 },
    { 1289746925, 40.667167, -73.973000, 70 },
    { 1290361198, 40.679333, -73.968667, 78 },
    { 1290361296, 40.679333, -73.968667, 78 },
    { 1290361351, 40.679333, -73.968667, 78 },
    { 1290361473, 40.679333, -73.968333, 78 },
    { 1290441983, 40.673833, -73.978167, 83 },
    { 1290693370, 40.765000, -73.997667, 85 },
    { 1290693372, 40.765167, -73.997667, 85 },
    { 1290693375, 40.765167, -73.997667, 85 },
    { 1292541885, 40.671500, -73.971500, 89 },
    { 1292541885, 40.671500, -73.971500, 89 },
    { 1293043881, 40.686167, -111.557333, 92 },
    { 1293043891, 40.686167, -111.557333, 92 },
    { 1293200647, 40.682500, -111.584333, 95 },
    { 1293233121, 40.690667, -111.550000, 97 },
    { 1293233126, 40.690667, -111.550000, 97 },
    { 1293233139, 40.690667, -111.550167, 97 },
    { 1293233163, 40.690833, -111.550333, 97 },
    { 1295120108, 40.671500, -73.971333, 102 },
    { 1298303464, 40.671333, -73.971500, 104 },
    { 1301154260, 19.950000, -155.862000, 106 },
    { 1301154329, 19.950167, -155.862000, 106 },
    { 1302318998, 40.727833, -73.994500, 109 },
    { 1302390099, 40.671500, -73.971333, 111 },
    { 1302390103, 40.671333, -73.971167, 111 },
    { 1303257048, 40.671333, -73.971333, 114 },
    { 1303781051, 40.671500, -73.971500, 116 },
    { 1304006007, 40.741667, -74.003000, 118 },
    { 1304006020, 40.741667, -74.003000, 118 },
    { 1304006021, 40.741667, -74.003000, 118 },
    { 1304006023, 40.741667, -74.003000, 118 },
    { 1305998484, 40.671500, -73.971667, 123 },
    { 1306005700, 40.671500, -73.971167, 125 },
    { 1307282470, 40.668000, -73.973667, 127 },
    { 1307282485, 40.667333, -73.974667, 127 },
    { 1307282500, 40.667333, -73.974667, 127 },
    { 1311707414, 40.671500, -73.971500, 131 },
    { 1311707415, 40.671500, -73.971500, 131 },
    { 1311707444, 40.671500, -73.971500, 131 },
    { 1311707444, 40.671500, -73.971500, 131 },
    { 1311772477, 40.671500, -73.971500, 136 },
    { 1311772478, 40.671500, -73.971500, 136 },
    { 1313085706, 40.671500, -73.971333, 139 },
    { 1313085707, 40.671500, -73.971333, 139 },
    { 1313342910, 40.671500, -73.971500, 142 },
    { 1313342910, 40.671500, -73.971500, 142 },
    { 1313946726, 40.675667, -73.969833, 145 },
    { 1313946727, 40.675667, -73.969833, 145 },
    { 1313946732, 40.675667, -73.969833, 145 },
    { 1313946735, 40.675667, -73.969833, 145 },
    { 1313946747, 40.676000, -73.969833, 145 },
    { 1313946751, 40.676000, -73.969833, 145 },
    { 1313946771, 40.675833, -73.970167, 145 },
    { 1313946772, 40.675833, -73.970167, 145 },
    { 1313946774, 40.675833, -73.970167, 145 },
    { 1313946779, 40.675833, -73.970000, 145 },
    { 1313946781, 40.675833, -73.970000, 145 },
    { 1313946783, 40.675833, -73.970000, 145 },
    { 1313946789, 40.675667, -73.969833, 145 },
    { 1313946799, 40.675667, -73.969667, 145 },
    { 1313946802, 40.675667, -73.969667, 145 },
    { 1313946806, 40.675667, -73.969667, 145 },
    { 1313946808, 40.675833, -73.969667, 145 },
    { 1313946810, 40.675833, -73.969667, 145 },
    { 1313946813, 40.675833, -73.969667, 145 },
    { 1313946816, 40.675833, -73.969667, 145 },
    { 1313946818, 40.675833, -73.969500, 145 },
    { 1313946821, 40.675833, -73.969500, 145 },
    { 1314474418, 40.671500, -73.971167, 168 },
    { 1314474470, 40.671333, -73.971333, 168 },
    { 1314474502, 40.671333, -73.971333, 168 },
    { 1314474505, 40.671333, -73.971333, 168 },
    { 1315169046, 40.671500, -73.971667, 173 },
    { 1315169080, 40.671500, -73.971500, 173 },
    { 1318194603, 40.671500, -73.971500, 176 },
    { 1318695550, 40.729833, -73.999500, 178 },
    { 1318695757, 40.729833, -73.999500, 178 },
    { 1319111642, 40.671500, -73.971333, 181 },
    { 1319111644, 40.671500, -73.971333, 181 },
    { 1319111651, 40.671500, -73.971333, 181 },
    { 1319111654, 40.671500, -73.971333, 181 },
    { 1319111785, 40.671500, -73.971500, 181 },
    { 1319111804, 40.671500, -73.971500, 181 },
    { 1319226529, 19.016167, -70.020000, 188 },
    { 1319301245, 19.679667, -70.377500, 190 },
    { 1319301681, 19.675500, -70.044833, 192 },
    { 1319304493, 19.677500, -70.035500, 192 },
    { 1319304496, 19.677500, -70.035500, 192 },
    { 1319304516, 19.677500, -70.035500, 192 },
    { 1319304526, 19.677500, -70.035500, 192 },
    { 1319304540, 19.677500, -70.035500, 192 },
    { 1319348440, 19.641667, -69.903833, 199 },
    { 1319348814, 19.641833, -69.904000, 199 },
    { 1319916461, 40.664833, -73.978500, 202 },
    { 1320006025, 40.721667, -73.994667, 204 },
    { 1320006036, 40.723500, -73.996500, 204 },
    { 1320006549, 40.723333, -73.996167, 204 },
    { 1320006553, 40.723333, -73.996333, 204 },
    { 1320006556, 40.723333, -73.996333, 204 },
    { 1320006587, 40.723333, -73.996667, 204 },
    { 1320006728, 40.723500, -73.996500, 204 },
    { 1320007249, 40.723500, -73.996333, 204 },
    { 1320007252, 40.723500, -73.996333, 204 },
    { 1322153396, 40.671500, -73.971667, 214 },
    { 1322153398, 40.671500, -73.971667, 214 },
    { 1322153429, 40.671500, -73.971500, 214 },
    { 1322153435, 40.671667, -73.971500, 214 },
    { 1322153439, 40.671667, -73.971500, 214 },
    { 1322153441, 40.671667, -73.971500, 214 },
    { 1322170291, 40.671333, -73.971500, 221 },
    { 1322170325, 40.671333, -73.971500, 221 },
    { 1322171918, 40.671500, -73.971667, 221 },
    { 1322171921, 40.671500, -73.971667, 221 },
    { 1322171929, 40.671500, -73.971667, 221 },
    { 1322171934, 40.671500, -73.971667, 221 },
    { 1322171939, 40.671500, -73.971667, 221 },
    { 1322171951, 40.671333, -73.971833, 221 },
    { 1322171953, 40.671333, -73.971833, 221 },
    { 1322171955, 40.671333, -73.971667, 221 },
    { 1322174189, 40.671500, -73.971667, 232 },
    { 1322174194, 40.671333, -73.971833, 232 },
    { 1323457208, 40.727833, -73.995333, 235 },
    { 1323621454, 40.738333, -73.990000, 237 },
    { 1323621462, 40.738333, -73.990000, 237 },
    { 1323621578, 40.738333, -73.989833, 237 },
    { 1323621581, 40.738333, -73.990000, 237 },
    { 1323621584, 40.738333, -73.990000, 237 },
    { 1326639081, 43.113667, -72.907333, 243 },
    { 1326639083, 43.113667, -72.907333, 243 },
    { 1326640689, 43.113333, -72.907833, 243 },
    { 1326640694, 43.113333, -72.907833, 243 },
    { 1327592244, 0.000000, 0.000000, 248 },
    { 1327592244, 0.000000, 0.000000, 248 },
    { 1327592244, 0.000000, 0.000000, 248 },
    { 1327592244, 0.000000, 0.000000, 248 },
    { 1327592313, 0.000000, 0.000000, 248 },
  };

  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    PhotoHandle ph = NewPhoto(
        kTestData[i].timestamp, kTestData[i].latitude, kTestData[i].longitude);
    EpisodeHandle eh = state_.episode_table()->MatchPhotoToEpisode(ph, state_.db());
    if (!eh.get()) {
      eh = NewEpisode(ph->timestamp());
    }
    eh->Lock();
    ASSERT_EQ(kTestData[i].expected_episode_id, eh->id().local_id());
    eh->AddPhoto(ph->id().local_id());
    SaveEpisode(eh);
  }
}

TEST_F(EpisodeTableTest, MatchPhotoToEpisodeDeviceId) {
  // Create an episode from an old device and add a photo.
  EpisodeHandle old_eh = NewEpisodeWithTimeAndDevice(1, 1);
  PhotoHandle old_ph = NewPhotoWithTimeAndDevice(1, 1);
  old_eh->Lock();
  old_eh->AddPhoto(old_ph->id().local_id());
  SaveEpisode(old_eh);

  // Create a photo to match.
  PhotoHandle ph = NewPhotoWithTimeAndDevice(1, 2);
  EpisodeHandle match_eh =
      state_.episode_table()->MatchPhotoToEpisode(ph, state_.db());
  // Shouldn't match the existing episode from old device.
  EXPECT(!match_eh.get());

  // Now create an episode from new device and add a photo.
  EpisodeHandle eh = NewEpisodeWithTimeAndDevice(1, 2);
  PhotoHandle new_ph = NewPhotoWithTimeAndDevice(1, 2);
  eh->Lock();
  eh->AddPhoto(new_ph->id().local_id());
  SaveEpisode(eh);

  // Now, the test photo should match the new episode.
  match_eh = state_.episode_table()->MatchPhotoToEpisode(ph, state_.db());
  EXPECT_EQ(eh.get(), match_eh.get());
}

TEST_F(EpisodeTableTest, MatchPhotoToEpisodeParentId) {
  // Create an episode with a parent id and add a photo.
  EpisodeHandle child_eh = NewEpisode(1);
  PhotoHandle child_ph = NewPhoto(1, 0, 0);
  child_eh->Lock();
  child_eh->mutable_parent_id()->set_server_id("parent");
  child_eh->AddPhoto(child_ph->id().local_id());
  SaveEpisode(child_eh);

  // Create a photo to match.
  PhotoHandle ph = NewPhoto(1, 0, 0);
  EpisodeHandle match_eh =
      state_.episode_table()->MatchPhotoToEpisode(ph, state_.db());
  // Shouldn't match the existing episode from old device.
  EXPECT(!match_eh.get());

  // Clear out parent id on episode and photo should now match.
  child_eh->Lock();
  child_eh->clear_parent_id();
  SaveEpisode(child_eh);
  match_eh = state_.episode_table()->MatchPhotoToEpisode(ph, state_.db());
  EXPECT_EQ(child_eh.get(), match_eh.get());
}

TEST_F(EpisodeTableTest, CanAddPhotoToEpisode) {
  const WallTime kNow = 1000;
  const WallTime kDay = 24 * 60 * 60;

  struct {
    int64_t photo_user_id;
    int64_t photo_device_id;
    int64_t episode_user_id;
    int64_t episode_device_id;
    int64_t expected_episode_id;
  } kTestData[] = {
    // Neither photo or episode has a user id set.
    { 0, 0, 0, 0, 2 },
    // Photo has user id, episode does not.
    { 1, 0, 0, 0, 5 },
    // Episode has user id, photo does not.
    { 0, 0, 1, 0, 8 },
    // Photo has mismatching user id.
    { 2, 0, 0, 0, 0 },
    // Episode has mismatching user id.
    { 0, 0, 2, 0, 0 },
    // Photo and episode have mismatching user id.
    { 1, 0, 2, 0, 0 },
    // Photo and episode have matching user id.
    { 3, 0, 3, 0, 20 },
    // Photo has device id, episode does not.
    { 0, 2, 0, 0, 23 },
    // Episode has device id, photo does not.
    { 0, 0, 0, 2, 26 },
    // Photo has mismatching device id.
    { 0, 3, 0, 0, 0 },
    // Episode has mismatching device id.
    { 0, 0, 0, 3, 0 },
    // Photo and episode have mismatching device id.
    { 0, 3, 0, 4, 0 },
    // Photo and episode have matching device id.
    { 0, 4, 0, 4, 38 },
  };

  state_.SetUserId(1);
  state_.SetDeviceId(2);

  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    {
      // Create our episode containing a single photo.
      PhotoHandle ph = NewPhoto(kNow + kDay * i, 0, 0);
      EpisodeHandle eh = NewEpisode(ph->timestamp());
      eh->Lock();
      if (kTestData[i].episode_device_id) {
        eh->mutable_id()->set_server_id(
            EncodeEpisodeId(kTestData[i].episode_device_id,
                            eh->id().local_id(), 0));
      }
      eh->AddPhoto(ph->id().local_id());
      if (kTestData[i].episode_user_id > 0) {
        eh->set_user_id(kTestData[i].episode_user_id);
      }
      SaveEpisode(eh);
    }

    // Create a new photo and verify matching it to an episode meets are
    // expectation.
    PhotoHandle ph = NewPhoto(kNow + kDay * i, 0, 0);
    if (kTestData[i].photo_device_id) {
      ph->mutable_id()->set_server_id(
          EncodePhotoId(kTestData[i].photo_device_id,
                        ph->id().local_id(), 0));
    }
    if (kTestData[i].photo_user_id > 0) {
      ph->set_user_id(kTestData[i].photo_user_id);
    }
    EpisodeHandle eh = state_.episode_table()->MatchPhotoToEpisode(ph, state_.db());
    const int64_t episode_id = eh.get() ? eh->id().local_id() : 0;
    ASSERT_EQ(kTestData[i].expected_episode_id, episode_id) << ": " << i;
  }
}

TEST_F(EpisodeTableTest, TimeRange) {
  const WallTime kNow = 1343077044;   // 07/23/12 16:57:24 EST
  bool tz_set = false;
  string orig_tz;
  if (getenv("TZ")) {
    tz_set = true;
    orig_tz = getenv("TZ");
  }
  setenv("TZ", "America/New_York", 1);
  tzset();

  EpisodeHandle e = NewEpisode();
  WallTime earliest, latest;
  EXPECT(!e->GetTimeRange(&earliest, &latest));

  // Add single photo.
  PhotoHandle ph = NewPhoto(kNow, 0, 0);
  e->Lock();
  e->AddPhoto(ph->id().local_id());
  SaveEpisode(e);
  EXPECT(e->GetTimeRange(&earliest, &latest));
  EXPECT_EQ(earliest, kNow);
  EXPECT_EQ(latest, kNow);
  EXPECT_EQ("Mon, Jul 23", e->FormatTimeRange(false));
  EXPECT_EQ("4:57p", e->FormatTimeRange(true));

  // Add photo within same minute.
  ph = NewPhoto(kNow + 20, 0, 0);
  e->Lock();
  e->AddPhoto(ph->id().local_id());
  SaveEpisode(e);
  EXPECT(e->GetTimeRange(&earliest, &latest));
  EXPECT_EQ(earliest, kNow);
  EXPECT_EQ(latest, kNow + 20);
  EXPECT_EQ("Mon, Jul 23", e->FormatTimeRange(false));
  EXPECT_EQ("4:57p", e->FormatTimeRange(true));

  // Add photo two minutes later.
  ph = NewPhoto(kNow + 120, 0, 0);
  e->Lock();
  e->AddPhoto(ph->id().local_id());
  SaveEpisode(e);
  EXPECT(e->GetTimeRange(&earliest, &latest));
  EXPECT_EQ(earliest, kNow);
  EXPECT_EQ(latest, kNow + 120);
  EXPECT_EQ("Mon, Jul 23", e->FormatTimeRange(false));
  EXPECT_EQ("4:57p", e->FormatTimeRange(true));

  // Add photo next day in AM.
  ph = NewPhoto(kNow + 60 * 60 * 8, 0, 0);
  e->Lock();
  e->AddPhoto(ph->id().local_id());
  SaveEpisode(e);
  EXPECT(e->GetTimeRange(&earliest, &latest));
  EXPECT_EQ(earliest, kNow);
  EXPECT_EQ(latest, kNow + 60 * 60 * 8);
  EXPECT_EQ("Tue, Jul 24", e->FormatTimeRange(false));
  EXPECT_EQ("4:57p", e->FormatTimeRange(true));

  if (tz_set) {
    setenv("TZ", orig_tz.c_str(), 1);
  } else {
    unsetenv("TZ");
  }
  tzset();
}

TEST_F(EpisodeTableTest, DeletePhotoImages) {
  // Create a photo and add a local image to it.
  PhotoHandle p = NewPhoto();
  WriteLocalImage(PhotoFilename(p->id().local_id(), 120), "thumbnail");
  EXPECT_EQ(Format("<%d-0120.jpg>", p->id().local_id()).str,
            ListLocalImages());

  // Add the photo to a bunch of episodes.
  EpisodeHandle episodes[5];
  for (int i = 0; i < ARRAYSIZE(episodes); ++i) {
    episodes[i] = NewEpisode();
    episodes[i]->Lock();
    episodes[i]->AddPhoto(p->id().local_id());
    SaveEpisode(episodes[i]);
  }

  // Remove the photo from the episodes. The image will get deleted when the
  // photo is removed from the last episode.
  for (int i = 0; i < ARRAYSIZE(episodes); ++i) {
    EXPECT_EQ(Format("<%d-0120.jpg>", p->id().local_id()).str,
              ListLocalImages());
    episodes[i]->Lock();
    episodes[i]->RemovePhoto(p->id().local_id());
    SaveEpisode(episodes[i]);
  }

  EXPECT_EQ("<>", ListLocalImages());
}

TEST_F(EpisodeTableTest, FullText) {
  EpisodeHandle e1 = NewEpisode();
  e1->Lock();
  PhotoHandle p1 = NewPhoto();
  p1->Lock();
  p1->mutable_placemark()->set_country("USA");
  p1->mutable_placemark()->set_state("New York");
  p1->SaveAndUnlock(state_.db());
  e1->AddPhoto(p1->id().local_id());
  SaveEpisode(e1);
  EpisodeHandle e2 = NewEpisode();
  e2->Lock();
  PhotoHandle p2 = NewPhoto();
  p2->Lock();
  p2->mutable_placemark()->set_country("New Zealand");
  p2->mutable_placemark()->set_locality("Auckland");
  p2->SaveAndUnlock(state_.db());
  e2->AddPhoto(p2->id().local_id());
  SaveEpisode(e2);

  EXPECT_EQ(Search("new"), vector<int64_t>(L(e1->id().local_id(), e2->id().local_id())));
  EXPECT_EQ(Search("york"), vector<int64_t>(L(e1->id().local_id())));
  EXPECT_EQ(Search("zealand"), vector<int64_t>(L(e2->id().local_id())));
}

// Only run the Perf test on actual devices as the numbers it spits out are
// meaningless on the simulator.
#if !(TARGET_IPHONE_SIMULATOR)

TEST_F(EpisodeTableTest, Perf) {
  const int kEpisodes = 100000;
  const int kHour = 60 * 60;
  const int kYear = 365 * 24 * kHour;
  const int kNow = WallTime_Now();

  Random r(static_cast<unsigned>(WallTime_Now()));
  WallTimer timer;

  for (int i = 0; i < kEpisodes; ++i) {
    DBHandle updates = state_.NewDBTransaction();
    EpisodeHandle e = state_.episode_table()->NewContent(updates);
    // Randomly choose a timestamp in the past year.
    e->set_timestamp(kNow - kYear + r(kYear));

    PhotoHandle p = state_.photo_table()->NewContent(updates);
    p->mutable_episode_id()->CopyFrom(e->id());
    // Randomly choose a timestamp within 1 hour of the episode timestamp.
    p->set_timestamp(e->timestamp() + r(2 * kHour) - kHour);
    e->AddPhoto(p->id().local_id());
    p->SaveAndUnlock(updates);

    e->SaveAndUnlock(updates);
    updates->Commit();
  }

  // NOTE(pmattis): perf: creation: 100000 episodes, 0.452 ms/episode
  printf("perf: creation: %d episodes, %.03f ms/episode\n",
         kEpisodes, timer.Milliseconds() / kEpisodes);

  // Close and reopen the database to ensure nothing is cached.
  state_.db()->Close();
  CHECK(state_.db()->Open(1024 * 1024));

  timer.Restart();

  int count = 0;
  for (ScopedPtr<EpisodeTable::EpisodeIterator> iter(
           state_.episode_table()->NewEpisodeIterator(0, false, state_.db()));
       !iter->done();
       iter->Next()) {
    ++count;
  }

  // NOTE(pmattis): perf: iteration: 100000 episodes, 626.6 ms
  printf("perf: iteration: %d episodes, %.01f ms\n",
         count, timer.Milliseconds());
}

#endif // !(TARGET_IPHONE_SIMULATOR)

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
