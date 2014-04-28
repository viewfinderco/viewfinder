// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_ACTIVITY_TABLE_H
#define VIEWFINDER_ACTIVITY_TABLE_H

#import "ActivityMetadata.pb.h"
#import "ContentTable.h"
#import "DayMetadata.pb.h"
#import "PhotoSelection.h"
#import "WallTime.h"

typedef google::protobuf::RepeatedPtrField<ActivityMetadata::Episode> ShareEpisodes;

// The ActivityTable class maintains the mappings:
//   <device-activity-id> -> <ActivityMetadata>
//   <server-activity-id> -> <device-activity-id>
//   <device-viewpoint-id>,<timestamp>,<device-activity-id> -> <>
//   <timestamp>,<device-activity-id> -> <>
//   <server-episode-id>,<device-activity-id> -> <>
//
// For quarantined activities, maintain an index of device activity ids.
//   <device-activity-id> -> <>

class ActivityTable_Activity : public ActivityMetadata {
 public:
  virtual void MergeFrom(const ActivityMetadata& m);
  // Unimplemented; exists to get the compiler not to complain about hiding the base class's overloaded MergeFrom.
  virtual void MergeFrom(const ::google::protobuf::Message&);

  // Filters the share new or share existing activity of any photos that are
  // not present in selection. If the activity is modified, any deletions
  // needed to clean up database indexes are added to updates. Returns true if
  // a share activity was filtered and it still contains photos.
  bool FilterShare(const PhotoSelectionSet& selection, const DBHandle& updates);

  // Returns formatted name of user who created activity. If
  // "shorten" is true, returns just first name; otherwise full.
  string FormatName(bool shorten);

  // Returns a formatted timestamp, relative to the current date.
  string FormatTimestamp(bool shorten);

  // Returns formatted version of activity content. If not NULL, uses the
  // supplied activity row to inform the formatting of the activity contents.
  // This provides conversation-dependent context, such as eliminating
  // photos from a share activity which are duplicates in the conversation.
  string FormatContent(
      const ViewpointSummaryMetadata::ActivityRow* activity_row, bool shorten);

  // Returns the timestamp at which this activity was viewed. If none
  // has been set, returns the current wall time.
  WallTime GetViewedTimestamp() const;

  // Returns whether this activity is an update to the conversation,
  // as opposed to content.
  bool IsUpdate() const;

  // Returns whether the activity is visible in the viewpoint.
  // This excludes non-displayed activity types as well as any
  // quarantined activities.
  bool IsVisible() const;

  // Returns the list of shared episodes, if this is a share_new,
  // share_existing, save_photos or unshare activity; NULL otherwise.
  const ShareEpisodes* GetShareEpisodes();

 protected:
  bool Load();
  void SaveHook(const DBHandle& updates);
  void DeleteHook(const DBHandle& updates);

  // Specialty function for default share activity "caption" in the event
  // one is not specified for the activity.
  string FormatShareContent(
      const ViewpointSummaryMetadata::ActivityRow* activity_row, bool shorten);

  // Invalidates all days which are affected by this activity. This includes
  // the day of the activity itself, any days on which episodes shared, updated,
  // or unshared in this activity took place, and the first and last days
  // of the viewpoint which this activity is part of.
  void InvalidateDays(const DBHandle& updates);

  int64_t local_id() const { return activity_id().local_id(); }
  const string& server_id() const { return activity_id().server_id(); }

  ActivityTable_Activity(AppState* state, const DBHandle& db, int64_t id);

 protected:
  AppState* const state_;
  DBHandle db_;

 private:
  // The timestamp as stored on disk.
  WallTime disk_timestamp_;
};

class ActivityTable : public ContentTable<ActivityTable_Activity> {
  typedef ActivityTable_Activity Activity;

  typedef ::google::protobuf::RepeatedPtrField<ContactMetadata> ContactArray;

 public:
  // Iterates over activities. The current activity
  // may be fetched via a call to GetActivity().
  class ActivityIterator : public ContentIterator {
   public:
    virtual ~ActivityIterator();

    // Only valid to call if !done().
    ContentHandle GetActivity();
    int64_t activity_id() const { return cur_activity_id_; }
    WallTime timestamp() const { return cur_timestamp_; }

    virtual void Seek(WallTime seek_time) = 0;

   protected:
    ActivityIterator(ActivityTable* table, bool reverse, const DBHandle& db);

   protected:
    ActivityTable* table_;
    DBHandle db_;
    int64_t cur_activity_id_;
    WallTime cur_timestamp_;
  };

  ActivityTable(AppState* state);
  virtual ~ActivityTable();

  ContentHandle NewActivity(const DBHandle& updates) {
    return NewContent(updates);
  }
  ContentHandle LoadActivity(int64_t id, const DBHandle& db) {
    return LoadContent(id, db);
  }
  ContentHandle LoadActivity(const string& server_id, const DBHandle& db) {
    return LoadContent(server_id, db);
  }

  // Returns the most recent activity for the viewpoint or an
  // empty handle if none was found.
  ContentHandle GetLatestActivity(int64_t viewpoint_id, const DBHandle& db);

  // Returns the first activity for the viewpoint or an empty
  // handle if none was found.
  ContentHandle GetFirstActivity(int64_t viewpoint_id, const DBHandle& db);

  // Returns the activity that posted the comment.
  ContentHandle GetCommentActivity(const string& comment_server_id, const DBHandle& db);

  // Returns the activities which added photos from the specified episode.
  void ListEpisodeActivities(
      const string& episode_server_id, vector<int64_t>* activity_ids, const DBHandle& db);

  // Returns a new ActivityIterator object for iterating over
  // activities in timestamp order. Specify reverse to iterate from
  // most to least recent. The caller is responsible for deleting the
  // iterator.
  ActivityIterator* NewTimestampActivityIterator(
      WallTime start, bool reverse, const DBHandle& db);

  // Returns a new ActivityIterator object for iterating over
  // activities in the specified viewpoint. The activities within the
  // viewpoint are returned in sorted timestamp order from oldest to
  // newest. Specify reverse to iterate instead from newest to
  // oldest. The caller is responsible for deleting the iterator.
  ActivityIterator* NewViewpointActivityIterator(
      int64_t viewpoint_id, WallTime start, bool reverse, const DBHandle& db);

  // Override of base class FSCK to unquarantine activities on startup.
  virtual bool FSCK(
      bool force, ProgressUpdateBlock progress_update, const DBHandle& updates);

  // Repairs secondary indexes and sanity checks all references from
  // activities to other assets.
  bool FSCKImpl(int prev_fsck_version, const DBHandle& updates);

  // Consistency check on activity metdata.
  bool FSCKActivity(const DBHandle& updates);

  // Consistency check on activity-by-timestamp index.
  bool FSCKActivityTimestampIndex(const DBHandle& updates);

  // Consistency check on viewpoint-activity-timestamp index.
  bool FSCKViewpointActivityIndex(const DBHandle& updates);

  static const ContactArray* GetActivityContacts(const ActivityMetadata& m);
};

typedef ActivityTable::ContentHandle ActivityHandle;

string EncodeActivityTimestampKey(WallTime timestamp, int64_t activity_id);
string EncodeCommentActivityKey(const string& episode_server_id);
string EncodeEpisodeActivityKey(const string& episode_server_id, int64_t activity_id);
string EncodeEpisodeActivityKeyPrefix(const string& episode_server_id);
string EncodeQuarantinedActivityKey(int64_t activity_id);
string EncodeViewpointActivityKey(int64_t viewpoint_id, WallTime timestamp, int64_t activity_id);
bool DecodeActivityTimestampKey(Slice key, WallTime* timestamp, int64_t* activity_id);
bool DecodeCommentActivityKey(Slice key, string* comment_server_id);
bool DecodeEpisodeActivityKey(Slice key, string* episode_server_id, int64_t* activity_id);
bool DecodeViewpointActivityKey(Slice key, int64_t* viewpoint_id,
                                WallTime* timestamp, int64_t* activity_id);
bool DecodeQuarantinedActivityKey(Slice key, int64_t* activity_id);

#endif  // VIEWFINDER_ACTIVITY_TABLE_H

// local variables:
// mode: c++
// end:
