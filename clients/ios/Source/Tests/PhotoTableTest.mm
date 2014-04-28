// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "ImageIndex.h"
#import "PhotoStorage.h"
#import "PhotoTable.h"
#import "Testing.h"
#import "TestUtils.h"

namespace {

class PhotoTableTest : public BaseContentTest {
 public:
  PhotoTableTest() {
  }

  PhotoHandle NewPhoto() {
    DBHandle updates = state_.NewDBTransaction();
    PhotoHandle h = photo_table()->NewContent(updates);
    updates->Commit();
    return h;
  }

  PhotoHandle NewPhoto(WallTime timestamp) {
    DBHandle updates = state_.NewDBTransaction();
    PhotoHandle h = photo_table()->NewContent(updates);
    h->Lock();
    h->set_timestamp(timestamp);
    updates->Commit();
    return h;
  }

  PhotoHandle LoadPhoto(int64_t id) {
    return photo_table()->LoadContent(id, db());
  }

  PhotoHandle LoadPhoto(const string& server_id) {
    return photo_table()->LoadContent(server_id, db());
  }

  PhotoHandle LoadAssetPhoto(const string& asset_key) {
    return photo_table()->LoadAssetPhoto(asset_key, db());
  }

  void SavePhoto(const PhotoHandle& h) {
    DBHandle updates = state_.NewDBTransaction();
    h->SaveAndUnlock(updates);
    updates->Commit();
  }

  bool AssetPhotoExists(const string& asset_key) {
    return photo_table()->AssetPhotoExists(asset_key, db());
  }

  void AddAssetKey(const PhotoHandle& h, const string& asset_key) {
    DBHandle updates = state_.NewDBTransaction();
    if (h->AddAssetKey(asset_key)) {
      h->Save(updates);
    }
    updates->Commit();
  }

  void RemoveAssetKey(const PhotoHandle& h, const string& asset_key) {
    DBHandle updates = state_.NewDBTransaction();
    h->RemoveAssetKey(asset_key);
    h->Save(updates);
    updates->Commit();
  }

  string GetUnexpiredURL(const PhotoHandle& h, const string& name) {
    DBHandle updates = state_.NewDBTransaction();
    string s = h->GetUnexpiredURL(name, updates);
    updates->Commit();
    return s;
  }

  void SetURL(const PhotoHandle& h, const string& name, const string& url) {
    DBHandle updates = state_.NewDBTransaction();
    h->SetURL(name, url, updates);
    updates->Commit();
  }

  void DeleteURL(const PhotoHandle& h, const string& name) {
    DBHandle updates = state_.NewDBTransaction();
    h->DeleteURL(name, updates);
    updates->Commit();
  }

  void DeleteAllImages(int64_t id) {
    DBHandle updates = state_.NewDBTransaction();
    photo_table()->DeleteAllImages(id, updates);
    updates->Commit();
  }

  void AssetsNotFound(const StringSet& not_found) {
    DBHandle updates = state_.NewDBTransaction();
    photo_table()->AssetsNotFound(not_found, updates);
    updates->Commit();
  }

  int referenced_photos() const {
    return photo_table()->referenced_contents();
  }

  void ReplaceAssetKey(const PhotoHandle& h, const string& value) {
    while (h->asset_keys_size()) {
      h->RemoveAssetKey(h->asset_keys(0));
    }
    h->AddAssetKey(value);
  }

  string GetAssetKeys(const PhotoHandle& h) {
    // Convert the protobuf::RepeatedPtrField into a vector to get operator== and operator<<.
    return ToString(vector<string>(h->asset_keys().begin(),
                                   h->asset_keys().end()));
  }

  string GetAssetUrls(const PhotoHandle& h) {
    vector<string> out;
    for (int i = 0; i < h->asset_keys_size(); i++) {
      Slice url;
      if (DecodeAssetKey(h->asset_keys(i), &url, NULL) && !url.empty()) {
        out.push_back(url.as_string());
      }
    }
    return ToString(out);
  }

  string GetAssetFingerprints(const PhotoHandle& h) const {
    vector<string> out;
    for (int i = 0; i < h->asset_fingerprints_size(); i++) {
      out.push_back(h->asset_fingerprints(i));
    }
    return ToString(out);
  }

  string Search(const string& fingerprint_term) const {
    ImageFingerprint f;
    f.add_terms(fingerprint_term);
    StringSet matched_ids;
    state_.image_index()->Search(db(), f, &matched_ids);
    vector<string> sorted_ids(matched_ids.begin(), matched_ids.end());
    std::sort(sorted_ids.begin(), sorted_ids.end());
    return ToString(sorted_ids);
  }
};

TEST_F(PhotoTableTest, NewPhoto) {
  for (int i = 1; i < 10; ++i) {
    ASSERT_EQ(i, NewPhoto()->id().local_id());
    ASSERT_EQ(0, referenced_photos());
  }
}

TEST_F(PhotoTableTest, Basic) {
  // Create a new photo.
  ASSERT_EQ(0, referenced_photos());
  PhotoHandle p = NewPhoto();
  ASSERT_EQ(1, p->id().local_id());
  ASSERT_EQ(1, referenced_photos());
  // Though we never saved the photo, we can load it because there is still a
  // reference to it.
  ASSERT_EQ(p.get(), LoadPhoto(1).get());
  ASSERT_EQ(1, referenced_photos());
  // Release the reference.
  p.reset();
  ASSERT_EQ(0, referenced_photos());
  // We never saved the photo and there are no other references, so we won't
  // be able to load it.
  ASSERT(!LoadPhoto(1).get());
  ASSERT_EQ(0, referenced_photos());
  p = NewPhoto();
  ASSERT_EQ(2, p->id().local_id());
  ASSERT_EQ(1, referenced_photos());
  // Verify we can retrieve it.
  ASSERT_EQ(p.get(), LoadPhoto(2).get());
  ASSERT_EQ(1, referenced_photos());
  // Verify that setting a server id sets up a mapping to the local id.
  p->Lock();
  p->mutable_id()->set_server_id("a");
  SavePhoto(p);
  ASSERT_EQ(p.get(), LoadPhoto("a").get());
  // Verify that changing the server id works properly.
  p->Lock();
  p->mutable_id()->set_server_id("b");
  SavePhoto(p);
  ASSERT_EQ(p.get(), LoadPhoto("b").get());
  ASSERT(!LoadPhoto("a").get());
  // Verify that setting an asset key sets up a mapping to the local id.
  p->Lock();
  ReplaceAssetKey(p, "a/c");
  SavePhoto(p);
  ASSERT_EQ(p.get(), LoadAssetPhoto("a/c").get());
  // Verify that changing the asset key works properly.
  p->Lock();
  ReplaceAssetKey(p, "a/d");
  SavePhoto(p);
  ASSERT_EQ(p.get(), LoadAssetPhoto("a/d").get());
  ASSERT(!LoadAssetPhoto("a/c").get());
  // Try new-format asset keys.
  p->Lock();
  ReplaceAssetKey(p, "a/e#f");
  SavePhoto(p);
  ASSERT(!LoadAssetPhoto("a/d").get());
  ASSERT_EQ(p.get(), LoadAssetPhoto("a/e").get());
  ASSERT_EQ(p.get(), LoadAssetPhoto("a/e#f").get());
  ASSERT_EQ(p.get(), LoadAssetPhoto("a/g#f").get());
  // Verify AssetPhotoExists only returns true if both the url and fingerprint
  // match.
  ASSERT(AssetPhotoExists("a/e#f"));
  ASSERT(!AssetPhotoExists("a/e#g"));
  ASSERT(!AssetPhotoExists("a/g#f"));
  // Verify changing new-format asset keys works properly.
  p->Lock();
  ReplaceAssetKey(p, "a/h#i");
  SavePhoto(p);
  ASSERT(!LoadAssetPhoto("a/e").get());
  // Fingerprints are never removed once added, so this old key still works
  ASSERT(LoadAssetPhoto("a/e#f").get());
  ASSERT_EQ(p.get(), LoadAssetPhoto("a/h").get());
  ASSERT_EQ(p.get(), LoadAssetPhoto("a/h#i").get());
  ASSERT_EQ(p.get(), LoadAssetPhoto("a/j#i").get());
  // Update the asset key to not contain an asset fingerprint.
  p->Lock();
  ReplaceAssetKey(p, "a/k");
  SavePhoto(p);
  ASSERT_EQ(2, db()->Get<int64_t>("a/k", -1));
  ASSERT_EQ(-1, db()->Get<int64_t>("ar/i#j", -1));
  // Update the photo to not contain an asset key.
  p->Lock();
  p->clear_asset_keys();
  SavePhoto(p);
}

TEST_F(PhotoTableTest, ShouldUpdateTimestamp) {
  const double kHourInSeconds = 60 * 60;
  WallTime ts = WallTime_Now();
  PhotoHandle p = NewPhoto(ts);
  for (int i = 0; i < 24; ++i) {
    ASSERT(!p->ShouldUpdateTimestamp(ts + kHourInSeconds * i));
  }
  ASSERT(p->ShouldUpdateTimestamp(ts + 1));
  ASSERT(p->ShouldUpdateTimestamp(ts + kHourInSeconds * 24));
}

TEST_F(PhotoTableTest, AddAssetKey) {
  PhotoHandle p = NewPhoto();
  ASSERT_EQ(1, p->id().local_id());
  p->Lock();
  ReplaceAssetKey(p, "a/b");
  AddAssetKey(p, "a/b#c");
  EXPECT_EQ("<b>", GetAssetUrls(p));
  EXPECT_EQ("<c>", GetAssetFingerprints(p));
  ReplaceAssetKey(p, "a/d");
  AddAssetKey(p, "a/d#c");
  EXPECT_EQ("<d>", GetAssetUrls(p));
  EXPECT_EQ("<c>", GetAssetFingerprints(p));
  ReplaceAssetKey(p, "a/f#e");
  EXPECT_EQ("<f>", GetAssetUrls(p));
  EXPECT_EQ("<c e>", GetAssetFingerprints(p));
  AddAssetKey(p, "a/g#e");
  EXPECT_EQ("<f g>", GetAssetUrls(p));
  EXPECT_EQ("<c e>", GetAssetFingerprints(p));
  p->Unlock();
  AssetsNotFound(L("g"));
  ASSERT_EQ("<not found>", db()->Get<string>("a/g#h", "<not found>"));
  ASSERT_EQ("<not found>", db()->Get<string>("ar/h#g", "<not found>"));
}

TEST_F(PhotoTableTest, MultipleAssetKeys) {
  PhotoHandle p = NewPhoto();
  p->Lock();

  AddAssetKey(p, "a/b#c");
  EXPECT_EQ("<a/b#c>", GetAssetKeys(p));
  EXPECT_EQ("<b>", GetAssetUrls(p));
  EXPECT_EQ("<c>", GetAssetFingerprints(p));

  AddAssetKey(p, "a/d#c");
  EXPECT_EQ("<a/b#c a/d#c>", GetAssetKeys(p));
  EXPECT_EQ("<b d>", GetAssetUrls(p));
  EXPECT_EQ("<c>", GetAssetFingerprints(p));

  RemoveAssetKey(p, "a/d#c");
  EXPECT_EQ("<a/b#c>", GetAssetKeys(p));
  EXPECT_EQ("<b>", GetAssetUrls(p));
  EXPECT_EQ("<c>", GetAssetFingerprints(p));

  RemoveAssetKey(p, "a/b#c");
  EXPECT_EQ("<>", GetAssetKeys(p));
  EXPECT_EQ("<>", GetAssetUrls(p));
  EXPECT_EQ("<c>", GetAssetFingerprints(p));
  EXPECT(!p->HasAssetUrl());

  RemoveAssetKey(p, "a/#c");
  EXPECT_EQ("<>", GetAssetKeys(p));

  AddAssetKey(p, "a/e#f");
  AddAssetKey(p, "a/g#f");
  AddAssetKey(p, "a/h#i");
  EXPECT_EQ("<a/e#f a/g#f a/h#i>", GetAssetKeys(p));
  EXPECT_EQ("<e g h>", GetAssetUrls(p));
  EXPECT_EQ("<c f i>", GetAssetFingerprints(p));

  RemoveAssetKey(p, "a/e#f");
  EXPECT_EQ("<a/h#i a/g#f>", GetAssetKeys(p));
  EXPECT_EQ("<h g>", GetAssetUrls(p));
  EXPECT_EQ("<c f i>", GetAssetFingerprints(p));

  RemoveAssetKey(p, "a/g#f");
  EXPECT_EQ("<a/h#i>", GetAssetKeys(p));
  EXPECT_EQ("<h>", GetAssetUrls(p));
  EXPECT_EQ("<c f i>", GetAssetFingerprints(p));

  RemoveAssetKey(p, "a/h#i");
  EXPECT_EQ("<>", GetAssetKeys(p));
  EXPECT_EQ("<>", GetAssetUrls(p));
  EXPECT_EQ("<c f i>", GetAssetFingerprints(p));

  AddAssetKey(p, "a/j#f");
  EXPECT_EQ("<a/j#f>", GetAssetKeys(p));
  EXPECT_EQ("<j>", GetAssetUrls(p));
  EXPECT_EQ("<c f i>", GetAssetFingerprints(p));

  RemoveAssetKey(p, ToString("a/#i"));
  RemoveAssetKey(p, ToString("a/j#f"));
  EXPECT_EQ("<>", GetAssetKeys(p));
}

TEST_F(PhotoTableTest, NotFound) {
  PhotoHandle p = NewPhoto();
  ASSERT_EQ(1, p->id().local_id());
  p->Lock();
  ReplaceAssetKey(p, "a/b#c");
  SavePhoto(p);
  ASSERT_EQ(p.get(), LoadAssetPhoto("a/b#c").get());
  ASSERT_EQ(p.get(), LoadAssetPhoto("a/#c").get());
  // Mark a different asset as not being found.
  AssetsNotFound(L("d"));
  ASSERT_EQ(p.get(), LoadAssetPhoto("a/b#c").get());
  ASSERT_EQ(1, db()->Get<int64_t>("a/b#c"));
  // Mark the asset as not being found.
  AssetsNotFound(L("b"));
  // We'll still be able to retrieve it as LoadAssetPhoto() will fall back to
  // using the fingerprint.
  ASSERT_EQ(p.get(), LoadAssetPhoto("a/b#c").get());
  ASSERT_EQ(p.get(), LoadAssetPhoto("a/#c").get());
  // But the asset url will have been stripped.
  ASSERT_EQ("<>", GetAssetKeys(p));
  ASSERT_EQ("<c>", GetAssetFingerprints(p));
  ASSERT_EQ(-1, db()->Get<int64_t>("a/b#c", -1));
  ASSERT_EQ(1, db()->Get<int64_t>("af/c"));
}

TEST_F(PhotoTableTest, URL) {
  PhotoHandle x = NewPhoto();
  ASSERT_EQ("", x->GetURL("a"));
  SetURL(x, "a", "b");
  ASSERT_EQ("b", x->GetURL("a"));
  SetURL(x, "c", "d");
  ASSERT_EQ("b", x->GetURL("a"));
  ASSERT_EQ("d", x->GetURL("c"));
  PhotoHandle y = NewPhoto();
  SetURL(y, "a", "e");
  ASSERT_EQ("b", x->GetURL("a"));
  ASSERT_EQ("d", x->GetURL("c"));
  ASSERT_EQ("e", y->GetURL("a"));
  DeleteURL(x, "a");
  ASSERT_EQ("", x->GetURL("a"));
  DeleteURL(x, "c");
  ASSERT_EQ("", x->GetURL("c"));
  DeleteURL(y, "a");
  ASSERT_EQ("", y->GetURL("a"));
}

TEST_F(PhotoTableTest, UnexpiredURL) {
  const WallTime now = WallTime_Now();

  PhotoHandle x = NewPhoto();
  SetURL(x, "a",
         Format("https://s3/foo?Signature=bar&Expires=%.0f&AWSAccessKeyId=blah",
                now + 1000));
  // An unexpired URL will be returned.
  ASSERT(!GetUnexpiredURL(x, "a").empty());
  ASSERT(!x->GetURL("a").empty());

  SetURL(x, "a",
         Format("https://s3/foo?Signature=bar&Expires=%.0f&AWSAccessKeyId=blah",
                now - 1));
  // An expired URL won't be returned.
  ASSERT(GetUnexpiredURL(x, "a").empty());
  // And will have been deleted.
  ASSERT(x->GetURL("a").empty());

  // Verify permissive URL parsing.
  SetURL(x, "a",
         Format("?Signature=bar&Expires=%.0f&AWSAccessKeyId=blah",
                now - 1));
  // An expired URL won't be returned.
  ASSERT(GetUnexpiredURL(x, "a").empty());
  // And will have been deleted.
  ASSERT(x->GetURL("a").empty());

  SetURL(x, "a",
         Format("?Expires=%.0f",
                now - 1));
  // An expired URL won't be returned.
  ASSERT(GetUnexpiredURL(x, "a").empty());
  // And will have been deleted.
  ASSERT(x->GetURL("a").empty());
}

TEST_F(PhotoTableTest, DeleteAllImages) {
  // Create a new photo with some local and asset images.
  PhotoHandle p = NewPhoto();
  p->Lock();
  ReplaceAssetKey(p, "a/hello");
  SavePhoto(p);
  WriteLocalImage(PhotoFilename(p->id().local_id(), 120), "thumbnail");
  WriteLocalImage(PhotoFilename(p->id().local_id(), 480), "medium");
  WriteLocalImage(PhotoFilename(p->id().local_id(), 960), "full");
  EXPECT_EQ(Format("<%d-0120.jpg %d-0480.jpg %d-0960.jpg>",
                   p->id().local_id(), p->id().local_id(),
                   p->id().local_id()).str,
            ListLocalImages());

  // Delete all the images and verify everything is deleted.
  __block string deleted_asset_key;
  state_.delete_asset()->AddSingleShot(^(const string& asset_key) {
      deleted_asset_key = asset_key;
    });
  DeleteAllImages(p->id().local_id());
  EXPECT_EQ("<>", ListLocalImages());
  EXPECT_EQ("a/hello", deleted_asset_key);
}

TEST_F(PhotoTableTest, PerceptualFingerprint) {
  PhotoHandle p = NewPhoto();
  p->Lock();
  // Add a fingerprint term.
  p->mutable_perceptual_fingerprint()->add_terms("00000000000000000000");
  SavePhoto(p);
  EXPECT_EQ("<1>", Search("00000000000000000000"));
  EXPECT_LT(0, state_.image_index()->TotalTags(db()));
  p->Lock();
  // Add another fingerprint term.
  p->mutable_perceptual_fingerprint()->add_terms("11111111111111111111");
  SavePhoto(p);
  EXPECT_EQ("<1>", Search("00000000000000000000"));
  EXPECT_EQ("<1>", Search("11111111111111111111"));
  p->Lock();
  // Remove the first term.
  p->mutable_perceptual_fingerprint()->clear_terms();
  p->mutable_perceptual_fingerprint()->add_terms("11111111111111111111");
  SavePhoto(p);
  EXPECT_EQ("<>", Search("00000000000000000000"));
  EXPECT_EQ("<1>", Search("11111111111111111111"));
  p->Lock();
  // Remove the second term.
  p->mutable_perceptual_fingerprint()->clear_terms();
  SavePhoto(p);
  EXPECT_EQ("<>", Search("11111111111111111111"));
  EXPECT_EQ(0, state_.image_index()->TotalTags(db()));
}

TEST_F(PhotoTableTest, FSCKMissingIndex) {
  // Create a photo without asset index entries
  PhotoMetadata m;
  m.mutable_id()->set_local_id(3);
  m.add_asset_keys(EncodeAssetKey("url", "fp"));
  m.add_asset_fingerprints("fp");
  state_.db()->PutProto(EncodeContentKey(DBFormat::photo_key(), m.id().local_id()), m);

  DBHandle updates = state_.NewDBTransaction();
  state_.photo_table()->FSCK(true, ^(const string) {}, updates);
  updates->Commit();

  EXPECT_EQ(state_.db()->Get<int64_t>(EncodeAssetKey("url", "fp")), m.id().local_id());
  EXPECT_EQ(state_.db()->Get<int64_t>(EncodeAssetFingerprintKey("fp")), m.id().local_id());
}

TEST_F(PhotoTableTest, FSCKIndexConflict) {
  // Create two photos with the same asset keys, and index entries for one.
  PhotoMetadata m;
  m.mutable_id()->set_local_id(1);
  m.add_asset_keys(EncodeAssetKey("url", "fp"));
  m.add_asset_fingerprints("fp");
  state_.db()->PutProto(EncodeContentKey(DBFormat::photo_key(), m.id().local_id()), m);
  state_.db()->Put<int64_t>(EncodeAssetKey("url", "fp"), 1);
  state_.db()->Put<int64_t>(EncodeAssetFingerprintKey("fp"), 1);

  m.mutable_id()->set_local_id(2);
  state_.db()->PutProto(EncodeContentKey(DBFormat::photo_key(), m.id().local_id()), m);

  DBHandle updates = state_.NewDBTransaction();
  state_.photo_table()->FSCK(true, ^(const string) {}, updates);
  updates->Commit();

  // Index entries still point to #1.
  EXPECT_EQ(state_.db()->Get<int64_t>(EncodeAssetKey("url", "fp")), 1);
  EXPECT_EQ(state_.db()->Get<int64_t>(EncodeAssetFingerprintKey("fp")), 1);

  // The keys have been stripped from #2
  PhotoMetadata m2;
  ASSERT(state_.db()->GetProto(EncodeContentKey(DBFormat::photo_key(), 2), &m2));
  EXPECT_EQ(m2.asset_keys_size(), 0);
  EXPECT_EQ(m2.asset_fingerprints_size(), 0);
  EXPECT(m2.update_metadata());
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
