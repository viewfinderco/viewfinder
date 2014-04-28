// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_STRING_UTILS_H
#define VIEWFINDER_STRING_UTILS_H

#import <iostream>
#import <limits>
#import <sstream>
#import <unicode/utext.h>
#import "STLUtils.h"
#import "Utils.h"

class Splitter {
 public:
  Splitter(const string& str, const string& delim, bool allow_empty)
      : str_(str),
        delim_(delim),
        allow_empty_(allow_empty) {
  }

  operator vector<string>() {
    vector<string> result;
    Split(std::back_insert_iterator<vector<string> >(result));
    return result;
  }

 private:
  template <typename Iterator>
  void Split(Iterator result) {
    if (str_.empty()) {
      return;
    }
    for (string::size_type begin_index, end_index = 0; ;) {
      begin_index = str_.find_first_not_of(delim_, end_index);
      if (begin_index == string::npos) {
        MaybeOutputEmpty(result, (end_index == 0) + str_.size() - end_index);
        return;
      }
      MaybeOutputEmpty(result, (end_index == 0) + begin_index - end_index - 1);
      end_index = str_.find_first_of(delim_, begin_index);
      if (end_index == string::npos) {
        end_index = str_.size();
      }
      *result++ = str_.substr(begin_index, (end_index - begin_index));
    }
  }

  template <typename Iterator>
  void MaybeOutputEmpty(Iterator result, int count) {
    if (!allow_empty_) {
      return;
    }
    for (int i = 0; i < count; ++i) {
      *result++ = string();
    }
  }

 private:
  const string& str_;
  const string& delim_;
  const bool allow_empty_;
};

inline Splitter Split(const string& str, const string& delim) {
  return Splitter(str, delim, false);
}

inline Splitter SplitAllowEmpty(const string& str, const string& delim) {
  return Splitter(str, delim, true);
}

class WordSplitter {
 public:
  WordSplitter(const Slice& str)
      : str_(str) {
  }

  operator vector<string>();
  operator StringSet();

 private:
  template <typename Iterator>
  void Split(Iterator result);

  const Slice& str_;
};

// Split the given string into words in an i18n-aware way.
inline WordSplitter SplitWords(const Slice& str) {
  return WordSplitter(str);
}

template <typename Iter>
string Join(Iter begin, Iter end, const string& delim) {
  string res;
  for (int i = 0; begin != end; ++i, ++begin) {
    if (i != 0) {
      res.append(delim);
    }
    res.append(*begin);
  }
  return res;
}

string Join(const vector<string>& parts, const string& delim,
            int begin = 0, int end = std::numeric_limits<int>::max());

// Trim is UTF8 aware and will handle all unicode whitespace (Z, C)
// classes. Returns true if any characters were trimmed from the
// input string.  The trimmed result is stored in *result.
bool Trim(const Slice& str, string* result);

string Trim(const string& str);

// Removes all leading and trailing whitespace, and replaces all
// repeated internal whitespace (plus any control characters) with a
// single space. Note that this method applies to the unicode
// whitespace (Z) and control character (C) classes
string NormalizeWhitespace(const Slice& str);

// Performs a localized case insensitive string comparison, returning -1 if a <
// b, 0 if a == b and +1 if a > b.
int LocalizedCaseInsensitiveCompare(const Slice& a, const Slice& b);

// Performs a localized formatting of the specifying number.
string LocalizedNumberFormat(int value);

// Returns the first N characters from str.  This function knows about utf8 character boundaries
// as well as combining characters and surrogates.
string TruncateUTF8(const Slice& str, int n);

// Asserts that "str" begins with "prefix" and returns the remaining portion of "str".
Slice RemovePrefix(const Slice& str, const Slice& prefix);

string BinaryToHex(const Slice& s);

// Returns a new "formatted" 128-bit UUID. On iOS the string is formatted as:
//
//   aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
//
// Each non-hyphen character is a hexadecimal value.
string NewUUID();

string Base64Encode(const Slice& str);
string Base64HexEncode(const Slice& str, bool padding = true);
string Base64Decode(const Slice& str);
string Base64HexDecode(const Slice& str);

string ToLowercase(const Slice& str);
string ToUppercase(const Slice& str);
// Converts an 8-bit ASCII string (possibly lossily) into a 7-bit
// ASCII string. If the specified string is not convertible into
// 8-bit ASCII, an empty string is returned.
string ToAsciiLossy(const Slice& str);

void Fixed32Encode(string* s, uint32_t v, bool big_endian = true);
uint32_t Fixed32Decode(Slice* s, bool big_endian = true);
void Fixed64Encode(string* s, uint64_t v, bool big_endian = true);
uint64_t Fixed64Decode(Slice* s, bool big_endian = true);

void Varint64Encode(string* s, uint64_t v);
uint64_t Varint64Decode(Slice* s);

void OrderedCodeEncodeVarint32(string* s, uint32_t v);
void OrderedCodeEncodeVarint32Decreasing(string* s, uint32_t v);
void OrderedCodeEncodeVarint64(string* s, uint64_t v);
void OrderedCodeEncodeVarint64Decreasing(string* s, uint64_t v);
uint32_t OrderedCodeDecodeVarint32(Slice* s);
uint32_t OrderedCodeDecodeVarint32Decreasing(Slice* s);
uint64_t OrderedCodeDecodeVarint64(Slice* s);
uint64_t OrderedCodeDecodeVarint64Decreasing(Slice* s);

void OrderedCodeEncodeInt64Pair(string* s, int64_t a, int64_t b);
void OrderedCodeDecodeInt64Pair(Slice* s, int64_t *a, int64_t *b);

// Formats a count using abbreviations for thousands.
// 1-999: "1"-"999"
// 1,000-9,999: "1.0K"-"9.9K"
// 10,000-999,000: "10K"-"999K"
// 1,000,000-9,999,999: "1.0M"-"9.9M"
// etc. including "B", and "T".
string FormatCount(int64_t count);

inline Slice Pluralize(
    int n, const char* singular = "", const char* plural = "s") {
  return (n == 1) ? singular : plural;
}

// Parses a decimal integer from the given string, which must contain only digits.
// Does no bounds checking; behavior on overflow is undefined.
// This is much faster than strtoll on iOS because strtoll uses division in its bounds
// checking, and 64-bit integer division is implemented in software on iOS devices.
int64_t FastParseInt64(const Slice& s);

template <typename T>
struct ToStringImpl {
  static string Convert(const T& t) {
    std::ostringstream s;
    s.precision(std::numeric_limits<double>::digits10 + 1);
    s << t;
    return s.str();
  }
};

template <>
struct ToStringImpl<Slice> {
  inline static string Convert(const Slice& s) {
    return s.ToString();
  }
};

template <>
struct ToStringImpl<string> {
  inline static string Convert(const string& s) {
    return s;
  }
};

// Faster int to string conversion.
string Int32ToString(int32_t v);
string Int64ToString(int64_t v);
string Uint32ToString(uint32_t v);
string Uint64ToString(uint64_t v);

string GzipEncode(const Slice& str);
string GzipDecode(const Slice& str);

template <>
struct ToStringImpl<int32_t> {
  inline static string Convert(int32_t v) {
    return Int32ToString(v);
  }
};

template <>
struct ToStringImpl<int64_t> {
  inline static string Convert(int64_t v) {
    return Int64ToString(v);
  }
};

template <>
struct ToStringImpl<uint32_t> {
  inline static string Convert(uint32_t v) {
    return Uint32ToString(v);
  }
};

template <>
struct ToStringImpl<uint64_t> {
  inline static string Convert(uint64_t v) {
    return Uint64ToString(v);
  }
};

template <typename T>
inline string ToString(const T &t) {
  return ToStringImpl<T>::Convert(t);
}

template <typename T>
inline void FromString(const string &str, T *val) {
  std::istringstream s(str);
  s >> *val;
}

inline void FromString(const string& str, string* val) {
  *val = str;
}

template <typename T>
inline T FromString(const string &str, T val = T()) {
  std::istringstream s(str);
  s >> val;
  return val;
}

template <typename T>
inline T FromString(const Slice &str, T val = T()) {
  return FromString<T>(str.as_string(), val);
}

inline Slice ToSlice(const Slice& s) {
  return s;
}

#ifdef __OBJC__

#import <Foundation/NSData.h>
#import <Foundation/NSString.h>
#import <Foundation/NSURL.h>

inline NSString* NewNSString(const Slice& s) {
  return [[NSString alloc] initWithBytes:s.data()
                                  length:s.size()
                                encoding:NSUTF8StringEncoding];
}

inline NSString* NewNSString(const char* s) {
  return NewNSString(Slice(s));
}

inline NSString* NewNSString(const string& s) {
  return NewNSString(Slice(s));
}

inline NSData* NewNSData(const Slice& s) {
  return [[NSData alloc] initWithBytes:s.data()
                                length:s.size()];
}

inline NSData* NewNSData(const string& s) {
  return NewNSData(Slice(s));
}

inline NSURL* NewNSURL(const Slice& s) {
  return [[NSURL alloc] initWithString:NewNSString(s)];
}

inline NSURL* NewNSURL(const string& s) {
  return NewNSURL(Slice(s));
}

inline string ToString(NSString* s) {
  if (s) {
    return [s UTF8String];
  }
  return "";
}

inline string ToString(NSData* d) {
  if (d) {
    return string((const char*)d.bytes, d.length);
  }
  return "";
}

inline string ToString(NSObject* o) {
  return ToString([o description]);
}

inline string ToString(NSURL *u) {
  return ToString([u description]);
}

inline Slice ToSlice(NSString* s) {
  if (s) {
    return [s UTF8String];
  }
  return Slice();
}

inline Slice ToSlice(NSData* d) {
  if (d) {
    return Slice((const char*)d.bytes, d.length);
  }
  return Slice();
}

#endif // __OBJC__

// Iterates over unicode characters in the given (UTF-8 encoded) string.
// Note that this class uses real 32-bit characters instead of the UTF-16 codepoints used
// in both NSString and icu::UnicodeString.
class UnicodeCharIterator {
 public:
  explicit UnicodeCharIterator(const Slice& s);

  ~UnicodeCharIterator();

  bool error() const { return error_; }

  UChar32 Get() const { return next_; }

  bool Done() const { return next_ < 0; }

  void Advance() {
    next_ = utext_next32(utext_);
  }

  // Returns the position of the first byte of the current character.
  int64_t Position() const {
    return utext_getPreviousNativeIndex(utext_);
  }

 private:
  bool error_;
  UText* utext_;
  UChar32 next_;
};

class ReverseUnicodeCharIterator {
 public:
  explicit ReverseUnicodeCharIterator(const Slice& s);

  ~ReverseUnicodeCharIterator();

  bool error() const { return error_; }

  UChar32 Get() const { return next_; }

  bool Done() const { return next_ < 0; }

  void Advance() {
    next_ = utext_previous32(utext_);
  }

  // Returns the position of the first byte of the current character.
  int64_t Position() const {
    return utext_getNativeIndex(utext_);
  }

 private:
  bool error_;
  UText* utext_;
  UChar32 next_;
};

// Returns true if 'c' is alphabetic.  Equivalent to the \pL regex character class.
bool IsAlphaUnicode(UChar32 c);

// Returns true if 'c' is alphanumeric.  Equivalent to the \pL and \pN regex character classes.
bool IsAlphaNumUnicode(UChar32 c);

// Returns true if 'c' is a whitespace or control character.  Equivalent to the \pZ and \pC regex character classes.
bool IsSpaceControlUnicode(UChar32 c);

#endif // VIEWFINDER_STRING_UTILS_H
