// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#include <stdlib.h>
#include "Random.h"

int32_t Random::Next32() {
  return rand_r(&seed_);
}

int64_t Random::Next64() {
  const int64_t next = Next32();
  return (next - 1) * 2147483646L + Next32();
}
