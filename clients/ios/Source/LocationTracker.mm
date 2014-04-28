// Copyright 2011 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "Analytics.h"
#import "Breadcrumb.pb.h"
#import "DB.h"
#import "GeocodeManager.h"
#import "LocationTracker.h"
#import "LocationUtils.h"
#import "Logging.h"
#import "NetworkManager.h"
#import "ServerUtils.h"
#import "UIAppState.h"
#import "WallTime.h"

namespace {

// Disable LOCLOG statements in APPSTORE builds as they contain Personally
// Identifiable Information.
#ifdef APPSTORE
#define LOCLOG  if (0) VLOG
#else
#define LOCLOG  VLOG
#endif

const CLLocationAccuracy kMinLocationAccuracy = 100;
const double kLocationFixTime = 10;
const double kLocationInterval = 10 * 60;  // 10 mins
const float kMinBatteryLevelForLocationTask = 0.5;

}  // namespace

Location MakeLocation(CLLocation* l) {
  Location r;
  r.set_latitude(l.coordinate.latitude);
  r.set_longitude(l.coordinate.longitude);
  r.set_accuracy(l.horizontalAccuracy);
  if (l.verticalAccuracy >= 0) {
    r.set_altitude(l.altitude);
  }
  return r;
}

Breadcrumb MakeBreadcrumb(CLLocation* l) {
  Breadcrumb b;
  b.mutable_location()->CopyFrom(MakeLocation(l));
  b.set_timestamp([l.timestamp timeIntervalSince1970]);
  return b;
}

@interface LocationTracker (internal)
- (void)maybeStoreLocation:(CLLocation*)location;
- (void)maybeGeocodeLastBreadcrumb;
- (void)stopLocationTask;
- (bool)maybeStartLocationTask;
- (void)intervalTimerFired:(NSTimer*)timer;
- (void)locationTimerFired:(NSTimer*)timer;
- (void)applicationWillResignActive;
- (void)applicationDidBecomeActive;
@end  // LocationTracker

@implementation LocationTracker

@dynamic breadcrumb;
@dynamic location;

- (id)initWithState:(UIAppState*)state {
  if (self = [super init]) {
    state_ = state;

    [self maybeGeocodeLastBreadcrumb];
    [self maybeInitialize];

    state_->app_did_become_active()->Add(^{
        [self maybeInitialize];
      });
  }

  return self;
}

- (void)maybeInitialize {
  switch ([CLLocationManager authorizationStatus]) {
    case kCLAuthorizationStatusNotDetermined:
      LOCLOG("location: authorization not determined");
      break;
    case kCLAuthorizationStatusRestricted:
      LOCLOG("location: authorization restricted");
      break;
    case kCLAuthorizationStatusDenied:
      LOCLOG("location: authorization denied");
      break;
    case kCLAuthorizationStatusAuthorized:
      [self ensureInitialized];
      authorization_did_change_.Run(true);
      return;
  }

  if (location_manager_) {
    [self stop];
    location_manager_ = NULL;
    [self stopLocationTask];
  }
  authorization_did_change_.Run(false);
}

- (void)ensureInitialized {
  if (!location_manager_) {
    location_manager_ = [CLLocationManager new];
    location_manager_.delegate = self;
    location_manager_.distanceFilter = kMinLocationAccuracy;
    location_manager_.desiredAccuracy = kMinLocationAccuracy;

    LOCLOG("location: start monitoring significant location changes");
    [location_manager_ startMonitoringSignificantLocationChanges];
    if (![self maybeStartLocationTask]) {
      [self stopLocationTask];
    }

    struct {
      SEL selector;
      NSString* name;
    } kNotifications[] = {
      { @selector(applicationWillResignActive),
        UIApplicationWillResignActiveNotification },
      { @selector(applicationDidBecomeActive),
        UIApplicationDidBecomeActiveNotification },
    };

    for (int i = 0; i < ARRAYSIZE(kNotifications); ++i) {
      [[NSNotificationCenter defaultCenter]
          addObserver:self
             selector:kNotifications[i].selector
                 name:kNotifications[i].name
               object:NULL];
    }
  }
}

- (void)locationManager:(CLLocationManager*)manager
       didFailWithError:(NSError*)error {
  LOCLOG("location: error: %@", error);
}

- (void)locationManager:(CLLocationManager*)manager
    didUpdateToLocation:(CLLocation*)new_location
           fromLocation:(CLLocation*)old_location {
  if (!new_location) {
    LOCLOG("location: no new location data!");
    return;
  }

  if (new_location.coordinate.latitude == old_location.coordinate.latitude &&
      new_location.coordinate.longitude == old_location.coordinate.longitude &&
      new_location.horizontalAccuracy == old_location.horizontalAccuracy) {
    return;
  }

  if (new_location.horizontalAccuracy <= kMinLocationAccuracy) {
    // If the accuracy is sufficient, stop background location updates.
    [self maybeStoreLocation:new_location];
    [self stopLocationTask];
  } else if (![self maybeStartLocationTask]) {
    // We were unable to start a background location task, so try to store
    // whatever location we have.
    [self maybeStoreLocation:new_location];
  }
}

- (bool)authorized {
  return location_manager_ != NULL;
}

- (Breadcrumb)breadcrumb {
  return MakeBreadcrumb([location_manager_ location]);
}

- (Location)location {
  return MakeLocation([location_manager_ location]);
}

- (CallbackSet1<bool>*)authorizationDidChange {
  return &authorization_did_change_;
}

- (CallbackSet*)breadcrumbDidBecomeAvailable {
  return &breadcrumb_did_become_available_;
}

- (void)start {
  if (!enabled_) {
    enabled_ = true;
    location_manager_.distanceFilter = kCLLocationAccuracyBest;
    location_manager_.desiredAccuracy = kCLLocationAccuracyBest;
    [location_manager_ startUpdatingLocation];
    LOCLOG("location: start updating location (%.0f)",
           [location_manager_ desiredAccuracy]);
  }
}

- (void)stop {
  if (enabled_) {
    enabled_ = false;
    LOCLOG("location: stop updating location");
    [location_manager_ stopUpdatingLocation];
    location_manager_.distanceFilter = kMinLocationAccuracy;
    location_manager_.desiredAccuracy = kMinLocationAccuracy;
  }
}

- (void)maybeStoreLocation:(CLLocation*)l {
  Breadcrumb b(MakeBreadcrumb(l));
  b.set_debug(state_->ui_application_state());

  if (state_->last_breadcrumb()) {
    const float loc_dist = DistanceBetweenLocations(
        state_->last_breadcrumb()->location(), b.location());
    const float time_dist = b.timestamp() -
        state_->last_breadcrumb()->timestamp();
    if (loc_dist < kMinLocationAccuracy && time_dist < 60 * 60) {
      // Ignore location updates that are less than 100 meters from our last
      // location and within the past hour.
      LOCLOG("location: ignoring loc=%.2f  time=%.2f  state=%s",
             loc_dist, time_dist, b.debug());
      return;
    }
    LOCLOG("location: breadcrumb %s: <%.2f,%.0f> %s",
           WallTimeFormat("%F/%T.%Q", b.timestamp()),
           loc_dist, b.location().accuracy(), b.debug());
  } else {
    LOCLOG("location: breadcrumb %s: <%+f,%+f,%.0f> %s",
           WallTimeFormat("%F/%T.%Q", b.timestamp()),
           b.location().latitude(), b.location().longitude(),
           b.location().accuracy(), b.debug());
  }
  state_->set_last_breadcrumb(b);
  state_->net_manager()->Dispatch();

  [self maybeGeocodeLastBreadcrumb];
}

- (void)maybeGeocodeLastBreadcrumb {
  if (state_->ui_application_background()) {
    return;
  }
  if (!state_->geocode_manager()) {
    return;
  }
  if (!state_->last_breadcrumb() ||
      geocoding_breadcrumb_ == state_->last_breadcrumb()) {
    return;
  }
  if (state_->last_breadcrumb()->has_placemark()) {
    return;
  }
  geocoding_breadcrumb_ = state_->last_breadcrumb();
  Breadcrumb* b = new Breadcrumb(*state_->last_breadcrumb());
  state_->geocode_manager()->ReverseGeocode(
      &b->location(), ^(const Placemark* m){
        geocoding_breadcrumb_ = NULL;
        ScopedPtr<Breadcrumb> deleter(b);
        if (!m) {
          // Geocoding failed.
          return;
        }
        if (b->timestamp() == state_->last_breadcrumb()->timestamp()) {
          // Only re-write the last breadcrumb if a new one hasn't been
          // generated.
          b->mutable_placemark()->CopyFrom(*m);
          state_->set_last_breadcrumb(*b);
          breadcrumb_did_become_available_.Run();
        }
      });
}

- (void)stopLocationTask {
  if (!enabled_) {
    [location_manager_ stopUpdatingLocation];
  }
  if (location_timer_ != NULL) {
    LOCLOG("location: stop location task");
    [location_timer_ invalidate];
    location_timer_ = NULL;
  }
  if (location_manager_) {
    if (!enabled_ && !interval_timer_) {
      interval_timer_ =
          [NSTimer
            scheduledTimerWithTimeInterval:kLocationInterval
                                    target:self
                                  selector:@selector(intervalTimerFired:)
                                  userInfo:NULL
                                   repeats:YES];
    }
  } else {
    [interval_timer_ invalidate];
    interval_timer_ = NULL;
  }
}

- (bool)maybeStartLocationTask {
  if (location_timer_ != NULL) {
    // We're aleady running a location task.
    return true;
  }
  if (enabled_) {
    // Location updates are already enabled.
    return false;
  }
  if (!state_->battery_charging() &&
      state_->battery_level() < kMinBatteryLevelForLocationTask) {
    // Insufficient battery for performing a location task.
    LOCLOG("location: insufficient battery: %.2f", state_->battery_level());
    return false;
  }

  // Temporarily turn on high accuracy location info. This code path is
  // executed when the app starts or when a significant location change event
  // occurs.
  LOCLOG("location: start location task");

  location_timer_ =
      [NSTimer
        scheduledTimerWithTimeInterval:kLocationFixTime
                                target:self
                              selector:@selector(locationTimerFired:)
                              userInfo:NULL
                               repeats:YES];

  [location_manager_ startUpdatingLocation];
  return true;
}

- (void)intervalTimerFired:(NSTimer*)timer {
  LOCLOG("location: interval timer fired");
  [self maybeStartLocationTask];
}

- (void)locationTimerFired:(NSTimer*)timer {
  LOCLOG("location: location timer fired");
  if (!location_manager_) {
    return;
  }
  [self maybeStoreLocation:[location_manager_ location]];
  [self stopLocationTask];
}

- (void)applicationWillResignActive {
  if (!location_manager_) {
    return;
  }
  LOCLOG("location: stop monitoring significant location changes");
  [location_manager_ stopMonitoringSignificantLocationChanges];
  [self stopLocationTask];

  if (enabled_) {
    LOCLOG("location: stop updating location");
    [location_manager_ stopUpdatingLocation];
    location_manager_.distanceFilter = kMinLocationAccuracy;
    location_manager_.desiredAccuracy = kMinLocationAccuracy;
  }
}

- (void)applicationDidBecomeActive {
  if (!location_manager_) {
    return;
  }
  LOCLOG("location: start monitoring significant location changes");
  [location_manager_ startMonitoringSignificantLocationChanges];

  if (enabled_) {
    location_manager_.distanceFilter = kCLLocationAccuracyBest;
    location_manager_.desiredAccuracy = kCLLocationAccuracyBest;
    LOCLOG("location: start updating location (%.0f)",
           location_manager_.desiredAccuracy);
    [location_manager_ startUpdatingLocation];
  } else {
    [self maybeStartLocationTask];
  }
}

@end  // LocationTracker
