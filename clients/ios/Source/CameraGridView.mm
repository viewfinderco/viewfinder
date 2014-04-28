// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "Appearance.h"
#import "CameraGridView.h"
#import "Logging.h"
#import "UIStyle.h"

namespace {

LazyStaticRgbColor kCameraGridColor = { Vector4f(1, 1, 1, 0.5) };
LazyStaticRgbColor kCameraGridShadowColor = { Vector4f(0, 0, 0, 0.5) };

void DrawLine(CGContextRef context, float x1, float y1, float x2, float y2) {
  CGContextMoveToPoint(context, x1, y1);
  CGContextAddLineToPoint(context, x2, y2);
}

}  // namespace

@implementation CameraGridView

- (id)initWithGridSize:(int)grid_size {
  if (self = [super init]) {
    self.backgroundColor = [UIColor clearColor];
    grid_size_ = grid_size;
  }
  return self;
}

- (void)drawRect:(CGRect)rect {
  const CGFloat grid_xsize = self.frame.size.width / grid_size_;
  const CGFloat grid_ysize = self.frame.size.height / grid_size_;

  CGContextRef context = UIGraphicsGetCurrentContext();
  CGFloat line_width = UIStyle::kDividerSize;
  CGContextSetLineWidth(context, line_width);

  CGContextSetStrokeColorWithColor(context, kCameraGridShadowColor);
  for (int i = 1; i < grid_size_; ++i) {
    for (int j = 0; j < grid_size_; ++j) {
      const float start = (j == 0) ? 0 : line_width;
      const float end = (j == grid_size_ - 1) ? 0 : line_width;
      DrawLine(context,
               i * grid_xsize - line_width, j * grid_ysize + start,
               i * grid_xsize - line_width, (j + 1) * grid_ysize - end);
      DrawLine(context,
               i * grid_xsize + line_width, j * grid_ysize + start,
               i * grid_xsize + line_width, (j + 1) * grid_ysize - end);
      DrawLine(context,
               j * grid_xsize + start, i * grid_ysize - line_width,
               (j + 1) * grid_xsize - end, i * grid_ysize - line_width);
      DrawLine(context,
               j * grid_xsize + start, i * grid_ysize + line_width,
               (j + 1) * grid_xsize - end, i * grid_ysize + line_width);
    }
  }
  CGContextStrokePath(context);

  CGContextSetStrokeColorWithColor(context, kCameraGridColor);
  for (int i = 1; i < grid_size_; ++i) {
    DrawLine(context, i * grid_xsize, 0,
             i * grid_xsize, self.frame.size.height);
    DrawLine(context, 0, i * grid_ysize,
             self.frame.size.width, i * grid_ysize);
  }
  CGContextStrokePath(context);
}

@end  // CameraGridView
