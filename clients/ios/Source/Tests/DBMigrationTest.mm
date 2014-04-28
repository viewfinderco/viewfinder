// Copyright 2012 Viewfinder. All rights reserved.
// Author: Ben Darnell

#ifdef TESTING

#import "ContactManager.h"
#import "DBMigrationIOS.h"
#import "ImageIndex.h"
#import "PhotoManager.h"
#import "TestAssets.h"
#import "Testing.h"
#import "TestUtils.h"

namespace {

class DBMigrationTest : public BaseContentTest {
 protected:
  DBMigrationTest()
      : migration_(&state_, NULL) {
  }

  string ProtoToSortedString(const google::protobuf::RepeatedPtrField<string> field) {
    vector<string> s;
    for (int i = 0; i < field.size(); i++) {
      s.push_back(field.Get(i));
    }
    std::sort(s.begin(), s.end());
    return ToString(s);
  }

  void RunAndWaitForScan(void (^block)()) {
    Barrier* barrier = new Barrier(1);
    state_.assets_scan_end()->AddSingleShot(^(const StringSet*) {
        barrier->Signal();
      });
    block();
    barrier->Wait();
    delete barrier;
  }

  DBMigrationIOS migration_;
};

TEST_F(DBMigrationTest, MoveAssetKeys) {
  DBHandle updates = state_.NewDBTransaction();
  int64_t local_id = 0;
  {
    PhotoHandle ph = state_.photo_table()->NewPhoto(updates);
    ph->Lock();
    ph->mutable_id()->set_deprecated_asset_key(DBFormat::asset_key("asset-key-1"));
    local_id = ph->id().local_id();
    ph->SaveAndUnlock(updates);
  }

  migration_.MoveAssetKeys(updates);

  CHECK(updates->Commit());

  PhotoHandle ph2 = state_.photo_table()->LoadPhoto(local_id, state_.db());
  EXPECT(!ph2->id().has_deprecated_asset_key());
  EXPECT_EQ(ph2->asset_keys(0), DBFormat::asset_key("asset-key-1"));
}

TEST_F(DBMigrationTest, SplitAssetKeys) {
  DBHandle updates = state_.NewDBTransaction();
  int64_t local_id = 0;
  {
    PhotoHandle ph = state_.photo_table()->NewPhoto(updates);
    ph->Lock();
    ph->add_asset_keys("a/url1#fp1");
    ph->add_asset_keys("a/#fp2");
    local_id = ph->id().local_id();
    ph->SaveAndUnlock(updates);
  }

  migration_.SplitAssetKeys(updates);

  CHECK(updates->Commit());

  PhotoHandle ph = state_.photo_table()->LoadPhoto(local_id, state_.db());
  EXPECT_EQ("<a/url1#fp1>", ProtoToSortedString(ph->asset_keys()));
  EXPECT_EQ("<fp1 fp2>", ProtoToSortedString(ph->asset_fingerprints()));
}

TEST_F(DBMigrationTest, AssetFingerprintIndex) {
  DBHandle updates = state_.NewDBTransaction();
  updates->Put("ar/a#b", Slice("1"));
  updates->Put("ar/a#c", Slice("1"));
  updates->Put("ar/d#", Slice("2"));

  migration_.AssetFingerprintIndex(updates);

  CHECK(updates->Commit());

  EXPECT(!state_.db()->Exists(Slice("ar/a#b")));
  EXPECT(!state_.db()->Exists(Slice("ar/c#b")));
  EXPECT(!state_.db()->Exists(Slice("ar/d#")));
  EXPECT_EQ(state_.db()->Get<int64_t>("af/a"), 1);
  EXPECT_EQ(state_.db()->Get<int64_t>("af/d"), 2);
}

TEST_F(DBMigrationTest, ContactIndexStoreRaw) {
  DBHandle updates = state_.NewDBTransaction();
  {
    ContactMetadata m;
    m.set_primary_identity("Email:ben@emailscrubbed.com");
    m.add_indexed_names("ben  0 A");
    updates->PutProto("c/1", m);
  }

  migration_.ContactIndexStoreRaw(updates);
  CHECK(updates->Commit());

  {
    ContactMetadata m;
    CHECK(state_.db()->GetProto("c/1", &m));
    EXPECT_EQ(m.indexed_names(0), "cn/ben  0 A Email:ben@emailscrubbed.com");
  }
}

TEST_F(DBMigrationTest, SplitContactsUsers) {
  {
    DBHandle updates = state_.NewDBTransaction();

    {
      ContactMetadata m;
      m.set_name("A Contact");
      m.set_primary_identity("Email:contact@emailscrubbed.com");
      m.add_deprecated_identities(m.primary_identity());
      updates->PutProto("c/Email:contact@emailscrubbed.com", m);
    }
    {
      ContactMetadata m;
      m.set_name("A User");
      m.set_deprecated_user_name(true);
      m.set_user_id(1);
      m.set_primary_identity("VF:1");
      m.add_deprecated_identities(m.primary_identity());
      updates->PutProto("c/VF:1", m);
      updates->PutProto("ci/1", m);
    }
    {
      ContactMetadata m;
      m.set_name("Multiple Identities");
      m.set_deprecated_user_name(true);
      m.set_user_id(2);
      m.set_primary_identity("Email:id1@emailscrubbed.com");;
      m.add_deprecated_identities(m.primary_identity());
      m.add_deprecated_identities("Email:id2@emailscrubbed.com");
      m.add_deprecated_identities("VF:2");
      updates->PutProto("c/Email:id1@emailscrubbed.com", m);
      updates->PutProto("c/Email:id2@emailscrubbed.com", m);
      updates->PutProto("c/VF:2", m);
      updates->PutProto("ci/2", m);
    }
    CHECK(updates->Commit());
  }

  {
    DBHandle updates = state_.NewDBTransaction();
    migration_.SplitContactsUsers(updates);
    CHECK(updates->Commit());
  }

  {
    ContactMetadata m;
    ASSERT(state_.contact_manager()->LookupUser(1, &m));
    EXPECT_EQ(m.name(), "A User");
    EXPECT(!m.has_primary_identity());
    EXPECT_EQ(m.identities_size(), 0);
    EXPECT_EQ(m.deprecated_identities_size(), 0);
  }
  {
    ContactMetadata m;
    ASSERT(state_.contact_manager()->LookupUser(2, &m));
    EXPECT_EQ(m.name(), "Multiple Identities");
    EXPECT_EQ(m.primary_identity(), "Email:id1@emailscrubbed.com");
    ASSERT_EQ(m.identities_size(), 2);
    EXPECT_EQ(m.identities(0).identity(), "Email:id1@emailscrubbed.com");
    EXPECT_EQ(m.identities(1).identity(), "Email:id2@emailscrubbed.com");
  }
  {
    vector<ContactMetadata> results;
    state_.contact_manager()->Search("contact", &results, NULL);
    ASSERT_EQ(results.size(), 1);
    EXPECT_EQ(results[0].name(), "A Contact");
    EXPECT_EQ(results[0].primary_identity(), "Email:contact@emailscrubbed.com");
    ASSERT_EQ(results[0].identities_size(), 1);
    EXPECT_EQ(results[0].identities(0).identity(), "Email:contact@emailscrubbed.com");
  }
}

TEST_F(DBMigrationTest, IndexServerContactId) {
  DBHandle updates = state_.NewDBTransaction();
  ContactMetadata m;
  m.set_contact_id("ip:local_contact_id");
  m.set_server_contact_id("ip:server_contact_id");
  updates->PutProto(DBFormat::contact_key(m.contact_id()), m);

  migration_.IndexServerContactId(updates);
  CHECK(updates->Commit());

  EXPECT_EQ(state_.db()->Get<string>(DBFormat::server_contact_id_key(m.server_contact_id())),
            m.contact_id());
}

TEST_F(DBMigrationTest, CleanupContactIdentities) {
  {
    DBHandle updates = state_.NewDBTransaction();
    ContactMetadata m;
    m.set_contact_source(ContactManager::kContactSourceIOSAddressBook);
    m.set_contact_id("ip:no_identity");
    updates->PutProto(DBFormat::contact_key(m.contact_id()), m);

    m.Clear();
    m.set_contact_source(ContactManager::kContactSourceIOSAddressBook);
    m.set_contact_id("ip:no_primary_identity");
    m.add_identities()->set_identity("Email:npi@example.com");
    updates->PutProto(DBFormat::contact_key(m.contact_id()), m);

    m.Clear();
    m.set_contact_source(ContactManager::kContactSourceIOSAddressBook);
    m.set_contact_id("ip:primary_only");
    m.set_primary_identity("Email:primary@example.com");
    updates->PutProto(DBFormat::contact_key(m.contact_id()), m);

    m.Clear();
    m.set_contact_source(ContactManager::kContactSourceIOSAddressBook);
    m.set_contact_id("ip:unchanged");
    m.set_primary_identity("Email:unchanged@example.com");
    m.add_identities()->set_identity("Email:unchanged@example.com");
    updates->PutProto(DBFormat::contact_key(m.contact_id()), m);

    m.Clear();
    m.set_contact_source(ContactManager::kContactSourceIOSAddressBook);
    m.set_contact_id("ip:empty_identity");
    m.set_primary_identity("");
    m.add_identities()->set_identity("");
    updates->PutProto(DBFormat::contact_key(m.contact_id()), m);

    CHECK(updates->Commit());
  }

  {
    DBHandle updates = state_.NewDBTransaction();
    migration_.CleanupContactIdentities(updates);
    CHECK(updates->Commit());
  }

  std::map<string, ContactMetadata> contacts;
  for (DB::PrefixIterator iter(state_.db(), DBFormat::contact_key("")); iter.Valid(); iter.Next()) {
    ContactMetadata m;
    if (!m.ParseFromArray(iter.value().data(), iter.value().size())) {
      continue;
    }

    ASSERT(!m.primary_identity().empty());
    ASSERT(!ContainsKey(contacts, m.primary_identity()));
    contacts[m.primary_identity()] = m;
  }
  ASSERT_EQ(contacts.size(), 3);
  vector<string> emails = L("Email:npi@example.com", "Email:primary@example.com", "Email:unchanged@example.com");
  for (int i = 0; i < emails.size(); i++) {
    ASSERT(ContainsKey(contacts, emails[i]));
    const ContactMetadata& m = contacts[emails[i]];
    EXPECT_EQ(m.primary_identity(), emails[i]);
    EXPECT_EQ(m.identities_size(), 1);
    EXPECT_EQ(m.identities(0).identity(), emails[i]);
  }
}

TEST_F(DBMigrationTest, RemoveLocalOnlyPhotos) {
  const int kCount = 10;

  typedef std::unordered_set<int64_t> PhotoIdSet;
  PhotoIdSet keep_photos;
  PhotoIdSet delete_photos;

  TestAssets test_assets;
  for (int i = 0; i < kCount; ++i) {
    NSURL* url = test_assets.AddTextImage(Format("%d", i));
    ALAsset* asset = test_assets.Lookup(url);
    const int64_t photo_id = photo_manager()->NewAssetPhoto(
        asset, EncodeAssetKey(ToString(url), AssetNewFingerprint(asset)),
        [asset thumbnail]);
    if ((i % 2) == 0) {
      keep_photos.insert(photo_id);

      DBHandle updates = state_.NewDBTransaction();
      PhotoHandle ph = photo_table()->LoadPhoto(photo_id, updates);
      ph->Lock();
      ph->mutable_images();
      ph->clear_upload_metadata();
      ph->clear_upload_full();
      ph->clear_upload_thumbnail();
      ph->SaveAndUnlock(updates);
      updates->Commit();
    } else {
      delete_photos.insert(photo_id);
    }
  }

  {
    DBHandle updates = state_.NewDBTransaction();
    migration_.RemoveLocalOnlyPhotos(updates);
    ASSERT(updates->Commit());
  }

  for (PhotoIdSet::iterator iter(keep_photos.begin());
       iter != keep_photos.end();
       ++iter) {
    PhotoHandle ph = photo_table()->LoadPhoto(*iter, db());
    EXPECT(ph.get());
    EXPECT_EQ(1, episode_table()->CountEpisodes(*iter, db()));
  }

  for (PhotoIdSet::iterator iter(delete_photos.begin());
       iter != delete_photos.end();
       ++iter) {
    PhotoHandle ph = photo_table()->LoadPhoto(*iter, db());
    EXPECT(!ph.get());
    EXPECT_EQ(0, episode_table()->CountEpisodes(*iter, db()));
  }
}

TEST_F(DBMigrationTest, ConvertAssetFingerprints) {
  if (kIOSVersion >= "7.0") {
    // Nothing to do, this migration does not run on iOS 7.
    return;
  }

  const int kCount = 10;

  typedef std::unordered_map<int64_t, PhotoMetadata> PhotoMetadataMap;
  PhotoMetadataMap orig_metadata;

  TestAssets test_assets;
  for (int i = 0; i < kCount; ++i) {
    NSURL* url = test_assets.AddTextImage(Format("%d", i));
    ALAsset* asset = test_assets.Lookup(url);
    const int64_t photo_id = photo_manager()->NewAssetPhoto(
        asset, EncodeAssetKey(ToString(url), AssetNewFingerprint(asset)),
        [asset thumbnail]);

    DBHandle updates = state_.NewDBTransaction();
    PhotoHandle ph = photo_table()->LoadPhoto(photo_id, updates);
    ph->Lock();

    EXPECT(IsPerceptualFingerprint(ph->asset_fingerprints(2)));
    ProtoRepeatedFieldRemoveElement(ph->mutable_asset_fingerprints(), 2);
    orig_metadata[photo_id] = *ph;

    ph->clear_asset_fingerprints();
    if (ph->asset_keys_size() > 1) {
      // TODO(peter): This can be removed when we no longer generate old
      // asset fingerprints.
      ProtoRepeatedFieldRemoveElement(ph->mutable_asset_keys(), 1);
    }

    for (int i = 0; i < ph->asset_keys_size(); ++i) {
      const string& asset_key = ph->asset_keys(i);
      Slice url;
      Slice fingerprint;
      ASSERT(DecodeAssetKey(asset_key, &url, &fingerprint));
      ASSERT(IsNewAssetFingerprint(fingerprint));
      const string old_asset_fingerprint = AssetOldFingerprint(asset);
      ph->set_asset_keys(i, EncodeAssetKey(url, old_asset_fingerprint));
      ph->add_asset_fingerprints(old_asset_fingerprint);
    }

    ph->SaveAndUnlock(updates);
    updates->Commit();
  }

  {
    DBHandle updates = state_.NewDBTransaction();
    migration_.ConvertAssetFingerprints(updates);
    ASSERT(updates->Commit());
  }

  for (PhotoMetadataMap::iterator iter(orig_metadata.begin());
       iter != orig_metadata.end();
       ++iter) {
    PhotoHandle ph = photo_table()->LoadPhoto(iter->first, db());
    EXPECT(ph.get());
    ph->clear_placemark();
    ph->clear_placemark_histogram();
    const PhotoMetadata& expected = iter->second;
    EXPECT_EQ(ToString(expected), ToString(*ph));
  }
}

TEST_F(DBMigrationTest, IndexPhotos) {
  const int kCount = 10;

  TestAssets test_assets;
  NSURL* urls[kCount];
  for (int i = 0; i < kCount; ++i) {
    urls[i] = test_assets.AddTextImage(Format("%d", i));
    ALAsset* asset = test_assets.Lookup(urls[i]);
    photo_manager()->NewAssetPhoto(
        asset, EncodeAssetKey(ToString(urls[i]), AssetNewFingerprint(asset)),
        [asset thumbnail]);
  }

  // All of the photos should have been indexed.
  ASSERT_EQ(13 * kCount, state_.image_index()->TotalTags(state_.db()));
  ASSERT_LE(13, state_.image_index()->UniqueTags(state_.db()));

  typedef std::unordered_map<int64_t, PhotoMetadata> PhotoMetadataMap;
  PhotoMetadataMap orig_metadata;

  {
    // Loop over the photos and rewrite the metadata so that it is in the
    // pre-indexed state. This involves removing the perceptual fingerprint.
    DBHandle updates = state_.NewDBTransaction();
    for (DB::PrefixIterator iter(state_.db(), DBFormat::photo_key());
         iter.Valid();
         iter.Next()) {
      const Slice value = iter.value();
      PhotoMetadata m;
      if (!m.ParseFromString(ToString(value))) {
        continue;
      }
      m.mutable_images()->mutable_tn()->set_size(0);
      m.clear_upload_thumbnail();
      m.clear_upload_full();
      for (int i = 0; i < m.asset_fingerprints_size(); ++i) {
        if (IsPerceptualFingerprint(m.asset_fingerprints(i))) {
          ProtoRepeatedFieldRemoveElement(m.mutable_asset_fingerprints(), i);
          --i;
        }
      }
      orig_metadata[m.id().local_id()] = m;

      m.clear_update_metadata();
      if (m.has_perceptual_fingerprint()) {
        state_.image_index()->Remove(
            m.perceptual_fingerprint(), ToString(m.id().local_id()), updates);
        m.clear_perceptual_fingerprint();
      }

      updates->PutProto(iter.key(), m);
    }

    ASSERT(updates->Commit());
  }

  ASSERT_EQ(0, state_.image_index()->TotalTags(state_.db()));
  ASSERT_EQ(0, state_.image_index()->UniqueTags(state_.db()));

  {
    DBHandle updates = state_.NewDBTransaction();
    migration_.IndexPhotos(updates);
    ASSERT(updates->Commit());
  }

  ASSERT_EQ(13 * kCount, state_.image_index()->TotalTags(state_.db()));
  ASSERT_LE(13, state_.image_index()->UniqueTags(state_.db()));

  // Verify the photos have been rewritten back to their post-indexing state.
  for (DB::PrefixIterator iter(state_.db(), DBFormat::photo_key());
       iter.Valid();
       iter.Next()) {
    const Slice value = iter.value();
    PhotoMetadata m;
    if (!m.ParseFromString(ToString(value))) {
      continue;
    }

    Slice url;
    Slice fingerprint;
    ASSERT(DecodeAssetKey(m.asset_keys(0), &url, &fingerprint));
    PhotoMetadata expected = orig_metadata[m.id().local_id()];

    EXPECT(IsNewAssetFingerprint(fingerprint));
    EXPECT(IsNewAssetFingerprint(m.asset_fingerprints(0)));
    const int perceptual_fingerprint_index = m.asset_fingerprints_size() - 1;
    EXPECT(IsPerceptualFingerprint(
               m.asset_fingerprints(perceptual_fingerprint_index)));
    ProtoRepeatedFieldRemoveElement(
        m.mutable_asset_fingerprints(), perceptual_fingerprint_index);

    expected.set_update_metadata(true);

    {
      // We have to compare the perceptual fingerprints separately because they
      // may not be identical. The perceptual fingerprint in the expected
      // metadata was generated from a square thumbnail. The perceptual
      // fingerprint in the migrated metadata is generated from an aspect ratio
      // thumbnail.
      const ImageFingerprint fingerprint = m.perceptual_fingerprint();
      const ImageFingerprint expected_fingerprint = expected.perceptual_fingerprint();
      m.clear_perceptual_fingerprint();
      expected.clear_perceptual_fingerprint();
      EXPECT_GE(12, ImageIndex::HammingDistance(fingerprint, expected_fingerprint));
    }

    // The rest of the metadata can be compared for equality.
    EXPECT_EQ(ToString(expected), ToString(m));
  }
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
