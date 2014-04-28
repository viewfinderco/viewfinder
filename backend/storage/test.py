#!/usr/bin/env python
#
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

import boto
import sys
from boto.exception import S3ResponseError
from tornado import ioloop, options, web
from viewfinder.backend.base import asyncboto, secrets

options.define("port", default=8888, help="Port to serve HTTP requests")

class S3Handler(web.RequestHandler):
  def initialize(self):
    self.conn = boto.connect_s3(
        aws_access_key_id = secrets.GetSecret('aws_access_key_id').strip(),
        aws_secret_access_key = secrets.GetSecret('aws_secret_access_key').strip())
    self.bucket = self.conn.get_bucket('staging.goviewfinder.com')

  @asyncboto.asyncs3
  def get(self):
    k = self.bucket.new_key(self.get_argument("key"))
    try:
      self.write(k.get_contents_as_string())
    except S3ResponseError:
      self.send_error(404)
      return
    finally:
      k.close()
    self.finish()

def main():
  options.parse_command_line()

  application = web.Application([
      (r"/s3", S3Handler),
      ])

  application.listen(options.options.port)
  ioloop.IOLoop.instance().start()
  return 0

if __name__ == "__main__":
  sys.exit(main())
