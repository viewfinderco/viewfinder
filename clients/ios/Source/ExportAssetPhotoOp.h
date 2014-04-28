// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_EXPORT_ASSET_PHOTO_OP_H
#define VIEWFINDER_EXPORT_ASSET_PHOTO_OP_H

#import "PhotoTable.h"

class UIAppState;

class ExportAssetPhotoOp {
  typedef void (^CompletionBlock)(string asset_url);

 public:
  // Exports the given photo into the assets library, downloading its full-size
  // version if necessary. If the photo is already in the assets library a new
  // copy will be made.
  static void New(UIAppState* state, int64_t photo_id,
                  CompletionBlock completion);

 private:
  ExportAssetPhotoOp(UIAppState* state, int64_t photo_id,
                     CompletionBlock completion);
  ~ExportAssetPhotoOp();

  void Run();
  void LoadImageDataDone(const string& path, const string& md5, int size);
  void AddAssetDone(const string& asset_url);
  void Finish(const string& asset_url);

 private:
  UIAppState* const state_;
  const int64_t photo_id_;
  const PhotoHandle photo_;
  vector<int> sizes_;
  CompletionBlock completion_;
};

#endif  // VIEWFINDER_EXPORT_ASSET_PHOTO_OP_H
