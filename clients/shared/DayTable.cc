// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <unordered_set>
#import "AppState.h"
#import "AsyncState.h"
#import "CommentTable.h"
#import "ContactManager.h"
#import "DayTable.h"
#import "Defines.h"
#import "FontSymbols.h"
#import "LocationUtils.h"
#import "PhotoTable.h"
#import "PlacemarkHistogram.h"
#import "STLUtils.h"
#import "StringUtils.h"
#import "Timer.h"

namespace {

// Key for invalidation trigger for use with transactions involving DayTable.
const string kDayTableCommitTrigger = "DayTableInvalidation";

// Maintains a sequence of invalidation ids.
const string kDayTableInvalidationSeqNoKey =
    DBFormat::metadata_key("next_day_table_invalidation_seq_no");

// The timezone for which the current day table metadata is built.
const string kDayTableTimezoneKey =
    DBFormat::metadata_key("day_table_timezone");

// Event/Conversations summaries.
const string kEpisodeSummaryKey = DBFormat::metadata_key("episode_summary");
const string kEventSummaryKey = DBFormat::metadata_key("event_summary");
const string kFullEventSummaryKey = DBFormat::metadata_key("full_event_summary");
const string kConversationSummaryKey = DBFormat::metadata_key("conversation_summary");
const string kUnviewedConversationSummaryKey =
    DBFormat::metadata_key("unviewed_conversation_summary");

// Increment to clear all cached day table entries.
const int64_t kDayTableFormat = 85;
const string kDayTableFormatKey = DBFormat::metadata_key("day_table_format");

const string kDayKeyPrefix = DBFormat::day_key("");
const string kDayEventKeyPrefix = DBFormat::day_event_key("");
const string kDayEpisodeInvalidationKeyPrefix = DBFormat::day_episode_invalidation_key("");
const string kEpisodeEventKeyPrefix = DBFormat::episode_event_key("");
const string kTrapdoorEventKeyPrefix = DBFormat::trapdoor_event_key();
const string kTrapdoorKeyPrefix = DBFormat::trapdoor_key("");
const string kUserInvalidationKeyPrefix = DBFormat::user_invalidation_key("");
const string kViewpointConversationKeyPrefix = DBFormat::viewpoint_conversation_key("");
const string kViewpointInvalidationKeyPrefix = DBFormat::viewpoint_invalidation_key("");

const int kDayInSeconds = 60 * 60 * 24;
const int kMinRefreshCount = 20;  // Minimum number of days to refresh in a cycle
const float kCommentThreadThreshold = 60 * 60;
const WallTime kMinTimestamp = 2 * kDayInSeconds;
const WallTime kMaxTimestamp = std::numeric_limits<int32_t>::max();
const float kPracticalDayOffset = 4.5 * 60 * 60;  // In seconds (04:30)
// Threshold number of photos in an event between
// using 2 "unit" rows in the summary view and 3 "unit" rows.
const int kEventPhotoThreshold = 5;
// Maximum sample sizes for trapdoor assets, by type.
const int kTrapdoorPhotoCount = 6;

const DBRegisterKeyIntrospect kDayKeyIntrospect(
    kDayKeyPrefix,
    [](Slice key) {
      WallTime timestamp;
      if (!DecodeDayKey(key, &timestamp)) {
        return string();
      }
      return string(Format("%s", DBIntrospect::timestamp(timestamp)));
    },
    [](Slice value) {
      return DBIntrospect::FormatProto<DayMetadata>(value);
    });

const DBRegisterKeyIntrospect kDayEventKeyIntrospect(
    kDayEventKeyPrefix,
    [](Slice key) {
      WallTime timestamp;
      int index;
      if (!DecodeDayEventKey(key, &timestamp, &index)) {
        return string();
      }
      return string(Format("%s/%d", DBIntrospect::timestamp(timestamp), index));
    },
    [](Slice value) {
      return DBIntrospect::FormatProto<EventMetadata>(value);
    });

const DBRegisterKeyIntrospect kDayEpisodeInvalidateKeyIntrospect(
    kDayEpisodeInvalidationKeyPrefix,
    [](Slice key) {
      WallTime timestamp;
      int64_t episode_id;
      if (!DecodeDayEpisodeInvalidationKey(key, &timestamp, &episode_id)) {
        return string();
      }
      return string(Format("%s/%d", DBIntrospect::timestamp(timestamp), episode_id));
    },
    [](Slice value) {
      return value.ToString();
    });

// Need this for migration which removes the obsolete
// day summary rows.
const DBRegisterKeyIntrospect kDaySummaryRowKeyIntrospect(
    DBFormat::day_summary_row_key(""), [](Slice key) {
      return key.ToString();
    }, NULL);

const DBRegisterKeyIntrospect kEventSummaryKeyIntrospect(
    kEventSummaryKey, NULL, [](Slice value) {
      return DBIntrospect::FormatProto<SummaryMetadata>(value);
    });

const DBRegisterKeyIntrospect kConversationSummaryKeyIntrospect(
    kConversationSummaryKey, NULL, [](Slice value) {
      return DBIntrospect::FormatProto<SummaryMetadata>(value);
    });

const DBRegisterKeyIntrospect kFullEventSummaryKeyIntrospect(
    kFullEventSummaryKey, NULL, [](Slice value) {
      return DBIntrospect::FormatProto<SummaryMetadata>(value);
    });

const DBRegisterKeyIntrospect kUnviewedConversationSummaryKeyIntrospect(
    kUnviewedConversationSummaryKey, NULL, [](Slice value) {
      return DBIntrospect::FormatProto<SummaryMetadata>(value);
    });

const DBRegisterKeyIntrospect kEpisodeEventKeyIntrospect(
    kEpisodeEventKeyPrefix, [](Slice key) {
      if (!key.starts_with(kEpisodeEventKeyPrefix)) {
        return string();
      }
      key.remove_prefix(kEpisodeEventKeyPrefix.size());
      const int64_t episode_id = OrderedCodeDecodeVarint64(&key);
      return string(Format("%d", episode_id));
    }, NULL);

const DBRegisterKeyIntrospect kViewpointConversationKeyIntrospect(
    kViewpointConversationKeyPrefix, [](Slice key) {
      if (!key.starts_with(kViewpointConversationKeyPrefix)) {
        return string();
      }
      key.remove_prefix(kViewpointConversationKeyPrefix.size());
      const int64_t viewpoint_id = OrderedCodeDecodeVarint64(&key);
      return string(Format("%d", viewpoint_id));
    }, NULL);

const DBRegisterKeyIntrospect kTrapdoorEventKeyIntrospect(
    kTrapdoorEventKeyPrefix, [](Slice key) {
      if (!key.starts_with(kTrapdoorEventKeyPrefix)) {
        return string();
      }
      key.remove_prefix(kTrapdoorEventKeyPrefix.size());
      // TODO(ben): unmangle the ordered code in the event portion of the key.
      return key.as_string();;
    }, NULL);

const DBRegisterKeyIntrospect kTrapdoorKeyIntrospect(
    kTrapdoorKeyPrefix,
    [](Slice key) {
      int64_t viewpoint_id;
      if (!DecodeTrapdoorKey(key, &viewpoint_id)) {
        return string();
      }
      return string(Format("%d", viewpoint_id));
    },
    [](Slice value) {
      return DBIntrospect::FormatProto<TrapdoorMetadata>(value);
    });

const DBRegisterKeyIntrospect kUserInvalidationKeyIntrospect(
    DBFormat::user_invalidation_key(""),
    [](Slice key) {
      int64_t user_id;
      if (!DecodeUserInvalidationKey(key, &user_id)) {
        return string();
      }
      return string(Format("%d", user_id));
    }, NULL);

const DBRegisterKeyIntrospect kViewpointInvalidationKeyIntrospect(
    DBFormat::viewpoint_invalidation_key(""),
    [](Slice key) {
      WallTime timestamp;
      int64_t viewpoint_id;
      int64_t activity_id;
      if (!DecodeViewpointInvalidationKey(key, &timestamp, &viewpoint_id, &activity_id)) {
        return string();
      }
      return string(Format("%s/%d/%d", DBIntrospect::timestamp(timestamp),
                           viewpoint_id, activity_id));
    },
    [](Slice value) {
      return value.ToString();
    });

const DBRegisterKeyIntrospect kViewpointSummaryKeyIntrospect(
    DBFormat::viewpoint_summary_key(), NULL,
    [](Slice value) {
      return DBIntrospect::FormatProto<ViewpointSummaryMetadata>(value);
    });

// Returns true if the placemark has enough valid components to be formatted
// for display.
bool IsValidPlacemark(const Placemark& placemark) {
  return (placemark.has_sublocality() ||
          placemark.has_locality() ||
          placemark.has_state()) &&
      placemark.has_country();
}

// Sets contact first name and full name if available. If neither is available,
// set the user id. Returns false iff the user has been terminated.
bool InitializeContributor(
    AppState* state, DayContributor* contrib, int64_t user_id, const string& identity) {
  ContactMetadata c;
  if (user_id) {
    if (state->contact_manager()->LookupUser(user_id, &c) &&
        c.label_terminated()) {
      return false;
    }
    contrib->set_user_id(user_id);
  } else {
    contrib->set_identity(identity);
  }
  return true;
}

typedef google::protobuf::RepeatedPtrField<DayContributor> DayContributorArray;

// Gets a vector of contributors. Uses first names if there are more than
// one contributor or if "shorten" is true. If a contributor has only a
// user_id, attempts to lookup the name using the contact manager.
void GetContributors(AppState* state, const DayContributorArray& contributors,
                     int contributor_mask, bool shorten, vector<string>* contrib_vec) {
  for (int i = 0; i < contributors.size(); ++i) {
    if (contributor_mask && !(contributors.Get(i).type() & contributor_mask)) {
      continue;
    }
    // Lookup names via contact manager by user id.
    const int64_t user_id = contributors.Get(i).user_id();
    ContactMetadata cm;
    if (user_id) {
      if (!state->contact_manager()->LookupUser(user_id, &cm) ||
          user_id != cm.user_id() /* merged user */) {
        continue;
      }
    } else {
      cm.set_primary_identity(contributors.Get(i).identity());
      cm.add_identities()->set_identity(cm.primary_identity());
    }
    const string first = state->contact_manager()->FirstName(cm, true);
    const string name = state->contact_manager()->FullName(cm, true);

    if (shorten) {
      if (user_id != state->user_id()) {
        if (!first.empty()) {
          contrib_vec->push_back(first);
          break;
        } else if (!name.empty()) {
          contrib_vec->push_back(name);
          break;
        }
      }
      continue;
    } else if (contributors.size() > 1) {
      if (!first.empty()) {
        contrib_vec->push_back(first);
        continue;
      }
    }
    if (!name.empty()) {
      contrib_vec->push_back(name);
    } else if (!first.empty()) {
      contrib_vec->push_back(first);
    }
  }
}

struct Holiday {
  const WallTime timestamp;
  const string title;
};

struct HolidaysByTimestamp {
  bool operator()(const Holiday& a, WallTime ts) const {
    return a.timestamp < ts;
  }
};

// These values are sorted by the timestamp. Take care that they remain so.
// TODO(spencer): fetch these values from the server.
const Holiday kUSHolidays[] = {
  {1009843200, "New Year's Day"},
  {1011571200, "Martin Luther King Jr.'s Day"},
  {1013644800, "Valentine's Day"},
  {1013990400, "President's Day"},
  {1016323200, "St. Patrick's Day"},
  {1022457600, "Memorial Day"},
  {1025740800, "Independence Day"},
  {1030924800, "Labor Day"},
  {1036022400, "Halloween"},
  {1038441600, "Thanksgiving Day"},
  {1040688000, "Christmas Eve"},
  {1040774400, "Christmas Day"},
  {1041292800, "New Year's Eve"},
  {1041379200, "New Year's Day"},
  {1043020800, "Martin Luther King Jr.'s Day"},
  {1045180800, "Valentine's Day"},
  {1045440000, "President's Day"},
  {1047859200, "St. Patrick's Day"},
  {1053907200, "Memorial Day"},
  {1057276800, "Independence Day"},
  {1062374400, "Labor Day"},
  {1067558400, "Halloween"},
  {1069891200, "Thanksgiving Day"},
  {1072224000, "Christmas Eve"},
  {1072310400, "Christmas Day"},
  {1072828800, "New Year's Eve"},
  {1072915200, "New Year's Day"},
  {1074470400, "Martin Luther King Jr.'s Day"},
  {1076716800, "Valentine's Day"},
  {1076889600, "President's Day"},
  {1079481600, "St. Patrick's Day"},
  {1085961600, "Memorial Day"},
  {1088899200, "Independence Day"},
  {1094428800, "Labor Day"},
  {1099180800, "Halloween"},
  {1101340800, "Thanksgiving Day"},
  {1103846400, "Christmas Eve"},
  {1103932800, "Christmas Day"},
  {1104451200, "New Year's Eve"},
  {1104537600, "New Year's Day"},
  {1105920000, "Martin Luther King Jr.'s Day"},
  {1108339200, "Valentine's Day"},
  {1108944000, "President's Day"},
  {1111017600, "St. Patrick's Day"},
  {1117411200, "Memorial Day"},
  {1120435200, "Independence Day"},
  {1125878400, "Labor Day"},
  {1130716800, "Halloween"},
  {1132790400, "Thanksgiving Day"},
  {1135382400, "Christmas Eve"},
  {1135468800, "Christmas Day"},
  {1135987200, "New Year's Eve"},
  {1136073600, "New Year's Day"},
  {1137369600, "Martin Luther King Jr.'s Day"},
  {1139875200, "Valentine's Day"},
  {1140393600, "President's Day"},
  {1142553600, "St. Patrick's Day"},
  {1148860800, "Memorial Day"},
  {1151971200, "Independence Day"},
  {1157328000, "Labor Day"},
  {1162252800, "Halloween"},
  {1164240000, "Thanksgiving Day"},
  {1166918400, "Christmas Eve"},
  {1167004800, "Christmas Day"},
  {1167523200, "New Year's Eve"},
  {1167609600, "New Year's Day"},
  {1168819200, "Martin Luther King Jr.'s Day"},
  {1171411200, "Valentine's Day"},
  {1171843200, "President's Day"},
  {1174089600, "St. Patrick's Day"},
  {1180310400, "Memorial Day"},
  {1183507200, "Independence Day"},
  {1188777600, "Labor Day"},
  {1193788800, "Halloween"},
  {1195689600, "Thanksgiving Day"},
  {1198454400, "Christmas Eve"},
  {1198540800, "Christmas Day"},
  {1199059200, "New Year's Eve"},
  {1199145600, "New Year's Day"},
  {1200873600, "Martin Luther King Jr.'s Day"},
  {1202947200, "Valentine's Day"},
  {1203292800, "President's Day"},
  {1205712000, "St. Patrick's Day"},
  {1211760000, "Memorial Day"},
  {1215129600, "Independence Day"},
  {1220227200, "Labor Day"},
  {1225411200, "Halloween"},
  {1227744000, "Thanksgiving Day"},
  {1230076800, "Christmas Eve"},
  {1230163200, "Christmas Day"},
  {1230681600, "New Year's Eve"},
  {1230768000, "New Year's Day"},
  {1232323200, "Martin Luther King Jr.'s Day"},
  {1234569600, "Valentine's Day"},
  {1234742400, "President's Day"},
  {1237248000, "St. Patrick's Day"},
  {1243209600, "Memorial Day"},
  {1246665600, "Independence Day"},
  {1252281600, "Labor Day"},
  {1256947200, "Halloween"},
  {1259193600, "Thanksgiving Day"},
  {1261612800, "Christmas Eve"},
  {1261699200, "Christmas Day"},
  {1262217600, "New Year's Eve"},
  {1262304000, "New Year's Day"},
  {1263772800, "Martin Luther King Jr.'s Day"},
  {1266105600, "Valentine's Day"},
  {1266192000, "President's Day"},
  {1268784000, "St. Patrick's Day"},
  {1275264000, "Memorial Day"},
  {1278201600, "Independence Day"},
  {1283731200, "Labor Day"},
  {1288483200, "Halloween"},
  {1290643200, "Thanksgiving Day"},
  {1293148800, "Christmas Eve"},
  {1293235200, "Christmas Day"},
  {1293753600, "New Year's Eve"},
  {1293840000, "New Year's Day"},
  {1295222400, "Martin Luther King Jr.'s Day"},
  {1297641600, "Valentine's Day"},
  {1298246400, "President's Day"},
  {1300320000, "St. Patrick's Day"},
  {1306713600, "Memorial Day"},
  {1309737600, "Independence Day"},
  {1315180800, "Labor Day"},
  {1320019200, "Halloween"},
  {1322092800, "Thanksgiving Day"},
  {1324684800, "Christmas Eve"},
  {1324771200, "Christmas Day"},
  {1325289600, "New Year's Eve"},
  {1325376000, "New Year's Day"},
  {1326672000, "Martin Luther King Jr.'s Day"},
  {1329177600, "Valentine's Day"},
  {1329696000, "President's Day"},
  {1331942400, "St. Patrick's Day"},
  {1338163200, "Memorial Day"},
  {1341360000, "Independence Day"},
  {1346630400, "Labor Day"},
  {1351641600, "Halloween"},
  {1353542400, "Thanksgiving Day"},
  {1356307200, "Christmas Eve"},
  {1356393600, "Christmas Day"},
  {1356912000, "New Year's Eve"},
};

struct ActivityOlderThan {
  bool operator()(const ActivityHandle& a, const ActivityHandle& b) const {
    return a->timestamp() < b->timestamp();
  }
};

struct CachedEpisodeLessThan {
  bool operator()(const CachedEpisode* a, const CachedEpisode* b) const {
    if (a->earliest_photo_timestamp() != b->earliest_photo_timestamp()) {
      return a->earliest_photo_timestamp() < b->earliest_photo_timestamp();
    } else if (b->has_parent_id() &&
               a->id().server_id() == b->parent_id().server_id()) {
      return true;
    } else if (a->in_library() != b->in_library()) {
      return a->in_library();
    } else if (a->photos_size() != b->photos_size()) {
      return a->photos_size() > b->photos_size();
    } else {
      return a->id().local_id() < b->id().local_id();
    }
  }
};

struct EpisodePhotoLessThan {
  bool operator()(const std::pair<int, const DayPhoto*>& a,
                  const std::pair<int, const DayPhoto*>& b) const {
    if (a.first != b.first) {
      return a.first < b.first;
    }
    return a.second->timestamp() < b.second->timestamp();
  }
};

struct EventDistanceGreaterThan {
  bool operator()(const DayTable::Event& a,
                  const DayTable::Event& b) const {
    return a.distance() > b.distance();
  }
};

struct EventTimestampGreaterThan {
  bool operator()(const DayTable::Event& a,
                  const DayTable::Event& b) const {
    return a.latest_timestamp() > b.latest_timestamp();
  }
};

struct SummaryRowGreaterThan {
  bool operator()(const SummaryRow* a, const SummaryRow* b) {
    if (a->day_timestamp() != b->day_timestamp()) {
      return a->day_timestamp() > b->day_timestamp();
    }
    return a->identifier() < b->identifier();
  }
  bool operator()(const SummaryRow* a, const SummaryRow& b) {
    return (*this)(a, &b);
  }
  bool operator()(const SummaryRow& a, const SummaryRow& b) {
    return (*this)(&a, &b);
  }
};

struct TrapdoorGreaterThan {
  bool operator()(const DayTable::Trapdoor& a,
                  const DayTable::Trapdoor& b) const {
    return a.latest_timestamp() > b.latest_timestamp();
  }
};

struct ContributorNewerThan {
  bool operator()(const ViewpointSummaryMetadata::Contributor& a,
                  const ViewpointSummaryMetadata::Contributor& b) const {
    return a.update_seq() > b.update_seq();
  }
};


// An iterator which merges activities and episodes into a sequence of
// days for which DayMetadata must be constructed. The day builder starts
// with the most recent day and iterates towards the least recent.
class DayBuilderIterator {
 public:
  DayBuilderIterator(AppState* state, const DBHandle& snapshot)
      : done_(false),
        activity_iter_(state->activity_table()->NewTimestampActivityIterator(
                           kMaxTimestamp, true, snapshot)),
        episode_iter_(state->episode_table()->NewEpisodeIterator(
                          kMaxTimestamp, true, snapshot)),
        cur_timestamp_(0) {
    UpdateState();
  }

  // Advance the iterator. Sets done() to true if there are no more
  // days in the iteration.
  void Next() {
    if (!done_) {
      // NOTE: Even though cur_timestamp_ is a double, it is truncated
      // to an int before being encoded for the index, so we can subtract
      // 1 without fear of skipping any fractional entries.
      activity_iter_->Seek(cur_timestamp_ - 1);
      episode_iter_->Seek(cur_timestamp_ - 1);
      UpdateState();
    }
  }

  WallTime timestamp() const { return cur_timestamp_; }
  bool done() const { return done_; }

 private:
  void UpdateState() {
    WallTime timestamp = 0;
    if (activity_iter_->done() && episode_iter_->done()) {
      done_ = true;
    } else if (!activity_iter_->done() && !episode_iter_->done()) {
      timestamp = CanonicalizeTimestamp(
          std::max<WallTime>(activity_iter_->timestamp(), episode_iter_->timestamp()));
    } else if (!activity_iter_->done()) {
      timestamp = CanonicalizeTimestamp(activity_iter_->timestamp());
    } else if (!episode_iter_->done()) {
      timestamp = CanonicalizeTimestamp(episode_iter_->timestamp());
    }
    if (!done_) {
      if (timestamp == cur_timestamp_) {
        LOG("day table: day builder iterator done as timestamps equal %s, %d == %d",
            WallTimeFormat("%b %e, %Y", timestamp), int(timestamp), int(cur_timestamp_));
        done_ = true;
      } else {
        cur_timestamp_ = timestamp;
      }
    }
  }

 private:
  bool done_;
  ScopedPtr<ActivityTable::ActivityIterator> activity_iter_;
  ScopedPtr<EpisodeTable::EpisodeIterator> episode_iter_;
  // Invariant: cur_timestamp_ is always a "canonical" timestamp, aligned
  // to day boundaries.
  WallTime cur_timestamp_;
};

// Used to build and sort a list of event trapdoors.
struct TrapdoorProfile {
  int photo_count;
  int contrib_count;
  string title;
  TrapdoorProfile(int pc, int cc, const string& title)
      : photo_count(pc), contrib_count(cc), title(title) {}
};

// Combines an existing stream of activities with a vector of
// ActivityHandle objects, sorted by timestamps. At each step of the
// iteration, ::should_append() can be consulted to determine whether
// the next activity should be taken from ::cur_activity() or built
// from scratch by calling ViewpointSummary::AppendActivityRows().
typedef google::protobuf::RepeatedPtrField<
  ViewpointSummaryMetadata::ActivityRow> ActivityRowArray;

class ActivityMergeIterator {
 public:
  ActivityMergeIterator(
      AppState* state, const DBHandle& db, const ActivityRowArray* existing,
      const vector<ActivityHandle>& ah_vec)
      : state_(state),
        db_(db),
        existing_(existing),
        existing_index_(0),
        vec_index_(0),
        cur_index_(-1),
        prev_index_(-1),
        next_index_(-1),
        done_(false),
        should_append_(false),
        cur_is_existing_(true) {
    for (int i = 0; i < ah_vec.size(); ++i) {
      const bool already_contains_key =
          ContainsKey(activity_ids_, ah_vec[i]->activity_id().local_id());
      DCHECK(!already_contains_key);
      if (already_contains_key) {
        continue;
      }
      activity_ids_.insert(ah_vec[i]->activity_id().local_id());
      // Verify activities are provided in sorted order.
      if (i > 0) {
        DCHECK_GE(ah_vec[i]->timestamp(), ah_vec[i - 1]->timestamp());
      }
      // Remove non-visible activities. They're added to the activity
      // ids set which will prevent them from being added from existing.
      if (ah_vec[i]->IsVisible()) {
        ah_vec_.push_back(ah_vec[i]);
      }
    }
    // Skip existing, leading row(s) which are being replaced.
    existing_index_ = NextExistingIndex(0, false);
    // Set initial state.
    UpdateInternal();
  }

  void Next() {
    DCHECK(!done_);
    if (done_) return;
    if (cur_is_existing_) {
      existing_index_ = NextExistingIndex(existing_index_ + 1, false);
      DCHECK_LE(existing_index_, existing_->size());
    } else {
      ++vec_index_;
      DCHECK_LE(vec_index_, ah_vec_.size());
    }
    UpdateInternal();
  }

  bool done() const { return done_; }

  const ActivityHandle& cur_ah() {
    if (cur_index_ != -1 && !cur_ah_.get()) {
      cur_ah_ = LoadActivity(cur_index_);
    }
    return cur_ah_;
  }
  const ActivityHandle& prev_ah() {
    if (prev_index_ != -1 && !prev_ah_.get()) {
      prev_ah_ = LoadActivity(prev_index_);
    }
    return prev_ah_;
  }
  const ActivityHandle& next_ah() {
    if (next_index_ != -1 && !next_ah_.get()) {
      next_ah_ = LoadActivity(next_index_);
    }
    return next_ah_;
  }

  bool should_append() const { return should_append_; }

  const ViewpointSummaryMetadata::ActivityRow& cur_activity() const {
    DCHECK_LT(existing_index_, existing_->size());
    return existing_->Get(existing_index_);
  }

 private:
  void UpdateInternal() {
    const bool prev_is_existing = cur_is_existing_;
    if (!IsExisting(existing_index_, vec_index_, &cur_is_existing_)) {
      done_ = true;
      return;
    }
    bool next_is_existing = false;
    const int next_existing_index =
        cur_is_existing_ ? NextExistingIndex(existing_index_ + 1, true) : existing_index_;
    const int next_vec_index = cur_is_existing_ ? vec_index_ : vec_index_ + 1;
    const bool has_next = IsExisting(next_existing_index, next_vec_index, &next_is_existing);

    // Always append the row fresh if it is an update
    // (!cur_is_existing_), or either the previous or next is not
    // existing.
    should_append_ = !cur_is_existing_ || !prev_is_existing || !next_is_existing;
    // If we're going to append, include the activity id in
    // the activity ids set, so we skip all rows.
    if (should_append_ && cur_is_existing_) {
      activity_ids_.insert(existing_->Get(existing_index_).activity_id());
    }

    if (cur_ah_.get() || cur_index_ != -1) {
      prev_ah_ = cur_ah_;
      prev_index_ = cur_index_;
    } else {
      prev_ah_ = ActivityHandle();
      prev_index_ = -1;
    }
    if (cur_is_existing_) {
      cur_ah_ = ActivityHandle();
      cur_index_ = existing_index_;
    } else {
      cur_ah_ = ah_vec_[vec_index_];
      cur_index_ = -1;
    }
    if (!has_next) {
      next_ah_ = ActivityHandle();
      next_index_ = -1;
    } else if (next_is_existing) {
      next_ah_ = ActivityHandle();
      next_index_ = next_existing_index;
    } else {
      next_ah_ = ah_vec_[next_vec_index];
      next_index_ = -1;
    }
  }

  ActivityHandle LoadActivity(int index) {
    const int64_t activity_id = existing_->Get(index).activity_id();
    return state_->activity_table()->LoadActivity(activity_id, db_);
  }

  int NextExistingIndex(int index, bool skip_same_id) const {
    while (index < existing_->size() &&
           (ContainsKey(activity_ids_, existing_->Get(index).activity_id()) ||
            (skip_same_id && index > 0 &&
             existing_->Get(index).activity_id() == existing_->Get(index - 1).activity_id()) ||
            existing_->Get(index).type() == ViewpointSummaryMetadata::HEADER)) {
      ++index;
    }
    return index;
  }

  bool IsExisting(int existing_index, int vec_index, bool* is_existing) const {
    if (existing_index < existing_->size() &&
        vec_index < ah_vec_.size()) {
      if (existing_->Get(existing_index).timestamp() <
          ah_vec_[vec_index]->timestamp()) {
        *is_existing = true;
      } else {
        *is_existing = false;
      }
    } else if (existing_index < existing_->size()) {
      *is_existing = true;
    } else if (vec_index < ah_vec_.size()) {
      *is_existing = false;
    } else {
      // Case where the next is past the end of the iteration.
      *is_existing = true;
      return false;
    }
    return true;
  }

 private:
  AppState* const state_;
  const DBHandle db_;
  const ActivityRowArray* existing_;
  vector<ActivityHandle> ah_vec_;
  std::unordered_set<int64_t> activity_ids_;
  int existing_index_;
  int vec_index_;
  int64_t cur_index_;
  int64_t prev_index_;
  int64_t next_index_;
  ActivityHandle cur_ah_;
  ActivityHandle prev_ah_;
  ActivityHandle next_ah_;
  bool done_;
  bool should_append_;
  bool cur_is_existing_;
};

}  // unnamed namespace


bool IsThreadTypeCombine(ActivityThreadType type) {
  return (type == THREAD_COMBINE ||
          type == THREAD_COMBINE_NEW_USER ||
          type == THREAD_COMBINE_END ||
          type == THREAD_COMBINE_WITH_TIME ||
          type == THREAD_COMBINE_NEW_USER_WITH_TIME ||
          type == THREAD_COMBINE_END_WITH_TIME);
}


////
// Event
// TODO(spencer): move this code below the Trapdoor object so it matches
//   the header file.

// Threshold between being near a "top" location (home) and far (away).
const double DayTable::Event::kHomeVsAwayThresholdMeters = 50 * 1000;  // 50km

// Geographic distance (in meters) before events are split when close
// to a "top" location.
const double DayTable::Event::kHomeThresholdMeters = 2.5 * 1000;  // 2.5km
// Threshold for distance (in meters) when not close to a "top" location.
const double DayTable::Event::kAwayThresholdMeters = 10 * 1000;  // 10km

// Time in seconds before events are split when close to a "top" location.
const double DayTable::Event::kHomeThresholdSeconds = 4 * 60 * 60;  // 4 hours
// Threshold for time (in seconds) when far from a "top" location.
const double DayTable::Event::kAwayThresholdSeconds = 6 * 60 * 60;  // 6 hours

// Time in seconds by which events can be extended past the trailing
// edge of the threshold to include episodes nearby in time.
const double DayTable::Event::kExtendThresholdRatio = 0.25;  // 25%

// Threshold distance in meters from top location to be considered "exotic".
const double DayTable::Event::kExoticThresholdMeters = 1000 * 1000;


DayTable::Event::Event(AppState* state, const DBHandle& db)
    : state_(state),
      db_(db) {
}

string DayTable::Event::FormatTitle(bool shorten) const {
  string exotic_suffix;
  if (distance() >= kExoticThresholdMeters) {
    exotic_suffix = kBoldSpaceSymbol + kBoldCompassSymbol;
  }

  if (has_title()) {
    // If we have a title from trapdoors we've contributed to, blend that with location.
    string loc_str;
    if (has_location() && has_placemark()) {
      if (shorten) {
        // Use just locality or sublocality for short location.
        state_->placemark_histogram()->FormatLocality(
            location(), placemark(), &loc_str);
        return Format("%s%s%s%s%s", ToUppercase(loc_str), exotic_suffix,
                      kSpaceSymbol, kSpaceSymbol, short_title());
      } else {
        // Otherwise, use shortened format of location.
        state_->placemark_histogram()->FormatLocation(
            location(), placemark(), true, &loc_str);
        return Format("%s%s%s%s%s", ToUppercase(loc_str), exotic_suffix,
                      kSpaceSymbol, kSpaceSymbol, title());
      }
    } else {
      return shorten ? short_title() : title();
    }
  }

  // Otherwise, use location if available, holiday, or default title.
  return FormatLocation(shorten, true /* uppercase */);
}

string DayTable::Event::FormatLocation(bool shorten, bool uppercase) const {
  string title;
  state_->day_table()->IsHoliday(CanonicalizeTimestamp(earliest_timestamp()), &title);
  if (has_location() && has_placemark()) {
    string loc_str;
    state_->placemark_histogram()->FormatLocation(
        location(), placemark(), shorten, &loc_str);
    if (!title.empty()) {
      return Format("%s%s%s%s", uppercase ? ToUppercase(loc_str) : loc_str,
                    kSpaceSymbol, kSpaceSymbol, title);
    } else {
      return Format("%s", uppercase ? ToUppercase(loc_str) : loc_str);
    }
  } else if (!title.empty()) {
    return title;
  }
  return shorten ? "" : "Location Unavailable";
}

string DayTable::Event::FormatRelatedConvos(bool shorten) const {
  if (!trapdoors_.size()) {
    return "";
  }
  string display_title;
  if (has_title()) {
    display_title = shorten ? short_title() : title();
  } else {
    ViewpointHandle vh =
        state_->viewpoint_table()->LoadViewpoint(trapdoors_[0]->viewpoint_id(), db_);
    if (!vh.get()) {
      return "";
    }
    display_title = vh->FormatTitle(shorten, true);
  }
  if (trapdoors_.size() == 1 || shorten) {
    return display_title;
  }
  return Format("%s and %d other%s", display_title, trapdoors_.size() - 1,
                Pluralize(trapdoors_.size() - 1));
}

string DayTable::Event::FormatTimestamp(bool shorten) const {
  return shorten ?
      FormatShortRelativeDate(latest_timestamp(), state_->WallTime_Now()) :
      FormatRelativeDate(latest_timestamp(), state_->WallTime_Now());
}

string DayTable::Event::FormatTimeRange(bool shorten) const {
  return shorten ?
      FormatRelativeTime(latest_timestamp(), state_->WallTime_Now()) :
      ::FormatTimeRange(earliest_timestamp(), latest_timestamp());
}

string DayTable::Event::FormatContributors(bool shorten) const {
  vector<string> contrib_vec;
  GetContributors(state_, contributors(), 0, shorten, &contrib_vec);
  if (shorten) {
    return contrib_vec.size() > 0 ? contrib_vec[0] : "";
  } else {
    return Join(contrib_vec, ", ");
  }
}

string DayTable::Event::FormatPhotoCount() const {
  return LocalizedNumberFormat(photo_count());
}

bool DayTable::Event::IsEmpty() const {
  return photo_count() == 0;
}

bool DayTable::Event::WithinTimeRange(
    const CachedEpisode* anchor, WallTime timestamp, double margin_secs) {
  const WallTime start_time = anchor->earliest_photo_timestamp() - margin_secs;
  const WallTime end_time = anchor->latest_photo_timestamp() + margin_secs;
  return timestamp >= start_time && timestamp <= end_time;
}

bool DayTable::Event::ContainsPhotosFromEpisode(const CachedEpisode* ce) {
  for (int i = 0; i < ce->photos_size(); ++i) {
    if (ContainsKey(photo_ids_, ce->photos(i).photo_id())) {
      return true;
    }
  }
  return false;
}

