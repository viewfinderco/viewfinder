// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.
//
// PhotoTable maintain the following tables for assets:
//
//   <asset-url>#<asset-fingerprint> -> <local-photo-id>
//   <asset-fingerprint>#<asset-url> -> <local-photo-id>
//
// When an asset is encountered during a scan, we either create a new photo, or
// add the above mappings pointing to an empty string. When we notice an asset
// has been deleted we update the corresponding PhotoMetadata to remove the
// asset-url but leave the asset-fingerprint in place.

#import <re2/re2.h>
#import "AppState.h"
#import "AsyncState.h"
#import "DayTable.h"
#import "GeocodeManager.h"
#import "ImageIndex.h"
#import "LazyStaticPtr.h"
#import "LocationUtils.h"
#import "NetworkQueue.h"
#import "PhotoStorage.h"
#import "PhotoTable.h"
#import "PlacemarkHistogram.h"
#import "PlacemarkTable.h"
#import "ServerUtils.h"
#import "StringUtils.h"
#import "Timer.h"
#import "WallTime.h"

const string PhotoTable::kPhotoDuplicateQueueKeyPrefix = DBFormat::photo_duplicate_queue_key();

namespace {

const int kPhotoFSCKVersion = 3;
const int kUnquarantineVersion = 4;

const int kSecondsInHour = 60 * 60;
const int kSecondsInDay = kSecondsInHour * 24;

const WallTime kURLExpirationSlop = 60;
const string kAssetFingerprintKeyPrefix = DBFormat::asset_fingerprint_key("");
const string kDeprecatedAssetReverseKeyPrefix = DBFormat::deprecated_asset_reverse_key("");
const string kUnquarantineVersionKey = DBFormat::metadata_key("unquarantine_version");

const string kPerceptualFingerprintPrefix = "P";
const int kPerceptualFingerprintBinarySize = 20;
const int kPerceptualFingerprintSize = 29;

// S3 urls look like:
// https://s3/foo?Signature=bar&Expires=1347112861&AWSAccessKeyId=blah
LazyStaticPtr<RE2, const char*> kS3URLRE = {
  ".*[?&]Expires=([0-9]+).*"
};

const DBRegisterKeyIntrospect kPhotoKeyIntrospect(
    DBFormat::photo_key(), NULL, [](Slice value) {
      return DBIntrospect::FormatProto<PhotoMetadata>(value);
    });

const DBRegisterKeyIntrospect kPhotoDuplicateQueueKeyIntrospect(
    PhotoTable::kPhotoDuplicateQueueKeyPrefix,
    [](Slice key) {
      int64_t local_id;
      if (!DecodePhotoDuplicateQueueKey(key, &local_id)) {
        return string();
      }
      return string(Format("%d", local_id));
    }, NULL);

const DBRegisterKeyIntrospect kPhotoServerKeyIntrospect(
    DBFormat::photo_server_key(), NULL, [](Slice value) {
      return value.ToString();
    });

const DBRegisterKeyIntrospect kPhotoURLKey(
    DBFormat::photo_url_key(""), NULL, [](Slice value) {
      return value.ToString();
    });

const DBRegisterKeyIntrospect kAssetKeyIntrospect(
    DBFormat::asset_key(""), NULL, [](Slice value) {
      return value.ToString();
    });

const DBRegisterKeyIntrospect kAssetDeprecatedReverseKeyIntrospect(
    DBFormat::deprecated_asset_reverse_key(""), NULL, [](Slice value) {
      return value.ToString();
    });

const DBRegisterKeyIntrospect kAssetFingerprintKeyIntrospect(
    DBFormat::asset_fingerprint_key(""), NULL, [](Slice value) {
      return value.ToString();
    });

string EncodePhotoURLKey(int64_t id, const string& name) {
  return DBFormat::photo_url_key(Format("%d/%s", id, name));
}

}  // namespace

string EncodeAssetFingerprintKey(const Slice& fingerprint) {
  string s = kAssetFingerprintKeyPrefix;
  fingerprint.AppendToString(&s);
  return s;
}

string EncodePhotoDuplicateQueueKey(int64_t local_id) {
  string s = PhotoTable::kPhotoDuplicateQueueKeyPrefix;
  OrderedCodeEncodeVarint64(&s, local_id);
  return s;
}

string EncodePerceptualFingerprint(const Slice& term) {
  DCHECK_EQ(kPerceptualFingerprintBinarySize, term.size());
  return kPerceptualFingerprintPrefix + Base64Encode(term);
}

bool DecodeAssetFingerprintKey(Slice key, Slice* fingerprint) {
  if (!key.starts_with(kAssetFingerprintKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kAssetFingerprintKeyPrefix.size());
  *fingerprint = key;
  return true;
}

bool DecodePhotoDuplicateQueueKey(Slice key, int64_t* local_id) {
  if (!key.starts_with(PhotoTable::kPhotoDuplicateQueueKeyPrefix)) {
    return false;
  }
  key.remove_prefix(PhotoTable::kPhotoDuplicateQueueKeyPrefix.size());
  *local_id = OrderedCodeDecodeVarint64(&key);
  return true;
}

bool DecodePerceptualFingerprint(Slice fingerprint, string* term) {
  if (fingerprint.size() != kPerceptualFingerprintSize ||
      !fingerprint.starts_with(kPerceptualFingerprintPrefix)) {
    return false;
  }
  fingerprint.remove_prefix(kPerceptualFingerprintPrefix.size());
  if (term) {
    *term = Base64Decode(fingerprint);
  }
  return true;
}

bool DecodeDeprecatedAssetReverseKey(Slice key, Slice* fingerprint, Slice* url) {
  if (!key.starts_with(kDeprecatedAssetReverseKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kDeprecatedAssetReverseKeyPrefix.size());
  const int pos = key.rfind('#');
  if (pos == key.npos) {
    return false;
  }
  if (fingerprint) {
    *fingerprint = key.substr(0, pos);
  }
  if (url) {
    *url = key.substr(pos + 1);
  }
  return true;
}

PhotoTable_Photo::PhotoTable_Photo(AppState* state, const DBHandle& db, int64_t id)
    : state_(state),
      db_(db) {
  mutable_id()->set_local_id(id);
}

void PhotoTable_Photo::MergeFrom(const PhotoMetadata& m) {
  // Some assertions that immutable properties don't change.
  if (episode_id().has_server_id() && m.episode_id().has_server_id()) {
    DCHECK_EQ(episode_id().server_id(), m.episode_id().server_id());
  }
  if (has_user_id() && m.has_user_id()) {
    DCHECK_EQ(user_id(), m.user_id());
  }
  if (has_timestamp() && m.has_timestamp()) {
    // TODO(peter): I have photos in my asset library with timestamps that
    // differ by more than a second from the data stored on the server.
    // DCHECK_EQ(trunc(timestamp()), trunc(m.timestamp()));
  }

  PhotoMetadata::MergeFrom(m);
}

void PhotoTable_Photo::MergeFrom(const ::google::protobuf::Message&) {
  DIE("MergeFrom(Message&) should not be used");
}


int64_t PhotoTable_Photo::GetDeviceId() const {
  if (!id().has_server_id()) {
    return state_->device_id();
  }
  int64_t device_id = 0;
  int64_t dummy_id = 0;
  WallTime dummy_timestamp = 0;
  DecodePhotoId(
      id().server_id(), &device_id, &dummy_id, &dummy_timestamp);
  return device_id;
}

int64_t PhotoTable_Photo::GetUserId() const {
  return has_user_id() ? user_id() : state_->user_id();
}

bool PhotoTable_Photo::GetLocation(Location* loc, Placemark* pm) {
  if (has_location() && loc) {
    loc->CopyFrom(location());
  }
  // If we have a location, but the placemark isn't set, try to
  // reverse geocode.
  // NOTE: there are some photos which have location and placemark
  //   is set, but is empty. Make sure we reverse geocode in this case.
  if (has_location() && (!has_placemark() || !placemark().has_country())) {
    state_->photo_table()->MaybeReverseGeocode(local_id());
    return true;
  }
  if (has_placemark() && pm) {
    pm->CopyFrom(placemark());
  }
  return has_location();
}

string PhotoTable_Photo::FormatLocation(bool shorten) {
  Location location;
  Placemark placemark;
  if (GetLocation(&location, &placemark)) {
    string s;
    state_->placemark_histogram()->FormatLocation(location, placemark, shorten, &s);
    return s;
  }
  return shorten ? "" : "Location Unavailable";
}

string PhotoTable_Photo::GetURL(const string& name) {
  return db_->Get<string>(EncodePhotoURLKey(local_id(), name));
}

string PhotoTable_Photo::GetUnexpiredURL(
    const string& name, const DBHandle& updates) {
  const string url = GetURL(name);
  if (!url.empty()) {
    int expires = 0;
    if (!RE2::FullMatch(url, *kS3URLRE, &expires)) {
      return url;
    }
    if (expires >= WallTime_Now() + kURLExpirationSlop) {
      return url;
    }
    DeleteURL(name, updates);
  }
  return string();
}

void PhotoTable_Photo::SetURL(
    const string& name, const string& url, const DBHandle& updates) {
  updates->Put(EncodePhotoURLKey(local_id(), name), url);
}

void PhotoTable_Photo::DeleteURL(const string& name, const DBHandle& updates) {
  updates->Delete(EncodePhotoURLKey(local_id(), name));
}

bool PhotoTable_Photo::ShouldUpdateTimestamp(WallTime exif_timestamp) {
  const int64_t orig_seconds = trunc(timestamp());
  const int64_t exif_seconds = trunc(exif_timestamp);

  if (fabs(orig_seconds - exif_seconds) < kSecondsInDay &&
      (orig_seconds % kSecondsInHour) == (exif_seconds % kSecondsInHour)) {
    LOG("photo: %s: original (%s) and exif (%s) timestamps [probably] differ as "
        "time zone information is not captured in exif data; ignoring difference "
        "and continuing with original", id(),
        WallTimeFormat("%F %T", timestamp()),
        WallTimeFormat("%F %T", exif_timestamp));
    return false;
  }

  return true;
}

void PhotoTable_Photo::Quarantine(
    const string& reason, const DBHandle& updates) {
  LOG("photo: quarantining %s: %s", id(), reason);

  // Mark the photo as quarantined in the database. This will prevent the photo
  // from reappearing the next time the app starts.
  set_label_error(true);

  // Remove the photo from every episode it is posted to. This causes it to
  // disappear in the UI.
  vector<int64_t> episode_ids;
  state_->episode_table()->ListEpisodes(local_id(), &episode_ids, updates);
  for (int i = 0; i < episode_ids.size(); ++i) {
    EpisodeHandle e = state_->episode_table()->LoadEpisode(episode_ids[i], updates);
    e->Lock();
    e->QuarantinePhoto(local_id());
    e->SaveAndUnlock(updates);
  }
}

void PhotoTable_Photo::Invalidate(const DBHandle& updates) {
  vector<int64_t> episode_ids;
  state_->episode_table()->ListEpisodes(local_id(), &episode_ids, updates);
  for (int i = 0; i < episode_ids.size(); ++i) {
    EpisodeHandle e = state_->episode_table()->LoadEpisode(episode_ids[i], updates);
    if (e.get()) {
      e->Invalidate(updates);
    }
  }
}

bool PhotoTable_Photo::Load() {
  disk_asset_keys_ = GetAssetKeySet();
  disk_perceptual_fingerprint_ = perceptual_fingerprint();
  day_table_fields_ = GetDayTableFields();
  return true;
}

void PhotoTable_Photo::SaveHook(const DBHandle& updates) {
  StringSet asset_keys_set = GetAssetKeySet();
  for (StringSet::iterator it = disk_asset_keys_.begin(); it != disk_asset_keys_.end(); ++it) {
    if (!ContainsKey(asset_keys_set, *it)) {
      updates->Delete(*it);
    }
  }
  disk_asset_keys_ = asset_keys_set;

  for (int i = 0; i < asset_keys_size(); i++) {
    updates->Put(asset_keys(i), local_id());
  }

  if (disk_perceptual_fingerprint_.SerializeAsString() !=
      perceptual_fingerprint().SerializeAsString()) {
    const string id_str = ToString(id().local_id());
    state_->image_index()->Remove(disk_perceptual_fingerprint_, id_str, updates);
    disk_perceptual_fingerprint_ = perceptual_fingerprint();
    state_->image_index()->Add(disk_perceptual_fingerprint_, id_str, updates);

    for (int i = 0; i < disk_perceptual_fingerprint_.terms_size(); ++i) {
      AddAssetFingerprint(EncodePerceptualFingerprint(
                              disk_perceptual_fingerprint_.terms(i)), false);
    }
  }

  for (int i = 0; i < asset_fingerprints_size(); i++) {
    updates->Put(EncodeAssetFingerprintKey(asset_fingerprints(i)), local_id());
  }

  // The "removed" and "unshared" labels affect the post relationship between
  // an episode and a photo. They are only used in client/server communication
  // and should not be persisted to disk.
  clear_label_removed();
  clear_label_unshared();

  if (has_location() && has_placemark() && !placemark_histogram()) {
    set_placemark_histogram(true);
    state_->placemark_histogram()->AddPlacemark(
        placemark(), location(), updates);
  }

  const string new_day_table_fields = GetDayTableFields();
  if (day_table_fields_ != new_day_table_fields) {
    // Only invalidate if the day table fields have changed. Note that we don't
    // have to invalidate the episodes if the day table fields are empty, which
    // indicates that the photo did not previously exist. If the photo was just
    // created the episode it was added to (if any) will have already been
    // invalidated.
    if (!day_table_fields_.empty()) {
      // Invalidate all activities which have shared this photo and all episodes
      // which contain it.
      Invalidate(updates);
    }
    day_table_fields_ = new_day_table_fields;
  }

  // Ugh, PhotoTable_Photo is the base class but PhotoHandle needs a pointer to
  // the superclass.
  typedef ContentTable<PhotoTable_Photo>::Content Content;
  Content* content = reinterpret_cast<Content*>(this);
  state_->net_queue()->QueuePhoto(PhotoHandle(content), updates);

  if (!label_error() && candidate_duplicates_size() > 0) {
    updates->Put(EncodePhotoDuplicateQueueKey(local_id()), string());
    AppState* s = state_;
    updates->AddCommitTrigger("PhotoDuplicateQueue", [s] {
        s->ProcessPhotoDuplicateQueue();
      });
  } else {
    updates->Delete(EncodePhotoDuplicateQueueKey(local_id()));
  }
}

void PhotoTable_Photo::DeleteHook(const DBHandle& updates) {
  for (StringSet::iterator it = disk_asset_keys_.begin(); it != disk_asset_keys_.end(); ++it) {
    updates->Delete(*it);
  }

  if (disk_perceptual_fingerprint_.terms_size() > 0) {
    const string id_str = ToString(id().local_id());
    state_->image_index()->Remove(disk_perceptual_fingerprint_, id_str, updates);
  }

  if (has_location() && has_placemark() && placemark_histogram()) {
    clear_placemark_histogram();
    state_->placemark_histogram()->RemovePlacemark(
        placemark(), location(), updates);
  }

  // Ugh, PhotoTable_Photo is the base class but PhotoHandle needs a pointer to
  // the superclass.
  typedef ContentTable<PhotoTable_Photo>::Content Content;
  Content* content = reinterpret_cast<Content*>(this);
  state_->net_queue()->DequeuePhoto(PhotoHandle(content), updates);

  updates->Delete(EncodePhotoDuplicateQueueKey(local_id()));

  state_->photo_storage()->DeleteAll(local_id(), updates);
}

StringSet PhotoTable_Photo::GetAssetKeySet() const {
  return StringSet(asset_keys().begin(), asset_keys().end());
}

string PhotoTable_Photo::GetDayTableFields() const {
  PhotoMetadata m;
  if (has_id()) {
    m.mutable_id()->CopyFrom(id());
    // The server-id for a photo is set the first time the photo is loaded and
    // its original timestamp is verified. We don't need to perform a day table
    // refresh when that occurs.
    m.mutable_id()->clear_server_id();
  }
  if (has_episode_id()) {
    m.mutable_episode_id()->CopyFrom(episode_id());
  }
  if (has_placemark()) {
    m.mutable_placemark()->CopyFrom(placemark());
  }
  if (has_aspect_ratio()) {
    m.set_aspect_ratio(aspect_ratio());
  }
  if (has_timestamp()) {
    m.set_timestamp(timestamp());
  }
  return m.SerializeAsString();
}

bool PhotoTable_Photo::ShouldAddPhotoToEpisode() const {
  if (!has_aspect_ratio() ||
      std::isnan(aspect_ratio()) ||
      !has_timestamp() ||
      (candidate_duplicates_size() > 0)) {
    // We don't have enough photo metadata to match the photo to an
    // episode. Note that we'll add a photo to an episode before we've
    // downloaded any of the photo images and rely on the prioritization of
    // images needed for the UI.
    return false;
  }
  return true;
}

void PhotoTable_Photo::FindCandidateDuplicates() {
  if (!has_perceptual_fingerprint()) {
    return;
  }
  WallTimer timer;
  StringSet matched_ids;
  state_->image_index()->Search(state_->db(), perceptual_fingerprint(), &matched_ids);
  clear_candidate_duplicates();
  for (StringSet::iterator iter(matched_ids.begin());
       iter != matched_ids.end();
       ++iter) {
    const int64_t local_id = FromString<int64_t>(*iter);
    if (local_id == id().local_id()) {
      // Never consider a photo its own candidate duplicate.
      continue;
    }
    add_candidate_duplicates(local_id);
  }
  if (candidate_duplicates_size() > 0) {
    LOG("photo: %s: %d candidate duplicates (%.2f ms): %s",
        id(), candidate_duplicates_size(), timer.Milliseconds(), matched_ids);
  }
}

bool PhotoTable_Photo::HasAssetUrl() const {
  return asset_keys_size() > 0;
}

bool PhotoTable_Photo::AddAssetKey(const string& asset_key) {
  Slice url;
  Slice fingerprint;
  if (!DecodeAssetKey(asset_key, &url, &fingerprint)) {
    LOG("photo: invalid asset key %s", asset_key);
    return false;
  }

  bool changed = false;
  if (!fingerprint.empty()) {
    changed = AddAssetFingerprint(fingerprint, false);
  }

  DCHECK(!url.empty());  // Shouldn't happen any more, but just in case.
  if (!url.empty()) {
    bool found = false;
    for (int i = 0; i < asset_keys_size(); i++) {
      if (asset_keys(i) == asset_key) {
        found = true;
        break;
      }

      Slice url2, fingerprint2;
      if (!DecodeAssetKey(asset_keys(i), &url2, &fingerprint2)) {
        continue;
      }
      if (url == url2 && !fingerprint.empty() && fingerprint2.empty()) {
        // Upgrade the existing url-only asset key to include the fingerprint.
        set_asset_keys(i, asset_key);
        changed = true;
        found = true;
      }
    }
    if (!found) {
      add_asset_keys(asset_key);
      changed = true;
    }
  }

  return changed;
}

bool PhotoTable_Photo::AddAssetFingerprint(const Slice& fingerprint, bool from_server) {
  for (int i = 0; i < asset_fingerprints_size(); i++) {
    if (asset_fingerprints(i) == fingerprint) {
      return false;
    }
  }
  add_asset_fingerprints(fingerprint.as_string());
  // If the server doesn't know about this fingerprint, upload the metadata.
  if (!from_server) {
    set_update_metadata(true);
  } else {
    string term;
    if (DecodePerceptualFingerprint(fingerprint, &term)) {
      ImageFingerprint* pf = mutable_perceptual_fingerprint();
      for (int i = 0; i < pf->terms_size(); i++) {
        if (pf->terms(i) == term) {
          return true;
        }
      }
      pf->add_terms(term);
    }
  }
  return true;
}

bool PhotoTable_Photo::RemoveAssetKey(const string& asset_key) {
  for (int i = 0; i < asset_keys_size(); i++) {
    if (asset_keys(i) == asset_key) {
      RemoveAssetKeyByIndex(i);
      return true;
    }
  }
  return false;
}

bool PhotoTable_Photo::RemoveAssetKeyByIndex(int index) {
  DCHECK_GE(index, 0);
  DCHECK_LT(index, asset_keys_size());
  if (index < 0 || index >= asset_keys_size()) {
    return false;
  }
  ProtoRepeatedFieldRemoveElement(mutable_asset_keys(), index);
  return true;
}

bool PhotoTable_Photo::InLibrary() {
  return state_->episode_table()->ListLibraryEpisodes(
      id().local_id(), NULL, db_);
}

bool PhotoTable_Photo::MaybeSetServerId() {
  const int64_t device_id = state_->device_id();
  if (id().has_server_id() || !device_id) {
    return false;
  }
  mutable_id()->set_server_id(
      EncodePhotoId(device_id, id().local_id(), timestamp()));
  return true;
}

PhotoTable::PhotoTable(AppState* state)
    : ContentTable<Photo>(state,
                          DBFormat::photo_key(),
                          DBFormat::photo_server_key(),
                          kPhotoFSCKVersion,
                          DBFormat::metadata_key("photo_table_fsck")),
      geocode_in_progress_(0) {
}

PhotoTable::~PhotoTable() {
}

void PhotoTable::Reset() {
}

PhotoHandle PhotoTable::LoadPhoto(const PhotoId& id, const DBHandle& db) {
  PhotoHandle ph;
  if (id.has_local_id()) {
    ph = LoadPhoto(id.local_id(), db);
  }
  if (!ph.get() && id.has_server_id()) {
    ph = LoadPhoto(id.server_id(), db);
  }
  return ph;
}

PhotoHandle PhotoTable::LoadAssetPhoto(
    const Slice& asset_key, const DBHandle& db) {
  const int64_t id = AssetToDeviceId(asset_key, false, db);
  if (id == -1) {
    return ContentHandle();
  }
  return LoadPhoto(id, db);
}

bool PhotoTable::AssetPhotoExists(
    const Slice& url, const Slice& fingerprint, const DBHandle& db) {
  return AssetToDeviceId(url, fingerprint, true, db) != -1;
}

bool PhotoTable::AssetPhotoExists(
    const Slice& asset_key, const DBHandle& db) {
  return AssetToDeviceId(asset_key, true, db) != -1;
}

void PhotoTable::AssetsNotFound(
    const StringSet& not_found, const DBHandle& updates) {
  for (StringSet::const_iterator iter(not_found.begin());
       iter != not_found.end();
       ++iter) {
    const string& url = *iter;
    DCHECK(!url.empty());
    if (url.empty()) {
      // TODO(peter): Perhaps do something slightly more encompassing as far as
      // validation. A super short prefix could still remove a bunch of stuff,
      // though asset-urls currently appear to be a fixed length (78 bytes?).
      continue;
    }

    // Loop over all (there is normally only 1, but might be more if this is
    // the first full scan after asset urls have changed) of the asset-keys
    // with url as a prefix.
    for (DB::PrefixIterator iter(updates, EncodeAssetKey(url, ""));
         iter.Valid();
         iter.Next()) {
      const Slice key = iter.key();
      Slice fingerprint;
      if (!DecodeAssetKey(key, NULL, &fingerprint)) {
        // This shouldn't happen.
        DCHECK(false) << ": unable to decode: " << key;
        continue;
      }

      // Load the associated photo and clear the url from the asset key.
      PhotoHandle ph = LoadAssetPhoto(key, updates);
      if (ph.get()) {
        ph->Lock();
        // Clear the url, but leave the fingerprint.
        ph->RemoveAssetKey(key.as_string());
        if (ph->upload_metadata() && !ph->HasAssetUrl()) {
          // The photo has not been uploaded to the server and only exists
          // locally. The local asset has disappeared. Quarantine.
          ph->Quarantine("garbage collect", updates);
        }
        ph->SaveAndUnlock(updates);
      } else {
        // No asset associated with the key. Nothing to update, just
        // delete.
        updates->Delete(key);
        if (!fingerprint.empty()) {
          updates->Delete(EncodeAssetFingerprintKey(fingerprint));
        }
      }
    }
  }
}

void PhotoTable::DeleteAllImages(int64_t photo_id, const DBHandle& updates) {
  const PhotoHandle ph = LoadPhoto(photo_id, updates);
  LOG("photo table: deleting all images for photo %d", photo_id);
  if (ph.get()) {
    // Clear the download bits: the photo won't ever be displayed in the UI, so
    // there is no need to download any images.
    ph->Lock();
    ph->clear_download_thumbnail();
    ph->clear_download_full();
    ph->clear_download_medium();
    ph->clear_download_original();
    // Clear asset keys from photo metadata, delete from index, and try
    // to delete underlying assets.
    for (int i = 0; i < ph->asset_keys_size(); i++) {
      const string key = ph->asset_keys(i);
      // Clear the url, but leave the fingerprint.
      ph->RemoveAssetKey(key);
      updates->Delete(key);
      state_->DeleteAsset(key);
    }

    ph->SaveAndUnlock(updates);
  }
  state_->photo_storage()->DeleteAll(photo_id, updates);
}

bool PhotoTable::PhotoInLibrary(int64_t photo_id, const DBHandle& db) {
  PhotoHandle ph = LoadPhoto(photo_id, db);
  return ph.get() && ph->InLibrary();
}

bool PhotoTable::IsAssetPhotoEqual(
    const PhotoMetadata& local, const PhotoMetadata& server) {
  std::set<string> local_fingerprints;
  std::set<string> server_fingerprints;
  for (int i = 0; i < local.asset_fingerprints_size(); ++i) {
    local_fingerprints.insert(local.asset_fingerprints(i));
  }
  for (int i = 0; i < server.asset_fingerprints_size(); ++i) {
    server_fingerprints.insert(server.asset_fingerprints(i));
  }

  if (!server_fingerprints.empty()) {
    // If we have an asset fingerprint on the server, only consider the two
    // photos equal if we have the matching fingerprint locally.
    // All photos uploaded since version 1.2 have fingerprints.
    return SetsIntersect(local_fingerprints, server_fingerprints);
  }

  // If we don't have fingerprints, use some crude heuristics to tell if the photo
  // is definitely different, otherwise assume nothing has happened that would
  // cause asset ids to be reused.
  // Unfortunately, most metadata fields are unreliable for this purpose.
  // Photos can losslessly have their orientation fields normalized, and iTunes
  // appears to sometimes alter timestamps based on the current local timezone.

  if (local.has_location() != server.has_location()) {
    // The local photo has a location while the server photo does not (or vice
    // versa). These cannot be the same photo.
    return false;
  }
  if (local.has_location()) {
    if (DistanceBetweenLocations(local.location(), server.location()) > .1) {
      // The local and server photo locations differ too much. These cannot be
      // the same photo.
      return false;
    }
  }
  return true;
}

bool PhotoTable::ReverseGeocode(
    int64_t photo_id, GeocodeCallback completion) {
  // This must always be running on the main thread.
  DCHECK(dispatch_is_main_thread());
  if (!dispatch_is_main_thread()) {
    LOG("cannot reverse geocode except on main thread; this should never happen");
    return false;
  }
  if (!state_->geocode_manager()) {
    return false;
  }
  PhotoHandle p = LoadPhoto(photo_id, state_->db());
  if (!p.get()) {
    LOG("photo: %s is not a valid photo id", photo_id);
    return false;
  }
  // Exit if:
  // - No location set.
  // - Invalid location.
  // - A previous error with placemark was encountered.
  // - We already have a valid placemark.
  if (!p->has_location() ||
      !PlacemarkTable::IsLocationValid(p->location()) ||
      p->error_placemark_invalid() ||
      (p->has_placemark() && PlacemarkTable::IsPlacemarkValid(p->placemark()))) {
    return false;
  }
  VLOG("reverse geocode on location: %s", p->location());

  PlacemarkHandle h = state_->placemark_table()->FindPlacemark(p->location(), state_->db());
  if (h->valid()) {
    // Optimized the reverse geocode out of existence by reusing the placemark
    // for a previously reverse geocoded photo at the same location.
    LOG("reverse geocode photo %d with location: %s, placemark: %s",
        p->id().local_id(), p->location(), *h);
    p->Lock();
    p->mutable_placemark()->CopyFrom(*h);
    DBHandle updates = state_->NewDBTransaction();
    p->SaveAndUnlock(updates);
    updates->Commit();
    return false;
  }

  // Look up the callback set for this location.
  const Location* l = &h->location();
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
    CHECK(state_->geocode_manager()->ReverseGeocode(
              l, [this, p, h, l, callbacks](const Placemark* m) {
                DBHandle updates = state_->NewDBTransaction();
                p->Lock();
                if (m && PlacemarkTable::IsPlacemarkValid(*m)) {
                  h->Lock();
                  h->CopyFrom(*m);
                  h->SaveAndUnlock(updates);
                  p->mutable_placemark()->CopyFrom(*m);
                } else if (m) {
                  // On an invalid placemark, indicate a placemark error so we don't retry.
                  p->set_error_placemark_invalid(true);
                } else {
                  p->mutable_placemark()->Clear();
                }
                p->SaveAndUnlock(updates);
                updates->Commit();
                // Erase from geocode_callback_map_ before running the
                // callbacks because running the callbacks might want to
                // reverse geocode the same placemark again if geocoding
                // failed.
                geocode_callback_map_.erase(l);
                callbacks->Run(p->has_placemark());
                delete callbacks;
              }));
  } else {
    CHECK_GT(callbacks->size(), 1);
  }
  return true;
}

void PhotoTable::MaybeUnquarantinePhoto(
    const PhotoHandle& ph, const DBHandle& updates) {
  vector<int64_t> episode_ids;
  state_->episode_table()->ListEpisodes(ph->id().local_id(), &episode_ids, updates);
  if (episode_ids.empty()) {
    // Try to load original episode.
    episode_ids.push_back(ph->episode_id().local_id());
  }
  int count = 0;
  for (int i = 0; i < episode_ids.size(); ++i) {
    EpisodeHandle eh = state_->episode_table()->LoadEpisode(episode_ids[i], updates);
    if (eh.get()) {
      eh->Lock();
      eh->AddPhoto(ph->id().local_id());
      eh->SaveAndUnlock(updates);
      ++count;
    }
  }
  if (!count) {
    LOG("photo unquarantine: photo %s had no episodes", *ph);
    return;
  }
  LOG("photo unquarantine: resetting error bit on photo %s and "
      "re-posting to %d episodes", *ph, count);
  ph->Lock();
  ph->clear_label_error();
  if (ph->error_upload_thumbnail()) {
    // If we encountered an error uploading the thumbnail, try
    // uploading the metadata again.
    ph->set_upload_metadata(true);
  }
  ph->SaveAndUnlock(updates);
}

void PhotoTable::MaybeUnquarantinePhoto(int64_t photo_id) {
  DBHandle updates = state_->NewDBTransaction();
  PhotoHandle ph = LoadPhoto(photo_id, updates);
  MaybeUnquarantinePhoto(ph, updates);
  updates->Commit();
}

bool PhotoTable::MaybeUnquarantinePhotos(ProgressUpdateBlock progress_update) {
  const int cur_version = state_->db()->Get<int>(kUnquarantineVersionKey, 0);
  if (cur_version >= kUnquarantineVersion) {
    return false;
  }

  if (progress_update) {
    progress_update("Reviving Missing Photos");
  }

  int unquarantines = 0;
  DBHandle updates = state_->NewDBTransaction();
  for (DB::PrefixIterator iter(updates, DBFormat::photo_key());
       iter.Valid();
       iter.Next()) {
    const int64_t ph_id = DecodeContentKey(iter.key());
    PhotoHandle ph = LoadPhoto(ph_id, updates);
    if (ph->label_error()) {
      MaybeUnquarantinePhoto(ph, updates);
      ++unquarantines;
    }
  }

  updates->Put<int>(kUnquarantineVersionKey, kUnquarantineVersion);
  updates->Commit();
  return unquarantines > 0;
}

void PhotoTable::MaybeReverseGeocode(int64_t photo_id) {
  MutexLock l(&mu_);
  if (geocode_in_progress_) {
    return;
  }
  const GeocodeCallback completion = [this](bool success) {
    MutexLock l(&mu_);
    --geocode_in_progress_;
  };
  // Need to run this on a different thread as we can arrive at this
  // point with locks held and PhotoManager::ReverseGeocode may invoke
  // its callback synchronously in case the requested location is in
  // the placemark table.
  state_->async()->dispatch_after_main(
      0, [this, photo_id, completion] {
        if (ReverseGeocode(photo_id, completion)) {
          ++geocode_in_progress_;
        }
      });
}

int64_t PhotoTable::AssetToDeviceId(
    const Slice& url, const Slice& fingerprint,
    bool require_url_match, const DBHandle& db) {
  // Look up the existing mapping for the url.
  int64_t local_id = -1;
  if (!url.empty()) {
    for (DB::PrefixIterator iter(db, EncodeAssetKey(url, ""));
         iter.Valid();
         iter.Next()) {
      Slice existing_url;
      Slice existing_fingerprint;
      if (!DecodeAssetKey(iter.key(), &existing_url, &existing_fingerprint)) {
        // This shouldn't happen.
        DCHECK(false) << ": unable to decode: " << iter.key();
        continue;
      }
      if (require_url_match && url != existing_url) {
        continue;
      }
      if (fingerprint.empty() ||
          existing_fingerprint.empty() ||
          fingerprint == existing_fingerprint) {
        local_id = FromString<int64_t>(iter.value(), -1);
      }
      break;
    }
  }

  if (local_id == -1 && !require_url_match && !fingerprint.empty()) {
    local_id = db->Get<int64_t>(EncodeAssetFingerprintKey(fingerprint), -1);
  }
  return local_id;
}

int64_t PhotoTable::AssetToDeviceId(
    const Slice& asset_key, bool require_url_match,
    const DBHandle& db) {
  Slice url;
  Slice fingerprint;
  if (!DecodeAssetKey(asset_key, &url, &fingerprint)) {
    return false;
  }
  return AssetToDeviceId(url, fingerprint, require_url_match, db);
}

bool PhotoTable::FSCKImpl(int prev_fsck_version, const DBHandle& updates) {
  LOG("FSCK: PhotoTable");
  bool changes = false;

  for (DB::PrefixIterator iter(updates, DBFormat::photo_key());
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const Slice value = iter.value();
    PhotoMetadata pm;
    if (pm.ParseFromArray(value.data(), value.size())) {
      PhotoHandle ph = LoadPhoto(pm.id().local_id(), updates);
      ph->Lock();
      bool save_ph = false;
      if (key != EncodeContentKey(DBFormat::photo_key(), pm.id().local_id())) {
        LOG("FSCK: photo id %d does not equal key %s; deleting key and re-saving",
            pm.id().local_id(), key);
        updates->Delete(key);
        save_ph = true;
      }

      // Check server key mapping.
      if (ph->id().has_server_id()) {
        const string server_key = EncodeContentServerKey(DBFormat::photo_server_key(),
                                                         ph->id().server_id());
        if (!updates->Exists(server_key)) {
          LOG("FSCK: missing photo server key mapping");
          save_ph = true;
        } else {
          const int64_t mapped_local_id = updates->Get<int64_t>(server_key, -1);
          if (mapped_local_id != ph->id().local_id()) {
            LOG("FSCK: photo local id mismatch: %d != %d; deleting existing mapping",
                mapped_local_id, ph->id().local_id());
            updates->Delete(server_key);
            save_ph = true;
          }
        }
      }

      if (ph->shared() && ph->upload_medium()) {
        // Re-save any shared with with a non-uploaded medium resolution
        // image to force it to be re-added to the network queue.
        LOG("FSCK: non-uploaded medium resolution image");
        save_ph = true;
      }

      // Check the asset key index.
      const string local_id_str = ToString(ph->id().local_id());
      for (int i = 0; i < ph->asset_keys_size(); i++) {
        Slice url, fingerprint;
        if (!DecodeAssetKey(ph->asset_keys(i), &url, &fingerprint)) {
          continue;
        }

        string value;
        if (!updates->Get(ph->asset_keys(i), &value)) {
          LOG("FSCK: adding missing asset key index %s for photo %s", ph->asset_keys(i), local_id_str);
          updates->Put(ph->asset_keys(i), local_id_str);
          changes = true;
        } else if (value != local_id_str) {
          LOG("FSCK: removing conflicting asset key %s from photo %s (owned by %s)", ph->asset_keys(i),
              local_id_str, value);
          // Remove it from disk_asset_keys so the save doesn't remove the entry from its owner.
          ph->disk_asset_keys_.erase(ph->asset_keys(i));
          ProtoRepeatedFieldRemoveElement(ph->mutable_asset_keys(), i);
          save_ph = true;
          --i;
          continue;
        }
      }

      // Check the asset fingerprint index.
      for (int i = 0; i < ph->asset_fingerprints_size(); i++) {
        string value;
        const string fp_key = EncodeAssetFingerprintKey(ph->asset_fingerprints(i));
        if (!updates->Get(fp_key, &value)) {
          LOG("FSCK: adding missing asset fingerprint key %s for photo %s", fp_key, local_id_str);
          updates->Put(fp_key, local_id_str);
          changes = true;
        } else if (value != local_id_str) {
          LOG("FSCK: removing conflicting asset fingerprint %s from photo %s (owned by %s)",
              ph->asset_fingerprints(i), local_id_str, value);
          ProtoRepeatedFieldRemoveElement(ph->mutable_asset_fingerprints(), i);
          // If we modified asset fingerprints, the photo metadata needs to be re-uploaded.
          ph->set_update_metadata(true);
          save_ph = true;
          --i;
          continue;
        }
      }

      if (save_ph) {
        LOG("FSCK: rewriting photo %s", *ph);
        ph->SaveAndUnlock(updates);
        changes = true;
      } else {
        ph->Unlock();
      }
    }
  }

  return changes;
}

// local variables:
// mode: c++
// end:
