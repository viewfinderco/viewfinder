// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifndef VIEWFINDER_PLACEMARK_TABLE_H
#define VIEWFINDER_PLACEMARK_TABLE_H

#import <unordered_map>
#import "DB.h"
#import "Location.pb.h"
#import "Mutex.h"
#import "Placemark.pb.h"
#import "ScopedHandle.h"

class AppState;

// The PlacemarkTable class maintains the mappings:
//   <location> -> <Placemark>
//
// PlacemarkTable and PlacemarkHandle are thread-safe, but individual
// Placemarks are not.
//
// Note that we use exact location comparison. This is pessimistic, but ok
// since we expect to have identical locations when a user takes multiple
// pictures at the same location.
class PlacemarkTable {
 public:
  class PlacemarkData : public Placemark {
    friend class PlacemarkTable;
    friend class ScopedHandle<PlacemarkData>;

   public:
    void SaveAndUnlock(const DBHandle& updates);

    void Lock() {
      mu_.Lock();
      locked_ = true;
    }

    void Unlock() {
      locked_ = false;
      mu_.Unlock();
    }

    bool valid() { return valid_; }
    const Location& location() const { return location_; }

   private:
    PlacemarkData(PlacemarkTable* table, const Location& location,
                  const string& key);

    void Load(const DBHandle& db);

    // Increments the content reference count. Only used by PlacemarkHandle.
    void Ref() {
      refcount_.Ref();
    }

    // Calls content table to decrement reference count and delete the content
    // if this is the last remaining reference. Only used by PlacemarkHandle.
    void Unref() {
      table_->ReleasePlacemark(this);
    }

   private:
    PlacemarkTable* const table_;
    const Location location_;
    const string key_;
    AtomicRefCount refcount_;
    Mutex mu_;
    bool locked_;
    bool valid_;
  };

  typedef ScopedHandle<PlacemarkData> PlacemarkHandle;

 public:
  PlacemarkTable(AppState* state);
  ~PlacemarkTable();

  static bool IsLocationValid(const Location& location);
  static bool IsPlacemarkValid(const Placemark& placemark);

  // Retrieve the placemark for the specified location. This will create a new
  // placemark (with Placemark::valid() == false) if one doesn't exist.
  PlacemarkHandle FindPlacemark(const Location& location, const DBHandle& db);

  // Return a count of the number of referenced placemarks.
  int referenced_placemarks() const {
    MutexLock l(&mu_);
    return placemarks_.size();
  }

 private:
  void ReleasePlacemark(PlacemarkData* p);

 private:
  mutable Mutex mu_;
  std::unordered_map<string, PlacemarkData*> placemarks_;
};

typedef PlacemarkTable::PlacemarkHandle PlacemarkHandle;

string EncodePlacemarkKey(const Location& l);
bool DecodePlacemarkKey(Slice key, Location* l);

#endif  // VIEWFINDER_PLACEMARK_TABLE_H

// local variables:
// mode: c++
// end:
