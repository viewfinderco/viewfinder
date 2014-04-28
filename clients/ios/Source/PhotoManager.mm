// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <CoreImage/CoreImage.h>
#import <ImageIO/ImageIO.h>
#import <MobileCoreServices/UTCoreTypes.h>
#import "AsyncState.h"
#import "ContactManager.h"
#import "Exif.h"
#import "ExportAssetPhotoOp.h"
#import "FileUtils.h"
#import "GeocodeManager.h"
#import "ImageFingerprint.h"
#import "ImageIndex.h"
#import "LocationTracker.h"
#import "NetworkManager.h"
#import "NetworkQueue.h"
#import "NotificationManager.h"
#import "PathUtils.h"
#import "PhotoManager.h"
#import "PhotoStorage.h"
#import "PhotoView.h"
#import "PlacemarkTable.h"
#import "ServerId.h"
#import "ServerUtils.h"
#import "SubscriptionManagerIOS.h"
#import "Timer.h"
#import "UIAppState.h"

namespace {

const float kJpegThumbnailQuality = 0.7;
const float kJpegOriginalQuality = 0.8;
const int kMaxOriginalJpegSizeForImage = 3 * 1024 * 1024;      // 3 MB
const float kMaxFullSizeScale = 2;
const int kMaxInflightAssetThumbnails = 1;

const NetworkQueue::PhotoType THUMBNAIL = NetworkQueue::THUMBNAIL;
const NetworkQueue::PhotoType MEDIUM = NetworkQueue::MEDIUM;
const NetworkQueue::PhotoType FULL = NetworkQueue::FULL;
const NetworkQueue::PhotoType ORIGINAL = NetworkQueue::ORIGINAL;

const string kOneTimeAssetThumbnailGenerationKey =
    DBFormat::metadata_key("one_time_asset_thumbnail_generation");

int MaxSizeToLoadSize(int max_size) {
  if (max_size <= kThumbnailSize) {
    return kThumbnailSize;
  } else if (max_size <= kMediumSize) {
    return kMediumSize;
  } else if (max_size <= kFullSize) {
    return kFullSize;
  }
  return max_size;
}

// Is the source jpeg dimension compatible with writing the destination jpeg
// dimension? We only allow generation of jpegs from the next size larger.
bool CanWriteJpeg(int dest_jpeg_dim, int src_jpeg_dim) {
  if (src_jpeg_dim <= dest_jpeg_dim) {
    return false;
  }
  if (dest_jpeg_dim == kThumbnailSize) {
    return kMediumSize == src_jpeg_dim;
  } else if (dest_jpeg_dim == kMediumSize) {
    return kFullSize == src_jpeg_dim;
  } else if (dest_jpeg_dim == kFullSize) {
    return kFullSize < src_jpeg_dim;
  }
  return false;
}

bool HasAssetError(const PhotoMetadata& p, float max_size) {
  if (max_size <= kThumbnailSize) {
    return p.error_asset_thumbnail();
  }
  // There is no medium asset size, just thumbnail, full and original.
  if (max_size <= kFullSize) {
    return p.error_asset_full();
  }
  return p.error_asset_original();
}

bool ResizePhoto(Image* image, const CGSize& desired_size) {
  if (desired_size.width >= image->width() &&
      desired_size.height >= image->height()) {
    return false;
  }
  int bits_per_pixel = 32;
  if (std::max(desired_size.width, desired_size.height) <= kThumbnailSize) {
    bits_per_pixel = 16;
    if (image->bits_per_component() == 5) {
      return false;
    }
  }
  Image new_image(image->Convert(desired_size, bits_per_pixel));
  new_image.swap(*image);
  return true;
}

WallTime ParseExifTimestamp(NSString* date_time) {
  if (!date_time) {
    return -1;
  }
  return ParseExifDate(ToSlice(date_time));
}

}  // namespace

PhotoManager::PhotoManager(UIAppState* state)
    : state_(state),
      photo_dir_(state_->photo_dir()),
      assets_initial_scan_(false) {
  state_->assets_scan_start()->Add(^{
      assets_initial_scan_ = state_->assets_initial_scan();
    });

  // Watch for new assets.
  state_->assets_scan_progress()->Add(
      ^(const AssetScanData& data) {
          @autoreleasepool {
            NewAssetPhoto(data.asset, data.asset_key, data.square_thumbnail);
          }
    });

  state_->assets_scan_end()->AddSingleShot(^(const StringSet* not_found) {
      assets_initial_scan_ = state_->assets_initial_scan();
    });
}

PhotoManager::~PhotoManager() {
}

int64_t PhotoManager::NewAssetPhoto(
    ALAsset* asset, const string& asset_key, CGImageRef square_thumbnail) {
  // Due to the horrific nature of the ALAssetsLibrary api, multiple asset
  // scans can be running concurrently. Enforce mutual exclusion for the
  // creation of new assets.
  MutexLock l(&assets_mu_);

  PhotoHandle p = state_->photo_table()->LoadAssetPhoto(asset_key, state_->db());
  if (p.get()) {
    // We already have a photo associated with the specified asset. Make sure
    // the asset_key is up to date.
    DBHandle updates = state_->NewDBTransaction();
    p->Lock();
    if (p->AddAssetKey(asset_key)) {
      p->Save(updates);
    }
    p->Unlock();
    updates->Commit();
    return 0;
  }

  // NOTE(pmattis): This is useful for limiting the number of photos found by
  // the client during development.
  // static int32_t photo_count = 0;
  // if (OSAtomicIncrement32(&photo_count) > 1) {
  //   return 0;
  // }

  // Verify the square thumbnail is, in fact, square.
  DCHECK_EQ(CGImageGetWidth(square_thumbnail), CGImageGetHeight(square_thumbnail));

  const CGSize dimensions = [asset defaultRepresentation].dimensions;
  float aspect_ratio = dimensions.width / dimensions.height;
  if (std::isnan(aspect_ratio)) {
    // Something is wrong with the asset. Don't try to add it.
    return 0;
  }

  // Create a new photo.
  DBHandle updates = state_->NewDBTransaction();
  p = state_->photo_table()->NewPhoto(updates);
  p->Lock();

  // Initialize the photo metadata.
  p->AddAssetKey(asset_key);

  if (kIOSVersion < "7") {
    Slice url;
    Slice fingerprint;
    DecodeAssetKey(asset_key, &url, &fingerprint);
    // TODO(peter): For backward compatibility, we currently add the old asset
    // key as well. This should be removed when the code is stable.
    p->AddAssetKey(EncodeAssetKey(url, AssetOldFingerprint(asset)));
  }

  NSDate* date = [asset valueForProperty:ALAssetPropertyDate];
  if (date) {
    p->set_timestamp([date timeIntervalSince1970]);
    if (p->timestamp() < 0) {
      // If the timestamp is negative, just use the current time and mark in
      // the metadata that bad value.
      p->set_timestamp(WallTime_Now());
      p->set_error_timestamp_invalid(true);
    }
    // Indicate that we should verify the timestamp when the asset is first
    // loaded.
    p->set_error_timestamp(true);
  }
  CLLocation* location = [asset valueForProperty:ALAssetPropertyLocation];
  if (location) {
    p->mutable_location()->CopyFrom(MakeLocation(location));
  }
  p->set_aspect_ratio(aspect_ratio);

  *p->mutable_perceptual_fingerprint() =
      FingerprintImage(square_thumbnail, aspect_ratio);

  const int64_t res = NewPhotoCommon(p, updates);
  if (res > 0) {
    Image image;
    image.reset([asset aspectRatioThumbnail]);
    // On iOS 7, the aspect-ratio thumbnail is not constrained to a maximum
    // dimension of 120. Perform that constraint ourselves.
    if (image.pixel_width() > kThumbnailSize ||
        image.pixel_height() > kThumbnailSize) {
      image = image.Convert(
          AspectFit(CGSizeMake(kThumbnailSize, kThumbnailSize),
                    image.aspect_ratio()).size,
          32);
    }
    MaybeWriteThumbnail(p, image);
  }
  return res;
}

int64_t PhotoManager::NewViewfinderPhoto(
    const PhotoMetadata& m, NSData* jpeg_data) {
  DBHandle updates = state_->NewDBTransaction();
  PhotoHandle p = state_->photo_table()->NewPhoto(updates);
  const string filename = PhotoOriginalFilename(p->id());
  if (!state_->photo_storage()->Write(filename, 0, ToSlice(jpeg_data), updates)) {
    updates->Abandon();
    return 0;
  }

  p->Lock();
  p->MergeFrom(m);
  return NewPhotoCommon(p, updates);
}

void PhotoManager::CopyToAssetsLibrary(int64_t photo_id, void (^completion)(string asset_url)) {
  ExportAssetPhotoOp::New(state_, photo_id, completion);
}

void PhotoManager::LoadLocalThumbnail(
    int64_t photo_id, void (^done)(Image image)) {
  PhotoHandle p = state_->photo_table()->LoadPhoto(photo_id, state_->db());
  if (!p.get()) {
    LOG("photo: %s is not a valid photo id", photo_id);
  } else {
    // For thumbnails we don't adjust for the screen scale as speed is the
    // important issue and we want to be sure to grab the lowest resolution image
    // available.
    const float scale = [UIScreen mainScreen].scale;
    const CGSize size = CGSizeMake(kThumbnailSize, kThumbnailSize);
    const int flags = WANT_IMAGE | QUEUE_DOWNLOAD | GENERATE_THUMBNAIL;
    if (MaybeLoadInternal(p, size, flags, ^(Image image) {
          // Set the image scale to the ui screen scale. On a retina display,
          // this will effectively halve the Image::{width,height}() which will
          // cause a higher-res photo to be loaded.
          Image new_image(image);
          if (new_image) {
            new_image.set_scale(scale);
          }
          done(new_image);
        })) {
      return;
    }
  }
  state_->async()->dispatch_low_priority(^{
      done(Image());
    });
}

void PhotoManager::LoadLocalPhoto(
    int64_t photo_id, CGSize size,
    void (^done)(Image image)) {
  PhotoHandle p = state_->photo_table()->LoadPhoto(photo_id, state_->db());
  if (!p.get()) {
    LOG("photo: %s is not a valid photo id", photo_id);
  } else {
    const float scale = [UIScreen mainScreen].scale;
    size.width *= scale;
    size.height *= scale;
    size = AspectFill(size, p->aspect_ratio()).size;
    const int flags = WANT_IMAGE | QUEUE_DOWNLOAD | GENERATE_THUMBNAIL;
    if (MaybeLoadInternal(p, size, flags, ^(Image image) {
          // Set the image scale to the ui screen scale.
          Image new_image(image);
          if (new_image) {
            new_image.set_scale(scale);
          }
          done(new_image);
        })) {
      return;
    }
  }
  state_->async()->dispatch_low_priority(^{
      done(Image());
    });
}

void PhotoManager::LoadNetworkThumbnail(
    int64_t photo_id, void (^done)(Image image)) {
  PhotoHandle p = state_->photo_table()->LoadPhoto(photo_id, state_->db());
  if (!p.get()) {
    LOG("photo: %s is not a valid photo id", photo_id);
    state_->async()->dispatch_low_priority(^{
        done(Image());
      });
    return;
  }

  if (p->label_error() ||
      p->upload_thumbnail() ||
      !state_->is_registered() ||
      !p->download_thumbnail()) {
    // Network loading cannot proceed. Just try to load the local thumbnail.
    LoadLocalThumbnail(photo_id, done);
    return;
  }

  // Wait for the download to complete. The callback will also be invoked if
  // the photo is deleted or quarantined.
  state_->net_queue()->WaitForDownload(photo_id, THUMBNAIL, ^{
      // The photo was written locally (or an error occurred). Just try to load
      // the local photo and let it take care of the error processing.
      VLOG("photo: %s network thumbnail loaded", photo_id);
      LoadLocalThumbnail(photo_id, done);
    });
}

void PhotoManager::LoadNetworkPhoto(
    int64_t photo_id, CGSize size,
    void (^done)(Image image)) {
  PhotoHandle p = state_->photo_table()->LoadPhoto(photo_id, state_->db());
  if (!p.get()) {
    LOG("photo: %s is not a valid photo id", photo_id);
    state_->async()->dispatch_low_priority(^{
        done(Image());
      });
    return;
  }

  if (p->label_error() ||
      p->upload_metadata() ||
      !state_->is_registered()) {
    // Network loading cannot proceed. Just try to load the local photo.
    VLOG("photo: %s unable to load network photo", photo_id);
    LoadLocalPhoto(photo_id, size, done);
    return;
  }

  size = AspectFill(size, p->aspect_ratio()).size;
  const float scale = [UIScreen mainScreen].scale;
  const float max_size = std::max(size.width, size.height) * scale;
  NetworkQueue::PhotoType download_type = static_cast<NetworkQueue::PhotoType>(0);
  bool download_queued = false;
  if (max_size <= kThumbnailSize) {
    download_type = THUMBNAIL;
    download_queued = !p->upload_thumbnail() && p->download_thumbnail();
  } else if (max_size <= kMaxFullSizeScale * kFullSize ||
             p->error_download_original()) {
    // Get the full size image even if it's not as large as the requested
    // size in the event that no higher-resolution image is available.
    // If the size of full isn't large enough, adjust "size" to match
    // so loading the local photo doesn't fail.
    if (max_size > kFullSize) {
      const float adjust = kFullSize / max_size;
      size = CGSizeMake(size.width * adjust, size.height * adjust);
    }
    download_type = FULL;
    download_queued = !p->upload_full() && p->download_full();
  } else {
    DCHECK(max_size <= kOriginalSize) << "; " << max_size << " vs. " << kOriginalSize;
    DCHECK(!p->error_download_original());
    download_type = ORIGINAL;
    download_queued = !p->upload_original() && p->download_original();
  }
  if (!download_queued) {
    // The photo is not queued for download and has either already been
    // downloaded or is not on the server. Just try to load the local photo.
    VLOG("photo: %s network photo already loaded", photo_id);
    LoadLocalPhoto(photo_id, size, done);
    return;
  }

  // Wait for the download to complete. The callback will also be invoked if
  // the photo is deleted or quarantined.
  state_->net_queue()->WaitForDownload(photo_id, download_type, ^{
      // The photo was written locally (or an error occurred). Just try to load
      // the local photo and let it take care of the error processing.
      VLOG("photo: %s network photo loaded", photo_id);
      LoadLocalPhoto(photo_id, size, done);
    });
}

void PhotoManager::LoadViewfinderImages(
    int64_t photo_id, const DBHandle& db, void (^done)(bool success)) {
  PhotoHandle ph = state_->photo_table()->LoadPhoto(photo_id, db);
  if (!ph.get()) {
    state_->async()->dispatch_low_priority(^{
        done(false);
      });
    return;
  }
  if (!LoadViewfinderImages(ph, done)) {
    state_->async()->dispatch_low_priority(^{
        done(false);
      });
  }
}

int64_t PhotoManager::NewPhotoCommon(const PhotoHandle& p, const DBHandle& updates) {
  // Find candidate duplicate photos. If any candidates are found, the photo is
  // hidden temporarily while it undergoes further processing.
  p->FindCandidateDuplicates();

  state_->episode_table()->AddPhotoToEpisode(p, updates);

  // Queue the photo for upload.
  p->set_upload_metadata(true);
  p->set_upload_thumbnail(true);
  p->set_upload_medium(true);
  p->set_upload_full(true);
  p->set_upload_original(true);

  // Save the photo.
  p->SaveAndUnlock(updates);
  VLOG("photo: new photo: %s", p->id());

  updates->Commit();
  return p->id().local_id();
}

void PhotoManager::QuarantinePhoto(PhotoHandle p, const string& reason) {
  DBHandle updates = state_->NewDBTransaction();
  QuarantinePhoto(p, reason, updates);
  updates->Commit();
}

void PhotoManager::QuarantinePhoto(
    PhotoHandle p, const string& reason, const DBHandle& updates) {
  p->Lock();
  p->Quarantine(reason, updates);
  p->SaveAndUnlock(updates);
}

void PhotoManager::LoadViewfinderPhotoError(
    PhotoHandle p, const string& filename, void (^done)(bool error, Image image)) {
  // Just remove the file and database entry associated with the error.
  DBHandle updates = state_->NewDBTransaction();
  state_->photo_storage()->Delete(filename, updates);
  updates->Commit();
  done(true, Image());
}

void PhotoManager::LoadAssetPhotoError(
    PhotoHandle p, int types, void (^done)(bool error, Image image)) {
  p->Lock();
  if (types & THUMBNAIL) {
    p->set_error_asset_thumbnail(true);
  }
  if (types & FULL) {
    p->set_error_asset_full(true);
  }
  if (types & ORIGINAL) {
    p->set_error_asset_original(true);
  }

  DBHandle updates = state_->NewDBTransaction();
  p->SaveAndUnlock(updates);
  updates->Commit();
  done(true, Image());
}

bool PhotoManager::LoadViewfinderImages(
    PhotoHandle ph, void (^completion)(bool success)) {
  // Load the image data for one of the desired sizes. Note the order is
  // important here as we want to have viewfinder generate the full, medium and
  // thumbnail size images from the original image.

  int size = 0;
  if (!ph->images().has_orig()) {
    size = kOriginalSize;
  } else if (!ph->images().has_full()) {
    size = kFullSize;
  } else if (!ph->images().has_med()) {
    size = kMediumSize;
  } else if (!ph->images().has_tn()) {
    size = kThumbnailSize;
    // Force the thumbnail jpeg to be regenerated if it was not generated from
    // the medium image. The new thumbnail will be generated from the next
    // larger image (the medium) and not from the ALAsset.
    const string filename = PhotoThumbnailFilename(ph->id());
    if (state_->photo_storage()->Metadata(filename).parent_size() !=
        kMediumSize) {
      DBHandle updates = state_->NewDBTransaction();
      state_->photo_storage()->Delete(filename, updates);
      updates->Commit();
    }
  } else {
    // If this is an asset photo and we're not storing originals to the cloud,
    // remove the viewfinder original image immediately in order to save disk
    // space.
    if (ph->HasAssetUrl() && !state_->store_originals()) {
      const string filename = PhotoOriginalFilename(ph->id());
      DBHandle updates = state_->NewDBTransaction();
      state_->photo_storage()->Delete(filename, updates);
      updates->Commit();
    }
    state_->async()->dispatch_low_priority(^{
        DBHandle updates = state_->NewDBTransaction();
        ph->Lock();
        ph->SaveAndUnlock(updates);
        updates->Commit();
        completion(true);
      });
    return true;
  }

  void (^done)(const string& path, const string& md5) =
      ^(const string& path, const string& md5) {
    const int64_t file_size = FileSize(path);
    if (file_size <= 0 || md5.empty()) {
      QuarantinePhoto(
          ph, Format("upload metadata: unable to load image data: %s",
                     PhotoSizeSuffix(size)));
      completion(false);
      return;
    }
    PhotoMetadata::Image* i = NULL;
    if (size == kThumbnailSize) {
      i = ph->mutable_images()->mutable_tn();
    } else if (size == kMediumSize) {
      i = ph->mutable_images()->mutable_med();
    } else if (size == kFullSize) {
      i = ph->mutable_images()->mutable_full();
    } else if (size == kOriginalSize) {
      i = ph->mutable_images()->mutable_orig();
    } else {
      CHECK(false);
      return;        // Silence the code analyzer.
    }
    i->set_size(file_size);
    i->set_md5(md5);
    VLOG("photo: %s: md5 done: %s: %d %s",
         ph->id(), PhotoSizeSuffix(size), i->size(), i->md5());

    LoadViewfinderImages(ph, completion);
  };

  return MaybeLoadImageData(ph, size, done);
}

bool PhotoManager::MaybeLoadImageData(
    PhotoHandle p, int size,
    void (^completion)(const string& path, const string& md5)) {
  void (^done)() = ^{
    const string filename = PhotoFilename(p->id(), size);
    const string path = JoinPath(photo_dir_, filename);
    const string md5 = state_->photo_storage()->Metadata(filename).md5();
    completion(path, md5);
  };

  // Passing STORE_JPEG causes MaybeLoadInternal() to write the jpeg to the
  // viewfinder photo area. We explicitly do not pass
  // QUEUE_DOWNLOAD. MaybeLoadImageData() is called to load local image data in
  // preparation to upload images and for exporting images to the assets
  // library. In neither case do we want to queue the image for download if it
  // doesn't exist locally.
  return MaybeLoadInternal(p, CGSizeMake(size, size), STORE_JPEG, ^(Image image) {
      done();
    });
}

bool PhotoManager::MaybeLoadInternal(
    PhotoHandle p, CGSize size, int load_flags, void (^done)(Image image)) {
  CHECK_NE((load_flags & STORE_JPEG) != 0,
           (load_flags & WANT_IMAGE) != 0);

  if (p->label_error()) {
    return false;
  }

  void (^completion)(bool, Image) = ^(bool error, Image image) {
    if (!error) {
      done(image);
      return;
    }
    dispatch_main(^{
        // Recursively try to load the photo, this will cause other resolutions
        // of the photo to be attempted and eventually kick down into the asset
        // library loading.
        if (MaybeLoadInternal(p, size, load_flags, done)) {
          return;
        }
        done(Image());
      });
  };

  // First try and load the image from the local viewfinder storage area. This
  // might fail if an appropriate resolution image does not exist, or the jpeg
  // has been corrupted. On jpeg corruption (and some other errors),
  // MaybeLoadViewfinder() will return true, but error==true will be returned
  // to the completion and the offending corrupt file will have been deleted.
  if (MaybeLoadViewfinder(p, size, load_flags, completion)) {
    return true;
  }

  // Next try and load the image from the assets library. This might fail if
  // the asset does not exist or has some other error (e.g. the asset exists
  // but the thumbnail does not).
  if (MaybeLoadAsset(p, size, load_flags, completion)) {
    return true;
  }

  MaybeMarkPhotoForDownload(p, size, load_flags);
  return false;
}

void PhotoManager::MaybeMarkPhotoForDownload(
    PhotoHandle p, CGSize size, int load_flags) {
  if (!p->upload_metadata()) {
    if (load_flags & QUEUE_DOWNLOAD) {
      state_->async()->dispatch_after_main(0, ^{
          // The photo has been uploaded to the server, try to download the images
          // again.
          DBHandle updates = state_->NewDBTransaction();
          const float max_size = std::max(size.width, size.height);
          p->Lock();

          bool changed = false;  // don't save unless changed.
          if (!p->error_download_thumbnail() &&
              max_size <= kThumbnailSize) {
            if (!p->error_ui_thumbnail() || !p->download_thumbnail()) {
              p->set_error_ui_thumbnail(true);
              p->set_download_thumbnail(true);
              changed = true;
            }
          } else if (!p->error_download_full() &&
                     (max_size <= kMaxFullSizeScale * kFullSize ||
                      p->error_download_original())) {
            // TODO(pmattis): Also try and download the medium resolution
            // image. This needs coordination with LoadNetworkPhoto() and error
            // handling in case the full resolution image exists but the medium
            // resolution image does not.
            if (!p->error_ui_full() || !p->download_full()) {
              p->set_error_ui_full(true);
              p->set_download_full(true);
              changed = true;
            }
          } else if (!p->error_download_original()) {
            if (!p->error_ui_original() || !p->download_original()) {
              p->set_error_ui_original(true);
              p->set_download_original(true);
              changed = true;
            }
          }

          if (changed) {
            p->SaveAndUnlock(updates);
            updates->Commit();
            state_->net_manager()->Dispatch();
          } else {
            p->Unlock();
          }
        });
    }
  } else {
    if (p->HasAssetUrl() && !state_->assets_authorized()) {
      // Do not quarantine asset photos if the user has denied us access to
      // their asset library. Instead, just wait for the user to give us access
      // again.
    } else {
      // The photo only exists locally and cannot be loaded: quarantine it.
      QuarantinePhoto(p, "load: local-only photo");
    }
  }
}

// Tries to load a non-assets-library (a.k.a. viewfinder) photo. This method
// has a synchronous and asynchronous portion. The synchronous portion looks
// for an image to load and returns false if no suitable image could be
// found. If false is returned, the "done" callback will never be invoked. If
// true is returned, a suitable image to load was found and the actual loading
// is kicked onto a low priority thread. The done callback will be invoked from
// the low priority thread and passed true on a successful load and false
// otherwise.
bool PhotoManager::MaybeLoadViewfinder(
    PhotoHandle p, CGSize size, int load_flags,
    void (^done)(bool error, Image image)) {
  // __block WallTimer timer;
  const bool want_image = (load_flags & WANT_IMAGE) != 0;

  // Find the smallest resolution image that satisfies the request.
  const float max_size = std::max(size.width, size.height);

  string filename_metadata;
  const string filename =
      state_->photo_storage()->LowerBound(
          p->id().local_id(), max_size, &filename_metadata);
  if (filename.empty()) {
    return false;
  }

  // Fail if the file does not exist.
  if (state_->photo_storage()->Size(filename) <= 0) {
    state_->async()->dispatch_low_priority(^{
        LoadViewfinderPhotoError(p, filename, done);
      });
    return true;
  }

  // Determine the max dimension of the on disk image.
  const int max_dim = PhotoFilenameToSize(filename);
  if (max_size > max_dim) {
    // We've been asked to load an image that is larger than the one we have on
    // disk. Fail and let network loading run if we haven't encountered a
    // network error for that photo size.
    if (!p->error_download_thumbnail() &&
        max_size <= kThumbnailSize) {
      DCHECK_LT(max_dim, kThumbnailSize);
      return false;
    } else if (!p->error_download_full() &&
               (max_size <= kMaxFullSizeScale * kFullSize ||
                p->error_download_original())) {
      if (max_dim < kFullSize) {
        return false;
      }
      // We already have a full image.
    } else if (!p->error_download_original()) {
      return false;
    }
    // There is no larger image to load from the network. Use what we have.
  }

  // Map the requested size to one of thumbnail, medium, full or original.
  const int load_size = MaxSizeToLoadSize(max_size);
  if (max_dim == load_size && !want_image && !filename_metadata.empty()) {
    // We already have the correct file and the caller did not want either the
    // jpeg data or image.
    state_->async()->dispatch_low_priority(^{
        done(false, Image());
      });
    return true;
  }

  state_->async()->dispatch_low_priority(^{
      const string path = state_->photo_storage()->PhotoPath(filename);
      Image image;
      if (max_dim <= max_size * 1.5) {
        // We have an appropriate resolution. If we need the image, load and resize
        // it.
        if (want_image) {
          if (!image.Decompress(path, 0, NULL)) {
            LOG("photo: %s: loading failed: %s", p->id(), filename);
            LoadViewfinderPhotoError(p, filename, done);
            return;
          } else {
            // LOG("photo: %s: loaded image: %dx%d: %.3f ms",
            //     p->id(), image.width(), image.height(),
            //     timer.Milliseconds());
            // timer.Restart();
          }
        }
      } else {
        // TODO(pmattis): Use Image::Decompress() to perform the decoding.
        NSURL* url = [NSURL fileURLWithPath:NewNSString(path)];
        ScopedRef<CGImageSourceRef> image_src(
            CGImageSourceCreateWithURL((__bridge CFURLRef)url, NULL));
        if (!image_src || CGImageSourceGetCount(image_src) < 1) {
          if (!image_src) {
            LOG("photo: %s: unable to decompress image: %s",
                p->id(), filename);
          } else {
            LOG("photo: %s: no images found: %s", p->id(), filename);
          }
          LoadViewfinderPhotoError(p, filename, done);
          return;
        } else {
          image.acquire(
              CGImageSourceCreateThumbnailAtIndex(
                  image_src, 0,
                  Dict(kCGImageSourceCreateThumbnailFromImageAlways, true,
                       kCGImageSourceThumbnailMaxPixelSize, load_size,
                       kCGImageSourceCreateThumbnailWithTransform, true)));
          // LOG("photo: %s: loaded image: %s: %dx%d: %.3f ms",
          //     p->id(), filename, image.width(), image.height(),
          //     timer.Milliseconds());
          // timer.Restart();

          if (max_dim != load_size) {
            NSDictionary* raw_properties =
                (__bridge_transfer NSDictionary*)
                CGImageSourceCopyPropertiesAtIndex(image_src, 0, NULL);
            Dict properties(
                [[NSMutableDictionary alloc] initWithDictionary:raw_properties]);

            // Erase all 3 image orientation properties.
            properties.erase(kCGImagePropertyOrientation);
            properties.find_dict(kCGImagePropertyIPTCDictionary)
                .erase(kCGImagePropertyIPTCImageOrientation);
            properties.find_dict(kCGImagePropertyTIFFDictionary)
                .erase(kCGImagePropertyTIFFOrientation);

            NSData* jpeg_data =
                image.CompressJPEG(&properties, kJpegThumbnailQuality);
            if (jpeg_data && CanWriteJpeg(load_size, max_dim)) {
#ifdef DEBUG
              Image check_image;
              Dict check_properties;
              check_image.Decompress(jpeg_data, load_size, &check_properties);
              CHECK(!check_properties.find(kCGImagePropertyOrientation))
                  << check_properties.dict();
#endif  // DEBUG

              const string new_filename = PhotoFilename(p->id(), load_size);
              DBHandle updates = state_->NewDBTransaction();
              if (state_->photo_storage()->Write(
                      new_filename, max_dim, ToSlice(jpeg_data), updates)) {
                updates->Commit();
              }
              // LOG("photo: %s: wrote image: %s (%s): %d bytes: %.3f ms",
              //     p->id(), new_filename, filename,
              //     jpeg_data.length, timer.Milliseconds());
            }
          }
        }
      }

      state_->photo_storage()->Touch(filename, filename_metadata);
      done(false, image);
    });
  return true;
}

void PhotoManager::MaybeRetryLoadAsset(PhotoHandle p, CGSize size, int load_flags,
                                       void (^done)(bool error, Image image),
                                       const string& asset_key) {
  DBHandle updates = state_->NewDBTransaction();
  p->Lock();
  p->RemoveAssetKey(asset_key);
  p->SaveAndUnlock(updates);
  updates->Commit();
  if (p->HasAssetUrl()) {
    LOG("photo: %s: loading asset %s failed, retrying with next asset key", p->id(), asset_key);
    if (MaybeLoadAsset(p, size, load_flags, done)) {
      return;
    }
  }
  LOG("photo: %s: loading failed: %s", p->id(), asset_key);
  MaybeMarkPhotoForDownload(p, size, load_flags);
  LoadAssetPhotoError(p, THUMBNAIL|FULL|ORIGINAL, done);
}

bool PhotoManager::MaybeLoadAsset(
    PhotoHandle p, CGSize size, int load_flags,
    void (^done)(bool error, Image image)) {
  if (p->asset_keys_size() == 0) {
    return false;
  }
  const string asset_key = p->asset_keys(0);

  // Check for existing errors before attempting to load the asset.
  const float max_size = std::max(size.width, size.height);
  if (!state_->assets_authorized() || HasAssetError(*p, max_size)) {
    return false;
  }

  __block WallTimer timer;
  ALAssetsLibraryAssetForURLResultBlock result = ^(ALAsset* asset) {
    if (!asset) {
      // The asset does not exist.
      MaybeRetryLoadAsset(p, size, load_flags, done, asset_key);
      return;
    }

    // LOG("photo: %s: retrieved asset: %.3f ms",
    //     p->id(), timer.Milliseconds());
    // timer.Restart();

    Image image;
    const bool store_jpeg = (load_flags & STORE_JPEG) != 0;
    const bool want_image = (load_flags & WANT_IMAGE) != 0;

    if (max_size <= kThumbnailSize) {
      image.reset([asset aspectRatioThumbnail]);
      if (!image) {
        LOG("photo: %s: thumbnail image not found: %s",
            p->id(), asset_key);
        LoadAssetPhotoError(p, THUMBNAIL, done);
        return;
      } else {
        // LOG("photo: %s: loaded thumbnail image: %.3f ms",
        //     p->id(), timer.Milliseconds());
        // timer.Restart();

        DCHECK(!store_jpeg);
        if (!assets_initial_scan_ && (load_flags & GENERATE_THUMBNAIL)) {
          // Don't compress jpegs during the initial asset scan as we don't
          // want to use the CPU cycles.
          Image image_ref(image);
          state_->async()->dispatch_low_priority(^{
              MaybeWriteThumbnail(p, image_ref);
              // LOG("photo: %s: wrote thumbnail image: %.3f ms",
              //     p->id(), timer.Milliseconds());
            });
        }
      }
    } else {
      @autoreleasepool {
        ALAssetRepresentation* rep = [asset defaultRepresentation];
        MaybeUpdateMetadata(p, rep);

        bool use_full_resolution = (max_size > kFullSize);
        if (use_full_resolution && !store_jpeg) {
          // TODO(pmattis): Investigate using
          // ALAssetRepresentation.dimensions instead of the byte size of
          // the full resolution jpeg. "dimensions" is only available on
          // iOS 5.1 and above.

          // Don't use the full resolution jpeg if it is large and the full
          // size can scale up acceptably.
          if (rep.size >= kMaxOriginalJpegSizeForImage &&
              max_size <= kMaxFullSizeScale * kFullSize) {
            use_full_resolution = false;
          }
        }

        if (use_full_resolution) {
          // Generate the image if we were requested to or if the image
          // contains edits (!p->adjustment_xmp.empty()).
          Dict metadata(rep.metadata);
          Value adjustment_xmp = metadata.find_value(@"AdjustmentXMP");
          const bool has_edits = (bool)adjustment_xmp.get();
          if (want_image || (store_jpeg && has_edits)) {
            image.reset([rep fullResolutionImage]);
            if (!image) {
              LOG("photo: %s: full resolution image not found: %s",
                  p->id(), asset_key);
              LoadAssetPhotoError(p, ORIGINAL, done);
              return;
            }
            // Set the orientation and scale. This is only needed for the
            // fullResolutionImage. Nice API Apple.
            image.set_asset_orientation(rep.orientation);
            image.set_scale(rep.scale);

            // LOG("photo: %s: loaded full resolution image: %dx%d: %.3f ms",
            //     p->id(), image.width(), image.height(),
            //     timer.Milliseconds());
            // timer.Restart();

            // In addition to applying the adjustment xmp,
            // MaybeApplyAdjustmentXMP will resize the image to the
            // specified size, obviating the need to call ResizePhoto().
            if (has_edits && MaybeApplyAdjustmentXMP(p, &image, size, ToSlice((NSString*)adjustment_xmp))) {
              // LOG("photo: %s: applied adjustments: %dx%d: %.3f ms",
              //     p->id(), image.width(), image.height(),
              //     timer.Milliseconds());
              // timer.Restart();
            } else if (ResizePhoto(&image, size)) {
              // LOG("photo: %s: resized full resolution image: %dx%d: %.3f ms",
              //     p->id(), image.pixel_width(), image.pixel_height(),
              //     timer.Milliseconds());
              // timer.Restart();
            } else if (!image) {
              LOG("photo: %s: resizing full resolution image failed", p->id());
            }
          }
          if (store_jpeg) {
            NSData* jpeg_data;
            if (image && has_edits) {
              // The image had edits. Compress the edited image.
              Dict properties(Dict(rep.metadata).clone());
              jpeg_data = image.CompressJPEG(&properties, kJpegOriginalQuality);
            } else {
              NSMutableData* mutable_data =
                  [[NSMutableData alloc] initWithLength:rep.size];
              uint8_t* dest = reinterpret_cast<uint8_t*>(mutable_data.mutableBytes);
              NSError* error = NULL;
              [rep getBytes:dest fromOffset:0 length:rep.size error:&error];
              if (error) {
                LOG("photo: %s: error reading original jpeg data",
                    p->id());
                LoadAssetPhotoError(p, ORIGINAL, done);
                return;
              }
              jpeg_data = mutable_data;
            }
            DBHandle updates = state_->NewDBTransaction();
            const string filename = PhotoOriginalFilename(p->id());
            if (state_->photo_storage()->Write(
                    filename, 0, ToSlice(jpeg_data), updates)) {
              updates->Commit();
            }
            // LOG("photo: %s: wrote image: %s: %d bytes: %.3f ms",
            //     p->id(), filename, jpeg_data.length, timer.Milliseconds());
          }
        } else {
          image.reset([rep fullScreenImage]);
          image.set_scale(rep.scale);
          if (!image) {
            LOG("photo: %s: full screen image not found: %s",
              p->id(), asset_key);
            LoadAssetPhotoError(p, FULL, done);
            return;
          } else {
            // LOG("photo: %s: loaded full screen image: %dx%d: %.3f ms",
            //     p->id(), image.width(), image.height(),
            //     timer.Milliseconds());
            // timer.Restart();

            if (want_image) {
              if (ResizePhoto(&image, size)) {
                // LOG("photo: %s: resized full screen image: %dx%d: %.3f ms",
                //     p->id(), image.pixel_width(), image.pixel_height(),
                //     timer.Milliseconds());
              }
              if (!image) {
                LOG("photo: %s: resizing full screen image failed", p->id());
              }
            }

            // NOTE(peter): We intentionally ignore the store_jpeg
            // parameter here as we only want to generate medium and full
            // jpegs from the original jpeg in order to provide more
            // determinism in the generated jpeg data.
          }
        }
      }
    }
    done(false, image);
  };

  ALAssetsLibraryAccessFailureBlock failure = ^(NSError* error) {
    LOG("photo: %s: loading failed: %s", p->id(), asset_key);
    state_->async()->dispatch_low_priority(^{
        LoadAssetPhotoError(p, THUMBNAIL|FULL|ORIGINAL, done);
      });
  };

  state_->AssetForKey(asset_key, result, failure);
  return true;
}

void PhotoManager::MaybeWriteThumbnail(PhotoHandle p, const Image& image) {
  NSData* jpeg_data = image.CompressJPEG(NULL, kJpegThumbnailQuality);
  if (!jpeg_data) {
    return;
  }
  DBHandle updates = state_->NewDBTransaction();
  const string filename = PhotoThumbnailFilename(p->id());
  if (state_->photo_storage()->Write(filename, 0, ToSlice(jpeg_data), updates)) {
    updates->Commit();
  }
}

// Update photo metadata either if there's an error in the timestamp (need to
// pull the creation timestamp from exif metadata); or if any edits have been
// made to the photo (need to copy the edit adjustments XML to photo metadata).
void PhotoManager::MaybeUpdateMetadata(
    const PhotoHandle& p, ALAssetRepresentation* rep) {
  if (!p->error_timestamp()) {
    return;
  }

  Dict metadata(rep.metadata);
  WallTime timestamp = -1;

  if (p->error_timestamp()) {
    DCHECK(!p->id().has_server_id());
    // LOG("photo: maybe update timestamp: %s", p->id());

    // ALAssetPropertyDate returns the last modification time of the asset. We
    // want the creation time that is stored in the DateTimeOriginal exif
    // metadata. Unfortunately, retrieval of the exif metadata is orders of
    // magnitude slower than accessing ALAssetPropertyDate (10's of milliseconds
    // vs sub-millisecond). So we compromise and assume ALAssetPropertyDate is
    // correct initially and set a flag on the photo metadata
    // (PhotoMetadata::error_timestamp) that indicates we should verify the
    // timestamp the first time the full-screen or original resolution version of
    // the assets is accessed. This might be when the photo is displayed for the
    // first time, or when it is being uploaded.

    // TODO(pmattis): The following line of code generates the C++ exception:
    // Threw error #101 (Unregistered schema namespace URI) in
    // serializeStructProperty(). It looks like it also catches the exception,
    // but it is suspicious that this is happening. It reproduces every time in
    // my iOS 6.0 Simulator client.
    Dict exif(metadata.find_dict(kCGImagePropertyExifDictionary));
    WallTime timestamp = ParseExifTimestamp(
        exif.find(kCGImagePropertyExifDateTimeOriginal));
    if (timestamp < 0) {
      timestamp = ParseExifTimestamp(
          exif.find(kCGImagePropertyExifDateTimeDigitized));
    }
    if (timestamp < 0) {
      Dict tiff(metadata.find_dict(kCGImagePropertyTIFFDictionary));
      timestamp = ParseExifTimestamp(
          tiff.find(kCGImagePropertyTIFFDateTime));
    }
  }

  DBHandle updates = state_->NewDBTransaction();

  p->Lock();
  p->clear_error_timestamp();

  if (timestamp >= 0 && p->ShouldUpdateTimestamp(timestamp)) {
    LOG("photo: %s: update timestamp: %s -> %s", p->id(),
        WallTimeFormat("%F %T", p->timestamp()),
        WallTimeFormat("%F %T", timestamp));
    p->set_timestamp(timestamp);

    EpisodeHandle e = state_->episode_table()->LoadEpisode(p->episode_id(), updates);
    state_->episode_table()->AddPhotoToEpisode(p, updates);
    if (e.get() && e->id().local_id() != p->episode_id().local_id()) {
      e->Lock();
      e->RemovePhoto(p->id().local_id());
      e->SaveAndUnlock(updates);
    }
  }

  p->SaveAndUnlock(updates);
  updates->Commit();
}

bool PhotoManager::MaybeApplyAdjustmentXMP(
    const PhotoHandle& p, Image* image, CGSize desired_size, const Slice& adjustment_xmp) {
  if (adjustment_xmp.empty()) {
    return false;
  }
  if (kIOSVersion < "6.0") {
    // TODO(peter): Parse the XMP ourselves and generate the list of
    // filters. The filters all exist on iOS 5.0, but
    // filterArrayFromSerializedXMP does not. Looks like apple internally uses
    // the XMPCore library that is part if the xmpsdk from Adobe:
    //     http://www.adobe.com/devnet/xmp.html
    return false;
  }

  CIImage* input_image =
      [CIImage imageWithCGImage:*image];
  NSError* error = NULL;
  NSArray* filters =
      [CIFilter filterArrayFromSerializedXMP:NewNSData(adjustment_xmp)
                            inputImageExtent:input_image.extent
                                       error:&error];
  if (error) {
    LOG("photo: %s: CIFilter creation failed: %@\n%s",
        p->id(), error, adjustment_xmp);
    return false;
  }

  CIImage* output_image = input_image;
  for (CIFilter* filter in filters) {
    [filter setValue:output_image forKey:kCIInputImageKey];
    output_image = [filter outputImage];
  }

  if (desired_size.width > 0 && desired_size.height > 0) {
    desired_size = image->ToImageCoordinates(desired_size);
    const CGSize size = output_image.extent.size;
    const float scale = std::max((float)desired_size.width / size.width,
                                 (float)desired_size.height / size.height);
    if (scale < 1) {
      output_image = [output_image imageByApplyingTransform:
                                     CGAffineTransformMakeScale(scale, scale)];
    }
  }

  image->acquire([core_image_context() createCGImage:output_image
                                            fromRect:output_image.extent]);
  return true;
}

CIContext* PhotoManager::core_image_context() {
  MutexLock l(&core_image_mu_);
  if (!core_image_context_) {
    // NOTE(peter): The software renderer is an order of magnitude slower. Use
    // the GPU!
    core_image_context_ =
        [CIContext contextWithOptions:
                     Dict(kCIContextUseSoftwareRenderer, NO)];
  }
  return core_image_context_;
}

// local variables:
// mode: c++
// end:
