// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#import "STLUtils.h"
#import "Testing.h"

namespace {

TEST(STLUtilsTest, ContainerLiteral) {
  typedef std::vector<string> V;
  EXPECT_EQ(1, V(L("a")).size());
  EXPECT_EQ(2, V(L("a", "b")).size());
  EXPECT_EQ(3, V(L("a", "b", "c")).size());
  EXPECT_EQ(4, V(L("a", "b", "c", "d")).size());
  EXPECT_EQ("a", V(L("a", "b", "c", "d"))[0]);
  EXPECT_EQ("b", V(L("a", "b", "c", "d"))[1]);
  EXPECT_EQ("c", V(L("a", "b", "c", "d"))[2]);
  EXPECT_EQ("d", V(L("a", "b", "c", "d"))[3]);
  EXPECT_EQ("e", V(L("a", "b", "c", "d", "e"))[4]);
  EXPECT_EQ("f", V(L("a", "b", "c", "d", "e", "f"))[5]);
  EXPECT_EQ("g", V(L("a", "b", "c", "d", "e", "f", "g"))[6]);
  EXPECT_EQ("h", V(L("a", "b", "c", "d", "e", "f", "g", "h"))[7]);
  EXPECT_EQ("i", V(L("a", "b", "c", "d", "e", "f", "g", "h", "i"))[8]);
  EXPECT_EQ("j", V(L("a", "b", "c", "d", "e", "f", "g", "h", "i", "j"))[9]);

  typedef std::set<int> S;
  EXPECT_EQ(0, *S(L(0)).rbegin());
  EXPECT_EQ(1, *S(L(0, 1)).rbegin());
  EXPECT_EQ(2, *S(L(0, 1, 2)).rbegin());
  EXPECT_EQ(3, *S(L(0, 1, 2, 3)).rbegin());
  EXPECT_EQ(4, *S(L(0, 1, 2, 3, 4)).rbegin());
  EXPECT_EQ(5, *S(L(0, 1, 2, 3, 4, 5)).rbegin());
  EXPECT_EQ(6, *S(L(0, 1, 2, 3, 4, 5, 6)).rbegin());
  EXPECT_EQ(7, *S(L(0, 1, 2, 3, 4, 5, 6, 7)).rbegin());
  EXPECT_EQ(8, *S(L(0, 1, 2, 3, 4, 5, 6, 7, 8)).rbegin());
  EXPECT_EQ(9, *S(L(0, 1, 2, 3, 4, 5, 6, 7, 8, 9)).rbegin());
}

}  // namespace

#endif  // TESTING
