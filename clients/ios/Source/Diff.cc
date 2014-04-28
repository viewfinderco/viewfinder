// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.
//
// The diff code is adapted from the google diff-match-patch library, but
// c++-ified and simplified. It implements Myers' diff algorithm with a few
// additional speedups (checks for common simple cases):
//
//   E. Myers, "An O(ND) Difference Algorithm and Its Variations,"
//   Algorithmica 1, 2 (1986), 251-266.

/*
 * Copyright 2008 Google Inc. All Rights Reserved.
 * Author: fraser@google.com (Neil Fraser)
 * Author: mikeslemmer@emailscrubbed.com (Mike Slemmer)
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * Diff Match and Patch
 * http://code.google.com/p/google-diff-match-patch/
 */

#include "Diff.h"
#include "Logging.h"
#include "Utils.h"

namespace {

// A helper class which allows the diff algorithm to work on an
// array of integers instead of bytes. This simplifies the utf-8
// handling: we convert both text strings to arrays of integers.
class IntSlice {
 public:
  IntSlice(Slice slice) {
    for (;;) {
      int uc = utfnext(&slice);
      if (uc == -1) {
        return;
      }
      ints_.push_back(uc);
    }
  }
  IntSlice(const IntSlice& is, int start, int n = npos) {
    if (n == std::numeric_limits<int>::max()) {
      n = is.size() - start;
    }
    for (int i = start; i < start + n; ++i) {
      ints_.push_back(is[i]);
    }
  }

  IntSlice substr(int start, int n = npos) {
    return IntSlice(*this, start, n);
  }

  void remove_prefix(int n) {
    int orig_size = ints_.size();
    ints_.erase(ints_.begin(), ints_.begin() + n);
    CHECK_EQ(ints_.size(), orig_size - n);
  }

  int size() const { return ints_.size(); }
  bool empty() const { return ints_.empty(); }
  int operator[](int i) const { return ints_[i]; }

 private:
  static const int npos;
  // TODO(spencer): share underlying array.
  // Pete suggests moving code in constructor to create the array of
  // unicode characters into a method. Then make IntSlice just keep
  // a pointer and length into the array.
  vector<int> ints_;
};

const int IntSlice::npos = std::numeric_limits<int>::max();


class Differ {
 public:
  Differ(vector<DiffOp>* out)
      : out_(out) {
  }

  void DiffMain(IntSlice from, int from_offset, IntSlice to, int to_offset) {
    // Add a MATCH for the common prefix.
    const int prefix = CommonPrefix(from, to);
    AddEdit(DiffOp::MATCH, from.substr(0, prefix), from_offset);
    from.remove_prefix(prefix);
    to.remove_prefix(prefix);
    from_offset += prefix;
    to_offset += prefix;

    // Add a MATCH for the common suffix.
    const int suffix = CommonSuffix(from, to);

    DiffCompute(from.substr(0, from.size() - suffix), from_offset,
                to.substr(0, to.size() - suffix), to_offset);

    AddEdit(DiffOp::MATCH, from.substr(from.size() - suffix),
            from_offset + from.size() - suffix);
  }

 public:
  static int CommonPrefix(IntSlice a, IntSlice b) {
    const int n = std::min(a.size(), b.size());
    for (int i = 0; i < n; ++i) {
      if (a[i] != b[i]) {
        return i;
      }
    }
    return n;
  }

  static int CommonSuffix(IntSlice a, IntSlice b) {
    const int n = std::min(a.size(), b.size());
    for (int i = 1; i <= n; ++i) {
      if (a[a.size() - i] != b[b.size() - i]) {
        return i - 1;
      }
    }
    return n;
  }

  void AddEdit(DiffOp::Type type, IntSlice str, int offset) {
    if (str.empty()) {
      return;
    }
    if (!out_->empty()) {
      // Combine sequential edit operations.
      DiffOp* o = &out_->back();
      if (o->type == type) {
        o->length += str.size();
        return;
      }
    }
    out_->push_back(DiffOp(type, offset, str.size()));
  }

  void DiffCompute(IntSlice from, int from_offset, IntSlice to, int to_offset) {
    if (from.empty()) {
      // Simple insertion.
      AddEdit(DiffOp::INSERT, to, to_offset);
      return;
    }
    if (to.empty()) {
      // Simple deletion.
      AddEdit(DiffOp::DELETE, from, from_offset);
      return;
    }

    DiffBisect(from, from_offset, to, to_offset);
  }

  void DiffBisect(IntSlice from, int from_offset, IntSlice to, int to_offset) {
    const int max_d = (from.size() + to.size() + 1) / 2;
    const int v_offset = max_d;
    const int v_length = 2 * max_d;
    vector<int> v1(v_length, -1);
    vector<int> v2(v_length, -1);
    v1[v_offset + 1] = 0;
    v2[v_offset + 1] = 0;
    const int delta = from.size() - to.size();
    // If the total number of characters is odd, then the front path will
    // collide with the reverse path.
    const bool front = (delta % 2 != 0);
    // Offsets for start and end of k loop.
    // Prevents mapping of space beyond the grid.
    int k1start = 0;
    int k1end = 0;
    int k2start = 0;
    int k2end = 0;
    for (int d = 0; d < max_d; d++) {
      // Walk the front path one step.
      for (int k1 = -d + k1start; k1 <= d - k1end; k1 += 2) {
        const int k1_offset = v_offset + k1;
        int x1;
        if (k1 == -d || (k1 != d && v1[k1_offset - 1] < v1[k1_offset + 1])) {
          x1 = v1[k1_offset + 1];
        } else {
          x1 = v1[k1_offset - 1] + 1;
        }
        int y1 = x1 - k1;
        while (x1 < from.size() && y1 < to.size() && from[x1] == to[y1]) {
          x1++;
          y1++;
        }
        v1[k1_offset] = x1;
        if (x1 > from.size()) {
          // Ran off the right of the graph.
          k1end += 2;
        } else if (y1 > to.size()) {
          // Ran off the bottom of the graph.
          k1start += 2;
        } else if (front) {
          int k2_offset = v_offset + delta - k1;
          if (k2_offset >= 0 && k2_offset < v_length && v2[k2_offset] != -1) {
            // Mirror x2 onto top-left coordinate system.
            int x2 = from.size() - v2[k2_offset];
            if (x1 >= x2) {
              // Overlap detected.
              v1.clear();
              v2.clear();
              return DiffBisectSplit(from, from_offset, to, to_offset, x1, y1);
            }
          }
        }
      }

      // Walk the reverse path one step.
      for (int k2 = -d + k2start; k2 <= d - k2end; k2 += 2) {
        const int k2_offset = v_offset + k2;
        int x2;
        if (k2 == -d || (k2 != d && v2[k2_offset - 1] < v2[k2_offset + 1])) {
          x2 = v2[k2_offset + 1];
        } else {
          x2 = v2[k2_offset - 1] + 1;
        }
        int y2 = x2 - k2;
        while (x2 < from.size() && y2 < to.size() &&
               from[from.size() - x2 - 1] == to[to.size() - y2 - 1]) {
          x2++;
          y2++;
        }
        v2[k2_offset] = x2;
        if (x2 > from.size()) {
          // Ran off the left of the graph.
          k2end += 2;
        } else if (y2 > to.size()) {
          // Ran off the top of the graph.
          k2start += 2;
        } else if (!front) {
          int k1_offset = v_offset + delta - k2;
          if (k1_offset >= 0 && k1_offset < v_length && v1[k1_offset] != -1) {
            int x1 = v1[k1_offset];
            int y1 = v_offset + x1 - k1_offset;
            // Mirror x2 onto top-left coordinate system.
            x2 = from.size() - x2;
            if (x1 >= x2) {
              // Overlap detected.
              v1.clear();
              v2.clear();
              return DiffBisectSplit(from, from_offset, to, to_offset, x1, y1);
            }
          }
        }
      }
    }
    // Number of diffs equals number of characters, no commonality at all.
    AddEdit(DiffOp::DELETE, from, from_offset);
    AddEdit(DiffOp::INSERT, to, to_offset);
  }

  void DiffBisectSplit(IntSlice from, int from_offset, IntSlice to, int to_offset, int x, int y) {
    const IntSlice from1a = from.substr(0, x);
    const IntSlice from1b = from.substr(x);
    const IntSlice to1a = to.substr(0, y);
    const IntSlice to1b = to.substr(y);

    // Compute both diffs serially.
    DiffMain(from1a, from_offset, to1a, to_offset);
    DiffMain(from1b, from_offset + x, to1b, to_offset + y);
  }

 private:
  vector<DiffOp>* const out_;
};

// CharCounter counts characters in a string and translates positions
// from character counts to other metrics.  Call AdvanceTo to set the
// position in characters, then call offset to get the equivalent
// in the chosen metric.
class CharCounter {
 public:
  CharCounter(const Slice& str, DiffMetric metric)
      : str_(str),
        metric_(metric),
        char_offset_(0),
        offset_(0) {
  }

  // Returns the current offset in the selected metric.
  int offset() { return offset_; };

  // Set the current position to new_char_offset.  Can only move forward.
  void AdvanceTo(int new_char_offset) {
    CHECK_LE(char_offset_, new_char_offset);
    while (char_offset_ < new_char_offset) {
      int chr = utfnext(&str_);
      char_offset_++;
      offset_+= CharSize(chr);
    }
  }

  // Returns the size of the given unicode character according to the
  // selected metric.
  int CharSize(int chr) {
    switch (metric_) {
      case DIFF_CHARACTERS:
        return 1;

      case DIFF_UTF16:
        return (chr < 0xffff) ? 1 : 2;

      default:
        DIE("unknown metric %d", metric_);
    };
  }

 private:
  Slice str_;
  DiffMetric metric_;
  int char_offset_;
  int offset_;
};

}  // namespace

void DiffStrings(Slice from, Slice to, vector<DiffOp>* out, DiffMetric metric) {
  Differ d(out);
  d.DiffMain(IntSlice(from), 0, IntSlice(to), 0);

  if (metric == DIFF_CHARACTERS) {
    // Optimization: Differ uses character counts by default so we can
    // skip the post-processing, although the post-processing would
    // still be correct for DIFF_CHARACTERS.
    return;
  }

  CharCounter from_counter(from, metric);
  CharCounter to_counter(to, metric);
  for (int i = 0; i < out->size(); i++) {
    DiffOp* op = &(*out)[i];

    CharCounter* counter = (op->type == DiffOp::INSERT) ? &to_counter : &from_counter;
    counter->AdvanceTo(op->offset);
    int new_offset = counter->offset();
    counter->AdvanceTo(op->offset + op->length);
    int new_length = counter->offset() - new_offset;
    op->offset = new_offset;
    op->length = new_length;
  }
}
