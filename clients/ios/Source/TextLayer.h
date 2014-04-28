// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.
// Author: Spencer Kimball.

#import <CoreText/CoreText.h>
#import <QuartzCore/QuartzCore.h>
#import "ScopedRef.h"

CAShapeLayer* MakeShapeLayerFromRects(
    const vector<CGRect>& rects, float margin, float corner_radius);

// A CALayer sub-class with no implicit animations.
@interface BasicCALayer : CALayer {
}

@end  // BasicCALayer

@interface TextLayer : BasicCALayer {
 @private
  ScopedRef<CTFramesetterRef> text_framesetter_;
  ScopedRef<CTFrameRef> text_frame_;
  NSAttributedString* attr_str_;
  float max_width_;
  float ascent_;
  float descent_;
  float leading_;
}

@property (nonatomic, readonly) CTFrameRef textFrame;
@property (nonatomic) NSAttributedString* attrStr;
@property (nonatomic) float maxWidth;
@property (nonatomic, readonly) float ascent;
@property (nonatomic, readonly) float descent;
@property (nonatomic, readonly) float leading;
@property (nonatomic, readonly) float baseline;

// Returns the bounding rectangle for the character at the specified string
// index.
- (CGRect)rectForIndex:(int)index;

// Returns the bounding rectangle for the specified range of characters in the
// string.
- (vector<CGRect>)rectsForRange:(const NSRange&)range;

// Returns the closest string index to the specified point, constrained to the
// specified range.
- (int)closestIndexToPoint:(CGPoint)point withinRange:(NSRange)range;

@end  // TextLayer

// local variables:
// mode: objc
// end:
