// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <CoreLocation/CoreLocation.h>
#import <Foundation/Foundation.h>
#import "Callback.h"
#import "ScopedPtr.h"

class UIAppState;
class Breadcrumb;
class Location;

Location MakeLocation(CLLocation* l);
Breadcrumb MakeBreadcrumb(CLLocation* l);

@interface LocationTracker : NSObject <CLLocationManagerDelegate> {
 @private
  UIAppState* state_;
  CLLocationManager* location_manager_;
  const Breadcrumb* geocoding_breadcrumb_;
  CallbackSet1<bool> authorization_did_change_;
  CallbackSet breadcrumb_did_become_available_;
  NSTimer* interval_timer_;
  NSTimer* location_timer_;
  bool enabled_;
}

@property (nonatomic, readonly) bool authorized;
@property (nonatomic, readonly) Breadcrumb breadcrumb;
@property (nonatomic, readonly) Location location;
@property (nonatomic, readonly) CallbackSet1<bool>* authorizationDidChange;
@property (nonatomic, readonly) CallbackSet* breadcrumbDidBecomeAvailable;

- (id)initWithState:(UIAppState*)state;
- (void)ensureInitialized;
- (void)start;
- (void)stop;

@end  // ViewController

// local variables:
// mode: objc
// end:
