# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Handler for Viewfinder service RPCs.

  - ServiceHandler: web request handler for REST API.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import base64
import logging
import json
import time
import toro
import validictory

from copy import deepcopy
from functools import partial
from tornado import gen, web
from tornado.ioloop import IOLoop
from viewfinder.backend.base import constants, counters, handler, secrets, util
from viewfinder.backend.base.message import Message, MIN_SUPPORTED_MESSAGE_VERSION, MAX_SUPPORTED_MESSAGE_VERSION
from viewfinder.backend.base.message import REQUIRED_MIGRATORS, INLINE_INVALIDATIONS, INLINE_COMMENTS
from viewfinder.backend.base.message import EXTRACT_FILE_SIZES, EXTRACT_ASSET_KEYS, SPLIT_NAMES, EXPLICIT_SHARE_ORDER
from viewfinder.backend.base.message import SUPPRESS_BLANK_COVER_PHOTO, SUPPORT_MULTIPLE_IDENTITIES_PER_CONTACT
from viewfinder.backend.base.message import RENAME_PHOTO_LABEL, SUPPORT_REMOVED_FOLLOWERS, SUPPRESS_COPY_TIMESTAMP
from viewfinder.backend.base.message import SUPPORT_CONTACT_LIMITS, SUPPRESS_EMPTY_TITLE
from viewfinder.backend.base.exceptions import InvalidRequestError, PermissionError
from viewfinder.backend.db import db_client
from viewfinder.backend.db.accounting import Accounting
from viewfinder.backend.db.activity import Activity
from viewfinder.backend.db.asset_id import IdPrefix
from viewfinder.backend.db.comment import Comment
from viewfinder.backend.db.client_log import ClientLog
from viewfinder.backend.db.contact import Contact
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.followed import Followed
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.subscription import Subscription
from viewfinder.backend.db.user import User
from viewfinder.backend.db.user_photo import UserPhoto
from viewfinder.backend.db.user_post import UserPost
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.notification_manager import NotificationManager
from viewfinder.backend.resources.calendar import Calendar
from viewfinder.backend.resources.message.error_messages import INVALID_JSON_REQUEST, MERGE_COOKIE_NOT_CONFIRMED
from viewfinder.backend.resources.message.error_messages import MISSING_MERGE_SOURCE, UNSUPPORTED_ASSET_TYPE
from viewfinder.backend.resources.message.error_messages import UPDATE_PWD_NOT_CONFIRMED, IDENTITY_NOT_CANONICAL
from viewfinder.backend.services.itunes_store import ITunesStoreClient, VerifyResponse
from viewfinder.backend.www import base, json_schema, password_util, photo_store, www_util


# Counter which tracks average time per request.  All request types are considered.
# A single snapshot of this value is not interesting, but historical data can be used
# to track the usage of resources on a machine.
_avg_req_time = counters.define_average('viewfinder.service.avg_req_time', 'Average seconds per client request.')
_req_per_min = counters.define_rate('viewfinder.service.req_per_min', 'Average # of client requests per minute.', 60)
_fail_per_min = counters.define_rate('viewfinder.service.fail_per_min', 'Average # of failed client requests per minute.', 60)


@gen.coroutine
def AddFollowers(client, obj_store, user_id, device_id, request):
  """Add resolved contacts as followers of an existing viewpoint."""
  request['user_id'] = user_id
  yield Activity.VerifyActivityId(client, user_id, device_id, request['activity']['activity_id'])

  # Validate contact identities.
  _ValidateContacts(request['contacts'])

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'AddFollowersOperation.Execute',
                 request)

  logging.info('ADD FOLLOWERS: user: %d, device: %d, %d contacts' %
               (user_id, device_id, len(request['contacts'])))

  raise gen.Return({})


@gen.coroutine
def AllocateIds(client, obj_store, user_id, device_id, request):
  """Allocates an asset id for the current device.  The request should include the asset id prefix
  for the requested type.  Currently, only comment, activity and operation ids are supported.
  """
  prefixes = request['asset_types']
  timestamp = util.GetCurrentTimestamp()

  def ValidateId(prefix):
    """Validate a single requested Id"""
    if not IdPrefix.IsValid(prefix):
      raise InvalidRequestError(UNSUPPORTED_ASSET_TYPE, asset_type=prefix)

    # Among valid prefixes, only Activity, Comment and Operation are supported.
    if not prefix in 'acop':
      raise InvalidRequestError(UNSUPPORTED_ASSET_TYPE, asset_type=IdPrefix.GetAssetName(prefix))

  def ConstructId(prefix, uniquifier):
    if prefix == 'a':
      asset_id = Activity.ConstructActivityId(timestamp, device_id, uniquifier)
    elif prefix == 'c':
      asset_id = Comment.ConstructCommentId(timestamp, device_id, uniquifier)
    elif prefix == 'p':
      asset_id = Photo.ConstructPhotoId(timestamp, device_id, uniquifier)
    else:
      asset_id = Operation.ConstructOperationId(device_id, uniquifier)

    return asset_id

  for prefix in prefixes:
    ValidateId(prefix)

  # AllocateAssetIds returns a unique, increasing number which can be used as a unique component of asset ids.
  unique_start = yield gen.Task(User.AllocateAssetIds, client, user_id, len(prefixes))

  asset_ids = [ConstructId(p, u) for p, u in zip(prefixes, range(unique_start, unique_start + len(prefixes)))]
  raise gen.Return({'asset_ids': asset_ids, 'timestamp': timestamp})


@gen.coroutine
def BuildArchive(client, obj_store, user_id, device_id, request):
  """Request the service to build a zip file of all of a users conversations and associated photos.
  Once the zip has been stored to S3, an email will be mailed to the user with a signed S3 url which
  will expire after 24 hours.
  """
  request['user_id'] = user_id

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 0,  # All build archive requests serialize on lock for user 0.
                 device_id,
                 'BuildArchiveOperation.Execute',
                 request)

  logging.info('BUILD ARCHIVE: user: %d, device: %d' % (user_id, device_id))

  raise gen.Return({})

def GetCalendar(client, obj_store, user_id, device_id, request, callback):
  """Queries calendar(s) for the user for the specified year."""
  def _OnQueryUser(user):
    calendars = request['calendars']
    response = {'calendars': []}
    for cal in calendars:
      if cal['calendar_id'] == 'holidays':
        cal_data = Calendar.GetHolidaysByLocale(user.locale)
      else:
        cal_data = Calendar.GetCalendar(cal['calendar_id'])
      response['calendars'].append({'calendar_id': cal_data.calendar_id,
                                    'year': cal['year'],
                                    'events': cal_data.GetEvents(year=cal['year'])})
    logging.info('GET CALENDAR: user: %d, device: %d, %d calendars, event counts: %s' %
                 (user_id, device_id,
                  len(calendars), dict([(c['calendar_id'], len(c['events'])) \
                                          for c in response['calendars']])))
    callback(response)

  # Query the user's locale.
  User.Query(client, user_id, None, _OnQueryUser)


@gen.coroutine
def HidePhotos(client, obj_store, user_id, device_id, request):
  """Hides photos from a user's personal library and inbox view. To be more precise, *posts*
  are marked as removed. This means that if a photo has been shared with a user multiple times,
  every instance of that photo (i.e. post) should be marked as hidden.
  """
  request['user_id'] = user_id
  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'HidePhotosOperation.Execute',
                 request)

  num_photos = sum(len(ep_dict['photo_ids']) for ep_dict in request['episodes'])
  logging.info('HIDE PHOTOS: user: %d, device: %d, %d photos' %
               (user_id, device_id, num_photos))

  raise gen.Return({})


@gen.coroutine
def ListIdentities(client, obj_store, user_id, device_id, request):
  """Returns a list of identities linked to this account."""
  def _MakeIdentityDict(ident):
    i_dict = {'identity': ident.key}
    if ident.authority is not None:
      i_dict['authority'] = ident.authority
    return i_dict

  query_expr = 'identity.user_id=%d' % user_id
  identities = yield gen.Task(Identity.IndexQuery, client, query_expr, ['key', 'authority'])

  raise gen.Return({'identities': [_MakeIdentityDict(ident) for ident in identities]})


@gen.coroutine
def MergeAccounts(client, obj_store, user_id, device_id, request):
  """Merges assets from the user account given in the request into the account of the current
  user.
  """
  yield Activity.VerifyActivityId(client, user_id, device_id, request['activity']['activity_id'])

  source_user_cookie = request.pop('source_user_cookie', None)
  if source_user_cookie is not None:
    # Decode the cookie for the source account to merge.
    merge_cookie = web.decode_signed_value(secrets.GetSecret('cookie_secret'),
                                           base._USER_COOKIE_NAME,
                                           source_user_cookie,
                                           base._USER_COOKIE_EXPIRES_DAYS)
    if merge_cookie is None:
      raise web.HTTPError(403, 'The source_user_cookie value is not valid.')

    source_user_dict = json.loads(merge_cookie)
    source_user_id = source_user_dict['user_id']

    # Source user cookie must be confirmed in order to merge it.
    if not www_util.IsConfirmedCookie(source_user_dict.get('confirm_time', None)):
      raise PermissionError(MERGE_COOKIE_NOT_CONFIRMED, user_id=source_user_id)
  else:
    source_identity_dict = request.pop('source_identity', None)
    if source_identity_dict is None:
      raise InvalidRequestError(MISSING_MERGE_SOURCE)

    identity = yield Identity.VerifyConfirmedIdentity(client,
                                                      source_identity_dict['identity'],
                                                      source_identity_dict['access_token'])
    source_user_id = identity.user_id

  if source_user_id is not None:
    if source_user_id == user_id:
      raise web.HTTPError(400, 'Cannot merge a user account into itself.')

    source_user = yield gen.Task(User.Query, client, source_user_id, None)
    if source_user.IsTerminated():
      raise web.HTTPError(400, 'Cannot merge a terminated user account.')

    request['source_user_id'] = source_user_id
    request['target_user_id'] = user_id
    yield gen.Task(Operation.CreateAndExecute,
                   client,
                   user_id,
                   device_id,
                   'MergeAccountsOperation.Execute',
                   request)
  else:
    request.pop('activity')
    request['source_identity_key'] = identity.key
    request['target_user_id'] = user_id
    yield gen.Task(Operation.CreateAndExecute,
                   client,
                   user_id,
                   device_id,
                   'LinkIdentityOperation.Execute',
                   request)

  logging.info('MERGE ACCOUNTS: user: %d, device: %d, source: %s' %
               (user_id, device_id, source_user_id or identity.key))

  raise gen.Return({})


def NewClientLogUrl(client, obj_store, user_id, device_id, request, callback):
  """Gets an S3 PUT URL for clients to write mobile device logs."""
  kwargs = {'user_id': user_id,
            'device_id': device_id,
            'timestamp': request['timestamp'],
            'client_log_id': request['client_log_id']}
  if 'content_type' in request:
    kwargs['content_type'] = request['content_type']
  if 'content_md5' in request:
    kwargs['content_md5'] = request['content_md5']
  if 'num_bytes' in request:
    kwargs['max_bytes'] = request['num_bytes']

  logging.info('GET NEW CLIENT LOG URL: user: %d, device: %d, client log id: %s' %
                 (user_id, device_id, request['client_log_id']))
  response = {'client_log_put_url': ClientLog.GetPutUrl(**kwargs)}
  callback(response)


@gen.coroutine
def OldRemovePhotos(client, obj_store, user_id, device_id, request):
  """Used by older clients to remove photos from showing in a user's personal library. Unlike
  the new remove_photos, photos can be removed from shared viewpoints as well as the default
  viewpoint. Photos are hidden in shared viewpoints, and removed from the default viewpoint.
  """
  remove_episodes = []
  hide_episodes = []
  for ep_dict in request['episodes']:
    episode = yield gen.Task(Episode.Query, client, ep_dict['episode_id'], None, must_exist=False)
    if episode is None or episode.viewpoint_id == base.ViewfinderContext.current().user.private_vp_id:
      # Episodes from the user's default viewpoint should be removed.
      remove_episodes.append(ep_dict)
    else:
      # Episodes from other viewpoints should be hidden.
      hide_episodes.append(ep_dict)

  hide_request = deepcopy(request)
  if len(hide_episodes) > 0:
    hide_request['episodes'] = hide_episodes
    yield HidePhotos(client, obj_store, user_id, device_id, hide_request)

  remove_request = deepcopy(request)
  remove_request['episodes'] = remove_episodes
  yield RemovePhotos(client, obj_store, user_id, device_id, remove_request)

  raise gen.Return({})


@gen.coroutine
def PostComment(client, obj_store, user_id, device_id, request):
  """Adds a new comment to an existing viewpoint."""
  headers = request.pop('headers')
  activity = request.pop('activity')
  viewpoint_id = request['viewpoint_id']

  yield Activity.VerifyActivityId(client, user_id, device_id, activity['activity_id'])
  yield Comment.VerifyCommentId(client, user_id, device_id, request['comment_id'])

  request = {'headers': headers,
             'user_id': user_id,
             'activity': activity,
             'comment': request}

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'PostCommentOperation.Execute',
                 request)

  logging.info('POST COMMENT: user: %d, device: %d, viewpoint: %s' %
               (user_id, device_id, viewpoint_id))
  raise gen.Return({})


@gen.coroutine
def QueryContacts(client, obj_store, user_id, device_id, request):
  """Queries contacts for the current user.
  Note: This does not remove duplicate contact entries.  This isn't practical because multiple
  contacts with the same contact_id may be present across multiple range query results.  Multiple
  contacts with the same contact_id should be very uncommon, but are possible.  Because older
  contact rows are returned first, the client may assume the last contact with the same contact_id
  is the correct one."""
  def _MakeContactDict(contact):
    """Makes a dict for JSON output from the contact."""
    c_dict = {'contact_id': contact.contact_id,
              'contact_source': contact.contact_source}
    util.SetIfNotNone(c_dict, 'name', contact.name)
    util.SetIfNotNone(c_dict, 'given_name', contact.given_name)
    util.SetIfNotNone(c_dict, 'family_name', contact.family_name)
    util.SetIfNotNone(c_dict, 'rank', contact.rank)
    if contact.labels is not None and len(contact.labels) > 0:
      c_dict['labels'] = list(contact.labels)
    identities_list = []
    if contact.identities_properties is not None:
      for identity_properties in contact.identities_properties:
        identity_key = identity_properties[0]
        identity_dict = {'identity': identity_key}
        util.SetIfNotNone(identity_dict, 'description', identity_properties[1])
        util.SetIfNotNone(identity_dict, 'user_id', identity_key_to_user_id_map[Identity.Canonicalize(identity_key)])
        identities_list.append(identity_dict)
      c_dict['identities'] = identities_list
    return c_dict

  start_key = request.get('start_key', None)
  limit = request.get('limit', None)

  contacts = yield gen.Task(Contact.RangeQuery,
                            client,
                            hash_key=user_id,
                            range_desc=None,
                            limit=limit,
                            col_names=None,
                            excl_start_key=start_key,
                            scan_forward=True)

  # Get corresponding identities.
  identity_keys = list({identity for co in contacts for identity in co.identities})
  identity_dbkeys = [db_client.DBKey(identity_key, None) for identity_key in identity_keys]
  identities = yield gen.Task(Identity.BatchQuery, client, identity_dbkeys, None, must_exist=False)
  user_ids = [identity.user_id if identity is not None else None for identity in identities]
  identity_key_to_user_id_map = dict(zip(identity_keys, user_ids))

  # Formulates the contacts list into a dict for JSON output.
  response = {'num_contacts': len(contacts),
              'contacts': [_MakeContactDict(co) for co in contacts]}
  if contacts:
    response['last_key'] = contacts[-1].sort_key

  logging.info('QUERY CONTACTS: user: %d, device: %d, %d contacts, start key %s, last key %s' %
               (user_id, device_id, response['num_contacts'], start_key, response.get('last_key', 'None')))

  raise gen.Return(response)


@gen.engine
def QueryEpisodes(client, obj_store, user_id, device_id, request, callback):
  """Queries posts from the specified episodes.
  """
  def _MakePhotoDict(post, photo, user_post, user_photo):
    ph_dict = photo.MakeMetadataDict(post, user_post, user_photo)

    # Do not return access URLs for posts which have been removed.
    if not post.IsRemoved():
      _AddPhotoUrls(obj_store, ph_dict)

    return ph_dict

  limit = request.get('photo_limit', None)

  # Get all requested episodes, along with posts for each episode.
  episode_keys = [db_client.DBKey(ep_dict['episode_id'], None) for ep_dict in request['episodes']]

  post_tasks = []
  for ep_dict in request['episodes']:
    if ep_dict.get('get_photos', False):
      post_tasks.append(gen.Task(Post.RangeQuery, client, ep_dict['episode_id'], None, limit,
                                 None, excl_start_key=ep_dict.get('photo_start_key', None)))
    else:
      post_tasks.append(util.GenConstant(None))

  episodes, posts_list = yield [gen.Task(Episode.BatchQuery, client, episode_keys, None, must_exist=False),
                                gen.Multi(post_tasks)]

  # Get viewpoint records for all viewpoints containing episodes.
  viewpoint_keys = [db_client.DBKey(viewpoint_id, None)
                    for viewpoint_id in set(ep.viewpoint_id for ep in episodes if ep is not None)]

  # Get follower records for all viewpoints containing episodes, along with photo and user post objects.
  follower_keys = [db_client.DBKey(user_id, db_key.hash_key) for db_key in viewpoint_keys]

  all_posts = [post for posts in posts_list if posts is not None for post in posts]
  photo_keys = [db_client.DBKey(post.photo_id, None) for post in all_posts]
  user_post_keys = [db_client.DBKey(user_id, Post.ConstructPostId(post.episode_id, post.photo_id))
                    for post in all_posts]
  if user_id:
    # TODO(ben): we can probably skip this for the web view
    user_photo_task = gen.Task(UserPhoto.BatchQuery, client,
                               [db_client.DBKey(user_id, post.photo_id) for post in all_posts],
                               None, must_exist=False)
  else:
    user_photo_task = util.GenConstant(None)

  viewpoints, followers, photos, user_posts, user_photos = yield [
    gen.Task(Viewpoint.BatchQuery, client, viewpoint_keys, None, must_exist=False),
    gen.Task(Follower.BatchQuery, client, follower_keys, None, must_exist=False),
    gen.Task(Photo.BatchQuery, client, photo_keys, None),
    gen.Task(UserPost.BatchQuery, client, user_post_keys, None, must_exist=False),
    user_photo_task,
    ]

  # Get set of viewpoint ids to which the current user has access.
  viewable_viewpoint_ids = set(viewpoint.viewpoint_id for viewpoint, follower in zip(viewpoints, followers)
                               if _CanViewViewpointContent(viewpoint, follower))

  response_dict = {'episodes': []}
  num_photos = 0

  for ep_dict, episode, posts in zip(request['episodes'], episodes, posts_list):
    # Gather list of (post, photo, user_post) tuples for this episode.
    photo_info_list = []
    if ep_dict.get('get_photos', False):
      for post in posts:
        photo = photos.pop(0)
        user_post = user_posts.pop(0)
        user_photo = user_photos.pop(0) if user_photos is not None else None
        assert photo.photo_id == post.photo_id, (episode, post, photo)
        if user_photo:
          assert user_photo.photo_id == photo.photo_id
          assert user_photo.user_id == user_id
        photo_info_list.append((post, photo, user_post, user_photo))

    if episode is not None and episode.viewpoint_id in viewable_viewpoint_ids:
      response_ep_dict = {'episode_id': ep_dict['episode_id']}

      # Only return episode metadata if "get_attributes" is True.
      if ep_dict.get('get_attributes', False):
        response_ep_dict.update(episode._asdict())

      # Only return photos if "get_photos" is True.
      if ep_dict.get('get_photos', False):
        response_ep_dict['photos'] = [_MakePhotoDict(photo, post, user_post, user_photo)
                                      for photo, post, user_post, user_photo in photo_info_list]
        if len(photo_info_list) > 0:
          response_ep_dict['last_key'] = photo_info_list[-1][0].photo_id
          num_photos += len(photo_info_list)

      response_dict['episodes'].append(response_ep_dict)

  logging.info('QUERY EPISODES: user: %d, device: %d, %d episodes, %d photos' %
               (user_id, device_id, len(response_dict['episodes']), num_photos))

  callback(response_dict)


@gen.coroutine
def QueryFollowed(client, obj_store, user_id, device_id, request):
  """Queries all viewpoints followed by the current user. Supports a limit and a start key
  for pagination.
  """
  start_key = request.get('start_key', None)
  limit = request.get('limit', None)

  followed = yield gen.Task(Followed.RangeQuery,
                            client,
                            hash_key=user_id,
                            range_desc=None,
                            limit=limit,
                            col_names=['viewpoint_id'],
                            excl_start_key=start_key)

  # Get the viewpoint associated with each follower object.
  last_key = followed[-1].sort_key if len(followed) > 0 else None

  viewpoint_keys = [db_client.DBKey(f.viewpoint_id, None) for f in followed]
  follower_keys = [db_client.DBKey(user_id, f.viewpoint_id) for f in followed]
  viewpoints, followers = yield [gen.Task(Viewpoint.BatchQuery, client, viewpoint_keys, None, must_exist=False),
                                 gen.Task(Follower.BatchQuery, client, follower_keys, None, must_exist=False)]

  # Formulate the viewpoints list into a dict for JSON output.
  # NOTE: If we ever add content to the viewpoint data being returned here, filtering out that content
  #       if the requester doesn't have view access to it should be considered.
  response = {'viewpoints': [_MakeViewpointMetadataDict(v, f, obj_store)
                             for v, f in zip(viewpoints, followers)
                             if v is not None]}
  util.SetIfNotNone(response, 'last_key', last_key)

  logging.info('QUERY FOLLOWED: user: %d, device: %d, %d viewpoints, start key %s, last key %s' %
               (user_id, device_id, len(response['viewpoints']), start_key,
                response.get('last_key', 'None')))

  raise gen.Return(response)

@gen.coroutine
def QueryNotifications(client, obj_store, user_id, device_id, request):
  """Queries a list of pending notifications for a user since the last
  request.
  """
  # Clients are not allowed to request long polling for more than this duration.
  MAX_LONG_POLL = 300
  # Within our fake long polling, poll the database this often.
  LONG_POLL_INTERVAL = 5

  start_key = int(request.get('start_key')) if 'start_key' in request else None
  limit = request.get('limit', None)
  scan_forward = request.get('scan_forward', True)
  max_long_poll = min(int(request.get('max_long_poll', 0)),
                      MAX_LONG_POLL)
  if max_long_poll > 0:
    deadline = IOLoop.current().time() + max_long_poll
  else:
    deadline = None

  while True:
    notifications = yield NotificationManager.QuerySince(client,
                                                         user_id,
                                                         device_id,
                                                         start_key,
                                                         limit=limit,
                                                         scan_forward=scan_forward)
    if len(notifications) > 0 or deadline is None:
      break

    now = IOLoop.current().time()
    next_try = now + LONG_POLL_INTERVAL
    if next_try >= deadline:
      # No point in scheduling a query after we expect our client to go away.
      break

    vf_context = base.ViewfinderContext.current()
    assert vf_context.connection_close_event is not None
    try:
      yield vf_context.connection_close_event.wait(next_try)
    except toro.Timeout:
      # The close event timed out, meaning the client is still connected
      # and it's time to try again.
      pass
    else:
      # The close event triggered without timing out, so give up.
      assert vf_context.connection_close_event.is_set()
      break

  # At this point we either have non-empty results, the client is not
  # in long-polling mode, the long-polling deadline has expired, or
  # the client has disconnected. We could short-circuit in the latter
  # case, but it doesn't hurt to go ahead and generate the empty
  # result.

  # Get any activities that are associated with the notifications in a single batch query.
  activity_keys = [db_client.DBKey(n.viewpoint_id, n.activity_id)
                   for n in notifications
                   if n.activity_id is not None]
  activities = yield gen.Task(Activity.BatchQuery, client, activity_keys, None)

  response = {'notifications': []}
  if len(notifications) > 0:
    response['last_key'] = www_util.FormatIntegralLastKey(notifications[-1].notification_id)

  for notification in notifications:
    notification_dict = {'notification_id': notification.notification_id,
                         'name': notification.name,
                         'sender_id': notification.sender_id,
                         'timestamp': notification.timestamp}

    util.SetIfNotNone(notification_dict, 'op_id', notification.op_id)

    invalidate = notification.GetInvalidate()
    util.SetIfNotNone(notification_dict, 'invalidate', invalidate)

    # If the operation modified a viewpoint's update_seq or viewed_seq values, in-line them.
    if notification.update_seq is not None or notification.viewed_seq is not None:
      vp_dict = notification_dict.setdefault('inline', {}).setdefault('viewpoint', {})
      vp_dict['viewpoint_id'] = notification.viewpoint_id
      if notification.update_seq is not None:
        vp_dict['update_seq'] = notification.update_seq
      if notification.viewed_seq is not None:
        vp_dict['viewed_seq'] = notification.viewed_seq

    # If the operation added an activity, in-line it.
    if notification.activity_id is not None:
      activity = activities.pop(0)

      # Project all activity columns, but nest the json column underneath a key called activity.name.
      activity_dict = activity.MakeMetadataDict()
      notification_dict.setdefault('inline', {})['activity'] = activity_dict

      # If this was a post_comment notification, in-line the comment metadata if no invalidation exists.
      # NOTE: If/when we allow unfollowing viewpoints, permissions would have to be checked to ensure that
      #       the calling user is still a follower of the viewpoint containing the comment.
      if activity.name == 'post_comment' and notification.invalidate is None:
        comment_id = activity_dict['post_comment']['comment_id']
        comment = yield gen.Task(Comment.Query, client, notification.viewpoint_id, comment_id, col_names=None)
        notification_dict['inline']['comment'] = comment._asdict()

    response['notifications'].append(notification_dict)

  if len(response['notifications']) > 0:
    # Query usage data and inline it into the last notification in the response.
    def _AccountingAsDict(act):
      if act is None:
        return None
      act_dict = act._asdict()
      act_dict.pop('hash_key', None)
      act_dict.pop('sort_key', None)
      act_dict.pop('op_ids', None)
      return act_dict

    owned, shared, visible = yield gen.Task(Accounting.QueryUserAccounting, client, user_id)
    usage_dict = {}
    util.SetIfNotNone(usage_dict, 'owned_by', _AccountingAsDict(owned))
    util.SetIfNotNone(usage_dict, 'shared_by', _AccountingAsDict(shared))
    util.SetIfNotNone(usage_dict, 'visible_to', _AccountingAsDict(visible))
    if len(usage_dict.keys()) > 0:
      # This notification may not have an inline field.
      last_notification = response['notifications'][-1]
      last_notification.setdefault('inline', {})['user'] = { 'usage': usage_dict }

  num_uploads = len([a for a in activities if a is not None and a.name == 'upload_episode'])
  num_shares = len([a for a in activities if a is not None and a.name in ['share_existing', 'share_new']])
  num_unshares = len([a for a in activities if a is not None and a.name == 'unshare'])
  num_comment_posts = len([a for a in activities if a is not None and a.name == 'post_comment'])
  logging.info('QUERY NOTIFICATIONS: user: %d, device: %d, start_key: %r, count: %d, '
               '%d uploads, %d shares, %d unshares, %d comment posts' %
               (user_id, device_id, start_key, len(notifications), num_uploads, num_shares,
                num_unshares, num_comment_posts))

  # Disable notification responses for older clients.
  if request['headers']['original_version'] < Message.UPDATE_SHARE_VERSION:
    raise gen.Return({'notifications': []})
  else:
    raise gen.Return(response)


@gen.coroutine
def QueryUsers(client, obj_store, user_id, device_id, request):
  """Queries users by user id, filtering by friendships."""
  user_friend_list = yield gen.Task(User.QueryUsers, client, user_id, request['user_ids'])
  user_dicts = yield [gen.Task(user.MakeUserMetadataDict, client, user_id, forward_friend, reverse_friend)
                      for user, forward_friend, reverse_friend in user_friend_list]

  response = {'users': user_dicts}
  logging.info('QUERY USERS: user: %d, device: %d, %d users' %
               (user_id, device_id, len(user_dicts)))
  raise gen.Return(response)


@gen.coroutine
def QueryViewpoints(client, obj_store, user_id, device_id, request):
  """Queries viewpoint metadata, as well as associated followers and episodes.
  """
  @gen.coroutine
  def _QueryFollowers():
    """Produces list of (followers, last_key) tuples, one for each viewpoint in the request."""
    tasks = []
    for vp_dict in request['viewpoints']:
      if vp_dict.get('get_followers', False):
        start_key = vp_dict.get('follower_start_key', None)
        tasks.append(Viewpoint.QueryFollowers(client,
                                              vp_dict['viewpoint_id'],
                                              excl_start_key=int(start_key) if start_key is not None else None,
                                              limit=limit))
      else:
        tasks.append(util.GenConstant(None))

    follower_results = yield tasks
    raise gen.Return(follower_results)

  @gen.coroutine
  def _QueryActivities():
    """Produces list of (activities, last_key) tuples, one for each viewpoint in the request."""
    tasks = []
    for vp_dict in request['viewpoints']:
      if vp_dict.get('get_activities', False):
        tasks.append(gen.Task(Viewpoint.QueryActivities, client, vp_dict['viewpoint_id'],
                              excl_start_key=vp_dict.get('activity_start_key', None),
                              limit=limit))
      else:
        tasks.append(util.GenConstant(None))

    activity_results = yield tasks
    raise gen.Return(activity_results)

  @gen.coroutine
  def _QueryEpisodes():
    """Produces list of (episodes, last_key) tuples, one for each viewpoint in the request."""
    tasks = []
    for vp_dict in request['viewpoints']:
      if vp_dict.get('get_episodes', False):
        tasks.append(gen.Task(Viewpoint.QueryEpisodes, client, vp_dict['viewpoint_id'],
                              excl_start_key=vp_dict.get('episode_start_key', None),
                              limit=limit))
      else:
        tasks.append(util.GenConstant(None))

    episode_results = yield tasks
    raise gen.Return(episode_results)

  @gen.coroutine
  def _QueryComments():
    """Produces list of (comments, last_key) tuples, one for each viewpoint in the request."""
    tasks = []
    for vp_dict in request['viewpoints']:
      if vp_dict.get('get_comments', False):
        tasks.append(gen.Task(Viewpoint.QueryComments, client, vp_dict['viewpoint_id'],
                              excl_start_key=vp_dict.get('comment_start_key', None),
                              limit=limit))
      else:
        tasks.append(util.GenConstant(None))

    comment_results = yield tasks
    raise gen.Return(comment_results)

  limit = request.get('limit', None)
  viewpoint_keys = [db_client.DBKey(vp_dict['viewpoint_id'], None) for vp_dict in request['viewpoints']]
  follower_keys = [db_client.DBKey(user_id, vp_dict['viewpoint_id']) for vp_dict in request['viewpoints']]

  results = yield [gen.Task(Viewpoint.BatchQuery, client, viewpoint_keys, None, must_exist=False),
                   gen.Task(Follower.BatchQuery, client, follower_keys, None, must_exist=False),
                   _QueryFollowers(),
                   _QueryActivities(),
                   _QueryEpisodes(),
                   _QueryComments()]

  viewpoints, followers, follower_id_results, activity_results, episode_results, comment_results = results
  zip_list = zip(request['viewpoints'], viewpoints, followers, follower_id_results, activity_results,
                 episode_results, comment_results)

  num_followers = 0
  num_activities = 0
  num_episodes = 0
  num_comments = 0
  response_vp_dicts = []
  for vp_dict, viewpoint, follower, follower_result, activity_result, episode_result, comment_result in zip_list:
    # Only return the viewpoint metadata if the caller is a follower of the viewpoint.
    if follower is not None:
      response_vp_dict = {'viewpoint_id': viewpoint.viewpoint_id}

      # Only return viewpoint metadata if "get_attributes" is True.
      if vp_dict.get('get_attributes', False):
        response_vp_dict.update(_MakeViewpointMetadataDict(viewpoint, follower, obj_store))

      # Only return followers if the follower is not removed and "get_followers" is True.
      if not follower.IsRemoved() and vp_dict.get('get_followers', False):
        followers, last_key = follower_result
        response_vp_dict['followers'] = [foll.MakeFriendMetadataDict() for foll in followers]
        if last_key is not None:
          response_vp_dict['follower_last_key'] = www_util.FormatIntegralLastKey(last_key)
        num_followers += len(followers)

      # Only return content about viewpoint if follower is allowed to view it.
      if _CanViewViewpointContent(viewpoint, follower):
        # Only return activities if "get_activities" is True.
        if vp_dict.get('get_activities', False):
          activities, last_key = activity_result
          response_vp_dict['activities'] = [act.MakeMetadataDict() for act in activities]
          if last_key is not None:
            response_vp_dict['activity_last_key'] = last_key
          num_activities += len(activities)

        # Only return episodes if "get_episodes" is True.
        if vp_dict.get('get_episodes', False):
          episodes, last_key = episode_result
          response_vp_dict['episodes'] = [ep._asdict() for ep in episodes]
          if last_key is not None:
            response_vp_dict['episode_last_key'] = last_key
          num_episodes += len(episodes)

        # Only return comments if "get_comments" is True.
        if vp_dict.get('get_comments', False):
          comments, last_key = comment_result
          response_vp_dict['comments'] = [co._asdict() for co in comments]
          if last_key is not None:
            response_vp_dict['comment_last_key'] = last_key
          num_comments += len(comments)

      response_vp_dicts.append(response_vp_dict)

  logging.info('QUERY VIEWPOINTS: user: %d, device: %d, %d viewpoints, %d followers, '
               '%d activities, %d episodes, %d comments' %
               (user_id, device_id, len(response_vp_dicts), num_followers,
                num_activities, num_episodes, num_comments))

  raise gen.Return({'viewpoints': response_vp_dicts})


def RecordSubscription(client, obj_store, user_id, device_id, request, callback):
  """Records an external subscription."""
  def _OnRecord(verify_response, op):
    callback({'subscription': Subscription.CreateFromITunes(user_id, verify_response).MakeMetadataDict()})

  def _OnVerify(environment, verify_response):
    if (environment == 'prod' and
        verify_response.GetStatus() == VerifyResponse.SANDBOX_ON_PROD_ERROR):
      ITunesStoreClient.Instance('dev').VerifyReceipt(receipt_data, partial(_OnVerify, 'dev'))
      return

    if not verify_response.IsValid():
      logging.warning('record_subscription: invalid signature; request: %r', request)
      raise web.HTTPError(400, 'invalid receipt signature')

    if environment == 'prod':
      op_request = {
        'headers': request['headers'],
        'user_id': user_id,
        'verify_response_str': verify_response.ToString(),
        }
      Operation.CreateAndExecute(client, user_id, device_id,
                                 'Subscription.RecordITunesTransactionOperation',
                                 op_request, partial(_OnRecord, verify_response))
    else:
      # Accept sandbox receipts, but do not record them.  This is required
      # for app store approval (reviewers will attempt to subscribe with
      # sandbox accounts and we must not return an error).
      callback({'subscription': Subscription.CreateFromITunes(user_id, verify_response).MakeMetadataDict()})

  receipt_data = base64.b64decode(request['receipt_data'])

  # We must support both prod and sandbox itunes instances:  Even release
  # builds will use the sandbox when the app is under review.  There is no
  # (supported) way for an app to know whether a receipt is from a prod
  # or sandbox purchase until we attempt to verify the signature.  Apple
  # recommends always trying prod first, and falling back to sandbox
  # upon receiving an appropriate error code.
  # https://developer.apple.com/library/ios/#technotes/tn2259/_index.html#//apple_ref/doc/uid/DTS40009578-CH1-FREQUENTLY_ASKED_QUESTIONS
  ITunesStoreClient.Instance('prod').VerifyReceipt(receipt_data, partial(_OnVerify, 'prod'))


@gen.coroutine
def RemoveContacts(client, obj_store, user_id, device_id, request):
  """Remove contacts."""
  request['user_id'] = user_id
  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'RemoveContactsOperation.Execute',
                 request)

  logging.info('REMOVE CONTACTS: user: %d, device: %d, contact_count: %d' %
               (user_id, device_id, len(request['contacts'])))
  raise gen.Return({})


@gen.coroutine
def RemoveFollowers(client, obj_store, user_id, device_id, request):
  """Remove followers of an existing viewpoint."""
  request['user_id'] = user_id
  yield Activity.VerifyActivityId(client, user_id, device_id, request['activity']['activity_id'])

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'RemoveFollowersOperation.Execute',
                 request)

  logging.info('REMOVE FOLLOWERS: user: %d, device: %d, %d followers' %
               (user_id, device_id, len(request['remove_ids'])))

  raise gen.Return({})


@gen.coroutine
def RemovePhotos(client, obj_store, user_id, device_id, request):
  """Removes photos from a user's personal library. To be more precise, *posts* are marked as
  removed. This means that if a photo has been uploaded or saved to the library multiple times,
  every instance of that photo (i.e. post) should be marked as removed.
  """
  request['user_id'] = user_id
  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'RemovePhotosOperation.Execute',
                 request)

  num_photos = sum(len(ep_dict['photo_ids']) for ep_dict in request['episodes'])
  logging.info('REMOVE PHOTOS: user: %d, device: %d, %d photos' %
               (user_id, device_id, num_photos))

  raise gen.Return({})


@gen.coroutine
def RemoveViewpoint(client, obj_store, user_id, device_id, request):
  """Remove a viewpoint from a user's inbox."""

  request['user_id'] = user_id
  viewpoint_id = request['viewpoint_id']

  # Check that the user isn't trying to remove their default viewpoint.  We do it here
  # because it saves us a query for user during the operation and the default viewpoint id
  # can't change.
  if base.ViewfinderContext.current().user.private_vp_id == viewpoint_id:
    raise PermissionError('User is not allowed to remove their default viewpoint: %s' % viewpoint_id)

  yield gen.Task(Operation.CreateAndExecute, client, user_id, device_id, 'RemoveViewpointOperation.Execute', request)

  logging.info('REMOVE VIEWPOINT: user: %d, device: %d, viewpoint: %s' % (user_id, device_id, viewpoint_id))

  raise gen.Return({})


@gen.coroutine
def ResolveContacts(client, obj_store, user_id, device_id, request):
  """Resolves contact identities to user ids."""
  ident_tasks = []
  for ident in request['identities']:
    # Validate identity key.
    Identity.ValidateKey(ident)

    if ident.startswith(('Email:', 'Phone:')):
      # Only allow email addresses and phone numbers to be resolved through this interface.  Other
      # identity types (e.g. FacebookGraph) are denser and could be exhaustively enumerated, and
      # there is little use in allowing users to enter them directly.
      ident_tasks.append(gen.Task(Identity.Query, client, ident, None, must_exist=False))
    else:
      ident_tasks.append(util.GenConstant(None))

  ident_results = yield ident_tasks

  user_tasks = []
  for ident in ident_results:
    if ident is not None and ident.user_id is not None:
      user_tasks.append(gen.Task(User.Query, client, ident.user_id, None, must_exist=False))
    else:
      user_tasks.append(util.GenConstant(None))

  user_results = yield user_tasks

  results = []
  for request_ident, ident, user in zip(request['identities'], ident_results, user_results):
    result_contact = {'identity': request_ident}
    if user is not None:
      assert ident is not None and user.user_id == ident.user_id
      assert ident.key == request_ident
      result_contact['user_id'] = ident.user_id
      util.SetIfNotNone(result_contact, 'name', user.name)
      util.SetIfNotNone(result_contact, 'given_name', user.given_name)
      util.SetIfNotNone(result_contact, 'family_name', user.family_name)
      result_contact['labels'] = user.MakeLabelList(False)
    results.append(result_contact)

  raise gen.Return({'contacts': results})


@gen.coroutine
def SavePhotos(client, obj_store, user_id, device_id, request):
  """Saves photos from existing episodes to new episodes in the current user's default
  viewpoint. This is used to implement the "save photos to library" functionality.
  """
  request['user_id'] = user_id

  yield Activity.VerifyActivityId(client, user_id, device_id, request['activity']['activity_id'])

  vp_ids = request.get('viewpoint_ids', [])
  ep_dicts = request.get('episodes', [])
  num_photos = 0
  for ep_dict in ep_dicts:
    yield Episode.VerifyEpisodeId(client, user_id, device_id, ep_dict['new_episode_id'])
    num_photos += len(ep_dict['photo_ids'])

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'SavePhotosOperation.Execute',
                 request)

  logging.info('SAVE PHOTOS: user: %d, device: %d, %d viewpoints, %d episodes, %d photos' %
               (user_id, device_id, len(vp_ids), len(ep_dicts), num_photos))

  raise gen.Return({})


@gen.coroutine
def ShareExisting(client, obj_store, user_id, device_id, request):
  """Shares photos from existing episodes with the followers of an existing viewpoint."""
  request['user_id'] = user_id

  yield Activity.VerifyActivityId(client, user_id, device_id, request['activity']['activity_id'])

  num_photos = 0
  for ep_dict in request['episodes']:
    yield Episode.VerifyEpisodeId(client, user_id, device_id, ep_dict['new_episode_id'])
    num_photos += len(ep_dict['photo_ids'])

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'ShareExistingOperation.Execute',
                 request)

  logging.info('SHARE EXISTING: user: %d, device: %d, viewpoint: %s, %d episodes, %d photos' %
               (user_id, device_id, request['viewpoint_id'], len(request['episodes']), num_photos))

  raise gen.Return({})


@gen.coroutine
def ShareNew(client, obj_store, user_id, device_id, request):
  """Shares a list of photos with each of a list of contacts, specified
  by a contact identity key or a viewfinder user id. Creates a new
  viewpoint and episodes, with the contacts as followers.
  """
  request['user_id'] = user_id

  yield Activity.VerifyActivityId(client, user_id, device_id, request['activity']['activity_id'])

  vp_dict = request['viewpoint']
  yield Viewpoint.VerifyViewpointId(client, user_id, device_id, vp_dict['viewpoint_id'])

  num_photos = 0
  for ep_dict in request['episodes']:
    yield Episode.VerifyEpisodeId(client, user_id, device_id, ep_dict['new_episode_id'])
    num_photos += len(ep_dict['photo_ids'])

  # Validate contact identities.
  _ValidateContacts(request['contacts'])

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'ShareNewOperation.Execute',
                 request)

  logging.info('SHARE NEW: user: %d, device: %d, viewpoint: %s, %d episodes, %d photos' %
               (user_id, device_id, vp_dict['viewpoint_id'], len(request['episodes']),
                num_photos))

  raise gen.Return({})


@gen.coroutine
def TerminateAccount(client, obj_store, user_id, device_id, request):
  """Terminate the calling user's account. Unlink all identities from the
  user, mute all device alerts, and disable all sharing.
  """
  request['user_id'] = user_id
  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'User.TerminateAccountOperation',
                 request)

  logging.info('TERMINATE ACCOUNT: user: %d, device: %d' % (user_id, device_id))
  raise gen.Return({})


@gen.coroutine
def UnlinkIdentity(client, obj_store, user_id, device_id, request):
  """Unlink an existing identity from the requesting account."""
  # Validate identity key.
  Identity.ValidateKey(request['identity'])

  unlink_ident = yield gen.Task(Identity.Query, client, request['identity'], None, must_exist=False)

  # If the identity is missing, then assume unlink is being re-called, and do a no-op. If the
  # user_id does not match, raise a permission error. Otherwise, if request is for an authorized
  # id, we must query to ensure this won't be last one remaining.
  if unlink_ident is not None:
    if unlink_ident.user_id != user_id:
      raise PermissionError('Identity "%s" not linked to this account' % request['identity'])

    if unlink_ident.authority is not None:
      query_expr = 'identity.user_id=%d' % user_id
      all_identities = yield gen.Task(Identity.IndexQuery, client, query_expr, ['key', 'authority'])

      # Verify there is at least one identity remaining with an authority.
      if not any([one_identity.authority is not None and one_identity.key != unlink_ident.key
                  for one_identity in all_identities]):
        raise PermissionError('Removing this identity authorized by %s, would leave you '
                              'with no way to access your account' % unlink_ident.authority)

    request['user_id'] = user_id
    yield gen.Task(Operation.CreateAndExecute,
                   client,
                   user_id,
                   device_id,
                   'Identity.UnlinkIdentityOperation',
                   request)

  logging.info('IDENTITY UNLINK: user: %d, device: %d, identity: %s' %
               (user_id, device_id, request['identity']))
  raise gen.Return({})


@gen.coroutine
def Unshare(client, obj_store, user_id, device_id, request):
  """Unshares photos from the episodes in the specified viewpoint, as
  well as from all derived episodes to which the photos were shared.
  """
  yield Activity.VerifyActivityId(client, user_id, device_id, request['activity']['activity_id'])

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'UnshareOperation.Execute',
                 request)

  logging.info('UNSHARE: user: %d, device: %d, viewpoint: %s, %d episodes, %d photos' %
               (user_id, device_id, request['viewpoint_id'], len(request['episodes']),
                sum([len(ep_dict['photo_ids']) for ep_dict in request['episodes']])))
  raise gen.Return({})


@gen.coroutine
def UpdateDevice(client, obj_store, user_id, device_id, request):
  """Updates the device metadata. Sets a new secure client access cookie.
  """
  device_dict = request['device_dict']
  if device_dict.has_key('device_id') and device_dict['device_id'] != device_id:
    raise web.HTTPError(400, 'bad auth cookie; device id mismatch %d != %d' %
                        (device_dict['device_id'], device_id))

  request['user_id'] = user_id
  request['device_id'] = device_id
  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'Device.UpdateOperation',
                 request)

  logging.info('UPDATE DEVICE: user: %d, device: %d' % (user_id, device_id))
  raise gen.Return({})


@gen.coroutine
def UpdateEpisode(client, obj_store, user_id, device_id, request):
  """Updates episode metadata."""
  yield Activity.VerifyActivityId(client, user_id, device_id, request['activity']['activity_id'])

  headers = request.pop('headers')
  activity = request.pop('activity')

  request = {'headers': headers,
             'user_id': user_id,
             'activity': activity,
             'episode': request}

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'UpdateEpisodeOperation.Execute',
                 request)

  logging.info('UPDATE EPISODE: user: %d, device: %d, episode: %s' %
               (user_id, device_id, request['episode']['episode_id']))

  raise gen.Return({})


@gen.coroutine
def UpdateFollower(client, obj_store, user_id, device_id, request):
  """Updates follower metadata."""
  request['user_id'] = user_id

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'UpdateFollowerOperation.Execute',
                 request)

  logging.info('UPDATE FOLLOWER: user: %d, device: %d, viewpoint: %s' %
               (user_id, device_id, request['follower']['viewpoint_id']))
  raise gen.Return({})


@gen.coroutine
def UpdateFriend(client, obj_store, user_id, device_id, request):
  """Updates friend metadata."""
  request['user_id'] = user_id

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'Friend.UpdateOperation',
                 request)

  logging.info('UPDATE FRIEND: user: %d, device: %d, friend: %s' %
               (user_id, device_id, request['friend']['user_id']))
  raise gen.Return({})


@gen.coroutine
def UpdatePhoto(client, obj_store, user_id, device_id, request):
  """Updates photo metadata."""
  request['user_id'] = user_id

  # If activity header is required, then expect it to have device_id from cookie.
  if request['headers']['original_version'] >= Message.ADD_OP_HEADER_VERSION:
    yield Activity.VerifyActivityId(client, user_id, device_id, request['activity']['activity_id'])
  else:
    yield Activity.VerifyActivityId(client, user_id, 0, request['activity']['activity_id'])

  request = {'headers': request.pop('headers'),
             'act_dict': request.pop('activity'),
             'ph_dict': request}

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'Photo.UpdateOperation',
                 request)

  logging.info('UPDATE PHOTO: user: %d, device: %d, photo: %s' %
               (user_id, device_id, request['ph_dict']['photo_id']))
  raise gen.Return({})


@gen.coroutine
def UpdateUser(client, obj_store, user_id, device_id, request):
  """Updates user profile and settings metadata."""
  password = request.pop('password', None)
  if password is not None:
    context = base.ViewfinderContext.current()

    user = context.user
    old_password = request.pop('old_password', None)

    # Recently confirmed cookies can always set the password -- this is how we do password resets.
    if not context.IsConfirmedUser():
      # Cookie is not confirmed, so raise an error unless one of the following is true:
      #   1. The old_password field is set and matches the user's current password.
      #   2. The user currently has no password. 
      if old_password is None and user.pwd_hash is not None:
        raise PermissionError(UPDATE_PWD_NOT_CONFIRMED)

      if user.pwd_hash is not None:
        yield password_util.ValidateUserPassword(client, user, old_password)

    # Replace password with generated hash and salt.
    pwd_hash, salt = password_util.GeneratePasswordHash(password)
    request['pwd_hash'] = pwd_hash
    request['salt'] = salt

  request = {'headers': request.pop('headers'),
             'user_dict': request,
             'settings_dict': request.pop('account_settings', None)}
  request['user_dict']['user_id'] = user_id

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'User.UpdateOperation',
                 request)

  logging.info('UPDATE USER: user: %d, device: %d' % (user_id, device_id))
  raise gen.Return({})


@gen.coroutine
def UpdateUserPhoto(client, obj_store, user_id, device_id, request):
  op_request = {'headers': request.pop('headers'),
                'up_dict': request}
  op_request['up_dict']['user_id'] = user_id
  yield gen.Task(Operation.CreateAndExecute, client, user_id, device_id, 'UserPhoto.UpdateOperation', op_request)
  logging.info('UPDATE USER PHOTO: user: %d, device:%d, photo:%s' %
               (user_id, device_id, op_request['up_dict']['photo_id']))
  raise gen.Return({})


@gen.coroutine
def UpdateViewpoint(client, obj_store, user_id, device_id, request):
  """Updates viewpoint metadata."""
  yield Activity.VerifyActivityId(client, user_id, device_id, request['activity']['activity_id'])

  headers = request.pop('headers')
  activity = request.pop('activity')
  viewpoint_id = request['viewpoint_id']

  # We need to preserve backwards-compatibility with old clients that use update_viewpoint in
  # order to make changes to follower attributes. 
  follower_columns = Follower._table.GetColumnNames()
  viewpoint_columns = Viewpoint._table.GetColumnNames()
  if all(attr in follower_columns for attr in request.keys()):
    request = {'headers': headers,
               'user_id': user_id,
               'follower': request}

    yield gen.Task(Operation.CreateAndExecute,
                   client,
                   user_id,
                   device_id,
                   'UpdateFollowerOperation.Execute',
                   request)
  elif all(attr in viewpoint_columns for attr in request.keys()):
    request = {'headers': headers,
               'user_id': user_id,
               'activity': activity,
               'viewpoint': request}

    yield gen.Task(Operation.CreateAndExecute,
                   client,
                   user_id,
                   device_id,
                   'UpdateViewpointOperation.Execute',
                   request)
  else:
    raise web.HTTPError(400, 'Viewpoint and follower attributes cannot be updated together ' +
                             'in the same call to update_viewpoint.')

  logging.info('UPDATE VIEWPOINT: user: %d, device: %d, viewpoint: %s' %
               (user_id, device_id, viewpoint_id))
  raise gen.Return({})


@gen.coroutine
def UploadContacts(client, obj_store, user_id, device_id, request):
  """Creates/updates contacts metadata."""
  request['user_id'] = user_id
  contact_count = len(request['contacts'])

  # Pre-process each contact and generate contact_id list to return as result.
  result_contact_ids = []
  for contact in request['contacts']:
    canon_identities = set()
    identities_properties = []
    for contact_identity in contact['identities']:
      identity_key = contact_identity['identity']
      description = contact_identity.get('description', None)

      if identity_key != Identity.Canonicalize(identity_key):
        raise InvalidRequestError(IDENTITY_NOT_CANONICAL, identity_key=identity_key)

      canon_identities.add(identity_key)

      # Build identities_properties in the form that's expected for creating a contact.
      identities_properties.append((identity_key, description))

    # Set 'identities' and 'identities_properties' as is expected for creating the contact.
    contact['identities'] = list(canon_identities)
    contact['identities_properties'] = identities_properties

    # Now, calculated the contact_id.
    contact['contact_id'] = Contact.CalculateContactId(contact)

    # Add contact_id to result list.
    result_contact_ids.append(contact['contact_id'])

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'UploadContactsOperation.Execute',
                 request)

  logging.info('UPLOAD CONTACTS: user: %d, device: %d, contact_count: %d' % (user_id, device_id, contact_count))
  raise gen.Return({'contact_ids': result_contact_ids})


@gen.coroutine
def UploadEpisode(client, obj_store, user_id, device_id, request):
  """Creates metadata for new photos and returns URLs where the client
  should upload the photo images. Creates a new episode to group the
  photos or adds the photos to an existing episode.
  """
  def _GenerateUploadUrl(obj_store, ph_dict, suffix, md5_attr):
    """Create an S3 URL that is the target of a photo upload. "suffix" is
    appended to the end of the photo id in order to distinguish different
    photo sizes. The value of the "md5_attr" attribute is converted to a
    base-64 encoded value for the HTTP Content-MD5 header. Using this
    attribute ensures that the user uploads a photo that exactly matches
    the MD5, and also enables detection of any bit corruption on the wire.
    """
    md5_hex = ph_dict[md5_attr]
    try:
      # Convert MD5 encoded as a hex string to base-64 string.
      content_md5 = base64.b64encode(md5_hex.decode('hex'))
    except TypeError:
      raise InvalidRequestError('md5 value "%s" is invalid; it must be in ascii hex format' % md5_hex)

    return obj_store.GenerateUploadUrl('%s%s' % (ph_dict['photo_id'], suffix),
                                       content_type=ph_dict.get('content_type', 'image/jpeg'),
                                       content_md5=content_md5)

  @gen.coroutine
  def _VerifyAttributeUpdate(photo, suffix, attr_name, new_value):
    """Checks whether the specified photo metadata attribute is about
    to be modified. Don't allow the change if the photo image data has
    already been uploaded to S3. This check prevents situations where
    photo MD5 values are updated after the initial upload, which could
    allow a user to overwrite an existing photo in order to bypass the
    7-day unshare rule. But it still allows cases where a new MD5 was
    generated by the client as part of a rebuild.
    """
    existing_value = getattr(photo, attr_name)
    if new_value != existing_value:
      # Existing attribute value does not match, so only allow it to be updated if the image data
      # has not yet been uploaded.
      etag = yield gen.Task(Photo.IsImageUploaded, obj_store, photo.photo_id, suffix)
      if etag is not None:
        raise PermissionError('cannot overwrite existing photo "%s" with a new photo' %
                              (photo.photo_id + suffix))

  @gen.coroutine
  def _VerifyPhoto(ph_dict):
    """Verify the photo's id. Override any MD5 values that have changed
    on the client as long as the photo image data hasn't yet been uploaded.
    """
    yield Photo.VerifyPhotoId(client, user_id, device_id, ph_dict['photo_id'])
    photo = yield gen.Task(Photo.Query, client, ph_dict['photo_id'], None, must_exist=False)

    if photo is not None:
      # Photo must be owned by calling user, or there's a security breach.
      assert photo.user_id == user_id, (photo, user_id)

      yield [gen.Task(_VerifyAttributeUpdate, photo, '.t', 'tn_md5', ph_dict['tn_md5']),
             gen.Task(_VerifyAttributeUpdate, photo, '.m', 'med_md5', ph_dict['med_md5']),
             gen.Task(_VerifyAttributeUpdate, photo, '.f', 'full_md5', ph_dict['full_md5']),
             gen.Task(_VerifyAttributeUpdate, photo, '.o', 'orig_md5', ph_dict['orig_md5'])]

  yield Activity.VerifyActivityId(client, user_id, device_id, request['activity']['activity_id'])

  request['user_id'] = user_id

  episode_id = request['episode']['episode_id']
  yield Episode.VerifyEpisodeId(client, user_id, device_id, episode_id)

  # In parallel, verify each photo id and update any attributes that can be overridden.
  yield [gen.Task(_VerifyPhoto, ph_dict) for ph_dict in request['photos']]

  yield gen.Task(Operation.CreateAndExecute,
                 client,
                 user_id,
                 device_id,
                 'UploadEpisodeOperation.Execute',
                 request)

  logging.info('UPLOAD EPISODE: user: %d, device: %d, episode: %s, %d photos' %
               (user_id, device_id, episode_id, len(request['photos'])))

  response = {'episode_id': episode_id,
              'photos': [{'photo_id': ph_dict['photo_id'],
                          'tn_put_url': _GenerateUploadUrl(obj_store, ph_dict, '.t', 'tn_md5'),
                          'med_put_url': _GenerateUploadUrl(obj_store, ph_dict, '.m', 'med_md5'),
                          'full_put_url': _GenerateUploadUrl(obj_store, ph_dict, '.f', 'full_md5'),
                          'orig_put_url': _GenerateUploadUrl(obj_store, ph_dict, '.o', 'orig_md5')}
                         for ph_dict in request['photos']]}

  raise gen.Return(response)


def _ValidateContacts(contact_dicts):
  """For each contact in "contact_dicts" that has an identity attribute, validates the identity
  key format. The "contact_dicts" have the FOLLOWER_CONTACTS_METADATA format defined in
  json_schema.py.
  """
  for contact in contact_dicts:
    if 'identity' in contact:
      Identity.ValidateKey(contact['identity'])


def _CanViewViewpointContent(viewpoint, follower):
  """Returns true if the given follower is allowed to view the viewpoint's content:
    1. Follower must exist
    2. Viewpoint must not be removed by the follower
    3. Cookie must allow access to the viewpoint (prospective user invitations have access to
       a single viewpoint's content and to any system viewpoints)
  """
  if viewpoint is None or follower is None or not follower.CanViewContent():
    return False

  if viewpoint.IsSystem() or base.ViewfinderContext.current().CanViewViewpoint(viewpoint.viewpoint_id):
    return True

  return False



def _AddPhotoUrls(obj_store, ph_dict):
  """Adds photo urls to the photo dict for each photo size: original, full, medium, and
  thumbnail. The photo dict should already have a "photo_id" property.
  """
  ph_dict['tn_get_url'] = photo_store.GeneratePhotoUrl(obj_store, ph_dict['photo_id'], '.t')
  ph_dict['med_get_url'] = photo_store.GeneratePhotoUrl(obj_store, ph_dict['photo_id'], '.m')
  ph_dict['full_get_url'] = photo_store.GeneratePhotoUrl(obj_store, ph_dict['photo_id'], '.f')
  ph_dict['orig_get_url'] = photo_store.GeneratePhotoUrl(obj_store, ph_dict['photo_id'], '.o')


def _MakeViewpointMetadataDict(viewpoint, follower, obj_store):
  """Returns a viewpoint metadata dictionary appropriate for a service query response.
  The response dictionary contains valid photo urls for the viewpoints cover photo.
  """
  metadata_dict = viewpoint.MakeMetadataDict(follower)
  if 'cover_photo' in metadata_dict:
    _AddPhotoUrls(obj_store, metadata_dict['cover_photo'])

  return metadata_dict


class ServiceHandler(base.BaseHandler):
  """The RPC multiplexer for client request/responses. The POST
  request body contains the JSON-encoded RPC input, and the HTTP
  response body contains the JSON-encoded RPC output.
  """
  class Method(object):
    """An entry in the service map. When a service request is received,
    it is validated according to the "request" schema. If the message
    format has changed, it is migrated according to the "request_migrators".
    The request is dispatched to the "handler" function. The response is
    validated according to the "response" schema after format migration
    according to the "response_migrators". If "allow_prospective" is true,
    then prospective users are allowed access to the method.

    WARNING: If "allow_prospective" is true, then the method must ensure
             that the prospective user has access only to the viewpoint
             given in the cookie.
    """
    def __init__(self, request, response, handler, allow_prospective=False,
                 min_supported_version=MIN_SUPPORTED_MESSAGE_VERSION,
                 max_supported_version=MAX_SUPPORTED_MESSAGE_VERSION,
                 request_migrators=[], response_migrators=[]):
      self.request = request
      self.response = response
      self.handler = handler
      self.allow_prospective = allow_prospective
      self.min_supported_version = max(min_supported_version, MIN_SUPPORTED_MESSAGE_VERSION)
      self.max_supported_version = min(max_supported_version, MAX_SUPPORTED_MESSAGE_VERSION)
      self.request_migrators = sorted(REQUIRED_MIGRATORS + request_migrators)
      self.response_migrators = sorted(REQUIRED_MIGRATORS + response_migrators)

  # Map from service name to Method instance.
  SERVICE_MAP = {
    'add_followers': Method(request=json_schema.ADD_FOLLOWERS_REQUEST,
                            response=json_schema.ADD_FOLLOWERS_RESPONSE,
                            min_supported_version=Message.EXTRACT_MD5_HASHES,
                            handler=AddFollowers),
    'allocate_ids': Method(request=json_schema.ALLOCATE_IDS_REQUEST,
                           response=json_schema.ALLOCATE_IDS_RESPONSE,
                           min_supported_version=Message.EXTRACT_MD5_HASHES,
                           handler=AllocateIds),
    'build_archive': Method(request=json_schema.BUILD_ARCHIVE_REQUEST,
                           response=json_schema.BUILD_ARCHIVE_RESPONSE,
                           min_supported_version=Message.EXTRACT_MD5_HASHES,
                           handler=BuildArchive),
    'get_calendar': Method(request=json_schema.GET_CALENDAR_REQUEST,
                           response=json_schema.GET_CALENDAR_RESPONSE,
                           min_supported_version=Message.EXTRACT_MD5_HASHES,
                           handler=GetCalendar),
    'hide_photos': Method(request=json_schema.HIDE_PHOTOS_REQUEST,
                          response=json_schema.HIDE_PHOTOS_RESPONSE,
                          min_supported_version=Message.RENAME_PHOTO_LABEL,
                          handler=HidePhotos),
    'list_identities': Method(request=json_schema.LIST_IDENTITIES_REQUEST,
                              response=json_schema.LIST_IDENTITIES_RESPONSE,
                              min_supported_version=Message.EXTRACT_MD5_HASHES,
                              handler=ListIdentities),
    'merge_accounts': Method(request=json_schema.MERGE_ACCOUNTS_REQUEST,
                             response=json_schema.MERGE_ACCOUNTS_RESPONSE,
                             handler=MergeAccounts),
    'new_client_log_url': Method(request=json_schema.NEW_CLIENT_LOG_URL_REQUEST,
                                 response=json_schema.NEW_CLIENT_LOG_URL_RESPONSE,
                                 min_supported_version=Message.EXTRACT_MD5_HASHES,
                                 handler=NewClientLogUrl),
    'post_comment': Method(request=json_schema.POST_COMMENT_REQUEST,
                           response=json_schema.POST_COMMENT_RESPONSE,
                           min_supported_version=Message.EXTRACT_MD5_HASHES,
                           handler=PostComment),
    'query_contacts': Method(request=json_schema.QUERY_CONTACTS_REQUEST,
                             response=json_schema.QUERY_CONTACTS_RESPONSE,
                             response_migrators=[SUPPORT_MULTIPLE_IDENTITIES_PER_CONTACT],
                             min_supported_version=Message.EXTRACT_MD5_HASHES,
                             handler=QueryContacts),
    'query_episodes': Method(request=json_schema.QUERY_EPISODES_REQUEST,
                             response=json_schema.QUERY_EPISODES_RESPONSE,
                             response_migrators=[EXTRACT_ASSET_KEYS, RENAME_PHOTO_LABEL],
                             min_supported_version=Message.EXTRACT_MD5_HASHES,
                             handler=QueryEpisodes,
                             allow_prospective=True),
    'query_followed': Method(request=json_schema.QUERY_FOLLOWED_REQUEST,
                             response=json_schema.QUERY_FOLLOWED_RESPONSE,
                             min_supported_version=Message.EXTRACT_MD5_HASHES,
                             handler=QueryFollowed,
                             allow_prospective=True),
    'query_notifications': Method(request=json_schema.QUERY_NOTIFICATIONS_REQUEST,
                                  response=json_schema.QUERY_NOTIFICATIONS_RESPONSE,
                                  response_migrators=[INLINE_INVALIDATIONS, INLINE_COMMENTS],
                                  min_supported_version=Message.EXTRACT_MD5_HASHES,
                                  handler=QueryNotifications),
    'query_users': Method(request=json_schema.QUERY_USERS_REQUEST,
                          response=json_schema.QUERY_USERS_RESPONSE,
                          min_supported_version=Message.EXTRACT_MD5_HASHES,
                          handler=QueryUsers,
                          allow_prospective=True),
    'query_viewpoints': Method(request=json_schema.QUERY_VIEWPOINTS_REQUEST,
                               response=json_schema.QUERY_VIEWPOINTS_RESPONSE,
                               response_migrators=[SUPPORT_REMOVED_FOLLOWERS],
                               min_supported_version=Message.EXTRACT_MD5_HASHES,
                               handler=QueryViewpoints,
                               allow_prospective=True),
    'record_subscription': Method(request=json_schema.RECORD_SUBSCRIPTION_REQUEST,
                                  response=json_schema.RECORD_SUBSCRIPTION_RESPONSE,
                                  min_supported_version=Message.EXTRACT_MD5_HASHES,
                                  handler=RecordSubscription),
    'remove_contacts': Method(request=json_schema.REMOVE_CONTACTS_REQUEST,
                              response=json_schema.REMOVE_CONTACTS_RESPONSE,
                              min_supported_version=Message.SUPPORT_MULTIPLE_IDENTITIES_PER_CONTACT,
                              handler=RemoveContacts),
    'remove_followers': Method(request=json_schema.REMOVE_FOLLOWERS_REQUEST,
                               response=json_schema.REMOVE_FOLLOWERS_RESPONSE,
                               handler=RemoveFollowers),
    'remove_photos': Method(request=json_schema.REMOVE_PHOTOS_REQUEST,
                            response=json_schema.REMOVE_PHOTOS_RESPONSE,
                            min_supported_version=Message.EXTRACT_MD5_HASHES,
                            handler=RemovePhotos),
    'remove_viewpoint': Method(request=json_schema.REMOVE_VIEWPOINT_REQUEST,
                               response=json_schema.REMOVE_VIEWPOINT_RESPONSE,
                               min_supported_version=Message.INLINE_COMMENTS,
                               handler=RemoveViewpoint),
    'resolve_contacts': Method(request=json_schema.RESOLVE_CONTACTS_REQUEST,
                               response=json_schema.RESOLVE_CONTACTS_RESPONSE,
                               min_supported_version=Message.EXTRACT_MD5_HASHES,
                               handler=ResolveContacts),
    'save_photos': Method(request=json_schema.SAVE_PHOTOS_REQUEST,
                          response=json_schema.SAVE_PHOTOS_RESPONSE,
                          request_migrators=[SUPPRESS_COPY_TIMESTAMP],
                          handler=SavePhotos),
    'share_existing': Method(request=json_schema.SHARE_EXISTING_REQUEST,
                             response=json_schema.SHARE_EXISTING_RESPONSE,
                             request_migrators=[EXPLICIT_SHARE_ORDER, SUPPRESS_COPY_TIMESTAMP],
                             min_supported_version=Message.EXTRACT_MD5_HASHES,
                             handler=ShareExisting),
    'share_new': Method(request=json_schema.SHARE_NEW_REQUEST,
                        response=json_schema.SHARE_NEW_RESPONSE,
                        request_migrators=[EXPLICIT_SHARE_ORDER, SUPPRESS_BLANK_COVER_PHOTO, SUPPRESS_COPY_TIMESTAMP],
                        min_supported_version=Message.EXTRACT_MD5_HASHES,
                        handler=ShareNew),
    'terminate_account': Method(request=json_schema.TERMINATE_ACCOUNT_REQUEST,
                                response=json_schema.TERMINATE_ACCOUNT_RESPONSE,
                                min_supported_version=Message.EXTRACT_MD5_HASHES,
                                handler=TerminateAccount),
    'unlink_identity': Method(request=json_schema.UNLINK_IDENTITY_REQUEST,
                              response=json_schema.UNLINK_IDENTITY_RESPONSE,
                              min_supported_version=Message.EXTRACT_MD5_HASHES,
                              handler=UnlinkIdentity),
    'unshare': Method(request=json_schema.UNSHARE_REQUEST,
                      response=json_schema.UNSHARE_RESPONSE,
                      min_supported_version=Message.EXTRACT_MD5_HASHES,
                      handler=Unshare),
    'update_device': Method(request=json_schema.UPDATE_DEVICE_REQUEST,
                            response=json_schema.UPDATE_DEVICE_RESPONSE,
                            min_supported_version=Message.EXTRACT_MD5_HASHES,
                            handler=UpdateDevice),
    'update_episode': Method(request=json_schema.UPDATE_EPISODE_REQUEST,
                             response=json_schema.UPDATE_EPISODE_RESPONSE,
                             min_supported_version=Message.EXTRACT_MD5_HASHES,
                             handler=UpdateEpisode),
    'update_follower': Method(request=json_schema.UPDATE_FOLLOWER_REQUEST,
                              response=json_schema.UPDATE_FOLLOWER_RESPONSE,
                              handler=UpdateFollower),
    'update_friend': Method(request=json_schema.UPDATE_FRIEND_REQUEST,
                            response=json_schema.UPDATE_FRIEND_RESPONSE,
                            handler=UpdateFriend),
    'update_photo': Method(request=json_schema.UPDATE_PHOTO_REQUEST,
                           response=json_schema.UPDATE_PHOTO_RESPONSE,
                           request_migrators=[EXTRACT_ASSET_KEYS],
                           min_supported_version=Message.EXTRACT_MD5_HASHES,
                           handler=UpdatePhoto),
    'update_user': Method(request=json_schema.UPDATE_USER_REQUEST,
                          response=json_schema.UPDATE_USER_RESPONSE,
                          request_migrators=[SPLIT_NAMES],
                          handler=UpdateUser),
    'update_user_photo': Method(request=json_schema.UPDATE_USER_PHOTO_REQUEST,
                                response=json_schema.UPDATE_USER_PHOTO_RESPONSE,
                                min_supported_version=Message.EXTRACT_ASSET_KEYS,
                                handler=UpdateUserPhoto),
    'update_viewpoint': Method(request=json_schema.UPDATE_VIEWPOINT_REQUEST,
                               response=json_schema.UPDATE_VIEWPOINT_RESPONSE,
                               request_migrators=[SUPPRESS_EMPTY_TITLE],
                               min_supported_version=Message.EXTRACT_MD5_HASHES,
                               handler=UpdateViewpoint),
    'upload_contacts': Method(request=json_schema.UPLOAD_CONTACTS_REQUEST,
                              response=json_schema.UPLOAD_CONTACTS_RESPONSE,
                              request_migrators=[SUPPORT_CONTACT_LIMITS],
                              min_supported_version=Message.SUPPORT_MULTIPLE_IDENTITIES_PER_CONTACT,
                              handler=UploadContacts),
    'upload_episode': Method(request=json_schema.UPLOAD_EPISODE_REQUEST,
                             response=json_schema.UPLOAD_EPISODE_RESPONSE,
                             request_migrators=[EXTRACT_FILE_SIZES, EXTRACT_ASSET_KEYS],
                             min_supported_version=Message.EXTRACT_MD5_HASHES,
                             handler=UploadEpisode),
    }

  def __init__(self, application, request, **kwargs):
    super(ServiceHandler, self).__init__(application, request, **kwargs)

  @handler.authenticated(allow_prospective=True)
  @handler.asynchronous(datastore=True, obj_store=True)
  def post(self, method_name):
    """Parses the JSON request body, validates it, and invokes the
    method as specified in the request URI. On completion, the
    response is returned as a JSON-encoded HTTP response body.
    """
    def _OnSuccess(method, start_time, user, device_id, response_dict):
      self.set_status(200)
      self.set_header('Content-Type', 'application/json; charset=UTF-8')
      # self.write() accepts a dict directly, but tornado's json_encode
      # does bytes-to-unicode conversions that are unnecessary on py2
      # and surprisingly expensive.
      self.write(json.dumps(response_dict))

      request_time = time.time() - start_time
      _avg_req_time.add(request_time)
      logging.debug('serviced %s request in %.4fs: %s' %
                    (method_name, request_time, response_dict))
      self.finish()

    # Set api_name for use in any error response.
    self.api_name = method_name
    _req_per_min.increment()
    start_time = time.time()

    # Check service method; (501: Not Implemented).
    if not ServiceHandler.SERVICE_MAP.has_key(method_name):
      _fail_per_min.increment()
      self.send_error(status_code=501)
      return

    json_request = self._LoadJSONRequest()
    if json_request is None:
      _fail_per_min.increment()
      return

    # Get current user and device id (both of which were originally derived from the user cookie).
    user = base.ViewfinderContext.current().user
    device_id = base.ViewfinderContext.current().device_id

    method = ServiceHandler.SERVICE_MAP[method_name]
    ServiceHandler.InvokeService(self._client, self._obj_store, method_name, user.user_id, device_id,
                                 json_request, callback=partial(_OnSuccess, method, start_time, user, device_id))

  def _handle_request_exception(self, e):
    """Need to override to increment _fail_per_min counter."""
    _fail_per_min.increment()
    super(ServiceHandler, self)._handle_request_exception(e)

  @staticmethod
  @gen.coroutine
  def InvokeService(client, obj_store, method_name, user_id, device_id, json_request):
    """Validates the JSON request body and invokes the method as specified
    in the request URI. On completion, the response is returned as a
    JSON-encoded response dictionary.
    """
    # Look up information about the service method.
    method = ServiceHandler.SERVICE_MAP[method_name]

    # Only allow prospective users to access methods that have been explicitly allowed.
    if not base.ViewfinderContext.current().user.IsRegistered() and not method.allow_prospective:
      raise web.HTTPError(403, 'Permission denied; user account is not registered.')

    try:
      request_message = yield gen.Task(base.BaseHandler._CreateRequestMessage,
                                       client,
                                       json_request,
                                       method.request,
                                       migrators=method.request_migrators,
                                       min_supported_version=method.min_supported_version,
                                       max_supported_version=method.max_supported_version)
    except Exception as ex:
      logging.warning(util.FormatLogArgument(json_request))
      raise InvalidRequestError(INVALID_JSON_REQUEST, request=ex.message)

    # Older clients called remove_photos instead of hide_photos, so redirect them.
    if method_name == 'remove_photos' and request_message.original_version < Message.RENAME_PHOTO_LABEL:
      handler = OldRemovePhotos
    else:
      handler = method.handler

    response_dict = yield gen.Task(handler, client, obj_store, user_id, device_id, request_message.dict)

    response_message = yield gen.Task(base.BaseHandler._CreateResponseMessage,
                                      client,
                                      response_dict,
                                      method.response,
                                      request_message.original_version,
                                      migrators=method.response_migrators)

    raise gen.Return(response_message.dict)
