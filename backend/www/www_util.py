# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""WWW utility methods.

  ParseJSONRequest(): parses a JSON request body into python data structures
  ParseJSONResponse(): parses a JSON response body into python data structures
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

from contextlib import closing
from cStringIO import StringIO
import gzip
import json
from tornado import escape, web
from viewfinder.backend.base import constants, util
from viewfinder.backend.base.exceptions import InvalidRequestError, HttpForbiddenError, NotFoundError
from viewfinder.backend.base.exceptions import ServiceUnavailableError

_CONTENT_TYPES = ['application/json', 'text/javascript']

# In order to authorize certain high-privilege operations, such as update password, the user
# must present a cookie which has recently been confirmed via email or SMS.
_CONFIRM_TIME_LIMIT = constants.SECONDS_PER_HOUR


def ParseJSONRequest(request):
  """Parse the JSON-encoded contents of the request body and return
  the python data object.
  """
  content_type = request.headers.get('Content-Type', '')
  if not any(content_type.startswith(x) for x in _CONTENT_TYPES):
    raise web.HTTPError(400, 'bad request content type: %s' % content_type)
  json_dict = json.loads(request.body)
  #logging.debug('parsed: %s' % repr(json_dict))
  return json_dict


def ParseJSONResponse(response):
  """Parse the JSON-encoded contents of the response body and return
  the python data object.
  """
  content_type = response.headers.get('Content-Type', '')
  if not any(content_type.startswith(x) for x in _CONTENT_TYPES):
    raise web.HTTPError(response.code, '%r' % response.headers)
  try:
    json_dict = json.loads(response.body)
    #logging.debug('parsed: %s' % repr(json_dict))
  except:
    if response.code == 200:
      raise
    json_dict = {'error': response.body}
  if response.code != 200:
    error = 'unknown'
    if isinstance(json_dict, dict) and json_dict.get('error'):
      error = json_dict.get('error')
    raise web.HTTPError(response.code, '%s' % error)
  return json_dict


def GzipEncode(s):
  """Compresses 's' (which may be a byte or unicode string) with gzip and returns the result."""
  with closing(StringIO()) as sio:
      with gzip.GzipFile(fileobj=sio, mode='wb') as gzfile:
        gzfile.write(escape.utf8(s))
      return sio.getvalue()


def GzipDecode(s):
  """Decompresses 's' and returns the result as a byte string."""
  with closing(StringIO(s)) as sio:
      with gzip.GzipFile(fileobj=sio, mode='rb') as gzfile:
        return gzfile.read()


def HTTPInfoFromException(value):
  """Returns a tuple containing the HTTP status code and error message, based on the passed
  exception info.
  """
  if isinstance(value, web.HTTPError):
    return value.status_code, value.log_message
  elif isinstance(value, InvalidRequestError):
    return 400, value.args[0]
  elif isinstance(value, HttpForbiddenError):
    return 403, value.args[0]
  elif isinstance(value, NotFoundError):
    return 404, value.args[0]
  elif isinstance(value, ServiceUnavailableError):
    return 503, value.args[0]
  else:
    return 500, str(value)


def FormatIntegralLastKey(value):
  """Formats an integral last key as a string, zero-padding up to 15 digits of precision.

  15 digits is enough precision to handle any conceivable values we'll need to return.
  """
  assert value < 1000000000000000, value
  return '%015d' % value


def IsConfirmedCookie(confirm_time):
  """Given the confirm time of a cookie, check that the cookie was confirmed no more than an
  hour ago. A recently confirmed cookie is required to perform certain high privilege operations,
  such as updating the password.
  """
  return confirm_time is not None and util.GetCurrentTimestamp() < confirm_time + _CONFIRM_TIME_LIMIT
