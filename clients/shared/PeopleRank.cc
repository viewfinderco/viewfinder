// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#import <queue>
#import "ActivityTable.h"
#import "AppState.h"
#import "PeopleRank.h"
#import "STLUtils.h"
#import "StringUtils.h"
#import "Timer.h"

namespace {

const string kFollowerGroupKeyPrefix = DBFormat::follower_group_key("");

const double kHalfLife = 45 * 24 * 60 * 60;  // 1.5 months

// This constant was empirically determined based on trying to
// minimize an annoying user who starts sometimes multiple
// conversations a day with me despite my utter lack of interest. But
// balanced to include groups from conversations I didn't start but
// still might.
const double kUserInitiatedConversationMultiplier = 4;

// TODO(spencer): remove this in next version.
const DBRegisterKeyIntrospect kFollowerGroupKeyDeprecatedIntrospect(
    DBFormat::follower_group_key_deprecated(""), NULL,
    [](Slice value) {
      return DBIntrospect::FormatProto<FollowerGroup>(value);
    });

const DBRegisterKeyIntrospect kFollowerGroupKeyIntrospect(
    kFollowerGroupKeyPrefix,
    [](Slice key) {
      vector<int64_t> user_ids;
      if (!DecodeFollowerGroupKey(key, &user_ids)) {
        return string();
      }
      return ToString(user_ids);
    },
    [](Slice value) {
      return DBIntrospect::FormatProto<FollowerGroup>(value);
    });

double Decay(double time) {
  return exp(-log(2.0) * time / kHalfLife);
}

struct ViewpointInfoLessThan {
  bool operator()(const FollowerGroup::ViewpointInfo* a,
                  const FollowerGroup::ViewpointInfo* b) {
    return a->viewpoint_id() < b->viewpoint_id();
  }
  bool operator()(const FollowerGroup::ViewpointInfo* a,
                  const FollowerGroup::ViewpointInfo& b) {
    return (*this)(a, &b);
  }
  bool operator()(const FollowerGroup::ViewpointInfo& a,
                  const FollowerGroup::ViewpointInfo& b) {
    return (*this)(&a, &b);
  }
};

struct BestContactGreaterThan {
  PeopleRank* people_rank;
  std::unordered_map<int64_t, int>* user_id_counts;
  WallTime now;

  BestContactGreaterThan(PeopleRank* pr,
                         std::unordered_map<int64_t, int>* uic,
                         WallTime n)
      : people_rank(pr),
        user_id_counts(uic),
        now(n) {
  }
  bool operator()(const ContactMetadata& a, const ContactMetadata& b) {
    DCHECK(a.has_user_id());
    DCHECK(b.has_user_id());
    if ((*user_id_counts)[a.user_id()] != (*user_id_counts)[b.user_id()]) {
      return (*user_id_counts)[a.user_id()] > (*user_id_counts)[b.user_id()];
    }
    return people_rank->UserRank(a.user_id(), now) > people_rank->UserRank(b.user_id(), now);
  }
};

struct FollowerGroupGreaterThan {
  WallTime now;
  FollowerGroupGreaterThan(WallTime n)
      : now(n) {
  }
  bool operator()(const FollowerGroup* a, const FollowerGroup* b) {
    return a->weight() > b->weight();
  }
};

struct ViewpointLatestTimestampGreaterThan {
  bool operator()(const FollowerGroup::ViewpointInfo*& a,
                  const FollowerGroup::ViewpointInfo*& b) {
    return a->latest_timestamp() > b->latest_timestamp();
  }
};

}  // namespace

typedef google::protobuf::RepeatedPtrField<FollowerGroup::ViewpointInfo> ViewpointInfoArray;

string EncodeFollowerGroupKey(const vector<int64_t>& user_ids) {
  vector<int64_t> sorted_user_ids(user_ids);
  std::sort(sorted_user_ids.begin(), sorted_user_ids.end());
  string group_key;
  for (int i = 0; i < sorted_user_ids.size(); ++i) {
    OrderedCodeEncodeVarint64(&group_key, sorted_user_ids[i]);
  }
  return DBFormat::follower_group_key(group_key);
}

bool DecodeFollowerGroupKey(Slice key, vector<int64_t>* user_ids) {
  user_ids->clear();
  if (!key.starts_with(kFollowerGroupKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kFollowerGroupKeyPrefix.size());
  while (!key.empty()) {
    user_ids->push_back(OrderedCodeDecodeVarint64(&key));
  }
  return true;
}

////
// PeopleRank

PeopleRank::PeopleRank(AppState* state)
    : state_(state),
      day_table_epoch_(0) {
  Initialize();
}

PeopleRank::~PeopleRank() {
}

double PeopleRank::UserRank(int64_t user_id, WallTime now) {
  if (!ContainsKey(user_map_, user_id)) {
    return 0;
  }
  return user_map_[user_id];
}

typedef google::protobuf::RepeatedField<int64_t> UserIdArray;

// Note this is a brute force scan over all of the groups. It's fast
// enough for now, with a test case of 700 groups. However, we may
// need to keep an index from user id to group. Then you intersect
// the various groups, similar to the way ContactManager::Search()
// intersects the contacts matching the search.
void PeopleRank::FindBestGroups(
    const vector<int64_t>& user_ids, vector<const FollowerGroup*>* groups) {
  CHECK(dispatch_is_main_thread());
  groups->clear();

  for (GroupMap::iterator iter = group_map_.begin();
       iter != group_map_.end();
       ++iter) {
    const FollowerGroup& fg = iter->second;
    // Prospective groups must have more user ids than were passed.
    if (fg.user_ids_size() <= user_ids.size()) {
      continue;
    }
    bool all_match = true;
    for (int i = 0; i < user_ids.size(); ++i) {
      UserIdArray::const_iterator it = std::lower_bound(
          fg.user_ids().begin(), fg.user_ids().end(), user_ids[i]);
      if (it == fg.user_ids().end() || *it != user_ids[i]) {
        all_match = false;
        break;
      }
    }

    if (all_match) {
      groups->push_back(&fg);
    }
  }

  std::sort(groups->begin(), groups->end(),
            FollowerGroupGreaterThan(state_->WallTime_Now()));
}

void PeopleRank::FindBestContacts(
    const vector<int64_t>& user_ids, ContactManager::ContactVec* contacts) {
  CHECK(dispatch_is_main_thread());
  vector<const FollowerGroup*> groups;
  FindBestGroups(user_ids, &groups);

  std::unordered_map<int64_t, int> user_id_counts;
  for (int i = 0; i < user_ids.size(); ++i) {
    user_id_counts[user_ids[i]] = 0;
  }

  contacts->clear();
  for (int i = 0; i < groups.size(); ++i) {
    for (int j = 0; j < groups[i]->user_ids_size(); ++j) {
      const int64_t user_id = groups[i]->user_ids(j);
      if (!ContainsKey(user_id_counts, user_id)) {
        contacts->resize(contacts->size() + 1);
        state_->contact_manager()->LookupUser(user_id, &contacts->back());
      }
      ++user_id_counts[user_id];
    }
  }

  std::sort(contacts->begin(), contacts->end(), BestContactGreaterThan(this, &user_id_counts, state_->WallTime_Now()));
}

void PeopleRank::AddViewpoint(
    int64_t viewpoint_id, const vector<int64_t>& user_ids, const DBHandle& updates) {
  const string key = EncodeFollowerGroupKey(user_ids);
  FollowerGroup* fg = NULL;
  if (!ContainsKey(group_map_, key)) {
    fg = &group_map_[key];
    for (int i = 0; i < user_ids.size(); ++i) {
      fg->add_user_ids(user_ids[i]);
    }
  } else {
    fg = &group_map_[key];
  }

  FollowerGroup::ViewpointInfo* vp_info = NULL;
  FollowerGroup::ViewpointInfo search;
  search.set_viewpoint_id(viewpoint_id);
  ViewpointInfoArray::pointer_iterator it =
      std::lower_bound(fg->mutable_viewpoints()->pointer_begin(),
                       fg->mutable_viewpoints()->pointer_end(),
                       &search, ViewpointInfoLessThan());
  if (it == fg->mutable_viewpoints()->pointer_end() ||
      (*it)->viewpoint_id() != viewpoint_id) {
    // Viewpoint doesn't exist yet in this follower group; add it.
    vp_info = fg->add_viewpoints();
    vp_info->set_viewpoint_id(viewpoint_id);
    // Need to lookup first activity for earliest timestamp.
    ActivityHandle ah = state_->activity_table()->GetFirstActivity(viewpoint_id, updates);
    if (ah.get()) {
      vp_info->set_earliest_timestamp(ah->timestamp());
    }
    // Sort the newly added viewpoint.
    std::sort(fg->mutable_viewpoints()->pointer_begin(),
              fg->mutable_viewpoints()->pointer_end(),
              ViewpointInfoLessThan());
  }
  updates->PutProto(key, *fg);
}

void PeopleRank::RemoveViewpoint(
    int64_t viewpoint_id, const vector<int64_t>& user_ids, const DBHandle& updates) {
  const string key = EncodeFollowerGroupKey(user_ids);
  if (!ContainsKey(group_map_, key)) {
    return;
  }
  FollowerGroup* fg = &group_map_[key];

  FollowerGroup::ViewpointInfo search;
  search.set_viewpoint_id(viewpoint_id);
  ViewpointInfoArray::pointer_iterator it =
      std::lower_bound(fg->mutable_viewpoints()->pointer_begin(),
                       fg->mutable_viewpoints()->pointer_end(),
                       &search, ViewpointInfoLessThan());
  if (it == fg->mutable_viewpoints()->pointer_end() ||
      (*it)->viewpoint_id() != viewpoint_id) {
    // Viewpoint isn't here; ignore.
    return;
  }
  if (fg->viewpoints_size() == 0) {
    updates->Delete(key);
    group_map_.erase(key);
  } else {
    updates->PutProto(key, *fg);
  }
}

void PeopleRank::Reset() {
  user_map_.clear();
  group_map_.clear();
}

vector<int64_t> PeopleRank::MostRecentViewpoints(
    const FollowerGroup& group, int max_count) {
  ViewpointLatestTimestampGreaterThan compare;
  std::priority_queue<const FollowerGroup::ViewpointInfo*,
                      vector<const FollowerGroup::ViewpointInfo*>,
                      ViewpointLatestTimestampGreaterThan> pq(compare);
  for (int i = 0; i < group.viewpoints_size(); ++i) {
    pq.push(&group.viewpoints(i));
    if (pq.size() > max_count) {
      pq.pop();
    }
  }

  vector<int64_t> vp_ids;
  while (!pq.empty()) {
    vp_ids.push_back(pq.top()->viewpoint_id());
    pq.pop();
  }
  std::reverse(vp_ids.begin(), vp_ids.end());

  return vp_ids;
}

void PeopleRank::Initialize() {
  for (DB::PrefixIterator iter(state_->db(), kFollowerGroupKeyPrefix);
       iter.Valid();
       iter.Next()) {
    FollowerGroup* fg = &group_map_[iter.key().as_string()];
    if (!fg->ParseFromArray(iter.value().data(), iter.value().size())) {
      group_map_.erase(iter.key().as_string());
    }
  }

  for (GroupMap::iterator iter = group_map_.begin();
       iter != group_map_.end();
       ++iter) {
    FollowerGroup& fg = iter->second;
    double fg_weight = 0;
    for (int i = 0; i < fg.viewpoints_size(); ++i) {
      fg_weight += fg.viewpoints(i).weight();
    }
    fg.set_weight(fg_weight);

    // Iterate over each user in the group and update the user weight.
    for (int i = 0; i < fg.user_ids_size(); ++i) {
      const int64_t user_id = fg.user_ids(i);
      user_map_[user_id] += fg_weight;
    }
  }

  // Setup day table refresh callback.
  state_->day_table()->update()->Add([this] {
      DayTableRefresh();
    });
}

void PeopleRank::DayTableRefresh() {
  CHECK(dispatch_is_main_thread());

  // If currently refreshing, skip the update. We wait for the day
  // table to quiesce. Otherwise, since refreshes are done from most
  // recent to least recent, the last update timestamp would skip
  // refreshes to old viewpoints.
  if (state_->day_table()->refreshing()) {
    return;
  }

  const int old_epoch = day_table_epoch_;
  snapshot_ = state_->day_table()->GetSnapshot(&day_table_epoch_);
  if (old_epoch == day_table_epoch_) {
    // Nothing to do.
    return;
  }

  WallTime now = state_->WallTime_Now();
  WallTimer timer;

  // Initialize a map from viewpoint id to viewpoint info with weight
  // and latest timestamp.
  std::unordered_map<int64_t, FollowerGroup::ViewpointInfo> weight_map;
  for (int i = 0; i < snapshot_->conversations()->row_count(); ++i) {
    SummaryRow row;
    if (snapshot_->conversations()->GetSummaryRow(i, &row)) {
      FollowerGroup::ViewpointInfo& vp_info = weight_map[row.identifier()];
      vp_info.set_weight(row.weight());
      vp_info.set_latest_timestamp(row.timestamp());
    }
  }

  // Compute new weights for follower groups and users.
  user_map_.clear();
  for (GroupMap::iterator iter = group_map_.begin();
       iter != group_map_.end();
       ++iter) {
    FollowerGroup& fg = iter->second;
    double fg_weight = 0;

    for (int i = 0; i < fg.viewpoints_size(); ++i) {
      const FollowerGroup::ViewpointInfo& vp_info = weight_map[fg.viewpoints(i).viewpoint_id()];
      const double vp_weight = vp_info.weight() * Decay(now - vp_info.earliest_timestamp());
      fg.mutable_viewpoints(i)->set_latest_timestamp(vp_info.latest_timestamp());
      fg.mutable_viewpoints(i)->set_weight(vp_weight);
      fg_weight += vp_weight;
    }

    fg.set_weight(fg_weight);

    // Iterate over each user in the group and update the user weight.
    for (int i = 0; i < fg.user_ids_size(); ++i) {
      const int64_t user_id = fg.user_ids(i);
      user_map_[user_id] += fg_weight;
    }
  }

  VLOG("people rank: refreshed in %.3fms", timer.Milliseconds());

#ifdef DEBUG_PEOPLE_RANK
  for (GroupMap::iterator iter = group_map_.begin();
       iter != group_map_.end();
       ++iter) {
    vector<int64_t> user_ids;
    if (!DecodeFollowerGroupKey(iter->first, &user_ids)) {
      LOG("group %s: %s", iter->first, iter->second);
    } else {
      LOG("group %s: %s", ToString(user_ids), iter->second);
    }
  }
  for (UserMap::iterator iter = user_map_.begin();
       iter != user_map_.end();
       ++iter) {
    LOG("user %d: %f", iter->first, iter->second);
  }
#endif  // DEBUG_PEOPLE_RANK
}

// local variables:
// mode: c++
// end:
