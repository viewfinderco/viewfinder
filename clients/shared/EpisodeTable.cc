// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AppState.h"
#import "ContactManager.h"
#import "DayTable.h"
#import "EpisodeTable.h"
#import "FullTextIndex.h"
#import "LazyStaticPtr.h"
#import "LocationUtils.h"
#import "NetworkQueue.h"
#import "PlacemarkHistogram.h"
#import "STLUtils.h"
#import "StringUtils.h"
#import "Timer.h"
#import "WallTime.h"

namespace {

const int kEpisodeFSCKVersion = 7;

const string kEpisodeParentChildKeyPrefix = DBFormat::episode_parent_child_key(string());
const string kEpisodePhotoKeyPrefix = DBFormat::episode_photo_key(string());
const string kEpisodeSelectionKeyPrefix = DBFormat::episode_selection_key(string());
const string kEpisodeStatsKey = DBFormat::metadata_key("episode_stats");
const string kEpisodeTimestampKeyPrefix = DBFormat::episode_timestamp_key(string());
const string kPhotoEpisodeKeyPrefix = DBFormat::photo_episode_key(string());

const string kEpisodeIndexName = "ep";
const string kLocationIndexName = "epl";

const double kMaxTimeDist = 60 * 60;      // 1 hour
const double kMaxLocDist = 10000;         // 10 km

const DBRegisterKeyIntrospect kEpisodeKeyIntrospect(
    DBFormat::episode_key(), NULL, [](Slice value) {
      return DBIntrospect::FormatProto<EpisodeMetadata>(value);
    });

const DBRegisterKeyIntrospect kEpisodeServerKeyIntrospect(
    DBFormat::episode_server_key(), NULL, [](Slice value) {
      return value.ToString();
    });

const DBRegisterKeyIntrospect kEpisodeParentChildKeyIntrospect(
    kEpisodeParentChildKeyPrefix,
    [](Slice key) {
      int64_t parent_id;
      int64_t child_id;
      if (!DecodeEpisodeParentChildKey(key, &parent_id, &child_id)) {
        return string();
      }
      return string(Format("%d/%d", parent_id, child_id));
    },
    [](Slice value) {
      return value.ToString();
    });

const DBRegisterKeyIntrospect kEpisodePhotoKeyIntrospect(
    kEpisodePhotoKeyPrefix,
    [](Slice key) {
      int64_t episode_id;
      int64_t photo_id;
      if (!DecodeEpisodePhotoKey(key, &episode_id, &photo_id)) {
        return string();
      }
      return string(Format("%d/%d", episode_id, photo_id));
    },
    [](Slice value) {
      return value.ToString();
    });

const DBRegisterKeyIntrospect kPhotoEpisodeKeyIntrospect(
    kPhotoEpisodeKeyPrefix, [](Slice key) {
      int64_t photo_id;
      int64_t episode_id;
      if (!DecodePhotoEpisodeKey(key, &photo_id, &episode_id)) {
        return string();
      }
      return string(Format("%d/%d", photo_id, episode_id));
    }, NULL);

const DBRegisterKeyIntrospect kEpisodeSelectionKeyIntrospect(
    kEpisodeSelectionKeyPrefix, NULL, [](Slice value) {
      return DBIntrospect::FormatProto<EpisodeSelection>(value);
    });

const DBRegisterKeyIntrospect kEpisodeTimestampKeyIntrospect(
    kEpisodeTimestampKeyPrefix , [](Slice key) {
      WallTime timestamp;
      int64_t episode_id;
      if (!DecodeEpisodeTimestampKey(key, &timestamp, &episode_id)) {
        return string();
      }
      return string(
          Format("%s/%d", DBIntrospect::timestamp(timestamp), episode_id));
    }, NULL);

class QueryRewriter : public FullTextQueryVisitor {
 public:
  QueryRewriter(AppState* state)
      : state_(state) {
  }

  FullTextQuery* ParseAndRewrite(const Slice& query) {
    ScopedPtr<FullTextQuery> parsed_query(FullTextQuery::Parse(query));
    stack_.push_back(Accumulator());
    VisitNode(*parsed_query);
    CHECK_EQ(stack_.size(), 1);
    CHECK_EQ(stack_[0].size(), 1);
    return stack_[0][0];
  }

  void VisitTermNode(const FullTextQueryTermNode& node) {
    vector<FullTextQuery*> terms;
    terms.push_back(new FullTextQueryTermNode(node));
    AddContactTerms(node.term(), false, &terms);
    stack_.back().push_back(new FullTextQueryOrNode(terms));
  }

  void VisitPrefixNode(const FullTextQueryPrefixNode& node) {
    vector<FullTextQuery*> terms;
    terms.push_back(new FullTextQueryPrefixNode(node));
    AddContactTerms(node.prefix(), true, &terms);
    stack_.back().push_back(new FullTextQueryOrNode(terms));
  }

  void VisitParentNode(const FullTextQueryParentNode& node) {
    stack_.push_back(Accumulator());
    VisitChildren(node);
    FullTextQuery* new_node;
    if (node.type() == FullTextQuery::AND) {
      new_node = new FullTextQueryAndNode(stack_.back());
    } else {
      new_node = new FullTextQueryOrNode(stack_.back());
    }
    stack_.pop_back();
    stack_.back().push_back(new_node);
  }

 private:
  void AddContactTerms(const string& query, bool prefix, vector<FullTextQuery*>* terms) {
    // Rewrite each term to its union with any matching contact entries.
    vector<ContactMetadata> contact_results;
    int options = ContactManager::SORT_BY_NAME | ContactManager::VIEWFINDER_USERS_ONLY;
    if (prefix) {
      options |= ContactManager::PREFIX_MATCH;
    }
    state_->contact_manager()->Search(query, &contact_results, NULL, options);
    for (const ContactMetadata& c : contact_results) {
      // Even if the underlying query is in prefix mode, the resulting tokens are always exact matches.
      terms->push_back(new FullTextQueryTermNode(ContactManager::FormatUserToken(c.user_id())));
    }
  }

  AppState* state_;

  typedef vector<FullTextQuery*> Accumulator;
  vector<Accumulator> stack_;
};

}  // namespace

string EncodeEpisodePhotoKey(int64_t episode_id, int64_t photo_id) {
  string s;
  OrderedCodeEncodeInt64Pair(&s, episode_id, photo_id);
  return DBFormat::episode_photo_key(s);
}

string EncodePhotoEpisodeKey(int64_t photo_id, int64_t episode_id) {
  string s;
  OrderedCodeEncodeInt64Pair(&s, photo_id, episode_id);
  return DBFormat::photo_episode_key(s);
}

string EncodeEpisodeTimestampKey(WallTime timestamp, int64_t episode_id) {
  string s;
  OrderedCodeEncodeVarint32(&s, timestamp);
  OrderedCodeEncodeVarint64(&s, episode_id);
  return DBFormat::episode_timestamp_key(s);
}

string EncodeEpisodeParentChildKey(int64_t parent_id, int64_t child_id) {
  string s;
  OrderedCodeEncodeInt64Pair(&s, parent_id, child_id);
  return DBFormat::episode_parent_child_key(s);
}

bool DecodeEpisodePhotoKey(Slice key, int64_t* episode_id, int64_t* photo_id) {
  if (!key.starts_with(kEpisodePhotoKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kEpisodePhotoKeyPrefix.size());
  OrderedCodeDecodeInt64Pair(&key, episode_id, photo_id);
  return true;
}

bool DecodePhotoEpisodeKey(Slice key, int64_t* photo_id, int64_t* episode_id) {
  if (!key.starts_with(kPhotoEpisodeKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kPhotoEpisodeKeyPrefix.size());
  OrderedCodeDecodeInt64Pair(&key, photo_id, episode_id);
  return true;
}

bool DecodeEpisodeTimestampKey(
    Slice key, WallTime* timestamp, int64_t* episode_id) {
  if (!key.starts_with(kEpisodeTimestampKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kEpisodeTimestampKeyPrefix.size());
  *timestamp = OrderedCodeDecodeVarint32(&key);
  *episode_id = OrderedCodeDecodeVarint64(&key);
  return true;
}

bool DecodeEpisodeParentChildKey(Slice key, int64_t* parent_id, int64_t* child_id) {
  if (!key.starts_with(kEpisodeParentChildKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kEpisodeParentChildKeyPrefix.size());
  OrderedCodeDecodeInt64Pair(&key, parent_id, child_id);
  return true;
}


////
// EpisodeTable_Episode

EpisodeTable_Episode::EpisodeTable_Episode(AppState* state, const DBHandle& db, int64_t id)
    : state_(state),
      db_(db),
      additions_(0),
      hiddens_(0),
      quarantines_(0),
      removals_(0),
      unshares_(0),
      have_photo_state_(false),
      recompute_timestamp_range_(false),
      resolved_location_(false) {
  mutable_id()->set_local_id(id);
}

void EpisodeTable_Episode::MergeFrom(const EpisodeMetadata& m) {
  // Some assertions that immutable properties don't change.
  if (parent_id().has_server_id() && m.parent_id().has_server_id()) {
    DCHECK_EQ(parent_id().server_id(), m.parent_id().server_id());
  }
  if (viewpoint_id().has_server_id() && m.viewpoint_id().has_server_id()) {
    DCHECK_EQ(viewpoint_id().server_id(), m.viewpoint_id().server_id());
  }
  if (has_user_id() && m.has_user_id()) {
    DCHECK_EQ(user_id(), m.user_id());
  }

  EpisodeMetadata::MergeFrom(m);
}

void EpisodeTable_Episode::MergeFrom(const ::google::protobuf::Message&) {
  DIE("MergeFrom(Message&) should not be used");
}


int64_t EpisodeTable_Episode::GetDeviceId() const {
  if (!id().has_server_id()) {
    return state_->device_id();
  }
  int64_t device_id = 0;
  int64_t dummy_id = 0;
  WallTime dummy_timestamp = 0;
  DecodeEpisodeId(
      id().server_id(), &device_id, &dummy_id, &dummy_timestamp);
  return device_id;
}

int64_t EpisodeTable_Episode::GetUserId() const {
  return has_user_id() ? user_id() : state_->user_id();
}

void EpisodeTable_Episode::AddPhoto(int64_t photo_id) {
  PhotoState* s = NULL;
  if (photos_.get()) {
    s = FindPtrOrNull(photos_.get(), photo_id);
  }

  bool new_photo = false;
  if (!s && !have_photo_state_) {
    // Optimize the common case where photo state has not been
    // initialized. Load only the photo state for the photo being added.
    if (!photos_.get()) {
      photos_.reset(new PhotoStateMap);
    }
    const string value = db_->Get<string>(
        EncodeEpisodePhotoKey(id().local_id(), photo_id));
    if (!value.empty()) {
      s = &(*photos_)[photo_id];
      if (value == EpisodeTable::kHiddenValue) {
        *s = HIDDEN;
      } else if (value == EpisodeTable::kPostedValue) {
        *s = POSTED;
      } else if (value == EpisodeTable::kQuarantinedValue) {
        *s = QUARANTINED;
      } else if (value == EpisodeTable::kRemovedValue) {
        *s = REMOVED;
      } else if (value == EpisodeTable::kUnsharedValue) {
        *s = UNSHARED;
      } else {
        CHECK(false) << "unexpected value: " << value;
      }
    }
  }

  if (!s) {
    new_photo = true;
    additions_++;
    s = &(*photos_)[photo_id];
  } else if (*s == HIDDEN) {
    additions_++;
    hiddens_--;
  } else if (*s == QUARANTINED) {
    additions_++;
    quarantines_--;
  } else if (*s == REMOVED) {
    additions_++;
    removals_--;
  } else if (*s == UNSHARED) {
    additions_++;
    unshares_--;
  } else {
    CHECK_NE(*s, HIDE_PENDING) << "hidden pending";
    CHECK_NE(*s, QUARANTINE_PENDING) << "quarantine pending";
    CHECK_NE(*s, REMOVE_PENDING) << "remove pending";
    CHECK_NE(*s, UNSHARE_PENDING) << "unshare pending";
  }
  *s = POST_PENDING;

  // When a new photo is added we can incrementally update the timestamp
  // range. Otherwise, we have to recompute the timestamp range from scratch.
  if (!new_photo) {
    recompute_timestamp_range_ = true;
  }
}

void EpisodeTable_Episode::HidePhoto(int64_t photo_id) {
  MutexLock lock(&photos_mu_);
  EnsurePhotoState();
  PhotoState* s = FindPtrOrNull(photos_.get(), photo_id);
  if (s) {
    if (*s == POSTED) {
      additions_--;
      hiddens_++;
      *s = HIDE_PENDING;
    } else if (*s == QUARANTINED) {
      quarantines_--;
      hiddens_++;
      *s = HIDE_PENDING;
    } else if (*s == REMOVED) {
      removals_--;
      hiddens_++;
      *s = HIDE_PENDING;
    } else {
      CHECK_NE(*s, POST_PENDING) << "post pending";
      CHECK_NE(*s, QUARANTINE_PENDING) << "quarantine pending";
      CHECK_NE(*s, REMOVE_PENDING) << "remove pending";
      CHECK_NE(*s, UNSHARE_PENDING) << "unshare pending";
    }
  } else {
    // We've queried a photo as part of this episode which has been
    // removed. We still need to record it, but with state removed.
    hiddens_++;
    (*photos_)[photo_id] = HIDE_PENDING;
  }

  recompute_timestamp_range_ = true;
}

void EpisodeTable_Episode::QuarantinePhoto(int64_t photo_id) {
  MutexLock lock(&photos_mu_);
  EnsurePhotoState();
  PhotoState* s = FindPtrOrNull(photos_.get(), photo_id);
  if (s) {
    if (*s == HIDDEN) {
      quarantines_++;
      hiddens_--;
      *s = QUARANTINE_PENDING;
    } else if (*s == POSTED) {
      quarantines_++;
      additions_--;
      *s = QUARANTINE_PENDING;
    } else if (*s == REMOVED) {
      quarantines_++;
      removals_--;
      *s = QUARANTINE_PENDING;
    } else {
      CHECK_NE(*s, HIDE_PENDING) << "hidden pending";
      CHECK_NE(*s, POST_PENDING) << "post pending";
      CHECK_NE(*s, REMOVE_PENDING) << "remove pending";
      CHECK_NE(*s, UNSHARE_PENDING) << "unshare pending";
    }
  } else {
    // We've queried a photo as part of this episode which has been
    // removed. We still need to record it, but with state unshared.
    quarantines_++;
    (*photos_)[photo_id] = QUARANTINE_PENDING;
  }

  recompute_timestamp_range_ = true;
}

void EpisodeTable_Episode::RemovePhoto(int64_t photo_id) {
  MutexLock lock(&photos_mu_);
  EnsurePhotoState();
  PhotoState* s = FindPtrOrNull(photos_.get(), photo_id);
  if (s) {
    if (*s == HIDDEN) {
      hiddens_--;
      removals_++;
      *s = REMOVE_PENDING;
    } else if (*s == POSTED) {
      additions_--;
      removals_++;
      *s = REMOVE_PENDING;
    } else if (*s == QUARANTINED) {
      quarantines_--;
      removals_++;
      *s = REMOVE_PENDING;
    } else {
      CHECK_NE(*s, HIDE_PENDING) << "hidden pending";
      CHECK_NE(*s, POST_PENDING) << "post pending";
      CHECK_NE(*s, QUARANTINE_PENDING) << "quarantine pending";
      CHECK_NE(*s, UNSHARE_PENDING) << "unshare pending";
    }
  } else {
    // We've queried a photo as part of this episode which has been
    // removed. We still need to record it, but with state removed.
    removals_++;
    (*photos_)[photo_id] = REMOVE_PENDING;
  }

  recompute_timestamp_range_ = true;
}

void EpisodeTable_Episode::UnsharePhoto(int64_t photo_id) {
  MutexLock lock(&photos_mu_);
  EnsurePhotoState();
  PhotoState* s = FindPtrOrNull(photos_.get(), photo_id);
  if (s) {
    if (*s == HIDDEN) {
      hiddens_--;
      unshares_++;
      *s = UNSHARE_PENDING;
    } else if (*s == POSTED) {
      additions_--;
      unshares_++;
      *s = UNSHARE_PENDING;
    } else if (*s == QUARANTINED) {
      quarantines_--;
      unshares_++;
      *s = UNSHARE_PENDING;
    } else if (*s == REMOVED) {
      removals_--;
      unshares_++;
      *s = UNSHARE_PENDING;
    } else {
      CHECK_NE(*s, HIDE_PENDING) << "hidden pending";
      CHECK_NE(*s, POST_PENDING) << "post pending";
      CHECK_NE(*s, QUARANTINE_PENDING) << "quarantine pending";
      CHECK_NE(*s, REMOVE_PENDING) << "remove pending";
    }
  } else {
    // We've queried a photo as part of this episode which has been
    // removed. We still need to record it, but with state unshared.
    unshares_++;
    (*photos_)[photo_id] = UNSHARE_PENDING;
  }

  recompute_timestamp_range_ = true;
}

bool EpisodeTable_Episode::IsHidden(int64_t photo_id) {
  MutexLock lock(&photos_mu_);
  EnsurePhotoState();
  const PhotoState state = FindOrDefault(*photos_, photo_id, REMOVED);
  return (state == HIDDEN || state == HIDE_PENDING);
}

bool EpisodeTable_Episode::IsPosted(int64_t photo_id) {
  MutexLock lock(&photos_mu_);
  EnsurePhotoState();
  const PhotoState state = FindOrDefault(*photos_, photo_id, REMOVED);
  return (state == POSTED || state == POST_PENDING);
}

bool EpisodeTable_Episode::IsQuarantined(int64_t photo_id) {
  MutexLock lock(&photos_mu_);
  EnsurePhotoState();
  const PhotoState state = FindOrDefault(*photos_, photo_id, REMOVED);
  return (state == QUARANTINED || state == QUARANTINE_PENDING);
}

bool EpisodeTable_Episode::IsRemoved(int64_t photo_id) {
  MutexLock lock(&photos_mu_);
  EnsurePhotoState();
  const PhotoState state = FindOrDefault(*photos_, photo_id, REMOVED);
  return (state == REMOVED || state == REMOVE_PENDING);
}

bool EpisodeTable_Episode::IsUnshared(int64_t photo_id) {
  MutexLock lock(&photos_mu_);
  EnsurePhotoState();
  const PhotoState state = FindOrDefault(*photos_, photo_id, REMOVED);
  return (state == UNSHARED || state == UNSHARE_PENDING);
}

int EpisodeTable_Episode::CountPhotos() {
  MutexLock lock(&photos_mu_);
  EnsurePhotoState();
  int count = 0;
  for (PhotoStateMap::iterator iter(photos_->begin());
       iter != photos_->end();
       ++iter) {
    if (iter->second == POSTED || iter->second == POST_PENDING) {
      ++count;
    }
  }
  return count;
}

void EpisodeTable_Episode::ListPhotos(vector<int64_t>* photo_ids) {
  MutexLock lock(&photos_mu_);
  EnsurePhotoState();
  for (PhotoStateMap::iterator iter(photos_->begin());
       iter != photos_->end();
       ++iter) {
    const bool posted = (iter->second == POSTED || iter->second == POST_PENDING);
    if (posted) {
      photo_ids->push_back(iter->first);
    }
  }
}

void EpisodeTable_Episode::ListAllPhotos(vector<int64_t>* photo_ids) {
  MutexLock lock(&photos_mu_);
  EnsurePhotoState();
  for (PhotoStateMap::iterator iter(photos_->begin());
       iter != photos_->end();
       ++iter) {
    photo_ids->push_back(iter->first);
  }
}

void EpisodeTable_Episode::ListUnshared(vector<int64_t>* unshared_ids) {
  MutexLock lock(&photos_mu_);
  EnsurePhotoState();
  for (PhotoStateMap::iterator iter(photos_->begin());
       iter != photos_->end();
       ++iter) {
    if (iter->second == UNSHARED || iter->second == UNSHARE_PENDING) {
      unshared_ids->push_back(iter->first);
    }
  }
}

bool EpisodeTable_Episode::InLibrary() {
  if (!has_viewpoint_id()) {
    // If there's no viewpoint, user hasn't uploaded episode; always show.
    return true;
  }
  // Otherwise, show any episode which is part of the default viewpoint.
  ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(viewpoint_id(), db_);
  return vh.get() && vh->is_default();
}

bool EpisodeTable_Episode::GetTimeRange(
    WallTime* earliest, WallTime* latest) {
  if (!has_earliest_photo_timestamp() && !has_latest_photo_timestamp()) {
    return false;
  }
  *earliest = earliest_photo_timestamp();
  *latest = latest_photo_timestamp();
  return true;
}

bool EpisodeTable_Episode::GetLocation(Location* loc, Placemark* pm) {
  if (resolved_location_) {
    if (!location_.get()) {
      return false;
    }
    *loc = *location_;
    if (pm) {
      *pm = *placemark_;
    }
    return true;
  }
  resolved_location_ = true;
  location_.reset(new Location);
  placemark_.reset(new Placemark);

  vector<int64_t> photo_ids;
  ListPhotos(&photo_ids);
  for (int i = 0; i < photo_ids.size(); ++i) {
    PhotoHandle ph = state_->photo_table()->LoadPhoto(photo_ids[i], db_);
    if (ph.get() &&
        ph->GetLocation(location_.get(), placemark_.get())) {
      *loc = *location_;
      if (pm) {
        *pm = *placemark_;
      }
      return true;
    }
  }
  location_.reset(NULL);
  placemark_.reset(NULL);
  return false;
}

bool EpisodeTable_Episode::MaybeSetServerId() {
  const int64_t device_id = state_->device_id();
  if (id().has_server_id() || !device_id) {
    return false;
  }
  mutable_id()->set_server_id(
      EncodeEpisodeId(device_id, id().local_id(), timestamp()));
  return true;
}

string EpisodeTable_Episode::FormatLocation(bool shorten) {
  Location loc;
  Placemark pm;

  if (GetLocation(&loc, &pm)) {
    string loc_str;
    state_->placemark_histogram()->FormatLocation(loc, pm, shorten, &loc_str);
    return ToUppercase(loc_str);
  }
  return shorten ? "" : "Location Unavailable";
}

string EpisodeTable_Episode::FormatTimeRange(bool shorten, WallTime now) {
  WallTime earliest, latest;
  if (!GetTimeRange(&earliest, &latest)) {
    return "";
  }

  // If shorten is true, format just the earliest time.
  if (shorten) {
    return FormatRelativeTime(earliest, now == 0 ? earliest : now);
  }
  // Format a time range, using start of the day corresponding
  // to the latest time as "now". This results in the time
  // range being expressed as times only.
  return FormatDateRange(earliest, latest, now == 0 ? latest : now);
}

string EpisodeTable_Episode::FormatContributor(bool shorten) {
  if (!has_user_id() || user_id() == state_->user_id()) {
    return "";
  }
  if (shorten) {
    return state_->contact_manager()->FirstName(user_id());
  } else {
    return state_->contact_manager()->FullName(user_id());
  }
}

void EpisodeTable_Episode::Invalidate(const DBHandle& updates) {
  typedef ContentTable<EpisodeTable_Episode>::Content Content;
  EpisodeHandle eh(reinterpret_cast<Content*>(this));
  state_->day_table()->InvalidateEpisode(eh, updates);

  // Invalidate any activities which shared photos from this episode.
  if (id().has_server_id()) {
    vector<int64_t> activity_ids;
    state_->activity_table()->ListEpisodeActivities(id().server_id(), &activity_ids, updates);
    for (int i = 0; i < activity_ids.size(); ++i) {
      ActivityHandle ah = state_->activity_table()->LoadActivity(activity_ids[i], updates);
      state_->day_table()->InvalidateActivity(ah, updates);
    }
  }
}

bool EpisodeTable_Episode::Load() {
  disk_timestamp_ = timestamp();
  return true;
}

void EpisodeTable_Episode::SaveHook(const DBHandle& updates) {
  bool has_posted_photo = false;
  bool update_episode_timestamp = false;
  if (photos_.get()) {
    if (recompute_timestamp_range_) {
      clear_earliest_photo_timestamp();
      clear_latest_photo_timestamp();
    }

    // Persist any photo additions/removals.
    int photo_count = 0;
    int updated = 0;
    for (PhotoStateMap::iterator iter(photos_->begin());
         iter != photos_->end();
         ++iter) {
      const int64_t photo_id = iter->first;
      const string episode_photo_key = EncodeEpisodePhotoKey(id().local_id(), photo_id);
      const string photo_episode_key = EncodePhotoEpisodeKey(photo_id, id().local_id());

      // Keep earliest and latest photo timestamps up to date. Note that in the
      // common case where a photo is being added, we're simply updating the
      // existing range and not recomputing it from scratch.
      if ((recompute_timestamp_range_ && iter->second == POSTED) ||
          iter->second == POST_PENDING) {
        PhotoHandle ph = state_->photo_table()->LoadPhoto(photo_id, updates);
        if (!ph.get()) {
          LOG("couldn't load photo %d", photo_id);
          continue;
        }
        // Keep earliest and latest photo timestamps up-to-date.
        if (!has_earliest_photo_timestamp() ||
            ph->timestamp() < earliest_photo_timestamp()) {
          set_earliest_photo_timestamp(ph->timestamp());
        }
        if (!has_latest_photo_timestamp() ||
            ph->timestamp() > latest_photo_timestamp()) {
          set_latest_photo_timestamp(ph->timestamp());
        }
      }

      // Counts of the number of episodes the photo resides in immediately
      // before/after performing an addition or deletion. Used to determine if
      // the total count of photos in episodes is changing.
      int pre_add_episode_count = -1;
      int post_delete_episode_count = -1;

      if (iter->second == HIDE_PENDING) {
        pre_add_episode_count = state_->episode_table()->CountEpisodes(photo_id, updates);
        updates->Put(episode_photo_key, EpisodeTable::kHiddenValue);
        updates->Put(photo_episode_key, string());
        iter->second = HIDDEN;
        ++updated;
      } else if (iter->second == POST_PENDING) {
        pre_add_episode_count = state_->episode_table()->CountEpisodes(photo_id, updates);
        updates->Put(episode_photo_key, EpisodeTable::kPostedValue);
        updates->Put(photo_episode_key, string());
        iter->second = POSTED;
        ++updated;
      } else if (iter->second == QUARANTINE_PENDING) {
        // NOTE: quarantined photos count against total count of photos.
        pre_add_episode_count = state_->episode_table()->CountEpisodes(photo_id, updates);
        updates->Put(episode_photo_key, EpisodeTable::kQuarantinedValue);
        updates->Put(photo_episode_key, string());
        iter->second = QUARANTINED;
        ++updated;
      } else if (iter->second == REMOVE_PENDING) {
        updates->Put(episode_photo_key, EpisodeTable::kRemovedValue);
        if (updates->Exists(photo_episode_key)) {
          // Decrement the photo ref count for this episode.
          updates->Delete(photo_episode_key);
        }
        post_delete_episode_count = state_->episode_table()->CountEpisodes(photo_id, updates);
        iter->second = REMOVED;
        ++updated;
      } else if (iter->second == UNSHARE_PENDING) {
        updates->Put(episode_photo_key, EpisodeTable::kUnsharedValue);
        if (updates->Exists(photo_episode_key)) {
          updates->Delete(photo_episode_key);
          post_delete_episode_count = state_->episode_table()->CountEpisodes(photo_id, updates);
        }
        iter->second = UNSHARED;
        ++updated;
      }
      if (iter->second == POSTED) {
        has_posted_photo = true;
      }
      if (pre_add_episode_count == 0) {
        // Photo was added to its first episode.
        ++photo_count;
      }
      if (post_delete_episode_count == 0) {
        // Photo was deleted from its last episode. Delete any images
        // associated with the photo.
        state_->photo_table()->DeleteAllImages(photo_id, updates);
        --photo_count;
      }
    }

    if (photo_count != 0) {
      VLOG("saved episode had net addition of %d photos", photo_count);
    }

    if (!has_earliest_photo_timestamp()) {
      DCHECK(!has_latest_photo_timestamp());
      set_earliest_photo_timestamp(timestamp());
      set_latest_photo_timestamp(timestamp());
    }

    // Update the episode timestamp mapping any time a photo is added,
    // hidden, removed or unshared.
    update_episode_timestamp = updated > 0;
  }

  if (disk_timestamp_ != timestamp() || update_episode_timestamp) {
    if (disk_timestamp_ > 0) {
      updates->Delete(
          EncodeEpisodeTimestampKey(disk_timestamp_, id().local_id()));
    }
    disk_timestamp_ = timestamp();
  }
  // We reference has_posted_photo to avoid counting photos in the episode
  // unnecessarily.
  if (disk_timestamp_ > 0 && (has_posted_photo || CountPhotos() > 0)) {
    // Only add the episode to the <timestamp>,<episode-id> map if the
    // episode contains POSTED photos.
    updates->Put(EncodeEpisodeTimestampKey(disk_timestamp_, id().local_id()),
                 string());
  }
  if (has_parent_id()) {
    updates->Put(EncodeEpisodeParentChildKey(parent_id().local_id(), id().local_id()),
                 string());
  }

  additions_ = 0;
  hiddens_ = 0;
  quarantines_ = 0;
  removals_ = 0;
  unshares_ = 0;
  recompute_timestamp_range_ = false;

  Invalidate(updates);
}

void EpisodeTable_Episode::DeleteHook(const DBHandle& updates) {
  int photo_count = 0;
  MutexLock lock(&photos_mu_);
  EnsurePhotoState();
  for (PhotoStateMap::iterator iter(photos_->begin());
       iter != photos_->end();
       ++iter) {
    const int64_t photo_id = iter->first;
    const string episode_photo_key = EncodeEpisodePhotoKey(id().local_id(), photo_id);
    const string photo_episode_key = EncodePhotoEpisodeKey(photo_id, id().local_id());

    updates->Delete(episode_photo_key);
    updates->Delete(photo_episode_key);

    if (!state_->episode_table()->CountEpisodes(photo_id, updates)) {
      // Photo was deleted from its last episode. Delete any images
      // associated with the photo.
      state_->photo_table()->DeleteAllImages(photo_id, updates);
      --photo_count;
    }
  }

  if (photo_count != 0) {
    VLOG("deleted episode had net addition of %d photos", photo_count);
  }

  if (disk_timestamp_ > 0) {
    updates->Delete(
        EncodeEpisodeTimestampKey(disk_timestamp_, id().local_id()));
  }
  if (has_parent_id()) {
    updates->Delete(EncodeEpisodeParentChildKey(parent_id().local_id(), id().local_id()));
  }
  // Delete episode selection key.
  if (id().has_server_id()) {
    updates->Delete(DBFormat::episode_selection_key(id().server_id()));
  }

  Invalidate(updates);
}

void EpisodeTable_Episode::EnsurePhotoState() {
  photos_mu_.AssertHeld();
  if (have_photo_state_) {
    return;
  }
  if (!photos_.get()) {
    photos_.reset(new PhotoStateMap);
  }
  have_photo_state_ = true;

  for (ScopedPtr<EpisodeTable::EpisodePhotoIterator> iter(
           new EpisodeTable::EpisodePhotoIterator(id().local_id(), db_));
       !iter->done();
       iter->Next()) {
    const int64_t photo_id = iter->photo_id();
    if (ContainsKey(*photos_, photo_id)) {
      // Note that the disk photo state gets layered in underneath the existing
      // photo state.
      continue;
    }
    const Slice value = iter->value();
    if (value == EpisodeTable::kHiddenValue) {
      (*photos_)[photo_id] = HIDDEN;
    } else if (value == EpisodeTable::kPostedValue) {
      (*photos_)[photo_id] = POSTED;
    } else if (value == EpisodeTable::kQuarantinedValue) {
      (*photos_)[photo_id] = QUARANTINED;
    } else if (value == EpisodeTable::kRemovedValue) {
      (*photos_)[photo_id] = REMOVED;
    } else if (value == EpisodeTable::kUnsharedValue) {
      (*photos_)[photo_id] = UNSHARED;
    }
  }
}


////
// EpisodeIterator

EpisodeTable::EpisodeIterator::EpisodeIterator(
    EpisodeTable* table, WallTime start, bool reverse, const DBHandle& db)
    : ContentIterator(db->NewIterator(), reverse),
      table_(table),
      db_(db),
      timestamp_(0),
      episode_id_(0) {
  Seek(start);
}

EpisodeHandle EpisodeTable::EpisodeIterator::GetEpisode() {
  if (done()) {
    return EpisodeHandle();
  }
  return table_->LoadContent(episode_id_, db_);
}

void EpisodeTable::EpisodeIterator::Seek(WallTime seek_time) {
  ContentIterator::Seek(EncodeEpisodeTimestampKey(
                            seek_time, reverse_ ? std::numeric_limits<int64_t>::max() : 0));
}

bool EpisodeTable::EpisodeIterator::IteratorDone(const Slice& key) {
  return !key.starts_with(kEpisodeTimestampKeyPrefix);
}

bool EpisodeTable::EpisodeIterator::UpdateStateHook(const Slice& key) {
  return DecodeEpisodeTimestampKey(key, &timestamp_, &episode_id_);
}


////
// EpisodePhotoIterator

EpisodeTable::EpisodePhotoIterator::EpisodePhotoIterator(
    int64_t episode_id, const DBHandle& db)
    : ContentIterator(db->NewIterator(), false),
      episode_prefix_(EncodeEpisodePhotoKey(episode_id, 0)),
      photo_id_(0) {
  Seek(episode_prefix_);
}

bool EpisodeTable::EpisodePhotoIterator::IteratorDone(const Slice& key) {
  return !key.starts_with(episode_prefix_);
}

bool EpisodeTable::EpisodePhotoIterator::UpdateStateHook(const Slice& key) {
  int64_t episode_id;
  return DecodeEpisodePhotoKey(key, &episode_id, &photo_id_);
}


////
// EpisodeTable

const string EpisodeTable::kHiddenValue = "h";
const string EpisodeTable::kPostedValue = "a";
const string EpisodeTable::kQuarantinedValue = "q";
const string EpisodeTable::kRemovedValue = "r";
const string EpisodeTable::kUnsharedValue = "u";


EpisodeTable::EpisodeTable(AppState* state)
    : ContentTable<Episode>(state,
                            DBFormat::episode_key(),
                            DBFormat::episode_server_key(),
                            kEpisodeFSCKVersion,
                            DBFormat::metadata_key("episode_table_fsck")),
      stats_initialized_(false),
      episode_index_(new FullTextIndex(state_, kEpisodeIndexName)),
      location_index_(new FullTextIndex(state_, kLocationIndexName)) {
}

EpisodeTable::~EpisodeTable() {
}

void EpisodeTable::Reset() {
  MutexLock l(&stats_mu_);
  stats_initialized_ = false;
  stats_.Clear();
}

EpisodeHandle EpisodeTable::LoadEpisode(const EpisodeId& id, const DBHandle& db) {
  EpisodeHandle eh;
  if (id.has_local_id()) {
    eh = LoadEpisode(id.local_id(), db);
  }
  if (!eh.get() && id.has_server_id()) {
    eh = LoadEpisode(id.server_id(), db);
  }
  return eh;
}

EpisodeTable::ContentHandle EpisodeTable::MatchPhotoToEpisode(
    const PhotoHandle& p, const DBHandle& db) {
  const WallTime max_time = p->timestamp() + kMaxTimeDist;
  const WallTime min_time = std::max<WallTime>(0, p->timestamp() - kMaxTimeDist);
  for (ScopedPtr<EpisodeTable::EpisodeIterator> iter(
           NewEpisodeIterator(min_time, false, db));
       !iter->done() && iter->timestamp() <= max_time;
       iter->Next()) {
    EpisodeHandle e = LoadEpisode(iter->episode_id(), db);
    if (!e.get() ||
        // Only match to episodes owned by this user.
        e->GetUserId() != p->GetUserId() ||
        // Server disallows match to an episode created on another device.
        e->GetDeviceId() != p->GetDeviceId() ||
        // Don't match a photo to an episode which is a reshare!
        e->has_parent_id()) {
      continue;
    }

    // We use a photo iterator instead of ListPhotos() because we most likely
    // will match on the first photo.
    for (ScopedPtr<EpisodeTable::EpisodePhotoIterator> photo_iter(
             new EpisodeTable::EpisodePhotoIterator(e->id().local_id(), db));
         !photo_iter->done();
         photo_iter->Next()) {
      if (photo_iter->value() != EpisodeTable::kPostedValue) {
        continue;
      }
      PhotoHandle q = state_->photo_table()->LoadPhoto(photo_iter->photo_id(), db);
      if (!q.get()) {
        continue;
      }
      if (p->has_timestamp() && q->has_timestamp()) {
        const double time_dist = fabs(p->timestamp() - q->timestamp());
        if (time_dist >= kMaxTimeDist) {
          continue;
        }
      }
      if (p->has_location() && q->has_location()) {
        const double loc_dist = DistanceBetweenLocations(
            p->location(), q->location());
        if (loc_dist >= kMaxLocDist) {
          continue;
        }
      }
      return e;
    }
  }
  return EpisodeHandle();
}

void EpisodeTable::AddPhotoToEpisode(const PhotoHandle& p, const DBHandle& updates) {
  if (!p->ShouldAddPhotoToEpisode()) {
    return;
  }
  EpisodeHandle e = MatchPhotoToEpisode(p, updates);
  if (!e.get()) {
    e = NewEpisode(updates);
    e->Lock();
    e->set_timestamp(p->timestamp());
    e->set_upload_episode(true);
    e->MaybeSetServerId();
    VLOG("photo: new episode: %s", e->id());
  } else {
    e->Lock();
  }
  p->mutable_episode_id()->CopyFrom(e->id());
  e->AddPhoto(p->id().local_id());
  e->SaveAndUnlock(updates);
}

int EpisodeTable::CountEpisodes(int64_t photo_id, const DBHandle& db) {
  int count = 0;
  for (DB::PrefixIterator iter(db, EncodePhotoEpisodeKey(photo_id, 0));
       iter.Valid();
       iter.Next()) {
    int64_t photo_id;
    int64_t episode_id;
    if (DecodePhotoEpisodeKey(iter.key(), &photo_id, &episode_id)) {
      ++count;
    }
  }
  return count;
}

bool EpisodeTable::ListEpisodes(
    int64_t photo_id, vector<int64_t>* episode_ids, const DBHandle& db) {
  for (DB::PrefixIterator iter(db, EncodePhotoEpisodeKey(photo_id, 0));
       iter.Valid();
       iter.Next()) {
    int64_t photo_id;
    int64_t episode_id;
    if (DecodePhotoEpisodeKey(iter.key(), &photo_id, &episode_id)) {
      if (episode_ids) {
        episode_ids->push_back(episode_id);
      } else {
        return true;
      }
    }
  }
  return episode_ids && !episode_ids->empty();
}

bool EpisodeTable::ListLibraryEpisodes(
    int64_t photo_id, vector<int64_t>* episode_ids, const DBHandle& db) {
  vector<int64_t> raw_episode_ids;
  if (!ListEpisodes(photo_id, &raw_episode_ids, db)) {
    return false;
  }
  for (int i = 0; i < raw_episode_ids.size(); ++i) {
    EpisodeHandle eh = LoadEpisode(raw_episode_ids[i], db);
    if (eh.get() && eh->InLibrary()) {
      if (episode_ids) {
        episode_ids->push_back(raw_episode_ids[i]);
      } else {
        return true;
      }
    }
  }
  return episode_ids && !episode_ids->empty();
}

void EpisodeTable::RemovePhotos(
    const PhotoSelectionVec& photo_ids, const DBHandle& updates) {
  typedef std::unordered_map<int64_t, vector<int64_t> > EpisodeToPhotoMap;
  EpisodeToPhotoMap episodes;
  for (int i = 0; i < photo_ids.size(); ++i) {
    episodes[photo_ids[i].episode_id].push_back(photo_ids[i].photo_id);
  }

  ServerOperation op;
  ServerOperation::RemovePhotos* r = op.mutable_remove_photos();

  // Process the episodes in the same order as specified in the photo_ids
  // vector to ease testing.
  for (int i = 0; !episodes.empty() && i < photo_ids.size(); ++i) {
    const int64_t episode_id = photo_ids[i].episode_id;
    const vector<int64_t>* v = FindPtrOrNull(episodes, episode_id);
    if (!v) {
      continue;
    }
    const EpisodeHandle eh = LoadEpisode(episode_id, updates);
    if (!eh.get()) {
      episodes.erase(episode_id);
      continue;
    }
    eh->Lock();

    ActivityMetadata::Episode* e = NULL;
    for (int j = 0; j < v->size(); ++j) {
      const int64_t photo_id = (*v)[j];
      if (!state_->photo_table()->LoadPhoto(photo_id, updates).get()) {
        continue;
      }
      if (!e) {
        // Only add an episode to the server operation when the first valid
        // photo id is found.
        e = r->add_episodes();
        e->mutable_episode_id()->CopyFrom(eh->id());
      }
      e->add_photo_ids()->set_local_id(photo_id);
      eh->RemovePhoto(photo_id);
    }

    if (e) {
      eh->SaveAndUnlock(updates);
    } else {
      eh->Unlock();
    }

    episodes.erase(episode_id);
  }

  if (r->episodes_size() > 0) {
    // Only queue the operation if photos were removed.
    op.mutable_headers()->set_op_id(state_->NewLocalOperationId());
    op.mutable_headers()->set_op_timestamp(WallTime_Now());
    state_->net_queue()->Add(PRIORITY_UI_ACTIVITY, op, updates);
  }
}

EpisodeHandle EpisodeTable::GetEpisodeForPhoto(
    const PhotoHandle& p, const DBHandle& db) {
  // Start with the photo's putative episode.
  EpisodeHandle eh = LoadEpisode(p->episode_id(), db);
  if (eh.get()) {
    return eh;
  }

  // Otherwise, get a list of all episodes the photo belongs to
  // and find the first which has been uploaded, and for which the
  // photo has neither been removed or unshared.
  vector<int64_t> episode_ids;
  ListEpisodes(p->id().local_id(), &episode_ids, db);
  for (int i = 0; i < episode_ids.size(); ++i) {
    eh = LoadEpisode(episode_ids[i], db);
    if (eh.get() &&
        !eh->upload_episode() &&
        !eh->IsRemoved(p->id().local_id()) &&
        !eh->IsUnshared(p->id().local_id())) {
      return eh;
    }
  }

  return EpisodeHandle();
}

void EpisodeTable::Validate(
    const EpisodeSelection& s, const DBHandle& updates) {
  const string key(DBFormat::episode_selection_key(s.episode_id()));

  // Load any existing episode selection and clear attributes which have been
  // queried by "s". If no attributes remain set, the selection is deleted.
  EpisodeSelection existing;
  if (updates->GetProto(key, &existing)) {
    if (s.get_attributes()) {
      existing.clear_get_attributes();
    }
    if (s.get_photos()) {
      if (!existing.get_photos() ||
          s.photo_start_key() <= existing.photo_start_key()) {
        existing.clear_get_photos();
        existing.clear_photo_start_key();
      }
    } else if (existing.get_photos()) {
      existing.set_photo_start_key(
          std::max(existing.photo_start_key(),
                   s.photo_start_key()));
    }
  }

  if (existing.has_get_attributes() ||
      existing.has_get_photos()) {
    updates->PutProto(key, existing);
  } else {
    updates->Delete(key);
  }
}

void EpisodeTable::Invalidate(
    const EpisodeSelection& s, const DBHandle& updates) {
  const string key(DBFormat::episode_selection_key(s.episode_id()));

  // Load any existing episode selection and merge invalidations from "s".
  EpisodeSelection existing;
  if (!updates->GetProto(key, &existing)) {
    existing.set_episode_id(s.episode_id());
  }

  if (s.get_attributes()) {
    existing.set_get_attributes(true);
  }
  if (s.get_photos()) {
    if (existing.get_photos()) {
      existing.set_photo_start_key(std::min<string>(existing.photo_start_key(),
                                                    s.photo_start_key()));
    } else {
      existing.set_photo_start_key(s.photo_start_key());
    }
    existing.set_get_photos(true);
  }

  updates->PutProto(key, existing);
}

void EpisodeTable::ListInvalidations(
    vector<EpisodeSelection>* v, int limit, const DBHandle& db) {
  v->clear();
  ScopedPtr<leveldb::Iterator> iter(db->NewIterator());
  iter->Seek(kEpisodeSelectionKeyPrefix);
  while (iter->Valid() && (limit <= 0 || v->size() < limit)) {
    Slice key = ToSlice(iter->key());
    if (!key.starts_with(kEpisodeSelectionKeyPrefix)) {
      break;
    }
    EpisodeSelection eps;
    if (db->GetProto(key, &eps)) {
      v->push_back(eps);
    } else {
      LOG("unable to read episode selection at key %s", key);
    }
    iter->Next();
  }
}

void EpisodeTable::ClearAllInvalidations(const DBHandle& updates) {
  ScopedPtr<leveldb::Iterator> iter(updates->NewIterator());
  iter->Seek(kEpisodeSelectionKeyPrefix);
  for (; iter->Valid(); iter->Next()) {
    Slice key = ToSlice(iter->key());
    if (!key.starts_with(kEpisodeSelectionKeyPrefix)) {
      break;
    }
    updates->Delete(key);
  }
}

void EpisodeTable::ListEpisodesByParentId(
    int64_t parent_id, vector<int64_t>* children, const DBHandle& db) {
  for (DB::PrefixIterator iter(db, EncodeEpisodeParentChildKey(parent_id, 0));
       iter.Valid();
       iter.Next()) {
    int64_t parent_id;
    int64_t child_id;
    if (DecodeEpisodeParentChildKey(iter.key(), &parent_id, &child_id)) {
      children->push_back(child_id);
    }
  }
}

EpisodeTable::EpisodeIterator* EpisodeTable::NewEpisodeIterator(
    WallTime start, bool reverse, const DBHandle& db) {
  return new EpisodeIterator(this, start, reverse, db);
}

EpisodeStats EpisodeTable::stats() {
  EnsureStatsInit();
  MutexLock l(&stats_mu_);
  return stats_;
}

bool EpisodeTable::FSCKImpl(int prev_fsck_version, const DBHandle& updates) {
  LOG("FSCK: EpisodeTable");
  bool changes = false;
  if (FSCKEpisode(prev_fsck_version, updates)) {
    changes = true;
  }
  // Handle any duplicates in secondary indexes by timestamp. These can exist
  // as a result of a server bug which rounded up timestamps.
  if (FSCKEpisodeTimestampIndex(updates)) {
    changes = true;
  }
  return changes;
}

bool EpisodeTable::FSCKEpisode(int prev_fsck_version, const DBHandle& updates) {
  bool changes = false;
  for (DB::PrefixIterator iter(updates, DBFormat::episode_key());
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const Slice value = iter.value();
    EpisodeMetadata em;
    if (em.ParseFromArray(value.data(), value.size())) {
      EpisodeHandle eh = LoadEpisode(em.id().local_id(), updates);
      eh->Lock();
      bool save_eh = false;
      if (key != EncodeContentKey(DBFormat::episode_key(), em.id().local_id())) {
        LOG("FSCK: episode id %d does not equal key %s; deleting key and re-saving",
            em.id().local_id(), key);
        updates->Delete(key);
        save_eh = true;
      }

      // Check required fields.
      if (!eh->has_id() || !eh->has_timestamp()) {
        LOG("FSCK: episode missing required fields: %s", *eh);
      }

      // Check viewpoint; lookup first by server id.
      if (eh->has_viewpoint_id()) {
        ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(eh->viewpoint_id(), updates);
        if (vh.get() && !eh->viewpoint_id().local_id()) {
          LOG("FSCK: missing local id for viewpoint %s", vh->id());
          eh->mutable_viewpoint_id()->CopyFrom(vh->id());
          save_eh = true;
        } else if (!vh.get()) {
          if (eh->viewpoint_id().has_server_id()) {
            LOG("FSCK: missing viewpoint %s; setting invalidation", eh->viewpoint_id());
            state_->viewpoint_table()->InvalidateFull(eh->viewpoint_id().server_id(), updates);
            changes = true;
          } else {
            LOG("FSCK: invalid reference to viewpoint %s; clearing", eh->viewpoint_id());
            eh->clear_viewpoint_id();
            save_eh = true;
          }
        }
      }

      // Check secondary indexes.
      if (eh->has_timestamp() && eh->CountPhotos() > 0) {
        const string ts_episode_key = EncodeEpisodeTimestampKey(
            eh->timestamp(), eh->id().local_id());
        if (!updates->Exists(ts_episode_key)) {
          LOG("FSCK: missing timestamp episode key");
          save_eh = true;
        }
      }

      // Verify photo timestamp range is set.
      if (!eh->has_earliest_photo_timestamp() ||
          !eh->has_latest_photo_timestamp()) {
        LOG("FSCK: missing photo timestamp range; recomputing...");
        eh->recompute_timestamp_range_ = true;
        save_eh = true;
      }

      if (save_eh) {
        LOG("FSCK: rewriting episode %s", *eh);
        eh->SaveAndUnlock(updates);
        changes = true;
      } else {
        eh->Unlock();
      }
    }
  }

  return changes;
}

bool EpisodeTable::FSCKEpisodeTimestampIndex(const DBHandle& updates) {
  // Map from episode id to secondary index key.
  std::unordered_map<int64_t, string>* episode_ids(
      new std::unordered_map<int64_t, string>);
  bool changes = false;

  for (DB::PrefixIterator iter(updates, kEpisodeTimestampKeyPrefix);
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    WallTime timestamp;
    int64_t episode_id;
    if (!DecodeEpisodeTimestampKey(key, &timestamp, &episode_id)) {
      LOG("FSCK: unreadable episode timestamp secondary index: %s", key);
      updates->Delete(key);
      changes = true;
    } else {
      if (ContainsKey(*episode_ids, episode_id)) {
        LOG("FSCK: episode timestamp secondary index contains duplicate entries for %d; "
            "deleting earlier instance (%s)", episode_id, (*episode_ids)[episode_id]);
        updates->Delete((*episode_ids)[episode_id]);
        changes = true;
      }
      (*episode_ids)[episode_id] = ToString(key);
    }
  }

  delete episode_ids;
  return changes;
}

void EpisodeTable::Search(const Slice& query, EpisodeSearchResults* results) {
  QueryRewriter rewriter(state_);
  ScopedPtr<FullTextQuery> parsed_query(rewriter.ParseAndRewrite(query));
  FullTextQueryIteratorBuilder builder({episode_index_.get(), location_index_.get()}, state_->db());
  for (ScopedPtr<FullTextResultIterator> iter(builder.BuildIterator(*parsed_query));
       iter->Valid();
       iter->Next()) {
    results->push_back(FastParseInt64(iter->doc_id()));
  }
}

void EpisodeTable::SaveContentHook(Episode* episode, const DBHandle& updates) {
  vector<FullTextIndexTerm> terms;
  vector<FullTextIndexTerm> location_terms;
  int pos = 0;
  int location_pos = 0;
  // Don't index anything/remove all indexed terms if all photos have been removed.
  if (episode->CountPhotos() > 0) {
    Location loc;
    Placemark pm;
    // Index the location at several granularities.  This lets us have separate autocomplete
    // entries for "Soho, NYC" and "New York, NY".
    if (episode->GetLocation(&loc, &pm)) {
      StringSet seen_location_terms;
      auto IndexLocationTerm = [&](const string& term) {
        if (term.empty() || ContainsKey(seen_location_terms, term)) {
          return;
        }
        seen_location_terms.insert(term);
        // Index each location term as both a bag of words in the main index and a single term in the
        // location index (for better autocomplete).
        pos = episode_index_->ParseIndexTerms(pos, term, &terms);
        // TODO(ben): this raw term should go through the denormalization process so "i" can
        // autocomplete to "Île-de-France".
        location_terms.push_back(FullTextIndexTerm(ToLowercase(term), term, location_pos++));
      };

      IndexLocationTerm(FormatPlacemarkWithReferencePlacemark(pm, NULL, false, PM_SUBLOCALITY, 2));
      IndexLocationTerm(FormatPlacemarkWithReferencePlacemark(pm, NULL, false, PM_LOCALITY, 2));
      IndexLocationTerm(FormatPlacemarkWithReferencePlacemark(pm, NULL, false, PM_STATE, 2));
    }
    if (episode->has_timestamp()) {
      // Index the month, date and year.
      const string date = FormatDate("%B %e %Y", episode->timestamp());
      pos = episode_index_->ParseIndexTerms(pos, date, &terms);
    }
    if (episode->user_id() != 0 && episode->user_id() != state_->user_id()) {
      pos = episode_index_->AddVerbatimToken(pos, ContactManager::FormatUserToken(episode->user_id()), &terms);
    }
    if (episode->viewpoint_id().local_id() != 0) {
      pos = episode_index_->AddVerbatimToken(pos, ViewpointTable::FormatViewpointToken(episode->viewpoint_id().local_id()), &terms);
    }
  }
  episode_index_->UpdateIndex(terms, ToString(episode->id().local_id()),
                              FullTextIndex::TimestampSortKey(episode->timestamp()),
                              episode->mutable_indexed_terms(), updates);
  location_index_->UpdateIndex(location_terms, ToString(episode->id().local_id()),
                               FullTextIndex::TimestampSortKey(episode->timestamp()),
                               episode->mutable_indexed_location_terms(), updates);

  EnsureStatsInit();
  MutexLock l(&stats_mu_);
  stats_.set_hidden_photos(stats_.hidden_photos() + episode->hiddens());
  stats_.set_posted_photos(stats_.posted_photos() + episode->additions());
  stats_.set_quarantined_photos(stats_.quarantined_photos() + episode->quarantines());
  stats_.set_removed_photos(stats_.removed_photos() + episode->removals());
  stats_.set_unshared_photos(stats_.unshared_photos() + episode->unshares());
}

void EpisodeTable::DeleteContentHook(Episode* episode, const DBHandle& updates) {
  episode_index_->RemoveTerms(episode->mutable_indexed_terms(), updates);
  location_index_->RemoveTerms(episode->mutable_indexed_location_terms(), updates);
}

void EpisodeTable::EnsureStatsInit() {
  if (stats_initialized_) {
    return;
  }

  MutexLock l(&stats_mu_);
  stats_initialized_ = true;
  // ScopedTimer timer("episode stats");

  // The stats could not be loaded; Regenerate from scratch.
  int hidden_photos = 0;
  int posted_photos = 0;
  int quarantined_photos = 0;
  int removed_photos = 0;
  int unshared_photos = 0;
  for (DB::PrefixIterator iter(state_->db(), EncodeEpisodePhotoKey(0, 0));
       iter.Valid();
       iter.Next()) {
    const Slice value = iter.value();
    int64_t episode_id;
    int64_t photo_id;
    if (DecodeEpisodePhotoKey(iter.key(), &episode_id, &photo_id)) {
      if (value == EpisodeTable::kHiddenValue) {
        hidden_photos++;
      } else if (value == EpisodeTable::kPostedValue) {
        posted_photos++;
      } else if (value == EpisodeTable::kQuarantinedValue) {
        quarantined_photos++;
      } else if (value == EpisodeTable::kRemovedValue) {
        removed_photos++;
      } else if (value == EpisodeTable::kUnsharedValue) {
        unshared_photos++;
      }
    }
  }

  stats_.set_hidden_photos(hidden_photos);
  stats_.set_posted_photos(posted_photos);
  stats_.set_quarantined_photos(quarantined_photos);
  stats_.set_removed_photos(removed_photos);
  stats_.set_unshared_photos(unshared_photos);
}

// local variables:
// mode: c++
// end:
