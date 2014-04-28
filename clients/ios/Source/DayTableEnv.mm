// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "DayTable.h"
#import "DayTableEnv.h"
#import "LayoutUtils.h"
#import "UIAppState.h"
#import "UIStyle.h"

namespace {

class DayTableIOSEnv : public DayTableEnv {
 public:
  DayTableIOSEnv(UIAppState* state)
      : state_(state) {
  }
  virtual ~DayTableIOSEnv() {
  }

  virtual float GetSummaryEventHeight(
      const Event& ev, const DBHandle& db) {
    return ::GetSummaryEventHeight(
        state_, ev, SUMMARY_COLLAPSED_LAYOUT, state_->screen_width(), db);
  }

  virtual float GetFullEventHeight(
      const Event& ev, const DBHandle& db) {
    return ::GetFullEventHeight(state_, ev, state_->screen_width(), db);
  }

  virtual float GetInboxCardHeight(
      const Trapdoor& trap) {
    return ::GetInboxCardHeight(state_, trap, state_->screen_width());
  }

  virtual float GetConversationHeaderHeight(
      const ViewpointHandle& vh, int64_t cover_photo_id) {
    return InitConversationHeader(
        state_, NULL, vh->id().local_id(), cover_photo_id, 0, 0, state_->screen_width());
  }

  virtual float GetConversationActivityHeight(
      const ViewpointHandle& vh, const ActivityHandle& ah,
      int64_t reply_to_photo_id, ActivityThreadType thread_type,
      const DBHandle& db) {
    return InitConversationActivity(
        state_, NULL, vh, ah, NULL, reply_to_photo_id, 0,
        thread_type, 0, state_->screen_width(), db);
  }

  virtual float GetConversationUpdateHeight(
      const ViewpointHandle& vh, const ActivityHandle& ah,
      ActivityUpdateType update_type, const DBHandle& db) {
    return InitConversationUpdate(
        state_, NULL, vh, ah, update_type, 0, state_->screen_width(), db);
  }

  virtual float GetShareActivityPhotosRowHeight(
      EpisodeLayoutType layout_type, const vector<PhotoHandle>& photos,
      const vector<EpisodeHandle>& episodes,
      const DBHandle& db) {
    return InitShareActivityPhotosRow(
        state_, NULL, CONVERSATION_LAYOUT, photos, episodes,
        state_->screen_width(), 0, db);
  }

  virtual float full_event_summary_height_suffix() {
    return UIStyle::kGutterSpacing;
  }

 private:
  UIAppState* const state_;
};

}  // namespace

DayTableEnv* NewDayTableIOSEnv(UIAppState* state) {
  return new DayTableIOSEnv(state);
}

// local variables:
// mode: c++
// end:
