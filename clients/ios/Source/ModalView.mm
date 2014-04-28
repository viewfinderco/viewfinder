// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#import "Appearance.h"
#import "AttrStringUtils.h"
#import "CALayer+geometry.h"
#import "ModalView.h"
#import "Navbar.h"
#import "RootViewController.h"
#import "TextLayer.h"
#import "UIAppState.h"
#import "UIView+geometry.h"

namespace {

const float kShowDuration = 0.300;
const float kHideDuration = 0.300;

}  // namespace

@implementation ModalView

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;

    self.autoresizesSubviews = YES;
    self.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
    self.backgroundColor = [UIColor blackColor];
    self.hidden = YES;

    // Add modal frame to the current view controller's view.
    UIView* controller_view =
        state_->root_view_controller().currentViewController.view;
    [controller_view addSubview:self];
  }
  return self;
}

- (void)setFrame:(CGRect)f {
  if (state_) {
    // Keep the modal view's frame equal to the root view controller's bounds
    // so we maintain the mask. We have to convert the frame into the
    // coordinate system of the current view controller, which might be smaller
    // than the root view controller's bounds.
    UIView* v = state_->root_view_controller().view;
    const CGRect f = [v convertRect:v.bounds toView:self.superview];
    [super setFrame:f];
  }
}

- (void)findAndResignFirstResponder {
  // Resign first responder if necessary.
  UIView* controller_view =
      state_->root_view_controller().currentViewController.view;
  first_responder_ = [controller_view findFirstResponder];
  if (first_responder_) {
    [first_responder_ resignFirstResponder];
  }
}

- (void)restoreFirstResponder {
  if (first_responder_ && first_responder_.window) {
    [first_responder_ becomeFirstResponder];
  }
}

- (void)show {
  if (self.hidden == NO) {
    return;
  }

  [self findAndResignFirstResponder];

  self.backgroundColor = [UIColor clearColor];
  self.transform = CGAffineTransformMakeScale(1, 0.0001);
  self.layer.shouldRasterize = YES;
  self.layer.rasterizationScale = [UIScreen mainScreen].scale;
  shown_from_rect_ = false;
  self.hidden = NO;
  BeginIgnoringInteractionEvents();
  [UIView animateWithDuration:kShowDuration
                   animations:^{
      self.backgroundColor = [UIColor blackColor];
      self.transform = CGAffineTransformIdentity;
    }
                   completion:^(BOOL finished) {
      EndIgnoringInteractionEvents();
      self.layer.shouldRasterize = NO;
    }];
}

- (void)showFromRect:(CGRect)rect {
  if (self.hidden == NO) {
    return;
  }

  [self findAndResignFirstResponder];

  const CGRect dest_frame = self.frame;
  shown_from_rect_ = true;
  show_position_ = CGPointMake(CGRectGetMidX(rect), CGRectGetMidY(rect));

  self.backgroundColor = [UIColor clearColor];
  const float scale = 1.0 / self.bounds.size.height;
  self.transform = CGAffineTransformMakeScale(scale, scale);
  self.center = show_position_;
  self.layer.shouldRasterize = YES;
  self.layer.rasterizationScale = [UIScreen mainScreen].scale;
  self.hidden = NO;
  BeginIgnoringInteractionEvents();
  [UIView animateWithDuration:kShowDuration
                   animations:^{
      self.transform = CGAffineTransformIdentity;
      self.frame = dest_frame;
      self.backgroundColor = [UIColor blackColor];
    }
                   completion:^(BOOL finished) {
      EndIgnoringInteractionEvents();
      self.layer.shouldRasterize = NO;
    }];
}

- (void)hide:(bool)remove {
  if (self.hidden == YES) {
    return;
  }
  const CGPoint orig_origin = self.frameOrigin;
  const float scale = 1.0 / self.bounds.size.height;
  self.layer.shouldRasterize = YES;
  self.layer.rasterizationScale = [UIScreen mainScreen].scale;
  BeginIgnoringInteractionEvents();
  [UIView animateWithDuration:kHideDuration
                   animations:^{
      self.backgroundColor = [UIColor clearColor];
      if (shown_from_rect_) {
        self.transform = CGAffineTransformMakeScale(scale, scale);
        self.center = show_position_;
      } else {
        self.transform = CGAffineTransformMakeScale(1.1, 0.0001);
      }
    }
                   completion:^(BOOL finished) {
      EndIgnoringInteractionEvents();
      [self restoreFirstResponder];
      self.layer.shouldRasterize = NO;
      if (remove) {
        [self removeFromSuperview];
      } else {
        self.transform = CGAffineTransformIdentity;
        self.frameOrigin = orig_origin;
        self.hidden = YES;
      }
    }];
}

@end  // ModalView
