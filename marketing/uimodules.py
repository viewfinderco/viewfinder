import posixpath
from tornado.web import UIModule

class Header(UIModule):
  """Module for rendering the standard viewfinder header.  Should be included
  on every viewfinder page.
  """
  def render(self, **settings):
    name = None
    return self.render_string('header_module.html', name=name, **settings)

  def javascript_files(self):
    jsfiles = ['js/third_party/underscore.js',
              'js/viewfinder.js']

    return jsfiles

  def css_files(self):
    return ['css/viewfinder.css',
            'css/header.css']

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
