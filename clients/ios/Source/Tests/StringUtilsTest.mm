// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "STLUtils.h"
#import "StringUtils.h"
#import "Testing.h"

namespace {

void Base64Test(const string& src, const string& expected) {
  const string encoded_result = Base64Encode(src);
  EXPECT_EQ(encoded_result, expected);
  const string decoded_result = Base64Decode(expected);
  EXPECT_EQ(decoded_result, src);
}

void Base64HexTest(const string& src, const string& expected, bool padding = true) {
  const string encoded_result = Base64HexEncode(src, padding);
  EXPECT_EQ(encoded_result, expected);
  const string decoded_result = Base64HexDecode(expected);
  EXPECT_EQ(decoded_result, src);
}

TEST(SplitTest, AllowEmpty) {
  struct {
    const string str;
    const string expected;
  } kTestData[] = {
    { "", "" },
    { ".", ":" },
    { "..", "::" },
    { "...", ":::" },
    { "a..", "a::" },
    { ".a.", ":a:" },
    { "..a", "::a" },
    { "a.b.", "a:b:" },
    { ".a.b", ":a:b" },
    { "a.b.c", "a:b:c" },
  };
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    vector<string> v = SplitAllowEmpty(kTestData[i].str, ".");
    EXPECT_EQ(kTestData[i].expected, Join(v, ":"))
        << ": " << kTestData[i].str;
  }
}

TEST(WordSplitTest, Basic) {
  struct {
    const string str;
    const string expected;
  } kTestData[] = {
    { "", "" },
    { "hello", "hello" },
    { "hello world", "hello|world" },
    { "\"Hello\", she said", "Hello|she|said" },
    { "héllo  world", "héllo|world" },
    { "lots\tof\r\n\r\nweird\u00a0whitespace", "lots|of|weird|whitespace" },
    { "日本將派遣副首相麻生太郎於4月前往中國大陸訪問", "日本|將|派遣|副|首相|麻生|太郎|於|4|月|前往|中國大陸|訪問" },
  };
  for (int i = 0; i < ARRAYSIZE(kTestData); ++i) {
    vector<string> v = SplitWords(kTestData[i].str);
    EXPECT_EQ(Join(v, "|"), kTestData[i].expected);
  }
}

TEST(Base64Test, Basic) {
  Base64Test("", "");
  Base64Test("a", "YQ==");
  Base64Test("aa", "YWE=");
  Base64Test("aaa", "YWFh");
  Base64Test("aaab", "YWFhYg==");
  Base64Test("aaabb", "YWFhYmI=");
  Base64Test("aaabbb", "YWFhYmJi");

  string s;
  for (int i = 0; i < 1024; ++i) {
    s += static_cast<char>(i);
  }
  EXPECT_EQ(Base64Decode(Base64Encode(s)), s);
}

TEST(Base64HexTest, Basic) {
  Base64HexTest("", "");
  Base64HexTest("a", "NF==");
  Base64HexTest("aa", "NL3=");
  Base64HexTest("aaa", "NL4W");
  Base64HexTest("aaab", "NL4WNV==");
  Base64HexTest("aaabb", "NL4WNa7=");
  Base64HexTest("aaabbb", "NL4WNa8X");
  Base64HexTest("", "", false);
  Base64HexTest("a", "NF", false);
  Base64HexTest("aa", "NL3", false);
  Base64HexTest("aaa", "NL4W", false);
  Base64HexTest("aaab", "NL4WNV", false);
  Base64HexTest("aaabb", "NL4WNa7", false);
  Base64HexTest("aaabbb", "NL4WNa8X", false);

  string s;
  for (int i = 0; i < 1024; ++i) {
    s += static_cast<char>(i);
  }
  EXPECT_EQ(Base64HexDecode(Base64HexEncode(s)), s);
}

TEST(FixedIntTest, Basic) {
  for (int i = 0; i < 10000; ++i) {
    string s32;
    string s64;
    Fixed32Encode(&s32, i, i % 2);
    Fixed64Encode(&s64, i, i % 2);
    Slice encoded32(s32);
    Slice encoded64(s64);
    EXPECT_EQ(i, Fixed32Decode(&encoded32, i % 2));
    EXPECT(encoded32.empty());
    EXPECT_EQ(i, Fixed64Decode(&encoded64, i % 2));
    EXPECT(encoded64.empty());
  }
  for (uint32_t i = 100000; i < 1000000000; i *= 10) {
    string s;
    Fixed32Encode(&s, i);
    Slice encoded(s);
    EXPECT_EQ(i, Fixed32Decode(&encoded));
    EXPECT(encoded.empty());
  }
  for (uint64_t i = 100000; i < 10000000000000000000ULL; i *= 10) {
    string s;
    Fixed64Encode(&s, i);
    Slice encoded(s);
    EXPECT_EQ(i, Fixed64Decode(&encoded));
    EXPECT(encoded.empty());
  }
}

TEST(FixedIntTest, Endianness) {
  string s32;
  Fixed32Encode(&s32, 1, true);
  EXPECT_EQ(s32.data()[3], 1);
  EXPECT_EQ(s32.data()[0], 0);

  s32.clear();
  Fixed32Encode(&s32, 1, false);
  EXPECT_EQ(s32.data()[3], 0);
  EXPECT_EQ(s32.data()[0], 1);

  string s64;
  Fixed64Encode(&s64, 1, true);
  EXPECT_EQ(s64.data()[7], 1);
  EXPECT_EQ(s64.data()[0], 0);

  s64.clear();
  Fixed64Encode(&s64, 1, false);
  EXPECT_EQ(s64.data()[7], 0);
  EXPECT_EQ(s64.data()[0], 1);
}

TEST(Varint64Test, Basic) {
  for (int i = 0; i < 10000; ++i) {
    string s;
    Varint64Encode(&s, i);
    Slice encoded(s);
    EXPECT_EQ(i, Varint64Decode(&encoded));
  }
  for (uint64_t i = 100000; i < 10000000000000000000ULL; i *= 10) {
    string s;
    Varint64Encode(&s, i);
    Slice encoded(s);
    EXPECT_EQ(i, Varint64Decode(&encoded));
  }
}

TEST(OrderedCodeTest, Basic) {
  // Test the ordering of increasing codes.
  string last32;
  string last64;
  for (int i = 0; i < 1000000; ++i) {
    string encoded32;
    OrderedCodeEncodeVarint32(&encoded32, i);
    EXPECT_LT(last32, encoded32);
    last32 = encoded32;

    string encoded64;
    OrderedCodeEncodeVarint64(&encoded64, i);
    EXPECT_LT(last64, encoded64);
    last64 = encoded64;

    {
      Slice s(encoded32);
      EXPECT_EQ(i, OrderedCodeDecodeVarint32(&s));
    }

    {
      Slice s(encoded64);
      EXPECT_EQ(i, OrderedCodeDecodeVarint64(&s));
    }
  }

  // Test the ordering of decreasing codes.
  last32.erase();
  last64.erase();
  OrderedCodeEncodeVarint32Decreasing(&last32, 0);
  OrderedCodeEncodeVarint64Decreasing(&last64, 0);

  for (int i = 1; i < 1000000; ++i) {
    string encoded32;
    OrderedCodeEncodeVarint32Decreasing(&encoded32, i);
    EXPECT_GT(last32, encoded32);
    last32 = encoded32;

    string encoded64;
    OrderedCodeEncodeVarint64Decreasing(&encoded64, i);
    EXPECT_GT(last64, encoded64);
    last64 = encoded64;

    {
      Slice s(encoded32);
      EXPECT_EQ(i, OrderedCodeDecodeVarint32Decreasing(&s));
    }

    {
      Slice s(encoded64);
      EXPECT_EQ(i, OrderedCodeDecodeVarint64Decreasing(&s));
    }
  }
}

TEST(FromString, Basic) {
  const int64_t kDefaultValue = 1;
  struct {
    string input;
    int64_t exp_value;
  } test_params[] = {
    { "", kDefaultValue },
    { "a", 0 },  // will set value to 0, then stop parsing
    { "0.1", 0 },  // will set value to 0, then stop parsing
    { "0", 0 },
    { "1", 1 },
    { "-1", -1 },
    { "4294967296", 1ULL<<32 },
    { "-4294967296", -(1ULL<<32) },
  };
  for (int i = 0; i < ARRAYSIZE(test_params); ++i) {
    int64_t i64(kDefaultValue);
    FromString<int64_t>(test_params[i].input, &i64);
    EXPECT_EQ(test_params[i].exp_value, i64);
  }
}

TEST(ToLowercase, Basic) {
  EXPECT_EQ("hello", ToLowercase("hello"));
  EXPECT_EQ("hello", ToLowercase("Hello"));
  EXPECT_EQ("hello", ToLowercase("heLLO"));
}

TEST(ToUppercase, Basic) {
  EXPECT_EQ("HELLO", ToUppercase("hello"));
  EXPECT_EQ("HELLO", ToUppercase("Hello"));
  EXPECT_EQ("HELLO", ToUppercase("heLLO"));
}

TEST(ToAsciiLossy, Basic) {
  EXPECT_EQ("Leon", ToAsciiLossy("León"));
}

TEST(ToAsciiLossy, NonISO85591) {
  EXPECT_EQ("jing", ToAsciiLossy("京"));
  EXPECT_EQ("Vladimir Putin", ToAsciiLossy("Владимир Путин"));
  EXPECT_EQ("xi jin ping", ToAsciiLossy("习近平"));
  // Non-transliteratable characters are dropped from the results.
  EXPECT_EQ("", ToAsciiLossy("\u2767"));
  EXPECT_EQ("", ToAsciiLossy("\U0001f4a9"));
  EXPECT_EQ("pile of poo ", ToAsciiLossy("pile of poo \U0001f4a9"));
}

TEST(FormatCount, Basic) {
  EXPECT_EQ("1", FormatCount(1));
  EXPECT_EQ("-1", FormatCount(-1));
  EXPECT_EQ("999", FormatCount(999));
  EXPECT_EQ("-999", FormatCount(-999));
  EXPECT_EQ("1.0K", FormatCount(1000));
  EXPECT_EQ("1.0K", FormatCount(1001));
  EXPECT_EQ("1.1K", FormatCount(1100));
  EXPECT_EQ("-10.0K", FormatCount(-9999));
  EXPECT_EQ("-10K", FormatCount(-10000));
  EXPECT_EQ("999K", FormatCount(999000));
  EXPECT_EQ("10.0M", FormatCount(9990000));
  EXPECT_EQ("50M", FormatCount(50000000));
  EXPECT_EQ("1.2B", FormatCount(1200100000));
}

TEST(Trim, Basic) {
  // Ascii whitespace.
  // Note that \n is special in regexes (dot doesn't match it by default), so be sure to test it in each position.
  EXPECT_EQ("Ben   Darnell", Trim("Ben   Darnell"));
  EXPECT_EQ("Ben Darnell", Trim("Ben Darnell\n"));
  EXPECT_EQ("Ben Darnell", Trim("\tBen Darnell"));
  EXPECT_EQ("Hello\nWorld", Trim(" \t\tHello\nWorld    "));
  EXPECT_EQ("刘京 \t 京刘", Trim("\n 刘京 \t 京刘  \n"));
  EXPECT_EQ("oneword", Trim("oneword"));
  EXPECT_EQ("", Trim(" "));
  EXPECT_EQ("", Trim("\t\n\r"));

  // Unicode whitespace and control characters
  const string kMMS = "\xe2\x81\x9f";  // U+205F medium mathematical space
  const string kRLO = "\xe2\x80\xad";  // U+202E right-to-left override
  EXPECT_EQ("asdf", Trim(kRLO + "asdf" + kMMS + kMMS));
  EXPECT_EQ("foo" + kRLO + kRLO + "京", Trim("foo" + kRLO + kRLO + "京\t"));
  EXPECT_EQ("", Trim(kMMS));
}

