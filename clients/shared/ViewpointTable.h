// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_VIEWPOINT_TABLE_H
#define VIEWFINDER_VIEWPOINT_TABLE_H

#import "ContentTable.h"
#import "DB.h"
#import "EpisodeTable.h"
#import "InvalidateMetadata.pb.h"
#import "PhotoSelection.h"
#import "ScopedHandle.h"
#import "ViewpointMetadata.pb.h"

class ActivityTable;
class AppState;
class ContactMetadata;
class FullTextIndex;
class NetworkQueue;
class PhotoTable;

// The ViewpointTable class maintains the mappings:
//   <device-viewpoint-id> -> <ViewpointMetadata>
//   <server-viewpoint-id> -> <ViewpointSelection>
//   <server-viewpoint-id> -> <device-viewpoint-id>
//   <device-viewpoint-id>,<follower-id> -> <>  (follower table)
//   <device-viewpoint-id> -> <scroll-offset>
//   <follower-id>,<device-viewpoint-id> -> <>  (reverse follower table)
//
// ViewpointTable is thread-safe and ViewpointHandle is thread-safe, but individual
// Viewpoints are not.

class ViewpointTable_Viewpoint : public ViewpointMetadata {
  enum FollowerState {
    // It is important for ADDED to be have the value 0 so that that value is
    // the default state for a follower.
    ADDED = 0,
    LOADED,
    REMOVED,
  };

  typedef std::map<int64_t, FollowerState> FollowerStateMap;

 public:
  static const string kTypeDefault;
  static const double kViewpointGCExpirationSeconds;

 public:
  virtual void MergeFrom(const ViewpointMetadata& m);
  // Unimplemented; exists to get the compiler not to complain about hiding the base class's overloaded MergeFrom.
  virtual void MergeFrom(const ::google::protobuf::Message&);

  // Adds a follower to the viewpoint. The follower is persisted when
  // Save() is called.
  void AddFollower(int64_t follower_id);

  // Removes a follower from the viewpoint.
  void RemoveFollower(int64_t follower_id);

  // Returns a count of the number of followers.
  int CountFollowers();

  // Lists the followers of the viewpoint. Note that this will not
  // include prospective users which have not yet been sent to the
  // server (e.g. that don't yet have a user id).
  void ListFollowers(vector<int64_t>* follower_ids);

  // List the follower ids removable by the current user. This is
  // always true for the user himself. It is true otherwise if the
  // user added the specified follower in the past 7 days.
  void GetRemovableFollowers(std::unordered_set<int64_t>* removable);

  // List the episodes that are associated with the viewpoint.
  void ListEpisodes(vector<EpisodeHandle>* episodes);

  // Returns the first sharing episode with at least one valid photo.
  // If "ph_ptr" is not NULL, it is set to the anchor episode's first
  // valid photo.
  EpisodeHandle GetAnchorEpisode(PhotoHandle* ph_ptr);

  // Returns the photo id and aspect ratio of this viewpoint's cover photo.
  // If not set explicitly in the viewpoint metadata, a cover photo is
  // chosen automatically. If no photos are available, returns false.
  bool GetCoverPhoto(int64_t* photo_id, int64_t* episode_id,
                     WallTime* timestamp, float* aspect_ratio);

  // Returns the viewpoint title. If none has been set explicitly,
  // creates one based on the content of the viewpoint.
  string FormatTitle(bool shorten, bool normalize_whitespace = false);

  // Returns the default title for use when no title has been explicitly
  // set for the viewpoint.
  string DefaultTitle();

  // Invalidate all episodes in the viewpoint. Called when personal label
  // is set or viewpoint is removed--will properly update all event trapdoors.
  void InvalidateEpisodes(const DBHandle& updates);

  bool is_default() const { return type() == kTypeDefault; }

  // Returns the expiration wall time for garbage collecting this viewpoint.
  // If the viewpoint has been marked "unrevivable", expiration is immediate;
  // otherwise, expiration is +kViewpointGCExpirationSeconds from current time.
  float GetGCExpiration();

 protected:
  // Store the original cover photo information if available in order to
  // notice changes and invalidate appropriately.
  bool Load();
  // If the cover photo has changed, invalidates both the previous
  // cover photo's episode (if one was set) and the new cover photo's
  // episode.
  void SaveHook(const DBHandle& updates);
  void DeleteHook(const DBHandle& updates);

  string GetDayTableFields() const;

  int64_t local_id() const { return id().local_id(); }
  const string& server_id() const { return id().server_id(); }

  ViewpointTable_Viewpoint(AppState* state, const DBHandle& db, int64_t id);

 protected:
  AppState* state_;
  DBHandle db_;

 private:
  void EnsureFollowerState();
  // Adds metadata for user_id to users if it is not already present in unique_users.
  void AddUniqueUser(int64_t user_id, std::unordered_set<int64_t>* unique_users, vector<ContactMetadata>* users);

 private:
  // A cache of the followers, loaded on demand.
  ScopedPtr<FollowerStateMap> followers_;
  CoverPhoto orig_cover_photo_;
  bool disk_label_removed_;
  string day_table_fields_;
};

class ViewpointTable : public ContentTable<ViewpointTable_Viewpoint> {
  typedef ViewpointTable_Viewpoint Viewpoint;

 public:
  ViewpointTable(AppState* state);
  ~ViewpointTable();

  ContentHandle NewViewpoint(const DBHandle& updates) {
    return NewContent(updates);
  }
  ContentHandle LoadViewpoint(int64_t id, const DBHandle& db) {
    return LoadContent(id, db);
  }
  ContentHandle LoadViewpoint(const string& server_id, const DBHandle& db) {
    return LoadContent(server_id, db);
  }
  ContentHandle LoadViewpoint(const ViewpointId& id, const DBHandle& db);

  // Looks up the viewpoint by "vp_id->server_id" if available and
  // sets "vp_id->local_id". If the viewpoint doesn't exist, a local,
  // empty viewpoint is created.
  void CanonicalizeViewpointId(ViewpointId* vp_id, const DBHandle& updates);

  // Lists the viewpoints (other than default) the specified photo has
  // been shared to.
  void ListViewpointsForPhotoId(
      int64_t photo_id, vector<int64_t>* viewpoint_ids, const DBHandle& db);

  // Lists the viewpoints the specified user is a follower of.
  void ListViewpointsForUserId(
      int64_t user_id, vector<int64_t>* viewpoint_ids, const DBHandle& db);

  // Returns whether "self" user has created a viewpoint.
  bool HasUserCreatedViewpoint(const DBHandle& db);

  // Add followers to an existing viewpoint.
  ContentHandle AddFollowers(
      int64_t viewpoint_id, const vector<ContactMetadata>& contacts);

  // Remove followers from an existing viewpoint.
  ContentHandle RemoveFollowers(
      int64_t viewpoint_id, const vector<int64_t>& user_ids);

  // Posts a comment to an existing viewpoint. If "reply_to_photo_id" is
  // not 0, sets the "asset_id" in the post metadata to the server id
  // of the photo in question.
  ContentHandle PostComment(
      int64_t viewpoint_id, const string& message, int64_t reply_to_photo_id);

  // Removes photos from all saved library episodes. The episode id listed
  // with each photo in the selection vector is ignored. Instead, uses
  // EpisodeTable::ListLibraryEpisodes to get the complete list of saved
  // episodes.
  void RemovePhotos(const PhotoSelectionVec& photo_ids);

  // Saves photos from conversation episodes to library episodes which are
  // part of the default viewpoint. Specify autosave_viewpoint_id to indicate
  // all photos in the viewpoint should be saved. This handles a possible
  // race condition where new photos are added between the client gathering
  // photo ids ("photo_ids") and this call going through to the server. The
  // server will handle adding any additional photos when the operation is
  // executed. Specify autosave_viewpoint_id=0 otherwise.
  void SavePhotos(const PhotoSelectionVec& photo_ids, int64_t autosave_viewpoint_id);
  void SavePhotos(const PhotoSelectionVec& photo_ids,
                  int64_t autosave_viewpoint_id, const DBHandle& updates);

  // Shares photos to an existing viewpoint. Returns NULL on failure
  // and the viewpoint on success. If "update_cover_photo" is
  // specified, the cover photo will be modified to the first photo
  // in the photo_ids selection vec.
  ContentHandle ShareExisting(
      int64_t viewpoint_id, const PhotoSelectionVec& photo_ids,
      bool update_cover_photo);

  // Shares photos to a new viewpoint. Returns NULL on failure and the new
  // viewpoint on success. If "provisional" is true, the new viewpoint will not
  // be uploaded to the server until the provisional bit is cleared.
  ContentHandle ShareNew(
      const PhotoSelectionVec& photo_ids,
      const vector<ContactMetadata>& contacts,
      const string& title, bool provisional);

  // Commit a provisional viewpoint, allowing it to be uploaded to the server.
  bool CommitShareNew(int64_t viewpoint_id, const DBHandle& updates);

  // Update an existing share new activity. Returns false if the activity could
  // not be updated (e.g it is not provisional or does not exist) and true if
  // the activity was updated. Note that any existing photos in the share new
  // activity are replaced with the photos specified in the photo_ids vector.
  // The activity's timestamp is updated to the current time.
  bool UpdateShareNew(
      int64_t viewpoint_id, int64_t activity_id,
      const PhotoSelectionVec& photo_ids);

  // Unshares photos from an existing viewpoint. Returns NULL on failure and
  // the viewpoint on success.
  ContentHandle Unshare(
      int64_t viewpoint_id, const PhotoSelectionVec& photo_ids);

  // Removes the viewpoint from the inbox view if label_removed has
  // not been set. This invokes /service/remove_viewpoint on the server.
  ContentHandle Remove(int64_t viewpoint_id);

  // Updates the viewpoint cover photo.
  ContentHandle UpdateCoverPhoto(int64_t viewpoint_id, int64_t photo_id, int64_t episode_id);

  // Updates the viewpoint title.
  ContentHandle UpdateTitle(int64_t viewpoint_id, const string& title);

  // Updates viewpoint "viewed_seq" property on the server to mark
  // the viewpoint as viewed.
  ContentHandle UpdateViewedSeq(int64_t viewpoint_id);

  // Sets viewpoint "scroll_offset" property.
  void SetScrollOffset(int64_t viewpoint_id, float offset);

  // Returns viewpoint "scroll_offset" property.
  float GetScrollOffset(int64_t viewpoint_id);

  // Reset the cover photo based on the first available share activity
  // (photo neither removed nor unshared).
  bool ResetCoverPhoto(const ContentHandle& vh, const DBHandle& updates);

  // Update viewpoint labels.
  ContentHandle UpdateAutosaveLabel(int64_t viewpoint_id, bool autosave);
  ContentHandle UpdateHiddenLabel(int64_t viewpoint_id, bool hidden);
  ContentHandle UpdateMutedLabel(int64_t viewpoint_id, bool muted);

  // TODO(spencer): Move the validation/invalidation code into ContentTable template.

  // Validates portions of the specified viewpoint.
  // IMPORTANT: this method must be kept in sync with the current set of
  //   attributes contained in ViewpointSelection.
  void Validate(const ViewpointSelection& s, const DBHandle& updates);

  // Invalidates portions of the specified viewpoint.
  // IMPORTANT: this method must be kept in sync with the current set of
  //   attributes contained in ViewpointSelection.
  void Invalidate(const ViewpointSelection& s, const DBHandle& updates);

  // Fully invalidates the viewpoint specified by "server_id".
  void InvalidateFull(const string& server_id, const DBHandle& updates);

  // Lists the viewpoint invalidations. Specify limit=0 for all invalidations.
  void ListInvalidations(vector<ViewpointSelection>* v, int limit, const DBHandle& db);

  // Clear all of the viewpoint invalidations.
  void ClearAllInvalidations(const DBHandle& updates);

  // Process any pending viewpoints for garbage collection. When a
  // viewpoint is garbage collected, its contents are recursively
  // removed from the DB.
  void ProcessGCQueue();

  // Verifies there are no orphaned viewpoints, created to satisfy a
  // CanonicalizeViewpointId call.
  bool FSCKImpl(int prev_fsck_version, const DBHandle& updates);

  typedef vector<int64_t> ViewpointSearchResults;
  void Search(const Slice& query, ViewpointSearchResults* results);

  FullTextIndex* viewpoint_index() const { return viewpoint_index_.get(); }

  // Returns a string that can be used in search (in other indexes) to find
  // records related to the given viewpoint.
  static string FormatViewpointToken(int64_t vp_id);

  // Prefix common to all FormatViewpointToken() strings.
  static const string kViewpointTokenPrefix;

 protected:
  virtual void SaveContentHook(Viewpoint* viewpoint, const DBHandle& updates);
  virtual void DeleteContentHook(Viewpoint* viewpoint, const DBHandle& updates);

 private:
  ContentHandle UpdateLabel(int64_t viewpoint_id,
                            bool (ViewpointMetadata::*getter)() const,
                            void (ViewpointMetadata::*setter)(bool),
                            void (ViewpointMetadata::*clearer)(),
                            bool set_label);

  ScopedPtr<FullTextIndex> viewpoint_index_;
};

typedef ViewpointTable::ContentHandle ViewpointHandle;

string EncodeFollowerViewpointKey(int64_t follower_id, int64_t viewpoint_id);
string EncodeViewpointFollowerKey(int64_t viewpoint_id, int64_t follower_id);
string EncodeViewpointScrollOffsetKey(int64_t viewpoint_id);
string EncodeViewpointGCKey(int64_t viewpont_id, WallTime expiration);
bool DecodeFollowerViewpointKey(Slice key, int64_t* follower_id, int64_t* viewpoint_id);
bool DecodeViewpointFollowerKey(Slice key, int64_t* viewpoint_id, int64_t* follower_id);
bool DecodeViewpointScrollOffsetKey(Slice key, int64_t* viewpoint_id);
bool DecodeViewpointGCKey(Slice key, int64_t* viewpoint_id, WallTime* expiration);

#endif  // VIEWFINDER_VIEWPOINT_TABLE_H

// local variables:
// mode: c++
// end:
