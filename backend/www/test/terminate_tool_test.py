# Copyright 2012 Viewfinder Inc. All Rights Reserved.

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

from tornado import options
from viewfinder.backend.www.test import service_base_test
from viewfinder.backend.www.tools import terminate_tool


class TerminateToolTestCase(service_base_test.ServiceBaseTestCase):
  """Test cases for backend/www/tools/terminate_tool.py."""
  def testTerminate(self):
    self._validate = False

    self._RunAsync(terminate_tool.Terminate,
                   self._client,
                   user_id=self._user.user_id,
                   base_url=self.get_url(''),
                   no_prompt=True)

    # Account should be terminated, so any API call will result in 401.
    self.assertRaisesHttpError(401, self._tester.SendRequest, 'query_notifications', self._cookie, {})
