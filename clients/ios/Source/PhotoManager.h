// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_PHOTO_MANAGER_H
#define VIEWFINDER_PHOTO_MANAGER_H

#import "ActivityTable.h"
#import "AssetsManager.h"
#import "Callback.h"
#import "CommentTable.h"
#import "DayTable.h"
#import "DB.h"
#import "EpisodeTable.h"
#import "Image.h"
#import "PhotoMetadata.pb.h"
#import "PhotoTable.h"
#import "PlacemarkHistogram.h"
#import "Server.pb.h"
#import "ViewpointTable.h"

class ExportAssetPhotoOp;
class NotificationManager;
class PhotoStorage;
class PhotoUpdate;
class PlacemarkTable;
class QueryEpisodesResponse;
class QueryFollowedResponse;
class QueryNotificationsResponse;
class QueryViewpointsResponse;
class UIAppState;

@class CIContext;
@class CLLocation;

class PhotoManager {
  friend class ExportAssetPhotoOp;

 public:
  PhotoManager(UIAppState* state);
  ~PhotoManager();

  // Create a new photo from an ALAsset.
  int64_t NewAssetPhoto(ALAsset* asset, const string& asset_key, CGImageRef square_thumbnail);

  // Create a new viewfinder photo.
  int64_t NewViewfinderPhoto(const PhotoMetadata& m, NSData* jpeg_data);

  // Copies the given photo into the assets library, downloading its full-size
  // version if necessary.  The photo must not already be in the assets library.
  void CopyToAssetsLibrary(int64_t photo_id, void (^completion)(string asset_url));

  // Asynchronously load a local/network thumbnail/photo. These methods return
  // their result on the done() block on the low-priority pool, but must be called
  // from the main thread.
  void LoadLocalThumbnail(int64_t photo_id, void (^done)(Image image));
  void LoadLocalPhoto(int64_t photo_id, CGSize size, void (^done)(Image image));
  void LoadNetworkThumbnail(int64_t photo_id, void (^done)(Image image));
  void LoadNetworkPhoto(int64_t photo_id, CGSize size, void (^done)(Image image));

  // Generates the viewfinder images for the specified photo, invoking
  // "completion" when done.
  void LoadViewfinderImages(int64_t photo_id, const DBHandle& db,
                            void (^completion)(bool success));

  // Asynchronously reverse geocodes the location for the specified photo id
  // generating placemark information. Invokes completion when the reverse
  // geocoding is done.
  bool ReverseGeocode(int64_t photo_id, void (^completion)(bool success));

 private:
  int64_t NewPhotoCommon(const PhotoHandle& p, const DBHandle& updates);

  void QuarantinePhoto(PhotoHandle p, const string& reason);
  void QuarantinePhoto(PhotoHandle p, const string& reason,
                       const DBHandle& updates);
  void LoadViewfinderPhotoError(
      PhotoHandle p, const string& filename, void (^done)(bool error, Image image));
  void LoadAssetPhotoError(
      PhotoHandle p, int types, void (^done)(bool error, Image image));

  bool LoadViewfinderImages(PhotoHandle p, void (^completion)(bool success));
  bool MaybeLoadImageData(PhotoHandle p, int size,
                          void (^completion)(const string& path, const string& md5));

  enum {
    STORE_JPEG = 1 << 0,
    WANT_IMAGE = 1 << 1,
    QUEUE_DOWNLOAD = 1 << 2,
    GENERATE_THUMBNAIL = 1 << 3,
  };

  bool MaybeLoadInternal(PhotoHandle p, CGSize size,
                         int load_flags, void (^done)(Image image));
  void MaybeMarkPhotoForDownload(PhotoHandle p, CGSize size, int load_flags);
  bool MaybeLoadViewfinder(PhotoHandle p, CGSize size,
                           int load_flags, void (^done)(bool error, Image image));
  bool MaybeLoadAsset(PhotoHandle p, CGSize size,
                      int load_flags, void (^done)(bool error, Image image));
  void MaybeRetryLoadAsset(PhotoHandle p, CGSize size, int load_flags,
                           void (^done)(bool error, Image image),
                           const string& asset_key);
  void MaybeWriteThumbnail(PhotoHandle p, const Image& image);
  void MaybeUpdateMetadata(const PhotoHandle& p, ALAssetRepresentation* rep);
  bool MaybeApplyAdjustmentXMP(const PhotoHandle& p, Image* image,
                               CGSize desired_size, const Slice& adjustment_xmp);

  CIContext* core_image_context();

 private:
  UIAppState* state_;
  const string photo_dir_;
  const string photo_tmp_dir_;
  Mutex assets_mu_;
  bool assets_initial_scan_;
  Mutex core_image_mu_;
  CIContext* core_image_context_;
};

#endif  // VIEWFINDER_PHOTO_MANAGER_H
