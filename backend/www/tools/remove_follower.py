# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Remove a follower from a viewpoint

Usage:

% python backend/www/tools/remove_follower.py --viewpoint_id=<viewpoint_id> \
    --user_id=<user_id>
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import json
import logging
import pprint
import sys

from functools import partial
from tornado import options
from tornado.web import stack_context
from viewfinder.backend.base import util
from viewfinder.backend.db.db_client import DBClient
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.followed import Followed
from viewfinder.backend.db.notification import Notification
from viewfinder.backend.db.user import User
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.www import base, www_main

options.define('user_id', default=None, type=int, help='user id of the account running service method')
options.define('viewpoint_id', default=None, type=str, help='viewpoint id')


def _RunService(callback):
  """Removes the follower by loading follower relation and deleting it.
  Removes all notifications related to the viewpoint.
  """
  assert options.options.user_id, 'must specify a user id (--user_id)'
  assert options.options.viewpoint_id, 'must specify a viewpoint id (--viewpoint_id)'

  client = DBClient.Instance()

  def _OnService(response_dict):
    logging.info('result: %s' % util.ToCanonicalJSON(response_dict, indent=2))
    callback()

  def _OnNotification(n, cb):
    if n.viewpoint_id == options.options.viewpoint_id:
      n.name = 'clear_badges'
      n.sender_id = 494
      n.sender_device_id = 2260
      n.invalidate = None
      n.op_id = None
      n.viewpoint_id = None
      n.update_seq = None
      n.viewed_seq = None
      n.activity_id = None
      n.badge = 0
      print 'resetting notification to clear_badges: %s' % n
      n.Update(client, cb)
    else:
      cb()

  def _DoneQueryFollowed():
    Notification.VisitRange(client, options.options.user_id, None, None, _OnNotification, callback)

  def _OnQueryFollowed(f, cb):
    if f.viewpoint_id == options.options.viewpoint_id:
      print 'deleting: %s' % f
      f.Delete(client, cb)
    else:
      cb()

  def _OnDeleteFollower():
    Followed.VisitRange(client, options.options.user_id, None, None, _OnQueryFollowed, _DoneQueryFollowed)

  def _OnQueryFollower(f):
    if f:
      print 'deleting: %s' % f
      f.Delete(client, _OnDeleteFollower)
    else:
      _OnDeleteFollower()

  Follower.Query(client, options.options.user_id, options.options.viewpoint_id,
                 None, _OnQueryFollower, must_exist=False)


if __name__ == '__main__':
  www_main.InitAndRun(_RunService)
