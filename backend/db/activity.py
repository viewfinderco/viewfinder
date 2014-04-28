# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Viewfinder activity.

  Activities are associated with a viewpoint and contain a record of all high-level operations
  which have modified the structure of the viewpoint in some way. For example, each upload and
  share operation will create an activity, since each action creates a new episode within a
  viewpoint. Each activity is associated with a custom set of arguments, which are typically
  the identifiers of assets involved in the operation. For example, a share activity would
  contain the identifiers of the episodes and photos that were shared. See the header for
  notification.py for a discussion of how activities are different from notifications.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import json

from tornado import gen
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.asset_id import IdPrefix, ConstructTimestampAssetId, DeconstructTimestampAssetId, VerifyAssetId
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.range_base import DBRangeObject


@DBObject.map_table_attributes
class Activity(DBRangeObject):
  """Viewfinder activity data object."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.ACTIVITY)

  def MakeMetadataDict(self):
    """Constructs a dictionary containing activity metadata in a format that conforms to
    ACTIVITY in json_schema.py.
    """
    activity_dict = self._asdict()
    activity_dict[activity_dict.pop('name')] = json.loads(activity_dict.pop('json'))
    return activity_dict

  @classmethod
  def ConstructActivityId(cls, timestamp, device_id, uniquifier):
    """Returns an activity id constructed from component parts. Activities sort from newest
    to oldest. See "ConstructTimestampAssetId" for details of the encoding.
    """
    return ConstructTimestampAssetId(IdPrefix.Activity, timestamp, device_id, uniquifier)

  @classmethod
  def ConstructActivityIdFromOperationId(cls, timestamp, operation_id):
    """Returns an activity id constructed by combining the specified timestamp and the
    device_id and device_op_id from the operation_id.
    """
    device_id, uniquifier = Operation.DeconstructOperationId(operation_id)
    return Activity.ConstructActivityId(timestamp, device_id, uniquifier)

  @classmethod
  def DeconstructActivityId(cls, activity_id):
    """Returns the components of an activity id: timestamp, device_id, and uniquifier."""
    return DeconstructTimestampAssetId(IdPrefix.Activity, activity_id)

  @classmethod
  @gen.coroutine
  def VerifyActivityId(cls, client, user_id, device_id, activity_id):
    """Ensures that a client-provided activity id is valid according to the rules specified
    in VerifyAssetId.
    """
    yield VerifyAssetId(client, user_id, device_id, IdPrefix.Activity, activity_id, has_timestamp=True)

  @classmethod
  @gen.coroutine
  def CreateAddFollowers(cls, client, user_id, viewpoint_id, activity_id, timestamp,
                         update_seq, follower_ids):
    """Creates an activity that tracks the changes to the specified viewpoint resulting from
    an "add_followers" operation.
    """
    args_dict = {'follower_ids': follower_ids}
    activity = yield Activity._CreateActivity(client,
                                              user_id,
                                              viewpoint_id,
                                              activity_id,
                                              timestamp,
                                              update_seq,
                                              'add_followers',
                                              args_dict)
    raise gen.Return(activity)

  @classmethod
  @gen.coroutine
  def CreateMergeAccounts(cls, client, user_id, viewpoint_id, activity_id, timestamp,
                          update_seq, target_user_id, source_user_id):
    """Creates an activity that tracks the changes to the specified viewpoint resulting from
    a "merge_accounts" operation.
    """
    args_dict = {'target_user_id': target_user_id,
                 'source_user_id': source_user_id}
    activity = yield Activity._CreateActivity(client,
                                              user_id,
                                              viewpoint_id,
                                              activity_id,
                                              timestamp,
                                              update_seq,
                                              'merge_accounts',
                                              args_dict)
    raise gen.Return(activity)

  @classmethod
  @gen.coroutine
  def CreatePostComment(cls, client, user_id, viewpoint_id, activity_id, timestamp,
                        update_seq, cm_dict):
    """Creates an activity that tracks the changes to the specified viewpoint resulting from
    a "post_comment" operation.
    """
    args_dict = {'comment_id': cm_dict['comment_id']}
    activity = yield Activity._CreateActivity(client,
                                              user_id,
                                              viewpoint_id,
                                              activity_id,
                                              timestamp,
                                              update_seq,
                                              'post_comment',
                                              args_dict)
    raise gen.Return(activity)

  @classmethod
  @gen.coroutine
  def CreateRemoveFollowers(cls, client, user_id, viewpoint_id, activity_id, timestamp,
                            update_seq, follower_ids):
    """Creates an activity that tracks the changes to the specified viewpoint resulting from
    an "remove_followers" operation.
    """
    args_dict = {'follower_ids': follower_ids}
    activity = yield Activity._CreateActivity(client,
                                              user_id,
                                              viewpoint_id,
                                              activity_id,
                                              timestamp,
                                              update_seq,
                                              'remove_followers',
                                              args_dict)
    raise gen.Return(activity)

  @classmethod
  @gen.coroutine
  def CreateRemovePhotos(cls, client, user_id, viewpoint_id, activity_id, timestamp,
                         update_seq, ep_dicts):
    """Creates an activity that tracks the changes to the specified viewpoint resulting from
    a "remove_photos" operation.
    """
    args_dict = {'episodes': [{'episode_id': ep_dict['new_episode_id'],
                               'photo_ids': ep_dict['photo_ids']}
                              for ep_dict in ep_dicts]}
    activity = yield Activity._CreateActivity(client,
                                              user_id,
                                              viewpoint_id,
                                              activity_id,
                                              timestamp,
                                              update_seq,
                                              'remove_photos',
                                              args_dict)
    raise gen.Return(activity)

  @classmethod
  @gen.coroutine
  def CreateSavePhotos(cls, client, user_id, viewpoint_id, activity_id, timestamp,
                       update_seq, ep_dicts):
    """Creates an activity that tracks the changes to the specified viewpoint resulting from
    a "save_photos" operation.
    """
    args_dict = {'episodes': [{'episode_id': ep_dict['new_episode_id'],
                               'photo_ids': ep_dict['photo_ids']}
                              for ep_dict in ep_dicts]}
    activity = yield Activity._CreateActivity(client,
                                              user_id,
                                              viewpoint_id,
                                              activity_id,
                                              timestamp,
                                              update_seq,
                                              'save_photos',
                                              args_dict)
    raise gen.Return(activity)

  @classmethod
  @gen.coroutine
  def CreateShareExisting(cls, client, user_id, viewpoint_id, activity_id, timestamp,
                          update_seq, ep_dicts):
    """Creates an activity that tracks the changes to the specified viewpoint resulting from
    a "share_existing" operation.
    """
    args_dict = {'episodes': [{'episode_id': ep_dict['new_episode_id'],
                               'photo_ids': ep_dict['photo_ids']}
                              for ep_dict in ep_dicts]}
    activity = yield Activity._CreateActivity(client,
                                              user_id,
                                              viewpoint_id,
                                              activity_id,
                                              timestamp,
                                              update_seq,
                                              'share_existing',
                                              args_dict)
    raise gen.Return(activity)

  @classmethod
  @gen.coroutine
  def CreateShareNew(cls, client, user_id, viewpoint_id, activity_id, timestamp,
                     update_seq, ep_dicts, follower_ids):
    """Creates an activity that tracks the changes to the specified viewpoint resulting from
    a "share_new" operation.
    """
    args_dict = {'episodes': [{'episode_id': ep_dict['new_episode_id'],
                               'photo_ids': ep_dict['photo_ids']}
                              for ep_dict in ep_dicts],
                 'follower_ids': follower_ids}
    activity = yield Activity._CreateActivity(client,
                                              user_id,
                                              viewpoint_id,
                                              activity_id,
                                              timestamp,
                                              update_seq,
                                              'share_new',
                                              args_dict)
    raise gen.Return(activity)

  @classmethod
  @gen.coroutine
  def CreateUnshare(cls, client, user_id, viewpoint_id, activity_id, timestamp,
                    update_seq, ep_dicts):
    """Creates an activity that tracks the changes to the specified viewpoint resulting from
    a "unshare" operation.
    """
    args_dict = {'episodes': [{'episode_id': ep_dict['episode_id'],
                               'photo_ids': ep_dict['photo_ids']}
                              for ep_dict in ep_dicts]}
    activity = yield Activity._CreateActivity(client,
                                              user_id,
                                              viewpoint_id,
                                              activity_id,
                                              timestamp,
                                              update_seq,
                                              'unshare',
                                              args_dict)
    raise gen.Return(activity)

  @classmethod
  @gen.coroutine
  def CreateUpdateEpisode(cls, client, user_id, viewpoint_id, activity_id, timestamp,
                          update_seq, ep_dict):
    """Creates an activity that tracks the changes to the specified viewpoint resulting from
    an "update_episode" operation.
    """
    args_dict = {'episode_id': ep_dict['episode_id']}
    activity = yield Activity._CreateActivity(client,
                                              user_id,
                                              viewpoint_id,
                                              activity_id,
                                              timestamp,
                                              update_seq,
                                              'update_episode',
                                              args_dict)
    raise gen.Return(activity)

  @classmethod
  @gen.coroutine
  def CreateUpdateViewpoint(cls, client, user_id, viewpoint_id, activity_id, timestamp,
                            update_seq, prev_values):
    """Creates an activity that tracks the changes to the specified viewpoint resulting from
    an "update_viewpoint" operation.
    """
    args_dict = {'viewpoint_id': viewpoint_id}
    args_dict.update(prev_values)
    activity = yield Activity._CreateActivity(client,
                                              user_id,
                                              viewpoint_id,
                                              activity_id,
                                              timestamp,
                                              update_seq,
                                              'update_viewpoint',
                                              args_dict)
    raise gen.Return(activity)

  @classmethod
  @gen.coroutine
  def CreateUploadEpisode(cls, client, user_id, viewpoint_id, activity_id, timestamp,
                         update_seq, ep_dict, ph_dicts):
    """Create an activity that tracks the changes to the specified viewpoint resulting from
    a "upload_episode" operation.
    """
    args_dict = {'episode_id': ep_dict['episode_id'],
                 'photo_ids': [ph_dict['photo_id'] for ph_dict in ph_dicts]}
    activity = yield Activity._CreateActivity(client,
                                              user_id,
                                              viewpoint_id,
                                              activity_id,
                                              timestamp,
                                              update_seq,
                                              'upload_episode',
                                              args_dict)
    raise gen.Return(activity)

  @classmethod
  @gen.coroutine
  def _CreateActivity(cls, client, user_id, viewpoint_id, activity_id, timestamp,
                      update_seq, name, args_dict):
    """Helper method that creates an activity for any kind of operation."""
    activity = yield gen.Task(Activity.Query, client, viewpoint_id, activity_id, None, must_exist=False)

    # If activity doesn't exist, then create it. Otherwise, this is idempotent create case, so just verify user_id.
    if activity is None:
      from viewfinder.backend.base import message
      args_dict['headers'] = dict(version=message.MAX_MESSAGE_VERSION)

      activity = Activity.CreateFromKeywords(viewpoint_id=viewpoint_id, activity_id=activity_id,
                                             user_id=user_id, timestamp=timestamp, update_seq=update_seq,
                                             name=name, json=json.dumps(args_dict))
      yield gen.Task(activity.Update, client)
    else:
      # Idempotent create.
      assert activity.user_id == user_id, (activity, user_id)

    raise gen.Return(activity)
