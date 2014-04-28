# Copyright 2013 Viewfinder Inc. All Rights Reserved
"""Interface with GCM (Google Cloud Messaging).

For now, a simple cmdline-only tool, to be fleshed out into a proper class later.

To issue a message to a device:
python -m viewfinder.backend.services.gcm_utils --id="ABC...123" --data_value="my message here"
"""

import sys

from gcm import GCM
from tornado import gen, options
from viewfinder.backend.base import main, secrets

API_KEY_NAME='gcm_api_key'

options.define('id', default=None, help='Device GCM id (look at your android app logs)')
options.define('data_key', default='message', help='Key this particular bit of data')
options.define('data_value', default=None, help='Value to store under data_key')

def _Start():
  assert options.options.id and options.options.data_key and options.options.data_value

  api_key = secrets.GetSecret(API_KEY_NAME)
  print 'API key: %s' % api_key
  g = GCM(api_key)
  data = {options.options.data_key: options.options.data_value}

  # Do not catch any of the exceptions for now, we'd like to see them.
  g.plaintext_request(registration_id=options.options.id, data=data)

if __name__ == '__main__':
  options.options.domain = 'goviewfinder.com'
  options.options.devbox = True
  options.parse_command_line()

  secrets.InitSecrets(shared_only=True, callback=_Start);
