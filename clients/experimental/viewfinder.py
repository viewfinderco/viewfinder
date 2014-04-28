#! /usr/bin/env python

import copy
import json
import math
import os
import pygame
import random
import sys
import time
from collections import namedtuple
from datetime import timedelta, datetime
from operator import itemgetter

from state_abbrev import STATE_MAP

pygame.init()
pygame.font.init()
font = pygame.font.SysFont("helvetica", 12)
bold_font = pygame.font.SysFont("helvetica", 12, bold=True)

iphone_dims = 640, 960
event_height = 320
window_height = iphone_dims[1]
target_box_width = 30
target_box_padding = 15
right_margin = target_box_width + target_box_padding
min_tick_x_offset = 140
draw_color = pygame.Color(127, 127, 127, 255)
line_color = pygame.Color(217, 67, 67, 255)
circle_color = pygame.Color(217, 217, 217, 255)
backdrop_color = pygame.Color(255, 255, 255, 255)
text_color = pygame.Color(67, 67, 67, 255)
place_color = pygame.Color(245, 117, 39, 255)
cur_time_color = pygame.Color(217, 67, 67, 255)
max_places = 15

# Time constants in seconds
HOUR = 60 * 60
DAY = 60 * 60 * 24
MONTH = DAY * 30  # approximate
YEAR = DAY * 365  # approximate


class VFTime(object):
  """Class that understands how motion translates to changes in the
  current time. All values are expressed as UTC time in seconds since
  the epoch. As y values increase, time decreases. So most recent dates
  are ordered at the "top" of the screen and less recent at the bottom.
  """
  _MIN_TOTAL_SECS = iphone_dims[1] #float(60 * 60 * 24 * 7)  # 1 week

  def __init__(self, min_time, max_time, reverse_x=True, reverse_y=True):
    """'min_time' and 'max_time' are the the first and last event
    timestamps.  'reverse_x' and 'reverse_y' specify whether the
    directionality of x and y axes should be reversed.
    """
    self._total_secs = max_time - min_time
    self._min_time = min_time
    self._max_time = max_time
    self._cur_time = max_time
    self._width = (iphone_dims[0] - right_margin)
    self._height = iphone_dims[1]
    self._roc_max = float(max_time - min_time) / self._height
    self._roc_min = float(VFTime._MIN_TOTAL_SECS) / self._height
    self._roc_slope = float(VFTime._MIN_TOTAL_SECS - self._total_secs) / \
        (self._width * self._height)
    self._reverse_x = reverse_x
    self._reverse_y = reverse_y
    self._active = False

  def Start(self, start_pos):
    """Called to reset the time based on an initial touch
    point. 'start_pos' is the iphone screen coordinates of the initial
    touch point.
    """
    self._last_pos = self._TransformPos(start_pos)
    self._cur_time = self._min_time + self._last_pos[1] * self._roc_max
    self._active = True

  def Stop(self):
    self._active = False

  def IsActive(self):
    return self._active

  def AdjustTime(self, touch_pos):
    """Computes the delta time by integrating the change in time
    implied by traveling along a linear path between self._last_pos
    and touch_pos (after transforming). Sets the new time and last
    position.

    The time is always adjusted by min and max constraints to account
    for the discontinuities which would occur when the position moves
    horizontally backwards.
    """
    if not self._active:
      return
    new_pos = self._TransformPos(touch_pos)
    delta_time = self._IntegrateTime(new_pos)
    self._cur_time = self._EnforceBounds(self._cur_time + delta_time, new_pos)
    self._last_pos = new_pos

  def ComputeTimeAtPos(self, pos, log=False):
    """Computes the resulting time if the current time was adjusted by
    a movement to 'pos'. Similarly to AdjustTime, this is done by
    integrating the change in time implied by traveling along a linear
    path between self._last_pos and 'pos'. Does not mutate the internal
    state of the object.
    """
    new_pos = self._TransformPos(pos)
    delta_time = self._IntegrateTime(new_pos, log)
    return self._cur_time + delta_time

  def GetMaxInterval(self):
    """Returns the maximum interval in seconds (min, max)."""
    return (self._min_time, self._max_time)

  def GetInterval(self):
    """Returns the size of the current interval in seconds (min, max)."""
    interval = self._height * (self._roc_max + self._roc_slope * self._last_pos[0])
    y_ratio = float(self._last_pos[1]) / float(self._height)
    return (self._cur_time - y_ratio * interval,
            self._cur_time + (1.0 - y_ratio) * interval)

  def GetPos(self):
    """Returns the last reported position (untransform to iphone coordinates)."""
    return self._UntransformPos()

  def GetTime(self):
    """Returns the current time as seconds since the epoch in UTC."""
    return self._cur_time

  def GetDatetime(self):
    """Returns a datetime object for the current time."""
    return datetime.fromtimestamp(self._cur_time)

  def _IntegrateTime(self, new_pos, log=False):
    """Integrates time by movement along the linear path defined by the
    vector between self._last_pos and new_pos.

    - 'm': slope of line from self._last_pos to new_pos.
    - 'a': max rate of change (self._roc_max) is (max - min seconds) / screen height
    - 'b': rate of change slope (self._roc_slope)
    - 'c': last Y position (self._last_pos[1])
    - 'd': exponent in an inverse exponential curve from max roc to min roc
    """
    x_delta = float(new_pos[0] - self._last_pos[0])
    y_delta = (new_pos[1] - self._last_pos[1])
    if y_delta == 0.0:
      return 0.0  # no integration necessary
    m = x_delta / y_delta
    a = self._roc_max
    b = self._roc_slope
    c = float(self._last_pos[1])

    def _ComputeIntegral(y):
      return 0.5 * y * (2*a + b*(2*self._last_pos[0] + m*(y-2*self._last_pos[1])))

    if log:
      max_diff = (new_pos[1] - self._last_pos[1]) * (self._roc_max + self._roc_slope * min(new_pos[0], self._last_pos[0]))
      print 'max interval: %.2f' % (self._max_time - self._min_time)
      print 'x delta: %.2f, y delta: %.2f, slope: %.2f' % (x_delta, y_delta, 1/m)
      print 'max difference allowed: %.2f' % max_diff
      print 'integral at new pos: %.2f' % _ComputeIntegral(new_pos[1])
      print 'integral at old pos: %.2f' % _ComputeIntegral(self._last_pos[1])
      print 'integrated difference: %.2f' % (_ComputeIntegral(new_pos[1]) - _ComputeIntegral(self._last_pos[1]))

    return _ComputeIntegral(new_pos[1]) - _ComputeIntegral(self._last_pos[1])

  def _EnforceBounds(self, cur_time, new_pos):
    """The current x position defines the interval of time which
    stretches vertically from 0 to 'self._height'. As long as fixing
    'cur_time' at the current y position does not imply that the
    interval would fail to take up the entire screen, no adjustment
    is necessary.
    """
    interval = self._height * (self._roc_max + self._roc_slope * new_pos[0])
    y_ratio = float(new_pos[1]) / float(self._height)
    if cur_time - y_ratio * interval < self._min_time:
      cur_time = self._min_time + y_ratio * interval
    if cur_time + (1.0 - y_ratio) * interval >= self._max_time:
      cur_time = self._max_time - (1.0 - y_ratio) * interval
    return cur_time

  def _UntransformPos(self):
    """Converts the bounded, transformed current position back to screen
    dimensions.
    """
    pos = [self._last_pos[0] + right_margin, self._last_pos[1]]
    if self._reverse_x:
      pos[0] = iphone_dims[0] - pos[0] - 1
    if self._reverse_y:
      pos[1] = iphone_dims[1] - pos[1] - 1
    return pos

  def _TransformPos(self, pos):
    """Returns a transformed position. Uses 'reverse_x' and 'reverse_y'
    to decide whether to reverse the x and y axes.
    """
    new_pos = copy.copy(pos)
    if self._reverse_x:
      new_pos[0] = iphone_dims[0] - new_pos[0] - 1
    if self._reverse_y:
      new_pos[1] = iphone_dims[1] - new_pos[1] - 1
    new_pos[0] = min(self._width, max(0, new_pos[0] - right_margin))
    new_pos[1] = min(self._height, max(0, int(new_pos[1])))
    return new_pos


def DimensionToPixel(dimension):
  return int((1.0 * dimension * window_height) / iphone_dims[1])

def DimensionsToPixels(dimensions):
  return [DimensionToPixel(x) for x in dimensions]

def PixelToDimension(pixel):
  return int((1.0 * pixel * iphone_dims[1]) / window_height)

def PixelsToDimensions(pixels):
  return [PixelToDimension(x) for x in pixels]

# Create the simulation window
window_dimensions = [d for d in DimensionsToPixels(iphone_dims)]
window = pygame.display.set_mode(window_dimensions, pygame.DOUBLEBUF | \
                                   pygame.HWSURFACE | \
                                   pygame.RESIZABLE)
pygame.display.set_caption('Timeline')

def GetSurface():
  return pygame.display.get_surface()

def ClearSurface():
  GetSurface().fill(backdrop_color)

def DrawTargetBoxes():
  box = [iphone_dims[0] - target_box_width - target_box_padding,
         target_box_padding, target_box_width, iphone_dims[1] - target_box_padding * 2]
  pygame.draw.rect(GetSurface(), draw_color, DimensionsToPixels(box), 1)

  #box = [iphone_dims[0] * target_box_padding,
  #       iphone_dims[1] * target_box_padding,
  #       iphone_dims[0] * target_box_width,
  #       iphone_dims[1] * (1.0 - target_box_padding * 2)]
  #pygame.draw.rect(GetSurface(), draw_color, DimensionsToPixels(box), 1)

def DrawLabel(label, x, y, color, font, transparency, bold=False, border=False, left_justify=False):
  color = pygame.Color(*[int(i + transparency * (j - i)) for i, j in zip(color, backdrop_color)])
  offset = DimensionsToPixels([x, y])
  ts = bold_font.render(label, True, color) if bold else font.render(label, True, color)
  if y > iphone_dims[1] - ts.get_height():
    offset[1] -= (ts.get_height() + 2)
  else:
    offset[1] += 2
  if left_justify:
    offset[0] = min(iphone_dims[0], offset[0])
  else:
    offset[0] = max(0, offset[0] - ts.get_width())
  GetSurface().blit(ts, offset)
  if border:
    pygame.draw.rect(GetSurface(), color,
                     [offset[0]-2, offset[1]-2, ts.get_width() + 4, ts.get_height() + 4], 1)

def DrawLine(line, color, transparency):
  color = pygame.Color(*[int(i + transparency * (j - i)) for i, j in zip(color, backdrop_color)])
  tx_line = [DimensionsToPixels(pt) for pt in line]
  pygame.draw.aaline(GetSurface(), color, tx_line[0], tx_line[1], 1)

def EnforceBounds(val, min_val, max_val):
  val = max(val, min_val)
  return min(val, max_val)

def GetNextMonth(date):
  if date.month == 12:
    return date.replace(year=date.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
  else:
    return date.replace(month=date.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

def DrawGuides(vf_time):
  """Draws guides showing the currently displayed interval at scale on
  the right side of the screen. Also draw a line backwards from the
  current time to the corresponding time on the right side interval.
  """
  pos = vf_time.GetPos()
  cur_time = vf_time.GetTime()
  interval = vf_time.GetInterval()
  interval_size = interval[1] - interval[0]
  max_interval = vf_time.GetMaxInterval()
  max_interval_size = max_interval[1] - max_interval[0]

  def _DrawGuideLine(timestamp, fmt, transparency=0.0):
    """Draws a guide line from current interval at 'timestamp' to the max
    interval.
    """
    left_ratio = float(timestamp - interval[0]) / interval_size
    left_y = int(iphone_dims[1] * (1.0 - left_ratio))
    right_ratio = float(timestamp - max_interval[0]) / (max_interval[1] - max_interval[0])
    right_y = int(iphone_dims[1] * (1.0 - right_ratio))
    line = [(pos[0], left_y), (iphone_dims[0], right_y)]
    DrawLine(line, line_color, 0.0)
    DrawLabel(datetime.fromtimestamp(timestamp).strftime(fmt),
              iphone_dims[0], right_y, text_color, font, 0.0)

  def _DrawHorizontalGuideLine(timestamp, fmt, transparency=0.0):
    """Draws a guide line from current interval at 'timestamp' to the max
    interval.
    """
    left_ratio = float(timestamp - interval[0]) / interval_size
    left_y = int(iphone_dims[1] * (1.0 - left_ratio))
    right_ratio = float(timestamp - max_interval[0]) / (max_interval[1] - max_interval[0])
    right_y = int(iphone_dims[1] * (1.0 - right_ratio))
    line = [(iphone_dims[0] - 60, right_y), (iphone_dims[0], right_y)]
    DrawLine(line, line_color, 0.0)
    DrawLabel(datetime.fromtimestamp(timestamp).strftime(fmt),
              iphone_dims[0]-60, right_y, text_color, font, 0.0)

  # Draw interval guide lines.
  [_DrawHorizontalGuideLine(x, '%b %d, %Y') for x in interval]
  _DrawHorizontalGuideLine(cur_time, '%b %d, %Y')

  interval = max_interval
  interval_size = max_interval[1] - max_interval[0]
  def _DrawIntervalTick(timestamp, fmt, transparency=0.0):
    """Draws a guide label with specified 'timestamp' and 'fmt'."""
    label = datetime.fromtimestamp(timestamp).strftime(fmt)
    ratio = float(timestamp - interval[0]) / interval_size
    x = iphone_dims[0]#max(min_tick_x_offset, pos[0])
    y = int(iphone_dims[1] * (1.0 - ratio))
    DrawLabel(label, x, y, text_color, font, transparency)

  # Draw ticks for days, months, & years.
  start = datetime.fromtimestamp(interval[0])
  end = datetime.fromtimestamp(interval[1])

  fade_interval = [60, 4]
  if interval_size < DAY * fade_interval[0]:
    transparency = max(0.0, (float(interval_size - DAY * fade_interval[1]) / DAY) / (fade_interval[0] - fade_interval[1]))
    cur = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while cur < end:
      _DrawIntervalTick(time.mktime(cur.timetuple()), '%b %d, %Y', transparency)
      cur = cur + timedelta(days=1)

  fade_interval = [36, 12]
  if interval_size < MONTH * fade_interval[0]:
    transparency = max(0.0, (float(interval_size - MONTH * fade_interval[1]) / MONTH) / (fade_interval[0] - fade_interval[1]))
    cur = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while cur < end:
      _DrawIntervalTick(time.mktime(cur.timetuple()), '%b %Y', transparency)
      cur = GetNextMonth(cur)

  # Draw years if there are possibly more than two displayed.
  if interval_size >= MONTH * 12:
    cur = start.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    while cur < end:
      _DrawIntervalTick(time.mktime(cur.timetuple()), '%Y')
      cur = cur.replace(year=cur.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

  #DrawLabel(datetime.fromtimestamp(cur_time).strftime('%b %d, %Y'),
  #          pos[0], pos[1], cur_time_color, font, 0.0)
  # Draw max interval labels.
  #DrawLabel(datetime.fromtimestamp(max_interval[1]).strftime('%b %d, %Y'),
  #          iphone_dims[0], 0, text_color, font, 0.0)
  #DrawLabel(datetime.fromtimestamp(max_interval[0]).strftime('%b %d, %Y'),
  #          iphone_dims[0], iphone_dims[1], text_color, font, 0.0)


def GetPlace(pm):
  locality = pm.get('locality', None)
  state = pm.get('state', None)
  country = pm.get('country', None)
  if country == 'United States':
    if locality and state:
      return '%s, %s' % (locality, STATE_MAP[state])
  elif locality and country:
    return '%s, %s' % (locality, pm['iso_country_code'])
  return locality or state or pm.get('country', None)


def CombinePlaces(places, time_resolution):
  """Try to combine consecutive viewpoints into a meta-viewpoints by
  locality, state, and then country. Combination can only occur if the
  time delta between the viewpoints is <= time_resolution. Returns two
  lists: one for locality and one for country.
  """
  sorted_places = sorted([{'locality': GetPlace(p['placemark']),
                           'timestamp': p['timestamp'],
                           'opacity': 1.0,
                           'num_combined': 1,
                           'total_count': p['total_count']} for p in places], key=itemgetter('timestamp'))
  place_list = []
  def _GetAvgTimestamp(p):
    return p['timestamp'] / p['num_combined']

  def _MaybeCombinePlace(p):
    if place_list:
      last_place = place_list[-1]
      if p['locality'] == last_place['locality'] and \
            abs(p['timestamp'] - _GetAvgTimestamp(last_place)) < time_resolution:
        for attr in ['timestamp', 'total_count', 'num_combined']:
          last_place[attr] += p[attr]
        return
    place_list.append(p)

  for p in sorted_places:
    _MaybeCombinePlace(p)

  for p in place_list:
    p['timestamp'] = _GetAvgTimestamp(p)
  return place_list


def GetCircle(pos):
  """Gets the circle (center, radius) that goes through the two
  endpoints of the current time extent (x=pos[0]) and just touches the
  left edge of the screen. Also computes the degrees (in radians) of
  the small arc through the three points.

  Returns (center, radius, arc-degrees).
  """
  if pos[0] == 0:
    pos[0] = 1
  a, b = float(pos[0]), 0.0
  c, d = 0.0, iphone_dims[1]/2.0
  e, f = float(pos[0]), float(iphone_dims[1])
  k = (0.5)*((a**2+b**2)*(e-c) + (c**2+d**2)*(a-e) + (e**2+f**2)*(c-a)) / (b*(e-c)+d*(a-e)+f*(c-a))
  h = (0.5)*((a**2+b**2)*(f-d) + (c**2+d**2)*(b-f) + (e**2+f**2)*(d-b)) / (a*(f-d)+c*(b-f)+e*(d-b))
  rsqr = (a-h)**2 + (b-k)**2

  theta = math.acos(((a-h)*(e-h) + (b-k)*(f-k)) / rsqr)
  return ((h, k), math.sqrt(rsqr), theta)


def RenderEvents(vf_time, places):
  """Renders events based on the current time and interval available
  via vf_time.
  """
  # Get circle and draw it.
  c, r, theta = GetCircle(vf_time.GetPos())

  def _GetArcCoords(radians):
    """Returns the coordinates on the arc for the specified angle."""
    return [c[0] + r*math.cos(radians), c[1] + r*math.sin(radians)]

  def _GetTimestamp(radians):
    """Gets timestamp implied by moving to 'radians' degrees on the arc."""
    return vf_time.ComputeTimeAtPos(_GetArcCoords(radians))

  def _ApproximateAngle(timestamp, x, x1):
    """Determines the position along the arc of the specified timestamp
    via numeric approximation (Secant Method).
    """
    def f(x):
      return _GetTimestamp(x) - timestamp
    error = 1  # get within 1 pixel
    x2 = 0
    for attempt in xrange(20):
      d = f(x1) - f(x)
      if d < error:
        return x1
      x2 = x1 - f(x1) * (x1 - x) / d
      x = x1
      x1 = x2
      dx = x1 - x
    assert False, 'could not converge on position'

  def _ComputeDecay(distance, half_distance):
    return math.exp(-math.log(2.0) * distance / half_distance)

  interval = vf_time.GetInterval()
  combined_places = CombinePlaces(places, float(interval[1] - interval[0]) / 24)
  start_angle = math.pi - theta / 2
  end_angle = math.pi + theta / 2
  text_height = 16.0
  half_distance = 12.0

  places = []
  for p in combined_places:
    place_angle = _ApproximateAngle(p['timestamp'], start_angle, end_angle)
    if place_angle > start_angle and place_angle < end_angle:
      p['x'], p['y'] = _GetArcCoords(place_angle)
      places.append(p)

  # For each place, compute the rank in the 'neighborhood'.
  for p in places:
    y = p['y']
    sub_places = [sp for sp in places if sp['y'] > (y - text_height) and sp['y'] < (y + text_height)]
    max_count = max([sp['total_count'] for sp in sub_places])
    total_weight = 0
    for sp in sub_places:
      total_weight += (float(sp['total_count']) / max_count) * _ComputeDecay(abs(sp['y'] - y), half_distance)
    p['weight'] = (float(p['total_count']) / max_count) / total_weight

  if places:
    min_weight = min(p['weight'] for p in places)
    max_weight = max(p['weight'] for p in places)
    sorted_places = sorted(places, key=itemgetter('weight'))
    for p in sorted_places:
      if min_weight == max_weight:
        opacity = 1.0
      else:
        opacity = (p['weight'] - min_weight) / (max_weight - min_weight)
      DrawLabel('%s' % (p['locality']), p['x'], p['y'], place_color,
                font, 1.0 - opacity, left_justify=True)


def ProcessMotion(vf_time):
  """Process pygame events for the window. Mousedown in the target area
  starts the simulation. Mouse movement is reported to the 'vf_time' arg
  to adjust the current time. Mouseup stop the simulation.
  """
  last_pos = None
  for event in pygame.event.get():
    if event.type == pygame.QUIT or event.type == pygame.KEYDOWN:
      return sys.exit(0)
    if vf_time.IsActive():
      if event.type == pygame.MOUSEMOTION:
        if event.buttons[0]:
          last_pos = event.pos
      elif event.type == pygame.MOUSEBUTTONUP:
        if event.button == 1:
          vf_time.Stop()
    else:
      if event.type == pygame.MOUSEBUTTONDOWN:
        if event.button == 1:
          pos = PixelsToDimensions(event.pos)
          x, y = pos
          if x > iphone_dims[0] - target_box_width - target_box_padding and \
                x < iphone_dims[0] - target_box_padding and \
                y > target_box_padding and \
                y < iphone_dims[1] - target_box_padding:
            vf_time.Start(pos)

  if last_pos:
    vf_time.AdjustTime(PixelsToDimensions(last_pos))


def main():
  vp_data = []
  with open(os.path.join(os.path.dirname(__file__), 'viewpoint_data.txt'), 'r') as f:
    vp_data = json.load(f)
    vp_data = [vp for vp in vp_data if 'placemark' in vp]
    for index in xrange(len(vp_data)):
      vp = vp_data[index]
      vp['index'] = index
      vp['timestamp'] = index * event_height
      vp['datetime'] = datetime.fromtimestamp(vp['timestamp'])

  max_date = vp_data[0]['datetime']
  min_date = vp_data[-1]['datetime']
  vf_time = VFTime(vp_data[0]['timestamp'], vp_data[-1]['timestamp'])

  # Rates encompass: X years, 12 months, 28-31 days, 24 hours.
  levels = ['hours', 'days', 'months', 'years']
  level = levels[-1]
  display_places = False

  while True:
    ClearSurface()
    ProcessMotion(vf_time)
    if not vf_time.IsActive():
      DrawTargetBoxes()
    else:
      label = vf_time.GetDatetime().strftime('%b %d %Y')
      DrawGuides(vf_time)

      # Get list of viewpoints with place information between min-max dates.
      interval = vf_time.GetInterval()
      start = interval[0] - (interval[1] - interval[0]) / 2
      end = interval[1] + (interval[1] - interval[0]) / 2
      places = [vp for vp in vp_data if vp['timestamp'] > start and vp['timestamp'] < end]
      if vf_time.GetPos()[0] < 500:
        display_places = True
      if display_places:
        RenderEvents(vf_time, vp_data)

    pygame.display.flip()

if __name__ == '__main__':
  main()
