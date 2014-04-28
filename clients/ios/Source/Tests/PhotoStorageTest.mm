// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "DigestUtils.h"
#import "FileUtils.h"
#import "PathUtils.h"
#import "PhotoMetadata.pb.h"
#import "PhotoStorage.h"
#import "Testing.h"
#import "TestUtils.h"

namespace {

class PhotoStorageTest : public Test {
 public:
  PhotoStorageTest()
      : state_(dir()) {
  }

  bool Write(const string& filename, const string& data) {
    DBHandle updates = state_.NewDBTransaction();
    if (!photo_storage()->Write(filename, 0, data, updates)) {
      return false;
    }
    updates->Commit();
    return true;
  }

  bool AddExisting(const string& path, const string& filename,
                   const string& md5, const string& server_id) {
    DBHandle updates = state_.NewDBTransaction();
    if (!photo_storage()->AddExisting(
            path, filename, md5, server_id, updates)) {
      return false;
    }
    updates->Commit();
    return true;
  }

  void SetServerId(const string& filename, const string& server_id) {
    DBHandle updates = state_.NewDBTransaction();
    photo_storage()->SetServerId(filename, server_id, updates);
    updates->Commit();
  }

  void SetAssetSymlink(const string& filename, const string& server_id,
                       const string& asset_key) {
    photo_storage()->SetAssetSymlink(filename, server_id, asset_key);
  }

  string ReadAssetSymlink(const string& filename, const string& server_id) {
    return photo_storage()->ReadAssetSymlink(filename, server_id);
  }

  bool MaybeLinkServerId(const string& filename, const string& server_id,
                         const string& md5) {
    DBHandle updates = state_.NewDBTransaction();
    bool res = photo_storage()->MaybeLinkServerId(
        filename, server_id, md5, updates);
    if (res) {
      // A second call should be a no-op.
      CHECK(photo_storage()->MaybeLinkServerId(
                filename, server_id, md5, updates));
    }
    updates->Commit();
    return res;
  }

  void Delete(const string& filename) {
    DBHandle updates = state_.NewDBTransaction();
    photo_storage()->Delete(filename, updates);
    updates->Commit();
  }

  void DeleteAll(int64_t photo_id) {
    DBHandle updates = state_.NewDBTransaction();
    photo_storage()->DeleteAll(photo_id, updates);
    updates->Commit();
  }

  string Read(const string& filename) {
    const string filename_metadata =
        db()->Get<string>(DBFormat::photo_path_key(filename));
    return photo_storage()->Read(filename, filename_metadata);
  }

  int64_t Size(const string& filename) {
    return photo_storage()->Size(filename);
  }

  PhotoPathMetadata Metadata(const string& filename) {
    return photo_storage()->Metadata(filename);
  }

  string LowerBound(int64_t photo_id, int max_size) {
    string metadata;
    return photo_storage()->LowerBound(photo_id, max_size, &metadata);
  }

  string PhotoPathFilenames() {
    string s;
    for (DB::PrefixIterator iter(db(), DBFormat::photo_path_key(""));
         iter.Valid();
         iter.Next()) {
      if (!s.empty()) {
        s += ",";
      }
      s += iter.key().substr(DBFormat::photo_path_key("").size()).ToString();
    }
    return s;
  }

  string PhotoAccessFilenames() {
    string s;
    for (DB::PrefixIterator iter(db(), DBFormat::photo_path_access_key(""));
         iter.Valid();
         iter.Next()) {
      Slice t(iter.key().substr(DBFormat::photo_path_access_key("").size()));
      OrderedCodeDecodeVarint32Decreasing(&t);
      if (!s.empty()) {
        s += ",";
      }
      s += t.ToString();
    }
    return s;
  }

  string ListLocalPhotos() {
    vector<string> files;
    DirList(state_.photo_dir(), &files);
    for (vector<string>::iterator iter(files.begin()); iter != files.end(); ) {
      if (*iter == "tmp") {
        iter = files.erase(iter);
      } else {
        ++iter;
      }
    }
    std::sort(files.begin(), files.end());
    return ToString(files);
  }

  string ListServerPhotos() {
    vector<string> files;
    DirList(state_.server_photo_dir(), &files);
    std::sort(files.begin(), files.end());
    return ToString(files);
  }

  const DBHandle& db() { return state_.db(); }
  const string& photo_dir() { return state_.photo_dir(); }
  PhotoStorage* photo_storage() { return state_.photo_storage(); }

 protected:
  TestUIAppState state_;
};

TEST_F(PhotoStorageTest, ReadWriteDelete) {
  const string kData = "hello world";
  EXPECT(Write("foo", kData));
  EXPECT_EQ("foo", PhotoPathFilenames());
  EXPECT_EQ("foo", PhotoAccessFilenames());
  EXPECT_EQ(MD5(kData), Metadata("foo").md5());
  EXPECT_EQ(1, Metadata("foo").access_time());
  EXPECT(photo_storage()->Check());

  EXPECT_EQ(kData, Read("foo"));
  EXPECT_EQ(kData.size(), Size("foo"));

  Delete("foo");
  EXPECT_EQ("", PhotoPathFilenames());
  EXPECT_EQ("", PhotoAccessFilenames());
  EXPECT_EQ("", Read("foo"));
  EXPECT(photo_storage()->Check());
}

TEST_F(PhotoStorageTest, DeleteAll) {
  EXPECT(Write("1-foo", "foo"));
  EXPECT(Write("1-bar", "bar"));
  EXPECT(Write("2-foo", "foo"));
  EXPECT(Write("10-bar", "bar"));
  DeleteAll(1);

  EXPECT_EQ("10-bar,2-foo", PhotoPathFilenames());
  EXPECT_EQ("10-bar,2-foo", PhotoAccessFilenames());
}

TEST_F(PhotoStorageTest, Ordering) {
  // Write 2 photos within the same second.
  EXPECT(Write("foo", "1"));
  EXPECT(Write("bar", "2"));
  // The photos are ordered by name.
  EXPECT_EQ("bar,foo", PhotoAccessFilenames());
  EXPECT_EQ(1, Metadata("foo").access_time());
  EXPECT_EQ(1, Metadata("bar").access_time());
  EXPECT(photo_storage()->Check());

  // Access the 2 photos in different seconds.
  state_.set_now(100);
  EXPECT_EQ("2", Read("bar"));
  EXPECT_EQ(100, Metadata("bar").access_time());
  state_.set_now(101);
  EXPECT_EQ("1", Read("foo"));
  EXPECT_EQ(101, Metadata("foo").access_time());
  // The photos are ordered by access time.
  EXPECT_EQ("foo,bar", PhotoAccessFilenames());
  EXPECT(photo_storage()->Check());

  // The ordering doesn't change if the photos are accessed again within the
  // time granularity.
  state_.set_now(150);
  EXPECT_EQ("2", Read("bar"));
  EXPECT_EQ(100, Metadata("bar").access_time());
  EXPECT_EQ("foo,bar", PhotoAccessFilenames());
  EXPECT(photo_storage()->Check());
}

TEST_F(PhotoStorageTest, LowerBound) {
  EXPECT(Write("1-0120.jpg", "1"));
  EXPECT(Write("1-0480.jpg", "2"));
  EXPECT(Write("1-0960.jpg", "3"));
  EXPECT(Write("1-orig.jpg", "4"));
  EXPECT_EQ("1-0120.jpg", LowerBound(1, 1));
  EXPECT_EQ("1-0120.jpg", LowerBound(1, 120));
  EXPECT_EQ("1-0480.jpg", LowerBound(1, 121));
  EXPECT_EQ("1-0480.jpg", LowerBound(1, 480));
  EXPECT_EQ("1-0960.jpg", LowerBound(1, 481));
  EXPECT_EQ("1-0960.jpg", LowerBound(1, 960));
  EXPECT_EQ("1-orig.jpg", LowerBound(1, 961));
  EXPECT_EQ("1-orig.jpg", LowerBound(1, 100000));

  // We'll always return the largest resolution for a photo if nothing smaller
  // matches.
  EXPECT(Write("2-0120.jpg", "1"));
  EXPECT_EQ("2-0120.jpg", LowerBound(2, 120));
  EXPECT_EQ("2-0120.jpg", LowerBound(2, 121));
}

TEST_F(PhotoStorageTest, PhotoFilenameToLocalId) {
  struct {
    string filename;
    int64_t local_id;
  } testdata[] = {
    { "1-0.jpg", 1 },
    { "10-2.jpg", 10 },
    { "20-30", 20 },
  };
  for (int i = 0; i < ARRAYSIZE(testdata); ++i) {
    EXPECT_EQ(testdata[i].local_id,
              PhotoFilenameToLocalId(testdata[i].filename));
  }
}

TEST_F(PhotoStorageTest, PhotoFilenameToSize) {
  struct {
    string filename;
    int size;
  } testdata[] = {
    { "1-0.jpg", 0 },
    { "10-1.jpg", 1 },
    { "20-0120.jpg", kThumbnailSize },
    { "30-0480", kMediumSize },
    { "40-0960", kFullSize },
    { "40-orig.jpg", kOriginalSize },
    { "ph4kHJk35-0120.jpg", kThumbnailSize },
    { "ph4kHI-36-0960.jpg", kFullSize },
  };
  for (int i = 0; i < ARRAYSIZE(testdata); ++i) {
    EXPECT_EQ(testdata[i].size,
              PhotoFilenameToSize(testdata[i].filename));
  }
}

TEST_F(PhotoStorageTest, PhotoFilenameToType) {
  struct {
    string filename;
    int type;
  } testdata[] = {
    { "1-0.jpg", FILE_ORIGINAL },
    { "10-1.jpg", FILE_ORIGINAL },
    { "20-0120.jpg", FILE_THUMBNAIL },
    { "30-0480", FILE_MEDIUM },
    { "40-0960", FILE_FULL },
    { "40-orig.jpg", FILE_ORIGINAL },
    { "ph4kHJk35-0120.jpg", FILE_THUMBNAIL },
    { "ph4kHI-36-0960.jpg", FILE_FULL },
  };
  for (int i = 0; i < ARRAYSIZE(testdata); ++i) {
    EXPECT_EQ(testdata[i].type,
              PhotoFilenameToType(testdata[i].filename));
  }
}

TEST_F(PhotoStorageTest, GarbageCollect) {
  // Add 4 photos, including the photo_key database entries.
  const int64_t kPhotoIds[] = { 1, 2, 3};
  const vector<string> kFilenames = L(
      string(Format("%d-%04f", kPhotoIds[0], kThumbnailSize)),
      string(Format("%d-%04f", kPhotoIds[1], kMediumSize)),
      string(Format("%d-%04f", kPhotoIds[2], kFullSize)));

  for (int i = 0; i < ARRAYSIZE(kPhotoIds); ++i) {
    db()->Put(
        EncodeContentKey(DBFormat::photo_key(), kPhotoIds[i]), string());
    EXPECT(Write(kFilenames[i], "hello"));
  }

  // Delete the photo_key associated with kPhotoIds[0]
  db()->Delete(EncodeContentKey(DBFormat::photo_key(), kPhotoIds[0]));

  // Delete kFilenames[1].
  FileRemove(JoinPath(photo_dir(), kFilenames[1]));

  // Before garbage collection, we expect the photo path and access filenames
  // to be unchanged.
  EXPECT_EQ(Join(kFilenames, ","), PhotoPathFilenames());
  EXPECT_EQ(Join(kFilenames, ","), PhotoAccessFilenames());

  // Garbage collection should collect kFilenames[0] and kFilenames[1] leaving
  // only kFilenames[2].
  photo_storage()->GarbageCollect();
  EXPECT_EQ(kFilenames[2], PhotoPathFilenames());
  EXPECT_EQ(kFilenames[2], PhotoAccessFilenames());
}

TEST_F(PhotoStorageTest, LocalUsage) {
  const string kData = "aa";
  const int kFiles = 10;
  EXPECT_EQ(0, photo_storage()->local_bytes());

  // Deleting a non-existent file should not affect the local bytes count.
  Delete("foo");
  EXPECT_EQ(0, photo_storage()->local_bytes());

  for (int i = 0; i < kFiles; ++i) {
    EXPECT(Write(Format("%d", i), kData));
    EXPECT_EQ(kData.size() * (i + 1), photo_storage()->local_bytes());
    EXPECT_EQ(i + 1, photo_storage()->local_original_files());
  }
  for (int i = kFiles; i < 2 * kFiles; ++i) {
    WriteStringToFile(JoinPath(photo_dir(), "foo"), kData);
    EXPECT(AddExisting(JoinPath(photo_dir(), "foo"),
                       Format("%d", i), MD5(kData), Format("bar%d", i)));
    EXPECT_EQ(kData.size() * (i + 1), photo_storage()->local_bytes());
    EXPECT_EQ(i + 1, photo_storage()->local_original_files());
  }
  for (int i = 0; i < 2 * kFiles; ++i) {
    Delete(Format("%d", i));
    EXPECT_EQ(kData.size() * (2 * kFiles - i - 1),
              photo_storage()->local_bytes());
    EXPECT_EQ(2 * kFiles - i - 1,
              photo_storage()->local_original_files());
  }
}

TEST_F(PhotoStorageTest, LocalUsageUpgrade) {
  // Write a bunch of files to the photo storage.
  const string kData = "aaa";
  const int kFiles = 10;
  for (int i = 0; i < kFiles; ++i) {
    EXPECT(Write(Format("%d", i), kData));
  }

  // Delete the local usage databasekey.
  db()->Delete(DBFormat::metadata_key("local_bytes"));

  // Verify a new photo storage instance correctly recalculates the usage.
  ScopedPtr<PhotoStorage> photo_storage(new PhotoStorage(&state_));
  EXPECT_EQ(kFiles * kData.size(), photo_storage->local_bytes());
  EXPECT_EQ(kFiles, photo_storage->local_original_files());
}

TEST_F(PhotoStorageTest, Scanner) {
  // Write a bunch of files to the photo storage.
  const string kData = "aaaa";
  const int kFiles = 10;
  for (int i = 0; i < kFiles; ++i) {
    EXPECT(Write(Format("%d%d", i, i), kData));
  }

  // Verify that the scanner can iterate over the files properly.
  PhotoStorage::Scanner scanner(photo_storage());
  for (int i = 0; i < kFiles / 2; ++i) {
    EXPECT(scanner.Step(1));
    EXPECT_EQ(string(Format("%d%d", i, i)), scanner.pos());
    EXPECT_EQ(kData.size() * (i + 1), scanner.local_bytes());
    EXPECT_EQ(i + 1, scanner.local_original_files());
  }

  // Verify that the scanner notices deletions to files it has already scanned,
  // but not to ones it hasn't scanned.
  for (int i = 0; i < kFiles / 2; ++i) {
    Delete(Format("%d%d", i, i));
    EXPECT_EQ(kData.size() * (kFiles / 2 - i - 1), scanner.local_bytes());
    EXPECT_EQ(kFiles / 2 - i - 1, scanner.local_original_files());
  }
  for (int i = kFiles / 2; i < kFiles; ++i) {
    Delete(Format("%d%d", i, i));
    EXPECT_EQ(0, scanner.local_bytes());
    EXPECT_EQ(0, scanner.local_original_files());
  }

  // Verify that the scanner notices creation of files it has already scanned,
  // but not to ones it hasn't scanned.
  for (int i = 0; i < kFiles / 2; ++i) {
    EXPECT(Write(Format("%d", i), kData));
    EXPECT_EQ(kData.size() * (i + 1), scanner.local_bytes());
    EXPECT_EQ(i + 1, scanner.local_original_files());
  }
  for (int i = kFiles / 2; i < kFiles; ++i) {
    EXPECT(Write(Format("%d", i), kData));
    EXPECT_EQ(kData.size() * (kFiles / 2), scanner.local_bytes());
    EXPECT_EQ(kFiles / 2, scanner.local_original_files());
  }

  // Finish off the scan and verify the scanners local_bytes value equals the
  // photo storage value.
  EXPECT(scanner.Step(kFiles / 2));
  EXPECT_EQ(photo_storage()->local_bytes(), scanner.local_bytes());
  EXPECT_EQ(photo_storage()->local_original_files(),
            scanner.local_original_files());
  EXPECT(!scanner.Step(1));
  EXPECT(!scanner.Step(1));

  // Add one more file and verify the scanner updates appropriately.
  EXPECT(Write("a", kData));
  EXPECT_EQ(kData.size() * 11, scanner.local_bytes());
  EXPECT_EQ(11, scanner.local_original_files());
}

TEST_F(PhotoStorageTest, MaybeLinkServerId) {
  // Add a local photo and connect the server id.
  ASSERT(Write("foo-0120.jpg", "hello"));
  SetServerId("foo-0120.jpg", "bar");
  ASSERT_EQ("<foo-0120.jpg>", ListLocalPhotos());
  ASSERT_EQ("<bar-0120.jpg>", ListServerPhotos());
  // The local file exists and the MD5 is of the original data.
  ASSERT(MaybeLinkServerId("foo-0120.jpg", "bar", "world"));
  ASSERT_EQ(MD5("hello"), Metadata("foo-0120.jpg").md5());
  // Remove the local file.
  db()->Delete(DBFormat::photo_path_key("foo-0120.jpg"));
  FileRemove(JoinPath(photo_dir(), "foo-0120.jpg"));
  // The server file exists.
  ASSERT(MaybeLinkServerId("foo-0120.jpg", "bar", "world"));
  // The local file has been regenerated.
  ASSERT_EQ("<foo-0120.jpg>", ListLocalPhotos());
  ASSERT_EQ("<bar-0120.jpg>", ListServerPhotos());
  ASSERT_EQ("hello", Read("foo-0120.jpg"));
  // But the md5 has been updated to what the server told us.
  ASSERT_EQ("world", Metadata("foo-0120.jpg").md5());
  // Both the local and server file should get deleted.
  Delete("foo-0120.jpg");
  ASSERT_EQ("<>", ListLocalPhotos());
  ASSERT_EQ("<>", ListServerPhotos());
}

TEST_F(PhotoStorageTest, AssetSymlink) {
  SetAssetSymlink("foo-0120.jpg", "bar", "hello");
  ASSERT_EQ("<>", ListLocalPhotos());
  ASSERT_EQ("<bar-0120.jpg>", ListServerPhotos());
  ASSERT_EQ("hello", ReadAssetSymlink("foo-0120.jpg", "bar"));

  SetAssetSymlink("foo-orig.jpg", "bar", "world");
  ASSERT_EQ("<>", ListLocalPhotos());
  ASSERT_EQ("<bar-0120.jpg bar-orig.jpg>", ListServerPhotos());
  ASSERT_EQ("world", ReadAssetSymlink("foo-orig.jpg", "bar"));

  // TODO(peter): Test HaveAssetSymlink().
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
