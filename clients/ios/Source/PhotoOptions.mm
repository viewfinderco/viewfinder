// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "Analytics.h"
#import "CheckmarkBadge.h"
#import "Logging.h"
#import "MathUtils.h"
#import "PhotoOptions.h"
#import "PhotoSelection.h"
#import "UIAppState.h"
#import "UIStyle.h"
#import "UIView+geometry.h"
#import "ViewpointTable.h"

namespace {

const float kSinglePhotoCloseButtonWidth = 68;

const float kHideDuration = 0.200;
const float kShowDuration = 0.200;

LazyStaticImage kSinglePhotoButtonSingle(
    @"single-photo-button-single", UIEdgeInsetsMake(0, 11, 0, 11));
LazyStaticImage kSinglePhotoButtonSingleActive(
    @"single-photo-button-single-active", UIEdgeInsetsMake(0, 11, 0, 11));

LazyStaticUIFont kPhotoOptionsButtonFont = {
  kProximaNovaSemibold, 16
};

LazyStaticHexColor kPhotoOptionsButtonColor = { "#ffffff" };
LazyStaticHexColor kPhotoOptionsButtonActiveColor = { "#ffffff7f" };

UIButton* NewNavbarButton(
    UIImage* image, NSString* title, UIImage* bg_image, UIImage* bg_active,
    float width, id target, SEL selector) {
  UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
  b.showsTouchWhenHighlighted = NO;
  b.frameSize = CGSizeMake(width, bg_image.size.height);
  if (image) {
    [b setImage:image
       forState:UIControlStateNormal];
    b.imageEdgeInsets = UIEdgeInsetsMake(2, 0, 0, 0);
  } else if (title) {
    b.titleLabel.font = kPhotoOptionsButtonFont.get();
    b.titleLabel.lineBreakMode = NSLineBreakByTruncatingTail;
    [b setTitle:title forState:UIControlStateNormal];
    [b setTitleColor:kPhotoOptionsButtonColor.get()
            forState:UIControlStateNormal];
    [b setTitleColor:kPhotoOptionsButtonActiveColor.get()
            forState:UIControlStateHighlighted];
  }
  if (bg_image) {
    [b setBackgroundImage:bg_image forState:UIControlStateNormal];
  }
  if (bg_active) {
    [b setBackgroundImage:bg_active forState:UIControlStateHighlighted];
  }
  [b addTarget:target
        action:selector
     forControlEvents:UIControlEventTouchUpInside];
  return b;
}

}  // namespace

@implementation PhotoOptions

@synthesize env = env_;

- (id)initWithEnv:(id<PhotoOptionsEnv>)env {
  if (self = [super init]) {
    env_ = env;
    done_position_ = CGPointMake(1, 0);  // upper-right corner

    self.frameHeight = kSinglePhotoButtonSingle.get().size.height;

    done_ = NewNavbarButton(
        NULL, @"Close", kSinglePhotoButtonSingle, kSinglePhotoButtonSingleActive,
        kSinglePhotoCloseButtonWidth, env, @selector(photoOptionsClose));
    [self addSubview:done_];
  }
  return self;
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];
  [self setDoneFrame];
}

- (CGPoint)donePosition {
  return done_position_;
}

- (void)setDonePosition:(CGPoint)p {
  done_position_ = p;
}

- (void)setDoneFrame {
  CGRect f = done_.frame;
  f.origin.x = LinearInterp<float>(
      done_position_.x, 0, 1, 0, self.boundsWidth - f.size.width);
  f.origin.y = LinearInterp<float>(
      done_position_.y, 0, 1, 0, self.boundsHeight - f.size.height);
  done_.frame = f;
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

@end  // PhotoOptions
