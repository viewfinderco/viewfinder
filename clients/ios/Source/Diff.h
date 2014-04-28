// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_DIFF_H
#define VIEWFINDER_DIFF_H

#include "Utils.h"

struct DiffOp {
  enum Type {
    MATCH,   // offset/length refer to "from"
    INSERT,  // offset/length refer to "to"
    DELETE,  // offset/length refer to "from"
  };
  DiffOp()
      : type(MATCH),
        offset(0),
        length(0) {
  }
  DiffOp(Type t, int o, int l)
      : type(t),
        offset(o),
        length(l) {
  }
  Type type;
  int offset;
  int length;
};

// Computes list of difference ops to transform string "from" to
// string "to". This method is utf-8 aware and the component pieces
// are broken according to utf-8 character boundaries. The offset
// component of each diff op is specified in terms of the chosen metric.
enum DiffMetric {
  DIFF_CHARACTERS,  // Number of unicode (utf-8) characters
  DIFF_UTF16,  // Number of utf-16 code points (surrogate pairs count as 2)
  //DIFF_BYTES,
};
void DiffStrings(Slice from, Slice to, vector<DiffOp>* out, DiffMetric metric);

#endif  // VIEWFINDER_DIFF_H
