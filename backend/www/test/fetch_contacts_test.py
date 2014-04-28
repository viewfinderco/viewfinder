#!/usr/bin/env python
#
# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Tests that fetch contacts for simulated Google and Facebook accounts.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import json
import mock
import time

from cStringIO import StringIO
from tornado import httpclient, web
from viewfinder.backend.base import util
from viewfinder.backend.base.exceptions import TooManyRetriesError, FailpointError
from viewfinder.backend.base.testing import MockAsyncHTTPClient
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.op.fetch_contacts_op import FetchContactsOperation
from viewfinder.backend.op.op_context import EnterOpContext
from viewfinder.backend.op.op_mgr_db_client import OpMgrDBClient
from viewfinder.backend.www.auth_viewfinder import LoginViewfinderHandler, VerifyIdBaseHandler
from viewfinder.backend.www.test import service_base_test


class FetchContactsTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(FetchContactsTestCase, self).setUp()

    user_dict = {'name': 'Andy Kimball', 'id': 100}
    self._andy_user, device_id = self._tester.RegisterFacebookUser(user_dict)
    self._andy_facebook = 'FacebookGraph:100'

    self._user_cookie = self._GetSecureUserCookie(self._andy_user, device_id)
    user_dict = {'name': 'Andrew Kimball', 'email': 'andy@emailscrubbed.com', 'verified_email': True}
    self._tester.LinkGoogleUser(user_dict, user_cookie=self._user_cookie)
    self._andy_google = 'Email:andy@emailscrubbed.com'

    user_dict = {'name': 'Mike Purtell', 'given_name': 'Mike', 'family_name': 'Purtell', 'email': 'mike@vf.com'}

    self._old_fetch_count = FetchContactsOperation._MAX_FETCH_COUNT
    FetchContactsOperation._MAX_FETCH_COUNT = 3

  def tearDown(self):
    super(FetchContactsTestCase, self).tearDown()
    FetchContactsOperation._MAX_FETCH_COUNT = self._old_fetch_count

  def testSingleContact(self):
    """Test fetch of single contact."""
    contacts = self._TestFetchContacts(self._andy_facebook, self._andy_user.user_id,
                                       {'data': [{'id': 200, 'name': 'Rachel Kimball'}]})
    self.assertEqual(contacts[0].identities_properties[0], ['FacebookGraph:200', None])
    self.assertEqual(contacts[0].name, 'Rachel Kimball')

    contacts = self._TestFetchContacts(self._andy_google, self._andy_user.user_id,
                                       self._CreateGoogleContactFeed([{'emails': [('rachel@emailscrubbed.com', None)],
                                                                       'name': 'Rachel Kimball'}]))
    self.assertEqual(contacts[0].identities_properties[0], ['Email:rachel@emailscrubbed.com', None])
    self.assertEqual(contacts[0].name, 'Rachel Kimball')

  def testSingleContactWithUnsupportedAuthority(self):
    """Test fetch of contacts using an identity with an authority that we don't support."""
    identity_key = 'Email:' + self._user.email
    # We need an access_token set on the identity in order to hit the desired code path.
    identity = self._RunAsync(Identity.Query, self._client, identity_key, None)
    identity.access_token = '123'
    self._RunAsync(identity.Update, self._client)
    # Update model to match.
    self._validator.ValidateUpdateDBObject(Identity, **identity._asdict())

    self._FetchContacts(identity_key,
                        self._user.user_id,
                        self._CreateGoogleContactFeed([{'emails': [('john@rr.com', None)],
                                                        'name': 'John Purtell'}]),
                        None)
    # Expectation is a no-op.  Shouldn't fail, but also shouldn't result in any new contacts.
    self._AssertContactCounts(self._user.user_id, 0, 0)



  def testMultipleContacts(self):
    """Test fetch of multiple contacts."""
    contacts = self._TestFetchContacts(self._andy_facebook, self._andy_user.user_id,
                                       {'data': [{'id': 200, 'name': 'Rachel Kimball'},
                                                 {'id': 300, 'name': 'Mike Purtell'},
                                                 {'id': 400, 'name': 'Matt Tracy'}]})
    self.assertEqual(len(contacts), 3)

    contacts = self._TestFetchContacts(self._andy_google, self._andy_user.user_id,
                                       self._CreateGoogleContactFeed([{'emails': [('rachel@emailscrubbed.com', None)],
                                                                       'name': 'Rachel Kimball'},
                                                                      {'emails': [('mike@emailscrubbed.com', None)],
                                                                       'name': 'Mike Purtell'},
                                                                      {'emails': [('matt@emailscrubbed.com', None)],
                                                                       'name': 'Matt Tracy'},
                                                                      {'phones': [('+13191234567', 'Work')],
                                                                       'name': 'J. Smith'},
                                                                      {'phones': [('+13195550210', 'cabin')],
                                                                       'emails': [('j@emailscrubbed.com', None)],
                                                                       'name': 'K. Smith'},
                                                                      {'phones': [('+13195550211', 'Beach')],
                                                                       'emails': [('j@emailscrubbed.com', None)],
                                                                       'name': 'K. Smith II'},
                                                                      {'phones': [('+13195550212', 'Fax'),
                                                                                  ('+12065550213', 'Home')],
                                                                       'emails': [('jason@emailscrubbed.com', None),
                                                                                  ('jason@bitnet.edu', 'Other')],
                                                                       'name': 'Jason Smith'}]))
    self.assertEqual(len(contacts), 7)

  def testInvalidPhoneNumbers(self):
    """Fetch a contact with just an invalid phone number and observe that the contact isn't fetched.
    This is because we only accept fetched contacts that have at least one valid identity.
    """
    contacts = self._TestFetchContacts(self._andy_google, self._andy_user.user_id,
                                       self._CreateGoogleContactFeed([{'phones': [('1fss3193770219', None)],
                                                                       'name': 'J. Smith'}]))
    self.assertEqual(len(contacts), 0)

  def testGMailRelField(self):
    """Check mapping of Google's wellknown contact relations."""
    feed = self._CreateGoogleContactFeed([{'emails': [('mike@emailscrubbed.com', None)],
                                           'name': 'Mike Purtell'},
                                          {'phones': [('+13191234567', 'Work')],
                                           'name': 'J. Smith'},
                                          {'phones': [('+13195550210', 'cabin')],
                                           'name': 'K. Smith'}])

    # Check that the feed generated what we intend to test.
    # 'None' should generate the 'other' schema identifier for the rel field and no label field:
    self.assertEqual(feed['feed']['entry'][0]['gd$email'][0]['rel'], 'http://schemas.google.com/g/2005#other')
    self.assertNotIn('label', feed['feed']['entry'][0]['gd$email'][0])

    # Check that we got the desired rel value and that the label field didn't get set.
    self.assertEqual(feed['feed']['entry'][1]['gd$phoneNumber'][0]['rel'], 'http://schemas.google.com/g/2005#work')
    self.assertNotIn('label', feed['feed']['entry'][1]['gd$phoneNumber'][0])

    # We just care that the label got set, regardless of the rel field, because we give it priority.
    self.assertEqual(feed['feed']['entry'][2]['gd$phoneNumber'][0]['label'], 'cabin')

    self._TestFetchContacts(self._andy_google, self._andy_user.user_id, feed)

    # Check the actual contacts, not the ones in the model.
    contacts = self._RunAsync(Contact.RangeQuery, self._client, self._andy_user.user_id, None, 10, None)

    self.assertEqual(len(contacts), 3)
    contacts.sort(key=lambda x: x.name)
    self.assertEqual(contacts[0].name, 'J. Smith')
    # This one translates from the well known value in the rel field.
    self.assertEqual(contacts[0].identities_properties[0][1], 'Work')
    self.assertEqual(contacts[1].name, 'K. Smith')
    # This one takes the label field.
    self.assertEqual(contacts[1].identities_properties[0][1], 'cabin')
    self.assertEqual(contacts[2].name, 'Mike Purtell')
    # This one has the well known value, '...#other, in the rel field and we translate that to None.
    self.assertEqual(contacts[2].identities_properties[0][1], None)

  def testNoContacts(self):
    """Test fetch of no contacts."""
    contacts = self._TestFetchContacts(self._andy_facebook, self._andy_user.user_id,
                                       {'data': []}, {'data': []})
    self.assertEqual(len(contacts), 0)

    contacts = self._TestFetchContacts(self._andy_google, self._andy_user.user_id,
                                       self._CreateGoogleContactFeed([]))
    self.assertEqual(len(contacts), 0)

    contacts = self._TestFetchContacts(self._andy_google, self._andy_user.user_id,
                                       {'feed': {'entry': [{}],
                                                 'openSearch$startIndex': {'$t': '1'},
                                                 'openSearch$totalResults': {'$t': '0'}}})
    self.assertEqual(len(contacts), 0)

  def testContactsWithoutIdentities(self):
    """Test fetching contacts that don't have any identities.
    These identities should get skipped during fetch.
    """
    contacts = self._TestFetchContacts(self._andy_facebook, self._andy_user.user_id,
                                       {'data': [{'name': 'Rachel Kimball'},
                                                 {'name': 'Rachel Kimball III'}]})

    self.assertEqual(len(contacts), 0)

    contacts = self._TestFetchContacts(self._andy_google, self._andy_user.user_id,
                                       self._CreateGoogleContactFeed([{'name': 'Rachel Kimball'},
                                                                      {'name': 'Rachel Kimball III'}]))
    self.assertEqual(len(contacts), 0)

  def testDuplicateContacts(self):
    """Test fetch with duplicate contacts."""
    self._FetchContacts(self._andy_facebook,
                        self._andy_user.user_id,
                        {'data': [{'id': 200, 'name': 'Rachel Kimball'},
                                  {'id': 200, 'name': 'Rachel Kimball'}]})
    # Should be only one contact after this fetch.
    self._AssertContactCounts(self._andy_user.user_id, 1, 0)

    self._FetchContacts(self._andy_google,
                        self._andy_user.user_id,
                        self._CreateGoogleContactFeed([{'emails': [('rachel@emailscrubbed.com', None)],
                                                        'name': 'Rachel Kimball'},
                                                       {'emails': [('rachel@emailscrubbed.com', None)],
                                                        'name': 'Rachel Kimball'}]))
    # There should be just one more contact now for the one deduped contact fetched for a different contact source.
    self._AssertContactCounts(self._andy_user.user_id, 2, 0)

  def testSerialContacts(self):
    """Test fetching contact #1, then contact #2."""
    self._TestFetchContacts(self._andy_facebook, self._andy_user.user_id,
                                       {'data': [{'id': 200, 'name': 'Rachel Kimball'}]})
    self._TestFetchContacts(self._andy_facebook, self._andy_user.user_id,
                            {'data': [{'id': 300, 'name': 'Mike Purtell'}]})

    self._TestFetchContacts(self._andy_google, self._andy_user.user_id,
                            self._CreateGoogleContactFeed([{'emails': [('rachel@emailscrubbed.com', None)],
                                                            'name': 'Rachel Kimball'}]))
    self._TestFetchContacts(self._andy_google, self._andy_user.user_id,
                            self._CreateGoogleContactFeed([{'emails': [('mike@emailscrubbed.com', None)],
                                                            'name': 'Mike Purtell'}]))

  def testSameContact(self):
    """Test same contact fetched twice."""
    self._TestFetchContacts(self._andy_facebook, self._andy_user.user_id,
                            {'data': [{'id': 200, 'name': 'Rachel Kimball'}]})
    self._TestFetchContacts(self._andy_facebook, self._andy_user.user_id,
                            {'data': [{'id': 200, 'name': 'Rachel Kimball'}]})

    self._TestFetchContacts(self._andy_google, self._andy_user.user_id,
                            self._CreateGoogleContactFeed([{'emails': [('rachel@emailscrubbed.com', None)],
                                                            'name': 'Rachel Kimball'}]))
    self._TestFetchContacts(self._andy_google, self._andy_user.user_id,
                            self._CreateGoogleContactFeed([{'emails': [('rachel@emailscrubbed.com', None)],
                                                            'name': 'Rachel Kimball'}]))

  def testRenamedContacts(self):
    """Test fetching contacts, then same contacts with new names."""
    contacts = self._TestFetchContacts(self._andy_facebook, self._andy_user.user_id,
                                       {'data': [{'id': 200, 'name': 'Andrew Kimball'},
                                                 {'id': 300, 'name': 'Spencer Kimball', 'first_name': 'Spencer'},
                                                 {'id': 400, 'name': 'Kathryn Kimball', 'last_name': 'Kimball'},
                                                 {'id': 500, 'name': 'Michael Purtell'},
                                                 {'id': 600, 'name': 'Peter Mattis', 'last_name': 'Mattis'}]})
    contacts = self._TestFetchContacts(self._andy_facebook, self._andy_user.user_id,
                                       {'data': [{'id': 200, 'name': 'Andy Kimball'},
                                                 {'id': 300, 'name': 'Spencer Kimball', 'first_name': 'Spence'},
                                                 {'id': 400, 'name': 'Kathryn Kimball', 'last_name': 'Mattis'},
                                                 {'id': 500,
                                                  'name': 'Mike Purtell Reincarnated',
                                                  'first_name': 'Mike',
                                                  'last_name': 'Purtell Reincarnated'},
                                                 {'id': 600, 'name': 'Pete Mattis', 'first_name': 'Pete'}]})
    self.assertEqual(contacts[0].name, 'Andy Kimball')
    self.assertEqual(contacts[1].name, 'Spencer Kimball')
    self.assertEqual(contacts[1].given_name, 'Spence')
    self.assertEqual(contacts[2].name, 'Kathryn Kimball')
    self.assertEqual(contacts[2].family_name, 'Mattis')
    self.assertEqual(contacts[3].name, 'Mike Purtell Reincarnated')
    self.assertEqual(contacts[4].name, 'Pete Mattis')
    self.assertEqual(contacts[4].given_name, 'Pete')
    self.assertIsNone(contacts[4].family_name)

    contacts = self._TestFetchContacts(self._andy_google, self._andy_user.user_id,
                                       self._CreateGoogleContactFeed([{'emails': [('kimball.andy@emailscrubbed.com', None)],
                                                                       'name': 'Andrew Kimball'},
                                                                      {'emails': [('spencer@emailscrubbed.com', None)],
                                                                       'name': 'Spencer Kimball',
                                                                       'given_name': 'Spencer'},
                                                                      {'emails': [('kat@foo.com', None)],
                                                                       'family_name': 'Kimball'},
                                                                      {'emails': [('mike@emailscrubbed.com', None)],
                                                                       'phones': [('+15151234567', None)]},
                                                                      {'emails': [('pete@emailscrubbed.com', None)],
                                                                       'family_name': 'Mattis'}]))
    contacts = self._TestFetchContacts(self._andy_google, self._andy_user.user_id,
                                       self._CreateGoogleContactFeed([{'emails': [('kimball.andy@emailscrubbed.com', None)],
                                                                       'name': 'Andy Kimball'},
                                                                      {'emails': [('spencer@emailscrubbed.com', None)],
                                                                       'phones': [('+15151234567', 'Boat')],
                                                                       'name': 'Spencer Kimball',
                                                                       'given_name': 'Spence'},
                                                                      {'emails': [('kat@foo.com', None)],
                                                                       'family_name': 'Mattis'},
                                                                      {'emails': [('mike@emailscrubbed.com', None)],
                                                                       'phones': [('+12121234567', None)],
                                                                       'name': 'Mike Purtell',
                                                                       'given_name': 'Mike',
                                                                       'family_name': 'Purtell'},
                                                                      {'emails': [('pete@emailscrubbed.com', None)],
                                                                       'given_name': 'Pete'}]))
    self.assertEqual(contacts[0].name, 'Andy Kimball')
    self.assertEqual(contacts[1].name, 'Spencer Kimball')
    self.assertEqual(contacts[1].given_name, 'Spence')
    self.assertIn('Phone:+15151234567', contacts[1].identities)
    self.assertIn(['Phone:+15151234567', 'Boat'], contacts[1].identities_properties)
    self.assertEqual(contacts[2].family_name, 'Mattis')
    self.assertEqual(contacts[3].name, 'Mike Purtell')
    self.assertIn('Phone:+12121234567', contacts[3].identities)
    self.assertIn(['Phone:+12121234567', None], contacts[3].identities_properties)
    self.assertEqual(contacts[4].given_name, 'Pete')
    self.assertIsNone(contacts[4].family_name)

  def testMissingName(self):
    """Test contact without name."""
    contacts = self._TestFetchContacts(self._andy_facebook, self._andy_user.user_id,
                                       {'data': [{'id': 200},
                                                 {'id': 300, 'name': 'Mike Purtell'}]})
    self.assertEqual(len(contacts), 1)

    contacts = self._TestFetchContacts(self._andy_google, self._andy_user.user_id,
                                       {'feed': {'entry': [{'gd$email': [{'primary': True,
                                                                          'address': 'kimball.andy@emailscrubbed.com'}]}],
                                                 'openSearch$startIndex': {'$t': '1'},
                                                 'openSearch$totalResults': {'$t': '1'}}})
    self.assertIsNone(contacts[0].name)

  def testPaging(self):
    """Test multiple pages of contacts."""
    with mock.patch('tornado.httpclient.AsyncHTTPClient', MockAsyncHTTPClient()) as mock_client:
      # Start with Facebook case.
      photos_dict = {'data': [{'created_time': '2013-01-01 00:00:00', 'from': {'id': 200}},
                              {'created_time': '2013-01-01 00:00:00', 'from': {'id': 200}},
                              {'created_time': '2013-01-01 00:00:00', 'from': {'id': 200}}],
                     'paging': {'next': 'https://graph.facebook.com/me/more-photos'}}
      self._AddMockJSONResponse(mock_client, r'https://graph.facebook.com/me/photos\?', photos_dict)

      more_photos_dict = {'data': [{'created_time': '2012-12-31 00:00:00', 'from': {'id': 300}}]}
      self._AddMockJSONResponse(mock_client, r'https://graph.facebook.com/me/more-photos', more_photos_dict)

      people_dict = {'data': [{'id': 200, 'name': 'Rachel Kimball', 'rank': 0},
                              {'id': 300, 'name': 'Mike Purtell', 'rank': 1},
                              {'id': 400, 'name': 'Matt Tracy'}],
                     'paging': {'next': 'https://graph.facebook.com/me/more-friends'}}
      self._AddMockJSONResponse(mock_client, r'https://graph.facebook.com/me/friends\?', people_dict)

      more_people_dict = {'data': [{'id': 500, 'name': 'Ben Darnell'}]}
      self._AddMockJSONResponse(mock_client, r'https://graph.facebook.com/me/more-friends', more_people_dict)

      self._RunFetchContactsOperation(self._andy_facebook, self._andy_user.user_id)

      # Validate that all contacts from both pages were created.
      self._ValidateContacts(self._andy_facebook, self._andy_user.user_id,
                             {'data': people_dict['data'] + more_people_dict['data']})

      # Now test Google case.
      people_dict = {'feed': {'entry': [{'gd$email': [{'primary': True,
                                                       'address': 'kimball.andy@emailscrubbed.com'}]}],
                              'openSearch$startIndex': {'$t': '1'},
                              'openSearch$totalResults': {'$t': '2'}}}
      self._AddMockJSONResponse(mock_client, r'https://www.google.com/m8/feeds/contacts/default/full.*start-index=1',
                                people_dict)

      people_dict = {'feed': {'entry': [{'gd$email': [{'primary': True,
                                                       'address': 'mike@emailscrubbed.com'}]}],
                              'openSearch$startIndex': {'$t': '2'},
                              'openSearch$totalResults': {'$t': '2'}}}
      self._AddMockJSONResponse(mock_client, r'https://www.google.com/m8/feeds/contacts/default/full.*start-index=2',
                                people_dict)

      self._RunFetchContactsOperation(self._andy_google, self._andy_user.user_id)

  def testPosterRanking(self):
    """Test ranking of person who posted photos."""
    util._TEST_TIME = time.mktime((2013, 1, 2, 0, 0, 0, 0, 0, 0))
    self._TestFetchContacts(self._andy_facebook, self._andy_user.user_id,
                            {'data': [{'id': 200, 'name': 'Rachel Kimball', 'rank': 3},
                                      {'id': 300, 'name': 'Mike Purtell', 'rank': 2},
                                      {'id': 400, 'name': 'Matt Tracy', 'rank': 1},
                                      {'id': 500, 'name': 'Ben Darnell', 'rank': 4}]},
                            {'data': [{'created_time': '2012-12-31 00:00:00', 'from': {'id': 200}},
                                      {'created_time': '2013-01-01 00:00:00', 'from': {'id': 300}},
                                      {'created_time': '2013-01-01 00:00:00', 'from': {'id': 400}},
                                      {'created_time': '2013-01-01 00:00:00', 'from': {'id': 400}},
                                      {'created_time': '2100-01-01 00:00:00', 'from': {'id': 1000}},
                                      {'created_time': '2013-01-02 00:00:00'},
                                      {'from': {'id': 500}},
                                      {'from': None}]})

  def testTaggedRanking(self):
    """Test ranking of people tagged in photos."""
    util._TEST_TIME = time.mktime((2013, 1, 2, 0, 0, 0, 0, 0, 0))
    self._TestFetchContacts(self._andy_facebook, self._andy_user.user_id,
                            {'data': [{'id': 200, 'name': 'Rachel Kimball', 'rank': 0},
                                      {'id': 300, 'name': 'Mike Purtell', 'rank': 1},
                                      {'id': 400, 'name': 'Matt Tracy', 'rank': 2}]},
                            {'data': [{'tags': {'data': [{'id': 200, 'created_time': '2012-12-31 00:00:00'},
                                                         {'id': 200, 'created_time': '2012-12-31 00:00:00'},
                                                         {'id': 300, 'created_time': '2010-12-31 00:00:00'},
                                                         {'id': 300},
                                                         {}]}},
                                      {'tags': None},
                                      {'tags': {'data': [{'id': 400, 'created_time': '2010-12-31 00:00:00'}]}}]})

  def testLikedRanking(self):
    """Test ranking of people who liked photos."""
    util._TEST_TIME = time.mktime((2013, 1, 2, 0, 0, 0, 0, 0, 0))
    self._TestFetchContacts(self._andy_facebook, self._andy_user.user_id,
                            {'data': [{'id': 200, 'name': 'Rachel Kimball', 'rank': 0},
                                      {'id': 300, 'name': 'Mike Purtell', 'rank': 2},
                                      {'id': 400, 'name': 'Matt Tracy', 'rank': 1},
                                      {'id': 500, 'name': 'Ben Darnell'}]},
                            {'data': [{'created_time': '2012-01-01 00:00:00',
                                       'from': {'id': 200},
                                       'likes': {'data': [{'id': 200}, {}]}},
                                      {'created_time': '1900-01-01 00:00:00',
                                       'from': {'id': 300},
                                       'likes': {'data': [{'id': 300}]}},
                                      {'created_time': '2012-01-01 00:00:00',
                                       'from': {'id': 400},
                                       'likes': {'data': [{'id': 400}, {'id': 200}, {'id': 500}]}},
                                      {'likes': {'data': [{'id': 300}, {'id': 300}]}},
                                      {'likes': None} ]})

  def testMultipleEmails(self):
    """Test Google responses containing multiple contact emails."""
    feed = {'feed': {'entry': [{'gd$email': [{'address': 'mike@emailscrubbed.com'}]},
                               {'gd$email': [{'address': 'andy@emailscrubbed.com'},
                                             {'primary': True,
                                              'address': 'kimball.andy@emailscrubbed.com'}]},
                               {'gd$email': []},
                               {} ],
                     'openSearch$startIndex': {'$t': '1'},
                     'openSearch$totalResults': {'$t': '2'}}}
    contacts = self._TestFetchContacts(self._andy_google, self._andy_user.user_id, feed)
    self.assertEqual(len(contacts), 2)
    self.assertEqual(len(contacts[0].identities_properties), 1)
    self.assertEqual(contacts[0].identities_properties[0], ['Email:mike@emailscrubbed.com', None])
    self.assertEqual(len(contacts[1].identities_properties), 2)
    # 'kimball.any@emailscrubbed.com' should be first in list because it's the primary email address.
    self.assertEqual(contacts[1].identities_properties[0], ['Email:kimball.andy@emailscrubbed.com', None])
    self.assertEqual(contacts[1].identities_properties[1], ['Email:andy@emailscrubbed.com', None])

  def testFetchErrors(self):
    """ERROR: Test errors on fetch attempts."""
    def _RunFetchContactsOperationDirect(identity_key, user_id):
      """Invokes the FetchContacts operation for the specified user."""
      op = Operation(user_id, Operation.ConstructOperationId(Device.SYSTEM, 1))
      op.timestamp = util._TEST_TIME
      with EnterOpContext(op):
        self._RunAsync(FetchContactsOperation.Execute,
                       OpMgrDBClient(self._client),
                       key=identity_key,
                       user_id=user_id)

    def _CreateErrorResponse(request):
      return httpclient.HTTPResponse(request, 400)

    with mock.patch('tornado.httpclient.AsyncHTTPClient', MockAsyncHTTPClient()) as mock_client:
      mock_client.map(r'https://graph.facebook.com/me/photos\?', _CreateErrorResponse)
      self.assertRaises(web.HTTPError, _RunFetchContactsOperationDirect,
                        self._andy_facebook, self._andy_user.user_id)

      self._AddMockJSONResponse(mock_client, r'https://graph.facebook.com/me/photos\?', {'data': []})
      mock_client.map(r'https://graph.facebook.com/me/friends\?', _CreateErrorResponse)
      self.assertRaises(TooManyRetriesError, _RunFetchContactsOperationDirect,
                        self._andy_facebook, self._andy_user.user_id)

      mock_client.map(r'https://www.google.com/m8/feeds/contacts/default/full', _CreateErrorResponse)
      self.assertRaises(TooManyRetriesError, _RunFetchContactsOperationDirect,
                        self._andy_google, self._andy_user.user_id)

  @mock.patch.object(Contact, 'MAX_CONTACTS_LIMIT', 2)
  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testMaxContactsLimit(self):
    """Try various sequences of fetches to hit total contacts limit."""
    # Fetch one contact from Facebook.
    self._FetchContacts(self._andy_facebook,
                        self._andy_user.user_id,
                        {'data': [{'id': 200, 'name': 'Andrew Kimball'}]})
    util._TEST_TIME += 1
    self._AssertContactCounts(self._andy_user.user_id, 1, 0)

    # Fetch one (different) contact from Facebook.  This leave the previously fetched contact in the 'removed' state.
    self._FetchContacts(self._andy_facebook,
                        self._andy_user.user_id,
                        {'data': [{'id': 600, 'name': 'Peter Mattis', 'last_name': 'Mattis'}]})
    util._TEST_TIME += 1
    self._AssertContactCounts(self._andy_user.user_id, 1, 1)

    # Fetch two (different from previous) contacts from Facebook.  This leads to two 'removed' contacts.
    self._FetchContacts(self._andy_facebook,
                        self._andy_user.user_id,
                        {'data': [{'id': 201, 'name': 'Andrew Kimball Sr.'},
                                  {'id': 601, 'name': 'Peter Mattis Sr.', 'last_name': 'Mattis'}]})
    util._TEST_TIME += 1
    self._AssertContactCounts(self._andy_user.user_id, 2, 2)

    # Fetch a google contact.  Because there are no previously fetched google contacts, none of the existing
    #  contacts are removed and this one would exceed the limit of total contacts and so is not inserted.
    self._FetchContacts(self._andy_google,
                        self._andy_user.user_id,
                        self._CreateGoogleContactFeed([{'emails': [('kimball.andy@emailscrubbed.com', None)],
                                                        'name': 'Andrew Kimball'}]),
                        None)
    util._TEST_TIME += 1
    self._AssertContactCounts(self._andy_user.user_id, 2, 2)

    # Now, fetch a single Facebook contact.  This lowers the total number of present contacts to 1.
    self._FetchContacts(self._andy_facebook,
                        self._andy_user.user_id,
                        {'data': [{'id': 202, 'name': 'Andrew Kimball'}]})
    util._TEST_TIME += 1
    self._AssertContactCounts(self._andy_user.user_id, 1, 4)

    # Now, try to add the google contact again and see that the number of present contacts increases.
    self._FetchContacts(self._andy_google,
                        self._andy_user.user_id,
                        self._CreateGoogleContactFeed([{'emails': [('kimball.andy@emailscrubbed.com', None)],
                                                        'name': 'Andrew Kimball'}]),
                        None)
    util._TEST_TIME += 1
    self._AssertContactCounts(self._andy_user.user_id, 2, 4)

  @mock.patch.object(Contact, 'MAX_REMOVED_CONTACTS_LIMIT', 2)
  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testRemovedContactsReset(self):
    """Try various sequences of fetches to hit total contacts limit."""
    # Fetch one contact from Facebook.
    self._FetchContacts(self._andy_facebook,
                        self._andy_user.user_id,
                        {'data': [{'id': 200, 'name': 'Andrew Kimball'}]})
    util._TEST_TIME += 1
    self._AssertContactCounts(self._andy_user.user_id, 1, 0)

    # Fetch one (different) contact from Facebook.  This leave the previously fetched contact in the 'removed' state.
    self._FetchContacts(self._andy_facebook,
                        self._andy_user.user_id,
                        {'data': [{'id': 600, 'name': 'Peter Mattis', 'last_name': 'Mattis'}]})
    util._TEST_TIME += 1
    self._AssertContactCounts(self._andy_user.user_id, 1, 1)

    # Fetch two (different from previous) contacts from Facebook.  This causes reset: 'removed' contacts => 0.
    self._FetchContacts(self._andy_facebook,
                        self._andy_user.user_id,
                        {'data': [{'id': 201, 'name': 'Andrew Kimball Sr.'},
                                  {'id': 601, 'name': 'Peter Mattis Sr.', 'last_name': 'Mattis'}]})
    util._TEST_TIME += 1
    self._AssertContactCounts(self._andy_user.user_id, 2, 0)

    # Now, fetch a single Facebook contact which matches one of the existing contacts.
    #   This will result in the other contact getting removed.
    self._FetchContacts(self._andy_facebook,
                        self._andy_user.user_id,
                        {'data': [{'id': 201, 'name': 'Andrew Kimball Sr.'}]})
    util._TEST_TIME += 1
    self._AssertContactCounts(self._andy_user.user_id, 1, 1)

    # Now, fetch a Google contact and see just the 'present' count increase.
    self._FetchContacts(self._andy_google,
                        self._andy_user.user_id,
                        self._CreateGoogleContactFeed([{'emails': [('kimball.andy@emailscrubbed.com', None)],
                                                        'name': 'Andrew Kimball'}]),
                        None)
    util._TEST_TIME += 1
    self._AssertContactCounts(self._andy_user.user_id, 2, 1)

    # Now, fetch a different Google contact and see the 'removed' count go to zero because of the previous
    #   Google contact being removed and causing the reset limit to get hit.
    self._FetchContacts(self._andy_google,
                        self._andy_user.user_id,
                        self._CreateGoogleContactFeed([{'emails': [('Michael.Purtell@emailscrubbed.com', None)],
                                                        'name': 'Mike Purtell'}]),
                        None)
    util._TEST_TIME += 1
    self._AssertContactCounts(self._andy_user.user_id, 2, 0)

  def _AssertContactCounts(self, user_id, expected_present_count, expected_removed_count):
    """Checks that the number present and removed contacts, for the given user, matches what's expected."""
    contacts = self._RunAsync(Contact.RangeQuery, self._client, user_id, None, 1000, None)
    actual_removed_count = len([c for c in contacts if c.IsRemoved()])
    actual_present_count = len(contacts) - actual_removed_count
    if expected_present_count != actual_present_count:
      self.assertEqual(expected_present_count, actual_present_count)
    if expected_removed_count != actual_removed_count:
      self.assertEqual(expected_removed_count, actual_removed_count)

  def _CreateGoogleContactFeed(self, contact_list):
    """Create simple Google contact field containing list of contacts with a dict containing
    the following optional fields:
      {'email': [('andy@emailscrubbed.com', type), ...],  # First one will be primary.
       'phones': [('+13191234567', type), ...],
       'name': 'Andy Kimball',
       'given_name': 'Andy',
       'family_name': 'Kimball'}
    """
    feed = {'feed': {'entry': [],
                     'openSearch$startIndex': {'$t': '1'},
                     'openSearch$totalResults': {'$t': str(len(contact_list))}}}

    for contact in contact_list:
      gd_name = {}
      if 'name' in contact:
        gd_name['gd$fullName'] = {'$t': contact['name']}
      if 'given_name' in contact:
        gd_name['gd$givenName'] = {'$t': contact['given_name']}
      if 'family_name' in contact:
        gd_name['gd$familyName'] = {'$t': contact['family_name']}

      email_list = []
      for email, label in contact.get('emails', []):
        email_info = {'address': email}
        for key, val in FetchContactsOperation._GOOGLE_TYPE_LOOKUP.items():
          if label == val:
            email_info['rel'] = key
        if 'rel' not in email_info:
          email_info['label'] = label
        email_list.append(email_info)
      if len(email_list) > 0:
        email_list[0]['primary'] = True
      contact_entry = {'gd$email': email_list}

      phone_list = []
      for phone, label in contact.get('phones', []):
        phone_info = {'uri': 'tel:' + phone, '$t': phone}
        for key, val in FetchContactsOperation._GOOGLE_TYPE_LOOKUP.items():
          if label == val:
            phone_info['rel'] = key
        if 'rel' not in phone_info:
          phone_info['label'] = label
        phone_list.append(phone_info)
      util.SetIfNotEmpty(contact_entry, 'gd$phoneNumber', phone_list)

      util.SetIfNotEmpty(contact_entry, 'gd$name', gd_name)

      feed['feed']['entry'].append(contact_entry)

    return feed

  def _FetchContacts(self, identity_key, user_id, people_dict, photos_dict=None):
    """Fetches contacts from mocked Facebook or Google service."""
    with mock.patch('tornado.httpclient.AsyncHTTPClient', MockAsyncHTTPClient()) as mock_client:
      photos_dict = photos_dict or {'data': []}
      self._AddMockJSONResponse(mock_client, r'https://graph.facebook.com/me/photos\?', photos_dict)
      self._AddMockJSONResponse(mock_client, r'https://graph.facebook.com/me/friends\?', people_dict)
      self._AddMockJSONResponse(mock_client, r'https://www.google.com/m8/feeds/contacts/default/full', people_dict)

      self._RunFetchContactsOperation(identity_key, user_id)

  def _RunFetchContactsOperation(self, identity_key, user_id):
    """Invokes the FetchContacts operation for the specified user."""
    request = {'key': identity_key,
               'user_id': user_id,
               'headers': {'synchronous': True}}
    self._RunAsync(Operation.CreateAndExecute,
                   self._client,
                   user_id,
                   Device.SYSTEM,
                   'FetchContactsOperation.Execute',
                   request)

  def _AddMockJSONResponse(self, mock_client, url, response_dict):
    """Adds a mapping entry to the mock client such that requests to "url" will return an HTTP
    response containing the JSON-formatted "response_dict".
    """
    def _CreateResponse(request):
      return httpclient.HTTPResponse(request, 200,
                                     headers={'Content-Type': 'application/json'},
                                     buffer=StringIO(json.dumps(response_dict)))

    mock_client.map(url, _CreateResponse)

  def _ValidateContacts(self, identity_key, user_id, people_dict):
    """Validates that corresponding contacts have been created for the people described in
    "people_dict". Returns the list of contact objects.
    """
    contacts = []
    if 'FacebookGraph:' in identity_key:
      contact_source = Contact.FACEBOOK
      for data in people_dict['data']:
        if 'name' in data and data.has_key('id'):
          contacts.append(self._ValidateOneContact(user_id,
                                                   [('FacebookGraph:' + str(data.get('id')), None)],
                                                   Contact.FACEBOOK,
                                                   data.get('name', None),
                                                   data.get('first_name', None),
                                                   data.get('last_name', None),
                                                   data.get('rank', None)))
    else:
      contact_source = Contact.GMAIL
      for rank, entry in enumerate(people_dict['feed']['entry']):
        identities_properties = []
        email_info_list = sorted(entry.get('gd$email', []), key=lambda e: not e.get('primary', False))
        for email_info in email_info_list:
          email = email_info['address']
          gmail_type_str =  FetchContactsOperation._GOOGLE_TYPE_LOOKUP.get(email_info.get('rel', None), None)
          description = email_info.get('label', gmail_type_str)
          primary = email_info.get('primary', False)
          identity_properties = ('Email:' + email, description)
          if primary:
            identities_properties.insert(0, identity_properties)
          else:
            identities_properties.append(identity_properties)
        phone_info_list = entry.get('gd$phoneNumber', [])
        for phone_info in phone_info_list:
          phone = phone_info['uri']
          if phone.startswith('tel:+'):
            gmail_type_str =  FetchContactsOperation._GOOGLE_TYPE_LOOKUP.get(phone_info.get('rel', None), None)
            description = phone_info.get('label', gmail_type_str)
            identity_properties = ('Phone:' + phone[4:], description)
            identities_properties.append(identity_properties)
        name = entry.get('gd$name', {}).get('gd$fullName', {}).get('$t', None)
        given_name = entry.get('gd$name', {}).get('gd$givenName', {}).get('$t', None)
        family_name = entry.get('gd$name', {}).get('gd$familyName', {}).get('$t', None)
        if len(identities_properties) > 0:
          contacts.append(self._ValidateOneContact(user_id,
                                                   identities_properties,
                                                   Contact.GMAIL,
                                                   name,
                                                   given_name,
                                                   family_name,
                                                   None))

    # Now, 'remove' any contacts that are present, but not in this fetched batch (in same contact_source).
    fetched_contact_ids = {c.contact_id for c in contacts}
    predicate = lambda c: not c.IsRemoved() and c.contact_source == contact_source
    existing_contacts = self._validator.QueryModelObjects(Contact, predicate=predicate)
    for existing_contact in existing_contacts:
      if existing_contact.contact_id not in fetched_contact_ids:
        # Create a 'removed' contact and delete the original one.
        self._validator.ValidateCreateContact(user_id,
                                              None,
                                              util._TEST_TIME,
                                              existing_contact.contact_source,
                                              contact_id=existing_contact.contact_id,
                                              labels=[Contact.REMOVED])
        self._validator.ValidateDeleteDBObject(Contact, existing_contact.GetKey())

    return contacts

  def _ValidateOneContact(self, user_id, identities_properties, contact_source, name, given_name, family_name, rank=None):
    """Validates that the specified contact has been created, and any previous contacts with
    same identity have been deleted. Returns the contact that should exist.
    """
    contact_dict = Contact.CreateContactDict(user_id,
                                             identities_properties,
                                             util._TEST_TIME,
                                             contact_source,
                                             name=name,
                                             given_name=given_name,
                                             family_name=family_name,
                                             rank=rank)

    # Find any old contact with same identity.
    predicate = lambda contact: contact_dict['contact_id'] == contact.contact_id
    old_contacts = self._validator.QueryModelObjects(Contact, predicate=predicate)
    if len(old_contacts) == 0 or old_contacts[0].IsRemoved():
      if len(old_contacts) > 0:
        # Validate that old contact has been deleted.
        self._validator.ValidateDeleteDBObject(Contact, old_contacts[0].GetKey())
      # Validate that new create contact has been created.
      contact_dict =  Contact.CreateContactDict(**contact_dict)
      return self._validator.ValidateCreateDBObject(Contact, **contact_dict)

    return old_contacts[0]

  def _TestFetchContacts(self, identity_key, user_id, people_dict, photos_dict=None):
    """Runs the fetch contacts operation and validates that it creates, updates, and deletes the
    expected objects. Returns the list of contacts that should have been created/updated.
    """
    self._FetchContacts(identity_key, user_id, people_dict, photos_dict)

    # Validate all contacts that should have been created.
    contacts = self._ValidateContacts(identity_key, user_id, people_dict)

    # Validate that last_fetch was set in identity.
    self._validator.ValidateUpdateDBObject(Identity, key=identity_key, last_fetch=util._TEST_TIME)

    # Increment time so that subsequent contacts will use later time.
    util._TEST_TIME += 1

    return contacts
