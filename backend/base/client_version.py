# Copyright 2013 Viewfinder Inc. All Rights Reserved.

"""Client versioning handler.

Must be kept up to date with the versioning logic in the client:
//viewfinder/client/ios/Source/Utils.mm::AppVersion

TODO(marc): should we exclude 'adhoc' and 'dev' when comparing versions?
TODO(marc): handle android versioning once we have it.
"""

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

class ClientVersion(object):
  def __init__(self, version):
    self.version = version
    self.components = version.split('.') if version is not None else None

  def IsValid(self):
    if not self.version:
      return False
    if not self.components:
      return False
    # Require at least one dot in the name.
    if len(self.components) < 2:
      return False

    # TODO(marc): we may want additional logic here (eg: w.x.y.z).
    return True

  def IsDev(self):
    return self.version.endswith('.dev')

  def IsTestFlight(self):
    return self.version.endswith('.adhoc')

  def IsAppStore(self):
    return not self.IsDev() and not self.IsTestFlight()

  def LT(self, version):
    return cmp(self.components, version.split('.')) < 0

  def LE(self, version):
    return cmp(self.components, version.split('.')) <= 0

  def EQ(self, version):
    return cmp(self.components, version.split('.')) == 0

  def GT(self, version):
    return cmp(self.components, version.split('.')) > 0

  def GE(self, version):
    return cmp(self.components, version.split('.')) >= 0
