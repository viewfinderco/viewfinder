// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "CALayer+geometry.h"
#import "CheckmarkBadge.h"
#import "CompositeTextLayers.h"
#import "TitleRowView.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kDuration = 0.3;

}  // namespace

@implementation TitleRowView

- (id)init {
  if (self = [super init]) {
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
    badge_.layer.anchorPoint = CGPointMake(0, 0.5);
    badge_.frameLeft = self.textLayer.frameLeft + self.badgeLeftMargin;
    badge_.frameTop = self.textLayer.frameTop + self.badgeTopMargin;
    badge_.selectedImage = self.selectedImage;
    badge_.unselectedImage = self.unselectedImage;
    [self addSubview:badge_];
    badge_.selected = false;

    if (![UIView areAnimationsEnabled]) {
      self.textLayer.slideLeft = self.textEditModeOffset;
      return;
    }

    badge_.alpha = 0;
    [UIView animateWithDuration:kDuration
                     animations:^{
        self.textLayer.slideLeft = self.textEditModeOffset;
        badge_.alpha = 1;
      }];
  } else {
    [UIView animateWithDuration:kDuration
                     animations:^{
        self.textLayer.slideLeft = 0;
        badge_.alpha = 0;
      }
                     completion:^(BOOL finished) {
        [badge_ removeFromSuperview];
        badge_ = NULL;
      }];
  }
}

- (bool)selected {
  return badge_ && badge_.selected;
}

- (void)setSelected:(bool)value {
  if (badge_) {
    badge_.selected = value;
  }
}

- (float)badgeLeftMargin {
  return 0;
}

- (float)badgeTopMargin {
  return 0;
}

- (float)textEditModeOffset {
  if (badge_) {
    return badge_.naturalSize.width - 4;
  }
  return 0;
}

- (UIImage*)selectedImage {
  return UIStyle::kBadgeAllSelected;
}

- (UIImage*)unselectedImage {
  return UIStyle::kBadgeAllUnselected;
}

@end  // TitleRowView
