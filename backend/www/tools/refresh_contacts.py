# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Refreshes an identity's contacts.

Usage:

python backend/www/tools/refresh_contacts.py --identity="Email:spencer.kimball@emailscrubbed.com"
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import logging
import sys

from tornado import ioloop, options
from viewfinder.backend.base import util
from viewfinder.backend.db.db_client import DBClient
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.user import User
from viewfinder.backend.www import www_main

options.define('identity', default='', help='identity of inviter')


def _Unlink(callback):
  assert options.options.identity, 'must specify --identity'
  client = DBClient.Instance()

  def _OnQueryIdentity(ident):
    assert ident.authority, 'unauthenticated identity has no associated contacts: %r' % ident
    assert ident.access_token, 'identity has no access token: %r' % ident
    ident.FetchContacts(client, callback)

  Identity.Query(client, options.options.identity, None, _OnQueryIdentity)


if __name__ == '__main__':
  www_main.InitAndRun(_Unlink)
