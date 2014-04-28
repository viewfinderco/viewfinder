// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <QuartzCore/QuartzCore.h>
#import "CheckmarkBadge.h"
#import "Logging.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

namespace {

const float kDuration = 0.15;
const float kSelectedAlpha = 1.0;
const float kUnselectedAlpha = 0.7;
const float kPointInsideMargin = 12;

}  // namespace

@implementation CheckmarkBadge

- (id)init {
  if (self = [super init]) {
    self.frameSize = self.naturalSize;
    self.userInteractionEnabled = NO;
  }
  return self;
}

- (CGSize)naturalSize {
  return self.selectedImage.size;
}

- (bool)selected {
  return selected_ != NULL;
}

- (void)setSelected:(bool)value {
  if ((value && selected_) || (!value && unselected_)) {
    return;
  }

  UIImageView* old_badge;
  UIImageView* new_badge;
  float new_badge_alpha = 1;
  if (value) {
    old_badge = unselected_;
    new_badge = [[UIImageView alloc] initWithImage:self.selectedImage];
    unselected_ = NULL;
    selected_ = new_badge;
    new_badge_alpha = kSelectedAlpha;
  } else {
    old_badge = selected_;
    new_badge = [[UIImageView alloc] initWithImage:self.unselectedImage];
    selected_ = NULL;
    unselected_ = new_badge;
    new_badge_alpha = kUnselectedAlpha;
  }
  [self addSubview:new_badge];

  if (![UIView areAnimationsEnabled]) {
    [old_badge removeFromSuperview];
    new_badge.alpha = new_badge_alpha;
    return;
  }

  if (!old_badge) {
    new_badge.transform = CGAffineTransformMakeScale(0.0001, 0.0001);
  }

  new_badge.alpha = 0;
  [UIView animateWithDuration:kDuration
                   animations:^{
      new_badge.transform = CGAffineTransformMakeScale(1.1, 1.1);
      new_badge.alpha = new_badge_alpha;
      old_badge.alpha = 0;
    }
                   completion:^(BOOL finished) {
      [old_badge removeFromSuperview];
      [UIView animateWithDuration:kDuration
                       animations:^{
          new_badge.transform = CGAffineTransformIdentity;
        }];
    }];
}

// Provide some extra padding on checkmark badge's extents to
// allow for a minimally sized hit area.
- (BOOL)pointInside:(CGPoint)p
          withEvent:(UIEvent*)event {
  return p.x > -kPointInsideMargin &&
      p.x < self.boundsWidth + kPointInsideMargin &&
      p.y > -kPointInsideMargin &&
      p.y < self.boundsHeight + kPointInsideMargin;
}

- (UIImage*)selectedImage {
  if (selected_image_) {
    return selected_image_;
  }
  return UIStyle::kBadgeSelected;
}

- (void)setSelectedImage:(UIImage*)image {
  if (image == selected_image_) {
    return;
  }
  selected_image_ = image;
  self.frameSize = self.naturalSize;
  if (selected_) {
    [selected_ removeFromSuperview];
    selected_ = NULL;
    self.selected = true;
  }
}

- (UIImage*)unselectedImage {
  if (unselected_image_) {
    return unselected_image_;
  }
  return UIStyle::kBadgeUnselected;
}

- (void)setUnselectedImage:(UIImage*)image {
  if (image == unselected_image_) {
    return;
  }
  unselected_image_ = image;
  if (unselected_) {
    [unselected_ removeFromSuperview];
    unselected_ = NULL;
    self.selected = false;
  }
}

- (bool)actAsButton {
  return act_as_button_;
}

- (void)setActAsButton:(bool)act_as_button {
  act_as_button_ = act_as_button;
  if (act_as_button_ && !single_tap_recognizer_) {
    self.userInteractionEnabled = YES;
    single_tap_recognizer_ =
        [[UITapGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSingleTap:)];
    single_tap_recognizer_.delegate = self;
    single_tap_recognizer_.numberOfTapsRequired = 1;
    [self addGestureRecognizer:single_tap_recognizer_];
  } else if (!act_as_button_ && single_tap_recognizer_) {
    self.userInteractionEnabled = NO;
    single_tap_recognizer_.enabled = NO;
    single_tap_recognizer_.delegate = NULL;
    [self removeGestureRecognizer:single_tap_recognizer_];
    single_tap_recognizer_ = NULL;
  }
}

- (void)remove {
  [UIView animateWithDuration:kDuration
                   animations:^{
      self.transform = CGAffineTransformMakeScale(0.0001, 0.0001);
      self.alpha = 0;
    }
                   completion:^(BOOL finished) {
      [self removeFromSuperview];
    }
   ];
}

- (void)setButtonCallback:(ButtonCallback)button_callback {
  button_callback_ = button_callback;
}

- (void)handleSingleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }

  if (button_callback_) {
    button_callback_();
  }
  UIView* badge = selected_ ? selected_ : unselected_;
  [UIView animateWithDuration:kDuration / 2
                   animations:^{
      badge.transform = CGAffineTransformMakeScale(0.80, 0.80);
    }
                   completion:^(BOOL finished) {
      [UIView animateWithDuration:kDuration
                       animations:^{
          badge.transform = CGAffineTransformIdentity;
        }];
    }];
}

- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer*)recognizer {
  return YES;
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer*)recognizer
       shouldReceiveTouch:(UITouch*)touch {
  if (recognizer == single_tap_recognizer_) {
    return act_as_button_;
  }
  return YES;
}

@end  // CheckmarkBadge
