// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_LAYOUT_UTILS_H
#define VIEWFINDER_LAYOUT_UTILS_H

#import <QuartzCore/CAAnimation.h>
#import <unordered_set>
#import <QuartzCore/QuartzCore.h>
#import "DayTable.h"
#import "PhotoView.h"
#import "RowView.h"
#import "UIAppState.h"

@class CheckmarkBadge;
@class CompositeTextLayer;
@class EventTextLayer;
@class LayoutController;
@class UIView;

typedef void (^ExpandCallback)();

enum {
  kConversationActivityTag = 1,
  kConversationContentTag,
  kConversationCoverTag,
  kConversationEpisodeTag,
  kConversationFollowersTag,
  kConversationHeaderTag,
  kConversationHeaderRowTag,
  kConversationThreadTag,
  kConversationTitleTag,
  kConversationUpdateTag,
  kCoverGradientTag,
  kEpisodePhotoTag,
  kEpisodeRowTag,
  kEventBevelTag,
  kEventBodySectionTag,
  kEventEpisodeTag,
  kEventTitleSectionTag,
  kFullEventTag,
  kInboxCardTag,
  kInboxCardThumbnailTag,
  kInnerShadowTag,
  kMorePhotosTag,
  kSummaryEventTag,
  kTileShimGradientTag,
  kToolbarTag,
};

struct LayoutRow {
  LayoutRow()
      : view(NULL) {
  }
  RowView* view;
};

struct EpisodeLayoutRow : public LayoutRow {
  EpisodeLayoutRow(WallTime t, ViewpointSummaryMetadata::ActivityRowType ty)
      : timestamp(t), type(ty), pinned(false) {
  }
  EpisodeLayoutRow()
      : timestamp(0), type(ViewpointSummaryMetadata::PHOTOS), pinned(false) {
  }
  WallTime timestamp;
  ViewpointSummaryMetadata::ActivityRowType type;
  bool pinned;  // true to pin in row cache
};

class LayoutTransitionState {
  struct PhotoState {
    CGRect frame;
    CGPoint position;
    float scale;
    PhotoView* photo;
  };

  typedef std::unordered_map<PhotoView*, PhotoState, HashObjC> PhotoStateMap;
  typedef std::unordered_map<UIView*, UIColor*, HashObjC> ViewColorMap;
  typedef std::unordered_map<UIView*, CGRect, HashObjC> ViewFrameMap;
  typedef std::unordered_set<PhotoView*, HashObjC> PhotoSet;
  typedef std::unordered_set<UIView*, HashObjC> ViewSet;

 public:
  LayoutTransitionState(UIAppState* state, UIViewController* current);
  ~LayoutTransitionState();

  void FadeInAlpha(UIView* v);
  void FadeInBackground(UIView* v);
  void SlideFromBottom(UIView* v);
  void ZoomIn(UIView* v);
  void ZoomOut(UIView* v);
  void PrepareRow(const LayoutRow& r, bool animate_event_photos,
                  bool animate_conversation_photos);
  void PreparePhoto(PhotoView* p, PhotoView* other_view, bool animate_copy);
  void PrepareFinish();
  void Commit();

 private:
  void PrepareView(UIView* v);

 private:
  UIAppState* const state_;
  UIViewController* current_;
  PhotoStateMap photo_state_;
  PhotoSet matched_photos_;
  ViewSet fade_in_alpha_;
  ViewSet zoom_in_;
  ViewSet zoom_out_;
  ViewColorMap fade_in_background_;
  ViewFrameMap orig_frame_;
  CAKeyframeAnimation* opacity_animation_;
};

typedef google::protobuf::RepeatedPtrField<FilteredEpisode> FilteredEpisodes;
typedef google::protobuf::RepeatedPtrField<DayPhoto> DayPhotos;

float GetSummaryEventHeight(
    UIAppState* state, const Event& ev, PhotoLayoutType layout,
    float width, const DBHandle& db);
float GetFullEventHeight(
    UIAppState* state, const Event& ev, float width, const DBHandle& db);
float GetInboxCardHeight(
    UIAppState* state, const Trapdoor& trap, float width);
float InitShareActivityPhotosRow(
    UIAppState* state, EpisodeLayoutRow* row,
     EpisodeLayoutType layout_type, const vector<PhotoHandle>& photos,
    const vector<EpisodeHandle>& episodes,
    float width, float y, const DBHandle& db);
float InitEventPhotos(
    UIAppState* state, RowView* row_view, UIView* parent_view,
    const FilteredEpisodes& episodes, PhotoLayoutType layout,
    float width, bool* can_expand, const DBHandle& db);
float InitInboxCardPhotos(
    UIAppState* state, RowView* row_view, UIView* parent_view,
    const DayPhotos& photos, PhotoLayoutType layout,
    float width, bool* can_expand);
float InitConversationHeader(
    UIAppState* state, LayoutRow* row, int64_t viewpoint_id,
    int64_t cover_photo_id, int64_t cover_episode_id,
    float cover_aspect_ratio, float width);
float InitBrowsingCard(
    UIAppState* state, LayoutRow* row, const TrapdoorHandle& trh,
    const ViewpointHandle& vh, float weight, float width);
float InitInboxCard(
    UIAppState* state, LayoutRow* row, const TrapdoorHandle& trh,
    const ViewpointHandle& vh, bool interactive, float weight, float width);
void InitSummaryEvent(
    UIAppState* state, LayoutRow* row, const EventHandle& evh,
    float weight, float width, const DBHandle& db);
void InitFullEvent(
    UIAppState* state, LayoutRow* row, const EventHandle& evh,
    bool single_photo_selection, float weight, float width, const DBHandle& db);
float InitConversationUpdate(
    UIAppState* state, LayoutRow* row, const ViewpointHandle& vh,
    const ActivityHandle& ah, ActivityUpdateType update_type,
    int row_index, float width, const DBHandle& db);
float InitConversationActivity(
    UIAppState* state, LayoutRow* row, const ViewpointHandle& vh, const ActivityHandle& ah,
    const ViewpointSummaryMetadata::ActivityRow* activity_row,
    int64_t reply_to_photo_id, int64_t reply_to_episode_id,
    ActivityThreadType thread_type, int row_index, float width, const DBHandle& db);

// Add rounded corners to "view" such that they lie above all
// subsequently added layers (by dint of a very high z-position).
// The corners reveal a black background.
void AddRoundedCorners(UIView* view);

// Creates a photo view which shares images with existing photo views,
// provided they've been saved to state->photo_view_map() via a call to
// BuildPhotoViewMap().
PhotoView* NewPhotoView(UIAppState* state, int64_t episode_id, int64_t photo_id,
                        float aspect_ratio, const CGRect& frame);
UIView* NewReplyToShadow(PhotoView* p);
// Caches the PhotoViews which hang off "v" and it's subviews recursively.
void BuildPhotoViewMap(PhotoViewMap* map, UIView* v);
PhotoView* FindMatchingPhotoView(PhotoViewMap* map, PhotoView* p,
                                 bool require_episode_match = false);
void InitPhotoViewImage(PhotoViewMap* map, PhotoView* p);

#endif // VIEWFINDER_LAYOUT_UTILS_H
