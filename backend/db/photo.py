# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Viewfinder photo.

  Photo: viewfinder photo information
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging

from tornado import gen, httpclient, options
from viewfinder.backend.base import constants
from viewfinder.backend.base.exceptions import InvalidRequestError, PermissionError, ServiceUnavailableError
from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.asset_id import IdPrefix, ConstructTimestampAssetId, DeconstructTimestampAssetId, VerifyAssetId
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.hash_base import DBHashObject
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.user_photo import UserPhoto
from viewfinder.backend.resources.message.error_messages import SERVICE_UNAVAILABLE


@DBObject.map_table_attributes
class Photo(DBHashObject):
  """Viewfinder photo data object."""
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.PHOTO)

  # The period (in seconds) for which a photo that was shared directly
  # with other users can be fully unshared.
  CLAWBACK_GRACE_PERIOD = constants.SECONDS_PER_WEEK

  # There's a set of attributes which are allowed to be updated when creating
  # photo metadata when the photo metadata already exists (but not after S3 upload of data).  This is to handle a
  # special case in the client where MD5 generation for photo data isn't deterministic (platform weirdness).
  PHOTO_CREATE_ATTRIBUTE_UPDATE_ALLOWED_SET = ('tn_md5', 'med_md5', 'orig_md5', 'full_md5')

  def __init__(self, photo_id=None):
    super(Photo, self).__init__()
    self.photo_id = photo_id

  def MakeMetadataDict(self, post, user_post, user_photo):
    """Constructs a dictionary containing photo metadata attributes, overridden by post and
    user post attributes where required.
    """
    ph_dict = self._asdict()
    labels = post.labels.combine()
    if user_post is not None:
      labels = labels.union(user_post.labels.combine())
    asset_keys = set()
    if user_photo is not None and user_photo.asset_keys:
      asset_keys.update(user_photo.asset_keys)
    if asset_keys:
      ph_dict['asset_keys'] = list(UserPhoto.MakeAssetFingerprintSet(asset_keys))
    if len(labels) > 0:
      ph_dict['labels'] = list(labels)
    ph_dict.pop('client_data', None)
    return ph_dict

  @classmethod
  def ConstructPhotoId(cls, timestamp, device_id, uniquifier):
    """Returns a photo id constructed from component parts. Photos
    sort from newest to oldest. See "ConstructTimestampAssetId" for
    details of the encoding.
    """
    return ConstructTimestampAssetId(IdPrefix.Photo, timestamp, device_id, uniquifier)

  @classmethod
  def DeconstructPhotoId(cls, photo_id):
    """Returns the components of a photo id: timestamp, device_id, and
    uniquifier.
    """
    return DeconstructTimestampAssetId(IdPrefix.Photo, photo_id)

  @classmethod
  @gen.coroutine
  def VerifyPhotoId(cls, client, user_id, device_id, photo_id):
    """Ensures that a client-provided photo id is valid according
    to the rules specified in VerifyAssetId.
    """
    yield VerifyAssetId(client, user_id, device_id, IdPrefix.Photo, photo_id, has_timestamp=True)

  @classmethod
  @gen.coroutine
  def CreateNew(cls, client, **ph_dict):
    """Creates a new photo metadata object from the provided dictionary.

    Returns: new photo.
    """
    assert 'photo_id' in ph_dict and 'user_id' in ph_dict and 'episode_id' in ph_dict, ph_dict
    photo = Photo.CreateFromKeywords(**ph_dict)
    yield photo.Update(client)
    raise gen.Return(photo)

  @classmethod
  @gen.coroutine
  def UpdateExisting(cls, client, **ph_dict):
    """Updates existing photo metadata from the provided dictionary."""
    assert 'timestamp' not in ph_dict and 'episode_id' not in ph_dict and 'user_id' not in ph_dict, ph_dict
    photo = Photo.CreateFromKeywords(**ph_dict)
    yield photo.Update(client)

  @classmethod
  @gen.coroutine
  def CheckCreate(cls, client, **ph_dict):
    """For a photo that already exists, check that its attributes match.
    Return: photo, if it already exists.
    """
    assert 'photo_id' in ph_dict and 'user_id' in ph_dict, ph_dict
    photo = yield Photo.Query(client, ph_dict['photo_id'], None, must_exist=False)
    # All attributes should match between the ph_dict and persisted photo metadata
    # (except those allowed to be different).
    if photo is not None and \
        photo.HasMismatchedValues(Photo.PHOTO_CREATE_ATTRIBUTE_UPDATE_ALLOWED_SET, **ph_dict):
      logging.warning('Photo.CheckCreate: keyword mismatch failure: %s, %s' % (photo, ph_dict))
      raise InvalidRequestError('There is a mismatch between request and persisted photo metadata during photo '
                                  'metadata creation.')
    raise gen.Return(photo)

  @classmethod
  @gen.coroutine
  def IsImageUploaded(cls, obj_store, photo_id, suffix):
    """Determines whether a photo's image data has been uploaded to S3
    by using a HEAD request. If the image exists, then invokes callback
    with the Etag of the image. Otherwise, invokes the callback with None.
    """
    url = obj_store.GenerateUrl(photo_id + suffix, method='HEAD')
    http_client = httpclient.AsyncHTTPClient()
    try:
      response = yield http_client.fetch(url,
                                         method='HEAD',
                                         validate_cert=options.options.validate_cert)
    except httpclient.HTTPError as e:
      if e.code == 404:
        raise gen.Return(None)
      else:
        logging.warning('Photo store S3 HEAD request error: [%s] %s' % (type(e).__name__, e.message))
        raise ServiceUnavailableError(SERVICE_UNAVAILABLE)

    if response.code == 200:
      raise gen.Return(response.headers['Etag'])
    else:
      raise AssertionError('failure on HEAD request to photo %s: %s' %
                           (photo_id + suffix, response))

  @classmethod
  @gen.coroutine
  def UpdatePhoto(cls, client, act_dict, **ph_dict):
    """Updates photo to metadata object from the provided dictionary."""
    assert 'photo_id' in ph_dict and 'user_id' in ph_dict, ph_dict
    photo = yield Photo._CheckUpdate(client, **ph_dict)

    assert photo is not None, ph_dict
    assert photo.photo_id == ph_dict['photo_id'], (photo, ph_dict)
    assert photo.user_id == ph_dict['user_id'], (photo, ph_dict)

    asset_keys = ph_dict.pop('asset_keys', None)
    if asset_keys:
      assert ph_dict['user_id']

      up_dict = {'user_id': ph_dict['user_id'],
                 'photo_id': ph_dict['photo_id'],
                 'asset_keys': asset_keys}
      user_photo = UserPhoto.CreateFromKeywords(**up_dict)
    else:
      user_photo = None

    photo.UpdateFromKeywords(**ph_dict)

    # Aborts are NOT allowed after this point because we're about to modify db state.
    # Ensure that we haven't modified it yet.
    client.CheckDBNotModified()

    yield photo.Update(client)

    if user_photo is not None:
      yield user_photo.Update(client)

  @classmethod
  @gen.coroutine
  def _CheckUpdate(cls, client, **ph_dict):
    """Checks that the photo exists.  Checks photo metadata object against the provided dictionary.
    Checks that the user_id in the dictionary matches the one on the photo.
    Returns: photo
    """
    assert 'photo_id' in ph_dict and 'user_id' in ph_dict, ph_dict
    photo = yield Photo.Query(client, ph_dict['photo_id'], None, must_exist=False)

    if photo is None:
      raise InvalidRequestError('Photo "%s" does not exist and so cannot be updated.' %
                                ph_dict['photo_id'])

    if photo.user_id != ph_dict['user_id']:
      raise PermissionError('User id of photo does not match requesting user')

    raise gen.Return(photo)

  @classmethod
  @gen.coroutine
  def UpdateOperation(cls, client, act_dict, ph_dict):
    """Updates photo metadata."""
    assert ph_dict['user_id'] == Operation.GetCurrent().user_id

    # Call helper to carry out update of the photo.
    yield Photo.UpdatePhoto(client, act_dict=act_dict, **ph_dict)
