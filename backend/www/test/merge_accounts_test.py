# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Tests for merge accounts operation.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import mock

from copy import deepcopy
from viewfinder.backend.base import message, util
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.db_client import DBKey
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.merge_accounts_op import MergeAccountsOperation
from viewfinder.backend.services.email_mgr import TestEmailManager
from viewfinder.backend.www.test import auth_test, service_base_test


class MergeAccountsTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(MergeAccountsTestCase, self).setUp()

    self._CreateSimpleTestAssets()

    # Create a viewpoint for user #2 and one for user #3.
    self._vp_id, self._ep_id = self._ShareSimpleTestAssets([self._user2.user_id])
    self._vp_id2, self._ep_id2 = self._ShareSimpleTestAssets([self._user3.user_id])

    # Create confirmed cookies.
    self._confirmed_cookie2 = self._tester.GetSecureUserCookie(user_id=self._user2.user_id,
                                                               device_id=self._device_ids[1],
                                                               user_name=self._user2.name,
                                                               confirm_time=util._TEST_TIME)

    self._confirmed_cookie3 = self._tester.GetSecureUserCookie(user_id=self._user3.user_id,
                                                               device_id=self._device_ids[2],
                                                               user_name=self._user3.name,
                                                               confirm_time=util._TEST_TIME)

  def testMergeWithCookie(self):
    """Test basic merge using source cookie."""
    # Merge user #3 into user #2.
    self._tester.MergeAccounts(self._cookie2, source_user_cookie=self._confirmed_cookie3)
    self.assertEqual(len(self._tester.QueryFollowed(self._cookie2)['viewpoints']), 3)

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie3)

  def testMergeWithIdentity(self):
    """Test basic merge using source identity."""
    # Merge user #3 into user #2.
    source_identity_dict = self._TestGenerateMergeToken('Email:%s' % self._user3.email,
                                                        user_cookie=self._cookie2,
                                                        error_if_linked=False)
    self._tester.MergeAccounts(self._cookie2, source_identity_dict=source_identity_dict)
    self.assertEqual(len(self._tester.QueryFollowed(self._cookie2)['viewpoints']), 3)

    # Link a previously unlinked email to user #2.
    source_identity_dict = self._TestGenerateMergeToken('Email:another-email@emailscrubbed.com',
                                                        user_cookie=self._cookie2,
                                                        error_if_linked=True)
    self._tester.MergeAccounts(self._cookie2, source_identity_dict=source_identity_dict)
    self.assertEqual(self._tester.ListIdentities(self._cookie2),
                     ['Email:another-email@emailscrubbed.com', 'Email:user3@emailscrubbed.com', 'FacebookGraph:2'])

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie3)

  @mock.patch.object(MergeAccountsOperation, '_FOLLOWER_LIMIT', 2)
  def testMergeMultipleViewpoints(self):
    """Test merge with multiple source viewpoints."""
    self._ShareSimpleTestAssets([self._user3.user_id])
    self._ShareSimpleTestAssets([self._user3.user_id])
    self._ShareSimpleTestAssets([self._user3.user_id])

    # Merge user #3 into user #2.
    self._tester.MergeAccounts(self._cookie2, source_user_cookie=self._confirmed_cookie3)
    self.assertEqual(len(self._tester.QueryFollowed(self._cookie2)['viewpoints']), 6)

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie3)

  def testMergeOverlappingViewpoints(self):
    """Test merge where some source viewpoints are already followed by the target user."""
    self._ShareSimpleTestAssets([self._user2.user_id, self._user3.user_id])
    self._ShareSimpleTestAssets([self._user2.user_id, self._user3.user_id])

    # Merge user #2 into user #3.
    self._tester.MergeAccounts(self._cookie3, source_user_cookie=self._confirmed_cookie2)
    self.assertEqual(len(self._tester.QueryFollowed(self._cookie3)['viewpoints']), 5)

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie2)

  def testMergeRemovedSourceViewpoint(self):
    """Test merge where a source viewpoint has been removed."""
    vp_id, ep_id = self._ShareSimpleTestAssets([self._user2.user_id])
    self._tester.RemoveViewpoint(self._cookie2, vp_id)

    # Merge user #2 into user #3.
    self._tester.MergeAccounts(self._cookie3, source_user_cookie=self._confirmed_cookie2)
    self.assertEqual(len(self._tester.QueryFollowed(self._cookie3)['viewpoints']), 3)

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie2)

  def testMergeRemovedTargetViewpoint(self):
    """Test merge where the target user has removed the target viewpoint."""
    # ------------------------------
    # RemoveViewpoint case (revivable).
    # ------------------------------
    vp_id, _ = self._ShareSimpleTestAssets([self._user2.user_id, self._user3.user_id])
    self._tester.RemoveViewpoint(self._cookie3, vp_id)

    self._tester.MergeAccounts(self._cookie3, source_user_cookie=self._confirmed_cookie2)
    response_dict = self._tester.QueryFollowed(self._cookie3)
    vp_dict = util.GetSingleListItem([vp_dict for vp_dict in response_dict['viewpoints']
                                      if vp_dict['viewpoint_id'] == vp_id])
    self.assertIn(Follower.REMOVED, vp_dict['labels'])

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie2)

    # ------------------------------
    # RemoveFollowers case (un-revivable).
    # ------------------------------
    vp_id, _ = self._ShareSimpleTestAssets([self._user3.user_id])
    self._tester.RemoveFollowers(self._cookie, vp_id, [self._user.user_id])

    self._tester.MergeAccounts(self._cookie, source_user_cookie=self._confirmed_cookie3)
    response_dict = self._tester.QueryFollowed(self._cookie)
    vp_dict = util.GetSingleListItem([vp_dict for vp_dict in response_dict['viewpoints']
                                      if vp_dict['viewpoint_id'] == vp_id])
    self.assertIn(Follower.REMOVED, vp_dict['labels'])
    self.assertIn(Follower.UNREVIVABLE, vp_dict['labels'])

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie3)

  def testMergeOldFollower(self):
    """Bug 468: Test merge with follower that never had adding_user_id set."""
    # Simulate followers in prod db that never had adding_user_id set.
    self._UpdateOrAllocateDBObject(Follower, user_id=self._user3.user_id, viewpoint_id=self._vp_id2,
                                   adding_user_id=None)

    # Merge user #3 into user #2.
    self._tester.MergeAccounts(self._cookie2, source_user_cookie=self._confirmed_cookie3)
    follower = self._RunAsync(Follower.Query, self._client, self._user2.user_id, self._vp_id2, None)
    self.assertIsNone(follower.adding_user_id)

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie3)

  def testRemovedAddingUser(self):
    """Test merge with follower whose adding_user_id has been removed."""
    # Share to second viewpoint.
    vp_id, _ = self._tester.ShareNew(self._cookie2, [(self._ep_id, self._photo_ids)], [self._user3.user_id])

    # Now remove user #1 from first viewpoint.
    self._tester.RemoveFollowers(self._cookie, self._vp_id, [self._user.user_id])

    # Merge user #2 into user #3.
    self._tester.MergeAccounts(self._cookie3, source_user_cookie=self._confirmed_cookie2)

    response_dict = self._tester.QueryViewpoints(self._cookie3, [self._tester.CreateViewpointSelection(self._vp_id)])
    self.assertEqual(response_dict['viewpoints'][0]['followers'],
                     [{'follower_id': 1, 'labels': ['removed', 'unrevivable'], 'follower_timestamp': util._TEST_TIME},
                      {'follower_id': 2, 'adding_user_id': 1, 'follower_timestamp': util._TEST_TIME},
                      {'follower_id': 3, 'adding_user_id': 1, 'follower_timestamp': util._TEST_TIME}])

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie2)

  def testLinkUnboundIdentity(self):
    """Link an identity that exists, but is not bound to any user."""
    identity_key = 'Email:new.user@emailscrubbed.com'
    self._UpdateOrAllocateDBObject(Identity, key=identity_key)
    source_identity_dict = self._TestGenerateMergeToken(identity_key, user_cookie=self._cookie3)
    self._tester.MergeAccounts(self._cookie3, source_identity_dict=source_identity_dict)

  def testLinkAfterUnlink(self):
    """Test linking an identity after it was unlinked from another user."""
    # Link a phone to user #3.
    identity_key = 'Phone:+12345678901'
    source_identity_dict = self._TestGenerateMergeToken(identity_key, user_cookie=self._cookie3)
    self._tester.MergeAccounts(self._cookie3, source_identity_dict=source_identity_dict)

    # Unlink the phone.
    self._tester.UnlinkIdentity(self._cookie3, identity_key)

    # Now link it to user #1.
    source_identity_dict = self._TestGenerateMergeToken(identity_key, user_cookie=self._cookie)
    self._tester.MergeAccounts(self._cookie, source_identity_dict=source_identity_dict)

    self.assertEqual(self._tester.ListIdentities(self._cookie),
                     [u'Email:user1@emailscrubbed.com', u'Phone:+12345678901'])

  def testLinkWithContacts(self):
    """Test link of an identity which another user has as a contact."""
    # Create contact for user #1
    identity_key = 'Email:foo@emailscrubbed.com'
    contact_dict = Contact.CreateContactDict(self._user.user_id,
                                             [(identity_key, None)],
                                             util._TEST_TIME,
                                             Contact.GMAIL)
    self._UpdateOrAllocateDBObject(Contact, **contact_dict)

    # Link the identity to user #2 and verify that user #1 is notified.
    source_identity_dict = self._TestGenerateMergeToken(identity_key, user_cookie=self._cookie2)
    self._tester.MergeAccounts(self._cookie2, source_identity_dict=source_identity_dict)

    response_dict = self._tester.QueryNotifications(self._cookie, 1, scan_forward=False)
    self.assertEqual(response_dict['notifications'][0]['name'], 'link identity')

  def testMergeToken(self):
    """Test the /merge_token auth API."""
    # ------------------------------
    # Generate email as a mobile client.
    # ------------------------------
    source_identity_dict = self._TestGenerateMergeToken('Email:mobile-user@bar.com', user_cookie=self._cookie2)
    email = TestEmailManager.Instance().emails['mobile-user@bar.com'][0]
    self.assertEqual(email['toname'], self._user2.name)
    self.assertIn('Hello %s' % self._user2.name, email['html'])
    self.assertIn('Hello %s' % self._user2.name, email['text'])
    self.assertIn('link mobile-user@bar.com', email['html'])
    self.assertIn(source_identity_dict['access_token'], email['html'])
    self.assertIn(source_identity_dict['access_token'], email['text'])

    # ------------------------------
    # Generate email as a web client.
    # ------------------------------
    source_identity_dict = self._TestGenerateMergeToken('Email:web-user@bar.com', user_cookie=self._cookie3)
    email = TestEmailManager.Instance().emails['web-user@bar.com'][0]
    self.assertIn(source_identity_dict['access_token'], email['html'])
    self.assertIn(source_identity_dict['access_token'], email['text'])

    # ------------------------------
    # ERROR: Use non-canonical identity.
    # ------------------------------
    self.assertRaisesHttpError(400, self._TestGenerateMergeToken, 'Phone:456-7890', user_cookie=self._cookie2)

    # ------------------------------
    # ERROR: Try to call without being logged in.
    # ------------------------------
    self.assertRaisesHttpError(403, self._TestGenerateMergeToken, 'Email:foo@bar.com', user_cookie=None)

    # ------------------------------
    # ERROR: Try to use unsupported identity type.
    # ------------------------------
    self.assertRaisesHttpError(400,
                               self._TestGenerateMergeToken,
                               'Facebook:1234',
                               user_cookie=self._cookie2)

    # ------------------------------
    # ERROR: Raise error if an identity is already linked to a user when "error_if_linked" is true.
    # ------------------------------
    self.assertRaisesHttpError(403,
                               self._TestGenerateMergeToken,
                               'Email:%s' % self._user3.email,
                               user_cookie=self._cookie,
                               error_if_linked=True)

    # ------------------------------
    # ERROR: Try to use merge token with /verify/viewfinder. 
    # ------------------------------
    source_identity_dict = self._TestGenerateMergeToken('Email:web-user@bar.com', user_cookie=self._cookie3)
    verify_url = self._tester.GetUrl('/verify/viewfinder')
    request_dict = {'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION,
                                'synchronous': True},
                    'identity': source_identity_dict['identity'],
                    'access_token': source_identity_dict['access_token']}
    self.assertRaisesHttpError(400,
                               auth_test._SendAuthRequest,
                               self._tester,
                               verify_url,
                               'POST',
                               request_dict=request_dict)
    self._validator.ValidateUpdateDBObject(Identity, key=source_identity_dict['identity'], expires=0)

  def testAccessToken(self):
    """Use valid and invalid access tokens with merge_accounts."""
    # ------------------------------
    # ERROR: Try to use invalid token.
    # ------------------------------
    source_identity_dict = self._TestGenerateMergeToken('Email:foo@bar.com', user_cookie=self._cookie3)
    bad_source_identity_dict = deepcopy(source_identity_dict)
    bad_source_identity_dict['access_token'] = 'unknown'
    self.assertRaisesHttpError(403,
                               self._tester.MergeAccounts,
                               self._cookie3,
                               source_identity_dict=bad_source_identity_dict)

    # ------------------------------
    # Use valid token, which should succeed.
    # ------------------------------
    self._tester.MergeAccounts(self._cookie3, source_identity_dict=source_identity_dict)

    # ------------------------------
    # Use valid token, which should fail, since tokens are single-use.
    # ------------------------------
    self.assertRaisesHttpError(403,
                               self._tester.MergeAccounts,
                               self._cookie3,
                               source_identity_dict=source_identity_dict)

  def testMergeSkipSystem(self):
    """Test that merge will skip system viewpoints."""
    # Prepare system viewpoint.
    self._MakeSystemViewpoint(self._vp_id2)

    # Merge user #3 into user #2.
    self._tester.MergeAccounts(self._cookie2, source_user_cookie=self._confirmed_cookie3)

    # Ensure that user #2 was not added as a follower to the system viewpoint.
    follower = self._RunAsync(Follower.Query, self._client, self._user2.user_id, self._vp_id2, None, must_exist=False)
    self.assertIsNone(follower)

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie3)

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testMergeIdempotency(self):
    """Force op failure in order to test idempotency."""
    # Do not use tester framework, as notifications are not idempotent (by-design), and unlike other
    # operations, the MergeAccountsOperation interleaves notifications with db mutations. 
    self._validate = False

    request_dict = {'activity': self._tester.CreateActivityDict(self._cookie2),
                    'source_user_cookie': self._confirmed_cookie3}
    self._tester.SendRequest('merge_accounts', self._cookie2, request_dict)

    actual_dict = self._tester.SendRequest('query_followed', self._cookie2, {})
    self.assertEqual(len(actual_dict['viewpoints']), 3)

    actual_dict = self._tester.SendRequest('list_identities', self._cookie2, {})
    self.assertEqual(len(actual_dict['identities']), 2)

    self.assertRaisesHttpError(401, self._tester.SendRequest, 'list_identities', self._cookie3, {})

  @mock.patch.object(Operation, 'FAILPOINTS_ENABLED', True)
  def testLinkIdempotency(self):
    """Force op failure in order to test idempotency."""
    source_identity_dict = self._TestGenerateMergeToken('Email:test@test.com', user_cookie=self._cookie2)
    self._tester.MergeAccounts(self._cookie2, source_identity_dict=source_identity_dict)

  def testNoMergeSource(self):
    """ERROR: Try to merge without a user cookie or identity source."""
    self.assertRaisesHttpError(400,
                               self._tester.MergeAccounts,
                               self._confirmed_cookie2)

  def testMergeIntoSelf(self):
    """ERROR: Try to merge account into itself."""
    self.assertRaisesHttpError(400,
                               self._tester.MergeAccounts,
                               self._confirmed_cookie2,
                               source_user_cookie=self._confirmed_cookie2)

  def testBadCookie(self):
    """ERROR: Pass bad source user cookie."""
    self.assertRaisesHttpError(403, self._tester.MergeAccounts, self._cookie, source_user_cookie='BADF00D')

  def testMergeTerminatedAccount(self):
    """ERROR: Try to merge a terminated user account."""
    self._tester.TerminateAccount(self._confirmed_cookie3)
    self.assertRaisesHttpError(400,
                               self._tester.MergeAccounts,
                               self._cookie,
                               source_user_cookie=self._confirmed_cookie3)

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie3)

  def testMergeProspectiveUser(self):
    """Merge from a prospective user account."""
    prospective_user, vp_id, ep_id = self._CreateProspectiveUser()

    # ------------------------------
    # Merge using confirmed cookie.
    # ------------------------------
    prospective_cookie = self._tester.GetSecureUserCookie(user_id=prospective_user.user_id,
                                                          device_id=prospective_user.webapp_dev_id,
                                                          user_name=None,
                                                          viewpoint_id=vp_id,
                                                          confirm_time=util._TEST_TIME)
    self._tester.MergeAccounts(self._cookie, source_user_cookie=prospective_cookie)

    # ------------------------------
    # ERROR: Try to merge using unconfirmed cookie.
    # ------------------------------
    prospective_cookie = self._tester.GetSecureUserCookie(user_id=prospective_user.user_id,
                                                          device_id=prospective_user.webapp_dev_id,
                                                          user_name=None,
                                                          viewpoint_id=vp_id)
    self.assertRaisesHttpError(403, self._tester.MergeAccounts, self._cookie, source_user_cookie=prospective_cookie)

  def testMergeWithContacts(self):
    """Test merge in which another user has the source user as a contact."""
    # Create user #1 contacts for user #2 and user #3.
    exp_contacts = []
    for user, identity in zip(self._users[1:], self._identities[1:]):
      contact_dict = Contact.CreateContactDict(self._user.user_id,
                                               [(identity.key, None)],
                                               util._TEST_TIME,
                                               Contact.GMAIL)
      exp_contacts.append({'contact_id': contact_dict['contact_id'],
                           'contact_source': contact_dict['contact_source'],
                           'identities': [{'identity': identity.key, 'user_id': 3}]})
      self._UpdateOrAllocateDBObject(Contact, **contact_dict)

    # Merge user #2 into user #3. Contact's user id should be updated.
    self._tester.MergeAccounts(self._cookie3, source_user_cookie=self._confirmed_cookie2)
    self.assertEqual(sorted(self._tester.QueryContacts(self._cookie)['contacts']), sorted(exp_contacts))

    # Remove cookie so that base class won't try to validate its user's assets (and fail).
    self._cookies.remove(self._cookie2)

  def _TestGenerateMergeToken(self, identity_key, user_cookie, error_if_linked=None):
    """Invokes the merge_token auth API that triggers the email of a Viewfinder access token.
    Validates that an identity was created. Returns a source_identity_dict that can be passed
    directly to merge_accounts.
    """
    url = self._tester.GetUrl('/merge_token/viewfinder')
    request_dict = {'headers': {'version': message.MAX_SUPPORTED_MESSAGE_VERSION,
                                'synchronous': True},
                    'identity': identity_key}
    util.SetIfNotNone(request_dict, 'error_if_linked', error_if_linked)

    auth_test._SendAuthRequest(self._tester, url, 'POST', user_cookie=user_cookie, request_dict=request_dict)
    identity = self._RunAsync(Identity.Query, self._client, identity_key, None)

    # Validate the identity.
    self._validator.ValidateUpdateDBObject(Identity,
                                           key=identity_key,
                                           authority='Viewfinder',
                                           user_id=identity.user_id,
                                           access_token=identity.access_token,
                                           expires=identity.expires)
    return {'identity': identity.key, 'access_token': identity.access_token}


def _TestMergeAccounts(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test merge_accounts service API call."""
  validator = tester.validator
  target_user_id, device_id = tester.GetIdsFromCookie(user_cookie)

  # Send merge_accounts request.
  actual_dict = tester.SendRequest('merge_accounts', user_cookie, request_dict)
  op_dict = tester._DeriveNotificationOpDict(target_user_id, device_id, request_dict)

  source_user_cookie = request_dict.get('source_user_cookie')
  if source_user_cookie is not None:
    source_user_id, _ = tester.GetIdsFromCookie(source_user_cookie)
  else:
    source_identity_key = request_dict['source_identity']['identity']
    identity = validator.GetModelObject(Identity, source_identity_key)
    source_user_id = identity.user_id

  # If source user account exists, then validate merge.
  if source_user_id is not None:
    # Validate merge users case.

    # Validate that target user is added to all viewpoints followed by the source user. 
    for source_follower in validator.QueryModelObjects(Follower, predicate=lambda f: f.user_id == source_user_id):
      viewpoint_id = source_follower.viewpoint_id

      # Skip removed followers.
      if source_follower.IsRemoved():
        continue

      # Skip default and system viewpoints.
      viewpoint = validator.GetModelObject(Viewpoint, DBKey(viewpoint_id, None))
      if viewpoint.IsDefault() or viewpoint.IsSystem():
        continue

      # Skip viewpoints that target already follows.
      db_key = DBKey(target_user_id, viewpoint_id)
      target_follower = validator.GetModelObject(Follower, db_key, must_exist=False)
      if target_follower is not None:
        continue

      validator.ValidateFollower(user_id=target_user_id,
                                 viewpoint_id=viewpoint_id,
                                 timestamp=op_dict['op_timestamp'],
                                 labels=[Follower.CONTRIBUTE],
                                 last_updated=op_dict['op_timestamp'],
                                 adding_user_id=source_follower.adding_user_id,
                                 viewed_seq=None)

      # Validate activity and notifications for the viewpoint merge.
      activity_id = request_dict['activity']['activity_id']
      truncated_ts, device_id, (client_id, server_id) = Activity.DeconstructActivityId(activity_id)
      activity_id = Activity.ConstructActivityId(truncated_ts, device_id, (client_id, viewpoint_id))
      activity_dict = {'name': 'merge_accounts',
                       'activity_id': activity_id,
                       'timestamp': request_dict['activity']['timestamp'],
                       'target_user_id': target_user_id,
                       'source_user_id': source_user_id}

      def _GetInvalidate(follower_id):
        if follower_id == target_user_id:
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

    # Validate that all identities have been moved from the source to the target user.
    for identity in validator.QueryModelObjects(Identity, predicate=lambda i: i.user_id == source_user_id):
      # Validate Identity objects.
      validator.ValidateUpdateDBObject(Identity, key=identity.key, user_id=target_user_id, expires=0)

      # Validate Contact objects.
      validator.ValidateRewriteContacts(identity.key, op_dict)

      # Validate contact notifications.
      validator.ValidateContactNotifications('merge identities', identity.key, op_dict)

    # Validate target user notification.
    validator.ValidateUserNotification('merge users', target_user_id, op_dict)

    # Validate the account termination.
    validator.ValidateTerminateAccount(source_user_id, op_dict, merged_with=target_user_id)
  else:
    # Validate link identity case.

    # Validate Identity object.
    validator.ValidateUpdateDBObject(Identity, key=source_identity_key, user_id=target_user_id, expires=0)

    # Validate Contact objects.
    validator.ValidateRewriteContacts(source_identity_key, op_dict)

    # Validate contact notifications.
    validator.ValidateContactNotifications('link identity', identity.key, op_dict)

    # Validate target user notification.
    validator.ValidateUserNotification('link user', target_user_id, op_dict)

  tester._CompareResponseDicts('merge_accounts', target_user_id, request_dict, {}, actual_dict)
  return actual_dict
