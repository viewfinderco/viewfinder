// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis, Spencer Kimball.

#import <list>
#import <map>
#import <QuartzCore/QuartzCore.h>
#import <UIKit/UIGestureRecognizerSubclass.h>
#import "Appearance.h"
#import "AsyncState.h"
#import "DBFormat.h"
#import "Logging.h"
#import "MathUtils.h"
#import "PhotoView.h"
#import "PhysicsModel.h"
#import "STLUtils.h"
#import "Timer.h"
#import "TimeRange.h"
#import "UIAppState.h"
#import "ValueUtils.h"
#import "ViewfinderTool.h"

namespace {

// Sizes in pixels.
const float kRowTickMarkLength = 2.5;
const float kRowTickMarkWidth = 4;
const float kInnerArcOffset = kRowTickMarkLength + 2;
const float kInnerArcWidth = 14;
const float kInnerArcShadowWidth = 1;
const float kInnerArcHighlightWidth = 1;
const float kInnerFontSize = 11;
const float kInnerTextOffset = kInnerArcOffset + 3;
const float kOuterArcOffset = kInnerArcOffset + kInnerArcWidth;
const float kOuterArcWidth = 14;
const float kOuterArcShadowWidth = 1;
const float kOuterArcHighlightWidth = 1;
const float kOuterFontSize = 12;
const float kOuterTextOffset = kOuterArcOffset + 3;
const float kMinArcSegmentLength = 100;
const float kArcWidth = kOuterArcOffset + kOuterArcWidth;
const float kScrollBarWidth = 6;
const float kScrollBarMinHeight = 16;
const float kScrollBarMargin = 2;
const float kCurrentTimeLength = 75;
const float kOutlineWidth = 1;

const int kMaxNewLayersPerRedraw = 5;
const float kMinScrollPositionDelta = 0.5;
const double kArcError = 0.1;  // 1/10 of a pixel
const float kOvershootFactor = 1.05;

static const float kPositionIndicatorRadius = 4;
static const float kPositionIndicatorYBorder = 3;
static const float kPositionIndicatorLeftBorder = 5;
static const float kPositionIndicatorRightBorder = 10;
static const float kPositionIndicatorTouchBorder = 10;
static const float kPositionIndicatorTouchOffset = 60;

// In seconds.
const float kQuiescenceDuration = 0.300;
const float kPositionIndicatorFadeDuration = 0.500;
const float kScrollVelocityHalfLife = 0.020;

const float kActivationXCoordPct = 0.60;     // x coord (as %) for activation
const float kActivationInterruptPct = 0.50;  // when can activation be interrupted?

const float kPinchMinScale = 0.2;
const float kPinchMaxScale = 2.0;

// In pixels / second.
const float kMinPIScrollVelocity = 100;      // start transition to position indicator
const float kMaxPIScrollVelocity = 200;      // transition is complete
const float kFadePIScrollVelocity = 5;       // start countdown to fade position indicator
const float kCenteringVelocity = 150;        // threshold velocity for centering
const float kMaxZeroingPanVelocity = 10;     // max pan velocity to engage zeroing

// In seconds.
const float kImpulseTrackThreshold = 0.200;

// Margin sizes in pixels.
const float kRightMargin = 40;
const float kActivationMargin = 40;
const float kJumpScrollMargin = 40;
const float kJumpScrollTransitionStart = 20;
const float kJumpScrollTransitionEnd = 50;
const float kArcMargin = 90;
const float kEpsilon = 0.0001;

const float kTitleLeftMargin = 1;
const float kPositionIndicatorFontSize = 13;

const Vector4f kClearColorRgb(0, 0, 0, 0);

const float kOuterDividerIntensity = 0.8;
const float kInnerDividerIntensity = 0.7;
const float kInnerArcBandIntensity = 0.3;
const float kInnerArcTickMarkIntensity = 0.4;
const float kMaskGradientWidth = 150;

LazyStaticUIFont kInnerFont = { kDIN, kInnerFontSize };
LazyStaticUIFont kOuterFont = { kDIN, kOuterFontSize };
LazyStaticUIFont kPositionIndicatorFont = { kDIN, kPositionIndicatorFontSize };
LazyStaticRgbColor kLocationIndicatorBackgroundColor = { Vector4f(0.88, 0.302, 0.228, 0.8) };
LazyStaticRgbColor kLocationIndicatorBorderColor = { Vector4f(0.88, 0.302, 0.228, 1) };
LazyStaticRgbColor kLocationIndicatorBackgroundActiveColor = { Vector4f(0.910, 0.537, 0.227, 0.8) };
LazyStaticRgbColor kLocationIndicatorBorderActiveColor = { Vector4f(0.910, 0.537, 0.227, 1) };
LazyStaticRgbColor kPositionIndicatorColor = { Vector4f(1, 1, 1, 1) };
LazyStaticRgbColor kPositionIndicatorBackgroundColor = { Vector4f(0, 0, 0, 1.0) };
LazyStaticRgbColor kPositionIndicatorBorderColor = { Vector4f(0.5, 0.5, 0.5, 1.0) };
// TODO(spencer): might need to vary this for the inbox view.
LazyStaticRgbColor kScrollBarBackgroundColor = { Vector4f(0.3, 0.3, 0.3, 0.7) };
LazyStaticRgbColor kScrollBarBorderColor = { Vector4f(0.2, 0.2, 0.2, 0.8) };

typedef std::pair<float, float> Interval;
typedef std::pair<int, int> RowRange;

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
  WallTime begin_time;
  WallTime end_time;
  bool is_merged;
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
  return LinearInterp(val, min_val, max_val, min_t, max_t);
}

Vector4f Blend(const Vector4f& a, const Vector4f& b, float t) {
  return a + (b - a) * t;
}

// Compute the angle for an arc that intersects rect. There are likely a few
// assumptions below that "center.y() == CGRectGetMidY(f)". Don't assume this
// code is more general than its current usage.
double ArcAngle(const Vector2f& center, const double r, const CGRect& f) {
  double theta = 2 * kPi;

  {
    // Find the intersection of the circle with the top edge of the rectangle.
    const float y = f.origin.y - center.y();
    const float x = sqrt(r * r - y * y) + center.x();
    if (!std::isnan(x)) {
      const Vector2f d((Vector2f(x, 0) - center).normalize());
      const double t = 2 * acos(d.dot(Vector2f(-1, 0)));
      theta = std::min(theta, t);
    }
  }

  {
    // Find the intersection of the circle with the right edge of the
    // rectangle.
    const float x = f.origin.x + f.size.width - center.x();
    const float y = sqrt(r * r - x * x) + center.y();
    if (!std::isnan(y)) {
      const Vector2f d((Vector2f(f.size.width, y) - center).normalize());
      const double t = 2 * acos(d.dot(Vector2f(-1, 0)));
      theta = std::min(theta, t);
    }
  }

  return theta;
}

// Generate the vertices and triangles for a series of arc segments. Each
// generated vertex is passed to the add_vertex block which takes the vertex,
// the index of the radius on which the vertex was generated and a value "t" in
// the range [0,1] indicating where on that arc segment the vertex was
// generated (useful for calculating texture coordinates).
void GenerateArc(const CGPoint& center, bool degenerate,
                 const CGRect& bounds, const vector<double>& radius,
                 float t1, float t2,
                 void (^add_vertex)(const Vector4f& v, int i, float t),
                 void (^add_triangle)(int a, int b, int c)) {
  if (degenerate) {
    const float h = bounds.size.height;
    for (int i = 0; i < radius.size(); ++i) {
      const float x = center.x - radius[i];
      add_vertex(Vector4f(x, h * t2, 0, 1), i, 0);
      add_vertex(Vector4f(x, h * t1, 0, 1), i, 1);
    }
    for (int i = 1, offset = 0; i < radius.size(); ++i, offset += 2) {
      add_triangle(offset, offset + 1, offset + 2);
      add_triangle(offset + 1, offset + 2, offset + 3);
    }
  } else {
    vector<double> arc_angle(radius.size());
    for (int i = 0; i < arc_angle.size(); ++i) {
      arc_angle[i] = ArcAngle(center, radius[i], bounds);
    }
    if (radius[0] == 0 && center.x >= CGRectGetMaxX(bounds)) {
      // If the radius is 0 (this is a point) and the arc is offscreen,
      // ArcAngle() returns 2*kPi which is overkill.
      arc_angle[0] = arc_angle[1];
    }
    // Ensure that arc_angle[i] >= arc_angle[i + 1] so that each successive arc
    // is smaller than the last.
    for (int i = arc_angle.size() - 1; i > 0; --i) {
      arc_angle[i - 1] = std::max(arc_angle[i], arc_angle[i - 1]);
    }

    // We want to choose the step_angle such that the distance between the line
    // segment connecting 2 points on the arc and the arc itself is constrained
    // to some value (e.g. 1/10 of a pixel).
    const double max_step_angle =
        2 * acos((radius.back() - kArcError) / radius.back());
    const double step_angle =
        arc_angle[0] / ceil(arc_angle[0] / max_step_angle);

    Matrix4f m;
    m.translate(-center.x, -center.y, 0);
    m.rotate(step_angle, 0, 0, 1);
    m.translate(center.x, center.y, 0);

    // Add vertices for each arc radius and triangles stretching between the
    // radii.
    double prev_start_angle = 0;
    int prev_offset = 0;
    int cur_offset = 0;

    for (int i = 0; i < radius.size(); ++i) {
      const double theta =
          std::max(arc_angle[i], arc_angle[i + (i == 0 ? 1 : -1)]);
      const double start_angle =
          floor((kPi - theta / 2) / step_angle) * step_angle;
      const double end_angle =
          std::min(
              ceil((kPi + theta / 2) / step_angle) * step_angle,
              start_angle + 2 * kPi);
      const int steps = ceil((end_angle - start_angle) / step_angle);

      Vector4f v(center.x + radius[i] * cos(start_angle),
                 center.y + radius[i] * sin(start_angle),
                 0, 1);
      add_vertex(v, i, 0);

      for (int j = 0; j < steps; ++j) {
        v = m * v;
        add_vertex(v, i, (j + 1.0) / steps);
      }

      int next_offset = cur_offset + 1 + steps;
      if (i > 0) {
        const int offset = (start_angle - prev_start_angle) / step_angle;
        prev_offset += offset;

        for (int j = cur_offset + 1, k = prev_offset + 1;
             j < next_offset; ++j, ++k) {
          add_triangle(k - 1, j - 1, j);
          add_triangle(k - 1, k, j);
        }
      }

      prev_start_angle = start_angle;
      prev_offset = cur_offset;
      cur_offset = next_offset;
    }
  }
}

const float kAAFilterRadius = 1;

// TODO(pmattis): Move SolidShaderState and TextureShaderState to another file.
class SolidShaderState {
 public:
  SolidShaderState() {
    position_.reserve(10000);
    color_.reserve(10000);
    index_.reserve(10000);
  }

  int AddVertex(const Vector4f& p, const Vector4f& c) {
    const int index = position_.size();
    position_.push_back(p);
    color_.push_back(c);
    return index;
  }

  void AddTriangle(int a, int b, int c) {
    index_.push_back(a);
    index_.push_back(b);
    index_.push_back(c);
  }

  // Add an anti-aliased line.
  void AALine(const Vector2f& a, const Vector2f& b, float width,
              const Vector4f& color, const Vector4f& clear) {
    const Vector2f east = (b - a).normalize();
    // const Vector2f west = -east;
    const Vector2f north(-east.y(), east.x());
    const Vector2f south = -north;

    const float inner_width = (width - kAAFilterRadius) / 2;
    const int a_inner_s = AddVertex(a + south * inner_width, color);
    const int a_inner_n = AddVertex(a + north * inner_width, color);
    const int b_inner_s = AddVertex(b + south * inner_width, color);
    const int b_inner_n = AddVertex(b + north * inner_width, color);
    if (inner_width > 0) {
      // Only draw the inner triangles if they are not degenerate.
      AddTriangle(a_inner_s, a_inner_n, b_inner_s);
      AddTriangle(a_inner_n, b_inner_s, b_inner_n);
    }

    const float outer_width = inner_width + kAAFilterRadius;
    const int a_outer_s = AddVertex(a + south * outer_width, clear);
    const int a_outer_n = AddVertex(a + north * outer_width, clear);
    const int b_outer_s = AddVertex(b + south * outer_width, clear);
    const int b_outer_n = AddVertex(b + north * outer_width, clear);
    AddTriangle(a_inner_n, a_outer_n, b_inner_n);
    AddTriangle(a_outer_n, b_inner_n, b_outer_n);
    AddTriangle(a_inner_s, a_outer_s, b_inner_s);
    AddTriangle(a_outer_s, b_inner_s, b_outer_s);
  }

  // Add an anti-aliased triangle.
  void AATriangle(Vector2f a, Vector2f b, Vector2f c,
                  const Vector4f& color, const Vector4f& clear) {
    // Force the vertices of the triangle to be clockwise (or is it
    // counter-clockwise). Regardless, this ensures that we compute normals
    // below that point out from the triangle.
    if ((b - a).dot(c - a) < 0) {
      std::swap(b, c);
    }

    const int a_inner = AddVertex(a, color);
    const int b_inner = AddVertex(b, color);
    const int c_inner = AddVertex(c, color);

    const Vector2f ab = (a - b).normalize() * kAAFilterRadius;
    const Vector2f ab_n(-ab.y(), ab.x());
    const Vector2f bc = (b - c).normalize() * kAAFilterRadius;
    const Vector2f bc_n(-bc.y(), bc.x());
    const Vector2f ca = (c - a).normalize() * kAAFilterRadius;
    const Vector2f ca_n(-ca.y(), ca.x());

    const int a_outer =
        AddVertex(LineIntersection(a + ab_n, a + ab_n + ab,
                                   a + ca_n, a + ca_n + ca),
                  clear);
    const int b_outer =
        AddVertex(LineIntersection(b + ab_n, b + ab_n + ab,
                                   b + bc_n, b + bc_n + bc),
                  clear);
    const int c_outer =
        AddVertex(LineIntersection(c + ca_n, c + ca_n + ca,
                                   c + bc_n, c + bc_n + bc),
                  clear);

    AddTriangle(a_inner, b_inner, c_inner);
    AddTriangle(a_inner, a_outer, b_inner);
    AddTriangle(a_outer, b_inner, b_outer);
    AddTriangle(b_inner, b_outer, c_inner);
    AddTriangle(b_outer, c_inner, c_outer);
    AddTriangle(c_inner, c_outer, a_inner);
    AddTriangle(c_outer, a_inner, a_outer);
  }

  int size() const {
    return position_.size();
  }
  const Vector4f& position(int i) const {
    return position_[i];
  }
  const Vector4f& color(int i) const {
    return color_[i];
  }

  void Draw() {
    if (index_.empty()) {
      return;
    }

    // Set up the attributes for our shader program.
    glVertexAttribPointer(A_POSITION, 4, GL_FLOAT, GL_FALSE,
                          sizeof(position_[0]), &position_[0]);
    glEnableVertexAttribArray(A_POSITION);
    glVertexAttribPointer(A_COLOR, 4, GL_FLOAT, GL_FALSE,
                          sizeof(color_[0]), &color_[0]);
    glEnableVertexAttribArray(A_COLOR);
    // GL_CHECK_ERRORS();

    glDrawElements(GL_TRIANGLES, index_.size(),
                   GL_UNSIGNED_SHORT, &index_[0]);

    // Disable the attributes we set up.
    glDisableVertexAttribArray(A_POSITION);
    glDisableVertexAttribArray(A_COLOR);
    // GL_CHECK_ERRORS();
  }

 private:
  Vector2f LineIntersection(const Vector2f& a, const Vector2f& b,
                            const Vector2f& c, const Vector2f& d) {
    const Vector2f ba = b - a;
    const Vector2f dc = d - c;
    const Vector2f dc_perp(dc.y(), -dc.x());
    const float v = ba.dot(dc_perp);
    if (v == 0) {
      // No intersection, lines are parallel.
      return a;
    }
    const Vector2f ca = c - a;
    const float t = ca.dot(dc_perp) / v;
    return a + ba * t;
  }

 private:
  vector<Vector4f> position_;
  vector<Vector4f> color_;
  vector<unsigned short> index_;
};

class TextureShaderState {
 public:
  TextureShaderState() {
    position_.reserve(10000);
    tex_coord_.reserve(10000);
    index_.reserve(10000);
  }

  int AddVertex(const Vector4f& p, const Vector2f& t, float a = 1) {
    const int index = position_.size();
    position_.push_back(p);
    tex_coord_.push_back(t);
    alpha_.push_back(a);
    return index;
  }

  void AddTriangle(int a, int b, int c) {
    index_.push_back(a);
    index_.push_back(b);
    index_.push_back(c);
  }

  int size() const {
    return position_.size();
  }
  const Vector4f& position(int i) const {
    return position_[i];
  }
  const Vector2f& tex_coord(int i) const {
    return tex_coord_[i];
  }

  void Draw() {
    if (index_.empty()) {
      return;
    }

    // Set up the attributes for our shader program.
    glVertexAttribPointer(A_POSITION, 4, GL_FLOAT, GL_FALSE,
                          sizeof(position_[0]), &position_[0]);
    glEnableVertexAttribArray(A_POSITION);
    glVertexAttribPointer(A_TEX_COORD, 2, GL_FLOAT, GL_FALSE,
                          sizeof(tex_coord_[0]), &tex_coord_[0]);
    glEnableVertexAttribArray(A_TEX_COORD);
    glVertexAttribPointer(A_ALPHA, 1, GL_FLOAT, GL_FALSE,
                          sizeof(alpha_[0]), &alpha_[0]);
    glEnableVertexAttribArray(A_ALPHA);
    // GL_CHECK_ERRORS();

    glDrawElements(GL_TRIANGLES, index_.size(),
                   GL_UNSIGNED_SHORT, &index_[0]);

    // Disable the attributes we set up.
    glDisableVertexAttribArray(A_POSITION);
    glDisableVertexAttribArray(A_TEX_COORD);
    glDisableVertexAttribArray(A_ALPHA);
    // GL_CHECK_ERRORS();
  }

 private:
  vector<Vector4f> position_;
  vector<Vector2f> tex_coord_;
  vector<float> alpha_;
  vector<unsigned short> index_;
};

struct RowRankSort {
  const vector<float>& weights;

  RowRankSort(const vector<float>& w)
      : weights(w) {}

  bool operator()(const int a, const int b) const {
    return weights[a] > weights[b];
  }
};

struct RowDisplaySort {
  const vector<float>& weights;
  const ViewfinderLayerCache& cache;

  RowDisplaySort(const ViewfinderLayerCache& c, const vector<float>& w)
      : weights(w),
        cache(c) {}

  bool operator()(const int a, const int b) const {
    const ViewfinderLayerData* a_layer = FindPtrOrNull(cache, a);
    const ViewfinderLayerData* b_layer = FindPtrOrNull(cache, b);
    if (a_layer && !b_layer) {
      return true;
    } else if (!a_layer && b_layer) {
      return false;
    } else if (a_layer && b_layer) {
      if (a_layer->alpha > b_layer->alpha) {
        return true;
      } else if (a_layer->alpha < b_layer->alpha) {
        return false;
      }
    }
    return weights[a] > weights[b];
  }
};

}  // namespace

const float kViewfinderToolActivationSecs = 0.400;

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
  CGContextMoveToPoint(
      context, pos.x - (kLeftBorder - kRadius), pos.y - kYBorder);
  CGContextAddLineToPoint(
      context, pos.x + size.width, pos.y - kYBorder);
  CGContextAddLineToPoint(
      context, pos.x + size.width + kRightBorder, pos.y + size.height / 2);
  CGContextAddLineToPoint(
      context, pos.x + size.width, pos.y + kYBorder + size.height);
  CGContextAddLineToPoint(
      context, pos.x - (kLeftBorder - kRadius),
      pos.y + kYBorder + size.height);
  CGContextAddArcToPoint(
      context, pos.x - kLeftBorder, pos.y + kYBorder + size.height,
      pos.x - kLeftBorder, pos.y + (kYBorder - kRadius) + size.height,
      kRadius);
  CGContextAddLineToPoint(
      context, pos.x - kLeftBorder, pos.y - (kYBorder - kRadius));
  CGContextAddArcToPoint(
      context, pos.x - kLeftBorder, pos.y - kYBorder,
      pos.x - (kLeftBorder - kRadius), pos.y - kYBorder,
      kRadius);
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


// Computes a velocity using exponential decay to confine it to an
// arbitrarily sized window of time.
class DecayingVelocity {
 public:
  // max_velocity == 0 does not cap velocity.
  DecayingVelocity(float half_life, float min_velocity=0, float max_velocity=0)
      : half_life_(half_life),
        min_velocity_(min_velocity),
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
    MaybeUpdate(move, now);
  }

  // Direction must be normalized.
  bool IsSwipe(const Vector2f& direction, float velocity_threshold, float pct_total) {
    CHECK_EQ(direction.length(), 1.0);
    Vector2f normalized(velocity_);
    normalized.normalize();
    return (normalized.dot(direction) >= pct_total &&
            velocity_.dot(direction) >= velocity_threshold);
  }

  const Vector2f& velocity() {
    MaybeUpdate(Vector2f(0, 0), WallTime_Now());
    return velocity_;
  }
  float magnitude() {
    MaybeUpdate(Vector2f(0, 0), WallTime_Now());
    return velocity_.length();
  }
  float operator()(int i) {
    MaybeUpdate(Vector2f(0, 0), WallTime_Now());
    return velocity_(i);
  }

  static const float kMinUpdateInterval;
  static const Vector2f UP;
  static const Vector2f DOWN;
  static const Vector2f LEFT;
  static const Vector2f RIGHT;

 private:
  void MaybeUpdate(const Vector2f& move, WallTime now) {
    if ((now - last_move_time_) < kMinUpdateInterval) {
      return;
    }
    // Limit the decay time to 1/100th of a second.
    const float decay_time = now - last_move_time_;
    const float decay = Decay(decay_time, half_life_);
    const float instantaneous_velocity = move.length() / decay_time;
    float scale = 1;
    if (max_velocity_ > 0 && instantaneous_velocity > max_velocity_) {
      scale = max_velocity_ / instantaneous_velocity;
    } else if (min_velocity_ > 0 && instantaneous_velocity < min_velocity_) {
      scale = 0;
    }
    move_duration_ = move_duration_ * decay + decay_time;
    last_move_time_ = now;
    move_total_ = move_total_ * decay + move * scale;
    velocity_ = move_total_ / move_duration_;
  }

  float Decay(float time, float half_life) {
    return exp(-log(2.0) * time / half_life);
  }

  const float half_life_;
  const float min_velocity_;
  const float max_velocity_;
  float move_duration_;
  WallTime last_move_time_;
  Vector2f move_total_;
  Vector2f velocity_;
};

const float DecayingVelocity::kMinUpdateInterval = 0.01;
const Vector2f DecayingVelocity::UP = Vector2f(0, -1);
const Vector2f DecayingVelocity::DOWN = Vector2f(0, 1);
const Vector2f DecayingVelocity::LEFT = Vector2f(-1, 0);
const Vector2f DecayingVelocity::RIGHT = Vector2f(1, 0);

@interface DialUIPanGestureRecognizer : UIPanGestureRecognizer {
 @private
  bool touches_can_begin_;
}

@property (nonatomic) bool touchesCanBegin;

@end  // DialUIPanGestureRecognizer

@implementation DialUIPanGestureRecognizer

@synthesize touchesCanBegin = touches_can_begin_;

- (void)touchesBegan:(NSSet*)touches
           withEvent:(UIEvent*)event {
  [super touchesBegan:touches withEvent:event];
  if (touches_can_begin_) {
    self.state = UIGestureRecognizerStateBegan;
  }
}

@end  // DialUIPanGestureRecognizer


@implementation ViewfinderTool

- (id)initWithEnv:(id<ViewfinderToolEnv>)env appState:(UIAppState*)state {
  if (self = [super init]) {
    env_ = env;
    state_ = state;
    pct_active_ = 0.0;
    pct_quiescent_ = 0.0;
    pct_scrolling_ = 0.0;
    mode_ = VF_INACTIVE;
    needs_finish_ = false;
    target_index_ = -1;
    tracking_model_.reset(new PhysicsModel);
    location_model_.reset(new PhysicsModel);
    scroll_velocity_.reset(new DecayingVelocity(kScrollVelocityHalfLife));
    self.autoresizesSubviews = YES;
    self.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;
    self.backgroundColor = [UIColor clearColor];

    // Decrease the {contents,rasterization}Scale so that the backing bitmap
    // for the layer associated with the viewfinder tool is very small and thus
    // consumes very few resources.
    self.layer.contentsScale = 1 / 100.0;
    self.layer.rasterizationScale = 1 / 100.0;

    pan_recognizer_ =
        [[DialUIPanGestureRecognizer alloc]
          initWithTarget:self action:@selector(handlePan:)];
    pan_recognizer_.cancelsTouchesInView = NO;
    [pan_recognizer_ setDelegate:self];

    activation_recognizer_ =
        [[UILongPressGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleActivation:)];
    activation_recognizer_.cancelsTouchesInView = YES;
    activation_recognizer_.delaysTouchesBegan = YES;
    activation_recognizer_.minimumPressDuration = kViewfinderToolActivationSecs;
    [activation_recognizer_ setDelegate:self];
    [activation_recognizer_ setNumberOfTapsRequired:0];

    long_press_recognizer_ =
        [[UILongPressGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleLongPress:)];
    long_press_recognizer_.cancelsTouchesInView = NO;
    [long_press_recognizer_ setDelegate:self];
    [long_press_recognizer_ setNumberOfTapsRequired:0];

    single_tap_recognizer_ =
        [[UITapGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSingleTap:)];
    single_tap_recognizer_.cancelsTouchesInView = NO;
    [single_tap_recognizer_ setDelegate:self];
    [single_tap_recognizer_ setNumberOfTapsRequired:1];
    // Don't recognize single taps unless both long press recognizers fail.
    [single_tap_recognizer_
      requireGestureRecognizerToFail:pan_recognizer_];
    [single_tap_recognizer_
      requireGestureRecognizerToFail:activation_recognizer_];
    [single_tap_recognizer_
      requireGestureRecognizerToFail:long_press_recognizer_];

    pinch_recognizer_ =
        [[UIPinchGestureRecognizer alloc]
          initWithTarget:self action:@selector(handlePinch:)];
    [pinch_recognizer_ setDelegate:self];
    pinch_recognizer_.cancelsTouchesInView = NO;
    pinch_recognizer_.enabled = NO;

    left_swipe_recognizer_ =
        [[UISwipeGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSwipeLeft:)];
    [left_swipe_recognizer_ setDelegate:self];
    left_swipe_recognizer_.cancelsTouchesInView = NO;
    left_swipe_recognizer_.direction = UISwipeGestureRecognizerDirectionLeft;

    right_swipe_recognizer_ =
        [[UISwipeGestureRecognizer alloc]
          initWithTarget:self action:@selector(handleSwipeRight:)];
    [right_swipe_recognizer_ setDelegate:self];
    right_swipe_recognizer_.cancelsTouchesInView = NO;
    right_swipe_recognizer_.direction = UISwipeGestureRecognizerDirectionRight;
  }
  return self;
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];
  [self computeConstants];

  if (!position_indicator_) {
    position_indicator_ = [PositionIndicatorLayer new];
    [self.layer addSublayer:position_indicator_];
    [self initScrollBar];
    [self initLocationIndicator];
  }

  // Update current position and track scrolling velocity. We update
  // cur_pos_ here because the summary or day views may be scrolled
  // independently of the viewfinder UI.
  const float new_pos = self.frame.origin.y + cur_loc_.y;
  const float delta_pos = new_pos - cur_pos_;
  cur_pos_ = new_pos;

  if (scroll_velocity_.get()) {
    if ([self doesModeTrackScrollVelocity] &&
        self.frame.origin.y >= 0 &&
        self.frame.origin.y < max_tracking_pos_) {
      scroll_velocity_->Adjust(Vector2f(0, delta_pos));
      if (pct_active_ == 0.0) {
        [self setViewfinderState:GESTURE_NONE touch_loc:touch_loc_];
        [self redraw];
        return;
      }
    } else {
      scroll_velocity_->Adjust(Vector2f(0, 0));
    }
  }

  // If the mode of the viewfinder is updating the parent view's
  // scroll offset (position), then we specifically redraw the
  // viewfinder's contents when our frame is set.
  if ([self doesModeUpdatePosition]) {
    [self redraw];
  }
}

- (void)addGestureRecognizers:(UIView*)event_view {
  [event_view addGestureRecognizer:pan_recognizer_];
  [event_view addGestureRecognizer:activation_recognizer_];
  [event_view addGestureRecognizer:long_press_recognizer_];
  [event_view addGestureRecognizer:single_tap_recognizer_];
  [event_view addGestureRecognizer:pinch_recognizer_];
  [event_view addGestureRecognizer:left_swipe_recognizer_];
  [event_view addGestureRecognizer:right_swipe_recognizer_];
}

- (void)removeGestureRecognizers:(UIView*)event_view {
  // It is important to disable the gesture recognizer before removing it from its view.
  // The recognizer may have queued some events to its delegate, and will crash if the
  // delegate is deallocated before those messages are delivered.
  // (Setting the delegate to null is an additional precaution; setting enabled to false
  // appears to be sufficient)
  pan_recognizer_.enabled = NO;
  pan_recognizer_.delegate = NULL;
  [event_view removeGestureRecognizer:pan_recognizer_];
  activation_recognizer_.enabled = NO;
  activation_recognizer_.delegate = NULL;
  [event_view removeGestureRecognizer:activation_recognizer_];
  long_press_recognizer_.enabled = NO;
  long_press_recognizer_.delegate = NULL;
  [event_view removeGestureRecognizer:long_press_recognizer_];
  single_tap_recognizer_.enabled = NO;
  single_tap_recognizer_.delegate = NULL;
  [event_view removeGestureRecognizer:single_tap_recognizer_];
  pinch_recognizer_.enabled = NO;
  pinch_recognizer_.delegate = NULL;
  [event_view removeGestureRecognizer:pinch_recognizer_];
  left_swipe_recognizer_.enabled = NO;
  left_swipe_recognizer_.delegate = NULL;
  [event_view removeGestureRecognizer:left_swipe_recognizer_];
  right_swipe_recognizer_.enabled = NO;
  right_swipe_recognizer_.delegate = NULL;
  [event_view removeGestureRecognizer:right_swipe_recognizer_];
}

- (void)initScrollBar {
  scroll_bar_ = [CALayer new];
  scroll_bar_.backgroundColor = kScrollBarBackgroundColor;
  scroll_bar_.borderWidth = 1;
  scroll_bar_.borderColor = kScrollBarBorderColor;
  scroll_bar_.cornerRadius = kScrollBarWidth / 2;
  scroll_bar_.hidden = YES;
  [self.layer insertSublayer:scroll_bar_ below:position_indicator_];
}

- (void)initLocationIndicator {
  location_indicator_ = [CAShapeLayer new];
  location_indicator_.fillColor = kLocationIndicatorBackgroundColor;
  location_indicator_.strokeColor = kLocationIndicatorBorderColor;
  location_indicator_.lineJoin = kCALineJoinRound;
  location_indicator_.lineWidth = 1;
  location_indicator_.hidden = YES;
  [self.layer addSublayer:location_indicator_];

  const CGPoint kOuterStartPt = CGPointMake(0, 0);
  const CGPoint kOuterBezierPts[] = {
    CGPointMake(53, 0), CGPointMake(53, 0), CGPointMake(53, 0),
    CGPointMake(67, 8), CGPointMake(67, 8), CGPointMake(67, 8),
    CGPointMake(53, 16), CGPointMake(53, 16), CGPointMake(53, 16),
    CGPointMake(0, 16), CGPointMake(0, 16), CGPointMake(0, 16),
  };
  const CGPoint kInnerStartPt = CGPointMake(3.82, 4);
  const CGPoint kInnerBezierPts[] = {
    CGPointMake(1.27, 7.45), CGPointMake(1.45, 7.45), CGPointMake(3.82, 11.82),
    CGPointMake(3.82, 11.82), CGPointMake(51.64, 11.82), CGPointMake(51.82, 11.82),
    CGPointMake(54.55, 9.64), CGPointMake(54.73, 6.18), CGPointMake(51.82, 4),
    CGPointMake(51.64, 4), CGPointMake(3.45, 4), CGPointMake(3.82, 4),
  };

  ScopedRef<CGMutablePathRef> path(CGPathCreateMutable());

  // Start with the outer path.
  CGPathMoveToPoint(path, NULL, kOuterStartPt.x, kOuterStartPt.y);
  for (int j = 0; j < ARRAYSIZE(kOuterBezierPts); j += 3) {
    CGPathAddCurveToPoint(path, &CGAffineTransformIdentity,
                          kOuterBezierPts[j + 0].x, kOuterBezierPts[j + 0].y,
                          kOuterBezierPts[j + 1].x, kOuterBezierPts[j + 1].y,
                          kOuterBezierPts[j + 2].x, kOuterBezierPts[j + 2].y);
  }
  CGPathCloseSubpath(path);

  CGPathMoveToPoint(path, NULL, kInnerStartPt.x, kInnerStartPt.y);
  for (int j = 0; j < ARRAYSIZE(kInnerBezierPts); j += 3) {
    CGPathAddCurveToPoint(path, &CGAffineTransformIdentity,
                          kInnerBezierPts[j + 0].x, kInnerBezierPts[j + 0].y,
                          kInnerBezierPts[j + 1].x, kInnerBezierPts[j + 1].y,
                          kInnerBezierPts[j + 2].x, kInnerBezierPts[j + 2].y);
  }
  CGPathCloseSubpath(path);

  location_indicator_.path = path;
}

- (void)handlePan:(UIPanGestureRecognizer*)recognizer {
  const CGPoint p = [recognizer locationInView:self];

  switch (recognizer.state) {
    case UIGestureRecognizerStateBegan:
      pan_velocity_ = CGPointMake(0, 0);
      [self setViewfinderState:GESTURE_TRACK touch_loc:p];
      break;

    case UIGestureRecognizerStateChanged: {
      pan_velocity_ = [recognizer velocityInView:self];
      Vector2f delta_loc = Vector2f(cur_loc_) - Vector2f(touch_loc_);
      Vector2f delta_touch = Vector2f(p) - Vector2f(touch_loc_);
      [self setViewfinderState:GESTURE_TRACK touch_loc:p];

      // Compute the delta in current scroll position based on movement.
      if ([self isModeTracking]) {
        if (shape_ == SHAPE_DIAL) {
          if (!elastic_) {
            delta_touch(0) = 0;
          }
        } else if (shape_ == SHAPE_TIMELINE || shape_ == SHAPE_TIMEARC) {
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

        const CGPoint new_loc = (Vector2f(cur_loc_) + delta_touch).ToCGPoint();
        [self setCurrentLocation:new_loc integrate:true];
        display_link_.paused = NO;
      }
      break;
    }

    case UIGestureRecognizerStateEnded:
    case UIGestureRecognizerStateCancelled:
      tracking_ = false;
      [self setViewfinderState:GESTURE_RELEASE touch_loc:p];
      break;
    default:
      break;
  }
}

- (void)handleLongPress:(UILongPressGestureRecognizer*)recognizer {
  const CGPoint p = [recognizer locationInView:self];
  switch (recognizer.state) {
    case UIGestureRecognizerStateBegan:
      [self setViewfinderState:GESTURE_LONG_PRESS touch_loc:p];
      break;
    case UIGestureRecognizerStateEnded:
    case UIGestureRecognizerStateCancelled:
      [self setViewfinderState:GESTURE_RELEASE touch_loc:p];
      break;
    default:
      break;
  }
}

- (void)handleActivation:(UILongPressGestureRecognizer*)recognizer {
  const CGPoint p = [recognizer locationInView:self];
  switch (recognizer.state) {
    case UIGestureRecognizerStateBegan:
      [self setViewfinderState:GESTURE_ACTIVATION touch_loc:p];
      break;
    case UIGestureRecognizerStateEnded:
    case UIGestureRecognizerStateCancelled:
      [self setViewfinderState:GESTURE_RELEASE touch_loc:p];
      break;
    default:
      break;
  }
}

- (void)handleSingleTap:(UITapGestureRecognizer*)recognizer {
  if (recognizer.state != UIGestureRecognizerStateEnded) {
    return;
  }
  if (![self doesModePassGesturesToParent]) {
    const CGPoint p = [recognizer locationInView:self];
    [self setViewfinderState:GESTURE_SINGLE_TAP touch_loc:p];
  }
}

- (void)handlePinch:(UIPinchGestureRecognizer*)recognizer {
  const CGPoint p = [recognizer locationInView:self];
  pinch_scale_ = ClampValue(recognizer.scale, kPinchMinScale, kPinchMaxScale);
  switch (recognizer.state) {
    case UIGestureRecognizerStateBegan:
      [self setViewfinderState:GESTURE_PINCH touch_loc:p];
      break;
    case UIGestureRecognizerStateChanged:
      [self setViewfinderState:GESTURE_TRACK touch_loc:p];
      float new_x;
      if (pinch_scale_ > 1.0) {
        new_x = pinch_start_x_ + (0 - pinch_start_x_) *
                ((pinch_scale_ - 1) / (kPinchMaxScale - 1));
      } else {
        new_x = pinch_start_x_ + (self.trackingWidth - pinch_start_x_) *
                ((1 - pinch_scale_) / (1 - kPinchMinScale));
      }
      [self setCurrentLocation:CGPointMake(new_x, cur_loc_.y) integrate:false];
      display_link_.paused = NO;
      break;
    case UIGestureRecognizerStateEnded:
    case UIGestureRecognizerStateCancelled:
      [self setViewfinderState:GESTURE_RELEASE touch_loc:p];
      break;
    default:
      break;
  }
}

- (void)handleSwipeLeft:(UISwipeGestureRecognizer*)recognizer {
  const CGPoint p = [recognizer locationInView:self];
  if (![self doesModePassGesturesToParent]) {
    [self setViewfinderState:GESTURE_SWIPE_LEFT touch_loc:p];
  }
}

- (void)handleSwipeRight:(UISwipeGestureRecognizer*)recognizer {
  const CGPoint p = [recognizer locationInView:self];
  if (![self doesModePassGesturesToParent]) {
    [self setViewfinderState:GESTURE_SWIPE_RIGHT touch_loc:p];
  }
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

- (float)integral:(const CGPoint&)from_loc
                y:(float)y
                m:(float)m
              log:(bool)log {
#if defined(LINEAR_INTEGRATION)
  const float a = roc_min_;
  const float b = roc_slope_;
  return 0.5 * y * (2 * a + b * (2 * from_loc.x + (y - 2 * from_loc.y) / m));
#elif defined(EXPONENTIAL_INTEGRATION)
  CHECK_NE(m, 0);
  const float x0 = from_loc.x;
  const float y0 = from_loc.y;
  const float delta_y = m * x0 + y - y0;
  const float pow_inv_change = pow(delta_y / m, alpha_);
  float integral;
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

- (float)delta:(const CGPoint&)to_loc
       fromLoc:(const CGPoint&)from_loc
           log:(bool)log {
  const CGPoint tx_to_loc = [self transformPoint:to_loc];
  const CGPoint tx_from_loc = [self transformPoint:from_loc];
  const CGPoint delta_loc = CGPointMake(tx_to_loc.x - tx_from_loc.x,
                                        tx_to_loc.y - tx_from_loc.y);
  if (fabs(delta_loc.y) < kEpsilon) {
    // No integration necessary
    return 0;
  } else if (fabs(delta_loc.x) < kEpsilon) {
    // Integration is simply the rate of change * delta y.
    float roc = [self rateOfChange:tx_to_loc.x];
    if (std::isnan(roc)) {
      LOG("should never get NaN for rate of change: %s", tx_to_loc);
      roc = roc_min_;
    }
    return (shape_ == SHAPE_DIAL) ? -roc * delta_loc.y : roc * delta_loc.y;
  }

  const float m = delta_loc.y / delta_loc.x;
  const float to_val = [self integral:tx_from_loc y:tx_to_loc.y m:m log:log];
  const float from_val = [self integral:tx_from_loc y:tx_from_loc.y m:m log:log];
  return (shape_ == SHAPE_DIAL) ? from_val - to_val : to_val - from_val;
}

// Compute the delta Y necessary to move from "from_loc" to "to_loc"
// such that position integrates from cur_pos to new_pos. The
// y-coordinate of "to_loc" is ignored.
- (float)deltaY:(float)to_pos
        fromPos:(float)from_pos
          toLoc:(const CGPoint&)to_loc
        fromLoc:(const CGPoint&)from_loc {
#if defined(LINEAR_INTEGRATION)
  CHECK(false) << "delta Y for linear integration still needs to be worked out";
#elif defined(EXPONENTIAL_INTEGRATION)
  const CGPoint tx_to_loc = [self transformPoint:to_loc];
  const CGPoint tx_from_loc = [self transformPoint:from_loc];
  const float dx = tx_to_loc.x - tx_from_loc.x;

  if (fabs(dx) < kEpsilon) {
    return (to_pos - from_pos) / [self rateOfChange:tx_from_loc.x];
  }

  const float roc_to = [self rateOfChange:tx_to_loc.x] - roc_min_;
  const float roc_from = [self rateOfChange:tx_from_loc.x] - roc_min_;

  return (to_pos - from_pos) /
      (roc_min_ + ((roc_to * tx_to_loc.x - roc_from * tx_from_loc.x) /
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

// Finds the book-ending indexes which bracket the specified interval.
- (Indexes)indexesForInterval:(const Interval&)interval {
  std::vector<float>::const_iterator start_iter = std::lower_bound(
      positions_.begin(), positions_.end(), interval.first);
  int start_index = 0;
  if (start_iter != positions_.begin()) {
    start_iter--;
    start_index = start_iter - positions_.begin();
  }

  std::vector<float>::const_iterator end_iter = std::lower_bound(
      positions_.begin(), positions_.end(), interval.second);
  int end_index = end_iter - positions_.begin();

  return Indexes(start_index, end_index, 0);
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
  if (cur_timestamp >= t) {
    return positions_[index];
  }
  // Extrapolate based on the beginning and ending timestamps and positions.
  if (t <= timestamps_.front()) {
    return min_pos_ - (timestamps_.front() - t) *
        (max_pos_ - min_pos_) / (max_time_ - min_time_);
  } else {
    CHECK_GE(t, timestamps_.back());
    return max_pos_ + (t - timestamps_.back()) *
        (max_pos_ - min_pos_) / (max_time_ - min_time_);
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
  if (cur_timestamp <= t) {
    return positions_[index];
  }
  // Extrapolate based on the beginning and ending timestamps and positions.
  if (t <= timestamps_.back()) {
    return max_pos_ + (timestamps_.back() - t) *
        (max_pos_ - min_pos_) / (max_time_ - min_time_);
  } else {
    CHECK_GE(t, timestamps_.front());
    return min_pos_ - (t - timestamps_.front()) *
        (max_pos_ - min_pos_) / (max_time_ - min_time_);
  }
}

- (float)positionForTime:(WallTime)t {
  if (env_.viewfinderTimeAscending) {
    return [self positionForTimeAscending:t];
  }
  return [self positionForTimeDescending:t];
}

- (float)positionForAngle:(double)radians
                   circle:(const Circle&)c
                  withPos:(float)pos
                  withLoc:(const CGPoint&)loc {
  const CGPoint arc_coords = c.arc_coords(radians);
  return pos + [self delta:arc_coords fromLoc:loc log:false];
}

- (double)angleForPosition:(double)p
                    circle:(const Circle&)c
                   withPos:(float)pos
                   withLoc:(const CGPoint&)loc {
  if (shape_ == SHAPE_DIAL) {
    // What we're doing here is mapping position "p" to an angle. The
    // reference position, "pos", is always at kPi radians. It
    // corresponds to the red dial indicator which remains stable at the
    // left side of the dial.
    //
    // The thing to keep in mind about the underlying model is that if a
    // label starts at the top of the dial, if we rotate the dial by
    // exactly c.theta radians (the angle of the visible arc), that
    // label will end at the bottom of the dial. Although you can spin
    // the dial with a direct vertical pan and your finger won't be
    // forced to follow a radial path, we imagine that any y-axis
    // panning acts tangentially at the red dial indicator. Therefore, a
    // full vertical pan changes position by ROC * height. Since it also
    // changes the angle by c.theta, we can assign [c.theta / (ROC *
    // height)] radians to each positional unit. So if [p == pos + 1],
    // then p is at angle [kPi + c.theta / (ROC * height)].

    const CGPoint tx_loc = [self transformPoint:loc];
    const float roc = [self rateOfChange:tx_loc.x];
    const double radian_units = c.theta / (roc * self.trackingHeight);
    const double center_y = self.bounds.size.height / 2;
    return kPi - radian_units * (p - pos + (cur_loc_.y - center_y));
  } else if (shape_ == SHAPE_TIMELINE ||
             (shape_ == SHAPE_TIMEARC && c.degenerate)) {
    // For shape TIMELINE, we have a degenerate circle. We map the
    // entire position range (min_pos_ => max_pos_) onto c.theta and use
    // the offset from center to compute angle. We use deltaY() to
    // determine the imputed y coordinate on the timeline (at x=0) which
    // would take us from pos to p.
    CHECK(c.degenerate);
    const float x = c.center.x - c.radius;
    const float y = loc.y + [self deltaY:p fromPos:pos toLoc:CGPointMake(x, 0) fromLoc:loc];
    return kPi - c.theta * ((y - self.trackingHeight / 2) / self.trackingHeight);
  } else {
    CHECK_EQ(shape_, SHAPE_TIMEARC);
    // Binary search for an angle on the arc to which the delta position
    // would yield "p" starting at the current location "loc" and current
    // position "pos".

    double s = kPi / 2;
    double e = s + kPi;
    while (fabs(e - s) * c.radius > 0.5) {
      const double m = s + (e - s) / 2;
      const float p_m = [self positionForAngle:m circle:c withPos:pos withLoc:loc];
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
}

- (CGPoint)coordsForPosition:(double)p
                      circle:(const Circle&)c
                     withPos:(float)pos
                     withLoc:(const CGPoint&)loc {
  if (shape_ == SHAPE_TIMELINE ||
      (shape_ == SHAPE_TIMEARC && c.degenerate)) {
    const float x = int(c.center.x - c.radius);
    return CGPointMake(x, cur_loc_.y + [self deltaY:p
                                            fromPos:pos
                                              toLoc:CGPointMake(x, 0)
                                            fromLoc:loc]);
  } else {
    return c.arc_coords([self angleForPosition:p circle:c withPos:pos withLoc:loc]);
  }
}

// Solve for the delta in the current location's y coordinate which if
// moved to directly from the current x coordinate, will set cur_pos_
// to the specified position 'p'.
- (float)deltaYForPosition:(float)p
                   withPos:(float)pos
                   withLoc:(CGPoint)loc {
  const CGPoint tx_loc = [self transformPoint:loc];
  float roc;
  roc = [self rateOfChange:tx_loc.x];
  if (shape_ == SHAPE_DIAL) {
    roc = -roc;
  }
  return (p - pos) / roc;
}

- (int)indexAtLocation:(CGPoint)pt
            arc_coords:(CGPoint*)arc_coords {
  if (visible_.empty()) {
    return -1;
  }
  // Locates the index of the row closest to the specified point.
  // Returns -1 if no index matches.
  const float kSearchTolerance = 40;
  const float search_y = pt.y - UIStyle::kTitleFont.height() / 2;
  const VisibleRow* vg;

  std::map<float,VisibleRow>::const_iterator iter = visible_.lower_bound(search_y);
  if (iter == visible_.end()) {
    vg = &visible_.rbegin()->second;
  } else {
    if (iter != visible_.begin()) {
      const float below_diff = fabs((iter->second.pt.y - UIStyle::kTitleFont.height() / 2) - pt.y);
      std::map<float,VisibleRow>::const_iterator prev_iter = iter;
      iter--;
      const float above_diff = fabs((iter->second.pt.y - UIStyle::kTitleFont.height() / 2) - pt.y);
      if (below_diff < above_diff) {
        iter = prev_iter;
      }
    }
    vg = &iter->second;
  }

  if (vg != NULL && layer_cache_.find(vg->index) != layer_cache_.end()) {
    CompositeTextLayer* layer = layer_cache_[vg->index].layer;
    // Verify the coordinates are close enough to the label.
    const float max_search_x = pt.x + kSearchTolerance;
    const float min_search_x = pt.x - kSearchTolerance;
    const float max_search_y = pt.y + kSearchTolerance;
    const float min_search_y = pt.y - kSearchTolerance;
    if (max_search_x >= layer.frame.origin.x &&
        min_search_x <= (layer.frame.origin.x + layer.textWidth) &&
        max_search_y >= layer.frame.origin.y &&
        min_search_y <= (layer.frame.origin.y + layer.frame.size.height)) {
      *arc_coords = vg->pt;
      return vg->index;
    }
  }
  return -1;
}

- (Interval)getArcInterval:(float)pos
                   withLoc:(const CGPoint&)loc {
  // Computes the interval from the start to the end of the arc.
  if (shape_ == SHAPE_TIMELINE) {
    return Interval(pos - loc.y + [self delta:CGPointMake(0, 0) fromLoc:loc log:false],
                    pos + (self.trackingHeight - loc.y) +
                    [self delta:CGPointMake(0, self.trackingHeight) fromLoc:loc log:false]);
  } else if (shape_ == SHAPE_DIAL) {
    return [self getInterval:loc];
  } else {
    CHECK_EQ(shape_, SHAPE_TIMEARC);
    const Circle c = [self getCircle:loc];
    return Interval([self positionForAngle:(kPi + c.theta / 2)
                                    circle:c
                                   withPos:pos
                                   withLoc:loc],
                    [self positionForAngle:(kPi - c.theta / 2)
                                    circle:c
                                   withPos:pos
                                   withLoc:loc]);
  }
}

- (Interval)getInterval:(const CGPoint&)loc {
  const CGPoint tx_loc = [self transformPoint:loc];
  const float interval = self.trackingHeight * (1 + [self rateOfChange:tx_loc.x]);
  const float y_ratio = tx_loc.y / self.trackingHeight;
  return Interval(cur_pos_ - y_ratio * interval,
                  cur_pos_ + (1.0 - y_ratio) * interval);
}

- (float)inactiveWidth {
  return kArcWidth;
}

- (float)rowHeaderHeight {
  return UIStyle::kTitleFont.height() + UIStyle::kSubtitleFont.height();
}

- (float)leftActivationMargin {
  return kActivationMargin;
}

- (float)rightActivationMargin {
  return kJumpScrollMargin;
}

- (ViewfinderMode)mode {
  return mode_;
}

- (bool)active {
  return !(mode_ == VF_INACTIVE ||
           mode_ == VF_SCROLLING ||
           mode_ == VF_STOWING);
}

- (CALayer*)positionIndicator {
  return position_indicator_;
}

// Sets the current position. If the mode enforces bounds constraints,
// and those constraints are exceeded, returns true.
- (bool)updateCurrentPosition:(float)new_pos {
  if (std::isnan(new_pos)) {
    LOG("update current position supplied with NaN; cur_pos_: %f, "
        "cur_loc_: %s, min_tracking_pos_: %f, max_tracking_pos_: %f, # positions: %d",
        cur_pos_, cur_loc_, min_tracking_pos_, max_tracking_pos_, positions_.size());
    return false;
  }
  if ([self doesModeTrackScrollVelocity]) {
    scroll_velocity_->Adjust(Vector2f(0, new_pos - cur_pos_));
  }

  float scroll_pos = new_pos - cur_loc_.y;
  if (shape_ == SHAPE_DIAL && mode_ == VF_TRACKING) {
    const float y_ratio = touch_loc_.y / self.bounds.size.height;
    scroll_pos = std::max<float>(
        scroll_pos, min_tracking_pos_ - y_ratio * self.bounds.size.height / 2);
    scroll_pos = std::min<float>(
        scroll_pos, max_tracking_pos_ + (1 - y_ratio) * self.bounds.size.height / 2);
  } else if ([self doesModeBoundPosition]) {
    scroll_pos = std::max<float>(scroll_pos, min_tracking_pos_);
    scroll_pos = std::min<float>(scroll_pos, max_tracking_pos_);
  }
  //LOG("bounding: %d from %f to %f", [self doesModeBoundPosition], new_pos, bounded_pos);
  cur_pos_ = scroll_pos + cur_loc_.y;
  // The scroll position of the parent is set during rendering.
  return scroll_pos != new_pos;
}

- (void)setTargetIndex:(int)index {
  // Add/remove boosted weight from new and old targets respectively.
  if (target_index_ >= 0 && target_index_ < weights_.size()) {
    weights_[target_index_] -= kTargetWeightBoost;
  }
  if (index >= 0 && index < weights_.size()) {
    weights_[index] += kTargetWeightBoost;
    target_index_ = index;
  } else {
    target_index_ = -1;
  }
}

- (WallTime)currentOuterTime:(WallTime)t {
  return GetCurrentOuterTime(time_scale_, t);
}

- (WallTime)currentInnerTime:(WallTime)t {
  return GetCurrentInnerTime(time_scale_, t);
}

- (WallTime)nextOuterTime:(WallTime)t {
  return GetNextOuterTime(time_scale_, t);
}

- (WallTime)nextInnerTime:(WallTime)t {
  return GetNextInnerTime(time_scale_, t);
}

- (float)trackingWidth {
  return self.bounds.size.width - kRightMargin;
}

- (float)trackingHeight {
  return self.bounds.size.height;
}

- (Circle)getCircleFromXCoord:(double)x {
  x = std::max<double>(x, 0.1);
  bool degenerate = (x == 0.1);

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

- (Circle)getCircle:(const CGPoint&)p {
  // Gets the circle (center, radius) that goes through the two endpoints of
  // the current x coordinate (p.x) and just touches the left edge of the
  // screen. Also computes the degrees (in radians) of the small arc through
  // the three points.
  double x = shape_ == SHAPE_TIMELINE ? 0 : p.x;
  x = ClampValue(x - kArcMargin, 0, self.trackingWidth);
  return [self getCircleFromXCoord:x];
}

- (void)drawRowText {
  if (mode_ == VF_SCROLLING) {
    // Don't draw row text in modes where the view is managing the
    // text.  We allow requests to draw in mode VF_INACTIVE in order
    // to undraw extant labels from the dial when it's closed without
    // a "stowing" animation.
    return;
  }

  const float row_alpha = 1.0;
  const Circle& c = circle_;

  // Start the transition from full to short title at pct_active_ == 0 and
  // end it at 1.
  const Interval interval = [self getInterval:cur_loc_];
  const float interval_size = interval.second - interval.first;
  /*
    // TODO(spencer): title transition should be done as a function of crowding.
  float title_transition = 0;
  if (pct_active_ > 0) {
    title_transition =
        Interp((interval.second - interval.first) / max_row_height_,
               max_rows / 2, max_rows, 0, 1);
  }
  */
  float title_transition =
      Interp(pct_active_, 0, 1, 0, 1);

  // Disallow partially transitioned titles unless actively tracking.
  if (![self canModeShowLabelTransitions]) {
    title_transition = int(title_transition + 0.5);
  }

  // TODO(spencer): Use these to possibly decide whether to show a country flag.
  //const float kMinDistance = 150 * 1000;  // In m
  //const float kMaxDistance = 5000 * 1000;  // In m
  const float kMinIndex = weights_.size() * 0.05;
  const float kMaxIndex = weights_.size() * 0.33;

  const float kRowDisplayAlphaThreshold = 0.10;

  // Constants determining how labels fade.
  const float kFadeStart = UIStyle::kTitleFont.height() * 2.5;
  const float kFadeEnd = UIStyle::kTitleFont.height() * 1.25;
  // How much to scale rows at the periphery.
  //const float kMaxScale = 1.0;//0.8;

  // Make a copy of the existing layers. Every layer that is still in use will
  // get removed from old_layers.
  ViewfinderLayerCache old_layers(layer_cache_);
  visible_.clear();

  // Get start and end indexes which bracket the visible rows.
  Indexes bracket = [self indexesForInterval:interval];

  // Now, if there are more rows than we can possibly fit on the
  // screen, we sample by taking successive groups of 'n' indexes
  // and include all pre-existing indexes (so they can fade out
  // gracefully) or the highest weighted one if none are pre-existing.
  const float sample_height = UIStyle::kTitleFont.height() * 0.75; // empirically chosen to 75% of title height
  const int max_rows = std::max<int>(1, int(self.bounds.size.height / sample_height));
  const int sample_n = std::max<int>(1, floorf(float(bracket.end - bracket.start) / max_rows));

  vector<int> samples;
  vector<int> indexes;
  for (int i = bracket.start; i < bracket.end; ++i) {
    if ([env_ viewfinderIsSubrow:self index:i + start_row_]) {
      continue;
    }
    if (sample_n > 1) {
      samples.push_back(i);
      if (samples.size() == sample_n) {
        sort(samples.begin(), samples.end(), RowDisplaySort(layer_cache_, weights_));
        indexes.push_back(samples[0]);
        for (int j = 1; j < samples.size(); ++j) {
          if (FindPtrOrNull(layer_cache_, samples[j])) {
            indexes.push_back(samples[j]);
          }
        }
        samples.clear();
      }
    } else {
      indexes.push_back(i);
    }
  }
  // Include remaining samples.
  if (sample_n > 1 && !samples.empty()) {
    sort(samples.begin(), samples.end(), RowDisplaySort(layer_cache_, weights_));
    indexes.push_back(samples[0]);
    for (int j = 1; j < samples.size(); ++j) {
      if (FindPtrOrNull(layer_cache_, samples[j])) {
        indexes.push_back(samples[j]);
      }
    }
  }

  // Sort the weights according to first the already-visible rows' title
  // alphas from greatest to least and then by weight, also in descending order.
  sort(indexes.begin(), indexes.end(), RowDisplaySort(layer_cache_, weights_));

  // A count of the newly created layers.
  int newly_created_layers = 0;

  for (int i = 0; i < indexes.size(); i++) {
    const int index = indexes[i];
    const bool already_exists = ContainsKey(layer_cache_, index);
    if (newly_created_layers >= kMaxNewLayersPerRedraw && !already_exists) {
      continue;
    }
    // This is the index into the total array of rows which may be
    // available if only a fraction are being shown currently.
    const int row_index = start_row_ + index;
    const CGPoint offset = [env_ viewfinderTextOffset:self index:row_index];
    const float p = positions_[index] + offset.y;
    float alpha = row_alpha;  // May be modified for pinned row

    // Be careful not to ignore rows as soon as their position
    // extends beyond the top of the interval. We still want to show
    // them while any part of the text should be visible.
    if (p + max_row_height_ < (interval.first - interval_size * 0.10) ||
        p > (interval.second + interval_size * 0.10)) {
      continue;
    }

    // Determine label height.
    // TODO(spencer): this is garbage. Get rid of it.
    float label_height = 0;
    if ([env_ viewfinderIsSubrow:self index:row_index]) {
      label_height = UIStyle::kSubtitleFont.height();
    } else {
      label_height = (title_transition < 1) ?
                     (UIStyle::kTitleFont.height() + UIStyle::kSubtitleFont.height()) :
                     UIStyle::kTitleFont.height();
    }

    CGPoint pt = [self coordsForPosition:p circle:c withPos:cur_pos_ withLoc:cur_loc_];

    // Rows scale depending on 'curvature' of current interval.
    // This gives the viewfinder a vaguely spherical aspect when
    // pulled to its extreme limits.
    //const float title_scale = Interp(fabs(pt.y - c.center.y) / c.radius, 0, 1, 1.0, kMaxScale);

    // Find bracketing rows (based on y coordinates of already-drawn
    // rows), and depending on proximity and alpha, compute this
    // row's alpha.
    std::map<float,VisibleRow>::const_iterator lb_iter = visible_.lower_bound(pt.y);
    std::map<float,VisibleRow>::const_iterator iter = lb_iter;
    float overlap = 0;
    while (iter != visible_.end() && iter->second.pt.y - pt.y < kFadeStart) {
      const float a = 1 - iter->second.alpha;
      const float alpha_adjust = 1 - a * a;
      const float diff_y = (iter->second.pt.y - pt.y) / alpha_adjust;
      overlap += Interp(diff_y, kFadeEnd, kFadeStart, 1, 0.01);
      ++iter;
    }
    iter = lb_iter;
    while (iter != visible_.begin()) {
      --iter;
      if (pt.y - iter->second.pt.y >= kFadeStart) break;
      const float a = 1 - iter->second.alpha;
      const float alpha_adjust = 1 - a * a;
      const float diff_y = (pt.y - iter->second.pt.y) / alpha_adjust;
      overlap += Interp(diff_y, kFadeEnd, kFadeStart, 1, 0.01);
    }
    float title_alpha = alpha * ClampValue(1.0 - overlap, 0.01, 1);

    if (ContainsKey(visible_, pt.y)) {
      continue;
    }
    visible_[pt.y] = VisibleRow(index, pt, title_alpha);

    // Don't render nearly-invisible rows.
    if (title_alpha < kRowDisplayAlphaThreshold) {
      continue;
    }
    old_layers.erase(index);

    bool take_ownership = pct_active_ > 0;
    ViewfinderLayerData* layer_data = &layer_cache_[index];
    layer_data->alpha = title_alpha;
    layer_data->layer = [env_ viewfinderTextLayer:self
                                            index:row_index
                                         oldLayer:layer_data->layer
                                    takeOwnership:take_ownership];
    if (!layer_data->layer) {
      if (take_ownership) {
        DCHECK(layer_data->layer != NULL);
      }
      layer_cache_.erase(index);
      continue;
    }
    if (!already_exists) {
      ++newly_created_layers;
    }
    CompositeTextLayer* layer = layer_data->layer;

    if (pct_active_ > 0.0) {
      // Compute angle for tick marks, but only if they are being drawn.
      layer_data->angle = [self angleForPosition:p circle:c withPos:cur_pos_ withLoc:cur_loc_];
    }

    layer.transition = title_transition;
    layer.opacity = title_alpha;

    // The color of the title (do this in increments of 10% intensity to avoid
    // excessive text layer redraws).
    if (index == target_index_) {
      [layer blendForegroundColor:UIStyle::kImportantColor blendRatio:int(pct_active_ * 10) / 10.0];
    } else if (unviewed_[index]) {
      [layer blendForegroundColor:UIStyle::kImportantColor blendRatio:int(pct_active_ * 10) / 10.0];
    } else {
      const int rank = ranks_[index];
      const float weight_ratio = ClampValue((rank - kMinIndex) / (kMaxIndex - kMinIndex), 0, 1) * (pct_active_ ? 1 : 0);
      const Vector4f weighted_color = Blend(UIStyle::kTitleTextColor,
                                            UIStyle::kMinTitleTextColor,
                                            weight_ratio);
      [layer blendForegroundColor:weighted_color blendRatio:int(pct_active_ * 10) / 10.0];
    }

    if (pct_active_ > 0.0) {
      // Ensure the top-left and bottom-left corner of the text lies within the arc.
      const float top_left_y = pt.y - c.center.y;
      const float top_left_x = c.center.x - sqrt(
          std::max<float>(0, c.radius * c.radius - top_left_y * top_left_y));
      const float bottom_left_y = pt.y + label_height - c.center.y;
      const float bottom_left_x = c.center.x - sqrt(
          std::max<float>(0, c.radius * c.radius - bottom_left_y * bottom_left_y));

      pt.x = std::max<float>(offset.x, std::max(top_left_x, bottom_left_x));
      if (pct_active_ > 0.9) {
        pt.x = Interp(pct_active_, 0.9, 1, pt.x, std::max(top_left_x, bottom_left_x));
      }
      layer.frame = CGRectMake(
          pt.x, pt.y, std::max<float>(0, self.bounds.size.width - pt.x), label_height);

      // The viewfinder is active, ensure the ViewfinderTool layer is the
      // superlayer.
      if (layer.superlayer != self.layer) {
        [self.layer insertSublayer:layer below:position_indicator_];
      }
    } else {
      layer.frame = CGRectMake(offset.x, offset.y,
                               self.bounds.size.width - offset.x, label_height);
    }
  }

  for (ViewfinderLayerCache::iterator iter(old_layers.begin());
       iter != old_layers.end();
       ++iter) {
    // Return the text layer to the view that owns the viewfinder.
    // This will remove the text layer from its superlayer if applicable.
    [env_ viewfinderTextLayer:self
                        index:start_row_ + iter->first
                     oldLayer:iter->second.layer
                takeOwnership:false];
    layer_cache_.erase(iter->first);
  }

  // Remove rows from the visible vector which weren't displayed.
  for (std::map<float,VisibleRow>::iterator iter = visible_.begin();
       iter != visible_.end(); ) {
    std::map<float,VisibleRow>::iterator prev_iter = iter;
    ++iter;
    if (!FindPtrOrNull(layer_cache_, prev_iter->second.index)) {
      visible_.erase(prev_iter);
    }
  }
}

- (BOOL)pointInside:(CGPoint)p
          withEvent:(UIEvent*)event {
  return NO;
}

- (void)begin:(CGPoint)p {
  if (!needs_finish_) {
    __weak ViewfinderTool* weak_self = self;
    gl_ = LockGLState(^{
        [weak_self renderArc];
      });
    if (!gl_) {
      LOG("viewfinder: could not lock GL layer");
      return;
    }
    gl_->layer().hidden = YES;
    [self.layer insertSublayer:gl_->layer() below:position_indicator_];
    touch_loc_ = p;
    // When getting the centering y coordinate, use x coordinate equal
    // to the final activation width.
    cur_loc_.x = kActivationXCoordPct * self.trackingWidth;
    const float y = mode_ == VF_JUMP_SCROLLING ? cur_loc_.y : [self getCenteringYCoord];
    cur_pos_ = cur_pos_ - cur_loc_.y;
    cur_loc_ = CGPointMake(0, y);
    cur_pos_ += y;
    elastic_ = shape_ != SHAPE_DIAL;
    pan_velocity_ = CGPointMake(0, 0);
    [env_ viewfinderBegin:self];
    needs_finish_ = true;
    pinch_recognizer_.enabled = YES;
  }
}

- (void)willMoveToSuperview:(UIView*)new_superview {
  // Ugh, retain cycles. CADisplayLink retains its target. Says so right in the
  // documentation. And ViewfinderTool retains CADisplayLink. We allow this
  // retain cycle to exist only when the ViewfinderTool is part of the view
  // hierarchy. If the ViewfinderTool is removed from its superview, we kill
  // the CADisplayLink which breaks the retain cycle.
  if (new_superview) {
    if (!display_link_) {
      display_link_ = [CADisplayLink displayLinkWithTarget:self
                                                  selector:@selector(displayLinkCallback:)];
      [display_link_ addToRunLoop:[NSRunLoop mainRunLoop] forMode:NSDefaultRunLoopMode];
    }
  } else {
    [display_link_ invalidate];
    display_link_ = NULL;
  }
}

- (void)finish {
  if (needs_finish_) {
    if (gl_) {
      ReleaseGLState();
      gl_ = NULL;
    }
    visible_.clear();
    [self setTargetIndex:-1];
    UIEdgeInsets content_insets = [env_ viewfinderContentInsets:self];
    const float min_position = -content_insets.top;
    if (cur_pos_ - cur_loc_.y < min_position) {
      [env_ viewfinderUpdate:self position:min_position animated:YES];
    }
    [env_ viewfinderFinish:self];
    needs_finish_ = false;
    pinch_recognizer_.enabled = NO;
  }
}

- (void)initialize:(float)scroll_offset {
  if (initialized_) {
    return;
  }
  scroll_velocity_->Reset();
  cur_pos_ = scroll_offset + cur_loc_.y;
  const std::pair<int, int> rows = [env_ viewfinderRows:self];
  start_row_ = rows.first;
  end_row_ = rows.second;
  [self initPositions];
  initialized_ = true;
}

- (void)invalidate:(float)scroll_offset {
  initialized_ = false;
  [self initialize:scroll_offset];
}

- (void)open {
  if (self.canActivate) {
    [self setViewfinderState:GESTURE_OPEN
                   touch_loc:CGPointMake(0, self.bounds.size.height / 2)];
  }
}

- (void)close:(bool)animate {
  if (!animate) {
    mode_ = VF_INACTIVE;
  }
  [self setViewfinderState:GESTURE_CLOSE touch_loc:touch_loc_];
}

- (ViewfinderShape)getShape {
  return SHAPE_DIAL;
}

- (void)ensureTimesInitialized {
  // If there are still unprocessed "new" timestamps to add to the
  // "outer" and "inner" time sets, handle them now.
  if (new_timestamps_.empty()) {
    return;
  }
  for (TimestampSet::iterator iter = new_timestamps_.begin();
       iter != new_timestamps_.end();
       ++iter) {
    const WallTime t = *iter;
    const WallTime cur_outer_time = [self currentOuterTime:t];
    outer_times_.insert(cur_outer_time);
    const WallTime cur_inner_time = [self currentInnerTime:t];
    inner_times_.insert(cur_inner_time);
  }
  new_timestamps_.clear();
}

- (void)initPositions {
  // Clear layer cache by first removing any extant layers.
  for (ViewfinderLayerCache::iterator iter(layer_cache_.begin());
       iter != layer_cache_.end();
       ++iter) {
    if (iter->second.layer) {
      // Return the text layer to the view that owns the viewfinder.
      // This will remove the text layer from its superlayer if applicable.
      [env_ viewfinderTextLayer:self
                          index:start_row_ + iter->first
                       oldLayer:iter->second.layer
                  takeOwnership:false];
    }
  }

  // Create a set of previous timestamps which accord with the
  // contents of the outer and inner times. Computing current and
  // next inner/outer times is very expensive. The goal here is to
  // avoid doing it unnecessarily.
  // TODO(spencer): this algorithm never clears unused outer/inner
  //   times (e.g. if rows are deleted). Should be rare and the result
  //   will just be additional segments in the dial.
  TimestampSet existing_timestamps;
  for (int i = 0; i < timestamps_.size(); ++i) {
    existing_timestamps.insert(timestamps_[i]);
  }

  layer_cache_.clear();
  positions_.clear();
  ranks_.clear();
  timestamps_.clear();
  weights_.clear();

  time_scale_ = [env_ viewfinderTimeScaleSeconds:self];
  CHECK_LE(start_row_, end_row_);
  min_pos_ = 0;
  max_pos_ = 0;
  min_time_ = std::numeric_limits<WallTime>::max();
  max_time_ = 0;
  max_row_height_ = 0;

  [self setTargetIndex:-1];
  if (end_row_ == start_row_) {
    return;
  }
  positions_.resize(end_row_ - start_row_);
  ranks_.resize(positions_.size());
  timestamps_.resize(positions_.size());
  weights_.resize(positions_.size());
  unviewed_.resize(positions_.size());
  vector<int> indexes(positions_.size());

  for (int i = 0; i < positions_.size(); ++i) {
    const int index = start_row_ + i;
    const CGRect b = [env_ viewfinderRowBounds:self index:index];
    max_pos_ = std::max(max_pos_, CGRectGetMaxY(b));

    positions_[i] = CGRectGetMinY(b);
    max_row_height_ = std::max<float>(max_row_height_, b.size.height);
    indexes[i] = i;

    const ViewfinderRowInfo info = [env_ viewfinderRowInfo:self index:index];
    timestamps_[i] = info.timestamp;
    weights_[i] = info.weight;
    unviewed_[i] = info.unviewed;
    min_time_ = std::min(min_time_, info.timestamp);
    max_time_ = std::max(max_time_, info.timestamp);

    if (!ContainsKey(existing_timestamps, info.timestamp)) {
      new_timestamps_.insert(info.timestamp);
    }
  }

  // Compute min & max times.
  min_time_ = [self currentOuterTime:min_time_];
  max_time_ = [self nextOuterTime:[self currentOuterTime:max_time_]];

  // Sort the indexes by weight and build a rank lookup.
  sort(indexes.begin(), indexes.end(), RowRankSort(weights_));
  for (int i = 0; i < ranks_.size(); ++i) {
    ranks_[indexes[i]] = i;
  }

  // LOG("min-time=%s   max-time=%s",
  //     WallTimeFormat("%F %T", min_time_),
  //     WallTimeFormat("%F %T", max_time_));
  // LOG("min-pos=%s   max-pos=%s", min_pos_, max_pos_);

  [self computeConstants];
}

- (void)computeConstants {
  UIEdgeInsets content_insets = [env_ viewfinderContentInsets:self];
  min_tracking_pos_ = min_pos_ - content_insets.top;
  max_tracking_pos_ = std::max<float>(self.bounds.size.height, max_pos_ + content_insets.bottom) -
                      self.bounds.size.height;
  // Increase tracking_total by kOvershootFactor to make navigating to
  // the end of the scroll easier.
  tracking_total_ = (max_tracking_pos_ - min_tracking_pos_) * kOvershootFactor;

  if (tracking_total_ >= self.bounds.size.height) {
    roc_min_ = self.bounds.size.height / self.trackingHeight;
    roc_max_ = tracking_total_ / self.trackingHeight;
    can_activate_ = true;
  } else {
    roc_max_ = roc_min_ = 1;
    can_activate_ = false;
  }
#if defined(LINEAR_INTEGRATION)
  roc_slope_ = (roc_max_ - roc_min_) / self.trackingWidth;
#elif defined(EXPONENTIAL_INTEGRATION)
  // This is the percentage of tracking width which we want to have
  // the rate-of-change increase by pct_change from min to max over
  // the horizontal space defined by pct_margin of tracking width.
  const float pct_change = 0.05;
  const float pct_margin = 0.50;
  const float margin = pct_margin * self.trackingWidth;
  const float diff = roc_max_ - roc_min_;
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

- (float)deltaForTracking:(const CGPoint&)new_loc
                 last_loc:(const CGPoint&)last_loc {
  return [self delta:new_loc fromLoc:last_loc log:false];
}

- (bool)setCurrentLocation:(CGPoint)new_loc
                 integrate:(bool)integrate {
  float new_pos = cur_pos_;
  if (integrate) {
    const float delta = [self deltaForTracking:new_loc last_loc:cur_loc_];
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
    return CGRectMake(0, self.bounds.size.height / 2, self.trackingWidth, 0);
  } else {
    if (shape_ == SHAPE_TIMELINE || shape_ == SHAPE_TIMEARC) {
      float min_y = 0;
      float max_y = self.trackingHeight;
      float p0 = 0;
      CGPoint c0 = [self coordsForPosition:p0 circle:circle_ withPos:cur_pos_ withLoc:cur_loc_];
      max_y = std::min<float>(max_y, cur_loc_.y - c0.y);

      float pN = tracking_total_ + self.trackingHeight;
      CGPoint cN = [self coordsForPosition:pN circle:circle_ withPos:cur_pos_ withLoc:cur_loc_];
      min_y = std::max<float>(min_y, cur_loc_.y + (self.trackingHeight - cN.y));
      if (max_y < min_y) {
        max_y = min_y;
      }
      return CGRectMake(0, min_y, self.trackingWidth, max_y - min_y);
    }
    return CGRectMake(0, 0, self.trackingWidth, self.trackingHeight);
  }
}

- (float)getCenteringYCoord {
  const float center_y = 0.5 * self.trackingHeight;
  CGRect bounds = [self getCurrentBounds];
  return ClampValue(center_y, bounds.origin.y, bounds.origin.y + bounds.size.height);
}

- (bool)isModeAnimating {
  return (mode_ == VF_ACTIVATING ||
          mode_ == VF_RELEASING ||
          mode_ == VF_JUMP_SCROLLING ||
          mode_ == VF_STOWING ||
          mode_ == VF_ZEROING ||
          mode_ == VF_ZOOMING ||
          mode_ == VF_BOUNCING);
}

- (bool)isModeZooming {
  return (mode_ == VF_ZOOMING ||
          mode_ == VF_ZEROING);
}

- (bool)isModeTracking {
  return (mode_ == VF_TRACKING);
}

- (bool)isModeTrackable {
  return (mode_ == VF_QUIESCENT ||
          mode_ == VF_TRACKING ||
          mode_ == VF_RELEASING ||
          mode_ == VF_BOUNCING ||
          (mode_ == VF_ACTIVATING &&
           cur_loc_.x > kActivationInterruptPct * self.trackingWidth));
}

- (bool)isModePinchable {
  return (mode_ == VF_TRACKING ||
          mode_ == VF_RELEASING ||
          mode_ == VF_PINCHING ||
          mode_ == VF_QUIESCENT);
}

- (bool)canActivate {
  return (mode_ == VF_INACTIVE || mode_ == VF_SCROLLING) &&
      can_activate_ && [env_ viewfinderAlive:self];
}

- (bool)canActivateJumpScroll:(const CGPoint&)touch_loc {
  return ((mode_ == VF_INACTIVE || mode_ == VF_SCROLLING) &&
          [self canActivate] &&
          (touch_loc.x > self.bounds.size.width - kJumpScrollMargin));
}

- (bool)canActivateTimeline:(const CGPoint&)touch_loc {
  return ((mode_ == VF_INACTIVE || mode_ == VF_SCROLLING) &&
          [self canActivate] &&
          (touch_loc.x > self.bounds.size.width - kActivationMargin));
}

- (bool)canActivateDial:(const CGPoint&)touch_loc {
  return ((mode_ == VF_INACTIVE || mode_ == VF_SCROLLING) &&
          [self canActivate] &&
          (touch_loc.x < kActivationMargin));
}

- (bool)doesModeAnimateOnRelease {
  return (mode_ == VF_TRACKING);
}

- (bool)doesModeTrackScrollVelocity {
  return (mode_ == VF_INACTIVE ||
          mode_ == VF_SCROLLING);
}

- (bool)doesModeBoundPosition {
  return !(mode_ == VF_RELEASING ||
           mode_ == VF_BOUNCING);
}

- (bool)doesModeStayCentered {
  return (shape_ == SHAPE_DIAL &&
          (mode_ == VF_ACTIVATING ||
           mode_ == VF_TRACKING ||
           mode_ == VF_RELEASING ||
           mode_ == VF_BOUNCING));
}

- (bool)doesModeNeedCentering {
  return ((shape_ == SHAPE_TIMELINE ||
           shape_ == SHAPE_TIMEARC) &&
          (mode_ == VF_RELEASING ||
           mode_ == VF_BOUNCING));
}

- (bool)doesModeNeedTimedCallbacks {
  return ([self isModeAnimating] ||
          (mode_ == VF_SCROLLING && pct_scrolling_ > 0) ||
          (mode_ == VF_QUIESCENT && pct_quiescent_ < 1));
}

- (bool)doesModePassGesturesToParent {
  return (mode_ == VF_INACTIVE ||
          mode_ == VF_SCROLLING);
}

- (bool)doesModeUpdatePosition {
  return (mode_ != VF_INACTIVE &&
          mode_ != VF_SCROLLING);
}

- (bool)shouldModeBounce {
  return (mode_ == VF_RELEASING &&
          ((cur_pos_ - cur_loc_.y < min_tracking_pos_) ||
           (cur_pos_ - cur_loc_.y > max_tracking_pos_)));
}

- (bool)canModeBeStowed {
  return (mode_ == VF_TRACKING ||
          mode_ == VF_RELEASING ||
          mode_ == VF_PINCHING ||
          mode_ == VF_QUIESCENT);
}

- (bool)canModeShowLabelTransitions {
  // TODO(spencer): need to ascertain here whether or not there
  //   has been sufficient movement since the start of tracking
  //   to show label transitions.
  return (mode_ == VF_JUMP_SCROLLING ||
          mode_ == VF_TRACKING ||
          mode_ == VF_PINCHING);
}

// Resets all physics models.
- (void)resetModels {
  tracking_model_->Reset();
  location_model_->Reset();
}

// Tracking animations adjust the scroll offset as if tracking.
- (void)initTrackingAnimation:(PhysicsModel::LocationFunc)target_loc {
  [self resetModels];
  tracking_model_->Reset(Vector2f(cur_loc_), Vector2f(0, 0));
  tracking_model_->AddDefaultSpring(target_loc);
  [self initLocationAnimation];
}

- (void)initZoomAnimation {
  [self resetModels];
  tracking_model_->Reset(Vector2f(cur_loc_), Vector2f(0, 0));
  const Vector2f target_loc(0, cur_loc_.y);
  tracking_model_->AddQuickSpring(PhysicsModel::StaticLocation(target_loc));
  [self initLocationAnimation];
}

// This is a shortcut for a tracking animation to stow the viewfinder.
- (void)initStowAnimation {
  [self resetModels];
  tracking_model_->Reset(Vector2f(cur_loc_), Vector2f(0, 0));
  const Vector2f target_loc(0, cur_loc_.y);
  tracking_model_->AddVeryQuickSpring(PhysicsModel::StaticLocation(target_loc));
  [self initLocationAnimation];
}

- (void)adjustJumpScrollModel {
  const float scroll_pos = cur_pos_ - cur_loc_.y;
  Interval interval = [self getInterval:touch_loc_];
  interval.second -= self.trackingHeight;
  if (interval.first < 0) {
    interval.second -= interval.first;
    interval.first = 0;
  } else if (interval.second > tracking_total_) {
    interval.first -= (interval.second - tracking_total_);
    interval.second = tracking_total_;
  } else {
    return;
  }
  const float implied_y = (((scroll_pos - interval.first) * self.trackingHeight) /
                           (interval.second - interval.first));
  tracking_model_->set_position(Vector2f(touch_loc_.x, implied_y));
}

- (void)initJumpScrollAnimation {
  [self resetModels];
  const float scroll_pos = cur_pos_ - cur_loc_.y;
  const float implied_y = (scroll_pos * self.trackingHeight) / tracking_total_;
  tracking_model_->Reset(Vector2f(self.trackingWidth, implied_y), Vector2f(0, 0));
  // Dynamic spring location which tracks current touch position.
  PhysicsModel::LocationFunc spring_loc = ^(const PhysicsModel::State& state, double t) {
    return Vector2f(touch_loc_);
  };
  tracking_model_->AddVeryQuickSpring(spring_loc);
  PhysicsModel::ExitConditionFunc exit = ^(PhysicsModel::State* state,
                                           const PhysicsModel::State& prev_state,
                                           double t, const Vector2f& a) {
    return false;
  };
  tracking_model_->SetExitCondition(exit);

  location_model_->Reset(Vector2f(cur_loc_), Vector2f(0, 0));
  // Dynamic spring location which tracks current touch position.
  PhysicsModel::LocationFunc loc_spring_loc = ^(const PhysicsModel::State& state, double t) {
    const float transition_start = self.trackingWidth - kJumpScrollTransitionStart;
    const float transition_end = self.trackingWidth - kJumpScrollTransitionEnd;
    if (jump_scroll_timeline_) {
      return Vector2f(touch_loc_);
    } else if (touch_loc_.x >= transition_start) {
      return Vector2f(0, touch_loc_.y);
    } else if (touch_loc_.x <= transition_end) {
      jump_scroll_timeline_ = true;
    }
    const float spring_x = LinearInterp<float>(
        touch_loc_.x, transition_end, transition_start, transition_end, 0);
    return Vector2f(spring_x, touch_loc_.y);
  };
  location_model_->AddQuickSpring(loc_spring_loc);
  location_model_->SetExitCondition(exit);
}

- (void)initZeroAnimation {
  [self resetModels];
  const CGPoint offset =
      [env_ viewfinderTextOffset:self index:(start_row_ + target_index_)];
  const float target_pos = positions_[target_index_] + offset.y;
  float zero_y = self.bounds.size.height / 2;
  if (target_pos - zero_y < min_tracking_pos_) {
    zero_y = target_pos - min_tracking_pos_;
  } else if (target_pos - zero_y > max_tracking_pos_) {
    zero_y = target_pos - max_tracking_pos_;
  }
  const float delta_y = [self deltaYForPosition:target_pos - zero_y
                                        withPos:cur_pos_ - cur_loc_.y
                                        withLoc:cur_loc_];
  tracking_model_->Reset(Vector2f(cur_loc_), Vector2f(0, 0));
  const Vector2f zero_loc(cur_loc_.x, cur_loc_.y + delta_y);
  tracking_model_->AddQuickSpring(PhysicsModel::StaticLocation(zero_loc));

  location_model_->Reset(Vector2f(cur_loc_), Vector2f(0, 0));
  location_model_->AddQuickSpring(PhysicsModel::StaticLocation(Vector2f(cur_loc_.x, zero_y)));
}

// On release, set up a tracking animation with a frictional force. If
// the touch and release were done in rapid succession, impulse_track
// will be true. We use this to avoid having quick swipes in the same
// direction unintentionally slow the scroll.
- (void)initReleaseAnimation:(bool)impulse_track {
  [self resetModels];
  Vector2f release_velocity = pan_velocity_;
  Vector2f norm_release_velocity = release_velocity;
  norm_release_velocity.normalize();
  if (shape_ == SHAPE_DIAL) {
    // Always remove the horizontal velocity.
    release_velocity.x() = 0;
  } else if (fabs(Vector2f(0, 1).dot(norm_release_velocity)) >= 0.75) {
    // If the dial was released in a mostly vertical direction (75%),
    // remove the x-component.
    release_velocity.x() = 0;
  }
  // Use existing velocity instead of release velocity if this is an
  // impulse track, the existing velocity > the release velocity, and
  // there's < 45 degree angle between velocities.
  if (impulse_track &&
      tracking_model_->velocity().length() > release_velocity.length() &&
      fabs(tracking_model_->velocity().dot(norm_release_velocity)) < (sqrt(2) / 2)) {
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
                                           double t, const Vector2f& a) {
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
  [self resetModels];
  // The actual scroll buffer offset, which may be less than or
  // greater than min_tracking_pos_ and max_tracking_pos_ respectively.
  Vector2f p = tracking_model_->position();
  Vector2f v = tracking_model_->velocity();
  float target_pos;
  if (cur_pos_ - cur_loc_.y <= min_tracking_pos_) {
    target_pos = min_tracking_pos_;
  } else if (cur_pos_ - cur_loc_.y >= max_tracking_pos_) {
    target_pos = max_tracking_pos_;
  } else {
    return;
  }
  const float y = p(1) + [self deltaYForPosition:target_pos
                                         withPos:cur_pos_ - cur_loc_.y
                                         withLoc:p.ToCGPoint()];

  // Zero out x coordinate of current velocity.
  v(0) = 0;
  tracking_model_->Reset(p, v);
  // These constants are geared towards medium response and a small
  // degree of oscillation on a reasonable initial velocity.
  const float kSpring = 75;
  const float kDamp = 12;
  PhysicsModel::LocationFunc spring_loc = ^(const PhysicsModel::State& state, double t) {
    return Vector2f(state.p(0), y);
  };
  tracking_model_->AddSpring(spring_loc, kSpring, kDamp);

  location_model_->Reset(Vector2f(cur_loc_), Vector2f(0, 0));
  const float center_y = [self getCenteringYCoord];
  location_model_->AddQuickSpring(PhysicsModel::StaticLocation(Vector2f(cur_loc_.x, center_y)));

  // Exit the physics simulation according to the precision of current
  // value of cur_pos_ instead of the default checks for equilibrium.
  const float kMinTolerance = 0.5;
  PhysicsModel::ExitConditionFunc exit = ^(PhysicsModel::State* state,
                                           const PhysicsModel::State& prev_state,
                                           double t, const Vector2f& a) {
    return (fabs(state->v(1)) < 1 &&
            fabs(cur_pos_ - cur_loc_.y - target_pos) <= kMinTolerance);
  };
  tracking_model_->SetExitCondition(exit);
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
    location_model_->AddAccelerationFilter(^(const PhysicsModel::State& state, double t, const Vector2f& a) {
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
        const float center_y = [self getCenteringYCoord];
        const float y_accel = -kSpring * (cur_loc_.y - center_y) - kDamp * state.v(1);
        return Vector2f(a(0), y_accel);
      });
  }
}

- (void)displayLinkCallback:(CADisplayLink*)link {
  if ([self doesModeNeedTimedCallbacks]) {
    const Gesture gesture = [self isModeAnimating] ? [self animate] : GESTURE_NONE;
    if (([self isModeAnimating] && gesture != GESTURE_TRANSITION) ||
        (mode_ == VF_QUIESCENT && pct_quiescent_ < 1) ||
        (mode_ == VF_SCROLLING && pct_scrolling_ > 0)) {
      // continue animation...
    } else {
      display_link_.paused = YES;
    }
    [self setViewfinderState:gesture touch_loc:touch_loc_];
  } else {
    display_link_.paused = YES;
  }
  if ([self doesModeUpdatePosition]) {
    const float new_pos = cur_pos_ - cur_loc_.y;
    if (fabs(self.frame.origin.y - new_pos) >= kMinScrollPositionDelta) {
      [env_ viewfinderUpdate:self position:new_pos animated:NO];
      return;
    }
  }
  [self redraw];
}

- (Gesture)animate {
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
    [self updateCurrentPosition:(cur_pos_ + delta)];
    tracking_model_done = false;
  } else if ([self shouldModeBounce]) {
    return GESTURE_BOUNCE;
  }

  if ((tracking_model_done && location_model_done) ||
      ([self canModeBeStowed] && cur_loc_.x <= kActivationMargin)) {
    return GESTURE_TRANSITION;
  }

  return GESTURE_NONE;
}

- (float)jumpScrollTransitionPct {
  if (jump_scroll_timeline_) {
    return 1;
  }
  return LinearInterp<float>(touch_loc_.x, self.trackingWidth - kJumpScrollTransitionEnd,
                             self.trackingWidth - kJumpScrollTransitionStart, 1, 0);
}

- (void)drawPositionIndicator {
  if (mode_ == VF_JUMP_SCROLLING) {
    position_indicator_.opacity = 1 - self.jumpScrollTransitionPct;
  } else if (mode_ == VF_SCROLLING) {
    if (pct_scrolling_ == 0) {
      position_indicator_.hidden = YES;
      return;
    }
    position_indicator_.opacity = pct_scrolling_;
  } else {
    position_indicator_.hidden = YES;
    return;
  }
  position_indicator_.hidden = NO;

  float y = 0;
  int index = 0;
  CGRect visible_bounds = UIEdgeInsetsInsetRect(self.bounds, [env_ viewfinderContentInsets:self]);
  if (max_pos_ - min_pos_ > visible_bounds.size.height) {
    const float avail_height = visible_bounds.size.height - position_indicator_.frame.size.height;
    const float scroll_pos = ClampValue(cur_pos_ - cur_loc_.y, min_tracking_pos_, max_tracking_pos_);
    y = (scroll_pos / (max_tracking_pos_ - min_tracking_pos_)) * avail_height;
    index = [self indexesForPosition:cur_pos_ - cur_loc_.y + y].start;
  }
  y += visible_bounds.origin.y;

  // Use the first of the bookended positions as the display time.
  const WallTime t = [env_ viewfinderRowInfo:self index:index].timestamp;
  position_indicator_.text =
      NewNSString([env_ viewfinderFormatPositionIndicator:self
                                              atTimestamp:t]);

  float x = self.bounds.size.width - position_indicator_.bounds.size.width;
  if (mode_ == VF_JUMP_SCROLLING) {
    x -= kPositionIndicatorTouchOffset;
  }

  position_indicator_.origin = MakeIntegralPoint(x, y);
}

// Draw the viewfinder arc.
- (void)drawArc {
  if (!gl_) {
    return;
  }
  if (pct_active_ == 0.0) {
    if (gl_) {
      gl_->layer().hidden = YES;
    }
    return;
  }

  gl_->layer().frame = self.bounds;
  gl_->layer().hidden = NO;
  [gl_->layer() setNeedsDisplay];
}

- (void)renderArc {
  // Set up our model-view-projection matrix.
  Matrix4f mvp;
  const CGRect b = gl_->layer().bounds;
  mvp.ortho(0, b.size.width, b.size.height, 0, -10, 10);

  // We draw from front to back in order to be able to use
  // glBlendFunc(GL_SRC_ALPHA_SATURATE, GL_ONE) which is necessary for
  // anti-aliased triangles/lines.
  [self renderArcTicks:mvp];
  [self renderArcGradient:mvp];
  [self renderArcTexture:mvp];
  [self renderArcText:mvp];
}

- (void)renderArcGradient:(const Matrix4f&)mvp {
  // TODO(pmattis): Use a VBO for storing the per-vertex info.
  const Circle& c = circle_;
  const vector<double> kRadius = {
    0,
    c.radius - kMaskGradientWidth,
    c.radius - 0.5,
    c.radius,
    c.radius + kInnerArcOffset - kAAFilterRadius,
    c.radius + kInnerArcOffset,
    c.radius + kInnerArcOffset + kInnerArcShadowWidth,
    c.radius + kInnerArcOffset + kInnerArcShadowWidth + kAAFilterRadius,
    c.radius + kInnerArcOffset + kInnerArcWidth - kInnerArcHighlightWidth,
    c.radius + kOuterArcOffset,
    c.radius + kOuterArcOffset + kOuterArcShadowWidth,
    c.radius + kOuterArcOffset + kOuterArcWidth - kOuterArcHighlightWidth,
    c.radius + kArcWidth,
    // A final gradient to anti-alias the edge of the arc.
    c.radius + kArcWidth + kAAFilterRadius,
  };

  const float mask_alpha = pct_active_ * (1.0 - pct_quiescent_ * 0.25);
  const float it = kInnerArcBandIntensity;
  const Vector4f kColor[] = {
    { 0, 0, 0, 0.5 * mask_alpha },
    { 0, 0, 0, 0.5 * mask_alpha },
    { 0, 0, 0, 1.0 * mask_alpha },
    { 0, 0, 0, std::max<float>(0.6, mask_alpha) },
    { 0, 0, 0, std::max<float>(0.6, mask_alpha) },
    { 0, 0, 0, 1 },
    { it, it, it, 1 },
    { 0, 0, 0, 0.75 },
    { 0, 0, 0, 0.65 },
    { 0, 0, 0, 0.75 },
    { 0, 0, 0, 0.85 },
    { 0, 0, 0, 0.8 },
    { it, it, it, 1 },
    { 0, 0, 0, 0 },
  };
  CHECK_EQ(kRadius.size(), ARRAYSIZE(kColor));

  // Blocks are not allowed to access array variables. Force the conversion to
  // a pointer.
  const Vector4f* kColorPtr = kColor;

  // Avoid placing SolidShaderState in block storage but only using a pointer
  // to it from within the blocks.
  SolidShaderState solid_state;
  SolidShaderState* solid = &solid_state;

  GenerateArc(
      c.center, c.degenerate, self.bounds, kRadius, 0, 1,
      ^(const Vector4f& v, int i, float t) {
        solid->AddVertex(v, kColorPtr[i]);
      },
      ^(int a, int b, int c) {
        solid->AddTriangle(a, b, c);
      });

  solid->Draw();

  // LOG("%d triangles", solid.size() / 3);
}

- (void)renderArcTexture:(const Matrix4f&)mvp {
  const Interval interval = [self getArcInterval:cur_pos_ withLoc:cur_loc_];
  const float tx_start = 0;
  const float tx_end = 1;
  const float ty_start = interval.first / self.trackingHeight;
  const float ty_end = ty_start + self.trackingHeight / gl_->arc_texture()->height();
  const vector<Vector2f> kTexStart = {
    Vector2f(tx_end, ty_end),
    Vector2f(tx_start, ty_end)
  };
  const vector<Vector2f> kTexEnd = {
    Vector2f(tx_end, ty_start),
    Vector2f(tx_start, ty_start)
  };
  const vector<double> kRadius = {
    circle_.radius + kInnerArcOffset,
    circle_.radius + kArcWidth
  };

  // Avoid placing TextureShaderState in block storage but only using a pointer
  // to it from within the blocks.
  TextureShaderState texture_state;
  TextureShaderState* texture = &texture_state;

  GenerateArc(
      circle_.center, circle_.degenerate, self.bounds, kRadius, 0, 1,
      ^(const Vector4f& v, int i, float t) {
        texture->AddVertex(v, kTexStart[i] + (kTexEnd[i] - kTexStart[i]) * t);
      },
      ^(int a, int b, int c) {
        texture->AddTriangle(a, b, c);
      });

  // Set up the uniform variables for our shader program.
  glUseProgram(gl_->texture_shader()->name());
  // GL_CHECK_ERRORS();
  glUniformMatrix4fv(gl_->u_texture_mvp(), 1, false, mvp.data());
  glActiveTexture(GL_TEXTURE1);
  glBindTexture(GL_TEXTURE_2D, gl_->arc_texture()->name());
  glUniform1i(gl_->u_texture_texture(), 1);
  texture->Draw();
}

- (void)renderArcTicks:(const Matrix4f&)mvp {
  SolidShaderState solid;

  const float angle_adjust = 0; //kTitleFont.height_ / circle_.radius / 2;
  const float r1 = kRowTickMarkLength + 1;
  const float r2 = 1;
  const float width_angle = kRowTickMarkWidth / circle_.radius / 2;

  for (std::map<float, VisibleRow>::iterator iter(visible_.begin());
       iter != visible_.end();
       ++iter) {
    // Draw a tick mark on the inner edge of the inner arc for the row.
    const VisibleRow& v_row = iter->second;
    const ViewfinderLayerData* layer_data = FindPtrOrNull(layer_cache_, v_row.index);
    if (layer_data == NULL) {
      continue;
    }
    const float tick_angle = layer_data->angle - angle_adjust;

    const float it = kInnerArcTickMarkIntensity;
    Vector4f c(it, it, it, layer_data->layer.opacity);
    solid.AATriangle(
        circle_.arc_coords(tick_angle - width_angle, r1),
        circle_.arc_coords(tick_angle + width_angle, r1),
        circle_.arc_coords(tick_angle, r2),
        c, kClearColorRgb);
  }

  // Set up the uniform variables for our shader program.
  glUseProgram(gl_->solid_shader()->name());
  // GL_CHECK_ERRORS();
  glUniformMatrix4fv(gl_->u_solid_mvp(), 1, false, mvp.data());
  solid.Draw();
}

// Returns whether or not the specified arc segment intersects some
// part of the visible circle.
- (bool)isArcSegmentVisible:(float)begin_angle
                   endAngle:(float)end_angle
                     circle:(const Circle&)circle {
  if (begin_angle > end_angle) {
    std::swap(begin_angle, end_angle);
  }
  const float s = kPi - circle.theta / 2;
  const float e = s + circle.theta;
  const bool begin_before = begin_angle < s;
  const bool begin_in = begin_angle >= s && begin_angle <= e;
  const bool end_after = end_angle > e;
  const bool end_in = end_angle >= s && end_angle <= e;

  if (begin_in || end_in || (begin_before && end_after)) {
    return true;
  }
  return false;
}

- (ArcText)createOuterSegment:(WallTime)begin_time
                   beginAngle:(float)begin_angle
                      endTime:(WallTime)end_time
                     endAngle:(float)end_angle
                     isMerged:(bool)is_merged {
  ArcText at;
  at.begin_time = std::min<WallTime>(begin_time, end_time);
  at.end_time = std::max<WallTime>(begin_time, end_time);
  at.is_merged = is_merged;
  at.begin = std::min<float>(begin_angle, end_angle);
  at.end = std::max<float>(begin_angle, end_angle);
  at.str = FormatOuterTimeRange(
      time_scale_, begin_time, end_time, ![env_ viewfinderTimeAscending]);
  return at;
}

- (ArcText)createInnerSegment:(WallTime)begin_time
                   beginAngle:(float)begin_angle
                      endTime:(WallTime)end_time
                     endAngle:(float)end_angle
                     isMerged:(bool)is_merged {
  ArcText at;
  at.begin_time = std::min<WallTime>(begin_time, end_time);
  at.end_time = std::max<WallTime>(begin_time, end_time);
  at.is_merged = is_merged;
  at.begin = std::min<double>(begin_angle, end_angle);
  at.end = std::max<double>(begin_angle, end_angle);
  at.str = FormatInnerTimeRange(
      time_scale_, begin_time, end_time, ![env_ viewfinderTimeAscending]);
  return at;
}

- (void)renderArcText:(const Matrix4f&)mvp {
  // TODO(pmattis): This method is ginormous and needs to be cut into pieces.
  vector<ArcText> outer_text;
  vector<ArcText> inner_text;

  {
    std::set<WallTime>::const_iterator iter(outer_times_.begin());
    WallTime begin_time = *iter;
    float begin_angle = [self angleForPosition:[self positionForTime:begin_time]
                                        circle:circle_
                                       withPos:cur_pos_
                                       withLoc:cur_loc_];
    WallTime end_time = begin_time;
    float end_angle = begin_angle;

    bool is_merged = false;
    bool prev_is_merged = false;
    WallTime prev_end_time = begin_time;
    float prev_end_angle = begin_angle;

    while (iter != outer_times_.end()) {
      end_time = [self nextOuterTime:*iter];
      end_angle = [self angleForPosition:[self positionForTime:end_time]
                                  circle:circle_
                                 withPos:cur_pos_
                                 withLoc:cur_loc_];
      const bool segment_visible =
          [self isArcSegmentVisible:begin_angle endAngle:end_angle circle:circle_];

      // If we're thinking about merging, check whether the current segment
      // should stand alone first.
      if (is_merged) {
        const float cur_segment_length = fabs(end_angle - prev_end_angle) *
                                         (circle_.radius + kOuterTextOffset);
        if (cur_segment_length >= kMinArcSegmentLength) {
          outer_text.push_back([self createOuterSegment:begin_time
                                             beginAngle:begin_angle
                                                endTime:prev_end_time
                                               endAngle:prev_end_angle
                                               isMerged:prev_is_merged]);
          is_merged = false;
          begin_time = *iter;
          begin_angle = [self angleForPosition:[self positionForTime:begin_time]
                                        circle:circle_
                                       withPos:cur_pos_
                                       withLoc:cur_loc_];
        }
      }
      const float segment_length = fabs(end_angle - begin_angle) *
                                   (circle_.radius + kOuterTextOffset);
      if (segment_length < kMinArcSegmentLength) {
        prev_is_merged = is_merged;
        prev_end_time = end_time;
        prev_end_angle = end_angle;
        is_merged = true;
        ++iter;
        continue;
      }

      if (segment_visible) {
        outer_text.push_back([self createOuterSegment:begin_time
                                           beginAngle:begin_angle
                                              endTime:end_time
                                             endAngle:end_angle
                                             isMerged:is_merged]);
      }
      if (++iter != outer_times_.end()) {
        begin_time = *iter;
        begin_angle = [self angleForPosition:[self positionForTime:begin_time]
                                      circle:circle_
                                     withPos:cur_pos_
                                     withLoc:cur_loc_];
      }
      is_merged = false;
    }
    if (outer_text.empty() || is_merged) {
      outer_text.push_back([self createOuterSegment:begin_time
                                         beginAngle:begin_angle
                                            endTime:end_time
                                           endAngle:end_angle
                                           isMerged:is_merged]);
    }
  }

  for (int i = 0; i < outer_text.size(); ++i) {
    const ArcText& outer = outer_text[i];
    // Loop over the inner times.
    std::set<WallTime>::const_iterator iter(
        inner_times_.lower_bound(outer.begin_time));
    int inner_count = 0;
    WallTime begin_time = *iter;
    float begin_angle =
        [self angleForPosition:[self positionForTime:begin_time]
                        circle:circle_
                       withPos:cur_pos_
                       withLoc:cur_loc_];
    WallTime end_time = begin_time;
    float end_angle = begin_angle;

    bool is_merged = false;
    bool prev_is_merged = false;
    WallTime prev_end_time = begin_time;
    float prev_end_angle = begin_angle;

    while (*iter < outer.end_time && iter != inner_times_.end()) {
      // TODO(spencer): if we want to fully eliminate the call to next
      // inner time, we could store a pair<> of inner times instead.
      end_time = [self nextInnerTime:*iter];
      end_angle = [self angleForPosition:[self positionForTime:end_time]
                                  circle:circle_
                                 withPos:cur_pos_
                                 withLoc:cur_loc_];
      const bool segment_visible =
          [self isArcSegmentVisible:begin_angle endAngle:end_angle circle:circle_];

      // If we're thinking about merging, check whether the current segment
      // should stand alone first.
      if (is_merged) {
        const float cur_segment_length = fabs(end_angle - prev_end_angle) *
                                         (circle_.radius + kInnerTextOffset);
        if (cur_segment_length >= kMinArcSegmentLength) {
          inner_text.push_back([self createInnerSegment:begin_time
                                             beginAngle:begin_angle
                                                endTime:prev_end_time
                                               endAngle:prev_end_angle
                                               isMerged:prev_is_merged]);
          is_merged = false;
          begin_time = *iter;
          begin_angle = [self angleForPosition:[self positionForTime:begin_time]
                                        circle:circle_
                                       withPos:cur_pos_
                                       withLoc:cur_loc_];
        }
      }
      const float segment_length = fabs(end_angle - begin_angle) *
                                   (circle_.radius + kInnerTextOffset);
      if (segment_length < kMinArcSegmentLength) {
        prev_is_merged = is_merged;
        prev_end_time = end_time;
        prev_end_angle = end_angle;
        is_merged = true;
        ++iter;
        continue;
      }

      if (segment_visible) {
        inner_text.push_back([self createInnerSegment:begin_time
                                           beginAngle:begin_angle
                                              endTime:end_time
                                             endAngle:end_angle
                                             isMerged:is_merged]);
        ++inner_count;
      }
      if (++iter != inner_times_.end()) {
        begin_time = *iter;
        begin_angle = [self angleForPosition:[self positionForTime:begin_time]
                                      circle:circle_
                                     withPos:cur_pos_
                                     withLoc:cur_loc_];
      }
      is_merged = false;
    }

    // If there's leftover, create final segment.
    if (!inner_count || is_merged) {
      inner_text.push_back([self createInnerSegment:begin_time
                                         beginAngle:begin_angle
                                            endTime:end_time
                                           endAngle:end_angle
                                           isMerged:is_merged]);
    }
    // Make sure final segment extends to full angle.
    if (end_time != outer.end_time) {
      inner_text.back() = [self createInnerSegment:inner_text.back().begin_time
                                        beginAngle:([env_ viewfinderTimeAscending] ?
                                                    inner_text.back().end : inner_text.back().begin)
                                           endTime:inner_text.back().end_time
                                          endAngle:[env_ viewfinderTimeAscending] ? outer.begin : outer.end
                                          isMerged:inner_text.back().is_merged];
    }
  }

  struct {
    const vector<ArcText>& text;
    UIFont* font;
  } glyph_data[] = {
    { outer_text, kOuterFont },
    { inner_text, kInnerFont },
  };

  // Ensure that we have info for every potential glyph.
  for (int i = 0; i < ARRAYSIZE(glyph_data); ++i) {
    const vector<ArcText>& text = glyph_data[i].text;
    UIFont* font = glyph_data[i].font;

    for (int j = 0; j < text.size(); ++j) {
      const ArcText& a = text[j];
      gl_->AccumulateGlyphs(Slice(a.str), font);
    }
  }
  gl_->CommitGlyphTexture();

  struct {
    vector<ArcText>* text;
    const float offset;
    UIFont* font;
    const float tick_radius;
    const float tick_length;
    const float tick_intensity;
  } data[] = {
    { &outer_text, kOuterTextOffset, kOuterFont,
      kInnerArcOffset + kInnerArcShadowWidth,
      kOuterArcWidth + kInnerArcWidth - kOuterArcHighlightWidth - kInnerArcShadowWidth,
      kOuterDividerIntensity },
    { &inner_text, kInnerTextOffset, kInnerFont,
      kInnerArcOffset + kInnerArcShadowWidth,
      kInnerArcWidth - kInnerArcShadowWidth,
      kInnerDividerIntensity },
  };

  TextureShaderState texture;
  SolidShaderState solid;
  std::unordered_set<float> tick_angles;

  for (int i = 0; i < ARRAYSIZE(data); ++i) {
    const float radius = circle_.radius + data[i].offset;
    vector<ArcText>* text = data[i].text;
    UIFont* font = glyph_data[i].font;

    for (int j = 0; j < text->size(); ++j) {
      ArcText* a = &(*text)[j];
      a->line_length = 0;

      Slice s(a->str);
      while (!s.empty()) {
        const int r = utfnext(&s);
        if (r == -1) {
          break;
        }
        const GLState::GlyphInfo* g = gl_->GetGlyphInfo(std::make_pair(font, r));
        CHECK(g->str != NULL);
        a->line_length += g->size.width;
      }
    }

    for (int j = 0; j < text->size(); ++j) {
      const ArcText& a = (*text)[j];
      const float line_angle = a.line_length / radius;

      // Limit the begin angle to the start of the visible screen arc and the
      // end angle to the end of the visible screen arc so that the arc text
      // is always centered on the visible arc segment.
      const float begin_angle = std::max<float>(a.begin, kPi - circle_.theta / 2);
      const float end_angle = std::min<float>(a.end, kPi + circle_.theta / 2);
      float angle = begin_angle + (end_angle - begin_angle - line_angle) / 2 - kPi / 2;

      Slice s(a.str);
      while (!s.empty()) {
        const int r = utfnext(&s);
        if (r == -1) {
          break;
        }
        const GLState::GlyphInfo* g = gl_->GetGlyphInfo(std::make_pair(font, r));
        CHECK(g->str != NULL);

        const float glyph_angle = g->size.width / radius;
        float alpha = 1;
        if (angle + kPi / 2 < a.begin + glyph_angle) {
          alpha = Interp(angle + kPi / 2, a.begin, a.begin + glyph_angle, 0, 1);
        } else if (angle + kPi / 2 > a.end - glyph_angle * 2) {
          alpha = Interp(angle + kPi / 2, a.end - glyph_angle * 2, a.end - glyph_angle, 1, 0);
        }

        if (alpha > 0 && angle > 0 && angle < kPi) {
          Matrix4f m;
          // Translate glyph so that it is horizontally centered and its baseline
          // is vertically on the edge of the arc.
          m.translate(-g->size.width, radius -
                      (g->size.height - font.ascender) + 0.5, 0);
          // Rotate to the correct orientation and position.
          m.rotate(angle, 0, 0, 1);
          m.translate(circle_.center.x, circle_.center.y, 0);

          const int a = texture.AddVertex(
              m * Vector4f(0, 0, 0, 1),
              Vector2f(g->tx_start, g->ty_start), alpha);
          const int b = texture.AddVertex(
              m * Vector4f(0, g->size.height, 0, 1),
              Vector2f(g->tx_start, g->ty_end), alpha);
          const int c = texture.AddVertex(
              m * Vector4f(g->size.width, 0, 0, 1),
              Vector2f(g->tx_end, g->ty_start), alpha);
          const int d = texture.AddVertex(
              m * Vector4f(g->size.width, g->size.height, 0, 1),
              Vector2f(g->tx_end, g->ty_end), alpha);
          texture.AddTriangle(a, b, c);
          texture.AddTriangle(d, c, b);
        }

        angle += glyph_angle;
      }
    }

    const Vector4f tick_color(
        data[i].tick_intensity, data[i].tick_intensity,
        data[i].tick_intensity, 1);
    for (int j = 0; j < text->size(); ++j) {
      // Draw tick marks between arc segments.
      const ArcText& a = (*text)[j];
      if (!ContainsKey(tick_angles, a.begin) &&
          a.begin > kPi / 2 && a.begin < (kPi * 3) / 2) {
        tick_angles.insert(a.begin);
        solid.AALine(
            circle_.arc_coords(a.begin, data[i].tick_radius),
            circle_.arc_coords(a.begin, data[i].tick_radius + data[i].tick_length),
            1.5, tick_color, kClearColorRgb);
      }
      if (!ContainsKey(tick_angles, a.end) &&
          a.end > kPi / 2 && a.end < (kPi * 3) / 2) {
        tick_angles.insert(a.end);
        solid.AALine(
            circle_.arc_coords(a.end, data[i].tick_radius),
            circle_.arc_coords(a.end, data[i].tick_radius + data[i].tick_length),
            1.5, tick_color, kClearColorRgb);
      }
    }
  }

  // Set up the uniform variables for our shader program.
  glUseProgram(gl_->texture_shader()->name());
  // GL_CHECK_ERRORS();
  glUniformMatrix4fv(gl_->u_texture_mvp(), 1, false, mvp.data());
  glUniform1i(gl_->u_texture_texture(), 0);
  glBlendFunc(GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
  texture.Draw();

  // Set up the uniform variables for our shader program.
  glUseProgram(gl_->solid_shader()->name());
  // GL_CHECK_ERRORS();
  glUniformMatrix4fv(gl_->u_solid_mvp(), 1, false, mvp.data());
  solid.Draw();

  glBlendFunc(GL_SRC_ALPHA_SATURATE, GL_ONE);
}

- (void)drawScrollBar {
  if (pct_active_ > 0 && (max_pos_ - min_pos_) > self.bounds.size.height) {
    const float max_size = (max_pos_ - min_pos_) * ((shape_ == SHAPE_DIAL) ? 2 : 1);
    const Interval interval = [self getArcInterval:cur_pos_ withLoc:cur_loc_];
    const float interval_size = interval.second - interval.first;
    const float height = Interp(interval_size, self.bounds.size.height, max_size,
                                kScrollBarMinHeight, self.bounds.size.height);
    const float scroll_pos = cur_pos_ - cur_loc_.y;
    const float y = ((scroll_pos - min_tracking_pos_) / (max_tracking_pos_ - min_tracking_pos_)) *
                    (self.bounds.size.height - height);
    scroll_bar_.frame = CGRectMake(self.bounds.size.width - kScrollBarWidth - kScrollBarMargin, y, kScrollBarWidth, height);
    scroll_bar_.hidden = NO;
  } else {
    scroll_bar_.hidden = YES;
  }
}

- (void)drawLocationIndicator {
  if (pct_active_ == 0) {
    location_indicator_.hidden = YES;
  } else {
    const float angle_adjust = 0; //kTitleFont.height_ / circle_.radius / 2;
    const float cur_angle = [self angleForPosition:cur_pos_
                                            circle:circle_
                                           withPos:cur_pos_
                                           withLoc:cur_loc_] - angle_adjust;
    CGAffineTransform xform = CGAffineTransformMakeTranslation(
        circle_.center.x, circle_.center.y);
    xform = CGAffineTransformRotate(xform, cur_angle);
    xform = CGAffineTransformTranslate(xform, circle_.radius + kArcWidth, -4);
    xform = CGAffineTransformScale(xform, -0.5, 0.5);

    [location_indicator_ setAffineTransform:xform];
    location_indicator_.hidden = NO;
    location_indicator_.strokeColor = (pct_quiescent_ > 0 || !elastic_) ?
                                      kLocationIndicatorBorderColor :
                                      kLocationIndicatorBorderActiveColor;
    location_indicator_.fillColor = (pct_quiescent_ > 0 || !elastic_) ?
                                    kLocationIndicatorBackgroundColor :
                                    kLocationIndicatorBackgroundActiveColor;
    if (mode_ == VF_JUMP_SCROLLING) {
      location_indicator_.opacity = self.jumpScrollTransitionPct;
    } else {
      location_indicator_.opacity = 1;
    }
  }
}

- (void)setViewfinderState:(Gesture)gesture
                 touch_loc:(CGPoint)touch_loc {
  const ViewfinderMode old_mode = mode_;
  const WallTime now = WallTime_Now();

  if (gesture == GESTURE_TRACK) {
    touch_loc_ = touch_loc;

    if ([self canActivateJumpScroll:touch_loc]) {
      // Activate jump scrolling.
      shape_ = SHAPE_TIMELINE;
      mode_ = VF_JUMP_SCROLLING;
      jump_scroll_timeline_ = false;
      [self begin:touch_loc];
      [self initJumpScrollAnimation];
    } else if ([self isModeTrackable]) {
      mode_ = VF_TRACKING;
      tracking_start_ = now;
      [self setTargetIndex:-1];
    } else if (mode_ == VF_JUMP_SCROLLING) {
      [self adjustJumpScrollModel];
    }
  } else if (gesture == GESTURE_ACTIVATION) {
    [self ensureTimesInitialized];
    // Initialize current position.
    cur_pos_ = self.frame.origin.y + cur_loc_.y;
    if ([self canActivateJumpScroll:touch_loc]) {
      // Activate jump scrolling.
      shape_ = SHAPE_TIMELINE;
      mode_ = VF_JUMP_SCROLLING;
      jump_scroll_timeline_ = false;
      [self begin:touch_loc];
      [self initJumpScrollAnimation];
      cur_loc_.x = 0;
    } else if ([self canActivateDial:touch_loc]) {
      shape_ = [self getShape];
      mode_ = VF_ACTIVATING;
      [self begin:touch_loc];
      // Activates out to a pleasing x coordinate for zoom.
      const float x_coord = kActivationXCoordPct * self.trackingWidth;
      const Vector2f initial_loc(x_coord, cur_loc_.y);
      [self initTrackingAnimation:PhysicsModel::StaticLocation(initial_loc)];
    }
  } else if (gesture == GESTURE_SINGLE_TAP) {
    if ([self isModeTrackable] &&
        tracking_model_->velocity().length() < kMaxZeroingPanVelocity) {
      // Start zeroing if the current mode is trackable and the pan
      // velocity is below the maximum allowed.
      CGPoint target_loc;
      [self setTargetIndex:[self indexAtLocation:touch_loc arc_coords:&target_loc]];
      // If no target was selected, stow the viewfinder.
      if (target_index_ == -1) {
        mode_ = VF_STOWING;
        [self initStowAnimation];
      } else {
        mode_ = VF_ZEROING;
        [self initZeroAnimation];
      }
    }
  } else if (gesture == GESTURE_SWIPE_LEFT ||
             gesture == GESTURE_SWIPE_RIGHT) {
    if (mode_ == VF_TRACKING && shape_ == SHAPE_DIAL) {
      elastic_ = true;
    }
  } else if (gesture == GESTURE_PINCH) {
    // TODO(spencer): pinch collapses conversation views.
    if ([self isModePinchable]) {
      if (mode_ != VF_PINCHING) {
        mode_ = VF_PINCHING;
        pinch_start_x_ = mode_ == VF_INACTIVE ? 0 : cur_loc_.x;
      }
    }
  } else if (gesture == GESTURE_RELEASE) {
    if (mode_ == VF_JUMP_SCROLLING) {
      if (jump_scroll_timeline_) {
        mode_ = VF_STOWING;
        [self initStowAnimation];
      } else {
        cur_loc_.x = 0;
        mode_ = VF_INACTIVE;
      }
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
      const bool impulse_track = (now - tracking_start_) < kImpulseTrackThreshold;
      [self initReleaseAnimation:impulse_track];
    } else if (mode_ == VF_PINCHING) {
      mode_ = VF_QUIESCENT;
    }
    // Reset elasticity of dial on release.
    if (shape_ == SHAPE_DIAL) {
      elastic_ = false;
    }
  } else if (gesture == GESTURE_BOUNCE) {
    mode_ = VF_BOUNCING;
    [self initScrollBounceAnimation];
  } else if (gesture == GESTURE_OPEN) {
    [self ensureTimesInitialized];
    if ([self canActivate]) {
      shape_ = [self getShape];
      mode_ = VF_ACTIVATING;
      [self begin:touch_loc];
      // Activates out to a pleasing x coordinate for zoom.
      const float x_coord = kActivationXCoordPct * self.trackingWidth;
      const Vector2f initial_loc(x_coord, cur_loc_.y);
      [self initTrackingAnimation:PhysicsModel::StaticLocation(initial_loc)];
    }
  } else if (gesture == GESTURE_CLOSE) {
    if (mode_ != VF_INACTIVE) {
      mode_ = VF_STOWING;
      [self initStowAnimation];
    } else {
      cur_loc_.x = 0;
    }
  } else if (gesture == GESTURE_TRANSITION) {
    if (mode_ == VF_ACTIVATING) {
      if (tracking_) {
        mode_ = VF_TRACKING;
      } else {
        mode_ = VF_RELEASING;
        [self initReleaseAnimation:true];
      }
    } else if (mode_ == VF_RELEASING) {
      if (cur_loc_.x > 0 && cur_loc_.x < kActivationMargin) {
        mode_ = VF_STOWING;
        [self initStowAnimation];
      } else if (cur_loc_.x == 0) {
        // If viewfinder is pushed all the way off, de-activate.
        mode_ = VF_INACTIVE;
      } else {
        mode_ = tracking_ ? VF_TRACKING : VF_QUIESCENT;
      }
    } else if (mode_ == VF_BOUNCING) {
      mode_ = VF_QUIESCENT;
    } else if (mode_ == VF_ZEROING) {
      // If released in zeroing, transition to ZOOMING.
      mode_ = VF_ZOOMING;
      [self initZoomAnimation];
    } else if (mode_ == VF_ZOOMING || mode_ == VF_STOWING) {
      mode_ = VF_INACTIVE;
    } else {
      CHECK([self isModeAnimating]);
    }
  } else {
    if (gesture != GESTURE_NONE) {
      return;
    }
    // Handle scroll transition. We activate SCROLLING mode if the
    // velocity of vertical scroll exceeds kMinPIScrollVelocity. We
    // start a transition out of scrolling when scroll velocity is
    // 0 and the user is no longer tracking.
    if (mode_ == VF_INACTIVE && scroll_velocity_->magnitude() > kMinPIScrollVelocity) {
      mode_ = VF_SCROLLING;
      scrolling_start_time_ = 0;
    } else if (mode_ == VF_SCROLLING) {
      if (scroll_velocity_->magnitude() <= kFadePIScrollVelocity) {
        if (scrolling_start_time_ == 0) {
          scrolling_start_time_ = now;
        } else if ((now - scrolling_start_time_) >= kPositionIndicatorFadeDuration) {
          mode_ = VF_INACTIVE;
        }
      } else {
        scrolling_start_time_ = 0;
      }
    }
  }

  // Compute how activated the viewfinder tool is.
  pct_active_ = ClampValue((cur_loc_.x - 1) / kActivationMargin, 0, 1);
  pct_quiescent_ = 0;
  pct_scrolling_ = 0;

  // Compute the circle on which to draw labels.
  circle_ = [self getCircle:cur_loc_];

  if (mode_ == VF_INACTIVE) {
    // Final redraw ensures gl layer is cleared. Otherwise, if the dial
    // is closed with animation=NO, a leftover ghost of the dial will
    // display on the gl layer the next time the dial is opened.
    [self redraw];
    [self finish];
  } else if (mode_ == VF_SCROLLING) {
    if (![env_ viewfinderDisplayPositionIndicator:self]) {
      pct_scrolling_ = 0;
    } else {
      pct_scrolling_ = (scrolling_start_time_ == 0) ? 1 :
                       Interp(now - scrolling_start_time_, 0,
                              kPositionIndicatorFadeDuration, 1, 0);
    }
  } else if (mode_ == VF_QUIESCENT) {
    if (old_mode != mode_) {
      quiescent_start_time_ = now;
    }
    pct_quiescent_ = Interp(now - quiescent_start_time_, 0, kQuiescenceDuration, 0, 1);
  }

  if (old_mode != mode_) {
    //LOG("transitioning from mode %d to mode %d with gesture %d; animating: %d",
    //old_mode, mode_, gesture, [self isModeAnimating]);
    if (![self isModeAnimating]) {
      [self resetModels];
    }
    // Only allow the pan recognizer to begin when we're in a release
    // animation. This allows any touch to the screen to stop the
    // current animation by reseting the pan velocity to 0.
    pan_recognizer_.touchesCanBegin = mode_ == VF_RELEASING;
    display_link_.paused = NO;
  } else {
    if ([self doesModeNeedTimedCallbacks]) {
      display_link_.paused = NO;
    }
  }
}

- (bool)isAppActive {
  return [UIApplication sharedApplication].applicationState ==
      UIApplicationStateActive;
}

- (void)redraw {
  if (!initialized_ || positions_.empty()) {
    return;
  }
  if (!self.isAppActive || ![env_ viewfinderAlive:self]) {
    return;
  }

  [CATransaction begin];
  [CATransaction setDisableActions:YES];

  [self drawScrollBar];
  [self drawLocationIndicator];
  [self drawPositionIndicator];
  [self drawRowText];
  [self drawArc];

  [CATransaction commit];
}

- (void)drawRect:(CGRect)rect {
  if (!initialized_) {
    return;
  }
  [super drawRect:rect];
  display_link_.paused = NO;
}

- (BOOL)gestureRecognizerShouldBegin:(UIGestureRecognizer*)recognizer {
  if (!self.userInteractionEnabled) {
    return NO;
  }
  // Special cases depending on viewfinder mode.
  const CGPoint p = [recognizer locationInView:self];
  switch (mode_) {
    case VF_ACTIVATING:
      return recognizer != long_press_recognizer_;
    case VF_INACTIVE:
    case VF_SCROLLING:
      if (recognizer == activation_recognizer_) {
        return (p.x > self.bounds.size.width - kJumpScrollMargin ||
                p.x < kActivationMargin);
      }
      if (recognizer == pan_recognizer_ && mode_ == VF_SCROLLING) {
        // Allow the pan recognizer to begin if we're currently scrolling and
        // the touch location is close to the position indicator frame.
        const CGRect f = CGRectInset(
            position_indicator_.frame,
            -kPositionIndicatorTouchBorder, -kPositionIndicatorTouchBorder);
        if (CGRectContainsPoint(f, p)) {
          return YES;
        }
      }
      return NO;
    case VF_JUMP_SCROLLING:
      return recognizer == pan_recognizer_;
    default:
      break;
  }
  if (pct_active_ > 0) {
    // Make sure the exit button isn't being tapped.
    UIView* v = [self.superview hitTest:[recognizer locationInView:self.superview] withEvent:NULL];
    if ([v isKindOfClass:[UIControl class]]) {
      return NO;
    }
    return YES;
  }
  return NO;
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

- (void)dealloc {
  if (gl_) {
    ReleaseGLState();
    gl_ = NULL;
  }
}

@end  // ViewfinderTool
