// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#include "Diff.h"
#include "Testing.h"
#include "Utils.h"

namespace {

string DiffStringsDebug(Slice from, Slice to) {
  vector<DiffOp> out;
  DiffStrings(from, to, &out, DIFF_CHARACTERS);
  string r;
  for (int i = 0; i < out.size(); ++i) {
    const DiffOp& op = out[i];
    const char* prefix = "";
    switch (op.type) {
      case DiffOp::MATCH:
        break;
      case DiffOp::INSERT:
        prefix = "+";
        break;
      case DiffOp::DELETE:
        prefix = "-";
        break;
    }
    if (!r.empty()) {
      r += ":";
    }
    Slice use = (op.type == DiffOp::MATCH || op.type == DiffOp::DELETE) ?
                from : to;
    const char* start = NULL;
    for (int j = 0; j < op.offset + op.length; ++j) {
      if (j == op.offset) {
        start = use.data();
      }
      CHECK_NE(-1, utfnext(&use));
    }
    r += Format("%s%s", prefix, Slice(start, use.data() - start));
    // Append the offset if not 0.
    if (op.offset != 0) {
      r += Format("@%d", op.offset);
    }
  }
  return r;
}

string DiffStringsMetrics(Slice from, Slice to, DiffMetric metric) {
  vector<DiffOp> out;
  DiffStrings(from, to, &out, metric);
  string r;
  for (int i = 0; i < out.size(); i++) {
    const DiffOp& op = out[i];
    const char* prefix = "";
    switch (op.type) {
      case DiffOp::MATCH:
        prefix = "=";
        break;
      case DiffOp::INSERT:
        prefix = "+";
        break;
      case DiffOp::DELETE:
        prefix = "-";
        break;
    };
    if (!r.empty()) {
      r += ":";
    }
    r += Format("%s%d", prefix, op.length);
    if (op.offset != 0) {
      r += Format("@%d", op.offset);
    }
  }
  return r;
}

TEST(DiffTest, Basic) {
  EXPECT_EQ("a", DiffStringsDebug("a", "a"));
  EXPECT_EQ("+a", DiffStringsDebug("", "a"));
  EXPECT_EQ("-a", DiffStringsDebug("a", ""));
  EXPECT_EQ("a:+bc@1", DiffStringsDebug("a", "abc"));
  EXPECT_EQ("a:-bc@1", DiffStringsDebug("abc", "a"));
  EXPECT_EQ("+ab:c", DiffStringsDebug("c", "abc"));
  EXPECT_EQ("-ab:c@2", DiffStringsDebug("abc", "c"));
  EXPECT_EQ("a:+bc@1:d@1", DiffStringsDebug("ad", "abcd"));
  EXPECT_EQ("a:-bc@1:d@3", DiffStringsDebug("abcd", "ad"));
  EXPECT_EQ("a:+b@1:c@1:+d@3", DiffStringsDebug("ac", "abcd"));
  EXPECT_EQ("a:-b@1:c@2:-d@3", DiffStringsDebug("abcd", "ac"));
  EXPECT_EQ("-abc:+def", DiffStringsDebug("abc", "def"));
}

TEST(DiffTest, UTF8) {
  EXPECT_EQ("\u8000", DiffStringsDebug("\u8000", "\u8000"));
  EXPECT_EQ("\u8000:+\u801A@1", DiffStringsDebug("\u8000", "\u8000\u801A"));
  EXPECT_EQ("\u8000:-\u801A@1", DiffStringsDebug("\u8000\u801A", "\u8000"));
  EXPECT_EQ("-\u8000:\u801A@1", DiffStringsDebug("\u8000\u801A", "\u801A"));
  EXPECT_EQ("-a:\u8000@1:-b@2:\u801A@3", DiffStringsDebug("a\u8000b\u801A", "\u8000\u801A"));
  EXPECT_EQ("\u8000:+a@1:\u801A@1:+b@3", DiffStringsDebug("\u8000\u801A", "\u8000a\u801Ab"));
}

TEST(DiffTest, Emoji) {
  // Emoji are special because they're outside the basic multilingual plane.
  // In utf8 everything works normally, but in utf16 they take up two
  // codepoints.
  const char* kManWithTurban = "\U0001f473";
  const char* kPileOfPoo = "\U0001f4a9";
  const char* kMoonViewingCeremony = "\U0001F391";

  // Make sure that the compiler turns \U escapes into utf8.
  EXPECT_EQ("\xf0\x9f\x91\xb3", kManWithTurban);

  // Basic insertion and removal.
  EXPECT_EQ("+\U0001f473", DiffStringsDebug("", kManWithTurban));
  EXPECT_EQ("-\U0001f391", DiffStringsDebug(kMoonViewingCeremony, ""));

  // Edits happen with characters, not bytes.
  EXPECT_EQ("-\U0001f473:+\U0001f4a9", DiffStringsDebug(kManWithTurban, kPileOfPoo));

  // Offsets are measured in characters by default.
  const char* kAddRemoveWithOffset1 = "\U0001f391a b\U0001f473";
  const char* kAddRemoveWithOffset2 = "\U0001f391a c\U0001f4a9";
  EXPECT_EQ("\U0001f391a :-b\U0001f473@3:+c\U0001f4a9@3", DiffStringsDebug(kAddRemoveWithOffset1, kAddRemoveWithOffset2));

  // Check the offset measurements for different metrics.
  EXPECT_EQ("=3:-2@3:+2@3", DiffStringsMetrics(kAddRemoveWithOffset1, kAddRemoveWithOffset2, DIFF_CHARACTERS));
  EXPECT_EQ("=4:-3@4:+3@4", DiffStringsMetrics(kAddRemoveWithOffset1, kAddRemoveWithOffset2, DIFF_UTF16));

  // When lengths change, make sure the metrics are reported for the correct
  // string.
  EXPECT_EQ("-1:+1", DiffStringsMetrics("a", kMoonViewingCeremony, DIFF_CHARACTERS));
  EXPECT_EQ("-1:+2", DiffStringsMetrics("a", kMoonViewingCeremony, DIFF_UTF16));

  // A more complicated (and unfortunately illegible) string that tests
  // some more cases, with changes before and after emoji characters,
  // as well as regular unicode characters (which still count as one
  // codepoint).
  const char* kLongString1 = "\U0001f473 abc 123 \u1234 \U0001f4a9";
  const char* kLongString2 = "\U0001f473 abd 145 \U0001f4a9 \u1200";
  EXPECT_EQ("\U0001f473 ab:-c@4:+d@4: 1@5:-23 \u1234@7:+45@7: \U0001f4a9@11:+ \u1200@11", DiffStringsDebug(kLongString1, kLongString2));

  EXPECT_EQ("=4:-1@4:+1@4:=2@5:-4@7:+2@7:=2@11:+2@11", DiffStringsMetrics(kLongString1, kLongString2, DIFF_CHARACTERS));
  EXPECT_EQ("=5:-1@5:+1@5:=2@6:-4@8:+2@8:=3@12:+2@13", DiffStringsMetrics(kLongString1, kLongString2, DIFF_UTF16));

}

TEST(DiffTest, States) {
  EXPECT_EQ("A:-L@1:+labama@1", DiffStringsDebug("AL", "Alabama"));
  EXPECT_EQ("A:-K@1:+laska@1", DiffStringsDebug("AK", "Alaska"));
  EXPECT_EQ("A:-Z@1:+rizona@1", DiffStringsDebug("AZ", "Arizona"));
  EXPECT_EQ("A:-R@1:+rkansas@1", DiffStringsDebug("AR", "Arkansas"));
  EXPECT_EQ("C:-A@1:+alifornia@1", DiffStringsDebug("CA", "California"));
  EXPECT_EQ("C:-O@1:+olorado@1", DiffStringsDebug("CO", "Colorado"));
  EXPECT_EQ("C:-T@1:+onnecticut@1", DiffStringsDebug("CT", "Connecticut"));
  EXPECT_EQ("D:-E@1:+elaware@1", DiffStringsDebug("DE", "Delaware"));
  EXPECT_EQ("F:-L@1:+lorida@1", DiffStringsDebug("FL", "Florida"));
  EXPECT_EQ("G:-A@1:+eorgia@1", DiffStringsDebug("GA", "Georgia"));
  EXPECT_EQ("H:-I@1:+awaii@1", DiffStringsDebug("HI", "Hawaii"));
  EXPECT_EQ("I:-D@1:+daho@1", DiffStringsDebug("ID", "Idaho"));
  EXPECT_EQ("I:-L@1:+llinois@1", DiffStringsDebug("IL", "Illinois"));
  EXPECT_EQ("I:-N@1:+ndiana@1", DiffStringsDebug("IN", "Indiana"));
  EXPECT_EQ("I:-A@1:+owa@1", DiffStringsDebug("IA", "Iowa"));
  EXPECT_EQ("K:-S@1:+ansas@1", DiffStringsDebug("KS", "Kansas"));
  EXPECT_EQ("K:-Y@1:+entucky@1", DiffStringsDebug("KY", "Kentucky"));
  EXPECT_EQ("L:-A@1:+ouisiana@1", DiffStringsDebug("LA", "Louisiana"));
  EXPECT_EQ("M:-E@1:+aine@1", DiffStringsDebug("ME", "Maine"));
  EXPECT_EQ("M:-D@1:+aryland@1", DiffStringsDebug("MD", "Maryland"));
  EXPECT_EQ("M:-A@1:+assachusetts@1", DiffStringsDebug("MA", "Massachusetts"));
  EXPECT_EQ("M:-I@1:+ichigan@1", DiffStringsDebug("MI", "Michigan"));
  EXPECT_EQ("M:-N@1:+innesota@1", DiffStringsDebug("MN", "Minnesota"));
  EXPECT_EQ("M:-S@1:+ississippi@1", DiffStringsDebug("MS", "Mississippi"));
  EXPECT_EQ("M:-O@1:+issouri@1", DiffStringsDebug("MO", "Missouri"));
  EXPECT_EQ("M:-T@1:+ontana@1", DiffStringsDebug("MT", "Montana"));
  EXPECT_EQ("N:-E@1:+ebraska@1", DiffStringsDebug("NE", "Nebraska"));
  EXPECT_EQ("N:-V@1:+evada@1", DiffStringsDebug("NV", "Nevada"));
  EXPECT_EQ("N:+ew @1:H@1:+ampshire@5", DiffStringsDebug("NH", "New Hampshire"));
  EXPECT_EQ("N:+ew @1:J@1:+ersey@5", DiffStringsDebug("NJ", "New Jersey"));
  EXPECT_EQ("N:+ew @1:M@1:+exico@5", DiffStringsDebug("NM", "New Mexico"));
  EXPECT_EQ("N:+ew @1:Y@1:+ork@5", DiffStringsDebug("NY", "New York"));
  EXPECT_EQ("N:+orth @1:C@1:+arolina@7", DiffStringsDebug("NC", "North Carolina"));
  EXPECT_EQ("N:+orth @1:D@1:+akota@7", DiffStringsDebug("ND", "North Dakota"));
  EXPECT_EQ("O:-H@1:+hio@1", DiffStringsDebug("OH", "Ohio"));
  EXPECT_EQ("O:-K@1:+klahoma@1", DiffStringsDebug("OK", "Oklahoma"));
  EXPECT_EQ("O:-R@1:+regon@1", DiffStringsDebug("OR", "Oregon"));
  EXPECT_EQ("P:-A@1:+ennsylvania@1", DiffStringsDebug("PA", "Pennsylvania"));
  EXPECT_EQ("R:+hode @1:I@1:+sland@7", DiffStringsDebug("RI", "Rhode Island"));
  EXPECT_EQ("S:+outh @1:C@1:+arolina@7", DiffStringsDebug("SC", "South Carolina"));
  EXPECT_EQ("S:+outh @1:D@1:+akota@7", DiffStringsDebug("SD", "South Dakota"));
  EXPECT_EQ("T:-N@1:+ennessee@1", DiffStringsDebug("TN", "Tennessee"));
  EXPECT_EQ("T:-X@1:+exas@1", DiffStringsDebug("TX", "Texas"));
  EXPECT_EQ("U:-T@1:+tah@1", DiffStringsDebug("UT", "Utah"));
  EXPECT_EQ("V:-T@1:+ermont@1", DiffStringsDebug("VT", "Vermont"));
  EXPECT_EQ("V:-A@1:+irginia@1", DiffStringsDebug("VA", "Virginia"));
  EXPECT_EQ("W:-A@1:+ashington@1", DiffStringsDebug("WA", "Washington"));
  EXPECT_EQ("W:+est @1:V@1:+irginia@6", DiffStringsDebug("WV", "West Virginia"));
  EXPECT_EQ("W:-I@1:+isconsin@1", DiffStringsDebug("WI", "Wisconsin"));
  EXPECT_EQ("W:-Y@1:+yoming@1", DiffStringsDebug("WY", "Wyoming"));
}

}  // namespace

#endif  // TESTING
