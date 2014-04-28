# Copyright 2012 Viewfinder Inc. All Rights Reserved.

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

from tornado import options
from viewfinder.backend.www.test import service_base_test
from viewfinder.backend.www.tools import merge_tool


class MergeToolTestCase(service_base_test.ServiceBaseTestCase):
  """Test cases for backend/www/tools/merge_tool.py."""
  def testMerge(self):
    self._validate = False

    self._RunAsync(merge_tool.Merge,
                   self._client,
                   target_user_id=self._user.user_id,
                   source_user_id=self._user2.user_id,
                   base_url=self.get_url(''),
                   no_prompt=True)

    actual_dict = self._tester.SendRequest('list_identities', self._cookie, {})
    self.assertEqual(len(actual_dict['identities']), 2)
