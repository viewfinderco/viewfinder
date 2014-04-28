// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#include "Exif.h"
#include "Logging.h"

namespace {

const uint16_t kExifBigEndian = 0x4d4d;
const uint16_t kExifLittleEndian = 0x4949;

const int kExifBytesPerFormat[] = {
  0, 1, 1, 2, 4, 8, 1, 1, 2, 4, 8, 4, 8,
};

enum JpegTag {
  kJpegStartOfImage = 0xffd8,
  kJpegEndOfImage = 0xffd9,
  kJpegStartOfScan = 0xffda,
  kJpegApp0 = 0xffe0,
  kJpegApp1 = 0xffe1,
  kJpegApp2 = 0xffe2,
  kJpegApp3 = 0xffe3,
  kJpegApp4 = 0xffe4,
  kJpegApp5 = 0xffe5,
  kJpegApp6 = 0xffe6,
  kJpegApp7 = 0xffe7,
  kJpegApp8 = 0xffe8,
  kJpegApp9 = 0xffe9,
  kJpegApp10 = 0xffea,
  kJpegApp11 = 0xffeb,
  kJpegApp12 = 0xffec,
  kJpegApp13 = 0xffed,
  kJpegApp14 = 0xffee,
  kJpegApp15 = 0xffef,
  kJpegStartOfFrame0 = 0xffc0,
  kJpegStartOfFrame1 = 0xffc1,
  kJpegStartOfFrame2 = 0xffc2,
  kJpegStartOfFrame3 = 0xffc3,
  kJpegStartOfFrame5 = 0xffc5,
  kJpegStartOfFrame6 = 0xffc6,
  kJpegStartOfFrame7 = 0xffc7,
  kJpegStartOfFrame9 = 0xffc9,
  kJpegStartOfFrame10 = 0xffca,
  kJpegStartOfFrame11 = 0xffcb,
  kJpegStartOfFrame13 = 0xffcd,
  kJpegStartOfFrame14 = 0xffce,
  kJpegStartOfFrame15 = 0xffcf,
};

inline int GetUint8(Slice s, int offset) {
  if (s.size() < offset + sizeof(uint8_t)) {
    return -1;
  }
  return *reinterpret_cast<const uint8_t*>(s.data() + offset);
}

inline int GetUint16(Slice s, int offset, int byte_order) {
  if (s.size() < offset + sizeof(uint16_t)) {
    return -1;
  }
  const uint8_t* p = reinterpret_cast<const uint8_t*>(s.data() + offset);
  if (byte_order == kExifBigEndian) {
    return (p[0] << 8) | p[1];
  }
  return (p[1] << 8) | p[0];
}

inline int GetUint32(Slice s, int offset, int byte_order) {
  if (s.size() < offset + sizeof(uint32_t)) {
    return -1;
  }
  const uint8_t* p = reinterpret_cast<const uint8_t*>(s.data() + offset);
  if (byte_order == kExifBigEndian) {
    return (p[0] << 24) | (p[1] << 16) | (p[2] << 8) | p[3];
  }
  return (p[3] << 24) | (p[2] << 16) | (p[1] << 8) | p[0];
}

bool ScanExifHeader(Slice s) {
  const uint8_t kExifHeader[] = { 0x45, 0x78, 0x69, 0x66 };
  for (int i = 0; i < ARRAYSIZE(kExifHeader); ++i) {
    if (GetUint8(s, i) != kExifHeader[i]) {
      return false;
    }
  }
  return true;
}

bool ScanExifDir(Slice s, int dir, int offset, int byte_order, TagCallback callback) {
  const int n = GetUint16(s, dir, byte_order);
  if (n < 0) {
    return false;
  }
  // LOG("exif: scan dir (%d/%d): %d entries", dir, s.size(), n);
  for (int i = 0; i < n; ++i) {
    const int entry = dir + 2 + (12 * i);
    const int tag = GetUint16(s, entry, byte_order);
    if (tag < 0) {
      LOG("exif: %d: unable to read tag", i);
      continue;
    }
    const int format = GetUint16(s, entry + 2, byte_order);
    if (format < kExifFormatByte || format > kExifFormatDouble) {
      LOG("exif: %d: unknown format: %d", i, format);
      continue;
    }

    const int components = GetUint32(s, entry + 4, byte_order);
    if (components < 0) {
      LOG("exif: %d: unable to read components", i);
      continue;
    }
    int value = entry + 8;
    const int byte_count = components * kExifBytesPerFormat[format];
    if (byte_count > 4) {
      const int overflow = GetUint32(s, value, byte_order);
      if (overflow < 0) {
        LOG("exif: %d: unable to read overflow offset", i);
        continue;
      }
      value = offset + overflow;
    }

    if (tag == kExifExif || tag == kExifInterop || tag == kExifGPS) {
      const int subdir = GetUint32(s, value, byte_order);
      ScanExifDir(s, offset + subdir, offset, byte_order, callback);
    } else {
      Slice data = s.substr(value, byte_count);
      if (data.size() != byte_count) {
        LOG("exif: %d: unable to read tag value", i);
        continue;
      }
      //const Slice pretty_data = (format == kExifFormatString) ?
      //    data.substr(0, data.size() - 1) : Slice();
      // LOG("exif: %d: tag %04x, format %d, components %d, size %d: %s",
      //     i, tag, format, components, byte_count, pretty_data);
      callback(static_cast<ExifTag>(tag),
               static_cast<ExifFormat>(format), data);
    }
  }
  return true;
}

int NextUint8(DataSource* s) {
  Slice p = s->Peek();
  if (p.empty()) {
    return -1;
  }
  const uint8_t b = *reinterpret_cast<const uint8_t*>(p.data());
  s->Advance(1);
  return b;
}

int NextUint16(DataSource* s) {
  Slice p = s->Peek();
  if (p.size() < 2) {
    const int a = NextUint8(s);
    if (a < 0) {
      return -1;
    }
    const int b = NextUint8(s);
    if (b < 0) {
      return -1;
    }
    return (a << 8) | b;
  }
  const uint8_t* ptr = reinterpret_cast<const uint8_t*>(p.data());
  const int r = (ptr[0] << 8) | ptr[1];
  s->Advance(2);
  return r;
}

string NextString(DataSource* s, int n) {
  string r;
  while (n > 0) {
    Slice p = s->Peek();
    if (p.empty()) {
      break;
    }
    const int t = std::min<int>(n, p.size());
    r.append(p.data(), t);
    s->Advance(t);
    n -= t;
  }
  return r;
}

}  // namespace

bool ScanExif(Slice s, TagCallback callback) {
  if (!ScanExifHeader(s)) {
    return false;
  }

  const int byte_order = GetUint16(s, 6, kExifBigEndian);
  if (byte_order < 0) {
    return false;
  }
  // LOG("exif: byte order: %04x", byte_order);

  if (GetUint16(s, 8, byte_order) != 0x2a) {
    return false;
  }

  const int offset = GetUint32(s, 10, byte_order);
  if (offset < 0) {
    return false;
  }

  if (!ScanExifDir(s, offset + 6, 6, byte_order, callback)) {
    return false;
  }

  return true;
}

bool ScanJpeg(DataSource* s, TagCallback callback) {
  if (NextUint16(s) != kJpegStartOfImage) {
    return false;
  }

  for (;;) {
    const int type = NextUint16(s);
    if (type < 0) {
      return false;
    }
    const int size = NextUint16(s) - sizeof(uint16_t);
    if (size < 0) {
      return false;
    }
    // LOG("jpeg: marker: %02x %d", type, size);

    switch (type) {
      case kJpegEndOfImage:
      case kJpegStartOfScan:
        return false;

      case kJpegStartOfFrame0:
      case kJpegStartOfFrame1:
      case kJpegStartOfFrame2:
      case kJpegStartOfFrame3:
      case kJpegStartOfFrame5:
      case kJpegStartOfFrame6:
      case kJpegStartOfFrame7:
      case kJpegStartOfFrame9:
      case kJpegStartOfFrame10:
      case kJpegStartOfFrame11:
      case kJpegStartOfFrame13:
      case kJpegStartOfFrame14:
      case kJpegStartOfFrame15:
        break;

      case kJpegApp0:
        break;
      case kJpegApp1: {
        // Try to get the exif data without copying.
        const Slice slice = s->Peek();
        if (slice.size() >= size) {
          return ScanExif(slice.substr(0, size), callback);
        }
        // The data is non-contiguous, copy it to a string.
        const string str = NextString(s, size);
        if (str.size() != size) {
          return false;
        }
        return ScanExif(str, callback);
      }
      case kJpegApp2:
      case kJpegApp3:
      case kJpegApp4:
      case kJpegApp5:
      case kJpegApp6:
      case kJpegApp7:
      case kJpegApp8:
      case kJpegApp9:
      case kJpegApp10:
      case kJpegApp11:
      case kJpegApp12:
      case kJpegApp13:
      case kJpegApp14:
      case kJpegApp15:
        break;
    }

    s->Advance(size);
  }

  return true;
}

bool ScanJpeg(Slice s, TagCallback callback) {
  SliceDataSource source(s);
  return ScanJpeg(&source, callback);
}

WallTime ParseExifDate(const Slice& s) {
  struct tm t;
  memset(&t, 0, sizeof(t));
  strptime(s.data(), "%Y:%m:%d %H:%M:%S", &t);
  t.tm_isdst = -1;
  return mktime(&t);
}
