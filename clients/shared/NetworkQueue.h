// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_NETWORK_QUEUE_H
#define VIEWFINDER_NETWORK_QUEUE_H

#import <map>
#import "ActivityTable.h"
#import "CommentTable.h"
#import "DB.h"
#import "EpisodeTable.h"
#import "Mutex.h"
#import "PhotoTable.h"
#import "Server.pb.h"
#import "ViewpointTable.h"

class AppState;
class PhotoUpdate;

// These priorities are persisted to disk, so be careful when changing them.
enum {
  // Prioritize operations performed explicitly by the user or required by the
  // UI. For example, prioritize the retrieval of thumbnail images that need to
  // be displayed on screen.
  PRIORITY_UI_THUMBNAIL = 10,
  PRIORITY_UI_FULL = 20,
  PRIORITY_UI_ACTIVITY = 50,
  PRIORITY_UI_UPLOAD_PHOTO = 70,
  PRIORITY_UI_ORIGINAL = 100,
  // Used by NetworkManager to clear all preceding priority levels.
  PRIORITY_UI_MAX = 101,
  // The priority band for viewpoint updates, such as updating the viewed
  // sequence number.
  PRIORITY_UPDATE_VIEWPOINT = 300,
  // The priority bands for uploading photos that are used by the client for
  // display.
  PRIORITY_UPLOAD_PHOTO = 400,
  PRIORITY_UPLOAD_PHOTO_MEDIUM = 500,
  // The priority band for downloading photos that are not visible on the
  // screen.
  PRIORITY_DOWNLOAD_PHOTO = 550,
  // The priority band for uploading original images.
  PRIORITY_UPLOAD_PHOTO_ORIGINAL = 600,
  PRIORITY_MAX = 1000,
};

// The NetworkQueue maintains a map from:
//   <priority>,<sequence> -> <ServerOperation>
//   <device-photo-id> -> <priority>,<sequence>
//
// Both priorities and sequence numbers are sorted such that lower values come
// before higher values. The sequence number is internally allocated and
// ensures FIFO for operations with the same priority.
class NetworkQueue {
  typedef CallbackSet1<int> DownloadCallbackSet;
  typedef std::unordered_map<
    int64_t, DownloadCallbackSet*> DownloadCallbackMap;

 public:
  class Iterator {
   public:
    Iterator(leveldb::Iterator* iter);
    ~Iterator();

    // Advance to the next queued operation.
    void Next();

    // Skip to the next priority band containing a queued operation.
    void SkipPriority();

    const ServerOperation& op() const { return op_; }
    bool done() const { return done_; }
    int priority() const { return priority_; }
    int64_t sequence() const { return sequence_; }

   private:
    bool UpdateState();

   private:
    ScopedPtr<leveldb::Iterator> iter_;
    bool done_;
    int priority_;
    int64_t sequence_;
    ServerOperation op_;
  };

  enum PhotoType {
    THUMBNAIL = PhotoMetadata::THUMBNAIL,
    MEDIUM = PhotoMetadata::MEDIUM,
    FULL = PhotoMetadata::FULL,
    ORIGINAL = PhotoMetadata::ORIGINAL,
  };

  struct Episode {
    EpisodeHandle parent;
    EpisodeHandle episode;
    vector<PhotoHandle> photos;
  };

  struct DownloadPhoto {
    EpisodeHandle episode;
    PhotoHandle photo;
    PhotoType type;
    string path;
    string url;
  };

  struct RemovePhotos {
    OpHeaders headers;
    QueueMetadata queue;
    vector<Episode> episodes;
  };

  struct UpdatePhoto {
    OpHeaders headers;
    PhotoHandle photo;
  };

  struct UpdateViewpoint {
    OpHeaders headers;
    ViewpointHandle viewpoint;
  };

  // UploadActivity handles a locally-created activity which still must be sent
  // to the server via share_new, share_existing, add_followers, post_comment
  // or unshare operations.
  struct UploadActivity {
    OpHeaders headers;
    ActivityHandle activity;
    ViewpointHandle viewpoint;
    // For shares.
    vector<Episode> episodes;
    // For shares & add_followers.
    vector<ContactMetadata> contacts;
    // For post comment.
    CommentHandle comment;
  };

  struct UploadEpisode {
    OpHeaders headers;
    EpisodeHandle episode;
    vector<PhotoHandle> photos;
  };

  struct UploadPhoto {
    EpisodeHandle episode;
    PhotoHandle photo;
    PhotoType type;
    string url;
    string path;
    string md5;
  };

 public:
  NetworkQueue(AppState* state);
  ~NetworkQueue();

  // Add an operation with the specified priority to the queue. Note that
  // nothing in the NetworkQueue prohibits the same operation from being
  // enqueued multiple times at the same or different priorities. Returns the
  // sequence number of the newly added entry.
  int64_t Add(int priority, const ServerOperation& op, const DBHandle& updates);

  // Remove the operation with the specified priority and sequence number from
  // the queue. This should only be called once the operation has completed and
  // before retrieving the next operation from the queue.
  void Remove(int priority, int64_t sequence, const DBHandle& updates);
  void Remove(int priority, int64_t sequence,
              const ServerOperation& op, const DBHandle& updates);

  // Queue the specified photo, possibly moving it from its current position in
  // the queue to a new position. Returns true iff the photo was modified.
  bool QueuePhoto(const PhotoHandle& ph, const DBHandle& updates);

  // Dequeue the specified photo. Returns true iff the photo was modified.
  bool DequeuePhoto(const PhotoHandle& ph, const DBHandle& updates);

  // Queue the specified activity. Returns true iff the activity was modified.
  bool QueueActivity(const ActivityHandle& ah, const DBHandle& updates);

  // Dequeue the specified activity. Returns true iff the activity was
  // modified.
  bool DequeueActivity(const ActivityHandle& ah, const DBHandle& updates);

  // Queue the specified viewpoint. Returns true iff the viewpoint was modified.
  bool QueueViewpoint(const ViewpointHandle& vh, const DBHandle& updates);

  // Dequeue the specified viewpoint. Returns true iff the viewpoint was
  // modified.
  bool DequeueViewpoint(const ViewpointHandle& vh, const DBHandle& updates);

  // Returns a new Iterator object for iterating over the queued
  // operations. The caller is responsible for deleting the iterator.
  Iterator* NewIterator();

  // Returns true iff nothing is queued.
  bool Empty();
  // Returns the priority of the item on the top of the queue, or -1 if nothing
  // is queued.
  int TopPriority();

  /// Returns the (adjusted) number of pending network operations.
  int GetNetworkCount();
  int GetDownloadCount();
  int GetUploadCount();

  // Returns true iff we should process the given priority band given the
  // network (wifi vs 3g/lte) and other settings.
  bool ShouldProcessPriority(int priority) const;
  // Returns true iff the given priority band corresponds to a download.
  bool IsDownloadPriority(int priority) const;

  // Commit queued requests.
  void CommitQueuedDownloadPhoto(const string& md5, bool retry);
  void CommitQueuedRemovePhotos(bool error);
  void CommitQueuedUpdatePhoto(bool error);
  enum UpdateViewpointType {
    UPDATE_VIEWPOINT_METADATA,
    UPDATE_VIEWPOINT_FOLLOWER_METADATA,
    UPDATE_VIEWPOINT_REMOVE,
    UPDATE_VIEWPOINT_VIEWED_SEQ,
  };
  void CommitQueuedUpdateViewpoint(UpdateViewpointType type, bool error);
  void CommitQueuedUploadEpisode(const UploadEpisodeResponse& r, int status);
  void CommitQueuedUploadPhoto(bool error);
  void CommitQueuedUploadActivity(bool error);

  // Process server responses.
  void ProcessQueryEpisodes(
      const QueryEpisodesResponse& r, const vector<EpisodeSelection>& v,
      const DBHandle& updates);
  void ProcessQueryFollowed(
      const QueryFollowedResponse& r, const DBHandle& updates);
  void ProcessQueryNotifications(
      const QueryNotificationsResponse& r, const DBHandle& updates);
  void ProcessQueryViewpoints(
      const QueryViewpointsResponse& r, const vector<ViewpointSelection>& v,
      const DBHandle& updates);

  // Wait for the specified photo to be downloaded, invoking "done" when the
  // photo has been downloaded or an error has occurred. It is the callers
  // responsibility to ensure that the specified photo has been queued for
  // download.
  void WaitForDownload(
      int64_t photo_id, PhotoType desired_type, Callback<void ()> done);

  // Returns a map containing counts of enqueued operations by priority.
  // Should be converted to an integer (with ceil()) before display.
  // Fractional values are used to compensate for the fact that one user action
  // may result in multiple queued operations (e.g. uploading metadata,
  // thumbnail, medium, full sizes are 0.25 each so the counter goes up by one
  // for each photo taken).
  typedef std::map<int, double> NetworkStatsMap;
  NetworkStatsMap stats();

  const DownloadPhoto* queued_download_photo() const {
    return queued_download_photo_.get();
  }
  const RemovePhotos* queued_remove_photos() const {
    return queued_remove_photos_.get();
  }
  const UpdatePhoto* queued_update_photo() const {
    return queued_update_photo_.get();
  }
  const UpdateViewpoint* queued_update_viewpoint() const {
    return queued_update_viewpoint_.get();
  }
  const UploadEpisode* queued_upload_episode() const {
    return queued_upload_episode_.get();
  }
  const UploadPhoto* queued_upload_photo() const {
    return queued_upload_photo_.get();
  }
  const UploadActivity* queued_upload_activity() const {
    return queued_upload_activity_.get();
  }

 private:
  void UpdateStatsLocked(int priority, const ServerOperation& op, bool addition);

  void EnsureInitLocked();
  void EnsureStatsInitLocked();

  ActivityHandle ProcessActivity(const ActivityMetadata& m, const DBHandle& updates);
  CommentHandle ProcessComment(const CommentMetadata& m, const DBHandle& updates);
  EpisodeHandle ProcessEpisode(const EpisodeMetadata& m,
                               bool recurse, const DBHandle& updates);
  PhotoHandle ProcessPhoto(const PhotoUpdate& u, EpisodeHandle* old_eh,
                           const DBHandle& updates);
  PhotoHandle ProcessPhoto(PhotoHandle h, const PhotoUpdate& u,
                           EpisodeHandle* old_eh, const DBHandle& updates);
  ViewpointHandle ProcessViewpoint(const ViewpointMetadata& m,
                                   bool recurse, const DBHandle& updates);

  void MaybeQueueNetwork(int priority);
  bool MaybeQueueUploadActivity(const ServerOperation& op, int priority,
                                const DBHandle& updates);
  bool MaybeQueueUpdatePhoto(const ServerOperation& op, int priority,
                             const DBHandle& updates);
  bool MaybeQueueRemovePhotos(const ServerOperation& op, int priority,
                              int64_t sequence, const DBHandle& updates);
  bool MaybeQueueDownloadPhoto(const PhotoHandle& ph, const DBHandle& updates);
  bool MaybeQueueUpdateViewpoint(const ServerOperation& op, const DBHandle& updates);
  bool MaybeQueueUploadPhoto(const PhotoHandle& ph, int priority,
                             const DBHandle& updates);
  bool MaybeQueueUpdatePhotoMetadata(const PhotoHandle& ph, const DBHandle& updates);
  bool MaybeQueueUploadEpisode(const EpisodeHandle& eh, const DBHandle& updates);
  void MaybeReverseGeocode(UploadEpisode* u, int index);
  void MaybeLoadImages(UploadEpisode* u, int index);

  void QuarantinePhoto(PhotoHandle p, const string& reason);
  void QuarantinePhoto(PhotoHandle p, const string& reason,
                       const DBHandle& updates);

  void UpdateViewpointError(ViewpointHandle vh);
  void UpdatePhotoError(PhotoHandle p);
  void UploadPhotoError(PhotoHandle p, int types);
  void DownloadPhotoError(PhotoHandle p, int types);
  void UploadActivityError(ActivityHandle ah);

  void NotifyDownload(int64_t photo_id, int types);

 private:
  AppState* state_;
  int64_t next_sequence_;
  mutable Mutex mu_;
  ScopedPtr<NetworkStatsMap> stats_;
  Mutex queue_mu_;
  bool queue_in_progress_;
  WallTime queue_start_time_;
  ScopedPtr<DownloadPhoto> queued_download_photo_;
  ScopedPtr<RemovePhotos> queued_remove_photos_;
  ScopedPtr<UpdatePhoto> queued_update_photo_;
  ScopedPtr<UpdateViewpoint> queued_update_viewpoint_;
  ScopedPtr<UploadEpisode> queued_upload_episode_;
  ScopedPtr<UploadPhoto> queued_upload_photo_;
  ScopedPtr<UploadActivity> queued_upload_activity_;
  const string photo_tmp_dir_;
  Mutex download_callback_mu_;
  DownloadCallbackMap download_callback_map_;
};

string EncodeNetworkQueueKey(int priority, int64_t sequence);
bool DecodeNetworkQueueKey(Slice key, int* priority, int64_t* sequence);

#endif  // VIEWFINDER_NETWORK_QUEUE_H

// local variables:
// mode: c++
// end:
