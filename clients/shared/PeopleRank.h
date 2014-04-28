// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#ifndef VIEWFINDER_PEOPLE_RANK_H
#define VIEWFINDER_PEOPLE_RANK_H

#import <unordered_map>
#import "ContactManager.h"
#import "DayTable.h"
#import "FollowerGroup.pb.h"
#import "Mutex.h"

// Algorithm to compute weight for a group and for all users who belong
// to one or more groups.
//
// G: Follower group
// U: User
// UM: User weight map
// V: Viewpoint
// VW: viewpoint weight
// VT: time between "now" and creation timestamp of conversation
// DW: decayed viewpoint weight
// GW: group weight
// HL: half life of conversation weight
//
// for G in FollowerGroup.iteration:
//   GW = 0;
//   for V in G.viewpoints:
//     DW = exp(-log(2.0) * VT / HL) * VW;
//     GW += DW;
//     for U in G.users:
//       UM[U] += DW;

// The PeopleRank class maintains the mapping:
//   <sorted list of user ids, comma-separated> -> <FollowerGroup>

class PeopleRank {
 public:
  PeopleRank(AppState* state);
  ~PeopleRank();

  // NOTE: the public interface to PeopleRank should be used from the main
  //   thread only--it is not thread safe with possible asynchronous updates
  //   from the day table.

  // Returns a weight to be used for relative ranking between individual
  // users which takes time and participation in all relevant viewpoints
  // into consideration. Returns 0 if the user_id is unknown or the
  // rankings are being determined.
  // When using UserRank in a sorting function, the same value for 'now'
  // must be used for all comparisons in the sort.
  double UserRank(int64_t user_id, WallTime now);

  // Returns a sorted list of FollowerGroups, ordered by weight in
  // descending order, which include all of the users listed in
  // "user_ids", plus at least one additional user.
  void FindBestGroups(
      const vector<int64_t>& user_ids, vector<const FollowerGroup*>* groups);

  // Returns a sorted list of ContactMetadata objects, ordered by weight in
  // descending order. The list of applicable contacts is determined based on
  // groups which also include the users listed in "user_ids".
  void FindBestContacts(
      const vector<int64_t>& user_ids, ContactManager::ContactVec* contacts);

  // Adds the viewpoint to the follower group containing the specified
  // list of user ids. The vector of user ids need not be sorted.
  void AddViewpoint(
      int64_t viewpoint_id, const vector<int64_t>& user_ids, const DBHandle& updates);

  // Removes the viewpoint from the follower group containing the specified
  // list of user ids. The vector of user ids need not be sorted.
  void RemoveViewpoint(
      int64_t viewpoint_id, const vector<int64_t>& user_ids, const DBHandle& updates);

  // Reset the internal state. Intended for use from migrations.
  void Reset();

  // Returns the "max_count" most recently updated viewpoints from the group.
  static vector<int64_t> MostRecentViewpoints(
      const FollowerGroup& group, int max_count);

 private:
  enum UpdateType {
    ADD_WEIGHT,
    REMOVE_WEIGHT,
    UPDATE_WEIGHT,
  };

  // Initialize the in-memory group and user weights.
  void Initialize();

  // Trolls the day table for updated viewpoints and adjusts last
  // update times and weights as appropriate to recompute all group
  // and user weights incrementally.
  void DayTableRefresh();

  void UpdateWeightsInternal(
      int64_t viewpoint_id, const string& key, UpdateType u_type, const DBHandle& updates);

 private:
  AppState* state_;
  int day_table_epoch_;
  DayTable::SnapshotHandle snapshot_;
  // Comma-separated user ids => group weight.
  typedef std::unordered_map<string, FollowerGroup> GroupMap;
  GroupMap group_map_;
  // User id => user weight.
  typedef std::unordered_map<int64_t, double> UserMap;
  UserMap user_map_;
};

string EncodeFollowerGroupKey(const vector<int64_t>& user_ids);
bool DecodeFollowerGroupKey(Slice key, vector<int64_t>* user_ids);

#endif  // VIEWFINDER_PEOPLE_RANK_H

// local variables:
// mode: c++
// end:
