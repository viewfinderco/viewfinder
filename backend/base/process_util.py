# Copyright 2012 Viewfinder Inc.  All Rights Reserved.
"""Utility functions for unix-style processes.
"""

__author__ = 'ben@emailscrubbed.com (Ben Darnell)'

import os
import sys

_process_name = None

# http://stackoverflow.com/questions/564695/is-there-a-way-to-change-effective-process-name-in-python
def SetProcessName(newname):
  '''Attempts to set the process name (as reported by tools like top).

  Only works on linux.  See also the pypi module `setproctitle`, which
  is a more robust and portable implementation of this idea.

  Setting the process name to the name of the main script file allows
  "pidof -x" (and therefore redhat-style init scripts) to work.
  '''
  global _process_name
  _process_name = newname
  try:
    from ctypes import cdll, byref, create_string_buffer
    libc = cdll.LoadLibrary('libc.so.6')
    buff = create_string_buffer(len(newname) + 1)
    buff.value = newname
    libc.prctl(15, byref(buff), 0, 0, 0)
  except:
    pass

def GetProcessName():
  if not _process_name:
    return os.path.basename(sys.argv[0])
  return _process_name
