#!/usr/bin/env python
"""Walks a directory, fingerprinting all .jpg files therein.

Output is a tab-separated file: filename TAB fingerprint
"""

import os

from tornado.options import parse_command_line

from imagefingerprint import FingerprintImage

def format_fp(fp):
  return ':'.join(s.encode('hex') for s in fp)

def main():
  args = parse_command_line()

  for arg in args:
    for dirpath, dirnames, filenames in os.walk(arg):
      for filename in filenames:
        if filename.lower().endswith('.jpg'):
          qualname = os.path.join(dirpath, filename)
          assert '\t' not in qualname
          fp = FingerprintImage(qualname)
          print '%s\t%s' % (qualname, format_fp(fp))

if __name__ == '__main__':
  main()
