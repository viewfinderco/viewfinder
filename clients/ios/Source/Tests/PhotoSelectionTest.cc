// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifdef TESTING

#include "PhotoSelection.h"
#include "Testing.h"

namespace {

TEST(PhotoSelectionTest, Basic) {
  PhotoSelectionSet pss;
  pss.insert(PhotoSelection(1, 5, 0.1));
  pss.insert(PhotoSelection(2, 4, 1));
  pss.insert(PhotoSelection(3, 3, 1.1));
  pss.insert(PhotoSelection(4, 2, 2.1));
  pss.insert(PhotoSelection(5, 1, 100));

  EXPECT_EQ(5, pss.size());
  PhotoSelectionVec psv = SelectionSetToVec(pss);
  EXPECT_EQ(psv.size(), pss.size());

  for (int i = 0; i < psv.size(); ++i) {
    EXPECT_EQ(i + 1, psv[i].photo_id);
    EXPECT_EQ(5 - i, psv[i].episode_id);
  }

  // Add some redundant entries.
  pss.insert(PhotoSelection(1, 5, 101));
  pss.insert(PhotoSelection(5, 1, 102));
  EXPECT_EQ(5, pss.size());

  // Add another selection with existing photo id but new episode id.
  pss.insert(PhotoSelection(1, 6, 103));
  EXPECT_EQ(6, pss.size());
  psv = SelectionSetToVec(pss);
  EXPECT_EQ(psv.size(), pss.size());
  EXPECT_EQ(1, psv[5].photo_id);
  EXPECT_EQ(6, psv[5].episode_id);
}
}  // namespace

#endif  // TESTING
