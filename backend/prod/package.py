#!/usr/bin/env python
#
# Copyright (C) 2011 Viewfinder Inc.
#

"""Bundle up a collection of python servers for deployment to the
Amazon Web Services cloud on a single AMI instance. Creates a
self-extracting Python deployment file for use with AWS.

Every deployment starts with a deployment template, which is based on
template.py. This file should be copied and modified as appropriate
for the server in question. The deployment template file has comments
which describe each configurable aspect of an instance deployment
profile.

Invoke this script with the deployment template as the argument. The
output will be a file of the same basename with suffix: "_pkg.py" in
the same directory as the deployment template.

On execution, the new _pkg.py script will unpack the specified
python files and packages and run whatever setup script was specified
in the deployment template. The babysitter server is then run to start
the specified servers and monitor them.

The output executable is written to the current directory.
"""

import base64
import os
import os.path
import re
import stat
import string
import subprocess
import sys
import zlib


def _FileMatches(path, excl_regexps):
  """Returns true if the specified path matches none of the
  specified exclude regular expresions.
  """
  for r in excl_regexps:
    if re.match(r, path):
      return False
  return True


def _GetFilesRecursively(path, excl_regexps=[
    r"#.*",
    r"\..+",
    r".*~$",
    r".*\.pyc$",
    r".*_test.py$",
    r".*_pkg.py$"]):
  """Recursively walks the source directory and locates matching
  files. Returns a list of files.
  """
  entries = os.listdir(path)
  dirs = [e for e in entries if os.path.isdir(os.path.join(path, e))
          and _FileMatches(e, excl_regexps)]
  files = [os.path.join(path, e) for e in entries if
           os.path.isfile(os.path.join(path, e)) and _FileMatches(e, excl_regexps)]
  for d in dirs:
    files += _GetFilesRecursively(os.path.join(path, d), excl_regexps)
  return files


def _ReadFile(path):
  return open(path, 'rb').read()


def _Package(template, package_out, files):
  """Package up all files into a self-extracting python script
  suffixed by _pkg.py. This script has one potentially long data
  string, which is the encoded, gzipped contents of the deployment
  files. The files are a .tgz tarball and are un-archived into their
  original directory structure and permissions using subprocess to
  invoke tar.

  Once this is complete, the decode.py script is invoked.
  """
  # Roll a tgz tarball with files as arguments.
  p = subprocess.Popen([ "tar", "czfH", "-" ] + list(files),
                       bufsize=4096, stdout=subprocess.PIPE)
  (tarball, stderr) = p.communicate()

  out = open(package_out, "w")
  out.write("#!/usr/bin/env python\n")
  out.write("import subprocess, base64, zlib, os, stat, sys\n")
  out.write("tarball = base64.b64decode('")
  out.write(base64.b64encode(tarball))
  out.write("')\n")
  out.write("os.mkdir('viewfinder')\n")
  out.write("os.chdir('viewfinder')\n")
  out.write("p = subprocess.Popen([ \"tar\", \"xzf\", \"-\" ],\n")
  out.write("                     bufsize=4096, stdin=subprocess.PIPE)\n")
  out.write("p.communicate(input=tarball)\n")
  out.write("os.execv('./backend/prod/deploy.py', "
            "['./backend/prod/deploy.py', '{0}'])\n".format(template))

  out.close()
  os.chmod(package_out, stat.S_IRWXU)


def main():
  """Extract the deployment template from command line arguments,
  import it, gather the list files to package, and run the packer.
  """
  try:
    # Import the deploy template, as we must access its servers
    # list to search for python files to bundle for deployment.
    deploy_template = sys.argv[1]
    assert os.path.isfile(deploy_template), \
        "deployment template {0} is not a file".format(deploy_template)
    exec(open(deploy_template, 'rb'))

    deploy_name = os.path.splitext(os.path.basename(deploy_template))[0]
    package_out = os.path.join(os.path.dirname(deploy_template),
                               deploy_name + "_pkg.py")

    # Get the full list of deployed files
    files = _GetFilesRecursively("./")

    # Package the contents into a deployment executable.
    _Package(deploy_name, package_out, files)

    print "{0} deployment packaged into {1}".format(
      deploy_template, package_out)
    return 0

  except (IndexError, AssertionError), err:
    print("Error: {0}, Usage: {1} <deploy-template>".format(
        str(err), os.path.basename(sys.argv[0])))
    return -1


if __name__ == "__main__":
  sys.exit(main())
