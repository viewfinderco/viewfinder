#!/usr/bin/env python
#
# Copyright 2011 Viewfinder Inc. All Rights Reserved.

"""Template for deployment descriptor. Copy this file and name it
so that it corresponds to one AWS AMI instance. That is, its name
should reflect the server mix / function of the deployed instance.

NOTE: All paths must be relative to the root source directory, not
to the deployment directory.
"""

__author__ = 'spencer@emailscrubbed.com (Spencer Kimball)'

# List server specifications. Each specification details:
servers = [
  {
    # Server type: used as a prefix when creating a CNAME in AWS
    # Route 53, Amazon's cloud DNS service. The suffix of the
    # CNAME record specifies the AMI instance. One CNAME record
    # pointing to the IP address of the AMI instance is created
    # for each server specification running in the instance. If
    # more than one instance of a specific type of server is
    # running (see list of process specifications below), there is
    # still only a single CNAME record for that server type.
    "type": "default",

    # Path to server executable: a python script (typically
    # starting a tornado http server). Any '.py' files in the same
    # directory are automatically included with the exception of
    # files ending in '_test.py'.
    #
    # Paths must be specified relative to root of the source
    # directory. For example, if deployment templates are in
    # backend/deploy/, and server binaries are in
    # backend/viewfinder/, then paths here should be specified as
    # backend/viewfinder/<file>.
    "path": "",

    # A list of process specifications. Each item in the list is a
    # list of command line flags, with one such list per server
    # process that is to be started on each AMI instance.
    # e.g.: [ [ "--port=8080" ], [ "--port=8081" ] ] would start
    # two instances of this server type, one with port 8080 and the
    # other with port 8081.
    "proceses": [],

    # Number of instances of the server to run globally. The
    # babysitter allows only a fixed number of instances to host
    # this server type.  This is used, for example, to run just a
    # single 'console' server, for example. 0 to create a process
    # in each instance.
    "num_processes": 0,
    },
  ]

# Script for deployment startup which is run when a new Amazon AMI
# (Amazon Machine Instance) is created for the deployment. This is a
# shell script which sets up the production environment; for example,
# running easy_install to download and install tornado, greenlets, and
# boto, compiling C++ libraries, etc.
setup_script = """
# Commands for setup here
"""
