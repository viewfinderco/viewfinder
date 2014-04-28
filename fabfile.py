"""Viewfinder production scripts

Cookbook:

* Launch new instances: specify NodeType,Name,Zone
  $ fab create_instance:STAGING,STAGING_003,us-east-1c
* Resume installation of failed instance creation (eg: stuck in state 'pending' or not ssh-able):
  $ fab create_instance:STAGING,STAGING_003,us-east-1c,i-9a0cdbe9
* Stop and destroy a running instance:
  $ fab destroy_instance:STAGING,i-9a0cdbe9
* Deploy env/code changes and restart:
  $ fab nodetype:STAGING deploy
  $ fab nodetype:PROD deploy

Region currently default to 'us-east-1'. When running in multiple regions, add region:<...> task.

"""
import os
import re
import subprocess
import time
from collections import defaultdict
from fabric.api import *
from fabric.operations import *
from fabric.network import NetworkError
from fabric.state import output
from fabric.utils import *
from fabric.contrib.files import *
from fabric.contrib.project import rsync_project

from viewfinder.backend.base import util
from viewfinder.backend.prod import ec2_utils

kVFPassphraseFile = '~/.ssh/vf-passphrase'
kInstanceType = 'm1.medium'

env.user = 'ec2-user'
env.key_filename = '~/.ssh/wwwkey.pem'
env.region = 'us-east-1'
env.node_type = None

# Disable various output levels.
output['running'] = False
output['stdout'] = False
output['warnings'] = False

# Amazon Linux AMI.  Note that these are region-specific; this one is for
# us-east.  List is at http://aws.amazon.com/amazon-linux-ami/
BASE_AMI = 'ami-3275ee5b'

def runs_last(func):
  """Decorator to run a function only on the last invocation.
  We determine last by comparing the number times called with the size of env.hosts.
  Return None on all invocations but the last one where we return the function return value.
  """
  def Wrapper():
    calls = func.num_host_calls
    if calls >= len(env.hosts) - 1:
      return func()
    else:
      func.num_host_calls = calls + 1
      return None

  setattr(func, 'num_host_calls', 0)
  return Wrapper


def fprint(string):
  host_str = '[%s] ' % env.host_string if env.host_string else ''
  time_str = time.strftime("%H:%M:%S")
  puts('%s%s %s' % (host_str, time_str, string), show_prefix=False, end='\n')


def fprompt(text, default=None, validate=None):
  host_str = '[%s] ' % env.host_string if env.host_string else ''
  time_str = time.strftime("%H:%M:%S")
  return prompt('%s%s %s' % (host_str, time_str, text), default=default, validate=validate)


def load_passphrase_from_file():
  """Read the viewfinder passphrase from local file."""
  vf_path = os.path.expanduser(kVFPassphraseFile)
  assert os.access(vf_path, os.F_OK) and os.access(vf_path, os.R_OK), '%s must exist and be readable' % vf_path
  with open(vf_path) as f:
    user_data = f.read()
  return user_data.strip('\n')


def get_ami_metadata():
  """Fetch ami metadata for the local instance. Returns a dict of 'key':'value'. eg: 'instance-id':'i-e7f7e69b'."""
  res = {}
  base_url = 'http://169.254.169.254/latest/meta-data'
  instance_id = run('curl %s/instance-id' % base_url)
  assert re.match('i-[0-9a-f]{8}', instance_id)
  res['instance-id'] = instance_id

  return res


@task
def get_healthz():
  """Fetch healthz status for the local instance."""
  url = 'https://localhost:8443/healthz'
  ret = 'FAIL'
  with settings(warn_only=True):
    ret = run('curl -k %s' % url)
  fprint('Healthz status: %s' % ret)
  return ret == 'OK'

@task
def nodetype(typ):
  """Specify node type: STAGING or PROD."""
  # Don't override hosts if specified on the command line.
  if not env.hosts:
    env.hosts = ec2_utils.ListInstancesDNS(region='us-east-1', node_types=[typ], states=['running'])
  env.nodetype = typ


def is_old_env():
  """Return True if ~/env is old-style (plain directory) or False if new style (symlink).
  No ~/env returns False.
  """
  env_exists = exists('~/env')
  if not env_exists:
    # So such directory or link.
    return False
  with settings(warn_only=True):
      is_link = run('readlink ~/env')
  if is_link.return_code == 0:
    # This is a symlink. New-style environment.
    return False
  return True


def is_old_code():
  """Return True if ~/viewfinder is old-style (plain directory) or False if new style (symlink).
  No ~/viewfinder returns False.
  """
  code_exists = exists('~/viewfinder')
  if not code_exists:
    # So such directory or link.
    return False
  with settings(warn_only=True):
      is_link = run('readlink ~/viewfinder')
  if is_link.return_code == 0:
    # This is a symlink. New-style code.
    return False
  return True


def get_file_suffix(prefix, filename):
  # Depending on how the linking was done, the destination could be absolute or relative, with or without '/'.
  result = re.match(r'^(?:/home/%s/)?%s.([0-9a-f]+)/?$' % (env.user, prefix), filename)
  if result is None or len(result.groups()) != 1:
    return None
  return result.groups()[0]


def get_link_suffix(symlink):
  """Follow 'symlink' in ~/ and determine the suffix for the target (of the form <symlink>.[a-f0-9]+.
  Returns None if the symlink does not exist or is not a symlink.
  """
  with settings(warn_only=True):
    if not exists('~/%s' % symlink):
      return None
    target = run('readlink ~/%s' % symlink)
    if target.return_code != 0:
      return None
  suffix = get_file_suffix(symlink, target)
  assert suffix is not None, 'Could not determine suffix from filename %s' % target
  return suffix


def active_env():
  """Return the revision ID of the current environment, or None if it does not exist or cannot be determined."""
  return get_link_suffix('env')


def active_code():
  """Return the revision ID of the current code, or None if it does not exist or cannot be determined."""
  return get_link_suffix('viewfinder')


def latest_requirements_revision():
  """Return the revision ID of the last change to the prod-requirements file.
  hg log lists all revisions, regardless of what we're synced to. -r :. shows all entries up to the currently-synced
  point. However, they are listed in reverse order (older first, latest last), so we must tail it.
  """
  return local('hg log -r :. --template "{node|short}\n" scripts/prod-requirements.txt | tail -n 1', capture=True)


def hg_revision():
  """Returns the HG revision."""
  return local('hg identify -i', capture=True)


def hg_revision_timestamp(rev):
  """Returns the timestamp (in seconds) of 'rev', or None if cannot be determined.

  Since mq (and non-linear history in general) makes it possible have revisions dated
  before their true "commit" date, we must find the newest ancestor of the given revision.
  """
  try:
    revset = 'last(sort(ancestors(%s), date))' % rev
    res = subprocess.check_output(['hg', 'log', '-r', revset, '--template', '{date}'], stderr=subprocess.STDOUT)
    return float(res.strip())
  except subprocess.CalledProcessError:
    return None


@runs_once
def code_prep():
  """Generate the code tarball and return the HG revision."""
  rev = hg_revision()
  assert not rev.endswith('+'), 'Client has pending changes, cannot install.'
  fprint('Preparing local code tarball (rev %s)' % rev)
  filename = 'viewfinder.%s.tar.gz' % rev

  local('hg identify -i > hg_revision.txt')
  local('tar czf %s --exclude "*.o" --exclude "*~" --exclude "*.pyc" __init__.py scripts/ marketing/ backend/ resources/ secrets/viewfinder.co hg_revision.txt' % filename)
  return rev


@runs_last
def code_cleanup():
  """Delete the generated tarball and revision file."""
  fprint('Cleaning up local code')
  local('rm -f hg_revision.txt viewfinder.*.tar.gz')


@task
def code_install():
  """Install latest code from local directory.
  We put the current hg revision in a file, generate a local tarball, copy it to the instance and untar.
  code_prep() and code_cleanup() are run the first and last time respectively.
  """
  assert env.host_string, "no hosts specified"
  assert not is_old_code(), 'Active code is using the old style (directory instead of symlink). ' \
                            'Manual intervention required'
  # code_prep is only run the first time. Subsequent runs return the same value as the first time.
  rev = code_prep()
  if code_verify(rev):
    return

  fprint('Installing code (rev %s)' % rev)

  filename = 'viewfinder.%s.tar.gz' % rev
  dirname = 'viewfinder.%s' % rev

  put(filename, '~/%s' % filename)

  run('mkdir -p ~/%s' % dirname)
  # TODO: purge old pycs
  with cd('~/%s' % dirname):
    run('tar xzvf ../%s' % filename)
  # HACK: the local viewfinder/pythonpath directory has testing garbage in it,
  # so until we fix the push to use the hg manifest recreate it on the other
  # side instead of syncing it.
  run('mkdir -p ~/%s/pythonpath' % dirname)
  with cd('~/%s/pythonpath' % dirname):
    run('ln -f -s ~/%s viewfinder' % dirname)

  # Delete the tarball. We never reuse it anyway.
  run('rm -f ~/%s' % filename)

  # code_cleanup is run on the last invocation (based on the size of env.hosts).
  code_cleanup()


@task
def code_activate(requirements_revision=None):
  """Make the code at revision active (latest if None)."""
  assert not is_old_code(), 'Active code is old-style (directory, not symlink). Manual intervention required!'
  req_rev = requirements_revision or hg_revision()
  assert code_verify(req_rev), 'Desired code revision %s invalid, cannot be made active' % req_rev
  # Note: -T forces the target to be treated as a normal file. Without it, the link will be:
  # ~/viewfinder/viewfinder.<rev> -> ~/viewfinder.<rev> instead of being in the home directory.
  run('ln -T -s -f ~/viewfinder.%s ~/viewfinder' % req_rev)
  fprint('Code at revision %s marked active.' % req_rev)


@task
def code_verify(revision=None):
  """Verify the code for a given revision (latest if None).
  We only check the symlink. TODO: find a way to validate the code itself."""
  if is_old_code():
    fprint('installed code is in the old style (directory instead of symlink). Manual intervention required')
    return False
  rev = revision or hg_revision()
  if exists('~/viewfinder.%s' % rev):
    fprint('Code at revision %s is installed' % rev)
    return True
  else:
    fprint('Code at revision %s is not installed' % rev)
    return False

@task
def virtualenv_install():
  """Install the latest virtual environment if needed.
  We do nothing if the env is already the latest.
  We do install the new environment even if we are using the old style.
  This does not activate (symlink) the newly installed environment.
  """
  # Installs the latest virtual environment from the local prod-requirements.txt.
  prod_rev = latest_requirements_revision()
  assert re.match(r'[0-9a-f]+', prod_rev)

  active_env_rev = active_env()
  if prod_rev == active_env_rev:
    assert virtualenv_verify(prod_rev), 'Active environment is not valid'
    return

  env_dir = 'env.%s' % prod_rev
  package_dir = 'python-package.%s' % prod_rev
  requirements_file = 'prod-requirements.txt.%s' % prod_rev
  if exists(env_dir):
    fprint('prod-requirements (rev %s) already installed, but not active.' % prod_rev)
  else:
    fprint('installing environment from prod-requirements (rev %s)' % prod_rev)
    run('rm -rf ~/%s ~/%s ~/%s' % (env_dir, package_dir, requirements_file))
    rsync_project(local_dir='third_party/python-package/', remote_dir='~/%s/' % package_dir, ssh_opts='-o StrictHostKeyChecking=no')
    put('scripts/prod-requirements.txt', '~/%s' % requirements_file)
    run('python2.7 ~/%s/virtualenv.py --never-download ~/%s/viewfinder' % (package_dir, env_dir))

  # Let fabric surface the failure.
  run('~/%s/viewfinder/bin/pip install -f file://$HOME/%s --no-index -r ~/%s' %
      (env_dir, package_dir, requirements_file))
  # Do not delete the prod-requirements file when done as we may use it to verify the environment later.


@task
def virtualenv_activate(requirements_revision=None):
  """Make the virtual env at revision active (latest if None)."""
  assert not is_old_env(), 'Active environment is old-style (directory, not symlink). Manual intervention required!'
  req_rev = requirements_revision or latest_requirements_revision()
  assert virtualenv_verify(req_rev), 'Desired env revision %s invalid, cannot be made active' % req_rev

  # Create sitecustomize.py file, which sets default str encoding as UTF-8.
  # See http://blog.ianbicking.org/illusive-setdefaultencoding.html.
  env_dir = 'env.%s' % req_rev
  run('echo "import sys; sys.setdefaultencoding(\'utf-8\')" > %s/viewfinder/lib/python2.7/sitecustomize.py' % env_dir);

  # Note: -T forces the target to be treated as a normal file. Without it, the link will be:
  # ~/viewfinder/viewfinder.<rev> -> ~/viewfinder.<rev> instead of being in the home directory.
  run('ln -T -s -f ~/env.%s ~/env' % req_rev)
  fprint('Environment at rev %s marked active.' % req_rev)


@task
def virtualenv_verify(requirements_revision=None):
  """Verify the virtual environment for a given revision (latest if None)."""
  req_rev = requirements_revision or latest_requirements_revision()

  env_dir = 'env.%s' % req_rev
  package_dir = 'python-package.%s' % req_rev
  requirements_file = 'prod-requirements.txt.%s' % req_rev
  with settings(warn_only=True):
    out = run('~/%s/viewfinder/bin/pip install -f file://$HOME/%s --no-index -r ~/%s --no-install --no-download -q' % (env_dir, package_dir, requirements_file))
  if out.return_code == 0:
    fprint('Valid virtual environment for prod-requirements (rev %s)' % req_rev)
    return True
  else:
    fprint('Bad virtual environment for prod-requirements (rev %s)' % req_rev)
    return False


@task
def install_crontab():
  """Install or remove crontab for given node type."""
  assert env.nodetype, 'no nodetype specified'
  assert env.host_string, 'no hosts specified'
  cron_file = '~/viewfinder/scripts/crontab.%s' % env.nodetype.lower()
  # Run 'crontab <filename>' if the remote file exists, otherwise run 'crontab -r'.
  # Warn only as 'crontab -r' fails if no crontab is installed.
  with settings(warn_only=True):
    run('if [ -e %s ]; then crontab %s; else crontab -r; fi' % (cron_file, cron_file))


@task
def yum_install():
  """Install required yum packages."""
  fprint('Installing yum packages.')
  sudo('yum -y update')
  sudo('yum -y install make zlib gcc gcc-c++ openssl-devel python27 python27-devel libcurl-devel pcre-devel')


@task
def haproxy_install():
  """Install and configure haproxy.
  HAProxy is not controlled by the prod-requirements file, and not easily versioned. As such, we install it in its
  own directory.
  TODO(marc): replace with yum package once 1.5 is stable and rolled out to AWS.
  """
  # rsync the haproxy source.
  fprint('Rsync thirdparty/haproxy ~/haproxy')
  rsync_project(local_dir='third_party/haproxy/', remote_dir='~/haproxy/', ssh_opts='-o StrictHostKeyChecking=no')

  # build haproxy and install it in ~/bin.}
  fprint('Building haproxy')
  run('haproxy/build.sh ~/')

  # Concatenate the certificate and key into a single file (this is expected by haproxy) and push it.
  fprint('Generating viewfinder.pem for haproxy')
  vf_passphrase = load_passphrase_from_file()
  # Staging and prod use the same certs.
  local('scripts/generate_haproxy_certificate.sh viewfinder.co %s viewfinder.pem' % vf_passphrase)
  run('mkdir -p ~/conf')
  run('rm -f ~/conf/viewfinder.pem')
  put('viewfinder.pem', '~/conf/viewfinder.pem')
  run('chmod 400 ~/conf/viewfinder.pem')

  # Remove local file.
  local('rm -f viewfinder.pem')

  # Install the config files.
  fprint('Pushing haproxy configs')
  assert env.nodetype, 'no nodetype specified'
  run('ln -f -s ~/viewfinder/scripts/haproxy.conf ~/conf/haproxy.conf')
  run('ln -f -s ~/viewfinder/scripts/haproxy.redirect.%s.conf ~/conf/haproxy.redirect.conf' % env.nodetype.lower())


