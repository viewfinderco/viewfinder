// Copyright 2013 Viewfinder. All rights reserved.
// Author: Ben Darnell

#ifdef TESTING

#import "PhoneUtils.h"
#import "Testing.h"


TEST(PhoneUtilsTest, IsValidPhoneNumber) {
  EXPECT(IsValidPhoneNumber("14242345678", "US"));
  EXPECT(IsValidPhoneNumber("4242345678", "US"));  // Leading "1" is optional.
  EXPECT(!IsValidPhoneNumber("1424234567", "US"));  // Not enough digits.
  EXPECT(!IsValidPhoneNumber("424234567", "US"));  // Not enough digits.
  EXPECT(IsValidPhoneNumber("+14242345678", "US"));  // International format.
  EXPECT(IsValidPhoneNumber("(424) 234-5678", "US"));
  EXPECT(IsValidPhoneNumber("(42) (4234)-5678", "US"));  // Messed-up formatting is ignored.

  EXPECT(!IsValidPhoneNumber("14242345678", "FR"));  // US number not valid in FR.
  EXPECT(IsValidPhoneNumber("+14242345678", "FR"));  // International format always works.
}

TEST(PhoneUtilsTest, IsPhoneNumberPrefix) {
  EXPECT(IsPhoneNumberPrefix("12345"));
  EXPECT(IsPhoneNumberPrefix("+1234"));
  EXPECT(IsPhoneNumberPrefix("(123) 45"));
  EXPECT(IsPhoneNumberPrefix("+1-2-3"));
  EXPECT(!IsPhoneNumberPrefix("abcd"));
  EXPECT(!IsPhoneNumberPrefix("123abc"));
  EXPECT(!IsPhoneNumberPrefix("+1-b-3"));
}

TEST(PhoneUtilsTest, FormatPhoneNumberPrefix) {
  EXPECT_EQ(FormatPhoneNumberPrefix("4241234567", "US"), "(424) 123-4567");
  EXPECT_EQ(FormatPhoneNumberPrefix("424123", "US"), "424-123");
  EXPECT_EQ(FormatPhoneNumberPrefix("424", "US"), "424");
  EXPECT_EQ(FormatPhoneNumberPrefix("+14241234567", "US"), "+1 424-123-4567");
  EXPECT_EQ(FormatPhoneNumberPrefix("+1424123", "US"), "+1 424-123");
  EXPECT_EQ(FormatPhoneNumberPrefix("(42) (4123)-4567", "US"), "(424) 123-4567");
  EXPECT_EQ(FormatPhoneNumberPrefix("+33123456", "US"), "+33 1 23 45 6");
}

TEST(PhoneUtilsTest, NormalizedPhoneNumber) {
  EXPECT_EQ(NormalizedPhoneNumber("4241234567", "US"), "+14241234567");
  EXPECT_EQ(NormalizedPhoneNumber("(424) 123-4567", "US"), "+14241234567");
  EXPECT_EQ(NormalizedPhoneNumber("+14241234567", "FR"), "+14241234567");
}

#endif  // TESTING
