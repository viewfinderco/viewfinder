// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <unordered_set>
#import "ActivityTable.h"
#import "AppState.h"
#import "AsyncState.h"
#import "CommentTable.h"
#import "ContactManager.h"
#import "DayTable.h"
#import "EpisodeTable.h"
#import "FullTextIndex.h"
#import "IdentityManager.h"
#import "NetworkManager.h"
#import "NetworkQueue.h"
#import "PeopleRank.h"
#import "PhotoTable.h"
#import "PlacemarkHistogram.h"
#import "ServerId.h"
#import "StringUtils.h"
#import "ViewpointTable.h"

const string ViewpointTable::kViewpointTokenPrefix = "_vp";

namespace {

const int kViewpointFSCKVersion = 2;

const WallTime kClawbackGracePeriod = 7 * 24 * 60 * 60;  // 1 week

const string kFollowerViewpointKeyPrefix = DBFormat::follower_viewpoint_key("");
const string kViewpointFollowerKeyPrefix = DBFormat::viewpoint_follower_key("");
const string kViewpointGCKeyPrefix = DBFormat::viewpoint_gc_key("");
const string kViewpointSelectionKeyPrefix = DBFormat::viewpoint_selection_key("");
const string kViewpointScrollOffsetKeyPrefix = DBFormat::viewpoint_scroll_offset_key("");
const string kHasUserCreatedViewpointKey = DBFormat::metadata_key("has_user_created_viewpoint");
const string kViewpointIndexName = "vp";
const string kViewpointGCCommitTrigger = "ViewpontTableGC";

const DBRegisterKeyIntrospect kFollowerViewpointKeyIntrospect(
    kFollowerViewpointKeyPrefix, [](Slice key) {
      int64_t follower_id;
      int64_t viewpoint_id;
      if (!DecodeFollowerViewpointKey(key, &follower_id, &viewpoint_id)) {
        return string();
      }
      return string(Format("%d/%d", follower_id, viewpoint_id));
    }, NULL);

const DBRegisterKeyIntrospect kViewpointKeyIntrospect(
    DBFormat::viewpoint_key(), NULL, [](Slice value) {
      return DBIntrospect::FormatProto<ViewpointMetadata>(value);
    });

const DBRegisterKeyIntrospect kViewpointServerKeyIntrospect(
    DBFormat::viewpoint_server_key(), NULL, [](Slice value) {
      return value.ToString();
    });

const DBRegisterKeyIntrospect kViewpointFollowerKeyIntrospect(
    kViewpointFollowerKeyPrefix, [](Slice key) {
      int64_t viewpoint_id;
      int64_t follower_id;
      if (!DecodeViewpointFollowerKey(key, &viewpoint_id, &follower_id)) {
        return string();
      }
      return string(Format("%d/%d", viewpoint_id, follower_id));
    }, NULL);

const DBRegisterKeyIntrospect kViewpointGCKeyIntrospect(
    kViewpointGCKeyPrefix, [](Slice key) {
      int64_t viewpoint_id;
      WallTime expiration;
      if (!DecodeViewpointGCKey(key, &viewpoint_id, &expiration)) {
        return string();
      }
      return string(Format("%d/%s", viewpoint_id, DBIntrospect::timestamp(expiration)));
    }, NULL);

const DBRegisterKeyIntrospect kViewpointSelectionKeyIntrospect(
    kViewpointSelectionKeyPrefix, NULL, [](Slice value) {
      return DBIntrospect::FormatProto<ViewpointSelection>(value);
    });

const DBRegisterKeyIntrospect kViewpointScrollOffsetKeyIntrospect(
    kViewpointScrollOffsetKeyPrefix,
    [](Slice key) {
      int64_t viewpoint_id;
      if (!DecodeViewpointScrollOffsetKey(key, &viewpoint_id)) {
        return string();
      }
      return string(Format("%d", viewpoint_id));
    },
    [](Slice value) {
      return value.ToString();
    });

// Creates a local activity as a placeholder for display. The metadata
// will eventually be replaced on a notification from the server after
// the client uploads the activity via a share_new, share_existing,
// add_followers, post_comment, etc. operation.
ActivityHandle NewLocalActivity(
    AppState* state, WallTime timestamp,
    const ViewpointHandle& vh, const DBHandle& updates) {
  ActivityHandle ah = state->activity_table()->NewActivity(updates);
  ah->Lock();
  ah->set_timestamp(timestamp);
  ah->set_user_id(state->user_id());
  ah->mutable_activity_id()->set_server_id(
      EncodeActivityId(state->device_id(), ah->activity_id().local_id(),
                       ah->timestamp()));
  ah->mutable_viewpoint_id()->CopyFrom(vh->id());

  // NOTE: we don't set the activity's update_seq value as there's no
  // way to know in advance the correct value that the server will
  // assign when the activity is uploaded. When the uploaded activity
  // is queried on a subsequent notification, the correct value will
  // be set.
  ah->set_upload_activity(true);

  return ah;
}

// Creates a local activity as a placeholder for upload, but without
// an explicit viewpoint, as the activity is meant for the default
// viewpoint.
ActivityHandle NewLocalActivity(
    AppState* state, WallTime timestamp, const DBHandle& updates) {
  ActivityHandle ah = state->activity_table()->NewActivity(updates);
  ah->Lock();
  ah->set_timestamp(timestamp);
  ah->set_user_id(state->user_id());
  ah->mutable_activity_id()->set_server_id(
      EncodeActivityId(state->device_id(), ah->activity_id().local_id(),
                       ah->timestamp()));
  ah->set_upload_activity(true);

  return ah;
}

// Fits the specified photo ids where possible into "existing_episodes";
// otherwise, creates new derivative episodes as necessary to hold photos.
// A description of episode id / photo ids for each is stored in
// *share_episodes.
bool AddPhotosToActivity(
    AppState* state, const vector<EpisodeHandle>& existing_episodes,
    ShareEpisodes* share_episodes, const ViewpointHandle& vh,
    const PhotoSelectionVec& photo_ids, const DBHandle& updates) {
  vector<EpisodeHandle> episodes;

  for (int i = 0; i < photo_ids.size(); ++i) {
    const int64_t photo_id = photo_ids[i].photo_id;
    const int64_t episode_id = photo_ids[i].episode_id;

    PhotoHandle ph = state->photo_table()->LoadPhoto(photo_id, updates);
    if (!ph.get()) {
      // Unable to find the photo.
      return false;
    }

    // Find the existing episode structure if it exists. This could be
    // optimized, but should be plenty fast even when sharing hundreds of
    // photos.
    ActivityMetadata::Episode* e = NULL;
    EpisodeHandle eh;
    for (int j = 0; j < episodes.size(); ++j) {
      if (episodes[j]->parent_id().local_id() == episode_id) {
        eh = episodes[j];
        e = share_episodes->Mutable(j);
        break;
      }
    }
    if (!e) {
      // Check the existing_episodes vector.
      for (int j = 0; j < existing_episodes.size(); ++j) {
        if (existing_episodes[j]->parent_id().local_id() == episode_id) {
          eh = existing_episodes[j];
          break;
        }
      }
      if (!eh.get()) {
        // Create a new episode, inheriting bits of state from the parent
        // episode.
        EpisodeHandle parent = state->episode_table()->LoadEpisode(episode_id, updates);
        if (!parent.get()) {
          // Unable to find episode photo is being shared from.
          return false;
        }

        eh = state->episode_table()->NewEpisode(updates);
        eh->Lock();
        eh->set_user_id(state->user_id());
        eh->set_timestamp(parent->timestamp());
        eh->set_publish_timestamp(WallTime_Now());
        eh->set_upload_episode(true);
        eh->mutable_id()->set_server_id(
            EncodeEpisodeId(state->device_id(), eh->id().local_id(),
                            eh->timestamp()));
        eh->mutable_parent_id()->CopyFrom(parent->id());
        if (vh.get()) {
          eh->mutable_viewpoint_id()->CopyFrom(vh->id());
        }
      } else {
        eh->Lock();
      }
      episodes.push_back(eh);

      e = share_episodes->Add();
      e->mutable_episode_id()->CopyFrom(eh->id());
    }

    e->add_photo_ids()->CopyFrom(ph->id());
    eh->AddPhoto(ph->id().local_id());
  }

  for (int i = 0; i < episodes.size(); ++i) {
    episodes[i]->SaveAndUnlock(updates);
  }
  return true;
}

bool AddPhotosToShareActivity(
    AppState* state, ShareEpisodes* share_episodes, const ViewpointHandle& vh,
    const PhotoSelectionVec& photo_ids, const DBHandle& updates) {
  // List the existing episodes in the viewpoint.
  vector<EpisodeHandle> existing_episodes;
  vh->ListEpisodes(&existing_episodes);

  return AddPhotosToActivity(state, existing_episodes, share_episodes, vh, photo_ids, updates);
}

bool AddPhotosToSaveActivity(
    AppState* state, ShareEpisodes* share_episodes,
    const PhotoSelectionVec& photo_ids, const DBHandle& updates) {
  // Get list of all episodes which have parent id equal to episode
  // ids specified in "photo_ids" and are part of the default
  // viewpoint. We filter this list to contain only episodes which are
  // local or part of the default viewpoint. This comprises the list
  // of "existing" episodes to which we want to add any overlapping
  // photo ids.
  vector<EpisodeHandle> existing_episodes;
  for (int i = 0; i < photo_ids.size(); ++i) {
    const int64_t episode_id = photo_ids[i].episode_id;

    vector<int64_t> child_ids;
    state->episode_table()->ListEpisodesByParentId(episode_id, &child_ids, updates);
    for (int j = 0; j < child_ids.size(); ++j) {
      EpisodeHandle eh = state->episode_table()->LoadEpisode(child_ids[j], updates);
      if (eh.get()) {
        ViewpointHandle vh = state->viewpoint_table()->LoadViewpoint(eh->viewpoint_id(), updates);
        if (!vh.get() || vh->is_default()) {
          DCHECK_EQ(eh->user_id(), state->user_id());
          existing_episodes.push_back(eh);
        }
      }
    }
  }

  ViewpointHandle vh;
  return AddPhotosToActivity(state, existing_episodes, share_episodes, vh, photo_ids, updates);
}

bool AddContactsToAddFollowersActivity(
    const ActivityHandle& ah, const vector<ContactMetadata>& contacts) {
  for (int i = 0; i < contacts.size(); ++i) {
    ah->mutable_add_followers()->add_contacts()->CopyFrom(contacts[i]);
  }
  return true;
}

bool AddContactsToShareNewActivity(
    const ActivityHandle& ah, const vector<ContactMetadata>& contacts) {
  for (int i = 0; i < contacts.size(); ++i) {
    ah->mutable_share_new()->add_contacts()->CopyFrom(contacts[i]);
  }
  return true;
}

}  // namespace

string EncodeFollowerViewpointKey(int64_t follower_id, int64_t viewpoint_id) {
  string s;
  OrderedCodeEncodeInt64Pair(&s, follower_id, viewpoint_id);
  return DBFormat::follower_viewpoint_key(s);
}

string EncodeViewpointFollowerKey(int64_t viewpoint_id, int64_t follower_id) {
  string s;
  OrderedCodeEncodeInt64Pair(&s, viewpoint_id, follower_id);
  return DBFormat::viewpoint_follower_key(s);
}

string EncodeViewpointGCKey(int64_t viewpont_id, WallTime expiration) {
  string s;
  OrderedCodeEncodeVarint64(&s, viewpont_id);
  OrderedCodeEncodeVarint32(&s, expiration);
  return DBFormat::viewpoint_gc_key(s);
}

string EncodeViewpointScrollOffsetKey(int64_t viewpoint_id) {
  string s;
  OrderedCodeEncodeVarint64(&s, viewpoint_id);
  return DBFormat::viewpoint_scroll_offset_key(s);
}

bool DecodeFollowerViewpointKey(Slice key, int64_t* follower_id, int64_t* viewpoint_id) {
  if (!key.starts_with(kFollowerViewpointKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kFollowerViewpointKeyPrefix.size());
  OrderedCodeDecodeInt64Pair(&key, follower_id, viewpoint_id);
  return true;
}

bool DecodeViewpointFollowerKey(Slice key, int64_t* viewpoint_id, int64_t* follower_id) {
  if (!key.starts_with(kViewpointFollowerKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kViewpointFollowerKeyPrefix.size());
  OrderedCodeDecodeInt64Pair(&key, viewpoint_id, follower_id);
  return true;
}

bool DecodeViewpointGCKey(Slice key, int64_t* viewpoint_id, WallTime* expiration) {
  if (!key.starts_with(kViewpointGCKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kViewpointGCKeyPrefix.size());
  *viewpoint_id = OrderedCodeDecodeVarint64(&key);
  *expiration = OrderedCodeDecodeVarint32(&key);
  return true;
}

bool DecodeViewpointScrollOffsetKey(Slice key, int64_t* viewpoint_id) {
  if (!key.starts_with(kViewpointScrollOffsetKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kViewpointScrollOffsetKeyPrefix.size());
  *viewpoint_id = OrderedCodeDecodeVarint64(&key);
  return true;
}


////
// ViewpointTable_Viewpoint

const string ViewpointTable_Viewpoint::kTypeDefault = "default";
const double ViewpointTable_Viewpoint::kViewpointGCExpirationSeconds = 60 * 60 * 24;  // 1 day

ViewpointTable_Viewpoint::ViewpointTable_Viewpoint(
    AppState* state, const DBHandle& db, int64_t id)
    : state_(state),
      db_(db),
      disk_label_removed_(true) {
  mutable_id()->set_local_id(id);
}

void ViewpointTable_Viewpoint::MergeFrom(const ViewpointMetadata& m) {
  // Some assertions that immutable properties don't change.
  if (has_user_id() && m.has_user_id()) {
    DCHECK_EQ(user_id(), m.user_id());
  }
  if (m.has_cover_photo()) {
    // Clear existing cover photo in case client has just a
    // local id and server is sending just a server id--we don't
    // want any franken-merging in the event the cover photo changes.
    clear_cover_photo();
  }

  // Ratchet the update/viewed sequence numbers to allow only monotonic
  // increases. In the case of viewed_seq, the client may have updated
  // locally only to have a concurrent query via viewpoint invalidation
  // overwrite the local value.
  const int64_t max_update_seq = std::max<int64_t>(update_seq(), m.update_seq());
  const int64_t max_viewed_seq = std::max<int64_t>(viewed_seq(), m.viewed_seq());

  ViewpointMetadata::MergeFrom(m);

  set_update_seq(max_update_seq);
  set_viewed_seq(max_viewed_seq);
}

void ViewpointTable_Viewpoint::MergeFrom(const ::google::protobuf::Message&) {
  DIE("MergeFrom(Message&) should not be used");
}


void ViewpointTable_Viewpoint::AddFollower(int64_t follower_id) {
  EnsureFollowerState();
  if (!ContainsKey(*followers_, follower_id) ||
      (*followers_)[follower_id] == REMOVED) {
    (*followers_)[follower_id] = ADDED;
  }
}

void ViewpointTable_Viewpoint::RemoveFollower(int64_t follower_id) {
  EnsureFollowerState();
  (*followers_)[follower_id] = REMOVED;
}

int ViewpointTable_Viewpoint::CountFollowers() {
  EnsureFollowerState();
  return followers_->size();
}

void ViewpointTable_Viewpoint::ListFollowers(vector<int64_t>* follower_ids) {
  EnsureFollowerState();
  for (FollowerStateMap::iterator iter(followers_->begin());
       iter != followers_->end();
       ++iter) {
    follower_ids->push_back(iter->first);
  }
}

void ViewpointTable_Viewpoint::GetRemovableFollowers(
    std::unordered_set<int64_t>* removable) {
  std::unordered_map<int64_t, bool> removable_map;

  vector<int64_t> follower_ids;
  ListFollowers(&follower_ids);
  for (int i = 0; i < follower_ids.size(); ++i) {
    removable_map[follower_ids[i]] = false;
  }
  removable_map[state_->user_id()] = true;

  // Next, any users who were added during share_new or add_followers
  // activities originated by the current user less than 7 days ago are
  // added to removable_map=true.
  std::unordered_map<int64_t, int64_t> merged;  // source_id -> target_id
  for (ScopedPtr<ActivityTable::ActivityIterator> iter(
           state_->activity_table()->NewViewpointActivityIterator(
               local_id(), std::numeric_limits<int32_t>::max(), true, db_));
       !iter->done();
       iter->Prev()) {
    ActivityHandle ah = iter->GetActivity();

    // Keep track of all merged accounts.
    if (ah->has_merge_accounts()) {
      merged[ah->merge_accounts().source_user_id()] = ah->merge_accounts().target_user_id();
    }

    // Skip activities not owned by the current user or are more than
    // the removable time limit.
    if (ah->user_id() != state_->user_id() ||
        (state_->WallTime_Now() - ah->timestamp()) > kClawbackGracePeriod) {
      continue;
    }

    // add_followers and share_new activities have a list of users.
    const ::google::protobuf::RepeatedPtrField<ContactMetadata>* contacts = NULL;
    if (ah->has_add_followers()) {
      contacts = &ah->add_followers().contacts();
    } else if (ah->has_share_new()) {
      contacts = &ah->share_new().contacts();
    }
    if (contacts) {
      for (int i = 0; i < contacts->size(); ++i) {
        ContactMetadata cm = contacts->Get(i);
        if (cm.has_user_id()) {
          int64_t user_id = cm.user_id();
          if (ContainsKey(merged, user_id)) {
            user_id = merged[user_id];
          }
          if (ContainsKey(removable_map, user_id)) {
            removable_map[user_id] = true;
          }
        }
      }
    }
  }

  removable->clear();
  for (std::unordered_map<int64_t, bool>::iterator iter = removable_map.begin();
       iter != removable_map.end();
       ++iter) {
    if (iter->second) {
      removable->insert(iter->first);
    }
  }
}

void ViewpointTable_Viewpoint::ListEpisodes(
    vector<EpisodeHandle>* episodes) {
  std::unordered_set<string> unique_server_ids;
  for (ScopedPtr<ActivityTable::ActivityIterator> iter(
           state_->activity_table()->NewViewpointActivityIterator(
               id().local_id(), 0, false, db_));
       !iter->done();
       iter->Next()) {
    ActivityHandle ah = iter->GetActivity();
    if (!ah.get()) {
      continue;
    }
    const ShareEpisodes* share_episodes = ah->GetShareEpisodes();
    if (!share_episodes) {
      continue;
    }

    for (int i = 0; i < share_episodes->size(); ++i) {
      const ActivityMetadata::Episode& episode = share_episodes->Get(i);
      const string server_id = episode.episode_id().server_id();
      if (!ContainsKey(unique_server_ids, server_id)) {
        unique_server_ids.insert(server_id);
        EpisodeHandle eh = state_->episode_table()->LoadEpisode(server_id, db_);
        if (eh.get()) {
          episodes->push_back(eh);
        }
      }
    }
  }
}

EpisodeHandle ViewpointTable_Viewpoint::GetAnchorEpisode(PhotoHandle* ph_ptr) {
  // TODO(spencer): when cover photo can be updated, the anchor
  // episode will be set as viewpoint metadata.

  // As a fallback, iterate through activities until the first share
  // with photos.  These loops look daunting, but in most cases, it's
  // just going to grab the very first photo, which will be from the
  // first episode of the first share.
  for (ScopedPtr<ActivityTable::ActivityIterator> iter(
           state_->activity_table()->NewViewpointActivityIterator(
               id().local_id(), 0, false, db_));
       !iter->done();
       iter->Next()) {
    ActivityHandle ah = iter->GetActivity();
    if (!ah.get() ||
        (!ah->has_share_new() && !ah->has_share_existing())) {
      continue;
    }

    const ShareEpisodes* episodes = ah->GetShareEpisodes();
    for (int i = 0; i < episodes->size(); ++i) {
      EpisodeHandle eh = state_->episode_table()->LoadEpisode(
          episodes->Get(i).episode_id(), db_);
      if (!eh.get()) continue;

      // Exclude unshared ids.
      vector<int64_t> unshared_ids;
      eh->ListUnshared(&unshared_ids);
      std::unordered_set<int64_t> unshared_set(
          unshared_ids.begin(), unshared_ids.end());

      // Get first shared photo which we successfully load.
      for (int j = 0; j < episodes->Get(i).photo_ids_size(); ++j) {
        PhotoHandle ph = state_->photo_table()->LoadPhoto(episodes->Get(i).photo_ids(j), db_);
        if (ph.get() && !ContainsKey(unshared_set, ph->id().local_id())) {
          if (ph_ptr) {
            *ph_ptr = ph;
          }
          return eh;
        }
      }
    }
  }
  return EpisodeHandle();
}

bool ViewpointTable_Viewpoint::GetCoverPhoto(
    int64_t* photo_id, int64_t* episode_id, WallTime* timestamp,
    float* aspect_ratio) {
  if (!has_cover_photo()) {
    return false;
  }
  PhotoHandle ph =
      state_->photo_table()->LoadPhoto(cover_photo().photo_id(), db_);
  EpisodeHandle eh =
      state_->episode_table()->LoadEpisode(cover_photo().episode_id(), db_);
  if (!ph.get() || ph->label_error() ||
      !eh.get() || eh->IsUnshared(ph->id().local_id())) {
    return false;
  }

  *photo_id = ph->id().local_id();
  *episode_id = eh->id().local_id();
  *timestamp = ph->timestamp();
  *aspect_ratio = ph->aspect_ratio();
  return true;
}

string ViewpointTable_Viewpoint::FormatTitle(bool shorten, bool normalize_whitespace) {
  if (has_title() && !title().empty()) {
    return normalize_whitespace ? NormalizeWhitespace(title()) : title();
  }
  return DefaultTitle();
}

string ViewpointTable_Viewpoint::DefaultTitle() {
  // Get anchor episode to craft a default title.
  EpisodeHandle eh = GetAnchorEpisode(NULL);
  if (eh.get()) {
    Location location;
    Placemark placemark;
    if (eh->GetLocation(&location, &placemark)) {
      // Use shortened format of location.
      string loc_str;
      state_->placemark_histogram()->FormatLocation(location, placemark, true, &loc_str);
      return loc_str;
    }
  }
  return "Untitled";
}

void ViewpointTable_Viewpoint::InvalidateEpisodes(const DBHandle& updates) {
  if (is_default()) {
    // Don't invalidate trapdoors for the default viewpoint.
    return;
  }

  vector<EpisodeHandle> episodes;
  ListEpisodes(&episodes);
  for (int i = 0; i < episodes.size(); ++i) {
    episodes[i]->Invalidate(updates);
  }
}

float ViewpointTable_Viewpoint::GetGCExpiration() {
  return state_->WallTime_Now() + (label_unrevivable() ? 0 : kViewpointGCExpirationSeconds);
}

void ViewpointTable_Viewpoint::SaveHook(const DBHandle& updates) {
  // If the viewpoint is being removed (or added back), make sure to
  // update the appropriate follower groups.
  if (label_removed() != disk_label_removed_) {
    EnsureFollowerState();
  }

  if (followers_.get()) {
    vector<int64_t> original; // original list of followers
    vector<int64_t> current;  // current list of followers
    vector<int64_t> removed;  // keep track of followers to remove from map
    vector<int64_t> added;    // keep track of any added followers
    // Persist any added followers.
    for (FollowerStateMap::iterator iter(followers_->begin());
         iter != followers_->end(); ) {
      FollowerStateMap::iterator cur(iter++);
      const int64_t follower_id = cur->first;
      if (cur->second == ADDED) {
        updates->Put(EncodeViewpointFollowerKey(id().local_id(), follower_id), string());
        updates->Put(EncodeFollowerViewpointKey(follower_id, id().local_id()), string());
        cur->second = LOADED;
        added.push_back(follower_id);
        current.push_back(follower_id);
      } else if (cur->second == REMOVED) {
        original.push_back(follower_id);
        updates->Delete(EncodeViewpointFollowerKey(id().local_id(), follower_id));
        updates->Delete(EncodeFollowerViewpointKey(follower_id, id().local_id()));
        removed.push_back(follower_id);
        // If the removed follower is the user, ensure that
        // removed/unrevivable labels are set.
        if (follower_id == state_->user_id()) {
          set_label_removed(true);
          set_label_unrevivable(true);
        }
      } else {
        DCHECK_EQ(cur->second, LOADED);
        original.push_back(follower_id);
        current.push_back(follower_id);
      }
    }
    // Erase removed followers from map.
    for (int i = 0; i < removed.size(); ++i) {
      followers_->erase(removed[i]);
    }

    // Update the follower groups if applicable.
    if (!added.empty() || !removed.empty() ||
        disk_label_removed_ != label_removed()) {
      if (type() != "system") {
        // Don't count followers of system viewpoints.
        if (!disk_label_removed_) {
          state_->people_rank()->RemoveViewpoint(id().local_id(), original, updates);
        }
        if (!label_removed()) {
          state_->people_rank()->AddViewpoint(id().local_id(), current, updates);
        }
      }
      disk_label_removed_ = label_removed();
    }
  }

  // If removed label is set, make sure to add this viewpoint to
  // the garbage collection queue.
  if (label_removed()) {
    const WallTime expiration = GetGCExpiration();
    updates->Put(EncodeViewpointGCKey(id().local_id(), expiration), string());

    // If unrevivable, schedule immediate processing of the queue on commit.
    if (label_unrevivable()) {
      AppState* state = state_;
      updates->AddCommitTrigger(kViewpointGCCommitTrigger, [state] {
          dispatch_after_main(0, [state] {
              state->viewpoint_table()->ProcessGCQueue();
            });
        });
    }
  }

  // If we have changes to the cover photo, perform necessary invalidations.
  if (cover_photo().photo_id().server_id() != orig_cover_photo_.photo_id().server_id() ||
      cover_photo().episode_id().server_id() != orig_cover_photo_.episode_id().server_id()) {
    EpisodeHandle old_eh;
    if (orig_cover_photo_.has_episode_id()) {
      old_eh = state_->episode_table()->LoadEpisode(orig_cover_photo_.episode_id(), updates);
      if (old_eh.get()) {
        old_eh->Invalidate(updates);
      }
    }
    EpisodeHandle eh = state_->episode_table()->LoadEpisode(cover_photo().episode_id(), updates);
    if (eh.get()) {
      eh->Invalidate(updates);
    }
    orig_cover_photo_.CopyFrom(cover_photo());
  }

  typedef ContentTable<ViewpointTable_Viewpoint>::Content Content;
  ViewpointHandle vh (reinterpret_cast<Content*>(this));
  state_->net_queue()->QueueViewpoint(vh, updates);

  const string new_day_table_fields = GetDayTableFields();
  if (day_table_fields_ != new_day_table_fields) {
    // If not the default viewpoint, invalidate so changes to metadata
    // (e.g. title, labels, unviewed, etc.) are visible.
    if (!is_default()) {
      state_->day_table()->InvalidateViewpoint(vh, updates);
    }
    day_table_fields_ = new_day_table_fields;
  }
}

void ViewpointTable_Viewpoint::DeleteHook(const DBHandle& updates) {
  // Delete all activities.
  for (ScopedPtr<ActivityTable::ActivityIterator> iter(
           state_->activity_table()->NewViewpointActivityIterator(
               local_id(), 0, false, updates));
       !iter->done();
       iter->Next()) {
    ActivityHandle ah = iter->GetActivity();
    if (ah.get()) {
      ah->Lock();
      ah->DeleteAndUnlock(updates);
    }
  }

  EnsureFollowerState();
  if (followers_.get()) {
    vector<int64_t> original; // original list of followers
    // Persist any added followers.
    for (FollowerStateMap::iterator iter(followers_->begin());
         iter != followers_->end();
         iter++) {
      const int64_t follower_id = iter->first;
      original.push_back(follower_id);
      updates->Delete(EncodeViewpointFollowerKey(id().local_id(), follower_id));
      updates->Delete(EncodeFollowerViewpointKey(follower_id, id().local_id()));
    }

    // Update the follower groups. Don't count followers of system
    // viewpoints.
    if (type() != "system") {
      state_->people_rank()->RemoveViewpoint(id().local_id(), original, updates);
    }
  }

  // Remove scroll offset key.
  state_->db()->Delete(EncodeViewpointScrollOffsetKey(id().local_id()));

  typedef ContentTable<ViewpointTable_Viewpoint>::Content Content;
  ViewpointHandle vh (reinterpret_cast<Content*>(this));
  state_->net_queue()->DequeueViewpoint(vh, updates);
  state_->day_table()->InvalidateViewpoint(vh, updates);
}

string ViewpointTable_Viewpoint::GetDayTableFields() const {
  ViewpointMetadata m(*this);
  m.clear_queue();
  m.clear_update_metadata();
  m.clear_update_follower_metadata();
  m.clear_update_remove();
  m.clear_update_viewed_seq();
  return m.SerializeAsString();
}

bool ViewpointTable_Viewpoint::Load() {
  if (has_cover_photo()) {
    orig_cover_photo_.CopyFrom(cover_photo());
  }
  day_table_fields_ = GetDayTableFields();
  disk_label_removed_ = label_removed();
  return true;
}

void ViewpointTable_Viewpoint::EnsureFollowerState() {
  if (followers_.get()) {
    return;
  }
  followers_.reset(new FollowerStateMap);
  for (DB::PrefixIterator iter(db_, EncodeViewpointFollowerKey(id().local_id(), 0));
       iter.Valid();
       iter.Next()) {
    int64_t viewpoint_id;
    int64_t follower_id;
    if (DecodeViewpointFollowerKey(iter.key(), &viewpoint_id, &follower_id)) {
      (*followers_)[follower_id] = LOADED;
    }
  }
}


////
// ViewpointTable

ViewpointTable::ViewpointTable(AppState* state)
    : ContentTable<Viewpoint>(state,
                              DBFormat::viewpoint_key(),
                              DBFormat::viewpoint_server_key(),
                              kViewpointFSCKVersion,
                              DBFormat::metadata_key("viewpoint_table_fsck")),
      viewpoint_index_(new FullTextIndex(state_, kViewpointIndexName)) {
  state_->app_did_become_active()->Add([this] {
      ProcessGCQueue();
    });
}

ViewpointTable::~ViewpointTable() {
}

ViewpointHandle ViewpointTable::LoadViewpoint(const ViewpointId& id, const DBHandle& db) {
  ViewpointHandle vh;
  if (id.has_local_id()) {
    vh = LoadViewpoint(id.local_id(), db);
  }
  if (!vh.get() && id.has_server_id()) {
    vh = LoadViewpoint(id.server_id(), db);
  }
  return vh;
}

void ViewpointTable::CanonicalizeViewpointId(
    ViewpointId* vp_id, const DBHandle& updates) {
  // Do not try to canonicalize if there are no available ids.
  if (!vp_id->has_server_id() && !vp_id->has_local_id()) {
    LOG("cannot canonicalize empty viewpoint id");
    return;
  }
  ViewpointHandle vh = LoadViewpoint(*vp_id, updates);
  if (!vh.get()) {
    vh = NewViewpoint(updates);
    vh->Lock();
    vh->mutable_id()->set_server_id(vp_id->server_id());
    {
      // The "default" viewpoint has special handling. We need to set
      // ViewpointMetadata::type() appropriately when synthesizing a viewpoint.
      int64_t device_id;
      int64_t device_local_id;
      if (DecodeViewpointId(vp_id->server_id(), &device_id, &device_local_id)) {
        if (device_local_id == 0) {
          vh->set_type(vh->kTypeDefault);
        }
      }
      // Create a full invalidation for the viewpoint.
      InvalidateFull(vp_id->server_id(), updates);
    }
    vh->SaveAndUnlock(updates);
    vp_id->set_local_id(vh->id().local_id());
  } else if (!vp_id->has_local_id()) {
    vp_id->set_local_id(vh->id().local_id());
  }
}

void ViewpointTable::ListViewpointsForPhotoId(
    int64_t photo_id, vector<int64_t>* viewpoint_ids, const DBHandle& db) {
  std::set<int64_t> unique_viewpoint_ids;
  vector<int64_t> episode_ids;
  state_->episode_table()->ListEpisodes(photo_id, &episode_ids, db);
  for (int i = 0; i < episode_ids.size(); ++i) {
    EpisodeHandle eh = state_->episode_table()->LoadEpisode(episode_ids[i], db);
    if (!eh.get() || !eh->has_viewpoint_id()) {
      continue;
    }
    ViewpointHandle vh = LoadViewpoint(eh->viewpoint_id(), db);
    if (vh.get() && !vh->is_default() && !vh->label_removed()) {
      unique_viewpoint_ids.insert(vh->id().local_id());
    }
  }
  viewpoint_ids->clear();
  viewpoint_ids->insert(viewpoint_ids->begin(),
                        unique_viewpoint_ids.begin(), unique_viewpoint_ids.end());
}

void ViewpointTable::ListViewpointsForUserId(
    int64_t user_id, vector<int64_t>* viewpoint_ids, const DBHandle& db) {
  for (DB::PrefixIterator iter(db, EncodeFollowerViewpointKey(user_id, 0));
       iter.Valid();
       iter.Next()) {
    int64_t follower_id;
    int64_t viewpoint_id;
    if (DecodeFollowerViewpointKey(iter.key(), &follower_id, &viewpoint_id)) {
      ViewpointHandle vh = LoadViewpoint(viewpoint_id, db);
      if (vh.get() && !vh->is_default() && !vh->label_removed()) {
        viewpoint_ids->push_back(viewpoint_id);
      }
    }
  }
}

bool ViewpointTable::HasUserCreatedViewpoint(const DBHandle& db) {
  if (db->Exists(kHasUserCreatedViewpointKey)) {
    return true;
  }
  for (DB::PrefixIterator iter(db, DBFormat::viewpoint_key());
       iter.Valid();
       iter.Next()) {
    const int64_t vp_id = state_->viewpoint_table()->DecodeContentKey(iter.key());
    ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(vp_id, db);
    if (!vh.get() ||
        vh->type() == "default" ||
        vh->type() == "system" ||
        vh->user_id() != state_->user_id()) {
      continue;
    }
    db->Put<bool>(kHasUserCreatedViewpointKey, true);
    return true;
  }
  return false;
}

ViewpointTable::ContentHandle ViewpointTable::AddFollowers(
    int64_t viewpoint_id, const vector<ContactMetadata>& contacts) {
  if (!state_->is_registered()) {
    return ContentHandle();
  }

  DBHandle updates = state_->NewDBTransaction();

  ViewpointHandle vh = LoadViewpoint(viewpoint_id, updates);
  if (!vh.get()) {
    return ContentHandle();
  }
  // Add followers.
  vh->Lock();
  for (int i = 0; i < contacts.size(); ++i) {
    if (contacts[i].has_user_id()) {
      vh->AddFollower(contacts[i].user_id());
    }
  }
  vh->SaveAndUnlock(updates);

  // Create the local activity for adding followers.
  const WallTime timestamp = state_->WallTime_Now();
  ActivityHandle ah = NewLocalActivity(state_, timestamp, vh, updates);
  if (!AddContactsToAddFollowersActivity(ah, contacts)) {
    updates->Abandon();
    return ContentHandle();
  }
  ah->SaveAndUnlock(updates);
  updates->Commit();

  state_->async()->dispatch_after_main(0, [this] {
      state_->net_manager()->Dispatch();
    });
  return vh;
}

ViewpointTable::ContentHandle ViewpointTable::RemoveFollowers(
    int64_t viewpoint_id, const vector<int64_t>& user_ids) {
  if (!state_->is_registered()) {
    return ContentHandle();
  }

  DBHandle updates = state_->NewDBTransaction();

  ViewpointHandle vh = LoadViewpoint(viewpoint_id, updates);
  if (!vh.get()) {
    return ContentHandle();
  }
  // Remove followers.
  vh->Lock();
  for (int i = 0; i < user_ids.size(); ++i) {
    vh->RemoveFollower(user_ids[i]);
  }
  vh->SaveAndUnlock(updates);

  // Create the local activity for removing followers.
  const WallTime timestamp = state_->WallTime_Now();
  ActivityHandle ah = NewLocalActivity(state_, timestamp, vh, updates);
  for (int i = 0; i < user_ids.size(); ++i) {
    ah->mutable_remove_followers()->add_user_ids(user_ids[i]);
  }
  ah->SaveAndUnlock(updates);
  updates->Commit();

  state_->async()->dispatch_after_main(0, [this] {
      state_->net_manager()->Dispatch();
    });
  return vh;
}

ViewpointTable::ContentHandle ViewpointTable::PostComment(
    int64_t viewpoint_id, const string& message,
    int64_t reply_to_photo_id) {
  if (!state_->is_registered()) {
    return ContentHandle();
  }

  DBHandle updates = state_->NewDBTransaction();

  ViewpointHandle vh = LoadViewpoint(viewpoint_id, updates);
  if (!vh.get()) {
    return ContentHandle();
  }

  // Create the local activity for the comment.
  const WallTime timestamp = state_->WallTime_Now();
  ActivityHandle ah = NewLocalActivity(state_, timestamp, vh, updates);

  // Create the comment.
  CommentHandle ch = state_->comment_table()->NewComment(updates);
  ch->Lock();
  ch->set_timestamp(timestamp);
  ch->mutable_comment_id()->set_server_id(
      EncodeCommentId(state_->device_id(), ch->comment_id().local_id(),
                      ch->timestamp()));
  ch->mutable_viewpoint_id()->CopyFrom(vh->id());
  ch->set_user_id(state_->user_id());
  ch->set_message(message);
  if (reply_to_photo_id != 0) {
    PhotoHandle ph = state_->photo_table()->LoadPhoto(reply_to_photo_id, updates);
    // TODO(spencer): if you're offline and add a photo to a
    // conversation but the photo hasn't uploaded yet, this will skip
    // the reply-to-photo. We might consider generating the server id
    // earlier, instead of only at upload time.
    if (ph.get() && !ph->id().server_id().empty()) {
      ch->set_asset_id(ph->id().server_id());
    }
  }
  ch->SaveAndUnlock(updates);

  ah->mutable_post_comment()->mutable_comment_id()->CopyFrom(ch->comment_id());

  ah->SaveAndUnlock(updates);
  updates->Commit();

  state_->async()->dispatch_after_main(0, [this] {
      state_->net_manager()->Dispatch();
    });
  return vh;
}

void ViewpointTable::RemovePhotos(
    const PhotoSelectionVec& photo_ids) {
  DBHandle updates = state_->NewDBTransaction();

  // For each photo id, query all episodes containing the photo that
  // are part of the default viewpoint (e.g. visible in the library).
  PhotoSelectionVec complete_ids;
  for (int i = 0; i < photo_ids.size(); ++i) {
    vector<int64_t> episode_ids;
    if (state_->episode_table()->ListLibraryEpisodes(
            photo_ids[i].photo_id, &episode_ids, updates)) {
      for (int j = 0; j < episode_ids.size(); ++j) {
        complete_ids.push_back(PhotoSelection(photo_ids[i].photo_id, episode_ids[j]));
      }
    }
  }

  state_->episode_table()->RemovePhotos(complete_ids, updates);
  updates->Commit();

  state_->async()->dispatch_after_main(0, [this] {
      state_->net_manager()->Dispatch();
    });
}

void ViewpointTable::SavePhotos(
    const PhotoSelectionVec& photo_ids, int64_t autosave_viewpoint_id) {
  if (!state_->is_registered()) {
    return;
  }

  DBHandle updates = state_->NewDBTransaction();
  SavePhotos(photo_ids, autosave_viewpoint_id, updates);
  updates->Commit();

  state_->async()->dispatch_after_main(0, [this] {
      state_->net_manager()->Dispatch();
    });
}

void ViewpointTable::SavePhotos(
    const PhotoSelectionVec& photo_ids, int64_t autosave_viewpoint_id, const DBHandle& updates) {
  // Create the local activity for the save.
  const WallTime timestamp = state_->WallTime_Now();
  ActivityHandle ah = NewLocalActivity(state_, timestamp, updates);
  if (!AddPhotosToSaveActivity(
          state_, ah->mutable_save_photos()->mutable_episodes(), photo_ids, updates)) {
    updates->Abandon();
    return;
  }
  if (autosave_viewpoint_id != 0) {
    ViewpointHandle vh = LoadViewpoint(autosave_viewpoint_id, updates);
    if (vh.get()) {
      ah->mutable_save_photos()->mutable_viewpoint_id()->CopyFrom(vh->id());
    }
  }

  ah->SaveAndUnlock(updates);
}

ViewpointTable::ContentHandle ViewpointTable::ShareExisting(
    int64_t viewpoint_id, const PhotoSelectionVec& photo_ids,
    bool update_cover_photo) {
  if (!state_->is_registered()) {
    return ContentHandle();
  }

  DBHandle updates = state_->NewDBTransaction();

  ViewpointHandle vh = LoadViewpoint(viewpoint_id, updates);
  if (!vh.get()) {
    return ContentHandle();
  }
  DCHECK(!vh->provisional());

  // Create the local activity for the share.
  const WallTime timestamp = state_->WallTime_Now();
  ActivityHandle ah = NewLocalActivity(state_, timestamp, vh, updates);
  if (!AddPhotosToShareActivity(
          state_, ah->mutable_share_existing()->mutable_episodes(),
          vh, photo_ids, updates)) {
    updates->Abandon();
    return ContentHandle();
  }
  ah->SaveAndUnlock(updates);
  state_->SetupViewpointTransition(viewpoint_id, updates);

  // Reset the cover photo if one isn't set or an update was specified.
  if (!vh->has_cover_photo() || update_cover_photo) {
    const ActivityMetadata::Episode* cover_episode =
        ah->share_existing().episodes_size() > 0 ?
        &ah->share_existing().episodes(0) : NULL;
    if (cover_episode && cover_episode->photo_ids_size() > 0) {
      vh->Lock();
      if (update_cover_photo) {
        vh->set_update_metadata(true);
      }
      vh->mutable_cover_photo()->mutable_photo_id()->CopyFrom(
          cover_episode->photo_ids(0));
      vh->mutable_cover_photo()->mutable_episode_id()->CopyFrom(
          cover_episode->episode_id());
      vh->SaveAndUnlock(updates);
    }
  }

  updates->Commit();

  state_->async()->dispatch_after_main(0, [this] {
      state_->net_manager()->Dispatch();
    });
  return vh;
}

ViewpointTable::ContentHandle ViewpointTable::ShareNew(
    const PhotoSelectionVec& photo_ids,
    const vector<ContactMetadata>& contacts,
    const string& title, bool provisional) {
  if (!state_->is_registered()) {
    return ContentHandle();
  }

  DBHandle updates = state_->NewDBTransaction();

  // Create the viewpoint for the share.
  ViewpointHandle vh = NewViewpoint(updates);
  vh->Lock();
  vh->mutable_id()->set_server_id(
      EncodeViewpointId(state_->device_id(), vh->id().local_id()));
  vh->set_user_id(state_->user_id());
  if (!title.empty()) {
    vh->set_title(title);
  }
  if (provisional) {
    vh->set_provisional(provisional);
  }
  // Set default labels admin and contribute.
  vh->set_label_admin(true);
  vh->set_label_contribute(true);

  // Add followers.
  bool has_user_id = false;
  vh->AddFollower(state_->user_id());
  for (int i = 0; i < contacts.size(); ++i) {
    if (contacts[i].has_user_id()) {
      if (contacts[i].user_id() == state_->user_id()) {
        has_user_id = true;
      }
      vh->AddFollower(contacts[i].user_id());
    }
  }
  if (!has_user_id) {
    vh->AddFollower(state_->user_id());
  }
  vh->SaveAndUnlock(updates);

  // Create the local activity for the share.
  const WallTime timestamp = state_->WallTime_Now();
  ActivityHandle ah = NewLocalActivity(state_, timestamp, vh, updates);
  if (!AddPhotosToShareActivity(
          state_, ah->mutable_share_new()->mutable_episodes(),
          vh, photo_ids, updates)) {
    updates->Abandon();
    return ContentHandle();
  }
  if (!AddContactsToShareNewActivity(ah, contacts)) {
    updates->Abandon();
    return ContentHandle();
  }
  if (!has_user_id) {
    ContactMetadata c;
    if (state_->contact_manager()->LookupUser(state_->user_id(), &c)) {
      ah->mutable_share_new()->add_contacts()->CopyFrom(c);
    }
  }
  if (provisional) {
    ah->set_provisional(provisional);
  }
  ah->SaveAndUnlock(updates);

  // Set the cover photo automatically to first shared photo.
  const ActivityMetadata::Episode* cover_episode =
      ah->share_new().episodes_size() > 0 ?
      &ah->share_new().episodes(0) : NULL;
  if (cover_episode && cover_episode->photo_ids_size() > 0) {
    vh->Lock();
    vh->mutable_cover_photo()->mutable_photo_id()->CopyFrom(
        cover_episode->photo_ids(0));
    vh->mutable_cover_photo()->mutable_episode_id()->CopyFrom(
        cover_episode->episode_id());
    vh->SaveAndUnlock(updates);
  }

  state_->SetupViewpointTransition(vh->id().local_id(), updates);
  updates->Commit();

  state_->async()->dispatch_after_main(0, [this] {
      state_->net_manager()->Dispatch();
    });
  return vh;
}

bool ViewpointTable::CommitShareNew(int64_t viewpoint_id, const DBHandle& updates) {
  ViewpointHandle vh = LoadViewpoint(viewpoint_id, updates);
  if (!vh.get()) {
    return false;
  }
  vh->Lock();
  vh->clear_provisional();

  // Mark any provisional activities as ready.
  for (ScopedPtr<ActivityTable::ActivityIterator> iter(
           state_->activity_table()->NewViewpointActivityIterator(
               vh->id().local_id(), 0, false, updates));
       !iter->done();
       iter->Next()) {
    ActivityHandle ah = iter->GetActivity();
    if (!ah.get() || !ah->provisional()) {
      continue;
    }
    ah->Lock();
    ah->clear_provisional();
    if (ah->has_share_new()) {
      // Update activity timestamp.
      ah->set_timestamp(state_->WallTime_Now());

      // Add followers which have user ids already. Prospective contacts
      // will only be added as followers when the server reports back with
      // a followers invalidation.
      for (int i = 0; i < ah->share_new().contacts_size(); ++i) {
        const ContactMetadata& c = ah->share_new().contacts(i);
        if (c.has_user_id()) {
          vh->AddFollower(c.user_id());
        }
      }
    }
    ah->SaveAndUnlock(updates);
  }

  vh->SaveAndUnlock(updates);
  return true;
}

bool ViewpointTable::UpdateShareNew(
    int64_t viewpoint_id, int64_t activity_id,
    const PhotoSelectionVec& photo_ids) {
  if (!state_->is_registered()) {
    return false;
  }

  DBHandle updates = state_->NewDBTransaction();

  ViewpointHandle vh = LoadViewpoint(viewpoint_id, updates);
  if (!vh.get() || !vh->provisional()) {
    return false;
  }

  ActivityHandle ah = state_->activity_table()->LoadActivity(
      activity_id, updates);
  if (!ah.get() || !ah->provisional()) {
    return false;
  }

  ah->Lock();
  ah->FilterShare(PhotoSelectionSet(photo_ids.begin(), photo_ids.end()), updates);

  if (!AddPhotosToShareActivity(
          state_, ah->mutable_share_new()->mutable_episodes(),
          vh, photo_ids, updates)) {
    updates->Abandon();
    return false;
  }

  // Update the timestamp in case there was a lag. Note that the
  // original server id would have been encoded with a different
  // timestamp, so these two could become out of sync. The timestamp
  // baked into the server id is not used for anything on the server
  // or client--it's mostly an aide to debugging. It will remain the
  // time at which the client thought it first created the activity.
  ah->set_timestamp(state_->WallTime_Now());
  ah->SaveAndUnlock(updates);

  // Set the cover photo automatically to first shared photo.
  const ActivityMetadata::Episode* cover_episode =
      ah->share_new().episodes_size() > 0 ?
      &ah->share_new().episodes(0) : NULL;
  vh->Lock();
  vh->clear_cover_photo();
  if (cover_episode && cover_episode->photo_ids_size() > 0) {
    vh->mutable_cover_photo()->mutable_photo_id()->CopyFrom(
        cover_episode->photo_ids(0));
    vh->mutable_cover_photo()->mutable_episode_id()->CopyFrom(
        cover_episode->episode_id());
  }
  vh->SaveAndUnlock(updates);
  updates->Commit();

  state_->async()->dispatch_after_main(0, [this] {
      state_->net_manager()->Dispatch();
    });
  return true;
}

ViewpointTable::ContentHandle ViewpointTable::Unshare(
    int64_t viewpoint_id, const PhotoSelectionVec& photo_ids) {
  if (!state_->is_registered()) {
    return ContentHandle();
  }

  DBHandle updates = state_->NewDBTransaction();

  ViewpointHandle vh = LoadViewpoint(viewpoint_id, updates);
  if (!vh.get()) {
    return ContentHandle();
  }

  vector<EpisodeHandle> existing_episodes;
  vh->ListEpisodes(&existing_episodes);
  std::unordered_map<int64_t, EpisodeHandle> episode_map;
  for (int i = 0; i < existing_episodes.size(); ++i) {
    episode_map[existing_episodes[i]->id().local_id()] = existing_episodes[i];
  }

  // Create the local activity for the unshare.
  const WallTime timestamp = state_->WallTime_Now();
  ActivityHandle ah = NewLocalActivity(state_, timestamp, vh, updates);
  ShareEpisodes* share_episodes = ah->mutable_unshare()->mutable_episodes();
  vector<EpisodeHandle> episodes;
  bool unshared_cover_photo = false;

  for (int i = 0; i < photo_ids.size(); ++i) {
    const int64_t photo_id = photo_ids[i].photo_id;
    const int64_t episode_id = photo_ids[i].episode_id;

    PhotoHandle ph = state_->photo_table()->LoadPhoto(photo_id, updates);
    if (!ph.get()) {
      // Unable to find the photo to unshare.
      updates->Abandon();
      return ContentHandle();
    }

    ActivityMetadata::Episode* e = NULL;
    EpisodeHandle eh;
    for (int j = 0; j < episodes.size(); ++j) {
      if (episodes[j]->id().local_id() == episode_id) {
        eh = episodes[j];
        e = share_episodes->Mutable(j);
        break;
      }
    }
    if (!e) {
      if (!ContainsKey(episode_map, episode_id)) {
        // Unable to find episode being unshared from.
        updates->Abandon();
        return ContentHandle();
      }
      eh = episode_map[episode_id];
      episodes.push_back(eh);
      e = share_episodes->Add();
      e->mutable_episode_id()->CopyFrom(eh->id());
      eh->Lock();
    }

    e->add_photo_ids()->CopyFrom(ph->id());
    // Actually unshare the photo from the local episode. This will
    // happen again when the notification for the unshare is received,
    // but this updates the UI immediately.
    eh->UnsharePhoto(ph->id().local_id());

    if (vh->has_cover_photo() &&
        vh->cover_photo().photo_id().server_id() == ph->id().server_id() &&
        vh->cover_photo().episode_id().server_id() == eh->id().server_id()) {
      unshared_cover_photo = true;
    }
  }

  if (share_episodes->size() == 0) {
    ah->Unlock();
    updates->Abandon();
    return vh;
  }

  // Save all episodes which have had photos unshared.
  for (int i = 0; i < episodes.size(); ++i) {
    episodes[i]->SaveAndUnlock(updates);
  }

  ah->SaveAndUnlock(updates);

  // If we're unsharing the cover photo, set a new one locally.
  if (unshared_cover_photo) {
    ResetCoverPhoto(vh, updates);
  }

  updates->Commit();

  state_->async()->dispatch_after_main(0, [this] {
      state_->net_manager()->Dispatch();
    });
  return vh;
}

ViewpointTable::ContentHandle ViewpointTable::Remove(
    int64_t viewpoint_id) {
  DBHandle updates = state_->NewDBTransaction();

  ViewpointHandle vh = LoadViewpoint(viewpoint_id, updates);
  if (!vh.get()) {
    return ContentHandle();
  }

  if (!vh->label_removed()) {
    vh->Lock();
    vh->set_label_removed(true);
    vh->set_update_remove(true);
    vh->SaveAndUnlock(updates);

    vh->InvalidateEpisodes(updates);
    updates->Commit();
    state_->async()->dispatch_after_main(0, [this] {
        state_->net_manager()->Dispatch();
      });
  }

  return vh;
}

ViewpointTable::ContentHandle ViewpointTable::UpdateCoverPhoto(
    int64_t viewpoint_id, int64_t photo_id, int64_t episode_id) {
  DBHandle updates = state_->NewDBTransaction();

  ViewpointHandle vh = LoadViewpoint(viewpoint_id, updates);
  if (!vh.get()) {
    return ContentHandle();
  }

  PhotoHandle ph = state_->photo_table()->LoadPhoto(photo_id, updates);
  EpisodeHandle eh = state_->episode_table()->LoadEpisode(episode_id, updates);
  if (ph.get() && eh.get()) {
    vh->Lock();
    vh->set_update_metadata(true);
    vh->mutable_cover_photo()->mutable_photo_id()->CopyFrom(ph->id());
    vh->mutable_cover_photo()->mutable_episode_id()->CopyFrom(eh->id());
    vh->SaveAndUnlock(updates);
    updates->Commit();
    state_->async()->dispatch_after_main(0, [this] {
        state_->net_manager()->Dispatch();
      });
  }

  return vh;
}

ViewpointTable::ContentHandle ViewpointTable::UpdateTitle(
    int64_t viewpoint_id, const string& title) {
  DBHandle updates = state_->NewDBTransaction();

  ViewpointHandle vh = LoadViewpoint(viewpoint_id, updates);
  if (!vh.get()) {
    return ContentHandle();
  }

  vh->Lock();
  vh->set_title(title);
  vh->set_update_metadata(true);
  vh->SaveAndUnlock(updates);
  updates->Commit();
  state_->async()->dispatch_after_main(0, [this] {
      state_->net_manager()->Dispatch();
    });

  return vh;
}

ViewpointTable::ContentHandle ViewpointTable::UpdateViewedSeq(
    int64_t viewpoint_id) {
  DBHandle updates = state_->NewDBTransaction();

  ViewpointHandle vh = LoadViewpoint(viewpoint_id, updates);
  if (!vh.get()) {
    return ContentHandle();
  }

  // Do not update the viewed sequence for provisional viewpoints. They are
  // local to the client.
  if (!vh->provisional() && vh->viewed_seq() < vh->update_seq()) {
    vh->Lock();
    vh->set_viewed_seq(vh->update_seq());
    vh->set_update_viewed_seq(true);
    vh->SaveAndUnlock(updates);
    updates->Commit();
    state_->async()->dispatch_after_main(0, [this] {
        state_->net_manager()->Dispatch();
      });
  }

  return vh;
}

void ViewpointTable::SetScrollOffset(int64_t viewpoint_id, float offset) {
  state_->db()->Put(EncodeViewpointScrollOffsetKey(viewpoint_id), offset);
}

float ViewpointTable::GetScrollOffset(int64_t viewpoint_id) {
  return state_->db()->Get<float>(EncodeViewpointScrollOffsetKey(viewpoint_id), 0);
}

bool ViewpointTable::ResetCoverPhoto(
    const ViewpointHandle& vh, const DBHandle& updates) {
  PhotoHandle ph;
  EpisodeHandle eh = vh->GetAnchorEpisode(&ph);
  vh->Lock();
  if (ph.get()) {
    vh->mutable_cover_photo()->mutable_photo_id()->CopyFrom(ph->id());
    vh->mutable_cover_photo()->mutable_episode_id()->CopyFrom(eh->id());
  } else {
    vh->clear_cover_photo();
  }
  vh->SaveAndUnlock(updates);
  return ph.get();
}

ViewpointTable::ContentHandle ViewpointTable::UpdateAutosaveLabel(
    int64_t viewpoint_id, bool autosave) {
  return UpdateLabel(viewpoint_id,
                     &ViewpointMetadata::label_autosave,
                     &ViewpointMetadata::set_label_autosave,
                     &ViewpointMetadata::clear_label_autosave,
                     autosave);
}

ViewpointTable::ContentHandle ViewpointTable::UpdateHiddenLabel(
    int64_t viewpoint_id, bool hidden) {
  return UpdateLabel(viewpoint_id,
                     &ViewpointMetadata::label_hidden,
                     &ViewpointMetadata::set_label_hidden,
                     &ViewpointMetadata::clear_label_hidden,
                     hidden);
}

ViewpointTable::ContentHandle ViewpointTable::UpdateMutedLabel(
    int64_t viewpoint_id, bool muted) {
  return UpdateLabel(viewpoint_id,
                     &ViewpointMetadata::label_muted,
                     &ViewpointMetadata::set_label_muted,
                     &ViewpointMetadata::clear_label_muted,
                     muted);
}

ViewpointTable::ContentHandle ViewpointTable::UpdateLabel(
    int64_t viewpoint_id,
    bool (ViewpointMetadata::*getter)() const,
    void (ViewpointMetadata::*setter)(bool),
    void (ViewpointMetadata::*clearer)(),
    bool set_label) {
  DBHandle updates = state_->NewDBTransaction();

  ViewpointHandle vh = LoadViewpoint(viewpoint_id, updates);
  if (!vh.get()) {
    return ContentHandle();
  }

  if ((*vh.*getter)() != set_label) {
    vh->Lock();
    if (set_label) {
      (*vh.*setter)(true);
    } else {
      (*vh.*clearer)();
    }
    vh->set_update_follower_metadata(true);
    vh->SaveAndUnlock(updates);
    vh->InvalidateEpisodes(updates);
    updates->Commit();
    state_->async()->dispatch_after_main(0, [this] {
        state_->net_manager()->Dispatch();
      });
  }

  return vh;
}

void ViewpointTable::Validate(
    const ViewpointSelection& s, const DBHandle& updates) {
  const string key(DBFormat::viewpoint_selection_key(s.viewpoint_id()));

  // Load any existing viewpoint selection and clear attributes which have been
  // queried by "s". If no attributes remain set, the selection is deleted.
  ViewpointSelection existing;
  if (updates->GetProto(key, &existing)) {
    if (s.get_attributes()) {
      existing.clear_get_attributes();
    }
    if (s.get_followers()) {
      if (!existing.get_followers() ||
          s.follower_start_key() <= existing.follower_start_key()) {
        existing.clear_get_followers();
        existing.clear_follower_start_key();
      }
    } else if (existing.get_followers()) {
      existing.set_follower_start_key(
          std::max(existing.follower_start_key(),
                   s.follower_start_key()));
    }
    if (s.get_activities()) {
      if (!existing.get_activities() ||
          s.activity_start_key() <= existing.activity_start_key()) {
        existing.clear_get_activities();
        existing.clear_activity_start_key();
      }
    } else if (existing.get_activities()) {
      existing.set_activity_start_key(
          std::max(existing.activity_start_key(),
                   s.activity_start_key()));
    }
    if (s.get_episodes()) {
      if (!existing.get_episodes() ||
          s.episode_start_key() <= existing.episode_start_key()) {
        existing.clear_get_episodes();
        existing.clear_episode_start_key();
      }
    } else if (existing.get_episodes()) {
      existing.set_episode_start_key(
          std::max(existing.episode_start_key(),
                   s.episode_start_key()));
    }
    if (s.get_comments()) {
      if (!existing.get_comments() ||
          s.comment_start_key() <= existing.comment_start_key()) {
        existing.clear_get_comments();
        existing.clear_comment_start_key();
      }
    } else if (existing.get_comments()) {
      existing.set_comment_start_key(
          std::max(existing.comment_start_key(),
                   s.comment_start_key()));
    }
  }

  if (existing.has_get_attributes() ||
      existing.has_get_followers() ||
      existing.has_get_activities() ||
      existing.has_get_episodes() ||
      existing.has_get_comments()) {
    updates->PutProto(key, existing);
  } else {
    updates->Delete(key);
  }
}

void ViewpointTable::Invalidate(
    const ViewpointSelection& s, const DBHandle& updates) {
  const string key(DBFormat::viewpoint_selection_key(s.viewpoint_id()));

  // Load any existing viewpoint selection and merge invalidations from "s".
  ViewpointSelection existing;
  if (!updates->GetProto(key, &existing)) {
    existing.set_viewpoint_id(s.viewpoint_id());
  }

  if (s.get_attributes()) {
    existing.set_get_attributes(true);
  }
  if (s.get_followers()) {
    if (existing.get_followers()) {
      existing.set_follower_start_key(std::min<string>(existing.follower_start_key(),
                                                       s.follower_start_key()));
    } else {
      existing.set_follower_start_key(s.follower_start_key());
    }
    existing.set_get_followers(true);
  }
  if (s.get_activities()) {
    if (existing.get_activities()) {
      existing.set_activity_start_key(std::min<string>(existing.activity_start_key(),
                                                       s.activity_start_key()));
    } else {
      existing.set_activity_start_key(s.activity_start_key());
    }
    existing.set_get_activities(true);
  }
  if (s.get_episodes()) {
    if (existing.get_episodes()) {
      existing.set_episode_start_key(std::min<string>(existing.episode_start_key(),
                                                      s.episode_start_key()));
    } else {
      existing.set_episode_start_key(s.episode_start_key());
    }
    existing.set_get_episodes(true);
  }
  if (s.get_comments()) {
    if (existing.get_comments()) {
      existing.set_comment_start_key(std::min<string>(existing.comment_start_key(),
                                                      s.comment_start_key()));
    } else {
      existing.set_comment_start_key(s.comment_start_key());
    }
    existing.set_get_comments(true);
  }

  updates->PutProto(key, existing);
}

void ViewpointTable::InvalidateFull(
    const string& server_id, const DBHandle& updates) {
  ViewpointSelection s;
  s.set_viewpoint_id(server_id);
  s.set_get_attributes(true);
  s.set_get_activities(true);
  s.set_get_episodes(true);
  s.set_get_followers(true);
  s.set_get_comments(true);
  Invalidate(s, updates);
}

void ViewpointTable::ListInvalidations(
    vector<ViewpointSelection>* v, int limit, const DBHandle& db) {
  v->clear();
  ScopedPtr<leveldb::Iterator> iter(db->NewIterator());
  iter->Seek(kViewpointSelectionKeyPrefix);
  while (iter->Valid() && (limit <= 0 || v->size() < limit)) {
    Slice key = ToSlice(iter->key());
    if (!key.starts_with(kViewpointSelectionKeyPrefix)) {
      break;
    }
    ViewpointSelection vps;
    if (db->GetProto(key, &vps)) {
      if (vps.has_viewpoint_id() && !vps.viewpoint_id().empty()) {
        v->push_back(vps);
      } else {
        LOG("empty viewpoint id in viewpoint selection: %s; deleting", key);
        state_->db()->Delete(key);
      }
    } else {
      LOG("unable to read viewpoint selection at key %s; deleting", key);
      state_->db()->Delete(key);
    }
    iter->Next();
  }
}

void ViewpointTable::ClearAllInvalidations(const DBHandle& updates) {
  ScopedPtr<leveldb::Iterator> iter(updates->NewIterator());
  iter->Seek(kViewpointSelectionKeyPrefix);
  for (; iter->Valid(); iter->Next()) {
    Slice key = ToSlice(iter->key());
    if (!key.starts_with(kViewpointSelectionKeyPrefix)) {
      break;
    }
    updates->Delete(key);
  }
}

void ViewpointTable::ProcessGCQueue() {
  LOG("processing viewpoint garbage collection queue");
  DBHandle updates = state_->NewDBTransaction();
  for (DB::PrefixIterator iter(updates, kViewpointGCKeyPrefix);
       iter.Valid();
       iter.Next()) {
    int64_t viewpoint_id;
    WallTime expiration;
    if (DecodeViewpointGCKey(iter.key(), &viewpoint_id, &expiration)) {
      if (state_->WallTime_Now() >= expiration) {
        ViewpointHandle vh = LoadViewpoint(viewpoint_id, updates);
        if (vh.get()) {
          LOG("deleting viewpoint %s", vh->id());
          vh->Lock();
          vh->DeleteAndUnlock(updates);
        }
        updates->Delete(iter.key());
      }
    }
  }
  updates->Commit();
}

bool ViewpointTable::FSCKImpl(int prev_fsck_version, const DBHandle& updates) {
  LOG("FSCK: ViewpointTable");
  bool changes = false;

  for (DB::PrefixIterator iter(updates, DBFormat::viewpoint_key());
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const Slice value = iter.value();
    ViewpointMetadata vm;
    if (vm.ParseFromArray(value.data(), value.size())) {
      ViewpointHandle vh = LoadViewpoint(vm.id().local_id(), updates);
      vh->Lock();
      bool save_vh = false;
      if (key != EncodeContentKey(DBFormat::viewpoint_key(), vm.id().local_id())) {
        LOG("FSCK: viewpoint id %d does not equal key %s; deleting key and re-saving",
            vm.id().local_id(), key);
        updates->Delete(key);
        save_vh = true;
      }

      // Check server key mapping. This is special as viewpoints get created
      // ahead of time when the first activity is received for a viewpoint
      // which was shared with the user. We've experienced corruption issues
      // in the past where an activity incorrectly refers to a viewpoint with
      // no data via its local id while the "real" viewpoint arrives later and
      // is assigned a subsequent local id and overrides the mapping.
      //
      // This code depends on the code in ActivityTable::FSCK rewriting any
      // references as necessary.
      if (vh->id().has_server_id()) {
        const string server_key = EncodeContentServerKey(DBFormat::viewpoint_server_key(),
                                                         vh->id().server_id());
        if (!updates->Exists(server_key)) {
          LOG("FSCK: missing viewpoint server key mapping");
          save_vh = true;
        } else {
          const int64_t mapped_local_id = updates->Get<int64_t>(server_key, -1);
          if (mapped_local_id != vh->id().local_id()) {
            LOG("FSCK: viewpoint local id mismatch: %d != %d; deleting existing mapping",
                mapped_local_id, vh->id().local_id());
            updates->Delete(server_key);
            ViewpointHandle mapped_vh = LoadViewpoint(mapped_local_id, updates);
            if (mapped_vh.get()) {
              LOG("FSCK: deleting incorrectly mapped viewpoint %s", *mapped_vh);
              // List all followers, add to "canonical" viewpoint with lowest
              // id and delete mappings to this vestigial viewpoint.
              vector<int64_t> follower_ids;
              mapped_vh->ListFollowers(&follower_ids);
              for (int i = 0; i < follower_ids.size(); ++i) {
                vh->AddFollower(follower_ids[i]);
                updates->Delete(EncodeViewpointFollowerKey(mapped_vh->id().local_id(), follower_ids[i]));
                updates->Delete(EncodeFollowerViewpointKey(follower_ids[i], mapped_vh->id().local_id()));
              }
              updates->Delete(EncodeContentKey(DBFormat::viewpoint_key(), mapped_local_id));
            }
            save_vh = true;
          }
        }
      }

      // Check required fields.
      if (!vh->has_id() ||
          !vh->has_user_id()) {
        LOG("FSCK: viewpoint missing required fields: %s", *vh);
        if (vh->id().has_server_id() && !vh->id().server_id().empty()) {
          LOG("FSCK: setting invalidation for viewpoint %s", *vh);
          InvalidateFull(vh->id().server_id(), updates);
          changes = true;
        }
      }

      if (save_vh) {
        LOG("FSCK: rewriting viewpoint %s", *vh);
        vh->SaveAndUnlock(updates);
        changes = true;
      } else {
        vh->Unlock();
      }
    }
  }

  return changes;
}

void ViewpointTable::Search(const Slice& query, ViewpointSearchResults* results) {
  ScopedPtr<FullTextQuery> parsed_query(FullTextQuery::Parse(query));
  for (ScopedPtr<FullTextResultIterator> iter(viewpoint_index_->Search(state_->db(), *parsed_query));
       iter->Valid();
       iter->Next()) {
    results->push_back(FastParseInt64(iter->doc_id()));
  }
}

string ViewpointTable::FormatViewpointToken(int64_t vp_id) {
  return Format("%s%d_", kViewpointTokenPrefix, vp_id);
}

void ViewpointTable::SaveContentHook(Viewpoint* viewpoint, const DBHandle& updates) {
  vector<FullTextIndexTerm> terms;
  int pos = viewpoint_index_->ParseIndexTerms(0, viewpoint->title(), &terms);

  vector<int64_t> followers;
  viewpoint->ListFollowers(&followers);
  for (auto user_id : followers) {
    pos = viewpoint_index_->AddVerbatimToken(pos, ContactManager::FormatUserToken(user_id), &terms);
  }

  if (viewpoint->label_removed()) {
    // If the viewpoint has been removed, clear out its terms so it won't show
    // up in the autocomplete.
    // It would be nice to do the same for comments, but that's more expensive
    // and the comments are not as individually prominent in the results.
    terms.clear();
  }

  // TODO(ben): Ensure that the viewpoint is re-saved when an activity is added.
  ActivityHandle ah = state_->activity_table()->GetLatestActivity(viewpoint->id().local_id(), updates);
  const string sort_key = ah.get() ? FullTextIndex::TimestampSortKey(ah->timestamp()) : "";
  viewpoint_index_->UpdateIndex(terms, ToString(viewpoint->id().local_id()), sort_key,
                                viewpoint->mutable_indexed_terms(), updates);
}

void ViewpointTable::DeleteContentHook(Viewpoint* viewpoint, const DBHandle& updates) {
  viewpoint_index_->RemoveTerms(viewpoint->mutable_indexed_terms(), updates);
}

// local variables:
// mode: c++
// end:
