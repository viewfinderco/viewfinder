// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "Appearance.h"
#import "CALayer+geometry.h"

@implementation CALayer (geometry)

- (CGPoint)frameOrigin {
  return self.frame.origin;
}

- (void)setFrameOrigin:(CGPoint)p {
  CGRect f = self.frame;
  f.origin = p;
  self.frame = MakeIntegralRect(f);
}

- (CGSize)frameSize {
  return self.frame.size;
}

- (void)setFrameSize:(CGSize)s {
  CGRect f = self.frame;
  f.size = s;
  self.frame = MakeIntegralRect(f);
}

- (CGFloat)frameLeft {
  return self.frame.origin.x;
}

- (void)setFrameLeft:(CGFloat)v {
  CGRect f = self.frame;
  f.origin.x = v;
  self.frame = MakeIntegralRect(f);
}

- (CGFloat)frameTop {
  return self.frame.origin.y;
}

- (void)setFrameTop:(CGFloat)v {
  CGRect f = self.frame;
  f.origin.y = v;
  self.frame = MakeIntegralRect(f);
}

- (CGFloat)frameRight {
  CGRect f = self.frame;
  return f.origin.x + f.size.width;
}

- (void)setFrameRight:(CGFloat)v {
  CGRect f = self.frame;
  f.origin.x = v - f.size.width;
  self.frame = MakeIntegralRect(f);
}

- (CGFloat)frameBottom {
  CGRect f = self.frame;
  return f.origin.y + f.size.height;
}

- (void)setFrameBottom:(CGFloat)v {
  CGRect f = self.frame;
  f.origin.y = v - f.size.height;
  self.frame = MakeIntegralRect(f);
}

- (CGFloat)frameWidth {
  return self.frame.size.width;
}

- (void)setFrameWidth:(CGFloat)v {
  CGRect f = self.frame;
  f.size.width = v;
  self.frame = MakeIntegralRect(f);
}

- (CGFloat)frameHeight {
  return self.frame.size.height;
}

- (void)setFrameHeight:(CGFloat)v {
  CGRect f = self.frame;
  f.size.height = v;
  self.frame = MakeIntegralRect(f);
}

- (void)centerFrameWithinSuperlayer {
  [self centerFrameWithinFrame:self.superlayer.bounds];
}

- (void)centerFrameWithinFrame:(CGRect)f {
  self.frameLeft = f.origin.x + (f.size.width - self.frameWidth) / 2;
  self.frameTop = f.origin.y + (f.size.height - self.frameHeight) / 2;
}

@end  // CALayer (geometry)
