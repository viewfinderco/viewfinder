// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_IMAGE_INDEX_H
#define VIEWFINDER_IMAGE_INDEX_H

#import <map>
#import <set>
#import "DB.h"
#import "ImageFingerprint.pb.h"
#import "StringUtils.h"
#import "Utils.h"

class ImageIndex {
 public:
  ImageIndex(bool histogram = false);
  ~ImageIndex();

  // Adds the specified fingerprint and id to the index.
  void Add(const ImageFingerprint& fingerprint,
           const string& id, const DBHandle& updates);

  // Removes the specified fingerprint and id from the index.
  void Remove(const ImageFingerprint& fingerprint,
              const string& id, const DBHandle& updates);

  // Search the index for the specified fingerprint, returning the ids of any
  // matching fingerprints.
  int Search(const DBHandle& db, const ImageFingerprint& fingerprint,
             StringSet* matched_ids) const;

  // Returns a "pretty" histogram of the bits that were set in indexed
  // fingerprints. Note that this histogram is not persistent and is only
  // mainted if "true" was passed to the histogram parameter of the
  // constructor.
  string PrettyHistogram() const;

  // Return the total/unique indexed tags. These functions are slow.
  int TotalTags(const DBHandle& db) const;
  int UniqueTags(const DBHandle& db) const;

  static ImageFingerprint Intersect(
      const ImageFingerprint& a, const ImageFingerprint& b);
  static int HammingDistance(
      const ImageFingerprint& a, const ImageFingerprint& b);

 private:
  ScopedPtr<vector<int> > histogram_;
  int histogram_count_;
};

ostream& operator<<(ostream& os, const ImageFingerprint& f);

#endif // VIEWFINDER_IMAGE_INDEX_H
