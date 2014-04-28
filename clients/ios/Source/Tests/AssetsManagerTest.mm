// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#if defined(TESTING) && (TARGET_IPHONE_SIMULATOR)

#import "AssetsManager.h"
#import "DB.h"
#import "Image.h"
#import "TestAssets.h"
#import "Testing.h"
#import "TestUtils.h"
#import "Timer.h"


// Declarations of private iOS classes needed for the FastAssetURL() hack.
@interface PLManagedAsset {
}
@property (readonly) NSString* filename;
@property (readonly) NSString* uuid;
@end  // PLManagedAsset

@interface ALAssetPrivate {
}
@property (readonly) PLManagedAsset* photo;
@end  // ALAssetPrivate

@interface ALAsset (internal)
@property (readonly) ALAssetPrivate* internal;
@end  // ALAsset (internal)


namespace {

// Accessing asset.internal.photo.uuid is much faster than [asset
// valueForProperty:ALAssetPropertyURL], though not at all kosher per Apple's
// guidelines. Keeping this around in test code in case we ever find a need/use
// for it. FastAssetURL() is about twice as fast as AssetURL() on an iPhone 4S.
string FastAssetURL(ALAsset* asset) {
  NSString* ns_filename = asset.internal.photo.filename;
  const Slice filename = ToSlice(ns_filename);
  const int pos = filename.rfind('.');
  if (pos == Slice::npos) {
    return AssetURL(asset);
  }
  const Slice ext = filename.substr(pos + 1);
  NSString* ns_uuid = asset.internal.photo.uuid;
  const Slice uuid = ToSlice(ns_uuid);
  string res = "assets-library://asset/asset.";
  res.append(ext.data(), ext.size());
  res.append("?id=");
  res.append(uuid.data(), uuid.size());
  res.append("&ext=");
  res.append(ext.data(), ext.size());
  return res;
}

class AssetsManagerTest : public Test {
 protected:
  AssetsManagerTest()
      : state_(dir()),
        a_([[AssetsManager alloc] initWithState:&state_]),
        asset_(NULL) {
  }
  ~AssetsManagerTest() {
    [a_ stop];
  }

  // Runs a block, which should trigger exactly one asset scan,
  // and waits for that scan to finish before continuing.
  // Scans can be triggered manually with [a_ scan], or automatically
  // by changing an asset (once the notification listener is registered,
  // which is not the case at the start of a test).  It is important
  // to wait for any scans started within a test to finish, because
  // if a scan is left in progress when the test finishes it may
  // block change notifications for the next test.
  void RunAndWaitForScan(void (^block)()) {
    Barrier* barrier = new Barrier(1);
    state_.assets_scan_end()->AddSingleShot(^(const StringSet*) {
          barrier->Signal();
        });
    block();
    barrier->Wait();
    delete barrier;
  }

 protected:
  TestAssets test_assets_;
  TestUIAppState state_;
  AssetsManager* const a_;
  ScopedPtr<Barrier> scan_end_barrier_;
  ScopedPtr<Barrier> scan_progress_barrier_;
  ScopedPtr<Barrier> changed_barrier_;
  ScopedPtr<Barrier> lookup_barrier_;
  ALAsset* asset_;
};

TEST_F(AssetsManagerTest, Changed) {
  // Perform an initial scan.
  scan_end_barrier_.reset(new Barrier(1));
  state_.assets_scan_end()->AddSingleShot(^(const StringSet*) {
      scan_end_barrier_->Signal();
    });
  [a_ scan];
  scan_end_barrier_->Wait();

  // Reset the scan end barrier.
  scan_end_barrier_.reset(new Barrier(1));
  state_.assets_scan_end()->AddSingleShot(^(const StringSet*) {
      scan_end_barrier_->Signal();
    });

  // Add a new asset to the library.
  scan_progress_barrier_.reset(new Barrier(1));
  lookup_barrier_.reset(new Barrier(1));
  __block NSURL* new_asset_url;
  __block int scan_progress_id = state_.assets_scan_progress()->Add(
      ^(const AssetScanData& data) {
        scan_progress_barrier_->Wait();
        // Note that "asset_key" is composed of both the asset_url and
        // asset_fingerprint.
        Slice asset_url;
        CHECK(DecodeAssetKey(data.asset_key, &asset_url, NULL));
        if (asset_url == ToString(new_asset_url)) {
          // Only signal the lookup barrier when we've seen the new asset.
          lookup_barrier_->Signal();
          state_.assets_scan_progress()->Remove(scan_progress_id);
        }
      });
  new_asset_url = test_assets_.Add();
  scan_progress_barrier_->Signal();
  lookup_barrier_->Wait();

  // Wait for the scan to end.
  scan_end_barrier_->Wait();

  // Reset the scan end barrier.
  scan_end_barrier_.reset(new Barrier(1));
  __block int quick_scans = 0;
  __block StringSet not_found;
  __block int scan_end_id = state_.assets_scan_end()->Add(
      ^(const StringSet* not_found_assets) {
        if (not_found_assets) {
          state_.assets_scan_end()->Remove(scan_end_id);
          not_found = *not_found_assets;
          scan_end_barrier_->Signal();
        } else {
          ++quick_scans;
        }
      });
  // Force a full scan.
  state_.db()->Delete(DBFormat::metadata_key("last_full_asset_scan"));
  // Delete the new asset
  test_assets_.Delete(new_asset_url);
  // Wait for the scan to end.
  scan_end_barrier_->Wait();
  // We should have seen at least one quick scan due to the asset library
  // change.
  EXPECT_GE(1, quick_scans);
  EXPECT_EQ(1, not_found.size());
  EXPECT(ContainsKey(not_found, ToString(new_asset_url)));
}

TEST_F(AssetsManagerTest, ChangedDuringLookup) {
  // Must have at least one asset for this test
  NSURL* new_asset_url = test_assets_.Add();

  // Perform an initial scan.
  __block string scanned_asset_key;
  RunAndWaitForScan(^{
        // Remember the first asset scanned.
        state_.assets_scan_progress()->AddSingleShot(
            ^(const AssetScanData& data) {
              scanned_asset_key = data.asset_key;
            });
        [a_ scan];
      });
  LOG("scan done");

  // Lookup the asset we saw during the scan.
  lookup_barrier_.reset(new Barrier(1));
  dispatch_low_priority(^{
      [a_ assetForKey:scanned_asset_key
         resultBlock:^(ALAsset* asset) {
          asset_ = asset;
          lookup_barrier_->Signal();
        }
        failureBlock:^(NSError* error) {
          CHECK(false);
        }];
    });
  lookup_barrier_->Wait();
  LOG("lookup asset done");

  // Poke the assets library and wait for the change notification.
  changed_barrier_.reset(new Barrier(1));
  state_.assets_changed()->AddSingleShot(^{
      changed_barrier_->Signal();
    });
  LOG("poking asset library");
  test_assets_.Poke();
  changed_barrier_->Wait();
  LOG("asset library changed");

  // Verify that the defaultRepresentation pointer has been cleared (as
  // expected) by the change notification.
  Image image;
  image.reset([asset_ aspectRatioThumbnail]);
  LOG("asset thumbnail: %.0fx%.0f", image.width(), image.height());
  if (ToSlice([UIDevice currentDevice].systemVersion) < "6.0") {
    ALAssetRepresentation* rep = [asset_ defaultRepresentation];
    EXPECT(rep == NULL);
  }

  RunAndWaitForScan(^{
        test_assets_.Delete(new_asset_url);
      });
}

TEST_F(AssetsManagerTest, ChangedWhileScanning1) {
  // Must have at least one asset for this test
  NSURL* new_asset_url = test_assets_.Add();

  // Perform an intial scan, blocking the scan when the first asset is
  // encountered.
  scan_end_barrier_.reset(new Barrier(1));
  scan_progress_barrier_.reset(new Barrier(1));
  lookup_barrier_.reset(new Barrier(1));

  state_.assets_scan_progress()->AddSingleShot(
      ^(const AssetScanData& data) {
        scan_progress_barrier_->Signal();
        lookup_barrier_->Wait();
      });
  state_.assets_scan_end()->AddSingleShot(^(const StringSet*) {
      scan_end_barrier_->Signal();
    });

  [a_ scan];
  scan_progress_barrier_->Wait();
  LOG("hit scan progress");

  // Poke the assets library and wait for the change notification.
  changed_barrier_.reset(new Barrier(1));
  state_.assets_changed()->AddSingleShot(^{
      changed_barrier_->Signal();
    });

  test_assets_.Poke();
  changed_barrier_->Wait();
  LOG("hit assets changed");

  // Release the scan and verify that it episodeually finishes.
  lookup_barrier_->Signal();
  scan_end_barrier_->Wait();

  RunAndWaitForScan(^{
        test_assets_.Delete(new_asset_url);
      });
}

TEST_F(AssetsManagerTest, ChangedWhileScanning2) {
  // Perform an intial scan, blocking the scan when the first group is
  // encountered.
  scan_end_barrier_.reset(new Barrier(1));
  scan_progress_barrier_.reset(new Barrier(1));
  lookup_barrier_.reset(new Barrier(1));

  state_.assets_scan_group()->AddSingleShot(^{
      scan_progress_barrier_->Signal();
      lookup_barrier_->Wait();
    });
  state_.assets_scan_end()->AddSingleShot(^(const StringSet*) {
      scan_end_barrier_->Signal();
    });

  [a_ scan];
  scan_progress_barrier_->Wait();
  LOG("hit scan groups");

  // Poke the assets library and wait for the change notification.
  changed_barrier_.reset(new Barrier(1));
  state_.assets_changed()->AddSingleShot(^{
      changed_barrier_->Signal();
    });

  test_assets_.Poke();
  changed_barrier_->Wait();
  LOG("hit assets changed");

  // Release the scan and verify that it episodeually finishes.
  lookup_barrier_->Signal();
  scan_end_barrier_->Wait();
}

TEST_F(AssetsManagerTest, AssetMap) {
  vector<string> urls;
  for (int i = 1; i <= 10; ++i) {
    urls.push_back(ToString(test_assets_.Add()));
    AssetMap map;
    map.Scan();
    EXPECT_EQ(urls.size(), map.size());

    for (int j = 0; j < urls.size(); ++j) {
      EXPECT(ContainsKey(map, urls[j]));
    }
  }
}

TEST_F(AssetsManagerTest, AssetMapValidAfterNotification) {
  [a_ scan];

  NSURL* url1 = test_assets_.AddTextImage("1");
  NSURL* url2 = test_assets_.AddTextImage("2");
  NSURL* url3 = test_assets_.AddTextImage("3");

  AssetMap map;
  map.Scan();
  EXPECT_EQ(3, map.size());
  EXPECT(ContainsKey(map, ToString(url1)));
  EXPECT(ContainsKey(map, ToString(url2)));
  EXPECT(ContainsKey(map, ToString(url3)));

  RunAndWaitForScan(^{
      test_assets_.Delete(url3);
    });

  EXPECT_EQ(3, map.size());
  EXPECT_EQ(ToString(url1), AssetURL(FindOrNull(map, ToString(url1))));
  EXPECT_EQ(ToString(url2), AssetURL(FindOrNull(map, ToString(url2))));
  EXPECT_EQ("", AssetURL(FindOrNull(map, ToString(url3))));

  RunAndWaitForScan(^{
      test_assets_.AddTextImage("4");
    });

  EXPECT_EQ(3, map.size());
  EXPECT_EQ(ToString(url1), AssetURL(FindOrNull(map, ToString(url1))));
  EXPECT_EQ(ToString(url2), AssetURL(FindOrNull(map, ToString(url2))));
  EXPECT_EQ("", AssetURL(FindOrNull(map, ToString(url3))));
}

TEST_F(AssetsManagerTest, FastAssetURL) {
  NSURL* url1 = test_assets_.AddTextImage("1");

  AssetMap map;
  map.Scan();

  ALAsset* asset1 = FindOrNull(map, ToString(url1));
  WallTimer fast_t;
  const string fast_url = FastAssetURL(asset1);
  fast_t.Stop();
  WallTimer normal_t;
  const string normal_url = AssetURL(asset1);
  normal_t.Stop();
  LOG("%.3f %.3f", fast_t.Milliseconds(), normal_t.Milliseconds());
  EXPECT_EQ(normal_url, fast_url);
}

}  // namespace

#endif  // defined(TESTING) && (TARGET_IPHONE_SIMULATOR)

#if defined(TESTING) && !(TARGET_IPHONE_SIMULATOR)

#import "AssetsManager.h"
#import "Testing.h"
#import "Timer.h"

namespace {

TEST(AssetManagerTest, AssetMapScan) {
  WallTimer t;
  AssetMap map;
  map.Scan();
  LOG("%d unique assets, %.1f ms", map.size(), t.Milliseconds());
}

}  // namespace

#endif  // defined(TESTING) && !(TARGET_IPHONE_SIMULATOR)

// local variables:
// mode: c++
// end:
