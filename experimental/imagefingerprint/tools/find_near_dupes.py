#!/usr/bin/env python
"""Reads a fingerprint file and prints all near-duplicate images.

This is a python reimplementation of the indexing in ImageIndex.mm.

The input is a tab-separated file as produced by fingerprint_directory.py.
The output is: filename1 TAB filename2 TAB hamming distance.
"""

import collections
from tornado.options import parse_command_line, options, define

define('min', default=0)
define('max', default=12)

def parse_fp(fp):
  return [s.decode('hex') for s in fp.strip().split(':')]

kTagLengths =  [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 4]

def gen_tags(fp):
  for term in fp:
    term = term.encode('hex')
    pos = 0
    for l in kTagLengths:
      yield '%d:%s' % (pos, term[pos:pos+l])
      pos += l
    assert pos == len(term)

def count_bits(n):
  return bin(n).count('1')

def hamming(t1, t2):
  assert len(t1) == len(t2)
  total = 0
  for c1, c2 in zip(t1, t2):
    d = ord(c1) ^ ord(c2)
    total += count_bits(d)
  return total

def distance(fp1, fp2):
  return min(hamming(t1, t2) for t1 in fp1 for t2 in fp2)

class Index(object):
  def __init__(self):
    # maps tags -> list of filename, fingerprint pairs
    self.index = collections.defaultdict(list)

  def load(self, filename):
    with open(filename) as f:
      for line in f:
        filename, fingerprint = line.split('\t')
        fingerprint = parse_fp(fingerprint)
        for tag in gen_tags(fingerprint):
          self.index[tag].append((filename, fingerprint))

  def find_matches(self, min_hamming, max_hamming):
    assert min_hamming <= max_hamming
    assert max_hamming <= 12, 'accuracy not guaranteed for distance > 12'
    seen = set()
    for tag, lst in self.index.iteritems():
      for fn1, fp1 in lst:
        for fn2, fp2 in lst:
          if fn1 == fn2:
            continue
          key = tuple(sorted([fn1, fn2]))
          if key in seen:
            continue
          seen.add(key)
          dist = distance(fp1, fp2)
          if min_hamming <= dist <= max_hamming:
            print '%s\t%s\t%d' % (fn1, fn2, dist)

def main():
  args = parse_command_line()

  index = Index()
  for arg in args:
    index.load(arg)

  index.find_matches(options.min, options.max)

if __name__ == '__main__':
  main()
