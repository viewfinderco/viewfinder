// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.
// Author: Spencer Kimball.

#import "AttrStringUtils.h"
#import "CALayer+geometry.h"
#import "Logging.h"
#import "TextLayer.h"
#import "UIStyle.h"

namespace {

// This constant nudges the framesetter in the right direction
// in the event that content in the attributed string confuses the
// size constraints and the frame draw. This happens especially in
// the case of truncated paragraph styles and emoji characters.
const float kFramesetterExtraHeight = 5;

CGRect IntersectionRectForLine(
    CTLineRef line, const CGPoint& line_origin,
    const NSRange& intersection, const float height) {
  // Determine the rectangle the intersection range covers on this line.
  float ascent = 0.0;
  float descent = 0.0;
  float leading = 0.0;
  CTLineGetTypographicBounds(line, &ascent, &descent, &leading);

  const float y_min = height - line_origin.y - ascent;
  const float y_max = height - line_origin.y + descent;
  const float x_min = line_origin.x + CTLineGetOffsetForStringIndex(
      line, intersection.location, NULL);
  const float x_max = line_origin.x + CTLineGetOffsetForStringIndex(
      line, intersection.location + intersection.length, NULL);

  return CGRectMake(x_min, y_min, x_max - x_min, y_max - y_min);
}

CGSize SuggestedSizeForConstraints(
    CTFramesetterRef framesetter, const CGSize& constraints) {
  CFRange fit_range;
  const CGSize suggested_size =
      CTFramesetterSuggestFrameSizeWithConstraints(
          framesetter, CFRangeMake(0, 0), NULL, constraints, &fit_range);
  // Round the width and height up to the next integer. On iOS 5, failure to do
  // this causes strings to display the truncation ellipses incorrectly.
  return CGSizeMake(ceilf(suggested_size.width), ceilf(suggested_size.height));
}

}  // namespace

CAShapeLayer* MakeShapeLayerFromRects(
    const vector<CGRect>& rects, float margin, float corner_radius) {
  if (rects.empty()) {
    return NULL;
  }

  ScopedRef<CGMutablePathRef> path(CGPathCreateMutable());
  for (int i = 0; i < rects.size(); ++i) {
    UIBezierPath* rounded_rect_path =
        [UIBezierPath bezierPathWithRoundedRect:CGRectInset(rects[i], -margin, -margin)
                                   cornerRadius:corner_radius];
    CGPathAddPath(path, NULL, rounded_rect_path.CGPath);
  }

  CAShapeLayer* layer = [CAShapeLayer new];
  layer.path = path;
  return layer;
}

@implementation BasicCALayer

- (id<CAAction>)actionForKey:(NSString*)key {
  // Disable all implicit animations. They are never what we want.
  return NULL;
}

@end  // BasicCALayer

@implementation TextLayer

@synthesize maxWidth = max_width_;
@synthesize ascent = ascent_;
@synthesize descent = descent_;
@synthesize leading = leading_;
@synthesize baseline = baseline_;

- (id)init {
  if (self = [super init]) {
    self.contentsScale = [UIScreen mainScreen].scale;
    self.rasterizationScale = [UIScreen mainScreen].scale;
    max_width_ = CGFLOAT_MAX;
    // self.backgroundColor = MakeUIColor(1, 0, 0, 0.2).CGColor;
    // self.opacity = 0.5;
  }
  return self;
}

- (id)initWithLayer:(id)layer {
  if (self = [super initWithLayer:layer]) {
    if ([layer isKindOfClass:[TextLayer class]]) {
      TextLayer* other = (TextLayer*)layer;
      text_framesetter_.reset(other->text_framesetter_);
      text_frame_.reset(other->text_frame_);
      attr_str_ = other->attr_str_;
      max_width_ = other->max_width_;
      ascent_ = other->ascent_;
      descent_ = other->descent_;
      leading_ = other->leading_;
      baseline_ = other->baseline_;
    }
  }
  return self;
}

- (CGRect)drawBounds {
  return CGRectMake(0, 0, self.bounds.size.width,
                    self.bounds.size.height + kFramesetterExtraHeight);
}

- (CTFrameRef)textFrame {
  return text_frame_.get();
}

- (NSAttributedString*)attrStr {
  return attr_str_;
}

- (void)setAttrStr:(NSAttributedString*)attr_str {
  if (attr_str == attr_str_) {
    return;
  }
  attr_str_ = attr_str;
  AttrStringMetrics(attr_str_, &ascent_, &descent_, &leading_);
  baseline_ = ascent_ + leading_;
  [self recomputeBounds];
}

- (float)maxWidth {
  return max_width_;
}

- (void)setMaxWidth:(float)v {
  if (max_width_ == v) {
    return;
  }
  max_width_ = v;
  [self recomputeBounds];
}

- (void)recomputeBounds {
  if (!attr_str_ || max_width_ <= 0) {
    return;
  }

  text_framesetter_.acquire(
      CTFramesetterCreateWithAttributedString(
          (__bridge CFAttributedStringRef)attr_str_));
  if (!text_framesetter_.get()) {
    return;
  }

  const CGSize suggested_size = SuggestedSizeForConstraints(
      text_framesetter_, CGSizeMake(max_width_, CGFLOAT_MAX));
  self.bounds = CGRectMake(0, 0, suggested_size.width, suggested_size.height);
}

- (void)setBounds:(CGRect)b {
  if (!attr_str_ || max_width_ <= 0) {
    [super setBounds:CGRectZero];
    text_framesetter_.reset(NULL);
    if (text_frame_.get()) {
      text_frame_.reset(NULL);
      [self setNeedsDisplay];
    }
    return;
  }

  [super setBounds:b];

  ScopedRef<CGPathRef> path(CGPathCreateWithRect(self.drawBounds, NULL));
  text_frame_.acquire(CTFramesetterCreateFrame(
                          text_framesetter_, CFRangeMake(0,0), path, NULL));
  if (text_frame_.get()) {
    [self setNeedsDisplay];
  }
}

- (void)drawInContext:(CGContextRef)context {
  if (!text_frame_.get()) {
    return;
  }

  CGContextSaveGState(context);
  CGContextTranslateCTM(context, 0, self.drawBounds.size.height);
  CGContextScaleCTM(context, 1, -1);

  CTFrameDraw(text_frame_, context);

  // NOTE: the code below visualizes the font metrics.
  /*
  CGContextBeginPath(context);
  CGContextSetLineWidth(context, 0.5);
  const float topline = descent_;
  CGContextMoveToPoint(context, 0, topline);
  CGContextAddLineToPoint(context, self.bounds.size.width, topline);
  CGContextSetStrokeColorWithColor(context, [UIColor blackColor].CGColor);
  CGContextDrawPath(context, kCGPathFillStroke);

  CGContextBeginPath(context);
  const float baseline = descent_ + ascent_;
  CGContextMoveToPoint(context, 0, baseline);
  CGContextAddLineToPoint(context, self.bounds.size.width, baseline);
  CGContextSetStrokeColorWithColor(context, [UIColor whiteColor].CGColor);
  CGContextDrawPath(context, kCGPathFillStroke);
  */

  CGContextRestoreGState(context);
}

- (CGRect)rectForIndex:(int)index {
  if (!text_frame_.get()) {
    return CGRectZero;
  }

  const Array lines(CTFrameGetLines(text_frame_));
  if (lines.size() <= 0) {
    return CGRectZero;
  }

  const float height = self.drawBounds.size.height;
  for (int i = 0; i < lines.size(); ++i) {
    const CTLineRef line = (__bridge CTLineRef)lines.at<id>(i);
    const CFRange line_range = CTLineGetStringRange(line);
    if (index < line_range.location) {
      continue;
    }
    if (index >= line_range.location + line_range.length) {
      if (i + 1 < lines.size() ||
          index > line_range.location + line_range.length) {
        continue;
      }
    }
    CGPoint line_origin;
    CTFrameGetLineOrigins(text_frame_, CFRangeMake(i, 1), &line_origin);

    float ascent = 0.0;
    float descent = 0.0;
    float leading = 0.0;
    CTLineGetTypographicBounds(line, &ascent, &descent, &leading);

    const float y_min = height - line_origin.y - ascent;
    const float y_max = height - line_origin.y + descent;
    const float x_min = line_origin.x +
        CTLineGetOffsetForStringIndex(line, index, NULL);
    float x_max = 0;
    if (index < line_range.location + line_range.length) {
      x_max = line_origin.x +
          CTLineGetOffsetForStringIndex(line, index + 1, NULL);
    } else {
      x_max = x_min;
    }
    return CGRectMake(x_min, y_min, x_max - x_min, y_max - y_min);
  }
  return CGRectZero;
}

- (vector<CGRect>)rectsForRange:(const NSRange&)range {
  vector<CGRect> rects;
  if (!text_frame_.get()) {
    return rects;
  }

  const Array lines(CTFrameGetLines(text_frame_));
  if (lines.size() <= 0) {
    return rects;
  }

  // For each line, find the range of string indexes that it covers and
  // determine if any links intersect that range.
  const float height = self.drawBounds.size.height;
  for (int i = 0; i < lines.size(); ++i) {
    const CTLineRef line = (__bridge CTLineRef)lines.at<id>(i);
    const CFRange cf_line_range = CTLineGetStringRange(line);
    const NSRange line_range = { cf_line_range.location, cf_line_range.length };
    const NSRange intersection = NSIntersectionRange(range, line_range);
    if (intersection.length <= 0) {
      continue;
    }
    CGPoint line_origin;
    CTFrameGetLineOrigins(text_frame_, CFRangeMake(i, 1), &line_origin);
    rects.push_back(
        IntersectionRectForLine(line, line_origin, intersection, height));
  }
  return rects;
}

- (int)closestIndexToPoint:(CGPoint)point
               withinRange:(NSRange)range {
  if (!text_frame_.get()) {
    return 0;
  }

  // Convert the point into the CoreText coordinate system.
  point.y = self.frameHeight - point.y;

  const Array lines(CTFrameGetLines(text_frame_));
  vector<CGPoint> origins(lines.size());
  CTFrameGetLineOrigins(text_frame_, CFRangeMake(0, 0), &origins[0]);

  for (int i = 0; i < lines.size(); i++) {
    CTLineRef line = (__bridge CTLineRef)lines.at<id>(i);
    float ascent = 0.0;
    float descent = 0.0;
    float leading = 0.0;
    CTLineGetTypographicBounds(line, &ascent, &descent, &leading);

    const float y_min = ceil(origins[i].y - descent);
    if (point.y < y_min) {
      // Note that y_min[i] > y_min[i+1]. That is each line has a larger y
      // coordinates than its successor line. We're looking for the first line
      // whose y_min >= point.y which is a close approximation to the closest
      // line to the point.
      continue;
    }

    const CFRange cf_line_range = CTLineGetStringRange(line);
    const NSRange line_range = { cf_line_range.location, cf_line_range.length };
    const NSRange intersection = NSIntersectionRange(range, line_range);
    if (intersection.length <= 0) {
      continue;
    }

    // This line origin is closest to the y-coordinate of our point, now look
    // for the closest string index in this line.
    const CGPoint line_point = CGPointMake(
        point.x - origins[i].x, point.y - origins[i].y);
    const int index = CTLineGetStringIndexForPosition(line, line_point);
    if (index < intersection.location) {
      return intersection.location;
    }
    if (index > intersection.location + intersection.length) {
      return intersection.location + intersection.length;
    }
    return index;
  }
  return attr_str_.length;
}

@end  // TextLayer
