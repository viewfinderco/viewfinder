// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "DB.h"
#import "Format.h"
#import "Logging.h"
#import "Mutex.h"
#import "ServerId.h"
#import "StringUtils.h"

namespace {

// NOTE: these should be kept up to date with the id prefixes used by
//       the server. These can be found in backend/db/id_prefix.py.
const char* kActivityPrefix = "a";
const char* kCommentPrefix = "c";
const char* kEpisodePrefix = "e";
const char* kOperationPrefix = "o";
const char* kPhotoPrefix = "p";
const char* kViewpointPrefix = "v";

bool DecodeId(const char* prefix, const Slice& server_id, int64_t* device_id,
              int64_t* local_id, WallTime* timestamp, bool reverse_timestamp) {
  if (server_id.empty() ||
      !server_id.starts_with(prefix)) {
    return false;
  }

  const string decoded = Base64HexDecode(server_id.substr(1));
  Slice s(decoded);

  if (decoded.size() < 4) {
    return false;
  }
  *timestamp = Fixed32Decode(&s);
  if (reverse_timestamp) {
    *timestamp = (1ULL << 32) - *timestamp - 1;
  }

  *device_id = Varint64Decode(&s);
  *local_id = Varint64Decode(&s);
  return true;
}

bool DecodeId(const char* prefix, const Slice& server_id,
              int64_t* device_id, int64_t* local_id) {
  if (server_id.empty() ||
      !server_id.starts_with(prefix)) {
    return false;
  }

  const string decoded = Base64HexDecode(server_id.substr(1));
  Slice s(decoded);

  *device_id = Varint64Decode(&s);
  *local_id = Varint64Decode(&s);
  return true;
}

string EncodeId(const char* prefix, int64_t device_id, int64_t local_id) {
  string encoded;
  Varint64Encode(&encoded, device_id);
  Varint64Encode(&encoded, local_id);
  return Format("%s%s", prefix, Base64HexEncode(encoded, false));
}

string EncodeId(const char* prefix, int64_t device_id, int64_t local_id,
                WallTime timestamp, bool reverse_timestamp) {
  if (timestamp < 0) {
    // If timestamp is negative, just use the current time.
    timestamp = WallTime_Now();
  }

  string encoded;
  if (reverse_timestamp) {
    timestamp = (1ULL << 32) - int(timestamp) - 1;
  }
  Fixed32Encode(&encoded, timestamp);
  Varint64Encode(&encoded, device_id);
  Varint64Encode(&encoded, local_id);
  return Format("%s%s", prefix, Base64HexEncode(encoded, false));
}

}  // namespace


string EncodeActivityId(int64_t device_id, int64_t local_id, WallTime timestamp) {
  return EncodeId(kActivityPrefix, device_id, local_id, timestamp, true);
}

string EncodeCommentId(int64_t device_id, int64_t local_id, WallTime timestamp) {
  return EncodeId(kCommentPrefix, device_id, local_id, timestamp, false);
}

string EncodeEpisodeId(int64_t device_id, int64_t local_id, WallTime timestamp) {
  return EncodeId(kEpisodePrefix, device_id, local_id, timestamp, true);
}

string EncodePhotoId(int64_t device_id, int64_t local_id, WallTime timestamp) {
  return EncodeId(kPhotoPrefix, device_id, local_id, timestamp, true);
}

string EncodeOperationId(int64_t device_id, int64_t local_id) {
  return EncodeId(kOperationPrefix, device_id, local_id);
}

string EncodeViewpointId(int64_t device_id, int64_t local_id) {
  return EncodeId(kViewpointPrefix, device_id, local_id);
}


bool DecodeActivityId(const Slice& server_id, int64_t* device_id,
                      int64_t* local_id, WallTime* timestamp) {
  return DecodeId(kActivityPrefix, server_id, device_id, local_id, timestamp, true);
}

bool DecodeCommentId(const Slice& server_id, int64_t* device_id,
                     int64_t* local_id, WallTime* timestamp) {
  return DecodeId(kCommentPrefix, server_id, device_id, local_id, timestamp, false);
}

bool DecodeEpisodeId(const Slice& server_id, int64_t* device_id,
                     int64_t* local_id, WallTime* timestamp) {
  return DecodeId(kEpisodePrefix, server_id, device_id, local_id, timestamp, true);
}

bool DecodePhotoId(const Slice& server_id, int64_t* device_id,
                   int64_t* local_id, WallTime* timestamp) {
  return DecodeId(kPhotoPrefix, server_id, device_id, local_id, timestamp, true);
}

bool DecodeOperationId(const Slice& server_id, int64_t* device_id, int64_t* local_id) {
  return DecodeId(kOperationPrefix, server_id, device_id, local_id);
}

bool DecodeViewpointId(const Slice& server_id, int64_t* device_id, int64_t* local_id) {
  return DecodeId(kViewpointPrefix, server_id, device_id, local_id);
}
