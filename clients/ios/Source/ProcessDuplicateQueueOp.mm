// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.
//
// TODO
//
// - Should we compare any bits of the photo metadata? Timestamp? Location?
//
// - We do not allow duplicates even when the user has the photo duplicated in
//   their asset library. Andy thought we should in order to minimize false
//   positives.

#import "AsyncState.h"
#import "ImageIndex.h"
#import "PhotoManager.h"
#import "PhotoStorage.h"
#import "PhotoView.h"
#import "ProcessDuplicateQueueOp.h"
#import "UIAppState.h"

namespace {

// Thresholds for comparing thumbnails and full size images. We give a bit more
// leeway to the thumbnail comparison as jpeg compression artifacts can be more
// dominant at the smaller size.
const float kStrongCompareThumbnailThreshold = 5;
const float kStrongCompareFullThreshold = 2;

void CleanupViewfinderImages(
    UIAppState* state, const PhotoHandle& photo,
    int64_t photo_id, const DBHandle& updates) {
  if ((photo.get() && photo->shared()) ||
      state->CloudStorageEnabled()) {
    return;
  }
  // If we're not uploading the photo, delete the viewfinder images in order
  // to avoid consuming excessive disk space. These images will be
  // regenerated when the photo is shared.
  state->photo_storage()->Delete(PhotoMediumFilename(photo_id), updates);
  state->photo_storage()->Delete(PhotoFullFilename(photo_id), updates);
  state->photo_storage()->Delete(PhotoOriginalFilename(photo_id), updates);
}

void CleanupViewfinderImages(
    UIAppState* state, int64_t photo_id, const DBHandle& updates) {
  PhotoHandle photo = state->photo_table()->LoadPhoto(photo_id, updates);
  CleanupViewfinderImages(state, photo, photo_id, updates);
}

void CleanupViewfinderImages(UIAppState* state, int64_t photo_id) {
  DBHandle updates = state->NewDBTransaction();
  CleanupViewfinderImages(state, photo_id, updates);
  updates->Commit();
}

}  // namespace

ProcessDuplicateQueueOp::ProcessDuplicateQueueOp(
    UIAppState* state, int64_t photo_id, CompletionBlock completion)
    : state_(state),
      photo_id_(photo_id),
      completion_(completion),
      aspect_ratio_(1),
      candidate_index_(0) {
}

ProcessDuplicateQueueOp::~ProcessDuplicateQueueOp() {
}

void ProcessDuplicateQueueOp::New(
    UIAppState* state, int64_t local_id, CompletionBlock completion) {
  ProcessDuplicateQueueOp* op = new ProcessDuplicateQueueOp(
      state, local_id, completion);
  op->Run();
}

void ProcessDuplicateQueueOp::Run() {
  PhotoHandle ph = state_->photo_table()->LoadPhoto(photo_id_, state_->db());
  if (!ph.get() || ph->has_episode_id()) {
    Finish(0, "");
    return;
  }

  aspect_ratio_ = ph->aspect_ratio();
  candidates_.assign(ph->candidate_duplicates().begin(),
                     ph->candidate_duplicates().end());

  // Ensure that we've generated the viewfinder thumbnail and full images.
  if (!state_->photo_storage()->Exists(PhotoThumbnailFilename(photo_id_)) ||
      !state_->photo_storage()->Exists(PhotoFullFilename(photo_id_))) {
    ph->clear_images();
    state_->photo_manager()->LoadViewfinderImages(
        photo_id_, state_->db(), ^(bool success) {
          if (!success) {
            Quarantine("load: unable to load viewfinder images");
            return;
          }
          photo_orig_md5_ = ph->images().orig().md5();
          ProcessNextCandidate();
        });
  } else {
    ProcessNextCandidate();
  }
}

void ProcessDuplicateQueueOp::ProcessNextCandidate() {
  if (candidate_index_ > 0) {
    CleanupViewfinderImages(state_, candidates_[candidate_index_ - 1]);
  }

  for (;;) {
    if (candidate_index_ >= candidates_.size()) {
      Finish(0, "");
      return;
    }

    const int64_t candidate_id = candidates_[candidate_index_++];
    PhotoHandle candidate = state_->photo_table()->LoadPhoto(candidate_id, state_->db());
    if (!candidate.get()) {
      continue;
    }

    // If the md5s of the original images match, we can stop processing
    // immediately. This is a huge performance win since it avoids downloading
    // any images from the server for comparison in the common case that a user
    // has simply upgraded to iOS 7.
    if (!photo_orig_md5_.empty() &&
        photo_orig_md5_ == candidate->images().orig().md5()) {
      Finish(candidate_id, "original md5s match");
      return;
    }

    LoadPotentialDuplicateThumbnail(candidate_id);
    break;
  }
}

void ProcessDuplicateQueueOp::LoadPotentialDuplicateThumbnail(int64_t candidate_id) {
  if (photo_thumbnail_.get()) {
    // We've already loaded the thumbnail image for the potential
    // duplicate. Jump straight to loading the candidate thumbnail.
    LoadCandidateImages(candidate_id);
    return;
  }

  state_->photo_manager()->LoadLocalThumbnail(photo_id_, ^(Image image) {
      if (!image.get()) {
        // Unable to load thumbnail. Quarantine.
        Quarantine("load: unable to load thumbnail");
        return;
      }

      photo_thumbnail_ = image;
      LoadCandidateImages(candidate_id);
    });
}

void ProcessDuplicateQueueOp::LoadPotentialDuplicateFull(
    int64_t candidate_id, float thumbnail_c) {
  if (photo_full_.get()) {
    // We've already loaded the full size image for the potential
    // duplicate. Jump straight to loading the candidate full size image.
    LoadCandidateFull(candidate_id, thumbnail_c);
    return;
  }

  const CGSize load_size = AspectFit(
      CGSizeMake(kFullSize, kFullSize), aspect_ratio_).size;
  state_->photo_manager()->LoadLocalPhoto(
      photo_id_, load_size, ^(Image image) {
        if (!image.get()) {
          // Unable to load thumbnail. Quarantine.
          Quarantine("load: unable to full size image");
          return;
        }
        image.set_scale(1);
        photo_full_ = image;
        LoadCandidateFull(candidate_id, thumbnail_c);
    });
}

void ProcessDuplicateQueueOp::LoadCandidateImages(int64_t candidate_id) {
  // Ensure that the candidate thumbnail was generated from the medium size
  // image and is not the quick thumbnail generated from the asset
  // library. We'll only have an asset library thumbnail if the candidate has
  // not been uploaded to the server (i.e. we've found potential duplicates
  // within the assets library).
  const PhotoPathMetadata m = state_->photo_storage()->Metadata(
      PhotoThumbnailFilename(candidate_id));
  if (m.parent_size() == kMediumSize) {
    LoadCandidateThumbnail(candidate_id);
    return;
  }

  state_->photo_manager()->LoadViewfinderImages(
      candidate_id, state_->db(), ^(bool success) {
        if (!success) {
          ProcessNextCandidate();
          return;
        }
        LoadCandidateThumbnail(candidate_id);
      });
}

void ProcessDuplicateQueueOp::LoadCandidateThumbnail(int64_t candidate_id) {
  state_->photo_manager()->LoadLocalThumbnail(candidate_id, ^(Image image) {
      if (!image.get()) {
        ProcessNextCandidate();
        return;
      }

      const float c = StrongCompareImages(photo_thumbnail_, image);
      LOG("%d: thumbnail compare (%d): %f", photo_id_, candidate_id, c);
      if (c > kStrongCompareThumbnailThreshold) {
        ProcessNextCandidate();
        return;
      }

      LoadPotentialDuplicateFull(candidate_id, c);
    });
}

void ProcessDuplicateQueueOp::LoadCandidateFull(
    int64_t candidate_id, float thumbnail_c) {
  PhotoHandle ph = state_->photo_table()->LoadPhoto(candidate_id, state_->db());
  if (!ph.get()) {
    ProcessNextCandidate();
    return;
  }

  void (^done)(Image image) = ^(Image image) {
    if (!image.get()) {
      ProcessNextCandidate();
      return;
    }
    image.set_scale(1);
    const float c = StrongCompareImages(photo_full_, image);
    LOG("%d: full compare (%d): %f (%f)", photo_id_, candidate_id, c, thumbnail_c);
    if (c > kStrongCompareFullThreshold) {
      ProcessNextCandidate();
      return;
    }

    Finish(candidate_id, Format("full-size images match: %f", c));
  };

  const CGSize load_size = AspectFit(
      CGSizeMake(kFullSize, kFullSize), ph->aspect_ratio()).size;

  // We need to try to load the local photo first in order to mark for
  // download.
  state_->photo_manager()->LoadLocalPhoto(
      candidate_id, load_size, ^(Image image) {
        if (!image.get()) {
          state_->photo_manager()->LoadNetworkPhoto(
              candidate_id, load_size, done);
          return;
        }
        done(image);
      });
}

void ProcessDuplicateQueueOp::Quarantine(const string& reason) {
  DBHandle updates = state_->NewDBTransaction();
  PhotoHandle ph = state_->photo_table()->LoadPhoto(photo_id_, updates);
  if (ph.get()) {
    ph->Quarantine(reason, updates);
  }
  updates->Commit();

  state_->async()->dispatch_background(^{
      completion_();
      delete this;
    });
}

void ProcessDuplicateQueueOp::Finish(int64_t original_id, const string& reason) {
  DBHandle updates = state_->NewDBTransaction();
  PhotoHandle photo = state_->photo_table()->LoadPhoto(photo_id_, updates);
  if (photo.get()) {
    if (!photo->has_episode_id()) {
      CleanupViewfinderImages(state_, photo, photo_id_, updates);
    }

    PhotoHandle original;
    if (original_id != 0) {
      original = state_->photo_table()->LoadPhoto(original_id, updates);
      CleanupViewfinderImages(state_, original, original_id, updates);
    }

    if (original.get()) {
      LOG("%s: duplicate of %s (%s): %.1f ms",
          photo->id(), original->id(), reason, timer_.Milliseconds());

      // The potential duplicate (photo) is a duplicate of original.
      original->Lock();
      photo->Lock();

      // If we've found the original move all of the asset keys and
      // perceptual fingerprints into the original.
      for (int i = 0; i < photo->asset_keys_size(); ++i) {
        original->AddAssetKey(photo->asset_keys(i));
      }

      for (int i = 0; i < photo->perceptual_fingerprint().terms_size(); ++i) {
        const string& term = photo->perceptual_fingerprint().terms(i);
        ImageFingerprint* f = original->mutable_perceptual_fingerprint();
        bool found = false;
        for (int j = 0; j < f->terms_size(); ++j) {
          if (term == f->terms(j)) {
            found = true;
            break;
          }
        }
        if (!found) {
          f->add_terms(term);
        }
      }

      // Delete the photo (the duplicate) before saving the original in order
      // to generate the proper sequence of asset key deletions and puts.
      photo->DeleteAndUnlock(updates);
      original->SaveAndUnlock(updates);
    } else {
      LOG("%s: not a duplicate: %.1f ms", photo->id(), timer_.Milliseconds());

      // The potential duplicate (photo) is a unique photo. Clear the
      // candidate duplicates in order to allow it to appear in the library.
      photo->Lock();
      photo->clear_candidate_duplicates();
      if (!photo->has_episode_id()) {
        state_->episode_table()->AddPhotoToEpisode(photo, updates);
      }
      photo->SaveAndUnlock(updates);
    }
  }

  updates->Commit();

  state_->async()->dispatch_background(^{
      completion_();
      delete this;
    });
}

// local variables:
// mode: c++
// end:
