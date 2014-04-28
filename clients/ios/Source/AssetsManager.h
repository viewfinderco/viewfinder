// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <unordered_map>
#import <unordered_set>
#import <AssetsLibrary/AssetsLibrary.h>
#import "Mutex.h"
#import "ScopedPtr.h"
#import "UIAppState.h"

bool IsOldAssetFingerprint(const Slice& fingerprint);
bool IsNewAssetFingerprint(const Slice& fingerprint);
string AssetOldFingerprint(ALAsset* asset);
string AssetNewFingerprint(ALAsset* asset);
string AssetURL(ALAsset* asset);

void SimpleAssetScan(ALAssetsLibrary* library, void (^callback)(ALAsset* asset));

// A map from asset url to ALAsset*. Provides quicker lookup of assets from
// asset-keys than using [ALAssetLibrary assetForKey:]. Note that the majority
// of memory is the asset url strings which are 80-bytes in length. Much of
// this space is wasted redundancy and through trickery we could reduce the
// overhead to 16-bytes per asset url, but that doesn't seem worth it right
// now. The data behind the ALAsset* is all cached by CoreData and will be
// purged in low memory situations.
class AssetMap : public std::unordered_map<string, ALAsset*> {
 public:
  AssetMap(ALAssetsLibrary* library = NULL);

  void Scan();

 private:
  ALAssetsLibrary* const library_;
};

typedef std::unordered_map<string, ALAssetsGroup*> AssetGroupMap;

@class AssetsScanState;

typedef std::unordered_set<string> AssetSet;

@interface AssetsManager : NSObject {
 @private
  Mutex mu_;
  Mutex deletion_mu_;
  UIAppState* state_;
  ALAssetsLibrary* assets_library_;
  bool installed_changed_notification_;
  AssetsScanState __weak* current_scan_;
  AssetSet verified_assets_;
  int num_scans_;
  int num_scans_completed_;
  bool full_scan_;
  bool stopped_;
  int64_t next_scan_id_;
  bool deletion_inflight_;
  bool cached_authorization_determined_;
  bool cached_authorization_failed_;
  AssetGroupMap asset_groups_;
}

@property (readonly, nonatomic) ALAssetsLibrary* assetsLibrary;
@property (readonly, nonatomic) bool authorizationDetermined;
@property (readonly, nonatomic) bool authorized;
@property (readonly, nonatomic) bool fullScan;
@property (readonly, nonatomic) bool initialScan;
@property (readonly, nonatomic) bool scanning;
@property (readonly, nonatomic) int numScans;
@property (readonly, nonatomic) int numScansCompleted;

- (id)initWithState:(UIAppState*)state;
- (void)authorize;
- (void)scan;
- (void)stop;
- (void)assetForKey:(const string&)key
        resultBlock:(ALAssetsLibraryAssetForURLResultBlock)result
       failureBlock:(ALAssetsLibraryAccessFailureBlock)failure;
- (void)addAsset:(NSData*)data
        metadata:(NSDictionary*)metadata
        callback:(void(^)(string asset_url, string asset_key))done;
- (void)deleteAsset:(const string&)key;

@end  // AssetsManager

// local variables:
// mode: objc
// end:
