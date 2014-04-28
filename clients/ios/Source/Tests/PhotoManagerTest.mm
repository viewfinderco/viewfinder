// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "FileUtils.h"
#import "PathUtils.h"
#import "PhotoDuplicateQueue.h"
#import "PhotoManager.h"
#import "PhotoStorage.h"
#import "Server.pb.h"
#import "StringUtils.h"
#import "TestAssets.h"
#import "Testing.h"
#import "TestUtils.h"

namespace {

class TestEnv : public TestUIAppState {
 public:
  TestEnv(const string& dir)
      : TestUIAppState(dir),
        assets_manager_([[AssetsManager alloc] initWithState:this]),
        network_up_(false),
        network_wifi_(false) {
  }

  ~TestEnv() {
    [assets_manager_ stop];
  }

  TestAssets* test_assets() { return &test_assets_; }

  virtual void AssetForKey(const string& key,
                           ALAssetsLibraryAssetForURLResultBlock result,
                           ALAssetsLibraryAccessFailureBlock failure) {
    Slice url, fingerprint;
    DecodeAssetKey(key, &url, &fingerprint);
    [test_assets_.library() assetForURL:NewNSURL(url)
                            resultBlock:result
                           failureBlock:failure];
  }

  virtual void AddAsset(NSData* data, NSDictionary* metadata,
                        void (^done)(string asset_url, string asset_key)) {
    [assets_manager_ addAsset:data metadata:metadata callback:done];
  }

  virtual void DeleteAsset(const string& key) {
    Slice url, fingerprint;
    DecodeAssetKey(key, &url, &fingerprint);
    test_assets_.Delete(NewNSURL(url));
  }

  void set_network_up(bool v) { network_up_ = v; }
  virtual bool network_up() const { return network_up_; }

  void set_network_wifi(bool v) { network_wifi_ = v; }
  virtual bool network_wifi() const { return network_wifi_; }

  virtual AssetsManager* assets_manager() const { return assets_manager_; }

 private:
  AssetsManager* assets_manager_;
  TestAssets test_assets_;
  bool network_up_;
  bool network_wifi_;
};

class PhotoManagerTest : public Test {
 protected:
  PhotoManagerTest()
      : env_(dir()) {
  }

  int64_t NewViewfinderPhoto(WallTime timestamp) {
    PhotoMetadata m;
    m.set_timestamp(timestamp);
    m.set_aspect_ratio(640.0 / 852.0);
    return photo_manager()->NewViewfinderPhoto(
        m, ReadFileToData(MainBundlePath("test-photo.jpg")));
  }

  void GenerateViewfinderImages(int64_t photo_id) {
    Barrier* barrier = new Barrier(1);
    photo_manager()->LoadViewfinderImages(
        photo_id, db(), ^(bool success) {
          barrier->Signal();
        });
    barrier->Wait();
    delete barrier;
  }

  void SimulateOKNetwork() {
    // Simulate an ok network.
    env_.set_network_up(true);
    env_.set_network_wifi(true);
  }

  // void ProcessQueryUpdates(const string& query_updates_json) {
  //   QueryUpdatesResponse r;
  //   ASSERT(ParseQueryUpdatesResponse(&r, query_updates_json));
  //   photo_manager()->ProcessQueryUpdates(r);
  // }

  // void ProcessGetMetadata(const string& get_metadata_json) {
  //   GetMetadataResponse r;
  //   ASSERT(ParseGetMetadataResponse(
  //              &r, get_metadata_json,
  //              photo_manager()->update_photo_ids(),
  //              photo_manager()->update_episode_ids()));
  //   photo_manager()->ProcessGetMetadata(r);
  // }

  const DBHandle& db() { return env_.db(); }
  NetworkQueue* net_queue() { return env_.net_queue(); }
  PhotoDuplicateQueue* photo_duplicate_queue() { return env_.photo_duplicate_queue(); }
  PhotoManager* photo_manager() { return env_.photo_manager(); }
  PhotoTable* photo_table() { return env_.photo_table(); }

 protected:
  TestEnv env_;
};

TEST_F(PhotoManagerTest, NewViewfinderPhoto) {
  // Add a new viewfinder photo.
  const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());
  // ASSERT_EQ(1, photo_manager()->num_photos());
  // ASSERT_EQ(1, photo_manager()->num_episodes());

  // Verify the photo can be retrieved.
  Barrier* barrier = new Barrier(1);
  const float kSize = 240;
  photo_manager()->LoadLocalPhoto(
      photo_id, CGSizeMake(kSize, kSize), ^(Image image){
        const float min_dim = kSize;
        const float max_dim = kMediumSize;
        EXPECT_GE(max_dim, image.width());
        EXPECT_LE(min_dim, image.width());
        EXPECT_GE(max_dim, image.height());
        EXPECT_LE(min_dim, image.height());
        barrier->Signal();
      });
  barrier->Wait();
  delete barrier;
}

TEST_F(PhotoManagerTest, NewAssetPhoto) {
  // Add a new assets photo.
  NSURL* url = env_.test_assets()->Add();
  ALAsset* asset = env_.test_assets()->Lookup(url);
  const int64_t photo_id = photo_manager()->NewAssetPhoto(
      asset, DBFormat::asset_key(ToString(url)), [asset thumbnail]);
  ASSERT_NE(0, photo_id);
  // ASSERT_EQ(1, photo_manager()->num_photos());
  // ASSERT_EQ(1, photo_manager()->num_episodes());

  {
    // Verify the thumbnail can be retrieved.
    Barrier* barrier = new Barrier(1);
    photo_manager()->LoadLocalThumbnail(
        photo_id, ^(Image image) {
          EXPECT_GE(kThumbnailSize, image.width());
          EXPECT_GE(kThumbnailSize, image.height());
          barrier->Signal();
        });
    barrier->Wait();
    delete barrier;
  }

  {
    // Verify the photo can be retrieved.
    Barrier* barrier = new Barrier(1);
    const float kSize = 240;
    photo_manager()->LoadLocalPhoto(
        photo_id, CGSizeMake(kSize, kSize), ^(Image image) {
          const float min_dim = kSize;
          const float max_dim = kMediumSize;
          EXPECT_GE(max_dim, image.width());
          EXPECT_LE(min_dim, image.width());
          EXPECT_GE(max_dim, image.height());
          EXPECT_LE(min_dim, image.height());
          barrier->Signal();
        });
    barrier->Wait();
    delete barrier;
  }
}

TEST_F(PhotoManagerTest, DuplicatePhoto) {
  // Add a new asset photo.
  NSURL* url1 = env_.test_assets()->Add();
  ALAsset* asset1 = env_.test_assets()->Lookup(url1);
  const int64_t photo_id1 = photo_manager()->NewAssetPhoto(
      asset1, DBFormat::asset_key(ToString(url1)), [asset1 thumbnail]);
  ASSERT_NE(0, photo_id1);

  GenerateViewfinderImages(photo_id1);

  // Add the same photo again.
  NSURL* url2 = env_.test_assets()->Add();
  ALAsset* asset2 = env_.test_assets()->Lookup(url2);
  const int64_t photo_id2 = photo_manager()->NewAssetPhoto(
      asset2, DBFormat::asset_key(ToString(url2)), [asset2 thumbnail]);
  ASSERT_NE(0, photo_id2);

  // Wait for duplicate processing to finish.
  photo_duplicate_queue()->Drain();

  // Verify the duplicate was deleted and its asset key was added to the
  // original.
  PhotoHandle h1 = photo_table()->LoadPhoto(photo_id1, db());
  PhotoHandle h2 = photo_table()->LoadPhoto(photo_id2, db());
  ASSERT_EQ(2, h1->asset_keys_size());
  ASSERT(!h2.get());
}

TEST_F(PhotoManagerTest, NotDuplicatePhoto) {
  // Add a new asset photo.
  NSURL* url1 = env_.test_assets()->AddTextImage("hello.");
  ALAsset* asset1 = env_.test_assets()->Lookup(url1);
  const int64_t photo_id1 = photo_manager()->NewAssetPhoto(
      asset1, DBFormat::asset_key(ToString(url1)), [asset1 thumbnail]);
  ASSERT_NE(0, photo_id1);

  GenerateViewfinderImages(photo_id1);

  // Add a slightly different photo (trailing comma vs period).
  NSURL* url2 = env_.test_assets()->AddTextImage("hello,");
  ALAsset* asset2 = env_.test_assets()->Lookup(url2);
  // Note, the perceptual fingerprints for these two images match because the
  // square thumbnails are identical due to the cropping.
  const int64_t photo_id2 = photo_manager()->NewAssetPhoto(
      asset2, DBFormat::asset_key(ToString(url2)), [asset2 thumbnail]);
  ASSERT_NE(0, photo_id2);

  // Wait for duplicate processing to finish.
  photo_duplicate_queue()->Drain();

  // Verify both photos still exist.
  PhotoHandle h1 = photo_table()->LoadPhoto(photo_id1, db());
  PhotoHandle h2 = photo_table()->LoadPhoto(photo_id2, db());
  ASSERT_EQ(1, h1->asset_keys_size());
  ASSERT_EQ(1, h2->asset_keys_size());
  ASSERT_EQ(0, h2->candidate_duplicates_size());
}

TEST_F(PhotoManagerTest, CopyToAssetsLibrary) {
  // Add a new viewfinder photo.
  const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());
  ASSERT_NE(0, photo_id);

  // Copy it to the assets library.
  Barrier* barrier = new Barrier(1);
  __block string asset_key;
  dispatch_main(^{
      photo_manager()->CopyToAssetsLibrary(photo_id, ^(string asset_url) {
          EXPECT(!asset_url.empty());
          asset_key = EncodeAssetKey(asset_url, "");
          barrier->Signal();
        });
    });

  barrier->Wait();
  delete barrier;

  // Try to load it.  PhotoManager will pull from our local cache instead of
  // the asset library, so talk to the asset library directly.
  barrier = new Barrier(1);
  env_.AssetForKey(asset_key,
                   ^(ALAsset* asset) {
                     barrier->Signal();
                   },
                   ^(NSError* error) {
                     LOG("Error loading asset: %s", error);
                     EXPECT(false);
                     barrier->Signal();
                   });
  barrier->Wait();
  delete barrier;

  env_.DeleteAsset(asset_key);
}

TEST_F(PhotoManagerTest, AttachAssetFingerprintFromServer) {
  // Create a photo and give it a server id.
  const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());
  ASSERT_NE(0, photo_id);
  {
    PhotoHandle ph = env_.photo_table()->LoadPhoto(photo_id, env_.db());
    ph->Lock();
    ph->mutable_id()->set_server_id("p123");
    ph->SaveAndUnlock(env_.db());
  }

  // Process a response from the server that gives this photo an asset fingerprint.
  QueryEpisodesResponse r;
  vector<EpisodeSelection> v;
  const string kResponseData =
      "{\n"
      "  \"episodes\": [\n"
      "    {\n"
      "      \"photos\": [\n"
      "        {\n"
      "          \"photo_id\": \"p123\",\n"
      "          \"asset_keys\": [\n"
      "            \"a/#abcd\"\n"
      "          ]\n"
      "        }\n"
      "      ]\n"
      "    }\n"
      "  ]\n"
      "}";
  ASSERT(ParseQueryEpisodesResponse(&r, &v, 100, kResponseData));
  net_queue()->ProcessQueryEpisodes(r, v, env_.db());

  // Load the photo and see that the asset fingerprint was applied.
  {
    PhotoHandle ph = env_.photo_table()->LoadPhoto(photo_id, env_.db());
    ASSERT(ph.get());
    ASSERT_EQ(ph->asset_fingerprints_size(), 1);
    ASSERT_EQ(ph->asset_fingerprints(0), "abcd");
  }

  // The photo can now be queried by asset key.
  {
    PhotoHandle ph = env_.photo_table()->LoadAssetPhoto("a/#abcd", env_.db());
    ASSERT(ph.get());
    ASSERT_EQ(ph->id().local_id(), photo_id);
  }
}

TEST_F(PhotoManagerTest, MatchServerPhotoByAssetFingerprint) {
  // Create a local photo with an asset fingerprint but no server id.
  const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());
  ASSERT_NE(0, photo_id);
  {
    PhotoHandle ph = env_.photo_table()->LoadPhoto(photo_id, env_.db());
    ph->Lock();
    ph->add_asset_fingerprints("abcd");
    ph->SaveAndUnlock(env_.db());
  }

  // Process a response from the server that gives this photo a server id.
  QueryEpisodesResponse r;
  vector<EpisodeSelection> v;
  const string kResponseData =
      "{\n"
      "  \"episodes\": [\n"
      "    {\n"
      "      \"photos\": [\n"
      "        {\n"
      "          \"photo_id\": \"p123\",\n"
      "          \"asset_keys\": [\n"
      "            \"a/#abcd\"\n"
      "          ]\n"
      "        }\n"
      "      ]\n"
      "    }\n"
      "  ]\n"
      "}";
  ASSERT(ParseQueryEpisodesResponse(&r, &v, 100, kResponseData));
  net_queue()->ProcessQueryEpisodes(r, v, env_.db());

  // Load the photo and see that the server id was applied instead of creating a new photo.
  {
    PhotoHandle ph = env_.photo_table()->LoadPhoto(photo_id, env_.db());
    ASSERT(ph.get());
    ASSERT_EQ(ph->id().server_id(), "p123");
  }

  // The photo can now be queried by server id.
  {
    PhotoHandle ph = env_.photo_table()->LoadPhoto("p123", env_.db());
    ASSERT(ph.get());
    ASSERT_EQ(ph->id().local_id(), photo_id);
  }

}

// TEST_F(PhotoManagerTest, QueryUpdatesKey) {
//   EXPECT_EQ(string(), photo_manager()->query_updates_key());

//   QueryUpdatesResponse r;
//   photo_manager()->ProcessQueryUpdates(r);
//   EXPECT_EQ(string(), photo_manager()->query_updates_key());

//   r.set_last_key("foo");
//   photo_manager()->ProcessQueryUpdates(r);
//   EXPECT_EQ("foo", photo_manager()->query_updates_key());

//   r.clear_last_key();
//   photo_manager()->ProcessQueryUpdates(r);
//   EXPECT_EQ("foo", photo_manager()->query_updates_key());

//   r.set_last_key("bar");
//   photo_manager()->ProcessQueryUpdates(r);
//   EXPECT_EQ("bar", photo_manager()->query_updates_key());

//   EXPECT_EQ("bar", env_.db()->Get<string>("m/query_updates"));
// }

// TEST_F(PhotoManagerTest, QueryUpdatesShare) {
//   env_.set_network_up(true);
//   env_.set_network_wifi(true);

//   {
//     const string kQueryUpdatesResponse =
//         "{\n"
//         "  \"photos\" : [\n"
//         "    {\n"
//         "      \"labels\": \"+given,+repost,+download\",\n"
//         "      \"photo_id\": \"pg2uJzmHO2k\",\n"
//         "      \"sharing_user_id\": 16\n"
//         "    }\n"
//         "  ]\n"
//         "}\n";
//     ProcessQueryUpdates(kQueryUpdatesResponse);
//   }

//   ASSERT_EQ(1, photo_manager()->update_photo_ids().size());
//   ASSERT_EQ("pg2uJzmHO2k", *photo_manager()->update_photo_ids().begin());
//   ASSERT(photo_manager()->update_episode_ids().empty());
//   ASSERT_EQ(0, photo_manager()->update_episode_ids().size());

//   {
//     const string kGetMetadataResponse =
//         "{\n"
//         "  \"photos\": [\n"
//         "    {\n"
//         "      \"aspect_ratio\": 0.75,\n"
//         "      \"episode_id\": \"eg2udYXHP-V\",\n"
//         "      \"full_get_url\": \"full\",\n"
//         "      \"location\": {\n"
//         "        \"accuracy\": 0.0,\n"
//         "        \"latitude\": 41.035,\n"
//         "        \"longitude\": -72.2105\n"
//         "      },\n"
//         "      \"med_get_url\": \"med\",\n"
//         "      \"photo_id\": \"pg2uJzmHO2k\",\n"
//         "      \"placemark\": {\n"
//         "        \"country\": \"United States\",\n"
//         "        \"iso_country_code\": \"US\",\n"
//         "        \"locality\": \"East Hampton\",\n"
//         "        \"state\": \"New York\",\n"
//         "        \"sublocality\": \"The Hamptons\",\n"
//         "        \"subthoroughfare\": \"20\",\n"
//         "        \"thoroughfare\": \"Hedges Banks Dr\"\n"
//         "      },\n"
//         "      \"timestamp\": 1338075904.99,\n"
//         "      \"tn_get_url\": \"tn\",\n"
//         "      \"user_id\": 16\n"
//         "    }\n"
//         "  ]\n"
//         "}\n";
//     ProcessGetMetadata(kGetMetadataResponse);
//   }

//   ASSERT_EQ(1, photo_manager()->num_queued_photos());
//   ASSERT_EQ(0, photo_manager()->num_queued_uploads());
//   ASSERT_EQ(1, photo_manager()->num_queued_downloads());
//   ASSERT_EQ(1, photo_manager()->update_episode_ids().size());
//   ASSERT_EQ("eg2udYXHP-V", *photo_manager()->update_episode_ids().begin());
// }

// TEST_F(PhotoManagerTest, AddPhotoToEpisodeError) {
//   env_.set_network_up(true);
//   env_.set_network_wifi(true);
//   env_.set_user_id(1);

