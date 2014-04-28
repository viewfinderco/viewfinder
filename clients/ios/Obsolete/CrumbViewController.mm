// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "CrumbPath.h"
#import "CrumbPathView.h"
#import "CrumbViewController.h"
#import "Logging.h"

@implementation CrumbViewController

- (void)loadView {
  map_view_ = [MKMapView new];
  map_view_.delegate = self;
  map_view_.showsUserLocation = TRUE;
  map_view_.zoomEnabled = TRUE;
  map_view_.scrollEnabled = TRUE;
  self.view = map_view_;
}

- (void)viewDidUnload {
  [map_view_ release];
  map_view_ = nil;
  [super viewDidUnload];
}

- (void)addLocation:(CLLocation*)location {
  if (!crumbs_) {
    crumbs_ = [[CrumbPath alloc] initWithCenterCoordinate:location.coordinate];
    [map_view_ addOverlay:crumbs_];
    // Zoom to the current user location on the first location update.
    MKCoordinateRegion user_location =
        MKCoordinateRegionMakeWithDistance(
            location.coordinate, 1500.0, 1500.0);
    [map_view_ setRegion:user_location animated:YES];
  } else {
    MKMapRect update_rect = [crumbs_ addCoordinate:location.coordinate];
    if (!MKMapRectIsNull(update_rect)) {
      // There is a non null update rect.
      // Compute the currently visible map zoom scale
      MKZoomScale currentZoomScale =
          (CGFloat)(map_view_.bounds.size.width / map_view_.visibleMapRect.size.width);
      // Find out the line width at this zoom scale and outset the update_rect
      // by that amount
      CGFloat line_width = MKRoadWidthAtZoomScale(currentZoomScale);
      update_rect = MKMapRectInset(update_rect, -line_width, -line_width);
      // Ask the overlay view to update just the changed area.
      [crumb_path_view_ setNeedsDisplayInMapRect:update_rect];
    }
  }
}

- (MKOverlayView*)mapView:(MKMapView*)map_view
           viewForOverlay:(id<MKOverlay>)overlay {
  if (!crumb_path_view_) {
    crumb_path_view_ = [[CrumbPathView alloc] initWithOverlay:overlay];
  }
  return crumb_path_view_;
}

- (void) dealloc {
  [crumb_path_view_ release];
  [crumbs_ release];
  [map_view_ release];
  [super dealloc];
}

@end  // CrumbViewController
