// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis, Spencer Kimball.
//
// TODO
//
// Ranking groups
// - Inverse frequency of location
// - Weighted shares
//   - # photos * shares-per-photo
//   - %-age photos shared
//   - volume of photos shared
// - Weighted views
//
// Colored histogram of volume (draw on arc)
// - Colored by proximity to home location
// - Height based on number of photos
//
// Titling
// - Infrequent location
// - User label
// - Auto-generated (#photos/#shares)

#import <list>
#import <map>
#import <OpenGLES/EAGL.h>
#import <OpenGLES/EAGLDrawable.h>
#import <QuartzCore/QuartzCore.h>
#import "Appearance.h"
#import "Diff.h"
#import "GL.h"
#import "Logging.h"
#import "PhotoView.h"
#import "STLUtils.h"
#import "ValueUtils.h"
#import "ViewfinderTool.h"

namespace {

// Sizes in pixels.
const float kInnerArcWidth = 14;
const float kInnerArcShadowWidth = 1;
const float kInnerFontSize = 12;
const float kInnerTextOffset = 3;
const float kOuterArcWidth = 14;
const float kOuterArcHighlightWidth = 1;
const float kOuterFontSize = 12;
const float kOuterTextOffset = kInnerArcWidth + 3;
const float kEpisodeTextOffset = 2;
const float kEpisodeTickMarkLength = 4;
const float kEpisodeTickMarkWidth = 4;
const float kArcWidth = kOuterArcWidth + kInnerArcWidth;
const float kCurrentTimeLength = 75;
const float kOutlineWidth = 1;

static const float kPositionIndicatorRadius = 4;
static const float kPositionIndicatorYBorder = 3;
static const float kPositionIndicatorLeftBorder = 10;
static const float kPositionIndicatorRightBorder = 5;

const float kAnimationDelay = 1.0 / 30;      // In seconds

const float kVelocityHalfLife = 0.100;       // In seconds
const float kActivationXCoordPct = 0.60;     // x coord (as %) for left activation swipe
const float kActivationInterruptPct = 0.50;  // when can activation be interrupted?

const float kPinchMinScale = 0.2;
const float kPinchMaxScale = 2.0;

// In pixels / second.
const float kMinPIScrollVelocity = 100;      // start transition to position indicator
const float kMaxPIScrollVelocity = 200;      // transition is complete
const float kMinHeaderScrollVelocity = 400;  // start transition away from headers
const float kMaxHeaderScrollVelocity = 800;  // transition is complete
const float kMinSIScrollVelocity = 20;       // start transition to scroll indicator on pan
const float kMaxSIScrollVelocity = 350;      // transition to max opacity complete
const float kMinMaskScrollVelocity = 0;      // start transition to mask opacity
const float kMaxMaskScrollVelocity = 150;    // transition to mask opacity complete
const float kCenteringVelocity = 150;        // threshold velocity for centering
const float kMaxZeroingPanVelocity = 10;     // max pan velocity to engage zeroing

// In seconds.
const float kImpulseTrackThreshold = 0.200;

const float kEpisodeAimCorrection = kArcWidth;  // in pixels; NOTE: 0 is disabled

// Margin sizes in pixels.
const float kVerticalMargin = 60;
const float kRightMargin = 60;
const float kActivationMargin = 30;
const float kJumpScrollMargin = 60;
const float kArcMargin = 90;
const float kEpsilon = 0.0001;

const float kTitleLeftMargin = 1;
const float kGroupTitleFontSize = 13;
const float kGroupSubtitleFontSize = 9;
const float kPositionIndicatorFontSize = 12;

const Vector4f kGroupTitleTextRgb(1, 1, 1, 1);
const Vector4f kViewfinderOrangeRgb(0.910, 0.537, 0.227, 1);
const Vector4f kViewfinderBurntOrangeRgb(0.741, 0.357, 0.204, 1);
const Vector4f kViewfinderRedRgb(0.70, 0.231, 0.188, 1);
const Vector4f kViewfinderGreenRgb(0.098, 0.467, 0.294, 1);
const Vector4f kViewfinderBlueRgb(0.149, 0.404, 0.588, 1);
const Vector4f kViewfinderGray1Rgb(0.925, 0.918, 0.898, 1);
const Vector4f kViewfinderGray2Rgb(0.831, 0.820, 0.792, 1);
const Vector4f kViewfinderGray3Rgb(0.694, 0.678, 0.659, 1);
const Vector4f kViewfinderGray4Rgb(0.435, 0.404, 0.384, 1);
const Vector4f kViewfinderGray5Rgb(0.278, 0.251, 0.235, 1);
const Vector4f kViewfinderGray6Rgb(0.125, 0.122, 0.110, 1);

const Vector4f kExoticLocaleBlueRgb(0.404, 0.784, 1.000, 1);
const Vector4f kViewfinderIndicatorOrangeRgb(0.918, 0.537, 0.180, 1);
const Vector4f kViewfinderIndicatorGrayRgb(0.525, 0.510, 0.490, 1);

Vector4f AlphaBlend(const Vector4f& c1, const Vector4f& c2, float alpha) {
  return c1 * alpha + c2 * (1 - alpha);
}

const float kOuterTickMarkIntensity = 0.6;
const float kInnerTickMarkIntensity = 0.5;
const float kEpisodeTickMarkIntensity = 0.8;
const float kMaskGradientWidth = 150;
const float kMaskStartAlpha = 1.25;
const float kMaskEndAlpha = 0.5;
const float kInnerAlpha = 0.8;
const float kOuterAlpha = 0.8;

const Vector4f kWhite(1, 1, 1, 1);
// const Vector4f kTriangleColorRgb =
//     AlphaBlend(kViewfinderRedRgb, kWhite * kInnerAlpha, 0.6);
// const Vector4f kCurrentTimeColorRgb =
//     AlphaBlend(kWhite, kViewfinderRedRgb, 0.9);

const float kGroupTitleFontAscentOffset = 4;
LazyStaticFont kInnerFont = { kHelveticaMedium, kInnerFontSize };
LazyStaticFont kOuterFont = { kHelveticaBold, kOuterFontSize };
LazyStaticFont kGroupTitleFont = { kHelveticaMedium, kGroupTitleFontSize };
LazyStaticFont kGroupSubtitleFont = { kHelvetica, kGroupSubtitleFontSize };
LazyStaticFont kPositionIndicatorFont = { kHelveticaMedium, kPositionIndicatorFontSize };
LazyStaticRgbColor kGroupTitleBackgroundColor = { Vector4f(0, 0, 0, 0.6) };
LazyStaticRgbColor kGroupTitleTextColor = { kGroupTitleTextRgb };
LazyStaticRgbColor kPositionIndicatorColor = { Vector4f(1, 1, 1, 0.8) };
LazyStaticRgbColor kPositionIndicatorBackgroundColor = { Vector4f(0, 0, 0, 0.6) };
LazyStaticRgbColor kPositionIndicatorBorderColor = { Vector4f(0.5, 0.5, 0.5, 0.6) };
LazyStaticRgbColor kMaskColor = { Vector4f(0, 0, 0, 1) };
// LazyStaticRgbColor kTriangleColor = { kTriangleColorRgb };
// LazyStaticRgbColor kCurrentTimeColor = { kCurrentTimeColorRgb };
// LazyStaticRgbColor& kCurrentTimeBorderColor = kCurrentTimeColor;
// LazyStaticRgbColor kCurrentTimeBackgroundColor = { kViewfinderRedRgb };
LazyStaticRgbColor kInnerArcShadowColor = { Vector4f(0.5, 0.5, 0.5, 1.0) };
LazyStaticRgbColor kInnerArcColor = { Vector4f(0.6, 0.6, 0.6, 1.0) };
LazyStaticRgbColor kOuterArcColor = { Vector4f(0.8, 0.8, 0.8, 1.0) };
LazyStaticRgbColor kOuterArcHighlightColor = { Vector4f(0.9, 0.9, 0.9, 1.0) };
LazyStaticRgbColor kScrollIndicatorColor = { kViewfinderIndicatorGrayRgb };

LazyStaticImage kArcBackground = { @"arc-background@2x.png" };

typedef std::pair<float, float> Interval;
typedef std::pair<int, int> GroupRange;

// Relative importance of various contributions to group weight.  The
// weights are used to rank order groups. The ordering prioritizes the
// display of groups in the viewfinder when there are too many to fit.
const float kVolumeWeightFactor = 0.25;
const float kLocationWeightFactor = 0.75;
const float kTargetWeightBoost = 1;

float ClampValue(float value, float minimum, float maximum) {
  return std::max<float>(minimum, std::min<float>(maximum, value));
}

struct Arc {
  Arc(double b, double e)
      : begin(std::min<double>(b, e)),
        end(std::max<double>(b, e)) {
  }
  double size() const { return end - begin; }
  double begin;
  double end;
};

struct ArcText {
  string orig_str;
  string str;
  double begin;
  double end;
  double line_length;
};

struct Indexes {
  Indexes(int s, int e, float i)
       : start(s), end(e), interp(i) {}
  int start;
  int end;
  float interp;
};

float Interp(float val, float min_val, float max_val,
             float min_t, float max_t) {
  if (val < min_val) {
    return min_t;
  }
  if (val > max_val) {
    return max_t;
  }
  return min_t + (max_t - min_t) * (val - min_val) / (max_val - min_val);
}

Vector4f Blend(const Vector4f& a, const Vector4f& b, float t) {
  return a + (b - a) * t;
}

double ArcAngle(const Vector2f& center, const double r, const CGRect& f) {
  double theta = 2 * kPi;

  {
    const float y = -center.y();
    const float x = sqrt(r * r - y * y) + center.x();
    if (!std::isnan(x)) {
      const Vector2f d((Vector2f(x, 0) - center).normalize());
      const double t = 2 * acos(d.dot(Vector2f(-1, 0)));
      theta = std::min(theta, t);
    }
  }

  {
    const float x = f.size.width - center.x();
    const float y = sqrt(r * r - x * x) + center.y();
    if (!std::isnan(y)) {
      const Vector2f d((Vector2f(f.size.width, y) - center).normalize());
      const double t = 2 * acos(d.dot(Vector2f(-1, 0)));
      theta = std::min(theta, t);
    }
  }

  return theta;
}

CTLineRef MakeCTLine(const Slice& str, CTFontRef font) {
  NSString* ns_str = NewNSString(str);
  const Dict attrs(kCTFontAttributeName, (__bridge id)font,
                   kCTForegroundColorFromContextAttributeName, true);
  NSAttributedString* ns_attr_str =
      [[NSAttributedString alloc] initWithString:ns_str attributes:attrs];
  return CTLineCreateWithAttributedString(
      (__bridge CFAttributedStringRef)ns_attr_str);
}

// Draws a string of text at the specified scale and position. Returns the
// number of pixels in width of the drawn text.
float DrawText(
    const Slice& str, CTFontRef font, float scale, const CGPoint& p) {
  ScopedRef<CTLineRef> line(MakeCTLine(str, font));
  if (CTLineGetGlyphCount(line) == 0) {
    return 0;
  }

  float ascent;
  float width = CTLineGetTypographicBounds(line, &ascent, NULL, NULL);

  CGContextRef context = UIGraphicsGetCurrentContext();
  CGContextSaveGState(context);

  CGContextTranslateCTM(context, p.x, p.y + ascent);
  CGContextSetTextPosition(context, 0, 0);

  // Initialize the text matrix to a known value.
  CGContextSetTextMatrix(context, CGAffineTransformIdentity);

  // Flip the context vertically around the x-axis.
  CGContextScaleCTM(context, scale, -scale);

  CFArrayRef run_array = CTLineGetGlyphRuns(line);
  const int run_count = CFArrayGetCount(run_array);
  for (int i = 0; i < run_count; i++) {
    CTRunRef run = (CTRunRef)CFArrayGetValueAtIndex(run_array, i);
    const CFRange range = CFRangeMake(0, CTRunGetGlyphCount(run));
    CTRunDraw(run, context, range);
  }

  CGContextRestoreGState(context);
  return width * scale;
}

// Draws the transition between 2 strings of text at the specified scale and
// position. Returns the number of pixels in width of the drawn text.
float DrawDiffText(
    const string& from, const string& to, CTFontRef font,
    float t, float scale, CGPoint p) {
  float start_x = p.x;
  vector<DiffOp> diff;
  DiffStrings(from, to, &diff, DIFF_CHARACTERS);

  const Dict attrs(kCTFontAttributeName, (__bridge id)font,
                   kCTForegroundColorFromContextAttributeName, true);
  CGContextRef context = UIGraphicsGetCurrentContext();

  // Loop over the diffs, outputting the matches, insertions and deletions in
  // order to animate the transition from "from" to "to".
  for (int i = 0; i < diff.size(); ++i) {
    const DiffOp& op = diff[i];
    NSString* const str = NewNSString(op.str);
    NSAttributedString* attr_str =
        [[NSAttributedString alloc] initWithString:str attributes:attrs];
    ScopedRef<CTLineRef> line(
        CTLineCreateWithAttributedString(
            (__bridge CFAttributedStringRef)attr_str));
    if (CTLineGetGlyphCount(line) == 0) {
      continue;
    }

    CGContextSaveGState(context);

    float ascent;
    float descent;
    const float width = CTLineGetTypographicBounds(
        line, &ascent, &descent, NULL) * scale;
    const float height = (ascent + descent) * scale;

    switch (op.type) {
      case DiffOp::MATCH:
        break;
      case DiffOp::INSERT:
        CGContextClipToRect(
            context, CGRectMake(p.x, p.y, width * t, height));
        p.x -= (1 - t) * width;
        break;
      case DiffOp::DELETE:
        CGContextClipToRect(
            context, CGRectMake(p.x, p.y, width * (1 - t), height));
        p.x -= t * width;
        break;
    }

    CGContextTranslateCTM(context, p.x, p.y + ascent);
    CGContextSetTextPosition(context, 0, 0);

    // Initialize the text matrix to a known value.
    CGContextSetTextMatrix(context, CGAffineTransformMakeScale(scale, scale));

    // Flip the context vertically around the x-axis.
    CGContextScaleCTM(context, 1, -1);

    CFArrayRef run_array = CTLineGetGlyphRuns(line);
    const int run_count = CFArrayGetCount(run_array);
    for (int j = 0; j < run_count; j++) {
      CTRunRef run = (CTRunRef)CFArrayGetValueAtIndex(run_array, j);
      const CFRange range = CFRangeMake(0, CTRunGetGlyphCount(run));
      CTRunDraw(run, context, range);
    }

    CGContextRestoreGState(context);
    p.x += width;
  }
  return p.x - start_x;
}

float DrawTransitionText(
    const string& from, const string& to, CTFontRef font,
    float t, float scale, CGPoint p) {
  if (t <= 0) {
    return DrawText(from, font, scale, p);
  }
  if (t >= 1) {
    return DrawText(to, font, scale, p);
  }
  return DrawDiffText(from, to, font, t, scale, p);
}

}  // namespace

@interface GLLayer : CAEAGLLayer {
 @private
  EAGLContext* context_;
  GLuint framebuffer_;
  GLuint renderbuffer_;
  bool owns_framebuffer_;
  void (^draw_)();
}

@end  // GLLayer

@implementation GLLayer

- (id)initWithCallback:(void (^)())draw {
  if (self = [super init]) {
    self.contentsScale = [UIScreen mainScreen].scale;
    self.rasterizationScale = [UIScreen mainScreen].scale;
    self.opaque = NO;
    self.drawableProperties =
        Dict(kEAGLDrawablePropertyRetainedBacking, NO,
             kEAGLDrawablePropertyColorFormat, kEAGLColorFormatRGBA8);
    draw_ = draw;

    context_ = [[EAGLContext alloc]
                     initWithAPI:kEAGLRenderingAPIOpenGLES2];
    [EAGLContext setCurrentContext:context_];
  }
  return self;
}

- (id)initWithLayer:(id)layer {
  DIE("unimplemented");
  return NULL;
}

- (void)setFrame:(CGRect)f {
  if (!CGRectEqualToRect(self.frame, f)) {
    [self framebufferDestroy];
  }
  [super setFrame:f];
}

- (void)display {
  [EAGLContext setCurrentContext:context_];
  if (!framebuffer_) {
    [self framebufferCreate];
  }

  // Even though we're drawing over the entire viewport, clearing provides an
  // optimization path for the OpenGL driver.
  glClear(GL_COLOR_BUFFER_BIT);
  draw_();

  [context_ presentRenderbuffer:GL_RENDERBUFFER];
}

- (void)framebufferCreate {
  [self framebufferDestroy];

  owns_framebuffer_ = true;
  glGenFramebuffers(1, &framebuffer_);
  glBindFramebuffer(GL_FRAMEBUFFER, framebuffer_);

  glGenRenderbuffers(1, &renderbuffer_);
  glBindRenderbuffer(GL_RENDERBUFFER, renderbuffer_);

  [context_ renderbufferStorage:GL_RENDERBUFFER fromDrawable:self];
  glFramebufferRenderbuffer(
      GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, renderbuffer_);

  if (glCheckFramebufferStatus(GL_FRAMEBUFFER) !=
      GL_FRAMEBUFFER_COMPLETE) {
    DIE("failed to make complete framebuffer object %x",
        glCheckFramebufferStatus(GL_FRAMEBUFFER));
  }

  GLint width;
  GLint height;
  glGetRenderbufferParameteriv(GL_RENDERBUFFER, GL_RENDERBUFFER_WIDTH, &width);
  glGetRenderbufferParameteriv(GL_RENDERBUFFER, GL_RENDERBUFFER_HEIGHT, &height);
  glViewport(0, 0, width, height);
  glClearColor(0, 0, 0, 0);
  glDisable(GL_BLEND);
  glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
}

- (void)framebufferDestroy {
  if (owns_framebuffer_) {
    owns_framebuffer_ = false;
    glDeleteFramebuffers(1, &framebuffer_);
    glDeleteRenderbuffers(1, &renderbuffer_);
  }
  framebuffer_ = 0;
  renderbuffer_ = 0;
}

- (void)dealloc {
  [self framebufferDestroy];
}

@end  // GLLayer

// A CALayer subclass for drawing the position indicator.
@interface PositionIndicatorLayer : CALayer {
 @private
  NSString* text_;
}

@property NSString* text;

@end  // PositionIndicatorLayer

@implementation PositionIndicatorLayer

- (id)init {
  if (self = [super init]) {
    self.contentsScale = [UIScreen mainScreen].scale;
    self.rasterizationScale = [UIScreen mainScreen].scale;
  }
  return self;
}

- (id)initWithLayer:(id)layer {
  if (self = [super initWithLayer:layer]) {
    if ([layer isKindOfClass:[PositionIndicatorLayer class]]) {
      PositionIndicatorLayer* other = (PositionIndicatorLayer*)layer;
      text_ = other->text_;
    }
  }
  return self;
}

- (void)setOrigin:(CGPoint)p {
  CGRect f = self.frame;
  f.origin = p;
  self.frame = f;
}

- (NSString*)text {
  return text_;
}

- (void)setText:(NSString*)text {
  if (ToSlice(text_) == ToSlice(text)) {
    return;
  }

  text_ = text;

  const CGSize size = [text_ sizeWithFont:kPositionIndicatorFont];
  CGRect f = self.frame;
  f.size.width = 2 + size.width + kPositionIndicatorLeftBorder +
      kPositionIndicatorRightBorder;
  f.size.height = 2 + size.height + 2 * kPositionIndicatorYBorder;
  self.frame = f;

  [self setNeedsDisplay];
}

- (void)drawInContext:(CGContextRef)context {
  CGContextSaveGState(context);

  const float kLeftBorder = kPositionIndicatorLeftBorder;
  const float kRightBorder = kPositionIndicatorRightBorder;
  const float kYBorder = kPositionIndicatorYBorder;
  const float kRadius = kPositionIndicatorRadius;
  const CGSize size = [text_ sizeWithFont:kPositionIndicatorFont];
  const CGPoint pos = { 1 + kLeftBorder, 1 + kYBorder };

  // Draw a pretty box around the position indicator.
  CGContextBeginPath(context);
  // CGContextSetAlpha(context, position_alpha);
  // TODO(pmattis): Drawing the shadow is very expensive graphics operation.
  // CGContextSetShadow(context, CGSizeMake(0, 2), 2);
  CGContextMoveToPoint(
      context, pos.x + size.width + (kRightBorder - kRadius), pos.y - kYBorder);
  CGContextAddLineToPoint(
      context, pos.x, pos.y - kYBorder);
  CGContextAddLineToPoint(
      context, pos.x - kLeftBorder, pos.y + size.height / 2);
  CGContextAddLineToPoint(
      context, pos.x, pos.y + kYBorder + size.height);
  CGContextAddLineToPoint(
      context, pos.x + size.width + (kRightBorder - kRadius),
      pos.y + kYBorder + size.height);
  CGContextAddArc(
      context, pos.x + size.width + (kRightBorder - kRadius),
      pos.y + size.height + (kYBorder - kRadius),
      kRadius, kPi / 2, 0, true);
  CGContextAddLineToPoint(
      context, pos.x + size.width + kRightBorder, pos.y - (kYBorder - kRadius));
  CGContextAddArc(
      context, pos.x + size.width + (kRightBorder - kRadius),
      pos.y - (kYBorder - kRadius),
      kRadius, 0, -kPi / 2, true);
  CGContextSetStrokeColorWithColor(context, kPositionIndicatorBorderColor);
  CGContextSetFillColorWithColor(context, kPositionIndicatorBackgroundColor);
  CGContextDrawPath(context, kCGPathFillStroke);

  CGContextSetFillColorWithColor(context, kPositionIndicatorColor);
  CGContextSetTextDrawingMode(context, kCGTextFill);

  UIGraphicsPushContext(context);
  [text_ drawAtPoint:pos withFont:kPositionIndicatorFont];
  UIGraphicsPopContext();

  CGContextRestoreGState(context);
}

@end  // PositionIndicatorLayer

// A CALayer subclass for drawing the transition text.
@interface EpisodeTextLayer : CALayer {
 @private
  string full_title_;
  string short_title_;
  string full_subtitle_;
  string short_subtitle_;
  ScopedRef<CTFontRef> title_font_;
  ScopedRef<CTFontRef> subtitle_font_;
  Vector4f text_color_;
  float scale_;
  float render_scale_;
  float transition_;
  float width_;
}

@property float scale;
@property Vector4f textColor;
@property float transition;
@property (readonly) float width;

@end  // EpisodeTextLayer

@implementation EpisodeTextLayer

- (id)init {
  if (self = [super init]) {
    self.contentsScale = [UIScreen mainScreen].scale;
    self.rasterizationScale = [UIScreen mainScreen].scale;
  }
  return self;
}

- (id)initWithLayer:(id)layer {
  if (self = [super initWithLayer:layer]) {
    if ([layer isKindOfClass:[EpisodeTextLayer class]]) {
      EpisodeTextLayer* other = (EpisodeTextLayer*)layer;
      full_title_ = other->full_title_;
      short_title_ = other->short_title_;
      full_subtitle_ = other->full_subtitle_;
      short_subtitle_ = other->short_subtitle_;
      title_font_.reset(other->title_font_);
      subtitle_font_.reset(other->subtitle_font_);
      scale_ = other->scale_;
      render_scale_ = other->render_scale_;
      transition_ = other->transition_;
      width_ = other->width_;
    }
  }
  return self;
}

- (float)titleHeight {
  return CTFontGetAscent(title_font_) +
      CTFontGetDescent(title_font_) +
      CTFontGetLeading(title_font_);
}

- (void)setTitleFont:(CTFontRef)font {
  title_font_.reset(font);
}

- (void)setSubtitleFont:(CTFontRef)font {
  subtitle_font_.reset(font);
}

- (const string&)fullTitle {
  return full_title_;
}

- (void)setFullTitle:(const string&)s {
  if (full_title_ == s) {
    return;
  }
  // LOG("  full title changed: %s -> %s", full_title_, s);
  full_title_ = s;
  [self setNeedsDisplay];
}

- (const string&)shortTitle {
  return short_title_;
}

- (void)setShortTitle:(const string&)s {
  if (short_title_ == s) {
    return;
  }
  // LOG("  short title changed: %s -> %s", short_title_, s);
  short_title_ = s;
  [self setNeedsDisplay];
}

- (const string&)fullSubtitle {
  return full_subtitle_;
}

- (void)setFullSubtitle:(const string&)s {
  if (full_subtitle_ == s) {
    return;
  }
  // LOG("  full subtitle changed: %s -> %s", full_subtitle_, s);
  full_subtitle_ = s;
  [self setNeedsDisplay];
}

- (const string&)shortSubtitle {
  return short_subtitle_;
}

- (void)setShortSubtitle:(const string&)s {
  if (short_subtitle_ == s) {
    return;
  }
  // LOG("  short subtitle changed: %s -> %s", short_subtitle_, s);
  short_subtitle_ = s;
  [self setNeedsDisplay];
}

- (float)scale {
  return scale_;
}

- (void)setScale:(float)v {
  const float delta = fabs(scale_ - v);
  if (delta < 0.001) {
    return;
  }
  // LOG("  scale changed: %f -> %f", scale_, v);
  scale_ = v;
  [self setNeedsDisplay];
}

- (Vector4f)textColor {
  return text_color_;
}

- (void)setTextColor:(Vector4f)v {
  if (text_color_.equal(v, 0.001)) {
    return;
  }
  // LOG("  text color: %.1f -> %.1f", text_color_, v);
  text_color_ = v;
  [self setNeedsDisplay];
}

- (float)transition {
  return transition_;
}

- (void)setTransition:(float)v {
  if (fabs(transition_ - v) < 0.001) {
    return;
  }
  // LOG("  transition changed: %.1f -> %.1f", transition_, v);
  transition_ = v;
  [self setNeedsDisplay];
}

- (float)width {
  return width_;
}

- (void)drawInContext:(CGContextRef)context {
  UIGraphicsPushContext(context);

  render_scale_ = scale_;
  width_ = 0;

  CGContextSetRGBFillColor(
      context, text_color_(0), text_color_(1), text_color_(2), text_color_(3));
  CGContextSetTextDrawingMode(context, kCGTextFill);

  CGPoint pt = { kEpisodeTextOffset, 0 };

  const string& title = (transition_ < 1 ? full_title_ : short_title_);
  const string& subtitle = (transition_ < 1 ? full_subtitle_ : short_subtitle_);

  if (!title.empty()) {
    width_ = DrawTransitionText(full_title_, short_title_, title_font_, transition_, scale_, pt);

    // Render the short subtitle (if visible) as a diff text from
    // empty string on the same line as the title.
    if (!short_subtitle_.empty()) {
      // TODO(spencer): major hack with ascents between different fonts.
      width_ += DrawTransitionText("", short_subtitle_, subtitle_font_, transition_, scale_,
                                   CGPointMake(pt.x + width_,
                                               pt.y + kGroupTitleFontAscentOffset * scale_));
    }
    if (!full_subtitle_.empty()) {
      width_ = std::max<float>(width_, DrawTransitionText(
                                   full_subtitle_, "", subtitle_font_, transition_, scale_,
                                   CGPointMake(pt.x, pt.y + self.titleHeight)));
    }
  } else if (!subtitle.empty()) {
    width_ = DrawTransitionText(full_subtitle_, short_subtitle_,
                                subtitle_font_, transition_, scale_,
                                CGPointMake(pt.x, pt.y + (title.empty() ? 0 : self.titleHeight)));
  }

  UIGraphicsPopContext();
}

@end  // EpisodeTextLayer

// Computes a velocity using exponential decay to confine it to an
// arbitrarily sized window of time.
class DecayingVelocity {
 public:
  // max_velocity == 0 does not cap velocity.
  DecayingVelocity(float half_life, float max_velocity=0)
      : half_life_(half_life),
        max_velocity_(max_velocity) {
    Reset();
  }

  void Reset() {
    Reset(Vector2f(0, 0));
  }

  void Reset(const Vector2f& velocity) {
    move_duration_ = 0.0;
    move_total_ = velocity;
    velocity_ = velocity;
    last_move_time_ = WallTime_Now();
  }

  void Adjust(const Vector2f& move, WallTime now=0) {
    if (!now) {
      now = WallTime_Now();
    }
    // Limit the decay time to 1/100th of a second.
    const float decay_time = std::max<float>(0.01, (now - last_move_time_));
    const float decay = Decay(decay_time, half_life_);
    const float instantaneous_velocity = move.length() / decay_time;
    float scale = 1;
    if (max_velocity_ > 0 && instantaneous_velocity > max_velocity_) {
      scale = max_velocity_ / instantaneous_velocity;
    }
    move_duration_ = move_duration_ * decay + decay_time;
    last_move_time_ = now;
    move_total_ = move_total_ * decay + move * scale;
    velocity_ = move_total_ / move_duration_;
  }

  // Direction must be normalized.
  bool IsSwipe(const Vector2f& direction, float velocity_threshold, float pct_total) {
    CHECK_EQ(direction.length(), 1.0);
    Vector2f normalized(velocity_);
    normalized.normalize();
    return (normalized.dot(direction) >= pct_total &&
            velocity_.dot(direction) >= velocity_threshold);
  }

  const Vector2f& velocity() const { return velocity_; }
  float magnitude() const { return velocity_.length(); }
  float operator()(int i) const { return velocity_(i); }

  static const Vector2f UP;
  static const Vector2f DOWN;
  static const Vector2f LEFT;
  static const Vector2f RIGHT;

 private:
  float Decay(float time, float half_life) {
    return exp(-log(2.0) * time / half_life);
  }

  const float half_life_;
  const float max_velocity_;
  float move_duration_;
  WallTime last_move_time_;
  Vector2f move_total_;
  Vector2f velocity_;
};

const Vector2f DecayingVelocity::UP = Vector2f(0, -1);
const Vector2f DecayingVelocity::DOWN = Vector2f(0, 1);
const Vector2f DecayingVelocity::LEFT = Vector2f(-1, 0);
const Vector2f DecayingVelocity::RIGHT = Vector2f(1, 0);


////
// Physics model for simulating spring and friction accelerations.
//
//  Derived from: http://gafferongames.com/game-physics/integration-basics/
class PhysicsModel {
 public:
  PhysicsModel() {
    Reset(Vector2f(0, 0), Vector2f(0, 0));
  }
  virtual ~PhysicsModel() {}

  void Reset() {
    accels_.clear();
    filters_.clear();
    start_time_ = WallTime_Now();
    last_time_ = start_time_;
    exit_condition_ = nil;
  }

  void Reset(const Vector2f& location, const Vector2f& velocity) {
    accels_.clear();
    filters_.clear();
    start_time_ = WallTime_Now();
    last_time_ = start_time_;
    state_.p = location;
    state_.v = velocity;
    exit_condition_ = nil;
  }

  const Vector2f& position() const { return state_.p; }
  void set_position(const Vector2f& p) { state_.p = p; }
  const Vector2f& velocity() const { return state_.v; }
  void set_velocity(const Vector2f& v) { state_.v = v; }

  // Sets "location" according to current accelerations at time "now"
  // and existing state of the model.
  // Returns whether the system has achieved equilibrium; that is,
  // velocity is 0 and location is unchanged.
  bool RunModel(Vector2f* prev_loc, Vector2f* new_loc, WallTime now=0) {
    if (!now) {
      now = WallTime_Now();
    }
    if (now - last_time_ < kEpsilon) {
      *new_loc = state_.p;
      return false;
    }
    State prev_state = state_;
    Vector2f a;
    while (last_time_ < now) {
      const float dt = std::min<float>(kDeltaTime_, now - last_time_);
      a = Integrate(&state_, (last_time_ - start_time_), dt);
      last_time_ += dt;
    }
    bool complete;
    if (exit_condition_) {
      complete = exit_condition_(&state_, prev_state, last_time_, a);
    } else {
      complete = DefaultExitCondition(&state_, prev_state, last_time_, a);
    }
    *prev_loc = prev_state.p;
    *new_loc = state_.p;
    //LOG("prev: %s, cur: %s, v: %s, dt: %f", *prev_loc, state_.p, state_.v, (now - last_time_));
    return complete || WallTime_Now() - start_time_ > kMaxSimulationTime_;
  }

  // This model applies accelerations to an object whose state is represented
  // by position and velocity.
  struct State {
    Vector2f p;  // position
    Vector2f v;  // velocity
  };
  typedef Vector2f (^AccelerationFunc)(const State& state, float t);
  typedef Vector2f (^AccelerationFilter)(const State& state, float t, const Vector2f& a);
  typedef Vector2f (^LocationFunc)(const State& state, float t);
  typedef bool (^ExitConditionFunc)(State* state, const State& prev_state, float t, const Vector2f& a);

  // Specifies a fixed location.
  static LocationFunc StaticLocation(const Vector2f& spring_loc) {
    Vector2f sl = spring_loc;
    return ^(const State& state, float t) {
      return sl;
    };
  }

  // Spring forces pull towards the location of the spring with varying
  // forces and include a dampening function to slow the approach velocity
  // to 0 as the object reaches the spring.

  // A totally customizable spring.
  void AddSpring(LocationFunc spring_loc, float spring_force, float damp_force) {
    AddSpringWithDampening(spring_loc, spring_force, damp_force);
  }

  // The default spring takes about 1s to pull an object from anywhere on screen.
  void AddDefaultSpring(LocationFunc spring_loc) {
    const float kSpringForce = 100;
    const float kDampeningForce = 20;
    AddSpringWithDampening(spring_loc, kSpringForce, kDampeningForce);
  }

  // Adds a spring which takes 550-600ms to pull an object from anywhere on screen.
  void AddQuickSpring(LocationFunc spring_loc) {
    const float kSpringForce = 500;
    const float kDampeningForce = 50;
    AddSpringWithDampening(spring_loc, kSpringForce, kDampeningForce);
  }

  // Adds a spring that takes about 1.5s to pull an object from anywhere on screen.
  void AddSlowSpring(LocationFunc spring_loc) {
    const float kSpringForce = 10;
    const float kDampeningForce = 5;
    AddSpringWithDampening(spring_loc, kSpringForce, kDampeningForce);
  }

  // Adds a spring which takes 350-400ms to pull an object from anywhere on screen.
  void AddVeryQuickSpring(LocationFunc spring_loc) {
    const float kSpringForce = 750;
    const float kDampeningForce = 55;
    AddSpringWithDampening(spring_loc, kSpringForce, kDampeningForce);
  }

  // Adds a deceleration opposite the current velocity, proportional
  // to the release coefficient of friction.
  static const float kFrictionCoeff_;
  void AddReleaseDeceleration() {
    AddFrictionalDeceleration(kFrictionCoeff_);
  }

  // Adds a filter to be applied to the output of all acceleration
  // functions.  Multiple filters may be added and are applied
  // successively to first the output of all acceleration functions
  // and then to the output of each filter in turn.
  void AddAccelerationFilter(AccelerationFilter filter) {
    filters_.push_back(filter);
  }

  // Customize the conditions under which the simulation is considered
  // complete. By default, uses DefaultExitConditions() as exit
  // conditions.  The supplied function is invoked after each
  // iterative step with the current state of the model, the current
  // time, and the last applied acceleration. The exit conditions
  // function receives a non-const pointer to the underlying state and
  // can modify it to enforce end conditions as necessary.
  void SetExitCondition(ExitConditionFunc exit_func) {
    exit_condition_ = exit_func;
  }

  static bool DefaultExitCondition(State* state, const State& prev_state,
                                   float t, const Vector2f& a) {
    return state->v.equal(Vector2f(0, 0), 1) && state->p.equal(prev_state.p, 1);
  }

 private:
  struct Derivative {
    Vector2f dp;  // derivative of position: velocity
    Vector2f dv;  // derivative of velocity: acceleration
  };

  // Add a spring force (acceleration = -kx, where k is spring force constant
  // and x is distance between spring and object). Also add a dampening force,
  // (acceleration = -bv, where b is the dampening factor and v is the velocity).
  void AddSpringWithDampening(LocationFunc spring_loc,
                              const float spring_force,
                              const float dampening_force) {
    const Vector2f k = -Vector2f(spring_force, spring_force);
    const Vector2f b = -Vector2f(dampening_force, dampening_force);

    accels_.push_back(^(const State& state, float t) {
        return k * (state.p - spring_loc(state, t)) + b * state.v;
      });
  }

  void AddFrictionalDeceleration(float mu) {
    accels_.push_back(^(const State& state, float t) {
        return Vector2f(state.v(0) == 0 ? 0 : (state.v(0) > 0 ? -mu : mu),
                        state.v(1) == 0 ? 0 : (state.v(1) > 0 ? -mu : mu));
      });
  }

  Derivative Evaluate(const State &initial, float t, float dt, const Derivative &d) {
    State state;
    state.p = initial.p + d.dp * dt;
    state.v = initial.v + d.dv * dt;

    Derivative output;
    output.dp = state.v;

    // Compute dv from constituent accelerations.
    output.dv = Vector2f(0, 0);
    for (std::list<AccelerationFunc>::iterator iter = accels_.begin();
         iter != accels_.end();
         ++iter) {
      output.dv += (*iter)(state, t);
    }
    for (std::list<AccelerationFilter>::iterator iter = filters_.begin();
         iter != filters_.end();
         ++iter) {
      output.dv = (*iter)(state, t, output.dv);
    }
    return output;
  }

  // RK4 numerical integrator. Returns the acceleration at time t.
  Vector2f Integrate(State* state, float t, float dt) {
    Derivative a = Evaluate(*state, t, 0, Derivative());
    Derivative b = Evaluate(*state, t, dt * 0.5, a);
    Derivative c = Evaluate(*state, t, dt * 0.5, b);
    Derivative d = Evaluate(*state, t, dt, c);

    const Vector2f dpdt = (a.dp + (b.dp + c.dp) * 2.0 + d.dp) * 1.0 / 6.0;
    const Vector2f dvdt = (a.dv + (b.dv + c.dv) * 2.0 + d.dv) * 1.0 / 6.0;

    state->p = state->p + dpdt * dt;
    state->v = state->v + dvdt * dt;
    return dvdt;
  }

 private:
  std::list<AccelerationFunc> accels_;
  std::list<AccelerationFilter> filters_;
  WallTime start_time_;
  WallTime last_time_;
  State state_;
  ExitConditionFunc exit_condition_;

  static const float kDeltaTime_;
  static const float kMaxSimulationTime_;
};

const float PhysicsModel::kFrictionCoeff_ = 200;     // coefficient of friction for releases
const float PhysicsModel::kDeltaTime_ = 0.020;       // granularity of simulation in seconds
const float PhysicsModel::kMaxSimulationTime_ = 5;   // maximum running time of simulation


@implementation ViewfinderTool

- (id)initWithEnv:(id<ViewfinderToolEnv>)env {
  if (self = [super init]) {
    env_ = env;
    pct_active_ = 0.0;
    mode_ = VF_INACTIVE;
    needs_finish_ = false;
    target_index_ = -1;
    pan_velocity_.reset(new DecayingVelocity(kVelocityHalfLife));
    location_velocity_.reset(new DecayingVelocity(kVelocityHalfLife));
    scroll_velocity_.reset(new DecayingVelocity(kVelocityHalfLife));
    tracking_model_.reset(new PhysicsModel);
    location_model_.reset(new PhysicsModel);
    self.autoresizesSubviews = YES;
    self.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
    self.backgroundColor = [UIColor clearColor];
    self.enabled = NO;
    self.exclusiveTouch = YES;

    // Decrease the {contents,rasterization}Scale so that the backing bitmap
    // for the layer associated with the viewfinder tool is very small and thus
    // consumes very few resources.
    self.layer.contentsScale = 1 / 100.0;
    self.layer.rasterizationScale = 1 / 100.0;

    position_indicator_ = [PositionIndicatorLayer new];
    [self.layer addSublayer:position_indicator_];

    title_font_.acquire(CTFontCreateWithName(
                            (__bridge CFStringRef)kHelveticaMedium,
                            kGroupTitleFontSize, NULL));
    subtitle_font_.acquire(CTFontCreateWithName(
                               (__bridge CFStringRef)kHelvetica,
                               kGroupSubtitleFontSize, NULL));
  }
  return self;
}

- (void)setEnabled:(BOOL)enabled {
  [super setEnabled:enabled];

  // Perform one-time initialization the first time the control is enabled.
  if (!enabled || long_press_recognizer_) {
    return;
  }

  long_press_recognizer_ =
      [[UILongPressGestureRecognizer alloc]
        initWithTarget:self action:@selector(handleLongPress:)];
  long_press_recognizer_.cancelsTouchesInView = NO;
  long_press_recognizer_.minimumPressDuration = 0.300;
  [long_press_recognizer_ setDelegate:self];
  [long_press_recognizer_ setNumberOfTapsRequired:0];
  [self addGestureRecognizer:long_press_recognizer_];

  single_tap_recognizer_ =
      [[UITapGestureRecognizer alloc]
        initWithTarget:self action:@selector(handleSingleTap:)];
  single_tap_recognizer_.cancelsTouchesInView = NO;
  single_tap_recognizer_.delaysTouchesEnded = NO;
  [single_tap_recognizer_ setDelegate:self];
  [single_tap_recognizer_ setNumberOfTapsRequired:1];
  [self addGestureRecognizer:single_tap_recognizer_];
  single_tap_recognizer_.enabled = YES;

  double_tap_recognizer_ =
      [[UITapGestureRecognizer alloc]
        initWithTarget:self action:@selector(handleDoubleTap:)];
  double_tap_recognizer_.cancelsTouchesInView = NO;
  double_tap_recognizer_.delaysTouchesEnded = NO;
  [double_tap_recognizer_ setDelegate:self];
  [double_tap_recognizer_ setNumberOfTapsRequired:2];
  [self addGestureRecognizer:double_tap_recognizer_];
  double_tap_recognizer_.enabled = YES;

  pinch_recognizer_ =
      [[UIPinchGestureRecognizer alloc]
        initWithTarget:self action:@selector(handlePinch:)];
  [pinch_recognizer_ setDelegate:self];
  pinch_recognizer_.cancelsTouchesInView = NO;
  [self addGestureRecognizer:pinch_recognizer_];
  pinch_recognizer_.enabled = YES;

  left_swipe_recognizer_ =
      [[UISwipeGestureRecognizer alloc]
        initWithTarget:self action:@selector(handleSwipeLeft:)];
  [left_swipe_recognizer_ setDelegate:self];
  left_swipe_recognizer_.cancelsTouchesInView = NO;
  left_swipe_recognizer_.direction = UISwipeGestureRecognizerDirectionLeft;
  [self addGestureRecognizer:left_swipe_recognizer_];
  left_swipe_recognizer_.enabled = YES;

  right_swipe_recognizer_ =
      [[UISwipeGestureRecognizer alloc]
        initWithTarget:self action:@selector(handleSwipeRight:)];
  [right_swipe_recognizer_ setDelegate:self];
  right_swipe_recognizer_.cancelsTouchesInView = NO;
  right_swipe_recognizer_.direction = UISwipeGestureRecognizerDirectionRight;
  [self addGestureRecognizer:right_swipe_recognizer_];
  right_swipe_recognizer_.enabled = YES;

  arc_ = [[GLLayer alloc] initWithCallback:^{
      [self renderArc];
    }];
  arc_.hidden = YES;
  [self.layer insertSublayer:arc_ below:position_indicator_];

  [self initGL];

  for (int i = 0; i < ARRAYSIZE(scroll_indicators_); i++) {
    scroll_indicators_[i] = [CAShapeLayer new];
    scroll_indicators_[i].fillColor = kScrollIndicatorColor;
    scroll_indicators_[i].hidden = YES;
    [self.layer insertSublayer:scroll_indicators_[i] below:position_indicator_];
  }
  [self initScrollIndicators];
}

- (void)initGL {
  gradient_shader_.reset(new GLProgram("gradient"));
  if (!gradient_shader_->Compile("Gradient", "")) {
    DIE("unable to compile: %s", gradient_shader_->id());
  }
  gradient_shader_->BindAttribute("a_position", A_POSITION);
  gradient_shader_->BindAttribute("a_tex_coord", A_TEX_COORD);
  if (!gradient_shader_->Link()) {
    DIE("unable to link: %s", gradient_shader_->id());
  }
  u_gradient_mvp_ = gradient_shader_->GetUniform("u_MVP");
  u_gradient_radius1_ = gradient_shader_->GetUniform("u_radius1");
  u_gradient_radius2_ = gradient_shader_->GetUniform("u_radius2");
  u_gradient_color_ = gradient_shader_->GetUniform("u_color");

  solid_shader_.reset(new GLProgram("solid"));
  if (!solid_shader_->Compile("Solid", "")) {
    DIE("unable to compile: %s", solid_shader_->id());
  }
  solid_shader_->BindAttribute("a_position", A_POSITION);
  solid_shader_->BindAttribute("a_color", A_COLOR);
  if (!solid_shader_->Link()) {
    DIE("unable to link: %s", solid_shader_->id());
  }
  u_solid_mvp_ = solid_shader_->GetUniform("u_MVP");

  texture_shader_.reset(new GLProgram("texture"));
  if (!texture_shader_->Compile("Texture", "")) {
    DIE("unable to compile: %s", texture_shader_->id());
  }
  texture_shader_->BindAttribute("a_position", A_POSITION);
  texture_shader_->BindAttribute("a_tex_coord", A_TEX_COORD);
  if (!texture_shader_->Link()) {
    DIE("unable to link: %s", texture_shader_->id());
  }
  u_texture_mvp_ = texture_shader_->GetUniform("u_MVP");
  u_texture_texture_ = texture_shader_->GetUniform("u_texture");
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];
  [self redrawAsync];
}

- (void)activate:(CGPoint)p
  withPinchScale:(float)pinch_scale {
}

- (void)handleLongPress:(UILongPressGestureRecognizer*)recognizer {
  if (recognizer.state == UIGestureRecognizerStateBegan) {
    const CGPoint p = [recognizer locationInView:self];
    [self setViewfinderState:GESTURE_LONG_PRESS touch_loc:p];
  }
}

- (void)handleSingleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  const CGPoint p = [recognizer locationInView:self];
  [self setViewfinderState:GESTURE_SINGLE_TAP touch_loc:p];
}

- (void)handleDoubleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  const CGPoint p = [recognizer locationInView:self];
  [self setViewfinderState:GESTURE_DOUBLE_TAP touch_loc:p];
}

- (void)handlePinch:(UIPinchGestureRecognizer*)recognizer {
  const CGPoint p = [recognizer locationInView:self];
  Gesture gesture = recognizer.state == UIGestureRecognizerStateEnded ?
                    GESTURE_RELEASE : GESTURE_PINCH;
  pinch_scale_ = ClampValue(recognizer.scale, kPinchMinScale, kPinchMaxScale);
  [self setViewfinderState:gesture touch_loc:p];
}

- (void)handleSwipeLeft:(UISwipeGestureRecognizer*)recognizer {
  const CGPoint p = [recognizer locationInView:self];
  [self setViewfinderState:GESTURE_SWIPE_LEFT touch_loc:p];
}

- (void)handleSwipeRight:(UISwipeGestureRecognizer*)recognizer {
  const CGPoint p = [recognizer locationInView:self];
  [self setViewfinderState:GESTURE_SWIPE_RIGHT touch_loc:p];
}

- (CGPoint)transformPoint:(const CGPoint&)p {
  float tx = std::min<float>(self.trackingWidth, std::max<float>(0, p.x));
  return CGPointMake(tx, p.y);
}

- (float)rateOfChange:(float)last_x {
#if defined(LINEAR_INTEGRATION)
  return roc_min_ + roc_slope_ * last_x;
#elif defined(EXPONENTIAL_INTEGRATION)
  return roc_min_ + beta_ * pow(last_x, alpha_);
#endif
}

- (double)integral:(const CGPoint&)last_loc
                 y:(double)y
                 m:(double)m
               log:(bool)log {
#if defined(LINEAR_INTEGRATION)
  const double a = roc_min_;
  const double b = roc_slope_;
  return 0.5 * y * (2 * a + b * (2 * last_loc.x + (y - 2 * last_loc.y) / m));
#elif defined(EXPONENTIAL_INTEGRATION)
  CHECK_NE(m, 0);
  const double x0 = last_loc.x;
  const double y0 = last_loc.y;
  const double delta_y = m * x0 + y - y0;
  const double pow_inv_change = pow(delta_y / m, alpha_);
  double integral;
  if (std::isnan(pow_inv_change)) {
    integral = roc_min_ * y + beta_ * (delta_y / (alpha_ + 1));
  } else {
    integral = roc_min_ * y + beta_ * (delta_y / (alpha_ + 1)) * pow_inv_change;
  }
  if (log || std::isnan(integral)) {
    LOG("computed integral %f from x0: %f, y0: %f, delta_y: %f, m: %f, pow_inv_change: %f, "
        "roc_min_: %f, beta: %f, alpha: %f", integral,
        x0, y0, delta_y, m, pow_inv_change, roc_min_, beta_, alpha_);
    CHECK(!std::isnan(integral));
  }
  return integral;
#endif
}

- (double)delta:(const CGPoint&)new_loc
       last_loc:(const CGPoint&)last_loc
            log:(bool)log {
  const CGPoint tx_new_loc = [self transformPoint:new_loc];
  const CGPoint tx_last_loc = [self transformPoint:last_loc];
  const CGPoint delta_loc = CGPointMake(
      tx_new_loc.x - tx_last_loc.x,
      tx_new_loc.y - tx_last_loc.y);
  if (fabs(delta_loc.y) < kEpsilon) {
    // No integration necessary
    return 0;
  } else if (fabs(delta_loc.x) < kEpsilon) {
    // Integration is simply the rate of change * delta y.
    return [self rateOfChange:tx_new_loc.x] * delta_loc.y;
  }

  // We perform the delta calculation using doubles to avoid any precision
  // problems if delta_loc.y is very small.
  const double m = delta_loc.y / delta_loc.x;
  const double new_val = [self integral:tx_last_loc y:tx_new_loc.y m:m log:log];
  const double old_val = [self integral:tx_last_loc y:tx_last_loc.y m:m log:log];
  return new_val - old_val;
}

// Compute the delta Y necessary to move from "cur_loc" to "new_loc"
// such that position integrates from cur_pos to new_pos. The
// y-coordinate of "new_loc" is ignored.
- (float)deltaY:(float)new_pos
        cur_pos:(float)cur_pos
        new_loc:(const CGPoint&)new_loc
        cur_loc:(const CGPoint&)cur_loc {
#if defined(LINEAR_INTEGRATION)
  CHECK(false) << "delta Y for lineary integration still needs to be worked out";
#elif defined(EXPONENTIAL_INTEGRATION)
  const CGPoint tx_new_loc = [self transformPoint:new_loc];
  const CGPoint tx_cur_loc = [self transformPoint:cur_loc];
  const float dx = tx_new_loc.x - tx_cur_loc.x;

  if (fabs(dx) < kEpsilon) {
    return (new_pos - cur_pos) / [self rateOfChange:tx_cur_loc.x];
  }

  const float roc_new = [self rateOfChange:tx_new_loc.x] - roc_min_;
  const float roc_cur = [self rateOfChange:tx_cur_loc.x] - roc_min_;

  return (new_pos - cur_pos) /
      (roc_min_ + ((roc_new * tx_new_loc.x - roc_cur * tx_cur_loc.x) /
                   (dx * (alpha_ + 1))));
#endif
}

// Finds the book-ending indexes which bracket the specified position.
// Returns an Indexes struct, which includes {start-index, end-index,
// and the interpolation factor relating the two}.
- (Indexes)indexesForPosition:(float)p {
  std::vector<float>::const_iterator iter = std::lower_bound(
      positions_.begin(), positions_.end(), p);
  if (iter == positions_.end()) {
    CHECK(iter != positions_.begin());
    --iter;
  } else {
    CHECK_GE(*iter, p);
  }
  const int index = iter - positions_.begin();
  const float cur_position = *iter;
  if (cur_position > p) {
    if (iter != positions_.begin()) {
      --iter;
      const float prev_position = *iter;
      const float r = (p - prev_position) / (cur_position - prev_position);
      return Indexes(index - 1, index, r);
    }
  }
  return Indexes(index, index, 0);
}

- (WallTime)timeForPosition:(float)p {
  const Indexes indexes = [self indexesForPosition:p];
  return Interp(indexes.interp, 0, 1, timestamps_[indexes.start],
                timestamps_[indexes.end]);
}

- (float)positionForTimeAscending:(WallTime)t {
  std::vector<WallTime>::const_iterator iter = std::lower_bound(
      timestamps_.begin(), timestamps_.end(), t, std::less<WallTime>());
  if (iter == timestamps_.end()) {
    CHECK(iter != timestamps_.begin());
    --iter;
  } else {
    CHECK_GE(*iter, t);
  }
  const int index = iter - timestamps_.begin();
  const WallTime cur_timestamp = *iter;
  if (cur_timestamp > t) {
    if (index > 0) {
      const WallTime prev_timestamp = timestamps_[index - 1];
      const float r = (t - prev_timestamp) / (cur_timestamp - prev_timestamp);
      const float cur_position = positions_[index];
      const float prev_position = positions_[index - 1];
      return prev_position + r * (cur_position - prev_position);
    }
  }
  // Extrapolate based on the beginning and ending timestamps and positions.
  if (t <= timestamps_.front()) {
    return min_tracking_pos_ - (timestamps_.front() - t) *
        (max_tracking_pos_ - min_tracking_pos_) / (max_time_ - min_time_);
  } else {
    CHECK_GE(t, timestamps_.back());
    return max_tracking_pos_ + (t - timestamps_.back()) *
        (max_tracking_pos_ - min_tracking_pos_) / (max_time_ - min_time_);
  }
}

- (float)positionForTimeDescending:(WallTime)t {
  std::vector<WallTime>::const_iterator iter = std::lower_bound(
      timestamps_.begin(), timestamps_.end(), t, std::greater<WallTime>());
  if (iter == timestamps_.end()) {
    CHECK(iter != timestamps_.begin());
    --iter;
  } else {
    CHECK_LE(*iter, t);
  }
  const int index = iter - timestamps_.begin();
  const WallTime cur_timestamp = *iter;
  if (cur_timestamp < t) {
    if (index > 0) {
      const WallTime prev_timestamp = timestamps_[index - 1];
      const float r = (t - cur_timestamp) / (prev_timestamp - cur_timestamp);
      const float cur_position = positions_[index];
      const float prev_position = positions_[index - 1];
      return cur_position + r * (prev_position - cur_position);
    }
  }
  // Extrapolate based on the beginning and ending timestamps and positions.
  if (t <= timestamps_.front()) {
    return max_tracking_pos_ + (timestamps_.front() - t) *
        (max_tracking_pos_ - min_tracking_pos_) / (max_time_ - min_time_);
  } else {
    CHECK_GE(t, timestamps_.back());
    return min_tracking_pos_ - (t - timestamps_.back()) *
        (max_tracking_pos_ - min_tracking_pos_) / (max_time_ - min_time_);
  }
}

- (float)positionForTime:(WallTime)t {
  if (env_.viewfinderTimeAscending) {
    return [self positionForTimeAscending:t];
  }
  return [self positionForTimeDescending:t];
}

- (float)positionForAngle:(double)radians
                   circle:(const Circle&)c {
  const CGPoint arc_coords = c.arc_coords(radians);
  return cur_pos_ + [self delta:arc_coords last_loc:cur_loc_ log:false];
}

- (double)angleForPosition:(double)p
                    circle:(const Circle&)c {
  double s = kPi - c.theta / 2;
  double e = s + c.theta;
  while (fabs(e - s) * c.radius > 0.5) {
    const double m = s + (e - s) / 2;
    const float p_m = [self positionForAngle:m circle:c];
    CHECK(!std::isnan(p_m));
    if (p < p_m) {
      s = m;
    } else if (p > p_m) {
      e = m;
    } else {
      s = m;
      break;
    }
  }
  return s;
}

- (CGPoint)coordsForPosition:(double)p
                      circle:(const Circle&)c {
  if (c.degenerate) {
    const float x = int(c.center.x - c.radius);
    return CGPointMake(x, cur_loc_.y + [self deltaY:p
                                            cur_pos:cur_pos_
                                            new_loc:CGPointMake(x, 0)
                                            cur_loc:cur_loc_]);
  } else {
    return c.arc_coords([self angleForPosition:p circle:c]);
  }
}

// Solve for the delta in the current location's y coordinate which if
// moved to directly from the current x coordinate, will set cur_pos_
// to the specified position 'p'.
- (double)deltaYForPosition:(double)p
               fromPosition:(double)pos
                 atLocation:(CGPoint)loc {
  const CGPoint tx_loc = [self transformPoint:loc];
  float roc;
  if ([self isModeJumpScrolling]) {
    roc = [self rateOfChange:self.trackingWidth];
  } else if ([env_ viewfinderElasticDial]) {
    roc = [self rateOfChange:tx_loc.x];
  } else {
    Interval ai = [self getArcInterval];
    roc = -(ai.second - ai.first) / self.trackingHeight;
  }
  return (p - pos) / roc;
}

- (int)indexAtLocation:(CGPoint)pt
            arc_coords:(CGPoint*)arc_coords {
  // Locates the index of the episode closest to the specified point.
  // Returns -1 if no index matches.
  UIFont* title_font = kGroupTitleFont;
  const float height = title_font.lineHeight;
  const float search_y = pt.y - height / 2;
  int index = -1;

  std::map<float,VisibleGroup>::const_iterator iter = visible_.lower_bound(search_y);
  if (iter == visible_.end()) {
    CHECK(!visible_.empty());
    *arc_coords = visible_.rbegin()->second.pt;
    index = visible_.rbegin()->second.index;
  } else {
    if (iter != visible_.begin()) {
      const float below_diff = iter->second.pt.y - search_y;
      std::map<float,VisibleGroup>::const_iterator prev_iter =
          visible_.lower_bound(search_y - below_diff);
      if (prev_iter != iter) {
        const float above_diff = search_y - prev_iter->second.pt.y;
        CHECK_LE(above_diff, below_diff);
        iter = prev_iter;
      }
    }
    *arc_coords = iter->second.pt;
    index = iter->second.index;
  }
  if (layer_cache_.find(index) != layer_cache_.end()) {
    EpisodeTextLayer* layer = layer_cache_[index].layer;
    // Verify the x coordinate is close enough to the label.
    if (pt.x >= layer.frame.origin.x &&
        pt.x <= (layer.frame.origin.x + layer.width)) {
      return index;
    }
  }
  return -1;
}

- (Interval)getArcInterval {
  // Computes the interval from the start to the end of the arc.
  const Circle c = [self getCircle:cur_loc_];
  return Interval([self positionForAngle:(kPi + c.theta / 2) circle:c],
                  [self positionForAngle:(kPi - c.theta / 2) circle:c]);
}

- (Interval)getInterval {
  const CGPoint last_loc = [self transformPoint:cur_loc_];
  const float interval = self.trackingHeight * [self rateOfChange:last_loc.x];
  const float y_ratio = last_loc.y / self.trackingHeight;
  return Interval(cur_pos_ - y_ratio * interval,
                  cur_pos_ + (1.0 - y_ratio) * interval);
}

- (float)inactiveWidth {
  return kArcWidth;
}

- (float)groupHeaderHeight {
  UIFont* title_font = kGroupTitleFont;
  UIFont* subtitle_font = kGroupSubtitleFont;
  return title_font.lineHeight + subtitle_font.lineHeight;
}

// Sets the current position. If the mode enforces bounds constraints,
// and those constraints are exceeded, returns true.
- (bool)updateCurrentPosition:(float)new_pos {
  if ([self doesModeTrackScrollVelocity]) {
    scroll_velocity_->Adjust(Vector2f(0, new_pos - cur_pos_));
  }

  float bounded_pos = new_pos;
  if ([env_ viewfinderElasticDial]) {
    bounded_pos = std::max<float>(
        bounded_pos, min_pos_ + cur_loc_.y);
    bounded_pos = std::min<float>(
        bounded_pos, max_pos_ - (self.bounds.size.height - cur_loc_.y));
  } else {
    bounded_pos = std::max<float>(
        bounded_pos, min_pos_ - self.bounds.size.height / 2);
    bounded_pos = std::min<float>(
        bounded_pos, max_pos_ + self.bounds.size.height / 2);
  }
  cur_pos_ = [self doesModeBoundPosition] ? bounded_pos : new_pos;
  [env_ viewfinderUpdate:self position:cur_pos_ - cur_loc_.y];
  return bounded_pos != new_pos;
}

- (void)setTargetIndex:(int)index {
  // Add/remove boosted weight from new and old targets respectively.
  // This is O(n), but seems not worth the effort to change; setting
  // a target is done so rarely.
  for (int i = 0; i < weights_.size(); i++) {
    // Clear boost from original target.
    if (weights_[i].second == target_index_) {
      weights_[i].first -= kTargetWeightBoost;
    } else if (weights_[i].second == index) {
      // Add boost to new target.
      weights_[i].first += kTargetWeightBoost;
    }
  }
  target_index_ = index;
  // Keep weights sorted.
  sort(weights_.begin(), weights_.end(), std::greater<std::pair<float,int> >());
}

- (WallTime)currentOuterTime:(WallTime)t {
  return [env_ viewfinderCurrentOuterTime:t];
}

- (WallTime)currentInnerTime:(WallTime)t {
  return [env_ viewfinderCurrentInnerTime:t];
}

- (WallTime)nextOuterTime:(WallTime)t {
  return [env_ viewfinderNextOuterTime:t];
}

- (WallTime)nextInnerTime:(WallTime)t {
  return [env_ viewfinderNextInnerTime:t];
}

- (float)trackingWidth {
  return self.bounds.size.width - kRightMargin;
}

- (float)trackingHeight {
  return self.bounds.size.height;
}

- (Circle)getCircle:(const CGPoint&) p {
  // Gets the circle (center, radius) that goes through the two endpoints of
  // the current x coordinate (p.x) and just touches the left edge of the
  // screen. Also computes the degrees (in radians) of the small arc through
  // the three points.
  bool degenerate = false;
  double x = ([self isModeJumpScrolling] && orig_mode_ == VF_INACTIVE) ? 0 :
             ClampValue(p.x - kArcMargin, 0, self.trackingWidth);
  if (x <= 0) {
    degenerate = true;
    x = 0.1;
  }
  // Coordinate at the top of the screen.
  const double a = x;
  const double b = 0;
  // Coordinate at the bottom of the screen.
  const double e = x;
  const double f = self.bounds.size.height;
  // Coordinate at the center of the left edge of the screen.
  const double c = 0;
  const double d = (f - b) / 2;
  const double k = ((a*a+b*b)*(e-c) + (c*c+d*d)*(a-e) + (e*e+f*f)*(c-a)) /
      (2*(b*(e-c)+d*(a-e)+f*(c-a)));
  const double h = ((a*a+b*b)*(f-d) + (c*c+d*d)*(b-f) + (e*e+f*f)*(d-b)) /
      (2*(a*(f-d)+c*(b-f)+e*(d-b)));
  const double rsqr = (a-h)*(a-h)+(b-k)*(b-k);
  const double theta = acos(((a-h)*(e-h)+(b-k)*(f-k)) / rsqr);
  //LOG("x: %f, h: %f, k: %f, radius: %f", x, h, k, sqrt(rsqr));
  const float x_offset = pct_active_ * kArcWidth;
  return Circle(CGPointMake(h + x_offset, k), sqrt(rsqr), theta, degenerate);
}

- (Circle)getHalfCircle:(const Circle&) c {
  // Create a new circle which allows angles to be located anywhere on
  // kPi radians. This prevents text (or tick marks, etc.) from
  // getting cut off by the bounds set on the circle (the 'theta'
  // variable). Further, we translate the circle used to locate the
  // episode text to the right by a constant factor. This has the
  // effect of rendering the text at a location consistent with where
  // the scroll position would move if the user aimed at that
  // offset. This accounts (somewhat imperfectly) for users' tendency
  // to aim at the middle or end of the text string, not at the very
  // beginning where it touches the arc.
  const double center_x = std::min<double>(cur_loc_.x + c.radius,
                                           c.center.x + kEpisodeAimCorrection);
  const CGPoint center = CGPointMake(center_x, c.center.y);
  return Circle(center, c.radius, kPi, c.degenerate);
}

- (void)drawEpisodes {
  const float episode_alpha =
      (pct_active_ > 0.0) ? 1.0 :
      Interp(scroll_velocity_->magnitude(),
             kMinHeaderScrollVelocity, kMaxHeaderScrollVelocity, 1, 0);

  UIFont* title_font = kGroupTitleFont;
  UIFont* subtitle_font = kGroupSubtitleFont;

  const Circle& c = circle_;
  const Circle half_c = [self getHalfCircle:c];

  // Determine the maximum number of group titles/subtitles we can display on
  // the screen without overlap.
  const float title_height = title_font.lineHeight;
  const float subtitle_height = subtitle_font.lineHeight;
  const float max_groups = floor(self.bounds.size.height / (title_height + subtitle_height));

  // Start the transition from full to short title at max_groups / 2 and end it
  // at max_groups.
  const Interval interval = [self getInterval];
  const float interval_size = interval.second - interval.first;
  float title_transition =
      Interp((interval.second - interval.first) / heights_[0],
             max_groups / 2, max_groups, 0, 1);
  // Disallow partially transitioned titles unless actively tracking.
  if (![self canModeShowLabelTransitions]) {
    title_transition = int(title_transition + 0.5);
  }

  const float kMinDistance = 150 * 1000;  // In m
  const float kMaxDistance = 5000 * 1000;  // In m

  const float kEpisodeSelectAlphaThreshold = 0.30;
  const float kEpisodeDisplayAlphaThreshold = 0.01;

  // Constants determining how labels fade.
  const float kFadeStart = title_height * 2;
  const float kFadeEnd = title_height * 1.25;
  // The faded neighbor factor allows a group to be crowded in closer
  // to a neighbor whose alpha is attenuated. The factor is expressed
  // in pixels and varies from 0 to the stated value with the inverse
  // of the neighbor's alpha.
  const float kFadedNeighborFactor = title_height / 2;
  // How much to scale groups at the periphery.
  const float kMaxScale = 1.0;//0.8;

  // Make a copy of the existing layers. Every layer that is still in use will
  // get removed from old_layers.
  ViewfinderLayerCache old_layers(layer_cache_);
  visible_.clear();

  for (int i = 0; i < weights_.size(); i++) {
    const int index = weights_[i].second;
    // This is the index into the total array of groups which may be
    // available if only a fraction are being shown currently.
    const int group_index = start_group_ + index;
    float p = positions_[index];
    float alpha = episode_alpha;  // May be modified for pinned group
    const float group_height = heights_[index];

    // Be careful not to ignore episodes as soon as their position
    // extends beyond the top of the interval. We still want to show
    // them while any part of the text should be visible.
    if (p + group_height < (interval.first - interval_size * 0.10) ||
        p > (interval.second + interval_size * 0.10)) {
      continue;
    }

    ViewfinderLayerData* layer_data = &layer_cache_[index];
    if (!layer_data->layer) {
      layer_data->layer = [EpisodeTextLayer new];
      layer_data->layer.titleFont = title_font_.get();
      layer_data->layer.subtitleFont = subtitle_font_.get();
      layer_data->layer.fullTitle =
          [env_ viewfinderGroupTitle:self index:group_index];
      layer_data->layer.shortTitle =
          [env_ viewfinderGroupShortTitle:self index:group_index];
      layer_data->layer.fullSubtitle =
          [env_ viewfinderGroupSubtitle:self index:group_index];
      layer_data->layer.shortSubtitle =
          [env_ viewfinderGroupShortSubtitle:self index:group_index];
      [self.layer insertSublayer:layer_data->layer
                           below:position_indicator_];
    } else {
      old_layers.erase(index);
    }

    // Set the layer opacity to 0 until we've determined if the layer is
    // visible.
    EpisodeTextLayer* layer = layer_data->layer;
    layer.opacity = 0;

    // Determine label heights.
    const string& title = title_transition < 1 ?
        layer_data->layer.fullTitle :
        layer_data->layer.shortTitle;
    const string& subtitle = title_transition < 1 ?
        layer_data->layer.fullSubtitle :
        layer_data->layer.shortSubtitle;
    const float height = (title.empty() ? 0 : title_height) +
        (subtitle.empty() ? 0 : subtitle_height);
    if (height == 0) {
      continue;
    }

    // If viewfinder is only partially active (or not at all), pin the
    // first visible group's title.
    if (p < interval.first && p + group_height > interval.first && pct_active_ < 1.0) {
      p = std::min<float>(interval.first, p + group_height - height);
      // Fade out the pinned group as the viewfinder dial activates.
      alpha *= (1.0 - pct_active_);
    }

    CGPoint pt = [self coordsForPosition:p circle:half_c];

    // Episodes scale depending on 'curvature' of current interval.
    // This gives the viewfinder a vaguely spherical aspect when
    // pulled to its extreme limits.
    const float title_scale = Interp(fabs(pt.y - c.center.y) / c.radius, 0, 1, 1.0, kMaxScale);

    // Find bracketing groups (based on y coordinate of already-drawn
    // groups), and depending on proximity and alpha, compute this
    // group's alpha.
    std::map<float,VisibleGroup>::const_iterator iter = visible_.lower_bound(pt.y);
    float next_alpha = alpha;
    float prev_alpha = alpha;
    if (iter != visible_.end()) {
      CHECK_LE(pt.y, iter->second.pt.y);
      float diff_y = iter->second.pt.y - pt.y;
      if (diff_y < kFadeStart) {
        diff_y += kFadedNeighborFactor * (1.0 - iter->second.alpha);
        next_alpha *= Interp(diff_y, kFadeEnd, kFadeStart, 0, 1);
      }
    }
    if (iter != visible_.begin()) {
      iter--;
      CHECK_LE(iter->second.pt.y, pt.y);
      float diff_y = pt.y - iter->second.pt.y;
      if (diff_y < kFadeStart) {
        diff_y += kFadedNeighborFactor * (1.0 - iter->second.alpha);
        prev_alpha *= Interp(diff_y, kFadeEnd, kFadeStart, 0, 1);
      }
    }

    const float title_alpha = std::min<float>(next_alpha, prev_alpha);
    if (title_alpha == 0) {
      continue;
    }
    CHECK(!ContainsKey(visible_, pt.y));
    visible_[pt.y] = VisibleGroup(index, pt, title_alpha);

    // Even though we keep track of groups with some degree of alpha,
    // don't bother rendering nearly-invisible groups.
    if (title_alpha < kEpisodeDisplayAlphaThreshold) {
      continue;
    }

    if ((pt.y + title_height + subtitle_height) <= 0 ||
        pt.y >= self.frame.size.height) {
      continue;
    }

    if (pct_active_ > 0.0) {
      // Compute angle for tick marks, but only if they are being drawn.
      layer_data->angle = [self angleForPosition:p circle:half_c];
    }

    // Ensure the top-left and bottom-left corner of the text lies within the arc.
    const float top_left_y = pt.y - c.center.y;
    const float top_left_x = c.center.x - sqrt(
        std::max<float>(0, c.radius * c.radius - top_left_y * top_left_y));
    const float bottom_left_y = pt.y + height - c.center.y;
    const float bottom_left_x = c.center.x - sqrt(
        std::max<float>(0, c.radius * c.radius - bottom_left_y * bottom_left_y));
    pt.x = std::max(top_left_x, bottom_left_x);
    layer.frame = CGRectMake(pt.x, pt.y, self.bounds.size.width, height);

    // The episode title header background (fades as viewfinder activates).
    if (pct_active_ < 1.0) {
      layer.backgroundColor = MakeUIColor(
          0, 0, 0, (1.0 - pct_active_) * 0.6 * title_alpha).CGColor;
    } else {
      layer.backgroundColor = [UIColor clearColor].CGColor;
    }
    layer.opacity = title_alpha;

    // The color of the episode.
    if (index == target_index_) {
      layer.textColor = Blend(kGroupTitleTextRgb, kViewfinderOrangeRgb, pct_active_);
    } else {
      float dist_ratio = pct_active_ *
          ClampValue((distances_[index] - kMinDistance) / (kMaxDistance - kMinDistance), 0, 1);
      layer.textColor = Blend(kGroupTitleTextRgb, kExoticLocaleBlueRgb, dist_ratio);
    }

    layer.transition = title_transition;
    layer.scale = title_scale;
  }

  for (ViewfinderLayerCache::iterator iter(old_layers.begin());
       iter != old_layers.end();
       ++iter) {
    [iter->second.layer removeFromSuperlayer];
    layer_cache_.erase(iter->first);
  }

  // Remove groups from the visible vector which shouldn't be
  // selectable because they're too faded..
  for (std::map<float,VisibleGroup>::iterator iter = visible_.begin();
       iter != visible_.end(); ) {
    std::map<float,VisibleGroup>::iterator prev_iter = iter;
    ++iter;
    if (prev_iter->second.alpha < kEpisodeSelectAlphaThreshold ||
        ((prev_iter->second.pt.y + title_height + subtitle_height) <= 0 ||
         prev_iter->second.pt.y >= self.frame.size.height)) {
      visible_.erase(prev_iter);
    }
  }
}

// TODO(pmattis): Move drawing of tick marks to the GLLayer.
- (void)drawArcTickMark:(const Circle&)c
                context:(CGContextRef)context
                  angle:(float)angle
           delta_radius:(float)delta_radius
                 length:(float)length
                  width:(float)width
              intensity:(float)intensity {
  const float kTickAngle = width / c.radius;
  const float sin_angle = sin(angle);
  const float highlight = std::min<float>(1.0, intensity * 1.33);
  const float shadow = intensity * 0.75;
  float fgs[] = { Interp(-sin_angle, -0.5, 0.5, shadow, highlight),
                  Interp(sin_angle, -0.5, 0.5, shadow, highlight) };
  CGContextSetLineWidth(context, length);
  CGContextSetRGBStrokeColor(context, fgs[0], fgs[0], fgs[0], 1);
  CGContextAddArc(context, c.center.x, c.center.y, c.radius + length / 2 + delta_radius,
                  angle - kTickAngle / 2, angle, false);
  CGContextDrawPath(context, kCGPathStroke);

  CGContextSetRGBStrokeColor(context, fgs[1], fgs[1], fgs[1], 1);
  CGContextAddArc(context, c.center.x, c.center.y, c.radius + length / 2 + delta_radius,
                  angle, angle + kTickAngle / 2, false);
  CGContextDrawPath(context, kCGPathStroke);
}

- (BOOL)pointInside:(CGPoint)p
          withEvent:(UIEvent*)event {
  if (self.hidden || !self.enabled) {
    return NO;
  }
  return YES;
}

- (void)begin:(CGPoint)p {
  if (!needs_finish_) {
    touch_loc_ = p;
    cur_loc_ = CGPointMake(0, self.bounds.size.height / 2);
    cur_pos_ = std::max<float>(cur_pos_, cur_loc_.y);
    pan_velocity_->Reset();
    location_velocity_->Reset();
    [env_ viewfinderBegin:self];
    needs_finish_ = true;
  }
}

- (void)finish {
  if (needs_finish_) {
    visible_.clear();
    [self setTargetIndex:-1];
    if (cur_pos_ - cur_loc_.y < 0) {
      [env_ viewfinderUpdate:self position:0];
    }
    [env_ viewfinderFinish:self];
    needs_finish_ = false;
  }
}

- (void)initialize {
  // If not initialized, handle that now.
  const std::pair<int, int> groups = [env_ viewfinderGroups:self];
  start_group_ = groups.first;
  end_group_ = groups.second;
  [self initPositions];
}

- (void)close:(bool)animate {
  if (!animate) {
    mode_ = VF_INACTIVE;
  }
  [self setViewfinderState:GESTURE_CLOSE touch_loc:touch_loc_];
}

- (void)initPositions {
  CHECK_LE(start_group_, end_group_);
  outer_times_.clear();
  positions_.clear();
  heights_.clear();

  min_pos_ = std::numeric_limits<float>::max();
  max_pos_ = self.bounds.size.height;

  min_time_ = std::numeric_limits<WallTime>::max();
  max_time_ = 0;

  positions_.resize(end_group_ - start_group_);
  heights_.resize(end_group_ - start_group_);
  if (positions_.empty()) {
    return;
  }
  timestamps_.resize(positions_.size());
  distances_.resize(positions_.size());
  weights_.resize(positions_.size());

  for (int i = 0; i < positions_.size(); ++i) {
    const int index = start_group_ + i;
    const CGRect b = [env_ viewfinderGroupBounds:self index:index];
    min_pos_ = std::min(min_pos_, CGRectGetMinY(b));
    max_pos_ = std::max(max_pos_, CGRectGetMaxY(b));
    // Adjust the scroll position of each group to be the middle of the row.
    positions_[i] = CGRectGetMinY(b);
    heights_[i] = b.size.height;

    const WallTime t = [env_ viewfinderGroupTimestamp:self index:index];
    timestamps_[i] = t;
    outer_times_.insert([self currentOuterTime:t]);

    distances_[i] = [env_ viewfinderGroupLocationDistance:self index:index];
    const float weight = kVolumeWeightFactor * [env_ viewfinderGroupVolumeWeight:self index:index] +
                         kLocationWeightFactor * [env_ viewfinderGroupLocationWeight:self index:index];
    weights_[i] = std::make_pair(weight, i);

    // Determine the 2 inner time steps before the episode's timestamp.
    const WallTime p =
        [self currentInnerTime:
                [self currentInnerTime:
                        [self currentInnerTime:t] - 1] - 1];
    outer_times_.insert([self currentOuterTime:p]);
    min_time_ = std::min(min_time_, p);

    // Determine the 2 inner time steps after the episode's timestamp.
    const WallTime n = [self nextInnerTime:[self nextInnerTime:t]];
    outer_times_.insert([self currentOuterTime:n]);
    max_time_ = std::max(max_time_, n);
  }

  // Sort groups by weight.
  sort(weights_.begin(), weights_.end(), std::greater<std::pair<float,int> >());

  // LOG("min-time=%s   max-time=%s",
  //     WallTimeFormat("%F %T", min_time_),
  //     WallTimeFormat("%F %T", max_time_));
  // LOG("min-pos=%s   max-pos=%s", min_pos_, max_pos_);

  //const float total = max_pos_ - min_pos_;
  min_tracking_pos_ = min_pos_;// - total * 0.1;
  max_tracking_pos_ = max_pos_;// + total * 0.1;
  const float tracking_total = max_tracking_pos_ - min_tracking_pos_;

  roc_min_ = self.bounds.size.height / self.trackingHeight;
  roc_max_ = tracking_total / self.trackingHeight;
#if defined(LINEAR_INTEGRATION)
   roc_slope_ = (roc_max_ - roc_min_) / self.trackingWidth;
#elif defined(EXPONENTIAL_INTEGRATION)
  // This is the percentage of tracking width which we want to have
  // the rate-of-change increase by pct_change from min to max over
  // the horizontal space defined by pct_margin of tracking width.
  const double pct_change = 0.05;
  const double pct_margin = 0.50;
  const double margin = pct_margin * self.trackingWidth;
  const double diff = roc_max_ - roc_min_;
  if (diff <= 0) {
    beta_ = 0;
    alpha_ = 1;
  } else {
    beta_ = exp((log(diff) * log(margin) - log(diff * pct_change) * log(self.trackingWidth)) /
                (log(margin) - log(self.trackingWidth)));
    alpha_ = (log(diff) - log(beta_)) / log(self.trackingWidth);
  }
  //LOG("exponential integration; roc_min_: %.03f, roc_max_: %.03f, left margin: %.01f, "
  //"width: %.01f, pct_change: %.03f, alpha: %f, beta: %f", roc_min_, roc_max_,
  //margin, self.trackingWidth, pct_change, alpha_, beta_);
#endif
}

- (void)maybeLoadNewGroups:(float)scroll_adjust {
  // Adjust start and end groups to populate the arc if the
  // auto-scroll would take us past the current interval.
  const float scroll_groups = scroll_adjust / heights_[0];
  if (scroll_adjust > 0 && cur_pos_ == max_pos_) {
    const int max_group = [env_ viewfinderNumGroups:self];
    const int new_end_group = std::min<int>(
        end_group_ + ceil(scroll_groups), max_group);
    if (new_end_group != end_group_) {
      start_group_ += new_end_group - end_group_;
      end_group_ = new_end_group;
      [self initPositions];
    }
  } else if (scroll_adjust < 0 && cur_pos_ == min_pos_) {
    const int new_start_group = std::max<int>(
        start_group_ + floor(scroll_groups), 0);
    if (new_start_group != start_group_) {
      end_group_ += new_start_group - start_group_;
      start_group_ = new_start_group;
      [self initPositions];
    }
  }
}

- (float)deltaForTracking:(const CGPoint&)new_loc
                 last_loc:(const CGPoint&)last_loc {
  if ([self isModeJumpScrolling]) {
    // With jump scroll, the delta is computed at the max rate of change.
    return [self delta:CGPointMake(self.trackingWidth, new_loc.y)
              last_loc:CGPointMake(self.trackingWidth, last_loc.y)
                   log:false];
  } else if ([env_ viewfinderElasticDial]) {
    // With elastic dial, the normal delta integration applies.
    return [self delta:new_loc last_loc:last_loc log:false];
  } else {
    // In rigid dial mode, the delta is defined by the arc interval.
    const float delta_y = new_loc.y - last_loc.y;
    Interval ai = [self getArcInterval];
    float roc = (ai.second - ai.first) / self.trackingHeight;
    if (fabs(delta_y) < kEpsilon) {
      return 0;
    }
    return -roc * delta_y;
  }
}

- (bool)setCurrentLocation:(CGPoint)new_loc
                 integrate:(bool)integrate {
  // Adjust the current location velocity.
  Vector2f move(new_loc.x - cur_loc_.x, new_loc.y - cur_loc_.y);
  location_velocity_->Adjust(move);

  float new_pos = cur_pos_;
  if (integrate) {
    const float delta = [self deltaForTracking:new_loc last_loc:cur_loc_];
    [self maybeLoadNewGroups:delta];
    new_pos = cur_pos_ + delta;
  }

  CGRect bounds = [self getCurrentBounds];
  CGPoint bounded_loc = CGPointMake(ClampValue(new_loc.x, bounds.origin.x,
                                               bounds.origin.x + bounds.size.width),
                                    ClampValue(new_loc.y, bounds.origin.y,
                                               bounds.origin.y + bounds.size.height));
  // Add in the contribution from the movement of the current
  // location's y coordinate.
  new_pos += bounded_loc.y - cur_loc_.y;

  cur_loc_ = bounded_loc;
  return [self updateCurrentPosition:new_pos];
}

- (CGRect)getCurrentBounds {
  // If the mode always stays centered, we restrict the y coordinate's
  // vertical movement.
  if ([self doesModeStayCentered]) {
    return CGRectMake(0, [self getCenteringYCoord], self.trackingWidth, 0);
  } else {
    return CGRectMake(0, 0, self.trackingWidth, self.trackingHeight);
  }
}

- (float)getCenteringYCoord {
  // Return the y coordinate to which we're centering, depending on
  // mode and current position.
  if ([self isModeZooming]) {
    float center_y = 0.25 * self.bounds.size.height;
    float cur_pos = cur_pos_ - cur_loc_.y;
    if (cur_pos - center_y < min_pos_) {
      center_y = cur_pos - min_pos_;
    } else if (cur_pos_ + (self.bounds.size.height - center_y) > max_pos_) {
      center_y = cur_pos_ + self.bounds.size.height - max_pos_;
    }
    return center_y;
  } else {
    return 0.5 * self.bounds.size.height;
  }
}

- (bool)isModeAnimating {
  return (mode_ == VF_ACTIVATING ||
          mode_ == VF_RELEASING ||
          mode_ == VF_ACTIVATING_JS ||
          mode_ == VF_RELEASING_JS ||
          mode_ == VF_STOWING ||
          mode_ == VF_ZEROING ||
          mode_ == VF_ZOOM_ZEROING ||
          mode_ == VF_ZOOMING ||
          mode_ == VF_BOUNCING);
}

- (bool)isModeZooming {
  return (mode_ == VF_ZOOMING ||
          mode_ == VF_ZOOM_ZEROING);
}

- (bool)isModeTracking {
  return (mode_ == VF_TRACKING ||
          mode_ == VF_MARGIN_SCROLLING ||
          mode_ == VF_JUMP_SCROLLING ||
          mode_ == VF_SCALING);
}

- (bool)isModeTrackable {
  return (mode_ == VF_QUIESCENT ||
          mode_ == VF_TRACKING ||
          mode_ == VF_RELEASING ||
          mode_ == VF_RELEASING_JS ||
          mode_ == VF_ZOOMING ||
          mode_ == VF_ZEROING ||
          mode_ == VF_ZOOM_ZEROING ||
          mode_ == VF_BOUNCING ||
          (mode_ == VF_ACTIVATING &&
           cur_loc_.x > kActivationInterruptPct * self.trackingWidth));
}

- (bool)isModeJumpScrolling {
  return (mode_ == VF_ACTIVATING_JS ||
          mode_ == VF_RELEASING_JS ||
          mode_ == VF_JUMP_SCROLLING);
}

- (bool)canActivateJumpScroll:(CGPoint)touch_loc {
  return ((mode_ == VF_INACTIVE ||
           mode_ == VF_TRACKING ||
           mode_ == VF_RELEASING ||
           mode_ == VF_RELEASING_JS ||
           mode_ == VF_QUIESCENT) &&
          self.tracking &&
          (touch_loc.x > self.bounds.size.width - kJumpScrollMargin));
}

- (bool)doesModeAnimateOnRelease {
  return (mode_ == VF_TRACKING ||
          mode_ == VF_MARGIN_SCROLLING ||
          mode_ == VF_SCALING);
}

- (bool)doesModeTrackScrollVelocity {
  return (mode_ == VF_INACTIVE ||
          mode_ == VF_SCROLLING);
}

- (bool)doesModeBoundPosition {
  return !(mode_ == VF_RELEASING ||
           mode_ == VF_BOUNCING ||
           mode_ == VF_ZEROING ||
           mode_ == VF_ZOOM_ZEROING);
}

- (bool)doesModeStayCentered {
  return (![env_ viewfinderElasticDial] &&
          (mode_ == VF_ACTIVATING ||
           mode_ == VF_TRACKING ||
           mode_ == VF_RELEASING ||
           mode_ == VF_ZEROING ||
           mode_ == VF_ZOOM_ZEROING ||
           mode_ == VF_BOUNCING));
}

- (bool)doesModeNeedCentering {
  return (([env_ viewfinderElasticDial] &&
           (mode_ == VF_RELEASING ||
            mode_ == VF_ZEROING ||
            mode_ == VF_ZOOM_ZEROING ||
            mode_ == VF_BOUNCING)) ||
          mode_ == VF_RELEASING_JS);
}

- (bool)doesModeNeedTimedCallbacks {
  return ([self isModeAnimating] ||
          mode_ == VF_MARGIN_SCROLLING ||
          mode_ == VF_SCROLLING);
}

- (bool)shouldModeBounce {
  return ((mode_ == VF_RELEASING ||
           mode_ == VF_RELEASING_JS ||
           mode_ == VF_ZEROING) &&
          ((cur_pos_ - cur_loc_.y < min_pos_) ||
           (cur_pos_ - cur_loc_.y > max_pos_ - self.bounds.size.height)));
}

- (bool)canModeBeStowed {
  return (mode_ == VF_TRACKING ||
          mode_ == VF_RELEASING ||
          mode_ == VF_MARGIN_SCROLLING ||
          mode_ == VF_SCALING ||
          mode_ == VF_PINCHING ||
          mode_ == VF_BOUNCING ||
          mode_ == VF_QUIESCENT);
}

- (bool)canModeShowLabelTransitions {
  return (([env_ viewfinderElasticDial] && mode_ == VF_TRACKING) ||
          mode_ == VF_SCALING ||
          mode_ == VF_PINCHING);
}

// Tracking animations adjust the scroll offset as if tracking.
- (void)initTrackingAnimation:(PhysicsModel::LocationFunc)target_loc {
  tracking_model_->Reset(Vector2f(cur_loc_), Vector2f(0, 0));
  tracking_model_->AddDefaultSpring(target_loc);
  [self initLocationAnimation];
}

- (void)initZoomAnimation {
  tracking_model_->Reset(Vector2f(cur_loc_), Vector2f(0, 0));
  const Vector2f target_loc(0, cur_loc_.y);
  tracking_model_->AddQuickSpring(PhysicsModel::StaticLocation(target_loc));
  [self initLocationAnimation];
}

// This is a shortcut for a tracking animation to stow the viewfinder.
- (void)initStowAnimation {
  tracking_model_->Reset(Vector2f(cur_loc_), Vector2f(0, 0));
  const Vector2f target_loc(0, cur_loc_.y);
  tracking_model_->AddVeryQuickSpring(PhysicsModel::StaticLocation(target_loc));
  [self initLocationAnimation];
}

// For zeroing, we attach a scroll bounce spring. If transitioning
// from zeroing to zoom-zeroing (a double tap), we don't clear
// the velocity but we do need to reset the models as the centering
// y coordinate will change from center to 25% for zoom.
- (void)initZeroAnimation:(bool)reset_velocity {
  const float center_y = [self getCenteringYCoord];
  const float delta_y = [self deltaYForPosition:positions_[target_index_]
                                   fromPosition:cur_pos_ - cur_loc_.y + center_y
                                     atLocation:cur_loc_];
  const Vector2f v(tracking_model_->velocity());
  tracking_model_->Reset(Vector2f(cur_loc_), reset_velocity ? Vector2f(0, 0) : v);
  const Vector2f zero_loc(cur_loc_.x, cur_loc_.y + delta_y);
  tracking_model_->AddQuickSpring(PhysicsModel::StaticLocation(zero_loc));
  [self initLocationAnimation];
  [self attachScrollBounceCondition];
}

// On release, set up a tracking animation with a frictional force. If
// the touch and release were done in rapid succession, reset_velocity
// will be false in order to avoid having quick swipes unintentionally
// slow the scroll.
- (void)initReleaseAnimation:(bool)reset_velocity {
  const float vertical_threshold = [env_ viewfinderElasticDial] ? 0.90 : 0.20;
  Vector2f release_velocity = pan_velocity_->velocity();
  // If the dial was released in a mostly (90%) vertical direction,
  // remove the x-component.
  if (pan_velocity_->IsSwipe(DecayingVelocity::UP, 0, vertical_threshold) ||
      pan_velocity_->IsSwipe(DecayingVelocity::DOWN, 0, vertical_threshold)) {
    release_velocity.x() = 0;
  }
  // Use existing velocity instead of release velocity if
  // "reset_velocity" is false, the existing velocity is greater than the
  // release velocity, and there's < 45 degree angle between velocities.
  if (!reset_velocity &&
      tracking_model_->velocity().length() > release_velocity.length() &&
      tracking_model_->velocity().dot(release_velocity) > (sqrt(2) / 2)) {
    release_velocity = tracking_model_->velocity();
  }
  tracking_model_->Reset(Vector2f(cur_loc_), release_velocity);
  tracking_model_->AddReleaseDeceleration();
  [self initLocationAnimation];
  [self attachScrollBounceCondition];
}

// Sets an exit condition on the tracking model looking for scroll
// buffer going out of bounds. If this happens, starts a scroll
// bounce animation.
- (void)attachScrollBounceCondition {
  PhysicsModel::ExitConditionFunc exit = ^(PhysicsModel::State* state,
                                           const PhysicsModel::State& prev_state,
                                           float t, const Vector2f& a) {
    if ([self shouldModeBounce]) {
      return true;
    }
    return PhysicsModel::DefaultExitCondition(state, prev_state, t, a);
  };
  tracking_model_->SetExitCondition(exit);
}

// Attach a spring to the location which will properly align either
// the top or bottom of the scroll buffer with the visible display.
- (void)initScrollBounceAnimation {
  // The actual scroll buffer offset, which may be less than or
  // greater than min_pos_ and max_pos_ respectively.
  Vector2f p = tracking_model_->position();
  Vector2f v = tracking_model_->velocity();
  const float center_y = [self getCenteringYCoord];
  float target_pos;
  if (cur_pos_ - cur_loc_.y <= min_pos_) {
    target_pos = min_pos_ + center_y;
  } else if (cur_pos_ - cur_loc_.y >= (max_pos_ - self.bounds.size.height)) {
    target_pos = max_pos_ - self.bounds.size.height + center_y;
  }
  const float y = p(1) + [self deltaYForPosition:target_pos
                                    fromPosition:cur_pos_ - cur_loc_.y + center_y
                                      atLocation:p.ToCGPoint()];

  // Zero out x coordinate of current velocity.
  v(0) = 0;
  tracking_model_->Reset(p, v);
  // These constants are geared towards medium response and a small
  // degree of oscillation on a reasonable initial velocity.
  const float kSpring = 75;
  const float kDamp = 12;
  PhysicsModel::LocationFunc spring_loc = ^(const PhysicsModel::State& state, float t) {
    return Vector2f(state.p(0), y);
  };
  tracking_model_->AddSpring(spring_loc, kSpring, kDamp);

  // Note that we initialize the location animation here, as it's
  // conditions for exit should not include a check against the target
  // y coordinate we're using for the tracking model. The location has
  // another spring for centering and will end up with a much different
  // value for y position.
  [self initLocationAnimation];

  // Exit the physics simulation according to the precision of current
  // value of cur_pos_ instead of the default checks for equilibrium.
  const float kMinTolerance = 0.5;
  PhysicsModel::ExitConditionFunc exit = ^(PhysicsModel::State* state,
                                           const PhysicsModel::State& prev_state,
                                           float t, const Vector2f& a) {
    if (fabs(state->v(1)) < 1 && fabs(cur_pos_ - target_pos) <= kMinTolerance) {
      cur_loc_.y = [self getCenteringYCoord];
      [self updateCurrentPosition:target_pos];
      return true;
    }
    return false;
  };
  tracking_model_->SetExitCondition(exit);
}

- (void)initActivateJSAnimation {
  const float implied_pos = touch_loc_.y * (max_pos_ - min_pos_) / self.bounds.size.height + min_pos_;
  const float delta_y = [self deltaYForPosition:implied_pos
                                   fromPosition:cur_pos_
                                     atLocation:CGPointMake(self.trackingWidth, cur_loc_.y)];
  tracking_model_->Reset(Vector2f(self.trackingWidth, cur_loc_.y), Vector2f(0, 0));
  tracking_model_->AddQuickSpring(PhysicsModel::StaticLocation(
                                        Vector2f(self.trackingWidth, cur_loc_.y + delta_y)));

  location_model_->Reset(Vector2f(cur_loc_), Vector2f(0, 0));
  const Vector2f target_loc((orig_mode_ == VF_INACTIVE) ? self.trackingWidth :  cur_loc_.x, touch_loc_.y);
  location_model_->AddQuickSpring(PhysicsModel::StaticLocation(target_loc));
}

// De-activates jump scroll by moving the current location to
// self.trackingWidth.
- (void)initReleaseJSAnimation {
  // Reset tracking.
  tracking_model_->Reset(Vector2f(cur_loc_), Vector2f(0, 0));
  // If jump scroll was initiated from an inactive state, stow.
  if (orig_mode_ == VF_INACTIVE) {
    *location_model_ = *tracking_model_;
    location_model_->AddVeryQuickSpring(PhysicsModel::StaticLocation(Vector2f(0, cur_loc_.y)));
  } else {
    // Otherwise, allow centering.
    [self initLocationAnimation];
  }
}

// The location model, which updates cur_loc_, is initialized from the
// current state of the tracking model. If the mode needs centering,
// an additional spring force is added to pull the current location to
// a centering y coordinate.
- (void)initLocationAnimation {
  *location_model_ = *tracking_model_;
  if ([self doesModeNeedCentering]) {
    // We add the centering spring as an acceleration filter. The current
    // velocity of the tracking model is compared to a maximum threshold
    // velocity. Once the underlying velocity is smaller than the threshold,
    // the frictional force is ignored and a new spring force is added
    // to center the location.
    location_model_->AddAccelerationFilter(^(const PhysicsModel::State& state, float t, const Vector2f& a) {
        const float center_y = [self getCenteringYCoord];
        const float tracking_v = fabs(tracking_model_->velocity()(1));
        if (tracking_v > kCenteringVelocity) {
          return Vector2f(a);
        }
        // A value of 100 pulls very hard. 10 is like molasses.
        const float kSpring = 80;
        // A value of 10 makes a pronounced spring-like effect.
        // 15 is minor; 20 is slowly guided in with no bounce.
        const float kDamp = 17;
        // Note we must use "cur_loc_.y" here instead of state.v(1) because
        // while state.v(1) is unconstrained, cur_loc_.y is bounded to the
        // screen dimensions, so the two can get out of sync.
        const float y_accel = -kSpring * (cur_loc_.y - center_y) - kDamp * state.v(1);
        return Vector2f(a(0), y_accel);
      });
  }
}

- (void)dispatchTimedCallback {
  if (!dispatched_ && [self doesModeNeedTimedCallbacks]) {
    dispatched_ = true;
    dispatch_after_main(kAnimationDelay, ^{
        dispatched_ = false;
        if (([self isModeAnimating] && [self animate]) ||
            (mode_ == VF_MARGIN_SCROLLING && [self marginScroll]) ||
            (mode_ == VF_SCROLLING && [self fadePositionIndicator])) {
          [self dispatchTimedCallback];
        }
        [self setViewfinderState:GESTURE_NONE touch_loc:touch_loc_];
        [self redraw];
      });
  }
}

- (void)redrawAsync {
  if (!needs_redraw_) {
    needs_redraw_ = true;
    dispatch_after_main(0, ^{
        [self redraw];
      });
  }
}

- (bool)animate {
  Vector2f last_loc;
  Vector2f new_loc;
  bool location_model_done = true;
  if (!location_model_->RunModel(&last_loc, &new_loc)) {
    // Compute location as a delta between the model's last & new
    // locations. cur_loc_ is bounded by the screen dimensions, so it
    // can get out of sync with the model.
    [self setCurrentLocation:(Vector2f(cur_loc_) + (new_loc - last_loc)).ToCGPoint()
                   integrate:false];
    location_model_done = false;
  }

  bool tracking_model_done = true;
  if (!tracking_model_->RunModel(&last_loc, &new_loc)) {
    const float delta = [self deltaForTracking:new_loc.ToCGPoint() last_loc:last_loc.ToCGPoint()];
    [self maybeLoadNewGroups:delta];
    [self updateCurrentPosition:(cur_pos_ + delta)];
    tracking_model_done = false;
  } else if ([self shouldModeBounce]) {
    [self setViewfinderState:GESTURE_BOUNCE touch_loc:touch_loc_];
    return true;
  }

  if ((tracking_model_done && location_model_done) ||
      ([self canModeBeStowed] && cur_loc_.x <= kActivationMargin)) {
    [self setViewfinderState:GESTURE_TRANSITION touch_loc:touch_loc_];
    return false;
  }
  return true;
}

- (bool)marginScroll {
  // Handle auto-scrolling in vertical margins.
  float delta_y = 0.0;
  if (touch_loc_.y < kVerticalMargin) {
    delta_y = touch_loc_.y - kVerticalMargin;
    delta_y = std::max<float>(delta_y, -kVerticalMargin);
  } else if (touch_loc_.y > self.bounds.size.height - kVerticalMargin) {
    delta_y = touch_loc_.y - (self.bounds.size.height - kVerticalMargin);
    delta_y = std::min<float>(delta_y, kVerticalMargin);
  }

  const CGPoint new_loc = CGPointMake(cur_loc_.x, cur_loc_.y + delta_y);
  [self setCurrentLocation:new_loc integrate:true];
  return true;
}

- (bool)fadePositionIndicator {
  if (scroll_velocity_->magnitude() > kMinPIScrollVelocity) {
    return true;
  } else {
    mode_ = VF_INACTIVE;
    return false;
  }
}

- (void)drawPositionIndicator {
  if (pct_active_ > 0.0) {
    position_indicator_.opacity = 0;
  } else {
    // The degree to which we should blend between the position indicator and
    // the episode labels.
    const float avail_height = [env_ viewfinderVisibleBounds:self].size.height -
                               position_indicator_.frame.size.height;
    const float y = (cur_pos_ / (max_pos_ - min_pos_)) * avail_height;
    position_indicator_.opacity =
        Interp(scroll_velocity_->magnitude(),
               kMinPIScrollVelocity, kMaxPIScrollVelocity, 0, 1);
    position_indicator_.origin = CGPointMake(0, y);

    // Use the first of the bookended positions as the display time.
    const int index = [self indexesForPosition:cur_pos_ - cur_loc_.y + y].start;
    const WallTime t = [env_ viewfinderGroupTimestamp:self index:index];
    position_indicator_.text =
        NewNSString([env_ viewfinderFormatPositionIndicator:t]);
  }
}

// Draw the viewfinder arc.
- (void)drawArc {
  if (pct_active_ == 0.0) {
    arc_.hidden = YES;
    return;
  }

  arc_.frame = self.bounds;
  arc_.hidden = NO;
  [arc_ setNeedsDisplay];
}

- (void)renderArc {
  // Set up our model-view-projection matrix.
  Matrix4f mvp;
  const CGRect b = arc_.bounds;
  mvp.ortho(0, b.size.width, b.size.height, 0, -10, 10);

  [self renderArcGradient:mvp rect:arc_.bounds];
  [self renderArcTicks:mvp];
  [self renderArcText:mvp];
}

- (void)renderArcGradient:(const Matrix4f&)mvp
                     rect:(const CGRect&)r {
#if 0
  CGRect solid_r;

  // Clamp the maximum value of the radius to something reasonable. Larger
  // values seem to cause some sort of floating point precision issues in the
  // fragment shader resulting in incorrect calculations for the distance of
  // the fragment to the center of the gradient.
  Circle c = circle_;
  const double kMaxRadius = 50000;
  if (c.radius > kMaxRadius) {
    c.center.x = c.center.x - c.radius + kMaxRadius;
    c.radius = kMaxRadius;
  }

  {
    // We know a large portion of the gradient area is a solid color. Render this
    // area using the solid shader instead of the more expensive gradient shader.
    const float min_radius = c.radius - kMaskGradientWidth;
    float a = min_radius / sqrt(2);
    if (2 * a > r.size.height) {
      // The circle intersects the top/bottom of the screen. It is better
      // (we'll cover more of the screen) to use a rectangle that is the height
      // of the screen than to use a square with sides that are 2*a in length.
      solid_r.origin.x = c.center.x -
          sqrt(min_radius * min_radius - c.center.y * c.center.y);
      solid_r.origin.y = 0;
      solid_r.size.width = c.center.x - solid_r.origin.x;
      solid_r.size.height = r.size.height;
    } else {
      solid_r = CGRectMake(c.center.x - a, c.center.y - a, 2 * a, 2 * a);
    }
    [self renderSolid:mvp rect:solid_r color:Vector4f(0, 0, 0, 0.5)];
  }

  // Set up the uniform variables for our shader program.
  glUseProgram(gradient_shader_->name());
  // GL_CHECK_ERRORS();
  glUniformMatrix4fv(u_gradient_mvp_, 1, false, mvp.data());

  // While it would be more natrual to pass in the radius and alpha arrays as
  // arrays of floats, we want to avoid any unnecessary work in the fragment
  // shader so we bundle them up into exactly the types and formats they'll be
  // needed in for the fragment shader.
  const GLfloat radius[9] = {
    c.radius - kMaskGradientWidth,
    c.radius,
    c.radius + 1,
    c.radius + kInnerArcWidth - 1,
    c.radius + kInnerArcWidth,
    c.radius + kInnerArcWidth + 1,
    c.radius + kArcWidth - 1,
    c.radius + kArcWidth,
    c.radius + kArcWidth + 1,
  };
  const Vector4f radius1[2] = {
    Vector4f(radius[0], radius[2], radius[4], radius[6]),
    Vector4f(radius[1], radius[3], radius[5], radius[7]),
  };
  const Vector4f radius2[2] = {
    Vector4f(radius[1], radius[3], radius[5], radius[7]),
    Vector4f(radius[2], radius[4], radius[6], radius[8]),
  };
  glUniform4fv(u_gradient_radius1_, ARRAYSIZE(radius1), radius1[0].data());
  glUniform4fv(u_gradient_radius2_, ARRAYSIZE(radius2), radius2[0].data());

  const Vector4f color[9] = {
    Vector4f(0, 0, 0, 0.5),         // radius - kMaskGradientWidth,
    Vector4f(0, 0, 0, 1.0),         // radius
    Vector4f(0.2, 0.2, 0.2, 1),     // radius + 1
    Vector4f(0.3, 0.3, 0.3, 1),     // radius + kInnerArcWidth - 1
    Vector4f(0.2, 0.2, 0.2, 1),     // radius + kInnerArcWidth
    Vector4f(0.15, 0.15, 0.15, 1),  // radius + kInnerArcWidth + 1
    Vector4f(0.2, 0.2, 0.2, 1),     // radius + kArcWidth - 1
    Vector4f(0.3, 0.3, 0.3, 1),     // radius + kArcWidth
    Vector4f(0, 0, 0, 0),           // radius + kArcWidth + 1
  };
  glUniform4fv(u_gradient_color_, ARRAYSIZE(color), color[0].data());

  CGRect pieces[3];
  // The portion of the original rect that is above the solid area.
  pieces[0] = CGRectMake(
      r.origin.x, r.origin.y, r.size.width, solid_r.origin.y - r.origin.y);
  // The portion of the original rect that is below the solid area.
  pieces[1] = CGRectMake(
      r.origin.x, CGRectGetMaxY(solid_r), r.size.width,
      CGRectGetMaxY(r) - CGRectGetMaxY(solid_r));
  // The portion of the original rect that is to the left of the solid area.
  pieces[2] = CGRectMake(
      r.origin.x, CGRectGetMaxY(pieces[0]),
      solid_r.origin.x - r.origin.x,
      CGRectGetMinY(pieces[1]) - CGRectGetMaxY(pieces[0]));

  glEnableVertexAttribArray(A_POSITION);
  glEnableVertexAttribArray(A_TEX_COORD);

  for (int i = 0; i < ARRAYSIZE(pieces); ++i) {
    if (CGRectIsEmpty(pieces[i])) {
      continue;
    }

    // Draw our rect. Note that we substract center from the texture
    // coordinates here so that we don't have to perform that computation in
    // the shader.
    const float x1 = pieces[i].origin.x;
    const float y1 = pieces[i].origin.y;
    const float x2 = x1 + pieces[i].size.width;
    const float y2 = y1 + pieces[i].size.height;
    const struct {
      Vector4f position;
      Vector2f tex_coord;
    } kVertices[4] = {
      { Vector4f(x1, y1, 0, 1), Vector2f(x1, y1) - Vector2f(c.center) },
      { Vector4f(x2, y1, 0, 1), Vector2f(x2, y1) - Vector2f(c.center) },
      { Vector4f(x1, y2, 0, 1), Vector2f(x1, y2) - Vector2f(c.center) },
      { Vector4f(x2, y2, 0, 1), Vector2f(x2, y2) - Vector2f(c.center) },
    };

    // Set up the attributes for our shader program.
    glVertexAttribPointer(A_POSITION, 4, GL_FLOAT, GL_FALSE,
                          sizeof(kVertices[0]), &kVertices[0].position);
    glVertexAttribPointer(A_TEX_COORD, 2, GL_FLOAT, GL_FALSE,
                          sizeof(kVertices[0]), &kVertices[0].tex_coord);
    // GL_CHECK_ERRORS();

    // Validate the program and draw our triangles.
    // CHECK(gradient_shader_->Validate());
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
  }

  // Disable the attributes we set up.
  glDisableVertexAttribArray(A_POSITION);
  glDisableVertexAttribArray(A_TEX_COORD);
  // GL_CHECK_ERRORS();
#endif

  {
    const Circle& c = circle_;
    const double kRadius[] = {
      -c.radius,
      -kMaskGradientWidth,
      0,
      1,
      kInnerArcWidth - 1,
      kInnerArcWidth,
      kInnerArcWidth + 1,
      kArcWidth - 1,
      kArcWidth,
      kArcWidth + 1,
    };
    const Vector4f kColor[ARRAYSIZE(kRadius)] = {
      Vector4f(0, 0, 0, 0.5),         // -c.radius
      Vector4f(0, 0, 0, 0.5),         // -kMaskGradientWidth,
      Vector4f(0, 0, 0, 1.0),         // 0
      Vector4f(0.2, 0.2, 0.2, 1),     // 1
      Vector4f(0.3, 0.3, 0.3, 1),     // kInnerArcWidth - 1
      Vector4f(0.2, 0.2, 0.2, 1),     // kInnerArcWidth
      Vector4f(0.15, 0.15, 0.15, 1),  // kInnerArcWidth + 1
      Vector4f(0.2, 0.2, 0.2, 1),     // kArcWidth - 1
      Vector4f(0.3, 0.3, 0.3, 1),     // kArcWidth
      Vector4f(0, 0, 0, 0),           // kArcWidth + 1
    };

    vector<Vector4f> position;
    vector<Vector4f> color;
    vector<unsigned short> index;

    // Pre-size the position, color and index vectors.
    position.reserve(10000);
    color.reserve(10000);
    index.reserve(30000);

    // We want to choose the step_angle such that the distance between the
    // line segment connecting 2 points on the arc and the arc itself is
    // constrained to some value (e.g. 1/4 of a pixel).
    const double kArcError = 0.25;
    const double r = c.radius + kRadius[ARRAYSIZE(kRadius) - 1];
    const double step_angle = 2 * acos((r - kArcError) / r);

    for (int i = 1; i < ARRAYSIZE(kRadius); ++i) {
      if (c.degenerate) {
        const float x1 = c.center.x - (c.radius + kRadius[i - 1]);
        const float x2 = c.center.x - (c.radius + kRadius[i]);
        const float h = self.bounds.size.height;
        position.push_back(Vector4f(x1, 0, 0, 1));
        position.push_back(Vector4f(x2, 0, 0, 1));
        position.push_back(Vector4f(x1, h, 0, 1));
        position.push_back(Vector4f(x2, h, 0, 1));
        color.push_back(kColor[i - 1]);
        color.push_back(kColor[i]);
        color.push_back(kColor[i - 1]);
        color.push_back(kColor[i]);
      } else {
        const double r1 = c.radius + kRadius[i - 1];
        const double r2 = c.radius + kRadius[i];
        const float theta = std::max(
            ArcAngle(Vector2f(c.center), r1, self.bounds),
            ArcAngle(Vector2f(c.center), r2, self.bounds));
        // We step through all of the arcs in the same size steps to ensure
        // that triangle coordinates between different radial segments match
        // exactly. We also need to start on a multiple of step_angle from the
        // most extreme start_angle (0).
        const float start =
            floor((kPi - theta / 2) / step_angle) * step_angle;
        const int steps = 2 * (1 + ceil(theta / step_angle));

        Matrix4f m;
        m.translate(-c.center.x, -c.center.y, 0);
        m.rotate(step_angle, 0, 0, 1);
        m.translate(c.center.x, c.center.y, 0);

        position.push_back(c.arc_coords(start, kRadius[i - 1]));
        position.push_back(c.arc_coords(start, kRadius[i]));
        color.push_back(kColor[i - 1]);
        color.push_back(kColor[i]);

        for (int i = 0; i < steps; ++i) {
          position.push_back(m * position[position.size() - 2]);
          color.push_back(color[color.size() - 2]);
        }
      }

      for (int i = 2; i < position.size(); ++i) {
        index.push_back(i - 2);
        index.push_back(i - 1);
        index.push_back(i);
      }
    }

    // Set up the uniform variables for our shader program.
    glUseProgram(solid_shader_->name());
    // GL_CHECK_ERRORS();
    glUniformMatrix4fv(u_solid_mvp_, 1, false, mvp.data());

    // Set up the attributes for our shader program.
    glVertexAttribPointer(A_POSITION, 4, GL_FLOAT, GL_FALSE,
                          sizeof(position[0]), &position[0]);
    glEnableVertexAttribArray(A_POSITION);
    glVertexAttribPointer(A_COLOR, 4, GL_FLOAT, GL_FALSE,
                          sizeof(color[0]), &color[0]);
    glEnableVertexAttribArray(A_COLOR);

    // Validate the program and draw our triangles.
    // CHECK(solid_shader_->Validate());
    glDrawElements(GL_TRIANGLES, index.size(), GL_UNSIGNED_SHORT, &index[0]);
    // LOG("%d triangles", index.size() / 3);

    // Disable the attributes we set up.
    glDisableVertexAttribArray(A_POSITION);
    glDisableVertexAttribArray(A_COLOR);
    // GL_CHECK_ERRORS();
  }
}

- (void)renderSolid:(const Matrix4f&)mvp
               rect:(const CGRect&)r
              color:(const Vector4f&)color {
  // Set up the uniform variables for our shader program.
  glUseProgram(solid_shader_->name());
  // GL_CHECK_ERRORS();
  glUniformMatrix4fv(u_solid_mvp_, 1, false, mvp.data());

  // Draw our rect.
  const float x1 = r.origin.x;
  const float y1 = r.origin.y;
  const float x2 = x1 + r.size.width;
  const float y2 = y1 + r.size.height;
  const struct {
    Vector4f position;
    Vector4f color;
  } kVertices[4] = {
    { Vector4f(x1, y1, 0, 1), color },
    { Vector4f(x2, y1, 0, 1), color },
    { Vector4f(x1, y2, 0, 1), color },
    { Vector4f(x2, y2, 0, 1), color },
  };

  // Set up the attributes for our shader program.
  glVertexAttribPointer(A_POSITION, 4, GL_FLOAT, GL_FALSE,
                        sizeof(kVertices[0]), &kVertices[0].position);
  glEnableVertexAttribArray(A_POSITION);
  glVertexAttribPointer(A_COLOR, 4, GL_FLOAT, GL_FALSE,
                        sizeof(kVertices[0]), &kVertices[0].color);
  glEnableVertexAttribArray(A_COLOR);
  // GL_CHECK_ERRORS();

  // Validate the program and draw our triangles.
  // CHECK(solid_shader_->Validate());
  glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);

  // Disable the attributes we set up.
  glDisableVertexAttribArray(A_POSITION);
  glDisableVertexAttribArray(A_COLOR);
  // GL_CHECK_ERRORS();
}

- (void)renderArcTicks:(const Matrix4f&)mvp {
  vector<Vector4f> position;
  vector<Vector4f> color;
  vector<unsigned short> index;

  for (std::map<float, VisibleGroup>::iterator iter(visible_.begin());
       iter != visible_.end();
       ++iter) {
    // Draw a tick mark on the inner edge of the inner arc for the episode.
    const VisibleGroup& v_group = iter->second;
    const ViewfinderLayerData* layer_data = FindPtrOrNull(layer_cache_, v_group.index);
    CHECK(layer_data != NULL);
    const float height = layer_data->layer.frame.size.height;
    const float tick_angle = layer_data->angle - height / circle_.radius / 2;
    const float width_angle = kEpisodeTickMarkWidth / circle_.radius / 2;

    const int start = position.size();
    index.push_back(start + 0);
    index.push_back(start + 1);
    index.push_back(start + 2);

    position.push_back(circle_.arc_coords(tick_angle - width_angle, 0));
    position.push_back(circle_.arc_coords(tick_angle + width_angle, 0));
    position.push_back(circle_.arc_coords(tick_angle, -kEpisodeTickMarkLength));
    color.push_back(Vector4f(1, 0, 0, 1));
    color.push_back(Vector4f(1, 0, 0, 1));
    color.push_back(Vector4f(1, 0, 0, 1));
  }

  // Set up the uniform variables for our shader program.
  glUseProgram(solid_shader_->name());
  // GL_CHECK_ERRORS();
  glUniformMatrix4fv(u_solid_mvp_, 1, false, mvp.data());

  // Set up the attributes for our shader program.
  glVertexAttribPointer(A_POSITION, 4, GL_FLOAT, GL_FALSE,
                        sizeof(position[0]), &position[0]);
  glEnableVertexAttribArray(A_POSITION);
  glVertexAttribPointer(A_COLOR, 4, GL_FLOAT, GL_FALSE,
                        sizeof(color[0]), &color[0]);
  glEnableVertexAttribArray(A_COLOR);

  // Validate the program and draw our triangles.
  // CHECK(solid_shader_->Validate());
  glDrawElements(GL_TRIANGLES, index.size(), GL_UNSIGNED_SHORT, &index[0]);

  // Disable the attributes we set up.
  glDisableVertexAttribArray(A_POSITION);
  glDisableVertexAttribArray(A_COLOR);
  // GL_CHECK_ERRORS();
}

- (void)renderArcText:(const Matrix4f&)mvp {
  vector<ArcText> outer_text;
  vector<ArcText> inner_text;

  for (std::set<WallTime>::iterator iter(outer_times_.begin());
       iter != outer_times_.end();
       ++iter) {
    const WallTime begin_time = *iter;
    const WallTime end_time = [self nextOuterTime:begin_time];

    {
      const float begin_angle =
          [self angleForPosition:[self positionForTime:begin_time]
                          circle:circle_];
      const float end_angle =
          [self angleForPosition:[self positionForTime:end_time]
                          circle:circle_];
      if (begin_angle >= end_angle) {
        continue;
      }

      outer_text.push_back(ArcText());
      outer_text.back().str = [env_ viewfinderFormatOuterTime:begin_time];
      outer_text.back().orig_str = outer_text.back().str;
      outer_text.back().begin = begin_angle;
      outer_text.back().end = end_angle;
    }

    {
      // The outer time is visible. Loop over the inner times.
      WallTime t = [self currentInnerTime:begin_time];
      float begin_angle =
          [self angleForPosition:[self positionForTime:begin_time]
                          circle:circle_];
      WallTime next;
      float end_angle;
      for (; t < end_time; t = next, begin_angle = end_angle) {
        next = [self nextInnerTime:t];
        end_angle = [self angleForPosition:[self positionForTime:next]
                                    circle:circle_];
        if (begin_angle >= end_angle) {
          continue;
        }

        inner_text.push_back(ArcText());
        inner_text.back().str = [env_ viewfinderFormatInnerTime:t];
        inner_text.back().orig_str = inner_text.back().str;
        inner_text.back().begin = begin_angle;
        inner_text.back().end = end_angle;
      }
    }
  }

  struct {
    const vector<ArcText>& text;
    UIFont* font;
  } glyph_data[] = {
    { outer_text, kOuterFont },
    { inner_text, kInnerFont },
  };

  // Ensure that every we have info for every potential glyph.
  bool rebuild_glyph_texture = false;
  for (int i = 0; i < ARRAYSIZE(glyph_data); ++i) {
    const vector<ArcText>& text = glyph_data[i].text;
    UIFont* font = glyph_data[i].font;

    for (int j = 0; j < text.size(); ++j) {
      const ArcText& a = text[j];
      Slice s(a.str);
      while (!s.empty()) {
        const Slice last(s);
        const int r = utfnext(&s);
        if (r == -1) {
          break;
        }
        GlyphInfo& g = glyphs_[std::make_pair(font, r)];
        if (!g.str) {
          g.str = NewNSString(last.substr(0, last.size() - s.size()));
          rebuild_glyph_texture = true;
        }
      }
    }

    glyphs_[std::make_pair(font, '-')].str = @"-";
  }

  if (rebuild_glyph_texture) {
    typedef std::map<std::pair<UIFont*, int>, GlyphInfo> GlyphMap;

    const float scale = [UIScreen mainScreen].scale;
    int width = 0;
    int height = 0;

    for (GlyphMap::iterator iter(glyphs_.begin());
         iter != glyphs_.end();
         ++iter) {
      GlyphInfo& g = iter->second;
      UIFont* font = iter->first.first;
      g.size = [g.str sizeWithFont:font];
      if (scale != 1) {
        font = [font fontWithSize:font.pointSize * scale];
        g.scaled_size = [g.str sizeWithFont:font];
      } else {
        g.scaled_size = g.size;
      }
      width += 2 + ceil(g.scaled_size.width);
      height = std::max<int>(height, ceil(g.scaled_size.height));
    }

    // Round width to the next multiple of 32 to improve texture performance
    // (according to the Instruments OpenGL Analyzer).
    width += (32 - (width % 32));
    vector<char> data(4 * width * height, 0);
    ScopedRef<CGColorSpaceRef> colorspace(CGColorSpaceCreateDeviceRGB());
    ScopedRef<CGContextRef> context(
        CGBitmapContextCreate(&data[0], width, height, 8,
                              4 * width, colorspace,
                              kCGBitmapByteOrder32Little | kCGImageAlphaPremultipliedFirst));
    CHECK(context.get() != NULL);

    CGContextSetRGBFillColor(context, 1, 1, 1, 1);
    CGContextTranslateCTM(context, 0.0, height);
    CGContextScaleCTM(context, 1.0, -1.0);

    UIGraphicsPushContext(context);

    float x = 1;
    for (GlyphMap::iterator iter(glyphs_.begin());
         iter != glyphs_.end();
         ++iter) {
      GlyphInfo& g = iter->second;
      UIFont* font = iter->first.first;
      if (scale != 1) {
        font = [font fontWithSize:font.pointSize * scale];
      }
      [g.str drawAtPoint:CGPointMake(x, 0) withFont:font];
      g.tx_start = (x + g.scaled_size.width) / width;
      g.tx_end = x / width;
      g.ty_start = g.scaled_size.height / height;
      g.ty_end = 0;
      x += 2 + ceil(g.scaled_size.width);
    }

    UIGraphicsPopContext();

    if (!glyph_tex_.get()) {
      glyph_tex_.reset(new GLMutableTexture2D);
      glyph_tex_->SetFormat(GL_BGRA);
      glyph_tex_->SetType(GL_UNSIGNED_BYTE);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
      glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);

      // Set up the uniform variables for our shader program.
      glUseProgram(texture_shader_->name());
      // Configure the texture for texture unit 0 and specify that as the uniform
      // for the texture shader.
      glActiveTexture(GL_TEXTURE0);
      glBindTexture(GL_TEXTURE_2D, glyph_tex_->name());
      glUniform1i(u_texture_texture_, 0);
    }
    glyph_tex_->SetPixels(width, height, &data[0]);
    GL_CHECK_ERRORS();
  }

  struct {
    vector<ArcText>* text;
    const float offset;
    UIFont* font;
    float tick_radius;
    float tick_length;
    float tick_intensity;
  } data[] = {
    { &outer_text, kOuterTextOffset, kOuterFont,
      kInnerArcWidth, kOuterArcWidth - kOuterArcHighlightWidth,
      kOuterTickMarkIntensity },
    { &inner_text, kInnerTextOffset, kInnerFont,
      kInnerArcShadowWidth, kInnerArcWidth - kInnerArcShadowWidth,
      kInnerTickMarkIntensity },
  };

  vector<Vector4f> position;
  vector<Vector2f> tex_coord;
  vector<unsigned short> index;

  for (int i = 0; i < ARRAYSIZE(data); ++i) {
    const float radius = circle_.radius + data[i].offset;
    const float spacing = 10;
    vector<ArcText>* text = data[i].text;
    UIFont* font = glyph_data[i].font;

    for (int j = 0; j < text->size(); ++j) {
      ArcText* a = &(*text)[j];
      a->line_length = 0;

      Slice s(a->str);
      while (!s.empty()) {
        const Slice last(s);
        const int r = utfnext(&s);
        if (r == -1) {
          break;
        }
        GlyphInfo& g = glyphs_[std::make_pair(font, r)];
        CHECK(g.str != NULL);
        a->line_length += g.size.width;
      }

      const float min_length = a->line_length + 2 * spacing;
      const float arc_length = (a->end - a->begin) * radius;

      if (arc_length < min_length) {
        if (j == 0) {
          // This is the first segment at the bottom of the arc. Grow it so
          // that it is large enough to fit the text.
          a->begin = a->end - min_length / radius;
          continue;
        }
        if (j + 1 == text->size()) {
          // This is the last segment at the top of the arc. Grow it so that it
          // is large enough to fit the text.
          a->end = a->begin + min_length / radius;
          continue;
        }

        // Merge this arc text with the next/previous piece of text.
        //
        // TODO(pmattis): This merging needs improvement as it causes
        // distracting flickering when segments reach the top and bottom of the
        // arc. Should figure out how to make the merging more persistent so
        // that the user never sees "Jan" and "Feb" merging into "Jan-Feb"
        // unless they are changing the zoom.
        if ((a->begin + a->end) / 2 >= kPi) {
          ArcText* n = &(*text)[j + 1];
          a->str = Format("%s-%s", a->orig_str, n->orig_str);
          a->end = n->end;
          text->erase(text->begin() + j + 1);
          j -= 1;
        } else {
          ArcText* p = &(*text)[j - 1];
          p->str = Format("%s-%s", p->orig_str, a->orig_str);
          p->end = a->end;
          text->erase(text->begin() + j);
          j -= 2;
        }
      }
    }

    for (int j = 0; j < text->size(); ++j) {
      const ArcText& a = (*text)[j];
      const float line_angle = a.line_length / radius;
      float angle = a.begin + (a.end - a.begin - line_angle) / 2 - kPi / 2;

      Slice s(a.str);
      while (!s.empty()) {
        const Slice last(s);
        const int r = utfnext(&s);
        if (r == -1) {
          break;
        }
        GlyphInfo& g = glyphs_[std::make_pair(font, r)];
        CHECK(g.str != NULL);

        const int start = position.size();
        index.push_back(start + 0);
        index.push_back(start + 1);
        index.push_back(start + 2);
        index.push_back(start + 3);
        index.push_back(start + 2);
        index.push_back(start + 1);

        Matrix4f m;
        // Translate glyph so that it is horizontally centered and it's
        // baseline is vertically on the edge of the arc.
        m.translate(-g.size.width, radius -
                    (g.size.height - font.ascender) + 0.5, 0);
        // Rotate to the correct orientation and position.
        m.rotate(angle, 0, 0, 1);
        m.translate(circle_.center.x, circle_.center.y, 0);

        position.push_back(m * Vector4f(0, 0, 0, 1));
        position.push_back(m * Vector4f(0, g.size.height, 0, 1));
        position.push_back(m * Vector4f(g.size.width, 0, 0, 1));
        position.push_back(m * Vector4f(g.size.width, g.size.height, 0, 1));

        tex_coord.push_back(Vector2f(g.tx_start, g.ty_start));
        tex_coord.push_back(Vector2f(g.tx_start, g.ty_end));
        tex_coord.push_back(Vector2f(g.tx_end, g.ty_start));
        tex_coord.push_back(Vector2f(g.tx_end, g.ty_end));

        angle += g.size.width / radius;
      }
    }

    // for (int j = 0; j + 1 < text->size(); ++j) {
    //   // Draw tick marks between arc segments.
    //   const ArcText& a = (*text)[j];
    //   [self drawArcTickMark:c
    //                 context:context
    //                   angle:a.end
    //            delta_radius:data[i].tick_radius
    //                  length:data[i].tick_length
    //                   width:2
    //               intensity:data[i].tick_intensity];
    // }
  }

  // Set up the uniform variables for our shader program.
  glUseProgram(texture_shader_->name());
  // GL_CHECK_ERRORS();
  glUniformMatrix4fv(u_texture_mvp_, 1, false, mvp.data());

  // Set up the attributes for our shader program.
  glVertexAttribPointer(A_POSITION, 4, GL_FLOAT, GL_FALSE,
                        sizeof(position[0]), &position[0]);
  glEnableVertexAttribArray(A_POSITION);
  glVertexAttribPointer(A_TEX_COORD, 2, GL_FLOAT, GL_FALSE,
                        sizeof(tex_coord[0]), &tex_coord[0]);
  glEnableVertexAttribArray(A_TEX_COORD);
  glEnable(GL_BLEND);
  // GL_CHECK_ERRORS();

  // Validate the program and draw our triangles.
  // CHECK(texture_shader_->Validate());
  glDrawElements(GL_TRIANGLES, index.size(), GL_UNSIGNED_SHORT, &index[0]);

  // Disable the attributes we set up.
  glDisableVertexAttribArray(A_POSITION);
  glDisableVertexAttribArray(A_TEX_COORD);
  glDisable(GL_BLEND);
}

