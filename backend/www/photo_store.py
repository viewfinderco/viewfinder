# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""HTTP request handler for serving viewfinder photo image file
assets.

In case of a local file store, permissions for the current user and
the requested photo are verified and the requester is redirected to
the FileObjectStoreHandler.

For an s3 file store, permissions for the current user and the
requested photo are verified and the requester is redirected to a
pre-authorized, expiring S3 URL.

 PhotoStoreHandler: Request handler for authorizing photo requests
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)',
               'andy@emailscrubbed.com (Andy Kimball)']

import base64
import httplib
import logging

from tornado import gen, options, web
from viewfinder.backend.base import handler
from viewfinder.backend.db.episode import Episode
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.db.post import Post
from viewfinder.backend.db.user_post import UserPost
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.www import base

options.define('validate_cert', default=True,
               help='set to False to allow insecure file obj store for testing')


def GeneratePhotoUrl(obj_store, photo_id, suffix):
  """Generate S3 signed URL for the given photo. The S3 response will contain a Cache-Control
  header specifying private caching and a 1 year max age.
  """
  return obj_store.GenerateUrl(photo_id + suffix, cache_control='private,max-age=31536000')


class PhotoStoreHandler(base.BaseHandler):
  """Handles PUT requests by storing image assets in the object
  store. GET request retrieve image assets. Each method type
  verifies user authentication credentials.
  """
  @handler.asynchronous(datastore=True, obj_store=True)
  @gen.engine
  def get(self, episode_id, photo_id, suffix):
    """Verifies user credentials and then redirects to the URL where
    the actual image bits are stored.
    """
    url = yield PhotoStoreHandler.GetPhotoUrl(self._client,
                                              self._obj_store,
                                              episode_id,
                                              photo_id,
                                              suffix)
    self.redirect(url)

  @handler.asynchronous(datastore=True, obj_store=True)
  @gen.engine
  def put(self, episode_id, photo_id, suffix):
    """Verifies user credentials. If the user has write access to the
    photo, and if an 'If-None-Match' is present, sends a HEAD request
    to the object store to determine asset Etag. If the Etag matches,
    returns a 304. Otherwise, generates an upload URL and redirects.
    """
    def _GetUploadUrl(photo, verified_md5):
      content_type = photo.content_type or 'image/jpeg'
      return self._obj_store.GenerateUploadUrl(photo_id + suffix, content_type=content_type,
                                               content_md5=verified_md5)

    # Always expect well-formed Content-MD5 header. This ensures that the image data always matches
    # what is in the metadata, and also enables the detection of any bit corruption on the wire.
    if 'Content-MD5' not in self.request.headers:
      raise web.HTTPError(400, 'Missing Content-MD5 header.')

    try:
      request_md5 = self.request.headers['Content-MD5']
      actual_md5 = base64.b64decode(request_md5).encode('hex')
    except:
      raise web.HTTPError(400, 'Content-MD5 header "%s" is not a valid base-64 value.' % request_md5)

    # Match against the MD5 value stored in the photo metadata.
    if suffix not in ['.t', '.m', '.f', '.o']:
      raise web.HTTPError(404, 'Photo not found; "%s" suffix is invalid.' % suffix)

    # Ensure that user has permission to PUT the photo.
    yield PhotoStoreHandler._AuthorizeUser(self._client, episode_id, photo_id, write_access=True)

    # Get photo metadata, which will be used to create the upload URL.
    photo = yield gen.Task(Photo.Query, self._client, photo_id, None)

    # Get name of MD5 attribute in the photo metadata.
    if suffix == '.o':
      attr_name = 'orig_md5'
    elif suffix == '.f':
      attr_name = 'full_md5'
    elif suffix == '.m':
      attr_name = 'med_md5'
    elif suffix == '.t':
      attr_name = 'tn_md5'
    else:
      raise web.HTTPError(404, 'Photo not found; "%s" suffix is invalid.' % suffix)

    # Check for the existence of the photo's image data in S3.
    etag = yield gen.Task(Photo.IsImageUploaded, self._obj_store, photo.photo_id, suffix)

    expected_md5 = getattr(photo, attr_name)
    if expected_md5 != actual_md5:
      if etag is None:
        # Since there is not yet any photo image data, update the photo metadata to be equal to the
        # actual MD5 value.
        setattr(photo, attr_name, actual_md5)
        yield gen.Task(photo.Update, self._client)

        # Redirect to the S3 location.
        self.redirect(_GetUploadUrl(photo, request_md5))
      else:
        # The client often sends mismatched MD5 values due to non-deterministic JPG creation IOS code.
        # Only log the mismatch if it's an original photo to avoid spamming logs.
        if suffix == '.o':
          logging.error('Content-MD5 header "%s" does not match expected MD5 "%s"' %
                        (actual_md5, expected_md5))

        self.set_status(400)
        self.finish()
    else:
      # Check for If-None-Match header, which is used by client to check whether photo image data
      # already exists (and therefore no PUT of the image data is needed).
      match_etag = self.request.headers.get('If-None-Match', None)
      if match_etag is not None and etag is not None and (match_etag == '*' or match_etag == etag):
        # Photo image data exists and is not modified, so no need for client to PUT it again.
        self.set_status(httplib.NOT_MODIFIED)
        self.finish()
      else:
        # Redirect to the S3 upload location.
        self.redirect(_GetUploadUrl(photo, request_md5))

  @classmethod
  @gen.coroutine
  def GetPhotoUrl(cls, client, obj_store, episode_id, photo_id, suffix):
    """Checks that the current user (in Viewfinder context) is authorized to get the specified
    photo, and returns a signed S3 URL for the photo if so.
    """
    yield gen.Task(PhotoStoreHandler._AuthorizeUser, client, episode_id, photo_id, write_access=False)
    raise gen.Return(GeneratePhotoUrl(obj_store, photo_id, suffix))

  @classmethod
  @gen.coroutine
  def _AuthorizeUser(cls, client, episode_id, photo_id, write_access):
    """Checks that the current user (in Viewfinder context) user is authorized to access the given photo:
      1. The photo must exist, and be in the given episode
      2. The photo must not be unshared
      3. If uploading the photo, the user must be the episode owner
      4. A prospective user has access only to photos in the viewpoint specified in the cookie
    """
    context = base.ViewfinderContext.current()
    if context is None or context.user is None:
      raise web.HTTPError(401, 'You are not logged in. Only users that have logged in can access this URL.')

    user_id = context.user.user_id
    post_id = Post.ConstructPostId(episode_id, photo_id)

    episode, post = yield [gen.Task(Episode.QueryIfVisible, client, user_id, episode_id, must_exist=False),
                           gen.Task(Post.Query, client, episode_id, photo_id, None, must_exist=False)]

    if episode is None or post is None:
      raise web.HTTPError(404, 'Photo was not found or you do not have permission to view it.')

    if write_access and episode.user_id != user_id:
      raise web.HTTPError(403, 'You do not have permission to upload this photo; it is not owned by you.')

    if post.IsUnshared():
      raise web.HTTPError(403, 'This photo can no longer be viewed; it was unshared.')

    # BUGBUG(Andy): The 1.5 client has a bug where it always passes in the library episode id
    # when trying to fetch a photo, even if the photo is part of a conversation. This results
    # in 403 errors when a user tries to sync to their library. For now, I'm disabling this
    # check. Once 2.0 has established itself, I'll re-enable the check. 
    #if post.IsRemoved():
    #  raise web.HTTPError(403, 'This photo can no longer be viewed; it was removed.')

    if not context.CanViewViewpoint(episode.viewpoint_id):
      # Always allow system viewpoints to be accessed by a prospective user.
      viewpoint = yield gen.Task(Viewpoint.Query, client, episode.viewpoint_id, None)
      if not viewpoint.IsSystem():
        raise web.HTTPError(403, 'You do not have permission to view this photo. '
                                 'To see it, you must register an account.')

  def _IsInteractiveRequest(self):
    """Always returns false, as this API is accessed programatically."""
    return False
