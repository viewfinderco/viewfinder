# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Tests for Follower data object.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import time
import unittest

from functools import partial

from viewfinder.backend.base import util
from viewfinder.backend.base.exceptions import PermissionError
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.device import Device
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.follower import Follower
from viewfinder.backend.db.viewpoint import Viewpoint

from base_test import DBBaseTestCase

class FollowerTestCase(DBBaseTestCase):
  def testUpdatePermissions(self):
    """Try to update permission labels to the empty set."""
    follower_dict = {'user_id': 1,
                     'viewpoint_id': 'vp1',
                     'labels': [Follower.ADMIN]}
    follower = self.UpdateDBObject(Follower, **follower_dict)
    self.assertRaises(PermissionError, follower.SetLabels, [])
