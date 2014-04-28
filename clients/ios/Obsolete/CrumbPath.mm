// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "CrumbPath.h"

#define MINIMUM_DELTA_METERS 10.0

@implementation CrumbPath

- (id)initWithCenterCoordinate:(CLLocationCoordinate2D)coord {
  if (self = [super init]) {
    // initialize point storage and place this first coordinate in it
    points_.push_back(MKMapPointForCoordinate(coord));
    bounds_ = MKMapRectMake(0, 0, MKMapSizeWorld.width, MKMapSizeWorld.height);
  }
  return self;
}

- (void)dealloc {
  [super dealloc];
}

- (MKMapPoint*) points {
  return &points_[0];
}

- (int)pointCount {
  return points_.size();
}

- (CLLocationCoordinate2D)coordinate {
  return MKCoordinateForMapPoint(points_[0]);
}

- (MKMapRect)boundingMapRect {
  return bounds_;
}

- (void)lockForReading {
  mu_.Lock();
}

- (void)unlockForReading {
  mu_.Unlock();
}

- (MKMapRect)addCoordinate:(CLLocationCoordinate2D)coord {
  // Acquire the write lock because we are going to be changing the list of points
  mu_.Lock();

  // Convert a CLLocationCoordinate2D to an MKMapPoint
  MKMapPoint new_point = MKMapPointForCoordinate(coord);
  const MKMapPoint& prev_point = points_.back();

  // Get the distance between this new point and the previous point.
  CLLocationDistance meters_apart = MKMetersBetweenMapPoints(new_point, prev_point);
  MKMapRect update_rect = MKMapRectNull;

  if (meters_apart > MINIMUM_DELTA_METERS) {
    // Add the new point to the points array
    points_.push_back(new_point);

    // Compute MKMapRect bounding prev_point and new_point
    const double minX = MIN(new_point.x, prev_point.x);
    const double minY = MIN(new_point.y, prev_point.y);
    const double maxX = MAX(new_point.x, prev_point.x);
    const double maxY = MAX(new_point.y, prev_point.y);

    update_rect = MKMapRectMake(minX, minY, maxX - minX, maxY - minY);
  }

  mu_.Unlock();

  return update_rect;
}

@end  // CrumbPath
