# -*- coding: utf-8 -*-
# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Base class for service request handler tests.

  ServiceBaseTestCase
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import logging
import mock
import shutil
import time
import tempfile

from collections import namedtuple
from copy import deepcopy
from tornado import httpclient, options, testing, web
from viewfinder.backend.base import secrets, util, environ
from viewfinder.backend.base.testing import BaseTestCase
from viewfinder.backend.db.client_log import CLIENT_LOG_CONTENT_TYPE
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.id_allocator import IdAllocator
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.user import User
from viewfinder.backend.db.versions import Version
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.db import db_client, local_client, vf_schema
from viewfinder.backend.db.test.db_validator import DBValidator
from viewfinder.backend.op.op_manager import OpManager
from viewfinder.backend.op.operation_map import DB_OPERATION_MAP
from viewfinder.backend.resources.resources_mgr import ResourcesManager
from viewfinder.backend.services.apns import APNS, TestService
from viewfinder.backend.services import email_mgr, sms_mgr
from viewfinder.backend.storage import file_object_store, object_store, server_log
from viewfinder.backend.www import auth, auth_viewfinder, basic_auth, server, uimodules
from viewfinder.backend.www.test.service_tester import ServiceTester


ClientLogRecord = namedtuple('ClientLogRecord', ['timestamp', 'client_id', 'contents'])


# TODO(spencer): use testing.AsyncHTTPSTestCase.
class ServiceBaseTestCase(BaseTestCase, testing.AsyncHTTPTestCase):
  """Initializes the test datastore and the viewfinder schema.
  """
  def setUp(self):
    if not hasattr(self, '_enable_xsrf'): self._enable_xsrf = True
    if not hasattr(self, '_url_host') or self._url_host is None: self._url_host = 'www.goviewfinder.com'
    super(ServiceBaseTestCase, self).setUp()
    # TODO(spencer): remove this when switched to AsyncHTTPSTestCase.
    basic_auth.BasicAuthHandler._HTTP_TEST_CASE = True
    db_client.DBClient.SetInstance(local_client.LocalClient(vf_schema.SCHEMA))
    self._client = db_client.DBClient.Instance()
    email_mgr.EmailManager.SetInstance(email_mgr.TestEmailManager())
    sms_mgr.SMSManager.SetInstance(sms_mgr.TestSMSManager())
    self._backup_dir = tempfile.mkdtemp()
    server_log.LogBatchPersistor.SetInstance(server_log.LogBatchPersistor(backup_dir=self._backup_dir))
    APNS.SetInstance('test', APNS(environment='test',
                                  feedback_handler=Device.FeedbackHandler(self._client)))
    self._apns = TestService.Instance()
    IdAllocator.ResetState()

    # Do not freeze new account creation during testing (dy default).
    options.options.freeze_new_accounts = False

    # Set deterministic testing timestamp used in place of time.time() in server code.
    util._TEST_TIME = time.time()

    # Create validator and create some users and devices for testing convenience.
    self._validator = DBValidator(self._client, self.stop, self.wait)
    self._tester = ServiceTester(self.get_url(''), self.http_client, self._validator,
                                 secrets.GetSecret('cookie_secret'), self.stop, self.wait)
    self._test_id = 1
    self._validate = True

    # Skip model_db validation for specified tables. Ignored if _validate==False.
    self._skip_validation_for = []

    self._RunAsync(vf_schema.SCHEMA.VerifyOrCreate, self._client)
    OpManager.SetInstance(OpManager(op_map=DB_OPERATION_MAP, client=self._client, scan_ops=True))

    # Ensure that test users are created.
    self._CreateTestUsers()

    # Remove limit of number of auth messages that can be sent to a particular identity key.
    auth_viewfinder.VerifyIdBaseHandler._MAX_MESSAGES_PER_MIN = 10000
    auth_viewfinder.VerifyIdBaseHandler._MAX_MESSAGES_PER_DAY = 10000

  def tearDown(self):
    # If validation is enabled, validate all viewpoint assets using the service API.
    # If the test failed, skip validation so we don't get extra redundant error reports
    # (The unittest framework reports errors in the main test and errors in tearDown separately)
    validate = self._validate and self._GetUnittestErrorCount() == self._unittest_error_count
    if validate:
      self._ValidateAssets()

    # Ensure that operations do not exist in the db.
    from viewfinder.backend.db.operation import Operation
    Operation.Scan(self._client, None, self.stop)
    ops, last_key = self.wait()
    if validate:
      self.assertTrue(len(ops) == 0, ops)
      self.assertTrue(last_key is None)

    # Cleanup all assets created during tests.
    self._tester.Cleanup(validate=validate, skip_validation_for=self._skip_validation_for)
    self._RunAsync(server_log.LogBatchPersistor.Instance().close)
    self._RunAsync(OpManager.Instance().Drain)

    shutil.rmtree(self._backup_dir)
    super(ServiceBaseTestCase, self).tearDown()
    self.assertIs(Operation.GetCurrent().operation_id, None)

  def run(self, result=None):
    self._unittest_result = result
    self._unittest_error_count = self._GetUnittestErrorCount()
    super(ServiceBaseTestCase, self).run(result)

  def _GetUnittestErrorCount(self):
    # Returns the number of errors the test framework has seen so far.  This is unfortunately
    # the best method available to detect in tearDown whether the test itself succeeded.
    return len(self._unittest_result.errors) + len(self._unittest_result.failures)

  def get_app(self):
    """Creates a web server which handles /service requests."""
    options.options.localdb = True
    options.options.fileobjstore = True
    options.options.localdb_dir = ''
    options.options.devbox = True
    options.options.domain = 'goviewfinder.com'
    options.options.short_domain = 'short.goviewfinder.com'

    # Init secrets with the unencrypted 'goviewfinder.com' domain.
    secrets.InitSecretsForTest()
    object_store.InitObjectStore(temporary=True)
    environ.ServerEnvironment.InitServerEnvironment()

    # Set up photo object store.
    obj_store = object_store.ObjectStore.GetInstance(object_store.ObjectStore.PHOTO)
    obj_store.SetUrlFmtString(self.get_url('/fileobjstore/photo/%s'))
    # Set up user logs object store.
    user_log_obj_store = object_store.ObjectStore.GetInstance(object_store.ObjectStore.USER_LOG)
    user_log_obj_store.SetUrlFmtString(self.get_url('/fileobjstore/user_log/%s'))
    # Set up user_zips object store.
    user_zips_obj_store = object_store.ObjectStore.GetInstance(object_store.ObjectStore.USER_ZIPS)
    user_zips_obj_store.SetUrlFmtString(self.get_url('/fileobjectstore/user_zips/%s'))

    settings = {
      'login_url': '/',
      'cookie_secret': secrets.GetSecret('cookie_secret'),
      'obj_store': obj_store,
      'server_version': ServiceTester.SERVER_VERSION,
      'google_client_id': secrets.GetSecret('google_client_id'),
      'google_client_secret': secrets.GetSecret('google_client_secret'),
      'google_client_mobile_id': secrets.GetSecret('google_client_mobile_id'),
      'google_client_mobile_secret': secrets.GetSecret('google_client_mobile_secret'),
      'facebook_api_key': secrets.GetSecret('facebook_api_key'),
      'facebook_secret': secrets.GetSecret('facebook_secret'),
      'template_path': ResourcesManager.Instance().template_path,
      'ui_modules': uimodules,
      'xsrf_cookies' : self._enable_xsrf,
      'static_path': ResourcesManager.Instance().static_path,
      }

    # Start with the production webapp handlers and add several for testing.
    webapp_handlers = deepcopy(server.WEBAPP_HANDLERS + server.ADMIN_HANDLERS)
    webapp_handlers.append((r'/fileobjstore/photo/(.*)',
                            file_object_store.FileObjectStoreHandler,
                            { 'storename': object_store.ObjectStore.PHOTO, 'contenttype': 'image/jpeg' }))
    webapp_handlers.append((r'/fileobjstore/user_log/(.*)',
                            file_object_store.FileObjectStoreHandler,
                            { 'storename': object_store.ObjectStore.USER_LOG, 'contenttype': 'text/plain' }))
    webapp_handlers.append((r'/fileobjstore/user_zips/(.*)',
                            file_object_store.FileObjectStoreHandler,
                            { 'storename': object_store.ObjectStore.USER_ZIPS, 'contenttype': 'application/zip' }))

    # Fake viewfinder handler - added explicitly because it is not part of WEBAPP_HANDLERS.
    webapp_handlers.append((r'/(link|login|register)/fakeviewfinder', auth_viewfinder.FakeAuthViewfinderHandler))

    application = web.Application(**settings)
    application.add_handlers(options.options.short_domain, server.SHORT_DOMAIN_HANDLERS)
    application.add_handlers('.*', webapp_handlers)
    return application

  def get_url(self, path):
    return 'http://%s:%d%s' % (self._url_host, self.get_http_port(), path)

  def assertRaisesHttpError(self, status_code, callableObj, *args, **kwargs):
    """Fail unless an exception of type HTTPError is raised by callableObj
    when invoked with arguments "args" and "kwargs", and unless the status
    code is equal to "status_code".
    """
    with self.assertRaises(httpclient.HTTPError) as cm:
      callableObj(*args, **kwargs)
    self.assertEqual(cm.exception.code, status_code)
    return cm.exception

  def _ValidateAssets(self):
    """"Query for all viewpoints, episodes, and photos in order to make
    sure they're configured and associated properly with one another.
    """
    logging.info('Validating all viewpoint assets from the vantage point of every test user...')
    for cookie in self._cookies:
      # Query all viewpoints followed by this user.
      self._tester.QueryFollowed(cookie)

      # Query all friends of this user.
      self._tester.QueryUsers(cookie, [u.user_id for u in self._users])

      # Query all viewpoints accessible to the user.
      vp_select_list = [self._tester.CreateViewpointSelection(vp.viewpoint_id)
                        for vp in self._validator.QueryModelObjects(Viewpoint)]
      self._tester.QueryViewpoints(cookie, vp_select_list)

      # Query all episodes accessible to the user.
      ep_select_list = [self._tester.CreateEpisodeSelection(ep.episode_id)
                        for ep in self._validator.QueryModelObjects(Episode)]
      self._tester.QueryEpisodes(cookie, ep_select_list)


  # =================================================================
  #
  # Helper methods that forward to the ServiceTester.
  #
  # =================================================================

  def _SendRequest(self, method, user_cookie, request_dict, version=None):
    """Pass through to ServiceTester.SendRequest."""
    return self._tester.SendRequest(method, user_cookie, request_dict, version=version)

  def _GetSecureUserCookie(self, user=None, device_id=None, confirm_time=None):
    """Pass through to ServiceTester.GetSecureUserCookie, but defaulting
    to user #1 and device #1 if not specified.
    """
    return self._tester.GetSecureUserCookie(user_id=self._user.user_id if not user else user.user_id,
                                            device_id=device_id or self._device_ids[0],
                                            user_name=self._user.name if not user else user.name,
                                            confirm_time=confirm_time)


  # =================================================================
  #
  # Helper methods to create test data used by derived tests.
  #
  # =================================================================

  def _CreateTestUsers(self):
    """Create several interesting users and devices to use in testing."""
    # List of test users.
    self._users = list()

    # List of main test user device.
    self._device_ids = list()

    # List of cookies containing user and main device.
    self._cookies = list()

    def _SaveUserInfo(user, device_id):
      self._users.append(user)
      device_id = user.webapp_dev_id if device_id is None else device_id
      self._device_ids.append(device_id)
      self._cookies.append(self._GetSecureUserCookie(user, device_id))

    # 1. Create default user (with web device and multiple mobile devices).
    user_dict = {'name': 'Viewfinder User #1', 'given_name': 'user1', 'email': 'user1@emailscrubbed.com'}
    device_dict = {'name': 'User #1 IPhone', 'push_token': '%sdevice1' % TestService.PREFIX}
    _SaveUserInfo(*self._tester.RegisterFakeViewfinderUser(user_dict, device_dict))
    self._user = self._users[0]

    # Create additional device for user #1.
    device_dict = {'name': 'User #1 IPad', 'push_token': '%sextra/device/1' % TestService.PREFIX}
    user, self._extra_device_id1 = self._tester.LoginFakeViewfinderUser(user_dict, device_dict)

    # Create additional device with no name and no push token for user #1.
    user, self._extra_device_id2 = self._tester.LoginFakeViewfinderUser(user_dict, {})

    # 2. Create Facebook user (with only mobile device).
    user_dict = {'name': 'Facebook User #2', 'email': 'user2@facebook.com',
                 'picture': {'data': {'url': 'http://facebook.com/user2'}}, 'id': 2}
    device_dict = {'name': 'User #2 IPhone', 'push_token': '%sdevice2' % TestService.PREFIX}
    _SaveUserInfo(*self._tester.RegisterFacebookUser(user_dict, device_dict))
    self._user2 = self._users[1]

    # Turn on email and SMS alerts in addition to APNS alerts for user #2.
    self._UpdateOrAllocateDBObject(AccountSettings,
                                   settings_id=AccountSettings.ConstructSettingsId(self._user2.user_id),
                                   group_name=AccountSettings.GROUP_NAME,
                                   user_id=self._user2.user_id,
                                   email_alerts=AccountSettings.EMAIL_ON_SHARE_NEW,
                                   sms_alerts=AccountSettings.SMS_ON_SHARE_NEW)

    # Set user #2's phone number.
    self._user2.phone = '+12121234567'
    self._UpdateOrAllocateDBObject(User, user_id=self._users[1].user_id, phone=self._user2.phone)

    # 3. Create user with minimal properties (with only web device).
    user_dict = {'name': 'Gmail User #3', 'email': 'user3@emailscrubbed.com', 'verified_email': True}
    _SaveUserInfo(*self._tester.RegisterGoogleUser(user_dict))
    self._user3 = self._users[2]

    # Get device object from database.
    Device.Query(self._client, self._user.user_id, self._device_ids[0], None, self.stop)
    self._mobile_device = self.wait()

    self._webapp_device_id = self._user.webapp_dev_id

    self._cookie, self._cookie2, self._cookie3 = self._cookies

    # Get identity for each user.
    self._identities = [self._RunAsync(user.QueryIdentities, self._client)[0] for user in self._users]

  def _CreateSimpleTestAssets(self):
    """Create two episodes with several photos in user #1's default
    viewpoint. This is useful for tests which just need a little data
    to work with, and where having lots of data makes debugging harder.
    """
    self._episode_id, self._photo_ids = self._UploadOneEpisode(self._cookie, 2)
    self._episode_id2, self._photo_ids2 = self._UploadOneEpisode(self._cookie, 2)

  def _ShareSimpleTestAssets(self, contacts):
    """Shares the episode and photos ids created by _CreateSimpleTestAssets with the given
    list of contacts. Returns a tuple with the viewpoint and episode.
    """
    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._episode_id, self._photo_ids)],
                                          contacts,
                                          **self._CreateViewpointDict(self._cookie))
    return vp_id, ep_ids[0]

  def _CreateSimpleContacts(self):
    """Create multiple unbound contacts for user #1 and user #2."""
    for user_id in [self._user.user_id, self._user2.user_id]:
      for identity_key in ['Local:identity1', 'Local:identity2']:
        contact_dict = Contact.CreateContactDict(user_id,
                                                 [('Phone:+13191234567', 'mobile'), (identity_key, None)],
                                                 util._TEST_TIME,
                                                 Contact.GMAIL)
        self._UpdateOrAllocateDBObject(Contact, **contact_dict)

  def _CreateProspectiveUser(self):
    """Creates a prospective user by sharing the photos created by _CreateSimpleTestAssets to
    a new email identity "Email:prospective@emailscrubbed.com". Returns a tuple containing the user,
    the new viewpoint, and the new episode.
    """
    assert getattr(self, '_episode_id'), 'call _CreateSimpleTestAssets first'
    vp_id, ep_ids = self._tester.ShareNew(self._cookie,
                                          [(self._episode_id, self._photo_ids)],
                                          ['Email:prospective@emailscrubbed.com'])

    identity = self._RunAsync(Identity.Query, self._client, 'Email:prospective@emailscrubbed.com', None)
    return self._RunAsync(User.Query, self._client, identity.user_id, None), vp_id, ep_ids[0]

  def _CreateQueryAssets(self, add_test_photos=False):
    """Create a good number of interesting viewfinder assets for use by
    query tests in derived classes. Use the tester classes in order to
    ensure that all will be cleaned up after the test has completed.
    """
    # User #1 has empty viewpoint with only himself as follower.
    self._tester.ShareNew(self._cookie, [], [], **self._CreateViewpointDict(self._cookie))

    # User #1 uploads a bunch of episodes to his default viewpoint.
    ep_ph_ids_list = self._UploadMultipleEpisodes(self._cookie,
                                                  37,
                                                  add_asset_keys=True,
                                                  add_test_photos=add_test_photos)

    # User #1 shares the episodes with users #2 and #3.
    vp_id, ep_ids = self._tester.ShareNew(self._cookie, ep_ph_ids_list,
                                          [self._user2.user_id, self._user3.user_id],
                                          **self._CreateViewpointDict(self._cookie))

    # All 3 users post comments to the new viewpoint.
    user_cookies = [self._cookie, self._cookie2, self._cookie3]
    self._PostCommentChain(user_cookies, vp_id, 4)
    self._PostCommentChain(user_cookies[:2], vp_id, 5, ph_id=ep_ph_ids_list[1][0])

    # User #1 shares 1/2 the new episodes to a new viewpoint with no followers.
    self._tester.ShareNew(self._cookie, ep_ph_ids_list[::2], [], **self._CreateViewpointDict(self._cookie))

    # User #3 uploads a bunch of episodes to his default viewpoint.
    ep_ph_ids_list = self._UploadMultipleEpisodes(self._cookie3, 17, add_test_photos=add_test_photos)

    # User #3 shares 1/2 the new episodes to a new viewpoint with user #1 as a follower.
    prev_vp_id, ep_ids = self._tester.ShareNew(self._cookie3, ep_ph_ids_list[::2], [self._user.user_id],
                                               **self._CreateViewpointDict(self._cookie3))

    # User #1 sets the viewed_seq on the new viewpoint.
    self._tester.UpdateViewpoint(self._cookie, prev_vp_id, viewed_seq=1)

    # User #1 reshares 1/2 of the new episodes to a new viewpoint with user #2 as a follower.
    ep_ph_ids_list = [(new_ep_id, old_ph_ids)
                      for new_ep_id, (old_ep_id, old_ph_ids) in zip(ep_ids, ep_ph_ids_list[::2])]
    vp_id, ep_ids = self._tester.ShareNew(self._cookie, ep_ph_ids_list[::2], [self._user2.user_id],
                                          **self._CreateViewpointDict(self._cookie))

    # Update some episode metadata in the new viewpoint.
    self._tester.UpdateEpisode(self._cookie, episode_id=ep_ids[0], title='Updated this title')

    # User #2 gets view-only permission on the new viewpoint.
    self._UpdateOrAllocateDBObject(Follower, user_id=self._user2.user_id, viewpoint_id=vp_id, labels=[])

    # User #1 reshares the episodes shared with user #2 back to the previous viewpoint.
    ep_ph_ids_list = [(new_ep_id, old_ph_ids)
                      for new_ep_id, (old_ep_id, old_ph_ids) in zip(ep_ids, ep_ph_ids_list[::2])]
    self._tester.ShareExisting(self._cookie, prev_vp_id, ep_ph_ids_list)

  def _UpdateOrAllocateDBObject(self, cls, **db_dict):
    """Updates an existing DBObject of type "cls", with the attributes
    in "db_dict". If no such object yet exists, allocates a new object,
    generating the object's key if necessary. Adds the object to the DB
    validator's model so that it can verify against it. Returns the
    updated or allocate object.

    This method is especially useful in cases where the service API
    does not have a way to create a certain kind of object without
    a lot of trouble, or if we need to simulate some condition by
    directly modifying an object in the DB.
    """
    # Check for conditions under which we can do an allocation.
    # For a hash-key only object, just verify the hash key
    # has not been supplied.
    #
    # For a composite key object, verify that the range key
    # is not supplied, but hash key is.
    hash_key_col = cls._table.hash_key_col
    range_key_col = cls._table.range_key_col
    if not range_key_col:
      if not db_dict.has_key(hash_key_col.name):
        cls.Allocate(self._client, self.stop)
      else:
        cls.Query(self._client, db_dict[hash_key_col.name],
                  col_names=None, callback=self.stop, must_exist=False)
    else:
      assert db_dict.has_key(hash_key_col.name), 'Must supply hash key.'
      if not db_dict.has_key(range_key_col.name):
        cls.Allocate(self._client, db_dict[hash_key_col.name], self.stop)
      else:
        cls.Query(self._client, db_dict[hash_key_col.name], db_dict[range_key_col.name],
                  col_names=None, callback=self.stop, must_exist=False)

    o = self.wait()
    if o == None:
      o = cls()
      o._version = Version.GetCurrentVersion()

    for k, v in db_dict.items():
      setattr(o, k, v)
    o.Update(self._client, self.stop)
    self.wait()
    self._validator.AddModelObject(o)
    return o

  def _MakeSystemViewpoint(self, viewpoint_id):
    """Force the specified viewpoint to be a system viewpoint for testing purposes."""
    viewpoint = self._RunAsync(Viewpoint.Query, self._client, viewpoint_id, None)

    # Patch read_only for the "type" field so that the field can be overwritten.
    with mock.patch.object(viewpoint._columns['type'].col_def, 'read_only', False):
      self._UpdateOrAllocateDBObject(Viewpoint, viewpoint_id=viewpoint_id, type=Viewpoint.SYSTEM)

  def _WriteClientLog(self, user_cookie, log_record):
    """Writes "log_content" to a user client log."""
    response_dict = self._SendRequest('new_client_log_url', user_cookie,
                                      {'headers': {'op_id': 'o1', 'op_timestamp': time.time()},
                                       'timestamp': log_record.timestamp,
                                       'client_log_id': log_record.client_id})
    url = response_dict['client_log_put_url']

    headers = {'Content-Type': CLIENT_LOG_CONTENT_TYPE}
    self._tester.http_client.fetch(url, callback=self.stop, method='PUT',
                                   body=log_record.contents, follow_redirects=False,
                                   headers=headers)
    response = self.wait()
    self.assertEqual(200, response.code)

  def _PostCommentChain(self, user_cookies, vp_id, num_comments, ph_id=None):
    """Generate and execute requests to post "num_comments" to the specified
    viewpoint. Select from "user_cookies" to impersonate users who are
    posting the comments. Link each comment to the preceding comment via
    its "asset_id" attribute. If "ph_id" is specified, link the "root"
    comment's "asset_id" to that photo. Return the list of ids of the
    photos that were created.
    """
    comment_ids = []
    timestamp = time.time()
    asset_id = ph_id
    for i in xrange(num_comments):
      cm_dict = {'timestamp': timestamp}
      message = 'Comment #%d' % self._test_id
      if asset_id is not None:
        cm_dict['asset_id'] = asset_id
      timestamp += 10
      self._test_id += 1

      user_cookie = user_cookies[i % len(user_cookies)]
      asset_id = self._tester.PostComment(user_cookie, vp_id, message, **cm_dict)
      comment_ids.append(asset_id)

    return comment_ids

    self._episode_id, self._photo_ids = self._UploadOneEpisodes(self._cookie, 2)

  def _UploadOneEpisode(self, user_cookie, num_photos):
    """Generate and execute a request to upload "num_photos" to the default
    viewpoint of the specified user. Return a tuple of ids:
      (episode_id, photo_ids)
    """
    ep_dict = {'title': 'Episode #%d Title' % self._test_id,
               'description': 'Episode #%d Description' % self._test_id}
    self._test_id += 1
    ph_dict_list = [self._CreatePhotoDict(user_cookie)
                    for i in range(num_photos)]
    return self._tester.UploadEpisode(user_cookie, ep_dict, ph_dict_list)

  def _UploadMultipleEpisodes(self, user_cookie, num_photos, add_asset_keys=False, add_test_photos=False):
    """Upload multiple episodes to the specified user's default viewpoint.
    Divide "num_photos" into groups that logarithmically decrease in size
    (base-2). Create the number of episodes that are needed to contain
    those photos, where each episode has a different number of photos,
    and the last episode has zero photos. Return a list of tuples:
      [(episode_id, photo_ids), ...]
    """
    result = []
    while True:
      half = (num_photos + 1) / 2
      num_photos -= half

      ep_dict = {'title': 'Episode #%d Title' % self._test_id,
                 'description': 'Episode #%d Description' % self._test_id}
      self._test_id += 1

      ph_dict_list = [self._CreatePhotoDict(user_cookie)
                      for i in range(half)]

      if add_asset_keys:
        for ph_dict in ph_dict_list:
          ph_dict['asset_keys'] = ['a/#asset_key-%d' % self._test_id]
          self._test_id += 1

      result.append(self._tester.UploadEpisode(user_cookie, ep_dict, ph_dict_list, add_test_photos=add_test_photos))

      if half == 0:
        return result



  # =================================================================
  #
  # Helper methods to get useful verification info from service API.
  #
  # =================================================================

  def _CountEpisodes(self, user_cookie, viewpoint_id):
    """Return count of episodes in the given viewpoint."""
    vp_select = self._tester.CreateViewpointSelection(viewpoint_id)
    response_dict = self._tester.QueryViewpoints(user_cookie, [vp_select])
    return len(response_dict['viewpoints'][0]['episodes'])



  # =================================================================
  #
  # Helper methods to create service API request and object dicts.
  #
  # =================================================================

  def _CreateViewpointDict(self, user_cookie, **update_vp_dict):
    """Create dict() for a test viewpoint, overriding default values with
    whatever is passed in "update_vp_dict"."""
    user_id, device_id = self._tester.GetIdsFromCookie(user_cookie)
    vp_dict = {'viewpoint_id': Viewpoint.ConstructViewpointId(device_id, self._test_id),
               'title': 'Title %s' % self._test_id,
               'description': 'Description %s. 朋友你好.' % self._test_id,
               'name': 'Name %s' % self._test_id,
               'type': Viewpoint.EVENT}
    self._test_id += 1
    vp_dict.update(**update_vp_dict)
    return vp_dict

  def _CreateEpisodeDict(self, user_cookie, **update_ep_dict):
    """Create dict() for a test episode, overriding default values with
    whatever is passed in "update_ep_dict"."""
    user_id, device_id = self._tester.GetIdsFromCookie(user_cookie)
    timestamp = time.time() - self._test_id
    ep_dict = {'episode_id': Episode.ConstructEpisodeId(timestamp, device_id, self._test_id),
               'timestamp': timestamp,
               'title': 'Title %s' % self._test_id,
               'description': 'Description %s. 朋友你好.' % self._test_id}
    self._test_id += 1
    ep_dict.update(**update_ep_dict)
    return ep_dict

  def _CreatePhotoDict(self, user_cookie, **update_ph_dict):
    """Create dict() for a test photo, overriding default values with
    whatever is passed in "update_ph_dict"."""
    user_id, device_id = self._tester.GetIdsFromCookie(user_cookie)
    timestamp = update_ph_dict.get('timestamp', time.time() - self._test_id)
    ph_dict = {'photo_id': Photo.ConstructPhotoId(timestamp, device_id, self._test_id),
               'aspect_ratio': .75 + self._test_id,
               'content_type': 'image/jpeg',
               'tn_md5': util.ComputeMD5Hex('thumbnail image data'),
               'med_md5': util.ComputeMD5Hex('medium image data'),
               'full_md5': util.ComputeMD5Hex('full image data'),
               'orig_md5': util.ComputeMD5Hex('original image data'),
               'location': {'latitude': 47.5675, 'longitude':-121.962, 'accuracy': 0.0},
               'placemark': {'iso_country_code': u'US',
                             'thoroughfare': u'SE 43rd St',
                             'locality': u'Fall City',
                             'country': u'United States',
                             'subthoroughfare': u'28408',
                             'state': u'Washington',
                             'sublocality': u'Issaquah Plateau'},
               'tn_size': 5 * 1024,
               'med_size': 40 * 1024,
               'full_size': 150 * 1024,
               'orig_size': 1200 * 1024,
               'timestamp': timestamp,
               'caption': 'Photo caption #%d' % self._test_id}
    self._test_id += 1
    ph_dict.update(**update_ph_dict)
    return ph_dict
