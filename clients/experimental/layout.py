#!/usr/bin/env python

from collections import namedtuple
import os
import pygame
import random
import sys
import time

pygame.init()
pygame.font.init()

iphone_dims = 320, 480
spacing = 5
draw_color = pygame.Color(127, 37, 37, 255)
backdrop_color = pygame.Color(255, 255, 255, 255)
aspect_ratios = [ 0.75, 1.0, 1.33333 ]

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
pygame.display.set_caption('Image Aspect Ratio Packing')
rect_tuple = namedtuple('rect_tuple', ['x', 'y', 'w', 'h'])

def GetSurface():
  return pygame.display.get_surface()

def ClearSurface():
  GetSurface().fill(backdrop_color)

def GetImages(num_images):
  return [random.choice(aspect_ratios) for i in xrange(num_images)]

def GetFirstRank(images, last_y):
  ar = images[0]
  if (ar < 1.0 and len(images) > 1) or len(images) == 2:
    return [], last_y

  rect = rect_tuple(x=0, y=last_y, w=iphone_dims[0], h=iphone_dims[0]/ar)
  return [rect], rect.h

def GetSecondRank(images, last_y):
  if not images or len(images) == 3:
    return [], last_y
  ar1 = images[0]
  ar2 = images[1]
  sum_ars = ar1 + ar2
  w1 = iphone_dims[0] * (ar1 / sum_ars)
  w2 = iphone_dims[0] * (ar2 / sum_ars)
  rect1 = rect_tuple(x=0, y=last_y, w=w1, h=w1/ar1)
  rect2 = rect_tuple(x=rect1.w, y=last_y, w=w2, h=w2/ar2)
  return [rect1, rect2], last_y + max(rect1.h, rect2.h)

def GetThirdRank(images, last_y):
  rows = []
  while images:
    assert len(images) != 1
    if len(images) == 5:
      ars = images[0:2]
    else:
      ars = images[0:min(len(images), 4)]
    sum_ars = sum(ars)
    ws = [iphone_dims[0] * (ar / sum_ars) for ar in ars]
    last_x = 0
    rects = []
    for w, ar in zip(ws, ars):
      rect = rect_tuple(x=last_x, y=0, w=w, h=w/ar)
      last_x += rect.w
      rects.append(rect)
    images = images[len(ars):]
    rows.append((rects[0].h, rects))

  # Now order the rows of rects by height.
  rects = []
  for h, row in sorted(rows, reverse=True):
    rects += [r._replace(y=last_y) for r in row]
    last_y += row[0].h
  return rects, last_y

def PackImages(images):
  packed = []
  rects, last_y = GetFirstRank(images, 0)
  packed += rects
  rects, last_y = GetSecondRank(images[len(packed):], last_y)
  packed += rects
  rects, last_y = GetThirdRank(images[len(packed):], last_y)
  packed += rects
  return packed

def TransformRect(rect):
  x = rect.x + spacing/2
  y = rect.y + spacing/2
  w, h = rect.w - spacing, rect.h - spacing
  return pygame.Rect([DimensionsToPixels(p) for p in [(x, y), (w, h)]])

def Draw(rects):
  for rect in rects:
    t_rect = TransformRect(rect)
    pygame.draw.rect(GetSurface(), draw_color, t_rect, 0)

def ReadAspectRatios(filename):
  f = open(filename, 'r')
  events = {}
  for line in f.readlines():
    event, img, ratio = [float(x) for x in line.split()]
    int_event = int(event)
    if not events.has_key(int_event):
      events[int_event] = []
    events[int_event].append(ratio)
  return events

def main():
  events = ReadAspectRatios(os.path.join(os.path.dirname(sys.argv[0]), 'aspect_ratio.txt'))

  for event_images in events.values():
    #num_images = random.randint(1, 24)
    #event_images = GetImages(num_images)
    rects = PackImages(event_images)
    ClearSurface()
    Draw(rects)
    pygame.display.flip()
    raw_input('press enter for next simulation')

if __name__ == '__main__':
  main()

