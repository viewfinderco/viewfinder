// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <AssetsLibrary/AssetsLibrary.h>
#import <CommonCrypto/CommonDigest.h>
#import <ImageIO/ImageIO.h>
#import <MobileCoreServices/UTCoreTypes.h>
#import <UIKit/UIImage.h>
#import "Image.h"
#import "Logging.h"
#import "ValueUtils.h"

namespace {

void ReleasePixelBuffer(void* pixel, const void* data, size_t size) {
  CVPixelBufferRef buffer = (CVPixelBufferRef)pixel;
  CVPixelBufferUnlockBaseAddress(buffer, 0);
  CVPixelBufferRelease(buffer);
}

CGImageRef MakeImage(CVPixelBufferRef buffer) CF_RETURNS_RETAINED;
CGImageRef MakeImage(CVPixelBufferRef buffer) {
  CVPixelBufferRetain(buffer);
  CVPixelBufferLockBaseAddress(buffer, 0);

  ScopedRef<CGDataProviderRef> provider(
      CGDataProviderCreateWithData(
          (void*)buffer,
          CVPixelBufferGetBaseAddress(buffer),
          CVPixelBufferGetBytesPerRow(buffer) *
          CVPixelBufferGetHeight(buffer),
          ReleasePixelBuffer));

  ScopedRef<CGColorSpaceRef> colorspace(
      CGColorSpaceCreateDeviceRGB());

  return CGImageCreate(
      CVPixelBufferGetWidth(buffer),
      CVPixelBufferGetHeight(buffer),
      8,
      32,
      CVPixelBufferGetBytesPerRow(buffer),
      colorspace,
      kCGBitmapByteOrder32Little | kCGImageAlphaNoneSkipFirst,
      provider,
      NULL,
      true,
      kCGRenderingIntentDefault);
}

CGImageRef ConvertImage(CGImageRef src_image,
                        int max_width,
                        int max_height,
                        int bits_per_component,
                        CGBitmapInfo bitmap_info) CF_RETURNS_RETAINED;
CGImageRef ConvertImage(CGImageRef src_image,
                        int max_width,
                        int max_height,
                        int bits_per_component,
                        CGBitmapInfo bitmap_info) {
  const int src_width = CGImageGetWidth(src_image);
  const int src_height = CGImageGetHeight(src_image);
  const float s = std::max((float)max_width / src_width,
                           (float)max_height / src_height);
  const int width = static_cast<int>(src_width * s);
  const int height = static_cast<int>(src_height * s);

  int bytes_per_row = 0;
  switch (bitmap_info & kCGBitmapByteOrderMask) {
    case kCGBitmapByteOrder16Little:
    case kCGBitmapByteOrder16Big:
      bytes_per_row = width * 2;
      break;
    case kCGBitmapByteOrder32Little:
    case kCGBitmapByteOrder32Big:
    default:
      bytes_per_row = width * 4;
      break;
  }

  ScopedRef<CGColorSpaceRef> colorspace(
      CGColorSpaceCreateDeviceRGB());

  ScopedRef<CGContextRef> context(
      CGBitmapContextCreate(
          NULL, width, height, bits_per_component,
          bytes_per_row, colorspace, bitmap_info));

  CGContextDrawImage(context, CGRectMake(0, 0, width, height), src_image);

  return CGBitmapContextCreateImage(context);
}

UIImageOrientation ExifToUIImageOrientation(int exif_orientation) {
  switch (exif_orientation) {
    default:
    case 1: return UIImageOrientationUp;
    case 2: return UIImageOrientationUpMirrored;
    case 3: return UIImageOrientationDown;
    case 4: return UIImageOrientationDownMirrored;
    case 5: return UIImageOrientationLeftMirrored;
    case 6: return UIImageOrientationRight;
    case 7: return UIImageOrientationRightMirrored;
    case 8: return UIImageOrientationLeft;
  }
}

int AssetToExifOrientation(int asset_orientation) {
  switch (asset_orientation) {
    default:
    case ALAssetOrientationUp:            return 1;
    case ALAssetOrientationDown:          return 3;
    case ALAssetOrientationLeft:          return 8;
    case ALAssetOrientationRight:         return 6;
    case ALAssetOrientationUpMirrored:    return 2;
    case ALAssetOrientationDownMirrored:  return 4;
    case ALAssetOrientationLeftMirrored:  return 5;
    case ALAssetOrientationRightMirrored: return 7;
  }
}

bool DecompressCommon(
    Image* dest, CGImageSourceRef image_src,
    float load_size, Dict* properties) {
  if (CGImageSourceGetCount(image_src) < 1) {
    LOG("no images found");
    return false;
  }
  if (load_size <= 0) {
    dest->acquire(CGImageSourceCreateImageAtIndex(image_src, 0, NULL));
  } else {
    dest->acquire(
        CGImageSourceCreateThumbnailAtIndex(
            image_src, 0,
            Dict(kCGImageSourceCreateThumbnailFromImageAlways, true,
                 kCGImageSourceThumbnailMaxPixelSize, load_size,
                 kCGImageSourceCreateThumbnailWithTransform, true)));
  }
  if (!dest->get()) {
    LOG("unable to create CGImage");
    return false;
  }

  Dict tmp_properties;
  if (!properties) {
    properties = &tmp_properties;
  }

  properties->acquire(
      (__bridge_transfer id)CGImageSourceCopyPropertiesAtIndex(image_src, 0, NULL));
  dest->set_exif_orientation(
      [[*properties objectForKey:(NSString*)kCGImagePropertyOrientation] intValue]);
  return true;
}

}  // namespace

string ImageSHA1Fingerprint(CGImageRef source_image) {
  // CGBitmapInfo represents the pixel format used in the raw image data.  Thumbnails from the asset library
  // on current-generation phones use AlphaNoneSkipFirst | ByteOrder16Little.  This is the most time-sensitive
  // case, so we fingerprint that version and convert anything else when we see it. (if we load from a jpeg
  // instead of the assets library, or load a full-size asset, we generally get AlphaNoneSkipLast |
  // ByteOrder32Little, and there are reports that on first-generation phones the defaults were different).
  const CGBitmapInfo target_bitmap_info = kCGImageAlphaNoneSkipFirst | kCGBitmapByteOrder16Little;
  const CGBitmapInfo bitmap_info = CGImageGetBitmapInfo(source_image);

  Image image;
  if (bitmap_info != target_bitmap_info) {
    LOG("image: converting image from %x to %x for fingerprint", bitmap_info, target_bitmap_info);
    image.acquire(ConvertImage(source_image, CGImageGetWidth(source_image), CGImageGetHeight(source_image),
                               5 /* bits_per_component */, target_bitmap_info));
  } else {
    image.reset(source_image);
  }

  // Note that CGImageGetDataProvider() does not return a retained reference
  // (so no ScopedRef).
  CGDataProviderRef data_provider = CGImageGetDataProvider(image);
  if (!data_provider) {
    return string();
  }
  ScopedRef<CFDataRef> data(CGDataProviderCopyData(data_provider));
  if (!data.get()) {
    return string();
  }

  // SHA1 is approximately the same speed as MD5 here, presumably because the
  // majority of the time is spent simply retrieving the thumbnail bytes.
  //
  // The image is composed of "height" rows. We want to only include the actual
  // image bytes in the SHA1 value. For aspectRatioThumbnail, it appears that
  // bytes_per_row is always 240 even when the width of the image is
  // significantly less. For example, if width is 90 (and bits_per_pixel is 2),
  // there will be 60 bytes at the end of each row that we do not want to
  // include in the fingerprint.
  const int bytes_per_row = CGImageGetBytesPerRow(image);
  const int bits_per_pixel = CGImageGetBitsPerPixel(image);
  const int width = CGImageGetWidth(image);
  const int image_bytes_per_row = width * ((bits_per_pixel + 7) / 8);
  const int height = CGImageGetHeight(image);
  const uint8_t* pixels = (const uint8_t*)CFDataGetBytePtr(data);
  CC_SHA1_CTX ctx;
  CC_SHA1_Init(&ctx);
  for (int i = 0; i < height; ++i) {
    const uint8_t* row = &pixels[i * bytes_per_row];
    CC_SHA1_Update(&ctx, row, image_bytes_per_row);
  }
  uint8_t digest[CC_SHA1_DIGEST_LENGTH];
  CC_SHA1_Final(digest, &ctx);
  return BinaryToHex(Slice((const char*)digest, ARRAYSIZE(digest)));
}

float StrongCompareImages(const Image& a_image, const Image& b_image) {
  if (CGImageGetBitmapInfo(a_image) != CGImageGetBitmapInfo(b_image)) {
    return 255;
  }

  CGDataProviderRef a_data_provider = CGImageGetDataProvider(a_image);
  if (!a_data_provider) {
    return 255;
  }
  ScopedRef<CFDataRef> a_data(CGDataProviderCopyData(a_data_provider));
  if (!a_data.get()) {
    return 255;
  }
  const int a_bits_per_pixel = CGImageGetBitsPerPixel(a_image);
  if (a_bits_per_pixel != 32) {
    return 255;
  }
  const int a_bytes_per_row = CGImageGetBytesPerRow(a_image);
  const int a_width = CGImageGetWidth(a_image);
  const int a_height = CGImageGetHeight(a_image);
  const uint8_t* a_pixels = (const uint8_t*)CFDataGetBytePtr(a_data);

  CGDataProviderRef b_data_provider = CGImageGetDataProvider(b_image);
  if (!b_data_provider) {
    return 255;
  }
  ScopedRef<CFDataRef> b_data(CGDataProviderCopyData(b_data_provider));
  if (!b_data.get()) {
    return 255;
  }
  const int b_bits_per_pixel = CGImageGetBitsPerPixel(b_image);
  if (b_bits_per_pixel != 32) {
    return 255;
  }
  const int b_bytes_per_row = CGImageGetBytesPerRow(b_image);
  const int b_width = CGImageGetWidth(b_image);
  const int b_height = CGImageGetHeight(b_image);
  const uint8_t* b_pixels = (const uint8_t*)CFDataGetBytePtr(b_data);

  if (a_width != b_width || a_height != b_height) {
    // Dimensions differ.
    return 255;
  }

  float sum_of_squares = 0;
  for (int i = 0; i < a_height; ++i) {
    const uint8_t* a_row = &a_pixels[i * a_bytes_per_row];
    const uint8_t* b_row = &b_pixels[i * b_bytes_per_row];
    for (int j = 0; j < a_width * 4; ++j) {
      const float d = (float(a_row[j]) - float(b_row[j])) / 255;
      sum_of_squares += d * d;
    }
  }
  // return 255 * sqrt(sum_of_squares / ((a_height - 2) * (a_width - 2) * 3));
  return 255 * sqrt(sum_of_squares / (a_height * a_width * 3));
}

float StrongCompareImages(const string& a_path, const string& b_path) {
  const int kMaxDim = 960;

  Image a_image;
  if (!a_image.Decompress(a_path, kMaxDim, NULL)) {
    return 255;
  }
  const float a_max_dim =
      std::max<float>(a_image.pixel_width(), a_image.pixel_height());

  Image b_image;
  if (!b_image.Decompress(b_path, a_max_dim, NULL)) {
    return 255;
  }

  // b might be smaller than a. If it is, we need to downscale a. Easiest
  // method is to just reload a.
  if (b_image.pixel_width() < a_image.pixel_width() ||
      b_image.pixel_height() < a_image.pixel_height()) {
    const float b_max_dim =
        std::max<float>(b_image.pixel_width(), b_image.pixel_height());
    if (!b_image.Decompress(a_path, b_max_dim, NULL)) {
      return 255;
    }
  }
  return StrongCompareImages(a_image, b_image);
}

Image::Image(const Image& image)
    : ScopedRef<CGImageRef>(image),
      exif_orientation_(image.exif_orientation_),
      scale_(image.scale_) {
}

Image::Image(CGImageRef image)
    : ScopedRef<CGImageRef>(image),
      exif_orientation_(0),
      scale_(1) {
}

Image::Image(CVPixelBufferRef buffer, int orientation)
    : ScopedRef<CGImageRef>(MakeImage(buffer)),
      exif_orientation_(orientation),
      scale_(1) {
}

Image::Image(CMSampleBufferRef buffer, int orientation)
    : ScopedRef<CGImageRef>(MakeImage(CMSampleBufferGetImageBuffer(buffer))),
      exif_orientation_(orientation),
      scale_(1) {
}

Image::~Image() {
}

UIImage* Image::MakeUIImage() const {
  return [[UIImage alloc]
           initWithCGImage:get()
                     scale:scale_
               orientation:ExifToUIImageOrientation(exif_orientation_)];
}

NSData* Image::CompressJPEG(Dict* properties, float quality) const {
  const int capacity_guess =
      static_cast<int>(bytes_per_row() * height() * 0.20);
  NSMutableData* data =
      [[NSMutableData alloc] initWithCapacity:capacity_guess];
  ScopedRef<CGImageDestinationRef> image_dest(
      CGImageDestinationCreateWithData((__bridge CFMutableDataRef)data,
                                       kUTTypeJPEG, 1, NULL));
  if (!image_dest) {
    LOG("unable to compress image");
    return NULL;
  }

  Dict tmp_properties;
  if (!properties) {
    properties = &tmp_properties;
  }
  if (exif_orientation_ > 0) {
    properties->insert(kCGImagePropertyOrientation, exif_orientation_);
  }
  properties->insert(kCGImageDestinationLossyCompressionQuality, quality);

  CGImageDestinationAddImage(image_dest, get(), *properties);
  if (!CGImageDestinationFinalize(image_dest)) {
    LOG("image finalization failed");
    return NULL;
  }
  return data;
}

NSData* Image::CompressPNG(Dict* properties) const {
  const int capacity_guess =
      static_cast<int>(bytes_per_row() * height() * 0.50);
  NSMutableData* data =
      [[NSMutableData alloc] initWithCapacity:capacity_guess];
  ScopedRef<CGImageDestinationRef> image_dest(
      CGImageDestinationCreateWithData((__bridge CFMutableDataRef)data,
                                       kUTTypePNG, 1, NULL));
  if (!image_dest) {
    LOG("unable to compress image");
    return NULL;
  }
  Dict tmp_properties;
  if (!properties) {
    properties = &tmp_properties;
  }
  CGImageDestinationAddImage(image_dest, get(), *properties);
  if (!CGImageDestinationFinalize(image_dest)) {
    LOG("image finalization failed");
    return NULL;
  }
  return data;
}

bool Image::Decompress(
    const string& path, float load_size, Dict* properties) {
  NSURL* url = [NSURL fileURLWithPath:NewNSString(path)];
  ScopedRef<CGImageSourceRef> image_src(
      CGImageSourceCreateWithURL((__bridge CFURLRef)url, NULL));
  if (!image_src) {
    LOG("%s: unable to decompress image", path);
    return false;
  }
  return DecompressCommon(this, image_src, load_size, properties);
}

bool Image::Decompress(
    NSData* data, float load_size, Dict* properties) {
  ScopedRef<CGImageSourceRef> image_src(
      CGImageSourceCreateWithData((__bridge CFDataRef)data, NULL));
  if (!image_src) {
    LOG("unable to decompress image");
    return false;
  }
  return DecompressCommon(this, image_src, load_size, properties);
}

Image Image::Convert(CGSize size, int bits_per_pixel) const {
  // The incoming size is specified in the same orientation as the image.
  if (size.width < 0) {
    size.width = width();
  }
  if (size.height < 0) {
    size.height = height();
  }
  // Adjust the incoming size to be in the same coordinate system as the
  // underlying image bytes.
  size = ToImageCoordinates(size);

  int bits_per_component = 0;
  CGBitmapInfo bitmap_info = 0;
  if (bits_per_pixel == 16) {
    bits_per_component = 5;
    bitmap_info = kCGBitmapByteOrderDefault | kCGImageAlphaNoneSkipFirst;
  } else if (bits_per_pixel == 32) {
    bits_per_component = 8;
    bitmap_info = kCGBitmapByteOrderDefault | kCGImageAlphaNoneSkipLast;
  } else {
    bits_per_component = this->bits_per_component();
    bitmap_info = CGImageGetBitmapInfo(get());
  }
  Image new_image(
      ConvertImage(get(), size.width * scale_, size.height * scale_,
                   bits_per_component, bitmap_info));
  new_image.exif_orientation_ = exif_orientation_;
  new_image.scale_ = scale_;
  return new_image;
}

CGSize Image::ToImageCoordinates(const CGSize& s) const {
  switch (exif_orientation_) {
    case 5:  // UIImageOrientationLeftMirrored
    case 6:  // UIImageOrientationRight
    case 7:  // UIImageOrientationRightMirrored
    case 8:  // UIImageOrientationLeft
      return CGSizeMake(s.height, s.width);
  }
  return s;
}

int Image::pixel_width() const {
  switch (exif_orientation_) {
    default:
    case 1:  // UIImageOrientationUp
    case 2:  // UIImageOrientationUpMirrored
    case 3:  // UIImageOrientationDown
    case 4:  // UIImageOrientationDownMirrored
      return CGImageGetWidth(get());
    case 5:  // UIImageOrientationLeftMirrored
    case 6:  // UIImageOrientationRight
    case 7:  // UIImageOrientationRightMirrored
    case 8:  // UIImageOrientationLeft
      return CGImageGetHeight(get());
  }
}

int Image::pixel_height() const {
  switch (exif_orientation_) {
    default:
    case 1:  // UIImageOrientationUp
    case 2:  // UIImageOrientationUpMirrored
    case 3:  // UIImageOrientationDown
    case 4:  // UIImageOrientationDownMirrored
      return CGImageGetHeight(get());
    case 5:  // UIImageOrientationLeftMirrored
    case 6:  // UIImageOrientationRight
    case 7:  // UIImageOrientationRightMirrored
    case 8:  // UIImageOrientationLeft
      return CGImageGetWidth(get());
  }
}

int Image::bytes_per_row() const {
  return CGImageGetBytesPerRow(get());
}

int Image::bits_per_component() const {
  return CGImageGetBitsPerComponent(get());
}

void Image::set_asset_orientation(int v) {
  exif_orientation_ = AssetToExifOrientation(v);
}

float Image::aspect_ratio() const {
  return (float)width() / height();
}

// local variables:
// mode: c++
// end:
