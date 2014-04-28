# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Enumeration of lock resource types.

Locks are acquired on resources. Each resource has a type and an id. The
resource type needs to be a unique string that ensures there is no conflict
between locks of different types. This enumeration lists the resource types
for locks taken by the Viewfinder backend.
"""

__author__ = 'andy@emailscrubbed.com (Andy Kimball)'


class LockResourceType:
  """Set of resource types used for locking. Each lock resource type should
  be two or three characters that are different from all other types. The
  resource type is concatenated with the resource id to form the lock id.
  For example:
    op:123
    vp:v--F
  """
  Job       = 'job'   # Resource id is job name (dbchk, get_logs, etc...).
  Operation = 'op'    # Resource id is user that initiated operation.
  Viewpoint = 'vp'    # Resource id is the viewpoint id.
