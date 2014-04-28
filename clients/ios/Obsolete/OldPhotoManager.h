// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_PHOTO_MANAGER_H
#define VIEWFINDER_PHOTO_MANAGER_H

#import <set>
#import <tr1/unordered_map>
#import <tr1/unordered_set>
#import <vector>
#import <stdint.h>
#import "AssetsManager.h"
#import "AsyncState.h"
#import "DB.h"
#import "Callback.h"
#import "Image.h"
#import "PhotoMetadata.pb.h"
#import "ValueUtils.h"
#import "WallTime.h"

class AppState;
class Breadcrumb;
class EpisodeUpdate;
class GetMetadataResponse;
class MetadataUploadResponse;
class PhotoStorage;
class PhotoUpdate;
class PlacemarkHistogram;
class QueryUpdatesResponse;
class ShareResponse;

@class CIDetector;

typedef std::tr1::unordered_set<string> ServerIdSet;

bool HasAssetKey(const PhotoId& id);
string GetAssetKey(const PhotoId& id);
bool DecodeServerId(const string& server_id,
                    uint64_t* device_id,
                    uint64_t* device_local_id);

class PhotoManager {
 public:
  struct EpisodeData;

  struct PhotoData {
    PhotoData()
        : priority(-1),
          timestamp(0),
          location(NULL),
          placemark(NULL),
          episode(NULL) {
    }
    int priority;
    WallTime timestamp;
    PhotoMetadata metadata;
    const Location* location;
    const Placemark* placemark;
    EpisodeData* episode;
  };

  typedef std::vector<PhotoData*> PhotoVec;

  struct EpisodeData {
    EpisodeData()
        : location(NULL),
          placemark(NULL) {
    }
    EpisodeMetadata metadata;
    const Location* location;
    const Placemark* placemark;
    PhotoVec photos;
  };

  enum PhotoType {
    THUMBNAIL = PhotoMetadata::THUMBNAIL,
    MEDIUM = PhotoMetadata::MEDIUM,
    FULL = PhotoMetadata::FULL,
    ORIGINAL = PhotoMetadata::ORIGINAL,
  };

  struct PhotoUpload {
    PhotoUpload(PhotoData* p = NULL)
        : photo(p) {
    }
    PhotoData* photo;
    PhotoType type;
    string url;
    string path;
    string md5;
  };

  struct PhotoDownload {
    PhotoId id;
    PhotoType type;
    string path;
    string url;
  };

  struct MetadataUpload {
    std::vector<PhotoData*> photos;
  };

  struct ShareUpload {
    PhotoVec photos;
    vector<ContactMetadata> contacts;
  };

  struct UnshareUpload {
    PhotoVec photos;
  };

  struct DeleteUpload {
    PhotoVec photos;
  };

 private:
  struct PhotoByTimestamp {
    bool operator()(const PhotoData* a, const PhotoData* b) const {
      if (a->metadata.timestamp() != b->metadata.timestamp()) {
        return a->metadata.timestamp() > b->metadata.timestamp();
      }
      // Distinguish identical timestamps using the local id. This makes
      // ordering predictable for tests.
      return a->metadata.id().local_id() < b->metadata.id().local_id();
    }
  };

  struct PhotoQueueCompare {
    bool operator()(const PhotoData* a, const PhotoData* b) const {
      if (a->priority != b->priority) {
        return a->priority > b->priority;
      }
      // Within a priority, sort on timestamp.
      if (a->timestamp != b->timestamp) {
        return a->timestamp > b->timestamp;
      }
      // Distinguish identical timestamps using the local id. This makes
      // ordering predictable for tests.
      return a->metadata.id().local_id() < b->metadata.id().local_id();
    }
  };

  struct LocationHash {
    size_t operator()(const Location& l) const {
      return static_cast<size_t>(
          1e6 * (l.latitude() + l.longitude()) + l.accuracy());
    }
  };

  struct LocationEq {
    bool operator()(const Location& a, const Location& b) const {
      return a.latitude() == b.latitude() &&
          a.longitude() == b.longitude() &&
          a.accuracy() == b.accuracy();
    }
  };

  struct PlacemarkHash {
    std::tr1::hash<string> h;
    size_t operator()(const Placemark& p) const {
      return h(p.iso_country_code()) +
          h(p.country()) +
          h(p.state()) +
          h(p.postal_code()) +
          h(p.locality()) +
          h(p.sublocality()) +
          h(p.thoroughfare()) +
          h(p.subthoroughfare());
    }
  };

  struct PlacemarkEq {
    bool operator()(const Placemark& a, const Placemark& b) const {
      return a.iso_country_code() == b.iso_country_code() &&
          a.country() == b.country() &&
          a.state() == b.state() &&
          a.postal_code() == b.postal_code() &&
          a.locality() == b.locality() &&
          a.sublocality() == b.sublocality() &&
          a.thoroughfare() == b.thoroughfare() &&
          a.subthoroughfare() == b.subthoroughfare();
    }
  };

 public:
  typedef std::tr1::unordered_map<int64_t, PhotoData> PhotoMap;
  typedef std::tr1::unordered_map<string, PhotoData*> ServerPhotoMap;
  typedef std::tr1::unordered_set<PhotoData*> PhotoSet;
  typedef std::tr1::unordered_map<int64_t, string> PhotoURLMap;
  typedef std::set<PhotoData*, PhotoQueueCompare> PhotoQueue;
  typedef std::tr1::unordered_map<PhotoData*, Image> PhotoDetectQueue;
  typedef std::tr1::unordered_set<EpisodeData*> EpisodeSet;
  typedef std::tr1::unordered_map<int64_t, EpisodeData> EpisodeMap;
  typedef std::tr1::unordered_map<string, EpisodeData*> ServerEpisodeMap;
  typedef std::tr1::unordered_map<
    Location, const Placemark*, LocationHash, LocationEq> LocationMap;
  typedef std::tr1::unordered_set<
    Placemark, PlacemarkHash, PlacemarkEq> PlacemarkSet;
  typedef CallbackSet1<bool> GeocodeCallbackSet;
  typedef std::tr1::unordered_map<
    const Location*, GeocodeCallbackSet*> GeocodeCallbackMap;
  typedef CallbackSet1<int> DownloadCallbackSet;
  typedef std::tr1::unordered_map<
    int64_t, DownloadCallbackSet*> DownloadCallbackMap;

 public:
  class Env {
   public:
    virtual ~Env() { }

    virtual void AssetForKey(const string& key,
                             ALAssetsLibraryAssetForURLResultBlock result,
                             ALAssetsLibraryAccessFailureBlock failure) = 0;
    virtual void TryDeleteAsset(const string& key) = 0;
    virtual void NetworkDispatch() = 0;
    virtual bool ReverseGeocode(
        const Location* l, void (^completion)(const Placemark*)) = 0;

    virtual CallbackSet* assets_scan_end() = 0;
    virtual AssetScanProgress* assets_scan_progress() = 0;
    virtual CallbackSet* auth_changed() = 0;
    virtual CallbackSet* network_changed() = 0;
    virtual CallbackSet* network_ready() = 0;
    virtual CallbackSet* settings_changed() = 0;

    virtual bool assets_scanning() = 0;
    virtual bool assets_full_scan() = 0;
    virtual bool cloud_storage() = 0;
    virtual const Breadcrumb* last_breadcrumb() = 0;
    virtual bool logged_in() = 0;
    virtual bool network_up() = 0;
    virtual bool network_wifi() = 0;
    virtual const string& photo_dir() = 0;
    virtual bool store_originals() = 0;
    virtual int64_t user_id() = 0;

    virtual DB* db() = 0;
    virtual PhotoStorage* photo_storage() = 0;
    virtual PlacemarkHistogram* placemark_histogram() = 0;
  };

 public:
  PhotoManager(AppState* state);
  PhotoManager(Env* env);
  ~PhotoManager();

  void EnsureInit();
  void MemoryStats();

  int64_t NewViewfinderPhoto(const PhotoMetadata& m, NSData* data);
  int64_t NewAssetPhoto(ALAsset* asset, const string& asset_key,
                        bool complete_on_main_thread);

  void SetDeviceId(int64_t device_id);

  // Process query updates, adding any photos and episodes that we don't have
  // to the retrieval queue.
  void ProcessQueryUpdates(const QueryUpdatesResponse& r);

  // Process the retrieval of photo and episode metadata.
  void ProcessGetMetadata(const GetMetadataResponse& r);

  // Commit the current metadata upload.
  void CommitQueuedMetadataUpload(const MetadataUploadResponse& r);
  // Commit the current photo upload.
  void CommitQueuedPhotoUpload(bool error);
  // Commit the current photo download.
  void CommitQueuedPhotoDownload(int64_t photo_id, const string& md5, bool retry);
  // Commit the current share upload.
  void CommitQueuedShareUpload();
  // Commit the current unshare upload.
  void CommitQueuedUnshareUpload();
  // Commit the current delete upload.
  void CommitQueuedDeleteUpload();

  // Add the specified contacts to the share list for the specified photos.
  void SharePhotos(const vector<int64_t>& photo_ids,
                   const vector<ContactMetadata>& contacts);

  // Unshare the specified photos.
  void UnsharePhotos(const vector<int64_t>& photo_ids);

  // Delete the specified photos.
  void DeletePhotos(const vector<int64_t>& photo_ids);
  void DeletePhoto(int64_t photo_id, DB::Batch* updates);

  // Asynchronously load a thumbnail/photo. These methods return their result
  // on the done() block, but must be called from the main thread.
  void LoadLocalThumbnail(int64_t photo_id, Image* image, void (^done)());
  void LoadLocalPhoto(int64_t photo_id, CGSize size,
                      Image* image, void (^done)());
  void LoadNetworkThumbnail(int64_t photo_id, Image* image, void (^done)());
  void LoadNetworkPhoto(int64_t photo_id, CGSize size,
                        Image* image, void (^done)());

  bool NeedsReverseGeocode(int64_t photo_id);
  bool ReverseGeocode(int64_t photo_id, void (^completion)(bool success));
  bool FormatLocation(int64_t photo_id, bool short_location, string* s);
  bool DistanceToLocation(int64_t photo_id, double* distance);
  const Placemark* GetPlacemark(int64_t photo_id);
  WallTime GetTimestamp(int64_t photo_id);

  int64_t device_id() const { return device_id_; }
  CallbackSet* geocode() { return &geocode_; }
  CallbackSet* queue() { return &queue_; }
  CallbackSet* update() { return &update_; }
  const PhotoMap& photos() const { return photo_map_; }
  const EpisodeMap& episodes() const { return episode_map_; }
  int num_photos() const { return photo_map_.size(); }
  int num_queued_photos() const { return queued_photos_.size(); }
  int num_queued_uploads() const { return queued_uploads_.size(); }
  int num_queued_downloads() const { return queued_downloads_.size(); }
  int num_queued_shares() const { return queued_shares_.size(); }
  int num_episodes() const { return episode_map_.size(); }

  const MetadataUpload* queued_metadata_upload() const {
    return queued_metadata_upload_.get();
  }
  const PhotoUpload* queued_photo_upload() const {
    return queued_photo_upload_.get();
  }
  const PhotoDownload* queued_photo_download() {
    return queued_photo_download_.get();
  }
  const ShareUpload* queued_share_upload() const {
    return queued_share_upload_.get();
  }
  const UnshareUpload* queued_unshare_upload() const {
    return queued_unshare_upload_.get();
  }
  const DeleteUpload* queued_delete_upload() const {
    return queued_delete_upload_.get();
  }
  const string& query_updates_key() const {
    return query_updates_key_;
  }
  const ServerIdSet& update_photo_ids() const {
    return update_photo_ids_;
  }
  const ServerIdSet& update_episode_ids() const {
    return update_episode_ids_;
  }

 private:
  void CommonInit();
  void GarbageCollectAssets();
  PhotoData* NewPhoto(const PhotoMetadata& p, bool owned, DB::Batch* updates);
  EpisodeData* NewEpisode(DB::Batch* updates);
  void CommitDeletePhoto(PhotoData* p, DB::Batch* updates);
  void DeleteEmptyEpisode(EpisodeData* e, DB::Batch* updates);
  bool LoadEpisode(EpisodeData* e, const EpisodeId& id);
  void AddPhoto(PhotoData* p, DB::Batch* updates);
  void AddPhoto(const Slice& key, const Slice& value, bool reset_errors);
  void AddPhotoToEpisode(PhotoData* p, DB::Batch* updates);
  void AddPhotoToExistingEpisode(PhotoData* p, EpisodeData* e, DB::Batch* updates);
  void RemovePhotoFromEpisode(PhotoData* p, DB::Batch* updates);
  EpisodeData* MatchPhotoToEpisode(PhotoData* p);
  bool ShouldAddPhotoToEpisode(PhotoData* p) const;
  bool ShouldDelete(PhotoData* p) const;
  void InternPhotoLocation(PhotoData* p);
  void InternEpisodeLocation(EpisodeData* e);
  void QuarantinePhoto(PhotoData* p);
  void LoadViewfinderPhotoError(PhotoData* p, const string& filename,
                                void (^done)(bool error));
  void LoadAssetPhotoError(PhotoData* p, int types,
                           void (^done)(bool error));
  void UploadPhotoError(PhotoData* p, int types);
  void DownloadPhotoError(PhotoData* p, int types);
  void WaitForDownload(int64_t photo_id, PhotoType type, void (^done)());
  void NotifyDownload(int64_t photo_id, int types);
  void MergePhotoUpdate(const PhotoUpdate& u, bool queue_update,
                        DB::Batch* updates);
  void MergePhotoUpdate(PhotoData* p, const PhotoUpdate& u,
                        DB::Batch* updates, bool dirty);
  bool MergePhotoMetadata(PhotoData* p, const PhotoMetadata& m,
                          DB::Batch* updates);
  void MergeEpisodeUpdate(const EpisodeUpdate& u, bool queue_update,
                        DB::Batch* updates);
  bool MergeEpisodeMetadata(EpisodeData* e, const EpisodeMetadata& m);
  void OutputPhotoMetadata(PhotoData* p, DB::Batch* updates);
  void OutputEpisodeMetadata(EpisodeData* e, DB::Batch* updates);
  void ReprioritizePhotoQueue();
  void UnqueuePhoto(PhotoData* p);
  void MaybeQueuePhoto(PhotoData* p);
  void MaybeQueueNetwork();
  void MaybeQueueMetadataUpload(EpisodeData* e);
  void MaybeLoadImages(MetadataUpload* u, int index);
  bool MaybeLoadImageData(PhotoData* p, int size,
                          void (^completion)(const string& path,
                                             const string& md5));
  void MaybeReverseGeocode(MetadataUpload* u, int index);
  void MaybeQueuePhotoUpload(PhotoData* p);
  void MaybeQueuePhotoDownload(PhotoData* p);
  void MaybeQueueShareUpload();
  void MaybeQueueUnshareUpload();
  void MaybeQueueDeleteUpload();
  bool MaybeLoadInternal(PhotoData* p, CGSize size, bool store_jpeg,
                         NSData* __strong* jpeg_data, Image* image,
                         void (^done)());
  bool MaybeLoadViewfinder(PhotoData* p, CGSize size, bool store_jpeg,
                           NSData* __strong* jpeg_data, Image* image,
                           void (^done)(bool error));
  bool MaybeLoadAsset(PhotoData* p, CGSize size, bool store_jpeg,
                      NSData* __strong* jpeg_data, Image* image,
                      void (^done)(bool error));
  void MaybeWriteThumbnail(PhotoData* p, NSData* jpeg_data);
  void MaybeQueueDetect(PhotoData* p, const Image& image);
  void MaybeDetect();
  void DetectFeatures(PhotoData* p, Image* image);

 private:
  ScopedPtr<Env> env_;
  ScopedPtr<AsyncState> async_;
  string photo_dir_;
  string photo_tmp_dir_;
  bool initialized_;
  int64_t device_id_;
  int64_t next_photo_id_;
  int64_t next_episode_id_;
  string query_updates_key_;
  PhotoMap photo_map_;
  ServerPhotoMap server_photo_map_;
  PhotoQueue queued_photos_;
  PhotoSet queued_uploads_;
  PhotoSet queued_downloads_;
  PhotoSet queued_shares_;
  PhotoDetectQueue queued_detects_;
  EpisodeMap episode_map_;
  ServerEpisodeMap server_episode_map_;
  LocationMap locations_;
  PlacemarkSet placemarks_;
  GeocodeCallbackMap geocode_callback_map_;
  DownloadCallbackMap download_callback_map_;
  PhotoURLMap thumbnail_get_urls_;
  PhotoURLMap thumbnail_put_urls_;
  PhotoURLMap medium_get_urls_;
  PhotoURLMap medium_put_urls_;
  PhotoURLMap full_get_urls_;
  PhotoURLMap full_put_urls_;
  PhotoURLMap original_get_urls_;
  PhotoURLMap original_put_urls_;
  CallbackSet geocode_;
  CallbackSet queue_;
  CallbackSet update_;
  WallTime last_load_time_;
  ScopedPtr<MetadataUpload> queued_metadata_upload_;
  ScopedPtr<PhotoUpload> queued_photo_upload_;
  ScopedPtr<PhotoDownload> queued_photo_download_;
  ScopedPtr<ShareUpload> queued_share_upload_;
  ScopedPtr<UnshareUpload> queued_unshare_upload_;
  ScopedPtr<DeleteUpload> queued_delete_upload_;
  bool queue_in_progress_;
  WallTime queue_start_time_;
  PhotoData* detect_in_progress_;
  ServerIdSet update_photo_ids_;
  ServerIdSet update_episode_ids_;
  CIDetector* face_detector_;
};

#endif  // VIEWFINDER_PHOTO_MANAGER_H
