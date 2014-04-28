// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.
// Author: Spencer Kimball.

#import <algorithm>
#import <unordered_set>
#import <vector>
#import "Analytics.h"
#import "AsyncState.h"
#import "AttrStringUtils.h"
#import "BadgeView.h"
#import "CALayer+geometry.h"
#import "CheckmarkBadge.h"
#import "Defines.h"
#import "Logging.h"
#import "MathUtils.h"
#import "NetworkManager.h"
#import "PhotoView.h"
#import "RootViewController.h"
#import "SinglePhotoView.h"
#import "StatusBar.h"
#import "STLUtils.h"
#import "SummaryLayoutController.h"
#import "SummaryView.h"
#import "UIView+geometry.h"

namespace {

typedef std::unordered_map<int, SummaryLayoutRow> RowCacheMap;

const float kSummaryTimeScale = 365 * 24 * 60 * 60;

const float kShowDuration = 0.300;
const float kHideDuration = 0.300;

const WallTime kScrollLoadThumbnailsWaitTime = 0.005;     // 5 ms
const WallTime kViewfinderLoadImagesDelay = 0.5;
const WallTime kViewfinderLoadThumbnailsWaitTime = 0.05;  // 50 ms
const float kViewfinderCacheBoundsPercentage = 0;

LazyStaticHexColor kBackgroundColor = { "#9f9c9c" };
LazyStaticHexColor kStatsDividerColor = { "#7f7c7c" };

const float kStatsBaseline = 24;
const float kStatsMargin = 2;

LazyStaticHexColor kStatsColor = { "#ffffff" };
LazyStaticHexColor kStatsNumberColor = { "#ffffff" };

LazyStaticCTFont kStatsFont = {
  kProximaNovaRegular, 12
};
LazyStaticCTFont kStatsNumberFont = {
  kProximaNovaSemibold, 17
};

LazyStaticDict kStatsAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)kStatsFont.get(),
        kCTForegroundColorAttributeName,
        (id)kStatsColor.get().CGColor);
  }
};

LazyStaticDict kStatsNumberAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)kStatsNumberFont.get(),
        kCTForegroundColorAttributeName,
        (id)kStatsNumberColor.get().CGColor);
  }
};

}  // namespace

const float kStatsHeight = 45;
const WallTime kScrollLoadImagesDelay = 0.1;

@implementation SummaryView

@synthesize toolbar = toolbar_;
@synthesize viewfinder = viewfinder_;
@synthesize editMode = edit_mode_;
@synthesize loadImagesDelay = load_images_delay_;
@synthesize controllerState = controller_state_;
@synthesize expandedRowIndex = expanded_row_index_;
@synthesize expandedRowHeight = expanded_row_height_;
@synthesize toolbarBottom = toolbar_bottom_;

- (id)initWithState:(UIAppState*)state
           withType:(SummaryType)type {
  if (self = [super init]) {
    state_ = state;
    type_ = type;
    initialized_ = false;
    expanded_row_index_ = -1;
    visible_rows_.second = -1;
    cache_rows_ = visible_rows_;

    load_images_delay_ = kScrollLoadImagesDelay;
    load_thumbnails_wait_time_ = kScrollLoadThumbnailsWaitTime;
    cache_bounds_percentage_ = self.defaultScrollCacheBoundsPercentage;

    self.autoresizesSubviews = YES;
    self.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
    self.backgroundColor = [UIColor clearColor];
    self.clipsToBounds = NO;
    // AddRoundedCorners(self);

    scroll_view_ = [TwoFingerSwipeScrollView new];
    scroll_view_.alwaysBounceVertical = YES;
    scroll_view_.autoresizesSubviews = YES;
    scroll_view_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
    scroll_view_.backgroundColor = kBackgroundColor;
    scroll_view_.scrollsToTop = NO;
    scroll_view_.showsVerticalScrollIndicator = NO;
    scroll_view_.showsHorizontalScrollIndicator = NO;
    [self addSubview:scroll_view_];

    [self updateScrollView];

    stats_view_ = [UIView new];
    stats_view_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleTopMargin;
    stats_view_.backgroundColor = [UIColor clearColor];
    [scroll_view_ addSubview:stats_view_];

    UIView* divider = [UIView new];
    divider.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    divider.backgroundColor = kStatsDividerColor;
    divider.frameTop = kStatsMargin;
    divider.frameWidth = self.boundsWidth;
    divider.frameHeight = UIStyle::kDividerSize;
    [stats_view_ addSubview:divider];

    stats_text_ = [TextLayer new];
    [stats_view_.layer addSublayer:stats_text_];

    viewfinder_ = [[ViewfinderTool alloc] initWithEnv:self appState:state_];
    viewfinder_.userInteractionEnabled = YES;
    [scroll_view_ addSubview:viewfinder_];
    [viewfinder_ addGestureRecognizers:scroll_view_];

    single_tap_recognizer_ =
        [[UITapGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSingleTap:)];
    single_tap_recognizer_.cancelsTouchesInView = NO;
    single_tap_recognizer_.delegate = self;
    single_tap_recognizer_.numberOfTapsRequired = 1;
    single_tap_recognizer_.enabled = YES;
    [scroll_view_ addGestureRecognizer:single_tap_recognizer_];

    swipe_left_recognizer_ =
        [[UISwipeGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSwipeLeft:)];
    swipe_left_recognizer_.cancelsTouchesInView = NO;
    swipe_left_recognizer_.delegate = self;
    swipe_left_recognizer_.direction = UISwipeGestureRecognizerDirectionLeft;
    swipe_left_recognizer_.enabled = YES;
    [scroll_view_ addGestureRecognizer:swipe_left_recognizer_];

    swipe_right_recognizer_ =
        [[UISwipeGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSwipeRight:)];
    swipe_right_recognizer_.cancelsTouchesInView = NO;
    swipe_right_recognizer_.delegate = self;
    swipe_right_recognizer_.direction = UISwipeGestureRecognizerDirectionRight;
    swipe_right_recognizer_.enabled = YES;
    [scroll_view_ addGestureRecognizer:swipe_right_recognizer_];

    // Avoid a reference cycle by using a weak pointer to self.
    __weak SummaryView* weak_self = self;
    photo_queue_.name = Format("summary (%d)", type_);
    photo_queue_.block = [^(vector<PhotoView*>* q) {
        [weak_self photoLoadPriorityQueue:q];
      } copy];
  }
  return self;
}

- (float)contentOffsetTop {
  // Returns the top of the visible area of the scroll view.
  return self.searching ? self.contentInsetTop : self.toolbarBottom;
}

- (float)maxExpandHeight {
  return scroll_view_.frameHeight - self.contentOffsetTop;
}

- (void)willMoveToSuperview:(UIView *)new_superview {
  [super willMoveToSuperview:new_superview];
  if (!new_superview && viewfinder_.active) {
    [viewfinder_ close:true];
  }
}

- (void)setHidden:(BOOL)value {
  if (self.hidden != value) {
    if (value) {
      [self unloadPhotos];
    } else {
      [self loadPhotos];
    }
  }
  scroll_view_.scrollsToTop = !value;
  [super setHidden:value];
}

- (void)clear {
  day_table_epoch_ = 0;
  snapshot_.reset();
  [self clearView];
}

- (bool)resetSnapshot:(bool)force {
  const int old_epoch = day_table_epoch_;
  snapshot_ = state_->day_table()->GetSnapshot(&day_table_epoch_);
  if (old_epoch == day_table_epoch_ && !force) {
    // Nothing to do.
    return false;
  }
  return true;
}

- (bool)rebuild {
  return [self rebuild:false];
}

- (bool)rebuild:(bool)force {
  if (![self resetSnapshot:force]) {
    return false;
  }
  [self clearView];

  LOG("%s: rebuild summary", self.name);

  [self maybeExpandRow];
  [self showView];
  [self initContentPosition:[self getCurrentRowIndex]];
  // Invalidate viewfinder before we call drawRect to ensure we're not
  // using outdated values to display row text.
  [viewfinder_ invalidate:scroll_view_.contentOffsetY];

  // Call drawRect directly instead of async setNeedsDisplay to
  // ensure rows are available for possible transition animation.
  [self drawRect:self.bounds];

  // TODO(spencer): The dispatch seems to be necessary on startup, or
  // the stats row is incorrectly positioned under the last row such
  // that its bottom aligns with the bottom of the scroll view.
  dispatch_after_main(0, ^{
      [self showStats];
    });

  controller_state_.current_photo = NULL;
  controller_state_.current_episode = 0;
  controller_state_.current_viewpoint = 0;

  return true;
}

- (void)maybeExpandRow {
  const int64_t current_row_id = [self getCurrentRowId];
  if ((expanded_row_id_ == 0 &&
       current_row_id == 0) ||
      (type_ != SUMMARY_EVENTS &&
       type_ != SUMMARY_CONVERSATIONS)) {
    return;
  }

  int row_index = -1;

  // Reset expanded row state.
  expanded_row_index_ = -1;

  // First, see if the current episode / current photo refers to
  // a row which requires expansion.
  if (current_row_id != 0 && controller_state_.current_photo) {
    // Show the row first--and check if the current photo is available.
    const int current_row_index = [self getRowIndexForId:current_row_id];
    [self showRow:current_row_index];
    const int64_t photo_id = controller_state_.current_photo.photoId;
    RowView* view = row_cache_[current_row_index].view;
    if ([view hasPhoto:photo_id] && ![view findPhotoView:photo_id]) {
      row_index = current_row_index;
    }
  }

  // If row_index is still -1, check whether we had a previously expanded row.
  if (row_index == -1 && expanded_row_id_ != 0) {
    row_index = [self getRowIndexForId:expanded_row_id_];
    [self showRow:row_index];  // Make sure row is shown so we can expand it.
  }

  if (row_index != -1) {
    expanded_row_index_ = row_index;
    expanded_row_height_ = [row_cache_[row_index].view toggleExpand:self.maxExpandHeight];
    expanded_row_id_ = [self getIdForRowIndex:expanded_row_index_];

    // If there's a current photo, locate frame and scroll so that it
    // is just visible at bottom of scroll.
    [self scrollToCurrentPhotoInRowView:row_cache_[row_index].view];

    // Reset the current episode so it doesn't cause further
    // repositioning of scroll offset.
    [self clearCurrentRowId];
  }

  // Invalidate the viewfinder positions to account for the expansion/collapse.
  [viewfinder_ invalidate:scroll_view_.contentOffsetY];
}

- (void)loadPhotos {
  state_->photo_loader()->LoadPhotos(&photo_queue_);
}

- (void)unloadPhotos {
  // Unload any loaded images.
  state_->photo_loader()->CancelLoadPhotos(&photo_queue_);
  MutexLock l(state_->photo_loader()->mutex());
  for (RowCacheMap::iterator iter(row_cache_.begin());
       iter != row_cache_.end();
       ++iter) {
    SummaryLayoutRow& row = iter->second;
    for (int i = 0; i < row.view.photos->size(); ++i) {
      (*row.view.photos)[i].image = NULL;
    }
  }
}

- (void)animateTransitionPrepare:(LayoutTransitionState*)transition {
  transition->FadeInAlpha(viewfinder_);

  // If we're transitioning from a conversation to the inbox, show the
  // inbox card immediately.
  UIViewController* prev = state_->root_view_controller().prevViewController;
  if (type_ == SUMMARY_CONVERSATIONS &&
      prev == (UIViewController*)state_->root_view_controller().conversationLayoutController) {
    const int64_t vp_id = ((LayoutController*)prev).controllerState.current_viewpoint;
    const int row_index = snapshot_->conversations()->GetViewpointRowIndex(vp_id);
    if (ContainsKey(row_cache_, row_index)) {
      transition->ZoomOut(row_cache_[row_index].view);
      return;
    }
  }

  // Otherwise, prepare the rows as usual so that images animate to their
  // respective positions if there's a match between views.
  if (visible_rows_.first != -1 &&
      visible_rows_.second != -1) {
    for (int i = visible_rows_.first; i <= visible_rows_.second; ++i) {
      if (ContainsKey(row_cache_, i)) {
        transition->PrepareRow(row_cache_[i], true, true);
      }
    }
  }
}

- (bool)viewfinderActive {
  return viewfinder_.active;
}

- (bool)isRowExpanded {
  return expanded_row_index_ != -1;
}

- (int)numSelected {
  return selection_.size();
}

- (SummaryType)type {
  return type_;
}

- (void)setType:(SummaryType)type {
  if (type == type_) {
    return;
  }
  // Close the viewfinder dial if open.
  if (viewfinder_.active) {
    [viewfinder_ close:false];
  }
  // Save prior offset.
  offset_map_[type_] = scroll_view_.contentOffsetY;
  // Restore offset for new type.
  type_ = type;
  {
    scroll_view_.delegate = NULL;
    scroll_view_.contentOffsetY = offset_map_[type_];
    scroll_view_.delegate = self;
  }

  photo_queue_.name = Format("summary (%d)", type_);
  [self clear];
  [self rebuild];
}

- (const PhotoSelectionSet&)selection {
  return selection_;
}

- (void)setSelection:(const PhotoSelectionSet&)selection {
  selection_ = selection;
  [self setSelectionBadgesForAllRows];
  selection_callback_.Run();
}

- (const vector<DisabledPhoto>&)disabledPhotos {
  return disabled_photos_;
}

- (void)setDisabledPhotos:(const vector<DisabledPhoto>&)disabled_photos {
  disabled_photos_ = disabled_photos;
  [self setSelectionBadgesForAllRows];
}

- (CallbackSet*)selectionCallback {
  return &selection_callback_;
}

- (CallbackSet*)scrollToTopCallback {
  return &scroll_to_top_callback_;
}

- (ActivatedCallbackSet*)modalCallback {
  return &modal_callback_;
}

- (ActivatedCallbackSet*)toolbarCallback {
  return &toolbar_callback_;
}

- (ViewpointSelectedCallbackSet*)viewpointCallback {
  return &viewpoint_callback_;
}

- (float)contentHeight {
  return scroll_view_.contentSize.height + self.contentInsetBottom;
}

- (void)drawRect:(CGRect)rect {
  // Note that snapshot_ might be NULL here if [SummaryLayoutController
  // setCurrentView] was called while the SummaryLayoutController was not
  // connected to the view hierarchy.
  if (self.hidden || !snapshot_.get() || CGRectIsEmpty(self.bounds)) {
    return;
  }
  [self scrollViewDidScroll:scroll_view_];
  [self showTextShadows];
}

- (float)rowWidth {
  return self.visibleBounds.size.width;
}

- (CGRect)visibleBounds {
  return self.bounds;
}

- (CGRect)cacheBounds:(const CGRect)bounds {
  return CGRectInset(bounds, 0, -bounds.size.height * cache_bounds_percentage_);
}

- (float)contentInsetBottom {
  return self.displayStats ? kStatsHeight : 0;
}

- (float)contentInsetTop {
  return self.toolbarBottom;
}

- (CGRect)rowBounds:(int)row_index {
  SummaryRow summary_row;
  if (row_index < 0 || row_index >= [self numRows] ||
      ![self getSummaryRow:row_index rowSink:&summary_row withSnapshot:snapshot_]) {
    return CGRectZero;
  }
  const float height = row_index == self.expandedRowIndex ?
                       self.expandedRowHeight :
                       summary_row.height();
  return CGRectMake(0, summary_row.position(), self.rowWidth, height);
}

- (int)minVisibleRow:(const CGRect&)bounds {
  const float y_min = CGRectGetMinY(bounds);
  const int num_rows = [self numRows];
  int s = 0;
  int e = num_rows;
  while (s != e) {
    CHECK_LT(s, e);
    const int m = (s + e) / 2;
    const CGRect b = [self rowBounds:m];
    if (CGRectGetMaxY(b) < y_min) {
      // Row m is before the visible bounds.
      s = m + 1;
    } else if (CGRectGetMinY(b) < y_min) {
      // Row m intersects the start of the visible bounds.
      return m;
    } else {
      // Row m is after the visible bounds.
      e = m;
    }
  }
  return std::min<int>(s, num_rows - 1);
}

- (int)maxVisibleRow:(const CGRect&)bounds {
  const float y_max = CGRectGetMaxY(bounds);
  const float num_rows = [self numRows];
  int s = 0;
  int e = num_rows;
  while (s != e) {
    CHECK_LT(s, e);
    const int m = (s + e) / 2;
    const CGRect b = [self rowBounds:m];
    if (CGRectGetMinY(b) >= y_max) {
      // Row m is after the end visible bounds.
      e = m;
    } else if (CGRectGetMaxY(b) >= y_max) {
      // Row m intersects the end of the visible bounds.
      return m;
    } else {
      // Row m is before the end visible bounds.
      s = m + 1;
    }
  }
  return std::min<int>(s, num_rows - 1);
}

- (RowRange)rowRange:(const CGRect&)bounds {
  if (bounds.size.width == 0 || bounds.size.height == 0) {
    return RowRange(-1, -1);
  }
  return RowRange([self minVisibleRow:bounds],
                  [self maxVisibleRow:bounds]);
}

- (void)clearView {
  MutexLock l(state_->photo_loader()->mutex());

  initialized_ = false;
  expanded_row_index_ = -1;
  scroll_view_.delegate = NULL;

  for (RowCacheMap::iterator iter(row_cache_.begin());
       iter != row_cache_.end();
       ++iter) {
    SummaryLayoutRow& row = iter->second;
    // If the superview isn't the scroll view, don't remove. This may
    // happen if the view transitioned from the inbox to a conversation,
    // where we maintain the inbox card and fade it out last.
    if (row.view.superview == scroll_view_) {
      [row.view removeFromSuperview];
    }
  }
  row_cache_.clear();

  [login_entry_ removeFromSuperview];
  login_entry_ = NULL;

  [self clearPlaceholder];
  [self hideTutorial];
}

- (void)showView {
  if (self.displayStats) {
    stats_attr_str_ = [self getStatsAttrStrWithAttributes:kStatsAttributes
                                     withNumberAttributes:kStatsNumberAttributes];
  }

  scroll_view_.delegate = NULL;
  scroll_view_.contentSize = CGSizeMake(self.bounds.size.width, self.totalHeight);
  scroll_view_.delegate = self;

  LOG("%s: %.0f height", self.name, self.totalHeight);
}

- (void)showStats {
  if (self.displayStats) {
    stats_view_.frame =
        CGRectMake(0, self.totalHeight, self.boundsWidth, kStatsHeight);
    stats_view_.hidden = NO;

    stats_text_.attrStr = AttrCenterAlignment(stats_attr_str_);
    stats_text_.maxWidth = stats_view_.frameWidth - kStatsMargin * 2;
    stats_text_.frameOrigin = CGPointMake((stats_view_.frameWidth - stats_text_.frameWidth) / 2,
                                          kStatsBaseline - stats_text_.baseline);
  } else {
    stats_view_.hidden = YES;
  }
}

- (void)initContentPosition:(int)row_index {
  // Disable calls to the scroll view delegate while we update the content
  // offset.
  scroll_view_.delegate = NULL;
  if (row_index == -1) {
    scroll_view_.contentOffsetY =
        std::min(scroll_view_.contentOffsetY, scroll_view_.contentOffsetMaxY);
  } else {
    const CGRect f = [self rowBounds:row_index];
    [scroll_view_ scrollRectToVisible:f animated:NO];
  }
  scroll_view_.delegate = self;
}

- (void)scrollToRow:(int)row_index {
  SummaryRow row;
  DCHECK([self getSummaryRow:row_index
                     rowSink:&row
                withSnapshot:snapshot_]);
  const float offset = std::min<float>(row.position(), scroll_view_.contentOffsetMaxY);
  [scroll_view_ setContentOffset:CGPointMake(0, offset) animated:YES];
}

- (void)scrollToTop {
  [scroll_view_ setContentOffset:CGPointMake(0, -self.contentInsetTop) animated:YES];
}

- (void)animateExpandRow:(int)row_index
              completion:(void (^)(void))completion {
  const int old_expanded_row_index = expanded_row_index_;
  const float old_expanded_row_height = expanded_row_height_;
  const int new_expanded_row_index = (expanded_row_index_ == row_index) ? -1 : row_index;
  float new_expanded_row_height = 0;

  // Temporarily set expanded row index to get new position.
  expanded_row_index_ = new_expanded_row_index;

  // Compute new visible bounds after the upcoming expand/collapse
  // is complete and scroll offset is adjusted (on expansion, scrolls
  // row to align with top of screen).
  CGRect new_bounds = self.bounds;
  if (new_expanded_row_index != -1) {
    new_expanded_row_height =
        [row_cache_[new_expanded_row_index].view animateToggleExpandPrepare:self.maxExpandHeight];
    expanded_row_height_ = new_expanded_row_height;
    SummaryRow expanded_row;
    DCHECK([self getSummaryRow:expanded_row_index_
                       rowSink:&expanded_row
                  withSnapshot:snapshot_]);
    // Align top of row with top of (visible) scroll view.
    new_bounds.origin.y = std::max<float>(0, expanded_row.position()) - self.contentOffsetTop;
  } else {
    // Do not change the scroll offset when collapsing.
    new_bounds.origin.y = scroll_view_.contentOffset.y;
  }

  const float max_origin_y = std::max<float>(
      0, self.totalHeight + self.contentInsetBottom - self.boundsHeight);
  new_bounds.origin.y = std::min<float>(new_bounds.origin.y, max_origin_y);

  RowRange new_visible_rows = [self rowRange:new_bounds];

  // Prepare old, expanded row for collapse.
  if (old_expanded_row_index != -1) {
    [row_cache_[old_expanded_row_index].view animateToggleExpandPrepare:self.maxExpandHeight];
  }

  // Show the new rows (but using the old expanded index). This places
  // everything correctly for the animation.
  expanded_row_index_ = old_expanded_row_index;
  expanded_row_height_ = old_expanded_row_height;
  [self showRows:new_visible_rows];

  // Set correct expanded row index & height.
  expanded_row_index_ = new_expanded_row_index;
  expanded_row_height_ = new_expanded_row_height;

  // We're going to change the scrollview offset to "new_bounds". We
  // set the scrollview offset without animation and adjust all view
  // offsets by the same delta to give the illusion that the scroll
  // view offset is being animated.
  scroll_view_.delegate = NULL;
  const float delta = new_bounds.origin.y - scroll_view_.contentOffsetY;
  expanded_row_id_ = self.isRowExpanded ? [self getIdForRowIndex:expanded_row_index_] : 0;

  [scroll_view_ setContentOffset:new_bounds.origin animated:NO];
  scroll_view_.scrollEnabled = NO;
  single_tap_recognizer_.enabled = NO;

  // Compute delta of scrollview adjustment and add to all view
  // offsets in advance.
  for (RowCacheMap::iterator iter(row_cache_.begin());
       iter != row_cache_.end();
       ++iter) {
    SummaryLayoutRow& cached_row = iter->second;
    [self setSelectionBadgesForRow:&iter->second];
    cached_row.view.frameTop = cached_row.view.frameTop + delta;
  }

  if (self.displayStats) {
    stats_view_.frameTop = stats_view_.frameTop + delta;
  }

  // Create display link to ensure parallax is maintained at each step
  // of the scroll view content offset animation.
  CADisplayLink* link = [CADisplayLink
                          displayLinkWithTarget:self
                                       selector:@selector(animateExpandRowStep)];
  [link addToRunLoop:[NSRunLoop mainRunLoop] forMode:NSRunLoopCommonModes];

  // Set animating_rows_, which prevents any rows from being evicted
  // from the row cache.
  animating_rows_ = true;

  // Run animation.
  [UIView animateWithDuration:kExpandAnimationDuration
                        delay:0.0
                      options:UIViewAnimationCurveEaseInOut
                   animations:^{
      for (RowCacheMap::iterator iter(row_cache_.begin());
           iter != row_cache_.end();
           ++iter) {
        SummaryLayoutRow& cached_row = iter->second;
        DCHECK([self getSummaryRow:iter->first
                           rowSink:&cached_row.summary_row
                      withSnapshot:snapshot_]);
        const CGRect f = cached_row.view.frame;
        cached_row.view.frame = CGRectMake(f.origin.x, cached_row.summary_row.position(),
                                           f.size.width, cached_row.summary_row.height());
        // Collapse/expand previous expanded or current expanded row as necessary.
        if (iter->first == old_expanded_row_index ||
            iter->first == expanded_row_index_) {
          [cached_row.view animateToggleExpandCommit];
        }
      }
      // Cancel edit mode if active.
      if (self.editModeActive) {
        [self cancelEditMode];
      }
      if (self.displayStats) {
        stats_view_.frameTop = self.totalHeight;
      }
      // Run the modal callback to update the summary toolbar.
      modal_callback_.Run(self.isModal);
    }
                   completion:^(BOOL finished) {
      if (old_expanded_row_index != -1) {
        [row_cache_[old_expanded_row_index].view animateToggleExpandFinalize];
      }
      if (self.isRowExpanded) {
        [row_cache_[expanded_row_index_].view animateToggleExpandFinalize];
      }
      [link invalidate];
      // On completion, reset the animating_rows_ bool so that hidden
      // rows are properly evicted.
      animating_rows_ = false;
      scroll_view_.delegate = self;
      scroll_view_.scrollEnabled = YES;
      single_tap_recognizer_.enabled = YES;
      [self updateScrollView];
      [self scrollViewDidScroll:scroll_view_];
      [self showView];
      [self showStats];
      // Invalidate the viewfinder positions to account for the expansion/collapse.
      [viewfinder_ invalidate:scroll_view_.contentOffsetY];
      if (completion) {
        completion();
      }
    }];
}

- (void)clearExpandedRow {
  expanded_row_id_ = 0;
  expanded_row_index_ = -1;
}

- (void)animateExpandRowStep {
  [self scrollViewDidScroll:scroll_view_];
}

- (void)handleSingleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }

  // Ignore taps which are meant for an underlying UI control, as in the
  // case of a tap on the expand button while in edit mode.
  const CGPoint p = [recognizer locationInView:scroll_view_];
  if ([[scroll_view_ hitTest:p withEvent:NULL] isKindOfClass:[UIControl class]]) {
    return;
  }
  const int row_index = [self rowAtPoint:p];
  ContentView* content_view = [self contentViewAtPoint:p inView:scroll_view_];
  PhotoView* photo_view = [content_view isKindOfClass:[PhotoView class]] ?
                          (PhotoView*)content_view : NULL;

  if ([self photoSelectionEnabled:row_index] ||
      self.singlePhotoSelectionEnabled) {
    if (row_cache_.find(row_index) != row_cache_.end()) {
      SummaryLayoutRow* row = &row_cache_[row_index];
      if (photo_view) {
        if ([photo_view.editBadge pointInside:
                   [recognizer locationInView:photo_view.editBadge] withEvent:NULL]) {
          [self togglePhoto:photo_view];
        } else {
          single_photo_view_ =
              [[SinglePhotoView alloc] initWithState:state_ withPhoto:photo_view];
          single_photo_view_.env = self;
          single_photo_view_.frame = self.frame;
          [self.superview addSubview:single_photo_view_];
          [single_photo_view_ show];
        }
      } else if ([self photoSelectionEnabled:row_index]) {
        // Select all if any aren't yet selected; if all selected, select none.
        [self selectAllPhotos:![self allPhotosSelectedInRow:*row] inRow:row];
      }
    }
  } else if (content_view && content_view.viewpointId != 0) {
    if (self.singleViewpointSelectionEnabled) {
      viewpoint_callback_.Run(content_view.viewpointId,
                              content_view.tag == kInboxCardThumbnailTag ?
                              photo_view : NULL);
    } else {
      // If the row is expanded, select the photo itself.
      if (self.isRowExpanded &&
          row_index == expanded_row_index_ &&
          photo_view && photo_view.selectable) {
        [self selectPhoto:photo_view inRow:row_index];
        return;
      }
      ControllerState new_controller_state;
      new_controller_state.current_viewpoint = content_view.viewpointId;
      DCHECK(ContainsKey(row_cache_, row_index));
      new_controller_state.current_view = row_cache_[row_index].view;
      if (content_view.tag == kInboxCardThumbnailTag) {
        // A specific photo was tapped.
        // NOTE: it was generally agreed that having a tapped photo take
        //   you to the location in the conversation where that photo lives
        //   is too confusing. So this is being taken out for the time being.
        // new_controller_state.current_photo = photo_view;
        //LOG("%s: tapping photo %d in viewpoint %d", self.name,
        //content_view.photoId, content_view.viewpointId);
      } else {
        //LOG("%s: tapping viewpoint %d", self.name, content_view.viewpointId);
      }
      [state_->root_view_controller() showConversation:new_controller_state];
    }
  } else if (type_ == SUMMARY_EVENTS) {
    // TODO(ben): refactor to get rid of explicit type_ check.
    if (row_index == -1) {
      return;
    }
    if (photo_view && photo_view.selectable) {
      [self selectPhoto:photo_view inRow:row_index];
    }
  }
}

- (void)handleSwipeLeft:(UISwipeGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  const CGPoint p = [recognizer locationInView:scroll_view_];
  int row_index = [self rowAtPoint:p];
  if (row_index != -1) {
    if ([self photoSelectionEnabled:row_index]) {
      CHECK(row_cache_.find(row_index) != row_cache_.end());
      SummaryLayoutRow* row = &row_cache_[row_index];
      [self selectAllPhotos:false inRow:row];
    }
  }
}

- (void)handleSwipeRight:(UISwipeGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  const CGPoint p = [recognizer locationInView:scroll_view_];
  int row_index = [self rowAtPoint:p];
  if (row_index != -1) {
    if ([self photoSelectionEnabled:row_index]) {
      CHECK(row_cache_.find(row_index) != row_cache_.end());
      SummaryLayoutRow* row = &row_cache_[row_index];
      [self selectAllPhotos:true inRow:row];
    }
  }
}

- (void)hideRows:(const RowRange&)v {
  // If we're in the middle of a drawer animation (collapsing or
  // expanding event rows), don't evict from cache. This is necessary
  // as some rows may be far outside the normally evictable bounds
  // due to a large event expanding or collapsing.
  if (animating_rows_) {
    return;
  }

  // Hide any rows that fall outside of the row range.
  vector<int> hidden_rows;
  for (RowCacheMap::iterator iter(row_cache_.begin());
       iter != row_cache_.end();
       ++iter) {
    // Skip any rows outside of visible range, or equal to the
    // currently expanded row.
    if ((iter->first >= v.first && iter->first <= v.second) ||
        iter->first == expanded_row_index_) {
      continue;
    }
    // LOG("%s:  %d: hiding row", self.name, c.index);
    hidden_rows.push_back(iter->first);
    SummaryLayoutRow& row = iter->second;
    [row.view removeFromSuperview];
  }
  for (int i = 0; i < hidden_rows.size(); ++i) {
    row_cache_.erase(hidden_rows[i]);
  }
}

- (bool)isPhotoVisible:(PhotoView*)p {
  const CGRect inter = CGRectIntersection(
      [self convertRect:p.frame fromView:p.superview], self.bounds);
  return !CGRectIsNull(inter);
}

// Returns the presentation layer if it's been initialized; otherwise,
// returns original layer.
- (CALayer*)getPresentationLayer:(CALayer*)layer {
  CALayer* present_layer = (CALayer*)layer.presentationLayer;
  if (present_layer.frame.size.width == 0 &&
      present_layer.frame.size.height == 0) {
    return layer;
  }
  return present_layer;
}

- (void)waitThumbnailsLocked:(const RowRange&)v
                       delay:(WallTime)delay {
  vector<PhotoView*> loading;
  for (RowCacheMap::iterator iter(row_cache_.begin());
       iter != row_cache_.end();
       ++iter) {
    SummaryLayoutRow& row = iter->second;
    if (iter->first < v.first || iter->first > v.second) {
      continue;
    }
    for (int i = 0; i < row.view.photos->size(); ++i) {
      PhotoView* p = (*row.view.photos)[i];
      if (!p.image && [self isPhotoVisible:p]) {
        loading.push_back(p);
      }
    }
  }

  if (loading.empty()) {
    return;
  }

  state_->photo_loader()->WaitThumbnailsLocked(loading, delay);
}

- (void)showRowThumbnailsLocked:(int)row_index {
  SummaryLayoutRow* row = &row_cache_[row_index];
  // Get the presentation layer of the row's view. This is necessary to
  // properly compute parallax mid-animation (e.g. for expanding and
  // collapsing rows).
  CALayer* row_p_layer = [self getPresentationLayer:row->view.layer];

  for (int i = 0; i < row->view.photos->size(); ++i) {
    PhotoView* p = (*row->view.photos)[i];

    if (![self isPhotoVisible:p]) {
      continue;
    }

    // TODO(pmattis): Share this code with
    // {Conversation,Event}LayoutController.
    CALayer* photo_p_layer = [self getPresentationLayer:p.layer];
    float t = [row_p_layer convertPoint:photo_p_layer.frame.origin
                              fromLayer:photo_p_layer].y +
              row_p_layer.frame.origin.y - scroll_view_.contentOffsetY;
    const float y1 = -p.frame.size.height;
    const float y2 = self.bounds.size.height;
    // Vary the position between 0.25 at the top of the screen and 0.5 at
    // the bottom of the screen.
    t = LinearInterp<float>(t, y1, y2, 0.25, 0.5);
    p.position = CGPointMake(0.5, t);

    if (p.image || p.thumbnail.get()) {
      // Image/thumbnail is already, or currently being, loaded.
      continue;
    }

    state_->photo_loader()->LoadThumbnailLocked(p);
  }
}

- (void)showRow:(int)row_index {
  SummaryLayoutRow* row = &row_cache_[row_index];
  if (row->view) {
    // Row already visible.
    return;
  }

  //  LOG("%s:  %d: showing row", self.name, row_index);
  if (![self getSummaryRow:row_index
                   rowSink:&row->summary_row
              withSnapshot:snapshot_]) {
    LOG("%s: couldn't fetch row %d", self.name, row_index);
    return;
  }

  [self initLayoutRow:row forRowIndex:row_index];
  [self updateLayoutRow:row forRowIndex:row_index];
  row->view.index = row_index;

  // Add text layer to row.
  if (row->view.textLayer) {
    row->view.textLayer.transition = 0;
    const CGPoint offset = [self rowTextOffset:row_index];
    row->view.textLayer.frame = CGRectMake(offset.x, offset.y, self.rowWidth - offset.x, 0);
    if (viewfinder_.active) {
      [row->view.textLayer removeFromSuperlayer];
    }
  }

  // Maintain selection of any photos which have just been made visible.
  [self setSelectionBadgesForRow:row];

  row->view.frameTop = row->summary_row.position();
  [scroll_view_ insertSubview:row->view belowSubview:viewfinder_];
}

- (void)showRows:(const RowRange&)v {
  MutexLock l(state_->photo_loader()->mutex());

  // Skip if empty.
  if (v.first == -1) {
    return;
  }
  // Loop over the row range, showing rows as necessary.
  const ScopedDisableUIViewAnimations disable_animations;
  for (int i = v.first; i <= v.second; ++i) {
    [self showRow:i];
    [self showRowThumbnailsLocked:i];
  }

  [self waitThumbnailsLocked:visible_rows_
                       delay:load_thumbnails_wait_time_];
}

- (void)showTextShadows {
  for (RowCacheMap::iterator iter(row_cache_.begin());
       iter != row_cache_.end();
       ++iter) {
    SummaryLayoutRow& row = iter->second;
    [row.view.textLayer setShadowWithColor:UIStyle::kShadowColor];
  }
}

- (float)loadPhotoPriority:(PhotoView*)p {
  if ([p isAppropriatelyScaled]) {
    return 0;
  }
  // Prioritize loading of the photo with the most screen overlap.
  const CGRect f = [self convertRect:p.frame
                            fromView:p.superview];
  //LOG("comparing photo frame %s to visible bounds: %s", f, self.visibleBounds);
  const float visible_fraction = VisibleFraction(f, self.visibleBounds);
  if (visible_fraction > 0) {
    // The photo is visible on the screen, prioritize loading over off-screen
    // photos.
    return 1 + visible_fraction;
  }

  const float cache_fraction = VisibleFraction(f, [self cacheBounds:self.visibleBounds]);
  //LOG("cache fraction: %f", cache_fraction);
  return cache_fraction;
}

- (void)photoLoadPriorityQueue:(vector<PhotoView*>*)q {
  // Loop over the cached photos and calculate a load priority for each photo.
  typedef std::pair<float, PhotoView*> PhotoPair;
  vector<PhotoPair> priority_queue;

  for (RowCacheMap::iterator iter(row_cache_.begin());
       iter != row_cache_.end();
       ++iter) {
    SummaryLayoutRow& row = iter->second;
    for (int i = 0; i < row.view.photos->size(); ++i) {
      PhotoView* p = (*row.view.photos)[i];
      const float priority = [self loadPhotoPriority:p];
      if (priority > 0) {
        priority_queue.push_back(std::make_pair(priority, p));
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
    PhotoView* const p = priority_queue[i].second;
    (*q)[i] = p;
  }
}

// Locates a photo in the view and returns its photo view, or NULL
// if not found.
- (PhotoView*)findPhotoView:(int64_t)photo_id {
  for (RowCacheMap::iterator iter(row_cache_.begin());
       iter != row_cache_.end();
       ++iter) {
    SummaryLayoutRow& row = iter->second;
    for (int i = 0; i < row.view.photos->size(); ++i) {
      PhotoView* p = (*row.view.photos)[i];
      if (p.photoId == photo_id) {
        return p;
      }
    }
  }
  return NULL;
}

- (void)animatePhotoSelection:(PhotoView*)p
                   completion:(void (^)(void))completion {
  // Only animate photo selections for photo picker.
  if (type_ != SUMMARY_PHOTO_PICKER) {
    completion();
    return;
  }

  // Create a duplicate photo view and animate it in an arc down
  // to the add photos button.
  PhotoView* copy = NewPhotoView(
      state_, p.episodeId, p.photoId, p.aspectRatio,
      [self.window convertRect:p.bounds fromView:p]);
  copy.image = p.image;
  copy.loadSize = p.loadSize;
  [self.window addSubview:copy];

  const CGRect f = [toolbar_.pickerBadge convertRect:toolbar_.pickerBadge.bounds toView:NULL];
  const float dest_x = CGRectGetMidX(f);
  const float dest_y = CGRectGetMidY(f);

  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  [CATransaction setCompletionBlock:^{
      [copy removeFromSuperview];
      completion();
    }];

  CGMutablePathRef path = CGPathCreateMutable();
  const CGPoint center = copy.center;
  CGPathMoveToPoint(path, NULL, center.x, center.y);
  CGPathAddQuadCurveToPoint(path, NULL,
                            center.x + (dest_x - center.x) * 0.75,
                            center.y + (dest_y - center.y) * 0.5,
                            dest_x, dest_y);

  CAKeyframeAnimation* path_anim = [CAKeyframeAnimation animationWithKeyPath:@"position"];
  path_anim.path = path;
  path_anim.duration = 0.300;
  path_anim.fillMode = kCAFillModeForwards;
  path_anim.removedOnCompletion = NO;

  CABasicAnimation* scale_anim = [CABasicAnimation animationWithKeyPath:@"transform"];
  const float scale = std::min(15.0 / copy.frameWidth, 15.0 / copy.frameHeight);
  CATransform3D scale_tx = CATransform3DMakeScale(scale, scale, scale);
  scale_anim.toValue = [NSValue valueWithCATransform3D:scale_tx];
  scale_anim.fillMode = kCAFillModeForwards;
  scale_anim.removedOnCompletion = NO;

  CABasicAnimation* alpha_anim = [CABasicAnimation animationWithKeyPath:@"opacity"];
  alpha_anim.toValue = [NSNumber numberWithFloat:0.5];
  alpha_anim.fillMode = kCAFillModeForwards;
  alpha_anim.removedOnCompletion = NO;

  CAAnimationGroup* group = [CAAnimationGroup animation];
  group.animations = [NSArray arrayWithObjects:path_anim, scale_anim, alpha_anim, nil];
  group.timingFunction = [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionEaseInEaseOut];
  group.duration = 0.300;
  group.fillMode = kCAFillModeForwards;
  group.removedOnCompletion = NO;

  [copy.layer addAnimation:group forKey:nil];

  [CATransaction commit];
}

- (bool)allPhotosSelectedInRow:(const SummaryLayoutRow&)row {
  for (int i = 0; i < row.view.photos->size(); ++i) {
    PhotoView* p = (*row.view.photos)[i];
    if (!p.selected) {
      return false;
    }
  }
  return true;
}

- (void)singlePhotoViewToggle:(PhotoView*)p {
  [self togglePhoto:p];
}

- (void)singlePhotoViewWillClose {
  single_photo_view_ = NULL;
}

- (void)togglePhoto:(PhotoView*)p {
  if (!p.selectable || !p.episodeId) {
    return;
  }
  const PhotoSelection key(p.photoId, p.episodeId);
  const bool selected = ContainsKey(selection_, key);

  if (self.singlePhotoSelectionEnabled) {
    for (auto iter = selection_.begin(); iter != selection_.end(); ++iter) {
      PhotoView* pv = [self findPhotoView:iter->photo_id];
      if (pv) {
        pv.selected = false;
      }
    }
    selection_.clear();
  }

  if (!selected) {
    selection_.insert(key);
  } else {
    selection_.erase(key);
  }
  [self setSelectionBadgesForAllRows];
  if (p.selected) {
    [self animatePhotoSelection:p completion:^{
        selection_callback_.Run();
      }];
  } else {
    selection_callback_.Run();
  }
}

- (void)selectAllPhotos:(bool)select
                  inRow:(SummaryLayoutRow*)row {
  bool animated = false;
  bool all_selected = true;
  WallTime t = state_->WallTime_Now();
  for (int i = 0; i < row->view.photos->size(); ++i) {
    PhotoView* p = (*row->view.photos)[i];
    if (!p.selectable || !p.episodeId) {
      continue;
    }
    const PhotoSelection key(p.photoId, p.episodeId, t);
    t += 0.001;  // maintain ordering
    if (select) {
      selection_.insert(key);
    } else {
      all_selected = false;
      selection_.erase(key);
    }
    p.selected = select;
    if (select) {
      const bool first_animation = !animated;
      [self animatePhotoSelection:p completion:^{
          if (first_animation) {
            selection_callback_.Run();
          }
        }];
      animated = true;
    }
  }
  row->view.selected = all_selected;
  selection_callback_.Run();
}

// Looks up whether the photo is listed in the disabled photos vector.
// *selected is set if the photo is disabled.
// NOTE: this may get expensive for large conversations, but unlikely
//   to matter. Something to keep in mind though.
- (bool)isPhotoDisabled:(int64_t)photo_id
               selected:(bool*)selected {
  for (int i = 0; i < disabled_photos_.size(); ++i) {
    if (disabled_photos_[i].photo_id == photo_id) {
      *selected = disabled_photos_[i].selected;
      return true;
    }
  }
  return false;
}

- (void)setSelectionBadgesForRow:(SummaryLayoutRow*)row {
  if (![self photoSelectionEnabled:row->view.index] &&
      !self.singlePhotoSelectionEnabled) {
    for (int i = 0; i < row->view.photos->size(); ++i) {
      (*row->view.photos)[i].editing = false;
    }
    row->view.editing = [self rowSelectionEnabled:row->view.index];
  } else {
    bool none_selectable = true;
    for (int i = 0; i < row->view.photos->size(); ++i) {
      PhotoView* p = (*row->view.photos)[i];
      if (p.tag == kEpisodePhotoTag) {
        p.editing = true;
        bool selected;
        if ([self isPhotoDisabled:p.photoId selected:&selected]) {
          p.selectable = false;
          p.selected = selected;
          p.enabled = false;
        } else {
          const PhotoSelection key(p.photoId, p.episodeId);
          none_selectable = false;
          p.selected = ContainsKey(selection_, key);
          p.enabled = true;
        }
      }
    }
    if (row->summary_row.type() == SummaryRow::EVENT ||
        row->summary_row.type() == SummaryRow::FULL_EVENT) {
      row->view.editing = [self rowSelectionEnabled:row->view.index];
      row->view.selected = [self allPhotosSelectedInRow:*row];
      row->view.enabled = !none_selectable;
    }
  }
}

- (void)setSelectionBadgesForAllRows {
  for (RowCacheMap::iterator iter(row_cache_.begin());
       iter != row_cache_.end();
       ++iter) {
    [self setSelectionBadgesForRow:&iter->second];
  }
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

- (int)rowAtPoint:(const CGPoint&)p {
  // Would be nicer to just do [self hitTest:...]. Need to figure out
  // how to make this work.
  for (RowCacheMap::iterator iter(row_cache_.begin());
       iter != row_cache_.end();
       ++iter) {
    SummaryLayoutRow& row = iter->second;
    if (CGRectContainsPoint(row.view.frame, p)) {
      return iter->first;
    }
  }
  return -1;
}

- (bool)canPerformNavbarAction {
  return !viewfinder_.active && !self.editModeActive &&
      !IsIgnoringInteractionEvents();
}

- (void)activateEditMode:(EditMode)edit_mode {
  if (!self.canPerformNavbarAction) {
    return;
  }
  if (type_ == SUMMARY_EVENTS) {
    state_->analytics()->EventActionToggle();
  } else if (type_ == SUMMARY_CONVERSATIONS) {
    state_->analytics()->InboxActionToggle();
  }
  if (self.zeroState) {
    const string asset_type =
        (type_ == SUMMARY_CONVERSATIONS) ? "Conversations" : "Photos";
    NSString* title = NewNSString(Format("You Have No %s!", asset_type));
    NSString* message;
    if (type_ == SUMMARY_CONVERSATIONS) {
      message = @"Start a conversation first.";
    } else {
      message = @"Use the camera to take photos first.";
    }
    UIAlertView* a =
        [[UIAlertView alloc]
              initWithTitle:title
                    message:message
                   delegate:NULL
          cancelButtonTitle:@"OK"
          otherButtonTitles:NULL];
    [a show];
    return;
  }

  edit_mode_ = edit_mode;
  [self setNeedsLayout];
  [self setSelectionBadgesForAllRows];
  [self updateScrollView];
  selection_callback_.Run();
  modal_callback_.Run(true);
}

- (void)cancelEditMode {
  [state_->root_view_controller().statusBar
      hideMessageType:STATUS_MESSAGE_UI
      minDisplayDuration:0.75];

  if (!self.editModeActive) {
    return;
  }
  if (single_photo_view_) {
    [single_photo_view_ hide];
    single_photo_view_ = NULL;
    return;
  }

  selection_.clear();
  disabled_photos_.clear();
  edit_mode_ = EDIT_MODE_INACTIVE;
  [self setNeedsLayout];
  [self setSelectionBadgesForAllRows];
  [self updateScrollView];
  modal_callback_.Run(false);
}

- (void)exitModal {
  if (viewfinder_.active) {
    [viewfinder_ close:true];
  }
}

- (void)navbarDial {
  if (!self.canPerformNavbarAction) {
    return;
  }
  if (type_ == SUMMARY_EVENTS) {
    state_->analytics()->EventSearchButton();
  } else if (type_ == SUMMARY_CONVERSATIONS) {
    state_->analytics()->InboxSearchButton();
  }
  if (viewfinder_.active) {
    [viewfinder_ close:false];
  }
  [viewfinder_ open];
}

- (void)navbarActionExit {
  if (self.editModeActive) {
    [self cancelEditMode];
  }
}

- (void)viewfinderBegin:(ViewfinderTool*)viewfinder {
  [self pauseNetwork];
  load_images_delay_ = kViewfinderLoadImagesDelay;
  load_thumbnails_wait_time_ = kViewfinderLoadThumbnailsWaitTime;
  cache_bounds_percentage_ = kViewfinderCacheBoundsPercentage;
  viewfinder_timer_.Restart();
  const CGPoint offset = scroll_view_.contentOffset;
  [scroll_view_ setContentOffset:offset animated:NO];
  [self updateCachedRows];
  [self setModal:true];
}

- (void)viewfinderUpdate:(ViewfinderTool*)viewfinder
                position:(float)position
                animated:(BOOL)animated {
  CGPoint offset = scroll_view_.contentOffset;
  offset.y = position;
  [scroll_view_ setContentOffset:offset animated:animated];
}

- (void)viewfinderFinish:(ViewfinderTool*)viewfinder {
  state_->analytics()->SummaryViewfinder(self.name, viewfinder_timer_.Get());
  load_images_delay_ = kScrollLoadImagesDelay;
  load_thumbnails_wait_time_ = kScrollLoadThumbnailsWaitTime;
  cache_bounds_percentage_ = self.defaultScrollCacheBoundsPercentage;
  [self resumeNetwork];
  [self setNeedsDisplay];
  [self updateCachedRows];
  [self setModal:false];
}

- (void)setModal:(bool)modal {
  scroll_view_.scrollEnabled = !modal;
  single_tap_recognizer_.enabled = !modal;
  swipe_left_recognizer_.enabled = !modal;
  swipe_right_recognizer_.enabled = !modal;
  modal_callback_.Run(modal);
}

- (bool)editModeActive {
  return edit_mode_ != EDIT_MODE_INACTIVE;
}

- (bool)isModal {
  return (viewfinder_.active || self.editModeActive);
}

- (bool)isScrolling {
  return scroll_view_.dragging || scroll_view_.decelerating;
}

- (bool)zeroState {
  return snapshot_.get() &&
      ([self numRows] == 0 || state_->fake_zero_state());
}

- (CGSize)contentSize {
  return scroll_view_.contentSize;
}

- (bool)viewfinderAlive:(ViewfinderTool*)viewfinder {
  return !self.zeroState && snapshot_.get();
}

- (bool)viewfinderTimeAscending {
  return false;
}

- (int)viewfinderNumRows:(ViewfinderTool*)viewfinder {
  return [self numRows];
}

- (std::pair<int, int>)viewfinderRows:(ViewfinderTool*)viewfinder {
  return std::make_pair(0, [self viewfinderNumRows:viewfinder]);
}

- (CGRect)viewfinderRowBounds:(ViewfinderTool*)viewfinder
                        index:(int)index {
  return [self rowBounds:index];
}

- (CGPoint)viewfinderTextOffset:(ViewfinderTool*)viewfinder
                          index:(int)index {
  return [self rowTextOffset:index];
}

- (CompositeTextLayer*)viewfinderTextLayer:(ViewfinderTool*)viewfinder
                                     index:(int)index
                                  oldLayer:(CompositeTextLayer*)old_layer
                             takeOwnership:(bool)owner {
  SummaryLayoutRow* const row = FindPtrOrNull(&row_cache_, index);
  CompositeTextLayer* layer = old_layer;
  if (row && row->view.textLayer != layer) {
    if (layer) {
      [layer removeFromSuperlayer];
    }
    layer = row->view.textLayer;
  }
  if (!row && !owner) {
    if (layer) {
      // The viewfinder tool, when closed, may be trying to "give
      // back" a text layer for which there is currently no cached (or
      // visible) row. The viewfinder tool also often looks at more
      // than the visible set of rows. If the viewfinder's not holding
      // onto the layer and there's no row visible, remove the layer.
      [layer removeFromSuperlayer];
    }
    return NULL;
  }
  if (!layer) {
    SummaryRow summary_row;
    if (![self getSummaryRow:index rowSink:&summary_row withSnapshot:snapshot_]) {
      DCHECK(false) << Format("%s: unable to fetch summary row %d", self.name, index);
      return NULL;
    }
    layer = [self getTextLayer:summary_row];
  }

  if (!owner) {
    // If expanding/collapsing rows, return NULL so the viewfinder
    // doesn't interfere.
    if (animating_rows_) {
      return NULL;
    }
    if (row) {
      [row->view addTextLayer:layer];
    }
  }

  return layer;
}

- (ViewfinderRowInfo)viewfinderRowInfo:(ViewfinderTool*)viewfinder
                                 index:(int)index {
  SummaryRow summary_row;
  if ([self getSummaryRow:index rowSink:&summary_row withSnapshot:snapshot_]) {
    return ViewfinderRowInfo(summary_row.timestamp(),
                             summary_row.weight(),
                             summary_row.unviewed());
  }
  return ViewfinderRowInfo();
}

- (bool)viewfinderIsSubrow:(ViewfinderTool*)viewfinder
                     index:(int)index {
  return false;
}

- (bool)viewfinderDisplayPositionIndicator:(ViewfinderTool*)viewfinder {
  return self.displayPositionIndicator;
}

- (string)viewfinderFormatPositionIndicator:(ViewfinderTool*)viewfinder
                                atTimestamp:(WallTime)t {
  return FormatRelativeDate(t, state_->WallTime_Now());
}

- (string)viewfinderFormatCurrentTime:(ViewfinderTool*)viewfinder
                          atTimestamp:(WallTime)t {
  return Format("%s", WallTimeFormat("%b %e", t));
}

- (float)viewfinderTimeScaleSeconds:(ViewfinderTool*)viewfinder {
  return kSummaryTimeScale;
}

- (UIEdgeInsets)viewfinderContentInsets:(ViewfinderTool*)viewfinder {
  return scroll_view_.contentInset;
}

- (void)viewDidAppear {
  LOG("%s: view did appear", self.name);
  if (!self.hidden) {
    [self loadPhotos];
  }
}

- (void)viewDidDisappear {
  LOG("%s: view did disappear", self.name);
  [self clear];
  [self unloadPhotos];
  if (network_paused_) {
    LOG("%s: network still paused after view disappeared", self.name);
    [self resumeNetwork];
  }
}

- (void)scrollViewDidScroll:(UIScrollView*)scroll_view {
  if (!initialized_) {
    [self initPlaceholder];
    [self showTutorial];
    initialized_ = true;
  }
  if (self.zeroState) {
    return;
  }

  const CGRect visible_bounds = scroll_view_.bounds;
  const CGRect cache_bounds = [self cacheBounds:visible_bounds];
  visible_rows_ = [self rowRange:visible_bounds];
  cache_rows_ = [self rowRange:cache_bounds];

  // LOG("%s: view did scroll%s: %d-%d  %d-%d: %.0f", self.name,
  //     scroll_view_.dragging ? " (dragging)" : "",
  //     visible_rows_.first, visible_rows_.second,
  //     cache_rows_.first, cache_rows_.second,
  //     scroll_view_.contentOffset);

  [self hideRows:cache_rows_];
  [self showRows:cache_rows_];

  // Pin viewfinder.
  viewfinder_.frame = CGRectOffset(
      viewfinder_.bounds, 0, scroll_view_.contentOffset.y);

  // TODO(pmattis): This seems to screw up network processing sometimes. It
  // looks like the run loop somehow gets stuck in UIEventTrackingMode.

  // Accept input for the default run loop mode. This allows reverse geocoding
  // to complete while the user is dragging.
  // NSRunLoop* run_loop = [NSRunLoop currentRunLoop];
  // [run_loop acceptInputForMode:NSDefaultRunLoopMode
  //                   beforeDate:[NSDate date]];

  // Load any higher-res versions of photos that are necessary X ms after
  // the most recent scroll.
  state_->photo_loader()->LoadPhotosDelayed(load_images_delay_, &photo_queue_);
}

- (void)pauseNetwork {
  if (!network_paused_) {
    VLOG("%s: pausing network", self.name);
    network_paused_ = true;
    state_->net_manager()->PauseNonInteractive();
  }
}

- (void)resumeNetwork {
  if (network_paused_) {
    VLOG("%s: resuming network", self.name);
    network_paused_ = false;
    state_->net_manager()->ResumeNonInteractive();
  }
}

- (void)scrollUIViewToVisible:(UIView*)view
                     animated:(BOOL)animated {
  // Give view frame a negative inset to move it at least a little
  // from top and bottom of view.
  const CGRect scroll_rect =
      CGRectInset([self convertRect:view.frame fromView:view.superview], 0, -10);
  [scroll_view_ scrollRectToVisible:scroll_rect animated:animated];
}

- (void)scrollViewWillBeginDragging:(UIScrollView*)scroll_view {
  //  LOG("%s: view will begin dragging", self.name);
  [self pauseNetwork];
  single_tap_recognizer_.enabled = NO;
}

- (void)scrollViewDidEndDragging:(UIScrollView*)scroll_view
                  willDecelerate:(BOOL)decelerate {
  //  LOG("%s: view did end dragging%s",
  //      self.name, decelerate ? " (decelerating)" : "");
  if (!decelerate) {
    [self scrollViewDidEndDecelerating:scroll_view];
  } else {
    [self setNeedsDisplay];
  }
}

- (void)scrollViewDidEndDecelerating:(UIScrollView*)scroll_view {
  //  LOG("%s: view did end decelerating", self.name);
  [self resumeNetwork];
  [self loadPhotos];
  [self setNeedsDisplay];
  single_tap_recognizer_.enabled = YES;
}

- (void)scrollViewDidScrollToTop:(UIScrollView*)scroll_view {
  //  LOG("%s: did scroll to top", self.name);
  scroll_to_top_callback_.Run();
}

- (void)scrollViewDidEndScrollingAnimation:(UIScrollView*)scroll_view {
  // LOG("%s: did end scrolling animation", self.name);
  [self scrollViewDidEndDragging:scroll_view willDecelerate:false];
}

- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer*)recognizer {
  UIView* v = [scroll_view_ hitTest:[recognizer locationInView:scroll_view_] withEvent:NULL];
  if ([v isKindOfClass:[UIControl class]]) {
    return NO;
  }
  return YES;
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer*)recognizer
       shouldReceiveTouch:(UITouch*)touch {
  return YES;
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer*)a
shouldRecognizeSimultaneouslyWithGestureRecognizer:(UIGestureRecognizer*)b {
  // Don't recognize taps and pans at the same time.
  return !([a isKindOfClass:[UITapGestureRecognizer class]] &&
           [b isKindOfClass:[UIPanGestureRecognizer class]]);
}

- (string)name {
  DIE("abstract method");
  return "";
}

- (float)defaultScrollCacheBoundsPercentage {
  DIE("abstract method");
  return 0;
}

- (int)numRows {
  DIE("abstract method");
  return 0;
}

- (float)totalHeight {
  DIE("abstract method");
  return 0;
}

- (bool)rowSelectionEnabled:(int)row_index {
  return self.editModeActive;
}

- (bool)photoSelectionEnabled:(int)row_index {
  return false;
}

- (bool)singlePhotoSelectionEnabled {
  return false;
}

- (bool)singleViewpointSelectionEnabled {
  return false;
}

- (bool)displayPositionIndicator {
  return true;
}

- (bool)searching {
  return false;
}

- (NSString*)searchTitle {
  return NULL;
}

- (void)initPlaceholder {
}

- (void)clearPlaceholder {
}

- (void)showTutorial {
}

- (void)hideTutorial {
}

- (void)scrollToCurrentPhotoInRowView:(RowView*)row_view {
}

- (void)updateScrollView {
  scroll_view_.contentInset = UIEdgeInsetsMake(
      self.contentInsetTop, 0, self.contentInsetBottom, 0);
}

- (void)hideToolbar {
  toolbar_callback_.Run(true);
}

- (void)showToolbar {
  toolbar_callback_.Run(false);
}

- (void)initLayoutRow:(SummaryLayoutRow*)row
          forRowIndex:(int)row_index {
  DIE("abstract method");
}

- (void)updateCachedRows {
  for (RowCacheMap::iterator iter(row_cache_.begin());
       iter != row_cache_.end();
       ++iter) {
    SummaryLayoutRow* row = &iter->second;
    [self updateLayoutRow:row forRowIndex:iter->first];
  }
}

- (void)updateLayoutRow:(SummaryLayoutRow*)row
            forRowIndex:(int)row_index {
  row->view.userInteractionEnabled = !viewfinder_.active;
}

- (int)getCurrentRowIndex {
  return -1;
}

- (int64_t)getCurrentRowId {
  return 0;
}

- (void)clearCurrentRowId {
}

- (bool)getSummaryRow:(int)row_index
              rowSink:(SummaryRow*)row
         withSnapshot:(const DayTable::SnapshotHandle&)snapshot {
  DIE("abstract method");
  return false;
}

- (bool)displayStats {
  return false;
}

- (NSMutableAttributedString*)getStatsAttrStrWithAttributes:(const Dict&)attrs
                                       withNumberAttributes:(const Dict&)num_attrs {
  DIE("abstract method");
  return NULL;
}

- (CGPoint)rowTextOffset:(int)row_index {
  DIE("abstract method");
  return CGPointZero;
}

- (CompositeTextLayer*)getTextLayer:(const SummaryRow&)summary_row {
  DIE("abstract method");
  return NULL;
}

- (int64_t)getIdForRowIndex:(int)row_index {
  SummaryRow row;
  DCHECK([self getSummaryRow:row_index rowSink:&row withSnapshot:snapshot_]);
  return [self getIdForSummaryRow:row];
}

- (int64_t)getIdForSummaryRow:(const SummaryRow&)row {
  DIE("abstract method");
  return -1;
}

- (int)getRowIndexForId:(int64_t)row_id {
  DIE("abstract method");
  return -1;
}

- (void)selectPhoto:(PhotoView*)photo_view inRow:(int)row_index {
  DIE("abstract method");
}

- (void)dealloc {
  // Ensure we don't leave the network paused!
  [self resumeNetwork];
}

@end  // SummaryView
