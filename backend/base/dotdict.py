# Copyright 2012 Viewfinder Inc. All Rights Reserved.

""" Defines DotDict data structure, a nestable dictionary structure which allows programmers
to access nested variables using '.' notation.
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'


class DotDict(dict):
  """Dictionary extension which allows referencing nested dictionaries using object dot notation.

  Pilfered from:
    http://stackoverflow.com/questions/3797957/python-easily-access-deeply-nested-dict-get-and-set

  Examples:

    d = DotDict({'a':{'b':1,'c':2}, 'd':3})
    print d.a.b  # 1
    print d.a.c  # 2
    print d.a.d  # Raises KeyError
    print d.d    # 3
    d.a.e = 3    # Value set correctly

    # Limitation - cannot set sparsely using dot notation:
    d.x.y.z = 3     # Fails with KeyError
    d['x.y.z'] = 3  # Works correctly
    print d.x.y.z   # 3
  """
  def __init__(self, value=None):
    if value is None:
      pass
    elif isinstance(value, dict):
      for key in value:
        self.__setitem__(key, value[key])
    else:
      raise TypeError, 'Can only initialize dotdict from another dict.'

  def __setitem__(self, key, value):
    if '.' in key:
      myKey, restOfKey = key.split('.', 1)
      target = self.setdefault(myKey, DotDict())
      if not isinstance(target, DotDict):
        raise KeyError('Cannot set "%s" in "%s" (%s)' % (restOfKey, myKey, repr(target)))
      target[restOfKey] = value
    else:
      if isinstance(value, dict) and not isinstance(value, DotDict):
        value = DotDict(value)
      dict.__setitem__(self, key, value)

  def __getitem__(self, key):
    if '.' not in key:
      return dict.__getitem__(self, key)
    myKey, restOfKey = key.split('.', 1)
    target = dict.__getitem__(self, myKey)
    if not isinstance(target, DotDict):
      raise KeyError('Cannot get "%s" in "%s" (%s)' % (restOfKey, myKey, repr(target)))
    return target[restOfKey]

  def __contains__(self, key):
    if '.' not in key:
      return dict.__contains__(self, key)
    myKey, restOfKey = key.split('.', 1)
    if not dict.__contains__(self, myKey):
      return False
    target = dict.__getitem__(self, myKey)
    if not isinstance(target, DotDict):
      return False
    return restOfKey in target

  def flatten(self):
    """Returns a regular dictionary with the same leaf items as this DotDict.
    The resulting dict will have no nesting - items will have a dot-joined key
    reflecting their nesting in the DotDict.

      #Example...
      d = DotDict()
      d.a = 1
      d.x = dict()
      d.x.y = 2
      d.x.z = 3

      flat = d.flatten()
      print d.keys()      # ['a', 'x.y', 'x.z']
    """
    newdict = dict()
    def recurse_flatten(prefix, dd):
      for k, v in dd.iteritems():
        newkey = prefix + '.' + k if len(prefix) > 0 else k
        if isinstance(v, DotDict):
          recurse_flatten(newkey, v)
        else:
          newdict[newkey] = v

    recurse_flatten('', self)
    return newdict


  def setdefault(self, key, default):
    if key not in self:
      self[key] = default
    return self[key]

  __setattr__ = __setitem__
  __getattr__ = __getitem__
