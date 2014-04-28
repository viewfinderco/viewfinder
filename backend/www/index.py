# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Handler for front page of site.

  IndexHandler
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

from tornado import web
import base

class IndexHandler(base.BaseHandler):
  def get(self):
    """If logged in, redirect to /view. Otherwise, render index.html content."""
    cur_user = self.get_current_user()
    if cur_user is not None and cur_user.IsRegistered():
      self.redirect('/view')
    else:
      self.render('square.html')


class RedirectHandler(web.RequestHandler):
  """Handler which redirects insecure traffic to a secure port."""
  def get(self, path):
    self._Redirect(path)
  def post(self, path):
    self._Redirect(path)
  def put(self, path):
    self._Redirect(path)
  def delete(self, path):
    self._Redirect(path)
  def head(self, path):
    self._Redirect(path)
  def options(self, path):
    self._Redirect(path)

  def _Redirect(self, path):
    redirect_port = self.settings['redirect_port']
    if redirect_port != 443:
      self.redirect('https://%s:%d/%s' % (self.settings['host'], redirect_port, path))
    else:
      self.redirect('https://%s/%s' % (self.settings['host'], path))
