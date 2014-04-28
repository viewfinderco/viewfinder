// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.
// Author: Peter Mattis.

// TODO(spencer):
//  - Fix timestamps & time formats reported to viewfinder.

#import <QuartzCore/QuartzCore.h>
#import "Analytics.h"
#import "AssetsManager.h"
#import "BadgeView.h"
#import "CALayer+geometry.h"
#import "CheckmarkBadge.h"
#import "ConversationHeaderRowView.h"
#import "ConversationLayoutController.h"
#import "ConversationUtils.h"
#import "CppDelegate.h"
#import "Defines.h"
#import "ExportUtils.h"
#import "Image.h"
#import "InboxCardRowView.h"
#import "LayoutController.h"
#import "Logging.h"
#import "MathUtils.h"
#import "NetworkManager.h"
#import "PhotoLoader.h"
#import "PhotoManager.h"
#import "PhotoUtils.h"
#import "PhotoView.h"
#import "RootViewController.h"
#import "ServerUtils.h"
#import "ShareActivityRowView.h"
#import "StatusBar.h"
#import "SummaryToolbar.h"
#import "SummaryView.h"
#import "TileLayout.h"
#import "Timer.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

@class ConversationScrollView;

namespace {

const float kCommentThreadThreshold = 60 * 60;

const float kConversationSpacing = 10;
const float kConversationMargin = 8;

const float kBrowsingTextLeftMargin = 16;
const float kBrowsingTextWithCoverPhotoLeftMargin = 60;
const float kBrowsingTextTopMargin = 45;
const float kBrowsingTimeoutSecs = 1.0;

const float kActivityTextLeftMargin = 38;
const float kActivityReplyTextLeftMargin = 38;
const float kActivityTextTopMargin = 18.5;
const float kActivityReplyTextTopMargin = 18.5;

const float kDuration = 0.3;

const int kActionSheetUnshareTag = 1;
const int kActionSheetShareTag = 2;

LazyStaticImage kConvoNegativeCornerLL(
    @"convo-negative-corner-ll.png");
LazyStaticImage kConvoNegativeCornerLR(
    @"convo-negative-corner-lr.png");

LazyStaticHexColor kConversationBackgroundColor = { "#3f3e3e" };

CGRect RowCacheFrame(const CGRect& f) {
  return CGRectInset(f, 0, -f.size.height / 2);
}

string MakeActionTitle(const string& action, int n) {
  if (n > 1) {
    return Format("%s %d Photos", action, n);
  }
  return Format("%s Photo", action);
}

UIView* MakeBrowsingOverlay(UIScrollView* parent) {
  UIView* v = [UIView new];
  v.alpha = 0;
  v.backgroundColor = [UIColor blackColor];
  CGRect f = parent.bounds;
  f.size.width = std::max(f.size.width, parent.contentSize.width);
  f.size.height = std::max(f.size.height, parent.contentSize.height);
  v.frame = f;
  [parent addSubview:v];
  return v;
}

}  // namespace

@implementation ConversationScrollView

@synthesize visibleInsets = visible_insets_;
@synthesize scrollingAnimation = scrolling_animation_;

- (BOOL)touchesShouldCancelInContentView:(UIView*)view {
  return YES;
}

- (void)scrollRectToVisible:(CGRect)rect
                   animated:(BOOL)animated {
  // NOTE(peter): This code does not perform horizontal scrolling. Simple to
  // add, just isn't needed at the moment.
  CGRect bounds = self.bounds;
  CGRect visible_bounds = self.visibleBounds;
  const CGRect scroll_bounds =
      CGRectMake(0, 0, self.contentSize.width, self.contentSize.height);

  // Increase the size of rect so that original rect is vertically centered
  // and intersect with visible bounds.
  rect = CGRectInset(rect, 0, -(visible_bounds.size.height - rect.size.height) / 2);
  rect = CGRectIntersection(scroll_bounds, rect);

  if (CGRectGetMaxY(rect) > CGRectGetMaxY(visible_bounds)) {
    const float delta = CGRectGetMaxY(rect) - CGRectGetMaxY(visible_bounds);
    bounds.origin.y += delta;
    visible_bounds.origin.y += delta;
  }
  if (CGRectGetMinY(rect) < CGRectGetMinY(visible_bounds)) {
    const float delta = CGRectGetMinY(visible_bounds) - CGRectGetMinY(rect);
    bounds.origin.y -= delta;
    visible_bounds.origin.y -= delta;
  }
  bounds.origin.y = std::max(bounds.origin.y, self.contentOffsetMinY);
  bounds.origin.y = std::min(bounds.origin.y, self.contentOffsetMaxY);
  [self setContentOffset:bounds.origin animated:animated];
}

- (void)setContentOffset:(CGPoint)offset
                animated:(BOOL)animated {
  // Set the scrolling-animation bool to prevent any concurrent day
  // table updates from spoiling the completion of the animation.
  scrolling_animation_ = animated && fabs(offset.y - self.contentOffsetY) >= 0.5;

  // If the distance to scroll exceeds two pages, animate with a cross
  // fade instead of the clunky animated-offset-scroll.
  if (animated && fabs(self.contentOffsetY - offset.y) > 2 * self.boundsHeight) {
    // Set offset to half a page from target without animation.
    const CGPoint partial_offset =
        CGPointMake(offset.x, offset.y + (self.contentOffsetY < offset.y ?
                                          -2 * self.boundsHeight : 2 * self.boundsHeight));
    [super setContentOffset:partial_offset animated:NO];
    // Animate with a cross fade and also set up an animated scroll
    // to the final offset so the perception of a scroll is maintained.
    [UIView transitionWithView:self
                      duration:0.3
                       options:UIViewAnimationOptionTransitionCrossDissolve
                    animations:^{
        [super setContentOffset:offset animated:NO];
      }
                    completion:^(BOOL finished) {
        self.scrollingAnimation = false;
      }];
  } else {
    [super setContentOffset:offset animated:animated];
  }
}

- (CGRect)visibleBounds {
  CGRect bounds = self.bounds;
  bounds.origin.y += visible_insets_.top;
  bounds.size.height -= visible_insets_.top + visible_insets_.bottom;
  return bounds;
}

@end  // ConversationScrollView

@implementation ConversationLayoutController

@synthesize pendingComment = pending_comment_;
@synthesize pendingAddPhotos = pending_add_photos_;

- (id)initWithState:(UIAppState*)state {
  if (self = [super initWithState:state]) {
    self.wantsFullScreenLayout = YES;

    need_rebuild_ = false;
    viewfinder_active_ = false;
    visible_conversations_ = std::make_pair(-1, -1);
    editing_row_index_ = -1;
    visible_conversation_ = -1;

    // Avoid a reference cycle by using a weak pointer to self.
    __weak ConversationLayoutController* weak_self = self;
    photo_queue_.name = "conversation";
    photo_queue_.block = [^(vector<PhotoView*>* q) {
        [weak_self photoLoadPriorityQueue:q];
      } copy];

    state_->app_did_become_active()->Add(^{
        [self maybeRebuildConversations];
      });
    // Receive notifications for refreshes to the day metadata.
    state_->day_table()->update()->Add(^{
        need_rebuild_ = true;
        [self maybeRebuildConversations];
      });

    // TODO(peter): This improves the first conversation view time, but at the
    // expense of consuming ~375ms on the main thread.
    //
    // state_->async()->dispatch_after_main(3, ^{
    //     // Pre-warm the controller so we don't pay various one-time
    //     // construction costs the first time a conversation is viewed.
    //     if (!self.visible) {
    //       WallTimer timer;
    //       self.view.frame = state_->ControllerFrame(self);
    //       rebuilding_ = true;
    //       [self viewWillAppear:NO];
    //       [self viewDidDisappear:NO];
    //       rebuilding_ = false;
    //       LOG("conversation: pre-warmed: %.3f ms", timer.Milliseconds());
    //     }
    //   });
  }
  return self;
}

- (NSString*)title:(CachedConversation*)c {
  ConversationHeaderRowView* header = [self getHeaderRowView:c];
  return header.emptyTitle ? @"Conversation" : header.title;
}

- (CGPoint)conversationOffset:(int)index {
 return CGPointMake(
      horizontal_scroll_.boundsWidth * index, 0);
}

- (CGRect)conversationBounds:(int)index {
  // The conversation scroll view is the size of the main view, but positioned
  // according to the width of the main scroll view (which is
  // kConversationSpacing wider than the main view).
  const CGPoint p = [self conversationOffset:index];
  return CGRectMake(p.x, p.y,
                    self.view.boundsWidth,
                    horizontal_scroll_.boundsHeight);
}

- (CGRect)visibleBounds {
  return horizontal_scroll_.bounds;
}

- (CGRect)cacheBounds {
  return self.visibleBounds;
}

- (float)cardHeight:(CachedConversation*)c {
  return c->vsh->total_height() + kConversationMargin;
}

- (CGRect)conversationCacheBounds:(CachedConversation*)c {
  return RowCacheFrame(c->scroll_view.bounds);
}

- (int)minVisibleRow:(CachedConversation*)c
              bounds:(const CGRect&)bounds {
  const float y_min = CGRectGetMinY(bounds);
  const int num_rows = c->vsh->activities_size();
  int s = 0;
  int e = num_rows;
  while (s != e) {
    CHECK_LT(s, e);
    const int m = (s + e) / 2;
    const int start_y = c->vsh->activities(m).position();
    const int end_y = start_y + c->vsh->activities(m).height();
    if (end_y < y_min) {
      // Row m is before the visible bounds.
      s = m + 1;
    } else if (start_y < y_min) {
      // Row m intersects the start of the visible bounds.
      return m;
    } else {
      // Row m is after the visible bounds.
      e = m;
    }
  }
  return std::max<int>(0, std::min<int>(s, num_rows - 1));
}

- (int)maxVisibleRow:(CachedConversation*)c
              bounds:(const CGRect&)bounds {
  const float y_max = CGRectGetMaxY(bounds);
  const float num_rows = c->vsh->activities_size();
  int s = 0;
  int e = num_rows;
  while (s != e) {
    CHECK_LT(s, e);
    const int m = (s + e) / 2;
    const int start_y = c->vsh->activities(m).position();
    const int end_y = start_y + c->vsh->activities(m).height();
    if (start_y >= y_max) {
      // Row m is after the end visible bounds.
      e = m;
    } else if (end_y >= y_max) {
      // Row m intersects the end of the visible bounds.
      return m;
    } else {
      // Row m is before the end visible bounds.
      s = m + 1;
    }
  }
  return std::max<int>(0, std::min<int>(s, num_rows - 1));
}

- (RowRange)rowRange:(CachedConversation*)c
              bounds:(const CGRect&)bounds {
  return RowRange([self minVisibleRow:c bounds:bounds],
                  [self maxVisibleRow:c bounds:bounds]);
}

- (int)numConversations {
  return snapshot_->conversations()->row_count();
}

- (int)minVisibleConversation:(const CGRect&)bounds {
  const float width = horizontal_scroll_.boundsWidth;
  const int row = CGRectGetMinX(bounds) / width;
  return std::max<int>(0, std::min<int>(self.numConversations - 1, row));
}

- (int)maxVisibleConversation:(const CGRect&)bounds {
  const float width = horizontal_scroll_.boundsWidth;
  const int row = (CGRectGetMaxX(bounds) + width - 1) / width;
  return std::min<int>(self.numConversations - 1, std::max<int>(0, row - 1));
}

- (ConversationRange)conversationRange:(const CGRect&)bounds {
  return ConversationRange([self minVisibleConversation:bounds],
                           [self maxVisibleConversation:bounds]);
}

- (CachedConversation*)currentConversation {
  return FindPtrOrNull(&conversation_cache_, visible_conversations_.first);
}

- (UIView*)currentConversationView {
  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return NULL;
  }
  return c->content_view;
}

- (CachedConversation*)conversationForRowView:(RowView*)row {
  for (ConversationCacheMap::iterator iter(conversation_cache_.begin());
       iter != conversation_cache_.end();
       ++iter) {
    CachedConversation* c = &iter->second;
    if (c->scroll_view == row.superview) {
      return c;
    }
  }
  return NULL;
}

- (CGPoint)rowTextOffset:(const ViewpointSummaryMetadata::ActivityRow&)row {
  if (row.type() == ViewpointSummaryMetadata::ACTIVITY ||
      (row.type() == ViewpointSummaryMetadata::REPLY_ACTIVITY &&
       row.photos(0).episode_id() == 0)) {
    return { kActivityTextLeftMargin, kActivityTextTopMargin };
  } else if (row.type() == ViewpointSummaryMetadata::REPLY_ACTIVITY) {
    return { kActivityReplyTextLeftMargin, kActivityReplyTextTopMargin };
  }
  return { 0, 0 };
}

- (float)rowTextMaxWidth:(const ViewpointSummaryMetadata::ActivityRow&)row {
  return self.view.frameWidth - [self rowTextOffset:row].x * 2;
}

- (bool)keyboardVisible {
  return keyboard_frame_.origin.y > 0;
}

- (void)initContentSize {
  // Disable calls to the scroll view delegate while we update the content
  // size.
  horizontal_scroll_.delegate = NULL;
  horizontal_scroll_.contentSize = CGSizeMake(
      [self conversationOffset:self.numConversations].x,
      horizontal_scroll_.boundsHeight);
  horizontal_scroll_.delegate = self;
}

- (int64_t)getViewpointId:(int)row_index {
  SummaryRow row;
  if (!snapshot_->conversations()->GetSummaryRow(row_index, &row)) {
    LOG("unable to find row index: %d", row_index);
    return 0;
  }
  return row.identifier();
}

- (void)initContentPosition {
  int index = -1;
  if (controller_state_.current_viewpoint == 0) {
    LOG("conversations: ERROR current viewpoint is not set");
  } else {
    index = snapshot_->conversations()->GetViewpointRowIndex(
        controller_state_.current_viewpoint);
    VLOG("conversations: init current viewpoint to %d as row index %d",
         controller_state_.current_viewpoint, index);
  }
  // Disable calls to the scroll view delegate while we update the content
  // position.
  horizontal_scroll_.delegate = NULL;
  if (index == -1) {
    horizontal_scroll_.contentOffsetX =
        std::min(horizontal_scroll_.contentOffsetX,
                 horizontal_scroll_.contentOffsetMaxX);
  } else {
    horizontal_scroll_.contentOffset = [self conversationOffset:index];
  }
  horizontal_scroll_.delegate = self;
}

- (ContentView*)contentViewAtPoint:(const CGPoint&)p
                            inView:(UIView*)view {
  UIView* hit_view = [view hitTest:p withEvent:NULL];
  ContentView* content_view = NULL;
  if ([hit_view isKindOfClass:[ContentView class]]) {
    content_view = (ContentView*)hit_view;
  }
  return content_view;
}

- (const EpisodeLayoutRow*)rowAtPoint:(const CGPoint&)p {
  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return NULL;
  }

  for (RowCacheMap::iterator iter(c->row_cache.begin());
       iter != c->row_cache.end();
       ++iter) {
    EpisodeLayoutRow* row = &iter->second;
    CGPoint tx_p = [row->view convertPoint:p fromView:horizontal_scroll_];
    if (CGRectContainsPoint(row->view.bounds, tx_p)) {
      return row;
    }
  }
  return NULL;
}

// Look backwards for the share activity row corresponding to the row
// at index.
- (int)findShareActivityForIndex:(int)index {
  if (index == -1) {
    return -1;
  }
  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return -1;
  }
  for (int i = index; i >= 0; --i) {
    const ViewpointSummaryMetadata::ActivityRow& activity_row = c->vsh->activities(i);
    if (activity_row.type() == ViewpointSummaryMetadata::ACTIVITY) {
      return i;
    } else if (activity_row.type() != ViewpointSummaryMetadata::PHOTOS) {
      return -1;
    }
  }
  return -1;
}

- (int)activityRowIndexAtPoint:(const CGPoint&)p {
  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return NULL;
  }
  const CGPoint tx_p = [c->scroll_view convertPoint:p fromView:horizontal_scroll_];
  const RowRange range = [self rowRange:c bounds:CGRectMake(0, tx_p.y, 0, 0)];
  if (range.first >= 0 && range.first < c->vsh->activities_size()) {
    return range.first;
  }
  return -1;
}

- (PhotoView*)photoAtPoint:(const CGPoint&)p
                     inRow:(const EpisodeLayoutRow&)row {
  for (int i = 0; i < row.view.photos->size(); ++i) {
    const CGPoint tx_p = [(*row.view.photos)[i] convertPoint:p fromView:horizontal_scroll_];
    if ((*row.view.photos)[i].selectable &&
        CGRectContainsPoint((*row.view.photos)[i].bounds, tx_p)) {
      return (*row.view.photos)[i];
    }
  }
  return NULL;
}

// Locates a photo in the view and returns its photo view, or NULL
// if not found.
- (PhotoView*)findPhotoView:(int64_t)photo_id {
  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return NULL;
  }

  for (RowCacheMap::iterator iter(c->row_cache.begin());
       iter != c->row_cache.end();
       ++iter) {
    EpisodeLayoutRow* row = &iter->second;
    for (int i = 0; i < row->view.photos->size(); ++i) {
      if ((*row->view.photos)[i].photoId == photo_id) {
        return (*row->view.photos)[i];
      }
    }
  }
  return NULL;
}

// Finds the photo within the current conversation.
- (bool)findPhoto:(int64_t)photo_id
            photo:(ViewpointSummaryMetadata::ActivityRow::Photo*)photo {
  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return NULL;
  }

  for (int i = 0; i < c->vsh->activities_size(); ++i) {
    const ViewpointSummaryMetadata::ActivityRow& row = c->vsh->activities(i);
    if (row.type() == ViewpointSummaryMetadata::PHOTOS ||
        row.type() == ViewpointSummaryMetadata::HEADER) {
      for (int j = 0; j < row.photos_size(); ++j) {
        if (row.photos(j).photo_id() == photo_id) {
          photo->CopyFrom(row.photos(j));
          return true;
        }
      }
    }
  }
  return false;
}

- (void)updateActionControls:(CachedConversation*)c
                 numSelected:(int)num_selected {
  NSString* message;
  if (edit_mode_ && editing_row_index_ != 0) {
    if (num_selected == 0) {
      message = @"Select Photos to Unshare or Forward";
    } else {
      message = Format("%d Photo%s Selected", num_selected, Pluralize(num_selected));
    }
    [state_->root_view_controller().statusBar
        setMessage:message
        activity:false
        type:STATUS_MESSAGE_UI];
  } else {
    [state_->root_view_controller().statusBar
        hideMessageType:STATUS_MESSAGE_UI
        minDisplayDuration:0.0];
  }
}

- (bool)activityAllPhotosSelected:(int)row_index {
  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return false;
  }
  const ViewpointSummaryMetadata::ActivityRow& row =
      c->vsh->activities(row_index);
  for (int i = 0; i < row.photos_size(); ++i) {
    const PhotoSelection key(row.photos(i).photo_id(), row.photos(i).episode_id());
    if (!ContainsKey(selection_, key)) {
      return false;
    }
  }
  return true;
}

- (int)activityCountPhotosSelected:(int)row_index {
  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return 0;
  }
  const ViewpointSummaryMetadata::ActivityRow& row =
      c->vsh->activities(row_index);
  int count = 0;
  for (int i = 0; i < row.photos_size(); ++i) {
    const PhotoSelection key(row.photos(i).photo_id(), row.photos(i).episode_id());
    if (ContainsKey(selection_, key)) {
      ++count;
    }
  }
  return count;
}

- (void)updateVisiblePhotoSelections:(CachedConversation*)c {
  for (RowCacheMap::iterator iter(c->row_cache.begin());
       iter != c->row_cache.end();
       ++iter) {
    EpisodeLayoutRow& row = iter->second;
    int select_count = 0;
    for (int i = 0; i < row.view.photos->size(); ++i) {
      PhotoView* p = (*row.view.photos)[i];
      const PhotoSelection key(p.photoId, p.episodeId);
      const bool selected = ContainsKey(selection_, key);
      p.selected = selected;
      if (selected) {
        ++select_count;
      }
    }

    if (row.view.editing) {
      row.view.selected = [self activityAllPhotosSelected:iter->first];
    }
  }
}

- (void)selectNone {
  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return;
  }

  selection_.clear();
  [self updateActionControls:c numSelected:selection_.size()];
  [self updateVisiblePhotoSelections:c];
}

- (void)togglePhoto:(PhotoView*)p {
  if (!p.selectable || !p.episodeId || !p.editing) {
    // This is a trapdoor photo or otherwise unselectable. Don't allow it to be
    // selected.
    return;
  }
  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return;
  }

  const PhotoSelection key(p.photoId, p.episodeId);
  const bool selected = !ContainsKey(selection_, key);
  if (selected) {
    selection_.insert(key);
  } else {
    selection_.erase(key);
  }

  [self updateActionControls:c numSelected:selection_.size()];
  [self updateVisiblePhotoSelections:c];
}

- (void)toggleActivityRow:(int)row_index {
  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return;
  }

  if (![self editingPhotosInRow:c row:row_index]) {
    return;
  }

  const ViewpointSummaryMetadata::ActivityRow& row = c->vsh->activities(row_index);
  vector<PhotoSelection> activity_photos;
  bool all_selected = true;

  for (int i = 0; i < row.photos_size(); ++i) {
    const PhotoSelection key(row.photos(i).photo_id(), row.photos(i).episode_id());
    if (!ContainsKey(selection_, key)) {
      all_selected = false;
    }
    activity_photos.push_back(key);
  }

  // Select all if any aren't yet selected; if all selected, select none.
  for (int i = 0; i < activity_photos.size(); ++i) {
    const PhotoSelection& key = activity_photos[i];
    if (all_selected) {
      selection_.erase(key);
    } else {
      selection_.insert(key);
    }
  }
  [self updateActionControls:c numSelected:selection_.size()];
  [self updateVisiblePhotoSelections:c];
}

- (void)selectActivityRow:(int)row_index
                 selected:(bool)selected {
  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return;
  }

  if (![self editingPhotosInRow:c row:row_index]) {
    return;
  }

  const ViewpointSummaryMetadata::ActivityRow& row = c->vsh->activities(row_index);

  for (int i = 0; i < row.photos_size(); ++i) {
    const PhotoSelection key(row.photos(i).photo_id(), row.photos(i).episode_id());
    if (selected) {
      selection_.erase(key);
    } else {
      selection_.insert(key);
    }
  }
  [self updateActionControls:c numSelected:selection_.size()];
  [self updateVisiblePhotoSelections:c];
}

- (void)setCurrentPhotos:(const DayTable::ViewpointSummaryHandle&)vsh {
  // Build a vector of the unique photos in the conversation.
  ControllerState controller_state =
      [state_->root_view_controller() photoLayoutController].controllerState;
  CurrentPhotos* cp = &controller_state.current_photos;
  cp->prev_callback = NULL;
  cp->next_callback = NULL;
  PhotoIdVec* v = &cp->photo_ids;
  v->clear();

  // Add cover photo to iteration. Because the cover photo can be
  // duplicated if the activity from which it was shared is not the
  // first, we check below to ensure we don't show the same photo twice.
  if (vsh->has_cover_photo()) {
    v->push_back(std::make_pair(vsh->cover_photo().photo_id(),
                                vsh->cover_photo().episode_id()));
  }

  // Get a vector of all photos using PHOTOS activity rows, which yield
  // a unique set of all photos displayed in the conversation besides the
  // cover photo.
  for (int i = 0; i < vsh->activities_size(); ++i) {
    const ViewpointSummaryMetadata::ActivityRow& row = vsh->activities(i);
    if (row.type() == ViewpointSummaryMetadata::PHOTOS) {
      for (int j = 0; j < row.photos_size(); ++j) {
        if (row.photos(j).photo_id() != vsh->cover_photo().photo_id()) {
          v->push_back(std::make_pair(row.photos(j).photo_id(), row.photos(j).episode_id()));
        }
      }
    }
  }

  // Setup refresh callback to re-load the viewpoint summary.
  const int64_t viewpoint_id = vsh->viewpoint_id();
  cp->refresh_callback = ^{
    // Take new snapshot.
    DayTable::SnapshotHandle new_snapshot = state_->day_table()->GetSnapshot(NULL);
    DayTable::ViewpointSummaryHandle new_vsh = new_snapshot->LoadViewpointSummary(viewpoint_id);
    [self setCurrentPhotos:new_vsh];
  };

  [state_->root_view_controller() photoLayoutController].controllerState = controller_state;
}

- (void)handleSingleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  if (browsing_) {
    [self stopBrowsing];
    return;
  }
  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return;
  }
  const CGPoint p = [recognizer locationInView:horizontal_scroll_];

  // Check for taps on header first.
  ConversationHeaderRowView* header = [self getHeaderRowView:c];
  if (header.editing &&
      [header maybeStopEditing:[recognizer locationInView:header]]) {
    return;
  }
  CGPoint tx_p = [c->scroll_view convertPoint:p fromView:horizontal_scroll_];
  UIView* v = [c->scroll_view hitTest:tx_p withEvent:NULL];
  PhotoView* pv = NULL;
  if (![v isKindOfClass:[PhotoView class]]) {
    if (!edit_mode_ && v.tag == kConversationFollowersTag) {
      show_all_followers_ = !show_all_followers_;
      header.showAllFollowers = show_all_followers_;
    }
    if (!edit_mode_) {
      return;
    }
  } else {
    pv = (PhotoView*)v;
  }

  if (edit_mode_) {
    if (pv) {
      [self togglePhoto:pv];
    } else {
      [self toggleActivityRow:[self activityRowIndexAtPoint:p]];
    }
  } else if (pv) {
    CachedConversation* const c = self.currentConversation;
    if (!c) {
      return;
    }
    [self setCurrentPhotos:c->vsh];
    ControllerState new_controller_state =
        [state_->root_view_controller() photoLayoutController].controllerState;
    new_controller_state.current_photo = pv;
    new_controller_state.current_viewpoint = c->vh->id().local_id();
    [state_->root_view_controller() showPhoto:ControllerTransition(new_controller_state)];
  }
}

- (void)handleLongPress:(UILongPressGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateBegan) {
    return;
  }
  if (edit_mode_ || add_photos_) {
    return;
  }
  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return;
  }
  const CGPoint p = [recognizer locationInView:horizontal_scroll_];
  CGPoint tx_p = [c->scroll_view convertPoint:p fromView:horizontal_scroll_];
  UIView* v = [c->scroll_view hitTest:tx_p withEvent:NULL];
  if (![v isKindOfClass:[PhotoView class]]) {
    return;
  }
  PhotoView* pv = (PhotoView*)v;
  [self replyToPhoto:pv];
}

- (void)replyToPhoto:(PhotoView*)pv {
  // Convert the photo view's frame from the conversation coordinate
  // system to the input view's coordinate system.
  CGRect f = [convo_navbar_ convertRect:pv.frame fromView:pv.superview];

  PhotoView* reply_to = [[PhotoView alloc] initWithState:state_];
  reply_to.frame = f;
  reply_to.aspectRatio = pv.aspectRatio;
  reply_to.episodeId = pv.episodeId;
  reply_to.photoId = pv.photoId;
  reply_to.image = pv.image;
  reply_to.loadSize = pv.loadSize;

  // LOG("reply to photo %d", pv.photoId);
  convo_navbar_.replyToPhoto = reply_to;
  [convo_navbar_ becomeFirstResponder];
}

- (void)handleSwipeLeft:(UISwipeGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  if (edit_mode_) {
    const CGPoint p = [recognizer locationInView:horizontal_scroll_];
    const int row_index = [self findShareActivityForIndex:[self activityRowIndexAtPoint:p]];
    if (row_index != -1) {
      [self selectActivityRow:row_index selected:true];
    }
  }
}

- (void)handleSwipeRight:(UISwipeGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  if (edit_mode_) {
    const CGPoint p = [recognizer locationInView:horizontal_scroll_];
    const int row_index = [self findShareActivityForIndex:[self activityRowIndexAtPoint:p]];
    if (row_index != -1) {
      [self selectActivityRow:row_index selected:false];
    }
  }
}

- (void)waitThumbnailsLocked:(CachedConversation*)c
                    rowRange:(const RowRange&)v
                       delay:(WallTime)delay {
  vector<PhotoView*> loading;
  for (RowCacheMap::iterator iter(c->row_cache.begin());
       iter != c->row_cache.end();
       ++iter) {
    EpisodeLayoutRow& row = iter->second;
    if (iter->first < v.first || iter->first > v.second) {
      continue;
    }
    for (int i = 0; i < row.view.photos->size(); ++i) {
      PhotoView* p = (*row.view.photos)[i];
      if (!p.image) {
        loading.push_back(p);
      }
    }
  }

  if (browsing_) {
    for (int i = 0; i < c->browsing_row.view.photos->size(); ++i) {
      PhotoView* p = (*c->browsing_row.view.photos)[i];
      if (!p.image) {
        if (!p.thumbnail.get()) {
          state_->photo_loader()->LoadThumbnailLocked(p);
        }
      }
      loading.push_back(p);
    }
  }

  if (loading.empty()) {
    return;
  }

  state_->photo_loader()->WaitThumbnailsLocked(loading, delay);
}

- (void)showRowThumbnailsLocked:(CachedConversation*)c
                       rowIndex:(int)row_index {
  EpisodeLayoutRow& row = c->row_cache[row_index];

  for (int j = 0; j < row.view.photos->size(); ++j) {
    PhotoView* p = (*row.view.photos)[j];

    const PhotoSelection key(p.photoId, p.episodeId);
    if (p.selectable) {
      // Disable the spongy animation for selection badge when showing
      // the row (e.g. not as a result of a user-initiated action).
      ScopedDisableUIViewAnimations disable_animations;
      p.selected = ContainsKey(selection_, key) ? YES : NO;
    }

    DCHECK_EQ(p.layer.cornerRadius, 0);
    // No parallax for cover photo.
    if (row_index != 0) {
      // TODO(pmattis): Share this code with
      // {Conversation,Summary}LayoutController.
      const float y1 = -p.frame.size.height;
      const float y2 = c->scroll_view.boundsHeight;
      float t = [self.view convertPoint:p.frame.origin
                               fromView:p.superview].y;
      // Vary the position between 0.25 at the top of the screen and 0.5 at
      // the bottom of the screen.
      t = LinearInterp<float>(t, y1, y2, 0.25, 0.5);
      p.position = CGPointMake(0.5, t);
    }

    if (p.image || p.thumbnail.get()) {
      // Image/thumbnail is already, or currently being, loaded.
      continue;
    }

    // LOG("  %d,%d: loading %d", row_index, j, p.photoId);
    state_->photo_loader()->LoadThumbnailLocked(p);
  }
}

- (void)updateConversationPositions:(CachedConversation*)c {
  c->vsh->UpdateRowPositions();
  [self initConversationSize:c];
  [self scrollViewDidScroll:c->scroll_view];
  [c->viewfinder invalidate:c->scroll_view.contentOffsetY];

  for (RowCacheMap::iterator iter(c->row_cache.begin());
       iter != c->row_cache.end();
       ++iter) {
    EpisodeLayoutRow* const row = &iter->second;
    CGRect f = row->view.frame;
    const ViewpointSummaryMetadata::ActivityRow& activity_row =
        c->vsh->activities(iter->first);
    f.origin.y = activity_row.position();
    f.size.height = activity_row.height();
    row->view.frame = f;
    [row->view layoutIfNeeded];
  }
  if (c->bottom_row) {
    c->bottom_row.frameTop = c->vsh->total_height();
  }
}

- (void)initConversationSize:(CachedConversation*)c {
  c->scroll_view.contentSize = CGSizeMake(
      self.view.boundsWidth, [self cardHeight:c]);
}

- (void)showConversation:(int)index {
  CachedConversation* const c = &conversation_cache_[index];
  if (c->scroll_view) {
    // Conversation already visible.
    return;
  }

  const int64_t viewpoint_id = [self getViewpointId:index];
  c->vsh = snapshot_->LoadViewpointSummary(viewpoint_id);
  c->vh = state_->viewpoint_table()->LoadViewpoint(viewpoint_id, snapshot_->db());
  c->vsh->UpdateRowHeights(c->vh);
  c->vsh->UpdateRowPositions();

  c->content_view = [UIView new];
  c->content_view.autoresizesSubviews = YES;
  // AddRoundedCorners(c->content_view);
  c->content_view.frame = [self conversationBounds:index];
  [horizontal_scroll_ addSubview:c->content_view];

  c->scroll_view = [ConversationScrollView new];
  c->scroll_view.alwaysBounceVertical = YES;
  c->scroll_view.autoresizesSubviews = YES;
  c->scroll_view.backgroundColor = kConversationBackgroundColor;
  c->scroll_view.canCancelContentTouches = YES;
  c->scroll_view.frame = c->content_view.bounds;
  c->scroll_view.tag = index;
  c->scroll_view.showsVerticalScrollIndicator = YES;
  c->scroll_view.scrollsToTop = YES;
  [c->content_view addSubview:c->scroll_view];

  // Adjust inset to account for input view, which may be active.
  [self adjustScroll:c scrollToBottom:false];

  // Add the viewfinder after (on top of) everything else in the scroll view.
  c->viewfinder = [[ViewfinderTool alloc] initWithEnv:self appState:state_];
  c->viewfinder.frame = c->scroll_view.bounds;
  c->viewfinder.tag = index;
  c->viewfinder.userInteractionEnabled = browsing_ ? NO : YES;
  [c->viewfinder addGestureRecognizers:c->scroll_view];
  [c->scroll_view addSubview:c->viewfinder];

  // Add the browsing trapdoor.
  SummaryRow row;
  if (snapshot_->conversations()->GetSummaryRow(index, &row)) {
    EpisodeLayoutRow* browsing_row = &c->browsing_row;
    TrapdoorHandle trh = snapshot_->LoadTrapdoor(row.identifier());
    InitBrowsingCard(
        state_, browsing_row, trh, c->vh, row.weight(), self.view.frameWidth);

    // Add text layer.
    const float left_margin =
        trh->has_cover_photo() ? kBrowsingTextWithCoverPhotoLeftMargin : kBrowsingTextLeftMargin;
    const float max_width =
        browsing_row->view.boundsWidth - kBrowsingTextLeftMargin - left_margin;
    browsing_row->view.textLayer.maxWidth = max_width;
    browsing_row->view.textLayer.transition = 0;
    browsing_row->view.textLayer.frame =
        CGRectMake(left_margin, kBrowsingTextTopMargin, max_width, 0);

    // Enable rasterization so that CoreAnimation properly antialiases the
    // browsing row when it is being shown/hidden.
    browsing_row->view.layer.rasterizationScale = [UIScreen mainScreen].scale;
    browsing_row->view.layer.shouldRasterize = YES;
    browsing_row->view.hidden = YES;
    browsing_row->view.frameTop = toolbar_.frameBottom + 4;
    browsing_row->view.layer.cornerRadius = 5;

    [self.view addSubview:browsing_row->view];
  }

  [self initConversationSize:c];

  // Add negative corners to conversation scroll view.
  c->bottom_row = [UIView new];
  c->bottom_row.frameTop = c->vsh->total_height();
  c->bottom_row.frameWidth = c->scroll_view.frameWidth;
  [c->scroll_view addSubview:c->bottom_row];

  UIImageView* ll_corner = [[UIImageView alloc] initWithImage:kConvoNegativeCornerLL];
  ll_corner.frameLeft = 8;
  ll_corner.frameBottom = 0;
  ll_corner.layer.zPosition = 1;
  [c->bottom_row addSubview:ll_corner];

  UIImageView* lr_corner = [[UIImageView alloc] initWithImage:kConvoNegativeCornerLR];
  lr_corner.frameRight = c->scroll_view.frameWidth - 8;
  lr_corner.frameBottom = 0;
  lr_corner.layer.zPosition = 1;
  [c->bottom_row addSubview:lr_corner];

  // Add browsing overlay after content size is set, as content size
  // is used to set overlay frame size.
  c->browsing_overlay = MakeBrowsingOverlay(c->scroll_view);

  // Make sure content offset does not exceed max. This can occasionally
  // happen if at the end of a conversation at the point that someone
  // unshares content.
  c->scroll_view.contentOffsetY =
      std::min(state_->viewpoint_table()->GetScrollOffset(viewpoint_id),
               c->scroll_view.contentOffsetMaxY);
  [c->viewfinder initialize:c->scroll_view.contentOffsetY];

  // If there is unviewed or pending content, we're meant to scroll to
  // the first row that's unviewed/pending.
  float scroll_to_y = -1;
  if (c->vsh->has_scroll_to_row()) {
    const ViewpointSummaryMetadata::ActivityRow& row =
        c->vsh->activities(c->vsh->scroll_to_row());
    ActivityHandle ah = state_->activity_table()->LoadActivity(row.activity_id(), state_->db());
    if (ah.get() && !ah->has_viewed_timestamp() && ah->update_seq() > c->vh->viewed_seq()) {
      // Make sure to offset by the toolbar's frame bottom so that no
      // part of the unviewed row is obscured.
      scroll_to_y = row.position() + toolbar_.frameBottom;
    }
  }

  // The computation for "close enough to scroll" is based on how much
  // unviewed/pending content has been added to the conversation (total
  // height - scroll_to_y) + the height of the comment input text box.
  // If current scroll position is less than that far off from the max
  // scroll position, it means the previous scroll was within the height
  // of the comment input from the bottom. We scroll in this case.
  const bool close_enough_to_scroll =
      scroll_to_y == -1 ? false :
      (c->scroll_view.contentOffsetMaxY - c->scroll_view.contentOffsetY) <
      (convo_navbar_.frameHeight + ([self cardHeight:c] - scroll_to_y));
  bool should_scroll = !rebuilding_ || close_enough_to_scroll;

  if (viewpoint_id == controller_state_.current_viewpoint) {
    // If the current viewpoint has pending content, scroll to bottom.
    // Note that we only do this for non-provisional viewpoints (e.g.
    // when we're not in 'compose' mode).
    if (controller_state_.pending_viewpoint && !c->vh->provisional()) {
      should_scroll = true;
      if (scroll_to_y == -1) {
        scroll_to_y = c->scroll_view.contentOffsetMaxY;
      }
    }
    // Clear pending flag so we don't scroll again on a follow-on rebuild.
    controller_state_.pending_viewpoint = false;
  }
  //  LOG("content offset %f, max: %f, scroll_to_y: %f, close_enough: %d, should_scroll: %d",
  //      c->scroll_view.contentOffsetY, c->scroll_view.contentOffsetMaxY,
  //      scroll_to_y, close_enough_to_scroll, should_scroll);

  // TODO(spencer): revisit this--it's pretty clunky.
  bool update_viewed_seq = true;
  if (scroll_to_y != -1) {
    scroll_to_y = std::min(scroll_to_y, c->scroll_view.contentOffsetMaxY);
    if (self.visible) {
      // The conversation layout controller is already visible. We
      // want to animate the "scroll_to_y" parameter, but dispatch it
      // to run after we've finished showing the conversation and
      // resetting the old scroll state.
      if (should_scroll) {
        UIScrollView* sv = c->scroll_view;
        // Wait for the block to run to update the viewed sequence number.
        update_viewed_seq = false;
        // Need to run the animation after stack unwinds as we're inside a CATransaction.
        dispatch_after_main(0, ^{
            [sv setContentOffset:CGPointMake(sv.contentOffsetX, scroll_to_y) animated:YES];
            // Set the viewed sequence number for visible conversation.
            state_->viewpoint_table()->UpdateViewedSeq(viewpoint_id);
          });
      } else if (c->scroll_view.contentOffsetY != c->scroll_view.contentOffsetMaxY) {
        // Don't scroll; Change the comment input background color to indicate
        // the presence of new content.
        dispatch_after_main(0, ^{
            [convo_navbar_ showNotificationGlow];
          });
      }
    } else {
      // Scroll the conversation to the correct position immediately so that
      // the subsequent call to showConversationThumbnailsLocked will load the
      // correct thumbnails.
      c->scroll_view.contentOffsetY = scroll_to_y;
    }
  } else if (controller_state_.current_photo) {
    // Scroll to first instance of the current photo. However, because
    // more than a single instance of an image may be visible in a
    // conversation, don't scroll if the photo is already
    // visible. This avoids having the "back" button from the photo
    // layout controller scroll to an earlier version of the photo.
    const PhotoView* photo = controller_state_.current_photo;
    CGRect scroll_to_f;
    bool found = false;
    for (int i = 0; i < c->vsh->activities_size(); ++i) {
      const ViewpointSummaryMetadata::ActivityRow& row = c->vsh->activities(i);
      if (row.type() != ViewpointSummaryMetadata::HEADER &&
          row.type() != ViewpointSummaryMetadata::PHOTOS) {
        continue;
      }
      for (int j = 0; j < row.photos_size(); ++j) {
        if (row.photos(j).photo_id() == photo.photoId) {
          CGRect f = CGRectMake(0, row.position(), c->scroll_view.boundsWidth, row.height());
          if (!found || CGRectContainsRect(c->scroll_view.bounds, f)) {
            scroll_to_f = f;
            found = true;
          }
        }
      }
    }
    if (found) {
      [c->scroll_view scrollRectToVisible:scroll_to_f animated:NO];
    }
  }

  // Update the viewed sequence number.
  if (update_viewed_seq) {
    state_->viewpoint_table()->UpdateViewedSeq(viewpoint_id);
  }

  // Ensure the header row is cached.
  [self ensureRow:c rowIndex:0];
  c->row_cache[0].pinned = true;
  [self getHeaderRowView:c].showAllFollowers = show_all_followers_;

  c->scroll_view.delegate = self;
  // The current method likely was called from within
  // scrollViewDidScroll, but it's not actually a problem because
  // the original invocation was made on behalf of the horizontal
  // scroll view and this is the conversation's scroll view.
  [self scrollViewDidScroll:c->scroll_view];

  // LOG("showing conversation %d, height %f", viewpoint_id, y);
}

- (void)showRow:(CachedConversation*)c
       rowIndex:(int)row_index {
  DCHECK_GE(row_index, 0);
  DCHECK_LT(row_index, c->vsh->activities_size());
  if (row_index < 0 || row_index > c->vsh->activities_size()) {
    return;
  }

  const float row_width = self.view.boundsWidth;
  const ViewpointSummaryMetadata::ActivityRow& row = c->vsh->activities(row_index);
  ActivityHandle ah;

  EpisodeLayoutRow* activity_row = &c->row_cache[row_index];
  activity_row->timestamp = row.timestamp();
  activity_row->type = row.type();
  int64_t reply_to_photo_id = -1;
  int64_t reply_to_episode_id = -1;

  // If the row is empty (denoted by a row height of 0), nothing else
  // to do here (and we definitely don't want the activity to be marked
  // as viewed, so return. We create an empty row view so code expecting
  // an accessible view for the row index is satisfied.
  if (row.height() == 0) {
    activity_row->view = [RowView new];
    activity_row->view.index = row_index;
    return;
  }

  if (row.has_activity_id()) {
    ah = state_->activity_table()->LoadActivity(row.activity_id(), snapshot_->db());

    if (row.update_seq() > c->vh->viewed_seq()) {
      // Can't update "ah" which is from a snapshot db, so fetch
      // current value from database and set the viewed timestamp to
      // the current time.
      ActivityHandle update_ah = state_->activity_table()->LoadActivity(
          ah->activity_id().local_id(), state_->db());
      if (!update_ah->has_viewed_timestamp()) {
        update_ah->Lock();
        update_ah->set_viewed_timestamp(state_->WallTime_Now());
        update_ah->SaveAndUnlock(state_->db());
      }
    }
  }

  switch (row.type()) {
    case ViewpointSummaryMetadata::HEADER: {
      InitConversationHeader(
          state_, activity_row, c->vh->id().local_id(),
          c->vsh->cover_photo().photo_id(),
          c->vsh->cover_photo().episode_id(),
          c->vsh->cover_photo().aspect_ratio(), row_width);
      activity_row->view.frameTop = row.position();
      __weak ConversationLayoutController* weak_self = self;
      ((ConversationHeaderRowView*)activity_row->view).editCoverPhotoCallback->Add(^{
          ConversationHeaderRowView* header = [weak_self getHeaderRowView:c];
          [weak_self showAddPhotosFromView:header.coverPhotoCTA
                       coverPhotoSelection:true];
        });
      break;
    }

    case ViewpointSummaryMetadata::UPDATE:
      InitConversationUpdate(
          state_, activity_row, c->vh, ah,
          static_cast<ActivityUpdateType>(row.thread_type()),
          row.row_count(), row_width, snapshot_->db());
      activity_row->view.frameTop = row.position();
      break;

    case ViewpointSummaryMetadata::REPLY_ACTIVITY:
      DCHECK_EQ(row.photos_size(), 1);
      if (row.photos_size() > 0 && row.photos(0).episode_id() != 0) {
        reply_to_photo_id = row.photos(0).photo_id();
        reply_to_episode_id = row.photos(0).episode_id();
      }
      // Fall through...

    case ViewpointSummaryMetadata::ACTIVITY:
      InitConversationActivity(
          state_, activity_row, c->vh, ah, &row, reply_to_photo_id,
          reply_to_episode_id, static_cast<ActivityThreadType>(row.thread_type()),
          row.row_count(), row_width, snapshot_->db());
      activity_row->view.frameTop = row.position();
      break;

    case ViewpointSummaryMetadata::PHOTOS: {
      // This map prevents us busily reloading episodes, as we're drawing
      // from a snapshot of the database.
      std::unordered_map<int64_t, EpisodeHandle> unique_episodes;
      vector<PhotoHandle> photos;
      vector<EpisodeHandle> episodes;
      for (int i = 0; i < row.photos_size(); ++i) {
        const PhotoHandle ph = state_->photo_table()->LoadPhoto(
            row.photos(i).photo_id(), snapshot_->db());
        const int64_t episode_id = row.photos(i).episode_id();
        if (!ContainsKey(unique_episodes, episode_id)) {
          unique_episodes[episode_id] =
              state_->episode_table()->LoadEpisode(episode_id, snapshot_->db());
        }
        const EpisodeHandle eh = unique_episodes[episode_id];
        DCHECK(ph.get());
        DCHECK(eh.get());
        photos.push_back(ph);
        episodes.push_back(eh);
      }
      InitShareActivityPhotosRow(
          state_, activity_row, CONVERSATION_LAYOUT, photos, episodes,
          row_width, row.position(), snapshot_->db());
      break;
    }

    default:
      LOG("unrecognized row type %d", row.type());
  }

  activity_row->view.env = self;
  activity_row->view.index = row_index;

  if (activity_row->view.textLayer) {
    activity_row->view.textLayer.maxWidth = [self rowTextMaxWidth:row];
    activity_row->view.textLayer.transition = 0;
    const CGPoint offset = [self rowTextOffset:row];
    activity_row->view.textLayer.frame =
        CGRectMake(offset.x, offset.y, self.view.frameWidth - offset.x * 2, 0);
    if (viewfinder_active_) {
      [activity_row->view.textLayer removeFromSuperlayer];
    }
  }

  // If the row height is different than expected, invalidate the
  // activity. People's names change, contacts move from prospective
  // to registered, etc.
  if (activity_row->view.frameHeight != row.height()) {
    LOG("activity row frame height mismatch: %.1f != %.1f for %s",
        activity_row->view.frameHeight, row.height(), *ah);
    DBHandle updates = state_->NewDBTransaction();
    state_->day_table()->InvalidateActivity(ah, updates);
    updates->Commit();
  }

  if (edit_mode_) {
    [self editModeInitRow:c row:activity_row rowIndex:row_index];
  }

  {
    // Insert row views such that earlier rows are "below" later rows.
    const EpisodeLayoutRow* next_row = NULL;
    int next_index = std::numeric_limits<int>::max();
    for (RowCacheMap::iterator iter(c->row_cache.begin());
         iter != c->row_cache.end();
         ++iter) {
      if (iter->first > row_index && iter->first < next_index) {
        next_index = iter->first;
        next_row = &iter->second;
      }
    }
    UIView* next_view = next_row ? next_row->view : c->viewfinder;
    [c->scroll_view insertSubview:activity_row->view belowSubview:next_view];
  }
}

- (void)ensureRow:(CachedConversation*)c
         rowIndex:(int)row_index {
  if (ContainsKey(c->row_cache, row_index)) {
    return;
  }
  // Disable UIView animations when we're showing row. This is necessary if the
  // row is being shown within an animation block. We don't want to animate the
  // position of the row frame.
  const ScopedDisableUIViewAnimations disable_animations;
  [self showRow:c rowIndex:row_index];
}

- (void)hideConversation:(int)index {
  // LOG("  %d: hiding conversation", index);
  CachedConversation* const c = &conversation_cache_[index];
  DCHECK(c);
  c->scroll_view.delegate = NULL;
  [c->viewfinder removeGestureRecognizers:c->scroll_view];
  [c->content_view removeFromSuperview];
  [c->browsing_row.view removeFromSuperview];

  // Update scroll offset when removing conversation.
  state_->viewpoint_table()->SetScrollOffset(
      c->vh->id().local_id(), std::max<float>(0, c->scroll_view.contentOffsetY));
}

- (void)hideRows:(CachedConversation*)c
        rowRange:(const RowRange&)v {
  // Hide any rows that fall outside of the row range.
  vector<int> hidden_rows;
  for (RowCacheMap::iterator iter(c->row_cache.begin());
       iter != c->row_cache.end();
       ++iter) {
    EpisodeLayoutRow& row = iter->second;
    if ((iter->first >= v.first && iter->first <= v.second) ||
        row.pinned) {
      continue;
    }
    if (row.view.modified) {
      // Do not hide modified rows while in editing mode.
      continue;
    }
    // LOG("%s: hiding row %d", c->vh->id(), iter->first);
    hidden_rows.push_back(iter->first);
    [row.view removeFromSuperview];
  }
  for (int i = 0; i < hidden_rows.size(); ++i) {
    c->row_cache.erase(hidden_rows[i]);
  }
}

- (void)showRows:(CachedConversation*)c
        rowRange:(const RowRange&)v {
  MutexLock l(state_->photo_loader()->mutex());

  // Loop over the row range, showing rows as necessary.
  for (int i = v.first; i <= v.second; ++i) {
    [self ensureRow:c rowIndex:i];
    // Always invoke this method to ensure parallax is adjusted on scrolling.
    [self showRowThumbnailsLocked:c rowIndex:i];
  }

  [self waitThumbnailsLocked:c rowRange:v delay:0.005];
}

- (void)hideConversations:(const ConversationRange&)v {
  // Hide any conversations that fall outside of the conversation range.
  vector<int> hidden_conversations;
  for (ConversationCacheMap::iterator iter(conversation_cache_.begin());
       iter != conversation_cache_.end();
       ++iter) {
    const int index = iter->first;
    if (index >= v.first && index <= v.second) {
      continue;
    }
    hidden_conversations.push_back(index);
    [self hideConversation:index];
  }
  for (int i = 0; i < hidden_conversations.size(); ++i) {
    conversation_cache_.erase(hidden_conversations[i]);
  }
}

- (void)showConversations:(const ConversationRange&)v {
  // Loop over the conversation range, showing conversations as necessary.
  for (int i = v.first; i <= v.second; ++i) {
    [self showConversation:i];
  }
}

- (void)pinConversationViewfinder:(CachedConversation*)c {
  c->viewfinder.frame = CGRectOffset(
      c->viewfinder.bounds, 0, c->scroll_view.contentOffsetY);
}

- (void)pinConversationCoverPhoto:(CachedConversation*)c {
  // The HEADER row is always at row index 0.
  EpisodeLayoutRow* const row = FindPtrOrNull(&c->row_cache, 0);
  if (!row || row->type != ViewpointSummaryMetadata::HEADER) {
    return;
  }

  // Pin the cover photo to the top of the scroll view.
  if (!row->view.photos->empty()) {
    PhotoView* p = (*row->view.photos)[0];
    p.frameTop = c->scroll_view.contentOffsetY;
    const float scroll_ratio =
        std::min<float>(p.frameHeight, std::max<float>(0, c->scroll_view.contentOffsetY)) / p.frameHeight;
    p.imageView.alpha = 0.33 + 0.67 * (1 - scroll_ratio);
    p.editBadge.alpha = 1 - scroll_ratio;
    ConversationHeaderRowView* header = [self getHeaderRowView:c];
    header.editCoverPhotoButton.alpha = edit_mode_ ? 0 : 1 - scroll_ratio;
  }
}

- (float)loadPhotoPriority:(PhotoView*)p {
  if ([p isAppropriatelyScaled]) {
    return 0;
  }

  // Prioritize loading of the photo with the most screen overlap.
  const CGRect f = [horizontal_scroll_ convertRect:p.frame
                                          fromView:p.superview];
  const float visible_fraction = VisibleFraction(f, self.visibleBounds);
  if (visible_fraction > 0) {
    // The photo is visible on the screen, prioritize loading over off-screen
    // photos.
    return 1 + visible_fraction;
  }
  const float cache_fraction = VisibleFraction(f, self.cacheBounds);
  return cache_fraction;
}

- (void)photoLoadPriorityQueue:(vector<PhotoView*>*)q {
  // Loop over the cached photos and calculate a load priority for each photo.
  typedef std::pair<float, PhotoView*> PhotoPair;
  vector<PhotoPair> priority_queue;

  for (ConversationCacheMap::iterator iter(conversation_cache_.begin());
       iter != conversation_cache_.end();
       ++iter) {
    CachedConversation* c = &iter->second;
    for (RowCacheMap::iterator iter(c->row_cache.begin());
         iter != c->row_cache.end();
         ++iter) {
      EpisodeLayoutRow& row = iter->second;
      for (int j = 0; j < row.view.photos->size(); ++j) {
        PhotoView* p = (*row.view.photos)[j];
        const float priority = [self loadPhotoPriority:p];
        if (priority > 0) {
          priority_queue.push_back(std::make_pair(priority, p));
        }
      }
    }

    if (browsing_) {
      for (int i = 0; i < c->browsing_row.view.photos->size(); ++i) {
        PhotoView* p = (*c->browsing_row.view.photos)[i];
        const float priority = [self loadPhotoPriority:p];
        if (priority > 0) {
          priority_queue.push_back(std::make_pair(priority, p));
        }
      }
    }
  }

  if (priority_queue.empty()) {
    return;
  }

  // Sort the photos by priority.
  std::sort(priority_queue.begin(), priority_queue.end(),
            std::greater<PhotoPair>());

  q->resize(priority_queue.size());
  for (int i = 0; i < priority_queue.size(); ++i) {
    (*q)[i] = priority_queue[i].second;
  }
}

- (bool)isModal {
  CachedConversation* const c = self.currentConversation;
  return (horizontal_scroll_.dragging ||
          horizontal_scroll_.decelerating ||
          (c && (c->scroll_view.scrollingAnimation ||
                 c->scroll_view.contentInset.top > 0)) ||
          viewfinder_active_ ||
          add_photos_ ||
          browsing_ ||
          showing_alert_ ||
          !state_->app_active());
}

- (void)maybeRebuildConversations {
  dispatch_after_main(0, ^{
      if (self.visible) {
        [self rebuildConversations];
      }
    });
}

- (void)rebuildConversations {
  if (!need_rebuild_) {
    return;
  }
  if (self.isModal) {
    return;
  }
  CachedConversation* const c = self.currentConversation;
  if (c) {
    if (c->scroll_view.dragging ||
        c->scroll_view.decelerating) {
      return;
    }
    if (edit_mode_) {
      // Allow rebuilding provisional conversations in edit mode because such
      // conversations can only have modifications that were created by the
      // ConversationLayoutController.
      if (!c->vh->provisional()) {
        return;
      }
      // Do not allow provisional conversations to be rebuilt if any
      // row is being edited and has focus (focus means either
      // keyboard is up or some other UI element which would be
      // destructively reset if we rebuild; e.g. the dropdown
      // suggestions menu in the header's followers field view).
      for (RowCacheMap::iterator iter(c->row_cache.begin());
           iter != c->row_cache.end();
           ++iter) {
        if (iter->second.view.hasFocus) {
          return;
        }
      }
    }
  }
  rebuilding_ = true;
  [self viewWillAppear:NO];
  rebuilding_ = false;
  if (snapshot_->conversations()->row_count() == 0) {
    // No conversations, pop back to our parent view.
    [self dismissSelf];
  }
}

- (bool)rebuildState {
  need_rebuild_ = false;

  const int old_epoch = day_table_epoch_;
  snapshot_ = state_->day_table()->GetSnapshot(&day_table_epoch_);
  if (old_epoch == day_table_epoch_) {
    return false;
  }

  // Store any photo views during rebuild so we don't needlessly recreate them.
  [self rebuildPhotoViewMap];
  [self clearConversationCache];

  if (network_paused_) {
    LOG("conversation: network still paused while rebuilding state; unpausing");
    [self resumeNetwork];
  }
   LOG("conversation: rebuild state: %d rows, %d height",
      snapshot_->conversations()->row_count(),
      snapshot_->conversations()->total_height());
  return true;
}

- (void)rebuildPhotoViewMap {
  // Rebuild the global photo map so it only contains photos that are currently
  // cached.
  BuildPhotoViewMap(state_->photo_view_map(), self.view);
}

- (void)clearConversationCache {
  MutexLock l(state_->photo_loader()->mutex());
  [self hideConversations:ConversationRange(-1, -1)];  // removes all
  DCHECK(conversation_cache_.empty());
}

- (void)showAddPhotosFromView:(UIView*)view
          coverPhotoSelection:(bool)cover_photo_selection {
  if (add_photos_) {
    return;
  }
  add_photos_ = [[PhotoPickerView alloc] initWithState:state_
                                  singlePhotoSelection:cover_photo_selection];
  add_photos_.hidden = YES;
  add_photos_.env = self;
  add_photos_.frame = self.view.bounds;

  CachedConversation* const c = self.currentConversation;
  if (!cover_photo_selection && c) {
    // Mark any existing photos as selected in the photo picker to
    // show what has already been shared into the conversation.
    PhotoSelectionSet selection;
    for (int i = 0; i < c->vsh->activities_size(); ++i) {
      const ViewpointSummaryMetadata::ActivityRow& row = c->vsh->activities(i);
      for (int j = 0; j < row.photos_size(); ++j) {
        // Note that we use parent_episode_id here instead of episode_id. The
        // selection returned from the add photos picker has episode ids
        // corresponding to episodes in the user's library, but once added to
        // the conversation a new episode id is generated. We want to specify
        // the original (parent) episode id in the selection.
        if (!row.photos(j).has_parent_episode_id()) {
          // Reply-to photos and cover photos will not have the parent episode
          // id set, but such photos will be mentioned elsewhere in the
          // activities.
          continue;
        }
        selection.insert(PhotoSelection(row.photos(j).photo_id(),
                                        row.photos(j).parent_episode_id()));
      }
    }

    // Disable the selected photos so that it is clear they are
    // already included, but can't be casually unshared directly
    // from this photo picker.
    vector<DisabledPhoto> disabled_photos;
    for (PhotoSelectionSet::iterator iter = selection.begin();
         iter != selection.end();
         ++iter) {
      disabled_photos.push_back(DisabledPhoto(iter->photo_id, true));
    }
    add_photos_.summary.disabledPhotos = disabled_photos;

    if (use_camera_) {
      // If use_camera_ is true, also include the photos which were just
      // taken (they're in controller_state.current_photos) as part of
      // existing selection.
      PhotoSelectionSet selected_photos = add_photos_.summary.selection;
      for (int i = 0; i < controller_state_.current_photos.photo_ids.size(); ++i) {
        selected_photos.insert(
            PhotoSelection(controller_state_.current_photos.photo_ids[i].first,
                           controller_state_.current_photos.photo_ids[i].second));
      }
      add_photos_.summary.selection = selected_photos;
    }
  }

  [UIView animateWithDuration:kDuration
                   animations:^{
      if (view) {
        const CGRect f = [view.superview convertRect:view.frame toView:self.view];
        [add_photos_ showFromRect:f];
      } else {
        [add_photos_ show];
      }
      [convo_navbar_ hide];
    }];
}

- (void)hideAddPhotos {
  if (!add_photos_) {
    return;
  }
  [UIView animateWithDuration:kDuration
                   animations:^{
      [add_photos_ hide:true];
      add_photos_ = NULL;
      [convo_navbar_ show];
      CachedConversation* c = self.currentConversation;
      if (c) {
        [self adjustScroll:c scrollToBottom:false];
      }
    }
                   completion:^(BOOL finished) {
      [self maybeRebuildConversations];
    }];
}

- (void)showConvoPicker {
  if (convo_picker_) {
    return;
  }
  convo_picker_ = [[ConversationPickerView alloc] initWithState:state_];
  convo_picker_.env = self;
  convo_picker_.frame = self.view.bounds;

  [UIView animateWithDuration:kDuration
                   animations:^{
      [convo_picker_ show];
      [convo_navbar_ hide];
    }];
}

- (void)hideConvoPicker {
  if (!convo_picker_) {
    return;
  }
  [UIView animateWithDuration:kDuration
                   animations:^{
      [convo_picker_ hide:true];
      convo_picker_ = NULL;
      [convo_navbar_ show];
    }];
}

- (void)dismissSelf {
  ControllerState pop_controller_state =
      [state_->root_view_controller() popControllerState];
  [state_->root_view_controller() dismissViewController:pop_controller_state];
}

- (void)toolbarDone {
  if (![self getHeaderRowView:self.currentConversation].canEndEditing) {
    return;
  }
  if (edit_mode_) {
    [self editModeEnd:true];
  }
  [self resetSteadyState];
}

- (void)toolbarInbox {
  if (IsIgnoringInteractionEvents()) {
    return;
  }
  [self dismissSelf];
}

- (void)toolbarCancel {
  CachedConversation* const c = self.currentConversation;
  if (c && c->vh->provisional()) {
    ConversationHeaderRowView* header = [self getHeaderRowView:c];
    if (header.editingTitle) {
      header.editing = false;
      [toolbar_ showStartConvoItems:true withTitle:[self title:c]];
      return;
    }
  }
  [self resetSteadyState];
}

- (void)toolbarEdit {
  CachedConversation* const c = self.currentConversation;
  if (!c || IsIgnoringInteractionEvents()) {
    return;
  }
  state_->analytics()->ConversationEditToggle();
  // TODO(spencer): need to revisit this. Clicking edit (instead of
  // the old navbar action mode) really should allow you to edit the
  // title and participants and shouldn't show this alert evert.
  if (!c->vsh->photo_count()) {
    [[[UIAlertView alloc]
       initWithTitle:@"No Photos In This Conversation!"
             message:@"Before you can share or export photos, there must be photos to share or export…"
            delegate:NULL
       cancelButtonTitle:@"OK"
       otherButtonTitles:NULL] show];
    return;
  }
  [self editModeBegin:self.currentConversation];
}

- (void)toolbarExit {
  CachedConversation* const c = self.currentConversation;
  if (!c || IsIgnoringInteractionEvents()) {
    return;
  }
  if (c->viewfinder.active) {
    [c->viewfinder close:true];
  }
}

- (void)resetSteadyState {
  CachedConversation* const c = self.currentConversation;

  horizontal_scroll_.scrollEnabled = YES;
  [UIView animateWithDuration:kDuration
                   animations:^{
      if (edit_mode_) {
        [self editModeEnd:false];
      }
      convo_navbar_.enabled = true;
      [convo_navbar_ show];
      [self adjustScroll:c scrollToBottom:false];
    }];

  if (c && c->vh->provisional()) {
    // TODO(peter): Actually delete the conversation. ViewpointTable::Remove()
    // only adds a removed label.
#ifndef KEEP_PROVISIONAL_CONVERSATIONS
    state_->viewpoint_table()->Remove(c->vh->id().local_id());
#endif  // !KEEP_PROVISIONAL_CONVERSATIONS
    [self dismissSelf];
    return;
  }

  [toolbar_ showConvoItems:true withTitle:[self title:c]];
  [self selectNone];
  [self resetConvoNavbar];

  [self maybeRebuildConversations];
}

- (bool)editingRow:(CachedConversation*)c
               row:(int)row_index {
  if (!edit_mode_) {
    return false;
  }
  if (c->vh->provisional() && (row_index != 0)) {
    // Only allow the header row to be edited in provisional conversations.
    return false;
  }
  if ((editing_row_index_ >= 0) && (editing_row_index_ != row_index)) {
    return false;
  }
  return true;
}

- (bool)editingPhotosInRow:(CachedConversation*)c
                       row:(int)row_index {
  if (![self editingRow:c row:row_index]) {
    return false;
  }
  if (c->vh->provisional()) {
    // Do not allow photos to be edited in provisional conversations.
    return false;
  }
  if (row_index == 0) {
    ConversationHeaderRowView* header = [self getHeaderRowView:c];
    if (header.editingTitle || header.editingFollowers) {
      return false;
    }
  }
  return true;
}

- (void)editModeInitRow:(CachedConversation*)c
                    row:(EpisodeLayoutRow*)row
               rowIndex:(int)row_index {
  const bool row_editing = [self editingRow:c row:row_index];
  const bool photo_editing = [self editingPhotosInRow:c row:row_index];

  row->view.editing = row_editing;
  if (row->view.editing) {
    row->view.selected = [self activityAllPhotosSelected:row_index];
  }

  const ViewpointSummaryMetadata::ActivityRow& activity_row =
      c->vsh->activities(row_index);
  if (activity_row.type() == ViewpointSummaryMetadata::HEADER ||
      activity_row.type() == ViewpointSummaryMetadata::PHOTOS) {
    for (int i = 0; i < row->view.photos->size(); ++i) {
      PhotoView* p = (*row->view.photos)[i];
      if (p.selectable && p.episodeId) {
        p.editing = photo_editing;
      }
    }
  }
}

- (void)editModeInitCachedRows:(CachedConversation*)c {
  for (RowCacheMap::iterator iter(c->row_cache.begin());
       iter != c->row_cache.end();
       ++iter) {
    [self editModeInitRow:c row:&iter->second rowIndex:iter->first];
  }
  [self scrollViewDidScroll:c->scroll_view];  // set cover photo badge alpha based on scroll
}

- (void)editModeBegin:(CachedConversation*)c {
  if (!edit_mode_) {
    edit_mode_ = true;
    [self adjustScroll:c scrollToBottom:false];
  }
  [self updateActionControls:c numSelected:selection_.size()];
  swipe_left_recognizer_.enabled = NO;
  swipe_right_recognizer_.enabled = NO;
  horizontal_scroll_.scrollEnabled = NO;

  ConversationHeaderRowView* header = [self getHeaderRowView:c];
  if (c->vh->provisional()) {
    if (header.editingTitle) {
      [toolbar_ showEditConvoItems:true withTitle:@"Add Title" withDoneEnabled:!header.emptyTitle];
      [convo_navbar_ hide];
    }
  } else if (editing_row_index_ == 0 /* header row */) {
    if (header.editingTitle) {
      [toolbar_ showEditConvoItems:true withTitle:@"Edit Title" withDoneEnabled:true];
    } else {
      [toolbar_ showEditConvoItems:true withTitle:@"Add People" withDoneEnabled:true];
    }
    [convo_navbar_ hide];
  } else {
    swipe_left_recognizer_.enabled = YES;
    swipe_right_recognizer_.enabled = YES;
    [toolbar_ showEditConvoPhotosItems:true];
    [convo_navbar_ showActionTray];
  }

  c->viewfinder.userInteractionEnabled = NO;
  [self editModeInitCachedRows:c];
}

- (void)editModeEnd:(bool)commit {
  edit_mode_ = false;
  editing_row_index_ = -1;

  [state_->root_view_controller().statusBar
      hideMessageType:STATUS_MESSAGE_UI
      minDisplayDuration:0.75];

  CachedConversation* const c = self.currentConversation;
  if (c) {
    c->viewfinder.userInteractionEnabled = YES;

    if (commit) {
      commit_transaction_ = state_->NewDBTransaction();
    }

    // This is more complicated than expected. The process of switching rows to
    // non-editing can cause the row_cache to change. For example, if the
    // keyboard is visible, switching the associated row to non-editing will
    // cause the keyboard to disappear which will adjust the scroll offsets and
    // cause scrollViewDidScroll to be called.
    vector<RowView*> row_views;
    for (RowCacheMap::iterator iter(c->row_cache.begin());
         iter != c->row_cache.end();
         ++iter) {
      row_views.push_back(iter->second.view);
    }

    for (int i = 0; i < row_views.size(); ++i) {
      RowView* view = row_views[i];
      for (int j = 0; j < view.photos->size(); ++j) {
        PhotoView* p = (*view.photos)[j];
        if (p.selectable && p.episodeId) {
          p.editing = false;
        }
      }
      if (commit) {
        [view commitEdits];
      }
      view.editing = false;

      if (view.index < c->vsh->activities_size()) {
        c->vsh->mutable_activities(view.index)->set_height(view.desiredFrameHeight);
      }
    }

    [UIView animateWithDuration:kDuration
                     animations:^{
        [self updateConversationPositions:c];
      }];

    if (commit) {
      // Always scroll to the top of a newly created conversation.
      if (c->vh->provisional()) {
        [c->scroll_view setContentOffset:CGPointMake(c->scroll_view.contentOffsetX, 0) animated:YES];
      }
      [self editModeFinishCommit:c];
    }

    horizontal_scroll_.scrollEnabled = c->vh->provisional() ? NO : YES;
  }

  [self hideAddPhotos];
  [self hideConvoPicker];

  [convo_navbar_ showMessageTray];
  swipe_left_recognizer_.enabled = NO;
  swipe_right_recognizer_.enabled = NO;
}

- (void)editModeCommitEdits:(CachedConversation*)c {
  commit_transaction_ = state_->NewDBTransaction();

  // Commit any edits without leaving editing mode.
  vector<RowView*> row_views;
  for (RowCacheMap::iterator iter(c->row_cache.begin());
       iter != c->row_cache.end();
       ++iter) {
    row_views.push_back(iter->second.view);
  }

  for (int i = 0; i < row_views.size(); ++i) {
    RowView* view = row_views[i];
    [view commitEdits];
  }

  commit_transaction_->Commit();
  commit_transaction_.reset();
}

- (void)editModeFinishCommit:(CachedConversation*)c {
  if (c->vh->provisional()) {
    state_->viewpoint_table()->CommitShareNew(
        c->vh->id().local_id(), commit_transaction_);
    // Note, clearing the provisional bit of c->vh isn't quite kosher as
    // the handle could potentially be shared elsewhere, but in practice it
    // isn't. We clear the provisional bit so that the code in
    // resetSteadyState does not pop us to the previous view controller.
    c->vh->clear_provisional();
  }

  commit_transaction_->Commit();
  commit_transaction_.reset();
}

- (ConversationHeaderRowView*)getHeaderRowView:(CachedConversation*)c {
  if (!c) {
    return NULL;
  }
  EpisodeLayoutRow* const header_row = FindPtrOrNull(&c->row_cache, 0);
  if (header_row &&
      header_row->type == ViewpointSummaryMetadata::HEADER &&
      [header_row->view isKindOfClass:[ConversationHeaderRowView class]]) {
    return (ConversationHeaderRowView*)header_row->view;
  }
  return NULL;
}

- (void)editModeStartEditingFollowers:(CachedConversation*)c {
  ConversationHeaderRowView* header_row_view = [self getHeaderRowView:c];
  if (header_row_view) {
    [header_row_view startEditingFollowers];
    if (!edit_mode_) {
      editing_row_index_ = 0;
      [self editModeBegin:c];
    }
  }
}

- (void)editModeStartEditingTitle:(CachedConversation*)c {
  ConversationHeaderRowView* header_row_view = [self getHeaderRowView:c];
  if (header_row_view) {
    [header_row_view startEditingTitle];
    if (!edit_mode_) {
      editing_row_index_ = 0;
      [self editModeBegin:c];
    }
  }
}

- (void)adjustScroll:(CachedConversation*)c
      scrollToBottom:(bool)scroll_to_bottom {
  // Adjust the scroll offset so that the photos/comments at the bottom of
  // the screen remain visible.
  // TODO(pmattis): Move this into a UIScrollView category.
  const float bottom = !edit_mode_ ?
                       convo_navbar_.contentInset :
                       std::max(keyboard_frame_.size.height, convo_navbar_.contentInset);
  const float max_offset =
      bottom + c->scroll_view.contentSize.height - c->scroll_view.frameHeight;
  const bool at_bottom = (c->scroll_view.contentOffsetY == max_offset);
  if (!scroll_to_bottom && at_bottom) {
    scroll_to_bottom = (bottom > c->scroll_view.contentInset.bottom);
  }
  if (edit_mode_ && keyboard_frame_.size.height > 0) {
    scroll_to_bottom = false;
  }
  c->scroll_view.contentInset = UIEdgeInsetsMake(0, 0, bottom, 0);

  // Adjust the visible area of the scroll view based on the toolbar
  // translucency and whether the keyboard is visible.
  UIEdgeInsets visible_insets = UIEdgeInsetsZero;
  visible_insets.top = toolbar_.frameBottom;
  visible_insets.bottom = keyboard_frame_.size.height;
  c->scroll_view.visibleInsets = visible_insets;

  if (scroll_to_bottom && !c->scroll_view.dragging) {
    // Scroll to the bottom of the conversation.
    const float y =
        std::max<float>(0, bottom + c->scroll_view.contentSize.height -
                        c->scroll_view.frameHeight);
    [c->scroll_view setContentOffset:CGPointMake(0, y) animated:YES];
  }
}

- (void)navbarMuteConvo:(UIView*)sender {
  CachedConversation* const c = self.currentConversation;
  if (!c || IsIgnoringInteractionEvents()) {
    return;
  }
  MuteConversations(state_, convo_navbar_.frame, self.view,
                    L(c->vh->id().local_id()), true, ^(bool finished) {
                      if (finished) {
                        CachedConversation* const c = self.currentConversation;
                        ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
                            c->vh->id().local_id(), state_->db());
                        [convo_navbar_ configureFromViewpoint:vh];
                      }
                    });
}

- (void)navbarRemoveConvo:(UIView*)sender {
  CachedConversation* const c = self.currentConversation;
  if (!c || IsIgnoringInteractionEvents()) {
    return;
  }
  RemoveConversations(state_, convo_navbar_.frame, self.view,
                      L(c->vh->id().local_id()), ^(bool finished) {
                        if (finished) {
                          ControllerState pop_controller_state =
                              [state_->root_view_controller() popControllerState];
                          pop_controller_state.current_viewpoint = 0;
                          [state_->root_view_controller() dismissViewController:pop_controller_state];
                        }
                      });
}

- (void)navbarUnmuteConvo:(UIView*)sender {
  CachedConversation* const c = self.currentConversation;
  if (!c || IsIgnoringInteractionEvents()) {
    return;
  }
  MuteConversations(state_, convo_navbar_.frame, self.view,
                    L(c->vh->id().local_id()), false, ^(bool finished) {
                      if (finished) {
                        CachedConversation* const c = self.currentConversation;
                        ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
                            c->vh->id().local_id(), state_->db());
                        [convo_navbar_ configureFromViewpoint:vh];
                      }
                    });
}

- (bool)verifyNavbarAction:(const string&)action
             selectionSize:(int)selection_size
      singlePhotoSelection:(bool)single_selection {
  if (selection_size > 0) {
    return true;
  }

  [[[UIAlertView alloc]
     initWithTitle:@"No Photo Selected"
           message:(single_selection ?
                    @"Tap a photo to select." :
                    @"Tap a photo to select individually or swipe to select entire events.")
          delegate:NULL
     cancelButtonTitle:@"OK"
     otherButtonTitles:NULL] show];
  return false;
}

- (void)navbarAddPeople:(UIView*)sender {
  if (IsIgnoringInteractionEvents()) {
    return;
  }
  state_->analytics()->ConversationAddPeopleButton();
  if (convo_navbar_.keyboardActive) {
    [convo_navbar_ endEditing:YES];
  }
  [self editModeStartEditingFollowers:self.currentConversation];
}

- (void)navbarUseCamera:(UIView*)sender {
  if (add_photos_ || use_camera_ || IsIgnoringInteractionEvents()) {
    // If the add-photos picker or camera are in the process of being
    // displayed, don't try to display them again.
    return;
  }
  state_->analytics()->ConversationCameraButton();
  if (convo_navbar_.keyboardActive) {
    [convo_navbar_ endEditing:YES];
  }
  use_camera_ = true;
  ControllerTransition transition(TRANSITION_SHOW_FROM_RECT);
  transition.rect = [sender.superview convertRect:sender.frame toView:self.view];
  [state_->root_view_controller() showCamera:transition];
}

- (void)navbarAddPhotos:(UIView*)sender {
  if (add_photos_ || use_camera_ || IsIgnoringInteractionEvents()) {
    // If the add-photos picker or camera are in the process of being
    // displayed, don't try to display them again.
    return;
  }
  state_->analytics()->ConversationAddPhotosButton();
  if (convo_navbar_.keyboardActive) {
    [convo_navbar_ endEditing:YES];
  }
  if (edit_mode_) {
    CachedConversation* const c = self.currentConversation;
    if (!c) {
      return;
    }
    UIView* first_responder = [c->scroll_view findFirstResponder];
    [first_responder resignFirstResponder];
    [self editModeCommitEdits:c];
  }
  [self showAddPhotosFromView:sender coverPhotoSelection:false];
}

- (void)navbarBeginMessage {
  CachedConversation* const c = self.currentConversation;
  if (c) {
    c->viewfinder.userInteractionEnabled = NO;
    convo_navbar_.pan = c->scroll_view.panGestureRecognizer;
  }
  [self adjustScroll:c scrollToBottom:(convo_navbar_.replyToPhoto == NULL)];
  [self stopBrowsing];
}

- (void)navbarEndMessage {
  convo_navbar_.pan = NULL;

  CachedConversation* const c = self.currentConversation;
  if (c) {
    c->viewfinder.userInteractionEnabled = YES;
  }
  [self adjustScroll:c scrollToBottom:false];
}

- (void)navbarShowDrawer {
  CachedConversation* const c = self.currentConversation;
  if (c) {
    c->viewfinder.userInteractionEnabled = NO;
    convo_navbar_.pan = c->scroll_view.panGestureRecognizer;
  }
  [self adjustScroll:c scrollToBottom:false];
  [self stopBrowsing];
}

- (void)navbarHideDrawer {
  convo_navbar_.pan = NULL;

  CachedConversation* const c = self.currentConversation;
  if (c) {
    c->viewfinder.userInteractionEnabled = YES;
  }
  [self adjustScroll:c scrollToBottom:false];
}

- (void)navbarExit:(UIView*)sender {
  [self toolbarCancel];
}

- (void)navbarExport:(UIView*)sender {
  if (![self verifyNavbarAction:"Export"
                  selectionSize:selection_.size()
           singlePhotoSelection:false]) {
    return;
  }
  LOG("conversation: export %d photo%s (%s)", selection_.size(), Pluralize(selection_.size()), selection_);
  state_->analytics()->ConversationExport(selection_.size());
  ShowExportDialog(state_, SelectionSetToVec(selection_), ^(bool completed) {
      [self resetSteadyState];
    });
}

- (void)navbarSend:(UIView*)sender {
  // End editing before sending the comment. This causes any existing
  // autocomplete to be selected.
  UIView* v = [convo_navbar_ findFirstResponder];
  [v resignFirstResponder];
  // Begin editing immediately so that the keyboard does not get dismissed.
  //
  // TODO(peter): Uncomment if we want the keyboard to stay visible after
  // sending the message.
  // [v becomeFirstResponder];

  const string comment(ToString(convo_navbar_.text));
  // The comment should never be empty, but just in case...
  if (!comment.empty()) {
    const int64_t viewpoint_id = [self getViewpointId:visible_conversations_.first];
    const int64_t reply_to_photo_id =
        convo_navbar_.replyToPhoto ? convo_navbar_.replyToPhoto.photoId : 0;
    state_->viewpoint_table()->PostComment(
        viewpoint_id, comment, reply_to_photo_id);
    // Scroll to bottom when keyboard is stowed.
    LOG("comment input send");
    DCHECK_EQ(controller_state_.current_viewpoint, viewpoint_id);
    controller_state_.pending_viewpoint = true;
  }

  [self resetConvoNavbar];
}

- (void)navbarShare:(UIView*)sender {
  if (![self verifyNavbarAction:"Share"
                  selectionSize:selection_.size()
           singlePhotoSelection:false]) {
    return;
  }
  if (snapshot_->conversations()->row_count() == 0) {
    [self navbarShareNew];
    return;
  }
  const string s = MakeActionTitle("Share", selection_.size());
  UIActionSheet* confirm =
      [[UIActionSheet alloc] initWithTitle:NewNSString(s + " to…")
                                  delegate:self
                         cancelButtonTitle:@"Cancel"
                    destructiveButtonTitle:@"New Conversation"
                         otherButtonTitles:@"Existing Conversation", nil];
  confirm.tag = kActionSheetShareTag;
  [confirm setActionSheetStyle:UIActionSheetStyleBlackOpaque];
  [confirm showFromRect:sender.bounds inView:sender animated:YES];
}

- (void)navbarShareNew {
  const PhotoSelectionVec photo_ids(SelectionSetToVec(selection_));
  const ContactManager::ContactVec contacts;
  ViewpointHandle vh = state_->viewpoint_table()->ShareNew(
      photo_ids, contacts, "", false);
  state_->analytics()->ConversationShareNew(photo_ids.size(), contacts.size());
  if (!vh.get()) {
    DIE("conversation: share_new failed: %d photo%s (%s)",
        photo_ids.size(), Pluralize(photo_ids.size()), photo_ids);
  }
  LOG("conversation: %s: share_new %d photo%s (%s)",
      vh->id(), photo_ids.size(), Pluralize(photo_ids.size()), photo_ids);
  [state_->root_view_controller().statusBar
      setMessage:(photo_ids.size() ?
                  Format("Sharing %d Photo%s…", photo_ids.size(), Pluralize(photo_ids.size())) :
                  @"Starting New Conversation")
      activity:true
      type:STATUS_MESSAGE_UI
      displayDuration:0.75];
  controller_state_.current_viewpoint = vh->id().local_id();
  controller_state_.pending_viewpoint = true;

  [self resetSteadyState];
}

- (void)navbarShareExisting {
  [self showConvoPicker];
}

- (void)conversationPickerSelection:(int64_t)viewpoint_id {
  const PhotoSelectionVec photo_ids(SelectionSetToVec(selection_));
  DCHECK(!photo_ids.empty());
  DCHECK_NE(viewpoint_id, 0);

  ViewpointHandle vh;
  vh = state_->viewpoint_table()->ShareExisting(viewpoint_id, photo_ids, false);
  state_->analytics()->ConversationShareExisting(photo_ids.size());
  LOG("conversation: %s: share_existing %d photo%s (%s)",
      vh->id(), photo_ids.size(), Pluralize(photo_ids.size()), photo_ids);
  [state_->root_view_controller().statusBar
      setMessage:Format("Sharing %d Photo%s…", photo_ids.size(),
                        Pluralize(photo_ids.size()))
      activity:true
      type:STATUS_MESSAGE_UI
      displayDuration:0.75];
  [self hideConvoPicker];
  [self resetSteadyState];
}

- (void)conversationPickerExit {
  [self hideConvoPicker];
}

- (void)navbarUnshare:(UIView*)sender {
  if (![self verifyNavbarAction:"Unshare"
                  selectionSize:selection_.size()
           singlePhotoSelection:false]) {
    return;
  }
  const bool filtered = FilterUnshareSelection(
      state_, &selection_, ^{
        CachedConversation* const c = self.currentConversation;
        if (c) {
          [self updateActionControls:c numSelected:selection_.size()];
          [self updateVisiblePhotoSelections:c];
        }
      }, snapshot_->db());
  if (filtered) {
    return;
  }

  const string s = MakeActionTitle("Unshare", selection_.size());
  UIActionSheet* confirm =
      [[UIActionSheet alloc]
        initWithTitle:NULL
             delegate:self
        cancelButtonTitle:@"Cancel"
        destructiveButtonTitle:NewNSString(s)
        otherButtonTitles:NULL];
  confirm.tag = kActionSheetUnshareTag;
  [confirm setActionSheetStyle:UIActionSheetStyleBlackOpaque];
  [confirm showFromRect:sender.bounds inView:sender animated:YES];
}

- (void)navbarUnshareFinish {
  const PhotoSelectionVec photo_ids(SelectionSetToVec(selection_));
  if (photo_ids.empty()) {
    return;
  }
  const int64_t viewpoint_id = [self getViewpointId:visible_conversations_.first];
  LOG("conversation: unshare %d photo%s (%s) from %d",
      photo_ids.size(), Pluralize(photo_ids.size()), photo_ids, viewpoint_id);
  [state_->root_view_controller().statusBar
      setMessage:Format("Unsharing %d Photo%s…", photo_ids.size(),
                        Pluralize(photo_ids.size()))
      activity:true
      type:STATUS_MESSAGE_UI
      displayDuration:0.75];

  state_->viewpoint_table()->Unshare(viewpoint_id, photo_ids);
  state_->analytics()->ConversationUnshare(photo_ids.size());

  [self resetSteadyState];
}

- (void)photoPickerAddPhotos:(PhotoSelectionVec)photo_ids {
  CachedConversation* const c = self.currentConversation;
  if (c->vh->provisional()) {
    // For provisional conversations, we allow an empty photo picker selection
    // to clear out the existing photos in the share new activity.
    const ViewpointSummaryMetadata::ActivityRow& activity_row = c->vsh->activities(0);
    LOG("conversation: update share_new %d photo%s to vp %d, activity %d",
        photo_ids.size(), Pluralize(photo_ids.size()), c->vh->id(),
        activity_row.activity_id());
    // TODO(peter): Clearing the need_rebuild_ flag is a hack. We need a
    // clearer signal of the day table refresh that has handled the
    // modification to the share_new activity.
    need_rebuild_ = false;
    state_->viewpoint_table()->UpdateShareNew(
        c->vh->id().local_id(), activity_row.activity_id(), photo_ids);
    [self editModeEnd:c];

    // For provisional conversations, we stay in editing mode and simply
    // dismiss the photo picker.
    DCHECK_EQ(controller_state_.current_viewpoint, c->vh->id().local_id());
    controller_state_.pending_viewpoint = true;
    [self hideAddPhotos];
    [self maybeRebuildConversations];
    return;
  }

  // If we're modifying the cover photo, check whether the selected
  // photo is already shared into the conversation and use it if so.
  ViewpointSummaryMetadata::ActivityRow::Photo photo;
  if (add_photos_.singlePhotoSelection &&
      photo_ids.size() == 1 &&
      [self findPhoto:photo_ids[0].photo_id photo:&photo]) {
    LOG("conversation: update cover photo for vp %d", c->vh->id());
    [state_->root_view_controller().statusBar
        setMessage:@"Updating cover photo…"
        activity:true
        type:STATUS_MESSAGE_UI
        displayDuration:0.75];
    state_->viewpoint_table()->UpdateCoverPhoto(
        c->vh->id().local_id(), photo.photo_id(), photo.episode_id());
    state_->analytics()->ConversationUpdateCoverPhoto();
  } else {
    if (![self verifyNavbarAction:add_photos_.singlePhotoSelection ? "Select Photo" : "Add Photos"
                    selectionSize:photo_ids.size()
             singlePhotoSelection:add_photos_.singlePhotoSelection]) {
      return;
    }
    LOG("conversation: share_existing %d photo%s to vp %d",
        photo_ids.size(), Pluralize(photo_ids.size()), c->vh->id());
    [state_->root_view_controller().statusBar
        setMessage:Format("Adding %d Photo%s…", photo_ids.size(),
                          Pluralize(photo_ids.size()))
        activity:true
        type:STATUS_MESSAGE_UI
        displayDuration:0.75];
    state_->viewpoint_table()->ShareExisting(
        c->vh->id().local_id(), photo_ids, add_photos_.singlePhotoSelection /* update cover photo */);
    state_->analytics()->ConversationShareExisting(photo_ids.size());
    if (add_photos_.singlePhotoSelection) {
      DCHECK_EQ(controller_state_.current_viewpoint, c->vh->id().local_id());
      controller_state_.pending_viewpoint = true;
    }
  }

  [self hideAddPhotos];
  [self resetSteadyState];
}

- (void)photoPickerExit {
  [self hideAddPhotos];
}

- (void)showInputView:(CachedConversation*)c {
  [convo_navbar_ show];

  // Set scroll view content inset to accommodate input view.
  c->scroll_view.contentInset = UIEdgeInsetsMake(
      0, 0, convo_navbar_.frameHeight, 0);

  // If we're close (within the height of the input text box) of the
  // bottom of the scroll buffer, scroll the rest of the way down so
  // there is no overlap.
  const bool close_enough_to_scroll =
      c->scroll_view.contentOffsetY >=
      ([self cardHeight:c] - c->scroll_view.boundsHeight - kConversationMargin);
  if (close_enough_to_scroll) {
    c->scroll_view.contentOffsetY = c->scroll_view.contentOffsetMaxY;
  }
}

- (void)hideInputView:(CachedConversation*)c {
  [convo_navbar_ hide];
}

- (void)rowViewDidBeginEditing:(RowView*)row {
  CachedConversation* const c = [self conversationForRowView:row];
  if (!c) {
    return;
  }
  editing_row_index_ = row.index;
  [self editModeBegin:c];
}

- (void)rowViewDidEndEditing:(RowView*)row {
  CachedConversation* const c = [self conversationForRowView:row];
  if (!c) {
    return;
  }
  if (editing_row_index_ == row.index) {
    editing_row_index_ = -1;
    if (!c->vh->provisional()) {
      [toolbar_ showConvoItems:true withTitle:[self title:c]];
    }
  }
}

- (void)rowViewDidChange:(RowView*)row {
  CachedConversation* const c = [self conversationForRowView:row];
  if (!c) {
    return;
  }

  ViewpointSummaryMetadata::ActivityRow* activity_row =
      c->vsh->mutable_activities(row.index);
  if (activity_row->height() != row.desiredFrameHeight) {
    activity_row->set_height(row.desiredFrameHeight);
    [self updateConversationPositions:c];
  }

  ConversationHeaderRowView* header = [self getHeaderRowView:c];
  if (c->vh->provisional() && header.editingTitle) {
    [toolbar_ showEditConvoItems:true
                       withTitle:@"Add Title"
                 withDoneEnabled:!header.emptyTitle];
  }
}

- (void)rowViewStopEditing:(RowView*)row commit:(bool)commit {
  if (commit) {
    if (edit_mode_) {
      [self editModeEnd:true];
    }
  }
  [self toolbarCancel];
}

- (void)rowViewCommitText:(RowView*)row text:(NSString*)text {
  CachedConversation* const c = [self conversationForRowView:row];
  if (!c) {
    return;
  }
  EpisodeLayoutRow* const layout_row = FindPtrOrNull(&c->row_cache, row.index);
  if (!layout_row) {
    return;
  }
  if (layout_row->type == ViewpointSummaryMetadata::HEADER) {
    if (c->vh->provisional()) {
      if (text.length > 0) {
        ViewpointHandle vh = state_->viewpoint_table()->LoadViewpoint(
            c->vh->id(), commit_transaction_);
        vh->Lock();
        vh->set_title(ToString(text));
        vh->SaveAndUnlock(commit_transaction_);
      }
    } else if (text.length > 0) {
      state_->viewpoint_table()->UpdateTitle(c->vh->id().local_id(), ToString(text));
      state_->analytics()->ConversationUpdateTitle();
    }
  }
}

- (void)rowViewCommitFollowers:(RowView*)row
                 addedContacts:(const ContactManager::ContactVec&)contacts
                    removedIds:(const vector<int64_t>&)removed_ids {
  CachedConversation* const c = [self conversationForRowView:row];
  if (!c || c->vh->provisional()) {
    return;
  }

  if (!contacts.empty() || !removed_ids.empty()) {
    LOG("conversation %s: add %d follower%s, remove %d follower%s",
        c->vh->id(), contacts.size(), Pluralize(contacts.size()),
        removed_ids.size(), Pluralize(removed_ids.size()));
    if (!contacts.empty()) {
      state_->viewpoint_table()->AddFollowers(c->vh->id().local_id(), contacts);
      state_->analytics()->ConversationAddFollowers(contacts.size());
    }
    if (!removed_ids.empty()) {
      state_->viewpoint_table()->RemoveFollowers(c->vh->id().local_id(), removed_ids);
      state_->analytics()->ConversationRemoveFollowers(removed_ids.size());
      // If the current user removed himself, transition to inbox.
      for (int i = 0; i < removed_ids.size(); ++i) {
        if (removed_ids[i] == state_->user_id()) {
          dispatch_after_main(0, ^{
              [state_->root_view_controller() showInbox:ControllerTransition()];
            });
        }
      }
    }
  }
}

- (void)viewfinderBegin:(ViewfinderTool*)viewfinder {
  CachedConversation* const c = FindPtrOrNull(
      &conversation_cache_, viewfinder.tag);
  if (!c) {
    return;
  }
  [UIView animateWithDuration:0.3
                   animations:^{
      [self hideInputView:c];
      // Clear scroll view content inset.
      c->scroll_view.contentInset = UIEdgeInsetsZero;
    }];
  [toolbar_ showSearchConvoItems:true];
  toolbar_.exitItem.customView.hidden =
      (c->viewfinder.mode == VF_JUMP_SCROLLING);
  [self pauseNetwork];
  viewfinder_active_ = true;
  viewfinder_timer_.Restart();
  const CGPoint offset = c->scroll_view.contentOffset;
  [c->scroll_view setContentOffset:offset animated:NO];
  c->scroll_view.scrollEnabled = NO;
  single_tap_recognizer_.enabled = NO;
  long_press_recognizer_.enabled = NO;
  horizontal_scroll_.scrollEnabled = NO;
}

- (void)viewfinderUpdate:(ViewfinderTool*)viewfinder
                position:(float)position
                animated:(BOOL)animated {
  CachedConversation* const c = FindPtrOrNull(
      &conversation_cache_, viewfinder.tag);
  if (!c) {
    return;
  }
  CGPoint offset = c->scroll_view.contentOffset;
  offset.y = position;
  [c->scroll_view setContentOffset:offset animated:animated];
}

- (void)viewfinderFinish:(ViewfinderTool*)viewfinder {
  CachedConversation* const c = FindPtrOrNull(
      &conversation_cache_, viewfinder.tag);
  if (!c) {
    return;
  }

  [UIView animateWithDuration:0.3
                   animations:^{
      [self showInputView:c];
    }];
  [toolbar_ showConvoItems:true withTitle:[self title:c]];
  [self resumeNetwork];
  viewfinder_active_ = false;
  c->scroll_view.scrollEnabled = YES;
  horizontal_scroll_.scrollEnabled = YES;
  single_tap_recognizer_.enabled = YES;
  long_press_recognizer_.enabled = YES;
  state_->analytics()->ConversationViewfinder(viewfinder_timer_.Get());
  [self maybeRebuildConversations];
}

- (bool)viewfinderAlive:(ViewfinderTool*)viewfinder {
  // Disable viewfinder on conversations.
  //return ContainsKey(conversation_cache_, viewfinder.tag) &&
  //snapshot_.get();
  return false;
}

- (bool)viewfinderShowPosition:(ViewfinderTool*)viewfinder {
  return false;
}

- (bool)viewfinderTimeAscending {
  return true;
}

- (int)viewfinderNumRows:(ViewfinderTool*)viewfinder {
  CachedConversation* const c = FindPtrOrNull(
      &conversation_cache_, viewfinder.tag);
  if (!c) {
    return 0;
  }
  return c->vsh->activities_size();
}

- (std::pair<int, int>)viewfinderRows:(ViewfinderTool*)viewfinder {
  return std::make_pair(0, [self viewfinderNumRows:viewfinder]);
}

- (CGRect)viewfinderRowBounds:(ViewfinderTool*)viewfinder
                        index:(int)index {
  CachedConversation* const c = FindPtrOrNull(
      &conversation_cache_, viewfinder.tag);
  if (!c || index < 0 || index >= c->vsh->activities_size()) {
    return CGRectZero;
  }
  const ViewpointSummaryMetadata::ActivityRow& row = c->vsh->activities(index);
  return CGRectMake(0, row.position(), c->scroll_view.boundsWidth, row.height());
}

- (CGPoint)viewfinderTextOffset:(ViewfinderTool*)viewfinder
                          index:(int)index {
  CachedConversation* const c = FindPtrOrNull(
      &conversation_cache_, viewfinder.tag);
  if (!c || index < 0 || index >= c->vsh->activities_size()) {
    return { 0, 0 };
  }
  const ViewpointSummaryMetadata::ActivityRow& row = c->vsh->activities(index);
  return [self rowTextOffset:row];
}

- (CompositeTextLayer*)viewfinderTextLayer:(ViewfinderTool*)viewfinder
                                     index:(int)index
                                  oldLayer:(CompositeTextLayer*)old_layer
                             takeOwnership:(bool)owner {
  CachedConversation* const c = FindPtrOrNull(
      &conversation_cache_, viewfinder.tag);
  if (!c || index < 0 || index >= c->vsh->activities_size()) {
    return NULL;
  }
  EpisodeLayoutRow* row = FindPtrOrNull(&c->row_cache, index);
  CompositeTextLayer* layer = old_layer;
  if (row) {
    if (!row->view.textLayer) {
      return NULL;
    }
    if (row->view.textLayer != layer) {
      if (layer) {
        [layer removeFromSuperlayer];
      }
      layer = row->view.textLayer;
    }
  }
  if (!layer) {
    const ViewpointSummaryMetadata::ActivityRow& row = c->vsh->activities(index);
    if (row.type() == ViewpointSummaryMetadata::ACTIVITY ||
        row.type() == ViewpointSummaryMetadata::REPLY_ACTIVITY) {
      ActivityHandle ah = state_->activity_table()->LoadActivity(
          row.activity_id(), snapshot_->db());
      ActivityThreadType thread_type = static_cast<ActivityThreadType>(row.thread_type());
      const bool is_continuation = (thread_type == THREAD_COMBINE ||
                                    thread_type == THREAD_COMBINE_END ||
                                    thread_type == THREAD_COMBINE_WITH_TIME ||
                                    thread_type == THREAD_COMBINE_END_WITH_TIME);
      layer = [[ActivityTextLayer alloc] initWithActivity:ah
                                          withActivityRow:&row
                                           isContinuation:is_continuation];
    }
  }

  if (!owner) {
    if (row) {
      [row->view addTextLayer:layer];
    } else if (!row) {
      // The viewfinder tool, when closed, may be trying to "give
      // back" a text layer for which there is currently no cached (or
      // visible) row. The viewfinder tool also often looks at more
      // than the visible set of rows. In both cases, we return the
      // original layer for the viewfinder tool to cache for use
      // when/if the row becomes visible.
      [layer removeFromSuperlayer];
    }
  }

  return layer;
}

- (ViewfinderRowInfo)viewfinderRowInfo:(ViewfinderTool*)viewfinder
                                 index:(int)index {
  CachedConversation* const c = FindPtrOrNull(
      &conversation_cache_, viewfinder.tag);
  if (!c || index < 0 || index >= c->vsh->activities_size()) {
    return ViewfinderRowInfo();
  }
  return ViewfinderRowInfo(c->vsh->activities(index).timestamp(), 1, false);
}

- (bool)viewfinderIsSubrow:(ViewfinderTool*)viewfinder
                     index:(int)index {
  CachedConversation* const c = FindPtrOrNull(
      &conversation_cache_, viewfinder.tag);
  if (!c || index < 0 || index >= c->vsh->activities_size()) {
    return true;
  }
  const ViewpointSummaryMetadata::ActivityRow& row = c->vsh->activities(index);
  // Ignore rows with height == 0, which is reserved for partially
  // resolved rows (e.g. could not download all metadata and/or
  // properly format the row's contents).
  return (row.height() == 0 ||
          row.type() == ViewpointSummaryMetadata::HEADER ||
          row.type() == ViewpointSummaryMetadata::FOOTER ||
          row.type() == ViewpointSummaryMetadata::PHOTOS ||
          row.type() == ViewpointSummaryMetadata::UPDATE);
}

- (bool)viewfinderDisplayPositionIndicator:(ViewfinderTool*)viewfinder {
  return false;
}

- (string)viewfinderFormatPositionIndicator:(ViewfinderTool*)viewfinder
                                atTimestamp:(WallTime)t {
  return FormatRelativeTime(t, state_->WallTime_Now());
}

- (string)viewfinderFormatCurrentTime:(ViewfinderTool*)viewfinder
                          atTimestamp:(WallTime)t {
  return FormatRelativeTime(t, state_->WallTime_Now());
}

- (float)viewfinderTimeScaleSeconds:(ViewfinderTool*)viewfinder {
  SummaryRow row;
  if (snapshot_->conversations()->GetSummaryRow(viewfinder.tag, &row)) {
    TrapdoorHandle trh = snapshot_->LoadTrapdoor(row.identifier());
    return trh->latest_timestamp() - trh->earliest_timestamp();
  }

  LOG("unable to find row index: %d", viewfinder.tag);
  return 24 * 60 * 60;
}

- (UIEdgeInsets)viewfinderContentInsets:(ViewfinderTool*)viewfinder {
  CachedConversation* const c = self.currentConversation;
  if (c) {
    return c->scroll_view.contentInset;
  } else {
    return UIEdgeInsetsZero;
  }
}

- (void)loadView {
  // LOG("conversation: view load");
  self.view = [UIView new];
  self.view.autoresizesSubviews = YES;
  self.view.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleHeight;
  self.view.backgroundColor = [UIColor clearColor];

  horizontal_scroll_ = [UIScrollView new];
  horizontal_scroll_.alwaysBounceHorizontal = YES;
  horizontal_scroll_.autoresizesSubviews = YES;
  horizontal_scroll_.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleHeight;
  horizontal_scroll_.backgroundColor = [UIColor clearColor];
  horizontal_scroll_.delegate = self;
  horizontal_scroll_.pagingEnabled = YES;
  horizontal_scroll_.scrollsToTop = NO;
  horizontal_scroll_.showsHorizontalScrollIndicator = NO;
  horizontal_scroll_.showsVerticalScrollIndicator = NO;
  [self.view addSubview:horizontal_scroll_];

  toolbar_ = [[SummaryToolbar alloc] initWithTarget:self];
  toolbar_.tag = kToolbarTag;
  [self.view addSubview:toolbar_];

  __weak ConversationLayoutController* weak_self = self;
  convo_navbar_ = [[ConversationNavbar alloc] initWithEnv:self];
  convo_navbar_.changed->Add(^{
      CachedConversation* c = weak_self.currentConversation;
      if (c) {
        [weak_self adjustScroll:c scrollToBottom:false];
      }
    });
  convo_navbar_.changed->Run();
  [self.view addSubview:convo_navbar_];

  single_tap_recognizer_ =
      [[UITapGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSingleTap:)];
  single_tap_recognizer_.cancelsTouchesInView = NO;
  single_tap_recognizer_.delegate = self;
  single_tap_recognizer_.numberOfTapsRequired = 1;
  single_tap_recognizer_.enabled = YES;
  [horizontal_scroll_ addGestureRecognizer:single_tap_recognizer_];

  long_press_recognizer_ =
      [[UILongPressGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleLongPress:)];
  long_press_recognizer_.cancelsTouchesInView = NO;
  long_press_recognizer_.delegate = self;
  long_press_recognizer_.enabled = YES;
  // This value should be higher than the one for viewfinder tool
  // activation, or we end up activating viewfinder and replying
  // to a photo if we long press on either side.
  long_press_recognizer_.minimumPressDuration = kViewfinderToolActivationSecs + 0.100;
  long_press_recognizer_.numberOfTapsRequired = 0;
  [horizontal_scroll_ addGestureRecognizer:long_press_recognizer_];

  swipe_left_recognizer_ =
      [[UISwipeGestureRecognizer alloc]
        initWithTarget:self action:@selector(handleSwipeLeft:)];
  swipe_left_recognizer_.cancelsTouchesInView = NO;
  swipe_left_recognizer_.delegate = self;
  swipe_left_recognizer_.direction = UISwipeGestureRecognizerDirectionLeft;
  swipe_left_recognizer_.enabled = NO;
  [horizontal_scroll_ addGestureRecognizer:swipe_left_recognizer_];

  swipe_right_recognizer_ =
      [[UISwipeGestureRecognizer alloc]
        initWithTarget:self action:@selector(handleSwipeRight:)];
  swipe_right_recognizer_.cancelsTouchesInView = NO;
  swipe_right_recognizer_.delegate = self;
  swipe_right_recognizer_.direction = UISwipeGestureRecognizerDirectionRight;
  swipe_right_recognizer_.enabled = NO;
  [horizontal_scroll_ addGestureRecognizer:swipe_right_recognizer_];
}

- (void)viewDidUnload {
  // LOG("conversation: view did unload");
  visible_conversation_ = -1;
  toolbar_ = NULL;
  horizontal_scroll_ = NULL;
  convo_navbar_ = NULL;
  add_photos_ = NULL;
  single_tap_recognizer_ = NULL;
  swipe_left_recognizer_ = NULL;
  swipe_right_recognizer_ = NULL;
  conversation_cache_.clear();
  day_table_epoch_ = 0;
}

- (void)viewWillAppear:(BOOL)animated {
  // LOG("conversation: view will appear%s%s",
  //     animated ? " (animated)" : "",
  //     self.visible ? " (visible)" : "");
  [super viewWillAppear:animated];

  [CATransaction begin];
  [CATransaction setDisableActions:YES];

  if (animated) {
    BuildPhotoViewMap(
        state_->photo_view_map(),
        state_->root_view_controller().prevViewController.view);
  }

  [self viewDidLayoutSubviews];
  [self rebuildState];
  [self initContentSize];
  [self initContentPosition];
  [self scrollViewDidScroll:horizontal_scroll_];

  if (animated && !self.visible) {
    // animateTransitionCommit must be called after animateTransitionPrepare.  RootViewController will do this,
    // but other transitions will not.  The only case where this currently happens is when the export dialog
    // is dismissed, which also happens to call view{Will,Did}Appear without view{WillDid}Disappear,
    // so we can detect this case with self.visible.
    [self animateTransitionPrepare];
  }

  if (snapshot_->conversations()->unviewed_inbox_count() > 0) {
    toolbar_.inboxBadge.text =
        Format("%d", snapshot_->conversations()->unviewed_inbox_count());
  } else {
    toolbar_.inboxBadge.text = NULL;
  }

  state_->photo_view_map()->clear();
  [CATransaction commit];

  if (!keyboard_will_show_.get()) {
    keyboard_will_show_.Init(
        UIKeyboardWillShowNotification,
        ^(NSNotification* n) {
          const Dict d(n.userInfo);
          keyboard_frame_ =
              d.find_value(UIKeyboardFrameEndUserInfoKey).rect_value();
          if (CGRectIsNull(keyboard_frame_)) {
            // iOS sends a keyboard will show notification when a TextView is
            // selected for copying even though the keyboard is not
            // shown.
            return;
          }
          const double duration =
              d.find_value(UIKeyboardAnimationDurationUserInfoKey).double_value();
          const int curve =
              d.find_value(UIKeyboardAnimationCurveUserInfoKey).int_value();
          const int options =
              (curve << 16) | UIViewAnimationOptionBeginFromCurrentState;
          [UIView animateWithDuration:duration
                                delay:0
                              options:options
                           animations:^{
              if (convo_navbar_.actionTray) {
                [convo_navbar_ hide];
              }
              CachedConversation* c = self.currentConversation;
              if (c) {
                [self adjustScroll:c scrollToBottom:false];
              }
            }
                           completion:NULL];
        });
  }
  if (!keyboard_will_hide_.get()) {
    keyboard_will_hide_.Init(
        UIKeyboardWillHideNotification,
        ^(NSNotification* n) {
          if (CGRectIsNull(keyboard_frame_)) {
            return;
          }
          keyboard_frame_ = CGRectZero;
          const Dict d(n.userInfo);
          const double duration =
              d.find_value(UIKeyboardAnimationDurationUserInfoKey).double_value();
          const int curve =
              d.find_value(UIKeyboardAnimationCurveUserInfoKey).int_value();
          const int options =
              (curve << 16) | UIViewAnimationOptionBeginFromCurrentState;
          [UIView animateWithDuration:duration
                                delay:0
                              options:options
                           animations:^{
              // If the active conversation is still being edited,
              // don't show the navbar--the keyboard may be resigned
              // in order to show a full contact selection table view.
              CachedConversation* const c = self.currentConversation;
              if (!c || ![self getHeaderRowView:c].editing) {
                [convo_navbar_ show];
              }
              if (c) {
                [self adjustScroll:c scrollToBottom:false];
              }
            }
                           completion:^(BOOL finished) {
            }];
        });
  }

  CachedConversation* const c = self.currentConversation;
  convo_navbar_.enabled = !c->vh->provisional();
  if (c->vh->provisional()) {
    [toolbar_ showStartConvoItems:true withTitle:[self title:c]];
    horizontal_scroll_.scrollEnabled = NO;
  } else {
    [toolbar_ showConvoItems:false withTitle:[self title:c]];
    if (convo_navbar_.pan != NULL) {
      convo_navbar_.pan = c->scroll_view.panGestureRecognizer;
    }
  }

  state_->analytics()->ConversationPage(controller_state_.current_viewpoint);
}

- (void)viewDidAppear:(BOOL)animated {
  // LOG("conversation: view did appear%s", animated ? " (animated)" : "");
  [super viewDidAppear:animated];
  transition_.reset(NULL);
  state_->photo_loader()->LoadPhotos(&photo_queue_);

  // If use_camera_ is true and some photos were taken, we've just
  // transitioned back from the camera controller. Immediately show
  // add photos dialog.
  if (use_camera_ && !controller_state_.current_photos.photo_ids.empty()) {
    [self showAddPhotosFromView:NULL coverPhotoSelection:false];
  }
  use_camera_ = false;

  // If pending_comment_ is true, start a reply-to-photo after
  // unwinding the stack.
  if (pending_comment_ && controller_state_.current_photo) {
    PhotoView* pv = [self findPhotoView:controller_state_.current_photo.photoId];
    dispatch_after_main(0, ^{
        [self replyToPhoto:pv];
      });
  } else if (pending_add_photos_) {
    [self showAddPhotosFromView:self.view coverPhotoSelection:false];
  }
  pending_comment_ = false;
  pending_add_photos_ = false;

  // Note: we set ControllerState::current_photo() to NULL so that a
  // day table rebuild does not cause us to scroll to the current
  // photo. Essentially, current_photo is only being used to pass
  // information from the calling view controller to our current
  // layout about which photo to display.
  controller_state_.current_photo = NULL;
}

- (void)viewWillDisappear:(BOOL)animated {
  LOG("conversation: view will disappear%s", animated ? " (animated)" : "");
  [super viewWillDisappear:animated];
  state_->photo_loader()->CancelLoadPhotos(&photo_queue_);

  if (edit_mode_) {
    CachedConversation* const c = self.currentConversation;
    if (c) {
      [self editModeCommitEdits:c];
    }
    [self editModeEnd:false];
  }

  if (self.numConversations > 0) {
    const int64_t viewpoint_id = [self getViewpointId:visible_conversations_.first];
    controller_state_.current_viewpoint = viewpoint_id;
  }

  // Reset the convo navbar state unless using the camera.
  if (!use_camera_) {
    [self resetConvoNavbar];
  }
  horizontal_scroll_.scrollEnabled = YES;

  keyboard_will_show_.Clear();
  keyboard_will_hide_.Clear();
}

- (void)viewDidDisappear:(BOOL)animated {
  // LOG("conversation: view did disappear%s", animated ? " (animated)" : "");
  DCHECK(!edit_mode_);
  // TODO(peter): add in hook to cancel any active edit mode state.
  [super viewDidDisappear:animated];
  // Unload any loaded images.
  [self clearConversationCache];
  // Reset navbar.
  [convo_navbar_ show];
  // Relinquish snapshot reference(s).
  day_table_epoch_ = 0;
  snapshot_.reset();
  show_all_followers_ = false;

  if (network_paused_) {
    LOG("conversation: network still paused after view disappeared; unpausing");
    [self resumeNetwork];
  }
}

- (void)viewDidLayoutSubviews {
  // LOG("conversation: view did layout subviews");
  [super viewDidLayoutSubviews];

  toolbar_.frame = CGRectMake(
      0, 0, self.view.frameWidth,
      toolbar_.intrinsicHeight + state_->status_bar_height());

  horizontal_scroll_.frame = CGRectMake(
      0, 0, self.view.boundsWidth + kConversationSpacing,
      self.view.boundsHeight);
}

- (void)resetConvoNavbar {
  [convo_navbar_ endEditing:YES];
  convo_navbar_.pan = NULL;
  convo_navbar_.text = @"";
  convo_navbar_.replyToPhoto = NULL;
  [convo_navbar_ showMessageTray];
}

- (void)animateTransitionPrepare {
  UIViewController* prev = state_->root_view_controller().prevViewController;
  if (![prev isKindOfClass:[LayoutController class]]) {
    // Only perform a transition animation if we're transitioning from a layout
    // controller.
    return;
  }

  CachedConversation* const c = self.currentConversation;
  if (!c) {
    return;
  }

  transition_.reset(new LayoutTransitionState(state_, self));
  transition_->FadeInBackground(self.view);
  transition_->FadeInAlpha(c->viewfinder);

  if (c->vh->provisional()) {
    // If this is a draft conversation, animate it sliding up from the bottom.
    transition_->SlideFromBottom(self.view);
  } else {
    // NOTE(peter): _UIBackdropView (which is the internal UIKit class which
    // causes the translucent-blurred background) cannot animate its blur if it
    // is contained inside a layer hierarcy where allowsGroupOpacity is
    // YES. Disable so that the convo_navbar can be transitioned in a pleasing
    // manner.
    convo_navbar_.layer.allowsGroupOpacity = NO;
    transition_->FadeInAlpha(convo_navbar_);
    if (prev == (UIViewController*)state_->root_view_controller().summaryLayoutController) {
      c->content_view.transform = CGAffineTransformMakeScale(0.9, 0.9);
    }
  }

  // If we're transitioning from an inbox card, animate from the inbox
  // card to the conversation
  UIView* cur_view = controller_state_.current_view;
  if (cur_view != NULL && [cur_view isKindOfClass:[InboxCardRowView class]]) {
    transition_->ZoomIn(cur_view);
    controller_state_.current_view = NULL;
  } else {
    for (RowCacheMap::iterator iter(c->row_cache.begin());
         iter != c->row_cache.end();
         ++iter) {
      // Fade in the header row.
      if (iter->first == 0) {
        transition_->FadeInAlpha(iter->second.view);
      } else {
        transition_->PrepareRow(iter->second, true, false);
      }
    }
  }

  transition_->PrepareFinish();
}

- (bool)animateTransitionCommit {
  // LOG("conversation: animate from view controller");
  if (!transition_.get()) {
    return false;
  }

  CachedConversation* const c = self.currentConversation;
  if (c) {
    c->content_view.transform = CGAffineTransformIdentity;
  }
  transition_->Commit();
  return true;
}

- (void)startBrowsing:(CachedConversation*)c {
  c->viewfinder.userInteractionEnabled = NO;
  c->browsing_row.view.alpha = 0;
  c->browsing_row.view.hidden = NO;
  c->browsing_row.view.transform = CGAffineTransformMakeScale(1, 0.0001);

  [UIView animateWithDuration:kDuration
                   animations:^{
      // Search through conversation cache for non-hidden browsing row
      // as it might have changed since this method was first invoked.
      for (ConversationCacheMap::iterator iter(conversation_cache_.begin());
           iter != conversation_cache_.end();
           ++iter) {
        CachedConversation* c = &iter->second;
        if (c->browsing_row.view.hidden == NO) {
          toolbar_.alpha = 1;
          c->browsing_overlay.alpha = 0.3;
          c->browsing_row.view.alpha = 1;
          c->browsing_row.view.transform = CGAffineTransformMakeScale(1, 1);
        }
      }
    }
                   completion:^(BOOL finished) {
      browsing_ = true;
      for (ConversationCacheMap::iterator iter(conversation_cache_.begin());
           iter != conversation_cache_.end();
           ++iter) {
        CachedConversation* c = &iter->second;
        if (c->browsing_row.view.hidden == NO) {
          [self scrollViewDidScroll:c->scroll_view];
        }
      }
    }];
}

- (void)stopBrowsing {
  if (!browsing_) {
    return;
  }
  browsing_ = false;
  [browsing_timer_ invalidate];
  browsing_timer_ = NULL;

  horizontal_scroll_.scrollEnabled = NO;
  [UIView animateWithDuration:kDuration
                   animations:^{
      for (ConversationCacheMap::iterator iter(conversation_cache_.begin());
           iter != conversation_cache_.end();
           ++iter) {
        CachedConversation* c = &iter->second;
        if (c->browsing_row.view.hidden == NO) {
          toolbar_.alpha = 1;
          c->browsing_overlay.alpha = 0;
          c->browsing_row.view.alpha = 0;
          // The 2x scale causes the browsing row to appear to "stretch" out of
          // existence.
          c->browsing_row.view.transform = CGAffineTransformMakeScale(2, 0.0001);
        }
      }
    }
                   completion:^(BOOL finished) {
      for (ConversationCacheMap::iterator iter(conversation_cache_.begin());
           iter != conversation_cache_.end();
           ++iter) {
        CachedConversation* c = &iter->second;
        if (c->browsing_row.view.hidden == NO) {
          c->viewfinder.userInteractionEnabled = YES;
          c->browsing_row.view.hidden = YES;
          c->browsing_row.view.transform = CGAffineTransformIdentity;
        }
      }
      horizontal_scroll_.scrollEnabled = YES;
      [self maybeRebuildConversations];
    }];
}

- (void)scrollViewDidScroll:(UIScrollView*)scroll_view {
  if (scroll_view == horizontal_scroll_) {
    visible_conversations_ = [self conversationRange:self.visibleBounds];
    cache_conversations_ = [self conversationRange:self.cacheBounds];

    // LOG("conversation: view did scroll: %d-%d  %d-%d: %.0f",
    //     visible_conversations_.first, visible_conversations_.second,
    //     cache_conversations_.first, cache_conversations_.second,
    //     scroll_view.contentOffset);

    [self hideConversations:cache_conversations_];
    [self showConversations:cache_conversations_];

    const float x = scroll_view.contentOffsetX;

    for (ConversationCacheMap::iterator iter(conversation_cache_.begin());
         iter != conversation_cache_.end();
         ++iter) {
      CachedConversation& c = iter->second;

      const float c_x = [self conversationOffset:iter->first].x;
      const float t = (x - c_x) / horizontal_scroll_.frameWidth;
      // The 0.7 value was experimentally determined.
      c.browsing_overlay.alpha = (browsing_ ? 0.3 : 0.0) + fabs(t) * 0.7;

      if (fabs(t) < 0.5 && visible_conversation_ != iter->first) {
        visible_conversation_ = iter->first;
        [convo_navbar_ configureFromViewpoint:c.vh];
        [toolbar_ showConvoItems:true withTitle:[self title:&c]];
      }

      if (browsing_) {
        c.browsing_row.view.hidden = NO;
        c.browsing_row.view.alpha = 1 - fabs(t);
      } else {
        const float scroll_t = x / horizontal_scroll_.frameWidth;
        if (x > 0 &&
            x < horizontal_scroll_.contentOffsetMaxX &&
            fabs(scroll_t - int(scroll_t + 0.5)) >= 0.25) {
          [self startBrowsing:&c];
        }
      }
    }
  } else {
    // One of the rows scrolled.
    const int index = scroll_view.tag;
    // LOG("conversation: view did scroll (%d): %.0f",
    //     index, scroll_view.contentOffsetY);
    CachedConversation* const c = FindPtrOrNull(&conversation_cache_, index);
    if (!c) {
      return;
    }

    const CGRect cache_bounds = [self conversationCacheBounds:c];
    const RowRange rows = [self rowRange:c bounds:cache_bounds];
    if (rows.first <= rows.second) {
      [self hideRows:c rowRange:rows];
      [self showRows:c rowRange:rows];
    }

    [self pinConversationViewfinder:c];
    [self pinConversationCoverPhoto:c];

    if (c->scroll_view.tracking &&
        c->scroll_view.contentOffsetY > c->scroll_view.contentOffsetMaxY) {
      const float offset = c->scroll_view.contentOffsetY - c->scroll_view.contentOffsetMaxY;
      [convo_navbar_ setPan:c->scroll_view.panGestureRecognizer withOffset:offset];
    }
  }

  // Load any higher-res versions of photos that are necessary a short delay
  // after the most recent scroll.
  const double delay = browsing_ ? 0.01 : 0.1;
  state_->photo_loader()->LoadPhotosDelayed(delay, &photo_queue_);
}

- (void)pauseNetwork {
  if (!network_paused_) {
    VLOG("conversation: pausing network");
    network_paused_ = true;
    state_->net_manager()->PauseNonInteractive();
  }
}

- (void)resumeNetwork {
  if (network_paused_) {
    VLOG("conversation: resuming network");
    network_paused_ = false;
    state_->net_manager()->ResumeNonInteractive();
  }
}

- (void)scrollViewWillBeginDragging:(UIScrollView*)scroll_view {
  VLOG("conversation: view will begin dragging");
  [self pauseNetwork];

  {
    // Hide the "copy" menu if it is visible.
    UIMenuController* menu_controller = [UIMenuController sharedMenuController];
    if (menu_controller.menuVisible) {
      [menu_controller setMenuVisible:NO animated:NO];
    }
  }

  if (browsing_) {
    // If user begins scrolling again, cancel browsing timer.
    if (scroll_view == horizontal_scroll_) {
      if (browsing_timer_) {
        [browsing_timer_ invalidate];
        browsing_timer_ = NULL;
      }
    } else {
      // Stop browsing mode if user begins scrolling a convo.
      [self stopBrowsing];
    }
  }

  CachedConversation* const c = self.currentConversation;
  if (c) {
    if (scroll_view == c->scroll_view) {
      c->drag_offset = c->scroll_view.contentOffsetY;
    } else if (scroll_view == horizontal_scroll_) {
      // If panning horizontally, close all followers if active.
      show_all_followers_ = false;
      [self getHeaderRowView:c].showAllFollowers = show_all_followers_;
    }
  }
}

- (void)scrollViewDidEndDragging:(UIScrollView*)scroll_view
                  willDecelerate:(BOOL)decelerate {
  VLOG("conversation: view will end dragging%s",
       decelerate ? " (decelerating)" : "");
  if (!decelerate) {
    [self scrollViewDidEndDecelerating:scroll_view];
  }
}

- (void)scrollViewDidEndDecelerating:(UIScrollView*)scroll_view {
  VLOG("conversation: view did end decelerating");
  if (scroll_view == horizontal_scroll_) {
    const int64_t viewpoint_id = [self getViewpointId:visible_conversations_.first];
    if (viewpoint_id != controller_state_.current_viewpoint) {
      // Clear reply-to-photo set in the input view if we change conversations.
      [self resetConvoNavbar];
      controller_state_.current_viewpoint = viewpoint_id;
      state_->analytics()->ConversationPage(controller_state_.current_viewpoint);
      // Scrolling horizontally clears selection.
      selection_.clear();

      if (convo_navbar_.topDrawerOpen) {
        // Hide the top drawer if we've switched to a new conversation.
        [convo_navbar_ show];
      }
    }

    // Set timer to close browsing interface.
    if (browsing_) {
      if (browsing_timer_) {
        [browsing_timer_ invalidate];
      }
      browsing_timer_ =
          [NSTimer scheduledTimerWithTimeInterval:kBrowsingTimeoutSecs
                                           target:self
                                         selector:@selector(stopBrowsing)
                                         userInfo:NULL
                                          repeats:NO];
    }
  }

  [self resumeNetwork];
  state_->photo_loader()->LoadPhotos(&photo_queue_);
  [self maybeRebuildConversations];
}

- (void)scrollViewDidEndScrollingAnimation:(UIScrollView*)scroll_view {
  if ([scroll_view isKindOfClass:[ConversationScrollView class]]) {
    ((ConversationScrollView*)scroll_view).scrollingAnimation = false;
    [self maybeRebuildConversations];
  }
}

- (BOOL)scrollViewShouldScrollToTop:(UIScrollView*)scroll_view {
  if (!convo_navbar_.keyboardActive && !convo_navbar_.actionTray) {
    // Hide the bottom/top drawer when scrolling to the top.
    [convo_navbar_ show];
  }
  return YES;
}

- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer*)recognizer {
  if (recognizer == long_press_recognizer_) {
    CachedConversation* const c = self.currentConversation;
    if (c) {
      return c->scroll_view.decelerating ? NO : YES;;
    }
  }
  return YES;
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer*)recognizer
       shouldReceiveTouch:(UITouch*)touch {
  return YES;
}

// TODO(spencer): move to CppDelegate.
- (void)actionSheet:(UIActionSheet*)sheet
clickedButtonAtIndex:(NSInteger)index {
  if (index == 0) {
    if (sheet.tag == kActionSheetUnshareTag) {
      [self navbarUnshareFinish];
    } else if (sheet.tag == kActionSheetShareTag) {
      [self navbarShareNew];
    }
  } else if (index == 1) {
    if (sheet.tag == kActionSheetUnshareTag) {
      [self resetSteadyState];
    } else if (sheet.tag == kActionSheetShareTag) {
      [self navbarShareExisting];
    }
  } else if (index == 2) {
    [self resetSteadyState];
  }
}

- (void)dealloc {
  // Ensure we don't leave the network paused!
  [self resumeNetwork];
}

@end  // ConversationLayoutController

ConversationLayoutController* NewConversationLayoutController(UIAppState* state) {
  return [[ConversationLayoutController alloc] initWithState:state];
}
