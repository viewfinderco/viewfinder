// Copyright 2012 Viewfinder Inc. All Rights Reserved.

/**
 * @fileoverview utilities methods.
 *
 * @author spencer@emailscrubbed.com (Spencer Kimball)
 */

viewfinder.util = {};

/**
 * Assertions. We allow these to be in the global namespace.
 */
function AssertException(message) { this.message = message; }
AssertException.prototype.toString = function () {
  return 'AssertException: ' + this.message;
}

function assert(exp, message) {
  if (!exp) {
    throw new AssertException(message);
  }
}

/**
 * Randomly shuffles the provided array.
 */
viewfinder.util.arrayShuffle = function(theArray) {
  var len = theArray.length;
  var i = len;
  while (i--) {
    var p = parseInt(Math.random() * len);
    var t = theArray[i];
    theArray[i] = theArray[p];
    theArray[p] = t;
  }
}

/**
 * Chooses a random integer between the specified range.
 * @param {array} range high and low values for the random choice.
 */
viewfinder.util.chooseRandomInt = function(range) {
  var diff = range[1] - range[0];
  return range[0] + Math.floor(Math.random() * (diff + 1));
}

/**
 * Joins the elements of an array ('arr'), excluding nulls and empty
 * strings, using the provided 'sep' string.
 *
 * @param {array} arr.
 * @param {string} sep.
 */
viewfinder.util.joinExceptNull = function(arr, sep) {
  var new_arr = [];
  for (var i = 0; i < arr.length; i++) {
    if (arr[i] != null && arr[i] != '') {
      new_arr.push(arr[i]);
    }
  }
  return new_arr.join(sep);
}

/**
 * Computes a dictionary of x, y offsets and w, h image scale size so
 * that the image fits as closely into the provided dimensions as
 * possible. If the aspect ratios don't match, the image will be
 * centered, with overflow hidden. If the aspect ratio is portrait in
 * the original image, then it will be vertically aligned to 1/4 of
 * the image instead of centered exactly in order to keep more of
 * the likely region of interest in the frame.
 *
 * @param {number} width of the image display container.
 * @param {number} height of the image display container.
 * @param {object} $img the jquery image element.
 */
viewfinder.util.computeImageXYWH = function(width, height, $img) {
  var imgWidth = $img.origWidth || $img[0].width;
  var imgHeight = $img.origHeight || $img[0].height;
  var imgAr = imgWidth / imgHeight;
  var dispAr = width / height;
  var x, y, w, h;
  if (imgAr > dispAr) {
    h = height;
    w = Math.floor(imgWidth * (height / imgHeight));
    x = Math.floor((width - w) * 0.50);
    y = 0;
  } else {
    w = width;
    h = Math.floor(imgHeight * (width / imgWidth));
    x = 0;
    if (dispAr > 1.0) {
      y = Math.floor((height - h) * (imgAr <= 1.0 ? 0.25 : 0.35));
    } else {
      y = Math.floor((height - h) * (imgAr <= 1.0 ? 0.0 : 0.25));
    }
  }
  return {left: x, top: y, width: w, height: h};
};

/**
 * Fits the provided array of rectangles either horizontally or
 * vertically (according to 'horiz') into the provided space. The first
 * rect is always laid out at full size. Successive rects are laid out
 * multiply in groups according to a maximum per group of maxPerDim. For
 * example, if 'horiz' == true, then rects are laid out horizontally in
 * successive columns. The first column will contain a single rect with
 * full height. The next column will contain up to maxPerDim rects,
 * stacked vertically.
 *
 * @param {array} array of rect objects.
 * @param {number} maximum number of rects per dimension.
 * @param {boolean} horizontal or vertical.
 * @return {array} of rect {x, y, w, h} objects.
 */
viewfinder.util.layoutRects = function(rects, maxPerDim, horiz) {
  var layoutRects = [];
  var lastX = 0.0;
  var lastY = 0.0;
  var first = true;

  while (rects.length > 0) {
    var rectArr = [];
    if (first || rects.length == 1) {
      rectArr.push(rects.shift());
    } else {
      if (maxPerDim == 1) {
        rectArr = rects.slice(0, 1);
      } else if (rects.length == maxPerDim + 1) {
        // If we only have just one more than the max number of rects per dim,
        // left, make sure we do 2 now.
        rectArr = rects.slice(0, 2);
      } else if (horiz && rects[0].w < 1.0 && rects[1].w < 1.0) {
        // If both of the next two rects are portrait, do a column of two rects.
        rectArr = rects.slice(0, 2);
      } else if (!horiz && rects[0].w > 1.0 && rects[1].w > 1.0) {
        // if both of the next two rects are landscape, do a row of two rects.
        rectArr = rects.slice(0, 2);
      } else {
        rectArr = rects.slice(0, Math.min(rects.length, maxPerDim));
      }
      rects = rects.slice(rectArr.length);
    }

    // Layout rects in columns that extend horizontally.
    if (horiz) {
      var sumIAR = 0.0;
      for (var i = 0; i < rectArr.length; i++) {
        sumIAR += rectArr[i].h / rectArr[i].w;
      }

      for (var i = 0, curY = 0; i < rectArr.length; i++) {
        iar = rectArr[i].h / rectArr[i].w;
        rectArr[i].x = lastX;
        rectArr[i].y = curY;
        rectArr[i].w = 1.0 / sumIAR;
        rectArr[i].h = iar / sumIAR;
        curY += rectArr[i].h;
      }
      lastX += 1.0 / sumIAR;
    } else {
      // Layout rects in rows that extend vertically.
      var sumAR = 0.0;
      for (var i = 0; i < rectArr.length; i++) {
        sumAR += rectArr[i].w / rectArr[i].h;
      }

      for (var i = 0, curX = 0; i < rectArr.length; i++) {
        ar = rectArr[i].w / rectArr[i].h;
        rectArr[i].x = curX;
        rectArr[i].y = lastY;
        rectArr[i].w = ar / sumAR;
        rectArr[i].h = 1.0 / sumAR;
        curX += rectArr[i].w;
      }
      lastY += 1.0 / sumAR;
    }
    layoutRects = layoutRects.concat(rectArr);
    first = false;
  }
  return layoutRects;
};
