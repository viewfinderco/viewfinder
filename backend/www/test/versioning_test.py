# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test old and new message formats.

This module contains tests that cover various versioning scenarios:

  1. Tests of older message formats that clients may still be using,
     in order to make sure that we still accept them.

  2. Tests to make sure we do not allow methods to be invoked using
     a version that does not support them.

  3. Tests of older DB formats that exist until DB upgrade occurs.

"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import json
import time

from viewfinder.backend.base.message import Message
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user import User
from viewfinder.backend.db.user_post import UserPost
from viewfinder.backend.www.test import auth_test, service_base_test

class VersioningTestCase(service_base_test.ServiceBaseTestCase):
  def setUp(self):
    super(VersioningTestCase, self).setUp()
    self._validate = False

  def testInlineInvalidationsMigration(self):
    """Ensure that the INLINE_INVALIDATIONS migration works correctly."""
    episode_id = Episode.ConstructEpisodeId(1, self._device_ids[0], 1)
    photo_id = Photo.ConstructPhotoId(1, self._device_ids[0], 1)
    request = {'activity': self._tester.CreateActivityDict(self._cookie),
               'episode': {'episode_id': episode_id,
                           'timestamp': 1},
               'photos': [self._CreatePhotoDict(self._cookie, photo_id=photo_id)]}
    self._SendRequest('upload_episode', self._cookie, request,
                      version=Message.EXTRACT_MD5_HASHES)

    request = {'episodes': [{'episode_id': episode_id,
                             'photo_ids': [photo_id]}]}
    self._SendRequest('remove_photos', self._cookie, request,
                      version=Message.EXTRACT_MD5_HASHES)

    request = {'activity': self._tester.CreateActivityDict(self._cookie),
               'viewpoint_id': self._user.private_vp_id,
               'viewed_seq': 2}
    self._SendRequest('update_viewpoint', self._cookie, request,
                      version=Message.EXTRACT_MD5_HASHES)

    response = self._SendRequest('query_notifications', self._cookie, {},
                                 version=Message.EXTRACT_MD5_HASHES)

    # upload_episode notification.
    notify_dict = response['notifications'][1]
    self.assertFalse('inline' in notify_dict)
    self.assertTrue('activity' in notify_dict)
    self.assertEqual(notify_dict['activity']['update_seq'], 1)

    # remove_photos notification.
    notify_dict = response['notifications'][2]
    self.assertFalse('inline' in notify_dict)
    self.assertFalse('activity' in notify_dict)

    # update_viewpoint notification.
    notify_dict = response['notifications'][3]
    self.assertFalse('inline' in notify_dict)
    self.assertFalse('activity' in notify_dict)

  def testFileSizeExtraction(self):
    """Ensure that the EXTRACT_FILE_SIZES migration works correctly."""
    episode_id = Episode.ConstructEpisodeId(1, self._device_ids[0], 1)
    photo_id = Photo.ConstructPhotoId(1, self._device_ids[0], 1)
    # create request with size fields in client_data.
    request = {'activity': self._tester.CreateActivityDict(self._cookie),
               'episode': {'episode_id': episode_id,
                           'timestamp': 1},
               'photos': [self._CreatePhotoDict(self._cookie, photo_id=photo_id,
                                                client_data={'tn_size':'5', 'med_size':'40',
                                                             'full_size':'150', 'orig_size':'1200'})]}

    # remove size fields from the photo metadata, leaving only those in client_data.
    photo = request['photos'][0]
    del photo['tn_size']
    del photo['med_size']
    del photo['full_size']
    del photo['orig_size']

    self._SendRequest('upload_episode', self._cookie, request, version=Message.INLINE_INVALIDATIONS)

  def testInlineCommentsMigration(self):
    """Ensure that the INLINE_COMMENTS migration works correctly."""
    comment_id = self._tester.PostComment(self._cookie, self._user.private_vp_id, 'hi')

    response_dict = self._SendRequest('query_notifications', self._cookie,
                                      {'scan_forward': False},
                                      version=Message.EXTRACT_FILE_SIZES)
    notify_dict = response_dict['notifications'][0]
    invalidate = notify_dict['invalidate']

    self.assertEqual(notify_dict['name'], 'post_comment')

    timestamp, device_id, uniquifier = Comment.DeconstructCommentId(comment_id)
    start_key = Comment.ConstructCommentId(timestamp, 0, 0)
    self.assertEqual(invalidate, {'viewpoints': [{'viewpoint_id': self._user.private_vp_id,
                                                  'get_comments': True,
                                                  'comment_start_key': start_key}]})

  def testSplitNamesMigration(self):
    """Ensure that the SPLIT_NAMES migration works correctly."""
    self._SendRequest('update_user', self._cookie,
                      {'name': ' \t\r\nAndrew   E \tKimball '},
                      version=Message.INLINE_COMMENTS)
    user = self._RunAsync(User.Query, self._client, self._user.user_id, None)
    self.assertEqual(user.name, ' \t\r\nAndrew   E \tKimball ')
    self.assertEqual(user.given_name, 'Andrew')
    self.assertEqual(user.family_name, 'E \tKimball ')

    self._SendRequest('update_user', self._cookie,
                      {'name': 'Andy'},
                      version=Message.INLINE_COMMENTS)
    user = self._RunAsync(User.Query, self._client, self._user.user_id, None)
    self.assertEqual(user.name, 'Andy')
    self.assertEqual(user.given_name, 'Andy')
    self.assertIsNone(user.family_name)

  def testExplicitShareOrderMigration(self):
    """Ensure that the EXPLICIT_SHARE_ORDER migration works correctly.
    The expectation is that the migration orders the episode ids and photo ids to the
    original mobile client algorithm for cover photo selection.
    """
    def _IsEpDictOrderedAsOriginalAlgorithm(ep_dicts, episode_id_key):
      """Returns true if the order matches original mobile client algorithm ordering for
      cover photo selection."""
      last_episode_id = None
      for ep_dict in ep_dicts:
        # Episodes should be greatest (earliest) first.
        if last_episode_id is not None and ep_dict[episode_id_key] >= last_episode_id:
          return False
        last_episode_id = ep_dict[episode_id_key]
        # Now, loop through the photos in this episode.
        last_photo_id = None
        for photo_id in ep_dict['photo_ids']:
          # Photo Ids should be least (oldest) first.
          if last_photo_id is not None and photo_id <= last_photo_id:
            return False
          last_photo_id = photo_id
      # Nothing out of order found.
      return True

    def _ConstructEpDict():
      """Create some ep_dicts for sharing."""
      # Create 2 episodes with 2 photos each.
      episode_id1, photo_ids1 = self._UploadOneEpisode(self._cookie, 2)
      episode_id2, photo_ids2 = self._UploadOneEpisode(self._cookie, 2)

      ep_dicts = self._tester._CreateCopyDictList(self._cookie,
                                                 [(episode_id1, photo_ids1),
                                                  (episode_id2, photo_ids2)])

      # Order the episodes and photos so that the migration will need to change it.
      # This is the opposite of the original client algorithm for cover photo selection.
      ep_dicts = sorted(ep_dicts, key=lambda e: e['new_episode_id'])
      for episode in ep_dicts:
        episode['photo_ids'] = sorted(episode['photo_ids'], reverse=True)

      # Assert that these are not ordered according to the original client algorithm for cover photo selection.
      self.assertFalse(_IsEpDictOrderedAsOriginalAlgorithm(ep_dicts, 'new_episode_id'),
                       'Should not be correctly ordered at this point')

      return ep_dicts

    # Generate a couple of ep_dicts to share.
    ep_dicts1 = _ConstructEpDict()
    ep_dicts2 = _ConstructEpDict()

    # Do a share_new.
    request_dict = {'activity': self._tester.CreateActivityDict(self._cookie),
                    'viewpoint': self._CreateViewpointDict(self._cookie),
                    'episodes': ep_dicts1,
                    'contacts': self._tester.CreateContactDicts([self._user2.user_id, self._user3.user_id])}
    self._SendRequest('share_new', self._cookie, request_dict, version=Message.INLINE_COMMENTS)

    # Now, do a share_existing.
    request_dict = {'activity': self._tester.CreateActivityDict(self._cookie),
                    'viewpoint_id': request_dict['viewpoint']['viewpoint_id'],
                    'episodes': ep_dicts2}
    self._SendRequest('share_existing', self._cookie, request_dict, version=Message.INLINE_COMMENTS)

    # Query the activities to see what order the episode_ids and photo_ids were persisted in.
    activities = self._RunAsync(Activity.RangeQuery,
                                      self._client,
                                      request_dict['viewpoint_id'],
                                      range_desc=None,
                                      limit=50,
                                      col_names=None,
                                      scan_forward=False)

    # Check that the order of episode ids and photo ids is consistent with the original mobile client
    # algorithm for cover photo selection.  This demonstrates that the migration happened.
    for activity in activities:
      # Note this is only valid for share_new and share_existing activities, but that's all we should have
      # as this point.
      args_dict = json.loads(activity.json)
      self.assertTrue(_IsEpDictOrderedAsOriginalAlgorithm(args_dict['episodes'], 'episode_id'),
                       'Should be correctly ordered at this point')

  def testSuppressBlankCoverPhotoMigration(self):
    """Ensure that the SUPPRESS_BLANK_COVER_PHOTO migration works correctly."""
    episode_id1, photo_ids1 = self._UploadOneEpisode(self._cookie, 2)
    ep_dicts = self._tester._CreateCopyDictList(self._cookie, [(episode_id1, photo_ids1)])

    update_vp_dict = {'cover_photo': {'episode_id': episode_id1, 'photo_id': ''}}
    request_dict = {'activity': self._tester.CreateActivityDict(self._cookie),
                    'viewpoint': self._CreateViewpointDict(self._cookie, **update_vp_dict),
                    'episodes': ep_dicts,
                    'contacts': self._tester.CreateContactDicts([self._user2.user_id])}
    self._SendRequest('share_new', self._cookie, request_dict, version=Message.EXPLICIT_SHARE_ORDER)

  def testSupportMultipleIdentitiesPerContact(self):
    """Ensure that the SUPPORT_MULTIPLE_IDENTITIES_PER_CONTACT migration works correctly."""
    identity_key = 'Email:' + self._user2.email

    # Create an identity to exercise the 'contact_user_id' field of the down-level response.
    self._UpdateOrAllocateDBObject(Identity, key=identity_key, user_id=21)

    # This contact is for a registered user.
    contact_dict = Contact.CreateContactDict(user_id=self._user.user_id,
                                             identities_properties=[(identity_key, 'work'),
                                                                    ('Email:' + self._user3.email, 'home'),
                                                                    ('Phone:+13191234567', 'mobile')],
                                             timestamp=1,
                                             contact_source=Contact.GMAIL,
                                             name='Mike Purtell',
                                             given_name='Mike',
                                             family_name='Purtell',
                                             rank=3)
    self._UpdateOrAllocateDBObject(Contact, **contact_dict)

    # This contact has been removed and shouldn't show up in down-level client queries.
    contact_dict = Contact.CreateContactDict(user_id=self._user.user_id,
                                             identities_properties=None,
                                             timestamp=1,
                                             contact_source=Contact.GMAIL,
                                             contact_id='gm:onetwothree',
                                             sort_key=Contact.CreateSortKey('gm:onetwothree', 1),
                                             labels=[Contact.REMOVED])
    self._UpdateOrAllocateDBObject(Contact, **contact_dict)

    # This contact has unknown identities.
    contact_dict = Contact.CreateContactDict(user_id=self._user.user_id,
                                             identities_properties=[('Email:someone@somewhere.com', 'work'),
                                                                    ('Email:somebody@somewhere.com', 'home'),
                                                                    ('Phone:+13191234567', 'mobile')],
                                             timestamp=1,
                                             contact_source=Contact.GMAIL,
                                             name='Some One',
                                             given_name='Some',
                                             family_name='Body',
                                             rank=5)
    self._UpdateOrAllocateDBObject(Contact, **contact_dict)

    # This contact has just a phone number and shouldn't show up in down-level client queries.
    contact_dict = Contact.CreateContactDict(user_id=self._user.user_id,
                                             identities_properties=[('Phone:+13191234567', 'mobile')],
                                             timestamp=1,
                                             contact_source=Contact.GMAIL,
                                             name='Some One with just a phone',
                                             given_name='Some',
                                             family_name='Body',
                                             rank=42)
    self._UpdateOrAllocateDBObject(Contact, **contact_dict)

    # This contact has no identities and shouldn't show up in down-level client queries.
    contact_dict = Contact.CreateContactDict(user_id=self._user.user_id,
                                             identities_properties=[],
                                             timestamp=1,
                                             contact_source=Contact.GMAIL,
                                             name='Some One with just a phone',
                                             given_name='Some',
                                             family_name='Body',
                                             rank=42)
    self._UpdateOrAllocateDBObject(Contact, **contact_dict)

    response = self._SendRequest('query_contacts', self._cookie, {}, version=Message.SUPPRESS_BLANK_COVER_PHOTO)

    # Verify response is what we expect for down-level client.
    self.assertEqual(response['headers'], {'version': Message.SUPPRESS_BLANK_COVER_PHOTO})
    self.assertEqual(response['num_contacts'], 2)
    response_contact = response['contacts'][1]
    self.assertEqual(response_contact['name'], 'Mike Purtell')
    self.assertEqual(response_contact['given_name'], 'Mike')
    self.assertEqual(response_contact['family_name'], 'Purtell')
    self.assertEqual(response_contact['rank'], 3)
    self.assertEqual(response_contact['contact_user_id'], 21)
    self.assertEqual(response_contact['identity'], identity_key)
    self.assertFalse('identities' in response_contact)
    self.assertFalse('contact_id' in response_contact)
    self.assertFalse('contact_source' in response_contact)
    self.assertFalse('labels' in response_contact)

    response_contact = response['contacts'][0]
    self.assertEqual(response_contact['name'], 'Some One')
    self.assertEqual(response_contact['given_name'], 'Some')
    self.assertEqual(response_contact['family_name'], 'Body')
    self.assertEqual(response_contact['rank'], 5)
    self.assertEqual(response_contact['identity'], 'Email:someone@somewhere.com')
    self.assertFalse('contact_user_id' in response_contact)
    self.assertFalse('identities' in response_contact)
    self.assertFalse('contact_id' in response_contact)
    self.assertFalse('contact_source' in response_contact)
    self.assertFalse('labels' in response_contact)

  def testRenamePhotoLabelMigration(self):
    """Test migrator that renames HIDDEN label to REMOVED for older clients."""
    ep_id, ph_ids = self._UploadOneEpisode(self._cookie, 2)

    response_dict = self._SendRequest('remove_photos', self._cookie,
                                      {'episodes': [{'episode_id': ep_id,
                                                     'photo_ids': ph_ids[:1]},
                                                    {'episode_id': ep_id,
                                                     'photo_ids': ph_ids[1:]}]},
                                      version=Message.SUPPORT_MULTIPLE_IDENTITIES_PER_CONTACT)

    # Update USER_POST row to use HIDDEN label.
    post_id = Post.ConstructPostId(ep_id, ph_ids[0])
    self._UpdateOrAllocateDBObject(UserPost,
                                   user_id=self._user.user_id,
                                   post_id=post_id,
                                   labels=[UserPost.HIDDEN])

    response_dict = self._SendRequest('query_episodes', self._cookie,
                                      {'episodes': [{'episode_id': ep_id,
                                                     'get_attributes': True,
                                                     'get_photos': True},
                                                    {'episode_id': ep_id,
                                                     'get_photos': True},
                                                    {'episode_id': ep_id}]},
                                      version=Message.SUPPORT_MULTIPLE_IDENTITIES_PER_CONTACT)

    labels = [ph_dict['labels'] for ep_dict in response_dict['episodes'] for ph_dict in ep_dict.get('photos', [])]
    self.assertEqual(labels, [[u'removed'], [u'removed'], [u'removed'], [u'removed']])

  def testSuppressAuthNameMigration(self):
    """Test migrator that removes names from non-register auth messages."""
    user_dict = {'name': 'Andy Kimball',
                 'given_name': 'Andy',
                 'family_name': 'Kimball',
                 'email': 'andy@emailscrubbed.com'}

    user, device_id = self._tester.RegisterViewfinderUser(user_dict, None)
    user_cookie = self._GetSecureUserCookie(user, device_id)

    url = self._tester.GetUrl('/link/viewfinder')
    request_dict = {'headers': {'version': Message.RENAME_PHOTO_LABEL,
                                'synchronous': True},
                    'auth_info': {'identity': 'Email:andy@emailscrubbed.com',
                                  'name': 'Andy Kimball',
                                  'given_name': 'Andy',
                                  'family_name': 'Kimball'}}
    response = auth_test._SendAuthRequest(self._tester,
                                          url,
                                          'POST',
                                          user_cookie=user_cookie,
                                          request_dict=request_dict)
    self.assertEqual(response.code, 200)

  def testSupportRemovedFollowers(self):
    """Test migrator that projects only ids from followers returned by query_viewpoints."""
    self._CreateSimpleTestAssets()
    vp_id, _ = self._ShareSimpleTestAssets([self._user2.user_id, self._user3.user_id])
    self._tester.RemoveFollowers(self._cookie, vp_id, [self._user3.user_id])

    response_dict = self._SendRequest('query_viewpoints', self._cookie,
                                      {'viewpoints': [{'viewpoint_id': vp_id,
                                                       'get_followers': True}]},
                                      version=Message.SEND_EMAIL_TOKEN)

    self.assertEqual(response_dict['viewpoints'][0]['followers'], [1, 2, 3])

  def testSuppressCopyTimestamp(self):
    """Test migrator that removes timestamp from share and save operations."""
    self._CreateSimpleTestAssets()

    # First do a share_new.
    new_episode_id = Episode.ConstructEpisodeId(time.time(), self._device_ids[0], self._test_id)
    self._test_id += 1

    request_dict = {'activity': self._tester.CreateActivityDict(self._cookie),
                    'viewpoint': self._CreateViewpointDict(self._cookie),
                    'episodes': [{'existing_episode_id': self._episode_id,
                                  'new_episode_id': new_episode_id,
                                  'timestamp': time.time(),
                                  'photo_ids': self._photo_ids}],
                    'contacts': self._tester.CreateContactDicts([self._user2.user_id])}
    self._SendRequest('share_new', self._cookie, request_dict, version=Message.SUPPORT_REMOVED_FOLLOWERS)

    # Now, do a share_existing.
    new_episode_id2 = Episode.ConstructEpisodeId(time.time(), self._device_ids[0], self._test_id)
    self._test_id += 1

    request_dict = {'activity': self._tester.CreateActivityDict(self._cookie),
                    'viewpoint_id': request_dict['viewpoint']['viewpoint_id'],
                    'episodes': [{'existing_episode_id': self._episode_id2,
                                  'new_episode_id': new_episode_id2,
                                  'timestamp': time.time(),
                                  'photo_ids': self._photo_ids2}]}
    self._SendRequest('share_existing', self._cookie, request_dict, version=Message.SUPPORT_REMOVED_FOLLOWERS)

    # Now, do a save_photos.
    save_episode_id = Episode.ConstructEpisodeId(time.time(), self._device_ids[1], self._test_id)
    self._test_id += 1

    request_dict = {'activity': self._tester.CreateActivityDict(self._cookie2),
                    'episodes': [{'existing_episode_id': new_episode_id,
                                  'new_episode_id': save_episode_id,
                                  'timestamp': time.time(),
                                  'photo_ids': self._photo_ids}]}
    self._SendRequest('save_photos', self._cookie2, request_dict, version=Message.SUPPORT_REMOVED_FOLLOWERS)

  def testSupportContactLimits(self):
    """Test migrator that truncates and skips fields in upload_contacts."""
    request_dict = {'contacts': [{'contact_source': Contact.MANUAL,
                                  'name': 'a' * 1001,
                                  'given_name': 'a' * 2000,
                                  'family_name': 'a' * 6000,
                                  'identities': [{'identity': 'Email:%s' % ('a' * 1001), 'description': 'a' * 1001}
                                                 for i in xrange(100)]}]}
    self._SendRequest('upload_contacts', self._cookie, request_dict, version=Message.SUPPRESS_COPY_TIMESTAMP)

  def testSuppressEmptyTitle(self):
    """Test migrator that removes empty titles from update_viewpoint operations."""
    self._CreateSimpleTestAssets()
    vp_id, ep_id = self._ShareSimpleTestAssets([self._user2.user_id])

    request_dict = {'activity': self._tester.CreateActivityDict(self._cookie),
                    'viewpoint_id': vp_id,
                    'title': ''}
    self._SendRequest('update_viewpoint', self._cookie, request_dict, version=Message.SUPPORT_CONTACT_LIMITS)

  def _TestMethodNotSupported(self, method, version):
    """Test that "method" is not supported in the specified "version" of the
    message protocol.
    """
    self.assertRaisesHttpError(400, self._SendRequest, method, self._cookie, {}, version=version)
