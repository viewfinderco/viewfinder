// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_IMAGE_H
#define VIEWFINDER_IMAGE_H

#import <CoreGraphics/CGImage.h>
#import <CoreMedia/CMSampleBuffer.h>
#import <CoreVideo/CVPixelBuffer.h>
#import "ScopedRef.h"
#import "ValueUtils.h"

@class UIImage;

class Image : public ScopedRef<CGImageRef> {
 public:
  Image(const Image& image);
  Image(CGImageRef image = NULL);
  Image(CVPixelBufferRef buffer, int orientation = 0);
  Image(CMSampleBufferRef buffer, int orientation = 0);
  ~Image();

  UIImage* MakeUIImage() const;

  NSData* CompressJPEG(Dict* properties, float quality) const;
  NSData* CompressPNG(Dict* properties) const;
  // The decompression routines automatically determine if the source is JPEG
  // or PNG compressed.
  bool Decompress(const string& path, float load_size, Dict* properties);
  bool Decompress(NSData* data, float load_size, Dict* properties);
  Image Convert(CGSize size, int bits_per_pixel) const;

  // Convert the input to image coordinates.
  CGSize ToImageCoordinates(const CGSize& s) const;

  int pixel_width() const;
  int pixel_height() const;
  float width() const { return pixel_width() / scale_; }
  float height() const { return pixel_height() / scale_; }
  int bytes_per_row() const;
  int bits_per_component() const;
  void set_asset_orientation(int v);
  void set_exif_orientation(int v) {
    exif_orientation_ = v;
  }
  int exif_orientation() const { return exif_orientation_; }
  void set_scale(float v) {
    scale_ = v;
  }
  float scale() const { return scale_; }
  float aspect_ratio() const;
  CGSize size() const {
    return CGSizeMake(pixel_width(), pixel_height());
  }

 private:
  int exif_orientation_;
  float scale_;
};

string ImageSHA1Fingerprint(CGImageRef image);

// Performs a root-mean-square comparison of a_image and b_image, returning a
// value in the range [0,255] with smaller values indicating the images are
// similar and larger values indicating the images are different. A value less
// than 1 is a fairly strong indication the images are identical modulo
// compression artifacts.
float StrongCompareImages(const Image& a_image, const Image& b_image);
// Performs a strong image comparision between the images located at a_path and
// b_path. Attempts to load images that are the same size, up to a maximum
// dimension of 960 pixels.
float StrongCompareImages(const string& a_path, const string& b_path);

#endif // VIEWFINDER_IMAGE_H
