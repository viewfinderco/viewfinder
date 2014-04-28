// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_PLACEMARK_HISTOGRAM_H
#define VIEWFINDER_PLACEMARK_HISTOGRAM_H

#import <unordered_map>
#import "DB.h"
#import "Mutex.h"
#import "PlacemarkHistogramEntry.pb.h"
#import "WallTime.h"

class AppState;
class Location;

class PlacemarkHistogram {
 public:
  struct TopPlacemark {
    Placemark placemark;
    Location centroid;
    double weight;
    bool useful_sublocality;

    TopPlacemark() : weight(0), useful_sublocality(false) {}
    TopPlacemark(const PlacemarkHistogramEntry& e, int total_count);
  };

 public:
  PlacemarkHistogram(AppState* state);
  ~PlacemarkHistogram();

  // Adds a placemark to the histogram.
  void AddPlacemark(const Placemark& placemark,
                    const Location& location,
                    const DBHandle& updates);

  // Removes a placemark from the histogram.
  void RemovePlacemark(const Placemark& placemark,
                       const Location& location,
                       const DBHandle& updates);

  // Findest the nearest "top" placemark. If there are no top
  // placemarks, returns false. Otherwise, returns true, and sets
  // *distance to the distance to the top placemark's centroid. If
  // top_placemark is not NULL, copies the top placemark's information
  // for use by the caller.
  bool DistanceToTopPlacemark(const Location& location,
                              double* distance,
                              TopPlacemark* top_placemark);

  bool DistanceToLocation(const Location& location, double* distance,
                          TopPlacemark* top = NULL);

  void FormatLocation(const Location& location, const Placemark& placemark,
                      bool short_location, string* s);
  void FormatLocality(const Location& location, const Placemark& placemark,
                      string* s);

 private:
  // If needs_refresh_ is true, reads the top-weighted placemarks from
  // the database and stores them in top_placemarks_. Otherwise, noop.
  void MaybeInitTopPlacemarks();

  // Updates the histogram for the specified placemark/location by
  // adjusting its photo count. The total histogram count is also
  // updated.
  void UpdateHistogram(const Placemark& placemark,
                       const Location& location,
                       int count,
                       const DBHandle& updates);

  // Finds the closest of the top placemarks to the specified
  // location. If there are no top placemarks, returns NULL.
  const TopPlacemark* FindClosestTopPlacemark(const Location& location);

  // Looks up the histogram in the database by canonicalized
  // placemark key. Sets *entry on success and returns true;
  // false otherwise.
  bool LookupHistogramEntry(const Placemark& placemark,
                            PlacemarkHistogramEntry* entry,
                            const DBHandle& db);

 public:
  static const double kMinRefreshIntervalSeconds;

 private:
  // Vector of location summaries.
  typedef vector<TopPlacemark> TopPlacemarkVec;
  // Map of placemark keys to updated counts to support batch
  // updates efficiently and correctly.
  typedef std::unordered_map<string, PlacemarkHistogramEntry> PlacemarkEntryMap;

  AppState* state_;
  mutable Mutex mu_;
  TopPlacemarkVec top_placemarks_;
  bool need_refresh_;
  WallTime last_refresh_;
  double total_count_;
};

#endif  // VIEWFINDER_PLACEMARK_HISTOGRAM_H
