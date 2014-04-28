# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Command line S3 util.

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import logging
import os
import re
import subprocess
import sys
import time
import traceback

from functools import partial
from tornado import gen, options
from viewfinder.backend.base import main
from viewfinder.backend.db import db_client
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.storage import store_utils

# Options for 'bench'
options.define('bench_read', default=True, help='Benchmark reads. If false: writes')
options.define('bench_iterations', default=10, help='Number of iterations per size in bench.')
options.define('bench_parallel', default=False, help='Run benchmark in parallel.')
options.define('bench_size_powers', type=int, default=range(10, 21), multiple=True,
               help='Min and max file sizes to test, in power of two')

# Options for 'ls'
options.options.define('R', type=bool, default=False, help='Recursive')

# Options for 'mv'
options.options.define('verify', type=bool, default=True, help='Verify destination files on mv')
options.options.define('delete_source', type=bool, default=True, help='Delete source files on mv')

def PrintHelp():
  """Print the summary help message."""
  print 'Usage: s3util [options] [command] [file/dir ...]\n' \
        'Commands:\n' \
        '  bench [options] <test dir>        ; perform S3 benchmark\n' \
        '     -bench_read                    ; benchmark Get operation (Put if False) [True]\n' \
        '     -bench_iterations=X            ; number of iterations per size [10]\n' \
        '     -bench_parallel                ; run Put/Get requests within a size in parallel [False]\n', \
        '     -bench_size_powers=X,Y:Z       ; sizes to test, in powers of two [10:20]\n' \
        '  cat <file>                        ; output the contents of a file in S3. (Auto unzip of .gz files)\n' \
        '  grep [pattern] [file0 file1 ... ] ; search for regexp "pattern" in files. Auto unzip of .gz files.\n' \
        '  ls [options] [pattern]            ; list contents of a directory\n' \
        '     -R                             ; recursively list files [False]\n' \
        '  mv [options] [pattern] [dest]     ; move matching files to dest\n' \
        '     --verify                       ; verify destination files [True]\n' \
        '     --delete_source                ; delete source files [True]\n' \
        '  put <source file> <dest dir>      ; copy a file to a directory in S3\n'

@gen.engine
def Benchmark(args, callback):
  """Run read or write benchmark against S3."""
  assert len(args) == 1

  res = store_utils.ParseFullPath(args[0])
  assert res is not None, 'Test dir is not part of a registered bucket'
  bucket, test_dir = res

  is_read = options.options.bench_read
  num_iterations = options.options.bench_iterations

  test_data = []
  for i in options.options.bench_size_powers:
    size = 2**i
    name = os.path.join(test_dir, '%.10d' % size)
    data = os.urandom(size)
    test_data.append((size, name, data))

  store = ObjectStore.GetInstance(bucket)
  if is_read:
    logging.info('Preparing test files')
    yield [gen.Task(store.Put, filename, data) for _, filename, data in test_data]

  test_type = 'read' if is_read else 'write'
  print 'Running %s test with %d iterations per size' % (test_type, num_iterations)
  for fsize, fname, data in test_data:
    sys.stdout.write('%s %d bytes: ' % (test_type, fsize))
    start = time.time()
    total_size = 0
    tasks = []
    for i in xrange(num_iterations):
      if is_read:
        tasks.append(gen.Task(store.Get, fname))
      else:
        tasks.append(gen.Task(store.Put, fname, data))
      total_size += fsize
    if options.options.bench_parallel:
      yield tasks
    else:
      for t in tasks:
        yield t

    end = time.time()
    delta = end - start
    speed = total_size / delta / 1024
    sys.stdout.write('%.2fs, %.2fkB/s\n' % (delta, speed))

  logging.info('Cleaning up test files')
  yield [gen.Task(store.Delete, filename) for _, filename, _ in test_data]

  callback()


@gen.engine
def Cat(args, callback):
  """Cat a single file."""
  assert len(args) == 1
  filename = args[0]

  # Parse file name and extract bucket and relative path.
  resolved = store_utils.ParseFullPath(filename)
  assert resolved is not None, 'Cannot determine bucket from %s' % filename
  bucket, path = resolved
  store = ObjectStore.GetInstance(bucket)

  # Read file and iterate over each line.
  contents = yield gen.Task(store_utils.GetFileContents, store, path)
  print contents

  callback()


@gen.engine
def Grep(args, callback):
  """Grep a set of files."""
  assert len(args) >= 2
  pattern = re.compile(args[0])
  files = args[1:]

  bucket = store = None
  for f in files:
    # Parse file name and extract bucket and relative path.
    resolved = store_utils.ParseFullPath(f)
    assert resolved is not None, 'Cannot determine bucket from %s' % f
    b, path = resolved
    assert bucket is None or bucket == b, 'Input files must all be in the same bucket'

    if store is None:
      # Initialize ObjectStore for this bucket.
      bucket = b
      store = ObjectStore.GetInstance(bucket)

    # Read file and iterate over each line.
    contents = yield gen.Task(store_utils.GetFileContents, store, path)
    for line in contents.split('\n'):
      if pattern.search(line):
        print '%s:%s' % (f, line)

  callback()


@gen.engine
def List(args, callback):
  """List buckets/files/directories."""
  assert len(args) <= 1
  if len(args) == 0:
    # We intentionally ignore -R when listing buckets, we don't want to traverse all of S3.
    for b in store_utils.ListBuckets():
      print '%s/' % b
  else:
    pattern = args[0]
    res = store_utils.ParseFullPath(pattern)
    if not res:
      logging.warning('%s is not in a registered bucket' % pattern)
    else:
      bucket, path = res
      store = ObjectStore.GetInstance(bucket)
      if options.options.R:
        files = yield gen.Task(store_utils.ListRecursively, store, path)
      else:
        subdirs, files = yield gen.Task(store_utils.ListFilesAndDirs, store, path)
        for d in subdirs:
         print '%s/%s' % (bucket, d)
      for d in files:
        print '%s/%s' % (bucket, d)

  callback()


@gen.engine
def Move(args, callback):
  """Move all files a pattern to a directory."""
  assert len(args) == 2
  pattern = args[0]
  dest = args[1]

  res_src = store_utils.ParseFullPath(pattern)
  res_dst = store_utils.ParseFullPath(dest)
  assert res_src is not None and res_dst is not None, 'Source or destination not part of a registered bucket'
  assert res_src[0] == res_dst[0], 'Moving between buckets not supported'

  bucket, pattern = res_src
  dest_dir = res_dst[1]
  src_prefix = store_utils.PrefixFromPattern(pattern)
  assert dest_dir.endswith('/'), 'Destination must be a directory (with trailing slash)'
  assert not src_prefix.startswith(dest_dir) and not dest_dir.startswith(src_prefix), \
         'Source and destination must not intersect'

  source_dir = os.path.dirname(src_prefix) + '/'
  store = ObjectStore.GetInstance(bucket)
  # Get list of files matching the pattern as well as any existing files in the destination directory.
  source_files = yield gen.Task(store_utils.ListRecursively, store, pattern)
  res = yield gen.Task(store_utils.ListRecursively, store, dest_dir)
  dest_files = set(res)

  if len(source_files) == 0:
    callback()
    return

  answer = raw_input("Move %d files from %s/%s to %s/%s? [y/N] " %
                     (len(source_files), bucket, source_dir, bucket, dest_dir)).strip()
  if answer != 'y':
    callback()
    return

  done = 0
  last_update = 0.0
  bytes_read = bytes_written = 0
  for src_name in source_files:
    delta = time.time() - last_update
    if (delta) > 10.0:
      print '%d/%d, read %.2f KB/s, wrote %.2f KB/s' % (done, len(source_files),
                                                        bytes_read / delta / 1024, bytes_written / delta / 1024)
      last_update = time.time()
      bytes_read = bytes_written = 0

    done += 1
    dst_name = dest_dir + src_name[len(source_dir):]
    if dst_name in dest_files:
      last_update = 0.0
      answer = raw_input('File exists: %s/%s. Overwrite, skip, or abort? [o/a/S] ' % (bucket, dst_name))
      if answer == 'a':
        callback()
        return
      elif answer != 'o':
        continue

    # Read source file.
    contents = yield gen.Task(store.Get, src_name)
    bytes_read += len(contents)

    # Write destination file.
    yield gen.Task(store.Put, dst_name, contents)
    bytes_written += len(contents)

    if options.options.verify:
      # Read dest file back.
      dst_contents = yield gen.Task(store.Get, dst_name)
      bytes_read += len(dst_contents)
      if dst_contents != contents:
        logging.warning('Verification failed for %s/%s, deleting destination' % (bucket, dst_name))
        yield gen.Task(store.Delete, dst_name)
        continue

    if options.options.delete_source:
      # Delete original file.
      yield gen.Task(store.Delete, src_name)

  callback()


@gen.engine
def Put(args, callback):
  """Copy a single file to a S3 directory."""
  assert len(args) == 2
  source = args[0]
  dest = args[1]

  res_dst = store_utils.ParseFullPath(dest)
  assert res_dst is not None, 'Destination not part of a registered bucket'
  bucket = res_dst[0]
  dest_dir = res_dst[1]
  assert dest_dir.endswith('/'), 'Destination must be a directory (with trailing slash)'

  # Check existence and readability of source file.
  if not os.access(source, os.F_OK):
    print 'Source file does not exist: %s' % source
    callback()
    return
  if not os.access(source, os.R_OK):
    print 'Source file is not readable: %s' % source
    callback()
    return

  # Check whether the destination exists.
  store = ObjectStore.GetInstance(bucket)
  dst_file = os.path.join(dest_dir, os.path.basename(source))
  exists = yield gen.Task(store_utils.FileExists, store, dst_file)
  if exists:
    answer = raw_input('Destination exists: %s/%s. Overwrite or skip? [o/S] ' % (bucket, dst_file))
    if answer != 'o':
      callback()
      return

  with open(source, 'r') as f:
    contents = f.read()
  # Assume 1MB/s transfer speed. If we don't have that good a connection, we really shouldn't be uploading big files.
  timeout = max(20.0, len(contents) / 1024 * 1024)
  yield gen.Task(store.Put, dst_file, contents, request_timeout=timeout)
  # We just assume that no exception means no failure, which is true for now.
  print '%s/%s: %d bytes OK' % (bucket, dst_file, len(contents))

  callback()


if __name__ == '__main__':
  # parse_command_line stops at the first non-options. Filter those out (we'll need them) and rerun.
  options.options.logging = 'warning'
  commands = []
  # parse_command_line skips the first argument, even if we provide the list.
  new_args = [sys.argv[0]]
  for a in options.parse_command_line(final=False):
    if a.startswith('-'):
      new_args.append(a)
    else:
      commands.append(a)
  options.parse_command_line(args=new_args)

  if len(commands) == 0:
    PrintHelp()
    sys.exit(0)

  cmd = commands[0]
  cmd_args = commands[1:]
  if cmd == 'bench':
    cb = Benchmark
  elif cmd == 'cat':
    cb = Cat
  elif cmd == 'grep':
    cb = Grep
  elif cmd == 'ls':
    cb = List
  elif cmd == 'mv':
    cb = Move
  elif cmd == 'put':
    cb = Put
  else:
    print 'Unknown command: %s' % cmd
    PrintHelp()
    sys.exit(0)

  sys.exit(main.InitAndRun(partial(cb, cmd_args), server_logging=False))
