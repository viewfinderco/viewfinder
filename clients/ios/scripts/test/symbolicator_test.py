#!/usr/bin/env python
#
# Copyright 2013 Viewfinder Inc. All Rights Reserved.

import cStringIO
import glob
import mock
import os
import unittest

from viewfinder.clients.ios.scripts import symbolicator

kTestDir = os.path.dirname(__file__)

# When the symbolicator output changes, run the test with this set to true to refresh the files.
kRefreshOutput = False

class SymbolicatorRegressionTest(unittest.TestCase):
  """A very crude test that ensures we stay compatible with old crash logs."""
  def test_past_output(self):
    if not os.path.exists(os.path.expanduser('~/Dropbox/viewfinder/dSYMS')):
      raise unittest.SkipTest('iOS symbol files not found')
    for filename in glob.glob(os.path.join(kTestDir, 'data/*.crash')):
      print filename
      output_buffer = cStringIO.StringIO()
      with mock.patch('sys.stdout', output_buffer):
        symbolicator.main(['symbolicator', filename])
      output = output_buffer.getvalue()
      if kRefreshOutput:
        with open(filename + '.out', 'w') as f:
          f.write(output)
      with open(filename + '.out') as f:
        expected = f.read()
      self.assertEqual(expected, output)
