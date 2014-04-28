// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "Format.h"
#import "Testing.h"

namespace {

void Check(const string& expected, const Formatter& format) {
  const string result = format.ToString();
  EXPECT_EQ(result, expected);
}

template <typename Tail>
void Check(const string& expected, const Formatter::ArgList<Tail>& args) {
  const string result = args.ToString();
  EXPECT_EQ(result, expected);
}

TEST(FormatTest, Basic) {
  // Pass-through formatting.
  Check("%", Format("%%"));
  Check("% hello % world", Format("%% hello %% world"));

  // Signed integer formatting.
  Check("42",    Format("%d") % 42);
  Check("42",    Format("%-d") % 42);
  Check("   42", Format("%5d") % 42);
  Check("42   ", Format("%-5d") % 42);
  Check("00042", Format("%05d") % 42);
  Check("42   ", Format("%-05d") % 42);
  Check("  +42", Format("%+5d") % 42);
  Check("  -42", Format("%5d") % -42);
  Check("  -42", Format("%+5d") % -42);
  Check("+0042", Format("%+05d") % 42);
  Check("-0042", Format("%+05d") % -42);
  Check("  042", Format("%5.3d") % 42);
  Check("  042", Format("%05.3d") % 42);
  Check("042  ", Format("%-5.3d") % 42);
  Check(" +042", Format("%+5.3d") % 42);
  Check(" -042", Format("%+5.3d") % -42);
  Check(" +042", Format("%+05.3d") % 42);
  Check(" -042", Format("%+05.3d") % -42);
  Check("+042 ", Format("%+-5.3d") % 42);
  Check("-042 ", Format("%+-5.3d") % -42);
  Check("042",   Format("%2.3d") % 42);
  Check("+042",  Format("%+2.3d") % 42);
  Check(" 042",  Format("% 2.3d") % 42);
  Check(" 42",   Format("% d") % 42);
  Check("+42",   Format("% +d") % 42);
  Check("+42",   Format("%+ d") % 42);

  // Signed integer formatting.
  Check("42",    Format("%i") % 42);
  Check("42",    Format("%-i") % 42);
  Check("   42", Format("%5i") % 42);
  Check("42   ", Format("%-5i") % 42);
  Check("00042", Format("%05i") % 42);
  Check("42   ", Format("%-05i") % 42);
  Check("  +42", Format("%+5i") % 42);
  Check("  -42", Format("%5i") % -42);
  Check("  -42", Format("%+5i") % -42);
  Check("+0042", Format("%+05i") % 42);
  Check("-0042", Format("%+05i") % -42);
  Check("  042", Format("%5.3i") % 42);
  Check("  042", Format("%05.3i") % 42);
  Check("042  ", Format("%-5.3i") % 42);
  Check(" +042", Format("%+5.3i") % 42);
  Check(" -042", Format("%+5.3i") % -42);
  Check(" +042", Format("%+05.3i") % 42);
  Check(" -042", Format("%+05.3i") % -42);
  Check("+042 ", Format("%+-5.3i") % 42);
  Check("-042 ", Format("%+-5.3i") % -42);
  Check("042",   Format("%2.3i") % 42);
  Check("+042",  Format("%+2.3i") % 42);
  Check(" 042",  Format("% 2.3i") % 42);
  Check(" 42",   Format("% i") % 42);
  Check("+42",   Format("% +i") % 42);
  Check("+42",   Format("%+ i") % 42);

  // Unsigned integer formatting.
  Check("42",    Format("%u") % 42);
  Check("42",    Format("%-u") % 42);
  Check("   42", Format("%5u") % 42);
  Check("42   ", Format("%-5u") % 42);
  Check("00042", Format("%05u") % 42);
  Check("42   ", Format("%-05u") % 42);
  Check("   42", Format("%+5u") % 42);
  Check("00042", Format("%+05u") % 42);
  Check("  042", Format("%5.3u") % 42);
  Check("  042", Format("%05.3u") % 42);
  Check("042  ", Format("%-5.3u") % 42);
  Check("  042", Format("%+5.3u") % 42);
  Check("  042", Format("%+05.3u") % 42);
  Check("042  ", Format("%+-5.3u") % 42);
  Check("042",   Format("%2.3u") % 42);
  Check("042",   Format("%+2.3u") % 42);
  Check("042",   Format("% 2.3u") % 42);
  Check("42",    Format("% u") % 42);
  Check("42",    Format("% +u") % 42);
  Check("42",    Format("%+ u") % 42);

  // Hexadecimal formatting.
  Check("2a",    Format("%x") % 42);
  Check("2a",    Format("%-x") % 42);
  Check("   2a", Format("%5x") % 42);
  Check("2a   ", Format("%-5x") % 42);
  Check("0002a", Format("%05x") % 42);
  Check("2a   ", Format("%-05x") % 42);
  Check("   2a", Format("%+5x") % 42);
  Check("0002a", Format("%+05x") % 42);
  Check("0x2a",  Format("%#x") % 42);
  Check(" 0x2a", Format("%#5x") % 42);
  Check("0x02a", Format("%#05x") % 42);
  Check("  02a", Format("%5.3x") % 42);
  Check("  02a", Format("%05.3x") % 42);
  Check("02a  ", Format("%-5.3x") % 42);
  Check("  02a", Format("%+5.3x") % 42);
  Check("  02a", Format("%+05.3x") % 42);
  Check("02a  ", Format("%+-5.3x") % 42);
  Check("0x02a", Format("%#5.3x") % 42);
  Check(" 0x2a", Format("%#5.2x") % 42);
  Check("0x2a ", Format("%#-5.2x") % 42);

  // Hexadecimal (capitalized) formatting.
  Check("2A",    Format("%X") % 42);
  Check("2A",    Format("%-X") % 42);
  Check("   2A", Format("%5X") % 42);
  Check("2A   ", Format("%-5X") % 42);
  Check("0002A", Format("%05X") % 42);
  Check("2A   ", Format("%-05X") % 42);
  Check("   2A", Format("%+5X") % 42);
  Check("0002A", Format("%+05X") % 42);
  Check("0X2A",  Format("%#X") % 42);
  Check(" 0X2A", Format("%#5X") % 42);
  Check("0X02A", Format("%#05X") % 42);
  Check("  02A", Format("%5.3X") % 42);
  Check("  02A", Format("%05.3X") % 42);
  Check("02A  ", Format("%-5.3X") % 42);
  Check("  02A", Format("%+5.3X") % 42);
  Check("  02A", Format("%+05.3X") % 42);
  Check("02A  ", Format("%+-5.3X") % 42);
  Check("0X02A", Format("%#5.3X") % 42);
  Check(" 0X2A", Format("%#5.2X") % 42);
  Check("0X2A ", Format("%#-5.2X") % 42);

  // Octal formatting.
  Check("52",    Format("%o") % 42);
  Check("52",    Format("%-o") % 42);
  Check("   52", Format("%5o") % 42);
  Check("52   ", Format("%-5o") % 42);
  Check("00052", Format("%05o") % 42);
  Check("52   ", Format("%-05o") % 42);
  Check("   52", Format("%+5o") % 42);
  Check("00052", Format("%+05o") % 42);
  Check("052",   Format("%#o") % 42);
  Check("  052", Format("%#5o") % 42);
  Check("00052", Format("%#05o") % 42);
  Check("  052", Format("%5.3o") % 42);
  Check("  052", Format("%05.3o") % 42);
  Check("052  ", Format("%-5.3o") % 42);
  Check("  052", Format("%+5.3o") % 42);
  Check("  052", Format("%+05.3o") % 42);
  Check("052  ", Format("%+-5.3o") % 42);
  Check(" 0052", Format("%#5.3o") % 42);
  Check("0052 ", Format("%#-5.3o") % 42);
  Check("  052", Format("%#5.2o") % 42);
  Check("052  ", Format("%#-5.2o") % 42);
  Check("00052", Format("%#5.4o") % 42);
  Check("00052", Format("%#-5.4o") % 42);

  // Fixed floating point formatting.
  Check("42.400000", Format("%f") % 42.4);
  Check("42.400000", Format("%0f") % 42.4);
  Check("42",        Format("%0.0f") % 42.4);
  Check("42.4",      Format("%0.1f") % 42.4);
  Check("    42.0",  Format("%8.1f") % 42.0);
  Check("   -42.0",  Format("%8.1f") % -42.0);
  Check("   +42.0",  Format("%+8.1f") % 42.0);
  Check("   -42.0",  Format("%+8.1f") % -42.0);
  Check("+00042.0",  Format("%+08.1f") % 42.0);
  Check("-00042.0",  Format("%+08.1f") % -42.0);
  Check("+00042.0",  Format("%#+08.1f") % 42.0);
  Check("-00042.0",  Format("%#+08.1f") % -42.0);
  Check("+000042.",  Format("%#+08.0f") % 42.0);
  Check("-000042.",  Format("%#+08.0f") % -42.0);
  Check("+42.0   ",  Format("%#+-08.1f") % 42.0);
  Check("-42.0   ",  Format("%#+-08.1f") % -42.0);

  // TODO(pmattis): Scientific floating point formatting.
  // TODO(pmattis): Hexadecimal floating point formatting.

  // Character formatting.
  Check("h", Format("%c") % 'h');
  Check("h", Format("%c") % "hello");

  // Bool formatting.
  Check("1",      Format("%d") % true);
  Check("0",      Format("%d") % false);
  Check("     1", Format("%6d") % true);
  Check("     0", Format("%6d") % false);
  Check("000001", Format("%06d") % true);
  Check("000000", Format("%06d") % false);
  Check("true",   Format("%#d") % true);
  Check("false",  Format("%#d") % false);

  // String formatting.
  Check("hello",  Format("%s") % "hello");
  Check(" hello", Format("%6s") % "hello");
  Check("hello ", Format("%-6s") % "hello");
  Check("hel",    Format("%0.3s") % "hello");
  Check("   hel", Format("%6.3s") % "hello");
  Check("hel   ", Format("%-6.3s") % "hello");
  Check(" hello", Format("%*s") % 6 % "hello");
  Check("hello ", Format("%-*s") % 6 % "hello");
  Check("   hel", Format("%*.3s") % 6 % "hello");
  Check("hel   ", Format("%-*.3s") % 6 % "hello");
  Check("hel",    Format("%0.*s") % 3 % "hello");
  Check("   hel", Format("%6.*s") % 3 % "hello");
  Check("hel   ", Format("%-6.*s") % 3 % "hello");
  Check("hel",    Format("%*.*s") % 0 % 3 % "hello");
  Check("   hel", Format("%*.*s") % 6 % 3 % "hello");
  Check("hel   ", Format("%-*.*s") % 6 % 3 % "hello");

  // Multiple arguments.
  Check("42 hello", Format("%d %s") % 42 % "hello");
  Check("hello 42", Format("%d %s") % "hello" % 42);
  Check("1 2 3 4 5", Format("%d %d %d %d %d") % 1 % 2 % 3 % 4 % 5);
}

}  // namespace

#endif  // TESTING
