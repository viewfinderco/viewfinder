// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <CommonCrypto/CommonDigest.h>
#import "DigestUtils.h"
#import "StringUtils.h"

string MD5(const Slice& str) {
  uint8_t digest[CC_MD5_DIGEST_LENGTH];
  CC_MD5(str.data(), str.size(), digest);
  return BinaryToHex(Slice((const char*)digest, ARRAYSIZE(digest)));
}
