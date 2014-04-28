// Copyright 2013 Viewfinder. All Rights Reserved.
// Author: Ben Darnell
//
// This file must contain minimal dependencies as it is used from outside the iOS client.
// Also note that it is plain c++ rather than objective-c++.

#ifndef VIEWFINDER_IMAGE_FINGERPRINT_H
#define VIEWFINDER_IMAGE_FINGERPRINT_H

#include <vector>
#include <string>
#include <CoreGraphics/CGImage.h>
#import "ImageFingerprint.pb.h"

// Generate a perceptual fingerprint of the image. The aspect_ratio corresponds
// to the aspect ratio (width / height) of the full image, of which the image
// being fingerprinted may be a square center crop.
ImageFingerprint FingerprintImage(CGImageRef image, float aspect_ratio);

// Prepare the src image for fingerprinting, converting the image to grayscale
// and scaling it down appropriately. Only provided here for testing purposes.
CGImageRef FingerprintPrepareImage(CGImageRef src, float aspect_ratio);

#endif  // VIEWFINDER_IMAGE_FINGERPRINT_H
