# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Manage entries in the AdminPermissions table.

Usage:

# Add/modify a user as root.
python admin_tool.py --op=set --user=<username> --rights=root
# Add/modify a user as support.
python admin_tool.py --op=set --user=<username> --rights=support
# Add/modify a user with no rights.
python admin_tool.py --op=set --user=<username>
# Delete a user.
python admin_tool.py --op=del --user=<username>

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import logging
import sys

from tornado import options
from viewfinder.backend.base import main
from viewfinder.backend.db import db_client, vf_schema
from viewfinder.backend.db.admin_permissions import AdminPermissions

options.define('user', default=None, help='user to set/delete')
options.define('rights', default=None, multiple=True, help='list of rights ("root", "support"). Omit to clear.')
options.define('op', default=None, help='command: set, del')

def ProcessAdmins(callback):
  client = db_client.DBClient.Instance()

  assert options.options.user is not None
  assert options.options.op is not None

  if options.options.op == 'set':
    permissions = AdminPermissions(options.options.user, options.options.rights)
    logging.info('committing %r' % permissions)
    permissions.Update(client, callback)

  elif options.options.op == 'del':
    admin = AdminPermissions(options.options.user)
    logging.info('deleting %r' % admin)
    admin.Delete(client, callback)

  else:
    logging.error('unknown op: %s' % options.options.op)
    callback()


if __name__ == '__main__':
  sys.exit(main.InitAndRun(ProcessAdmins))
