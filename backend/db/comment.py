# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder comment.

A viewpoint may contain any number of comments, which are textual messages
contributed by followers of that viewpoint. Comments are ordered by
ascending timestamp, and uniquely qualified by device id and a device-
generated comment id. Each time a new comment is posted to a viewpoint,
a viewpoint activity is created to track the action, and a notification
is sent to each follower of the viewpoint.

A comment can optionally be linked to other assets in the viewpoint via
its "asset_id" attribute. If a user comments on a photo, then the comment
is linked to that photo. If a user responds to a previous comment, then
the new comment is linked to the previous comment. Multiple comments can
be linked to the same "parent" comment.

  Comment: user-provided message regarding a viewpoint.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

from tornado import gen, escape
from viewfinder.backend.base.exceptions import LimitExceededError, PermissionError
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.accounting import Accounting
from viewfinder.backend.db.asset_id import IdPrefix, ConstructTimestampAssetId, DeconstructTimestampAssetId, VerifyAssetId
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.notification import Notification
from viewfinder.backend.db.range_base import DBRangeObject


@DBObject.map_table_attributes
class Comment(DBRangeObject):
  """Viewfinder comment data object."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.COMMENT)

  COMMENT_SIZE_LIMIT_BYTES = 32 * 1024
  """Max length (in bytes) of comments.
  This is based on a max bytes per row in dynamo of 64KB.
  """

  def __init__(self, viewpoint_id=None, comment_id=None):
    super(Comment, self).__init__()
    self.viewpoint_id = viewpoint_id
    self.comment_id = comment_id

  @classmethod
  def ShouldScrubColumn(cls, name):
    return name == 'message'

  @classmethod
  def ConstructCommentId(cls, timestamp, device_id, uniquifier):
    """Returns a comment id constructed from component parts. Comments
    sort from oldest to newest. See "ConstructTimestampAssetId" for
    details of the encoding.
    """
    return ConstructTimestampAssetId(IdPrefix.Comment, timestamp, device_id, uniquifier, reverse_ts=False)

  @classmethod
  def DeconstructCommentId(cls, comment_id):
    """Returns the components of a comment id: timestamp, device_id, and
    uniquifier.
    """
    return DeconstructTimestampAssetId(IdPrefix.Comment, comment_id, reverse_ts=False)

  @classmethod
  @gen.coroutine
  def VerifyCommentId(cls, client, user_id, device_id, comment_id):
    """Ensures that a client-provided comment id is valid according
    to the rules specified in VerifyAssetId.
    """
    yield VerifyAssetId(client, user_id, device_id, IdPrefix.Comment, comment_id, has_timestamp=True)

  @classmethod
  @gen.coroutine
  def CreateNew(cls, client, **cm_dict):
    """Creates the comment specified by "cm_dict". The caller is responsible for checking
    permission to do this, as well as ensuring that the comment does not yet exist (or is
    just being identically rewritten).

    Returns the created comment.
    """
    comment = Comment.CreateFromKeywords(**cm_dict)
    yield gen.Task(comment.Update, client)
    raise gen.Return(comment)
