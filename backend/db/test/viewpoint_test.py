# Copyright 2013 Viewfinder Inc. All rights reserved.
"""Tests for Viewpoint data object."""

__author__ = 'ben@emailscrubbed.com (Ben Darnell)'

from viewfinder.backend.db.viewpoint import Viewpoint

from base_test import DBBaseTestCase

class ViewpointTestCase(DBBaseTestCase):
  def testRepr(self):
    vp = Viewpoint.CreateFromKeywords(viewpoint_id='vp1', title='hello')
    self.assertIn('vp1', repr(vp))
    self.assertNotIn('hello', repr(vp))
