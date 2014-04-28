// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

// TODO(pmattis): Run FixLocalUsage() periodically even if local_bytes isn't
// negative.

#import <unistd.h>
#import <leveldb/iterator.h>
#import <re2/re2.h>
#import "Analytics.h"
#import "AsyncState.h"
#import "DigestUtils.h"
#import "FileUtils.h"
#import "LazyStaticPtr.h"
#import "Logging.h"
#import "PathUtils.h"
#import "PhotoMetadata.pb.h"
#import "PhotoStorage.h"
#import "PhotoTable.h"
#import "ServerUtils.h"
#import "STLUtils.h"
#import "StringUtils.h"
#import "Timer.h"

namespace {

typedef PhotoStorage::Setting Setting;
const vector<Setting> kSettings =
    L(Setting(100LL * 1024 * 1024, "100 MB", "1,000 photos"),
      Setting(500LL * 1024 * 1024, "500 MB", "5,000 photos"),
      Setting(1LL * 1024 * 1024 * 1024, "1 GB", "10,000 photos"),
      Setting(5LL * 1024 * 1024 * 1024, "5 GB", "50,000 photos"),
      Setting(10LL * 1024 * 1024 * 1024, "10 GB", "100,000 photos"));

const string kFormatKey = DBFormat::metadata_key("photo_storage_format");
const string kFormatValue = "1";
const string kLastGarbageCollectionKey = DBFormat::metadata_key("last_garbage_collection");
const string kLocalBytesLimitKey = DBFormat::metadata_key("local_storage");
const string kLocalBytesKeyKey = DBFormat::metadata_key("local_bytes");
const string kLocalFilesKey = DBFormat::metadata_key("local_files");
const string kPhotoPathKeyPrefix = DBFormat::photo_path_key("");
const string kPhotoPathAccessKeyPrefix = DBFormat::photo_path_access_key("");
const string kRemoteUsageKey = DBFormat::metadata_key("remote_usage");

// Maintain a minimum headroom of 10 MB.
const int64_t kMinHeadroom = 10 * 1024 * 1024;
const WallTime kTimeGranularity = 60;
const WallTime kDay = 24 * 60 * 60;
const int kMD5Size = 32;

LazyStaticPtr<RE2, const char*> kViewfinderPhotoIdRE = { "([0-9]+)-.*" };
LazyStaticPtr<RE2, const char*> kViewfinderPhotoSizeRE = { ".*-([0-9]+).*" };

const DBRegisterKeyIntrospect kPhotoPathKeyIntrospect(
    kPhotoPathKeyPrefix, NULL, [](Slice value) {
      return DBIntrospect::FormatProto<PhotoPathMetadata>(value);
    });

const DBRegisterKeyIntrospect kPhotoPathAccessKeyIntrospect(
    kPhotoPathAccessKeyPrefix, [](Slice key) {
      if (!key.starts_with(kPhotoPathAccessKeyPrefix)) {
        return string();
      }
      key.remove_prefix(kPhotoPathAccessKeyPrefix.size());
      const uint32_t t = OrderedCodeDecodeVarint32Decreasing(&key);
      return string(Format("%s/%s", DBIntrospect::timestamp(t), key));
    }, NULL);

string AccessKey(const string& filename, uint32_t access_time) {
  string s;
  OrderedCodeEncodeVarint32Decreasing(&s, access_time);
  s.append(filename);
  return DBFormat::photo_path_access_key(s);
}

int64_t DefaultBytesLimit() {
  // Set the default amount of local storage to use based on the user's total
  // disk space.
  const int64_t kGB = 1LL * 1024 * 1024 * 1024;
  const int64_t total_disk_space = TotalDiskSpace();
  if (total_disk_space <= 8 * kGB) {
    return kSettings[0].value;
  }
  if (total_disk_space <= 32 * kGB) {
    return kSettings[2].value;
  }
  return kSettings[3].value;
}

}  // namespace

const int kThumbnailSize = 120;
const int kMediumSize = 480;
const int kFullSize = 960;
const int kOriginalSize = 1000000000;

string PhotoSizeSuffix(int size) {
  if (size == kOriginalSize) {
    return "orig";
  }
  return Format("%04d", size);
}

string PhotoFilename(const string& server_id, const string& name) {
  return Format("%s-%s.jpg", server_id, name);
}

string PhotoFilename(int64_t local_id, const string& name) {
  return Format("%d-%s.jpg", local_id, name);
}

string PhotoFilename(const string& server_id, int size) {
  return PhotoFilename(server_id, PhotoSizeSuffix(size));
}

string PhotoFilename(const PhotoId& photo_id, const string& name) {
  return PhotoFilename(photo_id.local_id(), name);
}

string PhotoFilename(int64_t local_id, int size) {
  return PhotoFilename(local_id, PhotoSizeSuffix(size));
}

string PhotoFilename(const PhotoId& photo_id, int size) {
  return PhotoFilename(photo_id, PhotoSizeSuffix(size));
}

string PhotoThumbnailFilename(const PhotoId& photo_id) {
  return PhotoFilename(photo_id, kThumbnailSize);
}

string PhotoThumbnailFilename(int64_t local_id) {
  return PhotoFilename(local_id, kThumbnailSize);
}

string PhotoMediumFilename(const PhotoId& photo_id) {
  return PhotoFilename(photo_id, kMediumSize);
}

string PhotoMediumFilename(int64_t local_id) {
  return PhotoFilename(local_id, kMediumSize);
}

string PhotoFullFilename(const PhotoId& photo_id) {
  return PhotoFilename(photo_id, kFullSize);
}

string PhotoFullFilename(int64_t local_id) {
  return PhotoFilename(local_id, kFullSize);
}

string PhotoOriginalFilename(const PhotoId& photo_id) {
  return PhotoFilename(photo_id, kOriginalSize);
}

string PhotoOriginalFilename(int64_t local_id) {
  return PhotoFilename(local_id, kOriginalSize);
}

string PhotoBasename(const string& dir, const string& path) {
  Slice s(path);
  s.remove_prefix(dir.size() + 1);
  return s.ToString();
}

int64_t PhotoFilenameToLocalId(const Slice& filename) {
  int64_t local_id = -1;
  RE2::FullMatch(filename, *kViewfinderPhotoIdRE, &local_id);
  return local_id;
}

int PhotoFilenameToSize(const Slice& filename) {
  int size = kOriginalSize;
  RE2::FullMatch(filename, *kViewfinderPhotoSizeRE, &size);
  return size;
}

int PhotoFilenameToType(const Slice& filename) {
  const int size = PhotoFilenameToSize(filename);
  switch (size) {
    case kThumbnailSize:
      return FILE_THUMBNAIL;
    case kMediumSize:
      return FILE_MEDIUM;
    case kFullSize:
      return FILE_FULL;
    case kOriginalSize:
    default:
      return FILE_ORIGINAL;
  }
}

PhotoStorage::Scanner::Scanner(PhotoStorage* photo_storage)
    : photo_storage_(photo_storage),
      iter_(db()->NewIterator()),
      local_bytes_(0) {
  memset(local_files_, 0, sizeof(local_files_));
  photo_storage_->AddScanner(this);
}

PhotoStorage::Scanner::~Scanner() {
  photo_storage_->RemoveScanner(this);
}

bool PhotoStorage::Scanner::Step(int num_files) {
  MutexLock l(&mu_);
  for (int i = 0; num_files < 0 || i < num_files; ++i) {
    // Only advance the iterator just before we will use its value.
    if (pos_.empty()) {
      iter_->Seek(kPhotoPathKeyPrefix);
    } else if (iter_->Valid()) {
      iter_->Next();
    }
    if (!iter_->Valid()) {
      return false;
    }
    const Slice key(ToSlice(iter_->key()));
    if (!key.starts_with(kPhotoPathKeyPrefix)) {
      // We've reached the end of the photo_path_key keys. Set pos_ to the
      // "inifity" key so that the scanner will capture all future local_usage
      // increments.
      pos_ = "\xff";
      return false;
    }
    // Set pos_ to the name of the last file the scanner examined.
    pos_ = key.substr(kPhotoPathKeyPrefix.size());
    const Slice value(ToSlice(iter_->value()));
    PhotoPathMetadata m;
    m.ParseFromArray(value.data(), value.size());
    if (m.has_size()) {
      local_bytes_ += m.size();
    } else {
      local_bytes_ += FileSize(photo_storage_->PhotoPath(pos_));
    }
    local_files_[PhotoFilenameToType(pos_)] += 1;
  }
  return true;
}

void PhotoStorage::Scanner::StepNAndBackground(
    int files_per_step, Callback<void ()> done) {
  if (!Step(files_per_step)) {
    done();
    return;
  }
  // Step through the remaining files on a background thread.
  photo_storage_->async_->dispatch_background([this, done] {
      Step();
      done();
    });
}

void PhotoStorage::Scanner::IncrementLocalUsage(
    const string& filename, int64_t delta) {
  MutexLock l(&mu_);
  // Note that pos_ is the name of the last file the scanner examined. Only
  // apply the delta if it is for a filename that has already been
  // scanned.
  //
  // Note the use of <= is critical because we don't want there to be any
  // window where a file can slip in. For example, if pos_ were instead the
  // name of the next file the scanner will examine and the comparison below
  // was "filename < pos_" it would be possible for a file to be added to the
  // photo store but slip past the scanner. Consider the scanner saw the file
  // "aa" and the next file it will examine is "bb" (i.e. pos="bb"). If the
  // file "b" is created ("aa" < "b" < "bb"), the scanner would miss it.
  if (filename <= pos_) {
    local_bytes_ += delta;
    local_files_[PhotoFilenameToType(filename)] += (delta < 0) ? -1 : +1;
  }
}

PhotoStorage::PhotoStorage(AppState* state)
    : state_(state),
      async_(new AsyncState(state->async())),
      photo_dir_(state_->photo_dir()),
      server_photo_dir_(state_->server_photo_dir()),
      local_bytes_limit_(state_->db()->Get<int64_t>(
                             kLocalBytesLimitKey, DefaultBytesLimit())),
      local_bytes_(state_->db()->Get<int64_t>(kLocalBytesKeyKey, -1)),
      gc_(true) {
  for (int i = 0; i < ARRAYSIZE(local_files_); ++i) {
    local_files_[i] = state_->db()->Get<int>(
        Format("%s/%d", kLocalFilesKey, i), -1);
  }

  if (local_bytes_ < 0 ||
      state_->db()->Get<string>(kFormatKey) != kFormatValue) {
    FixLocalUsage();
  } else {
    VLOG("photo storage: local usage: %.2f MB",
         local_bytes_ / (1024.0 * 1024.0));
    state_->analytics()->LocalUsage(
        local_bytes_, local_files_[0], local_files_[1],
        local_files_[2], local_files_[3]);
  }

  if (state_->db()->GetProto(kRemoteUsageKey, &remote_usage_)) {
    VLOG("remote usage: %s", remote_usage_);
  }

  // Only kick off garbage collection if it has been more than a day since
  // garbage collection was last run.
  const WallTime last_garbage_collection =
      state_->db()->Get<WallTime>(kLastGarbageCollectionKey);
  if (WallTime_Now() - last_garbage_collection >= kDay) {
    if (last_garbage_collection == 0) {
      // No need to garbage collect the first time that app is started.
      state_->db()->Put(kLastGarbageCollectionKey, WallTime_Now());
    } else {
      async_->dispatch_after_background(
          15, [this, last_garbage_collection] {
            LOG("photo storage: garbage collect: last collection: %s",
                WallTimeFormat("%F %T", last_garbage_collection));
            GarbageCollect();
          });
    }
  }
}

PhotoStorage::~PhotoStorage() {
  async_.reset(NULL);
}

bool PhotoStorage::Write(
    const string& filename, int parent_size,
    const Slice& data, const DBHandle& updates) {
  const string key = DBFormat::photo_path_key(filename);
  if (IsUncommittedFile(filename) || updates->Exists(key)) {
    // Don't overwrite an existing file.
    return false;
  }

  updates->AddCommitTrigger(key, [this, filename]{
      RemoveUncommittedFile(filename);
    });
  AddUncommittedFile(filename);

  // TODO(pmattis): Gracefully handle out-of-space errors.
  if (!WriteStringToFile(PhotoPath(filename), data)) {
    RemoveUncommittedFile(filename);
    return false;
  }
  // Update the last access time.
  PhotoPathMetadata m;
  m.set_md5(MD5(data));
  m.set_access_time(state_->WallTime_Now());
  m.set_size(data.size());
  if (parent_size > 0) {
    m.set_parent_size(parent_size);
  }
  updates->PutProto(key, m);
  updates->Put(AccessKey(filename, m.access_time()), string());
  IncrementLocalUsage(filename, m.size(), updates);
  return true;
}

bool PhotoStorage::AddExisting(
    const string& path, const string& filename,
    const string& md5, const string& server_id, const DBHandle& updates) {
  if (IsUncommittedFile(filename)) {
    // Don't overwrite an existing file.
    return false;
  }

  // Protect "filename" from being removed until the database update commits.
  const string key = DBFormat::photo_path_key(filename);
  updates->AddCommitTrigger(key, [this, filename] {
      RemoveUncommittedFile(filename);
    });
  AddUncommittedFile(filename);

  // TODO(pmattis): Gracefully handle out-of-space errors.
  const string new_path = PhotoPath(filename);
  if (!FileRename(path, new_path)) {
    RemoveUncommittedFile(filename);
    return false;
  }
  // Update the last access time.
  PhotoPathMetadata m;
  if (!server_id.empty()) {
    const string server_path = PhotoServerPath(filename, server_id);
    if (link(new_path.c_str(), server_path.c_str()) == 0) {
      m.set_server_id(server_id);
    }
  }
  m.set_md5(md5);
  m.set_access_time(state_->WallTime_Now());
  m.set_size(FileSize(new_path));
  updates->PutProto(key, m);
  updates->Put(AccessKey(filename, m.access_time()), string());
  IncrementLocalUsage(filename, m.size(), updates);
  return true;
}

void PhotoStorage::SetServerId(
    const string& filename, const string& server_id, const DBHandle& updates) {
  const string key = DBFormat::photo_path_key(filename);
  PhotoPathMetadata m;
  if (!state_->db()->GetProto(key, &m)) {
    return;
  }

  // Construct the old and new paths.
  const string old_path = PhotoPath(filename);
  const string new_path = PhotoServerPath(filename, server_id);

  // Update the metadata to point to the new path.
  m.set_server_id(server_id);
  state_->db()->PutProto(key, m);

  // Link the old path to the new path.
  link(old_path.c_str(), new_path.c_str());
}

void PhotoStorage::SetAssetSymlink(
    const string& filename, const string& server_id,
    const string& asset_key) {
  const string symlink_path = PhotoServerPath(filename, server_id);
  FileRemove(symlink_path);
  if (symlink(asset_key.c_str(), symlink_path.c_str()) == -1) {
    LOG("photo storage: symlink failed: %s -> %s: %d (%s)",
        asset_key, symlink_path, errno, strerror(errno));
  }
}

string PhotoStorage::ReadAssetSymlink(
    const string& filename, const string& server_id) {
  const string symlink_path = PhotoServerPath(filename, server_id);
  char buf[1024];
  int n = readlink(symlink_path.c_str(), buf, ARRAYSIZE(buf));
  if (n == -1) {
    return string();
  }
  return string(buf, n);
}

bool PhotoStorage::HaveAssetSymlink(
    const string& filename, const string& server_id,
    const string& asset_key) {
  const string asset_symlink = ReadAssetSymlink(filename, server_id);
  if (asset_symlink.empty()) {
    return false;
  }
  Slice url;
  Slice fingerprint;
  if (!DecodeAssetKey(asset_key, &url, &fingerprint)) {
    return false;
  }
  if (asset_symlink == fingerprint) {
    // Symlinks are supposed to contain asset fingerprints.
    return true;
  }
  Slice symlink_url;
  Slice symlink_fingerprint;
  if (!DecodeAssetKey(asset_symlink, &symlink_url, &symlink_fingerprint)) {
    return false;
  }
  // But they used to contain asset urls.
  if (symlink_url != url) {
    return false;
  }
  // Replace the existing asset url symlink with the asset fingerprint.
  SetAssetSymlink(filename, server_id, fingerprint.ToString());
  DCHECK_EQ(fingerprint, ReadAssetSymlink(filename, server_id));
  return true;
}

void PhotoStorage::Delete(const string& filename, const DBHandle& updates) {
  PhotoPathMetadata m;
  const bool exists =
      state_->db()->GetProto(DBFormat::photo_path_key(filename), &m);
  // Delete the image before deleting from the database. If we crash before
  // deleting from the database, we'll just attempt another deletion the next
  // time we startup.
  const string path = PhotoPath(filename);
  const int64_t size = m.has_size() ? m.size() : FileSize(path);
  VLOG("photo storage: delete %s: %d", filename, size);
  // Note that we remove the file on disk even if the metadata exists because
  // we might be called via the garbage collection code path.
  FileRemove(path);
  if (m.has_server_id()) {
    FileRemove(PhotoServerPath(filename, m.server_id()));
  }
  if (m.has_access_time()) {
    updates->Delete(AccessKey(filename, m.access_time()));
  }
  if (exists) {
    IncrementLocalUsage(filename, -size, updates);
  }
  updates->Delete(DBFormat::photo_path_key(filename));
}

void PhotoStorage::DeleteAll(int64_t photo_id, const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, DBFormat::photo_path_key(Format("%s-", photo_id)));
       iter.Valid();
       iter.Next()) {
    Delete(iter.key().substr(kPhotoPathKeyPrefix.size()).ToString(), updates);
  }
}

string PhotoStorage::Read(const string& filename, const string& metadata) {
  string s;
  if (!ReadFileToString(PhotoPath(filename), &s)) {
    return string();
  }
  Touch(filename, metadata);
  return s;
}

void PhotoStorage::Touch(const string& filename, const string& metadata) {
  // Decode the filename metadata.
  PhotoPathMetadata m;
  m.ParseFromString(metadata);
  // Only update the access time if kTimeGranularity seconds have passed since
  // the last update.
  const WallTime now = state_->WallTime_Now();
  if (!m.has_access_time() ||
      (fabs(now - m.access_time()) >= kTimeGranularity)) {
    // TODO(pmattis): Batch access time updates together so that they are only
    // written once per X seconds.
    DBHandle updates = state_->NewDBTransaction();
    updates->Delete(AccessKey(filename, m.access_time()));
    m.set_access_time(now);
    updates->PutProto(DBFormat::photo_path_key(filename), m);
    updates->Put(AccessKey(filename, m.access_time()), string());
    updates->Commit(false);
  }
}

bool PhotoStorage::MaybeLinkServerId(
    const string& filename, const string& server_id,
    const string& md5, const DBHandle& updates) {
  const string local_path = PhotoPath(filename);
  if (updates->Exists(DBFormat::photo_path_key(filename)) &&
      FileExists(local_path)) {
    return true;
  }

  const string server_path = PhotoServerPath(filename, server_id);
  const int64_t size = FileSize(server_path);
  if (size <= 0) {
    return false;
  }

  // If the server didn't give us an MD5, don't trust the local data.
  if (md5.empty()) {
    FileRemove(server_path);
    return false;
  }

  if (link(server_path.c_str(), local_path.c_str()) != 0) {
    return false;
  }

  // Update the last access time.
  PhotoPathMetadata m;
  m.set_server_id(server_id);
  m.set_md5(md5);
  m.set_access_time(state_->WallTime_Now());
  m.set_size(size);
  updates->PutProto(DBFormat::photo_path_key(filename), m);
  updates->Put(AccessKey(filename, m.access_time()), string());
  IncrementLocalUsage(filename, m.size(), updates);
  return true;
}

bool PhotoStorage::Exists(const string& filename) {
  return state_->db()->Exists(DBFormat::photo_path_key(filename));
}

int64_t PhotoStorage::Size(const string& filename) {
  // Note that we want to check the actual file size on disk and not just the
  // size in PhotoPathMetadata so that this doubles as a check for the file's
  // existence.
  return ::FileSize(PhotoPath(filename));
}

PhotoPathMetadata PhotoStorage::Metadata(const string& filename) {
  PhotoPathMetadata m;
  state_->db()->GetProto(DBFormat::photo_path_key(filename), &m);
  return m;
}

string PhotoStorage::LowerBound(
    int64_t photo_id, int max_size, string* metadata) {
  const string max_key =
      DBFormat::photo_path_key(PhotoFilename(photo_id, max_size));
  string filename;
  for (DB::PrefixIterator iter(state_->db(), DBFormat::photo_path_key(Format("%d-", photo_id)));
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const Slice value = iter.value();
    filename = key.ToString();
    *metadata = value.ToString();
    if (key >= max_key) {
      break;
    }
  }
  if (filename.empty()) {
    return string();
  }
  // Strip off the prefix.
  return filename.substr(kPhotoPathKeyPrefix.size());
}

void PhotoStorage::GarbageCollect() {
  {
    MutexLock l(&mu_);
    if (!gc_) {
      // We've already collected garbage in this instance of the app. Garbage
      // is only created when the app crashes unexpectedly.
      return;
    }
    gc_ = false;
  }

  // PhotoStorage updates the filesystem before updating the database. See
  // Write(), AddExisting() and Delete(). We want to garbage collect database
  // keys for which there is not a corresponding file on disk. Before listing
  // the on disk images, grab a snapshot of the database state.
  DBHandle snapshot = state_->NewDBSnapshot();
  DBHandle updates = state_->NewDBTransaction();

  StringSet files;

  {
    // Populate a set of all of the filenames that exist in the photo
    // directory.
    LOG("photo storage: garbage collection: list files");
    vector<string> files_vec;
    DirList(photo_dir_, &files_vec);
    for (int i = 0; i < files_vec.size(); ++i) {
      // TODO(pmattis): This test for "tmp" can go away soon now that we're
      // placing temporary (downloading) photos in /tmp/photos.
      if (files_vec[i] != "tmp") {
        files.insert(files_vec[i]);
      }
    }
  }

  // Loop over all of the photo paths listed in the database and check to see
  // that there is corresponding photo metadata. Garbage collect any photo path
  // and the on disk image for which there is not associated photo metadata or
  // for which the on-disk image does not exist.
  LOG("photo storage: garbage collection: list database keys");
  for (DB::PrefixIterator iter(snapshot, kPhotoPathKeyPrefix);
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const string filename = key.substr(kPhotoPathKeyPrefix.size()).ToString();
    if (IsUncommittedFile(filename)) {
      LOG("photo storage: garbage collecting (skipping uncommited file): %s",
          filename);
      continue;
    }
    const int64_t local_id = PhotoFilenameToLocalId(filename);
    if (local_id == -1) {
      continue;
    }
    if (!state_->photo_table()->Exists(local_id, snapshot)) {
      // We have a photo-path-key for a photo that does not exist in the
      // PhotoTable.
      LOG("photo storage: garbage collecting (photo-id does not exist): %d: %s",
          local_id, filename);
      Delete(filename, updates);
    } else if (!ContainsKey(files, filename) &&
               state_->db()->Exists(key) &&
               !FileExists(PhotoPath(filename))) {
      // We have a photo-path-key for an image that does not exist on
      // disk. It is possible a concurrent deletion of the image occurred,
      // but it is safe for us to re-delete the image in that case.
      //
      // NOTE(peter): We need the !FileExists() test because the photo
      // could have been deleted and recreated between the creation of the
      // database snapshot and the listing of the image files on disk. The
      // ContainsKey() test can be viewed as an optimization that avoids
      // the FileExists() test in most cases.
      LOG("photo storage: garbage collecting (image does not exist): %d: %s",
          local_id, filename);
      Delete(filename, updates);
    }
  }

  // Loop over the on disk images in the photo directory and garbage collect
  // any image for which there is not a corresponding photo path in the
  // database.
  for (StringSet::iterator iter(files.begin());
       iter != files.end();
       ++iter) {
    const string& filename = *iter;
    if (IsUncommittedFile(filename)) {
      LOG("photo storage: garbage collecting (skipping uncommited file): %s",
          filename);
      continue;
    }
    // The FileExists() check prevents spurious log messages in the case where
    // the image is deleted between the time it is listed and now.
    if (!state_->db()->Exists(DBFormat::photo_path_key(filename)) &&
        FileExists(PhotoPath(filename))) {
      LOG("photo storage: garbage collecting (photo-path-key does not exist): %s",
          filename);
      Delete(filename, updates);
    }
  }

  updates->Put(kLastGarbageCollectionKey, WallTime_Now());
  updates->Commit();
}

bool PhotoStorage::Check() {
  // Each filename listed under photo_path_key with a non-zero access time
  // should have a corresponding entry under photo_path_access_key.
  bool ok = true;
  for (DB::PrefixIterator iter(state_->db(), kPhotoPathKeyPrefix);
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const Slice value = iter.value();
    PhotoPathMetadata m;
    m.ParseFromArray(value.data(), value.size());
    if (m.has_access_time()) {
      const string filename =
          key.substr(kPhotoPathKeyPrefix.size()).ToString();
      if (!state_->db()->Exists(AccessKey(filename, m.access_time()))) {
        LOG("photo storage: photo path access key does not exist: %s %s",
            filename, WallTimeFormat("%F-%T", m.access_time()));
        ok = false;
      }
    }
  }

  // Each filename should be listed only once under photo_path_access_key. And
  // every entry under photo_path_access_key should be pointed to by the
  // PhotoPathMetadata under photo_path_key.
  std::unordered_set<string> filenames;
  for (DB::PrefixIterator iter(state_->db(), kPhotoPathAccessKeyPrefix);
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    Slice s(key.substr(kPhotoPathAccessKeyPrefix.size()));
    const uint32_t access_time = OrderedCodeDecodeVarint32Decreasing(&s);
    const string filename = s.ToString();
    if (ContainsKey(filenames, filename)) {
      LOG("photo storage: filename occurs twice in photo path access: %s",
          filename);
      ok = false;
    }
    filenames.insert(filename);

    const string d = state_->db()->Get<string>(
        DBFormat::photo_path_key(filename), string());
    PhotoPathMetadata m;
    m.ParseFromString(d);
    if (key != AccessKey(filename, m.access_time())) {
      LOG("photo storage: photo path/access time mismatch: %s != %s",
          WallTimeFormat("%F-%T", access_time),
          WallTimeFormat("%F-%T", m.access_time()));
      ok = false;
    }
  }

  return ok;
}

string PhotoStorage::PhotoPath(const Slice& filename) {
  return JoinPath(photo_dir_, filename);
}

string PhotoStorage::PhotoServerPath(
    const Slice& filename, const string& server_id) {
  if (server_id.empty()) {
    return string();
  }
  const string server_filename = PhotoFilename(
      server_id, PhotoFilenameToSize(filename));
  return JoinPath(server_photo_dir_, server_filename);
}

void PhotoStorage::IncrementLocalUsage(
    const string& filename, int64_t delta, const DBHandle& updates) {
  {
    // The PhotoStorage class tracks the disk space used by all of the files
    // under its control in the local_usage_ member. Under various crash
    // scenarious, this value can get out of date. The Scanner class exists to
    // refresh the local_usage_ value. A scanner works by iterating over the
    // filenames in a photo storage in sorted order. The tricky part is that we
    // don't pause the photo storage while the scanner is operating. The user
    // might add a new picture or delete an existing picture. We keep the
    // scanner computation correct by telling any active scanners about changes
    // to files and letting the scanner determine if it should apply the change
    // or not based on whether it has already examined the file or not.
    MutexLock l(&mu_);
    for (ScannerSet::iterator iter(scanners_.begin());
         iter != scanners_.end();
         ++iter) {
      (*iter)->IncrementLocalUsage(filename, delta);
    }

    // If the local_usage value is invalid, don't adjust it further.
    if (local_bytes_ < 0) {
      return;
    }

    const int type = PhotoFilenameToType(filename);
    local_bytes_ += delta;
    local_files_[type] += (delta < 0) ? -1 : +1;
    if (local_bytes_ >= 0) {
      updates->Put(kLocalBytesKeyKey, local_bytes_);
      updates->Put(string(Format("%s/%d", kLocalFilesKey, type)),
                   local_files_[type]);
      // Run the changed callback after we've released mu_.
      async_->dispatch_after_main(0, [this] {
          changed_.Run();
        });
      return;
    }
  }

  // This increment whacked the local_usage value out of alignment. Fire off a
  // scanner to fix it.
  FixLocalUsage();
}

void PhotoStorage::FixLocalUsage() {
  WallTimer timer;
  Scanner* scanner = new Scanner(this);
  scanner->StepNAndBackground(100, [this, scanner, timer] {
      ScopedPtr<Scanner> scanner_deleter(scanner);

      MutexLock l(&mu_);
      local_bytes_ = scanner->local_bytes();
      for (int i = 0; i < ARRAYSIZE(local_files_); ++i) {
        local_files_[i] = scanner->local_files(i);
      }
      LOG("photo storage: fixed local usage: bytes=%d, files=%d: %.3f ms",
          local_bytes_, local_files_[0] + local_files_[1] +
          local_files_[2] + local_files_[3],
          timer.Milliseconds());
      DBHandle updates = state_->NewDBTransaction();
      updates->Put(kLocalBytesKeyKey, local_bytes_);
      for (int i = 0; i < ARRAYSIZE(local_files_); ++i) {
        updates->Put(string(Format("%s/%d", kLocalFilesKey, i)),
                     local_files_[i]);
      }
      updates->Put(kFormatKey, kFormatValue);
      updates->Commit();
      state_->analytics()->LocalUsage(
          local_bytes_, local_files_[0], local_files_[1],
          local_files_[2], local_files_[3]);
      // Run the changed callback on the main thread and after we've released
      // mu_.
      async_->dispatch_after_main(0, [this] {
          changed_.Run();
        });
    });
}

void PhotoStorage::AddScanner(Scanner* scanner) {
  MutexLock l(&mu_);
  scanners_.insert(scanner);
}

void PhotoStorage::RemoveScanner(Scanner* scanner) {
  MutexLock l(&mu_);
  scanners_.erase(scanner);
}

void PhotoStorage::AddUncommittedFile(const string& filename) {
  MutexLock l(&mu_);
  uncommitted_files_.insert(filename);
}

void PhotoStorage::RemoveUncommittedFile(const string& filename) {
  MutexLock l(&mu_);
  uncommitted_files_.erase(filename);
}

bool PhotoStorage::IsUncommittedFile(const string& filename) {
  MutexLock l(&mu_);
  return ContainsKey(uncommitted_files_, filename);
}

void PhotoStorage::set_local_bytes_limit(int64_t v) {
  local_bytes_limit_ = v;
  state_->db()->Put(kLocalBytesLimitKey, local_bytes_limit_);
}

const vector<Setting>& PhotoStorage::settings() const {
  return kSettings;
}

int PhotoStorage::setting_index(int64_t value) const {
  for (int i = 0; i < kSettings.size(); ++i) {
    if (value <= kSettings[i].value) {
      return i;
    }
  }
  return kSettings.size() - 1;
}

void PhotoStorage::update_remote_usage(const UsageMetadata& usage) {
  MutexLock l(&mu_);
  remote_usage_.MergeFrom(usage);
  state_->db()->PutProto(kRemoteUsageKey, remote_usage_);
}

UsageMetadata PhotoStorage::remote_usage() const {
  MutexLock l(&mu_);
  return remote_usage_;
}

// local variables:
// mode: c++
// end:
