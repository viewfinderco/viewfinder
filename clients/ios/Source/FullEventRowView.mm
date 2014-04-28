// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "Appearance.h"
#import "CALayer+geometry.h"
#import "CheckmarkBadge.h"
#import "CompositeTextLayers.h"
#import "DayTable.h"
#import "FullEventRowView.h"
#import "LayoutUtils.h"
#import "Logging.h"
#import "TileLayout.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kLeftMargin = 8;
const float kRightMargin = 8;
const float kTopMargin = 8;
const float kBottomMargin = 4;
const float kBadgeLeftMargin = kLeftMargin + 4;
const float kBadgeTopMargin = kTopMargin + 4;
const float kTitleHeight = 26;

LazyStaticImage kBadgeAllWithTextSelected(
    @"badge-all-withtext-selected.png");
LazyStaticImage kBadgeAllWithTextUnselected(
    @"badge-all-withtext-unselected.png");
LazyStaticImage kLibraryCard(
    @"library-card.png", UIEdgeInsetsMake(5, 5, 5, 5));
LazyStaticImage kLibraryCardMask(
    @"library-card-mask.png");

}  // namespace

////
// FullEventRowView

@implementation FullEventRowView

@synthesize event = evh_;

- (id)initWithState:(UIAppState*)state
          withEvent:(const EventHandle&)evh
          withWidth:(float)width
             withDB:(const DBHandle&)db {
  if (self = [super init]) {
    state_ = state;
    evh_ = evh;
    db_ = db;
    episode_id_ = 0;
    if (evh_->episodes_size() > 0) {
      episode_id_ = evh_->episodes(0).episode_id();
    }

    self.autoresizesSubviews = YES;
    self.backgroundColor = [UIColor clearColor];
    self.tag = kFullEventTag;

    UIView* photo_section = [UIView new];
    const float photos_width = width - kLeftMargin - kRightMargin;
    const float photos_height = InitEventPhotos(
        state_, self, photo_section, evh->episodes(), SUMMARY_EXPANDED_LAYOUT,
        photos_width, NULL, db);
    photo_section.frame = CGRectMake(
        0, kTitleHeight, photos_width, photos_height);

    const float height = kTopMargin + kTitleHeight + photos_height + kBottomMargin;
    self.frame = CGRectMake(0, 0, width, height);

    UIImageView* bg = [[UIImageView alloc] initWithImage:kLibraryCard];
    bg.autoresizingMask = UIViewAutoresizingFlexibleHeight;
    bg.clipsToBounds = YES;
    bg.frame = CGRectMake(kLeftMargin, kTopMargin,
                          width - kLeftMargin - kRightMargin,
                          height - kTopMargin - kBottomMargin);
    bg.userInteractionEnabled = YES;
    [bg addSubview:photo_section];
    [self addSubview:bg];

    // Configure layer mask for card.
    UIImage* mask_image = kLibraryCardMask.get();
    CALayer* mask = [CALayer layer];
    mask.contents = (id)mask_image.CGImage;
    mask.contentsScale = [UIScreen mainScreen].scale;
    mask.contentsCenter = CGRectMake(5 / mask_image.size.width, 5 / mask_image.size.height,
                                     1.0 / mask_image.size.width, 1.0 / mask_image.size.height);
    mask.frame = bg.bounds;
    bg.layer.mask = mask;
  }
  return self;
}

- (bool)editing {
  return badge_ != NULL;
}

- (void)setEditing:(bool)value {
  if ((badge_ != NULL) == value) {
    return;
  }
  if (value) {
    badge_ = [CheckmarkBadge new];
    badge_.frameOrigin = CGPointMake(kBadgeLeftMargin, kBadgeTopMargin);
    badge_.selectedImage = kBadgeAllWithTextSelected;
    badge_.unselectedImage = kBadgeAllWithTextUnselected;
    [self addSubview:badge_];
    badge_.selected = false;
  } else {
    [badge_ removeFromSuperview];
    badge_ = NULL;
  }
}

- (bool)selected {
  return badge_.selected;
}

- (void)setSelected:(bool)selected {
  badge_.selected = selected;
}

- (bool)enabled {
  return enabled_;
}

- (void)setEnabled:(bool)value {
  enabled_ = value;
  badge_.alpha = value ? 1 : 0.5;
}

+ (float)getEventHeightWithState:(UIAppState*)state
                       withEvent:(const Event&)ev
                       withWidth:(float)width
                          withDB:(const DBHandle&)db {
  const float photos_height =
      InitEventPhotos(state, NULL, NULL, ev.episodes(), SUMMARY_EXPANDED_LAYOUT,
                      width - kLeftMargin - kRightMargin, NULL, db);
  return kTopMargin + kTitleHeight + photos_height + kBottomMargin;
}

@end  // FullEventRowView

// local variables:
// mode: objc
// end:
