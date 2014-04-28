# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Viewfinder BuildArchiveOperation.

This operation builds an archive of content for a given user and sends the user
an email with a link that can be used to retrieve a zip file of their content.
The zip contains all source needed to invoke the web client and display the user's
conversations.
The link is an S3 signed URL that will expire after 24 hours.
Note: This operation runs as user 0 so that only one will be active at any given time.  This works
  as a throttling mechanism.
"""

__authors__ = ['mike@emailscrubbed.com (Mike Purtell)']

import calendar
import datetime
import json
import logging
import os
import random
import shutil
import string

from tornado import gen, httpclient, options, process

from viewfinder.backend.base import constants, util
from viewfinder.backend.base.environ import ServerEnvironment
from viewfinder.backend.base.exceptions import ServiceUnavailableError, NotFoundError
from viewfinder.backend.base.secrets import GetSecret
from viewfinder.backend.db import db_client
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.followed import Followed
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user import User
from viewfinder.backend.db.user_photo import UserPhoto
from viewfinder.backend.db.user_post import UserPost
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.op.viewfinder_op import ViewfinderOperation
from viewfinder.backend.resources.message.error_messages import SERVICE_UNAVAILABLE
from viewfinder.backend.resources.resources_mgr import ResourcesManager
from viewfinder.backend.services.email_mgr import EmailManager
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.www import base, www_util, photo_store

CONVO_FOLDER_NAME = 'conversations'

def _CanViewViewpointContent(viewpoint, follower):
  """Returns true if the given follower is allowed to view the viewpoint's content:
    1. Follower must exist
    2. Viewpoint must not be removed by the follower
  """
  if viewpoint is None or follower is None or not follower.CanViewContent():
    return False

  return True

def _MakeViewpointMetadataDict(viewpoint, follower):
  """Returns a viewpoint metadata dictionary appropriate for a service query response.
  The response dictionary contains valid photo urls for the viewpoint's cover photo.
  """
  def _GetNormalizedViewpointTitle(vp_dict):
    """Normalize the viewpoint title so that it can be used as a directory name in the archive.
    This will strip anything except for upper/lower case letters, digits and the space character.
    It will also truncate it to 100 characters to avoid file path limitations.
    """
    norm_title = ''
    if vp_dict['type'] == Viewpoint.DEFAULT:
      norm_title = 'Personal Collection'
    elif vp_dict.get('title') is not None:
      for c in vp_dict['title']:
        if c in BuildArchiveOperation._PATH_WHITELIST:
          norm_title += c
      # Avoid creating a folder path that's too long.
      norm_title = norm_title[:100]
    return norm_title

  vp_dict = viewpoint.MakeMetadataDict(follower)
  norm_vp_title = _GetNormalizedViewpointTitle(vp_dict)
  # Append the viewpoint id to the path to ensure uniqueness.
  vp_dict['folder_name'] = ('%s/%s %s' % (CONVO_FOLDER_NAME, norm_vp_title, vp_dict['viewpoint_id'])).strip()
  if 'cover_photo' in vp_dict:
    vp_dict['cover_photo']['full_get_url'] = \
      os.path.join(vp_dict['folder_name'], vp_dict['cover_photo']['photo_id'] + '.f.jpg')
  return vp_dict

@gen.coroutine
def _QueryFollowedForArchive(client, user_id):
  """Queries all viewpoints followed by the requested user (excluding the default/personal viewpoint)."""
  followed = yield gen.Task(Followed.RangeQuery,
                            client,
                            hash_key=user_id,
                            range_desc=None,
                            limit=None,
                            col_names=['viewpoint_id'],
                            excl_start_key=None)

  # Get the viewpoint associated with each follower object.
  viewpoint_keys = [db_client.DBKey(f.viewpoint_id, None) for f in followed]
  follower_keys = [db_client.DBKey(user_id, f.viewpoint_id) for f in followed]
  viewpoints, followers = yield [gen.Task(Viewpoint.BatchQuery, client, viewpoint_keys, None, must_exist=False),
                                 gen.Task(Follower.BatchQuery, client, follower_keys, None, must_exist=False)]

  # Formulate the viewpoints list into a dict for JSON output.
  response = {'viewpoints': [_MakeViewpointMetadataDict(v, f)
                             for v, f in zip(viewpoints, followers)
                             if v is not None and not v.IsDefault()]}

  raise gen.Return(response)

@gen.coroutine
def _QueryViewpointsForArchive(client,
                               user_id,
                               viewpoint_ids,
                               get_followers=False,
                               get_activities=False,
                               get_episodes=False,
                               get_comments=False,
                               get_attributes=False):
  """Queries viewpoint metadata, as well as associated followers and episodes.
  """
  @gen.coroutine
  def _QueryFollowers():
    """Produces list of (followers, last_key) tuples, one for each viewpoint in the request."""
    tasks = []
    for vp_id in viewpoint_ids:
      if get_followers:
        tasks.append(Viewpoint.QueryFollowers(client, vp_id))
      else:
        tasks.append(util.GenConstant(None))

    follower_results = yield tasks
    raise gen.Return(follower_results)

  @gen.coroutine
  def _QueryActivities():
    """Produces list of (activities, last_key) tuples, one for each viewpoint in the request."""
    tasks = []
    for vp_id in viewpoint_ids:
      if get_activities:
        tasks.append(gen.Task(Viewpoint.QueryActivities, client, vp_id))
      else:
        tasks.append(util.GenConstant(None))

    activity_results = yield tasks
    raise gen.Return(activity_results)

  @gen.coroutine
  def _QueryEpisodes():
    """Produces list of (episodes, last_key) tuples, one for each viewpoint in the request."""
    tasks = []
    for vp_id in viewpoint_ids:
      if get_episodes:
        tasks.append(gen.Task(Viewpoint.QueryEpisodes, client, vp_id))
      else:
        tasks.append(util.GenConstant(None))

    episode_results = yield tasks
    raise gen.Return(episode_results)

  @gen.coroutine
  def _QueryComments():
    """Produces list of (comments, last_key) tuples, one for each viewpoint in the request."""
    tasks = []
    for vp_id in viewpoint_ids:
      if get_comments:
        tasks.append(gen.Task(Viewpoint.QueryComments, client, vp_id))
      else:
        tasks.append(util.GenConstant(None))

    comment_results = yield tasks
    raise gen.Return(comment_results)

  viewpoint_keys = [db_client.DBKey(vp_id, None) for vp_id in viewpoint_ids]
  follower_keys = [db_client.DBKey(user_id, vp_id) for vp_id in viewpoint_ids]

  results = yield [gen.Task(Viewpoint.BatchQuery, client, viewpoint_keys, None, must_exist=False),
                   gen.Task(Follower.BatchQuery, client, follower_keys, None, must_exist=False),
                   _QueryFollowers(),
                   _QueryActivities(),
                   _QueryEpisodes(),
                   _QueryComments()]

  viewpoints, followers, follower_id_results, activity_results, episode_results, comment_results = results
  zip_list = zip(viewpoints, followers, follower_id_results, activity_results,
                 episode_results, comment_results)

  response_vp_dicts = []
  for viewpoint, follower, follower_result, activity_result, episode_result, comment_result in zip_list:
    # Only return the viewpoint metadata if the caller is a follower of the viewpoint.
    if follower is not None and not follower.IsRemoved():
      response_vp_dict = {'viewpoint_id': viewpoint.viewpoint_id}

      if get_attributes:
        response_vp_dict.update(_MakeViewpointMetadataDict(viewpoint, follower))

      if get_followers:
        followers, last_key = follower_result
        response_vp_dict['followers'] = [foll.MakeFriendMetadataDict() for foll in followers]
        if last_key is not None:
          response_vp_dict['follower_last_key'] = www_util.FormatIntegralLastKey(last_key)

      if _CanViewViewpointContent(viewpoint, follower):
        if get_activities:
          activities, last_key = activity_result
          response_vp_dict['activities'] = [act.MakeMetadataDict() for act in activities]
          if last_key is not None:
            response_vp_dict['activity_last_key'] = last_key

        if get_episodes:
          episodes, last_key = episode_result
          response_vp_dict['episodes'] = [ep._asdict() for ep in episodes]
          if last_key is not None:
            response_vp_dict['episode_last_key'] = last_key

        if get_comments:
          comments, last_key = comment_result
          response_vp_dict['comments'] = [co._asdict() for co in comments]
          if last_key is not None:
            response_vp_dict['comment_last_key'] = last_key

      response_vp_dicts.append(response_vp_dict)

  raise gen.Return({'viewpoints': response_vp_dicts})

@gen.coroutine
def _QueryUsersForArchive(client, requesting_user_id, user_ids):
  """Queries users by user id, filtering by friendships."""
  user_friend_list = yield gen.Task(User.QueryUsers, client, requesting_user_id, user_ids)
  user_dicts = yield [gen.Task(user.MakeUserMetadataDict, client, requesting_user_id, forward_friend, reverse_friend)
                      for user, forward_friend, reverse_friend in user_friend_list]

  response = {'users': user_dicts}
  raise gen.Return(response)


@gen.coroutine
def _QueryEpisodesForArchive(client, obj_store, user_id, episode_ids):
  """Queries posts from the specified episodes.
  """
  def _MakePhotoDict(post, photo, user_post, user_photo):
    ph_dict = photo.MakeMetadataDict(post, user_post, user_photo)

    # Do not return access URLs for posts which have been removed.
    if not post.IsRemoved():
      ph_dict['full_get_url'] = photo_store.GeneratePhotoUrl(obj_store, ph_dict['photo_id'], '.f')

    return ph_dict

  # Get all requested episodes, along with posts for each episode.
  episode_keys = [db_client.DBKey(ep_id, None) for ep_id in episode_ids]

  post_tasks = []
  for ep_id in episode_ids:
    post_tasks.append(gen.Task(Post.RangeQuery, client, ep_id, None, None, None, excl_start_key=None))

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

  for ep_id, episode, posts in zip(episode_ids, episodes, posts_list):
    # Gather list of (post, photo, user_post) tuples for this episode.
    photo_info_list = []
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
      response_ep_dict = {'episode_id': ep_id}

      response_ep_dict.update(episode._asdict())

      response_ep_dict['photos'] = [_MakePhotoDict(photo, post, user_post, user_photo)
                                    for photo, post, user_post, user_photo in photo_info_list]
      if len(photo_info_list) > 0:
        response_ep_dict['last_key'] = photo_info_list[-1][0].photo_id

      response_dict['episodes'].append(response_ep_dict)

  raise gen.Return(response_dict)

class BuildArchiveOperation(ViewfinderOperation):
  """ Operation to:
  1) Clear temporary directory used to construct zip file content.
  2) Collect a given user's content into a temporary directory.
  3) Copy web client code into the same temporary directory.
  4) Zip the temp directory up.
  5) Put the zip file into S3.
  6) Generate a signed URL referencing the zip file in S3.
  7) Email the signed URL to the user.
  """
  _PATH_WHITELIST = ' ' + string.ascii_letters + string.digits
  _OFFBOARDING_DIR_NAME = 'offboarding'
  _ZIP_FILE_NAME = 'vf.zip'
  _CONTENT_DIR_NAME = 'viewfinder'
  # 3 days for user to retrieve their zip file.
  _S3_ZIP_FILE_ACCESS_EXPIRATION = 3 * constants.SECONDS_PER_DAY

  def __init__(self, client, user_id, email):
    super(BuildArchiveOperation, self).__init__(client)
    self._user_id = user_id
    self._email = email
    self._notify_timestamp = self._op.timestamp
    self._photo_obj_store = ObjectStore.GetInstance(ObjectStore.PHOTO)
    self._user_zips_obj_store = ObjectStore.GetInstance(ObjectStore.USER_ZIPS)
    self._offboarding_assets_dir_path = ResourcesManager.Instance().GetOffboardingPath()
    self._temp_dir_path = os.path.join(ServerEnvironment.GetViewfinderTempDirPath(),
                                       BuildArchiveOperation._OFFBOARDING_DIR_NAME)
    self._zip_file_path = os.path.join(self._temp_dir_path, BuildArchiveOperation._ZIP_FILE_NAME)
    self._content_dir_path = os.path.join(self._temp_dir_path, BuildArchiveOperation._CONTENT_DIR_NAME)
    self._data_dir_path = os.path.join(self._content_dir_path, CONVO_FOLDER_NAME)

  @classmethod
  @gen.coroutine
  def Execute(cls, client, user_id, email):
    """Entry point called by the operation framework."""
    yield BuildArchiveOperation(client, user_id, email)._BuildArchive()

  def _ResetArchiveDir(self):
    """Get our temp directory into a known clean state."""
    # Make sure certain directories already exists.
    if not os.path.exists(ServerEnvironment.GetViewfinderTempDirPath()):
      os.mkdir(ServerEnvironment.GetViewfinderTempDirPath())
    if not os.path.exists(self._temp_dir_path):
      os.mkdir(self._temp_dir_path)

    # Blow away any previously existing content.
    if os.path.exists(self._content_dir_path):
      shutil.rmtree(self._content_dir_path)
    assert not os.path.exists(self._content_dir_path)
    # Blow away any previous zip file.
    if os.path.exists(self._zip_file_path):
      os.remove(self._zip_file_path)
    assert not os.path.exists(self._zip_file_path)

    # Recreate the content directory.
    os.mkdir(self._content_dir_path)
    os.mkdir(self._data_dir_path)

  @gen.coroutine
  def _ProcessPhoto(self, folder_path, photo_id, url):
    http_client = httpclient.AsyncHTTPClient()
    try:
      response = yield http_client.fetch(url,
                                         method='GET',
                                         validate_cert=options.options.validate_cert)
    except httpclient.HTTPError as e:
      if e.code == 404:
        logging.warning('Photo not found for users(%d) archive: %s' % (self._user_id, photo_id + '.f'))
        return
      else:
        logging.warning('Photo store S3 GET request error: [%s] %s' % (type(e).__name__, e.message))
        raise ServiceUnavailableError(SERVICE_UNAVAILABLE)

    if response.code != 200:
      raise AssertionError('failure on GET request for photo %s: %s' %
                           (photo_id + '.f', response))

    # Write the image to the jpg file.
    # TODO(mike): Consider moving this IO to thread pool to avoid blocking on main thread.
    with open(os.path.join(folder_path, photo_id + '.f.jpg'), mode='wb') as f:
      f.write(response.body)

  @gen.coroutine
  def _VerifyPhotoExists(self, folder_path, photo_id):
    """The file for this photo should already exist."""
    assert os.path.exists(os.path.join(folder_path, photo_id + '.f.jpg'))

  @gen.coroutine
  def _ProcessViewpoint(self, vp_dict):
    results_dict = yield _QueryViewpointsForArchive(self._client,
                                                    self._user_id,
                                                    [vp_dict['viewpoint_id']],
                                                    get_activities=True,
                                                    get_attributes=True,
                                                    get_comments=True,
                                                    get_episodes=True)

    viewpoint_folder_path = os.path.join(self._content_dir_path, vp_dict['folder_name'])
    # Now, grab the photos!
    episode_ids = [ep_dict['episode_id'] for ep_dict in results_dict['viewpoints'][0]['episodes']]
    episodes_dict = yield _QueryEpisodesForArchive(self._client, self._photo_obj_store, self._user_id, episode_ids)

    photos_to_fetch = dict()
    photos_to_merge = dict()

    # Gather photo URL's to request and replace URL's with archive paths.
    for ep_dict in episodes_dict['episodes']:
      for photo_dict in ep_dict['photos']:
        if photo_dict.get('full_get_url') is not None:
          photos_to_fetch[photo_dict['photo_id']] = photo_dict['full_get_url']
          photo_dict['full_get_url'] = os.path.join(vp_dict['folder_name'], photo_dict['photo_id'] + '.f.jpg')
      photos_to_merge[ep_dict['episode_id']] = ep_dict['photos']

    # Merge the photo metadata from query_episodes into the query_viewpoint response.
    for ep_dict in results_dict['viewpoints'][0]['episodes']:
      ep_dict['photos'] = photos_to_merge[ep_dict['episode_id']]

    if os.path.exists(viewpoint_folder_path):
      # Because the viewpoint folder already exists, let's just verify that everything else exists.
      assert os.path.exists(os.path.join(viewpoint_folder_path,'metadata.jsn'))
      for photo_id,url in photos_to_fetch.items():
        yield self._VerifyPhotoExists(viewpoint_folder_path, photo_id)
    else:
      # TODO(mike): Consider moving this IO to thread pool to avoid blocking on main thread.
      os.mkdir(viewpoint_folder_path)
      with open(os.path.join(viewpoint_folder_path,'metadata.jsn'), mode='wb') as f:
        f.write("viewfinder.jsonp_data =")
        json.dump(results_dict['viewpoints'][0], f)

      # Now, fetch all of the photos for this episode.
      # We'll do this serially since writing the files will be done with blocking-IO and we don't want to
      #   overwhelm the server with the blocking-IO.
      for photo_id,url in photos_to_fetch.items():
        yield self._ProcessPhoto(viewpoint_folder_path, photo_id, url)

  @gen.coroutine
  def _BuildArchive(self):
    """Drive overall archive process as outlined in class header comment."""

    logging.info('building archive for user: %d' % self._user_id)

    # Prepare temporary destination folder (delete existing.  We'll always start from scratch).
    self._ResetArchiveDir()

    # Copy in base assets and javascript which will drive browser experience of content for users.
    proc = process.Subprocess(['cp',
                               '-R',
                               os.path.join(self._offboarding_assets_dir_path, 'web_code'),
                               self._content_dir_path])
    code = yield gen.Task(proc.set_exit_callback)
    if code != 0:
      logging.error('Error copying offboarding assets: %d' % code)
      raise IOError()

    # Top level iteration is over viewpoints.
    # For each viewpoint,
    #    iterate over activities and collect photos/episodes as needed.
    #    Build various 'tables' in json format:
    #        Activity, Comment, Episode, Photo, ...
    #
    viewpoints_dict = yield _QueryFollowedForArchive(self._client, self._user_id)
    viewpoint_ids = [viewpoint['viewpoint_id'] for viewpoint in viewpoints_dict['viewpoints']]
    followers_dict = yield _QueryViewpointsForArchive(self._client,
                                                           self._user_id,
                                                           viewpoint_ids,
                                                           get_followers=True)
    for viewpoint, followers in zip(viewpoints_dict['viewpoints'], followers_dict['viewpoints']):
      viewpoint['followers'] = followers
    # Query user info for all users referenced by any of the viewpoints.
    users_to_query = list({f['follower_id'] for vp in followers_dict['viewpoints'] for f in vp['followers']})
    users_dict = yield _QueryUsersForArchive(self._client, self._user_id, users_to_query)
    top_level_metadata_dict = dict(viewpoints_dict.items() + users_dict.items())

    # Write the top level metadata to the root of the archive.
    # TODO(mike): Consider moving this IO to thread pool to avoid blocking on main thread.
    with open(os.path.join(self._content_dir_path, 'viewpoints.jsn'), mode='wb') as f:
      # Need to set metadata as variable for JS code.
      f.write("viewfinder.jsonp_data =")
      json.dump(top_level_metadata_dict, f)

    # Now, process each viewpoint.
    for vp_dict in top_level_metadata_dict['viewpoints']:
      if Follower.REMOVED not in vp_dict['labels']:
        yield self._ProcessViewpoint(vp_dict)

    # Now, generate user specific view file: index.html.
    # This is the file that the user will open to launch the web client view of their data.
    recipient_user = yield gen.Task(User.Query, self._client, self._user_id, None)
    user_info = {'user_id' : recipient_user.user_id,
                 'name' : recipient_user.name,
                 'email' : recipient_user.email,
                 'phone' : recipient_user.phone,
                 'default_viewpoint_id' : recipient_user.private_vp_id
                 }
    view_local = ResourcesManager().Instance().GenerateTemplate('view_local.html',
                                                                user_info=user_info,
                                                                viewpoint_id=None)
    with open(os.path.join(self._content_dir_path, 'index.html'), mode='wb') as f:
      f.write(view_local)

    with open(os.path.join(self._content_dir_path, 'README.txt'), mode='wb') as f:
      f.write("This Viewfinder archive contains both a readable local HTML file " +
              "and backup folders including all photos included in those conversations.\n")

    # Exec zip command relative to the parent of content dir so that paths in zip are relative to that.
    proc = process.Subprocess(['zip',
                               '-r',
                               BuildArchiveOperation._ZIP_FILE_NAME,
                               BuildArchiveOperation._CONTENT_DIR_NAME],
                              cwd=self._temp_dir_path)
    code = yield gen.Task(proc.set_exit_callback)
    if code != 0:
      logging.error('Error creating offboarding zip file: %d' % code)
      raise IOError()

    # Key is: "{user_id}/{timestamp}_{random}/Viewfinder.zip"
    # timestamp is utc unix timestamp.
    s3_key = '%d/%d_%d/Viewfinder.zip' % (self._user_id,
                               calendar.timegm(datetime.datetime.utcnow().utctimetuple()),
                               int(random.random() * 1000000))

    if options.options.fileobjstore:
      # Next, upload this to S3 (really fileobjstore in this case).
      with open(self._zip_file_path, mode='rb') as f:
        s3_data = f.read()
      yield gen.Task(self._user_zips_obj_store.Put, s3_key, s3_data)
    else:
      # Running against AWS S3, so use awscli to upload zip file into S3.
      s3_path = 's3://' + ObjectStore.USER_ZIPS_BUCKET + '/' + s3_key

      # Use awscli to copy file into S3.
      proc = process.Subprocess(['aws', 's3', 'cp', self._zip_file_path, s3_path, '--region', 'us-east-1'],
                                stdout=process.Subprocess.STREAM,
                                stderr=process.Subprocess.STREAM,
                                env={'AWS_ACCESS_KEY_ID': GetSecret('aws_access_key_id'),
                                     'AWS_SECRET_ACCESS_KEY': GetSecret('aws_secret_access_key')})

      result, error, code = yield [
        gen.Task(proc.stdout.read_until_close),
        gen.Task(proc.stderr.read_until_close),
        gen.Task(proc.set_exit_callback)
      ]

      if code != 0:
        logging.error("%d = 'aws s3 cp %s %s': %s" % (code, self._zip_file_path, s3_path, error))
        if result and len(result) > 0:
          logging.info("aws result: %s" % result)
        raise IOError()

    # Generate signed URL to S3 for given user zip.  Only allow link to live for 3 days.
    s3_url = self._user_zips_obj_store.GenerateUrl(s3_key,
                                                   cache_control='private,max-age=%d' %
                                                                 self._S3_ZIP_FILE_ACCESS_EXPIRATION,
                                                   expires_in=3 * self._S3_ZIP_FILE_ACCESS_EXPIRATION)
    logging.info('user zip uploaded: %s' % s3_url)

    # Finally, send the user an email with the link to download the zip files just uploaded to s3.
    email_args = {'from': EmailManager.Instance().GetInfoAddress(),
                  'to': self._email,
                  'subject': 'Your Viewfinder archive download is ready'}

    fmt_args = {'archive_url': s3_url,
                'hello_name': recipient_user.given_name or recipient_user.name}
    email_args['text'] = ResourcesManager.Instance().GenerateTemplate('user_zip.email', is_html=False, **fmt_args)
    yield gen.Task(EmailManager.Instance().SendEmail, description='user archive zip', **email_args)
