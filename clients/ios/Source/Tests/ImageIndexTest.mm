// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis

#ifdef TESTING

#import <CoreImage/CoreImage.h>
#import <ImageIO/ImageIO.h>
#import <re2/re2.h>
#import "Defines.h"
#import "FileUtils.h"
#import "Image.h"
#import "ImageFingerprint.h"
#import "ImageIndex.h"
#import "LazyStaticPtr.h"
#import "Matrix.h"
#import "PathUtils.h"
#import "ScopedPtr.h"
#import "STLUtils.h"
#import "StringUtils.h"
#import "Testing.h"
#import "TestUtils.h"
#import "Vector.h"

namespace {

typedef std::map<string, string> StringMap;

const string kTestDataDir = JoinPath(TmpDir(), "fingerprint");
LazyStaticPtr<RE2, const char*> kIDRe = { "(?:.*/)?(\\d+)-.*" };

string FilenameToId(const string& filename) {
  string id;
  if (!RE2::FullMatch(filename, *kIDRe, &id)) {
    return string();
  }
  return id;
}

class TestDataIterator {
 public:
  TestDataIterator(const string& filter = ".*\\.png$",
                   const string& subdir_filter = "")
      : subdir_index_(-1),
        filename_index_(0),
        count_(0) {
    if (!filter.empty()) {
      filter_.reset(new RE2(filter));
    }
    if (!subdir_filter.empty()) {
      subdir_filter_.reset(new RE2(subdir_filter));
    }
    Next();
  }

  void Next() {
    do {
      while (++filename_index_ < filenames_.size()) {
        if (filter_.get() &&
            !RE2::FullMatch(filename(), *filter_)) {
          continue;
        }
        id_ = FilenameToId(filename());
        if (!id_.empty()) {
          ++count_;
          return;
        }
      }

      filename_index_ = -1;
      filenames_.clear();

      subdir_ = Format("%02d000", ++subdir_index_);
      if (subdir_filter_.get() &&
          !RE2::FullMatch(subdir_, *subdir_filter_)) {
        continue;
      }

      fulldir_ = Format("%s/%s", kTestDataDir, subdir_);

      DirList(fulldir_, &filenames_);
    } while (!filenames_.empty());
  }

  bool done() const { return filenames_.empty(); };
  int count() const { return count_; }
  const string& id() const { return id_; }
  const string& filename() const { return filenames_[filename_index_]; }
  const string& full_dir() const { return fulldir_; }

  string full_path() const {
    return JoinPath(fulldir_, filename());
  }

  string sub_path() const {
    return JoinPath(subdir_, filename());
  }

 private:
  ScopedPtr<RE2> filter_;
  ScopedPtr<RE2> subdir_filter_;
  int subdir_index_;
  string subdir_;
  string fulldir_;
  string id_;
  vector<string> filenames_;
  int filename_index_;
  int count_;
};

class ImageIndexTest : public Test {
 public:
  ImageIndexTest()
      : index_(true),
        db_(NewTestDB(dir())) {
  }

  Image Load(const string& path, float size = 0) {
    Image image;
    image.Decompress(path, size, NULL);
    return image;
  }

  void WriteJPEG(const Image& image, const string& name) {
    WriteDataToFile(JoinPath(TmpDir(), name), image.CompressJPEG(NULL, 0.9));
  }
  void WritePNG(const Image& image, const string& name) {
    WriteDataToFile(JoinPath(TmpDir(), name), image.CompressPNG(NULL));
  }

  Image Scale(const Image& image, float scale) {
    CIFilter* filter = [CIFilter filterWithName:@"CILanczosScaleTransform"];
    [filter setValue:[NSNumber numberWithFloat:scale]
                forKey:@"inputScale"];
    return ApplyCIFilters(image, Array(filter));
  }

  Image Rotate(const Image& image, float degrees) {
    return Transform(image, CGAffineTransformMakeRotation(degrees * kPi / 180));
  }

  Image ReflectVertical(const Image& image) {
    return Transform(image, CGAffineTransformMakeScale(1, -1));
  }

  Image ReflectHorizontal(const Image& image) {
    return Transform(image, CGAffineTransformMakeScale(-1, 1));
  }

  Image Transform(const Image& image, CGAffineTransform transform) {
    CIFilter* filter = [CIFilter filterWithName:@"CIAffineTransform"];
    [filter setValue:[NSValue valueWithBytes:&transform
                                    objCType:@encode(CGAffineTransform)]
                forKey:@"inputTransform"];
    return ApplyCIFilters(image, Array(filter));
  }

  Image CompressJPEG(const Image& image, float quality) {
    Image new_image;
    new_image.Decompress(image.CompressJPEG(NULL, quality), 0, NULL);
    return new_image;
  }

  // Apply CoreImage auto-adjustment filters.
  Image AutoAdjust(const Image& image) {
    CIImage* input_image = [CIImage imageWithCGImage:image];
    NSArray* filters = [input_image autoAdjustmentFilters];
    return ApplyCIFilters(input_image, filters);
  }

  Image GaussianBlur(const Image& image, float radius) {
    CIFilter* filter = [CIFilter filterWithName:@"CIGaussianBlur"];
    [filter setValue:[NSNumber numberWithFloat:radius]
                forKey:@"inputRadius"];
    return ApplyCIFilters(image, Array(filter));
  }

  Image Vignette(const Image& image, float radius, float intensity) {
    CIFilter* filter = [CIFilter filterWithName:@"CIVignette"];
    [filter setValue:[NSNumber numberWithFloat:radius]
                forKey:@"inputRadius"];
    [filter setValue:[NSNumber numberWithFloat:intensity]
                forKey:@"inputIntensity"];
    return ApplyCIFilters(image, Array(filter));
  }

  ImageFingerprint Add(const Image& image, float aspect_ratio, const string& id) {
    DBHandle updates = db_->NewTransaction();
    const ImageFingerprint f = FingerprintImage(image, aspect_ratio);
    index_.Add(f, id, updates);
    updates->Commit();
    return f;
  }

  ImageFingerprint Add(const Image& image, const string& id) {
    return Add(image, 1, id);
  }

  void Remove(const ImageFingerprint& fingerprint, const string& id) {
    DBHandle updates = db_->NewTransaction();
    index_.Remove(fingerprint, id, updates);
    updates->Commit();
  }

  string Search(const ImageFingerprint& fingerprint) {
    StringSet matched_ids;
    index_.Search(db_, fingerprint, &matched_ids);
    vector<string> sorted_ids(matched_ids.begin(), matched_ids.end());
    std::sort(sorted_ids.begin(), sorted_ids.end());
    return ToString(sorted_ids);
  }

  int HammingDistance(const ImageFingerprint& f1, const ImageFingerprint& f2) {
    return index_.HammingDistance(f1, f2);
  }

 private:
  Image ApplyCIFilters(const Image& image, NSArray* filters) {
    return ApplyCIFilters([CIImage imageWithCGImage:image], filters);
  }

  Image ApplyCIFilters(CIImage* image, NSArray* filters) {
    CHECK(filters != NULL);
    for (CIFilter* filter in filters) {
      [filter setValue:image forKey:kCIInputImageKey];
      image = [filter outputImage];
    }
    return Image([core_image_context() createCGImage:image
                                            fromRect:image.extent]);
  }

  CIContext* core_image_context() {
    if (!core_image_context_) {
      // NOTE(peter): The software renderer is an order of magnitude slower. Use
      // the GPU!
      core_image_context_ =
          [CIContext contextWithOptions:
                       Dict(kCIContextUseSoftwareRenderer, NO)];
    }
    return core_image_context_;
  }

 protected:
  ImageIndex index_;
  DBHandle db_;
  CIContext* core_image_context_;
};

TEST_F(ImageIndexTest, Scale) {
  if (kIOSVersion < "6.0") {
    // The iOS 5.x scale is terrible, skip this test entirely.
    return;
  }
  Image image(Load(MainBundlePath("test-photo.jpg")));
  // The original image.
  const ImageFingerprint f1 = Add(image, "1");
  EXPECT_EQ("<1>", Search(f1));
  // 1/2 scale.
  const ImageFingerprint f2 = Add(Scale(image, 1.0 / 2), "2");
  LOG("HD(f1,f2): %d", HammingDistance(f1, f2));
  EXPECT_EQ("<1 2>", Search(f1));
  EXPECT_EQ("<1 2>", Search(f2));
  // 1/4 scale.
  const ImageFingerprint f3 = Add(Scale(image, 1.0 / 4), "3");
  LOG("HD(f1,f3): %d", HammingDistance(f1, f3));
  EXPECT_EQ("<1 2 3>", Search(f1));
  EXPECT_EQ("<1 2 3>", Search(f2));
  EXPECT_EQ("<1 2 3>", Search(f3));
  // 1/8 scale.
  const ImageFingerprint f4 = Add(Scale(image, 1.0 / 8), "4");
  LOG("HD(f1,f4): %d", HammingDistance(f1, f4));
  EXPECT_EQ("<1 2 3 4>", Search(f1));
  EXPECT_EQ("<1 2 3 4>", Search(f2));
  EXPECT_EQ("<1 2 3 4>", Search(f3));
  EXPECT_EQ("<1 2 3 4>", Search(f4));
  // 1/16 scale.
  const ImageFingerprint f5 = Add(Scale(image, 1.0 / 16), "5");
  LOG("HD(f1,f5): %d", HammingDistance(f1, f5));
  LOG("HD(f2,f5): %d", HammingDistance(f2, f5));
  LOG("HD(f3,f5): %d", HammingDistance(f3, f5));
  LOG("HD(f4,f5): %d", HammingDistance(f4, f5));
  EXPECT_EQ("<1 2 3 4 5>", Search(f1));
  EXPECT_EQ("<1 2 3 4 5>", Search(f2));
  EXPECT_EQ("<1 2 3 4 5>", Search(f3));
  EXPECT_EQ("<1 2 3 4 5>", Search(f4));
  EXPECT_EQ("<1 2 3 4 5>", Search(f5));
}

// NOTE(peter): Support for rotation invariant fingerprints is currently
// disabled.
//
// TEST_F(ImageIndexTest, Rotate) {
//   Image image(Load(MainBundlePath("test-photo.jpg")));
//   // The original image.
//   const ImageFingerprint f1 = Add(image, "1");
//   EXPECT_EQ("<1>", Search(f1));
//   // 90 degree rotation
//   const ImageFingerprint f2 = Add(Rotate(image, 90), "2");
//   LOG("HD(f1,f2): %d", HammingDistance(f1, f2));
//   EXPECT_EQ("<1 2>", Search(f1));
//   EXPECT_EQ("<1 2>", Search(f2));
//   // 180 degree rotation
//   const ImageFingerprint f3 = Add(Rotate(image, 180), "3");
//   LOG("HD(f1,f3): %d", HammingDistance(f1, f3));
//   EXPECT_EQ("<1 2 3>", Search(f1));
//   EXPECT_EQ("<1 2 3>", Search(f2));
//   EXPECT_EQ("<1 2 3>", Search(f3));
//   // 270 degree rotation
//   const ImageFingerprint f4 = Add(Rotate(image, 270), "4");
//   LOG("HD(f1,f4): %d", HammingDistance(f1, f4));
//   EXPECT_EQ("<1 2 3 4>", Search(f1));
//   EXPECT_EQ("<1 2 3 4>", Search(f2));
//   EXPECT_EQ("<1 2 3 4>", Search(f3));
//   EXPECT_EQ("<1 2 3 4>", Search(f4));
// }

// NOTE(peter): Support for reflection invariant fingerprints is currently
// disabled.
//
// TEST_F(ImageIndexTest, Reflect) {
//   Image image(Load(MainBundlePath("test-photo.jpg")));
//   // The original image.
//   const ImageFingerprint f1 = Add(image, "1");
//   EXPECT_EQ("<1>", Search(f1));
//   // Reflect horizontal.
//   const ImageFingerprint f2 = Add(ReflectHorizontal(image), "2");
//   LOG("HD(f1,f2): %d", HammingDistance(f1, f2));
//   EXPECT_EQ("<1 2>", Search(f1));
//   EXPECT_EQ("<1 2>", Search(f2));
//   // Reflect vertical
//   const ImageFingerprint f3 = Add(ReflectVertical(image), "3");
//   LOG("HD(f1,f3): %d", HammingDistance(f1, f3));
//   EXPECT_EQ("<1 2 3>", Search(f1));
//   EXPECT_EQ("<1 2 3>", Search(f2));
//   EXPECT_EQ("<1 2 3>", Search(f3));
// }

TEST_F(ImageIndexTest, JPEG) {
  Image image(Load(MainBundlePath("test-photo.jpg")));
  // The original image.
  const ImageFingerprint f1 = Add(image, "1");
  EXPECT_EQ("<1>", Search(f1));
  // 70% quality.
  const ImageFingerprint f2 = Add(CompressJPEG(image, 0.7), "2");
  LOG("HD(f1,f2): %d", HammingDistance(f1, f2));
  EXPECT_EQ("<1 2>", Search(f1));
  EXPECT_EQ("<1 2>", Search(f2));
  // 50% quality.
  const ImageFingerprint f3 = Add(CompressJPEG(image, 0.5), "3");
  LOG("HD(f1,f3): %d", HammingDistance(f1, f3));
  EXPECT_EQ("<1 2 3>", Search(f1));
  EXPECT_EQ("<1 2 3>", Search(f2));
  EXPECT_EQ("<1 2 3>", Search(f3));
  // 30% quality.
  const ImageFingerprint f4 = Add(CompressJPEG(image, 0.3), "4");
  LOG("HD(f1,f4): %d", HammingDistance(f1, f4));
  EXPECT_EQ("<1 2 3 4>", Search(f1));
  EXPECT_EQ("<1 2 3 4>", Search(f2));
  EXPECT_EQ("<1 2 3 4>", Search(f3));
  EXPECT_EQ("<1 2 3 4>", Search(f4));
  // 10% quality.
  const ImageFingerprint f5 = Add(CompressJPEG(image, 0.1), "5");
  LOG("HD(f1,f5): %d", HammingDistance(f1, f5));
  EXPECT_EQ("<1 2 3 4 5>", Search(f1));
  EXPECT_EQ("<1 2 3 4 5>", Search(f2));
  EXPECT_EQ("<1 2 3 4 5>", Search(f3));
  EXPECT_EQ("<1 2 3 4 5>", Search(f4));
  EXPECT_EQ("<1 2 3 4 5>", Search(f5));
  // 1% quality.
  const ImageFingerprint f6 = Add(CompressJPEG(image, 0.01), "6");
  LOG("HD(f1,f6): %d", HammingDistance(f1, f6));
  EXPECT_EQ("<1 2 3 4 5 6>", Search(f1));
  EXPECT_EQ("<1 2 3 4 5 6>", Search(f2));
  EXPECT_EQ("<1 2 3 4 5 6>", Search(f3));
  EXPECT_EQ("<1 2 3 4 5 6>", Search(f4));
  EXPECT_EQ("<1 2 3 4 5 6>", Search(f5));
  EXPECT_EQ("<1 2 3 4 5 6>", Search(f6));
}

TEST_F(ImageIndexTest, AutoAdjust) {
  Image image(Load(MainBundlePath("test-photo.jpg")));
  // The original image.
  const ImageFingerprint f1 = Add(image, "1");
  EXPECT_EQ("<1>", Search(f1));
  // CoreImage auto-adjustments: red-eye correction, face balance, saturation,
  // contrast and shadow detail.
  const ImageFingerprint f2 = Add(AutoAdjust(image), "2");
  LOG("HD(f1,f2): %d", HammingDistance(f1, f2));
  EXPECT_EQ("<1 2>", Search(f1));
  EXPECT_EQ("<1 2>", Search(f2));
}

TEST_F(ImageIndexTest, GaussianBlur) {
  if (kIOSVersion < "6.0") {
    // We don't have a good GaussianBlur equivalent on iOS 5.x.
    return;
  }
  Image image(Load(MainBundlePath("test-photo.jpg")));
  // The original image.
  const ImageFingerprint f1 = Add(image, "1");
  EXPECT_EQ("<1>", Search(f1));
  // 1-pixel radius.
  const ImageFingerprint f2 = Add(GaussianBlur(image, 1), "2");
  LOG("HD(f1,f2): %d", HammingDistance(f1, f2));
  EXPECT_EQ("<1 2>", Search(f1));
  EXPECT_EQ("<1 2>", Search(f2));
  // 2-pixel radius causes too much difference.
  const ImageFingerprint f3 = Add(GaussianBlur(image, 2), "3");
  LOG("HD(f1,f3): %d", HammingDistance(f1, f3));
  EXPECT_EQ("<1 2 3>", Search(f1));
  EXPECT_EQ("<1 2 3>", Search(f2));
  EXPECT_EQ("<1 2 3>", Search(f3));
}

TEST_F(ImageIndexTest, Vignette) {
  Image image(Load(MainBundlePath("test-photo.jpg")));
  // The original image.
  const ImageFingerprint f1 = Add(image, "1");
  EXPECT_EQ("<1>", Search(f1));
  // Weak vignette.
  const ImageFingerprint f2 = Add(Vignette(image, 0, 5), "2");
  LOG("HD(f1,f2): %d", HammingDistance(f1, f2));
  EXPECT_EQ("<1 2>", Search(f1));
  EXPECT_EQ("<1 2>", Search(f2));
}

TEST_F(ImageIndexTest, Remove) {
  Image image(Load(MainBundlePath("test-photo.jpg")));
  // Add the same image twice.
  const ImageFingerprint f1 = Add(image, "1");
  EXPECT_EQ(13, index_.TotalTags(db_));
  EXPECT_EQ(13, index_.UniqueTags(db_));
  const ImageFingerprint f2 = Add(image, "2");
  EXPECT_EQ(26, index_.TotalTags(db_));
  EXPECT_EQ(13, index_.UniqueTags(db_));
  EXPECT_EQ("<1 2>", Search(f1));
  // Remove the first image.
  Remove(f1, "1");
  EXPECT_EQ("<2>", Search(f1));
  EXPECT_EQ(13, index_.TotalTags(db_));
  EXPECT_EQ(13, index_.UniqueTags(db_));
  // Remove the second image.
  Remove(f2, "2");
  EXPECT_EQ("<>", Search(f1));
  EXPECT_EQ(0, index_.TotalTags(db_));
  EXPECT_EQ(0, index_.UniqueTags(db_));
}

#ifdef TEST_ALL

string DirForId(const Slice& id) {
  return Format("%s/%s000", kTestDataDir, id.substr(0, 2));
}

string OriginalPathForId(const Slice& id) {
  return Format("%s/%s.jpg", DirForId(id), id);
}

string PathForFilename(const string& filename) {
  const string id = FilenameToId(filename);
  return JoinPath(DirForId(FilenameToId(filename)), filename);
}

// NOTE(peter): This is a utility test that allows debugging of the difference
// between 2 photos and was useful in ironing out problems with the fingerprint
// routine. Specify the 2 files to be compared in the kTestData structure.
TEST_F(ImageIndexTest, Debug) {
  struct {
    const string file_a;
    const string file_b;
  } kTestData[] = {
    // { "01000/01274-iPhone-4s-6.1.3-aspect.png", "01000/01274-iPhone-4s-6.1.3-square.png" },
    // { "02000/02206-iPhone-4s-6.1.3-aspect.png", "02000/02206-iPhone-4s-6.1.3-square.png" },
    // { "02000/02459-iPhone-4s-6.1.3-aspect.png", "02000/02459-iPhone-4s-6.1.3-square.png" },
    // { "02000/02592-iPhone-4s-6.1.3-aspect.png", "02000/02592-iPhone-4s-6.1.3-square.png" },
    // { "03000/03002-iPhone-4s-6.1.3-aspect.png", "03000/03002-iPhone-4s-6.1.3-square.png" },
    // { "04000/04329-iPhone-4s-6.1.3-aspect.png", "04000/04329-iPhone-4s-6.1.3-square.png" },
    // { "04000/04894-iPhone-4s-6.1.3-aspect.png", "04000/04894-iPhone-4s-6.1.3-square.png" },
    // { "04000/04995-iPhone-4s-6.1.3-aspect.png", "04000/04995-iPhone-4s-6.1.3-square.png" },
    // { "07000/07708-iPhone-4s-6.1.3-aspect.png", "07000/07708-iPhone-4s-6.1.3-square.png" },
    // { "09000/09185-iPhone-4s-6.1.3-aspect.png", "09000/09185-iPhone-4s-6.1.3-square.png" },
    // { "09000/09938-iPhone-4s-6.1.3-aspect.png", "09000/09938-iPhone-4s-6.1.3-square.png" },

    { "00000/00112-iPad-3G-6.1.3-aspect.png", "00000/00112-iPad-3G-6.1.3-square.png" },
    { "00000/00727-iPad-3G-6.1.3-aspect.png", "00000/00727-iPad-3G-6.1.3-square.png" },
    { "01000/01271-iPad-3G-6.1.3-aspect.png", "01000/01271-iPad-3G-6.1.3-square.png" },
    { "01000/01541-iPad-3G-6.1.3-aspect.png", "01000/01541-iPad-3G-6.1.3-square.png" },
    { "01000/01814-iPad-3G-6.1.3-aspect.png", "01000/01814-iPad-3G-6.1.3-square.png" },
    { "05000/05479-iPad-3G-6.1.3-aspect.png", "05000/05479-iPad-3G-6.1.3-square.png" },
    { "05000/05813-iPad-3G-6.1.3-aspect.png", "05000/05813-iPad-3G-6.1.3-square.png" },
  };
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    Image image_a(Load(JoinPath(kTestDataDir, kTestData[i].file_a)));
    Image image_b(Load(JoinPath(kTestDataDir, kTestData[i].file_b)));
    const ImageFingerprint fingerprint_a =
        FingerprintImage(image_a, image_a.aspect_ratio());
    const ImageFingerprint fingerprint_b =
        FingerprintImage(image_b, image_a.aspect_ratio());
    const int distance =
        ImageIndex::HammingDistance(fingerprint_a, fingerprint_b);
    LOG("\n%s %s  %.0f\n%s %s  %.0f\n%s %d",
        fingerprint_a, kTestData[i].file_a, image_a.size(),
        fingerprint_b, kTestData[i].file_b, image_b.size(),
        ImageIndex::Intersect(fingerprint_a, fingerprint_b),
        distance);

    {
      Image thumbnail(FingerprintPrepareImage(image_a, image_a.aspect_ratio()));
      Slice suffix(kTestData[i].file_a);
      suffix.remove_prefix(suffix.size() - 11);
      WritePNG(thumbnail, FilenameToId(kTestData[i].file_a) + suffix.ToString());
    }

    {
      Image thumbnail(FingerprintPrepareImage(image_b, image_a.aspect_ratio()));
      Slice suffix(kTestData[i].file_b);
      suffix.remove_prefix(suffix.size() - 11);
      WritePNG(thumbnail, FilenameToId(kTestData[i].file_b) + suffix.ToString());
    }
  }
}

