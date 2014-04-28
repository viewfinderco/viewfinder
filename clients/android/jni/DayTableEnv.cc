// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#include "DayTable.h"
#include "DayTableEnv.h"

namespace {

class DayTableAndroidEnv : public DayTableEnv {
 public:
  DayTableAndroidEnv(NativeAppState* state)
      : state_(state) {
  }
  virtual ~DayTableAndroidEnv() {
  }

  virtual float GetSummaryEventHeight(
      const Event& ev, const DBHandle& db) {
    return 1;
  }

  virtual float GetFullEventHeight(
      const Event& ev, const DBHandle& db) {
    return 1;
  }

  virtual float GetInboxCardHeight(
      const Trapdoor& trap) {
    return 1;
  }

  virtual float GetConversationHeaderHeight(
      const ViewpointHandle& vh, int64_t cover_photo_id) {
    return 1;
  }

  virtual float GetConversationActivityHeight(
      const ViewpointHandle& vh, const ActivityHandle& ah,
      int64_t reply_to_photo_id, ActivityThreadType thread_type,
      const DBHandle& db) {
    return 1;
  }

  virtual float GetConversationUpdateHeight(
      const ViewpointHandle& vh, const ActivityHandle& ah,
      ActivityUpdateType update_type, const DBHandle& db) {
    return 1;
  }

  virtual float GetShareActivityPhotosRowHeight(
      EpisodeLayoutType layout_type, const vector<PhotoHandle>& photos,
      const vector<EpisodeHandle>& episodes, const DBHandle& db) {
    return 1;
  }

  virtual float full_event_summary_height_suffix() {
    return 1;
  }

 private:
  NativeAppState* const state_;
};

}  // namespace

DayTableEnv* NewDayTableAndroidEnv(NativeAppState* state) {
  return new DayTableAndroidEnv(state);
}
