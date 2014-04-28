#!/usr/bin/env python
"""Process iTunes subscription renewals.

This script finds all recently-expired subscriptions and checks with iTunes to see if they have been
renewed.  To account for transient failures and delays in processing, it should be run from cron so
that it runs several times within the EXPIRATION_GRACE_PERIOD.

NOTE: We currently process every subscription which expired within EXPIRATION_GRACE_PERIOD, even
if a previous run of this script already handled its renewal.  This is safe but inefficient.  When
we have more subscriptions we should probably make this smarter.

Usage:
  python -m viewfinder.backend.services.tools.itunes_renew
"""

import logging
import time
from tornado import gen, options
from tornado.httpclient import AsyncHTTPClient

from viewfinder.backend.base.main import InitAndRun
from viewfinder.backend.db.db_client import DBClient
from viewfinder.backend.db.job import Job
from viewfinder.backend.db.operation import Operation
from viewfinder.backend.db.subscription import Subscription
from viewfinder.backend.op.op_manager import OpManager
from viewfinder.backend.op.operation_map import DB_OPERATION_MAP
from viewfinder.backend.services.itunes_store import ITunesStoreClient, VerifyResponse

options.define('require_lock', type=bool, default=True,
               help='attempt to grab the job:itunes_renew lock before running. Exit if acquire fails.')

EXPIRATION_GRACE_PERIOD = 7 * 24 * 3600

def ShouldProcess(sub):
  if sub.payment_type != 'itunes':
    return False
  expiration_delta = time.time() - sub.expiration_ts
  if expiration_delta < 0:  # hasn't expired yet
    return False
  if expiration_delta > EXPIRATION_GRACE_PERIOD:  # expired too long ago
    return False
  return True

@gen.coroutine
def ProcessSubscription(db_client, sub):
  logging.info('processing subscription %s for user %d, expired %s', sub.transaction_id, sub.user_id,
               time.ctime(sub.expiration_ts))
  assert sub.renewal_data, 'subscription without renewal_data'
  response = yield gen.Task(ITunesStoreClient.Instance('prod').VerifyReceipt, sub.renewal_data)
  if response.GetStatus() == VerifyResponse.EXPIRED_ERROR:
    # The subscription has not been renewed (yet).  Do nothing now and check it again next time
    # the script runs until the grace period expires.
    return
  assert response.IsValid(), 'new subscription is not valid'
  new_transaction_id = Subscription.GetITunesTransactionId(response)
  if new_transaction_id != sub.transaction_id:
    # Sanity check the new subscription
    assert not response.IsExpired(), 'new transaction already expired at %s' % response.GetExpirationTime()
    assert Subscription.GetITunesSubscriptionId(response) == sub.subscription_id, 'subscription id changed'

    logging.info('recording new subscription %s for user %d', new_transaction_id, sub.user_id)
    op_request = {
      'headers': {'synchronous': True},
      'user_id': sub.user_id,
      'verify_response_str': response.ToString(),
      }
    yield gen.Task(Operation.CreateAndExecute, db_client, sub.user_id, Operation.ANONYMOUS_DEVICE_ID,
                   'Subscription.RecordITunesTransactionOperation', op_request)

@gen.coroutine
def RunOnce():
  db_client = DBClient.Instance()
  http_client = AsyncHTTPClient()
  ITunesStoreClient.SetInstance('prod', ITunesStoreClient(environment='prod', http_client=http_client))
  OpManager.SetInstance(OpManager(op_map=DB_OPERATION_MAP, client=db_client, scan_ops=False))
  last_key = None
  while True:
    results, last_key = yield gen.Task(Subscription.Scan, db_client, None, limit=1000, excl_start_key=last_key)

    for sub in results:
      if ShouldProcess(sub):
        yield ProcessSubscription(db_client, sub)

    if last_key is None:
      break

@gen.engine
def Main(callback):
  client = DBClient.Instance()
  job = Job(client, 'itunes_renew')

  if options.options.require_lock:
    got_lock = yield gen.Task(job.AcquireLock)
    if not got_lock:
      logging.warning('Failed to acquire job lock; exiting.')
      callback()
      return

  try:
    yield RunOnce()
  finally:
    yield gen.Task(job.ReleaseLock)

  callback()

if __name__ == '__main__':
  InitAndRun(Main)