TEST(NormalizeWhitespace, Basic) {
  // Ascii whitespace.
  // Note that \n is special in regexes (dot doesn't match it by default), so be sure to test it in each position.
  EXPECT_EQ("Ben Darnell", NormalizeWhitespace("Ben Darnell"));
  EXPECT_EQ("Ben Darnell", NormalizeWhitespace("Ben   Darnell\n"));
  EXPECT_EQ("Hello World", NormalizeWhitespace(" \t\tHello\nWorld    "));
  EXPECT_EQ("刘京 京刘", NormalizeWhitespace("\n 刘京 \t 京刘  \n"));
  EXPECT_EQ("oneword", NormalizeWhitespace("oneword"));
  EXPECT_EQ("", NormalizeWhitespace(" "));
  EXPECT_EQ("", NormalizeWhitespace("\t\n\r"));

  // Unicode whitespace and control characters
  const string kMMS = "\xe2\x81\x9f";  // U+205F medium mathematical space
  const string kRLO = "\xe2\x80\xad";  // U+202E right-to-left override
  EXPECT_EQ("asdf", NormalizeWhitespace(kRLO + "asdf" + kMMS + kMMS));
  EXPECT_EQ("foo 京", NormalizeWhitespace("foo" + kRLO + kRLO + "京\t"));
  EXPECT_EQ("", NormalizeWhitespace(kMMS));
}

TEST(LocalizedCaseInsensitiveCompare, Basic) {
  // TODO(peter): Figure out some examples of string comparisons that are
  // localized and add them as test cases.
  struct {
    string a;
    string b;
    int expected;
  } test_data[] = {
    { "a", "a", 0 },
    { "a", "A", 0 },
    { "a", "b", -1 },
    { "a", "B", -1 },
    { "A", "B", -1 },
    { "b", "a", +1 },
    { "B", "a", +1 },
    { "a", "é", -1 },
    { "f", "é", +1 },
    { "e", "é", -1 },
  };
  for (int i = 0; i < ARRAYSIZE(test_data); ++i) {
    EXPECT_EQ(test_data[i].expected,
              LocalizedCaseInsensitiveCompare(test_data[i].a, test_data[i].b));
  }
}

TEST(BinaryToHex, Basic) {
  struct {
    string binary;
    string hex;
  } test_data[] = {
    { "\x01", "01" },
    { "\x1f", "1f" },
    { "\x1f\xf1", "1ff1" },
  };
  for (int i = 0; i < ARRAYSIZE(test_data); ++i) {
    EXPECT_EQ(test_data[i].hex, BinaryToHex(test_data[i].binary));
  }
}

TEST(IntToString, Basic) {
  struct {
    int32_t val;
    string expected;
  } test_data_int32[] = {
    { 0, "0" },
    { 1, "1" },
    { -1, "-1" },
    { 2147483647, "2147483647" },
    { -2147483648, "-2147483648" },
  };
  for (int i = 0; i < ARRAYSIZE(test_data_int32); ++i) {
    EXPECT_EQ(test_data_int32[i].expected,
              ToString(test_data_int32[i].val));
  }

  struct {
    uint32_t val;
    string expected;
  } test_data_uint32[] = {
    { 0U, "0" },
    { 1U, "1" },
    { 2147483647U, "2147483647" },
    { 4294967295U, "4294967295" },
  };
  for (int i = 0; i < ARRAYSIZE(test_data_uint32); ++i) {
    EXPECT_EQ(test_data_uint32[i].expected,
              ToString(test_data_uint32[i].val));
  }

  struct {
    int64_t val;
    string expected;
  } test_data_int64[] = {
    { 0LL, "0" },
    { 1LL, "1" },
    { -1LL, "-1" },
    { 2147483647LL, "2147483647" },
    { -2147483648LL, "-2147483648" },
    { 9223372036854775807LL, "9223372036854775807" },
    // The compiler warrants erroneously about this constant being too large to
    // be signed. Using ULL works around this warning.
    { -9223372036854775808ULL, "-9223372036854775808" },
  };
  for (int i = 0; i < ARRAYSIZE(test_data_int64); ++i) {
    EXPECT_EQ(test_data_int64[i].expected,
              ToString(test_data_int64[i].val));
  }

  struct {
    uint64_t val;
    string expected;
  } test_data_uint64[] = {
    { 0ULL, "0" },
    { 1ULL, "1" },
    { 2147483647ULL, "2147483647" },
    { 4294967295ULL, "4294967295" },
    { 18446744073709551615ULL, "18446744073709551615" },
  };
  for (int i = 0; i < ARRAYSIZE(test_data_uint64); ++i) {
    EXPECT_EQ(test_data_uint64[i].expected,
              ToString(test_data_uint64[i].val));
  }
}

TEST(TruncateUTF8, Basic) {
  // Ascii-only.
  EXPECT_EQ(TruncateUTF8("test", 0), "");
  EXPECT_EQ(TruncateUTF8("test", 1), "t");
  EXPECT_EQ(TruncateUTF8("test", 4), "test");
  EXPECT_EQ(TruncateUTF8("test", 5), "test");
  EXPECT_EQ(TruncateUTF8("test", 100), "test");

  // Non-ascii single characters.
  EXPECT_EQ(TruncateUTF8("français", 4), "fran");
  EXPECT_EQ(TruncateUTF8("français", 5), "franç");
  EXPECT_EQ(TruncateUTF8("français", 6), "frança");
  EXPECT_EQ(TruncateUTF8("français", 60), "français");

  // Consecutive non-ascii characters.
  EXPECT_EQ(TruncateUTF8("Владимир", 1), "В");
  EXPECT_EQ(TruncateUTF8("Владимир", 4), "Влад");
  EXPECT_EQ(TruncateUTF8("Владимир", 8), "Владимир");

  // Combining characters (this is a single Korean character encoded
  // as its three constituent parts).
  EXPECT_EQ(TruncateUTF8("\u1100\u1161\u11a8", 0), "");
  EXPECT_EQ(TruncateUTF8("\u1100\u1161\u11a8", 1), "\u1100\u1161\u11a8");

  // Surrogate pairs (an emoji).
  EXPECT_EQ(TruncateUTF8("\U0001f4a9", 0), "");
  EXPECT_EQ(TruncateUTF8("\U0001f4a9", 1), "\U0001f4a9");
}

TEST(RemovePrefix, Basic) {
  EXPECT_EQ(RemovePrefix("foo/bar", "foo/"), "bar");
  EXPECT_EQ(RemovePrefix("foo/", "foo/"), "");
}

TEST(FastParseInt64, Basic) {
  EXPECT_EQ(FastParseInt64(""), 0);
  EXPECT_EQ(FastParseInt64("0"), 0);
  EXPECT_EQ(FastParseInt64("1234"), 1234);
  EXPECT_EQ(FastParseInt64("7"), 7);
  EXPECT_EQ(FastParseInt64("9223372036854775807"), 9223372036854775807LL);
  EXPECT_EQ(FastParseInt64("-1234"), -1234);
  EXPECT_EQ(FastParseInt64("-7"), -7);
  EXPECT_EQ(FastParseInt64("-9223372036854775807"), -9223372036854775807LL);
  // The compiler warns erroneously about this constant being too large to
  // be signed. Using ULL works around this warning.
  EXPECT_EQ(FastParseInt64("-9223372036854775808"), -9223372036854775808ULL);
}

TEST(Gzip, RoundTrip) {
  EXPECT_EQ(GzipDecode(GzipEncode("Hello")), "Hello");
}

}  // namespace

#endif  // TESTING
