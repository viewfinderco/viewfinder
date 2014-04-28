// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <QuartzCore/QuartzCore.h>
#import "Appearance.h"
#import "Logging.h"
#import "PullToRefreshView.h"
#import "ScopedRef.h"
#import "ValueUtils.h"

namespace {

const float kRefreshHeaderHeight = 40;
const double kPullAngle = 0;
const double kRefreshAngle = kPi;

LazyStaticUIFont kRefreshLabelFont = { kHelveticaMedium, 12 };
LazyStaticUIFont kRefreshSublabelFont = { kHelvetica, 12 };
LazyStaticRgbColor kRefreshTextColor = { Vector4f(1, 1, 1, 1) };
LazyStaticRgbColor kArrowStartColor = { Vector4f(1, 1, 1, 0) };
LazyStaticRgbColor kArrowEndColor = { Vector4f(1, 1, 1, 1) };

NSString* const kTextPull = @"Pull down to refresh...";
NSString* const kTextRelease = @"Release to refresh...";
NSString* const kTextRefreshing = @"Refreshing...";
NSString* const kTextDone = @"Refresh done";

enum {
  kIdle = 0,
  kTriggered,
  kLoading,
  kHiding,
};

CALayer* ArrowLayer() {
  ScopedRef<CGMutablePathRef> p(CGPathCreateMutable());
  CGPathAddRect(p, NULL, CGRectMake(3, 0, 5, 3));
  CGPathAddRect(p, NULL, CGRectMake(3, 4.5, 5, 3));
  CGPathAddRect(p, NULL, CGRectMake(3, 9, 5, 3));
  CGPathAddRect(p, NULL, CGRectMake(3, 13.5, 5, 3));
  CGPathAddRect(p, NULL, CGRectMake(3, 18, 5, 3));
  CGPathMoveToPoint(p, NULL, 0, 21);
  CGPathAddLineToPoint(p, NULL, 5.5, 30);
  CGPathAddLineToPoint(p, NULL, 11, 21);
  CGPathAddLineToPoint(p, NULL, 0, 21);
  CGPathCloseSubpath(p);

  CAShapeLayer* l = [CAShapeLayer layer];
  l.fillColor = MakeUIColor(1, 1, 1, 1).CGColor;
  l.fillRule = kCAFillRuleEvenOdd;
  l.frame = CGRectMake(0, 0, 11, 30);
  l.path = p;

  CAGradientLayer* g = [CAGradientLayer layer];
  g.colors = Array((__bridge id)((CGColorRef)kArrowStartColor),
                   (__bridge id)((CGColorRef)kArrowEndColor));
  g.frame = CGRectMake(0, 0, 11, 30);
  g.mask = l;
  return g;
}

}  // namespace

@implementation PullToRefreshView

- (id)initWithEnv:(id<PullToRefreshEnv>)env {
  if (self = [super init]) {
    self.autoresizesSubviews = YES;
    self.autoresizingMask =
        UIViewAutoresizingFlexibleLeftMargin |
        UIViewAutoresizingFlexibleRightMargin;
    self.backgroundColor = [UIColor clearColor];
    self.frame = CGRectMake(
        0, -kRefreshHeaderHeight, 0, kRefreshHeaderHeight);

    env_ = env;

    label_ = [UILabel new];
    label_.backgroundColor = [UIColor clearColor];
    label_.font = kRefreshLabelFont;
    label_.textAlignment = NSTextAlignmentCenter;
    label_.text = kTextPull;
    label_.textColor = kRefreshTextColor;
    CGRect f = CGRectZero;
    f.size = [label_ sizeThatFits:CGSizeZero];
    f = CGRectOffset(f, -f.size.width / 2, 0);
    f.origin.y = kRefreshHeaderHeight / 2 + 3;
    label_.frame = f;
    [self addSubview:label_];

    sublabel_ = [UILabel new];
    sublabel_.backgroundColor = [UIColor clearColor];
    sublabel_.font = kRefreshSublabelFont;
    sublabel_.textAlignment = NSTextAlignmentCenter;
    sublabel_.adjustsFontSizeToFitWidth = YES;
    sublabel_.text = @"Last updated: 00:00 pm";
    sublabel_.textColor = kRefreshTextColor;
    f = CGRectZero;
    f.size = [sublabel_ sizeThatFits:CGSizeZero];
    f = CGRectOffset(f, -f.size.width / 2, 0);
    f.origin.y = (kRefreshHeaderHeight - f.size.height) / 2 - 3;
    sublabel_.frame = f;
    sublabel_.text = NULL;
    [self addSubview:sublabel_];

    arrow_ = [UIView new];
    CALayer* arrow_layer = ArrowLayer();
    [arrow_.layer addSublayer:arrow_layer];
    arrow_.frame = CGRectMake(
          f.origin.x - 2 * arrow_layer.frame.size.width,
          (kRefreshHeaderHeight - arrow_layer.frame.size.height) / 2,
          arrow_layer.frame.size.width, arrow_layer.frame.size.height);
    arrow_.transform = CGAffineTransformMakeRotation(kPullAngle);
    [self addSubview:arrow_];

    spinner_ =
        [[UIActivityIndicatorView alloc]
          initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleGray];
    spinner_.color = kRefreshTextColor;
    spinner_.frame = CGRectMake(
        f.origin.x - 30, (kRefreshHeaderHeight - 20) / 2,
        20, 20);
    spinner_.hidesWhenStopped = YES;
    [self addSubview:spinner_];
  }
  return self;
}

- (void)reset {
}

- (NSString*)label {
  return label_.text;
}

- (void)setLabel:(NSString*)s {
  label_.text = s;
}

- (NSString*)sublabel {
  return sublabel_.text;
}

- (void)setSublabel:(NSString*)s {
  sublabel_.text = s;
}

- (void)dragUpdate {
  if (self.hidden || (state_ != kIdle && state_ != kTriggered)) {
    return;
  }

  UIScrollView* scroll_view = env_.pullToRefreshScrollView;
  const float y = scroll_view.contentOffset.y;
  if (y >= 0) {
    return;
  }

  // Update the pull to refresh arrow direction and label.
  [UIView animateWithDuration:0.2
                        delay:0
                      options:UIViewAnimationOptionBeginFromCurrentState
                   animations:^{
      [env_ pullToRefreshUpdate];
      if (y < -self.frame.size.height) {
        state_ = kTriggered;
        self.label = kTextRelease;
        arrow_.transform = CGAffineTransformMakeRotation(kRefreshAngle);
      } else {
        state_ = kIdle;
        self.label = kTextPull;
        arrow_.transform = CGAffineTransformMakeRotation(kPullAngle);
      }
    }
                   completion:NULL];
}

- (bool)dragEnd {
  if (self.hidden || state_ != kTriggered) {
    // If the pull-to-refresh wasn't triggered, ensure the top inset is 0.
    [self setTopInset:0 animated:false];
    return false;
  }
  return true;
}

- (void)setTopInset:(float)top animated:(bool)animated {
  UIScrollView* scroll_view = env_.pullToRefreshScrollView;
  if (scroll_view.dragging) {
    // Don't adjust the content inset while dragging is in progress. Doing so
    // causes jumps in the content offset which is visually disturbing.
    return;
  }
  const float y = scroll_view.contentOffset.y;

  [CATransaction begin];
  [CATransaction setDisableActions:YES];
  scroll_view.contentInset = UIEdgeInsetsMake(top, 0, 0, 0);
  scroll_view.contentOffset = CGPointMake(0, y);
  [CATransaction commit];

  if (animated && y < 0 && top == 0) {
    [scroll_view setContentOffset:CGPointMake(0, 0) animated:YES];
  }
}

- (void)start {
  if (state_ == kLoading) {
    return;
  }
  state_ = kLoading;

  // Start the spinner animating and adjust the content inset so that the
  // pull-to-refresh control stays visible while loading is in progress.
  [spinner_ startAnimating];
  [self setTopInset:self.frame.size.height animated:false];
  label_.text = kTextRefreshing;
  arrow_.hidden = YES;
  loading_start_ = WallTime_Now();
}

- (void)stop {
  if (state_ != kLoading) {
    return;
  }
  state_ = kHiding;

  // Give the user a bit of text so that they know loading is done.
  label_.text = kTextDone;

  // Display the done loading text for a minimum of 500ms and a maximum of
  // 1500ms (if loading finished immediately).
  const WallTime elapsed = WallTime_Now() - loading_start_;
  const WallTime delay = std::max(1.5 - elapsed, 0.5);
  dispatch_after_main(delay, ^{
      if (state_ != kHiding) {
        return;
      }
      // Stop the spinner and hide the pull-to-refresh control.
      [spinner_ stopAnimating];
      [self setTopInset:0 animated:true];

      dispatch_after_main(0.3, ^{
          // After the pull-to-refresh control is hidden, reset the state to
          // idle and call dragUpdate to reinitialize the label text and arrow
          // direction.
          if (state_ != kHiding) {
            return;
          }
          state_ = kIdle;
          arrow_.hidden = NO;
          [self dragUpdate];
        });
    });
}

@end  // PullToRefreshView
