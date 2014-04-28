// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "Appearance.h"
#import "AsyncState.h"
#import "AttrStringUtils.h"
#import "CompositeTextLayers.h"
#import "ContactManager.h"
#import "ContentView.h"
#import "ConversationActivityRowView.h"
#import "ConversationHeaderRowView.h"
#import "EventRowView.h"
#import "FullEventRowView.h"
#import "InboxCardRowView.h"
#import "LayoutUtils.h"
#import "Matrix.h"
#import "PhotoPickerView.h"
#import "PhotoView.h"
#import "RootViewController.h"
#import "RowView.h"
#import "ShareActivityRowView.h"
#import "TileLayout.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"
#import "WallTime.h"

namespace {

const float kTileWidth = 76;
const float kTileHeight = 72;

const float kSmallTileWidth = 76;
const float kSmallTileHeight = 40;

const float kLargeEventMargin = 29;

const float kFullEventTitleHeight = 40;
const float kPhotoSmallRowHeight = 40;
const float kConversationMargin = 8;
const float kConversationSpacing = 8;
const float kConversationPhotosMargin = 8;

const float kThumbnailLeftMargin = 16;
const float kThumbnailTopMargin = 52;
const float kThumbnailSpacing = 4;
const float kThumbnailDim = 40;
const float kReplyToThumbnailDim = 56;

const float kConversationUpdateLeftMargin = 38;
const float kConversationUpdateTopMargin = kConversationSpacing;
const float kConversationUpdateBottomMargin = kConversationSpacing;
const float kActivityContinuationMargin = 2;
const float kActivityContentLeftMargin = 54;
const float kActivityContentTopMargin = 6.5;
const float kActivityContentBottomMargin = 7;
const float kActivityReplyToTopMargin = 6.5;
const float kActivityTitleHeight = 30.5;
const float kShareActivityTitleHeight = 38.5;
const float kActivityPhotoRightMargin = 4;
const float kActivityPhotoTopMargin = 8;
const float kActivityReplyToRightMargin = kReplyToThumbnailDim +
    kActivityPhotoRightMargin + kConversationSpacing;

const CGRect kMorePhotosFrame = { { 284, 64 }, { 16, 16 } };

const double kPendingActivityThrobCycleSecs = 1.5;

struct PhotoLessThan {
  bool operator()(const PhotoHandle& a, const PhotoHandle& b) const {
    return a->timestamp() < b->timestamp();
  }
};

struct PhotoGreaterThan {
  bool operator()(const PhotoHandle& a, const PhotoHandle& b) const {
    return a->timestamp() > b->timestamp();
  }
};

struct DayPhotoLessThan {
  bool operator()(const DayPhoto& a, const DayPhoto& b) const {
    return a.timestamp() > b.timestamp();
  }
};

void ClearLayoutRow(LayoutRow* row) {
  row->view = NULL;
}

void InitUnviewedActivityFade(
    UIAppState* state, UIView* parent,
    const ActivityHandle& ah, float y) {
  const double delta_secs = state->WallTime_Now() - ah->GetViewedTimestamp();
  const double fade_seconds = UIStyle::kUnviewedFadeSeconds - delta_secs;
  if (fade_seconds <= 0) {
    return;
  }

  UIView* unviewed = [UIView new];
  unviewed.backgroundColor = ah->user_id() == state->user_id() ?
                             UIStyle::kPendingActivityColor :
                             UIStyle::kUnviewedActivityColor;
  unviewed.frame = CGRectMake(kConversationMargin, 0, 2, y);
  // Set the current alpha based on ratio of time left in fade.
  unviewed.alpha = fade_seconds / UIStyle::kUnviewedFadeSeconds;
  [parent addSubview:unviewed];
  // Need to run the animation after stack unwinds as we're inside a
  // CATransaction block which is constructed in the process of
  // building the conversation.
  dispatch_after_main(0, ^{
      [UIView animateWithDuration:fade_seconds
                       animations:^{
          unviewed.alpha = 0;
        }
     completion:^(BOOL finished) {
          [unviewed removeFromSuperview];
        }];
    });
}

void CheckPendingActivityThrob(
    UIAppState* state, int64_t activity_id, UIView* pending) {
  ActivityHandle ah = state->activity_table()->LoadActivity(
      activity_id, state->db());
  if (!ah->upload_activity()) {
    [pending removeFromSuperview];
    return;
  }
  dispatch_after_main(kPendingActivityThrobCycleSecs, ^{
      CheckPendingActivityThrob(state, activity_id, pending);
    });
}

void InitPendingActivityThrob(
    UIAppState* state, UIView* parent,
    const ActivityHandle& ah, float y) {
  if (!ah->upload_activity() || ah->provisional()) {
    return;
  }

  UIView* pending = [UIView new];
  pending.backgroundColor = UIStyle::kPendingActivityColor;
  pending.frame = CGRectMake(kConversationMargin, 0, 2, y);
  [parent addSubview:pending];

  const WallTime now = state->WallTime_Now();
  const int64_t cycle = int64_t(now / kPendingActivityThrobCycleSecs);
  CAKeyframeAnimation* animation =
      [CAKeyframeAnimation animationWithKeyPath:@"opacity"];
  // animation.keyTimes = Array(1, 1, 0.25, 0.25);
  animation.values = Array(1, 1, 0.25, 0.25, 1, 1);
  animation.calculationMode = kCAAnimationCubic;
  animation.duration = kPendingActivityThrobCycleSecs;
  animation.repeatCount = HUGE_VALF;
  animation.timeOffset = now - cycle * kPendingActivityThrobCycleSecs;
  [pending.layer addAnimation:animation forKey:NULL];

  CheckPendingActivityThrob(state, ah->activity_id().local_id(), pending);
}

void InitActivityStatusIndicator(
    UIAppState* state, UIView* parent,
    const ActivityHandle& ah, float y) {
  // Check whether the activity is awaiting upload or previously unviewed.
  if (ah->upload_activity()) {
    InitPendingActivityThrob(state, parent, ah, y);
  } else if (state->WallTime_Now() - ah->GetViewedTimestamp() < UIStyle::kUnviewedFadeSeconds) {
    InitUnviewedActivityFade(state, parent, ah, y);
  }
}

void FormatAddFollowersList(
    UIAppState* state, const ActivityHandle& ah,
    const string& verb, const vector<string>& followers,
    NSMutableAttributedString* attr_str) {
  const string name = state->contact_manager()->FirstName(ah->user_id());

  AppendAttrString(
      attr_str, name,
      UIStyle::kConversationUpdateFont, UIStyle::kConversationTitleColor);
  AppendAttrString(
      attr_str, Format(" %s ", verb),
      UIStyle::kConversationCaptionFont, UIStyle::kConversationCaptionColor);
  if (followers.size() > 1) {
    AppendAttrString(
        attr_str,
        Join(followers.begin(), followers.begin() + followers.size() - 1, ", "),
        UIStyle::kConversationUpdateFont, UIStyle::kConversationTitleColor);
    AppendAttrString(
        attr_str, " and ",
        UIStyle::kConversationCaptionFont, UIStyle::kConversationCaptionColor);
  }
  AppendAttrString(
      attr_str, Format("%s", followers.back()),
      UIStyle::kConversationUpdateFont, UIStyle::kConversationTitleColor);
  AppendAttrString(
      attr_str, Format(" %s", FormatTimeAgo(ah->timestamp(), state->WallTime_Now(), TIME_AGO_MEDIUM)),
      UIStyle::kConversationTimeFont, UIStyle::kConversationTimeColor);
}

void FormatAddFollowers(
    UIAppState* state, const ActivityHandle& ah,
    NSMutableAttributedString* attr_str) {
  DCHECK(ah->has_add_followers());

  vector<string> followers;
  vector<string> invitees;
  for (int i = 0; i < ah->add_followers().contacts_size(); ++i) {
    ContactMetadata cm = ah->add_followers().contacts(i);
    if (cm.has_user_id()) {
      state->contact_manager()->LookupUser(cm.user_id(), &cm);
    }
    const string name =
        ContactManager::FormatName(cm, ah->add_followers().contacts_size() > 1);
    if (cm.label_registered()) {
      followers.push_back(name);
    } else {
      invitees.push_back(name);
    }
  }
  if (!followers.empty()) {
    FormatAddFollowersList(state, ah, "added", followers, attr_str);
  }
  if (!invitees.empty()) {
    // If there was a mix of added and invited followers, make sure to
    // prepend a carriage return so the registered and prospective
    // followers each have their own lines.
    if (!followers.empty()) {
      AppendAttrString(
          attr_str, "\n", UIStyle::kConversationCaptionFont,
          UIStyle::kConversationCaptionColor);
    }
    FormatAddFollowersList(state, ah, "invited", invitees, attr_str);
  }
}

void FormatStartConversation(
    UIAppState* state, const ViewpointHandle& vh, const ActivityHandle& ah,
    NSMutableAttributedString* attr_str) {
  if (vh->provisional()) {
    AppendAttrString(
        attr_str, "Draft conversation",
        UIStyle::kConversationCaptionFont, UIStyle::kConversationCaptionColor);
  } else {
    const string name = state->contact_manager()->FirstName(ah->user_id());
    AppendAttrString(
        attr_str, name,
        UIStyle::kConversationUpdateFont, UIStyle::kConversationTitleColor);
    AppendAttrString(
        attr_str, " started the conversation",
        UIStyle::kConversationCaptionFont, UIStyle::kConversationCaptionColor);
    AppendAttrString(
        attr_str, Format(" %s", FormatTimeAgo(ah->timestamp(), state->WallTime_Now(), TIME_AGO_MEDIUM)),
        UIStyle::kConversationTimeFont, UIStyle::kConversationTimeColor);
  }
}

void FormatConversationUpdate(
    UIAppState* state, const ViewpointHandle& vh, const ActivityHandle& ah,
    NSMutableAttributedString* attr_str) {
  if (ah->has_add_followers()) {
    FormatAddFollowers(state, ah, attr_str);
    return;
  } else if (ah->has_share_new() || ah->has_share_existing()) {
    FormatStartConversation(state, vh, ah, attr_str);
    return;
  }

  AppendAttrString(
      attr_str,
      Format("%s %s%s", kTimeSymbol,
             FormatTimeAgo(ah->timestamp(), state->WallTime_Now(), TIME_AGO_MEDIUM), kSpaceSymbol),
      UIStyle::kConversationTimeFont, UIStyle::kConversationTimeColor);
  AppendAttrString(
      attr_str,
      Format("%s%s", state->contact_manager()->FirstName(ah->user_id()), kSpaceSymbol),
      UIStyle::kConversationUpdateFont, UIStyle::kConversationTitleColor);
  AppendAttrString(
      attr_str, ah->FormatContent(NULL, false),
      UIStyle::kConversationCaptionFont, UIStyle::kConversationCaptionColor);
}

float InitInboxCardInternal(
    UIAppState* state, LayoutRow* row, const TrapdoorHandle& trh,
    const ViewpointHandle& vh, bool interactive, float weight, float width) {
  const float height = [InboxCardRowView getInboxCardHeightWithState:state
                                                        withTrapdoor:*trh
                                                           withWidth:width];
  if (!row) {
    return height;
  }

  ClearLayoutRow(row);

  row->view = [[InboxCardRowView alloc] initWithState:state
                                         withTrapdoor:trh
                                          interactive:interactive
                                            withWidth:width];

  [row->view addTextLayer:[InboxCardRowView
                            newTextLayerWithTrapdoor:*trh
                                       withViewpoint:vh
                                           withWidth:width
                                          withWeight:weight]];

  return height;
}

}  // namespace

////
// LayoutTransitionState

LayoutTransitionState::LayoutTransitionState(
    UIAppState* state, UIViewController* current)
    : state_(state),
      current_(current) {
  // Start the new view fully on screen.
  current_.view.frame = state_->ControllerFrame(current_);

  opacity_animation_ =
      [CAKeyframeAnimation animationWithKeyPath:@"opacity"];
  opacity_animation_.values = Array(0.0, 1.0);
  opacity_animation_.keyTimes = Array(0.0, 1.0);
  opacity_animation_.timingFunction =
      [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionEaseOut];
  opacity_animation_.duration = 0.3;
}

LayoutTransitionState::~LayoutTransitionState() {
  for (PhotoSet::iterator iter(matched_photos_.begin());
       iter != matched_photos_.end();
       ++iter) {
    PhotoView* const p = *iter;
    p.hidden = NO;
  }
  for (PhotoStateMap::iterator iter(photo_state_.begin());
       iter != photo_state_.end();
       ++iter) {
    if (iter->second.photo != iter->first) {
      // Only remove the photo if we were animating a copy.
      [iter->second.photo removeFromSuperview];
    }
  }
}

void LayoutTransitionState::FadeInAlpha(UIView* v) {
  if (!v) {
    return;
  }
  v.alpha = 0;
  fade_in_alpha_.insert(v);
}

void LayoutTransitionState::FadeInBackground(UIView* v) {
  if (!v || ContainsKey(fade_in_background_, v)) {
    return;
  }
  fade_in_background_[v] = v.backgroundColor;
  v.backgroundColor = [UIColor clearColor];
}

void LayoutTransitionState::SlideFromBottom(UIView* v) {
  if (!v || ContainsKey(orig_frame_, v)) {
    return;
  }
  orig_frame_[v] = v.frame;
  v.frameTop = v.frameBottom;
}

void LayoutTransitionState::ZoomIn(UIView* v) {
  if (!v) {
    return;
  }
  zoom_in_.insert(v);
}

void LayoutTransitionState::ZoomOut(UIView* v) {
  if (!v) {
    return;
  }
  zoom_out_.insert(v);
  v.transform = CGAffineTransformMakeScale(2, 2);
}

void LayoutTransitionState::PrepareRow(
    const LayoutRow& r, bool animate_event_photos,
    bool animate_conversation_photos) {
  // Animate the opacity of text layers added by ViewfinderTool.
  if (r.view.textLayer) {
    [r.view.textLayer addAnimation:opacity_animation_ forKey:NULL];
  }

  for (int i = 0; i < r.view.photos->size(); ++i) {
    PhotoView* const p = (*r.view.photos)[i];
    if (!p.image) {
      continue;
    }
    // TODO(pmattis): This is non-obvious and fragile. Find a better way to
    // identify conversation vs event photos other than using
    // PhotoView.selectable.
    if ((p.selectable && !animate_event_photos) ||
        (!p.selectable && !animate_conversation_photos)) {
      FadeInAlpha(r.view);
      continue;
    }

    PhotoView* const other_view =
        FindMatchingPhotoView(state_->photo_view_map(), p, p.episodeId != 0);
    PreparePhoto(p, other_view, true);

    FadeInAlpha(p);
  }
}

void LayoutTransitionState::PreparePhoto(
    PhotoView* p, PhotoView* other_view, bool animate_copy) {
  if (!other_view) {
    return;
  }

  // Convert the old photo frame to the window coordinate system.
  CGRect f = [other_view convertRect:other_view.bounds toView:NULL];
  if (!CGRectIntersectsRect(other_view.window.frame, f)) {
    return;
  }

  // Account for transforms (e.g. rotations).
  CGAffineTransform t =
      [other_view convertTransform:CGAffineTransformIdentity
                            toView:NULL];
  t = [p.superview convertTransform:t fromView:current_.view];

  PhotoState* s = &photo_state_[p];
  s->frame = p.frame;
  s->position = p.position;
  s->scale = p.zoomScale;

  if (animate_copy) {
    // Convert the old photo frame into the new coordinate system.
    f = [current_.view convertRectFromWindow:f];
    // Create a copy of other photo view and add to current
    // controller so it stays visible above all other layers. It
    // will be removed when the transition state is destructed.
    PhotoView* copy = NewPhotoView(
        state_, other_view.episodeId, other_view.photoId, other_view.aspectRatio, f);
    [current_.view addSubview:copy];
    s->photo = copy;
    s->frame = [p.superview convertRect:s->frame toView:current_.view];

    matched_photos_.insert(other_view);
    // Hide the other view (we have its copy to represent it), as
    // the original may be scrolling or otherwise moving, causing
    // the original and copy to diverge messily. We unhide this
    // when the animation is complete and we destroy the copy.
    other_view.hidden = YES;
  } else {
    // Convert the old photo frame into the new coordinate system.
    f = [p.superview convertRectFromWindow:f];
    s->photo = p;
  }

  s->photo.transform = t;
  s->photo.frame = f;
  s->photo.position = other_view.position;
  s->photo.zoomScale = other_view.zoomScale;
}

void LayoutTransitionState::PrepareFinish() {
  PrepareView(current_.view);
}

void LayoutTransitionState::PrepareView(UIView* v) {
  for (UIView* s in v.subviews) {
    PrepareView(s);
  }

  if (v.backgroundColor) {
    FadeInBackground(v);
  }

  if (v.tag) {
    FadeInAlpha(v);
  }
}

void LayoutTransitionState::Commit() {
  for (PhotoStateMap::iterator iter(photo_state_.begin());
       iter != photo_state_.end();
       ++iter) {
    PhotoView* p = iter->first;
    const PhotoState& s = iter->second;
    // We need to set the PhotoView position before the frame due to the way
    // the position causes the bounds to be adjusted. This is only necessary
    // because we're within an animation block and UIKit animation triggers off
    // the setting of UIView properties.
    s.photo.position = s.position;
    s.photo.zoomScale = s.scale;
    s.photo.transform = CGAffineTransformIdentity;
    s.photo.frame = s.frame;
    if (s.photo != p) {
      // Only fade the alpha if we're animating a copy.
      s.photo.alpha = 0;
    }
  }

  for (ViewFrameMap::iterator iter(orig_frame_.begin());
       iter != orig_frame_.end();
       ++iter) {
    iter->first.frame = iter->second;
  }

  for (ViewColorMap::iterator iter(fade_in_background_.begin());
       iter != fade_in_background_.end();
       ++iter) {
    iter->first.backgroundColor = iter->second;
  }

  for (ViewSet::iterator iter(fade_in_alpha_.begin());
       iter != fade_in_alpha_.end();
       ++iter) {
    UIView* const v = *iter;
    v.alpha = 1;
  }

  for (ViewSet::const_iterator iter(zoom_in_.begin());
       iter != zoom_in_.end();
       ++iter) {
    UIView* const v = *iter;
    v.transform = CGAffineTransformMakeScale(2, 2);
  }

  for (ViewSet::const_iterator iter(zoom_out_.begin());
       iter != zoom_out_.end();
       ++iter) {
    UIView* const v = *iter;
    v.transform = CGAffineTransformIdentity;
  }
}

float GetSummaryEventHeight(
    UIAppState* state, const Event& ev, PhotoLayoutType layout,
    float width, const DBHandle& db) {
  return [EventRowView getEventHeightWithState:state
                                     withEvent:ev
                                     withWidth:width
                                        withDB:db];
}

float GetFullEventHeight(
    UIAppState* state, const Event& ev, float width, const DBHandle& db) {
  return [FullEventRowView getEventHeightWithState:state
                                         withEvent:ev
                                         withWidth:width
                                            withDB:db];
}

float GetInboxCardHeight(
    UIAppState* state, const Trapdoor& trap, float width) {
  return [InboxCardRowView getInboxCardHeightWithState:state withTrapdoor:trap withWidth:width];
}

float InitShareActivityPhotosRow(
    UIAppState* state, EpisodeLayoutRow* row,
    EpisodeLayoutType layout_type, const vector<PhotoHandle>& photos,
    const vector<EpisodeHandle>& episodes,
    float width, float y, const DBHandle& db) {
  float left_margin;
  left_margin = kConversationPhotosMargin;
  const float group_width = width - left_margin * 2;

  // Gather up the aspect ratios.
  vector<float> aspect_ratios(photos.size(), 0);
  for (int k = 0; k < photos.size(); ++k) {
    aspect_ratios[k] = photos[k]->aspect_ratio();
  }

  // Apply the tile layout.
  vector<CGRect> frames(photos.size());
  const float height =
      ShareLayout::Apply(
          aspect_ratios, &frames, NULL, group_width, UIStyle::kGutterSpacing, 1.0);

  if (row) {
    ClearLayoutRow(row);
    row->timestamp = photos[0]->timestamp();
    row->type = ViewpointSummaryMetadata::PHOTOS;

    // Init the row view.
    row->view = [RowView new];
    row->view.frame = CGRectInset(
        CGRectMake(0, y, width, height), left_margin, 0);
    row->view.tag = kEpisodeRowTag;
    row->view.backgroundColor = UIStyle::kConversationShareBackgroundColor;

    // Create the PhotoViews.
    row->view.photos->resize(photos.size(), NULL);
    for (int k = 0; k < photos.size(); ++k) {
      const PhotoHandle& ph = photos[k];
      const EpisodeHandle& eh = episodes[k];
      PhotoView* p = NewPhotoView(
          state, eh->id().local_id(), ph->id().local_id(), ph->aspect_ratio(), frames[k]);
      p.tag = kEpisodePhotoTag;
      (*row->view.photos)[k] = p;
      [row->view addSubview:p];
    }
  }

  return height;
}

float InitEventPhotos(
    UIAppState* state, RowView* row_view, UIView* parent_view,
    const FilteredEpisodes& episodes, PhotoLayoutType photo_layout,
    float width, bool* can_expand, const DBHandle& db) {
  if (can_expand) {
    *can_expand = false;
  }
  float y = 0;
  // Get all photos for layout.
  vector<PhotoHandle> photos;
  std::unordered_map<int64_t, int64_t> photo_episode_map;
  for (int i = 0; i < episodes.size(); ++i) {
    const FilteredEpisode& ep = episodes.Get(i);
    for (int j = 0; j < ep.photo_ids_size(); ++j) {
      const PhotoHandle ph = state->photo_table()->LoadPhoto(ep.photo_ids(j), db);
      if (ph.get()) {
        photos.push_back(ph);
        photo_episode_map[ep.photo_ids(j)] = ep.episode_id();
      }
    }
  }
  std::sort(photos.begin(), photos.end(), PhotoGreaterThan());

  // Gather up the aspect ratios.
  vector<float> aspect_ratios(photos.size(), 0);
  for (int i = 0; i < photos.size(); ++i) {
    aspect_ratios[i] = photos[i]->aspect_ratio();
  }

  // Apply the tile layout.
  vector<CGRect> frames(photos.size());
  int num_rows;
  EventLayout::Apply(aspect_ratios, &frames, &num_rows, width, UIStyle::kGutterSpacing, 1.0);

  // If we're in an expanded layout, we display all rows; otherwise,
  // we limit view to 3, and sample them at regular intervals.
  float fractional_row = 0;
  float fractional_step =
      (photo_layout == SUMMARY_COLLAPSED_LAYOUT && num_rows > 3) ? 3.0 / num_rows : 1.0;
  for (int j = 0, n = 0, row_count = 0; j < num_rows;
       ++j, fractional_row += fractional_step) {
    // Compute height of this row including leading spacing if not the 1st row.
    const float spacing = row_count > 0 ? UIStyle::kGutterSpacing : 0;
    const float height = frames[n].size.height + spacing;

    // Gather up the photos for the "j"th row of photos.
    const int start_n = n;
    int photo_count = 0;
    float cur_y = CGRectGetMinY(frames[n]);
    for (; n < frames.size(); ++n) {
      if (CGRectGetMinY(frames[n]) > cur_y) {
        break;
      }
      ++photo_count;
    }

    // Sample rows if necessary.
    if (fractional_step != 1.0 && fractional_row < row_count) {
      if (can_expand) {
        *can_expand = true;
      }
      continue;
    }

    if (row_view) {
      // Create the PhotoViews.
      for (int k = start_n; k < start_n + photo_count; ++k) {
        const PhotoHandle& ph = photos[k];
        DCHECK(ContainsKey(photo_episode_map, ph->id().local_id()));
        CGRect f = frames[k];
        f.origin.y = y + spacing;
        PhotoView* p = NewPhotoView(
            state, photo_episode_map[ph->id().local_id()],
            ph->id().local_id(), ph->aspect_ratio(), f);
        p.tag = kEpisodePhotoTag;
        row_view.photos->push_back(p);
        [parent_view addSubview:p];
      }
    }

    ++row_count;
    y += height;
  }

  return y;
}

float InitInboxCardPhotos(
    UIAppState* state, RowView* row_view, UIView* parent_view,
    const DayPhotos& photos, PhotoLayoutType layout,
    float width, bool* can_expand) {
  if (can_expand) {
    *can_expand = photos.size() > 0;
  }

  float y = 0;
  // Gather up the aspect ratios.
  vector<float> aspect_ratios(photos.size(), 0);
  for (int i = 0; i < photos.size(); ++i) {
    aspect_ratios[i] = photos.Get(i).aspect_ratio();
  }

  // Apply the tile layout.
  vector<CGRect> frames(photos.size());
  int num_rows;
  if (layout == SUMMARY_COLLAPSED_LAYOUT) {
    InboxCardLayout::Apply(
        aspect_ratios, &frames, &num_rows, width, UIStyle::kGutterSpacing, 3.0);
  } else {
    InboxCardLayout::ApplyExpanded(
        aspect_ratios, &frames, &num_rows, width, UIStyle::kGutterSpacing, 1.5);
  }

  // If we're in an expanded layout, we display all rows; otherwise, just one.
  if (layout == SUMMARY_COLLAPSED_LAYOUT && num_rows > 1) {
    num_rows = 1;
  }
  for (int j = 0, n = 0; j < num_rows; ++j) {
    // Compute height of this row including leading spacing if not the 1st row.
    const float spacing = j > 0 ? UIStyle::kGutterSpacing : 0;
    const float height = frames[n].size.height + spacing;

    // Gather up the photos for the "j"th row of photos.
    const int start_n = n;
    int photo_count = 0;
    float cur_y = CGRectGetMinY(frames[n]);
    for (; n < frames.size(); ++n) {
      if (CGRectGetMinY(frames[n]) > cur_y) {
        break;
      }
      ++photo_count;
    }

    if (row_view) {
      // Create the PhotoViews.
      for (int k = start_n; k < start_n + photo_count; ++k) {
        const DayPhoto& dp = photos.Get(k);
        CGRect f = frames[k];
        f.origin.y = y + spacing;
        PhotoView* p = NewPhotoView(
            state, dp.episode_id(), dp.photo_id(), dp.aspect_ratio(), f);
        p.tag = kEpisodePhotoTag;
        row_view.photos->push_back(p);
        [parent_view addSubview:p];
      }
    }

    y += height;
  }

  return y;
}

float InitConversationHeader(
    UIAppState* state, LayoutRow* row, int64_t viewpoint_id,
    int64_t cover_photo_id, int64_t cover_episode_id,
    float cover_aspect_ratio, float width) {
  DCHECK(dispatch_is_main_thread());
  ConversationHeaderRowView* view =
      [[ConversationHeaderRowView alloc] initWithState:state
                                           viewpointId:viewpoint_id
                                         hasCoverPhoto:(cover_photo_id != 0)
                                                 width:width];

  // The title and followers header.
  if (row != NULL) {
    ClearLayoutRow(row);
    row->view = view;

    if (!cover_photo_id) {
      cover_aspect_ratio = 1;
    } else {
      PhotoView* const p = NewPhotoView(
          state, cover_episode_id, cover_photo_id,
          cover_aspect_ratio, CGRectMake(0, 0, width, view.coverPhotoHeight));
      [view setCoverPhoto:p];
    }
  }
  return view.frameHeight;
}

float InitBrowsingCard(
    UIAppState* state, LayoutRow* row, const TrapdoorHandle& trh,
    const ViewpointHandle& vh, float weight, float width) {
  return InitInboxCardInternal(
      state, row, trh, vh, false, weight, width);
}

float InitInboxCard(
    UIAppState* state, LayoutRow* row, const TrapdoorHandle& trh,
    const ViewpointHandle& vh, bool interactive, float weight, float width) {
  return InitInboxCardInternal(
      state, row, trh, vh, interactive, weight, width);
}

void InitSummaryEvent(
    UIAppState* state, LayoutRow* row, const EventHandle& evh,
    float weight, float width, const DBHandle& db) {
  ClearLayoutRow(row);

  row->view = [[EventRowView alloc] initWithState:state
                                        withEvent:evh
                                        withWidth:width
                                           withDB:db];
  [row->view addTextLayer:
        [[EventCardTextLayer alloc] initWithEvent:*evh withWeight:weight]];
}

void InitFullEvent(
    UIAppState* state, LayoutRow* row, const EventHandle& evh,
    bool single_photo_selection, float weight, float width, const DBHandle& db) {
  ClearLayoutRow(row);

  row->view = [[FullEventRowView alloc] initWithState:state
                                            withEvent:evh
                                            withWidth:width
                                               withDB:db];
  [row->view addTextLayer:
        [[FullEventCardTextLayer alloc] initWithEvent:*evh withWeight:weight]];

  row->view.editing = !single_photo_selection;
}

float InitConversationUpdate(
    UIAppState* state, LayoutRow* row, const ViewpointHandle& vh,
    const ActivityHandle& ah, ActivityUpdateType update_type,
    int row_index, float width, const DBHandle& db) {
  const float left_margin = kConversationUpdateLeftMargin;
  const float top_margin = kConversationUpdateTopMargin;

  const float content_width = width - kConversationMargin * 2;
  const float text_width = content_width - left_margin - kConversationSpacing;

  NSMutableAttributedString* attr_str = [NSMutableAttributedString new];
  FormatConversationUpdate(state, vh, ah, attr_str);

  TextLayer* activity_text = [TextLayer new];
  activity_text.maxWidth = text_width;
  activity_text.attrStr = attr_str;

  activity_text.anchorPoint = CGPointMake(0, 0);
  activity_text.position = CGPointMake(left_margin, top_margin);
  const float bottom = CGRectGetMaxY(activity_text.frame) + kConversationUpdateBottomMargin;

  if (row) {
    ClearLayoutRow(row);
    row->view = [RowView new];
    row->view.backgroundColor =
        (row_index % 2) ? UIStyle::kConversationOddRowColor :
        UIStyle::kConversationEvenRowColor;
    row->view.tag = kConversationUpdateTag;
    row->view.frame = CGRectInset(
        CGRectMake(0, 0, width, bottom), kConversationMargin, 0);
    row->view.layer.sublayerTransform =
        CATransform3DMakeTranslation(-kConversationMargin, 0, 0);

    InitActivityStatusIndicator(state, row->view, ah, bottom);
    [row->view.layer addSublayer:activity_text];
  }

  return bottom;
}

float InitConversationActivity(
    UIAppState* state, LayoutRow* row, const ViewpointHandle& vh,
    const ActivityHandle& ah, const ViewpointSummaryMetadata::ActivityRow* activity_row,
    int64_t reply_to_photo_id, int64_t reply_to_episode_id,
    ActivityThreadType thread_type, int row_index, float width, const DBHandle& db) {
  const bool is_continuation = IsThreadTypeCombine(thread_type);
  const bool is_share = ah->has_share_new() || ah->has_share_existing();
  const float left_margin = kActivityContentLeftMargin;
  const float right_margin = reply_to_photo_id != -1 ?
      kActivityReplyToRightMargin : kConversationSpacing;
  float y = 0;
  if (is_continuation) {
    y += kActivityContinuationMargin;
  } else {
    const float top_margin = reply_to_photo_id != -1 ?
                             kActivityReplyToTopMargin : kActivityContentTopMargin;
    y += top_margin + kConversationSpacing;
    if (is_share) {
      y += kShareActivityTitleHeight;
    } else {
      y += kActivityTitleHeight;
    }
  }

  const float content_width = width - kConversationMargin * 2;
  const float text_width = content_width - left_margin - right_margin;

  const float top_margin = y;

  NSMutableAttributedString* attr_str = [NSMutableAttributedString new];
  NSRange comment_range = { attr_str.length, 0 };
  if (is_share) {
    AppendAttrString(attr_str, ah->FormatContent(activity_row, false),
                     UIStyle::kConversationSharePhotosFont,
                     UIStyle::kConversationSharePhotosColor);
  } else {
    AppendAttrString(attr_str, ah->FormatContent(activity_row, false),
                     UIStyle::kConversationMessageFont,
                     UIStyle::kConversationMessageColor);
  }
  if (ah->has_post_comment()) {
    comment_range.length = attr_str.length - comment_range.location;
  }

  if (thread_type == THREAD_COMBINE_WITH_TIME ||
      thread_type == THREAD_COMBINE_NEW_USER_WITH_TIME ||
      thread_type == THREAD_COMBINE_END_WITH_TIME) {
    AppendAttrString(attr_str,
                     Format("%s%s", kSpaceSymbol, FormatTime(ah->timestamp())),
                     UIStyle::kConversationTimeFont,
                     UIStyle::kConversationTimeColor);
  }

  float bottom_margin = kConversationSpacing;
  if (is_share) {
    attr_str = AttrTruncateTail(attr_str);
    y += kConversationSpacing +
         [ShareActivityRowView suggestedHeight:attr_str textWidth:text_width];
  } else {
    y += kConversationSpacing +
         [ConversationActivityRowView suggestedHeight:attr_str textWidth:text_width];
    if (thread_type != THREAD_COMBINE &&
        thread_type != THREAD_COMBINE_WITH_TIME) {
      y += kActivityContentBottomMargin;
      bottom_margin += kActivityContentBottomMargin;
    }
  }

  if (row) {
    ClearLayoutRow(row);
    if (is_share) {
      row->view = [[ShareActivityRowView alloc]
                    initWithActivity:ah
                     withActivityRow:activity_row
                                text:attr_str
                           textWidth:text_width
                           topMargin:top_margin
                        bottomMargin:bottom_margin
                          leftMargin:left_margin
                          threadType:thread_type
                             comment:comment_range];
    } else {
      row->view = [[ConversationActivityRowView alloc]
                    initWithActivity:ah
                                text:attr_str
                           textWidth:text_width
                           topMargin:top_margin
                        bottomMargin:bottom_margin
                          leftMargin:left_margin
                          threadType:thread_type
                             comment:comment_range];
    }
    row->view.backgroundColor =
        (row_index % 2) ? UIStyle::kConversationOddRowColor :
        UIStyle::kConversationEvenRowColor;
    row->view.tag = kConversationActivityTag;
    row->view.frame = CGRectInset(CGRectMake(0, 0, width, y), kConversationMargin, 0);
    row->view.layer.sublayerTransform =
        CATransform3DMakeTranslation(-kConversationMargin, 0, 0);

    if (reply_to_photo_id != -1) {
      PhotoHandle ph = state->photo_table()->LoadPhoto(reply_to_photo_id, db);
      if (ph.get()) {
        PhotoView* p = NewPhotoView(
            state, reply_to_episode_id, reply_to_photo_id, ph->aspect_ratio(),
            CGRectMake(width - kReplyToThumbnailDim - kActivityPhotoRightMargin,
                       kActivityPhotoTopMargin,
                       kReplyToThumbnailDim,
                       kReplyToThumbnailDim));
        p.selectable = true;
        row->view.photos->push_back(p);
        [row->view addSubview:NewReplyToShadow(p)];
      }
    }

    const bool is_continuation = IsThreadTypeCombine(thread_type);
    [row->view addTextLayer:
          [[ActivityTextLayer alloc] initWithActivity:ah
                                      withActivityRow:activity_row
                                       isContinuation:is_continuation]];

    InitActivityStatusIndicator(state, row->view, ah, y);

    DCHECK_EQ(y, row->view.desiredFrameHeight);
  }

  return y;
}

@interface RoundedCornersView : UIView {
 @private
  UIView* top_left_;
  UIView* top_right_;
  UIView* bottom_left_;
  UIView* bottom_right_;
}

- (id)init;

@end  // RoundedCornersView;


@implementation RoundedCornersView

- (id)init {
  if (self = [super init]) {
    self.autoresizingMask =
        UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    self.layer.zPosition = 10000;

    top_left_ = [[UIImageView alloc] initWithImage:UIStyle::kCornerTopLeft];
    top_left_.autoresizingMask =
        UIViewAutoresizingFlexibleRightMargin | UIViewAutoresizingFlexibleBottomMargin;
    [self addSubview:top_left_];

    top_right_ = [[UIImageView alloc] initWithImage:UIStyle::kCornerTopRight];
    top_right_.autoresizingMask =
        UIViewAutoresizingFlexibleLeftMargin | UIViewAutoresizingFlexibleBottomMargin;
    [self addSubview:top_right_];

    bottom_left_ = [[UIImageView alloc] initWithImage:UIStyle::kCornerBottomLeft];
    bottom_left_.autoresizingMask =
        UIViewAutoresizingFlexibleRightMargin | UIViewAutoresizingFlexibleTopMargin;
    [self addSubview:bottom_left_];

    bottom_right_ = [[UIImageView alloc] initWithImage:UIStyle::kCornerBottomRight];
    bottom_right_.autoresizingMask =
        UIViewAutoresizingFlexibleLeftMargin | UIViewAutoresizingFlexibleTopMargin;
    [self addSubview:bottom_right_];
  }
  return self;
}

- (void)layoutSubviews {
  [super layoutSubviews];

  top_right_.frameRight = self.boundsWidth;
  bottom_left_.frameBottom = self.boundsHeight;
  bottom_right_.frameRight = self.boundsWidth;
  bottom_right_.frameBottom = self.boundsHeight;
}

@end  // RoundedCornersView;

void AddRoundedCorners(UIView* view) {
  DCHECK(view.autoresizesSubviews) << "containing view must autoresize subviews";
  [view addSubview:[RoundedCornersView new]];
}

PhotoView* NewPhotoView(
    UIAppState* state, int64_t episode_id, int64_t photo_id,
    float aspect_ratio, const CGRect& frame) {
  PhotoView* p = [[PhotoView alloc] initWithState:state];
  p.aspectRatio = aspect_ratio;
  p.episodeId = episode_id;
  p.frame = frame;
  p.photoId = photo_id;
  [p ensureVerticalParallax:1.1];
  InitPhotoViewImage(state->photo_view_map(), p);
  return p;
}

UIView* NewReplyToShadow(PhotoView* p) {
  UIView* shadow = [UIView new];
  shadow.frame = p.frame;
  shadow.layer.shadowColor = [UIColor blackColor].CGColor;
  shadow.layer.shadowOpacity = 0.5;
  shadow.layer.shadowRadius = 1;
  shadow.layer.shadowOffset = CGSizeMake(0, 0);
  ScopedRef<CGPathRef> shadow_path(
      CGPathCreateWithRect(shadow.bounds, NULL));
  shadow.layer.shadowPath = shadow_path;

  p.frame = shadow.bounds;
  [shadow addSubview:p];
  return shadow;
}

void BuildPhotoViewMap(PhotoViewMap* map, UIView* v) {
  if ([v isKindOfClass:[PhotoView class]]) {
    PhotoView* p = (PhotoView*)v;
    (*map)[p.photoId].push_back(p);
  } else {
    for (UIView* s in v.subviews) {
      if (!s.hidden) {
        BuildPhotoViewMap(map, s);
      }
    }
  }
}

PhotoView* FindMatchingPhotoView(
    PhotoViewMap* map, PhotoView* p, bool require_episode_match) {
  vector<PhotoView*>* v = FindPtrOrNull(map, p.photoId);
  if (!v) {
    return NULL;
  }
  const CGSize desired_size = p.frame.size;
  PhotoView* best = NULL;
  float best_scale = 0;
  for (int i = 0; i < v->size(); ++i) {
    PhotoView* o = (*v)[i];
    const CGSize load_size = o.loadSize;
    if ((require_episode_match && o.episodeId != p.episodeId) ||
        load_size.width == 0 || load_size.height == 0) {
      continue;
    }
    const float scale = std::max(
        desired_size.width / load_size.width,
        desired_size.height / load_size.height);
    if (scale == 1.0) {
      // An exact match.
      return o;
    } else if (scale < 1.0) {
      // The image is larger than the desired size. We want the image that
      // minimizes down-scaling.
      if (best_scale < scale) {
        best = o;
        best_scale = scale;
      }
    } else {
      // The image is smaller than the desired size. We want the image that
      // minimizes up-scaling.
      if (!best || best_scale > scale) {
        best = o;
        best_scale = scale;
      }
    }
  }
  return best;
}

void InitPhotoViewImage(PhotoViewMap* map, PhotoView* p) {
  PhotoView* o = FindMatchingPhotoView(map, p);
  if (!o) {
    return;
  }
  p.image = o.image;
  p.loadSize = o.loadSize;
}

// local variables:
// mode: c++
// end:
