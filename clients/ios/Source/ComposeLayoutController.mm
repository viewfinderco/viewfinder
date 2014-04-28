// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <QuartzCore/QuartzCore.h>
#import "AttrStringUtils.h"
#import "Breadcrumb.pb.h"
#import "CALayer+geometry.h"
#import "CppDelegate.h"
#import "ComposeLayoutController.h"
#import "CompositeTextLayers.h"
#import "ConversationLayoutController.h"
#import "DBFormat.h"
#import "InitialScanPlaceholderView.h"
#import "LocationTracker.h"
#import "Logging.h"
#import "MathUtils.h"
#import "Mutex.h"
#import "PlacemarkHistogram.h"
#import "RootViewController.h"
#import "StatusBar.h"
#import "Timer.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kComposeTutorialAddPeopleTopMargin = 82;
const float kComposeTutorialAddTitleTopMargin = 126;
const float kComposeTutorialPhotosTopMargin = 4;
const float kComposeTutorialSearchTopMargin = 162;
const float kComposeTutorialSuggestionsBottomMargin = 12;

const float kEventWidth = 284;
const float kEventOffset = 18;
const float kEventBottomMargin = 12;

const WallTime kLoadImagesDelay = 0.1;
const WallTime kLoadThumbnailsWaitTime = 0.025;

const float kSuggestionOverlayTopMargin = 49;
const float kSuggestionLocationBaseline = 80;
const float kSuggestionDateBaseline = 101;
const float kSuggestionTextLeftMargin = 53;
const float kSuggestionTextWidth = 210;
const WallTime kSuggestionOverlayFadeDuration = 0.500;
const WallTime kAutoSuggestionMaxLastViewed = 60 * 60 * 24 * 7;  // 1 week before resetting last_viewed
const WallTime kAutoSuggestionSharedMultiplier = 0.25;  // already-shared events have weights decreased
//const WallTime kAutoSuggestionScrollDuration = 0.750;

const float kFollowersWidth = 320;
const float kFollowersHeight = 44;

const float kTitleWidth = 240;
const float kTitleHeight = 44;
const float kTitleLeftMargin = 40;
const float kTitleTopMargin = 10;
const float kTitleBottomMargin = 10;

const float kUseCameraLeftMargin = 6;
const float kUseCameraRightMargin = 6;
const float kUseCameraTopMargin = 48;
const float kUseCameraBottomMargin = 15;
const float kUseCameraLocationDateLeftMargin = 34;
const float kUseCameraLocationDateTopMargin = 14;
const float kUseCameraLocationsOKRightMargin = 6;
const float kUseCameraLocationsOKTopMargin = 4;
const float kUseCameraLocationLeftMargin = 6;
const float kUseCameraLocationTopMargin = 14;
const float kuseCameraLocationsEnabledLeftMargin = 2;
const float kuseCameraLocationsEnabledTopMargin = 12;

LazyStaticCTFont kTitleFont = {
  kProximaNovaSemibold, 17
};

LazyStaticCTFont kTitlePlaceholderFont = {
  kProximaNovaRegular, 17
};

LazyStaticUIFont kSuggestionLocationFont = {
  kProximaNovaBold, 16
};

LazyStaticUIFont kSuggestionDateFont = {
  kProximaNovaRegular, 14
};

LazyStaticUIFont kUseCameraButtonFont = {
  kProximaNovaSemibold, 16
};

LazyStaticUIFont kUseCameraLocationFont = {
  kProximaNovaBold, 12
};

LazyStaticUIFont kUseCameraLocationsOKFont = {
  kProximaNovaRegular, 12
};

LazyStaticUIFont kUseCameraDateFont = {
  kProximaNovaRegularItalic, 12
};

LazyStaticHexColor kSuggestionOverlayColor = { "#ffffff" };

LazyStaticHexColor kDividerColor = { "#bfbbbb" };
LazyStaticHexColor kSearchBarPinnedBGColor = { "#cfcbcb" };
LazyStaticHexColor kSearchBarUnpinnedBGColor = { "#cfcbcb" };
LazyStaticHexColor kSearchBarBorderColor = { "#9f9c9c" };
LazyStaticHexColor kTitleColor = { "#3f3e3e" };
LazyStaticHexColor kTitlePlaceholderColor = { "#cfcbcb" };
LazyStaticHexColor kUseCameraBoundaryColor = { "#9f9c9c" };
LazyStaticHexColor kUseCameraButtonColor = { "#2070aa" };
LazyStaticHexColor kUseCameraDateColor = { "#9f9c9c" };
LazyStaticHexColor kUseCameraLocationColor = { "#3f3e3e" };
LazyStaticHexColor kUseCameraLocationsOKColor = { "#2070aa" };

LazyStaticDict kTitleAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)kTitleFont.get(),
        kCTForegroundColorAttributeName,
        (__bridge id)kTitleColor.get().CGColor);
  }
};

LazyStaticDict kTitlePlaceholderAttributes = {^{
    return Dict(
        kCTFontAttributeName,
        (__bridge id)kTitlePlaceholderFont.get(),
        kCTForegroundColorAttributeName,
        (__bridge id)kTitlePlaceholderColor.get().CGColor);
  }
};

LazyStaticImage kComposeTutorialAddPeople(
    @"compose-tutorial-01.png");
LazyStaticImage kComposeTutorialAddTitle(
    @"compose-tutorial-02.png");
LazyStaticImage kComposeTutorialPhotos(
    @"compose-tutorial-03.png");
LazyStaticImage kComposeTutorialSearch(
    @"compose-tutorial-05.png");
LazyStaticImage kComposeTutorialSuggestions(
    @"compose-tutorial-04.png");
LazyStaticImage kConvoButtonLocationsOK(
    @"convo-button-locations-ok.png");
LazyStaticImage kConvoButtonLocationsOKActive(
    @"convo-button-locations-ok-active.png");
LazyStaticImage kConvoIconCamera(
    @"convo-icon-camera.png");
LazyStaticImage kConvoIconLocationOff(
    @"convo-icon-location-off.png");
LazyStaticImage kConvoIconLocationOn(
    @"convo-icon-location-on.png");
LazyStaticImage kConvoTitleIcon(
    @"convo-title-icon.png");
LazyStaticImage kSuggestionOverlay(
    @"suggestion-overlay.png");

const string kComposeAutosuggestKeyPrefix = DBFormat::compose_autosuggest_key("");
const string kComposeTutorialKey = DBFormat::metadata_key("compose_tutorial");

string EncodeComposeAutosuggestKey(int64_t episode_id, WallTime last_viewed) {
  string s;
  OrderedCodeEncodeVarint64(&s, episode_id);
  OrderedCodeEncodeVarint32(&s, last_viewed);
  return DBFormat::compose_autosuggest_key(s);
}

bool DecodeComposeAutosuggestKey(Slice key, int64_t* episode_id, WallTime* last_viewed) {
  if (!key.starts_with(kComposeAutosuggestKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kComposeAutosuggestKeyPrefix.size());
  *episode_id = OrderedCodeDecodeVarint64(&key);
  *last_viewed = OrderedCodeDecodeVarint32(&key);
  return true;
}

const DBRegisterKeyIntrospect kComposeAutosuggestKeyIntrospect(
    kComposeAutosuggestKeyPrefix, [](Slice key) {
      int64_t episode_id;
      WallTime last_viewed;
      if (!DecodeComposeAutosuggestKey(key, &episode_id, &last_viewed)) {
        return string();
      }
      return string(Format("%d/%s", episode_id, DBIntrospect::timestamp(last_viewed)));
    }, NULL);

UIButton* NewLocationsOKButton(id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  [b setImage:kConvoButtonLocationsOK
     forState:UIControlStateNormal];
  [b setImage:kConvoButtonLocationsOKActive
     forState:UIControlStateHighlighted];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  [b sizeToFit];
  return b;
}

UIButton* NewTutorialButton(id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return b;
}

UIButton* NewUseCameraButton(id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  [b setImage:kConvoIconCamera
     forState:UIControlStateNormal];
  b.titleLabel.font = kUseCameraButtonFont;
  [b setTitle:@"Use Camera"
     forState:UIControlStateNormal];
  [b setTitleColor:kUseCameraButtonColor.get()
          forState:UIControlStateNormal];

  const CGSize size =
      [[b titleForState:UIControlStateNormal] sizeWithFont:kUseCameraButtonFont];
  const float image_inset = (size.width - kConvoIconCamera.get().size.width) / 2;
  [b setImageEdgeInsets:UIEdgeInsetsMake(
        0, image_inset, size.height, image_inset)];
  [b setTitleEdgeInsets:UIEdgeInsetsMake(
        kConvoIconCamera.get().size.height, -kConvoIconCamera.get().size.width, 0, 0)];
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  b.frameSize = CGSizeMake(size.width, size.height + kConvoIconCamera.get().size.height);
  return b;
}

}  // namespace

@interface CameraEvent : UIView {
 @private
  UIAppState* state_;
  bool locations_on_;
  UILabel* location_and_date_;
  UILabel* turn_on_locations_;
  UIButton* locations_ok_;
  UIImageView* locations_enabled_;
  UIButton* use_camera_;
}

- (id)initWithState:(UIAppState*)state;

@end  // CameraEvent

@implementation CameraEvent

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;

    locations_on_ = false /* check location auth */;

    self.backgroundColor = [UIColor whiteColor];

    use_camera_ = NewUseCameraButton(self, @selector(useCamera));
    [self addSubview:use_camera_];

    NSMutableAttributedString* str = NewAttrString(
        "Turn on Locations ", kUseCameraLocationFont, kUseCameraLocationsOKColor);
    AppendAttrString(
        str, "to improve\nphoto groups and suggestions",
        kUseCameraLocationsOKFont, kUseCameraLocationsOKColor);
    turn_on_locations_ = [UILabel new];
    turn_on_locations_.attributedText = str;
    turn_on_locations_.numberOfLines = 2;
    [turn_on_locations_ sizeToFit];
    [self addSubview:turn_on_locations_];

    locations_ok_ = NewLocationsOKButton(self, @selector(locationsOK));
    [self addSubview:locations_ok_];

    locations_enabled_ = [[UIImageView alloc] initWithImage:kConvoIconLocationOff];
    [self addSubview:locations_enabled_];

    location_and_date_ = [UILabel new];
    location_and_date_.numberOfLines = 2;
    [self addSubview:location_and_date_];

    locations_on_ = state_->location_tracker().authorized;

    // Make sure we notice when locations are authorized.
    state_->location_tracker().authorizationDidChange->Add(^(bool authorized){
        locations_on_ = authorized;
        [self configureLocationAndDate];
      });

    // Any time there is a newly geocoded-breadcrumb, update.
    state_->location_tracker().breadcrumbDidBecomeAvailable->Add(^{
        [self configureLocationAndDate];
      });
  }
  return self;
}

- (void)layoutSubviews {
  [super layoutSubviews];

  [use_camera_ centerFrameWithinFrame:self.eventFrame];

  locations_enabled_.frameLeft = kuseCameraLocationsEnabledLeftMargin;
  locations_enabled_.frameTop = kuseCameraLocationsEnabledTopMargin;

  location_and_date_.frameLeft = kUseCameraLocationDateLeftMargin;
  location_and_date_.frameTop = kUseCameraLocationDateTopMargin;

  turn_on_locations_.frameLeft = kUseCameraLocationLeftMargin;
  turn_on_locations_.frameTop = kUseCameraLocationTopMargin;

  locations_ok_.frameRight = self.boundsWidth - kUseCameraLocationsOKRightMargin;
  locations_ok_.frameTop = kUseCameraLocationsOKTopMargin;

  [self configureLocationAndDate];
}

- (void)drawRect:(CGRect)rect {
  CGContextRef context = UIGraphicsGetCurrentContext();

  const float dash_lengths[] = {4, 3};
  CGContextSetLineDash(context, 0, dash_lengths, 2);
  CGContextSetLineWidth(context, 1);
  CGContextSetStrokeColorWithColor(context, kUseCameraBoundaryColor);

  const float radius = 5.0;
  const CGRect r = self.eventFrame;

  float minx = CGRectGetMinX(r);
  float midx = CGRectGetMidX(r);
  float maxx = CGRectGetMaxX(r);
  float miny = CGRectGetMinY(r);
  float midy = CGRectGetMidY(r);
  float maxy = CGRectGetMaxY(r);

  CGContextMoveToPoint(context, minx, midy);
  CGContextAddArcToPoint(context, minx, miny, midx, miny, radius);
  CGContextAddArcToPoint(context, maxx, miny, maxx, midy, radius);
  CGContextAddArcToPoint(context, maxx, maxy, midx, maxy, radius);
  CGContextAddArcToPoint(context, minx, maxy, minx, midy, radius);
  CGContextClosePath(context);

  CGContextStrokePath(context);
}

- (CGRect)eventFrame {
  return CGRectMake(kUseCameraLeftMargin, kUseCameraTopMargin,
                    self.frameWidth - kUseCameraLeftMargin - kUseCameraRightMargin,
                    self.frameHeight - kUseCameraTopMargin - kUseCameraBottomMargin);
}

- (void)configureLocationAndDate {
  locations_enabled_.hidden = !locations_on_;
  location_and_date_.hidden = !locations_on_;

  turn_on_locations_.hidden = locations_on_;
  locations_ok_.hidden = locations_on_;

  if (locations_on_) {
    const Breadcrumb* b = state_->last_breadcrumb();
    const bool locations_enabled = b && (!b->placemark().country().empty() ||
                                         !b->placemark().state().empty() ||
                                         !b->placemark().locality().empty() ||
                                         !b->placemark().sublocality().empty());
    locations_enabled_.image = locations_enabled ? kConvoIconLocationOn : kConvoIconLocationOff;

    string loc_str;
    if (locations_enabled) {
      state_->placemark_histogram()->FormatLocation(b->location(), b->placemark(), false, &loc_str);
    } else {
      loc_str = "Location Unavailable";
    }
    const WallTime now = state_->WallTime_Now();
    const WallTime ts = locations_enabled ? b->timestamp() : now;
    const string date_str = FormatTimeRange(ts, now);

    NSMutableAttributedString* str = NewAttrString(
        Format("%s\n", loc_str), kUseCameraLocationFont, kUseCameraLocationColor);
    AppendAttrString(str, date_str, kUseCameraDateFont, kUseCameraDateColor);

    location_and_date_.attributedText = str;
    [location_and_date_ sizeToFit];
  }
}

- (void)useCamera {
  ControllerTransition transition(TRANSITION_SHOW_FROM_RECT);
  transition.rect = use_camera_.frame;
  [state_->root_view_controller() showCamera:transition];
}

- (void)locationsOK {
  [state_->location_tracker() ensureInitialized];
  [state_->location_tracker() start];
}

@end  // CameraEvent

@implementation ComposeLayoutController

@synthesize allContacts = all_contacts_;

- (id)initWithState:(UIAppState*)state {
  if (self = [super initWithState:state]) {
    self.wantsFullScreenLayout = YES;

    need_rebuild_ = false;
    initialized_ = false;
    toolbar_offscreen_ = false;
    autosuggestions_initialized_ = false;
    edit_mode_ = EDIT_MODE_NONE;

    tutorial_mode_ = static_cast<ComposeTutorialMode>(
        state_->db()->Get<int>(kComposeTutorialKey, COMPOSE_TUTORIAL_ADD_PEOPLE));

    // Receive notifications for refreshes to day metadata.
    state_->day_table()->update()->Add(^{
        need_rebuild_ = true;
        // Wait for a fraction of a second before rebuilding in case the day
        // table update causes a viewpoint transition.
        [self maybeRebuildSummary:0.001];
      });

    __weak ComposeLayoutController* weak_self = self;
    photo_queue_.name = "compose";
    photo_queue_.block = [^(vector<PhotoView*>* q) {
        [weak_self photoLoadPriorityQueue:q];
      } copy];
  }
  return self;
}

- (void)setAllContacts:(ContactManager::ContactVec)all_contacts {
  all_contacts_ = all_contacts;
  // Need to clear the followers view in order to reset the label text
  // for next contacts.
  [followers_ clear];
}

- (bool)statusBarLightContent {
  return true;
}

// Build the sorted list of auto-suggestions.
- (void)initAutoSuggestions {
  if (autosuggestions_initialized_) {
    return;
  }
  autosuggestions_initialized_ = true;
  weighted_indexes_.clear();
  searching_weighted_index_ = 0;
  current_weighted_index_ = 0;

  // First, build a map of last viewed timestamps.
  std::unordered_map<int64_t, WallTime> last_viewed_map;
  for (DB::PrefixIterator iter(state_->db(), kComposeAutosuggestKeyPrefix);
       iter.Valid();
       iter.Next()) {
    int64_t episode_id;
    WallTime last_viewed;
    if (DecodeComposeAutosuggestKey(iter.key(), &episode_id, &last_viewed)) {
      last_viewed_map[episode_id] = last_viewed;
    } else {
      state_->db()->Delete(iter.key());
    }
  }

  // Next, iterate over all events and blend event weight with last viewed timestamp.
  const WallTime now = state_->WallTime_Now();
  for (int i = 0; i < self.numEvents; ++i) {
    SummaryRow row;
    if (![self getSummaryRow:i row:&row]) {
      continue;
    }
    const WallTime last_viewed = FindOrDefault(last_viewed_map, row.episode_id(), 0);
    const float time_weight =
        std::min<WallTime>(kAutoSuggestionMaxLastViewed, now - last_viewed) /
        kAutoSuggestionMaxLastViewed;
    const float share_weight = row.share_count() > 0 ? kAutoSuggestionSharedMultiplier : 1.0;
    const float weight = row.weight() * time_weight * share_weight;
    weighted_indexes_.push_back(WeightedIndex(weight, i));
  }

  // Finally, sort the weighted indexes from greatest to least.
  std::sort(weighted_indexes_.begin(), weighted_indexes_.end(),
            std::greater<WeightedIndex>());
}

// Rebuild the summary if there were changes and the user is not active.
- (void)maybeRebuildSummary:(double)delay {
  if (!state_->day_table()->initialized()) {
    return;
  }
  dispatch_after_main(delay, ^{
      if (self.visible && need_rebuild_) {
        [self rebuild:false];
      }
    });
}

- (bool)resetSnapshot:(bool)force {
  const int old_epoch = day_table_epoch_;
  snapshot_ = state_->day_table()->GetSnapshot(&day_table_epoch_);
  if (old_epoch == day_table_epoch_ && !force) {
    // Nothing to do.
    return false;
  }
  if (self.searching) {
    search_results_.clear();
    PopulateEventSearchResults(
        state_, snapshot_->events(), &search_results_, search_field_.searchQuery, &row_index_map_);
  }
  autosuggestions_initialized_ = false;
  return true;
}

- (void)clearEvents {
  for (ComposeEventMap::iterator iter(event_map_.begin());
       iter != event_map_.end();
       ++iter) {
    ComposeEvent& ev = iter->second;
    [ev.scroll removeFromSuperview];
  }
  event_map_.clear();
}

- (void)rebuild:(bool)force {
  if (!state_->app_active() || ![self resetSnapshot:force]) {
    return;
  }

  const ScopedDisableCAActions disable_ca_actions;

  // Store any photo views during rebuild so we don't needlessly recreate them.
  BuildPhotoViewMap(state_->photo_view_map(), self.view);

  // Clear existing data structures and views.
  [self clearEvents];

  [self updateToolbar];
  [self updateNavbar];

  // Show visible events.
  event_scroll_.contentSize =
      CGSizeMake(kEventWidth * self.numEvents + kEventOffset * 2, event_scroll_.boundsHeight);
  [self scrollViewDidScroll:event_scroll_];

  state_->photo_view_map()->clear();
}

- (bool)searching {
  return search_field_.searching;
}

- (int)numEvents {
  if (self.searching) {
    return search_results_.size();
  } else {
    return snapshot_.get() ? snapshot_->events()->row_count() : 0;
  }
}

- (int)currentEventIndex {
  return std::max<int>(0, int(event_scroll_.contentOffsetX / kEventWidth));
}

- (int64_t)currentEpisodeId {
  const int cur_event_index = self.currentEventIndex;
  SummaryRow row;
  if ([self getSummaryRow:cur_event_index row:&row]) {
    return row.episode_id();
  }
  return 0;
}

- (EventRange)eventRange:(CGRect)bounds {
  const int start = (CGRectGetMinX(bounds) - kEventOffset) / kEventWidth;
  const int end = (CGRectGetMaxX(bounds) - kEventOffset) / kEventWidth;
  return EventRange(std::max<int>(0, std::min<int>(self.numEvents - 1, start)),
                    std::max<int>(0, std::min<int>(self.numEvents - 1, end)));
}

- (CGRect)eventBounds:(int)event_index {
  return CGRectMake(kEventOffset + event_index * kEventWidth, 0,
                    kEventWidth, event_scroll_.boundsHeight);
}

- (CGRect)visibleBounds {
  /*
  CALayer* layer = (CALayer*)event_scroll_.layer.presentationLayer;
  if (layer.frame.size.width == 0 &&
      layer.frame.size.height == 0) {
    layer = event_scroll_.layer;
  }
  return layer.bounds;
  */
  return event_scroll_.bounds;
}

- (CGRect)cacheBounds {
  return CGRectInset(self.visibleBounds, -kEventWidth, 0);
}

- (bool)zeroState {
  return snapshot_.get() &&
      ([self numEvents] == 0 || state_->fake_zero_state());
}

- (int)getNextAutoSuggestIndex {
  int event_index = 0;
  if (self.searching) {
    event_index = weighted_indexes_[searching_weighted_index_].second;
    searching_weighted_index_ = (searching_weighted_index_ + 1) % weighted_indexes_.size();
  } else {
    event_index = weighted_indexes_[current_weighted_index_].second;
    current_weighted_index_ = (current_weighted_index_ + 1) % weighted_indexes_.size();
  }
  return event_index;
}

- (bool)getSummaryRow:(int)index
                  row:(SummaryRow*)row {
  if (self.searching) {
    if (index < 0 || index >= search_results_.size()) {
      return false;
    }
    row->CopyFrom(search_results_[index]);
    return true;
  } else {
    return snapshot_->events()->GetSummaryRow(index, row);
  }
}

- (void)createSuggestionOverlay:(const EventHandle&)evh {
  if (suggestion_overlay_) {
    [suggestion_overlay_ removeFromSuperview];
  }
  suggestion_overlay_ = [[UIImageView alloc] initWithImage:kSuggestionOverlay];
  suggestion_overlay_.frameTop = event_scroll_.frameTop + kSuggestionOverlayTopMargin;
  [self.view addSubview:suggestion_overlay_];

  UILabel* location = [UILabel new];
  location.text = NewNSString(evh->FormatLocation(false, false));
  location.font = kSuggestionLocationFont;
  location.textColor = kSuggestionOverlayColor;
  location.textAlignment = NSTextAlignmentCenter;
  location.lineBreakMode = NSLineBreakByTruncatingTail;
  [location sizeToFit];
  location.frameWidth = kSuggestionTextWidth;
  location.frameLeft = kSuggestionTextLeftMargin;
  location.frameTop = kSuggestionLocationBaseline - kSuggestionLocationFont.get().ascender;
  [suggestion_overlay_ addSubview:location];

  UILabel* date = [UILabel new];
  date.numberOfLines = 0;
  date.text = Format("%s\n%s", WallTimeFormat("%A", evh->latest_timestamp()),
                     WallTimeFormat("%B %e, %Y", evh->latest_timestamp()));
  date.font = kSuggestionDateFont;
  date.textAlignment = NSTextAlignmentCenter;
  date.textColor = kSuggestionOverlayColor;
  [date sizeToFit];
  date.frameLeft = kSuggestionTextLeftMargin + (kSuggestionTextWidth - date.frameWidth) / 2;
  date.frameTop = kSuggestionDateBaseline - kSuggestionDateFont.get().ascender;
  [suggestion_overlay_ addSubview:date];
}

- (void)removeSuggestionOverlay {
  if (!suggestion_overlay_) {
    return;
  }
  [UIView animateWithDuration:kSuggestionOverlayFadeDuration
                        delay:0.0
                      options:UIViewAnimationCurveEaseInOut
                   animations:^{
      suggestion_overlay_.alpha = 0;
    }
                   completion:^(BOOL finished) {
      [suggestion_overlay_ removeFromSuperview];
      suggestion_overlay_ = NULL;
    }];
}

/*
- (void)animateScrollStep {
  visible_events_ = [self eventRange:self.visibleBounds];
  [self hideEvents:visible_events_];
  [self showEvents:visible_events_];
}
*/

- (void)navbarAutoSuggest {
  [self initAutoSuggestions];
  if (weighted_indexes_.empty()) {
    return;
  }

  const int event_index = [self getNextAutoSuggestIndex];
  SummaryRow row;
  if ([self getSummaryRow:event_index row:&row]) {
    state_->db()->Put(EncodeComposeAutosuggestKey(
                          row.episode_id(), state_->WallTime_Now()), string());
  }

  // Create the overlay.
  EventHandle evh = snapshot_->LoadEvent(row.day_timestamp(), row.identifier());
  [self createSuggestionOverlay:evh];

  const CGRect bounds = [self eventBounds:event_index];
  [event_scroll_ setContentOffset:CGPointMake(bounds.origin.x - kEventOffset, 0) animated:YES];
  /*
    // TODO(spencer): the display link isn't reliably rendering the thumbnails
  // Manually animate the event scroll so that it's longer and smoother.
  CADisplayLink* link = [CADisplayLink displayLinkWithTarget:self
                                                    selector:@selector(animateScrollStep)];
  [link addToRunLoop:[NSRunLoop mainRunLoop] forMode:NSRunLoopCommonModes];
  [UIView animateWithDuration:kAutoSuggestionScrollDuration
                        delay:0.0
                      options:UIViewAnimationCurveEaseInOut
                   animations:^{
      event_scroll_.contentOffset = CGPointMake(bounds.origin.x - kEventOffset, 0);
    }
                   completion:^(BOOL finished) {
      [link invalidate];
      [self removeSuggestionOverlay];
      [self scrollViewDidScroll:event_scroll_];
    }];
  */
}

- (void)resetState {
  selection_.clear();
  all_contacts_.clear();
  [followers_ clear];
  title_.editableText = @"";
}

- (void)toolbarCancel {
  switch (edit_mode_) {
    case EDIT_MODE_NONE: {
      [self resetState];
      ControllerState pop_controller_state =
          [state_->root_view_controller() popControllerState];
      [state_->root_view_controller() dismissViewController:pop_controller_state];
      break;
    }
    case EDIT_MODE_FOLLOWERS:
      break;
    case EDIT_MODE_TITLE:
      title_.editableText = orig_title_;
      break;
  }
  [self setEditMode:EDIT_MODE_NONE];
  [self updateToolbar];
  [self updateNavbar];
}

- (void)toolbarDone {
  if (edit_mode_ == EDIT_MODE_FOLLOWERS) {
    all_contacts_ = followers_.allContacts;
  } else if (edit_mode_ == EDIT_MODE_TITLE) {
    // nothing to do.
  }
  [self setEditMode:EDIT_MODE_NONE];
  [self updateToolbar];
  [self updateNavbar];
}

- (void)shareNew {
  const PhotoSelectionVec photo_ids(SelectionSetToVec(selection_));
  const ContactManager::ContactVec contacts;
  ViewpointHandle vh = state_->viewpoint_table()->ShareNew(
      photo_ids, followers_.allContacts, ToString(title_.editableText), false);
  if (!vh.get()) {
    DIE("event: share_new failed: %d photo%s (%s)",
        photo_ids.size(), Pluralize(photo_ids.size()), photo_ids);
  }
  LOG("event: %s: share_new %d photo%s (%s)",
      vh->id(), photo_ids.size(), Pluralize(photo_ids.size()), photo_ids);
  [state_->root_view_controller().statusBar
      setMessage:@"Starting New Conversation"
      activity:true
      type:STATUS_MESSAGE_UI
      displayDuration:0.75];
  [self resetState];
}

- (void)toolbarSend {
  if (!selection_.empty()) {
    [self shareNew];
    return;
  }

  const int event_index = self.currentEventIndex;
  if (event_index < self.numEvents) {
    ComposeEvent* ev = &event_map_[event_index];
    __weak ComposeLayoutController* weak_self = self;
    CppDelegate* cpp_delegate = new CppDelegate;
    cpp_delegate->Add(
        @protocol(UIAlertViewDelegate), @selector(alertView:clickedButtonAtIndex:),
        ^(UIAlertView* alert, NSInteger index) {
          if (index == 1) {
            [weak_self toggleEvent:ev];
            [weak_self shareNew];
            alert.delegate = NULL;
            delete cpp_delegate;
          }
        });

    const int num_photos = ev->view.photos->size();
    [[[UIAlertView alloc]
       initWithTitle:@"Share from this event?"
             message:Format("Would you like to share the %d photo%s shown from this event "
                            "or continue without sharing?",
                            num_photos, Pluralize(num_photos))
            delegate:cpp_delegate->delegate()
       cancelButtonTitle:@"Continue"
       otherButtonTitles:@"Share Photos", NULL] show];
  } else {
    [self shareNew];
  }
}

- (void)hideToolbar {
  toolbar_offscreen_ = true;
  [self viewDidLayoutSubviews];
}

- (void)showToolbar {
  toolbar_offscreen_ = false;
  [self viewDidLayoutSubviews];
}

- (void)updateToolbar {
  switch (edit_mode_) {
    case EDIT_MODE_NONE:
      [toolbar_ showComposeItems:true numPhotos:selection_.size()];
      break;
    case EDIT_MODE_FOLLOWERS:
      [toolbar_ showAddPeopleItems:true];
      break;
    case EDIT_MODE_TITLE:
      [toolbar_ showAddTitleItems:true];
      break;
  }
}

- (void)updateNavbar {
  switch (edit_mode_) {
    case EDIT_MODE_NONE:
      [navbar_ show];
      [navbar_ showComposeItems];
      break;
    case EDIT_MODE_FOLLOWERS:
    case EDIT_MODE_TITLE:
      [navbar_ hide];
      break;
  }
}

- (void)clearViews {
  [toolbar_ removeFromSuperview];
  toolbar_ = NULL;
  [navbar_ removeFromSuperview];
  navbar_ = NULL;
}

- (void)loadView {
  //  LOG("compose: view load");

  self.view = [UIView new];
  self.view.autoresizesSubviews = YES;
  self.view.autoresizingMask =
      UIViewAutoresizingFlexibleWidth |
      UIViewAutoresizingFlexibleHeight;
  self.view.backgroundColor = [UIColor whiteColor];

  [self clearViews];

  // Create content scroll area for use with the expandable followers field view.
  content_ = [ConversationScrollView new];
  content_.scrollsToTop = NO;
  content_.autoresizesSubviews = YES;
  [self.view addSubview:content_];

  followers_ = [[FollowerFieldView alloc] initWithState:state_
                                            provisional:true
                                                  width:kFollowersWidth];
  followers_.enabled = true;
  followers_.editable = true;
  followers_.showEditIcon = true;
  followers_.editIconStyle = EDIT_ICON_DROPDOWN;
  followers_.delegate = self;
  [content_ addSubview:followers_];

  followers_divider_ = [UIView new];
  followers_divider_.backgroundColor = kDividerColor;
  [content_ addSubview:followers_divider_];

  title_container_ = [UIView new];
  title_container_.autoresizesSubviews = YES;
  [content_ addSubview:title_container_];

  UIImageView* title_icon = [[UIImageView alloc] initWithImage:kConvoTitleIcon];
  [title_container_ addSubview:title_icon];

  title_ = [[TextView alloc] initWithFrame:CGRectMake(0, 0, kTitleWidth, 0)];
  title_.autoresizingMask = UIViewAutoresizingFlexibleHeight;
  title_.autocorrectionType = UITextAutocorrectionTypeDefault;
  title_.autocapitalizationType = UITextAutocapitalizationTypeSentences;
  title_.autoresizesSubviews = YES;
  title_.linkStyle = UIStyle::kLinkAttributes;
  title_.keyboardAppearance = UIKeyboardAppearanceAlert;
  title_.returnKeyType = UIReturnKeyDone;
  title_.placeholderAttrText = NewAttrString("Add Title (optional)", kTitlePlaceholderAttributes);
  [title_ setAttributes:kTitleAttributes];
  title_.editableText = @"";
  title_.delegate = self;
  [title_container_ addSubview:title_];

  title_divider_ = [UIView new];
  title_divider_.backgroundColor = kDividerColor;
  [content_ addSubview:title_divider_];

  event_scroll_ = [UIScrollView new];
  event_scroll_.backgroundColor = [UIColor whiteColor];
  event_scroll_.autoresizesSubviews = YES;
  event_scroll_.directionalLockEnabled = YES;
  event_scroll_.showsHorizontalScrollIndicator = NO;
  event_scroll_.showsVerticalScrollIndicator = NO;
  event_scroll_.alwaysBounceVertical = NO;
  event_scroll_.alwaysBounceHorizontal = YES;
  event_scroll_.delegate = self;
  [content_ addSubview:event_scroll_];

  search_field_ = [[SearchFieldView alloc] initWithState:state_ withSearchParent:self.view];
  search_field_.pinnedBGColor = kSearchBarPinnedBGColor;
  search_field_.unpinnedBGColor = kSearchBarUnpinnedBGColor;
  search_field_.borderColor = kSearchBarBorderColor;
  search_field_.searchPlaceholder = @"Search Events";
  search_field_.env = self;
  [event_scroll_ addSubview:search_field_];

  use_camera_ = [[CameraEvent alloc] initWithState:state_];
  [event_scroll_ addSubview:use_camera_];

  __weak ComposeLayoutController* weak_self = self;
  toolbar_ = [[ComposeToolbar alloc] initWithTarget:weak_self];
  [self.view addSubview:toolbar_];

  navbar_ = [Navbar new];
  navbar_.env = weak_self;
  [self.view addSubview:navbar_];

  tutorial_overlay_ = [UIView new];
  [self.view addSubview:tutorial_overlay_];

  tutorial_button_ = NewTutorialButton(self, @selector(setNextTutorialMode));
  [tutorial_overlay_ addSubview:tutorial_button_];

  single_tap_recognizer_ =
      [[UITapGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSingleTap:)];
  single_tap_recognizer_.numberOfTapsRequired = 1;
  [event_scroll_ addGestureRecognizer:single_tap_recognizer_];

  if (self.visible) {
    [self viewWillAppear:NO];
  }
}

- (void)viewDidUnload {
  //  LOG("compose: view did unload");
  toolbar_ = NULL;
  navbar_ = NULL;
}

- (void)viewWillAppear:(BOOL)animated {
  //  LOG("compose: view will appear");
  [super viewWillAppear:animated];

  if (!keyboard_will_show_.get()) {
    keyboard_will_show_.Init(
        UIKeyboardWillShowNotification,
        ^(NSNotification* n) {
          const Dict d(n.userInfo);
          const CGRect keyboard_frame =
              d.find_value(UIKeyboardFrameEndUserInfoKey).rect_value();
          if (CGRectIsNull(keyboard_frame)) {
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
              UIEdgeInsets visible_insets = UIEdgeInsetsZero;
              visible_insets.bottom = keyboard_frame.size.height;
              content_.visibleInsets = visible_insets;
              content_.contentInsetBottom = visible_insets.bottom;
            }
                           completion:NULL];
        });
  }
  if (!keyboard_will_hide_.get()) {
    keyboard_will_hide_.Init(
        UIKeyboardWillHideNotification,
        ^(NSNotification* n) {
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
              content_.visibleInsets = UIEdgeInsetsZero;
              content_.contentInsetBottom = 0;
            }
                           completion:NULL];
        });
  }

  ScopedDisableCAActions disable_actions;
  ScopedDisableUIViewAnimations disable_animations;
  [self viewDidLayoutSubviews];
  if (self.numEvents == 0) {
    event_scroll_.contentOffset = CGPointMake(-kEventWidth, 0);
  } else {
    event_scroll_.contentOffset = CGPointMake(0, 0);
  }
}

- (void)viewDidAppear:(BOOL)animated {
  //  LOG("compose: view did appear");
  [super viewDidAppear:animated];

  // Make sure the location manager is enabled.
  if (state_->location_tracker().authorized) {
    [state_->location_tracker() ensureInitialized];
    [state_->location_tracker() start];
  }
}

- (void)viewWillDisappear:(BOOL)animated {
  // LOG("compose: view will disappear");
  [super viewWillDisappear:animated];

  keyboard_will_show_.Clear();
  keyboard_will_hide_.Clear();

  if (state_->location_tracker().authorized) {
    [state_->location_tracker() stop];
  }
  state_->set_compose_last_used(state_->WallTime_Now());

  [search_field_ searchBarCancel];
  search_results_.clear();
}

- (void)viewDidDisappear:(BOOL)animated {
  // LOG("compose: view did disappear");
  [super viewDidDisappear:animated];
  day_table_epoch_ = 0;
  snapshot_.reset();
}

- (void)viewDidLayoutSubviews {
  // LOG("compose: view did layout subviews");
  [super viewDidLayoutSubviews];

  toolbar_.frame = CGRectMake(
      0, 0, self.view.frameWidth,
      toolbar_.intrinsicHeight + state_->status_bar_height());

  if (toolbar_offscreen_) {
    toolbar_.frameBottom = -1;
  } else {
    toolbar_.frameTop = 0;
  }

  const float content_y = search_field_.searchPinned ?
                          search_field_.frameBottom :
                          toolbar_.frameBottom;
  content_.frame = CGRectMake(0, content_y, self.view.frameWidth,
                              self.view.boundsHeight - content_y);

  [navbar_ showComposeItems];
  navbar_.frame = CGRectMake(0, self.view.boundsHeight - navbar_.intrinsicHeight,
                             self.view.boundsWidth, navbar_.intrinsicHeight);

  const float followers_height =
      std::max<float>(kFollowersHeight, followers_.contentHeight);
  followers_.frame = CGRectMake(0, 0, self.view.boundsWidth, followers_height);

  followers_divider_.frame = CGRectMake(0, followers_.frameBottom, self.view.boundsWidth, UIStyle::kDividerSize);

  const float title_height =
      std::max<float>(kTitleHeight, kTitleTopMargin + title_.contentHeight + kTitleBottomMargin);
  title_container_.frame = CGRectMake(0, followers_divider_.frameBottom, self.view.boundsWidth, title_height);

  title_.frame = CGRectMake(kTitleLeftMargin, kTitleTopMargin, self.view.boundsWidth - kTitleLeftMargin,
                            title_.contentHeight);

  title_divider_.frame = CGRectMake(0, title_container_.frameBottom, self.view.boundsWidth, UIStyle::kDividerSize);

  const CGPoint preserved_content_offset = event_scroll_.contentOffset;
  const float event_scroll_y = search_field_.searchPinned ? 0 : title_divider_.frameBottom;
  event_scroll_.frame =
      CGRectMake(0, event_scroll_y, self.view.boundsWidth,
                 std::max<float>(0, content_.boundsHeight - event_scroll_y));
  // Without disabling UIView animations, the content inset and adjustment
  // to event scroll frame interact poorly and the search field becomes
  // briefly visible.
  {
    ScopedDisableUIViewAnimations disable_animations;
    event_scroll_.contentOffset = preserved_content_offset;
  }
  event_scroll_.contentSize =
      CGSizeMake(kEventWidth * self.numEvents + kEventOffset * 2, event_scroll_.boundsHeight);
  event_scroll_.contentInsetTop = search_field_.searchPinned ? 0 : search_field_.intrinsicHeight;
  event_scroll_.contentInsetLeft = kEventWidth;

  if (!search_field_.searchPinned) {
    search_field_.frameTop = -search_field_.intrinsicHeight;
  }
  search_field_.frameWidth = self.view.boundsWidth;

  content_.contentSize = CGSizeMake(self.view.boundsWidth, event_scroll_.frameBottom);

  use_camera_.frame = CGRectMake(-kEventWidth + kEventOffset, 0,
                                 kEventWidth, event_scroll_.boundsHeight - navbar_.boundsHeight);

  tutorial_overlay_.frame = self.view.bounds;

  [self rebuild:false];
  [self setTutorialMode:tutorial_mode_];
}

- (void)setTutorialMode:(ComposeTutorialMode)tutorial_mode {
  tutorial_mode_ = tutorial_mode;
  switch (tutorial_mode_) {
    case COMPOSE_TUTORIAL_ADD_PEOPLE:
      tutorial_overlay_.hidden = NO;
      toolbar_.alpha = 0.25;
      followers_.alpha = 1;
      title_container_.alpha = 0;
      event_scroll_.alpha = 0;
      navbar_.alpha = 0;
      [tutorial_button_ setImage:kComposeTutorialAddPeople forState:UIControlStateNormal];
      [tutorial_button_ sizeToFit];
      tutorial_button_.frameTop = kComposeTutorialAddPeopleTopMargin;
      break;
    case COMPOSE_TUTORIAL_ADD_TITLE:
      tutorial_overlay_.hidden = NO;
      toolbar_.alpha = 0.25;
      followers_.alpha = 0.25;
      title_container_.alpha = 1.0;
      event_scroll_.alpha = 0;
      navbar_.alpha = 0;
      [tutorial_button_ setImage:kComposeTutorialAddTitle forState:UIControlStateNormal];
      [tutorial_button_ sizeToFit];
      tutorial_button_.frameTop = kComposeTutorialAddTitleTopMargin;
      break;
    case COMPOSE_TUTORIAL_PHOTOS:
      tutorial_overlay_.hidden = NO;
      toolbar_.alpha = 0.25;
      followers_.alpha = 0.25;
      title_container_.alpha = 0.25;
      event_scroll_.alpha = 1.0;
      navbar_.alpha = 0;
      [tutorial_button_ setImage:kComposeTutorialPhotos forState:UIControlStateNormal];
      [tutorial_button_ sizeToFit];
      tutorial_button_.frameTop = kComposeTutorialPhotosTopMargin;
      break;
    case COMPOSE_TUTORIAL_SEARCH:
      tutorial_overlay_.hidden = NO;
      toolbar_.alpha = 0.25;
      followers_.alpha = 0.25;
      title_container_.alpha = 0.25;
      event_scroll_.alpha = 1.0;
      [event_scroll_ setContentOffset:CGPointMake(0, event_scroll_.contentOffsetMinY) animated:YES];
      navbar_.alpha = 0;
      [tutorial_button_ setImage:kComposeTutorialSearch forState:UIControlStateNormal];
      [tutorial_button_ sizeToFit];
      tutorial_button_.frameTop = kComposeTutorialSearchTopMargin;
      break;
    case COMPOSE_TUTORIAL_SUGGESTIONS:
      tutorial_overlay_.hidden = NO;
      toolbar_.alpha = 0.25;
      followers_.alpha = 0.25;
      title_container_.alpha = 0.25;
      event_scroll_.alpha = 0.25;
      [event_scroll_ setContentOffset:CGPointMake(0, 0) animated:YES];
      navbar_.alpha = 1.0;
      [tutorial_button_ setImage:kComposeTutorialSuggestions forState:UIControlStateNormal];
      [tutorial_button_ sizeToFit];
      tutorial_button_.frameBottom = self.view.boundsHeight - kComposeTutorialSuggestionsBottomMargin;
      break;
    case COMPOSE_TUTORIAL_DONE:
      tutorial_overlay_.hidden = YES;
      toolbar_.alpha = 1.0;
      followers_.alpha = 1.0;
      title_container_.alpha = 1.0;
      event_scroll_.alpha = 1.0;
      navbar_.alpha = 1.0;
      state_->db()->Put<int>(kComposeTutorialKey, static_cast<int>(tutorial_mode_));
      break;
  }

  tutorial_button_.frameLeft =
      (tutorial_overlay_.boundsWidth - tutorial_button_.frameWidth) / 2;
}

- (void)setNextTutorialMode {
  [self setTutorialMode:static_cast<ComposeTutorialMode>(tutorial_mode_ + 1)];
}

- (void)setEditMode:(ComposeEditMode)edit_mode {
  edit_mode_ = edit_mode;
  switch (edit_mode_) {
    case EDIT_MODE_NONE:
      title_.editable = false;  // toggle editable setting to resign first responder
      title_.editable = true;
      [followers_ stopEditing];
      event_scroll_.scrollEnabled = YES;
      break;
    case EDIT_MODE_FOLLOWERS:
      title_.editable = false;  // toggle editable setting to resign first responder
      title_.editable = true;
      event_scroll_.scrollEnabled = NO;
      break;
    case EDIT_MODE_TITLE:
      [followers_ stopEditing];
      event_scroll_.scrollEnabled = NO;
      break;
  }
  [self updateNavbar];
  [self updateToolbar];
}

- (void)initPlaceholder {
  if (state_->assets_initial_scan()) {
    // We're still performing the initial scan, show the initial scan
    // placeholder.
    if (!initial_scan_placeholder_) {
      initial_scan_placeholder_ = NewInitialScanPlaceholder();
      [event_scroll_ addSubview:initial_scan_placeholder_];
      [initial_scan_placeholder_ centerFrameWithinSuperview];
    }
    return;
  }
}

- (float)loadPhotoPriority:(PhotoView*)p {
  if ([p isAppropriatelyScaled]) {
    return 0;
  }
  // Prioritize loading of the photo with the most screen overlap.
  const CGRect f = [event_scroll_ convertRect:p.frame fromView:p.superview];
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

  for (ComposeEventMap::iterator iter(event_map_.begin());
       iter != event_map_.end();
       ++iter) {
    ComposeEvent& ev = iter->second;
    for (int i = 0; i < ev.view.photos->size(); ++i) {
      PhotoView* p = (*ev.view.photos)[i];
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

- (bool)isPhotoVisible:(PhotoView*)p {
  const CGRect inter = CGRectIntersection(
      [event_scroll_ convertRect:p.frame fromView:p.superview], self.visibleBounds);
  return !CGRectIsNull(inter);
}

- (void)waitThumbnailsLocked:(const EventRange&)v
                       delay:(WallTime)delay {
  vector<PhotoView*> loading;
  for (ComposeEventMap::iterator iter(event_map_.begin());
       iter != event_map_.end();
       ++iter) {
    ComposeEvent& ev = iter->second;
    if (iter->first < v.first || iter->first > v.second) {
      continue;
    }
    for (int i = 0; i < ev.view.photos->size(); ++i) {
      PhotoView* p = (*ev.view.photos)[i];
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

- (void)showEventThumbnailsLocked:(int)event_index {
  ComposeEvent* ev = &event_map_[event_index];
  for (int i = 0; i < ev->view.photos->size(); ++i) {
    PhotoView* p = (*ev->view.photos)[i];

    if (![self isPhotoVisible:p]) {
      continue;
    }
    float t = [ev->view convertPoint:p.frame.origin fromView:p].y -  ev->scroll.contentOffsetY;
    const float y1 = -p.frameHeight;
    const float y2 = event_scroll_.boundsHeight;
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

- (void)setSelectionBadgesForEvent:(ComposeEvent*)ev {
  bool all_selected = true;
  for (int i = 0; i < ev->view.photos->size(); ++i) {
    PhotoView* p = (*ev->view.photos)[i];
    const PhotoSelection key(p.photoId, p.episodeId);
    p.editing = true;
    p.selected = ContainsKey(selection_, key);
    if (!p.selected) {
      all_selected = false;
    }
  }
  ev->view.selected = !ev->view.photos->empty() && all_selected;
}

- (void)setSelectionBadgesForAllEvents {
  for (ComposeEventMap::iterator iter(event_map_.begin());
       iter != event_map_.end();
       ++iter) {
    [self setSelectionBadgesForEvent:&iter->second];
  }
  [self updateToolbar];
}

- (void)showEvent:(int)event_index {
  ComposeEvent* ev = &event_map_[event_index];
  if (ev->view) {
    return;  // Event already visible.
  }

  SummaryRow row;
  if (![self getSummaryRow:event_index row:&row]) {
    LOG("compose: couldn't fetch row %d", event_index);
  }

  // Create the vertical scroll for the event view. The event scroll is
  // kept in the map so that we don't lose vertical scroll offsets in
  // the event of a rebuild.
  if (!ev->scroll) {
    ev->scroll = [UIScrollView new];
    ev->scroll.autoresizingMask = UIViewAutoresizingFlexibleHeight;
    ev->scroll.contentInsetBottom = navbar_.frameHeight;
    ev->scroll.showsVerticalScrollIndicator = NO;
    [event_scroll_ addSubview:ev->scroll];
  }
  ev->scroll.delegate = NULL;
  ev->scroll.frame = [self eventBounds:event_index];
  ev->scroll.delegate = self;

  EventHandle evh = snapshot_->LoadEvent(row.day_timestamp(), row.identifier());
  InitSummaryEvent(state_, ev, evh, row.weight(), kEventWidth, snapshot_->db());
  ev->scroll.contentSize =
      CGSizeMake(ev->view.frameWidth, ev->view.frameHeight + kEventBottomMargin);
  [ev->scroll addSubview:ev->view];
  ev->view.index = event_index;

  // Maintain selection of any photos which have just been made visible.
  [self setSelectionBadgesForEvent:ev];
}

- (void)showEvents:(const EventRange&)v {
  MutexLock l(state_->photo_loader()->mutex());

  // Skip if empty.
  if (v.first >= self.numEvents) {
    return;
  }
  // Loop over the row range, showing rows as necessary.
  const ScopedDisableUIViewAnimations disable_animations;
  for (int i = v.first; i <= v.second; ++i) {
    [self showEvent:i];
    [self showEventThumbnailsLocked:i];
  }

  [self waitThumbnailsLocked:visible_events_
                       delay:kLoadThumbnailsWaitTime];
}

- (void)hideEvents:(const EventRange&)v {
  vector<int> hidden_events;
  for (ComposeEventMap::iterator iter(event_map_.begin());
       iter != event_map_.end();
       ++iter) {
    if (iter->first >= v.first && iter->first <= v.second) {
      continue;
    }
    hidden_events.push_back(iter->first);
    [iter->second.scroll removeFromSuperview];
  }
  for (int i = 0; i < hidden_events.size(); ++i) {
    event_map_.erase(hidden_events[i]);
  }
}

- (void)searchFieldViewWillBeginSearching:(SearchFieldView*)field {
}

- (void)searchFieldViewDidBeginSearching:(SearchFieldView*)field {
  [self hideToolbar];
}

- (void)searchFieldViewDidChange:(SearchFieldView*)field {
  [self viewDidLayoutSubviews];
}

- (void)searchFieldViewWillEndSearching:(SearchFieldView*)field {
}

- (void)searchFieldViewDidEndSearching:(SearchFieldView*)field {
  [self showToolbar];
}

- (void)searchFieldViewDidSearch:(SearchFieldView*)field {
  [self rebuild:true];
  // Revert scroll to origin of content area if search isn't empty.
  if (!field.searchQuery.empty() || searching_episode_id_ == 0) {
    [event_scroll_ setContentOffset:CGPointMake(0, 0) animated:NO];
  } else {
    // Otherwise, on an empty search we want to maintain the currently
    // displayed event so any photos that were just selected while
    // searching are still visible.
   const int orig_event_index =
        snapshot_->events()->GetEpisodeRowIndex(searching_episode_id_);
    const int event_index =
        self.searching ? row_index_map_[orig_event_index] : orig_event_index;
    const CGRect bounds = [self eventBounds:event_index];
    [event_scroll_ setContentOffset:CGPointMake(bounds.origin.x - kEventOffset, 0) animated:NO];
  }
}

- (void)searchFieldViewPopulateAutocomplete:(SearchFieldView*)field
                                    results:(SummaryAutocompleteResults*)results
                                   forQuery:(const Slice&)query {
  PopulateEventAutocomplete(state_, results, query);
}

- (void)textViewDidBeginEditing:(TextView*)text_view {
  // Reset followers auto-complete in case it's currently active. This is
  // essential when viewing the suggested groups or people, as they keyboard
  // is already resigned so we won't receive a did-end-editing callback.
  if (edit_mode_ == EDIT_MODE_FOLLOWERS) {
    all_contacts_ = followers_.allContacts;
    [followers_ resetAutocomplete];
  }
  orig_title_ = title_.editableText;
  [self setEditMode:EDIT_MODE_TITLE];
}

- (void)textViewDidEndEditing:(TextView*)text_view {
}

- (void)textViewDidChange:(TextView*)text_view {
  if (title_.frameHeight != title_.contentHeight) {
    [self viewDidLayoutSubviews];
  }
}

- (bool)textViewShouldReturn:(TextView*)text_view {
  [self setEditMode:EDIT_MODE_NONE];
  return false;
}

- (void)followerFieldViewStopEditing:(FollowerFieldView*)field
                              commit:(bool)commit {
}

- (void)followerFieldViewListFollowers:(FollowerFieldView*)field
                             followers:(ContactManager::ContactVec*)followers
                             removable:(std::unordered_set<int64_t>*)removable {
  *followers = all_contacts_;
  removable->clear();
}

- (void)followerFieldViewDidBeginEditing:(FollowerFieldView*)field {
  [self setEditMode:EDIT_MODE_FOLLOWERS];
}

- (void)followerFieldViewDidEndEditing:(FollowerFieldView*)field {
}

- (void)followerFieldViewDidChange:(FollowerFieldView*)field {
  if (followers_.frameHeight != followers_.contentHeight) {
    [self viewDidLayoutSubviews];
  }
}

- (bool)followerFieldViewEnableDone:(FollowerFieldView*)field {
  return true;
}

- (bool)followerFieldViewDone:(FollowerFieldView*)field {
  all_contacts_ = field.allContacts;
  [self setEditMode:EDIT_MODE_NONE];
  return false;
}

- (void)scrollViewDidScroll:(UIScrollView*)scroll_view {
  if (!initialized_) {
    [self initPlaceholder];
    initialized_ = true;
  }

  if (snapshot_.get()) {
    visible_events_ = [self eventRange:self.visibleBounds];
    cache_events_ = [self eventRange:self.cacheBounds];

    [self hideEvents:cache_events_];
    [self showEvents:cache_events_];

    // Load any higher-res versions of photos that are necessary X ms after
    // the most recent scroll.
    state_->photo_loader()->LoadPhotosDelayed(kLoadImagesDelay, &photo_queue_);

    // Keep track of the episode id representing the current event
    // while searching. We use this to relocate the content offset of
    // the event scroll when the search is cleared. This provides
    // necessary continuity.
    if (self.searching) {
      searching_episode_id_ = self.currentEpisodeId;
    }
  }

  // Pin the search field.
  if (scroll_view == event_scroll_) {
    search_field_.frameLeft = search_field_.searchPinned ? 0 : event_scroll_.contentOffsetX;
  }
}

- (void)scrollViewWillEndDragging:(UIScrollView*)scroll_view
                     withVelocity:(CGPoint)velocity
              targetContentOffset:(inout CGPoint *)target {
  if (scroll_view != event_scroll_ || !snapshot_.get()) {
    return;
  }
  if (target->y <= -search_field_.frameHeight) {
    target->y = -search_field_.frameHeight;
  } else {
    target->y = 0;
  }
  if (target->x < -kEventWidth / 2) {
    target->x = -kEventWidth;
    return;
  }

  const float page = (target->x + kEventOffset) / kEventWidth;
  const int event_index =
      std::max<int>(0, std::min<int>(self.numEvents - 1, int(page + 0.5)));
  target->x = event_index * kEventWidth;
}

- (void)scrollViewDidEndScrollingAnimation:(UIScrollView*)scroll_view {
  if (scroll_view != event_scroll_) {
    return;
  }
  [self removeSuggestionOverlay];
}

- (void)singlePhotoViewToggle:(PhotoView*)p {
  [self togglePhoto:p];
}

- (void)singlePhotoViewWillClose {
  single_photo_view_ = NULL;
  [self updateToolbar];
  [self updateNavbar];
}

- (void)togglePhoto:(PhotoView*)p {
  const PhotoSelection key(p.photoId, p.episodeId);
  if (!ContainsKey(selection_, key)) {
    selection_.insert(key);
  } else {
    selection_.erase(key);
  }

  [self setSelectionBadgesForAllEvents];
}

- (void)toggleEvent:(ComposeEvent*)ev {
  bool all_selected = true;
  for (int i = 0; i < ev->view.photos->size(); ++i) {
    PhotoView* p = (*ev->view.photos)[i];
    const PhotoSelection key(p.photoId, p.episodeId);
    if (!p.selected) {
      all_selected = false;
      break;
    }
  }

  WallTime t = state_->WallTime_Now();
  for (int i = 0; i < ev->view.photos->size(); ++i) {
    PhotoView* p = (*ev->view.photos)[i];
    const PhotoSelection key(p.photoId, p.episodeId, t);
    t += 0.001;  // maintain ordering
    if (all_selected) {
      selection_.erase(key);
    } else {
      selection_.insert(key);
    }
  }

  [self setSelectionBadgesForAllEvents];
}

- (void)handleSingleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }

  if (edit_mode_ != EDIT_MODE_NONE) {
    [self setEditMode:EDIT_MODE_NONE];
    return;
  }

  const CGPoint p = [recognizer locationInView:event_scroll_];
  UIView* hit_view = [event_scroll_ hitTest:p withEvent:NULL];
  PhotoView* photo_view = [hit_view isKindOfClass:[PhotoView class]] ? (PhotoView*)hit_view : NULL;

  if (photo_view) {
    if ([photo_view.editBadge pointInside:
               [recognizer locationInView:photo_view.editBadge] withEvent:NULL]) {
      [self togglePhoto:photo_view];
    } else {
      single_photo_view_ =
          [[SinglePhotoView alloc] initWithState:state_ withPhoto:photo_view];
      single_photo_view_.env = self;
      single_photo_view_.frame = self.view.bounds;
      [self.view addSubview:single_photo_view_];
      [single_photo_view_ show];
      [self updateToolbar];
      [self updateNavbar];
    }
  } else if ([hit_view isKindOfClass:[EventRowView class]]) {
    const int event_index = ((EventRowView*)hit_view).index;
    if (ContainsKey(event_map_, event_index)) {
      [self toggleEvent:&event_map_[event_index]];
    }
  }
}

@end  // ComposeLayoutController
