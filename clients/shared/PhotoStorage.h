// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_PHOTO_STORAGE_H
#define VIEWFINDER_PHOTO_STORAGE_H

#import <unordered_set>
#import "AppState.h"
#import "Callback.h"
#import "DB.h"
#import "Mutex.h"
#import "UserMetadata.pb.h"

class AsyncState;
class PhotoPathMetadata;

extern const int kThumbnailSize;
extern const int kMediumSize;
extern const int kFullSize;
extern const int kOriginalSize;

enum PhotoFileType {
  FILE_THUMBNAIL = 0,
  FILE_MEDIUM = 1,
  FILE_FULL = 2,
  FILE_ORIGINAL = 3,
};

// Various routines for generate and manipulating photo filenames.
string PhotoSizeSuffix(int size);
string PhotoFilename(const string& server_id, const string& name);
string PhotoFilename(const string& server_id, int size);
string PhotoFilename(int64_t local_id, const string& name);
string PhotoFilename(const PhotoId& photo_id, const string& name);
string PhotoFilename(int64_t local_id, int size);
string PhotoFilename(const PhotoId& photo_id, int size);
string PhotoThumbnailFilename(const PhotoId& photo_id);
string PhotoThumbnailFilename(int64_t local_id);
string PhotoMediumFilename(const PhotoId& photo_id);
string PhotoMediumFilename(int64_t local_id);
string PhotoFullFilename(const PhotoId& photo_id);
string PhotoFullFilename(int64_t local_id);
string PhotoOriginalFilename(const PhotoId& photo_id);
string PhotoOriginalFilename(int64_t local_id);
// Extracts the base photo filename from a full path.
string PhotoBasename(const string& dir, const string& path);
// Extracts the local photo id from a filename.
int64_t PhotoFilenameToLocalId(const Slice& filename);
// Extracts the size from a filename.
int PhotoFilenameToSize(const Slice& filename);
int PhotoFilenameToType(const Slice& filename);

// The photo storage class is the low-level interface for writing, reading and
// deleting photos on disk. In addition to wrapping the filesystem routines, it
// tracks access times and how much disk space is being used and reclaims disk
// space when a configurable threshold is reached.
class PhotoStorage {
 public:
  // A scanner allows asynchronous iteration over the files in a photo storage,
  // computing a value (currently just local-usage) as it goes. Care is taken
  // to correctly handle mutations to the photo store that occur concurrently
  // with the scan.
  class Scanner {
   public:
    Scanner(PhotoStorage* photo_storage);
    ~Scanner();

    // Step through the next num_files files.
    bool Step(int num_files = -1);
    // Asynchronously step through all of the remaining files in the
    // scanner. The first step is performed synchronously in
    // files_per_step. The done block is called when the scanner reaches the
    // end.
    void StepNAndBackground(int files_per_step, Callback<void ()> done);
    void IncrementLocalUsage(const string& filename, int64_t delta);

    const DBHandle& db() { return photo_storage_->state_->db(); }
    const Slice& pos() const { return pos_; }
    int64_t local_bytes() const { return local_bytes_; }
    int local_files(int i) const { return local_files_[i]; }
    int local_thumbnail_files() const { return local_files_[0]; }
    int local_medium_files() const { return local_files_[1]; }
    int local_full_files() const { return local_files_[2]; }
    int local_original_files() const { return local_files_[3]; }

   private:
    PhotoStorage* const photo_storage_;
    Mutex mu_;
    ScopedPtr<leveldb::Iterator> iter_;
    const string prefix_;
    Slice pos_;
    int64_t local_bytes_;
    int local_files_[4];
  };

  friend class Scanner;
  typedef std::unordered_set<Scanner*> ScannerSet;

  // A structure containing a local storage setting (value, title string and
  // detail string) for use by SettingViewController.
  struct Setting {
    Setting(int64_t v = 0,
            const string& t = string(),
            const string& d = string())
        : value(v),
          title(t),
          detail(d) {
    }
    int64_t value;
    string title;
    string detail;
  };

 public:
  PhotoStorage(AppState* state);
  ~PhotoStorage();

  // Writes the data to the specified file, updating the md5 and access time
  // for the file. The parent_size indicates the size (thumbnail, medium, full,
  // etc) of the image which generated the new image. A parent_size of 0
  // indicates the image was generated from an ALAsset.
  bool Write(const string& filename, int parent_size,
             const Slice& data, const DBHandle& updates);
  // Adds an existing file (specified by path) to the photo storage with the
  // name "filename", updating the md5 and access time for the file.
  bool AddExisting(const string& path, const string& filename,
                   const string& md5, const string& server_id,
                   const DBHandle& updates);
  // Sets the server id associated with filename, renaming the file on disk and
  // storing a level of indirection in the database so that we can still access
  // the image via "filename".
  void SetServerId(const string& filename, const string& server_id,
                   const DBHandle& updates);
  // Add a symlink for server_id to asset_key in the photo server directory.
  void SetAssetSymlink(const string& filename, const string& server_id,
                       const string& asset_key);
  // Read the asset symlink for server_id.
  string ReadAssetSymlink(const string& filename, const string& server_id);
  // Returns true if we have uploaded the asset for the specified server id.
  bool HaveAssetSymlink(const string& filename, const string& server_id,
                        const string& asset_key);
  // Deletes the specified file and the md5 and access time information.
  void Delete(const string& filename, const DBHandle& updates);
  // Delete all of the files associated with the photo id.
  void DeleteAll(int64_t photo_id, const DBHandle& updates);
  // Reads the data from the specified file, updating the access time for the
  // file.
  string Read(const string& filename, const string& metadata);
  // Updates the access time for the specified file.
  void Touch(const string& filename, const string& metadata);
  // Returns true if the file exists or if the server file exists. If only the
  // server file exists, the local file is linked to the server file and the
  // metadata is populated.
  bool MaybeLinkServerId(const string& filename, const string& server_id,
                         const string& md5, const DBHandle& updates);
  // Returns true if the file exists, false otherwise.
  bool Exists(const string& filename);
  // Returns the size of the specified file.
  int64_t Size(const string& filename);
  // Returns the metadata for the specified file.
  PhotoPathMetadata Metadata(const string& filename);

  // Returns the smallest resolution image that is greater than or equal to
  // max_size. The raw (unparsed) metadata for the filename is returned in the
  // metadata parameter, suitable for passing to Read().
  string LowerBound(int64_t photo_id, int max_size, string* metadata);

  string PhotoPath(const Slice& filename);

  // Garbage collect files that do not have a corresponding entry in the
  // database.
  void GarbageCollect();

  // Check the photo storage metadata for consistency. Returns true if the
  // internal consistency is ok and false otherwise.
  bool Check();

  void set_local_bytes_limit(int64_t v);
  int64_t local_bytes_limit() const { return local_bytes_limit_; }
  int64_t local_bytes() const { return local_bytes_; }
  int local_thumbnail_files() const { return local_files_[0]; }
  int local_medium_files() const { return local_files_[1]; }
  int local_full_files() const { return local_files_[2]; }
  int local_original_files() const { return local_files_[3]; }
  const vector<Setting>& settings() const;
  int setting_index(int64_t value) const;
  CallbackSet* changed() { return &changed_; }
  // Merge current usage with the passed in one (not all categories may be filled).
  void update_remote_usage(const UsageMetadata& usage);
  UsageMetadata remote_usage() const;

 private:
  string PhotoServerPath(const Slice& filename, const string& server_id);
  void IncrementLocalUsage(const string& filename,
                           int64_t deleta, const DBHandle& updates);
  void FixLocalUsage();
  void AddScanner(Scanner* scanner);
  void RemoveScanner(Scanner* scanner);
  void AddUncommittedFile(const string& filename);
  void RemoveUncommittedFile(const string& filename);
  bool IsUncommittedFile(const string& filename);
  void CommonInit();

 private:
  AppState* const state_;
  ScopedPtr<AsyncState> async_;
  const string photo_dir_;
  const string server_photo_dir_;
  mutable Mutex mu_;
  CallbackSet changed_;
  StringSet uncommitted_files_;
  int64_t local_bytes_limit_;
  int64_t local_bytes_;
  int local_files_[4];
  bool gc_;
  ScannerSet scanners_;
  UsageMetadata remote_usage_;
};

#endif  // VIEWFINDER_PHOTO_STORAGE_H