def setup_instance(zone, name, existing_instance_id=None):
  if not existing_instance_id:
    region_zones = ec2_utils.GetELBZones(env.region, node_types=[env.nodetype])
    assert zone, 'Availability zone not specified, available zones are: %s' % ' '.join(region_zones)

    user_data = load_passphrase_from_file()
    instance_id = ec2_utils.RunInstance(env.region, BASE_AMI, 'wwwkey', kInstanceType,
                                        availability_zone=zone, user_data=user_data)
    fprint('Launched new instance: %s' % instance_id)
  else:
    instance_id = existing_instance_id
    fprint('Resuming setup of instance %s' % instance_id)

  fprint('Adding tags NodeType=%s and Name=%s to instance %s' % (env.nodetype, name, instance_id))
  ec2_utils.CreateTag(env.region, instance_id, 'NodeType', env.nodetype)
  ec2_utils.CreateTag(env.region, instance_id, 'Name', name)

  for i in range(60):
    match = ec2_utils.GetInstance(env.region, instance_id)
    if match is None:
      fprint('Instance %s does not exist yet; waiting.' % instance_id)
    elif match.state != 'running':
      fprint('Instance %s in state %s; waiting.' % (instance_id, match.state))
    else:
      break
    time.sleep(2)
  else:
    fprint('Timed out waiting for instance: %s' % instance_id)
    raise Exception("timeout")
  assert match is not None and match.state == 'running'
  instance_hostname = match.public_dns_name
  fprint('Instance %s in state "running". Public DNS: %s' % (instance_id, instance_hostname))
  with settings(host_string=instance_hostname):
    for i in range(60):
      try:
        run("true")
        break
      except NetworkError:
        fprint('Waiting for instance to be sshable: %s' % instance_id)
        # don't retry too aggressively, it looks like we get blocked by a
        # firewall for too many failed attempts
        time.sleep(3)
    else:
      fprint('timed out waiting for sshability')
      raise Exception("timeout")

    # Install required packages.
    yum_install()
  return instance_id, instance_hostname


@task
def drain():
  """Drain nodes of a given type.
  This removes the instance from the region load balancers for this instance type (STAGING or PROD).
  """
  ami = get_ami_metadata()
  instance_id = ami['instance-id']
  ec2_utils.RemoveELBInstance(env.region, instance_id, env.nodetype)
  fprint('Removed instance %s from %s load balancers' % (instance_id, env.nodetype))


@task
def undrain():
  """Undrain nodes of a given type.
  This adds the instance from the region load balancers for this instance type (STAGING or PROD).
  After addition, we query the load balancers until the instance health is InService.
  """
  ami = get_ami_metadata()
  instance_id = ami['instance-id']

  fprint('Waiting for healthy backend')
  num_healthz_ok = 0
  for i in range(60):
    if get_healthz():
      num_healthz_ok += 1
      if num_healthz_ok >= 3:
        break
    else:
      num_healthz_ok = 0
    time.sleep(2)
  if num_healthz_ok < 3:
    raise Exception('healthz timeout')

  ec2_utils.AddELBInstance(env.region, instance_id, env.nodetype)
  fprint('Added instance %s to %s load balancers' % (instance_id, env.nodetype))
  for i in range(60):
    health = ec2_utils.GetELBInstanceHealth(env.region, instance_id, node_types=[env.nodetype])
    if health is None:
      fprint('No load balancer health information for instance %s; waiting.' % instance_id)
    elif health == 'InService':
      fprint('Load balancer health for instance %s is InService.' % instance_id)
      return
    else:
      fprint('Load balancer health information for instance %s is %s; waiting.' % (instance_id, health))
    time.sleep(2)
  raise Exception('timeout')


def check_min_healthy_instances(min_healthy):
  """Lookup the number of instances by ELB state and assert if the minimum required is not met."""
  healthy = ec2_utils.GetELBInstancesByHealth(env.region, node_types=[env.nodetype])
  num_healthy = len(healthy['InService'])
  assert num_healthy >= min_healthy, 'Not enough backends with healthy ELB status (%d vs %d)' % \
                                     (num_healthy, min_healthy)

@task
def create_instance(nodetype, name, zone, existing_instance_id=None):
  """Create a new instance. Specify NodeType,Name,AvailabilityZone,[id_to_resume]."""
  env.nodetype = nodetype

  # Names must be unique across all node types.
  named_instances = ec2_utils.ListInstances(env.region, names=[name])
  if named_instances:
    assert len(named_instances) == 1, 'Multiple instances found with name %s' % name
    prev_id = named_instances[0].id
    assert existing_instance_id is not None and existing_instance_id == prev_id, \
      'Name %s already in use by instance %s' % (name, prev_id)
  assert name.startswith(nodetype), 'Instance name must start with %s' % nodetype

  instance_id, instance_hostname = setup_instance(zone, name, existing_instance_id=existing_instance_id)
  with settings(host_string=instance_hostname):
    deploy(new_instance=True)


@task
def destroy_instance(nodetype, instance_id):
  """Stop and terminate an instance. Specify NodeType and InstanceID."""
  env.nodetype = nodetype
  instance = ec2_utils.GetInstance(env.region, instance_id)
  assert instance, 'Instance %s not found' % instance_id
  with settings(host_string=instance.public_dns_name):
    if instance.state == 'running':
      check_min_healthy_instances(3)
      drain()
      stop()
  fprint('Terminating instance %s' % instance_id)
  ec2_utils.TerminateInstance(env.region, instance_id)


@task
def restart():
  """Restart supervisord and its managed jobs."""
  fprint('Restarting supervisord')
  sudo('cp ~ec2-user/viewfinder/scripts/supervisord.d /etc/init.d/supervisord')
  sudo('/etc/init.d/supervisord restart')


@task
def stop():
  """Stop supervisord and its managed jobs."""
  # TODO(marc): we should eventually use supervisordctl, but sending SIGTERM shuts it down properly for now.
  fprint('Stopping supervisord')
  # If we attempt a "deploy" with a new instance that hasn't been setup yet, we'll have no supervisord script to copy.
  with settings(warn_only=True):
    # We copy it since this may be the first call to supervisord.
    # TODO(marc): remove 'cp' once supervisord init script is installed everywhere.
    sudo('cp ~ec2-user/viewfinder/scripts/supervisord.d /etc/init.d/supervisord')
    sudo('/etc/init.d/supervisord stop')


@task
def drainrestart():
  """Drain and restart nodes."""
  check_min_healthy_instances(2)
  drain()
  # Stop first to make sure we no longer use the viewfinder init scripts.
  stop()
  restart()
  undrain()


@task
def deploy(new_instance=False):
  """Deploy latest environment and code and restart backends."""
  # Run yum update/install first. We may have new dependencies.
  yum_install()
  # Push and build haproxy.
  haproxy_install()
  # Stage code, environment, and crontab.
  virtualenv_install()
  code_install()
  install_crontab()

  if not new_instance:
    # Remove backend from load balancer and stop. This would fail on non-running instances.
    drain()
    stop()

  # Flip symlinks.
  virtualenv_activate()
  code_activate()

  # Restart backend and re-add to load balancer.
  restart()
  undrain()


@task
def status():
  """Overall production status."""
  cl_timestamps = defaultdict(str)
  def _ResolveCLDate(rev):
    if rev == '??' or rev in cl_timestamps.keys():
      return
    ts = hg_revision_timestamp(rev)
    if ts is not None:
      cl_timestamps[rev] = util.TimestampUTCToISO8601(ts)

  env_rev = latest_requirements_revision()
  code_rev = hg_revision()
  _ResolveCLDate(env_rev)
  _ResolveCLDate(code_rev)
  print '=' * 80
  print 'Local environment:'
  print '  Env revision: %s (%s)' % (env_rev, cl_timestamps.get(env_rev, '??'))
  print '  Code revision: %s (%s)' % (code_rev, cl_timestamps.get(code_rev, '??'))

  for nodetype in ec2_utils.kValidNodeTypes:
    elbs = ec2_utils.GetLoadBalancers(env.region, [nodetype])
    assert len(elbs) == 1, 'Need exactly one %s load balancer in %s' % (nodetype, env.region)

    elb = elbs[0]
    instances = ec2_utils.ListInstances(env.region, node_types=[nodetype])

    elb_zones = {z:0 for z in elb.availability_zones}
    elb_health = {h.instance_id: h.state for h in elb.get_instance_health()}

    for i in instances:
      id = i.id
      if i.state != 'running':
        continue
      zone = i.placement
      if zone in elb_zones.keys():
        elb_zones[zone] += 1
      if id in elb_health:
        setattr(i, '_elb_health', elb_health[id])
      with settings(host_string=i.public_dns_name):
        setattr(i, '_env_rev', active_env() or '??')
        setattr(i, '_code_rev', active_code() or '??')
        _ResolveCLDate(i._env_rev)
        _ResolveCLDate(i._code_rev)

    print '\n%s' % ('=' * 80)
    print '%s ELB: %s' % (nodetype, elb.name)
    print '  # Running instances by ELB zone:'
    zone_str = ', '.join(['%s: %s' % (k, v) for k, v in elb_zones.iteritems()])
    print '  %s' % zone_str

    print ''
    print '%s instances: %d' % (nodetype, len(instances))
    print '  # %-8s %-12s %-13s %-10s %-12s %-13s %-10s %-13s %-10s' % \
          ('ID', 'Name', 'State', 'Zone', 'ELB state', 'Active env', 'Env date', 'Active code', 'Code date')
    for i in instances:
      env_rev = getattr(i, '_env_rev', '')
      code_rev = getattr(i, '_code_rev', '')
      print '  %-10s %-12s %-13s %-10s %-12s %-13s %-10s %-13s %-10s' % (i.id,
                                                             i.tags.get('Name', ''),
                                                             i.state,
                                                             i.placement,
                                                             getattr(i, '_elb_health', ''),
                                                             env_rev,
                                                             cl_timestamps[env_rev],
                                                             code_rev,
                                                             cl_timestamps[code_rev])

    if instances and code_rev and cl_timestamps.get(code_rev):
      # If the deployed revision exists locally, create a bookmark to it (one per nodetype).
      # This allows queries like these (some aliases are defined in viewfinder.hgrc)
      #   hg log -r ::.-::deployed_staging
      #   hg log -r ::deployed_staging-::deployed_prod
      local("hg bookmark -f -r %s deployed_%s" % (code_rev, nodetype.lower()))


@task
def cleanup():
  """Cleanup old env and code."""
  assert env.host_string

  # Search for active env.
  active_env_rev = active_env()
  assert active_env_rev, 'No active env, this could be a problem; aborting.'
  active_env_date = hg_revision_timestamp(active_env_rev)
  assert active_env_date, 'Could not determine timestamp for active env revision %s; aborting.' % active_env_rev

  fprint('Current active environment is revision %s (%s)' %
         (active_env_rev, util.TimestampUTCToISO8601(active_env_date)))

  # Search for, and iterate over, all environments.
  installed_env_revs = run('ls -d ~/env.*')
  for r in installed_env_revs.split():
    if not r.strip():
      continue
    rev = get_file_suffix('env', r)
    if not rev:
      continue
    if rev == active_env_rev:
      continue
    ts = hg_revision_timestamp(rev)
    if not ts:
      continue
    if ts >= active_env_date:
      fprint('Env revision %s (%s) newer than active env revision %s (%s); skipping.' %
             (rev, util.TimestampUTCToISO8601(ts), active_env_rev, util.TimestampUTCToISO8601(active_env_date)))
      continue

    answer = fprompt('Delete unused environment revision %s (%s)?' % (rev, util.TimestampUTCToISO8601(ts)),
                     default='N', validate='[yYnN]')
    if answer == 'n' or answer == 'N':
      continue
    run('rm -r -f env.%s prod-requirements.txt.%s python-package.%s' % (rev, rev, rev))
    fprint('Deleted environment revision %s (%s)' % (rev, util.TimestampUTCToISO8601(ts)))

  # Search for active code.
  active_code_rev = active_code()
  assert active_code_rev, 'No active code, this could be a problem; aborting.'
  active_code_date = hg_revision_timestamp(active_code_rev)
  assert active_code_date, 'Could not determine timestamp for active code revision %s; aborting.' % active_code_rev

  fprint('Current active code is revision %s (%s)' %
         (active_code_rev, util.TimestampUTCToISO8601(active_code_date)))

  # Search for, and iterate over, all code.
  installed_code_revs = run('ls -d ~/viewfinder.*')
  for r in installed_code_revs.split():
    if not r.strip():
      continue
    rev = get_file_suffix('viewfinder', r)
    if not rev:
      continue
    if rev == active_code_rev:
      continue
    ts = hg_revision_timestamp(rev)
    if not ts:
      continue
    if ts >= active_code_date:
      fprint('Code revision %s (%s) newer than active code revision %s (%s); skipping.' %
             (rev, util.TimestampUTCToISO8601(ts), active_code_rev, util.TimestampUTCToISO8601(active_code_date)))
      continue

    answer = fprompt('Delete unused code revision %s (%s)?' % (rev, util.TimestampUTCToISO8601(ts)),
                     default='N', validate='[yYnN]')
    if answer == 'n' or answer == 'N':
      continue
    run('rm -r -f viewfinder.%s' % rev)
    fprint('Deleted code revision %s (%s)' % (rev, util.TimestampUTCToISO8601(ts)))
