# Copyright 2013 Viewfinder Inc. All Rights Reserved
"""UserPhoto data object."""

__author__ = 'ben@emailscrubbed.com (Ben Darnell)'

from tornado import gen

from viewfinder.backend.db import vf_schema
from viewfinder.backend.db.base import DBObject
from viewfinder.backend.db.range_base import DBRangeObject
from viewfinder.backend.db import versions

@DBObject.map_table_attributes
class UserPhoto(DBRangeObject):
  __slots__ = []

  _table = DBObject._schema.GetTable(vf_schema.USER_PHOTO)

  @classmethod
  def AssetKeyToFingerprint(cls, asset_key):
    """Converts an asset key to a fingerprint-only asset key.

    Asset keys from the client may (in 1.4) contain asset urls that
    are only meaningful for that device.  We only want to store
    the fingerprint portion of the asset key.

    If the asset key does not contain a fingerprint, returns None.
    """
    # See DecodeAssetKey() in PhotoTable.mm
    if asset_key.startswith('a/'):
      _, sep, fingerprint = asset_key.rpartition('#')
      if sep and fingerprint:
        return 'a/#' + fingerprint
    return None

  @classmethod
  def MakeAssetFingerprintSet(cls, asset_keys):
    fingerprints = set(UserPhoto.AssetKeyToFingerprint(k) for k in asset_keys)
    # If any keys were missing fingerprints, discard the None entry.
    fingerprints.discard(None)
    return fingerprints

  def MergeAssetKeys(self, new_keys):
    """Merges the asset keys in new_keys into self.asset_keys.

    Returns True if any changes were made.
    """
    changed = False
    for key in new_keys:
      fingerprint = UserPhoto.AssetKeyToFingerprint(key)
      if fingerprint is not None and fingerprint not in self.asset_keys:
        self.asset_keys.add(fingerprint)
        changed = True
    return changed

  @classmethod
  @gen.coroutine
  def CreateNew(cls, client, **up_dict):
    asset_keys = up_dict.pop('asset_keys', [])
    up = UserPhoto.CreateFromKeywords(**up_dict)
    up.MergeAssetKeys(asset_keys)
    yield gen.Task(up.Update, client)

  @classmethod
  @gen.coroutine
  def UpdateOperation(cls, client, up_dict):
    asset_keys = up_dict.pop('asset_keys', [])
    user_photo = yield gen.Task(UserPhoto.Query, client, up_dict['user_id'], up_dict['photo_id'], None, must_exist=False)
    if user_photo is None:
      user_photo = UserPhoto.CreateFromKeywords(**up_dict)
    else:
      yield gen.Task(versions.Version.MaybeMigrate, client, user_photo, [versions.REMOVE_ASSET_URLS])
    user_photo.MergeAssetKeys(asset_keys)
    yield user_photo.Update(client)
