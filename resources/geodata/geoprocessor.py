# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Parses the cities1000.txt geonames database and builds a tiered
set of data structures for efficiently mapping placename prefixes to
latitude and longitude coordinates.

Datafile sourced from: http://download.geonames.org/.

IMPORTANT, Copyright: This work is licensed under a Creative Commons
Attribution 3.0 License.  This means you can use the dump as long as
you give credit to geonames (a link on your website to
www.geonames.org is ok) see
http://creativecommons.org/licenses/by/3.0/

The data structures necessarily follow the mechanics of data input.
To facilitate maximum speed and minimum bandwidth, the first data file
contains only the most populous cities. As soon as the first key is
pressed, the cities starting with that character which fall into the
ranks of the most populous are displayed. Immediately, the data file
corresponding to all cities starting with that first character is
loaded. This data file contains additional cities of lesser population
with no overlap with the first data file. The same format continues
until all cities have been covered.

The successive cutoffs for cities are determined by the
--datafile_size option and by the density of city names within a
particular range of placename prefixes.

Output is written to files of the format %d.%d in an output
subdirectory specified via --output_dir.

For a list of world cities with overweight inclusion of US cities, use:

% python geoprocessor.py --pop_filter=500000 --user_city_boost=5


The main 'geoname' table has the following fields :
---------------------------------------------------
geonameid         : integer id of record in geonames database
name              : name of geographical point (utf8) varchar(200)
asciiname         : name of geographical point in plain ascii characters, varchar(200)
alternatenames    : alternatenames, comma separated varchar(5000)
latitude          : latitude in decimal degrees (wgs84)
longitude         : longitude in decimal degrees (wgs84)
feature class     : see http://www.geonames.org/export/codes.html, char(1)
feature code      : see http://www.geonames.org/export/codes.html, varchar(10)
country code      : ISO-3166 2-letter country code, 2 characters
cc2               : alternate country codes, comma separated, ISO-3166 2-letter country code, 60 characters
admin1 code       : fipscode (subject to change to iso code), see exceptions below, see file admin1Codes.txt for display names of this code; varchar(20)
admin2 code       : code for the second administrative division, a county in the US, see file admin2Codes.txt; varchar(80)
admin3 code       : code for third level administrative division, varchar(20)
admin4 code       : code for fourth level administrative division, varchar(20)
population        : bigint (8 byte int)
elevation         : in meters, integer
dem               : digital elevation model, srtm3 or gtopo30, average elevation of 3''x3'' (ca 90mx90m) or 30''x30'' (ca 900mx900m) area in meters, integer. srtm processed by cgiar/ciat.
timezone          : the timezone id (see file timeZone.txt) varchar(40)
modification date : date of last modification in yyyy-MM-dd format

"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import codecs
import json
import locale
import logging
import os
import s2
import string
import sys

from bisect import bisect_left, bisect_right
from collections import namedtuple
from functools import partial
from operator import attrgetter
from tornado import options

options.define('cityfile', default='cities1000.txt', help='geonames datafile to parse')
options.define('uspostalfile', default='US_postal.txt', help='geonames datafile of US postal info')
options.define('output_dir', default='geodb/', help='subdirectory for geoname database output files')
options.define('datafile_size', default=1000, help='approximate number of places in a datafile')
options.define('ascii_names', default=False, help='include ascii names if normal name is non-ascii')
options.define('alt_names', default=False, help='include alternate names')
options.define('pop_filter', default=100000, help='minimum city population filter')
options.define('us_city_boost', default=2, help='boost for population of US cities to favor them when filtering')
options.define('create_recursive_data_files', default=False, help='create recursive subdirectories '
               'of city name / lat / long files, ordered lexicographically and by population')
options.define('filter_top_cities', default=True, help='create a file of the top world cities by population; '
               'output file is written to "output_dir/top_cities.txt"')

GeoDatum = namedtuple('GeoDatum', ['id', 'name', 'lat', 'lon', 'cc', 'state', 'county', 'pop'])


class GeoProcessor(object):
  """Main class for geoname processing. Handles initial parse of data
  file and spawns recursive datafile creation.
  """
  def __init__(self):
    self._data = None
    self._size = options.options.datafile_size
    self._ParseUSPostal(options.options.uspostalfile)
    self._ParseCities(options.options.cityfile)
    if not os.path.exists(options.options.output_dir):
      os.makedirs(options.options.output_dir)
    else:
      for f in os.listdir(options.options.output_dir):
        os.unlink(os.path.join(options.options.output_dir, f))

  def GetCities(self):
    """Returns the list of cities."""
    return self._data

  def NumCities(self):
    """Returns the number of places being processed."""
    return len(self._data)

  def RecursivelyCreateDataFiles(self, start='', end='', cities=None):
    """Filters out a set of places which match the place name entries
    which lie between (start, end), inclusive. If there are more than
    --datafile_size places with the prefix, the places are sorted by
    population. The largest --datafile_size places are bundled into a
    sorted datafile.

    In addition, the same prefix range is recursively subdivided into
    a set of sub-ranges, each of approximately --datafile_size places.

    The prefix range is returned.
    """
    if not cities:
      cities = self._data

    if len(cities) > options.options.datafile_size:
      # Include the --datafile_size most populous cities.
      pop_sorted = sorted(cities, key=attrgetter('pop'), reverse=True)
      output = pop_sorted[:options.options.datafile_size]
      leftover = []
      # Include any cities which are exactly this many characters.
      for city in cities:
        if len(city.name) == len(start):
          output.append(city)
        elif len(city.name) > len(start):
          leftover.append(city)
        else:
          assert False

      # Try to create a new data file for each --datafile_size cities,
      # breaking along distinct prefixes.
      cities = []
      first_prefix = leftover[0].name[:len(start) + 1]
      last_prefix = first_prefix
      for city in leftover:
        next_prefix = city.name[:len(start) + 1]
        if last_prefix != next_prefix and len(cities) >= options.options.datafile_size:
          self.RecursivelyCreateDataFile(first_prefix, next_prefix, cities)
          first_prefix = next_prefix
          cities = []
        else:
          cities.append(city)
        last_prefix = next_prefix
      if cities:
        self.RecursivelyCreateDataFile(first_prefix, next_prefix, cities)
    else:
      output = cities

    with open(os.path.join(options.options.output_dir, '%s-%s' % (start or '_', end or '_')), 'w') as f:
      json.dump(output, f)

  def FilterTopCities(self):
    """Applies the boost to US cities, sorts by population and outputs the
    list of files to output directory.
    """
    filtered_cities = []
    for city in self._data:
      filtered_cities.append(city)
    cities_sorted = sorted(filtered_cities, key=attrgetter('name'), cmp=locale.strcoll)
    with codecs.open(os.path.join(options.options.output_dir, 'top_cities.txt'), 'w', 'utf-8') as f:
      for c in cities_sorted:
        f.write('%s,%s,%s,%f,%f\n' % (c.name, c.state or '', c.cc, c.lat, c.lon))

  def _CleanName(self, name):
    """Strips illegal characters from place name and returns new name."""
    return name.strip(string.whitespace + string.punctuation)

  def _ParseUSPostal(self, datafile):
    """Loads and parses the provided datafile into an array of placename
    information.
    """
    self._us_postal = []
    with open(datafile, 'r') as f:
      for line in f.readlines():
        fields = line.split('\t')
        datum = GeoDatum(None, self._CleanName(fields[2].decode('utf-8')),
                         float(fields[9]), float(fields[10]), fields[0], fields[4], fields[5], None)
        self._us_postal.append(datum)
    self._us_postal = sorted(self._us_postal, key=attrgetter('name'), cmp=locale.strcoll)
    logging.info('parsed %d places from US postal database' % len(self._us_postal))

  def _ParseCities(self, datafile):
    """Loads and parses the provided datafile into an array of placename
    information.
    """
    count_under = 0
    count_over = 0
    us_postal_places = [d.name for d in self._us_postal]
    self._data = []
    with open(datafile, 'r') as f:
      for line in f.readlines():
        fields = line.split('\t')
        population = int(fields[14])
        if fields[8] == 'US':
          population *= options.options.us_city_boost
        if population < options.options.pop_filter:
          continue
        geo_id = fields[0]
        place = self._CleanName(fields[1].decode('utf-8'))
        cc = fields[8]
        lat = float(fields[4])
        lon = float(fields[5])
        pop = int(fields[14])

        # Attempt to find the place in the us postal database if cc='US'.
        state, county = (None, None)
        if cc == 'US':
          left_index = bisect_left(us_postal_places, place)
          right_index = bisect_right(us_postal_places, place)
          if left_index != len(self._us_postal) and right_index != len(self._us_postal):
            best_distance = None
            for i in range(left_index, right_index):
              best_index = -1
              distance = s2.DistanceBetweenLocations(lat, lon, self._us_postal[i].lat, self._us_postal[i].lon)
              if best_distance == None or distance < best_distance:
                state, county = (self._us_postal[i].state, self._us_postal[i].county)
                best_distance = distance
                best_index = i
              if distance > 1000:
                count_over += 1
              else:
                count_under += 1

        datum = GeoDatum(geo_id, place, lat, lon, cc, state, county, pop)
        self._data.append(datum)
        # Look for ascii name different from utf-8 name.
        if options.options.ascii_names and fields[1] != fields[2]:
          self._data.append(datum._replace(name=self._CleanName(fields[2].decode('utf-8'))))
        # Process alternate names if enabled.
        if options.options.alt_names:
          for alt_name in [self._CleanName(x.decode('utf-8')) for x in fields[3].split(',') if x]:
            self._data.append(datum._replace(name=alt_name))

    logging.info('%d US cities matched within 1km, %d didn\'t' % (count_under, count_over))
    self._data = sorted(self._data, key=attrgetter('name'), cmp=locale.strcoll)
    logging.info('parsed and sorted %d places from world cities database' % len(self._data))


def main():
  locale.setlocale(locale.LC_ALL, "")
  options.parse_command_line()
  geoproc = GeoProcessor()
  if options.options.create_recursive_data_files:
    geoproc.RecursivelyCreateDataFile()
  if options.options.filter_top_cities:
    geoproc.FilterTopCities()


if __name__ == '__main__':
  sys.exit(main())
