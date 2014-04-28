// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import <AssetsLibrary/AssetsLibrary.h>
#import <ImageIO/ImageIO.h>
#import "Appearance.h"
#import "FileUtils.h"
#import "Image.h"
#import "LocationTracker.h"
#import "LocationUtils.h"
#import "Logging.h"
#import "Mutex.h"
#import "PathUtils.h"
#import "StringUtils.h"
#import "TestAssets.h"

namespace {

// The latitude and longitude given to test assets. Corresponds to a point in
// the arctic ocean. We use this location to identify test assets so they can
// be garbage collected if a test shutdown before cleaning assets it created.
const double kTestAssetLatitude = 90;
const double kTestAssetLongitude = 23;

bool IsTestAssetLocation(CLLocation* l) {
  const double kMaxDiff = 1e-6;
  const CLLocationCoordinate2D c = l.coordinate;
  return (fabs(c.latitude - kTestAssetLatitude) < kMaxDiff &&
          fabs(c.longitude - kTestAssetLongitude) < kMaxDiff);
}

}  // namespace

TestAssets::TestAssets()
    : library_([ALAssetsLibrary new]) {
  // Find any test assets left around by previous instances but which weren't
  // properly cleaned up (perhaps the test crashed). We look for assets who
  // have a location close to the test asset location.
  Barrier* barrier = new Barrier(1);
  [library_
      enumerateGroupsWithTypes:ALAssetsGroupSavedPhotos
                    usingBlock:^(ALAssetsGroup* group, BOOL* stop) {
      [group setAssetsFilter:[ALAssetsFilter allPhotos]];
      ALAssetsGroupEnumerationResultsBlock asset_block =
          ^(ALAsset* asset, NSUInteger index, BOOL* stop) {
        if (index == NSNotFound) {
          barrier->Signal();
          return;
        }
        CLLocation* location = [asset valueForProperty:ALAssetPropertyLocation];
        if (!location) {
          return;
        }
        if (IsTestAssetLocation(location)) {
          NSURL* url = [asset defaultRepresentation].url;
          LOG("test-assets: garbage collecting: %s", url);
          urls_.insert(ToString(url));
        }
      };
      [group enumerateAssetsWithOptions:NSEnumerationReverse
                             usingBlock:asset_block];
    }
                failureBlock:^(NSError* error) {
      LOG("test-assets: scan error: %@", error);
    }];
  barrier->Wait();
  delete barrier;

  while (!urls_.empty()) {
    Delete(NewNSURL(*urls_.begin()));
  }
}

TestAssets::~TestAssets() {
  while (!urls_.empty()) {
    Delete(NewNSURL(*urls_.begin()));
  }
}

NSURL* TestAssets::Add(NSData* jpeg_data) {
  if (!jpeg_data) {
    jpeg_data = ReadFileToData(MainBundlePath("test-photo.jpg"));
  }

  Image image;
  CHECK(image.Decompress(jpeg_data, 0, NULL));

  Dict gps;
  gps.insert(kCGImagePropertyGPSTimeStamp, 1);
  gps.insert(kCGImagePropertyGPSLatitudeRef, "N");
  gps.insert(kCGImagePropertyGPSLatitude, kTestAssetLatitude);
  gps.insert(kCGImagePropertyGPSLongitudeRef, "E");
  gps.insert(kCGImagePropertyGPSLongitude, kTestAssetLongitude);
  Dict metadata;
  metadata.insert(kCGImagePropertyGPSDictionary, gps);

  Barrier* barrier = new Barrier(1);
  __block NSURL* asset_url = NULL;

  [library_ writeImageToSavedPhotosAlbum:image.get()
                                metadata:metadata
                         completionBlock:^(NSURL* url, NSError* error) {
      asset_url = url;
      barrier->Signal();
    }];

  barrier->Wait();
  delete barrier;

  urls_.insert(ToString(asset_url));
  return asset_url;
}

NSURL* TestAssets::AddTextImage(const string& text) {
  UILabel* label = [UILabel new];
  label.adjustsFontSizeToFitWidth = YES;
  label.backgroundColor = MakeUIColor(1, 1, 1, 1);
  label.font = [UIFont systemFontOfSize:200];
  label.numberOfLines = 1;
  label.text = NewNSString(text);
  label.textColor = MakeUIColor(0, 0, 0, 1);
  [label sizeToFit];

  UIGraphicsBeginImageContextWithOptions(
      label.bounds.size, NO, 0);
  [label drawRect:label.bounds];
  UIImage* image = UIGraphicsGetImageFromCurrentImageContext();
  UIGraphicsEndImageContext();
  return Add(UIImageJPEGRepresentation(image, 0.7));
}

ALAsset* TestAssets::Lookup(NSURL* url) {
  Barrier* barrier = new Barrier(1);
  __block ALAsset* asset = NULL;
  [library_ assetForURL:url
            resultBlock:^(ALAsset* a) {
      asset = a;
      barrier->Signal();
    }
           failureBlock:^(NSError* e) {
      LOG("unable to find asset: %s", e);
      barrier->Signal();
    }];
  barrier->Wait();
  delete barrier;
  return asset;
}

string TestAssets::GetBytes(ALAsset* asset) {
  ALAssetRepresentation* rep = [asset defaultRepresentation];
  string s(rep.size, '\0');
  uint8_t* dest = reinterpret_cast<uint8_t*>(&s[0]);
  [rep getBytes:dest fromOffset:0 length:s.size() error:NULL];
  return s;
}

string TestAssets::GetBytes(NSURL* url) {
  return GetBytes(Lookup(url));
}

void TestAssets::Delete(NSURL* url) {
  urls_.erase(ToString(url));

  Barrier* barrier = new Barrier(1);
  [library_ assetForURL:url
            resultBlock:^(ALAsset* asset) {
      [asset setImageData:NULL
                 metadata:NULL
          completionBlock:^(NSURL* url, NSError* e) {
          barrier->Signal();
        }];
    }
           failureBlock:^(NSError* e) {
      LOG("unable to find asset: %s", e);
      barrier->Signal();
    }];
  barrier->Wait();
  delete barrier;
}

void TestAssets::Poke() {
  Delete(Add());
}

#endif  // TESTING
