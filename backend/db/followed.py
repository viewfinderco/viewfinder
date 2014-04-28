# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Followed relation.

The Followed relation is basically a secondary index over the
"last_updated" attribute of the Viewpoint table. Viewpoints are
ordered according to the time of last update, rather than by
viewpoint id. However, the ordering is not perfectly maintained.
Viewpoints that were last updated on the same day are grouped
together, with the ordering within the group undefined. This
enables "query_followed" to return viewpoints in rough order, but
without paying a high cost for keeping the index maintained.

  Followed: sorts viewpoints in reverse order of last update.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

from tornado import gen
from viewfinder.backend.base import constants, util
from viewfinder.backend.db import db_client, vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.range_base import DBRangeObject


@DBObject.map_table_attributes
class Followed(DBRangeObject):
  """Viewfinder followed data object."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.FOLLOWED)

  def __init__(self, user_id=None, sort_key=None):
    super(Followed, self).__init__()
    self.user_id = user_id
    self.sort_key = sort_key

  @classmethod
  def CreateSortKey(cls, viewpoint_id, timestamp):
    """Creates a "sort_key" value, which is a concatenation of the timestamp
    (truncated to day boundary) and the viewpoint id.
    """
    # Reverse the timestamp so that Viewpoints sort with the latest updated first.
    prefix = util.CreateSortKeyPrefix(Followed._TruncateToDay(timestamp), randomness=False, reverse=True)
    return prefix + viewpoint_id

  @classmethod
  @gen.engine
  def UpdateDateUpdated(cls, client, user_id, viewpoint_id, old_timestamp, new_timestamp, callback):
    """Inserts a new followed record with date_updated set to the truncated "new_timestamp",
    and then deletes the followed record for "old_timestamp". A simple update is not possible
    because the "date_updated" attribute is part of the primary key. Optimize by not updating
    if the old and new "date_updated" values are the same.
    """
    # Always ratchet the timestamp -- never update to an older timestamp.
    assert new_timestamp is not None, (user_id, viewpoint_id)
    if old_timestamp is None or old_timestamp < new_timestamp:
      old_date_updated = Followed._TruncateToDay(old_timestamp)
      new_date_updated = Followed._TruncateToDay(new_timestamp)

      # Only update (and possibly delete) if old and new values are not the same.
      if old_date_updated != new_date_updated:
        # Insert the new followed record.
        followed = Followed(user_id, Followed.CreateSortKey(viewpoint_id, new_date_updated))
        followed.date_updated = new_date_updated
        followed.viewpoint_id = viewpoint_id
        yield gen.Task(followed.Update, client)

        # Delete the previous followed record, if it exists.
        if old_date_updated is not None:
          followed = Followed(user_id, Followed.CreateSortKey(viewpoint_id, old_date_updated))
          yield gen.Task(followed.Delete, client)

    callback()

  @classmethod
  def _TruncateToDay(cls, timestamp):
    """Truncate timestamp to day boundary."""
    if timestamp is None:
      return None
    return (timestamp // constants.SECONDS_PER_DAY) * constants.SECONDS_PER_DAY
