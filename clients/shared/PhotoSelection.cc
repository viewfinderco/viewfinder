// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <algorithm>
#import "PhotoSelection.h"

ostream& operator<<(ostream& os, const PhotoSelection& ps) {
  os << "(" << ps.photo_id << ", " << ps.episode_id
     << ", [" << (WallTime_Now() - ps.timestamp) << "s ago])";
  return os;
}

PhotoSelectionVec SelectionSetToVec(const PhotoSelectionSet& s) {
  PhotoSelectionVec v(s.begin(), s.end());;
  std::sort(v.begin(), v.end(), SelectionLessThan());
  return v;
}
