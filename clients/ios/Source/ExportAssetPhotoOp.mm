// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "ExportAssetPhotoOp.h"
#import "FileUtils.h"
#import "PhotoManager.h"
#import "PhotoStorage.h"
#import "ServerUtils.h"
#import "UIAppState.h"

ExportAssetPhotoOp::ExportAssetPhotoOp(
    UIAppState* state, int64_t photo_id,
    CompletionBlock completion)
    : state_(state),
      photo_id_(photo_id),
      photo_(state_->photo_table()->LoadPhoto(photo_id, state_->db())),
      // Try to load the original image first. This will likely fail if the
      // image did not originate on this device. After the original, we try to
      // load the full size photo.
      sizes_(L(kOriginalSize, kFullSize)),
      completion_([completion copy]) {
  DCHECK(dispatch_is_main_thread());

  // TODO(ben): Download original size if available. Note that the download is
  // straightforward, though it can be time consuming.
}

ExportAssetPhotoOp::~ExportAssetPhotoOp() {
}

void ExportAssetPhotoOp::New(UIAppState* state, int64_t photo_id,
                             CompletionBlock completion) {
  ExportAssetPhotoOp* op = new ExportAssetPhotoOp(state, photo_id, completion);
  op->Run();
}

void ExportAssetPhotoOp::Run() {
  if (!photo_.get()) {
    LOG("photo: %s is not a valid photo id", photo_id_);
    Finish("");
    return;
  }

  while (!sizes_.empty()) {
    const int size = sizes_.front();
    sizes_.erase(sizes_.begin());

    void (^done)(const string& path, const string& md5) =
        ^(const string& path, const string& md5) {
      LoadImageDataDone(path, md5, size);
    };

    if (state_->photo_manager()->MaybeLoadImageData(photo_, size, done)) {
      return;
    }
  }

  LOG("photo: %s: failed to load image data to export to assets library",
      photo_->id());
  Finish("");
}

void ExportAssetPhotoOp::LoadImageDataDone(
    const string& path, const string& md5, int size) {
  NSData* jpeg_data = NULL;
  if (!path.empty()) {
    jpeg_data = ReadFileToData(path);
  }
  if (!jpeg_data) {
    LOG("photo: %s: unable to load \"%s\" for export",
        photo_->id(), PhotoSizeSuffix(size));
    Run();
    return;
  }
  LOG("photo: %s: export to assets library: %s",
      photo_->id(), PhotoSizeSuffix(size));
  // Hold the asset mutex during the export so that PhotoManager::NewAssetPhoto
  // won't see the new asset until we've updated the metadata.
  state_->photo_manager()->assets_mu_.Lock();
  state_->AddAsset(jpeg_data, NULL, ^(string asset_url, string asset_key) {
      AddAssetDone(asset_url);
    });
}

void ExportAssetPhotoOp::AddAssetDone(const string& asset_url) {
  if (!asset_url.empty()) {
    // Add the newly-created asset url to the photo.
    DBHandle updates = state_->NewDBTransaction();
    // We've just exported a photo that did not previously have an
    // asset key, so add it.
    photo_->Lock();
    // HACK: This is just an asset url, not a key (with
    // fingerprint). NewAssetPhoto will see the url match and update
    // the fingerprint for us.
    photo_->AddAssetKey(EncodeAssetKey(asset_url, ""));
    photo_->Save(updates);
    photo_->Unlock();
    updates->Commit();
  }
  state_->photo_manager()->assets_mu_.Unlock();
  Finish(asset_url);
}

void ExportAssetPhotoOp::Finish(const string& asset_url) {
  completion_(asset_url);
  delete this;
}

// local variables:
// mode: c++
// end:
