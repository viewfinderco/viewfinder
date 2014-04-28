# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""HTTP request handler for reading and writing photo image file
assets for automated UI testing.

"""

__author__ = ['greg@emailscrubbed.com (Greg Vandenberg)']

import json
import logging
import os
import shutil

from tornado import gen, options, web
from viewfinder.backend.base import handler
from viewfinder.backend.base.environ import ServerEnvironment
from viewfinder.backend.db.identity import Identity
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.viewpoint import Viewpoint
from viewfinder.backend.www import base

_TEST_HOOKS_NOT_SUPPORTED = 'Test hooks are not supported. They are only supported when ' + \
                            'running on a development machine (using --devbox).'
_TEST_ACTION_NOT_SUPPORTED = 'This action is not supported.'
_STATIC_RESULTS_BASELINE = '/testing/static/results/baseline'
_STATIC_RESULTS_CURRENT = '/testing/static/results/current'

class TestHookHandler(web.RequestHandler):
  """ Handles POST requests and copies a given image to the
  specified destination
  """



  def check_xsrf_cookie(self):
    pass

  @handler.asynchronous(datastore=True, obj_store=True)
  @gen.coroutine
  def post(self, action):

    if not ServerEnvironment.IsDevBox():
      raise web.HTTPError(403, _TEST_HOOKS_NOT_SUPPORTED)

    from PIL import Image, ImageChops

    if action == 'copy':
      logging.info('Updating baseline image')
      urls = {}
      body = json.loads(self.request.body)
      testname = body['testname']
      imagename = body['imagename']
      scheme = body['scheme']

      _FULL_RESULTS_BASELINE = '%s/results/baseline/%s' % (options.options.testing_path, scheme)
      _FULL_RESULTS_CURRENT = '%s/results/current/%s' % (options.options.testing_path, scheme)

      # Overwrite the 'baseline' image for the test with the 'current' image.
      baseline_image = r'%s/%s/%s' % (_FULL_RESULTS_BASELINE, testname, imagename)
      current_image = r'%s/%s/Run 1/%s' % (_FULL_RESULTS_CURRENT, testname, imagename)

      yield self._UpdateImageMaskConfig(testname, imagename, scheme)

      if os.path.exists(current_image):
        shutil.copy(current_image, baseline_image)
        logging.info('Updated baseline image for %s' % testname)

      baseline_web_image = r'%s/%s/%s/%s' % (_STATIC_RESULTS_BASELINE, scheme, testname, imagename)
      current_web_image = r'%s/%s/%s/Run 1/%s' % (_STATIC_RESULTS_CURRENT, scheme, testname, imagename)

      urls['baseline'] = baseline_web_image
      urls['current'] = current_web_image

      # Return JSON result.
      self.write(urls)
      self.finish()
      return

    if action == 'delete':
      body = json.loads(self.request.body)
      testname = body['testname']
      imagename = body['imagename']

      current_image = r'%s/%s/Run 1/%s' % (_FULL_RESULTS_CURRENT, testname, imagename)
      if os.path.exists(current_image) is True:
        os.remove(current_image)
        logging.info('Deleted current capture image for %s' % testname)
      self.finish()
      return

    if action == 'token':
      body = json.loads(self.request.body)
      identity_key = body['auth_info']['identity'];

      identity = yield gen.Task(Identity.Query, self._client, identity_key, None, must_exist=False)
      if identity is None:
        raise web.HTTPError(400, 'Identity does not exist.')

      self.write(identity.access_token)
      self.finish()
      return

    if action == 'image':
      body = json.loads(self.request.body)
      test_name = body['testname']
      image_name = body['imagename']
      scheme = body['scheme']
      _FULL_RESULTS_BASELINE = '%s/results/baseline/%s' % (options.options.testing_path, scheme)
      _FULL_RESULTS_CURRENT = '%s/results/current/%s' % (options.options.testing_path, scheme)

      # get image base name
      tmp = image_name[:-4]
      base, num = tmp.split('|', 1)
      image_base_name = '%s.png' % base

      image1 = r'%s/%s/%s' % (_FULL_RESULTS_BASELINE, test_name, image_base_name)
      image2 = r'%s/%s/Run 1/%s' % (_FULL_RESULTS_CURRENT, test_name, image_name)

      if os.path.exists(image1) and os.path.exists(image2):
        self.set_header('Content-Type', 'application/json; charset=UTF-8')
        im1 = Image.open(image1)
        im2 = Image.open(image2)

        diff = ImageChops.difference(im2, im1)
        result = diff.getbbox() is None
        response = { 'response': result, 'bbox': diff.getbbox() }
        self.write(response)
      self.finish()
      return

    raise web.HTTPError(400, _TEST_ACTION_NOT_SUPPORTED)

  @gen.coroutine
  def _UpdateImageMaskConfig(self, test_name, image_name, scheme):

    _IMAGE_MASK_CONFIG_PATH = os.path.join(options.options.testing_path, 'config')
    _IMAGE_MASK_CONFIG_FILE = '%s/%s/image_masks_json.cfg' % (_IMAGE_MASK_CONFIG_PATH, scheme)
    _FULL_RESULTS_BASELINE = '%s/results/baseline' % options.options.testing_path
    _FULL_RESULTS_CURRENT = '%s/results/current' % options.options.testing_path
    baseline_image = r'%s/%s/%s/%s' % (_FULL_RESULTS_BASELINE, scheme, test_name, image_name)
    current_image = r'%s/%s/%s/Run 1/%s' % (_FULL_RESULTS_CURRENT, scheme, test_name, image_name)

    from PIL import Image, ImageChops

    try:
      im1 = Image.open(baseline_image)
      im2 = Image.open(current_image)
      _IMAGE_MASK_CONFIG = {}
      diff = ImageChops.difference(im2, im1)
      # TODO:  if image delta is smaller than 100 x 100 write to config
      bbox = diff.getbbox()
      if bbox is not None:
        if os.path.exists(_IMAGE_MASK_CONFIG_FILE):
          config_data = open(_IMAGE_MASK_CONFIG_FILE, 'r')
          _IMAGE_MASK_CONFIG = json.load(config_data)
        width = bbox[2] - bbox[0];
        height = bbox[3] - bbox[1]
        if width <= 100 and height <= 100:
          x, y = 0, 0
          mask = { "x":bbox[0], "y":bbox[1], "height":height-1, "width":width-1 }
          logging.info('bbox: %s' % mask)
          if test_name not in _IMAGE_MASK_CONFIG:
            _IMAGE_MASK_CONFIG[test_name] = {}
            _IMAGE_MASK_CONFIG[test_name][image_name] = []
          else:
            if image_name not in _IMAGE_MASK_CONFIG[test_name]:
              _IMAGE_MASK_CONFIG[test_name][image_name] = []
            else:
              # do not allow duplicate masks
              for dict in _IMAGE_MASK_CONFIG[test_name][image_name]:
                if dict['x'] == bbox[0] and dict['y'] == bbox[1]:
                  if dict['height'] == height or dict['width'] == width:
                    return;

          _IMAGE_MASK_CONFIG[test_name][image_name].append(mask)
          cfg_data_file = open(_IMAGE_MASK_CONFIG_FILE, 'w')
          cfg_data_file.write(json.dumps(_IMAGE_MASK_CONFIG))
          logging.info('Updated %s' % _IMAGE_MASK_CONFIG_FILE)
    except (IOError, ValueError) as e:
      logging.exception('Exception during image comparison')


