// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "BadgeView.h"
#import "Logging.h"
#import "MathUtils.h"
#import "UIStyle.h"
#import "UIView+geometry.h"

@implementation BadgeView

- (id)initWithImage:(UIImage*)image
               font:(UIFont*)font
              color:(UIColor*)color {
  if (self = [super initWithImage:image]) {
    self.hidden = YES;

    text_ = [UILabel new];
    text_.adjustsFontSizeToFitWidth = YES;
    text_.backgroundColor = [UIColor clearColor];
    text_.baselineAdjustment = UIBaselineAdjustmentAlignCenters;
    text_.minimumScaleFactor = 0.5;
    text_.font = font;
    text_.numberOfLines = 1;
    text_.textAlignment = NSTextAlignmentCenter;
    text_.textColor = color;
    position_ = CGPointMake(1, 1);
    [self addSubview:text_];
    self.text = NULL;
  }
  return self;
}

- (CGSize)textSize {
  CGSize s = [text_ sizeThatFits:self.superview.frameSize];
  s.width = std::min(s.width, self.superview.frameWidth - 14);
  s.height = self.image.size.height;
  return s;
}

- (void)layoutSubviews {
  [super layoutSubviews];
  const CGSize t = self.textSize;
  CGSize s = self.image.size;
  const float w = std::max(s.width, t.width + 14);
  const float h = t.height;
  // UIView.frame is a bit strange. Setting its value first applies the inverse
  // of UIView.transform. In order to set the frame without having the
  // transform unapplied, we have to explicitly apply the transform to the rect
  // we are setting. Ugh.
  self.frame = CGRectApplyAffineTransform(
      CGRectMake(
          LinearInterp<float>(position_.x, -1, 2, -self.superview.frameWidth,
                              2 * self.superview.frameWidth),
          LinearInterp<float>(position_.y, -1, 2, -self.superview.frameHeight,
                              2 * self.superview.frameHeight),
          w, h),
      self.transform);

  CGRect f;
  f.origin.x = (self.frameWidth - t.width) / 2;
  f.origin.y = (self.frameHeight - t.height) / 2;
  f.size = t;
  text_.frame = f;
}

- (CGPoint)position {
  return position_;
}

- (void)setPosition:(CGPoint)p {
  position_ = p;
  [self setNeedsLayout];
}

- (NSString*)text {
  return text_.text;
}

- (void)setText:(NSString*)t {
  NSArray* scale_values = NULL;

  if (t) {
    self.hidden = NO;
    // We're setting new text from nothing.
    if (!text_.text) {
      scale_values = @[@0.01, @1.05, @0.95, @1.0];
    } else {
      // We're changing existing text.
      scale_values = @[@0.95, @1.05, @1.0];
    }
  } else if (text_.text) {
    // We're replacing existing text with nothing.
    scale_values = @[@1.05, @0.01];
  }

  text_.text = t;
  [self layoutSubviews];
  [CATransaction begin];
  [CATransaction setCompletionBlock:^{
      if (!text_.text) {
        self.hidden = YES;
      }
    }];

  CAKeyframeAnimation* scale_anim = [CAKeyframeAnimation animationWithKeyPath:@"transform"];
  NSMutableArray* tx_values = [NSMutableArray arrayWithCapacity:scale_values.count];
  for (int i = 0; i < scale_values.count; ++i) {
    const float scale = [[scale_values objectAtIndex:i] floatValue];
    [tx_values addObject:[NSValue valueWithCATransform3D:
                                    CATransform3DMakeScale(scale, scale, scale)]];
  }
  scale_anim.values = tx_values;
  scale_anim.timingFunction = [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionEaseInEaseOut];
  scale_anim.duration = 0.300;
  scale_anim.removedOnCompletion = NO;
  scale_anim.fillMode = kCAFillModeForwards;

  [self.layer addAnimation:scale_anim forKey:nil];

  [CATransaction commit];
}

@end  // BadgeView
