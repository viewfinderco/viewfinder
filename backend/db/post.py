# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Post relation.

A post is the relationship between a photo and an episode. The post
table allows quick queries for all photos within an episode.

  Post: defines relation between a photo and an episode
"""

__author__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
              'andy@emailscrubbed.com (Andy Kimball)']

import logging

from tornado import gen
from functools import partial
from viewfinder.backend.base import util
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.asset_id import IdPrefix
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.range_base import DBRangeObject
from viewfinder.backend.db.user_post import UserPost

@DBObject.map_table_attributes
class Post(DBRangeObject):
  """Post data object."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.POST)

  UNSHARED = 'unshared'
  REMOVED = 'removed'

  def IsUnshared(self):
    """Returns true if the photo has been unshared by the posting user,
    making it inaccessible to followers of the viewpoint.
    """
    return Post.UNSHARED in self.labels

  def IsRemoved(self):
    """Returns true if the photo has been removed by the posting user, making it inaccessible
    to followers of the viewpoint. This label will always be set if the unshared label is set.
    """
    # TODO(Andy): Get rid of the UNSHARED check once every unshared post is also removed.
    return Post.UNSHARED in self.labels or Post.REMOVED in self.labels

  @classmethod
  def ConstructPostId(cls, episode_id, photo_id):
    """Returns a post id constructed by concatenating the id of the
    episode that contains the post with the id of the posted photo.
    The two parts are separated by a '+' character, which is not produced
    by the base64hex encoding, and so can be used to later deconstruct
    the post id if necessary. While the key for a post is composite with
    hash_key=episode_id and range_key=photo_id, the range key for the
    UserPost table must use a concatenation of the post key as its range
    key. ConstructPostId, and its inverse DeconstructPostId, concatenate
    and split the post key respectively into a single value. This
    concatenated post id will sort posts in the same order that
    (episode_id, photo_id) does. This is because each part is encoded
    using base64hex, which sorts in the same way as the source value.
    Furthermore, the '+' character sorts lower than any of the base64hex
    bytes, so the episode_id terminates with a "low" byte, making substring
    episode ids sort lower.
    """
    return IdPrefix.Post + episode_id[1:] + '+' + photo_id[1:]

  @classmethod
  def DeconstructPostId(cls, post_id):
    """Returns the components of a post id: (episode_id, photo_id)."""
    assert post_id[0] == IdPrefix.Post, post_id
    index = post_id.index('+')
    assert index > 0, post_id

    return IdPrefix.Episode + post_id[1:index], IdPrefix.Photo + post_id[index + 1:]

  @classmethod
  @gen.coroutine
  def CreateNew(cls, client, **post_dict):
    """Creates a new post from post_dict. The caller is responsible for checking permission to
    do this, as well as ensuring that the post does not yet exist (or is just being identically
    rewritten).

    Posts are sorted using the photo id. Since the photo id is prefixed by the photo timestamp,
    this amounts to sorting by photo timestamp, which is in order from newest to oldest (i.e.
    descending).

    Returns: post that was created.
    """
    post = Post.CreateFromKeywords(**post_dict)
    yield gen.Task(post.Update, client)
    raise gen.Return(post)
