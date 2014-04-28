# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Handlers for viewing and downloading server logs.

  LogHandler: Displays contents of a chosen log file.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import os
import stat
import time
from tornado import auth, template

from viewfinder.backend.base import handler, util
from viewfinder.backend.db import schema, vf_schema
from viewfinder.backend.www.admin import admin


class LogHandler(admin.AdminHandler):
  """Lists available server logs."""
  @handler.authenticated()
  @handler.asynchronous(datastore=True)
  @admin.require_permission(level='root')
  def get(self):
    t_dict = self.PermissionsTemplateDict()

    if self.get_argument('file', None):
      log_file = self.get_argument('file')
      assert 'logs_dir' in self.settings, 'logs are only available when server is run daemonized'
      with open(os.path.join(self.settings['logs_dir'], log_file), 'r') as f:
        f.seek(self.get_argument('offset', 0))
        t_dict['log_contents'] = f.read()
      t_dict['log_file'] = log_file
      self.render('log.html', **t_dict)
    else:
      col_names = ['Log fileame', 'Date Created', 'Last Modified', 'Bytes']
      col_data = list()
      assert 'logs_dir' in self.settings, 'logs are only available when server is run daemonized'
      for log_file in sorted(os.listdir(self.settings['logs_dir'])):
        stat = os.stat(os.path.join(self.settings['logs_dir'], log_file))
        col_data.append(['<a href="https://%s/admin/logs?file=%s">%s</a>' % (self.request.host, log_file, log_file),
                         time.asctime(time.gmtime(stat.st_atime)),
                         time.asctime(time.gmtime(stat.st_mtime)), stat.st_size])
      t_dict['col_names'] = col_names
      t_dict['col_data'] = col_data
      self.render('logs.html', **t_dict)
