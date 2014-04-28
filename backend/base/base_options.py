#!/usr/bin/env python
#
# Copyright 2012 Viewfinder Inc. All Rights reserved.
"""Command-line options used by base or higher layers.

These options are considered base in that they may be imported by any layer
at or above the base layer.
"""

import os
import viewfinder
from tornado import options

options.define('secrets_dir', os.path.join(viewfinder.__path__[0], 'secrets'),
               help='directory containing secrets files')

options.define('user_secrets_dir', os.path.join(os.path.expanduser('~/.secrets')),
               help='directory containing secrets files for the running user')

options.define('passphrase', None, help='the passphrase for decoding secrets')

options.define('passphrase_file', None, help='file containing the passphrase')

options.define('domain',
               default='viewfinder.co',
               help='service domain (for redirects, keys, etc.)')

options.define('www_label',
               default='www',
               help='The label to use for the prod_host domain (for redirects, etc.)')

options.define('short_domain',
               default='vfnd.co',
               help='domain used in some short URLs for SMS, etc.')

options.define('devbox',
               default=False,
               help='start in dev/desktop mode outside of EC2')

options.define('is_staging',
               type=bool,
               default=None,
               help='start in staging mode outside of EC2')

options.define('vf_temp_dir', default=None,
               help='directory for viewfinder temp files if running as devbox')
