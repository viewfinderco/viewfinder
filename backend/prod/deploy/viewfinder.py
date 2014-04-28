#!/usr/bin/env python
#
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Deployment descriptor for the Viewfinder web server.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

# List server specifications. Each specification details:
servers = [
  { "type": "www",
    "path": "backend/viewfinder/viewfinder.py",
    "processes": [["--port=80"], ],
    "num_processes": 0,
    },
]

setup_script = """
"""
