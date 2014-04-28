// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <dispatch/dispatch.h>
#import <QuartzCore/QuartzCore.h>
#import "Appearance.h"
#import "AppState.h"
#import "DB.h"
#import "Logging.h"
#import "Vector.h"
#import "ValueUtils.h"
#import "WheelMenu.h"

namespace {

enum {
  HOME = 1,
  CAMERA = 2,
  SETTINGS = 3,
  DEVELOPER = 4,
};

const string kAnimationScaleKey = AppState::metadata_key("wheel_animation_scale");
const string kWheelPosKey = AppState::metadata_key("wheel_pos");

const float kOuterRadius = 100;
const float kInnerRadius = 6;
const float kClickableRadius = 120;

const float kNotchLength = 3;
const float kNotchAngle = 4 * kPi / 180;
const float kNotchSpacingAngle = 12 * kPi / 180;

const float kSlotWidth = 10;
const float kSlotHeight = 5;
const float kSlotRadius = 84;
const int kNumSlots = 9;
const float kSlotAngle = (2 * kPi) / kNumSlots;

const float kBoxRadius = 58;
const float kBoxWidth = 26;
const float kBoxHeight = 24;
const float kBoxCornerRadius = 5;
const int kNumBoxes = 9;
const float kBoxAngle = (2 * kPi) / kNumBoxes;

const float kExpandDuration = 0.45;
const float kExpandScale = 310 / 200.0;
const float kExpandOffset = 20;
const float kShrinkDuration = 0.4;
const float kShrunkScale = 0.5;
const float kShrunkOffset = -5;
const float kShrunkAngle = 2 * kPi / 3;
const float kShudderAngle = 10 * kPi / 180;
const float kShrunkOpacity = 0.8;
const float kMoveDuration = 0.4;

const float kLeftAngle = -kBoxAngle * 2 / 3;
const float kCenterAngle1 = 2 * kPi - kBoxAngle * 7 / 4;
const float kCenterAngle2 = -kBoxAngle * 7 / 4;
const float kRightAngle = kPi * 3 / 2 - kBoxAngle * 2 / 3;

CGMutablePathRef WheelPath() {
  CGMutablePathRef path = CGPathCreateMutable();

  // Draw the outside of the wheel including the notches.
  CGPathAddArc(path, NULL, 0, 0, kOuterRadius,
               -(kNotchSpacingAngle / 2 + kNotchAngle),
               kNotchSpacingAngle / 2 + kNotchAngle,
               true);
  CGAffineTransform t =
      CGAffineTransformMakeRotation((kNotchSpacingAngle + kNotchAngle) / 2);
  CGPathAddLineToPoint(path, &t, kOuterRadius - kNotchLength, 0);
  t = CGAffineTransformMakeRotation(kNotchSpacingAngle / 2);
  CGPathAddLineToPoint(path, &t, kOuterRadius, 0);
  CGPathAddArc(path, NULL, 0, 0, kOuterRadius,
               kNotchSpacingAngle / 2, -kNotchSpacingAngle / 2,
               true);
  t = CGAffineTransformMakeRotation(-(kNotchSpacingAngle + kNotchAngle) / 2);
  CGPathAddLineToPoint(path, &t, kOuterRadius - kNotchLength, 0);
  t = CGAffineTransformMakeRotation(-kNotchSpacingAngle / 2 - kNotchAngle);
  CGPathAddLineToPoint(path, &t, kOuterRadius, 0);

  // Draw the inside of the wheel.
  CGPathMoveToPoint(path, NULL, kInnerRadius, 0);
  CGPathAddArc(path, NULL, 0, 0, kInnerRadius, 0, 2 * kPi, true);

  // Draw the slots in the outer rim.
  for (int i = 0; i < kNumSlots; ++i) {
    t = CGAffineTransformMakeRotation(kSlotAngle * i);
    CGPathAddRect(path, &t, CGRectMake(
                      kSlotRadius, -kSlotHeight / 2,
                      kSlotWidth, kSlotHeight));
  }

  // Draw the boxes.
  for (int i = 0; i < kNumBoxes; ++i) {
    const float w = kBoxWidth / 2;
    const float h = kBoxHeight / 2;
    const float r = kBoxCornerRadius;
    const CGPoint c = CGPointMake(kBoxRadius + w, 0);
    t = CGAffineTransformMakeRotation(kBoxAngle * i + kBoxAngle / 2);
    CGPathMoveToPoint(path, &t, c.x, c.y - h);
    CGPathAddArcToPoint(path, &t, c.x + w, c.y - h, c.x + w, c.y + h, r);
    CGPathAddArcToPoint(path, &t, c.x + w, c.y + h, c.x - w, c.y + h, r);
    CGPathAddArcToPoint(path, &t, c.x - w, c.y + h, c.x - w, c.y - h, r);
    CGPathAddArcToPoint(path, &t, c.x - w, c.y - h, c.x + w, c.y - h, r);
  }

  CGPathCloseSubpath(path);
  return path;
}

}  // namespace

@interface WheelMenu (internal)
- (void)expand;
- (void)shrink;
- (CGPoint)expandPosition;
- (CGPoint)shrunkPosition;
- (void)setScale:(float)v;
- (void)setAngle:(float)v;
- (void)resetTransform:(float)angle scale:(float)scale;
- (float)angleForPos:(float)wheel_pos;
- (void)updateAnimationScale;
@end  // WheelMenu (internal)

@implementation WheelMenu

- (id)initWithState:(AppState*)state {
  if (self = [super init]) {
    state_ = state;

    CALayer* shadow_layer = [CALayer layer];
    shadow_layer.shadowOffset = CGSizeMake(0, 1.5);
    shadow_layer.shadowRadius = 3.0;
    shadow_layer.shadowColor = [UIColor blackColor].CGColor;
    shadow_layer.shadowOpacity = 0.8;
    shadow_layer.zPosition = 1;
    [self.layer addSublayer:shadow_layer];

    wheel_ = [CAShapeLayer layer];
    wheel_.path = WheelPath();
    wheel_.fillColor = [UIColor whiteColor].CGColor;
    wheel_.fillRule = kCAFillRuleEvenOdd;
    [shadow_layer addSublayer:wheel_];

    struct {
      NSString* image_name;
      int tag;
    } kButtons[] = {
      { @"house.png", HOME },
      { @"camera.png", CAMERA },
      { @"gear.png", SETTINGS },
      { NULL, DEVELOPER },
    };

    buttons_ = [UIView new];
    for (int i = 0; i < kNumBoxes; ++i) {
      UIButton* b = [UIButton buttonWithType:UIButtonTypeCustom];
      float hue = kBoxAngle * (i - 2) / (2 * kPi);
      while (hue < 0) {
        hue += 1.0;
      }
      b.backgroundColor = MakeUIColorHSB(hue, 1, 1, 0.7);
      if (i < ARRAYSIZE(kButtons)) {
        if (kButtons[i].image_name) {
          UIImage* image = [UIImage imageNamed:kButtons[i].image_name];
          [b setImage:image forState:UIControlStateNormal];
          [b setImageEdgeInsets:UIEdgeInsetsMake(4, 4, 4, 4)];
          b.imageView.contentMode = UIViewContentModeScaleAspectFit;
          // Orient the image so that gravity points towards the center of the
          // wheel.
          b.imageView.transform = CGAffineTransformMakeRotation(kPi / 2);
        }
        [b setTag:kButtons[i].tag];
      }
      b.frame = CGRectMake(0, 0, kBoxWidth, kBoxHeight);
      b.transform =
          CGAffineTransformMakeRotation(kBoxAngle * (i - 2) + kBoxAngle / 2);
      CGPoint p = CGPointApplyAffineTransform(
          CGPointMake(kBoxRadius + kBoxWidth / 2, 0), b.transform);
      b.center = CGPointMake(p.x, p.y);
      b.showsTouchWhenHighlighted = YES;
      [b addTarget:self
            action:@selector(itemSelected:)
         forControlEvents:UIControlEventTouchUpInside];
      [buttons_ addSubview:b];
    }
    [self addSubview:buttons_];

    old_wheel_pos_ = wheel_pos_ = state_->db()->Get<float>(kWheelPosKey, 0.5);
    [self setAngle:[self angleForPos:wheel_pos_]];
    [self setScale:kShrunkScale];
    [self resetTransform:angle_ + kShrunkAngle scale:scale_];

    animation_scale_ = state_->db()->Get<float>(kAnimationScaleKey, 1.5);
  }
  return self;
}

- (void)layoutSubviews {
  CGPoint p;
  float opacity = 1.0;
  if (!expanded_) {
    p = [self shrunkPosition];
    opacity = kShrunkOpacity;
  } else {
    p = [self expandPosition];
  }
  buttons_.center = p;
  buttons_.layer.opacity = opacity;
  wheel_.position = p;
  wheel_.opacity = opacity;
}

- (UIView*)hitTest:(CGPoint)p
         withEvent:(UIEvent*)event {
  if (hidden_ || self.hidden || !self.enabled) {
    return NULL;
  }
  if (expanded_) {
    for (UIView* v in buttons_.subviews) {
      const CGPoint q = [v convertPoint:p fromView:self];
      UIView* u = [v hitTest:q withEvent:event];
      if (u) {
        return u;
      }
    }
  }
  if ([self pointInside:p withEvent:event]) {
    return self;
  }
  return NULL;
}

- (BOOL)pointInside:(CGPoint)p
          withEvent:(UIEvent*)event {
  if (hidden_ || self.hidden || !self.enabled) {
    return NO;
  }
  if (expanded_) {
    return true;
  }
  const float l = (Vector2f(p) - Vector2f(wheel_.position)).length();
  return l <= kClickableRadius * scale_;
}

- (BOOL)beginTrackingWithTouch:(UITouch*)touch
                     withEvent:(UIEvent*)event {
  if (!expanded_) {
    [self expand];
    tracking_ = false;
    had_selected_button_ = false;
    return YES;
  }
  tracking_ = true;

  const CGPoint p = [touch locationInView:self];
  const float l = (Vector2f(p) - Vector2f(wheel_.position)).length();
  if (l > kOuterRadius * scale_) {
    [self shrink];
    return NO;
  }

  // A click inside the inner radius will cause the will to shrink if no other
  // movement occurs.
  had_selected_button_ = (l < kInnerRadius * scale_ * 2);

  tracking_center_ = wheel_.position;
  tracking_start_ = p;
  return YES;
}

- (BOOL)continueTrackingWithTouch:(UITouch*)touch
                        withEvent:(UIEvent*)event {
  if (!tracking_) {
    const CGPoint p = [touch locationInView:self];
    const float l = (Vector2f(p) - Vector2f(wheel_.position)).length();
    if (l < kInnerRadius * scale_ * 5 || l > kOuterRadius * scale_) {
      [selected_button_ cancelTrackingWithEvent:event];
      selected_button_ = NULL;
      had_selected_button_ = true;
    } else {
      Vector2f touch_vec(Vector2f(p) - Vector2f(wheel_.position));
      touch_vec.normalize();

      UIButton* button = NULL;
      for (UIButton* v in [buttons_ subviews]) {
        const CGPoint c = [self convertPoint:v.center fromView:v.superview];
        Vector2f button_vec(Vector2f(c) - Vector2f(wheel_.position));
        button_vec.normalize();

        const float angle = fabs(acos(touch_vec.dot(button_vec)));
        if (angle <= kBoxAngle / 2) {
          button = v;
          break;
        }
      }
      if (selected_button_ != button) {
        [selected_button_ cancelTrackingWithEvent:event];
        selected_button_ = button;
        [selected_button_ beginTrackingWithTouch:touch withEvent:event];
        had_selected_button_ = true;
        return YES;
      }
    }
    if (selected_button_) {
      return [selected_button_ continueTrackingWithTouch:touch withEvent:event];
    }
    return YES;
  }

  [CATransaction begin];
  [CATransaction setValue:(id)kCFBooleanTrue forKey:kCATransactionDisableActions];

  const CGPoint p = [touch locationInView:self];
  const float delta_x = p.x - tracking_start_.x;
  if (fabs(delta_x) >= 5) {
    had_selected_button_ = false;
  }
  const float x = tracking_center_.x + delta_x;
  const float w = self.frame.size.width - 2 * kExpandOffset;
  wheel_pos_ = std::min<float>(1, std::max<float>(0, (x - kExpandOffset) / w));
  [self resetTransform:[self angleForPos:wheel_pos_] scale:scale_];

  [CATransaction commit];
  return YES;
}

- (void)endTrackingWithTouch:(UITouch*)touch
                   withEvent:(UIEvent*)event {
  if (selected_button_) {
    UIButton* b = selected_button_;
    selected_button_ = NULL;
    if (b.highlighted) {
      [b sendActionsForControlEvents:UIControlEventTouchUpInside];
    }
    [b cancelTrackingWithEvent:event];
    return;
  }
  if (had_selected_button_) {
    [self shrink];
    return;
  }
  if (!tracking_) {
    return;
  }

  [CATransaction begin];
  [CATransaction setValue:(id)kCFBooleanTrue forKey:kCATransactionDisableActions];

  const CGPoint p = [touch locationInView:self];
  const float delta_x = p.x - tracking_start_.x;
  const float x = tracking_center_.x + delta_x;
  const float w = self.frame.size.width - 2 * kExpandOffset;
  wheel_pos_ = std::min<float>(1, std::max<float>(0, (x - kExpandOffset) / w));
  const float start_pos = wheel_pos_;
  float start_angle = [self angleForPos:wheel_pos_];

  CAKeyframeAnimation* position =
      [CAKeyframeAnimation animationWithKeyPath:@"position"];
  {
    float end_pos = 0;
    if (wheel_pos_ < 0.25) {
      end_pos = 0;
    } else if (wheel_pos_ > 0.75) {
      end_pos = 1;
    } else {
      end_pos = 0.5;
    }
    Array values;
    Array times;
    for (int i = 0, n = 20; i <= n; ++i) {
      wheel_pos_ = start_pos + ((end_pos - start_pos) * i) / n;
      values.push_back([self expandPosition]);
      times.push_back(i / (2.0 * n));
    }
    wheel_pos_ = end_pos;
    position.values = values;
    position.keyTimes = times;
    position.duration = kMoveDuration * animation_scale_;
  }

  if (wheel_pos_ != old_wheel_pos_) {
    state_->db()->Put(kWheelPosKey, wheel_pos_);
    old_wheel_pos_ = wheel_pos_;
  }

  [self setAngle:[self angleForPos:wheel_pos_]];
  if (start_pos > wheel_pos_ && start_angle < angle_) {
    // The wheel is rolling to the left, make sure the angles cause a
    // counter-clockwise rotation.
    start_angle += 2 * kPi;
  } else if (start_pos < wheel_pos_ && start_angle > angle_) {
    // The wheel is rolling to the right, make sure the angles cause a
    // clockwise rotation.
    start_angle -= 2 * kPi;
  }
  const float shudder_angle = angle_ + (angle_ - start_angle) / 4;

  CAKeyframeAnimation* rotation =
      [CAKeyframeAnimation animationWithKeyPath:@"transform.rotation.z"];
  rotation.values = Array(start_angle,
                          angle_,
                          shudder_angle,
                          angle_);
  rotation.keyTimes = Array(0.0, 0.7, 0.85, 1.0);
  rotation.timingFunction =
      [CAMediaTimingFunction functionWithName:kCAMediaTimingFunctionEaseOut];
  rotation.duration = kMoveDuration * animation_scale_;

  CAAnimationGroup* animation = [CAAnimationGroup animation];
  animation.animations = Array(position, rotation);
  animation.duration = kMoveDuration * animation_scale_;
  animation.fillMode = kCAFillModeForwards;

  [buttons_.layer addAnimation:animation forKey:nil];
  [wheel_ addAnimation:animation forKey:nil];

  [CATransaction commit];
}

- (UIButton*)homeButton {
  return (UIButton*)[buttons_ viewWithTag:HOME];
}

- (UIButton*)cameraButton {
  return (UIButton*)[buttons_ viewWithTag:CAMERA];
}

- (UIButton*)settingsButton {
  return (UIButton*)[buttons_ viewWithTag:SETTINGS];
}

- (UIButton*)developerButton {
  return (UIButton*)[buttons_ viewWithTag:DEVELOPER];
}

- (void)setFrame:(CGRect)f {
  if (hidden_) {
    f = CGRectOffset(f, 0, kOuterRadius * kShrunkScale);
  }
  [super setFrame:f];
}

- (void)setHidden:(bool)hidden duration:(float)duration {
  CGPoint p = { self.center.x, self.frame.size.height / 2 };
  if (hidden) {
    p.y += kOuterRadius * kShrunkScale;
  }
  hidden_ = hidden;
  if (p.y != self.center.y) {
    [UIView animateWithDuration:duration
                          delay:0
                        options:UIViewAnimationOptionBeginFromCurrentState
                     animations:^{
        self.center = p;
      }
                     completion:NULL];
  }
}

- (void)expand {
  if (expanded_) {
    return;
  }
  expanded_ = true;

  [CATransaction begin];
  [CATransaction setValue:(id)kCFBooleanTrue forKey:kCATransactionDisableActions];
  [self setScale:kExpandScale];
  [self resetTransform:angle_ scale:scale_];

  CAKeyframeAnimation* scale =
      [CAKeyframeAnimation animationWithKeyPath:@"transform.scale"];
  scale.values = Array(kShrunkScale, kExpandScale,
                       kExpandScale * 1.1, kExpandScale);
  scale.keyTimes = Array(0, 0.5, 0.65, 0.8);
  scale.duration = kExpandDuration * animation_scale_;

  CAKeyframeAnimation* position =
      [CAKeyframeAnimation animationWithKeyPath:@"position"];
  position.values = Array(
      [self shrunkPosition],
      [self expandPosition]);
  position.keyTimes = Array(0.0, 0.5);
  position.duration = kExpandDuration * animation_scale_;

  CAKeyframeAnimation* rotation =
      [CAKeyframeAnimation animationWithKeyPath:@"transform.rotation.z"];
  rotation.values = Array(angle_ + kShrunkAngle, angle_,
                          angle_ - kShudderAngle, angle_);
  rotation.keyTimes = Array(0.0, 0.7, 0.85, 1.0);
  rotation.duration = kExpandDuration * animation_scale_;

  CAKeyframeAnimation* opacity =
      [CAKeyframeAnimation animationWithKeyPath:@"opacity"];
  opacity.values = Array(kShrunkOpacity, 1.0);
  opacity.keyTimes = Array(0.0, 0.5);
  opacity.duration = kExpandDuration * animation_scale_;

  CAAnimationGroup* animation = [CAAnimationGroup animation];
  animation.animations = Array(scale, position, rotation, opacity);
  animation.duration = kExpandDuration * animation_scale_;
  animation.fillMode = kCAFillModeForwards;

  [buttons_.layer addAnimation:animation forKey:nil];
  [wheel_ addAnimation:animation forKey:nil];

  [CATransaction commit];
}

- (void)shrink {
  if (!expanded_) {
    return;
  }
  expanded_ = false;

  [CATransaction begin];
  [CATransaction setValue:(id)kCFBooleanTrue forKey:kCATransactionDisableActions];
  [self setScale:kShrunkScale];
  [self resetTransform:angle_ + kShrunkAngle scale:scale_];

  CAKeyframeAnimation* scale =
      [CAKeyframeAnimation animationWithKeyPath:@"transform.scale"];
  scale.values = Array(kExpandScale, kExpandScale * 1.1,
                       kShrunkScale, kShrunkScale * 0.9, kShrunkScale);
  scale.keyTimes = Array(0.0, 0.4, 0.7, 0.85, 1.0);
  scale.duration = kShrinkDuration * animation_scale_;

  CAKeyframeAnimation* position =
      [CAKeyframeAnimation animationWithKeyPath:@"position"];
  position.values = Array(
      [self expandPosition],
      [self shrunkPosition]);
  position.keyTimes = Array(0.3, 0.7);
  position.duration = kShrinkDuration * animation_scale_;

  CAKeyframeAnimation* rotation =
      [CAKeyframeAnimation animationWithKeyPath:@"transform.rotation.z"];
  rotation.values = Array(angle_,
                          angle_ + kShrunkAngle,
                          angle_ + kShrunkAngle - kShudderAngle,
                          angle_ + kShrunkAngle);
  rotation.keyTimes = Array(0.0, 0.7, 0.85, 1.0);
  rotation.duration = kShrinkDuration * animation_scale_;

  CAKeyframeAnimation* opacity =
      [CAKeyframeAnimation animationWithKeyPath:@"opacity"];
  opacity.values = Array(1.0, kShrunkOpacity);
  opacity.keyTimes = Array(0.5, 1.0);
  opacity.duration = kShrinkDuration * animation_scale_;

  CAAnimationGroup* animation = [CAAnimationGroup animation];
  animation.animations = Array(scale, position, rotation, opacity);
  animation.duration = kShrinkDuration * animation_scale_;
  animation.fillMode = kCAFillModeForwards;

  [buttons_.layer addAnimation:animation forKey:nil];
  [wheel_ addAnimation:animation forKey:nil];
  [self updateAnimationScale];

  [CATransaction commit];
}

- (CGPoint)expandPosition {
  float t = 0;
  if (wheel_pos_ < 0.25) {
    t = wheel_pos_ / 0.25;
  } else if (wheel_pos_ < 0.75) {
    t = fabs(wheel_pos_ - 0.5) / 0.25;
  } else {
    t = (1 - wheel_pos_) / 0.25;
  }
  const float y_min_offset = kExpandOffset;
  const float y_max_offset = 2 * kExpandOffset;
  const float y_offset = y_min_offset +
      (y_max_offset - y_min_offset) * sin(t * kPi / 2);
  return CGPointMake(
      kExpandOffset + wheel_pos_ * (self.frame.size.width - 2 * kExpandOffset),
      self.frame.size.height - y_offset);
}

- (CGPoint)shrunkPosition {
  const float y_offset = kShrunkOffset * ((wheel_pos_ == 0.5) ? 3 : 1);
  return CGPointMake(
      kShrunkOffset + wheel_pos_ * (self.frame.size.width - 2 * kShrunkOffset),
      self.frame.size.height - y_offset);
}

- (void)itemSelected:(id)sender {
  [self shrink];
}

- (void)setScale:(float)v {
  scale_ = v;
  [self resetTransform:angle_ scale:scale_];
}

- (void)setAngle:(float)v {
  angle_ = v;
  [self resetTransform:angle_ scale:scale_];
}

- (void)resetTransform:(float)angle scale:(float)scale {
  CGAffineTransform t = CGAffineTransformMakeRotation(angle);
  t = CGAffineTransformScale(t, scale, scale);
  [buttons_ setTransform:t];
  [wheel_ setAffineTransform:t];
}

- (float)angleForPos:(float)wheel_pos {
  float begin_angle;
  float end_angle;
  float t = 0;
  if (wheel_pos <= 0.5) {
    begin_angle = kLeftAngle;
    end_angle = kCenterAngle1;
    t = wheel_pos / 0.5;
  } else {
    begin_angle = kCenterAngle2;
    end_angle = kRightAngle;
    t = (wheel_pos - 0.5) / 0.5;
  }
  return begin_angle + (end_angle - begin_angle) * t;
}

- (void)updateAnimationScale {
  if (animation_scale_ > 1.0) {
    animation_scale_ = std::max<float>(1.0, animation_scale_ * 0.95);
    state_->db()->Put(kAnimationScaleKey, animation_scale_);
  }
}

@end  // WheelMenu
