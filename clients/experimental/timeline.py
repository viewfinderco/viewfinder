#!/usr/bin/env python

import os
import pygame
import random
import sys
import time
from collections import namedtuple
from datetime import timedelta, datetime

pygame.init()
pygame.font.init()
sys_font = pygame.font.SysFont("fixed", 14)

iphone_dims = 320, 480
target_box_width = 0.075
target_box_padding = 0.025
draw_color = pygame.Color(127, 127, 127, 255)
line_color = pygame.Color(237, 237, 237, 255)
backdrop_color = pygame.Color(255, 255, 255, 255)
text_color = pygame.Color(67, 67, 67, 255)
rect_color = pygame.Color(217, 67, 67, 255)

# Query display modes and choose the second largest
modes = pygame.display.list_modes()
window_height = modes[1][1] if len(modes) > 1 else modes[0][1]

def DimensionToPixels(dimension):
  return int((1.0 * dimension * window_height) / iphone_dims[1])

def DimensionsToPixels(dimensions):
  return [DimensionToPixels(x) for x in dimensions]

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

def DrawTargetBox():
  box = [iphone_dims[0] * (1.0 - target_box_width - target_box_padding),
         iphone_dims[1] * target_box_padding,
         iphone_dims[0] * target_box_width,
         iphone_dims[1] * (1.0 - target_box_padding * 2)]
  pygame.draw.rect(GetSurface(), draw_color, DimensionsToPixels(box), 1)

def DrawLabel(x_off, y_off, label, color, border=False):
  max_y = 1.0 - target_box_padding * 2
  y_off = y_off * max_y + target_box_padding * iphone_dims[1]
  ts = sys_font.render(label, True, color)
  offset = DimensionsToPixels([x_off, y_off])
  GetSurface().blit(ts, offset)
  pygame.draw.line(GetSurface(), line_color,
                   (offset[0] + ts.get_width(), offset[1] + ts.get_height()),
                   (window_dimensions[0], offset[1] + ts.get_height()), 1)
  if border:
    pygame.draw.rect(GetSurface(), color,
                     [offset[0], offset[1], ts.get_width(), ts.get_height()], 1)

def DrawLabels(labels, x_off, transparency):
  color = pygame.Color(*[int(x + transparency * (y - x)) for x, y in zip(text_color, backdrop_color)])
  for label, pos in zip(labels, xrange(len(labels))):
    DrawLabel(x_off, (float(pos) * iphone_dims[1]) / (len(labels) - 1), label, color)

def EnforceBounds(val, min_val, max_val):
  val = max(val, min_val)
  return min(val, max_val)

def ProcessMotion(active, last_pos):
  new_pos = last_pos
  for event in pygame.event.get():
    if event.type == pygame.QUIT or event.type == pygame.KEYDOWN:
      return sys.exit(0)
    if active:
      if event.type == pygame.MOUSEMOTION:
        if event.buttons[0]:
          new_pos = event.pos
      elif event.type == pygame.MOUSEBUTTONUP:
        if event.button == 1:
          active = False
    else:
      if event.type == pygame.MOUSEBUTTONDOWN:
        if event.button == 1:
          x_pos, y_pos = [float(pos) / dim for pos, dim in zip(event.pos, window_dimensions)]
          if x_pos > (1.0 - target_box_width - target_box_padding) and \
                x_pos < (1.0 - target_box_padding) and \
                y_pos > target_box_padding and \
                y_pos < 1.0 - target_box_padding:
            active = True
            new_pos = event.pos

  x_ratio = EnforceBounds(float(new_pos[0]) / window_dimensions[0], 0.0, 1.0)
  old_y_ratio = EnforceBounds(float(last_pos[1]) / window_dimensions[1], 0.0, 1.0)
  y_ratio = EnforceBounds(float(new_pos[1]) / window_dimensions[1], 0.0, 1.0)
  y_delta = y_ratio - old_y_ratio

  return active, new_pos, x_ratio, y_ratio, y_delta

def GetNextMonth(date):
  if date.month == 12:
    return date.replace(year=date.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
  else:
    return date.replace(month=date.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)

def GetRange(level, max_date, min_date, cur_date):
  num_ticks = max_date.year - min_date.year + 1
  end_fmt = '%Y'
  cur_fmt = '%B %Y'
  tick_fmt = '%Y'
  if level == 'years':
    max_date = max_date.replace(year=max_date.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    min_date = min_date.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    num_ticks = max_date.year - min_date.year + 1
  if level == 'months':
    max_date = cur_date.replace(year=cur_date.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    min_date = cur_date.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    num_ticks = 13
    end_fmt = '%B %Y'
    cur_fmt = '%B %d'
    tick_fmt = '%B %Y'
  if level == 'days':
    max_date = GetNextMonth(cur_date)
    min_date = cur_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    num_ticks = (max_date - min_date).days + 1
    end_fmt = '%B %d %Y'
    cur_fmt = '%H:00'
    tick_fmt = '%B %d'
  if level == 'hours':
    min_date = cur_date.replace(hour=0, minute=0, second=0, microsecond=0)
    max_date = min_date + timedelta(days=1)
    num_ticks = 13
    end_fmt = '%B %d %Y'
    cur_fmt = '%H:%M'
    tick_fmt = '%H:00'
  return (max_date, min_date, num_ticks, tick_fmt, cur_fmt, end_fmt)

def main():
  max_date = datetime.utcnow()
  min_date = datetime(year=2008, month=3, day=13)
  cur_date = datetime.utcnow()
  active = False
  last_pos = 0, 0
  x_ratio, y_ratio = 0.0, 0.0

  # Rates encompass: X years, 12 months, 28-31 days, 24 hours.
  levels = ['hours', 'days', 'months', 'years']
  level = levels[-1]

  while True:
    ClearSurface()
    active, last_pos, x_ratio, y_ratio, y_delta = ProcessMotion(active, last_pos)
    if active:
      active_range = x_ratio / (1.0 / len(levels))
      level = levels[int(active_range)]

    end_date, start_date, num_ticks, tick_fmt, cur_fmt, end_fmt = GetRange(level, max_date, min_date, cur_date)
    delta = end_date - start_date
    secs_delta = delta.days * (3600*24) + delta.seconds

    if not active:
      DrawTargetBox()
    else:
      cur_date = end_date - timedelta(seconds=int(y_ratio * secs_delta))
      # This is a small fix to keep the dates from going haywire at the top end.
      if cur_date == end_date:
        cur_date -= timedelta(seconds=1)
      labels = [(end_date - timedelta(seconds=(secs_delta*i)/num_ticks)).strftime(end_fmt if i==0 or i==num_ticks-1 else tick_fmt) for i in xrange(num_ticks)]
      DrawLabels(labels, int(0.85 * iphone_dims[0]), 0)

    cur_delta = end_date - cur_date
    cur_secs_delta = cur_delta.days * (3600*24) + cur_delta.seconds
    DrawLabel(int(0.85 * iphone_dims[0]), (cur_secs_delta * iphone_dims[1]) / secs_delta,
              cur_date.strftime(cur_fmt), rect_color, border=True)

    pygame.display.flip()

if __name__ == '__main__':
  main()