- (void)drawScrollIndicators {
  for (int i = 0; i < 4; ++i) {
    CAShapeLayer* layer = scroll_indicators_[i];
    if (pct_active_ == 0.0) {
      layer.hidden = YES;
      continue;
    }

    // Is this indicator active?
    float velocity = 0;
    if (i == 0) {
      if ([env_ viewfinderElasticDial]) {
        velocity = std::max<float>((*location_velocity_)(1), 0);
      } else {
        velocity = std::min<float>((*location_velocity_)(1), 0);
      }
    } else if (i == 1) {
      velocity = std::min<float>((*location_velocity_)(0), 0);
    } else if (i == 2) {
      if ([env_ viewfinderElasticDial]) {
        velocity = std::min<float>((*location_velocity_)(1), 0);
      } else {
        velocity = std::max<float>((*location_velocity_)(1), 0);
      }
    } else if (i == 3) {
      velocity = std::max<float>((*location_velocity_)(0), 0);
    }

    // Opacity is equal to the scaled magnitude of scroll speed.
    if (location_velocity_->magnitude() > kMinSIScrollVelocity) {
      layer.opacity = Interp(fabs(velocity), kMinSIScrollVelocity, kMaxSIScrollVelocity, 0.10, 0.90);
    } else {
      layer.opacity = 0.10;
    }
    layer.hidden = NO;
  }
}

- (void)initScrollIndicators {
  const CGPoint kStartPt = CGPointMake(0.5, 0.27835);
  const CGPoint kBezierPts[] = {
    CGPointMake(0.769021, 0.009691), CGPointMake(0.769021, 0.009691), CGPointMake(0.769021, 0.009691),
    CGPointMake(0.784124, 0.000309), CGPointMake(0.814742, 0.000000), CGPointMake(0.798969, 0.000000),
    CGPointMake(0.829588, 0.010928), CGPointMake(0.829588, 0.010928), CGPointMake(0.829588, 0.010928),
    CGPointMake(0.984227, 0.166546), CGPointMake(0.984227, 0.166546), CGPointMake(0.984227, 0.166546),
    CGPointMake(0.999691, 0.185258), CGPointMake(0.999691, 0.216186), CGPointMake(0.999691, 0.201031),
    CGPointMake(0.985155, 0.231649), CGPointMake(0.985155, 0.231649), CGPointMake(0.985155, 0.231649),
    CGPointMake(0.531907, 0.685567), CGPointMake(0.531907, 0.685567), CGPointMake(0.531907, 0.685567),
    CGPointMake(0.515155, 0.701031), CGPointMake(0.485155, 0.701031), CGPointMake(0.500000, 0.701031),
    CGPointMake(0.464227, 0.683969), CGPointMake(0.464227, 0.683969), CGPointMake(0.464227, 0.683969),
    CGPointMake(0.015464, 0.236804), CGPointMake(0.015464, 0.236804), CGPointMake(0.015464, 0.236804),
    CGPointMake(0.000000, 0.216804), CGPointMake(0.000000, 0.185876), CGPointMake(0.000000, 0.201031),
    CGPointMake(0.015155, 0.165258), CGPointMake(0.015155, 0.165258), CGPointMake(0.015155, 0.165258),
    CGPointMake(0.171701, 0.011289), CGPointMake(0.171701, 0.011289), CGPointMake(0.171701, 0.011289),
    CGPointMake(0.185876, 0.000619), CGPointMake(0.216186, 0.000619), CGPointMake(0.201031, -0.000928),
    CGPointMake(0.226804, 0.010619), CGPointMake(0.226804, 0.010619), CGPointMake(0.226804, 0.010619),
  };
  const float kRotations[] = { 0, kPi / 2, kPi, 3 * kPi / 2 };

  for (int i = 0; i < 4; ++i) {
    CAShapeLayer* layer = scroll_indicators_[i];

    // Draw the indicator.
    ScopedRef<CGMutablePathRef> path(CGPathCreateMutable());
    CGPathMoveToPoint(path, NULL, kStartPt.x, kStartPt.y);
    for (int j = 0; j < ARRAYSIZE(kBezierPts); j += 3) {
      CGPathAddCurveToPoint(path, &CGAffineTransformIdentity,
                            kBezierPts[j + 0].x, kBezierPts[j + 0].y,
                            kBezierPts[j + 1].x, kBezierPts[j + 1].y,
                            kBezierPts[j + 2].x, kBezierPts[j + 2].y);
    }
    CGPathCloseSubpath(path);
    const float kScrollIndicatorSize = 75;
    // Translate to middle of screen.
    // TODO(spencer): figure out a better place to compute coordinates,
    //   as the size of the view into which they'll be put is not known
    //   at the time initScrollIndicators is called.
    CGAffineTransform xform = CGAffineTransformMakeTranslation(240, 240);
    // Scale to desired size.
    xform = CGAffineTransformScale(xform, kScrollIndicatorSize, kScrollIndicatorSize);
    // Rotation goes in 90 degree increments.
    xform = CGAffineTransformRotate(xform, kRotations[i]);
    // Translate to middle of screen.
    xform = CGAffineTransformTranslate(xform, -0.5, -0.97);

    [layer setAffineTransform:xform];
    layer.path = path;
  }
}

- (void)setViewfinderState:(Gesture)gesture
                 touch_loc:(CGPoint)touch_loc {
  ViewfinderMode old_mode = mode_;

  if (gesture == GESTURE_TRACK) {
    // Compute movement velocity & magnitude.
    Vector2f move = Vector2f(touch_loc) - Vector2f(touch_loc_);
    pan_velocity_->Adjust(move);
    touch_loc_ = touch_loc;

    if ([env_ viewfinderElasticDial] &&
        (mode_ == VF_TRACKING || mode_ == VF_MARGIN_SCROLLING)) {
      // Handle transitions between tracking & margin scrolling.
      // Margin scrolling only applies to rubberband mode.
      if ((touch_loc.y < kVerticalMargin &&
           cur_pos_ > (min_pos_ + cur_loc_.y)) ||
          (touch_loc.y > self.bounds.size.height - kVerticalMargin &&
           cur_pos_ < max_pos_ - (self.bounds.size.height - cur_loc_.y))) {
        mode_ = VF_MARGIN_SCROLLING;
      } else {
        mode_ = VF_TRACKING;
      }
    } else if ([self isModeTrackable]) {
      mode_ = VF_TRACKING;
      tracking_start_ = WallTime_Now();
    }
  } else if (gesture == GESTURE_LONG_PRESS) {
    if ([self canActivateJumpScroll:touch_loc]) {
      // Activate jump scrolling.
      [self begin:touch_loc];
      orig_mode_ = mode_;
      mode_ = VF_ACTIVATING_JS;
      [self initActivateJSAnimation];
    }
  } else if (gesture == GESTURE_SINGLE_TAP ||
             gesture == GESTURE_DOUBLE_TAP) {
    if (mode_ == VF_INACTIVE) {
      // Pass single tap events up to parent environment.
      if (gesture == GESTURE_SINGLE_TAP) {
        CGPoint scroll_view_loc =
            CGPointMake(touch_loc.x, touch_loc.y + self.frame.origin.y);
        [env_ viewfinderTapAtPoint:self point:scroll_view_loc];
      }
    } else if ([self isModeTrackable] &&
               pan_velocity_->magnitude() < kMaxZeroingPanVelocity) {
      // Start zeroing if the current mode is trackable and the pan
      // velocity is below the maximum allowed or if we're already
      // zeroing or zoom-zeroing.
      ViewfinderMode new_mode = (gesture == GESTURE_SINGLE_TAP) ? VF_ZEROING : VF_ZOOM_ZEROING;
      if (mode_ != VF_ZOOM_ZEROING && new_mode != mode_) {
        mode_ = new_mode;
        CGPoint target_loc;
        // Only set the target on the first tap.
        if (gesture == GESTURE_SINGLE_TAP) {
          [self setTargetIndex:[self indexAtLocation:touch_loc arc_coords:&target_loc]];
          // If no target was selected, stow the viewfinder.
          if (target_index_ == -1) {
            mode_ = VF_STOWING;
            [self initStowAnimation];
          } else {
            if (mode_ == VF_ZEROING) {
              [self initZeroAnimation:true];
            }
          }
        } else if (gesture == GESTURE_DOUBLE_TAP) {
          // On double tap, re-init the zeroing animation, but this
          // time without resetting the velocity.
          [self initZeroAnimation:false];
        }
      }
    }
  } else if (gesture == GESTURE_PINCH) {
    // Activate the viewfinder with a pinching gesture.
    if (mode_ == VF_INACTIVE) {
      [self begin:touch_loc];
    }
    if (mode_ != VF_PINCHING) {
      pinch_start_x_ = mode_ == VF_INACTIVE ? 0 : cur_loc_.x;
      mode_ = VF_PINCHING;
    }
    if (pinch_scale_ > 1.0) {
      cur_loc_.x = pinch_start_x_ + (0 - pinch_start_x_) *
                   ((pinch_scale_ - 1) / (kPinchMaxScale - 1));
    } else {
      cur_loc_.x = pinch_start_x_ + (self.trackingWidth - pinch_start_x_) *
                   ((1 - pinch_scale_) / (1 - kPinchMinScale));
    }
  } else if (gesture == GESTURE_SWIPE_RIGHT) {
    // Right swipe activates the viewfinder.
    if (mode_ == VF_INACTIVE) {
      mode_ = VF_ACTIVATING;
      [self begin:touch_loc];
      // Activates out to a pleasing x coordinate for zoom.
      const float x_coord = kActivationXCoordPct * self.trackingWidth;
      const Vector2f initial_loc(x_coord, cur_loc_.y);
      [self initTrackingAnimation:PhysicsModel::StaticLocation(initial_loc)];
    } else if (mode_ == VF_TRACKING && ![env_ viewfinderElasticDial]) {
      mode_ = VF_SCALING;
    }
  } else if (gesture == GESTURE_SWIPE_LEFT) {
    if (mode_ == VF_TRACKING && ![env_ viewfinderElasticDial]) {
      mode_ = VF_SCALING;
    }
  } else if (gesture == GESTURE_RELEASE) {
    if (mode_ == VF_JUMP_SCROLLING || mode_ == VF_ACTIVATING_JS) {
      mode_ = VF_RELEASING_JS;
      [self initReleaseJSAnimation];
    } else if ([self canModeBeStowed] &&
               cur_loc_.x > 0 && cur_loc_.x < kActivationMargin) {
      mode_ = VF_STOWING;
      [self initStowAnimation];
    } else if ([self canModeBeStowed] && cur_loc_.x < 1) {
      // If viewfinder is pushed all the way off, de-activate.
      mode_ = VF_INACTIVE;
    } else if ([self doesModeAnimateOnRelease]) {
      mode_ = VF_RELEASING;
      // If this is an impulse track (defined as a relatively short
      // track/release motion), we avoid resetting any existing velocity
      // in the tracking physics model.
      const bool impulse_track =
          (WallTime_Now() - tracking_start_ < kImpulseTrackThreshold);
      [self initReleaseAnimation:!impulse_track];
    } else if (mode_ == VF_PINCHING) {
      mode_ = VF_QUIESCENT;
    }
  } else if (gesture == GESTURE_BOUNCE) {
    mode_ = VF_BOUNCING;
    [self initScrollBounceAnimation];
  } else if (gesture == GESTURE_CLOSE) {
    if (mode_ != VF_INACTIVE) {
      mode_ = VF_STOWING;
      [self initStowAnimation];
    } else {
      cur_loc_.x = 0;
    }
  } else if (gesture == GESTURE_TRANSITION) {
    if (mode_ == VF_ACTIVATING) {
      if (self.tracking) {
        mode_ = VF_TRACKING;
      } else {
        mode_ = VF_RELEASING;
        [self initReleaseAnimation:true];
      }
    } else if (mode_ == VF_ACTIVATING_JS) {
      mode_ = VF_JUMP_SCROLLING;
    } else if (mode_ == VF_RELEASING ||
               mode_ == VF_RELEASING_JS) {
      if (cur_loc_.x > 0 && cur_loc_.x < kActivationMargin) {
        mode_ = VF_STOWING;
        [self initStowAnimation];
      } else if (cur_loc_.x == 0) {
        // If viewfinder is pushed all the way off, de-activate.
        mode_ = VF_INACTIVE;
      } else {
        mode_ = VF_QUIESCENT;
      }
    } else if (mode_ == VF_BOUNCING) {
      mode_ = VF_QUIESCENT;
    } else if (mode_ == VF_ZOOM_ZEROING) {
      // If released in zoom zeroing, transition to ZOOMING.
      mode_ = VF_ZOOMING;
      [self initZoomAnimation];
    } else if (mode_ == VF_ZEROING) {
      mode_ = VF_QUIESCENT;
    } else if (mode_ == VF_ZOOMING || mode_ == VF_STOWING) {
      mode_ = VF_INACTIVE;
    } else {
      CHECK([self isModeAnimating]);
    }
  } else {
    CHECK_EQ(gesture, GESTURE_NONE);
    if (mode_ == VF_INACTIVE && scroll_velocity_->magnitude() > kMinPIScrollVelocity) {
      mode_ = VF_SCROLLING;
    }
  }

  // Compute how activated the viewfinder tool is.
  pct_active_ = ClampValue((cur_loc_.x - 1) / kActivationMargin, 0, 1);

  if (mode_ == VF_INACTIVE) {
    [self finish];
  }

  // Compute the circle on which to draw labels.
  circle_ = [self getCircle:cur_loc_];

  if (old_mode != mode_) {
    //LOG("moving from %d to %d from gesture %d", old_mode, mode_, gesture);
    [self dispatchTimedCallback];
  } else {
    //LOG("remaining at mode %d with gesture %d", mode_, gesture);
  }

  if (gesture != GESTURE_NONE) {
    [self redrawAsync];
  }
}

- (BOOL)beginTrackingWithTouch:(UITouch*)touch
                     withEvent:(UIEvent*)event {
  if (mode_ != VF_INACTIVE) {
    touch_loc_ = [touch locationInView:self];
    [self setViewfinderState:GESTURE_TRACK touch_loc:touch_loc_];
  }

  return YES;
}

- (BOOL)continueTrackingWithTouch:(UITouch*)touch
                        withEvent:(UIEvent*)event {
  if (mode_ != VF_INACTIVE) {
    const CGPoint p = [touch locationInView:self];
    Vector2f delta_loc = Vector2f(cur_loc_) - Vector2f(touch_loc_);
    Vector2f delta_touch = Vector2f(p) - Vector2f(touch_loc_);
    [self setViewfinderState:GESTURE_TRACK touch_loc:p];

    // Compute the delta in current scroll position based on movement.
    if (mode_ == VF_SCALING) {
      CHECK(![env_ viewfinderElasticDial]);
      const CGPoint new_loc = {cur_loc_.x + delta_touch(0), cur_loc_.y};
      [self setCurrentLocation:new_loc integrate:false];
    } else if ([self isModeTracking]) {
      if (mode_ == VF_JUMP_SCROLLING) {
        // With jump scroll, zero the delta x and set y exactly.
        delta_touch(0) = 0;
        delta_touch(1) = p.y - cur_loc_.y;
      } else if (![env_ viewfinderElasticDial]) {
        // In rigid dial mode, do not adjust the x coordinate of
        // current location.
        delta_touch(0) = 0;
      } else {
        const float kHoningConstant = 4.0;
        // Compress the delta between the touch location and the
        // current location by adjusting delta_touch so that it moves
        // less quickly if moving towards it and more quickly if away.
        for (int i = 0; i < 2; i++) {
          if (fabs(delta_loc(i)) > kHoningConstant * fabs(delta_touch(i))) {
            const float ratio =
                ClampValue(kHoningConstant * delta_touch(i) / delta_loc(i), -1, 1);
            // If we're moving in the same direction and the current
            // location needs to be slowed down so that the touch
            // location can catch it, the ratio will be positive, so
            // we want to subtract from the intended delta. However,
            // if we're moving in opposite directions and so need to
            // speed up the adjustment, the ratio will be negative
            // and so we'll actually end up adding to the delta.
            delta_touch(i) -= delta_touch(i) * ratio;
          }
        }
      }

      if (mode_ == VF_MARGIN_SCROLLING) {
        // If margin scrolling, we do not adjust current position based
        // on changes in location; zero the delta y.
        delta_touch(1) = 0;
      }

      const CGPoint new_loc = (Vector2f(cur_loc_) + delta_touch).ToCGPoint();
      [self setCurrentLocation:new_loc integrate:true];
    }
  }

  return YES;
}

- (void)endTrackingWithTouch:(UITouch*)touch
                   withEvent:(UIEvent*)event {
  if (mode_ != VF_INACTIVE) {
    [self setViewfinderState:GESTURE_RELEASE touch_loc:[touch locationInView:self]];
    // Clear the pan velocity.
    pan_velocity_->Reset();
  }
}

- (void)cancelTrackingWithEvent:(UIEvent*)event {
}

- (void)redraw {
  needs_redraw_ = false;
  if (positions_.empty()) {
    return;
  }

  // Update current position and track scrolling velocity. We update cur_pos_
  // here because the summary or day views may be scrolled independently of the
  // viewfinder UI.
  if ([self doesModeTrackScrollVelocity]) {
    const float new_pos = self.frame.origin.y + cur_loc_.y;
    scroll_velocity_->Adjust(Vector2f(0, new_pos - cur_pos_));
    cur_pos_ = new_pos;
    if (pct_active_ == 0.0) {
      [self setViewfinderState:GESTURE_NONE touch_loc:touch_loc_];
    }
  } else {
    scroll_velocity_->Adjust(Vector2f(0, 0));
  }

  [CATransaction begin];
  [CATransaction setDisableActions:YES];

  [self drawScrollIndicators];
  [self drawPositionIndicator];
  [self drawEpisodes];
  [self drawArc];

  [CATransaction commit];
}

- (void)drawRect:(CGRect)rect {
  [super drawRect:rect];
  [self redraw];
}

- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer*)recognizer {
  return YES;
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer*)recognizer
       shouldReceiveTouch:(UITouch*)touch {
  return YES;
}

- (BOOL)gestureRecognizer:(UIGestureRecognizer*)a
shouldRecognizeSimultaneouslyWithGestureRecognizer:(UIGestureRecognizer*)b {
  // Don't recognize taps with anything else.
  return !([a isKindOfClass:[UITapGestureRecognizer class]] ||
           [b isKindOfClass:[UITapGestureRecognizer class]]);
}

@end  // ViewfinderTool
