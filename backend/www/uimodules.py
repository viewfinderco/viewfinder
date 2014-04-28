# Copyright 2012 Viewfinder Inc. All Rights Reserved.
""" UI Modules used by viewfinder. """

import posixpath
from tornado import options
from tornado.web import UIModule
from viewfinder.backend.base import environ
from viewfinder.backend.resources.resources_mgr import ResourcesManager
from viewfinder.backend.www.basic_auth import BasicAuthHandler

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'


class Header(UIModule):
  """Module for rendering the standard viewfinder header.  Should be included
  on every viewfinder page.  Obsolete: should be phased out in favor of Base
  uimodule.
  """
  def render(self, **settings):
    if isinstance(self.handler, BasicAuthHandler):
      # Will not try to render unless there is a current user.
      user = self.handler.get_current_user()
      if user is not None:
        name = user
      else:
        name = None
    else:
      name = self.handler._GetCurrentUserName()
    return self.render_string('header_module.html', name=name, **settings)

  def javascript_files(self):
    jsfiles = ResourcesManager.Instance().GetAssetPaths('header_js')

    if environ.ServerEnvironment.IsDevBox():
      jsfiles.append('js/testutils.js')

    return jsfiles

  def css_files(self):
    return ResourcesManager.Instance().GetAssetPaths('header_css')


class Base(UIModule):
  """Module for including javascript and css files common to all pages."""
  def render(self, **settings):
    return self.render_string('base_module.html', **settings)

  def javascript_files(self):
    jsfiles = ResourcesManager.Instance().GetAssetPaths('base_js')

    if environ.ServerEnvironment.IsDevBox():
      jsfiles.append('js/testutils.js')

    return jsfiles

  def css_files(self):
    return ResourcesManager.Instance().GetAssetPaths('base_css')


class Square(UIModule):
  """Module for acquisition notice."""
  def render(self, **settings):
    return ''

  def javascript_files(self):
    return ResourcesManager.Instance().GetAssetPaths('square_js')

  def css_files(self):
    return ResourcesManager.Instance().GetAssetPaths('square_css')


class View(UIModule):
  """Module which creates the primary viewfinder gallery application."""
  def render(self, **settings):
    return self.render_string('view_module.html', **settings)

  def javascript_files(self):
    return ResourcesManager.Instance().GetAssetPaths('view_js')

  def css_files(self):
    return ResourcesManager.Instance().GetAssetPaths('view_css')


class Admin(UIModule):
  """Module which marks all administrative pages.  Includes the navigation
  sidebar and a variety of scripts and stylesheets files used by admin pages.
  """
  def render(self, **settings):
    hg_revision = environ.ServerEnvironment.GetHGRevision()
    return self.render_string('admin_module.html', hg_revision=hg_revision, **settings)

  def javascript_files(self):
    return ResourcesManager.Instance().GetAssetPaths('admin_js')

  def css_files(self):
    return ResourcesManager.Instance().GetAssetPaths('admin_css')


class Script(UIModule):
  """ Simple module which, when used from a template, will result in a
  javascript file being embedded in the application.  Duplicate inclusions
  of the same file will result in the file being included in the resulting
  page only once.
  """
  JS_SUBDIR = 'js'

  def __init__(self, handler):
    super(Script, self).__init__(handler)
    self._js_file_set = set()
    self._js_files = []

  def render(self, file):
    file = posixpath.join(self.JS_SUBDIR, file)
    if not file in self._js_file_set:
      self._js_file_set.add(file)
      self._js_files.append(file)
    return ""

  def javascript_files(self):
    return self._js_files


class Css(UIModule):
  """ Simple module which, when used from a template, will result in a
  CSS file being linked in the application.  Duplicate inclusions of the
  same file will result in the file being included in the resulting
  html only once.
  """
  CSS_SUBDIR = 'css'

  def __init__(self, handler):
    super(Css, self).__init__(handler)

    # set is used to quickly test for uniqueness
    self._css_file_set = set()
    self._css_files = []

  def render(self, file):
    file = posixpath.join(self.CSS_SUBDIR, file)
    if not file in self._css_file_set:
      self._css_file_set.add(file)
      self._css_files.append(file)
    return ""

  def css_files(self):
    return self._css_files


class Auth(UIModule):
  """Module which creates the primary viewfinder authorization screens."""
  def render(self, prospective=False, signup_ident=None, **settings):
    return self.render_string('auth_module.html', prospective=prospective, signup_ident=signup_ident, **settings)

  def javascript_files(self):
    """Currently includes all JS files used by view module."""
    resourceManager = ResourcesManager.Instance()
    return resourceManager.GetAssetPaths('view_js') + resourceManager.GetAssetPaths('auth_js')

  def css_files(self):
    return ResourcesManager.Instance().GetAssetPaths('auth_css')
