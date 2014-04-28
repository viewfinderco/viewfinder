# Copyright 2012 Viewfinder Inc. All Rights Reserved.

"""JSON Schemas for administrative request/responses.
"""

__authors__ = ['spencer@emailscrubbed.com (Spencer Kimball)']


# Authenticate an administrator by username/password/OTP combo.
#
# /admin/otp

AUTHENTICATE_REQUEST = {
  'description': 'returns an admin cookie granting administrative '
  'privileges for use with /admin URLs.',
  'type': 'object',
  'properties': {
    'username': {'type': 'string'},
    'password': {'type': 'string'},
    'otp': {'type': 'number'}
    },
  }

AUTHENTICATE_RESPONSE = {
  'description': 'empty; cookie is returned as part of HTTP response',
  'type': 'object',
  'properties': {
    },
  }


# List client logs matching the specified user_id, date range,
#  and log file filter regular expression.
#
# /admin/service/list_client_logs

LIST_CLIENT_LOGS_REQUEST = {
  'description': 'fetch a list of S3 GET URLs for client logs matching '
  'specified user id, date range, and optional client log id filter regexp. '
  'logs are fetched only with full-day granularity and include the start of '
  'day for specified start time and end of day for specified end time.',
  'type': 'object',
  'properties': {
    'user_id': {'type': 'number'},
    'start_timestamp': {'type': 'number'},
    'end_timestamp': {'type': 'number'},
    'filter': {'type': 'string', 'required': False},
    },
  }

LIST_CLIENT_LOGS_RESPONSE = {
  'type': 'object',
  'properties': {
    'log_urls': {
      'description': 'array of (filename, url) for each matching log; '
      'URLs expire in 24 hours',
      'type': 'array',
      'items': {
        'type': 'object',
        'properties': {
          'filename': {'type': 'string'},
          'url': {'type': 'string'},
          },
        },
      },
    },
  }

