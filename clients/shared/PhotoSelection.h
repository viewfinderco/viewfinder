// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_PHOTO_SELECTION_H
#define VIEWFINDER_PHOTO_SELECTION_H

#import <unordered_set>
#import "WallTime.h"

struct PhotoSelection {
  int64_t photo_id;
  int64_t episode_id;
  WallTime timestamp;
  PhotoSelection()
      : photo_id(0), episode_id(0), timestamp(0) {
  }
  PhotoSelection(int64_t pi, int64_t ei, WallTime t = 0)
      : photo_id(pi),
        episode_id(ei),
        timestamp(!t ? WallTime_Now() : t) {
  }
};

ostream& operator<<(ostream& os, const PhotoSelection& ps);

struct PhotoSelectionHash {
  size_t operator()(const PhotoSelection& ps) const {
    // TODO(spencer): we need a hashing module.
    const size_t kPrime = 31;
    size_t result = kPrime + int(ps.photo_id ^ (ps.photo_id >> 32));
    return result * kPrime + int(ps.episode_id ^ (ps.episode_id >> 32));
  }
};

struct PhotoSelectionEqualTo {
  bool operator()(const PhotoSelection& a, const PhotoSelection& b) const {
    return a.photo_id == b.photo_id && a.episode_id == b.episode_id;
  }
};

struct SelectionLessThan {
  bool operator()(const PhotoSelection& a, const PhotoSelection& b) const {
    return a.timestamp < b.timestamp;
  }
};

typedef std::unordered_set<PhotoSelection,
                                PhotoSelectionHash,
                                PhotoSelectionEqualTo> PhotoSelectionSet;
typedef vector<PhotoSelection> PhotoSelectionVec;

// Convert photo selection set to vector.
PhotoSelectionVec SelectionSetToVec(const PhotoSelectionSet& s);

#endif  // VIEWFINDER_PHOTO_SELECTION_H

// local variables:
// mode: c++
// end:
