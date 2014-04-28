# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Utility to create S3 URLs.

Usage:

python -m viewfinder.backend.storage.url_generator --key=key
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import sys
import time

from tornado import httpclient, ioloop, options
from viewfinder.backend.base import main, secrets
from viewfinder.backend.storage.s3_object_store import S3ObjectStore

options.define('key', default='', help='S3 asset key')

def GenerateURL(callback):
  """Runs op on each table listed in --tables."""
  object_store = S3ObjectStore('photos-viewfinder-co')
  upload_url = object_store.GenerateUploadUrl(options.options.key)
  logging.info('PUT URL: %s' % upload_url)
  logging.info('GET URL: %s' % object_store.GenerateUrl(options.options.key))
  callback()


if __name__ == '__main__':
  sys.exit(main.InitAndRun(GenerateURL))
