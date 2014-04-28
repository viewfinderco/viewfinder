// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <MapKit/MapKit.h>

@class CrumbPath;
@class CrumbPathView;

@interface CrumbViewController : UIViewController <MKMapViewDelegate> {
 @private
  MKMapView* map_view_;
  CrumbPath* crumbs_;
  CrumbPathView* crumb_path_view_;
}

- (void)addLocation:(CLLocation*)location;

@end  // CrumbViewController

// local variables:
// mode: objc
// end:
