# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Client access to DynamoDB backend.

The client marshals and unmarshals Viewfinder schema objects and
parameters to/from the DynamoDB JSON-encoded format.

  DynamoDBClient
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

import heapq
import json
import logging
import time

from boto.exception import DynamoDBResponseError
from collections import namedtuple
from functools import partial
from tornado import gen, ioloop, stack_context
from viewfinder.backend.base import secrets, util, counters, rate_limiter
from viewfinder.backend.base.exceptions import DBProvisioningExceededError, DBLimitExceededError
from viewfinder.backend.base.util import ConvertToString, ConvertToNumber
from viewfinder.backend.db.asyncdynamo import AsyncDynamoDB
from db_client import DBClient, DBKey, ListTablesResult, CreateTableResult, DescribeTableResult, DeleteTableResult, GetResult, PutResult, DeleteResult, UpdateResult, QueryResult, ScanResult, BatchGetResult, DBKeySchema, TableSchema

# List of tables for which we want to save qps/backoff metrics.
kSaveMetricsFor = ['Follower', 'Photo', 'Viewpoint']

# The maximum throttling allowed as a fraction of the throughput capacity. 0.75 means that we can be limited down
# by at most 75% of the capacity (eg: we'll be allowed to use 1/4).
# TODO(marc): this should really take the number of backends into account.
kMaxCapacityThrottleFraction = 0.75

# What fraction of the throughput capacity do we lose every time we receive a throttle from dynamodb.
# eg: 0.05 means that we'll lose 5% of our capacity every time.
kPerThrottleLostCapacityFraction = 0.1

# Minimum amount of time between rate adjustments, in seconds.
kMinRateAdjustmentPeriod = 1.0


DynDBRequest = namedtuple('DynDBRequest', ['method', 'request', 'op', 'execute_cb', 'finish_cb'])

_requests_queued = counters.define_total('viewfinder.dynamodb.requests_queued',
                                         'Number of DynamoDB requests currently queued.')
# TODO: we should have this per table. A global counter is mostly meaningless.
_throttles_per_min = counters.define_rate('viewfinder.dynamodb.throttles_per_min',
                                          'Number of throttling errors received from DynamoDB per minute.', 60)
# In addition to these counters, each RequestQueue may setup an extra two (one for QPS, one for backoff).


class RequestQueue(object):
  """Manages the complexity of tracking successes and failures and
  estimating backoff delays for a request queue.
  """

  def __init__(self, table_name, read_write, name, ups):
    """'ups' is measured either as read or write capacity units per second.
    """
    self._name = name
    self._ups = ups
    self._queue = []
    self._last_rate_adjust = time.time()
    self._unavailable_rate = 0.0
    self._need_adj = False

    qps_counter = backoff_counter = None
    if table_name in kSaveMetricsFor:
      rw_str = 'write' if read_write else 'read'
      qps_counter = counters.define_rate('viewfinder.dynamodb.qps.%s_%s' % (table_name, rw_str),
                                         'Dynamodb %s QPS on %s' % (rw_str, table_name), 1)
      backoff_counter = counters.define_rate('viewfinder.dynamodb.backoff_per_sec.%s_%s' % (table_name, rw_str),
                                             'Dynamodb %s backoff seconds per second on %s' % (rw_str, table_name), 1)
    self._ups_rate = rate_limiter.RateLimiter(ups, qps_counter=qps_counter, backoff_counter=backoff_counter)

    self._timeout = None

  def Push(self, req):
    """Adds 'req', a DynDBRequest tuple, to the priority queue.
    """
    _requests_queued.increment()
    heapq.heappush(self._queue, (self._ComputePriority(req), req))

  def Pop(self):
    """Pops the highest priority request from the queue and returns it."""
    self._ups_rate.Add(1.0)
    _requests_queued.decrement()
    return heapq.heappop(self._queue)[1]

  def IsEmpty(self):
    """Returns True if the queue is empty, False otherwise."""
    return len(self._queue) == 0

  def Report(self, success, units=1):
    """'success' specifies whether or not the request failed due to a
    provisioned throughput exceeded error. On success, we adjust
    self._ups_stat if units != 1, as in the case of an eventually
    consistent read (units=0.5), or an operation requiring more than
    1 unit.

    On failure, set the _need_adj flag.
    """
    if success and units != 1.0:
      logging.debug('reported %.2f units for queue %s' % (units, self._name))
      self._ups_rate.Add(units - 1.0)

    if not success:
      _throttles_per_min.increment()
      self._need_adj = True

  def RecomputeRate(self):
    """Adjust the unavailable qps if needed and it's been long enough since the last adjustment.
    Increase or decrease based on the _need_adj flag and current min/max.
    """
    now = time.time()
    if (now - self._last_rate_adjust) >= kMinRateAdjustmentPeriod:
      new_adj = None
      # It's been long enough, we can adjust the rate if needed.
      if self._need_adj and self._unavailable_rate < (self._ups * kMaxCapacityThrottleFraction):
        new_adj = self._ups * kPerThrottleLostCapacityFraction
      elif not self._need_adj and self._unavailable_rate > 0.0:
        new_adj = -self._ups * kPerThrottleLostCapacityFraction
      # Clear need_adj regardless of whether we can change the rate or not. Otherwise, it will never be cleared
      # when we hit the max value for 'unavailable qps'.
      self._need_adj = False

      if new_adj is not None:
        self._last_rate_adjust = now
        self._unavailable_rate += new_adj
        self._ups_rate.SetUnavailableQPS(self._unavailable_rate)

  def GetBackoffSecs(self):
    """Ask the rate limiter for the number of seconds to sleep. We must sleep this long.
    We do not call RecomputeRate here since NeedsBackoff just did it.
    """
    return self._ups_rate.ComputeBackoffSecs()

  def NeedsBackoff(self):
    """Returns whether or not this queue needs to backoff. This calls a method on the rate limiter that does not
    increment the backoff counter.
    We first recompute the unavailable rate and adjust it if needed.
    """
    self.RecomputeRate()
    return self._ups_rate.NeedsBackoff()

  def ResetTimeout(self, callback):
    """Clears any existing timeout registered on the ioloop for this
    queue. If there is a current backoff and the queue is not empty,
    sets a new timeout based on backoff.
    """
    def _OnTimeout():
      self._timeout = None
      callback()

    if not self.IsEmpty() and self._timeout is None:
      backoff_secs = self.GetBackoffSecs()
      self._timeout = ioloop.IOLoop.current().add_timeout(time.time() + backoff_secs, _OnTimeout)
    elif self.IsEmpty():
      if self._timeout:
        ioloop.IOLoop.current().remove_timeout(self._timeout)
      self._timeout = None

  def _ComputePriority(self, req):
    """Computes the priority of 'req'. First cut of this algorithm is
    to simply order by the time the request was (re)added to the queue.
    """
    return time.time()


class RequestScheduler(object):
  """Prioritizes and schedules competing requests to the DynamoDB
  backend. Requests are organized by tables. Each table has its own
  provisioning for read and writes per second. Depending on failures
  indicating that provisioned throughput is being exceeded, requests
  are placed into priority queues and throttled to just under the
  maximum sustainable rate.
  """
  _READ_ONLY_METHODS = ('ListTables', 'DescribeTable', 'GetItem', 'Query', 'Scan', 'BatchGetItem')

  def __init__(self, schema):
    self._read_queues = dict([(t.name_in_db, RequestQueue(t.name, False, '%s reads' % (t.name), t.read_units)) \
                                for t in schema.GetTables()])
    self._write_queues = dict([(t.name_in_db, RequestQueue(t.name, True, '%s writes' % (t.name), t.write_units)) \
                                 for t in schema.GetTables()])
    self._cp_read_only_queue = RequestQueue('ControlPlane', False, 'Control Plane R/O', 100)
    self._cp_mutate_queue = RequestQueue('ControlPlane', True, 'Control Plane Mutate', 1)
    self._paused = False
    self._asyncdynamo = AsyncDynamoDB(secrets.GetSecret('aws_access_key_id'),
                                      secrets.GetSecret('aws_secret_access_key'))

  def Schedule(self, method, request, callback):
    """Creates a DynamoDB request to API call 'method' with JSON
    encoded arguments 'request'. Invokes 'callback' with JSON decoded
    response as an argument.
    """
    if method in ('ListTables', 'DescribeTable'):
      queue = self._cp_read_only_queue
    elif method in ('CreateTable', 'DeleteTable'):
      queue = self._cp_mutate_queue
    elif method in ('GetItem', 'Query', 'Scan'):
      queue = self._read_queues[request['TableName']]
    elif method in ('BatchGetItem',):
      table_names = request['RequestItems'].keys()
      assert len(table_names) == 1, table_names
      queue = self._read_queues[table_names[0]]
    else:
      assert method in ('DeleteItem', 'PutItem', 'UpdateItem'), method
      queue = self._write_queues[request['TableName']]

    # The execution callback that we initialize the dynamodb request with is wrapped
    # so that on execution, errors will be handled in the context of this method's caller.
    dyn_req = DynDBRequest(method=method, request=request, op=None, finish_cb=callback,
                           execute_cb=stack_context.wrap(partial(self._ExecuteRequest, queue)))
    queue.Push(dyn_req)
    self._ProcessQueue(queue)

  def _ExecuteRequest(self, queue, dyn_req):
    """Helper function to execute a DynamoDB request within the context
    in which is was scheduled. This way, if an unrecoverable exception is
    thrown during execution, it can be re-raised to the appropriate caller.
    """
    def _OnResponse(start_time, json_response):
      if dyn_req.method in ('BatchGetItem',):
        consumed_units = next(json_response.get('Responses').itervalues()).get('ConsumedCapacityUnits', 1)
      else:
        consumed_units = json_response.get('ConsumedCapacityUnits', 1)

      logging.debug('%s response: %d bytes, %d units, %.3fs elapsed' %
                    (dyn_req.method, len(json_response), consumed_units,
                     time.time() - start_time))
      queue.Report(True, consumed_units)
      dyn_req.finish_cb(json_response)

    def _OnException(type, value, tb):
      if type in (DBProvisioningExceededError, DBLimitExceededError):
        # Retry on DynamoDB throttling errors. Report the failure to the queue so that it will backoff the
        # requests/sec rate.
        queue.Report(False)
      elif type == DynamoDBResponseError and value.status in [500, 599] and \
           dyn_req.method in RequestScheduler._READ_ONLY_METHODS:
        # DynamoDB returns 500 when the service is unavailable for some reason.
        # Curl returns 599 when something goes wrong with the connection, such as a timeout or connection reset.
        # Only retry if this is a read-only request, since otherwise an update may be applied twice.
        pass
      else:
        # Re-raise the exception now that we're in the stack context of original caller.
        logging.warning('error calling "%s" with this request: %s' % (dyn_req.method, dyn_req.request))
        raise type, value, tb

      if dyn_req.method in ('BatchGetItem',):
        table_name = next(dyn_req.request['RequestItems'].iterkeys())
      else:
        table_name = dyn_req.request.get('TableName', None)
      logging.warning('%s against %s table failed: %s' % (dyn_req.method, table_name, value))
      queue.Push(dyn_req)
      self._ProcessQueue(queue)

    logging.debug('sending %s (%d bytes) dynamodb request' % (dyn_req.method, len(dyn_req.request)))
    with util.MonoBarrier(partial(_OnResponse, time.time()), on_exception=partial(_OnException)) as b:
      self._asyncdynamo.make_request(dyn_req.method, json.dumps(dyn_req.request), b.Callback())

  def _ProcessQueue(self, queue):
    """If the queue is not empty and adequate provisioning is expected,
    sends the highest priority queue item(s) to DynamoDB.

    When all items have been sent, resets the queue processing timeout.
    """
    if self._paused:
      return

    while not queue.IsEmpty() and not queue.NeedsBackoff():
      dyn_req = queue.Pop()
      dyn_req.execute_cb(dyn_req)

    queue.ResetTimeout(partial(self._ProcessQueue, queue))

  def _Pause(self):
    """Pauses all queue processing. No requests will be sent until
    _Resume() is invoked.
    NOTE: intended for testing.
    """
    self._paused = True

  def _Resume(self):
    """Resume the scheduler if paused."""
    if self._paused:
      self._paused = False
      [self._ProcessQueue(q) for q in self._read_queues.values()]
      [self._ProcessQueue(q) for q in self._write_queues.values()]
      [self._ProcessQueue(q) for q in (self._cp_read_only_queue, self._cp_mutate_queue)]


class DynamoDBClient(DBClient):
  """Asynchronous access to DynamoDB datastore.
  """
  _MAX_BATCH_SIZE = 100
  """Maximum number of key rows that can be specified in a DynamoDB batch."""

  def __init__(self, schema, read_only=False):
    """Uses single ConnectionManager instance of connection_manager is None.
    """
    self._schema = schema
    self._read_only = read_only
    self._scheduler = RequestScheduler(schema)

  def Shutdown(self):
    pass

  def ListTables(self, callback):
    def _OnList(response):
      # Map to application table names, which may be different than names in database.
      table_names = [self._schema.TranslateNameInDb(name_in_db)
                     for name_in_db in response['TableNames']]
      callback(ListTablesResult(tables=table_names))

    self._scheduler.Schedule('ListTables', {}, _OnList)

  def CreateTable(self, table, hash_key_schema, range_key_schema,
                  read_units, write_units, callback):
    assert not self._read_only, 'Received "CreateTable" request on read-only database'

    def _OnCreate(response):
      callback(CreateTableResult(self._GetTableSchema(table, response['TableDescription'])))

    request = {
      'TableName': table,
      'KeySchema': {
        'HashKeyElement': {'AttributeName': hash_key_schema.name,
                           'AttributeType': hash_key_schema.value_type},
        },
      'ProvisionedThroughput': {'ReadCapacityUnits': read_units,
                                'WriteCapacityUnits': write_units},
      }
    if range_key_schema:
      request['KeySchema']['RangeKeyElement'] = {
        'AttributeName': range_key_schema.name,
        'AttributeType': range_key_schema.value_type,
        }
    self._scheduler.Schedule('CreateTable', request, _OnCreate)

  def DeleteTable(self, table, callback):
    assert not self._read_only, 'Received "DeleteTable" request on read-only database'

    table_def = self._schema.GetTable(table)

    def _OnDelete(response):
      callback(DeleteTableResult(self._GetTableSchema(table_def.name_in_db, response['TableDescription'])))

    self._scheduler.Schedule('DeleteTable', {'TableName': table_def.name_in_db}, _OnDelete)

  def DescribeTable(self, table, callback):
    table_def = self._schema.GetTable(table)

    def _OnDescribe(response):
      desc = response['Table']
      schema = self._GetTableSchema(table_def.name_in_db, desc)
      callback(DescribeTableResult(schema=schema,
                                   count=desc.get('ItemCount', 0),
                                   size_bytes=desc.get('TableSizeBytes', 0)))

    self._scheduler.Schedule('DescribeTable', {'TableName': table_def.name_in_db}, _OnDescribe)

  def GetItem(self, table, key, callback, attributes, must_exist=True,
              consistent_read=False):
    table_def = self._schema.GetTable(table)

    def _OnGetItem(response):
      if must_exist:
        assert 'Item' in response, 'key %r does not exist in %s' % (key, table_def.name)
      if 'Item' not in response:
        callback(None)
      else:
        callback(GetResult(attributes=self._FromDynamoAttributes(table_def, response['Item']),
                           read_units=response['ConsumedCapacityUnits']))

    request = self._GetBaseRequest(table_def, key)
    request.update({'AttributesToGet': attributes,
                    'ConsistentRead': consistent_read})
    self._scheduler.Schedule('GetItem', request, _OnGetItem)

  @gen.engine
  def BatchGetItem(self, batch_dict, callback, must_exist=True):
    """See the header for DBClient.BatchGetItem for details. Note that currently items can
    only be requested from a single table at a time (though the interface supports multiple
    tables).
    """
    assert len(batch_dict) == 1, 'BatchGetItem currently supports only a single table'

    # Create dict of all unique keys to get.
    table_name, (keys, attributes, consistent_read) = next(batch_dict.iteritems())
    table_def = self._schema.GetTable(table_name)
    key_result_dict = {key: None for key in keys}
    read_units = 0.0

    # Loop until all keys have been fetched, at most 100 at a time.
    while True:
      item_count = 0
      dyn_keys = []
      for key, result in key_result_dict.iteritems():
        if result is None:
          # By default, assume that key does not exist (will just not be returned by DynamoDB).
          key_result_dict[key] = {}
          dyn_keys.append(self._ToDynamoKey(table_def, key))
          item_count += 1

        if item_count >= DynamoDBClient._MAX_BATCH_SIZE:
          break

      # If no items to fetch, then done.
      if item_count == 0:
        break

      # Create the request dict.
      request = {'RequestItems': {table_def.name_in_db: {'Keys': dyn_keys,
                                                         'AttributesToGet': attributes,
                                                         'ConsistentRead': consistent_read}}}

      # Send request to DynamoDB.
      response = yield gen.Task(self._scheduler.Schedule, 'BatchGetItem', request)

      # Re-send any unprocessed keys by setting their results back to None.
      if response['UnprocessedKeys']:
        for dyn_key in response['UnprocessedKeys'][table_def.name_in_db]['Keys']:
          key = self._FromDynamoKey(table_def, dyn_key)
          key_result_dict[key] = None

      # Save any response attributes from items that were found by key.
      for dyn_attrs in response['Responses'][table_def.name_in_db]['Items']:
        dyn_key = {'HashKeyElement': dyn_attrs[table_def.hash_key_col.key]}
        if table_def.range_key_col is not None:
          dyn_key['RangeKeyElement'] = dyn_attrs[table_def.range_key_col.key]

        key = self._FromDynamoKey(table_def, dyn_key)
        key_result_dict[key] = self._FromDynamoAttributes(table_def, dyn_attrs)

      read_units += response['Responses'][table_def.name_in_db]['ConsumedCapacityUnits']

    # Return one item in result for each key in batch_dict.
    result_items = []
    for key in next(batch_dict.itervalues()).keys:
      attributes = key_result_dict[key] or None
      if must_exist:
        assert attributes is not None, 'key %r does not exist in %s' % (key, table_def.name)
      result_items.append(attributes)

    callback({table_name: BatchGetResult(items=result_items, read_units=read_units)})

  def PutItem(self, table, key, callback, attributes, expected=None,
              return_values=None):
    assert not self._read_only, 'Received "PutItem" request on read-only database'

    table_def = self._schema.GetTable(table)

    def _OnPutItem(response):
      callback(PutResult(return_values=self._FromDynamoAttributes(table_def, response.get('Attributes', None)),
                         write_units=response['ConsumedCapacityUnits']))

    # Add key values to the attributes map, in accordance with DynamoDB requirements.
    attributes[table_def.hash_key_col.key] = key.hash_key
    if table_def.range_key_col:
      attributes[table_def.range_key_col.key] = key.range_key
    request = {'TableName': table_def.name_in_db,
               'Item': self._ToDynamoAttributes(table_def, attributes)}
    if expected is not None:
      request['Expected'] = self._ToDynamoExpected(table_def, expected)
    if return_values is not None:
      request['ReturnValues'] = return_values
    self._scheduler.Schedule('PutItem', request, _OnPutItem)

  def DeleteItem(self, table, key, callback, expected=None, return_values=None):
    assert not self._read_only, 'Received "DeleteItem" request on read-only database'

    table_def = self._schema.GetTable(table)

    def _OnDeleteItem(response):
      callback(DeleteResult(return_values=self._FromDynamoAttributes(table_def, response.get('Attributes', None)),
                            write_units=response['ConsumedCapacityUnits']))

    request = self._GetBaseRequest(table_def, key)
    if expected is not None:
      request['Expected'] = self._ToDynamoExpected(table_def, expected)
    if return_values is not None:
      request['ReturnValues'] = return_values
    self._scheduler.Schedule('DeleteItem', request, _OnDeleteItem)

  def UpdateItem(self, table, key, callback, attributes, expected=None,
                 return_values=None):
    assert not self._read_only, 'Received "UpdateItem" request on read-only database'

    table_def = self._schema.GetTable(table)

    def _OnUpdateItem(response):
      callback(UpdateResult(return_values=self._FromDynamoAttributes(table_def, response.get('Attributes', None)),
                            write_units=response['ConsumedCapacityUnits']))

    request = self._GetBaseRequest(table_def, key)
    request['AttributeUpdates'] = self._ToDynamoAttributeUpdates(table_def, attributes)
    if expected is not None:
      request['Expected'] = self._ToDynamoExpected(table_def, expected)
    if return_values is not None:
      request['ReturnValues'] = return_values
    self._scheduler.Schedule('UpdateItem', request, _OnUpdateItem)

  def Query(self, table, hash_key, range_operator, callback, attributes,
            limit=None, consistent_read=False, count=False,
            scan_forward=True, excl_start_key=None):
    table_def = self._schema.GetTable(table)

    def _OnQuery(response):
      callback(QueryResult(count=response['Count'],
                           items=[self._FromDynamoAttributes(table_def, item) for item in response.get('Items', [])],
                           last_key=self._FromDynamoKey(table_def, response.get('LastEvaluatedKey', None)),
                           read_units=response['ConsumedCapacityUnits']))

    request = {'TableName': table_def.name_in_db}
    request['HashKeyValue'] = self._ToDynamoValue(table_def.hash_key_col, hash_key)
    if range_operator is not None:
      request['RangeKeyCondition'] = {
        'AttributeValueList': [self._ToDynamoValue(table_def.range_key_col, rv) \
                               for rv in range_operator.key],
        'ComparisonOperator': range_operator.op}
    if attributes is not None:
      request['AttributesToGet'] = attributes
    if limit is not None:
      request['Limit'] = limit
    request['ConsistentRead'] = consistent_read
    request['Count'] = count
    request['ScanIndexForward'] = scan_forward
    if excl_start_key is not None:
      request['ExclusiveStartKey'] = self._ToDynamoKey(table_def, excl_start_key)

    self._scheduler.Schedule('Query', request, _OnQuery)

  def Scan(self, table, callback, attributes, limit=None,
           excl_start_key=None, scan_filter=None):
    table_def = self._schema.GetTable(table)

    def _OnScan(response):
      callback(ScanResult(count=response['Count'],
                          items=[self._FromDynamoAttributes(table_def, item) for item in response['Items']],
                          last_key=self._FromDynamoKey(table_def, response.get('LastEvaluatedKey', None)),
                          read_units=response['ConsumedCapacityUnits']))

    request = {'TableName': table_def.name_in_db}
    if attributes is not None:
      request['AttributesToGet'] = attributes
    if limit is not None:
      request['Limit'] = limit
    #request['Count'] = count
    if scan_filter is not None:
      request['ScanFilter'] = dict()
      for k, sf in scan_filter.items():
        col_def = table_def.GetColumnByKey(k)
        request['ScanFilter'][k] = {
          'AttributeValueList': [self._ToDynamoValue(col_def, v) for v in sf.value],
          'ComparisonOperator': sf.op}
    if excl_start_key is not None:
      request['ExclusiveStartKey'] = self._ToDynamoKey(table_def, excl_start_key)

    self._scheduler.Schedule('Scan', request, _OnScan)

  def AddTimeout(self, deadline_secs, callback):
    """Invokes the specified callback after 'deadline_secs'."""
    return ioloop.IOLoop.current().add_timeout(time.time() + deadline_secs, callback)

  def AddAbsoluteTimeout(self, abs_timeout, callback):
    """Invokes the specified callback at time 'abs_timeout'."""
    return ioloop.IOLoop.current().add_timeout(abs_timeout, callback)

  def RemoveTimeout(self, timeout):
    """Removes an existing timeout."""
    ioloop.IOLoopcurrent().remove_timeout(timeout)

  def _GetBaseRequest(self, table_def, key):
    """Creates the base request structure for accessing a DynamoDB table
    by key.
    """
    return {'TableName': table_def.name_in_db, 'Key': self._ToDynamoKey(table_def, key)}

  def _FromDynamoKey(self, table_def, dyn_key):
    """Converts a DynamoDB key into a DBKey named tuple, using the value
    types defined in the table key definition.
    """
    if dyn_key is None:
      return None
    value_type, value = dyn_key['HashKeyElement'].items()[0]
    hash_key = self._FromDynamoValue(table_def.hash_key_col, value_type, value)
    if table_def.range_key_col:
      value_type, value = dyn_key['RangeKeyElement'].items()[0]
      range_key = self._FromDynamoValue(table_def.range_key_col, value_type, value)
    else:
      range_key = None
    return DBKey(hash_key, range_key)

  def _ToDynamoKey(self, table_def, key):
    """Converts from a DBKey named tuple into a DynamoDB key."""
    dyn_key = {'HashKeyElement': self._ToDynamoValue(table_def.hash_key_col, key.hash_key)}
    if key.range_key is not None:
      assert table_def.range_key_col
      dyn_key['RangeKeyElement'] = self._ToDynamoValue(table_def.range_key_col, key.range_key)
    return dyn_key

  def _FromDynamoAttributes(self, table_def, dyn_attrs):
    """Converts attributes as reported by DynamoDB into a dictionary
    of key/value pairs. This verifies at each step that the value
    types are in agreement, and converts from a list to a set for value
    types 'SS' and 'NS'.
    """
    if dyn_attrs is None:
      return None
    attrs = dict()
    for k, v in dyn_attrs.items():
      value_type, value = v.items()[0]
      attrs[k] = self._FromDynamoValue(table_def.GetColumnByKey(k), value_type, value)
    return attrs

  def _ToDynamoAttributes(self, table_def, attrs):
    """Converts attributes from schema datamodel to a dictionary
    appropriate for use with DynamoDB JSON request protocol.
    """
    dyn_attrs = dict()
    for k, v in attrs.items():
      dyn_attrs[k] = self._ToDynamoValue(table_def.GetColumnByKey(k), v)
    return dyn_attrs

  def _ToDynamoAttributeUpdates(self, table_def, updates):
    """Converts attribute updates from schema datamodel to a
    dictionary appropriate for use with DynamoDB JSON request
    protocol.
    """
    dyn_updates = dict()
    for k, v in updates.items():
      dyn_updates[k] = {'Action': v.action}
      if v.value is not None:
        dyn_updates[k]['Value'] = self._ToDynamoValue(table_def.GetColumnByKey(k), v.value)
    return dyn_updates

  def _ToDynamoExpected(self, table_def, expected):
    """Converts expected values from schema datamodel to a dictionary
    appropriate for use with DynamoDB JSON request protocol. If the
    value of an expected key is a boolean, it must be False, and is
    meant to specify that the attribute must not exist.
    """
    dyn_exp = dict()
    for k, v in expected.items():
      if isinstance(v, bool):
        assert not v, 'if specifying a bool for an expected value, must be False'
        dyn_exp[k] = {'Exists': False}
      else:
        dyn_exp[k] = {'Value': self._ToDynamoValue(table_def.GetColumnByKey(k), v)}
    return dyn_exp

  def _FromDynamoValue(self, col_def, dyn_type, dyn_value):
    """Converts a dynamo value to a python data structure for use with
    viewfinder schema.
    """
    assert col_def.value_type == dyn_type, '%s != %s' % (col_def.value_type, dyn_type)
    if col_def.value_type == 'N':
      return ConvertToNumber(dyn_value)
    elif col_def.value_type == 'NS':
      return set([ConvertToNumber(dv) for dv in dyn_value])
    elif col_def.value_type == 'SS':
      return set([dv for dv in dyn_value])
    else:
      return dyn_value

  def _ToDynamoValue(self, col_def, v):
    """Converts a value to a representation appropriate for passing as a
    JSON-encoded value to DynamoDB.
    """
    if col_def.value_type == 'N':
      return {col_def.value_type: ConvertToString(v)}
    elif col_def.value_type == 'NS':
      return {col_def.value_type: [ConvertToString(v_el) for v_el in v]}
    elif col_def.value_type == 'SS':
      return {col_def.value_type: [v_el for v_el in v]}
    else:
      assert col_def.value_type == 'S', col_def.value_type
      return {col_def.value_type: v}

  def _GetTableSchema(self, name_in_db, desc):
    """Builds a table schema namedtuple from a create or delete table request.
    """
    assert desc['TableName'] == name_in_db, '%s != %s' % (desc['TableName'], name_in_db)

    def _GetDBKeySchema(key):
      if 'KeySchema' in desc and key in desc['KeySchema']:
        return DBKeySchema(name=desc['KeySchema'][key]['AttributeName'],
                           value_type=desc['KeySchema'][key]['AttributeType'])
      else:
        return None

    return TableSchema(create_time=desc.get('CreationDateTime', 0),
                       hash_key_schema=_GetDBKeySchema('HashKeyElement'),
                       range_key_schema=_GetDBKeySchema('RangeKeyElement'),
                       read_units=desc['ProvisionedThroughput']['ReadCapacityUnits'],
                       write_units=desc['ProvisionedThroughput']['WriteCapacityUnits'],
                       status=desc['TableStatus'])
