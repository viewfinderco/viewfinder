// Copyright 2012 Viewfinder. All rights reserved.
// Author: Ben Darnell
//
// See ImageIndex.mm for comments.  This file contains the core of the fingerprinting algorithm,
// extracted into a separate file so it can be used in other contexts.

#include <Accelerate/Accelerate.h>
#include <CoreGraphics/CGContext.h>
#include <CoreGraphics/CGBitmapContext.h>
#include <assert.h>
#include "ImageFingerprint.h"
#include "ImageFingerprintPrivate.h"

using std::string;
using std::vector;

namespace {

// The 2D Haar discrete wavelet transform. The resulting value at location x[0]
// is the average of all the input values.
template <int N>
void Haar2D(float* x) {
  float t[N];
  // Decompose rows.
  for (int i = 0; i < N; ++i) {
    for (int n = N / 2; n >= 1; n /= 2) {
      for (int k = 0; k < n * 2; ++k) {
        t[k] = x[i * N + k];
      }
      for (int k = 0; k < n; ++k) {
        x[i * N + k] = (t[2 * k] + t[2 * k + 1]) / 2;
        x[i * N + k + n] = (t[2 * k] - t[2 * k + 1]);
      }
    }
  }
  // Decompose columns.
  for (int i = 0; i < N; ++i) {
    for (int n = N / 2; n >= 1; n /= 2) {
      for (int k = 0; k < n * 2; ++k) {
        t[k] = x[k * N + i];
      }
      for (int k = 0; k < n; ++k) {
        x[k * N + i] = (t[2 * k] + t[2 * k + 1]) / 2;
        x[(k + n) * N + i] = (t[2 * k] - t[2 * k + 1]);
      }
    }
  }
}

// Returns true if the bottom row of the image is blank and the top row of the
// image is not blank. This is intended to provide a signal of the iOS6 aspect
// ratio thumbnail bug which leaves a blank row at the bottom of the image
// without also capturing images that contain a white border.
bool BottomRowIsBlank(CGImageRef image) {
  CGDataProviderRef data_provider = CGImageGetDataProvider(image);
  if (!data_provider) {
    return false;
  }
  CFDataRef data = CGDataProviderCopyData(data_provider);
  if (!data) {
    return false;
  }

  bool result = false;
  const int bits_per_pixel = CGImageGetBitsPerPixel(image);
  if (bits_per_pixel == 32) {
    const int bytes_per_row = CGImageGetBytesPerRow(image);
    const int width = CGImageGetWidth(image);
    const int height = CGImageGetHeight(image);
    const int image_bytes_per_row = width * ((bits_per_pixel + 7) / 8);
    const uint8_t* pixels = (const uint8_t*)CFDataGetBytePtr(data);
    result = true;
    const uint8_t* ptr = pixels + (height - 1) * bytes_per_row;
    for (int i = 0; i < image_bytes_per_row; ++i) {
      if (ptr[i] != 255) {
        result = false;
        break;
      }
    }
    if (result) {
      // Verify the top row is not blank too. If both the top and bottom row
      // are blank, the image probably has a border.
      const uint8_t* ptr = pixels;
      result = false;
      for (int i = 0; i < image_bytes_per_row; ++i) {
        if (ptr[i] != 255) {
          result = true;
          break;
        }
      }
    }
  } else if (bits_per_pixel == 16) {
    const int bytes_per_row = CGImageGetBytesPerRow(image);
    const int width = CGImageGetWidth(image);
    const int height = CGImageGetHeight(image);
    const uint8_t* pixels = (const uint8_t*)CFDataGetBytePtr(data);
    result = true;
    const uint16_t* ptr = (const uint16_t*)(pixels + (height - 1) * bytes_per_row);
    const CGBitmapInfo bitmap_info = CGImageGetBitmapInfo(image);
    uint16_t white = 0xffff;
    // NOTE(peter): most of the bitmap/alpha info combinations are not valid,
    // but we support as much as possible...just in case.
    switch (bitmap_info & kCGBitmapAlphaInfoMask) {
      case kCGImageAlphaNone:
        break;
      case kCGImageAlphaPremultipliedLast:
      case kCGImageAlphaLast:
      case kCGImageAlphaNoneSkipLast:
        if (bitmap_info & kCGBitmapByteOrder16Big) {
          white = 0xfeff;
        } else {
          white = 0xfffe;
        }
        break;
      case kCGImageAlphaPremultipliedFirst:
      case kCGImageAlphaFirst:
      case kCGImageAlphaNoneSkipFirst:
        if (bitmap_info & kCGBitmapByteOrder16Big) {
          white = 0xff7f;
        } else {
          white = 0x7fff;
        }
        break;
    }
    for (int i = 0; i < width; ++i) {
      if ((ptr[i] & white) != white) {
        result = false;
        break;
      }
    }
    if (result) {
      // Verify the top row is not blank too. If both the top and bottom row
      // are blank, the image probably has a border.
      const uint16_t* ptr = (const uint16_t*)pixels;
      result = false;
      for (int i = 0; i < width; ++i) {
        if ((ptr[i] & white) != white) {
          result = true;
          break;
        }
      }
    }
  } else {
    // TODO(peter): Handle other bit-per-pixel values?
    // assert(false);
  }
  CFRelease(data);
  return result;
}

// Convert the source image to grayscale and perform a square center crop. This
// allows fingerprints of square thumbnails to be compared to fingerprints of
// aspect ratio thumbnails.
//
// iOS6 aspect ratio thumbnails have a bug where the bottom row of pixels is
// sometimes all white. More specifically, it appears that the thumbnail was
// incorrectly drawn such that the image was shifted up by one pixel, exposing
// a bottom row of white pixels and cropping off the top row of pixels. Square
// thumbnails do not exhibit this problem and iOS7 aspect ratio thumbnails do
// not exhibit this problem.
//
// We attempt to normalize the source image, cropping the portion of the image
// which is consistent between the aspect ratio thumbnails (with and without
// the iOS6 bug) and the square thumbnails. The normalization consists of
// cropping out a 1 pixel border from the smaller dimension of the 120 aspect
// ratio thumbnail. This gets mildly complicated because 1 pixel in the 120
// aspect ratio thumbnail translates into >1 pixel for the 150 square
// thumbnails and the non-120 (iPad and iOS 7) aspect ratio thumbnails.
void ToGrayscaleImage(CGImageRef src, int N, float aspect_ratio, void* dest) {
  const float w = CGImageGetWidth(src);
  const float h = CGImageGetHeight(src);
  const float max_dim = std::max<float>(w, h);
  const float src_aspect_ratio = w / h;
  // The size of the border to trim from image. We trim a 1 pixel border from
  // aspect ratio thumbnails with a maximum dimension of 120. For all other
  // source images we scale up the size of the border accordingly.
  const float border = (aspect_ratio >= 1) ?
      ((max_dim * (aspect_ratio / src_aspect_ratio)) / 120) :
      ((max_dim / (aspect_ratio / src_aspect_ratio)) / 120);

  CGRect src_rect = CGRectMake(0, 0, w, h);
  if (w == h) {
    // Square aspect ratio, trim both directions.
    src_rect.origin.y += border;
    src_rect.size.height -= 2 * border;
    src_rect.origin.x += border;
    src_rect.size.width -= 2 * border;
  } else if (w > h) {
    // Horizontal aspect ratio, only trim vertically.
    src_rect.origin.y += border;
    src_rect.size.height -= 2 * border;
  } else if (h > w) {
    // Vertical aspect ratio, only trim horizontally.
    src_rect.origin.x += border;
    src_rect.size.width -= 2 * border;
  }
  if (BottomRowIsBlank(src)) {
    // The bottom row is blank, indicating that the image was shifted up 1
    // pixel.
    src_rect.origin.y += 1;
    src_rect.size.height -= 1;
  }

  const float s = N / std::min<float>(src_rect.size.width, src_rect.size.height);
  CGAffineTransform t = CGAffineTransformIdentity;
  t = CGAffineTransformTranslate(t, N / 2, N / 2);
  t = CGAffineTransformScale(t, s, s);
  t = CGAffineTransformTranslate(t, -CGRectGetMidX(src_rect), -CGRectGetMidY(src_rect));
  const CGRect dest_rect = CGRectApplyAffineTransform(CGRectMake(0, 0, w, h), t);

  CGColorSpaceRef colorspace(CGColorSpaceCreateDeviceGray());
  CGContextRef context(CGBitmapContextCreate(
                           dest, N, N, 8, N, colorspace, kCGImageAlphaNone));
  CGContextSetInterpolationQuality(context, kCGInterpolationMedium);
  CGContextDrawImage(context, dest_rect, src);
  CFRelease(context);
  CFRelease(colorspace);
}

void BlurImage(int N, void* src, void* dest) {
  vImage_Buffer src_buf = { src, N, N, N };
  vImage_Buffer dest_buf = { dest, N, N, N };
  // Note, that while kvImageEdgeExtend might seem a better option, it actually
  // produces much worse fingerprints due to the strange 1 pixel shadow on the
  // edges of pre-iOS-7 thumbnails. We blur with a background color of 127 in
  // order to minimize the disturbance of gradients near the edges.
  long result = vImageBoxConvolve_Planar8(
      &src_buf, &dest_buf, NULL, 0, 0, 5, 5, 127,
      kvImageDoNotTile | kvImageBackgroundColorFill);
  assert(result == 0);
}

void ToFloatImage(int N, void* src, void* dest) {
  vImage_Buffer src_buf = { src, N, N, N };
  vImage_Buffer dest_buf = { dest, N, N, N * sizeof(float) };
  long result = vImageConvert_Planar8toPlanarF(
      &src_buf, &dest_buf, 127.5, -127.5, kvImageDoNotTile);
  assert(result == 0);
}

void Rotate90(int N, void* src, void* dest) {
  vImage_Buffer src_buf = { src, N, N, N * sizeof(float) };
  vImage_Buffer dest_buf = { dest, N, N, N * sizeof(float) };
  long result = vImageRotate90_PlanarF(
      &src_buf, &dest_buf, kRotate90DegreesClockwise,
      0, kvImageDoNotTile);
  assert(result == 0);
}

void ReflectHorizontal(int N, void* src, void* dest) {
  vImage_Buffer src_buf = { src, N, N, N * sizeof(float) };
  vImage_Buffer dest_buf = { dest, N, N, N * sizeof(float) };
  long result = vImageHorizontalReflect_PlanarF(
      &src_buf, &dest_buf, kvImageDoNotTile);
  assert(result == 0);
}

void ReflectVertical(int N, void* src, void* dest) {
  vImage_Buffer src_buf = { src, N, N, N * sizeof(float) };
  vImage_Buffer dest_buf = { dest, N, N, N * sizeof(float) };
  long result = vImageVerticalReflect_PlanarF(
      &src_buf, &dest_buf, kvImageDoNotTile);
  assert(result == 0);
}

string HaarToTerm(const float* haar_data) {
  // We use a value of -2 instead of 0 so that small negative deltas are
  // treated the same as positive deltas. Such deltas can occur if there is
  // small bits of noise in an image. For example, consider the fingerprint of
  // an all black image and one containing imperceptible amounts of very dark
  // gray (e.g. 254, 254, 254) noise.
  static const float kHaarThreshold = -2;

  // Perform a zig-zag traveral of the 13x13 upper-left matrix of the resulting
  // data and output a hash bit if the value is greater than 0. It would be
  // slightly better to compute the median here, but the median is ~0 after the
  // Haar transform.
  uint8_t hash[kHaarHashBytes] = { 0 };
  for (int i = 0; i < kHaarHashBits; ++i) {
    // We skip the first 3 entries of haar_data (in the zig-zag traversal)
    // because they give little information. The first entry is the average
    // pixel value across the image. The second and third are the average
    // horizontal and vertical gradients, which were forced to be positive by
    // the orientation normalization.
    if (haar_data[kZigZagOffsets[i + kHaarHashSkip]] >= kHaarThreshold) {
      hash[i / 8] |= 1 << (i % 8);
    }
  }
  return string((const char*)hash, kHaarHashBytes);
}

}  // namespace

CGImageRef FingerprintPrepareImage(CGImageRef src, float aspect_ratio) {
  const int N = kHaarSmallN;
  uint8_t gray_data[N * N] = { 0 };
  ToGrayscaleImage(src, N, aspect_ratio, gray_data);
  CGColorSpaceRef colorspace(CGColorSpaceCreateDeviceGray());
  CGContextRef context(CGBitmapContextCreate(
                           gray_data, N, N, 8, N, colorspace, kCGImageAlphaNone));
  CGImageRef res = CGBitmapContextCreateImage(context);
  CFRelease(context);
  CFRelease(colorspace);
  return res;
}

ImageFingerprint FingerprintImage(CGImageRef image, float aspect_ratio) {
  float haar_buf1[kHaarSmallNxN];
  float haar_buf2[kHaarSmallNxN];
  float* haar_data = haar_buf1;

  {
    // Pre-process the image. First, transform the incoming image to a 32x32
    // grayscale image, distorting if necessary.
    uint8_t gray_data[kHaarSmallNxN] = { 0 };
    ToGrayscaleImage(image, kHaarSmallN, aspect_ratio, gray_data);

    // Apply a 5x5 box filter.
    uint8_t blur_data[kHaarSmallNxN];
    BlurImage(kHaarSmallN, gray_data, blur_data);

    // Convert to floating point values.
    ToFloatImage(kHaarSmallN, blur_data, haar_data);
  }

  ImageFingerprint f;

  // Save the raw float image in case orientation normalization is needed.
  memcpy(haar_buf2, haar_buf1, sizeof(haar_buf1));

  // Apply the Haar2D transform.
  Haar2D<kHaarSmallN>(haar_data);

  // NOTE(peter): Disable the support for normalizing rotation. This works, but
  // increases the indexing cost. And at the present time we don't care to find
  // duplicates that have different orientations.
  if (0) {
    // Force the average horizontal and vertical gradients to be positive and for
    // the horizontal gradient to be larger than the vertical gradient. This
    // normalizes the image orientation.
    float x_gradient = haar_data[kZigZagOffsets[1]];
    float y_gradient = haar_data[kZigZagOffsets[2]];
    const float rotate_gradient = fabs(x_gradient) - fabs(y_gradient);

    if (rotate_gradient < 0 || x_gradient < 0 || y_gradient < 0) {
      // We have to rotate and/or reflect the source. If any of the gradients are
      // smaller than the large thresholds we're uncertain about whether the
      // rotation or reflection is necessary and could thus rotate/reflect one
      // version of the image and not another. We handle this case by indexing
      // both the non-normalized image and the normalized image. Note that pixel
      // values are between [-127.5, 127.5] giving gradients that are in the
      // range [-255, 255].
      static const float kLargeThreshold = 3;

      if ((rotate_gradient < kLargeThreshold && rotate_gradient > -kLargeThreshold) ||
          (x_gradient < kLargeThreshold && x_gradient > -kLargeThreshold) ||
          (y_gradient < kLargeThreshold && y_gradient > -kLargeThreshold)) {
        f.add_terms(HaarToTerm(haar_data));
      }

      float* src = haar_buf2;
      float* tmp = haar_buf1;
      if (rotate_gradient < 0) {
        // LOG("rotate 90: %f %f", x_gradient, y_gradient);
        Rotate90(kHaarSmallN, src, tmp);
        std::swap(src, tmp);
        // When we rotate 90 degrees clockwise, the x and y gradients get swapped
        // and the x gradient gets reflected.
        std::swap(x_gradient, y_gradient);
        x_gradient = -x_gradient;
      }
      if (x_gradient < 0) {
        // LOG("reflect horizontal: %f", x_gradient);
        ReflectHorizontal(kHaarSmallN, src, tmp);
        std::swap(src, tmp);
      }
      if (y_gradient < 0) {
        // LOG("reflect vertical: %f", y_gradient);
        ReflectVertical(kHaarSmallN, src, tmp);
        std::swap(src, tmp);
      }
      haar_data = src;
      Haar2D<kHaarSmallN>(haar_data);
    }
  }

  const string term = HaarToTerm(haar_data);
  if (f.terms_size() == 0 || f.terms(0) != term) {
    f.add_terms(term);
  }
  return f;
}
