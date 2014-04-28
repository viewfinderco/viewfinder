# -*- coding: utf-8 -*-
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Tests DB indexing and querying.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import platform
import random
import time
import unittest

from functools import partial
from tornado import escape
from viewfinder.backend.base import util
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.schema import Location, Placemark
from viewfinder.backend.db.user import User
from viewfinder.backend.db.vf_schema import USER

from base_test import DBBaseTestCase

class IndexingTestCase(DBBaseTestCase):
  @async_test
  def testIndexing(self):
    """Tests indexing of multiple objects with overlapping field values.
    Creates 100 users, then queries for specific items.
    """
    given_names = ['Spencer', 'Peter', 'Brian', 'Chris']
    family_names = ['Kimball', 'Mattis', 'McGinnis', 'Schoenbohm']
    emails = ['spencer.kimball@emailscrubbed.com', 'spencer@goviewfinder.com',
              'petermattis@emailscrubbed.com', 'peter.mattis@gmail.com', 'peter@goviewfinder.com',
              'brian.mcginnis@emailscrubbed.com', 'brian@goviewfinder.com',
              'chris.schoenbohm@emailscrubbed.com', 'chris@goviewfinder.com']

    num_users = 100

    def _QueryAndVerify(users, barrier_cb, col, value):
      def _Verify(q_users):
        logging.debug('querying for %s=%s yielded %d matches' % (col, value, len(q_users)))
        for u in q_users:
          # Exclude users created by base class.
          if u.user_id not in [self._user.user_id, self._user2.user_id]:
            self.assertEqual(getattr(users[u.user_id], col), value)
        barrier_cb()
      User.IndexQuery(self._client, ('user.%s={v}' % col, {'v': value}),
                      col_names=None, callback=_Verify)

    def _OnCreateUsers(user_list):
      users = dict([(u.user_id, u) for u in user_list])
      with util.Barrier(self.stop) as b:
        [_QueryAndVerify(users, b.Callback(), 'given_name', value) for value in given_names]
        [_QueryAndVerify(users, b.Callback(), 'family_name', value) for value in family_names]
        [_QueryAndVerify(users, b.Callback(), 'email', value) for value in emails]

    with util.ArrayBarrier(_OnCreateUsers) as b:
      for i in xrange(num_users):
        kwargs = {'user_id': i + 10,
                  'given_name': random.choice(given_names),
                  'family_name': random.choice(family_names),
                  'email': random.choice(emails), }
        user = User.CreateFromKeywords(**kwargs)
        user.Update(self._client, partial(b.Callback(), user))

  def testIndexQueryForNonExistingItem(self):
    """IndexQuery should not return a result list with any None elements."""
    # Create a user:
    user = User.CreateFromKeywords(user_id=1, given_name='Mike', family_name='Purtell', email='mike@time.com')
    self._RunAsync(user.Update, self._client)

    # Should return one non-None item.
    results = self._RunAsync(User.IndexQuery, self._client, ('user.given_name={v}', {'v': 'Mike'}), col_names=None)
    self.assertEqual(len(results), 1)
    self.assertIsNotNone(results[0])

    # Delete the item that the index references.
    self._RunAsync(self._client.DeleteItem, table=USER, key=user.GetKey())

    # IndexQuery again with same query to see that a zero length list is returned.
    results = self._RunAsync(User.IndexQuery, self._client, ('user.given_name={v}', {'v': 'Mike'}), col_names=None)
    self.assertEqual(len(results), 0)

  def testStringSetIndexing(self):
    """Tests indexing of items in string set columns."""

    emails = ['spencer.kimball@emailscrubbed.com', 'spencer@goviewfinder.com',
              'petermattis@emailscrubbed.com', 'peter.mattis@gmail.com', 'peter@goviewfinder.com',
              'brian.mcginnis@emailscrubbed.com', 'brian@goviewfinder.com',
              'chris.schoenbohm@emailscrubbed.com', 'chris@goviewfinder.com']

    # Create a bunch of contacts with one or two identities.
    timestamp = util.GetCurrentTimestamp()
    for email in emails:
      for email2 in emails:
        contact = Contact.CreateFromKeywords(1,
                                             [('Email:' + email, None), ('Email:' + email2, None)],
                                             timestamp,
                                             Contact.GMAIL)
        self._RunAsync(contact.Update, self._client)

    for email in emails:
      q_contacts = self._RunAsync(Contact.IndexQuery,
                                  self._client,
                                  ('contact.identities={i}', {'i': 'Email:' + email}),
                                  col_names=None)
      logging.debug('querying for %s=%s yielded %d matches' % ('identities', 'Email:' + email, len(q_contacts)))
      for contact in q_contacts:
        self.assertTrue('Email:' + email in contact.identities)
      self.assertEqual(len(q_contacts), len(emails) * 2 - 1)

  @async_test
  def testRealTimeIndexing(self):
    """Tests index updates in real-time."""
    def _QueryAndVerify(p, barrier_cb, query, is_in):
      def _Verify(keys):
        ids = [key.hash_key for key in keys]
        if is_in:
          self.assertTrue(p.photo_id in ids)
        else:
          self.assertFalse(p.photo_id in ids)
        barrier_cb()
      Photo.IndexQueryKeys(self._client, query, callback=_Verify)

    def _OnUpdate(p):
      with util.Barrier(self.stop) as b:
        _QueryAndVerify(p, b.Callback(), ('photo.caption={c}', {'c': 'Class'}), False)
        _QueryAndVerify(p, b.Callback(), ('photo.caption={c}', {'c': 'reunion'}), False)
        _QueryAndVerify(p, b.Callback(), ('photo.caption={c}', {'c': '1992'}), True)
        _QueryAndVerify(p, b.Callback(), ('photo.caption={c}', {'c': 'culumbia'}), True)

    def _Update(p):
      p.caption = 'Columbia High School c.o. 1992'
      p.Update(self._client, callback=partial(_OnUpdate, p))

    photo_id = Photo.ConstructPhotoId(time.time(), 1, 1)
    p = self.UpdateDBObject(Photo, user_id=self._user.user_id,
                            photo_id=photo_id, caption='Class of 1992 reunion')

    with util.Barrier(partial(_Update, p)) as b:
      _QueryAndVerify(p, b.Callback(), ('photo.caption={c}', {'c': 'reunion'}), True)
      _QueryAndVerify(p, b.Callback(), ('photo.caption={c}', {'c': '1992'}), True)

  @async_test
  @unittest.skipIf(platform.python_implementation() == 'PyPy', 'metaphone queries broken on pypy')
  def testMetaphoneQueries(self):
    """Tests metaphone queries."""
    def _QueryAndVerify(p, barrier_cb, query_expr, match):
      def _Verify(keys):
        ids = [key.hash_key for key in keys]
        if match:
          self.assertTrue(p.photo_id in ids)
        else:
          self.assertFalse(ids)
        barrier_cb()
      Photo.IndexQueryKeys(self._client, query_expr, callback=_Verify)

    photo_id = Photo.ConstructPhotoId(time.time(), 1, 1)
    p = self.UpdateDBObject(Photo, user_id=self._user.user_id,
                            photo_id=photo_id, caption='Summer in East Hampton')

    with util.Barrier(self.stop) as b:
      _QueryAndVerify(p, b.Callback(), ('photo.caption={c}', {'c': 'summer'}), True)
      _QueryAndVerify(p, b.Callback(), ('photo.caption={c}', {'c': 'sumer'}), True)
      _QueryAndVerify(p, b.Callback(), ('photo.caption={c}', {'c': 'summa'}), False)
      _QueryAndVerify(p, b.Callback(), ('photo.caption={c}', {'c': 'sum'}), False)
      _QueryAndVerify(p, b.Callback(), ('photo.caption={c}', {'c': 'hamton'}), False)
      _QueryAndVerify(p, b.Callback(), ('photo.caption={c}', {'c': 'hamptons'}), True)
      _QueryAndVerify(p, b.Callback(), ('photo.caption={c}', {'c': 'hammpton'}), True)

  # Disabled because we removed location secondary index from Episode table.
  @async_test
  def disabled_t_estLocationQueries(self):
    """Tests location queries."""
    def _QueryAndVerify(episode_ids, barrier_cb, loc_search, matches):
      def _Verify(keys):
        ids = [key.hash_key for key in keys]
        self.assertEqual(len(ids), len(matches))
        [self.assertTrue(episode_ids[m] in ids) for m in matches]
        barrier_cb()

      Episode.IndexQueryKeys(self._client, 'episode.location="%f,%f,%f"' % \
                             (loc_search[0], loc_search[1], loc_search[2]), callback=_Verify)

    def _OnCreate(locations, episodes):
      with util.Barrier(self.stop) as b:
        episode_ids = dict([(v.title, v.episode_id) for v in episodes])
        # Exact search.
        _QueryAndVerify(episode_ids, b.Callback(),
                        Location(40.727657, -73.994583, 30), ['kimball ph'])
        _QueryAndVerify(episode_ids, b.Callback(),
                        Location(41.044048, -71.950622, 100), ['surf lodge'])
        # A super-small search area, centered in middle of Great Jones Alley.
        _QueryAndVerify(episode_ids, b.Callback(),
                        Location(40.727267, -73.994443, 10), [])
        # Widen the search area to 50m, centered in middle of Great Jones Alley.
        _QueryAndVerify(episode_ids, b.Callback(),
                        Location(40.727267, -73.994443, 50), ['kimball ph', 'bond st sushi'])
        # Union square with a 2km radius.
        _QueryAndVerify(episode_ids, b.Callback(),
                        Location(40.736462, -73.990517, 2000),
                        ['kimball ph', 'bond st sushi', 'viewfinder', 'soho house', 'google'])
        # The Dominican Republic.
        _QueryAndVerify(episode_ids, b.Callback(),
                        Location(19.041349, -70.427856, 75000), ['casa kimball'])
        # The Caribbean.
        _QueryAndVerify(episode_ids, b.Callback(),
                        Location(22.593726, -76.662598, 800000), ['casa kimball', 'atlantis'])
        # Long Island.
        _QueryAndVerify(episode_ids, b.Callback(), Location(40.989228, -72.144470, 40000),
                        ['kimball east', 'surf lodge'])

    locations = {'kimball ph': Location(40.727657, -73.994583, 50.0),
                 'bond st sushi': Location(40.726901, -73.994358, 50.0),
                 'viewfinder': Location(40.720169, -73.998756, 200.0),
                 'soho house': Location(40.740616, -74.005880, 200.0),
                 'google': Location(40.740974, -74.002115, 500.0),
                 'kimball east': Location(41.034184, -72.210603, 50.0),
                 'surf lodge': Location(41.044048, -71.950622, 100.0),
                 'casa kimball': Location(19.636848, -69.896602, 100.0),
                 'atlantis': Location(25.086104, -77.323065, 1000.0)}
    with util.ArrayBarrier(partial(_OnCreate, locations)) as b:
      device_episode_id = 0
      for place, location in locations.items():
        device_episode_id += 1
        timestamp = time.time()
        episode_id = Episode.ConstructEpisodeId(timestamp, 1, device_episode_id)
        episode = Episode.CreateFromKeywords(timestamp=timestamp,
                                             episode_id=episode_id, user_id=self._user.user_id,
                                             viewpoint_id=self._user.private_vp_id,
                                             publish_timestamp=timestamp,
                                             title=place, location=location)
        episode.Update(self._client, b.Callback())

  # Disabled because we removed placemark secondary index from Episode table.
  @async_test
  def disabled_t_estPlacemarkQueries(self):
    """Tests placemark queries."""
    def _QueryAndVerify(episode_ids, barrier_cb, search, matches):
      def _Verify(keys):
        ids = [key.hash_key for key in keys]
        self.assertEqual(len(ids), len(matches))
        [self.assertTrue(episode_ids[m] in ids) for m in matches]
        barrier_cb()

      Episode.IndexQueryKeys(self._client, ('episode.placemark={s}', {'s': search}), callback=_Verify)

    def _OnCreate(locations, episodes):
      with util.Barrier(self.stop) as b:
        episode_ids = dict([(v.title, v.episode_id) for v in episodes])
        _QueryAndVerify(episode_ids, b.Callback(), 'Broadway', ['kimball ph'])
        _QueryAndVerify(episode_ids, b.Callback(), '682 Broadway', ['kimball ph'])
        _QueryAndVerify(episode_ids, b.Callback(), 'Broadway 682', [])
        _QueryAndVerify(episode_ids, b.Callback(), 'new york, ny, united states',
                        ['kimball ph', 'bond st sushi', 'viewfinder', 'soho house', 'google'])
        _QueryAndVerify(episode_ids, b.Callback(), 'new york, ny',
                        ['kimball ph', 'bond st sushi', 'viewfinder', 'soho house', 'google'])
        _QueryAndVerify(episode_ids, b.Callback(), 'NY, United States',
                        ['kimball ph', 'bond st sushi', 'viewfinder', 'soho house', 'google',
                         'kimball east', 'surf lodge'])
        _QueryAndVerify(episode_ids, b.Callback(), 'United States',
                        ['kimball ph', 'bond st sushi', 'viewfinder', 'soho house', 'google',
                         'kimball east', 'surf lodge'])
        _QueryAndVerify(episode_ids, b.Callback(), 'Bahamas', ['atlantis'])
        _QueryAndVerify(episode_ids, b.Callback(), 'Dominican', ['casa kimball'])
        _QueryAndVerify(episode_ids, b.Callback(), 'Dominican Republic', ['casa kimball'])
        _QueryAndVerify(episode_ids, b.Callback(), 'Cabrera', ['casa kimball'])
        _QueryAndVerify(episode_ids, b.Callback(), 'DR', ['casa kimball'])

    locations = {'kimball ph': Placemark('US', 'United States', 'NY', 'New York',
                                         'NoHo', 'Broadway', '682'),
                 'bond st sushi': Placemark('US', 'United States', 'NY', 'New York',
                                            'NoHo', 'Bond St', '6'),
                 'viewfinder': Placemark('US', 'United States', 'NY', 'New York',
                                         'SoHo', 'Grand St', '154'),
                 'soho house': Placemark('US', 'United States', 'NY', 'New York',
                                         'Meatpacking District', '9th Avenue', '29-35'),
                 'google': Placemark('US', 'United States', 'NY', 'New York',
                                     'Chelsea', '8th Avenue', '111'),
                 'kimball east': Placemark('US', 'United States', 'NY', 'East Hampton',
                                           'Northwest Harbor', 'Milina', '35'),
                 'surf lodge': Placemark('US', 'United States', 'NY', 'Montauk',
                                         '', 'Edgemere St', '183'),
                 'casa kimball': Placemark('DR', 'Dominican Republic', 'Maria Trinidad Sanchez',
                                           'Cabrera', 'Orchid Bay Estates', '', '5-6'),
                 'atlantis': Placemark('BS', 'Bahamas', '', 'Paradise Island', '', '', '')}
    with util.ArrayBarrier(partial(_OnCreate, locations)) as b:
      device_episode_id = 0
      for place, placemark in locations.items():
        device_episode_id += 1
        timestamp = time.time()
        episode_id = Episode.ConstructEpisodeId(timestamp, 1, device_episode_id)
        episode = Episode.CreateFromKeywords(timestamp=timestamp,
                                             episode_id=episode_id, user_id=self._user.user_id,
                                             viewpoint_id=self._user.private_vp_id,
                                             publish_timestamp=timestamp,
                                             title=place, placemark=placemark)
        episode.Update(self._client, b.Callback())

  @async_test
  def testQuerying(self):
    """Tests querying of User objects."""
    def _QueryAndVerify(barrier_cb, query_expr, id_set):
      def _Verify(keys):
        ids = [key.hash_key for key in keys]
        if not id_set:
          self.assertFalse(ids)
        else:
          [self.assertTrue(i in id_set) for i in ids]
        barrier_cb()
      User.IndexQueryKeys(self._client, query_expr,
                          callback=_Verify)

    # Add given & family names to users created by base class.
    spencer = self.UpdateDBObject(User, user_id=self._user.user_id, given_name='Spencer', family_name='Kimball')
    andrew = self.UpdateDBObject(User, user_id=self._user2.user_id, given_name='Peter', family_name='Mattis')

    s_id = set([spencer.user_id])
    a_id = set([andrew.user_id])
    both_ids = s_id.union(a_id)
    no_ids = set([])
    with util.Barrier(self.stop) as b:
      _QueryAndVerify(b.Callback(), ('user.given_name={sp}', {'sp': 'spencer'}), s_id)
      _QueryAndVerify(b.Callback(), ('user.given_name={sp}', {'sp': '\'spencer\''}), s_id)
      _QueryAndVerify(b.Callback(), ('user.given_name={sp}', {'sp': '"spencer"'}), s_id)
      _QueryAndVerify(b.Callback(), ('(user.given_name={sp})', {'sp': 'spencer'}), s_id)
      _QueryAndVerify(b.Callback(), ('user.family_name={k}', {'k': 'kimball'}), both_ids)
      _QueryAndVerify(b.Callback(), ('user.given_name={sp} & user.given_name={pe}',
                                     {'sp': 'spencer', 'pe': 'peter'}), no_ids)
      _QueryAndVerify(b.Callback(), ('(user.given_name={sp} & user.given_name={pe})',
                                     {'sp': 'spencer', 'pe': 'peter'}), no_ids)
      _QueryAndVerify(b.Callback(), ('user.given_name={sp} - user.given_name={pe}',
                                     {'sp': 'spencer', 'pe': 'peter'}), s_id)
      _QueryAndVerify(b.Callback(), ('user.given_name={sp} | user.given_name={pe}',
                                     {'sp': 'spencer', 'pe': 'peter'}), both_ids)
      _QueryAndVerify(b.Callback(), ('user.given_name={sp} - user.family_name={k}',
                                     {'sp': 'spencer', 'k': 'kimball'}), no_ids)
      _QueryAndVerify(b.Callback(), ('user.email={sp}', {'sp': 'spencer'}), s_id)
      _QueryAndVerify(b.Callback(), ('user.email={sp} & user.email={gm}', {'sp': 'spencer', 'gm': 'gmail'}), s_id)
      _QueryAndVerify(b.Callback(), ('user.email={sp} & user.email={gm} & user.email=com',
                                     {'sp': 'spencer', 'gm': 'gmail', 'c': 'com'}), s_id)
      _QueryAndVerify(b.Callback(), ('user.email={gm} & user.email=com - user.email=spencer',
                                     {'gm': 'gmail', 'c': 'com', 'sp': 'spencer'}), no_ids)
      _QueryAndVerify(b.Callback(), ('user.email={c}', {'c': 'com'}), both_ids)
      _QueryAndVerify(b.Callback(), ('user.email={em}', {'em': '"spencer.kimball@emailscrubbed.com"'}), s_id)
      _QueryAndVerify(b.Callback(), ('user.given_name={sp} | user.given_name={pe} - user.email={gm}',
                                     {'sp': 'spencer', 'pe': 'peter', 'gm': 'gmail'}), both_ids)
      _QueryAndVerify(b.Callback(), ('(user.given_name={sp} | user.given_name={pe}) - user.email={gm}',
                                     {'sp': 'spencer', 'pe': 'peter', 'gm': 'gmail'}), a_id)

  @async_test
  def testRangeSupport(self):
    """Tests start_key, end_key, and limit support in IndexQueryKeys
    and IndexQuery.
    """
    name = 'Rumpelstiltskin'
    vp_id = 'v0'

    def _QueryAndVerify(cls, barrier_cb, query_expr, start_key, end_key, limit):
      def _FindIndex(list, db_key):
        for i, item in enumerate(list):
          if item.GetKey() == db_key:
            return i
        return -1

      def _Verify(results):
        all_items, some_items, some_item_keys = results

        # Ensure that IndexQuery and IndexQueryKeys return consistent results.
        assert len(some_items) == len(some_item_keys)
        assert [u.GetKey() for u in some_items] == some_item_keys

        # Ensure that right subset was returned.
        start_index = _FindIndex(all_items, start_key) + 1 if start_key is not None else 0
        end_index = _FindIndex(all_items, end_key) if end_key is not None else len(all_items)
        if limit is not None and start_index + limit < end_index:
          end_index = start_index + limit

        assert len(some_items) == end_index - start_index, (len(some_items), start_index, end_index)
        for expected_item, actual_item in zip(all_items[start_index:end_index], some_items):
          expected_dict = expected_item._asdict()
          actual_dict = actual_item._asdict()
          self.assertEqual(expected_dict, actual_dict)

        barrier_cb()

      with util.ArrayBarrier(_Verify) as b:
        cls.IndexQuery(self._client, query_expr, None, b.Callback(), limit=None)
        cls.IndexQuery(self._client, query_expr, None, b.Callback(),
                       start_index_key=start_key, end_index_key=end_key, limit=limit)
        cls.IndexQueryKeys(self._client, query_expr, b.Callback(),
                           start_index_key=start_key, end_index_key=end_key, limit=limit)

    def _RunQueries(cls, query_expr, hash_key_25, hash_key_75, callback):
      with util.Barrier(callback) as b:
        _QueryAndVerify(cls, b.Callback(), query_expr, start_key=None, end_key=None, limit=None)
        _QueryAndVerify(cls, b.Callback(), query_expr, start_key=None, end_key=None, limit=50)
        _QueryAndVerify(cls, b.Callback(), query_expr, start_key=None, end_key=hash_key_75, limit=50)
        _QueryAndVerify(cls, b.Callback(), query_expr, start_key=None, end_key=hash_key_25, limit=50)
        _QueryAndVerify(cls, b.Callback(), query_expr, start_key=hash_key_25, end_key=None, limit=50)
        _QueryAndVerify(cls, b.Callback(), query_expr, start_key=hash_key_75, end_key=None, limit=50)
        _QueryAndVerify(cls, b.Callback(), query_expr, start_key=hash_key_25, end_key=hash_key_75, limit=50)
        _QueryAndVerify(cls, b.Callback(), query_expr, start_key=hash_key_25, end_key=hash_key_75, limit=1)
        _QueryAndVerify(cls, b.Callback(), query_expr, start_key=hash_key_25, end_key=hash_key_75, limit=100)

    # Create 90 users all with the same given name, and 90 followers for the same viewpoint,
    # and 90 followers with same adding_user_id.
    for i in xrange(90):
      user_id = i + 10
      self.UpdateDBObject(User, given_name=name, user_id=user_id, signing_key={})
      self.UpdateDBObject(Follower, user_id=user_id, viewpoint_id=vp_id)

    with util.Barrier(self.stop) as b:
      _RunQueries(User, ('user.given_name={n}', {'n': name}), DBKey(25, None), DBKey(75, None), b.Callback())
      _RunQueries(Follower, ('follower.viewpoint_id={id}', {'id': vp_id}), DBKey(25, vp_id), DBKey(75, vp_id),
                  b.Callback())

  def testUnicode(self):
    """Test various interesting Unicode characters."""
    base_name = escape.utf8(u'ààà朋友你好abc123\U00010000\U00010000\x00\x01\b\n\t ')
    timestamp = time.time()
    contact_id_lookup = dict()

    def _CreateContact(index):
      name = base_name + str(index)
      identity_key = 'Email:%s' % name
      return Contact.CreateFromKeywords(100, [(identity_key, None)], timestamp, Contact.GMAIL, name=name)

    def _VerifyContacts(query_expr, start_key, end_key, exp_indexes):
      actual_contacts = self._RunAsync(Contact.IndexQuery, self._client, query_expr, None,
                                       start_index_key=start_key, end_index_key=end_key)
      self.assertEqual(len(exp_indexes), len(actual_contacts))
      for expected, actual in zip([_CreateContact(i) for i in exp_indexes], actual_contacts):
        self.assertEqual(expected._asdict(), actual._asdict())

    # Create 3 contacts under user 100 in the db.
    for i in xrange(3):
      contact = _CreateContact(i)
      contact_id_lookup[i] = contact.contact_id
      self._RunAsync(contact.Update, self._client)

    # Get contact by identity.
    identity_key = 'Email:%s' % base_name
    _VerifyContacts(('contact.identities={i}', {'i': identity_key + '0'}), None, None, [0])

    # Get multiple contacts.
    _VerifyContacts(('contact.identities={i} | contact.identities={i2}',
                     {'i': identity_key + '0', 'i2': identity_key + '1'}),
                    None, None, [1, 0])

    # Get contact with start key.
    sort_key = Contact.CreateSortKey(contact_id_lookup[1], timestamp)
    _VerifyContacts(('contact.identities={i} | contact.identities={i2}',
                     {'i': identity_key + '0', 'i2': identity_key + '1'}),
                    DBKey(100, sort_key), None, [0])

    # Get contact with end key.
    sort_key = Contact.CreateSortKey(contact_id_lookup[0], timestamp)
    _VerifyContacts(('contact.identities={i} | contact.identities={i2}',
                     {'i': identity_key + '0', 'i2': identity_key + '1'}),
                    None, DBKey(100, sort_key), [1])
