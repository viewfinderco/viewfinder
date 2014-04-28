# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Class to generate a merged log file and upload it to S3.

Can fetch pre-existing file from S3, append to it locally, and finally upload the result to S3.
Local working file is generated using tempfile.mkstemp and suffixed with the dot-joined id_list.
Name and location in S3 are based on 'id_list' and 's3_base'.
The name of the logfile in S3 will be os.path.join(s3_base, *id_list).
If multiple LocalLogMerge instances are used at the same time, id_list should be unique for each one of them.

Sample usage:
  # S3 file is: <object_store_path>/merged_log/viewfinder/full/2013-02-01/i-a5e3f
  merge = LocalLogMerge(object_store, ['2013-02-01', 'i-a5e3f'], 'merged_log/viewfinder/full/')
  yield gen.Task(merge.FetchExistingFromS3)

  for line in file:
    merge.Append(line)              # Append a line to the buffer.
  if success:
    merge.FlushBuffer()             # Apply buffer to local file.
  else:
    merge.DiscardBuffer()           # Discard buffer.
  # Process another file if needed.

  merge.Close()                     # Flush buffer and close local file.
  yield gen.Task(merge.Upload)      # Upload local file to S3
  merge.Cleanup()                   # Delete local file

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import logging
import os
import tempfile

from tornado import gen
from viewfinder.backend.base import retry
from viewfinder.backend.storage import file_object_store, s3_object_store

# Retry policy for uploading files to S3 (merge logs and registry).
kS3UploadRetryPolicy = retry.RetryPolicy(max_tries=5, timeout=300,
                                         min_delay=1, max_delay=30,
                                         check_exception=retry.RetryPolicy.AlwaysRetryOnException)
class LocalLogMerge(object):
  """Class used to build a single merged log file locally."""

  def __init__(self, logs_store, id_list, s3_base):
    self._logs_store = logs_store
    self._s3_filename = os.path.join(s3_base, *id_list)
    fd, self._working_filename = tempfile.mkstemp(suffix='.' + '.'.join(id_list))
    self._output = os.fdopen(fd, 'w')
    self._buffer = []
    self._needs_separator = False

  @gen.engine
  def FetchExistingFromS3(self, callback):
    """If S3 already has a file for this day/instance, fetch it and write its contents to the
    local working file.
    """
    contents = yield gen.Task(self._logs_store.Get, self._s3_filename, must_exist=False)
    if contents is not None:
      logging.info('Fetched %d bytes from existing S3 merged log file %s' % (len(contents), self._s3_filename))
      self._output.write(contents)
      self._output.flush()
      self._needs_separator = True
    callback()

  def Append(self, entry):
    """Add a single entry to the buffer."""
    assert self._output is not None
    self._buffer.append(entry)

  def FlushBuffer(self):
    """Write out all entries in the buffer."""
    assert self._output is not None
    if not self._buffer:
      return
    for entry in self._buffer:
      if self._needs_separator:
        self._output.write('\n')
      self._needs_separator = True
      self._output.write(entry)
    self._output.flush()
    self._buffer = []

  def DiscardBuffer(self):
    """Discard all entries in the buffer."""
    self._buffer = []

  def Close(self):
    """Close the working file."""
    assert self._output is not None
    self.FlushBuffer()
    self._output.close()
    self._output = None

  @gen.engine
  def Upload(self, callback):
    """Upload working file to S3."""
    assert self._output is None, 'Upload called before Close.'
    contents = open(self._working_filename, 'r').read()
    # Assume 1MB/s transfer speed. If we don't have that good a connection, we really shouldn't be uploading big files.
    timeout = max(20.0, len(contents) / 1024 * 1024)
    yield gen.Task(retry.CallWithRetryAsync, kS3UploadRetryPolicy,
                   self._logs_store.Put, self._s3_filename, contents, request_timeout=timeout)
    logging.info('Uploaded %d bytes to S3 file %s' % (len(contents), self._s3_filename))

    callback()

  def Cleanup(self):
    """Delete the local working file."""
    os.unlink(self._working_filename)
