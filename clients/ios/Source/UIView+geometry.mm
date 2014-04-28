// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <algorithm>
#import <QuartzCore/QuartzCore.h>
#import "Appearance.h"
#import "UIView+geometry.h"

float VisibleFraction(const CGRect& f, const CGRect& b) {
  const CGRect i = CGRectIntersection(f, b);
  return (i.size.width * i.size.height) /
      (b.size.width * b.size.height);
}

@implementation UIView (geometry)

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

- (CGFloat)boundsWidth {
  return self.bounds.size.width;
}

- (void)setBoundsWidth:(CGFloat)v {
  CGRect f = self.bounds;
  f.size.width = v;
  self.bounds = f;
}

- (CGFloat)boundsHeight {
  return self.bounds.size.height;
}

- (void)setBoundsHeight:(CGFloat)v {
  CGRect f = self.bounds;
  f.size.height = v;
  self.bounds = f;
}

- (CGPoint)boundsCenter {
  const CGRect b = self.bounds;
  return CGPointMake(CGRectGetMidX(b), CGRectGetMidY(b));
}

- (void)setBoundsCenter:(CGPoint)p {
  const CGPoint current_center = self.boundsCenter;
  CGRect b = self.bounds;
  b.origin.x += p.x - current_center.x;
  b.origin.y += p.y - current_center.y;
  self.bounds = b;
}

- (CGRect)presentationFrame {
  CALayer* p = self.layer.presentationLayer;
  if (!p) {
    return self.frame;
  }
  return p.frame;
}

- (CGFloat)presentationFrameLeft {
  return self.presentationFrame.origin.x;
}

- (CGFloat)presentationFrameTop {
  return self.presentationFrame.origin.y;
}

- (CGFloat)presentationFrameRight {
  return CGRectGetMaxX(self.presentationFrame);
}

- (CGFloat)presentationFrameBottom {
  return CGRectGetMaxY(self.presentationFrame);
}

- (void)centerFrameWithinSuperview {
  [self centerFrameWithinFrame:self.superview.bounds];
}

- (void)centerFrameWithinFrame:(CGRect)f {
  self.frameLeft = f.origin.x + (f.size.width - self.frameWidth) / 2;
  self.frameTop = f.origin.y + (f.size.height - self.frameHeight) / 2;
}

- (UIView*)baseView {
  UIView* v = self;
  while (v.superview != NULL) {
    v = v.superview;
  }
  return v;
}

- (CGRect)convertRectFromWindow:(CGRect)f {
  UIView* v = self.baseView;
  f = [self convertRect:f fromView:v];
  const CGPoint origin = v.frame.origin;
  return CGRectOffset(f, -origin.x, -origin.y);
}

- (CGPoint)convertPointFromWindow:(CGPoint)p {
  UIView* v = self.baseView;
  p = [self convertPoint:p fromView:v];
  const CGPoint origin = v.frame.origin;
  p.x -= origin.x;
  p.y -= origin.y;
  return p;
}

- (CGAffineTransform)subviewTransform {
  const CATransform3D t = self.layer.sublayerTransform;
  if (!CATransform3DIsAffine(t)) {
    return CGAffineTransformIdentity;
  }
  return CATransform3DGetAffineTransform(t);
}

- (CGAffineTransform)convertTransform:(CGAffineTransform)t
                             fromView:(UIView*)v {
  UIView* start = v;
  UIView* finish = self;
  if (start == NULL) {
    start = self;
    while (start.superview != NULL) {
      start = start.superview;
    }
  }
  // We're only able to walk from the descendant view to the parent view. If
  // start is a descendant of finish, then we just concatenate the transforms.
  if ([start isDescendantOfView:finish]) {
    while (start != finish) {
      // TODO(pmattis): Is the argument order to CGAffineTransformConcat()
      // correct. Doesn't matter if most transforms are the identity.
      t = CGAffineTransformConcat(t, start.transform);
      start = start.superview;
      t = CGAffineTransformConcat(t, start.subviewTransform);
    }
  } else if ([finish isDescendantOfView:start]) {
    // Finish is a descendant of start, concatenate the inverse transforms.
    while (start != finish) {
      // TODO(pmattis): Is the argument order to CGAffineTransformConcat()
      // correct. Doesn't matter if most transforms are the identity.
      t = CGAffineTransformConcat(
          t, CGAffineTransformInvert(finish.transform));
      finish = finish.superview;
      t = CGAffineTransformConcat(
          t, CGAffineTransformInvert(finish.subviewTransform));
    }
  }
  return t;
}

- (CGAffineTransform)convertTransform:(CGAffineTransform)t
                               toView:(UIView*)v {
  if (v == NULL) {
    v = self.baseView;
  }
  return [v convertTransform:t fromView:self];
}

@end  // UIView (geometry)

@implementation UIView (utility)

- (UIView*)findFirstResponder {
  if ([self isFirstResponder]) {
    return self;
  }
  for (UIView* v in self.subviews) {
    UIView* t = [v findFirstResponder];
    if (t) {
      return t;
    }
  }
  return NULL;
}

- (UIScrollView*)parentScrollView {
  for (UIView* v = self.superview; v != NULL; v = v.superview) {
    if ([v isKindOfClass:[UIScrollView class]]) {
      return (UIScrollView*)v;
    }
  }
  return NULL;
}

@end  // UIView (utility)

@implementation UIScrollView (geometry)

- (float)contentInsetBottom {
  return self.contentInset.bottom;
}

- (void)setContentInsetBottom:(float)v {
  UIEdgeInsets i = self.contentInset;
  i.bottom = v;
  self.contentInset = i;
}

- (float)contentInsetLeft {
  return self.contentInset.left;
}

- (void)setContentInsetLeft:(float)v {
  UIEdgeInsets i = self.contentInset;
  i.left = v;
  self.contentInset = i;
}

- (float)contentInsetRight {
  return self.contentInset.right;
}

- (void)setContentInsetRight:(float)v {
  UIEdgeInsets i = self.contentInset;
  i.right = v;
  self.contentInset = i;
}

- (float)contentInsetTop {
  return self.contentInset.top;
}

- (void)setContentInsetTop:(float)v {
  UIEdgeInsets i = self.contentInset;
  i.top = v;
  self.contentInset = i;
}

- (float)contentOffsetX {
  return self.contentOffset.x;
}

- (void)setContentOffsetX:(float)v {
  CGPoint p = self.contentOffset;
  p.x = v;
  self.contentOffset = p;
}

- (float)contentOffsetY {
  return self.contentOffset.y;
}

- (void)setContentOffsetY:(float)v {
  CGPoint p = self.contentOffset;
  p.y = v;
  self.contentOffset = p;
}

- (float)contentOffsetMinX {
  return -self.contentInset.left;
}

- (float)contentOffsetMinY {
  return -self.contentInset.top;
}

- (float)contentOffsetMaxX {
  return std::max<float>(
      0,
      self.contentInset.right +
      self.contentSize.width -
      self.frameWidth);
}

- (float)contentOffsetMaxY {
  return std::max<float>(
      0,
      self.contentInset.bottom +
      self.contentSize.height -
      self.frameHeight);
}

@end  // UIScrollView (geometry)
