# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test adding followers to an existing viewpoint.
"""

__author__ = ['andy@emailscrubbed.com (Andy Kimball)']

import mock

from copy import deepcopy
from functools import partial
from viewfinder.backend.base import constants, util
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.accounting import Accounting
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.services.email_mgr import EmailManager, TestEmailManager
from viewfinder.backend.www.test import service_base_test

class AddFollowersTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(AddFollowersTestCase, self).setUp()
    self._CreateSimpleTestAssets()
    self._CreateSimpleContacts()

    # Create a number of users.
    self._extra_users = []
    self._extra_device_ids = []
    for i in xrange(3):
      user, _ = self._tester.RegisterGoogleUser(user_dict={'name': 'Extra User #%d' % (i + 1),
                                                           'email': 'extra.user%d@emailscrubbed.com' % (i + 1),
                                                           'verified_email': True})
      self._extra_users.append(user)
      self._extra_device_ids.append(user.webapp_dev_id)

    # Create new viewpoint to test against.
    self._vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                                [(self._episode_id2, self._photo_ids2)],
                                                [self._user2.user_id],
                                                **self._CreateViewpointDict(self._cookie))

  def testAddFollower(self):
    """Add single follower to viewpoint."""
    self._tester.AddFollowers(self._cookie, self._vp_id, ['Email:extra.user1@emailscrubbed.com'])

  def testAddMultipleFollowers(self):
    """Add multiple followers to viewpoint."""
    self._tester.AddFollowers(self._cookie, self._user.private_vp_id,
                              ['Email:extra.user1@emailscrubbed.com',
                               'Email:extra.user2@emailscrubbed.com',
                               {'user_id': self._extra_users[0].user_id}])

  def testDuplicateFollowers(self):
    """Add same followers multiple times."""
    self._tester.AddFollowers(self._cookie, self._vp_id,
                              ['Email:extra.user1@emailscrubbed.com',
                               'Email:extra.user1@emailscrubbed.com',
                               'Email:extra.user2@emailscrubbed.com'])

    util._TEST_TIME += 100
    self._tester.AddFollowers(self._cookie, self._vp_id,
                              ['Email:extra.user1@emailscrubbed.com',
                               'Email:extra.user1@emailscrubbed.com',
                               'Email:extra.user2@emailscrubbed.com'])

    util._TEST_TIME += 100
    self._tester.AddFollowers(self._cookie2, self._vp_id,
                              ['Email:extra.user1@emailscrubbed.com',
                               'Email:extra.user1@emailscrubbed.com',
                               'Email:extra.user2@emailscrubbed.com'])

  def testAddAfterRemoveFollower(self):
    """Add a follower after having removed it."""
    # Mute it first -- when re-added it should no longer be muted.
    self._tester.UpdateFollower(self._cookie2, self._vp_id, labels=[Follower.CONTRIBUTE, Follower.MUTED])
    self._tester.RemoveFollowers(self._cookie, self._vp_id, [self._user2.user_id])
    self._tester.AddFollowers(self._cookie, self._vp_id, [self._user2.user_id])
    response_dict = self._tester.QueryFollowed(self._cookie2)
    self.assertEqual(response_dict['viewpoints'][0]['labels'], ['contribute'])

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testIdempotency(self):
    """Force op failure in order to test idempotency."""
    self._tester.RemoveViewpoint(self._cookie2, self._vp_id)
    self._tester.AddFollowers(self._cookie, self._vp_id,
                              ['Local:identity1',
                               {'identity': 'Local:identity2',
                                'name': 'Andy Kimball'},
                               'Email:extra.user1@emailscrubbed.com',
                               self._extra_users[1].user_id])

  def testNonCanonicalId(self):
    """ERROR: Try to use non-canonical contact identities."""
    self.assertRaisesHttpError(400,
                               self._tester.AddFollowers,
                               self._cookie,
                               self._user.private_vp_id,
                               ['Email:EXTRA.USER1@emailscrubbed.com'])

    self.assertRaisesHttpError(400,
                               self._tester.AddFollowers,
                               self._cookie,
                               self._user.private_vp_id,
                               ['Phone:123-456-7890'])

    self.assertRaisesHttpError(400,
                               self._tester.AddFollowers,
                               self._cookie,
                               self._user.private_vp_id,
                               ['Phone:1234567890'])

  def testEmptyFollowers(self):
    """Add empty set of followers."""
    self._tester.AddFollowers(self._cookie, self._user.private_vp_id, [])

  def testNotFollower(self):
    """ERROR: Try to add follower to viewpoint that is not followed."""
    self.assertRaisesHttpError(403, self._tester.AddFollowers, self._cookie3, self._vp_id,
                               ['Email:extra.user1@emailscrubbed.com'])

  def testNotContributor(self):
    """ERROR: Try to add follower to viewpoint without CONTRIBUTOR rights."""
    # We're manually creating a follower entry. the real DB will not have it since the op
    # fails, and the accounting entry will not be computed. Skip validation.
    self._skip_validation_for.append('Accounting')

    self._UpdateOrAllocateDBObject(Follower, viewpoint_id=self._vp_id,
                                   user_id=self._user3.user_id, viewed_seq=0)
    self.assertRaisesHttpError(403, self._tester.AddFollowers, self._cookie3, self._vp_id,
                               ['Email:extra.user1@emailscrubbed.com'])

  def testNotContributorAndProspectiveAdd(self):
    """ERROR: Try to add followers to viewpoint without CONTRIBUTOR rights."""
    # We're manually creating a follower entry. the real DB will not have it since the op
    # fails, and the accounting entry will not be computed. Skip validation.
    # Also add some prospective users to ensure that we don't mutate the DB before aborting.
    self._skip_validation_for.append('Accounting')

    self._UpdateOrAllocateDBObject(Follower, viewpoint_id=self._vp_id,
                                   user_id=self._user3.user_id, viewed_seq=0)
    self.assertRaisesHttpError(403, self._tester.AddFollowers, self._cookie3, self._vp_id,
                               [{'identity': 'Local:identity2',
                                 'name': 'Andy Kimball'},
                                 'Email:extra.user1@emailscrubbed.com',
                                {'identity': 'Phone:+60321345678',
                                 'name': 'Someone'}])

  def testIdentitySchemes(self):
    """Test add followers with various identity schemes."""
    self._tester.AddFollowers(self._cookie,
                              self._user.private_vp_id,
                              ['Local:identity2',
                               'Email:extra.user1@emailscrubbed.com',
                               'Phone:+14251234567',
                               'FacebookGraph:123',
                               'VF:456'])

  def testProspectiveAdd(self):
    """Verify that an unrecognized contact will result in the creation
    of a prospective user, which will then be added as a follower.
    """
    self._tester.AddFollowers(self._cookie, self._user.private_vp_id,
                              ['Local:identity1'])

  def testProspectiveAddIdentities(self):
    """Verify adding each kind of identity as a prospective user."""
    self._tester.AddFollowers(self._cookie, self._user.private_vp_id,
                              ['Local:identity1',
                               {'identity': 'Email:andy@emailscrubbed.com',
                                'name': 'Andy Kimball'},
                               'FacebookGraph:123',
                               'Phone:+442083661177'])

  def testMultipleProspectiveAdds(self):
    """Verify that multiple unrecognized contacts will result in the
    creation of prospective users.
    """
    self._tester.AddFollowers(self._cookie, self._user.private_vp_id,
                              ['Local:identity1',
                               {'identity': 'Local:identity2',
                                'name': 'Andy Kimball'},
                               'Email:andy@emailscrubbed.com',
                               {'identity': 'Phone:+14161234567',
                                'name': 'Someone'}])

  def testMixedProspectiveAdds(self):
    """Verify that unrecognized contacts mixed with existing users can
    be added as followers.
    """
    self._tester.AddFollowers(self._cookie, self._user.private_vp_id,
                              ['Local:identity1',
                               {'identity': 'Local:identity2',
                                'name': 'Andy Kimball'},
                               'Email:extra.user1@emailscrubbed.com',
                               self._extra_users[1].user_id])

  def testSequenceProspectiveAdds(self):
    """Add prospective users in sequence."""
    # Share to prospective user + non-prospective user.
    self._tester.AddFollowers(self._cookie, self._vp_id,
                              ['Email:test@test.com', self._user3.user_id])
    self.assertEqual(len(TestEmailManager.Instance().emails['user3@emailscrubbed.com']), 1)

    # Share to prospective user again, but not to non-prospective user (no email should be sent 2nd time).
    self._tester.AddFollowers(self._cookie, self._vp_id,
                              ['Email:test@test.com'])
    self.assertEqual(len(TestEmailManager.Instance().emails['user3@emailscrubbed.com']), 1)

  def testInvalidUserId(self):
    """ERROR: Try to add contact with invalid user id."""
    self.assertRaisesHttpError(400, self._tester.AddFollowers,
                               self._cookie,
                               self._user.private_vp_id,
                               [1000])

  def testUnknownIdentityFormat(self):
    """ERROR: Try to add contact with unknown identity format."""
    self.assertRaisesHttpError(400, self._tester.AddFollowers,
                               self._cookie,
                               self._user.private_vp_id,
                               ['Unknown:foo'])

    self.assertRaisesHttpError(400, self._tester.AddFollowers,
                               self._cookie,
                               self._user.private_vp_id,
                               ['Phone:123-456-7890'])

    self.assertRaisesHttpError(400, self._tester.AddFollowers,
                               self._cookie,
                               self._user.private_vp_id,
                               ['Phone:123'])

  def testAddsAcrossDays(self):
    """Add a follower on day 2, add another on day 3, then third on day 1."""
    self._tester.AddFollowers(self._cookie, self._vp_id,
                              [{'identity': 'Email:user1@emailscrubbed.com'}])

    # Add 24 hours to timestamp.
    act_dict = self._tester.CreateActivityDict(self._cookie)
    act_dict['timestamp'] += constants.SECONDS_PER_DAY
    self._tester.AddFollowers(self._cookie, self._vp_id,
                              [{'identity': 'Email:user1@emailscrubbed.com'},
                               {'user_id': self._extra_users[0].user_id}],
                              act_dict=act_dict)

    # Subtract 24 hours from timestamp.
    act_dict = self._tester.CreateActivityDict(self._cookie)
    act_dict['timestamp'] -= constants.SECONDS_PER_DAY
    self._tester.AddFollowers(self._cookie, self._vp_id,
                              [{'identity': 'Email:user1@emailscrubbed.com'},
                               {'user_id': self._extra_users[0].user_id},
                               {'user_id': self._extra_users[1].user_id}],
                              act_dict=act_dict)

  def testExceedAddFollowersLimit(self):
    """Try to exceed limit on number of followers on a viewpoint and observe that error is raised."""
    # Artificially lower limit on followers for test.
    with mock.patch.object(Viewpoint, 'MAX_FOLLOWERS', len(self._extra_users) + 1):
      # First, add (MAX_FOLLOWERS - 1) followers to the one follower that created the viewpoint.
      # This should succeed and result in MAX_FOLLOWERS followers on the viewpoint.
      contacts = [{'user_id': extra_user.user_id} for extra_user in self._extra_users]
      self._tester.AddFollowers(self._cookie, self._user.private_vp_id, contacts)

      # Now, add one more follower which should exceed the limit and cause an error to be raised.
      self.assertRaisesHttpError(403, self._tester.AddFollowers, self._cookie,
                                 self._user.private_vp_id, [{'user_id': self._user2.user_id}])

def _TestAddFollowers(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test add_followers
  service API call.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)
  viewpoint_id = request_dict['viewpoint_id']

  # Send add_followers request.
  actual_dict = tester.SendRequest('add_followers', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(user_id, device_id, request_dict)

  # Validate all prospective users were created.
  users = validator.ValidateCreateProspectiveUsers(op_dict, request_dict['contacts'])

  # Validate each of the new followers.
  added_followers = set()
  for user in users:
    follower_id = user.user_id
    follower = validator.GetModelObject(Follower, DBKey(follower_id, viewpoint_id), must_exist=False)
    if follower is None:
      added_followers.add(follower_id)
      validator.ValidateFollower(user_id=follower_id,
                                 viewpoint_id=viewpoint_id,
                                 timestamp=op_dict['op_timestamp'],
                                 labels=[Follower.CONTRIBUTE],
                                 last_updated=op_dict['op_timestamp'],
                                 adding_user_id=user_id,
                                 viewed_seq=0)
    elif follower.IsRemoved():
      # Revive removed follower.
      added_followers.add(follower_id)
      validator.ValidateFollower(user_id=follower_id,
                                 viewpoint_id=viewpoint_id,
                                 labels=follower.labels.intersection(Follower.PERMISSION_LABELS),
                                 last_updated=op_dict['op_timestamp'],
                                 adding_user_id=user_id)

  # Validate activity and notifications for the add.
  activity_dict = {'name': 'add_followers',
                   'activity_id': request_dict['activity']['activity_id'],
                   'timestamp': request_dict['activity']['timestamp'],
                   'follower_ids': [user.user_id for user in users]}

  def _GetInvalidate(follower_id):
    if follower_id in added_followers:
      return validator.CreateViewpointInvalidation(viewpoint_id)
    else:
      return {'viewpoints': [{'viewpoint_id': viewpoint_id, 'get_followers': True}]}

  validator.ValidateFollowerNotifications(viewpoint_id,
                                          activity_dict,
                                          op_dict,
                                          _GetInvalidate)

  # Validate all followers are friends.
  all_followers = validator.QueryModelObjects(Follower, predicate=lambda f: f.viewpoint_id == viewpoint_id)
  validator.ValidateFriendsInGroup([f.user_id for f in all_followers])

  validator.ValidateViewpointAccounting(viewpoint_id)
  tester._CompareResponseDicts('add_followers', user_id, request_dict, {}, actual_dict)
  return actual_dict
