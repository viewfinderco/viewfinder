// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <QuartzCore/QuartzCore.h>
#import "Appearance.h"
#import "AppState.h"
#import "Logging.h"
#import "PhotoManager.h"
#import "STLUtils.h"
#import "ViewfinderTool.h"

namespace {

const float kLeftMargin = 100;
const float kRightMargin = 40;
const float kTopMargin = 20;
const float kBottomMargin = 20;
const float kArcWidth = 25;
const WallTime kHour = 60 * 60;
const WallTime kDay = kHour * 24;
const WallTime kMonth = kDay * 30;        // Approximate
const WallTime kYear = kDay * 365;        // Approximate
const WallTime kMinTotalSecs = kDay * 7;  // 1 week

const float kYearFontSize = 15;
const float kYearTextOffset = 12;
const float kYearArcWidth = 24;

const float kMonthFontSize = 12;
const float kMonthTextOffset = 2.5;
const float kMonthArcWidth = 12;

LazyStaticFont kEpisodeFont = { kHelvetica, 15 };

int GetYear(WallTime t) {
  return LocalTime(t).tm_year;
}

struct EpisodeByPosition {
  bool operator()(const EpisodeInfo& a, const EpisodeInfo& b) const {
    return a.position < b.position;
  }
};

struct EpisodeByTime {
  bool operator()(const EpisodeInfo& a, const EpisodeInfo& b) const {
    return a.timestamp > b.timestamp;
  }
};

struct Arc {
  Arc(float b, float e)
      : begin(b),
        end(e) {
  }
  float size() const { return end - begin; }
  float begin;
  float end;
};

bool DrawArcText(
    const string& str, CTFontRef font, const CGPoint& center,
    float radius, float begin_angle, float end_angle,
    float max_scale, bool clip) {
  NSString* ns_str = NewNSString(str);
  const Dict attrs(kCTFontAttributeName, (__bridge id)font,
                   kCTForegroundColorFromContextAttributeName, true);
  NSAttributedString* ns_attr_str =
      [[NSAttributedString alloc] initWithString:ns_str attributes:attrs];
  ScopedRef<CTLineRef> line(
      CTLineCreateWithAttributedString(
          (__bridge CFAttributedStringRef)ns_attr_str));
  if (CTLineGetGlyphCount(line) == 0) {
    return false;
  }

  const float spacing_angle = 2 / radius;
  begin_angle += spacing_angle;
  end_angle -= spacing_angle;

  const double line_length =
      CTLineGetTypographicBounds(line, NULL, NULL, NULL);
  const float total_length = (end_angle - begin_angle) * radius;
  if (clip && total_length < line_length) {
    return false;
  }
  const float scale = std::max<float>(
      1, std::min<float>(max_scale, total_length / line_length));
  const float line_angle = line_length * scale / radius;
  const float start_angle = begin_angle +
      (end_angle - begin_angle - line_angle) / 2;

  CGContextRef context = UIGraphicsGetCurrentContext();

  // Move the origin from the lower left of the view nearer to its center.
  CGContextSaveGState(context);
  CGContextTranslateCTM(context, center.x, center.y);

  // Initialize the text matrix to a known value.
  CGContextSetTextMatrix(context, CGAffineTransformIdentity);

  // Flip the context vertically around the x-axis.
  CGContextScaleCTM(context, 1, -1);

  // Rotate the context to the start of the first glyph.
  CGContextRotateCTM(context, kPi / 2 + (kPi - start_angle));

  // Draw each glyph overstruck and centered over one another, making sure to
  // rotate the contxt after each glyph so the glyphs are spread along the arc.
  CGPoint text_position = CGPointMake(0.0, radius);
  CGContextSetTextPosition(context, text_position.x, text_position.y);

  CFArrayRef run_array = CTLineGetGlyphRuns(line);
  const int run_count = CFArrayGetCount(run_array);
  for (int i = 0; i < run_count; i++) {
    CTRunRef run = (CTRunRef)CFArrayGetValueAtIndex(run_array, i);
    const int run_glyph_count = CTRunGetGlyphCount(run);

    for (int j = 0; j < run_glyph_count; ++j) {
      const CFRange range = CFRangeMake(j, 1);
      const float width = CTRunGetTypographicBounds(
          run, range, NULL, NULL, NULL);

      CGAffineTransform text_matrix = CTRunGetTextMatrix(run);
      text_matrix.tx = text_position.x;
      text_matrix.ty = text_position.y;
      CGContextSetTextMatrix(context, text_matrix);

      CTRunDraw(run, context, range);

      // Glyphs are positioned relative to the text position for the line, so
      // offset text position leftwards by this glyph's width in preparation
      // for the next glyph.
      text_position.x -= width;

      // Setup the rotation for the next glyph.
      CGContextRotateCTM(context, -width * scale / radius);
    }
  }

  CGContextRestoreGState(context);
  return true;
}

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

}  // namespace

ViewfinderToolImpl::ViewfinderToolImpl(AppState* state, UIView* parent)
    : state_(state),
      parent_(parent),
      font_(kEpisodeFont),
      year_font_(CTFontCreateWithName(
                     (__bridge CFStringRef)kHelveticaBold,
                     kYearFontSize, NULL)),
      month_font_(CTFontCreateWithName(
                      (__bridge CFStringRef)kHelveticaMedium,
                      kMonthFontSize, NULL)),
      tracking_(false),
      min_pos_(0),
      min_tracking_pos_(0),
      max_pos_(0),
      max_tracking_pos_(0),
      cur_pos_(0),
      cur_opacity_(0),
      roc_max_(0),
      roc_slope_(0),
      min_time_(0),
      max_time_(0),
      last_loc_(CGPointMake(0, 0)),
      min_x_loc_(0) {
}

ViewfinderToolImpl::~ViewfinderToolImpl() {
}

void ViewfinderToolImpl::DrawRect(const CGRect& r) {
  if (!tracking_) {
    return;
  }

  const Circle c = GetCircle(last_loc_);
  DrawDates(c);
  DrawEpisodes(c);
}

void ViewfinderToolImpl::SetEpisodes(const vector<EpisodeInfo>& episodes) {
  episodes_ = episodes;
  years_.clear();

  min_pos_ = std::numeric_limits<float>::max();
  max_pos_ = 0;

  min_time_ = std::numeric_limits<WallTime>::max();
  max_time_ = 0;

  for (int i = 0; i < episodes_.size(); ++i) {
    const EpisodeInfo& e = episodes_[i];
    min_pos_ = std::min(min_pos_, e.position);
    max_pos_ = std::max(max_pos_, e.position);

    const WallTime t = e.timestamp;
    years_.insert(CurrentYear(t));

    // Determine the year 2 months before the episode's timestamp.
    const WallTime p = CurrentMonth(CurrentMonth(CurrentMonth(t) - 1) - 1);
    years_.insert(CurrentYear(p));
    min_time_ = std::min(min_time_, p);

    // Determine the year 2 months after the episode's timestamp.
    const WallTime n = NextMonth(NextMonth(t));
    years_.insert(CurrentYear(n));
    max_time_ = std::max(max_time_, n);
  }

  const float total = max_pos_ - min_pos_;
  min_tracking_pos_ = min_pos_ - total * 0.1;
  max_tracking_pos_ = max_pos_ + total * 0.1;
  const float tracking_total = max_tracking_pos_ - min_tracking_pos_;

  roc_max_ = tracking_total / tracking_height();
  roc_slope_ = (parent_.bounds.size.height - tracking_total) /
      (tracking_width() * tracking_height());
  cur_pos_ = min_tracking_pos_ + TransformPoint(last_loc_).y * roc_max_;

  Update();
}

void ViewfinderToolImpl::BeginTracking(const CGPoint& new_loc) {
  last_loc_ = new_loc;
  min_x_loc_ = last_loc_.x;
  tracking_ = true;
}

void ViewfinderToolImpl::ContinueTracking(const CGPoint& new_loc) {
  AdjustPosition(new_loc);
  Update();
}

void ViewfinderToolImpl::EndTracking(const CGPoint& new_loc) {
  CancelTracking();
}

void ViewfinderToolImpl::CancelTracking() {
  tracking_ = false;
  Update();
}

void ViewfinderToolImpl::Update() {
  [parent_ setNeedsDisplay];

  const float kMinOpacity = 0.5;
  const float kMaxOpacity = 0.85;

  if (min_x_loc_ >= parent_.bounds.size.width - 1.5 * kRightMargin) {
    const float min_x = parent_.bounds.size.width - 1.5 * kRightMargin;
    const float max_opacity =
        kMinOpacity + (kMaxOpacity - kMinOpacity) *
        Interp(TransformPoint(last_loc_).x, 0, tracking_width(), 1, 0);
    const float t = Interp(last_loc_.x, min_x, min_x + kRightMargin / 2, 1, 0);
    cur_opacity_ = kMinOpacity + (max_opacity - kMinOpacity) * t;
  } else {
    const float x = TransformPoint(last_loc_).x;
    const float t = Interp(x, 0, tracking_width(), 1, 0);
    cur_opacity_ = kMinOpacity + (kMaxOpacity - kMinOpacity) * t;
  }
}

void ViewfinderToolImpl::DrawDates(const Circle& c) {
  float arc_alpha = 1;
  if (last_loc_.x < kLeftMargin) {
    arc_alpha = Interp(last_loc_.x, kLeftMargin / 2, kLeftMargin, 0, 1);
  } else if (min_x_loc_ > parent_.bounds.size.width - 1.5 * kRightMargin) {
    const float min_x = parent_.bounds.size.width - 1.5 * kRightMargin;
    arc_alpha = Interp(last_loc_.x, min_x, min_x + kRightMargin / 2, 1, 0);
  }

  if (arc_alpha > 0) {
    CGContextRef context = UIGraphicsGetCurrentContext();
    CGContextSetAlpha(context, arc_alpha);

    DrawYears(c);
    DrawMonths(c);
  }
}

void ViewfinderToolImpl::DrawYears(const Circle& c) {
  const float kMinAngle = kPi - c.theta / 2;
  const float kMaxAngle = kPi + c.theta / 2;
  const float kSpacingAngle = 0.5 / c.radius;
  CGContextRef context = UIGraphicsGetCurrentContext();

  for (std::set<WallTime>::iterator iter(years_.begin());
       iter != years_.end();
       ++iter) {
    const WallTime t = *iter;

    float begin_angle =
        AngleForPosition(c, PositionForTime(t));
    float end_angle =
        AngleForPosition(c, PositionForTime(NextYear(t)));
    if (begin_angle > kMinAngle) {
      begin_angle += kSpacingAngle;
    }
    if (end_angle < kMaxAngle) {
      end_angle -= kSpacingAngle;
    }
    if (begin_angle >= end_angle) {
      continue;
    }

    CGContextAddArc(context, c.center.x, c.center.y,
                    c.radius + kYearArcWidth / 2, begin_angle, end_angle,
                    false);
    CGContextSetRGBStrokeColor(context, 1, 1, 1, 0.5);
    CGContextSetLineWidth(context, kYearArcWidth);
    CGContextDrawPath(context, kCGPathStroke);

    // Draw the 4-digit year, falling back to the 2 digit year if necessary.
    CGContextSetRGBFillColor(context, 0, 0, 0, 0.75);
    const string s = Format("%s", WallTimeFormat("%Y", t));
    if (!DrawArcText(s, year_font_, c.center, c.radius + kYearTextOffset,
                     begin_angle, end_angle, 1.5, true)) {
      DrawArcText(s.substr(2), year_font_, c.center,
                  c.radius + kYearTextOffset, begin_angle, end_angle,
                  1, true);
    }
  }
}

void ViewfinderToolImpl::DrawMonths(const Circle& c) {
  const float kSpacingAngle = 0.5 / c.radius;
  CGContextRef context = UIGraphicsGetCurrentContext();

  const WallTime t = TimeForPosition(position());
  WallTime times[6];
  times[0] = CurrentMonth(t);
  times[1] = CurrentMonth(times[0] - 1);
  times[2] = NextMonth(times[0]);
  times[3] = CurrentMonth(times[1] - 1);
  times[4] = NextMonth(times[2]);
  times[5] = NextMonth(times[4]);
  const float angles[ARRAYSIZE(times)] = {
    AngleForPosition(c, PositionForTime(times[0])),
    AngleForPosition(c, PositionForTime(times[1])),
    AngleForPosition(c, PositionForTime(times[2])),
    AngleForPosition(c, PositionForTime(times[3])),
    AngleForPosition(c, PositionForTime(times[4])),
    AngleForPosition(c, PositionForTime(times[5])),
  };
  const Arc arcs[] = {
    Arc(angles[0] + kSpacingAngle, angles[2] - kSpacingAngle),
    Arc(angles[1] + kSpacingAngle, angles[0] - kSpacingAngle),
    Arc(angles[2] + kSpacingAngle, angles[4] - kSpacingAngle),
    Arc(angles[3] + kSpacingAngle, angles[1] - kSpacingAngle),
    Arc(angles[4] + kSpacingAngle, angles[5] - kSpacingAngle),
  };
  const float cur_angle = AngleForPosition(c, position());

  if (arcs[0].size() > 0) {
    for (int i = 0; i < ARRAYSIZE(arcs); ++i) {
      const Arc& a = arcs[i];
      if (a.begin >= a.end) {
        continue;
      }
      CGContextAddArc(context, c.center.x, c.center.y,
                      c.radius + kMonthArcWidth / 2, a.begin, a.end, false);
      float alpha = 1;
      if (cur_angle < a.begin) {
        alpha = 1 - (a.begin - cur_angle) / (2 * arcs[0].size());
      } else if (cur_angle > a.end) {
        alpha = 1 - (cur_angle - a.end) / (2 * arcs[0].size());
      }
      alpha = std::max<float>(0.35, alpha);
      CGContextSetRGBStrokeColor(context, 1, 1, 1, 0.75 * alpha);
      CGContextSetLineWidth(context, kMonthArcWidth);
      CGContextDrawPath(context, kCGPathStroke);
    }
  }

  {
    const float cur_begin = cur_angle - 1.5 * kSpacingAngle;
    const float cur_end = cur_begin + 3 * kSpacingAngle;
    CGContextAddArc(context, c.center.x, c.center.y,
                    c.radius + kYearArcWidth / 2, cur_begin, cur_end, false);
    CGContextSetRGBStrokeColor(context, 1, 0, 0, 0.75);
    CGContextSetLineWidth(context, kYearArcWidth);
    CGContextDrawPath(context, kCGPathStroke);
  }

  if (arcs[0].size() > 0) {
    for (int i = 2; i >= 0; --i) {
      const Arc& a = arcs[i];
      float alpha = 1;
      if (cur_angle < a.begin) {
        alpha = 1 - 2 * (a.begin - cur_angle) / arcs[0].size();
      } else if (cur_angle > a.end) {
        alpha = 1 - 2 * (cur_angle - a.end) / arcs[0].size();
      }
      CGContextSetRGBFillColor(context, 0, 0, 0, 0.75 * alpha);
      const string s = Format("%s", WallTimeFormat("%b", times[i]));
      DrawArcText(s, month_font_, c.center, c.radius + kMonthTextOffset,
                  a.begin, a.end, 1, false);
    }
  }
}

void ViewfinderToolImpl::DrawEpisodes(const Circle& c) {
  const Interval interval = GetInterval();
  bool update_positions = false;

  for (int i = 0; i < episodes_.size(); ++i) {
    EpisodeInfo& e = episodes_[i];
    if (e.location.empty()) {
      const Placemark* p = state_->photo_manager()->GetPlacemark(e.photo_id);
      if (!p) {
        continue;
      }
      // TODO(pmattis): Grab the location formatting from viewfinder.py.
      e.location = p->locality();
      if (e.location.empty()) {
        continue;
      }
      update_positions = true;
    }
  }

  if (update_positions) {
    for (int i = 0; i < episodes_.size(); ++i) {
      EpisodeInfo& e = episodes_[i];
      if (e.location.empty()) {
        continue;
      }

      float p = e.position;
      int j, n = 1;

      for (j = i + 1; j < episodes_.size(); ++j) {
        const EpisodeInfo& o = episodes_[j];
        if (o.location.empty()) {
          continue;
        }
        if (o.location != e.location) {
          break;
        }
        p += o.position;
        n += 1;
      }

      p /= n;
      for (int k = i; k < j; ++k) {
        episodes_[k].combined_position = p;
      }
      i = j - 1;
    }
  }

  float episode_alpha = 1;
  if (last_loc_.x < kLeftMargin) {
    episode_alpha = Interp(last_loc_.x, kLeftMargin / 2, kLeftMargin, 0, 1);
  } else if (min_x_loc_ > parent_.bounds.size.width - 1.5 * kRightMargin) {
    const float min_x = parent_.bounds.size.width - 1.5 * kRightMargin;
    episode_alpha = Interp(last_loc_.x, min_x, min_x + kRightMargin / 2, 1, 0);
  }

  if (episode_alpha > 0) {
    const float kMinAngle = kPi - c.theta / 2;
    const float kMaxAngle = kPi + c.theta / 2;
    CGContextRef context = UIGraphicsGetCurrentContext();

    for (int i = 0; i < episodes_.size(); ++i) {
      EpisodeInfo& e = episodes_[i];
      if (e.location.empty() ||
          e.position < interval.first || e.position > interval.second) {
        continue;
      }

      // Skip over any episodes that have the same position and location.
      for (int j = i + 1; j < episodes_.size(); ++j) {
        const EpisodeInfo& o = episodes_[j];
        if (o.location.empty()) {
          continue;
        }
        if (o.combined_position != e.combined_position ||
            o.location != e.location) {
          break;
        }
        i = j;
      }

      const float p = e.combined_position;
      const float a = AngleForPosition(c, p);
      if (a <= kMinAngle || a >= kMaxAngle) {
        continue;
      }

      const float d = std::min<float>(
          fabs(p - cur_pos_),
          fabs(p - (cur_pos_ + parent_.frame.size.height))) / max_pos_;
      if (d > 0.5) {
        continue;
      }

      CGContextSaveGState(context);
      CGContextSetRGBFillColor(context, 1, 1, 1, 1);
      CGContextSetAlpha(context, episode_alpha * std::max<float>(0, 1 - d));
      CGContextSetTextDrawingMode(context, kCGTextFill);
      NSString* text = NewNSString(e.location);
      const CGSize size = [text sizeWithFont:font_];
      CGPoint pt = c.arc_coords(a);
      pt.y -= size.height / 2;

      // Ensure the top-left and bottom-left corner of the text lies within the
      // arc.
      const float top_left_y = pt.y - c.center.y;
      const float top_left_x = c.center.x - sqrt(
          c.radius * c.radius - top_left_y * top_left_y);
      const float bottom_left_y = pt.y + size.height - c.center.y;
      const float bottom_left_x = c.center.x - sqrt(
          c.radius * c.radius - bottom_left_y * bottom_left_y);
      pt.x = 1 + std::max(top_left_x, bottom_left_x);

      const float s = std::max<float>(0.5, 1 - d);
      CGContextTranslateCTM(context, pt.x, pt.y);
      CGContextScaleCTM(context, s, s);
      [text drawAtPoint:CGPointMake(0, 0) withFont:font_];
      CGContextRestoreGState(context);
    }
  }
}

void ViewfinderToolImpl::AdjustPosition(const CGPoint& new_loc) {
  cur_pos_ += Delta(new_loc);
  last_loc_ = new_loc;
  min_x_loc_ = std::min(min_x_loc_, last_loc_.x);

  const CGPoint last_loc = TransformPoint(last_loc_);
  const float interval = tracking_height() *
      (roc_max_ + roc_slope_ * last_loc.x);
  const float y_ratio = last_loc.y / tracking_height();

  cur_pos_ = std::max<float>(
      cur_pos_, min_pos_ - interval * 0.1 + y_ratio * interval);
  cur_pos_ = std::min<float>(
      cur_pos_, max_pos_ + interval * 0.1 - (1.0 - y_ratio) * interval);
}

float ViewfinderToolImpl::Delta(const CGPoint& p) const {
  const CGPoint last_loc = TransformPoint(last_loc_);
  const CGPoint new_loc = TransformPoint(p);
  const CGPoint delta_loc = CGPointMake(
      new_loc.x - last_loc.x,
      new_loc.y - last_loc.y);
  if (fabs(delta_loc.y) < 0.00001) {
    // No integration necessary
    return 0;
  }

  // We perform the delta calculation using doubles to avoid any precision
  // problems if delta_loc.y is very small.
  const double m = delta_loc.x / delta_loc.y;
  const double new_val = Integral(last_loc, new_loc.y, m);
  const double old_val = Integral(last_loc, last_loc.y, m);
  return new_val - old_val;
}

double ViewfinderToolImpl::Integral(
    const CGPoint& last_loc, double y, double m) const {
  const double a = roc_max_;
  const double b = roc_slope_;
  return 0.5 * y * (2 * a + b * (2 * last_loc.x + m * (y - 2 * last_loc.y)));
}

ViewfinderToolImpl::Interval ViewfinderToolImpl::GetInterval() const {
  const CGPoint last_loc = TransformPoint(last_loc_);
  const float interval = tracking_height() *
      (roc_max_ + roc_slope_ * last_loc.x);
  const float y_ratio = last_loc.y / tracking_height();
  return Interval(
      std::max<float>(
          min_tracking_pos_, cur_pos_ - y_ratio * interval),
      std::min<float>(
          max_tracking_pos_, cur_pos_ + (1.0 - y_ratio) * interval));
}

ViewfinderToolImpl::Circle ViewfinderToolImpl::GetCircle(const CGPoint& p) const {
  // Gets the circle (center, radius) that goes through the two endpoints of
  // the current time extent (p.x) and just touches the left edge of the
  // screen. Also computes the degrees (in radians) of the small arc through
  // the three points.
  const float x = std::max<float>(
      kArcWidth + 1,
      std::min<float>(parent_.bounds.size.width - kLeftMargin - kRightMargin,
                      p.x - kLeftMargin));
  // Coordinate at the top of the screen.
  const float a = x;
  const float b = 0;
  // Coordinate at the bottom of the screen.
  const float e = x;
  const float f = parent_.frame.size.height;
  // Coordinate at the center of the left edge of the screen.
  const float c = kArcWidth;
  const float d = (f - b) / 2;
  const float k = ((a*a+b*b)*(e-c) + (c*c+d*d)*(a-e) + (e*e+f*f)*(c-a)) /
      (2*(b*(e-c)+d*(a-e)+f*(c-a)));
  const float h = ((a*a+b*b)*(f-d) + (c*c+d*d)*(b-f) + (e*e+f*f)*(d-b)) /
      (2*(a*(f-d)+c*(b-f)+e*(d-b)));
  const float rsqr = (a-h)*(a-h)+(b-k)*(b-k);
  const float theta = acosf(((a-h)*(e-h)+(b-k)*(f-k)) / rsqr);
  return Circle(CGPointMake(h, k), sqrtf(rsqr), theta);
}

CGPoint ViewfinderToolImpl::TransformPoint(const CGPoint& p) const {
  const CGSize s = parent_.bounds.size;
  const float x = s.width - p.x - kRightMargin;
  const float y = p.y - kTopMargin;
  return CGPointMake(
      std::min<float>(s.width - kLeftMargin - kRightMargin,
                      std::max<float>(0, x)),
      std::min<float>(s.height - kTopMargin - kBottomMargin,
                      std::max<float>(0, y)));
}

WallTime ViewfinderToolImpl::TimeForPosition(float p) const {
  std::vector<EpisodeInfo>::const_iterator iter = std::lower_bound(
      episodes_.begin(), episodes_.end(),
      EpisodeInfo(0, p, 0, 0), EpisodeByPosition());
  if (iter == episodes_.end()) {
    --iter;
  }
  const EpisodeInfo& cur = *iter;
  if (cur.position > p) {
    if (iter != episodes_.begin()) {
      --iter;
      const EpisodeInfo& prev = *iter;
      const float r = (p - prev.position) / (cur.position - prev.position);
      return prev.timestamp + r * (cur.timestamp - prev.timestamp);
    }
  }
  return iter->timestamp;
}

float ViewfinderToolImpl::PositionForTime(WallTime t) const {
  std::vector<EpisodeInfo>::const_iterator iter = std::lower_bound(
      episodes_.begin(), episodes_.end(),
      EpisodeInfo(t, 0, 0, 0), EpisodeByTime());
  if (iter == episodes_.end()) {
    --iter;
  }
  const EpisodeInfo& cur = *iter;
  if (cur.timestamp < t) {
    if (iter != episodes_.begin()) {
      --iter;
      const EpisodeInfo& prev = *iter;
      const float r = (t - cur.timestamp) / (prev.timestamp - cur.timestamp);
      return cur.position + r * (prev.position - cur.position);
    }
  }
  // Extrapolate based on the beginning and ending timestamps and positions.
  const float extrapolated = min_tracking_pos_ + (t - max_time_) *
      (max_tracking_pos_ - min_tracking_pos_) / (min_time_ - max_time_);
  return std::min(max_tracking_pos_, std::max(min_tracking_pos_, extrapolated));
}

float ViewfinderToolImpl::PositionForAngle(const Circle& c, float radians) const {
  return cur_pos_ + Delta(c.arc_coords(radians));
}

float ViewfinderToolImpl::AngleForPosition(const Circle& c, float p) const {
  float s = kPi - c.theta / 2;
  float e = s + c.theta;
  if (p <= min_tracking_pos_) {
    return e;
  } else if (p >= max_tracking_pos_) {
    return s;
  }
  while (fabs(e - s) * c.radius > 0.1) {
    const float m = s + (e - s) / 2;
    const float p_m = PositionForAngle(c, m);
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

float ViewfinderToolImpl::tracking_width() const {
  return parent_.bounds.size.width - kLeftMargin - kRightMargin;
}

float ViewfinderToolImpl::tracking_height() const {
  return parent_.bounds.size.height - kTopMargin - kBottomMargin;
}


@interface ViewfinderTool (internal)
- (void)showTouchArea;
- (void)hideTouchArea;
@end  // ViewfinderTool (internal)

@implementation ViewfinderTool

- (id)initWithState:(AppState*)state {
  if (self = [super init]) {
    state_ = state;

    self.backgroundColor = [UIColor clearColor];
    self.autoresizesSubviews = YES;
    self.autoresizingMask =
        UIViewAutoresizingFlexibleWidth |
        UIViewAutoresizingFlexibleHeight;

    touch_area_ = [UIView new];
    [touch_area_ setUserInteractionEnabled:NO];
    [touch_area_ setBackgroundColor:MakeUIColor(0, 0, 0, 0.35)];
    [touch_area_ layer].borderWidth = 1;
    [touch_area_ layer].borderColor = MakeUIColor(1, 1, 1, 0.2).CGColor;
    [touch_area_ layer].cornerRadius = 19;
    [touch_area_ setHidden:YES];
    [self addSubview:touch_area_];

    impl_.reset(new ViewfinderToolImpl(state_, self));
  }
  return self;
}

- (void)drawRect:(CGRect)rect {
  [super drawRect:rect];
  impl_->DrawRect(rect);
}

- (void)layoutSubviews {
  [super layoutSubviews];
  CGRect f = self.bounds;
  f.origin.x = f.size.width - kRightMargin;
  f.size.width = kRightMargin - 2;
  f.origin.y = 2;
  f.size.height = f.size.height - 4;
  [touch_area_ setFrame:f];
}

- (BOOL)pointInside:(CGPoint)p
          withEvent:(UIEvent*)event {
  if (self.hidden || !self.enabled) {
    return NO;
  }
  if (p.x >= (self.bounds.size.width - kRightMargin)) {
    return YES;
  }
  return NO;
}

- (BOOL)beginTrackingWithTouch:(UITouch*)touch
                     withEvent:(UIEvent*)event {
  begin_time_ = touch.timestamp;
  [self hideTouchArea];
  impl_->BeginTracking([touch locationInView:self]);
  begin_.Run();
  return YES;
}

- (BOOL)continueTrackingWithTouch:(UITouch*)touch
                        withEvent:(UIEvent*)event {
  impl_->ContinueTracking([touch locationInView:self]);
  update_.Run();
  return YES;
}

- (void)endTrackingWithTouch:(UITouch*)touch
                   withEvent:(UIEvent*)event {
  if (touch.timestamp - begin_time_ < 0.2) {
    [self cancelTrackingWithEvent:event];
  } else {
    [self showTouchArea];
    impl_->EndTracking([touch locationInView:self]);
    end_.Run();
  }
}

- (void)cancelTrackingWithEvent:(UIEvent*)event {
  [self showTouchArea];
  impl_->CancelTracking();
  cancel_.Run();
}

- (CallbackSet*)begin {
  return &begin_;
}

- (CallbackSet*)end {
  return &end_;
}

- (CallbackSet*)cancel {
  return &cancel_;
}

- (CallbackSet*)update {
  return &update_;
}

- (float)position {
  return impl_->position();
}

- (float)opacity {
  return impl_->opacity();
}

- (void)setEpisodes:(const vector<EpisodeInfo>&)episodes {
  impl_->SetEpisodes(episodes);
}

- (void)showTouchArea {
  // [UIView animateWithDuration:0.2
  //                       delay:0
  //                     options:UIViewAnimationOptionBeginFromCurrentState
  //                  animations:^{
  //     [touch_area_ setAlpha:1.0];
  //   }
  //                completion:NULL];
}

- (void)hideTouchArea {
  // [UIView animateWithDuration:0.2
  //                       delay:0.2
  //                     options:UIViewAnimationOptionBeginFromCurrentState
  //                  animations:^{
  //     [touch_area_ setAlpha:0.0];
  //   }
  //                completion:NULL];
}

@end  // ViewfinderTool
