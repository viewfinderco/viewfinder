// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <QuartzCore/QuartzCore.h>
#import "CheckmarkBadge.h"
#import "Logging.h"
#import "PhotoTable.h"
#import "PhotoView.h"
#import "UIAppState.h"
#import "UIView+geometry.h"

namespace {

const float kDuration = 0.15;
const int kShowDebugLabel = 0;
const int kDebugLabelTag = 45678;

LazyStaticHexColor kDisabledOverlayColor = { "#0000007f" };

}  // namespace

CGRect AspectFit(const CGSize& bounds, float aspect_ratio) {
  CGRect r = { { 0, 0 }, bounds };
  const float a = r.size.width / r.size.height;
  if (aspect_ratio >= a) {
    r.size.height = r.size.width / aspect_ratio;
  } else {
    r.size.width = r.size.height * aspect_ratio;
  }
  return r;
}

CGRect AspectFill(const CGSize& bounds, float aspect_ratio) {
  CGRect r = { { 0, 0 }, bounds };
  const float a = r.size.width / r.size.height;
  if (aspect_ratio <= a) {
    r.size.height = r.size.width / aspect_ratio;
  } else {
    r.size.width = r.size.height * aspect_ratio;
  }
  return r;
}

@implementation PhotoView

@synthesize selectable = selectable_;
@synthesize imageView = image_view_;
@synthesize editBadge = edit_badge_;
@synthesize editBadgeOffset = edit_badge_offset_;

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    self.autoresizesSubviews = YES;
    self.backgroundColor = [UIColor clearColor];
    self.clipsToBounds = YES;
    self.userInteractionEnabled = YES;

    state_ = state;
    image_view_ = [[UIImageView alloc] initWithImage:NULL];
    image_view_.contentMode = UIViewContentModeScaleAspectFill;
    [self addSubview:image_view_];

    aspect_ratio_ = 1.0;
    zoom_scale_ = 1.0;
    position_ = CGPointMake(0.5, 0.5);
    selectable_ = true;
  }
  return self;
}

- (UILabel*)debugLabel {
  return (UILabel*)[self viewWithTag:kDebugLabelTag];
}

- (void)setPhotoId:(int64_t)v {
  [super setPhotoId:v];

  if (kShowDebugLabel) {
    UILabel* l = self.debugLabel;
    if (!l) {
      l = [UILabel new];
      l.autoresizingMask =
          UIViewAutoresizingFlexibleWidth |
          UIViewAutoresizingFlexibleHeight;
      l.adjustsFontSizeToFitWidth = YES;
      l.backgroundColor = MakeUIColor(0, 0, 0, 0.3);
      l.font = [UIFont boldSystemFontOfSize:14];
      l.frame = self.bounds;
      l.minimumScaleFactor = 0.5;
      l.tag = kDebugLabelTag;
      l.textAlignment = NSTextAlignmentCenter;
      l.textColor = MakeUIColor(1, 1, 1, 1);
      [self addSubview:l];
    }
    PhotoHandle ph = state_->photo_table()->LoadPhoto(v, state_->db());
    if (ph.get()) {
      l.text = Format("%d %s%s", v,
                      ph->id().has_server_id() ? "S" : "",
                      ph->HasAssetUrl() ? "A" : "");
    }
  }
}

- (ScopedPtr<Image>&)thumbnail {
  return thumbnail_;
}

- (float)aspectRatio {
  return aspect_ratio_;
}

- (void)setAspectRatio:(float)v {
  aspect_ratio_ = v;
  [self setImageFrame];
}

- (float)zoomScale {
  return zoom_scale_;
}

- (void)setZoomScale:(float)v {
  zoom_scale_ = v;
  [self setImageFrame];
}

- (CGPoint)position {
  return position_;
}

- (void)setPosition:(CGPoint)p {
  position_.x = std::max<float>(0, std::min<float>(1, p.x));
  position_.y = std::max<float>(0, std::min<float>(1, p.y));
  [self setImageFrame];
}

- (void)setFrame:(CGRect)f {
  [super setFrame:f];
  [self setImageFrame];
}

- (void)setImageFrame {
  const CGRect b = self.bounds;
  CGRect f = b;
  if (f.size.width == 0 || f.size.height == 0) {
    return;
  }

  // Apply the zoom scale.
  f.size.width *= zoom_scale_;
  f.size.height *= zoom_scale_;

  // Apply the position.
  const float a = f.size.width / f.size.height;
  if (aspect_ratio_ >= a) {
    f.size.width = f.size.height * aspect_ratio_;
  } else {
    f.size.height = f.size.width / aspect_ratio_;
  }
  f.origin.x = -(f.size.width - b.size.width) * position_.x;
  f.origin.y = -(f.size.height - b.size.height) * position_.y;

  image_view_.frame = MakeIntegralRect(f);
}

- (CGRect)imageFrame {
  return image_view_.frame;
}

- (CGSize)loadSize {
  return load_size_;
}

- (void)setLoadSize:(CGSize)s {
  load_size_ = s;
}

- (UIImage*)image {
  return image_view_.image;
}

- (void)setImage:(UIImage*)image {
  image_view_.image = image;
}

- (bool)editing {
  return edit_badge_ != NULL;
}

- (void)setEditing:(bool)value {
  if ((edit_badge_ != NULL) == value) {
    return;
  }
  if (value) {
    edit_badge_ = [CheckmarkBadge new];
    edit_badge_.autoresizingMask =
        UIViewAutoresizingFlexibleLeftMargin |
        UIViewAutoresizingFlexibleBottomMargin;
    edit_badge_.frameTop = edit_badge_offset_.y;
    edit_badge_.frameRight = self.frameWidth - edit_badge_offset_.x;
    [self addSubview:edit_badge_];
    edit_badge_.selected = false;
  } else {
    [edit_badge_ remove];
    edit_badge_ = NULL;
  }
}

- (bool)selected {
  if (self.editing) {
    return edit_badge_.selected;
  }
  return false;
}

- (void)setSelected:(bool)value {
  if (self.editing) {
    edit_badge_.selected = value;
  }
}

- (bool)enabled {
  return !disabled_;
}

- (void)setEnabled:(bool)value {
  DCHECK(edit_badge_);  // badge must already be set via editing=true
  if (disabled_ && value) {
    [disabled_ removeFromSuperview];
    disabled_ = NULL;
    edit_badge_.alpha = 1;
  } else if (!disabled_ && !value) {
    disabled_ = [UIView new];
    disabled_.frame = self.bounds;
    disabled_.backgroundColor = kDisabledOverlayColor;
    [self insertSubview:disabled_ belowSubview:edit_badge_];
    edit_badge_.alpha = 0.5;
  }
}

- (void)ensureVerticalParallax:(float)scale {
  // const CGSize s = self.frame.size;
  // if (aspect_ratio_ >= s.width / s.height) {
  //   self.zoomScale = scale;
  // }
}

- (bool)isAppropriatelyScaled {
  if (!photo_id_) {
    return true;
  }
  const CGSize load_size = self.loadSize;
  if (load_size.width > 0 && load_size.height > 0) {
    // The photo already has an image loaded, check to see if it is
    // appropriately scaled.
    const CGRect f = self.frame;
    const float scale = std::max(
        f.size.width / load_size.width,
        f.size.height / load_size.height);
    if (scale <= 1.0) {
      return true;
    }
  }
  return false;
}

- (NSString*)text {
  if (photo_id_) {
    PhotoHandle p = state_->photo_table()->LoadPhoto(
        photo_id_, state_->db());
    if (p.get()) {
      return Format("%s", *p);
    }
  }
  return NULL;
}

@end  // PhotoView
