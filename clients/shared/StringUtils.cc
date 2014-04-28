// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <ctype.h>
#import <unicode/brkiter.h>
#import <unicode/rbbi.h>
#import <unicode/translit.h>
#import <re2/re2.h>
#import <zlib.h>
#import "LazyStaticPtr.h"
#import "Logging.h"
#import "Mutex.h"
#import "ScopedPtr.h"
#import "StringUtils.h"

namespace {

LazyStaticPtr<RE2, const char*> kSqueezeWhitespaceRE = { "[\\pZ\\pC]+" };

// Used in ToAsciiLossy.
Mutex transliterator_mutex;
icu::Transliterator* transliterator;

// Used in WordSplitter.
Mutex word_break_iterator_mutex;
icu::RuleBasedBreakIterator* word_break_iterator;

// Used in TruncateUTF8.
Mutex char_break_iterator_mutex;
icu::BreakIterator* char_break_iterator;

const short* MakeBase64DecodingTable(const char* encoding_table) {
  short* table = new short[256];
  for (int i = 0; i < 256; i++) {
    table[i] = isspace(i) ? -1 : -2;
  }
  for (int i = 0; i < 64; ++i) {
    table[int(encoding_table[i])] = i;
  }
  return table;
}

const char kBase64EncodingTable[65] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
const short* kBase64DecodingTable =
    MakeBase64DecodingTable(kBase64EncodingTable);

const char kBase64HexEncodingTable[65] =
    "-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz";
const short* kBase64HexDecodingTable =
    MakeBase64DecodingTable(kBase64HexEncodingTable);

string Base64EncodeInternal(const Slice& str, const char* encoding_table, bool padding = true) {
  if (str.empty()) {
    return string();
  }

  const unsigned char* src = (const unsigned char*)str.data();
  int src_length = str.size();
  string result(((src_length + 2) / 3) * 4, '\0');
  int i = 0;

  // Keep going until we have less than 3 octets
  while (src_length > 2) {
    DCHECK_LE(i + 4, result.size());
    result[i++] = encoding_table[src[0] >> 2];
    result[i++] = encoding_table[((src[0] & 0x03) << 4) + (src[1] >> 4)];
    result[i++] = encoding_table[((src[1] & 0x0f) << 2) + (src[2] >> 6)];
    result[i++] = encoding_table[src[2] & 0x3f];

    // We just handled 3 octets of data
    src += 3;
    src_length -= 3;
  }

  // Now deal with the tail end of things
  if (src_length != 0) {
    DCHECK_LE(i + 4, result.size());
    result[i++] = encoding_table[src[0] >> 2];
    if (src_length > 1) {
      result[i++] = encoding_table[((src[0] & 0x03) << 4) + (src[1] >> 4)];
      result[i++] = encoding_table[(src[1] & 0x0f) << 2];
      if (padding) {
        result[i++] = '=';
      }
    } else {
      result[i++] = encoding_table[(src[0] & 0x03) << 4];
      if (padding) {
        result[i++] = '=';
        result[i++] = '=';
      }
    }
  }

  result.resize(i);
  return result;
}

string Base64DecodeInternal(const Slice& str, const short* decoding_table) {
  string result(str.size(), '\0');
  int j = 0;

  // Run through the whole string, converting as we go.
  for (int i = 0; i < str.size(); ++i) {
    int c = str[i];
    if (c == '=') {
      break;
    }

    c = decoding_table[c];
    if (c == -1) {
      // We're at a whitespace, simply skip over
      continue;
    } else if (c == -2) {
      // We're at an invalid character.
      return string();
    }

    switch (i % 4) {
      case 0:
        result[j] = c << 2;
        break;
      case 1:
        result[j++] |= c >> 4;
        result[j] = (c & 0x0f) << 4;
        break;
      case 2:
        result[j++] |= c >>2;
        result[j] = (c & 0x03) << 6;
        break;
      case 3:
        result[j++] |= c;
        break;
    }
  }

  result.resize(j);
  return result;
}

template <typename T>
void OrderedCodeEncodeVarintCommon(string *s, T v) {
  char buf[sizeof(T) + 1];
  uint8_t* end = reinterpret_cast<uint8_t*>(&buf[sizeof(T)]);
  uint8_t* ptr = end;

  while (v > 0) {
    *ptr-- = v & 255;
    v >>= 8;
  }
  const int len = end - ptr;
  *ptr = len;

  s->append(reinterpret_cast<char*>(ptr), len + 1);
}

template <typename T>
T OrderedCodeDecodeVarintCommon(Slice* s) {
  if (s->empty()) {
    return 0;
  }
  int len = (*s)[0];
  if ((len + 1) > s->size()) {
    return 0;
  }

  T v = 0;
  const uint8_t* ptr = reinterpret_cast<const uint8_t*>(s->data()) + len;
  for (int i = 0; i < len; ++i) {
    v |= static_cast<T>(*ptr--) << (i * 8);
  }
  s->remove_prefix(len + 1);

  return v;
}

void FixedEncode(string* s, uint64_t v, int bytes, bool big_endian) {
  static const int B = 0xff;
  int start_length = s->length();
  // This loop encodes the value as little-endian, regardless of
  // underlying CPU.
  for (int i = 0; i < bytes; i++) {
    s->push_back(uint8_t(v & B));
    v >>= 8;
  }
  // Reverse the result if encoding was requested as big-endian.
  if (big_endian) {
    reverse(s->begin() + start_length, s->end());
  }
}

uint64_t FixedDecode(Slice* s, int bytes, bool big_endian) {
  CHECK_GE(s->length(), bytes);
  uint64_t v = 0;
  const uint8_t* ptr = reinterpret_cast<const uint8_t*>(s->data()) + (big_endian ? 0 : bytes - 1);
  for (int i = 0; i < bytes; i++) {
    v = (v << 8) | *ptr;
    ptr += (big_endian ? 1 : -1);
  }
  s->remove_prefix(bytes);
  return v;
}

// Signed int to string conversion.
template <typename T, typename UnsignedT>
inline string IntToString(T v) {
  char buf[std::numeric_limits<T>::digits10 + 2] = { 0 };
  int i = ARRAYSIZE(buf);
  UnsignedT uv = (v < 0) ? static_cast<UnsignedT>(-v) :
      static_cast<UnsignedT>(v);
  do {
    buf[--i] = '0' + (uv % 10);
    uv /= 10;
  } while (uv);
  if (v < 0) {
    buf[--i] = '-';
  }
  return string(&buf[i], ARRAYSIZE(buf) - i);
};

// Unsigned int to string conversion.
template <typename T>
inline string UintToString(T v) {
  char buf[std::numeric_limits<T>::digits10 + 2] = { 0 };
  int i = ARRAYSIZE(buf);
  do {
    buf[--i] = '0' + (v % 10);
    v /= 10;
  } while (v);
  return string(&buf[i], ARRAYSIZE(buf) - i);
}

struct {
  int64_t max_value;
  int64_t divisor;
  const char* fmt;
} kFormatRanges[] = {
  { 1000, 1, "%.0f" },
  { 10000, 1000, "%.1fK" },
  { 1000000, 1000, "%.0fK" },
  { 10000000, 1000000, "%.1fM" },
  { 1000000000, 1000000, "%.0fM" },
  { 10000000000, 1000000000, "%.1fB" },
  { 1000000000000, 1000000000, "%.0fB" },
  { 10000000000000, 1000000000000, "%.1fT" },
  { 1000000000000000, 1000000000000, "%.0fT" },
};

const char kHexChars[] = "0123456789abcdef";

}  // namespace

WordSplitter::operator vector<string>() {
  vector<string> result;
  Split(std::back_insert_iterator<vector<string> >(result));
  return result;
};

WordSplitter::operator StringSet() {
  StringSet result;
  Split(std::insert_iterator<StringSet>(result, result.begin()));
  return result;
};

template <typename Iterator>
void WordSplitter::Split(Iterator result) {
  MutexLock lock(&word_break_iterator_mutex);
  if (!word_break_iterator) {
    UErrorCode icu_status = U_ZERO_ERROR;
    // In ICU 5.1, the locale passed here doesn't seem to matter for word breaks.  It will switch
    // between whitespace and dictionary modes automatically based on the characters it encouters.
    ScopedPtr<icu::BreakIterator> break_iter(
        icu::BreakIterator::createWordInstance(icu::Locale::getUS(), icu_status));
    if (!break_iter.get() || !U_SUCCESS(icu_status)) {
      LOG("failed to create break iterator: %s", icu_status);
      return;
    }

    // In ICU 5.1, all break iterators are instances of RuleBasedBreakIterator, which adds a method
    // we need to distinguish words from runs of punctuation.
    if (break_iter->getDynamicClassID() != icu::RuleBasedBreakIterator::getStaticClassID()) {
      LOG("got non-rule-based break iterator");
      return;
    }
    word_break_iterator = (icu::RuleBasedBreakIterator*)break_iter.release();
  }


  // The UText family of APIs in ICU would let us do this without so much copying.  However,
  // while BreakIterator supports UText, it can only do basic word breaking in this mode, not the
  // dictionary-based CJ segmentation.
  icu::UnicodeString ustr = icu::UnicodeString::fromUTF8(icu::StringPiece(str_.data(), str_.size()));
  word_break_iterator->setText(ustr);

  int pos = word_break_iterator->first();
  while (pos != icu::BreakIterator::DONE) {
    int start = pos;
    pos = word_break_iterator->next();
    if (word_break_iterator->getRuleStatus() != UBRK_WORD_NONE) {
      string substr;
      icu::UnicodeString usubstr = ustr.tempSubString(start, pos - start);
      usubstr.toUTF8String(substr);
      *result++ = substr;
    }
  }
}

string Join(const vector<string>& parts,
            const string& delim, int begin, int end) {
  string res;
  end = std::min<int>(parts.size() - 1, end);
  for (int i = begin; i <= end; ++i) {
    if (i != begin) {
      res.append(delim);
    }
    res.append(parts[i]);
  }
  return res;
}

bool Trim(const Slice& str, string* result) {
  // UnicodeCharIterators are significantly faster than RE2 when dealing with
  // unicode character classes, so use them to remove leading and trailing whitespace.
  int first = 0;
  int last = str.size();
  for (UnicodeCharIterator iter(str); !iter.Done(); iter.Advance()) {
    if (!IsSpaceControlUnicode(iter.Get())) {
      first = iter.Position();
      break;
    }
  }
  for (ReverseUnicodeCharIterator iter(str); !iter.Done(); iter.Advance()) {
    if (!IsSpaceControlUnicode(iter.Get())) {
      break;
    }
    last = iter.Position();
  }
  CHECK_LE(first, last);
  *result = str.substr(first, last - first).as_string();
  return first != 0 || last != str.size();
}

string Trim(const string& str) {
  string result;
  Trim(str, &result);
  return result;
}

string NormalizeWhitespace(const Slice& str) {
  string trimmed;
  Trim(str, &trimmed);
  RE2::GlobalReplace(&trimmed, *kSqueezeWhitespaceRE, " ");
  return trimmed;
}

string TruncateUTF8(const Slice &str, int n) {
  MutexLock lock(&char_break_iterator_mutex);
  if (!char_break_iterator) {
    UErrorCode icu_status = U_ZERO_ERROR;
    ScopedPtr<icu::BreakIterator> break_iter(
        icu::BreakIterator::createCharacterInstance(icu::Locale::getUS(), icu_status));
    if (!break_iter.get() || !U_SUCCESS(icu_status)) {
      LOG("failed to create break iterator: %s", icu_status);
      return "";
    }
    char_break_iterator = break_iter.release();
  }

  UErrorCode icu_status = U_ZERO_ERROR;
  UText* utext = utext_openUTF8(NULL, str.data(), str.size(), &icu_status);
  if (!U_SUCCESS(icu_status)) {
    return "";
  }

  char_break_iterator->setText(utext, icu_status);
  utext_close(utext);
  if (!U_SUCCESS(icu_status)) {
    return "";
  }

  int pos = char_break_iterator->next(n);
  if (pos == icu::BreakIterator::DONE) {
    // We hit the end of the string so return the whole thing
    return str.as_string();
  } else {
    return string(str.data(), pos);
  }
}

Slice RemovePrefix(const Slice& str, const Slice& prefix) {
  CHECK(str.starts_with(prefix));
  Slice result(str);
  result.remove_prefix(prefix.size());
  return result;
}

string BinaryToHex(const Slice& b) {
  string h(b.size() * 2, '0');
  const uint8_t* p = (const uint8_t*)b.data();
  for (int i = 0; i < b.size(); ++i) {
    const int c = p[i];
    h[2 * i] = kHexChars[c >> 4];
    h[2 * i + 1] = kHexChars[c & 0xf];
  }
  return h;
}

string Base64Encode(const Slice& str) {
  return Base64EncodeInternal(str, kBase64EncodingTable);
}

string Base64HexEncode(const Slice& str, bool padding) {
  return Base64EncodeInternal(str, kBase64HexEncodingTable, padding);
}

string Base64Decode(const Slice& str) {
  return Base64DecodeInternal(str, kBase64DecodingTable);
}

string Base64HexDecode(const Slice& str) {
  return Base64DecodeInternal(str, kBase64HexDecodingTable);
}

string ToLowercase(const Slice& str) {
  icu::UnicodeString ustr = icu::UnicodeString::fromUTF8(
      icu::StringPiece(str.data(), str.size()));
  // TODO(peter): Should we be specifying the locale here?
  ustr.toLower();
  string utf8;
  ustr.toUTF8String(utf8);
  return utf8;
}

string ToUppercase(const Slice& str) {
  icu::UnicodeString ustr = icu::UnicodeString::fromUTF8(
      icu::StringPiece(str.data(), str.size()));
  // TODO(peter): Should we be specifying the locale here?
  ustr.toUpper();
  string utf8;
  ustr.toUTF8String(utf8);
  return utf8;
}

string ToAsciiLossy(const Slice& str) {
  // If the string is already ascii-only we can exit early.
  bool ascii_only = true;
  for (int i = 0; i < str.size(); i++) {
    if (str[i] & 0x80) {
      ascii_only = false;
      break;
    }
  }
  if (ascii_only) {
    return str.as_string();
  }

  MutexLock lock(&transliterator_mutex);
  if (!transliterator) {
    UErrorCode icu_status = U_ZERO_ERROR;
    // ICU's Any-Latin conversion is best-effort; non-letter characters are left as-is, so
    // add an extra step at the end to strip out any non-ascii characters that remain.
    transliterator = icu::Transliterator::createInstance(
        "Any-Latin; Latin-ASCII; [^\\u0020-\\u007f] Any-Remove",
        UTRANS_FORWARD, icu_status);
    if (!transliterator || icu_status != U_ZERO_ERROR) {
      return "";
    }
  }

  icu::UnicodeString ustr = icu::UnicodeString::fromUTF8(icu::StringPiece(str.data(), str.size()));
  transliterator->transliterate(ustr);
  string ascii;
  ustr.toUTF8String(ascii);
  return ascii;
}

void Fixed32Encode(string* s, uint32_t v, bool big_endian) {
  FixedEncode(s, v, 4, big_endian);
}

uint32_t Fixed32Decode(Slice* s, bool big_endian) {
  return FixedDecode(s, 4, big_endian);
}

void Fixed64Encode(string* s, uint64_t v, bool big_endian) {
  FixedEncode(s, v, 8, big_endian);
}

uint64_t Fixed64Decode(Slice* s, bool big_endian) {
  return FixedDecode(s, 8, big_endian);
}

void Varint64Encode(string* s, uint64_t v) {
  static const int B = 128;
  unsigned char buf[10];
  unsigned char* ptr = buf;
  while (v >= B) {
    *(ptr++) = (v & (B-1)) | B;
    v >>= 7;
  }
  *(ptr++) = static_cast<unsigned char>(v);
  s->append(reinterpret_cast<char*>(buf), ptr - buf);
}

uint64_t Varint64Decode(Slice* s) {
  static const int B = 128;
  const uint8_t* b = reinterpret_cast<const uint8_t*>(s->begin());
  const uint8_t* e = reinterpret_cast<const uint8_t*>(s->end());
  const uint8_t* p = b;
  uint64_t result = 0;
  for (uint32_t shift = 0; shift <= 63 && p < e; shift += 7) {
    uint64_t byte = *p++;
    if (byte & B) {
      // More bytes are present
      result |= ((byte & 127) << shift);
    } else {
      result |= (byte << shift);
      break;
    }
  }
  s->remove_prefix(p - b);
  return result;
}

void OrderedCodeEncodeVarint32(string* s, uint32_t v) {
  OrderedCodeEncodeVarintCommon(s, v);
}

void OrderedCodeEncodeVarint32Decreasing(string* s, uint32_t v) {
  return OrderedCodeEncodeVarint32(s, ~v);
}

void OrderedCodeEncodeVarint64(string* s, uint64_t v) {
  OrderedCodeEncodeVarintCommon(s, v);
}

void OrderedCodeEncodeVarint64Decreasing(string* s, uint64_t v) {
  OrderedCodeEncodeVarint64(s, ~v);
}

uint32_t OrderedCodeDecodeVarint32(Slice* s) {
  return OrderedCodeDecodeVarintCommon<uint32_t>(s);
}

uint32_t OrderedCodeDecodeVarint32Decreasing(Slice* s) {
  return ~OrderedCodeDecodeVarint32(s);
}

uint64_t OrderedCodeDecodeVarint64(Slice* s) {
  return OrderedCodeDecodeVarintCommon<uint64_t>(s);
}

uint64_t OrderedCodeDecodeVarint64Decreasing(Slice* s)  {
  return ~OrderedCodeDecodeVarint64(s);
}

void OrderedCodeEncodeInt64Pair(string* s, int64_t a, int64_t b) {
  OrderedCodeEncodeVarint64(s, a);
  if (b != 0) {
    // Only encode "b" if it is non-zero. This is a slight space optimization,
    // but more importantly it allows us to encode only "a" so that we can
    // easily create the string prefix that finds all pairs that begin with
    // "a".
    OrderedCodeEncodeVarint64(s, b);
  }
}

void OrderedCodeDecodeInt64Pair(Slice* s, int64_t *a, int64_t *b) {
  *a = OrderedCodeDecodeVarint64(s);
  *b = OrderedCodeDecodeVarint64(s);
}

string FormatCount(int64_t count) {
  for (int i = 0; i < ARRAYSIZE(kFormatRanges); ++i) {
    if (fabs(count) < kFormatRanges[i].max_value) {
      return Format(kFormatRanges[i].fmt, (double(count) / kFormatRanges[i].divisor));
    }
  }
  return ToString(count);
}

int64_t FastParseInt64(const Slice& s) {
  int64_t x = 0;
  if (s[0] == '-') {
    for (int i = 1; i < s.size(); i++) {
      x = x * 10 - (s[i] - '0');
    }
  } else {
    for (int i = 0; i < s.size(); i++) {
      x = x * 10 + (s[i] - '0');
    }
  }
  return x;
}

string Int32ToString(int32_t v) {
  return IntToString<int32_t, uint32_t>(v);
}

string Int64ToString(int64_t v) {
  return IntToString<int64_t, uint64_t>(v);
}

string Uint32ToString(uint32_t v) {
  return UintToString(v);
}

string Uint64ToString(uint64_t v) {
  return UintToString(v);
}

string GzipEncode(const Slice& str) {
  if (str.size() == 0) {
    return NULL;
  }

  z_stream zlib;
  memset(&zlib, 0, sizeof(zlib));
  zlib.zalloc    = Z_NULL;
  zlib.zfree     = Z_NULL;
  zlib.opaque    = Z_NULL;
  zlib.total_out = 0;
  zlib.next_in   = (Bytef*)str.data();
  zlib.avail_in  = str.size();

  int error = deflateInit2(
      &zlib, Z_DEFAULT_COMPRESSION, Z_DEFLATED, (15+16), 8, Z_DEFAULT_STRATEGY);
  if (error != Z_OK) {
    switch (error) {
      case Z_STREAM_ERROR:
        LOG("deflateInit2() error: Invalid parameter passed in to function: %s",
            zlib.msg);
        break;
      case Z_MEM_ERROR:
        LOG("deflateInit2() error: Insufficient memory: %s",
            zlib.msg);
        break;
      case Z_VERSION_ERROR:
        LOG("deflateInit2() error: The version of zlib.h and the version "
            "of the library linked do not match: %s", zlib.msg);
        break;
      default:
        LOG("deflateInit2() error: Unknown error code %d: %s",
            error, zlib.msg);
        break;
    }
    return NULL;
  }

  string compressed;
  do {
    compressed.resize(std::max<int>(1024, compressed.size() * 2));
    zlib.next_out = (Bytef*)compressed.data() + zlib.total_out;
    zlib.avail_out = compressed.size() - zlib.total_out;

    error = deflate(&zlib, Z_FINISH);
  } while (error == Z_OK);

  if (error != Z_STREAM_END) {
    switch (error) {
      case Z_ERRNO:
        LOG("deflate() error: Error occured while reading file: %s",
            zlib.msg);
        break;
      case Z_STREAM_ERROR:
        LOG("deflate() error: : %s", zlib.msg);
        LOG("deflate() error: The stream state was inconsistent "
            "(e.g. next_in or next_out was NULL): %s", zlib.msg);
        break;
      case Z_DATA_ERROR:
        LOG("deflate() error: The deflate data was invalid or "
            "incomplete: %s", zlib.msg);
        break;
      case Z_MEM_ERROR:
        LOG("deflate() error: Memory could not be allocated for "
            "processing: %s", zlib.msg);
        break;
      case Z_BUF_ERROR:
        LOG("deflate() error: Ran out of output buffer for writing "
            "compressed bytes: %s", zlib.msg);
        break;
      case Z_VERSION_ERROR:
        LOG("deflate() error: The version of zlib.h and the version "
            "of the library linked do not match: %s", zlib.msg);
        break;
      default:
        LOG("deflate() error: Unknown error code %d: %s", error, zlib.msg);
        break;
    }
    return NULL;
  }

  compressed.resize(zlib.total_out);
  deflateEnd(&zlib);
  return compressed;
}

string GzipDecode(const Slice& str) {
  if (str.size() == 0) {
    return NULL;
  }

  z_stream zlib;
  memset(&zlib, 0, sizeof(zlib));
  zlib.zalloc    = Z_NULL;
  zlib.zfree     = Z_NULL;
  zlib.opaque    = Z_NULL;
  zlib.total_out = 0;
  zlib.next_in   = (Bytef*)str.data();
  zlib.avail_in  = str.size();

  int error = inflateInit2(&zlib, (15+16));
  if (error != Z_OK) {
    switch (error) {
      case Z_STREAM_ERROR:
        LOG("inflateInit2() error: Invalid parameter passed in to function: %s",
            zlib.msg);
        break;
      case Z_MEM_ERROR:
        LOG("inflateInit2() error: Insufficient memory: %s",
            zlib.msg);
        break;
      case Z_VERSION_ERROR:
        LOG("inflateInit2() error: The version of zlib.h and the version "
            "of the library linked do not match: %s", zlib.msg);
        break;
      default:
        LOG("inflateInit2() error: Unknown error code %d: %s",
            error, zlib.msg);
        break;
    }
    return NULL;
  }

  string decompressed;
  do {
    decompressed.resize(std::max<int>(1024, decompressed.size() * 2));
    zlib.next_out = (Bytef*)decompressed.data() + zlib.total_out;
    zlib.avail_out = decompressed.size() - zlib.total_out;

    error = inflate(&zlib, Z_FINISH);
  } while (error == Z_OK);

  if (error != Z_STREAM_END) {
    switch (error) {
      case Z_ERRNO:
        LOG("inflate() error: Error occured while reading file: %s",
            zlib.msg);
        break;
      case Z_STREAM_ERROR:
        LOG("inflate() error: : %s", zlib.msg);
        LOG("inflate() error: The stream state was inconsistent "
            "(e.g. next_in or next_out was NULL): %s", zlib.msg);
        break;
      case Z_DATA_ERROR:
        LOG("inflate() error: The inflate data was invalid or "
            "incomplete: %s", zlib.msg);
        break;
      case Z_MEM_ERROR:
        LOG("inflate() error: Memory could not be allocated for "
            "processing: %s", zlib.msg);
        break;
      case Z_BUF_ERROR:
        LOG("inflate() error: Ran out of output buffer for writing "
            "compressed bytes: %s", zlib.msg);
        break;
      case Z_VERSION_ERROR:
        LOG("inflate() error: The version of zlib.h and the version "
            "of the library linked do not match: %s", zlib.msg);
        break;
      default:
        LOG("inflate() error: Unknown error code %d: %s", error, zlib.msg);
        break;
    }
    return NULL;
  }

  decompressed.resize(zlib.total_out);
  inflateEnd(&zlib);
  return decompressed;
}

UnicodeCharIterator::UnicodeCharIterator(const Slice& s)
    : error_(false) {
  UErrorCode icu_status = U_ZERO_ERROR;
  utext_ = utext_openUTF8(NULL, s.data(), s.size(), &icu_status);
  if (!U_SUCCESS(icu_status)) {
    error_ = true;
  }
  next_ = utext_next32From(utext_, 0);
}

UnicodeCharIterator::~UnicodeCharIterator() {
  utext_close(utext_);
}

ReverseUnicodeCharIterator::ReverseUnicodeCharIterator(const Slice& s)
    : error_(false) {
  UErrorCode icu_status = U_ZERO_ERROR;
  utext_ = utext_openUTF8(NULL, s.data(), s.size(), &icu_status);
  if (!U_SUCCESS(icu_status)) {
    error_ = true;
  }
  next_ = utext_previous32From(utext_, utext_nativeLength(utext_));
}

ReverseUnicodeCharIterator::~ReverseUnicodeCharIterator() {
  utext_close(utext_);
}

bool IsAlphaUnicode(UChar32 c) {
  // "GC" here means "general category"
  return U_GET_GC_MASK(c) & U_GC_L_MASK;
}

bool IsAlphaNumUnicode(UChar32 c) {
  // "GC" here means "general category"
  const int32_t kAlphaNumMask = U_GC_L_MASK | U_GC_N_MASK;
  return U_GET_GC_MASK(c) & kAlphaNumMask;
}

bool IsSpaceControlUnicode(UChar32 c) {
  // "GC" here means "general category"
  const int32_t kSpaceControlMask = U_GC_Z_MASK | U_GC_C_MASK;
  return U_GET_GC_MASK(c) & kSpaceControlMask;
}

// NOTE(peter): This method is missing from re2.
namespace re2 {
void StringPiece::AppendToString(string* target) const {
  target->append(ptr_, length_);
}
}  // namespace re2

// local variables:
// mode: c++
// end:
