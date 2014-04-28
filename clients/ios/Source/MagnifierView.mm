// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "QuartzCore/QuartzCore.h"
#import "Appearance.h"
#import "Logging.h"
#import "MagnifierView.h"
#import "UIView+geometry.h"

namespace {

const float kDiameter = 133;
const float kBorder = 12;
const float kVerticalOffset = 66;

LazyStaticImage kLoupeMask(@"loupe-mask.png");
LazyStaticImage kLoupeHighlight(@"loupe-highlight.png");

}  // namespace

////
// MagnifierView

@implementation MagnifierView

@synthesize viewToMagnify = view_to_magnify_;
@synthesize touchPoint = touch_point_;

- (id)initWithFrame:(CGRect)frame {
  return [self initWithFrame:frame diameter:kDiameter];
}

- (id)initWithFrame:(CGRect)frame
           diameter:(int)d {
  if ((self = [super initWithFrame:CGRectMake(0, 0, d, d)])) {
    self.backgroundColor = [UIColor clearColor];
    self.layer.cornerRadius = d / 2;
    self.layer.masksToBounds = YES;
  }

  return self;
}

- (void)setTouchPoint:(CGPoint)p {
  touch_point_ = p;
  self.center = CGPointMake(p.x, p.y - kVerticalOffset);
}

- (void)drawRect:(CGRect)rect {
  CGContextRef context = UIGraphicsGetCurrentContext();
  const CGRect bounds = self.bounds;
  CGImageRef mask = kLoupeMask.get().CGImage;
  UIImage* glass = kLoupeHighlight;

  CGContextSaveGState(context);
  CGContextClipToMask(context, bounds, mask);
  CGContextClearRect(context, bounds);
  CGContextScaleCTM(context, 1.2, 1.2);
  CGContextTranslateCTM(context, self.frameWidth / 2 - touch_point_.x - kBorder,
                        self.frameHeight / 2 - touch_point_.y - kBorder);
  // Hide the loupe before rendering underlying layer so we don't
  // recursively render the loupe itself.
  self.hidden = YES;
  [self.viewToMagnify.layer renderInContext:context];
  self.hidden = NO;  // re-expose loupe.

  CGContextRestoreGState(context);
  [glass drawInRect:bounds];
}

@end  // MagnifierView

// local variables:
// mode: objc
// end:
