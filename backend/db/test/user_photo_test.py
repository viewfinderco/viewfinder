# Copyright 2013 Viewfinder Inc. All Rights Reserved
"""Tests for UserPhoto data object."""

__author__ = 'ben@emailscrubbed.com (Ben Darnell)'

from base_test import DBBaseTestCase

from viewfinder.backend.db.user_photo import UserPhoto
from viewfinder.backend.db import versions

class UserPhotoTestCase(DBBaseTestCase):
  def testAssetKeyToFingerprint(self):
    def test(asset_key, expected):
      self.assertEqual(UserPhoto.AssetKeyToFingerprint(asset_key), expected)
    test('', None)
    test('a/', None)
    test('a/b', None)
    test('a/#', None)
    test('a/b#', None)
    test('a/b#c', 'a/#c')
    test('a/b##c', 'a/#c')
    test('a/assets-library://asset/asset.JPG?id=D31F1D3C-CFB7-458F-BACD-7862D72098A6&ext=JPG#e5ad400c2214088928ef8400dcfb87bb3059b742',
         'a/#e5ad400c2214088928ef8400dcfb87bb3059b742')
    test('a/assets-library://asset/asset.JPG?id=D31F1D3C-CFB7-458F-BACD-7862D72098A6&ext=JPG',
         None)
    test('a/#e5ad400c2214088928ef8400dcfb87bb3059b742',
         'a/#e5ad400c2214088928ef8400dcfb87bb3059b742')

  def testMigration(self):
    user_photo = UserPhoto.CreateFromKeywords(
      user_id=1, photo_id='p1',
      asset_keys=['a/b', 'a/c#d', 'a/e#d', 'a/f#g'])
    user_photo._version = versions.REMOVE_ASSET_URLS.rank - 1
    self._RunAsync(versions.Version.MaybeMigrate, self._client, user_photo,
                   [versions.REMOVE_ASSET_URLS])
    print user_photo
    self.assertEqual(user_photo.asset_keys.combine(), set(['a/#d', 'a/#g']))

  def testMergeAssetKeys(self):
    user_photo = UserPhoto.CreateFromKeywords(
      user_id=1, photo_id='p1',
      asset_keys=['a/#b', 'a/#f'])
    user_photo.MergeAssetKeys(['a/b#c', 'a/d#c', 'a/e#f'])
    self.assertEqual(user_photo.asset_keys.combine(), set(['a/#b', 'a/#c', 'a/#f']))
