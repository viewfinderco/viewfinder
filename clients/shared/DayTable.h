// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_DAY_TABLE_H
#define VIEWFINDER_DAY_TABLE_H

#import <map>
#import <unordered_map>
#import "ActivityTable.h"
#import "Callback.h"
#import "DayMetadata.pb.h"
#import "DB.h"
#import "EpisodeTable.h"
#import "Location.pb.h"
#import "Mutex.h"
#import "Placemark.pb.h"
#import "ScopedHandle.h"
#import "ScopedPtr.h"
#import "ViewpointTable.h"
#import "WallTime.h"

class AppState;
class DayTableEnv;

enum ActivityThreadType {
  THREAD_START, // Start of a thread.
  THREAD_PHOTOS,  // Addition of photos.
  THREAD_END,  // Last comment in a thread.
  THREAD_POINT,  // Continuation of a thread.
  THREAD_COMBINE,  // Two successive comments combined to look like one.
  THREAD_COMBINE_NEW_USER,  // Combine but to new user.
  THREAD_COMBINE_WITH_TIME,  // Two successive comments combined, but with time appended.
  THREAD_COMBINE_NEW_USER_WITH_TIME,  // Combine requiring a time, but to new user.
  THREAD_COMBINE_END,  // Combined, but final comment.
  THREAD_COMBINE_END_WITH_TIME,  // Combine, but final comment with time prepended.
  THREAD_NONE,
};

enum ActivityUpdateType {
  UPDATE_SINGLE,   // Lone update.
  UPDATE_START,    // First update in a series.
  UPDATE_COMBINE,  // Middle update in a series.
  UPDATE_END,      // Final update in a series.
};

// DEPRECATED: remove when conversations stop using the episode layout.
enum EpisodeLayoutType {
  EVENT_SUMMARY_LAYOUT,
  CONVERSATION_LAYOUT,
  EVENT_EPISODE_LAYOUT,
};

enum PhotoLayoutType {
  SUMMARY_COLLAPSED_LAYOUT,
  SUMMARY_EXPANDED_LAYOUT,
  FULL_EVENT_LAYOUT,
};

bool IsThreadTypeCombine(ActivityThreadType type);

typedef std::unordered_set<uint64_t> PhotoIdSet;

// The DayTable class provides access to cached summaries of
// episodes and activites over the span of single days. The
// contents are invalidated with any added or modified activity.
// The mapping in the datamodel is from:
//
//   <timestamp> -> <DayMetadata>
//
// There is also a mapping from day timestamp to the most recent
// invalidation sequence number.
//
//   <timestamp>,<invalidation-seq-no> -> <>
//
// Timestamps are canonicalized to day granularity using
// CanonicalizeTimestamp.
//
// DayTable maintains a database snapshot from which it builds all of
// its summaries. The summaries themselves, however, are read and
// written using the read-write database.
//
// DayTable is thread-safe. All other objects are not and should
// be treated as read-only.
class DayTable {
 public:
  class Day;
  class Event;

  // Trapdoor. A viewpoint trapdoor, as the name suggests, provides a
  // link to a viewpoint. The metadata includes a summarization of the
  // goings-on within the linked viewpoint.
  //
  // There are three types of trapdoors: inboxes (INBOX), which cover
  // the entire history of a viewpoint, and events (EVENT), which give
  // detailed information in the event view about how episode(s) were
  // shared.
  class Trapdoor : public TrapdoorMetadata {
    friend class Day;
    friend class DayTable;
    friend class Event;
    friend class ScopedHandle<Trapdoor>;

   public:
    // Returns a formatted timestamp.
    string FormatTimestamp(bool shorten) const;

    // Returns a timestamp formatted as delta from current time ("time ago").
    string FormatTimeAgo() const;

    // Returns a formatted list of contributors, without regard for
    // whether any has contributed new content. "contributor_mask" is
    // a bitwise or of one or more of the values described in
    // DayMetadata.proto for DayContributor::ContributorType. Specify
    // 0 (default) for all types.
    string FormatContributors(bool shorten, int contributor_mask = 0) const;

    // Formats photo & comment counts.
    string FormatPhotoCount() const;
    string FormatCommentCount() const;

    // Returns true if should display in summary.
    bool DisplayInSummary() const;

    // Returns true if should display in inbox.
    bool DisplayInInbox() const;

    // Returns true if should display in event view.
    bool DisplayInEvent() const;

    // Returns true if there is no content in the trapdoor.
    bool IsEmpty() const;

    ViewpointHandle GetViewpoint() const;

   private:
    Trapdoor(AppState* state, const DBHandle& db);

    // Initialize an INBOX type trapdoor from a pre-built viewpoint
    // summary.
    void InitFromViewpointSummary(const ViewpointSummaryMetadata& vs);

    // Adds the specified share activity to the summary. The share
    // specifically is adding the provided CachedEpisode,
    // "ce". Updates the first and last timestamps and contributors.
    void AddSharedEpisode(const ActivityHandle& ah, const CachedEpisode* ce);

    // Canonicalizes internal state by calling SamplePhotos,
    // CanonicalizeContributors and CanonicalizeTitle to flesh out
    // metadata.
    const TrapdoorMetadata& Canonicalize();

    // Free up resources used to build the trapdoor.
    void Cleanup();

    // Samples photos from the available shares in round robin
    // fashion.
    void SamplePhotos();

    // Sets the cover photo information, if at least one photo is available.
    void MaybeSetCoverPhoto();

    // Sorts active contributors by max_update_seq.
    void CanonicalizeContributors();

    // Queries viewpoint for title information.
    void CanonicalizeTitle();

    void Ref() { refcount_.Ref(); }
    void Unref() { if (refcount_.Unref()) delete this; }

   private:
    AppState* state_;
    DBHandle db_;
    AtomicRefCount refcount_;
    ViewpointHandle viewpoint_;
    // Map user_id => max_update_seq. Value is a floating point number
    // to allow a slightly larger update sequence for the actual
    // contributor, so in the case of adding followers to a viewpoint,
    // the inviter sorts before invitees.
    std::unordered_map<int64_t, double> contributors_;
    // For prospective users who do not yet have a user id.
    std::unordered_map<string, double> contributors_by_identity_;
    // For sampling. These are only set for episodes which are
    // contemporaneous with the day of the trapdoor. For an INBOX
    // trapdoor, this means the day of the most recent activity.
    // The bool in the pair is true if this event is new, and should
    // count towards the new photo count.
    vector<std::pair<const CachedEpisode*, bool> > episodes_;
  };
  typedef ScopedHandle<Trapdoor> TrapdoorHandle;

  // Event. An event is a collection of episodes in the user's
  // personal library. Each event contains filtered episodes ordered
  // from least recent to most recent, and maintains an invariant that
  // all episodes in a group be within a threshold distance and
  // threshold time of each other. Episodes without any location on
  // any photos are grouped into a separate "location-less" group. The
  // groups themselves are also ordered from least to most recent
  // within the day, with the earliest timestamp of any episode within
  // the group being used as the sort key.
  //
  // A canonical location and associated placemark is determined by
  // finding the episode from amongst the group with location closest
  // to the group centroid and using its placemark.
  class Event : public EventMetadata {
    friend class Day;
    friend class DayTable;
    friend class ScopedHandle<Event>;

   public:
    // Returns a formatted title (combines related convo title & location).
    string FormatTitle(bool shorten) const;

    // Returns formatted location.
    string FormatLocation(bool shorten, bool uppercase = false) const;

    // Returns a formatted representation of related convos (trapdoors).
    string FormatRelatedConvos(bool shorten) const;

    // Returns a formatted timestamp.
    string FormatTimestamp(bool shorten) const;

    // Returns the formatted time span of the event from earliest
    // photo timestamp to latest.
    string FormatTimeRange(bool shorten) const;

    // Returns a formatted list of contributors.
    string FormatContributors(bool shorten) const;

    // Formats photo count.
    string FormatPhotoCount() const;

    // Returns a vector of event trapdoors.
    const vector<TrapdoorHandle>& trapdoors() const { return trapdoors_; }

    // Returns true if there is no content in the event.
    bool IsEmpty() const;

   private:
    Event(AppState* state, const DBHandle& db);

    // Returns true if "timestamp" falls between the anchor episode's
    // earliest and latest timestamps with a margin of "margin_secs"
    // at each bookend time.
    bool WithinTimeRange(
        const CachedEpisode* anchor, WallTime timestamp, double margin_secs);

    // Returns true if the event already contains any of the photos
    // which are part of the specified episode.
    bool ContainsPhotosFromEpisode(const CachedEpisode* ce);

    // Returns true if the episode can be added to this event based
    // on geo-temporal proximity to the "anchor" event.
    bool CanAddEpisode(
        const CachedEpisode* anchor, const CachedEpisode* ce, float threshold_ratio);

    // Adds the episode to the event.
    void AddEpisode(const CachedEpisode* ce);

    // Canonicalizes internal state by calling CanonicalizeEpisodes
    // and CanonicalizeLocation to flesh out metadata.
    const EventMetadata& Canonicalize();

    // Cleanup the resources used to build the event.
    void Cleanup();

    // Sorts the episodes by timestamp in descending order, determines
    // the first and last timestamps, the set of contributors sorted
    // by greatest to least contribution.
    void CanonicalizeEpisodes();

    // Determines canonical location and placemark.
    void CanonicalizeLocation();

    // Processes all of the EVENT trapdoors under this event.
    void CanonicalizeTrapdoors();

    void Ref() { refcount_.Ref(); }
    void Unref() { if (refcount_.Unref()) delete this; }

   private:
    AppState* state_;
    DBHandle db_;
    AtomicRefCount refcount_;
    vector<const CachedEpisode*> episodes_;
    std::unordered_set<int64_t> photo_ids_;
    vector<TrapdoorHandle> trapdoors_;

    static const double kHomeVsAwayThresholdMeters;
    static const double kHomeThresholdMeters;
    static const double kAwayThresholdMeters;
    static const double kHomeThresholdSeconds;
    static const double kAwayThresholdSeconds;

    static const double kExtendThresholdRatio;
    static const double kExoticThresholdMeters;
  };
  typedef ScopedHandle<Event> EventHandle;

  // The Day class provides an interface into the goings-on for a single
  // day. The timestamps which signify the beginning and end of a day are
  // not defined by 12 midnight to 12 midnight, but from an arbitrary
  // "real-world-offset" into a typical day, defaulting to 4 hours and
  // 30 minutes--meaning that days start at 4:30a and end at 4:30a the
  // following day.
  //
  // Day objects may be individually addressed using a timestamp "ts". The
  // range of assets displayed during that day are determined by using
  // the range:
  //
  //   [WallTime::CurrentDay(ts) + the "real-world-offset", +24h:00m)
  class Day {
    friend class DayTable;

   public:
    WallTime timestamp() const { return metadata_.timestamp(); }

    // Returns true if the episode handle represents a valid
    // episode. This may not be the case where an episode has only
    // been partially loaded (or not yet), but is referenced by an
    // activity.
    static bool IsEpisodeFullyLoaded(const EpisodeHandle& eh);

    // Initializes a CachedEpisode metadata from an episode handle.
    // If not NULL, photo_id_filter is applied against the photos
    // contained in the episode to determine inclusion.
    static void InitCachedEpisode(
        AppState* state, const EpisodeHandle& eh, CachedEpisode* ce, const DBHandle& db,
        const std::unordered_set<string>* photo_id_filter = NULL);

   private:
    Day(AppState* state, WallTime timestamp, const DBHandle& db);

    // Loads the cached day metadata to be augmented by activities
    // or episodes as needed.
    bool Load();

    // Saves derived events to database. Called from Rebuild() or
    // UpdateEpisodes().
    void Save(vector<Event>* events, const DBHandle& updates);

    // Rebuilds day from scratch by iterating over episode
    // table. Creates EVENT trapdoors for all viewpoints which have
    // episodes which occurred on this day. Creates EVENT trapdoors
    // for shares from photos within an event. Sorts vectors according
    // to applicable orderings and stores in db.
    void Rebuild(vector<Event>* events, const DBHandle& updates);

    // Updates day metadata by refreshing the specified vector of episodes.
    void UpdateEpisodes(const vector<int64_t>& episode_ids,
                        vector<Event>* events, const DBHandle& updates);

    // Segments cached episodes array into events.
    void SegmentEvents(vector<Event>* events);


    // Creates an EVENT trapdoor to display the disposition of sharing
    // for photos within an event view.
    void CreateEventTrapdoor(vector<Event>* events, const CachedEpisode* ce,
                             const ViewpointHandle& vh, int ev_index);

   private:
    AppState* state_;
    DBHandle db_;
    DayMetadata metadata_;
  };

  friend class Day;

  // Summary provides aggregate details and by-index querying of
  // summary rows across all days in the user's history. Summary rows
  // can be arbitrary types of information including events, fully-
  // expanded events, and conversations. See the subclasses of Summary
  // for examples.
  class Summary {
    friend class DayTable;

   public:
    enum SummaryType {
      EVENTS,
      FULL_EVENTS,
      CONVERSATIONS,
      UNVIEWED_CONVERSATIONS,
    };

   public:
    Summary(DayTable* day_table);
    virtual ~Summary();

    // Member accessors.
    virtual int photo_count() const { return summary_.photo_count(); }
    virtual int row_count() const { return summary_.rows_size(); }
    virtual int total_height() const { return summary_.total_height(); }

    // Get summary row by "row_index".
    virtual bool GetSummaryRow(int row_index, SummaryRow* row) const;

    void Ref() { refcount_.Ref(); }
    void Unref() { if (refcount_.Unref()) delete this; }

   protected:
    // Get summary row index by day "timestamp" and "identifier".
    int GetSummaryRowIndex(WallTime timestamp, int64_t identifier) const;

    // Adds summary rows comprising a full day.
    void AddDayRows(WallTime timestamp, const vector<SummaryRow>& rows);

    // Removes all summary rows for the specified day.
    void RemoveDayRows(WallTime timestamp);

    // Adds a single summary row.
    void AddRow(const SummaryRow& row);

    // Removes the summary row at "index".
    void RemoveRow(int index);

    // Loads summary information. Returns true if successfully loaded.
    bool Load(const string& key, const DBHandle& db);

    // Saves the summary information.
    void Save(const string& key, const DBHandle& updates);

    // Sets row positions and gets set of holidays by day timestamp.
    void Normalize();

    // Computes a weight contribution by normalizing "value" by "max".
    // If "max" is 0, returns 0. If "log_scale" is true, computes the
    // weight contribution after converting both "value" and "max" to
    // a logarithmic scale.
    float ComputeWeight(float value, float max, bool log_scale) const;

    // Normalizes the weight of a summary row. Stores weight in row->weight().
    void NormalizeRowWeight(SummaryRow* row, bool is_holiday) const;

    // Returns a height prefix for computing absolute positions.
    virtual float height_prefix() const { return 0; }

    // Returns a height suffix for computing absolute positions.
    virtual float height_suffix() const { return 0; }

    AppState* state() const { return day_table_->state_; }
    DayTableEnv* env() const { return day_table_->env_.get(); }

   protected:
    DayTable* const day_table_;
    DBHandle db_;
    SummaryMetadata summary_;
    AtomicRefCount refcount_;

    // For normalizing weights.
    int photo_count_max_;
    int comment_count_max_;
    int contributor_count_max_;
    int share_count_max_;
    double distance_max_;

    // Relative importance of various contributions to row weight. The
    // weights are used to rank order rows. The ordering prioritizes the
    // display of rows in the viewfinder when there are too many to fit.
    static const float kPhotoVolumeWeightFactor;
    static const float kCommentVolumeWeightFactor;
    static const float kContributorWeightFactor;
    static const float kShareWeightFactor;
    static const float kDistanceWeightFactor;
    static const float kUnviewedWeightBonus;
  };

  friend class Summary;

  class EventSummary : public Summary {
    friend class DayTable;

   public:
    EventSummary(DayTable* day_table);

    // Get event summary row index by episode id. Returns -1 if the
    // episode could not be located.
    int GetEpisodeRowIndex(int64_t episode_id) const;

    // Get the list of event summary row indexes with trapdoors pointing to the given episode id.
    void GetViewpointRowIndexes(int64_t viewpoint_id, vector<int>* row_indexes) const;

    // Writes episode ids for fast lookup and calls through to base class.
    void UpdateDay(WallTime timestamp,
                   const vector<Event>& events, const DBHandle& updates);

    bool Load(const DBHandle& db);
    void Save(const DBHandle& updates);

   protected:
    // Add 4pt prefix and suffix to height of summary.
    float height_prefix() const { return 4; }
    float height_suffix() const { return 4; }
  };
  typedef ScopedHandle<EventSummary> EventSummaryHandle;


  class ConversationSummary : public Summary {
    friend class DayTable;

   public:
    // Accessor for unviewed inbox count.
    int unviewed_inbox_count() const { return summary_.unviewed_count(); }

    // Get event summary row index by viewpoint id.
    int GetViewpointRowIndex(int64_t viewpoint_id) const;

    // Writes viewpoint ids for fast lookup and updates/adds a summary.
    void UpdateTrapdoor(
        const Trapdoor& trap, const DBHandle& updates);

    // Removes a trapdoor from the summary.
    void RemoveTrapdoor(int64_t viewpoint_id, const DBHandle& updates);

    bool Load(const DBHandle& db);
    void Save(const DBHandle& updates);

   protected:
    // Add 4pt prefix and suffix to height of summary.
    float height_prefix() const { return 4; }
    float height_suffix() const { return 4; }

   private:
    ConversationSummary(DayTable* day_table);

    void SanityCheck(const DBHandle& db);
    void SanityCheckRemoved(int64_t viewpoint_id);
  };
  typedef ScopedHandle<ConversationSummary> ConversationSummaryHandle;


  class UnviewedConversationSummary : public Summary {
    friend class DayTable;

   public:
    void UpdateTrapdoor(
        const Trapdoor& trap, const DBHandle& updates);

    void RemoveTrapdoor(int64_t viewpoint_id, const DBHandle& updates);

    bool Load(const DBHandle& db);
    void Save(const DBHandle& updates);

   private:
    UnviewedConversationSummary(DayTable* day_table);
  };
  typedef ScopedHandle<UnviewedConversationSummary> UnviewedConversationSummaryHandle;


  class FullEventSummary : public Summary {
    friend class DayTable;

   public:
    // Get event summary row index by episode id. Returns -1 if the
    // episode could not be located.
    int GetEpisodeRowIndex(int64_t episode_id) const;

    // Get the list of event summary row indexes with trapdoors pointing to the given episode id.
    void GetViewpointRowIndexes(int64_t viewpoint_id, vector<int>* row_indexes) const;

    void UpdateDay(WallTime timestamp,
                   const vector<Event>& events, const DBHandle& updates);

    bool Load(const DBHandle& db);
    void Save(const DBHandle& updates);

   protected:
    virtual float height_suffix() const;

   private:
    FullEventSummary(DayTable* day_table);
  };
  typedef ScopedHandle<FullEventSummary> FullEventSummaryHandle;


  // Summary describes the skeleton of a viewpoint's activities for
  // efficiently displaying the visible portion.
  class ViewpointSummary : public ViewpointSummaryMetadata {
   public:
    ViewpointSummary(DayTable* day_table, const DBHandle& db);
    ~ViewpointSummary();

    // Loads summary information. Returns true if summary information could
    // be loaded; otherwise false indicates the summary should be built from
    // scratch.
    bool Load(int64_t viewpoint_id);

    // Saves the summary information. Computes and writes trapdoor metadata
    // to the database. Returns the result in "*trap".
    void Save(const DBHandle& updates, Trapdoor* trap);

    // Rebuilds summary from scratch.
    void Rebuild(const ViewpointHandle& vh);

    // Incrementally updates summary by adding or updating the specified
    // activity "ah". Merges the existing array of activity rows with those
    // specified in "ah_vec", ignoring existing rows being replaced.
    // REQUIRES: ah_vec is sorted by activity timestamps.
    void UpdateActivities(
        const ViewpointHandle& vh, const vector<ActivityHandle>& ah_vec);

    // Computes the final row heights, but only when run on the main thread
    // since some of the row heights depend on UIKit functionality that is not
    // available on non-main threads.
    void UpdateRowHeights(const ViewpointHandle& vh);

    // Computes the final row positions based upon the current row heights.
    void UpdateRowPositions();

    // Deletes viewpoint summary.
    static void Delete(int64_t id, const DBHandle& updates);

    // Returns true if there are no photos and no comments.
    bool IsEmpty() const;

    float total_height() const { return total_height_; }

    void Ref() { refcount_.Ref(); }
    void Unref() { if (refcount_.Unref()) delete this; }

   private:
    // Set positions (based on cumulative row heights), timestamp
    // range, asset counts, and sort contributors by recent activity.
    void Normalize(const ViewpointHandle& vh);

    // Loads and returns the specified activity (unless "activity_id" == -1).
    ActivityHandle LoadActivity(int64_t activity_id);

    // Appends header row including cover photo and viewpoint title &
    // followers.
    void AppendHeaderRow(
        const ViewpointHandle& vh, const ActivityHandle& ah);

    // Appends activity row(s) for the specified activity (possibly taking
    // previous and next activity into account).
    void AppendActivityRows(
        const ViewpointHandle& vh, const ActivityHandle& ah,
        const ActivityHandle& prev_ah, const ActivityHandle& next_ah,
        std::unordered_set<uint64_t>* unique_ids);

    AppState* state() const { return day_table_->state_; }
    DayTableEnv* env() const { return day_table_->env_.get(); }

   private:
    DayTable* const day_table_;
    DBHandle db_;
    AtomicRefCount refcount_;
    float total_height_;
  };

  friend class ViewpointSummary;
  typedef ScopedHandle<ViewpointSummary> ViewpointSummaryHandle;

  // A snapshot of day table state, including all summary handles:
  // (events, full events, conversations, unviewed conversations). Use
  // this object to access cached day table metadata across the entire
  // spectrum at a single slice in time.
  //
  // NOTE: be careful to release these objects frequently as live
  //   references to leveldb snapshots causes the underlying sstables
  //   not to merge.
  class Snapshot {
   public:
    Snapshot(AppState* state, const DBHandle& snapshot_db);
    ~Snapshot();

    // Accessor for the underlying database snapshot.
    const DBHandle& db() const { return snapshot_db_; }

    // Fetches the day table summary information for events.
    const EventSummaryHandle& events() const {
      return events_;
    }

    // Fetches the day table summary information for fully expanded events.
    const FullEventSummaryHandle& full_events() const {
      return full_events_;
    }

    // Fetches the day table summary information for conversations.
    const ConversationSummaryHandle& conversations() const {
      return conversations_;
    }

    // Fetches the day table summary information for conversations.
    const UnviewedConversationSummaryHandle& unviewed_conversations() const {
      return unviewed_conversations_;
    }

    // Fetches the viepwoint summary for the specified viewpoint.
    ViewpointSummaryHandle LoadViewpointSummary(int64_t viewpoint_id) const;

    // Loads the event specified by the timestamp / index combination.
    EventHandle LoadEvent(WallTime timestamp, int index);

    // Loads the trapdoor specified by viewpoint id.
    TrapdoorHandle LoadTrapdoor(int64_t viewpoint_id);

    // Returns a trapdoor for the specified viewpoint & photo combination.
    TrapdoorHandle LoadPhotoTrapdoor(int64_t viewpoint_id, int64_t photo_id);

    void Ref() { refcount_.Ref(); }
    void Unref() { if (refcount_.Unref()) delete this; }

   private:
    AppState* state_;
    DBHandle snapshot_db_;
    AtomicRefCount refcount_;
    EventSummaryHandle events_;
    FullEventSummaryHandle full_events_;
    ConversationSummaryHandle conversations_;
    UnviewedConversationSummaryHandle unviewed_conversations_;
  };
  typedef ScopedHandle<Snapshot> SnapshotHandle;

 public:
  DayTable(AppState* state, DayTableEnv* env);
  ~DayTable();

  // Initialize the day table; verifies day table format version and
  // timezone and starts garbage collection cycle. Returns true if
  // the day table's contents were reset for a full refresh.
  bool Initialize(bool force_reset);

  bool initialized() const;

  // Fetches the day table summary information as a snapshot in time.
  const SnapshotHandle& GetSnapshot(int* epoch);

  // Invalidates an activity; this affects both the day upon which the
  // activity occurred as well as the viewpoint to which the activity
  // belongs.
  void InvalidateActivity(const ActivityHandle& ah, const DBHandle& updates);

  // Invalidate any cached day metadata for the specified timestamp.
  void InvalidateDay(WallTime timestamp, const DBHandle& updates);

  // Invalidates an episode; this affects the day upon which the
  // episode occurred.
  void InvalidateEpisode(const EpisodeHandle& eh, const DBHandle& updates);

  // Invalidates viewpoint metadata.
  void InvalidateViewpoint(const ViewpointHandle& vh, const DBHandle& updates);

  // Invalidates user contact metadata.
  void InvalidateUser(int64_t user_id, const DBHandle& updates);

  // Invalidates current snapshot and invokes all update callbacks.
  void InvalidateSnapshot();

  // Pause/resume all/event refreshes. If "callback" is not NULL, it is invoked
  // after the first round of refreshes is complete.
  void PauseAllRefreshes();
  void PauseEventRefreshes();
  void ResumeAllRefreshes(Callback<void ()> callback = nullptr);
  void ResumeEventRefreshes();

  // Returns true if there are refreshes still pending; false otherwise.
  bool refreshing() const;

  AppState* state() const { return state_; }

  // Callers can register to be notified when day metadata has been
  // refreshed and a new snapshot epoch has arrived.
  CallbackSet* update() { return &update_; }

  // TODO(spencer): this is completely temporary; needs to be
  // normalized to handle a specific user's locale. Probably
  // going to want a "CalendarTable" and will need a hook into
  // network manager to query events from the server.
  //
  // Returns true if the specified timestamp falls on a holiday.
  // "*s" is set to the holiday name.
  bool IsHoliday(WallTime timestamp, string* s);

 private:
  void InvalidateDayLocked(WallTime timestamp, const DBHandle& updates);
  void InvalidateViewpointLocked(const ViewpointHandle& vh, const DBHandle& updates);

  // Invalidates current snapshot and invokes all update callbacks.
  void InvalidateSnapshotLocked();

  // Loads summary information. Called from InvalidateSnapshotLocked.
  void LoadSummariesLocked(const DBHandle& db);

  // Returns whether the system time zone has changed from the
  // timezone persisted to the database.
  bool ShouldUpdateTimezone() const;

  // Updates the timezone used for computing local times.
  void UpdateTimezone(const DBHandle& updates);

  // Clears all cached day metadata and prepares for a complete rebuild.
  void ResetLocked(const DBHandle& updates);
  void DeleteDayTablesLocked(const DBHandle& updates);
  void InvalidateAllDaysLocked(const DBHandle& updates);
  void InvalidateAllViewpointsLocked(const DBHandle& updates);

  // Deletes invalidation keys under mutex mu_, verifying the
  // invalidation sequence number of each before removing the key.
  void DeleteInvalidationKeysLocked(
      const vector<std::pair<string, int64_t> >& invalidation_keys,
      const DBHandle& updates);

  // Dispatch a low-priority thread to refresh invalidating day
  // metadata contents as needed. If a refresh is already underway,
  // returns immediately as a no-op.
  void MaybeRefresh(Callback<void ()> callback = nullptr);

  // Refresh any days for which metadata has been invalidated. Sets
  // *completed to true if the refresh processed all invalidated
  // days. Returns the number of days refreshed.
  int RefreshDayEpisodes(bool* completed);

  // Refresh any viewpoints for which activities have been
  // invalidated. Sets *completed to true if refresh processed
  // all pending invalidations. Returns the number of viewpoints
  // which were refreshed.
  int RefreshViewpoints(bool* completed);

  // Refresh any updated users. This is mostly a no-op at the moment as
  // User contact info is utilized on the fly when displaying instead of
  // being baked into the cached display metadata.
  int RefreshUsers(bool* completed);

  // Garbage collect any days which were created under different
  // assumptions as to when a day "begins". This will happen if the
  // user's timezone changes or if we (or maybe even the user) decides
  // to modify the "practical day offset".
  //
  // Called on startup to run in a background thread.
  // TODO(spencer): unittest this.
  void GarbageCollect();

 private:
  AppState* state_;
  ScopedPtr<DayTableEnv> env_;
  mutable Mutex mu_;
  int epoch_;
  SnapshotHandle snapshot_;
  CallbackSet update_;
  bool initialized_;
  bool all_refreshes_paused_;
  bool event_refreshes_paused_;
  bool refreshing_;
  int64_t invalidation_seq_no_;
  string timezone_;
  std::unordered_map<WallTime, int> holiday_timestamps_;
};

typedef DayTable::Event Event;
typedef DayTable::EventHandle EventHandle;
typedef DayTable::Trapdoor Trapdoor;
typedef DayTable::TrapdoorHandle TrapdoorHandle;

// DayTableEnv is the interface the day table uses for querying the UI
// about the size of UI elements.
class DayTableEnv {
 public:
  virtual ~DayTableEnv() { }

  virtual float GetSummaryEventHeight(
      const Event& ev, const DBHandle& db) = 0;
  virtual float GetFullEventHeight(
      const Event& ev, const DBHandle& db) = 0;
  virtual float GetInboxCardHeight(
      const Trapdoor& trap) = 0;
  virtual float GetConversationHeaderHeight(
      const ViewpointHandle& vh, int64_t cover_photo_id) = 0;
  virtual float GetConversationActivityHeight(
      const ViewpointHandle& vh, const ActivityHandle& ah,
      int64_t reply_to_photo_id, ActivityThreadType thread_type,
      const DBHandle& db) = 0;
  virtual float GetConversationUpdateHeight(
      const ViewpointHandle& vh, const ActivityHandle& ah,
      ActivityUpdateType update_type, const DBHandle& db) = 0;
  virtual float GetShareActivityPhotosRowHeight(
      EpisodeLayoutType layout_type, const vector<PhotoHandle>& photos,
      const vector<EpisodeHandle>& episodes,
      const DBHandle& db) = 0;

  virtual float full_event_summary_height_suffix() = 0;
};

WallTime CanonicalizeTimestamp(WallTime timestamp);

string EncodeDayKey(WallTime timestamp);
string EncodeDayEventKey(WallTime timestamp, int index);
string EncodeDayEpisodeInvalidationKey(WallTime timestamp, int64_t episode_id);
string EncodeEpisodeEventKey(int64_t episode_id);
string EncodeTimestampAndIdentifier(WallTime timestamp, int64_t identifier);
string EncodeTrapdoorEventKey(int64_t viewpoint_id, const string& event_key);
string EncodeTrapdoorKey(int64_t viewpoint_id);
string EncodeUserInvalidationKey(int64_t user_id);
string EncodeViewpointConversationKey(int64_t viewpoint_id);
string EncodeViewpointInvalidationKey(
    WallTime timestamp, int64_t viewpoint_id, int64_t activity_id);
string EncodeViewpointSummaryKey(int64_t viewpoint_id);
bool DecodeDayKey(Slice key, WallTime* timestamp);
bool DecodeDayEventKey(Slice key, WallTime* timestamp, int* index);
bool DecodeDayEpisodeInvalidationKey(Slice key, WallTime* timestamp, int64_t* episode_id);
bool DecodeTimestampAndIdentifier(Slice key, WallTime* timestamp, int64_t* identifier);
bool DecodeTrapdoorKey(Slice key, int64_t* viewpoint_id);
bool DecodeUserInvalidationKey(Slice key, int64_t* user_id);
bool DecodeViewpointInvalidationKey(
    Slice key, WallTime* timestamp, int64_t* viewpoint_id, int64_t* activity_id);

#endif  // VIEWFINDER_DAY_TABLE_H

// local variables:
// mode: c++
// end:
