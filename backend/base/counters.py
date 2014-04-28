# Copyright 2012 Viewfinder Inc. All Rights Reserved.

""" Module to support custom performance counters in python modules.
"""

__author__ = 'matt@emailscrubbed.com (Matt Tracy)'

import time
from dotdict import DotDict
from collections import deque


class _CounterManager(DotDict):
  """A CounterManager object is used as a central place for modules to register their
  performance counters.  The manager allows access to the counters utilizing a simple
  namespace notation.
  """
  def register(self, counter):
    """Register a counter with the manager.  Counters are organized
    into namespaces using '.' as a separator.  Examples of module names:

      # Valid counter names
      my_counter
      module.counters.another_counter

    Note that it is invalid for a counter's name to be the namespace of
    another counter:

      # Invalid counter names, due to namespace conflict:
      my_module.counter
      my_module.counter.invalid
    """
    cname = counter.name
    if len(cname) == 0:
      raise ValueError('Cannot register counter with a blank name.')

    # Verify that there are no namespace conflicts.
    existing = self.get(cname, None)
    if existing:
      if isinstance(existing, DotDict):
        raise KeyError('Cannot register counter with name %s because a namespace'
                        ' with the same name was previously registered.' % cname)
      else:
        raise KeyError('Cannot register counter with name %s because a counter'
                        ' with the same name was previously registered.' % cname)

    # Insert the actual counter.
    try:
      self[cname] = counter
    except KeyError:
      raise KeyError('Cannot register counter with name %s because a portion of its'
                     ' namespace conflicts with a previously registered counter.' % cname)


# Global instance of CounterManager.
counters = _CounterManager()


def define_total(name, description, manager=counters):
  """Creates a performance counter which tracks some cumulative value over the
  course of the program. The performance counter can be incremented using one
  of several increment methods:

    # Define a new total counter in the module.
    total_counter = counters.total('module.counters.total', 'Total count of events.')

    # ...

    total_counter.increment()      # Increment by 1
    total_counter.increment(20)
    total_counter.decrement()      # Decrement by 1
    total_counter.decrement(20)

  When sampled using a Meter, this counter returns the total accumulated value of the
  counter since the start of the program.
  """
  counter = _TotalCounter(name, description)
  manager.register(counter)
  return counter


def define_delta(name, description, manager=counters):
  """Creates a performance counter which tracks the accumulation of a value since the previous
  sample of the counter, thus providing a delta of the underlying value of the counter. The
  performance counter can be incremented using one of several increment methods:

    # Define a new delta counter in the module.
    delta_counter = counters.delta('module.counters.delta', 'Count of new events.')

    # ...

    delta_counter.increment()      # Increment by 1
    delta_counter.increment(20)
    delta_counter.decrement()      # Decrement by 1
    delta_counter.decrement(20)

  When sampled using a Meter, this counter returns the difference in the accumulated value
  since the previous sample of the Meter.
  """
  counter = _DeltaCounter(name, description)
  manager.register(counter)
  return counter


def define_rate(name, description, unit_seconds=1, manager=counters):
  """Creates a performance counter which tracks some rate at which a value accumulates
  over the course of the program. The counter has an optional 'unit_seconds' parameter
  which determines the time unit associated with the value - the default is one second.

  The counter can be incremented using one of several increment methods:

    # Define a new rate counter in the module.
    rate_counter = counters.rate('module.counters.rate', 'Accumulation per minute', unit_seconds=60)

    # ...

    rate_counter.increment()      # Increment by 1
    rate_counter.increment(20)
    rate_counter.decrement()      # Decrement by 1
    rate_counter.decrement(20)

  When sampled using a Meter, this counter returns the average rate of change in the underlying value
  per the given unit of time, taken over the time span since the previous sample of the Meter.
  """
  counter = _RateCounter(name, description, unit_seconds)
  manager.register(counter)
  return counter


def define_average(name, description, manager=counters):
  """Creates a performance counter which tracks the average value of a quantity which varies
  for discrete occurrences of an event.  An example would be the average time taken to complete
  an operation, or the bytes transferred per operation.  Unlike other counters, this counter
  provides only a single method 'add()', which is called with the quantity for a single
  occurrence of the event.  The counter will essentially track the average of all numbers
  passed to the 'add()' method.

    # Define a new average counter in the module.
    avg_counter = counters.average('module.counters.average', 'Average bytes per request')

    # ...

    response = perform_some_request()
    avg_counter.add(response.bytes_transfered)


  When sampled using a Meter, this counter returns the average value of quantities passed
  to 'add()' for all events since the previous sample of the Meter.
  """
  counter = _AverageCounter(name, description)
  manager.register(counter)
  return counter


class _BaseCounter(object):
  """ Basic counter object, which should not be directly instantiated.  Implements
  the common method 'get_sampler()', which returns a closure function which can be
  called repeatedly to sample the counter.
  """
  def __init__(self, name, description):
    self.name = name
    self.description = description

  def get_sampler(self):
    """ Returns a closure function which can be called repeatedly to sample the counter.
    The use of a closure function ensures that multiple Meters can be used simultaneously
    without interference.
    """
    last_sample = [self._raw_sample()]
    def sampler_func():
      old_sample = last_sample[0]
      last_sample[0] = self._raw_sample()
      return self._computed_sample(old_sample, last_sample[0])
    return sampler_func

  def _raw_sample(self):
    """Returns a raw sample for the counter, which represents the value of internal
    counters at the moment the sample is taken.  Two raw samples will be used inside
    of _computed_sample() to return a value from the counter with proper units.
    """
    raise NotImplementedError('_raw_sample() must be implemented in a subclass.')

  def _computed_sample(self, s1, s2):
    """Using two raw samples taken previously, creates a sample in units
    which are appropriate to the specific type of counter.
    """
    raise NotImplementedError('_computed_sample() must be implemented in a subclass.')


class _TotalCounter(_BaseCounter):
  """Counter type which provides a running total for the duration of the program."""
  def __init__(self, name, description):
    super(_TotalCounter, self).__init__(name, description)
    self._counter = 0L

  def increment(self, value=1):
    """Increments the internal counter by a value.  If not value is provided, increments
    by one.
    """
    self._counter += value

  def decrement(self, value=1):
    """Decrements the internal counter by a value.  If not value is provided, decrements
    by one.
    """
    self._counter -= value

  def get_total(self):
    return self._counter

  def _raw_sample(self):
    # Raw sample is simply the current value of the counter.
    return self._counter

  def _computed_sample(self, s1, s2):
    # For total, do not consider the earlier value - just return the current value.
    return s2


class _DeltaCounter(_TotalCounter):
  """Counter type which provides the accumulation since the previous sample of the counter."""

  def _computed_sample(self, s1, s2):
    # For delta, subtract the previous sample from the current sample.
    return s2 - s1


class _RateCounter(_TotalCounter):
  """Counter type which provides the rate of accumulation since the previous sample of the counter.
  The rate is expressed in terms of a unit of time provided in seconds; the default is one second.
  """
  def __init__(self, name, description, unit_seconds=1, time_func=None):
    super(_RateCounter, self).__init__(name, description)
    self._resolution = unit_seconds
    self._time_func = time_func or time.time

  def _raw_sample(self):
    # Raw sample for Rate must include both the current clock and the counter value.
    return (self._counter, self._time_func())

  def _computed_sample(self, s1, s2):
    # Take the delta for the counter value and divide it by the elapsed time since the previous sample.
    # The result is multiplied by the resolution value in order to provide the correct units.
    time_diff = s2[1] - s1[1]
    if time_diff == 0:
      return 0
    return (s2[0] - s1[0]) * self._resolution / time_diff


class _AverageCounter(_BaseCounter):
  """Counter type which provides the average value of some quantity over a number of occurences."""
  def __init__(self, name, description):
    super(_AverageCounter, self).__init__(name, description)
    self._counter = 0L
    self._base_counter = 0L

  def add(self, value):
    """Adds the value from a single occurrence to the counter."""
    self._counter += value
    self._base_counter += 1

  def _raw_sample(self):
    return (self._counter, self._base_counter)

  def _computed_sample(self, s1, s2):
    base_diff = s2[1] - s1[1]
    if base_diff == 0:
      return 0
    return (s2[0] - s1[0]) / base_diff


class Meter(object):
  """Meter object, used to periodically sample all performance counters in a given namespace.
  Once created, samples can be obtained by periodically calling the sample() method of the
  Meter object.

      # Example:
      import counters

      r = counters.define_rate('module.rate', 'Rate counter')
      d = counters.define_delta('module.delta', 'Delta counter')

      m = counters.Meter()
      m.add_counters(counters.counters.module)

      sample = m.sample()
      print sample.module.rate      # 0
      print sample.module.delta     # 0

      desc = m.describe()

      print sample.module.rate      # 'Rate counter'
      print sample.module.delta     # 'Delta counter'
  """
  def __init__(self, counters=None):
    """Initialize a new meter object.  If the optional counters parameter is provided,
    its value is passed immediately to the add_counters() method.
    """
    self._counters = dict()
    self._description = None
    if counters is not None:
      self.add_counters(counters)

  def add_counters(self, counters):
    """Add an additional counter or collection of counters to this meter.  The intention is
    for a portion of the global 'counters' instance (or another CounterManager object) to be
    passed to this method.
    """
    if isinstance(counters, DotDict):
      flat = counters.flatten()
      self._counters.update([(v, v.get_sampler()) for v in flat.itervalues()])
    else:
      # Single counter instance.
      self._counters[counters] = counters.get_sampler()

    # Clear existing description object.
    self._description = None

  def sample(self):
    """Samples all counters being tracked by this meter, returning a DotDict object
    with all of the sampled values organized by namespace.
    """
    new_sample = DotDict()
    for k in self._counters.keys():
      new_sample[k.name] = self._counters[k]()
    return new_sample

  def describe(self):
    """Returns the description of all counters being tracked by this meter. The returned
    object is a DotDict object with all of the descriptions organized by counter namespace.
    """
    if self._description is None:
      new_description = DotDict()
      for k in self._counters.keys():
        new_description[k.name] = k.description
      self._description = new_description
    return self._description
