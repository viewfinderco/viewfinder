// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "ContentTable.h"
#import "StringUtils.h"

string EncodeContentKey(const string& prefix, int64_t local_id) {
  return prefix + ToString(local_id);
}

string EncodeContentServerKey(const string& prefix, const string& server_id) {
  return prefix + server_id;
}

// local variables:
// mode: c++
// end:
