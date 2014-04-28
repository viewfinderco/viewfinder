// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball

#import "AlertNotificationView.h"
#import "Appearance.h"
#import "Logging.h"
#import "UIView+geometry.h"

namespace {

const float kAlertNotificationBottomMargin = 4;
const float kDismissButtonWidth = 44;
const float kDismissButtonHeight = 44;

LazyStaticImage kAlertNotificationNew(@"alert-bar.png");
LazyStaticImage kAlertNotificationX(@"alert-bar-x.png");
LazyStaticImage kAlertNotificationXActive(@"alert-bar-x-highlighted.png");

LazyStaticHexColor kAlertNotificationTextColor = { "#ffffffff" };
LazyStaticHexColor kAlertNotificationTextActiveColor = { "#fffffff7" };

LazyStaticUIFont kAlertNotificationButtonUIFont = {
  kProximaNovaBold, 17
};

}  // namespace

@implementation AlertNotificationView

@synthesize height = height_;
@synthesize active = active_;

- (id)initWithType:(AlertNotificationType)type
   withAlertString:(const string&)alert_str
       withTimeout:(float)timeout
      withCallback:(AlertNotificationBlock)block {
  if (self = [super init]) {
    block_ = block;
    active_ = false;

    self.autoresizesSubviews = YES;
    self.backgroundColor = [UIColor clearColor];
    self.hidden = YES;
    self.layer.anchorPoint = CGPointMake(0.5, 0);

    UIImage* bg_image = kAlertNotificationNew;
    height_ = bg_image.size.height;

    self.showsTouchWhenHighlighted = NO;
    self.contentHorizontalAlignment = UIControlContentHorizontalAlignmentCenter;
    self.contentVerticalAlignment = UIControlContentVerticalAlignmentCenter;
    self.titleLabel.font = kAlertNotificationButtonUIFont.get();
    self.titleLabel.lineBreakMode = NSLineBreakByTruncatingTail;
    self.titleEdgeInsets = UIEdgeInsetsMake(20, 0, kAlertNotificationBottomMargin, 0);
    [self setTitle:NewNSString(alert_str) forState:UIControlStateNormal];
    [self setTitleColor:kAlertNotificationTextColor.get()
               forState:UIControlStateNormal];
    [self setTitleColor:kAlertNotificationTextActiveColor.get()
               forState:UIControlStateHighlighted];
    [self setBackgroundImage:bg_image
                    forState:UIControlStateNormal];
    [self addTarget:self
             action:@selector(runBlock)
          forControlEvents:UIControlEventTouchUpInside];

    dismiss_ = [UIButton buttonWithType:UIButtonTypeCustom];
    dismiss_.showsTouchWhenHighlighted = NO;
    [dismiss_ setImage:kAlertNotificationX
              forState:UIControlStateNormal];
    [dismiss_ setImage:kAlertNotificationXActive
              forState:UIControlStateHighlighted];
    [dismiss_ addTarget:self
                action:@selector(remove)
      forControlEvents:UIControlEventTouchUpInside];
    dismiss_.frameSize = CGSizeMake(kDismissButtonWidth, kDismissButtonHeight);
    [self addSubview:dismiss_];

    // If the timeout is not zero, set a callback to remove self.
    if (timeout != 0) {
      dispatch_after_main(timeout, ^{
          [self remove];
        });
    }
  }
  return self;
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];

  CGRect dismiss_f = dismiss_.frame;
  dismiss_f.origin.x = f.size.width - dismiss_f.size.width;
  dismiss_f.origin.y = self.titleLabel.frameTop +
      (self.titleLabel.frameHeight - dismiss_f.size.height) / 2;
  dismiss_.frame = dismiss_f;
}

- (void)runBlock {
  [self remove];
  block_();
}

- (void)show {
  self.hidden = NO;
  self.transform = CGAffineTransformMakeScale(1, 0.0001);
  active_ = true;
  [UIView animateWithDuration:0.300
                   animations:^{
      self.transform = CGAffineTransformIdentity;
    }];
}

- (void)remove {
  active_ = false;
  [UIView animateWithDuration:0.300
                   animations:^{
      self.transform = CGAffineTransformMakeScale(1, 0.0001);
    }
                   completion:^(BOOL finished) {
      self.hidden = YES;
      [self removeFromSuperview];
    }];
}

@end  // AlertNotificationView
