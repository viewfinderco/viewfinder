// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis
//
// Constants shared by the ImageFingerprint and ImageIndex code.

#ifndef VIEWFINDER_IMAGE_FINGERPRINT_PRIVATE_H
#define VIEWFINDER_IMAGE_FINGERPRINT_PRIVATE_H

#include <vector>

const int kHaarSmallN = 32;
const int kHaarSmallNxN = kHaarSmallN * kHaarSmallN;
const int kHaarHashN = 13;
const int kHaarHashNxN = kHaarHashN * kHaarHashN;
const int kHaarHashBits = 160;
const int kHaarHashBytes = (kHaarHashBits + 7) / 8;
// Skip the first entry of haar_data (in the zig-zag traversal) because it
// gives little information. The first entry is the average pixel value across
// the image.
const int kHaarHashSkip = 1;

extern const std::vector<int> kZigZagOffsets;

#endif  // VIEWFINDER_IMAGE_FINGERPRINT_PRIVATE_H
