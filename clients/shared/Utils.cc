// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "ActivityMetadata.pb.h"
#import "CommentMetadata.pb.h"
#import "EpisodeStats.pb.h"
#import "Location.pb.h"
#import "PhotoMetadata.pb.h"
#import "Placemark.pb.h"
#import "StringUtils.h"
#import "Utils.h"
#import "ViewpointMetadata.pb.h"

ostream& operator<<(ostream& os, const ActivityId& i) {
  os << i.local_id() << "[" << ServerIdFormat(i.server_id()) << "]";
  return os;
}

ostream& operator<<(ostream& os, const CommentId& i) {
  os << i.local_id() << "[" << ServerIdFormat(i.server_id()) << "]";
  return os;
}

ostream& operator<<(ostream& os, const EpisodeId& i) {
  os << i.local_id() << "[" << ServerIdFormat(i.server_id()) << "]";
  return os;
}

ostream& operator<<(ostream& os, const EpisodeStats& s) {
  os << "{\n";
  os << "  posted_photos: " << s.posted_photos() << ",\n";
  os << "  removed_photos: " << s.removed_photos() << "\n";
  os << "}";
  return os;
}

ostream& operator<<(ostream& os, const PhotoId& i) {
  os << i.local_id() << "[" << ServerIdFormat(i.server_id()) << "]";
  return os;
}

ostream& operator<<(ostream& os, const ViewpointId& i) {
  os << i.local_id() << "[" << ServerIdFormat(i.server_id()) << "]";
  return os;
}

ostream& operator<<(ostream& os, const ServerIdFormat& f) {
  if (f.id.empty()) {
    os << "-";
    return os;
  }
  const string decoded = Base64HexDecode(f.id.substr(1));
  uint64_t device_id = 0;
  uint64_t device_local_id = 0;

  Slice s(decoded);
  // Viewpoint and operation server ids do not contain timestamps.

  // TODO(pmattis): This logic deserves to be in ServerId.{h,mm}.
  if (f.id[0] != 'v' && f.id[0] != 'o') {
    if (decoded.size() < 4) {
      os << f.id;
      return os;
    }
    // Skip the timestamp.
    s.remove_prefix(4);
  }

  device_id = Varint64Decode(&s);
  device_local_id = Varint64Decode(&s);
  os << f.id
     << "/" << device_id
     << "/" << device_local_id;
  return os;
}

ostream& operator<<(ostream& os, const Location& l) {
  os << "(" << l.latitude() << ", " << l.longitude() << ")";
  return os;
}

ostream& operator<<(ostream& os, const Placemark& p) {
  vector<const char*> parts;
  if (p.has_sublocality()) parts.push_back(p.sublocality().c_str());
  if (p.has_locality()) parts.push_back(p.locality().c_str());
  if (p.has_state()) parts.push_back(p.state().c_str());
  if (p.has_country()) parts.push_back(p.country().c_str());
  os << Join(parts.begin(), parts.end(), ", ");
  return os;
}

ostream& operator<<(ostream& os, const google::protobuf::Message& msg) {
  os << msg.DebugString();
  return os;
}

/*
 * The authors of this software are Rob Pike and Ken Thompson.
 *              Copyright (c) 2002 by Lucent Technologies.
 * Permission to use, copy, modify, and distribute this software for any
 * purpose without fee is hereby granted, provided that this entire notice
 * is included in all copies of any software which is or includes a copy
 * or modification of this software and in all copies of the supporting
 * documentation for such software.
 * THIS SOFTWARE IS BEING PROVIDED "AS IS", WITHOUT ANY EXPRESS OR IMPLIED
 * WARRANTY.  IN PARTICULAR, NEITHER THE AUTHORS NOR LUCENT TECHNOLOGIES MAKE ANY
 * REPRESENTATION OR WARRANTY OF ANY KIND CONCERNING THE MERCHANTABILITY
 * OF THIS SOFTWARE OR ITS FITNESS FOR ANY PARTICULAR PURPOSE.
 */

namespace {

typedef signed int Rune;

enum
{
  UTFmax	= 4,		/* maximum bytes per rune */
  Runesync	= 0x80,		/* cannot represent part of a UTF sequence (<) */
  Runeself	= 0x80,		/* rune and UTF sequences are the same (<) */
  Runeerror	= 0xFFFD,	/* decoding error in UTF */
  Runemax	= 0x10FFFF,	/* maximum rune value */
};

}  // namespace

namespace re2 {

int chartorune(Rune* r, const char* s);
int fullrune(const char* s, int n);

}  // namespace re2

int utfnlen(const char* s, int m) {
  int n;
  Rune rune;
  const char *es = s + m;
  for (n = 0; s < es; n++) {
    int c = *(unsigned char*)s;
    if (c < Runeself){
      if (c == '\0')
        break;
      s++;
      continue;
    }
    if (!re2::fullrune(s, es - s))
      break;
    s += re2::chartorune(&rune, s);
  }
  return n;
}

int utfnext(Slice* s) {
  if (s->empty()) {
    return -1;
  }
  int c = *(unsigned char*)s->data();
  if (c < Runeself) {
    s->remove_prefix(1);
    return c;
  }
  if (!re2::fullrune(s->data(), s->size())) {
    return -1;
  }
  Rune rune;
  s->remove_prefix(re2::chartorune(&rune, s->data()));
  return rune;
}

// local variables:
// mode: c++
// end:
