// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

// TODO(pmattis): Interpret the "regions" section of the
// kCGImagePropertyExifAuxDictionary dictionary in [ALAssetRepresentation
// metadata]. See
// http://owl.phy.queensu.ca/~phil/exiftool/TagNames/XMP.html.
//
// {
//     Regions = {
//         HeightAppliedTo = 2448;
//         RegionList = (
//             {
//                 Height = "0.246";
//                 Type = Face;
//                 Width = "0.184";
//                 X = "0.212";
//                 Y = "0.254";
//             }
//         );
//         WidthAppliedTo = 3264;
//     };
// }
//
// TODO(pmattis): What happens to image and jpeg loading if the photo is
// deleted during the load?
//
// TODO(pmattis): Asset keys are not unique across devices. Do not assume they
// are.
//
// TODO(pmattis): Discover the real original timestamp of a photo whenever the
// full-screen jpeg is viewed and use that timestamp to move the photo to the
// correct episode.
//
// TODO(pmattis): Add checks that we never try to upload photo metadata for a
// photo we don't own.
//
// TODO(pmattis): Add a PhotoManager::Scanner which scans over the photos,
// checking for inconsistencies and repairing them.

#import <AssetsLibrary/AssetsLibrary.h>
#import <CoreImage/CoreImage.h>
#import <ImageIO/ImageIO.h>
#import <MobileCoreServices/UTCoreTypes.h>
#import <libkern/OSAtomic.h>
#import "Analytics.h"
#import "AppState.h"
#import "AssetsManager.h"
#import "Breadcrumb.pb.h"
#import "ContactManager.h"
#import "DB.h"
#import "Exif.h"
#import "FileUtils.h"
#import "GeocodeManager.h"
#import "LocationTracker.h"
#import "LocationUtils.h"
#import "Logging.h"
#import "NetworkManager.h"
#import "PathUtils.h"
#import "PhotoManager.h"
#import "PhotoMetadata.pb.h"
#import "PhotoStorage.h"
#import "PhotoView.h"
#import "PlacemarkHistogram.h"
#import "Server.pb.h"
#import "ServerUtilsInternal.h"
#import "STLUtils.h"
#import "Timer.h"

namespace {

const string kDeviceIdKey = DBFormat::metadata_key("device_id");
const string kNextPhotoIdKey = DBFormat::metadata_key("next_photo_id");
// TODO(peter): This should be 'next_episode_id', but it's a pain to change.
const string kNextEpisodeIdKey = DBFormat::metadata_key("next_event_id");
const string kQueryUpdatesKey = DBFormat::metadata_key("query_updates");
const string kResetErrorsKey = DBFormat::metadata_key("reset_errors");
// If the value stored under kResetErrorsKey does not match kResetErrorsValue
// all of the error labels will be cleared from photos. This can be used to
// reset the error state of all photos when a client update fixes the
// underlying cause of the error.
const string kResetErrorsValue = "1";
const double kMaxTimeDist = 60 * 60;      // 1 hour
const double kMaxLocDist = 10000;         // 10 km
const double kPauseNetworkDuration = 2;
const float kJpegThumbnailQuality = 0.7;
const int kMaxPhotosPerUpload = 10;
const int kMaxQueuedDetects = 10;
const int kMaxPhotos = std::numeric_limits<int>::max();
// const int kMaxPhotos = 1;

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

void SetUploadBits(PhotoMetadata* m, int bits) {
  m->set_upload(m->upload() | bits);
}

void ClearUploadBits(PhotoMetadata* m, int bits) {
  m->set_upload(m->upload() & ~bits);
  if (m->upload() == 0) {
    m->clear_upload();
  }
}

bool UploadPhoto(PhotoManager::PhotoData* p, PhotoManager::Env* env) {
  return p->episode &&
      (env->cloud_storage() || p->metadata.has_share());
}

bool UploadMetadata(const PhotoMetadata& m) {
  return (m.upload() & m.METADATA) != 0;
}

bool UploadThumbnail(const PhotoMetadata& m) {
  return (m.upload() & m.THUMBNAIL) != 0;
}

bool UploadMedium(const PhotoMetadata& m) {
  return (m.upload() & m.MEDIUM) != 0;
}

bool UploadFull(const PhotoMetadata& m) {
  return (m.upload() & m.FULL) != 0;
}

bool UploadOriginal(const PhotoMetadata& m) {
  return (m.upload() & m.ORIGINAL) != 0;
}

void SetDownloadBits(PhotoMetadata* m, int bits) {
  m->set_download(m->download() | bits);
}

void ClearDownloadBits(PhotoMetadata* m, int bits) {
  m->set_download(m->download() & ~bits);
  if (m->download() == 0) {
    m->clear_download();
  }
}

bool DownloadThumbnail(const PhotoMetadata& m) {
  return (m.download() & m.THUMBNAIL) != 0;
}

bool DownloadMedium(const PhotoMetadata& m) {
  return (m.download() & m.MEDIUM) != 0;
}

bool DownloadFull(const PhotoMetadata& m) {
  return (m.download() & m.FULL) != 0;
}

bool DownloadOriginal(const PhotoMetadata& m) {
  return (m.download() & m.ORIGINAL) != 0;
}

void SetServerMetadataBits(PhotoMetadata* m, int bits) {
  m->set_server(m->server() | bits);
}

int GetLocalMetadataBits(const PhotoManager::PhotoData* p) {
  int local_bits = 0;
  if (p->metadata.has_parent_id()) {
    local_bits |= PhotoMetadata::PARENT_ID;
  }
  if (p->metadata.has_episode_id()) {
    local_bits |= PhotoMetadata::EPISODE_ID;
  }
  if (p->metadata.has_user_id()) {
    local_bits |= PhotoMetadata::USER_ID;
  }
  if (p->metadata.has_aspect_ratio()) {
    local_bits |= PhotoMetadata::ASPECT_RATIO;
  }
  if (p->metadata.has_timestamp()) {
    local_bits |= PhotoMetadata::TIMESTAMP;
  }
  if (p->location || p->metadata.has_location()) {
    local_bits |= PhotoMetadata::LOCATION;
  }
  if (p->placemark || p->metadata.has_placemark()) {
    local_bits |= PhotoMetadata::PLACEMARK;
  }
  if (p->metadata.has_caption()) {
    local_bits |= PhotoMetadata::CAPTION;
  }
  if (p->metadata.has_link()) {
    local_bits |= PhotoMetadata::LINK;
  }
  return local_bits;
}

int PhotoPriority(const PhotoMetadata& m, bool wifi) {
  // Calculate a priority for the photo given its state and the state of the
  // network connection. The photo priority and timestamp determine which photo
  // will be queued next. The code in MaybeQueueNetwork() determines what on
  // the photo will be queued, which usually matches up with the priority.
  //
  // The priorities are conceptually divided into 5 ranges 0-9, 10-19, 20-29,
  // 30-39 and 40-49. The highest priority range (40-49) are reserved for
  // photos which the UI is currently interacting with and require some server
  // operation. The next bucket range (30-39) corresponds to photos that have
  // the delete or unshare timestamps set. Note that a photo will only stay in
  // that priority range for as long as the delete or unshare timestamp is set
  // and that MaybeQueueNetwork() sends delete and unshare requests before most
  // anything else. The next two ranges (20-29 and 10-19) correspond to photos
  // that have a pending share request. The distinction between the two ranges
  // ensures that we'll upload all of the photos that have been shared before
  // uploading any of the share requests and thus minimize the number of share
  // requests that are sent. Lastly, the priority range 0-9 can be considered
  // the "background" priority.

  int boost = 0;
  if (m.error_ui_thumbnail() || m.error_ui_full()) {
    // Photos that the UI is waiting for get the highest precedence.
    boost = 40;
  } else if (m.has_delete_timestamp() || m.has_unshare_timestamp()) {
    // Deleted or unshared photos are in the next priority range.
    boost = 30;
  } else if (m.has_share()) {
    // A shared photo that still needs to be uploaded gets precendence over a
    // shared photo that just needs the share uploaded. This helps minimize the
    // number of share requests to the server.
    if (UploadThumbnail(m) ||
        UploadFull(m)) {
      boost = 20;
    } else {
      boost = 10;
    }
  }

  // Give thumbnails required by the ui precedence over full-screen images.
  if (m.error_ui_thumbnail() && DownloadThumbnail(m)) {
    return 7 + boost;
  }
  if (DownloadThumbnail(m) || DownloadFull(m)) {
    return 6 + boost;
  }
  // Photo upload takes precedence over metadata, but we must upload
  // metadata for a particular photo before uploading the photo data.
  if (UploadMetadata(m)) {
    return 4 + boost;
  }
  if (UploadThumbnail(m) ||
      UploadMedium(m) ||
      UploadFull(m) ||
      (wifi && UploadOriginal(m))) {
    return 5 + boost;
  }
  if (DownloadMedium(m)) {
    return 3 + boost;
  }
  if (UploadOriginal(m)) {
    return 2 + boost;
  }
  if (DownloadOriginal(m)) {
    return 1 + boost;
  }
  return boost;
}

WallTime PhotoTimestamp(const PhotoMetadata& m) {
  if (m.has_delete_timestamp()) {
    return m.delete_timestamp();
  }
  if (m.has_unshare_timestamp()) {
    return m.unshare_timestamp();
  }
  if (m.has_share()) {
    return m.share().timestamp();
  }
  return m.timestamp();
}

template <typename Proto>
bool MergeUnknownLabels(Proto* dest, const Proto& src) {
  bool dirty = false;
  for (int i = 0; i < src.unknown_labels_size(); ++i) {
    const string& label = src.unknown_labels(i);
    CHECK(label[0] == '-' || label[0] == '+');
    const string alt_label = (label[0] == '-' ? "+" : "-") + label.substr(1);
    bool found = false;
    for (int j = 0; j < dest->unknown_labels_size(); ++j) {
      if (label == dest->unknown_labels(j)) {
        found = true;
        break;
      } else if (alt_label == dest->unknown_labels(j)) {
        found = true;
        dest->set_unknown_labels(j, label);
        break;
      }
    }
    if (!found) {
      dirty = true;
      dest->add_unknown_labels(src.unknown_labels(i));
    }
  }
  return dirty;
}

#define MERGE_LABEL(name)                                       \
  if (src.has_label_##name()) {                                 \
    dirty = true;                                               \
    dest->set_label_##name(src.label_##name());                 \
  }

bool MergePhotoLabels(PhotoMetadata* dest, const PhotoMetadata& src) {
  bool dirty = false;

  MERGE_LABEL(download);
  MERGE_LABEL(error);
  MERGE_LABEL(extant);
  MERGE_LABEL(given);
  MERGE_LABEL(owned);
  MERGE_LABEL(personal);
  MERGE_LABEL(repost);
  MERGE_LABEL(reshared);
  MERGE_LABEL(shared);
  MERGE_LABEL(viewed);
  if (MergeUnknownLabels(dest, src)) {
    dirty = true;
  }

  return dirty;
}

bool MergeEpisodeLabels(EpisodeMetadata* dest, const EpisodeMetadata& src) {
  bool dirty = false;

  MERGE_LABEL(owned);
  MERGE_LABEL(shared);
  MERGE_LABEL(invited);
  MERGE_LABEL(accepted);
  MERGE_LABEL(declined);
  if (MergeUnknownLabels(dest, src)) {
    dirty = true;
  }

  return dirty;
}
#undef MERGE_LABEL

bool IsMyPhoto(const PhotoMetadata& p, int64_t user_id) {
  if (!p.has_user_id()) {
    return true;
  }
  return p.user_id() == user_id;
}

bool CanAddPhotoToEpisode(
    const PhotoMetadata& p, const EpisodeMetadata& e, int64_t user_id) {
  // A photo can only be added to an episode created by the same user.
  const int64_t photo_user_id = p.has_user_id() ? p.user_id() : user_id;
  const int64_t episode_user_id = e.has_user_id() ? e.user_id() : user_id;
  if (photo_user_id != episode_user_id) {
    // LOG("photo: unable to add photo %s to episode %s, "
    //     "different user-ids (%d != %d)",
    //     p.id(), e.id(), photo_user_id, episode_user_id);
    return false;
  }
  return true;
}

const string kStandardAssetKeyPrefix = "a/assets-library://asset/asset.JPG?id=";
const string kStandardAssetKeySuffix = "&ext=JPG";

bool HasAssetError(const PhotoMetadata& m, float max_size) {
  if (max_size <= kThumbnailSize) {
    return m.error_asset_thumbnail();
  }
  // There is no medium asset size, just thumbnail, full and original.
  if (max_size <= kFullSize) {
    return m.error_asset_full();
  }
  return m.error_asset_original();
}

void SetAssetKey(PhotoId* id, Slice asset_key) {
  if (asset_key.starts_with(kStandardAssetKeyPrefix) &&
      asset_key.ends_with(kStandardAssetKeySuffix)) {
    asset_key.remove_prefix(kStandardAssetKeyPrefix.size());
    asset_key.remove_suffix(kStandardAssetKeySuffix.size());
    asset_key.CopyToString(id->mutable_standard_asset_key());
    id->clear_asset_key();
  } else {
    asset_key.CopyToString(id->mutable_asset_key());
    id->clear_standard_asset_key();
  }
}

// TODO(pmattis): Spencer doesn't like these parameter names.
bool ResizePhoto(CGSize size, Image* image) {
  // TODO(pmattis): Don't bother resizing if the scale difference is not
  // significant.
  if (size.width >= image->width() && size.height >= image->height()) {
    return false;
  }
  int bits_per_pixel = 32;
  if (std::max(size.width, size.height) <= kThumbnailSize) {
    bits_per_pixel = 16;
    if (image->bits_per_component() == 5) {
      return false;
    }
  }
  Image new_image(image->Convert(size, bits_per_pixel));
  new_image.swap(*image);
  return true;
}

class ALAssetRepresentationDataSource : public DataSource {
 public:
  ALAssetRepresentationDataSource(ALAssetRepresentation* rep)
      : rep_(rep),
        buf_(16 * 1024, '0'),
        offset_(0) {
  }

protected:
  Slice PeekInternal() {
    if (pos_.empty()) {
      NSError* error;
      const uint32_t n = [rep_ getBytes:reinterpret_cast<uint8_t*>(&buf_[0])
                             fromOffset:offset_
                                 length:buf_.size()
                                  error:&error];
      offset_ += n;
      pos_ = Slice(buf_.data(), n);
    }
    return pos_;
  }

  void AdvanceInternal(int n) {
    const int t = std::min<int>(n, pos_.size());
    pos_.remove_prefix(t);
    if (pos_.empty()) {
      offset_ += (n - t);
    }
  }

 private:
  ALAssetRepresentation* const rep_;
  string buf_;
  Slice pos_;
  off_t offset_;
};

WallTime ExtractDateTime(ALAsset* asset) {
  // ALAssetRepresentationDataSource source([asset defaultRepresentation]);

  // __block string date_time;

  // ScanJpeg(&source, ^(ExifTag tag, ExifFormat format, const Slice& data) {
  //     switch (tag) {
  //       case kExifDateTime:
  //       case kExifDateTimeOriginal:
  //         // We take the smaller of either the DateTime tag (which is supposed
  //         // to be the modification time) and the DateTimeOriginal tag. My
  //         // iphone sometimes reports DateTimeOriginal as being 1 hour in the
  //         // future from DateTime.
  //         if (date_time.empty() || date_time > data) {
  //           data.CopyToString(&date_time);
  //         }
  //         break;
  //       default:
  //         break;
  //     }
  //   });

  // if (!date_time.empty()) {
  //   return ParseExifDate(date_time);
  // }

  // We're unable to find a date tag, use whatever the asset thinks the date
  // is.
  NSDate* date = [asset valueForProperty:ALAssetPropertyDate];
  return [date timeIntervalSince1970];
}

class PhotoManagerEnv : public PhotoManager::Env {
 public:
  PhotoManagerEnv(AppState* state)
      : state_(state) {
  }
  ~PhotoManagerEnv() {
  }

  virtual void AssetForKey(const string& key,
                           ALAssetsLibraryAssetForURLResultBlock result,
                           ALAssetsLibraryAccessFailureBlock failure) {
    [state_->assets_manager() assetForKey:key
                              resultBlock:result
                             failureBlock:failure];
  }
  virtual void TryDeleteAsset(const string& key) {
    [state_->assets_manager() tryDeleteAsset:key];
  }
  virtual void NetworkDispatch() {
    return state_->net_manager()->Dispatch();
  }
  virtual bool ReverseGeocode(
      const Location* l, void (^completion)(const Placemark*)) {
    return state_->geocode_manager()->ReverseGeocode(l, completion);
  }
  virtual CallbackSet* assets_scan_end() {
    return state_->assets_manager().scanEnd;
  }
  virtual AssetScanProgress* assets_scan_progress() {
    return state_->assets_manager().scanProgress;
  }
  virtual CallbackSet* auth_changed() {
    return state_->auth_changed();
  }
  virtual CallbackSet* network_changed() {
    return state_->net_manager()->network_changed();
  }
  virtual CallbackSet* network_ready() {
    return state_->net_manager()->network_ready();
  }
  virtual CallbackSet* settings_changed() {
    return state_->settings_changed();
  }
  virtual bool assets_scanning() {
    return state_->assets_manager().scanning;
  }
  virtual bool assets_full_scan() {
    return state_->assets_manager().fullScan;
  }
  virtual bool cloud_storage() {
    return state_->cloud_storage();
  }
  virtual const Breadcrumb* last_breadcrumb() {
    return state_->location_tracker().last_breadcrumb;
  }
  virtual bool logged_in() {
    return state_->logged_in();
  }
  virtual bool network_up() {
    return state_->net_manager()->network_up();
  }
  virtual bool network_wifi() {
    return state_->net_manager()->network_wifi();
  }
  virtual const string& photo_dir() {
    return state_->photo_dir();
  }
  virtual bool store_originals() {
    return state_->store_originals();
  }
  virtual int64_t user_id() {
    return state_->contact_manager()->user_id();
  }
  virtual DB* db() {
    return state_->db();
  }
  virtual PhotoStorage* photo_storage() {
    return state_->photo_storage();
  }
  virtual PlacemarkHistogram* placemark_histogram() {
    return state_->placemark_histogram();
  }

 private:
  AppState* const state_;
};

}  // namespace

bool HasAssetKey(const PhotoId& id) {
  return id.has_asset_key() ||
      id.has_standard_asset_key();
}

string GetAssetKey(const PhotoId& id) {
  if (id.has_standard_asset_key()) {
    return Format("%s%s%s",
                  kStandardAssetKeyPrefix,
                  id.standard_asset_key(),
                  kStandardAssetKeySuffix);
  }
  return id.asset_key();
}

bool DecodeServerId(const string& server_id,
                    uint64_t* device_id,
                    uint64_t* device_local_id) {
  if (server_id.empty()) {
    return false;
  }
  const Slice id(server_id);
  const string decoded = Base64HexDecode(id.substr(1));
  if (decoded.size() < 4) {
    return false;
  }

  // Skip the timestamp.
  Slice s(decoded);
  s.remove_prefix(4);

  uint64_t dummy;
  if (!device_id) {
    device_id = &dummy;
  }
  if (!device_local_id) {
    device_local_id = &dummy;
  }
  *device_id = Varint64Decode(&s);
  *device_local_id = Varint64Decode(&s);
  return true;
}

PhotoManager::PhotoManager(AppState* state)
    : env_(new PhotoManagerEnv(state)) {
  CommonInit();
}

PhotoManager::PhotoManager(Env* env)
    : env_(env) {
  CommonInit();
}

PhotoManager::~PhotoManager() {
  // Delete the async state first. This will block until all of the running
  // async operations have completed.
  async_.reset(NULL);
}

void PhotoManager::EnsureInit() {
  if (initialized_) {
    return;
  }
  initialized_ = true;
  LOG("photo: ensuring init");

  next_photo_id_ = env_->db()->Get<int>(kNextPhotoIdKey, 1);
  next_episode_id_ = env_->db()->Get<int>(kNextEpisodeIdKey, 1);
  LOG("photo: device-id=%d  next-photo-id=%d  next-episode-id=%d",
      device_id_, next_photo_id_, next_episode_id_);

  WallTimer timer;
  for (DB::PrefixIterator iter(env_->db(), DBFormat::photo_update_key(""));
       iter.Valid();
       iter.Next()) {
    update_photo_ids_.insert(iter.key().substr(2).ToString());
  }
  LOG("photo: scanned photo updates in %.03fs", timer.Milliseconds());

  timer.Restart();
  for (DB::PrefixIterator iter(env_->db(), DBFormat::episode_update_key(""));
       iter.Valid();
       iter.Next()) {
    update_episode_ids_.insert(key.substr(2).ToString());
  }
  LOG("photo: scanned episode updates in %.03fs", timer.Milliseconds());

  // Reset the error label on all stored photos whenever the value stored in
  // kResetErrorsKey differs from kResetErrorsValue.
  const bool reset_errors =
      (env_->db()->Get<string>(kResetErrorsKey) != kResetErrorsValue);

  timer.Restart();
  for (DB::PrefixIterator iter(env_->db(), DBFormat::photo_key());
       iter.Valid();
       iter.Next()) {
    AddPhoto(key, value, reset_errors);
  }
  LOG("photo: scanned image assets in %.03fs", timer.Milliseconds());

  if (reset_errors) {
    env_->db()->Put(kResetErrorsKey, kResetErrorsValue);
  }

  LOG("photo: loaded %d photos (%d uploads, %d downloads)",
      num_photos(), num_queued_uploads(), num_queued_downloads());
  LOG("photo: loaded %d episodes", num_episodes());
  MemoryStats();

  if (!photo_map_.empty()) {
    update_.Run();
  }
}

void PhotoManager::MemoryStats() {
  int metadata_bytes = 0;
  int id_bytes = 0;
  int asset_key_bytes = 0;
  int other_bytes = 0;
  int location_bytes = 0;
  int placemark_bytes = 0;

  for (PhotoMap::const_iterator iter(photo_map_.begin());
       iter != photo_map_.end();
       ++iter) {
    const PhotoData& p = iter->second;
    const PhotoMetadata& m = p.metadata;
    metadata_bytes += sizeof(PhotoMetadata);

    if (m.has_id()) {
      id_bytes += sizeof(PhotoId);
      if (m.id().has_server_id()) {
        id_bytes += sizeof(string) + m.id().server_id().size();
      }
      if (m.id().has_asset_key()) {
        asset_key_bytes += sizeof(string) + m.id().asset_key().size();
      }
      if (m.id().has_standard_asset_key()) {
        asset_key_bytes += sizeof(string) + m.id().standard_asset_key().size();
      }
    }
    if (m.has_parent_id()) {
      id_bytes += sizeof(PhotoId);
      if (m.parent_id().has_server_id()) {
        id_bytes += sizeof(string) + m.parent_id().server_id().size();
      }
      if (m.parent_id().has_asset_key()) {
        asset_key_bytes += sizeof(string) + m.parent_id().asset_key().size();
      }
      if (m.parent_id().has_standard_asset_key()) {
        asset_key_bytes +=
            sizeof(string) + m.parent_id().standard_asset_key().size();
      }
    }

    if (m.has_caption()) {
      other_bytes += sizeof(string) + m.caption().size();
    }
    if (m.has_link()) {
      other_bytes += sizeof(string) + m.link().size();
    }
  }

  for (LocationMap::iterator iter(locations_.begin());
       iter != locations_.end();
       ++iter) {
    location_bytes += sizeof(Location);
  }

  for (PlacemarkSet::iterator iter(placemarks_.begin());
       iter != placemarks_.end();
       ++iter) {
    const Placemark& p = *iter;
    placemark_bytes += sizeof(Placemark);
    if (p.has_iso_country_code()) {
      placemark_bytes += sizeof(string) + p.iso_country_code().size();
    }
    if (p.has_country()) {
      placemark_bytes += sizeof(string) + p.country().size();
    }
    if (p.has_state()) {
      placemark_bytes += sizeof(string) + p.state().size();
    }
    if (p.has_postal_code()) {
      placemark_bytes += sizeof(string) + p.postal_code().size();
    }
    if (p.has_locality()) {
      placemark_bytes += sizeof(string) + p.locality().size();
    }
    if (p.has_sublocality()) {
      placemark_bytes += sizeof(string) + p.sublocality().size();
    }
    if (p.has_thoroughfare()) {
      placemark_bytes += sizeof(string) + p.thoroughfare().size();
    }
    if (p.has_subthoroughfare()) {
      placemark_bytes += sizeof(string) + p.subthoroughfare().size();
    }
  }

  const float n = num_photos() ? num_photos() : 1;
  LOG("photo: %d metadata bytes, %.1f bytes/photo",
      metadata_bytes, metadata_bytes / n);
  LOG("photo: %d id bytes, %.1f bytes/photo",
      id_bytes, id_bytes / n);
  LOG("photo: %d asset-key bytes, %.1f bytes/photo",
      asset_key_bytes, asset_key_bytes / n);
  LOG("photo: %d location bytes, %.1f bytes/photo",
      location_bytes, location_bytes / n);
  LOG("photo: %d placemark bytes, %.1f bytes/photo",
      placemark_bytes, placemark_bytes / n);
  LOG("photo: %d other bytes, %.1f bytes/photo",
      other_bytes, other_bytes / n);
}

int64_t PhotoManager::NewViewfinderPhoto(
    const PhotoMetadata& m, NSData* data) {
  DB::Batch updates;
  PhotoManager::PhotoData* p = NewPhoto(m, true, &updates);

  const string filename = PhotoOriginalFilename(p->metadata.id());
  if (!env_->photo_storage()->Write(filename, data, &updates)) {
    updates.Abandon();
    return -1;
  }

  env_->db()->Put(updates);
  return p->metadata.id().local_id();
}

int64_t PhotoManager::NewAssetPhoto(
    ALAsset* asset, const string& asset_key, bool complete_on_main_thread) {
  // This is for testing only and can be used to limit the number of asset
  // photos added.
  static int32_t photo_count = 0;
  if (OSAtomicIncrement32(&photo_count) > kMaxPhotos) {
    return 0;
  }

  // Add the asset to the database.
  PhotoMetadata m;
  SetAssetKey(m.mutable_id(), asset_key);
  m.set_timestamp(ExtractDateTime(asset));
  CLLocation* location =
      [asset valueForProperty:ALAssetPropertyLocation];
  if (location) {
    m.mutable_location()->CopyFrom(MakeLocation(location));
  }
  CGImageRef thumbnail = [asset aspectRatioThumbnail];
  if (!thumbnail) {
    // Something is wrong with the asset. Don't try to add it.
    return 0;
  }

  m.set_aspect_ratio((float)CGImageGetWidth(thumbnail) /
                     (float)CGImageGetHeight(thumbnail));
  if (std::isnan(m.aspect_ratio())) {
    // Something is wrong with the asset. Don't try to add it.
    return 0;
  }

  if (complete_on_main_thread) {
    // Complete the photo creation on the main thread. This is used by
    // production code because NewAssetPhoto() is called from a background
    // thread by the assets scan.
    async_->dispatch_main(^{
        DB::Batch updates;
        if (NewPhoto(m, true, &updates)) {
          env_->db()->Put(updates);
        }
      });
    return 0;
  }

  // Complete the photo creation immediately and return the new photo id. Used
  // for testing.
  DB::Batch updates;
  PhotoData* p = NewPhoto(m, true, &updates);
  if (!p) {
    return 0;
  }
  env_->db()->Put(updates);
  return p->metadata.id().local_id();
}

void PhotoManager::SetDeviceId(int64_t device_id) {
  if (device_id_ != device_id) {
    device_id_ = device_id;
    env_->db()->Put(kDeviceIdKey, device_id);
  }
}

void PhotoManager::ProcessQueryUpdates(const QueryUpdatesResponse& r) {
  DB::Batch updates;

  if (r.has_last_key()) {
    query_updates_key_ = r.last_key();
  }
  updates.Put(kQueryUpdatesKey, query_updates_key_);

  // Note that a single query updates response may refer to the same
  // photo/episode multiple times. If the photo/episode is new, we queue the
  // photo/episode for retrieval via /get_episodes (a.k.a. get metadata) and only
  // unqueue it when get metadata completes. Photos that are queued for
  // metadata retrieval are not added to episodes (see ShouldAddPhotoToEpisode).
  for (int i = 0; i < r.episodes_size(); ++i) {
    MergeEpisodeUpdate(r.episodes(i), true, &updates);
  }
  for (int i = 0; i < r.photos_size(); ++i) {
    MergePhotoUpdate(r.photos(i), true, &updates);
  }

  env_->db()->Put(updates);
}

void PhotoManager::ProcessGetMetadata(const GetMetadataResponse& r) {
  DB::Batch updates;

  for (int i = 0; i < r.episodes_size(); ++i) {
    MergeEpisodeUpdate(r.episodes(i), false, &updates);
  }
  for (int i = 0; i < r.photos_size(); ++i) {
    MergePhotoUpdate(r.photos(i), false, &updates);
  }

  env_->db()->Put(updates);
}

void PhotoManager::CommitQueuedMetadataUpload(
    const MetadataUploadResponse& r) {
  if (!queued_metadata_upload_.get()) {
    LOG("photo: commit failed: no metadata upload queued");
    return;
  }

  ScopedPtr<PhotoManager::MetadataUpload> u(
      queued_metadata_upload_.release());
  if (r.photos_size() != u->photos.size()) {
    LOG("photo: unexpected number of photos in response: %d != %d\n%@",
        r.photos_size(), u->photos.size(), r);
    return;
  }
  if (!r.has_episode_id()) {
    LOG("photo: unable to find episode_id:\n%@", r);
    return;
  }

  DB::Batch updates;

  PhotoManager::EpisodeData* e = u->photos[0]->episode;
  if (e->metadata.id().server_id() != r.episode_id()) {
    if (e->metadata.id().has_server_id()) {
      server_episode_map_.erase(e->metadata.id().server_id());
    }
    e->metadata.mutable_id()->set_server_id(r.episode_id());
    server_episode_map_[e->metadata.id().server_id()] = e;
    OutputEpisodeMetadata(e, &updates);
    LOG("photo: episode metadata: %s (%s)", e->metadata.id(),
        e->metadata.id().server_id());
  }

  // Update the metadata for any photo that was uploaded.
  for (int i = 0; i < r.photos_size(); ++i) {
    PhotoData* p = u->photos[i];
    // Mark the server has having all of our local metadata bits.
    SetServerMetadataBits(&p->metadata, GetLocalMetadataBits(p));
    ClearUploadBits(&p->metadata, PhotoMetadata::METADATA);
    MergePhotoUpdate(p, r.photos(i), &updates, true);
    LOG("photo: photo metadata: %s (%s)", p->metadata.id(),
        p->metadata.id().server_id());
  }

  env_->db()->Put(updates);
}

void PhotoManager::CommitQueuedPhotoUpload(bool error) {
  if (!queued_photo_upload_.get()) {
    LOG("photo: commit failed: no photo upload queued");
    return;
  }

  PhotoData* p = queued_photo_upload_->photo;
  const PhotoType type = queued_photo_upload_->type;
  const string path = queued_photo_upload_->path;
  queued_photo_upload_.reset(NULL);
  bool delete_photo = false;

  switch (type) {
    case THUMBNAIL:
      thumbnail_put_urls_.erase(p->metadata.id().local_id());
      break;
    case MEDIUM:
      medium_put_urls_.erase(p->metadata.id().local_id());
      delete_photo = true;
      break;
    case FULL:
      full_put_urls_.erase(p->metadata.id().local_id());
      delete_photo = HasAssetKey(p->metadata.id());
      break;
    case ORIGINAL:
      original_put_urls_.erase(p->metadata.id().local_id());
      delete_photo = true;
      break;
  }

  if (error) {
    UploadPhotoError(p, type);
    return;
  }

  DB::Batch updates;
  if (delete_photo && !path.empty()) {
    // The photo has been uploaded to the server, no need to keep the
    // original/medium images around.
    const string filename = PhotoBasename(photo_dir_, path);
    LOG("photo: %s: deleting image %s", p->metadata.id(), filename);
    env_->photo_storage()->Delete(filename, &updates);
  }

  // Clear the upload error bit on success.
  switch (type) {
    case THUMBNAIL:
      p->metadata.clear_error_upload_thumbnail();
      break;
    case MEDIUM:
      p->metadata.clear_error_upload_medium();
      break;
    case FULL:
      p->metadata.clear_error_upload_full();
      break;
    case ORIGINAL:
      p->metadata.clear_error_upload_original();
      break;
  }

  ClearUploadBits(&p->metadata, type);
  OutputPhotoMetadata(p, &updates);
  env_->db()->Put(updates);

  MaybeQueuePhoto(p);
}

void PhotoManager::CommitQueuedPhotoDownload(
    int64_t photo_id, const string& md5, bool retry) {
  if (!queued_photo_download_.get()) {
    LOG("photo: commit failed: no photo download queued");
    return;
  }

  PhotoData* p = FindPtrOrNull(&photo_map_, photo_id);
  if (!p) {
    LOG("photo: %s is not a valid photo id", photo_id);
    return;
  }

  const PhotoType type = queued_photo_download_->type;
  const string path = queued_photo_download_->path;
  queued_photo_download_.reset(NULL);
  string filename;

  switch (type) {
    case THUMBNAIL:
      thumbnail_get_urls_.erase(photo_id);
      filename = PhotoThumbnailFilename(p->metadata.id());
      break;
    case MEDIUM:
      medium_get_urls_.erase(photo_id);
      filename = PhotoMediumFilename(p->metadata.id());
      break;
    case FULL:
      full_get_urls_.erase(photo_id);
      filename = PhotoFullFilename(p->metadata.id());
      break;
    case ORIGINAL:
      original_get_urls_.erase(photo_id);
      filename = PhotoOriginalFilename(p->metadata.id());
      break;
  }

  const bool error = md5.empty() && !retry;
  if (!error) {
    DB::Batch updates;

    if (env_->photo_storage()->AddExisting(path, filename, md5, &updates)) {
      ClearDownloadBits(&p->metadata, type);

      // Clear the download error bit on success.
      switch (type) {
        case THUMBNAIL:
          p->metadata.clear_error_download_thumbnail();
          p->metadata.clear_error_ui_thumbnail();
          break;
        case MEDIUM:
          p->metadata.clear_error_download_medium();
          break;
        case FULL:
          p->metadata.clear_error_download_full();
          p->metadata.clear_error_ui_full();
          break;
        case ORIGINAL:
          p->metadata.clear_error_download_original();
          break;
      }

      if (!p->episode) {
        AddPhotoToEpisode(p, &updates);
      }

      OutputPhotoMetadata(p, &updates);
      env_->db()->Put(updates);
    } else {
      retry = true;
    }
  }

  if (!retry) {
    // Run any download callbacks (on both success and error) after the
    // downloaded photo has been written.
    NotifyDownload(photo_id, type);
  }

  if (error) {
    // A persistent error (e.g. photo does not exist). Stop trying to download
    // the photo.
    DownloadPhotoError(p, type);
  } else {
    MaybeQueuePhoto(p);
  }
}

void PhotoManager::CommitQueuedShareUpload() {
  if (!queued_share_upload_.get()) {
    LOG("photo: commit failed: no share upload queued");
    return;
  }

  DB::Batch updates;
  ScopedPtr<ShareUpload> u(queued_share_upload_.release());

  for (int i = 0; i < u->photos.size(); ++i) {
    PhotoData* p = u->photos[i];

    // Remove any contacts that were shared.
    PhotoShare* share = p->metadata.mutable_share();

    typedef std::tr1::unordered_map<string, const ContactMetadata*> ContactSet;
    ContactSet unique_contacts;

    google::protobuf::RepeatedPtrField<ContactMetadata> existing_contacts;
    existing_contacts.Swap(share->mutable_contacts());

    for (int j = 0; j < existing_contacts.size(); ++j) {
      const ContactMetadata& c = existing_contacts.Get(j);
      unique_contacts[c.identity()] = &c;
    }
    for (int j = 0; j < u->contacts.size(); ++j) {
      const ContactMetadata& c = u->contacts[j];
      unique_contacts.erase(c.identity());
    }

    for (ContactSet::iterator iter(unique_contacts.begin());
         iter != unique_contacts.end();
         ++iter) {
      share->add_contacts()->CopyFrom(*iter->second);
    }

    if (share->contacts_size() == 0) {
      p->metadata.clear_share();
    }

    OutputPhotoMetadata(p, &updates);
    MaybeQueuePhoto(p);
  }

  env_->db()->Put(updates);
}

void PhotoManager::CommitQueuedUnshareUpload() {
  if (!queued_unshare_upload_.get()) {
    LOG("photo: commit failed: no unshare upload queued");
    return;
  }

  DB::Batch updates;
  ScopedPtr<UnshareUpload> u(queued_unshare_upload_.release());

  for (int i = 0; i < u->photos.size(); ++i) {
    PhotoData* p = u->photos[i];
    LOG("photo: commit unshare: %s", p->metadata.id());
    p->metadata.clear_unshare_timestamp();
    OutputPhotoMetadata(p, &updates);
    MaybeQueuePhoto(p);
  }

  env_->db()->Put(updates);
}

void PhotoManager::CommitQueuedDeleteUpload() {
  if (!queued_delete_upload_.get()) {
    LOG("photo: commit failed: no delete upload queued");
    return;
  }

  DB::Batch updates;
  ScopedPtr<DeleteUpload> u(queued_delete_upload_.release());

  for (int i = 0; i < u->photos.size(); ++i) {
    CommitDeletePhoto(u->photos[i], &updates);
  }

  env_->db()->Put(updates);
}

void PhotoManager::SharePhotos(
    const vector<int64_t>& photo_ids,
    const vector<ContactMetadata>& contacts) {
  const WallTime now = WallTime_Now();
  DB::Batch updates;

  for (int i = 0; i < photo_ids.size(); ++i) {
    PhotoData* p = FindPtrOrNull(&photo_map_, photo_ids[i]);
    if (!p) {
      LOG("photo: %s is not a valid photo id", photo_ids[i]);
      continue;
    }

    PhotoShare* share = p->metadata.mutable_share();
    share->set_timestamp(now);

    // Merge the existing contacts with the new contacts.
    typedef std::tr1::unordered_map<string, const ContactMetadata*> ContactSet;
    ContactSet unique_contacts;

    google::protobuf::RepeatedPtrField<ContactMetadata> existing_contacts;
    existing_contacts.Swap(share->mutable_contacts());

    for (int i = 0; i < existing_contacts.size(); ++i) {
      const ContactMetadata& c = existing_contacts.Get(i);
      unique_contacts[c.identity()] = &c;
    }
    for (int i = 0; i < contacts.size(); ++i) {
      const ContactMetadata& c = contacts[i];
      unique_contacts[c.identity()] = &c;
    }
    for (ContactSet::iterator iter(unique_contacts.begin());
         iter != unique_contacts.end();
         ++iter) {
      share->add_contacts()->CopyFrom(*iter->second);
    }

    OutputPhotoMetadata(p, &updates);
    MaybeQueuePhoto(p);
  }

  env_->db()->Put(updates);
  env_->NetworkDispatch();
}

void PhotoManager::UnsharePhotos(const vector<int64_t>& photo_ids) {
  DB::Batch updates;

  for (int i = 0; i < photo_ids.size(); ++i) {
    PhotoData* p = FindPtrOrNull(&photo_map_, photo_ids[i]);
    if (!p) {
      LOG("photo: %s is not a valid photo id", photo_ids[i]);
      continue;
    }

    p->metadata.clear_share();
    p->metadata.set_unshare_timestamp(WallTime_Now());

    OutputPhotoMetadata(p, &updates);
    MaybeQueuePhoto(p);
  }

  env_->db()->Put(updates);
  env_->NetworkDispatch();
}

void PhotoManager::DeletePhotos(const vector<int64_t>& photo_ids) {
  DB::Batch updates;
  for (int i = 0; i < photo_ids.size(); ++i) {
    DeletePhoto(photo_ids[i], &updates);
  }
  if (updates.count() > 0) {
    env_->db()->Put(updates);
    env_->NetworkDispatch();
    update_.Run();
  }
}

void PhotoManager::DeletePhoto(int64_t photo_id, DB::Batch* updates) {
  PhotoData* p = FindPtrOrNull(&photo_map_, photo_id);
  if (!p) {
    LOG("photo: %s is not a valid photo id", photo_id);
    return;
  }
  LOG("photo: deleting %s", p->metadata.id());

  // Remove the photo from its episode. This causes it to disappear in the UI.
  RemovePhotoFromEpisode(p, updates);

  // Delete the photo from various queued uploads.
  UnqueuePhoto(p);

  if (p->metadata.id().has_server_id()) {
    server_photo_map_.erase(p->metadata.id().server_id());
    update_photo_ids_.erase(p->metadata.id().server_id());
  }

  // Mark the photo as deleted in the database. This will prevent the photo
  // from reappearing the next time the app starts.
  p->metadata.clear_share();
  p->metadata.clear_unshare_timestamp();
  p->metadata.set_delete_timestamp(WallTime_Now());

  OutputPhotoMetadata(p, updates);

  if (HasAssetKey(p->metadata.id())) {
    // Try to delete the associated asset. This will only succeed if viewfinder
    // created the asset.
    env_->TryDeleteAsset(GetAssetKey(p->metadata.id()));
  }

  if (!p->metadata.id().has_server_id() || ShouldDelete(p)) {
    // The photo hasn't been uploaded to the server yet or the server was the
    // source of the deletion, commit the delete immediately.
    CommitDeletePhoto(p, updates);
  } else {
    // Queue the photo for deletion.
    MaybeQueuePhoto(p);
  }

  // Delete any images associated with the photo in the background.
  async_->dispatch_low_priority(^{
      // Note that "p" could be deleted before we reach this code, so be
      // careful not to use it.
      env_->photo_storage()->DeleteAll(photo_id);
    });
}

void PhotoManager::LoadLocalThumbnail(
    int64_t photo_id, Image* image, void (^done)()) {
  last_load_time_ = WallTime_Now();

  // For thumbnails we don't adjust for the screen scale as speed is the
  // important issue and we want to be sure to grab the lowest resolution image
  // available.
  const float scale = [UIScreen mainScreen].scale;
  const CGSize size = CGSizeMake(kThumbnailSize, kThumbnailSize);
  PhotoData* const p = FindPtrOrNull(&photo_map_, photo_id);
  if (!p) {
    LOG("photo: %s is not a valid photo id", photo_id);
  } else if (MaybeLoadInternal(p, size, false, NULL, image, ^{
        // Set the image scale to the ui screen scale. On a retina display,
        // this will effectively halve the Image::{width,height}() which will
        // cause a higher-res photo to be loaded.
        if (*image) {
          image->set_scale(scale);
        }
        done();
      })) {
    return;
  }
  async_->dispatch_low_priority(done);
}

void PhotoManager::LoadLocalPhoto(
    int64_t photo_id, CGSize size,
    Image* image, void (^done)()) {
  last_load_time_ = WallTime_Now();

  const float scale = [UIScreen mainScreen].scale;
  size.width *= scale;
  size.height *= scale;
  PhotoData* const p = FindPtrOrNull(&photo_map_, photo_id);
  if (!p) {
    LOG("photo: %s is not a valid photo id", photo_id);
  } else {
    size = AspectFill(size, p->metadata.aspect_ratio()).size;
    if (MaybeLoadInternal(p, size, false, NULL, image, ^{
          // Set the image scale to the ui screen scale.
          if (*image) {
            image->set_scale(scale);
          }
          done();
        })) {
      return;
    }
  }
  async_->dispatch_low_priority(done);
}

void PhotoManager::LoadNetworkThumbnail(
    int64_t photo_id, Image* image, void (^done)()) {
  last_load_time_ = WallTime_Now();

  PhotoData* const p = FindPtrOrNull(&photo_map_, photo_id);
  if (!p) {
    LOG("photo: %s is not a valid photo id", photo_id);
    async_->dispatch_low_priority(done);
    return;
  }

  if (p->metadata.label_error() ||
      !p->metadata.id().has_server_id() ||
      !env_->network_up() ||
      !env_->logged_in() ||
      !DownloadThumbnail(p->metadata)) {
    // Network loading cannot proceed. Just try to load the local thumbnail.
    LoadLocalThumbnail(photo_id, image, done);
    return;
  }

  // Wait for the download to complete. The callback will also be invoked if
  // the photo is deleted or quarantined.
  WaitForDownload(photo_id, THUMBNAIL, ^{
      // The photo was written locally (or an error occurred). Just try to load
      // the local photo and let it take care of the error processing.
      // LOG("photo: %s network thumbnail loaded", photo_id);
      LoadLocalThumbnail(photo_id, image, done);
    });
}

void PhotoManager::LoadNetworkPhoto(
    int64_t photo_id, CGSize size,
    Image* image, void (^done)()) {
  last_load_time_ = WallTime_Now();

  PhotoData* const p = FindPtrOrNull(&photo_map_, photo_id);
  if (!p) {
    LOG("photo: %s is not a valid photo id", photo_id);
    async_->dispatch_low_priority(done);
    return;
  }

  if (p->metadata.label_error() ||
      !p->metadata.id().has_server_id() ||
      !env_->network_up() ||
      !env_->logged_in()) {
    // Network loading cannot proceed. Just try to load the local photo.
    // LOG("photo: %s unable to load network photo", photo_id);
    LoadLocalPhoto(photo_id, size, image, done);
    return;
  }

  size = AspectFill(size, p->metadata.aspect_ratio()).size;
  const float scale = [UIScreen mainScreen].scale;
  const float max_size = std::max(size.width, size.height) * scale;
  PhotoType download_type = static_cast<PhotoType>(0);
  bool download_queued = false;
  if (max_size <= kThumbnailSize) {
    download_type = THUMBNAIL;
    download_queued = DownloadThumbnail(p->metadata);
  } else if (max_size <= kFullSize) {
    download_type = FULL;
    download_queued = DownloadFull(p->metadata);
  }
  if (!download_queued) {
    // The photo is not queued for download and has either already been
    // downloaded or is not on the server. Just try to load the local photo.
    // LOG("photo: %s network photo already loaded", photo_id);
    LoadLocalPhoto(photo_id, size, image, done);
    return;
  }

  // Wait for the download to complete. The callback will also be invoked if
  // the photo is deleted or quarantined.
  WaitForDownload(photo_id, download_type, ^{
      // The photo was written locally (or an error occurred). Just try to load
      // the local photo and let it take care of the error processing.
      // LOG("photo: %s network photo loaded", photo_id);
      LoadLocalPhoto(photo_id, size, image, done);
    });
}

void PhotoManager::CommonInit() {
  async_.reset(new AsyncState);
  photo_dir_ = env_->photo_dir();
  photo_tmp_dir_ = JoinPath(photo_dir_, "tmp");
  initialized_ = false;
  device_id_ = env_->db()->Get<int>(kDeviceIdKey, 0);
  query_updates_key_ = env_->db()->Get<string>(kQueryUpdatesKey);
  last_load_time_ = 0;
  queue_in_progress_ = false;
  queue_start_time_ = 0;
  detect_in_progress_ = NULL;
  face_detector_ = NULL;

  // Remove the photo tmp directory and all of its contents and recreate it.
  DirRemove(photo_tmp_dir_, true);
  DirCreate(photo_tmp_dir_);

  env_->assets_scan_progress()->Add(
      ^(ALAsset* asset, const string& asset_key, int progress) {
          if (!asset) {
            // Asset has already been added to the database.
            return;
          }
          NewAssetPhoto(asset, asset_key, true);
    });

  // Watch for the end of each asset scan and add new assets and check that
  // photos for existing assets still exist.
  env_->assets_scan_end()->Add(^{
      async_->dispatch_main(^{
          // TODO(pmattis): Only perform this check after EnsureInit() has been
          // called instead of forcing a call to EnsureInit().
          EnsureInit();
          if (env_->assets_full_scan()) {
            GarbageCollectAssets();
          }
          env_->NetworkDispatch();
        });
    });

  env_->auth_changed()->Add(^{
      ReprioritizePhotoQueue();
      env_->NetworkDispatch();
    });
  env_->network_changed()->Add(^{
      ReprioritizePhotoQueue();
    });
  env_->network_ready()->Add(^{
      MaybeQueueNetwork();
    });
  env_->settings_changed()->Add(^{
      ReprioritizePhotoQueue();
      env_->NetworkDispatch();
    });
}

void PhotoManager::GarbageCollectAssets() {
  vector<int64_t> deletions;
  for (PhotoMap::iterator iter(photo_map_.begin());
       iter != photo_map_.end();
       ++iter) {
    PhotoData* p = &iter->second;
    if (p->metadata.has_delete_timestamp()) {
      // Photo has already been marked as deleted, no need to check
      // again.
      continue;
    }
    if (p->metadata.id().has_server_id()) {
      // The photo has been uploaded to the server, don't attempt to delete it.
      continue;
    }
    if (!HasAssetKey(p->metadata.id())) {
      // The photo doesn't exist in the assets library, only in the viewfinder
      // photo area.
      continue;
    }
    if (env_->db()->Exists(GetAssetKey(p->metadata.id()))) {
      // The photo still exists in the assets library, leave it be.
      continue;
    }
    // The photo no longer exists in the assets library, delete it. We can't
    // call DeletePhoto() here as doing so might modify photo_map_ which we're
    // iterating over.
    deletions.push_back(p->metadata.id().local_id());
  }

  if (deletions.empty()) {
    return;
  }
  DB::Batch updates;
  for (int i = 0; i < deletions.size(); ++i) {
    DeletePhoto(deletions[i], &updates);
  }
  if (updates.count() > 0) {
    env_->db()->Put(updates);
    update_.Run();
  }
}

bool PhotoManager::NeedsReverseGeocode(int64_t photo_id) {
  PhotoData* p = FindPtrOrNull(&photo_map_, photo_id);
  if (!p || !p->location) {
    return false;
  }
  if (!p->placemark) {
    InternPhotoLocation(p);
  }
  return !p->placemark;
}

bool PhotoManager::ReverseGeocode(
    int64_t photo_id, void (^completion)(bool success)) {
  PhotoData* p = FindPtrOrNull(&photo_map_, photo_id);
  if (!p) {
    LOG("photo: %s is not a valid photo id", photo_id);
    return false;
  }
  if (!p->location || p->placemark) {
    return false;
  }
  InternPhotoLocation(p);
  if (p->placemark) {
    // Optimized the reverse geocode out of existence by reusing the placemark
    // for a previously reverse geocoded photo at the same location.
    return false;
  }

  // Look up the callback set for this location.
  const Location* l = p->location;
  GeocodeCallbackSet* callbacks = geocode_callback_map_[l];
  const bool do_reverse_geocode = !callbacks;
  if (!callbacks) {
    callbacks = new GeocodeCallbackSet;
    geocode_callback_map_[l] = callbacks;
  }
  // Add the completion to the callback set.
  callbacks->Add(completion);

  if (do_reverse_geocode) {
    // Only run reverse geocoding for the first caller interested in reverse
    // geocoding this location.
    CHECK(env_->ReverseGeocode(
              l, ^(const Placemark* m) {
                if (m) {
                  p->metadata.mutable_placemark()->CopyFrom(*m);
                  InternPhotoLocation(p);
                  DB::Batch updates;
                  OutputPhotoMetadata(p, &updates);
                  env_->db()->Put(updates);
                }
                callbacks->Run(p->placemark != NULL);
                geocode_callback_map_.erase(l);
                geocode_.Run();
                delete callbacks;
              }));
  } else {
    CHECK_GT(callbacks->size(), 1);
  }
  return true;
}

bool PhotoManager::FormatLocation(
    int64_t photo_id, bool short_location, string* s) {
  PhotoData* t = FindPtrOrNull(&photo_map_, photo_id);
  if (!t) {
    return false;
  }
  if (!t->placemark) {
    return false;
  }
  if (!s) {
    return true;
  }

  // Find the closest top placemark and format the specified photo's
  // placemark relative to it. If there is no top placemark, use
  // the current breadcrumb's placemark.
  const Placemark* ref_pm;
  double distance;
  PlacemarkHistogram::TopPlacemark top;
  if (env_->placemark_histogram()->DistanceToTopPlacemark(
          *t->location, &distance, &top)) {
    ref_pm = &top.placemark;
  } else {
    ref_pm = &env_->last_breadcrumb()->placemark();
  }

  const Placemark& m = *t->placemark;
  *s = FormatPlacemarkWithCurrentLocation(m, ref_pm, short_location);
  return true;
}

bool PhotoManager::DistanceToLocation(int64_t photo_id, double* distance) {
  PhotoData* t = FindPtrOrNull(&photo_map_, photo_id);
  if (!t) {
    return false;
  }
  if (!t->location) {
    return false;
  }
  // Find the closest top placemark and format the specified photo's
  // placemark relative to it.
  if (!env_->placemark_histogram()->DistanceToTopPlacemark(
          *t->location, distance, NULL)) {
    const Breadcrumb* bc = env_->last_breadcrumb();
    if (!bc) {
      return false;
    }
    *distance = DistanceBetweenLocations(bc->location(), *t->location);
  }
  return true;
}

const Placemark* PhotoManager::GetPlacemark(int64_t photo_id) {
  PhotoData* p = FindPtrOrNull(&photo_map_, photo_id);
  if (!p) {
    return NULL;
  }
  return p->placemark;
}

WallTime PhotoManager::GetTimestamp(int64_t photo_id) {
  PhotoData* p = FindPtrOrNull(&photo_map_, photo_id);
  if (!p) {
    return 0;
  }
  return p->metadata.timestamp();
}

PhotoManager::PhotoData* PhotoManager::NewPhoto(
    const PhotoMetadata& m, bool owned, DB::Batch* updates) {
  // Ensure initialization has finished.
  EnsureInit();

  PhotoId photo_id(m.id());
  photo_id.set_local_id(next_photo_id_++);
  updates->Put(kNextPhotoIdKey, next_photo_id_);

  PhotoData* p = &photo_map_[photo_id.local_id()];
  p->metadata.CopyFrom(m);
  p->metadata.mutable_id()->CopyFrom(photo_id);
  if (owned) {
    p->metadata.set_label_owned(true);
  }

  AddPhoto(p, updates);

  if (HasAssetKey(p->metadata.id())) {
    updates->Put(GetAssetKey(p->metadata.id()), p->metadata.id().local_id());
  }

  update_.Run();
  return p;
}

PhotoManager::EpisodeData* PhotoManager::NewEpisode(DB::Batch* updates) {
  EpisodeId id;
  id.set_local_id(next_episode_id_++);
  updates->Put(kNextEpisodeIdKey, next_episode_id_);

  EpisodeData* e = &episode_map_[id.local_id()];
  e->metadata.mutable_id()->CopyFrom(id);
  return e;
}

void PhotoManager::CommitDeletePhoto(PhotoData* p, DB::Batch* updates) {
  LOG("photo: commit delete: %s", p->metadata.id());
  queued_photos_.erase(p);
  queued_uploads_.erase(p);
  queued_downloads_.erase(p);
  queued_shares_.erase(p);
  updates->Delete(DBFormat::photo_key(p->metadata.id().local_id()));
  photo_map_.erase(p->metadata.id().local_id());
}

void PhotoManager::DeleteEmptyEpisode(EpisodeData* e, DB::Batch* updates) {
  CHECK_EQ(e->photos.size(), 0);

  if (e->metadata.id().has_server_id()) {
    if (ContainsKey(update_episode_ids_, e->metadata.id().server_id())) {
      LOG("photo: not deleting episode queued for updating: %s",
          e->metadata.id());
      return;
    }
  }

  LOG("photo: deleting empty episode %s", e->metadata.id());
  updates->Delete(DBFormat::episode_key(e->metadata.id().local_id()));
  if (e->metadata.id().has_server_id()) {
    server_episode_map_.erase(e->metadata.id().server_id());
    update_episode_ids_.erase(e->metadata.id().server_id());
  }
  episode_map_.erase(e->metadata.id().local_id());
}

bool PhotoManager::LoadEpisode(EpisodeData* e, const EpisodeId& id) {
  if (!env_->db()->GetProto(
          DBFormat::episode_key(id.local_id()), &e->metadata)) {
    LOG("photo: unable to load EpisodeMetadata: %s", id);
    return false;
  }
  if (e->metadata.id().has_server_id()) {
    server_episode_map_[e->metadata.id().server_id()] = e;
  }
  InternEpisodeLocation(e);
  return true;
}

void PhotoManager::AddPhoto(PhotoData* p, DB::Batch* updates) {
  InternPhotoLocation(p);

  AddPhotoToEpisode(p, updates);

  if (p->metadata.id().has_server_id()) {
    server_photo_map_[p->metadata.id().server_id()] = p;
  } else {
    // Queue the photo if we don't have an associated server id for it.
    SetUploadBits(&p->metadata, PhotoMetadata::METADATA);
    SetUploadBits(&p->metadata, PhotoMetadata::THUMBNAIL);
    SetUploadBits(&p->metadata, PhotoMetadata::MEDIUM);
    SetUploadBits(&p->metadata, PhotoMetadata::FULL);
    SetUploadBits(&p->metadata, PhotoMetadata::ORIGINAL);
  }

  MaybeQueuePhoto(p);
  env_->NetworkDispatch();
}

void PhotoManager::AddPhoto(
    const Slice& key, const Slice& value, bool reset_errors) {
  const int64_t local_id = FromString<int64_t>(key.substr(2));
  if (ContainsKey(photo_map_, local_id)) {
    // Photo has already been added.
    return;
  }
  PhotoData* p = &photo_map_[local_id];
  if (!p->metadata.ParseFromArray(value.data(), value.size())) {
    LOG("photo: unable to parse PhotoMetadata: %s", key);
    photo_map_.erase(local_id);
    return;
  }

  bool dirty = false;
  if (reset_errors && p->metadata.label_error()) {
    LOG("photo: %s: clearing error label", p->metadata.id());
    p->metadata.clear_label_error();
    if (p->metadata.id().has_server_id()) {
      update_photo_ids_.insert(p->metadata.id().server_id());
    }
    dirty = true;
  }

  p->metadata.clear_error_asset_thumbnail();
  p->metadata.clear_error_asset_full();
  p->metadata.clear_error_asset_original();

  DB::Batch updates;

  if (!IsMyPhoto(p->metadata, env_->user_id()) && p->metadata.upload()) {
    // Clear any upload bits if this is not my photo. These bits should only be
    // set for photos the user created, but were set mistakenly in older
    // clients.
    p->metadata.clear_upload();
    dirty = true;
  }

  AddPhoto(p, &updates);

  if (ShouldDelete(p)) {
    DeletePhoto(p->metadata.id().local_id(), &updates);
    dirty = false;
  } else {
    // Process potential unknown labels which have become known through
    // an application upgrade.
    if (ParsePhotoLabels(&p->metadata, "")) {
      dirty = true;
    }
  }

  if (dirty) {
    OutputPhotoMetadata(p, &updates);
  }

  if (updates.count() > 0) {
    env_->db()->Put(updates);
  }
}

void PhotoManager::AddPhotoToEpisode(PhotoData* p, DB::Batch* updates) {
  if (p->episode) {
    // Photo has already been added to an episode. Remove it from the episode first
    // if you want to change episodes.
    return;
  }

  if (!ShouldAddPhotoToEpisode(p)) {
    return;
  }

  if (p->metadata.episode_id().has_local_id()) {
    // Photo is already part of an episode.
    const EpisodeId& episode_id = p->metadata.episode_id();
    if (episode_id.local_id() > 0) {
      EpisodeData* e = &episode_map_[episode_id.local_id()];
      if (!e->photos.empty() || LoadEpisode(e, episode_id)) {
        AddPhotoToExistingEpisode(p, e, updates);
        if (p->episode) {
          return;
        }
      }
    }
    if (p->metadata.id().has_server_id()) {
      // We weren't able to add the photo to the episode listed in its metadata
      // but the photo has a valid server id. Queue the photo metadata for
      // retrieval.
      LOG("photo: %d unable to add photo to episode (retrieving metadata)",
          p->metadata.id());
      update_photo_ids_.insert(p->metadata.id().server_id());
      return;
    } else if (!IsMyPhoto(p->metadata, env_->user_id())) {
      // We weren't able to add the photo to the episode listed in its metadata
      // and the photo is not ours. This shouldn't possibly happen as the photo
      // should have a server_id if it isn't ours.
      LOG("photo: %d unable to add photo to episode (quarantining)",
          p->metadata.id());
      QuarantinePhoto(p);
      return;
    }
  }

  EpisodeData* e = MatchPhotoToEpisode(p);
  bool dirty_episode = false;
  if (!e) {
    e = NewEpisode(updates);
    dirty_episode = true;
  }
  AddPhotoToExistingEpisode(p, e, updates);

  p->metadata.mutable_episode_id()->CopyFrom(e->metadata.id());

  // Update the episode's date.
  if (!e->metadata.has_timestamp() ||
      e->metadata.timestamp() > p->metadata.timestamp()) {
    e->metadata.set_timestamp(p->metadata.timestamp());
    dirty_episode = true;
  }

  OutputPhotoMetadata(p, updates);
  if (dirty_episode) {
    OutputEpisodeMetadata(e, updates);
  }
}

void PhotoManager::AddPhotoToExistingEpisode(
    PhotoData* p, EpisodeData* e, DB::Batch* updates) {
  if (p->episode) {
    // Photo has already been added to an episode. Remove it from the episode first
    // if you want to change episodes.
    return;
  }
  if (!ShouldAddPhotoToEpisode(p)) {
    return;
  }
  if (!CanAddPhotoToEpisode(p->metadata, e->metadata, env_->user_id())) {
    return;
  }

  p->episode = e;
  e->photos.push_back(p);
  std::sort(e->photos.begin(), e->photos.end(), PhotoByTimestamp());

  if (!e->metadata.has_timestamp() ||
      e->metadata.timestamp() > p->metadata.timestamp()) {
    e->metadata.set_timestamp(p->metadata.timestamp());
    OutputEpisodeMetadata(e, updates);
  }
}

bool PhotoManager::ShouldAddPhotoToEpisode(PhotoData* p) const {
  if (p->metadata.has_delete_timestamp() ||
      p->metadata.label_error() ||
      !p->metadata.has_aspect_ratio() ||
      std::isnan(p->metadata.aspect_ratio()) ||
      !p->metadata.has_timestamp() ||
      ContainsKey(update_photo_ids_, p->metadata.id().server_id())) {
    // We don't have enough photo metadata to match the photo to an
    // episode. Note that we'll add a photo to an episode before we've
    // downloaded any of the photo images and rely on the prioritization of
    // images needed for the UI.
    return false;
  }
  return true;
}

bool PhotoManager::ShouldDelete(PhotoData* p) const {
  if (p->metadata.id().has_server_id() &&
      ContainsKey(update_photo_ids_, p->metadata.id().server_id())) {
    return false;
  }
  if (p->metadata.label_owned() ||
      p->metadata.label_given() ||
      p->metadata.label_shared()) {
    return false;
  }
  return true;
}

void PhotoManager::InternPhotoLocation(PhotoData* p) {
  // Replace PhotoMetadata::location and PhotoMetadata::placemark with pointers
  // to interned Location and Placemark objects. That is, all identical
  // locations and placemarks are represented by a single canonical object.

  LocationMap::iterator iter;
  if (p->metadata.has_location()) {
    iter = locations_.insert(
        std::make_pair(p->metadata.location(), (const Placemark*)NULL)).first;
  } else if (p->location) {
    iter = locations_.insert(
        std::make_pair(*p->location, (const Placemark*)NULL)).first;
  } else {
    p->placemark = NULL;
    return;
  }
  p->location = &iter->first;

  // Clear the placemark if it isn't valid.
  if (p->metadata.has_placemark() &&
      !p->metadata.placemark().has_iso_country_code()) {
    p->metadata.clear_placemark();
  }

  if (!iter->second && p->metadata.has_placemark()) {
    iter->second = &(*placemarks_.insert(p->metadata.placemark()).first);
  }
  p->placemark = iter->second;

  p->metadata.clear_location();
  p->metadata.clear_placemark();

  // TODO(pmattis): Garbage collect unreferenced locations/placemarks. Loop
  // over all of the photos and find references to locations/placemarks. Loop
  // over the locations/placemarks and delete the unreferenced objects.
}

void PhotoManager::InternEpisodeLocation(EpisodeData* e) {
  // Replace EpisodeMetadata::location and EpisodeMetadata::placemark with pointers
  // to interned Location and Placemark objects. That is, all identical
  // locations and placemarks are represented by a single canonical object.

  LocationMap::iterator iter;
  if (e->metadata.has_location()) {
    iter = locations_.insert(
        std::make_pair(e->metadata.location(), (const Placemark*)NULL)).first;
  } else if (e->location) {
    iter = locations_.insert(
        std::make_pair(*e->location, (const Placemark*)NULL)).first;
  } else {
    e->placemark = NULL;
    return;
  }

  e->location = &iter->first;
  if (!iter->second && e->metadata.has_placemark()) {
    iter->second = &(*placemarks_.insert(e->metadata.placemark()).first);
  }
  e->placemark = iter->second;

  e->metadata.clear_location();
  e->metadata.clear_placemark();
}

void PhotoManager::RemovePhotoFromEpisode(PhotoData* p, DB::Batch* updates) {
  EpisodeData* e = p->episode;
  if (!e) {
    return;
  }
  for (PhotoVec::iterator iter(e->photos.begin());
       iter != e->photos.end();
       ++iter) {
    if (*iter == p) {
      e->photos.erase(iter);
      if (e->photos.empty()) {
        DeleteEmptyEpisode(e, updates);
      }
      break;
    }
  }
  p->episode = NULL;
}

PhotoManager::EpisodeData* PhotoManager::MatchPhotoToEpisode(PhotoData* p) {
  vector<EpisodeData*> candidates;

  for (EpisodeMap::iterator iter(episode_map_.begin());
       iter != episode_map_.end();
       ++iter) {
    EpisodeData* e = &iter->second;
    if (!CanAddPhotoToEpisode(p->metadata, e->metadata, env_->user_id())) {
      continue;
    }
    if (e->metadata.has_timestamp() && p->metadata.has_timestamp()) {
      WallTime time_dist = fabs(p->metadata.timestamp() - e->metadata.timestamp());
      if (time_dist < 2 * kMaxTimeDist) {
        candidates.push_back(e);
      }
    }
  }

  for (int i = 0; i < candidates.size(); ++i) {
    EpisodeData* e = candidates[i];
    for (int j = 0; j < e->photos.size(); ++j) {
      const PhotoData* q = e->photos[j];
      if (p->metadata.has_timestamp() && q->metadata.has_timestamp()) {
        const double time_dist =
            fabs(p->metadata.timestamp() - q->metadata.timestamp());
        if (time_dist >= kMaxTimeDist) {
          continue;
        }
      }
      if (p->location && q->location) {
        const double loc_dist = DistanceBetweenLocations(
            *p->location, *q->location);
        if (loc_dist >= kMaxLocDist) {
          continue;
        }
      }
      return e;
    }
  }
  return NULL;
}

void PhotoManager::QuarantinePhoto(PhotoData* p) {
  LOG("photo: quarantining %s", p->metadata.id());

  DB::Batch updates;

  // Remove the photo from its episode. This causes it to disappear in the UI.
  RemovePhotoFromEpisode(p, &updates);

  // Delete the photo from the various queued uploads.
  UnqueuePhoto(p);

  // Mark the photo as quarantined in the database. This will prevent the photo
  // from reappearing the next time the app starts.
  p->metadata.set_label_error(true);

  OutputPhotoMetadata(p, &updates);

  env_->db()->Put(updates);
}

void PhotoManager::LoadViewfinderPhotoError(
    PhotoData* p, const string& filename, void (^done)(bool error)) {
  // Just remove the file and database entry associated with the error.
  DB::Batch updates;
  env_->photo_storage()->Delete(filename, &updates);
  env_->db()->Put(updates);
  done(true);
}

void PhotoManager::LoadAssetPhotoError(
    PhotoData* p, int types, void (^done)(bool error)) {
  // LoadAssetPhotoError() can be called on any thread. Bump to the main
  // thread.
  async_->dispatch_main(^{
      if (types & THUMBNAIL) {
        p->metadata.set_error_asset_thumbnail(true);
      }
      if (types & FULL) {
        p->metadata.set_error_asset_full(true);
      }
      if (types & ORIGINAL) {
        p->metadata.set_error_asset_original(true);
      }

      DB::Batch updates;
      OutputPhotoMetadata(p, &updates);
      env_->db()->Put(updates);

      done(true);
    });
}

void PhotoManager::UploadPhotoError(PhotoData* p, int types) {
  if (types & THUMBNAIL) {
    if (p->metadata.error_upload_thumbnail()) {
      // We had previously tried to upload this photo and encountered an
      // error. Quarantine the photo.
      QuarantinePhoto(p);
      return;
    }
    p->metadata.set_error_upload_thumbnail(true);
  }
  if (types & MEDIUM) {
    if (p->metadata.error_upload_medium()) {
      // We had previously tried to upload this photo and encountered an
      // error. Quarantine the photo.
      QuarantinePhoto(p);
      return;
    }
    p->metadata.set_error_upload_medium(true);
  }
  if (types & FULL) {
    if (p->metadata.error_upload_full()) {
      // We had previously tried to upload this photo and encountered an
      // error. Quarantine the photo.
      QuarantinePhoto(p);
      return;
    }
    p->metadata.set_error_upload_full(true);
  }
  if (types & ORIGINAL) {
    if (p->metadata.error_upload_original()) {
      // We had previously tried to upload this photo and encountered an
      // error. Quarantine the photo.
      QuarantinePhoto(p);
      return;
    }
    p->metadata.set_error_upload_original(true);
  }

  // Reset the photo state machine. Upload the metadata and images again. The
  // error_upload_* bits will be cleared when the photo is uploaded.
  SetUploadBits(&p->metadata, PhotoMetadata::METADATA);
  SetUploadBits(&p->metadata, PhotoMetadata::THUMBNAIL);
  SetUploadBits(&p->metadata, PhotoMetadata::MEDIUM);
  SetUploadBits(&p->metadata, PhotoMetadata::FULL);
  SetUploadBits(&p->metadata, PhotoMetadata::ORIGINAL);

  if (p->metadata.id().has_server_id()) {
    server_photo_map_.erase(p->metadata.id().server_id());
    update_photo_ids_.erase(p->metadata.id().server_id());
    p->metadata.mutable_id()->clear_server_id();
  }

  DB::Batch updates;
  OutputPhotoMetadata(p, &updates);
  env_->db()->Put(updates);

  MaybeQueuePhoto(p);
}

void PhotoManager::DownloadPhotoError(PhotoData* p, int types) {
  if (!p->metadata.id().has_server_id()) {
    // How on earth were we trying to download a photo without a corresponding
    // server id.
    QuarantinePhoto(p);
    return;
  }

  if (types & THUMBNAIL) {
    if (p->metadata.error_download_thumbnail()) {
      // We had previously tried to download this photo and encountered an
      // error. Quarantine the photo.
      QuarantinePhoto(p);
      return;
    }
    p->metadata.set_error_download_thumbnail(true);
  }
  if (types & MEDIUM) {
    if (p->metadata.error_download_medium()) {
      // We had previously tried to download this photo and encountered an
      // error. Quarantine the photo.
      QuarantinePhoto(p);
      return;
    }
    p->metadata.set_error_download_medium(true);
  }
  if (types & FULL) {
    if (p->metadata.error_download_full()) {
      // We had previously tried to download this photo and encountered an
      // error. Quarantine the photo.
      QuarantinePhoto(p);
      return;
    }
    p->metadata.set_error_download_full(true);
  }
  if (types & ORIGINAL) {
    if (p->metadata.error_download_original()) {
      // We had previously tried to download this photo and encountered an
      // error. Quarantine the photo.
      QuarantinePhoto(p);
      return;
    }
    p->metadata.set_error_download_original(true);
  }

  // Reset the photo state machine. Download the metadata and images again. The
  // error_download_* bits will be cleared when the image is successfully
  // downloaded.
  update_photo_ids_.insert(p->metadata.id().server_id());

  DB::Batch updates;
  OutputPhotoMetadata(p, &updates);
  env_->db()->Put(updates);

  MaybeQueuePhoto(p);
}

void PhotoManager::WaitForDownload(
    int64_t photo_id, PhotoType desired_type, void (^done)()) {
  DownloadCallbackSet*& callbacks = download_callback_map_[photo_id];
  if (!callbacks) {
    callbacks = new DownloadCallbackSet;
  }
  __block int id = callbacks->Add(^(int type) {
      if ((type & desired_type) == 0) {
        return;
      }
      callbacks->Remove(id);
      done();
    });
}

void PhotoManager::NotifyDownload(int64_t photo_id, int types) {
  DownloadCallbackSet* callbacks =
      FindOrNull(&download_callback_map_, photo_id);
  if (!callbacks) {
    return;
  }
  callbacks->Run(types);
  if (callbacks->empty()) {
    download_callback_map_.erase(photo_id);
    delete callbacks;
  }
}

void PhotoManager::MergePhotoUpdate(
    const PhotoUpdate& u, bool queue_update, DB::Batch* updates) {
  const string& server_id = u.metadata().id().server_id();
  PhotoData* p = NULL;
  bool dirty = false;

  if (!queue_update) {
    update_photo_ids_.erase(server_id);
    updates->Delete(DBFormat::photo_update_key(server_id));
  }

  // Asset keys are not unique across devices. This code assumes they are
  // unique for a single user, which is probably true. Perhaps we should
  // perform some additional checks (e.g. matching dates or MD5s).
  if (u.metadata().id().has_asset_key() && u.metadata().label_owned()) {
    // First, attempt to look up the photo by the asset key.
    const string& asset_key = u.metadata().id().asset_key();
    const int64_t local_id = env_->db()->Get<int64_t>(asset_key, -1);
    if (local_id > 0) {
      p = FindPtrOrNull(&photo_map_, local_id);
      if (p) {
        if (p->metadata.id().has_server_id() &&
            p->metadata.id().server_id() != server_id) {
          LOG("photo: unexpected server id change (ignoring): %s -> %s",
              p->metadata.id(), ServerIdFormat(server_id));
          return;
        }

        PhotoData* other = FindOrNull(&server_photo_map_, server_id);
        if (other && other != p) {
          // Delete the placeholder photo data and update the server-id for the
          // actual photo data.
          LOG("photo: deleting placeholder photo: %s", other->metadata.id());
          p->metadata.mutable_id()->set_server_id(server_id);
          updates->Delete(DBFormat::photo_key(other->metadata.id().local_id()));
          server_photo_map_[server_id] = p;
          photo_map_.erase(other->metadata.id().local_id());
        }
      }
    }
  }

  if (!p) {
    // Lookup by asset key failed (presumably because the photo was generated
    // by a different device). Lookup by server id.
    p = FindOrNull(&server_photo_map_, server_id);
  }

  bool update_metadata = false;

  if (!p) {
    // Lookup failed. Create a new photo and queue for metadata download.
    PhotoMetadata m;
    m.mutable_id()->set_server_id(server_id);
    p = NewPhoto(m, false, updates);
    CHECK(p != NULL);
    LOG("photo: new photo: %s (%s)", p->metadata.id(), server_id);
    dirty = true;
    update_metadata = true;
  } else {
    LOG("photo: existing photo: %s[%s] (%s)", p->metadata.id().local_id(),
        ServerIdFormat(server_id), server_id);
    if (!u.metadata().has_episode_id() &&
        !p->metadata.episode_id().has_server_id()) {
      update_metadata = true;
    }
  }

  if (queue_update && update_metadata) {
    update_photo_ids_.insert(server_id);
    updates->Put(DBFormat::photo_update_key(server_id), Slice());
  }

  MergePhotoUpdate(p, u, updates, dirty);
}

void PhotoManager::MergePhotoUpdate(
    PhotoData* p, const PhotoUpdate& u, DB::Batch* updates, bool dirty) {
  dirty |= MergePhotoMetadata(p, u.metadata(), updates);

  // Cache any URLs provided by the update.
  if (u.has_tn_put_url()) {
    thumbnail_put_urls_[p->metadata.id().local_id()] = u.tn_put_url();
  }
  if (u.has_med_put_url()) {
    medium_put_urls_[p->metadata.id().local_id()] = u.med_put_url();
  }
  if (u.has_full_put_url()) {
    full_put_urls_[p->metadata.id().local_id()] = u.full_put_url();
  }
  if (u.has_orig_put_url()) {
    original_put_urls_[p->metadata.id().local_id()] = u.orig_put_url();
  }

  if (!HasAssetKey(p->metadata.id())) {
    const PhotoId& id = p->metadata.id();
    if (!env_->photo_storage()->Exists(PhotoThumbnailFilename(id))) {
      if (u.has_tn_get_url()) {
        thumbnail_get_urls_[p->metadata.id().local_id()] = u.tn_get_url();
      }
      SetDownloadBits(&p->metadata, PhotoMetadata::THUMBNAIL);
      dirty = true;
    }
    if (!env_->photo_storage()->Exists(PhotoFullFilename(id))) {
      if (u.has_full_get_url()) {
        full_get_urls_[p->metadata.id().local_id()] = u.full_get_url();
      }
      SetDownloadBits(&p->metadata, PhotoMetadata::FULL);
      dirty = true;
    }
    // TODO(pmattis): Enable download of medium/original photos.
    // if (!env_->photo_storage()->Exists(PhotoMediumFilename(id))) {
    //   if (u.has_med_get_url()) {
    //     medium_get_urls_[p->metadata.id().local_id()] = u.med_get_url();
    //   }
    //   SetDownloadBits(&p->metadata, PhotoMetadata::MEDIUM);
    //   dirty = true;
    // }
    // if (!env_->photo_storage()->Exists(PhotoOriginalFilename(id))) {
    //   if (u.has_orig_get_url()) {
    //     original_get_urls_[p->metadata.id().local_id()] = u.orig_get_url();
    //   }
    //   SetDownloadBits(&p->metadata, PhotoMetadata::ORIGINAL);
    //   dirty = true;
    // }
  }

  if (IsMyPhoto(p->metadata, env_->user_id())) {
    // Determine if we need to upload metadata based on the bits of metadata we
    // have locally versus what we have sent to the server.
    const int local_bits = GetLocalMetadataBits(p);
    if (local_bits & ~p->metadata.server()) {
      const int diff = local_bits & ~p->metadata.server();
      LOG("photo: %s: metadata upload needed:%s%s%s%s%s%s%s%s%s",
          p->metadata.id(),
          (diff & PhotoMetadata::PARENT_ID) ? " parent_id" : "",
          (diff & PhotoMetadata::EPISODE_ID) ? " episode_id" : "",
          (diff & PhotoMetadata::USER_ID) ? " user_id" : "",
          (diff & PhotoMetadata::ASPECT_RATIO) ? " aspect_ratio" : "",
          (diff & PhotoMetadata::TIMESTAMP) ? " timestamp" : "",
          (diff & PhotoMetadata::LOCATION) ? " location" : "",
          (diff & PhotoMetadata::PLACEMARK) ? " placemark" : "",
          (diff & PhotoMetadata::CAPTION) ? " caption" : "",
          (diff & PhotoMetadata::LINK) ? " link" : "");
      if (!UploadMetadata(p->metadata)) {
        dirty = true;
        SetUploadBits(&p->metadata, PhotoMetadata::METADATA);
      }
    } else {
      // The server has all the information we would upload. No need to upload
      // the metadata again.
      if (UploadMetadata(p->metadata)) {
        dirty = true;
        ClearUploadBits(&p->metadata, PhotoMetadata::METADATA);
      }
    }
  }

  if (!p->episode) {
    AddPhotoToEpisode(p, updates);
  }

  bool queue_photo = true;
  if (dirty) {
    if (ShouldDelete(p)) {
      DeletePhoto(p->metadata.id().local_id(), updates);
      // DeletePhoto() may have removed the photo from photo_map_ rendering "p"
      // invalid at this point. Don't attempt to queue the photo.
      queue_photo = false;
    } else {
      OutputPhotoMetadata(p, updates);
    }
    update_.Run();
  }

  if (queue_photo) {
    MaybeQueuePhoto(p);
  }
}

bool PhotoManager::MergePhotoMetadata(
    PhotoData* p, const PhotoMetadata& m, DB::Batch* updates) {
  bool dirty = false;
  if (m.id().has_server_id()) {
    dirty = true;
    if (p->metadata.id().has_server_id()) {
      // TODO(pmattis): Looks like this can fire if we queue a metadata upload
      // for a reset device before processing query updates.
      CHECK_EQ(p->metadata.id().server_id(), m.id().server_id());
    } else {
      p->metadata.mutable_id()->set_server_id(m.id().server_id());
      server_photo_map_[p->metadata.id().server_id()] = p;
    }
  }
  if (m.has_parent_id()) {
    dirty = true;
    p->metadata.mutable_parent_id()->MergeFrom(m.parent_id());
    SetServerMetadataBits(&p->metadata, PhotoMetadata::PARENT_ID);
  }
  if (m.has_user_id()) {
    dirty = true;
    p->metadata.set_user_id(m.user_id());
    SetServerMetadataBits(&p->metadata, PhotoMetadata::USER_ID);
  }
  if (m.has_sharing_user_id()) {
    dirty = true;
    p->metadata.set_sharing_user_id(m.sharing_user_id());
  }
  if (m.has_aspect_ratio()) {
    dirty = true;
    p->metadata.set_aspect_ratio(m.aspect_ratio());
    SetServerMetadataBits(&p->metadata, PhotoMetadata::ASPECT_RATIO);
  }
  if (m.has_timestamp()) {
    dirty = true;
    p->metadata.set_timestamp(m.timestamp());
    SetServerMetadataBits(&p->metadata, PhotoMetadata::TIMESTAMP);
    if (p->episode) {
      std::sort(p->episode->photos.begin(), p->episode->photos.end(),
                PhotoByTimestamp());
    }
  }
  // If the existing photo has a location & placemark and has been
  // added to the placemark histogram, we need to remove it in case
  // this update has modified location/placemark. This handles the
  // following cases:
  //  - No change: restored to histogram on UpdatePhotoMetadata
  //  - Modified placemark: new info added to histogram on UpdatePhotoMetadata
  //  - Placemark/location deleted: removal from histogram is permanent
  if (p->location && p->placemark && p->metadata.placemark_histogram()) {
    p->metadata.set_placemark_histogram(false);
    env_->placemark_histogram()->RemovePlacemark(*p->placemark, *p->location, updates);
  }
  if (m.has_location()) {
    dirty = true;
    if (p->location) {
      p->metadata.mutable_location()->CopyFrom(*p->location);
    }
    p->metadata.mutable_location()->MergeFrom(m.location());
    SetServerMetadataBits(&p->metadata, PhotoMetadata::LOCATION);
  }
  if (m.has_placemark()) {
    dirty = true;
    if (p->placemark) {
      p->metadata.mutable_placemark()->CopyFrom(*p->placemark);
    }
    p->metadata.mutable_placemark()->MergeFrom(m.placemark());
    SetServerMetadataBits(&p->metadata, PhotoMetadata::PLACEMARK);
  }
  if (m.has_location() || m.has_placemark()) {
    InternPhotoLocation(p);
  }
  if (m.has_caption()) {
    dirty = true;
    p->metadata.set_caption(m.caption());
    SetServerMetadataBits(&p->metadata, PhotoMetadata::CAPTION);
  }
  if (m.has_link()) {
    dirty = true;
    p->metadata.set_link(m.link());
    SetServerMetadataBits(&p->metadata, PhotoMetadata::LINK);
  }
  if (m.has_episode_id()) {
    const string& server_episode_id = m.episode_id().server_id();
    EpisodeData* e = FindOrNull(&server_episode_map_, server_episode_id);
    if (!e) {
      // We can't find the episode the update references. Create a new episode
      // and queue the metadata for the episode for download.
      e = NewEpisode(updates);
      e->metadata.mutable_id()->set_server_id(server_episode_id);
      e->metadata.set_user_id(p->metadata.user_id());
      server_episode_map_[e->metadata.id().server_id()] = e;
      LOG("photo: new episode: %s (%s)", e->metadata.id(), server_episode_id);
      update_episode_ids_.insert(server_episode_id);
      updates->Put(DBFormat::episode_update_key(server_episode_id), Slice());
      OutputEpisodeMetadata(e, updates);
    }

    if (e != p->episode) {
      // Move the photo from its current episode to the new episode.
      if (p->episode) {
        LOG("photo: %s: changing episodes %s -> %s",
            p->metadata.id(), p->episode->metadata.id(), e->metadata.id());
      }
      RemovePhotoFromEpisode(p, updates);
    }

    p->metadata.mutable_episode_id()->CopyFrom(e->metadata.id());
    SetServerMetadataBits(&p->metadata, PhotoMetadata::EPISODE_ID);
    dirty = true;

    if (e != p->episode) {
      AddPhotoToExistingEpisode(p, e, updates);
    }
  }
  return MergePhotoLabels(&p->metadata, m) || dirty;
}

void PhotoManager::MergeEpisodeUpdate(
    const EpisodeUpdate& u, bool queue_update, DB::Batch* updates) {
  const string& server_id = u.metadata().id().server_id();
  EpisodeData* e = FindOrNull(&server_episode_map_, server_id);
  bool dirty = false;

  if (!queue_update) {
    update_episode_ids_.erase(server_id);
    updates->Delete(DBFormat::episode_update_key(server_id));
  }

  if (!e) {
    e = NewEpisode(updates);
    e->metadata.mutable_id()->set_server_id(server_id);
    server_episode_map_[e->metadata.id().server_id()] = e;
    LOG("photo: new episode: %s (%s)", e->metadata.id(), server_id);
    dirty = true;
    if (queue_update) {
      update_episode_ids_.insert(server_id);
      updates->Put(DBFormat::episode_update_key(server_id), Slice());
    }
  } else {
    LOG("photo: existing episode: %s (%s)", e->metadata.id(), server_id);
  }

  dirty |= MergeEpisodeMetadata(e, u.metadata());

  if (dirty) {
    OutputEpisodeMetadata(e, updates);
    update_.Run();
  }
}

bool PhotoManager::MergeEpisodeMetadata(
    EpisodeData* e, const EpisodeMetadata& m) {
  bool dirty = false;
  if (m.has_user_id()) {
    dirty = true;
    e->metadata.set_user_id(m.user_id());
  }
  if (m.has_sharing_user_id()) {
    dirty = true;
    e->metadata.set_sharing_user_id(m.sharing_user_id());
  }
  if (m.has_timestamp()) {
    dirty = true;
    e->metadata.set_timestamp(m.timestamp());
  }
  if (m.has_title()) {
    dirty = true;
    e->metadata.set_title(m.title());
  }
  if (m.has_description()) {
    dirty = true;
    e->metadata.set_description(m.description());
  }
  if (m.has_location()) {
    dirty = true;
    if (e->location) {
      e->metadata.mutable_location()->CopyFrom(*e->location);
    }
    e->metadata.mutable_location()->MergeFrom(m.location());
  }
  if (m.has_placemark()) {
    dirty = true;
    if (e->placemark) {
      e->metadata.mutable_placemark()->CopyFrom(*e->placemark);
    }
    e->metadata.mutable_placemark()->MergeFrom(m.placemark());
  }
  if (m.has_location() || m.has_placemark()) {
    InternEpisodeLocation(e);
  }
  if (m.has_name()) {
    dirty = true;
    e->metadata.set_name(m.name());
  }
  if (m.has_modified()) {
    dirty = true;
    e->metadata.set_modified(m.modified());
  }
  return MergeEpisodeLabels(&e->metadata, m) || dirty;
}

void PhotoManager::OutputPhotoMetadata(PhotoData* p, DB::Batch* updates) {
  PhotoMetadata m = p->metadata;
  if (p->location) {
    m.mutable_location()->CopyFrom(*p->location);
  }
  if (p->placemark) {
    m.mutable_placemark()->CopyFrom(*p->placemark);
  }

  // If there's both a location and a placemark AND we haven't already
  // updated the placemark histogram, do so now.
  if (m.has_location() && m.has_placemark() && !m.placemark_histogram()) {
    p->metadata.set_placemark_histogram(true);
    m.set_placemark_histogram(true);
    env_->placemark_histogram()->AddPlacemark(m.placemark(), m.location(), updates);
  } else if (m.has_delete_timestamp() && m.placemark_histogram()) {
    // Otherwise, if there's a delete timestamp and we're counting
    // this photo in the placemark histogram, remove it.
    p->metadata.set_placemark_histogram(false);
    m.set_placemark_histogram(false);
    env_->placemark_histogram()->RemovePlacemark(m.placemark(), m.location(), updates);
  }

  // Don't persist the image metadata to disk. It can be regenerated fairly
  // easily.
  m.clear_images();
  updates->PutProto(
      DBFormat::photo_key(p->metadata.id().local_id()), m);
}

void PhotoManager::OutputEpisodeMetadata(EpisodeData* e, DB::Batch* updates) {
  updates->PutProto(
      DBFormat::episode_key(e->metadata.id().local_id()), e->metadata);
}

void PhotoManager::ReprioritizePhotoQueue() {
  WallTimer timer;
  queued_photos_.clear();
  queued_uploads_.clear();
  queued_downloads_.clear();
  queued_shares_.clear();
  for (PhotoMap::iterator iter(photo_map_.begin());
       iter != photo_map_.end();
       ++iter) {
    MaybeQueuePhoto(&iter->second);
  }
  LOG("photo: reprioritize photo queue: %d photos (%d uploads, %d downloads): %.03f ms",
      queued_photos_.size(), num_queued_uploads(), num_queued_downloads(),
      timer.Milliseconds());
}

void PhotoManager::UnqueuePhoto(PhotoData* p) {
  // Delete the photo from various queued uploads.
  if (queued_metadata_upload_.get()) {
    MetadataUpload* u = queued_metadata_upload_.get();
    for (int i = 0; i < u->photos.size(); ++i) {
      if (u->photos[i] == p) {
        u->photos.erase(u->photos.begin() + i);
        break;
      }
    }
    if (u->photos.empty()) {
      queued_metadata_upload_.reset(NULL);
    }
  }
  if (queued_photo_upload_.get() &&
      (queued_photo_upload_->photo == p)) {
    queued_photo_upload_.reset(NULL);
  }
  if (queued_share_upload_.get()) {
    ShareUpload* u = queued_share_upload_.get();
    for (int i = 0; i < u->photos.size(); ++i) {
      if (u->photos[i] == p) {
        u->photos.erase(u->photos.begin() + i);
        break;
      }
    }
  }
  if (queued_unshare_upload_.get()) {
    UnshareUpload* u = queued_unshare_upload_.get();
    for (int i = 0; i < u->photos.size(); ++i) {
      if (u->photos[i] == p) {
        u->photos.erase(u->photos.begin() + i);
        break;
      }
    }
  }

  // Delete the photo from the various queues.
  queued_photos_.erase(p);
  queued_uploads_.erase(p);
  queued_downloads_.erase(p);
  queued_shares_.erase(p);

  // Indicate a download error occurred for all versions of the photo.
  NotifyDownload(p->metadata.id().local_id(), THUMBNAIL|MEDIUM|FULL|ORIGINAL);
}

void PhotoManager::MaybeQueuePhoto(PhotoData* p) {
  queued_photos_.erase(p);
  queued_uploads_.erase(p);
  queued_downloads_.erase(p);
  queued_shares_.erase(p);

  if (!env_->network_up() || !env_->logged_in()) {
    return;
  }
  if (p->metadata.label_error()) {
    // The photo has the error label, do not queue.
    return;
  }
  if (ContainsKey(update_photo_ids_, p->metadata.id().server_id())) {
    // The photo needs to be updated, do not queue.
    return;
  }

  bool queue = false;
  bool upload = false;
  bool download = false;
  const bool wifi = env_->network_wifi();
  p->priority = PhotoPriority(p->metadata, wifi);
  p->timestamp = PhotoTimestamp(p->metadata);

  if (wifi) {
    // We have a wifi network connection.
    string reason;
    if (p->metadata.has_delete_timestamp()) {
      reason += " delete";
      queue = true;
    }
    if (p->metadata.has_share() ||
        p->metadata.has_unshare_timestamp()) {
      if (p->metadata.has_share()) {
        reason += " share";
      }
      if (p->metadata.has_unshare_timestamp()) {
        reason += " unshare";
      }
      queue = true;
    }
    if (DownloadThumbnail(p->metadata) ||
        DownloadMedium(p->metadata) ||
        DownloadFull(p->metadata) ||
        DownloadOriginal(p->metadata)) {
      reason += Format(
          " download%s%s%s%s",
          DownloadThumbnail(p->metadata) ? ":thumbnail" : "",
          DownloadMedium(p->metadata)  ? ":medium" : "",
          DownloadFull(p->metadata)  ? ":full" : "",
          DownloadOriginal(p->metadata)  ? ":original" : "");
      queue = true;
      download = true;
    }
    if (UploadPhoto(p, env_.get()) &&
        (UploadMetadata(p->metadata) ||
         UploadThumbnail(p->metadata) ||
         UploadMedium(p->metadata) ||
         UploadFull(p->metadata) ||
         (env_->store_originals() && UploadOriginal(p->metadata)))) {
      reason += Format(
          " upload%s%s%s%s",
          UploadMetadata(p->metadata) ? ":metadata" : "",
          UploadThumbnail(p->metadata) ? ":thumbnail" : "",
          UploadMedium(p->metadata) ? ":medium" : "",
          UploadFull(p->metadata) ? ":full" : "");
      if (env_->store_originals() && UploadOriginal(p->metadata)) {
        reason += ":original";
      }
      queue = true;
      upload = true;
    }
    if (!reason.empty()) {
      LOG("photo: %s: queueing:%s [%d]", p->metadata.id(), reason, p->priority);
    }
  } else {
    // We have a 3g/edge network connection.
    string reason;
    if (p->metadata.has_delete_timestamp()) {
      reason += " delete";
      queue = true;
    }
    if (p->metadata.has_share() ||
        p->metadata.has_unshare_timestamp()) {
      if (p->metadata.has_share()) {
        reason += " share";
      }
      if (p->metadata.has_unshare_timestamp()) {
        reason += " unshare";
      }
      queue = true;
    }
    if (DownloadThumbnail(p->metadata) ||
        DownloadFull(p->metadata)) {
      reason += Format(
          " download%s%s",
          DownloadThumbnail(p->metadata) ? ":thumbnail" : "",
          DownloadFull(p->metadata) ? ":full" : "");
      queue = true;
      download = true;
    }
    // Only upload photos on 3g/edge if the photos have been shared/unshared.
    if (UploadPhoto(p, env_.get()) &&
        (UploadMetadata(p->metadata) ||
         UploadThumbnail(p->metadata) ||
         UploadFull(p->metadata))) {
      reason += Format(
          " upload%s%s%s",
          UploadMetadata(p->metadata) ? ":metadata" : "",
          UploadThumbnail(p->metadata) ? ":thumbnail" : "",
          UploadFull(p->metadata) ? ":full" : "");
      queue = true;
      upload = true;
    }
    if (!reason.empty()) {
      LOG("photo: %s: queueing:%s [%d]", p->metadata.id(), reason, p->priority);
    }
  }

  if (upload) {
    queued_uploads_.insert(p);
  }
  if (download) {
    queued_downloads_.insert(p);
  }
  if (p->metadata.has_share()) {
    queued_shares_.insert(p);
  }
  if (queue) {
    queued_photos_.insert(p);
  } else {
    p->priority = -1;
    p->timestamp = 0;
  }
}

void PhotoManager::MaybeQueueNetwork() {
  if (!env_->network_up() || !env_->logged_in()) {
    // The network is not ready for uploads or the user is not logged in. Clear
    // any queued item.
    queued_metadata_upload_.reset(NULL);
    queued_photo_upload_.reset(NULL);
    queued_photo_download_.reset(NULL);
    queued_share_upload_.reset(NULL);
    queued_unshare_upload_.reset(NULL);
    queued_delete_upload_.reset(NULL);
    return;
  }
  if (queued_metadata_upload_.get() ||
      queued_photo_upload_.get() ||
      queued_photo_download_.get() ||
      queued_share_upload_.get() ||
      queued_unshare_upload_.get() ||
      queued_delete_upload_.get()) {
    // An item is already queued, do not change it because the network request
    // might currently be in progress.
    return;
  }
  if (queue_in_progress_) {
    if (queue_start_time_ > 0) {
      LOG("photo: queue still in progress: %.03f ms",
          1000 * (WallTime_Now() - queue_start_time_));
    }
    return;
  }
  if (queued_photos_.empty()) {
    // There are no photos queued for upload.
    return;
  }
  if (env_->assets_scanning()) {
    // An asset library scan is still in progress.
    return;
  }

  PhotoData* p = *queued_photos_.begin();
  // If the UI is waiting for the photo to be download, retrieve the photo
  // before any other operations.
  if (p->metadata.id().has_server_id() &&
      ((DownloadThumbnail(p->metadata) && p->metadata.error_ui_thumbnail()) ||
       (DownloadFull(p->metadata) && p->metadata.error_ui_full()))) {
    MaybeQueuePhotoDownload(p);
    return;
  }

  const WallTime last_load_delta = WallTime_Now() - last_load_time_;
  if (last_load_delta < kPauseNetworkDuration) {
    const WallTime delay = kPauseNetworkDuration - last_load_delta;
    // LOG("photo: pausing network: %.1f sec", delay);
    async_->dispatch_after_main(delay, ^{
        MaybeQueueNetwork();
      });
  }

  // Upload metadata before any other operations.
  if (p->episode && UploadMetadata(p->metadata)) {
    MaybeQueueMetadataUpload(p->episode);
    return;
  }

  // Deletes & unshares take precedence over uploads & shares.
  if (p->metadata.has_delete_timestamp()) {
    MaybeQueueDeleteUpload();
    return;
  }
  if (p->metadata.has_unshare_timestamp()) {
    MaybeQueueUnshareUpload();
    return;
  }
  if (DownloadThumbnail(p->metadata) ||
      DownloadFull(p->metadata)) {
    MaybeQueuePhotoDownload(p);
    return;
  }

  // Upload thumbnail and full-screen images before share requests.
  if (UploadThumbnail(p->metadata) ||
      UploadFull(p->metadata)) {
    MaybeQueuePhotoUpload(p);
    return;
  }
  // Upload share requests before medium and original images.
  if (p->metadata.has_share()) {
    MaybeQueueShareUpload();
    return;
  }
  if (UploadMedium(p->metadata) ||
      UploadOriginal(p->metadata)) {
    MaybeQueuePhotoUpload(p);
    return;
  }
}

void PhotoManager::MaybeQueueMetadataUpload(EpisodeData* e) {
  queue_in_progress_ = true;
  queue_start_time_ = WallTime_Now();

  MetadataUpload* u = new MetadataUpload;
  for (int i = 0; i < e->photos.size(); ++i) {
    PhotoData* p = e->photos[i];
    if (!UploadMetadata(p->metadata)) {
      continue;
    }
    // Always start the images metadata from a clean slate.
    p->metadata.clear_images();
    u->photos.push_back(p);
    if (u->photos.size() >= kMaxPhotosPerUpload) {
      break;
    }
  }

  MaybeLoadImages(u, 0);
}

void PhotoManager::MaybeLoadImages(MetadataUpload* u, int index) {
  for (; index < u->photos.size(); ++index) {
    PhotoData* p = u->photos[index];
    PhotoMetadata::Image* i = NULL;
    int size = 0;

    if (!p->metadata.images().has_tn()) {
      size = kThumbnailSize;
      i = p->metadata.mutable_images()->mutable_tn();
    } else if (!p->metadata.images().has_orig()) {
      size = kOriginalSize;
      i = p->metadata.mutable_images()->mutable_orig();
    } else if (!p->metadata.images().has_full()) {
      size = kFullSize;
      i = p->metadata.mutable_images()->mutable_full();
    } else if (!p->metadata.images().has_med()) {
      size = kMediumSize;
      i = p->metadata.mutable_images()->mutable_med();
    } else {
      // If this is an asset photo and we're not storing originals to the
      // cloud, remove the viewfinder original image immediately.
      if (HasAssetKey(p->metadata.id()) && !env_->store_originals()) {
        const string filename = PhotoOriginalFilename(p->metadata.id());
        LOG("photo: %s: deleting image %s", p->metadata.id(), filename);
        DB::Batch updates;
        env_->photo_storage()->Delete(filename, &updates);
        env_->db()->Put(updates);
      }
      continue;
    }

    void (^done)(const string& path, const string& md5) =
        ^(const string& path, const string& md5) {
      const int64_t file_size = FileSize(path);
      if (file_size <= 0 || md5.empty()) {
        // Remove the photo from the MetadataUpload and quarantine.
        u->photos.erase(u->photos.begin() + index);
      } else {
        i->set_size(file_size);
        i->set_md5(md5);
      }
      // LOG("photo: %s: md5 done: %s: %d %s",
      //     p->metadata.id(), PhotoSizeSuffix(size), i->size(), i->md5());
      MaybeLoadImages(u, index);
    };

    if (MaybeLoadImageData(p, size, done)) {
      return;
    }
    // The image data could not be loaded. Remove the photo from the
    // MetadataUpload and quarantine.
    u->photos.erase(u->photos.begin() + index);
    --index;
  }

  dispatch_main(^{
      MaybeReverseGeocode(u, 0);
    });
}

bool PhotoManager::MaybeLoadImageData(
    PhotoData* p, int size,
    void (^completion)(const string& path, const string& md5)) {
  void (^done)() = ^{
    const string filename = PhotoFilename(p->metadata.id(), size);
    const string path = JoinPath(photo_dir_, filename);
    const string md5 = env_->photo_storage()->Metadata(filename).md5();
    completion(path, md5);
  };

  // Passing store_jpeg=true causes MaybeLoadInternal() to write the jpeg to
  // the viewfinder photo area.
  return MaybeLoadInternal(p, CGSizeMake(size, size), true, NULL, NULL, done);
}

void PhotoManager::MaybeReverseGeocode(MetadataUpload* u, int index) {
  for (; index < u->photos.size(); ++index) {
    PhotoData* p = u->photos[index];
    if (ReverseGeocode(p->metadata.id().local_id(), ^(bool) {
          MaybeReverseGeocode(u, index + 1);
        })) {
      return;
    }
  }

  // All of the photos could have been removed (and presumably quarantined)
  // during the upload queueing process.
  if (!u->photos.empty()) {
    // The queued upload is ready to go.
    EpisodeData* e = u->photos.front()->episode;
    LOG("photo: queued metadata upload: %s: %.03f ms",
        e->metadata.id(), 1000 * (WallTime_Now() - queue_start_time_));
    queued_metadata_upload_.reset(u);
  } else {
    delete u;
  }

  queue_in_progress_ = false;
  queue_start_time_ = 0;

  // Kick the NetworkManager. Even if no upload was queued, this will run the
  // dispatch loop and cause another upload queue to take place.
  env_->NetworkDispatch();
}

void PhotoManager::MaybeQueuePhotoUpload(PhotoData* p) {
  WallTimer timer;
  queue_in_progress_ = true;
  queue_start_time_ = WallTime_Now();

  PhotoUpload* u = new PhotoUpload(p);
  PhotoURLMap* urls = NULL;
  int size = 0;

  if (UploadThumbnail(p->metadata)) {
    u->type = THUMBNAIL;
    urls = &thumbnail_put_urls_;
    size = kThumbnailSize;
  } else if (UploadFull(p->metadata)) {
    u->type = FULL;
    urls = &full_put_urls_;
    size = kFullSize;
  } else if (UploadMedium(p->metadata)) {
    u->type = MEDIUM;
    urls = &medium_put_urls_;
    size = kMediumSize;
  } else if (UploadOriginal(p->metadata)) {
    u->type = ORIGINAL;
    urls = &original_put_urls_;
    size = kOriginalSize;
  } else {
    CHECK(false);
  }
  u->url = FindOrDefault(*urls, p->metadata.id().local_id(), string());

  void (^done)(const string& path, const string& md5) =
      ^(const string& path, const string& md5) {
    queued_photo_upload_.reset(u);
    queue_in_progress_ = false;
    queue_start_time_ = 0;

    if (path.empty() || md5.empty()) {
      async_->dispatch_main(^{
          LOG("photo: queue photo upload error: %s: %s",
              p->metadata.id(), PhotoSizeSuffix(size));
          CommitQueuedPhotoUpload(true);
        });
      return;
    }

    u->path = path;
    u->md5 = md5;

    // The queued upload is ready to go. Kick the NetworkManager.
    LOG("photo: queued photo upload: %s (%s): %.03f ms",
        p->metadata.id(), PhotoSizeSuffix(size), timer.Milliseconds());
    async_->dispatch_main(^{
        env_->NetworkDispatch();
      });
  };

  if (!MaybeLoadImageData(p, size, done)) {
    // We're not able to load the image data, invoke the completion on a
    // background thread to avoid too much recursion.
    dispatch_low_priority(^{
        done(string(), string());
      });
  }
}

void PhotoManager::MaybeQueuePhotoDownload(PhotoData* p) {
  PhotoDownload* d = new PhotoDownload;
  d->id = p->metadata.id();

  PhotoURLMap* urls = NULL;
  if (DownloadThumbnail(p->metadata)) {
    d->type = THUMBNAIL;
    d->path = JoinPath(photo_tmp_dir_, PhotoThumbnailFilename(d->id));
    urls = &thumbnail_get_urls_;
  } else if (DownloadFull(p->metadata)) {
    d->type = FULL;
    d->path = JoinPath(photo_tmp_dir_, PhotoFullFilename(d->id));
    urls = &full_get_urls_;
  } else if (DownloadMedium(p->metadata)) {
    d->type = MEDIUM;
    d->path = JoinPath(photo_tmp_dir_, PhotoMediumFilename(d->id));
    urls = &medium_get_urls_;
  } else if (DownloadOriginal(p->metadata)) {
    d->type = ORIGINAL;
    d->path = JoinPath(photo_tmp_dir_, PhotoOriginalFilename(d->id));
    urls = &original_get_urls_;
  }

  d->url = FindOrDefault(*urls, p->metadata.id().local_id(), string());
  queued_photo_download_.reset(d);

  env_->NetworkDispatch();
}

void PhotoManager::MaybeQueueShareUpload() {
  if (queued_share_upload_.get() || queued_photos_.empty()) {
    return;
  }

  for (PhotoQueue::iterator iter(queued_photos_.begin());
       iter != queued_photos_.end();
       ++iter) {
    PhotoData* p = *iter;
    if (!p->metadata.has_share()) {
      // All of the queued shares will be sorted at the front of the queue.
      break;
    }
    if (!p->metadata.id().has_server_id() ||
        UploadThumbnail(p->metadata) ||
        UploadFull(p->metadata)) {
      // Photo has not been uploaded. Skip for now.
      continue;
    }

    // Construct a new ShareUpload.
    ShareUpload* u = new ShareUpload;
    queued_share_upload_.reset(u);
    u->photos.push_back(p);

    std::set<string> identities;
    const PhotoShare& share = p->metadata.share();
    for (int i = 0; i < share.contacts_size(); ++i) {
      u->contacts.push_back(share.contacts(i));
      identities.insert(share.contacts(i).identity());
    }

    // Look for any photos that have a matching set of contacts that we can add
    // to this share upload.
    ++iter;
    for (; iter != queued_photos_.end(); ++iter) {
      PhotoData* p = *iter;
      if (!p->metadata.has_share()) {
        // All of the queued shares will be sorted at the front of the queue.
        break;
      }
      if (p->episode != u->photos.front()->episode) {
        // Different episode, don't include in this share.
        continue;
      }
      if (!p->metadata.id().has_server_id() ||
          UploadThumbnail(p->metadata) ||
          UploadFull(p->metadata)) {
        // Photo has not been uploaded. Skip for now.
        continue;
      }
      const PhotoShare& share = p->metadata.share();
      if (share.contacts_size() != identities.size()) {
        // Different number of contacts, they cannot possibly be equal.
        continue;
      }

      std::set<string> other_identities;
      for (int i = 0; i < share.contacts_size(); ++i) {
        other_identities.insert(share.contacts(i).identity());
      }
      if (identities != other_identities) {
        continue;
      }

      u->photos.push_back(p);
    }

    LOG("photo: queued share upload: %d photo%s, %d contact%s",
        u->photos.size(), Pluralize(u->photos.size()),
        u->contacts.size(), Pluralize(u->contacts.size()));
    env_->NetworkDispatch();
    break;
  }
}

void PhotoManager::MaybeQueueUnshareUpload() {
  if (queued_unshare_upload_.get() || queued_photos_.empty()) {
    return;
  }

  UnshareUpload* u = new UnshareUpload;
  queued_unshare_upload_.reset(u);

  for (PhotoQueue::iterator iter(queued_photos_.begin());
       iter != queued_photos_.end();
       ++iter) {
    PhotoData* p = *iter;
    if (!p->metadata.has_unshare_timestamp()) {
      continue;
    }
    EpisodeData* e = p->episode;
    for (int i = 0; i < e->photos.size(); ++i) {
      PhotoData* ep = e->photos[i];
      if (ep->metadata.has_unshare_timestamp()) {
        u->photos.push_back(ep);
      }
    }
    break;
  }
  CHECK_GT(u->photos.size(), 0);

  env_->NetworkDispatch();
}

void PhotoManager::MaybeQueueDeleteUpload() {
  if (queued_delete_upload_.get() || queued_photos_.empty()) {
    return;
  }

  DeleteUpload* u = new DeleteUpload;
  queued_delete_upload_.reset(u);

  for (PhotoQueue::iterator iter(queued_photos_.begin());
       iter != queued_photos_.end();
       ++iter) {
    PhotoData* p = *iter;
    if (!p->metadata.has_delete_timestamp()) {
      continue;
    }
    u->photos.push_back(p);
    if (u->photos.size() >= kMaxPhotosPerUpload) {
      break;
    }
  }

  env_->NetworkDispatch();
}

bool PhotoManager::MaybeLoadInternal(
    PhotoData* p, CGSize size, bool store_jpeg,
    NSData* __strong* jpeg_data, Image* image,
    void (^done)()) {
  if (p->metadata.has_delete_timestamp() ||
      p->metadata.label_error()) {
    return false;
  }

  void (^completion)(bool error) = ^(bool error) {
    if (!error) {
      done();
      return;
    }
    dispatch_main(^{
        // Recursively try to load the photo, this will cause other resolutions
        // of the photo to be attempted and eventually kick down into the asset
        // library loading.
        if (MaybeLoadInternal(p, size, store_jpeg, jpeg_data, image, done)) {
          return;
        }
        done();
      });
  };

  // First try and load the image from the local viewfinder storage area. This
  // might fail if an appropriate resolution image does not exist, or the jpeg
  // has been corrupted. On jpeg corruption (and some other errors),
  // MaybeLoadViewfinder() will return true, but error==true will be returned
  // to the completion and the offending corrupt file will have been deleted.
  if (MaybeLoadViewfinder(
          p, size, store_jpeg, jpeg_data, image, completion)) {
    return true;
  }

  // Next try and load the image from the assets library. This might fail if
  // the asset does not exist or has some other error (e.g. the asset exists
  // but the thumbnail does not).
  if (MaybeLoadAsset(
          p, size, store_jpeg, jpeg_data, image, completion)) {
    return true;
  }

  if (p->metadata.id().has_server_id()) {
    async_->dispatch_main(^{
        // The photo has been uploaded to the server, try to download the images
        // again.
        const float max_size = std::max(size.width, size.height);
        if (max_size <= kThumbnailSize) {
          p->metadata.set_error_ui_thumbnail(true);
          SetDownloadBits(&p->metadata, PhotoMetadata::THUMBNAIL);
        } else {
          // TODO(pmattis): Also try and download the medium resolution
          // image. This needs coordination with LoadNetworkPhoto() and error
          // handling in case the full resolution image exists but the medium
          // resolution image does not.
          p->metadata.set_error_ui_full(true);
          SetDownloadBits(&p->metadata, PhotoMetadata::FULL);
        }

        DB::Batch updates;
        OutputPhotoMetadata(p, &updates);
        env_->db()->Put(updates);

        MaybeQueuePhoto(p);
        env_->NetworkDispatch();
      });
  } else {
    // The photo only exists locally and cannot be loaded: quarantine it.
    QuarantinePhoto(p);
  }
  return false;
}

bool PhotoManager::MaybeLoadViewfinder(
    PhotoData* p, CGSize size, bool store_jpeg,
    NSData* __strong* dest_jpeg_data, Image* dest_image,
    void (^done)(bool error)) {
  // __block WallTimer timer;

  // Find the smallest resolution image that satisfies the request.
  const float max_size = std::max(size.width, size.height);

  string filename_metadata;
  const string filename =
      env_->photo_storage()->LowerBound(
          p->metadata.id().local_id(), max_size, &filename_metadata);
  if (filename.empty()) {
    return false;
  }

  // Fail if the file does not exist.
  if (env_->photo_storage()->Size(filename) <= 0) {
    async_->dispatch_low_priority(^{
        LoadViewfinderPhotoError(p, filename, done);
      });
    return true;
  }

  // Determine the max dimension of the on disk image.
  const int max_dim = PhotoFilenameToSize(filename);
  if (max_size > max_dim) {
    // We've been asked to load an image that is larger than the one we have on
    // disk. Fail and let network loading run.
    return false;
  }

  // Map the requested size to one of thumbnail, medium, full or original.
  const int load_size = MaxSizeToLoadSize(max_size);
  if (max_dim == load_size && !dest_jpeg_data &&
      !dest_image && !filename_metadata.empty()) {
    // We already have the correct file and the caller did not want either the
    // jpeg data or image.
    async_->dispatch_low_priority(^{
        done(false);
      });
    return true;
  }

  async_->dispatch_low_priority(^{
      // Load the jpeg data.
      NSData* tmp_jpeg_data;
      NSData* __strong* jpeg_data =
          dest_jpeg_data ? dest_jpeg_data : &tmp_jpeg_data;
      *jpeg_data = env_->photo_storage()->Read(filename, filename_metadata);

      if (!*jpeg_data) {
        LOG("photo: %s: loading failed: %s", p->metadata.id(), filename);
        LoadViewfinderPhotoError(p, filename, done);
        return;
      }

      if (max_dim <= max_size * 1.5) {
        // We have an appropriate resolution. If we need the image, load and resize
        // it.
        Image* image = dest_image;
        if (image) {
          if (!image->DecompressJPEG(*jpeg_data, NULL)) {
            LOG("photo: %s: loading failed: %s", p->metadata.id(), filename);
            LoadViewfinderPhotoError(p, filename, done);
            return;
          } else {
            // LOG("photo: %s: loaded image: %dx%d: %.3f ms",
            //     p->metadata.id(), image->width(), image->height(),
            //     timer.Milliseconds());
            // timer.Restart();

            // Resize the thumbnail smaller if necessary.
            MaybeQueueDetect(p, *image);
            if (ResizePhoto(size, image)) {
              if (!*image) {
                LOG("photo: %s: resizing failed", p->metadata.id());
              } else {
                // LOG("photo: %s: resized image: %dx%d: %.3f ms",
                //     p->metadata.id(), image->width(), image->height(),
                //     timer.Milliseconds());
              }
            }
          }
        }
      } else {
        ScopedRef<CGImageSourceRef> image_src(
            CGImageSourceCreateWithData(
                (__bridge CFDataRef)*jpeg_data,
                Dict(kCGImageSourceTypeIdentifierHint, kUTTypeJPEG)));
        if (!image_src || CGImageSourceGetCount(image_src) < 1) {
          if (!image_src) {
            LOG("photo: %s: unable to decompress image: %s",
                p->metadata.id(), filename);
          } else {
            LOG("photo: %s: no images found: %s", p->metadata.id(), filename);
          }
          LoadViewfinderPhotoError(p, filename, done);
          return;
        } else {
          Image tmp_image;
          Image* image = dest_image ? dest_image : &tmp_image;

          image->acquire(
              CGImageSourceCreateThumbnailAtIndex(
                  image_src, 0,
                  Dict(kCGImageSourceCreateThumbnailFromImageAlways, true,
                       kCGImageSourceThumbnailMaxPixelSize, load_size,
                       kCGImageSourceCreateThumbnailWithTransform, true)));
          // LOG("photo: %s: loaded image: %s: %dx%d: %.3f ms",
          //     p->metadata.id(), filename, image->width(), image->height(),
          //     timer.Milliseconds());
          // timer.Restart();

          if (max_dim != load_size) {
            *jpeg_data =
                image->CompressJPEG(NULL, kJpegThumbnailQuality);
            if (*jpeg_data) {
              const string filename = PhotoFilename(p->metadata.id(), load_size);
              DB::Batch updates;
              if (env_->photo_storage()->Write(
                      filename, *jpeg_data, &updates)) {
                env_->db()->Put(updates);
              }
              // LOG("photo: %s: wrote image: %s: %d bytes: %.3f ms",
              //     p->metadata.id(), filename,
              //     [*jpeg_data length], timer.Milliseconds());
              // timer.Restart();
            }
          }

          MaybeQueueDetect(p, *image);
          if (image != &tmp_image) {
            ResizePhoto(size, image);
            if (!*image) {
              LOG("photo: %s: resizing failed", p->metadata.id());
            } else {
              // LOG("photo: %s: resized image: %dx%d: %.3f ms",
              //     p->metadata.id(), image->width(), image->height(),
              //     timer.Milliseconds());
            }
          }
        }
      }

      done(false);
    });
  return true;
}

bool PhotoManager::MaybeLoadAsset(
    PhotoData* p, CGSize size, bool store_jpeg,
    NSData* __strong* jpeg_data, Image* dest_image,
    void (^done)(bool error)) {
  if (!HasAssetKey(p->metadata.id())) {
    return false;
  }

  // Check for existing errors before attempting to load the asset.
  const float max_size = std::max(size.width, size.height);
  if (HasAssetError(p->metadata, max_size)) {
    return false;
  }

  // __block WallTimer timer;
  const string asset_key = GetAssetKey(p->metadata.id());

  ALAssetsLibraryAssetForURLResultBlock result = ^(ALAsset* asset) {
    async_->dispatch_low_priority(^{
        if (!asset) {
          // The asset does not exist.
          LOG("photo: %s: loading failed: %s", p->metadata.id(), asset_key);
          LoadAssetPhotoError(p, THUMBNAIL|FULL|ORIGINAL, done);
          return;
        }

        Image tmp_image;
        Image* image = dest_image ? dest_image : &tmp_image;

        if (max_size <= kThumbnailSize) {
          image->reset([asset aspectRatioThumbnail]);
          if (!*image) {
            LOG("photo: %s: thumbnail image not found: %s",
                p->metadata.id(), asset_key);
            LoadAssetPhotoError(p, THUMBNAIL, done);
            return;
          } else {
            // LOG("photo: %s: loaded thumbnail image: %.3f ms",
            //     p->metadata.id(), timer.Milliseconds());
            // timer.Restart();

            // If we haven't been asked to store the jpeg or for the jpeg data
            // itself, asynchronously write a jpeg thumbnail that is quicker to
            // access.
            if (!store_jpeg && !jpeg_data) {
              Image image_ref(*image);
              async_->dispatch_low_priority(^{
                  NSData* jpeg_data = image_ref.CompressJPEG(
                      NULL, kJpegThumbnailQuality);
                  MaybeWriteThumbnail(p, jpeg_data);
                });
            } else {
              // Synchronously write a jpeg thumbnail that is quicker to
              // access.
              NSData* tmp_jpeg_data;
              NSData* __strong* dest_data =
                  jpeg_data ? jpeg_data : &tmp_jpeg_data;
              *dest_data =
                  image->CompressJPEG(NULL, kJpegThumbnailQuality);
              // LOG("photo: %s: compressed thumbnail image: %.3f ms",
              //     p->metadata.id(), timer.Milliseconds());
              // timer.Restart();
              MaybeWriteThumbnail(p, *dest_data);
            }

            MaybeQueueDetect(p, *image);
            if (image != &tmp_image) {
              if (ResizePhoto(size, image)) {
                // LOG("photo: %s: resized thumbnail image: %.3f ms",
                //     p->metadata.id(), timer.Milliseconds());
              }
              if (!*image) {
                LOG("photo: %s: resizing thumbnail image failed",
                    p->metadata.id());
              }
            }
          }
        } else if (max_size > kFullSize) {
          ALAssetRepresentation* rep = [asset defaultRepresentation];
          if (image != &tmp_image) {
            image->reset([rep fullResolutionImage]);
            if (!*image) {
              LOG("photo: %s: full resolution image not found: %s",
                  p->metadata.id(), asset_key);
              LoadAssetPhotoError(p, ORIGINAL, done);
              return;
            }
            // Set the orientation and scale. This is only needed for the
            // fullResolutionImage. Nice API Apple.
            image->set_asset_orientation(rep.orientation);
            image->set_scale(rep.scale);
            // We don't resize the image as
            // ALAssetRepresentation.fullResolutionImage appears to be a bit
            // magical and only loads/decompresses the jpeg data as needed to
            // display whatever part of the image is eventually displayed on
            // screen.
          }
          if (jpeg_data || store_jpeg) {
            NSMutableData* tmp_data =
                [[NSMutableData alloc] initWithLength:rep.size];
            uint8_t* dest = reinterpret_cast<uint8_t*>(tmp_data.mutableBytes);
            NSError* error = NULL;
            [rep getBytes:dest fromOffset:0 length:rep.size error:&error];
            if (error) {
              LOG("photo: %s: error reading original jpeg data",
                  p->metadata.id());
              LoadAssetPhotoError(p, ORIGINAL, done);
              return;
            } else {
              if (jpeg_data) {
                *jpeg_data = tmp_data;
              }
              if (store_jpeg) {
                DB::Batch updates;
                const string filename = PhotoOriginalFilename(p->metadata.id());
                if (env_->photo_storage()->Write(
                        filename, tmp_data, &updates)) {
                  env_->db()->Put(updates);
                }
              }
            }
          }
        } else {
          ALAssetRepresentation* rep = [asset defaultRepresentation];
          image->reset([rep fullScreenImage]);
          image->set_scale(rep.scale);
          if (!*image) {
            LOG("photo: %s: full screen image not found: %s",
                p->metadata.id(), asset_key);
            LoadAssetPhotoError(p, FULL, done);
            return;
          } else {
            // LOG("photo: %s: loaded full screen image: %dx%d: %.3f ms",
            //     p->metadata.id(), image->width(), image->height(),
            //     timer.Milliseconds());
            // timer.Restart();

            if (jpeg_data || store_jpeg) {
              NSData* tmp_jpeg_data;
              NSData* __strong* dest_data =
                  jpeg_data ? jpeg_data : &tmp_jpeg_data;
              *dest_data =
                  image->CompressJPEG(NULL, kJpegThumbnailQuality);
              if (store_jpeg) {
                const int load_size = MaxSizeToLoadSize(max_size);
                const string filename = PhotoFilename(p->metadata.id(), load_size);
                DB::Batch updates;
                if (env_->photo_storage()->Write(
                        filename, *dest_data, &updates)) {
                  env_->db()->Put(updates);
                }
              }
            }

            MaybeQueueDetect(p, *image);
            if (image != &tmp_image) {
              if (ResizePhoto(size, image)) {
                // LOG("photo: %s: resized full screen image: %dx%d: %.3f ms",
                //     p->metadata.id(), image->pixel_width(), image->pixel_height(),
                //     timer.Milliseconds());
              }
              if (!*image) {
                LOG("photo: %s: resizing full screen image failed",
                    p->metadata.id());
              }
            }
          }
        }
        if (image != &tmp_image && image) {
          MaybeQueueDetect(p, *image);
        }
        done(false);
      });
  };

  ALAssetsLibraryAccessFailureBlock failure = ^(NSError* error) {
    LOG("photo: %s: loading failed: %s", p->metadata.id(), asset_key);
    async_->dispatch_low_priority(^{
        LoadAssetPhotoError(p, THUMBNAIL|FULL|ORIGINAL, done);
      });
  };

  env_->AssetForKey(asset_key, result, failure);
  return true;
}

void PhotoManager::MaybeWriteThumbnail(PhotoData* p, NSData* jpeg_data) {
  if (!jpeg_data) {
    return;
  }
  DB::Batch updates;
  const string filename = PhotoThumbnailFilename(p->metadata.id());
  if (env_->photo_storage()->Write(filename, jpeg_data, &updates)) {
    env_->db()->Put(updates);
  }
}

void PhotoManager::MaybeQueueDetect(PhotoData* p, const Image& orig_image) {
  if (1 || p->metadata.has_features()) {
    // Detection has already been performed.
    return;
  }
  Image image(orig_image);
  async_->dispatch_after_main(0.0, ^{
      // Access/modify the detect queue on the main thread.
      if (queued_detects_.size() >= kMaxQueuedDetects) {
        // Too many detects queued.
        return;
      }
      Image& queued_image = queued_detects_[p];
      if (queued_image) {
        return;
      }
      if (!image ||
          std::max(image.width(), image.height()) < kMediumSize) {
        // Image is too small to perform detection on, we'll just load it when
        // it comes time to perform detection.
      } else {
        queued_image.reset(image);
        ResizePhoto(CGSizeMake(kMediumSize, kMediumSize), &queued_image);
      }
      MaybeDetect();
    });
}

void PhotoManager::MaybeDetect() {
  if (detect_in_progress_ || queued_detects_.empty()) {
    return;
  }
  PhotoDetectQueue::iterator iter(queued_detects_.begin());
  detect_in_progress_ = iter->first;

  PhotoData* p = detect_in_progress_;
  Image* image = &queued_detects_[p];
  if (!*image) {
    // TODO(pmattis): Handle MaybeLoadInternal() returning false.
    MaybeLoadInternal(
        p, CGSizeMake(kMediumSize, kMediumSize), false, NULL, image, ^{
          async_->dispatch_low_priority(^{
              DetectFeatures(p, image);
            });
        });
  } else {
    async_->dispatch_low_priority(^{
        DetectFeatures(p, image);
      });
  }
}

void PhotoManager::DetectFeatures(PhotoData* p, Image* image) {
  // Create the face detector object lazily as doing so is expensive.
  if (!face_detector_) {
    face_detector_ =
        [CIDetector
           detectorOfType:CIDetectorTypeFace
                  context:NULL
                  options:Dict(CIDetectorAccuracy, CIDetectorAccuracyLow)];
  }

  // Perform the face detection on a background thread.
  WallTimer timer;
  CIImage* cimage = [[CIImage alloc] initWithCGImage:*image];
  const int exif_orientation = image->exif_orientation();
  const Dict options(CIDetectorImageOrientation, exif_orientation);
  const Array cfeatures(
      [face_detector_ featuresInImage:cimage options:options]);
  const float width = image->width();
  const float height = image->height();

  async_->dispatch_main(^{
      // Update the PhotoMetadata on the main thread.
      LOG("photo: %s: %dx%d: detected %d: %.03f ms",
          p->metadata.id(), image->width(), image->height(),
          cfeatures.size(), timer.Milliseconds());
      PhotoMetadata::Features* features = p->metadata.mutable_features();
      for (int i = 0; i < cfeatures.size(); ++i) {
        CIFaceFeature* cf = cfeatures.at<Value>(i);
        PhotoMetadata::Features::Face* face = features->add_faces();
        PhotoMetadata::Features::Rect* b = face->mutable_bounds();
        b->set_x(cf.bounds.origin.x / width);
        b->set_y(cf.bounds.origin.y / height);
        b->set_width(cf.bounds.size.width / width);
        b->set_height(cf.bounds.size.height / height);
        if (cf.hasLeftEyePosition) {
          face->mutable_left_eye()->set_x(cf.leftEyePosition.x / width);
          face->mutable_left_eye()->set_y(cf.leftEyePosition.y / height);
        }
        if (cf.hasRightEyePosition) {
          face->mutable_right_eye()->set_x(cf.rightEyePosition.x / width);
          face->mutable_right_eye()->set_y(cf.rightEyePosition.y / height);
        }
        if (cf.hasMouthPosition) {
          face->mutable_mouth()->set_x(cf.mouthPosition.x / width);
          face->mutable_mouth()->set_y(cf.mouthPosition.y / height);
        }
      }
      // Mark the photo as having feature detection performed.
      env_->db()->PutProto(
          DBFormat::photo_key(p->metadata.id().local_id()), p->metadata);

      queued_detects_.erase(detect_in_progress_);
      detect_in_progress_ = NULL;
      MaybeDetect();
    });
}

// local variables:
// mode: c++
// end:
