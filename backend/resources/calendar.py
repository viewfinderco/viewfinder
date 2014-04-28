# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Calendar datamodel.

Calendars provide color to a chronology such as the Viewfinder search/
browse tool.

Calendars are parsed from the "resources/calendars/" subdirectory on
demand and cached.

TODO(spencer): this is a very rough beginning meant to capture
locale-specific holidays. We use here the holiday calendars provided
by Mozilla. The idea in general is to provide an interface to
arbitrary calendars, such as the wealth of calendars available via
Google's calendar app.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import datetime
import dateutil
import logging
import os
import time
import vobject

from functools import partial
from viewfinder.backend.base import util

class Calendar(object):
  """Interface to loading ICS iCalendar calendar data."""
  _RESOURCES_CALENDARS_FMT = '../../resources/calendars/%s'
  _DEFAULT_CALENDAR_ID = 'USHolidays.ics'

  """Mapping from locale to holidays calendar."""
  _locale_to_holiday_calendar_map = {
    'ar_DZ': 'AlgeriaHolidays.ics',
    'es_AR': 'ArgentinaHolidays.ics',
    'en_AU': 'AustraliaHolidays.ics',
    'de_AT': 'AustrianHolidays.ics',
    'eu_ES': 'BasqueHolidays.ics',
    'nl_BE': 'BelgianDutchHolidays.ics',
    'fr_BE': 'BelgianFrenchHolidays.ics',
    'de_BE': 'BelgianHolidays.ics',
    'es_BO': 'BoliviaHolidays.ics',
    'pt_BR': 'BrazilHolidays.ics',
    'bg_BG': 'BulgarianHolidays.ics',
    'en_CA': 'CanadaHolidays.ics',
    'es_CL': 'ChileHolidays.ics',
    'zh_CN': 'ChinaHolidays.ics',
    'es_CO': 'ColombianHolidays.ics',
    'hr_HR': 'CroatiaHolidays.ics',
    'cs_CZ': 'CzechHolidays.ics',
    'da_DK': 'DanishHolidays.ics',
    'be_NL': 'DutchHolidays.ics',
    'nl_NL': 'DutchHolidays.ics',
    'en_GB': 'EnglishHolidays.ics',
    'et_EE': 'EstoniaHolidays.ics',
    'fi_FI': 'FinlandHolidays.ics',
    'sv_FI': 'FinlandHolidays.ics',
    'fr_FR': 'FrenchHolidays.ics',
    'fy_NL': 'FrisianHolidays.ics',
    'de_DE': 'GermanHolidays.ics',
    'en_HK': 'HongKongHolidays.ics',
    'zh_HK': 'HongKongHolidays.ics',
    'hu_HU': 'HungarianHolidays.ics',
    'is_IS': 'IcelandHolidays.ics',
    'id_ID': 'IndonesianHolidays.ics',
    'it_IT': 'ItalianHolidays.ics',
    'ja_JP': 'JapanHolidays.ics',
    'sw_KE': 'KenyaHolidays.ics',
    'so_KE': 'KenyaHolidays.ics',
    'om_KE': 'KenyaHolidays.ics',
    'kam_KE': 'KenyaHolidays.ics',
    'lv_LV': 'LatviaHolidays.ics',
    'lt_LT': 'LithuanianHolidays.ics',
    'de_LU': 'LuxembourgHolidays.ics',
    'fr_LU': 'LuxembourgHolidays.ics',
    'en_NZ': 'NewZealandHolidays.ics',
    'mi_NZ': 'NewZealandHolidays.ics',
    'nb_NO': 'NorwegianHolidays.ics',
    'en_PK': 'PakistanHolidays.ics',
    'pa_Arab_PK': 'PakistanHolidays.ics',
    'pa_PK': 'PakistanHolidays.ics',
    'ur_PK': 'PakistanHolidays.ics',
    'es_PE': 'PeruHolidays.ics',
    'pl_PL': 'PolishHolidays.ics',
    'pt_PT': 'PortugalHolidays.ics',
    'en_QLD': 'QueenslandHolidays.ics',
    'en_AU_QLD': 'QueenslandHolidays.ics',
    'ro_MD': 'RomaniaHolidays.ics',
    'ro_RO': 'RomaniaHolidays.ics',
    'ru_RU': 'RussiaHolidays.ics',
    'ru_UA': 'RussiaHolidays.ics',
    'uk_UA': 'RussiaHolidays.ics',
    'en_SG': 'SingaporeHolidays.ics',
    'zh_Hans_SG': 'SingaporeHolidays.ics',
    'zh_SG': 'SingaporeHolidays.ics',
    'sk_SK': 'SlovakHolidays.ics',
    'af_ZA': 'SouthAfricaHolidays.ics',
    'en_ZA': 'SouthAfricaHolidays.ics',
    'nr_ZA': 'SouthAfricaHolidays.ics',
    'nso_ZA': 'SouthAfricaHolidays.ics',
    'ss_ZA': 'SouthAfricaHolidays.ics',
    'st_ZA': 'SouthAfricaHolidays.ics',
    'tn_ZA': 'SouthAfricaHolidays.ics',
    'ts_ZA': 'SouthAfricaHolidays.ics',
    've_ZA': 'SouthAfricaHolidays.ics',
    'xh_ZA': 'SouthAfricaHolidays.ics',
    'zu_ZA': 'SouthAfricaHolidays.ics',
    'ko_KR': 'SouthKoreaHolidays.ics',
    'es_ES': 'SpanishHolidays.ics',
    'si_LK': 'SriLankaHolidays.ics',
    'sv_SE': 'SwedishHolidays.ics',
    'de_CH': 'SwissHolidays.ics',
    'fr_CH': 'SwissHolidays.ics',
    'gsw_CH': 'SwissHolidays.ics',
    'it_CH': 'SwissHolidays.ics',
    'trv_TW': 'TaiwanHolidays.ics',
    'zh_Hant_TW': 'TaiwanHolidays.ics',
    'zh_TW': 'TaiwanHolidays.ics',
    'th_TH': 'ThaiHolidays.ics',
    'ku_Latn_TR': 'TurkeyHolidays.ics',
    'ku_TR': 'TurkeyHolidays.ics',
    'tr_TR': 'TurkeyHolidays.ics',
    'cy_GB': 'UKHolidays.ics',
    'en_GB': 'UKHolidays.ics',
    'gv_GB': 'UKHolidays.ics',
    'kw_GB': 'UKHolidays.ics',
    'en': 'USHolidays.ics',
    'en_US': 'USHolidays.ics',
    'es_US': 'USHolidays.ics',
    'haw_US': 'USHolidays.ics',
    'es_UY': 'UruguayHolidays.ics',
    'vi_VN': 'VietnamHolidays.ics',
    }

  """Cache for Calendar objects."""
  _cache = dict()

  def __init__(self, calendar_id):
    """Prepares a calendar for the specified 'calendar_id'.
    """
    self.calendar_id = calendar_id
    cal_path = os.path.dirname(__file__)
    path = os.path.join(cal_path, Calendar._RESOURCES_CALENDARS_FMT % self.calendar_id)
    with open(path, 'rb') as f:
      self._cal = vobject.readOne(f)

  def GetEvents(self, year):
    """Returns the events from the calendar for the year specified.
    In cases where the calendar does not span the requested year,
    throws a 'NoCalendarDataError' exception.
    """
    events = []
    for event in self._cal.components():
      if event.name == 'VEVENT':
        name = event.summary.value
        if event.getrruleset():
          rruleset = event.getrruleset()
          dates = rruleset.between(datetime.datetime(year - 1, 12, 31),
                                   datetime.datetime(year + 1, 1, 1))
          if len(dates) >= 1:
            if len(dates) > 1:
              logging.warning('holiday %s occurs more than once a year: %r' % (name, dates))
            delta = event.dtend.value - event.dtstart.value
            dtstart = dates[0]
            dtend = dtstart + delta
            events.append({'name': name,
                           'dtstart': time.mktime(dtstart.timetuple()),
                           'dtend': time.mktime(dtend.timetuple())})
        else:
          dtstart = event.dtstart.value
          dtend = event.dtend.value
          if dtstart.year == year:
            events.append({'name': name,
                           'dtstart': time.mktime(dtstart.timetuple()),
                           'dtend': time.mktime(dtend.timetuple())})
    return events

  @classmethod
  def GetCalendar(cls, calendar_id=None):
    """Attempts to locate a cached version of 'calendar_id'. If none is
    found, attempts to load from disk.
    """
    calendar_id = calendar_id or Calendar._DEFAULT_CALENDAR_ID
    if not Calendar._cache.has_key(calendar_id):
      cal = Calendar(calendar_id)
      Calendar._cache[calendar_id] = cal
    return Calendar._cache[calendar_id]

  @classmethod
  def GetHolidaysByLocale(cls, locale='en_US'):
    """Attempts to match the specified locale with a holidays
    calendar. Normalizes the locale by replacing '-' with '_'.
    """
    locale = locale.replace('-', '_')
    calendar_id = Calendar._locale_to_holiday_calendar_map.get(locale, None) or \
        Calendar._DEFAULT_CALENDAR_ID
    return Calendar.GetCalendar(calendar_id)
