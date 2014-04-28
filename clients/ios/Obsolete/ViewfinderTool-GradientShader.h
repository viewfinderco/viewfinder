// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <set>
#import <tr1/unordered_map>
#import <CoreText/CoreText.h>
#import <UIKit/UIKit.h>
#import "ScopedPtr.h"
#import "ScopedRef.h"
#import "Vector.h"
#import "WallTime.h"

//#define LINEAR_INTEGRATION
#define EXPONENTIAL_INTEGRATION

class DecayingVelocity;
class GLMutableTexture2D;
class GLProgram;
class PhysicsModel;

@class EpisodeTextLayer;
@class GLLayer;
@class PositionIndicatorLayer;
@class ViewfinderTool;

struct ViewfinderLayerData {
  ViewfinderLayerData()
      : layer(NULL),
        angle(0) {
  }
  EpisodeTextLayer* layer;
  float angle;
};

typedef std::tr1::unordered_map<int, ViewfinderLayerData> ViewfinderLayerCache;

@protocol ViewfinderToolEnv
- (void)viewfinderBegin:(ViewfinderTool*)viewfinder;
- (void)viewfinderUpdate:(ViewfinderTool*)viewfinder position:(float)position;
- (void)viewfinderFinish:(ViewfinderTool*)viewfinder;
- (void)viewfinderTapAtPoint:(ViewfinderTool*)viewfinder point:(CGPoint)p;
- (bool)viewfinderTimeAscending;
- (bool)viewfinderElasticDial;
- (CGRect)viewfinderVisibleBounds:(ViewfinderTool*)viewfinder;
- (int)viewfinderNumGroups:(ViewfinderTool*)viewfinder;
- (std::pair<int, int>)viewfinderGroups:(ViewfinderTool*)viewfinder;
- (std::pair<int, int>)viewfinderVisibleGroups:(ViewfinderTool*)viewfinder;
- (CGRect)viewfinderGroupBounds:(ViewfinderTool*)viewfinder index:(int)i;
- (WallTime)viewfinderGroupTimestamp:(ViewfinderTool*)viewfinder index:(int)i;
- (string)viewfinderGroupTitle:(ViewfinderTool*)viewfinder index:(int)i;
- (string)viewfinderGroupShortTitle:(ViewfinderTool*)viewfinder index:(int)i;
- (string)viewfinderGroupSubtitle:(ViewfinderTool*)viewfinder index:(int)i;
- (string)viewfinderGroupShortSubtitle:(ViewfinderTool*)viewfinder index:(int)i;
- (float)viewfinderGroupVolumeWeight:(ViewfinderTool*)viewfinder index:(int)i;
- (float)viewfinderGroupLocationWeight:(ViewfinderTool*)viewfinder index:(int)i;
- (double)viewfinderGroupLocationDistance:(ViewfinderTool*)viewfinder index:(int)i;
- (bool)viewfinderIsSubgroup:(ViewfinderTool*)viewfinder index:(int)i;
- (string)viewfinderFormatPositionIndicator:(WallTime)t;
- (string)viewfinderFormatCurrentTime:(WallTime)t;
- (string)viewfinderFormatOuterTime:(WallTime)t;
- (string)viewfinderFormatInnerTime:(WallTime)t;
- (WallTime)viewfinderCurrentOuterTime:(WallTime)t;
- (WallTime)viewfinderCurrentInnerTime:(WallTime)t;
- (WallTime)viewfinderNextOuterTime:(WallTime)t;
- (WallTime)viewfinderNextInnerTime:(WallTime)t;
@end  // ViewfinderToolEnv

@interface ViewfinderTool : UIControl<UIGestureRecognizerDelegate> {
 @private
  id<ViewfinderToolEnv> env_;
  ScopedRef<CTFontRef> title_font_;
  ScopedRef<CTFontRef> subtitle_font_;
  float pct_active_;
  int start_group_;
  int end_group_;
  float min_pos_;
  float min_tracking_pos_;
  float max_pos_;
  float max_tracking_pos_;
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
  std::vector<float> positions_;
  std::vector<float> heights_;
  std::vector<WallTime> timestamps_;
  std::vector<float> distances_;
  std::vector<std::pair<float,int> > weights_;
  UILongPressGestureRecognizer* long_press_recognizer_;
  UITapGestureRecognizer* single_tap_recognizer_;
  UITapGestureRecognizer* double_tap_recognizer_;
  UIPinchGestureRecognizer* pinch_recognizer_;
  UISwipeGestureRecognizer* left_swipe_recognizer_;
  UISwipeGestureRecognizer* right_swipe_recognizer_;
  GLLayer* arc_;
  CAShapeLayer* scroll_indicators_[4];
  PositionIndicatorLayer* position_indicator_;

  ViewfinderLayerCache layer_cache_;

  // OpenGL state.
  enum {
    A_POSITION,
    A_TEX_COORD,
    A_COLOR,
  };

  ScopedPtr<GLProgram> gradient_shader_;
  GLint u_gradient_mvp_;
  GLint u_gradient_radius1_;
  GLint u_gradient_radius2_;
  GLint u_gradient_color_;
  ScopedPtr<GLProgram> solid_shader_;
  GLint u_solid_mvp_;
  ScopedPtr<GLProgram> texture_shader_;
  GLint u_texture_mvp_;
  GLint u_texture_texture_;

  // A map from glyph (character) to glyph info (location in glyph texture.
  struct GlyphInfo {
    NSString* str;
    CGSize size;
    CGSize scaled_size;
    float tx_start;
    float tx_end;
    float ty_start;
    float ty_end;
  };

  std::map<std::pair<UIFont*, int>, GlyphInfo> glyphs_;
  ScopedPtr<GLMutableTexture2D> glyph_tex_;

  struct VisibleGroup {
    int index;
    CGPoint pt;
    float alpha;

    VisibleGroup()
        : index(0), alpha(0) {}
    VisibleGroup(int i, const CGPoint& p, float a)
        : index(i), pt(p), alpha(a) {}
  };
  std::map<float, VisibleGroup> visible_;

  enum ViewfinderMode {
    VF_INACTIVE,          // Viewfinder is fully stowed and not visible
    VF_SCROLLING,         // The UIScrollView of photos is scrolling or was recently
    VF_ACTIVATING,        // Animation of rubberband activation
    VF_TRACKING,          // Tracking touch position
    VF_JUMP_SCROLLING,    // Tracking touch position at max zoom
    VF_RELEASING,         // Decelerate moving arc
    VF_MARGIN_SCROLLING,  // Tracking in the vertical margins (top/bottom)
    VF_ACTIVATING_JS,     // Activating jump scroll
    VF_RELEASING_JS,      // Deactivating jump scroll back to either inactive or tracking
    VF_SCALING,           // Tracking in rigid dial mode to change the arc curvature
    VF_PINCHING,          // Changing the arc curvature
    VF_STOWING,           // Stowing the viewfinder
    VF_ZEROING,           // Zeroing in on an episode
    VF_ZOOM_ZEROING,      // Zeroing in and then zooming into an episode
    VF_ZOOMING,           // Zooming into an epsiode
    VF_BOUNCING,          // Bouncing out of upper and lower scroll bounds.
    VF_QUIESCENT,         // No longer tracking, but visible and not animating
  };
  ViewfinderMode mode_;
  ViewfinderMode orig_mode_;
  bool needs_finish_;

  enum Gesture {
    GESTURE_NONE,
    GESTURE_TRACK,
    GESTURE_RELEASE,
    GESTURE_LONG_PRESS,
    GESTURE_SINGLE_TAP,
    GESTURE_DOUBLE_TAP,
    GESTURE_PINCH,
    GESTURE_SWIPE_LEFT,
    GESTURE_SWIPE_RIGHT,
    GESTURE_BOUNCE,
    GESTURE_CLOSE,
    GESTURE_TRANSITION,
  };

  ScopedPtr<DecayingVelocity> pan_velocity_;
  ScopedPtr<DecayingVelocity> location_velocity_;
  ScopedPtr<DecayingVelocity> scroll_velocity_;
  WallTime tracking_start_;
  float pinch_start_x_;
  float pinch_scale_;
  int target_index_;

  ScopedPtr<PhysicsModel> tracking_model_;
  ScopedPtr<PhysicsModel> location_model_;
  bool dispatched_;
  bool needs_redraw_;

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

@property (readonly) float inactiveWidth;
@property (readonly) float groupHeaderHeight;

- (id)initWithEnv:(id<ViewfinderToolEnv>)env;
- (void)initialize;
- (void)close:(bool)animate;

@end  // ViewfinderTool

// local variables:
// mode: objc
// end:
