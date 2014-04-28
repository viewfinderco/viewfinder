#!/usr/bin/env python
#
# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Utilities for EC2 interaction.

Basic wrappers around boto EC2 libraries. Can be run in standalone or as a library.

Examples:
# List all instances.
$ python -m viewfinder.backend.prod.ec2_utils --op=list
# List running PROD instances.
$ python -m viewfinder.backend.prod.ec2_utils --op=list  --states=running --node_types=PROD

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import boto

from boto.ec2 import elb, regions
from boto.exception import EC2ResponseError
from collections import defaultdict
from tornado import options

kValidNodeTypes = ['PROD', 'STAGING']
kValidRegions = sorted([i.name for i in regions()])
kValidStateNames = ['pending', 'running', 'shutting-down', 'terminated', 'stopping', 'stopped']
kLoadBalancerNames = {'PROD': 'www-elb', 'STAGING': 'www-elb-staging'}

def _Connect(region):
  """Verify region and return an EC2 connection object."""
  ec2_region = None
  for r in regions():
    if r.name == region:
      ec2_region = r
      break
  assert ec2_region is not None, '"%s" not in the list of ec2 regions: %s' % \
                                 (region, ', '.join(kValidRegions))

  return boto.connect_ec2(region=ec2_region)


def _ConnectELB(region_name):
  """Connect to a given region for load balancer queries."""
  return elb.connect_to_region(region_name)


#################### Functions performing actual EC2 requests ########################

def ListInstances(region, instances=None, node_types=[], states=[], names=[]):
  """List instance DNS names in a given region. By default, return all instances.

  Defailed list of available filters can be found at:
  http://docs.aws.amazon.com/AWSEC2/latest/APIReference/ApiReference-query-DescribeInstances.html

  Can be filtered by:
   - instance_id
   - node_type (PROD or STAGING)
   - state (running, pending, etc...)
   - instance name (STAGING_0001, PROD_0004, etc...)

  Returns a list of matching instances (boto.ec2.instance.Instance).
  If instance IDs are specified and one or more is not found, an EC2ResponseError exception is thrown.
  """
  ec2 = _Connect(region)

  filters = {}
  if node_types:
    for i in node_types:
      assert i in kValidNodeTypes, '"%s" not in the list of valid node types: %s' % (i, ', '.join(kValidNodeTypes))
    filters['tag:NodeType'] = node_types

  if names:
    filters['tag:Name'] = names

  if states:
    for i in states:
      assert i in kValidStateNames, '"%s" not in the list of valid state names: %s' % (i, ', '.join(kValidStateNames))
    filters['instance-state-name'] = states

  matches = []
  for r in ec2.get_all_instances(instance_ids=instances, filters=filters):
    matches.extend(r.instances)
  return matches


def GetOwnerIDs(region):
  """Return the list of owner IDs in this region's security groups."""
  ec2 = _Connect(region)
  return [g.owner_id for g in ec2.get_all_security_groups()]


def GetImages(region, owner_ids=None):
  """Return the list of images owned IDs from 'owner_ids'. If None or empty, we return nothing."""
  ec2 = _Connect(region)
  if not owner_ids:
    return None
  return ec2.get_all_images(owners=owner_ids)


def GetLoadBalancers(region, node_types=None):
  """Return all load balancers in a given region. 'node_types' is an optional list of node-types; if not None,
  we will only lookup load balancers for those types.
  """
  elb_names = []
  if node_types is not None:
    for n in node_types:
      assert n in kLoadBalancerNames.keys(), \
          'node_type %s does not have an associated load balancer (%r)' % (n, kLoadBalancerNames)
      elb_names.append(kLoadBalancerNames[n])
  if not elb_names:
    elb_names = None

  ec2_elb = _ConnectELB(region)
  return ec2_elb.get_all_load_balancers(load_balancer_names=elb_names)


def CreateTag(region, resource_id, tag_name, tag_value):
  """Create a tag for 'resource_id' with specified name and value. 'tag_value' can be None."""
  ec2 = _Connect(region)
  ec2.create_tags([resource_id], {tag_name: tag_value})


def GetAvailabilityZones(region):
  """Retrieve the list of availability zones for 'region'. Returns list of names."""
  ec2 = _Connect(region)
  return [z.name for z in ec2.get_all_zones()]


def RunInstance(region, ami_id, keypair_name, instance_type, availability_zone=None, user_data=None):
  """Run a new instance in the given region. Returns the created instance ID."""
  ec2 = _Connect(region)
  ret = ec2.run_instances(ami_id, key_name=keypair_name, user_data=user_data, instance_type=instance_type,
                          placement=availability_zone)
  assert ret and len(ret.instances) == 1
  return ret.instances[0].id


def TerminateInstance(region, instance_id):
  """Terminate instance_id in region."""
  ec2 = _Connect(region)
  ec2.terminate_instances([instance_id])


#################### Convenience wrappers ########################

def ListInstancesDNS(region, instances=None, node_types=[], states=[], names=[]):
  """Return a list of DNS names for instances matching the arguments.
  If instance IDs are specified and one or more is not found, an EC2ResponseError exception is thrown.
  """
  return [i.public_dns_name for i in ListInstances(region, instances=instances,
                                                   node_types=node_types, states=states, names=names)]


def GetInstance(region, instance_id):
  """Find a specific instance given its ID. Returns a boto.ec2.instance.Instance object if found, else None."""
  try:
    matches = ListInstances(region, instances=[instance_id])
  except EC2ResponseError as e:
    if e.error_code == 'InvalidInstanceID.NotFound':
      return None
    raise

  if len(matches) == 0:
    return None
  assert len(matches) == 1
  return matches[0]


def ListImages(region):
  """Display the list of images in a given region."""
  all_images = GetImages(region, GetOwnerIDs(region))
  running_images = set([i.image_id for i in ListInstances(region)])

  if len(all_images) == 0:
    print 'No images in region %s' % region
    return
  print '# %-14s %-8s %-40s %-40s' % ('ID', 'Active', 'Name', 'Description')
  for i in all_images:
    active_str = 'ACTIVE' if i.id in running_images else ''
    print '%-16s %-8s %-40s %-40s' % (i.id, active_str, i.name, i.description)


def ListELB(region, node_types=None):
  """Print load balancer configuration in this region. If 'node_types' is not None, only return the corresponding
  load balancers.
  """
  elbs = GetLoadBalancers(region, node_types)
  for l in elbs:
    zone_count = {z:0 for z in l.availability_zones}
    instances = ListInstances(region, instances=[i.id for i in l.instances])
    instances_dict = {i.id: i for i in instances}
    unknown = 0
    for i in instances:
      if i.placement in zone_count.keys():
        zone_count[i.placement] += 1
      else:
        unknown += 1
    zone_str = 'zones: ' + ' '.join(['%s[%d]' % (k, v) for k, v in zone_count.iteritems()])
    if unknown > 0:
      zone_str += ' unknown[%d]' % unknown
    print '%s: %s' % (l.name, zone_str)
    states = l.get_instance_health()
    for s in states:
      print '  %-16s %-20s %-30s' % (s.instance_id, instances_dict[s.instance_id].placement, s.state)


def GetELBInstanceHealth(region, instance_id, node_types=None):
  """Lookup an instance in the load balancers in a region and return its health status. Returns None if no
  load balancers are found or if the instance is not found.
  If node_types is specified, only look for load balancers for those types.
  Possible return values are None, 'InService', or 'OutOfService'.
  """
  balancers = GetLoadBalancers(region, node_types=node_types)
  if not balancers:
    return None
  for b in balancers:
    for state in b.get_instance_health():
      if state.instance_id == instance_id:
        return state.state
  return None


def GetELBInstancesByHealth(region, node_types=None):
  """Return a dict of instance IDs by health state for the load balancers in a given region.
  If node_types is not None, only query load balancers for those types.
  """
  balancers = GetLoadBalancers(region, node_types=node_types)
  res = defaultdict(list)
  for b in balancers:
    for state in b.get_instance_health():
      res[state.state].append(state.instance_id)

  return res


def GetELBZones(region, node_types=None):
  """Return a list of availability zone names covered by the load balancers in a given region.
  If node_types is not None, only query load balancers for those types.
  """
  balancers = GetLoadBalancers(region, node_types=node_types)
  res = []
  for b in balancers:
    res.extend(b.availability_zones)

  return res


def RemoveELBInstance(region, instance_id, node_type):
  """Add an instance to the load balancer in 'region'. 'node_type' is one of STAGING or PROD.
  Adding an existing instance does nothing.
  Asserts if the load balancer was not found or the instance was not previously registered.
  """
  balancers = GetLoadBalancers(region, node_types=[node_type])
  assert balancers, 'No %s load balancer in region %s' % (node_type, region)
  assert len(balancers) == 1
  b = balancers[0]
  balancer_instances = set([i.id for i in b.instances])
  if instance_id not in balancer_instances:
    print 'Instance %s not found in %s load balancer in regions %s' % (instance_id, node_type, region)
    return
  b.deregister_instances([instance_id])
  print 'Removed instance %s from %s load balancer in region %s' % (instance_id, node_type, region)


def AddELBInstance(region, instance_id, node_type):
  """Add an instance to the load balancer in 'region'. 'node_type' is one of STAGING or PROD.
  Adding an existing instance does nothing.
  """
  balancers = GetLoadBalancers(region, node_types=[node_type])
  assert balancers, 'No %s load balancer in region %s' % (node_type, region)
  assert len(balancers) == 1
  b = balancers[0]
  b.register_instances([instance_id])
  print 'Added instance %s to %s load balancer in region %s' % (instance_id, node_type, region)


def main():
  options.define('op', default=None, help='Operation: elb-list, elb-add-instance, elb-del-instance, '
                                          'list, list-images')

  options.define('region', default='us-east-1',
                 help='Region. One of %s' % ', '.join(kValidRegions))

  options.define('instances', default=None, multiple=True,
                 help='List of EC2 instance IDs to lookup')

  options.define('names', default=None, multiple=True,
                 help='Instance names.')

  options.define('node_types', default=None, multiple=True,
                 help='Node types. One or more of: %s' % ', '.join(kValidNodeTypes))

  options.define('states', default=None, multiple=True,
                 help='Instance states. One or more of: %s' % ', '.join(kValidStateNames))

  options.parse_command_line()
  op = options.options.op
  assert op is not None

  if op == 'list':
    # We should probably display more useful information.
    dns = ListInstancesDNS(options.options.region,
                           options.options.instances,
                           options.options.node_types,
                           options.options.states,
                           options.options.names)
    print '\n'.join(dns)
  elif op == 'elb-list':
    ListELB(options.options.region, options.options.node_types)
  elif op == 'elb-add-instance':
    assert len(options.options.instances) == 1, 'Must specify exactly one instance on --instances'
    assert len(options.options.node_types) == 1, 'Must specify exactly one --node_types'
    AddELBInstance(options.options.region, options.options.instances[0], options.options.node_types[0])
  elif op == 'elb-del-instance':
    assert len(options.options.instances) == 1, 'Must specify exactly one instance on --instances'
    assert len(options.options.node_types) == 1, 'Must specify exactly one --node_types'
    RemoveELBInstance(options.options.region, options.options.instances[0], options.options.node_types[0])
  elif op == 'list-images':
    ListImages(options.options.region)


if __name__ == "__main__":
  main()
