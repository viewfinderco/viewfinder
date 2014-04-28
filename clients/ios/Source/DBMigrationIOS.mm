// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AssetsManager.h"
#import "DBMigrationIOS.h"
#import "EpisodeTable.h"
#import "FileUtils.h"
#import "Image.h"
#import "ImageFingerprint.h"
#import "ImageIndex.h"
#import "PhotoStorage.h"
#import "PhotoTable.h"
#import "ServerUtils.h"
#import "Timer.h"
#import "UIAppState.h"

DBMigrationIOS::DBMigrationIOS(UIAppState* state, ProgressUpdateBlock progress_update)
    : DBMigration(state, progress_update),
      state_(state) {
}

DBMigrationIOS::~DBMigrationIOS() {
}

void DBMigrationIOS::RunIOSMigration(
    const char* min_ios_version, const char* max_ios_version,
    const string& migration_key, migration_func migrator,
    const DBHandle& updates) {
  if (min_ios_version && kIOSVersion < min_ios_version) {
    return;
  }
  if (max_ios_version && kIOSVersion >= max_ios_version) {
    return;
  }
  RunMigration(migration_key, migrator, updates);
}

void DBMigrationIOS::RemoveLocalOnlyPhotos(const DBHandle& updates) {
  // Remove local-only photos that have not been uploaded to the server. Such
  // photos cannot be matched against when performing the duplicate detection
  // on the upgrade to iOS 7.
  for (DB::PrefixIterator iter(updates, DBFormat::photo_key());
       iter.Valid();
       iter.Next()) {
    const Slice value = iter.value();
    PhotoMetadata p;
    if (!p.ParseFromString(ToString(value))) {
      continue;
    }
    if (p.has_images() && !p.upload_full()) {
      // The photo has been uploaded to the server (or came to us from the
      // server).
      continue;
    }

    LOG("%s: removing local only photo", p.id());
    PhotoHandle ph = state_->photo_table()->LoadPhoto(p.id().local_id(), updates);
    ph->Lock();
    ph->DeleteAndUnlock(updates);

    // Remove the photo from every episode it is posted to. This causes it to
    // disappear in the UI.
    vector<int64_t> episode_ids;
    state_->episode_table()->ListEpisodes(ph->id().local_id(), &episode_ids, updates);
    for (int i = 0; i < episode_ids.size(); ++i) {
      EpisodeHandle eh = state_->episode_table()->LoadEpisode(episode_ids[i], updates);
      eh->Lock();
      eh->RemovePhoto(ph->id().local_id());
      eh->SaveAndUnlock(updates);
    }
  }
}

void DBMigrationIOS::ConvertAssetFingerprints(const DBHandle& updates) {
  if (!state_->assets_authorized()) {
    return;
  }

  int asset_photo_count = 0;
  for (DB::PrefixIterator iter(updates, DBFormat::asset_fingerprint_key(""));
       iter.Valid();
       iter.Next()) {
    ++asset_photo_count;
  }
  if (asset_photo_count == 0) {
    return;
  }

  WallTimer timer;
  __block int count = 0;

  SimpleAssetScan([ALAssetsLibrary new], ^(ALAsset* asset) {
      const string url = AssetURL(asset);
      if (url.empty()) {
        return;
      }
      const string old_fingerprint = AssetOldFingerprint(asset);
      if (old_fingerprint.empty()) {
        return;
      }

      const string asset_key = EncodeAssetKey(url, old_fingerprint);
      PhotoHandle ph = state_->photo_table()->LoadAssetPhoto(asset_key, updates);
      if (!ph.get()) {
        return;
      }

      const string new_fingerprint = AssetNewFingerprint(asset);
      const string new_asset_key = EncodeAssetKey(url, new_fingerprint);

      ph->Lock();
      google::protobuf::RepeatedPtrField<string> old_asset_keys;
      old_asset_keys.Swap(ph->mutable_asset_keys());
      google::protobuf::RepeatedPtrField<string> old_asset_fingerprints;
      old_asset_fingerprints.Swap(ph->mutable_asset_fingerprints());
      VLOG("%s: added asset key: %s", ph->id(), new_asset_key);
      ph->AddAssetKey(new_asset_key);
      for (int i = 0; i < old_asset_keys.size(); ++i) {
        ph->AddAssetKey(old_asset_keys.Get(i));
      }
      for (int i = 0; i < old_asset_fingerprints.size(); ++i) {
        ph->AddAssetFingerprint(old_asset_fingerprints.Get(i), false);
      }
      ph->SaveAndUnlock(updates);

      ++count;
    });

  LOG("migration: convert asset fingerprints: %d photos, %.1f secs",
      count, timer.Get());
}

void DBMigrationIOS::IndexPhotos(const DBHandle& updates) {
  WallTimer timer;
  int indexed_photos = 0;

  for (DB::PrefixIterator iter(updates, DBFormat::photo_key());
       iter.Valid();
       iter.Next()) {
    const Slice value = iter.value();
    PhotoMetadata p;
    if (!p.ParseFromString(ToString(value))) {
      continue;
    }
    if (p.label_error() ||
        p.asset_fingerprints_size() == 0 ||
        !p.has_images() ||
        p.upload_thumbnail() ||
        p.upload_full()) {
      // Only index non-quarantined photos that the user has uploaded as those
      // are the only photos we can match asset photos against.
      continue;
    }
    if (state_->episode_table()->CountEpisodes(p.id().local_id(), updates) == 0) {
      continue;
    }

    // Generate the perceptual fingerprint from the Viewfinder thumbnail.
    const string filename = PhotoThumbnailFilename(p.id());
    const string path = state_->photo_storage()->PhotoPath(filename);
    if (FileSize(path) <= 0) {
      // We were unable to find a thumbnail. Log a warning and continue
      // on. This might cause an unnecessary duplicate.
      LOG("unable to load: %s", path);
      continue;
    }
    Image image;
    if (!image.Decompress(path, 0, NULL)) {
      // We were unable to decompress the thumbnail. Log a warning and continue
      // on. This might cause an unnecessary duplicate.
      LOG("unable to decompress: %s", path);
      continue;
    }

    PhotoHandle ph = state_->photo_table()->LoadPhoto(p.id().local_id(), updates);
    ph->Lock();
    *ph->mutable_perceptual_fingerprint() =
        FingerprintImage(image, image.aspect_ratio());
    VLOG("%s: perceptual fingerprint: %s", ph->id(), ph->perceptual_fingerprint());
    ++indexed_photos;
    ph->SaveAndUnlock(updates);
  }

  LOG("migration: index photos: %d photos, %.1f secs",
      indexed_photos, timer.Get());
}

void DBMigrationIOS::RemoveAssetDuplicatePhotos(const DBHandle& updates) {
  WallTimer timer;

  // Build up a map from asset fingerprint to photo id.
  std::unordered_map<string, std::set<int64_t> > fingerprint_to_photo_id;
  for (DB::PrefixIterator iter(updates, DBFormat::photo_key());
       iter.Valid();
       iter.Next()) {
    const Slice value = iter.value();
    PhotoMetadata p;
    if (!p.ParseFromString(ToString(value))) {
      continue;
    }
    if (p.asset_fingerprints_size() == 0) {
      continue;
    }

    for (int i = 0; i < p.asset_fingerprints_size(); ++i) {
      const string& fingerprint = p.asset_fingerprints(i);
      if (!IsNewAssetFingerprint(fingerprint)) {
        continue;
      }
      fingerprint_to_photo_id[fingerprint].insert(p.id().local_id());
    }
  }

  std::unordered_set<int64_t> processed_photos;
  int removed_photos = 0;

  for (auto& iter : fingerprint_to_photo_id) {
    const auto& photo_ids = iter.second;
    if (photo_ids.size() == 1) {
      // There is only a single photo with this asset fingerprint. Nothing to
      // do.
      continue;
    }

    vector<PhotoHandle> local_photos;
    vector<PhotoHandle> server_photos;
    for (auto photo_id : photo_ids) {
      PhotoHandle ph = state_->photo_table()->LoadPhoto(photo_id, updates);
      if (!ph.get()) {
        continue;
      }
      if (ph->upload_metadata()) {
        local_photos.push_back(ph);
      } else {
        server_photos.push_back(ph);
      }
    }

    if (local_photos.empty() || server_photos.empty()) {
      // Either we only have local photos or we only have server photos, in
      // either case there is nothing we can do.
      continue;
    }

    // Remove any local-only photos and copy their asset keys to the first
    // server photo.
    const PhotoHandle& server_photo = server_photos[0];
    server_photo->Lock();
    for (const PhotoHandle& local_photo : local_photos) {
      const int64_t local_photo_id = local_photo->id().local_id();
      if (ContainsKey(processed_photos, local_photo_id)) {
        // Not sure how this could happen, but only process a photo for removal
        // once.
        continue;
      }

      vector<int64_t> episode_ids;
      state_->episode_table()->ListEpisodes(local_photo_id, &episode_ids, updates);
      if (episode_ids.size() > 1) {
        LOG("migration: skipping photo %s that is in %d episodes",
            local_photo->id(), episode_ids.size());
        continue;
      }

      processed_photos.insert(local_photo_id);
      LOG("migration: merging duplicate photo %s into %s",
          local_photo->id(), server_photo->id());

      local_photo->Lock();
      for (int i = 0; i < local_photo->asset_keys_size(); ++i) {
        server_photo->AddAssetKey(local_photo->asset_keys(i));
      }
      local_photo->clear_asset_keys();
      local_photo->SaveAndUnlock(updates);

      // Remove the photo from every episode it is posted to. This causes it to
      // disappear in the UI.
      for (int i = 0; i < episode_ids.size(); ++i) {
        EpisodeHandle e = state_->episode_table()->LoadEpisode(episode_ids[i], updates);
        if (!e->InLibrary()) {
          // We only remove from library episodes.
          LOG("migration: not removing %s from non-library episode %s",
              local_photo->id(), e->id());
          continue;
        }
        e->Lock();
        e->RemovePhoto(local_photo_id);
        e->SaveAndUnlock(updates);
      }
      ++removed_photos;
    }
    server_photo->SaveAndUnlock(updates);
  }

  LOG("migration: remove asset duplicate photos: %d, %.1f secs",
      removed_photos, timer.Get());
}

// local variables:
// mode: c++
// end:
