// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#import "AppState.h"
#import "PlacemarkTable.h"

namespace {

const string kPlacemarkKeyPrefix = DBFormat::placemark_key("");

const DBRegisterKeyIntrospect kPlacemarkKeyIntrospect(
    kPlacemarkKeyPrefix,
    [](Slice key) {
      Location l;
      if (!DecodePlacemarkKey(key, &l)) {
        return string();
      }
      return string(Format("%.6f,%.6f", l.latitude(), l.longitude()));
    },
    [](Slice value) {
      return DBIntrospect::FormatProto<Placemark>(value);
    });

void EncodeDouble(string* s, double v) {
  int64_t i;
  memcpy(&i, &v, sizeof(i));
  OrderedCodeEncodeVarint64(s, i);
}

double DecodeDouble(Slice* s) {
  const int64_t i = OrderedCodeDecodeVarint64(s);
  double d;
  memcpy(&d, &i, sizeof(i));
  return d;
}

}  // namespace

string EncodePlacemarkKey(const Location& l) {
  string s(kPlacemarkKeyPrefix);
  EncodeDouble(&s, l.latitude());
  EncodeDouble(&s, l.longitude());
  // We intentionally do not use Location::accuracy or Location::altitude here.
  return s;
}

bool DecodePlacemarkKey(Slice key, Location* l) {
  if (!key.starts_with(kPlacemarkKeyPrefix)) {
    return false;
  }
  key.remove_prefix(kPlacemarkKeyPrefix.size());
  l->set_latitude(DecodeDouble(&key));
  l->set_longitude(DecodeDouble(&key));
  return true;
}

PlacemarkTable::PlacemarkData::PlacemarkData(
    PlacemarkTable* table, const Location& location, const string& key)
    : table_(table),
      location_(location),
      key_(key),
      locked_(false),
      valid_(false) {
}

void PlacemarkTable::PlacemarkData::Load(const DBHandle& db) {
  valid_ = db->GetProto(EncodePlacemarkKey(location_), this);
}

void PlacemarkTable::PlacemarkData::SaveAndUnlock(const DBHandle& updates) {
  CHECK(locked_);
  updates->PutProto(EncodePlacemarkKey(location_), *this);
  valid_ = true;
  Unlock();
}

PlacemarkTable::PlacemarkTable(AppState* state) {
}

PlacemarkTable::~PlacemarkTable() {
}

bool PlacemarkTable::IsLocationValid(const Location& location) {
  // Disallow almost-certainly problematic 0,0 case.
  if (!location.has_latitude() || !location.has_longitude() ||
      (location.latitude() == 0 && location.longitude() == 0)) {
    return false;
  }
  return true;
}

bool PlacemarkTable::IsPlacemarkValid(const Placemark& placemark) {
  return placemark.has_country() || placemark.has_state() ||
      placemark.has_locality();
}

PlacemarkTable::PlacemarkHandle PlacemarkTable::FindPlacemark(
    const Location& location, const DBHandle& db) {
  MutexLock l(&mu_);
  const string key = EncodePlacemarkKey(location);
  PlacemarkData*& p = placemarks_[key];
  if (!p) {
    p = new PlacemarkData(this, location, key);
    p->Load(db);
  }
  return PlacemarkHandle(p);
}

void PlacemarkTable::ReleasePlacemark(PlacemarkData* p) {
  MutexLock l(&mu_);
  if (p->refcount_.Unref()) {
    placemarks_.erase(p->key_);
    delete p;
  }
}

// local variables:
// mode: c++
// end:
