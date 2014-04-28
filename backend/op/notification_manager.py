# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder notification manager.

  The notification manager:

  1. Creates notifications for the various operations. Notifications allow the client to
     incrementally stay in sync with server state as it changes. Each operation triggers zero,
     one, or more notifications. Notifications can be created just for the triggering user, or
     for all friends of the user, or for those who have the user as a contact, etc.

     See the header to notification.py for more information about notifications.

  2. Creates activities for operations that modify viewpoint assets.

  3. Sends push alerts to client devices for operations that require them.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import json
import logging

from tornado import gen
from viewfinder.backend.base import util
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.followed import Followed
from viewfinder.backend.db.notification import Notification
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.settings import AccountSettings


class NotificationManager(object):
  """Viewfinder notification data object.

  Methods on this class may be safely called without acquiring a lock for the notified user.
  This is important, because operations from multiple other users might trigger the concurrent
  creation of notifications for the same user. This class contains race detection and retry
  logic to handle this case.

  Methods on this class assume that an operation is currently in progress and that
  Operation.GetCurrent() will return a valid operation. Various attributes of the notifications
  are based upon the current operation in order to make notification creation idempotent in case
  the operation restarts.

  Tricky cases to consider when making changes:
    - unshare: Can generate notifications on viewpoints to which the current user does not have
               access. This happens when the unshared photo(s) have been reshared.

    - update_follower: Modifies metadata returned by query_viewpoints, but since only follower
                       metadata is affected, no activity is created. This means that the
                       notification viewpoint_id is defined but the activity is not.
  """
  MAX_INLINE_COMMENT_LEN = 512
  """Maximum length of a comment message that will be in-lined in a NotificationManager."""

  _QUERY_LIMIT = 100
  """Maximum number of notifications returned by QuerySince."""

  @classmethod
  @gen.coroutine
  def QuerySince(cls, client, user_id, device_id, start_key, limit=None, scan_forward=True):
    """Queries all notifications intended for 'user_id' with max 'limit' notifications since
    'start_key'. Creates a special "clear_badges" notification once all notifications have been
    queried. This resets the current badge counter and results in the push of an alert to all
    *other* devices so that their badge number can be updated to 0. If 'scan_forward' is false,
    then query in reverse (descending order), and do not set clear_badges.
    """
    from viewfinder.backend.op.alert_manager import AlertManager

    # Use consistent read to ensure that no notifications are skipped.
    limit = NotificationManager._QUERY_LIMIT if limit is None else limit
    notifications = yield gen.Task(Notification.RangeQuery,
                                   client,
                                   hash_key=user_id,
                                   range_desc=None,
                                   limit=limit,
                                   col_names=None,
                                   excl_start_key=start_key,
                                   consistent_read=True,
                                   scan_forward=scan_forward)

    # If all notifications have been queried, get the last notification.
    if len(notifications) < limit and scan_forward:
      if len(notifications) == 0:
        last_notification = yield Notification.QueryLast(client, user_id, consistent_read=True)
      else:
        last_notification = notifications[-1]

      # If all notifications have been queried, add the special "clear_badges" notification.
      if last_notification is None or last_notification.badge == 0:
        raise gen.Return(notifications)

      # If TryClearBadge returns false, then new notifications showed up while the query was running, and so
      # retry creation of the notification. 
      notification_id = last_notification.notification_id + 1 if last_notification else 0
      success = yield Notification.TryClearBadge(client, user_id, device_id, notification_id)
      if not success:
        results = yield NotificationManager.QuerySince(client, user_id, device_id, start_key, scan_forward=scan_forward)
        raise gen.Return(results)

      # Push badge update to any other devices this user owns, but exclude the current device
      # because pushing badge=0 to it is redundant and annoying.
      AlertManager.SendClearBadgesAlert(client, user_id, exclude_device_id=device_id)

    raise gen.Return(notifications)

  @classmethod
  @gen.coroutine
  def NotifyAddFollowers(cls, client, viewpoint_id, existing_followers, new_followers, contact_user_ids,
                         act_dict, timestamp):
    """Notifies the specified followers that they have been added to the specified viewpoint.
    Invalidates the entire viewpoint so that the new follower will load it in its entirety.
    Also notifies all existing followers of the viewpoint that new followers have been added.
    Creates an add_followers activity in the viewpoint.
    """
    # Create activity that includes user ids of all contacts added in the request, even if they were already followers.
    activity_func = NotificationManager._CreateActivityFunc(act_dict, Activity.CreateAddFollowers, contact_user_ids)

    # Invalidate entire viewpoint for new followers, and just the followers list for existing followers.
    new_follower_ids = set(follower.user_id for follower in new_followers)
    def _GetInvalidate(follower_id):
      if follower_id in new_follower_ids:
        return {'viewpoints': [NotificationManager._CreateViewpointInvalidation(viewpoint_id)]}
      else:
        return {'viewpoints': [{'viewpoint_id': viewpoint_id,
                                'get_followers': True}]}

    yield NotificationManager._NotifyFollowers(client,
                                               viewpoint_id,
                                               existing_followers + new_followers,
                                               _GetInvalidate,
                                               activity_func)

  @classmethod
  @gen.coroutine
  def NotifyCreateProspective(cls, client, prospective_identity_keys, timestamp):
    """Sends notifications that the given identities have been linked to new prospective user
    accounts. Sends notifications to all users that have a contact with a matching identity.
    """
    # Invalidate any contacts that may have been bound to a user id.
    yield [NotificationManager._NotifyUsersWithContact(client,
                                                       'create prospective user',
                                                       identity_key,
                                                       timestamp)
           for identity_key in prospective_identity_keys]

  @classmethod
  @gen.coroutine
  def NotifyFetchContacts(cls, client, user_id, timestamp, reload_all):
    """Adds a notification for the specified user that new contacts have been fetched and need
    to be pulled to the client. Invalidates all the newly fetched contacts, which all have
    sort_key greater than "timestamp".
    """
    invalidate = {'contacts': {'start_key': Contact.CreateSortKey(None, 0 if reload_all else timestamp)}}
    if reload_all:
      invalidate['contacts']['all'] = True
    yield NotificationManager.CreateForUser(client, user_id, 'fetch_contacts', invalidate=invalidate)

  @classmethod
  @gen.coroutine
  def NotifyHidePhotos(cls, client, user_id, ep_dicts):
    """Adds a notification for the specified user that photos have been marked as hidden from
    his personal collection. Invalidates all episodes that contain the posts to be hidden. No
    activity is created, since other followers of the affected viewpoint(s) are not affected
    by this action.
    """
    invalidate = {'episodes': [{'episode_id': ep_dict['episode_id'],
                                'get_photos': True} for ep_dict in ep_dicts]}
    yield NotificationManager.CreateForUser(client, user_id, 'hide_photos', invalidate=invalidate)

  @classmethod
  @gen.coroutine
  def NotifyLinkIdentity(cls, client, target_user_id, identity_key, timestamp):
    """Notifies all users referencing any contact having the specified identity that the contact
    has been modified. Invalidates the contact metadata so that the user will re-load it.
    Notifies the new owner of the identity that he needs to refresh his identity list.
    """
    yield NotificationManager._NotifyUsersWithContact(client, 'link identity', identity_key, timestamp)
    yield NotificationManager._NotifyUserInvalidateSelf(client, 'link user', target_user_id)

  @classmethod
  @gen.coroutine
  def NotifyMergeIdentities(cls, client, target_user_id, identity_keys, timestamp):
    """Notifies all users referencing any contact having the specified identity that the contact
    has been modified. Invalidates the contact metadata so that the user will re-load it.
    Notifies all owners of the identities and invalidates their user id. Causes an identity list refresh.
    """
    yield [NotificationManager._NotifyUsersWithContact(client, 'merge identities', identity_key, timestamp)
           for identity_key in identity_keys]
    yield NotificationManager._NotifyUserInvalidateSelf(client, 'merge users', target_user_id)

  @classmethod
  @gen.coroutine
  def NotifyMergeViewpoint(cls, client, viewpoint_id, existing_followers, target_follower,
                           source_user_id, act_dict, timestamp):
    """Notifies the target user that he has been added to the specified viewpoint. Invalidates
    the entire viewpoint so that the target user will load it in its entirety. Also notifies
    all specified existing followers of the viewpoint that a new follower has been added.
    Creates a merge activity in the viewpoint.
    """
    activity_func = NotificationManager._CreateActivityFunc(act_dict,
                                                     Activity.CreateMergeAccounts,
                                                     target_follower.user_id,
                                                     source_user_id)

    # Invalidate entire viewpoint for target_follower, and just the followers list for existing followers.
    def _GetInvalidate(follower_id):
      if follower_id == target_follower.user_id:
        return {'viewpoints': [NotificationManager._CreateViewpointInvalidation(viewpoint_id)]}
      else:
        return {'viewpoints': [{'viewpoint_id': viewpoint_id,
                                'get_followers': True}]}

    yield NotificationManager._NotifyFollowers(client,
                                               viewpoint_id,
                                               existing_followers + [target_follower],
                                               _GetInvalidate,
                                               activity_func)

  @classmethod
  @gen.coroutine
  def NotifyPostComment(cls, client, followers, act_dict, cm_dict):
    """Notifies specified followers that a new comment has been posted to the viewpoint.
    Invalidates this comment and all comments posted in the future by setting the start_key.
    Doing this enables the client to efficiently "stack" comment invalidations by fetching
    all comments beyond the lowest start_key in a single call to query_viewpoints. Creates a
    post_comment activity in the viewpoint.
    """
    from viewfinder.backend.db.comment import Comment

    activity_func = NotificationManager._CreateActivityFunc(act_dict, Activity.CreatePostComment, cm_dict)

    # Construct comment id that will sort before the posted comment and all others with
    # greater timestamps. Only do this if comment will not be in-lined.
    if len(cm_dict['message']) > NotificationManager.MAX_INLINE_COMMENT_LEN:
      start_key = Comment.ConstructCommentId(cm_dict['timestamp'], 0, 0)
      invalidate = {'viewpoints': [{'viewpoint_id': cm_dict['viewpoint_id'],
                                    'get_comments': True,
                                    'comment_start_key': start_key}]}
    else:
      invalidate = None

    yield NotificationManager._NotifyFollowers(client,
                                               cm_dict['viewpoint_id'],
                                               followers,
                                               invalidate,
                                               activity_func,
                                               inc_badge=True)

  @classmethod
  @gen.coroutine
  def NotifyRecordSubscription(cls, client, user_id):
    """Notifies other devices of the user that a new subscriptrion has been recorded and needs
    to be fetched.
    """
    invalidate = {'users': [user_id]}
    yield NotificationManager.CreateForUser(client,
                                            user_id,
                                            'record_subscription',
                                            invalidate=invalidate)

  @classmethod
  @gen.coroutine
  def NotifyRegisterUser(cls, client, user_dict, ident_dict, timestamp, is_first_register, is_linking):
    """Notifies friends and contact owners of the user when one (or several) of the following
    have occurred:

    1. One or more friend-visible user attributes have been updated (such as name).

    2. The user is registering for the first time (i.e. was a prospective user before). In this
       case, "is_first_register" is true.

    3. A new identity has been linked to the user. In this case, "is_linking" is true.

    The user himself is notified since a user always has a friend relationship with himself.
    """
    from viewfinder.backend.op.alert_manager import AlertManager

    if is_first_register or is_linking:
      # Invalidate the contacts of any other users that reference this user. 
      name = 'first register contact' if is_first_register else 'link contact'
      yield NotificationManager._NotifyUsersWithContact(client, name, ident_dict['key'], timestamp)

    # If any user fields were updated then all friends of the user need to be notified of the change.
    if any(attr_name != 'user_id' for attr_name in user_dict.keys()):
      invalidate = {'users': [user_dict['user_id']]}
      yield NotificationManager._NotifyFriends(client, 'register friend', user_dict['user_id'], invalidate)
    elif is_first_register or is_linking:
      # If users with contacts are notified, then also need to notify the user himself. 
      yield NotificationManager._NotifyUserInvalidateSelf(client, 'register friend self', user_dict['user_id'])

    # If user registered for first time, then send alert to all users who have this user as a contact.
    if is_first_register:
      @gen.coroutine
      def _VisitContactUserId(contact_user_id):
        settings = yield gen.Task(AccountSettings.QueryByUser, client, contact_user_id, None)
        yield AlertManager.SendRegisterAlert(client, user_dict['user_id'], contact_user_id, settings)

      yield gen.Task(Contact.VisitContactUserIds, client, ident_dict['key'], _VisitContactUserId)

  @classmethod
  @gen.coroutine
  def NotifyRemoveContacts(cls, client, user_id, timestamp, reload_all):
    """Adds a notification for the specified user that contacts have been removed and need
    to be removed from the client. Invalidates all the newly removed contacts, which all have
    sort_key greater than or equal to "timestamp".
    """
    invalidate = {'contacts': {'start_key': Contact.CreateSortKey(None, 0 if reload_all else timestamp)}}
    if reload_all:
      invalidate['contacts']['all'] = True
    yield NotificationManager.CreateForUser(client, user_id, 'remove_contacts', invalidate=invalidate)

  @classmethod
  @gen.coroutine
  def NotifyRemoveFollowers(cls, client, viewpoint_id, existing_followers, remove_ids, act_dict):
    """Notifies removed followers that they have been removed from the specified viewpoint.
    Invalidates the viewpoint attributes for those followers so that they will get the REMOVED
    label. Also notifies all existing followers of the viewpoint that they need to reload the
    list of viewpoint followers. Creates a remove_followers activity in the viewpoint.
    """
    # Create activity that includes user ids of all users removed in the request, even if they were not followers.
    activity_func = NotificationManager._CreateActivityFunc(act_dict, Activity.CreateRemoveFollowers, remove_ids)

    # Invalidate viewpoint attributes for removed followers, and the followers list for existing followers.
    remove_id_set = set(remove_ids)
    def _GetInvalidate(follower_id):
      if follower_id in remove_id_set:
        return {'viewpoints': [{'viewpoint_id': viewpoint_id,
                                'get_attributes': True}]}
      else:
        return {'viewpoints': [{'viewpoint_id': viewpoint_id,
                                'get_followers': True}]}

    yield NotificationManager._NotifyFollowers(client,
                                               viewpoint_id,
                                               existing_followers,
                                               _GetInvalidate,
                                               activity_func,
                                               always_notify=True)

  @classmethod
  @gen.coroutine
  def NotifyRemovePhotos(cls, client, user_id, ep_dicts):
    """Adds a notification for the specified user that photos have been marked as removed from
    his personal collection. Invalidates all episodes that contain the posts to be removed. No
    activity is created, since other followers of the affected viewpoint(s) are not affected
    by this action.
    """
    invalidate = {'episodes': [{'episode_id': ep_dict['episode_id'],
                                'get_photos': True} for ep_dict in ep_dicts]}
    yield NotificationManager.CreateForUser(client, user_id, 'remove_photos', invalidate=invalidate)

  @classmethod
  @gen.coroutine
  def NotifyRemoveViewpoint(cls, client, user_id, viewpoint_id):
    """Adds a notification for the specified user that a viewpoint have been marked
    as removed from their inbox.  Invalidates all viewpoints that were removed.  No
    activity is created since other followers of the affected viewpoint(s) are not
    affected by this action.
    """
    invalidate = {'viewpoints': [{'viewpoint_id': viewpoint_id,
                                  'get_attributes': True}]}
    yield NotificationManager.CreateForUser(client,
                                            user_id,
                                            'remove_viewpoint',
                                            invalidate=invalidate,
                                            viewpoint_id=viewpoint_id)

  @classmethod
  @gen.coroutine
  def NotifyReviveFollowers(cls, client, viewpoint_id, revive_follower_ids, timestamp):
    """Adds a notification for each of the followers that have been revived. The notification
    invalidates the entire viewpoint in order to force the client to load it in its entirety.
    """
    if len(revive_follower_ids) > 0:
      invalidate = {'viewpoints': [NotificationManager._CreateViewpointInvalidation(viewpoint_id)]}
      yield [NotificationManager.CreateForUser(client,
                                               follower_id,
                                               'revive followers',
                                               invalidate=invalidate,
                                               viewpoint_id=viewpoint_id)
             for follower_id in revive_follower_ids]

  @classmethod
  @gen.coroutine
  def NotifySavePhotos(cls, client, viewpoint_id, follower, act_dict, ep_dicts):
    """Creates notification and activity that new episode(s) have been created in a user's
    default viewpoint and filled with saved photos from other viewpoint(s). Since only the
    owning user follows the default viewpoint, the _NotifyFollowers call will just end up
    creating a notification for a single user. The new episode(s) are invalidated so that
    other devices will load them. Creates a save_photos activity in the viewpoint.
    """
    activity_func = NotificationManager._CreateActivityFunc(act_dict, Activity.CreateSavePhotos, ep_dicts)
    invalidate = {'episodes': [NotificationManager._CreateEpisodeInvalidation(ep_dict['new_episode_id'])
                               for ep_dict in ep_dicts]}
    yield NotificationManager._NotifyFollowers(client, viewpoint_id, [follower], invalidate, activity_func)

  @classmethod
  @gen.coroutine
  def NotifyShareExisting(cls, client, viewpoint_id, followers, act_dict, ep_dicts, viewpoint_updated):
    """Notifies the specified followers of an existing viewpoint that new photos have been
    shared with them. Invalidates all shared episodes. Creates a share activity in the viewpoint.
    """
    activity_func = NotificationManager._CreateActivityFunc(act_dict, Activity.CreateShareExisting, ep_dicts)
    invalidate = {'episodes': [NotificationManager._CreateEpisodeInvalidation(ep_dict['new_episode_id'])
                               for ep_dict in ep_dicts]}
    if viewpoint_updated:
      invalidate['viewpoints'] = [{'viewpoint_id': viewpoint_id,
                                   'get_attributes': True}]
    yield NotificationManager._NotifyFollowers(client,
                                               viewpoint_id,
                                               followers,
                                               invalidate,
                                               activity_func,
                                               inc_badge=True)

  @classmethod
  @gen.coroutine
  def NotifyShareNew(cls, client, vp_dict, followers, contact_user_ids, act_dict, ep_dicts, timestamp):
    """Notifies all followers of a new viewpoint that new photos have been shared with them.
    Invalidates the new viewpoint in its entirety. Notifies the owners of any contacts that
    have been newly registered. Creates a share activity in the viewpoint.
    """
    activity_func = NotificationManager._CreateActivityFunc(act_dict,
                                                     Activity.CreateShareNew,
                                                     ep_dicts,
                                                     contact_user_ids)

    invalidate = {'viewpoints': [NotificationManager._CreateViewpointInvalidation(vp_dict['viewpoint_id'])]}
    yield NotificationManager._NotifyFollowers(client,
                                               vp_dict['viewpoint_id'],
                                               followers,
                                               invalidate,
                                               activity_func,
                                               inc_badge=True)

  @classmethod
  @gen.coroutine
  def NotifyTerminateAccount(cls, client, user_id):
    """Notifies all friends of the specified user, and all users with the terminated user as
    a contact that the account has been terminated.
    """
    invalidate = {'users': [user_id]}
    yield NotificationManager._NotifyFriends(client, 'terminate_account', user_id, invalidate)

  @classmethod
  @gen.coroutine
  def NotifyUnshare(cls, client, viewpoint_id, followers, act_dict, ep_dicts, viewpoint_updated):
    """Notifies all followers of a viewpoint that photos have been unshared from the viewpoint.
    Invalidates all episodes that contain any of the unshared photos. Creates an unshare
    activity in the viewpoint.
    """
    activity_func = NotificationManager._CreateActivityFunc(act_dict, Activity.CreateUnshare, ep_dicts)
    invalidate = {'episodes': [NotificationManager._CreateEpisodeInvalidation(ep_dict['episode_id'])
                               for ep_dict in ep_dicts]}
    if viewpoint_updated:
      invalidate['viewpoints'] = [{'viewpoint_id': viewpoint_id,
                                   'get_attributes': True}]
    yield NotificationManager._NotifyFollowers(client,
                                               viewpoint_id,
                                               followers,
                                               invalidate,
                                               activity_func,
                                               inc_badge=True)

  @classmethod
  @gen.coroutine
  def NotifyUpdateEpisode(cls, client, viewpoint_id, followers, act_dict, ep_dict):
    """Notifies all followers of the specified viewpoint that an episode within the viewpoint
    has been updated. Invalidates the metadata on the episode (but not the photos). Creates an
    update_episode activity in the viewpoint.
    """
    activity_func = NotificationManager._CreateActivityFunc(act_dict, Activity.CreateUpdateEpisode, ep_dict)
    invalidate = {'episodes': [{'episode_id': ep_dict['episode_id'],
                                'get_attributes': True}]}
    yield NotificationManager._NotifyFollowers(client, viewpoint_id, followers, invalidate, activity_func)

  @classmethod
  @gen.coroutine
  def NotifyUpdateFriend(cls, client, friend_dict):
    """Adds a notification for the current user that friend metadata has changed. Since this
    only affects the current user, send invalidations to the current user's devices only.
    """
    invalidate = {'users': [friend_dict['user_id']]}
    yield NotificationManager.CreateForUser(client,
                                            NotificationManager._GetOperation().user_id,
                                            'update_friend',
                                            invalidate=invalidate)

  @classmethod
  @gen.coroutine
  def NotifyUpdateFollower(cls, client, foll_dict):
    """Adds a notification for the current user that follower metadata has changed. Since this
    only affects that user, invalidates the viewpoint metadata only for that user. No activity
    is created, since other followers of the viewpoint are not affected by this action.
    """
    viewpoint_id = foll_dict['viewpoint_id']

    # Do full viewpoint metadata invalidation by default.
    seq_num_pair = None
    invalidate = {'viewpoints': [{'viewpoint_id': viewpoint_id,
                                  'get_attributes': True}]}

    if 'viewed_seq' in foll_dict:
      # In-line the viewed_seq field since it was updated.
      seq_num_pair = (None, foll_dict['viewed_seq'])
      if len(foll_dict) == 2:
        # Only the viewed_seq attribute was updated, so no need to send full invalidation (since it is in-line).
        invalidate = None

    yield NotificationManager.CreateForUser(client,
                                            NotificationManager._GetOperation().user_id,
                                            'update_follower',
                                            invalidate=invalidate,
                                            viewpoint_id=viewpoint_id,
                                            seq_num_pair=seq_num_pair)

  @classmethod
  @gen.coroutine
  def NotifyUpdateUser(cls, client, user_dict, settings_dict, timestamp):
    """Notifies all friends of the specified user that one or more friend-visible attributes
    have been updated (such as name). If only private settings have been updated, only notify
    the user's other devices of the changes.
    """
    user_id = user_dict['user_id']

    if any(attr_name not in ('user_id', 'pwd_hash', 'salt') for attr_name in user_dict.keys()):
      # Public user profile fields were updated, so all friends of the user need to be notified of the change.
      invalidate = {'users': [user_id]}
      yield NotificationManager._NotifyFriends(client, 'update_user', user_dict['user_id'], invalidate)
    else:
      # Notify all of the calling user's devices. 
      invalidate = {'users': [user_dict['user_id']]}
      yield NotificationManager.CreateForUser(client, user_id, 'update_user', invalidate=invalidate)

  @classmethod
  @gen.coroutine
  def NotifyUpdateViewpoint(cls, client, vp_dict, followers, prev_values, act_dict):
    """Notifies all followers of the specified viewpoint that the viewpoint's metadata has
    been updated. "prev_values" contains the old values of title and/or cover photo, if they
    were updated. Invalidates the metadata on the viewpoint.
    """
    activity_func = NotificationManager._CreateActivityFunc(act_dict, Activity.CreateUpdateViewpoint, prev_values)
    invalidate = {'viewpoints': [{'viewpoint_id': vp_dict['viewpoint_id'],
                                  'get_attributes': True}]}
    yield NotificationManager._NotifyFollowers(client, vp_dict['viewpoint_id'], followers, invalidate, activity_func)

  @classmethod
  @gen.coroutine
  def NotifyUnlinkIdentity(cls, client, user_id, identity_key, timestamp):
    """Notifies all users referencing a contact having the specified identity that the contact
    has been modified. Invalidates the contact metadata so that the user will re-load it.
    Also invalidates the user itself, which causes a refresh of the identity list.
    """
    yield NotificationManager._NotifyUsersWithContact(client, 'unlink_identity', identity_key, timestamp)
    yield NotificationManager._NotifyUserInvalidateSelf(client, 'unlink_self', user_id)

  @classmethod
  @gen.coroutine
  def NotifyUploadContacts(cls, client, user_id, timestamp):
    """Adds a notification for the specified user that new contacts have been uploaded/updated and need
    to be pulled to the client. Invalidates all the newly uploaded/updated contacts, which all have
    sort_key greater than or equal to "timestamp".
    """
    invalidate = {'contacts': {'start_key': Contact.CreateSortKey(None, timestamp)}}
    yield NotificationManager.CreateForUser(client, user_id, 'upload_contacts', invalidate=invalidate)

  @classmethod
  @gen.coroutine
  def NotifyUploadEpisode(cls, client, viewpoint_id, follower, act_dict, ep_dict, ph_dicts):
    """Creates notification and activity that a new episode in a user's default viewpoint has
    been created and filled with uploaded photos. Since only the owning user follows the default
    viewpoint, the _NotifyFollowers call will just end up creating a notification for a single
    user. The new episode is invalidated so that other devices will load it. Creates an
    upload_episode activity in the viewpoint.
    """
    activity_func = NotificationManager._CreateActivityFunc(act_dict, Activity.CreateUploadEpisode,
                                                     ep_dict, ph_dicts)
    invalidate = {'episodes': [NotificationManager._CreateEpisodeInvalidation(ep_dict['episode_id'])]}
    yield NotificationManager._NotifyFollowers(client, viewpoint_id, [follower], invalidate, activity_func)

  @classmethod
  def _GetOperation(cls):
    """Gets the current operation, which must be in-scope."""
    operation = Operation.GetCurrent()
    assert operation.operation_id is not None, 'there must be current operation in order to create notification'
    return operation

  @classmethod
  def _CreateActivityFunc(cls, act_dict, create_func, *args):
    """Returns a coroutine with following signature:

      activity_func(client, user_id, viewpoint_id, update_seq)

    When this function is invoked, it executes "create_func", which is one of the constructor
    methods on the Activity class. It invokes the callback with the resulting activity.
    """
    @gen.coroutine
    def _CreateActivity(client, user_id, viewpoint_id, update_seq):
      activity = yield create_func(client,
                                   user_id,
                                   viewpoint_id,
                                   act_dict['activity_id'],
                                   act_dict['timestamp'],
                                   update_seq,
                                   *args)
      raise gen.Return(activity)

    return _CreateActivity

  @classmethod
  def _CreateViewpointInvalidation(cls, viewpoint_id):
    """Create invalidation for entire viewpoint, including all metadata and all collections.

    NOTE: Make sure to update this when new viewpoint collections are added.
    """
    return {'viewpoint_id': viewpoint_id, 'get_attributes': True, 'get_followers': True,
            'get_activities': True, 'get_episodes': True, 'get_comments': True}

  @classmethod
  def _CreateEpisodeInvalidation(cls, episode_id):
    """Create invalidation for entire episode, including all metadata and all collections.

    NOTE: Make sure to update this when new episode collections are added.
    """
    return {'episode_id': episode_id, 'get_attributes': True, 'get_photos': True}

  @classmethod
  @gen.coroutine
  def _NotifyUsersWithContact(cls, client, name, identity_key, timestamp):
    """Adds a notification to all users having contacts with the specified identity. Invalidates
    all contacts added after the specified timestamp.
    """
    @gen.coroutine
    def _VisitContactUserId(contact_user_id):
      yield NotificationManager.CreateForUser(client,
                                              contact_user_id,
                                              name,
                                              invalidate=invalidate)

    invalidate = {'contacts': {'start_key': Contact.CreateSortKey(None, timestamp)}}
    yield gen.Task(Contact.VisitContactUserIds, client, identity_key, _VisitContactUserId)

  @classmethod
  @gen.coroutine
  def _NotifyUserInvalidateSelf(cls, client, name, user_id):
    """Adds a notification for the user with 'user_id'. Invalidates this user to trigger a refresh of
    user information (eg: list of identities).
    """
    yield NotificationManager.CreateForUser(client,
                                            user_id,
                                            name,
                                            invalidate={'users': [user_id]})

  @classmethod
  @gen.coroutine
  def _NotifyFriends(cls, client, name, user_id, invalidate):
    """Adds a notification to all friends of the specified user that one or more friend-visible
    attributes have been updated. Always send the notification to every friend, even if that
    "friend" has blocked the user in question. Also send a notification to the user's other
    devices.
    """
    from viewfinder.backend.db.friend import Friend

    @gen.coroutine
    def _VisitFriend(friend):
      yield NotificationManager.CreateForUser(client,
                                              friend.friend_id,
                                              name,
                                              invalidate=invalidate)

    # Notify each friend as well as the user's other devices.
    yield gen.Task(Friend.VisitRange, client, user_id, None, None, _VisitFriend)

  @classmethod
  @gen.coroutine
  def _NotifyFollowers(cls, client, viewpoint_id, followers, invalidate, activity_func,
                       inc_badge=False, always_notify=False):
    """Adds a notification for each of the given followers that the specified viewpoint has
    structurally changed. If "invalidate" is a dict, then uses that directly. Otherwise, assumes
    it's a function that takes a follower id and returns the invalidate dict for that follower.
    If "always_notify" is true, then always send notifications, even to removed followers.

    In order to minimize undesirable client artifacts caused by reads of half-committed data,
    we will commit updates in this order:

    1. In parallel:
       a. Create the activity.
       b. Update all Followed records (of all followers in the viewpoint).

    2. In parallel:
       a. Update update_seq in the viewpoint.
       b. Update viewed_seq in the sending follower.

    3. In parallel:
       a. For each follower:
          i. Create notification
          ii. Send alert
    """
    from viewfinder.backend.db.viewpoint import Viewpoint
    from viewfinder.backend.op.alert_manager import AlertManager

    # Get the current operation, which provides the calling user and the op timestamp.
    operation = NotificationManager._GetOperation()

    @gen.coroutine
    def _NotifyOneFollower(viewpoint, seq_num_pair, activity, follower, follower_settings):
      """Creates a notification for the follower and sends an alert if configured to do so."""
      # If follower has been removed, do not send notifications or alerts to it.
      if follower.IsRemoved() and not always_notify:
        return

      # Get the invalidate dict.
      if invalidate is None or isinstance(invalidate, dict):
        foll_invalidate = invalidate
      else:
        foll_invalidate = invalidate(follower.user_id)

      # Don't send alert or increment badge for the user that is creating the activity and
      # sending the NotificationManager.
      is_sending_user = follower.user_id == operation.user_id

      # Create the notification for the follower.
      # Update the Followed index, which orders viewpoints by timestamp of last update.
      notification = yield Notification.CreateForUser(client,
                                                      operation,
                                                      follower.user_id,
                                                      activity.name,
                                                      invalidate=foll_invalidate,
                                                      activity_id=activity.activity_id,
                                                      viewpoint_id=viewpoint_id,
                                                      seq_num_pair=seq_num_pair,
                                                      inc_badge=inc_badge and not is_sending_user)

      if not is_sending_user:
        yield AlertManager.SendFollowerAlert(client,
                                             follower.user_id,
                                             notification.badge,
                                             viewpoint,
                                             follower,
                                             follower_settings,
                                             activity)

    # We want a locked viewpoint while updating its sequence numbers and the corresponding Followed rows.
    # Locking also prevents race conditions where new followers are added during iteration.
    Viewpoint.AssertViewpointLockAcquired(viewpoint_id)

    # Get affected viewpoint and the follower sending the notification, if it's available.
    viewpoint = yield gen.Task(Viewpoint.Query, client, viewpoint_id, None)
    sending_follower = next((follower for follower in followers if follower.user_id == operation.user_id), None)

    # Update the viewpoint and follower sequence numbers, but do not commit until after Followed
    # records are updated (since we're updating the viewpoint's "last_updated" at that time anyway).
    viewpoint.update_seq += 1
    if sending_follower is not None:
      sending_follower.viewed_seq += 1
      seq_num_pair = (viewpoint.update_seq, sending_follower.viewed_seq)
    else:
      seq_num_pair = (viewpoint.update_seq, None)

    # Create the activity.
    activity_task = activity_func(client, operation.user_id, viewpoint_id, viewpoint.update_seq)

    # Get account settings for each follower in order to determine what level of alerts they'd like.
    follower_keys = [AccountSettings.ConstructKey(follower.user_id) for follower in followers]
    settings_task = gen.Task(AccountSettings.BatchQuery, client, follower_keys, None, must_exist=False)

    # Update all Followed records.
    followed_task = gen.Multi([gen.Task(Followed.UpdateDateUpdated,
                                        client,
                                        follower.user_id,
                                        viewpoint_id,
                                        viewpoint.last_updated,
                                        operation.timestamp)
                               for follower in followers])

    activity, all_follower_settings, _ = yield [activity_task, settings_task, followed_task]

    # Now that the Followed records have been updated, update the viewpoint's "last_updated" attribute.
    # This must be done afterwards so that the previous value of last_updated is known, even if the
    # operation fails and restarts.
    if operation.timestamp > viewpoint.last_updated:
      viewpoint.last_updated = operation.timestamp

    # Commit changes to update_seq and the sending follower's viewed_seq.
    yield [gen.Task(viewpoint.Update, client),
           gen.Task(sending_follower.Update, client) if sending_follower is not None else util.GenConstant(None)]

    # Visit each follower and generate notifications and alerts for it.
    yield [_NotifyOneFollower(viewpoint, seq_num_pair, activity, follower, follower_settings)
           for follower, follower_settings in zip(followers, all_follower_settings)]

  @classmethod
  @gen.coroutine
  def CreateForUser(cls, client, user_id, name, invalidate=None,
                    activity_id=None, viewpoint_id=None, seq_num_pair=None,
                    inc_badge=False, consistent_read=False):
    """Calls Notification.CreateForUser with the current operation."""
    operation = NotificationManager._GetOperation()
    notification = yield Notification.CreateForUser(client,
                                                    operation,
                                                    user_id,
                                                    name,
                                                    invalidate,
                                                    activity_id,
                                                    viewpoint_id,
                                                    seq_num_pair,
                                                    inc_badge,
                                                    consistent_read)
    raise gen.Return(notification)
