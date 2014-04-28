// Copyright 2013 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "CompositeTextLayers.h"
#import "PhotoView.h"
#import "RowView.h"
#import "UIView+geometry.h"

const float kExpandAnimationDuration = 0.4;  // 400 ms

@implementation RowView

@synthesize env = env_;
@synthesize index = index_;
@synthesize textLayer = text_layer_;

- (id)init {
  if (self = [super init]) {
    index_ = -1;
  }
  return self;
}

- (bool)editing {
  return false;
}

- (void)setEditing:(bool)value {
}

- (UIView*)editingView {
  return self;
}

- (bool)modified {
  return false;
}

- (bool)selected {
  return false;
}

- (void)setSelected:(bool)value {
}

- (bool)enabled {
  return true;
}

- (void)setEnabled:(bool)value {
}

- (vector<PhotoView*>*)photos {
  return &photos_;
}

- (float)desiredFrameHeight {
  return [self sizeThatFits:self.bounds.size].height;
}

- (bool)hasFocus {
  return false;
}

- (bool)hasPhoto:(int64_t)photo_id {
  return [self findPhotoView:photo_id] != NULL;
}

- (PhotoView*)findPhotoView:(int64_t)photo_id {
  for (int i = 0; i < photos_.size(); ++i) {
    if (photos_[i].photoId == photo_id) {
      return photos_[i];
    }
  }
  return NULL;
}

- (void)addTextLayer:(CompositeTextLayer*)layer {
  text_layer_ = layer;
  [self.layer addSublayer:text_layer_];
}

- (void)commitEdits {
}

- (float)animateToggleExpandPrepare:(float)max_height {
  return self.frameHeight;
}

- (void)animateToggleExpandCommit {
}

- (void)animateToggleExpandFinalize {
}

- (float)toggleExpand:(float)max_height {
  return self.frameHeight;
}

- (void)pinVisibleElements:(CGRect)visible_bounds {
}

@end  // RowView
