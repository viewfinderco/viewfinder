// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#import <QuartzCore/QuartzCore.h>
#import "Appearance.h"
#import "Logging.h"
#import "Navbar.h"
#import "TutorialOverlayView.h"
#import "UIView+geometry.h"

namespace {

const float kTutorialOverlayTopMargin = -62;
const float kTutorialOverlayBottomMargin = -17.5;
const float kTutorialOverlaySideMargin = 44;

const float kTutorialOverlayTextTopMargin = 4;

const float kNippleLeftMargin = -10;
const float kNippleTopMargin = -7.5;
const float kNippleMinMargin = 45;

const float kNippleVerticalOverhang = 9;
const float kNippleVerticalUnderhang = 6;

LazyStaticImage kBlueNoticePopover(
    @"blue_notice_popover.png", UIEdgeInsetsMake(0, 52, 0, 52));
LazyStaticImage kBlueNoticePopoverNipple(
    @"blue_notice_popover_nipple.png");
LazyStaticImage kBlueNoticePopoverNippleUnder(
    @"blue_notice_popover_nipple_under.png");

LazyStaticHexColor kTutorialOverlayTextColor = { "#ffffff" };
LazyStaticHexColor kTutorialOverlayTextActiveColor = { "#fffffff7" };
LazyStaticHexColor kTutorialOverlayShadowColor = { "#595959" };

LazyStaticUIFont kTutorialOverlayButtonUIFont = {
  kProximaNovaRegular, 18
};

}  // namespace

@implementation TutorialOverlayView

@synthesize maxDisplayTime = max_display_time_;

- (id)initWithText:(const string&)text
     withNippleTip:(CGPoint)nipple_tip
   withOrientation:(TutorialOrientation)orientation
         withBlock:(TutorialActionBlock)block {
  if (self = [super init]) {
    block_ = block;
    self.autoresizingMask = UIViewAutoresizingFlexibleWidth;
    self.backgroundColor = [UIColor clearColor];
    self.clipsToBounds = NO;
    self.alpha = 0;

    button_ = [UIButton buttonWithType:UIButtonTypeCustom];
    button_.showsTouchWhenHighlighted = NO;
    button_.titleLabel.font = kTutorialOverlayButtonUIFont.get();
    button_.titleLabel.lineBreakMode = NSLineBreakByTruncatingTail;
    button_.titleLabel.shadowOffset = CGSizeMake(0, -1);
    button_.titleLabel.shadowColor = kTutorialOverlayShadowColor;
    [button_ setTitleEdgeInsets:UIEdgeInsetsMake(
          kTutorialOverlayTextTopMargin, 0, 0, 0)];
    [button_ setTitle:NewNSString(text) forState:UIControlStateNormal];
    [button_ setTitleColor:kTutorialOverlayTextColor.get()
                  forState:UIControlStateNormal];
    [button_ setTitleColor:kTutorialOverlayTextActiveColor.get()
                  forState:UIControlStateHighlighted];
    [button_ setBackgroundImage:kBlueNoticePopover
                       forState:UIControlStateNormal];
    [button_ addTarget:self
                action:@selector(runBlock)
      forControlEvents:UIControlEventTouchUpInside];

    // Increase the framewidth by the side margins.
    [button_ sizeToFit];
    button_.frameWidth = button_.frameWidth + kTutorialOverlaySideMargin * 2;
    [self addSubview:button_];

    // Set frame top of button relative to the nipple tip position.
    self.frameOrigin = orientation == TUTORIAL_OVER ?
                       CGPointMake(0, nipple_tip.y + kTutorialOverlayTopMargin) :
                       CGPointMake(0, nipple_tip.y + kTutorialOverlayBottomMargin);
    self.frameHeight = button_.frameHeight;

    // Add in the nipple, taking care to convert the frame into
    // the tutorial overlay coordinates.
    nipple_ = [[UIImageView alloc]
                initWithImage:(orientation == TUTORIAL_OVER ?
                               kBlueNoticePopoverNipple : kBlueNoticePopoverNippleUnder)];
    nipple_.frameOrigin =
        CGPointMake(nipple_tip.x + kNippleLeftMargin,
                    nipple_tip.y + kNippleTopMargin - self.frameOrigin.y);
    [self addSubview:nipple_];
  }
  return self;
}

- (void)setMaxDisplayTime:(double)max_display_time {
  // Verify only set once as we can't cancel previous dispatch.
  DCHECK_EQ(max_display_time_, 0);
  max_display_time_ = max_display_time;

  __weak TutorialOverlayView* weak_self = self;
  dispatch_after_main(max_display_time_, ^{
      [UIView animateWithDuration:0.3
                       animations:^{
          weak_self.alpha = 0;
        }
                       completion:^(BOOL finished) {
          [weak_self removeFromSuperview];
        }];
    });
}

- (void)show {
  if (self.alpha == 1) {
    // Nothing to do. Do not re-perform the wiggle animation.
    return;
  }
  [UIView animateWithDuration:0.300
                   animations:^{
      self.alpha = 1;
    }
                   completion:^(BOOL finished) {
      [self.layer addAnimation:NewWiggleAnimation() forKey:NULL];
    }];
}

- (void)hide {
  [UIView animateWithDuration:0.300
                   animations:^{
      self.alpha = 0;
    }];
}

- (void)layoutSubviews {
  [super layoutSubviews];
  // Center the button within the superview bounds horizontally.
  const float parent_width = self.superview.boundsWidth;
  self.frameWidth = parent_width;

  // Prefer to center the button, but provide bounds which limit it to
  // a minimum margin from the nipple tip.
  const float nipple_x = nipple_.frame.origin.x - kNippleLeftMargin;
  const float min_x = nipple_x + kNippleMinMargin - button_.frameWidth;
  const float max_x = nipple_x - kNippleMinMargin;
  button_.frameLeft = std::min<float>(
      max_x, std::max<float>(min_x, (parent_width - button_.frameWidth) / 2));
}

- (void)runBlock {
  block_();
}

+ (TutorialOverlayView*)createTutorialWithText:(const string&)text
                                        toRect:(CGRect)rect
                               withOrientation:(TutorialOrientation)orientation
                                     withBlock:(TutorialActionBlock)block {
  const CGPoint nipple_tip =
      CGPointMake(rect.origin.x + rect.size.width / 2,
                  orientation == TUTORIAL_OVER ?
                  rect.origin.y + kNippleVerticalOverhang :
                  CGRectGetMaxY(rect) - kNippleVerticalUnderhang);
  TutorialOverlayView* tutorial =
      [[TutorialOverlayView alloc]
                  initWithText:text
                 withNippleTip:nipple_tip
               withOrientation:orientation
                     withBlock:block];
  return tutorial;
}

@end  // TutorialOverlayView
