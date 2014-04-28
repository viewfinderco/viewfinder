# Copyright 2012 Viewfinder Inc. All Rights Reserved.

""" Module to support storing arbitrary contextual information using
tornado's StackContext class.

 * ContextLocal: base class which implements context-local instance management.
 * ViewfinderContext: context-local class for storing context during a viewfinder request.
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import threading

class _ContextLocalManager(threading.local):
  """Extension of threading.local which ensures that the 'current' attribute
  defaults to an empty dict for each thread.
  """
  def __init__(self):
    self.current = dict()


class ContextLocal(object):
  """Base class for objects which have a context-local instance.  An instance
  of a derived class can be pushed onto the persistent stack using a
  StackContext object. The currently in-scope instance of a derived class
  can be retrieved from the stack with the class method cls.current().
  This mimics the concept of a thread-local object, but the object is linked
  to the persistent stack context provided by Tornado.

  Example:

    # Create a stack-aware context class
    class MyContext(ContextLocal):
      def __init__(self, val):
        self.some_value = val

    # Push a new context onto the stack, and verify a value in it:
    with StackContext(MyContext(val)):
      assert MyContext.current().some_value == val
  """
  _contexts = _ContextLocalManager()
  _default_instance = None

  def __init__(self):
    """Maintain stack of previous instances.  This is a stack to support re-entry
    of a context.
    """
    self.__previous_instances = []

  @classmethod
  def current(cls):
    """Retrieves the currently in-scope instance of context class cls, or a
    default instance if no instance is currently in scope.
    """
    current_value = cls._contexts.current.get(cls.__name__, None)
    return current_value if current_value is not None else cls._default_instance

  def __enter__(self):
    """Sets this instance to be the currently in-scope instance of its class."""
    cls = type(self)
    self.__previous_instances.append(cls._contexts.current.get(cls.__name__, None))
    cls._contexts.current[cls.__name__] = self

  def __exit__(self, exc_type, exc_value, exc_traceback):
    """Sets the currently in-scope instance of this class to its previous value."""
    cls = type(self)
    cls._contexts.current[cls.__name__] = self.__previous_instances.pop()

  def __call__(self):
    """StackContext takes a 'context factory' as a parameter, which is a callable
    which should return a context object.  By making an instance of this class return
    itself when called, each instance becomes its own factory.
    """
    return self
