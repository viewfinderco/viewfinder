// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_MATH_UTILS_H
#define VIEWFINDER_MATH_UTILS_H

// Returns min_t if val < min_val. Returns max_t if val > max_val. Otherwise
// returns the linear interpolation between (min_t, min_val) and (max_t,
// max_val).
template <typename T>
T LinearInterp(T val, T min_val, T max_val, T min_t, T max_t) {
  if (val < min_val) {
    return min_t;
  }
  if (val > max_val) {
    return max_t;
  }
  return min_t + (max_t - min_t) * (val - min_val) / (max_val - min_val);
}

#endif // VIEWFINDER_MATH_UTILS_H
