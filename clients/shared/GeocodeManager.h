// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_GEOCODE_MANAGER_H
#define VIEWFINDER_GEOCODE_MANAGER_H

#import "Callback.h"

class Location;
class Placemark;

class GeocodeManager {
 protected:
  // Called when the reverse geocoding is complete. Placemark is NULL if
  // geocoding failed.
  typedef Callback<void (const Placemark*)> Completion;

 public:
  virtual ~GeocodeManager();

  // Returns true if the location is already queued for reverse geocoding.
  virtual bool ReverseGeocode(const Location* l, Completion completion) = 0;
};

GeocodeManager* NewGeocodeManager();

#endif  // VIEWFINDER_GEOCODE_MANAGER_H
