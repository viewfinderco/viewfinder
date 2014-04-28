# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder episode.

Episodes encompass a collection of photos separated by enough space
and/or time from previous or subsequent photos.

Episode ids are constructed from 32 bits of time, a variable-length-
encoded integer device id and a variable-length-encoded unique id from
the device. The final value is base64-hex encoded. They sort
lexicographically by timestamp (reverse ordered so the most recent
episodes are listed first in a query).

Photos are added to episodes via posts. A post is a composite-key
relation between an episode-id and a photo-id.

  Episode: a collection of photos contiguous in spacetime
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import logging

from functools import partial
from tornado import gen
from viewfinder.backend.base import util
from viewfinder.backend.base.exceptions import InvalidRequestError, PermissionError, LimitExceededError
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.accounting import Accounting
from viewfinder.backend.db.asset_id import IdPrefix, ConstructTimestampAssetId
from viewfinder.backend.db.asset_id import DeconstructTimestampAssetId, VerifyAssetId
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.hash_base import DBHashObject
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.notification import Notification
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user import User
from viewfinder.backend.db.user_photo import UserPhoto
from viewfinder.backend.db.user_post import UserPost
from viewfinder.backend.db.versions import Version
from viewfinder.backend.db.viewpoint import Viewpoint


@DBObject.map_table_attributes
class Episode(DBHashObject):
  """Viewfinder episode data object."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.EPISODE)

  def __init__(self, episode_id=None):
    super(Episode, self).__init__()
    self.episode_id = episode_id

  @classmethod
  def ConstructEpisodeId(cls, timestamp, device_id, uniquifier):
    """Returns an episode id constructed from component parts. Episodes
    sort from newest to oldest. See "ConstructTimestampAssetId" for
    details of the encoding.
    """
    return ConstructTimestampAssetId(IdPrefix.Episode, timestamp, device_id, uniquifier)

  @classmethod
  def DeconstructEpisodeId(cls, episode_id):
    """Returns the components of an episode id: timestamp, device_id, and
    uniquifier.
    """
    return DeconstructTimestampAssetId(IdPrefix.Episode, episode_id)

  @classmethod
  @gen.coroutine
  def VerifyEpisodeId(cls, client, user_id, device_id, episode_id):
    """Ensures that a client-provided episode id is valid according
    to the rules specified in VerifyAssetId.
    """
    yield VerifyAssetId(client, user_id, device_id, IdPrefix.Episode, episode_id, has_timestamp=True)

  @classmethod
  @gen.coroutine
  def CreateNew(cls, client, **ep_dict):
    """Creates the episode specified by 'ep_dict'. The caller is responsible for checking
    permission to do this, as well as ensuring that the episode does not yet exist (or is
    just being identically rewritten).

    Returns: The created episode.
    """
    assert 'episode_id' in ep_dict and 'user_id' in ep_dict and 'viewpoint_id' in ep_dict, ep_dict
    assert 'timestamp' in ep_dict, 'timestamp attribute required in episode: "%s"' % ep_dict
    assert 'publish_timestamp' in ep_dict, 'publish_timestamp attribute required in episode: "%s"' % ep_dict

    episode = Episode.CreateFromKeywords(**ep_dict)
    yield gen.Task(episode.Update, client)
    raise gen.Return(episode)

  @gen.coroutine
  def UpdateExisting(self, client, **ep_dict):
    """Updates an existing episode."""
    assert 'publish_timestamp' not in ep_dict and 'parent_ep_id' not in ep_dict, ep_dict
    self.UpdateFromKeywords(**ep_dict)
    yield gen.Task(self.Update, client)

  @classmethod
  @gen.coroutine
  def QueryIfVisible(cls, client, user_id, episode_id, must_exist=True, consistent_read=False):
    """If the user has viewing rights to the specified episode, returns that episode, otherwise
    returns None. The user has viewing rights if the user is a follower of the episode's
    viewpoint. If must_exist is true and the episode does not exist, raises an InvalidRequest
    exception.
    """
    episode = yield gen.Task(Episode.Query,
                             client,
                             episode_id,
                             None,
                             must_exist=False,
                             consistent_read=consistent_read)

    if episode is None:
      if must_exist == True:
        raise InvalidRequestError('Episode "%s" does not exist.' % episode_id)
    else:
      follower = yield gen.Task(Follower.Query,
                                client,
                                user_id,
                                episode.viewpoint_id,
                                col_names=None,
                                must_exist=False)
      if follower is None or not follower.CanViewContent():
        raise gen.Return(None)

    raise gen.Return(episode)

  @classmethod
  def QueryPosts(cls, client, episode_id, user_id, callback,
                 limit=None, excl_start_key=None, base_results=None):
    """Queries posts (up to 'limit' total) for the specified
    'episode_id', viewable by 'user_id'. The query is for posts starting
    with (but excluding) 'excl_start_key'. The photo metadata for each
    post relation are in turn queried and the post and photo metadata
    are combined into a single dict. The callback is invoked with the
    array of combined post/photo metadata, and the last queried post
    sort-key.

    The 'base_results' argument allows this method to be re-entrant.
    'limit' can be satisfied completely if a user is querying an
    episode they own with nothing archived or deleted. However, in cases
    where an episode hasn't been fully shared, or has many photos archived
    or deleted by the requesting user, QueryPosts needs to be re-invoked
    possibly many times to query 'limit' posts or reach the end of the
    episode.
    """
    def _OnQueryMetadata(posts, results):
      """Constructs the photo metadata to return. The "check_label" argument
      is used to determine whether to use the old permissions model or the
      new one. If "check_label" is true, then only return a photo if a label
      is present. Otherwise, the photo is part of an episode created by
      the new sharing functionality, and the user automatically has access
      to all photos in that episode.
      """
      ph_dicts = base_results or []
      for post, (photo, user_post) in zip(posts, results):
        ph_dict = photo._asdict()
        labels = post.labels.combine()
        if user_post is not None:
          labels = labels.union(user_post.labels.combine())
        if len(labels) > 0:
          ph_dict['labels'] = list(labels)
        ph_dicts.append(ph_dict)

      last_key = posts[-1].photo_id if len(posts) > 0 else None
      if last_key is not None and len(ph_dicts) < limit:
        Episode.QueryPosts(client, episode_id, user_id, callback, limit=limit,
                           excl_start_key=last_key, base_results=ph_dicts)
      else:
        callback((ph_dicts, last_key))

    def _OnQueryPosts(posts):
      with util.ArrayBarrier(partial(_OnQueryMetadata, posts)) as b:
        for post in posts:
          with util.ArrayBarrier(b.Callback()) as metadata_b:
            post_id = Post.ConstructPostId(post.episode_id, post.photo_id)
            Photo.Query(client, hash_key=post.photo_id, col_names=None,
                        callback=metadata_b.Callback())
            UserPost.Query(client, hash_key=user_id, range_key=post_id,
                           col_names=None, callback=metadata_b.Callback(), must_exist=False)

    # Query the posts with limit & excl_start_key.
    Post.RangeQuery(client, hash_key=episode_id, range_desc=None, limit=limit,
                    col_names=None, callback=_OnQueryPosts, excl_start_key=excl_start_key)
