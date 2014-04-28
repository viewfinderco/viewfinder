// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "Appearance.h"
#import "CALayer+geometry.h"
#import "CheckmarkBadge.h"
#import "CompositeTextLayers.h"
#import "DayTable.h"
#import "EventRowView.h"
#import "Logging.h"
#import "TileLayout.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kLeftMargin = 6;
const float kRightMargin = 6;
const float kTitleHeight = 48;

const float kBadgeLeftMargin = 2;
const float kBadgeTopMargin = 6;

const float kConvoBadgeRightMargin = 6;
const float kConvoBadgeTopMargin = 12.5;
const float kConvoBadgePopDuration = 0.300;
const float kConvoBadgePopDelay = 1.000;

const float kEventCardTextLeftMargin = 42;
const float kEventCardTextTopMargin = 17;

LazyStaticImage kConvoBadgeNew(
    @"convo-badge-new.png");
LazyStaticImage kConvoBadgeNotShared(
    @"convo-badge-notshared.png");
LazyStaticImage kLibraryCardMask(
    @"library-card-mask.png");

}  // namespace

////
// EventRowView

@implementation EventRowView

@synthesize event = evh_;

- (id)initWithState:(UIAppState*)state
          withEvent:(const EventHandle&)evh
          withWidth:(float)width
             withDB:(const DBHandle&)db {
  if (self = [super init]) {
    state_ = state;
    evh_ = evh;
    width_ = width;
    db_ = db;
    episode_id_ = 0;
    if (evh_->episodes_size() > 0) {
      episode_id_ = evh_->episodes(0).episode_id();
    }

    self.autoresizesSubviews = YES;
    self.clipsToBounds = YES;
    self.backgroundColor = [UIColor clearColor];
    self.tag = kSummaryEventTag;

    UIView* photo_section = [UIView new];
    const float photos_width = width_ - kLeftMargin - kRightMargin;
    const float photos_height = InitEventPhotos(
        state_, self, photo_section, evh->episodes(), SUMMARY_EXPANDED_LAYOUT,
        photos_width, NULL, db);
    [self addSubview:photo_section];

    height_ = kTitleHeight + photos_height;
    self.frame = CGRectMake(0, 0, width_, height_);
    photo_section.frame = CGRectMake(kLeftMargin, kTitleHeight,
                                     photos_width, height_ - kTitleHeight);

    // Configure layer mask for card.
    UIImage* mask_image = kLibraryCardMask.get();
    CALayer* mask = [CALayer layer];
    mask.contents = (id)mask_image.CGImage;
    mask.contentsScale = [UIScreen mainScreen].scale;
    mask.contentsCenter = CGRectMake(5 / mask_image.size.width, 5 / mask_image.size.height,
                                     1.0 / mask_image.size.width, 1.0 / mask_image.size.height);
    mask.frame = photo_section.bounds;
    photo_section.layer.mask = mask;

    if (evh_->latest_timestamp() > state_->compose_last_used()) {
      convo_badge_ = [[UIImageView alloc] initWithImage:kConvoBadgeNew];
    } else if (evh_->trapdoors().empty()) {
      convo_badge_ = [[UIImageView alloc] initWithImage:kConvoBadgeNotShared];
    }
    if (convo_badge_) {
      convo_badge_.frameRight = width - kConvoBadgeRightMargin;
      convo_badge_.frameTop = kConvoBadgeTopMargin;
      [self addSubview:convo_badge_];
      // Give the convo badge a slight "pop" when being displayed.
      [UIView animateWithDuration:kConvoBadgePopDuration
                            delay:kConvoBadgePopDelay
                          options:UIViewAnimationCurveEaseInOut
                       animations:^{
          convo_badge_.transform = CGAffineTransformMakeScale(1.1, 1.1);
        }
                       completion:^(BOOL finished) {
          [UIView animateWithDuration:kConvoBadgePopDuration
                                delay:0
                              options:UIViewAnimationCurveEaseInOut
                           animations:^{
              convo_badge_.transform = CGAffineTransformIdentity;
            }
                       completion:NULL];
        }];
    }

    badge_ = [CheckmarkBadge new];
    badge_.frameOrigin = CGPointMake(kBadgeLeftMargin, kBadgeTopMargin);
    badge_.selectedImage = UIStyle::kBadgeAllSelected;
    badge_.unselectedImage = UIStyle::kBadgeAllUnselected;
    [self addSubview:badge_];
    badge_.selected = false;
  }
  return self;
}

- (bool)selected {
  return badge_.selected;
}

- (void)setSelected:(bool)selected {
  badge_.selected = selected;
}

- (void)addTextLayer:(CompositeTextLayer*)layer {
  [super addTextLayer:layer];

  const CGPoint offset = CGPointMake(kEventCardTextLeftMargin, kEventCardTextTopMargin);
  const float layer_width = width_ - kEventCardTextLeftMargin * 2 -
                            (convo_badge_ ? convo_badge_.boundsWidth : 0);

  layer.transition = 0;
  layer.frame = CGRectMake(offset.x, offset.y, layer_width, 0);
  layer.maxWidth = layer_width;
}

+ (float)getEventHeightWithState:(UIAppState*)state
                       withEvent:(const Event&)ev
                       withWidth:(float)width
                          withDB:(const DBHandle&)db {
  const float photos_height =
      InitEventPhotos(state, NULL, NULL, ev.episodes(), SUMMARY_EXPANDED_LAYOUT,
                      width - kLeftMargin - kRightMargin, NULL, db);
  return kTitleHeight +  photos_height;
}

@end  // EventRowView

// local variables:
// mode: objc
// end:
