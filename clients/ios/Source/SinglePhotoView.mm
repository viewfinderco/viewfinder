// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#import <QuartzCore/QuartzCore.h>
#import "Appearance.h"
#import "UIAppState.h"
#import "CALayer+geometry.h"
#import "CheckmarkBadge.h"
#import "PhotoStorage.h"
#import "PhotoView.h"
#import "RootViewController.h"
#import "SinglePhotoView.h"
#import "StatusBar.h"
#import "UIView+geometry.h"
#import "UIViewController+viewfinder.h"

namespace {

const float kShowDuration = 0.300;
const float kHideDuration = 0.300;

LazyStaticHexColor kModalOverlayColor = { "#000000ff" };
LazyStaticHexColor kModalOverlayFadeColor = { "#00000000" };

}  // namespace

@implementation SinglePhotoView

@synthesize env = env_;

- (id)initWithState:(UIAppState*)state
          withPhoto:(PhotoView*)photo {
  if (self = [super init]) {
    state_ = state;
    photo_ = photo;

    orig_view_ = photo_.superview;
    orig_frame_ = photo_.frame;
    orig_index_ = [[orig_view_ subviews] indexOfObject:photo];

    self.hidden = YES;
    self.autoresizesSubviews = YES;
    self.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
    self.backgroundColor = kModalOverlayColor;

    scroll_view_ = [UIScrollView new];
    scroll_view_.alwaysBounceHorizontal = NO;
    scroll_view_.alwaysBounceVertical = NO;
    scroll_view_.autoresizesSubviews = YES;
    scroll_view_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
    scroll_view_.showsHorizontalScrollIndicator = NO;
    scroll_view_.showsVerticalScrollIndicator = NO;
    scroll_view_.delegate = self;
    scroll_view_.zoomScale = 1;
    [self addSubview:scroll_view_];

    const float max_dim = std::max(photo.frame.size.width,
                                   photo.frame.size.height);
    scroll_view_.maximumZoomScale = kFullSize / max_dim;

    options_ = [[PhotoOptions alloc] initWithEnv:self];
    options_.alpha = 0;
    options_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleBottomMargin;
    options_.donePosition = CGPointMake(0, 0);
    [self addSubview:options_];

    single_tap_recognizer_ =
        [[UITapGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSingleTap:)];
    single_tap_recognizer_.numberOfTapsRequired = 1;
    [self addGestureRecognizer:single_tap_recognizer_];

    double_tap_recognizer_ =
        [[UITapGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleDoubleTap:)];
    double_tap_recognizer_.numberOfTapsRequired = 2;
    [self addGestureRecognizer:double_tap_recognizer_];

    [single_tap_recognizer_
      requireGestureRecognizerToFail:double_tap_recognizer_];
  }
  return self;
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];
  scroll_view_.frame = self.bounds;
  [self scrollViewDidZoom:scroll_view_];
}

- (void)handleSingleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  if ([photo_.editBadge pointInside:
               [recognizer locationInView:photo_.editBadge] withEvent:NULL]) {
    [env_ singlePhotoViewToggle:photo_];
    return;
  }
  [self hide];
}

- (void)handleDoubleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  const float kZoomInThreshold = 1.001;
  if (scroll_view_.zoomScale <= kZoomInThreshold) {
    // We're sufficiently zoomed out: zoom in.
    const CGPoint c = [recognizer locationInView:photo_];
    CGRect f = scroll_view_.bounds;
    f.size.width /= scroll_view_.maximumZoomScale;
    f.size.height /= scroll_view_.maximumZoomScale;
    f.origin.x = c.x - f.size.width / 2;
    f.origin.y = c.y - f.size.height / 2;
    [scroll_view_ zoomToRect:f animated:YES];
  } else {
    // We're currently zoomed in: zoom out.
    [scroll_view_ setZoomScale:1.0 animated:YES];
  }
}

- (void)photoOptionsClose {
  [self hide];
}

- (void)show {
  self.backgroundColor = kModalOverlayFadeColor;
  self.hidden = NO;

  // Move edit badge to this view.
  if (photo_.editing) {
    [self addSubview:photo_.editBadge];
    photo_.editBadge.frame = [self convertRect:photo_.editBadge.frame fromView:photo_];
  }

  // Add photo to this view.
  [scroll_view_ addSubview:photo_];
  photo_.frame = [scroll_view_ convertRect:orig_frame_ fromView:orig_view_];

  [state_->root_view_controller().statusBar setHidden:YES animated:YES];

  [UIView animateWithDuration:kShowDuration
                   animations:^{
      photo_.frame = AspectFit(scroll_view_.bounds.size, photo_.aspectRatio);
      if (photo_.editing) {
        photo_.editBadge.frameOrigin =
            CGPointMake(self.boundsWidth - photo_.editBadge.frameWidth, 0);
      }
      [self scrollViewDidZoom:scroll_view_];
      self.backgroundColor = kModalOverlayColor;
      options_.alpha = 1;
    }];
}

- (void)hide {
  [env_ singlePhotoViewWillClose];
  scroll_view_.zoomScale = 1;

  [state_->root_view_controller().statusBar
      setHidden:state_->root_view_controller().currentViewController.statusBarHidden
      animated:YES];

  [UIView animateWithDuration:kHideDuration
                   animations:^{
      photo_.frame = [scroll_view_ convertRect:orig_frame_ fromView:orig_view_];
      if (photo_.editing) {
        const CGRect f = [self convertRect:orig_frame_ fromView:orig_view_];
        photo_.editBadge.frameOrigin =
            CGPointMake(f.origin.x + f.size.width - photo_.editBadge.frameWidth, f.origin.y);
      }
      self.backgroundColor = kModalOverlayFadeColor;
      options_.alpha = 0;
    }
                   completion:^(BOOL finished) {
      [orig_view_ insertSubview:photo_ atIndex:orig_index_];
      photo_.frame = orig_frame_;
      if (photo_.editing) {
        [photo_ addSubview:photo_.editBadge];
        photo_.editBadge.frameTop = 0;
        photo_.editBadge.frameRight = photo_.boundsWidth;
      }
      [self removeFromSuperview];
    }];
}

- (UIView*)viewForZoomingInScrollView:(UIScrollView*)scroll_view {
  return photo_;
}

- (void)scrollViewDidZoom:(UIScrollView*)scroll_view {
  const CGSize size = photo_.frame.size;
  const CGSize bounds = scroll_view_.bounds.size;
  const float x = std::max<float>(
      0, (bounds.width - size.width) / 2);
  const float y = std::max<float>(
      0, (bounds.height - size.height) / 2);
  scroll_view_.contentInset = UIEdgeInsetsMake(y, x, y, x);
}

@end  // SinglePhotoView
