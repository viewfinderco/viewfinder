# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Traverses the entire photo table, rewriting all photo assets by
reading them and writing them to new names. The rewrites are
determined as follows:

For p in photos:
  pid   => pid.o
  pid_f => pid.f
  pid_m => pid.m
  pid_t => pid.t

Usage:

python backend/storage/tools/rename_photo_assets.py [--copy_files|--verify_files|--REALLY_DELETE_OLD] [--limit=<limit>]
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging

from collections import deque
from functools import partial
from tornado import options
from viewfinder.backend.base import util
from viewfinder.backend.db.db_client import DBClient
from viewfinder.backend.db.photo import Photo
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.www import www_main

options.define('limit', default=None, help='limit on the total number of renames')
options.define('verify_files', default=False, help='fetch old and new and verify the bytes match')
options.define('copy_files', default=False, help='rename files by copying them from old filename to new')
options.define('REALLY_DELETE_OLD', default=False, help='delete old filenames; requires --verify_files')

_SCAN_LIMIT = 100
"""Limit for photos scanned with each DB operation."""

_INFLIGHT_LIMIT = 20
"""Maximum number of photo fetch / store renames allowed inflight."""

_CONTENT_TYPE = 'image/jpeg'
"""The default content type for copied image assets."""


def _OnScan(final_cb, client, count, scan_result):
  """Processes each photo from scan."""
  max_count = int(options.options.limit)
  photos, last_key = scan_result
  if options.options.limit and count + len(photos) > max_count:
    photos = photos[:max_count - count]
  logging.info('processing next %d photos' % len(photos))
  count += len(photos)

  obj_store = ObjectStore.GetInstance(ObjectStore.PHOTO)
  pending = deque(photos)
  inflight = set()

  def _OnSinkPhotoGet(ak, nak, callback, source_bytes, sink_bytes):
    """Verifies that the source and sink bytes match."""
    logging.info('got sink photo %s: %d bytes' % (nak, len(sink_bytes)))
    inflight.remove(ak)
    if source_bytes != sink_bytes:
      logging.error('source and sink bytes don\'t match! deleting sink to retry')
      obj_store.Delete(nak, callback)
      return
    logging.info('verified %s => %s' % (ak, nak))
    if options.options.REALLY_DELETE_OLD:
      logging.info('deleting %s' % ak)
      obj_store.Delete(ak, callback)
    else:
      callback()

  def _OnPhotoPut(ak, nak, callback, photo_bytes):
    """Removes the asset from inflight map."""
    logging.info('copied %s => %s' % (ak, nak))
    if options.options.verify_files:
      obj_store.Get(nak, partial(_OnSinkPhotoGet, ak, nak, callback, photo_bytes))
    else:
      inflight.remove(ak)
      callback()

  def _OnErrorSinkGet(ak, nak, callback, photo_bytes, type, value, tb):
    if options.options.copy_files:
      logging.info('copying...')
      obj_store.Put(nak, photo_bytes, partial(_OnPhotoPut, ak, nak, callback, photo_bytes),
                    content_type=_CONTENT_TYPE)
    else:
      logging.warning('old-suffix photo asset has not been copied: %s' % ak)
      inflight.remove(ak)
      callback()

  def _OnPhotoGet(ak, nak, callback, photo_bytes):
    """Get the sink photo to determine whether we need to copy. If the
    sink photo exists, the bytes are compared to the source as verification.
    """
    logging.info('got photo %s: %d bytes' % (ak, len(photo_bytes)))
    if options.options.verify_files or options.options.copy_files:
      with util.MonoBarrier(partial(_OnSinkPhotoGet, ak, nak, callback, photo_bytes),
                            on_exception=partial(_OnErrorSinkGet, ak, nak, callback, photo_bytes)) as b:
        obj_store.Get(nak, b.Callback())
    else:
      logging.info('fetched %d bytes for asset %s; not copying or verifying' %
                   (len(photo_bytes), ak))
      inflight.remove(ak)
      callback()

  def _OnErrorGet(ak, callback, type, value, tb):
    logging.info('no asset %s' % ak)
    inflight.remove(ak)
    callback()

  def _OnProcessed(photo, callback):
    logging.info('processed photo %s' % photo.photo_id)
    photo.new_assets = None
    photo.Update(client, callback)

  def _ProcessPending():
    while len(inflight) < _INFLIGHT_LIMIT and len(pending) > 0:
      photo = pending.popleft()
      #if options.options.copy_files and photo.new_assets == 'copied':
      #  continue
      with util.Barrier(partial(_OnProcessed, photo, _ProcessPending)) as b:
        for ak, nak in [(fmt % photo.photo_id, nfmt % photo.photo_id) \
                          for fmt, nfmt in (('%s', '%s.o'),
                                            ('%s_f', '%s.f'),
                                            ('%s_m', '%s.m'),
                                            ('%s_t', '%s.t'))]:
          assert ak not in inflight, ak
          inflight.add(ak)
          finish_cb = b.Callback()
          with util.MonoBarrier(partial(_OnPhotoGet, ak, nak, finish_cb),
                                on_exception=partial(_OnErrorGet, ak, finish_cb)) as get_b:
            obj_store.Get(ak, get_b.Callback())

    if len(pending) == 0 and len(inflight) == 0:
      if last_key and count < max_count:
        Photo.Scan(client, col_names=None, limit=_SCAN_LIMIT,
                   excl_start_key=last_key, callback=partial(_OnScan, final_cb, client, count))
      else:
        logging.info('finished rename of %d photos' % count)
        final_cb()

  _ProcessPending()


def _Start(callback):
  """Scans the entire photo table, renaming existing photo asset files
  from old names to new. If deletion is specified, removes old file. If
  neither deletion nor rename is specified, simply logs rename intention
  and delete intention.
  """
  if options.options.REALLY_DELETE_OLD:
    assert options.options.verify_files, 'must specify --verify_files to delete'
  client = DBClient.Instance()
  Photo.Scan(client, col_names=None, limit=_SCAN_LIMIT,
             excl_start_key=None, callback=partial(_OnScan, callback, client, 0))

if __name__ == '__main__':
  www_main.InitAndRun(_Start)
