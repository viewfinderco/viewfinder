# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Resources Manager.

Provides support for loading and rendering of various Viewfinder localizable resources,
such as html files, email templates, error strings, etc.

Supports precompilation of javascript and css.  By default, javascript and css are left unmodified
for ease of debugging.  You can also use --compile_assets=dynamic to develop with the processed code.
In production, --compile_assets=static should be used, and the assets should be precompiled with

  python -m viewfinder.backend.resources.resources_mgr build
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'

import os
import re

from tornado import options
from tornado import template
import webassets

options.define('compile_assets', default='none',
               help='"dynamic" to minify css and javascript on the fly, "static" to use precompiled versions, or '
               '"none" to serve unmodified source')

class ResourcesManager(object):
  _STATIC_URL_RE = re.compile('/static/([^?]*)')

  def __init__(self):
    # Set the resources directories.
    self.resources_path = os.path.dirname(__file__)
    self.static_path = os.path.join(self.resources_path, 'static')
    self.template_path = os.path.join(self.resources_path, 'template')
    self.offboarding_path = os.path.join(self.resources_path, 'offboarding')

    # Create a shared instance of the Tornado template loader.
    self._loader = template.Loader(self.template_path)

    self._assets = webassets.Environment(self.static_path, '/static')
    asset_mode = options.options.compile_assets.lower()
    assert asset_mode in ('static', 'dynamic', 'none')
    if asset_mode == 'none':
      self._assets.debug = True
    elif asset_mode == 'static':
      self._assets.auto_build = False
    self._DefineBundles()

  def LoadTemplate(self, name):
    """Load a template and return it wrapped in a tornado Template object."""
    return self._loader.load(name)

  def GenerateTemplate(self, name, **kwargs):
    """Load and generate the template with the given name, using the given arguments."""
    return self._loader.load(name).generate(**kwargs)

  def GetAssetPaths(self, name):
    """Returns a list of asset urls for the given resource group.

    If --compile_assets is true, this will be the compiled output, otherwise it will return the
    input files directly.

    The returned paths should be passed through static_url() to get a full versioned url
    (this is done automatically for UIModules, so in a module you can return this list directly
    in methods like UIModule.javascript_files).
    """
    # webassets adds the /static prefix and its own version suffix; we need to strip those off
    # so static_url can re-add the ones used by tornado's StaticFileHandler.
    urls = self._assets[name].urls()
    return [ResourcesManager._STATIC_URL_RE.match(url).group(1) for url in urls]

  def GetOffboardingPath(self):
    """Return path to assets to be included in user off boarding zip files"""
    return self.offboarding_path

  @staticmethod
  def Instance():
    """Get current global instance of the resource manager."""
    if not hasattr(ResourcesManager, '_instance'):
      ResourcesManager._instance = ResourcesManager()
    return ResourcesManager._instance

  def _DefineBundles(self):
    JS_FILTERS = 'jsmin'
    # cssrewrite fixes relative urls; cssmin removes whitespace and comments.
    CSS_FILTERS = 'cssrewrite,cssmin'

    self._assets.register('header_js',
                          'js/third_party/underscore.js',
                          'js/viewfinder.js',
                          filters=JS_FILTERS,
                          output='gen/header.js')

    self._assets.register('header_css',
                          'css/viewfinder.css',
                          'css/header.css',
                          filters=CSS_FILTERS,
                          output='gen/header.css')

    self._assets.register('base_js',
                          'js/third_party/underscore.js',
                          'js/viewfinder.js',
                          filters=JS_FILTERS,
                          output='gen/base.js')

    self._assets.register('base_css',
                          'css/viewfinder.css',
                          filters=CSS_FILTERS,
                          output='gen/base.css')

    self._assets.register('view_js',
                          'js/third_party/backbone.js',
                          'js/third_party/backbone.forms.js',
                          'js/third_party/dateformat.js',
                          'js/third_party/jquery.placeholder.js',
                          'js/third_party/jquery.hammer.js',
                          'js/third_party/fastclick.js',
                          'js/scrolleffect.js',
                          'js/query.js',
                          'js/models.js',
                          'js/views.js',
                          filters=JS_FILTERS,
                          output='gen/view.js')

    self._assets.register('view_css',
                          'css/view.css',
                          filters=CSS_FILTERS,
                          output='gen/view.css')

    self._assets.register('admin_js',
                          'js/third_party/jquery.dataTables.js',
                          'js/third_party/jquery.jqplot.js',
                          'js/third_party/jquery-ui-1.10.2.custom.min.js',
                          'js/third_party/jquery.ui.datetimepicker.js',
                          filters=JS_FILTERS,
                          output='gen/admin.js')

    self._assets.register('admin_css',
                          'css/button.css',
                          'css/dialog.css',
                          'css/admin.css',
                          'css/jquery.dataTables.css',
                          'css/jquery.jqplot.css',
                          'css/jquery.timepicker.css',
                          'css/ui-lightness/jquery-ui-1.10.2.custom.min.css',
                          filters=CSS_FILTERS,
                          output='gen/admin.css')

    self._assets.register('auth_js',
                          'js/third_party/phoneformat.js',
                          filters=JS_FILTERS,
                          output='gen/auth.js')

    self._assets.register('auth_css',
                          'css/auth.css',
                          filters=CSS_FILTERS,
                          output='gen/auth.css')

    self._assets.register('square_js',
                          'js/third_party/backbone.js',
                          'js/views.js',
                          'js/models.js',
                          filters=JS_FILTERS,
                          output='gen/square.js')

    self._assets.register('square_css',
                          'css/square.css',
                          filters=CSS_FILTERS,
                          output='gen/square.css')

def main():
  args = options.parse_command_line()
  # Force asset compilation in command-line mode.
  options.options.compile_assets = 'dynamic'

  assets = ResourcesManager.Instance()._assets
  import webassets.script
  webassets.script.main(args, env=assets)

if __name__ == '__main__':
  main()
