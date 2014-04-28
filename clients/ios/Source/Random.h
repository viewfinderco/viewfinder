// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_RANDOM_H
#define VIEWFINDER_RANDOM_H

class Random {
 public:
  explicit Random(unsigned seed)
      : seed_(seed) {
  }

  int32_t Next32();
  int64_t Next64();

  int32_t operator()(int n) {
    return Next32() % n;
  }

 private:
  unsigned seed_;
};

#endif  // VIEWFINDER_RANDOM_H
