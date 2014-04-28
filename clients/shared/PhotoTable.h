// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_PHOTO_TABLE_H
#define VIEWFINDER_PHOTO_TABLE_H

#import "ContentTable.h"
#import "Mutex.h"
#import "PhotoMetadata.pb.h"
#import "STLUtils.h"
#import "WallTime.h"

// The PhotoTable class maintains the mappings:
//   <device-photo-id> -> <PhotoMetadata>
//   <server-photo-id> -> <device-photo-id>
//   <device-photo-id>,<name> -> <PhotoUrl>
//
// PhotoTable is thread-safe and PhotoHandle is thread-safe, but individual
// Photos are not.

class PhotoTable_Photo : public PhotoMetadata {
  friend class PhotoTable;

 public:
  virtual void MergeFrom(const PhotoMetadata& m);
  // Unimplemented; exists to get the compiler not to complain about hiding the base class's overloaded MergeFrom.
  virtual void MergeFrom(const ::google::protobuf::Message&);

  // Return the device/user id for the photo. Returns
  // AppState::{device,user}_id if no the photo does not have a device/user id
  // set.
  int64_t GetDeviceId() const;
  int64_t GetUserId() const;
  // Returns true if the photo has a valid location. If "location"
  // and/or "placemark" are non-NULL, sets their values if available.
  // The photo may have a valid location but not a valid placemark.
  // In this case, unless it is already busy, the PhotoTable will be
  // asked to reverse geocode the location to a placemark.
  bool GetLocation(Location* location, Placemark* placemark);
  // Returns a formatted location.
  string FormatLocation(bool shorten);
  // Get the url for the specified name. Returns an empty string if no
  // such url exists.
  string GetURL(const string& name);
  // Get the url for the specified name, returning it only if it has not
  // expired.
  string GetUnexpiredURL(const string& name, const DBHandle& updates);
  // Set the url for the specified name.
  void SetURL(const string& name, const string& url, const DBHandle& updates);
  // Delete the url for the specified name.
  void DeleteURL(const string& name, const DBHandle& updates);
  // Returns whether the specified exif timestamp is materially different
  // from the photo's timestamp. This is true if the timestamps are not
  // equal to the second by any number of integer hour offsets up to 24.
  // This accounts for possible timezone ambiguity caused by parsing exif
  // datetime string.
  bool ShouldUpdateTimestamp(WallTime exif_timestamp);
  // Mark the photo as quarantined.
  void Quarantine(const string& reason, const DBHandle& updates);
  // Returns true iff the photo should be added to an episode.
  bool ShouldAddPhotoToEpisode() const;
  // Find the set of candidate duplicate photos.
  void FindCandidateDuplicates();

  bool HasAssetUrl() const;

  bool AddAssetKey(const string& asset_key);
  bool AddAssetFingerprint(const Slice& asset_fingerprint, bool from_server);
  void AddPerceptualFingerprint(const string& term);
  void AddPerceptualFingerprint(const ImageFingerprint& fingerprint);
  bool RemoveAssetKey(const string& asset_key);
  bool RemoveAssetKeyByIndex(int index);

  // Returns true if the photo is available in the library.
  bool InLibrary();

  // Set the server id if it is not already set. Returns true iff the server-id
  // was set.
  bool MaybeSetServerId();

  const DBHandle& db() const { return db_; }

 protected:
  bool Load();
  void SaveHook(const DBHandle& updates);
  void DeleteHook(const DBHandle& updates);

  // Invalidates all activities which have shared this photo and all episodes
  // which contain it.
  void Invalidate(const DBHandle& updates);

  StringSet GetAssetKeySet() const;
  string GetDayTableFields() const;

  int64_t local_id() const { return id().local_id(); }
  const string& server_id() const { return id().server_id(); }

  PhotoTable_Photo(AppState* state, const DBHandle& db, int64_t id);

 protected:
  AppState* const state_;
  DBHandle db_;

 private:
  StringSet disk_asset_keys_;
  ImageFingerprint disk_perceptual_fingerprint_;
  string day_table_fields_;
};

class PhotoTable : public ContentTable<PhotoTable_Photo> {
  typedef PhotoTable_Photo Photo;

  typedef CallbackSet1<bool> GeocodeCallbackSet;
  typedef std::unordered_map<
    const Location*, GeocodeCallbackSet*> GeocodeCallbackMap;
  typedef Callback<void (bool success)> GeocodeCallback;

 public:
  static const string kPhotoDuplicateQueueKeyPrefix;

 public:
  PhotoTable(AppState* state);
  ~PhotoTable();

  void Reset();

  ContentHandle NewPhoto(const DBHandle& updates) {
    return NewContent(updates);
  }
  ContentHandle LoadPhoto(int64_t id, const DBHandle& db) {
    return LoadContent(id, db);
  }
  ContentHandle LoadPhoto(const string& server_id, const DBHandle& db) {
    return LoadContent(server_id, db);
  }
  ContentHandle LoadPhoto(const PhotoId& id, const DBHandle& db);

  // Loads the photo for the specified asset key.
  ContentHandle LoadAssetPhoto(const Slice& asset_key, const DBHandle& db);

  // Returns true if a photo exists with the corresponding url/fingerprint or
  // asset key.
  bool AssetPhotoExists(const Slice& url, const Slice& fingerprint,
                        const DBHandle& db);
  bool AssetPhotoExists(const Slice& asset_key, const DBHandle& db);

  // The specified assets were not found during a full asset scan. Remove
  // references to the asset-urls from PhotoMetadata.
  void AssetsNotFound(const StringSet& not_found, const DBHandle& updates);

  // Delete all of the images associated with the photo.
  void DeleteAllImages(int64_t photo_id, const DBHandle& updates);

  // Returns true if the photo is available in the library.
  bool PhotoInLibrary(int64_t photo_id, const DBHandle& db);

  // Returns true if the two asset photos are equal.  Intended to be called from
  // asset scans on two photos with the same asset url to identify when iTunes has
  // reassigned asset urls to different photos.  If the "server" photo predates
  // asset fingerprints this method uses heuristics that err on the side of
  // assuming asset urls are not reassigned.
  static bool IsAssetPhotoEqual(
      const PhotoMetadata& local, const PhotoMetadata& server);

  // Reverse geocode the location information for the specified photo, invoking
  // the completion callback when done. Returns true if the reverse geocode was
  // started or queued and false if reverse geocoding was not required or is
  // not available. If false is return, "completion" will not be invoked.
  bool ReverseGeocode(int64_t photo_id, GeocodeCallback completion);

  // Resets the error label on the photo handle and re-posts to all
  // episodes.
  void MaybeUnquarantinePhoto(const ContentHandle& ph, const DBHandle& updates);
  void MaybeUnquarantinePhoto(int64_t photo_id);

  // Possibly unquarantine photos. As various fixes are introduced
  // which aim to make previously-quarantined photos accessible, an
  // internal quarantine version number is incremented. If incremented
  // since the last run, this method unquarantines all photos by
  // resetting each error label and re-posting the photo to all
  // events.  Quarantined photos will be re-queued for upload /
  // download and if successful, will be re-instated; otherwise, will
  // be re-quarantined.
  //
  // Returns whether photos were unquarantined.
  bool MaybeUnquarantinePhotos(ProgressUpdateBlock progress_update);

 private:
  friend class PhotoTable_Photo;

  // Start a reverse geocode with the photo manager. Only one reverse
  // geocode is kept in-flight by the DayTable at a time. Whether or
  // not a day needs a reverse geocode is stored in the DayMetadata.
  void MaybeReverseGeocode(int64_t photo_id);

  void MaybeProcessDuplicateQueueLocked();

  // Looks up the photo id for the specified url/fingerprint or asset_key. If
  // require_url_match is true, only returns the photo id if both the url and
  // fingerprint portions of the asset key match.
  int64_t AssetToDeviceId(const Slice& url, const Slice& fingerprint,
                          bool require_url_match, const DBHandle& db);
  int64_t AssetToDeviceId(const Slice& asset_key, bool require_url_match,
                          const DBHandle& db);

  // Possibly unquarantines photos and sanity checks metadata.
  bool FSCKImpl(int prev_fsck_version, const DBHandle& updates);

 private:
  mutable Mutex mu_;
  int geocode_in_progress_;
  GeocodeCallbackMap geocode_callback_map_;
};

typedef PhotoTable::ContentHandle PhotoHandle;

string EncodeAssetFingerprintKey(const Slice& fingerprint);
string EncodePhotoDuplicateQueueKey(int64_t local_id);
string EncodePerceptualFingerprint(const Slice& term);
bool DecodeAssetFingerprintKey(Slice key, Slice* fingerprint);
bool DecodePhotoDuplicateQueueKey(Slice key, int64_t* local_id);
bool DecodePerceptualFingerprint(Slice fingerprint, string* term);
bool DecodeDeprecatedAssetReverseKey(Slice key, Slice* fingerprint, Slice* url);

inline bool IsPerceptualFingerprint(const Slice& fingerprint) {
  return DecodePerceptualFingerprint(fingerprint, NULL);
}

#endif  // VIEWFINDER_PHOTO_TABLE_H

// local variables:
// mode: c++
// end:
