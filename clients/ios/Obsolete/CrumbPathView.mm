// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "CrumbPathView.h"
#import "CrumbPath.h"

@interface CrumbPathView (FileInternal)
- (CGPathRef)newPathForPoints:(MKMapPoint *)points
                   pointCount:(NSUInteger)point_count
                     clipRect:(MKMapRect)map_rect
                    zoomScale:(MKZoomScale)zoom_scale;
@end  // CrumbPathView

@implementation CrumbPathView

- (void)drawMapRect:(MKMapRect)mapRect
          zoomScale:(MKZoomScale)zoomScale
          inContext:(CGContextRef)context {
  CrumbPath* crumbs = (CrumbPath*)(self.overlay);

  CGFloat line_width = MKRoadWidthAtZoomScale(zoomScale);

  // outset the map rect by the line width so that points just outside
  // of the currently drawn rect are included in the generated path.
  MKMapRect clip_rect = MKMapRectInset(mapRect, -line_width, -line_width);

  [crumbs lockForReading];
  CGPathRef path = [self newPathForPoints:[crumbs points]
                               pointCount:[crumbs pointCount]
                                 clipRect:clip_rect
                                zoomScale:zoomScale];
  [crumbs unlockForReading];

  if (path != nil) {
    CGContextAddPath(context, path);
    CGContextSetRGBStrokeColor(context, 0.0f, 0.0f, 1.0f, 0.5f);
    CGContextSetLineJoin(context, kCGLineJoinRound);
    CGContextSetLineCap(context, kCGLineCapRound);
    CGContextSetLineWidth(context, line_width);
    CGContextStrokePath(context);
    CGPathRelease(path);
  }
}

@end  // CrumbPathView

@implementation CrumbPathView (FileInternal)

static BOOL lineIntersectsRect(MKMapPoint p0, MKMapPoint p1, MKMapRect r) {
  const double minX = MIN(p0.x, p1.x);
  const double minY = MIN(p0.y, p1.y);
  const double maxX = MAX(p0.x, p1.x);
  const double maxY = MAX(p0.y, p1.y);

  const MKMapRect r2 = MKMapRectMake(minX, minY, maxX - minX, maxY - minY);
  return MKMapRectIntersectsRect(r, r2);
}

#define MIN_POINT_DELTA 5.0

- (CGPathRef)newPathForPoints:(MKMapPoint *)points
                   pointCount:(NSUInteger)point_count
                     clipRect:(MKMapRect)map_rect
                    zoomScale:(MKZoomScale)zoom_scale {
  // The fastest way to draw a path in an MKOverlayView is to simplify the
  // geometry for the screen by eliding points that are too close together and
  // to omit any line segments that do not intersect the clipping rect.  While
  // it is possible to just add all the points and let CoreGraphics handle
  // clipping and flatness, it is much faster to do it yourself:
  if (point_count < 2)
    return NULL;

  CGMutablePathRef path = NULL;

  BOOL needs_move = YES;

#define POW2(a) ((a) * (a))

  // Calculate the minimum distance between any two points by figuring out how
  // many map points correspond to MIN_POINT_DELTA of screen points at the
  // current zoom_scale.
  double min_point_delta = MIN_POINT_DELTA / zoom_scale;
  double c2 = POW2(min_point_delta);

  MKMapPoint point;
  MKMapPoint last_point = points[0];
  NSUInteger i;
  for (i = 1; i < point_count - 1; i++) {
    point = points[i];
    double a2b2 = POW2(point.x - last_point.x) + POW2(point.y - last_point.y);
    if (a2b2 >= c2) {
      if (lineIntersectsRect(point, last_point, map_rect)) {
        if (!path)
          path = CGPathCreateMutable();
        if (needs_move) {
          CGPoint last_cg_point = [self pointForMapPoint:last_point];
          CGPathMoveToPoint(path, NULL, last_cg_point.x, last_cg_point.y);
        }
        CGPoint cg_point = [self pointForMapPoint:point];
        CGPathAddLineToPoint(path, NULL, cg_point.x, cg_point.y);
      } else {
        // discontinuity, lift the pen
        needs_move = YES;
      }
      last_point = point;
    }
  }

#undef POW2

  // If the last line segment intersects the map_rect at all, add it
  // unconditionally
  point = points[point_count - 1];
  if (lineIntersectsRect(last_point, point, map_rect)) {
    if (!path)
      path = CGPathCreateMutable();
    if (needs_move) {
      CGPoint last_cg_point = [self pointForMapPoint:last_point];
      CGPathMoveToPoint(path, NULL, last_cg_point.x, last_cg_point.y);
    }
    CGPoint cg_point = [self pointForMapPoint:point];
    CGPathAddLineToPoint(path, NULL, cg_point.x, cg_point.y);
  }

  return path;
}

@end  // CrumbPathView (FileInternal)
