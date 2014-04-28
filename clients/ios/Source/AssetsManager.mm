// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.
//
// Asset URLS (a.k.a. asset-keys) are not unique. This causes much
// headache. The asset-key is what uniquely identifies an asset in the user's
// asset library (i.e. their Camera Roll and photos synced via iTunes). Assets
// stored on the Camera Roll, or synced from iPhoto (via iTunes) have
// asset-keys that look like:
//
//   ...id=DB556431-8F4E-43F5-9AEC-2EC76977265B...
//
// The "id" portion of the string appears to be a UUID. This is all good and
// was the basis for my initial assumptions regarding asset-keys. The problem
// is with assets added to the phone by telling iTunes to sync with a
// particular folder. Such assets have asset-keys that look like:
//
//   ...id=00000000-0000-0000-0000-000000000065...
//
// The id is a hex string. The first photo synced appears to always start with
// the value 65. Subsequent photos get sequentially increasing values (e.g. 66,
// 67, etc). If user adds photos to this folder and syncs again the id keeps
// increasing and everything is ok. The headache occurs if the user selects a
// different folder to sync with. For example, if I sync with a folder "Foo"
// with a single image in it I'll get an asset with the key:
//
//   ...id=00000000-0000-0000-0000-000000000065...
//
// If I then change the folder I sync with to "Bar" that contains a single
// image we'll see an asset with the same key:
//
//   ...id=00000000-0000-0000-0000-000000000065...
//
// When scanning through the assets library, there are 4 scenarios to consider:
//
//   1. We've encountered a new asset-key which corresponds to a new photo.
//
//   2. We've encountered a new asset-key which corresponds to a photo we've
//   seen before. This is possible when the user syncs to a folder with iTunes.
//
//   3. We've encountered an existing asset-key which corresponds to a photo
//   we've previously seen.
//
//   4. We've encountered an existing asset-key which corresponds to a new
//   photo.
//
// So the asset-key is essentially useless in determining if we've seen a photo
// before or not. Enter the asset-fingerprint. The SHA1 of the
// ALAsset.aspectRatioThumbnail data. This is somewhat costly to compute (~1
// ms) per asset, but gives us an excellent identity for the asset.

#import <deque>
#import <libkern/OSAtomic.h>
#import <UIKit/UIAlertView.h>
#import <UIKit/UIDevice.h>
#import "Analytics.h"
#import "AssetsManager.h"
#import "AsyncState.h"
#import "DB.h"
#import "LocationTracker.h"
#import "Logging.h"
#import "PhotoManager.h"
#import "PhotoMetadata.pb.h"
#import "PhotoTable.h"
#import "ServerUtils.h"
#import "STLUtils.h"
#import "StringUtils.h"
#import "Timer.h"
#import "UIAppState.h"

namespace {

typedef std::vector<ALAssetsGroup*> GroupVec;

const string kFormatKey = DBFormat::metadata_key("assets_format");
const string kFormatValue = "2";
const string kLastFullScanKey = DBFormat::metadata_key("last_full_asset_scan");
const string kAssetCountKey = DBFormat::metadata_key("asset_count");
const string kAssetDeletionKeyPrefix = DBFormat::asset_deletion_key("");
const WallTime kDay = 24 * 60 * 60;
const int kGroupScanConcurrency = 1;
const int kAssetScanConcurrency = 2;
const int kOldAssetFingerprintSize = 40;
const int kNewAssetFingerprintSize = 41;

// All asset library permissions Viewfinder is interested in.
// Types of assets to load. We ignore:
// - ALAssetsGroupFaces
// - ALAssetsGroupPhotoStream
// - ALAssetsGroupLibrary
//   - Note that ALAssetsGroupLibrary is a special group that includes all
//     assets on the device. But we're already getting all of the assets via
//     the "album", "event" and "saved photos" groups.
ALAssetsGroupType kAssetGroupTypes = (ALAssetsGroupAlbum |
                                      ALAssetsGroupEvent |
                                      ALAssetsGroupSavedPhotos);

// iOS asks for both location and asset library permission when the user first
// accesses the assets library.
CLAuthorizationStatus LocationManagerAuthorizationStatus() {
  return [CLLocationManager authorizationStatus];
}

ALAuthorizationStatus AssetsLibraryAuthorizationStatus() {
  return [ALAssetsLibrary authorizationStatus];
}

bool AuthorizationFailed() {
  if (kIOSVersion < "6.0") {
    return (LocationManagerAuthorizationStatus() == kCLAuthorizationStatusDenied ||
            LocationManagerAuthorizationStatus() == kCLAuthorizationStatusRestricted);
  } else {
    return (AssetsLibraryAuthorizationStatus() == ALAuthorizationStatusDenied ||
            AssetsLibraryAuthorizationStatus() == ALAuthorizationStatusRestricted);
  }
}

bool AuthorizationNotDetermined() {
  if (kIOSVersion < "6.0") {
    return (LocationManagerAuthorizationStatus() ==
            kCLAuthorizationStatusNotDetermined);
  } else {
    return (AssetsLibraryAuthorizationStatus() ==
            ALAuthorizationStatusNotDetermined);
  }
}

string AssetNewFingerprint(CGImageRef image) {
  return "N" + ImageSHA1Fingerprint(image);
}

void ScanAssetsByUrl(UIAppState* state, ALAssetsLibrary* library, NSEnumerator* asset_enumerator) {
  NSURL* url = asset_enumerator.nextObject;
  if (!url) {
    return;
  }
  [library assetForURL:url
           resultBlock:^(ALAsset* asset) {
      CGImageRef square_thumbnail = asset.thumbnail;
      const string fingerprint = AssetNewFingerprint(square_thumbnail);
      if (fingerprint.empty()) {
        ScanAssetsByUrl(state, library, asset_enumerator);
        return;
      }
      const AssetScanData data(
          asset, EncodeAssetKey(ToString(url), fingerprint),
          1, square_thumbnail);
      dispatch_low_priority(^{
          state->assets_scan_progress()->Run(data);
          ScanAssetsByUrl(state, library, asset_enumerator);
        });
    }
          failureBlock:^(NSError* error) {
      LOG("assets: error loading asset %s: %s", url, error);
      ScanAssetsByUrl(state, library, asset_enumerator);
    }
   ];
};

}  // namespace


bool IsOldAssetFingerprint(const Slice& fingerprint) {
  return fingerprint.size() == kOldAssetFingerprintSize;
}

bool IsNewAssetFingerprint(const Slice& fingerprint) {
  return fingerprint.size() == kNewAssetFingerprintSize &&
      fingerprint[0] == 'N';
}

string AssetOldFingerprint(ALAsset* asset) {
  return ImageSHA1Fingerprint([asset aspectRatioThumbnail]);
}

string AssetNewFingerprint(ALAsset* asset) {
  return AssetNewFingerprint([asset thumbnail]);
}

string AssetURL(ALAsset* asset) {
  NSURL* url = (kIOSVersion >= "6.0") ?
      [asset valueForProperty:ALAssetPropertyAssetURL] :
      [asset defaultRepresentation].url;
  return ToString(url);
}


void SimpleAssetScan(
    ALAssetsLibrary* library, void (^callback)(ALAsset* asset)) {
  Barrier* barrier = new Barrier(1);
  __block vector<Barrier*> group_barriers;

  [library
    enumerateGroupsWithTypes:kAssetGroupTypes
                  usingBlock:^(ALAssetsGroup* group, BOOL* stop) {
      if (!group) {
        // Wait for all of the group scans to finish.
        for (int i = 0; i < group_barriers.size(); ++i) {
          group_barriers[i]->Wait();
          delete group_barriers[i];
        }
        barrier->Signal();
        return;
      }

      [group setAssetsFilter:[ALAssetsFilter allPhotos]];
      Barrier* group_barrier = new Barrier(1);
      group_barriers.push_back(group_barrier);

      [group enumerateAssetsWithOptions:NSEnumerationReverse
                             usingBlock:^(ALAsset* asset, NSUInteger index, BOOL* stop) {
          @autoreleasepool {
            if (!asset) {
              group_barrier->Signal();
              return;
            }
            callback(asset);
          }
        }];
    }
                failureBlock:^(NSError* error) {
      LOG("%s", error);
    }];

  barrier->Wait();
  delete barrier;
}


AssetMap::AssetMap(ALAssetsLibrary* library)
  : library_(library ? library : [ALAssetsLibrary new]) {
}

void AssetMap::Scan() {
  clear();
  SimpleAssetScan(library_, ^(ALAsset* asset) {
      (*this)[AssetURL(asset)] = asset;
    });
}

@interface AssetsManager (internal)
- (void)assetsChanged;
- (void)forceScan:(bool)full_scan_ok;
- (void)scanLocked:(bool)full_scan_ok;
- (void)maybeProcessDeletionQueue;
- (void)scanCompleted:(const AssetSet&)scanned_assets withGroups:(const AssetGroupMap&)asset_groups;
@end  // AssetsManager (internal)

@interface AssetsScanState : NSObject {
 @private
  Mutex mu_;
  UIAppState* state_;
  AssetsManager* assets_manager_;
  StringSet not_found_;
  // The set of previously-existing asset groups, loaded from the db to detect deletion.
  StringSet asset_group_ids_;
  // The set of currently-existing asset groups, populated as we enumerate them.
  AssetGroupMap asset_groups_;
  std::deque<ALAssetsGroup*> pending_groups_;
  int32_t inflight_groups_;
  bool full_scan_;
  volatile bool cancelled_;
  int scanning_;
  int32_t asset_index_;
  int32_t total_assets_;
  int32_t inflight_assets_;
  AssetSet scanned_assets_;
  WallTimer timer_;
}

- (id)initWithState:(UIAppState*)state
      assetsManager:(AssetsManager*)assets_manager
           fullScan:(bool)full_scan;
- (void)scanStart;
- (void)scanStartInternal;
- (void)scanGroup:(ALAssetsGroup*)group;
- (void)scanCancel;
- (void)scanDone;

@end  // AssetsScanState

@implementation AssetsScanState

- (id)initWithState:(UIAppState*)state
      assetsManager:(AssetsManager*)assets_manager
           fullScan:(bool)full_scan {
  if (self = [super init]) {
    state_ = state;
    assets_manager_ = assets_manager;
    full_scan_ = full_scan;
  }
  return self;
}

- (void)scanStart {
  if (!state_->async()->Enter()) {
    return;
  }
  scanning_ = 1;
  dispatch_low_priority(^{
      [self scanStartInternal];
    });
}

- (void)scanStartInternal {
  state_->assets_scan_start()->Run();

  WallTimer timer;
  if (full_scan_) {
    // If we're doing a full scan, build up a list of the assets that are
    // not found during the scan. We initialize a set with all of the
    // assets we've previously seen.
    //
    // TODO(pmattis): not_found might get fairly large. We should store it
    // in leveldb at some point.
    for (DB::PrefixIterator iter(state_->db(), DBFormat::asset_key(""));
         iter.Valid();
         iter.Next()) {
      Slice url;
      if (!DecodeAssetKey(iter.key(), &url, NULL)) {
        // This shouldn't happen.
        DCHECK(false) << ": unable to decode: " << iter.key();
        continue;
      }
      if (!url.empty()) {
        not_found_.insert(url.ToString());
      }
    }
  }

  // List out all of the asset groups we saw in the previous scan.
  for (DB::PrefixIterator iter(state_->db(), kAssetCountKey);
       iter.Valid();
       iter.Next()) {
    const Slice group_id(iter.key().substr(kAssetCountKey.size() + 1));
    asset_group_ids_.insert(group_id.ToString());
  }

  __block int group_count = 0;
  [assets_manager_.assetsLibrary
      enumerateGroupsWithTypes:kAssetGroupTypes
      usingBlock:^(ALAssetsGroup* group, BOOL* stop) {
      if (!group) {
        LOG("assets: scanned %d group%s: %.03f ms",
            group_count, Pluralize(group_count), timer.Milliseconds());
        [self scanDone];
        return;
      }
      [self scanGroup:group];
      ++group_count;
    }
     failureBlock:^(NSError* error) {
      LOG("assets: scan error: %@", error);
      [self scanDone];
    }];
}

- (void)scanGroup:(ALAssetsGroup*)group {
  // When an asset library changed notification is received, all of the
  // associated ALAsset* objects are invalidated immediately. Once invalided,
  // method calls on such objects seem to disappear into the ether. So be
  // careful to not call any ALAsset* object methods when holding mu_.
  const string group_id =
      ToString([group valueForProperty:ALAssetsGroupPropertyPersistentID]);

  const ALAssetsGroupType group_type = ((NSNumber*)[group valueForProperty:ALAssetsGroupPropertyType]).intValue;

  MutexLock l(&mu_);
  scanning_ += 1;
  asset_group_ids_.erase(group_id);
  asset_groups_[group_id] = group;
  // The camera roll is most likely to contain changes, so always put it at the front of the list
  // (it always seems to come last when enumerating groups).
  // Group types are specified as a bitmask, although in practice only one bit seems to be set at a time.
  if (group_type & ALAssetsGroupSavedPhotos) {
    pending_groups_.push_front(group);
  } else {
    pending_groups_.push_back(group);
  }
  [self scanGroupBeginLocked];
}

- (void)scanGroupBeginLocked {
  CHECK(!pending_groups_.empty());
  if (inflight_groups_ >= kGroupScanConcurrency) {
    return;
  }

  ALAssetsGroup* group = pending_groups_.front();
  pending_groups_.pop_front();
  ++inflight_groups_;

  dispatch_low_priority(^{
      WallTimer timer;
      state_->assets_scan_group()->Run();

      // Set the asset filter before calling [ALAssetsGroup numberOfAssets] so
      // that the call reflects the number of assets that match the filter.
      [group setAssetsFilter:[ALAssetsFilter allPhotos]];

      const string group_id =
          ToString([group valueForProperty:ALAssetsGroupPropertyPersistentID]);
      const string group_name =
          ToString([group valueForProperty:ALAssetsGroupPropertyName]);
      const int old_asset_count = state_->db()->Get<int>(
          Format("%s/%s", kAssetCountKey, group_id));
      const int new_asset_count = [group numberOfAssets];
      const int delta_asset_count = new_asset_count - old_asset_count;
      OSAtomicAdd32(new_asset_count, &total_assets_);

      __block int asset_count = 0;
      ALAssetsGroupEnumerationResultsBlock asset_block =
          ^(ALAsset* asset, NSUInteger index, BOOL* stop) {
        if (index == NSNotFound) {
          LOG("assets: scanned (%s) \"%s\": %d (%d): %.03f sec",
              full_scan_ ? "full" : "quick", group_name,
              asset_count, new_asset_count, timer.Get());
          state_->db()->Put<int>(
              Format("%s/%s", kAssetCountKey, group_id),
              new_asset_count);
          [self scanGroupEnd];
          return;
        }

        if (cancelled_) {
          *stop = YES;
          return;
        }

        ++asset_count;
        CGImageRef square_thumbnail = [asset thumbnail];
        const string fingerprint = AssetNewFingerprint(square_thumbnail);
        if (fingerprint.empty()) {
          // We couldn't fingerprint the asset if we couldn't retrieve the
          // thumbnail. Skip for now.
          return;
        }

        const string url = AssetURL(asset);
        if (url.empty()) {
          // This can happen when an asset library changed notification has
          // been received.
          return;
        }
        if (!full_scan_) {
          const bool exists = state_->photo_table()->AssetPhotoExists(
              url, fingerprint, state_->db());
          if (exists) {
            // During a quick scan, keep track of the number of new assets. If the
            // number of new assets exceeds the change in asset count, stop the
            // scan.
            --asset_count;
            if (asset_count >= delta_asset_count) {
              *stop = YES;
              return;
            }
          }
        } else {
          not_found_.erase(url);
        }

        const AssetScanData data(
            asset, EncodeAssetKey(url, fingerprint),
            OSAtomicIncrement32(&asset_index_), square_thumbnail);

        {
          // TODO(peter): The scanned_assets_ structure might get fairly
          // large. Perhaps look into ways that it can be compressed. For
          // example, the asset urls have lots of repetition. Prefix
          // compression would work wonders. Just sticking this data structure
          // in leveldb might be the best option.
          MutexLock l(&mu_);
          scanned_assets_.insert(data.asset_key);
        }

        [self scanAssetBegin];
        dispatch_low_priority(^{
            state_->assets_scan_progress()->Run(data);
            [self scanAssetEnd];
          });
      };

      // Scan in reverse so that we can stop the scan when we reach an asset
      // we've already seen. Note that forward scans seem to be ever so
      // slightly faster than reverse scans, but the speed difference due to
      // the scan direction is overwhelmed by the other processing that occurs
      // during scanning.
      LOG("assets: scanning \"%s\": %d -> %d",
          group_name, old_asset_count, new_asset_count);
      [group enumerateAssetsWithOptions:NSEnumerationReverse
                             usingBlock:asset_block];
  });
}

- (void)scanGroupEnd {
  {
    MutexLock l(&mu_);
    CHECK_GT(inflight_groups_, 0);
    --inflight_groups_;
    if (!pending_groups_.empty()) {
      // If there is another group to scan, avoid the call to scanDone.
      CHECK_GT(scanning_, 1);
      --scanning_;
      [self scanGroupBeginLocked];
      return;
    }
  }

  [self scanDone];
}

- (void)scanAssetBegin {
  MutexLock l(&mu_);
  mu_.Wait(^{
      return inflight_assets_ < kAssetScanConcurrency;
    });
  ++inflight_assets_;
  ++scanning_;
}

- (void)scanAssetEnd {
  {
    MutexLock l(&mu_);
    --inflight_assets_;
    if (scanning_ > 1) {
      --scanning_;
      return;
    }
  }
  [self scanDone];
}

- (void)scanCancel {
  MutexLock l(&mu_);
  cancelled_ = true;
}

- (void)scanDone {
  bool new_scan = false;

  {
    MutexLock l(&mu_);
    CHECK_GT(scanning_, 0);
    scanning_ -= 1;
    if (scanning_ > 0) {
      return;
    }
    if (cancelled_) {
      LOG("assets: scan cancelled");
      state_->async()->Exit();
      return;
    }
    if (full_scan_) {
      // If this was the initial asset scan, kick-off a new scan when we
      // complete in order to pick up any changes that we missed due to not
      // having installed the assets library changed notification yet.
      new_scan = assets_manager_.initialScan;
      state_->db()->Put(kFormatKey, kFormatValue);
      state_->db()->Put(kLastFullScanKey, WallTime_Now());

      DBHandle updates = state_->NewDBTransaction();
      state_->photo_table()->AssetsNotFound(not_found_, updates);
      updates->Commit();
    } else {  // !full_scan_
      if (!asset_group_ids_.empty()) {
        // Some asset groups existed in our database but we didn't see them in the scan;
        // trigger a full scan to clean up any deleted assets.
        DBHandle updates = state_->NewDBTransaction();
        for (StringSet::iterator iter(asset_group_ids_.begin());
             iter != asset_group_ids_.end();
             ++iter) {
          LOG("assets: group disappeared: \"%s\"", *iter);
          updates->Delete(Format("%s/%s", kAssetCountKey, *iter));
        }

        // Force a full scan.
        updates->Put(kLastFullScanKey, 0);
        updates->Commit();
      }

      // If we're due for a full scan, start it now.
      const WallTime last_full_scan = state_->db()->Get<WallTime>(kLastFullScanKey);
      new_scan = ((WallTime_Now() - last_full_scan) >= kDay);
    }
  }

  // Make sure we're not holding the mutex when we invoke the assets_scan_end
  // callbacks because these callbacks might call into
  // AssetsManager. AssetsManager::mu_ always has to be locked before
  // AssetsScanState::mu_ or deadlock can result.
  state_->assets_scan_end()->Run(full_scan_ ? &not_found_ : NULL);
  state_->analytics()->AssetsScan(
      full_scan_, total_assets_, asset_index_, timer_.Get());

  // Process the asset deletion queue whenever a scan ends.
  [assets_manager_ scanCompleted:scanned_assets_ withGroups:asset_groups_];

  if (new_scan) {
    // Kick off the new scan after this method returns so that the lock is
    // released and we don't deadlock in scanCancel.
    dispatch_low_priority(^{
        [assets_manager_ forceScan:true];
      });
  }

  state_->async()->Exit();
}

@end  // AssetsScanState

@implementation AssetsManager

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;

    [self cacheAssetsAuthorization];

    // We sometimes do not receive an assets library changed notification when
    // the app becomes active. This occurs frequently on iOS 7. So force a scan
    // whenever the app becomes active. This is mildly complicated by not
    // wanting to perform an extra scan if we do receive an assets library
    // changed notification. The solution is to delay the scan for 300 ms and
    // to cancel any delayed scan if an assets library changed notification
    // arrives.
    state_->app_did_become_active()->Add(^{
        const bool old_authorized = self.authorized;
        [self cacheAssetsAuthorization];

        if (state_->view_state() == STATE_ACCOUNT_SETUP ||
            state_->view_state() == STATE_OK) {
          if (old_authorized != state_->assets_authorized()) {
            // If we're transitioning out of the assets not determined or not
            // authorized states and assets access has been authorized, kick off
            // a scan.
            [self scan];
          } else if (num_scans_ > 0) {
            [self delayedScan];
          }
        }
      });
    state_->app_will_resign_active()->Add(^{
        if (state_->view_state() == STATE_OK) {
          [self cancelDelayedScan];
        }
      });
  }
  return self;
}

- (void)cacheAssetsAuthorization {
  // Cache whether authorization has been determined and whether it has
  // failed. We access these values frequently when switching between the
  // dashboard/library/inbox and the ALAssetsLibrary methods do locking
  // internally that appears to offer the potential for deadlock.
  cached_authorization_determined_ = !AuthorizationNotDetermined();
  if (cached_authorization_determined_) {
    cached_authorization_failed_ = AuthorizationFailed();
  } else {
    cached_authorization_failed_ = true;
  }
  VLOG("assets authorization: determined=%d failed=%d",
       int(cached_authorization_determined_),
       int(cached_authorization_failed_));
}

- (ALAssetsLibrary*)assetsLibrary {
  MutexLock l(&mu_);
  if (!assets_library_) {
    if (kIOSVersion >= "6.0") {
      // Turns off notifications from shared photo streams.
      [ALAssetsLibrary disableSharedPhotoStreamsSupport];
    }
    assets_library_ = [ALAssetsLibrary new];

    dispatch_main(^{
        [self maybeAddChangedNotification];
      });
  }
  return assets_library_;
}

- (bool)authorizationDetermined {
  return cached_authorization_determined_;
}

- (bool)authorized {
  return self.authorizationDetermined &&
      !cached_authorization_failed_;
}

- (void)maybeAddChangedNotification {
  if (installed_changed_notification_) {
    return;
  }
  if (self.initialScan) {
    // Do not add the assets library changed notification until the initial
    // asset scan is complete. This prevents asset library changes (e.g. the
    // user taking a screenshot) from restarting the scan.
    return;
  }

  [[NSNotificationCenter defaultCenter]
          addObserver:self
             selector:@selector(assetsChanged:)
                 name:ALAssetsLibraryChangedNotification
               object:assets_library_];

  installed_changed_notification_ = true;
}

- (bool)fullScan {
  MutexLock l(&mu_);
  return full_scan_;
}

- (bool)initialScan {
  return !state_->db()->Exists(kLastFullScanKey);
}

- (bool)scanning {
  MutexLock l(&mu_);
  return current_scan_ != NULL;
}

- (int)numScans {
  MutexLock l(&mu_);
  return num_scans_;
}

- (int)numScansCompleted {
  MutexLock l(&mu_);
  return num_scans_completed_;
}

- (void)assetsChanged:(NSNotification*)n {
  LOG("assets: library changed");

  if (!stopped_) {
    state_->assets_changed()->Run();
  }

  // Need to clear the verified asset set immediately as the assets changed
  // notification invalidates all of the ALAsset* pointers and we'll need to
  // re-verify asset fingerprints.
  mu_.Lock();
  verified_assets_.clear();
  mu_.Unlock();

  // If the notification gives us a list of asset urls, just process those.
  // The UpdatedAssetsKey includes both new and updated assets.
  // The UpdatedAssetGroupsKey does not appear to be set when a new asset is inserted, even
  // though the docs say it should be.  It does however appear to be set for deletions.
  // TODO(ben): Verify this behavior and use ALAssetLibraryUpdatedAssetGroupsKey to trigger a
  // full scan of the affected groups.
  NSSet *updated_assets = [n.userInfo objectForKey:ALAssetLibraryUpdatedAssetsKey];
  if (updated_assets.count > 0) {
    LOG("assets: scanning %d urls from notification", updated_assets.count);
    // No need to do our usual on-becoming-active scan if we got a notification as we woke up.
    [self cancelDelayedScan];
    ScanAssetsByUrl(state_, assets_library_, updated_assets.objectEnumerator);
  } else {
    // No usable information in the notification; kick off a new quick scan.
    [self forceScan:false];
  }
}

- (void)forceScan:(bool)full_scan_ok {
  [self cancelDelayedScan];

  MutexLock l(&mu_);
  if (current_scan_) {
    [current_scan_ scanCancel];
  }
  // The assets library will often send multiple changed notifications one
  // after the other. We don't want to kick off and cancel multiple
  // scans. Instead, we wait 100ms after the last change notification to start
  // a new scan.
  const int64_t scan_id = ++next_scan_id_;
  dispatch_after_low_priority(0.1, ^{
      MutexLock l(&mu_);
      if (scan_id != next_scan_id_) {
        return;
      }
      [self scanLocked:full_scan_ok];
    });
}

- (void)scanLocked:(bool)full_scan_ok {
  if (current_scan_) {
    [current_scan_ scanCancel];
  }
  if (stopped_) {
    return;
  }

  // Do nothing if we're not authorized.
  if (!self.authorized) {
    return;
  }

  const bool format_changed =
      (state_->db()->Get<string>(kFormatKey) != kFormatValue);
  const WallTime last_full_scan = state_->db()->Get<WallTime>(kLastFullScanKey);
  // If the database is empty or in an old format, we must do a full scan.
  full_scan_ = format_changed;
  if (!full_scan_ && full_scan_ok) {
    // Otherwise do full scans once a day, but the first scan after the app
    // launches should be quick so we can discover photos taken outside the
    // app.
    if (num_scans_completed_ > 0 && (WallTime_Now() - last_full_scan) >= kDay) {
      full_scan_ = true;
    }
  }

  LOG("assets: library scan (%s%s): last full scan: %s",
      full_scan_ ? "full" : "quick",
      format_changed ? " upgrade" : "",
      WallTimeFormat("%F %T", last_full_scan));

  num_scans_ += 1;
  AssetsScanState* scan =
      [[AssetsScanState alloc] initWithState:state_
                               assetsManager:self
                                    fullScan:full_scan_];
  current_scan_ = scan;
  [scan scanStart];
}

- (void)delayedScan {
  [self cancelDelayedScan];
  [self performSelector:@selector(scan)
             withObject:NULL
             afterDelay:0.3];
}

- (void)cancelDelayedScan {
  [NSObject cancelPreviousPerformRequestsWithTarget:self
                                           selector:@selector(scan)
                                             object:NULL];
}

- (void)authorize {
  DCHECK(AuthorizationNotDetermined());
  if (kIOSVersion < "6.0") {
    [state_->location_tracker() ensureInitialized];
  } else {
    // Note that simply performing any ALAssetsLibrary call is what
    // forces the authorization to be determined.
    [self.assetsLibrary
        enumerateGroupsWithTypes:kAssetGroupTypes
                      usingBlock:^(ALAssetsGroup* group, BOOL* stop) {
        *stop = YES;
      }
                    failureBlock:^(NSError* error) {
        LOG("assets: authorization error: %@", error);
      }];
  }
}

- (void)scan {
  [self cancelDelayedScan];

  MutexLock l(&mu_);
  if (!current_scan_) {
    [self scanLocked:true];
  }
}

- (void)scanCompleted:(const AssetSet&)scanned_assets withGroups:(const AssetGroupMap&)asset_groups {
  dispatch_main(^{
      [self maybeAddChangedNotification];
    });

  [self maybeProcessDeletionQueue];

  MutexLock l(&mu_);
  num_scans_completed_++;
  verified_assets_.insert(scanned_assets.begin(), scanned_assets.end());

  // ALAssetsLibrary only sends change notifications for assets in groups that it thinks you care about,
  // as determined by whether you retain a reference to the group object.  Once a scan finishes,
  // hang on to those groups until the next scan.
  asset_groups_ = asset_groups;
}

- (void)stop {
  MutexLock l(&mu_);
  stopped_ = true;

  if (installed_changed_notification_) {
    installed_changed_notification_ = false;
    [[NSNotificationCenter defaultCenter] removeObserver:self];
    // There is an almost unavoidable race in NSNotificationCenter notification
    // processing. The NSNotificationCenter maintains a weak reference to
    // AssetsManager that is removed by the call to removeObserver. But if a
    // notification is "in flight", it will still be delivered after
    // removeObserver completes. We hack around the race (which only occurs in
    // test code), by maintaining a reference to the AssetsManager for a
    // handful of seconds after it has been removed from the notification center.
    __block AssetsManager* self_ref = self;
    dispatch_after_main(5, ^{
        self_ref = NULL;
      });
  }

  // Cancel any existing scan and wait for it to finish. Note Objective-C
  // guarantees this is safe even if current_scan_ is NULL.
  [current_scan_ scanCancel];
}

- (void)assetForKey:(const string&)key
        resultBlock:(ALAssetsLibraryAssetForURLResultBlock)result
       failureBlock:(ALAssetsLibraryAccessFailureBlock)failure {
  // TODO(peter): [ALAssetsLibrary assetForURL] is horribly slow. Instead of
  // the verified_assets_ hack, we should avoid calling assetForURL at
  // all. During an asset scan we can build up an
  // unordered_map<string,ALAsset*> and then install this asset map when the
  // scan is complete. The tricky part is an assetsChanged notification needs
  // to clear the map.

  const string asset_key(key);
  Slice url;
  Slice fingerprint;
  if (!DecodeAssetKey(key, &url, &fingerprint)) {
    DCHECK(false) << ": unable to decode key: " << key;
    failure(NULL);
    return;
  }
  const string expected_fingerprint = fingerprint.ToString();

  WallTimer timer;
  [self.assetsLibrary assetForURL:NewNSURL(url)
                      resultBlock:^(ALAsset* asset) {
      state_->async()->dispatch_low_priority(^{
          if (!asset){
            result(NULL);
            return;
          }

          mu_.Lock();
          if (!ContainsKey(verified_assets_, asset_key)) {
            // Re-validate the fingerprint. Asset urls can get reused when
            // itunes/iphoto syncing settings are changed (see comments at top of
            // AssetsManager.mm), so we must fingerprint the photo we just loaded
            // to make sure it's the same. A full assets scan will eventually
            // remove all the dead asset keys (via AssetsNotFound), but those
            // happen at most once a day (and probably less, since users may not
            // leave the app open long enough for it to finish).  We must be
            // conservative here because if we load the wrong original asset we
            // will persist the mistake in the smaller image sizes.
            if (!expected_fingerprint.empty()) {
              mu_.Unlock();
              const string actual_fingerprint = AssetNewFingerprint(asset);
              if (expected_fingerprint != actual_fingerprint) {
                result(NULL);
                return;
              }
              mu_.Lock();
            }
          }
          verified_assets_.insert(asset_key);
          mu_.Unlock();

          result(asset);
        });
    }
                     failureBlock:failure];
}

- (void)addAsset:(NSData*)data
        metadata:(NSDictionary*)metadata
        callback:(void(^)(string asset_url, string asset_key))done {
  // Write the image to the asset library.
  [self.assetsLibrary
      writeImageDataToSavedPhotosAlbum:data
      metadata:metadata
      completionBlock:^(NSURL* url, NSError* error) {
      if (!url) {
        LOG("assets: unable to write asset: %s", error);
        if (done) {
          done("", "");
        }
        return;
      }
      // Retrieve the asset.
      ALAssetsLibraryAssetForURLResultBlock result = ^(ALAsset* asset) {
        CGImageRef square_thumbnail = [asset thumbnail];
        const string asset_url = AssetURL(asset);
        const string asset_key = EncodeAssetKey(
            asset_url, AssetNewFingerprint(square_thumbnail));
        if (done) {
          done(asset_url, asset_key);
        }
        // Pretend a scan saw the asset. The PhotoManager is hooked up to the
        // scan_progress callback and will add the new asset.  This is optional,
        // since a regular asset scan will eventually see the asset, but calling
        // it explicitly ensures that the new image is recognized promptly (important
        // when saving images from the camera).
        // Note that this must come after calling done() to avoid deadlocks
        // (between PhotoManager::CopyToAssetsLibrary and NewAssetPhoto).
        const AssetScanData data(asset, asset_key, 1, square_thumbnail);
        state_->assets_scan_progress()->Run(data);
      };

      ALAssetsLibraryAccessFailureBlock failure = ^(NSError* error) {
        LOG("assets: unable to retrieve asset: %s: %s", url, error);
        if (done) {
          done("", "");
        }
      };

      [self.assetsLibrary assetForURL:url
                          resultBlock:result
                         failureBlock:failure];
    }];
}

- (void)deleteAsset:(const string&)key {
  // Sigh, ALAssetsLibrary really is the worst API ever: asset deletion might
  // fail if we send too many deletion requests too quickly
  // (ALAsestsLibraryWriteBusyError). So we persist the desire to delete a key
  // and continually retry deletion until we get a permanent error or we
  // succeed.
  Slice url;
  if (!DecodeAssetKey(key, &url, NULL)) {
    DCHECK(false) << ": unable to decode key: " << key;
    return;
  }
  if (url.empty()) {
    return;
  }
  // There is a race between adding the asset url to the deletion queue and
  // syncing with a new folder via iTunes. But the race does not matter because
  // we can't delete assets synced via iTunes (ALAsset.editable == false).
  state_->db()->Put(DBFormat::asset_deletion_key(url.ToString()), "");
  [self maybeProcessDeletionQueue];
}

- (void)finishDeleteAsset:(const string&)deletion_key
                    error:(NSError*)error {
  WallTime delay = 0;
  if (!error ||
      ToSlice(error.domain) != ToSlice(ALAssetsLibraryErrorDomain) ||
      error.code != ALAssetsLibraryWriteBusyError) {
    // Delete the key unless the assets library is busy (in which case we'll
    // retry).
    state_->db()->Delete(deletion_key);
  } else {
    // The assets library was busy. Pause for a second before attempting the
    // deletion again.
    delay = 1;
  }

  dispatch_after_low_priority(delay, ^{
      deletion_mu_.Lock();
      deletion_inflight_ = false;
      deletion_mu_.Unlock();

      [self maybeProcessDeletionQueue];
    });
}

- (void)maybeProcessDeletionQueue {
  MutexLock l(&deletion_mu_);
  if (deletion_inflight_) {
    return;
  }

  string deletion_key;
  for (DB::PrefixIterator iter(state_->db(), kAssetDeletionKeyPrefix);
       iter.Valid();
       iter.Next()) {
    deletion_key = iter.key().ToString();
    break;
  }
  if (deletion_key.empty()) {
    return;
  }
  deletion_inflight_ = true;

  NSURL* url = NewNSURL(deletion_key.substr(kAssetDeletionKeyPrefix.size()));
  ALAssetsLibraryAssetForURLResultBlock result = ^(ALAsset* asset) {
    if (!asset.editable) {
      // We can only delete editable assets (i.e. assets the viewfinder app
      // created).
      LOG("assets: unable to delete non-editable asset %s", url);
      [self finishDeleteAsset:deletion_key error:NULL];
      return;
    }
    // Setting the assets image data to empty causes it to be deleted.
    [asset setImageData:NULL
               metadata:NULL
        completionBlock:^(NSURL*, NSError* error) {
        LOG("assets: delete %s: %s", url, error);
        [self finishDeleteAsset:deletion_key error:NULL];
      }];
  };
  ALAssetsLibraryAccessFailureBlock failure = ^(NSError* error) {
    LOG("assets: unable to retrieve asset: %s: %s", url, error);
    [self finishDeleteAsset:deletion_key error:error];
  };
  [self.assetsLibrary assetForURL:url
                      resultBlock:result
                     failureBlock:failure];
}

- (void)dealloc {
  [self stop];
}

@end  // AssetsManager
