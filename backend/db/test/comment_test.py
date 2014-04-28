# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Tests for Comment data object.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import time
import unittest

from functools import partial

from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.comment import Comment

from base_test import DBBaseTestCase

class CommentTestCase(DBBaseTestCase):
  def testSortOrder(self):
    """Verify that comments sort ascending by timestamp."""
    timestamp = time.time()
    comment_id1 = Comment.ConstructCommentId(timestamp, 0, 0)
    comment_id2 = Comment.ConstructCommentId(timestamp + 1, 0, 0)
    self.assertGreater(comment_id2, comment_id1)

  def testRepr(self):
    comment = Comment.CreateFromKeywords(viewpoint_id='vp1', comment_id='c1', message='hello')
    self.assertIn('vp1', repr(comment))
    self.assertNotIn('hello', repr(comment))
