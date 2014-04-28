// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import <deque>
#import <unordered_set>
#import <CoreLocation/CoreLocation.h>
#import "GeocodeManager.h"
#import "Location.pb.h"
#import "Logging.h"
#import "Placemark.pb.h"
#import "STLUtils.h"

namespace {

class GeocodeManagerIOS : public GeocodeManager {
  struct Pending {
    const Location* l;
    Completion completion;
  };

 public:
  GeocodeManagerIOS()
      : active_(false),
        geocoder_([CLGeocoder new]) {
  }

  ~GeocodeManagerIOS() {
  }

  // Returns true if the location is already queued for reverse geocoding.
  virtual bool ReverseGeocode(const Location* l, Completion completion) {
    if (ContainsKey(locations_, l)) {
      return false;
    }
    locations_.insert(l);
    queue_.push_back(Pending());
    queue_.back().l = l;
    queue_.back().completion = completion;
    MaybeProcessQueue();
    return true;
  }

 private:
  void MaybeProcessQueue() {
    if (active_ || queue_.empty()) {
      return;
    }
    active_ = true;

    Pending p = queue_.front();
    CLLocation* l = [[CLLocation alloc]
                      initWithLatitude:p.l->latitude()
                             longitude:p.l->longitude()];
    VLOG("geocode: start: %f,%f", l.coordinate.latitude, l.coordinate.longitude);

    [geocoder_
      reverseGeocodeLocation:l
           completionHandler:^(NSArray* placemarks, NSError* error) {
        VLOG("geocode: finish: %f,%f: %s",
             l.coordinate.latitude, l.coordinate.longitude, placemarks);
        Placemark storage;
        Placemark* m = NULL;

        if (error) {
          if (error.domain == kCLErrorDomain &&
              (error.code == kCLErrorGeocodeFoundPartialResult ||
               error.code == kCLErrorNetwork)) {
            // We're being throttled. Retry after a delay.
            LOG("geocode: throttled");
            dispatch_after_main(5, [this] {
                active_ = false;
                MaybeProcessQueue();
              });
            return;
          } else {
            // A more permanent error. Skip reverse geocoding this location.
            LOG("geocode: error: %@", error);
          }
        } else {
          for (int i = 0; i < placemarks.count; ++i) {
            CLPlacemark* mark = [placemarks objectAtIndex:i];
            NSDictionary* address = mark.addressDictionary;
            m = &storage;
            if (mark.ISOcountryCode) {
              m->set_iso_country_code(ToString(mark.ISOcountryCode));
            }
            if (mark.country) {
              m->set_country(ToString(mark.country));
            }
            NSString* state = address[@"State"];
            if (state) {
              m->set_state(ToString(state));
            }
            if (mark.postalCode) {
              m->set_postal_code(ToString(mark.postalCode));
            }
            if (mark.locality) {
              m->set_locality(ToString(mark.locality));
            }
            if (mark.subLocality) {
              m->set_sublocality(ToString(mark.subLocality));
            }
            if (mark.thoroughfare) {
              m->set_thoroughfare(ToString(mark.thoroughfare));
            }
            if (mark.subThoroughfare) {
              m->set_subthoroughfare(ToString(mark.subThoroughfare));
            }
            break;
          }
        }

        active_ = false;
        queue_.pop_front();
        locations_.erase(p.l);
        p.completion(m);
        MaybeProcessQueue();
      }];
  }

 private:
  bool active_;
  CLGeocoder* geocoder_;
  std::deque<Pending> queue_;
  std::unordered_set<const Location*> locations_;
};

}  // namespace

GeocodeManager::~GeocodeManager() {
}

GeocodeManager* NewGeocodeManager() {
  return new GeocodeManagerIOS;
}

// local variables:
// mode: c++
// end:
