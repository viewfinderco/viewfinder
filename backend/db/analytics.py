# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Analytics table.

Each row is composed of:
- hash key: entity: <type>:<id> (eg: us:112 for user_id 112)
- range key: base64 timestamp + type
- column 'type': string describing the entry
- column 'payload': optional payload. format based on the type of entry.

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import json
import logging
import os
import time

from tornado import gen
from viewfinder.backend.base import constants, util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.range_base import DBRangeObject

class Analytics(DBRangeObject):

  # Type strings. They should consist of: <Type>.<Action>. eg: User.CreateProspective

  # Payload for prospective:
  # - "register" for prospective user created inline with registration.
  # - "share_new=id" with user_id of the user starting the conversation.
  # - "add_followed=id" with user_id of the user performing the add_follower op.
  USER_CREATE_PROSPECTIVE = 'User.CreateProspective'

  USER_REGISTER = 'User.Register'

  # Payload for terminate:
  # - "terminate" on account termination.
  # - "merge=id" when merging accounts. id is the target user.
  USER_TERMINATE = 'User.Terminate'

  _table = DBObject._schema.GetTable(vf_schema.ANALYTICS)

  def __init__(self):
    super(Analytics, self).__init__()

  @classmethod
  def CreateSortKey(cls, timestamp, entry_type):
    """Create value for sort_key attribute.  This is derived from timestamp and type."""
    prefix = util.CreateSortKeyPrefix(timestamp, randomness=False)
    return prefix + entry_type

  @classmethod
  def Create(cls, **analytics_dict):
    """Create a new analytics object with fields from 'analytics_dict'. Sets timestamp if not
    specified. Payload may be empty.
    """
    create_dict = analytics_dict
    if 'timestamp' not in create_dict:
      create_dict['timestamp'] = util.GetCurrentTimestamp()

    entity = create_dict['entity']
    entry_type = create_dict['type']
    if entry_type.startswith('User.'):
      assert entity.startswith('us:'), 'Wrong entity string for type User.*: %r' % create_dict

    # Always store as int, floats cause problems as sort keys.
    create_dict['timestamp'] = int(create_dict['timestamp'])
    create_dict['sort_key'] = Analytics.CreateSortKey(create_dict['timestamp'], create_dict['type'])

    return cls.CreateFromKeywords(**create_dict)
