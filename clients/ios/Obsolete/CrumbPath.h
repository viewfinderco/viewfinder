// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <MapKit/MapKit.h>
#import "Mutex.h"

@interface CrumbPath : NSObject <MKOverlay> {
 @private
  Mutex mu_;
  vector<MKMapPoint> points_;
  MKMapRect bounds_;
}

// The following properties must only be accessed when holding the read lock
// via lockForReading.  Once you're done accessing the points, release the read
// lock with unlockForReading.
@property (readonly) MKMapPoint* points;
@property (readonly) int pointCount;

// Initialize the CrumbPath with the starting coordinate.  The CrumbPath's
// boundingMapRect will be set to a sufficiently large square centered on the
// starting coordinate.
- (id)initWithCenterCoordinate:(CLLocationCoordinate2D)coord;

// Add a location observation. A MKMapRect containing the newly added point and
// the previously added point is returned so that the view can be updated in
// that rectangle.  If the added coordinate has not moved far enough from the
// previously added coordinate it will not be added to the list and
// MKMapRectNull will be returned.
- (MKMapRect)addCoordinate:(CLLocationCoordinate2D)coord;

- (void)lockForReading;
- (void)unlockForReading;

@end  // CrumbPath

// local variables:
// mode: objc
// end:
