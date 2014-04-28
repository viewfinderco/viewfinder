// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_TESTS_TEST_ASSETS_H
#define VIEWFINDER_TESTS_TEST_ASSETS_H

#ifdef TESTING

#include <unordered_set>
#include "Utils.h"

@class ALAsset;
@class ALAssetsLibrary;
@class NSData;
@class NSURL;

class TestAssets {
 public:
  TestAssets();
  ~TestAssets();

  NSURL* Add(NSData* jpeg_data = NULL);
  NSURL* AddTextImage(const string& text);
  ALAsset* Lookup(NSURL* url);
  string GetBytes(ALAsset* asset);
  string GetBytes(NSURL* url);
  void Delete(NSURL* url);
  void Poke();

  ALAssetsLibrary* library() { return library_; }

 private:
  ALAssetsLibrary* library_;
  std::unordered_set<string> urls_;
};

#endif  // TESTING

#endif  // VIEWFINDER_TESTS_TEST_ASSETS_H
