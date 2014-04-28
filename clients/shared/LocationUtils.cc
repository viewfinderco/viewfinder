// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#include <unordered_map>
#include "LazyStaticPtr.h"
#include "Location.pb.h"
#include "LocationUtils.h"
#include "Logging.h"
#include "Placemark.pb.h"
#include "STLUtils.h"
#include "StringUtils.h"

namespace {

const double kMeanEarthRadius = 6371 * 1000;
const double kPi = 3.14159265358979323846;

// Abbreviates a place name if the name is >= eight characters
// and contains more than one word by taking the first letter of each
// word. Returns true if the placename was successfully abbreviated,
// and stores the result in *abbrev.
bool MaybeAbbreviatePlacename(const string& placename, string* abbrev) {
  if (placename.length() >= 8) {
    vector<string> split = Split(placename, " ");
    if (split.size() > 1) {
      abbrev->clear();
      for (int i = 0; i < split.size(); ++i) {
        abbrev->append(split[i].substr(0, 1));
      }
      return true;
    }
  }
  return false;
}

// TODO(spencer): look into making unordered_map<Slice, Slice> work, which
//   would save some memory here.
class CountryAbbrevMap : public std::unordered_map<string, string> {
 public:
  CountryAbbrevMap() {
    const struct {
      const char* alpha_2;
      const char* alpha_3;
    } kData[] = {
      {"AF", "AFG"},
      {"AX", "ALA"},
      {"AL", "ALB"},
      {"DZ", "DZA"},
      {"AS", "ASM"},
      {"AD", "AND"},
      {"AO", "AGO"},
      {"AI", "AIA"},
      {"AQ", "ATA"},
      {"AG", "ATG"},
      {"AR", "ARG"},
      {"AM", "ARM"},
      {"AW", "ABW"},
      {"AU", "AUS"},
      {"AT", "AUT"},
      {"AZ", "AZE"},
      {"BS", "BHS"},
      {"BH", "BHR"},
      {"BD", "BGD"},
      {"BB", "BRB"},
      {"BY", "BLR"},
      {"BE", "BEL"},
      {"BZ", "BLZ"},
      {"BJ", "BEN"},
      {"BM", "BMU"},
      {"BT", "BTN"},
      {"BO", "BOL"},
      {"BQ", "BES"},
      {"BA", "BIH"},
      {"BW", "BWA"},
      {"BV", "BVT"},
      {"BR", "BRA"},
      {"IO", "IOT"},
      {"BN", "BRN"},
      {"BG", "BGR"},
      {"BF", "BFA"},
      {"BI", "BDI"},
      {"KH", "KHM"},
      {"CM", "CMR"},
      {"CA", "CAN"},
      {"CV", "CPV"},
      {"KY", "CYM"},
      {"CF", "CAF"},
      {"TD", "TCD"},
      {"CL", "CHL"},
      {"CN", "CHN"},
      {"CX", "CXR"},
      {"CC", "CCK"},
      {"CO", "COL"},
      {"KM", "COM"},
      {"CG", "COG"},
      {"CD", "COD"},
      {"CK", "COK"},
      {"CR", "CRI"},
      {"CI", "CIV"},
      {"HR", "HRV"},
      {"CU", "CUB"},
      {"CW", "CUW"},
      {"CY", "CYP"},
      {"CZ", "CZE"},
      {"DK", "DNK"},
      {"DJ", "DJI"},
      {"DM", "DMA"},
      {"DO", "DOM"},
      {"EC", "ECU"},
      {"EG", "EGY"},
      {"SV", "SLV"},
      {"GQ", "GNQ"},
      {"ER", "ERI"},
      {"EE", "EST"},
      {"ET", "ETH"},
      {"FK", "FLK"},
      {"FO", "FRO"},
      {"FJ", "FJI"},
      {"FI", "FIN"},
      {"FR", "FRA"},
      {"GF", "GUF"},
      {"PF", "PYF"},
      {"TF", "ATF"},
      {"GA", "GAB"},
      {"GM", "GMB"},
      {"GE", "GEO"},
      {"DE", "DEU"},
      {"GH", "GHA"},
      {"GI", "GIB"},
      {"GR", "GRC"},
      {"GL", "GRL"},
      {"GD", "GRD"},
      {"GP", "GLP"},
      {"GU", "GUM"},
      {"GT", "GTM"},
      {"GG", "GGY"},
      {"GN", "GIN"},
      {"GW", "GNB"},
      {"GY", "GUY"},
      {"HT", "HTI"},
      {"HM", "HMD"},
      {"VA", "VAT"},
      {"HN", "HND"},
      {"HK", "HKG"},
      {"HU", "HUN"},
      {"IS", "ISL"},
      {"IN", "IND"},
      {"ID", "IDN"},
      {"IR", "IRN"},
      {"IQ", "IRQ"},
      {"IE", "IRL"},
      {"IM", "IMN"},
      {"IL", "ISR"},
      {"IT", "ITA"},
      {"JM", "JAM"},
      {"JP", "JPN"},
      {"JE", "JEY"},
      {"JO", "JOR"},
      {"KZ", "KAZ"},
      {"KE", "KEN"},
      {"KI", "KIR"},
      {"KP", "PRK"},
      {"KR", "KOR"},
      {"KW", "KWT"},
      {"KG", "KGZ"},
      {"LA", "LAO"},
      {"LV", "LVA"},
      {"LB", "LBN"},
      {"LS", "LSO"},
      {"LR", "LBR"},
      {"LY", "LBY"},
      {"LI", "LIE"},
      {"LT", "LTU"},
      {"LU", "LUX"},
      {"MO", "MAC"},
      {"MK", "MKD"},
      {"MG", "MDG"},
      {"MW", "MWI"},
      {"MY", "MYS"},
      {"MV", "MDV"},
      {"ML", "MLI"},
      {"MT", "MLT"},
      {"MH", "MHL"},
      {"MQ", "MTQ"},
      {"MR", "MRT"},
      {"MU", "MUS"},
      {"YT", "MYT"},
      {"MX", "MEX"},
      {"FM", "FSM"},
      {"MD", "MDA"},
      {"MC", "MCO"},
      {"MN", "MNG"},
      {"ME", "MNE"},
      {"MS", "MSR"},
      {"MA", "MAR"},
      {"MZ", "MOZ"},
      {"MM", "MMR"},
      {"NA", "NAM"},
      {"NR", "NRU"},
      {"NP", "NPL"},
      {"NL", "NLD"},
      {"NC", "NCL"},
      {"NZ", "NZL"},
      {"NI", "NIC"},
      {"NE", "NER"},
      {"NG", "NGA"},
      {"NU", "NIU"},
      {"NF", "NFK"},
      {"MP", "MNP"},
      {"NO", "NOR"},
      {"OM", "OMN"},
      {"PK", "PAK"},
      {"PW", "PLW"},
      {"PS", "PSE"},
      {"PA", "PAN"},
      {"PG", "PNG"},
      {"PY", "PRY"},
      {"PE", "PER"},
      {"PH", "PHL"},
      {"PN", "PCN"},
      {"PL", "POL"},
      {"PT", "PRT"},
      {"PR", "PRI"},
      {"QA", "QAT"},
      {"RE", "REU"},
      {"RO", "ROU"},
      {"RU", "RUS"},
      {"RW", "RWA"},
      {"BL", "BLM"},
      {"SH", "SHN"},
      {"KN", "KNA"},
      {"LC", "LCA"},
      {"MF", "MAF"},
      {"PM", "SPM"},
      {"VC", "VCT"},
      {"WS", "WSM"},
      {"SM", "SMR"},
      {"ST", "STP"},
      {"SA", "SAU"},
      {"SN", "SEN"},
      {"RS", "SRB"},
      {"SC", "SYC"},
      {"SL", "SLE"},
      {"SG", "SGP"},
      {"SX", "SXM"},
      {"SK", "SVK"},
      {"SI", "SVN"},
      {"SB", "SLB"},
      {"SO", "SOM"},
      {"ZA", "ZAF"},
      {"GS", "SGS"},
      {"SS", "SSD"},
      {"ES", "ESP"},
      {"LK", "LKA"},
      {"SD", "SDN"},
      {"SR", "SUR"},
      {"SJ", "SJM"},
      {"SZ", "SWZ"},
      {"SE", "SWE"},
      {"CH", "CHE"},
      {"SY", "SYR"},
      {"TW", "TWN"},
      {"TJ", "TJK"},
      {"TZ", "TZA"},
      {"TH", "THA"},
      {"TL", "TLS"},
      {"TG", "TGO"},
      {"TK", "TKL"},
      {"TO", "TON"},
      {"TT", "TTO"},
      {"TN", "TUN"},
      {"TR", "TUR"},
      {"TM", "TKM"},
      {"TC", "TCA"},
      {"TV", "TUV"},
      {"UG", "UGA"},
      {"UA", "UKR"},
      {"AE", "ARE"},
      {"GB", "GBR"},
      {"US", "USA"},
      {"UM", "UMI"},
      {"UY", "URY"},
      {"UZ", "UZB"},
      {"VU", "VUT"},
      {"VE", "VEN"},
      {"VN", "VNM"},
      {"VG", "VGB"},
      {"VI", "VIR"},
      {"WF", "WLF"},
      {"EH", "ESH"},
      {"YE", "YEM"},
      {"ZM", "ZMB"},
      {"ZW", "ZWE"},
    };
    for (int i = 0; i < ARRAYSIZE(kData); ++i) {
      (*this)[kData[i].alpha_2] = kData[i].alpha_3;
    }
  }
};

LazyStaticPtr<CountryAbbrevMap> kCountryAbbrevMap;

class StateAbbrevMap : public std::unordered_map<string, string> {
 public:
  StateAbbrevMap() {
    const struct {
      const char* state;
      const char* abbrev;
    } kData[] = {
      { "Alabama", "AL" },
      { "Alaska", "AK" },
      { "Arizona", "AZ" },
      { "Arkansas", "AR" },
      { "California", "CA" },
      { "Colorado", "CO" },
      { "Connecticut", "CT" },
      { "Delaware", "DE" },
      { "Florida", "FL" },
      { "Georgia", "GA" },
      { "Hawaii", "HI" },
      { "Idaho", "ID" },
      { "Illinois", "IL" },
      { "Indiana", "IN" },
      { "Iowa", "IA" },
      { "Kansas", "KS" },
      { "Kentucky", "KY" },
      { "Louisiana", "LA" },
      { "Maine", "ME" },
      { "Maryland", "MD" },
      { "Massachusetts", "MA" },
      { "Michigan", "MI" },
      { "Minnesota", "MN" },
      { "Mississippi", "MS" },
      { "Missouri", "MO" },
      { "Montana", "MT" },
      { "Nebraska", "NE" },
      { "Nevada", "NV" },
      { "New Hampshire", "NH" },
      { "New Jersey", "NJ" },
      { "New Mexico", "NM" },
      { "New York", "NY" },
      { "North Carolina", "NC" },
      { "North Dakota", "ND" },
      { "Ohio", "OH" },
      { "Oklahoma", "OK" },
      { "Oregon", "OR" },
      { "Pennsylvania", "PA" },
      { "Rhode Island", "RI" },
      { "South Carolina", "SC" },
      { "South Dakota", "SD" },
      { "Tennessee", "TN" },
      { "Texas", "TX" },
      { "Utah", "UT" },
      { "Vermont", "VT" },
      { "Virginia", "VA" },
      { "Washington", "WA" },
      { "West Virginia", "WV" },
      { "Wisconsin", "WI" },
      { "Wyoming", "WY" },
    };
    for (int i = 0; i < ARRAYSIZE(kData); ++i) {
      (*this)[kData[i].state] = kData[i].abbrev;
    }
  }
};

LazyStaticPtr<StateAbbrevMap> kStateAbbrevMap;

// Check whether either locality is a substring of the other. This
// handles differences in geo database names which drop the "city"
// suffix, and other similar (e.g. 'New York City' vs. 'New York').
bool LocalityMatch(const string& l1, const string& l2) {
  if (l1.find(l2) != l1.npos || l2.find(l1) != l2.npos) {
    return true;
  }
  return false;
}

}  // namespace


string FormatPlacemarkWithReferencePlacemark(
    const Placemark& pm, const Placemark* ref_pm, bool short_location,
    PlacemarkLevel min_level, int max_parts) {
  const string* parts[4] = {
    (min_level <= PM_SUBLOCALITY) ? &pm.sublocality() : NULL,
    &pm.locality(),
    &pm.state(),
    &pm.country(),
  };

  // Treat the sublocality as the locality if the locality is not present.
  if (!pm.has_locality() && pm.has_sublocality() && !pm.sublocality().empty()) {
    parts[1] = &pm.sublocality();
    parts[0] = NULL;
  }

  if (ref_pm) {
    // If the sublocality is present, but the country, state or city
    // are not the same as the reference placemark and short_location
    // is true, remove the sublocality.
    if (short_location && parts[0] != NULL &&
        (*parts[3] != ref_pm->country() ||
         *parts[2] != ref_pm->state() ||
         !LocalityMatch(*parts[1], ref_pm->locality()))) {
      parts[0] = NULL;
    }

    if (*parts[3] == ref_pm->country()) {
      // Skip the country if it's the same as the reference placemark's.
      parts[3] = NULL;
      if (*parts[2] == ref_pm->state() &&
          LocalityMatch(*parts[1], ref_pm->locality()) &&
          parts[0] != NULL && !parts[0]->empty()) {
        // Skip the state if it's the same as the reference placemark's
        // and the locality is the same as our current location...but
        // only if there's a valid sublocality.
        parts[2] = NULL;
      }
    } else {
      // Skip the state if the country is not the same as the
      // reference placemark's, but not if there's no locality. For
      // example, "Cabrera, Maria Trinidad Sanchez, Dominican
      // Republic" would become "Cabrera, Dominican Republic" if the
      // reference placemark is not in the Dominican Republic.
      // However, "Andhra Pradesh, India" won't just become "India".
      if (parts[1] != NULL && !parts[1]->empty()) {
        parts[2] = NULL;
      }
    }
  }

  string country_abbrev;
  string state_abbrev;
  string locality_abbrev;
  if (short_location) {
    // Try to abbreviate the city name if it's the same as the
    // reference placemark's. and there's also a sublocality. For
    // example, ("New York City" => "NYC").
    if (parts[0] != NULL && !parts[0]->empty() &&
        parts[1] != NULL && !parts[1]->empty() &&
        ref_pm && LocalityMatch(*parts[1], ref_pm->locality())) {
      if (MaybeAbbreviatePlacename(*parts[1], &locality_abbrev)) {
        parts[1] = &locality_abbrev;
      }
    }
    if (parts[2] && !parts[2]->empty()) {
      if (pm.iso_country_code() == "US") {
        state_abbrev = USStateAbbrev(pm.state());
        parts[2] = &state_abbrev;
      } else if ((parts[0] != NULL && !parts[0]->empty()) ||
                 (parts[1] != NULL && !parts[1]->empty())) {
        // If not a US state, then abbreviate long state names with
        // multiple words if we have the locality or sublocality.
        if (MaybeAbbreviatePlacename(*parts[2], &state_abbrev)) {
          parts[2] = &state_abbrev;
        }
      }
    }
    if (parts[3] && !parts[3]->empty()) {
      country_abbrev = CountryAbbrev(pm.iso_country_code());
      parts[3] = &country_abbrev;
    }
  }

  string location;
  const string* prev_part = NULL;
  int parts_used = 0;
  for (int i = min_level; i < ARRAYSIZE(parts); ++i) {
    if (!parts[i] || parts[i]->empty()) {
      continue;
    }
    if (prev_part && *prev_part == *parts[i]) {
      // Skip the part if it is equal to the previous part.
      continue;
    }
    if (!location.empty()) {
      location += ", ";
    }
    location += *parts[i];
    prev_part = parts[i];
    parts_used++;
    if (max_parts > 0 && parts_used >= max_parts) {
      break;
    }
  }

  return location;
}

string CountryAbbrev(const string& alpha_2) {
  return FindOrDefault(*kCountryAbbrevMap, alpha_2, alpha_2);
}

string USStateAbbrev(const string& state) {
  return FindOrDefault(*kStateAbbrevMap, state, state);
}

// Use the Haversine formula to determine the great-circle distance between 2
// points.
double DistanceBetweenLocations(const Location& a, const Location& b) {
  const double lat1 = a.latitude() * kPi / 180;
  const double lng1 = a.longitude() * kPi / 180;
  const double lat2 = b.latitude() * kPi / 180;
  const double lng2 = b.longitude() * kPi / 180;
  const double sin_dlat_2 = sin((lat2 - lat1) / 2);
  const double sin_dlng_2 = sin((lng2 - lng1) / 2);
  const double t = (sin_dlat_2 * sin_dlat_2) +
      (cos(lat1) * cos(lat2) * sin_dlng_2 * sin_dlng_2);
  return 2 * atan2(sqrt(t), sqrt(1 - t)) * kMeanEarthRadius;
}
