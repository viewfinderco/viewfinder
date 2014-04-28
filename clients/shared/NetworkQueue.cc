// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <leveldb/iterator.h>
#import "AppState.h"
#import "AsyncState.h"
#import "ContactManager.h"
#import "FileUtils.h"
#import "NetworkManager.h"
#import "NetworkQueue.h"
#import "NotificationManager.h"
#import "PathUtils.h"
#import "PhotoStorage.h"
#import "PlacemarkHistogram.h"
#import "ScopedPtr.h"
#import "Server.pb.h"
#import "ServerUtils.h"
#import "StringUtils.h"
#import "Timer.h"

namespace {

const string kNextSequenceKey = DBFormat::metadata_key("next_network_queue_sequence");
const string kNetworkQueueKeyPrefix = DBFormat::network_queue_key("");

const int kMaxPhotosPerUpload = 10;

const DBRegisterKeyIntrospect kNetworkQueueKeyIntrospect(
    kNetworkQueueKeyPrefix, [](Slice key) {
      int priority;
      int64_t sequence;
      if (!DecodeNetworkQueueKey(key, &priority, &sequence)) {
        return string();
      }
      return string(Format("%d/%d", priority, sequence));
    }, NULL);

// Returns the adjustment that should be made to the activity count for an operation
// at the given priority (which we use for a crude approximation of the type of operation).
double AdjustedCountForPriority(int priority) {
  switch (priority) {
    // Uploading one photo results in four operations, so count each one as 0.25.
    // If "store originals" is turned on, there is a fifth operation (which counts as 1.0
    // so the count in this case will be two per photo).  This is reasonable since we
    // present "store originals" as a separate feature, and otherwise we'd have to do something
    // special when backfilling originals.
    case PRIORITY_UI_UPLOAD_PHOTO:
    case PRIORITY_UPLOAD_PHOTO:
    case PRIORITY_UPLOAD_PHOTO_MEDIUM:
      return 0.25;
    default:
      return 1;
  }
}

}  // namespace

string EncodeNetworkQueueKey(int priority, int64_t sequence) {
  string s(kNetworkQueueKeyPrefix);
  OrderedCodeEncodeVarint32(&s, priority);
  OrderedCodeEncodeVarint64(&s, sequence);
  return s;
}

bool DecodeNetworkQueueKey(Slice key, int* priority, int64_t* sequence) {
  if (!key.starts_with(kNetworkQueueKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kNetworkQueueKeyPrefix.size());
  *priority = OrderedCodeDecodeVarint32(&key);
  *sequence = OrderedCodeDecodeVarint64(&key);
  return true;
}

NetworkQueue::Iterator::Iterator(leveldb::Iterator* iter)
    : iter_(iter),
      done_(false),
      priority_(0),
      sequence_(0) {
  iter_->Seek(kNetworkQueueKeyPrefix);
  while (!done_ && !UpdateState()) {
    iter_->Next();
  }
}

NetworkQueue::Iterator::~Iterator() {
}

void NetworkQueue::Iterator::Next() {
  while (!done_) {
    iter_->Next();
    if (UpdateState()) {
      break;
    }
  }
}

void NetworkQueue::Iterator::SkipPriority() {
  if (done_) {
    return;
  }
  const string next_priority_key = EncodeNetworkQueueKey(priority() + 1, 0);
  iter_->Seek(next_priority_key);
  while (!done_ && !UpdateState()) {
    iter_->Next();
  }
}

bool NetworkQueue::Iterator::UpdateState() {
  op_.Clear();
  if (!iter_->Valid()) {
    done_ = true;
    return true;
  }
  const Slice key(ToSlice(iter_->key()));
  if (!DecodeNetworkQueueKey(key, &priority_, &sequence_)) {
    done_ = true;
  }
  const Slice value(ToSlice(iter_->value()));
  if (!op_.ParseFromArray(value.data(), value.size())) {
    return false;
  }
  return true;
}

NetworkQueue::NetworkQueue(AppState* state)
    : state_(state),
      next_sequence_(0),
      queue_in_progress_(false),
      queue_start_time_(0),
      photo_tmp_dir_(JoinPath(TmpDir(), "photos")) {
  // Remove the photo tmp directory and all of its contents and recreate it.
  DirRemove(photo_tmp_dir_, true);
  DirCreate(photo_tmp_dir_);

  state_->network_ready()->Add([this](int priority) {
      MaybeQueueNetwork(priority);
    });

  // Set up callbacks for handling notification mgr callbacks.
  state_->notification_manager()->process_notifications()->Add(
      [this](const QueryNotificationsResponse& p, const DBHandle& updates) {
        ProcessQueryNotifications(p, updates);
      });
  state_->notification_manager()->nuclear_invalidations()->Add(
      [this](const DBHandle& updates) {
        // A nuclear invalidation. Clear all of the existing invalidations.
        state_->viewpoint_table()->ClearAllInvalidations(updates);
        state_->episode_table()->ClearAllInvalidations(updates);
      });

  // The DB might not have been opened at this point, so don't access it yet.
}

NetworkQueue::~NetworkQueue() {
}

int64_t NetworkQueue::Add(
    int priority, const ServerOperation& op, const DBHandle& updates) {
  MutexLock l(&mu_);
  EnsureInitLocked();
  const int64_t sequence = next_sequence_++;
  state_->db()->Put<int64_t>(kNextSequenceKey, next_sequence_);
  updates->PutProto(EncodeNetworkQueueKey(priority, sequence), op);
  UpdateStatsLocked(priority, op, true);

  updates->AddCommitTrigger("network", [this] {
      state_->async()->dispatch_after_main(0, [this] {
          state_->net_manager()->Dispatch();
        });
    });
  return sequence;
}

void NetworkQueue::Remove(
    int priority, int64_t sequence, const DBHandle& updates) {
  const string key = EncodeNetworkQueueKey(priority, sequence);
  ServerOperation op;
  if (!updates->GetProto(key, &op)) {
    return;
  }
  MutexLock l(&mu_);
  updates->Delete(key);
  UpdateStatsLocked(priority, op, false);

  updates->AddCommitTrigger("network", [this] {
      state_->async()->dispatch_after_main(0, [this] {
          state_->net_manager()->Dispatch();
        });
    });
}

void NetworkQueue::Remove(
    int priority, int64_t sequence,
    const ServerOperation& op, const DBHandle& updates) {
  MutexLock l(&mu_);
  updates->Delete(EncodeNetworkQueueKey(priority, sequence));
  UpdateStatsLocked(priority, op, false);
}

bool NetworkQueue::QueuePhoto(const PhotoHandle& ph, const DBHandle& updates) {
  if (ph->label_error() ||
      ph->candidate_duplicates_size() > 0) {
    // The photo is quarantined or otherwise non-uploadable. Remove it from the
    // queue.
    return DequeuePhoto(ph, updates);
  }

  // Set the priority if it hasn't been set or is less than the currently set
  // priority. Otherwise, add the priority as a stat.
#define MAYBE_SET_PRIORITY(r, p)                \
  if (!priority || (p) < priority) {            \
    if (priority > 0) {                         \
      op.add_stats(priority);                   \
    }                                           \
    priority = p;                               \
    reason = r;                                 \
  } else {                                      \
    op.add_stats(p);                            \
  }

  ServerOperation op;
  int priority = 0;
  const char* reason = NULL;
  if (ph->download_thumbnail()) {
    MAYBE_SET_PRIORITY(
        "download_thumbnail",
        ph->error_ui_thumbnail() ? PRIORITY_UI_THUMBNAIL : PRIORITY_DOWNLOAD_PHOTO);
  }
  if (ph->download_full()) {
    MAYBE_SET_PRIORITY(
        "download_full",
        ph->error_ui_full() ? PRIORITY_UI_FULL : PRIORITY_DOWNLOAD_PHOTO);
  }
  if (ph->download_original()) {
    MAYBE_SET_PRIORITY(
        "download_original",
        ph->error_ui_original() ? PRIORITY_UI_ORIGINAL : PRIORITY_DOWNLOAD_PHOTO);
  }
  if (ph->upload_metadata()) {
    MAYBE_SET_PRIORITY(
        "upload_metadata",
        ph->shared() ? PRIORITY_UI_UPLOAD_PHOTO : PRIORITY_UPLOAD_PHOTO);
  } else if (ph->update_metadata()) {
    MAYBE_SET_PRIORITY(
        "update_metadata",
        ph->shared() ? PRIORITY_UI_UPLOAD_PHOTO : PRIORITY_UPLOAD_PHOTO);
  }
  if (ph->upload_thumbnail()) {
    MAYBE_SET_PRIORITY(
        "upload_thumbnail",
        ph->shared() ? PRIORITY_UI_UPLOAD_PHOTO : PRIORITY_UPLOAD_PHOTO);
  }
  if (ph->upload_full()) {
    MAYBE_SET_PRIORITY(
        "upload_full",
        ph->shared() ? PRIORITY_UI_UPLOAD_PHOTO : PRIORITY_UPLOAD_PHOTO);
  }
  if (ph->upload_medium()) {
    MAYBE_SET_PRIORITY(
        "upload_medium",
        ph->shared() ? PRIORITY_UI_UPLOAD_PHOTO : PRIORITY_UPLOAD_PHOTO_MEDIUM);
  }
  if (ph->upload_original()) {
    // Note: original images are only uploaded when cloud storage is enabled
    // and are never given PRIORITY_UI_UPLOAD_PHOTO.
    MAYBE_SET_PRIORITY("upload_original", PRIORITY_UPLOAD_PHOTO_ORIGINAL);
  }

#undef MAYBE_SET_PRIORITY

  bool changed = false;
  const int64_t old_priority = ph->queue().priority();
  const int64_t old_sequence = ph->queue().sequence();
  // Always dequeue the photo, even if the priority isn't changing, in order to
  // properly update the network queue stats.
  changed = DequeuePhoto(ph, updates);
  if (priority > 0) {
    op.set_update_photo(ph->id().local_id());
    ph->mutable_queue()->set_priority(priority);
    // If the priority of the photo is unchanged, reuse the old sequence
    // number. This is essential to make sure that we process all of the
    // updates for a photo sequentially instead of constantly moving the photo
    // to the end of the queue.
    if (priority == old_priority) {
      MutexLock l(&mu_);
      updates->PutProto(EncodeNetworkQueueKey(priority, old_sequence), op);
      UpdateStatsLocked(priority, op, true);
      ph->mutable_queue()->set_sequence(old_sequence);
    } else {
      ph->mutable_queue()->set_sequence(Add(priority, op, updates));
    }
    changed = true;
    VLOG("queueing %s (%s): %d,%d", ph->id(), reason,
         ph->queue().priority(), ph->queue().sequence());
  }

  return changed;
}

bool NetworkQueue::DequeuePhoto(const PhotoHandle& ph, const DBHandle& updates) {
  if (!ph->has_queue()) {
    return false;
  }
  VLOG("dequeuing %s: %d,%d", ph->id(),
       ph->queue().priority(), ph->queue().sequence());
  Remove(ph->queue().priority(), ph->queue().sequence(), updates);
  ph->clear_queue();
  return true;
}

bool NetworkQueue::QueueActivity(const ActivityHandle& ah, const DBHandle& updates) {
  if (ah->label_error() || ah->provisional()) {
    // The activity is quarantined. Remove it from the queue.
    return DequeueActivity(ah, updates);
  }

  int priority = 0;
  const char* reason = NULL;
  if (ah->upload_activity()) {
    priority = PRIORITY_UI_ACTIVITY;
    reason = "upload_activity";
  }

  // Always pedantically dequeue and queue the activity upload. This is less
  // fragile than relying on other code to have removed any existing queue
  // metadata after the last op was run successfully.
  const int64_t old_priority = ah->queue().priority();
  const int64_t old_sequence = ah->queue().sequence();
  bool changed = DequeueActivity(ah, updates);
  if (priority > 0) {
    ServerOperation op;
    op.mutable_headers()->set_op_id(state_->NewLocalOperationId());
    op.mutable_headers()->set_op_timestamp(WallTime_Now());
    op.set_upload_activity(ah->activity_id().local_id());
    ah->mutable_queue()->set_priority(priority);
    // If the priority of the activity is unchanged, reuse the old sequence
    // number. This is essential to make sure that we process activities in the
    // order they are generated instead of constantly moving them to the end of
    // the queue.
    if (priority == old_priority) {
      // TODO(peter): Share this code with QueuePhoto() and QueueViewpoint().
      MutexLock l(&mu_);
      updates->PutProto(EncodeNetworkQueueKey(priority, old_sequence), op);
      UpdateStatsLocked(priority, op, true);
      ah->mutable_queue()->set_sequence(old_sequence);
    } else {
      ah->mutable_queue()->set_sequence(Add(priority, op, updates));
    }
    changed = true;
    VLOG("queueing %s (%s): %d,%d", ah->activity_id(), reason,
         ah->queue().priority(), ah->queue().sequence());
  }

  return changed;
}

bool NetworkQueue::DequeueActivity(const ActivityHandle& ah, const DBHandle& updates) {
  if (!ah->has_queue()) {
    return false;
  }
  VLOG("dequeuing %s: %d,%d", ah->activity_id(),
       ah->queue().priority(), ah->queue().sequence());
  Remove(ah->queue().priority(), ah->queue().sequence(), updates);
  ah->clear_queue();
  return true;
}

bool NetworkQueue::QueueViewpoint(const ViewpointHandle& vh, const DBHandle& updates) {
  if (vh->label_error() || vh->provisional()) {
    // The viewpoint is quarantined. Remove it from the queue.
    return DequeueViewpoint(vh, updates);
  }

  int priority = 0;
  const char* reason = NULL;
  if (vh->update_metadata() ||
      vh->update_follower_metadata() ||
      vh->update_remove() ||
      vh->update_viewed_seq()) {
    priority = PRIORITY_UPDATE_VIEWPOINT;
    reason = "update_viewpoint";
  }

  // Always pedantically dequeue and queue the viewpoint update. This
  // is less fragile than relying on other code to have removed any
  // existing queue metadata after the last op was run successfully.
  const int64_t old_priority = vh->queue().priority();
  const int64_t old_sequence = vh->queue().sequence();
  bool changed = DequeueViewpoint(vh, updates);
  if (priority > 0) {
    ServerOperation op;
    op.mutable_headers()->set_op_id(state_->NewLocalOperationId());
    op.mutable_headers()->set_op_timestamp(WallTime_Now());
    op.set_update_viewpoint(vh->id().local_id());
    vh->mutable_queue()->set_priority(priority);
    // If the priority of the viewpoint is unchanged, reuse the old sequence
    // number. This is essential to make sure that we process viewpoint updates
    // in the order they are generated instead of constantly moving them to the
    // end of the queue.
    if (priority == old_priority) {
      // TODO(peter): Share this code with QueuePhoto() and QueueActivity().
      MutexLock l(&mu_);
      updates->PutProto(EncodeNetworkQueueKey(priority, old_sequence), op);
      UpdateStatsLocked(priority, op, true);
      vh->mutable_queue()->set_sequence(old_sequence);
    } else {
      vh->mutable_queue()->set_sequence(Add(priority, op, updates));
    }
    changed = true;
    VLOG("queueing viewpoint %s (%s): %d,%d", vh->id(), reason,
         vh->queue().priority(), vh->queue().sequence());
  }

  return changed;
}

bool NetworkQueue::DequeueViewpoint(const ViewpointHandle& vh, const DBHandle& updates) {
  if (!vh->has_queue()) {
    return false;
  }
  VLOG("dequeuing viewpoint %s: %d,%d", vh->id(),
       vh->queue().priority(), vh->queue().sequence());
  Remove(vh->queue().priority(), vh->queue().sequence(), updates);
  vh->clear_queue();
  return true;
}

NetworkQueue::Iterator* NetworkQueue::NewIterator() {
  return new Iterator(state_->db()->NewIterator());
}

bool NetworkQueue::Empty() {
  return TopPriority() == -1;
}

int NetworkQueue::TopPriority() {
  for (ScopedPtr<Iterator> iter(NewIterator());
       !iter->done();
       iter->SkipPriority()) {
    if (ShouldProcessPriority(iter->priority())) {
      return iter->priority();
    }
  }
  return -1;
}

int NetworkQueue::GetNetworkCount() {
  MutexLock l(&mu_);
  EnsureStatsInitLocked();

  double count = 0;
  for (NetworkStatsMap::const_iterator iter(stats_->begin());
       iter != stats_->end();
       ++iter) {
    const int priority = iter->first;
    if (ShouldProcessPriority(priority)) {
      count += iter->second;
    }
  }
  return ceil(count);
}

int NetworkQueue::GetDownloadCount() {
  MutexLock l(&mu_);
  EnsureStatsInitLocked();

  double count = 0;
  for (NetworkStatsMap::const_iterator iter(stats_->begin());
       iter != stats_->end();
       ++iter) {
    const int priority = iter->first;
    if (ShouldProcessPriority(priority) &&
        IsDownloadPriority(priority)) {
      count += iter->second;
    }
  }
  return ceil(count);
}

int NetworkQueue::GetUploadCount() {
  MutexLock l(&mu_);
  EnsureStatsInitLocked();

  double count = 0;
  for (NetworkStatsMap::const_iterator iter(stats_->begin());
       iter != stats_->end();
       ++iter) {
    const int priority = iter->first;
    if (ShouldProcessPriority(priority) &&
        !IsDownloadPriority(priority)) {
      count += iter->second;
    }
  }
  return ceil(count);
}

bool NetworkQueue::ShouldProcessPriority(int priority) const {
  if (priority == PRIORITY_UPLOAD_PHOTO ||
      priority == PRIORITY_UPLOAD_PHOTO_MEDIUM ||
      priority == PRIORITY_UPLOAD_PHOTO_ORIGINAL) {
    if (!state_->CloudStorageEnabled()) {
      return false;
    }
    // TODO(peter): Add a setting to control whether we upload photos over
    // 3g/lte when cloud storage is enabled.
    if (!state_->network_wifi()) {
      return false;
    }
  }
  if (priority == PRIORITY_UPLOAD_PHOTO_ORIGINAL &&
      !state_->store_originals()) {
    return false;
  }
  if (priority == PRIORITY_DOWNLOAD_PHOTO &&
      !state_->network_wifi()) {
    return false;
  }
  return true;
}

bool NetworkQueue::IsDownloadPriority(int priority) const {
  return priority == PRIORITY_UI_THUMBNAIL ||
      priority == PRIORITY_UI_FULL ||
      priority == PRIORITY_UI_ORIGINAL ||
      priority == PRIORITY_DOWNLOAD_PHOTO;
}

void NetworkQueue::CommitQueuedDownloadPhoto(const string& md5, bool retry) {
  if (!queued_download_photo_.get()) {
    LOG("photo: commit failed: no photo download queued");
    return;
  }
  DownloadPhoto* const d = queued_download_photo_.get();

  string filename;
  switch (d->type) {
    case THUMBNAIL:
      filename = PhotoThumbnailFilename(d->photo->id());
      break;
    case MEDIUM:
      filename = PhotoMediumFilename(d->photo->id());
      break;
    case FULL:
      filename = PhotoFullFilename(d->photo->id());
      break;
    case ORIGINAL:
      filename = PhotoOriginalFilename(d->photo->id());
      break;
  }

  const bool error = md5.empty() && !retry;
  if (!error) {
    DBHandle updates = state_->NewDBTransaction();

    if (state_->photo_storage()->AddExisting(
            d->path, filename, md5, d->photo->id().server_id(), updates)) {
      // Clear the download bits on success.
      d->photo->Lock();

      switch (d->type) {
        case THUMBNAIL:
          d->photo->clear_download_thumbnail();
          d->photo->clear_error_download_thumbnail();
          d->photo->clear_error_ui_thumbnail();
          break;
        case MEDIUM:
          d->photo->clear_download_medium();
          d->photo->clear_error_download_medium();
          break;
        case FULL:
          d->photo->clear_download_full();
          d->photo->clear_error_download_full();
          d->photo->clear_error_ui_full();
          break;
        case ORIGINAL:
          d->photo->clear_download_original();
          d->photo->clear_error_download_original();
          d->photo->clear_error_ui_original();
          break;
      }

      d->photo->SaveAndUnlock(updates);
      updates->Commit();
    } else {
      retry = true;
    }
  }

  if (!retry) {
    // Run any download callbacks (on both success and error) after the
    // downloaded photo has been written.
    NotifyDownload(d->photo->id().local_id(), d->type);
  }

  if (error) {
    // A persistent error (e.g. photo does not exist). Stop trying to download
    // the photo.
    DownloadPhotoError(d->photo, d->type);
  }

  queued_download_photo_.reset(NULL);
}

void NetworkQueue::CommitQueuedRemovePhotos(bool error) {
  if (!queued_remove_photos_.get()) {
    LOG("photo: commit failed: no remove photos queued");
    return;
  }

  // TODO(pmattis): How to handle errors? We tried to remove the photos but the
  // server returned an unrecoverable error.

  RemovePhotos* r = queued_remove_photos_.get();

  DBHandle updates = state_->NewDBTransaction();
  // Note, passing in the empty ServerOperation() is okay because the
  // RemovePhotos operation has no sub operations.
  Remove(r->queue.priority(), r->queue.sequence(), ServerOperation(), updates);
  updates->Commit();

  queued_remove_photos_.reset(NULL);
}

void NetworkQueue::CommitQueuedUpdatePhoto(bool error) {
  if (!queued_update_photo_.get()) {
    LOG("photo: commit failed: no photo update queued");
    return;
  }

  PhotoHandle ph = queued_update_photo_->photo;
  queued_update_photo_.reset(NULL);

  if (error) {
    UpdatePhotoError(ph);
    return;
  }

  DBHandle updates = state_->NewDBTransaction();
  ph->Lock();
  ph->clear_update_metadata();
  ph->SaveAndUnlock(updates);
  updates->Commit();
}

void NetworkQueue::CommitQueuedUpdateViewpoint(UpdateViewpointType type, bool error) {
  if (!queued_update_viewpoint_.get()) {
    LOG("photo: commit failed: no viewpoint update queued");
    return;
  }

  ViewpointHandle vh = queued_update_viewpoint_->viewpoint;
  queued_update_viewpoint_.reset(NULL);

  if (error) {
    UpdateViewpointError(vh);
    return;
  }

  DBHandle updates = state_->NewDBTransaction();
  vh->Lock();
  switch (type) {
    case UPDATE_VIEWPOINT_METADATA:
      vh->clear_update_metadata();
      break;
    case UPDATE_VIEWPOINT_FOLLOWER_METADATA:
      vh->clear_update_follower_metadata();
      break;
    case UPDATE_VIEWPOINT_REMOVE:
      vh->clear_update_remove();
      break;
    case UPDATE_VIEWPOINT_VIEWED_SEQ:
      vh->clear_update_viewed_seq();
      break;
    default:
      DCHECK(false) << "unknown update viewpoint type " << type;
      LOG("photo: unknown update viewpoint type: %d", type);
  }
  vh->SaveAndUnlock(updates);
  updates->Commit();
}

void NetworkQueue::CommitQueuedUploadEpisode(
    const UploadEpisodeResponse& r, int status) {
  if (!queued_upload_episode_.get()) {
    LOG("photo: commit failed: no episode upload queued");
    return;
  }

  UploadEpisode* u = queued_upload_episode_.get();
  if (status != 200) {
    // Episode upload failed.
    DBHandle updates = state_->NewDBTransaction();
    EpisodeHandle eh = u->episode;
    for (int i = 0; i < u->photos.size(); ++i) {
      const PhotoHandle& ph = u->photos[i];
      ph->Lock();
      if (ph->error_upload_metadata()) {
        // We had previously failed trying to upload this photo's
        // metadata. Quarantine the photo so that we don't try again.
        ph->Unlock();
        QuarantinePhoto(ph, "upload: metadata", updates);
        continue;
      }
      ph->set_error_upload_metadata(true);
      ph->SaveAndUnlock(updates);
    }
    queued_upload_episode_.reset(NULL);
    // Query the server for the episode metadata again. This will refresh the
    // metadata for all the photos in the episode, resetting their state. If we
    // then attempt to upload their metadata again we'll encounter the
    // error_upload_metadata bit and quarantine the photo.
    EpisodeSelection s;
    s.set_episode_id(eh->id().server_id());
    s.set_get_attributes(true);
    s.set_get_photos(true);
    state_->episode_table()->Invalidate(s, updates);
    updates->Commit();
    return;
  }

  if (u->photos.size() != r.photos_size()) {
    LOG("photo: commit failed: unexpected response size");
    queued_upload_episode_.reset(NULL);
    return;
  }

  DBHandle updates = state_->NewDBTransaction();

  for (int i = 0; i < r.photos_size(); ++i) {
    const PhotoHandle& ph = u->photos[i];
    const PhotoUpdate& u = r.photos(i);
    if (ph->id().server_id() != u.metadata().id().server_id()) {
      LOG("photo: unexpected server id in response: %s != %s",
          ph->id(), u.metadata().id());
      continue;
    }
    ProcessPhoto(ph, r.photos(i), NULL, updates);
    ph->SaveAndUnlock(updates);
  }

  updates->Commit();

  queued_upload_episode_.reset(NULL);
}

void NetworkQueue::CommitQueuedUploadPhoto(bool error) {
  if (!queued_upload_photo_.get()) {
    LOG("photo: commit failed: no photo upload queued");
    return;
  }

  PhotoHandle ph = queued_upload_photo_->photo;
  const PhotoType type = queued_upload_photo_->type;
  const string path = queued_upload_photo_->path;
  queued_upload_photo_.reset(NULL);

  if (error) {
    if (ph->GetDeviceId() == state_->device_id()) {
      // Only indicate upload errors on photos that were created on the current
      // device. If the photo was not created on the current device, we assume
      // that the server already has the photo and that the upload error was
      // because of a spurious content-md5 mismatch.
      UploadPhotoError(ph, type);
      return;
    }
    VLOG("photo: %s unable to upload photo created by device %d (current device %d)",
         ph->id(), ph->GetDeviceId(), state_->device_id());
  }

  DBHandle updates = state_->NewDBTransaction();
  bool delete_photo = false;
  ph->Lock();

  // Clear the upload error bit on success and delete the associated put url.
  switch (type) {
    case THUMBNAIL:
      ph->DeleteURL("tn_put", updates);
      ph->clear_upload_thumbnail();
      ph->clear_error_upload_thumbnail();
      break;
    case MEDIUM:
      ph->DeleteURL("med_put", updates);
      ph->clear_upload_medium();
      ph->clear_error_upload_medium();
      delete_photo = true;
      break;
    case FULL:
      ph->DeleteURL("full_put", updates);
      ph->clear_upload_full();
      ph->clear_error_upload_full();
      delete_photo = ph->HasAssetUrl();
      break;
    case ORIGINAL:
      ph->DeleteURL("orig_put", updates);
      ph->clear_upload_original();
      ph->clear_error_upload_original();
      delete_photo = true;
      break;
  }

  const string filename = PhotoBasename(state_->photo_dir(), path);
  for (int i = 0; i < ph->asset_keys_size(); i++) {
    Slice fingerprint;
    if (!DecodeAssetKey(ph->asset_keys(i), NULL, &fingerprint)) {
      continue;
    }
    // The photo has been uploaded to the server. Store a symlink to the asset
    // key it is associated with in the photo server directory so that we can
    // avoid having to try to upload the photo again if the database format
    // changes.
    state_->photo_storage()->SetAssetSymlink(
        filename, ph->id().server_id(),
        fingerprint.ToString());
    DCHECK_EQ(fingerprint, state_->photo_storage()->ReadAssetSymlink(
                  filename, ph->id().server_id()));
  }

  if (delete_photo && !path.empty()) {
    // The photo has been uploaded to the server, no need to keep the
    // original/medium images around.
    state_->photo_storage()->Delete(filename, updates);
  } else if (!ph->HasAssetUrl()) {
    // The photo was successfully uploaded to the server. Link it to the server
    // photo directory so that we can avoid downloading the photo again if the
    // database format changes.
    state_->photo_storage()->SetServerId(
        filename, ph->id().server_id(), updates);
  }

  ph->SaveAndUnlock(updates);
  updates->Commit();
}

void NetworkQueue::CommitQueuedUploadActivity(bool error) {
  if (!queued_upload_activity_.get()) {
    LOG("photo: commit failed: no activity upload queued");
    return;
  }

  ActivityHandle ah = queued_upload_activity_->activity;
  queued_upload_activity_.reset(NULL);

  if (error) {
    UploadActivityError(ah);
    return;
  }

  DBHandle updates = state_->NewDBTransaction();
  ah->Lock();
  ah->clear_upload_activity();
  ah->SaveAndUnlock(updates);
  updates->Commit();
}

void NetworkQueue::ProcessQueryEpisodes(
    const QueryEpisodesResponse& r, const vector<EpisodeSelection>& v,
    const DBHandle& updates) {
  typedef std::unordered_map<int64_t, EpisodeHandle> EpisodeMap;

  for (int i = 0; i < v.size(); ++i) {
    state_->episode_table()->Validate(v[i], updates);
  }

  for (int i = 0; i < r.episodes_size(); ++i) {
    const QueryEpisodesResponse::Episode& e = r.episodes(i);
    EpisodeMap old_episodes;

    EpisodeHandle eh;
    if (e.has_metadata()) {
      eh = ProcessEpisode(e.metadata(), false, updates);
    }

    for (int j = 0; j < e.photos_size(); ++j) {
      EpisodeHandle old_eh;
      PhotoHandle ph = ProcessPhoto(e.photos(j), &old_eh, updates);
      if (eh.get()) {
        const PhotoMetadata& m = e.photos(j).metadata();
        // Note: Even though we just merged "m" into "ph", we cleared
        // label_removed() and label_unshared() because those labels exist only
        // on the relationship between the photo and the episode we're
        // processing. So it's critically important to use "m.label_removed()"
        // and "m.label_unshared()" in the expression below.
        if (m.label_unshared()) {
          eh->UnsharePhoto(ph->id().local_id());
        } else if (m.label_hidden()) {
          eh->HidePhoto(ph->id().local_id());
        } else if (m.label_removed()) {
          eh->RemovePhoto(ph->id().local_id());
        } else {
          eh->AddPhoto(ph->id().local_id());
          // If the photo has an error, try to unquarantine the photo as
          // this episode may indicate a route through which the photo
          // may be successfully loaded and permanently unquarantined.
          // Dispatch on main thread to avoid re-entering episode locks.
          if (ph->label_error()) {
            const int64_t photo_id = ph->id().local_id();
            state_->async()->dispatch_after_low_priority(0, [this, photo_id] {
                state_->photo_table()->MaybeUnquarantinePhoto(photo_id);
              });
          }
        }

        // If this is the canonical episode for the photo, make sure the local
        // id is correct in PhotoMetadata.
        if (ph->episode_id().server_id() == eh->id().server_id()) {
          ph->mutable_episode_id()->CopyFrom(eh->id());
        }
      }
      if (old_eh.get()) {
        // The photo is changing episodes. Remove it from the old episode. We
        // have to perform this removal after the addition of the photo to the
        // new episode to ensure that the photo is always referenced by an
        // episode so that its images and assets do not get deleted.
        EpisodeHandle& saved_eh = old_episodes[old_eh->id().local_id()];
        if (!saved_eh.get()) {
          saved_eh = old_eh;
          saved_eh->Lock();
        }
        saved_eh->RemovePhoto(ph->id().local_id());
      }
      ph->SaveAndUnlock(updates);
    }

    if (eh.get()) {
      eh->SaveAndUnlock(updates);
    }

    // Only save the old episodes after the new episode has been saved.
    for (EpisodeMap::iterator iter(old_episodes.begin());
         iter != old_episodes.end();
         ++iter) {
      iter->second->SaveAndUnlock(updates);
    }
  }
}

void NetworkQueue::ProcessQueryFollowed(
    const QueryFollowedResponse& r, const DBHandle& updates) {
  for (int i = 0; i < r.viewpoints_size(); ++i) {
    ViewpointHandle vh = ProcessViewpoint(r.viewpoints(i), true, updates);
    vh->SaveAndUnlock(updates);
  }
}

void NetworkQueue::ProcessQueryNotifications(
    const QueryNotificationsResponse& r, const DBHandle& updates) {
  // LOG("process query notifications: %s", r);
  UsageMetadata merged_usage;
  bool found_remote_usage = false;
  for (int i = 0; i < r.notifications_size(); ++i) {
    const QueryNotificationsResponse::Notification& n = r.notifications(i);
    if (n.has_invalidate()) {
      const InvalidateMetadata& invalidate = n.invalidate();
      for (int j = 0; j < invalidate.viewpoints_size(); ++j) {
        state_->viewpoint_table()->Invalidate(invalidate.viewpoints(j), updates);
        VLOG("notification %d invalidated viewpoint %s",
             n.notification_id(), invalidate.viewpoints(j).viewpoint_id());
      }
      for (int j = 0; j < invalidate.episodes_size(); ++j) {
        state_->episode_table()->Invalidate(invalidate.episodes(j), updates);
        VLOG("notification %d invalidated episode %s",
             n.notification_id(), invalidate.episodes(j).episode_id());
      }

      // NOTE: contacts invalidation is handled in
      // ContactManager.ProcessQueryNotifications.
    }
    if (n.has_inline_invalidate()) {
      if (n.inline_invalidate().has_activity()) {
        // Process the activity.
        ActivityHandle ah = ProcessActivity(n.inline_invalidate().activity(), updates);
        ah->SaveAndUnlock(updates);
        VLOG("notification %d added activity %s", n.notification_id(), ah->activity_id());
      }
      if (n.inline_invalidate().has_viewpoint()) {
        // Set the update_seq and viewed_seq values on the indicated
        // viewpoint. If the viewpoint doesn't exist yet, we've
        // probably already written an invalidation for it, but
        // haven't yet queried it. When it's queried, we'll receive
        // up-to-date viewed/update sequence values.
        const QueryNotificationsResponse::InlineViewpoint& iv =
            n.inline_invalidate().viewpoint();
        ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
            iv.viewpoint_id(), updates);
        if (vh.get()) {
          vh->Lock();
          if (iv.has_update_seq() && iv.update_seq() > vh->update_seq()) {
            vh->set_update_seq(iv.update_seq());
          }
          if (iv.has_viewed_seq() && iv.viewed_seq() > vh->viewed_seq()) {
            vh->set_viewed_seq(iv.viewed_seq());
          }
          vh->SaveAndUnlock(updates);
          VLOG("notification %d added viewpoint %s", n.notification_id(), vh->id());
        }
      }
      if (n.inline_invalidate().has_comment()) {
        // An inlined comment. Create the comment directly.
        CommentHandle ch = ProcessComment(n.inline_invalidate().comment(), updates);
        ch->SaveAndUnlock(updates);
        VLOG("added comment %s to %s", ch->comment_id(), ch->viewpoint_id());
      }
      if (n.inline_invalidate().has_usage()) {
        // inlined usage. It is always optional and may be partial (eg: owned-by only).
        merged_usage.MergeFrom(n.inline_invalidate().usage());
        found_remote_usage = true;
      }
    }
  }
  // Only update remote usage once we've merged all entries. This saves db Puts.
  if (found_remote_usage) {
    VLOG("Merged usage: %s", ToString(merged_usage));
    state_->photo_storage()->update_remote_usage(merged_usage);
  }
}

void NetworkQueue::ProcessQueryViewpoints(
    const QueryViewpointsResponse& r, const vector<ViewpointSelection>& v,
    const DBHandle& updates) {
  for (int i = 0; i < v.size(); ++i) {
    state_->viewpoint_table()->Validate(v[i], updates);
  }

  for (int i = 0; i < r.viewpoints_size(); ++i) {
    const QueryViewpointsResponse::Viewpoint& v = r.viewpoints(i);

    ViewpointHandle vh;
    if (v.has_metadata()) {
      vh = ProcessViewpoint(v.metadata(), false, updates);
      VLOG("viewpoint %s", vh->id());
    } else {
      LOG("photo: ERROR: viewpoint id not returned with /query_viewpoints");
    }

    if (vh.get() && v.followers_size() > 0) {
      for (int j = 0; j < v.followers_size(); ++j) {
        if (v.followers(j).has_label_removed() &&
            v.followers(j).has_label_unrevivable()) {
          vh->RemoveFollower(v.followers(j).follower_id());
          VLOG("removed follower from %s: %d", vh->id(), v.followers(j).follower_id());
        } else {
          state_->contact_manager()->MaybeQueueUser(v.followers(j).follower_id(), updates);
          vh->AddFollower(v.followers(j).follower_id());
          VLOG("added follower to %s: %d", vh->id(), v.followers(j).follower_id());
        }
      }
    }

    for (int j = 0; j < v.activities_size(); ++j) {
      ActivityHandle ah = ProcessActivity(v.activities(j), updates);
      // If the activity has already been viewed, set viewed timestamp.
      ah->SaveAndUnlock(updates);
      // Add a follower if the activity is meant to indicate a merged user account.
      if (vh.get() && ah->has_merge_accounts()) {
        vh->AddFollower(ah->merge_accounts().target_user_id());
      }
      VLOG("added activity %s to %s", ah->activity_id(), vh->id());
    }

    for (int j = 0; j < v.episodes_size(); ++j) {
      EpisodeHandle eh = ProcessEpisode(v.episodes(j), true, updates);
      eh->SaveAndUnlock(updates);
      VLOG("added episode %s to %s", eh->id(), vh->id());
    }

    for (int j = 0; j < v.comments_size(); ++j) {
      CommentHandle ch = ProcessComment(v.comments(j), updates);
      ch->SaveAndUnlock(updates);
      VLOG("added comment %s to %s", ch->comment_id(), vh->id());
    }

    if (vh.get()) {
      vh->SaveAndUnlock(updates);
    }
  }
}

void NetworkQueue::WaitForDownload(
    int64_t photo_id, PhotoType desired_type, Callback<void ()> done) {
  MutexLock l(&download_callback_mu_);
  DownloadCallbackSet*& callbacks = download_callback_map_[photo_id];
  if (!callbacks) {
    callbacks = new DownloadCallbackSet;
  }
  int* callback_id = new int;
  *callback_id = callbacks->Add(
      [this, photo_id, desired_type, done, callback_id](int type) {
        if ((type & desired_type) == 0) {
          return;
        }
        // Mutex lock is held by caller.
        download_callback_mu_.AssertHeld();
        download_callback_map_[photo_id]->Remove(*callback_id);
        delete callback_id;
        done();
      });
}

void NetworkQueue::EnsureInitLocked() {
  if (!next_sequence_) {
    next_sequence_ = state_->db()->Get<int64_t>(kNextSequenceKey, 1);
  }
}

NetworkQueue::NetworkStatsMap NetworkQueue::stats() {
  MutexLock l(&mu_);
  EnsureStatsInitLocked();
  return *stats_;
}

void NetworkQueue::UpdateStatsLocked(
    int priority, const ServerOperation& op, bool addition) {
  EnsureStatsInitLocked();
  if (addition) {
    (*stats_)[priority] += AdjustedCountForPriority(priority);
    for (int i = 0; i < op.stats_size(); ++i) {
      (*stats_)[op.stats(i)] += AdjustedCountForPriority(op.stats(i));
    }
  } else {
    (*stats_)[priority] -= AdjustedCountForPriority(priority);
    if ((*stats_)[priority] <= 0) {
      stats_->erase(priority);
    }
    for (int i = 0; i < op.stats_size(); ++i) {
      const int p = op.stats(i);
      (*stats_)[p] -= AdjustedCountForPriority(p);
      if ((*stats_)[p] <= 0) {
        stats_->erase(p);
      }
    }
  }
}

void NetworkQueue::EnsureStatsInitLocked() {
  if (stats_.get()) {
    return;
  }

  WallTimer timer;
  stats_.reset(new NetworkStatsMap);

  // Regenerate stats from scratch.
  for (DB::PrefixIterator iter(state_->db(), kNetworkQueueKeyPrefix);
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const Slice value = iter.value();
    int priority;
    int64_t sequence;
    if (DecodeNetworkQueueKey(key, &priority, &sequence)) {
      (*stats_)[priority] += AdjustedCountForPriority(priority);
    }
    ServerOperation op;
    if (op.ParseFromArray(value.data(), value.size())) {
      for (int i = 0; i < op.stats_size(); ++i) {
        (*stats_)[op.stats(i)] += AdjustedCountForPriority(op.stats(i));
      }
    }
  }

  LOG("network queue stats: %s, %.03f ms", *stats_, timer.Milliseconds());
}

ActivityHandle NetworkQueue::ProcessActivity(
    const ActivityMetadata& m, const DBHandle& updates) {
  ActivityHandle h = state_->activity_table()->LoadActivity(
      m.activity_id().server_id(), updates);
  const char* action = "update";
  if (!h.get()) {
    h = state_->activity_table()->NewActivity(updates);
    action = "new";
  }

  if (m.has_user_id()) {
    // Fetch user information if user id is unknown.
    state_->contact_manager()->MaybeQueueUser(m.user_id(), updates);
  }

  h->Lock();
  h->MergeFrom(m);

  // Canonicalize viewpoint id to get a local id used to build mapping
  // from viewpoint-id to list of activities.
  state_->viewpoint_table()->CanonicalizeViewpointId(
      h->mutable_viewpoint_id(), updates);

  h->Save(updates);
  VLOG("photo: %s activity: %s", action, h->activity_id());
  return h;
}

CommentHandle NetworkQueue::ProcessComment(
    const CommentMetadata& m, const DBHandle& updates) {
  CommentHandle h = state_->comment_table()->LoadComment(
      m.comment_id().server_id(), updates);
  const char* action = "update";
  if (!h.get()) {
    h = state_->comment_table()->NewComment(updates);
    action = "new";
  }

  h->Lock();
  h->MergeFrom(m);

  // Canonicalize viewpoint id to get a local id.
  state_->viewpoint_table()->CanonicalizeViewpointId(
      h->mutable_viewpoint_id(), updates);

  h->Save(updates);

  VLOG("photo: %s comment: %s", action, h->comment_id());
  return h;
}

EpisodeHandle NetworkQueue::ProcessEpisode(
    const EpisodeMetadata& m, bool recurse, const DBHandle& updates) {
  EpisodeHandle h = state_->episode_table()->LoadEpisode(m.id(), updates);
  const char* action = "update";
  if (!h.get()) {
    h = state_->episode_table()->NewEpisode(updates);
    action = "new";
  }
  h->Lock();
  h->MergeFrom(m);
  // Every episode loaded from server gets upload bit set to 0.
  h->clear_upload_episode();

  // Canonicalize viewpoint id to get a local id.
  state_->viewpoint_table()->CanonicalizeViewpointId(
      h->mutable_viewpoint_id(), updates);

  h->Save(updates);
  VLOG("photo: %s episode: %s", action, h->id());
  if (recurse) {
    // Synthesize an EpisodeSelection for this episode.
    EpisodeSelection s;
    s.set_episode_id(m.id().server_id());
    s.set_get_photos(true);
    state_->episode_table()->Invalidate(s, updates);
  }
  return h;
}

PhotoHandle NetworkQueue::ProcessPhoto(
    const PhotoUpdate& u, EpisodeHandle* old_eh, const DBHandle& updates) {
  const PhotoMetadata& m = u.metadata();
  return ProcessPhoto(state_->photo_table()->LoadPhoto(m.id(), updates),
                      u, old_eh, updates);
}

// ProcessPhoto is called with server-supplied information about a photo in
// 'u'. This happens after upload_episode and query_episode. 'h' is the
// corresponding local photo, if any (for upload_episode there is always a
// local photo (but the local photo may not have a server_id yet), and for
// query_episodes the local photo is looked up by server_id). Processing a
// photo means merging the data in 'u' into a local photo (either 'h' or a
// newly-created photo).
PhotoHandle NetworkQueue::ProcessPhoto(
    PhotoHandle h, const PhotoUpdate& u,
    EpisodeHandle* old_eh, const DBHandle& updates) {
  const PhotoMetadata& m = u.metadata();
  const char* action = "update";

  if (!h.get()) {
    // The server sent us a photo that we couldn't look up by server_id.  Try
    // to look it up by asset_key to see if we have a match.
    for (int i = 0; !h.get() && i < m.asset_fingerprints_size(); i++) {
      h = state_->photo_table()->LoadAssetPhoto(EncodeAssetKey("", m.asset_fingerprints(i)), updates);
      if (!h.get()) {
        continue;
      }
      // Found photo with matching asset key.
      if (!state_->photo_table()->IsAssetPhotoEqual(*h, m)) {
        // This is a pre-fingerprint photo that matched on url, but doesn't appear to actually be the same.
        h.reset(NULL);
        continue;
      } else {
        // There have been issues with duplicate photos created for
        // the same asset key. Check here whether the photo we
        // already have on disk has the same server id as the one
        // which we're trying to add. If they're not the same, we
        // have a duplicate.

        // NOTE(peter): There is a usage scenario which can cause this to
        // occur. Existing viewfinder user has shared photo A. User gets new
        // phone and re-installs viewfinder. After login, but before photo A is
        // downloaded from the server, user decides to share photo A again. The
        // second share will cause a server_id to be assigned to the photo
        // which will prohibit the photo from being matched against the one on
        // the server. This is a deemed to be too rare a scenario to fix and
        // that effort should instead be put into adding functionality to
        // quickly find and delete duplicates.
        if (h->id().has_server_id() && m.id().has_server_id() &&
            h->id().server_id() != m.id().server_id()) {
          LOG("duplicate photo with same asset key: %s != %s", *h, m);
          h.reset(NULL);
          continue;
        }
      }
    }
  }

  if (!h.get()) {
    // We tried all the asset keys and still didn't find a match, so make a new photo.
    h = state_->photo_table()->NewPhoto(updates);
    action = "new";
  }

  h->Lock();

  // We still fetch images for "label_hidden" images because they're
  // hidden only in the feed, but not from the conversation to which
  // they belong.
  if (!m.label_unshared() && !m.label_removed()) {
    if (!h->HasAssetUrl()) {
      // No asset url which means the photo is not in the assets library. Check
      // to see if we already have the various thumbnail/medium/full/original
      // images.
      if (!state_->photo_storage()->MaybeLinkServerId(
              PhotoThumbnailFilename(h->id()), m.id().server_id(),
              m.images().tn().md5(), updates)) {
        if (u.has_tn_get_url()) {
          h->SetURL("tn_get", u.tn_get_url(), updates);
        }
        h->set_download_thumbnail(true);
      }
      if (!state_->photo_storage()->MaybeLinkServerId(
              PhotoMediumFilename(h->id()), m.id().server_id(),
              m.images().med().md5(), updates)) {
        if (u.has_med_get_url()) {
          h->SetURL("med_get", u.med_get_url(), updates);
        }
        h->set_download_medium(true);
      }
      if (!state_->photo_storage()->MaybeLinkServerId(
              PhotoFullFilename(h->id()), m.id().server_id(),
              m.images().full().md5(), updates)) {
        if (u.has_full_get_url()) {
          h->SetURL("full_get", u.full_get_url(), updates);
        }
        h->set_download_full(true);
      }
      if (!state_->photo_storage()->MaybeLinkServerId(
              PhotoOriginalFilename(h->id()), m.id().server_id(),
              m.images().orig().md5(), updates)) {
        if (u.has_orig_get_url()) {
          h->SetURL("orig_get", u.orig_get_url(), updates);
        }
        // By default, we don't fetch the original image. It is fetched
        // on occasions where it is necessary (e.g., if a resolution is
        // required for display which exceeds full-resolution).
      }
    } else {
      // The photo is stored in the asset library. Look for matching asset
      // symlinks which indicate the photo has already been uploaded to the
      // server. (under any of the possibly-multiple asset urls)
      for (int i = 0; i < h->asset_keys_size(); i++) {
        if (h->upload_thumbnail() &&
            state_->photo_storage()->HaveAssetSymlink(
                PhotoThumbnailFilename(h->id()), m.id().server_id(),
                h->asset_keys(i))) {
          h->clear_upload_thumbnail();
        }
        if (h->upload_medium() &&
            state_->photo_storage()->HaveAssetSymlink(
                PhotoMediumFilename(h->id()), m.id().server_id(),
                h->asset_keys(i))) {
          h->clear_upload_medium();
        }
        if (h->upload_full() &&
            state_->photo_storage()->HaveAssetSymlink(
                PhotoFullFilename(h->id()), m.id().server_id(),
                h->asset_keys(i))) {
          h->clear_upload_full();
        }
        if (h->upload_original() &&
            state_->photo_storage()->HaveAssetSymlink(
                PhotoOriginalFilename(h->id()), m.id().server_id(),
                h->asset_keys(i))) {
          h->clear_upload_original();
        }
      }
    }

    if (h->upload_thumbnail() && u.has_tn_put_url()) {
      h->SetURL("tn_put", u.tn_put_url(), updates);
    }
    if (h->upload_medium() && u.has_med_put_url()) {
      h->SetURL("med_put", u.med_put_url(), updates);
    }
    if (h->upload_full() && u.has_full_put_url()) {
      h->SetURL("full_put", u.full_put_url(), updates);
    }
    if (h->upload_original() && u.has_orig_put_url()) {
      h->SetURL("orig_put", u.orig_put_url(), updates);
    }
  }

  // If the existing photo has a location & placemark and has been added to the
  // placemark histogram, we need to remove it in case this update has modified
  // location/placemark. This handles the following cases:
  //  - No change: restored to histogram on PhotoTable_Photo::Save()
  //  - Modified placemark: new info added to histogram on PhotoTable_Photo::Save()
  //  - Placemark/location deleted: removal from histogram is permanent
  if (h->has_location() && h->has_placemark() && h->placemark_histogram()) {
    h->clear_placemark_histogram();
    state_->placemark_histogram()->RemovePlacemark(
        h->placemark(), h->location(), updates);
  }

  if (old_eh && m.episode_id().has_server_id() &&
      h->episode_id().server_id() != m.episode_id().server_id()) {
    EpisodeHandle eh = state_->episode_table()->LoadEpisode(h->episode_id(), updates);
    if (eh.get() && eh->id().server_id() != m.episode_id().server_id()) {
      // The server is changing the canonical episode for the photo. Most
      // likely this is because the client state was reset and we've downloaded
      // a photo that already existed in the asset library. We return to the
      // caller the old episode handle so that it can remove the photo from the
      // old episode. We can't remove the photo from the episode here as doing
      // so could leave the photo unreferenced by an episode causing its images
      // and assets to be deleted.
      *old_eh = eh;
      h->clear_episode_id();
    }
  }

  h->clear_upload_metadata();
  h->clear_update_metadata();
  h->clear_label_hidden();
  h->clear_label_removed();
  h->clear_label_unshared();
  h->clear_error_upload_metadata();
  h->clear_error_timestamp();

  // Construct a new PhotoMetadata that clears any field that should not be
  // merged directly.
  PhotoMetadata sanitized_metadata(m);
  sanitized_metadata.clear_asset_keys();
  sanitized_metadata.clear_asset_fingerprints();
  h->MergeFrom(sanitized_metadata);

  DCHECK_EQ(m.asset_keys_size(), 0);
  // If the server gave us any asset fingerprints, copy them to the local photo.
  for (int i = 0; i < m.asset_fingerprints_size(); i++) {
    h->AddAssetFingerprint(m.asset_fingerprints(i), true);
  }

  LOG("photo: %s photo: %s (%s): %supload%s%s%s%s download%s%s%s%s",
       action, h->id(), h->episode_id(),
       h->update_metadata() ? "update:metadata " : "",
       h->upload_thumbnail() ? ":thumbnail" : "",
       h->upload_medium() ? ":medium" : "",
       h->upload_full() ? ":full" : "",
       h->upload_original() ? ":original" : "",
       h->download_thumbnail() ? ":thumbnail" : "",
       h->download_medium() ? ":medium" : "",
       h->download_full() ? ":full" : "",
       h->download_original() ? ":original" : "");

  h->Save(updates);
  return h;
}

ViewpointHandle NetworkQueue::ProcessViewpoint(
    const ViewpointMetadata& m, bool recurse, const DBHandle& updates) {
  ViewpointHandle h = state_->viewpoint_table()->LoadViewpoint(
      m.id().server_id(), updates);
  const char* action = "update";
  if (!h.get()) {
    h = state_->viewpoint_table()->NewViewpoint(updates);
    action = "new";
  }
  h->Lock();
  h->MergeFrom(m);
  h->Save(updates);
  VLOG("photo: %s viewpoint: %s", action, h->id());

  if (recurse) {
    // Synthesize a ViewpointSelection for this viewpoint.
    ViewpointSelection s;
    s.set_viewpoint_id(m.id().server_id());
    s.set_get_activities(true);
    s.set_get_episodes(true);
    s.set_get_followers(true);
    s.set_get_comments(true);
    state_->viewpoint_table()->Invalidate(s, updates);
  }
  return h;
}

void NetworkQueue::MaybeQueueNetwork(int priority) {
  MutexLock l(&queue_mu_);
  if (!state_->is_registered()) {
    // The user is not logged in. Clear any queued item(s).
    queued_download_photo_.reset(NULL);
    queued_remove_photos_.reset(NULL);
    queued_update_viewpoint_.reset(NULL);
    queued_upload_episode_.reset(NULL);
    queued_upload_photo_.reset(NULL);
    queued_upload_activity_.reset(NULL);
    return;
  }
  if (queued_download_photo_.get() ||
      queued_remove_photos_.get() ||
      queued_update_viewpoint_.get() ||
      queued_upload_episode_.get() ||
      queued_upload_photo_.get() ||
      queued_upload_activity_.get()) {
    // An item is already queued, do not change it because the network request
    // might currently be in progress.
    return;
  }
  if (queue_in_progress_) {
    if (queue_start_time_ > 0) {
      VLOG("photo: queue still in progress: %.03f ms",
           1000 * (WallTime_Now() - queue_start_time_));
    }
    return;
  }

  // The network queue schedules in what order to
  // upload/download/remove/share/etc photos. The various MaybeQueue* methods
  // take a ServerOperation and try and create a queued_* operation. When the
  // queued operation is completed by the NetworkManager, the corresponding
  // CommitQueued* method is called. Note that the CommitQueued* methods do not
  // modify the queue. Instead, the code MaybeQueue* checks to see if the
  // specified work has already been done. For example, if
  // MaybeQueueUploadPhoto checks that some portion of the photo still needs to
  // be uploaded. If the photo has been completely uploaded, that queue entry
  // is moved and the loop below advances to the next one.
  //
  // This setup provides both robustness and the ability to queue the same
  // operation at different priorities. For example, downloading of a photo
  // might initially be queued at PRIORITY_DOWNLOAD_PHOTO. But if the user
  // attempts to view that photo before it has been downloaded, another queue
  // entry with priority PRIORITY_UI_THUMBNAIL will be created.

  DBHandle updates = state_->NewDBTransaction();
  for (ScopedPtr<NetworkQueue::Iterator> iter(NewIterator());
       !iter->done() && iter->priority() <= priority;
       iter->Next()) {
    while (!ShouldProcessPriority(iter->priority())) {
      iter->SkipPriority();
      if (iter->done()) {
        break;
      }
    }
    if (iter->done()) {
      break;
    }

    const ServerOperation& op = iter->op();
    if (op.has_update_viewpoint()) {
      if (MaybeQueueUpdateViewpoint(op, updates)) {
        break;
      }
    } else if (op.has_upload_activity()) {
      if (MaybeQueueUploadActivity(op, iter->priority(), updates)) {
        break;
      }
      // TODO(pmattis): Quarantine the activity.
    } else if (op.has_update_photo()) {
      if (MaybeQueueUpdatePhoto(op, iter->priority(), updates)) {
        break;
      }
      // TODO(pmattis): Quarantine the photo.
    } else if (op.has_remove_photos()) {
      if (MaybeQueueRemovePhotos(
              op, iter->priority(), iter->sequence(), updates)) {
        break;
      }
    }
    // If we fall through to here, we were unable to queue the server
    // operation. Remove it from the queue.
    VLOG("dequeuing %d,%d (unable to process)",
         iter->priority(), iter->sequence());
    Remove(iter->priority(), iter->sequence(), op, updates);
  }
  updates->Commit();
}

bool NetworkQueue::MaybeQueueUpdateViewpoint(
    const ServerOperation& op, const DBHandle& updates) {
  ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
      op.update_viewpoint(), updates);
  if (!vh.get() || vh->label_error()) {
    return false;
  }
  if (!vh->update_metadata() &&
      !vh->update_follower_metadata() &&
      !vh->update_remove() &&
      !vh->update_viewed_seq()) {
    return false;
  }

  ScopedPtr<UpdateViewpoint> u(new UpdateViewpoint);
  u->viewpoint = vh;
  u->headers.CopyFrom(op.headers());

  queued_update_viewpoint_.reset(u.release());
  return true;
}

bool NetworkQueue::MaybeQueueUploadActivity(
    const ServerOperation& op, int priority, const DBHandle& updates) {
  ActivityHandle ah = state_->activity_table()->LoadActivity(
      op.upload_activity(), updates);
  if (!ah.get() || ah->label_error()) {
    // Unable to find the queued activity or the activity is quarantined.
    return false;
  }
  if (!ah->upload_activity()) {
    // The queued activity no longer needs to be uploaded, presumably because
    // it has already been uploaded.
    return false;
  }
  if (!ah->has_share_new() && !ah->has_share_existing() &&
      !ah->has_add_followers() && !ah->has_post_comment() &&
      !ah->has_remove_followers() && !ah->has_save_photos() &&
      !ah->has_unshare()) {
    // Huh, how did this activity get queued?
    return false;
  }
  if (ah->has_share_new() &&
      ah->share_new().contacts_size() == 0) {
    // A share_new with 0 contacts is invalid and the server will reject
    // it. Mark the activity as provisional again so that the user can fix up
    // the problem. Note that ConversationLayoutController no longer allows the
    // creation of share_new activities with 0 contacts.
    ah->Lock();
    ah->set_provisional(true);
    ah->SaveAndUnlock(updates);
    return false;
  }

  ScopedPtr<UploadActivity> u(new UploadActivity);
  if (ah->has_viewpoint_id()) {
    u->viewpoint = state_->viewpoint_table()->LoadViewpoint(ah->viewpoint_id(), updates);
    if (!u->viewpoint.get()) {
      // Unable to find the viewpoint to share to. This shouldn't happen.
      return false;
    }
  }
  u->headers.CopyFrom(op.headers());
  u->activity = ah;

  if (ah->has_share_new() || ah->has_share_existing() ||
      ah->has_save_photos() || ah->has_unshare()) {
    // Ensure that all of the photos in the share have been uploaded.
    const ShareEpisodes* episodes = ah->GetShareEpisodes();
    for (int i = 0; i < episodes->size(); ++i) {
      u->episodes.push_back(Episode());
      Episode* e = &u->episodes.back();
      const ActivityMetadata::Episode& episode = episodes->Get(i);

      e->episode = state_->episode_table()->LoadEpisode(episode.episode_id(), updates);
      if (!e->episode.get()) {
        // Unable to find episode. This shouldn't happen.
        u->episodes.pop_back();
        continue;
      }

      for (int j = 0; j < episode.photo_ids_size(); ++j) {
        PhotoHandle ph = state_->photo_table()->LoadPhoto(episode.photo_ids(j), updates);
        if (!ph.get() || ph->label_error()) {
          // Skip non-existent photos or photos with errors.
          continue;
        }
        if (ph->upload_metadata() || ph->upload_thumbnail() || ph->upload_full()) {
          if (MaybeQueueUploadPhoto(ph, priority, updates)) {
            return true;
          }
          // Skip photos that cannot be uploaded.
          continue;
        }
        e->photos.push_back(ph);
      }

      // NOTE(peter): We check for the existence of the parent episode and its
      // server id after we have ensured that all of the shared photos have
      // been uploaded. This ensures that the parent episode will have had a
      // server id assigned to it.
      e->parent = state_->episode_table()->LoadEpisode(e->episode->parent_id(), updates);
      if (!e->parent.get() || e->parent->id().server_id().empty()) {
        // Unable to find parent episode or parent episode has no id. This shouldn't happen.
        u->episodes.pop_back();
        continue;
      }

      if (e->photos.empty()) {
        u->episodes.pop_back();
      }
    }

    // If this is a share_new activity, add contacts. Also, reset the
    // cover photo to the first photo which has been successfully
    // uploaded and verified.
    if (ah->has_share_new()) {
      for (int i = 0; i < ah->share_new().contacts_size(); ++i) {
        u->contacts.push_back(ah->share_new().contacts(i));
      }
      if (!u->episodes.empty() && !u->episodes.front().photos.empty()) {
        u->viewpoint->Lock();
        u->viewpoint->mutable_cover_photo()->mutable_photo_id()->CopyFrom(
            u->episodes.front().photos[0]->id());
        u->viewpoint->mutable_cover_photo()->mutable_episode_id()->CopyFrom(
            u->episodes.front().episode->id());
        u->viewpoint->SaveAndUnlock(updates);
      }
    }
    if (u->contacts.empty() && u->episodes.empty()) {
      return false;
    }
  } else if (ah->has_add_followers()) {
    for (int i = 0; i < ah->add_followers().contacts_size(); ++i) {
      u->contacts.push_back(ah->add_followers().contacts(i));
    }
    if (u->contacts.empty()) {
      return false;
    }
  } else if (ah->has_post_comment()) {
    u->comment = state_->comment_table()->LoadComment(
        ah->post_comment().comment_id(), updates);
  } else if (ah->has_remove_followers()) {
    if (ah->remove_followers().user_ids_size() == 0) {
      return false;
    }
  }

  queued_upload_activity_.reset(u.release());
  return true;
}

bool NetworkQueue::MaybeQueueUpdatePhoto(
    const ServerOperation& op, int priority, const DBHandle& updates) {
  PhotoHandle ph = state_->photo_table()->LoadPhoto(op.update_photo(), updates);
  if (!ph.get() || ph->label_error()) {
    // This shouldn't be possible. We never remove photo metadata and
    // quarantined photos are removed from the queue.
    return false;
  }
  if (ph->download_thumbnail() || ph->download_full() || ph->download_original()) {
    if (MaybeQueueDownloadPhoto(ph, updates)) {
      return true;
    }
  }
  if (ph->update_metadata() || ph->upload_metadata() ||
      ph->upload_thumbnail() || ph->upload_medium() ||
      ph->upload_full() || ph->upload_original()) {
    if (MaybeQueueUploadPhoto(ph, priority, updates)) {
      return true;
    }
  }
  ph->Lock();
  ph->SaveAndUnlock(updates);
  return false;
}

bool NetworkQueue::MaybeQueueRemovePhotos(
    const ServerOperation& op, int priority,
    int64_t sequence, const DBHandle& updates) {
  const ServerOperation::RemovePhotos& r = op.remove_photos();
  ScopedPtr<RemovePhotos> rp(new RemovePhotos);
  rp->headers.CopyFrom(op.headers());
  rp->queue.set_priority(priority);
  rp->queue.set_sequence(sequence);

  for (int i = 0; i < r.episodes_size(); ++i) {
    rp->episodes.push_back(Episode());
    Episode* e = &rp->episodes.back();
    const ActivityMetadata::Episode& episode = r.episodes(i);

    e->episode = state_->episode_table()->LoadEpisode(episode.episode_id(), updates);
    if (!e->episode.get()) {
      // Unable to find episode. This shouldn't happen.
      rp->episodes.pop_back();
      continue;
    }

    for (int j = 0; j < episode.photo_ids_size(); ++j) {
      PhotoHandle ph = state_->photo_table()->LoadPhoto(episode.photo_ids(j), updates);
      if (!ph.get() || ph->label_error()) {
        // Skip non-existent photos or photos with errors.
        continue;
      }
      if (ph->upload_metadata()) {
        // Skip photos that haven't been uploaded.
        continue;
      }
      e->photos.push_back(ph);
    }

    if (e->photos.empty()) {
      // No photos to remove.
      rp->episodes.pop_back();
    }
  }

  if (rp->episodes.empty()) {
    // Nothing to do. Too many errors?
    return false;
  }

  queued_remove_photos_.reset(rp.release());
  return true;
}

bool NetworkQueue::MaybeQueueDownloadPhoto(
    const PhotoHandle& ph, const DBHandle& updates) {
  ScopedPtr<DownloadPhoto> d(new DownloadPhoto);
  d->photo = ph;

  DCHECK(DirExists(photo_tmp_dir_)) << " " << photo_tmp_dir_ << " doesn't exist";

  if (d->photo->download_thumbnail()) {
    d->type = THUMBNAIL;
    d->path = JoinPath(photo_tmp_dir_, PhotoThumbnailFilename(d->photo->id()));
    d->url = d->photo->GetUnexpiredURL("tn_get", updates);
  } else if (d->photo->download_full()) {
    d->type = FULL;
    d->path = JoinPath(photo_tmp_dir_, PhotoThumbnailFilename(d->photo->id()));
    d->url = d->photo->GetUnexpiredURL("full_get", updates);
  } else if (d->photo->download_original()) {
    // We should never be trying to download the original more than once.
    DCHECK(!d->photo->error_download_original());
    d->type = ORIGINAL;
    d->path = JoinPath(photo_tmp_dir_, PhotoThumbnailFilename(d->photo->id()));
    d->url = d->photo->GetUnexpiredURL("orig_get", updates);
  } else {
    // Nothing left to do for this photo.
    return false;
  }

  VLOG("photo: %s: queueing download photo: %s", ph->id(), d->url);

  // NOTE(peter): We never download medium images. It is faster to download the
  // full size image and resize it.

  d->episode = state_->episode_table()->GetEpisodeForPhoto(ph, updates);
  if (!d->episode.get()) {
    // We were unable to find an episode the photo was part of.
    QuarantinePhoto(ph, "queue download: unable to find episode", updates);
    return false;
  }

  queued_download_photo_.reset(d.release());
  return true;
}

bool NetworkQueue::MaybeQueueUploadPhoto(
    const PhotoHandle& ph, int priority, const DBHandle& updates) {
  if (!ph->shared() && !state_->CloudStorageEnabled()) {
    // Cloud storage is disabled and the photo has not been shared. Stop
    // processing the queue.
    VLOG("photo: not queueing unshared photo (cloud storage disabled): %s", *ph);
    return false;
  }

  WallTimer timer;
  queue_start_time_ = WallTime_Now();

  if (ph->upload_metadata()) {
    // The photo metadata needs to be uploaded.
    if (!ph->episode_id().has_local_id()) {
      // The photo doesn't have an associated episode, upload isn't possible.
      QuarantinePhoto(ph, "upload: no episode id", updates);
      return false;
    }
    EpisodeHandle eh = state_->episode_table()->LoadEpisode(ph->episode_id(), updates);
    if (!eh.get()) {
      // Unable to find the photo's episode, upload isn't possible.
      QuarantinePhoto(ph, "upload: unable to load episode", updates);
      return false;
    }
    if (!MaybeQueueUploadEpisode(eh, updates)) {
      // If the episode couldn't be uploaded because it has no photos,
      // presumably this photo was removed. Quarantine the photo.
      QuarantinePhoto(ph, "upload: unable to upload episode", updates);
      return false;
    }
    return true;
  } else if (ph->update_metadata()) {
    return MaybeQueueUpdatePhotoMetadata(ph, updates);
  }

  EpisodeHandle eh = state_->episode_table()->LoadEpisode(ph->episode_id(), updates);
  if (!eh.get()) {
    // Unable to find the photo's episode, upload isn't possible.
    QuarantinePhoto(ph, "upload: unable to load episode", updates);
    return false;
  }
  if (!eh->id().has_server_id()) {
    // The episode doesn't have an associated server id, upload isn't possible.
    QuarantinePhoto(ph, "upload: no episode server id", updates);
    return false;
  }

  UploadPhoto* u = new UploadPhoto;
  u->episode = eh;
  u->photo = ph;
  int size = 0;

  if (ph->upload_thumbnail()) {
    u->type = THUMBNAIL;
    u->url = u->photo->GetUnexpiredURL("tn_put", updates);
    size = kThumbnailSize;
  } else if (ph->upload_full()) {
    u->type = FULL;
    u->url = u->photo->GetUnexpiredURL("full_put", updates);
    size = kFullSize;
  } else if (ph->upload_medium()) {
    u->type = MEDIUM;
    u->url = u->photo->GetUnexpiredURL("med_put", updates);
    size = kMediumSize;
  } else if (ph->upload_original()) {
    if (!state_->store_originals()) {
      // If cloud storage of originals is turned off, stop processing the queue
      // when we first see an operation for storing an original.
      delete u;
      if (priority != PRIORITY_UPLOAD_PHOTO_ORIGINAL) {
        // Enforce PRIORITY_UPLOAD_PHOTO_ORIGINAL at this point in order for
        // NetworkQueue::Empty() to work properly. Returning false will cause
        // the photo to be saved.
        return false;
      }
      return true;
    }
    u->type = ORIGINAL;
    u->url = u->photo->GetUnexpiredURL("orig_put", updates);
    size = kOriginalSize;
  } else {
    delete u;
    return false;
  }

  queue_in_progress_ = true;

  const string filename = PhotoFilename(u->photo->id(), size);
  u->path = JoinPath(state_->photo_dir(), filename);

  const Callback<void (bool)> done = [this, u, size, timer](bool success) {
    if (success) {
      if (size == kThumbnailSize) {
        u->md5 = u->photo->images().tn().md5();
      } else if (size == kMediumSize) {
        u->md5 = u->photo->images().med().md5();
      } else if (size == kFullSize) {
        u->md5 = u->photo->images().full().md5();
      } else if (size == kOriginalSize) {
        u->md5 = u->photo->images().orig().md5();
      } else {
        CHECK(false);
      }
      CHECK_EQ(32, u->md5.size());
    }

    MutexLock l(&queue_mu_);
    queued_upload_photo_.reset(u);
    queue_in_progress_ = false;
    queue_start_time_ = 0;

    // The queued upload is ready to go. Kick the NetworkManager.
    VLOG("photo: queued upload photo: %s (%s): %.03f ms",
         u->photo->id(), PhotoSizeSuffix(size), timer.Milliseconds());
    state_->async()->dispatch_main([this] {
        // Queuing the upload photo might have failed, but we want to go
        // through the same CommitQueueUploadPhoto() path and it is not
        // thread-safe to call CommitQueuedUploadPhoto() directly.
        state_->net_manager()->Dispatch();
      });
  };

  if (state_->photo_storage()->Exists(filename) &&
      u->photo->images().has_tn() &&
      u->photo->images().has_med() &&
      u->photo->images().has_full() &&
      u->photo->images().has_orig()) {
    state_->async()->dispatch_low_priority([done] {
        done(true);
      });
  } else {
    u->photo->clear_images();
    state_->LoadViewfinderImages(u->photo->id().local_id(), u->photo->db(), done);
  }
  return true;
}

bool NetworkQueue::MaybeQueueUpdatePhotoMetadata(
    const PhotoHandle& ph, const DBHandle& updates) {
  if (!ph->update_metadata()) {
    return false;
  }

  ScopedPtr<UpdatePhoto> u(new UpdatePhoto);
  u->headers.set_op_id(state_->NewLocalOperationId());
  u->headers.set_op_timestamp(WallTime_Now());
  u->photo = ph;

  queued_update_photo_.reset(u.release());
  return true;
}

bool NetworkQueue::MaybeQueueUploadEpisode(
    const EpisodeHandle& eh, const DBHandle& updates) {
  // NOTE: be careful if adding another "return false" case to this
  // code, as MaybeQueueUploadPhoto will quarantine the photo.
  queue_start_time_ = WallTime_Now();

  ScopedPtr<UploadEpisode> u(new UploadEpisode);
  u->headers.set_op_id(state_->NewLocalOperationId());
  u->headers.set_op_timestamp(WallTime_Now());
  u->episode = eh;

  vector<int64_t> photo_ids;
  u->episode->ListPhotos(&photo_ids);
  for (int i = 0; i < photo_ids.size(); ++i) {
    PhotoHandle ph = state_->photo_table()->LoadPhoto(photo_ids[i], updates);
    if (!ph.get()) {
      continue;
    }
    if (!ph->upload_metadata()) {
      continue;
    }
    u->photos.push_back(ph);
    if (u->photos.size() >= kMaxPhotosPerUpload) {
      break;
    }
  }

  if (u->photos.empty()) {
    // Nothing left to do for this episode.
    return false;
  }

  if (!u->episode->id().has_server_id()) {
    // The episode was created before we knew our device id.
    u->episode->Lock();
    CHECK(u->episode->MaybeSetServerId());
    u->episode->SaveAndUnlock(updates);
  }

  queue_in_progress_ = true;
  MaybeLoadImages(u.release(), 0);
  return true;
}

void NetworkQueue::MaybeReverseGeocode(UploadEpisode* u, int index) {
  for (; index < u->photos.size(); ++index) {
    const PhotoHandle& ph = u->photos[index];
    if (state_->photo_table()->ReverseGeocode(
            ph->id().local_id(), [this, u, index](bool) {
              MaybeReverseGeocode(u, index + 1);
            })) {
      return;
    }
  }

  // Note that we intentionally do not call dispatch_main() here as we want the
  // stack to unwind and locks to be released before grabbing queue_mu_.
  state_->async()->dispatch_main_async([this, u] {
      {
        MutexLock l(&queue_mu_);

        // All of the photos could have been removed (and presumably quarantined)
        // during the upload queueing process.
        const int64_t device_id = state_->device_id();
        if (device_id && !u->photos.empty()) {
          DBHandle updates = state_->NewDBTransaction();
          for (int i = 0; i < u->photos.size(); ++i) {
            const PhotoHandle& ph = u->photos[i];
            CHECK(ph->images().tn().has_md5());
            CHECK(ph->images().med().has_md5());
            CHECK(ph->images().full().has_md5());
            CHECK(ph->images().orig().has_md5());
            if (!ph->id().has_server_id()) {
              // The photo was created before we knew our device id.
              ph->Lock();
              CHECK(ph->MaybeSetServerId());
              ph->SaveAndUnlock(updates);
            }
          }
          updates->Commit();

          // The queued upload is ready to go.
          const EpisodeHandle& eh = u->episode;
          VLOG("photo: queued upload episode: %s: %.03f ms",
               eh->id(), 1000 * (WallTime_Now() - queue_start_time_));
          queued_upload_episode_.reset(u);
        } else {
          delete u;
        }

        queue_in_progress_ = false;
        queue_start_time_ = 0;
      }

      // Kick the NetworkManager. Even if no upload was queued, this will run the
      // dispatch loop and cause another upload queue to take place.
      state_->net_manager()->Dispatch();
    });
}

void NetworkQueue::MaybeLoadImages(UploadEpisode* u, int index) {
  for (; index < u->photos.size(); ++index) {
    PhotoHandle ph = u->photos[index];
    // Force the image data to be recomputed from scratch.
    ph->clear_images();

    const Callback<void (bool)> done = [this, ph, u, index](bool success) {
      if (success) {
        // In the process of loading the photo data the photo might have been
        // moved to a different episode. Don't upload it with the current
        // episode if that occurred.
        success = (ph->episode_id().local_id() == u->episode->id().local_id());
      }
      int next_index = index + 1;
      if (!success) {
        // Remove the photo from the UploadEpisode.
        u->photos.erase(u->photos.begin() + index);
        --next_index;
      }
      MaybeLoadImages(u, next_index);
    };

    state_->LoadViewfinderImages(ph->id().local_id(), ph->db(), done);
    return;
  }

  dispatch_main([this, u] {
      MaybeReverseGeocode(u, 0);
    });
}

void NetworkQueue::QuarantinePhoto(PhotoHandle p, const string& reason) {
  DBHandle updates = state_->NewDBTransaction();
  QuarantinePhoto(p, reason, updates);
  updates->Commit();
}

void NetworkQueue::QuarantinePhoto(
    PhotoHandle p, const string& reason, const DBHandle& updates) {
  p->Lock();
  p->Quarantine(reason, updates);
  p->SaveAndUnlock(updates);
}

void NetworkQueue::UpdateViewpointError(ViewpointHandle vh) {
  LOG("photo: quarantining viewpoint: %s", vh->id());
  DBHandle updates = state_->NewDBTransaction();
  vh->Lock();
  vh->set_label_error(true);
  vh->SaveAndUnlock(updates);
  updates->Commit();
}

void NetworkQueue::UpdatePhotoError(PhotoHandle p) {
  p->Lock();
  if (p->error_update_metadata()) {
    // We had previously tried to upload this photo and encountered an
    // error. Quarantine the photo.
    p->Unlock();
    QuarantinePhoto(p, "update: metadata");
    return;
  }
  p->set_error_update_metadata(true);
  DBHandle updates = state_->NewDBTransaction();
  p->SaveAndUnlock(updates);
  updates->Commit();
}

void NetworkQueue::UploadPhotoError(PhotoHandle p, int types) {
  p->Lock();
  if (types & THUMBNAIL) {
    if (p->error_upload_thumbnail()) {
      // We had previously tried to upload this photo and encountered an
      // error. Quarantine the photo.
      p->Unlock();
      QuarantinePhoto(p, "upload: thumbnail");
      return;
    }
    p->set_error_upload_thumbnail(true);
  }
  if (types & MEDIUM) {
    if (p->error_upload_medium()) {
      // We had previously tried to upload this photo and encountered an
      // error. Quarantine the photo.
      p->Unlock();
      QuarantinePhoto(p, "upload: medium");
      return;
    }
    p->set_error_upload_medium(true);
  }
  if (types & FULL) {
    if (p->error_upload_full()) {
      // We had previously tried to upload this photo and encountered an
      // error. Quarantine the photo.
      p->Unlock();
      QuarantinePhoto(p, "upload: full");
      return;
    }
    p->set_error_upload_full(true);
  }
  if (types & ORIGINAL) {
    if (p->error_upload_original()) {
      // We had previously tried to upload this photo and encountered an
      // error. We do not quarantine if we're unable to upload the original.
      p->Unlock();
      return;
    }
    // Failure to upload the original is expected if upload_originals is turned
    // on well after the original photo was added to the library. We do not
    // quarantine such photos, but simply clear the upload_original bit.
    p->clear_upload_original();
    p->set_error_upload_original(true);
    DBHandle updates = state_->NewDBTransaction();
    p->SaveAndUnlock(updates);
    updates->Commit();
    return;
  }

  // Reset the photo state machine. The error_upload_* bits will be cleared
  // when the photo is uploaded.
  p->set_upload_thumbnail(true);
  p->set_upload_medium(true);
  p->set_upload_full(true);
  p->set_upload_original(true);

  {
    // Re-add the photo to an episode.
    DBHandle updates = state_->NewDBTransaction();
    EpisodeHandle e = state_->episode_table()->LoadEpisode(p->episode_id(), updates);
    state_->episode_table()->AddPhotoToEpisode(p, updates);
    if (e.get() && e->id().local_id() != p->episode_id().local_id()) {
      // The photo's episode changed. Remove it from the old episode.
      e->Lock();
      e->RemovePhoto(p->id().local_id());
      e->SaveAndUnlock(updates);
    }
    updates->Commit();
  }

  DBHandle updates = state_->NewDBTransaction();
  p->SaveAndUnlock(updates);
  updates->Commit();
}

void NetworkQueue::DownloadPhotoError(PhotoHandle p, int types) {
  if (!p->id().has_server_id()) {
    // How on earth were we trying to download a photo without a corresponding
    // server id.
    QuarantinePhoto(p, "download: no server id");
    return;
  }
  if (!p->has_episode_id()) {
    // A photo without an episode. Quarantine.
    QuarantinePhoto(p, "download: no episode id");
    return;
  }

  p->Lock();

  // Reset the photo state machine. Download the metadata and images again. The
  // error_download_* bits will be cleared when the image is successfully
  // downloaded.
  if (types & THUMBNAIL) {
    if (p->error_download_thumbnail()) {
      // We had previously tried to download this photo and encountered an
      // error. Quarantine the photo.
      p->Unlock();
      QuarantinePhoto(p, "download: thumbnail");
      return;
    }
    p->set_error_download_thumbnail(true);
  }
  if (types & MEDIUM) {
    if (p->error_download_medium()) {
      // We had previously tried to download this photo and encountered an
      // error. Quarantine the photo.
      p->Unlock();
      QuarantinePhoto(p, "download: medium");
      return;
    }
    p->set_error_download_medium(true);
  }
  if (types & FULL) {
    if (p->error_download_full()) {
      // We had previously tried to download this photo and encountered an
      // error. Quarantine the photo.
      p->Unlock();
      QuarantinePhoto(p, "download: full");
      return;
    }
    p->set_error_download_full(true);
  }
  if (types & ORIGINAL) {
    // Never quarantine a photo because the original isn't available.
    DCHECK(!p->error_download_original());
    // Set the download error and unset the intention to download it.
    // The assumption is that the photo was never uplaoded and isn't
    // ever going to be available. This isn't necessarily an error.
    p->set_error_download_original(true);
    p->set_download_original(false);
  }

  DBHandle updates = state_->NewDBTransaction();

  // If thumbnail or full resolution is missing, synthesize an
  // EpisodeSelection for this episode in order to download the photo
  // metadata again.
  if (p->error_download_thumbnail() || p->error_download_full()) {
    EpisodeHandle found_episode =
        state_->episode_table()->GetEpisodeForPhoto(p, updates);

    if (!found_episode.get()) {
      // Couldn't find the photo's episode. Quarantine.
      p->Unlock();
      QuarantinePhoto(p, "download: unable to find episode");
      return;
    }

    EpisodeSelection s;
    s.set_episode_id(found_episode->id().server_id());
    s.set_get_photos(true);
    state_->episode_table()->Invalidate(s, updates);
  }

  p->SaveAndUnlock(updates);
  updates->Commit();
}

void NetworkQueue::UploadActivityError(ActivityHandle ah) {
  LOG("photo: quarantining activity: %s", ah->activity_id());
  DBHandle updates = state_->NewDBTransaction();
  ah->Lock();
  ah->set_label_error(true);
  ah->SaveAndUnlock(updates);
  updates->Commit();
}

void NetworkQueue::NotifyDownload(int64_t photo_id, int types) {
  MutexLock l(&download_callback_mu_);
  DownloadCallbackSet* callbacks =
      FindOrNull(&download_callback_map_, photo_id);
  if (!callbacks) {
    return;
  }
  callbacks->Run(types);
  if (callbacks->empty()) {
    download_callback_map_.erase(photo_id);
    delete callbacks;
  }
}

// local variables:
// mode: c++
// end:
