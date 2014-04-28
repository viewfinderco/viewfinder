#!/usr/bin/env python
#
# Copyright 2013 Viefinder Inc. All Rights Reserved.

__author__ = 'marc@emailscrubbed.com (Marc Berhault)'

import glob
import itertools
import os
import re
import shutil

from PIL import Image
from tornado import options

options.define('ninepatch', default=False, help='Generate android 9patch assets')
options.define('plain', default=False, help='Verify existence of plain assets on android')
options.define('regenerate', type=str, default=[], help='Regenerate 9patch is different. Names are source iOS images')
options.define('v', default=False, help='Verbose')

# List of files (name of iOS source image) to skip when processing plain assets.
SKIP_PLAIN = []

# List of files that are implicitly referenced.
FORCE_REFERENCE = ['Icon.png']

# This assumes the script is in ${VF_HOME}/clients/shared/scripts/
BASE_PATH=os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(__file__)), '../../../'))

# Paths relative to viewfinder home.
IOS_SOURCE_DIR=os.path.join(BASE_PATH, 'clients/ios/Source')
IOS_IMAGES_DIR=os.path.join(BASE_PATH, 'clients/ios/Source/Images')
# For now, assume they all go into x
ANDROID_IMAGES_DIR=os.path.join(BASE_PATH, 'clients/android/res/drawable-xhdpi')

def ImageName2X(name):
  base, ext = name.rsplit('.', 1)
  return '%s@2x.%s' % (base, ext)

def ImageName9Patch(name):
  base, ext = name.split('.')
  return ImageNameAndroid('%s.9.%s' % (base, ext))

def ImageNameAndroid(name):
  return name.replace('-', '_').lower()

def FindFilesIn(directory, pattern):
  """ Returns the list of all files in 'directory' matching the glob 'pattern'. """
  return  glob.glob(os.path.join(directory, pattern))


def ListBasename(filelist):
  """ Turns a list of paths into a list of basenames for each entry. """
  return [os.path.basename(f) for f in filelist]


def FindReferencedIOSImages():
  """ Find images referenced in the code and return a dict of "filename" -> "inset quad". """
  source_files = FindFilesIn(IOS_SOURCE_DIR, '*.mm')
  image_re = re.compile(r'^LazyStaticImage [^;]+;', re.MULTILINE)
  file_re = re.compile(r'@"([^"]+)"')
  # We're assuming the UIEdgeInsetsMake call is not split across lines. We strip whitespace away before searching.
  inset_re = re.compile(r'UIEdgeInsetsMake\(([0-9.]+),([0-9.]+),([0-9.]+),([0-9.]+)\)')

  def ParseLazyStaticImage(line):
    # Extract name
    result = file_re.search(line)
    assert result is not None, 'Could not extract filename from %r' % line
    name = result.group(1)
    # iOS assumes a .png extension if none is specified.
    if '.' not in name:
      name += '.png'

    # Look for edge inset. Replace whitespace to make the regexp simpler.
    inset = None
    if re.search(r'UIEdgeInsetsMake', line) is not None:
      result = inset_re.search(re.sub(r'\s','',line))
      assert result is not None, 'Found UIEdgeInsetsMake, but could not parse arguments: %r' % line
      assert len(result.groups()) == 4, 'invalid inset call: %r' % line
      inset = tuple([float(x) for x in result.groups()])

    return (name, inset)

  filenames = dict()
  for f in source_files:
    contents = open(f, 'r').read()
    for i in image_re.findall(contents):
      name, inset = ParseLazyStaticImage(i)

      if name in filenames:
        assert filenames[name] == inset, 'Image found with different insets: %s' % name
      else:
        filenames[name] = inset

  # Adjust for images that aren't explicitly referenced in the code.
  for name in FORCE_REFERENCE:
    filenames[name] = None

  return filenames


def FindMissingImages(referenced_images, asset_images):
  """ Check that every referenced image (and its 2x version) is found in 'asset_images'. """
  images = set(asset_images)
  for ref in referenced_images:
    if ref not in images:
      print '%s does not exist' % ref
    if ImageName2X(ref) not in images:
      print '%s does not exist' % ref_2x


def GetInsetFrom9Patch(path):
  """ Given the path to a 9-patch image, extract the regions and return an iOS inset specification:
  (top, left, bottom, right) in points.
  Android 9-patch is a regular image with an extra 1 pixel frame. Each frame pixel has value either 0 or 255.
  See: http://developer.android.com/guide/topics/graphics/2d-graphics.html#nine-patch
  The black lines in the example are actually present in the file, they are stored in the 1 pixel frame.

  We extract those lines and count the number of pixels before and after the area, which gives us the iOS
  specification passed to UIEdgeInsetsMake.
  """
  img = Image.open(path)
  pixels = img.load()
  width, height = img.size
  vert_line = [ pixels[0, y][3] for y in xrange(height) ]
  hor_line = [ pixels[x, 0][3] for x in xrange(width) ]
  # We want the real image limits, so remove the first and last row/col.
  vert_line = vert_line[1:-1]
  hor_line = hor_line[1:-1]

  # Find the size of each group of "0" or "255" in the extra pixels.
  vert_groups = [(k, len(list(g))) for k, g in itertools.groupby(vert_line)]
  hor_groups = [(k, len(list(g))) for k, g in itertools.groupby(hor_line)]

  assert len(vert_groups) <= 3, vert_groups
  assert len(hor_groups) <= 3, hor_groups

  # Generate iOS-style boundaries: (delta top, delta left, delta bottom, delta right)
  # Since we're operating on 2x images, we devide by two to get values in points instead of pixels.
  top = left = bottom = right = 0
  if vert_groups[0][0] == 0:
    top = float(vert_groups[0][1]) / 2
  if vert_groups[-1][0] == 0:
    bottom = float(vert_groups[-1][1]) / 2
  if hor_groups[0][0] == 0:
    left = float(hor_groups[0][1]) / 2
  if hor_groups[-1][0] == 0:
    right = float(hor_groups[-1][1]) / 2
  return (top, left, bottom, right)


def Generate9PatchFromInset(src_path, src_inset, dest_path, just_print_errors):
  """ Generate an android 9-patch at 'dest_path' from a source image at 'src_path' using the iOS inset 'src_inset'. """
  src_img = Image.open(src_path)
  width, height = src_img.size

  # Create a new image with the same mode but 1-pixel frame.
  new_width = width + 2
  new_height = height + 2
  new_img = Image.new('RGBA', size=(new_width, new_height), color=(0, 0, 0, 0))

  src_pixels = src_img.load()
  new_pixels = new_img.load()
  # Copy the source pixels into the dest image with an offset of (1, 1).
  # The paste command does weird things with the alpha band, so we do it manually.
  is_rgb = src_img.mode == 'RGB'
  for x in xrange(width):
    for y in xrange(height):
      pixel = src_pixels[x, y]
      if is_rgb:
        # If the source image does not have an alpha channel, we need to add one.
        assert len(pixel) == 3, 'RGB image with %d channels' % len(pixel)
        new_pixels[x + 1, y + 1] = pixel + (255,)
      else:
        assert len(pixel) == 4, 'RGBA image with %d channels' % len(pixel)
        new_pixels[x + 1, y + 1] = pixel

  # Go through the src inset. Multiple by two to convert from points to pixels in the 2x image.
  top, left, bottom, right = [int(x * 2) for x in src_inset]
  # Look for the size of the region. width - left - right and height - top - bottom
  region_hor = width - left - right
  region_ver = height - top - bottom
  print '  width=%f, left=%f, right=%f' % (width, left, right)
  print '  height=%f, top=%f, bottom=%f' % (height, top, bottom)
  if (region_hor <= 0 or region_ver <= 0):
    print '  ERROR: scaling region has width or height <= 0'
    return

  assert region_hor > 0
  assert region_ver > 0

  # We set the scale pixels as: 0, 0 * left, 255 * region_hor, 0 * right, 0
  # We set the fill pixels as 0, 0 * width, 0
  # The start and end 0 are for the 1-pixel frame.
  line_hor_scale = [0] + ([0] * left) + ([255] * region_hor) + ([0] * right) + [0]
  line_hor_fill = [0] + ([255] * width) + [0]
  line_ver_scale = [0] + ([0] * top) + ([255] * region_ver) + ([0] * bottom) + [0]
  line_ver_fill = [0] + ([255] * height) + [0]

  assert len(line_hor_scale) == new_width
  assert len(line_hor_fill) == new_width
  assert len(line_ver_scale) == new_height
  assert len(line_ver_fill) == new_height

  # Set the pixels in the frame. We specify the android 9-patch "fill" region to be the entire image.
  for y in xrange(new_height):
    new_pixels[0, y] = (0, 0, 0, line_ver_scale[y])
    new_pixels[new_width - 1, y] = (0, 0, 0, line_ver_fill[y])
  for x in xrange(new_width):
    new_pixels[x, 0] = (0, 0, 0, line_hor_scale[x])
    new_pixels[x, new_height - 1] = (0, 0, 0, line_hor_fill[x])

  if not just_print_errors:
    print '  Writing 9-patch: %s with size: %r' % (dest_path, new_img.size)
    new_img.save(dest_path)


def GenerateAndroid9Patch(referenced_images):
  """ Iterate over all referenced images with insets and check against the android 9-patch images. """
  for name, inset in referenced_images.iteritems():
    if inset is None:
      continue

    img_path = os.path.join(IOS_IMAGES_DIR, ImageName2X(name))
    assert os.access(img_path, os.R_OK), '2x version of %s is not readable' % name

    nine_path = os.path.join(ANDROID_IMAGES_DIR, ImageName9Patch(name))
    generate_9patch = True
    if os.access(nine_path, os.R_OK):
      generate_9patch = False
      android_inset = GetInsetFrom9Patch(nine_path)
      if inset == android_inset:
        if options.options.v:
          print '%s: OK %r' % (name, inset)
      else:
        print '%s: 9-patch with different inset:' % name
        print '  iOS 2x:   size: %r, inset: %r' % (Image.open(img_path).size, inset)
        print '  android:  size: %r, inset: %r' % (Image.open(nine_path).size, android_inset)
        # Dry run to print any errors.
        Generate9PatchFromInset(img_path, inset, nine_path, True)
        if name in options.options.regenerate:
          print '  Regenerating 9 patch...'
          generate_9patch = True
    if generate_9patch:
      print '%s: generating 9-patch with inset %r' % (name, inset)
      print '  iOS 2x:   size: %r, inset: %r' % (Image.open(img_path).size, inset)
      Generate9PatchFromInset(img_path, inset, nine_path, False)


def FindMissingAndroidPlainAssets(referenced_images, android_assets):
  """ Iterate over all referenced images in iOS. For each plain asset (without an inset), check whether it
  exists in the android assets list.
  """
  for name, inset in referenced_images.iteritems():
    if inset is not None:
      continue
    if name in SKIP_PLAIN:
      print 'WARNING: %s: skipping due to hard-coded exclusion in assets-tool.py' % name
      continue
    android_name = ImageNameAndroid(name)
    if android_name not in android_assets:
      name_2x = ImageName2X(name)
      shutil.copyfile(os.path.join(IOS_IMAGES_DIR, name_2x), os.path.join(ANDROID_IMAGES_DIR, android_name))
      print '%s: not in android assets, copied %s -> %s' % (name, name_2x, android_name)
    else:
      if options.options.v:
        print '%s: OK' % name

if __name__ == '__main__':
  options.parse_command_line(final=True)
  # Images found in the code. dict of "filename" -> "inset quad"
  referenced_images = FindReferencedIOSImages()
  # Full list of files in the images directory, filenames only.
  asset_images = ListBasename(FindFilesIn(IOS_IMAGES_DIR, '*'))

  FindMissingImages(sorted(referenced_images.keys()), asset_images)

  if options.options.ninepatch:
    GenerateAndroid9Patch(referenced_images)
  if options.options.plain:
    android_assets = ListBasename(FindFilesIn(ANDROID_IMAGES_DIR, '*'))
    FindMissingAndroidPlainAssets(referenced_images, android_assets)
