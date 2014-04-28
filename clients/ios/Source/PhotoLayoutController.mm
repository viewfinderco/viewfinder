// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.
//
// TODO(pmattis)
// - Provide a count of the number of photos in an episode.

#import <QuartzCore/QuartzCore.h>
#import "Analytics.h"
#import "Callback.h"
#import "ConversationLayoutController.h"
#import "ConversationPickerView.h"
#import "CppDelegate.h"
#import "DayTable.h"
#import "ExportUtils.h"
#import "LayoutController.h"
#import "LayoutUtils.h"
#import "Logging.h"
#import "Matrix.h"
#import "Navbar.h"
#import "PhotoHeader.h"
#import "PhotoLayoutController.h"
#import "PhotoLoader.h"
#import "PhotoManager.h"
#import "PhotoOptions.h"
#import "PhotoSelection.h"
#import "PhotoStorage.h"
#import "PhotoUtils.h"
#import "PhotoView.h"
#import "RootViewController.h"
#import "RotatingView.h"
#import "SummaryLayoutController.h"
#import "Timer.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"
#import "UIViewController+viewfinder.h"
#import "ViewpointTable.h"

namespace {

const float kHeaderHeight = 44;

const float kPhotoSpacing = 10;
const float kEventMarginWidth = 2;
const float kDuration = 0.3;

const float kDragToExitThreshold = 60;

const float kMinRadiansFromVerticalForPaging = kPi * 3 / 16;

LazyStaticRgbColor kPhotoTitleColor = { Vector4f(1, 1, 1, 1) };
LazyStaticRgbColor kEventMarginColor = { Vector4f(0.7, 0.7, 0.7, 1) };

LazyStaticHexColor kBackgroundColor = { "#0d0d0dff" };

LazyStaticUIFont kPhotoLocationFont = {
  kProximaNovaBold, 12
};
LazyStaticUIFont kPhotoTimestampFont = {
  kProximaNovaRegularItalic, 12
};

struct CachedPhoto {
  CachedPhoto()
      : index(-1),
        timestamp(0),
        scroll_view(NULL),
        title(NULL),
        view(NULL) {
  }
  int index;
  WallTime timestamp;
  string location_text;
  UIScrollView* scroll_view;
  UIView* title;
  PhotoView* view;
};

typedef std::pair<int, int> PhotoRange;
typedef std::unordered_map<int64_t, CachedPhoto> PhotoCacheMap;

float ClampContentOffset(float val, float content_size, float visible_size) {
  if (content_size > visible_size) {
    return std::min<float>(content_size - visible_size, val);
  }
  return (content_size - visible_size) / 2;
}

}  // namespace

enum ClampScrollType {
  CLAMP_SCROLL_NONE,
  CLAMP_SCROLL_HORIZONTAL,
  CLAMP_SCROLL_VERTICAL,
};

@interface PhotoLayoutController
    : LayoutController<ConversationPickerEnv,
                       NavbarEnv,
                       PhotoOptionsEnv,
                       UIGestureRecognizerDelegate,
                       UIScrollViewDelegate> {
 @private
  PhotoCacheMap photo_cache_;
  PhotoRange visible_photos_;
  PhotoRange cache_photos_;
  int last_visible_;
  bool need_rebuild_;
  bool paged_;  // true if the view was paged horizontally
  bool header_and_nav_visible_;
  ClampScrollType clamp_scroll_;
  CGPoint start_scroll_offset_;
  PhotoQueue photo_queue_;
  ScopedPtr<LayoutTransitionState> transition_;
  int day_table_epoch_;
  DayTable::SnapshotHandle snapshot_;
  PhotoSelectionSet selection_;
  RotatingView* rotating_view_;
  PhotoOptions* options_;
  UIScrollView* scroll_view_;
  PhotoHeader* header_;
  Navbar* navbar_;
  UITapGestureRecognizer* single_tap_recognizer_;
  UITapGestureRecognizer* double_tap_recognizer_;
  UIView* prev_event_margin_;
  UIView* next_event_margin_;
  ConversationPickerView* convo_picker_;
}

- (id)initWithState:(UIAppState*)state;

@end  // PhotoLayoutController

@implementation PhotoLayoutController

- (id)initWithState:(UIAppState*)state {
  if (self = [super initWithState:state]) {
    self.wantsFullScreenLayout = YES;

    header_and_nav_visible_ = true;
    visible_photos_.second = -1;
    cache_photos_ = visible_photos_;
    last_visible_ = -1;

    // Avoid a reference cycle by using a weak pointer to self.
    __weak PhotoLayoutController* weak_self = self;
    photo_queue_.name = "photo";
    photo_queue_.block = [^(vector<PhotoView*>* q) {
          [weak_self photoLoadPriorityQueue:q];
      } copy];

    // Receive notifications for refreshes to day metadata.
    state_->day_table()->update()->Add(^{
        dispatch_after_main(0, ^{
            need_rebuild_ = true;
            if (self.visible) {
              [self maybeRebuild];
            }
          });
      });
  }
  return self;
}

- (bool)statusBarHidden {
  return true;
}

- (PhotoSource)photoSource {
  if (state_->root_view_controller().popViewController ==
      state_->root_view_controller().summaryLayoutController) {
    SummaryPage summary_page =
        state_->root_view_controller().summaryLayoutController.summaryPage;
    if (summary_page == PAGE_PROFILE) {
      return SOURCE_PROFILE;
    } else {
      return SOURCE_INBOX;
    }
  } else if (state_->root_view_controller().popViewController ==
             (UIViewController*)state_->root_view_controller().conversationLayoutController) {
    return SOURCE_CONVERSATION;
  } else if (state_->root_view_controller().popViewController ==
             state_->root_view_controller().cameraController) {
    return SOURCE_CAMERA;
  }
  return SOURCE_UNKNOWN;
}

- (CGPoint)photoOffset:(int)index {
  return CGPointMake(
      scroll_view_.bounds.size.width * index, 0);
}

- (CGRect)photoBounds:(int)index {
  // The photo scroll view is the size of the main view, but positioned
  // according to the width of the main scroll view (which is kPhotoSpacing
  // wider than the main view).
  const CGPoint p = [self photoOffset:index];
  return CGRectMake(p.x, p.y,
                    rotating_view_.bounds.size.width,
                    scroll_view_.bounds.size.height);
}

- (CGRect)visibleBounds {
  return scroll_view_.bounds;
}

- (CGRect)cacheBounds {
  const CGRect f = self.visibleBounds;
  return CGRectInset(f, -f.size.width / 2, 0);
}

- (CGRect)layoutBounds {
  return rotating_view_.bounds;
}

- (int)numPhotos {
  return controller_state_.current_photos.photo_ids.size();
}

- (int)minVisiblePhoto:(const CGRect&)bounds {
  const float width = scroll_view_.bounds.size.width;
  const int photo = CGRectGetMinX(bounds) / width;
  return std::max<int>(0, std::min<int>(self.numPhotos - 1, photo));
}

- (int)maxVisiblePhoto:(const CGRect&)bounds {
  const float width = scroll_view_.bounds.size.width;
  const int photo = (CGRectGetMaxX(bounds) + width - 1) / width;
  return std::min<int>(self.numPhotos - 1, std::max<int>(0, photo - 1));
}

- (int)visiblePhoto:(const CGRect&)bounds {
  const float width = scroll_view_.bounds.size.width;
  const int photo = int(CGRectGetMinX(bounds) / width + 0.5);
  return std::max<int>(0, std::min<int>(self.numPhotos - 1, photo));
}

- (PhotoRange)photoRange:(const CGRect&)bounds {
  return PhotoRange([self minVisiblePhoto:bounds],
                    [self maxVisiblePhoto:bounds]);
}

- (int64_t)photoIndexToId:(int)index {
  return controller_state_.current_photos.photo_ids[index].first;
}

- (int64_t)photoIndexToEpisodeId:(int)index {
  return controller_state_.current_photos.photo_ids[index].second;
}

- (int)photoIdToIndex:(int64_t)id {
  const PhotoIdVec& v = controller_state_.current_photos.photo_ids;
  for (int i = 0; i < v.size(); ++i) {
    if (v[i].first == id) {
      return i;
    }
  }
  return -1;
}

- (string)photoTitle:(const CachedPhoto&)p {
  const PhotoHandle ph = state_->photo_table()->LoadPhoto(
      p.view.photoId, snapshot_->db());
  if (ph.get()) {
    return ph->FormatLocation(false);
  }
  return "Location Unavailable";
}

- (void)rebuildState {
  snapshot_ = state_->day_table()->GetSnapshot(&day_table_epoch_);
  controller_state_.current_photos.Refresh();

  // LOG("photo: %d photos", self.numPhotos);
  if (self.numPhotos == 0) {
    // No photos, pop back to our parent view.
    [self photoOptionsClose];
  }

  // Update indexes of all photos in the photo cache. And adjust their
  // frames in the event that the ordering of photos was changed due to
  // a refresh.
  for (PhotoCacheMap::iterator iter(photo_cache_.begin());
       iter != photo_cache_.end();
       ++iter) {
    CachedPhoto& p = iter->second;
    p.index = [self photoIdToIndex:p.view.photoId];
    p.scroll_view.frame = [self photoBounds:p.index];
  }
}

- (void)rebuildPhotoViewMap {
  // Rebuild the global photo map so it only contains photos that are currently
  // cached.
  state_->photo_view_map()->clear();
  BuildPhotoViewMap(state_->photo_view_map(), self.view);
}

- (void)clearPhotoCache {
  // Remove existing photo views.
  //
  // TODO(pmattis): Add an animation from the photos current position to their
  // new position.
  MutexLock l(state_->photo_loader()->mutex());
  for (PhotoCacheMap::iterator iter(photo_cache_.begin());
       iter != photo_cache_.end();
       ++iter) {
    CachedPhoto& p = iter->second;
    [p.scroll_view removeFromSuperview];
    [p.title removeFromSuperview];
  }
  photo_cache_.clear();
}

- (void)initContentSize {
  // Disable calls to the scroll view delegate while we update the content
  // size.
  id saved_delegate = scroll_view_.delegate;
  scroll_view_.delegate = NULL;
  scroll_view_.contentSize = CGSizeMake(
      [self photoOffset:self.numPhotos].x, scroll_view_.bounds.size.height);
  header_.titleView.contentSize = CGSizeMake(
      scroll_view_.contentSize.width, header_.titleView.frame.size.height);
  scroll_view_.delegate = saved_delegate;
}

- (void)initContentPosition {
  const int index = controller_state_.current_photo ?
                    [self photoIdToIndex:controller_state_.current_photo.photoId] : 0;

  // Disable calls to the scroll view delegate while we update the content
  // position.
  id saved_delegate = scroll_view_.delegate;
  if (index == -1) {
    scroll_view_.contentOffsetX =
        std::min(scroll_view_.contentOffsetX,
                 scroll_view_.contentOffsetMaxX);
  } else {
    scroll_view_.contentOffset = [self photoOffset:index];
  }
  header_.titleView.contentOffset = scroll_view_.contentOffset;
  scroll_view_.delegate = saved_delegate;
}

- (void)initEventMargins {
  const CurrentPhotos& cp = controller_state_.current_photos;
  if (cp.prev_callback) {
    prev_event_margin_.hidden = NO;
    prev_event_margin_.frameHeight = scroll_view_.frameHeight / 2;
    prev_event_margin_.frameTop = scroll_view_.frameHeight / 4;
    prev_event_margin_.frameWidth = kEventMarginWidth;
    prev_event_margin_.frameLeft =
        [self photoOffset:1].x -
        (kPhotoSpacing + kEventMarginWidth) / 2;
  } else {
    prev_event_margin_.hidden = YES;
  }
  if (cp.next_callback) {
    next_event_margin_.hidden = NO;
    next_event_margin_.frameHeight = scroll_view_.frameHeight / 2;
    next_event_margin_.frameTop = scroll_view_.frameHeight / 4;
    next_event_margin_.frameWidth = kEventMarginWidth;
    next_event_margin_.frameLeft =
        [self photoOffset:self.numPhotos - 1].x -
        (kPhotoSpacing + kEventMarginWidth) / 2;
  } else {
    next_event_margin_.hidden = YES;
  }
}

- (void)handleSingleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded ||
      IsIgnoringInteractionEvents()) {
    return;
  }

  // Toggle the visibility of the navbar & header.
  header_and_nav_visible_ = !header_and_nav_visible_;
  state_->analytics()->PhotoToolbarToggle(header_and_nav_visible_);
  [self updateHeaderAndNavbar];
}

- (void)handleDoubleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded ||
      IsIgnoringInteractionEvents()) {
    return;
  }
  CachedPhoto* const p = [self currentCachedPhoto];
  if (!p) {
    return;
  }
  const float kZoomInThreshold = 1.001;
  if (p->scroll_view.zoomScale <= kZoomInThreshold) {
    // We're sufficiently zoomed out: zoom in.
    const CGPoint c = [recognizer locationInView:p->view];
    CGRect f = rotating_view_.bounds;
    f.size.width /= p->scroll_view.maximumZoomScale;
    f.size.height /= p->scroll_view.maximumZoomScale;
    f.origin.x = c.x - f.size.width / 2;
    f.origin.y = c.y - f.size.height / 2;
    [p->scroll_view zoomToRect:f animated:YES];
  } else {
    // We're currently zoomed in: zoom out.
    [p->scroll_view setZoomScale:1.0 animated:YES];
  }
}

- (void)hidePhotos:(const PhotoRange&)v {
  // Hide any photos that fall outside of the photo range.
  vector<int64_t> hidden_photos;
  for (PhotoCacheMap::iterator iter(photo_cache_.begin());
       iter != photo_cache_.end();
       ++iter) {
    CachedPhoto* p = &iter->second;
    if (p->index >= v.first && p->index <= v.second) {
      continue;
    }
    // LOG("  %d: hiding photo", p->index);
    hidden_photos.push_back(iter->first);
    [p->scroll_view removeFromSuperview];
    [p->title removeFromSuperview];
  }
  for (int i = 0; i < hidden_photos.size(); ++i) {
    photo_cache_.erase(hidden_photos[i]);
  }
}

- (void)photoInitZoom:(CachedPhoto*)p {
  // TODO(peter): If we have the original image we should use that instead of
  // kFullSize.
  const float max_dim = std::max(p->view.frame.size.width,
                                 p->view.frame.size.height);
  p->scroll_view.maximumZoomScale = kFullSize / max_dim;
}

- (void)photoDidZoom:(CachedPhoto*)p {
  const CGSize size = p->view.frame.size;
  const CGSize bounds = rotating_view_.bounds.size;
  const float x = std::max<float>(
      0, (bounds.width - size.width) / 2);
  const float y = std::max<float>(
      0, (bounds.height - size.height) / 2);
  p->scroll_view.contentInset = UIEdgeInsetsMake(y, x, y, x);
}

- (void)waitThumbnailsLocked:(const PhotoRange&)v
                       delay:(WallTime)delay {
  vector<PhotoView*> loading;

  for (PhotoCacheMap::iterator iter(photo_cache_.begin());
       iter != photo_cache_.end();
       ++iter) {
    CachedPhoto* p = &iter->second;
    if (!p->view || p->index < v.first || p->index > v.second) {
      continue;
    }
    if (!p->view.image) {
      loading.push_back(p->view);
    }
  }

  if (loading.empty()) {
    return;
  }

  state_->photo_loader()->WaitThumbnailsLocked(loading, delay);
}

- (void)showPhotoThumbnailLocked:(CachedPhoto*)p {
  if (!p->view || p->view.image || p->view.thumbnail.get()) {
    // Image/thumbnail is already, or currently being, loaded.
    return;
  }

  InitPhotoViewImage(state_->photo_view_map(), p->view);
  if (p->view.image) {
    return;
  }

  // LOG("  %d: loading %d", p->index, p->view.photoId);

  state_->photo_loader()->LoadThumbnailLocked(p->view);
}

- (void)showPhotoTitle:(CachedPhoto*)p {
  const string location_text = [self photoTitle:*p];
  if (p->title) {
    if (location_text.empty() || p->location_text == location_text) {
      return;
    }
    // The location text has changed, just rebuild the entire title.
    [p->title removeFromSuperview];
    p->title = NULL;
  }
  p->location_text = location_text;

  const string labels[2] = {
    p->location_text,
    Format("%s, %s", FormatTime(p->timestamp), WallTimeFormat("%A, %B %e, %Y", p->timestamp)),
  };
  UIFont* fonts[2] = {
    kPhotoLocationFont,
    kPhotoTimestampFont,
  };
  const int count = 1 + !p->location_text.empty();

  p->title = [UIView new];
  p->title.autoresizesSubviews = YES;
  p->title.userInteractionEnabled = NO;
  CGSize size = header_.titleView.frame.size;
  p->title.frame = CGRectMake(
      p->scroll_view.frame.origin.x + 8, 0,
      size.width - 16, size.height);

  float y = size.height - (fonts[0].lineHeight + fonts[1].lineHeight + 2);

  for (int i = 0; i < count; ++i) {
    UILabel* label = [UILabel new];
    label.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    label.backgroundColor = [UIColor clearColor];
    label.font = fonts[i];
    label.frame = CGRectMake(0, y, size.width, fonts[i].lineHeight);
    label.lineBreakMode = NSLineBreakByTruncatingTail;
    label.text = NewNSString(labels[i]);
    label.textColor = kPhotoTitleColor;
    [p->title addSubview:label];
    y += fonts[i].lineHeight + 2;
  }

  [header_.titleView addSubview:p->title];
}

- (void)showPhotoLocked:(int)index {
  const int64_t id = [self photoIndexToId:index];
  CachedPhoto* const p = &photo_cache_[id];
  if (!p->scroll_view) {
    // LOG("  %d: showing photo: %d", index, id);
    p->index = index;

    p->scroll_view = [UIScrollView new];
    p->scroll_view.alwaysBounceHorizontal = NO;
    p->scroll_view.alwaysBounceVertical = NO;
    p->scroll_view.backgroundColor = [UIColor clearColor];
    p->scroll_view.autoresizesSubviews = YES;
    p->scroll_view.delegate = self;
    p->scroll_view.frame = [self photoBounds:index];
    p->scroll_view.showsHorizontalScrollIndicator = NO;
    p->scroll_view.showsVerticalScrollIndicator = NO;
    p->scroll_view.tag = index;
    p->scroll_view.zoomScale = 1;
    [scroll_view_ addSubview:p->scroll_view];
  }
  if (!p->view) {
    const PhotoHandle ph = state_->photo_table()->LoadPhoto(id, snapshot_->db());
    if (!ph.get()) {
      // Skip the photo--presumably we'll receive a day table update shortly.
      //
      // TODO(peter): Should add an activity indicator indicator until the
      // photo loads.
      return;
    }

    p->timestamp = ph->timestamp();
    p->view = [[PhotoView alloc] initWithState:state_];
    p->view.aspectRatio = ph->aspect_ratio();
    p->view.frame = AspectFit(self.layoutBounds.size, p->view.aspectRatio);
    p->view.episodeId = [self photoIndexToEpisodeId:index];
    p->view.photoId = id;
    [p->scroll_view addSubview:p->view];
    p->scroll_view.contentSize = p->view.frame.size;

    [self photoInitZoom:p];
    [self photoDidZoom:p];
  }

  [self showPhotoTitle:p];
  [self showPhotoThumbnailLocked:p];
}

- (void)showPhotos:(const PhotoRange&)v {
  MutexLock l(state_->photo_loader()->mutex());

  // Loop over the photo range, showing photos as necessary.
  for (int i = v.first; i <= v.second; ++i) {
    [self showPhotoLocked:i];
  }

  // Wait for thumbnails in any visible photos to be loaded.
  [self waitThumbnailsLocked:visible_photos_ delay:0.005];
}

- (void)unzoomPhotos:(const PhotoRange&)v {
  // Unzoom non-visible photos.
  for (PhotoCacheMap::iterator iter(photo_cache_.begin());
       iter != photo_cache_.end();
       ++iter) {
    CachedPhoto& p = iter->second;
    if (p.index >= v.first && p.index <= v.second) {
      continue;
    }
    p.scroll_view.zoomScale = 1;
  }
}

- (float)loadPhotoPriority:(CachedPhoto*)p {
  const CGSize load_size = p->view.loadSize;
  if (load_size.width > 0 && load_size.height > 0) {
    // The photo already has an image loaded, check to see if it is
    // appropriately scaled.
    const CGRect f = p->view.frame;
    const float scale = std::max(
        f.size.width / load_size.width,
        f.size.height / load_size.height);
    if (scale <= 1.0) {
      return 0;
    }
  }

  // Prioritize loading of the photo with the most screen overlap.
  const CGRect f = [scroll_view_ convertRect:p->view.frame
                                    fromView:p->view.superview];
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
  typedef std::pair<float, CachedPhoto*> PhotoPair;
  vector<PhotoPair> priority_queue;

  for (PhotoCacheMap::iterator iter(photo_cache_.begin());
       iter != photo_cache_.end();
       ++iter) {
    CachedPhoto* p = &iter->second;
    const float priority = [self loadPhotoPriority:p];
    if (priority > 0) {
      priority_queue.push_back(std::make_pair(priority, p));
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
    CachedPhoto* const p = priority_queue[i].second;
    (*q)[i] = p->view;
  }
}

- (void)showConvoPicker {
  if (convo_picker_) {
    return;
  }
  convo_picker_ = [[ConversationPickerView alloc] initWithState:state_];
  convo_picker_.env = self;
  convo_picker_.frame = self.view.bounds;
  [convo_picker_ show];
  [self updateHeaderAndNavbar];
}

- (void)hideConvoPicker {
  if (!convo_picker_) {
    return;
  }
  [convo_picker_ hide:true];
  convo_picker_ = NULL;
  [self updateHeaderAndNavbar];
  [self maybeRebuild];
}

- (void)photoOptionsClose {
  // Clear current photos callbacks.
  controller_state_.current_photos.refresh_callback = NULL;
  controller_state_.current_photos.prev_callback = NULL;
  controller_state_.current_photos.next_callback = NULL;

  ControllerState pop_controller_state =
      [state_->root_view_controller() popControllerState];
  if (paged_) {
    pop_controller_state.current_photo = controller_state_.current_photo;
    pop_controller_state.current_episode = controller_state_.current_episode;
    pop_controller_state.current_viewpoint = controller_state_.current_viewpoint;
    paged_ = false;
  }
  [state_->root_view_controller() dismissViewController:pop_controller_state];
}

- (void)navbarRelatedConvos {
  CachedPhoto* const p = [self currentCachedPhoto];
  if (!p) {
    return;
  }
  [self commentOnPhoto:p];
}

- (void)commentOnPhoto:(CachedPhoto*)p {
  if (controller_state_.current_viewpoint == 0) {
    // Photo was accessed from the library? This will be going away soon.
    return;
  }
  if (self.photoSource == SOURCE_CONVERSATION) {
    ControllerState pop_controller_state =
        [state_->root_view_controller() popControllerState];
    pop_controller_state.current_viewpoint = controller_state_.current_viewpoint;
    pop_controller_state.current_photo = p->view;
    state_->root_view_controller().conversationLayoutController.pendingComment = true;
    [state_->root_view_controller() dismissViewController:pop_controller_state];
  } else {
    ControllerState new_controller_state;
    new_controller_state.current_viewpoint = controller_state_.current_viewpoint;
    new_controller_state.current_photo = p->view;
    state_->root_view_controller().conversationLayoutController.pendingComment = true;
    [state_->root_view_controller() showConversation:new_controller_state];
  }
}

- (void)navbarActionExport {
  PhotoSelectionVec selection;
  const int index = visible_photos_.first;
  const int64_t photo_id = controller_state_.current_photos.photo_ids[index].first;
  const int64_t episode_id = controller_state_.current_photos.photo_ids[index].second;
  selection.push_back(PhotoSelection(photo_id, episode_id));
  LOG("photo: export photo (%s)", photo_id);
  state_->analytics()->PhotoExport();
  ShowExportDialog(state_, selection, NULL);
}

- (void)navbarActionRemove {
  // If from dashboard, remove simply reverts dashboard to default
  // image instead of removing it from library.
  if (self.photoSource == SOURCE_PROFILE) {
    [state_->root_view_controller().summaryLayoutController.dashboard resetBackground];
    [self photoOptionsClose];
    return;
  }

  CppDelegate* cpp_delegate = new CppDelegate;
  cpp_delegate->Add(
      @protocol(UIActionSheetDelegate),
      @selector(actionSheet:clickedButtonAtIndex:),
      ^(UIActionSheet* sheet, NSInteger button_index) {
        sheet.delegate = NULL;
        delete cpp_delegate;

        if (button_index == 0) {
          const int index = visible_photos_.first;
          PhotoSelectionVec photo_ids;
          const int64_t photo_id =
              controller_state_.current_photos.photo_ids[index].first;
          const int64_t episode_id =
              controller_state_.current_photos.photo_ids[index].second;
          photo_ids.push_back(PhotoSelection(photo_id, episode_id));
          LOG("photo: remove 1 photo (%d/%d)", photo_id, episode_id);
          controller_state_.current_photo = self.currentPhotoView;
          paged_ = true;
          state_->viewpoint_table()->RemovePhotos(photo_ids);
          state_->analytics()->PhotoRemove();
        }
      });

  UIActionSheet* confirm =
      [[UIActionSheet alloc]
        initWithTitle:NULL
             delegate:cpp_delegate->delegate()
        cancelButtonTitle:@"Cancel"
        destructiveButtonTitle:@"Remove Photo"
        otherButtonTitles:NULL];
  [confirm setActionSheetStyle:UIActionSheetStyleBlackOpaque];
  [confirm showFromRect:navbar_.frame inView:self.view animated:YES];
}

- (void)navbarActionShare {
  if (!state_->is_registered()) {
    state_->ShowNotRegisteredAlert();
    return;
  }
  if (snapshot_->conversations()->row_count() == 0) {
    [self navbarActionShareNew];
    return;
  }

  CppDelegate* cpp_delegate = new CppDelegate;
  cpp_delegate->Add(
      @protocol(UIActionSheetDelegate),
      @selector(actionSheet:clickedButtonAtIndex:),
      ^(UIActionSheet* sheet, NSInteger button_index) {
        sheet.delegate = NULL;
        delete cpp_delegate;

        if (button_index == 0) {
          [self navbarActionShareNew];
        } else if (button_index == 1) {
          // TODO(spencer): figure out rotated view as we are no longer
          //   putting this in rotating_view_.
          [self showConvoPicker];
        } else {
          // Nothing to do; action sheet is gone.
        }
      });

  UIActionSheet* confirm =
      [[UIActionSheet alloc] initWithTitle:@"Share Photo to…"
                                  delegate:cpp_delegate->delegate()
                         cancelButtonTitle:@"Cancel"
                    destructiveButtonTitle:@"New Conversation"
                         otherButtonTitles:@"Existing Conversation", NULL];
  [confirm setActionSheetStyle:UIActionSheetStyleBlackOpaque];
  [confirm showFromRect:navbar_.frame inView:self.view animated:YES];
}

- (void)navbarActionShareNew {
  CachedPhoto* const p = [self currentCachedPhoto];
  if (p) {
    PhotoSelectionVec photo_ids;
    photo_ids.push_back(PhotoSelection(p->view.photoId, p->view.episodeId));
    const ContactManager::ContactVec contacts;
    ViewpointHandle vh = state_->viewpoint_table()->ShareNew(
        photo_ids, contacts, "", false);
    if (!vh.get()) {
      DIE("photo: share_new failed: %d photo%s (%s)",
          photo_ids.size(), Pluralize(photo_ids.size()), photo_ids);
    }
    LOG("photo: %s: share_new %d photo%s (%s)",
        vh->id(), photo_ids.size(), Pluralize(photo_ids.size()), photo_ids);
  }
}

- (void)conversationPickerSelection:(int64_t)viewpoint_id {
  CachedPhoto* const p = [self currentCachedPhoto];
  if (p) {
    PhotoSelectionVec photo_ids;
    photo_ids.push_back(PhotoSelection(p->view.photoId, p->view.episodeId));
    DCHECK_NE(viewpoint_id, 0);

    ViewpointHandle vh;
    vh = state_->viewpoint_table()->ShareExisting(viewpoint_id, photo_ids, false);
    state_->analytics()->PhotoShareExisting();
    LOG("photo: %s: share_existing 1 photo (%s)", vh->id(), photo_ids);
  }
  [self hideConvoPicker];
}

- (void)conversationPickerExit {
  [self hideConvoPicker];
}

- (void)navbarActionUnshare {
  const int index = visible_photos_.first;
  const int64_t photo_id =
      controller_state_.current_photos.photo_ids[index].first;
  const int64_t episode_id =
      controller_state_.current_photos.photo_ids[index].second;

  selection_.clear();
  selection_.insert(PhotoSelection(photo_id, episode_id));

  if (FilterUnshareSelection(state_, &selection_, NULL, snapshot_->db())) {
    LOG("not unsharing as photo was filtered");
    return;
  }

  CppDelegate* cpp_delegate = new CppDelegate;
  cpp_delegate->Add(
      @protocol(UIActionSheetDelegate),
      @selector(actionSheet:clickedButtonAtIndex:),
      ^(UIActionSheet* sheet, NSInteger button_index) {
        sheet.delegate = NULL;
        delete cpp_delegate;

        if (button_index == 0) {
          PhotoSelectionVec photo_ids;
          photo_ids.push_back(PhotoSelection(photo_id, episode_id));

          // Load episode to get viewpoint id.
          const EpisodeHandle eh =
              state_->episode_table()->LoadEpisode(episode_id, snapshot_->db());
          DCHECK(eh.get());
          if (eh.get()) {
            const int64_t viewpoint_id = eh->viewpoint_id().local_id();
            LOG("conversation: unshare photo (%s) from %d", photo_id, viewpoint_id);
            controller_state_.current_photo = self.currentPhotoView;
            paged_ = true;
            state_->viewpoint_table()->Unshare(viewpoint_id, photo_ids);
            state_->analytics()->PhotoUnshare();
          }
        }
      });

  UIActionSheet* confirm =
      [[UIActionSheet alloc]
        initWithTitle:NULL
             delegate:cpp_delegate->delegate()
        cancelButtonTitle:@"Cancel"
        destructiveButtonTitle:@"Unshare Photo"
        otherButtonTitles:NULL];
  [confirm setActionSheetStyle:UIActionSheetStyleBlackOpaque];
  [confirm showFromRect:navbar_.frame inView:self.view animated:YES];
}

- (void)updateHeaderAndNavbar {
  // Only change UI elements if visible.
  if (!navbar_) {
    return;
  }

  if (header_and_nav_visible_) {
    [options_ show];
    [header_ show];
    if (convo_picker_) {
      [navbar_ hide];
    } else {
      [navbar_ show];
      if (self.photoSource == SOURCE_CAMERA) {
        [navbar_ showCameraPhotoItems];
      } else if (self.photoSource == SOURCE_PROFILE) {
        [navbar_ showProfilePhotoItems];
      } else if (self.photoSource == SOURCE_CONVERSATION ||
                 self.photoSource == SOURCE_INBOX) {
        [navbar_ showConversationsPhotoItems];
      }
    }
  } else {
    [options_ hide];
    [header_ hide];
    [navbar_ hide];
  }
}

- (CachedPhoto*)currentCachedPhoto {
  if (visible_photos_.second != -1) {
    const int64_t id = [self photoIndexToId:visible_photos_.first];
    return FindPtrOrNull(&photo_cache_, id);
  }
  return NULL;
}

- (PhotoView*)currentPhotoView {
  CachedPhoto* const p = [self currentCachedPhoto];
  return p ? p->view : NULL;
}

- (void)maybeRebuild {
  if (!need_rebuild_) {
    return;
  }
  CachedPhoto* const p = [self currentCachedPhoto];
  if (scroll_view_.dragging ||
      scroll_view_.decelerating ||
      (p && (p->scroll_view.dragging ||
             p->scroll_view.decelerating)) ||
      convo_picker_ ||
      !state_->app_active()) {
    return;
  }
  [self viewWillAppear:NO];
  need_rebuild_ = false;
}

- (void)loadView {
  // LOG("photo: view load");

  self.view = [UIView new];
  self.view.autoresizesSubviews = YES;
  self.view.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleHeight;
  self.view.backgroundColor = kBackgroundColor;

  // We need rotating_view to be a subview of self.view so that
  // animateTransitionPrepare can correctly convert rectangle coordinates when
  // self.view does not have a superview.
  rotating_view_ = [RotatingView new];
  rotating_view_.prepare->Add(^{
      [self rotatePrepare];
    });
  rotating_view_.commit->Add(^(float duration) {
      [self rotateCommit:duration];
    });
  rotating_view_.autoresizesSubviews = YES;
  rotating_view_.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleHeight;
  rotating_view_.backgroundColor = [UIColor clearColor];
  [self.view addSubview:rotating_view_];

  scroll_view_ = [UIScrollView new];
  scroll_view_.alwaysBounceHorizontal = YES;
  scroll_view_.alwaysBounceVertical = YES;
  scroll_view_.autoresizesSubviews = YES;
  scroll_view_.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleHeight;
  scroll_view_.backgroundColor = [UIColor clearColor];
  scroll_view_.delegate = self;
  scroll_view_.pagingEnabled = YES;
  scroll_view_.showsHorizontalScrollIndicator = NO;
  scroll_view_.showsVerticalScrollIndicator = NO;
  [rotating_view_ addSubview:scroll_view_];

  prev_event_margin_ = [UIView new];
  prev_event_margin_.backgroundColor = kEventMarginColor;
  [scroll_view_ addSubview:prev_event_margin_];

  next_event_margin_ = [UIView new];
  next_event_margin_.backgroundColor = kEventMarginColor;
  [scroll_view_ addSubview:next_event_margin_];

  options_ = [[PhotoOptions alloc] initWithEnv:self];
  options_.autoresizingMask =
      UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleBottomMargin;
  [rotating_view_ addSubview:options_];

  navbar_ = [Navbar new];
  navbar_.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleTopMargin;
  navbar_.env = self;
  [rotating_view_ addSubview:navbar_];

  header_ = [PhotoHeader new];
  header_.frameHeight = kHeaderHeight;
  [rotating_view_ addSubview:header_];

  single_tap_recognizer_ =
      [[UITapGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSingleTap:)];
  single_tap_recognizer_.delegate = self;
  single_tap_recognizer_.enabled = YES;
  single_tap_recognizer_.numberOfTapsRequired = 1;
  [scroll_view_ addGestureRecognizer:single_tap_recognizer_];

  double_tap_recognizer_ =
      [[UITapGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleDoubleTap:)];
  double_tap_recognizer_.delegate = self;
  double_tap_recognizer_.numberOfTapsRequired = 2;
  [scroll_view_ addGestureRecognizer:double_tap_recognizer_];

  [single_tap_recognizer_
    requireGestureRecognizerToFail:double_tap_recognizer_];
}

- (void)viewDidUnload {
  // LOG("photo: view did unload");
  header_ = NULL;
  navbar_ = NULL;
  rotating_view_ = NULL;
  options_ = NULL;
  scroll_view_ = NULL;
  single_tap_recognizer_ = NULL;
  double_tap_recognizer_ = NULL;
  photo_cache_.clear();
}

- (void)viewWillAppear:(BOOL)animated {
  // LOG("photo: view will appear%s", animated ? " (animated)" : "");
  [super viewWillAppear:animated];

  [CATransaction begin];
  [CATransaction setDisableActions:YES];

  PhotoView* tapped_photo = NULL;
  if (animated) {
    BuildPhotoViewMap(
        state_->photo_view_map(),
        state_->root_view_controller().prevViewController.view);
    tapped_photo = controller_state_.current_photo;
  }

  [self updateHeaderAndNavbar];
  [self viewDidLayoutSubviews];
  [self rebuildState];
  [self initContentSize];
  [self initContentPosition];
  [self initEventMargins];
  [self scrollViewDidScroll:scroll_view_];
  // Process any pending rotation after we've adjusted our scroll position to
  // account for the tapped photo that caused us to appear.
  [rotating_view_ willAppear];

  last_visible_ = [self visiblePhoto:self.visibleBounds];
  if (animated && !self.visible) {
    // animateTransitionCommit must be called after animateTransitionPrepare.  RootViewController will do this,
    // but other transitions will not.  The only case where this currently happens is when the export dialog
    // is dismissed, which also happens to call view{Will,Did}Appear without view{WillDid}Disappear,
    // so we can detect this case with self.visible.
    [self animateTransitionPrepare:tapped_photo];
  }

  state_->photo_view_map()->clear();
  [CATransaction commit];
}

- (void)viewDidAppear:(BOOL)animated {
  // LOG("photo: view did appear%s", animated ? " (animated)" : "");
  [super viewDidAppear:animated];
  transition_.reset(NULL);
  state_->photo_loader()->LoadPhotos(&photo_queue_);
}

- (void)viewWillDisappear:(BOOL)animated {
  // LOG("photo: view will disappear%s", animated ? " (animated)" : "");
  [super viewWillDisappear:animated];
  header_and_nav_visible_ = true;
  state_->photo_loader()->CancelLoadPhotos(&photo_queue_);
  CachedPhoto* const p = [self currentCachedPhoto];
  if (p) {
    controller_state_.current_photo = p->view;
  }
  [rotating_view_ willDisappear];
}

- (void)viewDidDisappear:(BOOL)animated {
  // LOG("photo: view did disappear%s", animated ? " (animated)" : "");
  [super viewDidDisappear:animated];
  // Unload any loaded images.
  [self clearPhotoCache];
  // Relinquish snapshot reference.
  day_table_epoch_ = 0;
  snapshot_.reset();
  clamp_scroll_ = CLAMP_SCROLL_NONE;
}

- (void)viewDidLayoutSubviews {
  // LOG("photo: view did layout subviews");
  [super viewDidLayoutSubviews];

  navbar_.frameBottom = rotating_view_.bounds.size.height;
  header_.frameBottom = navbar_.frameBottom - 44;

  scroll_view_.frame = CGRectMake(
      0, 0, rotating_view_.bounds.size.width + kPhotoSpacing,
      rotating_view_.bounds.size.height);
}

- (void)animateTransitionPrepare:(PhotoView*)tapped_photo {
  UIViewController* prev = state_->root_view_controller().prevViewController;
  if (![prev isKindOfClass:[LayoutController class]]) {
    // Only perform a transition animation if we're transitioning from a layout
    // controller.
    return;
  }

  transition_.reset(new LayoutTransitionState(state_, self));
  transition_->FadeInBackground(self.view);
  transition_->FadeInAlpha(header_);
  transition_->FadeInAlpha(navbar_);

  for (int i = visible_photos_.first; i <= visible_photos_.second; ++i) {
    const int id = [self photoIndexToId:i];
    CachedPhoto* const p = FindPtrOrNull(&photo_cache_, id);
    if (!p) {
      continue;
    }
    PhotoView* other_view = (tapped_photo && tapped_photo.photoId == id) ? tapped_photo : NULL;
    if (!other_view) {
      other_view = FindMatchingPhotoView(state_->photo_view_map(), p->view);
      if (!other_view) {
        continue;
      }
    }

    transition_->PreparePhoto(p->view, other_view, false);

    // Make the photo in the event/conversation view invisible to avoid a
    // ghosting effect.
    transition_->FadeInAlpha(other_view);
  }
}

- (bool)animateTransitionCommit {
  // LOG("photo: animate from view controller");
  if (!transition_.get()) {
    return false;
  }

  transition_->Commit();
  return true;
}

- (void)rotatePrepare {
  // Remember the current photo/group in preparation for interface rotation.
  CachedPhoto* const p = [self currentCachedPhoto];
  if (p) {
    controller_state_.current_photo = p->view;
  }
  // Disable scroll delegate callbacks during rotation.
  scroll_view_.delegate = NULL;
}

- (void)rotateCommit:(float)duration {
  // Resizes the scroll view.
  [self initContentSize];
  // Set the scroll position which was saved in rotatePrepare.
  [self initContentPosition];
  [self initEventMargins];
  // Set frames for header & navbar.
  [self viewDidLayoutSubviews];
  // Reset the scroll delegate now that rotation is committing.
  scroll_view_.delegate = self;

  // Loop over all of the cached photos and reset their scroll view and photo
  // view frames.
  for (PhotoCacheMap::iterator iter(photo_cache_.begin());
       iter != photo_cache_.end();
       ++iter) {
    CachedPhoto* p = &iter->second;
    // Save the current scroll offset as a normalized position within the photo
    // (i.e. the center is represented as <0.5,0.5>).
    const CGPoint c = {
      CGRectGetMidX(p->scroll_view.bounds) / p->scroll_view.contentSize.width,
      CGRectGetMidY(p->scroll_view.bounds) / p->scroll_view.contentSize.height
    };
    // Save the zoom scale.
    const float saved_scale = p->scroll_view.zoomScale;
    p->scroll_view.zoomScale = 1;
    p->scroll_view.frame = [self photoBounds:p->index];
    p->view.frame = AspectFit(self.layoutBounds.size, p->view.aspectRatio);
    [self photoInitZoom:p];
    p->scroll_view.contentSize = p->view.frame.size;
    // Restore the zoom scale.
    p->scroll_view.zoomScale = saved_scale;
    // Restore the scroll offset.
    p->scroll_view.contentOffset = CGPointMake(
      ClampContentOffset(p->scroll_view.contentSize.width * c.x -
                         p->scroll_view.bounds.size.width / 2,
                         p->scroll_view.contentSize.width,
                         p->scroll_view.bounds.size.width),
      ClampContentOffset(p->scroll_view.contentSize.height * c.y -
                         p->scroll_view.bounds.size.height / 2,
                         p->scroll_view.contentSize.height,
                         p->scroll_view.bounds.size.height));
    [self photoDidZoom:p];

    const CGSize s = header_.frame.size;
    p->title.frame = CGRectMake(
        p->scroll_view.frame.origin.x + 8, 0, s.width - 16, s.height);
  }
}

- (void)scrollViewDidScroll:(UIScrollView*)scroll_view {
  if (self.numPhotos == 0) {
    return;
  }

  if (scroll_view == scroll_view_) {
    // If clamp to vertical is true, disallow horizontal offsets;
    // otherwise, disallow vertical offsets.
    if (clamp_scroll_ == CLAMP_SCROLL_VERTICAL) {
      scroll_view.contentOffset = CGPointMake(start_scroll_offset_.x,
                                              scroll_view.contentOffsetY);
    } else if (clamp_scroll_ == CLAMP_SCROLL_HORIZONTAL) {
      scroll_view.contentOffset = CGPointMake(scroll_view.contentOffsetX,
                                              start_scroll_offset_.y);
    }

    // The header title view scrolls in sync with the main scroll view.
    header_.titleView.contentOffset = CGPointMake(scroll_view.contentOffsetX, 0);
    visible_photos_ = [self photoRange:self.visibleBounds];
    cache_photos_ = [self photoRange:self.cacheBounds];
    // LOG("photo: view did scroll: %d-%d  %d-%d: %.0f",
    //     visible_photos_.first, visible_photos_.second,
    //     cache_photos_.first, cache_photos_.second,
    //     scroll_view.contentOffset);

    [self hidePhotos:cache_photos_];
    [self showPhotos:cache_photos_];
    [self unzoomPhotos:visible_photos_];

    const int visible = [self visiblePhoto:self.visibleBounds];
    const int64_t photo_id = [self photoIndexToId:visible];
    CachedPhoto* const p = FindPtrOrNull(&photo_cache_, photo_id);
    if (p && visible != last_visible_) {
      if (controller_state_.current_photo.photoId != p->view.photoId) {
        last_visible_ = visible;
        paged_ = true;
        controller_state_.current_photo = p->view;
        // Set the current episode so that popping the view controller will
        // cause the event controller to show the correct event.
        controller_state_.current_episode = p->view.episodeId;
      }
      state_->analytics()->PhotoPage(controller_state_.current_photo.photoId);
    }

    // Potentially fade out the title and navbar if we're in the
    // process of dragging the photo vertically to dismiss it and
    // return to previous controller view.
    const float dismiss_offset = [self getDismissOffset];
    const float alpha = std::max<float>(0, 1.0 - fabs(dismiss_offset) / 2);
    options_.alpha = alpha;
    header_.alpha = alpha;
    navbar_.alpha = alpha;
  }

  // Load any higher-res versions of photos that are necessary 100ms after the
  // most recent scroll.
  state_->photo_loader()->LoadPhotosDelayed(0.1, &photo_queue_);
}

- (void)scrollViewWillBeginDragging:(UIScrollView*)scroll_view {
  CachedPhoto* const p = [self currentCachedPhoto];
  const bool cur_photo_zoomed = p && p->scroll_view.zoomScale > 1;
  scroll_view_.alwaysBounceVertical = cur_photo_zoomed ? NO : YES;
  clamp_scroll_ = CLAMP_SCROLL_NONE;
  if (scroll_view_ == scroll_view && !cur_photo_zoomed) {
    Vector2f velocity([scroll_view.panGestureRecognizer velocityInView:scroll_view]);
    velocity.normalize();
    const float dotprod = velocity.dot(Vector2f(1, 0));
    const float angle = acos(dotprod);
    // If the angle of velocity from the vertical exceeds the min for
    // paging, force paging by disallowing vertical scroll.
    if (fabs(angle - kPi / 2) < kMinRadiansFromVerticalForPaging) {
      clamp_scroll_ = CLAMP_SCROLL_VERTICAL;
    } else {
      clamp_scroll_ = CLAMP_SCROLL_HORIZONTAL;
    }
    start_scroll_offset_ = scroll_view_.contentOffset;
  }
}

- (float)getDismissOffset {
  if (clamp_scroll_ == CLAMP_SCROLL_VERTICAL) {
    return fabs(scroll_view_.contentOffsetY / kDragToExitThreshold);
  }
  return 0;
}

- (void)scrollViewDidEndDragging:(UIScrollView*)scroll_view
                  willDecelerate:(BOOL)decelerate {
  if (!decelerate) {
    [self scrollViewDidEndDecelerating:scroll_view];
  }
  const float dismiss_offset = [self getDismissOffset];
  if (fabs(dismiss_offset) >= 1) {
    state_->analytics()->PhotoSwipeDismiss();
    [self photoOptionsClose];
  }
}

- (void)scrollViewDidEndDecelerating:(UIScrollView*)scroll_view {
  // LOG("photo: view did end decelerating");
  state_->photo_loader()->LoadPhotos(&photo_queue_);

  // If setting the index modifies the underlying photo_ids array, we need to
  // reset the scroll view. This happens in case the layout view which supplied
  // the current photos iterator allows paging to photos beyond the initial
  // selection (e.g. other events).
  if (scroll_view_ == scroll_view &&
      controller_state_.current_photos.SetIndex(visible_photos_.first)) {
    [self rebuildPhotoViewMap];
    [self clearPhotoCache];
    [self viewWillAppear:NO];
  }
  clamp_scroll_ = CLAMP_SCROLL_NONE;
  [self maybeRebuild];
}

- (UIView*)viewForZoomingInScrollView:(UIScrollView*)scroll_view {
  if (scroll_view == scroll_view_) {
    return NULL;
  }
  CachedPhoto* p = FindPtrOrNull(
      &photo_cache_, [self photoIndexToId:scroll_view.tag]);
  if (!p) {
    // Huh? How did this happen? The scroll view tag should be our photo index.
    return NULL;
  }
  return p->view;
}

- (void)scrollViewDidZoom:(UIScrollView*)scroll_view {
  if (scroll_view == scroll_view_) {
    return;
  }
  CachedPhoto* p = FindPtrOrNull(
      &photo_cache_, [self photoIndexToId:scroll_view.tag]);
  if (!p) {
    // Huh? How did this happen? The scroll view tag should be our photo index.
    return;
  }
  [self photoDidZoom:p];
  if (p->scroll_view.zoomScale != 1) {
    state_->analytics()->PhotoZoom();
  }
}

- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer*)recognizer {
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

@end  // PhotoLayoutController

LayoutController* NewPhotoLayoutController(UIAppState* state) {
  return [[PhotoLayoutController alloc] initWithState:state];
}
