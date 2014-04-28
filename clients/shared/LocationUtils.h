// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_LOCATION_UTILS_H
#define VIEWFINDER_LOCATION_UTILS_H

#include "Utils.h"

class Location;
class Placemark;

enum PlacemarkLevel {
  PM_SUBLOCALITY,
  PM_LOCALITY,
  PM_STATE,
  PM_COUNTRY,
};

// Formats the placemark into a string within the context of the
// specified breadcrumb. If 'short_location' is specified,
// abbreviations are employed and sublocalities and states are dropped
// according to co-location within locality or country. Returns the
// formatted placemark as a string.
// 'max_parts' can be used to limit the length of the returned string
// (e.g. max_parts=2 for"SoHo, New York City" instead of "SoHo, New York
// City, NY, United States").
string FormatPlacemarkWithReferencePlacemark(
    const Placemark& pm, const Placemark* ref_pm, bool short_location,
    PlacemarkLevel min_level, int max_parts=-1);

// Returns the ISO-3166-1 3 letter Alpha-3 code from the 2
// letter Alpha-2 code.
string CountryAbbrev(const string& country);

// Returns the 2 letter US state abbreviation.
string USStateAbbrev(const string& state);

double DistanceBetweenLocations(const Location& a, const Location& b);

#endif  // VIEWFINDER_LOCATION_UTILS_H
