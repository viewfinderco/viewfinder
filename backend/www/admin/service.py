# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""Handler for administrative service RPCs.

  - AdminServiceHandler
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)']

import json
import logging
import time
import validictory

from functools import partial
from viewfinder.backend.base import handler, util
from viewfinder.backend.db.client_log import ClientLog
from viewfinder.backend.www import basic_auth, json_schema, www_util
from viewfinder.backend.www.admin import admin_schema


def ListClientLogs(client, obj_store, auth_credentials, request, callback):
  """Returns a list of client logs matching the specified client user
  id and start/end timestamps date range.
  """
  def _OnListClientLogs(log_urls):
    logging.info('LIST CLIENT LOGS: admin: %s, client user_id: %d, '
                 'start: %s, end: %s, filter: %s, num_logs: %d' %
                 (auth_credentials, request['user_id'],
                  ClientLog._IsoDate(request['start_timestamp']),
                  ClientLog._IsoDate(request['end_timestamp']),
                  request.get('filter', None), len(log_urls)))
    response = {'log_urls': log_urls}
    callback(response)

  ClientLog.ListClientLogs(request['user_id'], request['start_timestamp'],
                           request['end_timestamp'], request.get('filter', None),
                           _OnListClientLogs)


class AdminServiceHandler(basic_auth.BasicAuthHandler):
  """The RPC multiplexer for admin request/responses.
  """
  class Method(object):
    """An entry in the service map. When a service request is received,
    it is validated according to the "request" schema. The response is
    validated according to the "response" schema.
    """
    def __init__(self, request, response, handler):
      self.request = request
      self.response = response
      self.handler = handler

  # Map from service name to Method instance.
  SERVICE_MAP = {
    'list_client_logs': Method(request=admin_schema.LIST_CLIENT_LOGS_REQUEST,
                               response=admin_schema.LIST_CLIENT_LOGS_RESPONSE,
                               handler=ListClientLogs),
    }

  def __init__(self, application, request, **kwargs):
    super(AdminServiceHandler, self).__init__(application, request, **kwargs)

  @handler.authenticated()
  @handler.asynchronous(datastore=True, obj_store=True)
  # TODO(marc): use AdminHandler for service and require permissions
  def post(self, method_name):
    """Parses the JSON request body, validates it, and invokes the
    method as specified in the request URI. On completion, the
    response is returned as a JSON-encoded HTTP response body.
    """
    def _OnSuccess(method, start_time, response_dict):
      validictory.validate(response_dict, method.response)
      self.set_status(200)
      self.set_header('Content-Type', 'application/json; charset=UTF-8')
      self.write(response_dict)  # tornado automatically serializes json

      request_time = time.time() - start_time
      logging.debug('serviced %s request in %.4fs: %s' %
                    (method_name, request_time, response_dict))
      self.finish()

    def _OnException(type, value, tb):
      status, message = www_util.HTTPInfoFromException(value)
      self.set_status(status)
      if status == 500:
        logging.error('failure processing %s:\n%s' % (method_name, self.request.body),
                      exc_info=(type, value, tb))

      error_dict = {'error': {'method': method_name,
                              'message': '%s %s' % (type, value)}}
      validictory.validate(error_dict, json_schema.ERROR_RESPONSE)
      self.set_header('Content-Type', 'application/json; charset=UTF-8')
      self.write(error_dict)
      self.finish()

    start_time = time.time()

    # Check service method; (501: Not Implemented).
    if not AdminServiceHandler.SERVICE_MAP.has_key(method_name):
      self.send_error(status_code=501)
      return

    # Verify application/json; (415: Unsupported Media Type).
    # TODO(ben): Refactor BaseHandler so we can use _LoadJSONRequest here.
    content_type = self.request.headers['Content-Type']
    if not content_type.startswith('application/json'):
      self.send_error(status_code=415)
      return

    method = AdminServiceHandler.SERVICE_MAP[method_name]
    with util.MonoBarrier(partial(_OnSuccess, method, start_time),
                          on_exception=_OnException) as b:
      request_dict = json.loads(self.request.body)
      validictory.validate(request_dict, method.request)
      method.handler(self._client, self._obj_store, self.get_current_user(),
                     request_dict, b.Callback())
