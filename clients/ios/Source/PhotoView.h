// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "Appearance.h"
#import "ContentView.h"
#import "Image.h"
#import "ScopedPtr.h"

class UIAppState;
@class CheckmarkBadge;

// Aspect fit/fill the specified bounds given an aspect ratio. For aspect fit,
// the maximum dimension will be the max(bounds.width, bounds.height). For
// aspect fill, the minimum dimension will be min(bounds.width, bounds.height).
CGRect AspectFit(const CGSize& bounds, float aspect_ratio);
CGRect AspectFill(const CGSize& bounds, float aspect_ratio);

@interface PhotoView : ContentView {
 @private
  UIAppState* state_;
  ScopedPtr<Image> thumbnail_;
  float aspect_ratio_;
  float zoom_scale_;
  CGPoint position_;
  CGSize load_size_;
  UIImageView* image_view_;
  CheckmarkBadge* edit_badge_;
  CGPoint edit_badge_offset_;
  bool selectable_;
  UIView* disabled_;
}

@property (nonatomic, readonly) ScopedPtr<Image>& thumbnail;
@property (nonatomic, readonly) CGRect imageFrame;
@property (nonatomic) CGSize loadSize;
@property (nonatomic) UIImage* image;
@property (nonatomic) UIImageView* imageView;
@property (nonatomic) CheckmarkBadge* editBadge;
@property (nonatomic) CGPoint editBadgeOffset;
@property (nonatomic) float aspectRatio;
@property (nonatomic) float zoomScale;
@property (nonatomic) CGPoint position;
@property (nonatomic) bool editing;
@property (nonatomic) bool enabled;
@property (nonatomic) bool selectable;
@property (nonatomic) bool selected;

- (id)initWithState:(UIAppState*)state;
- (void)ensureVerticalParallax:(float)scale;
- (bool)isAppropriatelyScaled;

@end  // PhotoView

// local variables:
// mode: objc
// end:
