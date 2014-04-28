// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "STLUtils.h"
#import "Testing.h"
#import "ValueUtils.h"

namespace {

TEST(ValueUtilsTest, InvalidType) {
  // We can only retrieve an array or dict if the object type is compatible.
  Dict d("a", 1);
  ASSERT(!d.find_array("a").get());
  ASSERT(!d.find_dict("a").get());
  ASSERT_EQ(1, d.find_value("a").int_value());

  Array a(1, 2, 3);
  ASSERT(!a.at<Array>(0).get());
  ASSERT(!a.at<Dict>(1).get());
  ASSERT_EQ(3, a.at<Value>(2).int_value());

  Set s(4, 5, 6);

  // Trying to create an array using a dict or set object fails.
  ASSERT(!Array(d.get()).get());
  ASSERT(!Array(s.get()).get());
  ASSERT_EQ(0, Array(s.get()).size());

  // Trying to create a dict using an array or set object fails.
  ASSERT(!Dict(a.get()).get());
  ASSERT(!Dict(s.get()).get());
  ASSERT_EQ(0, Dict(s.get()).size());

  // Trying to create a set using an array or dict object fails.
  ASSERT(!Set(a.get()).get());
  ASSERT(!Set(d.get()).get());
  ASSERT_EQ(0, Set(d.get()).size());
}

TEST(ValueUtilsTest, ArrayEnumeration) {
  std::set<string> expected_keys(L("a", "b", "c"));
  Array a("a", "b", "c");
  for (id obj in a.array()) {
    ASSERT(!expected_keys.empty());
    ASSERT_EQ(ToString(obj), *expected_keys.begin());
    expected_keys.erase(ToString(obj));
  }
  ASSERT(expected_keys.empty());
}

TEST(ValueUtilsTest, DictEnumeration) {
  std::unordered_set<string> expected_keys(L("a", "b", "c"));
  Dict d("a", 1, "b", 2, "c", 3);
  for (id obj in d.dict()) {
    ASSERT_EQ(1, expected_keys.erase(ToString(obj)));
  }
  ASSERT(expected_keys.empty());
}

}  // namespace

#endif  // TESTING

// local variables:
// mode: c++
// end:
