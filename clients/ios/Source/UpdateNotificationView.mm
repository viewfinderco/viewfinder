// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "Appearance.h"
#import "UIAppState.h"
#import "UIView+geometry.h"
#import "UpdateNotificationView.h"

namespace {

const float kDuration = 0.3;

const string kUpdateNotificationVersion = "2.4.0";

LazyStaticImage kUpdateNotification(@"update-notification-2-4.png");

}  // namespace

@implementation UpdateNotificationView

- (id)initWithFrame:(CGRect)f {
  if (self = [super initWithFrame:f]) {
    self.userInteractionEnabled = YES;
    self.backgroundColor = MakeUIColor(0, 0, 0, 0.7);

    UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
    [b setImage:kUpdateNotification
       forState:UIControlStateNormal];
    [b setImage:kUpdateNotification
       forState:UIControlStateHighlighted];
    [b addTarget:self
          action:@selector(handleTapped:)
       forControlEvents:UIControlEventTouchUpInside];
    b.frameWidth = self.boundsWidth;
    b.frameHeight = self.boundsHeight;
    [self addSubview:b];
    [b centerFrameWithinSuperview];
  }
  return self;
}

- (void)handleTapped:(UIView*)sender {
  [UIView animateWithDuration:kDuration
                   animations:^{
      self.alpha = 0.0;
    }
                   completion:^(BOOL finished) {
      [self removeFromSuperview];
    }];
}

+ (void)maybeShow:(UIAppState*)state
           inView:(UIView*)parent {
  if (!state->show_update_notification(kUpdateNotificationVersion)) {
    return;
  }

  // Prevent the notification from being shown again.
  [UpdateNotificationView disable:state];

  UpdateNotificationView* n =
      [[UpdateNotificationView alloc] initWithFrame:parent.bounds];
  n.alpha = 0;
  [parent addSubview:n];

  [UIView animateWithDuration:kDuration
                   animations:^{
      n.alpha = 1.0;
    }];
}

+ (void)disable:(UIAppState*)state {
  state->set_show_update_notification(false);
}

@end  // UpdateNotificationView
