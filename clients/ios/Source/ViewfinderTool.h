// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <set>
#import <unordered_map>
#import <CoreText/CoreText.h>
#import "CompositeTextLayers.h"
#import "GLState.h"
#import "ScopedPtr.h"
#import "ScopedRef.h"
#import "UIStyle.h"
#import "Vector.h"
#import "WallTime.h"

//#define LINEAR_INTEGRATION
#define EXPONENTIAL_INTEGRATION

class UIAppState;
class DecayingVelocity;
class PhysicsModel;

@class DialUIPanGestureRecognizer;
@class PositionIndicatorLayer;
@class ViewfinderTool;

extern const float kViewfinderToolActivationSecs;

struct ViewfinderLayerData {
  ViewfinderLayerData()
      : layer(NULL),
        alpha(1),
        angle(0) {
  }
  CompositeTextLayer* layer;
  float alpha;
  float angle;
};

enum ViewfinderMode {
  VF_INACTIVE,          // Viewfinder is fully stowed and not visible
  VF_SCROLLING,         // The UIScrollView of photos is scrolling or was recently
  VF_ACTIVATING,        // Animation of dial/timeline activation
  VF_TRACKING,          // Tracking touch position
  VF_JUMP_SCROLLING,    // Tracking touch position at max zoom
  VF_RELEASING,         // Decelerate after tracking
  VF_PINCHING,          // Changing the zoom level via pinch gesture
  VF_STOWING,           // Stowing the viewfinder
  VF_ZEROING,           // Zeroing in on an episode
  VF_ZOOMING,           // Zooming into an epsiode
  VF_BOUNCING,          // Bouncing out of upper and lower scroll bounds
  VF_QUIESCENT,         // No longer tracking, but visible and not animating
};

typedef std::unordered_map<int, ViewfinderLayerData> ViewfinderLayerCache;
typedef std::unordered_set<WallTime> TimestampSet;

struct ViewfinderRowInfo {
  ViewfinderRowInfo(WallTime t = 0, float w = 0, bool u = false)
      : timestamp(t),
        weight(w),
        unviewed(u) {
  }
  WallTime timestamp;
  float weight;
  bool unviewed;
};

@protocol ViewfinderToolEnv
- (void)viewfinderBegin:(ViewfinderTool*)viewfinder;
- (void)viewfinderUpdate:(ViewfinderTool*)viewfinder
                position:(float)position
                animated:(BOOL)animated;
- (void)viewfinderFinish:(ViewfinderTool*)viewfinder;
- (bool)viewfinderAlive:(ViewfinderTool*)viewfinder;
- (bool)viewfinderTimeAscending;
- (int)viewfinderNumRows:(ViewfinderTool*)viewfinder;
- (std::pair<int, int>)viewfinderRows:(ViewfinderTool*)viewfinder;
- (CGRect)viewfinderRowBounds:(ViewfinderTool*)viewfinder index:(int)i;
- (CGPoint)viewfinderTextOffset:(ViewfinderTool*)viewfinder index:(int)i;
- (CompositeTextLayer*)viewfinderTextLayer:(ViewfinderTool*)viewfinder
                                     index:(int)index
                                  oldLayer:(CompositeTextLayer*)old_layer
                             takeOwnership:(bool)owner;
- (ViewfinderRowInfo)viewfinderRowInfo:(ViewfinderTool*)viewfinder index:(int)i;
- (bool)viewfinderIsSubrow:(ViewfinderTool*)viewfinder index:(int)i;
- (bool)viewfinderDisplayPositionIndicator:(ViewfinderTool*)viewfinder;
- (string)viewfinderFormatPositionIndicator:(ViewfinderTool*)viewfinder
                                atTimestamp:(WallTime)t;
- (string)viewfinderFormatCurrentTime:(ViewfinderTool*)viewfinder
                          atTimestamp:(WallTime)t;
- (float)viewfinderTimeScaleSeconds:(ViewfinderTool*)viewfinder;
- (UIEdgeInsets)viewfinderContentInsets:(ViewfinderTool*)viewfinder;
@end  // ViewfinderToolEnv

@interface ViewfinderTool : UIView<UIGestureRecognizerDelegate> {
 @private
  __weak id<ViewfinderToolEnv> env_;
  UIAppState* state_;
  bool initialized_;
  float pct_active_;
  float pct_quiescent_;
  WallTime quiescent_start_time_;
  float pct_scrolling_;
  WallTime scrolling_start_time_;
  int start_row_;
  int end_row_;
  float time_scale_;
  float min_pos_;
  float min_tracking_pos_;
  float max_pos_;
  float max_tracking_pos_;
  float tracking_total_;
  float max_row_height_;
  float cur_pos_;
  float roc_min_;
  float roc_max_;
#if defined(LINEAR_INTEGRATION)
  float roc_slope_;
#elif defined(EXPONENTIAL_INTEGRATION)
  double beta_;
  double alpha_;
#endif
  WallTime min_time_;
  WallTime max_time_;
  CGPoint cur_loc_;
  CGPoint touch_loc_;
  std::set<WallTime> outer_times_;
  std::set<WallTime> inner_times_;
  std::vector<float> positions_;
  std::vector<int> ranks_;
  std::vector<WallTime> timestamps_;
  std::vector<float> weights_;
  std::vector<bool> unviewed_;
  TimestampSet new_timestamps_;
  DialUIPanGestureRecognizer* pan_recognizer_;
  UILongPressGestureRecognizer* long_press_recognizer_;
  UILongPressGestureRecognizer* activation_recognizer_;
  UITapGestureRecognizer* single_tap_recognizer_;
  UIPinchGestureRecognizer* pinch_recognizer_;
  UISwipeGestureRecognizer* left_swipe_recognizer_;
  UISwipeGestureRecognizer* right_swipe_recognizer_;
  CALayer* scroll_bar_;
  CAShapeLayer* location_indicator_;
  PositionIndicatorLayer* position_indicator_;
  ViewfinderLayerCache layer_cache_;
  CADisplayLink* display_link_;

  // OpenGL state.
  GLState* gl_;

  struct VisibleRow {
    int index;
    CGPoint pt;
    float alpha;

    VisibleRow()
        : index(0), alpha(0) {}
    VisibleRow(int i, const CGPoint& p, float a)
        : index(i), pt(p), alpha(a) {}
  };
  std::map<float, VisibleRow> visible_;

  enum ViewfinderShape {
    SHAPE_DIAL,
    SHAPE_TIMELINE,
    SHAPE_TIMEARC,
  };
  ViewfinderShape shape_;
  bool can_activate_;
  bool jump_scroll_timeline_;
  bool elastic_;  // only applies to dial; timeline/arc always elastic

  ViewfinderMode mode_;
  bool needs_finish_;

  enum Gesture {
    GESTURE_NONE,
    GESTURE_TRACK,
    GESTURE_RELEASE,
    GESTURE_LONG_PRESS,
    GESTURE_ACTIVATION,
    GESTURE_SINGLE_TAP,
    GESTURE_PINCH,
    GESTURE_SWIPE_LEFT,
    GESTURE_SWIPE_RIGHT,
    GESTURE_BOUNCE,
    GESTURE_OPEN,
    GESTURE_CLOSE,
    GESTURE_TRANSITION,
  };

  CGPoint pan_velocity_;
  ScopedPtr<DecayingVelocity> scroll_velocity_;
  bool tracking_;
  WallTime tracking_start_;
  float pinch_start_x_;
  float pinch_scale_;
  int target_index_;

  ScopedPtr<PhysicsModel> tracking_model_;
  ScopedPtr<PhysicsModel> location_model_;

  struct Circle {
    Circle()
        : radius(0),
          theta(0),
          degenerate(false) {
    }
    Circle(const CGPoint& c, double r, double t, bool d=false)
        : center(c),
          radius(r),
          theta(t),
          degenerate(d) {
    }

    CGPoint arc_coords(double radians, double delta=0) const {
      return CGPointMake(
          center.x + (radius + delta) * cos(radians),
          center.y + (radius + delta) * sin(radians));
    }

    double angle_for_y(double y, double x) const {
      if (y < center.y - radius) {
        return kPi / 2;
      } else if (y > center.y + radius) {
        return -kPi / 2;
      }
      const double angle = asin((y - center.y) / radius);
      return (x < center.x) ? kPi - angle : angle;
    }

    CGPoint center;
    double radius;
    double theta;
    bool degenerate;
  };

  Circle circle_;
}

@property (nonatomic, readonly) float inactiveWidth;
@property (nonatomic, readonly) float rowHeaderHeight;
@property (nonatomic, readonly) float leftActivationMargin;
@property (nonatomic, readonly) float rightActivationMargin;
@property (nonatomic, readonly) ViewfinderMode mode;
// True if viewfinder is opening or has been opened; false if
// closing or has been closed.
@property (nonatomic, readonly) bool active;
@property (nonatomic, readonly) bool canActivate;

- (id)initWithEnv:(id<ViewfinderToolEnv>)env appState:(UIAppState*)state;
- (void)addGestureRecognizers:(UIView*)event_view;
- (void)removeGestureRecognizers:(UIView*)event_view;
- (void)initialize:(float)scroll_offset;
- (void)invalidate:(float)scroll_offset;
- (void)open;
- (void)close:(bool)animate;
- (void)redraw;

@end  // ViewfinderTool

// local variables:
// mode: objc
// end:
