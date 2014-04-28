# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Customization for display of database tables.

  Default: default display of a table row
  *: customized versions by table
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import pprint
import time

from tornado.escape import url_escape, xhtml_escape
from viewfinder.backend.base.util import ConvertToString
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.schema import UnpackLocation, UnpackPlacemark
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.viewpoint import Viewpoint

class FmtDefault(object):
  def __init__(self, table):
    self._table = table

  def FormatItemAttributes(self, item):
    """Returns an array of item attributes, one per column in the
    table definition, formatted for display in HTML table.
    """
    attributes = self._FormatAllAttributes(item)
    rows = [pretty for _, _, _, pretty in attributes]
    return rows

  def FormatItemAttributesForView(self, item):
    """Return an array of rows. Each row consists of "column name",
    "key", "value".
    """
    attributes = self._FormatAllAttributes(item)
    rows = [(name, key, pretty) for name, key, _, pretty in attributes]
    rows.extend(self._GetExtraViewFields(item))
    return rows

  def _GetExtraViewFields(self, item):
    """Class used to append new fields in per-object view. Nothing by default.
    Must be a list of (name, key, pretty)."""
    return []

  @staticmethod
  def _Escape(val):
    # Need to cast to string for int-valued columns (eg: user_id).
    return url_escape(ConvertToString(val))

  @staticmethod
  def _XEscape(val):
    # Need to cast to string for int-valued columns (eg: user_id).
    return xhtml_escape(ConvertToString(val))

  @staticmethod
  def _HashQueryLink(table, key, name=None):
    return '<a href="/admin/db?table=%s&type=query&hash_key=%s">%s</a>' % \
           (FmtDefault._Escape(table), FmtDefault._Escape(key), FmtDefault._XEscape(name if name is not None else key))

  @staticmethod
  def _SortQueryLink(table, hash_key, sort_key, name=None):
    """Builds a query link for a hash_key and sort_key. Sort key operator is 'EQ'."""
    return '<a href="/admin/db?table=%s&type=query&hash_key=%s&sort_key=%s&sort_desc=EQ">%s</a>' % \
           (FmtDefault._Escape(table), FmtDefault._Escape(hash_key), FmtDefault._Escape(sort_key),
           FmtDefault._XEscape(name if name is not None else '%s:%s' % (hash_key, sort_key)))

  @staticmethod
  def _EpisodeLink(vp, name=None):
    return FmtDefault._HashQueryLink('Episode', vp, name)

  @staticmethod
  def _PhotoLink(vp, name=None):
    return FmtDefault._HashQueryLink('Photo', vp, name)

  @staticmethod
  def _UserLink(vp, name=None):
    return FmtDefault._HashQueryLink('User', vp, name)

  @staticmethod
  def _ViewpointLink(vp, name=None):
    return FmtDefault._HashQueryLink('Viewpoint', vp, name)

  def _FormatAllAttributes(self, item):
    """Build list of (column, key, value, pretty_value). We need a list to keep the columns ordered."""
    attrs = []
    for name in self._table.GetColumnNames():
      c = self._table.GetColumn(name)
      value = item.get(c.key, None)
      pretty = self._FormatAttribute(name, value) if value is not None else '-'
      attrs.append((name, c.key, value, pretty))
    return attrs

  def _FormatAttribute(self, name, value):
    """Returns the attribute value; If none, returns '-'. Formats by
    default the following fields: 'viewpoint_id', 'episode_id',
    'photo_id', 'timestamp', 'Location', 'Placemark'.
    """
    if name == 'viewpoint_id' or name == 'private_vp_id':
      did, (vid, sid) = Viewpoint.DeconstructViewpointId(value)
      pretty = '%s/%d/%d' % (value, did, vid)
      return FmtDefault._ViewpointLink(value, pretty)
    elif name == 'user_id' or name == 'sender_id':
      return self._UserLink(value)
    elif name == 'episode_id' or name == 'parent_ep_id':
      ts, did, (eid, sid) = Episode.DeconstructEpisodeId(value)
      pretty = '%s/%d/%d' % (value, did, eid)
      return self._EpisodeLink(value, pretty)
    elif name == 'photo_id' or name == 'parent_id':
      ts, did, (pid, sid) = Photo.DeconstructPhotoId(value)
      pretty = '%s/%d/%d' % (value, did, pid)
      return self._PhotoLink(value, pretty)
    elif name == 'timestamp' or name == 'last_updated' or name == 'expires' or name == 'last_fetch':
      return self._FormatTimestamp(value)
    elif name == 'location':
      return self._XEscape(', '.join(['%s: %s' % (k, v) for k, v in UnpackLocation(value)._asdict().items()]))
    elif name == 'placemark':
      return self._XEscape(', '.join(['%s: %s' % (k, v) for k, v in UnpackPlacemark(value)._asdict().items()]))
    else:
      return self._XEscape('%s' % value)

  def _FormatTimestamp(self, timestamp):
    """Formats a timestamp (in UTC) via default format."""
    return self._XEscape(time.asctime(time.gmtime(timestamp)))

  def _GetQueryURL(self, table, hash_key):
    """Returns a URL to display a DB query of the table using
    hash key 'hash_key'.
    """
    return '/admin/db?table=%s&type=query&hash_key=%s' % (self._Escape(table), self._Escape(repr(hash_key)))


class FmtAccounting(FmtDefault):
  _names = { 'vs': 'viewpoint_size', 'us': 'user_size',
             'ow': 'owned_by', 'sb': 'shared_by', 'vt': 'visible_to' }

  def _FormatAttribute(self, name, value):
    if name == 'hash_key':
      split = value.split(':')
      prefix = split[0]
      prefix_name = self._names[prefix]
      if prefix == 'vs':
        return '%s:%s' % (self._XEscape(prefix_name), self._ViewpointLink(split[1]))
      elif prefix == 'us':
        return '%s:%s' % (self._XEscape(prefix_name), self._UserLink(split[1]))
    elif name == 'sort_key':
      split = value.split(':')
      prefix = split[0]
      prefix_name = self._names[prefix]
      if len(split) == 1:
        return prefix_name
      elif prefix == 'ow' or prefix == 'sb':
        return '%s:%s' % (self._XEscape(prefix_name), self._UserLink(split[1]))

    return FmtDefault._FormatAttribute(self, name, value)

class FmtEpisode(FmtDefault):
  def _GetExtraViewFields(self, item):
    ep_id = item.get('ei')
    extras = []
    extras.append(self._HashQueryLink('Index', 'ev:pa:%s' % ep_id, 'Children'))
    extras.append(self._HashQueryLink('Post', ep_id, 'Posts'))
    return [('Extras', '', ' &middot '.join(extras))]

class FmtIdentity(FmtDefault):
  def _GetExtraViewFields(self, item):
    id_id = item.get('ke')
    extras = []
    extras.append(self._HashQueryLink('Index', 'co:id:%s' % id_id, 'In-contacts'))
    return [('Extras', '', ' &middot '.join(extras))]


class FmtIndex(FmtDefault):
  def _FormatAllAttributes(self, item):
    """Build list of (column, key, value, pretty_value). We need a list to keep the columns ordered.
    The interpretation of the 'key' column depends on the beginning of the 'term' column."""
    attrs = []
    term = item.get('t', None)
    key = item.get('k', None)
    data = item.get('d', None)
    split = term.split(':')
    table = split[0]
    key_pretty = key
    if table == 'co':
      db_key = Contact._ParseIndexKey(key)
      key_pretty = self._SortQueryLink('Contact', db_key.hash_key, db_key.range_key)
    elif table == 'ev':
      key_pretty = self._EpisodeLink(key)
    elif table == 'fo':
      db_key = Follower._ParseIndexKey(key)
      key_pretty = self._SortQueryLink('Follower', db_key.hash_key, db_key.range_key)
    elif table == 'id':
      key_pretty = self._HashQueryLink('Identity', key)
    elif table == 'vp':
      key_pretty = self._ViewpointLink(key)

    attrs.append(('term', 't', term, term))
    attrs.append(('key', 'k', key, key_pretty))
    attrs.append(('data', 't', data, data))
    attrs.append(('_version', '_ve', data, data))
    return attrs

class FmtLock(FmtDefault):
  def _FormatAttribute(self, name, value):
    """Formats 'expiration' as human readable date/times.
    """
    if name == 'expiration':
      if value < time.time():
        return '<i>Expired</i>'
      else:
        return self._FormatTimestamp(value)
    else:
      return FmtDefault._FormatAttribute(self, name, value)


class FmtOperation(FmtDefault):
  def _FormatAttribute(self, name, value):
    """Formats 'timestamp' as human readable date/time, {'json',
    'first_exception', 'last_exception'} as <pre/> blocks for readability.
    """
    if name in ('json', 'first_exception', 'last_exception'):
      return '<pre>%s</pre>' % self._XEscape(value)
    elif name == 'backoff':
      if value < time.time():
        return '<i>Expired</i>'
      else:
        return self._FormatTimestamp(value)
    else:
      return FmtDefault._FormatAttribute(self, name, value)

class FmtUser(FmtDefault):
  def _GetExtraViewFields(self, item):
    user_id = item.get('ui')
    extras = []
    extras.append(self._HashQueryLink('Accounting', 'us:%s' % user_id, 'Accounting'))
    extras.append(self._HashQueryLink('Contact', user_id, 'Contacts'))
    extras.append(self._HashQueryLink('Device', user_id, 'Devices'))
    extras.append(self._HashQueryLink('Index', 'ev:ui:%s' % user_id, 'Episodes'))
    extras.append(self._HashQueryLink('Followed', user_id, 'Followed'))
    extras.append(self._HashQueryLink('Follower', user_id, 'Follower'))
    extras.append(self._HashQueryLink('Friend', user_id, 'Friends'))
    extras.append(self._HashQueryLink('Index', 'id:ui:%s' % user_id, 'Identities'))
    extras.append(self._HashQueryLink('Notification', user_id, 'Notifications'))
    extras.append(self._HashQueryLink('Settings', 'us:%s' % user_id, 'Settings'))
    extras.append(self._HashQueryLink('Subscription', user_id, 'Subscriptions'))
    extras.append(self._HashQueryLink('Index', 'vp:ui:%s' % user_id, 'Viewpoints'))
    return [('Extras', '', ' &middot '.join(extras))]

class FmtViewpoint(FmtDefault):
  def _GetExtraViewFields(self, item):
    vp_id = item.get('vi')
    extras = []
    extras.append(self._HashQueryLink('Accounting', 'vs:%s' % vp_id, 'Accounting'))
    extras.append(self._HashQueryLink('Activity', vp_id, 'Activities'))
    extras.append(self._HashQueryLink('Comment', vp_id, 'Comments'))
    extras.append(self._HashQueryLink('Index', 'ev:vi:%s' % vp_id, 'Episodes'))
    extras.append(self._HashQueryLink('Index', 'fo:vi:%s' % vp_id, 'Followers'))
    return [('Extras', '', ' &middot '.join(extras))]
