# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Handlers for rendering views, or streams of images.

Views are searches over the image database in the context of a
particular logged in user, browser-reported location, and current
time.

  ViewHandler: Returns JSON data containing image locations based
               on request parameters.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import base

from functools import partial
from operator import attrgetter
from tornado import auth, template
from viewfinder.backend.base import handler
from viewfinder.backend.db import contact, user

class ViewHandler(base.BaseHandler):
  """Displays the main /view page."""
  @handler.authenticated(allow_prospective=True)
  @handler.asynchronous(datastore=True)
  def get(self):
    context = base.ViewfinderContext.current()
    self.render('view.html', 
                is_registered=context.user.IsRegistered(),
                user_info={'user_id' : context.user.user_id,
                           'name' : context.user.name,
                           'email' : context.user.email,
                           'phone' : context.user.phone,
                           'default_viewpoint_id' : context.user.private_vp_id
                           },
                viewpoint_id=context.viewpoint_id)


class ViewBetaHandler(base.BaseHandler):
  """Displays a beta version of the /view page, which may have additional features enabled for testing."""
  @handler.authenticated(allow_prospective=True)
  @handler.asynchronous(datastore=True)
  def get(self):
    context = base.ViewfinderContext.current()
    self.render('view_beta.html',
                is_registered=context.user.IsRegistered(),
                user_id=context.user.user_id,
                viewpoint_id = context.viewpoint_id)
