// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "ActivityTable.h"
#import "AppState.h"
#import "CommentTable.h"
#import "ContactManager.h"
#import "DayTable.h"
#import "EpisodeTable.h"
#import "NetworkQueue.h"
#import "PlacemarkHistogram.h"
#import "StringUtils.h"
#import "WallTime.h"

namespace {

const int kActivityFSCKVersion = 6;

const int kMaxContentLength = 30;

const string kActivityTimestampKeyPrefix = DBFormat::activity_timestamp_key("");
const string kCommentActivityKeyPrefix = DBFormat::comment_activity_key("");
const string kEpisodeActivityKeyPrefix = DBFormat::episode_activity_key("");
const string kQuarantinedActivityKeyPrefix = DBFormat::quarantined_activity_key("");
const string kViewpointActivityKeyPrefix = DBFormat::viewpoint_activity_key("");

const DBRegisterKeyIntrospect kActivityKeyIntrospect(
    DBFormat::activity_key(), NULL, [](Slice value) {
      return DBIntrospect::FormatProto<ActivityMetadata>(value);
    });

const DBRegisterKeyIntrospect kActivityServerKeyIntrospect(
    DBFormat::activity_server_key(), NULL, [](Slice value) {
      return value.ToString();
    });

const DBRegisterKeyIntrospect kActivityTimestampKeyIntrospect(
    kActivityTimestampKeyPrefix, [](Slice key) {
      WallTime timestamp;
      int64_t activity_id;
      if (!DecodeActivityTimestampKey(key, &timestamp, &activity_id)) {
        return string();
      }
      return string(
          Format("%s/%d", DBIntrospect::timestamp(timestamp), activity_id));
    }, NULL);

const DBRegisterKeyIntrospect kViewpointActivityKeyIntrospect(
    kViewpointActivityKeyPrefix, [](Slice key) {
      WallTime timestamp;
      int64_t activity_id;
      int64_t viewpoint_id;
      if (!DecodeViewpointActivityKey(key, &viewpoint_id, &timestamp, &activity_id)) {
        return string();
      }
      return string(
          Format("%d/%s/%d", viewpoint_id,
                 DBIntrospect::timestamp(timestamp), activity_id));
    }, NULL);

const DBRegisterKeyIntrospect kCommentActivityKeyIntrospect(
    DBFormat::comment_activity_key(""), NULL, [](Slice value) {
      return value.ToString();
    });

const DBRegisterKeyIntrospect kEpisodeActivityKeyIntrospect(
    DBFormat::episode_activity_key(""), [](Slice key) {
      string server_episode_id;
      int64_t activity_id;
      if (!DecodeEpisodeActivityKey(key, &server_episode_id, &activity_id)) {
        return string();
      }
      return string(
          Format("[%s]/%d", ServerIdFormat(server_episode_id), activity_id));
    }, NULL);

const DBRegisterKeyIntrospect kQuarantinedActivityKeyIntrospect(
    kQuarantinedActivityKeyPrefix, [](Slice key) {
      int64_t activity_id;
      if (!DecodeQuarantinedActivityKey(key, &activity_id)) {
        return string();
      }
      return string(Format("%d", activity_id));
    }, NULL);

// Iterates over activities through a time range, ordered from most
// recent to least recent.
//
// Since timestamps are sorted in reverse order, start_time should be
// greater than or equal to end_time.
class TimestampActivityIterator : public ActivityTable::ActivityIterator {
 public:
  TimestampActivityIterator(ActivityTable* table, WallTime start_time,
                            bool reverse, const DBHandle& db)
      : ActivityTable::ActivityIterator(table, reverse, db) {
    Seek(start_time);
  }

  void Seek(WallTime seek_time) {
    ContentIterator::Seek(EncodeActivityTimestampKey(
                              seek_time, reverse_ ? std::numeric_limits<int64_t>::max() : 0));
  }

 protected:
  virtual bool IteratorDone(const Slice& key) {
    return !key.starts_with(kActivityTimestampKeyPrefix);
  }

  virtual bool UpdateStateHook(const Slice& key) {
    return DecodeActivityTimestampKey(key, &cur_timestamp_, &cur_activity_id_);
  }
};

// Iterates over activites in a viewpoint in order of increasing
// activity id.
class ViewpointActivityIterator : public ActivityTable::ActivityIterator {
 public:
  ViewpointActivityIterator(ActivityTable* table, int64_t viewpoint_id,
                            WallTime start_time, bool reverse, const DBHandle& db)
      : ActivityTable::ActivityIterator(table, reverse, db),
        viewpoint_id_(viewpoint_id) {
    Seek(start_time);
  }

  void Seek(WallTime seek_time) {
    ContentIterator::Seek(EncodeViewpointActivityKey(
                              viewpoint_id_, seek_time,
                              reverse_ ? std::numeric_limits<int64_t>::max() : 0));
  }

 protected:
  virtual bool IteratorDone(const Slice& key) {
    int64_t viewpoint_id;
    if (!DecodeViewpointActivityKey(key, &viewpoint_id, &cur_timestamp_, &cur_activity_id_)) {
      return true;
    }
    return viewpoint_id != viewpoint_id_;
  }

  virtual bool UpdateStateHook(const Slice& key) {
    int64_t viewpoint_id;
    return DecodeViewpointActivityKey(key, &viewpoint_id, &cur_timestamp_, &cur_activity_id_);
  }

 private:
  const int64_t viewpoint_id_;
};

}  // namespace


string EncodeActivityTimestampKey(
    WallTime timestamp, int64_t activity_id) {
  string s;
  OrderedCodeEncodeVarint32(&s, timestamp);
  OrderedCodeEncodeVarint64(&s, activity_id);
  return DBFormat::activity_timestamp_key(s);
}

string EncodeCommentActivityKey(const string& comment_server_id) {
  return DBFormat::comment_activity_key(comment_server_id);
}

string EncodeEpisodeActivityKey(
    const string& episode_server_id, int64_t activity_id) {
  string s = episode_server_id;
  s += '/';
  OrderedCodeEncodeVarint64(&s, activity_id);
  return DBFormat::episode_activity_key(s);
}

string EncodeEpisodeActivityKeyPrefix(const string& episode_server_id) {
  string s = episode_server_id;
  s += '/';
  return DBFormat::episode_activity_key(s);
}

string EncodeQuarantinedActivityKey(int64_t activity_id) {
  string s;
  OrderedCodeEncodeVarint64(&s, activity_id);
  return DBFormat::quarantined_activity_key(s);
}

string EncodeViewpointActivityKey(
    int64_t viewpoint_id, WallTime timestamp, int64_t activity_id) {
  string s;
  OrderedCodeEncodeVarint64(&s, viewpoint_id);
  OrderedCodeEncodeVarint32(&s, timestamp);
  OrderedCodeEncodeVarint64(&s, activity_id);
  return DBFormat::viewpoint_activity_key(s);
}

bool DecodeActivityTimestampKey(
    Slice key, WallTime* timestamp, int64_t* activity_id) {
  if (!key.starts_with(kActivityTimestampKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kActivityTimestampKeyPrefix.size());
  *timestamp = OrderedCodeDecodeVarint32(&key);
  *activity_id = OrderedCodeDecodeVarint64(&key);
  return true;
}

bool DecodeCommentActivityKey(Slice key, string* server_comment_id) {
  if (!key.starts_with(kCommentActivityKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kCommentActivityKeyPrefix.size());
  *server_comment_id = key.ToString();
  return true;
}

bool DecodeEpisodeActivityKey(
    Slice key, string* server_episode_id, int64_t* activity_id) {
  if (!key.starts_with(kEpisodeActivityKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kEpisodeActivityKeyPrefix.size());
  int slash_pos = key.find('/');
  if (slash_pos == -1) {
    return false;
  }
  *server_episode_id = key.substr(0, slash_pos).ToString();
  key.remove_prefix(slash_pos + 1);
  *activity_id = OrderedCodeDecodeVarint64(&key);
  return true;
}

bool DecodeQuarantinedActivityKey(Slice key, int64_t* activity_id) {
  if (!key.starts_with(kQuarantinedActivityKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kQuarantinedActivityKeyPrefix.size());
  *activity_id = OrderedCodeDecodeVarint64(&key);
  return true;
}

bool DecodeViewpointActivityKey(
    Slice key, int64_t* viewpoint_id, WallTime* timestamp, int64_t* activity_id) {
  if (!key.starts_with(kViewpointActivityKeyPrefix)) {
    return false;
  } else {
    key.remove_prefix(kViewpointActivityKeyPrefix.size());
  }
  *viewpoint_id = OrderedCodeDecodeVarint64(&key);
  *timestamp = OrderedCodeDecodeVarint32(&key);
  *activity_id = OrderedCodeDecodeVarint64(&key);
  return true;
}


////
// Activity

ActivityTable_Activity::ActivityTable_Activity(
    AppState* state, const DBHandle& db, int64_t id)
    : state_(state),
      db_(db),
      disk_timestamp_(0) {
  mutable_activity_id()->set_local_id(id);
}

void ActivityTable_Activity::MergeFrom(const ActivityMetadata& m) {
  // Clear out existing activity so merge doesn't accrete duplicate content.
  // NOTE: add activities here as they're added to the protobuf.
  clear_add_followers();
  clear_merge_accounts();
  clear_post_comment();
  clear_save_photos();
  clear_share_new();
  clear_share_existing();
  clear_unshare();
  clear_update_episode();
  clear_update_viewpoint();
  clear_upload_episode();

  // Some assertions that immutable properties of the activity don't change.
  if (has_timestamp() && m.has_timestamp()) {
    DCHECK_LT(fabs(timestamp() - m.timestamp()), 1e-6);
  }
  if (viewpoint_id().has_server_id() && m.viewpoint_id().has_server_id()) {
    DCHECK_EQ(viewpoint_id().server_id(), m.viewpoint_id().server_id());
  }
  if (has_user_id() && m.has_user_id()) {
    DCHECK_EQ(user_id(), m.user_id());
  }

  ActivityMetadata::MergeFrom(m);
}

void ActivityTable_Activity::MergeFrom(const ::google::protobuf::Message&) {
  DIE("MergeFrom(Message&) should not be used");
}

bool ActivityTable_Activity::FilterShare(
    const PhotoSelectionSet& selection, const DBHandle& updates) {
  DCHECK(provisional());
  if (!provisional()) {
    return false;
  }
  if (!has_share_new() && !has_share_existing()) {
    return false;
  }

  // Loop over the photos for the share and remove any that are no longer part
  // of the selection. We maintain the existing order by building up a new
  // ShareExisting activity from the old one.
  ShareEpisodes old_share_episodes;
  ShareEpisodes new_share_episodes;
  if (has_share_new()) {
    old_share_episodes.Swap(mutable_share_new()->mutable_episodes());
  } else if (has_share_existing()) {
    old_share_episodes.Swap(mutable_share_existing()->mutable_episodes());
  }

  for (int i = 0; i < old_share_episodes.size(); ++i) {
    const ActivityMetadata::Episode& old_episode = old_share_episodes.Get(i);
    ActivityMetadata::Episode* new_episode = NULL;
    const EpisodeId& episode_id = old_episode.episode_id();
    EpisodeHandle eh;

    for (int j = 0; j < old_episode.photo_ids_size(); ++j) {
      const PhotoId& photo_id = old_episode.photo_ids(j);
      const PhotoSelection key(photo_id.local_id(), episode_id.local_id());
      if (!ContainsKey(selection, key)) {
        // The photo is not part of the selection and should be removed from
        // the episode. It is removed from the activity by simply not copying
        // it to the new share activity.
        if (!eh.get()) {
          eh = state_->episode_table()->LoadEpisode(episode_id, updates);
          eh->Lock();
        }
        if (eh.get()) {
          eh->RemovePhoto(photo_id.local_id());
        }
        continue;
      }

      if (!new_episode) {
        new_episode = new_share_episodes.Add();
        new_episode->mutable_episode_id()->CopyFrom(episode_id);
      }
      new_episode->add_photo_ids()->CopyFrom(photo_id);
    }

    if (eh.get()) {
      // Delete the episode/activity index key.
      updates->Delete(EncodeEpisodeActivityKey(episode_id.server_id(), local_id()));
      eh->SaveAndUnlock(updates);
    }
  }

  if (has_share_new()) {
    if (new_share_episodes.size() == 0) {
      if (share_new().contacts_size() == 0) {
        clear_share_new();
      }
      return false;
    }
    mutable_share_new()->mutable_episodes()->Swap(&new_share_episodes);
  } else if (has_share_existing()) {
    if (new_share_episodes.size() == 0) {
      clear_share_existing();
      return false;
    }
    mutable_share_existing()->mutable_episodes()->Swap(&new_share_episodes);
  }
  return true;
}

string ActivityTable_Activity::FormatName(bool shorten) {
  if (shorten) {
    return state_->contact_manager()->FirstName(user_id());
  } else {
    return state_->contact_manager()->FullName(user_id());
  }
}

string ActivityTable_Activity::FormatTimestamp(bool shorten) {
  // TODO(spencer): need a shortened version of the relative time method.
  return FormatRelativeTime(timestamp(), state_->WallTime_Now());
}

string ActivityTable_Activity::FormatShareContent(
    const ViewpointSummaryMetadata::ActivityRow* activity_row, bool shorten) {
  int count = 0;
  vector<EpisodeHandle> episodes;

  // Use the activity row photos if possible; otherwise, use activity episodes.
  if (activity_row) {
    std::unordered_set<int64_t> unique_episode_ids;
    for (int i = 0; i < activity_row->photos_size(); ++i) {
      ++count;
      const int64_t episode_id = activity_row->photos(i).episode_id();
      if (ContainsKey(unique_episode_ids, episode_id)) {
        continue;
      }
      unique_episode_ids.insert(episode_id);
      EpisodeHandle eh = state_->episode_table()->LoadEpisode(episode_id, db_);
      if (eh.get()) {
        episodes.push_back(eh);
      }
    }
  } else {
    const ShareEpisodes* share_episodes = GetShareEpisodes();
    for (int i = 0; i < share_episodes->size(); ++i) {
      count += share_episodes->Get(i).photo_ids_size();
      EpisodeHandle eh =
          state_->episode_table()->LoadEpisode(share_episodes->Get(i).episode_id(), db_);
      if (eh.get()) {
        episodes.push_back(eh);
      }
    }
  }

  string long_loc_str;
  string first_loc_str;
  std::unordered_set<string> unique_loc_strs;
  for (int i = 0; i < episodes.size(); ++i) {
    Location location;
    Placemark placemark;
    EpisodeHandle eh = episodes[i];
    if (eh->GetLocation(&location, &placemark) &&
        (placemark.has_sublocality() ||
         placemark.has_locality() ||
         placemark.has_state() ||
         placemark.has_country())) {
      if (long_loc_str.empty()) {
        state_->placemark_histogram()->FormatLocation(
            location, placemark, shorten, &long_loc_str);
      }
      string short_loc_str;
      state_->placemark_histogram()->FormatLocation(
          location, placemark, true, &short_loc_str);
      if (!short_loc_str.empty()) {
        if (first_loc_str.empty()) {
          first_loc_str = short_loc_str;
        }
        unique_loc_strs.insert(short_loc_str);
      }
    }
  }

  if (unique_loc_strs.empty() && count > 0) {
    return Format("%d photo%s without location%s",
                  count, Pluralize(count), Pluralize(count));
  } else if (unique_loc_strs.size() == 1) {
    DCHECK(!long_loc_str.empty());
    return ToUppercase(long_loc_str);
  } else {
    return Format("%s and %d other location%s", ToUppercase(first_loc_str),
                  unique_loc_strs.size() - 1, Pluralize(unique_loc_strs.size() - 1));
  }
}

string ActivityTable_Activity::FormatContent(
    const ViewpointSummaryMetadata::ActivityRow* activity_row, bool shorten) {
  if (has_share_new() || has_share_existing()) {
    return FormatShareContent(activity_row, shorten);
  } else if (has_post_comment()) {
    CommentHandle ch = state_->comment_table()->LoadComment(
        post_comment().comment_id(), db_);
    if (ch.get()) {
      if (shorten) {
        const string normalized = NormalizeWhitespace(ch->message());
        if (normalized.length() <= kMaxContentLength) {
          // Optimization: the byte length of a string is never more than its character length, so
          // if we have less than kMaxContentLength bytes we can skip the character counting.
          return normalized.empty() ? " " : normalized;
        } else {
          const string truncated = TruncateUTF8(ch->message(), kMaxContentLength);
          if (truncated.length() == ch->message().length()) {
            // If the message contains multi-byte characters it may not have actually needed truncation.
            return truncated;
          } else {
            // If it did, remove any now-trailing whitespace (using the more efficient Trim since
            // the previous NormalizeWhitespace got rid of any non-ascii whitespace) and add an
            // ellipsis.
            return Trim(truncated) + "…";
          }
        }
      }
      const string trimmed = Trim(ch->message());
      return trimmed.empty() ? " " : trimmed;
    } else {
      return " ";
    }
  } else if (has_save_photos()) {
    return Format("%saved photos", shorten ? "S" : "s");
  } else if (has_update_episode()) {
    // TODO(spencer): need something better here.
    return Format("%spdated episode", shorten ? "U" : "u");
  } else if (has_update_viewpoint()) {
    // TODO(spencer): need something better here.
    return Format("%spdated conversation", shorten ? "U" : "u");
  } else if (has_add_followers()) {
    const bool more_than_one_follower = add_followers().contacts_size() > 1;
    vector<string> followers;
    for (int i = 0; i < add_followers().contacts_size(); ++i) {
      if (add_followers().contacts(i).has_user_id()) {
        const int64_t user_id = add_followers().contacts(i).user_id();
        if (more_than_one_follower) {
          followers.push_back(state_->contact_manager()->FirstName(user_id));
        } else {
          followers.push_back(state_->contact_manager()->FullName(user_id));
        }
      } else {
        followers.push_back(ContactManager::FormatName(
                                add_followers().contacts(i),
                                more_than_one_follower));
      }
    }
    if (shorten) {
      if (followers.size() > 3) {
        // Display 3 names max.
        followers.resize(4);
        followers[4] = "\u2026";
      }
      return Format("Added %s", Join(followers, ", "));
    } else {
      if (followers.size() > 1) {
        string name_str = Join(
            followers.begin(), followers.begin() + followers.size() - 1, ", ");
        return Format("added %s and %s", name_str, followers.back());
      } else if (followers.size() == 1) {
        return Format("added %s", followers[0]);
      }
    }
  }

  LOG("activity contents not formatted %s", *this);
  return "";
}

WallTime ActivityTable_Activity::GetViewedTimestamp() const {
  // If viewed timestamp isn't set, try reloading it from database.
  if (!has_viewed_timestamp()) {
    ActivityHandle ah = state_->activity_table()->LoadActivity(
        activity_id().local_id(), state_->db());
    return ah->viewed_timestamp();
  }
  return viewed_timestamp();
}

bool ActivityTable_Activity::IsUpdate() const {
  return has_add_followers() || has_update_viewpoint() || has_unshare();
}

bool ActivityTable_Activity::IsVisible() const {
  // Skip certain uninteresting (or unsupported) activities as well
  // as quarantined activities.
  if (has_update_viewpoint() ||
      has_update_episode() ||
      has_upload_episode() ||
      has_unshare()) {
    return false;
  }
  // Ignore quarantined activities.
  if (label_error()) {
    return false;
  }
  // Ignore empty activities.
  if (has_add_followers() && !add_followers().contacts_size()) {
    return false;
  }
  return true;
}

const ShareEpisodes* ActivityTable_Activity::GetShareEpisodes() {
  if (has_share_new()) {
    return &share_new().episodes();
  } else if (has_share_existing()) {
    return &share_existing().episodes();
  } else if (has_save_photos()) {
    return &save_photos().episodes();
  } else if (has_unshare()) {
    return &unshare().episodes();
  }
  return NULL;
}

bool ActivityTable_Activity::Load() {
  disk_timestamp_ = timestamp();
  return true;
}

void ActivityTable_Activity::SaveHook(const DBHandle& updates) {
  if (viewpoint_id().has_local_id() && has_timestamp()) {
    updates->Put(EncodeViewpointActivityKey(
                     viewpoint_id().local_id(), timestamp(), local_id()), "");
  }
  // Build secondary index for episodes added by this activity.
  // These are used to build EVENT trapdoors.
  if (has_share_new() || has_share_existing()) {
    DCHECK(activity_id().has_server_id());
    const ShareEpisodes* episodes = GetShareEpisodes();
    for (int i = 0; i < episodes->size(); ++i) {
      updates->Put(EncodeEpisodeActivityKey(
                       episodes->Get(i).episode_id().server_id(), local_id()), "");
      // Invalidate the episode if the activity pointing to it changed.
      EpisodeHandle eh = state_->episode_table()->LoadEpisode(
          episodes->Get(i).episode_id(), updates);
      if (eh.get()) {
        state_->day_table()->InvalidateEpisode(eh, updates);
      }

      if (!provisional()) {
        // If the activity is not provisional, mark each of its photos as
        // "shared".
        const Episode& e = episodes->Get(i);
        for (int j = 0; j < e.photo_ids_size(); ++j) {
          PhotoHandle ph = state_->photo_table()->LoadPhoto(e.photo_ids(j), updates);
          if (ph.get() && !ph->shared()) {
            ph->Lock();
            ph->set_shared(true);
            ph->SaveAndUnlock(updates);
          }
        }
      }
    }
  } else if (has_post_comment()) {
    // Build secondary index for comment -> activity so we can
    // invalidate an activity when the comment is saved.
    updates->Put<int64_t>(EncodeCommentActivityKey(
                              post_comment().comment_id().server_id()), local_id());
  }
  if (has_timestamp()) {
    updates->Put(EncodeActivityTimestampKey(timestamp(), local_id()), "");
  }

  // If the error label is set, add activity to the unquarantined index.
  const string quarantined_key = EncodeQuarantinedActivityKey(local_id());
  if (label_error()) {
    updates->Put(quarantined_key, "");
  } else if (updates->Exists(quarantined_key)) {
    updates->Delete(quarantined_key);
  }

  typedef ContentTable<ActivityTable_Activity>::Content Content;
  ActivityHandle ah(reinterpret_cast<Content*>(this));

  // Notice if the timestamp has changed and delete old index entries.
  if (disk_timestamp_ != timestamp()) {
    if (disk_timestamp_ > 0) {
      updates->Delete(EncodeViewpointActivityKey(
                          viewpoint_id().local_id(), disk_timestamp_, local_id()));
      updates->Delete(EncodeActivityTimestampKey(disk_timestamp_, local_id()));

      // In the event that the timestamp has changed by more than a
      // day, we must invalidate the day table for this activity using
      // the prior timestamp. It's easiest if we revert the timestamp
      // temporarily and then swap correct value back in.
      const double new_timestamp = ah->timestamp();
      ah->set_timestamp(disk_timestamp_);
      state_->day_table()->InvalidateActivity(ah, updates);
      ah->set_timestamp(new_timestamp);
    }
    disk_timestamp_ = timestamp();
  }

  // Ugh, ActivityTable_Activity is the base class but ActivityHandle needs a
  // pointer to the superclass.
  state_->net_queue()->QueueActivity(ah, updates);

  // Invalidate this activity.
  state_->day_table()->InvalidateActivity(ah, updates);
}

void ActivityTable_Activity::DeleteHook(const DBHandle& updates) {
  if (viewpoint_id().has_local_id() && has_timestamp()) {
    updates->Delete(EncodeViewpointActivityKey(
                        viewpoint_id().local_id(), timestamp(), local_id()));
  }

  if (has_share_new() || has_share_existing()) {
    DCHECK(activity_id().has_server_id());
    const ShareEpisodes* episodes = GetShareEpisodes();
    for (int i = 0; i < episodes->size(); ++i) {
      updates->Delete(EncodeEpisodeActivityKey(
                          episodes->Get(i).episode_id().server_id(), local_id()));
      // Delete the episode.
      EpisodeHandle eh = state_->episode_table()->LoadEpisode(
          episodes->Get(i).episode_id(), updates);
      if (eh.get()) {
        eh->Lock();
        eh->DeleteAndUnlock(updates);
      }
    }
  } else if (has_post_comment()) {
    CommentHandle ch = state_->comment_table()->LoadComment(
        post_comment().comment_id(), updates);
    if (ch.get()) {
      ch->Lock();
      ch->DeleteAndUnlock(updates);
      updates->Delete(EncodeCommentActivityKey(ch->comment_id().server_id()));
    }
  }
  if (has_timestamp()) {
    updates->Delete(EncodeActivityTimestampKey(timestamp(), local_id()));
  }

  // Delete quarantined marker.
  updates->Delete(EncodeQuarantinedActivityKey(local_id()));

  // Dequeue and invalidate this activity.
  typedef ContentTable<ActivityTable_Activity>::Content Content;
  ActivityHandle ah(reinterpret_cast<Content*>(this));
  state_->net_queue()->DequeueActivity(ah, updates);
  state_->day_table()->InvalidateActivity(ah, updates);
}


////
// ActivityIterator

ActivityTable::ActivityIterator::ActivityIterator(
    ActivityTable* table, bool reverse, const DBHandle& db)
    : ActivityTable::ContentIterator(db->NewIterator(), reverse),
      table_(table),
      db_(db),
      cur_activity_id_(0),
      cur_timestamp_(0) {
}

ActivityTable::ActivityIterator::~ActivityIterator() {
}

ActivityHandle ActivityTable::ActivityIterator::GetActivity() {
  if (done()) {
    return ActivityHandle();
  }
  return table_->LoadContent(cur_activity_id_, db_);
}


////
// ActivityTable

ActivityTable::ActivityTable(AppState* state)
    : ContentTable<Activity>(state,
                             DBFormat::activity_key(),
                             DBFormat::activity_server_key(),
                             kActivityFSCKVersion,
                             DBFormat::metadata_key("activity_table_fsck")) {
}

ActivityTable::~ActivityTable() {
}

ActivityHandle ActivityTable::GetLatestActivity(
    int64_t viewpoint_id, const DBHandle& db) {
  ScopedPtr<ActivityTable::ActivityIterator> vp_iter(
      NewViewpointActivityIterator(viewpoint_id, std::numeric_limits<int32_t>::max(), true, db));
  if (!vp_iter->done()) {
    return vp_iter->GetActivity();
  }
  return ActivityHandle();
}

ActivityHandle ActivityTable::GetFirstActivity(
    int64_t viewpoint_id, const DBHandle& db) {
  ScopedPtr<ActivityTable::ActivityIterator> vp_iter(
      NewViewpointActivityIterator(viewpoint_id, 0, false, db));
  if (!vp_iter->done()) {
    return vp_iter->GetActivity();
  }
  return ActivityHandle();
}

ActivityHandle ActivityTable::GetCommentActivity(
    const string& comment_server_id, const DBHandle& db) {
  const string key = EncodeCommentActivityKey(comment_server_id);
  const int64_t activity_id = db->Get<int64_t>(key, -1);
  if (activity_id != -1) {
    return LoadActivity(activity_id, db);
  }
  return ActivityHandle();
}

void ActivityTable::ListEpisodeActivities(
    const string& episode_server_id, vector<int64_t>* activity_ids, const DBHandle& db) {
  for (DB::PrefixIterator iter(db, EncodeEpisodeActivityKeyPrefix(episode_server_id));
       iter.Valid();
       iter.Next()) {
    string dummy_episode_id;
    int64_t activity_id;
    if (DecodeEpisodeActivityKey(iter.key(), &dummy_episode_id, &activity_id)) {
      activity_ids->push_back(activity_id);
    }
  }
}

ActivityTable::ActivityIterator* ActivityTable::NewTimestampActivityIterator(
    WallTime start, bool reverse, const DBHandle& db) {
  return new TimestampActivityIterator(this, start, reverse, db);
}

ActivityTable::ActivityIterator* ActivityTable::NewViewpointActivityIterator(
    int64_t viewpoint_id, WallTime start, bool reverse, const DBHandle& db) {
  return new ViewpointActivityIterator(this, viewpoint_id, start, reverse, db);
}

bool ActivityTable::FSCK(
    bool force, ProgressUpdateBlock progress_update, const DBHandle& updates) {
  // Restart any quarantined activities.
  int unquarantine_count = 0;
  for (DB::PrefixIterator iter(updates, kQuarantinedActivityKeyPrefix);
       iter.Valid();
       iter.Next()) {
    ++unquarantine_count;
    int64_t activity_id;
    if (DecodeQuarantinedActivityKey(iter.key(), &activity_id)) {
      ActivityHandle ah = LoadActivity(activity_id, updates);
      LOG("FSCK: unquarantined activity %s", ah->activity_id());
      ah->Lock();
      ah->clear_label_error();
      ah->SaveAndUnlock(updates);
    }
  }

  LOG("FSCK: unquarantined %d activities", unquarantine_count);
  return ContentTable<ActivityTable_Activity>::FSCK(force, progress_update, updates);
}

bool ActivityTable::FSCKImpl(int prev_fsck_version, const DBHandle& updates) {
  LOG("FSCK: ActivityTable");
  bool changes = false;
  if (FSCKActivity(updates)) {
    changes = true;
  }
  // Handle any duplicates in secondary indexes by timestamp. These can exist
  // as a result of a server bug which rounded up timestamps.
  if (FSCKActivityTimestampIndex(updates)) {
    changes = true;
  }
  if (FSCKViewpointActivityIndex(updates)) {
    changes = true;
  }
  return changes;
}

bool ActivityTable::FSCKActivity(const DBHandle& updates) {
  bool changes = false;
  for (DB::PrefixIterator iter(updates, DBFormat::activity_key());
       iter.Valid();
       iter.Next()) {
      const Slice key = iter.key();
      const Slice value = iter.value();
    ActivityMetadata am;
    if (am.ParseFromArray(value.data(), value.size())) {
      ActivityHandle ah = LoadActivity(am.activity_id().local_id(), updates);
      ah->Lock();
      bool save_ah = false;
      if (key != EncodeContentKey(DBFormat::activity_key(), am.activity_id().local_id())) {
        LOG("FSCK: activity id %d does not equal key %s; deleting key and re-saving",
            am.activity_id().local_id(), key);
        updates->Delete(key);
        save_ah = true;
      }

      // Check required fields.
      if (!ah->has_activity_id() ||
          (!ah->has_save_photos() && !ah->has_viewpoint_id()) ||
          !ah->has_user_id() ||
          !ah->has_timestamp()) {
        LOG("FSCK: activity missing required fields: %s", *ah);
      }

      // Check viewpoint; lookup first by server id.
      if (ah->viewpoint_id().has_server_id()) {
        ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
            ah->viewpoint_id().server_id(), updates);
        bool invalidate_viewpoint = false;
        if (!vh.get()) {
          LOG("FSCK: missing viewpoint %s; setting invalidation", ah->viewpoint_id());
          invalidate_viewpoint = true;
        } else if (vh->id().local_id() != ah->viewpoint_id().local_id()) {
          LOG("FSCK: viewpoint local id mismatch; %d != %d; resetting and clearing secondary indexes",
              vh->id().local_id(), ah->viewpoint_id().local_id());
          if (ah->viewpoint_id().has_local_id() && ah->has_timestamp()) {
            const string vp_activity_key = EncodeViewpointActivityKey(
                ah->viewpoint_id().local_id(), ah->timestamp(), ah->activity_id().local_id());
            updates->Delete(vp_activity_key);
          }
          if (ah->has_share_new() || ah->has_share_existing()) {
            const ShareEpisodes* episodes = ah->GetShareEpisodes();
            for (int i = 0; i < episodes->size(); ++i) {
              const string episode_key = EncodeEpisodeActivityKey(
                  episodes->Get(i).episode_id().server_id(), ah->activity_id().local_id());
              updates->Delete(episode_key);
            }
          }
          if (ah->has_post_comment()) {
            const string comment_activity_key = EncodeCommentActivityKey(
                ah->post_comment().comment_id().server_id());
            updates->Delete(comment_activity_key);
          }
          if (ah->has_timestamp()) {
            const string ts_activity_key = EncodeActivityTimestampKey(
                ah->timestamp(), ah->activity_id().local_id());
            updates->Delete(ts_activity_key);
          }
          // Clear quarantined key (if it exists).
          const string quarantined_key =
              EncodeQuarantinedActivityKey(ah->activity_id().local_id());
          updates->Delete(quarantined_key);

          ah->mutable_viewpoint_id()->clear_local_id();
          save_ah = true;
        } else if (ah->update_seq() > vh->update_seq()) {
          LOG("FSCK: encountered an activity with update_seq > viewpoint; "
              "activity: %s, viewpoint: %s", *ah, *vh);
          invalidate_viewpoint = true;
        }

        if (invalidate_viewpoint) {
          state_->viewpoint_table()->InvalidateFull(ah->viewpoint_id().server_id(), updates);
          changes = true;
        }
      }
      if (ah->viewpoint_id().has_server_id() && !ah->viewpoint_id().has_local_id()) {
        LOG("FSCK: activity has server id %s but no local id; canonicalizing",
            ah->viewpoint_id().server_id());
        state_->viewpoint_table()->CanonicalizeViewpointId(ah->mutable_viewpoint_id(), updates);
        save_ah = true;
      }

      // Check secondary indexes.
      if (ah->viewpoint_id().has_local_id() && ah->has_timestamp()) {
        const string vp_activity_key = EncodeViewpointActivityKey(
            ah->viewpoint_id().local_id(), ah->timestamp(), ah->activity_id().local_id());
        if (!updates->Exists(vp_activity_key)) {
          LOG("FSCK: missing viewpoint activity key");
          save_ah = true;
        }
      }
      if (ah->has_timestamp()) {
        const string ts_activity_key = EncodeActivityTimestampKey(
            ah->timestamp(), ah->activity_id().local_id());
        if (!updates->Exists(ts_activity_key)) {
          LOG("FSCK: missing timestamp activity key");
          save_ah = true;
        }
      }
      if (ah->has_share_new() || ah->has_share_existing()) {
        DCHECK(ah->activity_id().has_server_id());
        const ShareEpisodes* episodes = ah->GetShareEpisodes();
        for (int i = 0; i < episodes->size(); ++i) {
          const string episode_key = EncodeEpisodeActivityKey(
              episodes->Get(i).episode_id().server_id(), ah->activity_id().local_id());
          if (!updates->Exists(episode_key)) {
            LOG("FSCK: missing episode activity key");
            save_ah = true;
          }
        }
      }
      if (ah->has_post_comment()) {
        const string comment_activity_key = EncodeCommentActivityKey(
            ah->post_comment().comment_id().server_id());
        if (!updates->Exists(comment_activity_key)) {
          LOG("FSCK: missing comment activity key");
          save_ah = true;
        }
      }
      if (ah->label_error()) {
        const string quarantined_key =
            EncodeQuarantinedActivityKey(ah->activity_id().local_id());
        if (!updates->Exists(quarantined_key)) {
          LOG("FSCK: missing quarantined key for quarantined activity");
          save_ah = true;
        }
      }

      if (ah->upload_activity() && !ah->provisional()) {
        // Re-save any non-uploaded activity to force it to be re-added to
        // the network queue.
        LOG("FSCK: re-saving non-uploaded activity");
        save_ah = true;
      }

      if (save_ah) {
        LOG("FSCK: rewriting activity %s", *ah);
        ah->SaveAndUnlock(updates);
        changes = true;
      } else {
        ah->Unlock();
      }
    }
  }

  return changes;
}

bool ActivityTable::FSCKActivityTimestampIndex(const DBHandle& updates) {
  // Map from activity id to secondary index key.
  std::unordered_map<int64_t, string>* activity_ids(
      new std::unordered_map<int64_t, string>);
  bool changes = false;

  for (DB::PrefixIterator iter(updates, kActivityTimestampKeyPrefix);
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    WallTime timestamp;
    int64_t activity_id;
    if (!DecodeActivityTimestampKey(key, &timestamp, &activity_id)) {
      LOG("FSCK: unreadable activity timestamp secondary index: %s", key);
      updates->Delete(key);
      changes = true;
    } else {
      if (ContainsKey(*activity_ids, activity_id)) {
        LOG("FSCK: activity timestamp secondary index contains duplicate entries for %d; "
            "deleting earlier instance (%s)", activity_id, (*activity_ids)[activity_id]);
        updates->Delete((*activity_ids)[activity_id]);
        changes = true;
      }
      (*activity_ids)[activity_id] = ToString(key);
    }
  }

  delete activity_ids;
  return changes;
}

bool ActivityTable::FSCKViewpointActivityIndex(const DBHandle& updates) {
  // Map from activity id to secondary index key.
  std::unordered_map<int64_t, string>* activity_ids(
      new std::unordered_map<int64_t, string>);
  bool changes = false;

  for (DB::PrefixIterator iter(updates,kViewpointActivityKeyPrefix);
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    int64_t viewpoint_id;
    WallTime timestamp;
    int64_t activity_id;
    if (!DecodeViewpointActivityKey(key, &viewpoint_id, &timestamp, &activity_id)) {
      LOG("FSCK: unreadable activity timestamp secondary index: %s", key);
      updates->Delete(key);
      changes = true;
    } else {
      if (ContainsKey(*activity_ids, activity_id)) {
        LOG("FSCK: activity timestamp secondary index contains duplicate entries for %d; "
            "deleting earlier instance (%s)", activity_id, (*activity_ids)[activity_id]);
        updates->Delete((*activity_ids)[activity_id]);
        changes = true;
      }
      (*activity_ids)[activity_id] = ToString(key);
    }
  }

  delete activity_ids;
  return changes;
}

const ActivityTable::ContactArray* ActivityTable::GetActivityContacts(
    const ActivityMetadata& m) {
  if (m.has_share_new()) {
    return &m.share_new().contacts();
  }
  if (m.has_add_followers()) {
    return &m.add_followers().contacts();
  }
  return NULL;
}

// local variables:
// mode: c++
// end:
