# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Validated testing of the Viewfinder service API.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import difflib
import io
import json
import os
import re
import time

from collections import defaultdict
from copy import deepcopy
from tornado import web
from viewfinder.backend.base import util, message
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.notification import Notification
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.settings import AccountSettings
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.alert_manager import AlertManager
from viewfinder.backend.resources.resources_mgr import ResourcesManager
from viewfinder.backend.services.apns import TestService
from viewfinder.backend.services.email_mgr import TestEmailManager
from viewfinder.backend.services.sms_mgr import TestSMSManager
from viewfinder.backend.www import basic_auth
from viewfinder.backend.www.admin.otp import OTPEntryHandler
from viewfinder.backend.www.service import ServiceHandler
from viewfinder.backend.www.www_util import GzipEncode


class ServiceTester(object):
  """This class is a validated wrapper around the Viewfinder service API.
  API methods may be invoked twice to ensure idempotency. Results are
  validated against a model of the database to ensure correctness.
  The database is validated to ensure that the correct objects were
  created, updated, or deleted. All objects that are created during the
  operation are tracked so that they can be used in validation and then
  later cleaned up.

  In order to keep this file from getting massively large, the validation
  code for each service API method is implemented in each respective test
  file. To add a new method, create a method called _TestXXX in your
  test file, and then add a wrapper method here that calls it.
  """
  SERVER_VERSION = '1.1'

  def __init__(self, svc_url, http_client, validator, secret, stop, wait):
    self.validator = validator
    self.http_client = http_client
    self._svc_url = svc_url
    self._secret = secret
    self._stop = stop
    self._wait = wait
    self._op_id = 1
    self._test_id = 1

  def Cleanup(self, validate=False, skip_validation_for=None):
    """Deletes all objects that were created in the context of the model.
    If validate=True, then validates all objects before the cleanup.
    "skip_validation_for" is a list of string names of validation checks
    to skip.
    """
    # In addition to validating the presence/absence of objects, validate that the
    # proper alerts have been sent.
    if validate:
      if skip_validation_for is not None:
        if 'Alerts' not in skip_validation_for:
          self._ValidateAlerts()
        if 'Accounting' not in skip_validation_for:
          self.validator.ValidateAccounting()

    self.validator.Cleanup(validate=validate)


  # =================================================================
  #
  # Verified test wrappers for each service API method.
  #   -- Synchronous for ease of use
  #   -- Automatically generates request data where possible
  #   -- Creates activity parameter where required
  #   -- Creates request dict
  #
  # =================================================================

  def AddFollowers(self, user_cookie, viewpoint_id, contacts, act_dict=None):
    """add_followers: Adds contacts as followers of an existing viewpoint.

    The format of "contacts" is described in the header to CreateContactDicts.
    """
    request_dict = {'activity': act_dict or self.CreateActivityDict(user_cookie),
                    'viewpoint_id': viewpoint_id,
                    'contacts': self.CreateContactDicts(contacts)}

    from viewfinder.backend.www.test.add_followers_test import _TestAddFollowers
    _TestAddFollowers(self, user_cookie, request_dict)

  def BuildArchive(self, user_cookie):
    """build_archive: build archive of all of user content and prepare it for download."""
    from viewfinder.backend.www.test.build_archive_test import _TestBuildArchive
    return _TestBuildArchive(self, user_cookie)

  def HidePhotos(self, user_cookie, ep_ph_ids_list):
    """hide_photos: Hides photos from a user's personal library or inbox view.

    "ep_ph_ids_list" is a list of tuples in this format:
      [(episode, [photo_id, ...]), ...]
    """
    request_dict = {'episodes': [{'episode_id': episode_id,
                                  'photo_ids': photo_ids}
                                 for episode_id, photo_ids in ep_ph_ids_list]}

    from viewfinder.backend.www.test.hide_photos_test import _TestHidePhotos
    _TestHidePhotos(self, user_cookie, request_dict)

  def ListIdentities(self, user_cookie):
    """list_identities: Lists all identities that are linked to the requesting user.
    This is embedded in the query_users response when querying self.

    Returns a list of the identity keys.
    """
    user_id, device_id = self.GetIdsFromCookie(user_cookie)
    response_dict = self.QueryUsers(user_cookie, [user_id])
    private = response_dict['users'][0]['private']
    return [ident_dict['identity'] for ident_dict in private['user_identities']]

  def MergeAccounts(self, user_cookie, source_user_cookie=None, source_identity_dict=None, act_dict=None):
    """merge_accounts: Merges assets from a source user account into the target user account,
                       or links a source identity to the target user account.
    """
    from viewfinder.backend.www.test.merge_accounts_test import _TestMergeAccounts
    request_dict = {'activity': act_dict or self.CreateActivityDict(user_cookie)}
    util.SetIfNotNone(request_dict, 'source_user_cookie', source_user_cookie)
    util.SetIfNotNone(request_dict, 'source_identity', source_identity_dict)
    _TestMergeAccounts(self, user_cookie, request_dict)

  def PostComment(self, user_cookie, viewpoint_id, message, act_dict=None, **cm_dict):
    """post_comment: Adds a new comment to a viewpoint.

    Additional comment fields can be passed in "cm_dict". Returns the
    id of the new comment.
    """
    # Generate comment id (but can be overridden in cm_dict).
    user_id, device_id = self.GetIdsFromCookie(user_cookie)
    timestamp = time.time()
    comment_id = Comment.ConstructCommentId(timestamp, device_id, self._test_id)
    self._test_id += 1

    request_dict = {'activity': act_dict or self.CreateActivityDict(user_cookie),
                    'comment_id': comment_id,
                    'timestamp': timestamp,
                    'viewpoint_id': viewpoint_id,
                    'message': message}
    request_dict.update(cm_dict)

    from viewfinder.backend.www.test.post_comment_test import _TestPostComment
    _TestPostComment(self, user_cookie, request_dict)
    return comment_id

  def QueryContacts(self, user_cookie, limit=None, start_key=None):
    """query_contacts: Returns all contact metadata requested by the user."""
    request_dict = {}
    util.SetIfNotNone(request_dict, 'limit', limit)
    util.SetIfNotNone(request_dict, 'start_key', start_key)

    from viewfinder.backend.www.test.query_contacts_test import _TestQueryContacts
    return _TestQueryContacts(self, user_cookie, request_dict)

  def QueryEpisodes(self, user_cookie, ep_select_list, photo_limit=None):
    """query_episodes: Returns all episode metadata and collections
    requested by the user.

    "ep_select_list" is a list of episode selection dicts, such as
    generated by CreateEpisodeSelection.
    """
    request_dict = {'episodes': ep_select_list}
    util.SetIfNotNone(request_dict, 'photo_limit', photo_limit)

    from viewfinder.backend.www.test.query_episodes_test import _TestQueryEpisodes
    return _TestQueryEpisodes(self, user_cookie, request_dict)

  def QueryFollowed(self, user_cookie, limit=None, start_key=None):
    """query_followed: Returns metadata of all viewpoints followed by
    the user.
    """
    request_dict = {}
    util.SetIfNotNone(request_dict, 'limit', limit)
    util.SetIfNotNone(request_dict, 'start_key', start_key)

    from viewfinder.backend.www.test.query_followed_test import _TestQueryFollowed
    return _TestQueryFollowed(self, user_cookie, request_dict)

  def QueryNotifications(self, user_cookie, limit=None, start_key=None, scan_forward=None, max_long_poll=None):
    """query_notifications: Returns notifications for the requesting
    user.
    """
    request_dict = {}
    util.SetIfNotNone(request_dict, 'limit', limit)
    util.SetIfNotNone(request_dict, 'start_key', start_key)
    util.SetIfNotNone(request_dict, 'scan_forward', scan_forward)
    util.SetIfNotNone(request_dict, 'max_long_poll', max_long_poll)

    from viewfinder.backend.www.test.query_notifications_test import _TestQueryNotifications
    return _TestQueryNotifications(self, user_cookie, request_dict)

  def QueryUsers(self, user_cookie, user_ids):
    """query_users: Returns all user/friend metadata requested by the
    user.
    """
    from viewfinder.backend.www.test.query_users_test import _TestQueryUsers
    return _TestQueryUsers(self, user_cookie, {'user_ids': user_ids})

  def QueryViewpoints(self, user_cookie, vp_select_list, limit=None):
    """query_viewpoints: Returns all viewpoint metadata and collections
    requested by the user.

    "vp_select_list" is a list of viewpoint selection dicts, such as
    generated by CreateViewpointSelection.
    """
    request_dict = {'viewpoints': vp_select_list}
    util.SetIfNotNone(request_dict, 'limit', limit)

    from viewfinder.backend.www.test.query_viewpoints_test import _TestQueryViewpoints
    return _TestQueryViewpoints(self, user_cookie, request_dict)

  def RemoveContacts(self, user_cookie, contacts_list):
    """remove_contacts:  Removes contacts from a user's server based contacts container."""
    request_dict = {'contacts': contacts_list}
    from viewfinder.backend.www.test.remove_contacts_test import _TestRemoveContacts
    return _TestRemoveContacts(self, user_cookie, request_dict)

  def RemoveFollowers(self, user_cookie, viewpoint_id, remove_ids, act_dict=None):
    """remove_followers: Remove followers from an existing viewpoint.
    """
    request_dict = {'activity': act_dict or self.CreateActivityDict(user_cookie),
                    'viewpoint_id': viewpoint_id,
                    'remove_ids': remove_ids}

    from viewfinder.backend.www.test.remove_followers_test import _TestRemoveFollowers
    _TestRemoveFollowers(self, user_cookie, request_dict)

  def RemovePhotos(self, user_cookie, ep_ph_ids_list):
    """remove_photos: Removes photos from a user's personal library.

    "ep_ph_ids_list" is a list of tuples in this format:
      [(episode, [photo_id, ...]), ...]
    """
    request_dict = {'episodes': [{'episode_id': episode_id,
                                  'photo_ids': photo_ids}
                                 for episode_id, photo_ids in ep_ph_ids_list]}

    from viewfinder.backend.www.test.remove_photos_test import _TestRemovePhotos
    _TestRemovePhotos(self, user_cookie, request_dict)

  def RemoveViewpoint(self, user_cookie, viewpoint_id):
    """remove_viewpoint: Remove a viewpoint from a user's inbox."""
    request_dict = {'viewpoint_id': viewpoint_id}

    from viewfinder.backend.www.test.remove_viewpoint_test import _TestRemoveViewpoint
    _TestRemoveViewpoint(self, user_cookie, request_dict)

  def SavePhotos(self, user_cookie, ep_save_list=None, viewpoint_ids=None, act_dict=None):
    """save_photos: Saves photos to the user's default viewpoint.

    See header to _CreateCopyDictList for details on format for "save_list".

    Returns a list of the new episode ids.
    """
    request_dict = {'activity': act_dict or self.CreateActivityDict(user_cookie)}
    if ep_save_list is not None:
      request_dict['episodes'] = self._CreateCopyDictList(user_cookie, ep_save_list)
    util.SetIfNotNone(request_dict, 'viewpoint_ids', viewpoint_ids)

    from viewfinder.backend.www.test.save_photos_test import _TestSavePhotos
    _TestSavePhotos(self, user_cookie, request_dict)
    return [copy_dict['new_episode_id'] for copy_dict in request_dict.get('episodes', [])]

  def ShareExisting(self, user_cookie, viewpoint_id, share_list, act_dict=None):
    """share_existing: Shares photos with the followers of an existing
    viewpoint.

    See header to _CreateCopyDictList for details on format for "share_list".

    Returns a list of the new episode ids.
    """
    request_dict = {'activity': act_dict or self.CreateActivityDict(user_cookie),
                    'viewpoint_id': viewpoint_id,
                    'episodes': self._CreateCopyDictList(user_cookie, share_list)}

    from viewfinder.backend.www.test.share_existing_test import _TestShareExisting
    _TestShareExisting(self, user_cookie, request_dict)
    return [share_dict['new_episode_id'] for share_dict in request_dict['episodes']]

  def ShareNew(self, user_cookie, share_list, contacts, act_dict=None, **vp_dict):
    """share_existing: Shares photos with other users by adding them as followers to a new
    viewpoint to which the photos are added.

    See header to _CreateCopyDictList for details on format for "share_list". The format of
    "contacts" is described in the header to CreateContactDicts. The attributes in "vp_dict"
    are used to create the new viewpoint.

    cover_photo, if given, should have an existing_episode_id which this method will substitute
    for the new_episode_id once it's been determined.

    Returns a tuple of containing the viewpoint and episode ids:
      (viewpoint_id, new_episode_ids)
    """
    # Generate viewpoint_id (but it can be overridden in vp_dict).
    user_id, device_id = self.GetIdsFromCookie(user_cookie)
    viewpoint_id = vp_dict.get('viewpoint_id', Viewpoint.ConstructViewpointId(device_id, self._test_id))
    self._test_id += 1

    request_dict = {'activity': act_dict or self.CreateActivityDict(user_cookie),
                    'viewpoint': {'viewpoint_id': viewpoint_id,
                                  'type': Viewpoint.EVENT},
                    'episodes': self._CreateCopyDictList(user_cookie, share_list),
                    'contacts': self.CreateContactDicts(contacts)}
    cover_photo = vp_dict.get('cover_photo', None)
    if cover_photo is not None and type(cover_photo) is tuple:
      # cover_photo as tuple indicates that the episode_id is an existing_episode_id and should be substituted
      # with the new_episode_id and transformed into a dict.
      episode_id, photo_id = cover_photo
      for episode in request_dict['episodes']:
        if episode_id == episode['existing_episode_id']:
          cover_photo = {'episode_id': episode['new_episode_id'], 'photo_id': photo_id}
          break
      assert type(cover_photo) is not tuple, (vp_dict, request_dict)
      vp_dict['cover_photo'] = cover_photo
    request_dict['viewpoint'].update(vp_dict)

    from viewfinder.backend.www.test.share_new_test import _TestShareNew
    _TestShareNew(self, user_cookie, request_dict)

    return (request_dict['viewpoint']['viewpoint_id'],
            [share_dict['new_episode_id'] for share_dict in request_dict['episodes']])

  def TerminateAccount(self, user_cookie):
    """terminate_account: Terminates a user account.
    """
    from viewfinder.backend.www.test.terminate_account_test import _TestTerminateAccount
    _TestTerminateAccount(self, user_cookie, {})

  def UnlinkIdentity(self, user_cookie, identity_key):
    """unlink_identity: Unlinks an identity that is currently associated with the requesting
    user's Viewfinder account.
    """
    from viewfinder.backend.www.test.unlink_identity_test import _TestUnlinkIdentity
    _TestUnlinkIdentity(self, user_cookie, {'identity': identity_key})

  def Unshare(self, user_cookie, viewpoint_id, ep_ph_ids_list, act_dict=None):
    """unshare: Recursively unshares photos that were previously shared
    with other users.

    "ep_ph_ids_list" is a list of tuples in this format:
      [(episode, [photo_id, ...]), ...]
    """
    request_dict = {'activity': act_dict or self.CreateActivityDict(user_cookie),
                    'viewpoint_id': viewpoint_id,
                    'episodes': [{'episode_id': episode_id,
                                  'photo_ids': photo_ids}
                                 for episode_id, photo_ids in ep_ph_ids_list]}

    from viewfinder.backend.www.test.unshare_test import _TestUnshare
    _TestUnshare(self, user_cookie, request_dict)

  def UpdateDevice(self, user_cookie, device_id, **dev_dict):
    """update_device: Updates existing device's metadata.

    The attributes in "device_dict" are used to update the device.
    """
    request_dict = {'device_dict': {'device_id': device_id, 'device_uuid': '5DE5D5B8-7413-4B59-BB72-BD5E5F86C1AF',
                                    'test_udid': '7d527095d4e0539aba40c852547db5da00000000'}}
    request_dict['device_dict'].update(dev_dict)

    from viewfinder.backend.www.test.update_device_test import _TestUpdateDevice
    _TestUpdateDevice(self, user_cookie, request_dict)

  def UpdateEpisode(self, user_cookie, episode_id, act_dict=None, **ep_dict):
    """update_episode: Updates existing episode's metadata.

    The attributes in "ep_dict" are used to update the episode.
    """
    request_dict = {'activity': act_dict or self.CreateActivityDict(user_cookie),
                    'episode_id': episode_id}
    request_dict.update(ep_dict)

    from viewfinder.backend.www.test.update_episode_test import _TestUpdateEpisode
    _TestUpdateEpisode(self, user_cookie, request_dict)

  def UpdateFollower(self, user_cookie, viewpoint_id, act_dict=None, **foll_dict):
    """update_follower: Updates existing follower's metadata.

    The attributes in "foll_dict" are used to update the follower.
    """
    request_dict = {'follower': {'viewpoint_id': viewpoint_id}}
    request_dict['follower'].update(foll_dict)

    from viewfinder.backend.www.test.update_follower_test import _TestUpdateFollower
    _TestUpdateFollower(self, user_cookie, request_dict)

  def UpdateFriend(self, user_cookie, **friend_dict):
    """update_friend: Updates metadata about a friend.

    The attributes in "friend_dict" are used to update the friend.
    """
    request_dict = {'friend': friend_dict}
    from viewfinder.backend.www.test.update_friend_test import _TestUpdateFriend
    _TestUpdateFriend(self, user_cookie, request_dict)

  def UpdatePhoto(self, user_cookie, photo_id, act_dict=None, **ph_dict):
    """update_photo: Updates existing photo's metadata.

    The attributes in "ph_dict" are used to update the photo.
    """
    request_dict = {'activity': act_dict or self.CreateActivityDict(user_cookie),
                    'photo_id': photo_id}
    request_dict.update(ph_dict)

    from viewfinder.backend.www.test.update_photo_test import _TestUpdatePhoto
    _TestUpdatePhoto(self, user_cookie, request_dict)

  def UpdateUser(self, user_cookie, settings_dict=None, **user_dict):
    """update_user: Updates existing user's profile and settings metadata.

    The attributes in "user_dict" are used to update the user object, and the attributes in
    "settings_dict" are used to create or update the account settings object.
    """
    request_dict = {}
    util.SetIfNotNone(request_dict, 'account_settings', settings_dict)
    request_dict.update(user_dict)

    from viewfinder.backend.www.test.update_user_test import _TestUpdateUser
    _TestUpdateUser(self, user_cookie, request_dict)

  def UpdateUserPhoto(self, user_cookie, photo_id, **up_dict):
    """update_user_photo: Update existing photo's per-user metadata.

    The attributes in "up_dict" are used to update the UserPhoto.
    """
    request_dict = {'photo_id': photo_id}
    request_dict.update(up_dict)

    from viewfinder.backend.www.test.update_user_photo_test import _TestUpdateUserPhoto
    _TestUpdateUserPhoto(self, user_cookie, request_dict)

  def UpdateViewpoint(self, user_cookie, viewpoint_id, act_dict=None, **vp_dict):
    """update_viewpoint: Updates existing viewpoint's metadata.

    The attributes in "vp_dict" are used to update the viewpoint.
    """
    request_dict = {'activity': act_dict or self.CreateActivityDict(user_cookie),
                    'viewpoint_id': viewpoint_id}
    request_dict.update(vp_dict)

    from viewfinder.backend.www.test.update_viewpoint_test import _TestUpdateViewpoint
    _TestUpdateViewpoint(self, user_cookie, request_dict)

  def UploadContacts(self, user_cookie, contacts_dict_list):
    """upload_contacts: uploads new contacts.  Pre-existing contacts that match any of these are untouched."""
    user_id, device_id = self.GetIdsFromCookie(user_cookie)

    request_dict = {'contacts': contacts_dict_list}

    from viewfinder.backend.www.test.upload_contacts_test import _TestUploadContacts
    return _TestUploadContacts(self, user_cookie, request_dict)

  def UploadEpisode(self, user_cookie, ep_dict, ph_dict_list, act_dict=None, add_test_photos=False):
    """upload_episode: Uploads photos to an episode in the user's default
    viewpoint.

    The attributes in "ep_dict" are used to create the episode. The
    episode_id and timestamp are automatically generated if not present.

    The attributes in "ph_dict_list" are used to create each photo in
    the new episode. The photo_id and timestamp are automatically
    generated if not present.

    Returns a tuple of containing the episode and photo ids:
      (episode_id, photo_ids)
    """
    # Generate episode_id (but it can be overridden in ep_dict).
    user_id, device_id = self.GetIdsFromCookie(user_cookie)
    timestamp = ep_dict.get('timestamp', time.time())
    episode_id = ep_dict.get('episode_id', Episode.ConstructEpisodeId(timestamp, device_id, self._test_id))
    self._test_id += 1

    request_dict = {'activity': act_dict or self.CreateActivityDict(user_cookie),
                    'episode': {'episode_id': episode_id,
                                'timestamp': timestamp},
                    'photos': []}
    request_dict['episode'].update(ep_dict)

    for ph_dict in ph_dict_list:
      timestamp = time.time()
      photo_id = Photo.ConstructPhotoId(timestamp, device_id, self._test_id)
      self._test_id += 1
      request_ph_dict = {'photo_id': photo_id,
                         'timestamp': timestamp}
      request_ph_dict.update(ph_dict)
      request_dict['photos'].append(request_ph_dict)

    from viewfinder.backend.www.test.upload_episode_test import _TestUploadEpisode
    response_dict = _TestUploadEpisode(self, user_cookie, request_dict)

    if add_test_photos:
      welcome_path = os.path.join(ResourcesManager.Instance().resources_path, 'welcome')
      with io.open(os.path.join(welcome_path, 'beach_a1_full.jpg'), mode='rb') as f:
        image_data = f.read()

      for ph_dict in ph_dict_list:
        response = self.PutPhotoImage(user_cookie,
                                      episode_id,
                                      ph_dict['photo_id'],
                                      '.f',
                                      image_data,
                                      content_md5=util.ComputeMD5Base64(image_data))
        assert response.code == 200

    return (episode_id, [ph_dict['photo_id'] for ph_dict in response_dict['photos']])


  # =================================================================
  #
  # Helper methods to construct service API request dicts.
  #
  # =================================================================

  def CreateActivityDict(self, user_cookie):
    """Creates an activity dict to be passed to various service methods
    that create an activity. Uses the current time and the next unique
    test id.
    """
    user_id, device_id = self.GetIdsFromCookie(user_cookie)
    timestamp = time.time()
    activity_id = Activity.ConstructActivityId(timestamp, device_id, self._test_id)
    self._test_id += 1
    return {'activity_id': activity_id, 'timestamp': timestamp}

  def CreateContactDicts(self, contacts):
    """Creates a contact dict corresponding to each item in "contacts".
    If a contact is a string, then assumes it is an identity key. If a
    contact is a number, then assumes it is a user id. Otherwise, it
    should already be a contact metadata dict.
    """
    contact_dicts = []
    for contact in contacts:
      if type(contact) in [str, unicode]:
        contact_dicts.append({'identity': contact})
      elif type(contact) in [int, long]:
        contact_dicts.append({'user_id': contact})
      else:
        assert isinstance(contact, dict), contact
        contact_dicts.append(contact)
    return contact_dicts

  def CreateEpisodeSelection(self, episode_id, get_attributes=True, get_photos=True):
    """Creates an episode selection dict."""
    selection = {'episode_id': episode_id}
    util.SetIfNotNone(selection, 'get_attributes', get_attributes)
    util.SetIfNotNone(selection, 'get_photos', get_photos)
    return selection

  def CreateViewpointSelection(self, viewpoint_id, get_attributes=True,
                               get_followers=True, follower_start_key=None,
                               get_activities=True, activity_start_key=None,
                               get_episodes=True, episode_start_key=None,
                               get_comments=True, comment_start_key=None):
    """Creates a viewpoint selection dict."""
    # Put all arguments that need to go into the viewpoint request into a dict.
    kwargs = locals().copy()
    [kwargs.pop(key)
     for key, value in kwargs.items()
     if key in ['self', 'viewpoint_id'] or value is None]

    selection = {'viewpoint_id': viewpoint_id}
    selection.update(kwargs)
    return selection

  def CreateCopyDict(self, user_cookie, existing_episode_id, photo_ids):
    """Creates an episode copy request dict, using the current time and the next unique test
    id. See COPY_EPISODES_METADATA in json_schema.py for a description of the format.
    """
    user_id, device_id = self.GetIdsFromCookie(user_cookie)
    episode_id = Episode.ConstructEpisodeId(time.time(), device_id, self._test_id)
    copy_dict = {'existing_episode_id': existing_episode_id,
                 'new_episode_id': episode_id,
                 'photo_ids': photo_ids}
    self._test_id += 1
    return copy_dict

  def _CreateCopyDictList(self, user_cookie, copy_list):
    """Creates and returns a list of episode copy request dicts.

    "copy_list" is a list containing tuples and/or dicts. Dicts must be in the
    COPY_EPISODES_METADATA format described in json_schema.py. Any tuples in the list must be
    in the following format:
      (existing_ep_id, [ph_id1, ph_id2, ...])

    These tuples are converted into dicts using the current time and next unique test ids.
    """
    copy_dict_list = []
    for copy_item in copy_list:
      if type(copy_item) is tuple:
        existing_episode_id, photo_ids = copy_item
        copy_dict_list.append(self.CreateCopyDict(user_cookie, existing_episode_id, photo_ids))
      else:
        copy_dict_list.append(copy_item)

    return copy_dict_list


  # =================================================================
  #
  # Verified test wrappers for each auth API endpoint.
  #   -- Synchronous for ease of use
  #   -- The interface to Facebook or Google is mocked, with the
  #      contents of "user_dict" returned in lieu of what the real
  #      service would return.
  #   -- If "device_dict" is None, then simulates the web experience;
  #      else simulates the mobile device experience (and will
  #      register the calling device).
  #   -- If "user_cookie" is not None, then simulates case where
  #      calling user is already logged in.
  #   -- Returns a tuple with the registered user and the device id.
  #
  # =================================================================

  def LinkFacebookUser(self, user_dict, device_dict=None, user_cookie=None):
    """link/facebook: Links a Facebook account to an existing Viewfinder
                      account.
    """
    from viewfinder.backend.www.test.auth_facebook_test import _TestAuthFacebookUser
    return _TestAuthFacebookUser('link', self, user_dict, device_dict, user_cookie)

  def LinkGoogleUser(self, user_dict, device_dict=None, user_cookie=None):
    """link/google: Links a Google account to an existing Viewfinder
                    account.
    """
    from viewfinder.backend.www.test.auth_google_test import _TestAuthGoogleUser
    return _TestAuthGoogleUser('link', self, user_dict, device_dict, user_cookie)

  def LinkViewfinderUser(self, user_dict, device_dict=None, user_cookie=None):
    """link/viewfinder: Links an email or SMS identity to an existing Viewfinder account.
    """
    from viewfinder.backend.www.test.auth_viewfinder_test import _TestAuthViewfinderUser
    return _TestAuthViewfinderUser('link', self, user_dict, device_dict, user_cookie)

  def LoginFacebookUser(self, user_dict, device_dict=None, user_cookie=None):
    """login/facebook: Logs into an existing Viewfinder account using
                       an already linked Facebook account.
    """
    from viewfinder.backend.www.test.auth_facebook_test import _TestAuthFacebookUser
    return _TestAuthFacebookUser('login', self, user_dict, device_dict, user_cookie)

  def LoginFakeViewfinderUser(self, user_dict, device_dict=None, user_cookie=None):
    """login/fakeviewfinder: Logs into an existing Viewfinder account.

    This method is faster than LoginViewfinderUser but is less representative of the real
    process.  Use LoginViewfinderUser to test the login process; use LoginFakeViewfinderUser
    when you just need to log in.
    """
    from viewfinder.backend.www.test.auth_viewfinder_test import _TestFakeAuthViewfinderUser
    return _TestFakeAuthViewfinderUser('login', self, user_dict, device_dict, user_cookie)

  def LoginGoogleUser(self, user_dict, device_dict=None, user_cookie=None):
    """login/google: Logs into an existing Viewfinder account using
                     an already linked Google account.
    """
    from viewfinder.backend.www.test.auth_google_test import _TestAuthGoogleUser
    return _TestAuthGoogleUser('login', self, user_dict, device_dict, user_cookie)

  def LoginViewfinderUser(self, user_dict, device_dict=None, user_cookie=None):
    """login/viewfinder: Logs into an existing Viewfinder account using a verified email address.
    """
    from viewfinder.backend.www.test.auth_viewfinder_test import _TestAuthViewfinderUser
    return _TestAuthViewfinderUser('login', self, user_dict, device_dict, user_cookie)

  def LoginResetViewfinderUser(self, user_dict, device_dict=None, user_cookie=None):
    """login_reset/viewfinder: Logs into an existing Viewfinder account using a verified
                               identity, in order to produce a confirmed login cookie that
                               will be used to update the password.
    """
    from viewfinder.backend.www.test.auth_viewfinder_test import _TestAuthViewfinderUser
    return _TestAuthViewfinderUser('login_reset', self, user_dict, device_dict, user_cookie)

  def RegisterFacebookUser(self, user_dict, device_dict=None, user_cookie=None):
    """register/facebook: Registers a new Viewfinder account, linking it
                          to a Facebook account.
    """
    from viewfinder.backend.www.test.auth_facebook_test import _TestAuthFacebookUser
    return _TestAuthFacebookUser('register', self, user_dict, device_dict, user_cookie)

  def RegisterGoogleUser(self, user_dict, device_dict=None, user_cookie=None):
    """register/google: Registers a new Viewfinder account, linking it
                        to a Google account.
    """
    from viewfinder.backend.www.test.auth_google_test import _TestAuthGoogleUser
    return _TestAuthGoogleUser('register', self, user_dict, device_dict, user_cookie)

  def RegisterViewfinderUser(self, user_dict, device_dict=None, user_cookie=None):
    """register/viewfinder: Registers a new Viewfinder account, linking it to a verified email
                            address.
    """
    from viewfinder.backend.www.test.auth_viewfinder_test import _TestAuthViewfinderUser
    return _TestAuthViewfinderUser('register', self, user_dict, device_dict, user_cookie)

  def RegisterFakeViewfinderUser(self, user_dict, device_dict=None, user_cookie=None):
    """register/fakeviewfinder: Registers a new Viewfinder account, linking it to a verified email
                                address.

    This method is faster than RegisterViewfinderUser but is less representative of the real
    process.  Use RegisterViewfinderUser to test the registration process; use RegisterFakeViewfinderUser
    when you just need a user (using this in ServiceBaseTest._CreateTestUsers sped up the test suite
    by ~10%).
    """
    from viewfinder.backend.www.test.auth_viewfinder_test import _TestFakeAuthViewfinderUser
    return _TestFakeAuthViewfinderUser('register', self, user_dict, device_dict, user_cookie)


  # =================================================================
  #
  # Raw unverified access to the service API.
  #
  # =================================================================

  def GetUrl(self, path):
    """Gets full service URL by concatenating "path" to the service URL."""
    return self._svc_url + path

  def SendRequest(self, method, user_cookie, request_dict, version=None):
    """Makes a POST request to the specified service method. If
    version is not None, then does not migrate the version of the
    message -- just uses the "raw" request that was provided. Returns
    the JSON response as a Python dict.
    """
    return self._RunAsync(self.SendRequestAsync, method, user_cookie, request_dict, version=version)

  def SendRequestAsync(self, method, user_cookie, request_dict, callback, version=None):
    """Makes a POST request to the specified service method. If
    version is not None, then does not migrate the version of the
    message -- just uses the "raw" request that was provided. Invokes
    the callback with the JSON response as a Python dict.
    """
    def _OnFetch(response):
      response.rethrow()
      callback(json.loads(response.body))

    # Assume test requests use MAX_SUPPORTED_MESSAGE_VERSION (if "version" not specified) for two reasons:
    #   1. During phase 1 of format changes, the server does not accept messages with MAX_MESSAGE_VERSION,
    #      so tests could not use it anyway.
    #   2. During phase 1, this simulates clients still using the older format, which is good for testing.
    version = message.MAX_SUPPORTED_MESSAGE_VERSION if version is None else version
    request_message = message.Message(request_dict, default_version=version)

    has_op_header = 'op_id' in ServiceHandler.SERVICE_MAP[method].request['properties']['headers']['properties']
    if version >= message.Message.ADD_OP_HEADER_VERSION and has_op_header:
      user_id, device_id = self.GetIdsFromCookie(user_cookie)
      operation_id = Operation.ConstructOperationId(device_id, self._op_id)
      request_message.dict['headers'].setdefault('op_id', operation_id)
      request_message.dict['headers'].setdefault('op_timestamp', util.GetCurrentTimestamp())
      self._op_id += 1

    request_message.dict['headers']['synchronous'] = True

    headers = {'Content-Type': 'application/json',
               'Content-Encoding': 'gzip',
               'X-Xsrftoken': 'fake_xsrf',
               'Cookie': '_xsrf=fake_xsrf'}
    if user_cookie is not None:
      headers['Cookie'] += ';user=%s' % user_cookie

    url = self.GetUrl('/service/%s' % method)
    self.http_client.fetch(url, callback=_OnFetch, method='POST',
                           body=None if request_dict is None else GzipEncode(json.dumps(request_dict)),
                           headers=headers, follow_redirects=False)


  # =================================================================
  #
  # Raw unverified access to photo store API.
  #
  # =================================================================

  def GetPhotoImage(self, user_cookie, episode_id, photo_id, suffix):
    """Sends a GET request to the photo store URL for the specified
    episode and photo. Returns the HTTP response.
    """
    headers = {}
    if user_cookie is not None:
      headers = {'Cookie': 'user=%s' % user_cookie}

    url = self.GetUrl('/episodes/%s/photos/%s%s' % (episode_id, photo_id, suffix))
    return self._RunAsync(self.http_client.fetch, url, method='GET',
                          follow_redirects=True, headers=headers)

  def PutPhotoImage(self, user_cookie, episode_id, photo_id, suffix, image_data,
                    etag=None, content_md5=None):
    """Sends a PUT request to the photo store URL for the specified
    episode and photo. The put request body is set to "image_data".
    Returns the HTTP response.
    """
    headers = {'Content-Type': 'image/jpeg',
               'X-Xsrftoken': 'fake_xsrf',
               'Cookie': '_xsrf=fake_xsrf'}
    if user_cookie is not None:
      headers['Cookie'] += ';user=%s' % user_cookie
    if content_md5 is not None:
      headers['Content-MD5'] = content_md5
    if etag:
      headers['If-None-Match'] = etag

    url = self.GetUrl('/episodes/%s/photos/%s%s' % (episode_id, photo_id, suffix))
    response = self._RunAsync(self.http_client.fetch, url, method='PUT', body='',
                           follow_redirects=False, headers=headers)
    if response.code == 302:
      # Remove the XSRF cookie stuff as it's not used for fileobjstore access.
      headers.pop('X-Xsrftoken')
      cookies = headers.pop('Cookie').split(';')
      if len(cookies) > 1:
        headers['Cookie'] = cookies[1]
      response = self._RunAsync(self.http_client.fetch, response.headers['Location'],
                                method='PUT', body=image_data,
                                follow_redirects=False, headers=headers)
    return response


  # =================================================================
  #
  # Raw unverified access to Admin API.
  #
  # =================================================================

  def SendAdminRequest(self, method, request_dict):
    """Sends an HTTP request to the specified admin service "method" from
    the test-user/test-password admin. Returns the JSON response as a dict.
    """
    otp_cookie_value = OTPEntryHandler._CreateCookie('test-user', time.time())
    otp_cookie = web.create_signed_value(self._secret, basic_auth.COOKIE_NAME, otp_cookie_value)
    headers = {'Content-Type': 'application/json',
               'Cookie': '%s=%s;_xsrf=fake_xsrf' % (basic_auth.COOKIE_NAME, otp_cookie),
               'X-Xsrftoken': 'fake_xsrf'}
    url = self.GetUrl('/admin/service/%s' % method)
    response = self._RunAsync(self.http_client.fetch, url, method='POST',
                              body=None if request_dict is None else json.dumps(request_dict),
                              headers=headers, follow_redirects=False)
    response.rethrow()
    return json.loads(response.body)


  # =================================================================
  #
  # Manage cookies.
  #
  # =================================================================

  def EncodeUserCookie(self, cookie):
    """Json-encodes and signs a user cookie using the service secret."""
    return web.create_signed_value(self._secret, 'user', json.dumps(cookie))

  def DecodeUserCookie(self, cookie):
    """Decodes and json-decodes a user cookie using the service secret, or
    returns None if the cookie could not be decoded.
    """
    value = web.decode_signed_value(self._secret, 'user', cookie)
    return json.loads(value) if value else None

  def GetSecureUserCookie(self, user_id, device_id, user_name, viewpoint_id=None, confirm_time=None):
    """Creates an encoded user cookie containing the given information."""
    cookie = {'user_id': user_id,
              'name': user_name,
              'device_id': device_id,
              'server_version': ServiceTester.SERVER_VERSION}
    util.SetIfNotNone(cookie, 'viewpoint_id', viewpoint_id)
    util.SetIfNotNone(cookie, 'confirm_time', confirm_time)
    return self.EncodeUserCookie(cookie)

  def GetIdsFromCookie(self, user_cookie):
    """Gets the user_id and device_id fields from the encoded cookie."""
    cookie_dict = self.DecodeUserCookie(user_cookie)
    if cookie_dict is None:
      return (None, None)
    return cookie_dict.get('user_id', None), cookie_dict.get('device_id', None)

  def GetCookieFromResponse(self, response):
    """Extracts the user cookie from an HTTP response and returns it if
    it exists, or returns None if not."""
    user_cookie_header_list = [h for h in response.headers.get_list('Set-Cookie') if h.startswith('user=')]
    if not user_cookie_header_list:
      return None
    return re.match(r'user="?([^";]*)', user_cookie_header_list[-1]).group(1)


  # =================================================================
  #
  # Protected helper methods.
  #
  # =================================================================

  def _RunAsync(self, func, *args, **kwargs):
    """Runs an async function which takes a callback argument. Waits for
    the function to complete and returns any result.
    """
    func(callback=self._stop, *args, **kwargs)
    return self._wait()

  def _ValidateAlerts(self):
    """Iterates through the notifications of every user. For every notification that should
    result in an alert, ensures that the alert test service contains a corresponding alert for
    every device that should have been alerted.
    """
    # Group all notifications by user.
    notifications_by_user = defaultdict(list)
    notifications, last_key = self._RunAsync(Notification.Scan, self.validator.client, None)
    for n in notifications:
      notifications_by_user[n.user_id].append(n)

    # Get all emails and SMS messages that have been sent during the test.
    all_emails = TestEmailManager.Instance().emails
    all_sms = TestSMSManager.Instance().phone_numbers

    # Iterate over all notifications for each user.
    for user_id in notifications_by_user.keys():
      # Get user and settings objects.
      user = self._RunAsync(User.Query, self.validator.client, user_id, None)
      settings = self._RunAsync(AccountSettings.KeyQuery,
                                self.validator.client,
                                AccountSettings.ConstructKey(user_id),
                                None)

      # Get list of alerts for each device owned by this user.
      alerts_by_device = dict()
      devices = self._RunAsync(Device.RangeQuery, self.validator.client, user_id, None, None, None)
      for device in devices:
        if device.alert_user_id is not None:
          push_token = device.push_token[len(TestService.PREFIX):]
          alerts_by_device[device] = list(TestService.Instance().GetNotifications(push_token))

      # Get list of emails and SMS messages sent to this user.
      user_emails = all_emails.get(user.email, [])
      user_sms = all_sms.get(user.phone, [])

      # Iterate over each notification and verify that correct alert(s) were issued for it.
      for notify in notifications_by_user[user_id]:
        # Look up activity associated with the notification.
        if notify.activity_id is not None:
          activity = self._RunAsync(Activity.Query,
                                    self.validator.client,
                                    notify.viewpoint_id,
                                    notify.activity_id,
                                    None)

          # Only send add_followers alerts to users that were added to the viewpoint.
          if notify.name == 'add_followers' and user_id not in json.loads(activity.json)['follower_ids']:
            continue

        # Check APNS alerts to user devices.
        if settings.push_alerts != AccountSettings.PUSH_NONE:
          # Don't send op-related alerts to the user that performed the operation.
          if notify.name in ['add_followers', 'post_comment', 'share_existing', 'share_new'] and \
             notify.sender_id != user_id:
            # Ensure that alert was sent for every single device.
            for device, alerts in alerts_by_device.items():
              assert len(alerts) > 0, 'alert for notification "%s" was not sent to device "%s"' % (notify, device)
              alert = alerts.pop(0)
              assert notify.badge == alert['badge'], 'notification "%s" does not match alert "%s"' % (notify, alert)
              assert notify.viewpoint_id == alert['extra']['v'], \
                     'notification "%s" does not match alert "%s"' % (notify, alert)

              # Validate the push alert text.
              viewpoint = self._RunAsync(Viewpoint.Query, self.validator.client, notify.viewpoint_id, None)
              expected_alert_text = self._RunAsync(AlertManager._FormatAlertText,
                                                   self.validator.client,
                                                   viewpoint,
                                                   activity)
              assert alert['alert'] == expected_alert_text, (alert['alert'], expected_alert_text)

          elif notify.name == 'clear_badges':
            # Ensure that alert was sent to all but the sending device.
            for device, alerts in alerts_by_device.items():
              if notify.sender_device_id != device.device_id:
                assert len(alerts) > 0, 'alert for notification "%s" was not sent to device "%s"' % (notify, device)
                alert = alerts.pop(0)

          elif notify.name == 'first register contact':
            # Ensure that alert was sent for every single device.
            for device, alerts in alerts_by_device.items():
              assert len(alerts) > 0, 'alert for notification "%s" was not sent to device "%s"' % (notify, device)
              alert = alerts.pop(0)

              user_name = self._RunAsync(AlertManager._GetNameFromUserId,
                                         self.validator.client,
                                         notify.sender_id,
                                         prefer_given_name=False)
              expected_alert_text = '%s has joined Viewfinder' % user_name
              assert alert['alert'] == expected_alert_text, (alert['alert'], expected_alert_text)

        # Check email alerts.
        if settings.email_alerts != AccountSettings.EMAIL_NONE:
          # Skip past any auth emails.
          for email_args in list(user_emails):
            subject = email_args['subject']
            if 'Activate' in subject or 'Confirm' in subject or 'Reset' in subject or 'Viewfinder Code' in subject:
              user_emails.remove(email_args)

          # Never send emails to the user that performed the operation.
          if notify.name in ['share_new', 'add_followers'] and user.email and notify.sender_id != user_id:
            assert len(user_emails) > 0, 'alert for notification "%s" was not emailed to user %d (%s)' % \
                   (notify, user_id, user.email)
            email_args = user_emails.pop(0)

            # Validate the email args.
            viewpoint = self._RunAsync(Viewpoint.Query, self.validator.client, notify.viewpoint_id, None)
            expected_email_args = self._RunAsync(AlertManager._FormatAlertEmail,
                                                 self.validator.client,
                                                 user_id,
                                                 viewpoint,
                                                 activity)
            assert email_args['subject'] == expected_email_args['subject'], \
                   (email_args['subject'], expected_email_args['subject'])

        # Check SMS alerts.
        if settings.sms_alerts != AccountSettings.SMS_NONE:
          # Skip past any auth sms messages.
          for sms_args in list(user_sms):
            body = sms_args['Body']
            if 'Viewfinder code' in body:
              user_sms.remove(sms_args)

          # Never send SMS messages to the user that performed the operation.
          if notify.name in ['share_new', 'add_followers'] and user.phone and notify.sender_id != user_id:
            assert len(user_sms) > 0, 'alert for notification "%s" was not sent via SMS to user %d (%s)' % \
                   (notify, user_id, user.phone)
            sms_args = user_sms.pop(0)

            # Validate the SMS args.
            viewpoint = self._RunAsync(Viewpoint.Query, self.validator.client, notify.viewpoint_id, None)
            expected_sms_args = self._RunAsync(AlertManager._FormatAlertSMS,
                                               self.validator.client,
                                               user_id,
                                               viewpoint,
                                               activity)
            assert sms_args['To'] == expected_sms_args['number'], (sms_args, expected_sms_args)
            assert sms_args['Body'][:-10] == expected_sms_args['text'][:-10], (sms_args, expected_sms_args)

      # Check for additional alerts that were sent.
      if settings.push_alerts != AccountSettings.PUSH_NONE:
        for device, alerts in alerts_by_device.items():
          assert len(alerts) == 0, 'extra alert "%s" was sent to device "%s" for user %d' % \
                                   (alerts[0], device, user_id)

      if settings.email_alerts != AccountSettings.EMAIL_NONE:
        assert not user_emails, 'extra email was sent to user %d (%s)' % (user_id, user.email)

      if settings.sms_alerts != AccountSettings.SMS_NONE:
        assert not user_sms, 'extra SMS message was sent to user %d (%s)' % (user_id, user.phone)

  def _DeriveNotificationOpDict(self, user_id, device_id, request_dict):
    """Automatically derives an op_dict from a request_dict that was passed
    to a mutable service method. The op_dict can be passed to the various
    notification helper methods.
    """
    return {'op_id': request_dict['headers']['op_id'],
            'op_timestamp': request_dict['headers']['op_timestamp'],
            'user_id': user_id,
            'device_id': device_id}


  # =================================================================
  #
  # Private methods.
  #
  # =================================================================

  def _CompareResponseDicts(self, context, user_id, request_dict, expected_dict, actual_dict):
    """Dump the dicts as sorted JSON and compare."""
    actual_dict = deepcopy(actual_dict)
    actual_dict.pop('headers', None)
    self._RemoveKeys(expected_dict, set(['_version', 'sort_key']))
    exp_json = util.ToCanonicalJSON(expected_dict, indent=True)
    actual_json = util.ToCanonicalJSON(actual_dict, indent=True)
    if exp_json != actual_json:
      request_json = util.ToCanonicalJSON(request_dict, indent=True)
      if len(exp_json) > 1024:
        difference = '\n'.join(difflib.unified_diff(exp_json.split('\n'), actual_json.split('\n'), lineterm=''))
      else:
        difference = 'EXPECTED RESPONSE: %s\n\nACTUAL RESPONSE: %s\n\n' % (exp_json, actual_json)
      raise AssertionError('Difference detected in response.\n\n'
                           '---- %s (user %d) ----\n\nREQUEST: %s\n\n%s' %
                           (context, user_id, request_json, difference))

  def _RemoveKeys(self, item, key_set):
    """Recurse deeply into the item, removing items with a key value
    that is in "key_set".
    """
    if isinstance(item, dict):
      for key, value in item.items():
        if key in key_set:
          del item[key]
        else:
          self._RemoveKeys(value, key_set)
    elif isinstance(item, list):
      for value in item:
        self._RemoveKeys(value, key_set)
