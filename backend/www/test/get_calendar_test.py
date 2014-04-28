# Copyright 2012 Viewfinder Inc. All Rights Reserved.
# -*- coding: utf-8 -*-

"""Tests querying calendars by year.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import datetime
import json
import time

from functools import partial
from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.user import User
from viewfinder.backend.www import json_schema
from viewfinder.backend.www.test import service_base_test


class GetCalendarTestCase(service_base_test.ServiceBaseTestCase):
  def testGetCalendar(self):
    """Fetch events from a named calendar by year."""
    response_dict = self._SendRequest('get_calendar', self._cookie,
                                      {'calendars': [{'calendar_id': 'EnglishHolidays.ics',
                                                      'year': 2009},
                                                     {'calendar_id': 'FrenchHolidays.ics',
                                                      'year': 2008}]})
    cals = response_dict['calendars']
    self.assertEqual(len(cals), 2)
    self.assertTrue(any([ev['name'] == u'Boxing Day (Substitute)' for ev in cals[0]['events']]))
    self.assertTrue(any([ev['name'] == u'Fête du Travail' for ev in cals[1]['events']]))

  def testGetHolidaysByLocale_en_US(self):
    """Fetch holidays for en_US locale."""
    self._UpdateOrAllocateDBObject(User, user_id=self._user.user_id, locale='en_US')

    response_dict = self._SendRequest('get_calendar', self._cookie,
                                      {'calendars': [{'calendar_id': 'holidays', 'year': 2012}]})
    cals = response_dict['calendars']
    self.assertEqual(len(cals), 1)
    for ev_name in [u"President's Day", u'Memorial Day', u'Labor Day', u'Halloween',
                    u'Thanksgiving Day', u'Christmas Day', u"New Year's Day", u"New Year's Eve",
                    u'Independence Day', u"St. Patrick's Day", u"Valentine's Day",
                    u"Martin Luther King Jr.'s Day", u'Christmas Eve']:
      self.assertTrue(any([ev['name'] == ev_name for ev in cals[0]['events']]))

  def testGetAllHolidays_en_US(self):
    """Fetch all holidays for en_US locale for last decade."""
    self._UpdateOrAllocateDBObject(User, user_id=self._user.user_id, locale='en_US')

    response_dict = self._SendRequest('get_calendar', self._cookie,
                                      {'calendars': [{'calendar_id': 'holidays', 'year': year}
                                                     for year in range(2002, 2013)]})
    cals = response_dict['calendars']
    self.assertEqual(len(cals), 11)
    #for cal in cals:
    #  for ev in cal['events']:
    #    print '{"%s", %d},' % (ev['name'], int(ev['dtstart']))

  def testGetHolidaysByLocale_zh_CN(self):
    """Fetch holidays for year 2012 with Chinese/China locale."""
    self._UpdateOrAllocateDBObject(User, user_id=self._user.user_id, locale='zh_CN')

    response_dict = self._SendRequest('get_calendar', self._cookie,
                                      {'calendars': [{'calendar_id': 'holidays', 'year': 2012}]})

    cals = response_dict['calendars']
    self.assertEqual(len(cals), 1)
    chinese_ny = [ev for ev in cals[0]['events'] if ev['name'] == u'正月初一 壬辰（龙）年春节'][0]
    self.assertEqual(datetime.datetime.fromtimestamp(chinese_ny['dtstart']),
                     datetime.datetime(2012, 1, 23))
    self.assertEqual(datetime.datetime.fromtimestamp(chinese_ny['dtend']),
                     datetime.datetime(2012, 1, 24))
