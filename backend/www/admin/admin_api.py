# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Utilities for access the admin API.

This interface is built on python's urllib2 and cookielib modules and is
synchronous. As such, it should NEVER be used in the server, but only for
command-line admin utilities.

  - Authenticate: calls to /admin/otp to get admin auth credentials
  - ServiceRequest: calls to /admin/service
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)']

import json
import urllib2

from viewfinder.backend.base.exceptions import AdminAPIError


def _MakeRequest(host, path, request_dict):
  """Gets a URL to the specified "path" to the API endpoint
  available at "host".
  """
  # TODO(spencer): remove this once we're using tornado 3.0 and
  #   the AsyncHTTPSTestCase.
  from viewfinder.backend.www.basic_auth import BasicAuthHandler
  if BasicAuthHandler._HTTP_TEST_CASE:
    url = 'http://%s/admin%s' % (host, path)
  else:
    url = 'https://%s/admin%s' % (host, path)
  req = urllib2.Request(url)
  req.add_data(json.dumps(request_dict))
  req.add_header('Content-Type', 'application/json')
  return req


def _HandleResponse(method, response):
  """Verifies the response and returns the JSON dict of
  the response body on success. Raises AdminAPIError on error.
  """
  if response.code != 200:
    raise AdminAPIError('%s failed: %s' % (method, response.read()))
  else:
    response_dict = json.loads(response.read())
    if 'error' in response_dict:
      raise AdminAPIError('%s failed: %s' %
                          (method, response_dict['error']['message']))
    return response_dict


def Authenticate(opener, host, user, pwd, otp_entry):
  """Authenticates the user/pwd/otp_entry combination."""
  request_dict = {'username': user, 'password': pwd, 'otp': otp_entry}
  req = _MakeRequest(host, '/otp', request_dict)
  return _HandleResponse('authentication', opener.open(req))


def ServiceRequest(opener, host, method, request_dict):
  """Makes service request to '/service/' + "method" API method."""
  req = _MakeRequest(host, '/service/%s' % method, request_dict)
  return _HandleResponse(method, opener.open(req))