// Computes the histogram of distances between thumbnails that were generated
// from the same photo by different iOS devices/versions.
TEST_F(ImageIndexTest, FingerprintDistance) {
  vector<int> distance_histogram;
  int distance_sum = 0;
  int distance_count = 0;
  double M = 0;
  double S = 0;
  string last_id;
  string last_filename;
  ImageFingerprint last_fingerprint;
  float last_aspect_ratio = 1;

  // for (TestDataIterator iter(".*iPad-3G-6.1.3.*\\.png$", "0.000");
  for (TestDataIterator iter(".*iPad-3G-7.0.*\\.png$", "0.000");
  // for (TestDataIterator iter(".*iPhone-4s-6.1.3.*\\.png$", "0.000");
  // for (TestDataIterator iter(".*iPhone-4s-7.0.*\\.png$", "0.000");
       !iter.done(); iter.Next()) {
    Image image;
    image.Decompress(iter.full_path(), 0, NULL);
    if (!image.get()) {
      LOG("unable to load: %s", iter.full_path());
      continue;
    }
    if (Slice(iter.filename()).ends_with("-aspect.png")) {
      last_aspect_ratio = image.aspect_ratio();
    }
    const ImageFingerprint fingerprint =
        FingerprintImage(image, last_aspect_ratio);

    const string& id = iter.id();
    if (last_id == id) {
      const int distance = ImageIndex::HammingDistance(
          last_fingerprint, fingerprint);
      if (distance_histogram.size() <= distance) {
        distance_histogram.resize(distance + 1);
      }
      distance_histogram[distance] += 1;
      distance_sum += distance;
      ++distance_count;
      double tmp_M = M;
      M += (distance - tmp_M) / distance_count;
      S += (distance - tmp_M) * (distance - M);
      if (distance > 12) {
        LOG("%d %s %s\n%s\n%s\n%s", distance, last_filename, iter.sub_path(),
            fingerprint, last_fingerprint,
            ImageIndex::Intersect(fingerprint, last_fingerprint));
      }
    }
    last_id = id;
    last_filename = iter.sub_path();
    last_fingerprint = fingerprint;

    if ((iter.count() % 100) == 0) {
      LOG("%d", iter.count());
    }
  }

  LOG("distance average: %.3f  stddev: %.3f",
      double(distance_sum) / distance_count,
      sqrt(S / distance_count));
  for (int i = 0; i < distance_histogram.size(); ++i) {
    LOG("%2d: %d", i, distance_histogram[i]);
  }
}

TEST_F(ImageIndexTest, StrongCompareImages) {
  struct {
    const string a;
    const string b;
  } kTestData[] = {
    { "00012", "08056" },
    { "00015", "02328" },  // 02849 02944 03607 03690 07225 08417 08886 09338
    { "00066", "00067" },
    { "00084", "00085" },
    { "00084", "00087" },
    { "00085", "00087" },
    { "00152", "00153" },
    { "00164", "00165" },
    { "01136", "02177" },
    { "01138", "03006" },
    { "01141", "03228" },
    { "01504", "08893" },  // 08894
    { "01513", "08895" },  // 08896
    { "01523", "08897" },  // 08898
    { "01554", "08899" },  // 08900
    { "01558", "08901" },  // 08902
    { "01874", "02309" },
    { "01889", "03732" },
    { "01899", "03830" },
    { "01905", "02858" },
    { "01996", "02227" },
    { "02001", "03805" },
    { "02024", "02236" },
    { "02073", "03636" },
    { "02128", "02739" },  // 02803
    { "02135", "02779" },
    { "02154", "02892" },
    { "02218", "03693" },
    { "02245", "03481" },
    { "02264", "02361" },  // 04110
    { "02448", "03132" },
    { "02555", "03010" },
    { "02559", "04417" },
    { "02618", "03480" },
    { "02620", "02668" },
    { "02722", "03609" },
    { "02847", "04083" },
    { "02865", "03205" },
    { "02985", "03985" },
    { "02992", "03188" },  // 04267
    { "03078", "03694" },
    { "03140", "04185" },
    { "03177", "03930" },
    { "03188", "04267" },
    { "03197", "03541" },
    { "03352", "03954" },
    { "03393", "05075" },
    { "03506", "04026" },
    { "03529", "03750" },
    { "03530", "04100" },
    { "03858", "05342" },
    { "03913", "05134" },
    { "04254", "05477" },
    { "04379", "04403" },
    { "06555", "09921" },  // 09923
    { "06609", "09922" },  // 09925
    { "07162", "07392" },
    { "07208", "07260" },
    { "07227", "07229" },
    { "07263", "07324" },
    { "07289", "07371" },
    { "07297", "07317" },
    { "07346", "09874" },
    { "07464", "07618" },
    { "07634", "07636" },  // 07641
    { "07634", "07638" },
    { "07636", "07638" },
    { "07636", "07638" },  // 07641
    { "07646", "07651" },  // 08053
    { "07659", "07663" },
    { "07737", "07772" },
    { "07764", "07783" },
    { "07779", "07816" },
    { "07879", "07887" },
    { "07937", "07961" },  // 07989 08011 08048
    { "08033", "08040" },  // 08633
    { "08229", "08230" },
    { "08230", "08231" },
    { "08303", "08304" },
    { "08309", "08310" },
    { "08374", "08391" },
    { "08380", "08461" },
    { "08835", "08837" },
    { "08846", "08855" },
    { "08879", "08880" },
    { "08887", "08888" },
    { "08890", "08891" },
    { "08892", "09068" },
    { "08903", "08904" },
    { "08905", "08906" },
    { "08907", "08908" },
    { "08909", "08910" },
    { "08911", "08912" },
    { "08913", "08914" },
    { "08952", "08954" },
    { "08975", "08976" },
    { "09032", "09033" },
    { "09144", "09145" },
    { "09189", "09194" },
    { "09507", "09614" },
    { "09528", "09629" },
    { "09576", "09595" },
    { "09577", "09636" },
    { "09755", "09792" },
    { "09924", "09928" },
    { "09930", "09943" },
    { "09931", "09942" },
    { "09933", "09944" },
    { "09937", "09940" },
    { "09948", "09949" },
  };
  const string kSuffix = "-iPhone-4s-6.1.3-aspect.png";
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    LOG("%s %s %9.5f %9.5f", kTestData[i].a, kTestData[i].b,
        StrongCompareImages(OriginalPathForId(kTestData[i].a),
                            OriginalPathForId(kTestData[i].b)),
        StrongCompareImages(PathForFilename(kTestData[i].a + kSuffix),
                            PathForFilename(kTestData[i].b + kSuffix)));
  }
}

TEST_F(ImageIndexTest, Index) {
  const RE2 kBasenameRe("(?:.*/)?([^/]*)");

  typedef std::map<string, ImageFingerprint> FingerprintMap;

  StringSet unique_fingerprints;
  FingerprintMap id_to_fingerprint;
  int total = 0;
  float last_aspect_ratio = 1;

  for (TestDataIterator iter(".*iPhone-4s-6.1.3.*\\.png$", "00000");
       !iter.done(); iter.Next()) {
    Image image;
    image.Decompress(iter.full_path(), 0, NULL);
    if (!image.get()) {
      LOG("unable to load: %s", iter.full_path());
      continue;
    }
    const string path = iter.sub_path();
    if (Slice(path).ends_with("-aspect.png")) {
      last_aspect_ratio = image.aspect_ratio();
    }
    const ImageFingerprint fingerprint = Add(image, last_aspect_ratio, path);
    unique_fingerprints.insert(fingerprint.SerializeAsString());
    id_to_fingerprint[path] = fingerprint;
    ++total;
    if ((total % 100) == 0) {
      LOG("loading %d", total);
    }
  }

  LOG("index size: %d %d %d\n%s", index_.TotalTags(db_), index_.UniqueTags(db_),
      unique_fingerprints.size(), index_.PrettyHistogram());

  {
#if TARGET_IPHONE_SIMULATOR
    const string output_dir = JoinPath(TmpDir(), "output");
    DirRemove(output_dir, true);
    CHECK(DirCreate(output_dir));
#endif // TARGET_IPHONE_SIMULATOR

    int buckets = 0;
    int candidates = 0;

    while (!unique_fingerprints.empty()) {
      const int old_size = unique_fingerprints.size();
      StringSet matched_ids;
      const string fingerprint_str = *unique_fingerprints.begin();
      unique_fingerprints.erase(fingerprint_str);
      ImageFingerprint fingerprint;
      fingerprint.ParseFromString(fingerprint_str);
      candidates += index_.Search(db_, fingerprint, &matched_ids);

#if TARGET_IPHONE_SIMULATOR
      const string dir = JoinPath(output_dir, ToString(fingerprint));
      CHECK(DirCreate(dir));
#endif // TARGET_IPHONE_SIMULATOR

      StringSet unique_ids;
      for (StringSet::iterator iter(matched_ids.begin());
           iter != matched_ids.end();
           ++iter) {
        string id;
        if (RE2::FullMatch(*iter, *kIDRe, &id)) {
          unique_ids.insert(id);
        }
        const ImageFingerprint& matched_fingerprint = id_to_fingerprint[*iter];
        unique_fingerprints.erase(matched_fingerprint.SerializeAsString());
#if TARGET_IPHONE_SIMULATOR
        const int distance = HammingDistance(fingerprint, matched_fingerprint);
        Slice basename;
        CHECK(RE2::FullMatch(*iter, kBasenameRe, &basename));
        const string symlink_path = JoinPath(
            dir, string(Format("%02d:%s", distance, basename)));
        const string symlink_val = JoinPath(kTestDataDir, *iter);
        CHECK_EQ(0, symlink(symlink_val.c_str(), symlink_path.c_str()));
#endif // TARGET_IPHONE_SIMULATOR
      }
      if (unique_ids.size() > 1) {
        LOG("matched %s", unique_ids);
      }

      ++buckets;
      if (int(old_size / 100) != int(unique_fingerprints.size() / 100)) {
        LOG("processing %d", unique_fingerprints.size());
      }
    }

    LOG("%d images, %d buckets, %.1f candidates/bucket\n",
        total, buckets, float(candidates) / buckets);
  }
}

#endif  // TEST_ALL

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
