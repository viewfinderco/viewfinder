// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_EPISODE_TABLE_H
#define VIEWFINDER_EPISODE_TABLE_H

#import "ContentTable.h"
#import "DB.h"
#import "EpisodeMetadata.pb.h"
#import "EpisodeStats.pb.h"
#import "InvalidateMetadata.pb.h"
#import "PhotoSelection.h"
#import "PhotoTable.h"

class FullTextIndex;

// The EpisodeTable class maintains the mappings:
//   <device-episode-id> -> <EpisodeMetadata>
//   <server-episode-id> -> <EpisodeSelection>
//   <server-episode-id> -> <device-episode-id>
//   <device-parent-episode-id>,<device-episode-id> -> <>  (list children by parent id)
//   <device-episode-id>,<device-photo-id> -> <kPosted|kRemoved|kHidden|kUnshared>  (post table)
//   <device-photo-id>,<device-episode-id> -> <>  (photo ref-count table)
//   <timestamp>,<device-episode-id> -> <>        (episode by date table)
//
// EpisodeTable is thread-safe and EpisodeHandle is thread-safe, but individual
// Episodes are not.

class EpisodeTable_Episode : public EpisodeMetadata {
  friend class EpisodeTable;

  enum PhotoState {
    HIDE_PENDING = 0,
    POST_PENDING,
    QUARANTINE_PENDING,
    REMOVE_PENDING,
    UNSHARE_PENDING,
    HIDDEN,
    POSTED,
    QUARANTINED,
    REMOVED,
    UNSHARED,
  };
  typedef std::map<int64_t, PhotoState> PhotoStateMap;

 public:
  virtual void MergeFrom(const EpisodeMetadata& m);
  // Unimplemented; exists to get the compiler not to complain about hiding the base class's overloaded MergeFrom.
  virtual void MergeFrom(const ::google::protobuf::Message&);

  // Return the device/user id for the episode. Returns
  // AppState::{device,user}_id if no the episode does not have a device/user
  // id set.
  int64_t GetDeviceId() const;
  int64_t GetUserId() const;

  // Adds a photo to the episode. The added photo is not persisted until
  // Save() is called.
  void AddPhoto(int64_t photo_id);

  // Hides a photo from the epsiode. Hiding photos does not affect
  // accounting but removes the photo from the display.
  void HidePhoto(int64_t photo_id);

  // Indicates that a photo in the episode has been quarantined. This
  // does not remove the photo/episode ref count links, but will
  // prevent further attempts to display the photo. The quarantined
  // photo is not persisted until Save() is called.
  void QuarantinePhoto(int64_t photo_id);

  // Removes a photo from the episode. This only removes the
  // photo/episode ref count link for photos which are not shared. The
  // removed photo is not persisted until Save() is called. This should
  // only be done on photos which are part of the default viewpoint.
  void RemovePhoto(int64_t photo_id);

  // Unshares a photo from the episode. This removes the photo/episode
  // ref count link for shared photos (the call itself is only valid for
  // shared photos).
  void UnsharePhoto(int64_t photo_id);

  // Returns true if the photo is hidden from the episode.
  bool IsHidden(int64_t photo_id);

  // Returns true if the photo is posted to the episode.
  bool IsPosted(int64_t photo_id);

  // Returns true if the photo was quarantined from the episode.
  bool IsQuarantined(int64_t photo_id);

  // Returns true if the photo was removed from the episode.
  bool IsRemoved(int64_t photo_id);

  // Returns true if the photo was unshared from the episode.
  bool IsUnshared(int64_t photo_id);

  // Returns a count of the number of photos posted to the episode.
  int CountPhotos();

  // Lists only the POSTED photos associated with the episode.
  void ListPhotos(vector<int64_t>* photo_ids);

  // Lists all photos associated with the episode, regardless of
  // state.  This includes hidden, removed, unshared &
  // quarantined. Use the IsHidden, IsPosted, IsRemoved, IsQuarantined
  // & IsUnshared methods to check state of individual photos.
  void ListAllPhotos(vector<int64_t>* photo_ids);

  // Lists the photos which have been unshared.
  void ListUnshared(vector<int64_t>* unshared_ids);

  // Returns whether the episode is part of the user's photo library.
  // This is true if the episode is unshared or not part of any viewpoint,
  // or is part of the user's default viewpoint.
  bool InLibrary();

  // Returns time range from earliest to latest photo. If the episode
  // contains no photos, returns false.
  bool GetTimeRange(WallTime* earliest, WallTime* latest);

  // Returns true if any photo within this episode has a valid
  // location. If "location" and/or "placemark" are non-NULL, sets
  // their values if available. Since this method queries each photo
  // individually to find one with a location and placemark, the value
  // is cached after the first call and returned efficiently thereafter.
  bool GetLocation(Location* location, Placemark* placemark);

  // Set the server id if it is not already set. Returns true iff the server-id
  // was set.
  bool MaybeSetServerId();

  // Returns a formatted location.
  string FormatLocation(bool shorten);

  // Returns a formatted time range from earliest to latest photo timestamps.
  // Specifying "now" uses the specified date as the relative offset for
  // formatting. If not specified, the time range is formatted relative to
  // the latest timestamp of any photo in the episode.
  string FormatTimeRange(bool shorten, WallTime now = 0);

  // Returns a formatted contributor. If the episode is owned by the
  // user, returns empty string. Otherwise, returns full name if
  // "shorten" is false or first name if "shorten" is true.
  string FormatContributor(bool shorten);

  // Invalidates episode occurences in day metadata and all activities
  // which shared photos from this episode.
  void Invalidate(const DBHandle& updates);

  // Gets the pending count of photo additions, hiddens, quarantines,
  // removals and unshares.
  int additions() const { return additions_; }
  int hiddens() const { return hiddens_; }
  int quarantines() const { return quarantines_; }
  int removals() const { return removals_; }
  int unshares() const { return unshares_; }

 protected:
  bool Load();
  void SaveHook(const DBHandle& updates);
  void DeleteHook(const DBHandle& updates);

  int64_t local_id() const { return id().local_id(); }
  const string& server_id() const { return id().server_id(); }

  EpisodeTable_Episode(AppState* state, const DBHandle& db, int64_t id);

 private:
  void EnsurePhotoState();

 protected:
  AppState* state_;
  DBHandle db_;

 private:
  // The timestamp as stored on disk.
  WallTime disk_timestamp_;
  // A cache of the photos associated with the episode. Populated on-demand.
  ScopedPtr<PhotoStateMap> photos_;
  // Protects photos_.  Should be held when calling EnsurePhotoState.
  Mutex photos_mu_;
  int additions_;
  int hiddens_;
  int quarantines_;
  int removals_;
  int unshares_;
  bool have_photo_state_;
  bool recompute_timestamp_range_;
  // Cached values for GetLocation().
  bool resolved_location_;
  ScopedPtr<Location> location_;
  ScopedPtr<Placemark> placemark_;
};

class EpisodeTable : public ContentTable<EpisodeTable_Episode> {
  typedef EpisodeTable_Episode Episode;

 public:
  class EpisodeIterator : public ContentIterator {
    friend class EpisodeTable;

   public:
    ContentHandle GetEpisode();

    WallTime timestamp() const { return timestamp_; }
    int64_t episode_id() const { return episode_id_; }

    // Position the iterator at the specified time. done() is true
    // if there is no more content after seeking.
    void Seek(WallTime seek_time);

   private:
    EpisodeIterator(
        EpisodeTable* table, WallTime start, bool reverse, const DBHandle& db);

    bool IteratorDone(const Slice& key);
    bool UpdateStateHook(const Slice& key);

   private:
    EpisodeTable* const table_;
    DBHandle db_;
    WallTime timestamp_;
    int64_t episode_id_;
  };

  class EpisodePhotoIterator : public ContentIterator {
    friend class EpisodeTable;

   public:
    EpisodePhotoIterator(int64_t episode_id, const DBHandle& db);

    bool IteratorDone(const Slice& key);
    bool UpdateStateHook(const Slice& key);

    int64_t photo_id() const { return photo_id_; }

   private:
    const string episode_prefix_;
    int64_t photo_id_;
  };

 public:
  EpisodeTable(AppState* state);
  ~EpisodeTable();

  void Reset();

  ContentHandle NewEpisode(const DBHandle& updates) {
    return NewContent(updates);
  }
  ContentHandle LoadEpisode(int64_t id, const DBHandle& db) {
    return LoadContent(id, db);
  }
  ContentHandle LoadEpisode(const string& server_id, const DBHandle& db) {
    return LoadContent(server_id, db);
  }
  ContentHandle LoadEpisode(const EpisodeId& id, const DBHandle& db);

  // Find the episode to which the specified photo should be added. Might
  // return NULL if a new episode should be created.
  ContentHandle MatchPhotoToEpisode(const PhotoHandle& p, const DBHandle& db);

  // Add the photo to the best matching episode or create a new episode and add
  // the photo.
  void AddPhotoToEpisode(const PhotoHandle& p, const DBHandle& updates);

  // Returns a count of the number of episodes the specified photo is
  // associated with.
  int CountEpisodes(int64_t photo_id, const DBHandle& db);

  // Lists the episodes the specified photo is associated with.
  // Returns whether any episodes were found and sets the list of
  // matching episodes in *episode_ids. "episode_ids" maybe NULL.
  bool ListEpisodes(int64_t photo_id, vector<int64_t>* episode_ids, const DBHandle& db);

  // Lists the episodes the specified photo is associated with which
  // are part of the default viewpoint (e.g. visible in the personal
  // library). Returns whether any such episodes were located. Sets
  // *episode_ids with the list of episodes. "episode_ids" may be NULL.
  bool ListLibraryEpisodes(int64_t photo_id, vector<int64_t>* episode_ids, const DBHandle& db);

  // Removes photos from episodes and queues up a server operation. The
  // photo_ids vector consists of <photo-id, episode-id> pairs.
  void RemovePhotos(const PhotoSelectionVec& photo_ids,
                    const DBHandle& updates);

  // TODO(spencer): implement HidePhotos().
  // Hides photos from episodes and queues up a server operation.

  // Returns the most appropriate episode for the specified photo. We
  // prefer the original episode (as listed in p->episode_id()) if
  // available. Otherwise, try to locate a non-derived episode that the
  // user has access to.
  ContentHandle GetEpisodeForPhoto(const PhotoHandle& p, const DBHandle& db);

  // Validates portions of the specified episode.
  void Validate(const EpisodeSelection& s, const DBHandle& updates);

  // Invalidates portions of the specified episode.
  void Invalidate(const EpisodeSelection& s, const DBHandle& updates);

  // Lists the episode invalidations.
  void ListInvalidations(vector<EpisodeSelection>* v, int limit, const DBHandle& db);

  // Clear all of the episode invalidations.
  void ClearAllInvalidations(const DBHandle& updates);

  // Lists all episodes with matching parent id.
  void ListEpisodesByParentId(
      int64_t parent_id, vector<int64_t>* children, const DBHandle& db);

  // Returns a new EpisodeIterator object for iterating over the episodes in
  // ascending timestamp order. The caller is responsible for deleting the
  // iterator.
  EpisodeIterator* NewEpisodeIterator(WallTime start, bool reverse, const DBHandle& db);

  // Returns aggregated stats of photos contained across all episodes.
  EpisodeStats stats();

  // Repairs secondary indexes and sanity checks episode metadata.
  bool FSCKImpl(int prev_fsck_version, const DBHandle& updates);

  // Verifies and repairs references from episode metadata to other objects.
  bool FSCKEpisode(int prev_fsck_version, const DBHandle& updates);

  // Verifies and repairs episode timestamp secondary index.
  bool FSCKEpisodeTimestampIndex(const DBHandle& updates);

  // Returns local episode ids for episodes matching the query.
  typedef vector<int64_t> EpisodeSearchResults;
  void Search(const Slice& query, EpisodeSearchResults* results);

  FullTextIndex* episode_index() const { return episode_index_.get(); }
  FullTextIndex* location_index() const { return location_index_.get(); }

 public:
  static const string kHiddenValue;
  static const string kPostedValue;
  static const string kQuarantinedValue;
  static const string kRemovedValue;
  static const string kUnsharedValue;

 protected:
  virtual void SaveContentHook(Episode* episode, const DBHandle& updates);
  virtual void DeleteContentHook(Episode* episode, const DBHandle& updates);

 private:
  void EnsureStatsInit();

 private:
  mutable Mutex stats_mu_;
  bool stats_initialized_;
  EpisodeStats stats_;
  ScopedPtr<FullTextIndex> episode_index_;
  ScopedPtr<FullTextIndex> location_index_;
};

typedef EpisodeTable::ContentHandle EpisodeHandle;

string EncodeEpisodePhotoKey(int64_t episode_id, int64_t photo_id);
string EncodePhotoEpisodeKey(int64_t photo_id, int64_t episode_id);
string EncodeEpisodeTimestampKey(WallTime timestamp, int64_t episode_id);
string EncodeEpisodeParentChildKey(int64_t parent_id, int64_t child_id);
bool DecodeEpisodePhotoKey(Slice key, int64_t* episode_id, int64_t* photo_id);
bool DecodePhotoEpisodeKey(Slice key, int64_t* photo_id, int64_t* episode_id);
bool DecodeEpisodeTimestampKey(Slice key, WallTime* timestamp, int64_t* episode_id);
bool DecodeEpisodeParentChildKey(Slice key, int64_t* parent_id, int64_t* child_id);

#endif  // VIEWFINDER_EPISODE_TABLE_H

// local variables:
// mode: c++
// end:
