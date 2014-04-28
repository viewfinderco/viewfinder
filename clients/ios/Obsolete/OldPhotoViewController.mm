// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.
//
// TODO(pmattis): Lazily create the various toolbars and controls.
//
// TODO(pmattis): Disable the unshare button if no unsharable photos are
// selected (i.e. the selected photos have not been shared).
//
// TODO(pmattis): The whole AsyncState mechanism is fragile. Find a better way.
//
// class PhotoLayout {
//  public:
// };
//
// class IndividualPhotoLayout : public PhotoLayout {
//  public:
//    virtual int MinGroupForRect(const CGRect& f);
//    virtual int MaxGroupForRect(const CGRect& f);
//    virtual CGRect CacheBoundsForRect(const CGRect& f);
//    virtual GroupLayoutData* InitGroup(int index);
//    virtual void InitGroupView(GroupLayoutData* g);
//    virtual void UpdateBounds();
//    virtual void GroupDidZoom();
//    virtual void LayoutInternal();
//    virtual void ShowActionControls();
//    virtual void SwipeLeft();
//    virtual void SwipeRight();
// };
//
// class SummaryEventLayout : public PhotoLayout {
//  public:
//    virtual int MinGroupForRect(const CGRect& f);
//    virtual int MaxGroupForRect(const CGRect& f);
//    virtual CGRect CacheBoundsForRect(const CGRect& f);
//    virtual GroupLayoutData* InitGroup(int index);
//    virtual void InitGroupView(GroupLayoutData* g);
//    virtual void LayoutInternal();
//    virtual void ShowActionControls();
//    virtual void HideActionControls();
//    virtual void SwipeLeft();
//    virtual void SwipeRight();
// };
//
// class DetailedEventLayout : public PhotoLayout {
//  public:
//    virtual int MinGroupForRect(const CGRect& f);
//    virtual int MaxGroupForRect(const CGRect& f);
//    virtual CGRect CacheBoundsForRect(const CGRect& f);
//    virtual GroupLayoutData* InitGroup(int index);
//    virtual void InitGroupView(GroupLayoutData* g);
//    virtual void LayoutInternal();
//    virtual void ShowActionControls();
//    virtual void HideActionControls();
//    virtual void SwipeLeft();
//    virtual void SwipeRight();
// };

#import <algorithm>
#import <tr1/unordered_set>
#import <tr1/unordered_map>
#import <QuartzCore/QuartzCore.h>
#import "Appearance.h"
#import "AppState.h"
#import "AssetsManager.h"
#import "ContactPicker.h"
#import "DB.h"
#import "Image.h"
#import "Logging.h"
#import "Matrix.h"
#import "MKNumberBadgeView.h"
#import "Mutex.h"
#import "NetworkManager.h"
#import "TileLayout.h"
#import "PhotoManager.h"
#import "PhotoMetadata.pb.h"
#import "PhotoView.h"
#import "OldPhotoViewController.h"
#import "RootViewController.h"
#import "STLUtils.h"
#import "StringUtils.h"
#import "Timer.h"
#import "ViewfinderTool.h"

namespace {

typedef std::tr1::unordered_set<PhotoLayoutData*> SelectionSet;
typedef std::tr1::unordered_map<int64_t, PhotoLayoutData*> PhotoLayoutMap;
typedef std::tr1::unordered_map<int64_t, EventLayoutData*> EventLayoutMap;
typedef std::tr1::unordered_map<int, GroupLayoutData*> GroupLayoutMap;

typedef void (^ScopedCallback)();

const string kAnimationScaleKey = DBFormat::metadata_key("photo_animation_scale");

}  // namespace

@interface OldPhotoViewController (internal)
- (void)handleSingleTap:(UITapGestureRecognizer*)recognizer;
- (void)handleDoubleTap:(UITapGestureRecognizer*)recognizer;
- (void)handleSwipeLeft:(UISwipeGestureRecognizer*)recognizer;
- (void)handleSwipeRight:(UISwipeGestureRecognizer*)recognizer;
- (PhotoLayoutData*)findPhotoAtPoint:(CGPoint)p;
- (void)initLayout;
- (void)reloadPhotos;
- (void)assetLoadingProgress:(int)progress;
- (void)assetLoadingStop;
- (void)networkLoadingStart:(float)delay;
- (void)networkLoadingStop;
- (void)updateStatus;
- (void)statusMessage:(const string)message
             autohide:(bool)autohide;
- (void)statusAutoHide:(const int64_t)status_id;
- (void)popLayout;
- (void)showActionControls;
- (void)hideActionControls;
- (void)showEditingControls;
- (void)savePhotoEdits;
- (void)sharePhotosStart;
- (void)sharePhotosFinish;
- (void)unsharePhotosConfirm:(id)sender;
- (void)unsharePhotosFinish;
- (void)deletePhotosConfirm:(id)sender;
- (void)deletePhotosFinish;
- (void)viewfinderBegin;
- (void)viewfinderEnd;
- (void)viewfinderCancel;
- (void)viewfinderUpdate;
@end  // OldPhotoViewController (internal)

struct PhotoLayoutEnv {
  PhotoLayoutEnv(AppState* state,
                 OldPhotoViewController* self)
      : state(state),
        self(self),
        load_thumbnail_in_progress(0),
        load_in_progress(0),
        visible_bounds(CGRectZero),
        cache_bounds(CGRectZero),
        num_photos(0),
        num_groups(0),
        min_visible_group(-1),
        max_visible_group(-1),
        min_cache_group(-1),
        max_cache_group(-1),
        photo_shadows(true),
        photo_borders(true),
        show_toolbar(false),
        show_tabbar(true),
        show_status(true),
        animation_scale(state->db()->Get<float>(kAnimationScaleKey, 1.75)),
        next_status_id(0),
        status_autohide(false) {
  }
  ~PhotoLayoutEnv() {
    Clear(&photo_cache);
    Clear(&group_cache);
    Clear(&events);
    Clear(&recycled_photo_views);
    Clear(&recycled_scroll_views);
  }

  void Reset() {
    Clear(&photo_cache);
    Clear(&group_cache);
    Clear(&recycled_photo_views);
    Clear(&recycled_scroll_views);
    refresh_header = NULL;
    refresh_label = NULL;
    refresh_sublabel = NULL;
    refresh_arrow = NULL;
    refresh_spinner = NULL;
    scroll_view_background = NULL;
    scroll_view = NULL;
    content_view = NULL;
    status_label = NULL;
    toolbar = NULL;
    toolbar_title_view = NULL;
    action_bar = NULL;
    single_tap_recognizer = NULL;
    double_tap_recognizer = NULL;
    swipe_left_recognizer = NULL;
    swipe_right_recognizer = NULL;
    viewfinder_tool = NULL;
    contact_picker = NULL;
    toolbar_view_items.reset(NULL);
    toolbar_action_items.reset(NULL);
    toolbar_editing_items.reset(NULL);
    toolbar_share_items.reset(NULL);
    toolbar_editing_label = NULL;
    action_bar_event_items.reset(NULL);
    action_bar_photo_items.reset(NULL);
    action_bar_editing_items.reset(NULL);
  }

  void UpdateAnimationScale() {
    if (animation_scale > 1.0) {
      animation_scale = std::max<float>(1.0, animation_scale * 0.95);
      state->db()->Put(kAnimationScaleKey, animation_scale);
    }
  }

  bool editing() const {
    return !action_bar.hidden;
  }

  AppState* const state;
  OldPhotoViewController* const self;
  UIView* refresh_header;
  UILabel* refresh_label;
  UILabel* refresh_sublabel;
  UIImageView* refresh_arrow;
  UIActivityIndicatorView* refresh_spinner;
  UIColor* scroll_view_background;
  UIScrollView* scroll_view;
  UIView* content_view;
  UIView* content_overlay;
  UILabel* status_label;
  UIToolbar* toolbar;
  UIScrollView* toolbar_title_view;
  UIToolbar* action_bar;
  UITapGestureRecognizer* single_tap_recognizer;
  UITapGestureRecognizer* double_tap_recognizer;
  UISwipeGestureRecognizer* swipe_left_recognizer;
  UISwipeGestureRecognizer* swipe_right_recognizer;
  ViewfinderTool* viewfinder_tool;
  ContactPicker* contact_picker;
  Array toolbar_view_items;
  Array toolbar_action_items;
  Array toolbar_editing_items;
  Array toolbar_share_items;
  UILabel* toolbar_editing_label;
  Array action_bar_event_items;
  Array action_bar_photo_items;
  Array action_bar_editing_items;
  PhotoLayoutMap photo_cache;
  GroupLayoutMap group_cache;
  std::vector<EventLayoutData*> events;
  std::vector<PhotoView*> recycled_photo_views;
  std::vector<UIScrollView*> recycled_scroll_views;
  SelectionSet selection;
  Mutex load_mu;
  int load_thumbnail_in_progress;
  int load_in_progress;
  CGRect visible_bounds;
  CGRect cache_bounds;
  int num_photos;
  int num_groups;
  int min_visible_group;
  int max_visible_group;
  int min_cache_group;
  int max_cache_group;
  bool photo_shadows;
  bool photo_borders;
  bool show_toolbar;
  bool show_tabbar;
  bool show_status;
  float animation_scale;
  int64_t next_status_id;
  bool status_autohide;
};

class PhotoLayout {
 public:
  typedef PhotoLayoutEnv Env;

 public:
  virtual ~PhotoLayout() { }
  virtual void Layout(int64_t target_photo, bool animated,
                      void (^completion)() = NULL) = 0;
  virtual void UpdateBounds() = 0;
  virtual void RecyclePhotoView(PhotoView* view) = 0;
  virtual void MaybeShowPhotos() = 0;
  virtual void MaybeHidePhotos() = 0;
  virtual void MaybeLoadPhotos() = 0;
  virtual void EnterFullScreen(float duration) = 0;
  virtual void ExitFullScreen(float duration) = 0;
  virtual void ShowToolbar(float duration) = 0;
  virtual void HideToolbar(float duration, bool hide_action_controls = true) = 0;
  virtual void ToggleToolbar(float duration) = 0;
  virtual void ShowActionControls(float duration) = 0;
  virtual void HideActionControls(float duration) = 0;
  virtual void UpdateActionControls() = 0;
  virtual void ShowShareControls(float duration) = 0;
  virtual void ShowEditingControls(float duration) = 0;
  virtual void TogglePhoto(PhotoLayoutData* d) = 0;
  virtual void SwipeLeft(PhotoLayoutData* d) = 0;
  virtual void SwipeRight(PhotoLayoutData* d) = 0;
  virtual void GroupDidZoom(GroupLayoutData* g, bool toolbar_hidden) = 0;
};

namespace {

const float kRefreshHeaderHeight = 36;
const float kThumbnailSpacing = 3;
const float kEventSpacing = 10;
const float kPhotoSpacing = 20;
const float kLabelOriginX = kThumbnailSpacing + kThumbnailBorder * 2;
const float kDuration = 0.3;

const string kDetailedModeKey = DBFormat::metadata_key("detailed_mode");
const string kIndividualModeKey = DBFormat::metadata_key("individual_mode");

LazyStaticRgbColor kPhotoGroupTitleShadowColor = { Vector4f(0, 0, 0, 1) };
LazyStaticRgbColor kPhotoGroupLabelTextColor = { Vector4f(0, 0, 0, 0.7) };
LazyStaticRgbColor kPhotoGroupLabelShadowColor = { Vector4f(1, 1, 1, 1) };

LazyStaticRgbColor kThumbnailPrivateColor = { Vector4f(0.5, 0, 0, 1) };
LazyStaticRgbColor kThumbnailPublicColor = { Vector4f(0, 0.5, 0, 1) };
LazyStaticRgbColor kThumbnailSharedColor = { Vector4f(0, 0, 0.5, 1) };

LazyStaticFont kPhotoGroupLabelFont = { kHelveticaMedium, 12 };
LazyStaticFont kPhotoGroupTitleFont = { kHelveticaMedium, 12 };
LazyStaticFont kPhotoRefreshLabelFont = { kHelveticaMedium, 12 };
LazyStaticFont kPhotoRefreshSublabelFont = { kHelvetica, 12 };

// A marker used to indicate a thumbnail is being loaded.
Image* kThumbnailLoadingMarker = (Image*)0x1;

NSString* kTextPull = @"Pull down to refresh...";
NSString* kTextRelease = @"Release to refresh...";
NSString* kTextLoading = @"Loading...";
NSString* kTextNetworkDown = @"No network connection";
NSString* kTextNotSignedIn = @"Not signed in";

float ScaleFactor(const CGSize& screen_size, const CGSize& image_size) {
  if (image_size.width < 0) {
    // The image is uninitialized, pretend the scale factor is 1.
    return 1.0;
  }
  return screen_size.width / image_size.width;
}

struct EventByTimestamp {
  bool operator()(const EventLayoutData* a,
                  const EventLayoutData* b) const {
    if (!a || !b) {
      // Sort NULL pointers to the end.
      return a > b;
    }
    if (a->timestamp != b->timestamp) {
      return a->timestamp > b->timestamp;
    }
    // Distinguish identical timestamps by pointer comparison.
    return a > b;
  }
};

class PhotoLayoutBase : public PhotoLayout {
  typedef std::tr1::unordered_map<PhotoLayoutData*, ScopedCallback> GeocodeQueue;

protected:
  struct AsyncState {
    AsyncState()
        : inflight(0),
          alive(true) {
    }
    int inflight;
    bool alive;
  };

 public:
  struct LayoutData {
    LayoutData(int64_t t)
        : target_photo(t),
          content_width(0),
          content_height(0),
          scroll_size(CGSizeMake(0, 0)),
          scroll_delta(CGPointMake(0, 0)),
          scroll_background(NULL),
          photo_shadows(true),
          photo_borders(true),
          show_toolbar(false),
          show_tabbar(true),
          show_status(true),
          content_overlay_alpha(0) {
    }
    ~LayoutData() {
      Clear(&old_labels);
    }

    WallTimer timer;
    const int64_t target_photo;
    std::tr1::unordered_map<int64_t, int> photo_to_group;
    std::tr1::unordered_map<PhotoLayoutData*, CGRect> old_photo_frame;
    std::vector<UIView*> old_labels;
    float content_width;
    float content_height;
    CGSize scroll_size;
    CGPoint scroll_delta;
    UIColor* scroll_background;
    bool photo_shadows;
    bool photo_borders;
    bool show_toolbar;
    bool show_tabbar;
    bool show_status;
    float content_overlay_alpha;
  };

 public:
  PhotoLayoutBase(Env* env)
      : env_(env),
        state_(env->state),
        async_state_(new AsyncState),
        scroll_view_(env->scroll_view),
        content_view_(env->content_view),
        photo_cache_(env->photo_cache),
        group_cache_(env->group_cache),
        events_(env->events),
        recycled_photo_views_(env->recycled_photo_views),
        recycled_scroll_views_(env->recycled_scroll_views),
        num_photos_(env->num_photos),
        num_groups_(env->num_groups),
        min_visible_group_(env->min_visible_group),
        max_visible_group_(env->max_visible_group),
        min_cache_group_(env->min_cache_group),
        max_cache_group_(env->max_cache_group),
        photo_shadows_(env->photo_shadows),
        photo_borders_(env->photo_borders),
        geocode_in_progress_(0) {
    AsyncStateEnter(async_state_);
  }
  ~PhotoLayoutBase() {
    async_state_->alive = false;
    AsyncStateLeave(async_state_);
  }

 protected:
  virtual int MinGroupForRect(const CGRect& f) = 0;
  virtual int MaxGroupForRect(const CGRect& f) = 0;
  virtual CGRect CacheBoundsForRect(const CGRect& f) = 0;

  void UpdateBounds() {
    // Convert the visible bounds rect into the content coordinate system.
    env_->visible_bounds = [scroll_view_ bounds];
    env_->cache_bounds = CacheBoundsForRect(env_->visible_bounds);

    const CGRect visible = [content_view_ convertRect:env_->visible_bounds
                                             fromView:scroll_view_];
    const CGRect cache = [content_view_ convertRect:env_->cache_bounds
                                           fromView:scroll_view_];

    min_visible_group_ = MinGroupForRect(visible);
    max_visible_group_ = MaxGroupForRect(visible);
    min_cache_group_ = MinGroupForRect(cache);
    max_cache_group_ = MaxGroupForRect(cache);

    // LOG("photo: update bounds: %d-%d %d-%d",
    //     min_visible_group_, max_visible_group_,
    //     min_cache_group_, max_cache_group_);
  }

  void RecyclePhotoView(PhotoView* view) {
    CHECK(view != NULL);
    [view setPhoto:NULL];
    [view setImage:NULL];
    [view removeFromSuperview];
    [view layer].zPosition = 0;
    [view setTransform:CGAffineTransformIdentity];
    recycled_photo_views_.push_back(view);
  }

  void RecycleScrollView(UIScrollView* view) {
    CHECK(view != NULL);
    [view setDelegate:NULL];
    [view removeFromSuperview];
    [view layer].zPosition = 0;
    recycled_scroll_views_.push_back(view);
  }

  PhotoLayoutData* FindPhoto(int64_t photo_id) {
    PhotoLayoutData*& d = photo_cache_[photo_id];
    if (!d) {
      const PhotoManager::PhotoData* p = FindPtrOrNull(
          state_->photo_manager()->photos(), photo_id);
      if (p) {
        d = new PhotoLayoutData(p->metadata);
      } else {
        // Photo no longer exists, initialize a dummy PhotoLayoutData.
        PhotoMetadata m;
        m.mutable_id()->set_local_id(photo_id);
        m.set_aspect_ratio(1);
        d = new PhotoLayoutData(m);
      }
    }
    return d;
  }

  GroupLayoutData* FindGroup(int index) {
    CHECK_LT(index, num_groups_);
    GroupLayoutData*& g = group_cache_[index];
    if (!g) {
      g = InitGroup(index);
    }
    return g;
  }

  virtual GroupLayoutData* InitGroup(int index) = 0;

  // Called to initialize the view for a group in a layout specified manner.
  virtual void InitGroupView(GroupLayoutData* g) = 0;

  void InitGroupTitle(GroupLayoutData* g, bool show_count, bool show_index) {
    CHECK_GT(g->photos.size(), 0);

    PhotoLayoutData* d = g->photos.front();
    EventLayoutData* e = g->event;
    string labels[2];
    int count = 0;
    labels[count++] =
        Format("%s", WallTimeFormat("%B %e, %Y", d->timestamp));

    if (state_->photo_manager()->FormatLocation(d->photo_id, &labels[count])) {
      ++count;
    } else {
      MaybeReverseGeocode(d, ^{
          GroupLayoutData* g = d->group;
          if (g->view) {
            InitGroupTitle(g, show_count, show_index);
          }
        });
    }

    UIView* view = [UIView new];
    CGSize size = [env_->toolbar_title_view frame].size;
    [view setFrame:CGRectMake(
          g->frame.origin.x, 0, size.width, size.height)];

    UIFont* font = kPhotoGroupTitleFont;

    if (show_count || show_index) {
      string s;
      if (show_index) {
        const int index =
            std::find(e->photos.begin(), e->photos.end(), d->photo_id) -
            e->photos.begin();
        s += Format("%d", index + 1);
      }
      if (show_count) {
        if (show_index) {
          s += "/";
        }
        s += Format("%d", e->photos.size());
      }
      UILabel* label = MakeTitleLabel(s, font);
      [label sizeToFit];
      CGRect f = CGRectInset([label frame], -4, 0);
      f.origin.x = size.width - f.size.width;
      f.origin.y = 1 + (size.height - f.size.height) / 2;
      [label setBackgroundColor:[UIColor whiteColor]];
      [label setTextColor:[UIColor clearColor]];
      [label layer].cornerRadius = 2;
      [label setFrame:f];
      size.width = f.origin.x - 4;
      [view addSubview:label];
    }

    float y = (size.height - (2 * font.lineHeight + 2)) / 2;
    for (int i = 0; i < count; ++i) {
      UILabel* label = MakeTitleLabel(labels[i], font);
      [label setFrame:CGRectMake(0, y, size.width, font.lineHeight)];
      [view addSubview:label];
      y += font.lineHeight + 2;
    }

    [g->title removeFromSuperview];
    g->title = view;
    [env_->toolbar_title_view addSubview:g->title];
  }

  static UILabel* MakeTitleLabel(const string& s, UIFont* font) {
    NSString* text = NewNSString(s);
    UILabel* label = [UILabel new];
    [label setFont:font];
    [label setText:text];
    [label setTextColor:[UIColor whiteColor]];
    [label setTextAlignment:UITextAlignmentCenter];
    [label setLineBreakMode:UILineBreakModeMiddleTruncation];
    [label setBackgroundColor:[UIColor clearColor]];
    [label setShadowColor:kPhotoGroupTitleShadowColor];
    [label setShadowOffset:CGSizeMake(0, -0.5)];
    return label;
  }

  void MaybeShowGroup(GroupLayoutData* g, bool force = false) {
    if (g->view) {
      return;
    }
    if (!force &&
        (g->index < min_cache_group_ || g->index > max_cache_group_)) {
      return;
    }

    UIScrollView* view = NULL;
    if (!recycled_scroll_views_.empty()) {
      view = recycled_scroll_views_.back();
      CHECK(view != NULL);
      recycled_scroll_views_.pop_back();
    } else {
      view = [[UIScrollView alloc] initWithFrame:CGRectZero];
      view.clipsToBounds = NO;
      view.canCancelContentTouches = NO;
    }

    g->view = view;
    [g->view setTag:g->index];
    InitGroupView(g);
    view.delegate = env_->self;
    [content_view_ insertSubview:g->view atIndex:0];
  }

  void MaybeHideGroup(GroupLayoutData* g) {
    if (!g->view ||
        (g->index >= min_cache_group_ && g->index <= max_cache_group_)) {
      return;
    }
    RecycleScrollView(g->view);
    g->view = NULL;
    [g->title removeFromSuperview];
    g->title = NULL;
    [g->label removeFromSuperview];
    g->label = NULL;
  }

  void MaybeDestroyGroup(GroupLayoutData* g) {
    if (g->view) {
      return;
    }
    for (int i = 0; i < g->photos.size(); ++i) {
      if (g->photos[i]->view) {
        return;
      }
    }

    for (int i = 0; i < g->photos.size(); ++i) {
      PhotoLayoutData* d = g->photos[i];
      photo_cache_.erase(d->photo_id);
    }
    group_cache_.erase(g->index);
  }

  void MaybeShowPhotos() {
    // Show all photos within the cache bounds.
    for (int group = min_cache_group_; group <= max_cache_group_; ++group) {
      GroupLayoutData* g = FindGroup(group);
      for (int i = 0; i < g->photos.size(); ++i) {
        PhotoLayoutData* d = g->photos[i];
        MaybeShowPhoto(d);
      }
    }

    MaybeLoadThumbnails();
    WaitVisibleThumbnails(0.005);
  }

  void MaybeShowPhoto(PhotoLayoutData* d) {
    if (d->view) {
      return;
    }
    GroupLayoutData* g = d->group;
    MaybeShowGroup(g);
    if (!g->view ||
        g->index < min_cache_group_ || g->index > max_cache_group_) {
      return;
    }

    CGRect f = [scroll_view_ convertRect:d->frame fromView:g->view];
    if (!CGRectIntersectsRect(env_->cache_bounds, f)) {
      // LOG("  not showing: %s: %.3f %.3f %.3f",
      //     d->photo_id, env_->cache_bounds, f, [g->view frame]);
      return;
    }

    // LOG("photo: showing %s: %.3f %.3f", d->photo_id, env_->cache_bounds, f);
    PhotoView* view = NULL;
    if (!recycled_photo_views_.empty()) {
      view = recycled_photo_views_.back();
      CHECK(view != NULL);
      recycled_photo_views_.pop_back();
    } else {
      view = [PhotoView new];
    }
    d->view = view;
    [d->view setPhoto:d];
    [d->view setAspectRatio:d->aspect_ratio];
    [d->view setSelected:ContainsKey(env_->selection, d)];
    [d->view setShadowColor:kThumbnailShadowColor];
    [d->view setShadowOffset:kThumbnailShadowOffset];
    [d->view animateToFrame:d->frame
                     shadow:photo_shadows_
                     border:photo_borders_
                   duration:0];

    for (int i = 0; i < g->photos.size(); ++i) {
      if (g->photos[i] != d) {
        continue;
      }
      for (int j = i - 1; j >= 0; --j) {
        if (g->photos[j]->view) {
          [g->view insertSubview:view aboveSubview:g->photos[j]->view];
          return;
        }
      }
      for (int j = i + 1; j < g->photos.size(); ++j) {
        if (g->photos[j]->view) {
          [g->view insertSubview:view belowSubview:g->photos[j]->view];
          return;
        }
      }
      break;
    }

    [g->view insertSubview:view atIndex:0];
  }

  void MaybeHidePhotos() {
    for (UIView* v in [content_view_ subviews]) {
      if (![v isKindOfClass:[UIScrollView class]]) {
        continue;
      }
      for (PhotoView* u in [v subviews]) {
        if (![u isKindOfClass:[PhotoView class]]) {
          continue;
        }
        MaybeHidePhoto(u.photo);
      }
      GroupLayoutData* g = FindOrNull(group_cache_, v.tag);
      if (g) {
        MaybeHideGroup(g);
        MaybeDestroyGroup(g);
      }
    }
  }

  void MaybeHidePhoto(PhotoLayoutData* d) {
    if (!d->view) {
      MaybeDestroyGroup(d->group);
      return;
    }
    CHECK(d->group);

    GroupLayoutData* g = d->group;
    MaybeHideGroup(g);

    if (g->index >= min_cache_group_ && g->index <= max_cache_group_) {
      // If the group is visible, check for visibility of the photo. If the
      // group has already been hidden, the photo is definitely invisible.
      CGRect f = [scroll_view_ convertRect:[d->view frame]
                                  fromView:g->view];
      if (CGRectIntersectsRect(env_->cache_bounds, f)) {
        return;
      }
      // LOG("photo: hiding %s: %.0f %.0f", d->photo_id, env_->cache_bounds, f);
    } else {
      // LOG("photo: hiding %s (group hidden)", d->photo_id);
    }

    if (d->thumbnail != kThumbnailLoadingMarker) {
      // Delete any loaded but unset thumbnail.
      delete d->thumbnail;
      d->thumbnail = NULL;
    }

    RecyclePhotoView(d->view);
    d->view = NULL;
    d->load_size = CGSizeZero;

    // TODO(pmattis): Investigate segfault.
    MaybeDestroyGroup(g);
  }

  void MaybeLoadThumbnails() {
    MutexLock l(&env_->load_mu);
    // Initiate loading of thumbnails for visible photos first.
    MaybeLoadVisibleThumbnailsLocked();
    // Then initiated loading of thumbnails for cached photos.
    MaybeLoadCacheThumbnailsLocked();
  }

  void MaybeLoadVisibleThumbnailsLocked() {
    for (int group = min_visible_group_; group <= max_visible_group_; ++group) {
      GroupLayoutData* g = FindGroup(group);
      for (int i = 0; i < g->photos.size(); ++i) {
        PhotoLayoutData* d = g->photos[i];
        MaybeLoadThumbnailLocked(d, true);
      }
    }
  }

  void MaybeLoadCacheThumbnailsLocked() {
    for (int group = min_cache_group_;
         env_->load_thumbnail_in_progress < 2 &&
         group <= max_cache_group_;
         ++group) {
      GroupLayoutData* g = FindGroup(group);
      for (int i = 0; i < g->photos.size(); ++i) {
        PhotoLayoutData* d = g->photos[i];
        MaybeLoadThumbnailLocked(d, false);
      }
    }
  }

  void WaitVisibleThumbnails(double delay) {
    WallTimer timer;

    // Wait for any thumbnails within the visible bounds to load.
    std::vector<PhotoLayoutData*> loading;
    for (int group = min_visible_group_; group <= max_visible_group_; ++group) {
      GroupLayoutData* g = FindGroup(group);
      for (int i = 0; i < g->photos.size(); ++i) {
        PhotoLayoutData* d = g->photos[i];
        if (!d->view) {
          // The photo isn't visible, ignore for loading.
          continue;
        }
        if (![d->view image]) {
          // The photo is currently being (or has been) loaded. Add it to the
          // list of photos we're waiting for.
          loading.push_back(d);
        }
      }
    }
    if (loading.empty()) {
      return;
    }

    // LOG("photo: loading %d images", loading.size());

    {
      // Wait up to "delay" secs (usually 5ms or 0ms) for the visible
      // thumbnails to load.
      MutexLock l(&env_->load_mu);
      env_->load_mu.TimedWait(delay, ^{
          for (int i = 0; i < loading.size(); ++i) {
            PhotoLayoutData* d = loading[i];
            if (!d->thumbnail ||
                d->thumbnail == kThumbnailLoadingMarker) {
              return false;
            }
          }
          return true;
        });
    }

    // Set the loaded thumbnails.
    for (int i = 0; i < loading.size(); ++i) {
      PhotoLayoutData* d = loading[i];
      if (d->thumbnail == kThumbnailLoadingMarker) {
        continue;
      }
      ScopedPtr<Image> image(d->thumbnail);
      d->thumbnail = NULL;
      if (!*image) {
        // Loading failed.
        continue;
      }
      SetPhotoImage(d, *image);
      d->load_size = CGSizeMake(image->pixel_width(), image->pixel_height());
    }

    // LOG("photo: loaded %d images: %.03f ms",
    //     loading.size(), timer.Milliseconds());
  }

  void MaybeLoadThumbnailLocked(PhotoLayoutData* d, bool visible) {
    if (!d->view || [d->view image] || d->thumbnail) {
      return;
    }

    Env* const env = env_;
    if (!visible && env->load_thumbnail_in_progress >= 2) {
      // The photo is not visible on screen and there are too many thumbnail
      // loads in progress.
      return;
    }
    ++env->load_thumbnail_in_progress;

    // A photo without an image gets its thumbnail loaded. We set
    // Image::loading to kThumbnailLoadingMarker while the load is in
    // progress.
    Image* image = new Image;
    d->thumbnail = kThumbnailLoadingMarker;

    PhotoLayoutBase* const layout = this;
    AsyncState* state = async_state_;
    AsyncStateEnter(state);

    state_->photo_manager()->LoadThumbnail(
        d->photo_id, image, ^{
          // Once the load has finished, set the thumbnail image in
          // place. Unlocking the mutex will trigger any waiting
          // conditionals.
          env->load_mu.Lock();
          --env->load_thumbnail_in_progress;
          d->thumbnail = image;
          env->load_mu.Unlock();

          dispatch_main(^{
              if (!AsyncStateLeave(state)) {
                // The layout object has been destroyed. Leave everything
                // alone.
                return;
              }
              layout->MaybeLoadThumbnails();
              layout->WaitVisibleThumbnails(0);
            });
      });
  }

  void MaybeLoadPhotos() {
    if (env_->load_in_progress) {
      return;
    }

    std::vector<std::pair<float, PhotoLayoutData*> > priority_queue;
    for (UIView* v in [content_view_ subviews]) {
      if (![v isKindOfClass:[UIScrollView class]]) {
        continue;
      }
      for (PhotoView* u in [v subviews]) {
        if (![u isKindOfClass:[PhotoView class]]) {
          continue;
        }
        PhotoLayoutData* d = u.photo;
        if (!d) {
          continue;
        }
        const float priority = MaybeLoadPhotoPriority(d);
        if (priority > 0) {
          priority_queue.push_back(std::make_pair(priority, d));
        }
      }
    }

    if (priority_queue.empty()) {
      return;
    }

    std::sort(priority_queue.begin(), priority_queue.end());

    const std::pair<float, PhotoLayoutData*>& p = priority_queue.back();
    PhotoLayoutData* d = p.second;
    // LOG("photo: loading start %s: %.02f", d->photo_id, p.first);

    PhotoLayout* const layout = this;
    Env* const env = env_;
    ++env->load_in_progress;

    AsyncState* state = async_state_;
    AsyncStateEnter(state);

    // This is a bit complicated. We load the photo on a low priority
    // background thread. But while we are waiting for the block to be invoked,
    // "this" could be destroyed. AsyncState{Enter,Leave} is used to notice
    // when "this" is deleted.
    Image* image = new Image;
    env->state->photo_manager()->LoadPhoto(
        d->photo_id, d->frame.size, image, ^{
          // The photo has been loaded (or an error) occurred. Jump back
          // onto the main thread to perform UIKit manipulation.
          dispatch_main(^{
              // LOG("photo: loading done %s", d->photo_id);
              // Mark the load as being finished.
              --env->load_in_progress;
              ScopedPtr<Image> image_deleter(image);
              if (!AsyncStateLeave(state)) {
                // The layout object has been destroyed. Leave everything
                // alone.
                return;
              }
              if (d->view) {
                // The photo is still visible, update the image.
                SetPhotoImage(d, *image);
                d->load_size = d->frame.size;
              }
              // Maybe load another photo.
              layout->MaybeLoadPhotos();
            });
      });
  }

  // Return the visible fraction of rect "f" in rect "b".
  static float VisibleFraction(const CGRect& f, const CGRect& b) {
    const CGRect i = CGRectIntersection(f, b);
    return (i.size.width * i.size.height) /
        (b.size.width * b.size.height);
  }

  float MaybeLoadPhotoPriority(PhotoLayoutData* d) {
    if (d->load_size.width > 0 && d->load_size.height > 0) {
      // The photo already has an image loaded, check to see if it is
      // appropriately scaled.
      const float scale = std::max(
          d->frame.size.width / d->load_size.width,
          d->frame.size.height / d->load_size.height);
      if (scale <= 1.0) {
        // LOG("photo: load scale ok: %s: %.02f", d->photo_id, scale);
        return 0;
      }
    }

    // Prioritize loading of the photo with the most screen overlap.
    GroupLayoutData* g = d->group;
    const CGRect f = [scroll_view_ convertRect:[d->view frame]
                                      fromView:g->view];
    const float visible_fraction = VisibleFraction(f, env_->visible_bounds);
    if (visible_fraction > 0) {
      // The photo is visible on the screen, prioritize loading over off-screen
      // photos.
      // LOG("photo: load priority: %s: %.02f",
      //     d->photo_id, visible_fraction);
      return 1 + visible_fraction;
    }

    const float cache_fraction = VisibleFraction(f, env_->cache_bounds);
    // LOG("photo: load priority: %s: %.02f",
    //     d->photo_id, cache_fraction);
    return cache_fraction;
  }

  static void SetPhotoImage(PhotoLayoutData* d, const Image& image) {
    // TODO(pmattis): Investigate segfault. Presumably "d" could have been
    // deleted here.
    [d->view setImage:image.MakeUIImage()];
  }

  static void AsyncStateEnter(AsyncState* state) {
    ++state->inflight;
  }

  static bool AsyncStateLeave(AsyncState* state) {
    --state->inflight;
    if (!state->alive) {
      // The layout object has been destroyed.
      if (state->inflight == 0) {
        delete state;
      }
      return false;
    }
    return true;
  }

  void MaybeProcessGeocodeQueue() {
    if (geocode_in_progress_) {
      return;
    }

    while (!geocode_queue_.empty()) {
      GeocodeQueue::iterator iter(geocode_queue_.begin());
      PhotoLayoutData* d = iter->first;
      if (!d->group->view) {
        // Skip geocoding the photo if it is no longer visible.
        //
        // TODO(pmattis): Actually calculate the photo's visibility with
        // respect to cache_bounds.
        geocode_queue_.erase(iter);
        continue;
      }
      // LOG("photo: reverse geocoding start: %s", d->photo_id);

      // The AsyncState structure is used to prevent access to "this" after
      // "this" has been destroyed. In the ReverseGeocode() completion block,
      // we're careful to make sure AsyncState::alive is true before
      // accessing any member of "this".
      AsyncState* state = async_state_;
      AsyncStateEnter(state);

      void (^completion)() = iter->second;
      void (^geocode_completion)(bool success) = ^(bool success) {
        // LOG("photo: reverse geocoding done: %s", d->photo_id);
        if (!AsyncStateLeave(state)) {
          // The layout object has been destroyed. Do not attempt to
          // initialize the title.
          return;
        }
        if (success) {
          completion();
        }
        --geocode_in_progress_;
        geocode_queue_.erase(d);
        MaybeProcessGeocodeQueue();
      };

      ++geocode_in_progress_;
      if (state_->photo_manager()->ReverseGeocode(
              d->photo_id, geocode_completion)) {
        break;
      }

      // LOG("photo: reverse geocoding not started: %s", d->photo_id);
      CHECK(AsyncStateLeave(state));
      --geocode_in_progress_;
      geocode_queue_.erase(iter);
    }
  }

  void MaybeReverseGeocode(PhotoLayoutData* d, void (^completion)()) {
    if (!state_->photo_manager()->NeedsReverseGeocode(d->photo_id)) {
      // Photo no longer exists or is already reverse geocoded.
      return;
    }
    ScopedCallback __strong* callback = &geocode_queue_[d];
    if (*callback) {
      // The photo is already queued for reverse geocoding.
      return;
    }
    *callback = [completion copy];
    MaybeProcessGeocodeQueue();
  }

  void EnterFullScreen(float duration) {
    UITabBar* tabbar = env_->state->root_view_controller().tabbar;
    UILabel* status = env_->status_label;
    [UIView animateWithDuration:duration
                          delay:0
                        options:UIViewAnimationOptionBeginFromCurrentState
                     animations:^{
        CGRect f = status.frame;
        f.origin.y = env_->self.view.bounds.size.height;
        status.frame = f;
        f = tabbar.frame;
        f.origin.y = CGRectGetMaxY(status.frame);
        tabbar.frame = f;
      }
                    completion:^(BOOL finished) {
        if (finished) {
          [status setHidden:YES];
        }
      }
     ];
  }

  void ExitFullScreen(float duration) {
    if (env_->show_status && env_->show_tabbar) {
      PhotoLayoutEnv* env = env_;
      UITabBar* tabbar = env_->state->root_view_controller().tabbar;
      UILabel* status = env_->status_label;
      [UIView animateWithDuration:duration
                            delay:0
                          options:UIViewAnimationOptionBeginFromCurrentState
                       animations:^{
          CGRect f = tabbar.frame;
          f.origin.y = env_->self.view.bounds.size.height - f.size.height;
          tabbar.frame = f;
          f = status.frame;
          f.origin.y = tabbar.frame.origin.y - f.size.height;
          status.frame = f;
          [status setHidden:NO];
        }
                      completion:^(BOOL finished) {
          [env->self statusAutoHide:env->next_status_id];
        }
       ];
    }
  }

  void ShowToolbar(float duration) {
    if (env_->toolbar.hidden) {
      EnterFullScreen(duration);

      const CGRect f = [env_->toolbar frame];
      [env_->toolbar setFrame:CGRectMake(
            f.origin.x, -f.size.height, f.size.width, f.size.height)];
      [UIView animateWithDuration:duration
                       animations:^{
          [env_->toolbar setFrame:CGRectMake(
                f.origin.x, 0, f.size.width, f.size.height)];
          [env_->toolbar setHidden:NO];

          for (UIScrollView* v in [content_view_ subviews]) {
            if (![v isKindOfClass:[UIScrollView class]]) {
              continue;
            }
            GroupDidZoom(FindGroup(v.tag), false);
          }
        }];
    }
  }

  void HideToolbar(float duration, bool hide_action_controls = true) {
    if (!env_->toolbar.hidden) {
      PhotoLayoutEnv* env = env_;
      [UIView animateWithDuration:duration
                       animations:^{
          const CGRect f = [env->toolbar frame];
          [env->toolbar setFrame:CGRectMake(
                f.origin.x, -f.size.height, f.size.width, f.size.height)];

          for (UIScrollView* v in [content_view_ subviews]) {
            if (![v isKindOfClass:[UIScrollView class]]) {
              continue;
            }
            GroupDidZoom(FindGroup(v.tag), true);
          }
        }
                      completion:^(BOOL finished) {
          [env->toolbar setHidden:YES];
        }];

      ExitFullScreen(duration);
    }
    if (hide_action_controls) {
      HideActionControls(duration);
    }
  }

  void ToggleToolbar(float duration) {
    if (env_->toolbar.hidden) {
      ShowToolbar(duration);
    } else {
      HideToolbar(duration);
    }
  }

  void ShowActionControls(float duration) {
    duration *= env_->animation_scale;
    if (env_->action_bar.hidden) {
      const CGRect b = [env_->self.parentViewController.view bounds];
      const CGRect f = [env_->action_bar frame];
      [env_->action_bar setFrame:CGRectMake(
            0, b.size.height, f.size.width, f.size.height)];
      [UIView animateWithDuration:duration
                       animations:^{
          [env_->action_bar setHidden:NO];
          [env_->action_bar setFrame:CGRectMake(
                0, b.size.height - f.size.height, f.size.width, f.size.height)];
        }];

      [env_->toolbar setItems:env_->toolbar_action_items animated:YES];
      [env_->double_tap_recognizer setEnabled:NO];
      [env_->swipe_left_recognizer setEnabled:YES];
      [env_->swipe_right_recognizer setEnabled:YES];
      [env_->scroll_view setScrollEnabled:NO];

      UpdateActionControls();

      // Fire off a suggest friends request under the optimistic assumption
      // that the user will want to share a photo. We could be a little bit
      // more cautious and only send the suggest friends when a photo is first
      // selected, but this seems good enough.
      env_->state->net_manager()->SuggestFriends();
    }
  }

  void HideActionControls(float duration) {
    duration *= env_->animation_scale;
    if (!env_->action_bar.hidden) {
      PhotoLayoutEnv* env = env_;
      const CGRect b = [env_->self.parentViewController.view bounds];
      const CGRect f = [env_->action_bar frame];
      [UIView animateWithDuration:duration
                       animations:^{
          [env->action_bar setFrame:CGRectMake(
                0, b.size.height, f.size.width, f.size.height)];
        }
                      completion:^(BOOL finished) {
          [env->action_bar setHidden:YES];
        }];

      [env_->toolbar setItems:env_->toolbar_view_items animated:YES];
      [env_->double_tap_recognizer setEnabled:YES];
      [env_->swipe_left_recognizer setEnabled:NO];
      [env_->swipe_right_recognizer setEnabled:NO];
      [env_->scroll_view setScrollEnabled:YES];

      SelectNone();

      [env_->contact_picker hide];
      [env_->contact_picker removeFromSuperview];
      env_->contact_picker = NULL;
    }
  }

  void UpdateActionControls() {
    const int n = env_->selection.size();
    // Enable/disable the editing controls.
    const bool enabled = n != 0;
    for (UIBarButtonItem* item in [env_->action_bar items]) {
      if (item.action) {
        [item setEnabled:enabled];
      }
    }

    if (n == 0) {
      [env_->toolbar_editing_label setText:@"Select Photos"];
    } else if (env_->contact_picker) {
      [env_->toolbar_editing_label setText:
             Format("Share %d Photo%s", n, Pluralize(n))];
    } else {
      [env_->toolbar_editing_label setText:
             Format("%d Photo%s Selected", n, Pluralize(n))];
    }
  }

  void ShowShareControls(float duration) {
    [env_->toolbar_share_items[0] setEnabled:NO];
    [env_->toolbar setItems:env_->toolbar_share_items animated:YES];
    UpdateActionControls();
  }

  void ShowEditingControls(float duration) {
    [env_->toolbar setItems:env_->toolbar_editing_items animated:YES];
    [env_->action_bar setItems:env_->action_bar_editing_items animated:YES];
  }

  void TogglePhoto(PhotoLayoutData* d) {
    if (!d) {
      return;
    }

    const bool selected = !ContainsKey(env_->selection, d);
    if (selected) {
      env_->selection.insert(d);
    } else {
      env_->selection.erase(d);
    }
    [d->view setSelected:selected];

    UpdateActionControls();
  }

  void SelectAll() {
    if (min_visible_group_ < 0 || min_visible_group_ >= num_groups_) {
      LOG("photo: select all: unexpected group %d", min_visible_group_);
      return;
    }

    GroupLayoutData* g = FindGroup(min_visible_group_);
    for (int i = 0; i < g->photos.size(); ++i) {
      PhotoLayoutData* d = g->photos[i];
      env_->selection.insert(d);
      [d->view setSelected:YES];
    }

    UpdateActionControls();
  }

  void SelectNone() {
    for (SelectionSet::iterator iter(env_->selection.begin());
         iter != env_->selection.end();
         ++iter) {
      PhotoLayoutData* d = *iter;
      [d->view setSelected:NO];
    }
    env_->selection.clear();

    UpdateActionControls();
  }

  void GroupDidZoom(GroupLayoutData* g, bool toolbar_hidden) { }

  void Layout(int64_t target_photo,
              bool animated, void (^completion)()) {
    if (!env_->self.isViewLoaded) {
      return;
    }
    LayoutData* l = LayoutBegin(target_photo);
    LayoutInternal(l);
    LayoutCommit(l, animated, completion);
  }

  LayoutData* LayoutBegin(int64_t target_photo) {
    LayoutData* l = new LayoutData(target_photo);

    [CATransaction begin];
    [CATransaction setDisableActions:YES];
    [scroll_view_ setDelegate:NULL];

    for (PhotoLayoutMap::iterator iter(photo_cache_.begin());
         iter != photo_cache_.end();
         ++iter) {
      PhotoLayoutData* d = iter->second;
      if (d->group) {
        const CGPoint offset =
            d->group->view ? [d->group->view contentOffset] :
            CGPointMake(0, 0);
        l->old_photo_frame[d] = CGRectOffset(
            d->frame,
            d->group->frame.origin.x - offset.x,
            d->group->frame.origin.y - offset.y);
      }
      d->group = NULL;
    }

    // Free up any existing groups, recycling the associated UIScrollViews.
    for (GroupLayoutMap::iterator iter(group_cache_.begin());
         iter != group_cache_.end();
         ++iter) {
      GroupLayoutData* g = iter->second;
      if (g->view) {
        RecycleScrollView(g->view);
        g->view = NULL;
      }
      [g->title removeFromSuperview];
      g->title = NULL;
      if (g->label) {
        l->old_labels.push_back(g->label);
        g->label = NULL;
      }
      // LOG("deleting group data %p", (void*)g);
      delete g;
    }
    group_cache_.clear();

    return l;
  }

  void LayoutCommit(LayoutData* l, bool animated, void (^completion)()) {
    UpdateBounds();

    // Force group creation for any photos that are visible.
    for (PhotoLayoutMap::iterator iter(photo_cache_.begin());
         iter != photo_cache_.end();
         ++iter) {
      PhotoLayoutData* d = iter->second;
      if (!d->view || d->group) {
        continue;
      }
      GroupLayoutData* g = FindGroup(
          FindOrDefault(l->photo_to_group, d->photo_id, -1));
      CHECK_EQ(g, d->group);
    }

    // Show any photos that are now visible.
    for (int group = min_cache_group_; group <= max_cache_group_; ++group) {
      GroupLayoutData* g = FindGroup(group);
      for (int i = 0; i < g->photos.size(); ++i) {
        PhotoLayoutData* d = g->photos[i];
        MaybeShowPhoto(d);
      }
    }

    for (GroupLayoutMap::iterator iter(group_cache_.begin());
         iter != group_cache_.end();
         ++iter) {
      GroupLayoutData* g = iter->second;

      // Force the group to be showing if it contains any visible photos. This
      // is needed to properly animate currently visible photos off the screen.
      bool force_show_group = false;
      for (int j = 0; j < g->photos.size(); ++j) {
        if (g->photos[j]->view) {
          force_show_group = true;
          break;
        }
      }

      MaybeShowGroup(g, force_show_group);
      if (!g->view) {
        continue;
      }
      if (g->label) {
        [g->label setAlpha:0.0];
      }

      UIView* prev_sibling = NULL;
      for (int j = 0; j < g->photos.size(); ++j) {
        PhotoLayoutData* d = g->photos[j];
        MaybeShowPhoto(d);
        if (!d->view) {
          continue;
        }
        if ([d->view superview] != g->view) {
          if (prev_sibling) {
            [g->view insertSubview:d->view aboveSubview:prev_sibling];
          } else {
            [g->view insertSubview:d->view atIndex:0];
          }
        }
        prev_sibling = d->view;
      }
    }

    for (PhotoLayoutMap::iterator iter(photo_cache_.begin());
         iter != photo_cache_.end();
         ++iter) {
      PhotoLayoutData* d = iter->second;
      if (!d->view) {
        continue;
      }
      CHECK(d->group) << " " << d->photo_id << " "
                      << FindOrDefault(l->photo_to_group, d->photo_id, -1);
      GroupLayoutData* g = d->group;
      CHECK(g->view) << " " << g->index;
      CGRect* f = FindPtrOrNull(&l->old_photo_frame, d);
      if (f) {
        f->origin = [scroll_view_ convertPoint:f->origin toView:g->view];
        [d->view setFrame:*f];
      } else {
        [d->view setAlpha:0.0];
      }
    }

    [content_view_ setFrame:CGRectMake(
          l->scroll_delta.x, l->scroll_delta.y,
          l->content_width, l->content_height)];

    if (l->target_photo != -1) {
      PhotoLayoutData* d = FindPhoto(l->target_photo);
      [d->view layer].zPosition = 1;
      [d->group->view layer].zPosition = 1;
    }

    photo_shadows_ = l->photo_shadows;
    photo_borders_ = l->photo_borders;
    env_->show_toolbar = l->show_toolbar;
    env_->show_tabbar = l->show_tabbar;
    env_->show_status = l->show_status;

    [scroll_view_ setDelegate:env_->self];
    [CATransaction commit];

    if (l->show_toolbar) {
      ShowToolbar(kDuration);
      HideActionControls(kDuration);
    } else {
      HideToolbar(kDuration);
    }

    // Disable high-res photo loads while the layout animation is in progress.
    ++env_->load_in_progress;

    // We use the AsyncState mechanism to avoid accessing "this" in the
    // animation completion block if the "this" has been deleted.
    Env* const env = env_;
    AsyncState* state = async_state_;
    AsyncStateEnter(state);

    const int kOptions = UIViewAnimationOptionCurveEaseOut |
        UIViewAnimationOptionAllowUserInteraction |
        UIViewAnimationOptionBeginFromCurrentState;

    const float duration = kDuration * env_->animation_scale;
    [UIView animateWithDuration:(animated ? duration / 3 : 0.0)
                          delay:0
                        options:kOptions
                     animations:^{
        for (int i = 0; i < l->old_labels.size(); ++i) {
          UIView* label = l->old_labels[i];
          [label setAlpha:0.0];
        }
      }
                     completion:NULL];

    [UIView animateWithDuration:(animated ? duration / 3 : 0.0)
                          delay:duration
                        options:kOptions
                     animations:^{
        for (GroupLayoutMap::iterator iter(group_cache_.begin());
             iter != group_cache_.end();
             ++iter) {
          GroupLayoutData* g = iter->second;
          if (g->label) {
            [g->label setAlpha:1.0];
          }
        }
      }
                     completion:NULL];

    [UIView animateWithDuration:(animated ? duration : 0.0)
                          delay:0
                        options:kOptions
                     animations:^{
        if (l->content_overlay_alpha > 0) {
          [env_->content_overlay setHidden:NO];
        }
        [env_->content_overlay setAlpha:l->content_overlay_alpha];

        [content_view_ setFrame:CGRectMake(
              0, 0, l->content_width, l->content_height)];
        [scroll_view_ setFrame:CGRectMake(
              0, 0, l->scroll_size.width, l->scroll_size.height)];

        for (int i = 0; i < l->old_labels.size(); ++i) {
          UIView* label = l->old_labels[i];
          const CGRect f = [label frame];
          [label setFrame:CGRectMake(
                l->scroll_delta.x + f.origin.x,
                l->scroll_delta.y + f.origin.y,
                f.size.width, f.size.height)];
        }

        for (PhotoLayoutMap::iterator iter(photo_cache_.begin());
             iter != photo_cache_.end();
             ++iter) {
          PhotoLayoutData* d = iter->second;
          if (!d->view) {
            continue;
          }
          [d->view setAlpha:1.0];
          [d->view animateToFrame:d->frame
                           shadow:photo_shadows_
                           border:photo_borders_
                         duration:duration];
        }

        MaybeShowPhotos();

        LOG("layout %d photo%s, %d event%s, %d group%s: %0.3f ms",
            num_photos_, Pluralize(num_photos_),
            events_.size(), Pluralize(events_.size()),
            num_groups_, Pluralize(num_groups_),
            l->timer.Milliseconds());
    }
                     completion:^(BOOL finished) {
        for (int i = 0; i < l->old_labels.size(); ++i) {
          [l->old_labels[i] removeFromSuperview];
        }

        --env->load_in_progress;
        if (AsyncStateLeave(state)) {
          if (l->scroll_background) {
            [env_->scroll_view setBackgroundColor:l->scroll_background];
          }
          if (l->content_overlay_alpha == 0) {
            [env_->content_overlay setHidden:YES];
          }
          if (l->target_photo != -1) {
            PhotoLayoutData* d = FindPhoto(l->target_photo);
            [d->view layer].zPosition = 0;
            [d->group->view layer].zPosition = 0;
          }
          MaybeLoadPhotos();
          MaybeHidePhotos();
        }

        delete l;
        if (completion) {
          completion();
        }
    }];

    env_->UpdateAnimationScale();
  }

  virtual void LayoutInternal(LayoutData* l) = 0;

 protected:
  Env* const env_;
  AppState* const state_;
  AsyncState* const async_state_;
  UIScrollView* scroll_view_;
  UIView* content_view_;
  PhotoLayoutMap& photo_cache_;
  GroupLayoutMap& group_cache_;
  std::vector<EventLayoutData*>& events_;
  std::vector<PhotoView*>& recycled_photo_views_;
  std::vector<UIScrollView*>& recycled_scroll_views_;
  int& num_photos_;
  int& num_groups_;
  int& min_visible_group_;
  int& max_visible_group_;
  int& min_cache_group_;
  int& max_cache_group_;
  bool& photo_shadows_;
  bool& photo_borders_;
  GeocodeQueue geocode_queue_;
  int geocode_in_progress_;
};

// TODO(pmattis): Watch device orientation changes and switch from portrait to
// landscape.
class IndividualPhotoLayout : public PhotoLayoutBase {
 public:
  IndividualPhotoLayout(Env* env)
      : PhotoLayoutBase(env) {
  }

 private:
  int MinGroupForRect(const CGRect& f) {
    const float size = env_->self.view.bounds.size.width + kPhotoSpacing;
    const int group = CGRectGetMinX(f) / size;
    return std::max<int>(0, std::min<int>(num_groups_ - 1, group));
  }

  int MaxGroupForRect(const CGRect& f) {
    const float size = env_->self.view.bounds.size.width + kPhotoSpacing;
    const int group = (CGRectGetMaxX(f) + size - 1) / size;
    return std::min<int>(num_groups_ - 1, std::max<int>(0, group - 1));
  }

  CGRect CacheBoundsForRect(const CGRect& f) {
    // Extend the visible rect 50% in the layout direction.
    return CGRectInset(f, -f.size.width / 2, 0);
  }

  static CGRect AspectFit(const CGSize& bounds, float aspect_ratio) {
    CGRect r = { { 0, 0 }, bounds };
    const float cx = CGRectGetMidX(r);
    const float cy = CGRectGetMidY(r);
    const float a = r.size.width / r.size.height;
    if (aspect_ratio >= a) {
      r.size.height = r.size.width / aspect_ratio;
    } else {
      r.size.width = r.size.height * aspect_ratio;
    }
    r.origin.x = cx - r.size.width / 2;
    r.origin.y = cy - r.size.height / 2;
    return r;
  }

  GroupLayoutData* InitGroup(int index) {
    EventLayoutData* e = NULL;
    int photo_index = index;
    for (int i = 0; i < events_.size(); ++i) {
      e = events_[i];
      if (photo_index < e->photos.size()) {
        break;
      }
      photo_index -= e->photos.size();
      e = NULL;
    }
    CHECK(e != NULL);

    GroupLayoutData* g = new GroupLayoutData;
    g->index = index;
    g->event = e;

    g->frame.size = env_->self.view.bounds.size;
    g->frame.origin = CGPointMake(
        (g->frame.size.width + kPhotoSpacing) * g->index, 0);

    PhotoLayoutData* d = FindPhoto(e->photos[photo_index]);
    d->frame = AspectFit(g->frame.size, d->aspect_ratio);
    d->frame.origin = CGPointMake(0, 0);
    d->group = g;
    g->photos.push_back(d);

    return g;
  }

  void InitGroupView(GroupLayoutData* g) {
    [g->view setAlwaysBounceHorizontal:NO];
    [g->view setAlwaysBounceVertical:NO];
    [g->view setShowsHorizontalScrollIndicator:NO];
    [g->view setShowsVerticalScrollIndicator:NO];
    [g->view setScrollIndicatorInsets:UIEdgeInsetsMake(0, 0, 0, 0)];
    [g->view setContentInset:UIEdgeInsetsMake(0, 0, 0, 0)];
    [g->view setBackgroundColor:[UIColor clearColor]];
    [g->view setDecelerationRate:UIScrollViewDecelerationRateFast];

    // TODO(pmattis): Set the maximum zoom scale based on the photo resolution.
    [g->view setZoomScale:1];
    [g->view setMaximumZoomScale:2];

    [g->view setFrame:CGRectMake(
          g->frame.origin.x, g->frame.origin.y,
          env_->self.view.bounds.size.width,
          env_->self.view.bounds.size.height)];

    PhotoLayoutData* d = g->photos.front();
    [g->view setContentOffset:CGPointMake(0, 0)];
    [g->view setContentSize:d->frame.size];

    GroupDidZoom(g, env_->toolbar.hidden);
    InitGroupTitle(g, true, true);
  }

  void UpdateBounds() {
    PhotoLayoutBase::UpdateBounds();

    if (min_visible_group_ == max_visible_group_) {
      if (min_visible_group_ > 0) {
        GroupLayoutData* g = FindGroup(min_visible_group_ - 1);
        [g->view setZoomScale:1];
      }
      if (min_visible_group_ + 1 < num_groups_) {
        GroupLayoutData* g = FindGroup(min_visible_group_ + 1);
        [g->view setZoomScale:1];
      }
    }
  }

  void GroupDidZoom(GroupLayoutData* g, bool toolbar_hidden) {
    PhotoLayoutData* d = g->photos.front();
    const CGSize size = d->frame.size;
    const CGSize bounds = env_->self.view.bounds.size;
    const float scale = std::max<float>(1, [g->view zoomScale]);
    const float top = toolbar_hidden ? 0 :
        [env_->toolbar frame].size.height;
    const float x = std::max<float>(
        0, (bounds.width - size.width * scale) / 2);
    const float y = std::max<float>(
        0, (bounds.height - top - size.height * scale) / 2);
    [g->view setContentInset:UIEdgeInsetsMake(y + top, x, y, x)];
  }

  void LayoutInternal(LayoutData* l) {
    LayoutGroups(l);
    LayoutScrollToTarget(l);
    LayoutInitScroll(l);
    [env_->double_tap_recognizer setEnabled:YES];
  }

  void LayoutGroups(LayoutData* l) {
    num_groups_ = 0;
    for (int i = 0; i < events_.size(); ++i) {
      EventLayoutData* e = events_[i];
      for (int j = 0; j < e->photos.size(); ++j) {
        l->photo_to_group[e->photos[j]] = num_groups_++;
      }
    }

    const float visible_width = env_->self.view.bounds.size.width;
    const float visible_height = env_->self.view.bounds.size.height;
    l->content_width = (visible_width + kPhotoSpacing) * num_groups_;
    l->content_height = visible_height;
  }

  void LayoutScrollToTarget(LayoutData* l) {
    if (l->target_photo == -1) {
      return;
    }
    GroupLayoutData* target_group = FindGroup(
        FindOrDefault(l->photo_to_group, l->target_photo, -1));
    const CGPoint old_offset = [scroll_view_ contentOffset];
    [scroll_view_ setContentOffset:CGPointMake(
          target_group->frame.origin.x, 0)];
    [env_->toolbar_title_view setContentOffset:[scroll_view_ contentOffset]];
    l->scroll_delta = CGPointMake(
        [scroll_view_ contentOffset].x - old_offset.x, -old_offset.y);
  }

  void LayoutInitScroll(LayoutData* l) {
    [env_->viewfinder_tool setHidden:YES];
    [env_->swipe_left_recognizer setEnabled:NO];
    [env_->swipe_right_recognizer setEnabled:NO];
    [content_view_ setFrame:CGRectMake(
          0, 0, l->content_width, l->content_height)];
    [scroll_view_ setPagingEnabled:YES];
    [scroll_view_ setShowsHorizontalScrollIndicator:NO];
    [scroll_view_ setShowsVerticalScrollIndicator:NO];
    [scroll_view_ setContentSize:[content_view_ frame].size];
    [scroll_view_ setAlwaysBounceVertical:NO];
    l->scroll_size = env_->self.view.bounds.size;
    l->scroll_size.width += kPhotoSpacing;
    l->scroll_background = [UIColor blackColor];
    l->photo_shadows = false;
    l->photo_borders = false;
    l->show_toolbar = true;
    l->show_tabbar = false;
    l->show_status = false;

    [env_->content_overlay layer].zPosition = -1;
    [env_->content_overlay setHidden:NO];
    [env_->content_overlay setAlpha:0];
    [env_->content_overlay setBackgroundColor:[UIColor blackColor]];
    l->content_overlay_alpha = 1;
  }

  void ShowActionControls(float duration) {
    [env_->action_bar setItems:env_->action_bar_photo_items animated:NO];

    LOG("photo: show action controls: %d-%d",
        min_visible_group_, max_visible_group_);
    if (min_visible_group_ == max_visible_group_) {
      // Mark all of the photos (there should be only 1) as selected.
      GroupLayoutData* g = FindGroup(min_visible_group_);
      env_->selection.insert(g->photos.begin(), g->photos.end());
    }

    PhotoLayoutBase::ShowActionControls(duration);

    // Disable the select all/none gestures.
    [env_->swipe_left_recognizer setEnabled:NO];
    [env_->swipe_right_recognizer setEnabled:NO];
  }

  void SwipeLeft(PhotoLayoutData* d) {
    SelectNone();
  }

  void SwipeRight(PhotoLayoutData* d) {
    SelectAll();
  }
};

class SummaryEventLayout : public PhotoLayoutBase {
 public:
  SummaryEventLayout(Env* env)
      : PhotoLayoutBase(env) {
  }

 private:
  int MinGroupForRect(const CGRect& f) {
    const float size = kEventSpacing + env_->self.view.bounds.size.width / 2;
    const int group = (CGRectGetMinY(f) - kEventSpacing) / size;
    return std::max<int>(0, std::min<int>(num_groups_ - 1, group));
  }

  int MaxGroupForRect(const CGRect& f) {
    const float size = kEventSpacing + env_->self.view.bounds.size.width / 2;
    const int group = (CGRectGetMaxY(f) - kEventSpacing + size - 1) / size;
    return std::min<int>(num_groups_ - 1, std::max<int>(0, group - 1));
  }

  CGRect CacheBoundsForRect(const CGRect& f) {
    // Extend the visible rect 50% in the layout direction.
    return CGRectInset(f, 0, -f.size.height / 2);
  }

  GroupLayoutData* InitGroup(int index) {
    const float group_width = env_->self.view.bounds.size.width;
    const float group_height = group_width / 2;
    const float tile_width = (group_width - kThumbnailSpacing) / 4;
    const float tile_height = (group_height - kThumbnailSpacing) / 2;

    EventLayoutData* e = events_[index];
    CHECK_GT(e->photos.size(), 0);

    GroupLayoutData* g = new GroupLayoutData;
    g->index = index;
    g->event = e;

    g->photos.resize(e->photos.size(), NULL);
    for (int j = 0; j < g->photos.size(); ++j) {
      g->photos[j] = FindPhoto(e->photos[j]);
      g->photos[j]->group = g;
    }

    g->frame = CGRectMake(
        0,
        kEventSpacing + (group_height + kEventSpacing) * g->index,
        group_width, group_height + kEventSpacing);

    // Find the best (randomized) layout and apply it to the photos.
    const TileLayout* layout = TileLayout::Select(g);
    layout->Apply(g, tile_width, tile_height, kThumbnailSpacing);
    return g;
  }

  void InitGroupView(GroupLayoutData* g) {
    [g->view setAlwaysBounceHorizontal:NO];
    [g->view setAlwaysBounceVertical:NO];
    [g->view setShowsHorizontalScrollIndicator:YES];
    [g->view setShowsVerticalScrollIndicator:NO];
    [g->view setScrollIndicatorInsets:UIEdgeInsetsMake(0, 0, 0, 0)];
    [g->view setContentInset:UIEdgeInsetsMake(0, 0, 0, 0)];
    [g->view setBackgroundColor:[UIColor clearColor]];
    [g->view setDecelerationRate:UIScrollViewDecelerationRateNormal];
    [g->view setZoomScale:1];
    [g->view setMaximumZoomScale:1];

    const CGRect f = g->frame;
    [g->view setFrame:CGRectMake(
          f.origin.x, f.origin.y, env_->self.view.bounds.size.width,
          f.size.height)];
    [g->view setContentOffset:CGPointMake(0, 0)];
    [g->view setContentSize:f.size];

    InitGroupLabel(g);
  }

  void InitGroupLabel(GroupLayoutData* g) {
    PhotoLayoutData* d = g->photos.front();

    string labels[2];
    int count = 0;
    labels[count++] =
        Format("%s", WallTimeFormat("%b %e, %Y", d->timestamp));

    if (state_->photo_manager()->FormatLocation(d->photo_id, &labels[count])) {
      labels[count - 1] += ", ";
      ++count;
    } else {
      MaybeReverseGeocode(d, ^{
          GroupLayoutData* g = d->group;
          if (g->view) {
            InitGroupLabel(g);
          }
        });
    }

    const int visible_width = env_->self.view.bounds.size.width;
    int width = visible_width - 2 * kLabelOriginX;
    // Append a right-angle if the group is wider than the screen.
    const string count_str = Format(
        "%d%s", g->photos.size(),
        (g->frame.size.width > visible_width) ? " »" : "");
    UIView* group_count =
        MakeLabel(&count_str, 1,
                  env_->scroll_view_background, width);
    {
      CGRect f = [group_count frame];
      f.origin.x = width - f.size.width;
      width = f.origin.x - 4;
      [group_count setFrame:f];
    }

    UIView* group_title =
        MakeLabel(labels, count,
                  env_->scroll_view_background, width);

    UIView* view = [UIView new];
    [view setBackgroundColor:[UIColor clearColor]];
    {
      CGRect f = CGRectUnion([group_title frame], [group_count frame]);
      f.origin.x = kLabelOriginX;
      f.origin.y = g->frame.origin.y +
          kThumbnailBorder + kThumbnailSpacing - f.size.height / 2;
      [view setFrame:f];
    }
    [view addSubview:group_count];
    [view addSubview:group_title];
    [view layer].zPosition = 2;

    [g->label removeFromSuperview];
    g->label = view;

    // Add the group label to the main content view so that it doesn't scroll
    // horizontally with the group.
    [content_view_ addSubview:g->label];
  }

  static UIView* MakeLabel(
      const string* labels, int count, UIColor* background_color, int width) {
    UIView* background = [UIView new];
    [background setBackgroundColor:background_color];
    [background layer].cornerRadius = 2;
    [background setClipsToBounds:YES];

    UIFont* font = kPhotoGroupLabelFont;
    const float min_x = 4;
    const float max_x = width - 4;
    float x = min_x;

    for (int i = 0; i < count; ++i) {
      NSString* text = NewNSString(labels[i]);
      UILabel* label = [UILabel new];
      [label setFont:font];
      [label setText:text];
      [label setTextColor:kPhotoGroupLabelTextColor];
      [label setShadowColor:kPhotoGroupLabelShadowColor];
      [label setShadowOffset:CGSizeMake(0, 1)];
      [label setBackgroundColor:[UIColor clearColor]];
      [label setLineBreakMode:UILineBreakModeHeadTruncation];
      [label sizeToFit];
      CGRect f = [label frame];
      f.origin.x = x;
      f.origin.y = 1;
      f.size.width = std::min(x + f.size.width, max_x) - x;
      [label setFrame:f];
      x = CGRectGetMaxX(f);
      [background addSubview:label];
    }

    [background setFrame:CGRectMake(0, 0, x + 4, font.lineHeight + 2)];

    UIView* view = [UIView new];
    [view setBackgroundColor:[UIColor clearColor]];
    [view setFrame:[background frame]];
    [view layer].shadowColor = kThumbnailShadowColor;
    [view layer].shadowOffset = kThumbnailShadowOffset;
    [view layer].shadowOpacity = 1;
    [view layer].shadowRadius = kThumbnailShadowRadius;
    ScopedRef<CGPathRef> path(CGPathCreateWithRect([view bounds], NULL));
    [view layer].shadowPath = path;
    [view addSubview:background];
    return view;
  }

  void LayoutInternal(LayoutData* l) {
    LayoutGroups(l);
    LayoutScrollToTarget(l);
    LayoutInitScroll(l);
    [env_->double_tap_recognizer setEnabled:NO];
  }

  void LayoutGroups(LayoutData* l) {
    num_groups_ = events_.size();

    for (int i = 0; i < events_.size(); ++i) {
      EventLayoutData* e = events_[i];
      for (int j = 0; j < e->photos.size(); ++j) {
        l->photo_to_group[e->photos[j]] = i;
      }
    }

    const float group_width = env_->self.view.bounds.size.width;
    const float group_height = group_width / 2;
    UITabBar* tabbar = state_->root_view_controller().tabbar;
    l->content_width = group_width;
    l->content_height = tabbar.frame.size.height +
        (group_height + kEventSpacing) * num_groups_;
  }

  void LayoutScrollToTarget(LayoutData* l) {
    if (l->target_photo == -1) {
      return;
    }
    // Adjust the main scroll view vertically to make the target photo visible.
    GroupLayoutData* target_group = FindGroup(
        FindOrDefault(l->photo_to_group, l->target_photo, -1));
    const float max_y_offset = std::max<float>(
        0, l->content_height - env_->self.view.bounds.size.height);
    const float scroll_y_target = std::min<float>(
        max_y_offset,
        target_group->frame.origin.y - kEventSpacing);
    const CGPoint old_offset = [scroll_view_ contentOffset];
    [scroll_view_ setContentOffset:CGPointMake(0, scroll_y_target)];
    l->scroll_delta = CGPointMake(
        -old_offset.x, [scroll_view_ contentOffset].y - old_offset.y);
  }

  void LayoutInitScroll(LayoutData* l) {
    [env_->viewfinder_tool setHidden:NO];
    [env_->swipe_left_recognizer setEnabled:YES];
    [env_->swipe_right_recognizer setEnabled:YES];
    [content_view_ setFrame:CGRectMake(
          0, 0, l->content_width, l->content_height)];
    [scroll_view_ setPagingEnabled:NO];
    [scroll_view_ setShowsHorizontalScrollIndicator:YES];
    [scroll_view_ setShowsVerticalScrollIndicator:YES];
    [scroll_view_ setContentSize:[content_view_ frame].size];
    [scroll_view_ setAlwaysBounceVertical:YES];
    [scroll_view_ setBackgroundColor:env_->scroll_view_background];
    l->scroll_size = env_->self.view.bounds.size;
  }

  void ShowActionControls(float duration) {
    [env_->action_bar setItems:env_->action_bar_event_items animated:NO];

    PhotoLayoutBase::ShowActionControls(duration);

    [env_->single_tap_recognizer setEnabled:NO];
  }

  void HideActionControls(float duration) {
    CALayer* view_layer = NULL;
    CALayer* label_layer = NULL;
    if (!env_->selection.empty()) {
      GroupLayoutData* g = (*env_->selection.begin())->group;
      view_layer = [g->view layer];
      label_layer = [g->label layer];
    }

    PhotoLayoutBase::HideActionControls(duration);
    HideToolbar(duration, false);

    [env_->single_tap_recognizer setEnabled:YES];
    [env_->swipe_left_recognizer setEnabled:YES];
    [env_->swipe_right_recognizer setEnabled:YES];
    [env_->viewfinder_tool setHidden:NO];

    PhotoLayoutEnv* env = env_;
    [UIView animateWithDuration:duration * env->animation_scale
                     animations:^{
        [env->scroll_view setContentInset:UIEdgeInsetsZero];
        [env->content_overlay setAlpha:0];
      }
                     completion:^(BOOL finished) {
        [env->refresh_header setHidden:NO];
        [env->content_overlay setHidden:YES];
        if (view_layer) {
          view_layer.zPosition -= 20;
        }
        if (label_layer) {
          label_layer.zPosition -= 20;
        }
      }];
  }

  void SwipeLeft(PhotoLayoutData* d) {
    if (env_->scroll_view.dragging ||
        env_->scroll_view.decelerating) {
      // Ignore swipes while the scroll view is scrolling.
      return;
    }

    if (!env_->action_bar.hidden) {
      HideActionControls(kDuration);
      return;
    }

    if (!d) {
      return;
    }

    // Mark all of the photos as selected.
    GroupLayoutData* g = d->group;
    env_->selection.insert(g->photos.begin(), g->photos.end());
    [g->view layer].zPosition += 20;
    [g->label layer].zPosition += 20;

    ShowToolbar(kDuration);
    ShowActionControls(kDuration);

    const float y = [env_->toolbar frame].size.height;
    [env_->scroll_view setContentInset:UIEdgeInsetsMake(
          y, 0, 0, 0)];
    [env_->scroll_view setContentOffset:CGPointMake(
          0, g->frame.origin.y - y - kEventSpacing)
                               animated:YES];

    [env_->viewfinder_tool setHidden:YES];
    [env_->refresh_header setHidden:YES];
    [env_->content_overlay layer].zPosition = 10;
    [env_->content_overlay setHidden:NO];
    [env_->content_overlay setAlpha:0];
    [env_->content_overlay setBackgroundColor:[UIColor blackColor]];

    [UIView animateWithDuration:kDuration * env_->animation_scale
                     animations:^{
        [env_->content_overlay setAlpha:0.75];
      }];
  }

  void SwipeRight(PhotoLayoutData* d) {
    SwipeLeft(d);
  }
};

class DetailedEventLayout : public PhotoLayoutBase {
 public:
  DetailedEventLayout(Env* env)
      : PhotoLayoutBase(env) {
  }

 private:
  int MinGroupForRect(const CGRect& f) {
    const float size = env_->self.view.bounds.size.width + kPhotoSpacing;
    const int group = CGRectGetMinX(f) / size;
    return std::max<int>(0, std::min<int>(num_groups_ - 1, group));
  }

  int MaxGroupForRect(const CGRect& f) {
    const float size = env_->self.view.bounds.size.width + kPhotoSpacing;
    const int group = (CGRectGetMaxX(f) + size - 1) / size;
    return std::min<int>(num_groups_ - 1, std::max<int>(0, group - 1));
  }

  CGRect CacheBoundsForRect(const CGRect& f) {
    // Extend the visible rect 50% in the layout direction.
    return CGRectInset(f, -f.size.width / 2, 0);
  }

  GroupLayoutData* InitGroup(int index) {
    const float visible_width = env_->self.view.bounds.size.width;

    EventLayoutData* e = events_[index];
    CHECK_GT(e->photos.size(), 0);

    GroupLayoutData* g = new GroupLayoutData;
    g->index = index;
    g->event = e;

    g->photos.resize(e->photos.size(), NULL);
    for (int j = 0; j < g->photos.size(); ++j) {
      g->photos[j] = FindPhoto(e->photos[j]);
      g->photos[j]->group = g;
    }

    EventLayout::Apply(g, visible_width, kThumbnailSpacing);

    g->frame = CGRectMake(
        (visible_width + kPhotoSpacing) * g->index, 0,
        visible_width, CGRectGetMaxY(g->photos.back()->frame));
    return g;
  }

  void InitGroupView(GroupLayoutData* g) {
    [g->view setAlwaysBounceHorizontal:NO];
    [g->view setAlwaysBounceVertical:YES];
    [g->view setShowsHorizontalScrollIndicator:NO];
    [g->view setShowsVerticalScrollIndicator:YES];
    [g->view setScrollIndicatorInsets:UIEdgeInsetsMake(
          [env_->toolbar frame].size.height, 0, 0, 0)];
    [g->view setContentInset:UIEdgeInsetsMake(
          [env_->toolbar frame].size.height, 0, 0, 0)];
    [g->view setBackgroundColor:env_->scroll_view_background];
    [g->view setDecelerationRate:UIScrollViewDecelerationRateNormal];
    [g->view setZoomScale:1];
    [g->view setMaximumZoomScale:1];

    const CGRect f = g->frame;
    [g->view setFrame:CGRectMake(
          f.origin.x, f.origin.y,
          env_->self.view.bounds.size.width,
          env_->self.view.bounds.size.height)];
    [g->view setContentOffset:CGPointMake(
          0, -[g->view contentInset].top)];
    [g->view setContentSize:f.size];

    InitGroupTitle(g, true, false);
  }

  void LayoutInternal(LayoutData* l) {
    LayoutGroups(l);
    LayoutScrollToTarget(l);
    LayoutInitScroll(l);
    [env_->double_tap_recognizer setEnabled:NO];
  }

  void LayoutGroups(LayoutData* l) {
    num_groups_ = events_.size();

    for (int i = 0; i < events_.size(); ++i) {
      EventLayoutData* e = events_[i];
      for (int j = 0; j < e->photos.size(); ++j) {
        l->photo_to_group[e->photos[j]] = i;
      }
    }

    const float visible_width = env_->self.view.bounds.size.width;
    const float visible_height = env_->self.view.bounds.size.height;
    l->content_width = (visible_width + kPhotoSpacing) * num_groups_;
    l->content_height = visible_height;
  }

  void LayoutScrollToTarget(LayoutData* l) {
    if (l->target_photo == -1) {
      return;
    }
    GroupLayoutData* target_group = FindGroup(
        FindOrDefault(l->photo_to_group, l->target_photo, -1));
    const CGPoint old_offset = [scroll_view_ contentOffset];
    [scroll_view_ setContentOffset:CGPointMake(
          target_group->frame.origin.x, 0)];
    [env_->toolbar_title_view setContentOffset:[scroll_view_ contentOffset]];
    l->scroll_delta = CGPointMake(
        [scroll_view_ contentOffset].x - old_offset.x, -old_offset.y);
  }

  void LayoutInitScroll(LayoutData* l) {
    [env_->viewfinder_tool setHidden:YES];
    [env_->swipe_left_recognizer setEnabled:NO];
    [env_->swipe_right_recognizer setEnabled:NO];
    [content_view_ setFrame:CGRectMake(
          0, 0, l->content_width, l->content_height)];
    [scroll_view_ setPagingEnabled:YES];
    [scroll_view_ setShowsHorizontalScrollIndicator:NO];
    [scroll_view_ setShowsVerticalScrollIndicator:NO];
    [scroll_view_ setContentSize:[content_view_ frame].size];
    [scroll_view_ setAlwaysBounceVertical:NO];
    [scroll_view_ setBackgroundColor:env_->scroll_view_background];
    l->scroll_size = env_->self.view.bounds.size;
    l->scroll_size.width += kPhotoSpacing;
    [env_->toolbar_title_view setContentSize:CGSizeMake(
          [content_view_ frame].size.width,
          [env_->toolbar_title_view frame].size.height)];
    l->show_toolbar = true;
    l->show_tabbar = false;
    l->show_status = false;
  }

  void ShowActionControls(float duration) {
    if (min_visible_group_ == max_visible_group_) {
      GroupLayoutData* g = FindGroup(min_visible_group_);
      if (g->photos.size() == 1) {
        for (int i = 0; i < g->photos.size(); ++i) {
          PhotoLayoutData* d = g->photos[i];
          env_->selection.insert(d);
          [d->view setSelected:true];
        }
      }
    }

    [env_->action_bar setItems:env_->action_bar_event_items animated:NO];
    PhotoLayoutBase::ShowActionControls(duration);
  }

  void HideActionControls(float duration) {
    if (min_visible_group_ == max_visible_group_) {
      GroupLayoutData* g = FindGroup(min_visible_group_);
      for (int i = 0; i < g->photos.size(); ++i) {
        [g->photos[i]->view setShadowColor:kThumbnailShadowColor];
        [g->photos[i]->view setShadowOffset:kThumbnailShadowOffset];
      }
    }

    PhotoLayoutBase::HideActionControls(duration);
  }

  void SwipeLeft(PhotoLayoutData* d) {
    SelectNone();
  }

  void SwipeRight(PhotoLayoutData* d) {
    SelectAll();
  }
};

}  // namespace

@implementation OldPhotoViewController

- (id)initWithState:(AppState*)state {
  if (self = [super init]) {
    self.wantsFullScreenLayout = YES;

    env_.reset(new PhotoLayoutEnv(state, self));

    target_photo_ = -1;
    detailed_mode_ = state->db()->Get<bool>(kDetailedModeKey, false);
    individual_mode_ = state->db()->Get<bool>(kIndividualModeKey, false);

    state->status()->Add(^{
        [self updateStatus];
      });
    state->assets_manager().scanStart->Add(^{
        dispatch_main(^{
            if (state->assets_manager().fullScan) {
              [self assetLoadingProgress:0];
            }
          });
      });
    state->assets_manager().scanProgress->Add(
        ^(ALAsset*, const string&, int progress) {
        dispatch_main(^{
            if (state->assets_manager().fullScan) {
              [self assetLoadingProgress:progress];
            }
          });
      });
    env_->state->assets_manager().scanEnd->Add(^{
        dispatch_main(^{
            if (state->assets_manager().fullScan) {
              [self assetLoadingStop];
            }
          });
      });
    state->net_manager()->update_start()->Add(^{
        [self networkLoadingStart:0.5];
      });
    state->net_manager()->update_end()->Add(^{
        [self networkLoadingStop];
        if (!reload_delayed_) {
          [self reloadPhotos];
          reload_delayed_ = true;
        }
      });
    state->photo_manager()->update()->Add(^{
        if (!reload_needed_) {
          reload_needed_ = true;
          [env_->state->root_view_controller() setEventsReloadNeeded:true];
        }
      });

    reload_delayed_ = true;
    reload_needed_ = true;
  }
  return self;
}

- (void)loadView {
  LOG("photo: view load");
  self.view = [UIView new];
  self.view.autoresizesSubviews = YES;

  env_->scroll_view_background =
      [UIColor colorWithPatternImage:[UIImage imageNamed:@"paper.png"]];

  env_->scroll_view = [UIScrollView new];
  [env_->scroll_view setBackgroundColor:env_->scroll_view_background];
  [env_->scroll_view setAutoresizesSubviews:YES];
  [env_->scroll_view setAutoresizingMask:
         UIViewAutoresizingFlexibleWidth |
       UIViewAutoresizingFlexibleHeight];
  [env_->scroll_view setDelegate:self];
  [env_->scroll_view setCanCancelContentTouches:YES];
  [env_->scroll_view setAlwaysBounceVertical:YES];
  [self.view addSubview:env_->scroll_view];

  env_->viewfinder_tool =
      [[ViewfinderTool alloc] initWithState:env_->state];
  [env_->viewfinder_tool begin]->Add(^{
      [self viewfinderBegin];
    });
  [env_->viewfinder_tool update]->Add(^{
      [self viewfinderUpdate];
    });
  [env_->viewfinder_tool end]->Add(^{
      [self viewfinderEnd];
    });
  [env_->viewfinder_tool cancel]->Add(^{
      [self viewfinderCancel];
    });
  [self.view addSubview:env_->viewfinder_tool];

  env_->content_view = [UIView new];
  [env_->content_view setAutoresizesSubviews:YES];
  [env_->scroll_view addSubview:env_->content_view];

  env_->content_overlay = [UIView new];
  [env_->content_overlay setAutoresizingMask:
         UIViewAutoresizingFlexibleHeight |
       UIViewAutoresizingFlexibleWidth];
  [env_->content_overlay setUserInteractionEnabled:NO];
  [env_->content_overlay setHidden:YES];
  [env_->content_view addSubview:env_->content_overlay];

  env_->single_tap_recognizer =
      [[UITapGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSingleTap:)];
  [env_->single_tap_recognizer setDelegate:self];
  [env_->single_tap_recognizer setNumberOfTapsRequired:1];
  [env_->content_view addGestureRecognizer:env_->single_tap_recognizer];

  env_->double_tap_recognizer =
      [[UITapGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleDoubleTap:)];
  [env_->double_tap_recognizer setDelegate:self];
  [env_->double_tap_recognizer setNumberOfTapsRequired:2];
  [env_->double_tap_recognizer setEnabled:NO];
  [env_->content_view addGestureRecognizer:env_->double_tap_recognizer];

  [env_->single_tap_recognizer
      requireGestureRecognizerToFail:env_->double_tap_recognizer];

  env_->swipe_left_recognizer =
      [[UISwipeGestureRecognizer alloc]
        initWithTarget:self action:@selector(handleSwipeLeft:)];
  [env_->swipe_left_recognizer setEnabled:NO];
  [env_->swipe_left_recognizer setDelegate:self];
  [env_->swipe_left_recognizer
      setDirection:UISwipeGestureRecognizerDirectionLeft];
  [env_->content_view addGestureRecognizer:env_->swipe_left_recognizer];

  env_->swipe_right_recognizer =
      [[UISwipeGestureRecognizer alloc]
        initWithTarget:self action:@selector(handleSwipeRight:)];
  [env_->swipe_right_recognizer setEnabled:NO];
  [env_->swipe_right_recognizer setDelegate:self];
  [env_->swipe_right_recognizer
      setDirection:UISwipeGestureRecognizerDirectionRight];
  [env_->content_view addGestureRecognizer:env_->swipe_right_recognizer];

  {
    env_->toolbar = [UIToolbar new];
    [env_->toolbar setAutoresizesSubviews:YES];
    [env_->toolbar setAutoresizingMask:
           UIViewAutoresizingFlexibleBottomMargin |
         UIViewAutoresizingFlexibleWidth];
    [env_->toolbar setBarStyle:UIBarStyleBlackTranslucent];
    [env_->toolbar sizeToFit];
    [env_->toolbar setFrame:CGRectMake(
          0, 0, 0, [env_->toolbar frame].size.height)];
    [env_->toolbar setHidden:YES];

    UIBarButtonItem* back_item =
        [[UIBarButtonItem alloc]
            initWithImage:[UIImage imageNamed:@"back.png"]
                    style:UIBarButtonItemStylePlain
                   target:self
                   action:@selector(popLayout)];

    UIBarButtonItem* action_item =
        [[UIBarButtonItem alloc]
            initWithBarButtonSystemItem:UIBarButtonSystemItemAction
                                 target:self
                                 action:@selector(showActionControls)];
    [action_item setStyle:UIBarButtonItemStylePlain];

    env_->toolbar_title_view = [UIScrollView new];
    [env_->toolbar_title_view setAutoresizingMask:
           UIViewAutoresizingFlexibleHeight];
    [env_->toolbar_title_view setFrame:CGRectMake(
          0, 0, 230, [env_->toolbar frame].size.height)];
    [env_->toolbar_title_view setClipsToBounds:YES];
    [env_->toolbar_title_view setScrollEnabled:NO];
    [env_->toolbar_title_view setShowsVerticalScrollIndicator:NO];
    [env_->toolbar_title_view setShowsHorizontalScrollIndicator:NO];

    UIBarButtonItem* title_item =
        [[UIBarButtonItem alloc] initWithCustomView:env_->toolbar_title_view];
    env_->toolbar_view_items = Array(back_item, title_item, action_item);

    env_->toolbar_editing_label = [[UILabel alloc] init];
    [env_->toolbar_editing_label setText:@"10000 Photos Selected"];
    [env_->toolbar_editing_label setAutoresizingMask:UIViewAutoresizingFlexibleWidth];
    [env_->toolbar_editing_label setFont:[UIFont boldSystemFontOfSize:18]];
    [env_->toolbar_editing_label setTextColor:[UIColor whiteColor]];
    [env_->toolbar_editing_label setShadowColor:[UIColor blackColor]];
    [env_->toolbar_editing_label setShadowOffset:CGSizeMake(0, -1)];
    [env_->toolbar_editing_label setBackgroundColor:[UIColor clearColor]];
    [env_->toolbar_editing_label setTextAlignment:UITextAlignmentCenter];
    [env_->toolbar_editing_label setUserInteractionEnabled:NO];
    [env_->toolbar_editing_label sizeToFit];
    UIBarButtonItem* select_photos =
        [[UIBarButtonItem alloc]
            initWithCustomView:env_->toolbar_editing_label];
    UIBarButtonItem* cancel_item =
        [[UIBarButtonItem alloc]
          initWithTitle:@"Cancel"
                  style:UIBarButtonItemStyleBordered
                 target:self
                 action:@selector(hideActionControls)];
    [cancel_item setTintColor:kCancelTintColor];
    UIBarButtonItem* flex_space =
        [[UIBarButtonItem alloc]
            initWithBarButtonSystemItem:UIBarButtonSystemItemFlexibleSpace
                                 target:NULL
                                 action:NULL];
    env_->toolbar_action_items = Array(
        flex_space, select_photos, cancel_item);

    UIBarButtonItem* save_item =
        [[UIBarButtonItem alloc]
          initWithTitle:@"Save"
                  style:UIBarButtonItemStyleBordered
                 target:self
                 action:@selector(savePhotoEdits)];
    [save_item setEnabled:NO];

    UILabel* edit_photos_label = [UILabel new];
    [edit_photos_label setText:@"Edit Photo"];
    [edit_photos_label setAutoresizingMask:UIViewAutoresizingFlexibleWidth];
    [edit_photos_label setFont:[UIFont boldSystemFontOfSize:18]];
    [edit_photos_label setTextColor:[UIColor whiteColor]];
    [edit_photos_label setShadowColor:[UIColor blackColor]];
    [edit_photos_label setShadowOffset:CGSizeMake(0, -1)];
    [edit_photos_label setBackgroundColor:[UIColor clearColor]];
    [edit_photos_label setTextAlignment:UITextAlignmentCenter];
    [edit_photos_label setUserInteractionEnabled:NO];
    [edit_photos_label sizeToFit];
    UIBarButtonItem* edit_photos =
        [[UIBarButtonItem alloc]
            initWithCustomView:edit_photos_label];
    env_->toolbar_editing_items = Array(
        save_item, flex_space, edit_photos, flex_space, cancel_item);

    UIBarButtonItem* send_item =
        [[UIBarButtonItem alloc]
          initWithTitle:@"Send"
                  style:UIBarButtonItemStyleBordered
                 target:self
                 action:@selector(sharePhotosFinish)];
    [send_item setTintColor:kSendTintColor];
    [send_item setPossibleTitles:Set(@"Send", @"Cancel")];
    env_->toolbar_share_items = Array(
        send_item, flex_space, select_photos, flex_space, cancel_item);

    [env_->toolbar setItems:env_->toolbar_view_items];
    [self.view addSubview:env_->toolbar];
  }

  {
    env_->action_bar = [UIToolbar new];
    [env_->action_bar setAutoresizesSubviews:YES];
    [env_->action_bar setAutoresizingMask:
           UIViewAutoresizingFlexibleTopMargin |
         UIViewAutoresizingFlexibleWidth];
    [env_->action_bar setBarStyle:UIBarStyleBlackTranslucent];
    [env_->action_bar sizeToFit];
    [env_->action_bar setFrame:CGRectMake(
          0, 0, 0, [env_->action_bar frame].size.height)];
    [env_->action_bar setHidden:YES];

    struct {
      NSString* title;
      SEL selector;
      float width;
      UIColor* tint_color;
    } kEventItems[] = {
      { @"Share", @selector(sharePhotosStart), 90, NULL },
      { @"Unshare", @selector(unsharePhotosConfirm:), 90, NULL},
      { @"Delete", @selector(deletePhotosConfirm:), 90, kDeleteTintColor },
    };

    struct {
      NSString* title;
      SEL selector;
      float width;
      UIColor* tint_color;
    } kPhotoItems[] = {
      { @"Edit", @selector(showEditingControls), 70, NULL},
      { @"Share", @selector(sharePhotosStart), 70, NULL },
      { @"Unshare", @selector(unsharePhotosConfirm:), 70, NULL},
      { @"Delete", @selector(deletePhotosConfirm:), 70, kDeleteTintColor },
    };

    struct {
      NSString* title;
      SEL selector;
      float width;
      UIColor* tint_color;
    } kEditingItems[] = {
      { @"Rotate", NULL, 90, NULL},
      { @"Crop", NULL, 90, NULL},
      { @"Filter", NULL, 90, NULL },
    };

    UIBarButtonItem* flex_space =
        [[UIBarButtonItem alloc]
            initWithBarButtonSystemItem:UIBarButtonSystemItemFlexibleSpace
                                 target:NULL
                                 action:NULL];

    for (int i = 0; i < ARRAYSIZE(kEventItems); ++i) {
      if (env_->action_bar_event_items.size() > 0) {
        env_->action_bar_event_items.push_back(flex_space);
      }

      UIBarButtonItem* item =
          [[UIBarButtonItem alloc]
            initWithTitle:kEventItems[i].title
                    style:UIBarButtonItemStyleBordered
                   target:self
                   action:kEventItems[i].selector];
      [item setWidth:kEventItems[i].width];
      if (kEventItems[i].tint_color) {
        [item setTintColor:kEventItems[i].tint_color];
      }
      [item setEnabled:NO];

      env_->action_bar_event_items.push_back(item);
    }

    for (int i = 0; i < ARRAYSIZE(kPhotoItems); ++i) {
      if (env_->action_bar_photo_items.size() > 0) {
        env_->action_bar_photo_items.push_back(flex_space);
      }

      UIBarButtonItem* item =
          [[UIBarButtonItem alloc]
            initWithTitle:kPhotoItems[i].title
                    style:UIBarButtonItemStyleBordered
                   target:self
                   action:kPhotoItems[i].selector];
      [item setWidth:kPhotoItems[i].width];
      if (kPhotoItems[i].tint_color) {
        [item setTintColor:kPhotoItems[i].tint_color];
      }
      [item setEnabled:NO];

      env_->action_bar_photo_items.push_back(item);
    }

    for (int i = 0; i < ARRAYSIZE(kEditingItems); ++i) {
      if (env_->action_bar_editing_items.size() > 0) {
        env_->action_bar_editing_items.push_back(flex_space);
      }

      UIBarButtonItem* item =
          [[UIBarButtonItem alloc]
            initWithTitle:kEditingItems[i].title
                    style:UIBarButtonItemStyleBordered
                   target:self
                   action:kEditingItems[i].selector];
      [item setWidth:kEditingItems[i].width];
      if (kEditingItems[i].tint_color) {
        [item setTintColor:kEditingItems[i].tint_color];
      }
      [item setEnabled:NO];

      env_->action_bar_editing_items.push_back(item);
    }

    [self.view addSubview:env_->action_bar];
  }

  env_->refresh_header =
      [[UIView alloc] initWithFrame:CGRectMake(
            0, -kRefreshHeaderHeight, 0, kRefreshHeaderHeight)];
  [env_->refresh_header setAutoresizesSubviews:YES];
  [env_->refresh_header setAutoresizingMask:
       UIViewAutoresizingFlexibleLeftMargin |
       UIViewAutoresizingFlexibleRightMargin];
  [env_->refresh_header setBackgroundColor:[UIColor clearColor]];
  [env_->scroll_view addSubview:env_->refresh_header];

  env_->refresh_label = [UILabel new];
  [env_->refresh_label setBackgroundColor:[UIColor clearColor]];
  [env_->refresh_label setFont:kPhotoRefreshLabelFont];
  [env_->refresh_label setTextAlignment:UITextAlignmentCenter];
  [env_->refresh_label setText:kTextPull];
  CGRect f = CGRectZero;
  f.size = [env_->refresh_label sizeThatFits:CGSizeZero];
  f = CGRectOffset(f, -f.size.width / 2, 0);
  f.origin.y = kRefreshHeaderHeight / 2 + 3;
  [env_->refresh_label setFrame:f];
  [env_->refresh_header addSubview:env_->refresh_label];

  env_->refresh_sublabel = [UILabel new];
  [env_->refresh_sublabel setBackgroundColor:[UIColor clearColor]];
  [env_->refresh_sublabel setFont:kPhotoRefreshSublabelFont];
  [env_->refresh_sublabel setTextAlignment:UITextAlignmentCenter];
  [env_->refresh_sublabel setAdjustsFontSizeToFitWidth:YES];
  [env_->refresh_sublabel setText:@"Last updated: 00:00 pm"];
  f = CGRectZero;
  f.size = [env_->refresh_sublabel sizeThatFits:CGSizeZero];
  f = CGRectOffset(f, -f.size.width / 2, 0);
  f.origin.y = (kRefreshHeaderHeight - f.size.height) / 2 - 3;
  [env_->refresh_sublabel setFrame:f];
  [env_->refresh_sublabel setText:NULL];
  [env_->refresh_header addSubview:env_->refresh_sublabel];

  env_->refresh_arrow =
      [[UIImageView alloc] initWithImage:
                     [UIImage imageNamed:@"pull-to-refresh-arrow.png"]];
  [env_->refresh_arrow setFrame:CGRectMake(
        f.origin.x - 22.5, (kRefreshHeaderHeight - 30) / 2,
        11.5, 30)];
  [env_->refresh_arrow setTransform:CGAffineTransformMakeRotation(kPi)];
  [env_->refresh_header addSubview:env_->refresh_arrow];

  env_->refresh_spinner =
      [[UIActivityIndicatorView alloc]
        initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleGray];
  [env_->refresh_spinner setFrame:CGRectMake(
        f.origin.x - 30, (kRefreshHeaderHeight - 20) / 2,
        20, 20)];
  [env_->refresh_spinner setHidesWhenStopped:YES];
  [env_->refresh_header addSubview:env_->refresh_spinner];

  env_->status_label = [UILabel new];
  [env_->status_label setAutoresizingMask:
       UIViewAutoresizingFlexibleTopMargin |
       UIViewAutoresizingFlexibleWidth];
  [env_->status_label setBackgroundColor:MakeUIColor(0, 0, 0, 0.50)];
  [env_->status_label setTextColor:[UIColor whiteColor]];
  [env_->status_label setTextAlignment:UITextAlignmentCenter];
  [env_->status_label setFont:kPhotoRefreshLabelFont];
  [env_->status_label.layer setAnchorPoint:CGPointMake(0.5, 1)];
  [env_->status_label setFrame:CGRectMake(0, 0, 0, 20)];
  [self.view addSubview:env_->status_label];

  // {
  //   MKNumberBadgeView* badge =
  //       [[MKNumberBadgeView alloc]
  //         initWithFrame:CGRectMake(30, 432.5, 20, 20)];
  //   badge.font = [UIFont boldSystemFontOfSize:11];
  //   badge.fillColor = MakeUIColor(0.8549, 0.0314, 0.0706, 1);
  //   badge.value = 1;
  //   LOG("badge size: %.1f", badge.badgeSize);
  //   [self.view addSubview:badge];
  // }
}

- (void)viewDidUnload {
  LOG("photo: view did unload");
  env_->Reset();
  [super viewDidUnload];
}

- (void)viewWillAppear:(BOOL)animated {
  [super viewWillAppear:animated];
  [self viewDidLayoutSubviews];

  env_->state->photo_manager()->EnsureInit();

  // Perform a reload whenever the view appears.
  [self reloadPhotos];

  [env_->state->assets_manager() initialScan];

  if (env_->contact_picker) {
    [env_->contact_picker show];
  }
}

- (void)viewDidAppear:(BOOL)animated {
  [super viewDidAppear:animated];

  [env_->scroll_view flashScrollIndicators];
  if (!env_->group_cache.empty()) {
    for (int i = env_->min_visible_group; i <= env_->max_visible_group; ++i) {
      GroupLayoutData* g = env_->group_cache[i];
      if (g->view) {
        [g->view flashScrollIndicators];
      }
    }
  }
}

- (void)viewWillDisappear:(BOOL)animated {
  if (env_->contact_picker) {
    [env_->contact_picker hide];
  }
  [super viewWillDisappear:animated];
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

- (void)scrollViewDidScroll:(UIScrollView*)scroll_view {
  if (env_->scroll_view == scroll_view) {
    // The toolbar title view scrolls in sync with the main scroll view.
    if (!env_->toolbar.hidden) {
      [env_->toolbar_title_view setContentOffset:scroll_view.contentOffset];
    }

    if (layout_.get()) {
      layout_->UpdateBounds();
    }

    if (!env_->refresh_header.hidden &&
        scroll_view.dragging && scroll_view.contentOffset.y <= 0) {
      // Update the pull to refresh arrow direction and label.
      [UIView animateWithDuration:kDuration
                       animations:^{
          if (!env_->state->net_manager()->network_up()) {
            [env_->refresh_sublabel setText:kTextNetworkDown];
          } else if (!env_->state->logged_in()) {
            [env_->refresh_sublabel setText:kTextNotSignedIn];
          }
          if (!env_->refresh_arrow.hidden) {
            if (scroll_view.contentOffset.y <
                -[env_->refresh_header frame].size.height) {
              // User is scrolling above the header
              [env_->refresh_label setText:kTextRelease];
              [env_->refresh_arrow setTransform:CGAffineTransformIdentity];
            } else {
              // User is scrolling somewhere within the header
              [env_->refresh_label setText:kTextPull];
              [env_->refresh_arrow setTransform:
                     CGAffineTransformMakeRotation(kPi)];
            }
          }
        }];
    }
  }

  if (!layout_.get()) {
    return;
  }

  // if (env_->scroll_view == scroll_view) {
  //   LOG("photo: did scroll (main): offset=%.0f  groups=[%d %d]",
  //       scroll_view.contentOffset,
  //       env_->min_visible_group, env_->max_visible_group);
  // } else {
  //   LOG("photo: did scroll (group %d): offset=%.0f  groups=[%d %d]",
  //       scroll_view.tag, scroll_view.contentOffset,
  //       env_->min_visible_group, env_->max_visible_group);
  // }

  // Disable animations so that we don't animate positioning of the photos
  // below.
  [CATransaction begin];
  [CATransaction setDisableActions:YES];

  // Hide any photos that are no longer visible.
  layout_->MaybeHidePhotos();

  // Show any new photos that are now on screen.
  layout_->MaybeShowPhotos();

  [CATransaction commit];

  // Load any higher-res versions of photos that are necessary 100ms after the
  // most recently scroll.
  ++env_->load_in_progress;
  dispatch_after_main(0.1, ^{
      if (--env_->load_in_progress == 0) {
        layout_->MaybeLoadPhotos();
      }
    });
}

- (void)scrollViewWillBeginDragging:(UIScrollView*)scroll_view {
  if (env_->scroll_view == scroll_view) {
    [env_->viewfinder_tool setEnabled:NO];
    layout_->EnterFullScreen(kDuration);
  }
}

- (void)scrollViewDidEndDragging:(UIScrollView*)scroll_view
                  willDecelerate:(BOOL)decelerate {
  if (env_->scroll_view == scroll_view) {
    if (!env_->refresh_header.hidden &&
        (scroll_view.contentOffset.y <=
         -[env_->refresh_header frame].size.height)) {
      if (env_->state->net_manager()->QueryUpdates()) {
        reload_delayed_ = false;
        [self networkLoadingStart:0.0];
      } else {
        [self reloadPhotos];
      }
    }
  }

  if (!decelerate) {
    [self scrollViewDidEndDecelerating:scroll_view];
  }
}

- (void)scrollViewDidEndDecelerating:(UIScrollView*)scroll_view {
  if (env_->scroll_view == scroll_view) {
    [env_->viewfinder_tool setEnabled:YES];
    layout_->ExitFullScreen(kDuration);
  }
}

- (void)scrollViewWillEndDragging:(UIScrollView*)scroll_view
                     withVelocity:(CGPoint)velocity
              targetContentOffset:(inout CGPoint*)target {
}

- (UIView*)viewForZoomingInScrollView:(UIScrollView*)scroll_view {
  if (env_->scroll_view == scroll_view) {
    return NULL;
  }
  return env_->group_cache[scroll_view.tag]->photos.front()->view;
}

- (void)scrollViewDidZoom:(UIScrollView*)scroll_view {
  if (env_->scroll_view == scroll_view) {
    return;
  }
  layout_->GroupDidZoom(
      env_->group_cache[scroll_view.tag], env_->toolbar.hidden);
}

- (void)handleSingleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  if (!layout_.get()) {
    return;
  }

  const CGPoint p = [recognizer locationInView:env_->content_view];
  PhotoLayoutData* d = [self findPhotoAtPoint:p];

  if (env_->editing()) {
    if (!individual_mode_) {
      layout_->TogglePhoto(d);
    }
    return;
  }

  if (individual_mode_) {
    layout_->ToggleToolbar(kDuration);
    return;
  }

  // If a previous layout animation is still in progress, use the existing
  // target.
  const int64_t target = (target_photo_ != -1) ? target_photo_ :
      (d ? d->photo_id : -1);
  if (target != -1) {
    if (detailed_mode_) {
      individual_mode_ = true;
      env_->state->db()->Put(kIndividualModeKey, individual_mode_);
      if (target_photo_ != -1) {
        // A previous layout animation is still in progress. The user
        // effectively double-tapped. So act like we went straight from summary
        // mode to individual photo mode.
        detailed_mode_ = false;
        env_->state->db()->Put(kDetailedModeKey, detailed_mode_);
      }
    } else {
      detailed_mode_ = true;
      env_->state->db()->Put(kDetailedModeKey, detailed_mode_);
    }

    [self initLayout];

    // Remember the index of the target photo while the layout animation is in
    // progress.
    target_photo_ = target;
    layout_->Layout(target, true, ^{
        target_photo_ = -1;
      });
  }
}

- (void)handleDoubleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  if (!layout_.get() || !individual_mode_) {
    return;
  }

  const CGPoint p = [recognizer locationInView:env_->content_view];
  PhotoLayoutData* target = [self findPhotoAtPoint:p];

  if (target) {
    GroupLayoutData* g = target->group;
    if ([g->view zoomScale] == 1.0) {
      const CGPoint c = [recognizer locationInView:g->view];
      CGRect f = env_->self.view.bounds;
      f.size.width /= [g->view maximumZoomScale];
      f.size.height /= [g->view maximumZoomScale];
      f.origin.x = c.x - f.size.width / 2;
      f.origin.y = c.y - f.size.height / 2;
      [g->view zoomToRect:f animated:YES];
    } else {
      [g->view setZoomScale:1.0 animated:YES];
    }
  }
}

- (void)handleSwipeLeft:(UISwipeGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  const CGPoint p = [recognizer locationInView:env_->content_view];
  layout_->SwipeLeft([self findPhotoAtPoint:p]);
}

- (void)handleSwipeRight:(UISwipeGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  const CGPoint p = [recognizer locationInView:env_->content_view];
  layout_->SwipeRight([self findPhotoAtPoint:p]);
}

- (PhotoLayoutData*)findPhotoAtPoint:(CGPoint)p {
  for (UIView* v in [env_->content_view subviews]) {
    for (PhotoView* u in [v subviews]) {
      if (![u isKindOfClass:[PhotoView class]]) {
        continue;
      }
      PhotoLayoutData* d = u.photo;
      if (!d) {
        continue;
      }
      const CGRect f = [env_->content_view
                           convertRect:[d->view frame]
                              fromView:d->group->view];
      if (CGRectContainsPoint(f, p)) {
        return d;
      }
    }
  }
  return NULL;
}

- (void)initLayout {
  if (individual_mode_) {
    layout_.reset(new IndividualPhotoLayout(env_.get()));
  } else if (detailed_mode_) {
    layout_.reset(new DetailedEventLayout(env_.get()));
  } else {
    layout_.reset(new SummaryEventLayout(env_.get()));
  }
}

- (void)reloadPhotos {
  if (!reload_needed_) {
    return;
  }
  reload_needed_ = false;
  [env_->state->root_view_controller() setEventsReloadNeeded:false];

  // Clear out the existing events. We'll be reconstructing them.
  Clear(&env_->events);

  // Build up a map from local-id to photo layout data and clear out the
  // existing photos. We'll rebuild it below.
  PhotoLayoutMap photo_map(env_->photo_cache);
  env_->photo_cache.clear();
  env_->num_photos = 0;

  // Loop over the events and rebuild the photo and event data.
  EventLayoutMap event_map;
  const PhotoManager::EventMap& events =
      env_->state->photo_manager()->events();
  for (PhotoManager::EventMap::const_iterator iter(events.begin());
       iter != events.end();
       ++iter) {
    const PhotoManager::EventData& event = iter->second;
    if (event.photos.empty()) {
      continue;
    }

    EventLayoutData*& e =
        event_map[event.metadata.id().local_id()];
    if (!e) {
      e = new EventLayoutData(event.metadata);
      env_->events.push_back(e);
    }

    for (int i = 0; i < event.photos.size(); ++i) {
      const PhotoManager::PhotoData* p = event.photos[i];
      PhotoLayoutData* d = FindOrNull(photo_map, p->metadata.id().local_id());
      if (d) {
        photo_map.erase(d->photo_id);
        env_->photo_cache[d->photo_id] = d;
      }
      e->photos.push_back(p->metadata.id().local_id());
      ++env_->num_photos;
    }
  }

  // Clear (delete) any photo data that was not reused.
  for (PhotoLayoutMap::iterator iter(photo_map.begin());
       iter != photo_map.end();
       ++iter) {
    PhotoLayoutData* d = iter->second;
    if (d->view) {
      layout_->RecyclePhotoView(d->view);
      d->view = NULL;
    }
    env_->selection.erase(d);
  }
  Clear(&photo_map);

  // Sort the events by the most recent photo in the event.
  std::sort(env_->events.begin(), env_->events.end(),
            EventByTimestamp());

  if (!layout_.get()) {
    [self initLayout];
  }
  layout_->Layout(-1, true);
}

- (void)assetLoadingProgress:(int)progress {
  if (env_->events.empty()) {
    [env_->viewfinder_tool setHidden:YES];
    [env_->state->root_view_controller() showTabBar:false];
  }
  [self statusMessage:Format("Scanning: %d photo%s",
                             progress, Pluralize(progress))
             autohide:false];
}

- (void)assetLoadingStop {
  if (env_->events.empty()) {
    [env_->viewfinder_tool setHidden:NO];
    [env_->state->root_view_controller() showTabBar:env_->show_tabbar];
    [self reloadPhotos];
  }
  [self updateStatus];
}

- (void)networkLoadingStart:(float)delay {
  if (!env_->refresh_header.hidden) {
    [UIView animateWithDuration:0.2
                          delay:delay
                        options:UIViewAnimationOptionBeginFromCurrentState
                     animations:^{
        [env_->scroll_view setContentInset:UIEdgeInsetsMake(
              [env_->refresh_header frame].size.height, 0, 0, 0)];
        [env_->refresh_label setText:kTextLoading];
        [env_->refresh_arrow setHidden:YES];
        [env_->refresh_spinner startAnimating];
      }
                     completion:NULL];
  }
}

- (void)networkLoadingStop {
  if (env_->events.empty()) {
    [self reloadPhotos];
  }
  if (!env_->refresh_header.hidden) {
    [UIView animateWithDuration:0.2
                          delay:0.0
                        options:UIViewAnimationOptionBeginFromCurrentState
                     animations:^{
        [env_->scroll_view setContentInset:UIEdgeInsetsZero];
      }
                     completion:^(BOOL finished) {
        [env_->refresh_arrow setHidden:NO];
        [env_->refresh_spinner stopAnimating];
      }];
  }
}

- (void)updateStatus {
  if (env_->state->assets_manager().scanning) {
    return;
  } else if (!env_->state->net_manager()->network_up()) {
    [self statusMessage:Format("Offline")
               autohide:false];
  } else if (!env_->state->logged_in()) {
    [self statusMessage:Format("Not signed in")
               autohide:false];
  } else {
    [self statusMessage:env_->state->net_manager()->status()
               autohide:env_->state->net_manager()->status_autohide()];
  }
}

- (void)statusMessage:(const string)message
             autohide:(bool)autohide {
  if (message.empty()) {
    autohide = true;
  }
  const int64_t status_id = ++env_->next_status_id;

  // Wait 50ms before displaying the message, so that if another message comes
  // in within that time, we don't cause flickering of the status label.
  dispatch_after_main(0, ^{
      if (status_id != env_->next_status_id) {
        // Another status message came in and replaced this one.
        return;
      }
      if (message == ToSlice(env_->status_label.text)) {
        // Nothing has changed.
        return;
      }

      env_->status_autohide = autohide;
      [env_->status_label setText:NewNSString(message)];

      if (env_->status_label.hidden) {
        return;
      }

      CGRect f = env_->status_label.frame;
      if (f.origin.y == self.view.bounds.size.height) {
        UITabBar* tabbar = env_->state->root_view_controller().tabbar;
        [env_->status_label setFrame:CGRectMake(
              0, tabbar.frame.origin.y - f.size.height,
              f.size.width, f.size.height)];
        [env_->status_label setTransform:CGAffineTransformMakeScale(1, 0.0001)];
      }

      [UIView animateWithDuration:kDuration * env_->animation_scale
                            delay:0
                          options:UIViewAnimationOptionBeginFromCurrentState
                       animations:^{
          [env_->status_label setTransform:CGAffineTransformMakeScale(1, 1)];
        }
                       completion:^(BOOL finished) {
          if (!finished) {
            return;
          }
          [self statusAutoHide:status_id];
        }];
    });
}

- (void)statusAutoHide:(const int64_t)status_id {
  if (!env_->status_autohide || status_id != env_->next_status_id) {
    return;
  }
  dispatch_after_main(2, ^{
      if (status_id != env_->next_status_id) {
        return;
      }
      [UIView animateWithDuration:kDuration * env_->animation_scale
                            delay:0
                          options:UIViewAnimationOptionBeginFromCurrentState
                       animations:^{
          [env_->status_label setTransform:CGAffineTransformMakeScale(1, 0.0001)];
        }
                       completion:NULL];
    });
}

- (void)popLayout {
  if (!detailed_mode_ && !individual_mode_) {
    return;
  }
  if (individual_mode_) {
    individual_mode_ = false;
  } else {
    detailed_mode_ = false;
  }

  DB::Batch updates;
  updates.Put(kDetailedModeKey, detailed_mode_);
  updates.Put(kIndividualModeKey, individual_mode_);
  env_->state->db()->Put(updates);

  int64_t target = -1;
  if (env_->min_visible_group >= 0 &&
      env_->min_visible_group < env_->num_groups) {
    GroupLayoutData* g = env_->group_cache[env_->min_visible_group];
    target = g->photos.front()->photo_id;
  }

  [self initLayout];
  layout_->Layout(target, true);
}

- (void)showActionControls {
  layout_->ShowActionControls(kDuration);
  env_->UpdateAnimationScale();
}

- (void)hideActionControls {
  layout_->HideActionControls(kDuration);
  env_->UpdateAnimationScale();
}

- (void)showEditingControls {
  layout_->ShowEditingControls(kDuration);
  env_->UpdateAnimationScale();
}

- (void)savePhotoEdits {
  [self hideActionControls];
}

- (void)sharePhotosStart {
  if (env_->selection.empty()) {
    LOG("photo: share photos: selection empty");
    return;
  }

  // TODO(pmattis): Deselect photos that are not shareable.

  layout_->ShowShareControls(kDuration);

  env_->contact_picker =
      [[ContactPicker alloc] initWithState:env_->state];
  [env_->contact_picker changed]->Add(^{
      if ([env_->contact_picker numPicked] == 0) {
        [env_->toolbar_share_items[0] setEnabled:NO];
      } else {
        [env_->toolbar_share_items[0] setEnabled:YES];
      }
    });
  [env_->contact_picker changed]->Run();
  const float y = CGRectGetMaxY([env_->toolbar frame]);
  [env_->contact_picker setFrame:CGRectMake(
        0, y, self.view.bounds.size.width,
        self.view.bounds.size.height - y)];
  [self.view addSubview:env_->contact_picker];
  [env_->contact_picker show];

  if (!env_->state->logged_in()) {
    UIAlertView* alert =
        [[UIAlertView alloc]
          initWithTitle:@"Who Are You?"
                message:
            @"I need to know who your friends are in order to share with them."
               delegate:self
          cancelButtonTitle:@"No Thanks"
          otherButtonTitles:@"Sign In", nil];
    [alert show];
  }
}

- (void)sharePhotosFinish {
  vector<int64_t> photo_ids;
  for (SelectionSet::iterator iter(env_->selection.begin());
       iter != env_->selection.end();
       ++iter) {
    PhotoLayoutData* d = *iter;
    photo_ids.push_back(d->photo_id);
  }

  const ContactManager::ContactVec contacts([env_->contact_picker picked]);
  LOG("photo: share %d photo%s with %d contact%s",
      photo_ids.size(), Pluralize(photo_ids.size()),
      contacts.size(), Pluralize(contacts.size()));
  env_->state->photo_manager()->SharePhotos(photo_ids, contacts);

  [self hideActionControls];
}

- (void)unsharePhotosConfirm:(id)sender {
  // TODO(pmattis): Only enable the unshare button if the photos have been
  // shared.

  deleting_ = false;

  string s = "Unshare ";
  if (env_->selection.size() > 1) {
    s += Format("%d Photo", env_->selection.size());
  } else {
    s += "Photo";
  }

  UIActionSheet* confirm =
      [[UIActionSheet alloc]
        initWithTitle:NULL
             delegate:self
        cancelButtonTitle:@"Cancel"
        destructiveButtonTitle:NewNSString(s)
        otherButtonTitles:NULL];
  [confirm setActionSheetStyle:UIActionSheetStyleBlackOpaque];
  [confirm showFromBarButtonItem:sender animated:YES];
}

- (void)unsharePhotosFinish {
  std::vector<int64_t> photo_ids;
  for (SelectionSet::iterator iter(env_->selection.begin());
       iter != env_->selection.end();
       ++iter) {
    PhotoLayoutData* d = *iter;
    photo_ids.push_back(d->photo_id);
  }
  env_->state->photo_manager()->UnsharePhotos(photo_ids);
}

- (void)deletePhotosConfirm:(id)sender {
  deleting_ = true;

  string s = "Delete ";
  if (env_->selection.size() > 1) {
    s += Format("%d Photos", env_->selection.size());
  } else {
    s += "Photo";
  }

  UIActionSheet* confirm =
      [[UIActionSheet alloc]
        initWithTitle:NULL
             delegate:self
        cancelButtonTitle:@"Cancel"
        destructiveButtonTitle:NewNSString(s)
        otherButtonTitles:NULL];
  [confirm setActionSheetStyle:UIActionSheetStyleBlackOpaque];
  [confirm showFromBarButtonItem:sender animated:YES];
}

- (void)deletePhotosFinish {
  std::vector<int64_t> photo_ids;
  for (SelectionSet::iterator iter(env_->selection.begin());
       iter != env_->selection.end();
       ++iter) {
    PhotoLayoutData* d = *iter;
    photo_ids.push_back(d->photo_id);
  }

  // Delete the photos from the layout data.
  for (SelectionSet::iterator iter(env_->selection.begin());
       iter != env_->selection.end();
       ++iter) {
    PhotoLayoutData* d = *iter;
    EventLayoutData* e = d->group->event;

    for (int i = 0; i < e->photos.size(); ++i) {
      if (e->photos[i] == d->photo_id) {
        e->photos.erase(e->photos.begin() + i);
        break;
      }
    }
    if (e->photos.empty()) {
      for (int i = 0; i < env_->events.size(); ++i) {
        if (env_->events[i] == e) {
          env_->events.erase(env_->events.begin() + i);
          break;
        }
      }
    }

    env_->photo_cache.erase(d->photo_id);

    if (d->view) {
      layout_->RecyclePhotoView(d->view);
      d->view = NULL;
    }
    delete d;
  }
  env_->selection.clear();

  layout_->Layout(-1, true);

  // Delete the photos from the database.
  env_->state->photo_manager()->DeletePhotos(photo_ids);
}

- (void)actionSheet:(UIActionSheet*)sheet
clickedButtonAtIndex:(NSInteger)index {
  if (index == 0) {
    if (deleting_) {
      [self deletePhotosFinish];
    } else {
      [self unsharePhotosFinish];
    }
    [self hideActionControls];
  }
}

- (void)alertView:(UIAlertView*)alert
clickedButtonAtIndex:(NSInteger)index {
  [alert dismissWithClickedButtonIndex:index animated:YES];
  if (index == 1) {
    [env_->state->root_view_controller() showSettings];
  }
}

- (void)viewfinderBegin {
  [env_->content_overlay layer].zPosition = 10;
  [env_->content_overlay setHidden:NO];
  [env_->content_overlay setBackgroundColor:[UIColor blackColor]];
  layout_->EnterFullScreen(kDuration);

  const float group_height = env_->self.view.bounds.size.width / 2;

  vector<EventInfo> events;
  for (int i = 0; i < env_->events.size(); ++i) {
    EventLayoutData* e = env_->events[i];
    events.push_back(EventInfo(e->timestamp, (group_height + kEventSpacing) * i,
                               e->photos.front(), e->photos.size()));
  }
  [env_->viewfinder_tool setEvents:events];
  [env_->content_overlay setAlpha:[env_->viewfinder_tool opacity]];
}

- (void)viewfinderEnd {
  [self viewfinderUpdate];
  [self viewfinderCancel];
}

- (void)viewfinderCancel {
  [env_->content_overlay setAlpha:0];
  layout_->ExitFullScreen(kDuration);
}

- (void)viewfinderUpdate {
  const float max_y_offset = std::max<float>(
      0, [env_->content_view frame].size.height - self.view.bounds.size.height);
  CGPoint offset = [env_->scroll_view contentOffset];
  offset.y = std::min<float>(
      max_y_offset, [env_->viewfinder_tool position]);
  [env_->scroll_view setContentOffset:offset];
  [env_->content_overlay setAlpha:[env_->viewfinder_tool opacity]];
}

@end  // OldPhotoViewController