bool DayTable::Event::CanAddEpisode(
    const CachedEpisode* anchor, const CachedEpisode* ce, float threshold_ratio) {
  // Determine whether any photos in this episode are already in the
  // anchor episode--that implies the episode and an episode in the event have
  // a common ancestor.
  if (ContainsPhotosFromEpisode(ce)) {
    return true;
  }

  // Is within the close home threshold of time?
  const bool within_time_range = WithinTimeRange(
      anchor, ce->timestamp(), kHomeThresholdSeconds * threshold_ratio);

  // TODO(spencer): should we factor in whether or not the episode
  // is part of a viewpoint that is part of this event?

  // See if locations are similar enough to group.
  if (ce->has_location() && anchor->has_location()) {
    // Look at the distance as a function of how far anchor episode is
    // from nearest "top" location.
    double dist_to_top;
    if (state_->placemark_histogram()->DistanceToLocation(anchor->location(), &dist_to_top)) {
      const double dist_threshold =
          threshold_ratio * ((dist_to_top < kHomeVsAwayThresholdMeters) ?
                             kHomeThresholdMeters : kAwayThresholdMeters);
      const double time_threshold =
          threshold_ratio * ((dist_to_top < kHomeVsAwayThresholdMeters) ?
                             kHomeThresholdSeconds : kAwayThresholdSeconds);
      const bool within_time_range = WithinTimeRange(anchor, ce->timestamp(), time_threshold);
      const double dist = DistanceBetweenLocations(anchor->location(), ce->location());
      if (dist < dist_threshold && within_time_range) {
        return true;
      }
    } else {
      // If for some reason the distance-to-location didn't work, base
      // the decision off distance between locations compared to
      // tightest, "home" threshold distance.
      const float dist = DistanceBetweenLocations(anchor->location(), ce->location());
      const double dist_threshold = kHomeThresholdMeters * threshold_ratio;
      if (dist < dist_threshold && within_time_range) {
        return true;
      }
    }
  } else if (within_time_range) {
    // Without locations, fall back to whether the two episodes contain
    // photos contributed by the same user(s).
    return true;
  }

  return false;
}

void DayTable::Event::AddEpisode(const CachedEpisode* ce) {
  // Keep track of earliest and latest timestamps.
  if (!has_earliest_timestamp()) {
    set_earliest_timestamp(std::numeric_limits<WallTime>::max());
    set_latest_timestamp(0);
  }
  set_earliest_timestamp(std::min<double>(earliest_timestamp(), ce->earliest_photo_timestamp()));
  set_latest_timestamp(std::max<double>(latest_timestamp(), ce->latest_photo_timestamp()));

  episodes_.push_back(ce);
  for (int i = 0; i < ce->photos_size(); ++i) {
    photo_ids_.insert(ce->photos(i).photo_id());
  }
}

const EventMetadata& DayTable::Event::Canonicalize() {
  CHECK_GT(episodes_.size(), 0);
  CanonicalizeEpisodes();
  CanonicalizeLocation();
  CanonicalizeTrapdoors();
  Cleanup();
  return *this;
}

void DayTable::Event::Cleanup() {
  episodes_.clear();
  photo_ids_.clear();
}

void DayTable::Event::CanonicalizeEpisodes() {
  // Sort the episodes by earliest photo timestamp and number of photos.
  std::sort(episodes_.begin(), episodes_.end(), CachedEpisodeLessThan());
  // Map from user id to contributed photo count.
  std::unordered_map<int64_t, int> contributors;

  // Now, build vector of filtered episodes based on that ordering
  // by eliminating duplicative photo ids.
  std::unordered_set<int64_t> unique_photo_ids;
  int count = 0;
  for (int i = 0; i < episodes_.size(); ++i) {
    const CachedEpisode* ce = episodes_[i];
    FilteredEpisode* f_ep = add_episodes();
    f_ep->set_episode_id(ce->id().local_id());
    // Don't include photos from episodes which aren't in library.
    // We do want episode id however, as this is used to locate an
    // episode from a conversation containing photos from the event.
    if (!ce->in_library()) {
      continue;
    }
    for (int j = 0; j < ce->photos_size(); ++j) {
      if (!ContainsKey(unique_photo_ids, ce->photos(j).photo_id())) {
        unique_photo_ids.insert(ce->photos(j).photo_id());
        f_ep->add_photo_ids(ce->photos(j).photo_id());
        // Add contributors, including current user. If current user is
        // sole contributor, no contributors are added.
        contributors[episodes_[i]->user_id()] += 1;
        count += 1;
      }
    }
  }
  // Reset photo_count to account for duplicates.
  set_photo_count(count);

  // Sort contributors by contributed photo counts.
  vector<std::pair<int, int64_t> > by_count;
  for (std::unordered_map<int64_t, int>::iterator iter = contributors.begin();
       iter != contributors.end();
       ++iter) {
    by_count.push_back(std::make_pair(iter->second, iter->first));
  }
  // Clear contributors vector if it contains only the user.
  if (by_count.size() == 1 && by_count.back().second == state_->user_id()) {
    by_count.clear();
  }

  // Sort in order of most to least contributed photos.
  std::sort(by_count.begin(), by_count.end(), std::greater<std::pair<int, int64_t> >());
  for (int i = 0; i < by_count.size(); ++i) {
    const int64_t user_id = by_count[i].second;
    DayContributor contrib;
    if (!InitializeContributor(state_, &contrib, user_id, "")) {
      continue;
    }
    contrib.set_type(DayContributor::VIEWED_CONTENT);
    contrib.Swap(add_contributors());
  }
}

void DayTable::Event::CanonicalizeLocation() {
  // Compute the location centroid and find an actual location nearest
  // the centroid to choose its placemark. This helps to correct for
  // spurious reverse geo-locations.
  Location centroid;
  int count = 0;
  for (int i = 0; i < episodes_.size(); ++i) {
    if (episodes_[i]->has_location() &&
        IsValidPlacemark(episodes_[i]->placemark())) {
      const Location& location = episodes_[i]->location();
      centroid.set_latitude(centroid.latitude() + location.latitude());
      centroid.set_longitude(centroid.longitude() + location.longitude());
      centroid.set_accuracy(centroid.accuracy() + location.accuracy());
      centroid.set_altitude(centroid.altitude() + location.altitude());
      ++count;
    }
  }

  if (count == 0) {
    return;
  }

  centroid.set_latitude(centroid.latitude()  / count);
  centroid.set_longitude(centroid.longitude() / count);
  centroid.set_accuracy(centroid.accuracy() / count);
  centroid.set_altitude(centroid.altitude() / count);

  // Locate the episode closest to the centroid.
  int closest_index = -1;
  double closest_distance = std::numeric_limits<double>::max();
  for (int i = 0; i < episodes_.size(); ++i) {
    if (episodes_[i]->has_location() &&
        IsValidPlacemark(episodes_[i]->placemark())) {
      const double distance = DistanceBetweenLocations(
          centroid, episodes_[i]->location());
      if (distance < closest_distance) {
        closest_distance = distance;
        closest_index = i;
      }
    }
  }

  // Use the location & placemark of the closest episode.
  if (closest_index != -1) {
    mutable_location()->CopyFrom(episodes_[closest_index]->location());
    mutable_placemark()->CopyFrom(episodes_[closest_index]->placemark());

    // Handle case of pending reverse geocode.
    // TODO(spencer): we really should be returning this more elegantly.
    if (!IsValidPlacemark(placemark())) {
      clear_placemark();
    }
    double distance;
    if (state_->placemark_histogram()->DistanceToLocation(location(), &distance)) {
      set_distance(distance);
    }
  }
}

void DayTable::Event::CanonicalizeTrapdoors() {
  if (trapdoors_.empty()) {
    return;
  }
  int contributor_count_max = 0;
  int photo_count_max = 0;
  vector<TrapdoorProfile> profiles;
  for (int i = 0; i < trapdoors_.size(); ++i) {
    // Can only access Trapdoor::viewpoint_ before canonicalization.
    const string title = trapdoors_[i]->viewpoint_->title();
    // Compute contributor count before canonicalization.
    const int contrib_count = trapdoors_[i]->contributors_.size();
    // See if this trapdoor contains the anchor episode for the viewpoint...
    EpisodeHandle anchor = trapdoors_[i]->viewpoint_->GetAnchorEpisode(NULL);
    bool includes_anchor = false;
    if (anchor.get()) {
      for (int j = 0; j < trapdoors_[i]->episodes_.size(); ++j) {
        const int64_t local_id = trapdoors_[i]->episodes_[j].first->id().local_id();
        if (local_id == anchor->id().local_id()) {
          includes_anchor = true;
          break;
        }
      }
    }

    *add_trapdoors() = trapdoors_[i]->Canonicalize();

    if (!title.empty() && includes_anchor) {
      profiles.push_back(
          TrapdoorProfile(trapdoors_[i]->photo_count(), contrib_count, title));
      photo_count_max = std::max<int>(photo_count_max,
                                      profiles.back().photo_count);
      contributor_count_max = std::max<int>(contributor_count_max,
                                            profiles.back().contrib_count);
    }
  }

  if (!profiles.empty()) {
    const float kContribWeight = 0.55;
    const float kPhotosWeight = 0.45;
    vector<std::pair<float, int> > weighted_indexes;
    for (int i = 0; i < profiles.size(); ++i) {
      const float norm_contrib = contributor_count_max ?
                                 (profiles[i].contrib_count / contributor_count_max) : 0;
      const float norm_photo = photo_count_max ?
                               (profiles[i].photo_count / photo_count_max) : 0;
      const float weight = kContribWeight * norm_contrib + kPhotosWeight * norm_photo;
      weighted_indexes.push_back(std::make_pair(weight, i));
    }
    sort(weighted_indexes.begin(), weighted_indexes.end(),
         std::greater<std::pair<float, int> >());
    const string& best_title = profiles[weighted_indexes.front().second].title;
    set_title(NormalizeWhitespace(best_title));
    set_short_title(title());
  }
}


////
// Trapdoor

DayTable::Trapdoor::Trapdoor(AppState* state, const DBHandle& db)
    : state_(state),
      db_(db) {
}

string DayTable::Trapdoor::FormatTimestamp(bool shorten) const {
  return shorten ?
      FormatShortRelativeDate(earliest_timestamp(), state_->WallTime_Now()) :
      FormatRelativeDate(earliest_timestamp(), state_->WallTime_Now());
}

string DayTable::Trapdoor::FormatTimeAgo() const {
  return ::FormatTimeAgo(latest_timestamp(), state_->WallTime_Now(), TIME_AGO_SHORT);
}

string DayTable::Trapdoor::FormatContributors(
    bool shorten, int contributor_mask) const {
  vector<string> contrib_vec;
  GetContributors(state_, contributors(), contributor_mask, shorten, &contrib_vec);
  if (shorten) {
    return contrib_vec.size() > 0 ? contrib_vec[0] : "";
  } else {
    return Join(contrib_vec, ", ");
  }
}

string DayTable::Trapdoor::FormatPhotoCount() const {
  return LocalizedNumberFormat(photo_count());
}

string DayTable::Trapdoor::FormatCommentCount() const {
  return LocalizedNumberFormat(comment_count());
}

bool DayTable::Trapdoor::DisplayInSummary() const {
  // Display inbox trapdoors in the summary which have
  // unviewed content.
  if (type() == INBOX) {
    return unviewed_content();
  } else {
    return false;
  }
}

bool DayTable::Trapdoor::DisplayInInbox() const {
  // Display all inbox trapdoors.
  return type() == INBOX;
}

bool DayTable::Trapdoor::DisplayInEvent() const {
  // Display all event trapdoors in event view. You can access all
  // EVENT trapdoors from the event view.
  return type() == EVENT;
}

bool DayTable::Trapdoor::IsEmpty() const {
  return photo_count() == 0 && comment_count() == 0;
}

ViewpointHandle DayTable::Trapdoor::GetViewpoint() const {
  return state_->viewpoint_table()->LoadViewpoint(viewpoint_id(), db_);
}

void DayTable::Trapdoor::InitFromViewpointSummary(const ViewpointSummaryMetadata& vs) {
  viewpoint_ = state_->viewpoint_table()->LoadViewpoint(vs.viewpoint_id(), db_);

  set_viewpoint_id(viewpoint_->id().local_id());
  set_type(Trapdoor::INBOX);

  if (vs.has_cover_photo()) {
    mutable_cover_photo()->CopyFrom(vs.cover_photo());
  }
  set_earliest_timestamp(vs.earliest_timestamp());
  set_latest_timestamp(vs.latest_timestamp());

  set_photo_count(vs.photo_count());
  set_comment_count(vs.comment_count());
  set_new_photo_count(vs.new_photo_count());
  set_new_comment_count(vs.new_comment_count());

  // Determine unviewed / pending content flags and sample photos from
  // most recent to least recent.
  std::unordered_set<int64_t> unique_photo_ids;
  for (int i = vs.activities_size() - 1; i >= 0; --i) {
    const ViewpointSummaryMetadata::ActivityRow& row = vs.activities(i);
    const bool unviewed = row.update_seq() > viewpoint_->viewed_seq();
    if (unviewed) {
      set_unviewed_content(true);
    }
    // Sample photos if we have fewer than the trapdoor photo count.
    if (row.type() == ViewpointSummaryMetadata::HEADER ||
        row.type() == ViewpointSummaryMetadata::PHOTOS) {
      for (int j = row.photos_size() - 1; j >= 0; --j) {
        const int64_t photo_id = row.photos(j).photo_id();
        if (ContainsKey(unique_photo_ids, photo_id)) {
          continue;
        }
        unique_photo_ids.insert(photo_id);
        PhotoHandle ph = state_->photo_table()->LoadPhoto(photo_id, db_);
        if (!ph.get()) {
          continue;
        }
        DayPhoto* photo = add_photos();
        photo->set_photo_id(ph->id().local_id());
        photo->set_episode_id(row.photos(j).episode_id());
        photo->set_aspect_ratio(ph->aspect_ratio());
        photo->set_timestamp(ph->timestamp());
      }
    }
    if (row.pending()) {
      set_pending_content(true);
    }
  }

  if (viewpoint_->label_muted()) {
    set_muted(true);
  }
  if (viewpoint_->label_autosave()) {
    set_autosave(true);
  }

  // Transfer contributors & canonicalize. We must do this after we've
  // determined whether there's new content.
  for (int i = 0; i < vs.contributors_size(); ++i) {
    if (vs.contributors(i).user_id()) {
      contributors_[vs.contributors(i).user_id()] =
          vs.contributors(i).update_seq();
    } else {
      contributors_by_identity_[vs.contributors(i).identity()] =
          vs.contributors(i).update_seq();
    }
  }
  CanonicalizeContributors();
}

void DayTable::Trapdoor::AddSharedEpisode(
    const ActivityHandle& ah, const CachedEpisode* ce) {
  if (!ah->has_share_new() && !ah->has_share_existing()) {
    return;
  }

  if (!has_earliest_timestamp()) {
    // Initialize first and last timestamps.
    set_earliest_timestamp(ah->timestamp());
    set_latest_timestamp(ah->timestamp());
  } else {
    CHECK_EQ(viewpoint_id(), ah->viewpoint_id().local_id());
    set_earliest_timestamp(std::min<double>(earliest_timestamp(), ah->timestamp()));
    set_latest_timestamp(std::max<double>(latest_timestamp(), ah->timestamp()));
  }

  if (ah->upload_activity()) {
    set_pending_content(true);
  }

  episodes_.push_back(std::make_pair(ce, false));

  // Add sharees if available.
  if (ah->has_share_new()) {
    for (int i = 0; i < ah->share_new().contacts_size(); ++i) {
      if (ah->share_new().contacts(i).has_user_id()) {
        const int64_t user_id = ah->share_new().contacts(i).user_id();
        if (user_id) {
          contributors_[user_id] =
              std::max<double>(contributors_[user_id], ah->update_seq());
        } else {
          const string& identity = ah->share_new().contacts(i).primary_identity();
          contributors_by_identity_[identity] =
              std::max<double>(contributors_by_identity_[identity], ah->update_seq());
        }
      }
    }
  }

  // Add contributor.
  contributors_[ah->user_id()] =
      std::max<double>(contributors_[ah->user_id()], ah->update_seq() + 0.1);
}

const TrapdoorMetadata& DayTable::Trapdoor::Canonicalize() {
  CHECK(has_viewpoint_id());

  SamplePhotos();
  MaybeSetCoverPhoto();
  CanonicalizeContributors();

  Cleanup();
  return *this;
}

void DayTable::Trapdoor::Cleanup() {
  viewpoint_.reset();
  contributors_.clear();
  contributors_by_identity_.clear();
}

void DayTable::Trapdoor::SamplePhotos() {
  // Go through all episodes and build a vector of episode
  // photo id lists for episodes shared from an unviewed activity.
  int available_count = 0;
  for (int i = 0; i < episodes_.size(); ++i) {
    const CachedEpisode* ce = episodes_[i].first;
    const bool new_episode = episodes_[i].second;

    // Update photo counts only in the case of an EVENT type trapdoor.
    if (type() == EVENT) {
      if (new_episode) {
        set_new_photo_count(new_photo_count() + ce->photos_size());
      }
      set_photo_count(photo_count() + ce->photos_size());
    }
    available_count += ce->photos_size();
  }

  // Sample photo ids using round-robin.
  std::unordered_set<int64_t> sampled_ids;
  int sample_count = std::min<int>(available_count, kTrapdoorPhotoCount);
  // Maintain vector as a pair of (episode rank, photo) for proper sorting.
  vector<std::pair<int, const DayPhoto*> > photos;
  for (int round = 0, count = 0; count < sample_count; ++round) {
    bool found = false;  // safety check in case we can't meet sampling target
    for (int i = 0; i < episodes_.size() && count < sample_count; ++i) {
      const CachedEpisode* ce = episodes_[i].first;
      if (round < ce->photos_size() &&
          !ContainsKey(sampled_ids, ce->photos(round).photo_id())) {
        sampled_ids.insert(ce->photos(round).photo_id());  // prevent duplicates
        photos.push_back(std::make_pair(i, &ce->photos(round)));
        count++;
        found = true;
      }
    }
    if (!found) {
      // We ran out of photos to sample because of duplicates.
      break;
    }
  }
  // Sort photos by timestamp in ascending order and copy to sample array.
  std::sort(photos.begin(), photos.end(), EpisodePhotoLessThan());
  for (int i = 0; i < photos.size(); ++i) {
    add_photos()->CopyFrom(*photos[i].second);
  }
  if (sample_count < available_count) {
    set_sub_sampled(true);
  }
}

void DayTable::Trapdoor::MaybeSetCoverPhoto() {
  int64_t cover_photo_id;
  int64_t cover_episode_id;
  WallTime cover_timestamp;
  float cover_aspect_ratio;
  if (viewpoint_->GetCoverPhoto(&cover_photo_id,
                                &cover_episode_id,
                                &cover_timestamp,
                                &cover_aspect_ratio)) {
    mutable_cover_photo()->set_photo_id(cover_photo_id);
    mutable_cover_photo()->set_episode_id(cover_episode_id);
    mutable_cover_photo()->set_timestamp(cover_timestamp);
    mutable_cover_photo()->set_aspect_ratio(cover_aspect_ratio);
  }
}

void DayTable::Trapdoor::CanonicalizeContributors() {
  // The update sequence is a floating point value to allow the
  // user adding additional users to sort first.
  vector<std::pair<double, std::pair<int64_t, string> > > by_update_seq;
  for (std::unordered_map<int64_t, double>::iterator iter = contributors_.begin();
       iter != contributors_.end();
       ++iter) {
    // Add the user himself only if there is one contributor.
    if (iter->first != state_->user_id() ||
        (contributors_.size() + contributors_by_identity_.size()) == 1) {
      by_update_seq.push_back(std::make_pair(iter->second, std::make_pair(iter->first, "")));
    }
  }
  for (std::unordered_map<string, double>::iterator iter = contributors_by_identity_.begin();
       iter != contributors_by_identity_.end();
       ++iter) {
    by_update_seq.push_back(std::make_pair(iter->second, std::make_pair(0, iter->first)));
  }
  // Sort in order of most to least recent contributions.
  std::sort(by_update_seq.begin(), by_update_seq.end(),
            std::greater<std::pair<double, std::pair<int64_t, string> > >());
  for (int i = 0; i < by_update_seq.size(); ++i) {
    const int max_update_seq = int(by_update_seq[i].first);
    const int64_t user_id = by_update_seq[i].second.first;
    const string& identity = by_update_seq[i].second.second;
    DayContributor contrib;
    if (!InitializeContributor(state_, &contrib, user_id, identity)) {
      continue;
    }
    if (max_update_seq > viewpoint_->viewed_seq() && unviewed_content()) {
      contrib.set_type(DayContributor::UNVIEWED_CONTENT);
    } else {
      contrib.set_type(DayContributor::VIEWED_CONTENT);
    }
    contrib.Swap(add_contributors());
  }
  // Go through list of viewpoint followers and add any that haven't
  // already been included in contributors.
  vector<int64_t> follower_ids;
  viewpoint_->ListFollowers(&follower_ids);
  for (int i = 0; i < follower_ids.size(); ++i) {
    if (!ContainsKey(contributors_, follower_ids[i])) {
      DayContributor contrib;
      if (!InitializeContributor(state_, &contrib, follower_ids[i], "")) {
        continue;
      }
      contrib.set_type(DayContributor::NO_CONTENT);
      contrib.Swap(add_contributors());
    }
  }
}


////
// Day

DayTable::Day::Day(AppState* state, WallTime timestamp, const DBHandle& db)
    : state_(state),
      db_(db) {
  CHECK_EQ(timestamp, CanonicalizeTimestamp(timestamp));
  metadata_.set_timestamp(timestamp);
}

bool DayTable::Day::Load() {
  // Get the day metadata from the snapshot database.
  return db_->GetProto(EncodeDayKey(timestamp()), &metadata_);
}

void DayTable::Day::Save(
    vector<Event>* events, const DBHandle& updates) {
  std::sort(events->begin(), events->end(), EventTimestampGreaterThan());
  for (int i = 0; i < events->size(); ++i) {
    const EventMetadata& event = (*events)[i].Canonicalize();
    if ((*events)[i].IsEmpty()) {
      // NOTE: this is O(N) and if a large number of events occur on a day,
      // this code should be revamped for efficiency.
      events->erase(events->begin() + i);
      --i;
      continue;
    }
    updates->PutProto(EncodeDayEventKey(timestamp(), i), event);
  }

  updates->PutProto(EncodeDayKey(metadata_.timestamp()), metadata_);
}

void DayTable::Day::Rebuild(vector<Event>* events, const DBHandle& updates) {
  // Build a vector of all episodes which occurred on this day.
  const WallTime end_timestamp = NextDay(timestamp()) + kPracticalDayOffset;
  for (ScopedPtr<EpisodeTable::EpisodeIterator> iter(
           state_->episode_table()->NewEpisodeIterator(timestamp(), false, db_));
       !iter->done() && iter->timestamp() < end_timestamp;
       iter->Next()) {
    EpisodeHandle eh = state_->episode_table()->LoadEpisode(iter->episode_id(), db_);
    if (eh.get()) {
      CachedEpisode* ce = metadata_.add_episodes();
      InitCachedEpisode(state_, eh, ce, db_);
    }
  }

  SegmentEvents(events);
  Save(events, updates);
}

void DayTable::Day::UpdateEpisodes(
    const vector<int64_t>& episode_ids, vector<Event>* events, const DBHandle& updates) {
  for (int i = 0; i < episode_ids.size(); i++) {
    // Look for existing episode with this id to replace that entry.
    // NOTE: this is O(N*M), but we expect N & M to be small.
    int existing_index = -1;
    for (int j = 0; j < metadata_.episodes_size(); ++j) {
      if (metadata_.episodes(j).id().local_id() == episode_ids[i]) {
        existing_index = j;
        break;
      }
    }

    EpisodeHandle eh = state_->episode_table()->LoadEpisode(episode_ids[i], db_);
    if (IsEpisodeFullyLoaded(eh)) {
      CachedEpisode* ce;
      if (existing_index == -1) {
        ce = metadata_.add_episodes();
      } else {
        ce = metadata_.mutable_episodes(existing_index);
        ce->Clear();
      }
      InitCachedEpisode(state_, eh, ce, db_);
    } else if (existing_index != -1) {
      // In this instance, we found an existing cached episode, but have
      // since discovered it shouldn't be in the library, so it must be
      // removed; swap with last element and remove last.
      ProtoRepeatedFieldRemoveElement(metadata_.mutable_episodes(), existing_index);
    }
  }

  SegmentEvents(events);
  Save(events, updates);
}

void DayTable::Day::SegmentEvents(vector<Event>* events) {
  std::sort(metadata_.mutable_episodes()->pointer_begin(),
            metadata_.mutable_episodes()->pointer_end(),
            CachedEpisodeLessThan());

  // Create a vector of the cached episodes for segmentation.
  vector<const CachedEpisode*> episodes;
  vector<const CachedEpisode*> shared_episodes;
  for (int i = 0; i < metadata_.episodes_size(); ++i) {
    const CachedEpisode* ce = &metadata_.episodes(i);
    if (ce->in_library()) {
      episodes.push_back(ce);
    } else {
      shared_episodes.push_back(ce);
    }
  }
  std::reverse(episodes.begin(), episodes.end());

  events->clear();

  // While there are still episodes:
  // - Create event with least recent episode
  // - Match any remaining episodes to first episode based on thresholds
  // - For each episode (E) added in previous step...
  //   - Match remaining episodes to (E) based on extended threshold ratio
  while (!episodes.empty()) {
    // Create event with least recent episode.
    const CachedEpisode* ce = episodes.back();  // episodes was reversed, so least recent is last
    events->push_back(Event(state_, db_));
    events->back().AddEpisode(ce);
    episodes.pop_back();

    // Match remaining episodes to event based on first episode.
    vector<const CachedEpisode*> matched;
    for (int i = 0; i < episodes.size(); ++i) {
      if (events->back().CanAddEpisode(ce, episodes[i], 1.0)) {
        matched.push_back(episodes[i]);
        events->back().AddEpisode(episodes[i]);
        episodes.erase(episodes.begin() + i);
        --i;
      }
    }

    // Now, match all remaining episodes to those matched in previous
    // step using extended thresholds.
    for (int i = 0; i < matched.size(); ++i) {
      for (int j = 0; j < episodes.size(); ++j) {
        if (events->back().CanAddEpisode(matched[i], episodes[j], Event::kExtendThresholdRatio)) {
          events->back().AddEpisode(episodes[j]);
          episodes.erase(episodes.begin() + j);
          --j;
        }
      }
    }
  }

  // For each shared episode, add to the first event which contains
  // any photos from the episode. These are used to create trapdoors
  // (links) between conversations and events in the library and vice
  // versa.
  for (int i = 0; i < shared_episodes.size(); ++i) {
    const CachedEpisode* ce = shared_episodes[i];
    for (int j = 0; j < events->size(); ++j) {
      if ((*events)[j].ContainsPhotosFromEpisode(ce)) {
        if (!ce->in_library()) {
          (*events)[j].AddEpisode(ce);
        }
        if (ce->has_viewpoint_id()) {
          ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
              ce->viewpoint_id(), db_);
          // Don't show viewpoint trapdoor in events if viewpoint is removed
          // or this is the default viewpoint.
          if (vh.get() && !vh->label_removed() && !vh->is_default()) {
            CreateEventTrapdoor(events, ce, vh, j);
          }
        }
      }
    }
  }
}

bool DayTable::Day::IsEpisodeFullyLoaded(const EpisodeHandle& eh) {
  return (eh.get() &&
          eh->has_timestamp() &&
          eh->has_earliest_photo_timestamp() &&
          eh->has_latest_photo_timestamp());
}

void DayTable::Day::InitCachedEpisode(
    AppState* state, const EpisodeHandle& eh, CachedEpisode* ce, const DBHandle& db,
    const std::unordered_set<string>* photo_id_filter) {
  ce->mutable_id()->CopyFrom(eh->id());
  if (eh->has_parent_id()) {
    ce->mutable_parent_id()->CopyFrom(eh->parent_id());
  }
  if (eh->has_viewpoint_id()) {
    ce->mutable_viewpoint_id()->CopyFrom(eh->viewpoint_id());
  }
  ce->set_user_id(eh->user_id());

  DCHECK(eh->has_timestamp());
  ce->set_timestamp(eh->timestamp());

  if (!eh->GetLocation(ce->mutable_location(), ce->mutable_placemark())) {
    ce->clear_location();
    ce->clear_placemark();
  }

  DCHECK(eh->has_earliest_photo_timestamp());
  ce->set_earliest_photo_timestamp(eh->earliest_photo_timestamp());

  DCHECK(eh->has_latest_photo_timestamp());
  ce->set_latest_photo_timestamp(eh->latest_photo_timestamp());

  vector<int64_t> photo_ids;
  eh->ListAllPhotos(&photo_ids);
  for (int i = 0; i < photo_ids.size(); ++i) {
    // Skip photo states which we should never display.
    if (eh->IsQuarantined(photo_ids[i]) ||
        eh->IsRemoved(photo_ids[i]) ||
        eh->IsUnshared(photo_ids[i])) {
      continue;
    }
    PhotoHandle ph = state->photo_table()->LoadPhoto(photo_ids[i], db);
    if (!ph.get() ||
        (photo_id_filter && !ContainsKey(*photo_id_filter, ph->id().server_id()))) {
      continue;
    }
    DayPhoto* photo = ce->add_photos();
    photo->set_photo_id(ph->id().local_id());
    photo->set_episode_id(eh->id().local_id());
    photo->set_aspect_ratio(ph->aspect_ratio());
    photo->set_timestamp(ph->timestamp());
  }

  ce->set_in_library(eh->InLibrary());
}

void DayTable::Day::CreateEventTrapdoor(
    vector<Event>* events, const CachedEpisode* ce,
    const ViewpointHandle& vh, int ev_index) {
  const int64_t vp_id = vh->id().local_id();
  TrapdoorHandle trap;
  bool found = false;
  for (int i = 0; i < (*events)[ev_index].trapdoors_.size(); ++i) {
    if ((*events)[ev_index].trapdoors_[i]->viewpoint_id() == vp_id) {
      trap = (*events)[ev_index].trapdoors_[i];
      found = true;
      break;
    }
  }
  if (!found) {
    trap = TrapdoorHandle(new Trapdoor(state_, db_));
    trap->set_viewpoint_id(vp_id);
    trap->set_type(Trapdoor::EVENT);
    trap->set_event_index(ev_index);
    trap->viewpoint_ = vh;
    (*events)[ev_index].trapdoors_.push_back(trap);
  }

  // Lookup the activity which shared this episode.
  vector<int64_t> activity_ids;
  state_->activity_table()->ListEpisodeActivities(ce->id().server_id(), &activity_ids, db_);
  if (activity_ids.size() > 0) {
    ActivityHandle ah = state_->activity_table()->LoadActivity(activity_ids[0], db_);
    if (ah.get()) {
      DCHECK(ah->has_share_new() || ah->has_share_existing());
      trap->AddSharedEpisode(ah, ce);
    }
  }
}


////
// Summary

const float DayTable::Summary::kPhotoVolumeWeightFactor = 2;
const float DayTable::Summary::kCommentVolumeWeightFactor = 1.5;
const float DayTable::Summary::kContributorWeightFactor = 1;
const float DayTable::Summary::kShareWeightFactor = 2;
const float DayTable::Summary::kDistanceWeightFactor = 2;
// TODO(spencer): This value is set so that any unviewed row will have a weight
// that is greater than any viewed row (sum-of-the-weight-factors *
// holiday-multiplier). Take another look at these values.
const float DayTable::Summary::kUnviewedWeightBonus = 30;

typedef google::protobuf::RepeatedPtrField<SummaryRow> SummaryRowArray;

DayTable::Summary::Summary(DayTable* day_table)
    : day_table_(day_table),
      photo_count_max_(0),
      comment_count_max_(0),
      contributor_count_max_(0),
      share_count_max_(0),
      distance_max_(0) {
}

DayTable::Summary::~Summary() {
}

bool DayTable::Summary::GetSummaryRow(int row_index, SummaryRow* row) const {
  if (row_index < 0 || row_index >= row_count()) {
    LOG("requested row index out of bounds %d from %d-%d",
        row_index, 0, row_count());
    return false;
  }

  row->CopyFrom(summary_.rows(row_index));
  return true;
}

int DayTable::Summary::GetSummaryRowIndex(WallTime timestamp, int64_t identifier) const {
  DCHECK_EQ(timestamp, int(timestamp));
  SummaryRow search_row;
  search_row.set_day_timestamp(timestamp);
  search_row.set_identifier(identifier);
  SummaryRowArray::const_iterator it =
      std::lower_bound(summary_.rows().begin(),
                       summary_.rows().end(),
                       search_row, SummaryRowGreaterThan());
  if (it != summary_.rows().end() &&
      it->day_timestamp() == timestamp &&
      it->identifier() == identifier) {
    return it - summary_.rows().begin();
  }
  return -1;
}

void DayTable::Summary::AddDayRows(
    WallTime timestamp, const vector<SummaryRow>& rows) {
  DCHECK_EQ(timestamp, int(timestamp));
  if (rows.empty()) {
    return;
  }
  for (int i = 0; i < rows.size(); ++i) {
    summary_.mutable_rows()->Add()->CopyFrom(rows[i]);
  }
  // Sort newly-added values.
  std::sort(summary_.mutable_rows()->pointer_begin(),
            summary_.mutable_rows()->pointer_end(),
            SummaryRowGreaterThan());
}

void DayTable::Summary::RemoveDayRows(WallTime timestamp) {
  DCHECK_EQ(timestamp, int(timestamp));
  SummaryRow start_row;
  start_row.set_day_timestamp(timestamp);
  start_row.set_identifier(0);
  SummaryRow end_row;
  end_row.set_day_timestamp(timestamp - kDayInSeconds);
  end_row.set_identifier(0);
  SummaryRowArray::pointer_iterator start_it =
      std::lower_bound(summary_.mutable_rows()->pointer_begin(),
                       summary_.mutable_rows()->pointer_end(),
                       &start_row, SummaryRowGreaterThan());
  SummaryRowArray::pointer_iterator end_it =
      std::lower_bound(summary_.mutable_rows()->pointer_begin(),
                       summary_.mutable_rows()->pointer_end(),
                       &end_row, SummaryRowGreaterThan());
  const int count = end_it - start_it;
  for (SummaryRowArray::pointer_iterator iter = start_it; iter != end_it; ++iter) {
    // Set timestamp to -1 so removed rows sort to end.
    (*iter)->set_day_timestamp(-1);
  }
  // Sort removed values to end and truncate.
  std::sort(summary_.mutable_rows()->pointer_begin(),
            summary_.mutable_rows()->pointer_end(),
            SummaryRowGreaterThan());
  for (int i = 0; i < count; ++i) {
    DCHECK_EQ(summary_.rows(summary_.rows_size() - 1).day_timestamp(), -1);
    if (summary_.rows(summary_.rows_size() - 1).day_timestamp() == -1) {
      summary_.mutable_rows()->RemoveLast();
    }
  }
}

void DayTable::Summary::AddRow(const SummaryRow& row) {
  summary_.mutable_rows()->Add()->CopyFrom(row);
  // Sort newly-added row.
  std::sort(summary_.mutable_rows()->pointer_begin(),
            summary_.mutable_rows()->pointer_end(),
            SummaryRowGreaterThan());
}

void DayTable::Summary::RemoveRow(int index) {
  CHECK(index >= 0 && index < summary_.rows_size())
      << "day table: trying to remove non-existent summary row " << index;
  const int start_size = summary_.rows_size();
  // Swap row to end and remove last.
  ProtoRepeatedFieldRemoveElement(summary_.mutable_rows(), index);
  // Sort swapped row back into order.
  std::sort(summary_.mutable_rows()->pointer_begin(),
            summary_.mutable_rows()->pointer_end(),
            SummaryRowGreaterThan());
  DCHECK_EQ(summary_.rows_size(), start_size - 1)
      << "after removing index " << index << " size went from "
      << start_size << " to " << summary_.rows_size();
}

bool DayTable::Summary::Load(const string& key, const DBHandle& db) {
  db_ = db;
  if (!db_->GetProto(key, &summary_)) {
    VLOG("day table: failed to load summary info %s", DBIntrospect::Format(key));
    return false;
  }
  return true;
}

void DayTable::Summary::Save(
    const string& key, const DBHandle& updates) {
  Normalize();
  updates->PutProto(key, summary_);
}

void DayTable::Summary::Normalize() {
  summary_.set_total_height(height_prefix());
  summary_.set_photo_count(0);
  summary_.set_unviewed_count(0);

  photo_count_max_ = 0;
  comment_count_max_ = 0;
  contributor_count_max_ = 0;
  share_count_max_ = 0;
  distance_max_ = 0;

  // Get count maximums and compute row positions & total height.
  for (int i = 0; i < summary_.rows_size(); ++i) {
    SummaryRow* row = summary_.mutable_rows(i);
    row->set_position(summary_.total_height());
    summary_.set_photo_count(summary_.photo_count() + row->photo_count());
    summary_.set_total_height(summary_.total_height() + row->height());

    photo_count_max_ =
        std::max<int>(photo_count_max_, row->photo_count());
    comment_count_max_ =
        std::max<int>(comment_count_max_, row->comment_count());
    contributor_count_max_ =
        std::max<int>(contributor_count_max_, row->contributor_count());
    share_count_max_ =
        std::max<int>(share_count_max_, row->share_count());
    distance_max_ =
        std::max<double>(distance_max_, row->distance());
    if (row->unviewed()) {
      summary_.set_unviewed_count(summary_.unviewed_count() + 1);
    }
  }
  summary_.set_total_height(summary_.total_height() + height_suffix());

  // Normalize row weights.
  WallTime last_day_timestamp = 0;
  bool is_holiday = false;
  for (int i = 0; i < summary_.rows_size(); ++i) {
    SummaryRow* row = summary_.mutable_rows(i);
    // Get the set of days which are holidays.
    if (row->day_timestamp() != last_day_timestamp) {
      is_holiday = state()->day_table()->IsHoliday(row->day_timestamp(), NULL);
      last_day_timestamp = row->day_timestamp();
    }

    NormalizeRowWeight(row, is_holiday);
  }
}

float DayTable::Summary::ComputeWeight(float value, float max, bool log_scale) const {
  if (value <= (log_scale ? 1 : 0) || max <= (log_scale ? 1 : 0)) {
    return 0;
  }
  if (log_scale) {
    return log(value) / log(max);
  }
  return value / max;
}

void DayTable::Summary::NormalizeRowWeight(SummaryRow* row, bool is_holiday) const {
  const float photo_weight =
      ComputeWeight(row->photo_count(), photo_count_max_, true);
  const float comment_weight =
      ComputeWeight(row->comment_count(), comment_count_max_, true);
  const float contributor_weight =
      ComputeWeight(row->contributor_count(), contributor_count_max_, true);
  const float share_weight =
      ComputeWeight(row->share_count(), share_count_max_, true);
  const float distance_weight =
      ComputeWeight(row->distance(), distance_max_, true);

  float weight = photo_weight * kPhotoVolumeWeightFactor +
                 comment_weight * kCommentVolumeWeightFactor +
                 contributor_weight * kContributorWeightFactor +
                 share_weight * kShareWeightFactor +
                 distance_weight * kDistanceWeightFactor;
  // Unviewed weight bonus.
  if (row->unviewed()) {
    weight += kUnviewedWeightBonus;
  }
  // 1.5x weight multiplier if a holiday.
  if (is_holiday) {
    weight *= 1.5;
  }
  row->set_weight(weight);
}


////
// EventSummary

DayTable::EventSummary::EventSummary(DayTable* day_table)
    : Summary(day_table) {
}

int DayTable::EventSummary::GetEpisodeRowIndex(int64_t episode_id) const {
  string key;
  if (db_->Get(EncodeEpisodeEventKey(episode_id), &key)) {
    WallTime timestamp;
    int64_t index;
    if (DecodeTimestampAndIdentifier(key, &timestamp, &index)) {
      return GetSummaryRowIndex(timestamp, index);
    } else {
      LOG("day table: failed to decode key %s", key);
    }
  }
  LOG("day table: failed to find row index for episode %d", episode_id);
  return -1;
}

void DayTable::EventSummary::GetViewpointRowIndexes(int64_t viewpoint_id, vector<int>* row_indexes) const {
  for (DB::PrefixIterator iter(db_, DBFormat::trapdoor_event_key(viewpoint_id, ""));
       iter.Valid();
       iter.Next()) {
    WallTime timestamp;
    int64_t index;
    if (DecodeTimestampAndIdentifier(iter.value(), &timestamp, &index)) {
      row_indexes->push_back(GetSummaryRowIndex(timestamp, index));
    } else {
      LOG("day table: failed to decode key %s", iter.value());
    }
  }
}

void DayTable::EventSummary::UpdateDay(
    WallTime timestamp, const vector<Event>& events,
    const DBHandle& updates) {
  RemoveDayRows(timestamp);

  vector<SummaryRow> rows(events.size());
  for (int i = 0; i < events.size(); ++i) {
    const Event& ev = events[i];

    SummaryRow& row = rows[i];
    row.set_type(SummaryRow::EVENT);
    row.set_timestamp(ev.earliest_timestamp());
    row.set_day_timestamp(int(timestamp));
    row.set_identifier(i);
    row.set_height(env()->GetSummaryEventHeight(ev, db_));
    row.set_photo_count(ev.photo_count());
    row.set_contributor_count(ev.contributors_size());
    row.set_distance(ev.distance());
    if (ev.episodes_size() > 0) {
      row.set_episode_id(ev.episodes(0).episode_id());
    }

    const string key = EncodeTimestampAndIdentifier(timestamp, i);
    int share_count = 0;
    for (int j = 0; j < ev.trapdoors().size(); ++j) {
      share_count += ev.trapdoors()[j]->photo_count() * ev.trapdoors()[j]->contributors_size();
      updates->Put<string>(EncodeTrapdoorEventKey(ev.trapdoors()[j]->viewpoint_id(), key), key);
    }
    row.set_share_count(share_count);

    // Add secondary index for all episode ids in the event pointing to the event's key.
    for (int j = 0; j < ev.episodes_size(); ++j) {
      updates->Put<string>(EncodeEpisodeEventKey(ev.episodes(j).episode_id()), key);
    }
  }

  AddDayRows(timestamp, rows);
}

bool DayTable::EventSummary::Load(const DBHandle& db) {
  return Summary::Load(kEventSummaryKey, db);
}

void DayTable::EventSummary::Save(const DBHandle& updates) {
  Summary::Save(kEventSummaryKey, updates);
}


////
// FullEventSummary

DayTable::FullEventSummary::FullEventSummary(DayTable* day_table)
    : Summary(day_table) {
}

int DayTable::FullEventSummary::GetEpisodeRowIndex(int64_t episode_id) const {
  string key;
  if (db_->Get(EncodeEpisodeEventKey(episode_id), &key)) {
    WallTime timestamp;
    int64_t index;
    if (DecodeTimestampAndIdentifier(key, &timestamp, &index)) {
      return GetSummaryRowIndex(timestamp, index);
    } else {
      LOG("day table: failed to decode key %s", key);
    }
  }
  LOG("day table: failed to find row index for episode %d", episode_id);
  return -1;
}

void DayTable::FullEventSummary::GetViewpointRowIndexes(int64_t viewpoint_id, vector<int>* row_indexes) const {
  for (DB::PrefixIterator iter(db_, DBFormat::trapdoor_event_key(viewpoint_id, ""));
       iter.Valid();
       iter.Next()) {
    WallTime timestamp;
    int64_t index;
    if (DecodeTimestampAndIdentifier(iter.value(), &timestamp, &index)) {
      row_indexes->push_back(GetSummaryRowIndex(timestamp, index));
    } else {
      LOG("day table: failed to decode key %s", iter.value());
    }
  }
}

void DayTable::FullEventSummary::UpdateDay(
    WallTime timestamp, const vector<Event>& events,
    const DBHandle& updates) {
  RemoveDayRows(timestamp);

  vector<SummaryRow> rows(events.size());
  for (int i = 0; i < events.size(); ++i) {
    const Event& ev = events[i];

    SummaryRow& row = rows[i];
    row.set_type(SummaryRow::FULL_EVENT);
    row.set_timestamp(ev.earliest_timestamp());
    row.set_day_timestamp(int(timestamp));
    row.set_identifier(i);
    row.set_height(env()->GetFullEventHeight(ev, db_));
    row.set_photo_count(ev.photo_count());
    row.set_contributor_count(ev.contributors_size());
    row.set_distance(ev.distance());
    if (ev.episodes_size() > 0) {
      row.set_episode_id(ev.episodes(0).episode_id());
    }

    int share_count = 0;
    for (int j = 0; j < ev.trapdoors().size(); ++j) {
      share_count += ev.trapdoors()[j]->photo_count() * ev.trapdoors()[j]->contributors_size();
    }
    row.set_share_count(share_count);

    // Secondary index for all episode ids is handled by the normal EventSummary.
  }

  AddDayRows(timestamp, rows);
}

float DayTable::FullEventSummary::height_suffix() const {
  return env()->full_event_summary_height_suffix();
}

bool DayTable::FullEventSummary::Load(const DBHandle& db) {
  return Summary::Load(kFullEventSummaryKey, db);
}

void DayTable::FullEventSummary::Save(const DBHandle& updates) {
  Summary::Save(kFullEventSummaryKey, updates);
}


////
// ConversationSummary

DayTable::ConversationSummary::ConversationSummary(DayTable* day_table)
    : Summary(day_table) {
}

int DayTable::ConversationSummary::GetViewpointRowIndex(int64_t viewpoint_id) const {
  string key;
  if (db_->Get(EncodeViewpointConversationKey(viewpoint_id), &key)) {
    WallTime timestamp;
    int64_t identifier;
    if (DecodeTimestampAndIdentifier(key, &timestamp, &identifier)) {
      const int row_index = GetSummaryRowIndex(timestamp, identifier);
      if (row_index == -1) {
        // TODO(spencer): while there is a bug which sometimes causes the
        //   summary protobuf to get out of date, do a linear search for the
        //   missing viewpoint.
        for (int i = 0; i < summary_.rows_size(); ++i) {
          if (summary_.rows(i).identifier() == identifier) {
            LOG("found requested viewpoint with timestamp mismatch (%d != %d): %s",
                timestamp, summary_.rows(i).day_timestamp(), summary_.rows(i));
            return i;
          }
        }
      }
      return row_index;
    } else {
      LOG("day table: failed to decode key %s", key);
    }
  }
  LOG("day table: failed to find row index for viewpoint %d", viewpoint_id);
  return -1;
}

void DayTable::ConversationSummary::UpdateTrapdoor(
    const Trapdoor& trap, const DBHandle& updates) {
  if (trap.type() != TrapdoorMetadata::INBOX) {
    return;
  }
  RemoveTrapdoor(trap.viewpoint_id(), updates);

  SummaryRow row;
  row.set_type(SummaryRow::TRAPDOOR);
  row.set_timestamp(trap.latest_timestamp());
  row.set_day_timestamp(int(trap.latest_timestamp()));
  row.set_identifier(trap.viewpoint_id());
  row.set_height(env()->GetInboxCardHeight(trap));
  row.set_photo_count(trap.photo_count());
  row.set_comment_count(trap.comment_count());
  row.set_contributor_count(trap.contributors_size());
  if (trap.unviewed_content()) {
    row.set_unviewed(true);
  }

  AddRow(row);
  const string key = EncodeTimestampAndIdentifier(trap.latest_timestamp(), trap.viewpoint_id());
  updates->Put<string>(EncodeViewpointConversationKey(trap.viewpoint_id()), key);
}

void DayTable::ConversationSummary::RemoveTrapdoor(
    int64_t viewpoint_id, const DBHandle& updates) {
  // Do a linear search for the viewpoint in the rows vector.
  bool found = true;
  for (int i = 0; i < summary_.rows_size(); ++i) {
    const SummaryRow& row = summary_.rows(i);
    if (row.identifier() == viewpoint_id) {
      RemoveRow(i);
      SanityCheckRemoved(viewpoint_id);
      found = true;
      break;
    }
  }
  if (!found) {
    LOG("unable to find viewpoint %d in conversation summary:\n%s",
        viewpoint_id, summary_);
  }
  updates->Delete(EncodeViewpointConversationKey(viewpoint_id));
}

bool DayTable::ConversationSummary::Load(const DBHandle& db) {
  const bool res = Summary::Load(kConversationSummaryKey, db);
  if (!res) {
    return res;
  }
  SanityCheck(db);
  return res;
}

void DayTable::ConversationSummary::Save(const DBHandle& updates) {
  SanityCheck(updates);
  Summary::Save(kConversationSummaryKey, updates);
}

void DayTable::ConversationSummary::SanityCheck(const DBHandle& db) {
#if defined(ADHOC) || defined(DEVELOPMENT)
  // Verify no duplicate viewpoints.
  std::unordered_set<int64_t> viewpoint_ids;
  for (int i = 0; i < summary_.rows_size(); ++i) {
    const SummaryRow& r = summary_.rows(i);
    if (ContainsKey(viewpoint_ids, r.identifier())) {
      DIE("conversation summary contains duplicate viewpoint %d\n%s",
          r.identifier(), summary_);
    }
    viewpoint_ids.insert(r.identifier());
  }
  // Verify viewpoint conversation keys against summary rows.
  for (DB::PrefixIterator iter(db, DBFormat::viewpoint_conversation_key(""));
       iter.Valid();
       iter.Next()) {
    WallTime timestamp;
    int64_t identifier;
    if (!DecodeTimestampAndIdentifier(iter.value(), &timestamp, &identifier)) {
      DIE("invalid timestamp and identifier key for viewpoint conversation %s: %s",
          iter.key(), iter.value());
    }
    int index = GetSummaryRowIndex(timestamp, identifier);
    if (index == -1) {
      DIE("unable to locate summary row index for %d/%d in summary: %s",
          int(timestamp), identifier, summary_);
    }
  }
#endif // defined(ADHOC) || defined(DEVELOPMENT)
}

void DayTable::ConversationSummary::SanityCheckRemoved(int64_t viewpoint_id) {
#if defined(ADHOC) || defined(DEVELOPMENT)
  std::unordered_set<int64_t> viewpoint_ids;
  for (int i = 0; i < summary_.rows_size(); ++i) {
    const SummaryRow& r = summary_.rows(i);
    if (viewpoint_id == r.identifier()) {
      DIE("conversation summary unexpectedly contains viewpoint %d\n%s",
          viewpoint_id, summary_);
    }
  }
#endif // defined(ADHOC) || defined(DEVELOPMENT)
}


////
// UnviewedConversationSummary

DayTable::UnviewedConversationSummary::UnviewedConversationSummary(DayTable* day_table)
    : Summary(day_table) {
}

void DayTable::UnviewedConversationSummary::UpdateTrapdoor(
    const Trapdoor& trap, const DBHandle& updates) {
  RemoveTrapdoor(trap.viewpoint_id(), updates);

  if (trap.type() != TrapdoorMetadata::INBOX || !trap.unviewed_content()) {
    return;
  }

  SummaryRow row;
  row.set_type(SummaryRow::TRAPDOOR);
  row.set_timestamp(trap.latest_timestamp());
  row.set_day_timestamp(int(trap.latest_timestamp()));
  row.set_identifier(trap.viewpoint_id());
  row.set_height(env()->GetInboxCardHeight(trap));
  row.set_photo_count(trap.photo_count());
  row.set_comment_count(trap.comment_count());
  row.set_contributor_count(trap.contributors_size());
  row.set_unviewed(true);

  AddRow(row);
}

void DayTable::UnviewedConversationSummary::RemoveTrapdoor(
    int64_t viewpoint_id, const DBHandle& updates) {
  // Do a linear search for the viewpoint in the rows vector.
  for (int i = 0; i < summary_.rows_size(); ++i) {
    const SummaryRow& row = summary_.rows(i);
    if (row.identifier() == viewpoint_id) {
      RemoveRow(i);
      break;
    }
  }
}

bool DayTable::UnviewedConversationSummary::Load(const DBHandle& db) {
  return Summary::Load(kUnviewedConversationSummaryKey, db);
}

void DayTable::UnviewedConversationSummary::Save(const DBHandle& updates) {
  Summary::Save(kUnviewedConversationSummaryKey, updates);
}


////
// ViewpointSummary

DayTable::ViewpointSummary::ViewpointSummary(DayTable* day_table, const DBHandle& db)
    : day_table_(day_table),
      db_(db),
      total_height_(0) {
}

DayTable::ViewpointSummary::~ViewpointSummary() {
}

bool DayTable::ViewpointSummary::Load(int64_t viewpoint_id) {
  const string key = EncodeViewpointSummaryKey(viewpoint_id);
  if (!db_->Exists(key) || !db_->GetProto(key, this)) {
    return false;
  }

  return true;
}

void DayTable::ViewpointSummary::Save(
    const DBHandle& updates, Trapdoor* trap) {
  // The viewpoint summary is potentially large, as it contains info
  // on each activity row in the conversation.
  const string summary_key = EncodeViewpointSummaryKey(viewpoint_id());
  updates->PutProto(summary_key, *this);

  // The viewpoint trapdoor metadata is a constant size and is meant
  // to be efficiently loaded from the inbox view.
  trap->InitFromViewpointSummary(*this);
  const string trapdoor_key = EncodeTrapdoorKey(viewpoint_id());
  updates->PutProto(trapdoor_key, *trap);
}

void DayTable::ViewpointSummary::Rebuild(const ViewpointHandle& vh) {
  Clear();

  if (vh->is_default()) {
    return;
  }
  set_viewpoint_id(vh->id().local_id());

  ScopedPtr<ActivityTable::ActivityIterator> iter(
      state()->activity_table()->NewViewpointActivityIterator(
          vh->id().local_id(), 0, false, db_));
  PhotoIdSet unique_ids;
  ActivityHandle ah;
  ActivityHandle prev_ah;
  ActivityHandle next_ah;
  // Get first visible activity.
  for (; !iter->done(); iter->Next()) {
    ah = iter->GetActivity();
    if (!ah.get() || ah->IsVisible()) {
      break;
    }
    ah.reset();  // clear for the case of !IsVisible()
  }
  // Initialize header rows.
  if (ah.get()) {
    AppendHeaderRow(vh, ah);
  }
  // Process all activities sequentially.
  while (ah.get() != NULL) {
    do {
      iter->Next();
      next_ah = iter->done() ? ActivityHandle() : iter->GetActivity();
    } while (next_ah.get() && !next_ah->IsVisible());
    AppendActivityRows(vh, ah, prev_ah, next_ah, &unique_ids);
    prev_ah = ah;
    ah = next_ah;
  }

  Normalize(vh);
}

void DayTable::ViewpointSummary::UpdateActivities(
    const ViewpointHandle& vh, const vector<ActivityHandle>& ah_vec) {
  if (vh->is_default()) {
    return;
  }

  // We rebuild the activity array if replacing an existing activity
  // or inserting into (as opposed to appending to) the list of activities.
  ActivityRowArray existing;
  existing.Swap(mutable_activities());
  PhotoIdSet unique_ids;

  ActivityMergeIterator iter(state(), db_, &existing, ah_vec);
  if (!iter.done()) {
    AppendHeaderRow(vh, iter.cur_ah());
  }
  for (; !iter.done(); iter.Next()) {
    // Append activity row.
    if (iter.should_append()) {
      AppendActivityRows(vh, iter.cur_ah(), iter.prev_ah(), iter.next_ah(), &unique_ids);
    } else {
      // Copy from existing.
      add_activities()->CopyFrom(iter.cur_activity());
      // Augment unique ids.
      for (int j = 0; j < iter.cur_activity().photos_size(); ++j) {
        unique_ids.insert(iter.cur_activity().photos(j).photo_id());
      }
    }
  }

  Normalize(vh);
}

void DayTable::ViewpointSummary::UpdateRowHeights(const ViewpointHandle& vh) {
  if (!dispatch_is_main_thread()) {
    return;
  }
  for (int i = 0; i < activities_size(); ++i) {
    ActivityRow* row = mutable_activities(i);
    if (row->type() == HEADER && row->height() == 0) {
      row->set_height(env()->GetConversationHeaderHeight(vh, cover_photo().photo_id()));
      break;
    }
  }
}

void DayTable::ViewpointSummary::UpdateRowPositions() {
  total_height_ = 0;
  for (int i = 0; i < activities_size(); ++i) {
    ActivityRow* row = mutable_activities(i);
    row->set_position(total_height_);
    total_height_ += row->height();
  }
}

void DayTable::ViewpointSummary::Delete(int64_t id, const DBHandle& updates) {
  const string summary_key = EncodeViewpointSummaryKey(id);
  updates->Delete(summary_key);
  const string trapdoor_key = EncodeTrapdoorKey(id);
  updates->Delete(trapdoor_key);
}

bool DayTable::ViewpointSummary::IsEmpty() const {
  return !provisional() && !photo_count() && !comment_count() && !contributors_size();
}

void DayTable::ViewpointSummary::Normalize(
    const ViewpointHandle& vh) {
  typedef std::unordered_map<int64_t, int64_t> ContributorMap;
  ContributorMap contrib_map;
  typedef std::unordered_map<string, int64_t> ContributorByIdentityMap;
  ContributorByIdentityMap contrib_by_identity;
  std::unordered_map<int64_t, int64_t> photo_id_to_episode_id;
  int row_count = 0;
  WallTime earliest_timestamp = 0;
  WallTime latest_timestamp = 0;
  int new_comment_count = 0;
  int comment_count = 0;
  int new_photo_count = 0;
  int photo_count = 0;
  int prev_row_type = -1;
  int non_header_row_count = 0;

  clear_scroll_to_row();
  for (int i = 0; i < activities_size(); ++i) {
    ActivityRow* row = mutable_activities(i);

    // Build contributor map. Note that we include even zero height rows
    // to ensure that we don't skip users who are part of a conversation
    // but whose original add (e.g. in the case of a share_new without
    // photos) is a row which isn't displayed.
    for (int j = 0; j < row->user_ids_size(); ++j) {
      contrib_map[row->user_ids(j)] = row->update_seq();
    }
    for (int j = 0; j < row->user_identities_size(); ++j) {
      contrib_by_identity[row->user_identities(j)] = row->update_seq();
    }

    if (row->type() != HEADER) {
      if (row->height() == 0) {
        continue;
      }
      ++non_header_row_count;
    }
    if (i == 0 || row->timestamp() < earliest_timestamp) {
      earliest_timestamp = row->timestamp();
    }
    if (i == 0 || row->timestamp() > latest_timestamp) {
      latest_timestamp = row->timestamp();
    }

    // Build map from photo_id -> episode_id.
    if (row->type() == PHOTOS || row->type() == HEADER) {
      for (int j = 0; j < row->photos_size(); ++j) {
        if (row->photos(j).episode_id() != 0) {
          photo_id_to_episode_id[row->photos(j).photo_id()] = row->photos(j).episode_id();
          // Check for a duplicate photo also shown as cover photo. In
          // this case, subtract one from the photo count.
          if (row->type() != HEADER &&
              cover_photo().photo_id() == row->photos(j).photo_id()) {
            --photo_count;
          }
        }
      }
    }
    // Set any missing episode id for reply-to-photos.
    if (row->type() == REPLY_ACTIVITY) {
      DCHECK_EQ(row->photos_size(), 1);
      if (row->photos(0).episode_id() == 0) {
        const int64_t episode_id = FindOrDefault(photo_id_to_episode_id, row->photos(0).photo_id(), 0);
        if (episode_id != 0) {
          row->mutable_photos(0)->set_episode_id(episode_id);
        } else {
          // We weren't able to get a corresponding episode id, most
          // likely the result of the original photo having been
          // unshared, or not yet loaded. Reset the row type and
          // height.
          ActivityHandle ah = state()->activity_table()->LoadActivity(row->activity_id(), db_);
          row->set_height(env()->GetConversationActivityHeight(
                              vh, ah, -1,
                              static_cast<ActivityThreadType>(row->thread_type()), db_));
        }
      }
    }

    if (IsThreadTypeCombine(static_cast<ActivityThreadType>(row->thread_type())) ||
        (row->type() == UPDATE && prev_row_type == UPDATE)) {
      row_count--;
    }
    row->set_row_count(row_count++);
    prev_row_type = row->type();

    if (row->update_seq() > vh->viewed_seq()) {
      if (!has_scroll_to_row()) {
        // We don't keep track of a viewed sequence number on the header
        // row, but if the user hasn't seen the first activity, then we
        // want to show the entire header (cover photo, title, followers,
        // etc.).
        set_scroll_to_row(non_header_row_count == 1 ? 0 : i);
      }
      if (row->type() == PHOTOS || row->type() == HEADER) {
        new_photo_count += row->photos_size();
      } else if (row->is_comment()) {
        new_comment_count += 1;
      }
    }
    if (row->type() == PHOTOS || row->type() == HEADER) {
      photo_count += row->photos_size();
    } else if (row->is_comment()) {
      comment_count += 1;
    }
  }
  set_earliest_timestamp(earliest_timestamp);
  set_latest_timestamp(latest_timestamp);
  set_new_comment_count(new_comment_count);
  set_comment_count(comment_count);
  set_new_photo_count(new_photo_count);
  set_photo_count(photo_count);
  set_provisional(vh->provisional());

  // List followers in order to filter any which were removed.
  vector<int64_t> follower_ids;
  vh->ListFollowers(&follower_ids);
  std::unordered_set<int64_t> follower_set(follower_ids.begin(), follower_ids.end());

  // Sort list of contributors by most recent contribution.
  vector<Contributor> contribs;
  for (ContributorMap::iterator iter = contrib_map.begin();
       iter != contrib_map.end();
       ++iter) {
    if (ContainsKey(follower_set, iter->first)) {
      ViewpointSummaryMetadata::Contributor contrib;
      contrib.set_user_id(iter->first);
      contrib.set_update_seq(iter->second);
      contribs.push_back(contrib);
    }
  }
  for (ContributorByIdentityMap::iterator iter = contrib_by_identity.begin();
       iter != contrib_by_identity.end();
       ++iter) {
    ViewpointSummaryMetadata::Contributor contrib;
    contrib.set_identity(iter->first);
    contrib.set_update_seq(iter->second);
    contribs.push_back(contrib);
  }
  std::sort(contribs.begin(), contribs.end(), ContributorNewerThan());

  clear_contributors();
  for (int i = 0; i < contribs.size(); ++i) {
    add_contributors()->CopyFrom(contribs[i]);
  }
}

void DayTable::ViewpointSummary::AppendHeaderRow(
    const ViewpointHandle& vh, const ActivityHandle& ah) {
  CHECK_EQ(activities_size(), 0);

  // Try to get cover photo.
  clear_cover_photo();
  int64_t cover_photo_id;
  int64_t cover_episode_id;
  WallTime cover_timestamp;
  float cover_aspect_ratio;

  ActivityRow* row = add_activities();
  row->set_activity_id(ah->activity_id().local_id());
  row->set_timestamp(ah->timestamp());
  row->set_type(HEADER);
  // The actual height will be computed when the conversation is loaded.
  row->set_height(0);

  if (vh->GetCoverPhoto(
          &cover_photo_id, &cover_episode_id, &cover_timestamp, &cover_aspect_ratio)) {
    ActivityRow::Photo* arp = row->add_photos();
    arp->set_photo_id(cover_photo_id);
    arp->set_episode_id(cover_episode_id);

    mutable_cover_photo()->set_photo_id(cover_photo_id);
    mutable_cover_photo()->set_episode_id(cover_episode_id);
    mutable_cover_photo()->set_timestamp(cover_timestamp);
    mutable_cover_photo()->set_aspect_ratio(cover_aspect_ratio);
  }
}

void DayTable::ViewpointSummary::AppendActivityRows(
    const ViewpointHandle& vh, const ActivityHandle& ah,
    const ActivityHandle& prev_ah, const ActivityHandle& next_ah,
    PhotoIdSet* unique_ids) {
  DCHECK(ah->IsVisible());
  // Check if this is the first non-header row.
  CHECK_GT(activities_size(), 0) << "the header row should have been appended";
  bool first_activity = true;
  for (int i = 1 /* skip header row */; i < activities_size(); ++i) {
    if (activities(i).height() > 0) {
      first_activity = false;
    }
  }
  bool empty = true;

  const int start_activity = activities_size();
  ActivityRow* row = add_activities();
  row->set_activity_id(ah->activity_id().local_id());
  row->set_timestamp(ah->timestamp());
  row->set_type(ACTIVITY);
  row->set_thread_type(THREAD_NONE);
  if (ah->provisional()) {
    row->set_is_provisional_hint(true);
  }

  if (ah->has_share_new() || ah->has_share_existing()) {
    row->set_thread_type(THREAD_PHOTOS);
    row->set_height(env()->GetConversationActivityHeight(vh, ah, -1, THREAD_PHOTOS, db_));

    // Build list of photos to display from this activity.
    int duplicate_cover_photo_index = -1;
    vector<PhotoHandle> photos;
    vector<EpisodeHandle> episodes;
    const ShareEpisodes* share_episodes = ah->GetShareEpisodes();
    for (int i = 0; i < share_episodes->size(); ++i) {
      const EpisodeId& episode_id = share_episodes->Get(i).episode_id();
      EpisodeHandle eh = state()->episode_table()->LoadEpisode(episode_id, db_);
      if (!eh.get()) {
        LOG("day table: couldn't get episode %d", episode_id);
        continue;
      }

      // Exclude unshared ids.
      vector<int64_t> unshared_ids;
      eh->ListUnshared(&unshared_ids);
      std::unordered_set<int64_t> unshared_set(unshared_ids.begin(), unshared_ids.end());

      for (int j = 0; j < share_episodes->Get(i).photo_ids_size(); ++j) {
        PhotoHandle ph = state()->photo_table()->LoadPhoto(
            share_episodes->Get(i).photo_ids(j), db_);
        const int64_t photo_id = (ph.get() && !ph->label_error()) ? ph->id().local_id() : -1;
        // Exclude photos which can't be loaded, any photos which
        // have been unshared, and photos which have already been displayed.
        if (photo_id != -1 &&
            !ContainsKey(unshared_set, photo_id) &&
            !ContainsKey(*unique_ids, photo_id)) {
          unique_ids->insert(photo_id);

          if (photo_id == cover_photo().photo_id()) {
            duplicate_cover_photo_index = photos.size();
          }

          // Add all photos to activity row.
          ActivityRow::Photo* arp = row->add_photos();
          arp->set_photo_id(ph->id().local_id());
          arp->set_episode_id(eh->id().local_id());
          if (eh->has_parent_id()) {
            arp->set_parent_episode_id(eh->parent_id().local_id());
          }

          photos.push_back(ph);
          episodes.push_back(eh);
        }
      }
    }

    // If this is the first visible row and contains only the cover
    // photo, don't show the cover photo twice. Otherwise, we allow
    // the cover photo to be duplicated in the conversation to ease
    // user confusion.
    if (duplicate_cover_photo_index != -1 &&
        first_activity &&
        photos.size() == 1) {
      photos.clear();
    }

    // Skip if there are no photos after unshares are filtered.
    if (!photos.empty()) {
      DCHECK_EQ(photos.size(), episodes.size());
      empty = false;

      ViewpointSummaryMetadata::ActivityRow* episode_row = add_activities();
      episode_row->set_activity_id(ah->activity_id().local_id());
      episode_row->set_timestamp(ah->timestamp());
      episode_row->set_type(PHOTOS);

      for (int k = 0; k < photos.size(); ++k) {
        ActivityRow::Photo* arp = episode_row->add_photos();
        const PhotoHandle& ph = photos[k];
        const EpisodeHandle& eh = episodes[k];
        arp->set_photo_id(ph->id().local_id());
        arp->set_episode_id(eh->id().local_id());
        if (eh->has_parent_id()) {
          arp->set_parent_episode_id(eh->parent_id().local_id());
        }
      }
      episode_row->set_height(
          env()->GetShareActivityPhotosRowHeight(
              CONVERSATION_LAYOUT, photos, episodes, db_));
    }
  } else if (ah->has_post_comment()) {
    CommentHandle ch = state()->comment_table()->LoadComment(
        ah->post_comment().comment_id(), db_);
    if (ch.get()) {
      empty = false;
      bool prev_comment = prev_ah.get() && prev_ah->has_post_comment();
      double prev_delta = prev_comment ? ah->timestamp() - prev_ah->timestamp() : 0;
      bool prev_cont = prev_comment && (prev_delta < kCommentThreadThreshold);

      bool next_comment = next_ah.get() && next_ah->has_post_comment();
      double next_delta = 0;
      bool next_cont = false;
      if (next_comment) {
        // The next comment is only a continuation if it isn't a reply.
        CommentHandle next_ch = state()->comment_table()->LoadComment(
            next_ah->post_comment().comment_id(), db_);
        if (next_ch.get() && !next_ch->has_asset_id()) {
          next_delta = next_ah->timestamp() - ah->timestamp();
          next_cont = next_delta < kCommentThreadThreshold;
        }
      }

      // Handle reply-to-photo comment.
      int64_t reply_to_photo_id = -1;
      if (ch->has_asset_id()) {
        PhotoHandle ph = state()->photo_table()->LoadPhoto(ch->asset_id(), db_);
        if (ph.get()) {
          reply_to_photo_id = ph->id().local_id();
          prev_cont = false;
          row->set_type(REPLY_ACTIVITY);
          ActivityRow::Photo* arp = row->add_photos();
          arp->set_photo_id(reply_to_photo_id);
        }
      }

      if (prev_cont) {
        if (ah->user_id() == prev_ah->user_id()) {
          // If same user combine comments into a single
          // row. However, if the minute is different, show a new
          // time indication.
          const bool same_minute = int(ah->timestamp() / 60) == int(prev_ah->timestamp() / 60);
          if (!next_cont) {
            row->set_thread_type(same_minute ?
                                 THREAD_COMBINE_END : THREAD_COMBINE_END_WITH_TIME);
          } else if (ah->user_id() == next_ah->user_id()) {
            row->set_thread_type(same_minute ?
                                 THREAD_COMBINE : THREAD_COMBINE_WITH_TIME);
          } else {
            // Otherwise, combine but to a new user's comment.
            row->set_thread_type(same_minute ?
                                 THREAD_COMBINE_NEW_USER : THREAD_COMBINE_NEW_USER_WITH_TIME);
          }
        } else if (!next_cont) {
          row->set_thread_type(THREAD_END);
        } else {
          row->set_thread_type(THREAD_POINT);
        }
      } else if (!prev_cont && next_cont) {
        row->set_thread_type(THREAD_START);
      }
      row->set_is_comment(true);
      row->set_height(env()->GetConversationActivityHeight(
                          vh, ah, reply_to_photo_id,
                          static_cast<ActivityThreadType>(row->thread_type()), db_));
    }
  } else if (ah->IsUpdate()) {
    empty = false;
    row->set_type(UPDATE);
    bool prev_update = prev_ah.get() && prev_ah->IsUpdate();
    bool next_update = next_ah.get() && next_ah->IsUpdate();
    if (!prev_update) {
      row->set_thread_type(next_update ? UPDATE_START : UPDATE_SINGLE);
    } else {
      row->set_thread_type(next_update ? UPDATE_COMBINE : UPDATE_END);
    }
    row->set_height(env()->GetConversationUpdateHeight(
                        vh, ah, static_cast<ActivityUpdateType>(row->thread_type()), db_));
  }

  // Add contributor.
  row->add_user_ids(ah->user_id());

  // Add sharees if available.
  typedef ::google::protobuf::RepeatedPtrField<ContactMetadata> ContactArray;
  const ContactArray* contacts = ActivityTable::GetActivityContacts(*ah);
  for (int i = 0; contacts && i < contacts->size(); ++i) {
    if (contacts->Get(i).has_user_id()) {
      row->add_user_ids(contacts->Get(i).user_id());
    } else {
      DCHECK(!contacts->Get(i).primary_identity().empty());
      row->add_user_identities(contacts->Get(i).primary_identity());
    }
  }

  // If an activity couldn't be rendered, usually because comment or
  // episode hasn't been fully downloaded yet, set the row height to
  // zero, which will maintain its place in the viewpoint summary, but
  // prevent it from being displayed and prematurely marked as viewed.
  // We do this before setting update sequence to avoid having this
  // incomplete row scrolled-to in case the viewpoint is viewed.
  if (empty) {
    row->set_height(0);
  }

  // Set update sequence number. There is a window where activities are
  // viewed and have their timestamps set before the viewpoint viewed_seq
  // is updated. We handle this case here by just setting the putative
  // update_seq for the row to the value of the viewpoint's viewed_seq.
  // Also, if the activity is the user's own, there's a window between
  // the viewpoint's update_seq and viewed_seq being incremented.
  for (int i = start_activity; i < activities_size(); ++i) {
    row = mutable_activities(i);
    if (row->height() == 0) {
      continue;
    }
    if ((ah->has_viewed_timestamp() || ah->user_id() == state()->user_id()) &&
        ah->update_seq() > vh->viewed_seq()) {
      row->set_update_seq(vh->viewed_seq());
    } else {
      row->set_update_seq(ah->update_seq());
    }
    // Set pending boolean if we need to upload to server.
    if (ah->upload_activity()) {
      row->set_pending(true);
    }
  }
}


////
// Snapshot

DayTable::Snapshot::Snapshot(AppState* state, const DBHandle& snapshot_db)
    : state_(state),
      snapshot_db_(snapshot_db) {
  events_.reset(new EventSummary(state_->day_table()));
  events_->Load(snapshot_db_);
  full_events_.reset(new FullEventSummary(state_->day_table()));
  full_events_->Load(snapshot_db_);
  conversations_.reset(new ConversationSummary(state_->day_table()));
  conversations_->Load(snapshot_db_);
  unviewed_conversations_.reset(new UnviewedConversationSummary(state_->day_table()));
  unviewed_conversations_->Load(snapshot_db_);
}

DayTable::Snapshot::~Snapshot() {
}

DayTable::ViewpointSummaryHandle
DayTable::Snapshot::LoadViewpointSummary(int64_t viewpoint_id) const {
  ViewpointSummaryHandle vsh(
      new ViewpointSummary(state_->day_table(), snapshot_db_));
#ifdef ALWAYS_REBUILD_CONVERSATIONS
  const bool rebuild = true;
#else   // ALWAYS_REBUILD_CONVERSATIONS
  const bool rebuild = false;
#endif  // ALWAYS_REBUILD_CONVERSATIONS
  if (rebuild || !vsh->Load(viewpoint_id)) {
    ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
        viewpoint_id, snapshot_db_);
    vsh->Rebuild(vh);
  }
  return vsh;
}

EventHandle DayTable::Snapshot::LoadEvent(WallTime timestamp, int index) {
  timestamp = CanonicalizeTimestamp(timestamp);

  EventHandle evh(new Event(state_, snapshot_db_));
  if (!snapshot_db_->GetProto(EncodeDayEventKey(timestamp, index), evh.get())) {
    LOG("day table: failed to get event at %d/%d", int(timestamp), index);
    return EventHandle();
  }

  // Initialize the trapdoor objects.
  for (int i = 0; i < evh->trapdoors_size(); ++i) {
    evh->trapdoors_.push_back(new Trapdoor(state_, snapshot_db_));
    evh->trapdoors_[i]->Swap(evh->mutable_trapdoors(i));
  }
  evh->clear_trapdoors();

  return evh;
}

TrapdoorHandle DayTable::Snapshot::LoadTrapdoor(int64_t viewpoint_id) {
  TrapdoorHandle trh(new Trapdoor(state_, snapshot_db_));
  if (!snapshot_db_->GetProto(EncodeTrapdoorKey(viewpoint_id), trh.get())) {
    LOG("day table: failed to get trapdoor %d", viewpoint_id);
    return TrapdoorHandle();
  }
  return trh;
}

TrapdoorHandle DayTable::Snapshot::LoadPhotoTrapdoor(
    int64_t viewpoint_id, int64_t photo_id) {
  PhotoHandle ph = state_->photo_table()->LoadPhoto(photo_id, snapshot_db_);
  if (!ph.get()) {
    LOG("day table: failed to get photo for trapdoor %d", photo_id);
    return TrapdoorHandle();
  }
  TrapdoorHandle trh(new Trapdoor(state_, snapshot_db_));
  if (!snapshot_db_->GetProto(EncodeTrapdoorKey(viewpoint_id), trh.get())) {
    LOG("day table: failed to get trapdoor %d", viewpoint_id);
    return TrapdoorHandle();
  }

  // Clear sampled photos and add in photo_id as only sampled photo.
  trh->clear_photos();
  DayPhoto* photo = trh->add_photos();
  photo->set_photo_id(ph->id().local_id());
  photo->set_episode_id(0);
  photo->set_aspect_ratio(ph->aspect_ratio());
  photo->set_timestamp(ph->timestamp());

  return trh;
}


////
// DayTable

DayTable::DayTable(AppState* state, DayTableEnv* env)
    : state_(state),
      env_(env),
      epoch_(1),
      initialized_(false),
      all_refreshes_paused_(false),
      event_refreshes_paused_(false),
      refreshing_(false) {
  CHECK(env != NULL);

  invalidation_seq_no_ = state_->db()->Get<int64_t>(kDayTableInvalidationSeqNoKey, 1);
  timezone_ = state_->db()->Get<string>(kDayTableTimezoneKey, "");

  // Build map from localized holiday timestamp to holiday array index.
  for (int i = 0; i < ARRAYSIZE(kUSHolidays); ++i) {
    const WallTime timestamp = kUSHolidays[i].timestamp;
    const WallTime local_timestamp =
        timestamp - state_->TimeZoneOffset(timestamp) + kPracticalDayOffset;
    // LOG("%s: %d", kUSHolidays[i].title, int(local_timestamp));
    holiday_timestamps_[local_timestamp] = i;
  }
}

DayTable::~DayTable() {
}

bool DayTable::Initialize(bool force_reset) {
  MutexLock l(&mu_);
  initialized_ = true;
  bool delayed_refresh = true;
  bool reset = false;

#ifdef RESET_DAY_TABLE
  force_reset = true;
#endif  // RESET_DAY_TABLE

  if (ShouldUpdateTimezone() ||
      force_reset ||
      kDayTableFormat != state_->db()->Get<int64_t>(kDayTableFormatKey, 0)) {
    // Immediately delete all existing day table data and invalidate
    // activities and episodes as appropriate to rebuild cached day metadata.
    DBHandle updates = state_->NewDBTransaction();
    UpdateTimezone(updates);
    ResetLocked(updates);
    updates->Commit(false);
    delayed_refresh = false;
    reset = true;
  }

  // Always start paused--refreshing is resumed when maintenance is
  // completed and dashboard has confirmed initial scan is complete.
  all_refreshes_paused_ = true;
  event_refreshes_paused_ = true;

  // Take the initial day snapshot after the day table format has been
  // verified. If we took the snapshot earlier the snapshot might contain
  // unexpected data which could cause crashes or other harmful behavior.
  snapshot_.reset(new DayTable::Snapshot(state_, state_->NewDBSnapshot()));
  epoch_++;

  // Schedule delayed garbage collection after maintenance has completed.
  state_->maintenance_done()->Add([this](bool reset) {
      state_->async()->dispatch_after_background(12, [this] {
          GarbageCollect();
        });
    });

  return reset;
}

bool DayTable::initialized() const {
  MutexLock l(&mu_);
  return initialized_;
}

const DayTable::SnapshotHandle& DayTable::GetSnapshot(int* epoch) {
  MutexLock l(&mu_);
  DCHECK(initialized_);
  if (epoch) {
    *epoch = epoch_;
  }
  return snapshot_;
}

void DayTable::InvalidateActivity(
    const ActivityHandle& ah, const DBHandle& updates) {
  MutexLock l(&mu_);
  if (!initialized_) {
    return;
  }
  invalidation_seq_no_++;
  state_->db()->Put(kDayTableInvalidationSeqNoKey, invalidation_seq_no_);
  const WallTime timestamp = CanonicalizeTimestamp(ah->timestamp());
  updates->Put(EncodeViewpointInvalidationKey(
                   timestamp, ah->viewpoint_id().local_id(), ah->activity_id().local_id()),
               invalidation_seq_no_);
  if (!all_refreshes_paused_) {
    updates->AddCommitTrigger(kDayTableCommitTrigger, [this] {
        MaybeRefresh();
      });
  }
}

void DayTable::InvalidateDay(WallTime timestamp, const DBHandle& updates) {
  MutexLock l(&mu_);
  if (!initialized_) {
    return;
  }
  InvalidateDayLocked(timestamp, updates);
  if (!all_refreshes_paused_) {
    updates->AddCommitTrigger(kDayTableCommitTrigger, [this] {
        MaybeRefresh();
      });
  }
}

void DayTable::InvalidateDayLocked(WallTime timestamp, const DBHandle& updates) {
  invalidation_seq_no_++;
  state_->db()->Put(kDayTableInvalidationSeqNoKey, invalidation_seq_no_);
  timestamp = CanonicalizeTimestamp(timestamp);
  updates->Put(EncodeDayEpisodeInvalidationKey(timestamp, -1), invalidation_seq_no_);
}

void DayTable::InvalidateEpisode(const EpisodeHandle& eh, const DBHandle& updates) {
  MutexLock l(&mu_);
  if (!initialized_) {
    return;
  }
  invalidation_seq_no_++;
  state_->db()->Put(kDayTableInvalidationSeqNoKey, invalidation_seq_no_);
  updates->Put(EncodeDayEpisodeInvalidationKey(
                   CanonicalizeTimestamp(eh->timestamp()), eh->id().local_id()),
               invalidation_seq_no_);
  if (!all_refreshes_paused_ && !event_refreshes_paused_) {
    updates->AddCommitTrigger(kDayTableCommitTrigger, [this] {
        MaybeRefresh();
      });
  }
}

void DayTable::InvalidateViewpoint(const ViewpointHandle& vh, const DBHandle& updates) {
  MutexLock l(&mu_);
  if (!initialized_) {
    return;
  }
  InvalidateViewpointLocked(vh, updates);
  if (!all_refreshes_paused_) {
    updates->AddCommitTrigger(kDayTableCommitTrigger, [this] {
        MaybeRefresh();
      });
  }
}

void DayTable::InvalidateUser(int64_t user_id, const DBHandle& updates) {
  MutexLock l(&mu_);
  if (!initialized_) {
    return;
  }
  invalidation_seq_no_++;
  state_->db()->Put(kDayTableInvalidationSeqNoKey, invalidation_seq_no_);
  updates->Put(EncodeUserInvalidationKey(user_id), invalidation_seq_no_);

  if (!all_refreshes_paused_) {
    updates->AddCommitTrigger(kDayTableCommitTrigger, [this] {
        MaybeRefresh();
      });
  }
}

void DayTable::InvalidateViewpointLocked(
    const ViewpointHandle& vh, const DBHandle& updates) {
  // Set the timestamp for this invalidation to the latest activity for the viewpoint.
  ActivityHandle ah = state_->activity_table()->GetLatestActivity(
      vh->id().local_id(), updates);
  if (ah.get()) {
    invalidation_seq_no_++;
    state_->db()->Put(kDayTableInvalidationSeqNoKey, invalidation_seq_no_);
    const WallTime timestamp = CanonicalizeTimestamp(ah->timestamp());
    updates->Put(EncodeViewpointInvalidationKey(timestamp, vh->id().local_id(), -1),
                 invalidation_seq_no_);
  }
}

void DayTable::InvalidateSnapshot() {
  MutexLock l(&mu_);
  InvalidateSnapshotLocked();
}

void DayTable::InvalidateSnapshotLocked() {
  DCHECK(initialized_);
  snapshot_.reset(new DayTable::Snapshot(state_, state_->NewDBSnapshot()));
  epoch_++;
  state_->async()->dispatch_main([this] {
      update_.Run();
    });
}

void DayTable::PauseAllRefreshes() {
  MutexLock l(&mu_);
  DCHECK(!all_refreshes_paused_);
  all_refreshes_paused_ = true;
  mu_.Wait([this] {
      return !refreshing_;
    });
}

void DayTable::PauseEventRefreshes() {
  MutexLock l(&mu_);
  DCHECK(!event_refreshes_paused_);
  event_refreshes_paused_ = true;
  mu_.Wait([this] {
      return !refreshing_;
    });
}

void DayTable::ResumeAllRefreshes(Callback<void ()> callback) {
  {
    MutexLock l(&mu_);
    all_refreshes_paused_ = false;
  }
  MaybeRefresh(callback);
}

void DayTable::ResumeEventRefreshes() {
  {
    MutexLock l(&mu_);
    event_refreshes_paused_ = false;
  }
  MaybeRefresh();
}

bool DayTable::refreshing() const {
  MutexLock l(&mu_);
  return refreshing_;
}

bool DayTable::IsHoliday(WallTime timestamp, string* s) {
  const int index = FindOrDefault(holiday_timestamps_, timestamp, -1);
  if (index == -1) {
    return false;
  }
  if (s) {
    *s = kUSHolidays[index].title;
  }
  return true;
}

bool DayTable::ShouldUpdateTimezone() const {
  setenv("TZ", state_->timezone().c_str(), 1);
  tzset();
  return (timezone_ != state_->timezone());
}

void DayTable::UpdateTimezone(const DBHandle& updates) {
  timezone_ = state_->timezone();
  updates->Put<string>(kDayTableTimezoneKey, timezone_);
}

void DayTable::ResetLocked(const DBHandle& updates) {
  DeleteDayTablesLocked(updates);
  InvalidateAllDaysLocked(updates);
  InvalidateAllViewpointsLocked(updates);
}

void DayTable::DeleteDayTablesLocked(const DBHandle& updates) {
  for (DB::PrefixIterator iter(updates, kDayKeyPrefix);
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  for (DB::PrefixIterator iter(updates, kDayEventKeyPrefix);
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  for (DB::PrefixIterator iter(updates, kDayEpisodeInvalidationKeyPrefix);
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  for (DB::PrefixIterator iter(updates, kTrapdoorEventKeyPrefix);
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  for (DB::PrefixIterator iter(updates, kTrapdoorKeyPrefix);
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  for (DB::PrefixIterator iter(updates, kEpisodeEventKeyPrefix);
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  for (DB::PrefixIterator iter(updates, kViewpointConversationKeyPrefix);
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  for (DB::PrefixIterator iter(updates, kViewpointInvalidationKeyPrefix);
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  for (DB::PrefixIterator iter(updates, DBFormat::viewpoint_summary_key());
       iter.Valid();
       iter.Next()) {
    updates->Delete(iter.key());
  }
  updates->Delete(kEpisodeSummaryKey);
  updates->Delete(kEventSummaryKey);
  updates->Delete(kConversationSummaryKey);
  updates->Delete(kFullEventSummaryKey);
  updates->Delete(kUnviewedConversationSummaryKey);
  LOG("day table: clearing all cached day summaries");
  updates->Put(kDayTableFormatKey, kDayTableFormat);
}

void DayTable::InvalidateAllDaysLocked(const DBHandle& updates) {
  // Now, create invalidations for all days with content.
  ScopedPtr<DayBuilderIterator> builder_iter(new DayBuilderIterator(state_, updates));
  int days = 0;
  while (!builder_iter->done()) {
    ++days;
    InvalidateDayLocked(builder_iter->timestamp(), updates);
    builder_iter->Next();
  }
  LOG("day table: invalidated %d days", days);
}

void DayTable::InvalidateAllViewpointsLocked(const DBHandle& updates) {
  int viewpoints = 0;
  for (DB::PrefixIterator iter(updates, DBFormat::viewpoint_key());
       iter.Valid();
       iter.Next()) {
    const int64_t viewpoint_id = state_->viewpoint_table()->DecodeContentKey(iter.key());
    ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
        viewpoint_id, updates);
    InvalidateViewpointLocked(vh, updates);
    ++viewpoints;
  }
  LOG("day table: invalidated %d viewpoints", viewpoints);
}

void DayTable::DeleteInvalidationKeysLocked(
    const vector<std::pair<string, int64_t> >& invalidation_keys,
    const DBHandle& updates) {
  mu_.AssertHeld();
  // With mutex lock, delete invalidation keys if no new invalidation
  // arrived and commit, guaranteeing that we don't lose invalidations.
  for (int i = 0; i < invalidation_keys.size(); ++i) {
    const string& key = invalidation_keys[i].first;
    const int64_t snapshot_isn = invalidation_keys[i].second;
    const int64_t current_isn = state_->db()->Get<int64_t>(key, -1);
    if (current_isn == snapshot_isn) {
      updates->Delete(key);
    }
  }
}

void DayTable::MaybeRefresh(Callback<void ()> callback) {
  int64_t start_invalidation_seq_no;
  {
    MutexLock l(&mu_);
    if (refreshing_ || all_refreshes_paused_) {
      DCHECK(!callback);
      return;
    }
    LOG("day table: starting refresh cycle");
    refreshing_ = true;
    start_invalidation_seq_no = invalidation_seq_no_;
  }

  WallTimer timer;
  state_->async()->dispatch_low_priority(
      [this, callback, start_invalidation_seq_no, timer] {
        bool callback_invoked = false;
        bool done = false;
        while (!done) {
          bool day_episodes_completed;
          bool viewpoints_completed;
          bool users_completed;
          int refreshed_day_episodes = RefreshDayEpisodes(&day_episodes_completed);
          int refreshed_viewpoints = RefreshViewpoints(&viewpoints_completed);
          int refreshed_users = RefreshUsers(&users_completed);

          // If there's a callback, invoke it now.
          if (callback && !callback_invoked) {
            callback();
            callback_invoked = true;
          }

          // Check if work was done.
          if (refreshed_day_episodes + refreshed_viewpoints + refreshed_users == 0) {
            // In case there was no work to be done, backoff for 1
            // second so successive calls to InvalidateDay() don't
            // busily generate refresh log messages.
            state_->async()->dispatch_after_background(
                1, [this, start_invalidation_seq_no] {
                  mu_.Lock();
                  refreshing_ = false;
                  // Make sure we notify any listeners that may be waiting for
                  // the refreshing to become false.
                  state_->async()->dispatch_main([this] {
                      update_.Run();
                    });
                  const bool maybe_refresh =
                      invalidation_seq_no_ != start_invalidation_seq_no;
                  mu_.Unlock();
                  if (maybe_refresh) {
                    MaybeRefresh();
                  }
                });
            done = true;
          } else {
            MutexLock l(&mu_);
            // Break out of loop if we've processed all invalidated days
            // and if no new invalidations have occurred.
            if (day_episodes_completed && viewpoints_completed && users_completed &&
                invalidation_seq_no_ == start_invalidation_seq_no) {
              refreshing_ = false;
              done = true;
            }
            InvalidateSnapshotLocked();
          }
        }
        LOG("day table: completed refresh cycle: %.1f sec", timer.Get());

#ifdef CONTINUOUS_DAY_TABLE_REFRESH
        {
          LOG("day table: continuous day table refresh");
          DBHandle updates = state_->NewDBTransaction();
          InvalidateAllDaysLocked(updates);
          InvalidateAllViewpointsLocked(updates);
          updates->Commit(false);
        }
#endif  // CONTINUOUS_DAY_TABLE_REFRESH
    });
}

int DayTable::RefreshDayEpisodes(bool* completed) {
  if (event_refreshes_paused_) {
    return 0;
  }

  WallTimer timer;
  DBHandle snap = state_->NewDBSnapshot();
  DBHandle updates = state_->NewDBTransaction();

  typedef std::unordered_map<WallTime, vector<int64_t> > InvalidationMap;
  InvalidationMap invalidations;
  WallTime last_timestamp = 0;
  int refreshes = 0;
  vector<std::pair<string, int64_t> > invalidation_keys;

  *completed = true;  // start by assuming we complete full scan

  for (DB::PrefixIterator iter(snap, kDayEpisodeInvalidationKeyPrefix);
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const Slice value = iter.value();
    // Stop iteration if we exceed the refresh count limit per iteration.
    if (refreshes >= kMinRefreshCount) {
      *completed = false;
      break;
    }
    WallTime timestamp;
    int64_t episode_id;
    if (!DecodeDayEpisodeInvalidationKey(key, &timestamp, &episode_id)) {
      LOG("day table: unable to decode invalidation sequence key: %s", key);
      continue;
    }

    if (timestamp != last_timestamp) {
      ++refreshes;
      last_timestamp = timestamp;
    }

    // Build the invalidations map.
    invalidations[timestamp].push_back(episode_id);

    // Add invalidation key for deletion under mutex.
    const int64_t snapshot_isn = FromString<int64_t>(value);
    invalidation_keys.push_back(std::make_pair(key.ToString(), snapshot_isn));
  }

  if (invalidations.empty()) {
    return 0;
  }

  ScopedPtr<EventSummary> event_summary(new EventSummary(this));
  ScopedPtr<FullEventSummary> episode_summary(new FullEventSummary(this));
  event_summary->Load(snap);
  episode_summary->Load(snap);

  for (InvalidationMap::iterator iter = invalidations.begin();
       iter != invalidations.end();
       ++iter) {
    const WallTime timestamp = iter->first;
    const vector<int64_t>& episode_ids = iter->second;
    vector<Event> events;
    Day day(state_, timestamp, snap);
    if (!day.Load()) {
      day.Rebuild(&events, updates);
    } else {
      day.UpdateEpisodes(episode_ids, &events, updates);
    }

    event_summary->UpdateDay(timestamp, events, updates);
    episode_summary->UpdateDay(timestamp, events, updates);
  }

  event_summary->Save(updates);
  episode_summary->Save(updates);

  MutexLock l(&mu_);
  DeleteInvalidationKeysLocked(invalidation_keys, updates);
  CHECK(updates->Commit(false)) << "failed database update";

  if (refreshes > 0) {
    LOG("day table: %d day episode refreshes in %.3fs", refreshes, timer.Get());
  }
  return refreshes;
}

int DayTable::RefreshViewpoints(bool* completed) {
  WallTimer timer;
  DBHandle snap = state_->NewDBSnapshot();
  DBHandle updates = state_->NewDBTransaction();
  typedef std::unordered_map<int64_t, vector<int64_t> > InvalidationMap;
  InvalidationMap invalidations;
  int64_t last_viewpoint_id = 0;
  int refreshes = 0;
  vector<std::pair<string, int64_t> > invalidation_keys;

  *completed = true;  // start by assuming we complete full scan

  for (DB::PrefixIterator iter(snap, DBFormat::viewpoint_invalidation_key(""));
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const Slice value = iter.value();
    // Stop iteration if we exceed the refresh count limit per iteration.
    if (refreshes >= kMinRefreshCount) {
      *completed = false;
      break;
    }
    WallTime timestamp;
    int64_t viewpoint_id;
    int64_t activity_id;
    if (!DecodeViewpointInvalidationKey(key, &timestamp, &viewpoint_id, &activity_id)) {
      LOG("day table: unable to decode viewpoint invalidation key: %s", key);
      continue;
    }

    if (viewpoint_id != last_viewpoint_id) {
      ++refreshes;
      last_viewpoint_id = viewpoint_id;
    }

    // Build the invalidations map.
    invalidations[viewpoint_id].push_back(activity_id);

    // Save invalidation key for deletion under the mutex.
    const int64_t snapshot_isn = FromString<int64_t>(value);
    invalidation_keys.push_back(std::make_pair(key.ToString(), snapshot_isn));
  }

  if (invalidations.empty()) {
    return 0;
  }

  ScopedPtr<ConversationSummary> conversation_summary(new ConversationSummary(this));
  ScopedPtr<UnviewedConversationSummary> unviewed_conversation_summary(
      new UnviewedConversationSummary(this));
  conversation_summary->Load(snap);
  unviewed_conversation_summary->Load(snap);
  VLOG("day table: loaded conversation summary with %d rows",
       conversation_summary->row_count());

  // Process updates to each viewpoint.
  for (InvalidationMap::iterator iter = invalidations.begin();
       iter != invalidations.end();
       ++iter) {
    const int64_t viewpoint_id = iter->first;
    ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(viewpoint_id, snap);
    // Skip the user's default viewpoint and any removed viewpoints.
    if (!vh.get() || vh->is_default() || vh->label_removed()) {
      ViewpointSummary::Delete(viewpoint_id, updates);
      conversation_summary->RemoveTrapdoor(viewpoint_id, updates);
      unviewed_conversation_summary->RemoveTrapdoor(viewpoint_id, updates);
      VLOG("day table: removed trapdoor for viewpoint %d", viewpoint_id);
      continue;
    }

    ViewpointSummaryHandle vsh(new ViewpointSummary(state_->day_table(), snap));
    if (!vsh->Load(viewpoint_id)) {
      vsh->Rebuild(vh);
    } else {
      // Augment the viewpoint summary with updated activities.
      std::unordered_set<int64_t> activity_ids;
      vector<ActivityHandle> ah_vec;
      for (int i = 0; i < iter->second.size(); ++i) {
        // Ignore duplicate activities via multiple invalidations.
        if (ContainsKey(activity_ids, iter->second[i])) {
          continue;
        }
        activity_ids.insert(iter->second[i]);
        ActivityHandle ah = state_->activity_table()->LoadActivity(iter->second[i], snap);
        if (ah.get()) {
          ah_vec.push_back(ah);
        }
      }
      std::sort(ah_vec.begin(), ah_vec.end(), ActivityOlderThan());
      vsh->UpdateActivities(vh, ah_vec);
    }

    if (!vsh->IsEmpty()) {
      Trapdoor trap(state_, snap);
      vsh->Save(updates, &trap);

      conversation_summary->UpdateTrapdoor(trap, updates);
      unviewed_conversation_summary->UpdateTrapdoor(trap, updates);
      VLOG("day table: updated trapdoor for viewpoint %d", viewpoint_id);
    } else {
      VLOG("day table: skipping empty viewpoint %s", vh->id());
      ViewpointSummary::Delete(viewpoint_id, updates);
      conversation_summary->RemoveTrapdoor(viewpoint_id, updates);
      unviewed_conversation_summary->RemoveTrapdoor(viewpoint_id, updates);
    }
  }

  conversation_summary->Save(updates);
  unviewed_conversation_summary->Save(updates);

  VLOG("day table: saved conversation summary with %d rows",
       conversation_summary->row_count());

  MutexLock l(&mu_);
  DeleteInvalidationKeysLocked(invalidation_keys, updates);
  CHECK(updates->Commit(false)) << "failed database update";

  // Verify conversation summary after save has completed.
  conversation_summary->SanityCheck(state_->db());

  if (refreshes > 0) {
    LOG("day table: %d viewpoints refreshed in %.3fs", refreshes, timer.Get());
  }
  return refreshes;
}

int DayTable::RefreshUsers(bool* completed) {
  WallTimer timer;
  DBHandle snap = state_->NewDBSnapshot();
  DBHandle updates = state_->NewDBTransaction();
  int refreshes = 0;
  vector<std::pair<string, int64_t> > invalidation_keys;

  *completed = true;

  for (DB::PrefixIterator iter(snap, DBFormat::user_invalidation_key(""));
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    const Slice value = iter.value();
    ++refreshes;
    int64_t user_id;
    if (!DecodeUserInvalidationKey(key, &user_id)) {
      LOG("day table: unable to decode user invalidation key: %s", key);
      continue;
    }

    // Add invalidation key for deletion under mutex.
    const int64_t snapshot_isn = FromString<int64_t>(value);
    invalidation_keys.push_back(std::make_pair(key.ToString(), snapshot_isn));
  }

  MutexLock l(&mu_);
  DeleteInvalidationKeysLocked(invalidation_keys, updates);
  CHECK(updates->Commit(false)) << "failed database update";

  if (refreshes > 0) {
    LOG("day table: %d users refreshed in %.3fs", refreshes, timer.Get());
  }
  return refreshes;
}

void DayTable::GarbageCollect() {
  DBHandle updates = state_->NewDBTransaction();

  for (DB::PrefixIterator iter(updates, kDayKeyPrefix);
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    // Parse the day's timestamp key and delete the day if it
    // doesn't match its own canonicalization.
    WallTime timestamp;
    if (!DecodeDayKey(key, &timestamp) ||
        timestamp != CanonicalizeTimestamp(timestamp)) {
      updates->Delete(key);
    }
  }
  const int day_count = updates->tx_count();
  int last_count = updates->tx_count();
  if (day_count > 0) {
    LOG("day table: garbage collected %d days", day_count);
  }
  for (DB::PrefixIterator iter(updates, kDayEventKeyPrefix);
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    WallTime timestamp;
    int index;
    if (!DecodeDayEventKey(key, &timestamp, &index) ||
        timestamp != CanonicalizeTimestamp(timestamp)) {
      updates->Delete(key);
    }
  }
  const int event_count = updates->tx_count() - last_count;
  last_count = updates->tx_count();
  if (event_count > 0) {
    LOG("day table: garbage collected %d day events", event_count);
  }
  for (DB::PrefixIterator iter(updates, kDayEpisodeInvalidationKeyPrefix);
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    WallTime timestamp;
    int64_t episode_id;
    if (!DecodeDayEpisodeInvalidationKey(key, &timestamp, &episode_id) ||
        timestamp != CanonicalizeTimestamp(timestamp)) {
      updates->Delete(key);
    }
  }
  const int day_episode_count = updates->tx_count() - last_count;
  last_count = updates->tx_count();
  if (day_episode_count > 0) {
    LOG("day table: garbage collected %d day episode invalidations", day_episode_count);
  }
  updates->Commit();
}

WallTime CanonicalizeTimestamp(WallTime timestamp) {
  // Start at minimum offset to avoid negative timestamps.
  timestamp = std::max<WallTime>(timestamp, kMinTimestamp);
  return CurrentDay(timestamp - kPracticalDayOffset) + kPracticalDayOffset;
}

string EncodeDayKey(WallTime timestamp) {
  string s;
  OrderedCodeEncodeVarint32(&s, timestamp);
  return DBFormat::day_key(s);
}

string EncodeDayEventKey(WallTime timestamp, int index) {
  string s;
  OrderedCodeEncodeVarint32(&s, timestamp);
  OrderedCodeEncodeVarint32(&s, index);
  return DBFormat::day_event_key(s);
}

string EncodeDayEpisodeInvalidationKey(
    WallTime timestamp, int64_t episode_id) {
  string s;
  OrderedCodeEncodeVarint32Decreasing(&s, timestamp);
  OrderedCodeEncodeVarint64(&s, episode_id);
  return DBFormat::day_episode_invalidation_key(s);
}

string EncodeEpisodeEventKey(int64_t episode_id) {
  string s;
  OrderedCodeEncodeVarint64(&s, episode_id);
  return DBFormat::episode_event_key(s);
}

string EncodeTimestampAndIdentifier(WallTime timestamp, int64_t identifier) {
  string s;
  OrderedCodeEncodeVarint32(&s, timestamp);
  OrderedCodeEncodeVarint64(&s, identifier);
  return s;
}

string EncodeTrapdoorEventKey(int64_t viewpoint_id, const string& event_key) {
  return DBFormat::trapdoor_event_key(viewpoint_id, event_key);
}

string EncodeTrapdoorKey(int64_t viewpoint_id) {
  string s;
  OrderedCodeEncodeVarint64(&s, viewpoint_id);
  return DBFormat::trapdoor_key(s);
}

string EncodeUserInvalidationKey(int64_t user_id) {
  string s;
  OrderedCodeEncodeVarint64(&s, user_id);
  return DBFormat::user_invalidation_key(s);
}

string EncodeViewpointConversationKey(int64_t viewpoint_id) {
  string s;
  OrderedCodeEncodeVarint64(&s, viewpoint_id);
  return DBFormat::viewpoint_conversation_key(s);
}

string EncodeViewpointInvalidationKey(
    WallTime timestamp, int64_t viewpoint_id, int64_t activity_id) {
  string s;
  OrderedCodeEncodeVarint32Decreasing(&s, timestamp);
  OrderedCodeEncodeVarint64(&s, viewpoint_id);
  OrderedCodeEncodeVarint64(&s, activity_id);
  return DBFormat::viewpoint_invalidation_key(s);
}

string EncodeViewpointSummaryKey(int64_t viewpoint_id) {
  return Format("%s%d", DBFormat::viewpoint_summary_key(), viewpoint_id);
}

bool DecodeDayKey(Slice key, WallTime* timestamp) {
  if (!key.starts_with(kDayKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kDayKeyPrefix.size());
  *timestamp = OrderedCodeDecodeVarint32(&key);
  return true;
}

bool DecodeDayEventKey(Slice key, WallTime* timestamp, int* index) {
  if (!key.starts_with(kDayEventKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kDayEventKeyPrefix.size());
  *timestamp = OrderedCodeDecodeVarint32(&key);
  *index = OrderedCodeDecodeVarint32(&key);
  return true;
}

bool DecodeDayEpisodeInvalidationKey(
    Slice key, WallTime* timestamp, int64_t* episode_id) {
  if (!key.starts_with(kDayEpisodeInvalidationKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kDayEpisodeInvalidationKeyPrefix.size());
  *timestamp = OrderedCodeDecodeVarint32Decreasing(&key);
  *episode_id = OrderedCodeDecodeVarint64(&key);
  return true;
}

bool DecodeTimestampAndIdentifier(Slice key, WallTime* timestamp, int64_t* identifier) {
  *timestamp = OrderedCodeDecodeVarint32(&key);
  *identifier = OrderedCodeDecodeVarint64(&key);
  return true;
}

bool DecodeTrapdoorKey(Slice key, int64_t* viewpoint_id) {
  if (!key.starts_with(kTrapdoorKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kTrapdoorKeyPrefix.size());
  *viewpoint_id = OrderedCodeDecodeVarint64(&key);
  return true;
}

bool DecodeUserInvalidationKey(Slice key, int64_t* user_id) {
  if (!key.starts_with(kUserInvalidationKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kUserInvalidationKeyPrefix.size());
  *user_id = OrderedCodeDecodeVarint64(&key);
  return true;
}

bool DecodeViewpointInvalidationKey(
    Slice key, WallTime* timestamp, int64_t* viewpoint_id, int64_t* activity_id) {
  if (!key.starts_with(kViewpointInvalidationKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kViewpointInvalidationKeyPrefix.size());
  *timestamp = OrderedCodeDecodeVarint32Decreasing(&key);
  *viewpoint_id = OrderedCodeDecodeVarint64(&key);
  *activity_id = OrderedCodeDecodeVarint64(&key);
  return true;
}


// local variables:
// mode: c++
// end:
