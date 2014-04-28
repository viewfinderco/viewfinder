# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Url shortening service.

When sending texts, the size of links embedded in the text needs to be as short as possible.
The ShortURL service generates URL's by generating random numbers that are difficult to guess,
and then using those as an index into a database table. The table stores a set of named
parameters that a handler method can use to reconstruct the parameters that would have been
part of the longer URL.

The ShortURL service partitions the URL space into groups, so that URL's generated for one
group have no overlap with those for another group. It also enforces URL expiration, and
restricts the maximum number of incorrect guesses that can be made for URL's within a
particular group.
"""

__authors__ = ['andy@emailscrubbed.com (Andy Kimball)']

from tornado import gen, options, web
from viewfinder.backend.base import base64hex, handler
from viewfinder.backend.base.exceptions import InvalidRequestError
from viewfinder.backend.db.guess import Guess
from viewfinder.backend.db.short_url import ShortURL


class ShortURLBaseHandler(object):
  """Base class for ShortURL handlers.

  To use the service, derive a handler from this class and from a Tornado RequestHandler.
  Override _HandleGet and/or _HandlePost to receive a callback when a request comes in for
  a ShortURL in that group. Override _MAX_GUESSES to change the default for maximum number
  of incorrect guesses to allow.
  """
  _MAX_GUESSES = 100

  @handler.asynchronous(datastore=True, obj_store=True)
  @gen.engine
  def get(self, url_path):
    """Handle GET requests to a ShortURL. Recover the group id and random key components and
    use them to redeem the ShortURL if it exists and is not expired. Fetch the named parameters
    that were associated with the ShortURL and pass them to the _HandleGet method.
    """
    # Check that the ShortURL is valid.
    short_url = yield self._CheckShortURL(url_path)

    # Invoke the derived class to handle the request.
    self._HandleGet(short_url, **short_url.json)

  @handler.asynchronous(datastore=True, obj_store=True)
  @gen.engine
  def post(self, url_path):
    """Handle POST requests to a ShortURL. Recover the group id and random key components and
    use them to redeem the ShortURL if it exists and is not expired. Fetch the named parameters
    that were associated with the ShortURL and pass them to the _HandlePost method.
    """
    # Check that the ShortURL is valid.
    short_url = yield self._CheckShortURL(url_path)

    # Invoke the derived class to handle the request.
    self._HandlePost(short_url, **short_url.json)

  @gen.coroutine
  def _CheckShortURL(self, url_path):
    """Extract the ShortURL components from the URL path and check that the ShortURL exists
    and is valid.
    """
    # Split key to get the group_id and random key components.
    group_id = url_path[:-ShortURL.KEY_LEN_IN_BASE64]
    random_key = url_path[-ShortURL.KEY_LEN_IN_BASE64:]

    if len(group_id) == 0 or len(random_key) != ShortURL.KEY_LEN_IN_BASE64:
      raise web.HTTPError(400, 'The URL path is not valid.')

    # Raise error if too many guesses have been made in this group.
    guess_id = Guess.ConstructGuessId('url', group_id)
    if not (yield Guess.CheckGuessLimit(self._client, guess_id, self._MAX_GUESSES)):
      raise web.HTTPError(403, 'This link has been disabled for 24 hours in order to prevent unauthorized use.')

    # Try to find the ShortURL. Increment the incorrect guess count and raise an error if it cannot be found.
    short_url = yield gen.Task(ShortURL.Query, self._client, group_id, random_key, None, must_exist=False)
    if short_url is None:
      yield Guess.ReportIncorrectGuess(self._client, guess_id)
      raise web.HTTPError(404, 'The requested link could not be found.')

    if short_url.IsExpired():
      raise web.HTTPError(403, 'The requested link has expired and can no longer be used.')

    raise gen.Return(short_url)

  def _HandleGet(self, short_url):
    """Any derived class should override this method in order to handle HTTP GET requests
    to the ShortURL. This method is called with the redeemed ShortURL db object. In addition,
    any named parameters passed to ShortURL.Create are passed to the derived _HandleGet.
    """
    raise web.HTTPError(405)

  def _HandlePost(self, short_url):
    """Any derived class should override this method in order to handle HTTP POST requests
    to the ShortURL. This method is called with the redeemed ShortURL db object. In addition,
    any named parameters passed to ShortURL.Create are passed to the derived _HandlePost.
    """
    raise web.HTTPError(405)


class ShortDomainRedirectHandler(web.RequestHandler):
  """Handler which redirects ShortURLs from a short version of the domain name to the standard
  domain name.

  To use, set up a handler for each kind of ShortURL that needs to be redirected. Since the
  short domain name is used only to host ShortURL's, the ShortURL group_id prefix can be
  shortened even more (ex. from "pr/" to "p"). Use Tornado to chop off the old prefix, and
  specify the "add_prefix" argument to have this handler add the new prefix as part of the
  redirect URL.
  """
  def __init__(self, application, request, add_prefix):
    super(ShortDomainRedirectHandler, self).__init__(application, request)
    self._add_prefix = add_prefix

  def get(self, path):
    self.redirect('https://%s/%s' % (options.options.domain, self._add_prefix + path))
