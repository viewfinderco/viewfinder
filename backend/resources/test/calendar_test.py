# Copyright 2012 Viewfinder Inc. All Rights Reserved.
# -*- coding: utf-8 -*-

"""Test for Calendar objects.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import datetime
import time
import unittest

from viewfinder.backend.resources.calendar import Calendar

class CalendarTestCase(unittest.TestCase):
  def testSimple(self):
    """Reads US holidays calendar and gets events from current year."""
    cal = Calendar.GetCalendar()
    year = time.gmtime().tm_year
    events = cal.GetEvents(year=year)
    for holiday in ('Halloween', 'Independence Day', 'Labor Day', 'Memorial Day',
                    'New Year\'s Day', 'Christmas Day', 'Thanksgiving Day'):
      self.assertEqual(len([ev for ev in events if ev['name'] == holiday]), 1)

  def testDefault(self):
    """Verify US holidays are default."""
    default_cal = Calendar.GetCalendar()
    us_holidays = Calendar.GetCalendar('USHolidays.ics')
    self.assertEqual(default_cal, us_holidays)

  def testCaching(self):
    """Verifies calendar objects are cached on successive calls."""
    cal1 = Calendar.GetCalendar()
    cal2 = Calendar.GetCalendar()
    self.assertEqual(cal1, cal2)

  def testByLocale(self):
    """Verifies holiday calendars can be fetched directly by locale."""
    def _VerifyHoliday(cal, name, start_month, start_day, end_month, end_day):
      """Verifies that a holiday with the specified name and date exists."""
      year = datetime.date.today().year
      dtstart = time.mktime(datetime.datetime(year, start_month, start_day).timetuple())
      dtend = time.mktime(datetime.datetime(year, end_month, end_day).timetuple())
      events = cal.GetEvents(year)
      holidays = [ev for ev in events if ev['name'] == name and ev['dtstart'] == dtstart \
                    and ev['dtend'] == dtend]
      self.assertEqual(len(holidays), 1)

    us_cal = Calendar.GetHolidaysByLocale('en_US')
    ru_cal = Calendar.GetHolidaysByLocale('ru_RU')
    _VerifyHoliday(us_cal, 'Christmas Day', 12, 25, 12, 26)
    _VerifyHoliday(us_cal, 'New Year\'s Day', 1, 1, 1, 2)
    _VerifyHoliday(ru_cal, u'Новогодние каникулы', 1, 2, 1, 6)
    _VerifyHoliday(ru_cal, u'Новый год', 1, 1, 1, 2)


