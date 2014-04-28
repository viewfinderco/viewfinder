// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <CoreText/CoreText.h>
#import <UIKit/UIKit.h>
#import "Callback.h"
#import "Placemark.pb.h"
#import "ScopedRef.h"

class AppState;

struct EpisodeInfo {
   EpisodeInfo(WallTime t, float p, int64_t i, int c)
      : timestamp(t),
        position(p),
        combined_position(0),
        photo_id(i),
        count(c) {
  }
  WallTime timestamp;
  float position;
  float combined_position;
  int64_t photo_id;
  int count;
  string location;
};

class ViewfinderToolImpl {
  struct Circle {
    Circle(const CGPoint& c, float r, float t)
        : center(c),
          radius(r),
          theta(t) {
    }

    CGPoint arc_coords(float radians) const {
      return CGPointMake(
          center.x + radius * cosf(radians),
          center.y + radius * sinf(radians));
    }

    CGPoint center;
    float radius;
    float theta;
  };

  typedef std::pair<float, float> Interval;

 public:
  ViewfinderToolImpl(AppState* state, UIView* parent);
  ~ViewfinderToolImpl();

  void DrawRect(const CGRect& r);
  void SetEpisodes(const vector<EpisodeInfo>& episodes);
  void BeginTracking(const CGPoint& p);
  void ContinueTracking(const CGPoint& p);
  void EndTracking(const CGPoint& p);
  void CancelTracking();

  float position() const {
    return std::min(max_pos_, std::max(min_pos_, cur_pos_));
  }
  float opacity() const { return cur_opacity_; }

 private:
  void Update();
  void DrawDates(const Circle& c);
  void DrawYears(const Circle& c);
  void DrawMonths(const Circle& c);
  void DrawEpisodes(const Circle& c);
  void AdjustPosition(const CGPoint& p);
  float Delta(const CGPoint& p) const;
  double Integral(const CGPoint& last_loc, double y, double m) const;
  Interval GetInterval() const;
  Circle GetCircle(const CGPoint& p) const;
  CGPoint TransformPoint(const CGPoint& p) const;
  WallTime TimeForPosition(float p) const;
  float PositionForTime(WallTime t) const;
  float PositionForAngle(const Circle& c, float radians) const;
  float AngleForPosition(const Circle& c, float p) const;
  float tracking_width() const;
  float tracking_height() const;

 private:
  AppState* const state_;
  UIView* const parent_;
  UIFont* const font_;
  ScopedRef<CTFontRef> year_font_;
  ScopedRef<CTFontRef> month_font_;
  bool tracking_;
  float min_pos_;
  float min_tracking_pos_;
  float max_pos_;
  float max_tracking_pos_;
  float cur_pos_;
  float cur_opacity_;
  float roc_max_;
  float roc_slope_;
  WallTime min_time_;
  WallTime max_time_;
  CGPoint last_loc_;
  float min_x_loc_;
  vector<EpisodeInfo> episodes_;
  std::set<WallTime> years_;
};

@interface ViewfinderTool : UIControl {
 @private
  AppState* state_;
  CallbackSet begin_;
  CallbackSet end_;
  CallbackSet cancel_;
  CallbackSet update_;
  UIView* touch_area_;
  ScopedPtr<ViewfinderToolImpl> impl_;
  WallTime begin_time_;
}

@property (nonatomic, readonly) CallbackSet* begin;
@property (nonatomic, readonly) CallbackSet* end;
@property (nonatomic, readonly) CallbackSet* cancel;
@property (nonatomic, readonly) CallbackSet* update;
@property (nonatomic, readonly) float position;
@property (nonatomic, readonly) float opacity;

- (id)initWithState:(AppState*)state;
- (void)setEpisodes:(const vector<EpisodeInfo>&)episodes;

@end  // ViewfinderTool

// local variables:
// mode: objc
// end:
