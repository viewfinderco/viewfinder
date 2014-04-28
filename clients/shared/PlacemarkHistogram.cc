// Copyright 2012 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import <re2/re2.h>
#import "AppState.h"
#import "Breadcrumb.pb.h"
#import "DB.h"
#import "LazyStaticPtr.h"
#import "LocationUtils.h"
#import "Logging.h"
#import "PhotoMetadata.pb.h"
#import "PlacemarkHistogram.h"
#import "STLUtils.h"
#import "StringUtils.h"

namespace {

const string kFormatKey = DBFormat::metadata_key("placemark_histogram_format");
const string kFormatValue = "4";
const string kTotalCountKey = DBFormat::metadata_key("placemark_histogram_count");
// The weightiest placemarks in the histogram up to this percentile
// will be kept in-memory and returned from calls to
// DistanceToTopPlacemark().
const float kTopPercentile = 0.90;
// A top location must account for this percentage of total photos.
const float kMinPercentile = 0.10;
// No more than this count of top placemarks will be kept in-memory.
const int kTopMaxCount = 5;
// A top location must have at least this many sublocalities, and each
// must have at least this percent of the total count for
// sublocalities to be considered useful.
const int kSublocalityMinCount = 3;
const int kSublocalityMaxCount = 10;
const float kSublocalityMinFraction = 0.05;
const double kHomeVsAwayThresholdDistanceMeters = 100 * 1000;  // 100 km

LazyStaticPtr<RE2, const char*> kSortKeyRE = { "phs/([[:digit:]]+)/(.*)" };

// Lowercases provided string and replaces all instances of
// ':' with '-' characters.
string CanonicalizePlaceName(const string& name) {
  string lower = ToLowercase(name);
  std::replace(lower.begin(), lower.end(), ':', '-');
  return lower;
}

// Returns the canonical placemark is which country:state:locality.
string GetCanonicalPlacemark(const Placemark& pm) {
  return Format("%s:%s:%s",
                CanonicalizePlaceName(pm.country()),
                CanonicalizePlaceName(pm.state()),
                CanonicalizePlaceName(pm.locality()));
}

// Returns the key for the placemark's histogram entry.
string GetEntryKey(const Placemark& pm) {
  const string canon_pm_key = GetCanonicalPlacemark(pm);
  return DBFormat::placemark_histogram_key(canon_pm_key);
}

// Returns the key for the sorted placemark histogram entry.
// Reverse the weight by subtracting from 2^32-1 so the
// sort keys go from highest weight to lowest.
string GetSortedEntryKey(const Placemark& pm, int weight) {
  const string canon_pm_key = GetCanonicalPlacemark(pm);
  CHECK_LE(weight, 0x7fffffff);
  return DBFormat::placemark_histogram_sort_key(
      canon_pm_key, 0x7fffffff - weight);
}

struct SublocalityGreaterThan {
  bool operator()(const PlacemarkHistogramEntry::Sublocality* a,
                  const PlacemarkHistogramEntry::Sublocality* b) const {
    if (a->count() != b->count()) {
      return a->count() > b->count();
    }
    return a->name() < b->name();
  }
};

}  // namespace

// The minimum amount of time between placemark histogram inits.
const double PlacemarkHistogram::kMinRefreshIntervalSeconds = 60;

PlacemarkHistogram::PlacemarkHistogram(AppState* state)
    : state_(state),
      need_refresh_(true),
      last_refresh_(0),
      total_count_(state_->db()->Get<int>(kTotalCountKey, 0)) {
  const bool format_changed =
      (state_->db()->Get<string>(kFormatKey) != kFormatValue);

  if (format_changed) {
    DBHandle updates = state_->NewDBTransaction();

    // Delete all placemark entries and sort keys.
    for (DB::PrefixIterator iter(updates, DBFormat::placemark_histogram_key());
         iter.Valid();
         iter.Next()) {
      updates->Delete(iter.key());
    }
    for (DB::PrefixIterator iter(updates, DBFormat::placemark_histogram_sort_key());
         iter.Valid();
         iter.Next()) {
      updates->Delete(iter.key());
    }
    // Build histogram with placemarked photos.
    total_count_ = 0;
    for (DB::PrefixIterator iter(updates, DBFormat::photo_key());
         iter.Valid();
         iter.Next()) {
      const Slice key = iter.key();
      const Slice value = iter.value();
      PhotoMetadata p;
      if (!p.ParseFromArray(value.data(), value.size())) {
        LOG("placemark-histogram: unable to parse PhotoMetadata: %s", key);
      } else if (p.has_location() && p.has_placemark()) {
        UpdateHistogram(p.placemark(), p.location(), 1, updates);
      }
    }

    updates->Put(kFormatKey, kFormatValue);
    updates->Commit();
    LOG("placemark-histogram: built histogram from %d placemarked photo%s",
        total_count_, Pluralize(total_count_));
  }
}

PlacemarkHistogram::~PlacemarkHistogram() {
}

PlacemarkHistogram::TopPlacemark::TopPlacemark(
    const PlacemarkHistogramEntry& e, const int total_count)
    : placemark(e.placemark()),
      weight(e.count() / total_count),
      useful_sublocality(false) {
  // Compute location centroid.
  if (e.count() > 0) {
    centroid.set_latitude(e.location_sum().latitude() / e.count());
    centroid.set_longitude(e.location_sum().longitude() / e.count());
    centroid.set_accuracy(e.location_sum().accuracy() / e.count());
    centroid.set_altitude(e.location_sum().altitude() / e.count());
  }
  // Determine whether the sublocalities which are part of this top
  // location provide enough differentiation to be useful.
  vector<int> counts;
  int sublocality_count = 0;
  for (int i = 0; i < e.sublocalities_size(); ++i) {
    counts.push_back(e.sublocalities(i).count());
    sublocality_count += e.sublocalities(i).count();
  }
  // Reverse sort counts from largest to smallest. If a minimum number
  // meet the minimal percentile threshold, we conclude that
  // sublocalities will be a "useful" addition to this location.
  std::sort(counts.begin(), counts.end(), std::greater<int>());
  if (counts.size() >= kSublocalityMaxCount ||
      (counts.size() >= kSublocalityMinCount &&
       (float(counts[kSublocalityMinCount - 1]) / sublocality_count) >= kSublocalityMinFraction)) {
    useful_sublocality = true;
  }
}

void PlacemarkHistogram::AddPlacemark(const Placemark& placemark,
                                      const Location& location,
                                      const DBHandle& updates) {
  // LOG("adding placemark %s, location %s", placemark, location);
  UpdateHistogram(placemark, location, 1, updates);
}

void PlacemarkHistogram::RemovePlacemark(const Placemark& placemark,
                                         const Location& location,
                                         const DBHandle& updates) {
  // LOG("removing placemark %s, location %s", placemark, location);
  UpdateHistogram(placemark, location, -1, updates);
}

bool PlacemarkHistogram::DistanceToTopPlacemark(const Location& location,
                                                double* distance,
                                                TopPlacemark* top_placemark) {
  const TopPlacemark* closest = FindClosestTopPlacemark(location);
  if (!closest) {
    return false;
  }
  if (top_placemark) {
    *top_placemark = *closest;
  }
  *distance = DistanceBetweenLocations(closest->centroid, location);
  return true;
}

bool PlacemarkHistogram::DistanceToLocation(
    const Location& location, double* distance,
    PlacemarkHistogram::TopPlacemark* top) {
  // Find the closest top placemark and format the specified photo's
  // placemark relative to it.
  if (!DistanceToTopPlacemark(location, distance, top)) {
    const Breadcrumb* bc = state_->last_breadcrumb();
    if (!bc) {
      return false;
    }
    *distance = DistanceBetweenLocations(bc->location(), location);
  }
  return true;
}

void PlacemarkHistogram::FormatLocation(
    const Location& location, const Placemark& placemark,
    bool short_location, string* s) {
  // Find the closest top placemark and format the specified photo's
  // placemark relative to it. If there is no top placemark, use
  // the current breadcrumb's placemark.
  const Placemark* ref_pm;
  bool use_sublocality = false;
  double distance;
  TopPlacemark top;
  if (DistanceToTopPlacemark(location, &distance, &top)) {
    ref_pm = &top.placemark;
    use_sublocality = (top.useful_sublocality &&
                       distance < kHomeVsAwayThresholdDistanceMeters);
    // TODO(peter): Remove the dependency on LocationTracker.
  } else if (state_->last_breadcrumb()) {
    ref_pm = &state_->last_breadcrumb()->placemark();
  } else {
    ref_pm = NULL;
  }

  *s = FormatPlacemarkWithReferencePlacemark(
      placemark, ref_pm, short_location,
      use_sublocality ? PM_SUBLOCALITY : PM_LOCALITY);
}

void PlacemarkHistogram::FormatLocality(
    const Location& location, const Placemark& placemark, string* s) {
  double distance;
  TopPlacemark top;
  if (DistanceToLocation(location, &distance, &top) &&
      distance < kHomeVsAwayThresholdDistanceMeters &&
      top.useful_sublocality) {
    *s = placemark.sublocality();
    return;
  }
  *s = placemark.locality();
}

void PlacemarkHistogram::MaybeInitTopPlacemarks() {
  MutexLock l(&mu_);
  if (!need_refresh_ ||
      (last_refresh_ != 0 &&
       (state_->WallTime_Now() - last_refresh_) < kMinRefreshIntervalSeconds)) {
    return;
  }
  top_placemarks_.clear();
  need_refresh_ = false;
  last_refresh_ = state_->WallTime_Now();

  // Scan the placemark histogram entries by sort key which
  // provides an ordering over placemark entries by count.
  int count = 0;
  for (DB::PrefixIterator iter(state_->db(), DBFormat::placemark_histogram_sort_key());
       iter.Valid();
       iter.Next()) {
    const Slice key = iter.key();
    int weight;
    string canon_pm_key;
    if (!RE2::FullMatch(key, *kSortKeyRE, &weight, &canon_pm_key)) {
      LOG("placemark-histogram: unable to parse placemark hist entry key: %s", key);
      continue;
    }
    PlacemarkHistogramEntry phe;
    if (!state_->db()->GetProto(DBFormat::placemark_histogram_key(canon_pm_key), &phe)) {
      LOG("placemark-histogram: unable to find placemark %s", canon_pm_key);
      continue;
    }
    if ((count < kTopPercentile * total_count_) &&
        (phe.count() > kMinPercentile * total_count_) &&
        (top_placemarks_.size() < kTopMaxCount)) {
      count += phe.count();
      top_placemarks_.push_back(TopPlacemark(phe, total_count_));
      VLOG("placemark-histogram: placemark %d, %.1f%%, %.1f%%ile, %d sublocalities: %s",
           top_placemarks_.size(), phe.count() * 100.0 / total_count_,
           count * 100.0 / total_count_, phe.sublocalities_size(), phe.placemark());
      int sublocality_count = 0;
      for (int i = 0; i < std::min<int>(phe.sublocalities_size(), kSublocalityMinCount); ++i) {
        sublocality_count += phe.sublocalities(i).count();
        VLOG(" top sublocality %d: %.1f%%, %.1f%%ile: %s",
             i, phe.sublocalities(i).count() * 100.0 / phe.count(),
             sublocality_count * 100.0 / phe.count(),
             phe.sublocalities(i).name());
      }
      continue;
    }
    break;
  }
}

void PlacemarkHistogram::UpdateHistogram(const Placemark& placemark,
                                         const Location& location,
                                         int count,
                                         const DBHandle& updates) {
  MutexLock l(&mu_);
  PlacemarkHistogramEntry entry;

  if (LookupHistogramEntry(placemark, &entry, updates)) {
    // Remove the previous sorted key for the histogram entry.
    string prev_sort_key = GetSortedEntryKey(placemark, entry.count());
    updates->Delete(prev_sort_key);
    entry.mutable_location_sum()->set_latitude(
        entry.location_sum().latitude() + location.latitude() * count);
    entry.mutable_location_sum()->set_longitude(
        entry.location_sum().longitude() + location.longitude() * count);
    entry.mutable_location_sum()->set_accuracy(
        entry.location_sum().accuracy() + location.accuracy() * count);
    entry.mutable_location_sum()->set_altitude(
        entry.location_sum().altitude() + location.altitude() * count);
    entry.set_count(entry.count() + count);

    if (placemark.has_sublocality()) {
      // TODO(spencer): this almost certainly doesn't matter, but it
      //   is a linear search and we could easily enough keep the list
      //   of sublocalities sorted and do a binary search.
      PlacemarkHistogramEntry::Sublocality* sublocality = NULL;
      for (int i = 0; i < entry.sublocalities_size(); ++i) {
        if (entry.sublocalities(i).name() == placemark.sublocality()) {
          sublocality = entry.mutable_sublocalities(i);
          sublocality->set_count(sublocality->count() + count);
          if (sublocality->count() <= 0) {
            ProtoRepeatedFieldRemoveElement(entry.mutable_sublocalities(), i);
          }
          break;
        }
      }
      if (!sublocality && count > 0) {
        sublocality = entry.add_sublocalities();
        sublocality->set_name(placemark.sublocality());
        sublocality->set_count(count);
      }
      // Sort the sublocalities.
      std::sort(entry.mutable_sublocalities()->pointer_begin(),
                entry.mutable_sublocalities()->pointer_end(),
                SublocalityGreaterThan());
    }
  } else {
    if (count <= 0) {
      return;
    }
    *entry.mutable_placemark() = placemark;
    entry.mutable_placemark()->clear_sublocality();
    entry.mutable_placemark()->clear_thoroughfare();
    entry.mutable_placemark()->clear_subthoroughfare();
    *entry.mutable_location_sum() = location;
    entry.set_count(count);

    if (placemark.has_sublocality()) {
      PlacemarkHistogramEntry::Sublocality* sublocality = entry.add_sublocalities();
      sublocality->set_name(placemark.sublocality());
      sublocality->set_count(sublocality->count() + count);
    }
  }

  // Write the histogram entry and its sort key.
  string entry_key = GetEntryKey(placemark);
  if (entry.count() == 0) {
    updates->Delete(entry_key);
  } else {
    updates->PutProto(entry_key, entry);
    string sort_key = GetSortedEntryKey(placemark, entry.count());
    updates->Put(sort_key, "");
  }

  // Update the total histogram count.
  total_count_ += count;
  updates->Put(kTotalCountKey, total_count_);

  need_refresh_ = true;
}

const PlacemarkHistogram::TopPlacemark*
PlacemarkHistogram::FindClosestTopPlacemark(const Location& location) {
  MaybeInitTopPlacemarks();

  int closest_index = -1;
  double closest_distance = std::numeric_limits<double>::max();

  for (int i = 0; i < top_placemarks_.size(); ++i) {
    const TopPlacemark& top_placemark = top_placemarks_[i];
    double distance = DistanceBetweenLocations(top_placemark.centroid, location);
    if (closest_index == -1 || distance < closest_distance) {
      closest_index = i;
      closest_distance = distance;
    }
  }
  return closest_index == -1 ? NULL : &top_placemarks_[closest_index];
}

bool PlacemarkHistogram::LookupHistogramEntry(const Placemark& placemark,
                                              PlacemarkHistogramEntry* entry,
                                              const DBHandle& db) {
  const string key = GetEntryKey(placemark);
  if (!db->GetProto(key, entry)) {
    // LOG("placemark-histogram: unable to find placemark %s", key);
    return false;
  }

  return true;
}

// local variables:
// mode: c++
// end:
