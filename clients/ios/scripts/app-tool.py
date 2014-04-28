#! /usr/bin/env python
# -*- mode: python; -*-
# encoding: utf-8

import argparse
import bs4
import cookielib
import os
import re
import subprocess
import sys
import tempfile
import urllib
import urllib2

kDevAccounts = {
    'peter@emailscrubbed.com' : 'R3xihokV',
}

_COOKIE_PREFIX = os.path.expanduser('~/.app-tool.')

_BASE_URL = 'https://developer.apple.com'
_MAIN_URL = _BASE_URL + '/devcenter/ios/index.action'
_BASE_DEVICES_URL = _BASE_URL + '/ios/manage/devices'
_DEVICES_URL = _BASE_DEVICES_URL + '/index.action'
_DEVICES_ADD_URL = _BASE_DEVICES_URL + '/ios/manage/devices/add.action'
_BASE_PROFILES_URL = _BASE_URL + '/ios/manage/provisioningprofiles'
_DEVELOPMENT_PROFILES_URL = _BASE_PROFILES_URL + '/index.action'
_DISTRIBUTION_PROFILES_URL = _BASE_PROFILES_URL + '/viewDistributionProfiles.action'

def ErrorExit(message):
  print >>sys.stderr, message
  sys.exit(1)

kFormFieldsRe = re.compile(r'^(?:input|textarea|select)$')

def ExtractFormFields(soup):
  """Turn a BeautifulSoup form in to a dict of fields and default values"""
  fields = []
  for field in soup.find_all(kFormFieldsRe):
    if field.name == 'input':
      # ignore submit/image with no name attribute
      if field['type'] in ('submit', 'image') and not field.has_attr('name'):
        continue

      # single element nome/value fields
      if field['type'] in ('text', 'hidden', 'password', 'submit', 'image'):
        value = ''
        if field.has_attr('value'):
          value = field['value']
        fields.append((field['name'], value))
        continue

      # checkboxes and radios
      if field['type'] in ('checkbox', 'radio'):
        value = ''
        if field.has_attr('checked'):
          if field.has_attr('value'):
            value = field['value']
          else:
            value = 'on'
        if value:
          fields.append((field['name'], value))
        continue

      assert False, 'input type %s not supported' % field['type']
    elif field.name == 'textarea':
      fields.append((field['name'], field.string or ''))
    elif field.name == 'select':
      value = ''
      options = field.find_all('option')
      is_multiple = field.has_attr('multiple')
      selected_options = [
          option for option in options
          if option.has_attr('selected')
          ]

      # If no select options, go with the first one
      if not selected_options and options:
        selected_options = [options[0]]

      if not is_multiple:
        assert(len(selected_options) < 2)
        if len(selected_options) == 1:
          value = selected_options[0]['value']
      else:
        value = [option['value'] for option in selected_options]

      if value:
        fields.append((field['name'], value))

  return fields

class ProvisioningProfile(bs4.BeautifulSoup):
  def __init__(self, data):
    self.data = data

    (fd, filename) = tempfile.mkstemp(prefix='app-tool')
    os.close(fd)
    openssl = subprocess.Popen(
        ['openssl', 'smime', '-verify', '-inform', 'DIR', '-out', filename],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout, stderr) = openssl.communicate(self.data)
    f = open(filename, 'rb')
    xml = f.read()
    f.close()
    os.unlink(filename)

    super(ProvisioningProfile, self).__init__(xml)

  def reSign(self):
    # 1. Unzip the IPA
    #    - unzip Application.ipa
    # 2. Remove old CodeSignature
    #    - rm -rf "Payload/Application.app/_CodeSignature"
    #      "Payload/Application.app/CodeResources"
    # 3. Replace embedded mobile provisioning profile
    #    - cp "MyEnterprise.mobileprovision"
    #      "Payload/Application.app/embedded.mobileprovision"
    # 4. Re-sign
    #    - /usr/bin/codesign -f -s "iPhone Distribution: Certificate Name"
    #      --resource-rules "Payload/Application.app/ResourceRules.plist"
    #      "Payload/Application.app"
    # 5. Re-package
    #    - zip -qr "Application.resigned.ipa" Payload
    pass

class DevCenterPage(bs4.BeautifulSoup):
  _sign_in_re = re.compile(r'sign in', re.IGNORECASE)
  _team_selection_re = re.compile(r'select.*team')

  def __init__(self, resp):
    self.url = resp[0]
    super(DevCenterPage, self).__init__(resp[1], "html5lib")

  def loginNeeded(self):
    if self._sign_in_re.search(self.title.text):
      return True
    for span in self.find_all('span'):
      if span.text == 'Log in':
        return True
    return False

  def teamSelectionNeeded(self):
    return self._team_selection_re.match(self.title.text)

class DevCenterClient:
  _devices_left_re = re.compile(r'.*register (\d+) additional.*')
  _device_id_re = re.compile(r'^[A-Fa-f0-9]{40}$')

  def __init__(self, username, password, cookie_jar):
    self.username = username
    self.password = password
    self.cookie_file = _COOKIE_PREFIX + self.username
    self.cookie_jar = cookie_jar

  def _fetchUrl(self, url, data=None):
    self.cookie_jar.clear()
    if os.path.exists(self.cookie_file):
      self.cookie_jar.load(self.cookie_file, ignore_discard=True)
    req = urllib2.Request(url, data)
    resp = urllib2.urlopen(req)
    html = resp.read()
    self.cookie_jar.save(self.cookie_file, ignore_discard=True)
    return (resp.geturl(), html)

  def _baseUrl(self, url):
    req = urllib2.Request(url)
    return '%s://%s' % (req.get_type(), req.get_host())

  def _fetchPage(self, url, data=None):
    page = DevCenterPage(self._fetchUrl(url, data))
    if not page.loginNeeded():
      return page
    self._login(DevCenterPage(self._fetchUrl(_MAIN_URL)))
    return DevCenterPage(self._fetchUrl(url, data))

  def _login(self, page):
    print >>sys.stderr, 'Login %s' % self.username

    login_link = page.find('a', text='Log in')
    if not login_link:
      ErrorExit('unable to find login link')
    if not login_link.has_attr('href'):
      ErrorExit('unable to find login link')

    login_page = DevCenterPage(self._fetchUrl(login_link['href']))
    login_form = login_page.find(attrs={'name':'appleConnectForm'})
    if not login_form:
      ErrorExit('unable to find login form')

    form_fields = {}
    for field in login_form.find_all('input'):
      if field['type'] == 'hidden':
        if field.get('value'):
          form_fields[field['name']] = field['value']
      elif field['name'] == 'theAccountName':
        form_fields[field['name']] = self.username
      elif field['name'] == 'theAccountPW':
        form_fields[field['name']] = self.password

    url = '%s%s' % (self._baseUrl(login_page.url), login_form['action'])
    login_page = DevCenterPage(self._fetchUrl(url, urllib.urlencode(form_fields)))
    if login_page.loginNeeded():
      ErrorExit('login failed')

  def listDevices(self):
    def devicesRemaining(page):
      tag = page.select('.devicesannounce strong')
      if tag:
        m = self._devices_left_re.match(tag[0].text)
        if m:
          return ' (%s remaining)' % m.group(1)
      return ''

    page = self._fetchPage(_DEVICES_URL)
    devices = zip(page.select('td.name span'),
                  page.select('td.id'))

    print '%s: %d devices%s' % (self.username, len(devices),
                                devicesRemaining(page))

    for name, udid in devices:
      print '    %s : %s' % (udid.text.encode("iso-8859-15", "replace"),
                             name.text.encode("iso-8859-15", "replace"))

  def addDevice(self, device_id, device_name):
    if not self._device_id_re.match(device_id):
      ErrorExit('invalid device id: %s' % device_id)

    add_page = self._fetchPage(_DEVICES_ADD_URL)
    if not add_page:
      ErrorExit('unable to retrieve add device page')

    add_form = add_page.find(id="add")
    fields = {k : v for k,v in ExtractFormFields(add_form)}
    if (not 'deviceNameList[0]' in fields or
        not 'deviceNumberList[0]' in fields):
      ErrorExit('unexpected form fields: %s' % fields.keys())
    fields['deviceNameList[0]'] = device_name
    fields['deviceNumberList[0]'] = device_id

    url = '%s%s' % (self._baseUrl(add_page.url), add_form['action'])
    self._fetchPage(url, urllib.urlencode(fields))
    print '%s: device added\n  %s  %s' % (self.username, device_id, device_name)

  def listProfiles(self):
    def listProfilesInternal(type, url):
      page = self._fetchPage(url)
      profiles = []
      for profile in page.select('td.profile'):
        name = profile.find('span')
        if not name:
          continue
        parent = profile.parent
        appid = parent.select('td.appid')[0].stripped_strings.next()
        status = parent.select('td.statusXcode')[0].stripped_strings.next()
        profiles.append((name.text, appid, status))
      return profiles

    dev = listProfilesInternal('development', _DEVELOPMENT_PROFILES_URL)
    dist = listProfilesInternal('distribution', _DISTRIBUTION_PROFILES_URL)
    print '%s: %d development, %d distribution' % (
        self.username, len(dev), len(dist))
    for p in dev:
      print '    %-35s %-36s %-7s (development)' % p
    for p in dist:
      print '    %-35s %-36s %-7s (distribution)' % p

  def getProfile(self, name):
    def getProfileInternal(name, url):
      page = self._fetchPage(url)
      for profile in page.select('td.profile'):
        span = profile.find('span')
        if not span or name != span.text:
          continue
        links = profile.parent.select('td.action a[href*="/download.action"]')
        if not links:
          continue
        link = '%s%s' % (self._baseUrl(url), links[0]['href'])
        return ProvisioningProfile(self._fetchUrl(link)[1])
      return None

    profile = getProfileInternal(name, _DISTRIBUTION_PROFILES_URL)
    if not profile:
      profile = getProfileInternal(name, _DEVELOPMENT_PROFILES_URL)
    if profile:
      print profile.data

  def editProfile(self, name, devices):
    def fetchEditPage(name, url):
      page = self._fetchPage(url)
      for profile in page.select('td.profile'):
        span = profile.find('span')
        if not span or name != span.text:
          continue

        links = profile.parent.select('td.action a[href*="/edit.action"]')
        if not links:
          continue
        link = '%s%s' % (self._baseUrl(url), links[0]['href'])
        return self._fetchPage(link)
      return None

    # Fetch the edit page for the specified provisioning profile.
    edit_page = fetchEditPage(name, _DISTRIBUTION_PROFILES_URL)
    if not edit_page:
      edit_page = fetchEditPage(name, _DEVELOPMENT_PROFILES_URL)
      if not edit_page:
        return

    # Find the save form.
    save_form = edit_page.find(id='save')
    if not save_form:
      return

    # Edit the form, selecting or deselecting desired devices.
    edits = []
    for device in devices:
      op = device[0]
      if op == '+' or op == '-':
        device = device[1:];
      else:
        op = '+'
      checkbox = save_form.find('input', value=device)
      if not checkbox:
        print >>sys.stderr, 'unable to find device: %s' % device
        continue
      device_name = checkbox.find_next_sibling('label').text
      if op == '+':
        if not checkbox.has_attr('checked'):
          checkbox['checked'] = 'checked'
          edits.append('  added %s' % device_name)
      elif checkbox.has_attr('checked'):
        del checkbox['checked']
        edits.append('  removed %s' % device_name)

    if not edits:
      print '%s: %s\n  no changes' % (self.username, name)
      return

    # Extract the form fields and submit
    fields = ExtractFormFields(save_form)
    url = '%s%s' % (self._baseUrl(edit_page.url), save_form['action'])
    self._fetchPage(url, urllib.urlencode(fields))
    print '%s: %s\n%s' % (self.username, name, '\n'.join(edits))

class AppTool:
  def __init__(self):
    self.cookie_jar = cookielib.LWPCookieJar()
    urllib2.install_opener(
        urllib2.build_opener(urllib2.HTTPCookieProcessor(self.cookie_jar)))
    self.clients = {}

  def _getClient(self, username, password):
    try:
      client = self.clients[username]
    except KeyError:
      client = DevCenterClient(username, password, self.cookie_jar)
      self.clients[username] = client
    return client

  def _forEachClient(self, callback):
    separator = ''
    for username, password in kDevAccounts.iteritems():
      sys.stdout.write(separator)
      callback(self._getClient(username, password));
      # separator = '\n'

  def listDevices(self):
    self._forEachClient(lambda client : client.listDevices())

  def addDevice(self, username, device_id, device_name):
    try:
      password = kDevAccounts[username]
    except KeyError:
      ErrorExit('unable to find client: %s\n%s' %
                (username,
                 '\n'.join(['  %s' % account for account in kDevAccounts.keys()])))

    client = self._getClient(username, password)
    client.addDevice(device_id, device_name)

  def listProfiles(self):
    self._forEachClient(lambda client : client.listProfiles())

  def getProfile(self, name):
    self._forEachClient(lambda client : client.getProfile(name))

  def editProfile(self, name, devices):
    self._forEachClient(lambda client : client.editProfile(name, devices))

def main(args):
  tool = AppTool()

  if len(args.commands) == 0:
    ErrorExit('no commands specified')
  if args.commands[0] == 'devices':
    tool.listDevices()
  elif args.commands[0] == 'device-add':
    tool.addDevice(args.commands[1], args.commands[2], args.commands[3])
  elif args.commands[0] == 'profiles':
    tool.listProfiles()
  elif args.commands[0] == 'profile-get':
    tool.getProfile(args.commands[1])
  elif args.commands[0] == 'profile-edit':
    tool.editProfile(args.commands[1], args.commands[2:])
  else:
    ErrorExit('unknown command: %s' % args.commands[0])

if __name__ == '__main__':
  parser = argparse.ArgumentParser(
      description='Apple Developer Provisioning Profile Tool.')
  parser.add_argument('commands',
                      nargs='*',
                      help='the commands to run')
  parser.add_argument('-v', '--verbose',
                      dest='verbose',
                      action='store_true',
                      help='verbose logging')
  args = parser.parse_args()

  main(args)
