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
spacing = 2
row_height = 120
min_photo_height = 40
draw_text = False
if draw_text:
  row_height -= 10
max_rows_per_col = row_height / min_photo_height
sys_font = pygame.font.SysFont("fixed", 27)
photo_color = pygame.Color(127, 37, 37, 255)
screen_color = pygame.Color(255, 255, 255, 255)
backdrop_color = pygame.Color(127, 127, 127, 255)
line_color = pygame.Color(0, 0, 0, 255)
text_color = pygame.Color(67, 67, 67, 255)
aspect_ratios = [ 0.75, 1.0, 1.33333 ]

# Query display modes and choose the second largest
modes = pygame.display.list_modes()
window_dims = modes[1] if len(modes) > 1 else modes[0]
window_dims = [x for x in window_dims]

def DimensionToPixels(dimension):
  return int((1.0 * dimension * window_dims[1]) / iphone_dims[1])

def DimensionsToPixels(dimensions):
  return [DimensionToPixels(x) for x in dimensions]

# Create the simulation window
window = pygame.display.set_mode(window_dims, pygame.DOUBLEBUF | \
                                   pygame.HWSURFACE | \
                                   pygame.RESIZABLE)
pygame.display.set_caption('Image Aspect Ratio Packing')
rect_tuple = namedtuple('rect_tuple', ['x', 'y', 'w', 'h'])
view_dims = DimensionsToPixels(iphone_dims)

def GetSurface():
  return pygame.display.get_surface()

def ClearSurface():
  GetSurface().fill(backdrop_color)

def DrawScreen():
  pygame.draw.rect(GetSurface(), screen_color, [0, 0, view_dims[0], view_dims[1]], 0)

def GetImages(num_images):
  return [random.choice(aspect_ratios) for i in xrange(num_images)]

def PackImagesHelper(images, first, last_x, last_y):
  if not images:
    return [], last_x

  if first or len(images) == 1:
    ars = [images[0]]
  else:
    if len(images) == max_rows_per_col + 1:
      # If we only have just one more than the max number of rows per column,
      # left, make sure we do 2 now.
      ars = images[0:2]
    elif images[0] < 1.0 and images[1] < 1.0:
      # If both of the next two images are portrait, do a column of two images.
      ars = images[0:2]
    else:
      ars = images[0:min(len(images), max_rows_per_col)]
  ars = [1.0 / ar for ar in ars]
  sum_ars = sum(ars)
  hs = [row_height * (ar / sum_ars) for ar in ars]
  cur_y = last_y
  rects = []
  for h, ar in zip(hs, ars):
    rect = rect_tuple(x=0, y=cur_y, w=h/ar, h=h)
    cur_y += rect.h
    rects.append(rect)

  cols = [(rects[0].w, rects)]
  last_x += rects[0].w
  right_cols, right_x = PackImagesHelper(images[len(ars):], False, last_x, last_y)
  # Recursively adjust here to attempt to fill in whitespace by
  # not decreasing the size of successive images. We do this by
  # re-invoking the helper and specifying first=True so that it
  # uses a full-sized image.
  if first and right_x < iphone_dims[0] and len(images) > 2:
    right_cols, right_x = PackImagesHelper(images[len(ars):], True, last_x, last_y)
  cols += right_cols
  return cols, right_x

def PackImages(images, last_y):
  cols, right_x = PackImagesHelper(images, True, 0, last_y)
  # Now order the rows of rects by width.
  rects = []
  last_x = 0
  for w, col in sorted(cols, reverse=True):
    rects += [r._replace(x=last_x) for r in col]
    last_x += col[0].w
  return rects, last_x

def TransformRect(rect):
  x = rect.x + spacing/2
  y = rect.y + spacing/2
  w, h = rect.w - spacing, rect.h - spacing
  return pygame.Rect([DimensionsToPixels(p) for p in [(x, y), (w, h)]])

def Draw(rects):
  for rect in rects:
    t_rect = TransformRect(rect)
    pygame.draw.rect(GetSurface(), photo_color, t_rect, 0)

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
  events = ReadAspectRatios(os.path.join(os.path.dirname(sys.argv[0]), 'aspect_ratio.txt')).values()
  random.shuffle(events)

  num_per_screen = (iphone_dims[1] + row_height - 1) / row_height
  event_count = 1
  while events:
    ClearSurface()
    DrawScreen()
    last_y = 0
    center_cropping = False
    cur_event = event_count
    for event_images in events[:num_per_screen]:
      if draw_text:
        ts = sys_font.render('Event #%d (%d photos)' % (cur_event, len(event_images)),
                             True, text_color)
        GetSurface().blit(ts, DimensionsToPixels([5, last_y]))
        last_y += 10
      rects, last_x = PackImages(event_images, last_y)
      Draw(rects)
      # If there is whitespace, increase aspect ratio via center
      # crop; this will animate due to center-cropping flag.
      if last_x < iphone_dims[0]:
        center_cropping = True
        cur_w = rects[0].w
        delta = (iphone_dims[0] - last_x)
        new_w = cur_w + min(15, delta)
        event_images[0] = float(new_w) / rects[0].h
      cur_event += 1
      last_y += row_height
    pygame.display.flip()

    if not center_cropping:
      raw_input('press enter for next simulation')
      event_count += num_per_screen
      events = events[num_per_screen:]

if __name__ == '__main__':
  main()