//   struct {
//     string server_id;
//     int64_t photo_user_id;
//     int64_t episode_user_id;
//   } kTestPhotos[] = {
//     // Mismatched photo/episode user id. Photo metadata should be queued for
//     // retrieval.
//     { "a", 1, 2 },
//     // Mismatched photo/episode user id. Photo should be added to a new episode.
//     { "", 1, 2 },
//     // Mismatched photo/episode user id. Photo should be quarantined.
//     { "", 2, 3 },
//     // Non-existant episode. Photo metadata should be queued for retrieval.
//     { "b", 1, -1 },
//     // Non-existant episode. Photo should be added to a new episode.
//     { "", 1, -1 },
//     // Non-existant episode. Photo should be quarantined.
//     { "", 2, -1 },
//   };

//   for (int i = 0; i < ARRAYSIZE(kTestPhotos); ++i) {
//     PhotoMetadata p;
//     p.mutable_id()->set_local_id(i + 1);
//     if (!kTestPhotos[i].server_id.empty()) {
//       p.mutable_id()->set_server_id(kTestPhotos[i].server_id);
//     }
//     p.mutable_episode_id()->set_local_id(i + 1);
//     p.set_aspect_ratio(1);
//     p.set_label_owned(true);
//     p.set_timestamp(i * 24 * 60 * 60);
//     p.set_user_id(kTestPhotos[i].photo_user_id);
//     env_.db()->PutProto(DBFormat::photo_key(p.id().local_id()), p);

//     if (kTestPhotos[i].episode_user_id > 0) {
//       EpisodeMetadata e;
//       e.mutable_id()->set_local_id(i + 1);
//       e.set_user_id(kTestPhotos[i].episode_user_id);
//       env_.db()->PutProto(DBFormat::episode_key(e.id().local_id()), e);
//     }
//   }

//   env_.db()->Put(DBFormat::metadata_key("next_event_id"), 10);
//   photo_manager()->EnsureInit();
//   env_.network_changed()->Run();

//   // Verify the two photos with server ids were queued for download.
//   ASSERT_EQ(2, photo_manager()->update_photo_ids().size());
//   ASSERT(ContainsKey(photo_manager()->update_photo_ids(), "a"));
//   ASSERT(ContainsKey(photo_manager()->update_photo_ids(), "b"));

//   // Verify the two quarantined photos.
//   const PhotoManager::PhotoData* p = FindPtrOrNull(photo_manager()->photos(), 3);
//   ASSERT(p->metadata.label_error());
//   ASSERT(!p->episode);
//   p = FindPtrOrNull(photo_manager()->photos(), 6);
//   ASSERT(p->metadata.label_error());
//   ASSERT(!p->episode);

//   // Verify the two photos that were added to new episodes.
//   p = FindPtrOrNull(photo_manager()->photos(), 2);
//   ASSERT_EQ(10, p->metadata.episode_id().local_id());
//   ASSERT(p->episode);
//   ASSERT_EQ(10, p->episode->metadata.id().local_id());
//   p = FindPtrOrNull(photo_manager()->photos(), 5);
//   ASSERT_EQ(11, p->metadata.episode_id().local_id());
//   ASSERT(p->episode);
//   ASSERT_EQ(11, p->episode->metadata.id().local_id());
// }

// TEST_F(PhotoManagerTest, QueueMetadataUpload) {
//   // Add a new viewfinder photo.
//   const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());
//   ASSERT_NE(0, photo_id);
//   ASSERT_EQ(1, photo_manager()->num_photos());
//   ASSERT_EQ(0, photo_manager()->num_queued_photos());
//   ASSERT_EQ(0, photo_manager()->num_queued_uploads());
//   ASSERT_EQ(0, photo_manager()->num_queued_downloads());
//   ASSERT_EQ(1, photo_manager()->num_episodes());

//   SimulateOKNetwork();

//   // Wait for the metadata upload to be queued.
//   WaitForNetworkDispatch();

//   // Verify a metadata upload was queued.
//   ASSERT_EQ(1, photo_manager()->num_queued_photos());
//   ASSERT_EQ(1, photo_manager()->num_queued_uploads());
//   const PhotoManager::MetadataUpload* u =
//       photo_manager()->queued_metadata_upload();
//   ASSERT(u != NULL);
//   ASSERT_EQ(1, u->photos.size());
//   ASSERT_EQ(photo_id, u->photos[0]->metadata.id().local_id());
//   ASSERT(u->photos[0]->metadata.has_images());
//   ASSERT(u->photos[0]->metadata.images().has_tn());
//   ASSERT(u->photos[0]->metadata.images().has_med());
//   ASSERT(u->photos[0]->metadata.images().has_full());
//   ASSERT(u->photos[0]->metadata.images().has_orig());
//   const string bytes = ReadFileToString(MainBundlePath("test-photo.jpg"));
//   ASSERT_EQ(bytes.size(), u->photos[0]->metadata.images().orig().size());
//   ASSERT_EQ(MD5(bytes), u->photos[0]->metadata.images().orig().md5());
// }

// TEST_F(PhotoManagerTest, QueueMetadataUploadError) {
//   const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());
//   ASSERT_NE(0, photo_id);
//   ASSERT_EQ(1, photo_manager()->num_photos());
//   ASSERT_EQ(0, photo_manager()->num_queued_photos());
//   ASSERT_EQ(0, photo_manager()->num_queued_uploads());
//   ASSERT_EQ(0, photo_manager()->num_queued_downloads());
//   ASSERT_EQ(1, photo_manager()->num_episodes());

//   // Remove the underlying photo. This should cause the photo to be quarantined
//   // on metadata upload.
//   FileRemove(Format("%s/%d-orig.jpg", env_.photo_dir(), photo_id));

//   SimulateOKNetwork();

//   // Wait for the metadata upload.
//   WaitForNetworkDispatch();

//   // Verify no metadata upload was queued.
//   ASSERT_EQ(0, photo_manager()->num_queued_photos());
//   ASSERT_EQ(0, photo_manager()->num_queued_uploads());

//   // Verify the photo was quarantined.
//   const PhotoManager::PhotoData* p =
//       FindPtrOrNull(photo_manager()->photos(), photo_id);
//   ASSERT(p->metadata.label_error());
//   ASSERT(!p->episode);
// }

// TEST_F(PhotoManagerTest, MultipleViewfinderPhotos) {
//   // Create two Viewfinder photos separated by a day.
//   NewViewfinderPhoto(WallTime_Now());
//   NewViewfinderPhoto(WallTime_Now() + 24*60*60);
//   ASSERT_EQ(2, photo_manager()->num_photos());
//   ASSERT_EQ(2, photo_manager()->num_episodes());
// }

// // Make sure that unknown labels in a photo's metadata are processed
// // when EnsureInit is called. Any unknown labels which are now
// // recognized will be added to the predefined protobuf booleans.
// TEST_F(PhotoManagerTest, VerifyUnknownLabelProcessing) {
//   // Create two Viewfinder photos separated by a day.
//   PhotoMetadata pm;
//   pm.mutable_id()->set_local_id(1);
//   pm.set_aspect_ratio(1.0);
//   pm.set_label_owned(true);
//   pm.add_unknown_labels("+reshared");
//   pm.add_unknown_labels("-repost");
//   pm.add_unknown_labels("+unknown");
//   const string key = DBFormat::photo_key(pm.id().local_id());
//   env_.db()->PutProto(key, pm);
//   photo_manager()->EnsureInit();

//   pm.Clear();
//   env_.db()->GetProto(key, &pm);
//   ASSERT(pm.has_label_reshared());
//   ASSERT(pm.label_reshared());
//   ASSERT(pm.has_label_repost());
//   ASSERT(!pm.label_repost());
//   ASSERT_EQ(pm.unknown_labels_size(), 1);
//   ASSERT_EQ(pm.unknown_labels(0), "+unknown");
// }

// TEST_F(PhotoManagerTest, VerifyPartialMetadata) {
//   // Partial metadata can be returned in the case of a user update for
//   // a shared photo. Typically, these are returned with
//   // "sharing_user_id", "photo_id", and "labels". The additional data
//   // is expected to be queried via /service/get_episodes. However, if
//   // the application is restarted, the incomplete metadatas are read
//   // in EnsureInit and should not be queued, but the photo id should
//   // be in update_photo_ids_.

//   // Create an incomplete photo metadata.
//   const string& kServerId = "pg01";
//   PhotoMetadata pm;
//   pm.mutable_id()->set_local_id(1);
//   pm.mutable_id()->set_server_id(kServerId);
//   pm.set_aspect_ratio(0.0);
//   pm.set_label_shared(true);
//   pm.set_label_repost(true);
//   pm.set_label_download(true);
//   const string key = DBFormat::photo_key(pm.id().local_id());
//   env_.db()->PutProto(key, pm);

//   // Create pending photo update.
//   const string update_key = DBFormat::photo_update_key(kServerId);
//   env_.db()->Put(update_key, Slice());

//   // Verify a metadata upload was queued.
//   photo_manager()->EnsureInit();
//   ASSERT(ContainsKey(photo_manager()->update_photo_ids(), kServerId));
//   ASSERT_EQ(1, photo_manager()->num_photos());
//   ASSERT_EQ(0, photo_manager()->num_queued_downloads());
// }

// TEST_F(PhotoManagerTest, LoadLocalThumbnail) {
//   // Create a viewfinder photo and verify that loading the thumbnail does not
//   // load an image larger than 120x120.
//   const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());
//   const float scale = [UIScreen mainScreen].scale;
//   Barrier* barrier = new Barrier(1);
//   Image* image = new Image;
//   photo_manager()->LoadLocalThumbnail(photo_id, image, ^{
//       ScopedPtr<Image> image_deleter(image);
//       ASSERT_LE(image->pixel_width(), 120);
//       ASSERT_LE(image->pixel_height(), 120);
//       ASSERT_EQ(image->scale(), scale);
//       barrier->Signal();
//     });
//   barrier->Wait();
//   delete barrier;
// }

// TEST_F(PhotoManagerTest, ViewfinderPhotoScale) {
//   // Create a viewfinder photo and verify that when it's loaded,
//   // the UIScreen scale factor is applied to the. This method
//   // is dependent on the scale of "test-image.jpg".
//   const int width = 320;
//   const int height = 480;
//   const float scale = [UIScreen mainScreen].scale;
//   const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());
//   CGSize size = CGSizeMake(width, height);
//   Barrier* barrier = new Barrier(1);
//   Image* image = new Image;
//   photo_manager()->LoadLocalPhoto(photo_id, size, image, ^{
//       ScopedPtr<Image> image_deleter(image);
//       ASSERT_GE(image->pixel_width(), width);
//       ASSERT_GE(image->pixel_height(), height);
//       ASSERT_EQ(image->scale(), scale);
//       barrier->Signal();
//     });
//   barrier->Wait();
//   delete barrier;
// }

// TEST_F(PhotoManagerTest, QueueUnshareUpload) {
//   // Create two photos in different episodes (1 day later separates them).
//   const int64_t photo_id1 = NewViewfinderPhoto(WallTime_Now());
//   const int64_t photo_id2 = NewViewfinderPhoto(WallTime_Now() + 24*60*60);
//   photo_manager()->UnsharePhotos(L(photo_id1, photo_id2));
//   SimulateOKNetwork();

//   // Verify a metadata upload was queued.
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_metadata_upload());
//   ASSERT_EQ(2, photo_manager()->num_queued_photos());
//   ASSERT_EQ(2, photo_manager()->num_queued_uploads());
//   ASSERT_EQ(1, photo_manager()->queued_metadata_upload()->photos.size());
//   PhotoManager::PhotoData* photo = photo_manager()->queued_metadata_upload()->photos[0];
//   int64_t photo_id = photo->metadata.id().local_id();
//   SimulateMetadataUpload("e000000001", L(photo_id));

//   // As soon as the first share goes through, its unshare will occur.
//   WaitForNetworkDispatch();
//   ASSERT(!photo_manager()->queued_metadata_upload());
//   ASSERT(photo_manager()->queued_unshare_upload());
//   ASSERT_EQ(1, photo_manager()->queued_unshare_upload()->photos.size());
//   photo = photo_manager()->queued_unshare_upload()->photos[0];
//   ASSERT_EQ(photo_id, photo->metadata.id().local_id());
//   photo_manager()->CommitQueuedUnshareUpload();

//   // Handle the second photo upload.
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_metadata_upload());
//   ASSERT(!photo_manager()->queued_unshare_upload());
//   ASSERT_EQ(1, photo_manager()->queued_metadata_upload()->photos.size());
//   photo = photo_manager()->queued_metadata_upload()->photos[0];
//   photo_id = photo->metadata.id().local_id();
//   SimulateMetadataUpload("e000000002", L(photo_id));

//   // Waiting for network dispatch should schedule the unshare.
//   WaitForNetworkDispatch();
//   ASSERT(!photo_manager()->queued_metadata_upload());
//   ASSERT(photo_manager()->queued_unshare_upload());
//   ASSERT_EQ(1, photo_manager()->queued_unshare_upload()->photos.size());
//   photo = photo_manager()->queued_unshare_upload()->photos[0];
//   ASSERT_EQ(photo_id, photo->metadata.id().local_id());
//   photo_manager()->CommitQueuedUnshareUpload();

//   // Verify that both unshares were sent.
//   ASSERT(!photo_manager()->queued_metadata_upload());
//   ASSERT(!photo_manager()->queued_unshare_upload());
// }

// TEST_F(PhotoManagerTest, ShareDeletedPhoto) {
//   env_.set_network_up(true);
//   env_.set_network_wifi(true);

//   // Add 2 photos, which should get placed in the same episode.
//   const int64_t photo_ids[2] = {
//     NewViewfinderPhoto(WallTime_Now()),
//     NewViewfinderPhoto(WallTime_Now()),
//   };
//   ASSERT_EQ(2, photo_manager()->num_photos());
//   ASSERT_EQ(1, photo_manager()->num_episodes());
//   ASSERT_EQ(2, photo_manager()->num_queued_uploads());

//   WaitForNetworkDispatch();

//   {
//     // Simulate the metadata being uploaded.
//     const string kUploadEpisodeResponse =
//         "{\n"
//         "  \"episode_id\" : \"eg2lB2YuT-F\",\n"
//         "  \"photos\" : [\n"
//         "    {\n"
//         "      \"photo_id\" : \"pg2lAIIuj0k\",\n"
//         "    },\n"
//         "    {\n"
//         "      \"photo_id\" : \"pg2lAVnul0k\",\n"
//         "    }\n"
//         "  ]\n"
//         "}\n";
//     CommitMetadataUpload(kUploadEpisodeResponse);
//   }

//   {
//     // Share the first photo.
//     ContactMetadata contact;
//     contact.set_user_id(2);
//     photo_manager()->SharePhotos(L(photo_ids[0]), L(contact));
//     ASSERT_EQ(2, photo_manager()->num_queued_uploads());
//     ASSERT_EQ(1, photo_manager()->num_queued_shares());
//   }

//   {
//     // Wait for the thumbnail and full uploads to be queued.
//     const PhotoManager::PhotoType kUploadTypes[] = {
//       PhotoManager::THUMBNAIL,
//       PhotoManager::FULL,
//     };
//     for (int i = 0; i < ARRAYSIZE(kUploadTypes); ++i) {
//       WaitForNetworkDispatch();
//       ASSERT(photo_manager()->queued_photo_upload() != NULL);
//       const PhotoManager::PhotoUpload* u = photo_manager()->queued_photo_upload();
//       ASSERT_EQ(kUploadTypes[i], u->type);
//       ASSERT_EQ(photo_ids[0], u->photo->metadata.id().local_id());
//       photo_manager()->CommitQueuedPhotoUpload(false);
//     }
//   }

//   // Wait for the share to be queued.
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_share_upload() != NULL);
//   ASSERT_EQ(1, photo_manager()->queued_share_upload()->photos.size());
//   ASSERT_EQ(1, photo_manager()->queued_share_upload()->contacts.size());

//   // Delete the first photo.
//   photo_manager()->DeletePhotos(L(photo_ids[0]));
//   ASSERT_EQ(0, photo_manager()->num_queued_shares());

//   // The share should still be queued, but have no photos in it.
//   ASSERT(photo_manager()->queued_share_upload() != NULL);
//   ASSERT_EQ(0, photo_manager()->queued_share_upload()->photos.size());
//   ASSERT_EQ(1, photo_manager()->queued_share_upload()->contacts.size());
//   photo_manager()->CommitQueuedShareUpload();

//   // Wait for the delete to be queued.
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_delete_upload() != NULL);
//   photo_manager()->CommitQueuedDeleteUpload();
//   ASSERT(photo_manager()->queued_delete_upload() == NULL);

//   {
//     // Simulate the resulting query updates.
//     const string kQueryUpdatesResponse =
//         "{\n"
//         "  \"photos\" : [\n"
//         "    {\n"
//         "      \"aspect_ratio\": 1,\n"
//         "      \"content_type\": \"image/jpeg\",\n"
//         "      \"episode_id\": \"eg2lB2YuT-F\",\n"
//         "      \"labels\": \"+owned\",\n"
//         "      \"photo_id\": \"pg2lAVnul0k\",\n"
//         "      \"timestamp\": 1338225788,\n"
//         "      \"user_id\": 1\n"
//         "    },\n"
//         "    {\n"
//         "      \"aspect_ratio\": 1,\n"
//         "      \"content_type\": \"image/jpeg\",\n"
//         "      \"episode_id\": \"eg2lB2YuT-F\",\n"
//         "      \"labels\": \"+owned\",\n"
//         "      \"photo_id\": \"pg2lAIIuj0k\",\n"
//         "      \"timestamp\": 1338225788,\n"
//         "      \"user_id\": 1\n"
//         "    },\n"
//         "    {\n"
//         "      \"labels\": \"-owned\",\n"
//         "      \"photo_id\": \"pg2lAVnul0k\"\n"
//         "    }\n"
//         "  ]\n"
//         "}\n";
//     ProcessQueryUpdates(kQueryUpdatesResponse);
//   }

//   // Even though the deleted photo was resurrected, it shouldn't have been
//   // added to an episode.
//   ASSERT_EQ(2, photo_manager()->num_photos());
//   ASSERT_EQ(1, photo_manager()->num_episodes());
//   ASSERT_EQ(1, photo_manager()->episodes().begin()->second.photos.size());

//   // The server will not return any info for the deleted photo, but
//   // ParseGetMetadataResponse will add a synthetic entry indicating the photo
//   // has been deleted. Since this is a server initiated deletion, the delete
//   // will be committed immediately.
//   ProcessGetMetadata("{ }");
//   ASSERT_EQ(1, photo_manager()->num_photos());
//   ASSERT_EQ(1, photo_manager()->num_episodes());
// }

// TEST_F(PhotoManagerTest, UserDeletePhotoNoServerId) {
//   SimulateOKNetwork();

//   // Delete a photo that has no server id. The photo should be deleted
//   // immediately as we know the server knows nothing about it.
//   const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());
//   photo_manager()->DeletePhotos(L(photo_id));
//   env_.network_ready()->Run();

//   ASSERT(!photo_manager()->queued_delete_upload());
//   ASSERT(!ContainsKey(photo_manager()->photos(), photo_id));
// }

// TEST_F(PhotoManagerTest, UserDeletePhotoHasServerId) {
//   SimulateOKNetwork();

//   // Delete a photo that has a server id. The photo should be queued for
//   // deletion to the server and the deletion only committed once the server
//   // responds.
//   const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());

//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_metadata_upload());
//   SimulateMetadataUpload("e000000001", L(photo_id));

//   photo_manager()->DeletePhotos(L(photo_id));
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_delete_upload() != NULL);
//   ASSERT_EQ(1, photo_manager()->queued_delete_upload()->photos.size());
//   const PhotoManager::PhotoData* p =
//       photo_manager()->queued_delete_upload()->photos[0];
//   ASSERT_EQ(photo_id, p->metadata.id().local_id());
//   ASSERT(ContainsKey(photo_manager()->photos(), photo_id));

//   photo_manager()->CommitQueuedDeleteUpload();
//   ASSERT(!ContainsKey(photo_manager()->photos(), photo_id));
// }

// TEST_F(PhotoManagerTest, ServerDeletePhoto) {
//   SimulateOKNetwork();

//   // Process a photo deletion from the server. Since the deletion came from the
//   // server, the photo should be deleted immediately.
//   const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());

//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_metadata_upload());
//   SimulateMetadataUpload("e000000001", L(photo_id));

//   {
//     // Simulate the deletion from the server.
//     const string kQueryUpdatesResponse =
//         Format("{\n"
//                "  \"photos\" : [\n"
//                "    {\n"
//                "      \"photo_id\": \"%s\",\n"
//                "      \"labels\": \"-owned,-given,-shared\",\n"
//                "    }\n"
//                "  ]\n"
//                "}\n", ServerPhotoId(photo_id));
//     ProcessQueryUpdates(kQueryUpdatesResponse);
//   }

//   env_.network_ready()->Run();

//   ASSERT(!photo_manager()->queued_delete_upload());
//   ASSERT(!ContainsKey(photo_manager()->photos(), photo_id));
// }

// TEST_F(PhotoManagerTest, StorageSettings) {
//   SimulateOKNetwork();
//   env_.set_cloud_storage(false);
//   env_.set_store_originals(false);

//   // Add a new photo. It should not be uploaded while cloud storage is
//   // disabled.
//   const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());
//   env_.network_ready()->Run();
//   ASSERT_EQ(0, photo_manager()->num_queued_photos());
//   ASSERT_EQ(0, photo_manager()->num_queued_uploads());

//   // Enable cloud storage and indicate the settings have changed.
//   env_.set_cloud_storage(true);
//   env_.settings_changed()->Run();
//   ASSERT_EQ(1, photo_manager()->num_queued_photos());
//   ASSERT_EQ(1, photo_manager()->num_queued_uploads());

//   // Wait for the photo to be queued and simulate the server response.
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_metadata_upload());
//   SimulateMetadataUpload("e000000001", L(photo_id));

//   // Wait for the various images to be uploaded.
//   const PhotoManager::PhotoType kUploadTypes[] = {
//     PhotoManager::THUMBNAIL,
//     PhotoManager::FULL,
//     PhotoManager::MEDIUM,
//   };
//   for (int i = 0; i < ARRAYSIZE(kUploadTypes); ++i) {
//     WaitForNetworkDispatch();
//     ASSERT(photo_manager()->queued_photo_upload());
//     ASSERT_EQ(kUploadTypes[i], photo_manager()->queued_photo_upload()->type);
//     photo_manager()->CommitQueuedPhotoUpload(false);
//   }
//   ASSERT_EQ(0, photo_manager()->num_queued_photos());
//   ASSERT_EQ(0, photo_manager()->num_queued_uploads());

//   // Enable storage of original photos and indicate the settings have changed.
//   env_.set_store_originals(true);
//   env_.settings_changed()->Run();
//   ASSERT_EQ(1, photo_manager()->num_queued_photos());
//   ASSERT_EQ(1, photo_manager()->num_queued_uploads());

//   // Wait for the original image upload to be queued.
//   ASSERT(!photo_manager()->queued_photo_upload());
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_photo_upload());
//   ASSERT_EQ(PhotoManager::ORIGINAL, photo_manager()->queued_photo_upload()->type);
// }

// TEST_F(PhotoManagerTest, BulkShare) {
//   // Verify that a share of 2 photos that haven't been uploaded results in a
//   // single share upload containing both photos.
//   SimulateOKNetwork();
//   env_.set_cloud_storage(false);
//   env_.set_store_originals(false);

//   // Add 2 photos, which should get placed in the same episode.
//   const WallTime now = WallTime_Now();
//   const vector<int64_t> photo_ids(
//       L(NewViewfinderPhoto(now),
//         NewViewfinderPhoto(now - 1)));
//   ASSERT_EQ(2, photo_manager()->num_photos());
//   ASSERT_EQ(1, photo_manager()->num_episodes());
//   ASSERT_EQ(0, photo_manager()->num_queued_uploads());

//   {
//     // Share both photos.
//     ContactMetadata contact;
//     contact.set_user_id(2);
//     photo_manager()->SharePhotos(photo_ids, L(contact));
//     ASSERT_EQ(2, photo_manager()->num_queued_uploads());
//     ASSERT_EQ(2, photo_manager()->num_queued_shares());
//   }

//   {
//     // Wait for the metadata upload to be queued. It should contain both photos.
//     WaitForNetworkDispatch();
//     ASSERT(photo_manager()->queued_metadata_upload() != NULL);
//     const PhotoManager::MetadataUpload* u =
//         photo_manager()->queued_metadata_upload();
//     ASSERT_EQ(2, u->photos.size());
//     SimulateMetadataUpload("e000000001", photo_ids);
//   }

//   // Both photos should be uploaded before the share.
//   for (int i = 0; i < photo_ids.size(); ++i) {
//     // Wait for the thumbnail and full uploads to be queued.
//     const PhotoManager::PhotoType kUploadTypes[] = {
//       PhotoManager::THUMBNAIL,
//       PhotoManager::FULL,
//     };
//     for (int j = 0; j < ARRAYSIZE(kUploadTypes); ++j) {
//       WaitForNetworkDispatch();
//       ASSERT(photo_manager()->queued_photo_upload() != NULL);
//       const PhotoManager::PhotoUpload* u = photo_manager()->queued_photo_upload();
//       ASSERT_EQ(kUploadTypes[j], u->type);
//       ASSERT_EQ(photo_ids[i], u->photo->metadata.id().local_id());
//       photo_manager()->CommitQueuedPhotoUpload(false);
//     }
//   }

//   {
//     // Wait for the share upload to be queued.
//     WaitForNetworkDispatch();
//     ASSERT(photo_manager()->queued_share_upload() != NULL);
//     const PhotoManager::ShareUpload* u = photo_manager()->queued_share_upload();
//     ASSERT_EQ(2, u->photos.size());
//     ASSERT_EQ(1, u->contacts.size());
//   }
// }

// TEST_F(PhotoManagerTest, BulkDelete) {
//   env_.set_store_originals(false);
//   SimulateOKNetwork();

//   // Verify that delete uploads are broken up into reasonable size chunks.
//   vector<int64_t> photo_ids(27, 0);
//   for (int i = 0; i < photo_ids.size(); ++i) {
//     photo_ids[i] = NewViewfinderPhoto(WallTime_Now());
//   }
//   ASSERT_EQ(photo_ids.size(), photo_manager()->num_photos());
//   ASSERT_EQ(1, photo_manager()->num_episodes());

//   // Wait for the metadata to be uploaded.
//   const int kUploadCount[] = { 10, 10, 7 };
//   for (int i = 0; i < ARRAYSIZE(kUploadCount); ++i) {
//     WaitForNetworkDispatch();
//     ASSERT(photo_manager()->queued_metadata_upload() != NULL);
//     const PhotoManager::MetadataUpload* u =
//         photo_manager()->queued_metadata_upload();
//     ASSERT_EQ(kUploadCount[i], u->photos.size());
//     vector<int64_t> v(u->photos.size());
//     for (int i = 0; i < v.size(); ++i) {
//       v[i] = u->photos[i]->metadata.id().local_id();
//     }
//     SimulateMetadataUpload("e000000001", v);

//     for (int j = 0; j < v.size(); ++j) {
//       // Wait for the various images to be uploaded.
//       const PhotoManager::PhotoType kUploadTypes[] = {
//         PhotoManager::THUMBNAIL,
//         PhotoManager::FULL,
//         PhotoManager::MEDIUM,
//       };
//       for (int k = 0; k < ARRAYSIZE(kUploadTypes); ++k) {
//         WaitForNetworkDispatch();
//         ASSERT(photo_manager()->queued_photo_upload());
//         ASSERT_EQ(kUploadTypes[k], photo_manager()->queued_photo_upload()->type);
//         photo_manager()->CommitQueuedPhotoUpload(false);
//       }
//     }
//   }

//   // Delete all of the photos.
//   photo_manager()->DeletePhotos(photo_ids);

//   // Wait for the deletes to be queued and verify they are the expected sizes.
//   const int kDeleteCount[] = { 10, 10, 7 };
//   for (int i = 0; i < ARRAYSIZE(kDeleteCount); ++i) {
//     WaitForNetworkDispatch();
//     ASSERT(photo_manager()->queued_delete_upload() != NULL);
//     const PhotoManager::DeleteUpload* u = photo_manager()->queued_delete_upload();
//     ASSERT_EQ(kDeleteCount[i], u->photos.size());
//     photo_manager()->CommitQueuedDeleteUpload();
//   }
// }

// TEST_F(PhotoManagerTest, LoadViewfinderPhotoError) {
//   SimulateOKNetwork();

//   // Add a new viewfinder photo and simulate the upload to the server.
//   const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_metadata_upload());
//   SimulateMetadataUpload("e000000001", L(photo_id));

//   // Wait for the various images to be uploaded.
//   const PhotoManager::PhotoType kUploadTypes[] = {
//     PhotoManager::THUMBNAIL,
//     PhotoManager::FULL,
//     PhotoManager::MEDIUM,
//     PhotoManager::ORIGINAL,
//   };
//   for (int i = 0; i < ARRAYSIZE(kUploadTypes); ++i) {
//     WaitForNetworkDispatch();
//     ASSERT(photo_manager()->queued_photo_upload());
//     ASSERT_EQ(kUploadTypes[i], photo_manager()->queued_photo_upload()->type);
//     photo_manager()->CommitQueuedPhotoUpload(false);
//   }
//   ASSERT_EQ(0, photo_manager()->num_queued_photos());
//   ASSERT_EQ(0, photo_manager()->num_queued_uploads());
//   ASSERT_EQ(0, photo_manager()->num_queued_downloads());

//   // Delete the various local images.
//   const string kSuffix[] = { "0120", "0480", "0960", "orig" };
//   for (int i = 0; i < ARRAYSIZE(kSuffix); ++i) {
//     FileRemove(Format("%s/%d-%s.jpg", env_.photo_dir(), photo_id, kSuffix[i]));
//   }

//   // Attempt to load the various image sizes.
//   const int kLoadSizes[] = { 120, 480 };
//   const PhotoManager::PhotoType kLoadTypes[] = {
//     PhotoManager::THUMBNAIL,
//     PhotoManager::FULL,
//   };
//   for (int i = 0; i < ARRAYSIZE(kLoadSizes); ++i) {
//     Image image;
//     Barrier* barrier = new Barrier(1);
//     if (kLoadSizes[i] == 120) {
//       photo_manager()->LoadLocalThumbnail(
//           photo_id, &image, ^{
//             barrier->Signal();
//           });
//     } else {
//       photo_manager()->LoadLocalPhoto(
//           photo_id, CGSizeMake(kLoadSizes[i], kLoadSizes[i]), &image, ^{
//             barrier->Signal();
//           });
//     }
//     barrier->Wait();

//     // The load should have failed.
//     ASSERT(!image);
//     // But the image should now be queued for download.
//     ASSERT_EQ(1, photo_manager()->num_queued_downloads());
//     env_.network_ready()->Run();
//     ASSERT(photo_manager()->queued_photo_download() != NULL);
//     ASSERT_EQ(photo_id, photo_manager()->queued_photo_download()->id.local_id());
//     ASSERT_EQ(kLoadTypes[i], photo_manager()->queued_photo_download()->type);

//     // Simulate successful retrieval.
//     ASSERT(WriteStringToFile(
//                photo_manager()->queued_photo_download()->path, "hello"));
//     photo_manager()->CommitQueuedPhotoDownload(photo_id, "world", false);
//     ASSERT_EQ(0, photo_manager()->num_queued_downloads());
//   }
// }

// TEST_F(PhotoManagerTest, LoadAssetPhotoError) {
//   SimulateOKNetwork();

//   // Add a new assets photo and simulate the upload to the server.
//   NSURL* url = env_.test_assets()->Add();
//   ALAsset* asset = env_.test_assets()->Lookup(url);
//   const int64_t photo_id = photo_manager()->NewAssetPhoto(
//       asset, DBFormat::asset_key(ToString(url)), false);
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_metadata_upload());
//   SimulateMetadataUpload("e000000001", L(photo_id));

//   const PhotoManager::PhotoType kUploadTypes[] = {
//     PhotoManager::THUMBNAIL,
//     PhotoManager::FULL,
//     PhotoManager::MEDIUM,
//     PhotoManager::ORIGINAL,
//   };
//   for (int i = 0; i < ARRAYSIZE(kUploadTypes); ++i) {
//     WaitForNetworkDispatch();
//     ASSERT(photo_manager()->queued_photo_upload());
//     ASSERT_EQ(kUploadTypes[i], photo_manager()->queued_photo_upload()->type);
//     photo_manager()->CommitQueuedPhotoUpload(false);
//   }
//   ASSERT_EQ(0, photo_manager()->num_queued_photos());
//   ASSERT_EQ(0, photo_manager()->num_queued_uploads());
//   ASSERT_EQ(0, photo_manager()->num_queued_downloads());

//   // Delete the asset and any cached viewfinder images.
//   env_.test_assets()->Delete(url);
//   // Delete the various local images.
//   const string kSuffix[] = { "0120", "0480", "0960", "orig" };
//   for (int i = 0; i < ARRAYSIZE(kSuffix); ++i) {
//     FileRemove(Format("%s/%d-%s.jpg", env_.photo_dir(), photo_id, kSuffix[i]));
//   }

//   const int kLoadSizes[] = { 120, 480, 100000 };
//   const PhotoManager::PhotoType kLoadTypes[] = {
//     PhotoManager::THUMBNAIL,
//     PhotoManager::FULL,
//     PhotoManager::FULL,  // We currently only download thumbnail and full.
//   };
//   for (int i = 0; i < ARRAYSIZE(kLoadSizes); ++i) {
//     Image image;
//     Barrier* barrier = new Barrier(1);
//     if (kLoadSizes[i] == 120) {
//       photo_manager()->LoadLocalThumbnail(
//           photo_id, &image, ^{
//             barrier->Signal();
//           });
//     } else {
//       photo_manager()->LoadLocalPhoto(
//           photo_id, CGSizeMake(kLoadSizes[i], kLoadSizes[i]), &image, ^{
//             barrier->Signal();
//           });
//     }
//     barrier->Wait();
//     // The load should have failed.
//     ASSERT(!image);

//     // Verify the error was set appropriately.
//     const PhotoManager::PhotoData* p =
//         FindPtrOrNull(photo_manager()->photos(), photo_id);
//     ASSERT(p->metadata.error_asset_thumbnail());
//     ASSERT(p->metadata.error_asset_full());
//     ASSERT(p->metadata.error_asset_original());

//     switch (i) {
//       case 0:
//         ASSERT(p->metadata.error_ui_thumbnail());
//         break;
//       case 1:
//       case 2:
//         ASSERT(p->metadata.error_ui_full());
//         break;
//     }

//     // But the image should now be queued for download.
//     ASSERT_EQ(1, photo_manager()->num_queued_downloads());
//     env_.network_ready()->Run();
//     ASSERT(photo_manager()->queued_photo_download() != NULL);
//     ASSERT_EQ(photo_id, photo_manager()->queued_photo_download()->id.local_id());
//     ASSERT_EQ(kLoadTypes[i], photo_manager()->queued_photo_download()->type);

//     // Simulate successful retrieval.
//     ASSERT(WriteStringToFile(
//                photo_manager()->queued_photo_download()->path, "hello"));
//     photo_manager()->CommitQueuedPhotoDownload(photo_id, "world", false);
//     ASSERT_EQ(0, photo_manager()->num_queued_downloads());
//   }
// }

// TEST_F(PhotoManagerTest, UploadPhotoError) {
//   SimulateOKNetwork();

//   // Add a new viewfinder photo and simulate the metadata upload to the server.
//   const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_metadata_upload());
//   SimulateMetadataUpload("e000000001", L(photo_id));

//   const PhotoManager::PhotoType kUploadTypes[] = {
//     PhotoManager::THUMBNAIL,
//     PhotoManager::FULL,
//     PhotoManager::MEDIUM,
//     PhotoManager::ORIGINAL,
//   };
//   for (int i = 0; i < ARRAYSIZE(kUploadTypes); ++i) {
//     // Wait for the photo upload to be queued and simulate an upload failure.
//     WaitForNetworkDispatch();
//     ASSERT(photo_manager()->queued_photo_upload());
//     ASSERT_EQ(kUploadTypes[i], photo_manager()->queued_photo_upload()->type);
//     photo_manager()->CommitQueuedPhotoUpload(true);

//     // Verify the error was set appropriately.
//     const PhotoManager::PhotoData* p =
//         FindPtrOrNull(photo_manager()->photos(), photo_id);
//     switch (i) {
//       case 0:
//         ASSERT(p->metadata.error_upload_thumbnail());
//         break;
//       case 1:
//         ASSERT(p->metadata.error_upload_full());
//         break;
//       case 2:
//         ASSERT(p->metadata.error_upload_medium());
//         break;
//       case 3:
//         ASSERT(p->metadata.error_upload_original());
//         break;
//     }
//     // The server-id associated with the photo should have been cleared.
//     ASSERT(!p->metadata.id().has_server_id());

//     // Wait for the photo metadata to be queued for upload again.
//     WaitForNetworkDispatch();
//     ASSERT(photo_manager()->queued_metadata_upload());
//     SimulateMetadataUpload("e000000001", L(photo_id));

//     // Simulate successful upload of this photo type.
//     for (int j = 0; j <= i; ++j) {
//       WaitForNetworkDispatch();
//       ASSERT(photo_manager()->queued_photo_upload());
//       ASSERT_EQ(kUploadTypes[j], photo_manager()->queued_photo_upload()->type);
//       photo_manager()->CommitQueuedPhotoUpload(false);
//     }

//     switch (i) {
//       case 0:
//         ASSERT(!p->metadata.error_upload_thumbnail());
//         break;
//       case 1:
//         ASSERT(!p->metadata.error_upload_full());
//         break;
//       case 2:
//         ASSERT(!p->metadata.error_upload_medium());
//         break;
//       case 3:
//         ASSERT(!p->metadata.error_upload_original());
//         break;
//     }
//   }
// }

// TEST_F(PhotoManagerTest, UploadPhotoErrorQuarantine) {
//   SimulateOKNetwork();

//   // Add a new viewfinder photo and simulate the metadata upload to the server.
//   const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_metadata_upload());
//   SimulateMetadataUpload("e000000001", L(photo_id));

//   // Wait for the photo upload to be queued and simulate an upload failure.
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_photo_upload());
//   ASSERT_EQ(PhotoManager::THUMBNAIL,
//             photo_manager()->queued_photo_upload()->type);
//   photo_manager()->CommitQueuedPhotoUpload(true);

//   // Verify the error was set appropriately.
//   const PhotoManager::PhotoData* p =
//       FindPtrOrNull(photo_manager()->photos(), photo_id);
//   ASSERT(p->metadata.error_upload_thumbnail());
//   // The server-id associated with the photo should have been cleared.
//   ASSERT(!p->metadata.id().has_server_id());

//   // Wait for the photo metadata to be queued for upload again.
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_metadata_upload());
//   SimulateMetadataUpload("e000000001", L(photo_id));

//   // Wait for the photo upload to be queued and simulate another upload
//   // failure.
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_photo_upload());
//   ASSERT_EQ(PhotoManager::THUMBNAIL,
//             photo_manager()->queued_photo_upload()->type);
//   photo_manager()->CommitQueuedPhotoUpload(true);

//   // Verify the photo was quarantined.
//   ASSERT(p->metadata.label_error());
//   ASSERT(!p->episode);
// }

// TEST_F(PhotoManagerTest, DownloadPhotoError) {
//   SimulateOKNetwork();

//   // Add a new viewfinder photo and simulate the upload to the server.
//   const int64_t photo_id = NewViewfinderPhoto(WallTime_Now());
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_metadata_upload());
//   SimulateMetadataUpload("e000000001", L(photo_id));

//   // Wait for the various images to be uploaded.
//   const PhotoManager::PhotoType kUploadTypes[] = {
//     PhotoManager::THUMBNAIL,
//     PhotoManager::FULL,
//     PhotoManager::MEDIUM,
//     PhotoManager::ORIGINAL,
//   };
//   for (int i = 0; i < ARRAYSIZE(kUploadTypes); ++i) {
//     WaitForNetworkDispatch();
//     ASSERT(photo_manager()->queued_photo_upload());
//     ASSERT_EQ(kUploadTypes[i], photo_manager()->queued_photo_upload()->type);
//     photo_manager()->CommitQueuedPhotoUpload(false);
//   }
//   ASSERT_EQ(0, photo_manager()->num_queued_photos());
//   ASSERT_EQ(0, photo_manager()->num_queued_uploads());
//   ASSERT_EQ(0, photo_manager()->num_queued_downloads());

//   // Delete the various local images.
//   const string kSuffix[] = { "0120", "0480", "0960", "orig" };
//   for (int i = 0; i < ARRAYSIZE(kSuffix); ++i) {
//     FileRemove(Format("%s/%d-%s.jpg", env_.photo_dir(), photo_id, kSuffix[i]));
//   }

//   {
//     // Attempt to load the thumbnail.
//     Image image;
//     Barrier* barrier = new Barrier(1);
//     photo_manager()->LoadLocalThumbnail(
//         photo_id, &image, ^{
//           barrier->Signal();
//         });
//     barrier->Wait();
//     // The load should have failed.
//     ASSERT(!image);
//   }

//   {
//     // Verify the load error was set appropriately.
//     const PhotoManager::PhotoData* p =
//         FindPtrOrNull(photo_manager()->photos(), photo_id);
//     ASSERT(p->metadata.error_ui_thumbnail());
//   }

//   // The image should now be queued for download.
//   ASSERT_EQ(1, photo_manager()->num_queued_downloads());
//   env_.network_ready()->Run();
//   ASSERT(photo_manager()->queued_photo_download() != NULL);
//   ASSERT_EQ(photo_id, photo_manager()->queued_photo_download()->id.local_id());
//   ASSERT_EQ(PhotoManager::THUMBNAIL,
//             photo_manager()->queued_photo_download()->type);
//   // Simulate a failed download.
//   photo_manager()->CommitQueuedPhotoDownload(photo_id, string(), false);
//   ASSERT_EQ(0, photo_manager()->num_queued_downloads());

//   {
//     // Verify the error was set appropriately.
//     const PhotoManager::PhotoData* p =
//         FindPtrOrNull(photo_manager()->photos(), photo_id);
//     ASSERT(p->metadata.error_download_thumbnail());
//   }

//   // The metadata for the photo will now be queued for download. Simulate it
//   // being returned.
//   ASSERT_EQ(1, photo_manager()->update_photo_ids().size());
//   ProcessGetMetadata(
//       Format("{\n"
//              "  \"photos\": [\n"
//              "    {\n"
//              "      \"photo_id\": \"%s\",\n"
//              "    }\n"
//              "  ]\n"
//              "}\n", ServerPhotoId(photo_id)));

//   // Wait for the photo download to be queued.
//   ASSERT_EQ(1, photo_manager()->num_queued_downloads());
//   env_.network_ready()->Run();
//   ASSERT(photo_manager()->queued_photo_download() != NULL);
//   ASSERT_EQ(photo_id, photo_manager()->queued_photo_download()->id.local_id());
//   ASSERT_EQ(PhotoManager::THUMBNAIL,
//             photo_manager()->queued_photo_download()->type);
//   // Simulate a successful thumbnail download.
//   ASSERT(WriteStringToFile(
//              photo_manager()->queued_photo_download()->path, "hello"));
//   photo_manager()->CommitQueuedPhotoDownload(photo_id, "world", false);
//   ASSERT_EQ(1, photo_manager()->num_queued_downloads());
//   env_.network_ready()->Run();
//   ASSERT(photo_manager()->queued_photo_download() != NULL);
//   ASSERT_EQ(photo_id, photo_manager()->queued_photo_download()->id.local_id());
//   ASSERT_EQ(PhotoManager::FULL,
//             photo_manager()->queued_photo_download()->type);
//   // Simulate a successful full-screen download.
//   ASSERT(WriteStringToFile(
//              photo_manager()->queued_photo_download()->path, "world"));
//   photo_manager()->CommitQueuedPhotoDownload(photo_id, "hello", false);
//   ASSERT_EQ(0, photo_manager()->num_queued_downloads());

//   {
//     // Verify the errors were cleared appropriately.
//     const PhotoManager::PhotoData* p =
//         FindPtrOrNull(photo_manager()->photos(), photo_id);
//     ASSERT(!p->metadata.error_download_thumbnail());
//     ASSERT(!p->metadata.error_ui_thumbnail());
//   }

//   // Remove the thumbnail again and simulate a double download failure.
//   FileRemove(Format("%s/%d-0120.jpg", env_.photo_dir(), photo_id));

//   {
//     // Attempt to load the thumbnail.
//     Image image;
//     Barrier* barrier = new Barrier(1);
//     photo_manager()->LoadLocalThumbnail(
//         photo_id, &image, ^{
//           barrier->Signal();
//         });
//     barrier->Wait();
//     // The load should have failed.
//     ASSERT(!image);
//   }

//   // The image should now be queued for download.
//   ASSERT_EQ(1, photo_manager()->num_queued_downloads());
//   env_.network_ready()->Run();
//   ASSERT(photo_manager()->queued_photo_download() != NULL);
//   ASSERT_EQ(photo_id, photo_manager()->queued_photo_download()->id.local_id());
//   ASSERT_EQ(PhotoManager::THUMBNAIL,
//             photo_manager()->queued_photo_download()->type);
//   // Simulate a failed download.
//   photo_manager()->CommitQueuedPhotoDownload(photo_id, string(), false);
//   ASSERT_EQ(0, photo_manager()->num_queued_downloads());

//   {
//     // Verify the error was set appropriately.
//     const PhotoManager::PhotoData* p =
//         FindPtrOrNull(photo_manager()->photos(), photo_id);
//     ASSERT(p->metadata.error_download_thumbnail());
//   }

//   // The metadata for the photo will now be queued for download. Simulate it
//   // being returned.
//   ASSERT_EQ(1, photo_manager()->update_photo_ids().size());
//   ProcessGetMetadata(
//       Format("{\n"
//              "  \"photos\": [\n"
//              "    {\n"
//              "      \"photo_id\": \"%s\",\n"
//              "    }\n"
//              "  ]\n"
//              "}\n", ServerPhotoId(photo_id)));

//   // Wait for the photo download to be queued.
//   ASSERT_EQ(1, photo_manager()->num_queued_downloads());
//   env_.network_ready()->Run();
//   ASSERT(photo_manager()->queued_photo_download() != NULL);
//   ASSERT_EQ(photo_id, photo_manager()->queued_photo_download()->id.local_id());
//   ASSERT_EQ(PhotoManager::THUMBNAIL,
//             photo_manager()->queued_photo_download()->type);
//   // Simulate a failed download.
//   photo_manager()->CommitQueuedPhotoDownload(photo_id, string(), false);
//   ASSERT_EQ(0, photo_manager()->num_queued_downloads());

//   {
//     // Verify the photo was quarantined on the second download failure.
//     const PhotoManager::PhotoData* p =
//         FindPtrOrNull(photo_manager()->photos(), photo_id);
//     ASSERT(p->metadata.label_error());
//     ASSERT(!p->episode);
//   }
// }

// TEST_F(PhotoManagerTest, PlacemarkHistogram) {
//   env_.set_network_up(true);
//   env_.set_network_wifi(true);

//   Placemark pm;
//   pm.set_iso_country_code("US");
//   pm.set_country("United States");
//   pm.set_state("New York");
//   pm.set_locality("New York City");
//   pm.set_sublocality("Greenwich Village");
//   pm.set_thoroughfare("Broadway");
//   pm.set_subthoroughfare("682");

//   // Set up a reverse geocoding callback to set placemark.
//   env_.reverse_geocode()->Add(^(const Location* l, void (^done)(const Placemark*)) {
//       LOG("reverse geocode callback called for location %s", *l);
//       done(&pm);
//     });

//   // Create a photo with a location; this should trigger a
//   // reverse geolocation.
//   PhotoMetadata m;
//   m.set_timestamp(WallTime_Now());
//   m.set_aspect_ratio(640.0 / 852.0);
//   m.mutable_location()->set_latitude(40.727657);
//   m.mutable_location()->set_longitude(-73.994583);
//   m.mutable_location()->set_accuracy(50.0);
//   int64_t photo_id = photo_manager()->NewViewfinderPhoto(
//       m, ReadFileToData(MainBundlePath("test-photo.jpg")));

//   WaitForNetworkDispatch();

//   // Verify that the placemark histogram was updated with the
//   // reverse geo-located placemark.
//   double distance;
//   PlacemarkHistogram::TopPlacemark top;
//   CHECK(env_.placemark_histogram()->DistanceToTopPlacemark(
//             m.location(), &distance, &top));
//   ASSERT_EQ(top.weight, 1.0);
//   ASSERT_EQ(distance, 0.0);
//   ASSERT(photo_manager()->queued_metadata_upload());

//   {
//     // Simulate the metadata being uploaded.
//     const string kUploadEpisodeResponse =
//         "{\n"
//         "  \"episode_id\" : \"eg2lB2YuT-F\",\n"
//         "  \"photos\" : [\n"
//         "    {\n"
//         "      \"photo_id\" : \"pg2lAIIuj0k\",\n"
//         "    },\n"
//         "  ]\n"
//         "}\n";
//     CommitMetadataUpload(kUploadEpisodeResponse);
//   }
//   ASSERT(!photo_manager()->queued_metadata_upload());

//   {
//     // Simulate an update to photo metadata which alters
//     // the placemark.
//     const string kQueryUpdatesResponse =
//         "{\n"
//         "  \"photos\" : [\n"
//         "    {\n"
//         "      \"content_type\": \"image/jpeg\",\n"
//         "      \"episode_id\": \"eg2lB2YuT-F\",\n"
//         "      \"labels\": \"+owned\",\n"
//         "      \"photo_id\": \"pg2lAIIuj0k\",\n"
//         "      \"user_id\": 1\n"
//         "    },\n"
//         "    {\n"
//         "      \"photo_id\": \"pg2lAIIuj0k\",\n"
//         "      \"location\": {\n"
//         "        \"latitude\": 41.034184,\n"
//         "        \"longitude\": -72.210603,\n"
//         "        \"accuracy\": 50.0,\n"
//         "      },\n"
//         "      \"placemark\": {\n"
//         "        \"locality\": \"East Hampton\",\n"
//         "        \"sublocality\": \"The Hamptons\",\n"
//         "        \"thoroughfare\": \"Milina Dr.\",\n"
//         "        \"subthoroughfare\": \"35\",\n"
//         "      },\n"
//         "    }\n"
//         "  ]\n"
//         "}\n";
//     ProcessQueryUpdates(kQueryUpdatesResponse);
//   }

//   // Verify that the placemark histogram was updated with the
//   // updated placemark & location. Getting the top placemark
//   // near the original location yields the new location, which
//   // is some distance away.
//   CHECK(env_.placemark_histogram()->DistanceToTopPlacemark(
//             m.location(), &distance, &top));
//   CHECK_EQ(top.weight, 1.0);
//   // Placemark has changed!
//   CHECK_EQ(top.placemark.locality(), "East Hampton");
//   // Top location placemark strips out sublocality.
//   CHECK(top.placemark.sublocality().empty());
//   // The distance is about 153km.
//   CHECK_LT(fabs(distance - 153802), 1.0);

//   // Delete the photo.
//   photo_manager()->DeletePhotos(L(photo_id));
//   WaitForNetworkDispatch();
//   ASSERT(photo_manager()->queued_delete_upload() != NULL);
//   photo_manager()->CommitQueuedDeleteUpload();
//   ASSERT(photo_manager()->queued_delete_upload() == NULL);

//   // There should now be no information in the placemark histogram.
//   CHECK(!env_.placemark_histogram()->DistanceToTopPlacemark(
//             m.location(), &distance, &top));
// }

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
