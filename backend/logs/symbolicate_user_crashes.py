# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Symbolicate user crash logs.

This looks for unprocessed crash logs in s3://serverdata/merged_user_crashed/, symbolicates them, and sends a
summary email.

REQUIREMENTS:
- run on OSX for dependencies (mdfind, dwarfdump, atos)
- have the build dSyms on the local filesystem (default is ~/Dropbox/viewfinder/{dSYMs,dSYMs.uuid}

TODO: it would be great if we had a way to dump all symbols, allowing us to run this anywhere.

This grabs the 'client_logs_analysis' dynamodb lock to ensure we do not run at the same time as get_client_logs.py.

Usage:
# Symbolicate new crash logs and email summary
python -m viewfinder.backend.logs.symbolicate_user_crashes --devbox
# Don't write symbolicated files to S3 and log the summary email instead of sending.
python -m viewfinder.backend.logs.symbolicate_user_crashes --devbox --dry_run=True --send_email=False

Other options:
-require_lock: default=True: hold the job:client_logs_analysis lock during processing.
-send_email: default=True: email crash summaries (if any)
-email: recipient for summary emails
-show_at_most: default=2: show at most this many full crash logs in summary email

"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import cStringIO
import json
import logging
import numpy
import os
import re
import sys
import time
import traceback

from collections import defaultdict
from tornado import gen, options
from viewfinder.backend.base import constants, main, statistics, util
from viewfinder.backend.base.dotdict import DotDict
from viewfinder.backend.db import db_client
from viewfinder.backend.db.job import Job
from viewfinder.backend.logs import logs_util
from viewfinder.backend.services.email_mgr import EmailManager, LoggingEmailManager, SendGridEmailManager
from viewfinder.backend.storage.object_store import ObjectStore
from viewfinder.backend.storage import store_utils
from viewfinder.clients.ios.scripts.symbolicator import Symbolicator

options.define('dry_run', default=True, help='Do not update dynamodb metrics table')
options.define('require_lock', type=bool, default=True,
               help='attempt to grab the job:client_logs_analysis lock before running. Exit if acquire fails.')
options.define('send_email', type=bool, default=True,
               help='Email crash summary')
options.define('email', default='crash-reports+client@emailscrubbed.com', help='Email address to notify')
options.define('show_at_most', type=int, default=100,
               help='Show at most this many symbolicated crashes in email summary')
options.define('s3_url_expiration_days', default=14, help='Time to live in days for S3 URLs')

@gen.engine
def SendEmail(title, text, callback):
  args = {
    'from': 'crash-reports+client@emailscrubbed.com',
    'fromname': 'Symbolicator',
    'to': options.options.email,
    'subject': title,
    'text': text
  }
  yield gen.Task(EmailManager.Instance().SendEmail, description=title, **args)
  callback()


@gen.engine
def RunOnce(client, callback):
  # Find all crash files.
  merged_store = ObjectStore.GetInstance(logs_util.UserCrashLogsPaths.MERGED_LOGS_BUCKET)
  files = yield gen.Task(store_utils.ListAllKeys, merged_store, prefix='merged_user_crashes')

  crash_files = set()
  symbolicated_files = set()
  for f in files:
    if f.endswith('.crash') or f.endswith('.crash.gz'):
      crash_files.add(f)
    elif f.endswith('.crash.symbol') or f.endswith('.crash.gz.symbol'):
      # Strip '.symbol'.
      symbolicated_files.add(f[:-7])

  missing = crash_files.difference(symbolicated_files)

  """
  A sample list of files to test with. Should probably go away in favor of cmdline.
  missing = [
  'merged_user_crashes/8339/2013-07-25/dev-18194-01-17-14.918-2.0.1.61.crash',
  'merged_user_crashes/7872/2013-07-24/dev-17246-17-46-07.277-2.0.1.61.crash',
  'merged_user_crashes/8246/2013-07-25/dev-17947-00-07-59.215-2.0.1.61.crash',
  'merged_user_crashes/8246/2013-07-25/dev-17947-00-08-17.822-2.0.1.61.crash',
  'merged_user_crashes/8342/2013-07-25/dev-18136-00-58-09.061-2.0.1.61.crash',
  'merged_user_crashes/2286/2013-07-24/dev-17163-15-19-11.778-2.1.0.70.dev.jailbroken.crash',
  'merged_user_crashes/8768/2013-07-25/dev-18941-06-04-18.591-2.0.2.69.crash',
  'merged_user_crashes/8339/2013-07-25/dev-18194-01-18-17.613-2.0.1.61.crash',
  'merged_user_crashes/8074/2013-07-24/dev-17645-23-19-33.700-2.0.1.61.crash',
  'merged_user_crashes/8320/2013-07-25/dev-18096-01-31-49.906-2.0.1.61.crash',
  'merged_user_crashes/8246/2013-07-25/dev-17947-00-09-11.781-2.0.1.61.crash',
  'merged_user_crashes/8751/2013-07-25/dev-18910-05-54-43.572-2.0.2.69.crash',
  'merged_user_crashes/8246/2013-07-25/dev-17947-00-09-19.120-2.0.1.61.crash',
  'merged_user_crashes/8341/2013-07-25/dev-18134-00-46-50.904-2.0.1.61.crash',
  'merged_user_crashes/8316/2013-07-25/dev-18080-02-14-49.269-2.0.1.61.crash',
  'merged_user_crashes/8743/2013-07-25/dev-18898-05-40-50.450-2.0.1.61.crash',
  'merged_user_crashes/8074/2013-07-24/dev-17645-23-12-56.844-2.0.1.61.crash',
  'merged_user_crashes/2286/2013-07-24/dev-17163-15-19-20.884-2.1.0.70.dev.jailbroken.crash',
  'merged_user_crashes/8093/2013-07-24/dev-17650-23-29-34.198-2.0.1.61.crash',
  'merged_user_crashes/8339/2013-07-25/dev-18194-01-17-40.123-2.0.1.61.crash',
  'merged_user_crashes/8074/2013-07-24/dev-17645-23-19-41.996-2.0.1.61.crash'
  ]
  """

  logging.info('Found %d crash logs, %d missing: %r' % (len(crash_files), len(missing), missing))
  if not missing:
    callback()
    return

  missing_crashes = sorted(list(missing))
  processed_crashes = {}
  failures = {}
  for f in missing_crashes:
    try:
      # We could encounter any number of failures in get, symbolicate, and put.
      contents = yield gen.Task(merged_store.Get, f)
      # Is there a single command to do this?
      lines = [l + '\n' for l in contents.split('\n')]
      sym = Symbolicator()
      sym.process_one_file(lines)

      newfile = f + '.symbol'
      if not options.options.dry_run:
        yield gen.Task(merged_store.Put, newfile, sym.FullOutput())
        logging.info('Wrote %d bytes to %s' % (len(sym.FullOutput()), newfile))

      # We write the full symbolicated file to S3, but the summary email only includes
      # the summary: preamble + crashed thread backtrace.
      out_dict = sym.OutputDict()
      out_dict['filename'] = newfile
      processed_crashes[newfile] = out_dict
    except:
      msg = traceback.format_exc()
      logging.error('Failed to process %s: %s' % (f, msg))
      failures[f] = msg

  logging.info('Successfully processed crashes: %r' % processed_crashes.keys())
  logging.info('Symbolicate failures: %r' % failures)
  # Generate the email. Keys for 'processed_crashes' are the final filenames (with .symbol).
  # For 'failures', keys are the non-symbolicated filenames.
  title = '%d new client crashes' % len(missing_crashes)
  text = title + '\n'

  def _S3URL(filename):
    return merged_store.GenerateUrl(filename,
                                    expires_in=constants.SECONDS_PER_DAY * options.options.s3_url_expiration_days,
                                    content_type='text/plain')

  if failures:
    title += ' (%d failed during processing)' % len(failures)
    text += '\nProcessing failures: %d\n' % len(failures)
    for f, tb in failures.iteritems():
      text += '--------------------------\n'
      text += 'Non-symbolicated file: %s\n%s\n' % (_S3URL(f), tb)

  if processed_crashes:
    deduped_crashes = defaultdict(list)
    for v in processed_crashes.values():
      deduped_crashes[v['crashed_thread_backtrace']].append(v)
    text += '\n%d symbolicated crashes, %d after deduping\n\n' % \
            (len(processed_crashes), len(deduped_crashes))

    for crash_set in deduped_crashes.values():
      text += '--------------------------\n'
      text += '%d crashes after deduping. Full symbolicated files:\n' % len(crash_set)
      for c in crash_set:
        text += '%s\n' % _S3URL(c['filename'])
      text += '\nFirst crash:\n%s%s%s\n' % (c['preamble'], c['crashed_thread_title'],
                                            c['crashed_thread_backtrace'])


  yield gen.Task(SendEmail, title, text)
  callback()


@gen.engine
def Start(callback):
  assert sys.platform == 'darwin', 'This script can only run on OSX. You are using %s' % sys.platform

  """Grab a lock on job:client_logs_analysis and call RunOnce."""
  client = db_client.DBClient.Instance()
  job = Job(client, 'client_logs_analysis')

  if options.options.send_email:
    # When running on devbox, this prompts for the passphrase. Skip if not sending email.
    EmailManager.SetInstance(SendGridEmailManager())
  else:
    EmailManager.SetInstance(LoggingEmailManager())

  if options.options.require_lock:
    got_lock = yield gen.Task(job.AcquireLock)
    if got_lock == False:
      logging.warning('Failed to acquire job lock: exiting.')
      callback()
      return

  # We never call job.Start() since we don't want a summary status written to the DB, just the lock.
  try:
    yield gen.Task(RunOnce, client)
  except:
    logging.error(traceback.format_exc())
  finally:
    yield gen.Task(job.ReleaseLock)

  callback()


if __name__ == '__main__':
  sys.exit(main.InitAndRun(Start))
