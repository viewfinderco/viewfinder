#!/usr/bin/env python

import glob
import hashlib
from PIL import Image, ImageChops, ImageDraw
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import time

from subprocess import call
from tornado import template
from tornado.httpclient import HTTPClient, HTTPError
from tornado.options import options, define
from xml.etree import ElementTree
from viewfinder.backend.base.message import MAX_SUPPORTED_MESSAGE_VERSION

define('clean', type=bool, default=False,
       help='Remove all previous runs')
define('conf', type=str, default='iPhone5-ios7.0',
       help='The configuration to use for this run')
define('testname', type=str, default=None,
       help='name of the test to run')
define('testing_path', type=str, default=None,
       help='base path of the testing dir')
define('list', type=bool, default=False,
       help='list of all available tests')
define('regen', type=bool, default=False,
       help='regenerate html test results')

define('app_id', type=str,
       default='A77B9155-EEB7-443E-B4DC-FF8F266BAD0E',
       help='application id of the simulator app (/Users/%s/Library/Application\ Support' \
        '/iPhone\ Simulator/6.1/Applications/' % os.environ['USER'])
define('simulator', type=bool, default=False,
       help='True to compile the simulator build specified with the ios parameter')

_BASE_URL = 'https://www.goviewfinder.com:8443'

if options.testing_path:
  _BASE_PATH = options.testing_path
else:
  _BASE_PATH = os.path.join(os.environ['VF_HOME'],'clients/ios/testing')

_RESULTS_PATH = os.path.join(_BASE_PATH, 'results')
_SUMMARY = {}
_SNAPSHOTS_PATH = os.path.join(_BASE_PATH, 'snapshots')
_MAX_ARCHIVE_FOLDERS = 20
_CONFIG_DIR_PATH = os.path.join(_BASE_PATH, 'config');

_IMAGE_MASK_CONFIG = None
_SCHEME = None

def GetSchemeConfig():
  global _SCHEME
  config_file = '%s.cfg' % options.conf
  _SCHEME_CONFIG_FILE_PATH = os.path.join(_CONFIG_DIR_PATH, options.conf)
  _SCHEME_CONFIG_FILE = os.path.join(_SCHEME_CONFIG_FILE_PATH, config_file)
  if os.path.exists(_SCHEME_CONFIG_FILE):
    data = open(_SCHEME_CONFIG_FILE, 'r')
    _SCHEME = json.load(data)
  else:
    print 'The config file %s does not exist.' % config_file
    exit()

def SetupImageMasks():
  base_path = os.path.join(_BASE_PATH, 'config');
  config_data_path = os.path.join(base_path, options.conf);
  if not os.path.exists(config_data_path):
    os.makedirs(config_data_path, 0755)
  _IMAGE_MASK_CONFIG_FILE = os.path.join(config_data_path, 'image_masks_json.cfg')
  if os.path.exists(_IMAGE_MASK_CONFIG_FILE):
    config_data = open(_IMAGE_MASK_CONFIG_FILE, 'r')
    return json.load(config_data)
  else:
    print 'The mask config file %s does not exist.' % _IMAGE_MASK_CONFIG_FILE

def GetImageMasks(test_name, image_name):
  mask = None
  if _IMAGE_MASK_CONFIG:
    if test_name in _IMAGE_MASK_CONFIG:
      if image_name in _IMAGE_MASK_CONFIG[test_name]:
        mask = _IMAGE_MASK_CONFIG[test_name][image_name]
  return mask

def ApplyImageMask(test_name, image):
  tmp = image[:-4]
  base, num = tmp.split('|', 1)
  image_base_name = '%s.png' % base
  masks = GetImageMasks(test_name, image_base_name)
  image_name = r'results/current/%s/%s/Run 1/%s' % (options.conf, test_name, image)
  if masks is not None:
    im = Image.open(image_name)
    draw = ImageDraw.Draw(im)
    for mask in masks:
      x = mask['x']
      y = mask['y']
      h = mask['height']
      w = mask['width']
      draw.rectangle([(x,y),(x+w,y+h)], fill="white")
    im.save(image_name, "PNG")

def _ManageArchiveFolders():
  archive_path = os.path.join(_RESULTS_PATH, 'archive')

  # Make sure 'archive' directory exists.
  if not os.path.exists(archive_path):
    os.mkdir(archive_path)

  files = os.listdir(archive_path);
  to_delete = None;

  # Get folders to delete.
  if len(files) >= _MAX_ARCHIVE_FOLDERS:
    to_delete = files[::-1][_MAX_ARCHIVE_FOLDERS-1:]
  if to_delete is not None:
    for name in to_delete:
      fname = os.path.join(archive_path, name)
      print 'Deleting archive folder: %s' % fname
      shutil.rmtree(fname, True, None)

def GetApplicationId(ios):
  """Given the version number of the IOS sdk, determine what the application id is
      that was assigned to the simulator Viewfinder application by walking the filesystem
  """

  temp_path = r'/Users/%s/Library/Application Support/iPhone Simulator/%s/Applications' % \
    (os.environ['USER'],ios)
  try:
    output = subprocess.check_output(['find','.', '-iname','viewfinder.app'],cwd=temp_path)
    # Should have a string like './A77B9155-EEB7-443E-B4DC-FF8F266BAD0E/Viewfinder.app'.

    if len(output) is 0:
      raise IOError

    return output[2:-16]
  except (OSError, IOError) as e:
    print "\nYou are missing the 6.1 IOS simulator... " \
      "You should update the xcode simulators (Product -> Destination -> More Simulators...).\n", e
    exit()

def GetTestNames():
  """Grab the test files in the js directory and store the filenames in a
    test name global dict.
  """
  test_name = options.testname
  test_path = os.path.join(_BASE_PATH, 'tests')
  files = os.listdir(test_path);
  _LOCAL = {}
  for file in files:
    if file.startswith('test') and file.endswith('js'):
      _LOCAL[file[:-3]] = {'name': file[:-3],
                                  'images': [],
                                  'warnings': {},
                                  'alert': None }
  if options.list:
    return _LOCAL.keys()

  if test_name:
    if not test_name in _LOCAL.keys():
      print("Invalid testname provided.  Use --list for a list of all available tests.")
      exit()

    _LOCAL = {}
    _LOCAL[test_name] = { 'name': test_name,
                           'images': [],
                           'warnings': {},
                           'alert': None }
  global _SUMMARY
  _SUMMARY = _LOCAL
  return _LOCAL.keys()

def GetImageNames(test_name):
  """Get the names of all the screenshot images associated with
    the specified test.
  """
  _SUMMARY[test_name]['images'] = []
  current_path = os.path.join(_RESULTS_PATH, 'current')
  test_path = os.path.join(current_path, options.conf);
  if test_name:
    files = os.listdir('%s/%s/%s' % (test_path, test_name, r'Run 1/') );
    files.sort

    for tmpfile in files:
      if tmpfile.endswith('png'):
        _SUMMARY[test_name]['images'].append(tmpfile)

  return _SUMMARY[test_name]['images']

def SetupTestRun():
  """Setup the test run by moving the current folder of the previous
  run to an archive folder. Create a baseline folder for the tests
  if they do not already exist.
  """
  archive_path = os.path.join(_RESULTS_PATH, 'archive')
  current_path = os.path.join(_RESULTS_PATH, 'current')
  baseline_path = os.path.join(_RESULTS_PATH, 'baseline')
  config_dirname = options.conf

  # Current date for archive folder names.
  curdate = time.strftime("%Y%m%d%H%M%S")

  # Create archive folder.
  archive_folder = '%s/%s' % (archive_path, curdate)
  print 'archive folder:  %s' % archive_folder

  # Manage archive folders, ensure there are only MAX_ARCHIVE_FOLDERS.
  _ManageArchiveFolders()

  # Move current to archive.
  if os.path.exists(current_path) and options.clean:
    shutil.move(current_path, archive_folder)
    # Create 'current' folder for 'instruments' to write results to.
    os.makedirs(current_path, 0755)

  if not os.path.exists(current_path):
    os.makedirs(current_path, 0755)

  # overwrite if path exists
  test_path = os.path.join(current_path, config_dirname)
  if os.path.exists(test_path):
    shutil.move(test_path, archive_folder)
  os.makedirs(test_path, 0755)

  for key in _SUMMARY.keys():
    d = '%s/%s/%s' % (baseline_path, config_dirname, key)
    if not os.path.exists(d):
        os.makedirs(d, 0755)

def CopyTraceFilesIntoCurrent(test_name):
  base_path = os.path.join(_RESULTS_PATH, 'current')
  current_path = os.path.join(base_path, options.conf)
  test_path = os.path.join(current_path, test_name)
  trace_folders = os.path.join(_BASE_PATH, '*.trace')
  for path in glob.glob(trace_folders):
    print 'Copied %s to %s' % (path, test_path)
    shutil.move(path, test_path)

def CreateTestManifest(test_name):
  """ Write javascript control file based on specified test.  If 'all',
  create a control file for each test being run.
  """
  js_path = os.path.join(_BASE_PATH, 'js')
  imports = '#import "../tuneup/assertions.js"\n'\
            '#import "../tuneup/lang-ext.js"\n'\
            '#import "../tuneup/uiautomation-ext.js"\n'\
            '#import "../VFConstants-ext.js"\n'\
            '#import "../VFConstants.js"\n'\
            '#import "../VFMyInfo.js"\n'\
            '#import "../VFSignup.js"\n'\
            '#import "../VFLogin.js"\n'\
            '#import "../VFLogger.js"\n'\
            '#import "../viewfinder.client-1.0.0.js"\n'\
            '#import "../VFUtils.js"\n'\
            '#import "../VFUser.js"\n'\
            '#import "../VFNavigation.js"\n'\
            '#import "../VFAddContacts.js"\n'\
            '#import "../VFContacts.js"\n'\
            '#import "../VFOnboarding.js"\n'\
            '#import "../VFSettings.js"\n'\
            '#import "../VFConversation.js"\n'\
            '#import "../VFPersonalLibrary.js"\n'\
            '#import "../VFDashboard.js"\n'\
            '#import "../VFRunTest.js"\n'

  # Make sure the control directory exists.
  control_path = os.path.join(js_path, 'control')
  if not os.path.exists(control_path):
    os.mkdir(control_path)

  if test_name == 'all':
    for name in _SUMMARY.keys():
      f = open('%s/control/%s_control.js' % (js_path, name),'w')
      f.write(imports)
      if not name.endswith('.js'):
        name = name + '.js'
      f.write('#import "../../tests/' + name + '"\n')
      f.close()
  else:
    f = open('%s/control/%s_control.js' % (js_path, test_name),'w')
    f.write(imports)
    if not test_name.endswith('.js'):
      test_name = test_name + '.js'
    f.write('#import "../../tests/' + test_name + '"\n')
    f.close()
  f = open('%s/VFConstants-ext.js' % (js_path),'w')
  f.write('var scheme = "' + options.conf + '";\n')
  f.close()

def Md5ForFile(f):
  """Return an MD5 hash of the specified file.
  """
  md5 = hashlib.md5()
  if os.path.isfile(f):
    with open(f,'rb') as f:
      for chunk in iter(lambda: f.read(128*md5.block_size), b''):
        md5.update(chunk)
  else:
    return '0'
  return md5.digest()


def Setup(test_name):
  SetupSimDevice()
  SetupSimBefore('Media')
  SetupSimBefore('Library/AddressBook')

  ResetApplicationLibrary('setup')
  # kill assetsd as a workaround for IOS camera roll
  KillProcess('assetsd')
  CreateTestManifest(test_name)
  ResetTestUsers()


def Teardown(test_name):
  SetupSimAfter('Media')
  SetupSimAfter('Library/AddressBook')
  ResetApplicationLibrary('teardown')
  CopyTraceFilesIntoCurrent(test_name)
  SetupSimDeviceAfter();

def ExecuteTest():
  """Run the tests.
  """
  app_id = GetApplicationId(_SCHEME['ios'])
  test_name = options.testname
  if test_name:
    Setup(test_name)
    test_dir = '%s/results/current/%s/%s' % (_BASE_PATH, options.conf, test_name)
    os.makedirs(test_dir, 0755)
    instrument_cmd = "instruments " \
        "-t templates/VF_AutoUI_Template.tracetemplate /Users/%s/Library/Application\ Support" \
        "/iPhone\ Simulator/%s/Applications/%s/Viewfinder.app " \
        "-e UIASCRIPT js/control/%s_control.js " \
        "-e UIARESULTSPATH %s" % (os.environ['USER'],
                                                  _SCHEME['ios'],
                                                  app_id,
                                                  test_name,
                                                  test_dir)
    print instrument_cmd
    call(instrument_cmd,shell=True)
    Teardown(test_name)

  else:
    for temp_name in _SUMMARY.keys():
      Setup('all')
      test_dir = '%s/results/current/%s/%s' % (_BASE_PATH, options.conf, temp_name)
      os.makedirs(test_dir, 0755)
      instrument_cmd = "instruments " \
        "-t templates/VF_AutoUI_Template.tracetemplate /Users/%s/Library/Application\ Support" \
        "/iPhone\ Simulator/%s/Applications/%s/Viewfinder.app " \
        "-e UIASCRIPT js/control/%s_control.js " \
        "-e UIARESULTSPATH %s" % (os.environ['USER'],
                                                  _SCHEME['ios'],
                                                  app_id,
                                                  temp_name,
                                                  test_dir)
      print instrument_cmd
      call(instrument_cmd,shell=True)
      Teardown(temp_name)

def GetCurrentSchemes():
  current_path = os.path.join(_RESULTS_PATH, 'current')
  schemes = os.listdir(current_path)
  return schemes


def CreateSummaryResults():
  """Process the resulting .plist file from the test and generate the html results
  """
  errors = []
  passes = []
  current_path = os.path.join(_RESULTS_PATH, 'current')
  schemes = GetCurrentSchemes();
  test_path = os.path.join(current_path, options.conf)
  print 'Creating summary results.'
  for testname in _SUMMARY.keys():
    # Strip .js extension if present.
    if testname.endswith('.js'):
      testname = testname[:-3]
    temp_details = ''
    filepath = test_path + '/' + testname + r'/Run 1/Automation Results.plist'
    print filepath
    xmldoc = ElementTree.parse(filepath)
    dicts = xmldoc.findall('*/array/dict')
    for tmpdict in dicts:
      error = {}
      tmppass = {}
      if tmpdict.find('string').text == 'Error' and int(tmpdict.find('integer').text) == 4:
        error['testname'] = tmpdict[3].text
        error['timestamp'] = tmpdict.find('date').text
        error['status'] = tmpdict[1].text
        errors.append(error)
      elif tmpdict.find('string').text == 'Pass' and int(tmpdict.find('integer').text) == 4:
        tmppass['testname'] = tmpdict[3].text
        tmppass['timestamp'] = tmpdict.find('date').text
        tmppass['status'] = tmpdict[1].text
        passes.append(tmppass)
      elif tmpdict[1].text == 'Debug':
        temp_details += tmpdict[3].text + '\n'

    _SUMMARY[testname]['details'] = temp_details
    if not options.regen:
      ProcessScreenshots(testname)
    for image_name in GetImageNames(testname):
      if IsImageEqual(testname, image_name) is False:
        _SUMMARY[testname]['warnings'][image_name] = 'Warning: The screenshot does not match the Baseline.  ' \
          'Do you want to Accept the Current image as the new Baseline?'
        _SUMMARY[testname]['alert'] = True
      else:
        _SUMMARY[testname]['warnings'][image_name] = None

  fmt_args = {'errors': errors,
                'passes': passes,
                'summary': _SUMMARY,
                'random_num': random.randint(1,sys.maxsize),
                'schemes': schemes,
                'scheme': options.conf
                }

  # Setup the templates directories.
  resources_path = os.path.dirname('%s/testing' % _BASE_PATH)
  template_path = os.path.join(resources_path, 'templates')
  _loader = template.Loader(template_path)
  summary_html = _loader.load('summary_results.test').generate(**fmt_args)

  f = open('%s/index.html' % test_path,'w')
  f.write(summary_html)
  f.close()

def _GetProcessInfo(proc_name):
  ps = subprocess.Popen("ps ax -o pid= -o args= ", shell=True, stdout=subprocess.PIPE)
  ps_pid = ps.pid
  output = ps.stdout.read()
  ps.stdout.close()
  ps.wait()
  return ps_pid, output

def KillProcess(proc_name):
  ps_pid, output = _GetProcessInfo(proc_name)
  for line in output.split("\n"):
    res = re.findall("(\d+) (.*)", line)
    if res:
      pid = int(res[0][0])
      if proc_name in res[0][1] and pid != os.getpid() and pid != ps_pid:
        os.kill(pid, signal.SIGKILL)
        return

def ProcessExists(proc_name):
  ps_pid, output = _GetProcessInfo(proc_name)
  for line in output.split("\n"):
    res = re.findall("(\d+) (.*)", line)
    if res:
      pid = int(res[0][0])
      if proc_name in res[0][1] and pid != os.getpid() and pid != ps_pid:
        return True
  return False

def ResetTestUsers(num=5):
  # Login + terminate each user.
  for x in xrange(num):
    user = 'tester_%d@emailscrubbed.com' % x
    info_dict = {
       'identity': 'Email:%s' % user,
       }
    # Attempt to login user.
    resp = LoginUser(info_dict)
    # If login is successful, terminate the user account.
    if resp is not None:
      print 'Terminating user'
      TerminateUser(info_dict, resp)

def GetCookieFromResponse(response):
    """Extracts the user cookie from an HTTP response and returns it if
    it exists, or returns None if not."""
    user_cookie_header_list = [h for h in response.headers.get_list('Set-Cookie') if h.startswith('user=')]
    if not user_cookie_header_list:
      return None
    return re.match(r'user="?([^";]*)', user_cookie_header_list[-1]).group(1)

def AllocateIds(asset_types, user_cookie):
  http_headers = {
    'Cookie': '_xsrf=fake_xsrf; user=%s' % user_cookie,
    'X-XSRFToken': 'fake_xsrf',
    'Content-Type': 'application/json'
    }
  body = {
    'headers': {
      'version': MAX_SUPPORTED_MESSAGE_VERSION
      },
    'asset_types': asset_types
    }
  try:
    response = _CallService('/service/allocate_ids', body, http_headers)
  except HTTPError:
    return None
  else:
    return json.loads(response.body)

def LoginUser(info_dict):
  http_headers = {
    'Content-Type': 'application/json',
    'Cookie': '_xsrf=fake_xsrf',
    'X-XSRFToken': 'fake_xsrf',
    }
  body = {
    'headers': {
      'version': MAX_SUPPORTED_MESSAGE_VERSION
      },
    #'cookie_in_response': True,
    'auth_info': info_dict
    }
  try:
    response = _CallService('/login/fakeviewfinder', body, http_headers)
  except HTTPError:
    return None
  else:
    # Parse out user cookie and store in response.body as 'cookie'.
    user_cookie = GetCookieFromResponse(response)
    if user_cookie is None:
      raise "An error occurred getting user cookie from response."

    # Add user cookie to reponse.body.
    json_response = json.loads(response.body)
    json_response['cookie'] = user_cookie

    return json_response


def TerminateUser(info_dict, login_resp):
  http_headers = {
    'Cookie': '_xsrf=fake_xsrf; user=%s' % login_resp['cookie'],
    'X-XSRFToken': 'fake_xsrf',
    'Content-Type': 'application/json'
    }
  body = {
    'headers': login_resp['headers'],
    }

  op_id = AllocateIds(['o'], login_resp['cookie'])
  if op_id is not None:
    body['headers']['op_id'] = op_id['asset_ids'][0]

  try:
    response = _CallService('/service/terminate_account', body, http_headers)
  except HTTPError:
    return None;
  else:
    return json.loads(response.body)


def RegisterUser(info_dict):
  http_headers = {
    'Cookie': '_xsrf=fake_xsrf',
    'X-XSRFToken': 'fake_xsrf',
    'Content-Type': 'application/json',
    }

  body = {
    'headers': {
      'version': MAX_SUPPORTED_MESSAGE_VERSION
      },
    'auth_info': info_dict
    }

  response = _CallService('/register/fakeviewfinder', body, http_headers)

  return json.loads(response.body)

def _CallService(method, body, http_headers):
  url = '%s%s' % (_BASE_URL, method)
  return HTTPClient().fetch(url, method='POST', body=json.dumps(body), headers=http_headers,
                              validate_cert=False)


def SetupSimAfter(fname):
  """Replace the environments IOS simulator's Media directory with what it
  was before the test took place.
  """
  _IOS_FNAME = fname
  _IOS_FNAME_BACKUP = '%s.backup' % fname
  _IOS_FNAME_TEMP = '%s.temp' % fname

  _SNAPSHOTS_BACKUP_PATH = os.path.join(_SNAPSHOTS_PATH, _IOS_FNAME_BACKUP)

  ios_sim_path = r"/Users/%s/Library/Application Support" \
        "/iPhone Simulator/%s/" % (os.environ['USER'], _SCHEME['ios'])
  ios_fname_path = os.path.join(ios_sim_path, _IOS_FNAME)
  ios_fname_temp_path = os.path.join(ios_sim_path, _IOS_FNAME_TEMP)

  try:
    # Move fname to fname.tmp.
    shutil.move(ios_fname_path, ios_fname_temp_path)
    # Copy fname.backup to fname.
    shutil.copytree(_SNAPSHOTS_BACKUP_PATH, ios_fname_path)
    # Delete fname.tmp.
    shutil.rmtree(ios_fname_temp_path, True, None)
    # Delete fname.backup.
    shutil.rmtree(_SNAPSHOTS_BACKUP_PATH, True, None)
  except EnvironmentError, e:
    print "An error occurred in SetupSimAfter(%s). %s" % (fname, e)
    raise
  else:
    print "SetupSimAfter(%s) successful." % fname
    return 1;

def SetupSimDeviceAfter():
  app_id = GetApplicationId(_SCHEME['ios'])
  vf = r"/Users/%s/Library/Application Support" \
      "/iPhone Simulator/%s/Applications" \
      "/%s/Viewfinder.app" % (os.environ['USER'],
                                _SCHEME['ios'],
                                app_id)
  info_file_orig = os.path.join(vf, 'Info.plist')
  info_file_backup = 'snapshots/Info_backup.plist'
  shutil.copy(info_file_backup, info_file_orig)
  os.unlink(info_file_backup)

def SetupSimDevice():
  # Copy Info.plist
  GetSchemeConfig()
  app_id = GetApplicationId(_SCHEME['ios'])
  vf = r"/Users/%s/Library/Application Support" \
      "/iPhone Simulator/%s/Applications" \
      "/%s/Viewfinder.app" % (os.environ['USER'],
                                _SCHEME['ios'],
                                app_id)
  info_file_orig = os.path.join(vf, 'Info.plist')
  info_file_ipad = 'snapshots/Info_iPad.plist'
  info_file_backup = 'snapshots/Info_backup.plist'
  shutil.copy(info_file_orig, info_file_backup)
  cmd = "bin/choose_sim_device '%s' 'iOS %s'" % (_SCHEME['device_label'], _SCHEME['ios'])
  print "SetupSimDevice: %s" % cmd

  if (_SCHEME['device'] == 'iPad'):
    print "Copying %s to %s" % (info_file_ipad, info_file_orig)
    shutil.copy(info_file_ipad, info_file_orig)
  call(cmd, shell=True)


def SetupSimBefore(fname):
  """Copy our snapshot of the IOS simulator's Media directory which has 10 photos.
  """
  _IOS_FNAME = fname
  _IOS_FNAME_BACKUP = '%s.backup' % fname
  _IOS_FNAME_AUTOUI = '%s.autoui' % fname

  ios_sim_path = r"/Users/%s/Library/Application Support" \
        "/iPhone Simulator/%s/" % (os.environ['USER'], _SCHEME['ios'])
  ios_fname_path = os.path.join(ios_sim_path, _IOS_FNAME)
  _SNAPSHOTS_BACKUP_PATH = os.path.join(_SNAPSHOTS_PATH, _IOS_FNAME_BACKUP)
  _SNAPSHOTS_FNAME_AUTOUI_PATH = os.path.join(_SNAPSHOTS_PATH, _IOS_FNAME_AUTOUI)
  sum_file = os.path.join(_SNAPSHOTS_BACKUP_PATH, 'check.sum')

  try:
    # Check for special file in backup copy of Media folder.
    if not os.path.exists(sum_file):
      # Delete backup directory.
      if os.path.exists(_SNAPSHOTS_BACKUP_PATH):
        shutil.rmtree(_SNAPSHOTS_BACKUP_PATH, True, None)
      # Copy Media to Media.backup.
      shutil.copytree(ios_fname_path, _SNAPSHOTS_BACKUP_PATH)
      # Touch special file.
      file = open(sum_file, 'w+')
      file.close()
    # Delete Media folder.
    shutil.rmtree(ios_fname_path, None, None)
    # Copy our snapshot to Media.
    shutil.copytree(_SNAPSHOTS_FNAME_AUTOUI_PATH, ios_fname_path)

  except EnvironmentError, e:
    print "An error occurred in SetupSimBefore(%s). %s" % (fname, e)
    raise
  else:
    print "SetupSimBefore(%s) successful." % fname
    return 1;

def SetupSimulator(ios):
  """Build simulator app if necessary.
     xcodebuild -workspace $VF_HOME/clients/ios/ViewfinderWorkspace.xcworkspace
                -arch i386
                -scheme Viewfinder
                -sdk iphonesimulator7.0
  """
  simulator_cmd = 'xcodebuild -workspace %s/clients/ios/ViewfinderWorkspace.xcworkspace ' \
                  '-arch i386 -scheme Viewfinder -sdk iphonesimulator7.0' % (os.environ['VF_HOME'])
  call(simulator_cmd, shell=True)


def ResetApplicationLibrary(state):
  app_id = GetApplicationId(_SCHEME['ios'])
  ios_sim_basepath = r"/Users/%s/Library/Application Support" \
        "/iPhone Simulator/%s/Applications/%s/" % (os.environ['USER'], _SCHEME['ios'], app_id)

  src = os.path.join(ios_sim_basepath, 'Library')
  dst = os.path.join(ios_sim_basepath, 'Library.orig')

  if state == 'setup' and os.path.exists(src):
    if os.path.exists(dst):
      shutil.rmtree(dst, None, None)
    shutil.move(src, dst)
  if state == 'teardown' and os.path.exists(dst):
    if os.path.exists(src):
      shutil.rmtree(src, None, None)
    shutil.move(dst, src)

def IsImageEqual(testname, image_name):
  """Check if the given image is equal to the baseline image for this test.
  """
  image1 = 'results/baseline/%s/%s/%s' % (options.conf, testname, image_name)
  image2 = r'results/current/%s/%s/Run 1/%s' % (options.conf, testname, image_name)
  return Md5ForFile(image1) == Md5ForFile(image2)

def UpdateImageMaskConfig(test_name, image_name):
  tmp = image_name[:-4]
  base, num = tmp.split('|', 1)
  image_base_name = '%s.png' % base

  image1 = 'results/baseline/%s/%s/%s' % (options.conf, test_name, image_base_name)
  image2 = r'results/current/%s/%s/Run 1/%s' % (options.conf, test_name, image_name)

  im1 = Image.open(image1)
  im2 = Image.open(image2)

  diff = ImageChops.difference(im2, im1)
  print "%s: " % image_name
  print diff.getbbox()
  # TODO:  if image delta is smaller than 100 x 100 write to config
  bbox = diff.getbbox()
  if bbox is not None:
    width = bbox[2] - bbox[0];
    height = bbox[3] - bbox[1]
    if width <= 100 and height <= 100:
      mask = { "x":bbox[0], "y":bbox[1], "height":height, "width":width }
      if test_name not in _IMAGE_MASK_CONFIG:
        _IMAGE_MASK_CONFIG[test_name] = {}
      else:
        if image_base_name not in _IMAGE_MASK_CONFIG[test_name]:
          _IMAGE_MASK_CONFIG[test_name][image_base_name] = []
      _IMAGE_MASK_CONFIG[test_name][image_base_name].append(mask)
      # TODO(ben): fix or remove.
      #cfg_data_file = open(_IMAGE_MASK_CONFIG_FILE, 'w')
      #cfg_data_file.write(json.dumps(_IMAGE_MASK_CONFIG))
      print "Updated %s" % _IMAGE_MASK_CONFIG

def ProcessScreenshots(testname):
  print 'Processing screen shots.'
  testImages = GetImageNames(testname)
  image_processed = {}
  for image in testImages:
    tmp = image[:-4]
    try:
      name = tmp.split('|', 1)
      base = name[0]
      # Update image mask config if necessary.
      #UpdateImageMaskConfig(testname, image)

      # Apply masks to images before comparison.
      ApplyImageMask(testname, image)
      if base not in image_processed.keys():
        image_processed[base] = False
    except ValueError:
      print "An error occured parsing filename %s" % tmp

    image1 = 'results/baseline/%s/%s/%s.png' % (options.conf, testname, base)
    image2 = r'results/current/%s/%s/Run 1/%s' % (options.conf, testname, image)
    keep_image = r'results/current/%s/%s/Run 1/%s.png' % (options.conf, testname, base)

    if image_processed[base] == False:
      if Md5ForFile(image1) == Md5ForFile(image2):
        #shutil.move(image2, keep_image)
        image_processed[base] = True
      #else:
      shutil.move(image2, keep_image)
    else:
      if os.path.exists(keep_image):
        # delete image if we already found a match
        os.remove(image2)


def CheckEnvironment():
  status = True
  _AUTHORIZATION_FILE = '/etc/authorization'
  _XML_DATA_FILE = '%s/data/instrument_keys.xml' % _BASE_PATH
  _KEY_PROCESS_ANALYSIS = 'com.apple.dt.instruments.process.analysis'
  _KEY_PROCESS_KILL = 'com.apple.dt.instruments.process.kill'
  _WARNING_KEY_MISSING = 'The /etc/authorization file must contain the following key:  '
  _WARNING_KEY_INSTRUCTIONS = 'Copy the following XML into /etc/authorization.  Add the keys to the "rights" dict:'
  # Check for presence of keys in /etc/authorization.
  auth_file_contents = open(_AUTHORIZATION_FILE).read()
  is_analysis_present = _KEY_PROCESS_ANALYSIS not in auth_file_contents
  is_kill_present = _KEY_PROCESS_KILL not in auth_file_contents

  output = '\n'
  if is_analysis_present:
    output += '%s\n%s\n\n' % (_WARNING_KEY_MISSING, _KEY_PROCESS_ANALYSIS)
    status = False
  if is_kill_present:
    output += '%s\n%s\n\n' % (_WARNING_KEY_MISSING, _KEY_PROCESS_KILL)
    status = False

  if not status:
    output += '%s\n\n' % _WARNING_KEY_INSTRUCTIONS
    output += open(_XML_DATA_FILE).read()
    print output
    exit()

  # Start up local-viewfinder (if necessary).
  local_server = 'local-viewfinder'
  server_path = os.path.join(os.environ['VF_HOME'], 'scripts')
  log_path = os.path.join(os.environ['VF_HOME'], 'logs')
  x = os.path.join(server_path, local_server)
  if not os.path.exists(log_path):
    os.mkdir(log_path)
  logfile = os.path.join(log_path, 'server.log')
  if not ProcessExists(local_server):
    out = open(logfile,"w")
    subprocess.Popen([x], stdout=out, stderr=out)
    print "Starting local-viewfinder...%s" % ProcessExists(local_server)
    print "You can monitor the server log with, 'tail -f %s'" % logfile
  else:
    print "The local-viewfinder process is running"

def main():
  CheckEnvironment()
  global _IMAGE_MASK_CONFIG
  _IMAGE_MASK_CONFIG = SetupImageMasks()
  if options.conf:
    GetSchemeConfig()
  if options.list:
    tests = GetTestNames()
    tests.sort()
    for test in tests:
      print test
    return
  GetTestNames()
  if not options.regen:
    SetupTestRun()
  if options.simulator:
    SetupSimulator(_SCHEME['ios'])

  if not options.regen:
    ExecuteTest()
  CreateSummaryResults()

if __name__ == '__main__':
  options.parse_command_line()
  main()
