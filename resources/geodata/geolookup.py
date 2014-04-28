# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Parses the cities1000.txt geonames database and uses google maps
API to lookup locality, administrative_area_level_1 and country using
the latitude and longitude listed with each city.

Datafile sourced from: http://download.geonames.org/.

The contents of each lookup are written to a JSON-encoded file which
is re-read on each invocation. Only cities in cities1000.txt which are
not already accounted-for in the JSON-encoded file are looked up to
avoid duplicative queries.

Usage:

% python resources/geonames/geolookup.py --cityfile=cities1000.txt --lookupdb=lookup.json

"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import json
import logging
import os
import sys
import time

from functools import partial
from operator import attrgetter
from tornado import httpclient, ioloop, options
from viewfinder.backend.base import util
from viewfinder.resources.geodata.geoprocessor import GeoProcessor

options.define('lookupdb', default='lookup.json', help='JSON output file containing lookup data')
options.define('query_rate', default=10, help='allowed queries per second to google maps')


class GeoLookup(object):
  """Main class for geolookup. Handles initial parse of JSON data
  file and spawns async HTTP queries to google maps API.
  """
  def __init__(self, io_loop, geoproc):
    self._io_loop = io_loop
    self._geoproc = geoproc
    self._http_client = httpclient.AsyncHTTPClient()
    try:
      with open(options.options.lookupdb, 'r') as rf:
        self._lookup_db = json.load(rf)
    except:
      self._lookup_db = {}

  def RefreshDB(self, callback):
    """Refreshes the lookup database by iterating over all cities in
    the geoprocessor and querying google maps for address components
    for any that are missing.
    """
    def _OnLookup(city, barrier_cb, response):
      if response.code != 200:
        logging.error('error in google maps API query: %s' % response)
      else:
        try:
          json_response = json.loads(response.body)
          components = []
          if len(json_response['results']) > 0:
            for comp in json_response['results'][0]['address_components']:
              for t in comp['types']:
                if t in ('locality', 'administrative_area_level_1', 'country'):
                  components.append(comp)
                  break
          self._lookup_db[city.id] = components
        except:
          logging.exception('unable to parse google maps API response: %s' % response.body)
      barrier_cb()

    with util.Barrier(callback) as b:
      def _ProcessCities(cities):
        start_time = time.time()
        lookup_count = 0
        for index in xrange(len(cities)):
          city = cities[index]
          if city.id not in self._lookup_db:
            lat, lon = float(city.lat), float(city.lon)
            logging.info('looking up %s (%f, %f) via google maps API' % (city.name, lat, lon))
            if lookup_count / (1.0 + time.time() - start_time) > options.options.query_rate:
              logging.info('pausing to slow API query rate')
              return self._io_loop.add_timeout(time.time() + 1.0, partial(_ProcessCities, cities[index:]))
            lookup_count += 1
            self._http_client.fetch('http://maps.googleapis.com/maps/api/geocode/json?latlng=%f,%f&sensor=false' %
                                    (lat, lon), callback=partial(_OnLookup, city, b.Callback()), method='GET')

      cities = self._geoproc.GetCities()
      _ProcessCities(cities)

  def SaveDB(self):
    """Saves the database to disk by writing to a temporary file and
    then renames.
    """
    tmp_file = options.options.lookupdb + '.bak'
    try:
      with open(tmp_file, 'w') as wf:
        json.dump(self._lookup_db, wf)
      os.rename(tmp_file, options.options.lookupdb)
    except:
      logging.exception('unable to write lookup database')
      os.unlink(tmp_file)


def main():
  io_loop = ioloop.IOLoop.instance()
  options.parse_command_line()

  geoproc = GeoProcessor()
  geolookup = GeoLookup(io_loop, geoproc)

  def _OnRefresh():
    geolookup.SaveDB()
    io_loop.stop()

  geolookup.RefreshDB(_OnRefresh)

  io_loop.start()
  return 0


if __name__ == '__main__':
  sys.exit(main())
