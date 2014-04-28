// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <QuartzCore/QuartzCore.h>
#import "LayoutController.h"
#import "RootViewController.h"
#import "UIAppState.h"
#import "UIView+geometry.h"

// Invokes prev/next callbacks as necessary to page in more photo ids.
bool CurrentPhotos::SetIndex(int index) {
  if (index == 0 && prev_callback) {
    prev_callback();
    return true;
  } else if (index == photo_ids.size() - 1 && next_callback) {
    next_callback();
    return true;
  }
  return false;
}

void CurrentPhotos::Refresh() {
  if (refresh_callback) {
    refresh_callback();
  }
}

@implementation LayoutController

@synthesize controllerState = controller_state_;

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;
  }
  return self;
}

- (bool)visible {
  // Note that we need both the currentViewController test and the
  // "self.isViewLoaded && self.view.window" tests. The latter tests ensure
  // that a layout controller is not considered visible in viewWillAppear. The
  // currentViewController test ensures that a layout controller is not
  // considered visible once viewWillDisappear is called.
  return (state_->root_view_controller().currentViewController == self) &&
      self.isViewLoaded && self.view.window;
}

@end  // LayoutController

@implementation TwoFingerSwipeScrollView

- (id)init {
  if (self = [super init]) {
    swipe_up_recognizer_ =
        [[UISwipeGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSwipeUp:)];
    swipe_up_recognizer_.delegate = self;
    swipe_up_recognizer_.cancelsTouchesInView = NO;
    swipe_up_recognizer_.numberOfTouchesRequired = 2;
    swipe_up_recognizer_.direction = UISwipeGestureRecognizerDirectionUp;
    [self addGestureRecognizer:swipe_up_recognizer_];
    swipe_up_recognizer_.enabled = YES;

    swipe_down_recognizer_ =
        [[UISwipeGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSwipeDown:)];
    swipe_down_recognizer_.delegate = self;
    swipe_down_recognizer_.cancelsTouchesInView = NO;
    swipe_down_recognizer_.numberOfTouchesRequired = 2;
    swipe_down_recognizer_.direction = UISwipeGestureRecognizerDirectionDown;
    [self addGestureRecognizer:swipe_down_recognizer_];
    swipe_down_recognizer_.enabled = YES;
  }
  return self;
}

- (void)handleSwipeUp:(UISwipeGestureRecognizer*)recognizer {
  if (self.contentOffsetY < self.contentOffsetMaxY) {
    [self animateVerticalOffset:self.contentOffsetMaxY];
  }
}

- (void)handleSwipeDown:(UISwipeGestureRecognizer*)recognizer {
  if (self.contentOffsetY > self.contentOffsetMinY) {
    [self animateVerticalOffset:self.contentOffsetMinY];
  }
}

- (void)animateVerticalOffset:(float)vertical_offset {
  // Stop any existing scroll by disabling the scroll view and
  // immediately re-enabling it.
  self.scrollEnabled = NO;
  self.scrollEnabled = YES;
  [self setContentOffset:CGPointMake(self.contentOffsetX, vertical_offset) animated:YES];
}

- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer*)recognizer {
  return YES;
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer*)recognizer
       shouldReceiveTouch:(UITouch*)touch {
  return YES;
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer*)a
shouldRecognizeSimultaneouslyWithGestureRecognizer:(UIGestureRecognizer*)b {
  // Allow swipes to recognize with panning.
  return ([a isKindOfClass:[UISwipeGestureRecognizer class]] &&
          [b isKindOfClass:[UIPanGestureRecognizer class]]);
}

@end  // TwoFingerSwipeScrollView
