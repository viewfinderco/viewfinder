// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <Foundation/Foundation.h>
#import <UIKit/UIScrollView.h>
#import <UIKit/UIView.h>

// TODO(spencer): add bounds methods.

// Returns the visible fraction of rectangle f in rectangle b. Returns 1 if
// rectangle f is equal to rectangle b.
float VisibleFraction(const CGRect& f, const CGRect& b);

// Begin/end ignoring interaction events.
inline void BeginIgnoringInteractionEvents() {
  [[UIApplication sharedApplication] beginIgnoringInteractionEvents];
}

inline void EndIgnoringInteractionEvents() {
  [[UIApplication sharedApplication] endIgnoringInteractionEvents];
}

inline bool IsIgnoringInteractionEvents() {
  return [[UIApplication sharedApplication] isIgnoringInteractionEvents];
}

// An Objective-C category to add some utility properties to UIView.
@interface UIView (geometry)

@property (nonatomic) CGPoint frameOrigin;
@property (nonatomic) CGSize frameSize;

@property (nonatomic) CGFloat frameLeft;
@property (nonatomic) CGFloat frameTop;
@property (nonatomic) CGFloat frameRight;
@property (nonatomic) CGFloat frameBottom;

@property (nonatomic) CGFloat frameWidth;
@property (nonatomic) CGFloat frameHeight;

// The width/height of the view's bounds. Note that the bounds are from the
// view's coordinate system while the frame is in the superview's coordinate
// system. So frame{Width,Height} can differ from bounds{Width,Height} if
// UIView.transform is not the identity.
@property (nonatomic) CGFloat boundsWidth;
@property (nonatomic) CGFloat boundsHeight;
@property (nonatomic) CGPoint boundsCenter;

// The current location of the frame on screen. This differs from frame which
// is the location of the view after any animation completes. The
// presentationFrame is the current, mid-animation, location.
@property (nonatomic, readonly) CGRect presentationFrame;
@property (nonatomic, readonly) CGFloat presentationFrameLeft;
@property (nonatomic, readonly) CGFloat presentationFrameTop;
@property (nonatomic, readonly) CGFloat presentationFrameRight;
@property (nonatomic, readonly) CGFloat presentationFrameBottom;

- (void)centerFrameWithinSuperview;
- (void)centerFrameWithinFrame:(CGRect)f;

// convert{Rect,Point} do the wrong thing if fromView is NULL and self.window
// is NULL. We provide methods that do the correct thing.
- (CGRect)convertRectFromWindow:(CGRect)f;
- (CGPoint)convertPointFromWindow:(CGPoint)p;

// Like convert{Rect,Point}, but for a transform.
- (CGAffineTransform)convertTransform:(CGAffineTransform)t
                             fromView:(UIView*)v;
- (CGAffineTransform)convertTransform:(CGAffineTransform)t
                               toView:(UIView*)v;

@end  // UIView (geometry)

@interface UIView (utility)
- (UIView*)findFirstResponder;
- (UIScrollView*)parentScrollView;
@end  // UIView (utility)

// This is provided by iOS libraries, but never defined in a #include.
@interface UIView (debugging)
- (NSString*)recursiveDescription;
@end  // UIView (debugging)

@interface UIScrollView (geometry)

@property (nonatomic) float contentInsetBottom;
@property (nonatomic) float contentInsetLeft;
@property (nonatomic) float contentInsetRight;
@property (nonatomic) float contentInsetTop;
@property (nonatomic) float contentOffsetX;
@property (nonatomic) float contentOffsetY;
@property (nonatomic, readonly) float contentOffsetMinX;
@property (nonatomic, readonly) float contentOffsetMinY;
@property (nonatomic, readonly) float contentOffsetMaxX;
@property (nonatomic, readonly) float contentOffsetMaxY;

@end  // UIScrollView (geometry)

class ScopedDisableUIViewAnimations {
 public:
  ScopedDisableUIViewAnimations()
      : saved_enabled_([UIView areAnimationsEnabled]) {
    [UIView setAnimationsEnabled:NO];
  }
  ~ScopedDisableUIViewAnimations() {
    [UIView setAnimationsEnabled:saved_enabled_];
  }

 private:
  const BOOL saved_enabled_;
};

// local variables:
// mode: objc
// end:
