# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""UserPost relation.

By default, users have a relationship with photos that are contained
within viewpoints they follow. By default, all photos contained in
non-public viewpoints are shown as part of the user's personal
collection. However, the user may want to hide certain of these photos
from view. Inversely, the user may want to show public photos in his
personal view. This relation allows these kinds of per-user
customization of photos.

Each photo can be stamped with "labels" which describe the user-
specific customizations made to that photo. The name of each label
is chosen so that "is <name>" makes sense.

  'removed':  the photo should not be shown in the user's personal
              collection, and will ultimately deleted from the
              server if no other references to it are held.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import logging
import time

from functools import partial
from tornado import gen
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.range_base import DBRangeObject

@DBObject.map_table_attributes
class UserPost(DBRangeObject):
  """UserPost data object."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.USER_POST)

  HIDDEN = 'hidden'

  def IsHidden(self):
    """Returns true if the photo has been hidden by the user so that it will not show in the
    personal library or conversation feed.
    """
    return UserPost.HIDDEN in self.labels
