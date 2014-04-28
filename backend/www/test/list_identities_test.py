# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Test list_identities service API.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

from copy import deepcopy
from functools import partial
from viewfinder.backend.base.testing import async_test
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.www.test import service_base_test


class ListIdentitiesTestCase(service_base_test.ServiceBaseTestCase):
  def testListIdentities(self):
    """Test listing of identities after linking and unlinking a new identity."""
    self._tester.LinkFacebookUser({'id': 100}, user_cookie=self._cookie)
    self._tester.ListIdentities(self._cookie)

    self._tester.UnlinkIdentity(self._cookie, 'FacebookGraph:100')
    self._tester.ListIdentities(self._cookie)


def _TestListIdentities(tester, user_cookie, request_dict):
  """Called by the ServiceTester in order to test list_identities service API call.
  """
  validator = tester.validator
  user_id, device_id = tester.GetIdsFromCookie(user_cookie)
  request_dict = deepcopy(request_dict)

  # Send list_identities request.
  actual_dict = tester.SendRequest('list_identities', user_cookie, request_dict)

  expected_dict = {'user_identities': []}
  predicate = lambda ident: ident.user_id == user_id
  for expected_ident in validator.QueryModelObjects(Identity, predicate=predicate):
    ident_dict = {'identity': expected_ident.key}
    if expected_ident.authority is not None:
      ident_dict['authority'] = expected_ident.authority

    expected_dict['user_identities'].append(ident_dict)

  tester._CompareResponseDicts('list_identities', user_id, request_dict, expected_dict, actual_dict)
  return actual_dict
