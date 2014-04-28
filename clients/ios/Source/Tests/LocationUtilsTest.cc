// Copyright 2012 Viewfinder. All rights reserved.
// Author: Peter Mattis.

#ifdef TESTING

#include "LocationUtils.h"
#include "Placemark.pb.h"
#include "Testing.h"

namespace {

TEST(LocationUtilsTest, StateAbbrev) {
  EXPECT_EQ("AL", USStateAbbrev("Alabama"));
  EXPECT_EQ("AK", USStateAbbrev("Alaska"));
  EXPECT_EQ("AZ", USStateAbbrev("Arizona"));
  EXPECT_EQ("AR", USStateAbbrev("Arkansas"));
  EXPECT_EQ("CA", USStateAbbrev("California"));
  EXPECT_EQ("CO", USStateAbbrev("Colorado"));
  EXPECT_EQ("CT", USStateAbbrev("Connecticut"));
  EXPECT_EQ("DE", USStateAbbrev("Delaware"));
  EXPECT_EQ("FL", USStateAbbrev("Florida"));
  EXPECT_EQ("GA", USStateAbbrev("Georgia"));
  EXPECT_EQ("HI", USStateAbbrev("Hawaii"));
  EXPECT_EQ("ID", USStateAbbrev("Idaho"));
  EXPECT_EQ("IL", USStateAbbrev("Illinois"));
  EXPECT_EQ("IN", USStateAbbrev("Indiana"));
  EXPECT_EQ("IA", USStateAbbrev("Iowa"));
  EXPECT_EQ("KS", USStateAbbrev("Kansas"));
  EXPECT_EQ("KY", USStateAbbrev("Kentucky"));
  EXPECT_EQ("LA", USStateAbbrev("Louisiana"));
  EXPECT_EQ("ME", USStateAbbrev("Maine"));
  EXPECT_EQ("MD", USStateAbbrev("Maryland"));
  EXPECT_EQ("MA", USStateAbbrev("Massachusetts"));
  EXPECT_EQ("MI", USStateAbbrev("Michigan"));
  EXPECT_EQ("MN", USStateAbbrev("Minnesota"));
  EXPECT_EQ("MS", USStateAbbrev("Mississippi"));
  EXPECT_EQ("MO", USStateAbbrev("Missouri"));
  EXPECT_EQ("MT", USStateAbbrev("Montana"));
  EXPECT_EQ("NE", USStateAbbrev("Nebraska"));
  EXPECT_EQ("NV", USStateAbbrev("Nevada"));
  EXPECT_EQ("NH", USStateAbbrev("New Hampshire"));
  EXPECT_EQ("NJ", USStateAbbrev("New Jersey"));
  EXPECT_EQ("NM", USStateAbbrev("New Mexico"));
  EXPECT_EQ("NY", USStateAbbrev("New York"));
  EXPECT_EQ("NC", USStateAbbrev("North Carolina"));
  EXPECT_EQ("ND", USStateAbbrev("North Dakota"));
  EXPECT_EQ("OH", USStateAbbrev("Ohio"));
  EXPECT_EQ("OK", USStateAbbrev("Oklahoma"));
  EXPECT_EQ("OR", USStateAbbrev("Oregon"));
  EXPECT_EQ("PA", USStateAbbrev("Pennsylvania"));
  EXPECT_EQ("RI", USStateAbbrev("Rhode Island"));
  EXPECT_EQ("SC", USStateAbbrev("South Carolina"));
  EXPECT_EQ("SD", USStateAbbrev("South Dakota"));
  EXPECT_EQ("TN", USStateAbbrev("Tennessee"));
  EXPECT_EQ("TX", USStateAbbrev("Texas"));
  EXPECT_EQ("UT", USStateAbbrev("Utah"));
  EXPECT_EQ("VT", USStateAbbrev("Vermont"));
  EXPECT_EQ("VA", USStateAbbrev("Virginia"));
  EXPECT_EQ("WA", USStateAbbrev("Washington"));
  EXPECT_EQ("WV", USStateAbbrev("West Virginia"));
  EXPECT_EQ("WI", USStateAbbrev("Wisconsin"));
  EXPECT_EQ("WY", USStateAbbrev("Wyoming"));
}

TEST(LocationUtilsTest, StateAbbrevNotFound) {
  EXPECT_EQ("foo", USStateAbbrev("foo"));
}

Placemark GetNolitaPlacemark() {
  Placemark pm;
  pm.set_iso_country_code("US");
  pm.set_country("United States");
  pm.set_state("New York");
  pm.set_locality("New York City");
  pm.set_sublocality("NoLita");
  return pm;
}

Placemark GetNohoPlacemark() {
  Placemark pm;
  pm.set_iso_country_code("US");
  pm.set_country("United States");
  pm.set_state("New York");
  pm.set_locality("New York City");
  pm.set_sublocality("NoHo");
  return pm;
}

Placemark GetNewYorkNYPlacemark() {
  Placemark pm;
  pm.set_iso_country_code("US");
  pm.set_country("United States");
  pm.set_state("New York");
  pm.set_locality("New York");
  pm.set_sublocality("NoHo");
  return pm;
}

Placemark GetEastHamptonPlacemark() {
  Placemark pm;
  pm.set_iso_country_code("US");
  pm.set_country("United States");
  pm.set_state("New York");
  pm.set_locality("East Hampton");
  pm.set_sublocality("The Hamptons");
  return pm;
}

Placemark GetDomRepublicPlacemark() {
  Placemark pm;
  pm.set_iso_country_code("DO");
  pm.set_country("Republica Dominicana");
  pm.set_state("Maria Trinidad Sanchez");
  pm.set_locality("Cabrera");
  pm.set_sublocality("");
  return pm;
}

TEST(LocationUtilsTest, FormatPlacemarkWithReferencePlacemark) {
  Placemark nolita = GetNolitaPlacemark();
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, NULL, false, PM_SUBLOCALITY),
            "NoLita, New York City, New York, United States");
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, NULL, false, PM_LOCALITY),
            "New York City, New York, United States");
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, NULL, false, PM_STATE),
            "New York, United States");
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, NULL, false, PM_COUNTRY),
            "United States");

  Placemark noho = GetNohoPlacemark();
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, &noho, false, PM_SUBLOCALITY),
            "NoLita, New York City");
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, &noho, false, PM_LOCALITY),
            "New York City, New York");
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, &noho, true, PM_SUBLOCALITY),
            "NoLita, NYC");
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, &noho, true, PM_LOCALITY),
            "New York City, NY");

  Placemark nyny = GetNewYorkNYPlacemark();
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, &nyny, false, PM_SUBLOCALITY),
            "NoLita, New York City");
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, &nyny, false, PM_LOCALITY),
            "New York City, New York");

  Placemark eh = GetEastHamptonPlacemark();
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, &eh, false, PM_SUBLOCALITY),
            "NoLita, New York City, New York");
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, &eh, false, PM_LOCALITY),
            "New York City, New York");
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, &eh, true, PM_SUBLOCALITY),
            "New York City, NY");
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, &eh, true, PM_LOCALITY),
            "New York City, NY");

  Placemark dr = GetDomRepublicPlacemark();
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, &dr, false, PM_SUBLOCALITY),
            "NoLita, New York City, United States");
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, &dr, false, PM_LOCALITY),
            "New York City, United States");
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(nolita, &dr, true, PM_SUBLOCALITY),
            "New York City, USA");
  EXPECT_EQ(FormatPlacemarkWithReferencePlacemark(dr, &dr, true, PM_SUBLOCALITY),
            "Cabrera, MTS");
}

}  // namespace

#endif  // TESTING
