// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "Appearance.h"
#import "Testing.h"

namespace {

TEST(AppearanceTest, ParseRgbColor) {
  struct {
    const char* spec;
    const Vector4f expected;
    const bool success;
  } kTestdata[] = {
    { "", Vector4f(0, 0, 0, 0), false },
    { "#", Vector4f(0, 0, 0, 0), false },
    { "#1", Vector4f(0, 0, 0, 0), false },
    { "#12", Vector4f(0, 0, 0, 0), false },
    { "#12345", Vector4f(0, 0, 0, 0), false },
    { "#1234567", Vector4f(0, 0, 0, 0), false },
    { "#123", Vector4f(0x11, 0x22, 0x33, 0xff) / 255.0, true },
    { "#4567", Vector4f(0x44, 0x55, 0x66, 0x77) / 255.0, true },
    { "#abcdef", Vector4f(0xab, 0xcd, 0xef, 0xff) / 255.0, true },
    { "#89abcdef", Vector4f(0x89, 0xab, 0xcd, 0xef) / 255.0, true },
  };
  for (int i = 0; i < ARRAYSIZE(kTestdata); ++i) {
    Vector4f result;
    EXPECT_EQ(kTestdata[i].success, ParseRgbColor(kTestdata[i].spec, &result));
    EXPECT(kTestdata[i].expected.equal(result))
        << ": " << kTestdata[i].expected << " != " << result;
  }
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
