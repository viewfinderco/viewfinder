// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <stdlib.h>
#import "DigestUtils.h"
#import "Logging.h"

string MD5HexToBase64(const Slice& str) {
  if (str.size() != 32) {
    DCHECK_EQ(32, str.size());
    return string();
  }
  uint8_t digest[16];  // CC_MD5_DIGEST_LENGTH == 16
  char buf[3] = { '\0', '\0', '\0' };
  for (int i = 0; i < ARRAYSIZE(digest); i++) {
    buf[0] = str[2 * i];
    buf[1] = str[2 * i + 1];
    digest[i] = strtol(buf, 0, 16);
  }
  return Base64Encode(Slice((char*)digest, ARRAYSIZE(digest)));
}
