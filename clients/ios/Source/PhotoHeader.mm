// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "Appearance.h"
#import "Logging.h"
#import "PhotoHeader.h"
#import "UIView+geometry.h"

namespace {

const float kTitleViewHeight = 44;

const float kHideDuration = 0.200;
const float kShowDuration = 0.200;

}  // namespace

@implementation PhotoHeader

@synthesize titleView = title_view_;

- (id)init {
  if (self = [super init]) {
    self.autoresizesSubviews = YES;
    self.autoresizingMask =
        UIViewAutoresizingFlexibleBottomMargin |
        UIViewAutoresizingFlexibleWidth;

    title_view_ = [UIScrollView new];
    title_view_.autoresizingMask = UIViewAutoresizingFlexibleBottomMargin;
    title_view_.clipsToBounds = YES;
    title_view_.scrollEnabled = NO;
    title_view_.showsVerticalScrollIndicator = NO;
    title_view_.showsHorizontalScrollIndicator = NO;
    [self addSubview:title_view_];
  }
  return self;
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];
  title_view_.frameHeight = kTitleViewHeight;
  title_view_.frameWidth = f.size.width;
}

- (void)show {
  if (self.hidden == NO) {
    return;
  }
  self.hidden = NO;
  [UIView animateWithDuration:kShowDuration
                   animations:^{
      self.alpha = 1;
    }];
}

- (void)hide {
  if (self.hidden == YES) {
    return;
  }
  [UIView animateWithDuration:kHideDuration
                   animations:^{
      self.alpha = 0;
    }
                   completion:^(BOOL finished) {
      self.hidden = YES;
    }];
}

@end  // PhotoHeader
