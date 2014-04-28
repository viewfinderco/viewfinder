#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Facebook-specific test functions.

Creating facebook test users should only need to be done once--they
persist across unittest runs and are shared by all developers. Create
the universe of test users with:

% python -m viewfinder.backend.www.test.facebook_utils --create --num_users=<num>

Query users with:

% python -m viewfinder.backend.www.test.facebook_utils --query

Delete all existing test users with:

% python -m viewfinder.backend.www.test.facebook_utils --delete

  - FacebookUtils: encapsulates Facebook utilities
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import json
import logging
import os
import random
import urllib
import urlparse

from tornado import httpclient, options
from viewfinder.backend.base import base_options, secrets, util

options.define('create', default=False,
               help='Create test users, each with a random selection of friends')
options.define('query', default=False, help='Queries the list of facebook test users')
options.define('delete', default=False, help='Deletes all facebook test users')
options.define('num_users', default=100, help='Number of users for creation')


_FACEBOOK_APP_ACCESS_TOKEN_URL = 'https://graph.facebook.com/oauth/access_token'
_FACEBOOK_QUERY_TEST_USERS_URL = 'https://graph.facebook.com/%s/accounts/test-users'
_FACEBOOK_CREATE_TEST_USER_URL = 'https://graph.facebook.com/%s/accounts/test-users'
_FACEBOOK_DELETE_TEST_USER_URL = 'https://graph.facebook.com/%s'
_FACEBOOK_FRIEND_TEST_USER_URL = 'https://graph.facebook.com/%s/friends/%s'
_FACEBOOK_PERMISSIONS = 'offline_access,user_photos,friends_photos'


class FacebookUtils(object):
  """Provides utilities for interfacing with Facebook test user accounts.
  """
  def __init__(self):
    url = _FACEBOOK_APP_ACCESS_TOKEN_URL + '?' + \
        urllib.urlencode({'client_id': secrets.GetSecret('facebook_api_key'),
                          'client_secret': secrets.GetSecret('facebook_secret'),
                          'grant_type': 'client_credentials'})
    http_client = httpclient.HTTPClient()
    response = http_client.fetch(url, request_timeout=100)
    try:
      self._access_token = urlparse.parse_qs(response.body)['access_token'][0]
    except:
      logging.error('unable to parse access token from response body: %s' % response.body)
      raise

  def CreateTestUser(self, name):
    print 'creating user %s' % name
    url = (_FACEBOOK_CREATE_TEST_USER_URL % secrets.GetSecret('facebook_api_key')) + '?' + \
        urllib.urlencode({'installed': 'true',
                          'name': name,
                          'permissions': _FACEBOOK_PERMISSIONS,
                          'method': 'post',
                          'access_token': self._access_token})
    http_client = httpclient.HTTPClient()
    response = http_client.fetch(url, request_timeout=100)
    try:
      return json.loads(response.body)
    except:
      logging.error('unable to parse user data from response body: %s' % response.body)
      raise

  def DeleteTestUser(self, u):
    assert 'access_token' in u and 'id' in u, u
    print 'deleting user %s' % u['id']
    url = (_FACEBOOK_DELETE_TEST_USER_URL % u['id']) + '?' + \
        urllib.urlencode({'method': 'delete',
                          'access_token': u['access_token']})
    http_client = httpclient.HTTPClient()
    response = http_client.fetch(url, request_timeout=100)
    assert response.body == 'true', 'deleting user: %r' % u


  def QueryFacebookTestUsers(self, limit):
    url = (_FACEBOOK_QUERY_TEST_USERS_URL % secrets.GetSecret('facebook_api_key')) + '?' + \
      urllib.urlencode({'access_token': self._access_token, 'limit': limit})
    http_client = httpclient.HTTPClient()
    response = http_client.fetch(url, request_timeout=100)
    try:
      json_data = json.loads(response.body)
      return json_data['data']
    except:
      logging.error('unable to query facebook test users: %s' % response.body)
      raise

  def CreateFacebookFriend(id1, at1, id2, at2, friendships):
    if (id1, id2) in friendships:
      print 'friendships between %s and %s already exists' % (id1, id2)
      return

    print 'creating friendship between user %s and %s' % (id1, id2)
    try:
      http_client = httpclient.HTTPClient()
      url = (_FACEBOOK_FRIEND_TEST_USER_URL % (id1, id2)) + '?' + \
          urllib.urlencode({'method': 'post', 'access_token': at1})
      response = http_client.fetch(url, request_timeout=100)
      assert response.body == 'true', 'friendship from user %s to %s' % (id1, id2)

      url = (_FACEBOOK_FRIEND_TEST_USER_URL % (id2, id1)) + '?' + \
          urllib.urlencode({'method': 'post', 'access_token': at2})
      response = http_client.fetch(url, request_timeout=100)
      assert response.body == 'true', 'friendship from user %s to %s' % (id2, id1)
      friendships[(id1, id2)] = True
      friendships[(id2, id1)] = True
    except:
      logging.error('unable to create connection')

  def CreateFacebookTestUsers(self):
    users = FacebookUtils.QueryFacebookTestUsers(limit=options.options.num_users)

    with open(os.path.join(os.path.dirname(__file__), 'test_names'), 'r') as f:
      names = f.readlines()
      names = [name.strip() for name in names]
      random.shuffle(names)
      assert len(names) >= options.options.num_users
    logging.info('creating %d Facebook test users (%d more)' % \
                   (options.options.num_users, options.options.num_users - len(users)))

    for i in range(len(users), options.options.num_users):
      users.append(FacebookUtils.CreateTestUser(names[i]))

    logging.info('creating user connections...')
    friendships = dict()
    for cur_u in users:
      max_friends = min(len(users) - 1, 20)
      num_friends = random.randint(1, max_friends)
      friends = set([(u['id'], u['access_token']) for i in xrange(num_friends) \
                       for u in [random.choice(users)] if u != cur_u])
      logging.info('creating %d connections for user %s: %r' % (num_friends, cur_u['id'], friends))
      for friend in friends:
        FacebookUtils.CreateFacebookFriend(cur_u['id'], cur_u['access_token'], friend[0], friend[1], friendships)

  def DeleteFacebookTestUsers(self):
    logging.info('Deleting facebook users')
    http_client = httpclient.HTTPClient()
    users = FacebookUtils.QueryFacebookTestUsers(http_client, secrets.GetSecret('facebook_api_key'),
                                   secrets.GetSecret('facebook_secret'), self._access_token,
                                   limit=options.options.num_users)
    [FacebookUtils.DeleteTestUser(u) for u in users]


def main():
  options.parse_command_line()
  options.options.domain = 'goviewfinder.com'
  secrets.InitSecretsForTest()

  fu = FacebookUtils()

  # All of this synchronous stuff is slow, but it only needs to run once.
  if options.options.delete:
    fu.DeleteFacebookTestUsers()
  if options.options.query:
    users = fu.QueryFacebookTestUsers(limit=options.options.num_users)
    for u in users:
      print u.get('id', 'no id'), u.get('name', 'no name')
  if options.options.create:
    fu.CreateFacebookTestUsers()


if __name__ == '__main__':
  main()
